"""Requêtes de recherche : mots-clés, rôle éditorial de chaque plan (archive ou reconstitution)."""

import re
from usine.media import config as media_config
from usine.media.config import (
    MEDIA_MIX_MODE,
    REAL_MEDIA_ONLY,
    SMART_MIX_OVERRIDES,
    STYLE_SUFFIX_LOW_POLY_3D,
    gemini_client,
)

try:
    from google.genai import types
except (
    ImportError
):  # SDK absent : gemini_client vaut None et les appels Gemini sont ignorés
    types = None


# ═══════════════════════════════════════════════════════════════════════════════
#  METAPHORISATION GEMINI (Contournement Filtres de Sécurité)
# ═══════════════════════════════════════════════════════════════════════════════
def metaphoriser_prompt_avec_gemini(prompt_original: str) -> str:
    """
    Traduit un prompt potentiellement sensible en une métaphore visuelle sombre et artistique,
    excluant les termes bloqués par Imagen 4 (mort, cadavre, sang, armes, violence, personnes réelles).
    """
    if not gemini_client:
        return prompt_original

    if media_config.STYLE_SUFFIX == STYLE_SUFFIX_LOW_POLY_3D:
        style_rules = """- Style: cinematic 3D low-poly render, faceted polygon geometry, realistic depth of field, volumetric fog, cold desaturated blue-gray lighting.
- Characters: angular low-poly silhouettes or semi-realistic polygonal figures, described by posture/gesture only.
- Environment: cinematic, smoky, full-frame 3D scene with strong foreground subject and blurred atmospheric background."""
    else:
        style_rules = """- Style: Studio Ghibli anime illustration. Warm lamp or lantern light against deep blue night sky.
- Characters: semi-realistic, expressive faces, described by posture/gesture only (no face close-ups for the narrator).
- Environment: richly detailed hand-painted backgrounds. Contemporary indoor or outdoor night setting.
- Lighting: always a warm artificial light source (lamp, glowing window, lantern) contrasting with cool blue exterior."""

    system_instruction = f"""You are a creative prompt engineer for Imagen 4.
Your task is to rewrite a scene description into a safe, vivid visual prompt.

Rules:
{style_rules}
- Never name real people. Use "a young man seen from behind", "a woman by a window", "two figures at a table".
- Keep it SHORT (2-3 sentences max). Visual terms only. No technical instructions.
- Return ONLY the raw English prompt string, no quotes, no explanation."""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Translate this prompt into a safe, atmospheric metaphor: {prompt_original}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.75,
                max_output_tokens=160,
            ),
        )
        metaphor = response.text.strip()
        print(
            f"      🔮 Métaphore générée :\n         Original : {prompt_original[:60]}...\n         Traduit  : {metaphor}"
        )
        return metaphor
    except Exception as e:
        print(f"      ⚠️ Échec de la métaphorisation : {e}")
        return prompt_original


def obtenir_mots_cles_contexte(niche: str) -> str:
    """Extrait le nom principal de l'affaire ou de l'événement en anglais (ex: 'Enfield Poltergeist 1977')."""
    niche_l = (niche or "").lower()
    if any(
        token in niche_l
        for token in (
            "yuba",
            "madruga",
            "mathias",
            "weiher",
            "sterling",
            "huett",
            "plumas",
            "montego",
        )
    ):
        return "Yuba County Five"
    if "enfield" in niche_l:
        return "Enfield Poltergeist"
    if not gemini_client or not niche:
        return ""
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Extract the main historical case name, location or event name in English (maximum 3-4 words) from this niche: {niche}",
            config=types.GenerateContentConfig(
                system_instruction="Return ONLY the English name of the case or event. No quotes, no intro, no punctuation.",
                temperature=0.2,
                max_output_tokens=15,
            ),
        )
        ctx = (response.text or "").strip().replace('"', "")
        if not ctx:
            return ""
        print(f"      🔍 Contexte historique extrait de la niche : '{ctx}'")
        return ctx
    except Exception as e:
        print(f"      ⚠️ Échec extraction contexte : {e}")
        return ""


