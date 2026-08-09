# PiChat 3.5 PERFORMANCE — Déploiement Render

## Mise à jour d'une instance 3.4 déjà en ligne

**Ne recrée pas Render et ne recrée pas PostgreSQL.**

1. Dans PiChat : `Admin → Sauvegardes` et crée un backup.
2. Remplace le code du dépôt GitHub par PiChat 3.5 PERFORMANCE.
3. Commit puis Push sur la branche `main`.
4. Render redéploie automatiquement `pichat-free-online`.
5. Au démarrage, la migration `350001` est appliquée.
6. Ouvre `/api/health`, puis `Admin → Mise en ligne`.
7. Fais un rechargement forcé du navigateur une fois (`⌘⇧R` sur Mac) : le service worker 3.5 supprime les anciens caches.

La base Render existante et `PICHAT_SECRET_KEY` doivent être conservées : les comptes, messages, PyCoins, profils, salons, jeux et réglages restent en place.

## Nouveau déploiement

1. Mettre les fichiers sur GitHub, avec `render.yaml` à la racine.
2. Render → **New → Blueprint**.
3. Sélectionner le dépôt.
4. Déployer le Blueprint.
5. Ouvrir l'URL HTTPS fournie par Render puis `/setup`.
6. Créer le propriétaire. `/setup` se verrouille ensuite côté serveur.

## Performance 3.5

PiChat 3.5 ajoute :
- ping WebSocket direct sans requête base ;
- fallback HTTP `/api/ping` sans accès base ;
- bundles CSS/JS pour les deux écrans les plus lourds (chat et admin) ;
- compression GZip ;
- cache immutable des assets `?v=3500` ;
- service worker 3.5 nettoyant les caches précédents ;
- mesure de la médiane des dernières latences.

**Objectif d'affichage : moins de 50 ms.** Ce seuil est une cible et non une garantie : la connexion de l'utilisateur, la distance au datacenter et un éventuel réveil du service d'hébergement comptent aussi.

## Variables importantes

- `DATABASE_URL` : PostgreSQL
- `PICHAT_SECRET_KEY` : secret de l'instance — à conserver lors des mises à jour
- `PICHAT_STORAGE_BACKEND=database` ou stockage S3 compatible
- `PICHAT_COOKIE_SECURE=1` en HTTPS
- `PICHAT_INTERNET_MODE=1`
- `PICHAT_TRUST_PROXY=1`
- `PICHAT_SETUP_MODE=1`

## Contrôle rapide

- `/api/health` → `ok: true`
- `/api/ping` → `target_ms: 50`
- page de connexion stylée PiChat 3.5
- indicateur de ping visible
- WebSocket connecté dans le chat
- migration `350001` enregistrée dans `schema_migrations`
