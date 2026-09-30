"""
2_generate_audio.py — TTS Pipeline
Priorité : Gemini 3.1 Flash TTS (voix Enceladus) → Edge-TTS (fallback gratuit)

Modèle TTS : gemini-3.1-flash-tts-preview
Voix       : Enceladus (grave, calme, autorité — parfait true crime FR)
Format     : audio/l16 (PCM 24kHz) → converti en WAV avec en-tête Python wave
"""

import os
import io
import json
import asyncio
import re
import wave
import subprocess
import edge_tts
import numpy as np
import soundfile as sf
from dotenv import load_dotenv
from utils import trouver_dernier_projet

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = None

if GEMINI_API_KEY:
    try:
        from google import genai
        from google.genai import types

        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("✅ Gemini TTS initialisé (gemini-3.1-flash-tts-preview)")
    except Exception as e:
        print("⚠️ Gemini SDK indisponible : %s" % e)

# ── Gemini TTS ────────────────────────────────────────────────────────────────
GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"

# ── VOIX SELON LE GENRE DU NARRATEUR ──────────────────────────────────────────
# Le genre est lu depuis script.json ("narrateur_genre", posé par le cerveau
# série) ; à défaut la variable d'env VOICE_GENDER ; à défaut masculin
# (comportement historique). On surcharge les voix Gemini via env si besoin.
GEMINI_VOICE_BY_GENDER = {
    "masculin": os.getenv("GEMINI_TTS_VOICE_M", "Enceladus"),  # grave, posée
    "feminin": os.getenv("GEMINI_TTS_VOICE_F", "Kore"),  # claire, féminine
}
EDGE_VOICE_BY_GENDER = {
    "masculin": "fr-FR-HenriNeural",
    "feminin": "fr-FR-DeniseNeural",
}
EDGE_PARAMS_BY_GENDER = {
    "masculin": {"rate": "-4%", "pitch": "-2Hz", "volume": "+0%"},
    "feminin": {"rate": "-3%", "pitch": "+0Hz", "volume": "+0%"},
}


def normaliser_genre(valeur: str) -> str:
    """Normalise une valeur de genre vers 'masculin' ou 'feminin'."""
    v = (valeur or "").strip().lower().replace("é", "e").replace("è", "e")
    if v in {"f", "feminin", "femme", "female", "woman", "fille", "girl"}:
        return "feminin"
    return "masculin"


# Valeurs ACTIVES — réassignées par appliquer_genre_voix() selon l'histoire.
GEMINI_TTS_VOICE = GEMINI_VOICE_BY_GENDER["masculin"]
EDGE_VOICE = EDGE_VOICE_BY_GENDER["masculin"]
EDGE_PARAMS = EDGE_PARAMS_BY_GENDER["masculin"]


def appliquer_genre_voix(genre: str) -> str:
    """Sélectionne la voix TTS (Gemini + Edge) selon le genre du narrateur."""
    global GEMINI_TTS_VOICE, EDGE_VOICE, EDGE_PARAMS
    g = normaliser_genre(genre)
    GEMINI_TTS_VOICE = GEMINI_VOICE_BY_GENDER[g]
    EDGE_VOICE = EDGE_VOICE_BY_GENDER[g]
    EDGE_PARAMS = EDGE_PARAMS_BY_GENDER[g]
    print(
        f"   🎚️ Voix narrateur : {g} → Gemini «{GEMINI_TTS_VOICE}» / Edge «{EDGE_VOICE}»"
    )
    return g


# Signature vocale "Les Archives de Minuit" : narration documentaire naturelle,
# claire et incarnée. La tension vient du récit, jamais d'un chuchotement.
TTS_CONTEXT_PROMPT = """\
[natural] [documentary] [clear] [conversational]
Parle avec une voix française naturelle, ouverte et bien projetée, au volume normal d'un narrateur de documentaire.
Le ton est humain, fluide et captivant, comme si tu racontais une histoire troublante directement à une personne.
Articule clairement sans prendre une voix artificiellement grave. Garde un rythme vivant et marque seulement les pauses écrites dans le texte.
Ne chuchote jamais. Ne parle pas à voix basse. Pas de souffle audible, pas de voix cassée, pas de surjeu horrifique.
"""
TTS_TEMPO = float(os.getenv("TTS_TEMPO", "1.06"))

