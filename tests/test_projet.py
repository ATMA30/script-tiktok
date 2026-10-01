"""Détection du projet courant, validation d'un projet et points d'entrée des scripts."""

import importlib
import importlib.util
import os
import time
from pathlib import Path

from usine.utils import trouver_dernier_projet

ROOT = Path(__file__).resolve().parents[1]


def test_trouver_dernier_projet_force(tmp_path, monkeypatch):
    monkeypatch.setenv("FORCE_PROJET", str(tmp_path))
    assert trouver_dernier_projet() == str(tmp_path)


def test_trouver_dernier_projet_le_plus_recent(tmp_path, monkeypatch):
    monkeypatch.delenv("FORCE_PROJET", raising=False)
    monkeypatch.chdir(tmp_path)
    assert trouver_dernier_projet() is None
    (tmp_path / "projets" / "ancien").mkdir(parents=True)
    recent = tmp_path / "projets" / "recent"
    recent.mkdir()
    futur = time.time() + 60
    os.utime(recent, (futur, futur))
    assert trouver_dernier_projet() == os.path.join("projets", "recent")


def test_validate_project(projet_factice, tmp_path):
    from validate_project import validate_project

    assert validate_project(projet_factice) == 0
    assert validate_project(projet_factice, strict=True) == 1  # pas de final.mp4
    assert validate_project(tmp_path / "inexistant") == 1


def _charger_script(nom):
    # Les noms de scripts commencent par un chiffre (et 2.7_… contient un point).
    spec = importlib.util.spec_from_file_location(nom.replace(".", "_"), ROOT / nom)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scripts_enveloppes_pointent_vers_le_package():
    from usine.media.fetcher import main as media_main
    from usine.render.pipeline import main as render_main

    assert _charger_script("3_render_hyperframes.py").main is render_main
    assert _charger_script("2.7_media_fetcher.py").main is media_main
