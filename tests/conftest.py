"""Environnement de test isolé : sans .env, sans appel réseau et sans ffmpeg.

Le .env local ne doit pas influencer les tests : load_dotenv est neutralisé avant
tout import d'`usine`, et les réglages coûteux (Whisper, musique générée) sont coupés.
"""

import json
import math
import os
import stat
import struct
import sys
import wave

import dotenv
import pytest

dotenv.load_dotenv = lambda *args, **kwargs: False
# Aucun réglage ni clé du shell ne doit fuiter dans les tests.
for _key in [k for k in os.environ if k.startswith("USE_") or k.endswith("_API_KEY")]:
    del os.environ[_key]
os.environ.pop("BRAND_LOGO_PATH", None)
os.environ.update(
    {
        "GEMINI_API_KEY": "",
        "USE_WHISPER_SYNC": "0",
        "USE_AMBIENT_MUSIC": "0",
        # Sinon render_projet régénère les SFX manquants dans le vrai assets/sfx/.
        "USE_SYNTH_SFX": "0",
    }
)

FFPROBE_SHIM = """#!/usr/bin/env python3
import sys, wave
with wave.open(sys.argv[-1]) as w:
    print(f"{w.getnframes() / w.getframerate():.6f}")
"""

SCENES = [
    "En 1977, tout a commencé dans cette maison.",
    "Je suis parti de paris sans me retourner.",
    "Elle a disparu dans la nuit, sans laisser de trace.",
    "Il y avait 47 personnes et personne n'a rien vu.",
    "Pourquoi personne ne m'a jamais cru ?",
]


@pytest.fixture(scope="session", autouse=True)
def fake_ffprobe(tmp_path_factory):
    """Remplace ffprobe par un script qui lit la durée des WAV (seul usage en prepare-only)."""
    bin_dir = tmp_path_factory.mktemp("bin")
    shim = bin_dir / "ffprobe"
    shim.write_text(FFPROBE_SHIM)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    mp = pytest.MonkeyPatch()
    mp.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    yield shim
    mp.undo()


def _write_wav(path, seconds=1.6, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(800 * math.sin(2 * math.pi * 220 * n / rate)))
                for n in range(int(rate * seconds))
            )
        )


@pytest.fixture
def projet_factice(tmp_path):
    """Projet complet minimal : script.json, audio par scène, images pour 2 scènes sur 3."""
    from PIL import Image

    projet = tmp_path / "20260101_000000_Projet_Test"
    (projet / "audio").mkdir(parents=True)
    scenes = []
    for i, texte in enumerate(SCENES, 1):
        scenes.append({"audio_tts": texte, "subtitle": texte, "veo_prompt": "x"})
        _write_wav(projet / "audio" / f"scene_{i}.wav")
        if i % 3:
            media = projet / "real_media" / f"scene_{i}"
            media.mkdir(parents=True)
            Image.new("RGB", (64, 112), (i * 40, 80, 120)).save(media / "plan_1.jpg")
    script = {
        "titre": "Projet Test",
        "visual_bible": {"Marc Durand": "Marc Durand, security guard"},
        "scenes": scenes,
    }
    (projet / "script.json").write_text(
        json.dumps(script, ensure_ascii=False), encoding="utf-8"
    )
    (projet / "visual_plan.json").write_text(
        json.dumps({"scene_1": [{"source_type": "generated_imagen"}]}), encoding="utf-8"
    )
    return projet


@pytest.fixture
def set_render_flag(monkeypatch):
    """Force un réglage USE_* dans tous les modules usine.render qui l'ont importé."""

    def _set(name, value):
        for module in list(sys.modules.values()):
            if getattr(module, "__name__", "").startswith("usine.render") and hasattr(
                module, name
            ):
                monkeypatch.setattr(module, name, value)

    return _set
