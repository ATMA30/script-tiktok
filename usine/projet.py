"""Statut de validation d'un projet : rien n'est rendu sans accord humain.

Le cerveau écrit `script.json["validation"] = {"statut": "a_valider"}` ;
`0_usine.py` affiche le dossier et le passe à "valide" (ou "rejete").

    python -m usine.projet [projets/X]   → code 0 si le projet (défaut : le dernier) est validé
"""

import hashlib
import json
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from usine.garde_fous import noms_propres_hors_brief

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


def empreinte(script):
    """sha256 du contenu validé : narration, prompts, requêtes d'images, garde-fous.

    Toute modification de script.json après validation invalide le projet.
    """
    contenu = {
        "niche": script.get("niche"),
        "visual_bible": script.get("visual_bible"),
        "garde_fous": script.get("garde_fous"),
        "scenes": [
            {
                cle: scene.get(cle)
                for cle in ("audio_tts", "subtitle", "veo_prompt", "real_media_queries")
            }
            for scene in script.get("scenes", [])
        ],
    }
    brut = json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(brut).hexdigest()


def est_valide(projet_dir):
    """Validé ET inchangé depuis la validation."""
    script = lire_script(projet_dir)
    validation = script.get("validation") or {}
    return validation.get("statut") == VALIDE and validation.get(
        "empreinte"
    ) == empreinte(script)


def marquer(projet_dir, statut):
    """Enregistre le statut de validation (avec horodatage) dans script.json."""
    chemin = Path(projet_dir) / "script.json"
    script = lire_script(projet_dir)
    validation = script.get("validation") or {}
    validation["statut"] = statut
    validation[f"{statut}_le"] = datetime.now().isoformat(timespec="seconds")
    if statut == VALIDE:
        validation["empreinte"] = empreinte(script)
    script["validation"] = validation
    chemin.write_text(
        json.dumps(script, indent=4, ensure_ascii=False), encoding="utf-8"
    )


def _lire_brief(projet_dir):
    chemin = Path(projet_dir) / "brief.json"
    if not chemin.exists():
        return {}
    return json.loads(chemin.read_text(encoding="utf-8"))


def _propre(texte):
    """Retire les caractères de contrôle (\\r, séquences ANSI…) d'un texte externe."""
    return "".join(
        c for c in str(texte or "") if not unicodedata.category(c).startswith("C")
    )


def resume_dossier(projet_dir):
    """Texte à relire avant validation : affaire, statut judiciaire, sources, script."""
    script = lire_script(projet_dir)
    brief = _lire_brief(projet_dir)
    p = _propre
    lignes = [
        "═" * 70,
        f"  DOSSIER : {p(brief.get('title') or script.get('niche', '?'))}",
        f"  {p(brief.get('year_or_period', '?'))} · {p(brief.get('location', '?'))}",
        f"  Statut judiciaire : {p(brief.get('statut_judiciaire') or '?')}",
        "═" * 70,
        "",
        "SOURCES DÉCLARÉES PAR LE BRIEF :",
    ]
    for source in brief.get("sources") or []:
        lignes.append(f"  - {p(source.get('name', '?'))} — {p(source.get('url', ''))}")
    if not brief.get("sources"):
        lignes.append("  (aucune)")
    consultees = brief.get("sources_recherche") or []
    lignes.append("")
    lignes.append(
        f"SOURCES RÉELLEMENT CONSULTÉES PAR LA RECHERCHE GOOGLE : {len(consultees)}"
    )
    for source in consultees[:12]:
        lignes.append(f"  - {p(source)}")
    if not consultees:
        lignes.append(
            "  ⚠️ aucune : les sources ci-dessus n'ont pas été vérifiées par la recherche"
        )
    lignes.append("")
    lignes.append("POINTS INCERTAINS (à vérifier) :")
    for flag in brief.get("uncertainty_flags") or ["(aucun)"]:
        lignes.append(f"  - {p(flag)}")

    a_taire = (script.get("garde_fous") or {}).get("personnes_a_taire") or []
    noms_tus = {personne["nom"] for personne in a_taire}
    lignes.append("")
    lignes.append("PERSONNES NOMMABLES (vérifie leur rôle et leur statut) :")
    nommables = [x for x in brief.get("people") or [] if x.get("name") not in noms_tus]
    for personne in nommables:
        drapeaux = (
            ", condamnation définitive"
            if personne.get("condamnation_definitive")
            else ""
        )
        lignes.append(
            f"  - {p(personne.get('name'))} — {p(personne.get('role') or '?')}{drapeaux}"
        )
    if not nommables:
        lignes.append("  (aucune)")
    lignes.append("")
    lignes.append("PERSONNES NON NOMMÉES (mineurs, non condamnés, proches, témoins…) :")
    for personne in a_taire or [{"nom": "(aucune)", "raison": ""}]:
        raison = f" — {personne['raison']}" if personne.get("raison") else ""
        lignes.append(f"  - {p(personne['nom'])}{p(raison)}")

    inconnus = noms_propres_hors_brief(script, brief)
    lignes.append("")
    lignes.append(
        "NOMS PROPRES DU SCRIPT ABSENTS DU BRIEF (lieux ou personnes à vérifier) :"
    )
    lignes.append(f"  {p(', '.join(inconnus)) if inconnus else '(aucun)'}")
    lignes.append("")
    lignes.append("NARRATION :")
    for scene in script.get("scenes", []):
        lignes.append(f"  [{scene.get('id', '?'):>2}] {p(scene.get('audio_tts', ''))}")
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


EXTENSIONS_IMAGE = (".jpg", ".jpeg", ".png", ".webp")


def planche_contact(projet_dir, largeur_vignette=216, colonnes=5):
    """Assemble les images du projet en une planche à relire avant le rendu.

    Renvoie le chemin de planche_contact.jpg, ou None s'il n'y a aucune image.
    """
    from PIL import Image, ImageDraw

    dossier = Path(projet_dir) / "real_media"
    images = sorted(
        p
        for p in dossier.glob("scene_*/*")
        if p.suffix.lower() in EXTENSIONS_IMAGE and ".part" not in p.name
    )
    if not images:
        return None
    hauteur_vignette = largeur_vignette * 16 // 9
    lignes = (len(images) + colonnes - 1) // colonnes
    planche = Image.new(
        "RGB", (colonnes * largeur_vignette, lignes * (hauteur_vignette + 24)), "black"
    )
    dessin = ImageDraw.Draw(planche)
    for i, chemin in enumerate(images):
        x = (i % colonnes) * largeur_vignette
        y = (i // colonnes) * (hauteur_vignette + 24)
        try:
            with Image.open(chemin, formats=("JPEG", "PNG", "WEBP")) as im:
                vignette = im.convert("RGB")
                vignette.thumbnail((largeur_vignette, hauteur_vignette))
                planche.paste(vignette, (x, y))
        except Exception:
            dessin.text((x + 8, y + 8), "illisible", fill="red")
        dessin.text(
            (x + 4, y + hauteur_vignette + 4),
            f"{chemin.parent.name}/{chemin.name}",
            fill="white",
        )
    sortie = Path(projet_dir) / "planche_contact.jpg"
    planche.save(sortie, quality=85)
    return sortie
