"""
Render final TikTok video from script.json + audios + images using HyperFrames.

Visual style : drama intime / confession 1ʳᵉ personne
- 3D Ken Burns (perspective + dolly/orbit/tilt par scène)
- Transitions whip-blur douces entre scènes
- Intro épisode sobre (numéro + titre, fade doux)
- Sous-titres avec mots émotionnels clés en blanc chaud
- Film grain + vignette cinématique
- Pas de glitch, pas de HUD, pas de tag CLASSIFIED

Headless (Puppeteer + Chromium) — CI-friendly. No browser GUI opens.
"""

import os
import re
import json
import hashlib
import shutil
import subprocess
import argparse
import unicodedata
from pathlib import Path
from utils import trouver_dernier_projet
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Optional
from lottie_overlay import (
    build_lottie_overlays_for_scene,
    lottie_head_html,
    load_manifest as load_lottie_manifest,
    manifest_choices_summary as lottie_choices_summary,
)

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


class LottieOverlaySpec(BaseModel):
    asset_id: str = Field(
        description="ID of the Lottie asset to play. Must exactly match one of the IDs listed in the LOTTIE LIBRARY catalog."
    )
    in_time: float = Field(
        description="Relative timestamp in seconds within this scene (0.0 = scene start) when the overlay starts."
    )
    duration: float = Field(
        description="Playback duration in seconds. Use 0 to fall back to the asset's natural duration. Keep < scene length."
    )
    x_pct: float = Field(
        description="Horizontal center of the overlay in percent of frame width (0 left, 50 center, 100 right)."
    )
    y_pct: float = Field(
        description="Vertical center of the overlay in percent of frame height (0 top, 50 center, 100 bottom)."
    )
    width_pct: float = Field(
        description="Width of the overlay in percent of frame width. 100 = full width. Use ~30-60 for accents."
    )
    height_pct: float = Field(
        description="Height of the overlay in percent of frame height. Match width_pct for square assets, 100 for full-screen sweeps."
    )
    opacity: float = Field(
        description="Opacity 0.0-1.0. Atmospheric overlays: 0.4-0.7. Punctual reveals: 0.8-1.0."
    )
    monochrome: bool = Field(
        description="Whether to force grayscale to match the cinema true-crime palette. Almost always true."
    )
    reason: str = Field(
        description="One short sentence (<= 100 chars) explaining why this overlay punctuates this exact narration moment."
    )


class SceneDirectorPlan(BaseModel):
    strategy: str = Field(
        description="Visual strategy chosen for this scene (e.g. dramatic push-in, dark grid background, technical scanning)."
    )
    background_effect: str = Field(
        description="Procedural background type: 'mesh', 'lines', 'topo', 'dotgrid', 'scanline', or 'minimal'."
    )
    camera_move: str = Field(
        description="Camera motion style: 'dolly_in', 'dolly_out', 'pan_left', 'pan_right', 'zoom_pan', or 'static'."
    )
    glitch_triggers: List[float] = Field(
        description="Relative timestamps (in seconds, e.g., 1.5, 3.2, between 0.0 and scene duration) when digital glitch interference triggers. Return empty list if no glitch is needed."
    )
    vignette_intensity: float = Field(
        description="Intensity multiplier for vignette, from 0.7 (lighter) to 1.3 (darker/vignette heavy)."
    )
    hud_effect: str = Field(
        description="HUD style overlay: 'scanner', 'ticker', 'radar', or 'none'."
    )
    lottie_overlays: List[LottieOverlaySpec] = Field(
        default_factory=list,
        description="0 to 3 Lottie motion-graphic accents to layer on top of this scene. Pick from the LOTTIE LIBRARY only. Use sparingly — one good accent per scene beats three muddled ones. Return [] if the scene is already strong without overlays.",
    )


ROOT = Path(__file__).parent.resolve()
RENDER_ROOT = ROOT / "hyperframes_render"
WIDTH, HEIGHT = 1080, 1920
FPS = 30
HF_VERSION = "0.5.7"

# Les images doivent être présentes/décodées avant leur timecode réel. Sinon
# Chromium peut rendre 1-2 frames noires au moment où HyperFrames rend le clip
# visible pour la première fois.
# 0.0 = pas de preload, opacity:1 inline immédiat (v22, comportement validé).
# Tester >0 si Chromium décode trop lentement, mais cela peut réintroduire un
# bref noir au moment du scene_start si le tl.set GSAP est retardé.
IMAGE_PRELOAD_LEAD_SECONDS = float(os.getenv("IMAGE_PRELOAD_LEAD_SECONDS", "0.6"))

# USE_IMAGES = True → utilise les images du projet (real_media/scene_N/*.jpg)
#                    avec les overlays éditoriaux par-dessus (hybride)
# USE_IMAGES = False → 100% procédural (HTML/CSS/SVG/GSAP, pas d'images)
# Surcharge possible via env : USE_IMAGES=1 / USE_IMAGES=0
USE_IMAGES = os.getenv("USE_IMAGES", "1") == "1"
MOTION_STRENGTH = float(os.getenv("MOTION_STRENGTH", "2.0"))

# Agents IA de composition: puissants mais non déterministes.
# Les overlays sémantiques sont déterministes et activés par défaut.
# Les agents IA restent désactivés sauf demande explicite:
#   USE_SEMANTIC_OVERLAYS=0 python 3_render_hyperframes.py
#   USE_DIRECTOR_AGENT=1 python 3_render_hyperframes.py
#   USE_GENERATIVE_OVERLAYS=1 python 3_render_hyperframes.py
#   USE_AI_OVERLAY_DETECTION=1 python 3_render_hyperframes.py
USE_SEMANTIC_OVERLAYS = os.getenv("USE_SEMANTIC_OVERLAYS", "0") == "1"
USE_DIRECTOR_AGENT = os.getenv("USE_DIRECTOR_AGENT", "0") == "1"
# Lottie motion-graphic overlays. When the Director Agent is disabled, a
# deterministic paranormal preset chooses a few scene-relevant accents.
# Keep this opt-in so existing drama renders remain unchanged:
#   USE_LOTTIE_OVERLAYS=1 python 3_render_hyperframes.py
USE_LOTTIE_OVERLAYS = os.getenv("USE_LOTTIE_OVERLAYS", "0") == "1"
# Whoosh SFX on every dramatic red word — disabled by default because it ends
# up triggering on every scene (each scene has at least one dramatic word) and
# becomes irritating. Re-enable per-render with USE_WHOOSH_SFX=1.
USE_WHOOSH_SFX = os.getenv("USE_WHOOSH_SFX", "0") == "1"
USE_GENERATIVE_OVERLAYS = os.getenv("USE_GENERATIVE_OVERLAYS", "0") == "1"
USE_AI_OVERLAY_DETECTION = os.getenv("USE_AI_OVERLAY_DETECTION", "0") == "1"

# Pause lisible juste après le hook. Elle décale la scène 2, donc la voix ne
# démarre qu'après la carte noire.
# 2026-05 : raccourcie à 0.8s pour conserver l'élan TikTok (était 2.20s).
# SKIP_TRUTH_CARD=1 supprime totalement la carte (rendu plus punchy).
TRUTH_PREROLL_SECONDS = float(os.getenv("TRUTH_PREROLL_SECONDS", "3.00"))
SKIP_TRUTH_CARD = (
    os.getenv("SKIP_TRUTH_CARD", "1") == "1"
)  # drama : pas de carte VÉRITÉ

# Hook visuel sobre sur scène 1 (numéro épisode + fade doux, sans flash ni tag CASE)
USE_HOOK_INTRO = os.getenv("USE_HOOK_INTRO", "0") == "1"

# Outro / CTA "Part 2 ?" sur dernière scène
USE_OUTRO_CTA = os.getenv("USE_OUTRO_CTA", "0") == "1"
USE_BRAND_LOGO = os.getenv("USE_BRAND_LOGO", "0") == "1"
BRAND_LOGO_PATH = os.getenv(
    "BRAND_LOGO_PATH", str(ROOT / "assets" / "brand" / "logo_yurei.png")
)
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
# Note : on ajoute 0.6s de marge interne pour éviter le clip-out HyperFrames
# à la frontière exacte du root duration.
OUTRO_TAIL_SECONDS = float(os.getenv("OUTRO_TAIL_SECONDS", "3.5"))
OUTRO_TAIL_SAFETY_MARGIN = 0.6  # s avant la fin du root, le CTA fade out doux

# Subtitle "punch" mode : scale boost, glow rouge, stroke plus épais sur .emph
USE_PUNCH_SUBTITLES = os.getenv("USE_PUNCH_SUBTITLES", "1") == "1"

# SFX synthétiques générés à la volée si assets/sfx/ vide (whoosh, sub-drop, riser)
USE_SYNTH_SFX = os.getenv("USE_SYNTH_SFX", "1") == "1"

# Musique d'ambiance stressante (cherche musiques/[projet]_ambient.{mp3,wav}
# et la génère via 2.3_generate_music.py si absente)
USE_AMBIENT_MUSIC = os.getenv("USE_AMBIENT_MUSIC", "1") == "1"
AMBIENT_MUSIC_VOLUME = float(os.getenv("AMBIENT_MUSIC_VOLUME", "0.45"))
POST_MIX_MUSIC_VOLUME = float(os.getenv("POST_MIX_MUSIC_VOLUME", "0.28"))

# Color grading par acte : froid (intro) → cyan tendu (corps) → rouge (climax)
USE_ACT_GRADING = os.getenv("USE_ACT_GRADING", "1") == "1"

# Transitions variées entre scènes (flash, rgb-glitch, zoom-blur, hard-cut, fade-rouge)
USE_VARIED_TRANSITIONS = os.getenv("USE_VARIED_TRANSITIONS", "1") == "1"

# Désactive COMPLÈTEMENT toutes transitions inter-scènes : aucun flash, aucun
# voile noir/rouge au moment du cut. Hard cut pur pour que l'image suivante soit
# perceptible immédiatement. Remettre DISABLE_SCENE_TRANSITIONS=0 pour l'ancien
# style avec transitions cinématiques.
DISABLE_SCENE_TRANSITIONS = os.getenv("DISABLE_SCENE_TRANSITIONS", "1") == "1"

# Film grain animé (look 35mm documentaire)
USE_FILM_GRAIN = os.getenv("USE_FILM_GRAIN", "1") == "1"

# Tag CASE discret en coin permanent — désactivé pour le drama intime
USE_PERSISTENT_CASE_TAG = os.getenv("USE_PERSISTENT_CASE_TAG", "0") == "1"

# Letterbox cinéma (barres noires haut/bas légères)
USE_LETTERBOX = os.getenv("USE_LETTERBOX", "1") == "1"

# Vignette qui respire (pulse lent)
USE_BREATHING_VIGNETTE = os.getenv("USE_BREATHING_VIGNETTE", "1") == "1"

# Chromatic aberration sur les mots .emph (apparition)
USE_CHROMATIC_EMPH = os.getenv("USE_CHROMATIC_EMPH", "0") == "1"

# Sync sous-titres mot-par-mot via faster-whisper (élimine le drift de fin)
USE_WHISPER_SYNC = os.getenv("USE_WHISPER_SYNC", "1") == "1"

# Modèle Whisper global lazy-loaded (chargé une seule fois pour toutes les scènes)
_WHISPER_MODEL = None

# Backgrounds procéduraux alternés par scène (variété sans images)
BG_VARIANTS = ["minimal", "minimal", "minimal", "mesh", "minimal", "lines"]

# Mots auto-highlightés en rouge dans les sous-titres
DRAMATIC_KEYWORDS_FR = [
    "trahison",
    "trahi",
    "trahie",
    "trahir",
    "abandonné",
    "abandonnée",
    "quitté",
    "quittée",
    "menti",
    "mensonge",
    "mensonges",
    "jamais",
    "plus rien",
    "tout perdu",
    "erreur",
    "faute",
    "responsable",
    "silence",
    "seul",
    "seule",
    "peur",
    "honte",
    "culpabilité",
    "confiance",
    "aimé",
    "aimée",
    "détruit",
    "détruite",
    "brisé",
    "brisée",
    "regret",
    "regrette",
    "trop tard",
    "réalisé",
    "compris",
    "découvert",
    "aveugle",
    "naïf",
    "naïve",
    "remplacé",
    "remplacée",
    "viré",
    "virée",
    "utilisé",
    "utilisée",
    "manipulé",
    "manipulée",
    "disparu",
    "disparue",
    "disparus",
    "disparues",
    "disparaître",
    "disparition",
    "introuvable",
    "introuvables",
    "vide",
    "personne",
    "impossible",
    "inexpliqué",
    "inexpliquée",
    "ombre",
    "ombres",
    "fantôme",
    "fantômes",
    "hanté",
    "hantée",
    "cri",
    "cris",
    "nuit",
    "tempête",
    "corps",
    "trace",
    "traces",
    "retrouvé",
    "retrouvée",
    "retrouvés",
    "retrouvées",
    "emportés",
    "emportées",
    "urgence",
    "arrêtée",
    "arrêté",
    "vides",
    "tordues",
    "monstrueuse",
    "détaché",
    "détachée",
    "intacte",
    "dame",
    "blanche",
    "route",
    "auto-stoppeuse",
    "pâle",
    "rétroviseur",
    "banquette",
    "volatilisée",
    "morte",
    "accident",
    "effrayant",
    "froid",
    "virage",
    "hurle",
    "freine",
    "gendarmerie",
    "contradiction",
    "explication",
    "llorona",
    "emmurée",
    "mort",
]


def ffprobe_duration(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return float(out.stdout.strip())


def html_escape(s):
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── Phosphor-style icons (inline SVG) ─────────────────────────
ICONS = {
    "lock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="1.5"/><path d="M8 11V7a4 4 0 1 1 8 0v4"/></svg>',
    "warning": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 21h20L12 3z"/><line x1="12" y1="10" x2="12" y2="15"/><circle cx="12" cy="18" r="0.5" fill="currentColor"/></svg>',
    "file": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>',
    "eye": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3" fill="currentColor"/></svg>',
    "radio": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2" fill="currentColor"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49M19.07 4.93a10 10 0 0 1 0 14.14M7.76 16.24a6 6 0 0 1 0-8.49M4.93 19.07a10 10 0 0 1 0-14.14"/></svg>',
}


def emphasize_words(text):
    """Wrap only meaningful dramatic keywords in a red <span>."""
    escaped = html_escape(text)
    emph_class = "emph chromatic" if USE_CHROMATIC_EMPH else "emph"
    # 1. Keywords (case-insensitive, word boundary)
    pattern = r"\b(" + "|".join(re.escape(w) for w in DRAMATIC_KEYWORDS_FR) + r")\b"
    new_text, n = re.subn(
        pattern,
        lambda m: f'<span class="{emph_class}">{m.group(0)}</span>',
        escaped,
        flags=re.IGNORECASE,
    )
    if n > 0:
        return new_text
    return escaped


def red_word_indices(text):
    """Retourne les indices des mots d'un texte qui seront coloriés en rouge."""
    cleaned = re.sub(r"\[.*?\]", "", text).strip()
    words = cleaned.split()
    indices = []
    if not words:
        return indices

    # 1. Chercher les mots clés dramatiques
    has_keywords = False
    for idx, w in enumerate(words):
        w_clean = re.sub(r"[^\w]", "", w).lower()
        if w_clean in DRAMATIC_KEYWORDS_FR:
            indices.append(idx)
            has_keywords = True

    return indices


def _split_by_word_budget(sentence, max_words):
    """Découpe une phrase en sous-chunks de ≤ max_words mots, en cassant
    de préférence sur la ponctuation interne ou les conjonctions."""
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]
    # Points de coupe préférés : virgule, point-virgule, deux-points, tiret long
    break_words = set([",", ";", ":", "—", "–"])
    conjunctions = {
        "mais",
        "et",
        "puis",
        "alors",
        "or",
        "donc",
        "car",
        "parce",
        "lorsque",
        "quand",
        "tandis",
        "pendant",
        "après",
        "avant",
    }
    chunks, current = [], []
    for i, w in enumerate(words):
        current.append(w)
        # Coupe naturelle si on dépasse max_words ET on est sur un point de coupe
        if len(current) >= max_words:
            # Tente de couper sur le prochain point naturel proche
            stripped = w.rstrip(",;:—–").lower()
            ends_with_break = any(w.endswith(b) for b in break_words)
            if (
                ends_with_break
                or stripped in conjunctions
                or len(current) >= max_words + 2
            ):
                chunks.append(" ".join(current))
                current = []
    if current:
        chunks.append(" ".join(current))
    # Fusionne tout chunk final < 3 mots avec le précédent (évite "Shaffer?" tout seul)
    if len(chunks) >= 2 and len(chunks[-1].split()) < 3:
        chunks[-2] = chunks[-2] + " " + chunks[-1]
        chunks.pop()
    return chunks


def split_subtitle(text, duration, max_chunks=3, max_words=6):
    """Découpe le texte en chunks de ≤ max_words mots, distribution pondérée.
    Phrase-aware (ponctuation), avec sous-découpe par budget de mots."""
    text = re.sub(r"\[STYLE LOCK[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[.*?\]", "", text).strip()
    text = re.sub(r"\.{2,}", "…", text)
    text = re.sub(r"\s+([,.;!?…])", r"\1", text)
    text = re.sub(r"(?<!\S)\.(?!\S)", "", text)
    # 1. Découpe par phrases
    sentences = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]
    if not sentences:
        sentences = [text]
    # 2. Pour chaque phrase, sous-découpe par budget de mots
    parts = []
    for s in sentences:
        parts.extend(_split_by_word_budget(s, max_words))
    parts = [p.strip() for p in parts if re.search(r"[\wÀ-ÿ]", p)]
    # 3. Si encore trop de chunks, on fusionne par buckets pour respecter max_chunks
    if len(parts) > max_chunks:
        bucket_size = (len(parts) + max_chunks - 1) // max_chunks
        merged = []
        for i in range(0, len(parts), bucket_size):
            merged.append(" ".join(parts[i : i + bucket_size]))
        parts = merged
    if not parts:
        parts = [text]
    # 4. Pondération par nombre de mots (pacing proportionnel à la voix)
    weights = [max(1, len(p.split())) for p in parts]
    total_w = sum(weights)
    chunks, cursor = [], 0.0
    for p, w in zip(parts, weights):
        d = duration * (w / total_w)
        chunks.append({"text": p, "start": cursor, "duration": d})
        cursor += d
    return chunks


def load_visual_source_map(projet_dir):
    """Mappe chaque fichier média vers son source_type pour piloter le rendu."""
    plan_path = Path(projet_dir) / "visual_plan.json"
    source_map = {}
    if not plan_path.exists():
        return source_map
    try:
        visual_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return source_map

    for scene_key, plans in visual_plan.items():
        for idx, plan in enumerate(plans):
            source_type = plan.get("source_type", "")
            candidates = []
            file_path = plan.get("file_path")
            if file_path:
                candidates.append(Path(file_path))
            candidates.append(
                Path(projet_dir) / "real_media" / scene_key / f"plan_{idx + 1}.jpg"
            )
            candidates.append(
                Path(projet_dir) / "video" / scene_key / f"plan_{idx + 1}.mp4"
            )
            for candidate in candidates:
                try:
                    source_map[str(candidate.resolve())] = source_type
                except Exception:
                    pass
    return source_map


def pick_images(projet_dir, scene_idx, scene=None):
    """Récupère toutes les images disponibles pour une scène en fusionnant les sources.
    Si aucune image n'est trouvée pour la scène spécifique, on cherche dans les dossiers globaux du projet.
    """
    all_imgs = []
    excluded_media = set()
    if isinstance(scene, dict):
        for key in ("exclude_media", "excluded_media", "media_exclude"):
            values = scene.get(key) or []
            if isinstance(values, str):
                values = [values]
            excluded_media.update(str(v) for v in values)

    # 1. Sources spécifiques à la scène
    scene_folders = [
        projet_dir / "real_media" / f"scene_{scene_idx + 1}",
        projet_dir / "video" / f"scene_{scene_idx + 1}",
        projet_dir / "images" / f"scene_{scene_idx + 1}",
    ]

    for d in scene_folders:
        if d.is_dir():
            imgs = sorted(
                [
                    p
                    for p in d.iterdir()
                    if p.suffix.lower()
                    in (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".mp4",
                        ".mov",
                        ".m4v",
                        ".webm",
                    )
                    and p.name not in excluded_media
                ]
            )
            all_imgs.extend(imgs)

    # 2. Si toujours rien, on pioche dans les dossiers globaux (pour éviter le noir)
    if not all_imgs:
        global_folders = [
            projet_dir / "real_media",
            projet_dir / "video",
            projet_dir / "images",
        ]
        for d in global_folders:
            if d.is_dir():
                # On prend les images qui ne sont pas dans des sous-dossiers "scene_X"
                imgs = [
                    p
                    for p in d.iterdir()
                    if p.is_file()
                    and p.suffix.lower()
                    in (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".mp4",
                        ".mov",
                        ".m4v",
                        ".webm",
                    )
                    and p.name not in excluded_media
                ]
                all_imgs.extend(imgs)

    # 3. Déduplication par nom de fichier
    seen = set()
    unique_imgs = []
    for img in all_imgs:
        if img.name not in seen:
            unique_imgs.append(img)
            seen.add(img.name)

    # 4. Si on a des images globales mais qu'on veut de la variété, on mélange un peu si on en a peu
    if len(unique_imgs) > 0:
        # On utilise le scene_idx pour "shifter" la sélection de façon déterministe
        shift = scene_idx % len(unique_imgs)
        unique_imgs = unique_imgs[shift:] + unique_imgs[:shift]

    return unique_imgs


