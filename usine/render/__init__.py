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
