"""
═══════════════════════════════════════════════════════════════════════════
  CERVEAU « SÉRIE DRAMATIQUE 1ʳᵉ PERSONNE »  —  v2 : personnages vivants
═══════════════════════════════════════════════════════════════════════════
Génère des histoires dramatiques 100% originales, racontées à la première
personne par Lucas, autour de situations universelles qui révèlent le côté
sombre de la nature humaine.

Nouveautés v2 :
  • Personnages vivants : chaque secondaire a un détail inutile, une
    contradiction, un désir profond, un moment d'humanité, une phrase
    signature — et un plan de révélation progressif par épisode.
  • Situations-socles : les histoires partent de situations banales et
    reconnaissables, pas de scénarios extraordinaires.
  • Précision émotionnelle : les personnages sont montrés, jamais décrits.

Usage :
  python 1_generate_serie.py synopsis [--sujet "..."] [--episodes 8] [--scenes 9]
  python 1_generate_serie.py valider  [--serie series/<id>]
  python 1_generate_serie.py episode N [--serie series/<id>]
  python 1_generate_serie.py status   [--serie series/<id>]
  python 1_generate_serie.py list
"""

import os
import re
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("🚨 Erreur : GEMINI_API_KEY manquante dans .env")

client = genai.Client(api_key=API_KEY)

MODEL = os.getenv("SERIE_MODEL", "gemini-2.5-flash")
SERIES_DIR = Path("series")
PROJETS_DIR = Path("projets")

STYLE_LOCK = (
    "[STYLE LOCK: anime illustration style, semi-realistic detailed characters, "
    "hand-painted atmospheric background, warm artificial light source (glowing bulb, "
    "lantern or window) contrasting with cool deep blue night sky, lush environment "
    "with rich textures, Studio Ghibli aesthetic, expressive emotional character faces, "
    "contemporary or tropical intimate setting, full moon or stars optional, "
    "cinematic vertical composition 9:16, dark lower third for subtitles, "
    "NO text, NO watermark, NO live-action photography, NO 3D render]"
)

STYLE_LOCK_NOIR = (
    "[STYLE LOCK: black and white photography, high contrast noir cinematography, "
    "dramatic chiaroscuro shadows, dim interior lighting, vintage crime scene aesthetic, "
    "Agatha Christie detective novel atmosphere, sharp textures, grain, fog, "
    "9:16 vertical portrait, NO color, NO text, NO watermark]"
)

# Situations universelles — points de départ réalistes et reconnaissables
SITUATIONS_SOCLES = [
    # Amour
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
    # Famille
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
    # Travail
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
    # Amitié
    ("amitie", "Perdre un ami sans dispute, juste par dérive silencieuse"),
    ("amitie", "Découvrir qu'un proche parle dans ton dos depuis des années"),
    ("amitie", "Être là pour quelqu'un qui disparaît quand tu as besoin de lui"),
    ("amitie", "Comprendre trop tard qu'une amitié était à sens unique"),
    ("amitie", "Un ami qui change complètement dès qu'il obtient ce qu'il voulait"),
    # Soi
    ("soi", "Regretter une décision prise par peur, qui ne se représentera plus"),
    (
        "soi",
        "Réaliser qu'on a reproduit exactement ce qu'on détestait chez ses parents",
    ),
    ("soi", "Avoir gardé le silence au mauvais moment et vivre avec ça"),
    ("soi", "Choisir la sécurité et se demander des années après ce qu'on a raté"),
    ("soi", "Comprendre que quelqu'un qu'on croyait toxique nous protégeait"),
]


# ═══════════════════════════════════════════════════════════
#  MODÈLES STRUCTURÉS PYDANTIC
# ═══════════════════════════════════════════════════════════


class PersonnageVivant(BaseModel):
    nom: str = Field(description="Prénom du personnage.")
    relation: str = Field(
        description=(
            "Sa relation avec Lucas, avec la durée et le contexte. "
            "Ex: 'meilleur ami depuis 12 ans, se sont connus à la fac'."
        )
    )
    description_visuelle: str = Field(
        description=(
            "Description physique complète EN ANGLAIS pour la cohérence entre épisodes. "
            "Pour Lucas ('je'): jamais de face — mains, nuque, silhouette, reflet, POV. "
            "Pour les autres: description normale, traits distinctifs mémorables."
        )
    )
    detail_inutile: str = Field(
        description=(
            "Un détail de comportement ou d'habitude qui ne sert pas l'intrigue mais rend ce "
            "personnage réel. Doit être précis et concret. "
            "Ex: 'il apportait toujours quelque chose en venant, même juste un article découpé'. "
            "Ce détail est planté à l'épisode episode_detail et rappelé plus tard pour l'émotion."
        )
    )
    contradiction: str = Field(
        description=(
            "Une incohérence dans sa personnalité que Lucas observe sans l'expliquer. "
            "Ex: 'courageux sur les grandes choses, incapable de dire non à sa mère'. "
            "Planté naturellement dans une scène, jamais commenté directement."
        )
    )
    desir_profond: str = Field(
        description=(
            "Ce que ce personnage veut VRAIMENT — pas ce qu'il dit. Lucas le devine à travers "
            "ses actes répétés, jamais nommé explicitement dans la narration."
        )
    )
    moment_humanite: str = Field(
        description=(
            "Un moment PRÉCIS où le spectateur comprend et presque sympathise avec ce personnage, "
            "même s'il fait du mal. Doit arriver AVANT la trahison/rupture. "
            "Ex: 'elle m'a dit qu'elle avait peur de devenir sa mère — je n'avais pas compris'."
        )
    )
    phrase_signature: str = Field(
        description=(
            "Une expression ou façon de parler qui lui appartient. Citée par Lucas, "
            "reconnaissable immédiatement par le spectateur à chaque réapparition."
        )
    )
    episode_introduction: int = Field(
        description=(
            "Numéro de l'épisode où ce personnage apparaît pour la première fois (1 à N). "
            "Introduction : une seule action concrète, pas de description."
        )
    )
    episode_detail: int = Field(
        description=(
            "Épisode où planter le detail_inutile naturellement dans une scène."
        )
    )
    episode_humanite: int = Field(
        description=(
            "Épisode du moment_humanite. Doit être AVANT l'épisode où ce personnage déçoit Lucas."
        )
    )


class SituationSocle(BaseModel):
    territoire: str = Field(description="amour | famille | travail | amitie | soi")
    situation: str = Field(
        description=(
            "La situation universelle de base, formulée précisément. "
            "Doit être reconnaissable par le plus grand nombre possible."
        )
    )
    question_universelle: str = Field(
        description=(
            "La question que le spectateur se pose sur lui-même en regardant. "
            "Ex: 'Est-ce que j'aurais vu les signes ?' ou 'J'aurais fait pareil ?'"
        )
    )
    ancrage_quotidien: str = Field(
        description=(
            "Le contexte banal et concret où ça se passe. "
            "Ex: 'bureau open space', 'appartement partagé depuis 3 ans', 'dîner de famille du dimanche'."
        )
    )


