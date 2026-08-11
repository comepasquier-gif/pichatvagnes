# PiChat 3.6.2 — UX + API + PiBrawl FIX

- API OpenAI : Enregistrer lance désormais un vrai appel Responses avec le modèle choisi.
- Erreurs API explicites : clé invalide, modèle indisponible, quota/facturation, rate limit, permission.
- Un test API réussi active automatiquement PiAI et la génération directe PiGame Studio.
- Messages privés : compatibilité amis + classe + espaces + serveurs, modal restylée et composer corrigé.
- Chat : barre de saisie réparée, textarea auto-ajustable, Entrée = envoyer, Maj+Entrée = nouvelle ligne.
- PiBrawl : arène beaucoup plus claire, clic gauche fiable, tir maintenu, touche F, tir tactile maintenu.
- Cache PWA passé en 3.6.2 / 3620.

## 3.6.3 — Safari normal / PWA auto-refresh
- La navigation privée n'est plus nécessaire pour récupérer une nouvelle version.
- Nettoyage automatique uniquement des anciens caches PiChat lors d'un changement de build.
- Réinstallation automatique du Service Worker PiChat.
- Pages HTML servies avec Cache-Control no-store.
- Navigation PWA toujours network-first.
- Cache-busting global 3630.
- Service Worker enregistré avec une URL versionnée.
