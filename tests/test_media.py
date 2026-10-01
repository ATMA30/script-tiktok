"""Tests du media fetcher : nettoyage des prompts Imagen et filtrage des URLs."""

import pytest

from usine.media import config as media_config
from usine.media.generation import nettoyer_prompt
from usine.media.validation import url_est_suspecte


@pytest.fixture
def style(monkeypatch):
    def _set(nom):
        monkeypatch.setattr(media_config, "STYLE_SUFFIX", getattr(media_config, nom))

    return _set


def test_nettoyer_prompt_retire_les_declencheurs_camescope(style):
    # Piège connu : VHS / camcorder / archive footage déclenchent le HUD caméscope.
    style("STYLE_SUFFIX_NOIR")
    p = nettoyer_prompt("VHS camcorder archive footage of an empty road").lower()
    for mot in ("vhs", "camcorder", "archive footage"):
        assert mot not in p


def test_nettoyer_prompt_retire_style_lock_et_labels(style):
    style("STYLE_SUFFIX_NOIR")
    p = nettoyer_prompt(
        "PRIMARY SUBJECT: a man [STYLE LOCK: noir]\nSCENE ATMOSPHERE: fog"
    )
    assert "STYLE LOCK" not in p and "PRIMARY SUBJECT" not in p and "\n" not in p


def test_nettoyer_prompt_prefixe_selon_le_style(style):
    style("STYLE_SUFFIX_NOIR")
    assert nettoyer_prompt("a corridor").startswith("Black and white crime scene")
    style("STYLE_SUFFIX_LOW_POLY_3D")
    assert nettoyer_prompt("a corridor").startswith("Cinematic 3D low-poly")


def test_low_poly_conserve_hors_mode_3d_seulement(style):
    style("STYLE_SUFFIX_ANIME")
    assert "low-poly" not in nettoyer_prompt("a low-poly house").lower().split(".")[0]


def test_url_est_suspecte():
    assert url_est_suspecte("https://pornhub.com/x") is True
    assert url_est_suspecte("https://example.com/a.jpg") is False
