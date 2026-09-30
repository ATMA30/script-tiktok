import os
import asyncio
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

scene_context = "A sterile, soundproof police interrogation room. Dead silence in the background. Close-mic recording."
sample_context = "Rapport d'enquête officiel de police. Ton extrêmement froid, neutre et clinique. Aucune émotion, aucun suspense, aucun souffle. Le narrateur est un professionnel de la sécurité qui lit des faits objectifs de manière lente, grave et monotone."
audio_profile = "Narrateur français d'enquêtes criminelles. Voix d'homme mûr, grave, rocailleuse et très solennelle."
director_note = "Style: Newscaster. Pace: Natural. Accent: Transatlantic."

prompt = f"""Scene
{scene_context}

Sample Context
{sample_context}

Voice settings
Audio Profile: {audio_profile}
Director's note: {director_note}

Text
Le 19 septembre 1961, à 23 heures 30 précises. Beti et Barne Hille ont croisé quelque chose sur la Route 3..."""

model_name = 'gemini-3.1-flash-tts-preview'

try:
    response = gemini_client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=1.3,
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name='Enceladus'
                    )
                )
            )
        )
    )
    audio_parts = [part for part in response.candidates[0].content.parts if part.inline_data]
    if audio_parts:
        audio_bytes = audio_parts[0].inline_data.data
        with open("test_voice_enceladus.wav", "wb") as f:
            f.write(audio_bytes)
        print("✅ Fichier test_voice_enceladus.wav généré avec succès !")
    else:
        print("⚠️ Aucun audio retourné.")
except Exception as e:
    print(f"Erreur: {e}")
