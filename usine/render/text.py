"""Texte des sous-titres : échappement HTML, mots mis en valeur, découpage en chunks."""

import re
import unicodedata
from usine.render.config import USE_CHROMATIC_EMPH


# Mots auto-highlightés en rouge dans les sous-titres
DRAMATIC_KEYWORDS_FR = [
    "trahison",
    "trahi",
    "trahie",
    "trahir",
    "abandonné",
    "abandonnée",
    "quitté",
    "quittée",
    "menti",
    "mensonge",
    "mensonges",
    "jamais",
    "plus rien",
    "tout perdu",
    "erreur",
    "faute",
    "responsable",
    "silence",
    "seul",
    "seule",
    "peur",
    "honte",
    "culpabilité",
    "confiance",
    "aimé",
    "aimée",
    "détruit",
    "détruite",
    "brisé",
    "brisée",
    "regret",
    "regrette",
    "trop tard",
    "réalisé",
    "compris",
    "découvert",
    "aveugle",
    "naïf",
    "naïve",
    "remplacé",
    "remplacée",
    "viré",
    "virée",
    "utilisé",
    "utilisée",
    "manipulé",
    "manipulée",
    "disparu",
    "disparue",
    "disparus",
    "disparues",
    "disparaître",
    "disparition",
    "introuvable",
    "introuvables",
    "vide",
    "personne",
    "impossible",
    "inexpliqué",
    "inexpliquée",
    "ombre",
    "ombres",
    "fantôme",
    "fantômes",
    "hanté",
    "hantée",
    "cri",
    "cris",
    "nuit",
    "tempête",
    "corps",
    "trace",
    "traces",
    "retrouvé",
    "retrouvée",
    "retrouvés",
    "retrouvées",
    "emportés",
    "emportées",
    "urgence",
    "arrêtée",
    "arrêté",
    "vides",
    "tordues",
    "monstrueuse",
    "détaché",
    "détachée",
    "intacte",
    "dame",
    "blanche",
    "route",
    "auto-stoppeuse",
    "pâle",
    "rétroviseur",
    "banquette",
    "volatilisée",
    "morte",
    "accident",
    "effrayant",
    "froid",
    "virage",
    "hurle",
    "freine",
    "gendarmerie",
    "contradiction",
    "explication",
    "llorona",
    "emmurée",
    "mort",
]


def html_escape(s):
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── Phosphor-style icons (inline SVG) ─────────────────────────
ICONS = {
    "lock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="1.5"/><path d="M8 11V7a4 4 0 1 1 8 0v4"/></svg>',
    "warning": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 21h20L12 3z"/><line x1="12" y1="10" x2="12" y2="15"/><circle cx="12" cy="18" r="0.5" fill="currentColor"/></svg>',
    "file": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>',
    "eye": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3" fill="currentColor"/></svg>',
    "radio": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2" fill="currentColor"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49M19.07 4.93a10 10 0 0 1 0 14.14M7.76 16.24a6 6 0 0 1 0-8.49M4.93 19.07a10 10 0 0 1 0-14.14"/></svg>',
}


def emphasize_words(text):
    """Wrap only meaningful dramatic keywords in a red <span>."""
    escaped = html_escape(text)
    emph_class = "emph chromatic" if USE_CHROMATIC_EMPH else "emph"
    # 1. Keywords (case-insensitive, word boundary)
    pattern = r"\b(" + "|".join(re.escape(w) for w in DRAMATIC_KEYWORDS_FR) + r")\b"
    new_text, n = re.subn(
        pattern,
        lambda m: f'<span class="{emph_class}">{m.group(0)}</span>',
        escaped,
        flags=re.IGNORECASE,
    )
    if n > 0:
        return new_text
    return escaped


def red_word_indices(text):
    """Retourne les indices des mots d'un texte qui seront coloriés en rouge."""
    cleaned = re.sub(r"\[.*?\]", "", text).strip()
    words = cleaned.split()
    indices = []
    if not words:
        return indices

    # 1. Chercher les mots clés dramatiques
    for idx, w in enumerate(words):
        w_clean = re.sub(r"[^\w]", "", w).lower()
        if w_clean in DRAMATIC_KEYWORDS_FR:
            indices.append(idx)

    return indices


