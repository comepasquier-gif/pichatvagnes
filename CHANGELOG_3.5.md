# Changelog PiChat 3.5.0 PERFORMANCE

## Interface
- Nouveau branding PiChat / Chavagnes.
- Connexion et inscription reconstruites avec une couche CSS autonome afin d'éviter l'affichage brut observé en 3.4.
- Mini Bot animé et interactif.
- Nouvelle icône PWA mascotte.
- Couche visuelle 3.5 compatible dark, AMOLED, light, Discord, Neon et personnalisation existante.

## Performance
- Ping `/api/ping` ultra-léger.
- Ping WebSocket natif sur `/ws`, sans hit DB pour chaque mesure.
- Objectif visuel 50 ms et médiane glissante des dernières mesures.
- `Server-Timing` sur les réponses.
- Cache immutable pour les assets versionnés 3.5.
- Service worker allégé et cache namespace renouvelé.
- Bundles `chat35.bundle.*` et `admin35.bundle.*` afin de réduire fortement le nombre de requêtes au premier affichage.
- GZip activé pour les réponses textuelles suffisamment grandes.

## Données
- Migration `350001` automatique et idempotente.
- Aucun reset de base.
- PostgreSQL Render 3.4 conservé.

## Déploiement
- Dockerfile Render conserve `PYTHONPATH=/app:/app/backend` afin que `migrations` soit importable.

## 3.6.0 — OPEN ARENA
- Ajout de PiBrawl Arena, mini arena-shooter original en Canvas, clavier/souris + tactile.
- PiChat est le premier combattant, avec attaque courte portée en éventail et Super à recul.
- Système de personnages auto-découvert dans `personnages/`.
- `fighter.py` déclaratif et analysé par AST : aucun Python arbitraire exécuté sur le serveur.
- Ajout de `render-europe.yaml` : Web Service + PostgreSQL à Frankfurt pour réduire le ping en France.
- Nouvelle route `/pibrawl` et API `/api/pibrawl/roster`.
