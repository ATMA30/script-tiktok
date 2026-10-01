"""
0_trend_picker.py — Suggestions de prémisses basées sur les tendances

Deux modes :
  - Avec YOUTUBE_API_KEY : analyse les vidéos trending France (engagement rate réel)
    → Gemini mappe sur les situations-socles → 5 prémisses data-driven
  - Sans clé : Gemini génère directement depuis les situations-socles
    (aucune dépendance externe, toujours fonctionnel)

Usage standalone :
  python 0_trend_picker.py
  python 0_trend_picker.py --n 3 --region FR
"""

import os
import json
import argparse
from typing import Optional

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
MODEL = os.getenv("SERIE_MODEL", "gemini-2.5-flash")

# Catégories YouTube pertinentes pour le drama/story
YOUTUBE_CATEGORIES = {
    "24": "Entertainment",
    "22": "People & Blogs",
    "1": "Film & Animation",
}

SITUATIONS_SOCLES = [
    (
        "amour",
        "Aimer quelqu'un qui ne t'aime pas de la même façon, sans jamais le dire",
    ),
    ("amour", "Rester trop longtemps dans quelque chose qui ne fonctionnait plus"),
    ("amour", "Réaliser après la rupture que les signaux étaient là depuis le début"),
    ("amour", "Être remplacé sans explication, comme si on n'avait jamais existé"),
    (
        "amour",
        "Découvrir que la personne aimée était quelqu'un d'autre en dehors de toi",
    ),
    (
        "famille",
        "Grandir dans l'ombre d'un frère ou d'une sœur sans jamais le formuler",
    ),
    ("famille", "Réaliser adulte que son enfance n'était pas normale"),
    ("famille", "Vouloir l'approbation d'un parent qui ne la donnera jamais"),
    (
        "famille",
        "Un secret de famille maintenu pendant des décennies, révélé par accident",
    ),
    ("famille", "Se battre pour un héritage et perdre quelque chose d'irremplaçable"),
    (
        "travail",
        "Voir quelqu'un moins compétent passer devant soi grâce aux bonnes relations",
    ),
    ("travail", "Donner tout à une entreprise qui te remplace en une semaine"),
    ("travail", "Se taire face à une injustice par peur des conséquences"),
    ("travail", "Former quelqu'un qui finit par prendre ta place"),
    (
        "travail",
        "Réaliser que ce qu'on pensait être une amitié au travail était du calcul",
    ),
    ("amitie", "Perdre un ami sans dispute, juste par dérive silencieuse"),
    ("amitie", "Découvrir qu'un proche parle dans ton dos depuis des années"),
    ("amitie", "Être là pour quelqu'un qui disparaît quand tu as besoin de lui"),
    ("amitie", "Comprendre trop tard qu'une amitié était à sens unique"),
    ("amitie", "Un ami qui change complètement dès qu'il obtient ce qu'il voulait"),
    ("soi", "Regretter une décision prise par peur, qui ne se représentera plus"),
    (
        "soi",
        "Réaliser qu'on a reproduit exactement ce qu'on détestait chez ses parents",
    ),
    ("soi", "Avoir gardé le silence au mauvais moment et vivre avec ça"),
    ("soi", "Choisir la sécurité et se demander des années après ce qu'on a raté"),
    ("soi", "Comprendre que quelqu'un qu'on croyait toxique nous protégeait"),
]


# ─────────────────────────────────────────────
#  YouTube Data API
# ─────────────────────────────────────────────


def _fetch_youtube_trending(region: str = "FR", max_results: int = 30) -> list[dict]:
    """Récupère les vidéos trending Entertainment + People & Blogs avec leurs métriques."""
    if not YOUTUBE_API_KEY:
        return []

    videos = []
    for cat_id in ["24", "22"]:
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "snippet,statistics,contentDetails",
                    "chart": "mostPopular",
                    "regionCode": region,
                    "videoCategoryId": cat_id,
                    "maxResults": max_results,
                    "key": YOUTUBE_API_KEY,
                },
                timeout=10,
            )
            r.raise_for_status()
            for v in r.json().get("items", []):
                stats = v.get("statistics", {})
                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                comments = int(stats.get("commentCount", 0))
                if views == 0:
                    continue
                engagement = round((likes + comments) / views * 100, 2)
                videos.append(
                    {
                        "title": v["snippet"]["title"],
                        "channel": v["snippet"]["channelTitle"],
                        "views": views,
                        "likes": likes,
                        "comments": comments,
                        "engagement_rate": engagement,
                        "category": YOUTUBE_CATEGORIES.get(cat_id, cat_id),
                    }
                )
        except Exception as e:
            print(f"   ⚠️  YouTube API erreur (cat {cat_id}) : {e}")

    # Trier par engagement rate (pas par vues brutes)
    return sorted(videos, key=lambda x: x["engagement_rate"], reverse=True)


