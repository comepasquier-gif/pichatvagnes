# Mise à jour PiChat 3.4 → 3.5 PERFORMANCE — méthode rapide

Cette procédure conserve le service Render et la base PostgreSQL existants.

## 1. Avant la mise à jour

Dans PiChat : **Admin → Sauvegardes → Nouveau backup**.

## 2. GitHub

Le plus simple est d'utiliser **GitHub Desktop** :

1. Repository → **Show in Finder** pour ouvrir le dossier exact suivi par GitHub Desktop.
2. Copie le contenu de `PiChat_v3.5_PERFORMANCE` dans ce dossier.
3. Choisis **Remplacer** pour les fichiers existants.
4. Vérifie que `venv`, `.env`, `database/pichat.db` et les backups privés ne sont pas ajoutés.
5. Commit : `PiChat 3.5 PERFORMANCE`.
6. **Push origin**.

## 3. Render

Ne crée rien de nouveau. Render détecte le commit et redéploie automatiquement le Web Service.

Attends **Deploy live**, puis ouvre l'URL habituelle.

## 4. Première visite après 3.5

Le service worker 3.5 supprime les anciens caches PiChat 3.4. Si Safari affiche encore une ancienne interface, recharge une fois la page ou ferme/réouvre l'onglet.

Dans le chat, un badge affiche désormais par exemple :

`● 38 ms  objectif <50`

## 5. À ne pas faire

- Ne supprime pas `pichat-db`.
- Ne recrée pas le Blueprint.
- Ne change pas `PICHAT_SECRET_KEY`.
- Ne remets pas le dossier `venv` sur GitHub.
