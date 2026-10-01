"""Téléchargement borné de fichiers dont l'URL vient du web (résultats de recherche).

Garde-fous :
- HTTPS uniquement, port 443 uniquement ;
- l'hôte est vérifié sur l'URL TELLE QUE requests la prépare (c'est elle qui
  est envoyée) : urlparse et requests ne lisent pas toujours le même hôte
  (`https://127.0.0.1\\@example.com/`), et IDNA 2003/2008 diffèrent (`faß.de`) ;
- antislash et caractères non ASCII refusés dans l'hôte brut ;
- refus des hôtes qui résolvent vers une IP privée, locale ou réservée,
  y compris après chaque redirection (suivies à la main) ;
- taille maximale (Content-Length puis compteur sur les octets décompressés) ;
- durée totale maximale, DNS, en-têtes et redirections compris : le travail
  tourne dans un fil abandonné à l'échéance, la connexion étant coupée ;
- type de contenu attendu.

Limite connue : l'adresse est vérifiée avant la connexion, pas sur la socket
(rebinding DNS possible). Ne jamais passer d'en-tête d'authentification : les
en-têtes sont renvoyés à chaque redirection.
"""

import ipaddress
import os
import socket
import threading
import time
from urllib.parse import urljoin, urlparse

import requests

MAX_OCTETS_IMAGE = 25 * 1024 * 1024
MAX_OCTETS_VIDEO = 150 * 1024 * 1024
# octet-stream : certains CDN servent ainsi des images ; le décodage reste limité
# à JPEG/PNG/WEBP par Pillow (FORMATS_IMAGE).
TYPES_IMAGE = (
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/octet-stream",
    "binary/octet-stream",
)
TYPES_VIDEO = ("video/mp4",)
MAX_REDIRECTIONS = 5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


class TelechargementRefuse(Exception):
    """URL, réponse ou contenu refusé par un garde-fou."""


def verifier_url(url):
    """Renvoie l'URL préparée (à envoyer telle quelle) ou lève TelechargementRefuse."""
    try:
        brut = urlparse(url)
        if "\\" in url or not brut.netloc.isascii():
            raise TelechargementRefuse("hôte ambigu (antislash ou caractère non ASCII)")
        preparee = requests.Request("GET", url).prepare().url
        parsed = urlparse(preparee)
        if parsed.scheme != "https":
            raise TelechargementRefuse(f"schéma refusé ({parsed.scheme or 'aucun'})")
        if not parsed.hostname:
            raise TelechargementRefuse("hôte manquant")
        if parsed.port not in (None, 443):
            raise TelechargementRefuse(f"port refusé ({parsed.port})")
        infos = socket.getaddrinfo(parsed.hostname, 443)
    except TelechargementRefuse:
        raise
    except (OSError, ValueError, requests.RequestException) as e:
        # gaierror, UnicodeError (IDNA), port invalide, URL invalide pour requests
        raise TelechargementRefuse(f"URL inutilisable ({e})") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise TelechargementRefuse(f"adresse non publique ({ip})")
    return preparee


def _ouvrir(url, headers, timeout, etat):
    """GET en streaming, redirections suivies une à une après vérification."""
    for _ in range(MAX_REDIRECTIONS + 1):
        url = verifier_url(url)
        resp = requests.get(
            url, headers=headers, timeout=timeout, stream=True, allow_redirects=False
        )
        etat["resp"] = resp
        if resp.is_redirect:
            suivante = resp.headers.get("Location", "")
            resp.close()
            url = urljoin(url, suivante)
            continue
        return resp
    raise TelechargementRefuse(f"plus de {MAX_REDIRECTIONS} redirections")


def _couper(resp):
    """Coupe la connexion pour débloquer une lecture en cours (fil abandonné)."""
    brut = getattr(resp, "raw", None)
    try:
        if brut is not None and hasattr(brut, "shutdown"):
            brut.shutdown()
        resp.close()
    except Exception:
        pass


def _telecharger(url, temporaire, max_octets, types, timeout, entetes, etat):
    resp = _ouvrir(url, entetes, timeout, etat)
    with resp:
        if resp.status_code != 200:
            raise TelechargementRefuse(f"HTTP {resp.status_code}")
        content_type = resp.headers.get("Content-Type", "").lower()
        if types and not any(t in content_type for t in types):
            raise TelechargementRefuse(f"type refusé ({content_type[:40]})")
        annonce = resp.headers.get("Content-Length", "")
        if annonce.isdigit() and int(annonce) > max_octets:
            raise TelechargementRefuse(f"trop volumineux ({int(annonce)} octets)")
        recus = 0
        with open(temporaire, "wb") as f:
            for morceau in resp.iter_content(16384):
                if etat["annule"]:
                    raise TelechargementRefuse("échéance dépassée")
                recus += len(morceau)
                if recus > max_octets:
                    raise TelechargementRefuse(f"dépasse {max_octets} octets")
                f.write(morceau)


def telecharger_vers_fichier(
    url,
    chemin,
    *,
    max_octets=MAX_OCTETS_IMAGE,
    types=TYPES_IMAGE,
    timeout=25,
    duree_max=60,
    headers=None,
):
    """Télécharge `url` dans `chemin` en respectant tous les garde-fous.

    Renvoie True si le fichier est écrit ; sinon False, sans fichier résiduel.
    """
    temporaire = f"{chemin}.part"
    entetes = {"User-Agent": USER_AGENT, **(headers or {})}
    etat = {"resp": None, "annule": False, "erreur": None, "fini": False}

    def travail():
        try:
            _telecharger(url, temporaire, max_octets, types, timeout, entetes, etat)
            etat["fini"] = True
        except BaseException as e:  # remonté au fil principal
            etat["erreur"] = e
            if etat["annule"]:  # fil abandonné : ne rien laisser derrière soi
                try:
                    os.remove(temporaire)
                except OSError:
                    pass

    fil = threading.Thread(target=travail, daemon=True)
    debut = time.monotonic()
    fil.start()
    fil.join(duree_max)
    if fil.is_alive():
        etat["annule"] = True
        if etat["resp"] is not None:
            _couper(etat["resp"])
        fil.join(2)
        etat["erreur"] = TelechargementRefuse(
            f"plus de {duree_max} s ({time.monotonic() - debut:.1f} s)"
        )

    if etat["fini"] and not etat["annule"]:
        try:
            os.replace(temporaire, chemin)
            return True
        except OSError as e:
            etat["erreur"] = e
    erreur = etat["erreur"]
    if isinstance(
        erreur, (TelechargementRefuse, requests.RequestException, ValueError)
    ):
        print(f"      🚫 Téléchargement refusé : {erreur}")
    elif erreur is not None:
        print(f"      ⚠️ Téléchargement impossible : {type(erreur).__name__}: {erreur}")
    try:
        if os.path.exists(temporaire):
            os.remove(temporaire)
    except OSError:
        pass
    return False
