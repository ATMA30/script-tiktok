"""Orchestration du rendu : script.json + audio + images → projet HyperFrames → final.mp4."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from usine.utils import trouver_dernier_projet
from usine.render.alignment import align_scene_words
from usine.render.audio import (
    ensure_ambient_music,
    find_dramatic_audio_events,
    mix_audio_post_render,
)
from usine.render.cards import build_hook_intro, build_outro_cta, build_true_story_card
from usine.render.config import (
    AMBIENT_MUSIC_VOLUME,
    BG_VARIANTS,
    BRAND_LOGO_DEFAUT,
    BRAND_LOGO_PATH,
    HF_VERSION,
    OUTRO_TAIL_SECONDS,
    RENDER_ROOT,
    ROOT,
    SKIP_TRUTH_CARD,
    TRUTH_PREROLL_SECONDS,
    USE_BRAND_LOGO,
    USE_DRAMATIC_SILENCE,
    USE_IMAGES,
    USE_LOTTIE_OVERLAYS,
    USE_OUTRO_CTA,
    USE_WHISPER_SYNC,
)
from usine.render.director import _reset_director_state
from usine.render.media import ffprobe_duration, load_visual_source_map, pick_images
from usine.render.scenes import build_scene_blocks
from usine.render.sfx import (
    build_sfx_blocks,
    compile_sfx_composite,
    discover_sfx,
    ensure_synth_sfx,
)
from usine.render.template import build_html


def write_hyperframes_project(render_dir):
    render_dir.mkdir(parents=True, exist_ok=True)
    (render_dir / "package.json").write_text(
        json.dumps(
            {
                "name": render_dir.name,
                "private": True,
                "type": "module",
                "scripts": {
                    "dev": f"npx --yes hyperframes@{HF_VERSION} preview",
                    "check": f"npx --yes hyperframes@{HF_VERSION} lint && npx --yes hyperframes@{HF_VERSION} validate && npx --yes hyperframes@{HF_VERSION} inspect",
                    "render": f"npx --yes hyperframes@{HF_VERSION} render",
                },
            },
            indent=2,
        )
    )
    (render_dir / "hyperframes.json").write_text(
        json.dumps(
            {
                "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                "paths": {
                    "blocks": "compositions",
                    "components": "compositions/components",
                    "assets": "assets",
                },
            },
            indent=2,
        )
    )
    (render_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": render_dir.name,
                "name": render_dir.name,
                "createdAt": "2026-01-01T00:00:00.000Z",
            },
            indent=2,
        )
    )


def render_projet(projet_dir, do_check=False, prepare_only=False):
    projet_dir = Path(projet_dir).resolve()
    projet_name = projet_dir.name

    script = json.loads((projet_dir / "script.json").read_text(encoding="utf-8"))
    scenes = script["scenes"]
    source_map = load_visual_source_map(projet_dir)
    # Reset per-render state (so the Lottie variety tracker doesn't leak between videos).
    _reset_director_state()
    print(f"\n🎞️  HyperFrames render : {projet_name} ({len(scenes)} scènes)")

    render_dir = RENDER_ROOT / projet_name
    if render_dir.exists():
        shutil.rmtree(render_dir)
    assets_dir = render_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    write_hyperframes_project(render_dir)
    if USE_BRAND_LOGO:
        logo_src = Path(BRAND_LOGO_PATH).expanduser().resolve()
        if not logo_src.exists():
            # Ex. ancien BRAND_LOGO_PATH dans le .env, d'avant le rangement d'assets/brand/.
            print(f"   ⚠️ Logo introuvable : {logo_src} → logo par défaut")
            logo_src = BRAND_LOGO_DEFAUT
        if logo_src.exists():
            shutil.copy(logo_src, assets_dir / "yurei_logo.png")
            print(f"   ◉ Logo Yūrei intégré : {logo_src.name}")
        else:
            print(f"   ⚠️ Logo par défaut introuvable : {logo_src}")

    # Copy the curated Lottie library into the render assets. Animation JSON
    # is embedded in the page so frame capture stays deterministic.
    _lottie_src = ROOT / "assets" / "lottie"
    if USE_LOTTIE_OVERLAYS and _lottie_src.exists():
        _lottie_dst = assets_dir / "lottie"
        try:
            shutil.copytree(
                _lottie_src,
                _lottie_dst,
                ignore=shutil.ignore_patterns(
                    "generate_starter_library.py",
                    "curate_library.py",
                    "__pycache__",
                    "node_modules",
                    "*.tgz",
                    "package*.json",
                ),
            )
            n_anims = len(list((_lottie_dst / "library").glob("*.json")))
            n_vendor = (
                len(list((_lottie_dst / "vendor").glob("*")))
                if (_lottie_dst / "vendor").exists()
                else 0
            )
            print(
                f"   🎞️  Lottie library copiée ({n_anims} animations, {n_vendor} vendor files)"
            )
        except Exception as e:
            print(f"   ⚠️ Lottie library non copiée : {e}")

    scenes_meta = []
    scenes_data = []
    cursor = 0.0
    all_woosh_timestamps = []
    all_glitch_timestamps = []
    all_boom_timestamps = []
    for i, scene in enumerate(scenes):
        s_id = f"s{i + 1}"
        audio_src = projet_dir / "audio" / f"scene_{i + 1}.wav"
        if not audio_src.exists():
            print(f"   ⚠️  Skip scène {i + 1} : audio manquant")
            continue
        dur = ffprobe_duration(audio_src)
        shutil.copy(audio_src, assets_dir / f"{s_id}_vo.wav")

        if USE_IMAGES:
            # On prend jusqu'à 5 images par scène
            images = pick_images(projet_dir, i, scene)[:5]
            shots_list = images if len(images) >= 2 else (images * 2 if images else [])
            for j, img in enumerate(shots_list[:5]):
                shutil.copy(img, assets_dir / f"{s_id}_bg{j + 1}{img.suffix}")
        else:
            images = []

        subtitle_src = (
            scene.get("subtitle")
            or scene.get("sous_titre")
            or scene.get("audio_tts")
            or scene.get("voix_off_tts")
            or scene.get("voix_off", "")
        )
        truth_preroll = (
            TRUTH_PREROLL_SECONDS if (i == 1 and not SKIP_TRUTH_CARD) else 0.0
        )
        scene_start = cursor + truth_preroll

        if truth_preroll > 0:
            # La truth card couvre la période entre image scène 1 (qui se retire
            # à scene_1_end + 0.3) et image scène 2 (qui apparaît à scene_2_start).
            # On la fait commencer 0.5s AVANT la fin de scène 1 et se prolonger
            # jusqu'à ce que l'image de scène 2 soit déjà visible (chevauchement).
            card_start = max(0.0, cursor - 0.5)
            card_dur = truth_preroll + 1.2  # +0.5 avant + 0.7 après scene_2_start
            pre_html, pre_js = build_true_story_card(
                s_id, i, card_start, card_dur, subtitle_src
            )
        else:
            pre_html, pre_js = [], []

        # Alignement mot-par-mot via Whisper (anti-drift)
        word_timings = (
            align_scene_words(audio_src, subtitle_src) if USE_WHISPER_SYNC else None
        )
        if word_timings:
            print(f"   🔠 Whisper sync : {len(word_timings)} mots alignés")

        html, js, n_shots, scene_has_overlays, woosh_t, glitch_t, boom_t = (
            build_scene_blocks(
                i,
                scene,
                dur,
                images,
                scene_start,
                len(scenes),
                visual_bible=script.get("visual_bible"),
                word_timings=word_timings,
                source_map=source_map,
            )
        )
        all_woosh_timestamps.extend(woosh_t)
        all_glitch_timestamps.extend(glitch_t)
        all_boom_timestamps.extend(boom_t)
        if pre_html:
            html = pre_html + html
            js = pre_js + js

        # Hook intro punch (scène 1 uniquement) — superposé sur la scène
        hook_html, hook_js = build_hook_intro(s_id, i, scene_start, dur, subtitle_src)
        if hook_html:
            html = html + hook_html
            js = js + hook_js

        # Tail après la voix sur la dernière scène (CTA + musique seuls)
        outro_tail = (
            OUTRO_TAIL_SECONDS if (i == len(scenes) - 1 and USE_OUTRO_CTA) else 0.0
        )

        # Outro CTA (dernière scène uniquement) — superposé en fin, étendu par le tail
        outro_html, outro_js = build_outro_cta(
            s_id, i, scene_start, dur, len(scenes), tail_seconds=outro_tail
        )
        if outro_html:
            html = html + outro_html
            js = js + outro_js

        scene_total_duration = dur + truth_preroll + outro_tail
        scenes_meta.append(
            {
                "start": cursor,
                "duration": scene_total_duration,
                "html": html,
                "js": js,
                "has_overlays": scene_has_overlays,
            }
        )
        scenes_data.append(
            {
                "scene_idx": i,
                "voice_start": scene_start,
                "duration": dur,
                "word_timings": word_timings or [],
            }
        )
        bg_variant = BG_VARIANTS[i % len(BG_VARIANTS)] if not USE_IMAGES else "img"
        extras = []
        if truth_preroll:
            extras.append(f"pause vérité {truth_preroll:.2f}s")
        if outro_tail:
            extras.append(f"tail outro {outro_tail:.2f}s")
        extra = " + " + " + ".join(extras) if extras else ""
        print(
            f"   ▶ Scène {i + 1} : {dur:.2f}s{extra} · bg={bg_variant}, start={cursor:.2f}s"
        )
        cursor += scene_total_duration

    total = cursor

    # ── SFX scanning : ROOT/assets/sfx/*.mp3 (drone, whoosh, glitch...)
    sfx_root = ROOT / "assets" / "sfx"
    ensure_synth_sfx(sfx_root)
    sfx_available = discover_sfx(sfx_root)
    if sfx_available:
        sfx_html, sfx_js = build_sfx_blocks(
            scenes_meta,
            sfx_available,
            total,
            assets_dir,
            woosh_ts=all_woosh_timestamps,
            glitch_ts=all_glitch_timestamps,
            boom_ts=all_boom_timestamps,
        )
        if sfx_html:
            scenes_meta.append(
                {"start": 0, "duration": total, "html": sfx_html, "js": sfx_js}
            )
            print(f"   🔊 SFX intégrés : {', '.join(sfx_available.keys())}")
    else:
        print(
            "   ℹ️  Aucun SFX trouvé dans assets/sfx/ (optionnel : drop tes whoosh.mp3, drone.mp3 etc.)"
        )

    # ── Musique d'ambiance stressante (track audio continue, durée >= vidéo)
    music_path = ensure_ambient_music(projet_dir, target_duration=total)
    if music_path:
        music_dest = assets_dir / f"ambient_music{music_path.suffix}"
        shutil.copy(music_path, music_dest)
        music_html = [
            f'<audio id="ambient_music" class="clip" src="assets/{music_dest.name}" '
            f'data-start="0" data-duration="{total:.3f}" '
            f'data-track-index="2500" data-volume="{AMBIENT_MUSIC_VOLUME}"></audio>'
        ]
        scenes_meta.append(
            {"start": 0, "duration": total, "html": music_html, "js": []}
        )
        print(
            f"   🎼 Musique d'ambiance intégrée : {music_path.name} @ vol={AMBIENT_MUSIC_VOLUME}"
        )
    else:
        print(
            "   ℹ️  Pas de musique d'ambiance (USE_AMBIENT_MUSIC=0 ou échec génération)"
        )

    html_doc = build_html(projet_name, scenes_meta, total)
    (render_dir / "index.html").write_text(html_doc, encoding="utf-8")
    print(f"   📄 HTML écrit ({len(html_doc) // 1024} KB), total = {total:.2f}s")

    if do_check:
        print("   🔍 Lint + validate...")
        subprocess.run(["npm", "run", "check"], cwd=render_dir, check=True)

    if prepare_only:
        print(f"   ✅ Composition prête pour preview/snapshot : {render_dir}")
        return render_dir

    print("   🎬 npx hyperframes render (headless Chrome)...")
    r = subprocess.run(["npm", "run", "render"], cwd=render_dir)
    if r.returncode != 0:
        raise RuntimeError(f"HyperFrames render échec (code {r.returncode})")

    renders = sorted(
        (render_dir / "renders").glob("*.mp4"), key=lambda p: p.stat().st_mtime
    )
    if not renders:
        raise RuntimeError("Aucun MP4 trouvé dans renders/")
    final = projet_dir / "final.mp4"
    dramatic_events = (
        find_dramatic_audio_events(scenes_data) if USE_DRAMATIC_SILENCE else []
    )
    if dramatic_events:
        labels = ", ".join(
            f"{event['word']}@{event['time']:.2f}s" for event in dramatic_events
        )
        print(f"   🔇 Ruptures dramatiques : {labels}")
    compile_sfx_composite(
        projet_dir,
        total,
        all_woosh_timestamps,
        all_glitch_timestamps,
        all_boom_timestamps,
        scenes_data,
        dramatic_events=dramatic_events,
    )
    mix_audio_post_render(
        projet_dir,
        renders[-1],
        final,
        scenes_data,
        total,
        dramatic_events=dramatic_events,
    )
    print(f"\n✅ Final : {final}  ({final.stat().st_size // 1024} KB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projet", help="Chemin du projet (défaut: dernier)")
    ap.add_argument("--check", action="store_true", help="Lint + validate avant render")
    ap.add_argument(
        "--prepare-only",
        action="store_true",
        help="Écrit la composition HyperFrames sans lancer le rendu vidéo",
    )
    args = ap.parse_args()

    projet = args.projet or trouver_dernier_projet()
    if not projet:
        raise SystemExit("Aucun projet trouvé.")
    render_projet(
        projet,
        do_check=args.check,
        prepare_only=args.prepare_only,
    )
