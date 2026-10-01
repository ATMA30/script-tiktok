"""Garde-fous juridiques : présomption d'innocence, mineurs, brief sourcé."""

from usine.garde_fous import (
    brief_suffisant,
    nettoyer_requetes,
    personnes_a_taire,
    verifier_script,
)

PERSONNES = [
    {"name": "Paul Martin", "role": "victime"},
    {"name": "Lucie Bernard", "role": "victime", "mineur": True},
    {"name": "Jean Dufour", "role": "mis en examen"},
    {"name": "Marc Lefèvre", "role": "condamné"},
    {"name": "Anne Roux", "role": "Acquittée en appel"},
    {"name": "Hugo Petit", "role": "enfant de la victime"},
    {"name": "Claire Moreau", "role": "enquêtrice"},
]


def _noms(a_taire):
    return {p["nom"] for p in a_taire}


def test_personnes_a_taire_sans_condamnation_definitive():
    a_taire = personnes_a_taire(PERSONNES, "jugé en première instance, appel en cours")
    assert _noms(a_taire) == {
        "Lucie Bernard",
        "Jean Dufour",
        "Marc Lefèvre",
        "Anne Roux",
        "Hugo Petit",
    }


def test_condamne_definitivement_peut_etre_nomme():
    a_taire = personnes_a_taire(PERSONNES, "Condamnation définitive")
    assert "Marc Lefèvre" not in _noms(a_taire)
    assert "Jean Dufour" in _noms(a_taire)  # toujours pas condamné


def _script(*textes):
    return {
        "scenes": [
            {"id": i, "audio_tts": t, "subtitle": t} for i, t in enumerate(textes, 1)
        ]
    }


def test_verifier_script_detecte_nom_complet_nom_seul_et_prenom_de_mineur():
    a_taire = personnes_a_taire(PERSONNES, "instruction en cours")
    script = _script(
        "Jean Dufour est interrogé pendant dix heures.",
        "Les enquêteurs reviennent voir DUFOUR.",
        "La petite lucie n'est jamais rentrée.",
        "Paul Martin est retrouvé au bord de la route.",
    )
    violations = verifier_script(script, a_taire)
    assert len(violations) == 3
    assert all("Paul Martin" not in v for v in violations)


def test_verifier_script_ignore_accents_et_mots_partiels():
    a_taire = personnes_a_taire([{"name": "Marc Lefèvre", "role": "condamné"}], "")
    assert verifier_script(_script("Marc LEFEVRE nie tout."), a_taire)
    # « Lefèvrement » n'est pas le nom : pas de faux positif sur un mot plus long.
    assert not verifier_script(_script("Il parle lefèvrement."), a_taire)


def test_script_conforme_sans_violation():
    a_taire = personnes_a_taire(PERSONNES, "instruction en cours")
    script = _script(
        "Un suspect est interrogé pendant dix heures.",
        "La fillette n'est jamais rentrée.",
    )
    assert verifier_script(script, a_taire) == []


def test_nettoyer_requetes_retire_les_personnes_a_taire():
    a_taire = personnes_a_taire(PERSONNES, "instruction en cours")
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
    assert nettoyer_requetes(script, a_taire) == 1
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