def enrichir_requete_archive(query: str, contexte_niche: str = "") -> str:
    """Construit une requête moins vague pour limiter les faux positifs Bing."""
    q = re.sub(r"\s+", " ", query or "").strip()
    ctx = re.sub(r"\s+", " ", contexte_niche or "").strip()
    ctx_words = [w.lower() for w in re.findall(r"[a-zA-Z]+", ctx) if len(w) > 3]
    q_lower = q.lower()
    if ctx and not all(w in q_lower for w in ctx_words):
        q = f"{ctx} {q}"
    if "yuba" in q.lower() and "county" not in q.lower():
        q = f"Yuba County Five {q}"
    elif "enfield" in q.lower() and "poltergeist" not in q.lower():
        q = f"Enfield Poltergeist {q}"

    archive_terms = ["archive", "newspaper", "documentary", "photograph"]
    q_lower = q.lower()
    for term in archive_terms:
        if term not in q_lower:
            q = f"{q} {term}"
            break
    return q.strip()


def requete_affaire_specifique(
    query: str, contexte_niche: str = "", context_histoire: str = ""
) -> bool:
    """Évite les requêtes atmosphériques vagues en mode vrais médias."""
    haystack = (query or "").lower()
    case_tokens = {
        "enfield",
        "poltergeist",
        "hodgson",
        "janet",
        "peggy",
        "margaret",
        "maurice",
        "grosse",
        "playfair",
        "green street",
        "daily mirror",
        "police report",
        "paranormal evidence",
        "yuba",
        "madruga",
        "mathias",
        "weiher",
        "sterling",
        "huett",
        "plumas",
        "montego",
        "joe schons",
        "forest service trailer",
    }
    return any(tok in haystack for tok in case_tokens)


def choisir_role_media(
    scene_key: str,
    plan_index: int,
    plan: dict,
    contexte_niche: str = "",
    context_histoire: str = "",
) -> str:
    """Choisit si un plan doit utiliser une archive réelle ou une reconstitution générée."""
    if REAL_MEDIA_ONLY:
        return "real"
    if MEDIA_MIX_MODE in {"real", "archive", "archives"}:
        return "real"
    if MEDIA_MIX_MODE in {"generated", "generate", "imagen"}:
        return "generated"
    if MEDIA_MIX_MODE in {"smart", "mix", "mixed", "editorial"}:
        forced_scene = SMART_MIX_OVERRIDES.get(scene_key, [])
        if plan_index < len(forced_scene):
            return forced_scene[plan_index]

    text = " ".join(
        [
            plan.get("text_segment", ""),
            plan.get("veo_prompt", ""),
            " ".join(plan.get("real_media_queries", []) or []),
            contexte_niche or "",
        ]
    ).lower()

    real_score = 0
    generated_score = 0
    real_terms = [
        "photo",
        "photos",
        "photograph",
        "archive",
        "archives",
        "evidence",
        "preuve",
        "report",
        "police",
        "media coverage",
        "journal",
        "newspaper",
        "maison",
        "house",
        "bedroom",
        "chambre",
        "famille",
        "family",
        "hodgson",
        "janet",
        "peggy",
        "margaret",
        "maurice",
        "grosse",
        "playfair",
        "1977",
        "enfield",
        "levitation",
        "lévit",
        "chaise",
        "chair",
        "objects",
        "objets",
    ]
    generated_terms = [
        "voix",
        "voice",
        "entité",
        "entity",
        "malveillante",
        "shadowy",
        "figure",
        "silhouette",
        "cauchemar",
        "nightmare",
        "mystère",
        "mystery",
        "sombre",
        "dark",
        "seul chez",
        "glacer le sang",
        "quelque chose",
        "farce élaborée",
        "whispers",
        "low hum",
        "fear",
        "peur",
        "coups secs",
        "knocking sounds",
        "ce qui s'est passé",
        "ce qui s’est passé",
        "présence",
        "presence",
        "atmosphere",
        "atmosphère",
        "tension",
        "unseen",
        "invisible",
    ]
    for term in real_terms:
        if term in text:
            real_score += 1
    for term in generated_terms:
        if term in text:
            generated_score += 1

    text_only = (plan.get("text_segment", "") or "").lower()
    strong_real_text = any(
        term in text_only
        for term in [
            "photo",
            "photos",
            "photograph",
            "preuve",
            "preuves",
            "evidence",
            "police",
            "agents",
            "report",
            "rapport",
            "janet",
            "hodgson",
            "peggy",
            "maurice",
            "grosse",
            "playfair",
            "chaise",
            "objets",
        ]
    )
    strong_generated_text = any(
        term in text_only
        for term in [
            "entité",
            "malveillante",
            "quelque chose",
            "voix profonde",
            "cauchemar",
            "glacer le sang",
            "coups secs",
            "ce qui s'est passé",
            "ce qui s’est passé",
            "farce",
            "débat sur la vérité",
        ]
    )
    if strong_generated_text and not strong_real_text:
        return "generated"

    strong_real = any(
        term in text
        for term in [
            "photo",
            "photos",
            "photograph",
            "preuve",
            "evidence",
            "police",
            "report",
            "levit",
            "lévit",
            "janet",
            "hodgson",
            "peggy",
            "maurice",
            "grosse",
            "playfair",
            "house exterior",
            "maison",
            "bedroom",
            "chambre",
        ]
    )
    strong_generated = any(
        term in text
        for term in [
            "entité",
            "shadowy figure",
            "quelque chose",
            "voix profonde",
            "cauchemar",
            "glacer le sang",
            "coups secs",
            "ce qui s'est passé",
            "ce qui s’est passé",
            "unseen",
            "invisible",
            "présence",
            "presence",
        ]
    )

    # Le second plan d'une scène sert souvent de respiration/reconstitution,
    # sauf si le plan réclame explicitement une preuve ou une personne précise.
    if plan_index % 2 == 1 and not strong_real:
        generated_score += 4

    if strong_real:
        real_score += 3
    if strong_generated:
        generated_score += 4

    return "real" if real_score >= generated_score else "generated"


