# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Music DL
# Usage: pyinstaller musicdl.spec

import sys, os
block_cipher = None

a = Analysis(
    ['MusicDownloader.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'flask', 'flask.templating',
        'werkzeug', 'werkzeug.serving', 'werkzeug.routing',
        'jinja2', 'click',
        'yt_dlp', 'yt_dlp.extractor', 'yt_dlp.downloader',
        'mutagen', 'mutagen.mp3', 'mutagen.id3', 'mutagen.easyid3',
        'imageio_ffmpeg',
        'engineio', 'socketio',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MusicDL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # pas de fenetre console
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',        # place un icon.ico a cote de ce fichier
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MusicDL',
)