# ── Motion variants : micro-mouvements lisibles.
# Les médias réels doivent rester compréhensibles: pas de zoom/crop destructeur.
# Chaque variant porte aussi une "ease" et une "intensity" (1.0 = base, <1 plus
# calme, >1 plus tendu) pour que le rythme respire d'un plan à l'autre.
MOTION_VARIANTS = [
    # push-in posé
    {
        "start": {"scale": 1.0, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0},
        "end": {"scale": 1.028, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0},
        "ease": "power2.out",
        "intensity": 1.00,
    },
    # pan latéral gauche -> droite, scale stable
    {
        "start": {
            "scale": 1.018,
            "x": -12,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.018,
            "x": 12,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "sine.inOut",
        "intensity": 0.85,
    },
    # pull-out lent (révélation)
    {
        "start": {
            "scale": 1.032,
            "x": 0,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {"scale": 1.0, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0},
        "ease": "power3.inOut",
        "intensity": 0.92,
    },
    # pan vertical haut -> bas
    {
        "start": {
            "scale": 1.020,
            "x": 0,
            "y": 12,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.020,
            "x": 0,
            "y": -12,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "sine.inOut",
        "intensity": 0.90,
    },
    # push-in avec drift bas-droite (tension)
    {
        "start": {
            "scale": 1.0,
            "x": 0,
            "y": -6,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.030,
            "x": 10,
            "y": 8,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "power2.inOut",
        "intensity": 1.10,
    },
    # diagonale gauche-bas -> haut-droite
    {
        "start": {
            "scale": 1.018,
            "x": -10,
            "y": -8,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.018,
            "x": 10,
            "y": 8,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "sine.inOut",
        "intensity": 0.88,
    },
    # zoom serré (révélation forte)
    {
        "start": {
            "scale": 1.005,
            "x": 0,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.045,
            "x": -6,
            "y": 4,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "expo.out",
        "intensity": 1.20,
    },
    # drift très lent (plans contemplatifs)
    {
        "start": {
            "scale": 1.012,
            "x": 4,
            "y": -4,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.022,
            "x": -6,
            "y": 6,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "sine.inOut",
        "intensity": 0.75,
    },
    # push-in droite -> gauche (réorientation)
    {
        "start": {
            "scale": 1.008,
            "x": 12,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.030,
            "x": -8,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "power2.inOut",
        "intensity": 1.05,
    },
    # statique + très léger souffle (preuve)
    {
        "start": {
            "scale": 1.000,
            "x": 0,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {"scale": 1.012, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0},
        "ease": "sine.out",
        "intensity": 0.70,
    },
]


def gsap_obj(d):
    """Convertit un dict Python en littéral d'objet GSAP."""
    return "{" + ", ".join(f"{k}: {v}" for k, v in d.items()) + "}"


def build_procedural_bg(scene_idx, scene_start, audio_duration, bg_type=None):
    """Génère un background procédural (pas d'image). Alterne 6 variantes."""
    if bg_type and bg_type in [
        "mesh",
        "lines",
        "topo",
        "dotgrid",
        "scanline",
        "minimal",
    ]:
        variant = bg_type
    else:
        variant = BG_VARIANTS[scene_idx % len(BG_VARIANTS)]
    bg_id = f"s{scene_idx + 1}_bg"
    inner = '<div class="pbg-scan"></div>' if variant == "scanline" else ""
    html = (
        f'<div id="{bg_id}" class="pbg pbg-{variant} clip" '
        f'data-start="{scene_start:.3f}" data-duration="{audio_duration:.3f}" '
        f'data-track-index="{scene_idx * 20 + 9}">{inner}</div>'
    )
    js = [
        f'gsap.set("#{bg_id}", {{opacity: 0}});',
        f'tl.set("#{bg_id}", {{opacity: 1}}, {scene_start:.3f});',
        f'tl.to("#{bg_id}", {{opacity: 0, duration: 0.8, ease: "power2.in"}}, {(scene_start + audio_duration - 0.4):.3f});',
        f'tl.set("#{bg_id}", {{opacity: 0}}, {(scene_start + audio_duration):.3f});',
    ]
    # Motion subtile selon la variante
    if variant == "mesh":
        # Drift très lent du gradient mesh
        js.append(
            f'tl.fromTo("#{bg_id}", {{backgroundPosition: "0% 0%"}}, '
            f'{{backgroundPosition: "100% 100%", duration: {audio_duration:.3f}, '
            f'ease: "none", overwrite: "auto"}}, {scene_start:.3f});'
        )
    elif variant == "dotgrid":
        js.append(
            f'tl.fromTo("#{bg_id}", {{backgroundPosition: "0px 0px"}}, '
            f'{{backgroundPosition: "40px 60px", duration: {audio_duration:.3f}, '
            f'ease: "none", overwrite: "auto"}}, {scene_start:.3f});'
        )
    elif variant == "scanline":
        # Scan vertical lent
        js.append(
            f'tl.fromTo("#{bg_id} .pbg-scan", {{y: "-30%"}}, '
            f'{{y: "130%", duration: {audio_duration:.3f}, ease: "none"}}, {scene_start:.3f});'
        )
    elif variant == "lines":
        js.append(
            f'tl.fromTo("#{bg_id}", {{backgroundPosition: "0px 0px"}}, '
            f'{{backgroundPosition: "0px 80px", duration: {audio_duration:.3f}, '
            f'ease: "none"}}, {scene_start:.3f});'
        )
    return html, js


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

SEMANTIC_ANIMATION_TYPES = [
    "map_zoom",
    "message_send",
    "phone_call",
    "email_sent",
    "cctv_scan",
    "file_open",
    "redacted_report",
    "year_marker",
    "timeline_pin",
    "counter",
    "missing_person",
    "search_grid",
    "evidence_photo",
    "fingerprint_scan",
    "audio_waveform",
    "radio_signal",
    "police_lights",
    "route_trace",
    "door_open",
    "key_object",
    "medical_scan",
    "lab_sample",
    "newspaper_clip",
    "court_record",
    "classified_stamp",
    "entity_radar",
    "weather_alert",
    "storm_warning",
    "footprint_trail",
    "blood_trace",
    "fire_burst",
    "smoke_fog",
    "underground_depth",
    "coordinates_lock",
    "interrogation_note",
    "witness_card",
    "clock_tick",
    "warning_flash",
    "archive_box",
    "question_prompt",
]

SEMANTIC_ANIMATION_TYPES.extend(
    [
        "true_story_card",
        "last_seen_marker",
        "floor_plan",
        "exit_scan",
        "blind_spot",
        "corridor_scan",
        "motion_detector",
        "security_log",
        "missing_poster",
        "family_photo",
        "witness_quote",
        "case_board",
        "evidence_thread",
        "theory_stack",
        "official_denial",
        "document_leak",
        "breaking_news",
        "calendar_flip",
        "time_jump",
        "timeline_split",
        "mind_control",
        "memory_flash",
        "experiment_chamber",
        "thermal_scan",
        "dna_spiral",
        "heartbeat_monitor",
        "voice_print",
        "signal_jammer",
        "satellite_sweep",
        "map_pin_drop",
        "proximity_alert",
        "power_cut",
        "neon_bar",
        "searchlight",
        "basement_elevator",
        "sealed_door",
        "archive_stamp",
        "object_isolate",
        "crowd_noise",
        "room_tone",
    ]
)

SEMANTIC_META = {
    "map_zoom": {
        "label": "LOCALISATION",
        "detail": "Zoom satellite",
        "icon": "pin",
        "family": "map",
    },
    "message_send": {
        "label": "MESSAGE SORTANT",
        "detail": "Texte saisi puis envoyé",
        "icon": "radio",
        "family": "message",
    },
    "phone_call": {
        "label": "APPEL TRACE",
        "detail": "Signal téléphonique",
        "icon": "radio",
        "family": "signal",
    },
    "email_sent": {
        "label": "EMAIL EXPÉDIÉ",
        "detail": "Transmission numérique",
        "icon": "file",
        "family": "card",
    },
    "cctv_scan": {
        "label": "CAMÉRA ACTIVE",
        "detail": "Analyse de surveillance",
        "icon": "eye",
        "family": "scan",
    },
    "file_open": {
        "label": "DOSSIER OUVERT",
        "detail": "Pièces indexées",
        "icon": "file",
        "family": "file",
    },
    "redacted_report": {
        "label": "RAPPORT CAVIARDÉ",
        "detail": "Noms supprimés",
        "icon": "lock",
        "family": "redacted",
    },
    "year_marker": {
        "label": "DATE CLÉ",
        "detail": "Ancrage chronologique",
        "icon": "file",
        "family": "year",
    },
    "timeline_pin": {
        "label": "TIMELINE",
        "detail": "Événement verrouillé",
        "icon": "pin",
        "family": "card",
    },
    "counter": {
        "label": "COMPTEUR",
        "detail": "Volume détecté",
        "icon": "warning",
        "family": "counter",
    },
    "missing_person": {
        "label": "DISPARITION",
        "detail": "Avis de recherche",
        "icon": "eye",
        "family": "card",
    },
    "search_grid": {
        "label": "RECHERCHE",
        "detail": "Quadrillage de zone",
        "icon": "eye",
        "family": "search",
    },
    "evidence_photo": {
        "label": "PREUVE PHOTO",
        "detail": "Image cataloguée",
        "icon": "file",
        "family": "file",
    },
    "fingerprint_scan": {
        "label": "EMPREINTE",
        "detail": "Scan biométrique",
        "icon": "eye",
        "family": "scan",
    },
    "audio_waveform": {
        "label": "SIGNAL AUDIO",
        "detail": "Forme d'onde isolée",
        "icon": "radio",
        "family": "signal",
    },
    "radio_signal": {
        "label": "SIGNAL RADIO",
        "detail": "Fréquence interceptée",
        "icon": "radio",
        "family": "signal",
    },
    "police_lights": {
        "label": "POLICE",
        "detail": "Intervention en cours",
        "icon": "warning",
        "family": "card",
    },
    "route_trace": {
        "label": "TRAJET",
        "detail": "Itinéraire reconstruit",
        "icon": "pin",
        "family": "route",
    },
    "door_open": {
        "label": "PORTE",
        "detail": "Point de passage",
        "icon": "lock",
        "family": "card",
    },
    "key_object": {
        "label": "OBJET CLÉ",
        "detail": "Élément isolé",
        "icon": "file",
        "family": "card",
    },
    "medical_scan": {
        "label": "ANALYSE MÉDICALE",
        "detail": "Données biologiques",
        "icon": "warning",
        "family": "scan",
    },
    "lab_sample": {
        "label": "ÉCHANTILLON",
        "detail": "Protocole laboratoire",
        "icon": "file",
        "family": "card",
    },
    "newspaper_clip": {
        "label": "PRESSE",
        "detail": "Coupure archivée",
        "icon": "file",
        "family": "file",
    },
    "court_record": {
        "label": "PROCÈS-VERBAL",
        "detail": "Document légal",
        "icon": "file",
        "family": "file",
    },
    "classified_stamp": {
        "label": "CLASSIFIÉ",
        "detail": "Accès restreint",
        "icon": "lock",
        "family": "stamp",
    },
    "entity_radar": {
        "label": "SIGNATURE INCONNUE",
        "detail": "Présence non identifiée",
        "icon": "radio",
        "family": "radar",
    },
    "weather_alert": {
        "label": "MÉTÉO",
        "detail": "Condition relevée",
        "icon": "warning",
        "family": "card",
    },
    "storm_warning": {
        "label": "ALERTE ORAGE",
        "detail": "Pression instable",
        "icon": "warning",
        "family": "card",
    },
    "footprint_trail": {
        "label": "TRACES",
        "detail": "Empreintes relevées",
        "icon": "pin",
        "family": "route",
    },
    "blood_trace": {
        "label": "TRACE BIO",
        "detail": "Marque organique",
        "icon": "warning",
        "family": "card",
    },
    "fire_burst": {
        "label": "INCENDIE",
        "detail": "Source thermique",
        "icon": "warning",
        "family": "card",
    },
    "smoke_fog": {
        "label": "BROUILLARD",
        "detail": "Visibilité réduite",
        "icon": "eye",
        "family": "card",
    },
    "underground_depth": {
        "label": "SOUS-SOL",
        "detail": "Profondeur estimée",
        "icon": "lock",
        "family": "depth",
    },
    "coordinates_lock": {
        "label": "COORDONNÉES",
        "detail": "Position verrouillée",
        "icon": "pin",
        "family": "card",
    },
    "interrogation_note": {
        "label": "INTERROGATOIRE",
        "detail": "Déclaration analysée",
        "icon": "file",
        "family": "card",
    },
    "witness_card": {
        "label": "TÉMOIN",
        "detail": "Identité indexée",
        "icon": "eye",
        "family": "card",
    },
    "clock_tick": {
        "label": "HORLOGE",
        "detail": "Minute critique",
        "icon": "warning",
        "family": "clock",
    },
    "warning_flash": {
        "label": "ALERTE",
        "detail": "Risque élevé",
        "icon": "warning",
        "family": "card",
    },
    "archive_box": {
        "label": "ARCHIVE",
        "detail": "Boîte scellée",
        "icon": "file",
        "family": "file",
    },
    "question_prompt": {
        "label": "QUESTION",
        "detail": "Hypothèse ouverte",
        "icon": "warning",
        "family": "question",
    },
}

SEMANTIC_META.update(
    {
        "true_story_card": {
            "label": "HISTOIRE VRAIE",
            "detail": "Lieux et témoins réels",
            "icon": "eye",
            "family": "truth",
        },
        "last_seen_marker": {
            "label": "DERNIÈRE IMAGE",
            "detail": "Dernier moment confirmé",
            "icon": "eye",
            "family": "poster",
        },
        "floor_plan": {
            "label": "PLAN DES LIEUX",
            "detail": "Pièce par pièce",
            "icon": "file",
            "family": "blueprint",
        },
        "exit_scan": {
            "label": "SORTIE CONTRÔLÉE",
            "detail": "Passage vérifié",
            "icon": "lock",
            "family": "blueprint",
        },
        "blind_spot": {
            "label": "ANGLE MORT",
            "detail": "Zone non filmée",
            "icon": "eye",
            "family": "blueprint",
        },
        "corridor_scan": {
            "label": "COULOIR",
            "detail": "Trajectoire analysée",
            "icon": "pin",
            "family": "blueprint",
        },
        "motion_detector": {
            "label": "MOUVEMENT",
            "detail": "Détection instable",
            "icon": "eye",
            "family": "scan",
        },
        "security_log": {
            "label": "JOURNAL CAMÉRA",
            "detail": "Entrée horodatée",
            "icon": "file",
            "family": "scan",
        },
        "missing_poster": {
            "label": "AVIS DE RECHERCHE",
            "detail": "Personne introuvable",
            "icon": "eye",
            "family": "poster",
        },
        "family_photo": {
            "label": "FAMILLE",
            "detail": "Impact humain",
            "icon": "eye",
            "family": "poster",
        },
        "witness_quote": {
            "label": "TÉMOIGNAGE",
            "detail": "Déclaration clé",
            "icon": "file",
            "family": "caseboard",
        },
        "case_board": {
            "label": "TABLEAU D'ENQUÊTE",
            "detail": "Liens et hypothèses",
            "icon": "file",
            "family": "caseboard",
        },
        "evidence_thread": {
            "label": "FIL D'INDICES",
            "detail": "Éléments reliés",
            "icon": "pin",
            "family": "caseboard",
        },
        "theory_stack": {
            "label": "THÉORIES",
            "detail": "Pistes contradictoires",
            "icon": "warning",
            "family": "caseboard",
        },
        "official_denial": {
            "label": "DÉMENTI OFFICIEL",
            "detail": "Version contestée",
            "icon": "lock",
            "family": "caseboard",
        },
        "document_leak": {
            "label": "FUITE DOCUMENT",
            "detail": "Pièce sortie du dossier",
            "icon": "file",
            "family": "news",
        },
        "breaking_news": {
            "label": "ALERTE PRESSE",
            "detail": "Article archivé",
            "icon": "file",
            "family": "news",
        },
        "calendar_flip": {
            "label": "DATE",
            "detail": "Repère temporel",
            "icon": "file",
            "family": "year",
        },
        "time_jump": {
            "label": "ELLIPSE",
            "detail": "Des années passent",
            "icon": "warning",
            "family": "year",
        },
        "timeline_split": {
            "label": "TIMELINE BRISÉE",
            "detail": "Deux versions possibles",
            "icon": "pin",
            "family": "year",
        },
        "mind_control": {
            "label": "CONTRÔLE MENTAL",
            "detail": "Influence psychique",
            "icon": "radio",
            "family": "experiment",
        },
        "memory_flash": {
            "label": "MÉMOIRE",
            "detail": "Souvenir fragmenté",
            "icon": "eye",
            "family": "experiment",
        },
        "experiment_chamber": {
            "label": "PROTOCOLE",
            "detail": "Expérience clandestine",
            "icon": "file",
            "family": "experiment",
        },
        "thermal_scan": {
            "label": "THERMIQUE",
            "detail": "Source chaude isolée",
            "icon": "warning",
            "family": "experiment",
        },
        "dna_spiral": {
            "label": "ADN",
            "detail": "Trace biologique",
            "icon": "warning",
            "family": "experiment",
        },
        "heartbeat_monitor": {
            "label": "POULS",
            "detail": "Stress détecté",
            "icon": "radio",
            "family": "signal",
        },
        "voice_print": {
            "label": "EMPREINTE VOCALE",
            "detail": "Voix isolée",
            "icon": "radio",
            "family": "signal",
        },
        "signal_jammer": {
            "label": "BROUILLAGE",
            "detail": "Signal perturbé",
            "icon": "radio",
            "family": "signal",
        },
        "satellite_sweep": {
            "label": "SATELLITE",
            "detail": "Balayage orbital",
            "icon": "pin",
            "family": "map",
        },
        "map_pin_drop": {
            "label": "POINT CARTE",
            "detail": "Repère ajouté",
            "icon": "pin",
            "family": "map",
        },
        "proximity_alert": {
            "label": "PROXIMITÉ",
            "detail": "Plus proche qu'on croit",
            "icon": "warning",
            "family": "alert",
        },
        "power_cut": {
            "label": "COUPURE",
            "detail": "Lumière instable",
            "icon": "warning",
            "family": "alert",
        },
        "neon_bar": {
            "label": "BAR ORDINAIRE",
            "detail": "Lieu public réel",
            "icon": "pin",
            "family": "alert",
        },
        "searchlight": {
            "label": "PROJECTEUR",
            "detail": "Zone fouillée",
            "icon": "eye",
            "family": "search",
        },
        "basement_elevator": {
            "label": "NIVEAU INFÉRIEUR",
            "detail": "Descente verrouillée",
            "icon": "lock",
            "family": "depth",
        },
        "sealed_door": {
            "label": "PORTE SCELLÉE",
            "detail": "Accès refusé",
            "icon": "lock",
            "family": "blueprint",
        },
        "archive_stamp": {
            "label": "ARCHIVE SCELLÉE",
            "detail": "Dossier classé",
            "icon": "file",
            "family": "file",
        },
        "object_isolate": {
            "label": "OBJET ISOLÉ",
            "detail": "Pièce à conviction",
            "icon": "file",
            "family": "file",
        },
        "crowd_noise": {
            "label": "FOULE",
            "detail": "Témoins potentiels",
            "icon": "eye",
            "family": "signal",
        },
        "room_tone": {
            "label": "SILENCE",
            "detail": "Ambiance anormale",
            "icon": "radio",
            "family": "signal",
        },
    }
)

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


def _sem_slug(value):
    return re.sub(r"[^a-z0-9]+", "_", _fold_text(value)).strip("_") or "item"


def _sem_timing(scene_start, audio_duration, spec, offset=0.6, preferred=4.4):
    if "_start_offset" in spec and "_duration" in spec:
        return scene_start + float(spec["_start_offset"]), float(spec["_duration"])
    idx = int(spec.get("idx", 0))
    if audio_duration <= 1.4:
        return scene_start + 0.08, max(0.7, audio_duration - 0.16)
    local_offset = min(offset + idx * 0.36, max(0.18, audio_duration * 0.35))
    remaining = max(0.9, audio_duration - local_offset - 0.28)
    return scene_start + local_offset, max(1.0, min(preferred, remaining))


SEMANTIC_HERO_TYPES = {
    "map_zoom",
    "cctv_scan",
    "search_grid",
    "redacted_report",
    "classified_stamp",
    "year_marker",
    "question_prompt",
    "file_open",
    "missing_poster",
    "last_seen_marker",
    "floor_plan",
    "exit_scan",
    "blind_spot",
    "corridor_scan",
    "entity_radar",
    "radio_signal",
    "audio_waveform",
    "voice_print",
    "mind_control",
    "experiment_chamber",
    "underground_depth",
    "official_denial",
    "case_board",
    "evidence_thread",
}

SEMANTIC_PREF_DUR = {
    "map_zoom": 5.80,
    "satellite_sweep": 5.70,
    "map_pin_drop": 5.45,
    "cctv_scan": 4.85,
    "security_log": 4.60,
    "motion_detector": 4.55,
    "search_grid": 4.70,
    "searchlight": 4.80,
    "proximity_alert": 4.65,
    "redacted_report": 4.35,
    "classified_stamp": 4.20,
    "archive_stamp": 4.35,
    "document_leak": 4.40,
    "official_denial": 4.45,
    "breaking_news": 4.35,
    "year_marker": 4.45,
    "calendar_flip": 4.55,
    "time_jump": 4.60,
    "question_prompt": 4.65,
    "file_open": 4.45,
    "missing_poster": 4.45,
    "last_seen_marker": 4.35,
    "underground_depth": 4.65,
    "route_trace": 4.45,
    "floor_plan": 4.60,
    "exit_scan": 4.50,
    "blind_spot": 4.50,
    "mind_control": 4.65,
    "experiment_chamber": 4.65,
    "timeline_split": 4.55,
    "power_cut": 4.50,
    "neon_bar": 4.50,
    "room_tone": 4.35,
}


def _overlay_preferred_duration(spec):
    otype = spec.get("type")
    return SEMANTIC_PREF_DUR.get(
        otype, 4.15 if otype not in SEMANTIC_HERO_TYPES else 4.45
    )


SEMANTIC_VARIANT_ROTATION = {
    "classified_stamp": [
        "classified_stamp",
        "archive_stamp",
        "document_leak",
        "redacted_report",
        "official_denial",
        "file_open",
        "case_board",
        "evidence_thread",
    ],
    "redacted_report": [
        "redacted_report",
        "document_leak",
        "archive_stamp",
        "file_open",
        "official_denial",
        "case_board",
    ],
    "file_open": [
        "file_open",
        "archive_stamp",
        "object_isolate",
        "document_leak",
        "evidence_thread",
        "case_board",
    ],
    "cctv_scan": [
        "cctv_scan",
        "security_log",
        "motion_detector",
        "blind_spot",
        "corridor_scan",
    ],
    "security_log": [
        "security_log",
        "motion_detector",
        "cctv_scan",
        "blind_spot",
    ],
    "search_grid": [
        "search_grid",
        "searchlight",
        "proximity_alert",
        "motion_detector",
        "last_seen_marker",
    ],
    "map_zoom": [
        "map_zoom",
        "satellite_sweep",
        "map_pin_drop",
    ],
    "route_trace": [
        "route_trace",
        "satellite_sweep",
        "map_pin_drop",
        "proximity_alert",
    ],
    "year_marker": [
        "year_marker",
        "calendar_flip",
        "time_jump",
        "timeline_split",
    ],
    "timeline_pin": [
        "timeline_pin",
        "calendar_flip",
        "time_jump",
        "case_board",
    ],
    "question_prompt": [
        "question_prompt",
        "theory_stack",
        "case_board",
    ],
    "mind_control": [
        "mind_control",
        "memory_flash",
        "experiment_chamber",
        "timeline_split",
    ],
    "underground_depth": [
        "underground_depth",
        "basement_elevator",
        "sealed_door",
        "thermal_scan",
    ],
}


def _diversify_overlay_types(overlays, scene_idx):
    """Évite l'impression de boucle en variant le type exact et la famille visuelle."""
    diversified = []
    used_types = set()
    used_families = set()
    scene_idx = scene_idx or 0
    for rank, spec in enumerate(overlays):
        original = spec.get("type")
        candidates = list(SEMANTIC_VARIANT_ROTATION.get(original, [original]))
        if original == "map_zoom" and scene_idx <= 1:
            candidates = ["map_zoom", "satellite_sweep", "map_pin_drop"]
        else:
            shift = (scene_idx + rank * 2) % max(1, len(candidates))
            candidates = candidates[shift:] + candidates[:shift]

        chosen = None
        for cand in candidates:
            if cand not in SEMANTIC_META or cand in used_types:
                continue
            family = SEMANTIC_META.get(cand, {}).get("family")
            if family in used_families and len(candidates) > 1:
                continue
            chosen = cand
            break
        if chosen is None:
            for cand in candidates:
                if cand in SEMANTIC_META and cand not in used_types:
                    chosen = cand
                    break
        if chosen is None:
            chosen = original

        new_spec = dict(spec)
        new_spec["type"] = chosen
        diversified.append(new_spec)
        used_types.add(chosen)
        used_families.add(SEMANTIC_META.get(chosen, {}).get("family"))
    return diversified


def _prepare_overlay_schedule(overlays, audio_duration, scene_idx):
    """Décale les overlays pour éviter les recouvrements frame par frame."""
    if not overlays:
        return []
    base = 0.82
    end_guard = 1.10
    gap = 0.95
    available = max(0.0, audio_duration - base - end_guard)
    max_items = 2 if available >= 9.8 else 1
    curated = overlays[:max_items]

    if len(curated) == 1 or available < 4.9:
        spec = curated[0]
        spec["_start_offset"] = min(base, max(0.18, audio_duration * 0.22))
        room = audio_duration - spec["_start_offset"] - end_guard
        if room <= 3.10:
            spec["_duration"] = max(1.50, room)
        else:
            spec["_duration"] = max(3.10, min(_overlay_preferred_duration(spec), room))
        return [spec]

    first, second = curated[0], curated[1]
    first_pref = _overlay_preferred_duration(first)
    second_pref = _overlay_preferred_duration(second)
    first_dur = min(first_pref, max(4.05, available * 0.50))
    second_start = base + first_dur + gap
    second_room = audio_duration - second_start - end_guard
    if second_room < 3.35:
        first["_start_offset"] = base
        first["_duration"] = max(3.60, min(first_pref, available))
        return [first]

    first["_start_offset"] = base
    first["_duration"] = first_dur
    second["_start_offset"] = second_start
    second["_duration"] = max(3.35, min(second_pref, second_room))
    second["_secondary"] = True
    return [first, second]


def _sem_track(scene_idx, spec):
    return scene_idx * 20 + 15 + int(spec.get("idx", 0))


def _sem_meta(spec):
    return SEMANTIC_META.get(spec.get("type"), SEMANTIC_META["timeline_pin"])


def _sem_icon(spec):
    return ICONS.get(_sem_meta(spec).get("icon", "file"), ICONS["file"])


def _sem_label(spec):
    return html_escape(str(spec.get("label") or _sem_meta(spec)["label"]))


def _sem_detail(spec):
    return html_escape(str(spec.get("detail") or _sem_meta(spec)["detail"]))


def _sem_exit_js(oid, start, dur, outro="y"):
    exit_at = max(start + 0.35, start + dur - 0.45)
    if outro == "scale":
        return [
            f'tl.to("#{oid}", {{opacity: 0, scale: 0.92, duration: 0.42, ease: "power2.in"}}, {exit_at:.3f});',
            f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
        ]
    if outro == "x":
        return [
            f'tl.to("#{oid}", {{opacity: 0, x: -60, duration: 0.42, ease: "power2.in"}}, {exit_at:.3f});',
            f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
        ]
    return [
        f'tl.to("#{oid}", {{opacity: 0, y: -28, duration: 0.42, ease: "power2.in"}}, {exit_at:.3f});',
        f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
    ]


def _project_lnglat(lnglat):
    if not lnglat:
        return 540, 770
    lng, lat = lnglat
    x = 130 + ((float(lng) + 180.0) / 360.0) * 820
    y = 360 + ((90.0 - float(lat)) / 180.0) * 860
    return int(max(130, min(950, x))), int(max(360, min(1220, y)))


def _ov_sem_map_zoom(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_map_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.18, preferred=5.2
    )
    label = html_escape(spec.get("value", "ZONE"))
    coords = html_escape(spec.get("coords", "COORDONNÉES INCONNUES"))
    region = html_escape(spec.get("region") or "SECTOR")
    iso = html_escape(spec.get("iso") or "GEO")
    route_label = html_escape(spec.get("route_label", ""))
    route_count = int(spec.get("route_count") or 0)
    badge = html_escape(spec.get("badge", ""))
    x, y = _project_lnglat(spec.get("lnglat"))
    route_block = (
        f'<div class="sem-map-route-copy"><span>TRAJET</span><strong>{route_label}</strong>'
        f"<em>{route_count} lieux détectés</em></div>"
        if route_label
        else ""
    )
    badge_block = f'<div class="sem-map-badge">{badge}</div>' if badge else ""
    html = (
        f'<div id="{oid}" class="sem-overlay sem-map clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div id="{oid}_grid" class="sem-map-grid"></div>'
        f'<svg class="sem-map-lines" viewBox="0 0 1080 1920" preserveAspectRatio="none">'
        f'<path id="{oid}_route" d="M140 1390 C330 1050 420 920 {x} {y} S760 520 940 360" />'
        f'<circle cx="{x}" cy="{y}" r="92" class="sem-map-ring" id="{oid}_ring"/>'
        f"</svg>"
        f'<div class="sem-map-cross" style="left:{x}px; top:{y}px;"></div>'
        f'<div class="sem-map-dot" id="{oid}_dot" style="left:{x}px; top:{y}px;"></div>'
        f'<div class="sem-map-label" id="{oid}_label">'
        f'<div class="sem-kicker">GEO LOCK · {iso}</div>'
        f'<div class="sem-map-title">{label}</div>'
        f'<div class="sem-map-coords">{coords} · {region}</div>'
        f"{badge_block}"
        f"</div>"
        f"{route_block}"
        f'<div class="sem-map-readout">SAT LINK / ADAPTIVE LOCATION / TARGET ACQUIRED</div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{oid}_grid", {{scale: 0.72, x: {(540 - x) * 0.12:.1f}, y: {(790 - y) * 0.12:.1f}, transformOrigin: "{x}px {y}px"}});',
        f'gsap.set("#{oid}_route", {{drawSVG: "0%"}});'
        if False
        else f'gsap.set("#{oid}_route", {{strokeDasharray: 1800, strokeDashoffset: 1800}});',
        f'gsap.set("#{oid}_dot", {{scale: 0, opacity: 0}});',
        f'gsap.set("#{oid}_label", {{opacity: 0, y: 24}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.35, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid}_grid", {{scale: 1.34, x: {(540 - x) * 0.42:.1f}, y: {(790 - y) * 0.42:.1f}, duration: {dur:.3f}, ease: "power2.inOut"}}, {start:.3f});',
        f'tl.to("#{oid}_route", {{strokeDashoffset: 0, duration: 1.15, ease: "power2.out"}}, {(start + 0.32):.3f});',
        f'tl.to("#{oid}_dot", {{opacity: 1, scale: 1, duration: 0.34, ease: "back.out(2)"}}, {(start + 0.78):.3f});',
        f'tl.fromTo("#{oid}_ring", {{scale: 0.35, opacity: 0.95, transformOrigin: "50% 50%"}}, {{scale: 1.7, opacity: 0, duration: 0.95, repeat: 3, ease: "power2.out"}}, {(start + 0.84):.3f});',
        f'tl.to("#{oid}_label", {{opacity: 1, y: 0, duration: 0.48, ease: "power3.out"}}, {(start + 0.88):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_message(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_msg_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.5
    )
    body = html_escape(spec.get("body") or "Message envoyé.")
    html = (
        f'<div id="{oid}" class="sem-overlay sem-message clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-phone">'
        f'<div class="sem-phone-bar"></div>'
        f'<div class="sem-chat">'
        f'<div class="sem-chat-meta">ENVOI SÉCURISÉ</div>'
        f'<div id="{oid}_bubble" class="sem-bubble"><span id="{oid}_text">{body}</span></div>'
        f'<div id="{oid}_send" class="sem-send-row"><span></span><strong>ENVOYÉ</strong></div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: 44, scale: 0.96}});',
        f'gsap.set("#{oid}_bubble", {{clipPath: "inset(0 100% 0 0)"}});',
        f'gsap.set("#{oid}_send", {{opacity: 0, x: -16}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, scale: 1, duration: 0.45, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_bubble", {{clipPath: "inset(0 0% 0 0)", duration: 1.2, ease: "steps(18)"}}, {(start + 0.42):.3f});',
        f'tl.to("#{oid}_send", {{opacity: 1, x: 0, duration: 0.32, ease: "power2.out"}}, {(start + 1.72):.3f});',
        f'tl.to("#{oid}_send span", {{scale: 1.7, opacity: 0, duration: 0.55, repeat: 1, ease: "power2.out"}}, {(start + 1.82):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_year(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_year_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.65, preferred=4.2
    )
    value = html_escape(spec.get("value", "----"))
    html = (
        f'<div id="{oid}" class="sem-overlay sem-year clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-kicker">TIMELINE LOCK</div>'
        f'<div class="sem-year-num">{value}</div>'
        f'<div class="sem-year-rule" id="{oid}_rule"></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: -34, filter: "blur(10px)"}});',
        f'gsap.set("#{oid}_rule", {{scaleX: 0, transformOrigin: "center"}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, filter: "blur(0px)", duration: 0.58, ease: "expo.out"}}, {start:.3f});',
        f'tl.to("#{oid}_rule", {{scaleX: 1, duration: 0.72, ease: "power3.out"}}, {(start + 0.16):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur))
    return [html], js


def _ov_sem_counter(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_counter_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.76, preferred=4.3
    )
    try:
        final_val = int(re.sub(r"\D", "", str(spec.get("value", "0"))))
    except ValueError:
        final_val = 0
    html = (
        f'<div id="{oid}" class="sem-overlay sem-counter clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-kicker">QUANTIFICATION</div>'
        f'<div class="sem-counter-num" id="{oid}_num">0</div>'
        f'<div class="sem-meter"><div id="{oid}_bar"></div></div>'
        f"</div>"
    )
    js = [
        f"const {oid}_obj = {{val: 0}};",
        f'gsap.set("#{oid}", {{opacity: 0, x: 48}});',
        f'gsap.set("#{oid}_bar", {{scaleX: 0, transformOrigin: "left"}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, duration: 0.45, ease: "power3.out"}}, {start:.3f});',
        f'tl.to({oid}_obj, {{val: {final_val}, duration: 1.55, ease: "power2.out", onUpdate: () => {{ const el = document.getElementById("{oid}_num"); if (el) el.innerText = Math.floor({oid}_obj.val).toLocaleString("fr-FR"); }}}}, {(start + 0.24):.3f});',
        f'tl.to("#{oid}_bar", {{scaleX: 1, duration: 1.55, ease: "power2.out"}}, {(start + 0.24):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_cctv(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_cctv_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.52, preferred=4.8
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-cctv clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-cctv-frame">'
        f'<div class="sem-cctv-head"><span>CAM 03</span><strong>REC</strong></div>'
        f'<div class="sem-cctv-screen">'
        f'<div id="{oid}_scan" class="sem-cctv-scan"></div>'
        f'<div id="{oid}_box1" class="sem-cctv-box one"></div>'
        f'<div id="{oid}_box2" class="sem-cctv-box two"></div>'
        f"</div>"
        f'<div class="sem-cctv-foot">FRAME ANALYSIS / EXIT NOT CONFIRMED</div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 0.96}});',
        f'gsap.set("#{oid}_scan", {{y: -260}});',
        f'gsap.set("#{oid}_box1, #{oid}_box2", {{opacity: 0, scale: 0.88}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, duration: 0.45, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_scan", {{y: 290, duration: 1.05, repeat: 2, ease: "none"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid}_box1", {{opacity: 1, scale: 1, duration: 0.22, repeat: 3, yoyo: true, ease: "steps(1)"}}, {(start + 0.55):.3f});',
        f'tl.to("#{oid}_box2", {{opacity: 1, scale: 1, duration: 0.18, repeat: 4, yoyo: true, ease: "steps(1)"}}, {(start + 0.82):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_file(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_file_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.4
    )
    label = _sem_label(spec)
    detail = _sem_detail(spec)
    html = (
        f'<div id="{oid}" class="sem-overlay sem-file clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-file-back" id="{oid}_b1"></div><div class="sem-file-back two" id="{oid}_b2"></div>'
        f'<div class="sem-file-front">'
        f'<div class="sem-file-tab">{label}</div>'
        f'<div class="sem-file-line"></div><div class="sem-file-line short"></div><div class="sem-file-line mid"></div>'
        f'<div class="sem-file-stamp">{detail}</div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: 70, rotation: 4}});',
        f'gsap.set("#{oid}_b1", {{opacity: 0, x: -10, y: -8, rotation: -4}});',
        f'gsap.set("#{oid}_b2", {{opacity: 0, x: 10, y: -6, rotation: 5}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, rotation: 0, duration: 0.48, ease: "back.out(1.45)"}}, {start:.3f});',
        f'tl.to("#{oid}_b1", {{opacity: 0.9, x: -42, y: -34, duration: 0.52, ease: "power2.out"}}, {(start + 0.26):.3f});',
        f'tl.to("#{oid}_b2", {{opacity: 0.82, x: 44, y: -28, duration: 0.52, ease: "power2.out"}}, {(start + 0.34):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_redacted(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_redact_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.58, preferred=3.8
    )
    bars = "".join(
        f'<div class="sem-redact-bar" id="{oid}_b{i}" style="top:{42 + i * 48}px; width:{340 + (i * 86) % 310}px;"></div>'
        for i in range(5)
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-redacted clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'{bars}<div id="{oid}_stamp" class="sem-redact-stamp">{_sem_label(spec)}</div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 1}});',
        f'gsap.set("#{oid}_stamp", {{opacity: 0, scale: 0.72, rotation: -8}});',
    ]
    for i in range(5):
        js.append(f'gsap.set("#{oid}_b{i}", {{scaleX: 0, transformOrigin: "left"}});')
        js.append(
            f'tl.to("#{oid}_b{i}", {{scaleX: 1, duration: 0.22, ease: "power3.out"}}, {(start + 0.08 + i * 0.09):.3f});'
        )
    js.append(
        f'tl.to("#{oid}_stamp", {{opacity: 1, scale: 1, duration: 0.32, ease: "back.out(2)"}}, {(start + 0.64):.3f});'
    )
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_radar(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_radar_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.64, preferred=4.5
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-radar clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-radar-dish">'
        f'<div class="sem-radar-ring r1"></div><div class="sem-radar-ring r2"></div><div class="sem-radar-ring r3"></div>'
        f'<div id="{oid}_sweep" class="sem-radar-sweep"></div>'
        f'<div class="sem-radar-blip b1"></div><div class="sem-radar-blip b2"></div>'
        f"</div>"
        f'<div class="sem-radar-copy"><div class="sem-kicker">{_sem_label(spec)}</div><strong>{_sem_detail(spec)}</strong></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 0.84}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, duration: 0.42, ease: "back.out(1.5)"}}, {start:.3f});',
        f'tl.to("#{oid}_sweep", {{rotation: 360, duration: 1.25, repeat: 3, ease: "none"}}, {(start + 0.12):.3f});',
        f'tl.fromTo("#{oid} .sem-radar-blip", {{opacity: 0}}, {{opacity: 1, duration: 0.18, stagger: 0.22, repeat: 5, yoyo: true, ease: "steps(1)"}}, {(start + 0.42):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_search(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_search_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.62, preferred=4.4
    )
    cells = "".join(
        f'<div class="sem-search-cell" id="{oid}_c{i}"></div>' for i in range(12)
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-search clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-search-title"><span>{_sem_label(spec)}</span><strong>{_sem_detail(spec)}</strong></div>'
        f'<div class="sem-search-grid">{cells}</div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{oid} .sem-search-cell", {{opacity: 0, scale: 0.86}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.32, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-search-cell", {{opacity: 1, scale: 1, duration: 0.16, stagger: 0.055, ease: "power2.out"}}, {(start + 0.22):.3f});',
        f'tl.to("#{oid} .sem-search-cell:nth-child(7)", {{backgroundColor: "rgba(255,56,56,0.22)", borderColor: "rgba(255,56,56,0.9)", duration: 0.22, repeat: 4, yoyo: true, ease: "steps(1)"}}, {(start + 1.02):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_depth(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_depth_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.62, preferred=4.6
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-depth clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-depth-copy"><div class="sem-kicker">{_sem_label(spec)}</div><strong>{_sem_detail(spec)}</strong></div>'
        f'<div class="sem-depth-shaft"><div id="{oid}_fill" class="sem-depth-fill"></div><div id="{oid}_marker" class="sem-depth-marker">LEVEL -07</div></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: -32}});',
        f'gsap.set("#{oid}_fill", {{scaleY: 0, transformOrigin: "top"}});',
        f'gsap.set("#{oid}_marker", {{y: -210, opacity: 0}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, duration: 0.42, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_fill", {{scaleY: 1, duration: 1.25, ease: "power2.inOut"}}, {(start + 0.28):.3f});',
        f'tl.to("#{oid}_marker", {{y: 0, opacity: 1, duration: 1.25, ease: "power2.inOut"}}, {(start + 0.28):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_route(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_route_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.74, preferred=4.6
    )
    value = html_escape(spec.get("value") or "TRAJET RECONSTRUIT")
    detail = _sem_detail(spec)
    html = (
        f'<div id="{oid}" class="sem-overlay sem-route clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<svg viewBox="0 0 520 260"><path id="{oid}_path" d="M38 200 C150 70 265 235 470 62"/><circle cx="38" cy="200" r="8"/><circle cx="470" cy="62" r="8"/></svg>'
        f'<div class="sem-route-copy"><div class="sem-kicker">{_sem_label(spec)}</div><strong>{value}</strong><span>{detail}</span></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: 24}});',
        f'gsap.set("#{oid}_path", {{strokeDasharray: 760, strokeDashoffset: 760}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, duration: 0.42, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_path", {{strokeDashoffset: 0, duration: 1.25, ease: "power2.out"}}, {(start + 0.24):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur))
    return [html], js


def _ov_sem_question(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_question_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.2
    )
    value = html_escape(spec.get("value") or "HYPOTHÈSE OUVERTE")
    html = (
        f'<div id="{oid}" class="sem-overlay sem-question clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div id="{oid}_mark" class="sem-question-mark">?</div>'
        f'<div class="sem-question-copy"><div class="sem-kicker">{_sem_label(spec)}</div><strong>{value}</strong><span>{_sem_detail(spec)}</span></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{oid}_mark", {{scale: 0.7, rotation: -8}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.32, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid}_mark", {{scale: 1, rotation: 0, duration: 0.55, ease: "back.out(1.8)"}}, {(start + 0.08):.3f});',
        f'tl.to("#{oid}_mark", {{scale: 1.06, duration: 0.48, repeat: 3, yoyo: true, ease: "sine.inOut"}}, {(start + 0.72):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_card(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.1
    )
    value = html_escape(str(spec.get("value") or _sem_detail(spec)))
    role = html_escape(str(spec.get("role") or "STATUS ACTIVE"))
    html = (
        f'<div id="{oid}" class="sem-overlay sem-card sem-{slug} clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-card-icon">{_sem_icon(spec)}</div>'
        f'<div class="sem-card-body">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<strong>{value}</strong>"
        f"<span>{role}</span>"
        f'<div class="sem-card-bars"><i id="{oid}_b1"></i><i id="{oid}_b2"></i><i id="{oid}_b3"></i></div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: 54, skewX: -5}});',
        f'gsap.set("#{oid} .sem-card-bars i", {{scaleX: 0, transformOrigin: "left"}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, skewX: 0, duration: 0.44, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-card-icon", {{scale: 1.08, duration: 0.38, repeat: 2, yoyo: true, ease: "sine.inOut"}}, {(start + 0.35):.3f});',
        f'tl.to("#{oid} .sem-card-bars i", {{scaleX: 1, duration: 0.28, stagger: 0.08, ease: "power2.out"}}, {(start + 0.42):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_poster(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_poster_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.2
    )
    label = _sem_label(spec)
    detail = _sem_detail(spec)
    html = (
        f'<div id="{oid}" class="sem-overlay sem-poster clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-poster-sheet">'
        f'<div class="sem-poster-top">{label}</div>'
        f'<div class="sem-poster-face"><span></span><i id="{oid}_scan"></i></div>'
        f'<div class="sem-poster-name">{detail}</div>'
        f'<div class="sem-poster-lines"><b></b><b></b><b></b></div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: -56, rotation: -2}});',
        f'gsap.set("#{oid}_scan", {{y: -120}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, rotation: 0, duration: 0.42, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_scan", {{y: 130, duration: 0.95, repeat: 1, ease: "power1.inOut"}}, {(start + 0.34):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_blueprint(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_blue_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.15
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-blueprint clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-blue-card">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f'<svg viewBox="0 0 420 260">'
        f'<path id="{oid}_p1" d="M34 44 H380 V218 H34 Z M120 44 V218 M246 44 V142 H380 M120 132 H246" />'
        f'<path id="{oid}_p2" d="M62 190 C128 142 184 166 236 118 S312 90 362 70" />'
        f'<circle cx="236" cy="118" r="12" />'
        f"</svg>"
        f"<strong>{_sem_detail(spec)}</strong>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: 26}});',
        f'gsap.set("#{oid}_p1, #{oid}_p2", {{strokeDasharray: 900, strokeDashoffset: 900}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, duration: 0.40, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_p1", {{strokeDashoffset: 0, duration: 0.9, ease: "power2.out"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid}_p2", {{strokeDashoffset: 0, duration: 0.75, ease: "power2.out"}}, {(start + 0.56):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur))
    return [html], js


def _ov_sem_signal(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_signal_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.25
    )
    bars = "".join(
        f'<i id="{oid}_w{i}" style="height:{24 + ((i * 37) % 92)}px"></i>'
        for i in range(18)
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-signal clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-signal-card">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f'<div class="sem-wave">{bars}</div>'
        f"<strong>{_sem_detail(spec)}</strong>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 0.96}});',
        f'gsap.set("#{oid} .sem-wave i", {{scaleY: 0.18, transformOrigin: "50% 50%"}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, duration: 0.38, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-wave i", {{scaleY: 1, duration: 0.22, stagger: 0.025, repeat: 8, yoyo: true, ease: "sine.inOut"}}, {(start + 0.25):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_experiment(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_exp_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.25
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-experiment clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-exp-core">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f'<div class="sem-exp-rings"><i></i><i></i><i></i><b id="{oid}_needle"></b></div>'
        f"<strong>{_sem_detail(spec)}</strong>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, filter: "blur(6px)"}});',
        f'gsap.set("#{oid}_needle", {{rotation: -32, transformOrigin: "50% 100%"}});',
        f'tl.to("#{oid}", {{opacity: 1, filter: "blur(0px)", duration: 0.40, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-exp-rings i", {{scale: 1.18, opacity: 0.22, duration: 0.62, stagger: 0.12, repeat: 3, yoyo: true, ease: "sine.inOut"}}, {(start + 0.28):.3f});',
        f'tl.to("#{oid}_needle", {{rotation: 38, duration: 1.1, repeat: 2, yoyo: true, ease: "power1.inOut"}}, {(start + 0.30):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_caseboard(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_board_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.1
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-board clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-board-panel">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f'<div class="sem-board-nodes"><span></span><span></span><span></span><i id="{oid}_line"></i></div>'
        f"<strong>{_sem_detail(spec)}</strong>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: 42}});',
        f'gsap.set("#{oid} .sem-board-nodes span", {{scale: 0, opacity: 0}});',
        f'gsap.set("#{oid}_line", {{scaleX: 0, transformOrigin: "left"}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, duration: 0.40, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-board-nodes span", {{scale: 1, opacity: 1, duration: 0.22, stagger: 0.12, ease: "back.out(2)"}}, {(start + 0.25):.3f});',
        f'tl.to("#{oid}_line", {{scaleX: 1, duration: 0.55, ease: "power2.out"}}, {(start + 0.48):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_satellite(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_sat_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=5.4
    )
    title = html_escape(str(spec.get("value") or _sem_label(spec)))
    detail = html_escape(
        str(spec.get("coords") or spec.get("detail") or _sem_detail(spec))
    )
    route = html_escape(str(spec.get("route_label") or "BALAYAGE EN COURS"))
    html = (
        f'<div id="{oid}" class="sem-overlay sem-satellite clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-sat-grid"></div>'
        f'<div class="sem-sat-orbit"><i></i><i></i><i></i><b id="{oid}_sweep"></b><em></em></div>'
        f'<div class="sem-sat-copy"><div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<strong>{title}</strong><span>{detail}</span><small>{route}</small></div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 1.04, filter: "blur(5px)"}});',
        f'gsap.set("#{oid} .sem-sat-copy", {{opacity: 0, y: 28}});',
        f'gsap.set("#{oid} .sem-sat-orbit", {{scale: 0.76, opacity: 0}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.55, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-sat-orbit", {{scale: 1, opacity: 1, duration: 0.8, ease: "expo.out"}}, {(start + 0.12):.3f});',
        f'tl.to("#{oid}_sweep", {{rotation: 720, duration: {max(3.2, dur - 0.55):.3f}, ease: "none"}}, {(start + 0.30):.3f});',
        f'tl.to("#{oid} .sem-sat-copy", {{opacity: 1, y: 0, duration: 0.55, ease: "power3.out"}}, {(start + 0.55):.3f});',
        f'tl.to("#{oid} .sem-sat-orbit em", {{scale: 2.2, opacity: 0, duration: 1.15, repeat: {max(1, int(dur // 1.3))}, ease: "power2.out"}}, {(start + 0.72):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_security_matrix(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_sec_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.75
    )
    rows = "".join(
        f'<li id="{oid}_r{i}"><span>{(scene_idx + 2) * 11 + i:02d}:{(i * 7) % 60:02d}:{(i * 13) % 60:02d}</span>'
        f"<b>{'MOUVEMENT' if i == 3 else 'AUCUN SIGNAL'}</b></li>"
        for i in range(7)
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-security clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-security-panel"><div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<ul>{rows}</ul><strong>{_sem_detail(spec)}</strong></div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: -42}});',
        f'gsap.set("#{oid} li", {{opacity: 0, x: -18}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, duration: 0.42, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} li", {{opacity: 1, x: 0, duration: 0.18, stagger: 0.13, ease: "power2.out"}}, {(start + 0.22):.3f});',
        f'tl.to("#{oid}_r3", {{backgroundColor: "rgba(255,56,56,0.22)", duration: 0.18, repeat: 6, yoyo: true, ease: "steps(1)"}}, {(start + 1.25):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_timewarp(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_time_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.55
    )
    value = html_escape(str(spec.get("value") or "DATE"))
    html = (
        f'<div id="{oid}" class="sem-overlay sem-timewarp clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-time-lines"><i></i><i></i><i></i><i></i></div>'
        f'<div class="sem-time-copy"><div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<strong>{value}</strong><span>{_sem_detail(spec)}</span></div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, perspective: 900}});',
        f'gsap.set("#{oid} .sem-time-lines i", {{scaleY: 0, transformOrigin: "50% 50%"}});',
        f'gsap.set("#{oid} .sem-time-copy", {{opacity: 0, y: 34, rotationX: -18}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.35, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-time-lines i", {{scaleY: 1, duration: 0.42, stagger: 0.08, ease: "expo.out"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid} .sem-time-copy", {{opacity: 1, y: 0, rotationX: 0, duration: 0.65, ease: "back.out(1.7)"}}, {(start + 0.45):.3f});',
        f'tl.to("#{oid} .sem-time-lines", {{x: 42, duration: {max(3.0, dur - 0.8):.3f}, ease: "sine.inOut"}}, {(start + 0.7):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_blackout(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_black_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.5
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-blackout clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-black-veil"></div><div id="{oid}_beam" class="sem-black-beam"></div>'
        f'<div class="sem-black-copy"><div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<strong>{_sem_detail(spec)}</strong></div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{oid}_beam", {{x: -260, rotation: -12, opacity: 0}});',
        f'gsap.set("#{oid} .sem-black-copy", {{opacity: 0, y: 18}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.28, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid}_beam", {{opacity: 1, x: 720, rotation: 7, duration: {max(2.8, dur - 0.7):.3f}, ease: "sine.inOut"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid} .sem-black-copy", {{opacity: 1, y: 0, duration: 0.45, ease: "power3.out"}}, {(start + 0.42):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur))
    return [html], js


def _ov_year(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_ov_year"
    start = scene_start + 0.8
    dur = min(4.5, audio_duration - 1.5)
    value = html_escape(spec["value"])
    html = (
        f'<div id="{oid}" class="ov-year clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{scene_idx * 20 + 15 + spec.get("idx", 0)}">'
        f'<span class="ov-year-label">YEAR · CASE OPENED</span>{value}</div>'
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: -30}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, duration: 0.7, ease: "expo.out"}}, {start:.3f});',
        f'tl.to("#{oid}", {{opacity: 0, y: -20, duration: 0.5, ease: "expo.in"}}, '
        f"{(start + dur - 0.5):.3f});",
        f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
    ]
    return [html], js


def _ov_location(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_ov_loc"
    start = scene_start + 1.2
    dur = min(5.0, audio_duration - 1.8)
    label = html_escape(spec["value"])
    coords = html_escape(spec.get("coords", "COORDONNÉES INCONNUES"))
    map_id = f"{oid}_map"
    has_map = spec.get("lnglat") is not None
    iso = spec.get("iso") or ""
    lnglat = spec.get("lnglat") or [0, 0]

    map_block = ""
    if has_map:
        map_block = f'<div class="ov-loc-map"><svg id="{map_id}" viewBox="0 0 140 140"></svg></div>'

    extra_style = ' style="top: 920px;"' if spec.get("shift_down") else ""
    html = (
        f'<div id="{oid}" class="ov-location clip"{extra_style} '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{scene_idx * 20 + 15 + spec.get("idx", 0)}">'
        f"{map_block}"
        f'<div class="ov-loc-text">'
        f'<div class="ov-loc-label">{label}</div>'
        f'<div class="ov-loc-coords">{coords}</div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: -100, y: -10}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, y: 0, duration: 0.55, '
        f'ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}", {{opacity: 0, x: -60, duration: 0.4, '
        f'ease: "power2.in"}}, {(start + dur - 0.4):.3f});',
        f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
    ]
    if has_map:
        # D3 mini-map render (sync, runs once at page init)
        js.append(
            f"window.__renderMap && window.__renderMap("
            f'"{map_id}", [{lnglat[0]}, {lnglat[1]}], "{iso}");'
        )
    return [html], js


def _ov_counter(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_ov_cnt"
    start = scene_start + 1.0
    dur = min(4.5, audio_duration - 1.5)
    try:
        final_val = int(re.sub(r"\D", "", str(spec.get("value", "0"))))
    except ValueError:
        final_val = 0
    html = (
        f'<div id="{oid}" class="ov-counter clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{scene_idx * 20 + 15 + spec.get("idx", 0)}">'
        f'<div class="ov-cnt-label">VICTIMES</div>'
        f'<div class="ov-cnt-num" id="{oid}_num">0</div>'
        f'<div class="ov-cnt-bar"><div class="ov-cnt-fill" id="{oid}_fill"></div></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: 30, scale: 0.9}});',
        f'gsap.set("#{oid}_fill", {{width: "0%"}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, scale: 1, duration: 0.45, '
        f'ease: "back.out(1.5)"}}, {start:.3f});',
        # Counter animation
        f"const {oid}_obj = {{val: 0}};",
        f'tl.to({oid}_obj, {{val: {final_val}, duration: 2.0, ease: "power2.out", '
        f'onUpdate: () => {{ const el = document.getElementById("{oid}_num"); '
        f'if (el) el.innerText = Math.floor({oid}_obj.val).toLocaleString("fr-FR"); }}}}, '
        f"{(start + 0.4):.3f});",
        f'tl.to("#{oid}_fill", {{width: "100%", duration: 2.0, ease: "power2.out"}}, '
        f"{(start + 0.4):.3f});",
        f'tl.to("#{oid}", {{opacity: 0, y: -20, duration: 0.4, ease: "power2.in"}}, '
        f"{(start + dur - 0.4):.3f});",
        f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
    ]
    return [html], js


def _ov_dossier(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_ov_dos"
    start = scene_start + 1.5
    dur = min(4.0, audio_duration - 2.0)
    html = (
        f'<div id="{oid}" class="ov-dossier clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{scene_idx * 20 + 15 + spec.get("idx", 0)}">'
        f'<div class="ov-dos-paper" id="{oid}_p1"></div>'
        f'<div class="ov-dos-paper" id="{oid}_p2"></div>'
        f'<div class="ov-dos-folder">'
        f'<div class="ov-dos-tab">'
        f'<span class="ov-ico ov-dos-ico">{ICONS["file"]}</span>'
        f"CLASSIFIED FILE</div>"
        f'<div class="ov-dos-body">'
        f'<div class="ov-dos-line"></div>'
        f'<div class="ov-dos-line"></div>'
        f'<div class="ov-dos-line short"></div>'
        f'<div class="ov-dos-stamp">TOP SECRET</div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, rotation: 8, x: 80}});',
        f'gsap.set("#{oid}_p1", {{opacity: 0, x: -30, y: -10, rotation: -8}});',
        f'gsap.set("#{oid}_p2", {{opacity: 0, x: 30, y: -15, rotation: 12}});',
        f'tl.to("#{oid}", {{opacity: 1, rotation: -3, x: 0, duration: 0.55, '
        f'ease: "back.out(1.4)"}}, {start:.3f});',
        # Papers fly out
        f'tl.to("#{oid}_p1", {{opacity: 0.95, x: -90, y: -50, rotation: -15, '
        f'duration: 0.7, ease: "power2.out"}}, {(start + 0.4):.3f});',
        f'tl.to("#{oid}_p2", {{opacity: 0.95, x: 90, y: -40, rotation: 18, '
        f'duration: 0.7, ease: "power2.out"}}, {(start + 0.55):.3f});',
        f'tl.to("#{oid}", {{opacity: 0, x: 40, rotation: 10, duration: 0.4, '
        f'ease: "power2.in"}}, {(start + dur - 0.4):.3f});',
        f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
    ]
    return [html], js


def _ov_redacted(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_ov_red"
    start = scene_start + 0.8
    dur = min(3.5, audio_duration - 1.2)
    bars = "".join(
        f'<div class="ov-red-bar" id="{oid}_b{i}" style="top:{20 + i * 38}px; width:{180 + (i * 40) % 140}px;"></div>'
        for i in range(4)
    )
    html = (
        f'<div id="{oid}" class="ov-redacted clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{scene_idx * 20 + 15 + spec.get("idx", 0)}">'
        f'<div class="ov-red-stamp">REDACTED</div>'
        f"{bars}"
        f"</div>"
    )
    js = [f'gsap.set("#{oid}", {{opacity: 1}});']
    for i in range(4):
        bid = f"{oid}_b{i}"
        js.append(f'gsap.set("#{bid}", {{scaleX: 0, transformOrigin: "left"}});')
        js.append(
            f'tl.to("#{bid}", {{scaleX: 1, duration: 0.25, ease: "power3.out"}}, '
            f"{(start + 0.1 + i * 0.08):.3f});"
        )
    js.append(
        f'gsap.set("#{oid} .ov-red-stamp", {{opacity: 0, scale: 0.5, rotation: 0}});'
    )
    js.append(
        f'tl.to("#{oid} .ov-red-stamp", {{opacity: 1, scale: 1, rotation: -12, '
        f'duration: 0.3, ease: "back.out(2.5)"}}, {(start + 0.5):.3f});'
    )
    js.append(
        f'tl.to("#{oid}", {{opacity: 0, duration: 0.4, ease: "power2.in"}}, '
        f"{(start + dur - 0.4):.3f});"
    )
    js.append(f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});')
    return [html], js


def _ov_entity(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_ov_ent"
    start = scene_start + 1.0
    dur = min(4.5, audio_duration - 1.5)
    html = (
        f'<div id="{oid}" class="ov-entity clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{scene_idx * 20 + 15 + spec.get("idx", 0)}">'
        f'<svg class="ov-ent-radar" viewBox="0 0 200 200">'
        f'<circle cx="100" cy="100" r="90" fill="none" stroke="#ff2424" stroke-width="2" opacity="0.6"/>'
        f'<circle cx="100" cy="100" r="60" fill="none" stroke="#ff2424" stroke-width="1.5" opacity="0.45"/>'
        f'<circle cx="100" cy="100" r="30" fill="none" stroke="#ff2424" stroke-width="1" opacity="0.3"/>'
        f'<line x1="100" y1="100" x2="100" y2="10" stroke="#ff2424" stroke-width="2" opacity="0.8">'
        f'<animateTransform attributeName="transform" type="rotate" '
        f'from="0 100 100" to="360 100 100" dur="2.2s" repeatCount="indefinite"/>'
        f"</line>"
        f'<circle cx="100" cy="100" r="4" fill="#ff2424"/>'
        f'<circle cx="140" cy="78" r="6" fill="#ff8080">'
        f'<animate attributeName="opacity" values="1;0.2;1" dur="0.8s" repeatCount="indefinite"/>'
        f"</circle>"
        f'<circle cx="65" cy="135" r="5" fill="#ff8080">'
        f'<animate attributeName="opacity" values="0.3;1;0.3" dur="1.1s" repeatCount="indefinite"/>'
        f"</circle>"
        f"</svg>"
        f'<div class="ov-ent-text">'
        f'<div class="ov-ent-label">⚠ ENTITÉ DÉTECTÉE</div>'
        f'<div class="ov-ent-sub">NATURE : INCONNUE</div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 0.7, rotation: -8}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, rotation: 0, duration: 0.5, '
        f'ease: "back.out(1.8)"}}, {start:.3f});',
        # Pulse continu
        f'tl.to("#{oid}", {{scale: 1.04, duration: 0.5, yoyo: true, repeat: 5, '
        f'ease: "sine.inOut"}}, {(start + 0.6):.3f});',
        f'tl.to("#{oid}", {{opacity: 0, scale: 0.85, duration: 0.4, ease: "power2.in"}}, '
        f"{(start + dur - 0.4):.3f});",
        f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
    ]
    return [html], js


def _ov_person(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_ov_per"
    start = scene_start + 0.7
    dur = min(5.0, audio_duration - 1.2)
    name = html_escape(spec["value"])
    role = html_escape(spec.get("role", "WITNESS"))
    initials = "".join([p[0].upper() for p in spec["value"].split()[:2]])
    html = (
        f'<div id="{oid}" class="ov-person clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{scene_idx * 20 + 15 + spec.get("idx", 0)}">'
        f'<div class="ov-per-card">'
        f'<div class="ov-per-avatar">'
        f'<div class="ov-per-initials">{initials}</div>'
        f'<div class="ov-per-scan"></div>'
        f"</div>"
        f'<div class="ov-per-info">'
        f'<div class="ov-per-id">'
        f'<span class="ov-ico ov-per-ico">{ICONS["eye"]}</span>'
        f"ID #{(scene_idx * 7919) % 99999:05d}</div>"
        f'<div class="ov-per-name">{name}</div>'
        f'<div class="ov-per-role">{role}</div>'
        f'<div class="ov-per-status">◉ STATUT : ACTIF</div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )


def _ov_generative_agent(s_id, scene_idx, scene_start, audio_duration, spec):
    # Deprecated: generative agent visual overlays are disabled due to RCE risks.
    # Use structured SceneDirectorPlan instead.
    return [], []


def _ov_map_zoom(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_ov_mapz"
    start = scene_start
    dur = audio_duration
    label = html_escape(spec["value"])
    iso = spec.get("iso") or ""
    lnglat = spec.get("lnglat") or [0, 0]
    map_id = f"{oid}_fs_map"

    html = (
        f'<div id="{oid}" class="ov-map-zoom clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{scene_idx * 20 + 15 + spec.get("idx", 0)}" '
        f'style="position:absolute; inset:0; z-index:15; overflow:hidden;">'
        f'<div class="fs-map-container" id="{oid}_container" style="position:absolute; width:1080px; height:1920px; left:0; top:0;">'
        f'<svg id="{map_id}" viewBox="0 0 1080 1920" style="width:100%; height:100%; background:var(--bg-deep);"></svg>'
        f"</div>"
        f'<div class="map-overlay-ui" style="position:absolute; inset:0; pointer-events:none; z-index:16;">'
        # Grid lines
        f'<div style="position:absolute; top:50%; left:0; right:0; height:1px; background:rgba(255,56,56,0.3);"></div>'
        f'<div style="position:absolute; left:50%; top:0; bottom:0; width:1px; background:rgba(255,56,56,0.3);"></div>'
        # Crosshair center
        f'<div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); width:120px; height:120px; border:2px solid var(--accent); border-radius:50%; box-shadow:0 0 20px rgba(255,56,56,0.5);"></div>'
        # Top Text
        f'<div style="position:absolute; top:120px; left:0; right:0; text-align:center;">'
        f'<div style="color:var(--accent); font-family:var(--font-display2); font-size:36px; letter-spacing:14px; text-transform:uppercase;">SATELLITE LINK ESTABLISHED</div>'
        f'<div style="color:white; font-family:var(--font-display); font-size:110px; line-height:1; margin-top:20px; letter-spacing:4px;">{label}</div>'
        f'<div style="color:var(--muted); font-family:var(--font-mono); font-size:24px; margin-top:20px; letter-spacing:4px;">COORD: {lnglat[0]:.4f}, {lnglat[1]:.4f}</div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )

    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.6, ease: "power2.out"}}, {start:.3f});',
        # Zoom effect on the SVG container
        f'gsap.set("#{oid}_container", {{scale: 1.0, transformOrigin: "50% 50%"}});',
        f'tl.to("#{oid}_container", {{scale: 4.5, duration: {dur:.3f}, ease: "power2.inOut"}}, {start:.3f});',
        f'tl.to("#{oid}", {{opacity: 0, duration: 0.6, ease: "power2.in"}}, {(start + dur - 0.6):.3f});',
        f'window.__renderMap && window.__renderMap("{map_id}", [{lnglat[0]}, {lnglat[1]}], "{iso}", 1080, 1920);',
    ]
    return [html], js


OVERLAY_BUILDERS = {otype: _ov_sem_card for otype in SEMANTIC_ANIMATION_TYPES}
OVERLAY_BUILDERS.update(
    {
        "map_zoom": _ov_sem_map_zoom,
        "satellite_sweep": _ov_sem_satellite,
        "map_pin_drop": _ov_sem_satellite,
        "coordinates_lock": _ov_sem_satellite,
        "proximity_alert": _ov_sem_satellite,
        "message_send": _ov_sem_message,
        "year_marker": _ov_sem_year,
        "calendar_flip": _ov_sem_timewarp,
        "time_jump": _ov_sem_timewarp,
        "counter": _ov_sem_counter,
        "cctv_scan": _ov_sem_cctv,
        "security_log": _ov_sem_security_matrix,
        "motion_detector": _ov_sem_security_matrix,
        "file_open": _ov_sem_file,
        "evidence_photo": _ov_sem_file,
        "newspaper_clip": _ov_sem_file,
        "court_record": _ov_sem_file,
        "archive_box": _ov_sem_file,
        "archive_stamp": _ov_sem_file,
        "object_isolate": _ov_sem_file,
        "document_leak": _ov_sem_file,
        "breaking_news": _ov_sem_file,
        "redacted_report": _ov_sem_redacted,
        "classified_stamp": _ov_sem_redacted,
        "entity_radar": _ov_sem_radar,
        "radio_signal": _ov_sem_radar,
        "audio_waveform": _ov_sem_radar,
        "search_grid": _ov_sem_search,
        "underground_depth": _ov_sem_depth,
        "route_trace": _ov_sem_route,
        "footprint_trail": _ov_sem_route,
        "question_prompt": _ov_sem_question,
        "power_cut": _ov_sem_blackout,
        "neon_bar": _ov_sem_blackout,
        "searchlight": _ov_sem_blackout,
    }
)
for _otype in ("missing_person", "missing_poster", "last_seen_marker", "family_photo"):
    OVERLAY_BUILDERS[_otype] = _ov_sem_poster
for _otype in (
    "floor_plan",
    "exit_scan",
    "blind_spot",
    "corridor_scan",
    "door_open",
    "sealed_door",
    "basement_elevator",
):
    OVERLAY_BUILDERS[_otype] = _ov_sem_blueprint
for _otype in (
    "audio_waveform",
    "radio_signal",
    "voice_print",
    "signal_jammer",
    "phone_call",
    "heartbeat_monitor",
    "crowd_noise",
    "room_tone",
):
    OVERLAY_BUILDERS[_otype] = _ov_sem_signal
for _otype in (
    "medical_scan",
    "lab_sample",
    "mind_control",
    "memory_flash",
    "experiment_chamber",
    "thermal_scan",
    "dna_spiral",
    "timeline_split",
):
    OVERLAY_BUILDERS[_otype] = _ov_sem_experiment
for _otype in (
    "interrogation_note",
    "witness_card",
    "witness_quote",
    "case_board",
    "evidence_thread",
    "theory_stack",
    "official_denial",
):
    OVERLAY_BUILDERS[_otype] = _ov_sem_caseboard


def build_overlay_blocks(
    s_id, scene_idx, scene_start, audio_duration, subtitle_text, visual_bible=None
):
    """Détecte et construit les overlays sémantiques pour la scène."""
    overlays = detect_overlays(
        subtitle_text, visual_bible=visual_bible, scene_idx=scene_idx
    )
    overlays = _diversify_overlay_types(overlays, scene_idx)
    overlays = _prepare_overlay_schedule(overlays, audio_duration, scene_idx)
    all_html, all_js = [], []
    for m, spec in enumerate(overlays):
        spec["idx"] = m
        builder = OVERLAY_BUILDERS.get(spec["type"])
        if not builder:
            continue
        html, js = builder(s_id, scene_idx, scene_start, audio_duration, spec)
        all_html.extend(html)
        all_js.extend(js)
    return all_html, all_js, [s["type"] for s in overlays]


# Tracks which Lottie asset_ids the Director has already used in the current
# render. Read when building each scene's prompt, written after the LLM picks.
# Reset at the start of `traiter_render` so state doesn't leak between videos.
_DIRECTOR_USED_LOTTIE: list[str] = []


def _reset_director_state():
    """Call at the start of every fresh render to clear per-scene memory."""
    _DIRECTOR_USED_LOTTIE.clear()


def _word_timeline_time(scene_start, word_timings, targets, fallback):
    """Retourne le timecode absolu du premier mot cible aligné par Whisper."""
    normalized_targets = {_normalize_word(target) for target in targets}
    for word in word_timings or []:
        if _normalize_word(word.get("text", "")) in normalized_targets:
            return scene_start + float(word.get("start", 0.0))
    return scene_start + fallback


def build_curated_lottie_accents(
    scene_idx,
    scene_start,
    audio_duration,
    subtitle_text,
    word_timings,
):
    """Place la manifestation Yurei uniquement sur les disparitions."""
    if not USE_LOTTIE_OVERLAYS:
        return [], []

    folded = _normalize_word(subtitle_text)
    scene_end = scene_start + audio_duration
    specs = []

    def add(
        asset_id,
        absolute_time,
        duration,
        x_pct=50,
        y_pct=50,
        width_pct=100,
        height_pct=100,
        opacity=0.3,
        blend_mode="screen",
        monochrome=True,
        reason="",
    ):
        start = max(scene_start + 0.2, min(float(absolute_time), scene_end - 0.2))
        safe_duration = min(float(duration), max(0.2, scene_end - start - 0.05))
        specs.append(
            {
                "asset_id": asset_id,
                "in_time": start,
                "duration": safe_duration,
                "x_pct": x_pct,
                "y_pct": y_pct,
                "width_pct": width_pct,
                "height_pct": height_pct,
                "opacity": opacity,
                "blend_mode": blend_mode,
                "monochrome": monochrome,
                "reason": reason,
            }
        )

    # The red fracture lands around 62% of the authored animation. Start from
    # the mirror cue so the apparition has time to form before the reveal.
    if "retroviseur" in folded and "vide" in folded:
        mirror_cue = _word_timeline_time(
            scene_start,
            word_timings,
            {"rétroviseur", "retroviseur"},
            audio_duration * 0.35,
        )
        reveal_cue = _word_timeline_time(
            scene_start,
            word_timings,
            {"vide"},
            audio_duration * 0.68,
        )
        start = max(scene_start + 0.25, mirror_cue - 0.38)
        duration = max(2.8, min(4.1, (reveal_cue - start) / 0.62))
        add(
            "yurei_mirror_manifestation",
            start,
            duration,
            x_pct=50,
            y_pct=38,
            width_pct=80,
            height_pct=32,
            opacity=0.82,
            blend_mode="normal",
            monochrome=False,
            reason=(
                "La Dame Blanche se forme dans le rétroviseur puis se "
                "désagrège exactement sur la révélation de la banquette vide."
            ),
        )

    # Reuse the same spectral language on the second disappearance. This acts
    # as a channel signature, not as a decorative overlay.
    elif "disparu" in folded:
        reveal_cue = _word_timeline_time(
            scene_start,
            word_timings,
            {"disparu"},
            audio_duration * 0.62,
        )
        duration = min(3.2, max(2.6, audio_duration * 0.42))
        start = max(scene_start + 0.25, reveal_cue - duration * 0.62)
        add(
            "yurei_mirror_manifestation",
            start,
            duration,
            x_pct=50,
            y_pct=36,
            width_pct=68,
            height_pct=30,
            opacity=0.76,
            blend_mode="normal",
            monochrome=False,
            reason=(
                "La signature spectrale réapparaît dans la vitre arrière et "
                "s'évapore sur le mot disparu."
            ),
        )

    if not specs:
        return [], []

    html, js = build_lottie_overlays_for_scene(
        specs, scene_idx, frame_w=WIDTH, frame_h=HEIGHT, fps=FPS
    )
    if html:
        print(
            f"   🎞️  Lottie Yūrei : {[spec['asset_id'] for spec in specs]}"
        )
    return html, js


def generate_master_director_agent(
    s_id,
    scene_idx,
    scene_start,
    audio_duration,
    subtitle_text,
    images,
    visual_bible=None,
):
    """
    Appelle Gemini de manière structurée via response_schema (SceneDirectorPlan) pour déterminer
    la composition visuelle de la scène, puis génère le HTML + JS GSAP de manière déterministe et sécurisée.
    """
    if gemini_client is None:
        return None

    image_paths = []
    if images:
        for j, img in enumerate(images[:6]):
            img_id = f"{s_id}_bg{j + 1}"
            image_paths.append(f"assets/{img_id}{img.suffix}")

    lottie_catalog = lottie_choices_summary()
    # Build a compact usage histogram so the prompt explicitly nudges variety.
    if _DIRECTOR_USED_LOTTIE:
        from collections import Counter

        counts = Counter(_DIRECTOR_USED_LOTTIE)
        usage_hint = ", ".join(f"{k} (×{v})" for k, v in counts.most_common())
    else:
        usage_hint = "(none yet — this is the first scene)"
    lottie_block = ""
    if USE_LOTTIE_OVERLAYS and load_lottie_manifest().get("assets"):
        lottie_block = f"""
LOTTIE LIBRARY (you may sprinkle 0 to 3 motion-graphic accents — choose `asset_id` from this list ONLY):
{lottie_catalog}

Sizing rules — CRITICAL, read carefully:
- Procedural assets (scanline_sweep, glitch_burst, redacted_bar, vignette_pulse, crosshair_scan, radar_ping)
  are HUD-style overlays purpose-built to fill the frame. Use width_pct=100, height_pct=100, x_pct=50, y_pct=50.
- Curated assets (every id starting with `lf_`) are STANDALONE illustrations/loaders, not corner brackets.
  They will dominate the image if placed full-frame. Treat them as ACCENT widgets:
    * width_pct between 18 and 35, height_pct equal to width_pct (square box).
    * Place in a corner (x_pct/y_pct from {{18, 30, 70, 82}} pairs) — never centered over the subject.
    * Drop opacity to 0.35-0.6 so they read as ambient texture, not as main content.
  Exceptions: `lf_sonar_wave` and `lf_smoke_wisp` are atmospheric layers and may use width_pct up to 100
  if opacity stays ≤ 0.4.

General guidelines for `lottie_overlays`:
- Default to [] unless the narration genuinely benefits from a punctual visual accent (a glitch on a revelation, a radar ping on a location reveal, a redacted bar over a name, a crosshair over a face/object).
- `in_time` is RELATIVE to this scene (0.0 = scene start). Keep `in_time + duration` < scene duration.
- One strong, well-timed accent beats three muddled ones. Never stack two overlays at the same instant.
- Set duration to 0 to use each asset's natural duration, or override for a tighter pulse.
- Keep `monochrome` = true unless you really need an out-of-style accent.
- VARIETY ENFORCEMENT: across the full video, each `asset_id` should ideally appear at most twice.
  `glitch_burst` is reserved for genuine revelations — cap it at 2 uses total. The library has 19 assets;
  use the under-utilised ones (evidence_pin_thread, magnifier_sweep, fingerprint_reveal, redacted_tear,
  surveillance_rec, radar_sweep) when their description matches the narration.

ALREADY USED IN EARLIER SCENES OF THIS SAME VIDEO (avoid repeating, vary your choices):
{usage_hint}
"""

    prompt = f"""You are the MASTER VISUAL ARCHITECT for a TikTok true-crime video renderer.
Analyze the scene details and choose the best visual plan configuration to create a dark, tense, high-end documentary look.

SCENE DETAILS:
• Text: "{subtitle_text}"
• Duration: {audio_duration:.3f}s  |  Timeline start: {scene_start:.3f}s
• Images available: {json.dumps(image_paths)}
• Visual Bible: {json.dumps(visual_bible) if visual_bible else "None"}
{lottie_block}"""

    print(
        f"   🎬 Director Agent réfléchit pour la scène {scene_idx + 1} (Pydantic / Structured Output)..."
    )

    plan = None
    import time

    for attempt in range(3):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=SceneDirectorPlan,
                ),
            )
            plan = SceneDirectorPlan.model_validate_json(response.text.strip())
            break
        except Exception as e:
            print(f"   ⚠️ Erreur Director Agent (Essai {attempt + 1}/3) : {e}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                return None

    if plan is None:
        return None

    print(f"   🎥 Stratégie choisie: {plan.strategy}")
    print(
        f"   📊 Config: BG={plan.background_effect}, Cam={plan.camera_move}, HUD={plan.hud_effect}, Glitches={plan.glitch_triggers}"
    )

    html_parts = []
    js_parts = []

    s_id_master = f"{s_id}_master"
    html_parts.append(
        f'<div id="{s_id_master}" class="clip" '
        f'data-start="{scene_start:.3f}" data-duration="{audio_duration:.3f}" '
        f'data-track-index="{scene_idx * 20}" '
        f'style="position:absolute;inset:0;z-index:10;overflow:hidden;opacity:0;">'
    )

    # background
    bg_html, bg_js = build_procedural_bg(
        scene_idx, scene_start, audio_duration, bg_type=plan.background_effect
    )
    html_parts.append(bg_html)
    js_parts.extend(bg_js)

    # images
    shots = len(images)
    if shots > 0:
        slice_dur = audio_duration / shots
        for j in range(shots):
            img = images[j]
            start = scene_start + j * slice_dur
            dur = slice_dur + (1.2 if j < shots - 1 else 0)
            img_html, img_js = build_image_block(
                s_id,
                j,
                img,
                scene_idx,
                start,
                dur,
                is_last=(j == shots - 1),
                in_transition_from_prev=(j > 0),
                total_scenes=10,
                source_type="",
                camera_move=plan.camera_move,
            )
            html_parts.append(img_html)
            js_parts.extend(img_js)

    # hud fx
    fx_html, fx_js = build_scene_director_fx(
        s_id,
        scene_idx,
        scene_start,
        audio_duration,
        subtitle_text,
        hud_effect=plan.hud_effect,
    )
    html_parts.extend(fx_html)
    js_parts.extend(fx_js)

    # Lottie motion-graphic overlays (chosen by the Director Agent).
    # The LLM emits scene-relative timestamps; we make them absolute here and
    # clamp durations so an overlay never escapes its scene window.
    # Hard-gated by USE_LOTTIE_OVERLAYS — when off, we ignore any overlay
    # the LLM may still have hallucinated despite the prompt being trimmed.
    lottie_specs_abs = []
    if not USE_LOTTIE_OVERLAYS:
        plan.lottie_overlays = []
    for ov in plan.lottie_overlays or []:
        spec = ov.model_dump() if hasattr(ov, "model_dump") else dict(ov)
        rel_t = max(0.0, float(spec.get("in_time", 0.0)))
        spec["in_time"] = scene_start + rel_t
        raw_dur = float(spec.get("duration", 0.0) or 0.0)
        max_dur = max(0.2, audio_duration - rel_t - 0.05)
        # 0 / negative => let the validator fall back to the asset's natural duration,
        # but never exceed the remaining scene window.
        if raw_dur > 0:
            spec["duration"] = min(raw_dur, max_dur)
        else:
            spec["duration"] = max_dur
        lottie_specs_abs.append(spec)
        # Track usage so subsequent scenes in the same render get a "already used" hint.
        aid = spec.get("asset_id")
        if aid:
            _DIRECTOR_USED_LOTTIE.append(aid)

    if lottie_specs_abs:
        lottie_html, lottie_js = build_lottie_overlays_for_scene(
            lottie_specs_abs, scene_idx, frame_w=WIDTH, frame_h=HEIGHT, fps=FPS
        )
        if lottie_html:
            print(
                f"   🎞️  Lottie overlays: {len(lottie_html)} → {[s.get('asset_id') for s in lottie_specs_abs]}"
            )
        html_parts.extend(lottie_html)
        js_parts.extend(lottie_js)

    html_parts.append("</div>")

    master_fade_js = [
        f'gsap.set("#{s_id_master}", {{opacity: 0}});',
        f'tl.to("#{s_id_master}", {{opacity: 1, duration: 0.5}}, {scene_start:.3f});',
    ]

    # glitch triggers (GSAP toggles on global glitch overlay)
    for trigger_time in plan.glitch_triggers:
        abs_t = scene_start + trigger_time
        if abs_t >= scene_start and abs_t < scene_start + audio_duration - 0.2:
            master_fade_js.extend(
                [
                    f'tl.to("#glitch-overlay", {{opacity: 0.82, duration: 0.05, repeat: 3, yoyo: true, ease: "steps(1)"}}, {abs_t:.3f});',
                    f'tl.set("#glitch-overlay", {{opacity: 0}}, {(abs_t + 0.2):.3f});',
                ]
            )

    # vignette
    abs_end = scene_start + audio_duration
    master_fade_js.extend(
        [
            f'tl.to("#vignette", {{opacity: {0.85 * plan.vignette_intensity:.3f}, duration: 0.5}}, {scene_start:.3f});',
            f'tl.to("#{s_id_master}", {{opacity: 0, duration: 0.5}}, {(abs_end - 0.5):.3f});',
            f'tl.set("#{s_id_master}", {{opacity: 0}}, {abs_end:.3f});',
        ]
    )

    js_parts.extend(master_fade_js)

    return ["\n".join(html_parts)], js_parts, plan.strategy


def _act_grading_filter(scene_idx, total_scenes):
    """Retourne un CSS filter chain selon l'acte narratif.

    Default is now a darker, more restrained true-crime grade: less saturated,
    deeper blacks, and no warm/yellow climax. This reads more premium with
    low-poly 3D stills than the earlier colorful anime-style grading.
    """
    if not USE_ACT_GRADING or total_scenes <= 0:
        return "contrast(1.16) saturate(0.82) brightness(0.76)"
    progress = scene_idx / max(1, total_scenes - 1)
    if progress < 0.30:
        return "contrast(1.18) saturate(0.78) brightness(0.74) hue-rotate(2deg)"
    if progress < 0.70:
        return "contrast(1.20) saturate(0.76) brightness(0.72) hue-rotate(0deg)"
    return "contrast(1.22) saturate(0.72) brightness(0.70) hue-rotate(-2deg)"


def build_image_block(
    s_id,
    j,
    img_path,
    scene_idx,
    start,
    dur,
    is_last,
    in_transition_from_prev=False,
    total_scenes=10,
    source_type="",
    camera_move=None,
):
    """Génère HTML + GSAP pour 1 image avec Ken Burns + apparition instantanée.

    Le clip démarre légèrement avant le timecode du plan pour laisser Chromium
    charger/décoder l'image. Pendant cette avance, l'image reste à opacity:0;
    au vrai début du plan, un tl.set la passe immédiatement à opacity:1.
    """
    img_id = f"{s_id}_bg{j + 1}"

    variant = None
    if camera_move:
        camera_move = camera_move.lower()
        if "dolly_in" in camera_move:
            variant = MOTION_VARIANTS[0]
        elif "dolly_out" in camera_move:
            variant = MOTION_VARIANTS[2]
        elif "pan_left" in camera_move:
            variant = MOTION_VARIANTS[1]
        elif "pan_right" in camera_move:
            variant = MOTION_VARIANTS[7]
        elif "zoom_pan" in camera_move:
            variant = MOTION_VARIANTS[4]
        elif "static" in camera_move:
            variant = MOTION_VARIANTS[8]

    if not variant:
        # Hash déterministe mais désynchronisé entre scenes/plans pour casser
        # l'impression de "même mouvement à chaque fois". On combine scene_idx,
        # j, et un offset premier pour éviter toute périodicité visible.
        variant_idx = (scene_idx * 3 + j * 7 + scene_idx * j) % len(MOTION_VARIANTS)
        variant = MOTION_VARIANTS[variant_idx]
    tilt_table = [-0.28, 0.22, -0.14, 0.24, -0.18, 0.16, -0.20, 0.12]
    tilt = tilt_table[(scene_idx * 2 + j * 3) % len(tilt_table)]
    is_first_shot = j == 0 and not in_transition_from_prev
    is_generated_media = "generated" in (source_type or "")

    # Rythme: les plans courts sont plus tendus (intensité +), les plans longs
    # plus calmes (intensité -). Une vidéo qui respire entre plans = beaucoup
    # plus pro qu'une vidéo où tout va à la même vitesse.
    base_intensity = float(variant.get("intensity", 1.0))
    if dur < 2.5:
        rhythm = 1.18
    elif dur < 4.5:
        rhythm = 1.08
    elif dur < 7.5:
        rhythm = 1.02
    else:
        rhythm = 0.96
    intensity = base_intensity * rhythm * MOTION_STRENGTH

    is_video = img_path.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm")
    if is_video:
        preload_lead = min(0.6, max(0.0, start))
        clip_start = max(0.0, start - preload_lead)
        clip_dur = dur + preload_lead + 0.3
    else:
        preload_lead = start
        clip_start = 0.0
        clip_dur = start + dur + 0.3

    # z-index croissant mais ≤ 19 pour rester SOUS les overlays sémantiques
    # (.sem-overlay z-index 22-25, .dir-layer 18 — l'image reste au fond, les
    # animations apparaissent par-dessus).
    z_index = scene_idx + 10

    start_state = {
        "opacity": 0 if preload_lead > 0 else 1,
        "rotation": round(tilt * 0.35, 3),
        "transformOrigin": '"50% 50%"',
        **variant["start"],
    }

    initial_opacity = 0 if preload_lead > 0 else 1
    if is_video:
        html = (
            f'<video id="{img_id}" class="bg clip {"media-ai" if is_generated_media else "media-real"}" src="assets/{img_id}{img_path.suffix}" '
            f"autoplay loop muted playsinline "
            f'style="opacity: {initial_opacity}; z-index: {z_index}; object-fit: contain; width: 100%; height: 100%; background: #050505;" '
            f'data-start="{clip_start:.3f}" data-duration="{clip_dur:.3f}" '
            f'data-track-index="{scene_idx * 20 + j}"></video>'
        )
    else:
        html = (
            f'<img id="{img_id}" class="bg clip {"media-ai" if is_generated_media else "media-real"}" src="assets/{img_id}{img_path.suffix}" '
            f'loading="eager" decoding="sync" fetchpriority="high" '
            f'style="opacity: {initial_opacity}; z-index: {z_index}; object-fit: contain; background: #050505;" '
            f'data-start="{clip_start:.3f}" data-duration="{clip_dur:.3f}" '
            f'data-track-index="{scene_idx * 20 + j}" />'
        )
    atmo_id = f"{img_id}_atmo"
    html += (
        f'<div id="{atmo_id}" class="motion-atmosphere clip" '
        f'style="opacity:0; z-index:{z_index + 1};" '
        f'data-start="{clip_start:.3f}" data-duration="{clip_dur:.3f}" '
        f'data-track-index="{4000 + scene_idx * 10 + j}"></div>'
    )

    grading = _act_grading_filter(scene_idx, total_scenes)
    if os.getenv("VISUAL_STYLE") == "noir":
        # Mode mystère B&W : désaturation totale + fort contraste
        grading = "grayscale(1) contrast(1.25) brightness(0.88)"
    elif is_generated_media:
        grading = f"{grading} saturate(1.08) contrast(1.06)"
    start_state["filter"] = f'"{grading}"'

    js = []
    js.append(f'gsap.set("#{img_id}", {gsap_obj(start_state)});')
    if preload_lead > 0:
        if is_generated_media or j > 0:
            js.append(
                f'tl.to("#{img_id}", {{opacity: 1, duration: 0.36, ease: "power2.out", overwrite: "auto"}}, {start:.3f});'
            )
        else:
            js.append(f'tl.set("#{img_id}", {{opacity: 1}}, {start:.3f});')
    else:
        # Force opacity:1 dans le timeline GSAP au moment exact où HyperFrames
        # rend l'élément visible. Garantit qu'au cut, l'image N+1 n'est jamais
        # transparente (sinon écran noir entre flash et image).
        js.append(f'tl.set("#{img_id}", {{opacity: 1}}, {start:.3f});')

    # Ken Burns éditorial: zoom/pan + tilt discret + grading respirant par acte.
    # On amplifie/atténue le mouvement avec `intensity` (issu du variant + du
    # rythme par durée) pour que chaque plan ait sa propre énergie.
    def _scale(v, around=0.0):
        return around + (float(v) - around) * intensity

    motion_props = {}
    raw_end = variant["end"]
    base_scale = float(raw_end.get("scale", 1.0))
    motion_props["scale"] = round(_scale(base_scale, around=1.0), 4)
    motion_props["x"] = round(_scale(raw_end.get("x", 0)), 2)
    motion_props["y"] = round(_scale(raw_end.get("y", 0)), 2)
    motion_props["rotationY"] = raw_end.get("rotationY", 0)
    motion_props["rotationX"] = raw_end.get("rotationX", 0)
    motion_props["z"] = raw_end.get("z", 0)

    if is_generated_media:
        # Les images IA supportent un mouvement 2,5D plus ample. L'amplitude
        # reste cinématique mais doit être immédiatement perceptible sur mobile.
        motion_props["scale"] = round(float(motion_props["scale"]) + 0.075, 4)
        motion_props["x"] = round(
            motion_props["x"] + (42 if (scene_idx + j) % 2 == 0 else -42), 2
        )
        motion_props["y"] = round(
            motion_props["y"] + (-28 if (scene_idx + j) % 2 == 0 else 28), 2
        )
        motion_props["rotationY"] = round(
            (1.35 if (scene_idx + j) % 2 == 0 else -1.35) * intensity, 3
        )
        motion_props["rotationX"] = round(
            (-0.70 if j % 2 == 0 else 0.70) * intensity, 3
        )
    else:
        # Médias réels: on plafonne le zoom pour préserver la lisibilité.
        motion_props["scale"] = min(float(motion_props["scale"]), 1.030)

    # Easing varié par variant + tilt léger.
    ease_name = variant.get("ease", "sine.inOut")
    motion_props["rotation"] = round(tilt * (0.6 + 0.4 * intensity), 3)
    motion_props["duration"] = round(dur, 3)
    motion_props["ease"] = f'"{ease_name}"'
    motion_props["overwrite"] = '"auto"'
    js.append(f'tl.to("#{img_id}", {gsap_obj(motion_props)}, {start:.3f});')

    # Brume en contre-mouvement : elle donne une profondeur 2,5D lisible sans
    # recouvrir le sujet ni ajouter de HUD.
    atmo_direction = 1 if (scene_idx + j) % 2 == 0 else -1
    js.append(
        f'gsap.set("#{atmo_id}", {{opacity:0, x:{-150 * atmo_direction}, '
        f'y:{30 if j % 2 == 0 else -30}, scale:1.04, rotation:{-3 * atmo_direction}}});'
    )
    js.append(
        f'tl.to("#{atmo_id}", {{opacity:0.28, duration:0.55, ease:"power2.out"}}, '
        f'{start:.3f});'
    )
    js.append(
        f'tl.to("#{atmo_id}", {{x:{150 * atmo_direction}, '
        f'y:{-36 if j % 2 == 0 else 36}, scale:1.24, rotation:{3 * atmo_direction}, duration:{dur:.3f}, '
        f'ease:"sine.inOut"}}, {start:.3f});'
    )
    js.append(
        f'tl.to("#{atmo_id}", {{opacity:0.36, duration:{max(0.35, dur * 0.20):.3f}, '
        f'ease:"sine.inOut", yoyo:true, repeat:1}}, '
        f'{(start + dur * 0.34):.3f});'
    )
    js.append(
        f'tl.to("#{atmo_id}", {{opacity:0, duration:0.45, ease:"power2.in"}}, '
        f'{max(start, start + dur - 0.45):.3f});'
    )

    # Masquer l'image proprement à la fin de sa durée pour éviter les chevauchements
    js.append(f'tl.set("#{img_id}", {{opacity: 0}}, {(start + dur):.3f});')
    js.append(f'tl.set("#{atmo_id}", {{opacity: 0}}, {(start + dur):.3f});')

    return html, js


def build_scene_director_fx(
    s_id, scene_idx, scene_start, audio_duration, subtitle_src, hud_effect="scanner"
):
    """Couches de réalisation déterministes: scan, cadre, lumière et dossier.
    Désactivé en mode drama (USE_PERSISTENT_CASE_TAG=0) — pas de CASE/EVIDENCE/scanner."""
    if not USE_PERSISTENT_CASE_TAG:
        return [], []
    hud_effect = (hud_effect or "scanner").lower()
    case_no = f"{(scene_idx + 1) * 137:04d}-{(scene_idx * 73 + 19) % 97:02d}"
    severity = ["TRACE", "EVIDENCE", "ARCHIVE", "MISSING", "SEALED"][scene_idx % 5]
    side = "left" if scene_idx % 2 == 0 else "right"
    oid = f"{s_id}_dir"
    scan_id = f"{oid}_scan"
    pulse_id = f"{oid}_pulse"
    meta_id = f"{oid}_meta"
    rule_id = f"{oid}_rule"

    scan_html = (
        f'<div id="{scan_id}" class="dir-scan"></div>'
        if hud_effect == "scanner"
        else ""
    )
    pulse_html = (
        f'<div id="{pulse_id}" class="dir-pulse"></div>'
        if hud_effect == "radar"
        else ""
    )
    ticker_html = ""
    if hud_effect == "ticker":
        ticker_html = (
            f'<div id="{oid}_ticker" style="position:absolute; bottom:160px; right:48px; '
            f"font-family:var(--font-mono); font-size:16px; color:var(--accent); opacity:0.8; "
            f'letter-spacing:1px;">DECRYPTING: <span id="{oid}_t_val">0x0000</span></div>'
        )

    html = [
        (
            f'<div id="{oid}" class="dir-layer clip" '
            f'data-start="{scene_start:.3f}" data-duration="{audio_duration:.3f}" '
            f'data-track-index="{scene_idx * 20 + 12}">'
            f'<div class="dir-corner tl"></div><div class="dir-corner tr"></div>'
            f'<div class="dir-corner bl"></div><div class="dir-corner br"></div>'
            f"{scan_html}"
            f"{pulse_html}"
            f"{ticker_html}"
            f'<div id="{meta_id}" class="dir-meta {side}">'
            f"<span>CASE {case_no}</span><strong>{severity}</strong>"
            f"</div>"
            f'<div id="{rule_id}" class="dir-rule"></div>'
            f"</div>"
        )
    ]

    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{meta_id}", {{opacity: 0, y: -18}});',
        f'gsap.set("#{rule_id}", {{scaleX: 0, transformOrigin: "50% 50%"}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.45, ease: "power2.out"}}, {scene_start:.3f});',
        f'tl.to("#{meta_id}", {{opacity: 1, y: 0, duration: 0.55, ease: "power3.out"}}, {(scene_start + 0.18):.3f});',
        f'tl.to("#{rule_id}", {{scaleX: 1, duration: 0.7, ease: "expo.out"}}, {(scene_start + 0.25):.3f});',
    ]

    if hud_effect == "scanner":
        js.extend(
            [
                f'gsap.set("#{scan_id}", {{y: -260, opacity: 0}});',
                f'tl.to("#{scan_id}", {{y: 2100, opacity: 0.65, duration: {min(audio_duration * 0.72, 7.5):.3f}, ease: "power1.inOut"}}, {(scene_start + 0.5):.3f});',
            ]
        )
    elif hud_effect == "radar":
        pulse_in = scene_start + max(0.8, audio_duration * 0.34)
        pulse_out = pulse_in + 1.12
        js.extend(
            [
                f'gsap.set("#{pulse_id}", {{scale: 0.85, opacity: 0}});',
                f'tl.to("#{pulse_id}", {{opacity: 0.28, scale: 1.18, duration: 1.1, ease: "sine.out", overwrite: "auto"}}, {pulse_in:.3f});',
                f'tl.to("#{pulse_id}", {{opacity: 0, scale: 1.55, duration: 0.85, ease: "power2.in", overwrite: "auto"}}, {pulse_out:.3f});',
                f'tl.set("#{pulse_id}", {{opacity: 0}}, {(scene_start + audio_duration):.3f});',
            ]
        )
    elif hud_effect == "ticker":
        ticker_val_id = f"{oid}_t_val"
        js.extend(
            [
                f"const {oid}_t_obj = {{val: 0}};",
                f'tl.to({oid}_t_obj, {{val: 65535, duration: {audio_duration:.3f}, ease: "none", '
                f'onUpdate: () => {{ const el = document.getElementById("{ticker_val_id}"); '
                f'if (el) el.innerText = "0x" + Math.floor({oid}_t_obj.val).toString(16).toUpperCase(); }}}}, '
                f"{scene_start:.3f});",
            ]
        )

    js.extend(
        [
            f'tl.to("#{meta_id}", {{opacity: 0, y: -12, duration: 0.35, ease: "power2.in"}}, {(scene_start + audio_duration - 0.55):.3f});',
            f'tl.to("#{oid}", {{opacity: 0, duration: 0.45, ease: "power2.in"}}, {(scene_start + audio_duration - 0.45):.3f});',
            f'tl.set("#{oid}", {{opacity: 0}}, {(scene_start + audio_duration):.3f});',
        ]
    )
    return html, js


def build_true_story_card(s_id, scene_idx, card_start, hold_duration, subtitle_src=""):
    """Vraie pause noire après le hook, avant le démarrage de la scène 2."""
    if scene_idx != 1:
        return [], []
    oid = f"{s_id}_true_story"
    start = card_start
    dur = max(0.6, hold_duration - 0.05)
    folded = _fold_text(subtitle_src)
    if _has_keyword(folded, ["bar", "soiree", "soirée", "amis"]):
        sub = "un bar ordinaire · une sortie impossible"
    elif _has_keyword(folded, ["base", "dulce", "montauk", "souterrain"]):
        sub = "des lieux réels · des rumeurs documentées"
    else:
        sub = "lieux réels · témoins · archives"
    html = [
        (
            f'<div id="{oid}" class="truth-card clip" '
            f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
            f'data-track-index="{scene_idx * 20 + 14}">'
            f'<div class="truth-kicker">AVANT DE COMMENCER</div>'
            f'<div class="truth-title">HISTOIRE<br><span class="presque">(PRESQUE)</span> VRAIE</div>'
            f'<div class="truth-sub">{html_escape(sub)}</div>'
            f"</div>"
        )
    ]
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 0.985}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, duration: 0.22, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid} .truth-title", {{scale: 1.018, duration: {max(1.2, dur - 0.55):.3f}, ease: "sine.inOut"}}, {(start + 0.30):.3f});',
        f'tl.to("#{oid}", {{opacity: 0, scale: 1.01, duration: 0.24, ease: "power2.in"}}, {(start + dur - 0.24):.3f});',
        f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
    ]
    return html, js


def _derive_hook_title(subtitle_src):
    """Extrait 2-4 mots punch du hook narratif pour la headline d'intro."""
    txt = (subtitle_src or "").strip()
    if not txt:
        return "AFFAIRE", "NON RÉSOLUE"
    folded = _fold_text(txt)
    if _has_keyword(
        folded, ["disparu", "disparait", "disparition", "evapore", "evanoui"]
    ):
        return "DISPARU", "SANS TRACE"
    if _has_keyword(folded, ["meurtre", "tue", "assassin", "cadavre", "victime"]):
        return "AFFAIRE", "NON RÉSOLUE"
    if _has_keyword(folded, ["base", "souterrain", "secret", "classifie", "dossier"]):
        return "DOSSIER", "CLASSIFIÉ"
    if _has_keyword(
        folded, ["alien", "ovni", "extraterrestre", "rendlesham", "mothman"]
    ):
        return "RAPPORT", "INEXPLIQUÉ"
    if _has_keyword(folded, ["experience", "experiment", "controle", "mkultra"]):
        return "EXPÉRIENCE", "INTERDITE"
    return "AFFAIRE", "NON RÉSOLUE"


def build_hook_intro(s_id, scene_idx, scene_start, audio_duration, subtitle_src=""):
    """Intro sobre pour scène 1 drama intime : fade noir → titre épisode.

    Pas de flash rouge, pas de tag CASE/DOSSIER. Juste un fade élégant.
    """
    if scene_idx != 0 or not USE_HOOK_INTRO:
        return [], []

    oid = f"{s_id}_hook"
    title_id = f"{oid}_title"

    start = max(0.0, scene_start)
    title_in = start + 0.3
    hold_end = min(start + 3.5, start + max(2.5, audio_duration * 0.55))
    exit_dur = 0.7

    html = [
        (
            f'<div id="{oid}" class="hook-intro clip" '
            f'data-start="{start:.3f}" data-duration="{(hold_end - start + exit_dur):.3f}" '
            f'data-track-index="{scene_idx * 20 + 18}">'
            f'<div id="{title_id}" class="hook-title" '
            f'style="font-size:clamp(22px,5vw,38px);letter-spacing:0.15em;opacity:0;">'
            f"{html_escape((subtitle_src or '')[:60])}"
            f"</div>"
            f"</div>"
        )
    ]
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{title_id}", {{opacity: 0, y: 18, filter: "blur(6px)"}});',
        # Fade in doux de l'overlay sombre
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.5, ease: "power2.out"}}, {start:.3f});',
        # Titre apparaît avec un léger mouvement vers le haut
        f'tl.to("#{title_id}", {{opacity: 1, y: 0, filter: "blur(0px)", duration: 0.8, ease: "power3.out"}}, {title_in:.3f});',
        # Respiration subtile
        f'tl.to("#{title_id}", {{opacity: 0.85, duration: {max(1.2, hold_end - title_in - 0.6):.3f}, ease: "sine.inOut"}}, {(title_in + 0.7):.3f});',
        # Fade out doux
        f'tl.to("#{oid}", {{opacity: 0, duration: {exit_dur:.3f}, ease: "power2.in"}}, {hold_end:.3f});',
        f'tl.set("#{oid}", {{opacity: 0}}, {(hold_end + exit_dur):.3f});',
    ]
    return html, js


def build_outro_cta(
    s_id, scene_idx, scene_start, audio_duration, total_scenes, tail_seconds=0.0
):
    """CTA d'abonnement bref, affiché juste après la dernière phrase."""
    if scene_idx != total_scenes - 1 or not USE_OUTRO_CTA:
        return [], []

    oid = f"{s_id}_outro"
    voice_end = scene_start + audio_duration
    start = voice_end + 0.05
    # On finit le clip 0.05s avant la fin de la composition root (évite clip-out
    # exactement à la frontière qui peut faire disparaître le CTA prématurément).
    end = voice_end + tail_seconds - 0.05
    dur = max(0.0, end - start)
    if dur < 1.2:
        return [], []
    fade_out_dur = 0.50
    fade_out_at = end - fade_out_dur

    html = [
        (
            f'<div id="{oid}" class="outro-cta clip" '
            f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
            f'data-track-index="{scene_idx * 20 + 19}">'
            f'<div class="outro-cta-kicker">YŪREI</div>'
            f'<div class="outro-cta-title">ABONNE-TOI</div>'
            f'<div class="outro-cta-sub">POUR LA <span class="accent">SUITE</span></div>'
            f"</div>"
        )
    ]
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: 32}});',
        f'gsap.set("#{oid} .outro-cta-kicker", {{opacity: 0, y: 14}});',
        f'gsap.set("#{oid} .outro-cta-title", {{opacity: 0, scale: 0.88, filter: "blur(6px)"}});',
        f'gsap.set("#{oid} .outro-cta-sub", {{opacity: 0, y: 14}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, duration: 0.45, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .outro-cta-kicker", {{opacity: 1, y: 0, duration: 0.3, ease: "power3.out"}}, {(start + 0.05):.3f});',
        f'tl.to("#{oid} .outro-cta-title", {{opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.55, ease: "back.out(1.8)"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid} .outro-cta-sub", {{opacity: 1, y: 0, duration: 0.35, ease: "power3.out"}}, {(start + 0.30):.3f});',
        # Fade out doux dans les dernières 0.5s du tail
        f'tl.to("#{oid}", {{opacity: 0, duration: {fade_out_dur:.2f}, ease: "power2.in"}}, {fade_out_at:.3f});',
    ]
    return html, js


def build_scene_blocks(
    scene_idx,
    scene,
    audio_duration,
    images,
    scene_start,
    total_scenes,
    visual_bible=None,
    word_timings=None,
    source_map=None,
):
    """Génère HTML + tweens GSAP pour une scène.
    Retourne (html_parts, js_parts, n_shots, has_overlays, woosh_ts, glitch_ts, boom_ts)."""
    html_parts = []
    js_parts = []
    has_overlays = False
    s_id = f"s{scene_idx + 1}"

    # Listes pour accumuler les timings SFX
    woosh_t_scene = []
    glitch_t_scene = []
    boom_t_scene = []

    # Détection des transitions et révélations
    if scene_idx == 0:
        boom_t_scene.append(scene_start)
    elif scene_idx == 1 and not DISABLE_SCENE_TRANSITIONS:
        glitch_t_scene.append(scene_start)
    elif scene_idx == 6:
        boom_t_scene.append(scene_start)
    elif scene_idx == 8:
        boom_t_scene.append(scene_start)
    elif scene_idx == 9 and not DISABLE_SCENE_TRANSITIONS:
        glitch_t_scene.append(scene_start)

    subtitle_src = (
        scene.get("subtitle")
        or scene.get("sous_titre")
        or scene.get("audio_tts")
        or scene.get("voix_off_tts")
        or scene.get("voix_off", "")
    )

    shots_list = []
    if USE_IMAGES and images:
        max_shots = int(os.getenv("MAX_SHOTS_PER_SCENE", "4"))
        shots_list = images[:max_shots]

    director_result = None
    if USE_DIRECTOR_AGENT:
        director_result = generate_master_director_agent(
            s_id,
            scene_idx,
            scene_start,
            audio_duration,
            subtitle_src,
            shots_list,
            visual_bible,
        )

    if director_result:
        d_html, d_js, strategy = director_result
        html_parts.extend(d_html)
        js_parts.extend(d_js)
        shots = len(shots_list)
    else:
        if not shots_list:
            bg_html, bg_js = build_procedural_bg(scene_idx, scene_start, audio_duration)
            html_parts.append(bg_html)
            js_parts.extend(bg_js)

        if shots_list:
            n = len(shots_list)
            slice_dur = audio_duration / n
            for j in range(n):
                img = shots_list[j]
                start = scene_start + j * slice_dur
                dur = slice_dur + (1.2 if j < n - 1 else 0)
                html, js = build_image_block(
                    s_id,
                    j,
                    img,
                    scene_idx,
                    start,
                    dur,
                    is_last=(j == n - 1),
                    in_transition_from_prev=(j > 0),
                    total_scenes=total_scenes,
                    source_type=(source_map or {}).get(str(img.resolve()), ""),
                )
                html_parts.append(html)
                js_parts.extend(js)
            shots = n
        else:
            shots = 0

        fx_html, fx_js = build_scene_director_fx(
            s_id, scene_idx, scene_start, audio_duration, subtitle_src
        )
        html_parts.extend(fx_html)
        js_parts.extend(fx_js)

        if USE_SEMANTIC_OVERLAYS:
            ov_html, ov_js, ov_types = build_overlay_blocks(
                s_id,
                scene_idx,
                scene_start,
                audio_duration,
                subtitle_src,
                visual_bible=visual_bible,
            )
            if ov_types:
                print(f"   ✨ Overlays détectés: {', '.join(ov_types)}")
                has_overlays = True
                html_parts.extend(ov_html)
                js_parts.extend(ov_js)

        lottie_html, lottie_js = build_curated_lottie_accents(
            scene_idx,
            scene_start,
            audio_duration,
            subtitle_src,
            word_timings,
        )
        if lottie_html:
            has_overlays = True
            html_parts.extend(lottie_html)
            js_parts.extend(lottie_js)

    is_last_scene = scene_idx == total_scenes - 1
    subtitle_budget = audio_duration

    chunks = split_subtitle(
        subtitle_src,
        subtitle_budget,
        max_chunks=int(os.getenv("MAX_SUB_CHUNKS", "4")),
        max_words=int(os.getenv("MAX_WORDS_PER_CHUNK", "6")),
    )

    if word_timings:
        new_chunks = []
        cursor = 0
        for c in chunks:
            n_w = max(1, sum(1 for w in c["text"].split() if re.sub(r"[^\w]", "", w)))
            slice_ = word_timings[cursor : cursor + n_w]
            if slice_:
                c_start = slice_[0]["start"]
                c_end = slice_[-1]["end"]
                c_dur = max(0.8, (c_end - c_start) + 0.30)
                new_chunks.append(
                    {
                        "text": c["text"],
                        "start": c_start,
                        "duration": c_dur,
                        "_word_offset": cursor,
                        "_n_words": n_w,
                    }
                )
            else:
                new_chunks.append({**c, "_word_offset": cursor, "_n_words": n_w})
            cursor += n_w
        chunks = new_chunks

    for k in range(len(chunks)):
        c = chunks[k]
        if k < len(chunks) - 1:
            next_start = chunks[k + 1]["start"]
            max_dur = next_start - c["start"]
        else:
            max_dur = subtitle_budget - c["start"]
        chunks[k]["duration"] = max(0.2, min(c["duration"], max_dur - 0.03))

    for k, c in enumerate(chunks):
        sub_id = f"{s_id}_sub{k + 1}"
        start = scene_start + c["start"]
        dur = max(0.8, c["duration"])
        emph_html = emphasize_words(c["text"])
        chunk_word_prefix = sub_id if word_timings else None
        word_wrapped, _n_rendered = _wrap_words_for_reveal(
            emph_html, id_prefix=chunk_word_prefix
        )
        stripped = c["text"].strip()
        is_quote = bool(
            re.match(r'^["\u00ab\u201c\u201d]', stripped)
            and re.search(r'["\u00bb\u201c\u201d][?!.\u2026\s]*$', stripped)
        )
        extra_class = " quote" if is_quote else ""
        html_parts.append(
            f'<div id="{sub_id}" class="subtitle{extra_class} clip" '
            f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
            f'data-track-index="{scene_idx * 20 + 50 + k}" style="z-index: 50;">{word_wrapped}</div>'
        )
        js_parts.append(f'gsap.set("#{sub_id}", {{opacity: 0, y: 20}});')
        js_parts.append(
            f'tl.to("#{sub_id}", {{opacity: 1, y: 0, duration: 0.4, ease: "power2.out"}}, {start:.3f});'
        )
        js_parts.append(
            f'gsap.set("#{sub_id} .word", {{opacity: 0, y: 12, scale: 0.55}});'
        )

        used_whisper = False
        if word_timings:
            offset = c.get("_word_offset", 0)
            n_w = c.get("_n_words", 0)
            slice_ = word_timings[offset : offset + n_w]
            if len(slice_) >= 1:
                used_whisper = True
                for i, w in enumerate(slice_):
                    abs_t = scene_start + max(0.0, w["start"] - 0.06)
                    js_parts.append(
                        f'tl.to("#{sub_id}_w{i + 1}", '
                        f"{{opacity: 1, y: 0, scale: 1, duration: 0.22, "
                        f'ease: "back.out(1.6)", overwrite: "auto"}}, '
                        f"{abs_t:.3f});"
                    )

        if not used_whisper:
            n_words = max(1, len(c["text"].split()))
            word_stagger = max(0.07, min(0.22, (dur * 0.6) / n_words))
            word_duration = max(0.25, min(0.55, word_stagger * 1.6))
            js_parts.append(
                f'tl.to("#{sub_id} .word", {{opacity: 1, y: 0, scale: 1, duration: {word_duration:.3f}, '
                f'stagger: {word_stagger:.3f}, ease: "back.out(1.8)"}}, {(start + 0.10):.3f});'
            )

        # Check for red words in this chunk to schedule a whoosh sound.
        # Gated by USE_WHOOSH_SFX (default off) — the trigger fires on every
        # dramatic word, which feels like one whoosh per scene and gets old fast.
        if USE_WHOOSH_SFX:
            red_indices = red_word_indices(c["text"])
            if red_indices:
                first_red_idx = red_indices[0]
                if word_timings and used_whisper:
                    offset = c.get("_word_offset", 0)
                    n_w = c.get("_n_words", 0)
                    slice_ = word_timings[offset : offset + n_w]
                    if len(slice_) > first_red_idx:
                        rel_t = slice_[first_red_idx]["start"]
                    else:
                        rel_t = c["start"]
                else:
                    n_words = max(1, len(c["text"].split()))
                    word_stagger = max(0.07, min(0.22, (dur * 0.6) / n_words))
                    rel_t = c["start"] + 0.10 + first_red_idx * word_stagger
                woosh_t_scene.append(scene_start + rel_t)

        exit_at = start + dur - 0.35
        js_parts.append(
            f'tl.to("#{sub_id}", {{opacity: 0, y: -10, duration: 0.35, ease: "power2.in"}}, {exit_at:.3f});'
        )
        js_parts.append(f'tl.set("#{sub_id}", {{opacity: 0}}, {(start + dur):.3f});')

    html_parts.append(
        f'<audio id="{s_id}_vo" class="clip" src="assets/{s_id}_vo.wav" '
        f'data-start="{scene_start:.3f}" data-duration="{audio_duration:.3f}" '
        f'data-track-index="{1000 + scene_idx}" data-volume="0.0"></audio>'
    )

    return (
        html_parts,
        js_parts,
        shots,
        has_overlays,
        woosh_t_scene,
        glitch_t_scene,
        boom_t_scene,
    )


def _wrap_words_for_reveal(html, id_prefix=None):
    """Wrap chaque VRAI mot dans <span class='word'> (avec un id séquentiel
    optionnel pour le sync Whisper). Les tokens décoratifs ("...", "—", etc.)
    sont gardés en texte brut, sans span ni id : ils ne consomment pas d'index
    de mot, ce qui garantit l'alignement avec Whisper (qui ne les voit pas non plus).
    Retourne (html_str, n_real_words)."""
    parts = re.split(r'(<span class="emph(?: chromatic)?">[^<]*</span>)', html)
    out = []
    word_idx = [0]

    def make_word(w):
        # Si le token n'a aucun caractère alphanumérique (ex: "...", "—"), on
        # le laisse comme texte brut sans id, pour ne pas casser l'alignement.
        normalized = re.sub(r"[^\w]", "", w)
        if not normalized:
            return w
        word_idx[0] += 1
        if id_prefix:
            return f'<span class="word" id="{id_prefix}_w{word_idx[0]}">{w}</span>'
        return f'<span class="word">{w}</span>'

    for part in parts:
        if not part:
            continue
        m = re.match(r'<span class="(emph(?: chromatic)?)">([^<]*)</span>$', part)
        if m:
            classes = m.group(1)
            inner = m.group(2)
            words = inner.split()
            wrapped = " ".join(make_word(w) for w in words)
            out.append(f'<span class="{classes}">{wrapped}</span>')
        else:
            words = part.split()
            if words:
                out.append(" ".join(make_word(w) for w in words))
    rendered = " ".join(out)
    rendered = re.sub(
        r"(</span>)(</span>)?\s*([,.:;!?…]+)",
        lambda match: (
            f"{match.group(3)}{match.group(1)}{match.group(2) or ''}"
        ),
        rendered,
    )
    rendered = re.sub(r"\s+([,.…])", r"\1", rendered)
    return rendered, word_idx[0]


def _normalize_word(w):
    """Normalise un mot pour le matching : minuscules, sans accents, sans ponctuation."""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", w.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c) and c.isalnum())


def _align_by_text_match(script_words, w_words):
    """Aligne script_words ↔ w_words [(text, start, end), ...] via SequenceMatcher.
    Retourne une liste de {text, start, end} de même taille que script_words,
    avec interpolation linéaire pour les mots non matchés."""
    from difflib import SequenceMatcher

    norm_script = [_normalize_word(w) for w in script_words]
    norm_whisper = [_normalize_word(w[0]) for w in w_words]
    sm = SequenceMatcher(a=norm_script, b=norm_whisper, autojunk=False)

    # Construit un mapping script_idx → (start, end) pour les correspondances directes.
    direct = {}  # script_idx -> (start, end)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                _, t_start, t_end = w_words[j1 + k]
                direct[i1 + k] = (t_start, t_end)
        elif tag == "replace":
            # Match approximatif : on mappe proportionnellement le bloc
            n_s_block = i2 - i1
            n_w_block = j2 - j1
            if n_w_block == 0:
                continue
            for k in range(n_s_block):
                w_idx = j1 + min(
                    n_w_block - 1, round(k * (n_w_block - 1) / max(1, n_s_block - 1))
                )
                _, t_start, t_end = w_words[w_idx]
                direct[i1 + k] = (t_start, t_end)
        # 'delete' (script a des mots que Whisper n'a pas) : on remplit par interpolation après

    # Pour tous les mots du script non matchés, interpoler linéairement entre voisins matchés.
    last_t = w_words[0][1] if w_words else 0.0
    final_t = w_words[-1][2] if w_words else 0.0

    result = []
    for i in range(len(script_words)):
        if i in direct:
            t_start, t_end = direct[i]
        else:
            # Cherche le prochain mot matché vers la droite
            next_i = i + 1
            while next_i < len(script_words) and next_i not in direct:
                next_i += 1
            # Cherche le précédent mot matché vers la gauche
            prev_i = i - 1
            while prev_i >= 0 and prev_i not in direct:
                prev_i -= 1

            prev_t = direct[prev_i][1] if prev_i >= 0 else last_t
            next_t = direct[next_i][0] if next_i < len(script_words) else final_t + 0.5

            n_gap = (next_i - prev_i) if prev_i >= 0 else (next_i + 1)
            local_k = (i - prev_i) if prev_i >= 0 else (i + 1)
            t_start = prev_t + (next_t - prev_t) * (local_k / max(1, n_gap))
            t_end = t_start + 0.30  # durée par défaut interpolée
        result.append(
            {"text": script_words[i], "start": float(t_start), "end": float(t_end)}
        )
        last_t = t_end

    return result


def align_scene_words(audio_path, full_text):
    """Aligne les mots du script avec l'audio via faster-whisper + SequenceMatcher.
    Cache JSON dans `<audio_path>.words.json`.
    Retourne une liste de dicts {text, start, end} en secondes relatives au début de l'audio,
    ou None en cas d'échec.
    """
    if not USE_WHISPER_SYNC:
        return None
    audio_path = Path(audio_path)
    cache = audio_path.with_suffix(audio_path.suffix + ".words.json")
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("   ℹ️  faster-whisper indisponible — sync mot-par-mot désactivée.")
        return None

    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        device = "cpu"
        compute_type = "int8"
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
        except ImportError:
            pass

        print(
            f"   🤖 Chargement de Whisper (small, {compute_type} sur {device.upper()}) — une fois pour toutes les scènes..."
        )
        try:
            _WHISPER_MODEL = WhisperModel(
                "small", device=device, compute_type=compute_type
            )
        except Exception as e:
            print(f"   ⚠️  Whisper init échec : {e}")
            return None

    text = re.sub(r"\[STYLE LOCK[^\]]*\]", "", full_text, flags=re.IGNORECASE)
    text = re.sub(r"\[.*?\]", "", text).strip()
    script_words = [w for w in text.split() if re.sub(r"[^\w]", "", w)]
    if not script_words:
        return None

    try:
        segments, _ = _WHISPER_MODEL.transcribe(
            str(audio_path), word_timestamps=True, language="fr"
        )
        w_words = [
            (w.word.strip(), float(w.start), float(w.end))
            for s in segments
            for w in (s.words or [])
            if w.word and w.word.strip()
        ]
    except Exception as e:
        print(f"   ⚠️  Whisper transcribe échec : {e}")
        return None

    if not w_words:
        return None

    # Alignement textuel (SequenceMatcher) au lieu d'index proportionnel.
    # Beaucoup plus précis quand Whisper transcrit avec un nombre de mots différent.
    result = _align_by_text_match(script_words, w_words)

    try:
        cache.write_text(json.dumps(result), encoding="utf-8")
    except Exception:
        pass
    return result


def _dust_motes_html(count):
    """Génère N motes (divs) avec positions semi-aléatoires déterministes."""
    parts = []
    for i in range(count):
        # Pseudo-random déterministe basé sur l'index
        x = (i * 47) % 100
        y = (i * 71) % 100
        size = 2 + (i * 13) % 4
        glow = " glow" if i % 5 == 0 else ""
        parts.append(
            f'<div class="dust-mote{glow}" id="mote{i}" '
            f'style="left:{x}%;top:{y}%;width:{size}px;height:{size}px;"></div>'
        )
    return "\n        ".join(parts)


def _dust_motes_js(count, total_duration):
    """Anime les motes via GSAP timeline (déterministe, frame-perfect)."""
    js_lines = []
    for i in range(count):
        # Drift sur toute la durée — cycle lent
        drift_x = -40 + ((i * 17) % 80)  # -40 à +40 px
        drift_y = -60 + ((i * 23) % 120)  # -60 à +60 px
        cycle_dur = 6 + (i % 5) * 2  # 6-14s par cycle
        delay = (i * 0.3) % cycle_dur
        opacity_max = 0.35 + (i % 7) * 0.05
        js_lines.append(
            f'tl.fromTo("#mote{i}", '
            f"{{x: 0, y: 0, opacity: 0}}, "
            f"{{x: {drift_x}, y: {drift_y}, opacity: {opacity_max:.2f}, "
            f'duration: {cycle_dur}, ease: "sine.inOut", '
            f"yoyo: true, repeat: Math.floor({total_duration} / {cycle_dur})}}, {delay:.2f});"
        )
    return "\n      ".join(js_lines)


def build_flash_transitions(scenes_meta):
    """Transition inter-scènes : WHIP BLUR cinéma.

    Un voile transparent avec backdrop-filter:blur(20px) traverse l'écran
    horizontalement à chaque cut. Direction alternée (gauche→droite puis
    droite→gauche) selon la parité de la scène. Le cut entre images se fait
    pile quand le voile est au centre, donc le motion blur masque visuellement
    le cut. L'œil suit le mouvement, ne perçoit pas le changement d'image.
    """
    if DISABLE_SCENE_TRANSITIONS:
        return [], []
    html_parts = []
    js_parts = []

    for i, sm in enumerate(scenes_meta[1:], start=1):
        # On centre le voile sur scene_start exact : tween x va de from_x à to_x
        # sur 0.30s, le centre (50% du tween) est à start_t + 0.15.
        # → start_t = sm["start"] - 0.15 pour que le centre tombe sur sm["start"].
        start_t = sm["start"] - 0.15
        if start_t < 0:
            continue
        tid = f"trans{i}"

        direction = 1 if i % 2 == 1 else -1  # alterne droite/gauche
        from_x = -110 * direction  # %vw
        to_x = 110 * direction

        html_parts.append(
            f'<div id="{tid}" class="trans-whip clip" '
            f'data-start="{start_t:.3f}" data-duration="0.42" '
            f'data-track-index="{900 + i}"></div>'
        )
        # Initial : hors écran, opacity 0
        js_parts.append(f'gsap.set("#{tid}", {{x: "{from_x}vw", opacity: 0}});')
        # Apparition rapide
        js_parts.append(
            f'tl.to("#{tid}", {{opacity: 1, duration: 0.04, ease: "none"}}, {start_t:.3f});'
        )
        # Slide à travers l'écran (0.30s linéaire-ease)
        js_parts.append(
            f'tl.to("#{tid}", {{x: "{to_x}vw", duration: 0.30, ease: "power2.inOut"}}, {start_t:.3f});'
        )
        # Disparition à la sortie
        js_parts.append(
            f'tl.to("#{tid}", {{opacity: 0, duration: 0.06, ease: "none"}}, {(start_t + 0.30):.3f});'
        )
        # Hard kill safety
        js_parts.append(f'tl.set("#{tid}", {{opacity: 0}}, {(start_t + 0.42):.3f});')

    return html_parts, js_parts


def _persistent_case_tag_html(projet_name):
    """Tag CASE permanent en coin haut-droite, identifiant unique du projet."""
    if not USE_PERSISTENT_CASE_TAG:
        return ""
    # Identifiant stable basé sur le projet (hash() est randomisé par processus)
    h = int(hashlib.md5(projet_name.encode("utf-8")).hexdigest(), 16) & 0xFFFFFF
    case_id = f"{h >> 12:03X}-{h & 0xFFF:03X}"
    year = "26"  # année stylisée
    return (
        f'<div class="persistent-case-tag">'
        f'<span class="dot"></span>'
        f'DOSSIER<span class="sep">·</span>{case_id}<span class="sep">·</span>{year}'
        f"</div>"
    )


def build_html(projet_name, scenes_meta, total_duration):
    body_blocks = []
    js_blocks = []
    for sm in scenes_meta:
        body_blocks.extend(sm["html"])
        js_blocks.extend(sm["js"])

    # Flash transitions
    flash_html, flash_js = build_flash_transitions(scenes_meta)
    body_blocks.extend(flash_html)
    js_blocks.extend(flash_js)

    body_html = "\n      ".join(body_blocks)
    js_code = "\n      ".join(js_blocks)
    image_preload_hrefs = sorted(set(re.findall(r'<img[^>]+src="([^"]+)"', body_html)))
    image_preload_links = "\n    ".join(
        f'<link rel="preload" as="image" href="{href}" fetchpriority="high">'
        for href in image_preload_hrefs
    )

    # Lottie runtime <script type="module" src=...> — empty when Lottie is
    # disabled or the manifest has no assets, so the runtime isn't loaded.
    lottie_script_tag = lottie_head_html() if USE_LOTTIE_OVERLAYS else ""

    # Couches cinéma globales (opt-in via flags ENV)
    film_grain_html = (
        (
            f'<div id="film-grain" class="film-grain clip" data-start="0" '
            f'data-duration="{total_duration:.3f}" data-track-index="495"></div>'
        )
        if USE_FILM_GRAIN
        else ""
    )
    letterbox_html = (
        (
            f'<div id="letterbox" class="letterbox clip" data-start="0" '
            f'data-duration="{total_duration:.3f}" data-track-index="496"></div>'
        )
        if USE_LETTERBOX
        else ""
    )
    persistent_tag_html = _persistent_case_tag_html(projet_name)
    if persistent_tag_html:
        persistent_tag_html = (
            f'<div class="persistent-case-tag-wrap clip" data-start="0" '
            f'data-duration="{total_duration:.3f}" data-track-index="497" '
            f'style="position:absolute;inset:0;pointer-events:none;">'
            f"{persistent_tag_html}"
            f"</div>"
        )
    brand_logo_html = ""
    if USE_BRAND_LOGO:
        brand_logo_html = (
            f'<div id="brand-logo-wrap" class="brand-logo-wrap clip" '
            f'data-start="0" data-duration="{total_duration:.3f}" '
            f'data-track-index="498">'
            f'<img src="assets/yurei_logo.png" alt="" />'
            f"</div>"
        )
    scroll_hook_html = ""
    if USE_SCROLL_HOOK:
        scroll_hook_html = (
            f'<div id="scroll-hook" class="scroll-hook clip" '
            f'data-start="0" data-duration="3.300" data-track-index="499">'
            f"{html_escape(SCROLL_HOOK_TEXT)}"
            f"</div>"
        )

    # Vignette pulse (respiration)
    vignette_pulse_js = ""
    if USE_BREATHING_VIGNETTE:
        # Cycle de 8s : opacity 0.85 ↔ 1.05 + scale 1.00 ↔ 1.04
        n_cycles = max(1, int(total_duration / 8.0))
        vignette_pulse_js = (
            f'tl.fromTo("#vignette", '
            f"{{opacity: 0.85}}, "
            f'{{opacity: 1.05, duration: 8, ease: "sine.inOut", '
            f"yoyo: true, repeat: {n_cycles * 2}}}, 0);"
        )

    return f"""<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={WIDTH}, height={HEIGHT}" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Anton&family=Bebas+Neue&family=Inter:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&family=Crimson+Pro:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
    {image_preload_links}
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    {lottie_script_tag}
    <style>
      /* ── Design system : éditorial / docu épuré ─────────────── */
      :root {{
        --bg:        #08090f;
        --bg-deep:   #04050a;
        --surface:   rgba(255, 255, 255, 0.04);
        --border:    rgba(200, 220, 255, 0.10);
        --border-on: rgba(255, 56, 56, 0.50);
        --text:      #f0eee8;
        --muted:     #8899bb;
        --muted-2:   #445566;
        --accent:    #ff3838;
        --accent-d:  rgba(255, 56, 56, 0.55);

        --font-display: "Anton", "Inter", -apple-system, sans-serif;
        --font-display2: "Bebas Neue", "Inter", sans-serif;
        --font-sans: "Inter", -apple-system, "Helvetica Neue", Arial, sans-serif;
        --font-mono: "JetBrains Mono", "Courier New", monospace;
        --font-serif: "Crimson Pro", "Times New Roman", Georgia, serif;
      }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{
        margin: 0; width: {WIDTH}px; height: {HEIGHT}px;
        overflow: hidden; background: var(--bg-deep);
        color: var(--text);
        font-family: var(--font-sans);
        font-feature-settings: "ss01", "cv11";
        -webkit-font-smoothing: antialiased;
      }}
      #root {{
        position: relative; width: 100%; height: 100%;
        perspective: 1500px;
        background: var(--bg-deep);
      }}

      /* ── Images ─────────────────────────────────────────────── */
      .bg {{
        position: absolute; inset: 0; width: 100%; height: 100%;
        object-fit: cover; z-index: 1; opacity: 0;
        will-change: transform, opacity;
        transform-style: preserve-3d;
        transform-origin: 50% 50%;
        backface-visibility: hidden;
      }}
      .motion-atmosphere {{
        position: absolute;
        inset: -8%;
        pointer-events: none;
        background:
          radial-gradient(ellipse 55% 25% at 20% 38%, rgba(205,220,228,0.30), transparent 72%),
          radial-gradient(ellipse 65% 24% at 78% 66%, rgba(112,132,145,0.24), transparent 74%),
          linear-gradient(112deg, transparent 30%, rgba(255,255,255,0.055) 49%, transparent 66%);
        filter: blur(28px);
        mix-blend-mode: screen;
        will-change: transform, opacity;
      }}
      .brand-logo-wrap {{
        position: absolute;
        top: 48px;
        right: 42px;
        width: 156px;
        height: 156px;
        z-index: 92;
        opacity: 0.54;
        pointer-events: none;
        filter: drop-shadow(0 4px 14px rgba(0,0,0,0.85));
      }}
      .brand-logo-wrap img {{
        width: 100%;
        height: 100%;
        object-fit: contain;
      }}
      .scroll-hook {{
        position: absolute;
        top: 112px;
        left: 72px;
        right: 220px;
        z-index: 91;
        color: #fff;
        font-family: "Oswald", var(--font-display2);
        font-size: 45px;
        font-weight: 800;
        line-height: 1.06;
        letter-spacing: 0;
        text-transform: uppercase;
        text-align: left;
        text-shadow:
          0 3px 16px rgba(0,0,0,1),
          0 0 8px rgba(0,0,0,0.96);
        -webkit-text-stroke: 1px rgba(0,0,0,0.72);
      }}

      /* ── Backgrounds procéduraux (image-free) ───────────────── */
      .pbg {{
        position: absolute; inset: 0; opacity: 0;
        will-change: opacity;
      }}
      .pbg-minimal {{ background: var(--bg-deep); }}
      .pbg-dotgrid {{
        background-color: var(--bg-deep);
        background-image: radial-gradient(rgba(255,255,255,0.06) 1.5px, transparent 1.5px);
        background-size: 40px 40px;
      }}
      .pbg-mesh {{
        background:
          radial-gradient(ellipse 70% 50% at 20% 25%, rgba(255,56,56,0.10) 0%, transparent 60%),
          radial-gradient(ellipse 60% 40% at 80% 75%, rgba(70,80,120,0.18) 0%, transparent 55%),
          radial-gradient(ellipse 100% 100% at 50% 50%, transparent 40%, rgba(0,0,0,0.6) 100%),
          var(--bg-deep);
        background-size: 200% 200%;
      }}
      .pbg-lines {{
        background-color: var(--bg-deep);
        background-image: repeating-linear-gradient(
          0deg, transparent 0px, transparent 39px,
          rgba(255,255,255,0.04) 39px, rgba(255,255,255,0.04) 40px
        );
      }}
      .pbg-topo {{
        background: var(--bg-deep);
        background-image:
          radial-gradient(circle at 30% 40%, rgba(255,56,56,0.07) 0%, transparent 28%),
          radial-gradient(circle at 70% 60%, rgba(255,255,255,0.05) 0%, transparent 35%),
          repeating-radial-gradient(circle at 50% 50%,
            transparent 0px, transparent 38px,
            rgba(255,255,255,0.025) 38px, rgba(255,255,255,0.025) 39px);
      }}
      .pbg-scanline {{
        background: var(--bg-deep);
        overflow: hidden;
      }}
      .pbg-scan {{
        position: absolute; left: 0; right: 0;
        height: 280px;
        background: linear-gradient(180deg,
          transparent 0%,
          rgba(255,255,255,0.045) 40%,
          rgba(255,56,56,0.08) 50%,
          rgba(255,255,255,0.045) 60%,
          transparent 100%);
        filter: blur(2px);
      }}

      /* Vignette subtile globale (douce, pas oppressive) */
      .vignette {{
        position: absolute; inset: 0; z-index: 5; pointer-events: none;
        background: radial-gradient(ellipse 100% 100% at center,
          transparent 34%, rgba(0,0,0,0.82) 100%);
        will-change: opacity, transform;
      }}

      /* ── Film grain animé (look 35mm) ───────────────────────── */
      .film-grain {{
        position: absolute; inset: -2%; z-index: 6;
        pointer-events: none;
        background-image:
          radial-gradient(circle at 17% 23%, rgba(255,255,255,0.08) 0.5px, transparent 1.5px),
          radial-gradient(circle at 71% 47%, rgba(255,255,255,0.06) 0.5px, transparent 1.5px),
          radial-gradient(circle at 43% 81%, rgba(255,255,255,0.07) 0.5px, transparent 1.5px),
          radial-gradient(circle at 88% 12%, rgba(255,255,255,0.05) 0.5px, transparent 1.5px),
          radial-gradient(circle at 6% 64%, rgba(255,255,255,0.06) 0.5px, transparent 1.5px);
        background-size: 180px 180px, 220px 220px, 150px 150px, 200px 200px, 170px 170px;
        background-blend-mode: screen;
        mix-blend-mode: overlay;
        opacity: 0.18;
        animation: film-grain-shift 0.16s steps(3) infinite;
      }}
      @keyframes film-grain-shift {{
        0%   {{ background-position:   0px   0px,   0px   0px,   0px   0px,   0px   0px,   0px   0px; }}
        33%  {{ background-position: -30px  17px,  22px -19px, -15px  31px,  28px -11px, -18px  24px; }}
        66%  {{ background-position:  19px -28px, -33px  14px,  26px -22px, -14px  29px,  21px -16px; }}
        100% {{ background-position:   0px   0px,   0px   0px,   0px   0px,   0px   0px,   0px   0px; }}
      }}

      /* ── Letterbox cinéma (barres haut/bas légères) ─────────── */
      .letterbox {{
        position: absolute; inset: 0; z-index: 7;
        pointer-events: none;
      }}
      .letterbox::before, .letterbox::after {{
        content: ""; position: absolute; left: 0; right: 0;
        height: 70px;
        background: linear-gradient(180deg, rgba(0,0,0,0.92) 60%, transparent 100%);
      }}
      .letterbox::before {{ top: 0; }}
      .letterbox::after {{
        bottom: 0;
        background: linear-gradient(0deg, rgba(0,0,0,0.92) 60%, transparent 100%);
      }}

      /* ── Tag CASE permanent en coin haut-droite ─────────────── */
      .persistent-case-tag {{
        position: absolute; top: 36px; right: 36px; z-index: 35;
        pointer-events: none;
        font-family: var(--font-mono);
        font-size: 14px; letter-spacing: 2px;
        color: rgba(255,255,255,0.72);
        text-transform: uppercase;
        padding: 6px 10px;
        border: 1px solid rgba(255,56,56,0.55);
        background: rgba(0,0,0,0.45);
        backdrop-filter: blur(3px);
        opacity: 0.85;
      }}
      .persistent-case-tag .dot {{
        display: inline-block;
        width: 7px; height: 7px;
        background: var(--accent);
        border-radius: 50%;
        margin-right: 7px; vertical-align: middle;
        box-shadow: 0 0 8px rgba(255,56,56,0.9);
        animation: case-blink 1.4s steps(1, end) infinite;
      }}
      @keyframes case-blink {{
        0%, 65% {{ opacity: 1; }}
        66%, 100% {{ opacity: 0.15; }}
      }}
      .persistent-case-tag .sep {{
        color: rgba(255,56,56,0.7);
        margin: 0 6px;
      }}

      /* ── Chromatic aberration sur emph (statique, look glitch permanent) ── */
      .subtitle .emph.chromatic {{
        text-shadow:
          /* Glow & lisibilité (gardé) */
          0 0 8px rgba(0,0,0,1),
          0 0 16px rgba(0,0,0,0.95),
          0 4px 20px rgba(0,0,0,0.95),
          0 0 24px rgba(255,56,56,0.55),
          0 0 48px rgba(255,56,56,0.35),
          /* Chromatic split RGB */
          -3px 0 0 rgba(255, 30, 30, 0.85),
          3px 0 0 rgba(0, 200, 255, 0.55),
          -2px 1px 0 rgba(255, 60, 60, 0.45),
          2px -1px 0 rgba(0, 220, 255, 0.40);
      }}

      /* ── Fog : pseudo-shader CSS atmosphérique ──────────────── */
      .fog {{
        position: absolute; inset: -10%; z-index: 4;
        pointer-events: none;
        background:
          radial-gradient(ellipse 60% 40% at 25% 30%,
            rgba(255, 56, 56, 0.10) 0%, transparent 55%),
          radial-gradient(ellipse 50% 60% at 70% 60%,
            rgba(100, 110, 140, 0.18) 0%, transparent 60%),
          radial-gradient(ellipse 70% 50% at 50% 90%,
            rgba(80, 80, 100, 0.12) 0%, transparent 65%);
        filter: blur(40px);
        opacity: 0.38;
        will-change: transform, opacity;
        mix-blend-mode: screen;
      }}

      /* Flash blanc transitions (très subtil) */
      .flash {{
        position: absolute; inset: 0; z-index: 800; pointer-events: none;
        background: #fff; opacity: 0;
      }}

      /* ── 5 transitions inter-scènes alternées ──────────────── */
      .trans-flash-white {{
        position: absolute; inset: 0; z-index: 800; pointer-events: none;
        background: #fff; opacity: 0;
      }}
      .trans-rgb-glitch {{
        position: absolute; inset: 0; z-index: 800; pointer-events: none;
        opacity: 0;
      }}
      .trans-rgb-glitch .rgb-r, .trans-rgb-glitch .rgb-c {{
        position: absolute; inset: 0; pointer-events: none;
        mix-blend-mode: screen;
      }}
      .trans-rgb-glitch .rgb-r {{ background: rgba(255,40,40,0.55); }}
      .trans-rgb-glitch .rgb-c {{ background: rgba(0,200,255,0.45); }}
      .trans-zoom-blur {{
        position: absolute; inset: 0; z-index: 800; pointer-events: none;
        background: radial-gradient(circle at center,
          rgba(255,255,255,0.92) 0%,
          rgba(255,255,255,0.65) 20%,
          rgba(255,255,255,0.0) 60%);
        opacity: 0; transform-origin: center;
        filter: blur(8px);
      }}
      .trans-hard-cut {{
        position: absolute; inset: 0; z-index: 800; pointer-events: none;
        background: #000; opacity: 0;
      }}
      .trans-red-fade {{
        position: absolute; inset: 0; z-index: 800; pointer-events: none;
        background: radial-gradient(ellipse 80% 100% at center,
          rgba(180,30,30,0.85) 0%,
          rgba(120,10,10,0.55) 50%,
          rgba(40,0,0,0.45) 100%);
        opacity: 0;
        mix-blend-mode: multiply;
      }}

      /* ── WHIP BLUR cinéma : voile flou qui traverse l'écran ─────
         backdrop-filter rend flou le contenu derrière. Combiné avec
         translateX, ça donne l'effet "panoramique flou" qui masque le cut
         entre 2 images. Très utilisé en montage pro (Premiere/DaVinci). */
      .trans-whip {{
        position: absolute;
        top: 0; bottom: 0; left: 0;
        width: 100vw;
        z-index: 800;
        pointer-events: none;
        opacity: 0;
        backdrop-filter: blur(22px) brightness(0.92);
        -webkit-backdrop-filter: blur(22px) brightness(0.92);
        background: linear-gradient(90deg,
          rgba(255,255,255,0.02) 0%,
          rgba(255,255,255,0.18) 35%,
          rgba(255,255,255,0.28) 50%,
          rgba(255,255,255,0.18) 65%,
          rgba(255,255,255,0.02) 100%);
        will-change: transform, opacity;
      }}

      /* Scanning Laser Line */
      @keyframes scanning-laser {{
        0% {{ transform: translateY(-100%); opacity: 0; }}
        10% {{ opacity: 1; }}
        90% {{ opacity: 1; }}
        100% {{ transform: translateY(100%); opacity: 0; }}
      }}
      .scanline-laser {{
        position: absolute; top: 0; left: 0; width: 100%; height: 3px;
        background: var(--accent);
        box-shadow: 0 0 15px var(--accent), 0 0 30px var(--accent);
        z-index: 60;
        pointer-events: none;
        animation: scanning-laser 6s linear infinite;
        opacity: 0;
      }}

      /* Glitch Layer */
      .glitch-layer {{
        position: absolute; inset: 0; z-index: 70; pointer-events: none;
        background: rgba(255, 56, 56, 0.15);
        backdrop-filter: invert(1) hue-rotate(90deg);
        -webkit-backdrop-filter: invert(1) hue-rotate(90deg);
        mix-blend-mode: exclusion;
        opacity: 0;
      }}

      /* ── CLASSIFIED tag : minimal, plus éditorial ───────────── */
      .classified-tag {{
        position: absolute; top: 110px; left: 60px;
        z-index: 30; opacity: 0;
        display: flex; align-items: center; gap: 12px;
        font-family: var(--font-display2);  /* Bebas Neue */
        font-size: 26px; font-weight: 400; letter-spacing: 8px;
        color: var(--accent);
        text-transform: uppercase;
      }}
      .classified-tag .ico {{
        width: 22px; height: 22px;
        display: inline-flex; align-items: center; justify-content: center;
      }}
      .classified-tag .ico svg {{ width: 100%; height: 100%; stroke: var(--accent); }}

      /* ── HOOK INTRO (scène 1) : punch d'ouverture TikTok ──── */
      .hook-intro {{
        position: absolute; inset: 0; z-index: 90;
        pointer-events: none; opacity: 0;
      }}
      .hook-case-tag {{
        position: absolute; top: 240px; left: 50%;
        transform: translateX(-50%) scale(0.7);
        z-index: 92;
        font-family: var(--font-display2);
        font-size: 38px; font-weight: 400; letter-spacing: 10px;
        color: var(--accent);
        text-transform: uppercase;
        padding: 18px 36px;
        border: 2px solid var(--accent);
        background: rgba(0,0,0,0.78);
        backdrop-filter: blur(6px);
        text-shadow: 0 0 18px rgba(255,56,56,0.85);
        box-shadow: 0 0 32px rgba(255,56,56,0.35), inset 0 0 24px rgba(255,56,56,0.18);
        opacity: 0;
        white-space: nowrap;
      }}
      .hook-case-tag::before {{
        content: "● "; color: var(--accent);
        animation: hook-blink 0.9s steps(1,end) infinite;
      }}
      @keyframes hook-blink {{
        0%, 60% {{ opacity: 1; }}
        61%, 100% {{ opacity: 0; }}
      }}
      .hook-title {{
        position: absolute; top: 340px; left: 50%;
        transform: translateX(-50%);
        z-index: 92;
        font-family: var(--font-display);
        font-size: 132px; font-weight: 900; line-height: 0.94;
        letter-spacing: -2px;
        color: #fff;
        text-align: center;
        text-transform: uppercase;
        text-shadow:
          0 0 12px rgba(0,0,0,1),
          0 0 28px rgba(0,0,0,0.95),
          0 6px 30px rgba(0,0,0,0.95),
          0 0 60px rgba(255,56,56,0.45);
        -webkit-text-stroke: 2px rgba(0,0,0,0.85);
        paint-order: stroke fill;
        opacity: 0;
      }}
      .hook-title .accent {{ color: var(--accent); }}
      .hook-rgb-r, .hook-rgb-b {{
        position: absolute; inset: 0; z-index: 91;
        pointer-events: none; opacity: 0;
        mix-blend-mode: screen;
      }}
      .hook-flash-red {{
        position: absolute; inset: 0; z-index: 95;
        background: radial-gradient(circle at center, rgba(255,56,56,0.55) 0%, rgba(255,56,56,0.0) 60%);
        opacity: 0; pointer-events: none;
      }}

      /* ── OUTRO CTA (dernière scène) : "Quelle théorie ?" ──── */
      .outro-cta {{
        position: absolute; left: 0; right: 0;
        bottom: 540px;
        z-index: 88;
        text-align: center; opacity: 0;
        pointer-events: none;
      }}
      .outro-cta-kicker {{
        font-family: var(--font-display2);
        font-size: 30px; letter-spacing: 8px;
        color: var(--accent);
        text-transform: uppercase;
        margin-bottom: 18px;
        text-shadow: 0 0 20px rgba(255,56,56,0.7);
      }}
      .outro-cta-title {{
        font-family: var(--font-display);
        font-size: 112px; font-weight: 900; line-height: 0.94;
        color: #fff;
        text-transform: uppercase;
        text-shadow:
          0 0 12px rgba(0,0,0,1),
          0 4px 24px rgba(0,0,0,0.95),
          0 0 50px rgba(255,56,56,0.4);
        -webkit-text-stroke: 2px rgba(0,0,0,0.85);
        paint-order: stroke fill;
      }}
      .outro-cta-sub {{
        font-family: var(--font-display2);
        font-size: 38px; letter-spacing: 6px;
        color: rgba(255,255,255,0.92);
        text-transform: uppercase;
        margin-top: 28px;
        text-shadow: 0 4px 18px rgba(0,0,0,0.95);
      }}
      .outro-cta-sub .accent {{ color: var(--accent); }}
      .outro-cta-arrow {{
        display: block;
        margin: 30px auto 0;
        font-family: var(--font-display);
        font-size: 64px;
        color: var(--accent);
        animation: outro-bounce 0.7s ease-in-out infinite alternate;
      }}
      @keyframes outro-bounce {{
        0%   {{ transform: translateY(0); opacity: 1; }}
        100% {{ transform: translateY(14px); opacity: 0.5; }}
      }}

      /* ── Director layer: premium deterministic motion ─────── */
      .dir-layer {{
        position: absolute; inset: 0; z-index: 18;
        pointer-events: none; opacity: 0;
        mix-blend-mode: normal;
      }}
      .dir-layer::before {{
        content: "";
        position: absolute; inset: 0;
        background:
          linear-gradient(90deg, rgba(0,0,0,0.34), transparent 18%, transparent 82%, rgba(0,0,0,0.34)),
          linear-gradient(180deg, rgba(0,0,0,0.20), transparent 26%, transparent 76%, rgba(0,0,0,0.42));
      }}
      .dir-corner {{
        position: absolute; width: 92px; height: 92px;
        border-color: rgba(255,255,255,0.46);
        opacity: 0.78;
      }}
      .dir-corner.tl {{ top: 78px; left: 48px; border-top: 2px solid; border-left: 2px solid; }}
      .dir-corner.tr {{ top: 78px; right: 48px; border-top: 2px solid; border-right: 2px solid; }}
      .dir-corner.bl {{ bottom: 78px; left: 48px; border-bottom: 2px solid; border-left: 2px solid; }}
      .dir-corner.br {{ bottom: 78px; right: 48px; border-bottom: 2px solid; border-right: 2px solid; }}
      .dir-scan {{
        position: absolute; left: 0; right: 0; top: 0;
        height: 220px; opacity: 0;
        background: linear-gradient(180deg,
          transparent 0%,
          rgba(255,255,255,0.02) 30%,
          rgba(255,56,56,0.16) 51%,
          rgba(255,255,255,0.035) 62%,
          transparent 100%);
        filter: blur(1.6px);
      }}
      .dir-pulse {{
        position: absolute; left: 50%; top: 44%;
        width: 520px; height: 520px;
        margin-left: -260px; margin-top: -260px;
        border: 2px solid rgba(255,56,56,0.72);
        border-radius: 50%;
        box-shadow: 0 0 40px rgba(255,56,56,0.22), inset 0 0 40px rgba(255,56,56,0.10);
        opacity: 0;
      }}
      .dir-meta {{
        position: absolute; top: 110px;
        display: flex; align-items: center; gap: 14px;
        padding: 11px 14px 10px;
        border: 1px solid rgba(255,255,255,0.18);
        background: rgba(5,5,5,0.36);
        backdrop-filter: blur(4px);
        font-family: var(--font-mono);
        letter-spacing: 2.3px;
        text-transform: uppercase;
      }}
      .dir-meta.left {{ left: 58px; }}
      .dir-meta.right {{ right: 58px; }}
      .dir-meta span {{
        color: rgba(255,255,255,0.70);
        font-size: 14px; font-weight: 700;
      }}
      .dir-meta strong {{
        color: var(--accent);
        font-size: 14px; font-weight: 900;
      }}
      .dir-rule {{
        position: absolute; left: 210px; right: 210px; top: 171px;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,56,56,0.86), transparent);
        opacity: 0.9;
      }}

      /* ── Icon wrappers générique ────────────────────────────── */
      .ov-ico {{
        display: inline-flex; align-items: center; justify-content: center;
        flex-shrink: 0;
      }}
      .ov-ico svg {{ width: 100%; height: 100%; }}

      /* ── Subtitle : type comme héros, centré, pas de fond ──── */
      .subtitle {{
        position: absolute; left: 60px; right: 60px;
        bottom: 350px;
        z-index: 20; opacity: 0;
        color: #ffffff;
        font-family: "Oswald", var(--font-display2);
        font-size: 64px; font-weight: 800; line-height: 1.06;
        text-align: center; letter-spacing: 0;
        will-change: opacity, transform;
        /* Stack de text-shadows = lisibilité sur toutes images sans rectangle */
        text-shadow:
          0 0 8px rgba(0,0,0,1),
          0 0 16px rgba(0,0,0,0.95),
          0 4px 20px rgba(0,0,0,0.95),
          0 -2px 8px rgba(0,0,0,0.7),
          2px 2px 4px rgba(0,0,0,0.95),
          -2px -2px 4px rgba(0,0,0,0.95),
          2px -2px 4px rgba(0,0,0,0.95),
          -2px 2px 4px rgba(0,0,0,0.95);
        -webkit-text-stroke: 1px rgba(0,0,0,0.82);
        paint-order: stroke fill;
      }}
      .subtitle .emph {{
        color: var(--accent);
        -webkit-text-stroke: 1.4px rgba(0,0,0,0.95);
        paint-order: stroke fill;
        text-shadow:
          0 0 8px rgba(0,0,0,1),
          0 0 16px rgba(0,0,0,0.95),
          0 4px 20px rgba(0,0,0,0.95),
          0 0 18px rgba(255,56,56,0.42),
          0 0 34px rgba(255,56,56,0.24);
        filter: drop-shadow(0 0 4px rgba(255,56,56,0.32));
      }}
      .subtitle .word {{
        display: inline-block;
        will-change: opacity, transform;
      }}
      .subtitle .emph .word {{
        transform-origin: 50% 60%;
      }}
      /* Variant citation : Crimson Pro italic */
      .subtitle.quote {{
        font-family: var(--font-serif);
        font-style: italic;
        font-weight: 700;
        font-size: 62px;
        letter-spacing: 0;
      }}
      .subtitle.quote::before {{
        content: "“";
        position: absolute; top: -50px; left: 30%;
        font-size: 140px; font-weight: 900;
        color: var(--accent); opacity: 0.4;
        font-family: var(--font-serif);
        line-height: 1;
      }}

      /* ── Particles dust (CSS-only, deterministic via GSAP) ──── */
      .dust {{
        position: absolute; inset: 0; z-index: 3;
        pointer-events: none; overflow: hidden;
      }}
      .dust-mote {{
        position: absolute;
        width: 3px; height: 3px;
        background: rgba(255,255,255,0.5);
        border-radius: 50%;
        opacity: 0;
        will-change: transform, opacity;
      }}
      .dust-mote.glow {{
        width: 4px; height: 4px;
        background: rgba(255, 56, 56, 0.6);
        box-shadow: 0 0 8px rgba(255, 56, 56, 0.5);
      }}

      /* ── D3 mini-map dans la card location ──────────────────── */
      .ov-loc-map {{
        width: 140px; height: 140px;
        flex-shrink: 0;
        background: rgba(0,0,0,0.4);
        border: 1px solid var(--border);
        position: relative; overflow: hidden;
      }}
      .ov-loc-map svg {{ width: 100%; height: 100%; display: block; }}
      .ov-loc-map .country-bg {{
        fill: rgba(255,255,255,0.06);
        stroke: rgba(255,255,255,0.20);
        stroke-width: 0.4;
      }}
      .ov-loc-map .country-hl {{
        fill: rgba(255, 56, 56, 0.18);
        stroke: var(--accent);
        stroke-width: 0.7;
      }}
      .ov-loc-map .pin-pulse {{ fill: none; stroke: var(--accent); stroke-width: 1.2; }}
      .ov-loc-map .pin-dot   {{ fill: var(--accent); }}
      /* Petite marque tactique sous le sous-titre */
      .subtitle-rule {{
        position: absolute; bottom: 270px; left: 50%;
        transform: translateX(-50%);
        width: 60px; height: 2px; background: var(--accent);
        z-index: 19; opacity: 0;
      }}

      /* ── Semantic overlays : éditorial épuré ────────────────── */
      /* YEAR — typographie éditoriale dominante, top-center */
      .ov-year {{
        position: absolute; top: 200px; left: 0; right: 0;
        z-index: 25; opacity: 0;
        text-align: center;
        font-family: var(--font-display);  /* Anton */
        font-size: 420px; font-weight: 400; line-height: 0.82;
        letter-spacing: 0;
        color: var(--text);
      }}
      .ov-year-label {{
        display: block;
        font-family: var(--font-display2);  /* Bebas Neue */
        font-size: 26px; font-weight: 400;
        letter-spacing: 14px; color: var(--accent);
        margin-bottom: 18px; text-transform: uppercase;
      }}

      /* LOCATION — barre horizontale sobre, top-left */
      .ov-location {{
        position: absolute; top: 220px; left: 60px;
        z-index: 25; opacity: 0;
        display: flex; align-items: center; gap: 18px;
        padding: 18px 24px;
        background: var(--surface);
        border-left: 2px solid var(--accent);
        backdrop-filter: blur(6px);
      }}
      .ov-pin {{ width: 30px; height: 38px; flex-shrink: 0; }}
      .ov-loc-text {{ display: flex; flex-direction: column; gap: 4px; }}
      .ov-loc-label {{
        color: var(--text); font-size: 26px; font-weight: 800;
        letter-spacing: 1.5px;
      }}
      .ov-loc-coords {{
        color: var(--muted); font-size: 16px; font-weight: 500;
        letter-spacing: 1.2px; font-family: var(--font-mono);
      }}

      /* COUNTER — chiffre dominant + barre minimale, top-right */
      .ov-counter {{
        position: absolute; top: 240px; right: 60px;
        z-index: 25; opacity: 0;
        display: flex; flex-direction: column; gap: 12px;
        min-width: 320px; text-align: right;
      }}
      .ov-cnt-label {{
        color: var(--accent);
        font-family: var(--font-display2);
        font-size: 22px; font-weight: 400;
        letter-spacing: 10px; text-transform: uppercase;
      }}
      .ov-cnt-num {{
        color: var(--text);
        font-family: var(--font-display);  /* Anton */
        font-size: 180px; font-weight: 400; line-height: 0.88;
        letter-spacing: 0;
      }}
      .ov-cnt-bar {{
        width: 100%; height: 2px; background: var(--border);
        overflow: hidden; margin-top: 8px;
      }}
      .ov-cnt-fill {{
        height: 100%; width: 0%; background: var(--accent);
      }}

      /* DOSSIER — fiche minimale "scan en cours" */
      .ov-dossier {{
        position: absolute; top: 280px; left: 60px;
        width: 380px; z-index: 25; opacity: 0;
        background: var(--surface);
        border: 1px solid var(--border);
        backdrop-filter: blur(6px);
      }}
      .ov-dos-folder {{
        position: relative; padding: 22px 24px;
      }}
      .ov-dos-tab {{
        display: inline-flex; align-items: center; gap: 8px;
        font-family: var(--font-display2);
        font-size: 18px; font-weight: 400; letter-spacing: 6px;
        color: var(--accent); text-transform: uppercase;
        margin-bottom: 18px;
      }}
      .ov-dos-ico {{ width: 16px; height: 16px; }}
      .ov-dos-ico svg {{ stroke: var(--accent); }}
      .ov-dos-body {{
        display: flex; flex-direction: column; gap: 12px;
        padding: 8px 0 16px 0;
      }}
      .ov-dos-line {{ height: 3px; background: var(--text); opacity: 0.65; width: 100%; }}
      .ov-dos-line.short {{ width: 50%; }}
      .ov-dos-stamp {{
        display: block; margin-top: 18px;
        color: var(--accent); font-size: 18px; font-weight: 900;
        letter-spacing: 4px;
        border: 1.5px solid var(--accent); padding: 6px 14px;
        text-align: center;
      }}
      .ov-dos-paper {{ display: none; }}

      /* REDACTED — barres minimales noires + tag rouge */
      .ov-redacted {{
        position: absolute; top: 300px; left: 60px; right: 60px;
        height: 220px; z-index: 25; opacity: 1;
        pointer-events: none;
      }}
      .ov-red-bar {{
        position: absolute; left: 0;
        height: 22px; background: var(--text);
      }}
      .ov-red-stamp {{
        position: absolute; top: 110px; right: 0;
        color: var(--accent); font-size: 28px; font-weight: 900;
        letter-spacing: 6px; border: 1.5px solid var(--accent);
        padding: 6px 14px;
      }}

      /* ENTITY — alerte sobre */
      .ov-entity {{
        position: absolute; top: 240px; right: 60px;
        z-index: 25; opacity: 0;
        display: flex; align-items: center; gap: 18px;
        padding: 18px 24px;
        background: var(--surface);
        border-left: 2px solid var(--accent);
        backdrop-filter: blur(6px);
      }}
      .ov-ent-radar {{ width: 70px; height: 70px; flex-shrink: 0; }}
      .ov-ent-text {{ display: flex; flex-direction: column; gap: 4px; }}
      .ov-ent-label {{
        color: var(--text); font-size: 22px; font-weight: 800;
        letter-spacing: 2.5px; text-transform: uppercase;
      }}
      .ov-ent-sub {{
        color: var(--muted); font-size: 14px; font-weight: 600;
        letter-spacing: 2.5px;
        font-family: var(--font-mono);
      }}

      /* PERSON — fiche profile éditoriale */
      .ov-person {{
        position: absolute; top: 220px; left: 60px;
        z-index: 25; opacity: 0;
      }}
      .ov-per-card {{
        display: flex; gap: 22px; padding: 22px;
        background: var(--surface);
        border-left: 2px solid var(--accent);
        backdrop-filter: blur(6px);
        min-width: 440px;
      }}
      .ov-per-avatar {{
        position: relative; width: 100px; height: 130px;
        background: rgba(255,255,255,0.04);
        border: 1px solid var(--border);
        display: flex; align-items: center; justify-content: center;
        overflow: hidden;
      }}
      .ov-per-initials {{
        color: var(--accent); font-size: 44px; font-weight: 900;
        letter-spacing: 0;
      }}
      .ov-per-scan {{
        position: absolute; left: 0; right: 0; height: 1.5px;
        background: var(--accent);
      }}
      .ov-per-info {{
        display: flex; flex-direction: column; gap: 7px;
        justify-content: center; min-width: 240px;
      }}
      .ov-per-id {{
        display: flex; align-items: center; gap: 6px;
        color: var(--muted); font-size: 13px; font-weight: 600;
        letter-spacing: 2.5px;
        font-family: var(--font-mono);
        text-transform: uppercase;
      }}
      .ov-per-ico {{ width: 14px; height: 14px; }}
      .ov-per-ico svg {{ stroke: var(--muted); }}
      .ov-per-name {{
        color: var(--text); font-size: 30px; font-weight: 800;
        letter-spacing: 0;
      }}
      .ov-per-role {{
        color: var(--accent); font-size: 14px; font-weight: 700;
        letter-spacing: 3.5px; text-transform: uppercase;
      }}
      .ov-per-status {{
        color: var(--muted); font-size: 12px; font-weight: 600;
        letter-spacing: 2.5px;
        font-family: var(--font-mono);
        margin-top: 6px;
      }}

      /* ── Semantic animation pack v2 : 40 familles déterministes ─ */
      .sem-overlay {{
        position: absolute; inset: 0;
        z-index: 24; opacity: 0;
        pointer-events: none;
        color: var(--text);
        font-family: var(--font-sans);
      }}
      .sem-kicker {{
        font-family: var(--font-display2);
        color: var(--accent);
        letter-spacing: 7px;
        font-size: 20px;
        text-transform: uppercase;
        font-weight: 400;
      }}

      .truth-card {{
        position: absolute; inset: 0;
        z-index: 80; opacity: 0;
        pointer-events: none;
        padding: 0 76px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: flex-start;
        background: #000;
      }}
      .truth-kicker {{
        font-family: var(--font-mono);
        color: rgba(255,255,255,0.60);
        letter-spacing: 5px;
        font-size: 20px;
        text-transform: uppercase;
      }}
      .truth-title {{
        margin-top: 20px;
        font-family: var(--font-display);
        font-size: 132px;
        line-height: 0.88;
        letter-spacing: 0;
        text-transform: uppercase;
        text-shadow: 0 0 30px rgba(255,255,255,0.10);
      }}
      .truth-title .presque {{
        color: var(--accent);
        text-shadow:
          0 0 22px rgba(255,56,56,0.45),
          0 0 60px rgba(255,56,56,0.28);
      }}
      .truth-sub {{
        margin-top: 24px;
        font-family: var(--font-mono);
        color: var(--accent);
        font-size: 20px;
        letter-spacing: 3px;
        text-transform: uppercase;
      }}

      .sem-map {{
        z-index: 16;
        overflow: hidden;
        background:
          radial-gradient(circle at 50% 45%, rgba(255,56,56,0.16), transparent 22%),
          radial-gradient(circle at 40% 38%, rgba(255,255,255,0.08), transparent 28%),
          rgba(2,5,8,0.84);
      }}
      .sem-map-grid {{
        position: absolute; inset: -22%;
        background-image:
          linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px),
          linear-gradient(135deg, rgba(255,56,56,0.10), transparent 36%, rgba(255,255,255,0.08) 58%, transparent 78%);
        background-size: 64px 64px, 64px 64px, 100% 100%;
        filter: contrast(1.1);
      }}
      .sem-map-grid::before {{
        content: "";
        position: absolute; inset: 0;
        background:
          repeating-linear-gradient(24deg, transparent 0 86px, rgba(255,255,255,0.055) 87px 89px, transparent 90px 170px),
          repeating-linear-gradient(111deg, transparent 0 112px, rgba(255,56,56,0.08) 113px 115px, transparent 116px 220px);
      }}
      .sem-map-lines {{
        position: absolute; inset: 0;
        width: 100%; height: 100%;
      }}
      .sem-map-lines path {{
        fill: none;
        stroke: rgba(255,56,56,0.78);
        stroke-width: 4;
        stroke-linecap: round;
        filter: drop-shadow(0 0 12px rgba(255,56,56,0.55));
      }}
      .sem-map-ring {{
        fill: none;
        stroke: rgba(255,56,56,0.72);
        stroke-width: 3;
      }}
      .sem-map-dot {{
        position: absolute;
        width: 20px; height: 20px;
        margin-left: -10px; margin-top: -10px;
        border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 0 8px rgba(255,56,56,0.15), 0 0 30px rgba(255,56,56,0.9);
      }}
      .sem-map-cross {{
        position: absolute;
        width: 128px; height: 128px;
        margin-left: -64px; margin-top: -64px;
        border: 1px solid rgba(255,255,255,0.42);
      }}
      .sem-map-cross::before, .sem-map-cross::after {{
        content: "";
        position: absolute;
        background: rgba(255,255,255,0.46);
      }}
      .sem-map-cross::before {{ left: 50%; top: -30px; bottom: -30px; width: 1px; }}
      .sem-map-cross::after {{ top: 50%; left: -30px; right: -30px; height: 1px; }}
      .sem-map-label {{
        position: absolute; left: 62px; right: 62px; top: 164px;
        display: flex; flex-direction: column; align-items: flex-start;
        gap: 8px;
      }}
      .sem-map-title {{
        font-family: var(--font-display);
        font-size: 118px;
        line-height: 0.92;
        letter-spacing: 0;
        text-transform: uppercase;
        text-shadow: 0 8px 28px rgba(0,0,0,0.8);
      }}
      .sem-map-coords, .sem-map-readout {{
        font-family: var(--font-mono);
        color: rgba(255,255,255,0.76);
        font-size: 18px;
        letter-spacing: 2.2px;
        text-transform: uppercase;
      }}
      .sem-map-readout {{
        position: absolute; left: 62px; bottom: 340px;
        color: rgba(255,56,56,0.82);
      }}
      .sem-map-badge {{
        margin-top: 10px;
        display: inline-block;
        padding: 7px 10px;
        border: 1px solid rgba(255,56,56,0.72);
        color: var(--accent);
        font-family: var(--font-mono);
        font-size: 15px;
        letter-spacing: 2px;
        background: rgba(0,0,0,0.34);
      }}
      .sem-map-route-copy {{
        position: absolute; left: 70px; top: 540px;
        max-width: 740px;
        display: flex; flex-direction: column; gap: 5px;
      }}
      .sem-map-route-copy span {{
        font-family: var(--font-display2);
        color: var(--accent);
        letter-spacing: 6px;
        font-size: 22px;
      }}
      .sem-map-route-copy strong {{
        font-size: 32px;
        line-height: 1.08;
        text-transform: uppercase;
      }}
      .sem-map-route-copy em {{
        font-family: var(--font-mono);
        color: rgba(255,255,255,0.68);
        font-style: normal;
        font-size: 15px;
        letter-spacing: 2px;
        text-transform: uppercase;
      }}

      .sem-message .sem-phone {{
        position: absolute; right: 72px; top: 360px;
        width: 440px; min-height: 640px;
        border: 1px solid rgba(255,255,255,0.20);
        background: rgba(4,6,8,0.72);
        box-shadow: 0 24px 80px rgba(0,0,0,0.58);
        backdrop-filter: blur(8px);
      }}
      .sem-phone-bar {{
        position: absolute; top: 24px; left: 50%;
        width: 112px; height: 6px;
        transform: translateX(-50%);
        background: rgba(255,255,255,0.26);
      }}
      .sem-chat {{ padding: 76px 28px 32px; }}
      .sem-chat-meta {{
        font-family: var(--font-mono);
        color: rgba(255,255,255,0.55);
        font-size: 14px;
        letter-spacing: 2px;
        margin-bottom: 26px;
      }}
      .sem-bubble {{
        display: inline-block;
        max-width: 360px;
        padding: 18px 20px;
        background: rgba(255,255,255,0.92);
        color: #050505;
        font-size: 24px;
        line-height: 1.25;
        font-weight: 800;
      }}
      .sem-send-row {{
        display: flex; align-items: center; gap: 10px;
        margin-top: 22px;
        font-family: var(--font-mono);
        color: var(--accent);
        letter-spacing: 2px;
        font-size: 15px;
      }}
      .sem-send-row span {{
        width: 12px; height: 12px;
        border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 18px rgba(255,56,56,0.8);
      }}

      .sem-year {{
        top: 0;
        text-align: center;
        padding-top: 200px;
      }}
      .sem-year-num {{
        font-family: var(--font-display);
        font-size: 330px;
        line-height: 0.86;
        letter-spacing: 0;
        text-shadow: 0 10px 42px rgba(0,0,0,0.72);
      }}
      .sem-year-rule {{
        width: 520px; height: 2px;
        margin: 22px auto 0;
        background: linear-gradient(90deg, transparent, var(--accent), transparent);
      }}

      .sem-counter {{
        top: 250px; right: 62px; left: auto;
        width: 420px;
        display: flex; flex-direction: column; align-items: flex-end;
      }}
      .sem-counter-num {{
        font-family: var(--font-display);
        font-size: 142px;
        line-height: 0.92;
      }}
      .sem-meter {{
        width: 360px; height: 3px;
        background: rgba(255,255,255,0.18);
        overflow: hidden;
      }}
      .sem-meter div {{
        width: 100%; height: 100%;
        background: var(--accent);
      }}

      .sem-cctv-frame {{
        position: absolute; left: 72px; right: 72px; top: 300px;
        height: 520px;
        border: 1px solid rgba(255,255,255,0.22);
        background: rgba(0,0,0,0.58);
        box-shadow: inset 0 0 60px rgba(0,0,0,0.8);
      }}
      .sem-cctv-head, .sem-cctv-foot {{
        position: absolute; left: 24px; right: 24px;
        display: flex; justify-content: space-between;
        font-family: var(--font-mono);
        font-size: 16px;
        letter-spacing: 2px;
        color: rgba(255,255,255,0.72);
      }}
      .sem-cctv-head {{ top: 20px; }}
      .sem-cctv-head strong {{ color: var(--accent); }}
      .sem-cctv-foot {{ bottom: 20px; color: rgba(255,56,56,0.72); }}
      .sem-cctv-screen {{
        position: absolute; left: 32px; right: 32px; top: 62px; bottom: 62px;
        overflow: hidden;
        background:
          repeating-linear-gradient(0deg, rgba(255,255,255,0.04) 0 2px, transparent 3px 7px),
          radial-gradient(circle at 45% 44%, rgba(255,255,255,0.10), transparent 34%);
      }}
      .sem-cctv-scan {{
        position: absolute; left: 0; right: 0; top: 0;
        height: 90px;
        background: linear-gradient(180deg, transparent, rgba(255,56,56,0.24), transparent);
      }}
      .sem-cctv-box {{
        position: absolute;
        border: 2px solid rgba(255,56,56,0.95);
        box-shadow: 0 0 18px rgba(255,56,56,0.36);
      }}
      .sem-cctv-box.one {{ left: 160px; top: 118px; width: 210px; height: 150px; }}
      .sem-cctv-box.two {{ right: 190px; top: 210px; width: 150px; height: 120px; }}

      .sem-file {{
        top: 290px; left: 66px;
        width: 430px; height: 330px;
      }}
      .sem-file-front, .sem-file-back {{
        position: absolute;
        width: 390px; height: 270px;
        background: rgba(235,232,220,0.92);
        color: #101010;
        box-shadow: 0 24px 70px rgba(0,0,0,0.42);
      }}
      .sem-file-back {{ left: 36px; top: 42px; opacity: 0.7; }}
      .sem-file-back.two {{ left: 28px; top: 54px; opacity: 0.55; }}
      .sem-file-front {{ left: 0; top: 0; padding: 28px; }}
      .sem-file-tab {{
        display: inline-block;
        padding: 7px 12px;
        background: #101010;
        color: var(--accent);
        font-family: var(--font-display2);
        letter-spacing: 4px;
        font-size: 20px;
      }}
      .sem-file-line {{
        height: 8px; margin-top: 26px;
        background: rgba(0,0,0,0.72);
      }}
      .sem-file-line.short {{ width: 52%; }}
      .sem-file-line.mid {{ width: 76%; }}
      .sem-file-stamp {{
        margin-top: 30px;
        border: 2px solid var(--accent);
        color: var(--accent);
        display: inline-block;
        padding: 8px 12px;
        font-weight: 900;
        letter-spacing: 2px;
        text-transform: uppercase;
      }}

      .sem-redacted {{
        left: 62px; right: 62px; top: 290px;
        height: 330px;
      }}
      .sem-redact-bar {{
        position: absolute; left: 0;
        height: 28px;
        background: rgba(255,255,255,0.92);
        box-shadow: 0 0 24px rgba(0,0,0,0.6);
      }}
      .sem-redact-stamp {{
        position: absolute; right: 0; top: 210px;
        border: 2px solid var(--accent);
        color: var(--accent);
        padding: 10px 16px;
        font-family: var(--font-display2);
        font-size: 34px;
        letter-spacing: 7px;
        transform: rotate(-8deg);
      }}

      .sem-radar {{
        top: 290px; right: 70px;
        width: 420px; height: 420px;
      }}
      .sem-radar-dish {{
        position: absolute; right: 0; top: 0;
        width: 260px; height: 260px;
        border-radius: 50%;
        border: 1px solid rgba(255,56,56,0.65);
        background: radial-gradient(circle, rgba(255,56,56,0.12), rgba(0,0,0,0.34) 62%, transparent 63%);
        overflow: hidden;
      }}
      .sem-radar-ring {{
        position: absolute; border-radius: 50%;
        border: 1px solid rgba(255,255,255,0.22);
        inset: 28px;
      }}
      .sem-radar-ring.r2 {{ inset: 72px; }}
      .sem-radar-ring.r3 {{ inset: 112px; }}
      .sem-radar-sweep {{
        position: absolute; left: 50%; top: 50%;
        width: 120px; height: 2px;
        transform-origin: 0 50%;
        background: linear-gradient(90deg, var(--accent), transparent);
      }}
      .sem-radar-blip {{
        position: absolute; width: 12px; height: 12px;
        border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 18px rgba(255,56,56,0.8);
      }}
      .sem-radar-blip.b1 {{ left: 168px; top: 84px; }}
      .sem-radar-blip.b2 {{ left: 82px; top: 178px; }}
      .sem-radar-copy {{
        position: absolute; left: 0; top: 286px;
        width: 390px;
      }}
      .sem-radar-copy strong {{
        display: block;
        margin-top: 8px;
        font-size: 28px;
        letter-spacing: 0.4px;
      }}

      .sem-search {{
        left: 72px; right: 72px; top: 320px;
        height: 520px;
      }}
      .sem-search-title {{
        display: flex; justify-content: space-between; align-items: flex-end;
        margin-bottom: 18px;
        font-family: var(--font-mono);
      }}
      .sem-search-title span {{ color: var(--accent); letter-spacing: 4px; }}
      .sem-search-title strong {{ color: rgba(255,255,255,0.72); letter-spacing: 2px; }}
      .sem-search-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
      }}
      .sem-search-cell {{
        height: 116px;
        border: 1px solid rgba(255,255,255,0.20);
        background:
          linear-gradient(135deg, rgba(255,255,255,0.07), transparent),
          rgba(0,0,0,0.24);
      }}

      .sem-depth {{
        left: 74px; top: 290px;
        width: 410px; height: 560px;
      }}
      .sem-depth-copy strong {{
        display: block;
        margin-top: 8px;
        font-size: 28px;
      }}
      .sem-depth-shaft {{
        position: absolute; left: 18px; top: 122px;
        width: 86px; height: 360px;
        border-left: 2px solid rgba(255,255,255,0.22);
        border-right: 2px solid rgba(255,255,255,0.22);
        background: repeating-linear-gradient(180deg, rgba(255,255,255,0.08) 0 1px, transparent 2px 34px);
      }}
      .sem-depth-fill {{
        width: 100%; height: 100%;
        background: linear-gradient(180deg, rgba(255,56,56,0.06), rgba(255,56,56,0.35));
      }}
      .sem-depth-marker {{
        position: absolute; left: 106px; top: 288px;
        min-width: 180px;
        padding: 8px 12px;
        border-left: 2px solid var(--accent);
        background: rgba(0,0,0,0.58);
        color: var(--accent);
        font-family: var(--font-mono);
        letter-spacing: 2px;
      }}

      .sem-route {{
        left: 70px; top: 330px;
        width: 560px; height: 360px;
      }}
      .sem-route svg {{
        width: 520px; height: 260px;
        overflow: visible;
      }}
      .sem-route path {{
        fill: none;
        stroke: var(--accent);
        stroke-width: 5;
        stroke-linecap: round;
        filter: drop-shadow(0 0 14px rgba(255,56,56,0.55));
      }}
      .sem-route circle {{ fill: var(--accent); }}
      .sem-route-copy strong {{
        display: block;
        font-size: 28px;
        margin-top: 7px;
        text-transform: uppercase;
      }}
      .sem-route-copy span {{
        display: block;
        margin-top: 5px;
        font-family: var(--font-mono);
        color: rgba(255,255,255,0.68);
        letter-spacing: 2px;
        text-transform: uppercase;
      }}

      .sem-question {{
        top: 270px; left: 0; right: 0;
        text-align: center;
      }}
      .sem-question-mark {{
        font-family: var(--font-display);
        font-size: 260px;
        line-height: 0.88;
        color: var(--accent);
        text-shadow: 0 0 50px rgba(255,56,56,0.34);
      }}
      .sem-question-copy strong {{
        display: block;
        margin-top: 10px;
        font-size: 42px;
        text-transform: uppercase;
      }}
      .sem-question-copy span {{
        display: block;
        margin-top: 8px;
        font-family: var(--font-mono);
        color: rgba(255,255,255,0.68);
        letter-spacing: 2px;
        text-transform: uppercase;
      }}

      .sem-card {{
        top: 270px; right: 64px;
        width: 470px;
        display: flex; gap: 18px;
        padding: 20px;
        background: rgba(5,5,5,0.58);
        border-left: 2px solid var(--accent);
        border-top: 1px solid rgba(255,255,255,0.16);
        border-bottom: 1px solid rgba(255,255,255,0.10);
        backdrop-filter: blur(7px);
      }}
      .sem-card-icon {{
        width: 58px; height: 58px;
        color: var(--accent);
        flex: 0 0 auto;
      }}
      .sem-card-icon svg {{
        width: 100%; height: 100%;
        stroke: currentColor;
      }}
      .sem-card-body {{
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 7px;
      }}
      .sem-card-body strong {{
        font-size: 27px;
        line-height: 1.08;
        text-transform: uppercase;
        overflow-wrap: anywhere;
      }}
      .sem-card-body span {{
        font-family: var(--font-mono);
        color: rgba(255,255,255,0.62);
        font-size: 14px;
        letter-spacing: 2px;
        text-transform: uppercase;
      }}
      .sem-card-bars {{
        display: flex; flex-direction: column; gap: 5px;
        margin-top: 8px;
      }}
      .sem-card-bars i {{
        display: block; height: 3px;
        background: rgba(255,255,255,0.74);
      }}
      .sem-card-bars i:nth-child(1) {{ width: 78%; }}
      .sem-card-bars i:nth-child(2) {{ width: 56%; }}
      .sem-card-bars i:nth-child(3) {{ width: 86%; background: var(--accent); }}

      .sem-poster {{
        left: 70px; top: 250px;
        width: 360px; height: 500px;
      }}
      .sem-poster-sheet {{
        width: 330px;
        padding: 20px;
        background: rgba(238,235,224,0.94);
        color: #090909;
        box-shadow: 0 28px 80px rgba(0,0,0,0.50);
      }}
      .sem-poster-top {{
        background: #090909;
        color: var(--accent);
        padding: 7px 10px;
        font-family: var(--font-display2);
        font-size: 22px;
        letter-spacing: 4px;
        text-transform: uppercase;
      }}
      .sem-poster-face {{
        position: relative;
        height: 170px;
        margin-top: 18px;
        background: linear-gradient(135deg, rgba(0,0,0,0.14), rgba(0,0,0,0.42));
        overflow: hidden;
      }}
      .sem-poster-face span {{
        position: absolute; left: 50%; top: 50%;
        width: 84px; height: 108px;
        transform: translate(-50%, -42%);
        border-radius: 45% 45% 36% 36%;
        border: 2px solid rgba(0,0,0,0.42);
      }}
      .sem-poster-face i {{
        position: absolute; left: 0; right: 0; top: 0;
        height: 2px; background: var(--accent);
        box-shadow: 0 0 18px rgba(255,56,56,0.55);
      }}
      .sem-poster-name {{
        margin-top: 18px;
        font-size: 24px;
        font-weight: 900;
        text-transform: uppercase;
      }}
      .sem-poster-lines {{
        display: flex; flex-direction: column; gap: 7px;
        margin-top: 16px;
      }}
      .sem-poster-lines b {{
        display: block; height: 5px; background: rgba(0,0,0,0.64);
      }}
      .sem-poster-lines b:nth-child(2) {{ width: 72%; }}
      .sem-poster-lines b:nth-child(3) {{ width: 48%; }}

      .sem-blueprint {{
        left: 64px; top: 260px;
        width: 480px; height: 430px;
      }}
      .sem-blue-card {{
        padding: 22px;
        border: 1px solid rgba(255,255,255,0.18);
        background: rgba(0,0,0,0.58);
        backdrop-filter: blur(7px);
      }}
      .sem-blue-card svg {{
        width: 420px; height: 260px;
        margin-top: 16px;
      }}
      .sem-blue-card path {{
        fill: none;
        stroke: rgba(255,255,255,0.74);
        stroke-width: 3;
        stroke-linecap: round;
        stroke-linejoin: round;
      }}
      .sem-blue-card path:nth-child(2) {{
        stroke: var(--accent);
        filter: drop-shadow(0 0 12px rgba(255,56,56,0.45));
      }}
      .sem-blue-card circle {{ fill: var(--accent); }}
      .sem-blue-card strong {{
        display: block;
        margin-top: 8px;
        font-size: 25px;
        text-transform: uppercase;
      }}

      .sem-signal {{
        left: 64px; right: 64px; top: 300px;
        height: 330px;
      }}
      .sem-signal-card {{
        padding: 22px;
        border-left: 2px solid var(--accent);
        background: rgba(0,0,0,0.54);
        backdrop-filter: blur(7px);
      }}
      .sem-wave {{
        height: 138px;
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 18px;
      }}
      .sem-wave i {{
        width: 10px;
        background: linear-gradient(180deg, rgba(255,255,255,0.84), var(--accent));
        box-shadow: 0 0 14px rgba(255,56,56,0.38);
      }}
      .sem-signal-card strong {{
        display: block;
        font-size: 25px;
        text-transform: uppercase;
      }}

      .sem-experiment {{
        right: 64px; top: 270px;
        width: 430px; height: 470px;
      }}
      .sem-exp-core {{
        padding: 24px;
        background: rgba(0,0,0,0.62);
        border: 1px solid rgba(255,255,255,0.16);
        backdrop-filter: blur(8px);
      }}
      .sem-exp-rings {{
        position: relative;
        width: 230px; height: 230px;
        margin: 20px auto;
      }}
      .sem-exp-rings i {{
        position: absolute; inset: 0;
        border-radius: 50%;
        border: 2px solid rgba(255,56,56,0.54);
      }}
      .sem-exp-rings i:nth-child(2) {{ inset: 40px; border-color: rgba(255,255,255,0.24); }}
      .sem-exp-rings i:nth-child(3) {{ inset: 82px; border-color: rgba(255,56,56,0.34); }}
      .sem-exp-rings b {{
        position: absolute; left: 50%; top: 28px;
        width: 3px; height: 88px;
        background: var(--accent);
        transform-origin: 50% 100%;
        box-shadow: 0 0 18px rgba(255,56,56,0.75);
      }}
      .sem-exp-core strong {{
        display: block;
        font-size: 25px;
        text-transform: uppercase;
      }}

      .sem-board {{
        right: 64px; top: 255px;
        width: 470px; height: 380px;
      }}
      .sem-board-panel {{
        padding: 22px;
        background: rgba(0,0,0,0.58);
        border-top: 1px solid rgba(255,255,255,0.18);
        border-left: 2px solid var(--accent);
        backdrop-filter: blur(7px);
      }}
      .sem-board-nodes {{
        position: relative;
        height: 150px;
        margin-top: 20px;
      }}
      .sem-board-nodes span {{
        position: absolute;
        width: 54px; height: 54px;
        border-radius: 50%;
        border: 2px solid rgba(255,255,255,0.76);
        background: rgba(255,255,255,0.08);
      }}
      .sem-board-nodes span:nth-child(1) {{ left: 12px; top: 68px; }}
      .sem-board-nodes span:nth-child(2) {{ left: 170px; top: 16px; border-color: var(--accent); }}
      .sem-board-nodes span:nth-child(3) {{ right: 22px; top: 88px; }}
      .sem-board-nodes i {{
        position: absolute; left: 56px; right: 56px; top: 78px;
        height: 2px;
        background: linear-gradient(90deg, rgba(255,255,255,0.56), var(--accent), rgba(255,255,255,0.56));
      }}
      .sem-board-panel strong {{
        display: block;
        font-size: 25px;
        text-transform: uppercase;
      }}

      .sem-satellite {{
        z-index: 24;
        /* Plus léger, ne tape pas le centre de l'image */
        background:
          radial-gradient(circle at 80% 22%, rgba(255,56,56,0.10), transparent 35%);
      }}
      .sem-sat-grid {{
        /* Grid réduite : seulement coin haut-droite (zone du radar) */
        position: absolute; top: 110px; right: 30px;
        width: 380px; height: 380px;
        background-image:
          linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px);
        background-size: 38px 38px;
        opacity: 0.6;
      }}
      .sem-sat-orbit {{
        /* Radar compact en haut-droite, ne masque plus le centre de l'image */
        position: absolute; top: 130px; right: 50px;
        width: 340px; height: 340px;
      }}
      .sem-sat-orbit i {{
        position: absolute; inset: 0;
        border-radius: 50%;
        border: 1px solid rgba(255,255,255,0.20);
      }}
      .sem-sat-orbit i:nth-child(2) {{ inset: 50px; border-color: rgba(255,56,56,0.46); }}
      .sem-sat-orbit i:nth-child(3) {{ inset: 100px; border-color: rgba(255,255,255,0.28); }}
      .sem-sat-orbit b {{
        position: absolute; left: 50%; top: 50%;
        width: 160px; height: 2px;
        transform-origin: 0 50%;
        background: linear-gradient(90deg, var(--accent), transparent);
        box-shadow: 0 0 18px rgba(255,56,56,0.85);
      }}
      .sem-sat-orbit em {{
        position: absolute; left: 50%; top: 50%;
        width: 22px; height: 22px;
        margin-left: -11px; margin-top: -11px;
        border-radius: 50%;
        border: 2px solid var(--accent);
        box-shadow: 0 0 20px rgba(255,56,56,0.86);
      }}
      .sem-sat-copy {{
        /* Texte en bas-gauche, libère l'image centrale */
        position: absolute; left: 60px; right: 60px; bottom: 480px;
      }}
      .sem-sat-copy strong {{
        display: block;
        margin-top: 10px;
        font-family: var(--font-display);
        font-size: 72px;
        line-height: 0.92;
        text-transform: uppercase;
      }}
      .sem-sat-copy span, .sem-sat-copy small {{
        display: block;
        margin-top: 12px;
        font-family: var(--font-mono);
        color: rgba(255,255,255,0.70);
        font-size: 17px;
        letter-spacing: 2px;
        text-transform: uppercase;
      }}
      .sem-sat-copy small {{ color: var(--accent); }}

      .sem-security {{
        left: 64px; right: 64px; top: 260px;
        height: 620px;
      }}
      .sem-security-panel {{
        width: 520px;
        padding: 22px;
        background: rgba(0,0,0,0.64);
        border: 1px solid rgba(255,255,255,0.16);
        border-left: 2px solid var(--accent);
        backdrop-filter: blur(7px);
      }}
      .sem-security ul {{
        list-style: none;
        margin: 22px 0 18px;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }}
      .sem-security li {{
        display: flex;
        justify-content: space-between;
        gap: 18px;
        padding: 9px 10px;
        background: rgba(255,255,255,0.055);
        font-family: var(--font-mono);
        font-size: 15px;
        letter-spacing: 1.5px;
      }}
      .sem-security li b {{ color: var(--accent); font-weight: 800; }}
      .sem-security strong {{
        display: block;
        font-size: 27px;
        text-transform: uppercase;
      }}

      .sem-timewarp {{
        z-index: 23;
        background: radial-gradient(circle at 50% 48%, rgba(255,56,56,0.12), transparent 32%);
      }}
      .sem-time-lines {{
        position: absolute; inset: 160px 120px 420px;
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 36px;
        transform: skewX(-8deg);
      }}
      .sem-time-lines i {{
        display: block;
        border-left: 2px solid rgba(255,255,255,0.30);
        background: linear-gradient(180deg, transparent, rgba(255,56,56,0.25), transparent);
      }}
      .sem-time-copy {{
        position: absolute; left: 70px; right: 70px; top: 310px;
        text-align: center;
      }}
      .sem-time-copy strong {{
        display: block;
        margin-top: 16px;
        font-family: var(--font-display);
        font-size: 150px;
        line-height: 0.86;
      }}
      .sem-time-copy span {{
        display: block;
        margin-top: 12px;
        font-family: var(--font-mono);
        color: var(--accent);
        font-size: 18px;
        letter-spacing: 3px;
        text-transform: uppercase;
      }}

      .sem-blackout {{
        z-index: 25;
      }}
      .sem-black-veil {{
        position: absolute; inset: 0;
        background: rgba(0,0,0,0.40);
      }}
      .sem-black-beam {{
        position: absolute; top: 150px; bottom: 310px;
        width: 280px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.18), rgba(255,56,56,0.20), transparent);
        filter: blur(8px);
      }}
      .sem-black-copy {{
        position: absolute; left: 70px; top: 270px;
        width: 460px;
        padding: 22px;
        border-left: 2px solid var(--accent);
        background: rgba(0,0,0,0.58);
        backdrop-filter: blur(7px);
      }}
      .sem-black-copy strong {{
        display: block;
        margin-top: 10px;
        font-size: 30px;
        text-transform: uppercase;
      }}
    </style>
  </head>
  <body>
    <div id="root"
         data-composition-id="main"
         data-start="0"
         data-duration="{total_duration:.3f}"
         data-width="{WIDTH}"
         data-height="{HEIGHT}">

      {body_html}

      <div id="fog" class="fog clip"
           data-start="0" data-duration="{total_duration:.3f}" data-track-index="488"></div>

      <div id="dust" class="dust clip"
           data-start="0" data-duration="{total_duration:.3f}" data-track-index="490">
        {_dust_motes_html(28)}
      </div>

      <div id="vignette" class="vignette clip"
           data-start="0" data-duration="{total_duration:.3f}" data-track-index="500"></div>

      <div id="glitch-overlay" class="glitch-layer clip"
           data-start="0" data-duration="{total_duration:.3f}" data-track-index="510"></div>

      {film_grain_html}
      {letterbox_html}
      {persistent_tag_html}
      {brand_logo_html}
      {scroll_hook_html}
    </div>

    <script>
      // Safe render mode: GSAP-only deterministic timeline.
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{paused: true}});
      {js_code}

      // ── Particles dust : drift continu via GSAP timeline ────
      {_dust_motes_js(28, total_duration)}

      // ── Fog : drift très lent (full duration) ───────────────
      tl.fromTo("#fog",
        {{x: -30, y: -20, scale: 1.05, opacity: 0.55}},
        {{x: 30, y: 20, scale: 1.10, opacity: 0.70,
          duration: {total_duration:.3f}, ease: "sine.inOut",
          yoyo: true, repeat: 1}}, 0);

      // ── Vignette qui respire ────────────────────────────────
      {vignette_pulse_js}

      window.__timelines["main"] = tl;

      window.__hf = {{
        duration: {total_duration:.3f},
        seek: (time) => {{
          tl.time(time);
          if (window.__ThreeScene) window.__ThreeScene.update(time);
        }}
      }};
    </script>
  </body>
</html>
"""


def discover_sfx(sfx_root):
    """Scan ROOT/assets/sfx/ pour les fichiers SFX disponibles.
    Convention : whoosh.mp3, glitch.mp3, drone.mp3, classified.mp3, etc.
    Retourne un dict {nom_logique: chemin}.
    """
    if not sfx_root.is_dir():
        return {}
    found = {}
    for f in sfx_root.glob("*.mp3"):
        found[f.stem.lower()] = f
    for f in sfx_root.glob("*.wav"):
        if f.stem.lower() not in found:
            found[f.stem.lower()] = f
    return found


def _write_wav_mono(path, samples, sr=44100):
    """Écrit un fichier WAV mono 16-bit depuis un array float [-1, 1]."""
    import wave
    import numpy as np

    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)


