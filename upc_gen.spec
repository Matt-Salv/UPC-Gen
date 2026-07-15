import sys
from PyInstaller.utils.hooks import collect_all

openpyxl_datas, openpyxl_binaries, openpyxl_hiddenimports = collect_all('openpyxl')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=openpyxl_binaries,
    datas=[('fonts/arial.ttf', 'fonts')] + openpyxl_datas,
    hiddenimports=[
        'barcode.upc',
        'barcode.codex',
        'barcode.ean',
    ] + openpyxl_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='UPCGen',
        debug=False,
        strip=False,
        upx=True,
        console=False,
        argv_emulation=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        name='UPCGen',
    )
    app = BUNDLE(
        coll,
        name='UPCGen.app',
        bundle_identifier='com.rasterlab.upcgen',
        info_plist={
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.13.0',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='UPCGen',
        debug=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
    )
