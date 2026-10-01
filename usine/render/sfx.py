"""Effets sonores : synthèse des SFX manquants, pistes HTML et composite audio."""

import shutil
from pathlib import Path
from usine.render.config import ROOT, USE_SYNTH_SFX


def discover_sfx(sfx_root):
    """Scan ROOT/assets/sfx/ pour les fichiers SFX disponibles.
    Convention : whoosh.mp3, glitch.mp3, drone.mp3, classified.mp3, etc.
    Retourne un dict {nom_logique: chemin}.
    """
    if not sfx_root.is_dir():
        return {}
    found = {}
    for f in sfx_root.glob("*.mp3"):
        found[f.stem.lower()] = f
    for f in sfx_root.glob("*.wav"):
        if f.stem.lower() not in found:
            found[f.stem.lower()] = f
    return found


def _write_wav_mono(path, samples, sr=44100):
    """Écrit un fichier WAV mono 16-bit depuis un array float [-1, 1]."""
    import wave
    import numpy as np

    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)


def _synth_whoosh(duration=0.6, sr=44100):
    """Whoosh blanc filtré : sweep low-pass 300Hz → 5kHz → 300Hz."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    noise = np.random.randn(n).astype(np.float32) * 0.5
    # Filtrage manuel léger via moyenne glissante variable (cheap "lpf")
    cutoff = 0.05 + 0.45 * np.sin(np.pi * t / duration)
    out = np.zeros(n, dtype=np.float32)
    acc = 0.0
    for i in range(n):
        alpha = float(cutoff[i])
        acc = (1 - alpha) * acc + alpha * noise[i]
        out[i] = acc
    env = np.sin(np.pi * t / duration) ** 1.5
    return out * env * 0.75


def _synth_sub_drop(duration=1.2, sr=44100):
    """Sub-drop : 90Hz → 35Hz avec amplitude décroissante."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    freq = 90 * (35 / 90) ** (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    sub = np.sin(phase).astype(np.float32)
    # Petit harmonique pour épaisseur
    sub += 0.35 * np.sin(2 * phase)
    env = np.exp(-2.2 * t / duration)
    return sub * env * 0.9


