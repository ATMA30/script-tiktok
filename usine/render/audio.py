"""Audio final : musique d'ambiance, ruptures dramatiques, loudness et mixage post-rendu."""

import re
import subprocess
from pathlib import Path
from usine.render.config import (
    DRAMATIC_EVENT_SCENES,
    POST_MIX_MUSIC_VOLUME,
    ROOT,
    TARGET_LUFS,
    USE_AMBIENT_MUSIC,
    USE_DRAMATIC_SILENCE,
)
from usine.render.media import ffprobe_duration
from usine.render.text import _normalize_word


def _audio_duration_safe(path):
    """ffprobe safe : retourne 0 si fichier absent ou erreur."""
    try:
        return ffprobe_duration(path)
    except Exception:
        return 0.0


def ensure_ambient_music(projet_dir, target_duration=150):
    """Cherche musiques/[projet]_ambient.{mp3,wav} et la (re)génère si :
       - absente
       - plus courte que target_duration (vidéo plus longue que la musique)
    Retourne le Path du fichier audio ou None.
    """
    if not USE_AMBIENT_MUSIC:
        return None
    projet_name = projet_dir.name
    music_dir = ROOT / "musiques"
    music_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        music_dir / f"{projet_name}_ambient.mp3",
        music_dir / f"{projet_name}_ambient.wav",
    ]
    # Si une candidate existe ET couvre la durée cible avec ≥0.5s de marge, on la garde.
    for c in candidates:
        if c.exists() and c.stat().st_size > 1024:
            existing_dur = _audio_duration_safe(c)
            if existing_dur >= target_duration + 0.5:
                return c
            else:
                print(
                    f"   ♻️  Musique existante trop courte ({existing_dur:.1f}s < {target_duration:.1f}s) — régénération."
                )
                break

    # Génération à la volée via 2.3_generate_music.py
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "music_gen", ROOT / "2.3_generate_music.py"
        )
        if spec is None or spec.loader is None:
            return None
        music_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(music_mod)
    except Exception as e:
        print(f"   ⚠️  Impossible de charger 2.3_generate_music.py : {e}")
        return None

    # On génère systématiquement avec une marge de 10s sur la durée vidéo
    gen_duree = int(target_duration + 10)
    wav_path = music_dir / f"{projet_name}_ambient.wav"
    mp3_path = music_dir / f"{projet_name}_ambient.mp3"
    print(
        f"   🎵 Génération partition de tension ({gen_duree}s pour vidéo de {target_duration:.1f}s)..."
    )
    if not music_mod.generer_tension_score(str(wav_path), duree=gen_duree):
        return None
    if hasattr(music_mod, "wav_to_mp3") and music_mod.wav_to_mp3(
        str(wav_path), str(mp3_path)
    ):
        return mp3_path
    return wav_path if wav_path.exists() else None


def find_dramatic_audio_events(scenes_data):
    """Repère les révélations 'vide' et 'disparu' via l'alignement Whisper."""
    targets_by_scene = {}
    for raw_event in DRAMATIC_EVENT_SCENES.split(","):
        scene_number, separator, target = raw_event.strip().partition(":")
        if not separator:
            continue
        try:
            targets_by_scene[int(scene_number) - 1] = _normalize_word(target)
        except ValueError:
            print(f"   ⚠️ Rupture dramatique invalide ignorée : {raw_event}")

    events = []
    for scene in scenes_data:
        target = targets_by_scene.get(scene.get("scene_idx"))
        if not target:
            continue
        voice_start = float(scene.get("voice_start", 0.0))
        for word in scene.get("word_timings") or []:
            normalized = _normalize_word(word.get("text", ""))
            if normalized == target:
                events.append(
                    {
                        "word": normalized,
                        "time": voice_start + float(word.get("start", 0.0)),
                    }
                )
    return events


