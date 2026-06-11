# 🎵 Music DL

**Télécharge ta musique depuis YouTube Music. Écoute-la pour toujours — même hors ligne.**

Application de bureau Windows : recherche YouTube Music, téléchargement MP3/M4A avec les vraies pochettes d'album, lecteur intégré, playlists et mises à jour automatiques.

[**⬇️ Télécharger pour Windows**](https://github.com/Advm000/musicdl/releases/latest/download/Music-DL-Setup.exe) · [Site officiel](https://advm000.github.io/musicdl/) · [Releases](https://github.com/Advm000/musicdl/releases)

---

## ✨ Fonctionnalités

- 🔍 **Recherche YouTube Music** — chansons avec artiste, album, durée et pochettes officielles (ou colle un lien YouTube)
- ⬇️ **Téléchargement MP3 / M4A** — 128, 192 ou 320 kbps, jusqu'à 3 téléchargements en parallèle avec progression en direct
- 🖼️ **Vraies pochettes** — la cover officielle est intégrée dans chaque fichier et affichée dans l'app
- 📂 **Dossier automatique** — l'app crée et gère son dossier `Musique\Music DL` toute seule
- ✈️ **Mode hors ligne** — bibliothèque, playlists et lecture fonctionnent à 100 % sans internet
- 🎧 **Lecteur intégré** — grand lecteur, file d'attente, aléatoire, répétition, favoris, touches média
- 📋 **Playlists** — création, tri, filtre, mosaïques de pochettes
- 🔄 **Mises à jour automatiques** — notification dans l'app + installation en un clic

## 🚀 Installation

1. Télécharge [`Music-DL-Setup.exe`](https://github.com/Advm000/musicdl/releases/latest/download/Music-DL-Setup.exe)
2. Lance l'installateur (Windows 10/11)
3. C'est tout — aucune dépendance à installer

## 🛠️ Développement

```powershell
git clone https://github.com/Advm000/musicdl.git
cd musicdl
npm install
powershell -ExecutionPolicy Bypass -File tools/fetch-bins.ps1   # yt-dlp + ffmpeg
node tools/gen-icon.js                                          # icône
npm start                                                       # lancer en dev
npm run dist                                                    # builder l'installateur
```

**Stack** : Electron · yt-dlp · ffmpeg · electron-builder · electron-updater (GitHub Releases)

```
src/
  main.js        # process principal : recherche, téléchargements, bibliothèque, auto-update
  preload.js     # pont sécurisé IPC
  renderer/      # interface (HTML/CSS/JS, design "mockup v3")
bin/             # yt-dlp.exe, ffmpeg.exe (non versionnés — tools/fetch-bins.ps1)
docs/            # landing page (GitHub Pages)
mockups/         # maquettes de référence
```

## ⚖️ Avertissement

Music DL est destiné à un **usage personnel uniquement**. Respecte les conditions d'utilisation de YouTube et les droits d'auteur de ta région.

## 📄 Licence

MIT — © 2026 Advm000
