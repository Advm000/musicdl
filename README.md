<div align="center">

# Music DL — v3.1.0

**Téléchargeur de musique Windows · YouTube → MP3 320 kbps**

[![Release](https://img.shields.io/github/v/release/Advm000/musicdl?label=version&color=7c3aed)](https://github.com/Advm000/musicdl/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)](https://github.com/Advm000/musicdl/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**[Télécharger](https://github.com/Advm000/musicdl/releases/latest/download/MusicDL-Setup.exe)** · **[Landing Page](https://musicdl-official.netlify.app)** · **[Releases](https://github.com/Advm000/musicdl/releases)**

</div>

---

## Aperçu

Music DL est une application Windows qui permet de rechercher et télécharger de la musique depuis YouTube en MP3 haute qualité (320 kbps), avec pochettes, métadonnées, bibliothèque et playlists intégrées. Interface premium glassmorphism violet/cyan, mise à jour automatique.

---

## Fonctionnalités

### Recherche
- Recherche YouTube en temps réel (jusqu'à 50 résultats)
- Autocomplétion des suggestions (Google/YouTube)
- Aperçu : miniature, durée, chaîne, nombre de vues
- Téléchargement multiple simultané
- Annulation de téléchargement en cours
- Barre de progression en temps réel (vitesse + ETA)

### Téléchargement
- Format : **MP3 320 kbps** (meilleure qualité)
- Pochette intégrée automatiquement dans le fichier
- Métadonnées complètes : titre, artiste, album (ID3)
- Conversion FFmpeg embarquée (aucune installation requise)
- Stockage dans `AppData\Local\MusicDL` (invisible dans les dossiers système)

### Bibliothèque
- Vue tableau style Spotify (numéro, titre, artiste, album, durée, taille)
- Recherche instantanée dans la bibliothèque
- Tri : date, titre, artiste, favoris
- Sélection multiple + suppression groupée
- Favoris (filtre dédié)
- Ajout rapide à une playlist via menu contextuel
- Lecture directe depuis la bibliothèque

### Playlists
- Création, renommage, suppression de playlists
- Glisser-déposer pour réordonner les pistes
- Vue détail avec liste complète
- Lecture de playlist entière dans l'ordre

### Lecteur audio intégré
- Mini-player persistant en bas d'écran
- Contrôles : lecture/pause, précédent, suivant, shuffle, répétition
- Barre de progression cliquable (seek)
- Affichage : pochette, titre, artiste, durée
- File de lecture (queue) automatique
- Animations boutons (bounce + ripple)

### Mise à jour automatique
- Vérification au démarrage (6 secondes après lancement)
- Téléchargement silencieux en arrière-plan
- Notification dans l'app + installation au redémarrage
- Powered by `electron-updater` + GitHub Releases

### Divers
- Vérification connectivité internet (ping Google)
- Profil appareil unique (device ID, hostname, OS, date installation)
- Gestion des erreurs et annulations robuste
- Une seule instance (focus si déjà ouvert)
- Écran de chargement animé au démarrage

---

## Interface

| Onglet | Contenu |
|---|---|
| **RECHERCHE** | Barre de recherche + suggestions + résultats YouTube |
| **BIBLIOTHÈQUE** | Tous les MP3 téléchargés, Spotify-style |
| **PLAYLISTS** | Gestion complète des playlists |

**Design** : Glassmorphism · Thème violet (`#7c3aed`) / cyan (`#06b6d4`) · Animations CSS fluides · Police Inter · Swipe mobile

---

## Architecture technique

```
MusicDownloader.py          ← Backend Flask (Python 3.11)
├── API REST (/api/*)       ← Toutes les routes
├── HTML/CSS/JS (inline)    ← Interface complète embarquée
└── Logique métier          ← Download, tags, library, playlists

electron/
├── main.js                 ← Wrapper Electron (lance Flask, auto-update)
├── preload.js              ← Bridge IPC sécurisé
└── package.json            ← v3.1.0

musicdl.spec                ← Config PyInstaller 6.x
.github/workflows/release.yml ← CI/CD GitHub Actions
```

### Stack
| Composant | Technologie |
|---|---|
| Backend | Python 3.11 · Flask 3 |
| Téléchargement | yt-dlp |
| Audio | FFmpeg (imageio-ffmpeg) · mutagen |
| Frontend | HTML/CSS/JS vanilla (inline dans Python) |
| Desktop | Electron 28 · electron-updater |
| Packaging | PyInstaller 6 → MusicDL.exe · electron-builder → Setup.exe |
| CI/CD | GitHub Actions (Windows) |

### API Routes

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Interface principale |
| GET | `/api/search?q=&n=` | Recherche YouTube |
| GET | `/api/suggest?q=` | Autocomplétion |
| POST | `/api/download` | Lancer un téléchargement |
| GET | `/api/progress/:job_id` | Progression SSE |
| POST | `/api/cancel/:job_id` | Annuler |
| GET | `/api/library` | Liste des MP3 |
| GET | `/api/stream/:filename` | Lecture audio |
| GET | `/api/cover/:filename` | Pochette |
| DELETE | `/api/delete/:filename` | Supprimer |
| GET/POST | `/api/favorites/*` | Favoris |
| GET/POST/DELETE | `/api/playlists/*` | Playlists |
| GET | `/api/yt/url/:vid` | URL stream YouTube |
| GET | `/api/version` | Version app |
| GET | `/api/ping` | Test connectivité |
| GET | `/api/device` | Profil appareil |
| POST | `/api/quit` | Arrêt propre |

### Stockage
```
%LOCALAPPDATA%\MusicDL\
├── *.mp3               ← Musiques téléchargées
├── .favorites.json     ← Liste des favoris
├── .playlists.json     ← Playlists et leur contenu
├── device.json         ← Profil appareil
└── backend.log         ← Logs Electron/Flask
```

---

## Installation

### Utilisateur
1. Télécharger **[MusicDL-Setup.exe](https://github.com/Advm000/musicdl/releases/latest/download/MusicDL-Setup.exe)**
2. Lancer l'installeur
3. L'application démarre — les mises à jour se font **automatiquement**

**Requis** : Windows 10 / 11 (64-bit) · Connexion internet

### Développement
```bash
# Prérequis : Python 3.11, Node.js 20

# Backend
pip install -r requirements.txt

# Lancer en dev
python MusicDownloader.py

# Build complet
pyinstaller musicdl.spec --noconfirm --clean
cd electron && npm install && npm run build
```

---

## Build & Release

Le pipeline GitHub Actions se déclenche sur chaque tag `v*` :

```
1. Setup Python 3.11 + Node.js 20
2. pip install requirements + pyinstaller>=6.0,<7
3. pyinstaller musicdl.spec → dist/MusicDL/MusicDL.exe
4. npm install + génération icône SVG→PNG
5. electron-builder → MusicDL-Setup.exe
6. Création GitHub Release + upload assets
```

Pour publier une nouvelle version :
```bash
# Bumper APP_VERSION dans MusicDownloader.py
# Bumper version dans electron/package.json
git tag v3.x.x && git push origin v3.x.x
```

---

## Liens

| | Lien |
|---|---|
| Landing page | https://musicdl-official.netlify.app |
| Téléchargement direct | https://musicdl-official.netlify.app/download |
| GitHub Releases | https://github.com/Advm000/musicdl/releases |
| Lien court | https://tinyurl.com/2awfek5b |

---

## Changelog

| Version | Changements |
|---|---|
| **v3.1.0** | Suppression page Accueil — app plus légère et rapide |
| v3.0.1 | Covers mosaïque 2×2 (miniatures des pistes) |
| v3.0.0 | Playlists artistes auto-générées depuis la bibliothèque |
| v2.9.0 | Page Accueil ultra-pro (50 tracks/playlist, Mood, Throwback) |
| v2.8.6 | Fix SyntaxError Python 3.11 (f-string + backslash) |
| v2.8.0 | Mise à jour automatique (electron-updater) |
| v2.7.0 | Playlists complètes + lecteur audio intégré |
| v1.0.0 | Version initiale |

---

<div align="center">
Fait avec passion · Windows 10/11 · 64-bit
</div>
