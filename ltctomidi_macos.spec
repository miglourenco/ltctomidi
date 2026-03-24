# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for LTCtoMIDI — macOS (.app bundle).
Usage:
    python -m PyInstaller --clean ltctomidi_macos.spec
    (or just run build.sh)
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_all

block_cipher = None

# ── sounddevice: bundle data files + PortAudio dylib ─────────────────────────
_sd_datas = collect_data_files('sounddevice', include_py_files=False)
_sd_bins  = collect_dynamic_libs('sounddevice')

# ── numpy: collect everything (avoids missing-import errors on numpy 2.x) ────
_np_datas, _np_bins, _np_hidden = collect_all('numpy')

# ── certifi: bundle CA certificates for SSL (urlopen in update checker) ──────
_certifi_datas = collect_data_files('certifi')

# ── optional icon ─────────────────────────────────────────────────────────────
_icns_src  = [('ltctomidi.icns', '.')] if os.path.exists('ltctomidi.icns') else []
_icns_path = 'ltctomidi.icns'          if os.path.exists('ltctomidi.icns') else None

# ─────────────────────────────────────────────────────────────────────────────

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=_sd_bins + _np_bins,
    datas=_sd_datas + _np_datas + _certifi_datas + _icns_src,
    hiddenimports=_np_hidden + [
        'sounddevice',
        # rtmidi is still imported as a fallback but the primary macOS backend is
        # CoreMIDI via ctypes (avoids GIL crash on Python 3.12+).
        'rtmidi',
        'certifi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'PIL', 'pandas',
        'IPython', 'jupyter', 'notebook',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'wx', 'gtk',
        # Windows-only — not needed on macOS
        'ctypes.wintypes',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LTCtoMIDI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX not recommended on macOS
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icns_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='LTCtoMIDI',
)

app = BUNDLE(
    coll,
    name='LTCtoMIDI.app',
    icon=_icns_path,
    bundle_identifier='com.ltctomidi.app',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.1.0',
        'CFBundleName': 'LTCtoMIDI',
        'NSMicrophoneUsageDescription': 'LTCtoMIDI needs audio input to read LTC timecode.',
    },
)
