# Migration d’une ancienne base SQLite PiChat vers PostgreSQL

## Migration complète 3.3 → 3.4

1. Arrêtez l’ancien PiChat afin d’obtenir une base cohérente.
2. Faites une copie du fichier `pichat.db` et du dossier `uploads/`.
3. Configurez `DATABASE_URL` vers la base PostgreSQL de destination.
4. Lancez :

```bash
DATABASE_URL='postgresql://...' PICHAT_SECRET_KEY='...' \
python scripts/migrate_sqlite_to_postgres.py /chemin/database/pichat.db --replace
```

Le script initialise d’abord le schéma 3.4 et ses migrations, recopie les tables communes en conservant les identifiants, recale les séquences PostgreSQL puis cherche automatiquement l’ancien dossier `uploads/`.

Si les fichiers sont ailleurs :

```bash
DATABASE_URL='postgresql://...' PICHAT_SECRET_KEY='...' \
python scripts/migrate_sqlite_to_postgres.py /chemin/pichat.db --replace --uploads-dir /chemin/uploads
```

Les anciens fichiers compatibles sont importés dans le stockage persistant 3.4 et les URL des messages de type fichier ainsi que les avatars connus sont réécrites. Les fichiers dangereux/non reconnus sont ignorés avec un avertissement au lieu d’être remis en ligne aveuglément.

Les sessions, tentatives de connexion, liens d’assistance et clés API ne sont volontairement pas migrés. Les utilisateurs se reconnectent et les API sont reconfigurées depuis **Admin → Intégrations**.

## Contrôle après migration

- ouvrez `/admin` → **Mise en ligne** ;
- vérifiez utilisateurs, messages, salons, PyCoins, jeux et fichiers ;
- créez immédiatement une sauvegarde 3.4 ;
- lancez `python scripts/diagnostic.py`.
