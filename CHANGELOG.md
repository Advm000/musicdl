# CHANGELOG — Music DL

Format : Keep a Changelog (FR). Versions = tags GitHub.

## [1.3.0] — 2026-06-26
> Consolidation (fiabilité, bugs, lecteur, bibliothèque) + socle online (streaming/favoris/playlists/albums) + **lecture en ligne accélérée** + **stockage des titres dans les données de l'app (style Spotify)** + **désinstallation propre**. La page « Pour toi » a été **retirée**. Vérifié par robots E2E (ONLINE 14/14, QUEUE, FULL) — zéro erreur JS.
### Fiabilité
- `saveStore` **atomique** (`.tmp` + `rename`) ; `loadStore` sauvegarde `store.json.corrupt-<ts>` avant repli (anti-perte de bibliothèque).
### Bugs corrigés
- Clic « favori » barre lecteur n'ouvre plus le grand lecteur (`stopPropagation` sur `#ply-fav`/`#gl-fav`).
- Re-téléchargement conserve favori / ancienneté / paroles (plus de reset).
- Reprise de lecture : le seek de reprise est annulé par une vraie lecture + gardé sur le bon titre (corrige un faux compteur d'écoutes).
### Lecteur / file
- File d'attente : réordonnancement par déplacement DOM en place (fluide 30+).
- Reprise de la dernière lecture au démarrage (titre + position, en pause) ; raccourcis ←/→ (préc./suiv.).
- Marquage « fichier introuvable » (grisé, non lançable, auto-rétabli si rejoue).
### Bibliothèque
- Onglets **Titres / Albums** ; **analyseur albums/singles** (`classifyAlbums` : album = ≥2 titres distincts sous un vrai nom d'album, sinon single).
- **Mode sélection + suppression groupée** (`library:deleteMany`) ; boutons d'action **toujours visibles**.
### Socle ONLINE — réfs en ligne sans téléchargement
- `store.onlineMeta` (+ flag `saved` pour albums enregistrés, `fav` pour favoris) ; lecture **streaming** via `preview:get`.
- **Favoris online** (`online:setFav`) + **ajout playlist online** — boutons ♥/➕ sur les cartes de recherche.
- Cartes **album/playlist** : ⬇ télécharger tout · ♥ favori tout · ➕ (album → onglet Albums ; playlist → playlist enregistrée).
- **Téléchargement par titre et global** ; un titre online téléchargé devient local (conserve le favori).
### Lecture en ligne accélérée (NOUVEAU)
- **Préchargement** du lien de stream : au **survol** d'une carte, sur le **titre suivant** de la file, et à l'**ouverture d'un album/playlist en ligne** → lecture quasi instantanée.
- `warmYtdlp` au démarrage ; fusion des requêtes concurrentes (`previewInflight`) ; indicateur **« Chargement… »** dans le lecteur (plus jamais figé).
### Stockage style Spotify (NOUVEAU)
- Les titres téléchargés vivent désormais dans les **données de l'app** (`%APPDATA%/Music DL/media/<id>.<ext>`), **cachés** — plus de dossier visible. Réglage « dossier de téléchargement » retiré ; « Ouvrir le dossier » pointe sur la boîte de l'app. Anciens titres (dossier visible) toujours lisibles (compat).
### Désinstallation (NOUVEAU)
- `deleteAppDataOnUninstall: true` : **désinstaller efface toutes les données** de l'app (prépare le futur système de comptes). Les **mises à jour ne touchent pas** aux données.
### Retiré
- **Page « Pour toi »** entièrement supprimée (UI, navigation, moteur de goût/genres, radio, mixes, feed YT, ADN, handlers IPC, CSS, suite E2E `DISCOVER`). Le préchargement/streaming partagé est conservé.
### Tests
- Robots E2E rejoués : **ONLINE 14/14** (favoris/playlists/albums online, classifieur, streaming, téléchargement, suppression groupée), **QUEUE** ok, **FULL** ok (lecture locale, lecteur, minuteur, mini-lecteur, albums). **Zéro erreur JS.**

## [Historique] — 2026-06-17 : abandon de l'ancien v1.3
### Retiré
- **Abandon complet de l'ancien v1.3 « online »** (décision boss) : retour intégral à la base stable v1.2.0, avant de relancer le v1.3 « consolidation » ci-dessus.
  - Socle applicatif v1.3 annulé : `store.onlineMeta`, `reconcileLibrary` (rescan/relink), `resolveTrack`/`loadAt`/`loadPreviewTrack`, badges en ligne/hors-ligne, multi-sélection + `library:deleteMany`, favoris online, `collection:downloadAll`, `album:fav`, `playlist:addTrack(meta)`, `playlist:reorder`, bouton « + playlist » barre lecteur.
  - Refonte SaaS de la landing annulée : `docs/index.html` ramené au contenu v1.2.0 (fond WebGL/Three.js).
  - `PLAN-V1.3.md` supprimé. `HANDOFF.md` mis à jour (v1.3 abandonné).
- Méthode : `git reset` des 3 commits v1.3 non poussés + restauration `docs/index.html` depuis le tag `v1.2.0`. `src/` désormais identique à v1.2.0.
### Note
- Non poussé. Pour aligner le site GitHub Pages live (actuellement la refonte landing sur `origin/main`), il faudra pousser — en attente du GO du boss.

## [1.2.0] — 2026-06-14 (Latest, base stable courante)
### Ajouté
- Page artiste (top titres + discographie), playlists intelligentes virtuelles (favoris/récents/top), compteur d'écoutes (`store.plays`), file d'attente (drag&drop + menu contextuel), mini-lecteur.
### Corrigé
- Blocage fichier introuvable, boucle de file, file non nettoyée à la suppression, paroles karaoké invisibles, boutons DL page artiste, mini-lecteur rogné, playlists auto non rafraîchies.
### Technique
- Recherche migrée vers InnerTube `WEB_REMIX` (yt-dlp `ytmsearch` supprimé). Publication via GitHub Actions.

## [1.0.0]
- Première version publiée (recherche, téléchargement, lecteur, bibliothèque, paroles, auto-update, landing).
