"""Statut de validation d'un projet : rien n'est rendu sans accord humain.

Le cerveau écrit `script.json["validation"] = {"statut": "a_valider"}` ;
`0_usine.py` affiche le dossier et le passe à "valide" (ou "rejete").

    python -m usine.projet [projets/X]   → code 0 si le projet (défaut : le dernier) est validé
"""

import json
import sys
from datetime import datetime
from pathlib import Path

MEMOIRE_SUJETS = Path("projets/.subjects_memory.json")

A_VALIDER = "a_valider"
VALIDE = "valide"
REJETE = "rejete"


def lire_script(projet_dir):
    chemin = Path(projet_dir) / "script.json"
    if not chemin.exists():
        return {}
    return json.loads(chemin.read_text(encoding="utf-8"))


def statut_validation(projet_dir):
    return (lire_script(projet_dir).get("validation") or {}).get("statut")


def est_valide(projet_dir):
    return statut_validation(projet_dir) == VALIDE


def marquer(projet_dir, statut):
    """Enregistre le statut de validation (avec horodatage) dans script.json."""
    chemin = Path(projet_dir) / "script.json"
    script = lire_script(projet_dir)
    validation = script.get("validation") or {}
    validation["statut"] = statut
    validation[f"{statut}_le"] = datetime.now().isoformat(timespec="seconds")
    script["validation"] = validation
    chemin.write_text(
        json.dumps(script, indent=4, ensure_ascii=False), encoding="utf-8"
    )


def _lire_brief(projet_dir):
    chemin = Path(projet_dir) / "brief.json"
    if not chemin.exists():
        return {}
    return json.loads(chemin.read_text(encoding="utf-8"))


def resume_dossier(projet_dir):
    """Texte à relire avant validation : affaire, statut judiciaire, sources, script."""
    script = lire_script(projet_dir)
    brief = _lire_brief(projet_dir)
    lignes = [
        "═" * 70,
        f"  DOSSIER : {brief.get('title') or script.get('niche', '?')}",
        f"  {brief.get('year_or_period', '?')} · {brief.get('location', '?')}",
        f"  Statut judiciaire : {brief.get('statut_judiciaire') or '?'}",
        "═" * 70,
        "",
        "SOURCES :",
    ]
    for source in brief.get("sources") or []:
        lignes.append(f"  - {source.get('name', '?')} — {source.get('url', '')}")
    if not brief.get("sources"):
        lignes.append("  (aucune)")
    lignes.append("")
    lignes.append("POINTS INCERTAINS (à vérifier) :")
    for flag in brief.get("uncertainty_flags") or ["(aucun)"]:
        lignes.append(f"  - {flag}")
    lignes.append("")
    lignes.append("PERSONNES NON NOMMÉES (mineurs, non condamnés) :")
    a_taire = (script.get("garde_fous") or {}).get("personnes_a_taire") or []
    for personne in a_taire or [{"nom": "(aucune)", "raison": ""}]:
        raison = f" — {personne['raison']}" if personne.get("raison") else ""
        lignes.append(f"  - {personne['nom']}{raison}")
    lignes.append("")
    lignes.append("NARRATION :")
    for scene in script.get("scenes", []):
        lignes.append(f"  [{scene.get('id', '?'):>2}] {scene.get('audio_tts', '')}")
    lignes.append("═" * 70)
    return "\n".join(lignes)


def retirer_de_la_memoire(projet_dir, memoire=MEMOIRE_SUJETS):
    """Oublie le sujet d'un dossier rejeté : il pourra être proposé de nouveau."""
    memoire = Path(memoire)
    if not memoire.exists():
        return False
    data = json.loads(memoire.read_text(encoding="utf-8"))
    nom = Path(projet_dir).name
    avant = len(data.get("subjects", []))
    data["subjects"] = [
        s for s in data.get("subjects", []) if s.get("project_id") != nom
    ]
    if len(data["subjects"]) == avant:
        return False
    memoire.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def main(argv):
    from usine.utils import trouver_dernier_projet

    projet = argv[0] if argv else trouver_dernier_projet()
    if not projet or not (Path(projet) / "script.json").exists():
        print(f"❌ Projet introuvable : {projet}")
        return 1
    if est_valide(projet):
        print(f"✅ Projet validé : {projet}")
        return 0
    statut = statut_validation(projet) or "sans statut"
    print(f"⛔ Projet non validé ({statut}) : {projet}")
    print(f"   Relis-le puis : python 0_usine.py --valider {projet}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
