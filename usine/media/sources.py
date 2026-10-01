"""Téléchargement d'images réelles : DuckDuckGo, Bing, sources curées, stock Pexels/Pixabay."""

import html
import os
import random
import re
import requests
import urllib.parse
from usine.media.config import (
    CURATED_CASE_IMAGES,
    DDG_TIMEOUT,
    MAX_BING_RESULTS,
    MAX_DDG_QUERIES_PER_PLAN,
    MAX_DDG_RESULTS,
    PEXELS_API_KEY,
    PIXABAY_API_KEY,
    STRICT_REAL_VALIDATION,
    TRUST_CURATED_SOURCES,
)
from usine.media.queries import construire_requetes_reelles, enrichir_requete_archive
from usine.media.validation import (
    url_est_suspecte,
    valider_image_historique,
    verifier_securite_image,
)

USED_SOURCE_URLS = set()
DDG_RESULT_CACHE = {}


def telecharger_image_url(img_url: str, chemin_jpg: str, label: str = "") -> bool:
    canonical = re.sub(r"[?#].*$", "", img_url)
    if canonical in USED_SOURCE_URLS:
        print(f"      ↪️  Source déjà utilisée, on varie : {img_url[:70]}")
        return False
    if url_est_suspecte(img_url):
        print(f"      🚫 URL bloquée (domaine suspect) : {img_url[:70]}")
        return False
    try:
        resp = requests.get(
            img_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "image/jpeg,image/png,image/webp,image/apng,image/*,*/*;q=0.8",
            },
            timeout=25,
            stream=True,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get("Content-Type", "").lower()
        if not any(
            t in content_type
            for t in ["image/jpeg", "image/png", "image/jpg", "image/webp"]
        ):
            print(f"      ⚠️ Source curated non-image ({content_type[:40]}) — ignorée")
            return False
        with open(chemin_jpg, "wb") as f:
            for chunk in resp.iter_content(32768):
                f.write(chunk)
        if os.path.getsize(chemin_jpg) < 8000:
            os.remove(chemin_jpg)
            return False
        USED_SOURCE_URLS.add(canonical)
        print(f"      📚 Source curated téléchargée ({label or 'image'})")
        return True
    except Exception as e:
        print(f"      ⚠️ Échec source curated {label or img_url[:40]} : {e}")
        if os.path.exists(chemin_jpg):
            os.remove(chemin_jpg)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  TÉLÉCHARGEMENT VIDÉOS DE STOCK (PEXELS PORTRAIT)
# ═══════════════════════════════════════════════════════════════════════════════
def telecharger_pexels_video(query: str, chemin_mp4: str) -> bool:
    """Recherche et télécharge une vidéo portrait libre de droits sur Pexels."""
    if not PEXELS_API_KEY:
        return False
    try:
        clean_q = re.sub(r"[^\w\s]", " ", query).strip()
        url = f"https://api.pexels.com/videos/search?query={clean_q}&per_page=5&orientation=portrait"
        print(f"      🔍 Pexels Video Search : '{clean_q}'")
        r = requests.get(
            url, headers={"Authorization": PEXELS_API_KEY}, timeout=15
        ).json()
        videos = r.get("videos", [])
        if videos:
            video = videos[0]
            files = video.get("video_files", [])
            best_link = None

            # Cherche un fichier MP4 au format portrait
            for vf in files:
                if vf.get("file_type") == "video/mp4":
                    link = vf.get("link")
                    w = vf.get("width", 0)
                    h = vf.get("height", 0)
                    if link and h > w:
                        best_link = link
                        break
            # Fallback sur le premier lien MP4 si pas de format portrait strict
            if not best_link and files:
                for vf in files:
                    if vf.get("file_type") == "video/mp4" and vf.get("link"):
                        best_link = vf.get("link")
                        break

            if best_link:
                resp = requests.get(best_link, timeout=45, stream=True)
                if resp.status_code == 200:
                    with open(chemin_mp4, "wb") as f:
                        for chunk in resp.iter_content(65536):
                            f.write(chunk)
                    if os.path.getsize(chemin_mp4) > 50000:
                        print(
                            f"      🎥 [Pexels Video] Vidéo téléchargée -> {os.path.basename(chemin_mp4)}"
                        )
                        return True
    except Exception as e:
        print(f"      ⚠️ Échec téléchargement vidéo Pexels pour '{query}' : {e}")
    return False