class EpisodeOutline(BaseModel):
    numero: int
    titre: str
    resume: str = Field(
        description="Résumé en français, 3 à 5 phrases, à la première personne implicite."
    )
    beat_dramatique: str = Field(
        description="hook/conflit | montée | révélation | rupture | escalade | twist | dénouement"
    )
    cliffhanger: str = Field(
        description="La phrase-hameçon FINALE (français, 1ʳᵉ personne) qui rend l'épisode suivant obligatoire."
    )
    personnages_actifs: List[str] = Field(
        description="Prénoms des personnages présents dans cet épisode."
    )
    traits_a_revealer: List[str] = Field(
        description=(
            "Traits de personnages à révéler dans cet épisode selon le plan. "
            "Ex: ['Thomas.detail_inutile', 'Marie.moment_humanite']. "
            "Vide si aucun trait planifié pour cet épisode."
        )
    )


class SerieSynopsis(BaseModel):
    titre: str = Field(description="Titre viral de la série (court, intriguant).")
    logline: str = Field(
        description="Pitch d'une phrase, à la première personne, type punchline."
    )
    premisse: str = Field(
        description="La situation de départ et le conflit central, en français, à la 1ʳᵉ personne."
    )
    narrateur: str = Field(
        description="Qui est Lucas dans CETTE série : âge, situation, ce qu'il a à perdre."
    )
    narrateur_genre: str = Field(description="'masculin' ou 'féminin'.")
    themes: List[str] = Field(
        description="Thèmes parmi : amour, trahison, argent, pouvoir, lâcheté, ambition, famille."
    )
    situation_socle: SituationSocle = Field(
        description=(
            "La situation universelle de base — ce qui rend cette histoire reconnaissable par tous."
        )
    )
    personnages: List[PersonnageVivant] = Field(
        description=(
            "Tous les personnages secondaires importants avec leur profil émotionnel complet "
            "et leur plan de révélation progressive. Maximum 4 personnages."
        )
    )
    episodes: List[EpisodeOutline] = Field(
        description="Les N épisodes dans l'ordre de l'arc narratif."
    )


class Scene(BaseModel):
    id: int
    audio_tts: str = Field(
        description=(
            "Texte EXACT lu par la voix-off, en français, à la PREMIÈRE PERSONNE ('je'). "
            "Phrases courtes et incisives. 18 à 25 mots max. "
            "Scène 1 = hook brutal (plus court). Dernière = cliffhanger."
        )
    )
    subtitle: str = Field(description="Sous-titre, identique MOT POUR MOT à audio_tts.")
    veo_prompt: str = Field(
        description=(
            "UNE action physique précise + un mouvement de caméra EN ANGLAIS. "
            "Si un personnage secondaire apparaît: respecter sa description_visuelle. "
            "Lucas n'est JAMAIS de face. Finit par le STYLE LOCK."
        )
    )
    lyria_prompt: str = Field(
        description="Ambiance/foley EN ANGLAIS. Finit par ', no melody, no music'."
    )


class EpisodeScript(BaseModel):
    scenes: List[Scene]


# ── Modèles pour le mode MYSTÈRE (Agatha Christie) ──────────────────────────


class IndiceCache(BaseModel):
    objet_ou_fait: str = Field(
        description=(
            "Le détail précis planté dans l'épisode 1 (objet, comportement, phrase, heure). "
            "Ex: 'le verre de whisky avec du rouge à lèvres', 'la photo retournée sur le bureau'."
        )
    )
    apparence_innocente: str = Field(
        description=(
            "Ce que le spectateur pense de ce détail en épisode 1 — anodin, normal."
        )
    )
    signification_reelle: str = Field(
        description=(
            "Ce que ce détail révèle vraiment en épisode 2. Doit changer la lecture de toute la scène."
        )
    )
    scene_ep1: int = Field(
        description="Numéro de la scène de l'épisode 1 où cet indice apparaît."
    )


class PersonnageMystere(BaseModel):
    prenom: str = Field(description="Prénom du personnage.")
    role: str = Field(
        description="Son rôle dans l'histoire (propriétaire, voisin, suspect, victime...)."
    )
    relation_avec_autres: str = Field(
        description=(
            "Ses liens avec les autres personnages — y compris les liens cachés non révélés en épisode 1."
        )
    )
    secret: str = Field(
        description="Ce qu'il/elle cache — révélé seulement en épisode 2."
    )
    description_visuelle: str = Field(
        description=(
            "Description physique EN ANGLAIS pour la cohérence des images. "
            "Tenue, silhouette, traits distinctifs — style roman policier années 40-60."
        )
    )
    phrase_signature: str = Field(
        description=(
            "Une phrase ou tic de langage qui lui appartient, réutilisée pour le reconnaître."
        )
    )


class MaisonMystere(BaseModel):
    titre: str = Field(
        description="Titre court type 'La Maison du 12 Rue des Acacias' ou 'Le Manoir Beaumont'."
    )
    adresse: str = Field(description="Adresse fictive précise et évocatrice.")
    type_crime: str = Field(
        description="Le crime ou mystère central (meurtre, disparition, empoisonnement...)."
    )
    description_maison: str = Field(
        description=(
            "Description EN ANGLAIS de la maison — architecture, atmosphère, détails qui créent l'angoisse. "
            "Style: maison bourgeoise, cottage isolé, appartement haussmannien... 2-3 phrases."
        )
    )
    personnages: List[PersonnageMystere] = Field(description="2 à 4 personnages max.")
    indices: List[IndiceCache] = Field(
        description=(
            "5 à 7 indices cachés plantés en épisode 1, révélés en épisode 2. "
            "Chaque indice doit recontextualiser une scène entière."
        )
    )
    episode1_scenes: List[Scene] = Field(
        description=(
            "Épisode 1 : 8 à 10 scènes. Présente la maison et ses habitants. "
            "Chaque scène plante un ou deux indices en surface (apparence innocente). "
            "Voix de narrateur omniscient, ton froid et précis — pas de 'je'. "
            "Fin : découverte du crime ou de l'anomalie centrale."
        )
    )
    episode2_scenes: List[Scene] = Field(
        description=(
            "Épisode 2 : 8 à 10 scènes. Révèle la signification réelle de chaque indice. "
            "Chaque scène = un rappel flash de l'indice + sa vraie signification. "
            "Dernière scène : le coupable ou le twist final imparable."
        )
    )


# ═══════════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════

