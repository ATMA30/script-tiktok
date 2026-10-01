"""Images générées : nettoyage des prompts, Imagen 4 (avec détection de quota), Pollinations."""

import io
import os
import re
import requests
import time
import urllib.parse
from usine.media import config as media_config
from usine.media.config import (
    ALLOW_POLLINATIONS_FALLBACK,
    IMAGEN_MODEL_FAST,
    IMAGEN_MODEL_STANDARD,
    STYLE_SUFFIX_LOW_POLY_3D,
    STYLE_SUFFIX_NOIR,
    TARGET_H,
    TARGET_W,
    gemini_client,
)

try:
    from google.genai import types
except (
    ImportError
):  # SDK absent : gemini_client vaut None et les appels Gemini sont ignorés
    types = None

IMAGEN_QUOTA_EPUISE = False


def nettoyer_prompt(prompt: str) -> str:
    """Nettoie et applique le suffixe de style au prompt en langage naturel continu.

    Imagen 4 a tendance à rendre visuellement les structures `label: valeur` et les
    longues listes virgule/clé qui ouvrent un prompt (on a vu apparaître
    "low_poly_3d_mesh: true / faceted_polygon_geometry: true / primary_subject:"
    dans plusieurs images). On reformule donc tout en phrases anglaises continues.
    """
    p = re.sub(r"\[STYLE LOCK[^\]]*\]", "", prompt, flags=re.IGNORECASE)
    p = re.sub(r"\[([^\]]+)\]", r"\1", p)
    p = re.sub(
        r"\b(sign|signs|signage|signpost|placard|banner|caption|subtitle)\b[^.,;]*",
        "",
        p,
        flags=re.IGNORECASE,
    )

    # Retirer les labels structurés (PRIMARY SUBJECT:, SCENE ATMOSPHERE:, etc.)
    # qui se faisaient dessiner sur l'image par Imagen.
    p = re.sub(
        r"\b(PRIMARY SUBJECT|SCENE ATMOSPHERE|AI INTERPRETATION HINT|COMPOSITION|NEGATIVE PROMPT|PROMPT|SUBJECT|STYLE)\b[^\n:]*[:\-–]\s*",
        "",
        p,
        flags=re.IGNORECASE,
    )

    # Convertir tout saut de ligne en espace : on veut un seul paragraphe continu.
    p = p.replace("\n", " ").replace("\r", " ")
    p = re.sub(r"\s+", " ", p).strip(" ,.;:")

    # Supprimer uniquement les déclencheurs VHS/camcorder (HUD caméscope indésirable).
    # En mode low_poly_3d, on conserve explicitement les termes 3D/low-poly.
    mots_a_supprimer = [
        r"\bvhs\b",
        r"\bcamcorder\b",
        r"\bcamcorder[-\s]?style\b",
        r"\bfound[-\s]?footage\b",
        r"\bhome[-\s]?video\b",
        r"\btape[-\s]?artefacts?\b",
        r"\bscan[-\s]?lines?\b",
        r"\bviewfinder\b",
        r"\bvideo[-\s]?noise\b",
        r"\bvintage[-\s]?video\b",
        r"\bamateur[-\s]?footage\b",
        r"\barchive[-\s]?footage\b",
    ]
    if media_config.STYLE_SUFFIX != STYLE_SUFFIX_LOW_POLY_3D:
        mots_a_supprimer.extend([r"\b3d render\b", r"\blow[-\s]?poly\b"])
    for pattern in mots_a_supprimer:
        p = re.sub(pattern, "", p, flags=re.IGNORECASE)

    # Nettoyer les doubles virgules ou espaces vides suite aux suppressions
    p = re.sub(r",\s*,", ",", p)
    p = re.sub(r"\s+", " ", p).strip(" ,.;:")

    # Préfixe ancrant le style demandé (appliqué via le suffixe pour les détails).
    if media_config.STYLE_SUFFIX == STYLE_SUFFIX_NOIR:
        if not p.lower().startswith("black and white"):
            p = "Black and white crime scene photography depicting " + p
    elif media_config.STYLE_SUFFIX == STYLE_SUFFIX_LOW_POLY_3D:
        if not p.lower().startswith("cinematic 3d low-poly"):
            p = "Cinematic 3D low-poly render depicting " + p
    else:
        if not p.lower().startswith("anime illustration"):
            p = "Anime illustration style depicting " + p

    # Suffixe global de style en phrases continues (jamais en liste de tags).
    if "completely free of any written text" not in p.lower():
        p += media_config.STYLE_SUFFIX

    # Nettoyage final des ponctuations
    p = re.sub(r",\s*,", ",", p)
    p = re.sub(r"\s+", " ", p).strip(" ,.;:")

    if len(p) > 1200:
        p = p[:1200]
    return p


