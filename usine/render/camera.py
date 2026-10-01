"""Plans image : mouvements de caméra 2.5D, fonds procéduraux, grading et effets du Director."""

import os
from usine.render.config import (
    BG_VARIANTS,
    MOTION_STRENGTH,
    USE_ACT_GRADING,
    USE_PERSISTENT_CASE_TAG,
)


# ── Motion variants : micro-mouvements lisibles.
# Les médias réels doivent rester compréhensibles: pas de zoom/crop destructeur.
# Chaque variant porte aussi une "ease" et une "intensity" (1.0 = base, <1 plus
# calme, >1 plus tendu) pour que le rythme respire d'un plan à l'autre.
MOTION_VARIANTS = [
    # push-in posé
    {
        "start": {"scale": 1.0, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0},
        "end": {"scale": 1.028, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0},
        "ease": "power2.out",
        "intensity": 1.00,
    },
    # pan latéral gauche -> droite, scale stable
    {
        "start": {
            "scale": 1.018,
            "x": -12,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.018,
            "x": 12,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "sine.inOut",
        "intensity": 0.85,
    },
    # pull-out lent (révélation)
    {
        "start": {
            "scale": 1.032,
            "x": 0,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {"scale": 1.0, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0},
        "ease": "power3.inOut",
        "intensity": 0.92,
    },
    # pan vertical haut -> bas
    {
        "start": {
            "scale": 1.020,
            "x": 0,
            "y": 12,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.020,
            "x": 0,
            "y": -12,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "sine.inOut",
        "intensity": 0.90,
    },
    # push-in avec drift bas-droite (tension)
    {
        "start": {
            "scale": 1.0,
            "x": 0,
            "y": -6,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.030,
            "x": 10,
            "y": 8,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "power2.inOut",
        "intensity": 1.10,
    },
    # diagonale gauche-bas -> haut-droite
    {
        "start": {
            "scale": 1.018,
            "x": -10,
            "y": -8,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.018,
            "x": 10,
            "y": 8,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "sine.inOut",
        "intensity": 0.88,
    },
    # zoom serré (révélation forte)
    {
        "start": {
            "scale": 1.005,
            "x": 0,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.045,
            "x": -6,
            "y": 4,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "expo.out",
        "intensity": 1.20,
    },
    # drift très lent (plans contemplatifs)
    {
        "start": {
            "scale": 1.012,
            "x": 4,
            "y": -4,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.022,
            "x": -6,
            "y": 6,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "sine.inOut",
        "intensity": 0.75,
    },
    # push-in droite -> gauche (réorientation)
    {
        "start": {
            "scale": 1.008,
            "x": 12,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {
            "scale": 1.030,
            "x": -8,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "ease": "power2.inOut",
        "intensity": 1.05,
    },
    # statique + très léger souffle (preuve)
    {
        "start": {
            "scale": 1.000,
            "x": 0,
            "y": 0,
            "rotationY": 0,
            "rotationX": 0,
            "z": 0,
        },
        "end": {"scale": 1.012, "x": 0, "y": 0, "rotationY": 0, "rotationX": 0, "z": 0},
        "ease": "sine.out",
        "intensity": 0.70,
    },
]


def gsap_obj(d):
    """Convertit un dict Python en littéral d'objet GSAP."""
    return "{" + ", ".join(f"{k}: {v}" for k, v in d.items()) + "}"


def build_procedural_bg(scene_idx, scene_start, audio_duration, bg_type=None):
    """Génère un background procédural (pas d'image). Alterne 6 variantes."""
    if bg_type and bg_type in [
        "mesh",
        "lines",
        "topo",
        "dotgrid",
        "scanline",
        "minimal",
    ]:
        variant = bg_type
    else:
        variant = BG_VARIANTS[scene_idx % len(BG_VARIANTS)]
    bg_id = f"s{scene_idx + 1}_bg"
    inner = '<div class="pbg-scan"></div>' if variant == "scanline" else ""
    html = (
        f'<div id="{bg_id}" class="pbg pbg-{variant} clip" '
        f'data-start="{scene_start:.3f}" data-duration="{audio_duration:.3f}" '
        f'data-track-index="{scene_idx * 20 + 9}">{inner}</div>'
    )
    js = [
        f'gsap.set("#{bg_id}", {{opacity: 0}});',
        f'tl.set("#{bg_id}", {{opacity: 1}}, {scene_start:.3f});',
        f'tl.to("#{bg_id}", {{opacity: 0, duration: 0.8, ease: "power2.in"}}, {(scene_start + audio_duration - 0.4):.3f});',
        f'tl.set("#{bg_id}", {{opacity: 0}}, {(scene_start + audio_duration):.3f});',
    ]
    # Motion subtile selon la variante
    if variant == "mesh":
        # Drift très lent du gradient mesh
        js.append(
            f'tl.fromTo("#{bg_id}", {{backgroundPosition: "0% 0%"}}, '
            f'{{backgroundPosition: "100% 100%", duration: {audio_duration:.3f}, '
            f'ease: "none", overwrite: "auto"}}, {scene_start:.3f});'
        )
    elif variant == "dotgrid":
        js.append(
            f'tl.fromTo("#{bg_id}", {{backgroundPosition: "0px 0px"}}, '
            f'{{backgroundPosition: "40px 60px", duration: {audio_duration:.3f}, '
            f'ease: "none", overwrite: "auto"}}, {scene_start:.3f});'
        )
    elif variant == "scanline":
        # Scan vertical lent
        js.append(
            f'tl.fromTo("#{bg_id} .pbg-scan", {{y: "-30%"}}, '
            f'{{y: "130%", duration: {audio_duration:.3f}, ease: "none"}}, {scene_start:.3f});'
        )
    elif variant == "lines":
        js.append(
            f'tl.fromTo("#{bg_id}", {{backgroundPosition: "0px 0px"}}, '
            f'{{backgroundPosition: "0px 80px", duration: {audio_duration:.3f}, '
            f'ease: "none"}}, {scene_start:.3f});'
        )
    return html, js


def _act_grading_filter(scene_idx, total_scenes):
    """Retourne un CSS filter chain selon l'acte narratif.

    Default is now a darker, more restrained true-crime grade: less saturated,
    deeper blacks, and no warm/yellow climax. This reads more premium with
    low-poly 3D stills than the earlier colorful anime-style grading.
    """
    if not USE_ACT_GRADING or total_scenes <= 0:
        return "contrast(1.16) saturate(0.82) brightness(0.76)"
    progress = scene_idx / max(1, total_scenes - 1)
    if progress < 0.30:
        return "contrast(1.18) saturate(0.78) brightness(0.74) hue-rotate(2deg)"
    if progress < 0.70:
        return "contrast(1.20) saturate(0.76) brightness(0.72) hue-rotate(0deg)"
    return "contrast(1.22) saturate(0.72) brightness(0.70) hue-rotate(-2deg)"


def build_image_block(
    s_id,
    j,
    img_path,
    scene_idx,
    start,
    dur,
    is_last,
    in_transition_from_prev=False,
    total_scenes=10,
    source_type="",
    camera_move=None,
):
    """Génère HTML + GSAP pour 1 image avec Ken Burns + apparition instantanée.

    Le clip démarre légèrement avant le timecode du plan pour laisser Chromium
    charger/décoder l'image. Pendant cette avance, l'image reste à opacity:0;
    au vrai début du plan, un tl.set la passe immédiatement à opacity:1.
    """
    img_id = f"{s_id}_bg{j + 1}"

    variant = None
    if camera_move:
        camera_move = camera_move.lower()
        if "dolly_in" in camera_move:
            variant = MOTION_VARIANTS[0]
        elif "dolly_out" in camera_move:
            variant = MOTION_VARIANTS[2]
        elif "pan_left" in camera_move:
            variant = MOTION_VARIANTS[1]
        elif "pan_right" in camera_move:
            variant = MOTION_VARIANTS[7]
        elif "zoom_pan" in camera_move:
            variant = MOTION_VARIANTS[4]
        elif "static" in camera_move:
            variant = MOTION_VARIANTS[8]

    if not variant:
        # Hash déterministe mais désynchronisé entre scenes/plans pour casser
        # l'impression de "même mouvement à chaque fois". On combine scene_idx,
        # j, et un offset premier pour éviter toute périodicité visible.
        variant_idx = (scene_idx * 3 + j * 7 + scene_idx * j) % len(MOTION_VARIANTS)
        variant = MOTION_VARIANTS[variant_idx]
    tilt_table = [-0.28, 0.22, -0.14, 0.24, -0.18, 0.16, -0.20, 0.12]
    tilt = tilt_table[(scene_idx * 2 + j * 3) % len(tilt_table)]
    is_generated_media = "generated" in (source_type or "")

    # Rythme: les plans courts sont plus tendus (intensité +), les plans longs
    # plus calmes (intensité -). Une vidéo qui respire entre plans = beaucoup
    # plus pro qu'une vidéo où tout va à la même vitesse.
    base_intensity = float(variant.get("intensity", 1.0))
    if dur < 2.5:
        rhythm = 1.18
    elif dur < 4.5:
        rhythm = 1.08
    elif dur < 7.5:
        rhythm = 1.02
    else:
        rhythm = 0.96
    intensity = base_intensity * rhythm * MOTION_STRENGTH

    is_video = img_path.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm")
    if is_video:
        preload_lead = min(0.6, max(0.0, start))
        clip_start = max(0.0, start - preload_lead)
        clip_dur = dur + preload_lead + 0.3
    else:
        preload_lead = start
        clip_start = 0.0
        clip_dur = start + dur + 0.3

    # z-index croissant mais ≤ 19 pour rester SOUS les overlays sémantiques
    # (.sem-overlay z-index 22-25, .dir-layer 18 — l'image reste au fond, les
    # animations apparaissent par-dessus).
    z_index = scene_idx + 10

    start_state = {
        "opacity": 0 if preload_lead > 0 else 1,
        "rotation": round(tilt * 0.35, 3),
        "transformOrigin": '"50% 50%"',
        **variant["start"],
    }

    initial_opacity = 0 if preload_lead > 0 else 1
    if is_video:
        html = (
            f'<video id="{img_id}" class="bg clip {"media-ai" if is_generated_media else "media-real"}" src="assets/{img_id}{img_path.suffix}" '
            f"autoplay loop muted playsinline "
            f'style="opacity: {initial_opacity}; z-index: {z_index}; object-fit: contain; width: 100%; height: 100%; background: #050505;" '
            f'data-start="{clip_start:.3f}" data-duration="{clip_dur:.3f}" '
            f'data-track-index="{scene_idx * 20 + j}"></video>'
        )
    else:
        html = (
            f'<img id="{img_id}" class="bg clip {"media-ai" if is_generated_media else "media-real"}" src="assets/{img_id}{img_path.suffix}" '
            f'loading="eager" decoding="sync" fetchpriority="high" '
            f'style="opacity: {initial_opacity}; z-index: {z_index}; object-fit: contain; background: #050505;" '
            f'data-start="{clip_start:.3f}" data-duration="{clip_dur:.3f}" '
            f'data-track-index="{scene_idx * 20 + j}" />'
        )
    atmo_id = f"{img_id}_atmo"
    html += (
        f'<div id="{atmo_id}" class="motion-atmosphere clip" '
        f'style="opacity:0; z-index:{z_index + 1};" '
        f'data-start="{clip_start:.3f}" data-duration="{clip_dur:.3f}" '
        f'data-track-index="{4000 + scene_idx * 10 + j}"></div>'
    )

    grading = _act_grading_filter(scene_idx, total_scenes)
    if os.getenv("VISUAL_STYLE") == "noir":
        # Mode mystère B&W : désaturation totale + fort contraste
        grading = "grayscale(1) contrast(1.25) brightness(0.88)"
    elif is_generated_media:
        grading = f"{grading} saturate(1.08) contrast(1.06)"
    start_state["filter"] = f'"{grading}"'

    js = []
    js.append(f'gsap.set("#{img_id}", {gsap_obj(start_state)});')
    if preload_lead > 0:
        if is_generated_media or j > 0:
            js.append(
                f'tl.to("#{img_id}", {{opacity: 1, duration: 0.36, ease: "power2.out", overwrite: "auto"}}, {start:.3f});'
            )
        else:
            js.append(f'tl.set("#{img_id}", {{opacity: 1}}, {start:.3f});')
    else:
        # Force opacity:1 dans le timeline GSAP au moment exact où HyperFrames
        # rend l'élément visible. Garantit qu'au cut, l'image N+1 n'est jamais
        # transparente (sinon écran noir entre flash et image).
        js.append(f'tl.set("#{img_id}", {{opacity: 1}}, {start:.3f});')

    # Ken Burns éditorial: zoom/pan + tilt discret + grading respirant par acte.
    # On amplifie/atténue le mouvement avec `intensity` (issu du variant + du
    # rythme par durée) pour que chaque plan ait sa propre énergie.
    def _scale(v, around=0.0):
        return around + (float(v) - around) * intensity

    motion_props = {}
    raw_end = variant["end"]
    base_scale = float(raw_end.get("scale", 1.0))
    motion_props["scale"] = round(_scale(base_scale, around=1.0), 4)
    motion_props["x"] = round(_scale(raw_end.get("x", 0)), 2)
    motion_props["y"] = round(_scale(raw_end.get("y", 0)), 2)
    motion_props["rotationY"] = raw_end.get("rotationY", 0)
    motion_props["rotationX"] = raw_end.get("rotationX", 0)
    motion_props["z"] = raw_end.get("z", 0)

    if is_generated_media:
        # Les images IA supportent un mouvement 2,5D plus ample. L'amplitude
        # reste cinématique mais doit être immédiatement perceptible sur mobile.
        motion_props["scale"] = round(float(motion_props["scale"]) + 0.075, 4)
        motion_props["x"] = round(
            motion_props["x"] + (42 if (scene_idx + j) % 2 == 0 else -42), 2
        )
        motion_props["y"] = round(
            motion_props["y"] + (-28 if (scene_idx + j) % 2 == 0 else 28), 2
        )
        motion_props["rotationY"] = round(
            (1.35 if (scene_idx + j) % 2 == 0 else -1.35) * intensity, 3
        )
        motion_props["rotationX"] = round(
            (-0.70 if j % 2 == 0 else 0.70) * intensity, 3
        )
    else:
        # Médias réels: on plafonne le zoom pour préserver la lisibilité.
        motion_props["scale"] = min(float(motion_props["scale"]), 1.030)

    # Easing varié par variant + tilt léger.
    ease_name = variant.get("ease", "sine.inOut")
    motion_props["rotation"] = round(tilt * (0.6 + 0.4 * intensity), 3)
    motion_props["duration"] = round(dur, 3)
    motion_props["ease"] = f'"{ease_name}"'
    motion_props["overwrite"] = '"auto"'
    js.append(f'tl.to("#{img_id}", {gsap_obj(motion_props)}, {start:.3f});')

    # Brume en contre-mouvement : elle donne une profondeur 2,5D lisible sans
    # recouvrir le sujet ni ajouter de HUD.
    atmo_direction = 1 if (scene_idx + j) % 2 == 0 else -1
    js.append(
        f'gsap.set("#{atmo_id}", {{opacity:0, x:{-150 * atmo_direction}, '
        f"y:{30 if j % 2 == 0 else -30}, scale:1.04, rotation:{-3 * atmo_direction}}});"
    )
    js.append(
        f'tl.to("#{atmo_id}", {{opacity:0.28, duration:0.55, ease:"power2.out"}}, '
        f"{start:.3f});"
    )
    js.append(
        f'tl.to("#{atmo_id}", {{x:{150 * atmo_direction}, '
        f"y:{-36 if j % 2 == 0 else 36}, scale:1.24, rotation:{3 * atmo_direction}, duration:{dur:.3f}, "
        f'ease:"sine.inOut"}}, {start:.3f});'
    )
    js.append(
        f'tl.to("#{atmo_id}", {{opacity:0.36, duration:{max(0.35, dur * 0.20):.3f}, '
        f'ease:"sine.inOut", yoyo:true, repeat:1}}, '
        f"{(start + dur * 0.34):.3f});"
    )
    js.append(
        f'tl.to("#{atmo_id}", {{opacity:0, duration:0.45, ease:"power2.in"}}, '
        f"{max(start, start + dur - 0.45):.3f});"
    )

    # Masquer l'image proprement à la fin de sa durée pour éviter les chevauchements
    js.append(f'tl.set("#{img_id}", {{opacity: 0}}, {(start + dur):.3f});')
    js.append(f'tl.set("#{atmo_id}", {{opacity: 0}}, {(start + dur):.3f});')

    return html, js


def build_scene_director_fx(
    s_id, scene_idx, scene_start, audio_duration, subtitle_src, hud_effect="scanner"
):
    """Couches de réalisation déterministes : scan, cadre, lumière et dossier.
    Opt-in (USE_PERSISTENT_CASE_TAG=1) : DESIGN.md proscrit les HUD décoratifs."""
    if not USE_PERSISTENT_CASE_TAG:
        return [], []
    hud_effect = (hud_effect or "scanner").lower()
    case_no = f"{(scene_idx + 1) * 137:04d}-{(scene_idx * 73 + 19) % 97:02d}"
    severity = ["TRACE", "EVIDENCE", "ARCHIVE", "MISSING", "SEALED"][scene_idx % 5]
    side = "left" if scene_idx % 2 == 0 else "right"
    oid = f"{s_id}_dir"
    scan_id = f"{oid}_scan"
    pulse_id = f"{oid}_pulse"
    meta_id = f"{oid}_meta"
    rule_id = f"{oid}_rule"

    scan_html = (
        f'<div id="{scan_id}" class="dir-scan"></div>'
        if hud_effect == "scanner"
        else ""
    )
    pulse_html = (
        f'<div id="{pulse_id}" class="dir-pulse"></div>'
        if hud_effect == "radar"
        else ""
    )
    ticker_html = ""
    if hud_effect == "ticker":
        ticker_html = (
            f'<div id="{oid}_ticker" style="position:absolute; bottom:160px; right:48px; '
            f"font-family:var(--font-mono); font-size:16px; color:var(--accent); opacity:0.8; "
            f'letter-spacing:1px;">DECRYPTING: <span id="{oid}_t_val">0x0000</span></div>'
        )

    html = [
        (
            f'<div id="{oid}" class="dir-layer clip" '
            f'data-start="{scene_start:.3f}" data-duration="{audio_duration:.3f}" '
            f'data-track-index="{scene_idx * 20 + 12}">'
            f'<div class="dir-corner tl"></div><div class="dir-corner tr"></div>'
            f'<div class="dir-corner bl"></div><div class="dir-corner br"></div>'
            f"{scan_html}"
            f"{pulse_html}"
            f"{ticker_html}"
            f'<div id="{meta_id}" class="dir-meta {side}">'
            f"<span>CASE {case_no}</span><strong>{severity}</strong>"
            f"</div>"
            f'<div id="{rule_id}" class="dir-rule"></div>'
            f"</div>"
        )
    ]

    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{meta_id}", {{opacity: 0, y: -18}});',
        f'gsap.set("#{rule_id}", {{scaleX: 0, transformOrigin: "50% 50%"}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.45, ease: "power2.out"}}, {scene_start:.3f});',
        f'tl.to("#{meta_id}", {{opacity: 1, y: 0, duration: 0.55, ease: "power3.out"}}, {(scene_start + 0.18):.3f});',
        f'tl.to("#{rule_id}", {{scaleX: 1, duration: 0.7, ease: "expo.out"}}, {(scene_start + 0.25):.3f});',
    ]

    if hud_effect == "scanner":
        js.extend(
            [
                f'gsap.set("#{scan_id}", {{y: -260, opacity: 0}});',
                f'tl.to("#{scan_id}", {{y: 2100, opacity: 0.65, duration: {min(audio_duration * 0.72, 7.5):.3f}, ease: "power1.inOut"}}, {(scene_start + 0.5):.3f});',
            ]
        )
    elif hud_effect == "radar":
        pulse_in = scene_start + max(0.8, audio_duration * 0.34)
        pulse_out = pulse_in + 1.12
        js.extend(
            [
                f'gsap.set("#{pulse_id}", {{scale: 0.85, opacity: 0}});',
                f'tl.to("#{pulse_id}", {{opacity: 0.28, scale: 1.18, duration: 1.1, ease: "sine.out", overwrite: "auto"}}, {pulse_in:.3f});',
                f'tl.to("#{pulse_id}", {{opacity: 0, scale: 1.55, duration: 0.85, ease: "power2.in", overwrite: "auto"}}, {pulse_out:.3f});',
                f'tl.set("#{pulse_id}", {{opacity: 0}}, {(scene_start + audio_duration):.3f});',
            ]
        )
    elif hud_effect == "ticker":
        ticker_val_id = f"{oid}_t_val"
        js.extend(
            [
                f"const {oid}_t_obj = {{val: 0}};",
                f'tl.to({oid}_t_obj, {{val: 65535, duration: {audio_duration:.3f}, ease: "none", '
                f'onUpdate: () => {{ const el = document.getElementById("{ticker_val_id}"); '
                f'if (el) el.innerText = "0x" + Math.floor({oid}_t_obj.val).toString(16).toUpperCase(); }}}}, '
                f"{scene_start:.3f});",
            ]
        )

    js.extend(
        [
            f'tl.to("#{meta_id}", {{opacity: 0, y: -12, duration: 0.35, ease: "power2.in"}}, {(scene_start + audio_duration - 0.55):.3f});',
            f'tl.to("#{oid}", {{opacity: 0, duration: 0.45, ease: "power2.in"}}, {(scene_start + audio_duration - 0.45):.3f});',
            f'tl.set("#{oid}", {{opacity: 0}}, {(scene_start + audio_duration):.3f});',
        ]
    )
    return html, js
