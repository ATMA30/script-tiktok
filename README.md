# 🎬 Usine à Vidéos — True crime & faits divers (TikTok / Shorts)

Pipeline Python qui produit des vidéos verticales documentaires (1080×1920, 60–90 s) sur des **affaires criminelles réelles** : true crime international et faits divers francophones. Chaque vidéo part d'un **brief factuel sourcé** et n'est rendue **qu'après ta validation**.

> On parle de vraies personnes. Le cerveau applique des garde-fous juridiques (présomption d'innocence, aucun mineur nommé) et refuse d'écrire sans au moins deux sources. La validation humaine reste le dernier filet.

---

## ⚡ Démarrage rapide

```bash
python 0_usine.py                          # documente une affaire, l'affiche, demande ta validation, produit la vidéo
python 0_usine.py --sujet "L'affaire Landru"
python 0_usine.py --n 3                    # enchaîne 3 dossiers
python 0_usine.py --valider projets/XXX    # valide un dossier existant et le produit
```

Avant validation, tu relis :

- le statut judiciaire ;
- les sources ;
- les points incertains ;
- les personnes volontairement non nommées ;
- la narration des 10 scènes.

Ensuite, tu choisis : **[v]alider**, **[r]égénérer** ou **[a]bandonner**.

Après la préparation des médias, une **planche-contact** des images trouvées sur le web s'ouvre. Le rendu final n'est lancé qu'une fois les images validées (aucun visage de suspect ni de mineur).

La validation est liée au contenu : modifier `script.json` après coup l'annule, et il faut revalider.

Pour rendre en lot les dossiers déjà validés :

```bash
python batch_produce.py                    # tous les projets validés sans final.mp4
python validate_project.py projets/XXX     # vérifie l'intégrité d'un projet (sans API)
```

---

## 🚀 Installation

1. **Système** : Python 3.11+, Node.js 22 (pour `npx hyperframes`), ffmpeg.
2. **Python** :

   ```bash
   pip install -r requirements.txt        # pipeline
   pip install -r requirements-dev.txt    # + pytest et ruff pour développer
   ```

3. **Configuration** : `cp .env.example .env`, puis renseigne `GEMINI_API_KEY`, la seule clé obligatoire. Les autres variables pilotent les médias et le rendu, avec leurs valeurs par défaut.

---

## 📁 Architecture

```text
0_usine.py                    Orchestrateur : cerveau → validation → production
1_generate_brain.py           Cerveau : affaire → brief sourcé → script 10 scènes (statut « a_valider »)
2_generate_audio.py           Étape 1 : voix off Gemini TTS (Enceladus/Kore), repli Edge-TTS
2.3_generate_music.py         Étape 2 : musique d'ambiance (bibliothèque ou synthèse)
2.5_director_orchestrator.py  Étape 3 : plan visuel par scène
2.7_media_fetcher.py          Étape 4 : → usine/media/  (archives DDG/Bing, Imagen 4, secours)
3_render_hyperframes.py       Étape 5 : → usine/render/ (HTML HyperFrames → final.mp4)
batch_produce.py              Rend les projets validés
validate_project.py           Contrôle d'un projet
usine/
  garde_fous.py               Présomption d'innocence, mineurs, brief sourcé
  projet.py                   Statut de validation et résumé du dossier
  render/                     Moteur de rendu (config, scènes, overlays, audio, templates/styles.css)
  media/                      Requêtes, sources, validation NSFW, téléchargements bornés, génération
assets/                       SFX, Lottie, logo et identité visuelle (assets/brand/)
tests/                        pytest + snapshots HTML du rendu
```

Un projet vit dans `projets/<horodatage_titre>/` : `brief.json` (faits et sources), `script.json` (scènes et statut de validation), `audio/`, `real_media/`, `visual_plan.json`, `final.mp4`.

---

## ✅ Qualité

```bash
ruff check . && ruff format --check .
python3 -m pytest -q                       # ni clé API ni ffmpeg requis
UPDATE_GOLDEN=1 python3 -m pytest tests/test_render_snapshot.py   # après un changement VOULU du rendu
```

---

## 🛠️ CI/CD

- `.github/workflows/ci.yml` : lint + tests à chaque push sur `main` et à chaque PR.
- `.github/workflows/render.yml` : rendu vidéo sur GitHub Actions. Il se déclenche au push d'un `script.json` dans `projets/` ou manuellement. Le secret `GEMINI_API_KEY` doit être configuré dans le dépôt.