# ═══════════════════════════════════════════════════════════════════════════════
#  GÉNÉRATION IMAGEN 4
# ═══════════════════════════════════════════════════════════════════════════════
def generer_image_imagen4(prompt: str, chemin_jpg: str) -> bool:
    global IMAGEN_QUOTA_EPUISE
    if not gemini_client or IMAGEN_QUOTA_EPUISE:
        return False

    prompt_clean = nettoyer_prompt(prompt)
    print(f"      📝 Prompt final Imagen : {prompt_clean[:90]}...")

    for model in [IMAGEN_MODEL_STANDARD, IMAGEN_MODEL_FAST]:
        label = model.split("-generate")[0]
        for attempt in range(3):
            try:
                print(f"      🎨 [{label}] Essai {attempt + 1}/3...")
                response = gemini_client.models.generate_images(
                    model=model,
                    prompt=prompt_clean,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/jpeg",
                        aspect_ratio="9:16",
                    ),
                )

                if not response.generated_images:
                    print("      ⚠️ Aucun pixel renvoyé")
                    time.sleep(2)
                    continue

                img_bytes = response.generated_images[0].image.image_bytes
                with open(chemin_jpg, "wb") as f:
                    f.write(img_bytes)

                if os.path.getsize(chemin_jpg) > 5000:
                    print(
                        f"      ✅ [{label}] Succès -> {os.path.basename(chemin_jpg)}"
                    )
                    return True
                else:
                    print("      ⚠️ Fichier trop petit -> retry")

            except Exception as e:
                msg = str(e)
                if "429" in msg or "quota" in msg.lower():
                    print(f"      ⏹️ Quota atteint pour le modèle {label} : {msg[:100]}")
                    if model == IMAGEN_MODEL_FAST:
                        print(
                            "      ⏹️ Imagen quota totalement atteint -> désactivation temporaire de la session"
                        )
                        IMAGEN_QUOTA_EPUISE = True
                        return False
                    else:
                        print("      👉 Passage au modèle suivant...")
                        break
                if "safety" in msg.lower() or "blocked" in msg.lower():
                    print(
                        "      ⚠️ Bloqué par le filtre de sécurité de ce modèle -> passage au modèle suivant"
                    )
                    break
                print(f"      ⚠️ Erreur Imagen (Essai {attempt + 1}) : {msg[:120]}")
                time.sleep(3 * (attempt + 1))

    return False


def generer_image_pollinations(prompt: str, chemin_jpg: str) -> bool:
    """Fallback IA sans API pour garder un vrai mix archive/reconstitution."""
    if not ALLOW_POLLINATIONS_FALLBACK:
        return False
    try:
        prompt_clean = nettoyer_prompt(prompt)
        prompt_clean += (
            " The framing should look like a historically plausible reenactment. "
            "The image must contain no logos, no watermark, and no written text of any kind."
        )
        prompt_clean = prompt_clean[:950]
        encoded = urllib.parse.quote(prompt_clean)
        seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(prompt_clean)) % 1000000
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={TARGET_W}&height={TARGET_H}&seed={seed}&nologo=true&private=true&enhance=true"
        )
        print("      🧠 [Pollinations IA] Fallback reconstitution...")
        resp = requests.get(url, timeout=35)
        if resp.status_code != 200 or len(resp.content) < 5000:
            print(
                f"      ⚠️ Pollinations réponse invalide ({resp.status_code}, {len(resp.content)} octets)"
            )
            return False
        from PIL import Image

        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        img.save(chemin_jpg, "JPEG", quality=92, optimize=True)
        if os.path.getsize(chemin_jpg) > 5000:
            print(
                f"      ✅ [Pollinations IA] Succès -> {os.path.basename(chemin_jpg)}"
            )
            return True
    except Exception as e:
        print(f"      ⚠️ Échec Pollinations IA : {str(e)[:120]}")
    if os.path.exists(chemin_jpg):
        try:
            os.remove(chemin_jpg)
        except OSError:
            pass
    return False
