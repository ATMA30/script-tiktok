"""
lottie_overlay.py — bridge between the Lottie library and the HyperFrames render.

Responsibilities:
  - Load assets/lottie/manifest.json once per render
  - Expose `build_lottie_overlay_block(spec, scene_idx, master_id)` which emits
    the HTML + JS fragments for a lottie-web instance synced to the GSAP
    master timeline
  - Provide `lottie_head_html()` for the page <head> CDN script tag
  - Provide `validate_overlay_spec()` which clamps untrusted (LLM-produced)
    overlay specs into safe bounds before they reach the renderer

Design choices:
  * lottie-web is loaded once as a classic script from a pinned CDN URL,
    which remains compatible with HyperFrames 0.5.7's script validation.
    Animation JSON is embedded directly into the generated page.
  * Each overlay is driven by a GSAP tween that calls setFrame() on every
    onUpdate. This is deterministic under HyperFrames' CDP-driven capture,
    unlike letting the player autoplay against wall-clock.
  * Monochrome by default — applies a CSS grayscale+contrast filter to keep
    the overlay coherent with our cinema 35mm true-crime palette.
"""

import json
import os
from pathlib import Path
from typing import Optional

_MANIFEST_CACHE: Optional[dict] = None
_MANIFEST_PATH = Path(__file__).parent / "assets" / "lottie" / "manifest.json"
_LOTTIE_WEB_CDN = (
    "https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js"
)


def load_manifest() -> dict:
    """Returns {'version': int, 'assets': [...]}, cached per process.

    Empty manifest if the file is missing — the render must still work.
    """
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    if not _MANIFEST_PATH.exists():
        _MANIFEST_CACHE = {"version": 1, "assets": []}
        return _MANIFEST_CACHE
    try:
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
            _MANIFEST_CACHE = json.load(f)
    except Exception:
        _MANIFEST_CACHE = {"version": 1, "assets": []}
    return _MANIFEST_CACHE


def manifest_asset(asset_id: str) -> Optional[dict]:
    for a in load_manifest().get("assets", []):
        if a.get("id") == asset_id:
            return a
    return None


def lottie_head_html() -> str:
    """Charge lottie-web en script classique, compatible HyperFrames 0.5.7."""
    if not load_manifest().get("assets"):
        return ""
    return (
        f'<script src="{_LOTTIE_WEB_CDN}"></script>\n'
    )


def asset_animation_data(asset_id: str) -> Optional[dict]:
    asset = manifest_asset(asset_id)
    if not asset:
        return None
    path = _MANIFEST_PATH.parent / asset["file"]
    if not path.exists() or path.suffix.lower() != ".json":
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def asset_url(asset_id: str) -> Optional[str]:
    """Relative asset URL used for validation and render packaging."""
    a = manifest_asset(asset_id)
    if not a:
        return None
    return f"assets/lottie/{a['file']}"


