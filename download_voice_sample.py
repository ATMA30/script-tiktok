"""
download_voice_sample.py
─────────────────────────
Télécharge un segment audio précis d'une vidéo YouTube
et le prépare pour le clonage de voix sur ElevenLabs.

Usage :
    python3 download_voice_sample.py

Le script demande :
  1. Le lien YouTube
  2. Le timecode de début (MM:SS ou HH:MM:SS)
  3. Le timecode de fin
  4. Un nom pour le fichier de sortie

Le résultat va dans `voice_samples/<nom>.mp3` :
  - Audio mono 44100 Hz, 192 kbps (qualité ElevenLabs Voice Cloning)
  - Volume normalisé (loudnorm)
  - Prêt à uploader sur https://elevenlabs.io/app/voice-lab
"""

import os
import re
import sys
import subprocess
import yt_dlp

OUTPUT_DIR = "voice_samples"


def parser_timecode(tc: str) -> int:
    """Convertit 'MM:SS' ou 'HH:MM:SS' en secondes (int)."""
    tc = tc.strip()
    if not re.match(r'^\d+(:\d{1,2}){0,2}$', tc):
        raise ValueError(f"Timecode invalide : {tc!r} (attendu MM:SS ou HH:MM:SS)")
    parts = [int(p) for p in tc.split(':')]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"Timecode invalide : {tc!r}")


def secondes_vers_hhmmss(s: int) -> str:
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def nom_fichier_sain(nom: str) -> str:
    nom = re.sub(r'[^\w\-]+', '_', nom).strip('_')
    return nom or "voice_sample"


def telecharger_segment(url: str, start_s: int, end_s: int, sortie_mp3: str):
    """Télécharge UNIQUEMENT le segment via yt-dlp + extrait MP3 normalisé."""
    duree = end_s - start_s
    if duree <= 0:
        raise ValueError("La fin doit être après le début.")

    # yt-dlp utilise le format "*HH:MM:SS-HH:MM:SS"
    section = f"*{secondes_vers_hhmmss(start_s)}-{secondes_vers_hhmmss(end_s)}"

    print(f"\n📥 Téléchargement du segment {section[1:]} (≈ {duree}s)...")

    # Sortie temporaire (yt-dlp choisit l'extension)
    tmp_dir = os.path.join(OUTPUT_DIR, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    template = os.path.join(tmp_dir, "raw.%(ext)s")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': template,
        'download_ranges': yt_dlp.utils.download_range_func(None, [(start_s, end_s)]),
        'force_keyframes_at_cuts': True,
        'quiet': True,
        'no_warnings': True,
        'noprogress': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        titre_video = info.get('title', 'unknown')
        print(f"   🎬 Vidéo : {titre_video}")

    # Trouver le fichier téléchargé (extension variable)
    fichiers_tmp = [f for f in os.listdir(tmp_dir) if f.startswith("raw.")]
    if not fichiers_tmp:
        raise RuntimeError("Aucun fichier téléchargé.")
    raw_path = os.path.join(tmp_dir, fichiers_tmp[0])

    # ffmpeg : conversion → MP3 mono 44100 Hz + loudnorm (qualité ElevenLabs)
    print("\n🎚️ Conversion + normalisation audio...")
    cmd = [
        'ffmpeg', '-y',
        '-i', raw_path,
        '-ac', '1',                    # mono
        '-ar', '44100',                # 44.1 kHz
        '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',  # normalisation broadcast
        '-codec:a', 'libmp3lame',
        '-b:a', '192k',
        sortie_mp3,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ ffmpeg erreur : {result.stderr[-500:]}")
        raise RuntimeError("Conversion ffmpeg échouée")

    # Cleanup tmp
    try:
        os.remove(raw_path)
        os.rmdir(tmp_dir)
    except Exception:
        pass


def main():
    print("═" * 56)
    print("  🎙️ EXTRACTEUR DE SAMPLE VOIX — pour Voice Cloning")
    print("═" * 56)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        url = input("\n🔗 Lien YouTube : ").strip()
        if not url:
            print("❌ Lien vide, abandon.")
            return

        start_str = input("⏱️  Début   (MM:SS ou HH:MM:SS) : ").strip()
        end_str   = input("⏱️  Fin     (MM:SS ou HH:MM:SS) : ").strip()

        start_s = parser_timecode(start_str)
        end_s   = parser_timecode(end_str)

        if end_s <= start_s:
            print("❌ La fin doit être après le début.")
            return

        nom_default = f"sample_{start_str.replace(':','')}_{end_str.replace(':','')}"
        nom_input = input(f"📝 Nom du fichier (défaut: {nom_default}) : ").strip()
        nom = nom_fichier_sain(nom_input or nom_default)

        sortie_mp3 = os.path.join(OUTPUT_DIR, f"{nom}.mp3")

        telecharger_segment(url, start_s, end_s, sortie_mp3)

        taille_mo = os.path.getsize(sortie_mp3) / 1024 / 1024
        duree = end_s - start_s
        print(f"\n✅ Sample prêt : {sortie_mp3}")
        print(f"   • Durée : {duree}s")
        print(f"   • Taille : {taille_mo:.1f} Mo")
        print(f"\n📤 Étape suivante : upload sur https://elevenlabs.io/app/voice-lab")
        print(f"   → Add Voice → Instant Voice Clone → upload {os.path.basename(sortie_mp3)}")
        print(f"   → Récupère le Voice ID → mets-le dans .env (ELEVENLABS_VOICE_ID=...)")

    except KeyboardInterrupt:
        print("\n\n⏹️ Interrompu.")
    except Exception as e:
        print(f"\n❌ Erreur : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