def telecharger_pexels_image(query: str, chemin: str) -> bool:
    if not PEXELS_API_KEY:
        return False
    try:
        r = requests.get(
            f"https://api.pexels.com/v1/search?query={query}&per_page=10&orientation=portrait",
            headers={"Authorization": PEXELS_API_KEY},
            timeout=15,
        ).json()
        photos = r.get("photos", [])
        if photos:
            url = random.choice(photos)["src"]["large2x"]
            resp = requests.get(url, timeout=30, stream=True)
            if resp.status_code == 200:
                with open(chemin, "wb") as f:
                    for chunk in resp.iter_content(32768):
                        f.write(chunk)
                if os.path.getsize(chemin) > 5000:
                    print(
                        f"      🖼️ [Pexels Image] Téléchargée -> {os.path.basename(chemin)}"
                    )
                    return True
    except Exception as e:
        print(f"      ⚠️ Pexels Image : {e}")
    return False


def telecharger_pixabay_image(query: str, chemin: str) -> bool:
    if not PIXABAY_API_KEY:
        return False
    try:
        r = requests.get(
            f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}"
            f"&image_type=photo&orientation=vertical&per_page=10",
            timeout=15,
        ).json()
        hits = r.get("hits", [])
        if hits:
            url = random.choice(hits).get("largeImageURL", "")
            resp = requests.get(url, timeout=30, stream=True)
            if resp.status_code == 200:
                with open(chemin, "wb") as f:
                    for chunk in resp.iter_content(32768):
                        f.write(chunk)
                if os.path.getsize(chemin) > 5000:
                    print(
                        f"      🖼️ [Pixabay Image] Téléchargée -> {os.path.basename(chemin)}"
                    )
                    return True
    except Exception as e:
        print(f"      ⚠️ Pixabay Image : {e}")
    return False


