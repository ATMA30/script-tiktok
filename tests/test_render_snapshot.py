"""Snapshot du HTML HyperFrames : tout changement du rendu doit être volontaire.

Après une modification voulue du rendu, régénérer les références avec :
    UPDATE_GOLDEN=1 python3 -m pytest tests/test_render_snapshot.py
"""

import os
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"

CONFIGS = {
    "defaut": {},
    "complet": {
        "USE_SEMANTIC_OVERLAYS": True,
        "USE_LOTTIE_OVERLAYS": True,
        "USE_HOOK_INTRO": True,
        "USE_OUTRO_CTA": True,
        "USE_PERSISTENT_CASE_TAG": True,
        "DISABLE_SCENE_TRANSITIONS": False,
        "SKIP_TRUTH_CARD": False,
    },
}


@pytest.mark.parametrize("nom", CONFIGS)
def test_html_identique_au_snapshot(
    nom, projet_factice, tmp_path, monkeypatch, set_render_flag
):
    from usine.render import pipeline

    for flag, value in CONFIGS[nom].items():
        set_render_flag(flag, value)
    monkeypatch.setattr(pipeline, "RENDER_ROOT", tmp_path / "render")

    render_dir = pipeline.render_projet(projet_factice, prepare_only=True)
    html = (render_dir / "index.html").read_text(encoding="utf-8")

    golden = GOLDEN_DIR / f"render_{nom}.html"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden.parent.mkdir(exist_ok=True)
        golden.write_text(html, encoding="utf-8")
    assert golden.exists(), (
        f"Référence absente : lancer avec UPDATE_GOLDEN=1 ({golden})"
    )
    assert html == golden.read_text(encoding="utf-8"), (
        "Le HTML généré a changé. Si c'est voulu : UPDATE_GOLDEN=1 python3 -m pytest"
    )


def test_projet_hyperframes_complet(projet_factice, tmp_path, monkeypatch):
    from usine.render import pipeline

    monkeypatch.setattr(pipeline, "RENDER_ROOT", tmp_path / "render")
    render_dir = pipeline.render_projet(projet_factice, prepare_only=True)

    assert (render_dir / "index.html").exists()
    assert (render_dir / "package.json").exists()
    voix = sorted(p.name for p in (render_dir / "assets").glob("s*_vo.wav"))
    assert voix == [f"s{i}_vo.wav" for i in range(1, 6)]


def test_logo_introuvable_repli_sur_le_logo_par_defaut(
    projet_factice, tmp_path, monkeypatch
):
    # Ex. un ancien BRAND_LOGO_PATH dans le .env, d'avant le rangement d'assets/brand/.
    from usine.render import pipeline

    monkeypatch.setattr(pipeline, "RENDER_ROOT", tmp_path / "render")
    monkeypatch.setattr(pipeline, "BRAND_LOGO_PATH", str(tmp_path / "absent.png"))
    render_dir = pipeline.render_projet(projet_factice, prepare_only=True)
    copie = render_dir / "assets" / "yurei_logo.png"
    assert copie.read_bytes() == pipeline.BRAND_LOGO_DEFAUT.read_bytes()


def test_logo_chemin_dossier_repli_sur_le_logo_par_defaut(
    projet_factice, tmp_path, monkeypatch
):
    # Un BRAND_LOGO_PATH qui désigne un dossier ne doit pas faire planter le rendu.
    from usine.render import pipeline

    monkeypatch.setattr(pipeline, "RENDER_ROOT", tmp_path / "render")
    monkeypatch.setattr(pipeline, "BRAND_LOGO_PATH", str(tmp_path))
    render_dir = pipeline.render_projet(projet_factice, prepare_only=True)
    copie = render_dir / "assets" / "yurei_logo.png"
    assert copie.read_bytes() == pipeline.BRAND_LOGO_DEFAUT.read_bytes()


def test_brand_logo_path_vide_vaut_le_defaut(monkeypatch):
    import importlib

    from usine.render import config

    monkeypatch.setenv("BRAND_LOGO_PATH", "")
    try:
        assert importlib.reload(config).BRAND_LOGO_PATH == str(config.BRAND_LOGO_DEFAUT)
    finally:
        monkeypatch.delenv("BRAND_LOGO_PATH")
        importlib.reload(config)
