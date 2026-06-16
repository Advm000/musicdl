# MASTER.md — Source de vérité produit (Music DL)

> Mémoire permanente. Détail technique exhaustif : `HANDOFF.md`.
> **Base courante : v1.2.0 publié (stable). v1.3 ABANDONNÉ (2026-06-17).**

## Vision
App Windows de bureau pour **chercher, écouter et télécharger** de la musique depuis YouTube Music — gratuite, sans abonnement, sans compte, en français. Pochettes officielles, paroles synchronisées, bibliothèque locale.

## Objectif principal
Une app stable et agréable pour télécharger/écouter sa musique, sans casser la compatibilité de `store.json`.

## Résumé
Electron 42 (vanilla JS, pas de framework). Recherche via API interne InnerTube (`WEB_REMIX`). Téléchargement via `yt-dlp`+`ffmpeg` (binaires `bin/`). Persistance JSON `%APPDATA%/Music DL/store.json` + `covers/` + `lyrics/`. Auto-update + landing GitHub Pages.

## Fonctionnalités terminées (publié v1.2.0)
- Recherche titres/albums/artistes/playlists (InnerTube, pagination, repli yt-dlp).
- Page artiste (top titres, discographie).
- Téléchargement MP3/M4A (qualité réglable, pochette + métadonnées embarquées, 3 en parallèle).
- Lecteur (`<audio>` + `mdl://` seek Range), file d'attente (drag&drop, menu contextuel), mini-lecteur.
- Paroles synchronisées (LRCLIB), compteur d'écoutes, playlists (manuelles + intelligentes virtuelles favoris/récents/top).
- Auto-update (electron-updater) + landing GitHub Pages.

## Fonctionnalités en cours
**Aucune.** Projet parqué sur la base stable v1.2.0.

## Décision v1.3 (2026-06-17)
v1.3 (socle online `onlineMeta` / réconciliation bibliothèque / multi-suppression / favoris online + refonte landing SaaS) **annulé** sur décision du boss. Retour intégral à l'état v1.2.0 publié : code applicatif et landing restaurés à v1.2.0. Mode Radio (É6) : déjà reporté/annulé.

## Architecture globale
`main.js` (backend Node : IPC, store, yt-dlp/ffmpeg, InnerTube, lyrics, update, harness E2E) ⇄ `preload.js` (pont `window.mdl.*`, contextIsolation) ⇄ `renderer/` (UI vanilla : `app.js`, `index.html`, `styles.css`, `mini.*`).

## Technologies
Electron ^42.4.0, electron-updater ^6.8.9, electron-builder ^26.15.2, sharp ^0.35.1, png-to-ico ^3.0.1. Binaires : yt-dlp 2026.06.09, ffmpeg.

## Structure du projet
- `src/main.js` — backend + E2E. `src/preload.js` — API. `src/renderer/{app.js,index.html,styles.css,mini.*,fonts/}` — UI.
- `docs/index.html` — landing GitHub Pages (version v1.2.0, fond WebGL/Three.js).
- `.github/workflows/release.yml` — build/release. `tools/` — `fetch-bins.ps1`, sondes. `bin/` `dist/` `node_modules/` — gitignored.

## Décisions importantes (voir HANDOFF §11)
- Vanilla JS. InnerTube pour la recherche (yt-dlp a supprimé `ytmsearch`).
- `store.json` : compat ascendante stricte, ajouts additifs uniquement.
- Publication **uniquement via GitHub Actions** (jamais d'upload local de l'installeur).

## Roadmap
```
v1.2.0  PUBLIÉ (2026-06-14) — Latest, base stable courante
v1.3    ABANDONNÉ (2026-06-17)
suite   à définir par le boss
```

## Tags / versions
Remote : v1.0.0, v1.2.0 (Latest). `origin/main` = commit landing `2f90fc9` (la landing a été ramenée au contenu v1.2.0 localement, non poussé).
