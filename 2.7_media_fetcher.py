"""
2.7_media_fetcher.py — SMART REAL/GENERATED MEDIA MIX

Pipeline prioritaire pour chaque plan visuel :
  1. Décision éditoriale par plan : archive réelle ou reconstitution générée
  2. Pour les archives : DuckDuckGo Images + Bing Images + sources curated
  3. Pour les reconstitutions : Imagen 4.0 avec prompt sécurisé
  4. Stock Pexels/Pixabay uniquement si ALLOW_STOCK_FALLBACKS=1
  5. Fond noir générique (dernier recours pour débloquer le pipeline)

Toutes les images sont normalisées en 1080×1920 avec image entière centrée
sur fond flouté. On évite les crop-cover destructeurs.
"""

import os
import io
import json
import re
import random
import time
import requests
import urllib.parse
import html
import shutil
from dotenv import load_dotenv
from utils import trouver_dernier_projet

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        from google.genai import types

        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("✅ Moteur IA (Gemini API) initialisé")
    except Exception as e:
        print(f"⚠️ Gemini SDK indisponible : {e}")

# Modèles Imagen 4
IMAGEN_MODEL_STANDARD = "imagen-4.0-generate-001"
IMAGEN_MODEL_FAST = "imagen-4.0-fast-generate-001"

# Suffixe stylistique en LANGAGE NATUREL CONTINU.
#
# STYLE : feature film cinéma docu, prise en 35mm, pleine image plein cadre.
# IMPORTANT : on évite *toute* référence à "VHS", "camcorder", "archive footage",
# "found footage", "tape", "home video", "vintage video" — ces mots-clés
# poussent Imagen à reproduire l'esthétique camcorder amateur qu'on connaît
# (cadre noir, REC en haut à gauche, batterie en haut à droite, timestamp en
# bas). On vise au contraire l'esthétique d'un long-métrage documentaire pour
# le cinéma : pleine image sans bord, sans HUD, sans overlay.
#
# NE JAMAIS utiliser une liste de mots-clés type "no_textures, no_text" en
# début/fin de prompt : le modèle interprétait ces tokens comme des paires
# clé:valeur YAML et les rendait visuellement.
STYLE_SUFFIX_ANIME = (
    " Studio Ghibli anime illustration. Warm lamp glow against deep blue night. "
    "Hand-painted background, expressive faces. No words, no letters, no text."
)
STYLE_SUFFIX_LOW_POLY_3D = (
    " Premium cinematic 3D low-poly render with crisp faceted polygon geometry, physically based materials, "
    "sharp subject detail, realistic global illumination and depth of field, volumetric fog, "
    "cold desaturated blue-gray lighting with restrained deep-red accents, harsh chiaroscuro shadows, "
    "centered subject, polished feature-film composition, vertical 9:16. "
    "The image must be completely free of captions, subtitles, signs, labels, words, letters, numbers, and UI text."
)
STYLE_SUFFIX_NOIR = (
    " Black and white crime scene photography. Dramatic shadows. "
    "Vintage detective novel atmosphere. Interior shot. No words, no text."
)
# Sélectionné dynamiquement depuis script.json["visual_style"]
STYLE_SUFFIX = STYLE_SUFFIX_LOW_POLY_3D

TARGET_W, TARGET_H = 1080, 1920
IMAGEN_QUOTA_EPUISE = False
REAL_MEDIA_ONLY = os.getenv("REAL_MEDIA_ONLY", "0") == "1"
MEDIA_MIX_MODE = os.getenv("MEDIA_MIX_MODE", "smart").lower()
ALLOW_STOCK_FALLBACKS = os.getenv("ALLOW_STOCK_FALLBACKS", "0") == "1"
ALLOW_PEXELS_VIDEO = os.getenv("ALLOW_PEXELS_VIDEO", "0") == "1"
ALLOW_POLLINATIONS_FALLBACK = os.getenv("ALLOW_POLLINATIONS_FALLBACK", "1") == "1"
FORCE_MONOCHROME_MEDIA = os.getenv("FORCE_MONOCHROME_MEDIA", "0") == "1"
MAX_BING_RESULTS = int(os.getenv("MAX_BING_RESULTS", "24"))
MAX_DDG_RESULTS = int(os.getenv("MAX_DDG_RESULTS", "36"))
MAX_DDG_QUERIES_PER_PLAN = int(os.getenv("MAX_DDG_QUERIES_PER_PLAN", "3"))
DDG_TIMEOUT = float(os.getenv("DDG_TIMEOUT", "6"))
STRICT_REAL_VALIDATION = os.getenv("STRICT_REAL_VALIDATION", "1") == "1"
SKIP_CACHE_AUDIT = os.getenv("SKIP_CACHE_AUDIT", "0") == "1"
# Désactivé par défaut: même les sources "curated" passent par valider_image_historique.
# Évite les mismatch silencieux quand un keyword d'ambiance gagne contre le sujet réel
# (ex: image "snow mountain" choisie pour un sous-titre qui parle d'une voiture).
TRUST_CURATED_SOURCES = os.getenv("TRUST_CURATED_SOURCES", "0") == "1"
USED_SOURCE_URLS = set()
DDG_RESULT_CACHE = {}

# Grille éditoriale par défaut en mode smart:
# - REAL = preuve/archive/personne/lieu qui ancre l'histoire
# - GENERATED = reconstitution esthétique, tension, respiration visuelle
# L'IA n'est donc pas un simple fallback: elle est planifiée dès le début.
SMART_MIX_OVERRIDES = {
    "scene_1": ["generated", "generated"],
    "scene_2": ["real", "generated"],
    "scene_3": ["generated", "real"],
    "scene_4": ["real", "generated", "generated"],
    "scene_5": ["generated", "generated", "generated"],
    "scene_6": ["generated", "generated", "real", "generated"],
    "scene_7": ["generated", "generated"],
    "scene_8": ["real", "generated", "generated"],
    "scene_9": ["generated", "generated", "real"],
    "scene_10": ["generated", "generated"],
}

