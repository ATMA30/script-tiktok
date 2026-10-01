import os
import json
import re
import random
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("🚨 Erreur : GEMINI_API_KEY manquante dans .env")

client = genai.Client(api_key=API_KEY)

# ═══════════════════════════════════════════════════════════
#  MÉMOIRE PERSISTANTE DES SUJETS DÉJÀ TRAITÉS
# ═══════════════════════════════════════════════════════════
# Fichier JSON qui stocke chaque sujet déjà couvert, avec ses mots-clés
# distinctifs et le brief utilisé. Permet :
#   1. d'éviter de re-traiter un cas même sous un autre angle
#   2. de garder une trace auditable des sources utilisées
#   3. de regénérer la mémoire en scannant projets/ si le fichier est perdu
MEMORY_PATH = Path("projets/.subjects_memory.json")


def load_subject_memory() -> dict:
    """Charge la mémoire des sujets traités. Reconstruit depuis projets/ si absente."""
    if MEMORY_PATH.exists():
        try:
            return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            print("   ⚠️ Mémoire corrompue, reconstruction depuis projets/")
    # Reconstruction depuis projets/ (compatibilité avec l'ancien pipeline)
    mem = {"version": 1, "subjects": []}
    base = Path("projets")
    if base.is_dir():
        for proj in sorted(base.iterdir()):
            sj = proj / "script.json"
            if not sj.is_file():
                continue
            try:
                data = json.loads(sj.read_text(encoding="utf-8"))
                title = (data.get("niche") or "").strip()
                if title:
                    mem["subjects"].append(
                        {
                            "title": title,
                            "keywords": _extract_keywords(title),
                            "project_id": proj.name,
                            "source": "rebuilt_from_project",
                        }
                    )
            except Exception:
                pass
    save_subject_memory(mem)
    return mem


