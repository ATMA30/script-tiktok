"""Tests unitaires du moteur de rendu : texte, overlays, tag dossier."""

import hashlib

from usine.render import cards
from usine.render.overlays.builders import OVERLAY_BUILDERS
from usine.render.overlays.catalog import SEMANTIC_ANIMATION_TYPES
from usine.render.overlays.detection import detect_overlays
from usine.render.text import emphasize_words, html_escape, split_subtitle


def test_split_subtitle_couvre_toute_la_duree():
    chunks = split_subtitle(
        "Je ne savais pas que cette nuit allait tout changer pour moi et pour elle.",
        4.0,
    )
    assert len(chunks) == 2
    assert chunks[0]["start"] == 0.0
    fin = chunks[-1]["start"] + chunks[-1]["duration"]
    assert abs(fin - 4.0) < 1e-9
    assert all(len(c["text"].split()) <= 8 for c in chunks)


def test_emphasize_words_met_en_valeur_les_mots_dramatiques():
    html = emphasize_words("Elle a disparu dans la nuit")
    assert html == (
        'Elle a <span class="emph">disparu</span> dans la <span class="emph">nuit</span>'
    )


def test_html_escape():
    assert html_escape('<b>"x" & y</b>') == "&lt;b&gt;&quot;x&quot; &amp; y&lt;/b&gt;"


def test_detect_overlays_annee_lieu_et_repli():
    assert detect_overlays("En 1977, tout a commencé.") == [
        {"type": "year_marker", "value": "1977"}
    ]
    lieu = detect_overlays("Je suis parti de paris.")
    assert lieu[0]["type"] == "map_zoom" and lieu[0]["value"] == "PARIS"
    assert detect_overlays("Rien.") == [{"type": "timeline_pin"}]


def test_detect_overlays_limite_a_deux():
    texte = "En 1977 à paris, 47 personnes ont disparu. Pourquoi ?"
    assert len(detect_overlays(texte)) <= 2


def test_chaque_famille_d_overlay_a_un_builder():
    manquants = [t for t in SEMANTIC_ANIMATION_TYPES if t not in OVERLAY_BUILDERS]
    assert manquants == []


def test_tag_dossier_stable(monkeypatch):
    # Régression : hash() est randomisé par processus, l'ID changeait à chaque rendu.
    monkeypatch.setattr(cards, "USE_PERSISTENT_CASE_TAG", True)
    h = int(hashlib.md5(b"20260101_mon_projet").hexdigest(), 16) & 0xFFFFFF
    attendu = f"{h >> 12:03X}-{h & 0xFFF:03X}"
    assert attendu in cards._persistent_case_tag_html("20260101_mon_projet")
