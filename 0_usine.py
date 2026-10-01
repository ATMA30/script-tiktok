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
import subprocess
import sys
import tempfile
from pathlib import Path

from batch_produce import ETAPES, produire
from usine.projet import (
    REJETE,
    VALIDE,
    marquer,
    planche_contact,
    resume_dossier,
    retirer_de_la_memoire,
    statut_validation,
)

ROOT = Path(__file__).resolve().parent


def generer_dossier(sujet=None):
    """Lance le cerveau et renvoie le chemin du nouveau projet (ou None)."""
    with tempfile.TemporaryDirectory() as tmp:
        sortie = Path(tmp) / "projet.txt"
        cmd = [sys.executable, "1_generate_brain.py", "--sortie", str(sortie)]
        if sujet:
            cmd += ["--sujet", sujet]
        if subprocess.run(cmd, cwd=ROOT).returncode != 0 or not sortie.exists():
            return None
        chemin = sortie.read_text(encoding="utf-8").strip()
        return str(ROOT / chemin) if chemin else None


# Réponses acceptées, en mot entier : « voir le détail » ne valide rien.
REPONSES = {
    "valider": {"v", "valider", "o", "oui"},
    "regenerer": {"r", "regenerer", "régénérer"},
    "abandonner": {"a", "abandonner", "n", "non"},
}


def demander(question, choix):
    """Pose la question jusqu'à une réponse de `choix` (clés de REPONSES).

    Renvoie None si l'entrée est fermée (mode non interactif) ou interrompue.
    """
    while True:
        try:
            saisie = input(f"\n👉 {question} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n⏸️  Pas de réponse : le dossier reste « a_valider ».")
            return None
        for cle in choix:
            if saisie in REPONSES[cle]:
                return cle
        print(
            f"   Réponds par : {' / '.join(sorted(min(REPONSES[c], key=len) for c in choix))}"
        )


def ouvrir_image(chemin):
    """Ouvre l'image dans la visionneuse du système (macOS), sans bloquer."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(chemin)], check=False)


def valider_et_produire(projet):
    """Valide le dossier, prépare les médias, fait relire les images, puis rend."""
    marquer(projet, VALIDE)
    print(f"\n✅ Dossier validé : {projet}")
    if not produire(projet, ETAPES[:-1]):
        return False
    # Les images viennent du web APRÈS la validation du texte : elles se relisent aussi.
    planche = planche_contact(projet)
    if planche:
        print(f"\n🖼️  Planche-contact des images : {planche}")
        ouvrir_image(planche)
        reponse = demander(
            "Images OK (aucun visage de suspect ou de mineur, rien de déplacé) ? "
            "[v]alider / [a]bandonner >",
            ("valider", "abandonner"),
        )
        if reponse != "valider":
            print(
                "\n⏸️  Rendu non lancé. Remplace ou supprime les images concernées dans "
                f"{projet}/real_media/, puis : python 3_render_hyperframes.py --projet {projet}"
            )
            return False
    return produire(projet, ETAPES[-1:])


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
            ("valider", "regenerer", "abandonner"),
        )
        if reponse is None:
            print(f"   Plus tard : python 0_usine.py --valider {projet}")
            return False
        if reponse == "valider":
            return valider_et_produire(projet)
        marquer(projet, REJETE)
        retirer_de_la_memoire(projet, ROOT / "projets" / ".subjects_memory.json")
        if reponse == "abandonner":
            print(f"\n🗂️  Dossier abandonné (gardé, non validé) : {projet}")
            return False
        print("\n🔁 Nouvelle génération…")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("--sujet", help="Affaire précise (sinon recherche en ligne)")
    ap.add_argument(
        "--n", type=int, default=1, help="Nombre de dossiers à produire (≥ 1)"
    )
    ap.add_argument("--valider", metavar="PROJET", help="Valide un dossier existant")
    args = ap.parse_args(argv)
    if args.n < 1:
        ap.error("--n doit valoir au moins 1")

    if args.valider:
        if not (Path(args.valider) / "script.json").exists():
            print(f"❌ Pas de script.json dans {args.valider}")
            return 1
        print(resume_dossier(args.valider))
        statut = statut_validation(args.valider) or "sans statut"
        reponse = demander(
            f"Statut actuel : {statut}. Valider et produire ? [o]ui / [n]on >",
            ("valider", "abandonner"),
        )
        if reponse is None:
            return 1
        if reponse == "abandonner":
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