def _synth_riser(duration=3.5, sr=44100):
    """Riser cinématique pro : 5 couches stratifiées.
      C1 sub-sweep 40→90Hz (mass)
      C2 mid tonal sweep 200→1200Hz (énergie)
      C3 white noise filtré ascendant (air)
      C4 ride cymbal simulée (shimmer)
      C5 woosh percussif final (impact d'ouverture)
    Compression douce par tanh, fade-in 0.1s, fade-out géré par le caller."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    progress = t / duration  # 0 → 1

    # C1 sub sweep (40 → 90 Hz)
    sub_freq = 40 * (90 / 40) ** progress
    sub_phase = 2 * np.pi * np.cumsum(sub_freq) / sr
    sub = np.sin(sub_phase).astype(np.float32) * 0.50
    sub_env = progress**1.6
    sub *= sub_env

    # C2 tonal mid sweep (200 → 1200 Hz)
    mid_freq = 200 * (1200 / 200) ** progress
    mid_phase = 2 * np.pi * np.cumsum(mid_freq) / sr
    mid = np.sin(mid_phase).astype(np.float32) * 0.32
    # Légère détune pour épaisseur
    mid += 0.18 * np.sin(2 * np.pi * np.cumsum(mid_freq * 1.005) / sr)
    mid_env = progress**1.8
    mid *= mid_env

    # C3 white noise filtré (passe-haut progressif)
    raw_noise = np.random.randn(n).astype(np.float32)
    # Filtre simple : différence + ré-accumulation pour passe-haut
    hp_noise = raw_noise - np.concatenate(([0.0], raw_noise[:-1])) * 0.92
    noise_env = progress**2.2
    noise = hp_noise * noise_env * 0.30

    # C4 ride/cymbal-like : bruit modulé par enveloppes courtes répétitives
    cymb = np.zeros(n, dtype=np.float32)
    pulse_period = int(sr * 0.18)  # un "ride" toutes les 180ms
    for i in range(0, n, pulse_period):
        decay = np.exp(-np.arange(min(pulse_period, n - i)) / (sr * 0.08))
        local_noise = np.random.randn(len(decay)).astype(np.float32)
        local_noise = local_noise - np.concatenate(([0.0], local_noise[:-1])) * 0.95
        cymb[i : i + len(decay)] += local_noise * decay * 0.18
    cymb *= progress**1.4

    # C5 woosh "tail" très final (dernière 0.4s : impact d'ouverture)
    woosh = np.zeros(n, dtype=np.float32)
    woosh_start = max(0, n - int(0.4 * sr))
    woosh_len = n - woosh_start
    if woosh_len > 0:
        wt = np.linspace(0, 0.4, woosh_len, endpoint=False)
        ws = np.random.randn(woosh_len).astype(np.float32)
        ws = ws - np.concatenate(([0.0], ws[:-1])) * 0.85
        woosh[woosh_start:] = ws * np.sin(np.pi * wt / 0.4) * 0.55

    # Mix
    signal = sub + mid + noise + cymb + woosh
    # Soft-clip pour caractère cinéma
    signal = np.tanh(signal * 1.05) * 0.88
    # Fade-in 0.1s
    fade_in = min(int(0.1 * sr), n)
    if fade_in > 0:
        signal[:fade_in] *= np.linspace(0, 1, fade_in)
    return signal


def _synth_impact(duration=1.8, sr=44100):
    """Impact cinématique pro : sub-drop 50→25Hz + click HF + body tonal + reverb tail.
    Caractère bande-son blockbuster, durée 1.8s avec queue percussive."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)

    # C1 sub-drop : 50Hz → 25Hz, decay 1.5s (vraie présence sub)
    sub_freq = 50 * (25 / 50) ** np.minimum(1.0, t / 1.5)
    sub_phase = 2 * np.pi * np.cumsum(sub_freq) / sr
    sub = np.sin(sub_phase).astype(np.float32) * 0.85
    sub *= np.exp(-1.6 * t / duration * 3)  # decay rapide initial puis sustain

    # C2 body tonal (100Hz + harmonique 200Hz) : remplit le mid-bass
    body = 0.45 * np.sin(2 * np.pi * 100.0 * t) * np.exp(-3.2 * t)
    body += 0.22 * np.sin(2 * np.pi * 200.0 * t) * np.exp(-5.5 * t)

    # C3 click HF transitoire : déclencheur d'attaque
    click_env = np.exp(-45 * t) * 0.55
    raw = np.random.randn(n).astype(np.float32)
    # Passe-haut simple pour piquer le HF
    click = raw - np.concatenate(([0.0], raw[:-1])) * 0.95
    click *= click_env

    # C4 reverb tail simulé : convolution avec une IR exponentielle
    ir_len = int(sr * 1.2)
    ir = np.random.randn(ir_len).astype(np.float32)
    ir *= np.exp(-np.linspace(0, 8, ir_len))  # decay rapide → réverb courte
    # Convolve direct sound avec IR (mais signal est court, on convolve "click" seulement)
    reverb = np.convolve(click * 0.4, ir, mode="same") * 0.12

    # Mix
    signal = sub + body + click + reverb
    # Soft-clip
    signal = np.tanh(signal * 0.95) * 0.90
    # Fade-out final 0.2s pour finir propre
    fade_out = min(int(0.2 * sr), n)
    if fade_out > 0:
        signal[-fade_out:] *= np.linspace(1, 0, fade_out)
    return signal


