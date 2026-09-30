"""
Point d'entrée de l'usine.

⚠️ PIVOT : le mode principal est désormais la SÉRIE DRAMATIQUE 1ʳᵉ PERSONNE,
avec workflow de validation obligatoire (synopsis → épisode par épisode).
→ `python 0_usine.py`  délègue à `0_serie.py`.

L'ancien pipeline TRUE-CRIME automatique (sans validation) reste disponible,
mais débranché du flow principal :
→ `python 0_usine.py --legacy-truecrime [N]`
"""
import subprocess
import time
import sys
import os


def demarrer_serie():
    """Mode principal : orchestrateur série dramatique (0_serie.py)."""
    subprocess.run([sys.executable, "0_serie.py"], cwd=os.path.dirname(os.path.abspath(__file__)))


def demarrer_usine_legacy(nombre: int):
    """LEGACY — ancien pipeline true-crime automatique (true-crime, sans gate de validation)."""
    print("══════════════════════════════════════════════════════")
    print("   🎬 [LEGACY] USINE TRUE-CRIME — PIPELINE AUTO 🎬 ")
    print("══════════════════════════════════════════════════════")
    python_cmd = sys.executable
    os.makedirs("musiques", exist_ok=True)

    for i in range(nombre):
        print(f"\n🎬 VIDÉO {i+1}/{nombre} 🎬")
        echec = False
        etapes = [
            ("🧠 1/6 : Génération du scénario (Gemini)...",         "1_generate_brain.py"),
            ("🎙️ 2/6 : Voix Gemini TTS / Edge fallback...",        "2_generate_audio.py"),
            ("🎵 3/6 : Musique depuis bibliothèque locale...",       "2.3_generate_music.py"),
            ("🧠 4/6 : Orchestration Whisper + Director...",         "2.5_director_orchestrator.py"),
            ("🎨 5/6 : Images Imagen 4 / stock fallback...",        "2.7_media_fetcher.py"),
            ("🎬 6/6 : Rendu HyperFrames → final.mp4...",           "3_render_hyperframes.py"),
        ]
        for label, script in etapes:
            print(f"\n{label}")
            r = subprocess.run([python_cmd, script])
            if r.returncode != 0:
                print(f"\n❌ Échec sur {script} (code {r.returncode}). Pipeline arrêté.")
                echec = True
                break
        if echec:
            print(f"\n⛔ Vidéo {i+1} abandonnée.")
        else:
            print(f"\n✅ Vidéo {i+1} terminée !")
        if i < nombre - 1 and not echec:
            print("\n⏳ Pause anti-limite (30s)...")
            time.sleep(30)


if __name__ == "__main__":
    if "--legacy-truecrime" in sys.argv:
        # Récupère le nombre éventuel (dernier argument numérique), défaut 1.
        nums = [int(a) for a in sys.argv[1:] if a.isdigit()]
        demarrer_usine_legacy(nums[0] if nums else 1)
    else:
        demarrer_serie()
