"""Orchestration : un média par plan du visual_plan.json (réel, généré ou secours)."""

import json
import os
import re
import time
from usine.utils import trouver_dernier_projet
from usine.media import config as media_config
from usine.media.config import (
    ALLOW_PEXELS_VIDEO,
    ALLOW_STOCK_FALLBACKS,
    REAL_MEDIA_ONLY,
    SKIP_CACHE_AUDIT,
    STYLE_SUFFIX_ANIME,
    STYLE_SUFFIX_LOW_POLY_3D,
    STYLE_SUFFIX_NOIR,
    gemini_client,
)
from usine.media.generation import generer_image_imagen4, generer_image_pollinations
from usine.media.images import (
    creer_fond_noir,
    creer_reconstitution_locale,
    normaliser_image,
    reutiliser_media_backup,
)
from usine.media.queries import (
    choisir_role_media,
    extraire_mots_cles,
    metaphoriser_prompt_avec_gemini,
    obtenir_mots_cles_contexte,
    requete_affaire_specifique,
)
from usine.media.sources import (
    telecharger_bing_image,
    telecharger_duckduckgo_image,
    telecharger_pexels_image,
    telecharger_pexels_video,
    telecharger_pixabay_image,
    telecharger_source_curated,
)
from usine.media.validation import auditer_et_nettoyer_cache, image_est_trop_noire


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAITEMENT DE CHAQUE PLAN
# ═══════════════════════════════════════════════════════════════════════════════
VEO_PROMPT_DEFAUT = (
    "A lone figure standing in a foggy cinematic scene, centered vertical composition, "
    "faceted low-poly 3D geometry, cold desaturated lighting, mysterious true-crime atmosphere"
)


