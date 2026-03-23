#!/usr/bin/env bash
# Build LTCtoMIDI for macOS
# Run from the project root:  bash build.sh
set -e

echo "=== Installing / upgrading dependencies ==="
# python-rtmidi is kept as a fallback; macOS uses CoreMIDI directly via ctypes
# (avoids a fatal GIL crash with python-rtmidi on Python 3.12+).
python3 -m pip install --upgrade sounddevice numpy python-rtmidi pyinstaller Pillow

echo ""
echo "=== Building LTCtoMIDI.app ==="
python3 -m PyInstaller --clean -y ltctomidi_macos.spec

echo ""
echo "=== Generating DMG background ==="
python3 make_dmg_bg.py

echo ""
echo "=== Creating LTCtoMIDI.dmg ==="
rm -f dist/LTCtoMIDI.dmg
create-dmg \
  --volname "LTCtoMIDI" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "LTCtoMIDI.app" 150 200 \
  --hide-extension "LTCtoMIDI.app" \
  --app-drop-link 450 200 \
  --background "dmg_background.png" \
  "dist/LTCtoMIDI.dmg" \
  "dist/LTCtoMIDI.app"

echo ""
echo "=== Done! ==="
echo "App bundle : dist/LTCtoMIDI.app"
echo "Installer  : dist/LTCtoMIDI.dmg"
