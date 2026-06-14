# 📦 Music DL — Dossier de transfert (Handoff Master)

> Document de reprise production-ready. Mis à jour le 2026-06-14.
> Si une info manque elle est notée `UNKNOWN`. Priorité absolue : **stabilité**.

---

## 1. Vision du projet
Application **Windows de bureau** (Electron) pour **chercher, écouter, télécharger et organiser** de la musique depuis **YouTube Music**, sans abonnement. MP3/M4A avec vraies pochettes, lecteur complet, playlists, paroles karaoké, mode 100 % hors ligne, mises à jour automatiques. Cible : utilisateur grand public francophone. Design « pro » fidèle à un mockup officiel (palette bleu `#4f88f8` / turquoise `#1dd3b0`, fond sombre `#06080f`).

## 2. État actuel exact
- **Version publiée** : `v1.1.0` (release GitHub + installeur en ligne + landing). Le bump vers `1.2.0` se fait à l'étape release (É9).
- **package.json version locale** : `1.1.0`.
- **Branche** : `main`. Tous les travaux ci-dessous sont **commités** sur `main`.
- **Travaux v1.2** : Gate0 + É1 + É2 + É3 + É4 + É5 + É7 **FAITS et commités**. É6 (Radio) **sauté** (reporté v1.3). **Restent : É8 (E2E complets) et É9 (release v1.2.0)**.
- **Working tree propre** sauf 2 outils dev non suivis : `tools/probe-artist.js`, `tools/check-store.js` (et ce `HANDOFF.md`).
- Bibliothèque de test locale : variable (~1–3 titres ; le test torture en supprime/retélécharge). Reconstituée par les suites E2E.

### Journal des commits v1.2 (du plus récent au plus ancien)
```
9426596 feat(E7): landing 3D premium (heros incline souris, parallaxe, scroll cinematique)
602e956 feat(E5): playlists intelligentes (Favoris, Recents, Plus ecoutes)
0673cba feat(E4): file d'attente visible (panneau lateral, drag&drop, clic droit)
dbeef23 fix(E1+E3): boutons telechargement page artiste + espacement bas mini-lecteur
fd94d80 feat(E3): page artiste complete (en-tete, top titres, discographie)
08c66b7 fix(E2): paroles karaoke invisibles - hauteur panneau gl-lyrics
70fcda7 feat(E2): paroles synchronisees karaoke (LRCLIB)
```

