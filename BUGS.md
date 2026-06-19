# BUGS.md — Bugs, causes, correctifs, leçons (Music DL)

> Base : v1.2.0 stable. Détail v1.2 : `HANDOFF.md §10`.

## Risques ouverts
| # | Sujet | Statut | Note |
|---|-------|--------|------|
| L1 | `saveStore` non atomique | ✅ RÉSOLU (v1.3 conso) | Écriture atomique tmp+rename (`main.js:46`) + `loadStore` backup `store.json.corrupt-<ts>` (`main.js:32`). Vérifié E2E. |
| B1 | Clic « favori » barre lecteur ouvrait le grand lecteur | ✅ RÉSOLU (v1.3 conso) | `stopPropagation` sur `#ply-fav`/`#gl-fav` (`app.js`). |
| B2 | Re-téléchargement réinitialisait le favori | ✅ RÉSOLU (v1.3 conso) | Conserve favori/ancienneté/paroles depuis l'entrée existante (`main.js`). E2E favori final=true. |
| B3 | Reprise de lecture : seek non annulé par une vraie lecture | ✅ RÉSOLU (v1.3) | `restoreLastTrack` : `loadedmetadata` gardé sur le titre restauré + `restoring=false` dans `loadTrack`/`loadOnlineTrack`. C'était la cause du faux échec « compteur 0→0 » de la suite smart. |
| B4 | Playlist online polluait l'onglet Albums (en Singles) | ✅ RÉSOLU (v1.3) | Flag `onlineMeta.saved` : l'onglet Albums n'affiche que library + albums explicitement enregistrés (➕). Playlists/favoris restent à leur place. |

## Statut tests (session v1.3, 2026-06-17)
- 8 suites E2E sur `--user-data-dir` isolé. `online` (nouvelle) ✅ 15/15. `full/artist/queue/smart/torture/mini` ✅.
- `lyrics` = **faux échec** : pistes de test = Drumless (instrumentales) → 0 paroles LRCLIB ; le rendu (panneau 220px) fonctionne.
- `full` peut flaker sur le **dernier** pas (« album complet 11-13/13 ») = lenteur de téléchargement réseau, **pas un bug** (le code de DL est inchangé).

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
- Fiabilité store : depuis le v1.3 consolidation, `saveStore` est atomique (tmp+rename) et `loadStore` sauvegarde un store illisible (`store.json.corrupt-<ts>`) avant repli. `loadStore` réinjecte toujours les défauts pour tout champ manquant (compat ascendante).