def _synth_whoosh(duration=0.6, sr=44100):
    """Whoosh blanc filtré : sweep low-pass 300Hz → 5kHz → 300Hz."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    noise = np.random.randn(n).astype(np.float32) * 0.5
    # Filtrage manuel léger via moyenne glissante variable (cheap "lpf")
    cutoff = 0.05 + 0.45 * np.sin(np.pi * t / duration)
    out = np.zeros(n, dtype=np.float32)
    acc = 0.0
    for i in range(n):
        alpha = float(cutoff[i])
        acc = (1 - alpha) * acc + alpha * noise[i]
        out[i] = acc
    env = np.sin(np.pi * t / duration) ** 1.5
    return out * env * 0.75


def _synth_sub_drop(duration=1.2, sr=44100):
    """Sub-drop : 90Hz → 35Hz avec amplitude décroissante."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    freq = 90 * (35 / 90) ** (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    sub = np.sin(phase).astype(np.float32)
    # Petit harmonique pour épaisseur
    sub += 0.35 * np.sin(2 * phase)
    env = np.exp(-2.2 * t / duration)
    return sub * env * 0.9


def _synth_riser(duration=3.5, sr=44100):
    """Riser cinématique pro : 5 couches stratifiées.
      C1 sub-sweep 40→90Hz (mass)
      C2 mid tonal sweep 200→1200Hz (énergie)
      C3 white noise filtré ascendant (air)
      C4 ride cymbal simulée (shimmer)
      C5 woosh percussif final (impact d'ouverture)
    Compression douce par tanh, fade-in 0.1s, fade-out géré par le caller."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    progress = t / duration  # 0 → 1

    # C1 sub sweep (40 → 90 Hz)
    sub_freq = 40 * (90 / 40) ** progress
    sub_phase = 2 * np.pi * np.cumsum(sub_freq) / sr
    sub = np.sin(sub_phase).astype(np.float32) * 0.50
    sub_env = progress**1.6
    sub *= sub_env

    # C2 tonal mid sweep (200 → 1200 Hz)
    mid_freq = 200 * (1200 / 200) ** progress
    mid_phase = 2 * np.pi * np.cumsum(mid_freq) / sr
    mid = np.sin(mid_phase).astype(np.float32) * 0.32
    # Légère détune pour épaisseur
    mid += 0.18 * np.sin(2 * np.pi * np.cumsum(mid_freq * 1.005) / sr)
    mid_env = progress**1.8
    mid *= mid_env

    # C3 white noise filtré (passe-haut progressif)
    raw_noise = np.random.randn(n).astype(np.float32)
    # Filtre simple : différence + ré-accumulation pour passe-haut
    hp_noise = raw_noise - np.concatenate(([0.0], raw_noise[:-1])) * 0.92
    noise_env = progress**2.2
    noise = hp_noise * noise_env * 0.30

    # C4 ride/cymbal-like : bruit modulé par enveloppes courtes répétitives
    cymb = np.zeros(n, dtype=np.float32)
    pulse_period = int(sr * 0.18)  # un "ride" toutes les 180ms
    for i in range(0, n, pulse_period):
        decay = np.exp(-np.arange(min(pulse_period, n - i)) / (sr * 0.08))
        local_noise = np.random.randn(len(decay)).astype(np.float32)
        local_noise = local_noise - np.concatenate(([0.0], local_noise[:-1])) * 0.95
        cymb[i : i + len(decay)] += local_noise * decay * 0.18
    cymb *= progress**1.4

    # C5 woosh "tail" très final (dernière 0.4s : impact d'ouverture)
    woosh = np.zeros(n, dtype=np.float32)
    woosh_start = max(0, n - int(0.4 * sr))
    woosh_len = n - woosh_start
    if woosh_len > 0:
        wt = np.linspace(0, 0.4, woosh_len, endpoint=False)
        ws = np.random.randn(woosh_len).astype(np.float32)
        ws = ws - np.concatenate(([0.0], ws[:-1])) * 0.85
        woosh[woosh_start:] = ws * np.sin(np.pi * wt / 0.4) * 0.55

    # Mix
    signal = sub + mid + noise + cymb + woosh
    # Soft-clip pour caractère cinéma
    signal = np.tanh(signal * 1.05) * 0.88
    # Fade-in 0.1s
    fade_in = min(int(0.1 * sr), n)
    if fade_in > 0:
        signal[:fade_in] *= np.linspace(0, 1, fade_in)
    return signal


def _synth_impact(duration=1.8, sr=44100):
    """Impact cinématique pro : sub-drop 50→25Hz + click HF + body tonal + reverb tail.
    Caractère bande-son blockbuster, durée 1.8s avec queue percussive."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)

    # C1 sub-drop : 50Hz → 25Hz, decay 1.5s (vraie présence sub)
    sub_freq = 50 * (25 / 50) ** np.minimum(1.0, t / 1.5)
    sub_phase = 2 * np.pi * np.cumsum(sub_freq) / sr
    sub = np.sin(sub_phase).astype(np.float32) * 0.85
    sub *= np.exp(-1.6 * t / duration * 3)  # decay rapide initial puis sustain

    # C2 body tonal (100Hz + harmonique 200Hz) : remplit le mid-bass
    body = 0.45 * np.sin(2 * np.pi * 100.0 * t) * np.exp(-3.2 * t)
    body += 0.22 * np.sin(2 * np.pi * 200.0 * t) * np.exp(-5.5 * t)

    # C3 click HF transitoire : déclencheur d'attaque
    click_env = np.exp(-45 * t) * 0.55
    raw = np.random.randn(n).astype(np.float32)
    # Passe-haut simple pour piquer le HF
    click = raw - np.concatenate(([0.0], raw[:-1])) * 0.95
    click *= click_env

    # C4 reverb tail simulé : convolution avec une IR exponentielle
    ir_len = int(sr * 1.2)
    ir = np.random.randn(ir_len).astype(np.float32)
    ir *= np.exp(-np.linspace(0, 8, ir_len))  # decay rapide → réverb courte
    # Convolve direct sound avec IR (mais signal est court, on convolve "click" seulement)
    reverb = np.convolve(click * 0.4, ir, mode="same") * 0.12

    # Mix
    signal = sub + body + click + reverb
    # Soft-clip
    signal = np.tanh(signal * 0.95) * 0.90
    # Fade-out final 0.2s pour finir propre
    fade_out = min(int(0.2 * sr), n)
    if fade_out > 0:
        signal[-fade_out:] *= np.linspace(1, 0, fade_out)
    return signal


