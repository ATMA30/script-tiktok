"""Téléchargement borné : HTTPS, adresses publiques, taille, durée, type."""

import socket

import pytest

from usine.media import reseau

IP_PUBLIQUE = "93.184.216.34"


class _Reponse:
    def __init__(self, status=200, headers=None, morceaux=(b"x" * 1000,)):
        self.status_code = status
        self.headers = headers or {"Content-Type": "image/jpeg"}
        self.is_redirect = status in (301, 302, 303, 307, 308)
        self._morceaux = morceaux

    def iter_content(self, taille):
        yield from self._morceaux

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def dns(monkeypatch):
    """Faux DNS : hôte → IP, réglable par test."""
    table = {"exemple.com": IP_PUBLIQUE, "cdn.exemple.com": IP_PUBLIQUE}

    def getaddrinfo(hote, port, *args, **kwargs):
        if hote not in table:
            raise socket.gaierror("inconnu")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[hote], port))]

    monkeypatch.setattr(reseau.socket, "getaddrinfo", getaddrinfo)
    return table


@pytest.fixture
def http(monkeypatch):
    """Faux requests.get : URL → réponse."""
    reponses = {}
    appels = []

    def get(url, **kwargs):
        appels.append(url)
        return reponses[url]

    monkeypatch.setattr(reseau.requests, "get", get)
    return reponses, appels


def test_succes_ecrit_le_fichier_sans_residu(dns, http, tmp_path):
    reponses, _ = http
    reponses["https://exemple.com/a.jpg"] = _Reponse()
    chemin = tmp_path / "a.jpg"
    assert reseau.telecharger_vers_fichier("https://exemple.com/a.jpg", str(chemin))
    assert chemin.read_bytes() == b"x" * 1000
    assert not (tmp_path / "a.jpg.part").exists()


@pytest.mark.parametrize(
    "url", ["http://exemple.com/a.jpg", "file:///etc/passwd", "ftp://exemple.com/a"]
)
def test_schemas_non_https_refuses(dns, http, tmp_path, url):
    assert not reseau.telecharger_vers_fichier(url, str(tmp_path / "x"))
    assert http[1] == []  # aucune requête partie


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "192.168.1.1", "10.0.0.5", "169.254.169.254"]
)
def test_adresses_internes_refusees(dns, http, tmp_path, ip):
    dns["interne.exemple.com"] = ip
    url = "https://interne.exemple.com/a.jpg"
    assert not reseau.telecharger_vers_fichier(url, str(tmp_path / "x"))
    assert http[1] == []


def test_redirection_vers_adresse_interne_refusee(dns, http, tmp_path):
    reponses, appels = http
    dns["metadata.local"] = "169.254.169.254"
    reponses["https://exemple.com/a.jpg"] = _Reponse(
        302, {"Location": "https://metadata.local/latest"}
    )
    assert not reseau.telecharger_vers_fichier(
        "https://exemple.com/a.jpg", str(tmp_path / "x")
    )
    assert appels == ["https://exemple.com/a.jpg"]


def test_redirection_publique_suivie(dns, http, tmp_path):
    reponses, appels = http
    reponses["https://exemple.com/a.jpg"] = _Reponse(
        302, {"Location": "https://cdn.exemple.com/a.jpg"}
    )
    reponses["https://cdn.exemple.com/a.jpg"] = _Reponse()
    assert reseau.telecharger_vers_fichier(
        "https://exemple.com/a.jpg", str(tmp_path / "x")
    )
    assert appels == ["https://exemple.com/a.jpg", "https://cdn.exemple.com/a.jpg"]


def test_taille_annoncee_trop_grande(dns, http, tmp_path):
    reponses, _ = http
    reponses["https://exemple.com/a.jpg"] = _Reponse(
        headers={"Content-Type": "image/jpeg", "Content-Length": str(10**9)}
    )
    assert not reseau.telecharger_vers_fichier(
        "https://exemple.com/a.jpg", str(tmp_path / "x")
    )


def test_flux_sans_fin_coupe_au_plafond(dns, http, tmp_path):
    reponses, _ = http
    reponses["https://exemple.com/a.jpg"] = _Reponse(morceaux=[b"x" * 4096] * 100)
    chemin = tmp_path / "x"
    assert not reseau.telecharger_vers_fichier(
        "https://exemple.com/a.jpg", str(chemin), max_octets=10_000
    )
    assert not chemin.exists() and not (tmp_path / "x.part").exists()


