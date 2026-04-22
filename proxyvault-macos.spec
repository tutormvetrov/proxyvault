# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


target_arch = os.environ.get('PYINSTALLER_TARGET_ARCH') or 'universal2'
ROOT = Path.cwd()

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ProxyVault',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=target_arch,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ProxyVault',
)

app = BUNDLE(
    coll,
    name='ProxyVault.app',
    icon=None,
    bundle_identifier='com.proxyvault.app',
    info_plist={
        'CFBundleName': 'ProxyVault',
        'CFBundleDisplayName': 'ProxyVault',
        'CFBundleIdentifier': 'com.proxyvault.app',
        'LSMinimumSystemVersion': '12.0',
        'NSHighResolutionCapable': True,
    },
)
