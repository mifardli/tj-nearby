# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
hidden = collect_submodules("pystray") + collect_submodules("winrt")

a = Analysis(
    [str(root / "windows_app.py")],
    pathex=[str(root), str(root / "src")],
    binaries=[],
    datas=[
        (str(root / "config.example.yaml"), "."),
        (str(root / "src" / "tj_nearby" / "assets" / "tj_nearby.png"), "tj_nearby/assets"),
        (str(root / "src" / "tj_nearby" / "assets" / "tj_nearby.ico"), "tj_nearby/assets"),
        (str(root / "src" / "tj_nearby" / "assets" / "config.example.yaml"), "tj_nearby/assets"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TJ Nearby",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / "assets" / "tj_nearby.ico"),
    version=str(root / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TJ Nearby",
)
