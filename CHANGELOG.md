# CHANGELOG — Music DL

Format : Keep a Changelog (FR). Versions = tags GitHub.

## [Non publié] — 2026-06-17
### Retiré
- **Abandon complet de v1.3** (décision boss) : retour intégral à la base stable v1.2.0.
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
