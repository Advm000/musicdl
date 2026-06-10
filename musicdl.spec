# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Music DL (compatible PyInstaller 5.x et 6.x)

import sys, os
_icon = 'icon.ico' if os.path.exists('icon.ico') else None

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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy'],
    noarchive=False,
)

pyz = PYZ(a.pure)

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
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MusicDL',
)
