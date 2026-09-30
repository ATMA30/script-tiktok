# 🎬 Usine à Vidéos - Pipeline TikTok / Shorts Automatisé

**Mode principal actuel : SÉRIE DRAMATIQUE à la 1ʳᵉ personne.**
Le projet génère des histoires dramatiques 100% originales (pouvoir, argent, amour, trahison, vengeance), racontées à la première personne par le narrateur-héros, découpées en une **série de N épisodes courts** (60–90 s) pour TikTok / YouTube Shorts. La génération suit un **workflow de validation obligatoire en deux phases** (synopsis → épisode par épisode). Le rendu vidéo réutilise l'infra existante (Gemini TTS, Imagen/Pollinations, Whisper, moteur HyperFrames).

> Le mode historique **True Crime / Paranormal documentaire** reste sur le disque mais est débranché du flow principal (voir « Mode legacy » plus bas).

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
# … puis rendu via l'infra existante
python batch_produce.py            # détecte les projets/épisodes sans final.mp4
```

Chaque épisode validé est écrit comme un **projet standard** dans `projets/<serie>_ep0N_.../script.json` (même format que l'ancien pipeline) ; `batch_produce.py` le rend sans modification. La `visual_bible` est **partagée** entre tous les épisodes pour la cohérence visuelle.

### Mode legacy (true-crime documentaire)
```bash
python 0_usine.py --legacy-truecrime 3   # ancien pipeline auto, 3 vidéos
```

---

## 📖 Contexte historique (true-crime)

Le pipeline d'origine générait des vidéos documentaires verticales axées sur le True Crime et le Paranormal, utilisant l'IA (Gemini, Imagen, Whisper) et un moteur de rendu ultra-rapide basé sur le framework HTML HyperFrames.

---

## 📁 Architecture du Code (Nettoyée)

Le projet a été nettoyé de ses composants obsolètes (`moviepy` et scripts Whisper lourds locaux) au profit d'un pipeline modulaire, rapide et optimisé pour le Cloud (CI/CD).

```
.
├── 0_serie.py                      # ★ Orchestrateur PRINCIPAL — série dramatique (validation 2 phases)
├── 1_generate_serie.py             # ★ Cerveau série : synopsis + épisodes (fiction 1ʳᵉ personne)
├── 0_usine.py                      # Entrée legacy → délègue à 0_serie.py (ou --legacy-truecrime)
├── batch_produce.py                # Exécuteur batch pour produire plusieurs vidéos
├── 1_generate_brain.py             # [LEGACY] Étape 1 true-crime : scénario factuel via Gemini API
├── 2_generate_audio.py             # Étape 2 : Voix off via Gemini TTS (Enceladus) / Edge-TTS
├── 2.3_generate_music.py           # Étape 3 : Sélection musique locale ou synthèse de drones audio
├── 2.5_director_orchestrator.py    # Étape 4 : Découpage et synchronisation sémantique des plans
├── 2.7_media_fetcher.py            # Étape 5 : Récupération d'images réelles (Bing/DDG) et Imagen 4.0
├── 3_render_hyperframes.py         # Étape 6 : Rendu final MP4 via HyperFrames (Chromium Headless)
├── utils.py                        # Fonctions utilitaires partagées
└── validate_project.py             # Script de validation locale de l'intégrité d'un projet
```

### Outils Annexes
* `download_voice_sample.py` : Utilitaire d'extraction de voix YouTube pour l'entraînement / clonage de voix.
* `test_gemini_voice.py` : Script de test d'API pour la voix Gemini TTS.

---

## 🚀 Démarrage Rapide

### 1. Installation des dépendances
Installez les dépendances système requises pour le rendu Chromium Headless et FFmpeg, puis installez les dépendances Python :

```bash
pip install -r requirements.txt
```

### 2. Configuration (`.env`)
Copiez le fichier d'exemple et configurez votre clé API Gemini :

```bash
cp .env.example .env
```
*Note : Référez-vous à `.env.example` pour la liste complète des variables permettant de contrôler le rendu (noir et blanc, transitions, volumes, etc.).*

### 3. Exécution

Pour lancer le pipeline complet étape par étape en mode interactif :
```bash
python3 0_usine.py
```

Pour valider le format des fichiers et l'intégrité du dernier projet produit :
```bash
python3 validate_project.py
```

---

## 🛠️ Configuration CI/CD (GitHub Actions)

Le workflow `.github/workflows/render.yml` permet de déporter le rendu vidéo lourd sur GitHub Actions.
Il se déclenche automatiquement à chaque push d'un fichier `script.json` dans un dossier projet ou manuellement depuis l'onglet Actions de GitHub.
