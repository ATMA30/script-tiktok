"""Director : accents Lottie déterministes et Director Agent Gemini (optionnel)."""

import json
from google.genai import types
from usine.render.lottie import (
    build_lottie_overlays_for_scene,
    load_manifest as load_lottie_manifest,
    manifest_choices_summary as lottie_choices_summary,
)
from usine.render.camera import (
    build_image_block,
    build_procedural_bg,
    build_scene_director_fx,
)
from usine.render.config import FPS, HEIGHT, USE_LOTTIE_OVERLAYS, WIDTH, gemini_client
from usine.render.models import SceneDirectorPlan
from usine.render.text import _normalize_word


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
        print(f"   🎞️  Lottie Yūrei : {[spec['asset_id'] for spec in specs]}")
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
