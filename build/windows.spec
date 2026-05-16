# build/windows.spec
# pyinstaller build/windows.spec --noconfirm --clean

block_cipher = None

a = Analysis(
    ['../src/app.py'],
    pathex=['../src'],
    binaries=[],
    datas=[],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='OBS_EPG_Converter',
    debug=False, strip=False, upx=True, console=False,
    icon='../assets/icon.ico',
)