CURATED_CASE_IMAGES = {
    "enfield": [
        {
            "keywords": ["house", "exterior", "green street", "council", "maison"],
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/284%20Green%20Street%2C%20Enfield.jpg",
            "label": "284 Green Street, Enfield exterior",
        },
        {
            "keywords": ["house", "exterior", "green street", "council", "maison"],
            "url": "https://static.wikia.nocookie.net/paranormal/images/d/d9/Enfield_House.jpg/revision/latest?cb=20250222070041",
            "label": "Enfield House Exterior",
        },
        {
            "keywords": [
                "bedroom",
                "janet",
                "levitation",
                "hurled",
                "flying",
                "objects",
                "evidence",
            ],
            "url": "https://static.wikia.nocookie.net/paranormal/images/7/7d/Enfield_House_Children%27s_Bedroom.jpg/revision/latest?cb=20250222070109",
            "label": "Enfield House Children's Bedroom",
        },
        {
            "keywords": ["janet", "levitation", "hurled", "bed", "evidence"],
            "url": "https://deliria.it/blog/wp-content/uploads/2016/07/enfield-janet-hodgson.jpg",
            "label": "Janet Hodgson levitation archive",
        },
        {
            "keywords": [
                "janet",
                "levitation",
                "hurled",
                "bed",
                "flying",
                "evidence",
                "bedroom",
            ],
            "url": "http://www.spookyisles.com/wp-content/uploads/2012/04/Enfield-Poltergeist-Feature.jpg",
            "label": "Enfield Poltergeist levitation feature photo",
        },
        {
            "keywords": [
                "janet",
                "levitation",
                "bedroom",
                "objects",
                "chair",
                "evidence",
                "chambre",
            ],
            "url": "https://aventurasnahistoria.com.br/wp-content/uploads/ciencia/enfield_poltergeist_3.jpg",
            "label": "Enfield bedroom evidence photo",
        },
        {
            "keywords": [
                "bedroom",
                "chambre",
                "objects",
                "objets",
                "chair",
                "chaise",
                "evidence",
            ],
            "url": "https://www.net-voyance.fr/wp-content/uploads/2014/09/poltergeist-enfield.jpg",
            "label": "Enfield bedroom objects photo",
        },
        {
            "keywords": ["family", "famille", "hodgson", "peggy", "janet", "portrait"],
            "url": "https://imagenes.eltiempo.com/files/image_600_455/uploads/2023/08/10/64d55be5d2106.jpeg",
            "label": "Hodgson family / Enfield case photo",
        },
        {
            "keywords": [
                "janet",
                "levitation",
                "photo",
                "evidence",
                "flying",
                "bedroom",
            ],
            "url": "https://petapixel.com/assets/uploads/2023/10/enfield-photographer-denies-claim-janet-hodgson-jumped-ghost.jpg",
            "label": "Janet Hodgson levitation press photo",
        },
        {
            "keywords": [
                "janet",
                "levitation",
                "photo",
                "evidence",
                "bedroom",
                "apple",
            ],
            "url": "https://www.dexerto.com/cdn-image/wp-content/uploads/2023/10/25/enfield-poltergeist-photos-featured.jpg",
            "label": "Enfield Poltergeist featured photo",
        },
        {
            "keywords": [
                "family",
                "famille",
                "hodgson",
                "peggy",
                "janet",
                "media",
                "coverage",
            ],
            "url": "https://www.dexerto.com/cdn-image/wp-content/uploads/2023/10/25/enfield-poltergeist-photos-2-1024x683.jpg",
            "label": "Enfield Poltergeist family photo",
        },
        {
            "keywords": ["bedroom", "chambre", "objects", "photo", "evidence", "media"],
            "url": "https://www.dexerto.com/cdn-image/wp-content/uploads/2023/10/25/enfield-poltergeist-photos-1-1024x683.jpg",
            "label": "Enfield Poltergeist bedroom press photo",
        },
        {
            "keywords": [
                "bedroom",
                "chambre",
                "janet",
                "margaret",
                "photo",
                "evidence",
            ],
            "url": "https://www.dexerto.com/cdn-image/wp-content/uploads/2023/10/25/enfield-poltergeist-photos-1024x689.jpg",
            "label": "Enfield Poltergeist archive bedroom photo",
        },
        {
            "keywords": ["janet", "levitation", "photo", "evidence", "bedroom"],
            "url": "https://demonsspiritsandpoltergeist.com/wp-content/uploads/2026/03/Screenshot-177.png",
            "label": "Janet Hodgson levitation reference image",
        },
    ],
    "yuba": [
        {
            "keywords": [
                "missing",
                "poster",
                "group",
                "gary",
                "mathias",
                "madruga",
                "weiher",
                "sterling",
                "huett",
            ],
            "url": "https://dyatlovpass.com/resources/340/Yuba-county-5-Missing-poster-thumb.jpg",
            "label": "Yuba County Five missing poster",
        },
        {
            "keywords": ["map", "route", "oroville", "plumas", "forest", "case"],
            "url": "https://dyatlovpass.com/resources/340/Yuba-county-five-map-thumb.jpg",
            "label": "Yuba County Five route map",
        },
        {
            "keywords": ["plumas", "forest", "snow", "mountain", "road", "wilderness"],
            "url": "https://dyatlovpass.com/resources/340/Plumas-National-Forest.jpg",
            "label": "Plumas National Forest reference",
        },
        {
            "keywords": ["mercury", "montego", "car", "madruga", "vehicle"],
            "url": "https://dyatlovpass.com/resources/340/gallery/15-Mercury-Montego.jpg",
            "label": "1969 Mercury Montego reference",
        },
        {
            "keywords": ["case", "map", "trailer", "bodies", "distance"],
            "url": "https://dyatlovpass.com/resources/340/gallery/Case-Map-1978.jpg",
            "label": "Yuba County Five 1978 case map",
        },
        {
            "keywords": ["madruga", "army", "portrait", "jack"],
            "url": "https://dyatlovpass.com/resources/340/gallery/29-Jack-Madruga.jpg",
            "label": "Jack Madruga archive photo",
        },
        {
            "keywords": [
                "missing",
                "poster",
                "group",
                "gary",
                "mathias",
                "madruga",
                "weiher",
                "sterling",
                "huett",
            ],
            "url": "https://dyatlovpass.com/resources/340/gallery/39-Missing-poster.jpg",
            "label": "Yuba County Five missing poster full",
        },
        {
            "keywords": ["mercury", "montego", "car", "madruga", "vehicle"],
            "url": "https://dyatlovpass.com/resources/340/gallery/51-Mercury-Montego.jpg",
            "label": "1969 Mercury Montego archive angle",
        },
        {
            "keywords": ["snow", "mountain", "road", "winter", "plumas", "forest"],
            "url": "https://dyatlovpass.com/resources/340/gallery/13-snow-mountain-house.jpg",
            "label": "Yuba winter mountain reference",
        },
        {
            "keywords": [
                "trailer",
                "forest",
                "service",
                "forestry",
                "propane",
                "blankets",
            ],
            "url": "https://dyatlovpass.com/resources/340/gallery/16-Forestry-trailers.jpg",
            "label": "Forestry trailers exterior",
        },
        {
            "keywords": ["trailer", "forest", "service", "forestry", "ted", "weiher"],
            "url": "https://dyatlovpass.com/resources/340/gallery/17-Forestry-trailers.jpg",
            "label": "Forestry trailer front",
        },
        {
            "keywords": ["trailer", "bunk", "ted", "weiher", "inside", "blankets"],
            "url": "https://dyatlovpass.com/resources/340/gallery/18-Ted-Weithers-remains-found-on-this-bunk.jpg",
            "label": "Forestry trailer bunk reference",
        },
        {
            "keywords": ["trailer", "roger", "koch", "ted", "weiher", "discovered"],
            "url": "https://dyatlovpass.com/resources/340/gallery/22-Roger-Koch.jpg",
            "label": "Roger Koch archive photo",
        },
        {
            "keywords": ["behr", "market", "snacks", "food", "chico", "store"],
            "url": "https://dyatlovpass.com/resources/340/gallery/31-Behrs-market-menu.jpg",
            "label": "Behr's Market reference",
        },
        {
            "keywords": ["ted", "weiher", "grave", "real", "archive"],
            "url": "https://dyatlovpass.com/resources/340/gallery/10-Ted-Weiher-grave.jpg",
            "label": "Ted Weiher grave",
        },
        {
            "keywords": ["madruga", "jack", "grave", "real", "archive"],
            "url": "https://dyatlovpass.com/resources/340/gallery/12-Madruga-grave.jpg",
            "label": "Jack Madruga grave",
        },
        {
            "keywords": ["huett", "jackie", "grave", "real", "archive"],
            "url": "https://dyatlovpass.com/resources/340/gallery/11-Jackie-Huett-grave.jpeg",
            "label": "Jackie Huett grave",
        },
    ],
}

# ═══════════════════════════════════════════════════════════════════════════════
#  SÉCURITÉ — LISTE NOIRE NSFW & DOMAINES ADULTES
# ═══════════════════════════════════════════════════════════════════════════════
# Domaines ou sous-chaînes d'URL à rejeter immédiatement sans téléchargement
NSFW_URL_BLACKLIST = [
    # Sites adultes connus
    "xhcdn",
    "xvideos",
    "pornhub",
    "xhamster",
    "xnxx",
    "redtube",
    "youporn",
    "brazzers",
    "onlyfans",
    "spankbang",
    "beeg",
    "tube8",
    "nuvid",
    "drtuber",
    "tnaflix",
    "5max",
    "efukt",
    "hentai",
    "rule34",
    "gelbooru",
    "danbooru",
    "nhentai",
    "e-hentai",
    "8muses",
    "luscious",
    "motherless",
    "heavy-r",
    "xxxbunker",
    "sex.com",
    "sexvid",
    "pornpic",
    "slutload",
    "yobt",
    "thumbzilla",
    "titsintops",
    "milf",
    "bigass",
    "bigtits",
    "boobs",
    "nude",
    "naked",
    "nsfw",
    "18only",
    "adult",
    "porn",
    "xxx",
    "erotic",
    "voyeur",
    "thothub",
    "epawg",
    "camwhores",
    "pimpandhost",
    "pixhost",
    "metart",
    "xham",
    "pornosexe",
    "cdnclouder",
    # Domaines de contenu aléatoire sans rapport
    "alicdn",
    "shopee",
    "lazada",
    "tokopedia",
    "alibaba",
    "taobao",
    "sexualidade",
    "sexualidade",
]


def url_est_suspecte(url: str) -> bool:
    """Vérifie si une URL contient des marqueurs de contenu adulte ou hors-sujet."""
    url_lower = url.lower()
    return any(marker in url_lower for marker in NSFW_URL_BLACKLIST)


def telecharger_image_url(img_url: str, chemin_jpg: str, label: str = "") -> bool:
    canonical = re.sub(r"[?#].*$", "", img_url)
    if canonical in USED_SOURCE_URLS:
        print(f"      ↪️  Source déjà utilisée, on varie : {img_url[:70]}")
        return False
    if url_est_suspecte(img_url):
        print(f"      🚫 URL bloquée (domaine suspect) : {img_url[:70]}")
        return False
    try:
        resp = requests.get(
            img_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "image/jpeg,image/png,image/webp,image/apng,image/*,*/*;q=0.8",
            },
            timeout=25,
            stream=True,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get("Content-Type", "").lower()
        if not any(
            t in content_type
            for t in ["image/jpeg", "image/png", "image/jpg", "image/webp"]
        ):
            print(f"      ⚠️ Source curated non-image ({content_type[:40]}) — ignorée")
            return False
        with open(chemin_jpg, "wb") as f:
            for chunk in resp.iter_content(32768):
                f.write(chunk)
        if os.path.getsize(chemin_jpg) < 8000:
            os.remove(chemin_jpg)
            return False
        USED_SOURCE_URLS.add(canonical)
        print(f"      📚 Source curated téléchargée ({label or 'image'})")
        return True
    except Exception as e:
        print(f"      ⚠️ Échec source curated {label or img_url[:40]} : {e}")
        if os.path.exists(chemin_jpg):
            os.remove(chemin_jpg)
        return False


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

    if STYLE_SUFFIX == STYLE_SUFFIX_LOW_POLY_3D:
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


def contexte_validation_media(
    context_histoire: str, query: str, scene_text: str = "", veo_prompt: str = ""
) -> str:
    parts = [
        f"CASE: {context_histoire}".strip(),
        f"SEARCH_QUERY: {query}".strip(),
    ]
    if scene_text:
        parts.append(f"SCENE_TEXT: {scene_text[:420]}")
    if veo_prompt:
        # Hors f-string : un antislash dans l'expression casse Python < 3.12
        visual = re.sub(r"\[STYLE LOCK[^\]]*\]", "", veo_prompt, flags=re.IGNORECASE)
        parts.append(f"EXPECTED_VISUAL: {visual[:520]}")
    return "\n".join(p for p in parts if p)


