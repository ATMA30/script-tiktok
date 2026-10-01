"""Entrées média d'un projet : durée audio, images par scène, types de sources."""

import json
import subprocess
from pathlib import Path


def ffprobe_duration(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return float(out.stdout.strip())


def load_visual_source_map(projet_dir):
    """Mappe chaque fichier média vers son source_type pour piloter le rendu."""
    plan_path = Path(projet_dir) / "visual_plan.json"
    source_map = {}
    if not plan_path.exists():
        return source_map
    try:
        visual_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return source_map

    for scene_key, plans in visual_plan.items():
        for idx, plan in enumerate(plans):
            source_type = plan.get("source_type", "")
            candidates = []
            file_path = plan.get("file_path")
            if file_path:
                candidates.append(Path(file_path))
            candidates.append(
                Path(projet_dir) / "real_media" / scene_key / f"plan_{idx + 1}.jpg"
            )
            candidates.append(
                Path(projet_dir) / "video" / scene_key / f"plan_{idx + 1}.mp4"
            )
            for candidate in candidates:
                try:
                    source_map[str(candidate.resolve())] = source_type
                except Exception:
                    pass
    return source_map


def pick_images(projet_dir, scene_idx, scene=None):
    """Récupère toutes les images disponibles pour une scène en fusionnant les sources.
    Si aucune image n'est trouvée pour la scène spécifique, on cherche dans les dossiers globaux du projet.
    """
    all_imgs = []
    excluded_media = set()
    if isinstance(scene, dict):
        for key in ("exclude_media", "excluded_media", "media_exclude"):
            values = scene.get(key) or []
            if isinstance(values, str):
                values = [values]
            excluded_media.update(str(v) for v in values)

    # 1. Sources spécifiques à la scène
    scene_folders = [
        projet_dir / "real_media" / f"scene_{scene_idx + 1}",
        projet_dir / "video" / f"scene_{scene_idx + 1}",
        projet_dir / "images" / f"scene_{scene_idx + 1}",
    ]

    for d in scene_folders:
        if d.is_dir():
            imgs = sorted(
                [
                    p
                    for p in d.iterdir()
                    if p.suffix.lower()
                    in (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".mp4",
                        ".mov",
                        ".m4v",
                        ".webm",
                    )
                    and p.name not in excluded_media
                ]
            )
            all_imgs.extend(imgs)

    # 2. Si toujours rien, on pioche dans les dossiers globaux (pour éviter le noir)
    if not all_imgs:
        global_folders = [
            projet_dir / "real_media",
            projet_dir / "video",
            projet_dir / "images",
        ]
        for d in global_folders:
            if d.is_dir():
                # On prend les images qui ne sont pas dans des sous-dossiers "scene_X"
                imgs = [
                    p
                    for p in d.iterdir()
                    if p.is_file()
                    and p.suffix.lower()
                    in (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".mp4",
                        ".mov",
                        ".m4v",
                        ".webm",
                    )
                    and p.name not in excluded_media
                ]
                all_imgs.extend(imgs)

    # 3. Déduplication par nom de fichier
    seen = set()
    unique_imgs = []
    for img in all_imgs:
        if img.name not in seen:
            unique_imgs.append(img)
            seen.add(img.name)

    # 4. Si on a des images globales mais qu'on veut de la variété, on mélange un peu si on en a peu
    if len(unique_imgs) > 0:
        # On utilise le scene_idx pour "shifter" la sélection de façon déterministe
        shift = scene_idx % len(unique_imgs)
        unique_imgs = unique_imgs[shift:] + unique_imgs[:shift]

    return unique_imgs
