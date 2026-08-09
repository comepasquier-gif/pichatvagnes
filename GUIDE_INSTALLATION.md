# Guide d'installation — PiChat 3.4 FREE ONLINE

## 1. Pré-requis

- Python 3.9 ou plus récent pour une installation locale.
- GitHub pour le déploiement simple.
- En production : PostgreSQL via `DATABASE_URL`.

## 2. Installation locale de vérification

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Ne commitez jamais `.env`. Pour un test local sans PostgreSQL, laissez `DATABASE_URL` vide : PiChat utilise SQLite. Pour tester l'assistant de première installation, définissez `PICHAT_SETUP_MODE=1`.

Lancement :

```bash
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Ouvrez `/setup`, puis suivez :

1. créer le propriétaire ;
2. nommer l'instance ;
3. choisir les paramètres de sécurité et d'inscription ;
4. ajouter éventuellement une API IA ;
5. terminer.

Une fois le propriétaire créé, `/setup` est verrouillé côté API et redirigé côté serveur.

## 3. Données persistantes

### Base

- Local : SQLite reste supporté.
- Online : PostgreSQL est recommandé et sélectionné automatiquement si `DATABASE_URL` commence par `postgres://` ou `postgresql://`.

### Fichiers

`PICHAT_STORAGE_BACKEND` accepte :

- `database` : les fichiers sont conservés dans `file_objects` ; idéal pour démarrer sans disque persistant ;
- `s3` : bucket S3-compatible ; recommandé quand les fichiers deviennent nombreux ;
- `local` : uniquement pour une installation disposant réellement d'un disque persistant.

## 4. Variables essentielles

- `DATABASE_URL` : connexion PostgreSQL.
- `PICHAT_SECRET_KEY` : secret long et stable, utilisé notamment pour le coffre API.
- `PICHAT_STORAGE_BACKEND=database`.
- `PICHAT_COOKIE_SECURE=1` en HTTPS.
- `PICHAT_TRUST_PROXY=1` derrière Render/reverse proxy.

## 5. Vérification

```bash
python scripts/diagnostic.py
python scripts/check_no_secrets.py .
```
