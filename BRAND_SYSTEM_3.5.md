# PiChat 3.5 — Brand & Mascot System

La 3.5 suit les six références visuelles du projet : composition PiChat/Chavagnes, logo horizontal, guide de marque, Mascot System, Reactions & Emotions et Mini Bot Animation System.

## Personnage verrouillé

La mascotte reste un robot-chat : coque blanche, oreilles de chat à intérieur bleu/cyan, grand écran facial bleu nuit, écouteurs latéraux blancs/bleus, palette marine/bleu électrique/cyan/blanc avec accents dorés Chavagnes.

Les états changent principalement par les yeux, la bouche, les petits symboles et de très petits mouvements. Le Mini Bot ne doit pas se transformer en personnage différent selon les écrans.

## Palette 3.5

- Navy : `#050817`
- Navy 2 : `#081329`
- Bleu : `#2979ff`
- Cyan : `#32e2ff`
- Indigo : `#5b55ff`
- Or Chavagnes : `#e6b34c`
- Blanc : `#f7fbff`

## Assets

- `frontend/assets/brand/pichat-mascot.svg`
- `frontend/assets/brand/pichat-logo.svg`
- `frontend/assets/brand/pichat-app-icon.svg`
- `frontend/assets/icons/pichat-*.png`

## Mini Bot

`window.PiChatMiniBot.setState(n)` accepte les états 1 à 48 du système d'animation. Les états importants sont aussi déclenchés automatiquement : connexion perdue, reconnexion, utilisateur qui écrit, nouveau message, succès, erreur, mode admin et interactions tactiles.
