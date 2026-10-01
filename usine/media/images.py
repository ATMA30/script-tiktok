"""Traitement d'image : normalisation 1080×1920, noir et blanc, fonds de secours."""

import os
import random
import shutil
from usine.media.config import FORCE_MONOCHROME_MEDIA, FORMATS_IMAGE, TARGET_H, TARGET_W
from usine.media.validation import image_est_trop_noire


# ═══════════════════════════════════════════════════════════════════════════════
#  NORMALISATION & NETTOYAGE
# ═══════════════════════════════════════════════════════════════════════════════
def appliquer_noir_blanc_vhs(img):
    """Convertit tout média en noir et blanc contrasté avec une texture analogique légère."""
    if not FORCE_MONOCHROME_MEDIA:
        return img
    from PIL import Image, ImageDraw, ImageEnhance

    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(1.38)
    img = ImageEnhance.Brightness(img).enhance(0.94)
    img = img.convert("RGB")

    noise = Image.effect_noise(img.size, 18).convert("L")
    img = Image.blend(img, noise.convert("RGB"), 0.055)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    for y in range(0, h, 5):
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, 24))
    for y in range(0, h, 143):
        draw.rectangle([0, y, w, y + 2], fill=(235, 235, 235, 18))
    return img


def normaliser_image(chemin_jpg: str) -> bool:
    """Force l'image à exactement TARGET_W × TARGET_H.
    L'image originale reste entière, centrée, sur une version cover floutée.
    C'est volontairement plus lisible qu'un crop-cover qui coupe le sujet.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        print("      ⚠️ PIL ou ImageFilter non installé -> skip normalisation")
        return False

    try:
        with Image.open(chemin_jpg, formats=FORMATS_IMAGE) as im:
            w, h = im.size
            # Déterminer la méthode d'échantillonnage de manière compatible PIL ancienne et moderne
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            im = im.convert("RGB")

            scale_bg = max(TARGET_W / w, TARGET_H / h)
            bg_w = int(round(w * scale_bg))
            bg_h = int(round(h * scale_bg))
            bg_resized = im.resize((bg_w, bg_h), resample_filter)
            bg_left = (bg_w - TARGET_W) // 2
            bg_top = (bg_h - TARGET_H) // 2
            bg_cropped = bg_resized.crop(
                (bg_left, bg_top, bg_left + TARGET_W, bg_top + TARGET_H)
            )
            bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=46))
            bg_blurred = bg_blurred.point(lambda px: int(px * 0.72))

            scale_fit = min(TARGET_W / w, TARGET_H / h)
            fit_w = max(1, int(round(w * scale_fit)))
            fit_h = max(1, int(round(h * scale_fit)))
            fit_resized = im.resize((fit_w, fit_h), resample_filter)

            result = Image.new("RGB", (TARGET_W, TARGET_H))
            result.paste(bg_blurred, (0, 0))
            paste_x = (TARGET_W - fit_w) // 2
            paste_y = (TARGET_H - fit_h) // 2
            result.paste(fit_resized, (paste_x, paste_y))
            result = appliquer_noir_blanc_vhs(result)
            result = ImageEnhance.Contrast(result).enhance(1.04)
            result = result.filter(
                ImageFilter.UnsharpMask(radius=1.25, percent=120, threshold=3)
            )

            result.save(chemin_jpg, format="JPEG", quality=95, optimize=True)
            print(
                f"      📐 [Center-Fit + Blur + Sharp] Normalisé : {w}×{h} → {TARGET_W}×{TARGET_H}"
            )
            return True
    except Exception as e:
        print(f"      ⚠️ Normalisation échouée : {str(e)[:100]}")
        return False


def reutiliser_media_backup(
    dir_img: str, scene_key: str, plan_index: int, chemin_jpg: str, role: str
) -> bool:
    """Réutilise une ancienne image déjà validée si l'API de génération est indisponible.
    Utile quand Imagen atteint son quota: on garde un rendu complet au lieu d'un écran noir.
    """
    projet_dir = os.path.dirname(os.path.dirname(dir_img))
    plan_name = f"plan_{plan_index + 1}.jpg"
    candidates = []
    try:
        for name in os.listdir(projet_dir):
            if not name.startswith("media_backup_"):
                continue
            p = os.path.join(projet_dir, name, "real_media", scene_key, plan_name)
            if (
                os.path.exists(p)
                and os.path.getsize(p) > 5000
                and not image_est_trop_noire(p)
            ):
                candidates.append(p)
    except Exception:
        return False

    for candidate in sorted(candidates, reverse=True):
        try:
            shutil.copy(candidate, chemin_jpg)
            normaliser_image(chemin_jpg)
            print(
                f"      ♻️  Média {role} réutilisé depuis backup -> {os.path.basename(chemin_jpg)}"
            )
            return True
        except Exception as e:
            print(f"      ⚠️ Réutilisation backup échouée : {e}")
    return False


def creer_fond_noir(chemin_jpg: str) -> bool:
    try:
        from PIL import Image as PILImage

        img = PILImage.new("RGB", (TARGET_W, TARGET_H), color=(10, 10, 10))
        img.save(chemin_jpg, format="JPEG", quality=85)
        print(f"      ⬛ Fond de secours noir créé -> {os.path.basename(chemin_jpg)}")
        return True
    except Exception:
        return False


def creer_reconstitution_locale(prompt: str, chemin_jpg: str) -> bool:
    """Dernier filet visuel quand Imagen ET Pollinations échouent.

    REWRITTEN 2026-05-26 : produit un fallback ATMOSPHÉRIQUE NEUTRE, sans
    aucune forme reconnaissable (figures, véhicules, objets). L'ancienne
    version dessinait des silhouettes + hexagones qui dominaient l'écran et
    ne ressemblaient à rien de cinématographique. La nouvelle version
    produit une image qui passe pour un still de documentaire (chiaroscuro
    + brouillard + grain photo) sans contenu spécifique — ne distrait pas,
    laisse le sous-titre et le HUD éditorial faire le boulot narratif.
    """
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFilter, ImageEnhance

        seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(prompt or "")) % 1000003
        rng = random.Random(seed)

        # Dégradé vertical profond — base "salle vide film noir"
        img = PILImage.new("RGB", (TARGET_W, TARGET_H), (8, 9, 11))
        draw = ImageDraw.Draw(img, "RGBA")
        for y in range(TARGET_H):
            t = y / TARGET_H
            # Plus sombre en haut et bas, légèrement plus clair au milieu
            mid = 1.0 - abs(0.5 - t) * 2.0
            r = int(8 + 22 * mid)
            g = int(9 + 24 * mid)
            b = int(11 + 28 * mid)
            draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b, 255))

        # Halo doux décentré (chiaroscuro spotlight)
        halo_x = rng.randint(int(TARGET_W * 0.25), int(TARGET_W * 0.75))
        halo_y = rng.randint(int(TARGET_H * 0.30), int(TARGET_H * 0.55))
        halo_r = rng.randint(380, 560)
        halo = PILImage.new("L", (TARGET_W, TARGET_H), 0)
        hd = ImageDraw.Draw(halo)
        hd.ellipse(
            [halo_x - halo_r, halo_y - halo_r, halo_x + halo_r, halo_y + halo_r],
            fill=58,
        )
        halo = halo.filter(ImageFilter.GaussianBlur(180))
        light = PILImage.new("RGB", (TARGET_W, TARGET_H), (228, 226, 218))
        img = PILImage.composite(light, img, halo)

        # Brouillard / particules — quelques poussières discrètes
        draw = ImageDraw.Draw(img, "RGBA")
        for _ in range(rng.randint(80, 160)):
            x = rng.randint(0, TARGET_W)
            y = rng.randint(int(TARGET_H * 0.15), int(TARGET_H * 0.85))
            a = rng.randint(8, 36)
            r = rng.randint(1, 3)
            draw.ellipse([x, y, x + r, y + r], fill=(255, 250, 240, a))

        # Conversion N&B + boost contraste cinéma
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(1.45)
        img = ImageEnhance.Brightness(img).enhance(0.90)
        img = img.convert("RGB")

        # Grain photo argentique léger
        noise = PILImage.effect_noise(
            (TARGET_W, TARGET_H), rng.uniform(20, 34)
        ).convert("L")
        img = PILImage.blend(img, noise.convert("RGB"), 0.12)

        # Vignette circulaire
        vignette = PILImage.new("L", (TARGET_W, TARGET_H), 0)
        vd = ImageDraw.Draw(vignette)
        vd.ellipse(
            [-220, -120, TARGET_W + 220, TARGET_H + 180],
            fill=235,
        )
        vignette = vignette.filter(ImageFilter.GaussianBlur(180))
        dark = PILImage.new("RGB", (TARGET_W, TARGET_H), (0, 0, 0))
        img = PILImage.composite(img, dark, vignette)

        img.save(chemin_jpg, "JPEG", quality=90, optimize=True)
        print(
            f"      🖼️ Reconstitution locale neutre créée -> {os.path.basename(chemin_jpg)}"
        )
        return True
    except Exception as e:
        print(f"      ⚠️ Reconstitution locale échouée : {e}")
        return False
