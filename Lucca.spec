# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

project_root = Path("C:/Projects/ProjectLucca").resolve()
sys.path.insert(0, str(project_root / "src"))

datas = [
    (str(project_root / "assets"), "assets"),
    (str(project_root / "config"), "config"),
    (str(project_root / "templates"), "templates"),
    (str(project_root / "src" / "lucca" / "memory" / "migrations"), "lucca/memory/migrations"),
]
datas += collect_data_files("z3")
datas += collect_data_files("kokoro_onnx")

openvino_libs_dir = Path(sys.prefix) / "Lib" / "site-packages" / "openvino" / "libs"
if (openvino_libs_dir / "cache.json").exists():
    datas.append((str(openvino_libs_dir / "cache.json"), "openvino/libs"))

binaries = []
binaries += collect_dynamic_libs("z3")
binaries += collect_dynamic_libs("sqlite_vec")
binaries += collect_dynamic_libs("openvino")
binaries += collect_dynamic_libs("openvino_genai")
binaries += collect_dynamic_libs("openvino_tokenizers")
binaries += collect_dynamic_libs("onnxruntime")

hidden_imports = [
    "sqlite_vec",
    "kokoro_onnx",
    "sounddevice",
    "openvino",
    "openvino_genai",
    "openvino_tokenizers",
    "onnxruntime",
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "psutil",
    "httpx",
    "structlog",
    "zmq",
    "networkx",
    "scipy",
    "sklearn",
    "jinja2",
    "pydantic",
    "pydantic_settings",
    "rapidfuzz",
    "rich",
    "ulid",
]
hidden_imports += collect_submodules("lucca")
hidden_imports += collect_submodules("z3")
hidden_imports += collect_submodules("openvino")

a = Analysis(
    [str(project_root / "src" / "lucca" / "main.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
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
    name="Lucca",
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
    icon=[str(project_root / "assets" / "icon.ico")],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Lucca",
)
