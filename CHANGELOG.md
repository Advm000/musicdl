# CHANGELOG — Music DL

Format : Keep a Changelog (FR). Versions = tags GitHub.

## [Non publié] — v1.3.0 (en cours, NON commité au moment de la 1ère rédaction, NON poussé)
> Démarré en « consolidation sans nouvelle option », périmètre **élargi à la demande du boss** : socle online + page Découvertes. Vérifié par 8 suites E2E (voir HANDOFF §15). `src/` actuel = v1.2.0 + tout ce qui suit.
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
### Socle ONLINE (réintroduit, scoped) — réfs en ligne sans téléchargement
- `store.onlineMeta` (+ flag `saved` pour albums enregistrés, `fav` pour favoris) ; `resolveTrack`/`isFavAny`/`loadOnlineTrack` (lecture **streaming** via `preview:get`).
- **Favoris online** (`online:setFav`) + **ajout playlist online** (`playlist:addTrack` meta) — boutons ♥/➕ sur les cartes de recherche (titres).
- Cartes **album/playlist** (recherche) : ⬇ télécharger tout · ♥ favori tout · ➕ (**album → onglet Albums** `saved` ; **playlist → playlist enregistrée**).
- **Téléchargement par titre** (bouton ⬇ sur chaque ligne online) **et global** (en-tête album, barre playlist `#pld-dl`, cartes).
- `forgetOnline` (`online:remove`) ; un titre online téléchargé devient local (dl:done supprime l'entrée onlineMeta, conserve le favori).
### Page « Pour toi » (nouvelle page 3) — découvertes
- `store.interests` (artistes consultés, `interest:add`) ; algo `discover` : pool des top titres/albums des artistes d'intérêt (pondération récence + boost collaborations) + expansion des **artistes liés** (`collectRelatedArtists` dans `getArtist`).
- Bannière artiste cliquable (onglet Titres) → page artiste.
### Tests
- Nouvelle suite **`MUSICDL_E2E_ONLINE`** (`runOnlineE2E`) : favoris/playlists online, album sauvegardé, classifieur, **page Pour toi**, streaming, téléchargement titre+global, sélection/suppression. ✅ 15/15 étapes.

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