def measure_loudness(video_path):
    """Retourne (LUFS intégrés, true peak) via le résumé EBU R128."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video_path),
        "-af",
        "ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    summary = result.stderr.rsplit("Summary:", 1)[-1]
    integrated = re.search(r"Integrated loudness:\s+I:\s*(-?\d+(?:\.\d+)?)", summary)
    true_peak = re.search(r"True peak:\s+Peak:\s*(-?\d+(?:\.\d+)?)", summary)
    if not integrated or not true_peak:
        return None
    return float(integrated.group(1)), float(true_peak.group(1))


def normalize_loudness_master(video_path):
    """Applique une finition broadcast stable, puis limite les pics avant AAC."""
    video_path = Path(video_path)
    mastering_filter = (
        "acompressor=threshold=-10dB:ratio=3:attack=5:release=80:makeup=2dB,"
        "alimiter=limit=0.794328:level=false,"
        f"loudnorm=I={TARGET_LUFS:.1f}:TP=-2.0:LRA=11,"
        "alimiter=limit=0.794328:level=false"
    )
    normalized_path = video_path.with_name(f"{video_path.stem}.normalized.mp4")
    normalize_cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(video_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "copy",
        "-af",
        mastering_filter,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(normalized_path),
    ]
    normalized = subprocess.run(normalize_cmd, capture_output=True, text=True)
    if normalized.returncode != 0 or not normalized_path.exists():
        print(f"   ⚠️ Seconde passe loudness échouée : {normalized.stderr[-500:]}")
        normalized_path.unlink(missing_ok=True)
        return

    normalized_path.replace(video_path)
    measured = measure_loudness(video_path)
    if measured:
        integrated, true_peak = measured
        correction_db = TARGET_LUFS - integrated
        if abs(correction_db) > 0.2:
            corrected_path = video_path.with_name(f"{video_path.stem}.corrected.mp4")
            correction_filter = (
                f"volume={correction_db:.2f}dB,alimiter=limit=0.841395:level=false"
            )
            correction_cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-i",
                str(video_path),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c:v",
                "copy",
                "-af",
                correction_filter,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(corrected_path),
            ]
            corrected = subprocess.run(correction_cmd, capture_output=True, text=True)
            if corrected.returncode == 0 and corrected_path.exists():
                corrected_path.replace(video_path)
                measured = measure_loudness(video_path) or measured
            else:
                corrected_path.unlink(missing_ok=True)

        integrated, true_peak = measured
        print(
            f"   ✅ Master final : {integrated:.1f} LUFS, "
            f"true peak {true_peak:.1f} dBFS"
        )
    else:
        print(
            f"   ✅ Master finalisé vers {TARGET_LUFS:.1f} LUFS avec true peak protégé"
        )


def _trouver_musique(projet_dir):
    """Musique d'ambiance du projet : dans le projet, puis dans ROOT/musiques."""
    nom = Path(projet_dir).name
    for dossier in (Path(projet_dir), ROOT / "musiques"):
        for ext in (".mp3", ".wav"):
            candidat = dossier / f"{nom}_ambient{ext}"
            if candidat.exists():
                return candidat
    return None


def construire_filtre_mix(delais_voix_ms, avec_sfx, chaine_musique):
    """Graphe -filter_complex du mixage final.

    Entrées : 0 = vidéo, puis une entrée par voix, puis le SFX composite si
    `avec_sfx`, puis la musique si `chaine_musique` (filtres à lui appliquer).
    Chaque étiquette produite est consommée une seule fois : une sortie non
    branchée fait rejeter tout le graphe par ffmpeg.
    """
    parts = []
    idx = 1
    voix = []
    for i, delai in enumerate(delais_voix_ms):
        parts.append(f"[{idx}:a]adelay={delai}|{delai}[v{i}];")
        voix.append(f"[v{i}]")
        idx += 1
    if voix:
        parts.append(f"{''.join(voix)}amix=inputs={len(voix)}:normalize=0[voice_full];")
    else:
        parts.append("aevalsrc=0:d=10[voice_full];")

    if avec_sfx:
        parts.append(f"[{idx}:a]volume=1.0[sfx_full];")
        idx += 1
    else:
        parts.append("aevalsrc=0:d=10[sfx_full];")

    if chaine_musique is not None:
        # La voix est dédoublée : une copie pilote le ducking, l'autre part au mix.
        parts.append("[voice_full]asplit=2[voice_sc][voice_mix];")
        parts.append(f"[{idx}:a]{chaine_musique}[music_raw];")
        parts.append(
            "[music_raw][voice_sc]sidechaincompress="
            "threshold=0.15:ratio=4.5:attack=15:release=350[music_ducked];"
        )
        a_mixer, n = "[voice_mix][sfx_full][music_ducked]", 3
    else:
        a_mixer, n = "[voice_full][sfx_full]", 2
    parts.append(
        f"{a_mixer}amix=inputs={n}:normalize=0,"
        f"loudnorm=I={TARGET_LUFS:.1f}:TP=-1.0:LRA=11[audio_master]"
    )
    return "".join(parts)


