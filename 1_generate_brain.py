"""Cerveau true crime / faits divers : choisit une affaire, la documente, écrit le script.

1. Découverte d'affaires réelles via Gemini + recherche Google (ou sujet imposé).
2. Brief factuel sourcé (au moins 2 sources, statut judiciaire, rôles des personnes).
3. Script en 10 scènes ancré sur le brief, contrôlé par usine.garde_fous
   (présomption d'innocence, aucun mineur nommé).
4. Projet créé avec le statut « a_valider » : 0_usine.py le soumet à validation
   humaine avant tout rendu.

Usage : python 1_generate_brain.py [--sujet "L'affaire …"]
"""

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

from usine.garde_fous import (
    brief_suffisant,
    nettoyer_requetes,
    personnes_a_taire,
    verifier_script,
)
from usine.projet import A_VALIDER

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
#  BANQUE DE MOTS-CLÉS DE RECHERCHE — TRUE CRIME & FAITS DIVERS
#  Mots-clés LARGES, en français et en anglais. On laisse Google +
#  Gemini trouver la longue traîne plutôt que de retomber sur les
#  classiques saturés (Zodiac, Dahlia noir, Grégory…).
# ═══════════════════════════════════════════════════════════
SEARCH_TEMPLATES = [
    # Faits divers français et francophones
    "fait divers criminel non élucidé France",
    "affaire criminelle jugée cour d'assises",
    "disparition inquiétante jamais résolue gendarmerie",
    "cold case rouvert pôle crimes sériels Nanterre",
    "affaire criminelle historique France XIXe siècle",
    "enquête criminelle résolue grâce à l'ADN France",
    "fait divers étrange village français enquête",
    "affaire criminelle Belgique Suisse Québec procès",
    "casse célèbre France enquête police",
    "escroquerie célèbre procès France",
    # True crime international
    "solved cold case DNA genealogy conviction",
    "unsolved murder case police investigation",
    "famous heist investigation trial",
    "historical criminal case trial archives",
    "unsolved disappearance police case",
    "true crime case Japan Korea court ruling",
    "true crime case Latin America investigation trial",
    "forensic breakthrough solved murder case",
]


def _instantiate_template(tpl: str) -> str:
    """Renvoie le template tel quel (plus de slots à remplir — gardé pour
    rester compatible avec discover_candidates qui appelle cette fonction)."""
    return tpl


