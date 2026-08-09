# Guide de déploiement — GitHub → Render → HTTPS

## Objectif

Aucun Oracle Cloud, aucun Cloudflare Tunnel, aucun token de tunnel et aucun Mac à laisser allumé. Le dépôt contient `render.yaml`, `Dockerfile` et les migrations nécessaires.

## Déploiement Blueprint

1. Créez un dépôt GitHub vide.
2. Placez le contenu de PiChat 3.4 à la racine du dépôt puis poussez-le sur GitHub.
3. Dans Render, choisissez **New → Blueprint** et connectez ce dépôt.
4. Render lit `render.yaml`, crée le Web Service Docker et PostgreSQL, puis injecte `DATABASE_URL`.
5. `PICHAT_SECRET_KEY` est générée automatiquement par le Blueprint. Ne la changez pas après avoir enregistré des clés API.
6. Lancez le déploiement.
7. Ouvrez l’URL publique suivie de `/setup` et créez le propriétaire.
8. Ouvrez `/admin` → **Mise en ligne** et lancez le diagnostic.

Le service utilise l’URL HTTPS fournie par l’hébergeur. PiChat lit automatiquement `RENDER_EXTERNAL_URL` lorsqu’elle est présente.

## Ce qu’il faut savoir sur le gratuit Render

État vérifié le 9 août 2026 : le Web Service gratuit peut s’endormir après 15 minutes sans requête entrante, et le PostgreSQL gratuit est une base de démarrage de 1 Go qui expire après 30 jours. Le niveau gratuit convient donc à un lancement/test, pas à une instance communautaire durable sans migration.

PiChat évite malgré tout le principal piège du Web Service gratuit : les comptes, messages, réglages et fichiers ne dépendent pas de son disque éphémère.

Avant l’expiration de la base gratuite, passez simplement à une base PostgreSQL durable ou remplacez `DATABASE_URL`. Pour les fichiers volumineux, passez `PICHAT_STORAGE_BACKEND=s3`.

## Domaine personnalisé facultatif

Vous pouvez ajouter plus tard un domaine personnalisé chez l’hébergeur et conserver votre fournisseur DNS habituel. PiChat n’exige pas Cloudflare.

## Mise à jour 3.4 → 3.5 → 4.0

1. **Admin → Sauvegardes** : créez un backup.
2. Poussez le nouveau code sur GitHub.
3. L’hébergeur redéploie le conteneur.
4. Au démarrage, `init_database()` applique les migrations absentes de `schema_migrations`.
5. Les données restent dans PostgreSQL/stockage persistant.

Ne changez pas `PICHAT_SECRET_KEY` lors d’une simple mise à jour : elle sert à déchiffrer les clés API stockées côté serveur.
