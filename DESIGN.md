# Yurei Video Design System

## Identity

- Format: vertical 1080x1920, 30 fps.
- Mood: true crime / faits divers documentary, restrained dread, credible facts.
- Real people: no recognizable face of a real person; show places, objects,
  silhouettes, hands, empty courtrooms (see the legal rules in `usine/garde_fous.py`).
- Visual language: cinematic low-poly 3D, wet roads, fog, deep shadows.
- Avoid: VHS, camcorder HUD, decorative glitch spam, bright fantasy colors.

## Palette

- Background black: `#050505`
- Cold shadow: `#101b24`
- Primary text: `#ffffff`
- Muted text: `#a7adb4`
- Yurei red: `#ff3838`
- Red is reserved for key words, evidence links, and reveal impacts.

## Typography

- Captions: Oswald ExtraBold, centered, 64 px, line-height 1.06.
- Display cards: League Gothic or Bebas Neue.
- Letter spacing: 0 for captions; modest positive spacing only for labels.
- Captions stay above the lowest 15% of the frame.

## Motion

- Images use continuous 2.5D push, pan, or orbit motion.
- Prefer transforms and opacity; never animate layout dimensions.
- Rhythm: tension build, brief hold, hard reveal, recovery.
- Revelation effects last under 0.7 seconds.
- No effect may compete with the face, primary object, or active caption.

## Lottie

- Off by default (`USE_LOTTIE_OVERLAYS=0`); true crime relies on documentary
  overlays (map, year, file, counter) instead.
- If a story ever needs it, the custom `yurei_mirror_manifestation` signature:
  a faceless white figure, a brief red fracture, then spectral evaporation.
- Place it only when an apparition or disappearance is explicitly narrated.
- Keep it inside the physical surface where the event occurs: mirror, window,
  doorway, or dark background plane.
- Lottie layers remain below captions and are scrubbed deterministically.
- Do not use generic loaders, radar, magnifiers, investigation HUDs, or
  decorative Lotties (this is why `USE_PERSISTENT_CASE_TAG` stays off).

## Brand

- Keep the Yurei logo in the upper-right safe area at low opacity.
- First-frame hook occupies the upper-left safe area.
- A short « HISTOIRE VRAIE » card follows the hook (0.8 s).
- End every social version with a 1.5 to 1.8 second subscription CTA.

## Audio

- Final target: -14 LUFS integrated.
- True peak: at or below -1 dBFS.
- Stress music is present but sidechain-ducked under narration.
- Cut music before major disappearance words, then land a dry low sting.