def save_subject_memory(mem: dict):
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(
        json.dumps(mem, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _extract_keywords(text: str) -> list[str]:
    """Extrait les mots distinctifs (>= 5 lettres) d'un titre, hors stop-words."""
    stop = {
        "affaire",
        "mystere",
        "mystère",
        "disparition",
        "etrange",
        "étrange",
        "histoire",
        "secret",
        "mysterieux",
        "mystérieuse",
        "inexpliquée",
        "inexplique",
        "documentée",
        "documente",
        "celebre",
        "célèbre",
    }
    return [
        w
        for w in re.findall(r"[a-z0-9àâäéèêëîïôöùûüç]{4,}", (text or "").lower())
        if w not in stop
    ]


def subject_already_used(candidate_keywords: list[str], memory: dict) -> bool:
    """Vrai si > 50% des mots distinctifs du candidat matchent un sujet déjà couvert."""
    cand = set(candidate_keywords)
    if not cand:
        return False
    for s in memory.get("subjects", []):
        prev = set(s.get("keywords", []))
        if not prev:
            continue
        overlap = cand & prev
        # Si au moins 2 mots distinctifs en commun OU > 40% du candidat dans le passé.
        if len(overlap) >= 2 or (len(overlap) / max(1, len(cand))) > 0.4:
            return True
    return False


# ═══════════════════════════════════════════════════════════
#  BANQUE DE MOTS-CLÉS DE RECHERCHE
#  Mots-clés LARGES, en français et en anglais. On laisse Google +
#  Gemini trouver ce qu'ils veulent dans la longue traîne plutôt que
#  de forcer "Indonesia 1987 forest" — trop spécifique → Gemini retombe
#  sur les classiques (Dyatlov, Roswell, Enfield…) parce qu'il n'a rien
#  d'autre qui matche pile les contraintes.
# ═══════════════════════════════════════════════════════════
SEARCH_TEMPLATES = [
    # Français — identité paranormal documenté
    "enquête paranormale documentée",
    "disparition collective inexpliquée documentée",
    "mystère maritime équipage disparu",
    "maison hantée enquête historique",
    "apparition fantôme témoins multiples",
    "créature inconnue rapports officiels",
    "lieu inexpliqué phénomène scientifique",
    "hantise enquête police",
    "phénomène paranormal archives militaires",
    "île abandonnée disparition mystérieuse",
    "phare disparition inexpliquée",
    # Anglais — documenté et paranormal
    "paranormal documented case",
    "documented ghost investigation historical",
    "unexplained maritime disappearance records",
    "mysterious island disappearance documented",
    "cryptid official witness reports",
    "documented haunting investigation",
    "strange unexplained event witnesses",
    "police paranormal report",
    "declassified strange phenomenon",
    "unexplained place scientific investigation",
]


def _instantiate_template(tpl: str) -> str:
    """Renvoie le template tel quel (plus de slots à remplir — gardé pour
    rester compatible avec discover_candidates qui appelle cette fonction)."""
    return tpl


# ═══════════════════════════════════════════════════════════
#  NICHES TRUE CRIME / PARANORMAL FALLBACKS
#  Banque élargie de cas documentés. Le pipeline pioche dedans
#  uniquement si la recherche en ligne échoue, en évitant tout
#  sujet déjà utilisé dans un projet précédent (voir derive_used_niches).
# ═══════════════════════════════════════════════════════════
NICHES_HORREUR = [
    # Disparitions inexpliquées
    "La disparition mystérieuse de Lars Mittank à l'aéroport de Varna en 2014.",
    "La disparition de Brian Shaffer devant les caméras de surveillance d'un bar à Columbus.",
    "La disparition inexplicable du pilote Frederick Valentich en 1978 en Australie.",
    "L'affaire des cinq de Yuba en 1978, cinq amis disparus dans la forêt de Plumas.",
    "La disparition de Maura Murray en 2004 sur une route de campagne du New Hampshire.",
    "La disparition d'Asha Degree à 9 ans en Caroline du Nord en 2000.",
    "Le mystère du vol Malaysia Airlines 370 disparu en mars 2014.",
    "La disparition des sœurs Sodder dans l'incendie de Noël 1945.",
    "La disparition de Madeleine McCann en 2007 au Portugal.",
    "L'affaire Springfield Three, trois femmes évaporées en 1992 au Missouri.",
    # Affaires criminelles non résolues
    "Le tueur du Zodiac et ses lettres cryptées à la presse de San Francisco.",
    "L'affaire du Black Dahlia, le meurtre d'Elizabeth Short en 1947 à Los Angeles.",
    "Les meurtres du Texarkana Moonlight en 1946.",
    "L'affaire Hinterkaifeck, la ferme bavaroise massacrée en 1922.",
    "Le tueur en série du Long Island, identifié en 2023 après quinze ans.",
    "L'affaire Tylenol Murders, sept morts par capsules empoisonnées en 1982.",
    # Mystères paranormaux / pseudo-paranormaux historiques
    "L'affaire des randonneurs du col Dyatlov en 1959 dans l'Oural.",
    "Le mystère du SS Ourang Medan, le cargo retrouvé avec un équipage figé dans l'effroi.",
    "L'exorcisme réel de Roland Doe en 1949 qui a inspiré l'Exorciste.",
    "L'incident du Silver Bridge et les apparitions du Mothman en 1966.",
    "Le mystère de la station fantôme UVB-76 qui émet depuis 1976.",
    "L'affaire de l'homme de Somerton (Tamam Shud) en Australie.",
    "Le poltergeist d'Enfield en Angleterre dans les années 1970.",
    "L'incident de Rendlesham Forest en 1980, le Roswell britannique.",
    "Le hum de Taos, le bourdonnement entendu par 2 % de la ville.",
    "L'affaire du Mary Celeste, le navire retrouvé à la dérive en 1872.",
    "La nuit d'horreur d'Aurora, le cas Travis Walton enlevé en 1975.",
    "Les apparitions de Doris Bither, l'affaire The Entity en 1974.",
    "L'incident de Roswell en 1947 et le débris du Ranch Foster.",
    # Mystères / phénomènes inexpliqués
    "Le projet MK-Ultra, les expériences de contrôle mental de la CIA.",
    "L'incident de Tunguska en 1908, l'explosion mystérieuse de la taïga sibérienne.",
    "Les voyageurs du temps présumés, John Titor et Andrew Carlssin.",
    "Le code mystérieux du manuscrit Voynich, jamais déchiffré.",
    "La porte de l'Enfer du Turkménistan, le cratère qui brûle depuis 1971.",
    "Le mystère du Bermuda Triangle et la disparition du vol 19 en 1945.",
]


# ═══════════════════════════════════════════════════════════
#  MODÈLES STRUCTURÉS PYDANTIC
# ═══════════════════════════════════════════════════════════
class VisualBibleEntry(BaseModel):
    name: str = Field(description="Nom du personnage principal, lieu ou objet clé.")
    description: str = Field(
        description="Description physique ou atmosphérique complète en anglais pour assurer la cohérence visuelle."
    )


class Scene(BaseModel):
    id: int = Field(description="Numéro de la scène (de 1 à 10)")
    audio_tts: str = Field(
        description="Texte exact lu par la voix-off en français, de 18 à 25 mots maximum. Phrases courtes, pas de métaphore."
    )
    subtitle: str = Field(description="Sous-titre, identique mot-pour-mot à audio_tts.")
    veo_prompt: str = Field(
        description="Description physique précise de l'action de l'image en anglais. Sujet centré, pas de gore. Finit obligatoirement par le STYLE LOCK."
    )
    lyria_prompt: str = Field(
        description="Description d'ambiance sonore/foley en anglais. Finit obligatoirement par ', no melody, no music'."
    )
    real_media_queries: List[str] = Field(
        description="""2 requêtes précises en anglais pour trouver des photos ou vidéos réelles d'archives de cette affaire historique spécifique.
RÈGLES IMPÉRATIVES pour real_media_queries :
- Chaque requête DOIT inclure le nom propre de l'affaire (ex: 'Enfield Poltergeist 1977', 'Janet Hodgson SPR investigation').
- Préférer les termes documentaires : 'archival photo', 'historical photograph', 'real photo', 'documentary evidence', 'investigation photo'.
- INTERDICTION ABSOLUE des termes génériques non liés à l'affaire : pas de 'ghost', 'haunted house', 'scary', 'dark room' sans le nom de l'affaire.
- Viser des sources de qualité : Wikipedia, BBC, news archives, police records, SPR archives.
- Ex valides : 'Janet Hodgson Enfield poltergeist 1977 real photo', 'Enfield house 284 Green Street historical photograph'.
- Ex INVALIDES : 'dark hallway', 'mysterious ghost', 'scary bedroom'. Ces requêtes génèrent du contenu aléatoire et inapproprié."""
    )


class VideoScript(BaseModel):
    projet: str = Field(
        description="Nom unique sans espace pour le projet (ex: Mystere_Dyatlov_Oural)."
    )
    niche: str = Field(description="Le sujet exact de la vidéo.")
    visual_bible: List[VisualBibleEntry] = Field(
        description="Liste d'apparence des personnages, lieux et objets clés."
    )
    scenes: List[Scene] = Field(
        description="Les 10 scènes du documentaire ordonnées chronologiquement."
    )


# ═══════════════════════════════════════════════════════════
#  MEGA-PROMPT SYSTEME
# ═══════════════════════════════════════════════════════════
MEGA_PROMPT_SYSTEM = """Tu es le Showrunner de « Les Archives de Minuit », une série documentaire paranormale verticale.
Tu racontes uniquement des événements documentés : fantômes, maisons hantées, monstres rapportés, lieux inexpliqués et disparitions à dimension paranormale.
Ta signature est calme, précise et terrifiante. Tu parles comme si tu ouvrais un dossier qui n'aurait jamais dû être rendu public.
La peur vient des faits concrets, du détail impossible et de ce qui reste sans réponse, jamais de cris ni de clichés.
Le spectateur doit comprendre le mystère et ressentir une menace dans les trois premières secondes.

════════════════════════════════════════════
RÈGLE N°1 — BIBLE VISUELLE (cohérence absolue)
════════════════════════════════════════════
Définis UNE FOIS l'apparence physique de chaque personnage et lieu clé en anglais dans 'visual_bible'.
Utilise EXACTEMENT la même description dans chaque 'veo_prompt' où ils apparaissent.
JAMAIS de changement de vêtements ou de traits entre les scènes.

════════════════════════════════════════════
RÈGLE N°2 — STYLE VISUEL & FORMAT VERTICAL 9:16
════════════════════════════════════════════
Chaque 'veo_prompt' décrit UNE SEULE ACTION physique précise (pas une ambiance).
Ex : "A man's trembling hands turn the dial of a vintage shortwave radio, close-up shot"
Ajoute toujours un mouvement de caméra (e.g. Slow dolly zoom in, Low angle push, Extreme close-up rack focus).

Chaque 'veo_prompt' doit se terminer par le SUFFIXE OBLIGATOIRE exact :
[STYLE LOCK: Premium cinematic 3D low-poly art style, crisp faceted polygon geometry, physically based materials, portrait 9:16, sharp subject detail, harsh chiaroscuro shadows, volumetric fog, cold desaturated blue-gray palette, restrained deep-red accents, paranormal documentary aesthetic]


INTERDICTIONS ABSOLUES dans veo_prompt : aucun panneau, aucun texte visible, aucune date écrite, aucun watermark, aucune interface avec mots lisibles.

PROTOCOLE SÉCURITÉ IMAGE :
- Ne demande jamais de gore, blessures graphiques, torture visible, sang détaillé, cadavre explicite, violence en cours, mineurs en danger ou suicide.
- Si l'histoire contient de la violence, montre l'après-coup neutre : pièce vide, couloir, dossier, photo floue, objet abandonné, porte fermée, enquêteur de dos.
- Évite les mots déclencheurs : "gore", "blood splatter", "torture scene", "dead body close-up", "mutilated", "graphic injury".
- Composition calibrée TikTok : sujet principal bien visible et centré, cadrage vertical (9:16 portrait), espace sombre en bas pour les sous-titres, pas de texte dans l'image.

════════════════════════════════════════════
RÈGLE N°3 — NARRATION & ACCROCHE INVERSÉE (clarté maximale, 14 ans TikTok)
════════════════════════════════════════════
- Pour la SCÈNE 1 (HOOK) : Applique systématiquement l'ACCROCHE INVERSÉE. Extrais le "plot twist" ou le fait le plus choquant/incroyable de l'histoire et place-le dès la première phrase dans les 3 premières secondes (Hook), AVANT d'énoncer le moindre contexte.
- INTERDICTION ABSOLUE de commencer par des éléments de contexte dans la scène 1 : pas de date (ex: pas de "En 1959"), pas de prénom ou de nom propre (ex: pas de "Brian Shaffer"), pas de situation géographique précise. Le spectateur doit être frappé immédiatement par le mystère pur.
  - Correct : "Sa voiture roulait encore sur l'autoroute, mais le conducteur s'était volatilisé de l'habitacle."
  - Incorrect : "En 2006, à Columbus dans l'Ohio, Brian Shaffer disparaît mystérieusement d'un bar."
- Phrases courtes : 6 à 14 mots. Sujet + verbe + fait.
- Une seule info par phrase. Pas de métaphore.
- Mots simples et concrets.
- Noms-clés répétés dans 4-5 scènes pour ancrage mémoire.
- Chiffres en lettres : "deux cents personnes" pas "200".
- 18 à 25 mots par scène, pas plus.
- Après le hook (à partir de la SCÈNE 2), situe le contexte : le protagoniste, la date, le lieu exact et un repère proche ordinaire pour situer l'histoire dans la réalité ("un bar ordinaire", "une rue normale", "un appel banal").
- Le frisson vient du contraste : un lieu réel + un détail impossible.
- Distingue clairement fait vérifié, explication officielle et légende. Ne présente jamais une rumeur comme un fait.
- Termine sur une phrase obsédante, pas sur une demande générique de commentaire.
- Le sous-titre 'subtitle' doit être IDENTIQUE mot-pour-mot à 'audio_tts'.

════════════════════════════════════════════
RÈGLE N°4 — STRUCTURE 10 SCÈNES (ordre chronologique)
════════════════════════════════════════════
SCÈNE 1 — HOOK : Formule de l'Accroche Inversée (fait choquant / plot twist pur, sans date ni nom propre).
SCÈNE 2 — CONTEXTE + QUI/QUAND/OÙ : protagoniste + date + lieu exact + repère proche ordinaire.
SCÈNE 3 — DÉCLENCHEUR : ce qui commence tout.
SCÈNE 4 — CE QU'ILS VIVENT : détails précis et troublants.
SCÈNE 5 — L'ANOMALIE : le détail matériel qui rend l'affaire impossible.
SCÈNE 6 — ESCALADE : une seconde preuve ou conséquence plus inquiétante.
SCÈNE 7 — LE POINT DE BASCULE : disparition, apparition ou découverte.
SCÈNE 8 — EXPLICATION OFFICIELLE : ce qu'elle explique, puis sa limite exacte.
SCÈNE 9 — LA QUESTION IRRÉSOLUE : le fait qui résiste encore.
SCÈNE 10 — TRACE FINALE : une phrase courte et obsédante qui referme le dossier sans CTA générique.
"""


# ═══════════════════════════════════════════════════════════
#  RECHERCHE DYNAMIQUE DE SUJET
# ═══════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════
#  DÉCOUVERTE DE CANDIDATS PAR RECHERCHE PAR MOTS-CLÉS
# ═══════════════════════════════════════════════════════════
def _parse_json_block(text: str) -> Optional[list]:
    """Extrait le premier tableau JSON d'un texte (Gemini ajoute parfois
    des préambules type 'Here are the cases:' avant le JSON)."""
    if not text:
        return None
    text = text.strip()
    # Strip fences markdown
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    # Trouver le premier [ et le matcher avec le dernier ]
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def discover_candidates(
    memory: dict, n_keywords: int = 3, n_per_keyword: int = 4
) -> list[dict]:
    """Étape 1 : recherche Google avec mots-clés variés → liste de candidats.

    Tire {n_keywords} requêtes différentes des templates, chacune renvoie
    jusqu'à {n_per_keyword} cas concrets. On accumule, on dédoublonne contre
    la mémoire, et on retourne tous les candidats restants.
    """
    print(
        f"🔎 Découverte par mots-clés (mémoire : {len(memory['subjects'])} sujets déjà couverts)"
    )
    used_titles = [s.get("title", "") for s in memory["subjects"][-30:]]
    exclusion = "\n".join(f"- {t}" for t in used_titles) if used_titles else "(aucun)"

    all_candidates: list[dict] = []

    queries_drawn = random.sample(
        SEARCH_TEMPLATES, min(n_keywords, len(SEARCH_TEMPLATES))
    )
    for query_tpl in queries_drawn:
        query = _instantiate_template(query_tpl)
        print(f"   🔑 Requête : '{query}'")

        prompt = f"""You are a researcher hunting for OBSCURE but REAL documented paranormal and unexplained cases for the French vertical series "Les Archives de Minuit". The audience has already seen every viral classic.

SEARCH QUERY: {query}

Find {n_per_keyword} DISTINCT real, documented cases — pick cases that are:
- well-documented in at least one reputable source
- NOT viral hits (no Dyatlov, no Roswell, no Enfield, no Bermuda Triangle, no Black Dahlia, no Zodiac, no Mary Celeste, no JonBenét, no MH370, no Madeleine McCann, no Brian Shaffer, no Lars Mittank — these are over-saturated)
- preferably from OUTSIDE the Anglosphere classics — explore Brazil, Argentina, Mexico, Japan, Korea, Indonesia, Russia, Eastern Europe, Africa, French-speaking countries
- can be small-scale (a single village, a single hiker, a single building) — local mysteries are better than global ones
- can be RECENT (post-2010) or OLD (pre-1950)

For each case, return:
- title: short title in French
- year_or_period: precise year(s) or decade
- location: country + city/region
- one_liner: 1 sentence summary in French, with the most arresting concrete fact (a name, a date, a body count, an evidence type)
- source_hint: the kind of source where this is documented (Wikipedia, name of a news outlet, police archive, academic journal…)

CRITICAL RULES:
- ONLY real, documented cases. If you cannot find at least one reputable source, skip it.
- DIVERSE pool — mix documented hauntings, unexplained places, reported creatures, maritime mysteries and paranormal disappearances.
- EXCLUDE ordinary murders and conventional crime cases unless the central mystery is genuinely unexplained or paranormal.
- AVOID THESE ALREADY-COVERED CASES (do not propose any of them, nor close variants):
{exclusion}

Output a valid JSON array. Example:
[
  {{ "title": "...", "year_or_period": "1992", "location": "Bolivia, La Paz", "one_liner": "...", "source_hint": "..." }},
  ...
]
Return ONLY the JSON array. No explanation."""

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    temperature=1.1,
                ),
            )
            parsed = _parse_json_block(response.text or "")
            if not parsed:
                print("      ⚠️ Réponse non parsable")
                continue
            for c in parsed:
                if not isinstance(c, dict):
                    continue
                title = (c.get("title") or "").strip()
                if not title:
                    continue
                kws = _extract_keywords(
                    f"{title} {c.get('location', '')} {c.get('year_or_period', '')}"
                )
                if subject_already_used(kws, memory):
                    continue
                c["_search_query"] = query
                c["_keywords"] = kws
                all_candidates.append(c)
            print(
                f"      ✅ {len([c for c in parsed if isinstance(c, dict)])} candidats"
            )
        except Exception as e:
            print(f"      ⚠️ Erreur de recherche : {e}")
            continue

    # Dédoublonnage interne par titre (cas où deux requêtes ramènent le même)
    seen_titles = set()
    unique = []
    for c in all_candidates:
        sig = re.sub(r"[^a-z0-9]", "", c["title"].lower())[:30]
        if sig in seen_titles:
            continue
        seen_titles.add(sig)
        unique.append(c)

    print(f"   📋 {len(unique)} candidats uniques retenus après filtrage mémoire")
    return unique