def traiter_plan_unique(
    scene_key: str,
    i: int,
    plan: dict,
    dir_img: str,
    dir_vid: str,
    contexte_niche: str = "",
    context_histoire: str = "",
) -> str:
    veo_prompt = plan.get("veo_prompt", "") or VEO_PROMPT_DEFAUT
    real_queries = plan.get("real_media_queries", [])
    scene_text = plan.get("text_segment", "")

    chemin_jpg = os.path.join(dir_img, f"plan_{i + 1}.jpg")
    chemin_mp4 = os.path.join(dir_img, f"plan_{i + 1}.mp4")

    # Cache check
    if os.path.exists(chemin_mp4) and os.path.getsize(chemin_mp4) > 50000:
        if os.path.exists(chemin_jpg):
            os.remove(chemin_jpg)
        print(f"   ⏭️  {scene_key}/plan_{i + 1} (Vidéo) -> cache OK")
        return chemin_mp4

    if os.path.exists(chemin_jpg) and os.path.getsize(chemin_jpg) > 500:
        if plan.get("source_type") in [
            "generated_local",
            "generated_pollinations",
            "fallback_local",
            "fallback_black",
        ]:
            print(
                f"      🗑️ Image cache local/fallback trouvé ({plan.get('source_type')}), suppression pour régénération..."
            )
            try:
                os.remove(chemin_jpg)
            except OSError:
                pass
        else:
            if os.path.exists(chemin_mp4):
                os.remove(chemin_mp4)
            print(f"   ⏭️  {scene_key}/plan_{i + 1} (Image) -> cache OK")
            return chemin_jpg

    print(f"\n   🎬 {scene_key} / plan_{i + 1}")

    media_role = choisir_role_media(
        scene_key, i, plan, contexte_niche, context_histoire
    )
    plan["media_role"] = media_role
    print(f"      🎚️ Choix éditorial : {media_role.upper()}")

    real_queries_strict = [
        q
        for q in real_queries
        if (not REAL_MEDIA_ONLY)
        or requete_affaire_specifique(q, contexte_niche, context_histoire)
    ]

    if media_role == "real":
        # ── PRIORITÉ 0 : Vidéo Pexels désactivée par défaut.
        # C'est du stock, pas de l'archive vérifiable, donc trop risqué pour les "vrais médias".
        if ALLOW_PEXELS_VIDEO and real_queries_strict:
            for query in real_queries_strict:
                if telecharger_pexels_video(query, chemin_mp4):
                    if os.path.exists(chemin_jpg):
                        os.remove(chemin_jpg)
                    plan["source_type"] = "real_video"
                    return chemin_mp4

        # ── PRIORITÉ 0.5 : Photos réelles.
        # Enfield et autres affaires connues : on exploite d'abord les sources
        # curated variées, puis DDG court, puis Bing en filet de secours.
        if real_queries_strict:
            for query in real_queries_strict:
                if telecharger_source_curated(
                    query,
                    chemin_jpg,
                    contexte_niche,
                    context_histoire,
                    scene_text,
                    veo_prompt,
                ):
                    normaliser_image(chemin_jpg)
                    if os.path.exists(chemin_mp4):
                        os.remove(chemin_mp4)
                    plan["source_type"] = "curated_real"
                    return chemin_jpg
                if telecharger_duckduckgo_image(
                    query,
                    chemin_jpg,
                    contexte_niche,
                    context_histoire,
                    scene_text,
                    veo_prompt,
                ):
                    normaliser_image(chemin_jpg)
                    if os.path.exists(chemin_mp4):
                        os.remove(chemin_mp4)
                    plan["source_type"] = "real_search"
                    return chemin_jpg
                if telecharger_bing_image(
                    query,
                    chemin_jpg,
                    contexte_niche,
                    context_histoire,
                    scene_text,
                    veo_prompt,
                ):
                    normaliser_image(chemin_jpg)
                    if os.path.exists(chemin_mp4):
                        os.remove(chemin_mp4)
                    plan["source_type"] = "real_search"
                    return chemin_jpg

        elif REAL_MEDIA_ONLY:
            print(
                "      ⛔ Aucune requête assez spécifique à l'affaire pour du vrai média"
            )

    if REAL_MEDIA_ONLY:
        print(
            "      ⛔ REAL_MEDIA_ONLY=1 : génération IA et stock désactivés pour ce plan"
        )
        creer_fond_noir(chemin_jpg)
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "fallback_black"
        return chemin_jpg

    # ── PRIORITÉ 1 : Imagen 4 avec métaphorisation IA ──
    # Le sous-titre EXACT du plan (ce que la voix off dit pendant cette image)
    # passe en tête du prompt et hérite du poids le plus fort. Le veo_prompt
    # (ambiance générique de la scène) ne sert que de fond stylistique. Avant,
    # scene_text était tronqué en suffixe à 260 caractères et Imagen prenait
    # ses ordres dans le veo_prompt — d'où une "cuisine avec une mère" générée
    # alors que le sous-titre énumérait cinq hommes.
    #
    # IMPORTANT : on construit ici une phrase en langage naturel continu, sans
    # labels du type "PRIMARY SUBJECT: ..." qu'Imagen rendrait visuellement
    # comme du texte dans l'image.
    clean_veo = re.sub(
        r"\[STYLE LOCK[^\]]*\]", "", veo_prompt, flags=re.IGNORECASE
    ).strip()
    clean_veo = re.sub(
        r"\bthe Hesperus\b|\bHesperus\b",
        "an unmarked 1900 Scottish lighthouse tender",
        clean_veo,
        flags=re.IGNORECASE,
    )
    narration = (scene_text or "").strip()

    parts = []
    if clean_veo:
        parts.append(
            f"Create exactly this visual scene: {clean_veo[:850]}. "
            "Preserve the stated number of people, the stated lighting state, the concrete action, and the camera composition."
        )
    if narration:
        parts.append(
            "The image illustrates a narrated documentary beat, but it must never show the narration as captions or writing."
        )
    metaphorized = ""
    if media_config.STYLE_SUFFIX != STYLE_SUFFIX_LOW_POLY_3D:
        metaphorized = metaphoriser_prompt_avec_gemini(veo_prompt)
    if metaphorized and metaphorized.lower() not in (clean_veo or "").lower():
        parts.append(f"The overall visual feel is {metaphorized}.")
    parts.append(
        "All clothing, buildings, equipment, flags and vessel hulls are blank and unmarked. "
        "There are no readable words, names, letters, numbers, signs, logos, captions or interface elements anywhere. "
        "This is a fresh original frame that does not repeat earlier shots in the sequence."
    )
    generation_prompt = " ".join(parts)
    if generer_image_imagen4(generation_prompt, chemin_jpg):
        normaliser_image(chemin_jpg)
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "generated"
        return chemin_jpg

    if generer_image_pollinations(generation_prompt, chemin_jpg):
        normaliser_image(chemin_jpg)
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "generated_pollinations"
        return chemin_jpg

    if media_role == "generated" and reutiliser_media_backup(
        dir_img, scene_key, i, chemin_jpg, "IA"
    ):
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "generated_reused"
        return chemin_jpg

    if media_role == "generated" and creer_reconstitution_locale(
        generation_prompt, chemin_jpg
    ):
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = "generated_local"
        return chemin_jpg

    # ── PRIORITÉ REPLI 1.5 : si Imagen échoue, tenter une vraie image avant le stock.
    if real_queries_strict:
        for query in real_queries_strict:
            if telecharger_duckduckgo_image(
                query,
                chemin_jpg,
                contexte_niche,
                context_histoire,
                scene_text,
                veo_prompt,
            ):
                normaliser_image(chemin_jpg)
                if os.path.exists(chemin_mp4):
                    os.remove(chemin_mp4)
                plan["source_type"] = "real_search_after_imagen"
                return chemin_jpg
            if telecharger_source_curated(
                query,
                chemin_jpg,
                contexte_niche,
                context_histoire,
                scene_text,
                veo_prompt,
            ):
                normaliser_image(chemin_jpg)
                if os.path.exists(chemin_mp4):
                    os.remove(chemin_mp4)
                plan["source_type"] = "curated_real_after_imagen"
                return chemin_jpg

    if not ALLOW_STOCK_FALLBACKS:
        print(
            "      ⛔ Stock Pexels/Pixabay désactivé : fallback reconstitution locale"
        )
        if not creer_reconstitution_locale(generation_prompt, chemin_jpg):
            creer_fond_noir(chemin_jpg)
        if os.path.exists(chemin_mp4):
            os.remove(chemin_mp4)
        plan["source_type"] = (
            "fallback_local"
            if not image_est_trop_noire(chemin_jpg)
            else "fallback_black"
        )
        return chemin_jpg

    # ── PRIORITÉ 2 : Pexels Stock avec boucle de dégradation de mots-clés ──
    for q in real_queries + [veo_prompt]:
        mots_cles = extraire_mots_cles(q)
        words = mots_cles.split()
        for limit in range(len(words), 0, -1):
            query_degraded = " ".join(words[:limit])
            print(f"      🔄 Fallback Pexels dégradé : '{query_degraded}'")
            if telecharger_pexels_image(query_degraded, chemin_jpg):
                normaliser_image(chemin_jpg)
                if os.path.exists(chemin_mp4):
                    os.remove(chemin_mp4)
                plan["source_type"] = "stock_pexels"
                return chemin_jpg

    # ── PRIORITÉ 3 : Pixabay Stock avec boucle de dégradation de mots-clés ──
    for q in real_queries + [veo_prompt]:
        mots_cles = extraire_mots_cles(q)
        words = mots_cles.split()
        for limit in range(len(words), 0, -1):
            query_degraded = " ".join(words[:limit])
            print(f"      🔄 Fallback Pixabay dégradé : '{query_degraded}'")
            if telecharger_pixabay_image(query_degraded, chemin_jpg):
                normaliser_image(chemin_jpg)
                if os.path.exists(chemin_mp4):
                    os.remove(chemin_mp4)
                plan["source_type"] = "stock_pixabay"
                return chemin_jpg

    # ── PRIORITÉ 4 : Requêtes génériques de secours ──
    for query in [
        "dark mystery night fog",
        "abandoned room shadows",
        "shadow silhouette dark",
    ]:
        if telecharger_pexels_image(query, chemin_jpg):
            normaliser_image(chemin_jpg)
            if os.path.exists(chemin_mp4):
                os.remove(chemin_mp4)
            plan["source_type"] = "stock_pexels_generic"
            return chemin_jpg
        if telecharger_pixabay_image(query, chemin_jpg):
            normaliser_image(chemin_jpg)
            if os.path.exists(chemin_mp4):
                os.remove(chemin_mp4)
            plan["source_type"] = "stock_pixabay_generic"
            return chemin_jpg

    # ── DERNIER RECOURS : Fond noir ──
    creer_fond_noir(chemin_jpg)
    if os.path.exists(chemin_mp4):
        os.remove(chemin_mp4)
    plan["source_type"] = "fallback_black"
    return chemin_jpg