def _synth_glitch(duration=0.5, sr=44100):
    """Génère un effet de glitch numérique (bruits et impulsions carrées rapides)."""
    import numpy as np
    import random

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    signal = np.zeros(n, dtype=np.float32)
    for _ in range(4):
        start = random.randint(0, int(n * 0.7))
        length = random.randint(int(sr * 0.02), int(sr * 0.08))
        end = min(n, start + length)
        if end <= start:
            continue
        sub_t = t[start:end] - t[start]
        freq = random.choice([800, 1500, 3000, 5000])
        burst = np.sign(np.sin(2 * np.pi * freq * sub_t)) * 0.35
        burst += np.random.randn(len(sub_t)).astype(np.float32) * 0.25
        signal[start:end] = burst
    fade = min(int(0.01 * sr), n)
    if fade > 0:
        signal[:fade] *= np.linspace(0, 1, fade)
        signal[-fade:] *= np.linspace(1, 0, fade)
    return np.tanh(signal) * 0.75


def _synth_sub_bass_boom(duration=1.5, sr=44100):
    """Génère un boom sub-bass profond cinématique descendant (Bb0/A0)."""
    import numpy as np

    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    freq = 60.0 * (20.0 / 60.0) ** (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    sub = np.sin(phase).astype(np.float32)
    sub += 0.25 * np.sin(2 * phase)
    env = np.exp(-3.0 * t / duration)
    signal = sub * env
    # fade out final
    fade_out = min(int(0.15 * sr), n)
    if fade_out > 0:
        signal[-fade_out:] *= np.linspace(1, 0, fade_out)
    return np.tanh(signal) * 0.85


def _audio_duration_safe(path):
    """ffprobe safe : retourne 0 si fichier absent ou erreur."""
    try:
        return ffprobe_duration(path)
    except Exception:
        return 0.0


def ensure_ambient_music(projet_dir, target_duration=150):
    """Cherche musiques/[projet]_ambient.{mp3,wav} et la (re)génère si :
       - absente
       - plus courte que target_duration (vidéo plus longue que la musique)
    Retourne le Path du fichier audio ou None.
    """
    if not USE_AMBIENT_MUSIC:
        return None
    projet_name = projet_dir.name
    music_dir = ROOT / "musiques"
    music_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        music_dir / f"{projet_name}_ambient.mp3",
        music_dir / f"{projet_name}_ambient.wav",
    ]
    # Si une candidate existe ET couvre la durée cible avec ≥0.5s de marge, on la garde.
    for c in candidates:
        if c.exists() and c.stat().st_size > 1024:
            existing_dur = _audio_duration_safe(c)
            if existing_dur >= target_duration + 0.5:
                return c
            else:
                print(
                    f"   ♻️  Musique existante trop courte ({existing_dur:.1f}s < {target_duration:.1f}s) — régénération."
                )
                break

    # Génération à la volée via 2.3_generate_music.py
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "music_gen", ROOT / "2.3_generate_music.py"
        )
        if spec is None or spec.loader is None:
            return None
        music_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(music_mod)
    except Exception as e:
        print(f"   ⚠️  Impossible de charger 2.3_generate_music.py : {e}")
        return None

    # On génère systématiquement avec une marge de 10s sur la durée vidéo
    gen_duree = int(target_duration + 10)
    wav_path = music_dir / f"{projet_name}_ambient.wav"
    mp3_path = music_dir / f"{projet_name}_ambient.mp3"
    print(
        f"   🎵 Génération partition de tension ({gen_duree}s pour vidéo de {target_duration:.1f}s)..."
    )
    if not music_mod.generer_tension_score(str(wav_path), duree=gen_duree):
        return None
    if hasattr(music_mod, "wav_to_mp3") and music_mod.wav_to_mp3(
        str(wav_path), str(mp3_path)
    ):
        return mp3_path
    return wav_path if wav_path.exists() else None


