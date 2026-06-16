# RULES.md — Standards & contraintes (Music DL)

> Base : v1.2.0 stable. Voir `HANDOFF.md §14` pour les zones interdites.

## Priorités absolues (jamais sacrifier une supérieure pour une inférieure)
1. Stabilité 2. Cohérence produit 3. Qualité du code 4. Maintenabilité 5. Performance 6. Sécurité 7. Nouvelles fonctionnalités.

## Zones critiques — INTERDIT de modifier sans raison critique
- **Schéma `store.json` existant** : compat ascendante des bibliothèques. Ajouts **additifs uniquement** (jamais renommer/supprimer un champ). Anciens stores chargés sans migration.
- **Nom d'artefact `Music-DL-Setup.exe`** + bloc `publish` GitHub : casse l'auto-update et la landing.
- **Protocole `mdl://` + support Range** : casse le seek et la lecture locale.
- **`appId: com.advm.musicdl`** : identité de mise à jour.
- **Pont preload** (`contextIsolation:true`, `nodeIntegration:false`) : sécurité. Toute capacité passe par un IPC nommé + exposition explicite dans `preload.js`.

## Règles d'architecture
- Pas de framework front : vanilla JS.
- Tout accès Node depuis le renderer via `window.mdl.*` (preload) → `ipcMain.handle` (main). Aucun `require` Node dans le renderer.
- Logique réseau/fichiers (InnerTube, lyrics, yt-dlp, fs) **côté main** uniquement.
- IDs DOM kebab-case ; classes CSS préfixées par zone (`gl-`, `ply-`, `rc-`, `col-`, `pl-`, `art-`, `qrow-`, `qpanel-`, `news-`, `faq-`).

## Règles de qualité (avant chaque livraison)
- `node --check` OK sur `main.js`, `preload.js`, `app.js`, `mini.js`.
- Chaque `mdl.X` du renderer existe dans `preload.js` et pointe vers un `ipcMain.handle` réel (et inversement, pas de handler mort).
- Vérifier : imports, dépendances, régressions, impacts indirects, cohérence avec `MASTER.md`.
- Anti-régression : téléchargement, favoris/écoutes/playlists, seek `mdl://`, compat `store.json`.

## Tests E2E
- Harness `window.MDL_TEST.*`. Env : `MUSICDL_E2E` (complet), `_UPDATE`/`_TORTURE`/`_MINI`/`_LYRICS`/`_ARTIST`/`_QUEUE`/`_SMART` ; sortie `MUSICDL_SHOT_DIR`.
- **Tuer les zombies avant** (verrou single-instance) : `Get-Process -Name 'Music DL','electron' -EA SilentlyContinue | Stop-Process -Force`.
- **État dev pollué = faux négatif** : si `%APPDATA%/Music DL` contient une bibliothèque orpheline (dossier musique vide), l'E2E échoue à tort → lancer avec un **`--user-data-dir` isolé**.
- Lancer via le binaire direct `./node_modules/electron/dist/electron.exe .`. Suite UPDATE non lançable en dev (`if (!app.isPackaged) return`).

## Conventions de commit
- FR : `feat(zone):` / `fix(zone):` / `chore:` / `refactor(zone):` / `docs:`. Signés `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Aucune apostrophe/guillemet typographique ni emoji** (cassent PowerShell).
- Outil Bash (git-bash) : `git commit -F - <<'EOF' … EOF`, JAMAIS la here-string PowerShell `@'…'@`.
- Commiter/pousser **uniquement sur demande explicite du boss**.

## Release
- `npm version X.Y.Z` → commit/push → Release GitHub → déclencher `release.yml`. Vérifier `latest.yml` + exe + landing.
- **NE JAMAIS uploader l'installeur en local**.

## Bonnes pratiques
- Comprendre → analyser → vérifier impacts → modifier le minimum. Réutiliser l'existant. Pas de refactoring/dépendance/duplication inutiles.
