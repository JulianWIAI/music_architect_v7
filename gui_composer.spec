# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['gui_composer.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('FluidR3_GM.sf2', '.'),
    ],
    hiddenimports=[
        'composition_engine',
        'seed_builder',
        'wav_renderer',
        'genre_fusion',
        'gui_fusion_additions',
        'smart_arrangement',
        'bass_pattern_extractor',
        'lead_pattern_extractor',
        'rhythm_pattern_extractor',
        'pdmx_adapter',
        'midiutil',
        'midiutil.MidiFile',
        'numpy',
        'scipy',
        'scipy.signal',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SeedComposer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