## 3. Fonctionnalités
**Terminées (v1.0 → v1.1) :** recherche YouTube Music (titres/albums/playlists, onglets), recherche pro (jusqu'à 200 titres en scroll infini, suggestions à la frappe, albums intelligents = discographie de l'artiste d'abord), préécoute streaming, téléchargement MP3/M4A 128/192/320 kbps (3 parallèles, file, vraies pochettes), bibliothèque (tri 5 colonnes, filtre, favoris, suppression), playlists (CRUD, mosaïques, vue détail), lecteur complet (lecture/pause, suivant/précédent, aléatoire, répétition off/tout/un, volume/muet, seek via Range), grand lecteur, barre système, minuteur de sommeil, mises à jour auto (electron-updater + GitHub Releases), gestion d'erreurs audio robuste (anti-blocage/anti-boucle).
**Terminées (v1.2, commitées) :**
- **É1 mini-lecteur vertical** — fenêtre 252×420, grande pochette, halo, contrôles. (Espacement bas corrigé v1.2.)
- **É2 paroles synchronisées karaoké** (LRCLIB, hors ligne) — panneau dans le grand lecteur, ligne active surlignée + auto-scroll, clic = seek. (Bug rendu « hauteur 0 » corrigé.)
- **É3 Page Artiste** — vue dédiée (bannière photo + nom + abonnés, top titres préécoutables/téléchargeables, grille discographie cliquable) ; **noms d'artistes cliquables** partout (résultats, bibliothèque, lecteur, grand lecteur).
- **É4 file d'attente visible** — panneau latéral coulissant, **drag & drop** pour réordonner `playQueue`, suppression au survol, « Vider », **menu clic droit** « Lire ensuite » / « Ajouter à la file ».
- **É5 playlists intelligentes** — compteur d'écoutes (`store.plays`), 3 playlists virtuelles (❤ Favoris, 🕐 Récents, 🔥 Plus écoutés) en tête de la page Playlists, badge « Auto », non supprimables.
- **É7 landing 3D** — page GitHub Pages refondue (héros incliné à la souris, pochettes flottantes/parallaxe, halos, particules, révélations au scroll, compteurs animés, section nouveautés v1.2, FAQ SmartScreen, CTA pulsant, fallback `prefers-reduced-motion`).
**À faire (v1.2) :** É8 E2E complets (étendre `runE2E` aux nouvelles features + assertion hauteur paroles), É9 release v1.2.0.
**Futures (v1.3+) :** É6 mode Radio (enchaînement auto de titres similaires en streaming — reporté).

## 4. Architecture technique
- **Electron** (frameless, fenêtre custom). 2 process :
  - **Main** (`src/main.js`, ~1500 lignes) : fenêtre, IPC, recherche/téléchargement, store JSON, auto-update, tray, mini-window, protocole `mdl://`, paroles, **page artiste**, **compteur d'écoutes**, E2E.
  - **Renderer** (`src/renderer/`) : UI pure (pas de framework), `app.js` (~1900 lignes) = toute la logique UI, `index.html`, `styles.css`, + `mini.html`/`mini.js`.
- **Pont sécurisé** : `src/preload.js` (`contextBridge` → `window.mdl`), `contextIsolation: true`, `nodeIntegration: false`.
- **Binaires embarqués** (`bin/`, non versionnés) : `yt-dlp.exe`, `ffmpeg.exe`, `ffprobe.exe` — via `extraResources`. Récupérés par `tools/fetch-bins.ps1`.
- **Lecture des fichiers locaux** : protocole custom `mdl://local/?p=<path>` avec **support Range requests** (obligatoire pour le seek audio).
- **Verrou single-instance** : `app.requestSingleInstanceLock()` — une 2e instance quitte immédiatement (voir §10).

## 5. Structure du code
```
src/main.js            # process principal (tout le backend + suites E2E)
src/preload.js         # pont IPC (window.mdl.*)
src/renderer/
  index.html           # UI : pages Recherche/Bibliothèque/Playlists + player + grand lecteur + panneau file + modals
  app.js               # logique UI complète + MDL_TEST (hooks E2E)
  styles.css           # styles (palette mockup)
  mini.html / mini.js  # mini-lecteur vertical (fenêtre séparée)
  fonts/inter.css      # police Inter locale
bin/                   # yt-dlp + ffmpeg (gitignored, via tools/fetch-bins.ps1)
build/                 # icon.ico / icon.png (générés par tools/gen-icon.js)
docs/                  # landing page 3D (GitHub Pages) + docs/assets/ (icon + captures)
tools/                 # fetch-bins, gen-icon, upload-release-asset, probe-artist (sonde page artiste),
                       # check-store (diag store.json), release notes
.github/workflows/release.yml  # build+upload installeur via Actions (workflow_dispatch, input tag)
PLAN-V1.2.md           # plan détaillé v1.2 (étapes + protocole)
HANDOFF.md             # ce document
```

## 6. "Base de données"
Pas de SGBD. Persistance = **un fichier JSON** : `%APPDATA%/Music DL/store.json`.
```
{
  settings: { folder, quality:'128|192|320', format:'mp3|m4a', closeToTray:bool },
  library: [ { id, title, artist, album, year, duration, file, cover, favorite, addedAt, hasLyrics? } ],
  playlists: [ { id, name, tracks:[trackId], createdAt } ],
  recents: [ "requête" ],            // max 6
  plays:   { trackId: nombreEcoutes } // AJOUT v1.2/É5, retro-compatible (defaut {})
}
```
Autres dossiers `%APPDATA%/Music DL/` : `covers/<id>.jpg`, `lyrics/<id>.json` (`{id,synced,plain,found}`).
Fichiers audio : dans `settings.folder` (défaut `Musique/Music DL/`), nommés `Artiste - Titre.mp3`.
**Compat ascendante garantie** : `loadStore()` réinjecte les défauts pour tout champ manquant (dont `plays`). `library:delete` nettoie aussi `store.plays[id]`.

## 7. API & flux de données (IPC `window.mdl.*`)
Recherche/contenu : `search(q,kind)`, `searchMore(token,kind)`, `suggest(input)`, `getCollection({browseId,kind})`, **`getArtist(browseId)`**, **`getArtistByName(name)`**, `previewUrl(id)`.
Téléchargement : `download(track)` → events `dl:queue` / `dl:done` / `dl:error`.
Bibliothèque/playlists : `deleteTrack`, `revealTrack`, `openFolder`, `setFavorite`, **`bumpPlay(id)`** (incrémente `store.plays`), `createPlaylist`, `deletePlaylist`, `renamePlaylist`, `addToPlaylist`, `removeFromPlaylist`.
Paroles : `getLyrics(id)`, `refetchLyrics(id)` → event `lyrics:ready`.
Paramètres : `chooseFolder`, `saveSettings`. Update : `downloadUpdate`, `installUpdate` → `update:available/progress/ready/error`.
Fenêtre/mini/tray : `minimize/maximize/close`, `openMini/closeMini/miniCmd/sendMiniState`, events `remote:cmd`, `mini:state`.
Handlers IPC main correspondants : `artist:get`, `artist:byName`, `plays:bump` (ajoutés v1.2).

## 8. Logique métier
- **Recherche YouTube Music = API interne InnerTube** (`music.youtube.com/youtubei/v1/...`, client `WEB_REMIX`). Filtres `params` : songs/albums/artists/playlists. Pagination = jeton `continuation` dans le body. Repli `yt-dlp ytsearch` pour les titres.
- **Page artiste** : `getArtistByName` → recherche filtre artistes → `getArtist(browseId)` → `innertube('browse')` → header (nom/abonnés/photo normalisée `=w480-h480`), shelf top titres (`musicResponsiveListItemRenderer`), carrousels albums (`collectArtistAlbums`). UI : `openArtistByName` ouvre l'état `#ss-artist`.
- **Albums intelligents** : si la requête ≈ un nom d'artiste → discographie officielle affichée avant les autres albums.
- **Téléchargement** : `yt-dlp -x --audio-format` + `--embed-thumbnail`/`--embed-metadata`, pochette carrée, métadonnées complétées par un 2e appel `-j`. File de 3 en parallèle.
- **Lecteur** : élément `<audio>` unique, `playQueue` (ids) + `playPos`. `onLoadFail` anti-blocage/anti-boucle, file nettoyée à la suppression. Seek via `mdl://` + Range.
- **File d'attente (É4)** : panneau `#qpanel`, `moveInQueue/removeFromQueue/clearQueueExceptCurrent` (recalculent `playPos` via l'id courant), `playNext/addToQueue`, drag&drop HTML5, menu clic droit délégué.
- **Compteur d'écoutes (É5)** : dans `timeupdate`, un titre (hors préécoute) lu au-delà de **50 %** incrémente `store.plays[id]` **une fois par lecture** (garde `playCountedId`, réarmée dans `loadTrack`).
- **Playlists intelligentes (É5)** : `smartPlaylists()` calcule 3 listes virtuelles au rendu (non stockées). `findPlaylist(id)` route les ids `__fav/__recent/__top` vers le virtuel. `goPage(2)` re-rend la grille pour refléter favoris/écoutes à jour.
- **Paroles** : LRC parsé `[mm:ss.xx]`, ligne active + auto-scroll. Panneau `.gl-lyrics` a une **hauteur fixe 220px** en mode `lyrics-on` (correctif du rendu).
- **Rafraîchissement multi-panneaux** : `refreshCard(id)` met à jour **toutes** les `.rcard[data-id]` (résultats + page artiste), pas seulement la première (correctif bug A).

