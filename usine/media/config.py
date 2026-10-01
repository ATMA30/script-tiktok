"""Configuration du media fetcher : clés API, client Gemini, style visuel et réglages."""

import os
from dotenv import load_dotenv


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai

        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("✅ Moteur IA (Gemini API) initialisé")
    except Exception as e:
        print(f"⚠️ Gemini SDK indisponible : {e}")

# Formats acceptés à l'ouverture d'une image venue du web : Pillow devine sinon le
# format d'après le contenu, ce qui expose ses décodeurs exotiques (PSD, FITS…).
FORMATS_IMAGE = ("JPEG", "PNG", "WEBP")

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
