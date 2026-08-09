# PiChat 3.4 FREE ONLINE

PiChat 3.4 FREE ONLINE est la branche de PiChat conçue pour être déployée par un particulier sur un hébergeur moderne, sans laisser un Mac allumé et sans tunnel Cloudflare.

## Ce que conserve la 3.4

La base 3.3.1 reste présente : chat temps réel WebSocket, salons, messages privés, amis, profils, profils gaming, rôles joueur/modo/admin, permissions personnalisables, AutoModo, anti-spam, signalements, PyCoins, services, Arcade, mini-jeux, PiTutor/PiTutor+, PiGame Studio, import de jeux, IA configurable, sauvegardes, administration, PWA/mobile, commandes admin, Centre PRO, diagnostic, recherche et page de statut.

Les anciens assistants de tunnel/Railway sont conservés comme outils **legacy** en mode avancé, mais ne sont plus requis par le déploiement FREE ONLINE.

## Nouveautés 3.4

- PostgreSQL via `DATABASE_URL`, avec compatibilité SQLite locale.
- Migrations versionnées et automatiques au démarrage.
- Assistant `/setup` pour créer le premier propriétaire ; verrouillage serveur après initialisation.
- Stockage des uploads en base (`database`) ou objet compatible S3 (`s3`) ; le disque temporaire n'est pas la source de vérité.
- Backup portable v2 stocké en base, restauration et contrôle d'intégrité ; secrets/sessions exclus des exports.
- Gestionnaire Admin > Intégrations : nom, fournisseur, clé, modèle, test, activation/désactivation, suppression.
- Clés API chiffrées côté serveur avec `PICHAT_SECRET_KEY`, jamais retournées intégralement.
- Dashboard PRO et panneau **Mise en ligne** avec score /100.
- PiGame Studio : HTML, CSS, JS, JSON et ZIP ; pipeline validation/sandbox/preview/validation admin/publication.
- API PiGame limitée : pseudo, niveau, solde PyCoins en lecture, score, classement et succès. Aucun token n'est fourni à l'iframe.
- Thèmes PiChat Dark, AMOLED, Light, Discord, Neon + couleurs personnalisables.
- Durcissement HTTP : cookies HttpOnly/Secure, SameSite, vérification d'origine CSRF, rate limiting, anti brute-force durable, contrôles MIME/uploads.

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

## Déploiement

Le chemin le plus simple est : **GitHub → Render Blueprint → Deploy → URL HTTPS**. Voir `GUIDE_DEPLOIEMENT.md`.

## Données

En production, utilisez PostgreSQL. Les fichiers sont, par défaut, stockés dans PostgreSQL (`PICHAT_STORAGE_BACKEND=database`) pour que le serveur web puisse rester stateless. Pour de gros volumes, basculez vers un stockage objet S3-compatible sans modifier les routes applicatives.

## Mises à jour

Les migrations sont dans `migrations/versions/`. Ne supprimez jamais l'ancienne base lors d'une mise à jour. Créez un backup avant déploiement ; le schéma est ensuite migré automatiquement par `init_database()`.

## Outils

```bash
python scripts/diagnostic.py
python scripts/check_no_secrets.py .
python scripts/migrate_sqlite_to_postgres.py /chemin/ancienne-pichat.db --replace
```

## Sécurité

PiChat ne possède aucune fonction permettant à un administrateur de récupérer un mot de passe en clair. Les mots de passe sont hashés avec bcrypt. Les clés API ne sont pas incluses dans les backups portables non chiffrés.
