"""
═══════════════════════════════════════════════════════════════════════════
  ORCHESTRATEUR PRINCIPAL — point d'entrée unique
═══════════════════════════════════════════════════════════════════════════
Deux modes :

  VIDÉO UNIQUE (mode principal)
    Génère une histoire complète en une seule vidéo (arc entier, 60-90s).
    1 appel Gemini → script.json → pipeline de rendu.
    Validation humaine avant le rendu.

  SÉRIE (mode legacy)
    Génère un synopsis multi-épisodes avec validation en 2 phases.

Usage :  python 0_serie.py
"""

import sys
import os
import json
import subprocess
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).resolve().parent
SERIES_DIR = ROOT / "series"
PROJETS_DIR = ROOT / "projets"
BRAIN = "1_generate_serie.py"


def run_brain(*args, env_extra=None) -> bool:
    cmd = [PY, BRAIN, *[str(a) for a in args]]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    return r.returncode == 0


def latest_serie_dir() -> Path | None:
    if not SERIES_DIR.is_dir():
        return None
    cands = [d for d in SERIES_DIR.iterdir() if (d / "serie.json").is_file()]
    return max(cands, key=lambda d: d.name) if cands else None


def latest_projet_dir() -> Path | None:
    if not PROJETS_DIR.is_dir():
        return None
    cands = [d for d in PROJETS_DIR.iterdir() if (d / "script.json").is_file()]
    return max(cands, key=lambda d: d.stat().st_mtime) if cands else None


def load_serie(serie_dir: Path) -> dict:
    return json.loads((serie_dir / "serie.json").read_text(encoding="utf-8"))


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Sortie.")
        sys.exit(0)


def _choisir_sujet() -> tuple[str, dict | None]:
    """Retourne (sujet_libre, situation_suggeree_ou_None)."""
    print("\n  Comment choisir le sujet ?")
    print("  [1] Suggestions data-driven (tendances du moment)")
    print("  [2] Je saisis mon propre sujet")
    print("  [3] Automatique (Gemini choisit)")
    mode = ask("   > ").strip()

    if mode == "1":
        try:
            sys.path.insert(0, str(ROOT))
            from importlib import import_module

            picker = import_module("0_trend_picker".replace(".", "_"))
            suggestions = picker.pick_trending_premises(n=5)
            idx = picker.afficher_suggestions(suggestions)
            if idx is not None and 0 <= idx < len(suggestions):
                s = suggestions[idx]
                print(f"\n✅ Sujet choisi : {s.get('premisse', '')}")
                return "", s
        except Exception as e:
            print(f"   ⚠️  Trend picker indisponible : {e}")
        sujet = ask("👉 Saisir le sujet manuellement > ")
        return sujet, None
    elif mode == "2":
        sujet = ask("👉 Ton sujet > ")
        return sujet, None
    return "", None


# ─────────────────────────────────────────────────────────────
#  MODE 1 — MYSTÈRE AGATHA CHRISTIE (2 épisodes B&W)
# ─────────────────────────────────────────────────────────────