def _split_by_word_budget(sentence, max_words):
    """Découpe une phrase en sous-chunks de ≤ max_words mots, en cassant
    de préférence sur la ponctuation interne ou les conjonctions."""
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]
    # Points de coupe préférés : virgule, point-virgule, deux-points, tiret long
    break_words = set([",", ";", ":", "—", "–"])
    conjunctions = {
        "mais",
        "et",
        "puis",
        "alors",
        "or",
        "donc",
        "car",
        "parce",
        "lorsque",
        "quand",
        "tandis",
        "pendant",
        "après",
        "avant",
    }
    chunks, current = [], []
    for w in words:
        current.append(w)
        # Coupe naturelle si on dépasse max_words ET on est sur un point de coupe
        if len(current) >= max_words:
            # Tente de couper sur le prochain point naturel proche
            stripped = w.rstrip(",;:—–").lower()
            ends_with_break = any(w.endswith(b) for b in break_words)
            if (
                ends_with_break
                or stripped in conjunctions
                or len(current) >= max_words + 2
            ):
                chunks.append(" ".join(current))
                current = []
    if current:
        chunks.append(" ".join(current))
    # Fusionne tout chunk final < 3 mots avec le précédent (évite "Shaffer?" tout seul)
    if len(chunks) >= 2 and len(chunks[-1].split()) < 3:
        chunks[-2] = chunks[-2] + " " + chunks[-1]
        chunks.pop()
    return chunks


def split_subtitle(text, duration, max_chunks=3, max_words=6):
    """Découpe le texte en chunks de ≤ max_words mots, distribution pondérée.
    Phrase-aware (ponctuation), avec sous-découpe par budget de mots."""
    text = re.sub(r"\[STYLE LOCK[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[.*?\]", "", text).strip()
    text = re.sub(r"\.{2,}", "…", text)
    text = re.sub(r"\s+([,.;!?…])", r"\1", text)
    text = re.sub(r"(?<!\S)\.(?!\S)", "", text)
    # 1. Découpe par phrases
    sentences = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]
    if not sentences:
        sentences = [text]
    # 2. Pour chaque phrase, sous-découpe par budget de mots
    parts = []
    for s in sentences:
        parts.extend(_split_by_word_budget(s, max_words))
    parts = [p.strip() for p in parts if re.search(r"[\wÀ-ÿ]", p)]
    # 3. Si encore trop de chunks, on fusionne par buckets pour respecter max_chunks
    if len(parts) > max_chunks:
        bucket_size = (len(parts) + max_chunks - 1) // max_chunks
        merged = []
        for i in range(0, len(parts), bucket_size):
            merged.append(" ".join(parts[i : i + bucket_size]))
        parts = merged
    if not parts:
        parts = [text]
    # 4. Pondération par nombre de mots (pacing proportionnel à la voix)
    weights = [max(1, len(p.split())) for p in parts]
    total_w = sum(weights)
    chunks, cursor = [], 0.0
    for p, w in zip(parts, weights):
        d = duration * (w / total_w)
        chunks.append({"text": p, "start": cursor, "duration": d})
        cursor += d
    return chunks


def _wrap_words_for_reveal(html, id_prefix=None):
    """Wrap chaque VRAI mot dans <span class='word'> (avec un id séquentiel
    optionnel pour le sync Whisper). Les tokens décoratifs ("...", "—", etc.)
    sont gardés en texte brut, sans span ni id : ils ne consomment pas d'index
    de mot, ce qui garantit l'alignement avec Whisper (qui ne les voit pas non plus).
    Retourne (html_str, n_real_words)."""
    parts = re.split(r'(<span class="emph(?: chromatic)?">[^<]*</span>)', html)
    out = []
    word_idx = [0]

    def make_word(w):
        # Si le token n'a aucun caractère alphanumérique (ex: "...", "—"), on
        # le laisse comme texte brut sans id, pour ne pas casser l'alignement.
        normalized = re.sub(r"[^\w]", "", w)
        if not normalized:
            return w
        word_idx[0] += 1
        if id_prefix:
            return f'<span class="word" id="{id_prefix}_w{word_idx[0]}">{w}</span>'
        return f'<span class="word">{w}</span>'

    for part in parts:
        if not part:
            continue
        m = re.match(r'<span class="(emph(?: chromatic)?)">([^<]*)</span>$', part)
        if m:
            classes = m.group(1)
            inner = m.group(2)
            words = inner.split()
            wrapped = " ".join(make_word(w) for w in words)
            out.append(f'<span class="{classes}">{wrapped}</span>')
        else:
            words = part.split()
            if words:
                out.append(" ".join(make_word(w) for w in words))
    rendered = " ".join(out)
    rendered = re.sub(
        r"(</span>)(</span>)?\s*([,.:;!?…]+)",
        lambda match: f"{match.group(3)}{match.group(1)}{match.group(2) or ''}",
        rendered,
    )
    rendered = re.sub(r"\s+([,.…])", r"\1", rendered)
    return rendered, word_idx[0]


def _normalize_word(w):
    """Normalise un mot pour le matching : minuscules, sans accents, sans ponctuation."""

    nfkd = unicodedata.normalize("NFKD", w.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c) and c.isalnum())
