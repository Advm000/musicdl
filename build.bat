@echo off
setlocal enabledelayedexpansion
title Music DL — Build Windows Installer

echo.
echo  ================================================
echo   Music DL — Build Windows Installer
echo  ================================================
echo.

:: ── 1. Verifier Python ────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Python introuvable. Installez Python 3.10+ et relancez.
    pause & exit /b 1
)

:: ── 2. Installer / mettre a jour PyInstaller ──────────────────────────────────
echo  [1/4] Installation des dependances de build...
pip install pyinstaller --quiet --upgrade
if errorlevel 1 (
    echo  [ERREUR] pip a echoue.
    pause & exit /b 1
)

:: ── 3. Creer une icone par defaut si icon.ico absent ─────────────────────────
if not exist "icon.ico" (
    echo  [INFO] icon.ico absent — creation d'une icone par defaut...
    python -c "
import struct, zlib, base64, os
# Icone 16x16 minimale encodee en base64
data = b'AAABAAEAEBAAAAEAIABoBAAAFgAAACgAAAAQAAAAIAAAAAEAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAiIj/AImJ/wCIiP8AiIj/AImJ/wCIiP8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACIZP8AiGT/AYhk/wCIZP8AiGT/AIhk/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACIZP8AiGT/AIhk/wCIZP8AiGT/AIhk/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACIZP8AiGT/AIhk/wCIZP8AiGT/AIhk/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACIZP8AiGT/AIhk/wCIZP8AiGT/AIhk/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACIZP8AiGT/AIhk/wCIZP8AiGT/AIhk/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACIiP8AiYn/AIiI/wCIiP8AiYn/AIiI/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
with open('icon.ico','wb') as f:
    f.write(base64.b64decode(data))
print('icone creee')
" 2>nul || echo  [INFO] Icone par defaut ignoree, continuez sans.
)

:: ── 4. Nettoyer les anciens builds ───────────────────────────────────────────
echo  [2/4] Nettoyage des anciens builds...
if exist "dist\MusicDL"   rmdir /s /q "dist\MusicDL"
if exist "build\MusicDL"  rmdir /s /q "build\MusicDL"

:: ── 5. Lancer PyInstaller ────────────────────────────────────────────────────
echo  [3/4] Compilation avec PyInstaller...
echo        (cela peut prendre 2-5 minutes)
echo.
pyinstaller musicdl.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo  [ERREUR] PyInstaller a echoue. Verifiez les messages ci-dessus.
    pause & exit /b 1
)

echo.
echo  [OK] Executable cree dans : dist\MusicDL\MusicDL.exe

:: ── 6. Verifier si Inno Setup est installe ───────────────────────────────────
echo  [4/4] Creation de l'installeur Windows...
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"  set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"         set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if %ISCC%=="" (
    echo.
    echo  [INFO] Inno Setup non detecte.
    echo         Telechargez-le sur : https://jrsoftware.org/isinfo.php
    echo         Puis relancez build.bat pour generer l'installeur .exe
    echo.
    echo  En attendant, vous pouvez lancer l'app directement :
    echo         dist\MusicDL\MusicDL.exe
    echo.
    pause & exit /b 0
)

if not exist "installer_output" mkdir "installer_output"
%ISCC% "setup.iss"
if errorlevel 1 (
    echo  [ERREUR] Inno Setup a echoue.
    pause & exit /b 1
)

echo.
echo  ================================================
echo   BUILD COMPLET !
echo  ================================================
echo.
echo   Installeur : installer_output\MusicDL_Setup_v1.0.0.exe
echo.
echo   Ce fichier installe Music DL comme une vraie
echo   application Windows avec raccourci bureau et
echo   menu Demarrer.
echo.
echo   Donnees utilisateur stockees dans :
echo   %%LOCALAPPDATA%%\MusicDL\
echo   (personnel a ce PC, non supprime a la desinstallation)
echo.
pause
