"""
2.3_generate_music.py
─────────────────────
Sélectionne la musique d'ambiance pour la vidéo.
Pipeline :
  1. Pioche aléatoire dans la bibliothèque locale `musiques/library/`
     (tracks Pixabay Music, YouTube Audio Library, etc. — gratuit, libre commercial)
  2. Fallback : génère un drone d'ambiance cinématique via numpy
"""
import os
import json
import wave
import random
import shutil
import glob
import numpy as np
from utils import trouver_dernier_projet

LIBRARY_DIR = "musiques/library"


# ═══════════════════════════════════════════════════════
# OPTION 1 : Bibliothèque locale curée
# ═══════════════════════════════════════════════════════
def selectionner_depuis_library(chemin_sortie_mp3):
    """
    Pioche une track aléatoire dans musiques/library/.
    Retourne True si une track a été copiée, False sinon.
    """
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    tracks = []
    for ext in ('*.mp3', '*.wav', '*.m4a', '*.ogg'):
        tracks.extend(glob.glob(os.path.join(LIBRARY_DIR, ext)))

    if not tracks:
        print(f"   ℹ️ Bibliothèque vide ({LIBRARY_DIR}/) — fallback drone numpy")
        print(f"      → Télécharge des tracks 'dark ambient' / 'true crime' depuis :")
        print(f"        • https://pixabay.com/music/search/dark%20ambient/")
        print(f"        • https://pixabay.com/music/search/cinematic%20horror/")
        print(f"        • https://pixabay.com/music/search/suspense%20drone/")
        print(f"        Et place-les dans {LIBRARY_DIR}/")
        return False

    chosen = random.choice(tracks)
    ext_chosen = os.path.splitext(chosen)[1].lower()

    if ext_chosen == '.mp3':
        shutil.copy(chosen, chemin_sortie_mp3)
        print(f"   🎵 Track sélectionnée : {os.path.basename(chosen)}")
        return True

    # Conversion vers MP3 si autre format
    try:
        import subprocess
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', chosen,
             '-codec:a', 'libmp3lame', '-b:a', '192k',
             chemin_sortie_mp3],
            capture_output=True, timeout=120
        )
        if result.returncode == 0:
            print(f"   🎵 Track convertie : {os.path.basename(chosen)} → MP3")
            return True
    except Exception as e:
        print(f"   ⚠️ Conversion track échouée : {e}")

    return False


# ═══════════════════════════════════════════════════════
# OPTION 2 : Score de tension stratifié (fallback)
# ═══════════════════════════════════════════════════════

# ── Helpers pour Drone, Reverb et Noise ───────────────────────────────────────
def generate_brown_noise(n):
    """Génère du bruit brun (Brownian noise) via filtrage spectral FFT pour éviter la dérive."""
    white_fft = np.fft.rfft(np.random.normal(0, 1.0, n))
    frequencies = np.arange(1, len(white_fft) + 1)
    brown_fft = white_fft / frequencies
    brown_noise = np.fft.irfft(brown_fft, n)
    peak = np.max(np.abs(brown_noise))
    if peak > 0:
        brown_noise /= peak
    return brown_noise.astype(np.float32)


def feedback_comb_filter(x, delay_samples, feedback):
    """Filtre en peigne à rétroaction optimisé et vectorisé par blocs."""
    y = x.copy()
    n = len(x)
    for start in range(0, n, delay_samples):
        end = min(start + delay_samples, n)
        if start >= delay_samples:
            y[start:end] += feedback * y[start - delay_samples : end - delay_samples]
    return y


def schroeder_reverb(x, sample_rate=44100):
    """Simule un espace réverbérant via un réseau de filtres en peigne en parallèle."""
    delays = [0.0297, 0.0371, 0.0411, 0.0437]
    feedbacks = [0.75, 0.72, 0.69, 0.66]
    
    comb_outputs = []
    for d, f in zip(delays, feedbacks):
        delay_samples = int(d * sample_rate)
        comb_outputs.append(feedback_comb_filter(x, delay_samples, f))
    
    summed_comb = np.sum(comb_outputs, axis=0) / len(comb_outputs)
    return 0.4 * summed_comb + 0.6 * x


def physical_heartbeat(sample_rate=44100):
    """Modèle physique d'un battement de coeur (lub-dub) sans clic."""
    t1 = np.linspace(0, 0.15, int(0.15 * sample_rate))
    env1 = (t1 / 0.02) * np.exp(1 - t1 / 0.02)
    env1[t1 > 0.1] *= np.exp(-50 * (t1[t1 > 0.1] - 0.1))
    lub = np.sin(2 * np.pi * 45.0 * t1) * env1
    
    t2 = np.linspace(0, 0.12, int(0.12 * sample_rate))
    env2 = (t2 / 0.015) * np.exp(1 - t2 / 0.015)
    env2[t2 > 0.08] *= np.exp(-60 * (t2[t2 > 0.08] - 0.08))
    dub = np.sin(2 * np.pi * 58.0 * t2) * env2
    
    beat_len = int(0.6 * sample_rate)
    beat = np.zeros(beat_len, dtype=np.float32)
    beat[:len(t1)] += 0.8 * lub
    
    offset = int(0.16 * sample_rate)
    beat[offset:offset+len(t2)] += 0.6 * dub
    return beat


