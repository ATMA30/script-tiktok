"""Détection des overlays sémantiques à partir du texte narré (lieux, années, mots-clés)."""

import re
import unicodedata
from usine.render.overlays.catalog import SEMANTIC_META


# ── Semantic overlays : orchestre 40 animations déterministes et adaptatives ──
LOCATIONS_FR = {
    # kw : (label, coords_str, [lng, lat], iso_a3, region)
    "paris": (
        "PARIS",
        "48.8566°N · 2.3522°E",
        [2.3522, 48.8566],
        "FRA",
        "ÎLE-DE-FRANCE",
    ),
    "lille": (
        "LILLE",
        "50.6292°N · 3.0573°E",
        [3.0573, 50.6292],
        "FRA",
        "HAUTS-DE-FRANCE",
    ),
    "lyon": ("LYON", "45.7640°N · 4.8357°E", [4.8357, 45.7640], "FRA", "RHÔNE"),
    "marseille": (
        "MARSEILLE",
        "43.2965°N · 5.3698°E",
        [5.3698, 43.2965],
        "FRA",
        "BOUCHES-DU-RHÔNE",
    ),
    "bordeaux": (
        "BORDEAUX",
        "44.8378°N · 0.5792°W",
        [-0.5792, 44.8378],
        "FRA",
        "GIRONDE",
    ),
    "toulouse": (
        "TOULOUSE",
        "43.6047°N · 1.4442°E",
        [1.4442, 43.6047],
        "FRA",
        "HAUTE-GARONNE",
    ),
    "nantes": (
        "NANTES",
        "47.2184°N · 1.5536°W",
        [-1.5536, 47.2184],
        "FRA",
        "LOIRE-ATLANTIQUE",
    ),
    "nice": (
        "NICE",
        "43.7102°N · 7.2620°E",
        [7.2620, 43.7102],
        "FRA",
        "ALPES-MARITIMES",
    ),
    "strasbourg": (
        "STRASBOURG",
        "48.5734°N · 7.7521°E",
        [7.7521, 48.5734],
        "FRA",
        "BAS-RHIN",
    ),
    "rennes": (
        "RENNES",
        "48.1173°N · 1.6778°W",
        [-1.6778, 48.1173],
        "FRA",
        "ILLE-ET-VILAINE",
    ),
    "montpellier": (
        "MONTPELLIER",
        "43.6108°N · 3.8767°E",
        [3.8767, 43.6108],
        "FRA",
        "HÉRAULT",
    ),
    "calais": (
        "CALAIS",
        "50.9513°N · 1.8587°E",
        [1.8587, 50.9513],
        "FRA",
        "PAS-DE-CALAIS",
    ),
    "bruxelles": (
        "BRUXELLES",
        "50.8503°N · 4.3517°E",
        [4.3517, 50.8503],
        "BEL",
        "BELGIQUE",
    ),
    "brussels": (
        "BRUSSELS",
        "50.8503°N · 4.3517°E",
        [4.3517, 50.8503],
        "BEL",
        "BELGIUM",
    ),
    "londres": (
        "LONDRES",
        "51.5072°N · 0.1276°W",
        [-0.1276, 51.5072],
        "GBR",
        "UNITED KINGDOM",
    ),
    "london": (
        "LONDON",
        "51.5072°N · 0.1276°W",
        [-0.1276, 51.5072],
        "GBR",
        "UNITED KINGDOM",
    ),
    "new york": (
        "NEW YORK",
        "40.7128°N · 74.0060°W",
        [-74.0060, 40.7128],
        "USA",
        "NEW YORK",
    ),
    "columbus": (
        "COLUMBUS",
        "39.9612°N · 82.9988°W",
        [-82.9988, 39.9612],
        "USA",
        "OHIO",
    ),
    "ohio": (
        "OHIO",
        "40.4173°N · 82.9071°W",
        [-82.9071, 40.4173],
        "USA",
        "UNITED STATES",
    ),
    "ugly tuna": (
        "UGLY TUNA",
        "39.9977°N · 83.0086°W",
        [-83.0086, 39.9977],
        "USA",
        "COLUMBUS",
    ),
    "ugly tuna saloona": (
        "UGLY TUNA",
        "39.9977°N · 83.0086°W",
        [-83.0086, 39.9977],
        "USA",
        "COLUMBUS",
    ),
    "nouveau mexique": (
        "NEW MEXICO",
        "34.5000°N · 106.0000°W",
        [-106.0, 34.5],
        "USA",
        "NEW MEXICO",
    ),
    "nouveau-mexique": (
        "NEW MEXICO",
        "34.5000°N · 106.0000°W",
        [-106.0, 34.5],
        "USA",
        "NEW MEXICO",
    ),
    "new mexico": (
        "NEW MEXICO",
        "34.5000°N · 106.0000°W",
        [-106.0, 34.5],
        "USA",
        "NEW MEXICO",
    ),
    "dulce": (
        "DULCE BASE",
        "36.9300°N · 107.0000°W",
        [-107.0, 36.93],
        "USA",
        "NEW MEXICO",
    ),
    "montauk": ("MONTAUK", "41.0700°N · 71.8600°W", [-71.86, 41.07], "USA", "NEW YORK"),
    "roswell": (
        "ROSWELL",
        "33.3943°N · 104.5230°W",
        [-104.5230, 33.3943],
        "USA",
        "NEW MEXICO",
    ),
    "area 51": ("AREA 51", "37.2400°N · 115.8000°W", [-115.80, 37.24], "USA", "NEVADA"),
    "rendlesham": (
        "RENDLESHAM",
        "52.0900°N · 1.4300°E",
        [1.43, 52.09],
        "GBR",
        "SUFFOLK",
    ),
    "tunguska": (
        "TUNGUSKA",
        "60.8900°N · 101.9000°E",
        [101.90, 60.89],
        "RUS",
        "SIBERIA",
    ),
    "antarctique": (
        "ANTARCTICA",
        "82.8600°S · 135.0000°W",
        [-135.0, -82.86],
        "ATA",
        "POLAR",
    ),
    "antarctica": (
        "ANTARCTICA",
        "82.8600°S · 135.0000°W",
        [-135.0, -82.86],
        "ATA",
        "POLAR",
    ),
    "désert": ("DESERT ZONE", "CLASSIFIED", [-106.0, 34.5], "USA", "RESTRICTED"),
    "desert": ("DESERT ZONE", "CLASSIFIED", [-106.0, 34.5], "USA", "RESTRICTED"),
    "atlantique": ("ATLANTIC", "MID-OCEAN RIDGE", [-30.0, 30.0], None, "OCEAN"),
    "pacifique": ("PACIFIC", "MARIANA REGION", [142.0, 11.0], None, "OCEAN"),
    "russie": ("RUSSIA", "SECTOR 7", [60.0, 60.0], "RUS", "EASTERN EUROPE"),
    "états unis": ("USA", "RESTRICTED ZONE", [-100.0, 40.0], "USA", "UNITED STATES"),
    "états-unis": ("USA", "RESTRICTED ZONE", [-100.0, 40.0], "USA", "UNITED STATES"),
}