def mix_audio_post_render(
    projet_dir,
    rendered_mp4_path,
    final_mp4_path,
    scenes_data,
    total_duration,
    dramatic_events=None,
    musique_path=None,
):
    """
    Mélange de manière professionnelle la voix, les SFX et la musique d'ambiance avec FFmpeg.
    Applique une compression sidechain pour 'ducker' la musique sous la voix.

    NOTE : HyperFrames embarque également l'audio dans le HTML (via <audio> tags),
    mais les pistes voix sont forcées à volume=0.0 dans le HTML pour éviter le double.
    FFmpeg est l'unique source audio du final.mp4.
    """
    print("\n⚡️  Strip audio du rendu HyperFrames...")

    # Étape 0 : extraire uniquement la vidéo du MP4 rendu (supprimer l'audio HyperFrames)
    video_only_path = Path(rendered_mp4_path).with_suffix(".video_only.mp4")
    strip_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(rendered_mp4_path),
        "-an",  # no audio
        "-c:v",
        "copy",
        str(video_only_path),
    ]
    r_strip = subprocess.run(strip_cmd, capture_output=True, text=True)
    if r_strip.returncode != 0 or not video_only_path.exists():
        print(
            f"   ⚠️ Strip audio échec, on utilise le MP4 original : {r_strip.stderr[:200]}"
        )
        video_only_path = Path(rendered_mp4_path)  # fallback
    else:
        print("   ✅ Audio HyperFrames retiré (vidéo seule prête pour mix FFmpeg)")

    print("\n🎚️  Mixage audio post-rendu avec compression sidechain...")

    inputs = []

    # 1. Voix et leurs timings
    delais_voix_ms = []
    for i, scene in enumerate(scenes_data):
        audio_src = Path(projet_dir) / "audio" / f"scene_{i + 1}.wav"
        if audio_src.exists():
            inputs.extend(["-i", str(audio_src)])
            delais_voix_ms.append(int(round(scene["voice_start"] * 1000)))

    # 2. SFX composite unique
    sfx_composite = Path(projet_dir) / "audio" / "sfx_composite.wav"
    avec_sfx = sfx_composite.exists()
    if avec_sfx:
        inputs.extend(["-i", str(sfx_composite)])

    # 3. Musique d'ambiance (celle générée pour ce rendu, sinon recherche)
    if musique_path is None:
        musique_path = _trouver_musique(projet_dir)
    chaine_musique = None
    if musique_path:
        inputs.extend(["-i", str(musique_path)])
        chaine_musique = f"aloop=loop=-1:size=2e9,volume={POST_MIX_MUSIC_VOLUME:.3f}"
        if USE_DRAMATIC_SILENCE:
            for event in dramatic_events or []:
                t = float(event["time"])
                start = max(0.0, t - 0.85)
                end = t + 0.55
                chaine_musique += f",volume=0:enable='between(t,{start:.3f},{end:.3f})'"
        print(
            f"   🎼 Musique post-mix : volume={POST_MIX_MUSIC_VOLUME:.2f}, "
            "ducking voix actif"
        )
    else:
        print("   ℹ️  Pas de musique d'ambiance : voix + SFX seulement")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_only_path),  # vidéo sans audio
    ]
    cmd.extend(inputs)
    cmd.extend(
        [
            "-filter_complex",
            construire_filtre_mix(delais_voix_ms, avec_sfx, chaine_musique),
            "-map",
            "0:v",
            "-map",
            "[audio_master]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(final_mp4_path),
        ]
    )

    print(f"   🏃 Commande FFmpeg : {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # Pas de repli sur le rendu HyperFrames : sa piste voix est à volume 0,
        # la vidéo sortirait sans narration.
        raise RuntimeError(f"Mixage audio FFmpeg échoué :\n{r.stderr[-1500:]}")
    print("   ✅ Audio mixé avec succès (sidechain compress appliqué)")
    normalize_loudness_master(final_mp4_path)
