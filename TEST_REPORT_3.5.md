# PiChat 3.5 PERFORMANCE — rapport de contrôle

## Contrôles passés

- Grammaire Python compatible Python 3.9 sur tous les fichiers `.py` du projet.
- Syntaxe JavaScript vérifiée avec `node --check` sur tous les fichiers `.js`, y compris les bundles 3.5.
- Démarrage FastAPI en environnement de test SQLite.
- `/api/health` répond et annonce le mode performance avec cible 50 ms.
- `/api/ping` répond sans accès base et annonce `3.5.0` / `target_ms: 50`.
- Ping WebSocket `/ws` → `pong` testé après authentification.
- `/setup` : création propriétaire testée puis second setup refusé.
- Page `/login` 3.5 servie correctement.
- Bundles chat 3.5 servis avec cache `immutable`.
- Dashboard admin accessible après authentification.
- PiGame Studio : import JSON/JS/CSS/HTML/ZIP, sandbox, score et succès.
- PiGame : tentative `eval` refusée.
- Labo : comptes de test, permissions, simulation de connexions et nettoyage.
- Backups : création, téléchargement, exclusion de clé API, édition d'un fichier et suppression.
- Migrations neuves : `340001`, `340002`, `340003`, `350001`.

## Performance 3.5

Le chat charge désormais un bundle CSS et un bundle JS au lieu d'une longue série de ressources séparées. L'admin utilise le même principe. GZip, cache versionné et service worker 3.5 complètent cette réduction des requêtes.

Le seuil `< 50 ms` est une cible de latence RTT affichée. PiChat réduit la surcharge applicative, mais ne peut pas garantir la distance réseau ou l'état du service d'hébergement.

## Note environnement de test

L'environnement de construction ne contenait pas le paquet `bcrypt`. Le smoke test local a donc utilisé un module bcrypt de test temporaire uniquement pour exercer les flux. Le paquet de production conserve `bcrypt==4.2.1` dans `requirements.txt`; le module temporaire n'est pas inclus dans le ZIP.