SYSTEM_SYNOPSIS = """Tu es un scénariste spécialisé dans les histoires à la première personne qui révèlent le côté sombre de la nature humaine.

TON ANGLE : Les histoires qui touchent le plus de monde ne sont pas les plus extraordinaires — elles sont les plus PRÉCISES sur des situations universelles. La noirceur est dans la banalité, pas dans l'extrême. Les gens les plus sombres que Lucas rencontre sont des gens ordinaires qui font des choses ordinairement mauvaises.

LE NARRATEUR : Lucas, début de la trentaine. Ni héros ni victime parfaite. Il a fait des erreurs. Ce qui lui arrive révèle quelque chose de sombre chez les gens qui l'entourent — et parfois chez lui-même. Il raconte des mois après, avec du recul, une voix posée qui cache l'émotion.

RÈGLES ABSOLUES :
1. SITUATION UNIVERSELLE : partir d'une situation que des millions de personnes ont vécue ou connaissent. Le spectateur doit se dire "c'est exactement ça" pas "quel scénario".
2. PERSONNAGES VIVANTS : chaque personnage secondaire doit avoir une vraie vie intérieure. Ils ne sont pas des fonctions narratives. Lucas les aime avant qu'ils le déçoivent — le spectateur aussi.
3. PRÉCISION > INTENSITÉ : "Il a répondu 'vu' à mon message. Juste 'vu'. Après 4 ans." bat "Il m'a ignoré". Les détails concrets créent l'émotion.
4. PLAN DE RÉVÉLATION : chaque personnage se révèle progressivement. Le detail_inutile est planté tôt. Le moment_humanite arrive AVANT la trahison. Le spectateur doit avoir aimé ce personnage AVANT de le voir faire du mal.
5. QUESTION UNIVERSELLE : chaque série doit amener le spectateur à se demander quelque chose sur lui-même.
6. PREMIÈRE PERSONNE stricte du début à la fin.

Réponds UNIQUEMENT via le schéma structuré demandé."""

SYSTEM_EPISODE = """Tu es un scénariste viral. Tu écris des confessions à la première personne pour Lucas. Chaque épisode doit être impossible à arrêter.

CAPTIVATION : Le spectateur doit être accroché dès la première seconde et frustrée de ne pas avoir la suite. La narration ne doit jamais être plate.

RÈGLE HOOK (scène 1) — OBLIGATOIRE :
Commence par une RÉVÉLATION qui brise les attentes. Le résultat d'abord, jamais le début. Un fait concret, précis, shocking.
❌ "Je vais vous raconter..." / "Tout a commencé quand..." / "Je ne savais pas encore que..."
✅ "Il m'a envoyé un message à 23h47. 'On doit parler.' J'avais moi-même écrit ce message trois ans plus tôt."
✅ "Ce matin-là, j'ai découvert que le compte était vide. Deux cent mille euros. En une nuit."

RÈGLE MONTÉE : Chaque scène doit être plus tendue que la précédente. Une info nouvelle qui change tout. Une trahison qui s'aggrave. Pas deux scènes au même niveau.

RÈGLE PERSONNAGES : Montre, ne décris jamais. Une action concrète révèle plus qu'un adjectif.
❌ "Elle semblait gênée."
✅ "Elle a regardé son téléphone deux fois pendant que je parlais."

RÈGLE CLIFFHANGER (dernière scène) — OBLIGATOIRE :
Une information PRÉCISE que le spectateur n'a pas. Il doit SAVOIR ce qu'il rate.
❌ "Et c'est là que tout a changé."
✅ "Et dans cette boîte mail, il y avait 47 messages. Tous envoyés à mon patron. Tous signés de mon nom."

RÈGLE CHIFFRES ET DÉTAILS : Les chiffres précis et les détails inutiles créent la vérité. "3 ans" bat "longtemps". "23h47" bat "tard le soir". "47 messages" bat "beaucoup de messages".

LONGUEUR : 12 à 18 mots par scène. Pas plus. Une phrase = un souffle = un impact.

Réponds UNIQUEMENT via le schéma structuré demandé."""

# ── Modèle et prompt pour le mode vidéo unique ──────────────────────────────


class VideoUniqueSetup(BaseModel):
    titre: str = Field(description="Titre court et accrocheur (5 mots max).")
    situation_socle: SituationSocle
    personnages: List[PersonnageVivant] = Field(
        description="1 à 2 personnages secondaires max. Profil émotionnel complet."
    )
    scenes: List[Scene] = Field(
        description="Toutes les scènes de la vidéo dans l'ordre. Arc complet en une seule vidéo."
    )


SYSTEM_VIDEO_UNIQUE = """Tu es un scénariste viral. Tu écris une histoire COMPLÈTE à la première personne pour Lucas en UNE SEULE vidéo de 60 à 90 secondes.

DIFFÉRENCE CLÉ avec un épisode : l'histoire doit être ENTIÈRE. Début → conflit → révélation → fin. Pas de cliffhanger — une conclusion qui provoque une réaction émotionnelle forte (indignation, empathie, question morale).

STRUCTURE OBLIGATOIRE :
- Scène 1 (HOOK) : résultat shocking d'abord. Le spectateur veut savoir comment on en est arrivé là.
- Scènes 2-3 : contexte minimal, juste ce qu'il faut pour comprendre.
- Scènes 4-6 : montée — la trahison/révélation se construit progressivement.
- Scène 7-8 : le moment de vérité. Ce que Lucas découvre ou décide.
- Dernière scène (FIN) : une conclusion qui fait réfléchir. Pas "et ensuite ?", mais "et moi j'aurais fait quoi ?". Peut se terminer par une question directe au spectateur.

RÈGLES NARRATION :
- Hook brutal : résultat d'abord, chiffres précis, jamais "Je vais vous raconter..."
- Montrer, jamais décrire : "Elle a regardé son téléphone deux fois" > "elle semblait gênée"
- 12 à 18 mots par scène. Une phrase = un souffle = un impact.
- Personnages : 1 à 2 max. Chacun a un detail_inutile planté tôt et un moment d'humanité AVANT la révélation.
- Fin : provocante mais conclue. La dernière phrase doit déclencher des commentaires.

Réponds UNIQUEMENT via le schéma structuré demandé."""

