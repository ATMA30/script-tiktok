"""
generate_truecrime_extras.py — adds 6 procedural Lottie animations to the
library, tailored for a monochrome true-crime documentary aesthetic.

  1. evidence_pin_thread  (red string traced between two corkboard pins)
  2. magnifier_sweep      (magnifying glass passing over a detail)
  3. fingerprint_reveal   (whorls of a fingerprint tracing in)
  4. redacted_tear        (redaction bar slides in, jitters, rips apart)
  5. surveillance_rec     (camera viewfinder + blinking REC dot — loopable)
  6. radar_sweep          (radar/sonar with rotating wedge — loopable, 3s)

Run once:
    python assets/lottie/generate_truecrime_extras.py

It writes 6 files under library/ and merges entries into manifest.json
(preserving any existing entries — including the curated lf_* ones).
"""

import json
import math
from pathlib import Path

HERE = Path(__file__).parent
LIB = HERE / "library"
LIB.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920


def color(r, g, b, a=1.0):
    return [r / 255.0, g / 255.0, b / 255.0, a]


LIGHT = color(240, 245, 255)
INK = color(10, 10, 10)
RED = color(199, 30, 36)  # corkboard string red
REC = color(217, 46, 46)  # surveillance indicator red


def kf(t, v):
    return {"t": t, "s": v if isinstance(v, list) else [v]}


def static_tx(x=0, y=0, opacity=100, scale=100, rot=0):
    return {
        "o": {"a": 0, "k": opacity},
        "r": {"a": 0, "k": rot},
        "p": {"a": 0, "k": [x, y, 0]},
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {"a": 0, "k": [scale, scale, 100]},
    }


def lottie_skeleton(name, fps, dur, layers):
    return {
        "v": "5.7.4",
        "fr": fps,
        "ip": 0,
        "op": dur,
        "w": W,
        "h": H,
        "nm": name,
        "ddd": 0,
        "assets": [],
        "layers": layers,
        "markers": [],
        "meta": {"g": "script-tiktok procedural"},
    }


def shape_layer(ind, nm, ip, op, shapes, ks):
    return {
        "ddd": 0,
        "ind": ind,
        "ty": 4,
        "nm": nm,
        "ip": ip,
        "op": op,
        "st": 0,
        "sr": 1,
        "bm": 0,
        "ks": ks,
        "shapes": shapes,
    }


def stroke(rgba, w, opacity=100):
    return {
        "ty": "st",
        "c": {"a": 0, "k": rgba[:3] + [1.0]},
        "o": {"a": 0, "k": opacity * rgba[3]},
        "w": {"a": 0, "k": w},
        "lc": 2,
        "lj": 2,
        "ml": 4,
        "nm": "Stroke",
    }


def fill(rgba, opacity=100):
    return {
        "ty": "fl",
        "c": {"a": 0, "k": rgba[:3] + [1.0]},
        "o": {"a": 0, "k": opacity * rgba[3]},
        "r": 1,
        "nm": "Fill",
    }


def ellipse(w, h, p=(0, 0)):
    return {
        "ty": "el",
        "d": 1,
        "s": {"a": 0, "k": [w, h]},
        "p": {"a": 0, "k": list(p)},
        "nm": "Ellipse",
    }


def rect(w, h, p=(0, 0)):
    return {
        "ty": "rc",
        "d": 1,
        "s": {"a": 0, "k": [w, h]},
        "p": {"a": 0, "k": list(p)},
        "r": {"a": 0, "k": 0},
        "nm": "Rect",
    }


def path(vertices, in_t=None, out_t=None, closed=False):
    n = len(vertices)
    return {
        "ty": "sh",
        "ks": {
            "a": 0,
            "k": {
                "c": closed,
                "v": [list(v) for v in vertices],
                "i": [list(t) for t in (in_t or [[0, 0]] * n)],
                "o": [list(t) for t in (out_t or [[0, 0]] * n)],
            },
        },
        "nm": "Path",
    }