def construire_requetes_reelles(
    query: str,
    scene_text: str = "",
    contexte_niche: str = "",
    context_histoire: str = "",
) -> list:
    """Génère plusieurs requêtes exactes, FR/EN, pour éviter les résultats aléatoires."""
    base = re.sub(r"\s+", " ", query or "").strip()
    scene = re.sub(r"\s+", " ", scene_text or "").strip()
    ctx = contexte_niche or context_histoire or ""
    haystack = " ".join([base, scene, ctx]).lower()
    queries = []

    def add(q):
        q = re.sub(r"\s+", " ", q or "").strip()
        if q and q.lower() not in {x.lower() for x in queries}:
            queries.append(q)

    add(base)
    if ctx:
        add(f'"{ctx}" {base}')
    if any(
        token in haystack
        for token in (
            "yuba",
            "madruga",
            "mathias",
            "weiher",
            "sterling",
            "huett",
            "plumas",
            "montego",
        )
    ):
        add('"Yuba County Five" photographs')
        add('"Yuba County Five" missing poster')
        if any(x in haystack for x in ["map", "route", "oroville", "plumas"]):
            add('"Yuba County Five" route map Oroville Plumas')
            add('"Yuba County Five" case map 1978')
        if any(x in haystack for x in ["montego", "car", "vehicle", "voiture"]):
            add('"Yuba County Five" "Mercury Montego"')
            add('"Jack Madruga" "Mercury Montego"')
        if any(
            x in haystack
            for x in ["trailer", "forest service", "propane", "blankets", "canned"]
        ):
            add('"Yuba County Five" "Forest Service trailer"')
            add('"Yuba County Five" trailer canned food propane blankets')
        if any(x in haystack for x in ["mathias", "gary"]):
            add('"Gary Mathias" "Yuba County Five"')
            add('"Gary Mathias" army photo')
        if any(x in haystack for x in ["weiher", "ted"]):
            add('"Ted Weiher" "Yuba County Five"')
        if any(x in haystack for x in ["schons", "witness", "temoin"]):
            add('"Joe Schons" "Yuba County Five"')
        if any(
            x in haystack
            for x in ["madruga", "sterling", "huett", "family", "families"]
        ):
            add('"Jack Madruga" "Bill Sterling" "Jackie Huett"')
            add('"Yuba County Five" family photos')
    elif "enfield" in haystack:
        add("cas enfield poltergeist photos chambre janet")
        add("cas enfield poltergeist photos")
        add('"Enfield Poltergeist" photographs')
        if any(
            x in haystack
            for x in ["janet", "levitation", "lévit", "flying", "objects", "objets"]
        ):
            add("cas enfield Janet Hodgson levitation photo")
            add('"Enfield Poltergeist" "Janet Hodgson" levitation photograph')
            add('"Enfield Poltergeist" bedroom flying objects')
        if any(
            x in haystack
            for x in [
                "bedroom",
                "chambre",
                "coups",
                "knocking",
                "objets",
                "chair",
                "chaise",
            ]
        ):
            add("cas enfield chambre poltergeist photo")
            add('"Enfield Poltergeist" bedroom photograph')
        if any(
            x in haystack
            for x in ["house", "maison", "green street", "exterior", "council"]
        ):
            add('"Enfield Poltergeist" house exterior')
            add("maison poltergeist Enfield photo")
        if any(x in haystack for x in ["peggy", "family", "famille", "hodgson"]):
            add('"Hodgson family" "Enfield Poltergeist"')
            add('"Peggy Hodgson" "Enfield Poltergeist"')
        if any(
            x in haystack for x in ["maurice", "grosse", "playfair", "investigator"]
        ):
            add('"Maurice Grosse" "Enfield Poltergeist" photograph')
            add('"Guy Playfair" "Enfield Poltergeist" photograph')
        if any(x in haystack for x in ["police", "report", "media", "viral"]):
            add('"Enfield Poltergeist" police report')
            add('"Enfield Poltergeist" newspaper 1977')

    return queries[:8]