def ensure_synth_sfx(sfx_root):
    """Génère whoosh.wav, sub-drop.wav, riser.wav, impact.wav, glitch.wav, sub_bass_boom.wav synthétiques si manquants."""
    if not USE_SYNTH_SFX:
        return False
    try:
        import numpy as np  # noqa: F401
    except ImportError:
        print("   ⚠️  numpy indisponible : SFX synthétiques skip.")
        return False
    sfx_root.mkdir(parents=True, exist_ok=True)
    existing = {f.stem.lower() for f in sfx_root.glob("*.mp3")}
    existing |= {f.stem.lower() for f in sfx_root.glob("*.wav")}
    generators = {
        "whoosh": _synth_whoosh,
        "sub-drop": _synth_sub_drop,
        "riser": _synth_riser,
        "impact": _synth_impact,
        "glitch": _synth_glitch,
        "sub_bass_boom": _synth_sub_boom_sfx,  # Use helper or define a local mapping
    }
    # map sub_bass_boom generator
    generators["sub_bass_boom"] = _synth_sub_bass_boom

    created = []
    for name, fn in generators.items():
        if name in existing:
            continue
        path = sfx_root / f"{name}.wav"
        _write_wav_mono(path, fn())
        created.append(name)
    if created:
        print(f"   🛠️  SFX synthétiques générés : {', '.join(created)}")
    return True


