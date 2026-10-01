"""
Validation locale d'un projet video sans appel API.

Usage:
  python validate_project.py
  python validate_project.py projets/mon_projet
  python validate_project.py --strict projets/mon_projet
"""

import argparse
import json
from pathlib import Path

from usine.projet import VALIDE
from utils import trouver_dernier_projet


def _audio_for(project_dir: Path, scene_id: int) -> Path | None:
    for ext in (".wav", ".mp3"):
        path = project_dir / "audio" / f"scene_{scene_id}{ext}"
        if path.exists() and path.stat().st_size > 5000:
            return path
    return None


def _media_for(project_dir: Path, scene_id: int) -> list[Path]:
    media = []
    for folder in (
        project_dir / "real_media" / f"scene_{scene_id}",
        project_dir / "video" / f"scene_{scene_id}",
        project_dir / "images" / f"scene_{scene_id}",
    ):
        if folder.is_dir():
            media.extend(
                p
                for p in folder.iterdir()
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".mp4"}
            )
    return sorted(media)


def validate_project(project_dir: Path, strict: bool = False) -> int:
    errors = []
    warnings = []

    script_path = project_dir / "script.json"
    if not script_path.exists():
        errors.append(f"script.json manquant: {script_path}")
        return _report(project_dir, errors, warnings)

    try:
        script = json.loads(script_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"script.json invalide: {exc}")
        return _report(project_dir, errors, warnings)

    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append("script.json ne contient aucune scene")
        return _report(project_dir, errors, warnings)

    for index, scene in enumerate(scenes, 1):
        scene_id = scene.get("id", index)
        for field in ("audio_tts", "subtitle", "veo_prompt"):
            if not scene.get(field):
                errors.append(f"scene {scene_id}: champ manquant ou vide: {field}")

        audio = _audio_for(project_dir, scene_id)
        if not audio:
            errors.append(f"scene {scene_id}: audio manquant ou trop petit")

        media = _media_for(project_dir, scene_id)
        if not media:
            warnings.append(f"scene {scene_id}: aucun media trouve")

    visual_plan_path = project_dir / "visual_plan.json"
    if visual_plan_path.exists():
        try:
            visual_plan = json.loads(visual_plan_path.read_text(encoding="utf-8"))
            if not isinstance(visual_plan, dict) or not visual_plan:
                warnings.append("visual_plan.json est vide")
        except json.JSONDecodeError as exc:
            errors.append(f"visual_plan.json invalide: {exc}")
    else:
        warnings.append("visual_plan.json manquant")

    statut = (script.get("validation") or {}).get("statut")
    if statut != VALIDE:
        message = (
            f"dossier non validé ({statut or 'sans statut'}) : "
            f"python 0_usine.py --valider {project_dir}"
        )
        (errors if strict else warnings).append(message)

    final_path = project_dir / "final.mp4"
    if final_path.exists() and final_path.stat().st_size > 100_000:
        pass
    elif strict:
        errors.append("final.mp4 manquant ou trop petit")
    else:
        warnings.append("final.mp4 pas encore present")

    return _report(project_dir, errors, warnings)


def _report(project_dir: Path, errors: list[str], warnings: list[str]) -> int:
    print(f"\nValidation: {project_dir}")
    for warning in warnings:
        print(f"  WARN  {warning}")
    for error in errors:
        print(f"  ERROR {error}")

    if errors:
        print(
            f"\nResultat: ECHEC ({len(errors)} erreur(s), {len(warnings)} avertissement(s))"
        )
        return 1

    print(f"\nResultat: OK ({len(warnings)} avertissement(s))")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project", nargs="?", help="Dossier projet a valider")
    parser.add_argument("--strict", action="store_true", help="Exige final.mp4")
    args = parser.parse_args()

    project = args.project or trouver_dernier_projet()
    if not project:
        raise SystemExit("Aucun projet trouve.")

    raise SystemExit(validate_project(Path(project), strict=args.strict))
