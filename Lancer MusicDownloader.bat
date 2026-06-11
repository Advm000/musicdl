@echo off
title Music Downloader
echo Lancement du serveur...
python3 "%~dp0MusicDownloader.py"
if %errorlevel% neq 0 (
    echo Erreur. Appuie sur une touche.
    pause >nul
)
