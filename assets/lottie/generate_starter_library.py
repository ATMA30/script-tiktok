"""
generate_starter_library.py — generates a small starter library of Lottie animations
procedurally (Bodymovin JSON format), so the pipeline has something to render the
first time without depending on external downloads.

The animations are deliberately simple geometric motion graphics that look good
in a true-crime / paranormal aesthetic: scanline sweeps, redacted bars, vignette
pulses, radar pings, crosshair scans. They are meant as a *baseline*. The user is
expected to later replace or augment them with curated .lottie files from
LottieFiles, Lordicon, or hand-designed After Effects exports.

Run once:
    python assets/lottie/generate_starter_library.py

It writes:
    assets/lottie/library/<name>.json     (one Bodymovin file per asset)
    assets/lottie/manifest.json           (catalog used by the renderer)
"""

import json
import os
from pathlib import Path

HERE = Path(__file__).parent
LIB = HERE / "library"
LIB.mkdir(parents=True, exist_ok=True)

# Reference frame size used by all clips. The renderer scales to whatever
# CSS box the <dotlottie-wc> element gets — these dimensions only matter
# internally to keep proportions consistent.
W, H = 1080, 1920


def lottie_skeleton(name: str, fps: int, duration_frames: int, layers: list) -> dict:
    """Return a minimal Bodymovin v5.x JSON envelope around a list of layers."""
    return {
        "v": "5.7.4",
        "fr": fps,
        "ip": 0,
        "op": duration_frames,
        "w": W,
        "h": H,
        "nm": name,
        "ddd": 0,
        "assets": [],
        "layers": layers,
        "markers": [],
        "meta": {"g": "script-tiktok procedural"},
    }


def shape_layer(nm: str, in_frame: int, out_frame: int, shapes: list,
                transform: dict | None = None) -> dict:
    """Return a 'shape' layer (type 4) with the given child shapes."""
    return {
        "ddd": 0,
        "ind": 1,
        "ty": 4,
        "nm": nm,
        "ip": in_frame,
        "op": out_frame,
        "st": 0,
        "sr": 1,
        "bm": 0,
        "ks": transform or default_transform(),
        "shapes": shapes,
    }


def default_transform(x=W / 2, y=H / 2, opacity=100, scale=100) -> dict:
    return {
        "o": {"a": 0, "k": opacity},
        "r": {"a": 0, "k": 0},
        "p": {"a": 0, "k": [x, y, 0]},
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {"a": 0, "k": [scale, scale, 100]},
    }


def color(r, g, b, a=1.0):
    return [r / 255.0, g / 255.0, b / 255.0, a]


def rect_shape(w: float, h: float, fill_rgba: list, opacity: float = 100) -> list:
    """Helper that builds the list of sub-shapes for a filled rectangle."""
    return [
        {
            "ty": "rc",
            "d": 1,
            "s": {"a": 0, "k": [w, h]},
            "p": {"a": 0, "k": [0, 0]},
            "r": {"a": 0, "k": 0},
            "nm": "Rect",
        },
        {
            "ty": "fl",
            "c": {"a": 0, "k": fill_rgba[:3] + [1.0]},
            "o": {"a": 0, "k": opacity * fill_rgba[3]},
            "r": 1,
            "nm": "Fill",
        },
    ]


def keyframe(t: int, value) -> dict:
    """Linear keyframe at frame `t` with `value`."""
    return {"t": t, "s": value if isinstance(value, list) else [value]}


