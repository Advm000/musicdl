# CHANGELOG — Music DL

Format : Keep a Changelog (FR). Versions = tags GitHub.

## [Non publié] — v1.3.0 « Consolidation propre » (en cours, non poussé)
> Upgrade/fiabilisation de l'existant, **aucune nouvelle option**. Vérifié E2E (parcours complet + file d'attente) sur user-data isolé.
### Ajouté
- Reprise de la dernière lecture au démarrage (dernier titre + position, en pause). [E1]
- Raccourcis clavier ←/→ (titre précédent / suivant) ; Espace (lecture/pause) existait déjà. [E2]
- Marquage « fichier introuvable » des titres dont le fichier local a disparu : grisés et non lançables, rétabli automatiquement si le fichier rejoue. [A3/D2]
### Corrigé
- Clic « favori » dans la barre du lecteur n'ouvre plus le grand lecteur (`stopPropagation`). [B1]
- Re-téléchargement d'un titre : conserve le favori / l'ancienneté / les paroles (plus de reset à `false`). [B2]
### Fiabilité
- `saveStore` **atomique** (écriture `.tmp` + `rename`) — un crash en cours d'écriture ne peut plus tronquer `store.json`. [A1]
- `loadStore` sauvegarde `store.json.corrupt-<ts>` avant tout repli sur les défauts (plus de perte silencieuse). [A2]
### Performance
- File d'attente : réordonnancement par **déplacement DOM en place** au lieu d'une reconstruction complète — fluide à 30+ titres. [C1]

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
