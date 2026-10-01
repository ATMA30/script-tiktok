"""Garde-fous juridiques du true crime : présomption d'innocence et protection des mineurs.

Le cerveau (1_generate_brain.py) les applique au brief puis au script généré.
La validation humaine (0_usine.py) reste le dernier filet : ces contrôles
attrapent les noms, pas les formulations.

Règles :
- un mineur n'est jamais nommé (prénom compris) ;
- une personne soupçonnée, mise en examen, acquittée ou relaxée n'est jamais nommée ;
- un condamné n'est nommé que si la condamnation est définitive ;
- pas de script sans brief sourcé.
"""

import re
import unicodedata

MIN_SOURCES = 2
MIN_RESUME = 80

# Rôles (sans accents, minuscules) qui interdisent de nommer la personne.
ROLES_MINEURS = ("mineur", "enfant", "adolescent", "bebe", "nourrisson", "fillette")
ROLES_NON_CONDAMNES = (
    "suspect",
    "soupcon",
    "mis en examen",
    "mise en examen",
    "mis en cause",
    "mise en cause",
    "accus",
    "prevenu",
    "inculp",
    "acquitt",
    "relax",
    "non-lieu",
    "non lieu",
)


def plier(texte):
    """Minuscules sans accents, pour comparer des noms et des rôles."""
    nfkd = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def condamnation_definitive(statut_judiciaire):
    return "definitiv" in plier(statut_judiciaire)


def personnes_a_taire(personnes, statut_judiciaire):
    """Liste des personnes à ne jamais nommer, avec la raison.

    `personnes` : dicts {"name", "role", "mineur"} issus du brief.
    """
    definitive = condamnation_definitive(statut_judiciaire)
    a_taire = []
    for personne in personnes or []:
        nom = (personne.get("name") or "").strip()
        if not nom:
            continue
        role = plier(personne.get("role", ""))
        if personne.get("mineur") or any(m in role for m in ROLES_MINEURS):
            a_taire.append({"nom": nom, "raison": "mineur", "mineur": True})
        elif any(r in role for r in ROLES_NON_CONDAMNES):
            a_taire.append({"nom": nom, "raison": "non condamné", "mineur": False})
        elif "condamn" in role and not definitive:
            raison = "condamnation non définitive"
            a_taire.append({"nom": nom, "raison": raison, "mineur": False})
    return a_taire


def _motifs(personne):
    """Nom complet, nom de famille seul (≥ 4 lettres) et, pour un mineur, prénom seul."""
    plie = plier(personne["nom"])
    morceaux = [m for m in re.split(r"[\s\-']+", plie) if m]
    variantes = {plie}
    if len(morceaux) >= 2 and len(morceaux[-1]) >= 4:
        variantes.add(morceaux[-1])
    if personne["mineur"] and morceaux and len(morceaux[0]) >= 3:
        variantes.add(morceaux[0])
    return [re.compile(r"(?<!\w)" + re.escape(v) + r"(?!\w)") for v in variantes]


def _cite(texte, personne):
    plie = plier(texte)
    return any(motif.search(plie) for motif in _motifs(personne))


def verifier_script(script, a_taire):
    """Violations : une personne à taire est citée dans la narration ou les sous-titres."""
    violations = []
    for i, scene in enumerate(script.get("scenes", []), 1):
        texte = f"{scene.get('audio_tts', '')} {scene.get('subtitle', '')}"
        for personne in a_taire:
            if _cite(texte, personne):
                violations.append(
                    f"scène {scene.get('id', i)} : « {personne['nom']} » "
                    f"({personne['raison']}) ne doit pas être nommé"
                )
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
