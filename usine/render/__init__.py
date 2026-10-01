"""
Render final TikTok video from script.json + audios + images using HyperFrames.

Style : documentaire true crime / faits divers (DESIGN.md)
- Ken Burns 3D (perspective + dolly/orbit/tilt par scène)
- Overlays documentaires déterministes : carte, année, dossier, compteur
- Hook en fondu, carte « HISTOIRE VRAIE », CTA d'abonnement final
- Sous-titres avec mots clés en rouge, logo Yūrei discret
- Film grain + vignette cinématique, pas de HUD caméscope

Headless (Puppeteer + Chromium) — CI-friendly. No browser GUI opens.
"""
