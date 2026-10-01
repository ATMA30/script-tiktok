"""Cartes plein écran et décor global : intro, carte vérité, CTA, transitions, poussières, tag dossier."""

import hashlib
from usine.render.config import (
    DISABLE_SCENE_TRANSITIONS,
    USE_HOOK_INTRO,
    USE_OUTRO_CTA,
    USE_PERSISTENT_CASE_TAG,
)
from usine.render.overlays.detection import _fold_text, _has_keyword
from usine.render.text import html_escape


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
