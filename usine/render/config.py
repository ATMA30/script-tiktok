"""Configuration du rendu : chemins, client Gemini et réglages lus dans l'environnement."""

import os
from dotenv import load_dotenv
from google import genai
from pathlib import Path


load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


# Racine du projet (usine/render/config.py → ../../)
ROOT = Path(__file__).resolve().parents[2]
RENDER_ROOT = ROOT / "hyperframes_render"
WIDTH, HEIGHT = 1080, 1920
FPS = 30
HF_VERSION = "0.5.7"

# USE_IMAGES = True → utilise les images du projet (real_media/scene_N/*.jpg)
#                    avec les overlays éditoriaux par-dessus (hybride)
# USE_IMAGES = False → 100% procédural (HTML/CSS/SVG/GSAP, pas d'images)
# Surcharge possible via env : USE_IMAGES=1 / USE_IMAGES=0
USE_IMAGES = os.getenv("USE_IMAGES", "1") == "1"
MOTION_STRENGTH = float(os.getenv("MOTION_STRENGTH", "2.0"))

# Overlays documentaires (carte, année, dossier, compteur…) : déterministes,
# activés par défaut. Le Director Agent (Gemini) reste opt-in car non déterministe :
#   USE_SEMANTIC_OVERLAYS=0 python 3_render_hyperframes.py
#   USE_DIRECTOR_AGENT=1 python 3_render_hyperframes.py
USE_SEMANTIC_OVERLAYS = os.getenv("USE_SEMANTIC_OVERLAYS", "1") == "1"
USE_DIRECTOR_AGENT = os.getenv("USE_DIRECTOR_AGENT", "0") == "1"
# Accents Lottie (bibliothèque assets/lottie). Opt-in : sans Director Agent,
# un preset déterministe choisit quelques accents par scène.
#   USE_LOTTIE_OVERLAYS=1 python 3_render_hyperframes.py
USE_LOTTIE_OVERLAYS = os.getenv("USE_LOTTIE_OVERLAYS", "0") == "1"
# Whoosh SFX on every dramatic red word — disabled by default because it ends
# up triggering on every scene (each scene has at least one dramatic word) and
# becomes irritating. Re-enable per-render with USE_WHOOSH_SFX=1.
USE_WHOOSH_SFX = os.getenv("USE_WHOOSH_SFX", "0") == "1"

# Carte « HISTOIRE VRAIE » juste après le hook. Elle décale la scène 2 : la voix
# ne reprend qu'après la carte. 0.8 s pour garder l'élan TikTok (était 2.20 s).
# SKIP_TRUTH_CARD=1 supprime totalement la carte.
TRUTH_PREROLL_SECONDS = float(os.getenv("TRUTH_PREROLL_SECONDS", "0.8"))
SKIP_TRUTH_CARD = os.getenv("SKIP_TRUTH_CARD", "0") == "1"

# Hook visuel sobre sur la scène 1 (titre en fondu, sans flash)
USE_HOOK_INTRO = os.getenv("USE_HOOK_INTRO", "1") == "1"

# CTA d'abonnement sur la dernière scène (DESIGN.md : 1,5 à 1,8 s en fin de vidéo)
USE_OUTRO_CTA = os.getenv("USE_OUTRO_CTA", "1") == "1"
# Logo Yūrei en haut à droite, faible opacité (DESIGN.md)
USE_BRAND_LOGO = os.getenv("USE_BRAND_LOGO", "1") == "1"
BRAND_LOGO_DEFAUT = ROOT / "assets" / "brand" / "logo_yurei.png"
BRAND_LOGO_PATH = os.getenv("BRAND_LOGO_PATH", str(BRAND_LOGO_DEFAUT))
USE_SCROLL_HOOK = os.getenv("USE_SCROLL_HOOK", "0") == "1"
SCROLL_HOOK_TEXT = os.getenv(
    "SCROLL_HOOK_TEXT",
    "CETTE AFFAIRE A DÉCLENCHÉ UNE VRAIE ENQUÊTE DE POLICE",
)
TARGET_LUFS = float(os.getenv("TARGET_LUFS", "-14.0"))
USE_DRAMATIC_SILENCE = os.getenv("USE_DRAMATIC_SILENCE", "0") == "1"
DRAMATIC_EVENT_SCENES = os.getenv(
    "DRAMATIC_EVENT_SCENES",
    "4:vide,9:disparu",
)

# Secondes de queue après la voix sur la dernière scène (CTA + musique seuls)
OUTRO_TAIL_SECONDS = float(os.getenv("OUTRO_TAIL_SECONDS", "3.5"))

# SFX synthétiques générés à la volée si assets/sfx/ vide (whoosh, sub-drop, riser)
USE_SYNTH_SFX = os.getenv("USE_SYNTH_SFX", "1") == "1"

# Musique d'ambiance stressante (cherche musiques/[projet]_ambient.{mp3,wav}
# et la génère via 2.3_generate_music.py si absente)
USE_AMBIENT_MUSIC = os.getenv("USE_AMBIENT_MUSIC", "1") == "1"
AMBIENT_MUSIC_VOLUME = float(os.getenv("AMBIENT_MUSIC_VOLUME", "0.45"))
POST_MIX_MUSIC_VOLUME = float(os.getenv("POST_MIX_MUSIC_VOLUME", "0.28"))

# Color grading par acte : froid (intro) → cyan tendu (corps) → rouge (climax)
USE_ACT_GRADING = os.getenv("USE_ACT_GRADING", "1") == "1"

# Désactive COMPLÈTEMENT toutes transitions inter-scènes : aucun flash, aucun
# voile noir/rouge au moment du cut. Hard cut pur pour que l'image suivante soit
# perceptible immédiatement. Remettre DISABLE_SCENE_TRANSITIONS=0 pour l'ancien
# style avec transitions cinématiques.
DISABLE_SCENE_TRANSITIONS = os.getenv("DISABLE_SCENE_TRANSITIONS", "1") == "1"

# Film grain animé (look 35mm documentaire)
USE_FILM_GRAIN = os.getenv("USE_FILM_GRAIN", "1") == "1"

# Tag « DOSSIER · ID » en coin + couches de réalisation « enquête » (scan, cadre).
# Désactivé par défaut : DESIGN.md proscrit les HUD d'investigation décoratifs.
USE_PERSISTENT_CASE_TAG = os.getenv("USE_PERSISTENT_CASE_TAG", "0") == "1"

# Letterbox cinéma (barres noires haut/bas légères)
USE_LETTERBOX = os.getenv("USE_LETTERBOX", "1") == "1"

# Vignette qui respire (pulse lent)
USE_BREATHING_VIGNETTE = os.getenv("USE_BREATHING_VIGNETTE", "1") == "1"

# Chromatic aberration sur les mots .emph (apparition)
USE_CHROMATIC_EMPH = os.getenv("USE_CHROMATIC_EMPH", "0") == "1"

# Sync sous-titres mot-par-mot via faster-whisper (élimine le drift de fin)
USE_WHISPER_SYNC = os.getenv("USE_WHISPER_SYNC", "1") == "1"

# Backgrounds procéduraux alternés par scène (variété sans images)
BG_VARIANTS = ["minimal", "minimal", "minimal", "mesh", "minimal", "lines"]
