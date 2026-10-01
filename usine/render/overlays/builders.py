"""Générateurs HTML/GSAP des overlays sémantiques et table de dispatch OVERLAY_BUILDERS."""

import re
from usine.render.overlays.catalog import (
    SEMANTIC_ANIMATION_TYPES,
    SEMANTIC_META,
    _diversify_overlay_types,
    _prepare_overlay_schedule,
)
from usine.render.overlays.detection import _fold_text, detect_overlays
from usine.render.text import ICONS, html_escape


def _sem_slug(value):
    return re.sub(r"[^a-z0-9]+", "_", _fold_text(value)).strip("_") or "item"


def _sem_timing(scene_start, audio_duration, spec, offset=0.6, preferred=4.4):
    if "_start_offset" in spec and "_duration" in spec:
        return scene_start + float(spec["_start_offset"]), float(spec["_duration"])
    idx = int(spec.get("idx", 0))
    if audio_duration <= 1.4:
        return scene_start + 0.08, max(0.7, audio_duration - 0.16)
    local_offset = min(offset + idx * 0.36, max(0.18, audio_duration * 0.35))
    remaining = max(0.9, audio_duration - local_offset - 0.28)
    return scene_start + local_offset, max(1.0, min(preferred, remaining))


def _sem_track(scene_idx, spec):
    return scene_idx * 20 + 15 + int(spec.get("idx", 0))


def _sem_meta(spec):
    return SEMANTIC_META.get(spec.get("type"), SEMANTIC_META["timeline_pin"])


def _sem_icon(spec):
    return ICONS.get(_sem_meta(spec).get("icon", "file"), ICONS["file"])


def _sem_label(spec):
    return html_escape(str(spec.get("label") or _sem_meta(spec)["label"]))


def _sem_detail(spec):
    return html_escape(str(spec.get("detail") or _sem_meta(spec)["detail"]))


def _sem_exit_js(oid, start, dur, outro="y"):
    exit_at = max(start + 0.35, start + dur - 0.45)
    if outro == "scale":
        return [
            f'tl.to("#{oid}", {{opacity: 0, scale: 0.92, duration: 0.42, ease: "power2.in"}}, {exit_at:.3f});',
            f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
        ]
    if outro == "x":
        return [
            f'tl.to("#{oid}", {{opacity: 0, x: -60, duration: 0.42, ease: "power2.in"}}, {exit_at:.3f});',
            f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
        ]
    return [
        f'tl.to("#{oid}", {{opacity: 0, y: -28, duration: 0.42, ease: "power2.in"}}, {exit_at:.3f});',
        f'tl.set("#{oid}", {{opacity: 0}}, {(start + dur):.3f});',
    ]


def _project_lnglat(lnglat):
    if not lnglat:
        return 540, 770
    lng, lat = lnglat
    x = 130 + ((float(lng) + 180.0) / 360.0) * 820
    y = 360 + ((90.0 - float(lat)) / 180.0) * 860
    return int(max(130, min(950, x))), int(max(360, min(1220, y)))


