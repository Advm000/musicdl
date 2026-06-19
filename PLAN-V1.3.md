# PLAN v1.3 — « Consolidation propre » (upgrade, pas de nouvelles options)

> ✅ **ÉTAT 2026-06-17 : Lots A–E implémentés + vérifiés E2E.** Le périmètre a ensuite été **élargi à la demande du boss** (socle online : favoris/playlists/albums en ligne + lecture streaming ; page « Pour toi »). **L'état réel et exhaustif du v1.3 est dans `HANDOFF.md §15` et `CHANGELOG.md`** — ce plan ci-dessous est le périmètre initial (référence). Tout est dans `src/`, à commiter/pousser selon le boss.

> Base : v1.2.0 stable. Règle initiale : pas de nouvelle option (assouplie ensuite). Tout reste 100 % compatible `store.json` (ajouts additifs uniquement).

## Principe
- On ne change pas la surface de l'app (mêmes écrans, mêmes boutons).
- Chaque chantier = un bug réel, une faille de fiabilité, une lenteur, ou une finition manquante d'une fonction **déjà présente**.
- Livraison en une seule fois (petit périmètre).

---

## LOT A — Fiabilité (priorité 1, invisible mais critique)
| Réf | Chantier | Pourquoi | Où | Risque |
|-----|----------|----------|-----|--------|
| A1 | **`saveStore` atomique** (écrire `store.json.tmp` puis `fs.renameSync`) | Aujourd'hui écriture directe : un crash en cours d'écriture tronque le fichier → perte totale de la bibliothèque | `main.js:46` | Aucun (interne) |
| A2 | **`loadStore` : sauvegarde avant fallback** (copier en `store.json.corrupt-<ts>` si JSON illisible, au lieu de repartir en silence sur un store vide) | Ne plus jamais perdre une bibliothèque en silence ; récupérable | `main.js:32` | Aucun |
| A3 | **Feedback fichier manquant** : quand un fichier local a disparu, la lecture s'arrête sans rien dire → afficher un toast clair (« fichier introuvable ») + marquer le titre concerné comme indisponible dans la bibliothèque | Comportement existant trop silencieux après une désinstallation/déplacement | `app.js` (onLoadFail / `renderLibrary`) | Faible |

## LOT B — Bugs confirmés (priorité 1)
| Réf | Chantier | Pourquoi | Où | Risque |
|-----|----------|----------|-----|--------|
| B1 | **Clic « favori » barre lecteur ouvre le grand lecteur** : ajouter `e.stopPropagation()` au handler `#ply-fav` (et `#gl-fav` si même cas) | `#ply-fav` est imbriqué dans `#ply-left` (clic = ouvre le grand lecteur) | `app.js:1285`, `index.html:380` | Aucun |
| B2 | **Audit du reset favori au re-téléchargement** : vérifier que re-télécharger un titre déjà aimé conserve `favorite` | Un re-DL ne doit pas effacer un favori | `main.js:~749` | Faible |

## LOT C — Performance (priorité 2)
| Réf | Chantier | Pourquoi | Où | Risque |
|-----|----------|----------|-----|--------|
| C1 | **Audit `renderQueue()`** : si la file est entièrement re-rendue (innerHTML) à chaque déplacement, optimiser (déplacer le nœud DOM, pas de re-render global) pour rester fluide à 30+ titres | Lenteur perçue sur grosses files | `app.js:787` | Faible |

## LOT D — Finition de l'existant (priorité 3)
| Réf | Chantier | Pourquoi | Où | Risque |
|-----|----------|----------|-----|--------|
| D1 | **Messages d'erreur soignés** : uniformiser/clarifier les erreurs réseau et de recherche (texte humain, pas brut) | Lisibilité | `app.js` (setSearchState 'error'), `main.js:643` | Aucun |
| D2 | **Marquage « indisponible » en bibliothèque** (lié à A3) : titre dont le fichier manque grisé + non lançable, sans le supprimer | Cohérence après A3 | `app.js` `renderLibrary` | Faible |
| D3 | **Passe de cohérence visuelle** légère (alignements/états de focus déjà existants) | Polish sans nouvelle UI | `styles.css` | Aucun |

## LOT E — Complétude optionnelle (à décider par le boss — borderline « nouveau comportement »)
> À n'inclure que si tu valides ; sinon on s'en tient à A–D.
| Réf | Chantier | Note |
|-----|----------|------|
| E1 | **Reprendre la dernière lecture au lancement** (dernier titre + position) | Manque courant d'un lecteur ; additif dans `settings`. C'est un *comportement* en plus → optionnel. |
| E2 | **Raccourcis clavier** (espace = play/pause, flèches = précédent/suivant) | Confort ; pas de nouvelle UI mais nouveau comportement → optionnel. |

---

## HORS PÉRIMÈTRE (ce sont de « nouvelles options » → exclus de ce v1.3)
- Socle online / favoris online / `onlineMeta` (le gros v1.3 précédent, annulé).
- Multi-sélection + suppression groupée ; bouton « Re-lier le dossier ».
- Annuler / réessayer un téléchargement ; nombre de DL parallèles configurable.
- Mode Radio ; lancement au démarrage de Windows ; détection de doublons / espace disque.
- Refonte de la landing.

---

## Impact `store.json`
- Aucun champ existant modifié.
- A3/D2 : champ optionnel `missing` (toléré par `loadStore`, défaut absent).
- E1 (si retenu) : `settings.lastTrack`/`lastPos` additifs.

## Ordre & jalon
```
v1.3.0  =  Lot A  ->  Lot B  ->  Lot C  ->  Lot D   (+ E1/E2 si validés)
```
Estimation : ~2–3 jours (A+B+C+D). E1/E2 : +0,5 j.

## Tests (anti-régression)
- E2E complet sur **user-data isolé** (`--user-data-dir`) après chaque lot : recherche → téléchargement → lecture → albums.
- Scénarios ciblés : crash simulé pendant `saveStore` (A1), store corrompu au boot (A2), fichier supprimé puis lecture (A3/D2), clic favori barre lecteur (B1), file 30+ réordonnée (C1).
- Vérifier compat ascendante d'un `store.json` v1.2.0 réel.

## Release
- `npm version 1.3.0` → commit/push → Release GitHub → `release.yml`. Jamais d'upload local de l'exe.

## Décisions en attente du boss
1. On inclut **E1/E2** (reprise lecture / raccourcis) ou v1.3 = strictement A–D ?
2. Fichier manquant (A3/D2) : **marquer** (recommandé) ou ignorer/supprimer ?
