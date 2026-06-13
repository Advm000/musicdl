# 📋 PLAN v1.2 — « L'expérience » (ordre d'exécution)

> Démarrage : UNIQUEMENT à la notification du boss.
> Protocole : rester ACTIF et visible pendant tout le travail (voir §0).

## §0 — PROTOCOLE DE COMMUNICATION (obligatoire pendant le travail)
- **Annoncer le début de chaque étape** : « ÉTAPE X démarrée — voici ce que je fais »
- **Annoncer la fin de chaque étape** avec une **capture d'écran de preuve** quand c'est visuel
- **Signaler immédiatement tout bug ou blocage** rencontré, avec mon diagnostic, AVANT de le corriger
- Après les étapes 1, 2, 3 et 7 : **lancer l'app et la laisser ouverte** pour que le boss puisse tester en direct et me signaler ce qui cloche
- Jamais plus de ~15 min sans donner un signe de vie dans le chat

---

## ÉTAPE 1 — 🪟 Mini-lecteur VERTICAL pro (30 min – 1h)
**Objectif** : remplacer le mini horizontal par un design vertical type « grand lecteur de poche ».
**Comment je fais** :
- Nouvelle fenêtre ~240×360 : grande pochette carrée en haut (coins arrondis 18px, halo lumineux dégradé bleu→turquoise derrière, comme le grand lecteur), titre + artiste centrés, barre de progression cliquable, rangée de contrôles ⏮ ⏯ ⏭ en bas, boutons ⤢ (retour app) et épingle discrets en haut
- Fichiers : `src/renderer/mini.html` (refonte), `mini.js` (adapter), `main.js` (taille fenêtre)
- L'app se cache toujours quand le mini s'ouvre (comportement validé en v1.1)
**Vérification** : capture du mini en lecture + test boss en direct.

## ÉTAPE 2 — 🎤 Paroles synchronisées (45 min – 1h30)
**Objectif** : karaoké dans le grand lecteur, hors ligne.
**Comment je fais** :
- API LRCLIB (gratuite, sans clé) : `GET https://lrclib.net/api/get?artist_name=&track_name=&duration=` → paroles synchronisées `[mm:ss.xx]`
- Récupération à la fin de chaque téléchargement (+ bouton « réessayer » si absentes) ; stockage dans `userData/lyrics/<id>.lrc` ; CSP connect-src + lrclib.net
- Grand lecteur : zone paroles scrollable sous la pochette (pochette réduite), ligne active en `#4f88f8` + plus grande, lignes voisines grisées, auto-scroll fluide, clic ligne = seek
- Repli : paroles non synchronisées affichées en texte simple ; rien trouvé = message discret
- Récupération rétroactive pour les titres déjà téléchargés (bouton dans la bibliothèque)
**Vérification** : E2E sur un titre connu + capture karaoké + test boss.

## ÉTAPE 3 — 👤 Page Artiste (40 min – 1h15)
**Objectif** : cliquer un nom d'artiste → sa page complète.
**Comment je fais** :
- Backend : recherche filtre artistes (déjà en place) + `browse(artistId)` → header (nom, photo, auditeurs/mois), shelf « Titres populaires » (musicResponsiveListItemRenderer avec videoId), carrousels albums/singles (musicTwoRowItemRenderer, déjà parsé en v1.1)
- UI : nouvelle vue dans la page Recherche (comme la vue album) : bannière photo + nom + stats, top titres avec préécoute/téléchargement, grille discographie cliquable vers les vues album
- Rendre cliquables : artiste des cartes de résultats, des lignes bibliothèque, du lecteur et du grand lecteur
**Vérification** : E2E ouvre la page Stormy → top titres + discographie > 0 ; capture.

