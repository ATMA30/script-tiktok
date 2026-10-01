"""
Rendu batch : enchaîne les étapes 1 à 5 sur les projets VALIDÉS sans final.mp4.

Un projet n'est rendu que si sa validation humaine est faite
(python 0_usine.py --valider projets/…).

Usage :
  python3 batch_produce.py                     → tous les projets validés sans final.mp4
  python3 batch_produce.py projets/mon_projet  → un projet précis (doit être validé)
"""

import glob
import json
import os
import subprocess
import sys

from usine.projet import est_valide, statut_validation

ETAPES = [
    "2_generate_audio.py",
    "2.3_generate_music.py",
    "2.5_director_orchestrator.py",
    "2.7_media_fetcher.py",
    "3_render_hyperframes.py",
]

FINAL_VIDEO = "final.mp4"
STYLE_DEFAUT = "low_poly_3d"


def lire_visual_style(projet_dir: str) -> str:
    """Lit visual_style depuis script.json du projet (défaut : low_poly_3d)."""
    try:
        script_path = os.path.join(projet_dir, "script.json")
        if os.path.exists(script_path):
            with open(script_path, encoding="utf-8") as f:
                return json.load(f).get("visual_style", STYLE_DEFAUT)
    except Exception:
        pass
    return STYLE_DEFAUT


def run_step(script, projet_dir, visual_style=STYLE_DEFAUT):
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
    """Projets validés qui n'ont pas encore de rendu final."""
    if not os.path.isdir("projets"):
        return []
    a_traiter = []
    for script_path in sorted(glob.glob("projets/*/script.json")):
        dossier = os.path.dirname(script_path)
        if os.path.exists(os.path.join(dossier, FINAL_VIDEO)):
            continue
        if est_valide(dossier):
            a_traiter.append(dossier)
        else:
            statut = statut_validation(dossier) or "sans statut"
            print(f"   ⏸️  Ignoré (non validé : {statut}) : {os.path.basename(dossier)}")
    return a_traiter


def produire(projet, etapes=ETAPES):
    """Enchaîne `etapes` (par défaut 1 à 5) sur un projet validé. True si tout réussit."""
    vs = lire_visual_style(projet)
    for step in etapes:
        if not run_step(step, projet, visual_style=vs):
            print(f"⛔ Pipeline arrêté pour {os.path.basename(projet)}")
            return False
    if etapes[-1] == ETAPES[-1]:
        print(f"\n✅ VIDÉO TERMINÉE : {projet}/{FINAL_VIDEO}")
    return True


def main(argv):
    if argv:
        projets = []
        for p in argv:
            if not os.path.isdir(p):
                print(f"   ⚠️ Dossier introuvable : {p}")
            elif not est_valide(p):
                print(
                    f"   ⏸️  Non validé, ignoré : {p}  (python 0_usine.py --valider {p})"
                )
            else:
                projets.append(p)
    else:
        projets = detecter_projets_a_traiter()

    if not projets:
        print(f"✅ Aucun projet validé à traiter (sans {FINAL_VIDEO}).")
        return 0

    print(f"\n🎬 {len(projets)} projet(s) à produire :")
    for p in projets:
        print(f"   • {os.path.basename(p)}")

    echecs = 0
    for i, projet in enumerate(projets):
        print(f"\n\n{'=' * 60}")
        print(f"  PRODUCTION {i + 1}/{len(projets)} : {os.path.basename(projet)}")
        print(f"{'=' * 60}")
        if not produire(projet):
            echecs += 1

    print(f"\n\n{'=' * 60}")
    print(f"  BATCH TERMINÉ ({len(projets) - echecs}/{len(projets)} réussis)")
    print(f"{'=' * 60}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
