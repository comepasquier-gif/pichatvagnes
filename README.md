# PiChat 3.5 PERFORMANCE

PiChat 3.5 PERFORMANCE est la mise à jour de PiChat 3.4 FREE ONLINE pour un déploiement public simple sur Render, avec PostgreSQL, PWA, WebSocket et une nouvelle identité PiChat/Chavagnes.

## Ce que la 3.5 conserve

Aucune fonction métier de la 3.4 n'est supprimée : chat temps réel, salons, messages privés, amis, profils, profils gaming, rôles joueur/modo/admin, permissions modérateurs, AutoModo, anti-spam, signalements, PyCoins, services, Arcade, mini-jeux, PiTutor+, PiGame Studio, imports HTML/CSS/JS/JSON/ZIP, API IA configurable, backups, administration, PWA/mobile, commandes admin, Centre PRO, diagnostic, recherche et page de statut.

## Nouveautés 3.5

- **PiChat 3.5 PERFORMANCE** : nouvelle couche graphique homogène connexion/chat/admin/mobile.
- Nouvelle mascotte robot-chat et logo PiChat Chavagnes dans `frontend/assets/brand/`.
- Nouvelles icônes PWA générées à partir de la mascotte.
- **Mini Bot vivant** avec 48 états référencés et états automatiques (idle, écriture, reconnexion, erreur, succès, admin, PiGame, PiTutor, taps, danse…).
- **Ping Monitor** HTTP + WebSocket, avec objectif visuel `< 50 ms`.
- Ping WebSocket traité sans requête base afin de mesurer le RTT du canal temps réel avec un minimum de surcharge.
- Cache PWA `pichat-v3-3500` entièrement renouvelé pour éliminer le cache 3.4 obsolète.
- App shell PWA réduit : installation plus rapide, gros modules mis en cache à la demande.
- **Bundles PERFORMANCE** : le chat passe de 17 CSS + 19 JS à 1 CSS + 1 JS ; l’admin de 21 CSS + 20 JS à 1 CSS + 1 JS, tout en conservant les sources séparées pour compatibilité.
- Assets `?v=3500` servis avec cache immutable.
- Header `Server-Timing` pour diagnostiquer le temps serveur.
- Migration `350001` : mode performance, objectif ping et version du branding.
- Compatible avec la base PostgreSQL Render déjà créée en 3.4.

## Déploiement existant Render : NE PAS recréer la base

Pour passer d'une instance 3.4 déjà en ligne à 3.5 :

1. **Admin → Sauvegardes → Nouveau backup**.
2. Remplacer le code du dépôt GitHub par la 3.5, sans ajouter de `venv`, `.env`, base SQLite ou backup privé.
3. Commit + Push sur la branche `main`.
4. Render redéploie automatiquement `pichat-free-online`.
5. Au démarrage, la migration `350001` est appliquée automatiquement.
6. Les utilisateurs, messages, PyCoins, amis, salons, profils, jeux et réglages restent dans PostgreSQL.

Ne supprimez pas `pichat-db` et ne changez pas `PICHAT_SECRET_KEY`.

## Ping < 50 ms

Le chiffre affiché est une mesure de RTT depuis le navigateur. Vert = objectif atteint (`≤ 50 ms`), orange = latence correcte, rouge = latence élevée. PiChat réduit sa propre surcharge, mais la distance utilisateur ↔ datacenter et la connexion Internet restent hors du contrôle de l'application.

## Démarrage local

Python 3.9 minimum.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export PICHAT_SETUP_MODE=1
export PICHAT_SECRET_KEY='une-cle-longue-et-aleatoire'
uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Puis ouvrir `http://localhost:8000/setup`.

## Fichiers importants

- `Dockerfile` : Docker Render, avec `PYTHONPATH=/app:/app/backend`.
- `render.yaml` : Blueprint Render + PostgreSQL.
- `migrations/versions/v350001_performance_brand.py` : migration 3.5.
- `frontend/css/brand35.css` : couche graphique 3.5 + Mini Bot.
- `frontend/js/brand35.js` : marque + états du Mini Bot.
- `frontend/js/performance35.js` : mesure et affichage du ping.
- `frontend/service-worker.js` : cache PWA 3.5.
- `GUIDE_DEPLOIEMENT.md` et `MISE_A_JOUR_3.5_RAPIDE.md`.

## Sécurité

Les mots de passe restent hashés. Les clés API restent côté serveur et chiffrées. Les backups exportables excluent les secrets d'API, sessions et tentatives de connexion. Les jeux restent exécutés dans leur sandbox PiGame.