# ─────────────────────────────────────────────────────────────────────────────
#  1. SCANLINE SWEEP — fine bright horizontal line sweeps top → bottom
# ─────────────────────────────────────────────────────────────────────────────
def make_scanline_sweep() -> dict:
    fps, dur = 30, 60  # 2 s loopable sweep
    line_h = 18  # was 6 — bolder so it survives screen blend on dark frames
    transform = {
        "o": {
            "a": 1, "k": [
                {"t": 0,        "s": [0]},
                {"t": 4,        "s": [100]},
                {"t": dur - 4,  "s": [100]},
                {"t": dur,      "s": [0]},
            ]
        },
        "r": {"a": 0, "k": 0},
        "p": {
            "a": 1, "k": [
                {"t": 0,    "s": [W / 2, -line_h, 0]},
                {"t": dur,  "s": [W / 2, H + line_h, 0]},
            ]
        },
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {"a": 0, "k": [100, 100, 100]},
    }
    # Soft glow underlay (wider, fainter) + bright core line
    glow_shapes = rect_shape(W, line_h * 4, color(255, 255, 255, 0.35))
    core_shapes = rect_shape(W, line_h, color(255, 255, 255, 1.0))
    layer = shape_layer(
        "scanline", 0, dur,
        [
            {"ty": "gr", "it": glow_shapes, "nm": "Glow"},
            {"ty": "gr", "it": core_shapes, "nm": "Core"},
        ],
        transform,
    )
    return lottie_skeleton("scanline_sweep", fps, dur, [layer])


# ─────────────────────────────────────────────────────────────────────────────
#  2. REDACTED BAR — black bar slides in from the left, then a quick tear
# ─────────────────────────────────────────────────────────────────────────────
def make_redacted_bar() -> dict:
    fps, dur = 30, 45  # 1.5 s
    bar_w = 720
    bar_h = 64
    transform = {
        "o": {
            "a": 1, "k": [
                {"t": 0,        "s": [0]},
                {"t": 6,        "s": [100]},
                {"t": dur - 6,  "s": [100]},
                {"t": dur,      "s": [0]},
            ]
        },
        "r": {"a": 0, "k": 0},
        "p": {
            "a": 1, "k": [
                {"t": 0,    "s": [-bar_w / 2, H / 2, 0]},
                {"t": 10,   "s": [W / 2,      H / 2, 0]},
                {"t": dur - 10, "s": [W / 2,  H / 2, 0]},
                {"t": dur,  "s": [W + bar_w / 2, H / 2, 0]},
            ]
        },
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {"a": 0, "k": [100, 100, 100]},
    }
    shapes = rect_shape(bar_w, bar_h, color(10, 10, 10, 1.0))
    layer = shape_layer("redacted", 0, dur, [{"ty": "gr", "it": shapes, "nm": "Group"}], transform)
    return lottie_skeleton("redacted_bar", fps, dur, [layer])


# ─────────────────────────────────────────────────────────────────────────────
#  3. RADAR PING — two concentric expanding circles fading out
# ─────────────────────────────────────────────────────────────────────────────
def make_radar_ping() -> dict:
    fps, dur = 30, 45  # 1.5 s

    def ring_layer(ind: int, offset_frames: int, stroke_w: float = 14.0) -> dict:
        size_kf = [
            keyframe(offset_frames,      [60, 60]),
            keyframe(offset_frames + 30, [820, 820]),
        ]
        opacity_kf = [
            keyframe(offset_frames,      [0]),
            keyframe(offset_frames + 3,  [100]),
            keyframe(offset_frames + 30, [0]),
        ]
        shapes = [
            {
                "ty": "gr",
                "nm": "Ring",
                "it": [
                    {
                        "ty": "el",
                        "d": 1,
                        "s": {"a": 1, "k": size_kf},
                        "p": {"a": 0, "k": [0, 0]},
                        "nm": "Ellipse",
                    },
                    {
                        "ty": "st",
                        "c": {"a": 0, "k": color(255, 255, 255)[:3] + [1.0]},
                        "o": {"a": 1, "k": opacity_kf},
                        "w": {"a": 0, "k": stroke_w},
                        "lc": 2, "lj": 2, "ml": 4,
                        "nm": "Stroke",
                    },
                ],
            }
        ]
        return {
            "ddd": 0,
            "ind": ind,
            "ty": 4,
            "nm": f"ping_{ind}",
            "ip": 0,
            "op": dur,
            "st": 0,
            "sr": 1,
            "bm": 0,
            "ks": default_transform(),
            "shapes": shapes,
        }

    def center_dot_layer(ind: int) -> dict:
        op_kf = [
            keyframe(0,  [0]),
            keyframe(2,  [100]),
            keyframe(10, [100]),
            keyframe(dur, [0]),
        ]
        return {
            "ddd": 0,
            "ind": ind,
            "ty": 4,
            "nm": "center_dot",
            "ip": 0,
            "op": dur,
            "st": 0,
            "sr": 1,
            "bm": 0,
            "ks": default_transform(),
            "shapes": [
                {
                    "ty": "gr",
                    "nm": "Dot",
                    "it": [
                        {"ty": "el", "d": 1, "s": {"a": 0, "k": [42, 42]}, "p": {"a": 0, "k": [0, 0]}, "nm": "Ellipse"},
                        {
                            "ty": "fl",
                            "c": {"a": 0, "k": [1.0, 1.0, 1.0, 1.0]},
                            "o": {"a": 1, "k": op_kf},
                            "r": 1,
                            "nm": "Fill",
                        },
                    ],
                }
            ],
        }

    # 3 expanding rings + a bright center dot for a "lock" feel
    layers = [center_dot_layer(1), ring_layer(2, 0), ring_layer(3, 6), ring_layer(4, 12)]
    return lottie_skeleton("radar_ping", fps, dur, layers)


