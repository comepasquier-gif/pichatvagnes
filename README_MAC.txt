PICHAT 2.2.0 — PACKS FINAUX
=============================

Cette version réunit notamment :

  - PiGame Studio pour créer des mini-jeux à partir d’un prompt spécial ;
  - mode manuel avec ChatGPT.com : copier le prompt, ouvrir ChatGPT et importer le JSON ;
  - mode automatique facultatif avec l’API OpenAI ;
  - validation de sécurité et aperçu dans une iframe isolée ;
  - brouillons privés, validation administrateur et galerie publique ;
  - Arcade, défis, classements, PyCoins et badges ;
  - profils gaming Valorant, Brawl Stars, Roblox, Fortnite et jeux personnalisés ;
  - packs de modération, messages privés, PiTutor+ et multi-établissements.

DÉMARRAGE RAPIDE
----------------
Place le dossier PiChat directement dans Téléchargements, puis :

  cd ~/Downloads/PiChat
  python3 pichat.py install
  python3 pichat.py network

Le Terminal affiche l’adresse à ouvrir sur les téléphones du même Wi-Fi.

COMMANDES PRINCIPALES
---------------------
  python3 pichat.py install       Installation initiale
  python3 pichat.py repair        Réparation + migration
  python3 pichat.py start         Mac uniquement
  python3 pichat.py network       Mac + téléphones du Wi-Fi
  python3 pichat.py doctor        Diagnostic
  python3 pichat.py backup        Sauvegarde
  python3 pichat.py update ZIP    Mise à jour avec backup préalable
  python3 pichat.py admin ...     Créer/promouvoir un admin
  python3 pichat.py user ...      Créer un utilisateur
  python3 pichat.py moderator ... Gérer un modo
  python3 pichat.py packs status  État des packs finaux
  python3 pichat.py packs backup  Backup immédiat

PIGAME STUDIO
-------------
Dans PiChat : PiGame Studio → décrire le jeu → copier le prompt et ouvrir ChatGPT.
Après génération, colle la réponse JSON dans PiGame Studio pour créer un brouillon.

Le mode automatique nécessite OPENAI_API_KEY dans .env et doit être activé dans :
  http://localhost:8000/admin#game-studio

ARCADE ET BADGES — CONSOLE ADMIN
--------------------------------
  arcade
  arcade on
  arcade off
  badges
  badge-give PSEUDO CODE [MOTIF]
  badge-remove PSEUDO CODE

GUIDE
-----
Ouvre GUIDE_PICHAT_2.1.html dans Safari.
Les documents complémentaires sont rangés dans le dossier docs/.

NOUVEAU DANS LA 2.1.5
----------------------
Le bouton d'envoi possède une reconnexion automatique et une courte file
d'attente. Le panneau Administration > Labo test permet de créer 20 comptes et
des données de démonstration, puis de les supprimer sans toucher aux vrais comptes.

NOUVEAU DANS LA 2.2.0
----------------------
- Messages programmés avec contrôle AutoModo et droits revérifiés à l’envoi.
- Amis, demandes d’ami et blocages.
- Gestion des appareils connectés.
- Backups automatiques avec rotation sûre.
- Laboratoire de test mis à jour pour ces nouveaux modules.
