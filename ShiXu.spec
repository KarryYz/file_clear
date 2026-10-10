# Build from a clean venv. Only application assets are included; never user data.
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('frontend/dist', 'frontend/dist')] + collect_data_files('webview'),
    hiddenimports=['uvicorn.logging', 'uvicorn.loops.asyncio', 'uvicorn.protocols.http.h11_impl',
                   'uvicorn.protocols.websockets.websockets_impl', 'uvicorn.lifespan.on'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'gi', 'qtpy', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='ShiXu-0.2.0-windows-x64', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False)