# ─────────────────────────────────────────────────────────────────────────────
#  4. CROSSHAIR SCAN — central crosshair + 4 corner brackets, brief pulse
# ─────────────────────────────────────────────────────────────────────────────
def make_crosshair_scan() -> dict:
    fps, dur = 30, 60  # 2 s
    col = color(240, 245, 255)

    def line_layer(ind: int, points: tuple, op_in: int = 4, op_out: int = 56) -> dict:
        x1, y1, x2, y2 = points
        return {
            "ddd": 0,
            "ind": ind,
            "ty": 4,
            "nm": f"line_{ind}",
            "ip": 0,
            "op": dur,
            "st": 0,
            "sr": 1,
            "bm": 0,
            "ks": {
                "o": {
                    "a": 1, "k": [
                        keyframe(0, [0]),
                        keyframe(op_in, [80]),
                        keyframe(op_out, [80]),
                        keyframe(dur, [0]),
                    ]
                },
                "r": {"a": 0, "k": 0},
                "p": {"a": 0, "k": [0, 0, 0]},
                "a": {"a": 0, "k": [0, 0, 0]},
                "s": {"a": 0, "k": [100, 100, 100]},
            },
            "shapes": [
                {
                    "ty": "gr",
                    "it": [
                        {
                            "ty": "sh",
                            "ks": {
                                "a": 0,
                                "k": {
                                    "c": False,
                                    "v": [[x1, y1], [x2, y2]],
                                    "i": [[0, 0], [0, 0]],
                                    "o": [[0, 0], [0, 0]],
                                },
                            },
                            "nm": "Path",
                        },
                        {
                            "ty": "st",
                            "c": {"a": 0, "k": col[:3] + [1.0]},
                            "o": {"a": 0, "k": 100},
                            "w": {"a": 0, "k": 6},
                            "lc": 2, "lj": 2, "ml": 4,
                            "nm": "Stroke",
                        },
                    ],
                    "nm": "Group",
                }
            ],
        }

    cx, cy = W / 2, H / 2
    arm = 160
    bracket = 90
    # 4 lines: central + and 4 corner brackets (8 short lines)
    layers = [
        line_layer(1, (cx - arm, cy, cx + arm, cy)),  # horizontal cross
        line_layer(2, (cx, cy - arm, cx, cy + arm)),  # vertical cross
        # top-left bracket
        line_layer(3, (60, 60, 60 + bracket, 60)),
        line_layer(4, (60, 60, 60, 60 + bracket)),
        # top-right
        line_layer(5, (W - 60, 60, W - 60 - bracket, 60)),
        line_layer(6, (W - 60, 60, W - 60, 60 + bracket)),
        # bottom-left
        line_layer(7, (60, H - 60, 60 + bracket, H - 60)),
        line_layer(8, (60, H - 60, 60, H - 60 - bracket)),
        # bottom-right
        line_layer(9, (W - 60, H - 60, W - 60 - bracket, H - 60)),
        line_layer(10, (W - 60, H - 60, W - 60, H - 60 - bracket)),
    ]
    return lottie_skeleton("crosshair_scan", fps, dur, layers)