def verifier_securite_image(chemin_jpg: str) -> bool:
    """PHASE 1 — Vérification de sécurité obligatoire : rejette tout contenu NSFW/adulte/inapproprié.
    Cette vérification est indépendante de la pertinence historique et ne peut jamais être contournée.
    Retourne True si l'image est SAFE, False si elle doit être rejetée.
    """
    if not gemini_client:
        return True  # Sans IA, on suppose que la blacklist d'URL a déjà filtré
    try:
        from PIL import Image

        with Image.open(chemin_jpg) as im:
            prompt = (
                "Analyze this image carefully for safety and appropriateness. This image is for a professional documentary.\n"
                "You must perform a strict safety check.\n"
                "Answer UNSAFE if the image contains any of the following:\n"
                "- Nudity, partial nudity, exposed intimate parts, transparent or highly suggestive clothing.\n"
                "- Any sexual, romantic, or intimate actions/postures.\n"
                "- Any suggestive or adult-themed content, including adult movie posters, models in lingerie/underwear, or pin-up styles.\n"
                "- Graphic violence, blood, gore, weapons, or scary/disturbing faces (unless it is a highly desaturated historical document style).\n"
                "- Any commercial spam, product ads, online shopping pages, stock photo watermarks, or website screenshots.\n"
                "- Any modern gaming graphics, cartoons, anime, 3D renders, or fictional characters (like Roblox, Minecraft, Fortnite, or memes).\n"
                "\n"
                "If the image is completely clean, safe, and appropriate, answer SAFE.\n"
                "If there is ANY doubt or if the image triggers any of these rules, you MUST answer UNSAFE.\n"
                "Answer ONLY: SAFE or UNSAFE."
            )
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[im, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=5,
                ),
            )
            if response.text is None:
                print("      🛡️ Sécurité : Réponse nulle -> rejeté par précaution")
                return False
            ans = response.text.strip().upper()
            is_safe = "SAFE" in ans and "UNSAFE" not in ans
            print(
                f"      🛡️ Vérification sécurité : Réponse={ans} -> {'✅ SAFE' if is_safe else '🚫 UNSAFE — REJETÉ'}"
            )
            return is_safe
    except Exception as e:
        print(f"      ⚠️ Échec vérification sécurité : {e} -> rejeté par précaution")
        return False


def valider_image_historique(
    chemin_jpg: str,
    context_histoire: str,
    query: str,
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Pipeline de validation en 2 phases :
    PHASE 1 (obligatoire) : Vérification de sécurité NSFW — tout échec = rejet immédiat.
    PHASE 2 : Validation de pertinence historique/atmosphérique.
    """
    if not gemini_client:
        return False  # Sans IA, pas de validation possible → on ne prend aucun risque

    # ── PHASE 1 : Sécurité obligatoire ──
    if not verifier_securite_image(chemin_jpg):
        return False  # Rejet immédiat, sans passer à la phase 2

    # ── PHASE 2 : Pertinence ──
    try:
        from PIL import Image

        with Image.open(chemin_jpg) as im:
            context_block = contexte_validation_media(
                context_histoire, query, scene_text, veo_prompt
            )
            prompt = (
                "You are auditing one downloaded image for a serious documentary video.\n"
                "Your job is to decide whether this image is genuinely usable for the exact case and exact scene.\n"
                "\n"
                f"{context_block}\n"
                "\n"
                "CRITICAL REJECTION RULES:\n"
                "- Answer NO if the image is unrelated to the named case, person, place, object, period, or scene.\n"
                "- Answer NO for unrelated celebrities, actors, movie posters, book covers, memes, logos, ads, shopping pages, screenshots, gaming graphics, AI-looking fantasy art, or cartoons.\n"
                "- Answer NO if the search asks for a specific person/event/evidence and the image is only generic atmosphere.\n"
                "- Answer NO if the visual is modern when the scene requires a historical/period archive look.\n"
                "- Answer NO if the main subject is not understandable at mobile vertical-video size.\n"
                "\n"
                "ACCEPTABLE ONLY IF ONE OF THESE IS TRUE:\n"
                "- It appears to be a real archive/news/document/photo directly tied to the case.\n"
                "- It depicts the exact named person/place/evidence or a highly plausible period-correct representation of it.\n"
                "- For purely atmospheric queries, it clearly depicts the requested object/place/room and fits the period and tone.\n"
                "\n"
                "Be extremely skeptical. If there is any doubt, answer NO.\n"
                "Answer ONLY: YES or NO."
            )

            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[im, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=5,
                ),
            )
            if response.text is None:
                print("      🔍 Pertinence : Réponse nulle -> rejeté")
                return False
            ans = response.text.strip().upper()
            is_valid = "YES" in ans
            print(
                f"      🔍 Pertinence stricte : Réponse={ans} -> {'✅ Valide' if is_valid else '❌ Rejeté'}"
            )
            return is_valid
    except Exception as e:
        print(f"      ⚠️ Échec validation pertinence : {e} -> rejeté par précaution")
        return False


def valider_media_cache(
    chemin_media: str,
    context_histoire: str,
    queries: list,
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Valide la sécurité ET la pertinence d'un média existant (image ou vidéo).
    Retourne True si valide, False si invalide/suspect/hors-sujet.

    On effectue la double passe parce que les mismatch visuels/sous-titres
    (ex: image d'une femme alors que le sous-titre liste cinq hommes) ne sont
    pas détectables par la seule passe sécurité NSFW.
    """
    if not os.path.exists(chemin_media):
        return True

    query = queries[0] if queries else "dark mystery atmosphere"
    chemin_valider = chemin_media
    est_video = chemin_media.lower().endswith(".mp4")
    temp_jpg = None

    if est_video:
        temp_jpg = chemin_media + ".temp_val.jpg"
        import subprocess

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                chemin_media,
                "-ss",
                "00:00:01.5",
                "-vframes",
                "1",
                temp_jpg,
            ]
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )
            if os.path.exists(temp_jpg) and os.path.getsize(temp_jpg) > 1000:
                chemin_valider = temp_jpg
            else:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    chemin_media,
                    "-ss",
                    "00:00:00",
                    "-vframes",
                    "1",
                    temp_jpg,
                ]
                subprocess.run(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
                )
                if os.path.exists(temp_jpg) and os.path.getsize(temp_jpg) > 1000:
                    chemin_valider = temp_jpg
                else:
                    print(
                        f"      ⚠️ Impossible d'extraire une frame de la vidéo {os.path.basename(chemin_media)} — rejetée par sécurité"
                    )
                    return False
        except Exception as e:
            print(f"      ⚠️ Échec extraction frame vidéo : {e}")
            return False

    try:
        if STRICT_REAL_VALIDATION:
            valide = valider_image_historique(
                chemin_valider, context_histoire or query, query, scene_text, veo_prompt
            )
        else:
            valide = verifier_securite_image(chemin_valider)
        if temp_jpg and os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        return valide
    except Exception as e:
        if temp_jpg and os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        print(
            f"      ⚠️ Erreur lors de l'audit cache de {os.path.basename(chemin_media)} : {e}"
        )
        return False


def auditer_et_nettoyer_cache(
    dossier_projet: str, visual_plan: dict, context_histoire: str
):
    """Audit tout le cache existant et supprime immédiatement les fichiers invalides."""
    print("\n" + "═" * 56)
    print("  🛡️  AUDIT DE SÉCURITÉ & PERTINENCE DU CACHE EXISTANT")
    print("═" * 56)

    suppr_count = 0
    total_count = 0

    for scene_key, plans in visual_plan.items():
        for i, plan in enumerate(plans):
            file_path = plan.get("file_path", "")
            if not file_path:
                continue

            full_path = file_path
            if not os.path.isabs(full_path):
                full_path = os.path.join(
                    "/Users/melchioraholou/Documents/script-tiktok", file_path
                )

            if os.path.exists(full_path):
                total_count += 1
                print(
                    f"🧐 Audit cache : {scene_key}/plan_{i + 1} ({os.path.basename(full_path)})..."
                )
                queries = plan.get("real_media_queries", [])

                # Les médias générés (Imagen) sont issus d'un prompt qu'on contrôle,
                # donc on se contente d'une passe sécurité NSFW. Les sources curated
                # par contre venaient d'un scoring keyword qui pouvait se tromper de
                # sujet : on les soumet à la passe pertinence Gemini comme DDG/Bing.
                if plan.get("source_type") in {
                    "generated",
                    "imagen",
                    "generated_reused",
                }:
                    valide = verifier_securite_image(full_path)
                else:
                    valide = valider_media_cache(
                        full_path,
                        context_histoire,
                        queries,
                        plan.get("text_segment", ""),
                        plan.get("veo_prompt", ""),
                    )

                if not valide:
                    print(
                        f"💥 CACHE CORROMPU/INCORRECT -> Suppression de {os.path.basename(full_path)}"
                    )
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass
                    base_no_ext = os.path.splitext(full_path)[0]
                    for ext in [".jpg", ".mp4"]:
                        alt_path = base_no_ext + ext
                        if os.path.exists(alt_path):
                            try:
                                os.remove(alt_path)
                            except Exception:
                                pass
                    plan["file_path"] = ""
                    suppr_count += 1
                else:
                    print("   ✅ Cache validé.")

    print("\n" + "═" * 56)
    print(
        f"  🛡️ Fin audit cache : {suppr_count}/{total_count} médias corrompus supprimés"
    )
    print("═" * 56 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  NORMALISATION & NETTOYAGE
# ═══════════════════════════════════════════════════════════════════════════════
def appliquer_noir_blanc_vhs(img):
    """Convertit tout média en noir et blanc contrasté avec une texture analogique légère."""
    if not FORCE_MONOCHROME_MEDIA:
        return img
    from PIL import Image, ImageDraw, ImageEnhance

    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(1.38)
    img = ImageEnhance.Brightness(img).enhance(0.94)
    img = img.convert("RGB")

    noise = Image.effect_noise(img.size, 18).convert("L")
    img = Image.blend(img, noise.convert("RGB"), 0.055)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    for y in range(0, h, 5):
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, 24))
    for y in range(0, h, 143):
        draw.rectangle([0, y, w, y + 2], fill=(235, 235, 235, 18))
    return img


