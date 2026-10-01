#!/usr/bin/env python3
"""Generate the custom Yurei mirror manifestation Lottie.

The animation is authored for the diffusionstudio/text-to-lottie Skottie
preview harness, then embedded by the HyperFrames renderer as transparent
Bodymovin JSON.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "library" / "yurei_mirror_manifestation.json"
PREVIEW_OUTPUT = ROOT / "preview" / "yurei_mirror_manifestation.json"
MANIFEST = ROOT / "manifest.json"
FR = 60
OP = 210
W = 1000
H = 600

EASE_IN = {"x": [0.65], "y": [1.0]}
EASE_OUT = {"x": [0.35], "y": [0.0]}


def static(value):
    return {"a": 0, "k": value}


def animated(keys):
    frames = []
    for index, (time, value) in enumerate(keys):
        frame = {"t": time, "s": value if isinstance(value, list) else [value]}
        if index < len(keys) - 1:
            frame["i"] = EASE_IN
            frame["o"] = EASE_OUT
        frames.append(frame)
    return {"a": 1, "k": frames}


def transform(
    *,
    opacity=100,
    position=(500, 300, 0),
    scale=(100, 100, 100),
    rotation=0,
):
    return {
        "o": opacity if isinstance(opacity, dict) else static(opacity),
        "r": rotation if isinstance(rotation, dict) else static(rotation),
        "p": position if isinstance(position, dict) else static(list(position)),
        "a": static([0, 0, 0]),
        "s": scale if isinstance(scale, dict) else static(list(scale)),
    }


def group(items, name):
    return {
        "ty": "gr",
        "nm": name,
        "it": [
            *items,
            {
                "ty": "tr",
                "p": static([0, 0]),
                "a": static([0, 0]),
                "s": static([100, 100]),
                "r": static(0),
                "o": static(100),
            },
        ],
    }


def fill(color, opacity=100, slot=None):
    color_value = {"sid": slot} if slot else static(color)
    return {"ty": "fl", "c": color_value, "o": static(opacity)}


def stroke(color, width, opacity=100):
    return {
        "ty": "st",
        "c": static(color),
        "w": static(width),
        "o": static(opacity),
        "lc": 2,
        "lj": 2,
    }


def ellipse(x, y, width, height):
    return {
        "ty": "el",
        "p": static([x, y]),
        "s": static([width, height]),
    }


def rectangle(x, y, width, height, radius=0):
    return {
        "ty": "rc",
        "p": static([x, y]),
        "s": static([width, height]),
        "r": static(radius),
    }


def path(vertices, in_tangents, out_tangents, closed=False):
    return {
        "ty": "sh",
        "ks": static(
            {
                "c": closed,
                "v": vertices,
                "i": in_tangents,
                "o": out_tangents,
            }
        ),
    }


def shape_layer(name, shapes, *, ks=None, ip=0, op=OP):
    return {
        "ty": 4,
        "nm": name,
        "ip": ip,
        "op": op,
        "st": 0,
        "ks": ks or transform(),
        "shapes": shapes,
    }


def ghost_opacity(delay=0, peak=68):
    return animated(
        [
            (0 + delay, 0),
            (28 + delay, 0),
            (58 + delay, peak),
            (96 + delay, peak - 6),
            (108 + delay, peak),
            (113 + delay, 20),
            (117 + delay, peak - 10),
            (122 + delay, 8),
            (132 + delay, 0),
            (OP, 0),
        ]
    )


def ghost_scale(offset=0):
    return animated(
        [
            (0, [90 + offset, 90 + offset, 100]),
            (58, [100 + offset, 100 + offset, 100]),
            (108, [102 + offset, 102 + offset, 100]),
            (132, [108 + offset, 112 + offset, 100]),
            (OP, [112 + offset, 118 + offset, 100]),
        ]
    )


def build_animation():
    white = [0.72, 0.82, 0.9, 1.0]
    cold = [0.28, 0.48, 0.62, 1.0]
    red = [0.95, 0.035, 0.08, 1.0]
    dark = [0.008, 0.016, 0.026, 1.0]
    deep_red = [0.24, 0.005, 0.02, 1.0]

    body_vertices = [
        [-42, -94],
        [-96, -42],
        [-134, 70],
        [-126, 184],
        [-78, 230],
        [0, 252],
        [78, 230],
        [126, 184],
        [134, 70],
        [96, -42],
        [42, -94],
    ]
    body_in = [
        [-8, -4],
        [-18, -20],
        [-8, -36],
        [-8, -42],
        [-24, -14],
        [-28, 0],
        [-24, 14],
        [8, 42],
        [8, 36],
        [18, 20],
        [8, 4],
    ]
    body_out = [[-v[0], -v[1]] for v in body_in]

    layers = []

    # Topmost red fracture: three irregular cuts, never a generic HUD bar.
    fractures = [
        ([[-92, -20], [-32, -29], [28, -16], [88, -25]], 3.0, -12),
        ([[-118, 7], [-42, -2], [34, 12], [116, 4]], 4.5, 18),
        ([[-68, 35], [-18, 28], [22, 40], [68, 31]], 2.8, -30),
    ]
    for index, (vertices, line_width, shift) in enumerate(fractures):
        layers.append(
            shape_layer(
                f"red fracture {index + 1}",
                [
                    group(
                        [
                            path(
                                vertices,
                                [[0, 0], [-12, 2], [-12, -2], [0, 0]],
                                [[12, -2], [12, 2], [12, -2], [0, 0]],
                            ),
                            stroke(red, line_width, 92),
                        ],
                        "fracture",
                    )
                ],
                ks=transform(
                    opacity=animated(
                        [
                            (0, 0),
                            (102 + index * 2, 0),
                            (108 + index * 2, 88),
                            (116 + index * 2, 24),
                            (124 + index * 2, 0),
                            (OP, 0),
                        ]
                    ),
                    position=animated(
                        [
                            (0, [500 + shift, 300, 0]),
                            (104, [500 + shift, 300, 0]),
                            (124, [500 - shift, 300, 0]),
                            (OP, [500 - shift, 300, 0]),
                        ]
                    ),
                    scale=animated(
                        [
                            (0, [30, 100, 100]),
                            (104, [30, 100, 100]),
                            (112, [100, 100, 100]),
                            (124, [135, 100, 100]),
                            (OP, [135, 100, 100]),
                        ]
                    ),
                ),
            )
        )

    # Fine particles peel away from the silhouette after the disappearance.
    particles = [
        (-92, -36, -175, -142, 6),
        (-58, 38, -120, -175, 4),
        (-24, 112, -78, -205, 5),
        (18, 128, 64, -214, 4),
        (58, 62, 132, -168, 6),
        (92, -12, 190, -124, 4),
        (-110, 108, -224, -56, 3),
        (112, 126, 235, -42, 3),
    ]
    for index, (x0, y0, x1, y1, size) in enumerate(particles):
        start = 102 + index * 3
        layers.append(
            shape_layer(
                f"spectral particle {index + 1}",
                [group([ellipse(0, 0, size, size), fill(white, 80)], "particle")],
                ks=transform(
                    opacity=animated(
                        [
                            (0, 0),
                            (start, 0),
                            (start + 10, 72),
                            (start + 46, 34),
                            (start + 78, 0),
                            (OP, 0),
                        ]
                    ),
                    position=animated(
                        [
                            (0, [500 + x0, 320 + y0, 0]),
                            (start, [500 + x0, 320 + y0, 0]),
                            (start + 78, [500 + x1, 320 + y1, 0]),
                            (OP, [500 + x1, 320 + y1, 0]),
                        ]
                    ),
                    scale=animated(
                        [
                            (0, [70, 70, 100]),
                            (start, [70, 70, 100]),
                            (start + 35, [125, 125, 100]),
                            (start + 78, [40, 40, 100]),
                            (OP, [40, 40, 100]),
                        ]
                    ),
                ),
            )
        )

    # Curved filaments create an elegant evaporation instead of a generic glitch.
    wisps = [
        ([-96, 128], [-160, 62], [-190, -36]),
        ([-72, 188], [-130, 106], [-116, -62]),
        ([-26, 220], [-74, 126], [-42, -96]),
        ([28, 220], [82, 120], [54, -110]),
        ([74, 184], [142, 96], [130, -72]),
        ([98, 118], [174, 48], [202, -42]),
    ]
    for index, (a, b, c) in enumerate(wisps):
        start = 94 + index * 3
        layers.append(
            shape_layer(
                f"evaporation filament {index + 1}",
                [
                    group(
                        [
                            path(
                                [a, b, c],
                                [[0, 0], [-26, 36], [-18, 42]],
                                [[18, -30], [28, -38], [0, 0]],
                            ),
                            stroke(white if index % 2 == 0 else cold, 2.2, 58),
                        ],
                        "filament",
                    )
                ],
                ks=transform(
                    opacity=animated(
                        [
                            (0, 0),
                            (start, 0),
                            (start + 18, 52),
                            (start + 64, 16),
                            (start + 104, 0),
                            (OP, 0),
                        ]
                    ),
                    position=animated(
                        [
                            (0, [500, 300, 0]),
                            (start, [500, 300, 0]),
                            (start + 104, [500 + (index - 2.5) * 14, 205, 0]),
                            (OP, [500 + (index - 2.5) * 14, 205, 0]),
                        ]
                    ),
                    scale=animated(
                        [
                            (0, [88, 88, 100]),
                            (start, [88, 88, 100]),
                            (start + 104, [116, 126, 100]),
                            (OP, [116, 126, 100]),
                        ]
                    ),
                ),
            )
        )

    # Head and veil are split into translucent layers for depth.
    layers.append(
        shape_layer(
            "face void",
            [
                group(
                    [
                        ellipse(0, -145, 34, 9),
                        fill(deep_red, 58),
                    ],
                    "featureless face shadow",
                )
            ],
            ks=transform(
                opacity=ghost_opacity(4, 42),
                position=animated(
                    [
                        (0, [500, 330, 0]),
                        (58, [500, 300, 0]),
                        (108, [500, 294, 0]),
                        (132, [510, 264, 0]),
                        (OP, [510, 264, 0]),
                    ]
                ),
                scale=ghost_scale(-2),
            ),
        )
    )
    layers.append(
        shape_layer(
            "ghost head",
            [
                group(
                    [
                        ellipse(0, -145, 82, 108),
                        fill(dark, 94),
                    ],
                    "head shadow",
                ),
                group(
                    [
                        path(
                            [
                                [-46, -116],
                                [-56, -172],
                                [0, -214],
                                [56, -172],
                                [46, -116],
                            ],
                            [[0, 0], [-6, 18], [-24, 0], [-6, -18], [0, 0]],
                            [[6, -18], [24, 0], [24, 0], [6, 18], [0, 0]],
                        ),
                        stroke(cold, 2.2, 56),
                    ],
                    "broken hood arc",
                ),
            ],
            ks=transform(
                opacity=ghost_opacity(0, 54),
                position=animated(
                    [
                        (0, [500, 332, 0]),
                        (58, [500, 300, 0]),
                        (108, [500, 294, 0]),
                        (113, [488, 294, 0]),
                        (117, [512, 292, 0]),
                        (122, [495, 286, 0]),
                        (132, [506, 258, 0]),
                        (OP, [506, 258, 0]),
                    ]
                ),
                scale=ghost_scale(),
            ),
        )
    )
    layers.append(
        shape_layer(
            "inner veil",
            [
                group(
                    [
                        path(
                            body_vertices,
                            body_in,
                            body_out,
                            closed=True,
                        ),
                        fill(dark, 86),
                    ],
                    "inner veil",
                )
            ],
            ks=transform(
                opacity=ghost_opacity(2, 48),
                position=animated(
                    [
                        (0, [500, 335, 0]),
                        (58, [500, 300, 0]),
                        (108, [500, 294, 0]),
                        (132, [496, 250, 0]),
                        (OP, [496, 250, 0]),
                    ]
                ),
                scale=ghost_scale(-1),
            ),
        )
    )
    left_edge = [[-38, -92], [-92, -38], [-126, 72], [-120, 174], [-76, 226]]
    right_edge = [[38, -92], [92, -38], [126, 72], [120, 174], [76, 226]]
    layers.append(
        shape_layer(
            "fragmented veil edges",
            [
                group(
                    [
                        path(
                            left_edge,
                            [[0, 0], [-12, -18], [-8, -28], [-8, -32], [0, 0]],
                            [[12, 18], [8, 28], [8, 32], [10, 20], [0, 0]],
                        ),
                        stroke(white, 2.3, 64),
                    ],
                    "left veil edge",
                ),
                group(
                    [
                        path(
                            right_edge,
                            [[0, 0], [12, -18], [8, -28], [8, -32], [0, 0]],
                            [[-12, 18], [-8, 28], [-8, 32], [-10, 20], [0, 0]],
                        ),
                        stroke(white, 2.3, 64),
                    ],
                    "right veil edge",
                ),
            ],
            ks=transform(
                opacity=ghost_opacity(0, 52),
                position=animated(
                    [
                        (0, [500, 334, 0]),
                        (58, [500, 300, 0]),
                        (108, [500, 294, 0]),
                        (132, [502, 244, 0]),
                        (OP, [502, 244, 0]),
                    ]
                ),
                scale=ghost_scale(1),
            ),
        )
    )

    # Two delayed broken edges create a photographic afterimage without
    # enclosing the figure like a pictogram.
    for index, x_shift in enumerate((-16, 16)):
        layers.append(
            shape_layer(
                f"afterimage {index + 1}",
                [
                    group(
                        [
                            path(
                                left_edge if index == 0 else right_edge,
                                [[0, 0], [-12, -18], [-8, -28], [-8, -32], [0, 0]],
                                [[12, 18], [8, 28], [8, 32], [10, 20], [0, 0]],
                            ),
                            stroke(cold, 1.5, 42),
                        ],
                        "afterimage edge",
                    )
                ],
                ks=transform(
                    opacity=animated(
                        [
                            (0, 0),
                            (38 + index * 5, 0),
                            (66 + index * 5, 18),
                            (96, 8),
                            (108, 24),
                            (124, 0),
                            (OP, 0),
                        ]
                    ),
                    position=animated(
                        [
                            (0, [500 + x_shift, 310, 0]),
                            (66, [500 + x_shift, 300, 0]),
                            (108, [500 - x_shift, 294, 0]),
                            (124, [500 + x_shift * 2, 278, 0]),
                            (OP, [500 + x_shift * 2, 278, 0]),
                        ]
                    ),
                    scale=ghost_scale(3),
                ),
            )
        )

    # Transparent background is required by the preview skill's control contract.
    layers.append(
        shape_layer(
            "background",
            [
                group(
                    [
                        rectangle(W / 2, H / 2, W, H, 0),
                        fill([0, 0, 0, 0], 100, slot="bgColor"),
                    ],
                    "transparent background",
                )
            ],
            ks=transform(position=(0, 0, 0)),
        )
    )

    return {
        "v": "5.7.0",
        "fr": FR,
        "ip": 0,
        "op": OP,
        "w": W,
        "h": H,
        "nm": "Yurei Mirror Manifestation",
        "ddd": 0,
        "assets": [],
        "slots": {
            "bgColor": {"p": {"a": 0, "k": [0, 0, 0, 0]}},
        },
        "layers": layers,
    }


def update_manifest(size_kb):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    asset = {
        "id": "yurei_mirror_manifestation",
        "file": "library/yurei_mirror_manifestation.json",
        "tags": [
            "yurei",
            "ghost",
            "apparition",
            "mirror",
            "disappearance",
            "paranormal",
            "signature",
        ],
        "default_blend": "screen",
        "default_opacity": 0.68,
        "monochrome_safe": False,
        "natural_duration_s": OP / FR,
        "looping": False,
        "description": (
            "Custom Yurei signature: a white faceless apparition forms in a "
            "rear-view mirror, fractures in red, then evaporates into filaments."
        ),
        "size_kb": size_kb,
        "source_url": "https://github.com/diffusionstudio/lottie",
    }
    assets = [
        item for item in manifest.get("assets", []) if item.get("id") != asset["id"]
    ]
    assets.append(asset)
    manifest["assets"] = assets
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    preview_animation = build_animation()
    PREVIEW_OUTPUT.write_text(
        json.dumps(preview_animation, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )

    # The Diffusion Studio preview requires a slotted background control.
    # lottie-web does not resolve Skottie slots, so the production asset drops
    # that layer and remains genuinely transparent over the video.
    animation = dict(preview_animation)
    animation.pop("slots", None)
    animation["layers"] = [
        layer
        for layer in preview_animation["layers"]
        if layer.get("nm") != "background"
    ]
    OUTPUT.write_text(
        json.dumps(animation, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    size_kb = round(OUTPUT.stat().st_size / 1024, 1)
    update_manifest(size_kb)
    print(f"Wrote {PREVIEW_OUTPUT} and {OUTPUT} ({size_kb} KB runtime)")


if __name__ == "__main__":
    main()