def telecharger_bing_image(
    query: str,
    chemin_jpg: str,
    contexte_niche: str = "",
    context_histoire: str = "",
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Recherche et télécharge une image réelle depuis Bing Images avec SafeSearch strict et validation IA en 2 phases."""
    if MAX_BING_RESULTS <= 0:
        return False
    try:
        search_query = enrichir_requete_archive(query, contexte_niche)

        print(f"      🔍 Recherche Bing Image : '{search_query}'")
        # SafeSearch=Strict obligatoire + filtre de taille moyenne ou large
        url = (
            f"https://www.bing.com/images/search"
            f"?q={urllib.parse.quote(search_query)}"
            f"&safeSearch=Strict"
            f"&first=1"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": "SRCHHPGUSR=ADLT=STRICT",  # Force SafeSearch côté cookie également
        }
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return False

        decoded = html.unescape(r.text)
        urls = re.findall(r'"murl":"(https?://[^"]+)"', decoded)
        if not urls:
            return False

        attempts_tested = 0
        for img_url in urls[:MAX_BING_RESULTS]:
            try:
                # ── Filtre 1 : Extension et domaines suspects connus (sans téléchargement) ──
                if any(
                    x in img_url.lower()
                    for x in [".gif", ".webp", "doubleclick", "adsystem"]
                ):
                    continue
                if url_est_suspecte(img_url):
                    print(f"      🚫 URL bloquée (domaine suspect) : {img_url[:60]}")
                    continue

                attempts_tested += 1
                print(
                    f"      📥 [Essai {attempts_tested}] Téléchargement : {img_url[:70]}..."
                )
                resp = requests.get(
                    img_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                    timeout=10,
                    stream=True,
                )
                if resp.status_code != 200:
                    continue

                # Vérifier le Content-Type avant d'écrire
                content_type = resp.headers.get("Content-Type", "")
                if not any(
                    t in content_type
                    for t in ["image/jpeg", "image/png", "image/jpg", "image/webp"]
                ):
                    print(
                        f"      ⚠️ Content-Type non-image ({content_type[:30]}) — ignoré"
                    )
                    continue

                with open(chemin_jpg, "wb") as f:
                    for chunk in resp.iter_content(32768):
                        f.write(chunk)

                if os.path.getsize(chemin_jpg) < 15000:
                    # Image trop petite (miniature ou erreur)
                    os.remove(chemin_jpg)
                    continue

                # ── Filtre 2 : Validation IA en 2 phases (NSFW + Pertinence) ──
                if valider_image_historique(
                    chemin_jpg,
                    context_histoire or query,
                    search_query,
                    scene_text,
                    veo_prompt,
                ):
                    print(
                        f"      ✅ [Real Photo] Validée -> {os.path.basename(chemin_jpg)}"
                    )
                    return True
                else:
                    if os.path.exists(chemin_jpg):
                        os.remove(chemin_jpg)
                    print("      ↩️  Rejetée, on essaie la suivante...")

            except Exception as e:
                print(f"      ⚠️ Échec pour {img_url[:50]} : {e}")
                if os.path.exists(chemin_jpg):
                    os.remove(chemin_jpg)

    except Exception as e:
        print(f"      ⚠️ Erreur recherche Bing pour '{query}' : {e}")
    return False


def _ddg_vqd(session: requests.Session, query: str) -> str:
    r = session.get(
        "https://duckduckgo.com/",
        params={"q": query, "iax": "images", "ia": "images"},
        timeout=DDG_TIMEOUT,
    )
    if r.status_code not in (200, 202):
        return ""
    m = (
        re.search(r'vqd="([^"]+)"', r.text)
        or re.search(r"vqd='([^']+)'", r.text)
        or re.search(r"vqd=([^&]+)&", r.text)
    )
    return m.group(1) if m else ""


def _ddg_image_results(session: requests.Session, search_query: str) -> list:
    """Retourne les résultats DDG avec cache court pour éviter de refaire la même recherche."""
    cache_key = search_query.lower().strip()
    if cache_key in DDG_RESULT_CACHE:
        return DDG_RESULT_CACHE[cache_key]

    vqd = _ddg_vqd(session, search_query)
    if not vqd:
        DDG_RESULT_CACHE[cache_key] = []
        return []

    r = session.get(
        "https://duckduckgo.com/i.js",
        params={
            "l": "us-en",
            "o": "json",
            "q": search_query,
            "vqd": vqd,
            "f": ",,,",
            "p": "1",
            "u": "bing",
        },
        timeout=DDG_TIMEOUT,
    )
    if r.status_code != 200:
        DDG_RESULT_CACHE[cache_key] = []
        return []

    results = r.json().get("results", [])[:MAX_DDG_RESULTS]
    DDG_RESULT_CACHE[cache_key] = results
    return results


def telecharger_duckduckgo_image(
    query: str,
    chemin_jpg: str,
    contexte_niche: str = "",
    context_histoire: str = "",
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Recherche DuckDuckGo Images. Souvent meilleur que Bing pour les cas documentaires."""
    search_queries = construire_requetes_reelles(
        query, scene_text, contexte_niche, context_histoire
    )[:MAX_DDG_QUERIES_PER_PLAN]
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    )

    for search_query in search_queries:
        try:
            print(f"      🦆 Recherche DDG Image : '{search_query}'")
            results = _ddg_image_results(session, search_query)
            for idx, result in enumerate(results, 1):
                img_url = result.get("image") or result.get("thumbnail") or ""
                if not img_url or url_est_suspecte(img_url):
                    continue
                print(f"      📥 [DDG {idx}] {result.get('title', '')[:70]}...")
                if not telecharger_image_url(img_url, chemin_jpg, "DDG image"):
                    continue
                if (not STRICT_REAL_VALIDATION) or valider_image_historique(
                    chemin_jpg,
                    context_histoire or query,
                    search_query,
                    scene_text,
                    veo_prompt,
                ):
                    print(
                        f"      ✅ [DDG Real Photo] Validée -> {os.path.basename(chemin_jpg)}"
                    )
                    return True
                if os.path.exists(chemin_jpg):
                    os.remove(chemin_jpg)
                print("      ↩️  DDG rejetée, on essaie la suivante...")
        except Exception as e:
            print(f"      ⚠️ Erreur DDG pour '{search_query}' : {e}")
            if os.path.exists(chemin_jpg):
                os.remove(chemin_jpg)
    return False


