# -*- mode: python ; coding: utf-8 -*-

import sys
import os

block_cipher = None

# Collect web assets and custom devices JSON
added_files = [
    ('src/gui/web', 'src/gui/web'),
    ('src/drivers/custom_devices.json', 'src/drivers'),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'src.core.device_base',
        'src.core.device_manager',
        'src.core.win_raw_hid',
        'src.core.win_bluetooth',
        'src.core.app_host',
        'src.core.config_manager',
        'src.modules.base_module',
        'src.modules.omni_battery.module',
        'src.modules.desktop_fences.module',
        'src.modules.desktop_fences.fence_window',
        'src.modules.power_rename.module',
        'src.modules.awake.module',
        'src.modules.window_pinner.module',
        'src.drivers.logitech_hidpp',
        'src.drivers.bluetooth_driver',
        'src.drivers.vendor_24g_driver',
        'src.gui.window',
        'src.ui.cli',
        'src.ui.tray_app',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'numpy', 'pandas', 'PIL'],
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
    name='OmniToys',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No black terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/OmniToys.ico',
)