## ÉTAPE 4 — 📜 File d'attente visible (30 min – 1h)
**Objectif** : voir et contrôler « À suivre ».
**Comment je fais** :
- Panneau latéral droit coulissant (bouton liste dans le lecteur) : titre en cours en haut, puis la file ; chaque ligne = pochette mini + titre + durée + poignée
- Glisser-déposer natif HTML5 pour réordonner `playQueue` ; suppression au survol ; « Vider la file »
- Menu contextuel (clic droit) sur toutes les lignes de titres : « Lire ensuite » (insère après playPos) / « Ajouter à la file » (push)
**Vérification** : E2E réordonne par script et vérifie l'ordre ; capture du panneau.

## ÉTAPE 5 — ⭐ Playlists intelligentes (20 – 40 min)
**Objectif** : 3 playlists auto toujours à jour.
**Comment je fais** :
- Compteur d'écoutes : `store.plays[id]++` quand un titre passe >50% de sa durée (event timeupdate, une fois par lecture)
- Playlists virtuelles (non stockées, calculées au rendu) : ❤ Favoris (favorite=true), 🕐 Récents (25 derniers addedAt), 🔥 Plus écoutés (top 25 plays)
- Affichées en tête de la page Playlists avec badge « Auto », non supprimables, lecture/aléatoire OK
**Vérification** : E2E vérifie compteur après lecture + présence des 3 cartes.

## ÉTAPE 6 — 📻 Mode Radio (30 min – 1h) *(si le boss confirme)*
**Objectif** : enchaînement auto de titres similaires en streaming.
**Comment je fais** :
- Endpoint InnerTube `next` avec videoId → file « mix » de titres similaires (id, titre, artiste, pochette)
- Bouton 📻 sur les cartes/lignes : lance la préécoute du titre + pré-charge la suite ; à la fin d'un titre, enchaîne le suivant du mix (URL streaming via cache préécoute)
- Bandeau « Radio en cours — basée sur X » avec bouton stop ; téléchargement possible à tout moment
**Vérification** : E2E lance une radio, vérifie 2 enchaînements.

## ÉTAPE 7 — 🌐 Landing page 3D (1h – 2h)
**Objectif** : landing premium avec profondeur 3D, dans le contexte Music DL, qui donne envie de télécharger.
**Comment je fais** (CSS 3D + JS léger, pas de framework lourd → chargement rapide) :
- **Héros 3D** : la capture de l'app dans un cadre en perspective qui **s'incline en suivant la souris** (transform rotateX/rotateY + lissage), reflets et ombre portée dynamiques
- **Profondeur** : pochettes d'albums flottantes sur 3 couches de parallaxe (vitesses différentes au mouvement souris + au scroll), halos bleu/turquoise animés, fines particules
- **Scroll cinématique** : sections qui se révèlent (IntersectionObserver), carrousel conservé mais intégré au cadre 3D, compteurs animés (titres, version)
- **Conversion** : CTA « Télécharger » omniprésent et pulsant doucement, section nouveautés v1.2, FAQ courte (SmartScreen), footer pro
- Palette officielle stricte, responsive, fallback simple si l'utilisateur a un petit GPU
**Vérification** : déploiement Pages + captures desktop, test boss sur le vrai lien.

## ÉTAPE 8 — 🧪 Tests E2E complets (30 min – 1h)
- Étendre `runE2E` : paroles (state.lyricsLines>0 + capture karaoké), page artiste (top titres + albums), file d'attente (réordonnancement scripté), playlists auto (3 cartes + compteur), radio (2 enchaînements), mini vertical (capture)
- Lancer en détaché + Monitor ; **prévenir le boss de ne pas fermer la fenêtre pendant le test**

## ÉTAPE 9 — 🚀 Release v1.2.0 (20 – 40 min)
- `npm version 1.2.0` → commit + push → release GitHub (notes complètes) → workflow Actions → vérif latest.yml/exe/landing → annonce au boss : la notif de mise à jour arrive sur son app

---
**TOTAL : ~4h30 min / ~9h max** (sans radio : −30 min à −1h)
