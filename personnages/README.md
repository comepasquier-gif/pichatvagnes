# Personnages PiBrawl — système open-source

Un nouveau combattant ne demande **aucune modification du moteur**.

## Ajouter un perso

1. Duplique `personnages/_template/`.
2. Renomme le dossier, par exemple `pixelcat`.
3. Dans `fighter.py`, mets `"id": "pixelcat"`.
4. Ajoute sa tête : `head.png`, `head.webp` ou `head.jpg`.
5. Commit + Push sur GitHub. Render redéploie et le perso apparaît dans la sélection.

## Python, mais sûr

`fighter.py` est bien du Python lisible et éditable. Toutefois PiChat **ne l'importe pas** et ne fait aucun `exec`.
Le serveur analyse son AST et accepte uniquement :

```python
FIGHTER = { ... valeurs littérales Python ... }
```

Ainsi un perso peut définir ses statistiques, son attaque et son super sans pouvoir lire la base, les cookies, les clés API, le système de fichiers ou le réseau.

### Attaques supportées dans cette première version

Attaque : `spread_shot`, `single_shot`, `burst_shot`.

Super : `super_spread`, `dash_blast`, `heal_pulse`.

Le moteur est volontairement simple et sans framework afin que la communauté puisse ajouter de nouveaux types dans `frontend/js/pibrawl.js` et les autoriser dans `backend/services/pibrawl_registry.py`.
