@echo off
REM scripts\build_windows.bat
REM Запустить на Windows с Python 3.10+

echo.
echo  EPGMaster - OBS EPG Converter
echo  Windows Build
echo.

echo  Скачиваю иконку...
curl -fsSL "https://s3-v1-assets-eu7-01-prd-vxdgroup-cloud-xyz.b-cdn.net/softobs_5i1j5i/icon.png" -o assets\icon.png 2>nul
if exist assets\icon.png (
    echo  OK icon.png
) else (
    echo  иконку не удалось скачать
)

echo  Устанавливаю зависимости...
pip install pyinstaller certifi --quiet --upgrade

echo  Собираю .exe...
pyinstaller build\windows.spec --noconfirm --clean

echo.
echo  Готово! dist\OBS_EPG_Converter.exe
pause