BIG_NUMBER_WORDS = {
    "milliers": 4823,
    "millier": 4823,
    "centaines": 487,
    "centaine": 487,
    "millions": 1247000,
    "million": 1247000,
    "dizaines": 47,
    "dizaine": 47,
    "douzaine": 12,
}

FRENCH_YEAR_PHRASES = {
    "deux mille six": "2006",
    "deux mille sept": "2007",
    "deux mille huit": "2008",
    "deux mille neuf": "2009",
    "deux mille dix": "2010",
    "mil neuf cent quarante sept": "1947",
    "mille neuf cent quarante sept": "1947",
    "mil neuf cent soixante neuf": "1969",
    "mille neuf cent soixante neuf": "1969",
    "mil neuf cent soixante douze": "1972",
    "mille neuf cent soixante douze": "1972",
    "mil neuf cent soixante dix neuf": "1979",
    "mille neuf cent soixante dix neuf": "1979",
    "mil neuf cent quatre vingt": "1980",
    "mille neuf cent quatre vingt": "1980",
    "mil neuf cent quatre vingt neuf": "1989",
    "mille neuf cent quatre vingt neuf": "1989",
    "mil neuf cent quatre vingt douze": "1992",
    "mille neuf cent quatre vingt douze": "1992",
}

DOSSIER_KW = [
    "dossier",
    "document",
    "documents",
    "preuve",
    "preuves",
    "rapport",
    "fichier",
    "fichiers",
    "archives",
    "archive",
    "indice",
    "indices",
]