SYSTEM_MYSTERE = """Tu es un auteur de romans policiers à la Agatha Christie. Tu construis des histoires à 2 épisodes autour d'une maison et d'un crime, en plantant des indices cachés dans l'épisode 1 qui prennent tout leur sens en épisode 2.

STYLE NARRATIF : Voix de narrateur omniscient, froid, précis. PAS de "je" — tu observes et décris. Chaque phrase est un fait. Chaque fait cache quelque chose.

ÉPISODE 1 — "LA MAISON" :
- Présente la maison et ses habitants avec leurs routines apparemment normales.
- Chaque scène plante 1 ou 2 indices en surface (apparence innocente).
- Le spectateur voit tout mais ne comprend rien encore.
- Dernière scène : découverte du crime ou de l'anomalie centrale.
- Ton : atmosphérique, suspense croissant, questions non posées.

ÉPISODE 2 — "LES RÉVÉLATIONS" :
- Revient sur chaque indice de l'épisode 1 et révèle sa vraie signification.
- Structure : flash de rappel → "Ce que vous n'aviez pas remarqué..." → révélation.
- Chaque révélation doit recontextualiser une scène entière de l'épisode 1.
- Dernière scène : le coupable ou le twist final imparable.
- Ton : implacable, clinique, chaque révélation plus forte que la précédente.

RÈGLES INDICES :
- Minimum 5 indices cachés, maximum 7.
- Un indice = un objet précis, un comportement précis, une heure précise, une phrase précise.
- L'indice doit sembler COMPLÈTEMENT ANODIN en épisode 1.
- En épisode 2, il doit TOUT CHANGER.
- Exemples : "le verre de whisky avec une trace de rouge à lèvres" / "la fenêtre ouverte malgré le froid" / "le chien qui n'a pas aboyé"

RÈGLES NARRATION (les deux épisodes) :
- 15 à 22 mots par scène. Phrases courtes, sèches, précises.
- Chiffres précis : "23h47", "3 verres", "14 marches".
- NE PAS expliquer. Observer et constater seulement.
- Les veo_prompts doivent décrire des plans fixes d'intérieur : objets, silhouettes, ombres, détails de la maison.
- Style B&W crime scene photography. Terminer OBLIGATOIREMENT par le STYLE LOCK NOIR fourni.

Réponds UNIQUEMENT via le schéma structuré demandé."""


# ═══════════════════════════════════════════════════════════
#  VIDÉO UNIQUE — génération complète en un seul appel
# ═══════════════════════════════════════════════════════════


def generer_video_unique(
    sujet: Optional[str],
    n_scenes: int = 10,
    situation_suggeree: Optional[dict] = None,
) -> Optional[str]:
    """Génère une vidéo autonome complète (arc entier, pas de cliffhanger)."""
    print(f"\n{'═' * 60}\n  🎬 VIDÉO UNIQUE — {n_scenes} scènes\n{'═' * 60}")
    if sujet:
        print(f"  📌 Sujet : {sujet[:90]}")

    socles_examples = "\n".join(f"  [{t}] {s}" for t, s in SITUATIONS_SOCLES[:8])

    if situation_suggeree:
        consigne = (
            f"SITUATION DATA-DRIVEN :\nTerritoire : {situation_suggeree.get('territoire', '')}\n"
            f"Situation : {situation_suggeree.get('situation', '')}\n\n"
        )
    elif sujet:
        consigne = f"SUJET IMPOSÉ :\n«{sujet}»\n\n"
    else:
        consigne = (
            f"Choisis une situation parmi ces exemples (ou crée une variation originale) :\n"
            f"{socles_examples}\n\n"
        )

    user = (
        f"{consigne}"
        f"Génère une vidéo dramatique COMPLÈTE de {n_scenes} scènes (60-90 secondes au total), "
        f"racontée à la première personne par Lucas.\n\n"
        f"L'histoire doit avoir un arc ENTIER : hook → développement → révélation → conclusion.\n"
        f"Maximum 2 personnages secondaires. Chacun a un detail_inutile planté tôt "
        f"et un moment_humanite AVANT la révélation.\n\n"
        f"STYLE LOCK de chaque veo_prompt :\n{STYLE_LOCK}"
    )

    data = _generate_json(
        SYSTEM_VIDEO_UNIQUE,
        user,
        VideoUniqueSetup,
        temperature=1.0,
        label="vidéo unique",
        max_tokens=12000,
    )
    if not data:
        print("❌ Échec de la génération.")
        return None

    titre = data.get("titre", "Video")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    projet_nom = f"{timestamp}_{slugify(titre)}"
    dossier = PROJETS_DIR / projet_nom
    (dossier / "audio" / "sfx").mkdir(parents=True, exist_ok=True)

    personnages = data.get("personnages", [])
    if isinstance(personnages, list):
        personnages = [p if isinstance(p, dict) else {} for p in personnages]

    scenes = data.get("scenes", [])
    for i, s in enumerate(scenes, 1):
        s["id"] = s.get("id", i)
        veo = (s.get("veo_prompt") or "").strip()
        if veo and "[STYLE LOCK" not in veo:
            s["veo_prompt"] = f"{veo} {STYLE_LOCK}"
        elif not veo:
            s["veo_prompt"] = (
                f"A lone figure at a table under a warm lamp, night outside the window, slow push in. {STYLE_LOCK}"
            )
        lyria = (s.get("lyria_prompt") or "").strip()
        if not lyria:
            s["lyria_prompt"] = (
                "low ominous sub-bass drone, tense breathing, distant city hum, no melody, no music"
            )
        elif not lyria.endswith(", no melody, no music"):
            s["lyria_prompt"] = f"{lyria.rstrip(',.')}, no melody, no music"
        s["real_media_queries"] = []
        s["voix_off_tts"] = s.get("audio_tts", "")
        s["sous_titre"] = s.get("subtitle", "")
        s["lyria_type"] = "foley_ambiance"

    script_json = {
        "projet": projet_nom,
        "format": "video_unique",
        "titre": titre,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "narrateur_genre": "masculin",
        "situation_socle": data.get("situation_socle", {}),
        "personnages": personnages,
        "visual_bible": _personnages_to_visual_bible(personnages),
        "scenes": scenes,
        "niche": titre,
    }
    (dossier / "script.json").write_text(
        json.dumps(script_json, indent=4, ensure_ascii=False), encoding="utf-8"
    )

    # Affichage
    print(f"\n  📺 {titre}")
    socle = data.get("situation_socle", {})
    if socle:
        print(f"  🌍 [{socle.get('territoire', '')}] {socle.get('situation', '')}")
    if personnages:
        for p in personnages:
            print(f"  👤 {p.get('nom', '?')} — {p.get('relation', '')}")
            print(f'     Signature : "{p.get("phrase_signature", "")}"')
    print(f"\n  🎬 {len(scenes)} scènes :")
    for s in scenes:
        tag = (
            "🪝"
            if s["id"] == 1
            else ("🏁" if s["id"] == len(scenes) else f"#{s['id']}")
        )
        print(f"  [{tag}] {s.get('audio_tts', '')}")

    print(f"\n💾 Vidéo unique sauvegardée → {dossier}/script.json")
    print(f"   → Rendu : python batch_produce.py {dossier}")
    return str(dossier)


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════


def slugify(text: str, n: int = 5) -> str:
    mots = re.sub(r"[^\w\s]", "", text or "").split()[:n]
    return "_".join(w.capitalize() for w in mots) or "Serie"


def _norm_genre(valeur: str) -> str:
    v = (valeur or "").strip().lower().replace("é", "e").replace("è", "e")
    if v in {"f", "feminin", "femme", "female", "woman", "fille", "girl"}:
        return "féminin"
    return "masculin"


def _latest_serie() -> Optional[Path]:
    if not SERIES_DIR.is_dir():
        return None
    candidates = [d for d in SERIES_DIR.iterdir() if (d / "serie.json").is_file()]
    return max(candidates, key=lambda d: d.name) if candidates else None


