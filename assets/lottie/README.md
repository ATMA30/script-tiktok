# Lottie overlay system

Layer of motion-graphic accents (radar pings, scanlines, redacted bars, glitch
bursts, vignette pulses…) that the **Director Agent** can choose to drop on top
of each scene at the render step. Powered by [`@lottiefiles/dotlottie-wc`](https://github.com/LottieFiles/dotlottie-web)
(which itself wraps [ThorVG](https://github.com/thorvg/thorvg) — both researched
before building this).

## Directory layout

```
assets/lottie/
  ├── library/                      # one .json per animation (Bodymovin v5.x)
  ├── vendor/                       # self-hosted dotlottie-wc runtime + WASM
  │   ├── dotlottie-wc.js           # ESM entry, loaded once per render
  │   ├── dist-CDsU-l1k.js          # engine chunk (321 KB)
  │   ├── base-dotlottie-wc.js
  │   ├── decorate-C0oFmnNg.js
  │   └── dotlottie-player.wasm     # ThorVG-WASM core (1.7 MB)
  ├── manifest.json                 # catalog read by the renderer + briefed to Gemini
  ├── curated_sources.json          # URL list consumed by curate_library.py
  ├── curate_library.py             # downloads + monochromes + registers external Lotties
  ├── generate_starter_library.py   # regenerates the procedural starter assets
  └── README.md                     # you are here
```

## How it works

1. **Manifest** — each `.json` in `library/` has a matching entry in
   `manifest.json` with `id`, `tags`, `default_blend`, `default_opacity`,
   `natural_duration_s`, `looping`, `description`.
2. **Director Agent** (in `usine/render/director.py`) receives the catalog in
   its prompt and may emit a `lottie_overlays` array per scene: `asset_id`,
   `in_time` (scene-relative), `duration`, `x/y/width/height_pct`, `opacity`,
   `monochrome`, `reason`.
3. **Renderer** (`usine/render/lottie.py`) clamps the spec, emits a
   `<dotlottie-wc>` element + GSAP tweens that drive `setFrame()` on every
   `onUpdate` for frame-accurate playback under headless Chrome capture.
4. **HyperFrames** captures the page frame by frame; the entire Lottie playhead
   is deterministic.

## Add a new asset

Three routes:

### A. Curated download via `curate_library.py` (recommended)
1. Find a public Lottie URL (see "Finding URLs" below).
2. Add an entry to `curated_sources.json` under `"sources"`:
   ```json
   {
     "url": "https://lottie.host/UUID/evidence-pin.json",
     "id": "evidence_pin",
     "tags": ["evidence", "pin", "thread", "investigation"],
     "description": "Red string pinned across an evidence board.",
     "natural_duration_s": 2.4,
     "looping": false,
     "default_blend": "normal",
     "default_opacity": 0.95,
     "monochrome": "full"
   }
   ```
3. Run `python assets/lottie/curate_library.py`. The script downloads, flattens
   colors to monochrome (cinema noir palette), and registers the asset in
   `manifest.json`. Re-runs are idempotent; add `"force": true` to refresh.

### B. Manual drop-in
Drop a `.json` (Bodymovin) or `.lottie` (ZIP) into `library/` and add an entry
to `manifest.json` by hand. Useful for hand-edited / paid assets you don't
want re-downloaded.

### C. Procedural (Python-generated)
Add a `make_your_asset()` function in `generate_starter_library.py`, register
it in `ASSETS`, re-run the script. Easier for simple geometric primitives
(sweeps, bars, rings) than for hand-drawn motion.

## Finding URLs (LottieFiles MCP)

The community-built **`mcp-server-lottiefiles`** by junmer exposes the
LottieFiles catalog as MCP tools (`search_animations`, `get_animation_details`,
`get_popular_animations`). To enable it for Claude Code, add this block to your
`~/.claude.json` (or whichever Claude MCP config file your client reads):

```json
{
  "mcpServers": {
    "lottiefiles": {
      "command": "npx",
      "args": ["-y", "mcp-server-lottiefiles"]
    }
  }
}
```

Restart Claude. You can then ask Claude to search the catalog ("find me 5
glitch/scanline animations under 100 KB") and it will return CDN URLs you can
paste into `curated_sources.json`.

Direct URL patterns that work without auth:
- `https://assets{1-10}.lottiefiles.com/packages/lf20_<id>.json`
- `https://lottie.host/<uuid>/<name>.json`
- `https://raw.githubusercontent.com/<user>/<repo>/.../some.json`

Repo: <https://github.com/junmer/mcp-server-lottiefiles>

## Tuning

Per-render env vars (all in `usine/render/config.py`):
- `USE_DIRECTOR_AGENT=0` — skip Gemini, also skips Lottie overlay choice.
- `USE_DIRECTOR_AGENT=1` (default with `GEMINI_API_KEY`) — Director picks
  0-3 overlays per scene from the manifest.

The runtime is self-hosted in `vendor/`. To refresh / bump the version:
```bash
cd assets/lottie/vendor
rm -f *.js *.wasm
npm pack @lottiefiles/dotlottie-wc@<NEW_VERSION>
tar -xzf lottiefiles-dotlottie-wc-*.tgz
mv package/dist/*.js .
# Find the wasm version expected by the new bundle:
grep -oE 'u=`[0-9.]+`' dist-*.js   # → @lottiefiles/dotlottie-web@<wasm_ver>
curl -LO "https://cdn.jsdelivr.net/npm/@lottiefiles/dotlottie-web@<wasm_ver>/dist/dotlottie-player.wasm"
rm -rf package *.tgz
```

Then update the imported chunk name inside `usine/render/lottie.py` → `lottie_head_html()`
(the `dist-XXX.js` filename hash changes between versions).

## Known limits

- **Fonts** — Lottie text layers need fonts installed. Convert text to shapes
  in After Effects before exporting, or skip text overlays entirely (use HTML
  text instead, which we already do).
- **`<filter>` SVG tags** — ThorVG ignores them. If your Lottie uses Gaussian
  blur via filter, bake the blur into the export or accept the difference.
- **Async load race** — the wc may not be `ready` on the very first frame at
  `t=0`. Overlays scheduled in the first 100 ms of the timeline may flicker.
  Push them to at least 0.2 s if they matter.
- **Determinism** — we explicitly set `use-frame-interpolation="false"` and
  drive playback by `setFrame()` from GSAP. Do NOT switch on autoplay or the
  capture becomes wall-clock dependent.