def normaliser_image(chemin_jpg: str) -> bool:
    """Force l'image à exactement TARGET_W × TARGET_H.
    L'image originale reste entière, centrée, sur une version cover floutée.
    C'est volontairement plus lisible qu'un crop-cover qui coupe le sujet.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        print("      ⚠️ PIL ou ImageFilter non installé -> skip normalisation")
        return False

    try:
        with Image.open(chemin_jpg) as im:
            w, h = im.size
            # Déterminer la méthode d'échantillonnage de manière compatible PIL ancienne et moderne
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            im = im.convert("RGB")

            scale_bg = max(TARGET_W / w, TARGET_H / h)
            bg_w = int(round(w * scale_bg))
            bg_h = int(round(h * scale_bg))
            bg_resized = im.resize((bg_w, bg_h), resample_filter)
            bg_left = (bg_w - TARGET_W) // 2
            bg_top = (bg_h - TARGET_H) // 2
            bg_cropped = bg_resized.crop(
                (bg_left, bg_top, bg_left + TARGET_W, bg_top + TARGET_H)
            )
            bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=46))
            bg_blurred = bg_blurred.point(lambda px: int(px * 0.72))

            scale_fit = min(TARGET_W / w, TARGET_H / h)
            fit_w = max(1, int(round(w * scale_fit)))
            fit_h = max(1, int(round(h * scale_fit)))
            fit_resized = im.resize((fit_w, fit_h), resample_filter)

            result = Image.new("RGB", (TARGET_W, TARGET_H))
            result.paste(bg_blurred, (0, 0))
            paste_x = (TARGET_W - fit_w) // 2
            paste_y = (TARGET_H - fit_h) // 2
            result.paste(fit_resized, (paste_x, paste_y))
            result = appliquer_noir_blanc_vhs(result)
            result = ImageEnhance.Contrast(result).enhance(1.04)
            result = result.filter(
                ImageFilter.UnsharpMask(radius=1.25, percent=120, threshold=3)
            )

            result.save(chemin_jpg, format="JPEG", quality=95, optimize=True)
            print(
                f"      📐 [Center-Fit + Blur + Sharp] Normalisé : {w}×{h} → {TARGET_W}×{TARGET_H}"
            )
            return True
    except Exception as e:
        print(f"      ⚠️ Normalisation échouée : {str(e)[:100]}")
        return False


def nettoyer_prompt(prompt: str) -> str:
    """Nettoie et applique le suffixe de style au prompt en langage naturel continu.

    Imagen 4 a tendance à rendre visuellement les structures `label: valeur` et les
    longues listes virgule/clé qui ouvrent un prompt (on a vu apparaître
    "low_poly_3d_mesh: true / faceted_polygon_geometry: true / primary_subject:"
    dans plusieurs images). On reformule donc tout en phrases anglaises continues.
    """
    p = re.sub(r"\[STYLE LOCK[^\]]*\]", "", prompt, flags=re.IGNORECASE)
    p = re.sub(r"\[([^\]]+)\]", r"\1", p)
    p = re.sub(
        r"\b(sign|signs|signage|signpost|placard|banner|caption|subtitle)\b[^.,;]*",
        "",
        p,
        flags=re.IGNORECASE,
    )

    # Retirer les labels structurés (PRIMARY SUBJECT:, SCENE ATMOSPHERE:, etc.)
    # qui se faisaient dessiner sur l'image par Imagen.
    p = re.sub(
        r"\b(PRIMARY SUBJECT|SCENE ATMOSPHERE|AI INTERPRETATION HINT|COMPOSITION|NEGATIVE PROMPT|PROMPT|SUBJECT|STYLE)\b[^\n:]*[:\-–]\s*",
        "",
        p,
        flags=re.IGNORECASE,
    )

    # Convertir tout saut de ligne en espace : on veut un seul paragraphe continu.
    p = p.replace("\n", " ").replace("\r", " ")
    p = re.sub(r"\s+", " ", p).strip(" ,.;:")

    # Supprimer uniquement les déclencheurs VHS/camcorder (HUD caméscope indésirable).
    # En mode low_poly_3d, on conserve explicitement les termes 3D/low-poly.
    mots_a_supprimer = [
        r"\bvhs\b",
        r"\bcamcorder\b",
        r"\bcamcorder[-\s]?style\b",
        r"\bfound[-\s]?footage\b",
        r"\bhome[-\s]?video\b",
        r"\btape[-\s]?artefacts?\b",
        r"\bscan[-\s]?lines?\b",
        r"\bviewfinder\b",
        r"\bvideo[-\s]?noise\b",
        r"\bvintage[-\s]?video\b",
        r"\bamateur[-\s]?footage\b",
        r"\barchive[-\s]?footage\b",
    ]
    if STYLE_SUFFIX != STYLE_SUFFIX_LOW_POLY_3D:
        mots_a_supprimer.extend([r"\b3d render\b", r"\blow[-\s]?poly\b"])
    for pattern in mots_a_supprimer:
        p = re.sub(pattern, "", p, flags=re.IGNORECASE)

    # Nettoyer les doubles virgules ou espaces vides suite aux suppressions
    p = re.sub(r",\s*,", ",", p)
    p = re.sub(r"\s+", " ", p).strip(" ,.;:")

    # Préfixe ancrant le style demandé (appliqué via le suffixe pour les détails).
    if STYLE_SUFFIX == STYLE_SUFFIX_NOIR:
        if not p.lower().startswith("black and white"):
            p = "Black and white crime scene photography depicting " + p
    elif STYLE_SUFFIX == STYLE_SUFFIX_LOW_POLY_3D:
        if not p.lower().startswith("cinematic 3d low-poly"):
            p = "Cinematic 3D low-poly render depicting " + p
    else:
        if not p.lower().startswith("anime illustration"):
            p = "Anime illustration style depicting " + p

    # Suffixe global de style en phrases continues (jamais en liste de tags).
    if "completely free of any written text" not in p.lower():
        p += STYLE_SUFFIX

    # Nettoyage final des ponctuations
    p = re.sub(r",\s*,", ",", p)
    p = re.sub(r"\s+", " ", p).strip(" ,.;:")

    if len(p) > 1200:
        p = p[:1200]
    return p


# ═══════════════════════════════════════════════════════════════════════════════
#  GÉNÉRATION IMAGEN 4
# ═══════════════════════════════════════════════════════════════════════════════
def generer_image_imagen4(prompt: str, chemin_jpg: str) -> bool:
    global IMAGEN_QUOTA_EPUISE
    if not gemini_client or IMAGEN_QUOTA_EPUISE:
        return False

    prompt_clean = nettoyer_prompt(prompt)
    print(f"      📝 Prompt final Imagen : {prompt_clean[:90]}...")

    for model in [IMAGEN_MODEL_STANDARD, IMAGEN_MODEL_FAST]:
        label = model.split("-generate")[0]
        for attempt in range(3):
            try:
                print(f"      🎨 [{label}] Essai {attempt + 1}/3...")
                response = gemini_client.models.generate_images(
                    model=model,
                    prompt=prompt_clean,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/jpeg",
                        aspect_ratio="9:16",
                    ),
                )

                if not response.generated_images:
                    print("      ⚠️ Aucun pixel renvoyé")
                    time.sleep(2)
                    continue

                img_bytes = response.generated_images[0].image.image_bytes
                with open(chemin_jpg, "wb") as f:
                    f.write(img_bytes)

                if os.path.getsize(chemin_jpg) > 5000:
                    print(
                        f"      ✅ [{label}] Succès -> {os.path.basename(chemin_jpg)}"
                    )
                    return True
                else:
                    print("      ⚠️ Fichier trop petit -> retry")

            except Exception as e:
                msg = str(e)
                if "429" in msg or "quota" in msg.lower():
                    print(f"      ⏹️ Quota atteint pour le modèle {label} : {msg[:100]}")
                    if model == IMAGEN_MODEL_FAST:
                        print(
                            "      ⏹️ Imagen quota totalement atteint -> désactivation temporaire de la session"
                        )
                        IMAGEN_QUOTA_EPUISE = True
                        return False
                    else:
                        print("      👉 Passage au modèle suivant...")
                        break
                if "safety" in msg.lower() or "blocked" in msg.lower():
                    print(
                        "      ⚠️ Bloqué par le filtre de sécurité de ce modèle -> passage au modèle suivant"
                    )
                    break
                print(f"      ⚠️ Erreur Imagen (Essai {attempt + 1}) : {msg[:120]}")
                time.sleep(3 * (attempt + 1))

    return False


def generer_image_pollinations(prompt: str, chemin_jpg: str) -> bool:
    """Fallback IA sans API pour garder un vrai mix archive/reconstitution."""
    if not ALLOW_POLLINATIONS_FALLBACK:
        return False
    try:
        prompt_clean = nettoyer_prompt(prompt)
        prompt_clean += (
            " The framing should look like a historically plausible reenactment. "
            "The image must contain no logos, no watermark, and no written text of any kind."
        )
        prompt_clean = prompt_clean[:950]
        encoded = urllib.parse.quote(prompt_clean)
        seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(prompt_clean)) % 1000000
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={TARGET_W}&height={TARGET_H}&seed={seed}&nologo=true&private=true&enhance=true"
        )
        print("      🧠 [Pollinations IA] Fallback reconstitution...")
        resp = requests.get(url, timeout=35)
        if resp.status_code != 200 or len(resp.content) < 5000:
            print(
                f"      ⚠️ Pollinations réponse invalide ({resp.status_code}, {len(resp.content)} octets)"
            )
            return False
        from PIL import Image

        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        img.save(chemin_jpg, "JPEG", quality=92, optimize=True)
        if os.path.getsize(chemin_jpg) > 5000:
            print(
                f"      ✅ [Pollinations IA] Succès -> {os.path.basename(chemin_jpg)}"
            )
            return True
    except Exception as e:
        print(f"      ⚠️ Échec Pollinations IA : {str(e)[:120]}")
    if os.path.exists(chemin_jpg):
        try:
            os.remove(chemin_jpg)
        except OSError:
            pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  TÉLÉCHARGEMENT VIDÉOS DE STOCK (PEXELS PORTRAIT)
# ═══════════════════════════════════════════════════════════════════════════════
def telecharger_pexels_video(query: str, chemin_mp4: str) -> bool:
    """Recherche et télécharge une vidéo portrait libre de droits sur Pexels."""
    if not PEXELS_API_KEY:
        return False
    try:
        clean_q = re.sub(r"[^\w\s]", " ", query).strip()
        url = f"https://api.pexels.com/videos/search?query={clean_q}&per_page=5&orientation=portrait"
        print(f"      🔍 Pexels Video Search : '{clean_q}'")
        r = requests.get(
            url, headers={"Authorization": PEXELS_API_KEY}, timeout=15
        ).json()
        videos = r.get("videos", [])
        if videos:
            video = videos[0]
            files = video.get("video_files", [])
            best_link = None

            # Cherche un fichier MP4 au format portrait
            for vf in files:
                if vf.get("file_type") == "video/mp4":
                    link = vf.get("link")
                    w = vf.get("width", 0)
                    h = vf.get("height", 0)
                    if link and h > w:
                        best_link = link
                        break
            # Fallback sur le premier lien MP4 si pas de format portrait strict
            if not best_link and files:
                for vf in files:
                    if vf.get("file_type") == "video/mp4" and vf.get("link"):
                        best_link = vf.get("link")
                        break

            if best_link:
                resp = requests.get(best_link, timeout=45, stream=True)
                if resp.status_code == 200:
                    with open(chemin_mp4, "wb") as f:
                        for chunk in resp.iter_content(65536):
                            f.write(chunk)
                    if os.path.getsize(chemin_mp4) > 50000:
                        print(
                            f"      🎥 [Pexels Video] Vidéo téléchargée -> {os.path.basename(chemin_mp4)}"
                        )
                        return True
    except Exception as e:
        print(f"      ⚠️ Échec téléchargement vidéo Pexels pour '{query}' : {e}")
    return False


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


def telecharger_pexels_image(query: str, chemin: str) -> bool:
    if not PEXELS_API_KEY:
        return False
    try:
        r = requests.get(
            f"https://api.pexels.com/v1/search?query={query}&per_page=10&orientation=portrait",
            headers={"Authorization": PEXELS_API_KEY},
            timeout=15,
        ).json()
        photos = r.get("photos", [])
        if photos:
            url = random.choice(photos)["src"]["large2x"]
            resp = requests.get(url, timeout=30, stream=True)
            if resp.status_code == 200:
                with open(chemin, "wb") as f:
                    for chunk in resp.iter_content(32768):
                        f.write(chunk)
                if os.path.getsize(chemin) > 5000:
                    print(
                        f"      🖼️ [Pexels Image] Téléchargée -> {os.path.basename(chemin)}"
                    )
                    return True
    except Exception as e:
        print(f"      ⚠️ Pexels Image : {e}")
    return False


def telecharger_pixabay_image(query: str, chemin: str) -> bool:
    if not PIXABAY_API_KEY:
        return False
    try:
        r = requests.get(
            f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}"
            f"&image_type=photo&orientation=vertical&per_page=10",
            timeout=15,
        ).json()
        hits = r.get("hits", [])
        if hits:
            url = random.choice(hits).get("largeImageURL", "")
            resp = requests.get(url, timeout=30, stream=True)
            if resp.status_code == 200:
                with open(chemin, "wb") as f:
                    for chunk in resp.iter_content(32768):
                        f.write(chunk)
                if os.path.getsize(chemin) > 5000:
                    print(
                        f"      🖼️ [Pixabay Image] Téléchargée -> {os.path.basename(chemin)}"
                    )
                    return True
    except Exception as e:
        print(f"      ⚠️ Pixabay Image : {e}")
    return False


def telecharger_bing_image(
    query: str,
    chemin_jpg: str,
    contexte_niche: str = "",
    context_histoire: str = "",
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Recherche et télécharge une image réelle depuis Bing Images avec SafeSearch strict et validation IA en 2 phases."""
    if MAX_BING_RESULTS <= 0:
        return False
    try:
        search_query = enrichir_requete_archive(query, contexte_niche)

        print(f"      🔍 Recherche Bing Image : '{search_query}'")
        # SafeSearch=Strict obligatoire + filtre de taille moyenne ou large
        url = (
            f"https://www.bing.com/images/search"
            f"?q={urllib.parse.quote(search_query)}"
            f"&safeSearch=Strict"
            f"&first=1"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": "SRCHHPGUSR=ADLT=STRICT",  # Force SafeSearch côté cookie également
        }
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return False

        decoded = html.unescape(r.text)
        urls = re.findall(r'"murl":"(https?://[^"]+)"', decoded)
        if not urls:
            return False

        attempts_tested = 0
        for img_url in urls[:MAX_BING_RESULTS]:
            try:
                # ── Filtre 1 : Extension et domaines suspects connus (sans téléchargement) ──
                if any(
                    x in img_url.lower()
                    for x in [".gif", ".webp", "doubleclick", "adsystem"]
                ):
                    continue
                if url_est_suspecte(img_url):
                    print(f"      🚫 URL bloquée (domaine suspect) : {img_url[:60]}")
                    continue

                attempts_tested += 1
                print(
                    f"      📥 [Essai {attempts_tested}] Téléchargement : {img_url[:70]}..."
                )
                resp = requests.get(
                    img_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                    timeout=10,
                    stream=True,
                )
                if resp.status_code != 200:
                    continue

                # Vérifier le Content-Type avant d'écrire
                content_type = resp.headers.get("Content-Type", "")
                if not any(
                    t in content_type
                    for t in ["image/jpeg", "image/png", "image/jpg", "image/webp"]
                ):
                    print(
                        f"      ⚠️ Content-Type non-image ({content_type[:30]}) — ignoré"
                    )
                    continue

                with open(chemin_jpg, "wb") as f:
                    for chunk in resp.iter_content(32768):
                        f.write(chunk)

                if os.path.getsize(chemin_jpg) < 15000:
                    # Image trop petite (miniature ou erreur)
                    os.remove(chemin_jpg)
                    continue

                # ── Filtre 2 : Validation IA en 2 phases (NSFW + Pertinence) ──
                if valider_image_historique(
                    chemin_jpg,
                    context_histoire or query,
                    search_query,
                    scene_text,
                    veo_prompt,
                ):
                    print(
                        f"      ✅ [Real Photo] Validée -> {os.path.basename(chemin_jpg)}"
                    )
                    return True
                else:
                    if os.path.exists(chemin_jpg):
                        os.remove(chemin_jpg)
                    print("      ↩️  Rejetée, on essaie la suivante...")

            except Exception as e:
                print(f"      ⚠️ Échec pour {img_url[:50]} : {e}")
                if os.path.exists(chemin_jpg):
                    os.remove(chemin_jpg)

    except Exception as e:
        print(f"      ⚠️ Erreur recherche Bing pour '{query}' : {e}")
    return False


