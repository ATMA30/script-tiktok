"""Graphe ffmpeg du mixage final : toujours valide, quelle que soit la combinaison.

Régression : sans musique, la sortie `voice_sc` restait non branchée, ffmpeg
rejetait le graphe et la vidéo partait sans narration (voix à volume 0 dans le HTML).
"""

import re
import shutil
import subprocess

import pytest

from usine.render.audio import construire_filtre_mix

COMBINAISONS = [
    (delais, sfx, musique)
    for delais in ([], [0, 2600])
    for sfx in (False, True)
    for musique in (None, "aloop=loop=-1:size=2e9,volume=0.280")
]


def _etiquettes(filtre):
    produites, consommees = [], []
    for segment in filter(None, filtre.split(";")):
        entrees = re.match(r"^((?:\[[^\]]+\])*)", segment).group(1)
        sorties = re.search(r"((?:\[[^\]]+\])*)$", segment).group(1)
        consommees += [e for e in re.findall(r"\[([^\]]+)\]", entrees) if ":" not in e]
        produites += re.findall(r"\[([^\]]+)\]", sorties)
    return produites, consommees


@pytest.mark.parametrize("delais,sfx,musique", COMBINAISONS)
def test_chaque_etiquette_consommee_une_fois(delais, sfx, musique):
    produites, consommees = _etiquettes(construire_filtre_mix(delais, sfx, musique))
    assert produites.count("audio_master") == 1
    for etiquette in produites:
        if etiquette != "audio_master":
            assert consommees.count(etiquette) == 1, etiquette
    assert set(consommees) <= set(produites)


@pytest.mark.parametrize("delais,sfx,musique", COMBINAISONS)
def test_indices_d_entree_contigus(delais, sfx, musique):
    filtre = construire_filtre_mix(delais, sfx, musique)
    indices = sorted({int(i) for i in re.findall(r"\[(\d+):a\]", filtre)})
    attendu = len(delais) + int(sfx) + int(musique is not None)
    assert indices == list(range(1, attendu + 1))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg absent")
@pytest.mark.parametrize("musique", [None, "aloop=loop=-1:size=2e9,volume=0.280"])
def test_ffmpeg_accepte_le_graphe(musique, tmp_path):
    # Vrai ffmpeg : vidéo noire + 2 voix + SFX (+ musique), sources synthétiques.
    entrees = ["-f", "lavfi", "-i", "color=c=black:s=64x64:d=1"]
    for freq in (220, 330, 440) + ((550,) if musique else ()):
        entrees += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration=1"]
    filtre = construire_filtre_mix([0, 300], True, musique)
    cmd = ["ffmpeg", "-y", "-v", "error", *entrees, "-filter_complex", filtre]
    cmd += [
        "-map",
        "0:v",
        "-map",
        "[audio_master]",
        "-shortest",
        str(tmp_path / "o.mp4"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_mixage_rate_ne_laisse_aucun_final_mp4(tmp_path, monkeypatch):
    # Un final.mp4 partiel serait pris pour « terminé » par batch_produce.
    from types import SimpleNamespace

    from usine.render import audio

    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "scene_1.wav").write_bytes(b"RIFF")
    rendu = tmp_path / "rendu.mp4"
    rendu.write_bytes(b"video")
    final = tmp_path / "final.mp4"

    def _ffmpeg_ko(cmd, **kwargs):
        sortie = cmd[-1]
        if sortie.endswith(".mixage.mp4"):
            open(sortie, "wb").write(b"partiel")  # ffmpeg écrit puis échoue
        return SimpleNamespace(returncode=1, stderr="échec simulé")

    monkeypatch.setattr(audio.subprocess, "run", _ffmpeg_ko)
    with pytest.raises(RuntimeError, match="Mixage audio"):
        audio.mix_audio_post_render(tmp_path, rendu, final, [{"voice_start": 0}], 1.0)
    assert not final.exists()
    assert not list(tmp_path.glob("*.mixage.mp4"))
