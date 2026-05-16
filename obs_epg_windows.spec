# build: pyinstaller obs_epg_windows.spec --noconfirm --clean
block_cipher = None

a = Analysis(
    ['obs_epg.py'],
    pathex=['.'],
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
    # icon='icon.ico',  # раскомментируй и добавь icon.ico если нужно
)