def _ddg_vqd(session: requests.Session, query: str) -> str:
    r = session.get(
        "https://duckduckgo.com/",
        params={"q": query, "iax": "images", "ia": "images"},
        timeout=DDG_TIMEOUT,
    )
    if r.status_code not in (200, 202):
        return ""
    m = (
        re.search(r'vqd="([^"]+)"', r.text)
        or re.search(r"vqd='([^']+)'", r.text)
        or re.search(r"vqd=([^&]+)&", r.text)
    )
    return m.group(1) if m else ""


def _ddg_image_results(session: requests.Session, search_query: str) -> list:
    """Retourne les résultats DDG avec cache court pour éviter de refaire la même recherche."""
    cache_key = search_query.lower().strip()
    if cache_key in DDG_RESULT_CACHE:
        return DDG_RESULT_CACHE[cache_key]

    vqd = _ddg_vqd(session, search_query)
    if not vqd:
        DDG_RESULT_CACHE[cache_key] = []
        return []

    r = session.get(
        "https://duckduckgo.com/i.js",
        params={
            "l": "us-en",
            "o": "json",
            "q": search_query,
            "vqd": vqd,
            "f": ",,,",
            "p": "1",
            "u": "bing",
        },
        timeout=DDG_TIMEOUT,
    )
    if r.status_code != 200:
        DDG_RESULT_CACHE[cache_key] = []
        return []

    results = r.json().get("results", [])[:MAX_DDG_RESULTS]
    DDG_RESULT_CACHE[cache_key] = results
    return results