def apply_delay_tail(x, delay_time=0.22, feedback=0.45, sample_rate=44100):
    """Applique un délai avec feedback pour simuler une queue de réverb/écho."""
    delay_samples = int(delay_time * sample_rate)
    y = x.copy()
    n = len(x)
    for start in range(0, n, delay_samples):
        end = min(start + delay_samples, n)
        if start >= delay_samples:
            y[start:end] += feedback * y[start - delay_samples : end - delay_samples]
    return y


def generer_tension_score(chemin_sortie_wav, duree=150, sample_rate=44100):
    """
    Partition de tension true-crime stratifiée via numpy.
    Couche 1 — Sub-drone 38Hz (FM Synthesis)
    Couche 2 — Drone tonique 57Hz (FM Synthesis)
    Couche 3 — Dissonance pad (FM Synthesis)
    Couche 4 — Heartbeat (modèle physique + HRV)
    Couche 5 — Risers cycliques
    Couche 6 — Bruit brun chaud (spectral FFT)
    Couche 7 — Shimmer aigu
    Le drone ambiant complet passe par un Schroeder Reverb (feedback comb delays).
    """
    print(f"   🎵 Génération partition de tension FM + Reverb ({duree}s, 7 couches)...")
    n = int(duree * sample_rate)
    t = np.linspace(0, duree, n, dtype=np.float32)

    lfo_slow = 0.5 + 0.5 * np.sin(2 * np.pi * 0.022 * t)
    dissonance_lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.013 * t + 1.5)
    drone_med_lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.027 * t + 0.7)
    shimmer_lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.08 * t + 2.1)

    # ── Couche 1 : sub-drone 38Hz (FM Synthesis)
    phase_mod1 = np.sin(2 * np.pi * 19.0 * t) * (1.5 * lfo_slow)
    sub_drone = 0.55 * np.sin(2 * np.pi * 38.0 * t + phase_mod1)

    # ── Couche 2 : drone tonique 57Hz (Bb1) + harmonique 5th (FM Synthesis)
    phase_mod2 = np.sin(2 * np.pi * 28.5 * t) * (1.2 * (0.3 + 0.7 * lfo_slow))
    drone_tonic = 0.42 * np.sin(2 * np.pi * 57.0 * t + phase_mod2)
    phase_mod_fifth = np.sin(2 * np.pi * 42.75 * t) * (0.8 * lfo_slow)
    drone_fifth = 0.18 * np.sin(2 * np.pi * 85.5 * t + phase_mod_fifth)

    # ── Couche 3 : dissonance pad (FM Synthesis)
    phase_mod_tritone = np.sin(2 * np.pi * 40.3 * t) * (1.0 * dissonance_lfo)
    tritone = 0.16 * np.sin(2 * np.pi * 80.6 * t + phase_mod_tritone)
    phase_mod_m2 = np.sin(2 * np.pi * 30.2 * t) * (0.8 * dissonance_lfo)
    minor2 = 0.13 * np.sin(2 * np.pi * 60.4 * t + phase_mod_m2)

    # ── Couche 3b : drone medium 220Hz fluctuant (FM Synthesis)
    phase_mod_med1 = np.sin(2 * np.pi * 110.0 * t) * (0.6 * drone_med_lfo)
    drone_medium = 0.10 * np.sin(2 * np.pi * 220.0 * t + phase_mod_med1)
    phase_mod_med2 = np.sin(2 * np.pi * 116.5 * t) * (0.5 * drone_med_lfo)
    drone_medium += 0.07 * np.sin(2 * np.pi * 233.0 * t + phase_mod_med2)

    # ── Couche 5 : risers cycliques toutes les 25s
    risers = np.zeros(n, dtype=np.float32)
    cycle = 25.0
    n_cycles = int(duree / cycle)
    for c in range(n_cycles):
        start_s = c * cycle + 2.0
        end_s = start_s + min(cycle - 3.0, 15.0)
        if end_s > duree:
            break
        i0, i1 = int(start_s * sample_rate), int(end_s * sample_rate)
        if i1 <= i0:
            continue
        local_t = np.linspace(0, 1, i1 - i0, dtype=np.float32)
        riser_freq = 70.0 * (500.0 / 70.0) ** local_t
        riser_phase = 2 * np.pi * np.cumsum(riser_freq) / sample_rate
        riser_env = local_t ** 2.4
        risers[i0:i1] += 0.13 * np.sin(riser_phase).astype(np.float32) * riser_env

    # ── Couche 6 : bruit brun chaud (spectral FFT)
    brown_noise = generate_brown_noise(n)
    hiss_layer = 0.045 * brown_noise * (0.4 + 0.6 * lfo_slow)

    # ── Couche 7 : shimmer aigu très subtil (4-5kHz)
    shimmer = 0.018 * np.sin(2 * np.pi * 4400.0 * t) * shimmer_lfo
    shimmer += 0.012 * np.sin(2 * np.pi * 5230.0 * t + 1.3) * shimmer_lfo

    # Mixage ambiance
    ambient_signal = (
        sub_drone
        + drone_tonic
        + drone_fifth
        + tritone
        + minor2
        + drone_medium
        + risers
        + hiss_layer
        + shimmer
    )

    # Schroeder Reverb sur l'ambiance
    ambient_wet = schroeder_reverb(ambient_signal, sample_rate)

    # ── Couche 4 : heartbeat (BPM qui accélère 55 → 78, avec HRV et modèle physique)
    heartbeat_signal = np.zeros(n, dtype=np.float32)
    single_beat = physical_heartbeat(sample_rate)
    
    trigger_times = []
    curr_t = 0.2
    while curr_t < duree - 0.6:
        trigger_times.append(curr_t)
        base_bpm = 55.0 + (78.0 - 55.0) * (curr_t / duree)
        base_interval = 60.0 / base_bpm
        # HRV: RSA (modulation par la respiration) + jitter
        rsa = 0.05 * np.sin(2 * np.pi * 0.18 * curr_t)
        jitter = np.random.normal(0, 0.015)
        interval = base_interval + rsa + jitter
        curr_t += max(0.5, min(interval, 1.5))
        
    for t_trig in trigger_times:
        idx = int(t_trig * sample_rate)
        if idx < n:
            length = min(len(single_beat), n - idx)
            heartbeat_signal[idx : idx + length] += single_beat[:length]

    # Mixage final (ambiance réverbérée + battement propre et sec)
    signal = ambient_wet + 0.45 * heartbeat_signal

    # Enveloppe de tension croissante
    tension_env = 0.55 + 0.45 * (t / duree) ** 1.4
    signal = signal * tension_env

    # Soft-clip
    signal = np.tanh(signal * 1.15) * 0.85

    # Normalisation
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.80

    # Fades
    fade_in = np.linspace(0, 1, min(int(2.5 * sample_rate), n))
    fade_out = np.linspace(1, 0, min(int(4.0 * sample_rate), n))
    signal[:len(fade_in)] *= fade_in
    signal[-len(fade_out):] *= fade_out

    # Stéréo (Haas effect)
    signal_int16 = (signal * 32767).astype(np.int16)
    stereo = np.column_stack([
        signal_int16,
        np.roll(signal_int16, int(sample_rate * 0.011))
    ])

    with wave.open(chemin_sortie_wav, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(stereo.tobytes())

    print(f"   ✅ Partition tension générée : {os.path.basename(chemin_sortie_wav)}")
    return True


# Alias pour rétrocompatibilité
generer_drone_cinematic = generer_tension_score


def generer_sfx_impact(chemin_sortie, duree=4, sample_rate=44100):
    """
    Impact sourd profond cinématique (trailer hit).
    Modèle physique à 3 parties :
      1. Clic transitoire (attaque métallique à haute fréquence + bruit)
      2. Corps sub-bass (onde sinusoïdale descendante de 120Hz à 35Hz avec enveloppe exponentielle)
      3. Queue de délai (réverbération spatiale via delay feedback)
    """
    n = int(duree * sample_rate)
    
    # 1. Clic transitoire (50 ms)
    t_transient = np.linspace(0, 0.05, int(0.05 * sample_rate), dtype=np.float32)
    click = (np.sin(2 * np.pi * 1500.0 * t_transient) + np.sin(2 * np.pi * 3200.0 * t_transient)) * np.exp(-150 * t_transient)
    noise_burst = np.random.normal(0, 1.0, len(t_transient)).astype(np.float32) * np.exp(-200 * t_transient)
    transient = 0.5 * click + 0.3 * noise_burst

    # 2. Corps sub-bass (duree entière)
    t = np.linspace(0, duree, n, dtype=np.float32)
    freq_sweep = 120.0 * np.exp(-30.0 * t) + 35.0
    phase_sweep = 2 * np.pi * np.cumsum(freq_sweep) / sample_rate
    body = np.sin(phase_sweep) * np.exp(-3.5 * t)

    # Assemblage initial
    signal = np.zeros(n, dtype=np.float32)
    signal[:len(transient)] += transient * 0.7
    signal += body * 0.8

    # 3. Queue de délai (space reflections)
    signal = apply_delay_tail(signal, delay_time=0.22, feedback=0.42, sample_rate=sample_rate)

    # Normalisation et soft clipping
    signal = np.tanh(signal * 1.2)
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.85

    signal_int16 = (signal * 32767).astype(np.int16)
    with wave.open(chemin_sortie, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(signal_int16.tobytes())
    print(f"   ✅ SFX impact généré : {os.path.basename(chemin_sortie)}")


def generer_sfx_organique(chemin_sortie, type_organique="heartbeat", duree=6, sample_rate=44100):
    """
    Son organique (battement de coeur).
    Utilise le modèle physique de double battement (lub-dub) sans clic et la variabilité cardiaque (HRV).
    """
    n = int(duree * sample_rate)
    signal = np.zeros(n, dtype=np.float32)
    
    if "heart" in type_organique.lower():
        single_beat = physical_heartbeat(sample_rate)
        
        trigger_times = []
        curr_t = 0.2
        bpm = 65.0
        while curr_t < duree - 0.6:
            trigger_times.append(curr_t)
            base_interval = 60.0 / bpm
            rsa = 0.04 * np.sin(2 * np.pi * 0.25 * curr_t)
            jitter = np.random.normal(0, 0.01)
            interval = base_interval + rsa + jitter
            curr_t += max(0.4, min(interval, 1.2))
            
        for t_trig in trigger_times:
            idx = int(t_trig * sample_rate)
            if idx < n:
                length = min(len(single_beat), n - idx)
                signal[idx : idx + length] += single_beat[:length]
                
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.75

    signal_int16 = (signal * 32767).astype(np.int16)
    with wave.open(chemin_sortie, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(signal_int16.tobytes())
    print(f"   ✅ SFX organique généré : {os.path.basename(chemin_sortie)}")


def wav_to_mp3(chemin_wav, chemin_mp3):
    """Conversion WAV → MP3 via ffmpeg."""
    try:
        import subprocess
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', chemin_wav,
             '-codec:a', 'libmp3lame', '-b:a', '192k', '-q:a', '2',
             chemin_mp3],
            capture_output=True, timeout=60
        )
        if result.returncode == 0:
            os.remove(chemin_wav)
            print(f"   ✅ MP3 converti : {os.path.basename(chemin_mp3)}")
            return True
    except Exception as e:
        print(f"   ⚠️ Conversion MP3 : {e}")
    return False


# ═══════════════════════════════════════════════════════
# ORCHESTRATEUR
# ═══════════════════════════════════════════════════════
def generer_musique(dossier_projet):
    os.makedirs("musiques", exist_ok=True)
    os.makedirs(LIBRARY_DIR, exist_ok=True)

    script = None
    script_path = f"{dossier_projet}/script.json"
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            script = json.load(f)

    print(f"\n🎵 SÉLECTION MUSIQUE D'AMBIANCE")

    projet_name = os.path.basename(dossier_projet)
    chemin_mp3  = f"musiques/{projet_name}_ambient.mp3"
    chemin_wav  = f"musiques/{projet_name}_ambient.wav"

    if os.path.exists(chemin_mp3):
        print(f"   ⏭️ Musique déjà prête : {os.path.basename(chemin_mp3)}")
        return chemin_mp3

    musique_ok = selectionner_depuis_library(chemin_mp3)

    if not musique_ok:
        if generer_drone_cinematic(chemin_wav, duree=150):
            if not wav_to_mp3(chemin_wav, chemin_mp3):
                chemin_mp3 = chemin_wav

    # ── SFX par scène (impact, organique) ──
    if script:
        print(f"\n🎧 GÉNÉRATION DES SFX PAR SCÈNE ({len(script['scenes'])} scènes)")
        os.makedirs(f"{dossier_projet}/audio/sfx", exist_ok=True)

        for scene in script.get("scenes", []):
            s_id = scene['id']
            s_type = scene.get('lyria_type', 'ambiance')
            s_prompt = scene.get('lyria_prompt', '')
            chemin_sfx = f"{dossier_projet}/audio/sfx/scene_{s_id}.wav"

            if s_type == 'impact':
                print(f"   🔊 Scène {s_id} : impact")
                generer_sfx_impact(chemin_sfx)
            elif s_type == 'organique':
                print(f"   🔊 Scène {s_id} : organique")
                generer_sfx_organique(chemin_sfx, s_prompt)

    return chemin_mp3 if os.path.exists(chemin_mp3) else (chemin_wav if os.path.exists(chemin_wav) else None)


if __name__ == "__main__":
    d = trouver_dernier_projet()
    if d:
        result = generer_musique(d)
        if result:
            print(f"\n✅ Musique prête → {result}")
