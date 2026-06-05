# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file build spec for TuneBridge.

Bundles the GUI and Python deps into a single TuneBridge.exe.
NOTE: ffmpeg and Node.js are NOT bundled — they remain external runtime
dependencies expected on PATH (see README).

Build:  pyinstaller --noconfirm TuneBridge.spec
Output: dist/TuneBridge.exe
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# librosa (and friends) use lazy imports / bundled data — collect everything.
for pkg in ("librosa", "soundfile", "lazy_loader", "soxr", "audioread", "pooch"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# yt-dlp pulls extractors dynamically.
hiddenimports += collect_submodules("yt_dlp")

a = Analysis(
    ["tunebridge.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TuneBridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,            # windowed GUI app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
