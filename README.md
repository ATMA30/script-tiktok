# 🎬 Usine à Vidéos - Pipeline TikTok / Shorts Automatisé

**Mode principal actuel : SÉRIE DRAMATIQUE à la 1ʳᵉ personne.**
Le projet génère des histoires dramatiques 100% originales (pouvoir, argent, amour, trahison, vengeance), racontées à la première personne par le narrateur-héros, découpées en une **série de N épisodes courts** (60–90 s) pour TikTok / YouTube Shorts. La génération suit un **workflow de validation obligatoire en deux phases** (synopsis → épisode par épisode). Le rendu vidéo s'appuie sur Gemini TTS, Imagen 4, Whisper et le moteur HTML HyperFrames.

> Le mode historique **True Crime / Paranormal documentaire** reste disponible mais est débranché du flow principal (voir « Mode legacy » plus bas).

---

## ⚡ Démarrage rapide — Série dramatique

```bash
# Orchestrateur interactif (workflow de validation en 2 phases)
python 0_serie.py
```

Ou en ligne de commande, étape par étape (le synopsis doit être validé avant tout épisode) :

```bash
# PHASE 1 — synopsis (s'arrête pour validation)
python 1_generate_serie.py synopsis --episodes 8 --sujet "Ma sœur est morte il y a dix ans. Hier, elle a liké ma photo."
# GATE — accord humain explicite
python 1_generate_serie.py valider
# PHASE 2 — un épisode à la fois (refuse de tourner si non validé)
python 1_generate_serie.py episode 1
python 1_generate_serie.py episode 2
# … puis rendu
python batch_produce.py            # détecte les projets/épisodes sans final.mp4
```

Chaque épisode validé est écrit comme un **projet standard** dans `projets/<serie>_ep0N_.../script.json` ; `batch_produce.py` le rend sans modification. La `visual_bible` est **partagée** entre tous les épisodes pour la cohérence visuelle.

### Mode legacy (true-crime documentaire)

```bash
python 0_usine.py --legacy-truecrime 3   # ancien pipeline auto, 3 vidéos
```

---

## 🚀 Installation

1. **Dépendances système** : Python 3.11+, Node.js 22 (pour `npx hyperframes`), ffmpeg.
2. **Dépendances Python** :

   ```bash
   pip install -r requirements.txt        # pipeline
   pip install -r requirements-dev.txt    # + pytest et ruff pour développer
   ```

3. **Configuration** : copiez `.env.example` en `.env` et renseignez `GEMINI_API_KEY` (seule clé obligatoire). Les autres variables pilotent le rendu (overlays, transitions, volumes…).

Pour valider l'intégrité du dernier projet produit, sans appel API :

```bash
python validate_project.py
```

---

## 📁 Architecture du code

Les scripts numérotés sont les **points d'entrée** du pipeline, enchaînés par `batch_produce.py`. Les deux étapes les plus lourdes (médias et rendu) sont de simples enveloppes : leur code vit dans le package `usine/`.

```text
.
├── 0_serie.py                      # ★ Orchestrateur PRINCIPAL — série dramatique (validation 2 phases)
├── 0_trend_picker.py               # Suggestions de prémisses d'après les tendances YouTube
├── 0_usine.py                      # Entrée legacy → délègue à 0_serie.py (ou --legacy-truecrime)
├── 1_generate_serie.py             # ★ Cerveau série : synopsis + épisodes (fiction 1ʳᵉ personne)
├── 1_generate_brain.py             # [LEGACY] Scénario true-crime factuel via Gemini
├── 2_generate_audio.py             # Étape 1 : voix off Gemini TTS (Enceladus/Kore), repli Edge-TTS
├── 2.3_generate_music.py           # Étape 2 : musique locale ou synthèse de drones
├── 2.5_director_orchestrator.py    # Étape 3 : découpage et plan visuel par scène
├── 2.7_media_fetcher.py            # Étape 4 : → usine/media/  (images réelles DDG/Bing ou Imagen 4)
├── 3_render_hyperframes.py         # Étape 5 : → usine/render/ (HTML HyperFrames → final.mp4)
├── batch_produce.py                # Rend tous les projets sans final.mp4
├── validate_project.py             # Vérifie l'intégrité d'un projet (sans API)
├── usine/
│   ├── render/                     # Moteur de rendu : config, scènes, overlays, audio, template
│   │   └── templates/styles.css    # CSS de la vidéo
│   └── media/                      # Media fetcher : requêtes, sources, validation, génération
├── assets/                         # SFX, bibliothèque Lottie, logo et identité visuelle
├── series/                         # Synopsis des séries (serie.json)
└── tests/                          # pytest + snapshots HTML du rendu
```

---

## ✅ Qualité

```bash
ruff check . && ruff format --check .    # lint + formatage
python3 -m pytest -q                     # tests (ni clé API ni ffmpeg requis)
```

Le test `tests/test_render_snapshot.py` compare le HTML généré à une référence : toute modification du rendu le fait échouer. Si le changement est voulu, régénérez la référence :

```bash
UPDATE_GOLDEN=1 python3 -m pytest tests/test_render_snapshot.py
```

---

## 🛠️ CI/CD (GitHub Actions)

- `.github/workflows/ci.yml` : lint + tests à chaque push sur `main` et à chaque PR.
- `.github/workflows/render.yml` : déporte le rendu vidéo lourd sur GitHub Actions. Il se déclenche à chaque push d'un `script.json` dans `projets/`, ou manuellement depuis l'onglet Actions. Le secret `GEMINI_API_KEY` doit être configuré dans le dépôt.
