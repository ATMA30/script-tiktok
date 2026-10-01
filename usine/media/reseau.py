"""Téléchargement borné de fichiers dont l'URL vient du web (résultats de recherche).

Garde-fous :
- HTTPS uniquement ;
- refus des hôtes qui résolvent vers une IP privée, locale ou réservée,
  y compris après une redirection (redirections suivies à la main) ;
- taille maximale (Content-Length puis compteur pendant la lecture) ;
- durée totale maximale : un minuteur ferme la connexion à l'échéance, même si
  le serveur envoie quelques octets juste sous le timeout de lecture ;
- type de contenu attendu.

Limite connue : l'adresse est vérifiée avant la requête, pas sur la socket
(rebinding DNS possible). Suffisant pour ce pipeline local.
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
    """Lève TelechargementRefuse si l'URL n'est pas HTTPS ou vise une adresse interne."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise TelechargementRefuse(f"schéma refusé ({parsed.scheme or 'aucun'})")
        if not parsed.hostname:
            raise TelechargementRefuse("hôte manquant")
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except TelechargementRefuse:
        raise
    except (OSError, ValueError) as e:  # gaierror, UnicodeError (IDNA), port invalide
        raise TelechargementRefuse(f"URL inutilisable ({e})") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise TelechargementRefuse(f"adresse non publique ({ip})")


def _ouvrir(url, headers, timeout):
    """GET en streaming, redirections suivies une à une après vérification."""
    for _ in range(MAX_REDIRECTIONS + 1):
        verifier_url(url)
        resp = requests.get(
            url, headers=headers, timeout=timeout, stream=True, allow_redirects=False
        )
        if resp.is_redirect:
            suivante = resp.headers.get("Location", "")
            resp.close()
            url = urljoin(url, suivante)
            continue
        return resp
    raise TelechargementRefuse(f"plus de {MAX_REDIRECTIONS} redirections")


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
    debut = time.monotonic()
    minuteur = None
    try:
        resp = _ouvrir(url, entetes, timeout)
        # Échéance globale : fermer la réponse débloque iter_content.
        restant = max(0.0, duree_max - (time.monotonic() - debut))
        minuteur = threading.Timer(restant, resp.close)
        minuteur.daemon = True
        minuteur.start()
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
                try:
                    for morceau in resp.iter_content(16384):
                        recus += len(morceau)
                        if recus > max_octets:
                            raise TelechargementRefuse(f"dépasse {max_octets} octets")
                        if time.monotonic() - debut > duree_max:
                            raise TelechargementRefuse(f"plus de {duree_max} s")
                        f.write(morceau)
                except TelechargementRefuse:
                    raise
                except Exception as e:
                    if not minuteur.is_alive():
                        raise TelechargementRefuse(f"plus de {duree_max} s") from e
                    raise
        os.replace(temporaire, chemin)
        return True
    except (TelechargementRefuse, requests.RequestException, ValueError) as e:
        print(f"      🚫 Téléchargement refusé : {e}")
    except Exception as e:  # OSError (disque), erreurs de lecture d'un flux fermé…
        print(f"      ⚠️ Téléchargement impossible : {type(e).__name__}: {e}")
    finally:
        if minuteur is not None:
            minuteur.cancel()
    try:
        if os.path.exists(temporaire):
            os.remove(temporaire)
    except OSError:
        pass
    return False