def _ov_sem_map_zoom(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_map_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.18, preferred=5.2
    )
    label = html_escape(spec.get("value", "ZONE"))
    coords = html_escape(spec.get("coords", "COORDONNÉES INCONNUES"))
    region = html_escape(spec.get("region") or "SECTOR")
    iso = html_escape(spec.get("iso") or "GEO")
    route_label = html_escape(spec.get("route_label", ""))
    route_count = int(spec.get("route_count") or 0)
    badge = html_escape(spec.get("badge", ""))
    x, y = _project_lnglat(spec.get("lnglat"))
    route_block = (
        f'<div class="sem-map-route-copy"><span>TRAJET</span><strong>{route_label}</strong>'
        f"<em>{route_count} lieux détectés</em></div>"
        if route_label
        else ""
    )
    badge_block = f'<div class="sem-map-badge">{badge}</div>' if badge else ""
    html = (
        f'<div id="{oid}" class="sem-overlay sem-map clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div id="{oid}_grid" class="sem-map-grid"></div>'
        f'<svg class="sem-map-lines" viewBox="0 0 1080 1920" preserveAspectRatio="none">'
        f'<path id="{oid}_route" d="M140 1390 C330 1050 420 920 {x} {y} S760 520 940 360" />'
        f'<circle cx="{x}" cy="{y}" r="92" class="sem-map-ring" id="{oid}_ring"/>'
        f"</svg>"
        f'<div class="sem-map-cross" style="left:{x}px; top:{y}px;"></div>'
        f'<div class="sem-map-dot" id="{oid}_dot" style="left:{x}px; top:{y}px;"></div>'
        f'<div class="sem-map-label" id="{oid}_label">'
        f'<div class="sem-kicker">GEO LOCK · {iso}</div>'
        f'<div class="sem-map-title">{label}</div>'
        f'<div class="sem-map-coords">{coords} · {region}</div>'
        f"{badge_block}"
        f"</div>"
        f"{route_block}"
        f'<div class="sem-map-readout">SAT LINK / ADAPTIVE LOCATION / TARGET ACQUIRED</div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{oid}_grid", {{scale: 0.72, x: {(540 - x) * 0.12:.1f}, y: {(790 - y) * 0.12:.1f}, transformOrigin: "{x}px {y}px"}});',
        f'gsap.set("#{oid}_route", {{drawSVG: "0%"}});'
        if False
        else f'gsap.set("#{oid}_route", {{strokeDasharray: 1800, strokeDashoffset: 1800}});',
        f'gsap.set("#{oid}_dot", {{scale: 0, opacity: 0}});',
        f'gsap.set("#{oid}_label", {{opacity: 0, y: 24}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.35, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid}_grid", {{scale: 1.34, x: {(540 - x) * 0.42:.1f}, y: {(790 - y) * 0.42:.1f}, duration: {dur:.3f}, ease: "power2.inOut"}}, {start:.3f});',
        f'tl.to("#{oid}_route", {{strokeDashoffset: 0, duration: 1.15, ease: "power2.out"}}, {(start + 0.32):.3f});',
        f'tl.to("#{oid}_dot", {{opacity: 1, scale: 1, duration: 0.34, ease: "back.out(2)"}}, {(start + 0.78):.3f});',
        f'tl.fromTo("#{oid}_ring", {{scale: 0.35, opacity: 0.95, transformOrigin: "50% 50%"}}, {{scale: 1.7, opacity: 0, duration: 0.95, repeat: 3, ease: "power2.out"}}, {(start + 0.84):.3f});',
        f'tl.to("#{oid}_label", {{opacity: 1, y: 0, duration: 0.48, ease: "power3.out"}}, {(start + 0.88):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_message(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_msg_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.5
    )
    body = html_escape(spec.get("body") or "Message envoyé.")
    html = (
        f'<div id="{oid}" class="sem-overlay sem-message clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-phone">'
        f'<div class="sem-phone-bar"></div>'
        f'<div class="sem-chat">'
        f'<div class="sem-chat-meta">ENVOI SÉCURISÉ</div>'
        f'<div id="{oid}_bubble" class="sem-bubble"><span id="{oid}_text">{body}</span></div>'
        f'<div id="{oid}_send" class="sem-send-row"><span></span><strong>ENVOYÉ</strong></div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: 44, scale: 0.96}});',
        f'gsap.set("#{oid}_bubble", {{clipPath: "inset(0 100% 0 0)"}});',
        f'gsap.set("#{oid}_send", {{opacity: 0, x: -16}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, scale: 1, duration: 0.45, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_bubble", {{clipPath: "inset(0 0% 0 0)", duration: 1.2, ease: "steps(18)"}}, {(start + 0.42):.3f});',
        f'tl.to("#{oid}_send", {{opacity: 1, x: 0, duration: 0.32, ease: "power2.out"}}, {(start + 1.72):.3f});',
        f'tl.to("#{oid}_send span", {{scale: 1.7, opacity: 0, duration: 0.55, repeat: 1, ease: "power2.out"}}, {(start + 1.82):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_year(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_year_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.65, preferred=4.2
    )
    value = html_escape(spec.get("value", "----"))
    html = (
        f'<div id="{oid}" class="sem-overlay sem-year clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-kicker">TIMELINE LOCK</div>'
        f'<div class="sem-year-num">{value}</div>'
        f'<div class="sem-year-rule" id="{oid}_rule"></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: -34, filter: "blur(10px)"}});',
        f'gsap.set("#{oid}_rule", {{scaleX: 0, transformOrigin: "center"}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, filter: "blur(0px)", duration: 0.58, ease: "expo.out"}}, {start:.3f});',
        f'tl.to("#{oid}_rule", {{scaleX: 1, duration: 0.72, ease: "power3.out"}}, {(start + 0.16):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur))
    return [html], js


def _ov_sem_counter(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_counter_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.76, preferred=4.3
    )
    try:
        final_val = int(re.sub(r"\D", "", str(spec.get("value", "0"))))
    except ValueError:
        final_val = 0
    html = (
        f'<div id="{oid}" class="sem-overlay sem-counter clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-kicker">QUANTIFICATION</div>'
        f'<div class="sem-counter-num" id="{oid}_num">0</div>'
        f'<div class="sem-meter"><div id="{oid}_bar"></div></div>'
        f"</div>"
    )
    js = [
        f"const {oid}_obj = {{val: 0}};",
        f'gsap.set("#{oid}", {{opacity: 0, x: 48}});',
        f'gsap.set("#{oid}_bar", {{scaleX: 0, transformOrigin: "left"}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, duration: 0.45, ease: "power3.out"}}, {start:.3f});',
        f'tl.to({oid}_obj, {{val: {final_val}, duration: 1.55, ease: "power2.out", onUpdate: () => {{ const el = document.getElementById("{oid}_num"); if (el) el.innerText = Math.floor({oid}_obj.val).toLocaleString("fr-FR"); }}}}, {(start + 0.24):.3f});',
        f'tl.to("#{oid}_bar", {{scaleX: 1, duration: 1.55, ease: "power2.out"}}, {(start + 0.24):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_cctv(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_cctv_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.52, preferred=4.8
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-cctv clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-cctv-frame">'
        f'<div class="sem-cctv-head"><span>CAM 03</span><strong>REC</strong></div>'
        f'<div class="sem-cctv-screen">'
        f'<div id="{oid}_scan" class="sem-cctv-scan"></div>'
        f'<div id="{oid}_box1" class="sem-cctv-box one"></div>'
        f'<div id="{oid}_box2" class="sem-cctv-box two"></div>'
        f"</div>"
        f'<div class="sem-cctv-foot">FRAME ANALYSIS / EXIT NOT CONFIRMED</div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 0.96}});',
        f'gsap.set("#{oid}_scan", {{y: -260}});',
        f'gsap.set("#{oid}_box1, #{oid}_box2", {{opacity: 0, scale: 0.88}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, duration: 0.45, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_scan", {{y: 290, duration: 1.05, repeat: 2, ease: "none"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid}_box1", {{opacity: 1, scale: 1, duration: 0.22, repeat: 3, yoyo: true, ease: "steps(1)"}}, {(start + 0.55):.3f});',
        f'tl.to("#{oid}_box2", {{opacity: 1, scale: 1, duration: 0.18, repeat: 4, yoyo: true, ease: "steps(1)"}}, {(start + 0.82):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_file(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_file_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.4
    )
    label = _sem_label(spec)
    detail = _sem_detail(spec)
    html = (
        f'<div id="{oid}" class="sem-overlay sem-file clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-file-back" id="{oid}_b1"></div><div class="sem-file-back two" id="{oid}_b2"></div>'
        f'<div class="sem-file-front">'
        f'<div class="sem-file-tab">{label}</div>'
        f'<div class="sem-file-line"></div><div class="sem-file-line short"></div><div class="sem-file-line mid"></div>'
        f'<div class="sem-file-stamp">{detail}</div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: 70, rotation: 4}});',
        f'gsap.set("#{oid}_b1", {{opacity: 0, x: -10, y: -8, rotation: -4}});',
        f'gsap.set("#{oid}_b2", {{opacity: 0, x: 10, y: -6, rotation: 5}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, rotation: 0, duration: 0.48, ease: "back.out(1.45)"}}, {start:.3f});',
        f'tl.to("#{oid}_b1", {{opacity: 0.9, x: -42, y: -34, duration: 0.52, ease: "power2.out"}}, {(start + 0.26):.3f});',
        f'tl.to("#{oid}_b2", {{opacity: 0.82, x: 44, y: -28, duration: 0.52, ease: "power2.out"}}, {(start + 0.34):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_redacted(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_redact_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.58, preferred=3.8
    )
    bars = "".join(
        f'<div class="sem-redact-bar" id="{oid}_b{i}" style="top:{42 + i * 48}px; width:{340 + (i * 86) % 310}px;"></div>'
        for i in range(5)
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-redacted clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'{bars}<div id="{oid}_stamp" class="sem-redact-stamp">{_sem_label(spec)}</div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 1}});',
        f'gsap.set("#{oid}_stamp", {{opacity: 0, scale: 0.72, rotation: -8}});',
    ]
    for i in range(5):
        js.append(f'gsap.set("#{oid}_b{i}", {{scaleX: 0, transformOrigin: "left"}});')
        js.append(
            f'tl.to("#{oid}_b{i}", {{scaleX: 1, duration: 0.22, ease: "power3.out"}}, {(start + 0.08 + i * 0.09):.3f});'
        )
    js.append(
        f'tl.to("#{oid}_stamp", {{opacity: 1, scale: 1, duration: 0.32, ease: "back.out(2)"}}, {(start + 0.64):.3f});'
    )
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_radar(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_radar_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.64, preferred=4.5
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-radar clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-radar-dish">'
        f'<div class="sem-radar-ring r1"></div><div class="sem-radar-ring r2"></div><div class="sem-radar-ring r3"></div>'
        f'<div id="{oid}_sweep" class="sem-radar-sweep"></div>'
        f'<div class="sem-radar-blip b1"></div><div class="sem-radar-blip b2"></div>'
        f"</div>"
        f'<div class="sem-radar-copy"><div class="sem-kicker">{_sem_label(spec)}</div><strong>{_sem_detail(spec)}</strong></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 0.84}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, duration: 0.42, ease: "back.out(1.5)"}}, {start:.3f});',
        f'tl.to("#{oid}_sweep", {{rotation: 360, duration: 1.25, repeat: 3, ease: "none"}}, {(start + 0.12):.3f});',
        f'tl.fromTo("#{oid} .sem-radar-blip", {{opacity: 0}}, {{opacity: 1, duration: 0.18, stagger: 0.22, repeat: 5, yoyo: true, ease: "steps(1)"}}, {(start + 0.42):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_search(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_search_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.62, preferred=4.4
    )
    cells = "".join(
        f'<div class="sem-search-cell" id="{oid}_c{i}"></div>' for i in range(12)
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-search clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-search-title"><span>{_sem_label(spec)}</span><strong>{_sem_detail(spec)}</strong></div>'
        f'<div class="sem-search-grid">{cells}</div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{oid} .sem-search-cell", {{opacity: 0, scale: 0.86}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.32, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-search-cell", {{opacity: 1, scale: 1, duration: 0.16, stagger: 0.055, ease: "power2.out"}}, {(start + 0.22):.3f});',
        f'tl.to("#{oid} .sem-search-cell:nth-child(7)", {{backgroundColor: "rgba(255,56,56,0.22)", borderColor: "rgba(255,56,56,0.9)", duration: 0.22, repeat: 4, yoyo: true, ease: "steps(1)"}}, {(start + 1.02):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_depth(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_depth_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.62, preferred=4.6
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-depth clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-depth-copy"><div class="sem-kicker">{_sem_label(spec)}</div><strong>{_sem_detail(spec)}</strong></div>'
        f'<div class="sem-depth-shaft"><div id="{oid}_fill" class="sem-depth-fill"></div><div id="{oid}_marker" class="sem-depth-marker">LEVEL -07</div></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: -32}});',
        f'gsap.set("#{oid}_fill", {{scaleY: 0, transformOrigin: "top"}});',
        f'gsap.set("#{oid}_marker", {{y: -210, opacity: 0}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, duration: 0.42, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_fill", {{scaleY: 1, duration: 1.25, ease: "power2.inOut"}}, {(start + 0.28):.3f});',
        f'tl.to("#{oid}_marker", {{y: 0, opacity: 1, duration: 1.25, ease: "power2.inOut"}}, {(start + 0.28):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_route(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_route_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.74, preferred=4.6
    )
    value = html_escape(spec.get("value") or "TRAJET RECONSTRUIT")
    detail = _sem_detail(spec)
    html = (
        f'<div id="{oid}" class="sem-overlay sem-route clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<svg viewBox="0 0 520 260"><path id="{oid}_path" d="M38 200 C150 70 265 235 470 62"/><circle cx="38" cy="200" r="8"/><circle cx="470" cy="62" r="8"/></svg>'
        f'<div class="sem-route-copy"><div class="sem-kicker">{_sem_label(spec)}</div><strong>{value}</strong><span>{detail}</span></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: 24}});',
        f'gsap.set("#{oid}_path", {{strokeDasharray: 760, strokeDashoffset: 760}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, duration: 0.42, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_path", {{strokeDashoffset: 0, duration: 1.25, ease: "power2.out"}}, {(start + 0.24):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur))
    return [html], js


def _ov_sem_question(s_id, scene_idx, scene_start, audio_duration, spec):
    oid = f"{s_id}_sem_question_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.2
    )
    value = html_escape(spec.get("value") or "HYPOTHÈSE OUVERTE")
    html = (
        f'<div id="{oid}" class="sem-overlay sem-question clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div id="{oid}_mark" class="sem-question-mark">?</div>'
        f'<div class="sem-question-copy"><div class="sem-kicker">{_sem_label(spec)}</div><strong>{value}</strong><span>{_sem_detail(spec)}</span></div>'
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{oid}_mark", {{scale: 0.7, rotation: -8}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.32, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid}_mark", {{scale: 1, rotation: 0, duration: 0.55, ease: "back.out(1.8)"}}, {(start + 0.08):.3f});',
        f'tl.to("#{oid}_mark", {{scale: 1.06, duration: 0.48, repeat: 3, yoyo: true, ease: "sine.inOut"}}, {(start + 0.72):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_card(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.1
    )
    value = html_escape(str(spec.get("value") or _sem_detail(spec)))
    role = html_escape(str(spec.get("role") or "STATUS ACTIVE"))
    html = (
        f'<div id="{oid}" class="sem-overlay sem-card sem-{slug} clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-card-icon">{_sem_icon(spec)}</div>'
        f'<div class="sem-card-body">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<strong>{value}</strong>"
        f"<span>{role}</span>"
        f'<div class="sem-card-bars"><i id="{oid}_b1"></i><i id="{oid}_b2"></i><i id="{oid}_b3"></i></div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: 54, skewX: -5}});',
        f'gsap.set("#{oid} .sem-card-bars i", {{scaleX: 0, transformOrigin: "left"}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, skewX: 0, duration: 0.44, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-card-icon", {{scale: 1.08, duration: 0.38, repeat: 2, yoyo: true, ease: "sine.inOut"}}, {(start + 0.35):.3f});',
        f'tl.to("#{oid} .sem-card-bars i", {{scaleX: 1, duration: 0.28, stagger: 0.08, ease: "power2.out"}}, {(start + 0.42):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_poster(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_poster_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.2
    )
    label = _sem_label(spec)
    detail = _sem_detail(spec)
    html = (
        f'<div id="{oid}" class="sem-overlay sem-poster clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-poster-sheet">'
        f'<div class="sem-poster-top">{label}</div>'
        f'<div class="sem-poster-face"><span></span><i id="{oid}_scan"></i></div>'
        f'<div class="sem-poster-name">{detail}</div>'
        f'<div class="sem-poster-lines"><b></b><b></b><b></b></div>'
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: -56, rotation: -2}});',
        f'gsap.set("#{oid}_scan", {{y: -120}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, rotation: 0, duration: 0.42, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_scan", {{y: 130, duration: 0.95, repeat: 1, ease: "power1.inOut"}}, {(start + 0.34):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_blueprint(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_blue_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.15
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-blueprint clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-blue-card">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f'<svg viewBox="0 0 420 260">'
        f'<path id="{oid}_p1" d="M34 44 H380 V218 H34 Z M120 44 V218 M246 44 V142 H380 M120 132 H246" />'
        f'<path id="{oid}_p2" d="M62 190 C128 142 184 166 236 118 S312 90 362 70" />'
        f'<circle cx="236" cy="118" r="12" />'
        f"</svg>"
        f"<strong>{_sem_detail(spec)}</strong>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, y: 26}});',
        f'gsap.set("#{oid}_p1, #{oid}_p2", {{strokeDasharray: 900, strokeDashoffset: 900}});',
        f'tl.to("#{oid}", {{opacity: 1, y: 0, duration: 0.40, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid}_p1", {{strokeDashoffset: 0, duration: 0.9, ease: "power2.out"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid}_p2", {{strokeDashoffset: 0, duration: 0.75, ease: "power2.out"}}, {(start + 0.56):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur))
    return [html], js