def test_type_de_contenu_refuse(dns, http, tmp_path):
    reponses, _ = http
    reponses["https://exemple.com/a.jpg"] = _Reponse(
        headers={"Content-Type": "text/html"}
    )
    assert not reseau.telecharger_vers_fichier(
        "https://exemple.com/a.jpg", str(tmp_path / "x")
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://" + "a" * 70 + ".com/x.jpg",
        "https://../x.jpg",
        "https://exemple.com:99999/x",
    ],
)
def test_url_malformee_refusee_sans_planter(dns, http, tmp_path, url):
    # Régression : UnicodeError (IDNA) et port invalide remontaient à l'appelant.
    assert not reseau.telecharger_vers_fichier(url, str(tmp_path / "x"))


def test_octet_stream_accepte_pour_les_images(dns, http, tmp_path):
    reponses, _ = http
    reponses["https://exemple.com/a"] = _Reponse(
        headers={"Content-Type": "application/octet-stream"}
    )
    assert reseau.telecharger_vers_fichier("https://exemple.com/a", str(tmp_path / "x"))


def test_serveur_goutte_a_goutte_coupe_a_l_echeance(dns, http, tmp_path):
    import threading
    import time

    class _Lent(_Reponse):
        def __init__(self):
            super().__init__()
            self._ferme = threading.Event()

        def close(self):
            self._ferme.set()

        def iter_content(self, taille):
            yield b"x"
            # Bloque comme une lecture réseau tant que la connexion n'est pas fermée.
            self._ferme.wait(10)
            raise AttributeError("'NoneType' object has no attribute 'read'")

    reponses, _ = http
    reponses["https://exemple.com/a.jpg"] = _Lent()
    debut = time.monotonic()
    ok = reseau.telecharger_vers_fichier(
        "https://exemple.com/a.jpg", str(tmp_path / "x"), duree_max=0.3
    )
    assert not ok and time.monotonic() - debut < 3
    assert not (tmp_path / "x.part").exists()


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1\\@exemple.com/x.jpg",  # urlparse lit exemple.com, requests 127.0.0.1
        "https://10.0.0.1:443\\@exemple.com/x.jpg",
        "https://faß.de/x.jpg",  # IDNA 2003 ≠ 2008
        "https://exemple.com:8443/x.jpg",
    ],
)
def test_contournements_du_filtre_refuses(dns, http, tmp_path, url):
    assert not reseau.telecharger_vers_fichier(url, str(tmp_path / "x"))
    assert http[1] == []  # aucune requête partie


def test_url_envoyee_est_celle_verifiee(dns, http, tmp_path):
    reponses, appels = http
    url = "https://exemple.com/a b.jpg"
    preparee = reseau.verifier_url(url)
    reponses[preparee] = _Reponse()
    assert reseau.telecharger_vers_fichier(url, str(tmp_path / "x"))
    assert appels == [preparee]


def test_en_tetes_au_goutte_a_goutte_coupes_a_l_echeance(dns, monkeypatch, tmp_path):
    import time

    def get_lent(url, **kwargs):
        time.sleep(5)  # serveur qui égrène ses en-têtes
        return _Reponse()

    monkeypatch.setattr(reseau.requests, "get", get_lent)
    debut = time.monotonic()
    assert not reseau.telecharger_vers_fichier(
        "https://exemple.com/a.jpg", str(tmp_path / "x"), duree_max=0.3
    )
    assert time.monotonic() - debut < 3


@pytest.mark.parametrize("phase", ["en-tetes", "corps"])
def test_echeance_sur_un_vrai_socket(monkeypatch, tmp_path, phase):
    # Vrai serveur local qui envoie 1 octet par seconde : l'ancienne échéance
    # (minuteur + resp.close) restait bloquée ~20 s sur une vraie socket.
    import socketserver
    import time

    class Goutte(socketserver.BaseRequestHandler):
        def handle(self):
            entetes = b"HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\n\r\n"
            try:
                if phase == "corps":
                    self.request.sendall(entetes)
                    morceaux = [b"x"] * 30
                else:
                    morceaux = [bytes([o]) for o in entetes]
                for octet in morceaux:
                    self.request.sendall(octet)
                    time.sleep(1)
            except OSError:
                pass

    serveur = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Goutte)
    serveur.daemon_threads = True
    threading = __import__("threading")
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{serveur.server_address[1]}/a.jpg"
        monkeypatch.setattr(reseau, "verifier_url", lambda u: u)  # autorise le local
        debut = time.monotonic()
        ok = reseau.telecharger_vers_fichier(url, str(tmp_path / "x"), duree_max=2)
        assert not ok
        assert time.monotonic() - debut < 6
        assert not (tmp_path / "x").exists()
    finally:
        serveur.shutdown()
        serveur.server_close()
