#!/bin/bash
# build_linux.sh — собирает бинарник для Linux
set -e

if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "▸ Устанавливаю python3-tk…"
    sudo apt-get install -y python3-tk
fi

pip3 install pyinstaller --quiet --upgrade
pyinstaller obs_epg_linux.spec --noconfirm --clean

echo "✓ Готово! Бинарник: dist/obs-epg-converter"
