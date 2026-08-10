# PiBrawl Arena — PiChat 3.6

Mini jeu d'arène original, sans dépendance externe, conçu pour être modifié.

## Premier personnage

`personnages/pichat/` contient PiChat : combattant de proximité à 5 éclats en éventail, avec un Super plus large qui repousse. Le moteur et les assets PiChat sont originaux ; aucun asset ou code de Brawl Stars n'est inclus.

## Ajouter un personnage en 1 dossier

Copier `personnages/_template/` → par exemple `personnages/robot_bleu/`.

- `fighter.py` : statistiques + attaque + super ;
- `head.png` : tête du personnage.

Le serveur découvre les dossiers automatiquement. Pas de liste codée en dur.

## Pourquoi pas du Python arbitraire ?

Une instance publique ne doit jamais `import`/`exec` un fichier envoyé comme personnage. PiChat lit le fichier Python avec `ast`, puis n'autorise que `FIGHTER = { ... }` avec des valeurs littérales. C'est volontaire : le perso est simple à coder en Python, mais ne peut pas voler une clé API ou accéder à PostgreSQL.

## Europe / ping

Pour une nouvelle instance Render européenne, créer un nouveau Blueprint et indiquer **Blueprint Path** : `render-europe.yaml`.
Le fichier crée le Web Service et PostgreSQL dans la région `frankfurt`.
