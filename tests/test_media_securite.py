"""Garde-fous de sécurité du media fetcher : NSFW, audit du cache, formats, logs."""

from types import SimpleNamespace

import pytest
import requests
from PIL import Image

from usine.media import images, sources, validation


class _FauxGemini:
    """Client Gemini factice : répond toujours la même chose."""

    def __init__(self, reponse):
        self.models = SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(text=reponse)
        )


@pytest.fixture
def image_jpg(tmp_path):
    chemin = tmp_path / "img.jpg"
    Image.new("RGB", (64, 64), (200, 50, 50)).save(chemin)
    return chemin


def test_nsfw_rejete_sans_gemini(monkeypatch, image_jpg):
    monkeypatch.setattr(validation, "gemini_client", None)
    assert validation.verifier_securite_image(str(image_jpg)) is False


def test_nsfw_suit_la_reponse_de_gemini(monkeypatch, image_jpg):
    monkeypatch.setattr(validation, "gemini_client", _FauxGemini("SAFE"))
    assert validation.verifier_securite_image(str(image_jpg)) is True
    monkeypatch.setattr(validation, "gemini_client", _FauxGemini("UNSAFE"))
    assert validation.verifier_securite_image(str(image_jpg)) is False


def test_formats_exotiques_refuses(monkeypatch, tmp_path):
    # Un GIF déguisé en .jpg ne doit pas être décodé (Pillow devinerait le format).
    faux = tmp_path / "faux.jpg"
    Image.new("RGB", (64, 64)).save(faux, format="GIF")
    monkeypatch.setattr(validation, "gemini_client", _FauxGemini("SAFE"))
    assert validation.verifier_securite_image(str(faux)) is False
    assert images.normaliser_image(str(faux)) is False


def _projet_avec_cache(tmp_path):
    projet = tmp_path / "projets" / "p1"
    (projet / "real_media" / "scene_1").mkdir(parents=True)
    dedans = projet / "real_media" / "scene_1" / "plan_1.jpg"
    Image.new("RGB", (64, 64)).save(dedans)
    dehors = tmp_path / "ailleurs.jpg"
    Image.new("RGB", (64, 64)).save(dehors)
    plan = {
        "scene_1": [
            {
                "file_path": "projets/p1/real_media/scene_1/plan_1.jpg",
                "source_type": "imagen",
            },
            {"file_path": str(dehors), "source_type": "imagen"},
        ]
    }
    return dedans, dehors, plan


def test_audit_cache_sans_gemini_ne_supprime_rien(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    dedans, dehors, plan = _projet_avec_cache(tmp_path)
    monkeypatch.setattr(validation, "gemini_client", None)
    validation.auditer_et_nettoyer_cache("projets/p1", plan, "affaire")
    assert dedans.exists() and dehors.exists()


def test_audit_cache_ne_supprime_que_dans_le_projet(monkeypatch, tmp_path):
    # Régression : les chemins relatifs pointaient vers un ancien dossier codé en dur,
    # et rien n'empêchait de supprimer un fichier hors du projet.
    monkeypatch.chdir(tmp_path)
    dedans, dehors, plan = _projet_avec_cache(tmp_path)
    monkeypatch.setattr(validation, "gemini_client", _FauxGemini("UNSAFE"))
    validation.auditer_et_nettoyer_cache("projets/p1", plan, "affaire")
    assert not dedans.exists()  # audité et rejeté
    assert dehors.exists()  # hors du projet : jamais touché
    assert plan["scene_1"][0]["file_path"] == ""


def test_cle_pixabay_absente_des_logs(monkeypatch, capsys, tmp_path):
    fausse_cle = "cle-factice-123"
    monkeypatch.setattr(sources, "PIXABAY_API_KEY", fausse_cle)

    def _echec(url, params=None, **kwargs):
        # Comme requests : le message d'erreur contient l'URL complète, clé comprise.
        raise requests.ConnectionError(f"échec pour {url} {params or ''}")

    monkeypatch.setattr(sources.requests, "get", _echec)
    assert sources.telecharger_pixabay_image("maison", str(tmp_path / "x.jpg")) is False
    assert fausse_cle not in capsys.readouterr().out


def test_ddg_controle_nsfw_meme_hors_mode_strict(monkeypatch, tmp_path):
    chemin = tmp_path / "ddg.jpg"
    monkeypatch.setattr(sources, "STRICT_REAL_VALIDATION", False)
    monkeypatch.setattr(
        sources,
        "_ddg_image_results",
        lambda session, q: [{"image": "https://ex.com/a.jpg"}],
    )

    def _telecharge(url, chemin_jpg, label=""):
        Image.new("RGB", (64, 64)).save(chemin_jpg)
        return True

    monkeypatch.setattr(sources, "telecharger_image_url", _telecharge)
    monkeypatch.setattr(sources, "verifier_securite_image", lambda p: False)
    assert sources.telecharger_duckduckgo_image("route", str(chemin)) is False
    assert not chemin.exists()
