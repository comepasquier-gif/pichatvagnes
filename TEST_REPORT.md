# Rapport de tests — PiChat 3.4 FREE ONLINE

Validation effectuée le 9 août 2026 sur le paquet de livraison.

## Tests réussis

- Syntaxe/bytecode Python : 112 fichiers ; grammaire Python 3.9 vérifiée.
- JavaScript : 37 fichiers contrôlés avec `node --check`.
- FastAPI : démarrage via `TestClient`, `/api/health`, `/setup`, login, routes admin.
- Setup : création du premier propriétaire puis verrouillage API + redirection serveur.
- Permissions : un modérateur de Labo ne peut pas accéder au Dashboard admin.
- Migrations : `340001`, `340002`, `340003` appliquées sur une base neuve.
- PiGame Studio : JSON, HTML, CSS, JavaScript et ZIP importés ; paquet avec `eval` refusé.
- Sandbox PiGame : CSP sans réseau, iframe sans `allow-same-origin`, bridge PiGame limité.
- API PiGame : score et succès testés.
- Labo : génération de comptes/données, simulation de 8 connexions, nettoyage.
- Backups : création, téléchargement, intégrité ZIP, ajout/extraction/suppression d'un fichier, secrets et sessions exclus.
- Coffre API : une clé test est masquée dans l'API et absente du backup exportable.
- `render.yaml` : YAML parsé et champs Blueprint principaux vérifiés.
- Compatibilité SQL PostgreSQL : traduction des dates, paramètres datetime, `INSERT OR IGNORE`, MIN/MAX scalaires vérifiée.
- Scan de secrets : aucun `.env` privé, base réelle, clé privée ou token évident détecté.

## Limite de l'environnement de build

Le conteneur de validation ne fournit pas de serveur PostgreSQL ni le module `psycopg2` préinstallé ; une connexion PostgreSQL réelle n'a donc pas pu être ouverte ici. Le paquet installe `psycopg2-binary` via `requirements.txt`, et le chemin PostgreSQL a été validé statiquement ainsi que par les migrations/transformations SQL. Un diagnostic `/api/health` et `/admin > Mise en ligne` est prévu après le premier déploiement Render.
