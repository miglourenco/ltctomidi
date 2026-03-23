#!/usr/bin/env bash
# Build LTCtoMIDI for macOS
# Run from the project root:  bash build.sh
set -e

echo "=== Installing / upgrading dependencies ==="
# python-rtmidi is kept as a fallback; macOS uses CoreMIDI directly via ctypes
# (avoids a fatal GIL crash with python-rtmidi on Python 3.12+).
python3 -m pip install --upgrade sounddevice numpy python-rtmidi pyinstaller

echo ""
echo "=== Building LTCtoMIDI.app ==="
python3 -m PyInstaller --clean ltctomidi_macos.spec

echo ""
echo "=== Done! ==="
echo "App bundle: dist/LTCtoMIDI.app"
echo ""
echo "To create a distributable DMG (optional):"
echo "  hdiutil create -volname LTCtoMIDI -srcfolder dist/LTCtoMIDI.app -ov -format UDZO dist/LTCtoMIDI.dmg"