def _ov_sem_signal(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_signal_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.25
    )
    bars = "".join(
        f'<i id="{oid}_w{i}" style="height:{24 + ((i * 37) % 92)}px"></i>'
        for i in range(18)
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-signal clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-signal-card">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f'<div class="sem-wave">{bars}</div>'
        f"<strong>{_sem_detail(spec)}</strong>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 0.96}});',
        f'gsap.set("#{oid} .sem-wave i", {{scaleY: 0.18, transformOrigin: "50% 50%"}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, duration: 0.38, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-wave i", {{scaleY: 1, duration: 0.22, stagger: 0.025, repeat: 8, yoyo: true, ease: "sine.inOut"}}, {(start + 0.25):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_experiment(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_exp_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.25
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-experiment clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-exp-core">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f'<div class="sem-exp-rings"><i></i><i></i><i></i><b id="{oid}_needle"></b></div>'
        f"<strong>{_sem_detail(spec)}</strong>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, filter: "blur(6px)"}});',
        f'gsap.set("#{oid}_needle", {{rotation: -32, transformOrigin: "50% 100%"}});',
        f'tl.to("#{oid}", {{opacity: 1, filter: "blur(0px)", duration: 0.40, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-exp-rings i", {{scale: 1.18, opacity: 0.22, duration: 0.62, stagger: 0.12, repeat: 3, yoyo: true, ease: "sine.inOut"}}, {(start + 0.28):.3f});',
        f'tl.to("#{oid}_needle", {{rotation: 38, duration: 1.1, repeat: 2, yoyo: true, ease: "power1.inOut"}}, {(start + 0.30):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_caseboard(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_board_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=3.1
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-board clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-board-panel">'
        f'<div class="sem-kicker">{_sem_label(spec)}</div>'
        f'<div class="sem-board-nodes"><span></span><span></span><span></span><i id="{oid}_line"></i></div>'
        f"<strong>{_sem_detail(spec)}</strong>"
        f"</div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: 42}});',
        f'gsap.set("#{oid} .sem-board-nodes span", {{scale: 0, opacity: 0}});',
        f'gsap.set("#{oid}_line", {{scaleX: 0, transformOrigin: "left"}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, duration: 0.40, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-board-nodes span", {{scale: 1, opacity: 1, duration: 0.22, stagger: 0.12, ease: "back.out(2)"}}, {(start + 0.25):.3f});',
        f'tl.to("#{oid}_line", {{scaleX: 1, duration: 0.55, ease: "power2.out"}}, {(start + 0.48):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_satellite(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_sat_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=5.4
    )
    title = html_escape(str(spec.get("value") or _sem_label(spec)))
    detail = html_escape(
        str(spec.get("coords") or spec.get("detail") or _sem_detail(spec))
    )
    route = html_escape(str(spec.get("route_label") or "BALAYAGE EN COURS"))
    html = (
        f'<div id="{oid}" class="sem-overlay sem-satellite clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-sat-grid"></div>'
        f'<div class="sem-sat-orbit"><i></i><i></i><i></i><b id="{oid}_sweep"></b><em></em></div>'
        f'<div class="sem-sat-copy"><div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<strong>{title}</strong><span>{detail}</span><small>{route}</small></div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, scale: 1.04, filter: "blur(5px)"}});',
        f'gsap.set("#{oid} .sem-sat-copy", {{opacity: 0, y: 28}});',
        f'gsap.set("#{oid} .sem-sat-orbit", {{scale: 0.76, opacity: 0}});',
        f'tl.to("#{oid}", {{opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.55, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-sat-orbit", {{scale: 1, opacity: 1, duration: 0.8, ease: "expo.out"}}, {(start + 0.12):.3f});',
        f'tl.to("#{oid}_sweep", {{rotation: 720, duration: {max(3.2, dur - 0.55):.3f}, ease: "none"}}, {(start + 0.30):.3f});',
        f'tl.to("#{oid} .sem-sat-copy", {{opacity: 1, y: 0, duration: 0.55, ease: "power3.out"}}, {(start + 0.55):.3f});',
        f'tl.to("#{oid} .sem-sat-orbit em", {{scale: 2.2, opacity: 0, duration: 1.15, repeat: {max(1, int(dur // 1.3))}, ease: "power2.out"}}, {(start + 0.72):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_security_matrix(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_sec_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.75
    )
    rows = "".join(
        f'<li id="{oid}_r{i}"><span>{(scene_idx + 2) * 11 + i:02d}:{(i * 7) % 60:02d}:{(i * 13) % 60:02d}</span>'
        f"<b>{'MOUVEMENT' if i == 3 else 'AUCUN SIGNAL'}</b></li>"
        for i in range(7)
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-security clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-security-panel"><div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<ul>{rows}</ul><strong>{_sem_detail(spec)}</strong></div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, x: -42}});',
        f'gsap.set("#{oid} li", {{opacity: 0, x: -18}});',
        f'tl.to("#{oid}", {{opacity: 1, x: 0, duration: 0.42, ease: "power3.out"}}, {start:.3f});',
        f'tl.to("#{oid} li", {{opacity: 1, x: 0, duration: 0.18, stagger: 0.13, ease: "power2.out"}}, {(start + 0.22):.3f});',
        f'tl.to("#{oid}_r3", {{backgroundColor: "rgba(255,56,56,0.22)", duration: 0.18, repeat: 6, yoyo: true, ease: "steps(1)"}}, {(start + 1.25):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="x"))
    return [html], js


def _ov_sem_timewarp(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_time_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.55
    )
    value = html_escape(str(spec.get("value") or "DATE"))
    html = (
        f'<div id="{oid}" class="sem-overlay sem-timewarp clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-time-lines"><i></i><i></i><i></i><i></i></div>'
        f'<div class="sem-time-copy"><div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<strong>{value}</strong><span>{_sem_detail(spec)}</span></div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0, perspective: 900}});',
        f'gsap.set("#{oid} .sem-time-lines i", {{scaleY: 0, transformOrigin: "50% 50%"}});',
        f'gsap.set("#{oid} .sem-time-copy", {{opacity: 0, y: 34, rotationX: -18}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.35, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid} .sem-time-lines i", {{scaleY: 1, duration: 0.42, stagger: 0.08, ease: "expo.out"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid} .sem-time-copy", {{opacity: 1, y: 0, rotationX: 0, duration: 0.65, ease: "back.out(1.7)"}}, {(start + 0.45):.3f});',
        f'tl.to("#{oid} .sem-time-lines", {{x: 42, duration: {max(3.0, dur - 0.8):.3f}, ease: "sine.inOut"}}, {(start + 0.7):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur, outro="scale"))
    return [html], js


def _ov_sem_blackout(s_id, scene_idx, scene_start, audio_duration, spec):
    slug = _sem_slug(spec.get("type"))
    oid = f"{s_id}_sem_black_{slug}_{spec.get('idx', 0)}"
    start, dur = _sem_timing(
        scene_start, audio_duration, spec, offset=0.72, preferred=4.5
    )
    html = (
        f'<div id="{oid}" class="sem-overlay sem-blackout clip" '
        f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
        f'data-track-index="{_sem_track(scene_idx, spec)}">'
        f'<div class="sem-black-veil"></div><div id="{oid}_beam" class="sem-black-beam"></div>'
        f'<div class="sem-black-copy"><div class="sem-kicker">{_sem_label(spec)}</div>'
        f"<strong>{_sem_detail(spec)}</strong></div>"
        f"</div>"
    )
    js = [
        f'gsap.set("#{oid}", {{opacity: 0}});',
        f'gsap.set("#{oid}_beam", {{x: -260, rotation: -12, opacity: 0}});',
        f'gsap.set("#{oid} .sem-black-copy", {{opacity: 0, y: 18}});',
        f'tl.to("#{oid}", {{opacity: 1, duration: 0.28, ease: "power2.out"}}, {start:.3f});',
        f'tl.to("#{oid}_beam", {{opacity: 1, x: 720, rotation: 7, duration: {max(2.8, dur - 0.7):.3f}, ease: "sine.inOut"}}, {(start + 0.18):.3f});',
        f'tl.to("#{oid} .sem-black-copy", {{opacity: 1, y: 0, duration: 0.45, ease: "power3.out"}}, {(start + 0.42):.3f});',
    ]
    js.extend(_sem_exit_js(oid, start, dur))
    return [html], js


OVERLAY_BUILDERS = {otype: _ov_sem_card for otype in SEMANTIC_ANIMATION_TYPES}
OVERLAY_BUILDERS.update(
    {
        "map_zoom": _ov_sem_map_zoom,
        "satellite_sweep": _ov_sem_satellite,
        "map_pin_drop": _ov_sem_satellite,
        "coordinates_lock": _ov_sem_satellite,
        "proximity_alert": _ov_sem_satellite,
        "message_send": _ov_sem_message,
        "year_marker": _ov_sem_year,
        "calendar_flip": _ov_sem_timewarp,
        "time_jump": _ov_sem_timewarp,
        "counter": _ov_sem_counter,
        "cctv_scan": _ov_sem_cctv,
        "security_log": _ov_sem_security_matrix,
        "motion_detector": _ov_sem_security_matrix,
        "file_open": _ov_sem_file,
        "evidence_photo": _ov_sem_file,
        "newspaper_clip": _ov_sem_file,
        "court_record": _ov_sem_file,
        "archive_box": _ov_sem_file,
        "archive_stamp": _ov_sem_file,
        "object_isolate": _ov_sem_file,
        "document_leak": _ov_sem_file,
        "breaking_news": _ov_sem_file,
        "redacted_report": _ov_sem_redacted,
        "classified_stamp": _ov_sem_redacted,
        "entity_radar": _ov_sem_radar,
        "radio_signal": _ov_sem_radar,
        "audio_waveform": _ov_sem_radar,
        "search_grid": _ov_sem_search,
        "underground_depth": _ov_sem_depth,
        "route_trace": _ov_sem_route,
        "footprint_trail": _ov_sem_route,
        "question_prompt": _ov_sem_question,
        "power_cut": _ov_sem_blackout,
        "neon_bar": _ov_sem_blackout,
        "searchlight": _ov_sem_blackout,
    }
)
for _otype in ("missing_person", "missing_poster", "last_seen_marker", "family_photo"):
    OVERLAY_BUILDERS[_otype] = _ov_sem_poster
for _otype in (
    "floor_plan",
    "exit_scan",
    "blind_spot",
    "corridor_scan",
    "door_open",
    "sealed_door",
    "basement_elevator",
):
    OVERLAY_BUILDERS[_otype] = _ov_sem_blueprint
for _otype in (
    "audio_waveform",
    "radio_signal",
    "voice_print",
    "signal_jammer",
    "phone_call",
    "heartbeat_monitor",
    "crowd_noise",
    "room_tone",
):
    OVERLAY_BUILDERS[_otype] = _ov_sem_signal
for _otype in (
    "medical_scan",
    "lab_sample",
    "mind_control",
    "memory_flash",
    "experiment_chamber",
    "thermal_scan",
    "dna_spiral",
    "timeline_split",
):
    OVERLAY_BUILDERS[_otype] = _ov_sem_experiment
for _otype in (
    "interrogation_note",
    "witness_card",
    "witness_quote",
    "case_board",
    "evidence_thread",
    "theory_stack",
    "official_denial",
):
    OVERLAY_BUILDERS[_otype] = _ov_sem_caseboard


def build_overlay_blocks(
    s_id, scene_idx, scene_start, audio_duration, subtitle_text, visual_bible=None
):
    """Détecte et construit les overlays sémantiques pour la scène."""
    overlays = detect_overlays(
        subtitle_text, visual_bible=visual_bible, scene_idx=scene_idx
    )
    overlays = _diversify_overlay_types(overlays, scene_idx)
    overlays = _prepare_overlay_schedule(overlays, audio_duration, scene_idx)
    all_html, all_js = [], []
    for m, spec in enumerate(overlays):
        spec["idx"] = m
        builder = OVERLAY_BUILDERS.get(spec["type"])
        if not builder:
            continue
        html, js = builder(s_id, scene_idx, scene_start, audio_duration, spec)
        all_html.extend(html)
        all_js.extend(js)
    return all_html, all_js, [s["type"] for s in overlays]
