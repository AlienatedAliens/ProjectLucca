"""
Project Lucca — PyInstaller Executable Builder
Bundles Project Lucca into a standalone Windows desktop application (Lucca.exe).
Spec 01 §1, Spec 16 §3
"""

import os
import subprocess
import sys
from pathlib import Path


def build() -> int:
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    print("=" * 60)
    print("  PROJECT LUCCA — BUILDING DESKTOP EXECUTABLE (Lucca.exe)")
    print("=" * 60)

    # 1. Verify icons exist
    icon_ico = project_root / "assets" / "icon.ico"
    icon_png = project_root / "assets" / "icon.png"
    if not icon_ico.exists() or not icon_png.exists():
        print("Generating application icons from sprites...")
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QImage, QPainter

        src = QImage(str(project_root / "assets" / "sprites" / "lucca" / "portrait_classic.png"))
        dest = QImage(256, 256, QImage.Format.Format_ARGB32)
        dest.fill(QColor(0, 0, 0, 0))

        painter = QPainter(dest)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor(16, 28, 84))
        painter.setPen(QColor(230, 185, 50))
        painter.drawRoundedRect(8, 8, 240, 240, 48, 48)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        scaled = src.scaled(180, 216, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        painter.drawImage((256 - scaled.width()) // 2, (256 - scaled.height()) // 2, scaled)
        painter.end()

        dest.save(str(icon_png))
        dest.save(str(icon_ico))
        print("  Created assets/icon.png and assets/icon.ico")

    # 2. PyInstaller Command Arguments
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "Lucca",
        "--icon", str(icon_ico),
        "--add-data", f"{project_root / 'assets'};assets",
        "--add-data", f"{project_root / 'config'};config",
        "--add-data", f"{project_root / 'src' / 'lucca' / 'memory' / 'migrations'};lucca/memory/migrations",
        "--hidden-import", "sqlite_vec",
        "--hidden-import", "kokoro_onnx",
        "--hidden-import", "sounddevice",
        "--hidden-import", "openvino",
        "--hidden-import", "openvino_genai",
        "--hidden-import", "PyQt6",
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--hidden-import", "psutil",
        "--hidden-import", "httpx",
        "--hidden-import", "structlog",
        "--hidden-import", "zmq",
        "--hidden-import", "lucca.memory.manager",
        "--paths", str(project_root / "src"),
        str(project_root / "src" / "lucca" / "main.py"),
    ]

    print(f"Running command: {' '.join(cmd[:6])} ...")
    ret = subprocess.run(cmd)

    if ret.returncode == 0:
        exe_path = dist_dir / "Lucca" / "Lucca.exe"
        print("=" * 60)
        print(f"BUILD SUCCESSFUL: {exe_path}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("BUILD FAILED!")
        print("=" * 60)

    return ret.returncode


if __name__ == "__main__":
    sys.exit(build())
