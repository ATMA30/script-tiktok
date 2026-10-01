"""
2.5_director_orchestrator.py — ORCHESTRATION DES PLANS VISUELS
Rôle : Découpe les scènes en plans visuels en se basant sur les phrases du texte.
- Utilise l'en-tête WAV pour une lecture ultra-rapide (<1ms) de la durée de l'audio.
- Supprime le chargement lourd de Whisper en CPU/RAM.
- Découpe de façon sémantique chaque scène par rapport à la ponctuation des phrases.
"""

import os
import json
import re
import wave
import math
from utils import trouver_dernier_projet

MAX_PLANS_PER_SCENE = int(os.getenv("MAX_PLANS_PER_SCENE", "2"))


def get_audio_duration_wave(audio_path: str) -> float:
    """Retourne la durée précise d'un fichier WAV en lisant son en-tête (en millisecondes)."""
    try:
        with wave.open(audio_path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception as e:
        print(f"   ⚠️ wave.open erreur sur {os.path.basename(audio_path)} : {e}")
    return 0.0


def creer_plans_semantiques(
    scene_text: str,
    veo_prompt: str,
    lyria_prompt: str,
    duree_totale: float,
    real_media_queries: list = None,
) -> list:
    """
    Découpe le texte d'une scène en plans basés sur les phrases.
    La durée de chaque plan est estimée proportionnellement à la longueur de la phrase (en caractères).
    """
    # Nettoyage des balises et séparations par phrases (. ! ? ...)
    clean_text = re.sub(r"\[.*?\]", "", scene_text)
    phrases = [p.strip() for p in re.split(r"(?<=[.!?])\s+", clean_text) if p.strip()]

    if not phrases:
        phrases = [scene_text] if scene_text.strip() else ["Scène sans texte"]

    # Deux compositions fortes par scène donnent des plans de 4 à 6 secondes,
    # plus cinématographiques que des changements d'image à chaque courte phrase.
    max_plans = max(1, MAX_PLANS_PER_SCENE)
    if len(phrases) > max_plans:
        grouped = []
        for group_idx in range(max_plans):
            start = math.floor(group_idx * len(phrases) / max_plans)
            end = math.floor((group_idx + 1) * len(phrases) / max_plans)
            grouped.append(" ".join(phrases[start:end]))
        phrases = grouped
    elif len(phrases) == 1 and max_plans >= 2 and duree_totale >= 6.0:
        # Même narration, deux angles visuels distincts : le fetcher générera
        # deux compositions et le rendu évitera un plan unique de neuf secondes.
        phrases = [phrases[0], phrases[0]]

    total_chars = sum(len(p) for p in phrases)

    if total_chars == 0 or duree_totale <= 0:
        return [
            {
                "type": "VEO_TEXT_TO_VIDEO",
                "veo_prompt": veo_prompt,
                "lyria_prompt": lyria_prompt,
                "start": 0.0,
                "end": round(duree_totale, 3),
                "file_path": "",
                "text_segment": scene_text,
                "real_media_queries": real_media_queries or [],
            }
        ]

    plans = []
    current_start = 0.0

    for idx, phrase in enumerate(phrases):
        part_dur = (len(phrase) / total_chars) * duree_totale
        current_end = current_start + part_dur

        # S'assurer que le dernier plan s'aligne exactement sur la fin
        if idx == len(phrases) - 1:
            current_end = duree_totale

        plans.append(
            {
                "type": "VEO_TEXT_TO_VIDEO",
                "veo_prompt": veo_prompt,
                "lyria_prompt": lyria_prompt,
                "start": round(current_start, 3),
                "end": round(current_end, 3),
                "file_path": "",
                "text_segment": phrase,
                "real_media_queries": real_media_queries or [],
            }
        )
        current_start = current_end

    return plans


def traiter_orchestration(dossier_projet: str):
    print("═" * 56)
    print("  🎬 ÉTAPE 2.5 : DIRECTOR — Découpage Sémantique & WAV  ")
    print("═" * 56)

    script_path = f"{dossier_projet}/script.json"
    if not os.path.exists(script_path):
        print(f"❌ script.json introuvable : {script_path}")
        return

    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    visual_plan = {}
    total_duration = 0.0

    for scene in script_data.get("scenes", []):
        num = scene.get("id", "?")
        audio_tts = scene.get("audio_tts", "")
        veo_prompt = scene.get("veo_prompt", "")
        lyria = scene.get("lyria_prompt", "")
        real_media_queries = scene.get("real_media_queries", [])

        audio_path = f"{dossier_projet}/audio/scene_{num}.wav"
        if not os.path.exists(audio_path):
            print(f"   ⚠️  Audio manquant pour scène {num} — ignorée")
            continue

        # Extraction instantanée de la durée du WAV
        duree = get_audio_duration_wave(audio_path)
        if duree < 0.2:
            print(
                f"   ⚠️  Durée audio invalide pour scène {num} ({duree:.2f}s) — ignorée"
            )
            continue

        total_duration += duree

        # Découpage sémantique basé sur le texte
        plans = creer_plans_semantiques(
            audio_tts, veo_prompt, lyria, duree, real_media_queries
        )
        print(f"   📽️  Scène {num} — {duree:.2f}s → {len(plans)} plan(s) sémantique(s)")

        visual_plan[f"scene_{num}"] = plans

    if not visual_plan:
        print("❌ Aucun plan généré. Vérifie les fichiers WAV.")
        return

    with open(f"{dossier_projet}/visual_plan.json", "w", encoding="utf-8") as f:
        json.dump(visual_plan, f, indent=4, ensure_ascii=False)

    total_plans = sum(len(p) for p in visual_plan.values())
    print("\n✅ visual_plan.json sauvegardé")
    print(
        f"   📊 Projet : {len(visual_plan)} scènes, {total_plans} plans, {total_duration:.2f}s total"
    )


if __name__ == "__main__":
    dossier = trouver_dernier_projet()
    if dossier:
        traiter_orchestration(dossier)
    else:
        print("📁 Aucun projet trouvé.")