# ═══════════════════════════════════════════════════════════
#  RECHERCHE APPROFONDIE — BRIEF FACTUEL VÉRIFIÉ AVEC SOURCES
# ═══════════════════════════════════════════════════════════
class BriefPerson(BaseModel):
    name: str = ""
    role: str = ""


class BriefEvent(BaseModel):
    when: str = ""
    what: str = ""


class BriefSource(BaseModel):
    name: str = ""
    url: str = ""
    reliability: str = "unknown"


# Tous les champs sont optionnels avec des défauts vides. Gemini est inconstant
# avec le `google_search` tool — il peut omettre 1-2 champs même quand on est
# explicite sur le schéma. On préfère un brief partiel mais utilisable qu'un
# rejet total qui nous force à brûler des essais.
class CaseBrief(BaseModel):
    title: str = ""
    year_or_period: str = ""
    location: str = ""
    summary: str = ""
    people: List[BriefPerson] = Field(default_factory=list)
    timeline: List[BriefEvent] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    current_status: str = ""
    sources: List[BriefSource] = Field(default_factory=list)
    uncertainty_flags: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


def deep_research(candidate: dict) -> Optional[CaseBrief]:
    """Étape 2 : produit un brief factuel vérifié avec sources sur le candidat retenu.

    Important : on demande explicitement à Gemini de citer ses sources, de ne
    rien inventer, et de flagger les claims incertains. Le brief est sauvegardé
    avec le projet pour audit ultérieur.
    """
    title = candidate.get("title", "")
    location = candidate.get("location", "")
    year = candidate.get("year_or_period", "")
    print(f"📚 Deep research : '{title}' ({location}, {year})")

    prompt = f"""You are a factual researcher building a verified brief about a real documented case for a serious documentary channel.

CASE TO INVESTIGATE:
- Title: {title}
- Location: {location}
- Year/Period: {year}
- One-liner: {candidate.get("one_liner", "")}

YOUR TASK:
Search Google for this case and build a factual brief in FRENCH that strictly contains only verifiable facts from reputable sources (news outlets, police reports, court records, Wikipedia, academic publications).

ABSOLUTE RULES — read every word:
1. NEVER invent any fact. If you cannot verify a claim from at least one source, do not include it.
2. Cite at least 2 distinct sources. Include real URLs when possible.
3. For any claim that is disputed, theorised, or rests on a single weak source (forum, blog, podcast),
   add it to the `uncertainty_flags` list rather than presenting it as fact.
4. Use only neutral factual French. No dramatization, no speculation, no fictional framing.
5. People's names must be real and spelled correctly.
6. Dates must be as precise as your sources allow. Use 'approx.' when uncertain.
7. If the case turns out to be a hoax, legend or pure fiction, set summary to exactly "HOAX_OR_FICTION".

OUTPUT FORMAT — STRICT JSON, no markdown, no preamble. Use exactly these field names:

{{
  "title": "{title}",
  "year_or_period": "{year}",
  "location": "{location}",
  "summary": "200-300 mots en français, neutre, faits vérifiés uniquement.",
  "people": [
    {{ "name": "Nom complet", "role": "victime|témoin|enquêteur|suspect|membre famille" }}
  ],
  "timeline": [
    {{ "when": "1977-08-30 ou 'fin août 1977'", "what": "Événement factuel concret." }}
  ],
  "evidence": [
    "Preuve 1 (description française neutre)",
    "Preuve 2"
  ],
  "current_status": "non résolu | résolu | partiellement expliqué | cold case",
  "sources": [
    {{ "name": "BBC News, article du 12 janvier 2018", "url": "https://www.bbc.com/...", "reliability": "reputable_media" }},
    {{ "name": "Wikipédia FR: Affaire X", "url": "https://fr.wikipedia.org/...", "reliability": "wikipedia" }}
  ],
  "uncertainty_flags": [
    "Le témoignage de X est contesté par...",
    "Aucune source officielle ne confirme..."
  ],
  "keywords": ["nom1", "lieu1", "année", "objet_clé"]
}}

Return ONLY the JSON object. Every field above must be present. Use empty arrays [] for sections with no content."""

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    temperature=0.3,
                ),
            )
            raw = response.text or ""
            # Le tool google_search renvoie souvent un texte qui contient le JSON.
            # On extrait le bloc { ... }
            raw = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE
            )
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                print(f"      ⚠️ Pas de JSON dans la réponse (essai {attempt + 1})")
                continue
            data = json.loads(raw[start : end + 1])
            # Fallback : Gemini omet parfois title/year/location alors qu'ils
            # étaient déjà dans le candidat. On les remplit pour éviter le rejet.
            data.setdefault("title", title)
            data.setdefault("year_or_period", year)
            data.setdefault("location", location)
            # Validation Pydantic — schéma tout-optionnel, donc ne lève qu'en
            # cas de types incompatibles (jamais juste pour un champ manquant).
            brief = CaseBrief(**data)
            # Garde-fou : si Gemini signale "HOAX_OR_FICTION", on rejette.
            if "HOAX_OR_FICTION" in brief.summary:
                print("      🚫 Cas rejeté : hoax / fiction selon la recherche")
                return None
            # Vérifs qualité : un brief sans aucune source ou trop court n'est pas fiable.
            if len(brief.sources) < 2:
                print(
                    f"      ⚠️ Seulement {len(brief.sources)} source(s) — brief insuffisamment sourcé"
                )
                if attempt == 0:
                    continue
            if len(brief.summary) < 80:
                print(
                    f"      ⚠️ Résumé trop court ({len(brief.summary)} car.) — brief incomplet"
                )
                if attempt == 0:
                    continue
            print(
                f"      ✅ Brief vérifié : {len(brief.timeline)} événements, {len(brief.people)} personnes, "
                f"{len(brief.sources)} sources, {len(brief.uncertainty_flags)} flags d'incertitude"
            )
            return brief
        except Exception as e:
            print(
                f"      ⚠️ Erreur deep research (essai {attempt + 1}) : {str(e)[:120]}"
            )
            time.sleep(2)
    return None


