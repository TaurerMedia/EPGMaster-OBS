#!/bin/bash
# scripts/build_macos.sh
# Запуск: chmod +x scripts/build_macos.sh && ./scripts/build_macos.sh
set -e

ICON_URL="https://s3-v1-assets-eu7-01-prd-vxdgroup-cloud-xyz.b-cdn.net/softobs_5i1j5i/icon.png"
BG_URL="https://s3-v1-assets-eu7-01-prd-vxdgroup-cloud-xyz.b-cdn.net/softobs_5i1j5i/install-bg.png"
APP="OBS EPG Converter"
OUT_DIR="dist"

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║  EPGMaster · OBS EPG Converter        ║"
echo "║  macOS Build                          ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# ── Зависимости ──
echo "▸ Устанавливаю зависимости…"
pip3 install pyinstaller certifi --quiet --upgrade

# ── Иконка ──
echo "▸ Скачиваю иконку…"
curl -fsSL "$ICON_URL" -o assets/icon.png 2>/dev/null \
    && echo "  ✓ icon.png" \
    || echo "  ⚠ иконку не удалось скачать"

if [ -f assets/icon.png ]; then
    echo "▸ Конвертирую PNG → ICNS…"
    mkdir -p assets/icon.iconset
    for size in 16 32 64 128 256 512; do
        sips -z $size $size assets/icon.png \
            --out "assets/icon.iconset/icon_${size}x${size}.png" 2>/dev/null || true
        double=$((size * 2))
        sips -z $double $double assets/icon.png \
            --out "assets/icon.iconset/icon_${size}x${size}@2x.png" 2>/dev/null || true
    done
    iconutil -c icns assets/icon.iconset -o assets/icon.icns 2>/dev/null \
        && echo "  ✓ icon.icns" || echo "  ⚠ iconutil не сработал"
    rm -rf assets/icon.iconset
fi

# ── Сборка .app ──
echo "▸ Собираю .app…"
pyinstaller build/macos.spec --noconfirm --clean

# ── DMG фон ──
echo "▸ Скачиваю фон для DMG…"
curl -fsSL "$BG_URL" -o assets/dmg-bg.png 2>/dev/null \
    && echo "  ✓ dmg-bg.png" \
    || echo "  ⚠ фон не удалось скачать"

# ── Создание DMG ──
echo "▸ Создаю .dmg…"
DMG_TMP="_dmg_tmp"
rm -rf "$DMG_TMP"
mkdir "$DMG_TMP"
cp -R "$OUT_DIR/$APP.app" "$DMG_TMP/"
ln -s /Applications "$DMG_TMP/Applications"

if [ -f assets/dmg-bg.png ]; then
    mkdir -p "$DMG_TMP/.background"
    cp assets/dmg-bg.png "$DMG_TMP/.background/bg.png"
fi

hdiutil create \
    -volname "$APP" \
    -srcfolder "$DMG_TMP" \
    -ov -format UDZO \
    "$OUT_DIR/OBS_EPG_Converter_macOS.dmg"

rm -rf "$DMG_TMP"

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║  ✓ Готово!                            ║"
echo "╠═══════════════════════════════════════╣"
echo "║  .app → $OUT_DIR/$APP.app"
echo "║  .dmg → $OUT_DIR/OBS_EPG_Converter_macOS.dmg"
echo "╚═══════════════════════════════════════╝"
echo ""