# ═══════════════════════════════════════════════════════════════════════════════
#  IMAGES DE STOCK (PEXELS / PIXABAY) + DÉGRADATION DE MOTS-CLÉS
# ═══════════════════════════════════════════════════════════════════════════════
STOPWORDS_EN = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "over",
    "under",
    "down",
    "back",
    "away",
    "toward",
    "about",
    "before",
    "after",
    "their",
    "them",
    "they",
    "have",
    "been",
    "were",
    "will",
    "just",
    "than",
    "such",
    "each",
    "some",
    "when",
    "where",
    "while",
    "these",
    "those",
    "thing",
    "short",
    "long",
    "small",
    "large",
    "cinematic",
    "style",
    "lock",
    "shot",
    "angle",
    "film",
    "video",
    "image",
    "dramatic",
    "dark",
    "light",
    "bright",
    "showing",
    "reveal",
    "against",
    "pair",
    "photorealistic",
    "archival",
    "documentary",
    "photography",
    "naturalistic",
    "desaturated",
    "depth",
    "field",
    "crime",
    "evidence",
    "photo",
    "aesthetic",
}

KEYWORDS_BOOST = [
    "forest",
    "mountain",
    "cave",
    "abandoned",
    "house",
    "mansion",
    "castle",
    "corridor",
    "hallway",
    "basement",
    "attic",
    "cemetery",
    "graveyard",
    "tombstone",
    "church",
    "chapel",
    "cathedral",
    "fog",
    "mist",
    "smoke",
    "rain",
    "storm",
    "moonlight",
    "shadow",
    "silhouette",
    "figure",
    "detective",
    "police",
    "investigation",
    "evidence",
    "typewriter",
    "newspaper",
    "letter",
    "envelope",
    "cipher",
    "computer",
    "desk",
    "office",
    "room",
    "door",
    "window",
    "mirror",
    "document",
    "file",
    "knife",
    "gun",
    "weapon",
    "mask",
    "horror",
    "haunted",
    "mystery",
    "mysterious",
    "creepy",
    "eerie",
    "sinister",
    "night",
    "midnight",
    "twilight",
    "tunnel",
    "bridge",
    "road",
    "alley",
    "street",
]


def extraire_mots_cles(prompt: str) -> str:
    propre = re.sub(r"\[.*?\]", " ", prompt).lower()
    mots = re.findall(r"[a-z]+", propre)

    boost_hits = [m for m in mots if m in KEYWORDS_BOOST]
    if boost_hits:
        seen, uniques = set(), []
        for m in boost_hits:
            if m not in seen:
                seen.add(m)
                uniques.append(m)
        return " ".join(uniques[:3])

    significatifs = [m for m in mots if len(m) >= 5 and m not in STOPWORDS_EN]
    if significatifs:
        return " ".join(significatifs[:3])

    return "dark mystery night"