# ─────────────────────────────────────────────────────────────────────────────
#  5. GLITCH BURST — three quick black rectangles flashing across, like a tear
# ─────────────────────────────────────────────────────────────────────────────
def make_glitch_burst() -> dict:
    fps, dur = 30, 18  # 0.6 s

    def slab_layer(ind: int, y: float, w: float, h: float, t_in: int,
                   slab_color: list, dx_in: float = -160, dx_out: float = 160) -> dict:
        return {
            "ddd": 0,
            "ind": ind,
            "ty": 4,
            "nm": f"slab_{ind}",
            "ip": 0,
            "op": dur,
            "st": 0,
            "sr": 1,
            "bm": 0,
            "ks": {
                "o": {
                    "a": 1, "k": [
                        keyframe(t_in,     [0]),
                        keyframe(t_in + 1, [100]),
                        keyframe(t_in + 4, [100]),
                        keyframe(t_in + 5, [0]),
                    ]
                },
                "r": {"a": 0, "k": 0},
                "p": {
                    "a": 1, "k": [
                        keyframe(t_in,     [W / 2 + dx_in,  y, 0]),
                        keyframe(t_in + 5, [W / 2 + dx_out, y, 0]),
                    ]
                },
                "a": {"a": 0, "k": [0, 0, 0]},
                "s": {"a": 0, "k": [100, 100, 100]},
            },
            "shapes": [{"ty": "gr", "it": rect_shape(w, h, slab_color), "nm": "Group"}],
        }

    # Alternate dark and bright slabs for a stronger RGB-split feel.
    layers = [
        slab_layer(1, H * 0.22, W, 60, 0,  color(5, 5, 5, 1.0)),
        slab_layer(2, H * 0.40, W, 32, 2,  color(255, 255, 255, 1.0), dx_in=140, dx_out=-140),
        slab_layer(3, H * 0.58, W, 120, 4, color(5, 5, 5, 1.0)),
        slab_layer(4, H * 0.74, W, 24, 6,  color(255, 255, 255, 1.0), dx_in=-200, dx_out=200),
        slab_layer(5, H * 0.86, W, 50, 8,  color(5, 5, 5, 1.0)),
    ]
    return lottie_skeleton("glitch_burst", fps, dur, layers)


