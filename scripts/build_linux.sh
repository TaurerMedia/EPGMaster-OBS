#!/bin/bash
# scripts/build_linux.sh
set -e

echo ""
echo "  EPGMaster · OBS EPG Converter — Linux Build"
echo ""

if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "▸ Устанавливаю python3-tk…"
    sudo apt-get install -y python3-tk
fi

pip3 install pyinstaller certifi --quiet --upgrade
pyinstaller build/linux.spec --noconfirm --clean

echo ""
echo "  ✓ Готово! dist/obs-epg-converter"
echo ""
