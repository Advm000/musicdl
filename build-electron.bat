@echo off
setlocal enabledelayedexpansion
title Music DL — Build App Electron

echo.
echo  ================================================
echo   Music DL — Build Application Windows Electron
echo  ================================================
echo.

:: ── 1. Verifier Node.js ───────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Node.js introuvable.
    echo         Telechargez-le sur : https://nodejs.org  (version LTS)
    pause & exit /b 1
)
echo  [OK] Node.js detecte

:: ── 2. Build Python backend (PyInstaller) ────────────────────────────────────
echo.
echo  [1/3] Build du backend Python...
echo        (PyInstaller — peut prendre 3-5 min)
echo.
call build.bat
if errorlevel 1 (
    echo  [ERREUR] Build Python echoue. Verifiez build.bat
    pause & exit /b 1
)

if not exist "dist\MusicDL\MusicDL.exe" (
    echo  [ERREUR] dist\MusicDL\MusicDL.exe introuvable apres PyInstaller.
    pause & exit /b 1
)
echo  [OK] Backend Python pret : dist\MusicDL\MusicDL.exe

:: ── 3. Installer les dependances Electron ────────────────────────────────────
echo.
echo  [2/3] Installation des dependances Electron...
cd electron
npm install
if errorlevel 1 (
    echo  [ERREUR] npm install echoue.
    cd ..
    pause & exit /b 1
)
echo  [OK] Dependances Electron installees

:: ── 4. Build Electron + Installeur ───────────────────────────────────────────
echo.
echo  [3/3] Build de l'application Electron...
echo        (electron-builder — peut prendre 2-3 min)
echo.
npm run build
if errorlevel 1 (
    echo  [ERREUR] electron-builder a echoue.
    cd ..
    pause & exit /b 1
)

cd ..

echo.
echo  ================================================
echo   BUILD COMPLET !
echo  ================================================
echo.
echo   Installeur : electron\dist-electron\Music DL Setup 1.0.0.exe
echo.
echo   Ce fichier installe Music DL comme une vraie
echo   application Windows native (sans navigateur).
echo.
pause
