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


# ── Validation humaine : rien n'est rendu sans accord ─────────────────────────


def _projet_minimal(racine, nom, statut=None, final=False):
    import json

    dossier = racine / "projets" / nom
    dossier.mkdir(parents=True)
    script = {"niche": nom, "scenes": [{"id": 1, "audio_tts": "Un suspect."}]}
    if statut:
        script["validation"] = {"statut": statut}
    (dossier / "script.json").write_text(json.dumps(script), encoding="utf-8")
    if final:
        (dossier / "final.mp4").write_bytes(b"x")
    return dossier


def test_cycle_de_validation(tmp_path):
    from usine.projet import A_VALIDER, VALIDE, est_valide, marquer, statut_validation

    projet = _projet_minimal(tmp_path, "p", statut=A_VALIDER)
    assert not est_valide(projet)
    marquer(projet, VALIDE)
    assert est_valide(projet) and statut_validation(projet) == VALIDE


def test_resume_dossier_montre_sources_incertitudes_et_noms_tus(tmp_path):
    import json

    from usine.projet import resume_dossier

    projet = _projet_minimal(tmp_path, "p")
    script = json.loads((projet / "script.json").read_text())
    script["garde_fous"] = {
        "personnes_a_taire": [{"nom": "Jean Dufour", "raison": "non condamné"}]
    }
    (projet / "script.json").write_text(json.dumps(script))
    brief = {
        "title": "L'affaire X",
        "statut_judiciaire": "instruction en cours",
        "sources": [{"name": "Le Monde", "url": "https://lemonde.fr/x"}],
        "uncertainty_flags": ["Témoignage contesté"],
    }
    (projet / "brief.json").write_text(json.dumps(brief))
    texte = resume_dossier(projet)
    for attendu in (
        "L'affaire X",
        "instruction en cours",
        "Le Monde",
        "Témoignage contesté",
        "Jean Dufour",
        "Un suspect.",
    ):
        assert attendu in texte


def test_batch_ne_rend_que_les_projets_valides(tmp_path, monkeypatch):
    import batch_produce

    monkeypatch.chdir(tmp_path)
    _projet_minimal(tmp_path, "a_valide", statut="valide")
    _projet_minimal(tmp_path, "b_en_attente", statut="a_valider")
    _projet_minimal(tmp_path, "c_sans_statut")
    _projet_minimal(tmp_path, "d_deja_rendu", statut="valide", final=True)
    assert batch_produce.detecter_projets_a_traiter() == ["projets/a_valide"]


def test_batch_refuse_un_projet_explicite_non_valide(tmp_path, monkeypatch):
    import batch_produce

    projet = _projet_minimal(tmp_path, "p", statut="a_valider")
    appels = []
    monkeypatch.setattr(batch_produce, "produire", lambda p: appels.append(p))
    assert batch_produce.main([str(projet)]) == 0
    assert appels == []


def test_style_par_defaut_coherent(tmp_path):
    import batch_produce

    assert batch_produce.lire_visual_style(tmp_path) == "low_poly_3d"


def _usine(monkeypatch, reponses, produits):
    usine = _charger_script("0_usine.py")
    entrees = iter(reponses)
    monkeypatch.setattr("builtins.input", lambda _q: next(entrees))
    monkeypatch.setattr(usine, "produire", lambda p: produits.append(p) or True)
    return usine


def test_usine_valider_un_dossier_existant(tmp_path, monkeypatch):
    from usine.projet import statut_validation

    projet = _projet_minimal(tmp_path, "p", statut="a_valider")
    produits = []
    usine = _usine(monkeypatch, ["o"], produits)
    assert usine.main(["--valider", str(projet)]) == 0
    assert statut_validation(projet) == "valide" and produits == [str(projet)]


def test_usine_regenerer_puis_valider(tmp_path, monkeypatch):
    from usine.projet import statut_validation

    premier = _projet_minimal(tmp_path, "premier", statut="a_valider")
    second = _projet_minimal(tmp_path, "second", statut="a_valider")
    produits = []
    usine = _usine(monkeypatch, ["r", "v"], produits)
    dossiers = iter([str(premier), str(second)])
    monkeypatch.setattr(usine, "generer_dossier", lambda sujet=None: next(dossiers))
    assert usine.traiter_un_dossier() is True
    assert statut_validation(premier) == "rejete"
    assert statut_validation(second) == "valide" and produits == [str(second)]


def test_usine_abandon_ne_produit_rien(tmp_path, monkeypatch):
    from usine.projet import statut_validation

    projet = _projet_minimal(tmp_path, "p", statut="a_valider")
    produits = []
    usine = _usine(monkeypatch, ["a"], produits)
    monkeypatch.setattr(usine, "generer_dossier", lambda sujet=None: str(projet))
    assert usine.traiter_un_dossier() is False
    assert statut_validation(projet) == "rejete" and produits == []


def test_validate_project_signale_un_dossier_non_valide(tmp_path, capsys):
    from validate_project import validate_project

    projet = _projet_minimal(tmp_path, "p", statut="a_valider")
    validate_project(projet)
    assert "non validé" in capsys.readouterr().out