def _score_videos(videos: list[dict], top_n: int = 15) -> list[dict]:
    """Garde les top_n vidéos par engagement."""
    return videos[:top_n]


# ─────────────────────────────────────────────
#  Gemini distillation
# ─────────────────────────────────────────────


def _distill_with_gemini(
    top_videos: list[dict],
    n_suggestions: int = 5,
    region: str = "FR",
) -> list[dict]:
    """Mappe les tendances sur des situations-socles et génère des prémisses."""
    client = genai.Client(api_key=GEMINI_API_KEY)

    socles_str = "\n".join(f"  [{t}] {s}" for t, s in SITUATIONS_SOCLES)

    if top_videos:
        trending_str = "\n".join(
            f'  - "{v["title"]}" ({v["views"]:,} vues, {v["engagement_rate"]}% engagement)'
            for v in top_videos[:15]
        )
        context = (
            f"Voici les {len(top_videos[:15])} vidéos drama/story les plus engagées "
            f"en ce moment ({region}) :\n{trending_str}\n\n"
            f"En t'appuyant sur les ÉMOTIONS et THÈMES qui ressortent de ces titres "
            f"(pas les sujets exacts — inspire-toi des patterns émotionnels),"
        )
    else:
        context = "En te basant sur les situations universelles les plus résonantes,"

    prompt = f"""{context} génère {n_suggestions} prémisses originales pour une série
dramatique à la première personne (narrateur : Lucas, 30 ans).

Situations-socles disponibles (choisir ou combiner) :
{socles_str}

Règles :
- Chaque prémisse doit être reconnaissable par le plus grand nombre (pas extraordinaire, PRÉCIS)
- La noirceur est dans le banal, pas dans l'extrême
- Ancrer dans un contexte quotidien concret

Réponds en JSON :
{{
  "suggestions": [
    {{
      "territoire": "amour|famille|travail|amitie|soi",
      "situation": "La situation universelle de base",
      "premisse": "La prémisse précise pour Lucas (1-2 phrases, 1ère personne implicite)",
      "question_universelle": "Ce que le spectateur se demande sur lui-même",
      "ancrage": "Le contexte quotidien concret",
      "score_confiance": 0.0
    }}
  ]
}}"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.9,
                max_output_tokens=2048,
                response_mime_type="application/json",
            ),
        )
        data = json.loads(response.text)
        return data.get("suggestions", [])
    except Exception as e:
        print(f"   ⚠️  Gemini distillation erreur : {e}")
        return []


# ─────────────────────────────────────────────
#  Point d'entrée principal
# ─────────────────────────────────────────────


def pick_trending_premises(n: int = 5, region: str = "FR") -> list[dict]:
    """
    Retourne n prémisses suggérées.
    Avec YOUTUBE_API_KEY : data-driven (tendances réelles).
    Sans : Gemini seul sur les situations-socles.
    """
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY manquante.")
        return []

    if YOUTUBE_API_KEY:
        print("   📡 Récupération des tendances YouTube France…")
        raw = _fetch_youtube_trending(region=region)
        top = _score_videos(raw, top_n=15)
        print(f"   ✅ {len(top)} vidéos analysées (top engagement rate)")
    else:
        print("   ℹ️  Pas de YOUTUBE_API_KEY — mode Gemini seul (situations-socles)")
        top = []

    print("   🧠 Distillation Gemini…")
    suggestions = _distill_with_gemini(top, n_suggestions=n, region=region)
    return suggestions


def afficher_suggestions(suggestions: list[dict]) -> Optional[int]:
    """Affiche les suggestions et retourne l'index choisi (0-based) ou None."""
    if not suggestions:
        print("❌ Aucune suggestion générée.")
        return None

    print(f"\n{'═' * 60}")
    print("  🎯 PRÉMISSES SUGGÉRÉES PAR LES TENDANCES")
    print(f"{'═' * 60}")
    for i, s in enumerate(suggestions, 1):
        print(
            f"\n  [{i}] [{s.get('territoire', '?').upper()}] {s.get('situation', '')}"
        )
        print(f"      → {s.get('premisse', '')}")
        print(f'      💭 "{s.get("question_universelle", "")}"')
        print(f"      📍 {s.get('ancrage', '')}")

    print(f"\n  [0] Aucune — saisir ma propre prémisse")
    try:
        choix = int(input("\n👉 Ton choix > ").strip())
        if 1 <= choix <= len(suggestions):
            return choix - 1
    except (ValueError, KeyboardInterrupt):
        pass
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Trend picker — suggestions de prémisses")
    ap.add_argument("--n", type=int, default=5, help="Nombre de suggestions (défaut 5)")
    ap.add_argument("--region", default="FR", help="Code région YouTube (défaut FR)")
    args = ap.parse_args()

    suggestions = pick_trending_premises(n=args.n, region=args.region)
    afficher_suggestions(suggestions)
