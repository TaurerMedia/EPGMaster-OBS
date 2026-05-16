# build/macos.spec
# pyinstaller build/macos.spec --noconfirm --clean

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
exe = EXE(pyz, a.scripts, [],
    exclude_binaries=True,
    name='OBS EPG Converter',
    debug=False, strip=False, upx=False, console=False,
    argv_emulation=True,
    icon='../assets/icon.icns',
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name='OBS EPG Converter')
app = BUNDLE(coll,
    name='OBS EPG Converter.app',
    icon='../assets/icon.icns',
    bundle_identifier='io.epgmaster.obs-converter',
    info_plist={
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.14.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'OBS EPG Converter',
        'NSPrincipalClass': 'NSApplication',
    },
)
