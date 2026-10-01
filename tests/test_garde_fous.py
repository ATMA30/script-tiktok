"""Garde-fous juridiques : liste d'autorisation, mineurs, tous les champs, brief sourcé."""

import pytest

from usine.garde_fous import (
    brief_suffisant,
    nettoyer_requetes,
    personnes_a_taire,
    verifier_script,
)


def _noms(a_taire):
    return {p["nom"] for p in a_taire}


@pytest.mark.parametrize(
    "role",
    [
        "victime",
        "Victime présumée",
        "enquêteur",
        "Inspecteur de police",
        "magistrat",
        "juge d'instruction",
        "Président de la cour d'assises",
        "avocat de la défense",
        "médecin légiste",
    ],
)
def test_roles_nommables(role):
    assert personnes_a_taire([{"name": "Paul Martin", "role": role}]) == []


@pytest.mark.parametrize(
    "role",
    [
        "",
        "suspect",
        "tueur présumé",
        "auteur présumé",
        "meurtrier",
        "complice",
        "mis en examen",
        "gardé à vue",
        "Acquittée en appel",
        "accusé puis condamné",
        "témoin",
        "membre de la famille",
        "fils de la victime",
    ],
)
def test_tout_role_non_autorise_est_tu(role):
    # Liste d'autorisation : un rôle inconnu, vide ou ambigu n'est jamais nommé.
    assert _noms(personnes_a_taire([{"name": "Jean Dufour", "role": role}])) == {
        "Jean Dufour"
    }


def test_condamne_nomme_seulement_si_definitif_pour_cette_personne():
    personnes = [
        {"name": "Marc Lefèvre", "role": "condamné", "condamnation_definitive": True},
        {"name": "Luc Morel", "role": "condamné en première instance"},
        {"name": "Hugo Roy", "role": "condamné", "condamnation_definitive": False},
    ]
    # Le texte libre « non définitive » n'est plus lu : seul le drapeau compte.
    assert _noms(personnes_a_taire(personnes)) == {"Luc Morel", "Hugo Roy"}


def test_mineur_tu_meme_victime_ou_condamne():
    personnes = [
        {"name": "Lucie Bernard", "role": "victime", "mineur": True},
        {"name": "Tom Girard", "role": "enfant de la voisine"},
        {
            "name": "Léo Faure",
            "role": "condamné",
            "condamnation_definitive": True,
            "mineur": True,
        },
    ]
    a_taire = personnes_a_taire(personnes)
    assert _noms(a_taire) == {"Lucie Bernard", "Tom Girard", "Léo Faure"}
    assert all(p["mineur"] for p in a_taire)


def _script(*textes, **champs):
    script = {
        "scenes": [
            {"id": i, "audio_tts": t, "subtitle": t} for i, t in enumerate(textes, 1)
        ]
    }
    script.update(champs)
    return script


A_TAIRE = personnes_a_taire(
    [
        {"name": "Jean Dufour", "role": "mis en examen"},
        {"name": "Lucie Bernard", "role": "victime", "mineur": True},
        {"name": "Anne Roy", "role": "témoin"},
        {"name": "Paul Martin", "role": "victime"},
    ]
)


def test_verifier_script_nom_complet_nom_seul_prenom_de_mineur():
    script = _script(
        "Jean Dufour est interrogé pendant dix heures.",
        "Les enquêteurs reviennent voir DUFOUR.",
        "La petite lucie n'est jamais rentrée.",
        "Madame Roy affirme avoir tout vu.",  # nom de 3 lettres
        "Paul Martin est retrouvé au bord de la route.",  # victime adulte : autorisé
    )
    violations = verifier_script(script, A_TAIRE)
    assert len(violations) == 4
    assert all("Paul Martin" not in v for v in violations)


@pytest.mark.parametrize(
    "champs",
    [
        {"niche": "L'affaire Jean Dufour"},
        {"projet": "Affaire_Jean_Dufour"},
        {"visual_bible": {"Jean Dufour": "tall man, grey coat"}},
        {"visual_bible": {"suspect": "Dufour, tall man"}},
    ],
)
def test_verifier_script_couvre_tous_les_champs(champs):
    assert verifier_script(_script("Un suspect est interrogé.", **champs), A_TAIRE)


def test_verifier_script_veo_prompt():
    script = _script("Un suspect est interrogé.")
    script["scenes"][0]["veo_prompt"] = "Jean Dufour walks in the rain"
    assert verifier_script(script, A_TAIRE)


def test_accents_separateurs_et_ligatures():
    a_taire = personnes_a_taire([{"name": "Jean-Marc Lœuvre", "role": "suspect"}])
    assert verifier_script(_script("Jean Marc LOEUVRE nie tout."), a_taire)
    # Un mot plus long qui contient le nom n'est pas une citation.
    assert not verifier_script(_script("Les loeuvreries ferment."), a_taire)


def test_script_conforme_sans_violation():
    script = _script(
        "Un suspect est interrogé pendant dix heures.",
        "La fillette n'est jamais rentrée.",
        "Paul Martin est retrouvé au bord de la route.",
    )
    assert verifier_script(script, A_TAIRE) == []


def test_nettoyer_requetes_retire_les_personnes_a_taire():
    script = {
        "scenes": [
            {
                "real_media_queries": [
                    "Jean Dufour arrest photo",
                    "Lyon courthouse 1998 press photo",
                ]
            }
        ]
    }
    assert nettoyer_requetes(script, A_TAIRE) == 1
    assert script["scenes"][0]["real_media_queries"] == [
        "Lyon courthouse 1998 press photo"
    ]


def test_brief_suffisant():
    resume = "x" * 120
    sources = [{"name": "Le Monde"}, {"name": "AFP"}]
    assert brief_suffisant({"summary": resume, "sources": sources}) == (True, "")
    assert brief_suffisant({"summary": resume, "sources": sources[:1]})[0] is False
    assert brief_suffisant({"summary": "court", "sources": sources})[0] is False
    assert (
        brief_suffisant({"summary": "HOAX_OR_FICTION", "sources": sources})[0] is False
    )
