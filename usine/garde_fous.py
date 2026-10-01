"""Garde-fous juridiques du true crime : présomption d'innocence et protection des mineurs.

Le cerveau (1_generate_brain.py) les applique au brief puis au script généré.
La validation humaine (0_usine.py) reste le dernier filet : ces contrôles
attrapent les noms, pas les formulations ni les périphrases.

Règle de nommage par LISTE D'AUTORISATION (tout ce qui n'est pas autorisé est tu) :
- nommables : victimes adultes, enquêteurs, magistrats, avocats, experts ;
- condamnés : seulement si `condamnation_definitive` est vrai pour CETTE personne ;
- jamais : mineurs (prénom compris), suspects, mis en examen, acquittés, témoins,
  proches, et tout rôle absent ou non reconnu.
Pas de script sans brief sourcé.
"""

import re
import unicodedata

MIN_SOURCES = 2
MIN_RESUME = 80

# Débuts de rôle (sans accents, minuscules) qu'on peut nommer.
ROLES_NOMMABLES = (
    "victime",
    "enqueteur",
    "enquetrice",
    "policier",
    "policiere",
    "gendarme",
    "inspecteur",
    "inspectrice",
    "commissaire",
    "magistrat",
    "juge",
    "procureur",
    "procureure",
    "president",
    "presidente",
    "avocat",
    "avocate",
    "expert",
    "experte",
    "medecin legiste",
)
ROLE_CONDAMNE = "condamn"
MOTS_MINEURS = ("mineur", "bebe", "nourrisson")
DEBUTS_MINEURS = (
    "enfant",
    "fillette",
    "adolescent",
    "garcon",
    "ecolier",
    "collegien",
    "lyceen",
)


def plier(texte):
    """Minuscules sans accents (œ → oe), pour comparer des noms et des rôles."""
    texte = (texte or "").replace("œ", "oe").replace("Œ", "Oe").replace("ß", "ss")
    nfkd = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _est_mineur(personne, role):
    return (
        bool(personne.get("mineur"))
        or any(m in role for m in MOTS_MINEURS)
        or (role.startswith(DEBUTS_MINEURS))
    )


def personnes_a_taire(personnes):
    """Liste des personnes à ne jamais nommer, avec la raison.

    `personnes` : dicts {"name", "role", "mineur", "condamnation_definitive"} du brief.
    """
    a_taire = []
    for personne in personnes or []:
        nom = (personne.get("name") or "").strip()
        if not nom:
            continue
        role = plier(personne.get("role", "")).strip()
        if _est_mineur(personne, role):
            raison, mineur = "mineur", True
        elif role.startswith(ROLE_CONDAMNE):
            if personne.get("condamnation_definitive") is True:
                continue
            raison, mineur = "condamnation non définitive ou non attestée", False
        elif role.startswith(ROLES_NOMMABLES):
            continue
        else:
            raison, mineur = f"rôle « {role or 'non précisé'} » non nommable", False
        a_taire.append({"nom": nom, "raison": raison, "mineur": mineur})
    return a_taire


def _motifs(personne):
    """Nom complet, nom de famille seul (≥ 3 lettres) et, pour un mineur, prénom seul."""
    plie = plier(personne["nom"])
    morceaux = [m for m in re.split(r"[\s\-'’]+", plie) if m]
    variantes = {" ".join(morceaux)} if morceaux else set()
    if len(morceaux) >= 2 and len(morceaux[-1]) >= 3:
        variantes.add(morceaux[-1])
    if personne["mineur"] and morceaux and len(morceaux[0]) >= 3:
        variantes.add(morceaux[0])
    motifs = []
    for variante in variantes:
        # Les séparateurs du nom (espace, tiret, apostrophe) sont interchangeables.
        corps = r"[\s\-'’]+".join(re.escape(m) for m in variante.split(" "))
        motifs.append(re.compile(r"(?<!\w)" + corps + r"(?!\w)"))
    return motifs


def _cite(texte, personne):
    plie = plier(texte)
    return any(motif.search(plie) for motif in _motifs(personne))


def textes_du_script(script):
    """Tous les champs texte d'un script, avec leur emplacement (sauf requêtes d'images)."""
    textes = [
        ("titre", script.get("niche", "")),
        ("nom du projet", (script.get("projet") or "").replace("_", " ")),
    ]
    bible = script.get("visual_bible") or {}
    # Réponse brute de Gemini : liste de {name, description} ; script final : dict.
    entrees = (
        bible.items()
        if isinstance(bible, dict)
        else (
            (e.get("name", ""), e.get("description", ""))
            for e in bible
            if isinstance(e, dict)
        )
    )
    for cle, valeur in entrees:
        textes.append(("bible visuelle", f"{cle} {valeur}"))
    for i, scene in enumerate(script.get("scenes", []), 1):
        lieu = f"scène {scene.get('id', i)}"
        for champ in ("audio_tts", "subtitle", "veo_prompt", "lyria_prompt"):
            textes.append((lieu, scene.get(champ, "")))
    return textes


def verifier_script(script, a_taire):
    """Violations : une personne à taire est citée n'importe où dans le script."""
    violations = []
    for lieu, texte in textes_du_script(script):
        for personne in a_taire:
            if texte and _cite(texte, personne):
                violation = (
                    f"{lieu} : « {personne['nom']} » ({personne['raison']}) "
                    f"ne doit pas être nommé"
                )
                if violation not in violations:
                    violations.append(violation)
    return violations


def nettoyer_requetes(script, a_taire):
    """Retire les requêtes d'images qui visent une personne à taire (droit à l'image).

    Renvoie le nombre de requêtes retirées.
    """
    retirees = 0
    for scene in script.get("scenes", []):
        requetes = scene.get("real_media_queries") or []
        gardees = [q for q in requetes if not any(_cite(q, p) for p in a_taire)]
        retirees += len(requetes) - len(gardees)
        scene["real_media_queries"] = gardees
    return retirees


def brief_suffisant(brief):
    """(ok, raison) : un brief exploitable est sourcé, assez détaillé et pas un canular."""
    resume = brief.get("summary") or ""
    if "HOAX_OR_FICTION" in resume:
        return False, "canular ou fiction selon la recherche"
    sources = brief.get("sources") or []
    if len(sources) < MIN_SOURCES:
        return False, f"{len(sources)} source(s), il en faut au moins {MIN_SOURCES}"
    if len(resume) < MIN_RESUME:
        return False, f"résumé trop court ({len(resume)} caractères)"
    return True, ""
