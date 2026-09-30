"""
Script batch : Produit N vidéos complètes l'une après l'autre.

Usage :
  python3 batch_produce.py                     → traite tous les projets sans final.mp4
  python3 batch_produce.py projets/mon_projet  → force un projet spécifique
"""

import subprocess
import sys
import os
import glob
import json

ETAPES = [
    "2_generate_audio.py",
    "2.3_generate_music.py",
    "2.5_director_orchestrator.py",
    "2.7_media_fetcher.py",
    "3_render_hyperframes.py",
]

FINAL_VIDEO = "final.mp4"


def lire_visual_style(projet_dir: str) -> str:
    """Lit visual_style depuis script.json du projet (défaut: anime)."""
    try:
        script_path = os.path.join(projet_dir, "script.json")
        if os.path.exists(script_path):
            with open(script_path, encoding="utf-8") as f:
                return json.load(f).get("visual_style", "anime")
    except Exception:
        pass
    return "anime"


def run_step(script, projet_dir, visual_style="anime"):
    env = os.environ.copy()
    env["FORCE_PROJET"] = projet_dir
    env["VISUAL_STYLE"] = visual_style
    print(f"\n{'=' * 60}")
    print(f"▶ {script} → {os.path.basename(projet_dir)}")
    print(f"{'=' * 60}")
    result = subprocess.run(
        [sys.executable, script],
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    if result.returncode != 0:
        print(f"❌ ERREUR sur {script} (code {result.returncode})")
        return False
    return True


def detecter_projets_a_traiter():
    """Retourne les projets qui n'ont pas encore de rendu final."""
    if not os.path.isdir("projets"):
        return []
    tous = sorted(glob.glob("projets/*/script.json"))
    a_traiter = []
    for script_path in tous:
        dossier = os.path.dirname(script_path)
        if not os.path.exists(os.path.join(dossier, FINAL_VIDEO)):
            a_traiter.append(dossier)
    return a_traiter


# Projets explicites en argument, sinon auto-détection
if len(sys.argv) > 1:
    PROJETS = [p for p in sys.argv[1:] if os.path.isdir(p)]
else:
    PROJETS = detecter_projets_a_traiter()

if not PROJETS:
    print(f"✅ Aucun projet à traiter (tous ont déjà un {FINAL_VIDEO}).")
    sys.exit(0)

print(f"\n🎬 {len(PROJETS)} projet(s) à produire :")
for p in PROJETS:
    print(f"   • {os.path.basename(p)}")

for i, projet in enumerate(PROJETS):
    print(f"\n\n{'=' * 60}")
    print(f"  PRODUCTION {i + 1}/{len(PROJETS)} : {os.path.basename(projet)}")
    print(f"{'=' * 60}")

    vs = lire_visual_style(projet)
    if vs == "noir":
        print(f"  🎨 Style : NOIR B&W (mystère)")

    for step in ETAPES:
        if not run_step(step, projet, visual_style=vs):
            print(f"⛔ Pipeline arrêté pour {os.path.basename(projet)}")
            break
    else:
        print(f"\n✅ VIDÉO {i + 1} TERMINÉE : {projet}/{FINAL_VIDEO}")

print(f"\n\n{'=' * 60}")
print("  BATCH TERMINÉ")
print(f"{'=' * 60}")