# ─────────────────────────────────────────────────────────────────────────────
#  6. VIGNETTE PULSE — soft circular shadow breathing, useful as suspense layer
# ─────────────────────────────────────────────────────────────────────────────
def make_vignette_pulse() -> dict:
    fps, dur = 30, 90  # 3 s slow pulse

    # We approximate a vignette with a large ellipse stroke fading in/out.
    transform = {
        "o": {
            "a": 1, "k": [
                keyframe(0,        [40]),
                keyframe(dur // 2, [85]),
                keyframe(dur,      [40]),
            ]
        },
        "r": {"a": 0, "k": 0},
        "p": {"a": 0, "k": [W / 2, H / 2, 0]},
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {"a": 0, "k": [100, 100, 100]},
    }
    shapes = [
        {
            "ty": "gr",
            "nm": "Ring",
            "it": [
                {
                    "ty": "el",
                    "d": 1,
                    "s": {"a": 0, "k": [W * 1.6, H * 1.1]},
                    "p": {"a": 0, "k": [0, 0]},
                    "nm": "Ellipse",
                },
                {
                    "ty": "st",
                    "c": {"a": 0, "k": [0, 0, 0, 1.0]},
                    "o": {"a": 0, "k": 100},
                    "w": {"a": 0, "k": 480},
                    "lc": 2, "lj": 2, "ml": 4,
                    "nm": "Stroke",
                },
            ],
        }
    ]
    layer = shape_layer("vignette", 0, dur, shapes, transform)
    return lottie_skeleton("vignette_pulse", fps, dur, [layer])


# ─────────────────────────────────────────────────────────────────────────────
#  MANIFEST
# ─────────────────────────────────────────────────────────────────────────────
ASSETS = [
    {
        "id": "scanline_sweep",
        "factory": make_scanline_sweep,
        "tags": ["scan", "sweep", "hud", "tech", "loop", "atmosphere"],
        "default_blend": "screen",
        "default_opacity": 0.85,
        "monochrome_safe": True,
        "natural_duration_s": 2.0,
        "looping": True,
        "description": "Bright horizontal line with soft glow sweeps top to bottom — techno-investigation feel.",
    },
    {
        "id": "redacted_bar",
        "factory": make_redacted_bar,
        "tags": ["redacted", "censor", "reveal", "secret", "classified"],
        "default_blend": "normal",
        "default_opacity": 1.0,
        "monochrome_safe": True,
        "natural_duration_s": 1.5,
        "looping": False,
        "description": "Black bar slides in to censor, then slides out.",
    },
    {
        "id": "radar_ping",
        "factory": make_radar_ping,
        "tags": ["radar", "ping", "scan", "location", "hud", "alert", "lock"],
        "default_blend": "screen",
        "default_opacity": 1.0,
        "monochrome_safe": True,
        "natural_duration_s": 1.5,
        "looping": False,
        "description": "Three concentric rings expand from a bright center dot, like a radar lock.",
    },
    {
        "id": "crosshair_scan",
        "factory": make_crosshair_scan,
        "tags": ["crosshair", "target", "scan", "hud", "investigation", "focus"],
        "default_blend": "screen",
        "default_opacity": 0.95,
        "monochrome_safe": True,
        "natural_duration_s": 2.0,
        "looping": False,
        "description": "Central crosshair plus 4 corner brackets, framing the subject.",
    },
    {
        "id": "glitch_burst",
        "factory": make_glitch_burst,
        "tags": ["glitch", "tear", "interference", "shock", "revelation"],
        "default_blend": "normal",
        "default_opacity": 0.9,
        "monochrome_safe": True,
        "natural_duration_s": 0.6,
        "looping": False,
        "description": "Three quick black slabs tear across the frame for a sharp punch.",
    },
    {
        "id": "vignette_pulse",
        "factory": make_vignette_pulse,
        "tags": ["vignette", "atmosphere", "pulse", "breath", "tension"],
        "default_blend": "multiply",
        "default_opacity": 0.7,
        "monochrome_safe": True,
        "natural_duration_s": 3.0,
        "looping": True,
        "description": "Heavy vignette breathing — wraps the frame in darkness, heightens suspense.",
    },
]


def main():
    manifest = []
    for asset in ASSETS:
        out_path = LIB / f"{asset['id']}.json"
        data = asset["factory"]()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        size_kb = out_path.stat().st_size / 1024
        manifest.append({
            "id": asset["id"],
            "file": f"library/{asset['id']}.json",
            "tags": asset["tags"],
            "default_blend": asset["default_blend"],
            "default_opacity": asset["default_opacity"],
            "monochrome_safe": asset["monochrome_safe"],
            "natural_duration_s": asset["natural_duration_s"],
            "looping": asset["looping"],
            "description": asset["description"],
            "size_kb": round(size_kb, 1),
        })
        print(f"  ✅ {asset['id']:18s} → {out_path.name}  ({size_kb:.1f} KB)")

    manifest_path = HERE / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "assets": manifest}, f, indent=2, ensure_ascii=False)
    print(f"\n  📋 manifest.json → {len(manifest)} assets catalogued")


if __name__ == "__main__":
    main()