## 9. Services externes
- **YouTube Music InnerTube** (non officiel, sans clé) — recherche/browse/page artiste.
- **yt-dlp + ffmpeg** (binaires) — extraction/conversion audio + préécoute (`-g`).
- **LRCLIB** (`lrclib.net/api`, gratuit) — paroles.
- **GitHub** : repo `Advm000/musicdl` (public), Releases (auto-update + téléchargement), Pages (`advm000.github.io/musicdl`), Actions (build installeur).

## 10. Bugs & problèmes connus
- ✅ Corrigés v1.2 : blocage fichier introuvable, boucle file cassée, file non nettoyée à la suppression (É0) ; **paroles karaoké invisibles** (CSS hauteur panneau) ; **boutons télécharger manquants sur la page artiste** (collision d'id → `refreshCard` mis à jour pour toucher toutes les cartes) ; **bas du mini-lecteur rogné** (fenêtre 396→420) ; **playlists auto non rafraîchies** à la navigation (`goPage` re-rend) ; assertion favori E2E non-idempotente.
- ⚠️ **Upload local de l'installeur (166 Mo) échoue** sur connexion lente → **toujours publier via GitHub Actions** (`release.yml`), jamais en local.
- ⚠️ App **non signée** → SmartScreen Windows (documenté dans la FAQ de la landing).
- ⚠️ **Verrou single-instance** : tant qu'une instance « Music DL » tourne (ou un zombie après un test tué), toute nouvelle instance **quitte aussitôt (exit 0, rien écrit)**. Avant de lancer une suite E2E, **tuer les zombies** : PowerShell `Get-Process -Name 'Music DL','electron' -EA SilentlyContinue | Stop-Process -Force` (le process Electron prend le nom du `productName` « Music DL », pas `electron.exe`).
- ⚠️ Les rapports E2E (`*-report.json`) sont écrits juste avant `app.exit()` ; si le process est tué pendant l'écriture, le fichier peut être **rempli d'octets nuls**. Re-lancer la suite à froid.
- InnerTube/`params` peuvent changer côté Google → repli yt-dlp en place ; re-sonder avec `tools/probe-*.js`.
- `UNKNOWN` : comportement multi-écrans du mini-lecteur non testé ; suite UPDATE non exécutable en dev (`setupUpdater` garde `if (!app.isPackaged) return`).

## 11. Décisions techniques importantes
- **Pas de framework front** (vanilla JS) : démarrage rapide, taille réduite, contrôle total du design.
- **InnerTube plutôt que yt-dlp pour la recherche** : yt-dlp 2026.06 a supprimé `ytmsearch` ; InnerTube donne artiste/album/durée/pochettes + pagination + page artiste.
- **Paroles + page artiste côté main** (Node) : évite les contraintes CSP du renderer.
- **`store.plays` additif** : champ ajouté sans casser les bibliothèques existantes (défaut `{}`).
- **Playlists intelligentes virtuelles** (calculées, non stockées) : pas de migration de schéma, toujours à jour.
- **Publication via Actions** : contourne l'upload local lent. Artefact fixe `Music-DL-Setup.exe` (lien permanent landing).

## 12. Conventions
- Commits FR : `feat(EX):` / `fix(EX):` / `chore:` … signés `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Pas d'apostrophes/guillemets typographiques ni d'emojis dans les messages de commit** (cassent PowerShell). ⚠️ Dans l'outil Bash (git-bash), utiliser un **heredoc** `git commit -F - <<'EOF' … EOF`, **pas** la syntaxe here-string PowerShell `@'…'@` (elle laisse un `@` parasite dans le sujet).
- Hooks de test E2E via `window.MDL_TEST` ; lanceurs par variables d'env : `MUSICDL_E2E` (parcours complet), `_UPDATE`, `_TORTURE`, `_MINI`, `_LYRICS`, **`_ARTIST`**, **`_QUEUE`**, **`_SMART`** ; `MUSICDL_SHOT_DIR` (sortie captures + rapports).
- Lancer une suite : `MUSICDL_E2E_X=1 MUSICDL_SHOT_DIR="<dir>" npx electron .` (après avoir tué les zombies, cf §10).
- IDs DOM en kebab-case ; classes CSS préfixées par zone (`gl-`, `ply-`, `rc-`, `col-`, `pl-`, `art-`, `qrow-`, `qpanel-`, `news-`, `faq-`…).

## 13. Dépendances & versions critiques
- `electron ^42.4.0`, `electron-builder ^26.15.2`, `electron-updater ^6.8.9`, `sharp ^0.35.1`, `png-to-ico ^3.0.1`.
- Node v25 / npm 11 (machine de dev). yt-dlp `2026.06.09`. ffmpeg essentials (gyan.dev).
- Build : `npm run dist` (NSIS, `oneClick:false`, raccourcis bureau+menu).

## 14. Éléments INTERDITS à modifier sans raison critique
- Schéma `store.json` existant (compat ascendante des bibliothèques utilisateurs). Ajouts additifs OK (ex. `plays`).
- Nom d'artefact `Music-DL-Setup.exe` et bloc `publish` GitHub (casse l'auto-update et la landing).
- Protocole `mdl://` + support Range (casse le seek et l'affichage des fichiers locaux).
- `appId: com.advm.musicdl` (identité de mise à jour).
- Le pont preload (`contextIsolation`/`nodeIntegration`) — sécurité.

---

## 🧠 START_PROJECT_CONTEXT (bloc de reprise autonome)
```
PROJET: Music DL — app Windows Electron de telechargement/lecture YouTube Music (FR, sans abonnement).
REPO: github.com/Advm000/musicdl (public, branche main). Landing: advm000.github.io/musicdl (GitHub Pages /docs).
VERSION PUBLIEE: v1.1.0. EN COURS: v1.2 (Gate0+E1+E2+E3+E4+E5+E7 FAITS et commites ; reste E8 puis E9).
STACK: Electron 42 (main+preload+renderer vanilla JS, pas de framework). Persistance = %APPDATA%/Music DL/store.json
  (settings/library/playlists/recents/plays) + covers/ + lyrics/. Binaires bin/ (yt-dlp,ffmpeg) gitignored -> tools/fetch-bins.ps1.
FICHIERS CLES: src/main.js (backend+E2E), src/preload.js (window.mdl.*), src/renderer/{app.js,index.html,styles.css,mini.html,mini.js},
  docs/index.html (landing 3D), .github/workflows/release.yml.
RECHERCHE = API InnerTube YouTube Music (WEB_REMIX), filtres params songs/albums/artists/playlists, pagination via body.continuation.
  Repli yt-dlp ytsearch. PAGE ARTISTE = getArtist/getArtistByName (browse InnerTube). Paroles = LRCLIB (cote main).
  Telechargement + preecoute = yt-dlp+ffmpeg embarques.
LECTEUR: <audio> unique, playQueue+playPos, onLoadFail anti-blocage, seek via mdl:// + Range.
FILE D'ATTENTE (E4): panneau #qpanel, drag&drop, moveInQueue/removeFromQueue/clearQueueExceptCurrent, clic droit Lire ensuite/Ajouter.
PLAYLISTS AUTO (E5): store.plays{id->count} (incremente a 50% dans timeupdate, 1x/lecture via garde playCountedId).
  smartPlaylists() = 3 listes virtuelles calculees au rendu ; findPlaylist() route __fav/__recent/__top. goPage re-rend a la navigation.
TESTS: window.MDL_TEST.* + env MUSICDL_E2E[_UPDATE|_TORTURE|_MINI|_LYRICS|_ARTIST|_QUEUE|_SMART], MUSICDL_SHOT_DIR.
  Lancer: tuer zombies (PowerShell Get-Process -Name 'Music DL','electron' | Stop-Process -Force) PUIS
  MUSICDL_E2E_X=1 MUSICDL_SHOT_DIR='<dir>' npx electron .  (verrou single-instance : sinon exit 0 sans rien faire).
RELEASE (E9): npm version 1.2.0 -> commit/push -> creer GitHub Release tag vX.Y.Z -> declencher release.yml (workflow_dispatch).
  NE PAS uploader l'exe en local. Artefact fixe Music-DL-Setup.exe + latest.yml + .blockmap.
COMMITS: messages FR sans apostrophe typo/emoji. Outil Bash = heredoc git commit -F - <<'EOF' (PAS @'...'@ PowerShell).
  Signer Co-Authored-By: Claude Opus 4.8.
INTERDITS: schema store.json existant, nom artefact exe, protocole mdl://+Range, appId, pont preload.
PROCHAINE ACTION IMMEDIATE: E8 — etendre runE2E (src/main.js) pour couvrir page artiste, file d'attente, playlists auto,
  + une assertion sur la HAUTEUR rendue des paroles (la classe du bug paroles ne doit pas revenir). Puis E9 release 1.2.0.
PROTOCOLE: rester actif, annoncer chaque etape, captures de preuve, app laissee ouverte apres E3/E7 pour test boss,
  signe de vie <=15 min. Detail: PLAN-V1.2.md.
```