# Helper dummy name to satisfy references if any
def _synth_sub_boom_sfx():
    return _synth_sub_bass_boom()


def build_sfx_blocks(
    scenes_meta,
    sfx_available,
    total_duration,
    assets_dir,
    woosh_ts=[],
    glitch_ts=[],
    boom_ts=[],
):
    """Ajoute audio elements timés pour HyperFrames browser preview."""
    html_parts = []
    js_parts = []
    sfx_track = 2000

    def _stage(name, default_volume):
        """Helper : copie le fichier dans assets/ et retourne (src_name, volume)."""
        src = sfx_available.get(name)
        if not src:
            return None, default_volume
        dst = assets_dir / src.name
        if not dst.exists():
            shutil.copy(src, dst)
        return src.name, default_volume

    # 1. Drone ambient (continu, low vol) si présent
    drone_name, drone_vol = _stage("drone", 0.18)
    if drone_name:
        html_parts.append(
            f'<audio id="sfx_drone" class="clip" src="assets/{drone_name}" '
            f'data-start="0" data-duration="{total_duration:.3f}" '
            f'data-track-index="{sfx_track}" data-volume="{drone_vol}"></audio>'
        )
        sfx_track += 1

    # 2. Impact sur hook scène 1 (punch d'ouverture)
    impact_name, impact_vol = _stage("impact", 0.7)
    if impact_name and scenes_meta:
        first_start = scenes_meta[0]["start"]
        html_parts.append(
            f'<audio id="sfx_impact_hook" class="clip" src="assets/{impact_name}" '
            f'data-start="{first_start:.3f}" data-duration="1.8" '
            f'data-track-index="{sfx_track}" data-volume="{impact_vol}"></audio>'
        )
        sfx_track += 1

    # 3. Whooshes sur apparition des mots rouges
    whoosh_name, whoosh_vol = _stage("whoosh", 0.50)
    if whoosh_name:
        for idx, t in enumerate(woosh_ts):
            if t + 0.6 > total_duration:
                continue
            html_parts.append(
                f'<audio id="sfx_wh{idx}" class="clip" src="assets/{whoosh_name}" '
                f'data-start="{t:.3f}" data-duration="1.2" '
                f'data-track-index="{sfx_track + idx}" data-volume="{whoosh_vol}"></audio>'
            )
        sfx_track += len(woosh_ts)

    # 4. Glitches sur transitions
    glitch_name, glitch_vol = _stage("glitch", 0.45)
    if glitch_name:
        for idx, t in enumerate(glitch_ts):
            if t + 0.5 > total_duration:
                continue
            html_parts.append(
                f'<audio id="sfx_glitch{idx}" class="clip" src="assets/{glitch_name}" '
                f'data-start="{t:.3f}" data-duration="1.0" '
                f'data-track-index="{sfx_track + idx}" data-volume="{glitch_vol}"></audio>'
            )
        sfx_track += len(glitch_ts)

    # 5. Booms sur révélations
    boom_name, boom_vol = _stage("sub_bass_boom", 0.60)
    if boom_name:
        for idx, t in enumerate(boom_ts):
            if t + 1.0 > total_duration:
                continue
            html_parts.append(
                f'<audio id="sfx_boom{idx}" class="clip" src="assets/{boom_name}" '
                f'data-start="{t:.3f}" data-duration="1.8" '
                f'data-track-index="{sfx_track + idx}" data-volume="{boom_vol}"></audio>'
            )
        sfx_track += len(boom_ts)

    # 6. Riser sous le CTA outro (dernière scène, dans sa seconde moitié)
    riser_name, riser_vol = _stage("riser", 0.45)
    if riser_name and scenes_meta:
        last = scenes_meta[-1]
        t = last["start"] + last["duration"] * 0.45
        riser_dur = max(1.2, min(2.5, last["duration"] * 0.5))
        if t + riser_dur <= total_duration:
            html_parts.append(
                f'<audio id="sfx_riser_outro" class="clip" src="assets/{riser_name}" '
                f'data-start="{t:.3f}" data-duration="{riser_dur:.3f}" '
                f'data-track-index="{sfx_track}" data-volume="{riser_vol}"></audio>'
            )
            sfx_track += 1

    return html_parts, js_parts