def validate_overlay_spec(raw: dict) -> Optional[dict]:
    """Clamp untrusted spec into safe bounds. Returns None if unusable.

    Expected keys (all optional except asset_id and in_time):
        asset_id      str    — must match a manifest entry
        in_time       float  — absolute seconds on the master timeline (>= 0)
        duration      float  — playback duration, defaults to natural_duration_s
        x_pct, y_pct  float  — anchor center, 0..100, defaults to 50/50
        width_pct     float  — 1..120 (allow slight over-frame), default 100
        height_pct    float  — 1..120, default = width_pct * aspect (16:9 portrait)
        opacity       float  — 0..1, default = asset.default_opacity
        blend_mode    str    — CSS mix-blend-mode, default = asset.default_blend
        monochrome    bool   — default True
        reason        str    — optional, ignored at runtime
    """
    if not isinstance(raw, dict):
        return None
    aid = raw.get("asset_id")
    asset = manifest_asset(aid) if aid else None
    if not asset:
        return None

    def clamp(v, lo, hi, default):
        try:
            x = float(v)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, x))

    in_time = clamp(raw.get("in_time"), 0.0, 600.0, 0.0)
    duration = clamp(
        raw.get("duration", asset["natural_duration_s"]),
        0.1, 30.0,
        asset["natural_duration_s"],
    )
    x_pct = clamp(raw.get("x_pct"), -20.0, 120.0, 50.0)
    y_pct = clamp(raw.get("y_pct"), -20.0, 120.0, 50.0)
    width_pct = clamp(raw.get("width_pct"), 1.0, 120.0, 100.0)
    height_pct = clamp(raw.get("height_pct"), 1.0, 120.0, width_pct)
    opacity = clamp(raw.get("opacity", asset["default_opacity"]), 0.0, 1.0,
                    asset["default_opacity"])

    blend_mode = str(raw.get("blend_mode", asset["default_blend"]))
    # mix-blend-mode whitelist; fall back to default on unknown values.
    valid_blends = {
        "normal", "multiply", "screen", "overlay", "darken", "lighten",
        "color-dodge", "color-burn", "hard-light", "soft-light",
        "difference", "exclusion", "hue", "saturation", "color", "luminosity",
    }
    if blend_mode not in valid_blends:
        blend_mode = asset["default_blend"]

    monochrome = bool(raw.get("monochrome", True))

    return {
        "asset_id": aid,
        "in_time": in_time,
        "duration": duration,
        "x_pct": x_pct,
        "y_pct": y_pct,
        "width_pct": width_pct,
        "height_pct": height_pct,
        "opacity": opacity,
        "blend_mode": blend_mode,
        "monochrome": monochrome,
        "reason": str(raw.get("reason", ""))[:200],
    }


