#!/bin/bash
# build_macos.sh — собирает .app + .dmg
# Запускай на Mac: chmod +x build_macos.sh && ./build_macos.sh
set -e

echo "▸ Устанавливаю PyInstaller…"
pip3 install pyinstaller --quiet --upgrade

echo "▸ Собираю .app…"
pyinstaller obs_epg_macos.spec --noconfirm --clean

echo "▸ Создаю .dmg…"
DMG_TMP="dmg_tmp"
rm -rf "$DMG_TMP"
mkdir "$DMG_TMP"
cp -R "dist/OBS EPG Converter.app" "$DMG_TMP/"
ln -s /Applications "$DMG_TMP/Applications"

hdiutil create \
    -volname "OBS EPG Converter" \
    -srcfolder "$DMG_TMP" \
    -ov -format UDZO \
    "dist/OBS_EPG_Converter_macOS.dmg"

rm -rf "$DMG_TMP"

echo ""
echo "✓ Готово!"
echo "  .app → dist/OBS EPG Converter.app"
echo "  .dmg → dist/OBS_EPG_Converter_macOS.dmg"
