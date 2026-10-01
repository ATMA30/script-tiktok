"""Alignement mot à mot des sous-titres sur la voix via faster-whisper."""

import json
import re
from pathlib import Path
from usine.render.config import USE_WHISPER_SYNC
from usine.render.text import _normalize_word


# Modèle Whisper global lazy-loaded (chargé une seule fois pour toutes les scènes)
_WHISPER_MODEL = None


def _align_by_text_match(script_words, w_words):
    """Aligne script_words ↔ w_words [(text, start, end), ...] via SequenceMatcher.
    Retourne une liste de {text, start, end} de même taille que script_words,
    avec interpolation linéaire pour les mots non matchés."""
    from difflib import SequenceMatcher

    norm_script = [_normalize_word(w) for w in script_words]
    norm_whisper = [_normalize_word(w[0]) for w in w_words]
    sm = SequenceMatcher(a=norm_script, b=norm_whisper, autojunk=False)

    # Construit un mapping script_idx → (start, end) pour les correspondances directes.
    direct = {}  # script_idx -> (start, end)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                _, t_start, t_end = w_words[j1 + k]
                direct[i1 + k] = (t_start, t_end)
        elif tag == "replace":
            # Match approximatif : on mappe proportionnellement le bloc
            n_s_block = i2 - i1
            n_w_block = j2 - j1
            if n_w_block == 0:
                continue
            for k in range(n_s_block):
                w_idx = j1 + min(
                    n_w_block - 1, round(k * (n_w_block - 1) / max(1, n_s_block - 1))
                )
                _, t_start, t_end = w_words[w_idx]
                direct[i1 + k] = (t_start, t_end)
        # 'delete' (script a des mots que Whisper n'a pas) : on remplit par interpolation après

    # Pour tous les mots du script non matchés, interpoler linéairement entre voisins matchés.
    last_t = w_words[0][1] if w_words else 0.0
    final_t = w_words[-1][2] if w_words else 0.0

    result = []
    for i in range(len(script_words)):
        if i in direct:
            t_start, t_end = direct[i]
        else:
            # Cherche le prochain mot matché vers la droite
            next_i = i + 1
            while next_i < len(script_words) and next_i not in direct:
                next_i += 1
            # Cherche le précédent mot matché vers la gauche
            prev_i = i - 1
            while prev_i >= 0 and prev_i not in direct:
                prev_i -= 1

            prev_t = direct[prev_i][1] if prev_i >= 0 else last_t
            next_t = direct[next_i][0] if next_i < len(script_words) else final_t + 0.5

            n_gap = (next_i - prev_i) if prev_i >= 0 else (next_i + 1)
            local_k = (i - prev_i) if prev_i >= 0 else (i + 1)
            t_start = prev_t + (next_t - prev_t) * (local_k / max(1, n_gap))
            t_end = t_start + 0.30  # durée par défaut interpolée
        result.append(
            {"text": script_words[i], "start": float(t_start), "end": float(t_end)}
        )
        last_t = t_end

    return result


def align_scene_words(audio_path, full_text):
    """Aligne les mots du script avec l'audio via faster-whisper + SequenceMatcher.
    Cache JSON dans `<audio_path>.words.json`.
    Retourne une liste de dicts {text, start, end} en secondes relatives au début de l'audio,
    ou None en cas d'échec.
    """
    if not USE_WHISPER_SYNC:
        return None
    audio_path = Path(audio_path)
    cache = audio_path.with_suffix(audio_path.suffix + ".words.json")
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("   ℹ️  faster-whisper indisponible — sync mot-par-mot désactivée.")
        return None

    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        device = "cpu"
        compute_type = "int8"
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
        except ImportError:
            pass

        print(
            f"   🤖 Chargement de Whisper (small, {compute_type} sur {device.upper()}) — une fois pour toutes les scènes..."
        )
        try:
            _WHISPER_MODEL = WhisperModel(
                "small", device=device, compute_type=compute_type
            )
        except Exception as e:
            print(f"   ⚠️  Whisper init échec : {e}")
            return None

    text = re.sub(r"\[STYLE LOCK[^\]]*\]", "", full_text, flags=re.IGNORECASE)
    text = re.sub(r"\[.*?\]", "", text).strip()
    script_words = [w for w in text.split() if re.sub(r"[^\w]", "", w)]
    if not script_words:
        return None

    try:
        segments, _ = _WHISPER_MODEL.transcribe(
            str(audio_path), word_timestamps=True, language="fr"
        )
        w_words = [
            (w.word.strip(), float(w.start), float(w.end))
            for s in segments
            for w in (s.words or [])
            if w.word and w.word.strip()
        ]
    except Exception as e:
        print(f"   ⚠️  Whisper transcribe échec : {e}")
        return None

    if not w_words:
        return None

    # Alignement textuel (SequenceMatcher) au lieu d'index proportionnel.
    # Beaucoup plus précis quand Whisper transcrit avec un nombre de mots différent.
    result = _align_by_text_match(script_words, w_words)

    try:
        cache.write_text(json.dumps(result), encoding="utf-8")
    except Exception:
        pass
    return result