# ═══════════════════════════════════════════════════════════
#  GÉNÉRATION DU SCRIPT
# ═══════════════════════════════════════════════════════════
def generer_script(niche: str, brief: Optional[CaseBrief] = None) -> dict:
    """Appelle Gemini avec le Mega-Prompt et retourne le dictionnaire du script.

    Si `brief` est fourni, le script s'ancre dessus : aucune invention,
    chaque scène utilise les noms/dates/lieux/preuves du brief. Les claims
    incertains (uncertainty_flags) sont présentés avec des hedges
    ("selon des témoins", "il aurait été", "des chercheurs avancent").
    """
    # Construction du bloc de faits depuis le brief, transmis tel quel
    # au Mega-Prompt — c'est la source unique de vérité pour la génération.
    brief_block = ""
    if brief is not None:
        people_lines = "\n".join(f"  - {p.name} ({p.role})" for p in brief.people)
        timeline_lines = "\n".join(f"  - {e.when} : {e.what}" for e in brief.timeline)
        evidence_lines = "\n".join(f"  - {ev}" for ev in brief.evidence)
        sources_lines = "\n".join(
            f"  - {s.name} [{s.reliability}] {s.url}" for s in brief.sources
        )
        uncert_lines = (
            "\n".join(f"  - {u}" for u in brief.uncertainty_flags)
            if brief.uncertainty_flags
            else "  (aucun — tout est bien sourcé)"
        )

        brief_block = f"""

═══════════ BRIEF FACTUEL (SOURCE DE VÉRITÉ — N'INVENTE RIEN AU-DELÀ) ═══════════
Titre : {brief.title}
Période : {brief.year_or_period}
Lieu : {brief.location}
Statut actuel : {brief.current_status}

Résumé factuel :
{brief.summary}

Personnes impliquées :
{people_lines}

Chronologie :
{timeline_lines}

Preuves vérifiées :
{evidence_lines}

Sources :
{sources_lines}

Claims INCERTAINS — à mentionner avec prudence ("selon", "il aurait", "des témoins affirment") :
{uncert_lines}
═══════════════════════════════════════════════════════════════════════════════

RÈGLES ANCRAGE FACTUEL :
- Utilise UNIQUEMENT des faits, noms, dates et lieux du brief ci-dessus.
- Si un détail manque dans le brief, NE L'INVENTE PAS — formule autour.
- Les claims incertains DOIVENT être présentés avec hedges : "selon les témoins",
  "il aurait", "des enquêteurs avancent", "certains rapports suggèrent".
- Aucune fabulation de prénom, date, adresse, témoignage non présent dans le brief.
"""

    prompt_utilisateur = (
        f"Génère un épisode de « Les Archives de Minuit » en 10 scènes sur le sujet suivant :\n\n"
        f"{niche}\n"
        f"{brief_block}\n"
        f"RAPPEL CRITIQUE :\n"
        f"- Scène 1 (Hook) : DOIT utiliser l'Accroche Inversée. Commence directement par le fait le plus choquant ou le plot twist, sans prénom, sans date, sans contexte géographique.\n"
        f"- Scène 2 : Donne le contexte (prénom, date, lieu) — depuis le brief.\n"
        f"- Escalade de la tension à chaque scène, en suivant la chronologie du brief.\n"
        f"- Chaque veo_prompt DOIT se terminer par le STYLE LOCK exact.\n"
        f"- Pas de texte visible dans l'image, pas de gore.\n"
        f"- Chaque lyria_prompt doit se terminer par ', no melody, no music'."
    )

    STYLE_LOCK = (
        "[STYLE LOCK: Premium cinematic 3D low-poly art style, crisp faceted polygon geometry, "
        "physically based materials, portrait 9:16, sharp subject detail, harsh chiaroscuro shadows, "
        "volumetric fog, cold desaturated blue-gray palette, restrained deep-red accents, paranormal documentary aesthetic]"
    )

    for attempt in range(3):
        try:
            print(f"   🧠 Gemini génère le script structuré (Essai {attempt + 1}/3)...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_utilisateur,
                config=types.GenerateContentConfig(
                    system_instruction=MEGA_PROMPT_SYSTEM,
                    temperature=0.85,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                    response_schema=VideoScript,
                ),
            )

            script_data = json.loads(response.text)

            # Conversion de visual_bible de List[VisualBibleEntry] en Dict[str, str] pour compatibilité
            visual_bible_list = script_data.get("visual_bible", [])
            visual_bible_dict = {}
            if isinstance(visual_bible_list, list):
                for entry in visual_bible_list:
                    if isinstance(entry, dict):
                        name = entry.get("name")
                        desc = entry.get("description")
                        if name and desc:
                            visual_bible_dict[name] = desc
            elif isinstance(visual_bible_list, dict):
                visual_bible_dict = visual_bible_list
            script_data["visual_bible"] = visual_bible_dict
            script_data["channel_identity"] = "Les Archives de Minuit"
            script_data["visual_style"] = "low_poly_3d"
            script_data["narrateur_genre"] = "masculin"

            # Post-traitement de sécurité et formatage
            for scene in script_data.get("scenes", []):
                # Forcer la présence du STYLE LOCK
                veo = scene.get("veo_prompt", "").strip()
                if veo:
                    if "[STYLE LOCK" not in veo:
                        scene["veo_prompt"] = f"{veo} {STYLE_LOCK}"
                else:
                    scene["veo_prompt"] = (
                        f"Dark portrait cinematic reconstruction. Slow dolly zoom in. {STYLE_LOCK}"
                    )

                # Forcer le format sonore Lyria
                lyria = scene.get("lyria_prompt", "").strip()
                if not lyria:
                    scene["lyria_prompt"] = (
                        "Low ominous sub-bass drone, creaking silence, no melody, no music"
                    )
                elif not lyria.endswith(", no melody, no music"):
                    scene["lyria_prompt"] = f"{lyria.rstrip(',.')}, no melody, no music"

            return script_data
        except Exception as e:
            print(f"   ⚠️ Erreur génération/parsing (essai {attempt + 1}) : {e}")
            time.sleep(3)
    return None


