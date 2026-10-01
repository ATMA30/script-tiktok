"""
Orchestrateur : vidéos true crime / faits divers, avec validation humaine.

  python 0_usine.py                       → documente une affaire, l'affiche, demande
                                            ta validation, puis produit la vidéo
  python 0_usine.py --sujet "L'affaire …" → impose l'affaire
  python 0_usine.py --n 3                 → enchaîne 3 dossiers
  python 0_usine.py --valider projets/X   → valide un dossier existant et le produit

Rien n'est rendu sans validation : on parle de vraies personnes.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from batch_produce import produire
from usine.projet import REJETE, VALIDE, marquer, resume_dossier, statut_validation

ROOT = Path(__file__).resolve().parent


def _projets_existants():
    dossier = ROOT / "projets"
    return {p for p in dossier.iterdir() if p.is_dir()} if dossier.is_dir() else set()


def generer_dossier(sujet=None):
    """Lance le cerveau et renvoie le chemin du nouveau projet (ou None)."""
    avant = _projets_existants()
    cmd = [sys.executable, "1_generate_brain.py"] + (
        ["--sujet", sujet] if sujet else []
    )
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        return None
    nouveaux = sorted(_projets_existants() - avant, key=lambda p: p.stat().st_mtime)
    return os.path.relpath(nouveaux[-1], ROOT) if nouveaux else None


def demander(question, choix):
    """Pose une question jusqu'à obtenir une des réponses de `choix`."""
    while True:
        reponse = input(f"\n👉 {question} ").strip().lower()[:1]
        if reponse in choix:
            return reponse
        print(f"   Réponds par : {' / '.join(choix)}")


def valider_et_produire(projet):
    marquer(projet, VALIDE)
    print(f"\n✅ Dossier validé : {projet}")
    return produire(projet)


def traiter_un_dossier(sujet=None):
    """Génère un dossier, le soumet à validation, puis produit la vidéo si validé."""
    while True:
        projet = generer_dossier(sujet)
        if not projet:
            print("\n❌ Aucun dossier exploitable n'a pu être généré.")
            return False
        print("\n" + resume_dossier(projet))
        reponse = demander(
            "Valider ce dossier ? [v]alider / [r]égénérer / [a]bandonner >",
            ("v", "r", "a"),
        )
        if reponse == "v":
            return valider_et_produire(projet)
        marquer(projet, REJETE)
        if reponse == "a":
            print(f"\n🗂️  Dossier abandonné (gardé, non validé) : {projet}")
            return False
        print("\n🔁 Nouvelle génération…")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("--sujet", help="Affaire précise (sinon recherche en ligne)")
    ap.add_argument("--n", type=int, default=1, help="Nombre de dossiers à produire")
    ap.add_argument("--valider", metavar="PROJET", help="Valide un dossier existant")
    args = ap.parse_args(argv)

    if args.valider:
        if not (Path(args.valider) / "script.json").exists():
            print(f"❌ Pas de script.json dans {args.valider}")
            return 1
        print(resume_dossier(args.valider))
        statut = statut_validation(args.valider) or "sans statut"
        reponse = demander(
            f"Statut actuel : {statut}. Valider et produire ? [o]ui / [n]on >",
            ("o", "n"),
        )
        if reponse == "n":
            return 0
        return 0 if valider_et_produire(args.valider) else 1

    print("══════════════════════════════════════════════════════")
    print("   🎬 USINE TRUE CRIME / FAITS DIVERS 🎬 ")
    print("══════════════════════════════════════════════════════")
    reussis = sum(traiter_un_dossier(args.sujet) for _ in range(args.n))
    print(f"\n🏁 {reussis}/{args.n} vidéo(s) produite(s).")
    return 0 if reussis == args.n else 1


if __name__ == "__main__":
    sys.exit(main())
