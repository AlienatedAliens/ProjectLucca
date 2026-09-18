# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Projects/ProjectLucca/src/lucca/main.py'],
    pathex=['C:/Projects/ProjectLucca/src'],
    binaries=[],
    datas=[('C:/Projects/ProjectLucca/assets', 'assets'), ('C:/Projects/ProjectLucca/config', 'config'), ('C:/Projects/ProjectLucca/src/lucca/memory/migrations', 'lucca/memory/migrations')],
    hiddenimports=['sqlite_vec', 'kokoro_onnx', 'sounddevice', 'openvino', 'openvino_genai', 'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'psutil', 'httpx', 'structlog', 'zmq', 'lucca.memory.manager'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Lucca',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Projects/ProjectLucca/assets/icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Lucca',
)
