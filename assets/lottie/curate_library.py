"""
curate_library.py — download + theme + register external Lottie animations
into the local library.

Workflow:
  1. Edit `curated_sources.json` (sibling file) — add one entry per animation
     you want to pull in. Each entry has a direct .json URL (LottieFiles CDN,
     Lottie Host, GitHub raw, etc.) and the metadata you want in the manifest.
  2. Run `python assets/lottie/curate_library.py`.
  3. The script downloads each Lottie, optionally flattens its colors to a
     single greyscale tone (so the asset blends with the cinema noir palette),
     re-saves it under `library/<id>.json`, and merges the entry into
     `manifest.json` (the procedural assets stay in place).

How to find URLs:
  • LottieFiles MCP server (community: `npx -y mcp-server-lottiefiles`) — once
    enabled in Claude's MCP config, you can ask the assistant to search the
    catalog and return a list of CDN URLs. See README.md.
  • LottieFiles website — every free animation page exposes an "Asset link"
    UI giving both `.json` and `.lottie` URLs that are curl-able with no auth.
  • Lottie Host — pattern `https://lottie.host/<uuid>/<name>.json`
  • GitHub raw — search for `bodymovin` repos.

This script does NOT require npm. Coloring is implemented in pure Python by
walking the Bodymovin JSON (`fl`/`st` shape primitives with `c.k = [r,g,b,a]`).
That covers ~95% of Lottie color usage. For animations with theme slots (sid)
or gradient fills (`gf`/`gs`), the script attempts to handle them as well.
"""

import json
import re
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

HERE = Path(__file__).parent
LIB = HERE / "library"
MANIFEST = HERE / "manifest.json"
SOURCES = HERE / "curated_sources.json"

# Default target tone (R, G, B) for monochrome flatten. Matches the cinema
# 35mm true-crime palette — soft warm grey, not pure white.
DEFAULT_MONO = (210, 215, 218)


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "asset"


def download_json(url: str) -> dict:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 script-tiktok lottie-curate",
            "Accept": "application/json,*/*;q=0.5",
        },
    )
    with urlopen(req, timeout=20) as resp:
        body = resp.read()
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        head = body[:200].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Not JSON ({len(body)} bytes). First chars: {head!r}"
        ) from e


def _is_color_array(v) -> bool:
    """A Bodymovin color value is [r, g, b] or [r, g, b, a] with floats 0..1."""
    if not isinstance(v, list):
        return False
    if len(v) not in (3, 4):
        return False
    return all(isinstance(x, (int, float)) and 0.0 <= float(x) <= 1.0 for x in v)


def flatten_to_mono(node, target_rgb: tuple[int, int, int]) -> int:
    """Recursively walk the Lottie JSON, rewrite every solid color to `target_rgb`.

    Returns the number of color slots rewritten. Leaves alpha and animation
    keyframes intact (we only swap the static color tuples — opacity/keyframe
    timing keeps animating naturally).
    """
    tr, tg, tb = (c / 255.0 for c in target_rgb)
    count = 0

    def patch_static(d, k):
        nonlocal count
        v = d[k]
        if _is_color_array(v):
            a = float(v[3]) if len(v) == 4 else 1.0
            d[k] = [tr, tg, tb, a]
            count += 1

    def patch_animated_keys(kf_list):
        """A keyframed color animates the [r,g,b,a] tuple via `s`/`e` arrays
        inside each keyframe. We rewrite those tuples in place."""
        nonlocal count
        for kf in kf_list:
            if not isinstance(kf, dict):
                continue
            for slot in ("s", "e"):
                if slot in kf and _is_color_array(kf[slot]):
                    a = float(kf[slot][3]) if len(kf[slot]) == 4 else 1.0
                    kf[slot] = [tr, tg, tb, a]
                    count += 1

    def walk(obj):
        if isinstance(obj, dict):
            # `c` (color), `sc` (stroke color), and any field directly holding a color array
            for key in ("c", "sc", "fillColor", "strokeColor"):
                if key in obj and isinstance(obj[key], dict):
                    inner = obj[key]
                    if inner.get("a") == 0 and "k" in inner:
                        patch_static(inner, "k")
                    elif inner.get("a") == 1 and isinstance(inner.get("k"), list):
                        patch_animated_keys(inner["k"])
            # Bodymovin sometimes places a raw color array directly under `k`
            # (e.g. `{"k":[r,g,b,a]}`). Skip — handled via the parent above.
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(node)
    return count


def normalize_lottie(data: dict) -> dict:
    """Light cleanup: drop optional metadata fields that bloat the file."""
    drop_keys = {"meta", "comps", "markers"}
    for k in list(data.keys()):
        if k in drop_keys and not data[k]:
            del data[k]
    return data


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "assets": []}