def telecharger_duckduckgo_image(
    query: str,
    chemin_jpg: str,
    contexte_niche: str = "",
    context_histoire: str = "",
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Recherche DuckDuckGo Images. Souvent meilleur que Bing pour les cas documentaires."""
    search_queries = construire_requetes_reelles(
        query, scene_text, contexte_niche, context_histoire
    )[:MAX_DDG_QUERIES_PER_PLAN]
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    )

    for search_query in search_queries:
        try:
            print(f"      🦆 Recherche DDG Image : '{search_query}'")
            results = _ddg_image_results(session, search_query)
            for idx, result in enumerate(results, 1):
                img_url = result.get("image") or result.get("thumbnail") or ""
                if not img_url or url_est_suspecte(img_url):
                    continue
                print(f"      📥 [DDG {idx}] {result.get('title', '')[:70]}...")
                if not telecharger_image_url(img_url, chemin_jpg, "DDG image"):
                    continue
                if (not STRICT_REAL_VALIDATION) or valider_image_historique(
                    chemin_jpg,
                    context_histoire or query,
                    search_query,
                    scene_text,
                    veo_prompt,
                ):
                    print(
                        f"      ✅ [DDG Real Photo] Validée -> {os.path.basename(chemin_jpg)}"
                    )
                    return True
                if os.path.exists(chemin_jpg):
                    os.remove(chemin_jpg)
                print("      ↩️  DDG rejetée, on essaie la suivante...")
        except Exception as e:
            print(f"      ⚠️ Erreur DDG pour '{search_query}' : {e}")
            if os.path.exists(chemin_jpg):
                os.remove(chemin_jpg)
    return False


def telecharger_source_curated(
    query: str,
    chemin_jpg: str,
    contexte_niche: str = "",
    context_histoire: str = "",
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Essaie d'abord quelques sources connues pour une affaire précise.

    Scoring pondéré: la requête et le texte du sous-titre (ce qui est dit à l'écran)
    pèsent beaucoup plus que le veo_prompt (ambiance générique de la scène). Un
    candidat dont aucun keyword ne touche la query OU le scene_text est rejeté:
    c'est ce qui faisait gagner "snow mountain" face à "Mercury Montego" pour un
    sous-titre qui parle explicitement de la voiture.
    """
    q_str = (query or "").lower()
    scene_str = (scene_text or "").lower()
    veo_str = re.sub(
        r"\[STYLE LOCK[^\]]*\]", "", (veo_prompt or ""), flags=re.IGNORECASE
    ).lower()
    niche_str = (contexte_niche or "").lower()
    hist_str = (context_histoire or "").lower()
    haystack = " ".join([q_str, scene_str, veo_str, niche_str, hist_str])

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
        case_key = "yuba"
    elif "enfield" in haystack:
        case_key = "enfield"
    else:
        case_key = ""
    if not case_key:
        return False

    candidates = []
    for item in CURATED_CASE_IMAGES.get(case_key, []):
        kws = item["keywords"]
        # Poids éditoriaux : query >> scene_text > veo_prompt >> contexte global.
        hits_query = sum(1 for kw in kws if kw in q_str)
        hits_scene = sum(1 for kw in kws if kw in scene_str)
        hits_veo = sum(1 for kw in kws if kw in veo_str)
        hits_ctx = sum(1 for kw in kws if kw in niche_str or kw in hist_str)
        score = hits_query * 5 + hits_scene * 3 + hits_veo * 1 + hits_ctx * 1

        # Garde-fou : si la query ET le scene_text mentionnent un sujet précis
        # (voiture / personne / lieu / objet), un candidat sans aucun mot du
        # sujet est rejeté, même si son ambiance matche le veo_prompt.
        subject_match = (hits_query > 0) or (hits_scene > 0)
        if not subject_match:
            continue
        candidates.append((score, hits_query, hits_scene, item))

    if not candidates:
        # Aucun candidat ne matche le sujet : on n'invente pas, on laisse le
        # pipeline tomber sur DDG/Bing/Imagen au lieu de poser une image hors-sujet.
        print(
            "      ⛔ Aucune source curated ne matche le sujet de la requête/sous-titre"
        )
        return False

    # Tri: (score total, hits_query, hits_scene) tous décroissants.
    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    for score, hits_q, hits_s, item in candidates[:10]:
        print(
            f"      📚 Source curated : {item['label']} (score={score} q={hits_q} s={hits_s})"
        )
        if not telecharger_image_url(item["url"], chemin_jpg, item["label"]):
            continue
        # 1) Sécurité NSFW : non négociable.
        if not verifier_securite_image(chemin_jpg):
            if os.path.exists(chemin_jpg):
                os.remove(chemin_jpg)
            print("      ↩️  Source curated rejetée par sécurité")
            continue
        # 2) Pertinence Gemini : on n'a plus le droit de trust aveugle, car le
        # vrai bug du projet Yuba venait d'un keyword "snow/mountain" qui matchait
        # un paysage sans voiture pour un sous-titre qui parlait de la Montego.
        if STRICT_REAL_VALIDATION and not TRUST_CURATED_SOURCES:
            if not valider_image_historique(
                chemin_jpg, context_histoire or query, query, scene_text, veo_prompt
            ):
                if os.path.exists(chemin_jpg):
                    os.remove(chemin_jpg)
                print("      ↩️  Source curated rejetée par pertinence Gemini")
                continue
        print(
            f"      ✅ [Curated Real Photo] Validée -> {os.path.basename(chemin_jpg)}"
        )
        return True

    return False


def image_est_trop_noire(chemin_jpg: str) -> bool:
    """Détecte un fond noir de secours pour ne pas le recycler dans un rendu final."""
    try:
        from PIL import Image, ImageStat

        with Image.open(chemin_jpg) as im:
            im = im.convert("L").resize((32, 56))
            mean = ImageStat.Stat(im).mean[0]
            return mean < 18
    except Exception:
        return False


def reutiliser_media_backup(
    dir_img: str, scene_key: str, plan_index: int, chemin_jpg: str, role: str
) -> bool:
    """Réutilise une ancienne image déjà validée si l'API de génération est indisponible.
    Utile quand Imagen atteint son quota: on garde un rendu complet au lieu d'un écran noir.
    """
    projet_dir = os.path.dirname(os.path.dirname(dir_img))
    plan_name = f"plan_{plan_index + 1}.jpg"
    candidates = []
    try:
        for name in os.listdir(projet_dir):
            if not name.startswith("media_backup_"):
                continue
            p = os.path.join(projet_dir, name, "real_media", scene_key, plan_name)
            if (
                os.path.exists(p)
                and os.path.getsize(p) > 5000
                and not image_est_trop_noire(p)
            ):
                candidates.append(p)
    except Exception:
        return False

    for candidate in sorted(candidates, reverse=True):
        try:
            shutil.copy(candidate, chemin_jpg)
            normaliser_image(chemin_jpg)
            print(
                f"      ♻️  Média {role} réutilisé depuis backup -> {os.path.basename(chemin_jpg)}"
            )
            return True
        except Exception as e:
            print(f"      ⚠️ Réutilisation backup échouée : {e}")
    return False


def creer_fond_noir(chemin_jpg: str) -> bool:
    try:
        from PIL import Image as PILImage

        img = PILImage.new("RGB", (TARGET_W, TARGET_H), color=(10, 10, 10))
        img.save(chemin_jpg, format="JPEG", quality=85)
        print(f"      ⬛ Fond de secours noir créé -> {os.path.basename(chemin_jpg)}")
        return True
    except Exception:
        return False


def creer_reconstitution_locale(prompt: str, chemin_jpg: str) -> bool:
    """Dernier filet visuel quand Imagen ET Pollinations échouent.

    REWRITTEN 2026-05-26 : produit un fallback ATMOSPHÉRIQUE NEUTRE, sans
    aucune forme reconnaissable (figures, véhicules, objets). L'ancienne
    version dessinait des silhouettes + hexagones qui dominaient l'écran et
    ne ressemblaient à rien de cinématographique. La nouvelle version
    produit une image qui passe pour un still de documentaire (chiaroscuro
    + brouillard + grain photo) sans contenu spécifique — ne distrait pas,
    laisse le sous-titre et le HUD éditorial faire le boulot narratif.
    """
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFilter, ImageEnhance

        seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(prompt or "")) % 1000003
        rng = random.Random(seed)

        # Dégradé vertical profond — base "salle vide film noir"
        img = PILImage.new("RGB", (TARGET_W, TARGET_H), (8, 9, 11))
        draw = ImageDraw.Draw(img, "RGBA")
        for y in range(TARGET_H):
            t = y / TARGET_H
            # Plus sombre en haut et bas, légèrement plus clair au milieu
            mid = 1.0 - abs(0.5 - t) * 2.0
            r = int(8 + 22 * mid)
            g = int(9 + 24 * mid)
            b = int(11 + 28 * mid)
            draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b, 255))

        # Halo doux décentré (chiaroscuro spotlight)
        halo_x = rng.randint(int(TARGET_W * 0.25), int(TARGET_W * 0.75))
        halo_y = rng.randint(int(TARGET_H * 0.30), int(TARGET_H * 0.55))
        halo_r = rng.randint(380, 560)
        halo = PILImage.new("L", (TARGET_W, TARGET_H), 0)
        hd = ImageDraw.Draw(halo)
        hd.ellipse(
            [halo_x - halo_r, halo_y - halo_r, halo_x + halo_r, halo_y + halo_r],
            fill=58,
        )
        halo = halo.filter(ImageFilter.GaussianBlur(180))
        light = PILImage.new("RGB", (TARGET_W, TARGET_H), (228, 226, 218))
        img = PILImage.composite(light, img, halo)

        # Brouillard / particules — quelques poussières discrètes
        draw = ImageDraw.Draw(img, "RGBA")
        for _ in range(rng.randint(80, 160)):
            x = rng.randint(0, TARGET_W)
            y = rng.randint(int(TARGET_H * 0.15), int(TARGET_H * 0.85))
            a = rng.randint(8, 36)
            r = rng.randint(1, 3)
            draw.ellipse([x, y, x + r, y + r], fill=(255, 250, 240, a))

        # Conversion N&B + boost contraste cinéma
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(1.45)
        img = ImageEnhance.Brightness(img).enhance(0.90)
        img = img.convert("RGB")

        # Grain photo argentique léger
        noise = PILImage.effect_noise(
            (TARGET_W, TARGET_H), rng.uniform(20, 34)
        ).convert("L")
        img = PILImage.blend(img, noise.convert("RGB"), 0.12)

        # Vignette circulaire
        vignette = PILImage.new("L", (TARGET_W, TARGET_H), 0)
        vd = ImageDraw.Draw(vignette)
        vd.ellipse(
            [-220, -120, TARGET_W + 220, TARGET_H + 180],
            fill=235,
        )
        vignette = vignette.filter(ImageFilter.GaussianBlur(180))
        dark = PILImage.new("RGB", (TARGET_W, TARGET_H), (0, 0, 0))
        img = PILImage.composite(img, dark, vignette)

        img.save(chemin_jpg, "JPEG", quality=90, optimize=True)
        print(
            f"      🖼️ Reconstitution locale neutre créée -> {os.path.basename(chemin_jpg)}"
        )
        return True
    except Exception as e:
        print(f"      ⚠️ Reconstitution locale échouée : {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAITEMENT DE CHAQUE PLAN
# ═══════════════════════════════════════════════════════════════════════════════
VEO_PROMPT_DEFAUT = (
    "A lone figure standing in a foggy cinematic scene, centered vertical composition, "
    "faceted low-poly 3D geometry, cold desaturated lighting, mysterious true-crime atmosphere"
)


def traiter_plan_unique(
    scene_key: str,
    i: int,
    plan: dict,
    dir_img: str,
    dir_vid: str,
    contexte_niche: str = "",
    context_histoire: str = "",
) -> str:
    veo_prompt = plan.get("veo_prompt", "") or VEO_PROMPT_DEFAUT
    real_queries = plan.get("real_media_queries", [])
    scene_text = plan.get("text_segment", "")

    chemin_jpg = os.path.join(dir_img, f"plan_{i + 1}.jpg")
    chemin_mp4 = os.path.join(dir_img, f"plan_{i + 1}.mp4")

    # Cache check
    if os.path.exists(chemin_mp4) and os.path.getsize(chemin_mp4) > 50000:
        if os.path.exists(chemin_jpg):
            os.remove(chemin_jpg)
        print(f"   ⏭️  {scene_key}/plan_{i + 1} (Vidéo) -> cache OK")
        return chemin_mp4

    if os.path.exists(chemin_jpg) and os.path.getsize(chemin_jpg) > 500:
        if plan.get("source_type") in [
            "generated_local",
            "generated_pollinations",
            "fallback_local",
            "fallback_black",
        ]:
            print(
                f"      🗑️ Image cache local/fallback trouvé ({plan.get('source_type')}), suppression pour régénération..."
            )
            try:
                os.remove(chemin_jpg)
            except OSError:
                pass
        else:
            if os.path.exists(chemin_mp4):
                os.remove(chemin_mp4)
            print(f"   ⏭️  {scene_key}/plan_{i + 1} (Image) -> cache OK")
            return chemin_jpg

    print(f"\n   🎬 {scene_key} / plan_{i + 1}")

    media_role = choisir_role_media(
        scene_key, i, plan, contexte_niche, context_histoire
    )
    plan["media_role"] = media_role
    print(f"      🎚️ Choix éditorial : {media_role.upper()}")

    real_queries_strict = [
        q
        for q in real_queries
        if (not REAL_MEDIA_ONLY)
        or requete_affaire_specifique(q, contexte_niche, context_histoire)
    ]

    if media_role == "real":
        # ── PRIORITÉ 0 : Vidéo Pexels désactivée par défaut.
        # C'est du stock, pas de l'archive vérifiable, donc trop risqué pour les "vrais médias".
        if ALLOW_PEXELS_VIDEO and real_queries_strict:
            for query in real_queries_strict:
                if telecharger_pexels_video(query, chemin_mp4):
                    if os.path.exists(chemin_jpg):
                        os.remove(chemin_jpg)
                    plan["source_type"] = "real_video"
                    return chemin_mp4

        # ── PRIORITÉ 0.5 : Photos réelles.
        # Enfield et autres affaires connues : on exploite d'abord les sources
        # curated variées, puis DDG court, puis Bing en filet de secours.
        if real_queries_strict:
            for query in real_queries_strict:
                if telecharger_source_curated(
                    query,
                    chemin_jpg,
                    contexte_niche,
                    context_histoire,
                    scene_text,
                    veo_prompt,
                ):
                    normaliser_image(chemin_jpg)
                    if os.path.exists(chemin_mp4):
                        os.remove(chemin_mp4)
                    plan["source_type"] = "curated_real"
                    return chemin_jpg
                if telecharger_duckduckgo_image(
                    query,
                    chemin_jpg,
                    contexte_niche,
                    context_histoire,
                    scene_text,
                    veo_prompt,
                ):
                    normaliser_image(chemin_jpg)
                    if os.path.exists(chemin_mp4):
                        os.remove(chemin_mp4)
                    plan["source_type"] = "real_search"
                    return chemin_jpg
                if telecharger_bing_image(
                    query,
                    chemin_jpg,
                    contexte_niche,
                    context_histoire,
                    scene_text,
                    veo_prompt,
                ):
                    normaliser_image(chemin_jpg)
                    if os.path.exists(chemin_mp4):
                        os.remove(chemin_mp4)
                    plan["source_type"] = "real_search"
                    return chemin_jpg

        elif REAL_MEDIA_ONLY:
            print(
                "      ⛔ Aucune requête assez spécifique à l'affaire pour du vrai média"
            )

    if REAL_MEDIA_ONLY:
        print(
            "      ⛔ REAL_MEDIA_ONLY=1 : génération IA et stock désactivés pour ce plan"
        )
        creer_fond_noir(chemin_jpg)
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "fallback_black"
        return chemin_jpg

    # ── PRIORITÉ 1 : Imagen 4 avec métaphorisation IA ──
    # Le sous-titre EXACT du plan (ce que la voix off dit pendant cette image)
    # passe en tête du prompt et hérite du poids le plus fort. Le veo_prompt
    # (ambiance générique de la scène) ne sert que de fond stylistique. Avant,
    # scene_text était tronqué en suffixe à 260 caractères et Imagen prenait
    # ses ordres dans le veo_prompt — d'où une "cuisine avec une mère" générée
    # alors que le sous-titre énumérait cinq hommes.
    #
    # IMPORTANT : on construit ici une phrase en langage naturel continu, sans
    # labels du type "PRIMARY SUBJECT: ..." qu'Imagen rendrait visuellement
    # comme du texte dans l'image.
    clean_veo = re.sub(
        r"\[STYLE LOCK[^\]]*\]", "", veo_prompt, flags=re.IGNORECASE
    ).strip()
    clean_veo = re.sub(
        r"\bthe Hesperus\b|\bHesperus\b",
        "an unmarked 1900 Scottish lighthouse tender",
        clean_veo,
        flags=re.IGNORECASE,
    )
    narration = (scene_text or "").strip()

    parts = []
    if clean_veo:
        parts.append(
            f"Create exactly this visual scene: {clean_veo[:850]}. "
            "Preserve the stated number of people, the stated lighting state, the concrete action, and the camera composition."
        )
    if narration:
        parts.append(
            "The image illustrates a narrated documentary beat, but it must never show the narration as captions or writing."
        )
    metaphorized = ""
    if STYLE_SUFFIX != STYLE_SUFFIX_LOW_POLY_3D:
        metaphorized = metaphoriser_prompt_avec_gemini(veo_prompt)
    if metaphorized and metaphorized.lower() not in (clean_veo or "").lower():
        parts.append(f"The overall visual feel is {metaphorized}.")
    parts.append(
        "All clothing, buildings, equipment, flags and vessel hulls are blank and unmarked. "
        "There are no readable words, names, letters, numbers, signs, logos, captions or interface elements anywhere. "
        "This is a fresh original frame that does not repeat earlier shots in the sequence."
    )
    generation_prompt = " ".join(parts)
    if generer_image_imagen4(generation_prompt, chemin_jpg):
        normaliser_image(chemin_jpg)
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "generated"
        return chemin_jpg

    if generer_image_pollinations(generation_prompt, chemin_jpg):
        normaliser_image(chemin_jpg)
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "generated_pollinations"
        return chemin_jpg

    if media_role == "generated" and reutiliser_media_backup(
        dir_img, scene_key, i, chemin_jpg, "IA"
    ):
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "generated_reused"
        return chemin_jpg

    if media_role == "generated" and creer_reconstitution_locale(
        generation_prompt, chemin_jpg
    ):
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "generated_local"
        return chemin_jpg

    # ── PRIORITÉ REPLI 1.5 : si Imagen échoue, tenter une vraie image avant le stock.
    if real_queries_strict:
        for query in real_queries_strict:
            if telecharger_duckduckgo_image(
                query,
                chemin_jpg,
                contexte_niche,
                context_histoire,
                scene_text,
                veo_prompt,
            ):
                normaliser_image(chemin_jpg)
                if os.path.exists(chemin_mp4):
                    os.remove(chemin_mp4)
                plan["source_type"] = "real_search_after_imagen"
                return chemin_jpg
            if telecharger_source_curated(
                query,
                chemin_jpg,
                contexte_niche,
                context_histoire,
                scene_text,
                veo_prompt,
            ):
                normaliser_image(chemin_jpg)
                if os.path.exists(chemin_mp4):
                    os.remove(chemin_mp4)
                plan["source_type"] = "curated_real_after_imagen"
                return chemin_jpg

    if not ALLOW_STOCK_FALLBACKS:
        print(
            "      ⛔ Stock Pexels/Pixabay désactivé : fallback reconstitution locale"
        )
        if not creer_reconstitution_locale(generation_prompt, chemin_jpg):
            creer_fond_noir(chemin_jpg)
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = (
            "fallback_local"
            if not image_est_trop_noire(chemin_jpg)
            else "fallback_black"
        )
        return chemin_jpg

    # ── PRIORITÉ 2 : Pexels Stock avec boucle de dégradation de mots-clés ──
    for q in real_queries + [veo_prompt]:
        mots_cles = extraire_mots_cles(q)
        words = mots_cles.split()
        for limit in range(len(words), 0, -1):
            query_degraded = " ".join(words[:limit])
            print(f"      🔄 Fallback Pexels dégradé : '{query_degraded}'")
            if telecharger_pexels_image(query_degraded, chemin_jpg):
                normaliser_image(chemin_jpg)
                if os.path.exists(chemin_mp4):
                    os.remove(chemin_mp4)
                plan["source_type"] = "stock_pexels"
                return chemin_jpg

    # ── PRIORITÉ 3 : Pixabay Stock avec boucle de dégradation de mots-clés ──
    for q in real_queries + [veo_prompt]:
        mots_cles = extraire_mots_cles(q)
        words = mots_cles.split()
        for limit in range(len(words), 0, -1):
            query_degraded = " ".join(words[:limit])
            print(f"      🔄 Fallback Pixabay dégradé : '{query_degraded}'")
            if telecharger_pixabay_image(query_degraded, chemin_jpg):
                normaliser_image(chemin_jpg)
                if os.path.exists(chemin_mp4):
                    os.remove(chemin_mp4)
                plan["source_type"] = "stock_pixabay"
                return chemin_jpg

    # ── PRIORITÉ 4 : Requêtes génériques de secours ──
    for query in [
        "dark mystery night fog",
        "abandoned room shadows",
        "shadow silhouette dark",
    ]:
        if telecharger_pexels_image(query, chemin_jpg):
            normaliser_image(chemin_jpg)
            if os.path.exists(chemin_mp4):
                os.remove(chemin_mp4)
            plan["source_type"] = "stock_pexels_generic"
            return chemin_jpg
        if telecharger_pixabay_image(query, chemin_jpg):
            normaliser_image(chemin_jpg)
            if os.path.exists(chemin_mp4):
                os.remove(chemin_mp4)
            plan["source_type"] = "stock_pixabay_generic"
            return chemin_jpg

    # ── DERNIER RECOURS : Fond noir ──
    creer_fond_noir(chemin_jpg)
    if os.path.exists(chemin_mp4):
        os.remove(chemin_mp4)
    plan["source_type"] = "fallback_black"
    return chemin_jpg


# ═══════════════════════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════════════════
def traiter_fetcher(dossier_projet: str):
    plan_path = f"{dossier_projet}/visual_plan.json"
    if not os.path.exists(plan_path):
        print(f"❌ visual_plan.json introuvable : {plan_path}")
        return

    global STYLE_SUFFIX
    script_path = f"{dossier_projet}/script.json"
    niche = ""
    visual_bible = {}
    script_data = {}
    if os.path.exists(script_path):
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script_data = json.load(f)
                niche = script_data.get("niche", "")
                # Sélectionner le style visuel selon le projet
                visual_style = script_data.get("visual_style", "low_poly_3d")
                if visual_style in {"low_poly_3d", "3d", "low-poly"}:
                    STYLE_SUFFIX = STYLE_SUFFIX_LOW_POLY_3D
                    style_label = "3D low-poly cinematic"
                elif visual_style == "noir":
                    STYLE_SUFFIX = STYLE_SUFFIX_NOIR
                    style_label = "noir B&W"
                else:
                    STYLE_SUFFIX = STYLE_SUFFIX_ANIME
                    style_label = "anime couleur"
                print(f"   🎨 Style visuel : {visual_style.upper()} ({style_label})")
                # Charger la visual_bible pour la consistance des personnages
                raw_bible = script_data.get("visual_bible", {})
                if isinstance(raw_bible, dict):
                    visual_bible = raw_bible
                # Enrichir depuis personnages (format mystère : prenom + description_visuelle)
                for p in script_data.get("personnages", []):
                    if isinstance(p, dict):
                        key = p.get("prenom") or p.get("nom")
                        desc = p.get("description_visuelle", "")
                        if key and desc:
                            visual_bible[key] = desc
        except Exception as e:
            print(f"⚠️ Impossible de lire script.json : {e}")

    # Obtenir le contexte court de l'affaire en anglais
    contexte_niche = obtenir_mots_cles_contexte(niche) if niche else ""

    with open(plan_path, "r", encoding="utf-8") as f:
        visual_plan = json.load(f)

    # Injecter la visual_bible dans chaque plan pour la consistance des personnages
    if visual_bible:
        for scene_key, plans in visual_plan.items():
            # Récupérer le texte de la scène correspondante
            scene_num = int(scene_key.split("_")[1]) - 1
            scenes = (
                script_data.get("scenes", []) if os.path.exists(script_path) else []
            )
            scene_text = (
                scenes[scene_num].get("audio_tts", "")
                if 0 <= scene_num < len(scenes)
                else ""
            )
            for plan in plans:
                veo = plan.get("veo_prompt", "")
                # Chercher quel personnage est mentionné dans le veo_prompt ou la scène
                injected = []
                for nom, desc in visual_bible.items():
                    if nom.lower() in veo.lower() or nom.lower() in scene_text.lower():
                        # Injecter seulement les 80 premiers chars de la description
                        injected.append(f"{nom}: {desc[:80]}")
                if injected:
                    char_ctx = " | ".join(injected)
                    # L'action reste en tête : Imagen doit d'abord comprendre
                    # le plan, puis utiliser la bible comme contrainte de cohérence.
                    plan["veo_prompt"] = f"{veo} [CHARACTERS: {char_ctx}]"

    # L'audit Gemini peut être désactivé pour des médias Imagen déjà contrôlés
    # visuellement. Cela évite qu'une réponse ambiguë du classifieur supprime de
    # bons rendus pendant une régénération ciblée.
    if SKIP_CACHE_AUDIT:
        print("   ⏭️  Audit du cache désactivé (SKIP_CACHE_AUDIT=1)")
    else:
        auditer_et_nettoyer_cache(dossier_projet, visual_plan, niche or contexte_niche)

    src = "Imagen 4 (Gemini API)" if gemini_client else "Pexels/Pixabay (stock)"
    print("═" * 56)
    print(f"  🎨 ÉTAPE 2.7 : MEDIA FETCHER — {src}")
    print("═" * 56)
    if visual_bible:
        print(
            f"   👥 Visual bible : {len(visual_bible)} personnage(s) injectés dans les prompts"
        )

    work = []
    for scene_key, plans in visual_plan.items():
        num = scene_key.split("_")[1]
        dir_img = f"{dossier_projet}/real_media/scene_{num}"
        dir_vid = f"{dossier_projet}/video/scene_{num}"
        os.makedirs(dir_img, exist_ok=True)
        os.makedirs(dir_vid, exist_ok=True)
        for i, plan in enumerate(plans):
            work.append((scene_key, i, plan, dir_img, dir_vid, contexte_niche, niche))

    print(f"\n   🚀 {len(work)} médias à traiter (séquentiel)...\n")

    ok = 0
    for w in work:
        scene_key, i, plan, _, _, _, _ = w
        try:
            fichier = traiter_plan_unique(*w)
            plan["file_path"] = fichier
            if fichier:
                ok += 1
        except Exception as e:
            print(f"   ❌ {scene_key}/plan_{i + 1} exception : {e}")
            plan["file_path"] = ""
        # Pause courte pour respecter les rate-limits
        time.sleep(1.5)

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(visual_plan, f, indent=4, ensure_ascii=False)

    total = len(work)
    print(f"\n{'═' * 56}")
    print(f"  ✅ Fetcher terminé : {ok}/{total} médias créés")
    print(f"{'═' * 56}")


if __name__ == "__main__":
    d = trouver_dernier_projet()
    if d:
        traiter_fetcher(d)
    else:
        print("📁 Aucun projet trouvé.")