REDACTED_KW = [
    "secret",
    "secrets",
    "classifié",
    "classifiée",
    "déclassifié",
    "déclassifiée",
    "interdit",
    "interdite",
    "confidentiel",
    "top secret",
]

ENTITY_KW = [
    "entité",
    "entités",
    "extraterrestre",
    "extraterrestres",
    "alien",
    "aliens",
    "créature",
    "créatures",
    "non-humain",
    "non-humaine",
    "non humaine",
    "ovni",
    "démon",
    "démons",
    "démoniaque",
    "monstre",
    "monstres",
    "hybride",
    "hybrides",
]

SEMANTIC_KEYWORD_RULES = [
    (
        "question_prompt",
        [
            "pensez vous",
            "croyez vous",
            "comment",
            "pourquoi",
            "que pensez",
            "est il",
            "sont ils",
            "êtes vous",
            "etes vous",
        ],
    ),
    (
        "true_story_card",
        [
            "histoire vraie",
            "vrai cas",
            "cas réel",
            "faits réels",
            "temoignage reel",
            "témoignage réel",
        ],
    ),
    (
        "last_seen_marker",
        [
            "dernière fois",
            "derniere fois",
            "jamais revu",
            "plus revu",
            "dernière image",
            "derniere image",
        ],
    ),
    (
        "message_send",
        [
            "message",
            "sms",
            "texto",
            "envoie",
            "envoyer",
            "envoyé",
            "écrit",
            "ecrit",
            "répond",
            "repond",
        ],
    ),
    (
        "phone_call",
        [
            "appel",
            "appelle",
            "appelé",
            "téléphone",
            "telephone",
            "portable",
            "répondeur",
            "repondeur",
        ],
    ),
    ("email_sent", ["email", "e-mail", "mail", "courriel", "inbox"]),
    (
        "cctv_scan",
        [
            "caméra",
            "camera",
            "surveillance",
            "sécurité",
            "securite",
            "filmé",
            "filmée",
            "filme",
            "enregistre",
            "monitor",
        ],
    ),
    (
        "security_log",
        [
            "enregistre",
            "enregistrée",
            "enregistree",
            "filmé",
            "filmee",
            "filmée",
            "ressortir",
        ],
    ),
    (
        "missing_person",
        [
            "disparaît",
            "disparait",
            "disparu",
            "disparue",
            "disparition",
            "introuvable",
            "jamais ressortir",
        ],
    ),
    (
        "missing_poster",
        ["avis de recherche", "personne disparue", "porté disparu", "portee disparue"],
    ),
    (
        "search_grid",
        [
            "cherche",
            "chercher",
            "recherche",
            "recherches",
            "retrouver",
            "fouille",
            "fouilles",
            "inspecté",
            "inspecte",
        ],
    ),
    (
        "searchlight",
        ["organisées", "organisees", "massives", "équipes", "equipes", "ratissage"],
    ),
    ("file_open", DOSSIER_KW),
    (
        "classified_stamp",
        REDACTED_KW + ["gouvernement", "officiel", "officielle", "militaire", "base"],
    ),
    (
        "underground_depth",
        [
            "souterrain",
            "souterraine",
            "profondeur",
            "profondeurs",
            "sous la terre",
            "enfoui",
            "enfouis",
            "bunker",
        ],
    ),
    (
        "basement_elevator",
        ["niveau", "ascenseur", "descend", "descente", "sous sol", "sous-sol"],
    ),
    ("entity_radar", ENTITY_KW),
    (
        "mind_control",
        [
            "contrôle mental",
            "controle mental",
            "psychique",
            "influence",
            "manipulation mentale",
        ],
    ),
    (
        "experiment_chamber",
        [
            "expérience",
            "expériences",
            "experience",
            "experiences",
            "protocole",
            "clandestin",
        ],
    ),
    ("memory_flash", ["souvenir", "mémoire", "memoire", "amnésie", "amnesie"]),
    (
        "radio_signal",
        [
            "signal",
            "signaux",
            "radio",
            "fréquence",
            "frequence",
            "intercepter",
            "intercepte",
            "ondes",
        ],
    ),
    ("voice_print", ["voix", "murmure", "whisper", "chuchotement"]),
    ("audio_waveform", ["sons", "audio", "bruit", "cri", "cris", "silence"]),
    ("room_tone", ["silence", "silencieux", "vide", "calme anormal"]),
    ("floor_plan", ["plan", "plans", "bâtiment", "batiment", "bar", "étage", "etage"]),
    ("exit_scan", ["sortie", "seule sortie", "issue", "ressortir"]),
    (
        "blind_spot",
        [
            "angle mort",
            "zone non filmée",
            "zone non filmee",
            "hors caméra",
            "hors camera",
        ],
    ),
    ("corridor_scan", ["couloir", "corridor", "hallway"]),
    ("door_open", ["porte", "portes", "entrer", "entre"]),
    (
        "route_trace",
        [
            "trajet",
            "itinéraire",
            "itineraire",
            "piste",
            "pistes",
            "chemin",
            "se sépare",
            "se separe",
        ],
    ),
    (
        "interrogation_note",
        [
            "interrogatoire",
            "question",
            "questions",
            "réponse",
            "réponses",
            "reponse",
            "reponses",
            "déclare",
            "declare",
            "dit",
            "témoigne",
            "temoigne",
        ],
    ),
    (
        "witness_card",
        [
            "témoin",
            "témoins",
            "temoin",
            "temoins",
            "affirme",
            "raconte",
            "famille",
            "père",
            "pere",
        ],
    ),
    ("witness_quote", ["témoignage", "témoignages", "temoignage", "temoignages"]),
    ("family_photo", ["famille", "père", "pere", "mère", "mere", "parents"]),
    (
        "clock_tick",
        [
            "heure",
            "heures",
            "matin",
            "soir",
            "minute",
            "minutes",
            "attend",
            "attente",
            "plus tard",
        ],
    ),
    (
        "calendar_flip",
        [
            "avril",
            "janvier",
            "février",
            "fevrier",
            "mars",
            "mai",
            "juin",
            "juillet",
            "août",
            "aout",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
            "decembre",
        ],
    ),
    ("time_jump", ["ans plus tard", "années plus tard", "annees plus tard"]),
    (
        "warning_flash",
        [
            "danger",
            "tragique",
            "accident",
            "peur",
            "horreur",
            "terrifiant",
            "glaçant",
            "glacant",
            "fatal",
        ],
    ),
    (
        "medical_scan",
        [
            "médical",
            "medical",
            "torture",
            "psychique",
            "corps",
            "humain",
            "humaine",
            "âmes",
            "ames",
        ],
    ),
    ("heartbeat_monitor", ["stress", "panique", "respiration", "souffle", "angoisse"]),
    ("dna_spiral", ["adn", "hybride", "hybrides", "biologique"]),
    ("thermal_scan", ["chaleur", "thermique", "température", "temperature"]),
    (
        "lab_sample",
        [
            "expérience",
            "expériences",
            "experience",
            "experiences",
            "échantillon",
            "echantillon",
            "laboratoire",
        ],
    ),
    (
        "newspaper_clip",
        ["journal", "presse", "article", "obituary", "nécrologie", "necrologie"],
    ),
    ("breaking_news", ["révélations", "revelations", "nouvelle", "news", "affaire"]),
    (
        "court_record",
        [
            "police",
            "enquêteur",
            "enquêteurs",
            "enqueteur",
            "enqueteurs",
            "procès",
            "proces",
            "criminel",
        ],
    ),
    (
        "official_denial",
        [
            "nie",
            "dément",
            "dement",
            "version officielle",
            "fantaisie",
            "mythe",
            "mythes",
        ],
    ),
    (
        "document_leak",
        [
            "fuite",
            "révélé",
            "revele",
            "révélations",
            "revelations",
            "document déclassifié",
        ],
    ),
    (
        "coordinates_lock",
        ["coordonnées", "coordonnees", "localisation", "position", "zone"],
    ),
    (
        "footprint_trail",
        ["trace", "traces", "empreinte", "empreintes", "pas", "pied", "pieds"],
    ),
    ("evidence_thread", ["indice", "indices", "preuve", "preuves"]),
    ("case_board", ["hypothèse", "hypotheses", "hypothèse", "théorie", "theorie"]),
    ("theory_stack", ["théories", "theories", "pistes", "explication"]),
    ("blood_trace", ["sang", "cadavre", "blessure", "organique"]),
    ("fire_burst", ["feu", "flamme", "incendie", "brûle", "brule"]),
    ("smoke_fog", ["fumée", "fumee", "brouillard", "brume", "ombre", "ombres"]),
    (
        "storm_warning",
        ["orage", "éclair", "eclair", "tempête", "tempete", "pluie", "vent"],
    ),
    ("weather_alert", ["neige", "froid", "glace", "météo", "meteo"]),
    ("police_lights", ["sirène", "sirene", "patrouille", "gyrophare"]),
    ("key_object", ["objet", "clé", "cle", "photo", "photographie", "lettre"]),
    (
        "timeline_pin",
        ["début", "debut", "avant", "après", "apres", "événement", "evenement"],
    ),
    (
        "timeline_split",
        ["ou peut-être", "ou peut etre", "deux versions", "volontairement"],
    ),
    ("redacted_report", ["caviardé", "caviarde", "censure", "censuré", "censuree"]),
    (
        "archive_box",
        ["archivé", "archive", "archives", "boîte", "boite", "scellé", "scelle"],
    ),
    ("archive_stamp", ["classé", "classe", "scellé", "scelle", "dossier clos"]),
    ("object_isolate", ["objet", "photo", "lettre", "dossier", "fichier"]),
    (
        "proximity_alert",
        [
            "près de vous",
            "pres de vous",
            "ville",
            "centre ville",
            "centre-ville",
            "public",
        ],
    ),
    ("neon_bar", ["bar", "soirée", "soiree", "amis", "boire"]),
    ("power_cut", ["lumière", "lumiere", "ampoule", "éteint", "eteint"]),
    ("crowd_noise", ["foule", "amis", "témoins", "temoins", "bar animé", "bar anime"]),
    ("sealed_door", ["porte scellée", "porte scellee", "accès refusé", "acces refuse"]),
]