def _resolve_serie(arg: Optional[str]) -> Path:
    if arg:
        p = Path(arg)
        if (p / "serie.json").is_file():
            return p
        if (SERIES_DIR / arg / "serie.json").is_file():
            return SERIES_DIR / arg
        raise SystemExit(f"❌ Série introuvable : {arg}")
    latest = _latest_serie()
    if not latest:
        raise SystemExit(
            "❌ Aucune série trouvée. Lance d'abord : python 1_generate_serie.py synopsis"
        )
    return latest


def _load_serie(serie_dir: Path) -> dict:
    return json.loads((serie_dir / "serie.json").read_text(encoding="utf-8"))


def _save_serie(serie_dir: Path, data: dict):
    (serie_dir / "serie.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _strip_fences(raw: str) -> str:
    return re.sub(
        r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE
    )


def _generate_json(
    system: str,
    user: str,
    schema,
    temperature: float,
    label: str,
    max_tokens: int = 8192,
):
    for attempt in range(3):
        try:
            print(f"   🧠 Gemini ({label}) — essai {attempt + 1}/3…")
            response = client.models.generate_content(
                model=MODEL,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            return json.loads(_strip_fences(response.text))
        except Exception as e:
            print(f"   ⚠️ Erreur ({label}, essai {attempt + 1}) : {str(e)[:160]}")
            time.sleep(3)
    return None


def _personnages_to_visual_bible(personnages: list) -> dict:
    """Dérive la visual_bible (format legacy) depuis la liste de personnages vivants.
    Nécessaire pour la compatibilité avec 2.7_media_fetcher et 3_render_hyperframes."""
    out = {}
    for p in personnages:
        if isinstance(p, dict):
            nom = p.get("nom", "")
            desc = p.get("description_visuelle", "")
            if nom and desc:
                out[nom] = desc
    return out


def _build_personnages_context(personnages: list, episode_num: int) -> str:
    """Construit le contexte personnages pour un épisode donné.
    Inclut tous les traits révélés jusqu'à cet épisode."""
    if not personnages:
        return ""
    lines = ["\nPERSONNAGES ET PLAN DE RÉVÉLATION :"]
    for p in personnages:
        if not isinstance(p, dict):
            continue
        ep_intro = p.get("episode_introduction", 1)
        if ep_intro > episode_num:
            continue  # pas encore introduit
        lines.append(f"\n  {p.get('nom', '?')} ({p.get('relation', '')})")
        lines.append(f'    Phrase signature : "{p.get("phrase_signature", "")}"')
        # Traits déjà révélés
        if episode_num >= p.get("episode_detail", 99):
            lines.append(
                f"    Detail inutile (déjà planté) : {p.get('detail_inutile', '')}"
            )
        if episode_num >= p.get("episode_humanite", 99):
            lines.append(
                f"    Moment humanité (déjà révélé) : {p.get('moment_humanite', '')}"
            )
        lines.append(
            f"    Contradiction (à montrer quand pertinent) : {p.get('contradiction', '')}"
        )
        lines.append(
            f"    Désir profond (ne jamais nommer explicitement) : {p.get('desir_profond', '')}"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  PHASE 1 — SYNOPSIS
# ═══════════════════════════════════════════════════════════


def generer_synopsis(
    sujet: Optional[str],
    n_episodes: int,
    n_scenes: int,
    situation_suggeree: Optional[dict] = None,
) -> Optional[Path]:
    print(f"\n{'═' * 60}\n  🎬 PHASE 1 — SYNOPSIS ({n_episodes} épisodes)\n{'═' * 60}")
    if sujet:
        print(f"  📌 Prémisse imposée : {sujet[:90]}")

    # Construction du contexte situations-socles pour guider Gemini
    socles_examples = "\n".join(f"    [{t}] {s}" for t, s in SITUATIONS_SOCLES[:10])

    if situation_suggeree:
        consigne_sujet = (
            f"SITUATION DATA-DRIVEN (basée sur les tendances actuelles) :\n"
            f"Territoire : {situation_suggeree.get('territoire', '')}\n"
            f"Situation : {situation_suggeree.get('situation', '')}\n"
            f"Développe une série originale autour de ça.\n\n"
        )
    elif sujet:
        consigne_sujet = (
            f"PRÉMISSE IMPOSÉE :\n«{sujet}»\n"
            f"Développe l'arc autour de ça en restant 100% original.\n\n"
        )
    else:
        consigne_sujet = (
            f"Choisis une situation parmi ces exemples de situations universelles "
            f"(ou invente une variation originale dans le même esprit) :\n{socles_examples}\n\n"
        )

    user = (
        f"{consigne_sujet}"
        f"Conçois l'arc narratif complet d'une série dramatique de {n_episodes} épisode(s) "
        f"de 60 à 90 secondes, racontée à la première personne par Lucas.\n\n"
        f"IMPORTANT : pour chaque personnage secondaire, conçois le plan de révélation "
        f"progressive (quel épisode pour l'introduire, planter le detail_inutile, "
        f"et placer le moment_humanite AVANT la trahison).\n\n"
        f"Chaque épisode aura environ {n_scenes} scènes."
    )

    data = _generate_json(
        SYSTEM_SYNOPSIS, user, SerieSynopsis, temperature=1.0, label="synopsis"
    )
    if not data:
        print("❌ Échec de la génération du synopsis.")
        return None

    titre = data.get("titre", "Serie")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    serie_id = f"{timestamp}_{slugify(titre)}"
    serie_dir = SERIES_DIR / serie_id
    serie_dir.mkdir(parents=True, exist_ok=True)

    # Normalisation des personnages
    personnages = data.get("personnages", [])
    if isinstance(personnages, list):
        personnages = [p if isinstance(p, dict) else {} for p in personnages]

    # Épisodes
    episodes = []
    for ep in data.get("episodes", [])[:n_episodes]:
        episodes.append(
            {
                "numero": ep.get("numero"),
                "titre": ep.get("titre", ""),
                "resume": ep.get("resume", ""),
                "beat_dramatique": ep.get("beat_dramatique", ""),
                "cliffhanger": ep.get("cliffhanger", ""),
                "personnages_actifs": ep.get("personnages_actifs", []),
                "traits_a_revealer": ep.get("traits_a_revealer", []),
                "status": "pending",
                "project_dir": None,
            }
        )

    serie = {
        "serie_id": serie_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "synopsis_pending_validation",
        "n_episodes": n_episodes,
        "n_scenes_per_episode": n_scenes,
        "sujet_initial": sujet or "",
        "titre": titre,
        "logline": data.get("logline", ""),
        "premisse": data.get("premisse", ""),
        "narrateur": data.get("narrateur", ""),
        "narrateur_genre": _norm_genre(data.get("narrateur_genre", "masculin")),
        "themes": data.get("themes", []),
        "situation_socle": data.get("situation_socle", {}),
        "personnages": personnages,
        # visual_bible legacy (compatibilité aval)
        "visual_bible": _personnages_to_visual_bible(personnages),
        "episodes": episodes,
    }
    _save_serie(serie_dir, serie)
    afficher_synopsis(serie)
    print(f"\n💾 Synopsis sauvegardé → {serie_dir}/serie.json")
    print(f"⏸️  STATUT : synopsis_pending_validation")
    print(f"   → Valide avec :  python 1_generate_serie.py valider --serie {serie_dir}")
    return serie_dir


# ═══════════════════════════════════════════════════════════
#  GATE — VALIDATION
# ═══════════════════════════════════════════════════════════


def valider_synopsis(serie_dir: Path):
    serie = _load_serie(serie_dir)
    serie["status"] = "validated"
    serie["validated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_serie(serie_dir, serie)
    print(f"✅ Synopsis VALIDÉ → {serie_dir.name}")
    print(
        f"   → Génère l'épisode 1 :  python 1_generate_serie.py episode 1 --serie {serie_dir}"
    )


# ═══════════════════════════════════════════════════════════
#  PHASE 2 — ÉPISODE (un par un)
# ═══════════════════════════════════════════════════════════


def generer_episode(serie_dir: Path, numero: int) -> Optional[str]:
    serie = _load_serie(serie_dir)

    if serie.get("status") != "validated":
        print("⛔ Synopsis NON VALIDÉ. Impossible de générer un épisode.")
        print(
            f"   → Valide d'abord :  python 1_generate_serie.py valider --serie {serie_dir}"
        )
        return None

    episodes = serie.get("episodes", [])
    ep = next((e for e in episodes if e.get("numero") == numero), None)
    if ep is None:
        print(f"❌ Épisode {numero} absent du synopsis.")
        return None

    total = serie.get("n_episodes", len(episodes))
    n_scenes = serie.get("n_scenes_per_episode", 9)
    personnages = serie.get("personnages", [])

    print(
        f"\n{'═' * 60}\n  🎬 PHASE 2 — ÉPISODE {numero}/{total} — {ep.get('titre', '')}\n{'═' * 60}"
    )

    # Contexte de continuité
    bible_block = _build_personnages_context(personnages, numero)
    precedents = [e for e in episodes if e.get("numero", 0) < numero]
    prec_block = (
        "\n".join(
            f"  - Épisode {e['numero']} ({e.get('titre', '')}) : {e.get('resume', '')} "
            f"[cliffhanger : {e.get('cliffhanger', '')}]"
            for e in precedents
        )
        or "  (aucun — c'est le premier épisode)"
    )

    # Traits à révéler dans cet épisode
    traits_episode = ep.get("traits_a_revealer", [])
    traits_block = ""
    if traits_episode:
        traits_block = (
            f"\nTRAITS À RÉVÉLER DANS CET ÉPISODE (planter naturellement, ne jamais annoncer) :\n"
            + "\n".join(f"  - {t}" for t in traits_episode)
        )

    # Situation socle (pour maintenir l'ancrage universel)
    socle = serie.get("situation_socle", {})
    socle_block = ""
    if socle:
        socle_block = (
            f"\nSITUATION UNIVERSELLE DE LA SÉRIE :\n"
            f"  {socle.get('situation', '')}\n"
            f"  Question que le spectateur doit se poser : {socle.get('question_universelle', '')}\n"
            f"  Ancrage quotidien : {socle.get('ancrage_quotidien', '')}"
        )

    user = f"""SÉRIE : {serie.get("titre", "")}
LOGLINE : {serie.get("logline", "")}
PRÉMISSE : {serie.get("premisse", "")}
LUCAS DANS CETTE SÉRIE : {serie.get("narrateur", "")}
THÈMES : {", ".join(serie.get("themes", []))}
{socle_block}
{bible_block}

ÉPISODES PRÉCÉDENTS :
{prec_block}
{traits_block}

ÉPISODE À ÉCRIRE — n°{numero}/{total} : « {ep.get("titre", "")} »
Fonction dramatique : {ep.get("beat_dramatique", "")}
Personnages présents : {", ".join(ep.get("personnages_actifs", []))}
Résumé à développer : {ep.get("resume", "")}
Cliffhanger imposé (dernière scène) : {ep.get("cliffhanger", "")}

Écris cet épisode en EXACTEMENT {n_scenes} scènes.
Scène 1 = hook brutal (commencer par le résultat, pas le début).
Dernière scène = le cliffhanger.
STYLE LOCK à coller en fin de chaque veo_prompt :
{STYLE_LOCK}"""

    data = _generate_json(
        SYSTEM_EPISODE, user, EpisodeScript, temperature=0.9, label=f"épisode {numero}"
    )
    if not data:
        print("❌ Échec de la génération de l'épisode.")
        return None

    scenes = data.get("scenes", [])
    if not scenes:
        print("❌ Aucune scène générée.")
        return None

    # Post-traitement
    for i, s in enumerate(scenes, 1):
        s["id"] = s.get("id", i)
        veo = (s.get("veo_prompt") or "").strip()
        if veo and "[STYLE LOCK" not in veo:
            s["veo_prompt"] = f"{veo} {STYLE_LOCK}"
        elif not veo:
            s["veo_prompt"] = (
                f"First-person point of view, trembling hands on a table in a dim room, slow push in. {STYLE_LOCK}"
            )
        lyria = (s.get("lyria_prompt") or "").strip()
        if not lyria:
            s["lyria_prompt"] = (
                "low ominous sub-bass drone, tense breathing, distant city hum, no melody, no music"
            )
        elif not lyria.endswith(", no melody, no music"):
            s["lyria_prompt"] = f"{lyria.rstrip(',.')}, no melody, no music"
        s["real_media_queries"] = []
        s["voix_off_tts"] = s.get("audio_tts", "")
        s["sous_titre"] = s.get("subtitle", "")
        s["lyria_type"] = "foley_ambiance"

    # Écriture du projet épisode
    ep_slug = f"ep{numero:02d}_{slugify(ep.get('titre', ''), 4)}"
    projet_nom = f"{serie['serie_id']}_{ep_slug}"
    dossier = PROJETS_DIR / projet_nom
    (dossier / "audio" / "sfx").mkdir(parents=True, exist_ok=True)

    script_json = {
        "projet": projet_nom,
        "serie_id": serie["serie_id"],
        "episode": numero,
        "total_episodes": total,
        "niche": f"{serie.get('titre', '')} — Épisode {numero}/{total} : {ep.get('titre', '')}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "narrateur_genre": serie.get("narrateur_genre", "masculin"),
        "situation_socle": serie.get("situation_socle", {}),
        "personnages": personnages,
        "visual_bible": serie.get("visual_bible", {}),  # legacy compat
        "scenes": scenes,
    }
    (dossier / "script.json").write_text(
        json.dumps(script_json, indent=4, ensure_ascii=False), encoding="utf-8"
    )

    ep["status"] = "generated"
    ep["project_dir"] = str(dossier)
    ep["generated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_serie(serie_dir, serie)

    afficher_episode(script_json)
    print(f"\n💾 Épisode {numero} sauvegardé → {dossier}/script.json")
    suivant = numero + 1
    if any(e.get("numero") == suivant for e in episodes):
        print(
            f"   → Une fois validé :  python 1_generate_serie.py episode {suivant} --serie {serie_dir}"
        )
    else:
        print(f"   → Dernier épisode de la série. 🎉")
    return str(dossier)


# ═══════════════════════════════════════════════════════════
#  AFFICHAGE
# ═══════════════════════════════════════════════════════════


def afficher_synopsis(serie: dict):
    print(f"\n{'─' * 60}")
    print(f"  📺 {serie['titre']}")
    print(f"{'─' * 60}")
    print(f"  🎯 Logline  : {serie.get('logline', '')}")
    print(f"  🧩 Thèmes   : {', '.join(serie.get('themes', []))}")
    print(f"  🎙️  Voix     : {serie.get('narrateur_genre', 'masculin')}")

    socle = serie.get("situation_socle", {})
    if socle:
        print(f"\n  🌍 Situation universelle [{socle.get('territoire', '')}] :")
        print(f"     {socle.get('situation', '')}")
        print(f"     Question : {socle.get('question_universelle', '')}")

    print(f"\n  Prémisse : {serie.get('premisse', '')}")
    print(f"\n  Lucas : {serie.get('narrateur', '')}")

    personnages = serie.get("personnages", [])
    if personnages:
        print(f"\n  👥 Personnages ({len(personnages)}) :")
        for p in personnages:
            if isinstance(p, dict):
                print(f"\n    • {p.get('nom', '?')} — {p.get('relation', '')}")
                print(f'      Signature : "{p.get("phrase_signature", "")}"')
                print(f"      Détail    : {p.get('detail_inutile', '')}")
                print(
                    f"      Humanité  : ep.{p.get('episode_humanite', '?')} — {p.get('moment_humanite', '')[:80]}"
                )

    print(f"\n  🎬 Épisodes :")
    total = serie.get("n_episodes", len(serie.get("episodes", [])))
    for ep in serie.get("episodes", []):
        traits = ep.get("traits_a_revealer", [])
        traits_str = f"  [révèle: {', '.join(traits)}]" if traits else ""
        print(
            f"\n   ▶ ÉP.{ep.get('numero')}/{total} — {ep.get('titre', '')}  [{ep.get('beat_dramatique', '')}]{traits_str}"
        )
        print(f"     {ep.get('resume', '')}")
        print(f"     🪝 {ep.get('cliffhanger', '')}")


def afficher_episode(script: dict):
    print(f"\n{'─' * 60}")
    print(f"  🎬 {script.get('niche', '')}")
    print(f"{'─' * 60}")
    n_scenes = len(script.get("scenes", []))
    for s in script.get("scenes", []):
        vo = s.get("audio_tts", "")
        veo = re.sub(r"\s*\[STYLE LOCK[^\]]*\]", "", s.get("veo_prompt", "")).strip()
        tag = (
            "🪝 HOOK"
            if s["id"] == 1
            else ("🎣 CLIFF" if s["id"] == n_scenes else f"#{s['id']}")
        )
        print(f"\n  [{tag}] {vo}")
        print(f"         🎥 {veo[:140]}")


# ═══════════════════════════════════════════════════════════
#  STATUS / LIST
# ═══════════════════════════════════════════════════════════


def afficher_status(serie_dir: Path):
    serie = _load_serie(serie_dir)
    print(f"\n📺 {serie['titre']}  ({serie_dir.name})")
    print(f"   Statut : {serie.get('status')}")
    for ep in serie.get("episodes", []):
        mark = "✅" if ep.get("status") == "generated" else "⏳"
        print(
            f"   {mark} Ép. {ep.get('numero')} — {ep.get('titre', '')}  [{ep.get('status')}]"
            + (f"  → {ep.get('project_dir')}" if ep.get("project_dir") else "")
        )


def lister_series():
    if not SERIES_DIR.is_dir():
        print("Aucune série.")
        return
    for d in sorted(SERIES_DIR.iterdir()):
        if (d / "serie.json").is_file():
            s = _load_serie(d)
            gen = sum(
                1 for e in s.get("episodes", []) if e.get("status") == "generated"
            )
            print(
                f"  • {d.name} — {s.get('titre', '')} [{s.get('status')}] {gen}/{s.get('n_episodes')} épisodes"
            )


# ═══════════════════════════════════════════════════════════
#  MYSTÈRE — 2 épisodes Agatha Christie style
# ═══════════════════════════════════════════════════════════


def generer_mystere(sujet: Optional[str] = None) -> Optional[tuple[str, str]]:
    """Génère 2 épisodes mystère (contexte + révélations) dans 2 dossiers projets.
    Retourne (dossier_ep1, dossier_ep2) ou None si échec."""
    print(f"\n{'═' * 60}\n  🔍 MYSTÈRE AGATHA CHRISTIE — 2 épisodes\n{'═' * 60}")
    if sujet:
        print(f"  📌 Sujet : {sujet[:90]}")

    if sujet:
        user_prompt = f"MAISON/CRIME IMPOSÉ :\n«{sujet}»\nDéveloppe un mystère original autour de ça.\n\n"
    else:
        user_prompt = (
            "Invente une maison et un crime original. Choisis un cadre évocateur : "
            "manoir isolé, maison de village, appartement bourgeois, cottage en bord de mer...\n\n"
        )

    user_prompt += (
        f"Génère les 2 épisodes complets (8 à 10 scènes chacun) avec tous les indices cachés.\n"
        f"Chaque veo_prompt doit être en anglais et se terminer par :\n{STYLE_LOCK_NOIR}"
    )

    data = _generate_json(
        SYSTEM_MYSTERE,
        user_prompt,
        MaisonMystere,
        temperature=1.0,
        label="mystère",
        max_tokens=16000,
    )
    if not data:
        print("❌ Échec de la génération.")
        return None

    titre = data.get("titre", "Mystere")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    serie_id = f"{timestamp}_{slugify(titre)}"

    # ── Visual bible des personnages ──
    personnages = data.get("personnages", [])
    visual_bible = {
        p.get("prenom", ""): p.get("description_visuelle", "")
        for p in personnages
        if isinstance(p, dict)
    }

    def _post_process_scenes(scenes: list, ep_num: int) -> list:
        for i, s in enumerate(scenes, 1):
            s["id"] = s.get("id", i)
            veo = (s.get("veo_prompt") or "").strip()
            if veo and "[STYLE LOCK" not in veo:
                s["veo_prompt"] = f"{veo} {STYLE_LOCK_NOIR}"
            elif not veo:
                s["veo_prompt"] = (
                    f"Dark empty interior room, single lamp casting shadows on old furniture, "
                    f"close-up on a mysterious object. {STYLE_LOCK_NOIR}"
                )
            lyria = (s.get("lyria_prompt") or "").strip()
            if not lyria:
                s["lyria_prompt"] = (
                    "tension string drone, distant clock tick, creaking floor, no melody, no music"
                )
            elif not lyria.endswith(", no melody, no music"):
                s["lyria_prompt"] = f"{lyria.rstrip(',.')}, no melody, no music"
            s["real_media_queries"] = []
            s["voix_off_tts"] = s.get("audio_tts", "")
            s["sous_titre"] = s.get("subtitle", "")
            s["lyria_type"] = "foley_ambiance"
        return scenes

    # ── Épisode 1 — La Maison ──
    scenes1 = _post_process_scenes(data.get("episode1_scenes", []), 1)
    nom_ep1 = f"{serie_id}_ep01_La_Maison"
    dossier1 = PROJETS_DIR / nom_ep1
    (dossier1 / "audio" / "sfx").mkdir(parents=True, exist_ok=True)
    script1 = {
        "projet": nom_ep1,
        "mystere_id": serie_id,
        "episode": 1,
        "total_episodes": 2,
        "format": "mystere",
        "visual_style": "noir",
        "titre": f"{titre} — Épisode 1 : La Maison",
        "niche": f"{titre} — La Maison",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "narrateur_genre": "masculin",
        "adresse": data.get("adresse", ""),
        "type_crime": data.get("type_crime", ""),
        "description_maison": data.get("description_maison", ""),
        "personnages": personnages,
        "visual_bible": visual_bible,
        "indices": data.get("indices", []),
        "scenes": scenes1,
    }
    (dossier1 / "script.json").write_text(
        json.dumps(script1, indent=4, ensure_ascii=False), encoding="utf-8"
    )

    # ── Épisode 2 — Les Révélations ──
    scenes2 = _post_process_scenes(data.get("episode2_scenes", []), 2)
    nom_ep2 = f"{serie_id}_ep02_Les_Revelations"
    dossier2 = PROJETS_DIR / nom_ep2
    (dossier2 / "audio" / "sfx").mkdir(parents=True, exist_ok=True)
    script2 = {
        "projet": nom_ep2,
        "mystere_id": serie_id,
        "episode": 2,
        "total_episodes": 2,
        "format": "mystere",
        "visual_style": "noir",
        "titre": f"{titre} — Épisode 2 : Les Révélations",
        "niche": f"{titre} — Les Révélations",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "narrateur_genre": "masculin",
        "adresse": data.get("adresse", ""),
        "type_crime": data.get("type_crime", ""),
        "personnages": personnages,
        "visual_bible": visual_bible,
        "indices": data.get("indices", []),
        "scenes": scenes2,
    }
    (dossier2 / "script.json").write_text(
        json.dumps(script2, indent=4, ensure_ascii=False), encoding="utf-8"
    )

    # ── Affichage ──
    print(f"\n  🏠 {titre}")
    print(f"  📍 {data.get('adresse', '')}")
    print(f"  🔪 Crime : {data.get('type_crime', '')}")
    print(f"\n  👥 Personnages ({len(personnages)}) :")
    for p in personnages:
        if isinstance(p, dict):
            print(
                f"     • {p.get('prenom', '?')} ({p.get('role', '')}) — Secret : {p.get('secret', '')[:60]}"
            )
    print(f"\n  🔍 Indices cachés ({len(data.get('indices', []))}) :")
    for idx in data.get("indices", []):
        if isinstance(idx, dict):
            print(
                f"     • Scène {idx.get('scene_ep1', '?')} : {idx.get('objet_ou_fait', '')[:50]}"
            )
            print(f"       → Révélation : {idx.get('signification_reelle', '')[:70]}")
    print(f"\n  🎬 Épisode 1 ({len(scenes1)} scènes) :")
    for s in scenes1[:3]:
        print(f"     #{s['id']} {s.get('audio_tts', '')[:70]}")
    print(f"  🎬 Épisode 2 ({len(scenes2)} scènes) :")
    for s in scenes2[:3]:
        print(f"     #{s['id']} {s.get('audio_tts', '')[:70]}")

    print(f"\n💾 Épisode 1 → {dossier1}/script.json")
    print(f"💾 Épisode 2 → {dossier2}/script.json")
    return str(dossier1), str(dossier2)


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════


def main():
    ap = argparse.ArgumentParser(
        description="Cerveau série dramatique — v2 personnages vivants"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    # ── Mode mystère Agatha Christie (2 épisodes noir) ──
    p_mys = sub.add_parser(
        "mystere", help="Génère 2 épisodes mystère style Agatha Christie (B&W)"
    )
    p_mys.add_argument(
        "--sujet", help="Maison/crime imposé (ex: 'manoir isolé, empoisonnement')"
    )

    # ── Mode vidéo unique (drama) ──
    p_vid = sub.add_parser(
        "video", help="Génère une vidéo unique complète (arc entier)"
    )
    p_vid.add_argument("--sujet", help="Sujet/prémisse imposée")
    p_vid.add_argument(
        "--scenes", type=int, default=10, help="Nombre de scènes (défaut 10)"
    )

    # ── Mode série (legacy) ──
    p_syn = sub.add_parser("synopsis", help="[SÉRIE] Génère le synopsis de la série")
    p_syn.add_argument("--sujet", help="Prémisse imposée")
    p_syn.add_argument("--episodes", type=int, default=8)
    p_syn.add_argument("--scenes", type=int, default=9)

    p_val = sub.add_parser("valider", help="[SÉRIE] Valide le synopsis")
    p_val.add_argument("--serie")

    p_ep = sub.add_parser("episode", help="[SÉRIE] Génère un épisode")
    p_ep.add_argument("numero", type=int)
    p_ep.add_argument("--serie")

    p_st = sub.add_parser("status", help="[SÉRIE] Affiche l'état d'une série")
    p_st.add_argument("--serie")

    sub.add_parser("list", help="[SÉRIE] Liste toutes les séries")

    args = ap.parse_args()

    if args.cmd == "mystere":
        generer_mystere(args.sujet)
    elif args.cmd == "video":
        situation_suggeree = None
        trend_raw = os.getenv("TREND_SITUATION")
        if trend_raw:
            try:
                situation_suggeree = json.loads(trend_raw)
            except Exception:
                pass
        generer_video_unique(args.sujet, max(6, args.scenes), situation_suggeree)
    elif args.cmd == "synopsis":
        situation_suggeree = None
        trend_raw = os.getenv("TREND_SITUATION")
        if trend_raw:
            try:
                situation_suggeree = json.loads(trend_raw)
            except Exception:
                pass
        generer_synopsis(
            args.sujet, max(1, args.episodes), max(4, args.scenes), situation_suggeree
        )
    elif args.cmd == "valider":
        valider_synopsis(_resolve_serie(args.serie))
    elif args.cmd == "episode":
        generer_episode(_resolve_serie(args.serie), args.numero)
    elif args.cmd == "status":
        afficher_status(_resolve_serie(args.serie))
    elif args.cmd == "list":
        lister_series()


if __name__ == "__main__":
    main()