def mode_mystere():
    print("\n══════════════════════════════════════════════════════")
    print("   🔍 MYSTÈRE — Agatha Christie, B&W, 2 épisodes")
    print("══════════════════════════════════════════════════════")
    print("   Ép.1 : La maison et ses indices cachés")
    print("   Ép.2 : Les révélations")

    print("\n  Quel type de maison/crime ?")
    print("  [1] Automatique (Gemini choisit)")
    print("  [2] Je précise le cadre")
    mode = ask("   > ").strip()

    sujet = None
    if mode == "2":
        sujet = ask(
            "👉 Décris la maison/crime (ex: 'manoir breton, empoisonnement, années 50') > "
        )

    while True:
        args = ["mystere"]
        if sujet:
            args += ["--sujet", sujet]

        if not run_brain(*args):
            print("❌ Échec de la génération.")
            return

        # Trouver les 2 derniers projets créés (ep01 et ep02)

        projets = sorted(
            PROJETS_DIR.glob("*/script.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        ep2 = projets[0].parent if projets else None
        ep1 = projets[1].parent if len(projets) > 1 else None

        if not ep1 or not ep2:
            print("❌ Projets introuvables.")
            return

        choix = ask(
            "\n🟢 [o] Valider et rendre les 2 épisodes\n"
            "🔁 [r] Régénérer\n"
            "🛑 [n] Annuler\n   > "
        ).lower()

        if choix == "o":
            _lancer_rendu([str(ep1), str(ep2)])
            return
        elif choix == "r":
            continue
        else:
            print(f"👋 Scripts sauvegardés :\n   {ep1}\n   {ep2}")
            return


# ─────────────────────────────────────────────────────────────
#  MODE 2 — VIDÉO UNIQUE
# ─────────────────────────────────────────────────────────────


def mode_video_unique():
    print("\n══════════════════════════════════════════════════════")
    print("   🎬 VIDÉO UNIQUE — Histoire complète en 60-90s")
    print("══════════════════════════════════════════════════════")

    sujet, situation_suggeree = _choisir_sujet()

    try:
        n = ask("👉 Nombre de scènes ? (défaut 10) > ")
        n_scenes = int(n) if n else 10
    except ValueError:
        n_scenes = 10

    env_extra = {}
    if situation_suggeree:
        env_extra["TREND_SITUATION"] = json.dumps(
            situation_suggeree, ensure_ascii=False
        )

    while True:
        args = ["video", "--scenes", n_scenes]
        if sujet:
            args += ["--sujet", sujet]

        if not run_brain(*args, env_extra=env_extra):
            print("❌ Échec de la génération.")
            return

        projet_dir = latest_projet_dir()
        if not projet_dir:
            print("❌ Projet introuvable après génération.")
            return

        choix = ask(
            "\n🟢 [o] Valider et lancer le rendu\n"
            "🔁 [r] Régénérer une autre histoire\n"
            "✏️  [m] Éditer script.json manuellement puis continuer\n"
            "🛑 [n] Annuler\n   > "
        ).lower()

        if choix == "o":
            _lancer_rendu([str(projet_dir)])
            return
        elif choix == "r":
            continue
        elif choix == "m":
            print(f"\n✏️  Édite : {projet_dir / 'script.json'}")
            ask("   Appuie sur Entrée quand c'est fait…")
            _lancer_rendu([str(projet_dir)])
            return
        else:
            print(f"👋 Annulé. Script sauvegardé dans : {projet_dir}")
            return


# ─────────────────────────────────────────────────────────────
#  MODE 2 — SÉRIE (legacy)
# ─────────────────────────────────────────────────────────────


def mode_serie():
    serie_dir = _phase1_synopsis()
    if not serie_dir:
        return
    _phase2_episodes(serie_dir)
    _phase3_rendu_serie(serie_dir)
    print("\n✅ Terminé.")
    run_brain("status", "--serie", serie_dir)


def _phase1_synopsis() -> Path | None:
    print("\n══════════════════════════════════════════════════════")
    print("   🎬 SÉRIE — PHASE 1 : SYNOPSIS")
    print("══════════════════════════════════════════════════════")

    sujet, situation_suggeree = _choisir_sujet()

    try:
        n = ask("👉 Combien d'épisodes ? (défaut 8) > ")
        n_episodes = int(n) if n else 8
    except ValueError:
        n_episodes = 8

    env_extra = {}
    if situation_suggeree:
        env_extra["TREND_SITUATION"] = json.dumps(
            situation_suggeree, ensure_ascii=False
        )

    while True:
        args = ["synopsis", "--episodes", n_episodes]
        if sujet:
            args += ["--sujet", sujet]

        if not run_brain(*args, env_extra=env_extra):
            print("❌ Échec de la génération du synopsis.")
            return None

        serie_dir = latest_serie_dir()
        if not serie_dir:
            print("❌ Synopsis introuvable après génération.")
            return None

        choix = ask(
            "\n🟢 [o] Valider ce synopsis\n"
            "🔁 [r] Régénérer\n"
            "✏️  [m] Éditer serie.json manuellement\n"
            "🛑 [n] Annuler\n   > "
        ).lower()

        if choix == "o":
            run_brain("valider", "--serie", serie_dir)
            return serie_dir
        elif choix == "r":
            continue
        elif choix == "m":
            print(f"\n✏️  Édite : {serie_dir / 'serie.json'}")
            ask("   Appuie sur Entrée quand c'est fait…")
            run_brain("valider", "--serie", serie_dir)
            return serie_dir
        else:
            print("👋 Annulé.")
            return None


def _phase2_episodes(serie_dir: Path):
    print("\n══════════════════════════════════════════════════════")
    print("   🎬 PHASE 2 — ÉPISODE PAR ÉPISODE")
    print("══════════════════════════════════════════════════════")
    serie = load_serie(serie_dir)
    numeros = [e.get("numero") for e in serie.get("episodes", [])]

    for num in numeros:
        while True:
            if not run_brain("episode", num, "--serie", serie_dir):
                print(f"❌ Échec épisode {num}.")
                if ask("   Réessayer ? [o/n] > ").lower() != "o":
                    return
                continue

            choix = ask(
                f"\n🟢 [o] Valider épisode {num}\n"
                f"🔁 [r] Régénérer épisode {num}\n"
                f"🛑 [s] Stop\n   > "
            ).lower()

            if choix == "o":
                break
            elif choix == "r":
                continue
            else:
                print("🛑 Arrêt.")
                return


def _phase3_rendu_serie(serie_dir: Path):
    serie = load_serie(serie_dir)
    dirs = [
        e.get("project_dir")
        for e in serie.get("episodes", [])
        if e.get("status") == "generated"
    ]
    dirs = [d for d in dirs if d and (ROOT / d / "script.json").exists()]
    if not dirs:
        return
    print(f"\n   {len(dirs)} épisode(s) prêt(s) à rendre.")
    if ask("👉 Lancer le rendu ? [o/n] > ").lower() == "o":
        _lancer_rendu(dirs)


# ─────────────────────────────────────────────────────────────
#  RENDU COMMUN
# ─────────────────────────────────────────────────────────────


def _lancer_rendu(projet_dirs: list[str]):
    print("\n══════════════════════════════════════════════════════")
    print("   🎥 RENDU VIDÉO")
    print("══════════════════════════════════════════════════════")
    for d in projet_dirs:
        print(f"     • {d}")
    r = subprocess.run([PY, "batch_produce.py", *projet_dirs], cwd=ROOT)
    if r.returncode == 0:
        print("✅ Rendu terminé.")
    else:
        print("⚠️  Le rendu a rencontré une erreur.")


# ─────────────────────────────────────────────────────────────
#  MENU PRINCIPAL
# ─────────────────────────────────────────────────────────────


def main():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║          🎬 GÉNÉRATEUR DE VIDÉOS                    ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  [1] Mystère  — Agatha Christie, B&W, 2 épisodes    ║")
    print("║  [2] Drama    — Histoire complète, 1 vidéo (60-90s) ║")
    print("║  [3] Série    — N épisodes avec cliffhangers        ║")
    print("╚══════════════════════════════════════════════════════╝")

    choix = ask("\n👉 Ton choix > ").strip()

    if choix == "2":
        mode_video_unique()
    elif choix == "3":
        mode_serie()
    else:
        # Par défaut [1] : mystère
        mode_mystere()


if __name__ == "__main__":
    main()