DRAMATIC_KEYWORDS = [
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
    "faux",
    "fausse",
    "jamais",
    "rien",
    "plus rien",
    "tout perdu",
    "erreur",
    "faute",
    "responsable",
    "silence",
    "seul",
    "seule",
    "personne",
    "peur",
    "honte",
    "culpabilité",
    "amour",
    "aimé",
    "aimée",
    "confiance",
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
    "su",
    "aveugle",
    "naïf",
    "naïve",
]


def nettoyer_texte_pour_tts_ssml(texte: str) -> str:
    """Enrobe le texte avec des balises SSML pour Edge-TTS afin de rendre la voix dramatique."""
    texte_clean = nettoyer_texte_pour_tts(texte)
    # Appliquer des balises d'emphase sur les mots dramatiques
    for kw in DRAMATIC_KEYWORDS:
        pattern = r"\b(%s)\b" % re.escape(kw)
        texte_clean = re.sub(
            pattern,
            r'<emphasis level="strong">\1</emphasis>',
            texte_clean,
            flags=re.IGNORECASE,
        )

    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="fr-FR">'
        f'<voice name="{EDGE_VOICE}">'
        f'<prosody pitch="{EDGE_PARAMS["pitch"]}" rate="{EDGE_PARAMS["rate"]}" volume="{EDGE_PARAMS["volume"]}">'
        f"{texte_clean}"
        f"</prosody>"
        f"</voice>"
        f"</speak>"
    )
    return ssml


def enlever_silences_wav(audio_path, threshold_db=-45, keep_silence_sec=0.45):
    """
    Supprime les silences supérieurs à keep_silence_sec d'un fichier WAV.
    0.45s : préserve les respirations et pauses naturelles (style confession).
    """
    try:
        data, sr = sf.read(audio_path)
        is_stereo = len(data.shape) > 1
        if is_stereo:
            mono_data = np.mean(data, axis=1)
        else:
            mono_data = data

        # Calcul de l'énergie (RMS) par fenêtres de 10ms
        win_len = int(0.01 * sr)
        n_wins = len(mono_data) // win_len

        is_silent = np.zeros(n_wins, dtype=bool)
        for i in range(n_wins):
            win = mono_data[i * win_len : (i + 1) * win_len]
            rms = np.sqrt(np.mean(win**2))
            db = 20 * np.log10(rms + 1e-10)
            if db < threshold_db:
                is_silent[i] = True

        keep_wins = int(keep_silence_sec / 0.01)
        new_data_blocks = []
        idx = 0
        while idx < n_wins:
            if not is_silent[idx]:
                new_data_blocks.append(data[idx * win_len : (idx + 1) * win_len])
                idx += 1
            else:
                sil_start_idx = idx
                while idx < n_wins and is_silent[idx]:
                    idx += 1
                sil_end_idx = idx

                sil_wins = sil_end_idx - sil_start_idx
                wins_to_keep = min(sil_wins, keep_wins)
                if wins_to_keep > 0:
                    new_data_blocks.append(
                        data[
                            sil_start_idx * win_len : (sil_start_idx + wins_to_keep)
                            * win_len
                        ]
                    )

        # Ajouter le reste du fichier
        remaining_samples = len(data) % win_len
        if remaining_samples > 0:
            new_data_blocks.append(data[n_wins * win_len :])

        if new_data_blocks:
            compressed_data = np.concatenate(new_data_blocks, axis=0)
            sf.write(audio_path, compressed_data, sr)
            orig_duration = len(data) / sr
            new_duration = len(compressed_data) / sr
            print(
                f"   ✂️ Silence Removal : {orig_duration:.2f}s → {new_duration:.2f}s sur {os.path.basename(audio_path)}"
            )
    except Exception as e:
        print(f"   ⚠️ Échec du Silence Removal : {e}")


