@echo off
REM build_windows.bat — собирает OBS_EPG_Converter.exe
REM Запускай на Windows с Python 3.10+

echo Installing PyInstaller...
pip install pyinstaller --quiet --upgrade

echo Building .exe...
pyinstaller obs_epg_windows.spec --noconfirm --clean

echo.
echo Done! EXE: dist\OBS_EPG_Converter.exe
pause