def _synth_glitch(duration=0.5, sr=44100):
    """Génère un effet de glitch numérique (bruits et impulsions carrées rapides)."""
    import numpy as np
    import random

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    signal = np.zeros(n, dtype=np.float32)
    for _ in range(4):
        start = random.randint(0, int(n * 0.7))
        length = random.randint(int(sr * 0.02), int(sr * 0.08))
        end = min(n, start + length)
        if end <= start:
            continue
        sub_t = t[start:end] - t[start]
        freq = random.choice([800, 1500, 3000, 5000])
        burst = np.sign(np.sin(2 * np.pi * freq * sub_t)) * 0.35
        burst += np.random.randn(len(sub_t)).astype(np.float32) * 0.25
        signal[start:end] = burst
    fade = min(int(0.01 * sr), n)
    if fade > 0:
        signal[:fade] *= np.linspace(0, 1, fade)
        signal[-fade:] *= np.linspace(1, 0, fade)
    return np.tanh(signal) * 0.75


def _synth_sub_bass_boom(duration=1.5, sr=44100):
    """Génère un boom sub-bass profond cinématique descendant (Bb0/A0)."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    freq = 60.0 * (20.0 / 60.0) ** (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    sub = np.sin(phase).astype(np.float32)
    sub += 0.25 * np.sin(2 * phase)
    env = np.exp(-3.0 * t / duration)
    signal = sub * env
    # fade out final
    fade_out = min(int(0.15 * sr), n)
    if fade_out > 0:
        signal[-fade_out:] *= np.linspace(1, 0, fade_out)
    return np.tanh(signal) * 0.85


def ensure_synth_sfx(sfx_root):
    """Génère whoosh.wav, sub-drop.wav, riser.wav, impact.wav, glitch.wav, sub_bass_boom.wav synthétiques si manquants."""
    if not USE_SYNTH_SFX:
        return False
    try:
        import numpy as np  # noqa: F401
    except ImportError:
        print("   ⚠️  numpy indisponible : SFX synthétiques skip.")
        return False
    sfx_root.mkdir(parents=True, exist_ok=True)
    existing = {f.stem.lower() for f in sfx_root.glob("*.mp3")}
    existing |= {f.stem.lower() for f in sfx_root.glob("*.wav")}
    generators = {
        "whoosh": _synth_whoosh,
        "sub-drop": _synth_sub_drop,
        "riser": _synth_riser,
        "impact": _synth_impact,
        "glitch": _synth_glitch,
        "sub_bass_boom": _synth_sub_boom_sfx,  # Use helper or define a local mapping
    }
    # map sub_bass_boom generator
    generators["sub_bass_boom"] = _synth_sub_bass_boom

    created = []
    for name, fn in generators.items():
        if name in existing:
            continue
        path = sfx_root / f"{name}.wav"
        _write_wav_mono(path, fn())
        created.append(name)
    if created:
        print(f"   🛠️  SFX synthétiques générés : {', '.join(created)}")
    return True


# Helper dummy name to satisfy references if any
def _synth_sub_boom_sfx():
    return _synth_sub_bass_boom()


def build_sfx_blocks(
    scenes_meta,
    sfx_available,
    total_duration,
    assets_dir,
    woosh_ts=(),
    glitch_ts=(),
    boom_ts=(),
):
    """Ajoute audio elements timés pour HyperFrames browser preview."""
    html_parts = []
    js_parts = []
    sfx_track = 2000

    def _stage(name, default_volume):
        """Helper : copie le fichier dans assets/ et retourne (src_name, volume)."""
        src = sfx_available.get(name)
        if not src:
            return None, default_volume
        dst = assets_dir / src.name
        if not dst.exists():
            shutil.copy(src, dst)
        return src.name, default_volume

    # 1. Drone ambient (continu, low vol) si présent
    drone_name, drone_vol = _stage("drone", 0.18)
    if drone_name:
        html_parts.append(
            f'<audio id="sfx_drone" class="clip" src="assets/{drone_name}" '
            f'data-start="0" data-duration="{total_duration:.3f}" '
            f'data-track-index="{sfx_track}" data-volume="{drone_vol}"></audio>'
        )
        sfx_track += 1

    # 2. Impact sur hook scène 1 (punch d'ouverture)
    impact_name, impact_vol = _stage("impact", 0.7)
    if impact_name and scenes_meta:
        first_start = scenes_meta[0]["start"]
        html_parts.append(
            f'<audio id="sfx_impact_hook" class="clip" src="assets/{impact_name}" '
            f'data-start="{first_start:.3f}" data-duration="1.8" '
            f'data-track-index="{sfx_track}" data-volume="{impact_vol}"></audio>'
        )
        sfx_track += 1

    # 3. Whooshes sur apparition des mots rouges
    whoosh_name, whoosh_vol = _stage("whoosh", 0.50)
    if whoosh_name:
        for idx, t in enumerate(woosh_ts):
            if t + 0.6 > total_duration:
                continue
            html_parts.append(
                f'<audio id="sfx_wh{idx}" class="clip" src="assets/{whoosh_name}" '
                f'data-start="{t:.3f}" data-duration="1.2" '
                f'data-track-index="{sfx_track + idx}" data-volume="{whoosh_vol}"></audio>'
            )
        sfx_track += len(woosh_ts)

    # 4. Glitches sur transitions
    glitch_name, glitch_vol = _stage("glitch", 0.45)
    if glitch_name:
        for idx, t in enumerate(glitch_ts):
            if t + 0.5 > total_duration:
                continue
            html_parts.append(
                f'<audio id="sfx_glitch{idx}" class="clip" src="assets/{glitch_name}" '
                f'data-start="{t:.3f}" data-duration="1.0" '
                f'data-track-index="{sfx_track + idx}" data-volume="{glitch_vol}"></audio>'
            )
        sfx_track += len(glitch_ts)

    # 5. Booms sur révélations
    boom_name, boom_vol = _stage("sub_bass_boom", 0.60)
    if boom_name:
        for idx, t in enumerate(boom_ts):
            if t + 1.0 > total_duration:
                continue
            html_parts.append(
                f'<audio id="sfx_boom{idx}" class="clip" src="assets/{boom_name}" '
                f'data-start="{t:.3f}" data-duration="1.8" '
                f'data-track-index="{sfx_track + idx}" data-volume="{boom_vol}"></audio>'
            )
        sfx_track += len(boom_ts)

    # 6. Riser sous le CTA outro (dernière scène, dans sa seconde moitié)
    riser_name, riser_vol = _stage("riser", 0.45)
    if riser_name and scenes_meta:
        last = scenes_meta[-1]
        t = last["start"] + last["duration"] * 0.45
        riser_dur = max(1.2, min(2.5, last["duration"] * 0.5))
        if t + riser_dur <= total_duration:
            html_parts.append(
                f'<audio id="sfx_riser_outro" class="clip" src="assets/{riser_name}" '
                f'data-start="{t:.3f}" data-duration="{riser_dur:.3f}" '
                f'data-track-index="{sfx_track}" data-volume="{riser_vol}"></audio>'
            )
            sfx_track += 1

    return html_parts, js_parts


def compile_sfx_composite(
    projet_dir,
    total_duration,
    woosh_timestamps,
    glitch_timestamps,
    boom_timestamps,
    scenes_data,
    dramatic_events=None,
):
    """
    Compile tous les triggers SFX (whooshes, glitches, booms, riser, impact, and scene SFX)
    dans un unique fichier audio sfx_composite.wav pour le mixage final FFmpeg.
    """
    import numpy as np
    import soundfile as sf

    sr = 44100
    n_samples = int(total_duration * sr)
    composite = np.zeros(n_samples, dtype=np.float32)

    sfx_root = ROOT / "assets" / "sfx"

    def load_sfx_sample(name):
        for ext in [".wav", ".mp3"]:
            p = sfx_root / f"{name}{ext}"
            if p.exists():
                try:
                    data, sample_rate = sf.read(str(p))
                    if len(data.shape) > 1:
                        data = np.mean(data, axis=1)
                    if sample_rate != sr:
                        num_samples = int(len(data) * sr / sample_rate)
                        data = np.interp(
                            np.linspace(0, len(data), num_samples, endpoint=False),
                            np.arange(len(data)),
                            data,
                        )
                    return data
                except Exception as e:
                    print(f"   ⚠️ Erreur chargement échantillon SFX {name} : {e}")
        return None

    whoosh_samp = load_sfx_sample("whoosh")
    glitch_samp = load_sfx_sample("glitch")
    boom_samp = load_sfx_sample("sub_bass_boom")
    if boom_samp is None:
        boom_samp = load_sfx_sample("sub-drop")
    impact_samp = load_sfx_sample("impact")
    riser_samp = load_sfx_sample("riser")

    # 1. Overlay whooshes
    if whoosh_samp is not None:
        for t in woosh_timestamps:
            idx = int(t * sr)
            if idx < n_samples:
                length = min(len(whoosh_samp), n_samples - idx)
                composite[idx : idx + length] += whoosh_samp[:length] * 0.45

    # 2. Overlay glitches
    if glitch_samp is not None:
        for t in glitch_timestamps:
            idx = int(t * sr)
            if idx < n_samples:
                length = min(len(glitch_samp), n_samples - idx)
                composite[idx : idx + length] += glitch_samp[:length] * 0.48

    # 3. Overlay booms
    if boom_samp is not None:
        for t in boom_timestamps:
            idx = int(t * sr)
            if idx < n_samples:
                length = min(len(boom_samp), n_samples - idx)
                composite[idx : idx + length] += boom_samp[:length] * 0.58

    # 4. Overlay standard SFX
    if impact_samp is not None and scenes_data:
        idx = int(scenes_data[0]["voice_start"] * sr)
        if idx < n_samples:
            length = min(len(impact_samp), n_samples - idx)
            composite[idx : idx + length] += impact_samp[:length] * 0.65

    if riser_samp is not None and scenes_data:
        last_scene = scenes_data[-1]
        t_riser = last_scene["voice_start"] + last_scene["duration"] * 0.45
        idx = int(t_riser * sr)
        if idx < n_samples:
            length = min(len(riser_samp), n_samples - idx)
            composite[idx : idx + length] += riser_samp[:length] * 0.45

    # Chargement des SFX de scènes générés par 2.3_generate_music.py si présents
    for i, scene in enumerate(scenes_data):
        sfx_src = Path(projet_dir) / "audio" / "sfx" / f"scene_{i + 1}.wav"
        if sfx_src.exists():
            try:
                data, sample_rate = sf.read(str(sfx_src))
                if len(data.shape) > 1:
                    data = np.mean(data, axis=1)
                if sample_rate != sr:
                    num_samples = int(len(data) * sr / sample_rate)
                    data = np.interp(
                        np.linspace(0, len(data), num_samples, endpoint=False),
                        np.arange(len(data)),
                        data,
                    )
                idx = int(scene["voice_start"] * sr)
                if idx < n_samples:
                    length = min(len(data), n_samples - idx)
                    composite[idx : idx + length] += data[:length] * 0.45
            except Exception as e:
                print(f"   ⚠️ Erreur chargement SFX scène {i + 1} : {e}")

    # Ruptures horrifiques : retire les ambiances/SFX juste avant la révélation,
    # puis place un impact sec exactement sur le mot-clé.
    dramatic_events = dramatic_events or []
    for event in dramatic_events:
        t = float(event["time"])
        silence_start = max(0, int((t - 0.85) * sr))
        silence_end = max(silence_start, int((t - 0.06) * sr))
        composite[silence_start:silence_end] = 0.0
        sting = boom_samp if boom_samp is not None else impact_samp
        if sting is not None:
            idx = int(t * sr)
            if idx < n_samples:
                length = min(len(sting), n_samples - idx)
                composite[idx : idx + length] += sting[:length] * 0.78

    # Soft-clip et normalisation
    composite = np.tanh(composite * 1.15)
    peak = np.max(np.abs(composite))
    if peak > 0:
        composite = (composite / peak * 0.85).astype(np.float32)

    out_path = Path(projet_dir) / "audio" / "sfx_composite.wav"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), composite, sr)
    print(f"   🔊 sfx_composite.wav généré avec succès ({len(composite) / sr:.2f}s)")
    return out_path
