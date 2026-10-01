"""Assemblage d'une scène : plans image, sous-titres, overlays et accents."""

import os
import re
from usine.render.camera import (
    build_image_block,
    build_procedural_bg,
    build_scene_director_fx,
)
from usine.render.config import (
    DISABLE_SCENE_TRANSITIONS,
    USE_DIRECTOR_AGENT,
    USE_IMAGES,
    USE_SEMANTIC_OVERLAYS,
    USE_WHOOSH_SFX,
)
from usine.render.director import (
    build_curated_lottie_accents,
    generate_master_director_agent,
)
from usine.render.overlays.builders import build_overlay_blocks
from usine.render.text import (
    _wrap_words_for_reveal,
    emphasize_words,
    red_word_indices,
    split_subtitle,
)


def build_scene_blocks(
    scene_idx,
    scene,
    audio_duration,
    images,
    scene_start,
    total_scenes,
    visual_bible=None,
    word_timings=None,
    source_map=None,
):
    """Génère HTML + tweens GSAP pour une scène.
    Retourne (html_parts, js_parts, n_shots, has_overlays, woosh_ts, glitch_ts, boom_ts)."""
    html_parts = []
    js_parts = []
    has_overlays = False
    s_id = f"s{scene_idx + 1}"

    # Listes pour accumuler les timings SFX
    woosh_t_scene = []
    glitch_t_scene = []
    boom_t_scene = []

    # Détection des transitions et révélations
    if scene_idx == 0:
        boom_t_scene.append(scene_start)
    elif scene_idx == 1 and not DISABLE_SCENE_TRANSITIONS:
        glitch_t_scene.append(scene_start)
    elif scene_idx == 6:
        boom_t_scene.append(scene_start)
    elif scene_idx == 8:
        boom_t_scene.append(scene_start)
    elif scene_idx == 9 and not DISABLE_SCENE_TRANSITIONS:
        glitch_t_scene.append(scene_start)

    subtitle_src = (
        scene.get("subtitle")
        or scene.get("sous_titre")
        or scene.get("audio_tts")
        or scene.get("voix_off_tts")
        or scene.get("voix_off", "")
    )

    shots_list = []
    if USE_IMAGES and images:
        max_shots = int(os.getenv("MAX_SHOTS_PER_SCENE", "4"))
        shots_list = images[:max_shots]

    director_result = None
    if USE_DIRECTOR_AGENT:
        director_result = generate_master_director_agent(
            s_id,
            scene_idx,
            scene_start,
            audio_duration,
            subtitle_src,
            shots_list,
            visual_bible,
        )

    if director_result:
        d_html, d_js, strategy = director_result
        html_parts.extend(d_html)
        js_parts.extend(d_js)
        shots = len(shots_list)
    else:
        if not shots_list:
            bg_html, bg_js = build_procedural_bg(scene_idx, scene_start, audio_duration)
            html_parts.append(bg_html)
            js_parts.extend(bg_js)

        if shots_list:
            n = len(shots_list)
            slice_dur = audio_duration / n
            for j in range(n):
                img = shots_list[j]
                start = scene_start + j * slice_dur
                dur = slice_dur + (1.2 if j < n - 1 else 0)
                html, js = build_image_block(
                    s_id,
                    j,
                    img,
                    scene_idx,
                    start,
                    dur,
                    is_last=(j == n - 1),
                    in_transition_from_prev=(j > 0),
                    total_scenes=total_scenes,
                    source_type=(source_map or {}).get(str(img.resolve()), ""),
                )
                html_parts.append(html)
                js_parts.extend(js)
            shots = n
        else:
            shots = 0

        fx_html, fx_js = build_scene_director_fx(
            s_id, scene_idx, scene_start, audio_duration, subtitle_src
        )
        html_parts.extend(fx_html)
        js_parts.extend(fx_js)

        if USE_SEMANTIC_OVERLAYS:
            ov_html, ov_js, ov_types = build_overlay_blocks(
                s_id,
                scene_idx,
                scene_start,
                audio_duration,
                subtitle_src,
                visual_bible=visual_bible,
            )
            if ov_types:
                print(f"   ✨ Overlays détectés: {', '.join(ov_types)}")
                has_overlays = True
                html_parts.extend(ov_html)
                js_parts.extend(ov_js)

        lottie_html, lottie_js = build_curated_lottie_accents(
            scene_idx,
            scene_start,
            audio_duration,
            subtitle_src,
            word_timings,
        )
        if lottie_html:
            has_overlays = True
            html_parts.extend(lottie_html)
            js_parts.extend(lottie_js)

    subtitle_budget = audio_duration

    chunks = split_subtitle(
        subtitle_src,
        subtitle_budget,
        max_chunks=int(os.getenv("MAX_SUB_CHUNKS", "4")),
        max_words=int(os.getenv("MAX_WORDS_PER_CHUNK", "6")),
    )

    if word_timings:
        new_chunks = []
        cursor = 0
        for c in chunks:
            n_w = max(1, sum(1 for w in c["text"].split() if re.sub(r"[^\w]", "", w)))
            slice_ = word_timings[cursor : cursor + n_w]
            if slice_:
                c_start = slice_[0]["start"]
                c_end = slice_[-1]["end"]
                c_dur = max(0.8, (c_end - c_start) + 0.30)
                new_chunks.append(
                    {
                        "text": c["text"],
                        "start": c_start,
                        "duration": c_dur,
                        "_word_offset": cursor,
                        "_n_words": n_w,
                    }
                )
            else:
                new_chunks.append({**c, "_word_offset": cursor, "_n_words": n_w})
            cursor += n_w
        chunks = new_chunks

    for k in range(len(chunks)):
        c = chunks[k]
        if k < len(chunks) - 1:
            next_start = chunks[k + 1]["start"]
            max_dur = next_start - c["start"]
        else:
            max_dur = subtitle_budget - c["start"]
        chunks[k]["duration"] = max(0.2, min(c["duration"], max_dur - 0.03))

    for k, c in enumerate(chunks):
        sub_id = f"{s_id}_sub{k + 1}"
        start = scene_start + c["start"]
        dur = max(0.8, c["duration"])
        emph_html = emphasize_words(c["text"])
        chunk_word_prefix = sub_id if word_timings else None
        word_wrapped, _n_rendered = _wrap_words_for_reveal(
            emph_html, id_prefix=chunk_word_prefix
        )
        stripped = c["text"].strip()
        is_quote = bool(
            re.match(r'^["\u00ab\u201c\u201d]', stripped)
            and re.search(r'["\u00bb\u201c\u201d][?!.\u2026\s]*$', stripped)
        )
        extra_class = " quote" if is_quote else ""
        html_parts.append(
            f'<div id="{sub_id}" class="subtitle{extra_class} clip" '
            f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
            f'data-track-index="{scene_idx * 20 + 50 + k}" style="z-index: 50;">{word_wrapped}</div>'
        )
        js_parts.append(f'gsap.set("#{sub_id}", {{opacity: 0, y: 20}});')
        js_parts.append(
            f'tl.to("#{sub_id}", {{opacity: 1, y: 0, duration: 0.4, ease: "power2.out"}}, {start:.3f});'
        )
        js_parts.append(
            f'gsap.set("#{sub_id} .word", {{opacity: 0, y: 12, scale: 0.55}});'
        )

        used_whisper = False
        if word_timings:
            offset = c.get("_word_offset", 0)
            n_w = c.get("_n_words", 0)
            slice_ = word_timings[offset : offset + n_w]
            if len(slice_) >= 1:
                used_whisper = True
                for i, w in enumerate(slice_):
                    abs_t = scene_start + max(0.0, w["start"] - 0.06)
                    js_parts.append(
                        f'tl.to("#{sub_id}_w{i + 1}", '
                        f"{{opacity: 1, y: 0, scale: 1, duration: 0.22, "
                        f'ease: "back.out(1.6)", overwrite: "auto"}}, '
                        f"{abs_t:.3f});"
                    )

        if not used_whisper:
            n_words = max(1, len(c["text"].split()))
            word_stagger = max(0.07, min(0.22, (dur * 0.6) / n_words))
            word_duration = max(0.25, min(0.55, word_stagger * 1.6))
            js_parts.append(
                f'tl.to("#{sub_id} .word", {{opacity: 1, y: 0, scale: 1, duration: {word_duration:.3f}, '
                f'stagger: {word_stagger:.3f}, ease: "back.out(1.8)"}}, {(start + 0.10):.3f});'
            )

        # Check for red words in this chunk to schedule a whoosh sound.
        # Gated by USE_WHOOSH_SFX (default off) — the trigger fires on every
        # dramatic word, which feels like one whoosh per scene and gets old fast.
        if USE_WHOOSH_SFX:
            red_indices = red_word_indices(c["text"])
            if red_indices:
                first_red_idx = red_indices[0]
                if word_timings and used_whisper:
                    offset = c.get("_word_offset", 0)
                    n_w = c.get("_n_words", 0)
                    slice_ = word_timings[offset : offset + n_w]
                    if len(slice_) > first_red_idx:
                        rel_t = slice_[first_red_idx]["start"]
                    else:
                        rel_t = c["start"]
                else:
                    n_words = max(1, len(c["text"].split()))
                    word_stagger = max(0.07, min(0.22, (dur * 0.6) / n_words))
                    rel_t = c["start"] + 0.10 + first_red_idx * word_stagger
                woosh_t_scene.append(scene_start + rel_t)

        exit_at = start + dur - 0.35
        js_parts.append(
            f'tl.to("#{sub_id}", {{opacity: 0, y: -10, duration: 0.35, ease: "power2.in"}}, {exit_at:.3f});'
        )
        js_parts.append(f'tl.set("#{sub_id}", {{opacity: 0}}, {(start + dur):.3f});')

    html_parts.append(
        f'<audio id="{s_id}_vo" class="clip" src="assets/{s_id}_vo.wav" '
        f'data-start="{scene_start:.3f}" data-duration="{audio_duration:.3f}" '
        f'data-track-index="{1000 + scene_idx}" data-volume="0.0"></audio>'
    )

    return (
        html_parts,
        js_parts,
        shots,
        has_overlays,
        woosh_t_scene,
        glitch_t_scene,
        boom_t_scene,
    )
