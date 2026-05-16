# build: pyinstaller obs_epg_macos.spec --noconfirm --clean
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
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
    name='OBS EPG Converter', debug=False, strip=False, upx=False, console=False,
    argv_emulation=True)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name='OBS EPG Converter')
app = BUNDLE(coll,
    name='OBS EPG Converter.app',
    bundle_identifier='xyz.streamrussia.obs-epg-converter',
    info_plist={
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13.0',
        'CFBundleShortVersionString': '1.0.0',
    },
)