# ── Text Cleaning & Normalization Helpers ─────────────────────────────────────
def nettoyer_texte_pour_tts(texte: str) -> str:
    """Nettoie le texte pour éviter les stutters, balises parasites et caractères spéciaux."""
    if not texte:
        return ""
    # Conserve l'intention de pause du script utilisateur au lieu de supprimer
    # l'ellipse Unicode au nettoyage final.
    texte = texte.replace("…", "...")
    # 1. Enlever les balises entre crochets [STYLE LOCK...], [SFX...], etc.
    texte = re.sub(r"\[.*?\]", "", texte)
    # 2. Enlever les directions scéniques entre parenthèses (soupire), (silence), etc.
    texte = re.sub(r"\(.*?\)", "", texte)
    # 3. Enlever le markdown de gras/italique (**texte**, *texte*, _texte_)
    texte = re.sub(r"\*\*([^*]+)\*\*", r"\1", texte)
    texte = re.sub(r"\*([^*]+)\*", r"\1", texte)
    texte = re.sub(r"__([^_]+)__", r"\1", texte)
    texte = re.sub(r"_([^_]+)_", r"\1", texte)
    # 4. Remplacer les abréviations courantes pour éviter les hésitations du TTS
    abbreviations = {
        r"\bex\b\.?": "exemple",
        r"\betc\b\.?": "et cetera",
        r"\bvs\b\.?": "versus",
        r"\bN°\b": "numéro",
        r"\bn°\b": "numéro",
        r"\bM\b\.": "Monsieur",
        r"\bDr\b\.?": "Docteur",
        r"\bSt\b\.?": "Saint",
        r"\b%": " pour cent",
        r"\b&": " et ",
    }
    for pattern, replacement in abbreviations.items():
        texte = re.sub(pattern, replacement, texte, flags=re.IGNORECASE)
    # 5. Nettoyer les caractères spéciaux restants (garder la ponctuation de base française/anglaise)
    texte = re.sub(r'[^\w\s,.!?\'\-’"«»éèêëàâäîïôöùûüçÉÈÊËÀÂÄÎÏÔÖÙÛÜÇ]', "", texte)
    # 6. Remplacer les retours à la ligne par des espaces
    texte = texte.replace("\n", " ").replace("\r", " ").replace("_", " ")
    # 7. Remplacer plusieurs espaces par un seul
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte


def normaliser_audio_wav(chemin_wav: str, target_dbfs: float = -2.0):
    """Normalise un fichier WAV à -2 dBFS pour éviter la saturation."""
    try:
        if not os.path.exists(chemin_wav):
            return
        with wave.open(chemin_wav, "rb") as wf:
            params = wf.getparams()
            frames = wf.readframes(params.nframes)

        if params.sampwidth == 2:  # 16-bit PCM
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            peak = np.max(np.abs(data))
            if peak > 0:
                target_peak = (10 ** (target_dbfs / 20.0)) * 32767.0
                factor = target_peak / peak
                data_normalized = np.clip(data * factor, -32768, 32767).astype(np.int16)

                with wave.open(chemin_wav, "wb") as wf_out:
                    wf_out.setparams(params)
                    wf_out.writeframes(data_normalized.tobytes())
                print(
                    f"   🔊 Normalisation {target_dbfs} dBFS appliquée sur {os.path.basename(chemin_wav)}"
                )
    except Exception as e:
        print(f"   ⚠️ Erreur lors de la normalisation audio : {e}")


