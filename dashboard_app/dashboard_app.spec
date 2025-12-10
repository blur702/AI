# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

base_path = os.path.abspath(os.path.dirname(__file__))


a = Analysis(
    [os.path.join(base_path, 'main.py')],
    pathex=[base_path],
    binaries=[],
    datas=[
        (os.path.join(base_path, 'assets'), 'assets'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'requests',
        'psutil',
        'dashboard.backend.services_config',
        'vram_manager',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AI Dashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\icon.ico',
)