def telecharger_source_curated(
    query: str,
    chemin_jpg: str,
    contexte_niche: str = "",
    context_histoire: str = "",
    scene_text: str = "",
    veo_prompt: str = "",
) -> bool:
    """Essaie d'abord quelques sources connues pour une affaire précise.

    Scoring pondéré: la requête et le texte du sous-titre (ce qui est dit à l'écran)
    pèsent beaucoup plus que le veo_prompt (ambiance générique de la scène). Un
    candidat dont aucun keyword ne touche la query OU le scene_text est rejeté:
    c'est ce qui faisait gagner "snow mountain" face à "Mercury Montego" pour un
    sous-titre qui parle explicitement de la voiture.
    """
    q_str = (query or "").lower()
    scene_str = (scene_text or "").lower()
    veo_str = re.sub(
        r"\[STYLE LOCK[^\]]*\]", "", (veo_prompt or ""), flags=re.IGNORECASE
    ).lower()
    niche_str = (contexte_niche or "").lower()
    hist_str = (context_histoire or "").lower()
    haystack = " ".join([q_str, scene_str, veo_str, niche_str, hist_str])

    if any(
        token in haystack
        for token in (
            "yuba",
            "madruga",
            "mathias",
            "weiher",
            "sterling",
            "huett",
            "plumas",
            "montego",
        )
    ):
        case_key = "yuba"
    elif "enfield" in haystack:
        case_key = "enfield"
    else:
        case_key = ""
    if not case_key:
        return False

    candidates = []
    for item in CURATED_CASE_IMAGES.get(case_key, []):
        kws = item["keywords"]
        # Poids éditoriaux : query >> scene_text > veo_prompt >> contexte global.
        hits_query = sum(1 for kw in kws if kw in q_str)
        hits_scene = sum(1 for kw in kws if kw in scene_str)
        hits_veo = sum(1 for kw in kws if kw in veo_str)
        hits_ctx = sum(1 for kw in kws if kw in niche_str or kw in hist_str)
        score = hits_query * 5 + hits_scene * 3 + hits_veo * 1 + hits_ctx * 1

        # Garde-fou : si la query ET le scene_text mentionnent un sujet précis
        # (voiture / personne / lieu / objet), un candidat sans aucun mot du
        # sujet est rejeté, même si son ambiance matche le veo_prompt.
        subject_match = (hits_query > 0) or (hits_scene > 0)
        if not subject_match:
            continue
        candidates.append((score, hits_query, hits_scene, item))

    if not candidates:
        # Aucun candidat ne matche le sujet : on n'invente pas, on laisse le
        # pipeline tomber sur DDG/Bing/Imagen au lieu de poser une image hors-sujet.
        print(
            "      ⛔ Aucune source curated ne matche le sujet de la requête/sous-titre"
        )
        return False

    # Tri: (score total, hits_query, hits_scene) tous décroissants.
    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    for score, hits_q, hits_s, item in candidates[:10]:
        print(
            f"      📚 Source curated : {item['label']} (score={score} q={hits_q} s={hits_s})"
        )
        if not telecharger_image_url(item["url"], chemin_jpg, item["label"]):
            continue
        # 1) Sécurité NSFW : non négociable.
        if not verifier_securite_image(chemin_jpg):
            if os.path.exists(chemin_jpg):
                os.remove(chemin_jpg)
            print("      ↩️  Source curated rejetée par sécurité")
            continue
        # 2) Pertinence Gemini : on n'a plus le droit de trust aveugle, car le
        # vrai bug du projet Yuba venait d'un keyword "snow/mountain" qui matchait
        # un paysage sans voiture pour un sous-titre qui parlait de la Montego.
        if STRICT_REAL_VALIDATION and not TRUST_CURATED_SOURCES:
            if not valider_image_historique(
                chemin_jpg, context_histoire or query, query, scene_text, veo_prompt
            ):
                if os.path.exists(chemin_jpg):
                    os.remove(chemin_jpg)
                print("      ↩️  Source curated rejetée par pertinence Gemini")
                continue
        print(
            f"      ✅ [Curated Real Photo] Validée -> {os.path.basename(chemin_jpg)}"
        )
        return True

    return False