def appliquer_tempo_wav(chemin_wav: str, tempo: float = TTS_TEMPO):
    """Accélère très légèrement la voix sans changer la hauteur."""
    if not os.path.exists(chemin_wav) or abs(tempo - 1.0) < 0.01:
        return
    tempo = max(0.85, min(1.18, float(tempo)))
    tmp = chemin_wav + ".tempo.wav"
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", chemin_wav, "-filter:a", f"atempo={tempo:.3f}", tmp],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if (
            result.returncode == 0
            and os.path.exists(tmp)
            and os.path.getsize(tmp) > 2000
        ):
            os.replace(tmp, chemin_wav)
            print(
                f"   🎚️ Tempo naturel appliqué : x{tempo:.2f} sur {os.path.basename(chemin_wav)}"
            )
        elif os.path.exists(tmp):
            os.remove(tmp)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f"   ⚠️ Tempo audio non appliqué : {e}")


# ─────────────────────────────────────────────────────────────────────────────
def _pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Encapsule du raw PCM 16-bit mono en WAV valide (en mémoire)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def generer_audio_gemini(texte: str, chemin_sortie: str) -> bool:
    """
    Génère la voix via Gemini 3.1 Flash TTS.
    Gère le format audio/l16 (PCM 24kHz) retourné par Gemini.
    Retourne True si succès.
    """
    if not gemini_client:
        return False

    # Nettoyage complet
    texte_clean = nettoyer_texte_pour_tts(texte)
    if not texte_clean:
        return False

    # Le prompt combine le contexte narratif + le texte de la scène
    contents = f"{TTS_CONTEXT_PROMPT}\n\n{texte_clean}"

    for attempt in range(3):
        try:
            print(
                f"   🎙️ Gemini TTS [{GEMINI_TTS_VOICE}] scène → essai {attempt + 1}/3..."
            )
            response = gemini_client.models.generate_content(
                model=GEMINI_TTS_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=GEMINI_TTS_VOICE
                            )
                        )
                    ),
                ),
            )

            # Vérifier qu'on a bien reçu un candidat audio
            if not (
                response.candidates
                and response.candidates[0].content
                and response.candidates[0].content.parts
            ):
                print(f"   ⚠️ Gemini : aucun audio renvoyé (essai {attempt + 1})")
                import time

                time.sleep(2)
                continue

            audio_parts = [
                p for p in response.candidates[0].content.parts if p.inline_data
            ]
            if not audio_parts:
                print(f"   ⚠️ Gemini : parts sans inline_data (essai {attempt + 1})")
                import time

                time.sleep(2)
                continue

            mime = audio_parts[0].inline_data.mime_type or ""
            raw_data = audio_parts[0].inline_data.data

            # Gemini 3.1 TTS renvoie audio/l16 (PCM brut) → on ajoute l'en-tête WAV
            if "audio/l16" in mime.lower():
                wav_bytes = _pcm_to_wav_bytes(raw_data, sample_rate=24000)
            else:
                # Déjà un WAV ou autre format accepté directement
                wav_bytes = raw_data

            with open(chemin_sortie, "wb") as f:
                f.write(wav_bytes)

            if os.path.getsize(chemin_sortie) > 2000:
                print(f"   ✨ Gemini TTS ✅ : {os.path.basename(chemin_sortie)}")
                return True
            else:
                print(f"   ⚠️ Fichier audio trop petit — retry")

        except Exception as e:
            msg = str(e)
            if "429" in msg or "quota" in msg.lower():
                print(f"   ⚠️ Quota Gemini TTS atteint → fallback Edge-TTS")
                return False
            print(f"   ⚠️ Gemini TTS erreur (essai {attempt + 1}) : {msg[:120]}")
            import time

            time.sleep(3)

    return False


