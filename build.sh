#!/usr/bin/env bash
# Build LTCtoMIDI for macOS
# Run from the project root:  bash build.sh
set -e

echo "=== Installing / upgrading dependencies ==="
pip install --upgrade sounddevice numpy python-rtmidi pyinstaller

echo ""
echo "=== Building LTCtoMIDI.app ==="
python -m PyInstaller --clean ltctomidi_macos.spec

echo ""
echo "=== Done! ==="
echo "App bundle: dist/LTCtoMIDI.app"
echo ""
echo "To create a distributable DMG (optional):"
echo "  hdiutil create -volname LTCtoMIDI -srcfolder dist/LTCtoMIDI.app -ov -format UDZO dist/LTCtoMIDI.dmg"
