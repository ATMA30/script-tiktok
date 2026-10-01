"""Document HTML HyperFrames complet (styles, runtime GSAP, scènes)."""

import re
import textwrap
from pathlib import Path

from usine.render.lottie import lottie_head_html
from usine.render.cards import (
    _dust_motes_html,
    _dust_motes_js,
    _persistent_case_tag_html,
    build_flash_transitions,
)
from usine.render.config import (
    HEIGHT,
    SCROLL_HOOK_TEXT,
    USE_BRAND_LOGO,
    USE_BREATHING_VIGNETTE,
    USE_FILM_GRAIN,
    USE_LETTERBOX,
    USE_LOTTIE_OVERLAYS,
    USE_SCROLL_HOOK,
    WIDTH,
)
from usine.render.text import html_escape


_STYLES_PATH = Path(__file__).parent / "templates" / "styles.css"


def _styles_css():
    """CSS du document (templates/styles.css), indenté pour s'insérer dans <style>.

    Les jetons @@WIDTH@@ et @@HEIGHT@@ sont remplacés par la taille de la frame.
    """
    css = _STYLES_PATH.read_text(encoding="utf-8")
    css = css.replace("@@WIDTH@@", str(WIDTH)).replace("@@HEIGHT@@", str(HEIGHT))
    return textwrap.indent(css, " " * 6)


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
{_styles_css()}    </style>
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