# ═══════════════════════════════════════════════════════════
#  AFFAIRES DE SECOURS
#  Affaires réelles, documentées, jugées définitivement ou jamais
#  élucidées sans mis en cause nommé. Le pipeline n'y pioche que si la
#  recherche en ligne échoue, en évitant les sujets déjà traités.
# ═══════════════════════════════════════════════════════════
AFFAIRES_SECOURS = [
    # France
    "L'affaire Landru, le « Barbe-Bleue de Gambais », condamné en 1921.",
    "L'affaire Seznec et la disparition du conseiller Pierre Quéméneur en 1923.",
    "Le casse de la Société générale de Nice en 1976, le « casse du siècle ».",
    "La bande à Bonnot et la première attaque à l'automobile en 1911.",
    "L'affaire du Courrier de Lyon, l'attaque de la malle-poste en 1796.",
    "L'affaire Guy Georges, le tueur de l'Est parisien condamné en 2001.",
    "Les disparues de l'Yonne et la condamnation d'Émile Louis en 2004.",
    "La tuerie de Chevaline en 2012, jamais élucidée.",
    "Le vol de la Joconde au Louvre en 1911.",
    "Le gang des postiches et ses braquages de banques parisiennes dans les années 1980.",
    # International
    "Le Golden State Killer, identifié par la généalogie ADN et condamné en 2020.",
    "Le casse du centre diamantaire d'Anvers en 2003.",
    "Les empoisonnements au Tylenol à Chicago en 1982, jamais élucidés.",
    "Le massacre de la ferme d'Hinterkaifeck en Bavière en 1922, jamais résolu.",
    "Les meurtres du Texarkana Moonlight en 1946, jamais résolus.",
    "Le tueur de la Green River, condamné en 2003 après vingt ans d'enquête.",
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
- Chaque requête DOIT inclure le nom de l'affaire ou du lieu (ex: 'Landru trial 1921', 'Gambais villa Landru').
- Préférer les termes documentaires : 'archival photo', 'historical photograph', 'press photo', 'trial photo', 'crime scene location'.
- JAMAIS le nom d'un mineur ni d'une personne non condamnée définitivement : vise le lieu, le procès, l'objet ou l'enquête.
- INTERDICTION ABSOLUE des termes génériques non liés à l'affaire : pas de 'crime', 'murder', 'dark room' seuls.
- Viser des sources de qualité : Wikipedia, presse, archives judiciaires et policières.
- Ex valides : 'Landru trial Versailles 1921 press photo', 'Gambais villa Landru historical photograph'.
- Ex INVALIDES : 'dark hallway', 'murder scene', 'scary bedroom'. Ces requêtes génèrent du contenu aléatoire et inapproprié."""
    )


class VideoScript(BaseModel):
    projet: str = Field(
        description="Nom unique sans espace pour le projet (ex: Affaire_Landru_Gambais)."
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
STYLE_LOCK = (
    "[STYLE LOCK: Premium cinematic 3D low-poly art style, crisp faceted polygon geometry, "
    "physically based materials, portrait 9:16, sharp subject detail, harsh chiaroscuro shadows, "
    "volumetric fog, cold desaturated blue-gray palette, restrained deep-red accents, "
    "true crime documentary aesthetic]"
)

MEGA_PROMPT_SYSTEM = """Tu es le Showrunner de « Les Archives de Minuit », une chaîne documentaire verticale de true crime et de faits divers.
Tu racontes uniquement des affaires criminelles réelles et documentées : crimes, disparitions, enquêtes, procès, casses et escroqueries.
Ta signature est calme, précise et glaçante. Tu parles comme si tu ouvrais un dossier d'enquête.
La tension vient des faits concrets, du détail qui ne colle pas et de ce qui reste sans réponse, jamais de cris ni de clichés.
Le spectateur doit comprendre l'enjeu de l'affaire dans les trois premières secondes.

════════════════════════════════════════════
RÈGLE N°0 — CADRE JURIDIQUE (prioritaire sur toutes les autres)
════════════════════════════════════════════
- PRÉSOMPTION D'INNOCENCE : une personne n'est « coupable », « le meurtrier » ou « l'assassin » que si elle a été CONDAMNÉE DÉFINITIVEMENT. Sinon : « soupçonné », « mis en examen », « accusé », « jamais jugé ».
- Ne nomme JAMAIS une personne soupçonnée, mise en examen, acquittée, relaxée ou bénéficiaire d'un non-lieu : dis « un suspect », « un homme de 40 ans », « le principal suspect ».
- Ne nomme JAMAIS un mineur (victime, témoin ou auteur), ni par son nom ni par son prénom : « une fillette de huit ans », « un adolescent ».
- Les personnes à ne pas nommer sont listées dans le brief : respecte cette liste à la lettre.
- Dignité des victimes : aucun détail dégradant, aucune description de souffrance, aucune spéculation sur leur vie privée.
- Distingue toujours ce qui est jugé, ce qui est allégué et ce qui est une hypothèse. Une rumeur n'est jamais présentée comme un fait.
- Si l'affaire n'est pas jugée, dis-le explicitement dans le script.

════════════════════════════════════════════
RÈGLE N°1 — BIBLE VISUELLE (cohérence absolue)
════════════════════════════════════════════
Définis UNE FOIS l'apparence physique de chaque personnage et lieu clé en anglais dans 'visual_bible'.
Utilise EXACTEMENT la même description dans chaque 'veo_prompt' où ils apparaissent.
JAMAIS de changement de vêtements ou de traits entre les scènes.
Aucun visage reconnaissable d'une personne réelle : silhouette, mains, nuque, personnage de dos.

════════════════════════════════════════════
RÈGLE N°2 — STYLE VISUEL & FORMAT VERTICAL 9:16
════════════════════════════════════════════
Chaque 'veo_prompt' décrit UNE SEULE ACTION physique précise (pas une ambiance).
Ex : "A detective's gloved hand slides an old case file across a wooden desk, close-up shot"
Ajoute toujours un mouvement de caméra (e.g. Slow dolly zoom in, Low angle push, Extreme close-up rack focus).

Chaque 'veo_prompt' doit se terminer par le SUFFIXE OBLIGATOIRE exact :
@@STYLE_LOCK@@

INTERDICTIONS ABSOLUES dans veo_prompt : aucun panneau, aucun texte visible, aucune date écrite, aucun watermark, aucune interface avec mots lisibles.

PROTOCOLE SÉCURITÉ IMAGE :
- Ne demande jamais de gore, blessures graphiques, torture visible, sang détaillé, cadavre explicite, violence en cours, mineurs en danger ou suicide.
- Montre l'après-coup neutre : pièce vide, ruban de police, couloir, dossier, objet abandonné, porte fermée, enquêteur de dos, salle d'audience.
- Évite les mots déclencheurs : "gore", "blood splatter", "torture scene", "dead body close-up", "mutilated", "graphic injury".
- Composition calibrée TikTok : sujet principal bien visible et centré, cadrage vertical (9:16 portrait), espace sombre en bas pour les sous-titres, pas de texte dans l'image.

════════════════════════════════════════════
RÈGLE N°3 — NARRATION & ACCROCHE INVERSÉE (clarté maximale, 14 ans TikTok)
════════════════════════════════════════════
- SCÈNE 1 (HOOK) : ACCROCHE INVERSÉE. Le fait le plus saisissant de l'affaire dès la première phrase, AVANT tout contexte.
- Interdit dans la scène 1 : date, nom propre, lieu précis.
  - Correct : "Pendant deux ans, il a envoyé des lettres à la police. Personne n'a jamais su qui les écrivait."
  - Incorrect : "En 1969, à San Francisco, un tueur envoie des lettres à la presse."
- Phrases courtes : 6 à 14 mots. Sujet + verbe + fait. Une seule info par phrase. Pas de métaphore.
- Mots simples et concrets. Chiffres en lettres : "deux cents personnes" pas "200".
- 18 à 25 mots par scène, pas plus.
- À partir de la SCÈNE 2 : contexte (date, lieu exact, repère ordinaire) — en respectant la RÈGLE N°0 pour les noms.
- Le frisson vient du contraste : un lieu ordinaire + un détail qui ne colle pas.
- Termine sur une phrase obsédante, pas sur une demande générique de commentaire.
- Le sous-titre 'subtitle' doit être IDENTIQUE mot-pour-mot à 'audio_tts'.

════════════════════════════════════════════
RÈGLE N°4 — STRUCTURE 10 SCÈNES (ordre chronologique)
════════════════════════════════════════════
SCÈNE 1 — HOOK : accroche inversée (fait saisissant, sans date ni nom propre).
SCÈNE 2 — CONTEXTE : quand, où, qui (dans le respect de la RÈGLE N°0).
SCÈNE 3 — LES FAITS : ce qui se passe, ce qu'on découvre.
SCÈNE 4 — L'ENQUÊTE DÉMARRE : premiers constats, premières pistes.
SCÈNE 5 — L'INDICE : le détail matériel qui change tout.
SCÈNE 6 — LA PISTE : suspect, mobile ou fausse piste (sans nom si non condamné).
SCÈNE 7 — LA BASCULE : arrestation, aveu, découverte ou impasse.
SCÈNE 8 — LA JUSTICE : verdict et peine, ou absence de procès — formulé avec exactitude.
SCÈNE 9 — CE QUI RESTE SANS RÉPONSE : le fait qui résiste encore.
SCÈNE 10 — TRACE FINALE : une phrase courte et obsédante qui referme le dossier, sans CTA générique.
""".replace("@@STYLE_LOCK@@", STYLE_LOCK)


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

        prompt = f"""You are a researcher hunting for REAL, DOCUMENTED true crime cases and French "faits divers" for the French vertical channel "Les Archives de Minuit". The audience has already seen every viral classic.

SEARCH QUERY: {query}

Find {n_per_keyword} DISTINCT real criminal cases — pick cases that are:
- documented in reputable sources (national or regional press, court records, police communications, Wikipedia)
- legally safe to tell: either JUDGED with a FINAL conviction, or HISTORICAL (more than 20 years old), or officially UNSOLVED with no publicly named suspect
- NOT viral hits (no Zodiac, no Black Dahlia, no Jack the Ripper, no Ted Bundy, no JonBenét, no Madeleine McCann, no Grégory Villemin, no Dupont de Ligonnès — over-saturated)
- a mix of French and francophone "faits divers" (France, Belgium, Switzerland, Quebec) and international true crime
- can be small-scale (a single village, a single family, a single heist) — local cases are better than global ones

For each case, return:
- title: short title in French (case name or place, never the name of a minor or of an unconvicted suspect)
- year_or_period: precise year(s) or decade
- location: country + city/region
- legal_status: final conviction | judged, appeal pending | under investigation | unsolved | acquittal
- one_liner: 1 sentence summary in French, with the most arresting concrete fact
- source_hint: the kind of source where this is documented

CRITICAL RULES:
- ONLY real, documented criminal cases. If you cannot find at least one reputable source, skip it.
- EXCLUDE paranormal, ghosts, cryptids, UFOs and legends.
- EXCLUDE ongoing investigations with a publicly named suspect who has not been convicted.
- AVOID THESE ALREADY-COVERED CASES (do not propose any of them, nor close variants):
{exclusion}

Output a valid JSON array. Example:
[
  {{ "title": "...", "year_or_period": "1992", "location": "France, Lyon", "legal_status": "final conviction", "one_liner": "...", "source_hint": "..." }},
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
    mineur: bool = False


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
    statut_judiciaire: str = ""
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

    prompt = f"""You are a factual researcher building a verified brief about a real criminal case (true crime / French \"fait divers\") for a serious documentary channel.

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
8. Set `statut_judiciaire` precisely, in French: "condamnation définitive", "jugé en première instance, appel en cours",
   "instruction en cours", "non élucidé" or "acquittement / non-lieu". Check the most recent court decision.
9. For each person, `role` must be precise, in French: victime, témoin, enquêteur, magistrat, suspect, mis en examen,
   condamné, acquitté, membre de la famille. Set `mineur` to true if the person was under 18 at the time of the events.
10. For French cases, prefer French sources (Le Monde, Le Parisien, Ouest-France, franceinfo, AFP, regional press).

OUTPUT FORMAT — STRICT JSON, no markdown, no preamble. Use exactly these field names:

{{
  "title": "{title}",
  "year_or_period": "{year}",
  "location": "{location}",
  "summary": "200-300 mots en français, neutre, faits vérifiés uniquement.",
  "people": [
    {{ "name": "Nom complet", "role": "victime|témoin|enquêteur|suspect|mis en examen|condamné|acquitté|membre famille", "mineur": false }}
  ],
  "timeline": [
    {{ "when": "1977-08-30 ou 'fin août 1977'", "what": "Événement factuel concret." }}
  ],
  "evidence": [
    "Preuve 1 (description française neutre)",
    "Preuve 2"
  ],
  "current_status": "non résolu | résolu | partiellement expliqué | cold case",
  "statut_judiciaire": "condamnation définitive | jugé en première instance, appel en cours | instruction en cours | non élucidé | acquittement / non-lieu",
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
            # Un brief non sourcé ou trop maigre n'est jamais utilisé : pas de script
            # sur de vraies personnes sans faits vérifiables.
            ok, raison = brief_suffisant(brief.model_dump())
            if "HOAX_OR_FICTION" in brief.summary:
                print("      🚫 Cas rejeté : hoax / fiction selon la recherche")
                return None
            if not ok:
                print(f"      ⚠️ Brief insuffisant : {raison}")
                continue
            print(
                f"      ✅ Brief vérifié : {len(brief.timeline)} événements, {len(brief.people)} personnes, "
                f"{len(brief.sources)} sources, {len(brief.uncertainty_flags)} flags d'incertitude, "
                f"statut judiciaire : {brief.statut_judiciaire or '?'}"
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
def generer_script(niche: str, brief: CaseBrief) -> Optional[dict]:
    """Appelle Gemini avec le Mega-Prompt et retourne le dictionnaire du script.

    Le script s'ancre sur le `brief` (obligatoire) : aucune invention, chaque
    scène utilise les noms/dates/lieux/preuves du brief, et les claims incertains
    sont présentés avec prudence. Les garde-fous juridiques (usine.garde_fous)
    sont vérifiés après génération : un script qui nomme un mineur ou une personne
    non condamnée définitivement est régénéré, puis rejeté.
    """
    a_taire = personnes_a_taire(
        [p.model_dump() for p in brief.people], brief.statut_judiciaire
    )
    people_lines = "\n".join(
        f"  - {p.name} ({p.role}{', mineur' if p.mineur else ''})" for p in brief.people
    )
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
    taire_lines = (
        "\n".join(f"  - {p['nom']} ({p['raison']})" for p in a_taire)
        if a_taire
        else "  (aucune)"
    )

    brief_block = f"""

═══════════ BRIEF FACTUEL (SOURCE DE VÉRITÉ — N'INVENTE RIEN AU-DELÀ) ═══════════
Titre : {brief.title}
Période : {brief.year_or_period}
Lieu : {brief.location}
Statut actuel : {brief.current_status}
Statut judiciaire : {brief.statut_judiciaire or "inconnu — reste prudent"}

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

PERSONNES À NE JAMAIS NOMMER (ni nom, ni prénom — RÈGLE N°0) :
{taire_lines}
═══════════════════════════════════════════════════════════════════════════════

RÈGLES ANCRAGE FACTUEL :
- Utilise UNIQUEMENT des faits, noms, dates et lieux du brief ci-dessus.
- Si un détail manque dans le brief, NE L'INVENTE PAS — formule autour.
- Les claims incertains DOIVENT être présentés avec hedges : "selon les témoins",
  "il aurait", "des enquêteurs avancent", "certains rapports suggèrent".
- Aucune fabulation de prénom, date, adresse, témoignage non présent dans le brief.
"""

    consigne_noms = ""
    for attempt in range(3):
        prompt_utilisateur = (
            f"Génère un dossier de « Les Archives de Minuit » en 10 scènes sur l'affaire suivante :\n\n"
            f"{niche}\n"
            f"{brief_block}\n"
            f"RAPPEL CRITIQUE :\n"
            f"- RÈGLE N°0 (cadre juridique) avant tout : présomption d'innocence, aucun mineur nommé.\n"
            f"- Scène 1 (Hook) : accroche inversée, sans nom propre, sans date, sans lieu.\n"
            f"- Scène 2 : le contexte (date, lieu) — depuis le brief.\n"
            f"- Scène 8 : la décision de justice exacte (ou l'absence de procès).\n"
            f"- Chaque veo_prompt DOIT se terminer par le STYLE LOCK exact.\n"
            f"- Pas de texte visible dans l'image, pas de gore.\n"
            f"- Chaque lyria_prompt doit se terminer par ', no melody, no music'."
            f"{consigne_noms}"
        )
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
        except Exception as e:
            print(f"   ⚠️ Erreur génération/parsing (essai {attempt + 1}) : {e}")
            time.sleep(3)
            continue

        violations = verifier_script(script_data, a_taire)
        if violations:
            print("   🚫 Garde-fous juridiques : script rejeté")
            for v in violations:
                print(f"      - {v}")
            noms = ", ".join(sorted({p["nom"] for p in a_taire}))
            consigne_noms = (
                f"\n\nL'ESSAI PRÉCÉDENT A ÉTÉ REJETÉ : il nommait des personnes interdites. "
                f"N'écris JAMAIS ces noms ni ces prénoms : {noms}. "
                f"Désigne-les par leur rôle (« un suspect », « la fillette »)."
            )
            continue

        retirees = nettoyer_requetes(script_data, a_taire)
        if retirees:
            print(
                f"   🛡️ {retirees} requête(s) d'image retirée(s) (personne non nommable)"
            )

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
        script_data["garde_fous"] = {
            "statut_judiciaire": brief.statut_judiciaire,
            "personnes_a_taire": a_taire,
        }
        script_data["validation"] = {"statut": A_VALIDER}

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
    return None


# ═══════════════════════════════════════════════════════════
#  CRÉATION DU DOSSIER PROJET
# ═══════════════════════════════════════════════════════════
def _brief_depuis_secours(memory: dict, essais: int = 3):
    """Deep research sur des affaires de secours jamais traitées, jusqu'à un brief vérifié."""
    disponibles = [
        n
        for n in AFFAIRES_SECOURS
        if not subject_already_used(_extract_keywords(n), memory)
    ] or list(AFFAIRES_SECOURS)
    random.shuffle(disponibles)
    for affaire in disponibles[:essais]:
        print(f"\n🗂️  Affaire de secours tentée : {affaire}")
        brief = deep_research({"title": affaire, "one_liner": affaire})
        if brief is not None:
            return brief
    return None


def creer_projet(niche: str = None) -> Optional[str]:
    """Orchestre la génération et la sauvegarde du script.json.

    Flow :
      1. Charge la mémoire des sujets déjà traités.
      2. Découvre des candidats par recherche par mots-clés (3 requêtes × 4 cas),
         ou prend le sujet imposé (`niche`).
      3. Deep research → brief factuel vérifié avec sources. Sans brief vérifié,
         AUCUN script n'est généré (pas de mode dégradé sur de vraies personnes).
      4. Génère le script ancré sur le brief, contrôlé par les garde-fous juridiques.
      5. Crée le dossier projet (statut « a_valider ») + met à jour la mémoire.

    Retourne le chemin du projet, ou None en cas d'échec.
    """
    memory = load_subject_memory()
    brief: Optional[CaseBrief] = None

    if niche:
        print(f"📌 Sujet imposé : {niche}")
        brief = deep_research({"title": niche, "one_liner": niche})
    else:
        for cand in discover_candidates(memory):
            print(
                f"\n🎯 Candidat tenté : {cand['title']} ({cand.get('location', '?')}, {cand.get('year_or_period', '?')})"
            )
            brief = deep_research(cand)
            if brief is not None:
                break
            print("      ↪️  Cas non vérifié, on passe au suivant")
        if brief is None:
            print("   ⚠️ Aucun candidat vérifiable en ligne, affaires de secours")
            brief = _brief_depuis_secours(memory)

    if brief is None:
        print("❌ Aucun brief vérifié (2 sources minimum) : pas de script généré.")
        return None
    niche = brief.title or niche

    script_data = generer_script(niche, brief)
    if not script_data:
        print("❌ Échec de la génération du script (ou garde-fous non respectés).")
        return None

    # Le dossier n'est créé qu'une fois le script valide : un échec ne laisse
    # pas de projet à moitié vide que l'étape suivante prendrait pour le dernier.
    mots = re.sub(r"[^\w\s]", "", niche).split()[:5]
    nom_base = "_".join(w.capitalize() for w in mots)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_projet = f"{timestamp}_{nom_base}"
    dossier = f"projets/{nom_projet}"
    os.makedirs(f"{dossier}/audio/sfx", exist_ok=True)

    print(f"\n{'═' * 55}")
    print(f"  🎬 NOUVEAU PROJET : {nom_projet}")
    print(f"{'═' * 55}")
    print(f"  📖 Affaire : {niche[:80]}")

    # Brief = source de vérité consommée par la génération : gardé pour audit.
    with open(f"{dossier}/brief.json", "w", encoding="utf-8") as f:
        json.dump(brief.model_dump(), f, indent=2, ensure_ascii=False)
    print(
        f"  📋 Brief sauvegardé ({len(brief.sources)} sources, "
        f"{len(brief.uncertainty_flags)} flags) → {dossier}/brief.json"
    )

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
    entry = {
        "project_id": nom_projet,
        "title": niche,
        "keywords": brief.keywords or _extract_keywords(niche),
        "year_or_period": brief.year_or_period,
        "location": brief.location,
        "current_status": brief.current_status,
        "statut_judiciaire": brief.statut_judiciaire,
        "n_sources": len(brief.sources),
        "uncertainty_count": len(brief.uncertainty_flags),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    memory["subjects"].append(entry)
    save_subject_memory(memory)
    print(f"  🧠 Mémoire mise à jour : {len(memory['subjects'])} sujets enregistrés")

    print(f"\n✅ script.json sauvegardé (à valider) → {dossier}/script.json")
    print(f"📁 Projet : {dossier}")
    return dossier


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--sujet", help="Affaire précise (sinon recherche en ligne)")
    args = ap.parse_args()
    sys.exit(0 if creer_projet(args.sujet) else 1)