def compile_sfx_composite(
    projet_dir,
    total_duration,
    woosh_timestamps,
    glitch_timestamps,
    boom_timestamps,
    scenes_data,
    dramatic_events=None,
):
    """
    Compile tous les triggers SFX (whooshes, glitches, booms, riser, impact, and scene SFX)
    dans un unique fichier audio sfx_composite.wav pour le mixage final FFmpeg.
    """
    import numpy as np
    import soundfile as sf
    from pathlib import Path

    sr = 44100
    n_samples = int(total_duration * sr)
    composite = np.zeros(n_samples, dtype=np.float32)

    sfx_root = Path(__file__).parent.resolve() / "assets" / "sfx"

    def load_sfx_sample(name):
        for ext in [".wav", ".mp3"]:
            p = sfx_root / f"{name}{ext}"
            if p.exists():
                try:
                    data, sample_rate = sf.read(str(p))
                    if len(data.shape) > 1:
                        data = np.mean(data, axis=1)
                    if sample_rate != sr:
                        num_samples = int(len(data) * sr / sample_rate)
                        data = np.interp(
                            np.linspace(0, len(data), num_samples, endpoint=False),
                            np.arange(len(data)),
                            data,
                        )
                    return data
                except Exception as e:
                    print(f"   ⚠️ Erreur chargement échantillon SFX {name} : {e}")
        return None

    whoosh_samp = load_sfx_sample("whoosh")
    glitch_samp = load_sfx_sample("glitch")
    boom_samp = load_sfx_sample("sub_bass_boom")
    if boom_samp is None:
        boom_samp = load_sfx_sample("sub-drop")
    impact_samp = load_sfx_sample("impact")
    riser_samp = load_sfx_sample("riser")

    # 1. Overlay whooshes
    if whoosh_samp is not None:
        for t in woosh_timestamps:
            idx = int(t * sr)
            if idx < n_samples:
                length = min(len(whoosh_samp), n_samples - idx)
                composite[idx : idx + length] += whoosh_samp[:length] * 0.45

    # 2. Overlay glitches
    if glitch_samp is not None:
        for t in glitch_timestamps:
            idx = int(t * sr)
            if idx < n_samples:
                length = min(len(glitch_samp), n_samples - idx)
                composite[idx : idx + length] += glitch_samp[:length] * 0.48

    # 3. Overlay booms
    if boom_samp is not None:
        for t in boom_timestamps:
            idx = int(t * sr)
            if idx < n_samples:
                length = min(len(boom_samp), n_samples - idx)
                composite[idx : idx + length] += boom_samp[:length] * 0.58

    # 4. Overlay standard SFX
    if impact_samp is not None and scenes_data:
        idx = int(scenes_data[0]["voice_start"] * sr)
        if idx < n_samples:
            length = min(len(impact_samp), n_samples - idx)
            composite[idx : idx + length] += impact_samp[:length] * 0.65

    if riser_samp is not None and scenes_data:
        last_scene = scenes_data[-1]
        t_riser = last_scene["voice_start"] + last_scene["duration"] * 0.45
        idx = int(t_riser * sr)
        if idx < n_samples:
            length = min(len(riser_samp), n_samples - idx)
            composite[idx : idx + length] += riser_samp[:length] * 0.45

    # Chargement des SFX de scènes générés par 2.3_generate_music.py si présents
    for i, scene in enumerate(scenes_data):
        sfx_src = Path(projet_dir) / "audio" / "sfx" / f"scene_{i + 1}.wav"
        if sfx_src.exists():
            try:
                data, sample_rate = sf.read(str(sfx_src))
                if len(data.shape) > 1:
                    data = np.mean(data, axis=1)
                if sample_rate != sr:
                    num_samples = int(len(data) * sr / sample_rate)
                    data = np.interp(
                        np.linspace(0, len(data), num_samples, endpoint=False),
                        np.arange(len(data)),
                        data,
                    )
                idx = int(scene["voice_start"] * sr)
                if idx < n_samples:
                    length = min(len(data), n_samples - idx)
                    composite[idx : idx + length] += data[:length] * 0.45
            except Exception as e:
                print(f"   ⚠️ Erreur chargement SFX scène {i + 1} : {e}")

    # Ruptures horrifiques : retire les ambiances/SFX juste avant la révélation,
    # puis place un impact sec exactement sur le mot-clé.
    dramatic_events = dramatic_events or []
    for event in dramatic_events:
        t = float(event["time"])
        silence_start = max(0, int((t - 0.85) * sr))
        silence_end = max(silence_start, int((t - 0.06) * sr))
        composite[silence_start:silence_end] = 0.0
        sting = boom_samp if boom_samp is not None else impact_samp
        if sting is not None:
            idx = int(t * sr)
            if idx < n_samples:
                length = min(len(sting), n_samples - idx)
                composite[idx : idx + length] += sting[:length] * 0.78

    # Soft-clip et normalisation
    composite = np.tanh(composite * 1.15)
    peak = np.max(np.abs(composite))
    if peak > 0:
        composite = (composite / peak * 0.85).astype(np.float32)

    out_path = Path(projet_dir) / "audio" / "sfx_composite.wav"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), composite, sr)
    print(f"   🔊 sfx_composite.wav généré avec succès ({len(composite) / sr:.2f}s)")
    return out_path