def trim(s_kf, e_kf, m=1):
    def to_prop(v):
        if isinstance(v, list):
            return {"a": 1, "k": v}
        return {"a": 0, "k": v}

    return {
        "ty": "tm",
        "s": to_prop(s_kf),
        "e": to_prop(e_kf),
        "o": {"a": 0, "k": 0},
        "m": m,
        "nm": "Trim",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  1. EVIDENCE PIN + RED THREAD
# ─────────────────────────────────────────────────────────────────────────────
def make_evidence_pin_thread():
    fps, dur = 30, 60
    p1 = (320, 620)
    mid = (540, 990)
    p2 = (760, 1280)

    # Thread group — bezier path traced by trim "e"
    thread_path = path(
        vertices=[p1, mid, p2],
        in_t=[[0, 0], [-130, 30], [0, 0]],
        out_t=[[0, 0], [130, -30], [0, 0]],
        closed=False,
    )
    thread_group = {
        "ty": "gr",
        "nm": "Thread",
        "it": [
            thread_path,
            stroke(RED, 7),
            trim(s_kf=0, e_kf=[kf(8, 0), kf(48, 100)]),
        ],
    }
    thread_layer = shape_layer(3, "thread", 0, dur, [thread_group], static_tx())

    def pin_layer(ind, name, center, t_in):
        ks = {
            "o": {
                "a": 1,
                "k": [kf(t_in, 0), kf(t_in + 4, 100), kf(dur - 2, 100), kf(dur, 70)],
            },
            "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [center[0], center[1], 0]},
            "a": {"a": 0, "k": [0, 0, 0]},
            "s": {
                "a": 1,
                "k": [
                    kf(t_in, [0, 0, 100]),
                    kf(t_in + 4, [125, 125, 100]),
                    kf(t_in + 8, [100, 100, 100]),
                ],
            },
        }
        shapes = [
            {"ty": "gr", "nm": "head", "it": [ellipse(30, 30), fill(RED)]},
            {
                "ty": "gr",
                "nm": "shine",
                "it": [ellipse(10, 10, p=(-4, -4)), fill(LIGHT, opacity=90)],
            },
        ]
        return shape_layer(ind, name, 0, dur, shapes, ks)

    layers = [
        pin_layer(1, "pin_top", p1, 2),
        pin_layer(2, "pin_bottom", p2, 46),
        thread_layer,
    ]
    return lottie_skeleton("evidence_pin_thread", fps, dur, layers)


# ─────────────────────────────────────────────────────────────────────────────
#  2. MAGNIFIER SWEEP
# ─────────────────────────────────────────────────────────────────────────────
def make_magnifier_sweep():
    fps, dur = 30, 45
    R = 80
    handle_start = R / math.sqrt(2)  # 45° from center
    handle_end = handle_start + 80

    lens = {
        "ty": "gr",
        "nm": "lens",
        "it": [
            ellipse(R * 2, R * 2),
            stroke(LIGHT, 9),
        ],
    }
    inner_glow = {
        "ty": "gr",
        "nm": "lens_inner",
        "it": [
            ellipse((R - 14) * 2, (R - 14) * 2),
            stroke(LIGHT, 2, opacity=35),
        ],
    }
    handle = {
        "ty": "gr",
        "nm": "handle",
        "it": [
            path(
                [(handle_start, handle_start), (handle_end, handle_end)], closed=False
            ),
            stroke(LIGHT, 11),
        ],
    }

    mag_ks = {
        "o": {"a": 1, "k": [kf(0, 0), kf(4, 100), kf(40, 100), kf(45, 0)]},
        "r": {"a": 1, "k": [kf(0, [-6]), kf(22, [3]), kf(45, [-2])]},
        "p": {
            "a": 1,
            "k": [
                kf(0, [200, 1180, 0]),
                kf(22, [540, 960, 0]),
                kf(45, [900, 760, 0]),
            ],
        },
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {"a": 0, "k": [100, 100, 100]},
    }
    mag = shape_layer(1, "magnifier", 0, dur, [inner_glow, lens, handle], mag_ks)

    # Subtle detail pulse halfway through the sweep
    pulse_ks = {
        "o": {"a": 1, "k": [kf(18, 0), kf(22, 80), kf(30, 0)]},
        "r": {"a": 0, "k": 0},
        "p": {"a": 0, "k": [540, 960, 0]},
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {
            "a": 1,
            "k": [
                kf(18, [40, 40, 100]),
                kf(30, [180, 180, 100]),
            ],
        },
    }
    pulse = shape_layer(
        2,
        "detail_pulse",
        0,
        dur,
        [{"ty": "gr", "nm": "pulse", "it": [ellipse(40, 40), stroke(LIGHT, 4)]}],
        pulse_ks,
    )
    return lottie_skeleton("magnifier_sweep", fps, dur, [mag, pulse])


# ─────────────────────────────────────────────────────────────────────────────
#  3. FINGERPRINT REVEAL
# ─────────────────────────────────────────────────────────────────────────────
def make_fingerprint_reveal():
    fps, dur = 30, 54
    cx, cy = 540, 960

    # (w, h, off_x, off_y, t_start, e_target, rotation_deg)
    arcs = [
        (80, 100, 8, -15, 4, 78, -12),
        (160, 200, -10, -8, 10, 88, 35),
        (240, 290, 6, 5, 16, 72, -20),
        (320, 380, -4, 12, 22, 90, 100),
        (400, 460, 10, 18, 28, 65, -45),
    ]

    layers = []
    for i, (rw, rh, ox, oy, t0, et, rot) in enumerate(arcs):
        grp = {
            "ty": "gr",
            "nm": f"whorl_{i}",
            "it": [
                ellipse(rw, rh),
                stroke(LIGHT, 4),
                trim(s_kf=0, e_kf=[kf(t0, 0), kf(t0 + 12, et)]),
            ],
        }
        ks = {
            "o": {
                "a": 1,
                "k": [
                    kf(t0, 0),
                    kf(t0 + 4, 100),
                    kf(dur - 6, 100),
                    kf(dur, 0),
                ],
            },
            "r": {"a": 0, "k": rot},
            "p": {"a": 0, "k": [cx + ox, cy + oy, 0]},
            "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [100, 100, 100]},
        }
        layers.append(shape_layer(i + 1, f"whorl_{i}", 0, dur, [grp], ks))
    return lottie_skeleton("fingerprint_reveal", fps, dur, layers)


# ─────────────────────────────────────────────────────────────────────────────
#  4. REDACTED TEAR
# ─────────────────────────────────────────────────────────────────────────────
def make_redacted_tear():
    fps, dur = 30, 36
    bar_w = 720
    half_h = 32

    def half_layer(ind, name, y_rest, y_fly):
        ks = {
            "o": {
                "a": 1,
                "k": [
                    kf(0, 0),
                    kf(4, 100),
                    kf(28, 100),
                    kf(dur, 0),
                ],
            },
            "r": {"a": 0, "k": 0},
            "p": {
                "a": 1,
                "k": [
                    kf(0, [-bar_w / 2, y_rest, 0]),
                    kf(10, [540, y_rest, 0]),
                    kf(18, [540, y_rest, 0]),
                    kf(20, [533, y_rest, 0]),  # quick jitter
                    kf(22, [546, y_rest, 0]),
                    kf(24, [540, y_rest, 0]),
                    kf(34, [540, y_fly, 0]),  # tear apart
                ],
            },
            "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [100, 100, 100]},
        }
        shapes = [{"ty": "gr", "nm": "Group", "it": [rect(bar_w, half_h), fill(INK)]}]
        return shape_layer(ind, name, 0, dur, shapes, ks)

    y_top = 960 - half_h / 2
    y_bot = 960 + half_h / 2
    top = half_layer(1, "top_half", y_top, y_top - 90)
    bot = half_layer(2, "bottom_half", y_bot, y_bot + 90)
    return lottie_skeleton("redacted_tear", fps, dur, [top, bot])


# ─────────────────────────────────────────────────────────────────────────────
#  5. SURVEILLANCE — viewfinder + blinking REC dot (loopable)
# ─────────────────────────────────────────────────────────────────────────────
def make_surveillance_rec():
    fps, dur = 30, 45
    arm = 90
    corners = [
        (240, 720),
        (W - 240, 720),
        (240, H - 720),
        (W - 240, H - 720),
    ]

    bracket_shapes = []
    for cx, cy in corners:
        sx = arm if cx < W / 2 else -arm
        sy = arm if cy < H / 2 else -arm
        bracket_shapes.append(
            {
                "ty": "gr",
                "nm": "corner_h",
                "it": [
                    path([(cx, cy), (cx + sx, cy)], closed=False),
                    stroke(LIGHT, 7, opacity=85),
                ],
            }
        )
        bracket_shapes.append(
            {
                "ty": "gr",
                "nm": "corner_v",
                "it": [
                    path([(cx, cy), (cx, cy + sy)], closed=False),
                    stroke(LIGHT, 7, opacity=85),
                ],
            }
        )

    frame_layer = shape_layer(2, "viewfinder", 0, dur, bracket_shapes, static_tx())

    # REC dot: 1 clean "off" beat per loop, frame 0 and frame dur both at 100
    rec_ks = {
        "o": {
            "a": 1,
            "k": [
                kf(0, 100),
                kf(20, 100),
                kf(23, 0),
                kf(35, 0),
                kf(38, 100),
                kf(dur, 100),
            ],
        },
        "r": {"a": 0, "k": 0},
        "p": {"a": 0, "k": [W - 280, 760, 0]},
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {"a": 0, "k": [100, 100, 100]},
    }
    rec_shapes = [
        {"ty": "gr", "nm": "rec_glow", "it": [ellipse(46, 46), fill(REC, opacity=35)]},
        {"ty": "gr", "nm": "rec_dot", "it": [ellipse(26, 26), fill(REC)]},
    ]
    rec_layer = shape_layer(1, "rec_indicator", 0, dur, rec_shapes, rec_ks)

    return lottie_skeleton("surveillance_rec", fps, dur, [rec_layer, frame_layer])


# ─────────────────────────────────────────────────────────────────────────────
#  6. RADAR SWEEP — concentric rings + rotating wedge (loopable 3s)
# ─────────────────────────────────────────────────────────────────────────────
def make_radar_sweep():
    fps, dur = 30, 90
    cx, cy = 540, 960
    rings = [140, 240, 340]
    arm = 360

    base_shapes = []
    for r in rings:
        base_shapes.append(
            {
                "ty": "gr",
                "nm": f"ring_{r}",
                "it": [
                    ellipse(r * 2, r * 2),
                    stroke(LIGHT, 3, opacity=55),
                ],
            }
        )
    base_shapes.append(
        {
            "ty": "gr",
            "nm": "cross_h",
            "it": [
                path([(-arm, 0), (arm, 0)], closed=False),
                stroke(LIGHT, 2, opacity=40),
            ],
        }
    )
    base_shapes.append(
        {
            "ty": "gr",
            "nm": "cross_v",
            "it": [
                path([(0, -arm), (0, arm)], closed=False),
                stroke(LIGHT, 2, opacity=40),
            ],
        }
    )
    base_layer = shape_layer(
        2, "radar_base", 0, dur, base_shapes, static_tx(x=cx, y=cy)
    )

    # Rotating wedge
    R = 340
    spread = math.radians(32)
    trailing_tip = (0, -R)  # angle 0
    leading_tip = (R * math.sin(spread), -R * math.cos(spread))  # angle +spread

    wedge_path = path(
        vertices=[(0, 0), trailing_tip, leading_tip],
        closed=True,
    )
    wedge_shapes = [
        {"ty": "gr", "nm": "wedge_body", "it": [wedge_path, fill(LIGHT, opacity=28)]},
        {
            "ty": "gr",
            "nm": "leading_edge",
            "it": [
                path([(0, 0), leading_tip], closed=False),
                stroke(LIGHT, 4, opacity=85),
            ],
        },
    ]
    wedge_ks = {
        "o": {"a": 0, "k": 100},
        "r": {"a": 1, "k": [kf(0, 0), kf(dur, 360)]},
        "p": {"a": 0, "k": [cx, cy, 0]},
        "a": {"a": 0, "k": [0, 0, 0]},
        "s": {"a": 0, "k": [100, 100, 100]},
    }
    wedge_layer = shape_layer(1, "sweep", 0, dur, wedge_shapes, wedge_ks)

    return lottie_skeleton("radar_sweep", fps, dur, [wedge_layer, base_layer])


# ─────────────────────────────────────────────────────────────────────────────
ASSETS = [
    # id, factory, tags, blend, opacity, duration, loop, description
    (
        "evidence_pin_thread",
        make_evidence_pin_thread,
        ["evidence", "pin", "thread", "string", "corkboard", "investigation", "clue"],
        "normal",
        1.0,
        2.0,
        False,
        "Red string traces between two corkboard pins — detective evidence board.",
    ),
    (
        "magnifier_sweep",
        make_magnifier_sweep,
        ["magnifier", "loupe", "inspect", "detail", "investigation", "focus"],
        "screen",
        0.9,
        1.5,
        False,
        "Magnifying glass sweeps across the frame, pulses over a central detail.",
    ),
    (
        "fingerprint_reveal",
        make_fingerprint_reveal,
        ["fingerprint", "forensic", "evidence", "biometric", "reveal", "identity"],
        "screen",
        0.9,
        1.8,
        False,
        "Five concentric whorls trace in to form a fingerprint.",
    ),
    (
        "redacted_tear",
        make_redacted_tear,
        ["redacted", "censor", "classified", "tear", "rip", "secret"],
        "normal",
        1.0,
        1.2,
        False,
        "Black bar slides in to censor, jitters, then rips apart vertically.",
    ),
    (
        "surveillance_rec",
        make_surveillance_rec,
        ["surveillance", "camera", "cctv", "rec", "viewfinder", "watching", "loop"],
        "screen",
        0.95,
        1.5,
        True,
        "Camera viewfinder frame with a blinking REC indicator — loopable.",
    ),
    (
        "radar_sweep",
        make_radar_sweep,
        ["radar", "sonar", "sweep", "scan", "investigation", "detect", "loop"],
        "screen",
        0.85,
        3.0,
        True,
        "Concentric rings with a rotating sweep wedge — radar/sonar, loopable.",
    ),
]


def main():
    print("Building 6 true-crime extras …")
    for asset_id, factory, *_ in ASSETS:
        out = LIB / f"{asset_id}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(factory(), f, separators=(",", ":"))
        size_kb = out.stat().st_size / 1024
        print(f"  ✅ {asset_id:24s} → {out.name}  ({size_kb:.1f} KB)")

    # Merge new entries into manifest.json (keep curated entries intact)
    manifest_path = HERE / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {"version": 1, "assets": []}

    by_id = {a["id"]: a for a in manifest.get("assets", [])}
    for asset_id, _factory, tags, blend, opacity, dur, loop, desc in ASSETS:
        out = LIB / f"{asset_id}.json"
        size_kb = round(out.stat().st_size / 1024, 1)
        by_id[asset_id] = {
            "id": asset_id,
            "file": f"library/{asset_id}.json",
            "tags": tags,
            "default_blend": blend,
            "default_opacity": opacity,
            "monochrome_safe": True,
            "natural_duration_s": dur,
            "looping": loop,
            "description": desc,
            "size_kb": size_kb,
        }

    manifest["assets"] = sorted(by_id.values(), key=lambda a: a["id"])
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n  📋 manifest.json → {len(manifest['assets'])} assets catalogued")


if __name__ == "__main__":
    main()