def build_lottie_overlay_block(
    spec: dict,
    scene_idx: int,
    overlay_idx: int,
    parent_z: int = 500,
    frame_w: int = 1080,
    frame_h: int = 1920,
    fps: int = 30,
) -> tuple[list[str], list[str]]:
    """Generate (html_lines, js_lines) for a single Lottie overlay.

    The returned strings can be appended directly to the render's html_parts
    and js_parts lists. The element fades in at `in_time`, scrubs through
    its frames over `duration`, then fades out.
    """
    aid = spec["asset_id"]
    url = asset_url(aid)
    if not url:
        return [], []
    asset = manifest_asset(aid)
    if not asset:
        return [], []

    el_id = f"lo_s{scene_idx + 1}_{aid}_{overlay_idx}"
    t_in = float(spec["in_time"])
    dur = float(spec["duration"])
    t_out = t_in + dur
    fade = min(0.08, dur * 0.15)

    w_px = int(round(frame_w * spec["width_pct"] / 100.0))
    h_px = int(round(frame_h * spec["height_pct"] / 100.0))
    # CSS positions the element by its center; convert pct to top/left pixels.
    left_px = int(round(frame_w * spec["x_pct"] / 100.0 - w_px / 2))
    top_px = int(round(frame_h * spec["y_pct"] / 100.0 - h_px / 2))

    filter_css = (
        "grayscale(1) contrast(1.1) brightness(0.92)" if spec["monochrome"] else "none"
    )

    style = (
        f"position:absolute;left:{left_px}px;top:{top_px}px;"
        f"width:{w_px}px;height:{h_px}px;"
        f"opacity:0;pointer-events:none;"
        f"mix-blend-mode:{spec['blend_mode']};"
        f"filter:{filter_css};"
        f"z-index:{parent_z + overlay_idx};"
        f"will-change:opacity,transform;"
    )

    animation_data = asset_animation_data(aid)
    if not animation_data:
        return [], []
    # Scrub in the animation's native frame space. The authored Lottie may use
    # 60 fps while the HyperFrames composition runs at 30 fps.
    natural_frames = max(
        1,
        int(
            round(
                float(animation_data.get("op", 1))
                - float(animation_data.get("ip", 0))
            )
        ),
    )
    animation_json = json.dumps(animation_data, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    anim_var = f"__anim_{el_id}"

    html_lines = [
        f'<div id="{el_id}" class="lottie-overlay clip" '
        f'data-start="{t_in:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{800 + scene_idx * 5 + overlay_idx}" '
        f'style="{style}"></div>'
    ]

    head_var = f"__h_{el_id}"
    native_goto_var = f"__native_goto_{el_id}"
    seek_var = f"__hf_seek_{el_id}"
    time_var = f"__hf_time_{el_id}"
    js_lines = [
        f'var {anim_var} = lottie.loadAnimation({{'
        f'container: document.getElementById("{el_id}"), '
        f'renderer: "svg", loop: false, autoplay: false, '
        f'animationData: {animation_json}, '
        f'rendererSettings: {{preserveAspectRatio: "xMidYMid meet"}}'
        f'}});',
        # HyperFrames auto-discovers the native lottie-web instance and seeks it
        # in global milliseconds. Teach that same instance how to map global
        # composition time into this overlay's local authored frame range.
        f'var {native_goto_var} = {anim_var}.goToAndStop.bind({anim_var});',
        f'{anim_var}.goToAndStop = function(value, isFrame) {{'
        f'if (isFrame) return {native_goto_var}(value, true); '
        f'var globalSeconds = Number(value) / 1000; '
        f'var progress = Math.max(0, Math.min(1, '
        f'(globalSeconds - {t_in:.6f}) / {dur:.6f})); '
        f'return {native_goto_var}(progress * {natural_frames - 1}, true);'
        f'}};',
        f'window.__hfLottie = window.__hfLottie || [];',
        f'window.__hfLottie.push({anim_var});',
        f'var {seek_var} = tl.seek;',
        f'tl.seek = function(position, suppressEvents) {{ '
        f'var result = {seek_var}.call(this, position, suppressEvents); '
        f'var seconds = Number(position); '
        f'if (Number.isFinite(seconds)) '
        f'{{ {anim_var}.goToAndStop(seconds * 1000, false); }} '
        f'return result; '
        f'}};',
        f'var {time_var} = tl.time;',
        f'tl.time = function(value, suppressEvents) {{ '
        f'if (arguments.length === 0) return {time_var}.call(this); '
        f'var result = {time_var}.call(this, value, suppressEvents); '
        f'var seconds = Number(value); '
        f'if (Number.isFinite(seconds)) '
        f'{{ {anim_var}.goToAndStop(seconds * 1000, false); }} '
        f'return result; '
        f'}};',
        # Static fade in/out keyed on master timeline.
        f'gsap.set("#{el_id}", {{opacity: 0}});',
        f'tl.to("#{el_id}", {{opacity: {spec["opacity"]:.3f}, duration: {fade:.3f}, ease: "power1.out"}}, {t_in:.3f});',
        f'tl.to("#{el_id}", {{opacity: 0, duration: {fade:.3f}, ease: "power1.in"}}, {max(t_in, t_out - fade):.3f});',
        # Frame scrubbing.
        f'var {head_var} = {{f: 0}};',
        f'tl.fromTo({head_var}, {{f: 0}}, {{f: {natural_frames - 1}, '
        f'duration: {dur:.3f}, ease: "none", '
        f'onUpdate: function() {{ if ({anim_var}) '
        f'{{ {anim_var}.goToAndStop({head_var}.f, true); }} }} '
        f'}}, {t_in:.3f});',
    ]
    return html_lines, js_lines


def build_lottie_overlays_for_scene(
    specs: list[dict],
    scene_idx: int,
    frame_w: int = 1080,
    frame_h: int = 1920,
    fps: int = 30,
) -> tuple[list[str], list[str]]:
    """Build the HTML + JS for every overlay attached to a single scene."""
    html_all: list[str] = []
    js_all: list[str] = []
    for i, raw in enumerate(specs):
        clean = validate_overlay_spec(raw)
        if not clean:
            continue
        h, j = build_lottie_overlay_block(
            clean, scene_idx, i, frame_w=frame_w, frame_h=frame_h, fps=fps
        )
        html_all.extend(h)
        js_all.extend(j)
    return html_all, js_all


def manifest_choices_summary() -> str:
    """Compact textual catalog used to brief the Director Agent prompt."""
    items = load_manifest().get("assets", [])
    if not items:
        return "(no Lottie assets available)"
    lines = []
    for a in items:
        tags = ", ".join(a.get("tags", [])[:6])
        lines.append(
            f"- {a['id']} ({a['natural_duration_s']:.1f}s, "
            f"{'loopable' if a.get('looping') else 'one-shot'}): "
            f"{a.get('description', '')} | tags: {tags}"
        )
    return "\n".join(lines)