def write_hyperframes_project(render_dir):
    render_dir.mkdir(parents=True, exist_ok=True)
    (render_dir / "package.json").write_text(
        json.dumps(
            {
                "name": render_dir.name,
                "private": True,
                "type": "module",
                "scripts": {
                    "dev": f"npx --yes hyperframes@{HF_VERSION} preview",
                    "check": f"npx --yes hyperframes@{HF_VERSION} lint && npx --yes hyperframes@{HF_VERSION} validate && npx --yes hyperframes@{HF_VERSION} inspect",
                    "render": f"npx --yes hyperframes@{HF_VERSION} render",
                },
            },
            indent=2,
        )
    )
    (render_dir / "hyperframes.json").write_text(
        json.dumps(
            {
                "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                "paths": {
                    "blocks": "compositions",
                    "components": "compositions/components",
                    "assets": "assets",
                },
            },
            indent=2,
        )
    )
    (render_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": render_dir.name,
                "name": render_dir.name,
                "createdAt": "2026-01-01T00:00:00.000Z",
            },
            indent=2,
        )
    )


def find_dramatic_audio_events(scenes_data):
    """Repère les révélations 'vide' et 'disparu' via l'alignement Whisper."""
    targets_by_scene = {}
    for raw_event in DRAMATIC_EVENT_SCENES.split(","):
        scene_number, separator, target = raw_event.strip().partition(":")
        if not separator:
            continue
        try:
            targets_by_scene[int(scene_number) - 1] = _normalize_word(target)
        except ValueError:
            print(f"   ⚠️ Rupture dramatique invalide ignorée : {raw_event}")

    events = []
    for scene in scenes_data:
        target = targets_by_scene.get(scene.get("scene_idx"))
        if not target:
            continue
        voice_start = float(scene.get("voice_start", 0.0))
        for word in scene.get("word_timings") or []:
            normalized = _normalize_word(word.get("text", ""))
            if normalized == target:
                events.append(
                    {
                        "word": normalized,
                        "time": voice_start + float(word.get("start", 0.0)),
                    }
                )
    return events


def measure_loudness(video_path):
    """Retourne (LUFS intégrés, true peak) via le résumé EBU R128."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video_path),
        "-af",
        "ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    summary = result.stderr.rsplit("Summary:", 1)[-1]
    integrated = re.search(r"Integrated loudness:\s+I:\s*(-?\d+(?:\.\d+)?)", summary)
    true_peak = re.search(r"True peak:\s+Peak:\s*(-?\d+(?:\.\d+)?)", summary)
    if not integrated or not true_peak:
        return None
    return float(integrated.group(1)), float(true_peak.group(1))


def normalize_loudness_master(video_path):
    """Applique une finition broadcast stable, puis limite les pics avant AAC."""
    video_path = Path(video_path)
    mastering_filter = (
        "acompressor=threshold=-10dB:ratio=3:attack=5:release=80:makeup=2dB,"
        "alimiter=limit=0.794328:level=false,"
        f"loudnorm=I={TARGET_LUFS:.1f}:TP=-2.0:LRA=11,"
        "alimiter=limit=0.794328:level=false"
    )
    normalized_path = video_path.with_name(f"{video_path.stem}.normalized.mp4")
    normalize_cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(video_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "copy",
        "-af",
        mastering_filter,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(normalized_path),
    ]
    normalized = subprocess.run(normalize_cmd, capture_output=True, text=True)
    if normalized.returncode != 0 or not normalized_path.exists():
        print(f"   ⚠️ Seconde passe loudness échouée : {normalized.stderr[-500:]}")
        normalized_path.unlink(missing_ok=True)
        return

    normalized_path.replace(video_path)
    measured = measure_loudness(video_path)
    if measured:
        integrated, true_peak = measured
        correction_db = TARGET_LUFS - integrated
        if abs(correction_db) > 0.2:
            corrected_path = video_path.with_name(f"{video_path.stem}.corrected.mp4")
            correction_filter = (
                f"volume={correction_db:.2f}dB,"
                "alimiter=limit=0.841395:level=false"
            )
            correction_cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-i",
                str(video_path),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c:v",
                "copy",
                "-af",
                correction_filter,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(corrected_path),
            ]
            corrected = subprocess.run(
                correction_cmd, capture_output=True, text=True
            )
            if corrected.returncode == 0 and corrected_path.exists():
                corrected_path.replace(video_path)
                measured = measure_loudness(video_path) or measured
            else:
                corrected_path.unlink(missing_ok=True)

        integrated, true_peak = measured
        print(
            f"   ✅ Master final : {integrated:.1f} LUFS, "
            f"true peak {true_peak:.1f} dBFS"
        )
    else:
        print(
            f"   ✅ Master finalisé vers {TARGET_LUFS:.1f} LUFS "
            "avec true peak protégé"
        )


def mix_audio_post_render(
    projet_dir,
    rendered_mp4_path,
    final_mp4_path,
    scenes_data,
    total_duration,
    dramatic_events=None,
):
    """
    Mélange de manière professionnelle la voix, les SFX et la musique d'ambiance avec FFmpeg.
    Applique une compression sidechain pour 'ducker' la musique sous la voix.

    NOTE : HyperFrames embarque également l'audio dans le HTML (via <audio> tags),
    mais les pistes voix sont forcées à volume=0.0 dans le HTML pour éviter le double.
    FFmpeg est l'unique source audio du final.mp4.
    """
    print("\n⚡️  Strip audio du rendu HyperFrames...")

    # Étape 0 : extraire uniquement la vidéo du MP4 rendu (supprimer l'audio HyperFrames)
    video_only_path = Path(rendered_mp4_path).with_suffix(".video_only.mp4")
    strip_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(rendered_mp4_path),
        "-an",  # no audio
        "-c:v",
        "copy",
        str(video_only_path),
    ]
    r_strip = subprocess.run(strip_cmd, capture_output=True, text=True)
    if r_strip.returncode != 0 or not video_only_path.exists():
        print(
            f"   ⚠️ Strip audio échec, on utilise le MP4 original : {r_strip.stderr[:200]}"
        )
        video_only_path = Path(rendered_mp4_path)  # fallback
    else:
        print("   ✅ Audio HyperFrames retiré (vidéo seule prête pour mix FFmpeg)")

    print("\n🎚️  Mixage audio post-rendu avec compression sidechain...")

    inputs = []
    filter_parts = []
    input_idx = 1

    # 1. Liste des voix et leurs timings
    voix_inputs = []
    for i, scene in enumerate(scenes_data):
        audio_src = Path(projet_dir) / "audio" / f"scene_{i + 1}.wav"
        if audio_src.exists():
            inputs.extend(["-i", str(audio_src)])
            delay_ms = int(round(scene["voice_start"] * 1000))
            filter_parts.append(f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}[v{i}];")
            voix_inputs.append(f"[v{i}]")
            input_idx += 1

    n_voices = len(voix_inputs)
    if n_voices > 0:
        # Construire la voix complète et la splitter en 2 (sidechain + mix final)
        filter_parts.append(
            f"{''.join(voix_inputs)}amix=inputs={n_voices}:normalize=0[voice_full];"
        )
        filter_parts.append("[voice_full]asplit=2[voice_sc][voice_mix];")
    else:
        filter_parts.append("aevalsrc=0:d=10[voice_sc];")
        filter_parts.append("aevalsrc=0:d=10[voice_mix];")

    # 2. SFX Composite unique
    sfx_composite = Path(projet_dir) / "audio" / "sfx_composite.wav"
    if sfx_composite.exists():
        inputs.extend(["-i", str(sfx_composite)])
        filter_parts.append(f"[{input_idx}:a]volume=1.0[sfx_full];")
        input_idx += 1
    else:
        filter_parts.append("aevalsrc=0:d=10[sfx_full];")

    # 3. Ajouter la musique d'ambiance
    projet_name = Path(projet_dir).name
    musique_path = None
    candidats_dirs = [Path(projet_dir), Path(projet_dir).parent.parent / "musiques"]
    for d in candidats_dirs:
        for ext in [".mp3", ".wav"]:
            candidat = d / f"{projet_name}_ambient{ext}"
            if candidat.exists():
                musique_path = candidat
                break
        if musique_path:
            break

    if not musique_path:
        mus_dir = Path(projet_dir).parent.parent / "musiques"
        if mus_dir.exists():
            candidats = list(mus_dir.glob("*.mp3")) + list(mus_dir.glob("*.wav"))
            if candidats:
                musique_path = candidats[0]

    if musique_path:
        inputs.extend(["-i", str(musique_path)])
        music_idx = input_idx
        input_idx += 1
        music_chain = (
            f"[{music_idx}:a]aloop=loop=-1:size=2e9,"
            f"volume={POST_MIX_MUSIC_VOLUME:.3f}"
        )
        if USE_DRAMATIC_SILENCE:
            for event in dramatic_events or []:
                t = float(event["time"])
                start = max(0.0, t - 0.85)
                end = t + 0.55
                music_chain += (
                    f",volume=0:enable='between(t,{start:.3f},{end:.3f})'"
                )
        filter_parts.append(music_chain + "[music_raw];")
        # voice_sc = copie dédiée au sidechain (ne sera pas réutilisée)
        filter_parts.append(
            "[music_raw][voice_sc]sidechaincompress=threshold=0.15:ratio=4.5:attack=15:release=350[music_ducked];"
        )
        print(
            f"   🎼 Musique post-mix : volume={POST_MIX_MUSIC_VOLUME:.2f}, "
            "ducking voix actif"
        )
    else:
        filter_parts.append("aevalsrc=0:d=10[music_ducked];")

    # 4. Mixer le tout : voice_mix (copie voix pour mix) + sfx + musique duckée
    filter_parts.append(
        f"[voice_mix][sfx_full][music_ducked]"
        f"amix=inputs=3:normalize=0,"
        f"loudnorm=I={TARGET_LUFS:.1f}:TP=-1.0:LRA=11[audio_master]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_only_path),  # vidéo sans audio
    ]
    cmd.extend(inputs)
    cmd.extend(
        [
            "-filter_complex",
            "".join(filter_parts),
            "-map",
            "0:v",
            "-map",
            "[audio_master]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(final_mp4_path),
        ]
    )

    print(f"   🏃 Commande FFmpeg : {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        print("   ✅ Audio mixé avec succès (sidechain compress appliqué)")
        normalize_loudness_master(final_mp4_path)
    else:
        print(f"   ⚠️ FFmpeg mixage erreur : {r.stderr}")
        shutil.copy(rendered_mp4_path, final_mp4_path)


def render_projet(projet_dir, do_check=False, prepare_only=False):
    projet_dir = Path(projet_dir).resolve()
    projet_name = projet_dir.name

    script = json.loads((projet_dir / "script.json").read_text(encoding="utf-8"))
    scenes = script["scenes"]
    source_map = load_visual_source_map(projet_dir)
    # Reset per-render state (so the Lottie variety tracker doesn't leak between videos).
    _reset_director_state()
    print(f"\n🎞️  HyperFrames render : {projet_name} ({len(scenes)} scènes)")

    render_dir = RENDER_ROOT / projet_name
    if render_dir.exists():
        shutil.rmtree(render_dir)
    assets_dir = render_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    write_hyperframes_project(render_dir)
    if USE_BRAND_LOGO and BRAND_LOGO_PATH:
        logo_src = Path(BRAND_LOGO_PATH).expanduser().resolve()
        if logo_src.exists():
            shutil.copy(logo_src, assets_dir / "yurei_logo.png")
            print(f"   ◉ Logo Yūrei intégré : {logo_src.name}")
        else:
            print(f"   ⚠️ Logo introuvable : {logo_src}")

    # Copy the curated Lottie library into the render assets. Animation JSON
    # is embedded in the page so frame capture stays deterministic.
    _lottie_src = ROOT / "assets" / "lottie"
    if USE_LOTTIE_OVERLAYS and _lottie_src.exists():
        _lottie_dst = assets_dir / "lottie"
        try:
            shutil.copytree(
                _lottie_src,
                _lottie_dst,
                ignore=shutil.ignore_patterns(
                    "generate_starter_library.py",
                    "curate_library.py",
                    "__pycache__",
                    "node_modules",
                    "*.tgz",
                    "package*.json",
                ),
            )
            n_anims = len(list((_lottie_dst / "library").glob("*.json")))
            n_vendor = (
                len(list((_lottie_dst / "vendor").glob("*")))
                if (_lottie_dst / "vendor").exists()
                else 0
            )
            print(
                f"   🎞️  Lottie library copiée ({n_anims} animations, {n_vendor} vendor files)"
            )
        except Exception as e:
            print(f"   ⚠️ Lottie library non copiée : {e}")

    scenes_meta = []
    scenes_data = []
    cursor = 0.0
    all_woosh_timestamps = []
    all_glitch_timestamps = []
    all_boom_timestamps = []
    for i, scene in enumerate(scenes):
        s_id = f"s{i + 1}"
        audio_src = projet_dir / "audio" / f"scene_{i + 1}.wav"
        if not audio_src.exists():
            print(f"   ⚠️  Skip scène {i + 1} : audio manquant")
            continue
        dur = ffprobe_duration(audio_src)
        shutil.copy(audio_src, assets_dir / f"{s_id}_vo.wav")

        if USE_IMAGES:
            # On prend jusqu'à 5 images par scène
            images = pick_images(projet_dir, i, scene)[:5]
            shots_list = images if len(images) >= 2 else (images * 2 if images else [])
            for j, img in enumerate(shots_list[:5]):
                shutil.copy(img, assets_dir / f"{s_id}_bg{j + 1}{img.suffix}")
        else:
            images = []

        subtitle_src = (
            scene.get("subtitle")
            or scene.get("sous_titre")
            or scene.get("audio_tts")
            or scene.get("voix_off_tts")
            or scene.get("voix_off", "")
        )
        truth_preroll = (
            TRUTH_PREROLL_SECONDS if (i == 1 and not SKIP_TRUTH_CARD) else 0.0
        )
        scene_start = cursor + truth_preroll

        if truth_preroll > 0:
            # La truth card couvre la période entre image scène 1 (qui se retire
            # à scene_1_end + 0.3) et image scène 2 (qui apparaît à scene_2_start).
            # On la fait commencer 0.5s AVANT la fin de scène 1 et se prolonger
            # jusqu'à ce que l'image de scène 2 soit déjà visible (chevauchement).
            card_start = max(0.0, cursor - 0.5)
            card_dur = truth_preroll + 1.2  # +0.5 avant + 0.7 après scene_2_start
            pre_html, pre_js = build_true_story_card(
                s_id, i, card_start, card_dur, subtitle_src
            )
        else:
            pre_html, pre_js = [], []

        # Alignement mot-par-mot via Whisper (anti-drift)
        word_timings = (
            align_scene_words(audio_src, subtitle_src) if USE_WHISPER_SYNC else None
        )
        if word_timings:
            print(f"   🔠 Whisper sync : {len(word_timings)} mots alignés")

        html, js, n_shots, scene_has_overlays, woosh_t, glitch_t, boom_t = (
            build_scene_blocks(
                i,
                scene,
                dur,
                images,
                scene_start,
                len(scenes),
                visual_bible=script.get("visual_bible"),
                word_timings=word_timings,
                source_map=source_map,
            )
        )
        all_woosh_timestamps.extend(woosh_t)
        all_glitch_timestamps.extend(glitch_t)
        all_boom_timestamps.extend(boom_t)
        if pre_html:
            html = pre_html + html
            js = pre_js + js

        # Hook intro punch (scène 1 uniquement) — superposé sur la scène
        hook_html, hook_js = build_hook_intro(s_id, i, scene_start, dur, subtitle_src)
        if hook_html:
            html = html + hook_html
            js = js + hook_js

        # Tail après la voix sur la dernière scène (CTA + musique seuls)
        outro_tail = (
            OUTRO_TAIL_SECONDS if (i == len(scenes) - 1 and USE_OUTRO_CTA) else 0.0
        )

        # Outro CTA (dernière scène uniquement) — superposé en fin, étendu par le tail
        outro_html, outro_js = build_outro_cta(
            s_id, i, scene_start, dur, len(scenes), tail_seconds=outro_tail
        )
        if outro_html:
            html = html + outro_html
            js = js + outro_js

        scene_total_duration = dur + truth_preroll + outro_tail
        scenes_meta.append(
            {
                "start": cursor,
                "duration": scene_total_duration,
                "html": html,
                "js": js,
                "has_overlays": scene_has_overlays,
            }
        )
        scenes_data.append(
            {
                "scene_idx": i,
                "voice_start": scene_start,
                "duration": dur,
                "word_timings": word_timings or [],
            }
        )
        bg_variant = BG_VARIANTS[i % len(BG_VARIANTS)] if not USE_IMAGES else "img"
        extras = []
        if truth_preroll:
            extras.append(f"pause vérité {truth_preroll:.2f}s")
        if outro_tail:
            extras.append(f"tail outro {outro_tail:.2f}s")
        extra = " + " + " + ".join(extras) if extras else ""
        print(
            f"   ▶ Scène {i + 1} : {dur:.2f}s{extra} · bg={bg_variant}, start={cursor:.2f}s"
        )
        cursor += scene_total_duration

    total = cursor

    # ── SFX scanning : ROOT/assets/sfx/*.mp3 (drone, whoosh, glitch...)
    sfx_root = ROOT / "assets" / "sfx"
    ensure_synth_sfx(sfx_root)
    sfx_available = discover_sfx(sfx_root)
    if sfx_available:
        sfx_html, sfx_js = build_sfx_blocks(
            scenes_meta,
            sfx_available,
            total,
            assets_dir,
            woosh_ts=all_woosh_timestamps,
            glitch_ts=all_glitch_timestamps,
            boom_ts=all_boom_timestamps,
        )
        if sfx_html:
            scenes_meta.append(
                {"start": 0, "duration": total, "html": sfx_html, "js": sfx_js}
            )
            print(f"   🔊 SFX intégrés : {', '.join(sfx_available.keys())}")
    else:
        print(
            f"   ℹ️  Aucun SFX trouvé dans assets/sfx/ (optionnel : drop tes whoosh.mp3, drone.mp3 etc.)"
        )

    # ── Musique d'ambiance stressante (track audio continue, durée >= vidéo)
    music_path = ensure_ambient_music(projet_dir, target_duration=total)
    if music_path:
        music_dest = assets_dir / f"ambient_music{music_path.suffix}"
        shutil.copy(music_path, music_dest)
        music_html = [
            f'<audio id="ambient_music" class="clip" src="assets/{music_dest.name}" '
            f'data-start="0" data-duration="{total:.3f}" '
            f'data-track-index="2500" data-volume="{AMBIENT_MUSIC_VOLUME}"></audio>'
        ]
        scenes_meta.append(
            {"start": 0, "duration": total, "html": music_html, "js": []}
        )
        print(
            f"   🎼 Musique d'ambiance intégrée : {music_path.name} @ vol={AMBIENT_MUSIC_VOLUME}"
        )
    else:
        print(
            f"   ℹ️  Pas de musique d'ambiance (USE_AMBIENT_MUSIC=0 ou échec génération)"
        )

    html_doc = build_html(projet_name, scenes_meta, total)
    (render_dir / "index.html").write_text(html_doc, encoding="utf-8")
    print(f"   📄 HTML écrit ({len(html_doc) // 1024} KB), total = {total:.2f}s")

    if do_check:
        print("   🔍 Lint + validate...")
        subprocess.run(["npm", "run", "check"], cwd=render_dir, check=True)

    if prepare_only:
        print(f"   ✅ Composition prête pour preview/snapshot : {render_dir}")
        return render_dir

    print("   🎬 npx hyperframes render (headless Chrome)...")
    r = subprocess.run(["npm", "run", "render"], cwd=render_dir)
    if r.returncode != 0:
        raise RuntimeError(f"HyperFrames render échec (code {r.returncode})")

    renders = sorted(
        (render_dir / "renders").glob("*.mp4"), key=lambda p: p.stat().st_mtime
    )
    if not renders:
        raise RuntimeError("Aucun MP4 trouvé dans renders/")
    final = projet_dir / "final.mp4"
    dramatic_events = (
        find_dramatic_audio_events(scenes_data) if USE_DRAMATIC_SILENCE else []
    )
    if dramatic_events:
        labels = ", ".join(
            f"{event['word']}@{event['time']:.2f}s" for event in dramatic_events
        )
        print(f"   🔇 Ruptures dramatiques : {labels}")
    compile_sfx_composite(
        projet_dir,
        total,
        all_woosh_timestamps,
        all_glitch_timestamps,
        all_boom_timestamps,
        scenes_data,
        dramatic_events=dramatic_events,
    )
    mix_audio_post_render(
        projet_dir,
        renders[-1],
        final,
        scenes_data,
        total,
        dramatic_events=dramatic_events,
    )
    print(f"\n✅ Final : {final}  ({final.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--projet", help="Chemin du projet (défaut: dernier)")
    ap.add_argument("--check", action="store_true", help="Lint + validate avant render")
    ap.add_argument(
        "--prepare-only",
        action="store_true",
        help="Écrit la composition HyperFrames sans lancer le rendu vidéo",
    )
    args = ap.parse_args()

    projet = args.projet or trouver_dernier_projet()
    if not projet:
        raise SystemExit("Aucun projet trouvé.")
    render_projet(
        projet,
        do_check=args.check,
        prepare_only=args.prepare_only,
    )
