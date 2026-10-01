"""Contrôle des médias : URLs suspectes, sécurité et pertinence (Gemini), audit du cache."""

import os
import re
from usine.media.config import NSFW_URL_BLACKLIST, STRICT_REAL_VALIDATION, gemini_client

try:
    from google.genai import types
except (
    ImportError
):  # SDK absent : gemini_client vaut None et les appels Gemini sont ignorés
    types = None


def url_est_suspecte(url: str) -> bool:
    """Vérifie si une URL contient des marqueurs de contenu adulte ou hors-sujet."""
    url_lower = url.lower()
    return any(marker in url_lower for marker in NSFW_URL_BLACKLIST)


def contexte_validation_media(
    context_histoire: str, query: str, scene_text: str = "", veo_prompt: str = ""
) -> str:
    parts = [
        f"CASE: {context_histoire}".strip(),
        f"SEARCH_QUERY: {query}".strip(),
    ]
    if scene_text:
        parts.append(f"SCENE_TEXT: {scene_text[:420]}")
    if veo_prompt:
        # Hors f-string : un antislash dans l'expression casse Python < 3.12
        visual = re.sub(r"\[STYLE LOCK[^\]]*\]", "", veo_prompt, flags=re.IGNORECASE)
        parts.append(f"EXPECTED_VISUAL: {visual[:520]}")
    return "\n".join(p for p in parts if p)


def verifier_securite_image(chemin_jpg: str) -> bool:
    """PHASE 1 — Vérification de sécurité obligatoire : rejette tout contenu NSFW/adulte/inapproprié.
    Cette vérification est indépendante de la pertinence historique et ne peut jamais être contournée.
    Retourne True si l'image est SAFE, False si elle doit être rejetée.
    """
    if not gemini_client:
        return True  # Sans IA, on suppose que la blacklist d'URL a déjà filtré
    try:
        from PIL import Image

        with Image.open(chemin_jpg) as im:
            prompt = (
                "Analyze this image carefully for safety and appropriateness. This image is for a professional documentary.\n"
                "You must perform a strict safety check.\n"
                "Answer UNSAFE if the image contains any of the following:\n"
                "- Nudity, partial nudity, exposed intimate parts, transparent or highly suggestive clothing.\n"
                "- Any sexual, romantic, or intimate actions/postures.\n"
                "- Any suggestive or adult-themed content, including adult movie posters, models in lingerie/underwear, or pin-up styles.\n"
                "- Graphic violence, blood, gore, weapons, or scary/disturbing faces (unless it is a highly desaturated historical document style).\n"
                "- Any commercial spam, product ads, online shopping pages, stock photo watermarks, or website screenshots.\n"
                "- Any modern gaming graphics, cartoons, anime, 3D renders, or fictional characters (like Roblox, Minecraft, Fortnite, or memes).\n"
                "\n"
                "If the image is completely clean, safe, and appropriate, answer SAFE.\n"
                "If there is ANY doubt or if the image triggers any of these rules, you MUST answer UNSAFE.\n"
                "Answer ONLY: SAFE or UNSAFE."
            )
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[im, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=5,
                ),
            )
            if response.text is None:
                print("      🛡️ Sécurité : Réponse nulle -> rejeté par précaution")
                return False
            ans = response.text.strip().upper()
            is_safe = "SAFE" in ans and "UNSAFE" not in ans
            print(
                f"      🛡️ Vérification sécurité : Réponse={ans} -> {'✅ SAFE' if is_safe else '🚫 UNSAFE — REJETÉ'}"
            )
            return is_safe
    except Exception as e:
        print(f"      ⚠️ Échec vérification sécurité : {e} -> rejeté par précaution")
        return False