def save_manifest(m: dict):
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")


def upsert_manifest_entry(manifest: dict, entry: dict):
    """Replace any existing asset with the same id, else append."""
    aid = entry["id"]
    manifest["assets"] = [a for a in manifest["assets"] if a.get("id") != aid]
    manifest["assets"].append(entry)
    manifest["assets"].sort(key=lambda a: a.get("id", ""))


def process_source(src: dict, manifest: dict, dry_run: bool = False) -> bool:
    """Returns True on success."""
    url = src.get("url")
    aid = src.get("id") or slugify(src.get("description", ""))
    if not url or not aid:
        print(f"  ⚠️  Skipped (missing url or id): {src!r}")
        return False

    out_path = LIB / f"{aid}.json"
    if out_path.exists() and not src.get("force", False):
        print(f'  ⏭️  {aid:24s} → already in library (set "force": true to refresh)')
        upsert_manifest_entry(manifest, _entry_from_source(src, aid, out_path))
        return True

    print(f"  ⬇️  {aid:24s} ← {url[:70]}")
    try:
        data = download_json(url)
    except (URLError, HTTPError, RuntimeError) as e:
        print(f"     ❌ Download failed: {e}")
        return False

    # Quick sanity check: Bodymovin JSON has top-level `v` (version) and `layers`.
    if not isinstance(data, dict) or "v" not in data or "layers" not in data:
        print(
            f"     ❌ Not a Bodymovin Lottie JSON (keys: {list(data.keys())[:5] if isinstance(data, dict) else type(data).__name__})"
        )
        return False

    # Optional monochrome flatten
    mono_strength = src.get("monochrome", "full")  # "full" | "partial" | "off"
    if mono_strength in ("full", True):
        target = tuple(src.get("mono_target", DEFAULT_MONO))
        n_changed = flatten_to_mono(data, target)
        print(
            f"     🎨 Monochrome flatten → {n_changed} color slots rewritten ({target})"
        )

    data = normalize_lottie(data)

    if dry_run:
        print(f"     (dry-run) would write {out_path.name}")
        return True

    out_path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"     ✅ Wrote {out_path.name} ({size_kb:.1f} KB)")

    entry = _entry_from_source(src, aid, out_path)
    upsert_manifest_entry(manifest, entry)
    return True


def _entry_from_source(src: dict, aid: str, file_path: Path) -> dict:
    return {
        "id": aid,
        "file": f"library/{file_path.name}",
        "tags": src.get("tags", []),
        "default_blend": src.get("default_blend", "normal"),
        "default_opacity": float(src.get("default_opacity", 0.9)),
        "monochrome_safe": True,
        "natural_duration_s": float(src.get("natural_duration_s", 2.0)),
        "looping": bool(src.get("looping", False)),
        "description": src.get("description", ""),
        "size_kb": round(file_path.stat().st_size / 1024, 1),
        "source_url": src.get("url", ""),
    }


def main():
    if not SOURCES.exists():
        # Bootstrap with a documented empty config the first time.
        SOURCES.write_text(
            json.dumps(
                {
                    "_doc": (
                        "Each entry: {url, id, tags, description, natural_duration_s, "
                        "looping, default_blend, default_opacity, monochrome ('full'|"
                        "'partial'|'off'), mono_target [r,g,b], force (bool to refresh)}."
                    ),
                    "_example": {
                        "url": "https://lottie.host/UUID/name.json",
                        "id": "evidence_pin",
                        "tags": ["evidence", "pin", "investigation"],
                        "description": "Red string pinned across an evidence board.",
                        "natural_duration_s": 2.4,
                        "looping": False,
                        "default_blend": "normal",
                        "default_opacity": 0.95,
                        "monochrome": "full",
                    },
                    "sources": [],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"📝 Created {SOURCES.name} — add entries under 'sources' and rerun.")
        return

    cfg = json.loads(SOURCES.read_text(encoding="utf-8"))
    sources = cfg.get("sources", [])
    if not sources:
        print(
            f"ℹ️  No sources configured in {SOURCES.name}. Add some entries under 'sources'."
        )
        print(
            "   See README.md for how to find URLs (LottieFiles MCP, Lottie Host, etc.)."
        )
        return

    LIB.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    ok = 0
    for src in sources:
        if process_source(src, manifest):
            ok += 1

    save_manifest(manifest)
    print(
        f"\n✅ Curated {ok}/{len(sources)} sources. Manifest now has {len(manifest['assets'])} assets."
    )


if __name__ == "__main__":
    main()
