# BUGS.md — Bugs, causes, correctifs, leçons (Music DL)

> Base : v1.2.0 stable. Détail v1.2 : `HANDOFF.md §10`.

## Risques ouverts
| # | Sujet | Statut | Note |
|---|-------|--------|------|
| L1 | `saveStore` non atomique en v1.2.0 | LATENT | `fs.writeFileSync(STORE_FILE, …)` direct (`main.js:47`) ; un crash en cours d'écriture peut tronquer `store.json`. L'écriture atomique (tmp+rename) + backup corruption faisaient partie du socle v1.3 **annulé**. À reconsidérer si reprise. |

## Contraintes environnementales connues (non-bugs)
- **Verrou single-instance** : une instance « Music DL » (ou zombie après test tué) fait quitter toute nouvelle instance (exit 0, rien écrit). Tuer les zombies avant E2E.
- **État dev pollué** : si `%APPDATA%/Music DL/store.json` référence des titres dont les fichiers n'existent plus (dossier musique vide), l'E2E peut échouer à tort (« Déjà téléchargée » au re-DL + lecture d'un fichier absent). Lancer l'E2E avec `--user-data-dir` isolé.
- **Upload local installeur (166 Mo)** échoue sur connexion lente → publier via GitHub Actions uniquement.
- **App non signée** → SmartScreen Windows (documenté dans la FAQ landing).
- Rapports `*-report.json` remplis d'octets nuls si le process est tué pendant l'écriture → relancer à froid.
- InnerTube/`params` peuvent changer côté Google → repli `yt-dlp ytsearch` ; re-sonder via `tools/probe-*.js`.
- `UNKNOWN` : mini-lecteur multi-écrans non testé ; suite UPDATE non lançable en dev (`if (!app.isPackaged) return`).

## Corrigés (v1.2.0)
- Blocage « fichier introuvable » ; boucle de file cassée ; file non nettoyée à la suppression (É0).
- Paroles karaoké invisibles (CSS hauteur panneau fixe 220px).
- Boutons télécharger manquants page artiste (collision d'id → `refreshCard` touche toutes les cartes `[data-id]`).
- Bas du mini-lecteur rogné (fenêtre 396→420). Playlists intelligentes non rafraîchies (`goPage` re-rend).

## Décisions / leçons
- **v1.3 abandonné (2026-06-17)** : socle online + refonte landing annulés, retour à v1.2.0. Vérifié en amont que le socle v1.3 fonctionnait (E2E état propre) ; abandon = choix produit, pas un bug.
- Recherche : `yt-dlp ytmsearch` supprimé en 2026.06 → InnerTube `WEB_REMIX` (repli `ytsearch`).
- Toujours penser compat ascendante `store.json` (champs additifs, défauts réinjectés par `loadStore`).
- Fiabilité store : en v1.2.0, `saveStore` écrit en direct (non atomique) ; le `loadStore` réinjecte les défauts pour tout champ manquant (compat ascendante) mais ne sauvegarde pas un store illisible avant fallback. Améliorations (atomique + backup) étaient dans le socle v1.3 annulé (cf L1).