def valider_image_historique(
    chemin_jpg: str,
    context_histoire: str,
    query: str,
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Pipeline de validation en 2 phases :
    PHASE 1 (obligatoire) : Vérification de sécurité NSFW — tout échec = rejet immédiat.
    PHASE 2 : Validation de pertinence historique/atmosphérique.
    """
    if not gemini_client:
        return False  # Sans IA, pas de validation possible → on ne prend aucun risque

    # ── PHASE 1 : Sécurité obligatoire ──
    if not verifier_securite_image(chemin_jpg):
        return False  # Rejet immédiat, sans passer à la phase 2

    # ── PHASE 2 : Pertinence ──
    try:
        from PIL import Image

        with Image.open(chemin_jpg) as im:
            context_block = contexte_validation_media(
                context_histoire, query, scene_text, veo_prompt
            )
            prompt = (
                "You are auditing one downloaded image for a serious documentary video.\n"
                "Your job is to decide whether this image is genuinely usable for the exact case and exact scene.\n"
                "\n"
                f"{context_block}\n"
                "\n"
                "CRITICAL REJECTION RULES:\n"
                "- Answer NO if the image is unrelated to the named case, person, place, object, period, or scene.\n"
                "- Answer NO for unrelated celebrities, actors, movie posters, book covers, memes, logos, ads, shopping pages, screenshots, gaming graphics, AI-looking fantasy art, or cartoons.\n"
                "- Answer NO if the search asks for a specific person/event/evidence and the image is only generic atmosphere.\n"
                "- Answer NO if the visual is modern when the scene requires a historical/period archive look.\n"
                "- Answer NO if the main subject is not understandable at mobile vertical-video size.\n"
                "\n"
                "ACCEPTABLE ONLY IF ONE OF THESE IS TRUE:\n"
                "- It appears to be a real archive/news/document/photo directly tied to the case.\n"
                "- It depicts the exact named person/place/evidence or a highly plausible period-correct representation of it.\n"
                "- For purely atmospheric queries, it clearly depicts the requested object/place/room and fits the period and tone.\n"
                "\n"
                "Be extremely skeptical. If there is any doubt, answer NO.\n"
                "Answer ONLY: YES or NO."
            )

            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[im, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=5,
                ),
            )
            if response.text is None:
                print("      🔍 Pertinence : Réponse nulle -> rejeté")
                return False
            ans = response.text.strip().upper()
            is_valid = "YES" in ans
            print(
                f"      🔍 Pertinence stricte : Réponse={ans} -> {'✅ Valide' if is_valid else '❌ Rejeté'}"
            )
            return is_valid
    except Exception as e:
        print(f"      ⚠️ Échec validation pertinence : {e} -> rejeté par précaution")
        return False


def valider_media_cache(
    chemin_media: str,
    context_histoire: str,
    queries: list,
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Valide la sécurité ET la pertinence d'un média existant (image ou vidéo).
    Retourne True si valide, False si invalide/suspect/hors-sujet.

    On effectue la double passe parce que les mismatch visuels/sous-titres
    (ex: image d'une femme alors que le sous-titre liste cinq hommes) ne sont
    pas détectables par la seule passe sécurité NSFW.
    """
    if not os.path.exists(chemin_media):
        return True

    query = queries[0] if queries else "dark mystery atmosphere"
    chemin_valider = chemin_media
    est_video = chemin_media.lower().endswith(".mp4")
    temp_jpg = None

    if est_video:
        temp_jpg = chemin_media + ".temp_val.jpg"
        import subprocess

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                chemin_media,
                "-ss",
                "00:00:01.5",
                "-vframes",
                "1",
                temp_jpg,
            ]
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )
            if os.path.exists(temp_jpg) and os.path.getsize(temp_jpg) > 1000:
                chemin_valider = temp_jpg
            else:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    chemin_media,
                    "-ss",
                    "00:00:00",
                    "-vframes",
                    "1",
                    temp_jpg,
                ]
                subprocess.run(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
                )
                if os.path.exists(temp_jpg) and os.path.getsize(temp_jpg) > 1000:
                    chemin_valider = temp_jpg
                else:
                    print(
                        f"      ⚠️ Impossible d'extraire une frame de la vidéo {os.path.basename(chemin_media)} — rejetée par sécurité"
                    )
                    return False
        except Exception as e:
            print(f"      ⚠️ Échec extraction frame vidéo : {e}")
            return False

    try:
        if STRICT_REAL_VALIDATION:
            valide = valider_image_historique(
                chemin_valider, context_histoire or query, query, scene_text, veo_prompt
            )
        else:
            valide = verifier_securite_image(chemin_valider)
        if temp_jpg and os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        return valide
    except Exception as e:
        if temp_jpg and os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        print(
            f"      ⚠️ Erreur lors de l'audit cache de {os.path.basename(chemin_media)} : {e}"
        )
        return False


def auditer_et_nettoyer_cache(
    dossier_projet: str, visual_plan: dict, context_histoire: str
):
    """Audit tout le cache existant et supprime immédiatement les fichiers invalides."""
    print("\n" + "═" * 56)
    print("  🛡️  AUDIT DE SÉCURITÉ & PERTINENCE DU CACHE EXISTANT")
    print("═" * 56)

    suppr_count = 0
    total_count = 0

    for scene_key, plans in visual_plan.items():
        for i, plan in enumerate(plans):
            file_path = plan.get("file_path", "")
            if not file_path:
                continue

            full_path = file_path
            if not os.path.isabs(full_path):
                full_path = os.path.join(
                    "/Users/melchioraholou/Documents/script-tiktok", file_path
                )

            if os.path.exists(full_path):
                total_count += 1
                print(
                    f"🧐 Audit cache : {scene_key}/plan_{i + 1} ({os.path.basename(full_path)})..."
                )
                queries = plan.get("real_media_queries", [])

                # Les médias générés (Imagen) sont issus d'un prompt qu'on contrôle,
                # donc on se contente d'une passe sécurité NSFW. Les sources curated
                # par contre venaient d'un scoring keyword qui pouvait se tromper de
                # sujet : on les soumet à la passe pertinence Gemini comme DDG/Bing.
                if plan.get("source_type") in {
                    "generated",
                    "imagen",
                    "generated_reused",
                }:
                    valide = verifier_securite_image(full_path)
                else:
                    valide = valider_media_cache(
                        full_path,
                        context_histoire,
                        queries,
                        plan.get("text_segment", ""),
                        plan.get("veo_prompt", ""),
                    )

                if not valide:
                    print(
                        f"💥 CACHE CORROMPU/INCORRECT -> Suppression de {os.path.basename(full_path)}"
                    )
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass
                    base_no_ext = os.path.splitext(full_path)[0]
                    for ext in [".jpg", ".mp4"]:
                        alt_path = base_no_ext + ext
                        if os.path.exists(alt_path):
                            try:
                                os.remove(alt_path)
                            except Exception:
                                pass
                    plan["file_path"] = ""
                    suppr_count += 1
                else:
                    print("   ✅ Cache validé.")

    print("\n" + "═" * 56)
    print(
        f"  🛡️ Fin audit cache : {suppr_count}/{total_count} médias corrompus supprimés"
    )
    print("═" * 56 + "\n")


def image_est_trop_noire(chemin_jpg: str) -> bool:
    """Détecte un fond noir de secours pour ne pas le recycler dans un rendu final."""
    try:
        from PIL import Image, ImageStat

        with Image.open(chemin_jpg) as im:
            im = im.convert("L").resize((32, 56))
            mean = ImageStat.Stat(im).mean[0]
            return mean < 18
    except Exception:
        return False