# ═══════════════════════════════════════════════════════════
#  CRÉATION DU DOSSIER PROJET
# ═══════════════════════════════════════════════════════════
def creer_projet(niche: str = None) -> str:
    """Orchestre la génération et la sauvegarde du script.json.

    Nouveau flow :
      1. Charge la mémoire des sujets déjà traités.
      2. Découvre des candidats par recherche par mots-clés (3 requêtes × 4 cas).
      3. Pour le candidat retenu, deep research → brief factuel vérifié avec sources.
      4. Génère le script ancré sur le brief (aucune invention).
      5. Sauvegarde brief.json + met à jour la mémoire.

    Si `niche` est passé en argument (override manuel), on saute la découverte
    mais on tente quand même un deep research dessus.
    """
    memory = load_subject_memory()
    chosen_candidate: Optional[dict] = None
    brief: Optional[CaseBrief] = None

    if niche:
        # Override manuel : on construit un candidat minimal et on deep-research.
        print(f"📌 Niche fournie manuellement : {niche}")
        chosen_candidate = {
            "title": niche,
            "year_or_period": "",
            "location": "",
            "one_liner": niche,
        }
    else:
        # Découverte automatique
        candidates = discover_candidates(memory)
        if not candidates:
            # Fallback : random parmi NICHES_HORREUR jamais utilisées
            print(
                "   ⚠️ Aucun candidat trouvé via recherche, fallback sur banque locale"
            )
            available = [
                n
                for n in NICHES_HORREUR
                if not subject_already_used(_extract_keywords(n), memory)
            ]
            if not available:
                available = NICHES_HORREUR
            niche = random.choice(available)
            chosen_candidate = {
                "title": niche,
                "year_or_period": "",
                "location": "",
                "one_liner": niche,
            }
        else:
            # On essaie chaque candidat dans l'ordre jusqu'à un deep research réussi.
            for cand in candidates:
                print(
                    f"\n🎯 Candidat tenté : {cand['title']} ({cand.get('location', '?')}, {cand.get('year_or_period', '?')})"
                )
                b = deep_research(cand)
                if b is not None:
                    chosen_candidate = cand
                    brief = b
                    niche = b.title  # canonical title from the verified brief
                    break
                else:
                    print("      ↪️  Cas non vérifié, on passe au suivant")

            if brief is None:
                # Tous les deep research ont échoué : fallback ultime
                print("   ⚠️ Aucun candidat vérifiable, fallback sur banque locale")
                available = [
                    n
                    for n in NICHES_HORREUR
                    if not subject_already_used(_extract_keywords(n), memory)
                ]
                if not available:
                    available = NICHES_HORREUR
                niche = random.choice(available)
                chosen_candidate = {"title": niche}

    # Si la niche a été passée manuellement, on tente quand même un deep research.
    if brief is None and chosen_candidate:
        brief = deep_research(chosen_candidate)
        if brief is None:
            print(
                "   ⚠️ Deep research échouée — script sera généré sans brief (mode dégradé)"
            )

    # Nettoyage du nom de projet
    mots = re.sub(r"[^\w\s]", "", niche).split()[:5]
    nom_base = "_".join(w.capitalize() for w in mots)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_projet = f"{timestamp}_{nom_base}"
    dossier = f"projets/{nom_projet}"

    os.makedirs(dossier, exist_ok=True)
    os.makedirs(f"{dossier}/audio", exist_ok=True)
    os.makedirs(f"{dossier}/audio/sfx", exist_ok=True)

    print(f"\n{'═' * 55}")
    print(f"  🎬 NOUVEAU PROJET : {nom_projet}")
    print(f"{'═' * 55}")
    print(f"  📖 Sujet : {niche[:80]}...")

    # Sauvegarde du brief (audit + traçabilité) AVANT la génération.
    # Le brief est la source de vérité que la génération va consommer ;
    # on le persiste pour pouvoir auditer ce que Gemini a vu.
    if brief is not None:
        with open(f"{dossier}/brief.json", "w", encoding="utf-8") as f:
            json.dump(brief.model_dump(), f, indent=2, ensure_ascii=False)
        print(
            f"  📋 Brief sauvegardé ({len(brief.sources)} sources, "
            f"{len(brief.uncertainty_flags)} flags) → {dossier}/brief.json"
        )

    script_data = generer_script(niche, brief=brief)
    if not script_data:
        print("❌ Échec de la génération du script.")
        return None

    # Sauvegarde brute
    with open(f"{dossier}/script_brut.txt", "w", encoding="utf-8") as f:
        f.write(json.dumps(script_data, indent=4, ensure_ascii=False))

    scenes = script_data.get("scenes", [])
    print(f"   ✅ {len(scenes)} scènes générées avec succès.")

    for s in scenes:
        veo_ok = bool(s.get("veo_prompt"))
        lyria_ok = "no melody" in s.get("lyria_prompt", "").lower()
        audio_ok = bool(s.get("audio_tts"))
        status = "✅" if (veo_ok and lyria_ok and audio_ok) else "⚠️"
        print(
            f"   {status} Scène {s.get('id')} — VEO: {'✓' if veo_ok else '✗'} | LYRIA: {'✓' if lyria_ok else '✗'} | TTS: {'✓' if audio_ok else '✗'}"
        )

    # Aliases de compatibilité ascendante pour les autres scripts du pipeline
    for s in scenes:
        s["voix_off_tts"] = s.get("audio_tts", "")
        s["sous_titre"] = s.get("subtitle", "")
        s["lyria_type"] = "foley_ambiance"

    # Sauvegarde finale
    with open(f"{dossier}/script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=4, ensure_ascii=False)

    # Mise à jour de la mémoire des sujets traités (déduplication future).
    # On stocke le brief résumé pour pouvoir le ressortir / l'auditer plus tard.
    entry = {
        "project_id": nom_projet,
        "title": niche,
        "keywords": (brief.keywords if brief else _extract_keywords(niche)),
        "year_or_period": (brief.year_or_period if brief else ""),
        "location": (brief.location if brief else ""),
        "current_status": (brief.current_status if brief else ""),
        "n_sources": (len(brief.sources) if brief else 0),
        "uncertainty_count": (len(brief.uncertainty_flags) if brief else 0),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    memory["subjects"].append(entry)
    save_subject_memory(memory)
    print(f"  🧠 Mémoire mise à jour : {len(memory['subjects'])} sujets enregistrés")

    print(f"\n✅ script.json sauvegardé → {dossier}/script.json")
    print(f"📁 Projet : {dossier}")
    return dossier


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--sujet", help="Sujet précis (sinon recherche en ligne ou random)")
    args = ap.parse_args()
    creer_projet(args.sujet)
