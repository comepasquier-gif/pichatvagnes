# PiChat 3.5 PERFORMANCE — Installation

## Pour Render / GitHub

Aucun `venv` n'est nécessaire. Ne publie jamais `venv/`, `.venv/`, `.env`, une vraie base SQLite, des backups privés, des clés API ou des tokens. Render reconstruit Python à partir de `requirements.txt` et du `Dockerfile`.

## Mise à jour ultra rapide depuis PiChat 3.4

1. Télécharge la 3.5 et décompresse-la.
2. GitHub Desktop → **Repository → Show in Finder**.
3. Remplace le contenu du dépôt local par le contenu de la 3.5, **sans ajouter `venv`**.
4. GitHub Desktop doit alors afficher les modifications.
5. Commit : `PiChat 3.5 PERFORMANCE`.
6. Push origin.
7. Render redéploie automatiquement.

Ne supprime pas le service Render ni la base PostgreSQL existante.

## Test local facultatif

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PICHAT_SETUP_MODE=1
export PICHAT_SECRET_KEY='une-cle-locale-longue'
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Puis ouvre `http://127.0.0.1:8000/setup`.

## Vérification de performance

Dans le chat, le badge de ping indique la médiane des dernières mesures. PiChat privilégie le RTT WebSocket quand la connexion au salon est active et utilise `/api/ping` comme solution de repli. La cible UI est `< 50 ms`, sans garantie réseau absolue.