# ═══════════════════════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════════════════
def traiter_fetcher(dossier_projet: str):
    plan_path = f"{dossier_projet}/visual_plan.json"
    if not os.path.exists(plan_path):
        print(f"❌ visual_plan.json introuvable : {plan_path}")
        return

    script_path = f"{dossier_projet}/script.json"
    niche = ""
    visual_bible = {}
    script_data = {}
    if os.path.exists(script_path):
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script_data = json.load(f)
                niche = script_data.get("niche", "")
                # Sélectionner le style visuel selon le projet
                visual_style = script_data.get("visual_style", "low_poly_3d")
                if visual_style in {"low_poly_3d", "3d", "low-poly"}:
                    media_config.STYLE_SUFFIX = STYLE_SUFFIX_LOW_POLY_3D
                    style_label = "3D low-poly cinematic"
                elif visual_style == "noir":
                    media_config.STYLE_SUFFIX = STYLE_SUFFIX_NOIR
                    style_label = "noir B&W"
                else:
                    media_config.STYLE_SUFFIX = STYLE_SUFFIX_ANIME
                    style_label = "anime couleur"
                print(f"   🎨 Style visuel : {visual_style.upper()} ({style_label})")
                # Charger la visual_bible pour la consistance des personnages
                raw_bible = script_data.get("visual_bible", {})
                if isinstance(raw_bible, dict):
                    visual_bible = raw_bible
                # Enrichir depuis personnages (format mystère : prenom + description_visuelle)
                for p in script_data.get("personnages", []):
                    if isinstance(p, dict):
                        key = p.get("prenom") or p.get("nom")
                        desc = p.get("description_visuelle", "")
                        if key and desc:
                            visual_bible[key] = desc
        except Exception as e:
            print(f"⚠️ Impossible de lire script.json : {e}")

    # Obtenir le contexte court de l'affaire en anglais
    contexte_niche = obtenir_mots_cles_contexte(niche) if niche else ""

    with open(plan_path, "r", encoding="utf-8") as f:
        visual_plan = json.load(f)

    # Injecter la visual_bible dans chaque plan pour la consistance des personnages
    if visual_bible:
        for scene_key, plans in visual_plan.items():
            # Récupérer le texte de la scène correspondante
            scene_num = int(scene_key.split("_")[1]) - 1
            scenes = (
                script_data.get("scenes", []) if os.path.exists(script_path) else []
            )
            scene_text = (
                scenes[scene_num].get("audio_tts", "")
                if 0 <= scene_num < len(scenes)
                else ""
            )
            for plan in plans:
                veo = plan.get("veo_prompt", "")
                # Chercher quel personnage est mentionné dans le veo_prompt ou la scène
                injected = []
                for nom, desc in visual_bible.items():
                    if nom.lower() in veo.lower() or nom.lower() in scene_text.lower():
                        # Injecter seulement les 80 premiers chars de la description
                        injected.append(f"{nom}: {desc[:80]}")
                if injected:
                    char_ctx = " | ".join(injected)
                    # L'action reste en tête : Imagen doit d'abord comprendre
                    # le plan, puis utiliser la bible comme contrainte de cohérence.
                    plan["veo_prompt"] = f"{veo} [CHARACTERS: {char_ctx}]"

    # L'audit Gemini peut être désactivé pour des médias Imagen déjà contrôlés
    # visuellement. Cela évite qu'une réponse ambiguë du classifieur supprime de
    # bons rendus pendant une régénération ciblée.
    if SKIP_CACHE_AUDIT:
        print("   ⏭️  Audit du cache désactivé (SKIP_CACHE_AUDIT=1)")
    else:
        auditer_et_nettoyer_cache(dossier_projet, visual_plan, niche or contexte_niche)

    src = "Imagen 4 (Gemini API)" if gemini_client else "Pexels/Pixabay (stock)"
    print("═" * 56)
    print(f"  🎨 ÉTAPE 2.7 : MEDIA FETCHER — {src}")
    print("═" * 56)
    if visual_bible:
        print(
            f"   👥 Visual bible : {len(visual_bible)} personnage(s) injectés dans les prompts"
        )

    work = []
    for scene_key, plans in visual_plan.items():
        num = scene_key.split("_")[1]
        dir_img = f"{dossier_projet}/real_media/scene_{num}"
        dir_vid = f"{dossier_projet}/video/scene_{num}"
        os.makedirs(dir_img, exist_ok=True)
        os.makedirs(dir_vid, exist_ok=True)
        for i, plan in enumerate(plans):
            work.append((scene_key, i, plan, dir_img, dir_vid, contexte_niche, niche))

    print(f"\n   🚀 {len(work)} médias à traiter (séquentiel)...\n")

    ok = 0
    for w in work:
        scene_key, i, plan, _, _, _, _ = w
        try:
            fichier = traiter_plan_unique(*w)
            plan["file_path"] = fichier
            if fichier:
                ok += 1
        except Exception as e:
            print(f"   ❌ {scene_key}/plan_{i + 1} exception : {e}")
            plan["file_path"] = ""
        # Pause courte pour respecter les rate-limits
        time.sleep(1.5)

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(visual_plan, f, indent=4, ensure_ascii=False)

    total = len(work)
    print(f"\n{'═' * 56}")
    print(f"  ✅ Fetcher terminé : {ok}/{total} médias créés")
    print(f"{'═' * 56}")


def main():
    d = trouver_dernier_projet()
    if d:
        traiter_fetcher(d)
    else:
        print("📁 Aucun projet trouvé.")