def _fold_text(value):
    value = str(value or "").replace("’", "'").replace("œ", "oe")
    value = re.sub(r"[\u2010-\u2015\-]+", " ", value)
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip()


def _kw_pattern(keyword):
    key = re.escape(_fold_text(keyword))
    return rf"(?<!\w){key}(?!\w)"


def _has_keyword(text_folded, keywords):
    return any(re.search(_kw_pattern(kw), text_folded) for kw in keywords)


def _extract_year_value(text, text_folded):
    match = re.search(r"\b(19[0-9]\d|20[0-3]\d)\b", text)
    if match:
        return match.group(0)
    for phrase, year in sorted(
        FRENCH_YEAR_PHRASES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if re.search(_kw_pattern(phrase), text_folded):
            return year
    return None


def _location_tuple(data):
    if len(data) == 4:
        label, coords, lnglat, iso = data
        return label, coords, lnglat, iso, ""
    return data


def _location_matches(text_folded):
    matches = []
    seen = set()
    for kw, data in LOCATIONS_FR.items():
        match = re.search(_kw_pattern(kw), text_folded)
        if not match:
            continue
        label, coords, lnglat, iso, region = _location_tuple(data)
        if label in seen:
            continue
        seen.add(label)
        matches.append(
            {
                "type": "map_zoom",
                "value": label,
                "coords": coords,
                "lnglat": lnglat,
                "iso": iso,
                "region": region,
                "keyword": kw,
                "_pos": match.start(),
            }
        )
    return sorted(matches, key=lambda item: (item["_pos"], -len(item["keyword"])))


def _message_preview(text):
    quoted = re.search(r"[\"«“](.{4,72}?)[\"»”]", text)
    if quoted:
        return quoted.group(1).strip()
    cleaned = re.sub(r"\s+", " ", text).strip(" .…")
    words = cleaned.split()
    if len(words) > 9:
        cleaned = " ".join(words[:9]) + "..."
    return cleaned or "Message envoyé."


def _counter_from_text(text, text_folded, year_found=None):
    for kw, default in BIG_NUMBER_WORDS.items():
        if re.search(_kw_pattern(kw), text_folded):
            return default
    for num_match in re.finditer(r"\b(\d{2,})\b", text):
        val = int(num_match.group(0))
        if year_found and str(val) == str(year_found):
            continue
        if 10 < val < 10_000_000:
            return val
    return None


def _visual_bible_person(text_folded, visual_bible):
    if not visual_bible:
        return None
    for key, desc in visual_bible.items():
        candidates = []
        if (
            isinstance(key, str)
            and not key.lower().startswith("lieu")
            and not key.lower().startswith("objet")
        ):
            candidates.append(key)
        if isinstance(desc, str):
            candidates.append(desc.split(",", 1)[0].strip())
        for candidate in candidates:
            parts = [p for p in re.split(r"\s+", candidate.strip()) if p]
            if len(parts) < 2:
                continue
            full_name = " ".join(parts[:2])
            last_name = parts[-1]
            if _fold_text(full_name) in text_folded or re.search(
                _kw_pattern(last_name), text_folded
            ):
                return {
                    "type": "witness_card",
                    "value": full_name,
                    "role": _extract_role(desc),
                }
    return None


def _add_overlay(overlays, spec, limit=2):
    if len(overlays) >= limit:
        return False
    otype = spec.get("type")
    if not otype or any(item.get("type") == otype for item in overlays):
        return False
    if otype not in SEMANTIC_META:
        return False
    overlays.append(spec)
    return True


def detect_overlays(text, visual_bible=None, scene_idx=None):
    """Retourne au plus deux overlays par scène, choisis dans 80 familles adaptatives."""
    text = text or ""
    text_folded = _fold_text(text)
    overlays = []

    if _has_keyword(
        text_folded,
        [
            "pensez vous",
            "croyez vous",
            "comment",
            "pourquoi",
            "que pensez",
            "est il",
            "sont ils",
        ],
    ):
        _add_overlay(overlays, {"type": "question_prompt", "value": "À VOUS DE JUGER"})

    locs = _location_matches(text_folded)
    location_is_project_name = _has_keyword(
        text_folded, ["projets montauk", "projet montauk"]
    )
    scene_needs_non_geo = _has_keyword(
        text_folded,
        [
            "controle mental",
            "contrôle mental",
            "voyage temporel",
            "voyages temporels",
            "temoignent",
            "témoignent",
            "experiences horribles",
            "expériences horribles",
        ],
    )
    should_use_location = bool(locs) and not (
        scene_idx is not None
        and scene_idx >= 3
        and location_is_project_name
        and scene_needs_non_geo
    )
    if should_use_location and len(overlays) < 2:
        primary = {k: v for k, v in locs[0].items() if k != "_pos"}
        primary["detail"] = f"{primary.get('region') or primary.get('coords')}"
        if len(locs) > 1:
            primary["route_label"] = " → ".join(loc["value"] for loc in locs[:3])
            primary["route_count"] = len(locs)
        if _has_keyword(
            text_folded,
            ["souterrain", "souterraine", "sous la terre", "profondeur", "profondeurs"],
        ):
            primary["badge"] = "SOUS-SOL / PROFONDEUR ESTIMÉE"
        _add_overlay(overlays, primary)

    for otype, keywords in SEMANTIC_KEYWORD_RULES:
        if len(overlays) >= 2:
            break
        if not _has_keyword(text_folded, keywords):
            continue
        spec = {"type": otype}
        if otype == "message_send":
            spec["body"] = _message_preview(text)
        elif otype == "question_prompt":
            spec["value"] = "À VOUS DE JUGER"
        elif otype in ("missing_person", "missing_poster", "last_seen_marker"):
            spec["type"] = "missing_poster" if otype == "missing_person" else otype
        elif otype == "file_open":
            spec["detail"] = "Indice ajouté au dossier"
        _add_overlay(overlays, spec)

    year_found = _extract_year_value(text, text_folded)
    if year_found:
        _add_overlay(overlays, {"type": "year_marker", "value": year_found})

    counter_value = _counter_from_text(text, text_folded, year_found=year_found)
    if counter_value:
        _add_overlay(overlays, {"type": "counter", "value": counter_value})

    person_spec = _visual_bible_person(text_folded, visual_bible)
    if person_spec:
        _add_overlay(overlays, person_spec)

    if not overlays and _has_keyword(text_folded, REDACTED_KW):
        _add_overlay(overlays, {"type": "classified_stamp"})
    if not overlays:
        _add_overlay(overlays, {"type": "timeline_pin"})

    return overlays[:2]


def _extract_role(desc):
    """Extrait un rôle court depuis la description visual_bible (ex: 'geologist', 'security guard')."""
    # Cherche les mots-clés métier après la virgule
    after_comma = desc.split(",", 1)[1] if "," in desc else desc
    role_keywords = re.findall(
        r"\b(geologist|engineer|guard|scientist|soldier|witness|"
        r"géologue|ingénieur|garde|scientifique|soldat|témoin|"
        r"pilote|policier|détective|médecin|agent|chercheur)\b",
        after_comma,
        re.IGNORECASE,
    )
    if role_keywords:
        return role_keywords[0].upper()
    return "WITNESS"
