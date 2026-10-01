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