# ─────────────────────────────────────────────────────────────────────────────
async def generer_audio_edge(texte: str, chemin_sortie: str):
    """Fallback Edge-TTS avec paramètres vocaux natifs.

    edge-tts n'interprète pas toujours le SSML fourni comme attendu et peut
    prononcer ou étirer les balises. Le texte simple garde une durée naturelle.
    """
    texte_clean = nettoyer_texte_pour_tts(texte)

    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(
                text=texte_clean,
                voice=EDGE_VOICE,
                rate=EDGE_PARAMS["rate"],
                pitch=EDGE_PARAMS["pitch"],
                volume=EDGE_PARAMS["volume"],
            )
            await comm.save(chemin_sortie)
            print(f"   ✅ Edge-TTS fallback : {os.path.basename(chemin_sortie)}")
            return
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep((attempt + 1) * 3)
            else:
                print(f"   ❌ Edge-TTS échoué définitivement : {e}")
                # Crée un silence de 3s pour débloquer le pipeline
                import numpy as np, soundfile as sf

                sf.write(chemin_sortie, np.zeros(24000 * 3), 24000)
                print(f"   ⚠️ Silence artificiel créé (3s)")


# ─────────────────────────────────────────────────────────────────────────────
async def _traiter_scene(
    index: int, scene: dict, dossier_projet: str, semaphore: asyncio.Semaphore
):
    async with semaphore:
        chemin_audio = f"{dossier_projet}/audio/scene_{index + 1}.wav"

        # Cache : on saute si déjà généré et valide
        if os.path.exists(chemin_audio) and os.path.getsize(chemin_audio) > 5000:
            print(f"   ⏭️  Scène {index + 1} — cache OK")
            return

        print(f"   ► Scène {index + 1}...")

        # Gemini TTS lit mieux le texte orthographiquement correct (SUBTITLE / audio_tts)
        # car le modèle est multilingue et gère les noms anglais nativement.
        texte_source = (
            scene.get("audio_tts")
            or scene.get("subtitle")
            or scene.get("voix_off_tts")
            or scene.get("voix_off", "")
        )
        # Nettoyage et normalisation dans le pipeline de génération
        texte_source = nettoyer_texte_pour_tts(texte_source)

        # Pipeline : Gemini TTS → Edge-TTS fallback
        gemini_ok = generer_audio_gemini(texte_source, chemin_audio)
        if gemini_ok:
            enlever_silences_wav(chemin_audio)
            appliquer_tempo_wav(chemin_audio)
            normaliser_audio_wav(chemin_audio)
            return
        print(f"   🔄 Fallback Edge-TTS...")
        await generer_audio_edge(texte_source, chemin_audio)
        enlever_silences_wav(chemin_audio)
        appliquer_tempo_wav(chemin_audio)
        normaliser_audio_wav(chemin_audio)


# ─────────────────────────────────────────────────────────────────────────────
async def traiter_projet(dossier_projet: str):
    with open(f"{dossier_projet}/script.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # Voix masculine/féminine selon le narrateur de l'histoire.
    appliquer_genre_voix(
        data.get("narrateur_genre") or os.getenv("VOICE_GENDER", "masculin")
    )

    voix_active = (
        f"Gemini TTS ({GEMINI_TTS_VOICE})"
        if gemini_client
        else f"Edge-TTS ({EDGE_VOICE})"
    )
    print(f"\n🎙️ Génération AUDIO ({voix_active}) : {data['projet']}")
    os.makedirs(f"{dossier_projet}/audio", exist_ok=True)

    # Gemini TTS : 2 en parallèle max (respect des quotas)
    # Edge-TTS   : 5 en parallèle OK
    parallel = 2 if gemini_client else 5
    semaphore = asyncio.Semaphore(parallel)

    await asyncio.gather(
        *[
            _traiter_scene(i, s, dossier_projet, semaphore)
            for i, s in enumerate(data["scenes"])
        ]
    )
    print(f"✅ Audio terminé ({len(data['scenes'])} scènes) — {voix_active}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dossier = trouver_dernier_projet()
    if dossier:
        asyncio.run(traiter_projet(dossier))
    else:
        print("📁 Aucun projet trouvé.")
