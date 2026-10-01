"""
2.7_media_fetcher.py — SMART REAL/GENERATED MEDIA MIX

Pipeline prioritaire pour chaque plan visuel :
  1. Décision éditoriale par plan : archive réelle ou reconstitution générée
  2. Pour les archives : DuckDuckGo Images + Bing Images + sources curated
  3. Pour les reconstitutions : Imagen 4.0 avec prompt sécurisé
  4. Stock Pexels/Pixabay uniquement si ALLOW_STOCK_FALLBACKS=1
  5. Fond noir générique (dernier recours pour débloquer le pipeline)

Toutes les images sont normalisées en 1080×1920 avec image entière centrée
sur fond flouté. On évite les crop-cover destructeurs.
"""
