"""
Project Lucca — Environment Diagnostic Engine
Spec 11 §7, Phase Plan v2 §Phase 0 Spike 0.1 (`lucca-admin env-check`)
"""

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from lucca.core.config import get_config


def check_mshybrid_vram() -> tuple[bool, str]:
    """Checks dGPU VRAM baseline via nvidia-smi (< 300 MB expected at idle in MSHybrid)."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False, "nvidia-smi not found in PATH."
    try:
        res = subprocess.run(
            [nvidia_smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
        )
        used_mb = float(res.stdout.strip().splitlines()[0])
        if used_mb > 1500:
            msg = (
                f"dGPU VRAM used is {used_mb:.1f} MB "
                "(High idle usage; check if display is pinned to dGPU)."
            )
            return False, msg
        return True, f"dGPU VRAM used: {used_mb:.1f} MB"
    except Exception as e:
        return False, f"Failed querying nvidia-smi: {e}"


def check_openvino_npu() -> tuple[bool, str]:
    """Checks if OpenVINO detects the Intel NPU natively on Windows."""
    try:
        import openvino as ov

        core = ov.Core()
        devices = core.available_devices
        if "NPU" in devices:
            return True, f"Intel NPU detected by OpenVINO (devices: {devices})"
        return False, f"Intel NPU not detected. Available devices: {devices}"
    except ImportError:
        return False, "OpenVINO python package not installed."
    except Exception as e:
        return False, f"OpenVINO runtime error: {e}"


def check_sqlite_vec() -> tuple[bool, str]:
    """Verifies that sqlite3 can load extensions and that sqlite-vec loads successfully."""
    try:
        import sqlite_vec

        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT vec_version()")
        version = cursor.fetchone()[0]
        conn.close()
        return True, f"sqlite-vec loaded successfully (version: {version})"
    except Exception as e:
        return False, f"sqlite-vec failed to load: {e}"


def check_wslconfig() -> tuple[bool, str]:
    """Verifies canonical .wslconfig configuration (Register §C)."""
    userprofile = os.getenv("USERPROFILE")
    if not userprofile:
        return False, "USERPROFILE environment variable not set."
    cfg_path = Path(userprofile) / ".wslconfig"
    if not cfg_path.exists():
        return False, f".wslconfig not found at '{cfg_path}'. Run scripts/setup_wslconfig.ps1"

    content = cfg_path.read_text(encoding="utf-8")
    checks = [
        ("memory=4608MB", "4.5GB RAM clamp"),
        ("swap=0", "Zero swap"),
        ("pageReporting=true", "Page reporting enabled"),
        ("autoMemoryReclaim=gradual", "Gradual memory reclaim"),
    ]
    missing = [desc for target, desc in checks if target not in content]
    if missing:
        return False, f".wslconfig missing canonical settings: {', '.join(missing)}"
    return True, f".wslconfig canonical settings verified at {cfg_path}"


def check_docker_wsl() -> tuple[bool, str]:
    """Verifies Docker CE is reachable inside Ubuntu WSL2 distro."""
    wsl_bin = shutil.which("wsl")
    if not wsl_bin:
        return False, "wsl.exe not found in PATH."
    try:
        res = subprocess.run(
            ["wsl", "-d", "Ubuntu", "--", "docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if res.returncode == 0:
            return True, "Docker CE is running inside Ubuntu WSL2."
        return False, f"Docker not responding in Ubuntu WSL2: {res.stderr.strip()[:100]}"
    except subprocess.TimeoutExpired:
        return False, "WSL2 docker info command timed out."
    except Exception as e:
        return False, f"Failed checking WSL2 Docker: {e}"


def check_lucca_home() -> tuple[bool, str]:
    """Ensures LUCCA_HOME layout exists with all required subdirectories."""
    cfg = get_config()
    home = cfg.home_dir
    subdirs = ["app", "config", "models", "data", "workspace", "inbox", "logs", "cache", "tmp"]
    created = []
    for s in subdirs:
        p = home / s
        if not p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
                created.append(s)
            except Exception as e:
                return False, f"Failed creating '{p}': {e}"
    msg = f"LUCCA_HOME verified at '{home}'"
    if created:
        msg += f" (initialized directories: {', '.join(created)})"
    return True, msg


def run_env_check() -> int:
    """Executes all Spike 0.1 environment checks and reports status."""
    print("=" * 68)
    print("  PROJECT LUCCA — SYSTEM ENVIRONMENT CHECK (SPIKE 0.1)")
    print("=" * 68)

    checks = [
        ("MSHybrid dGPU VRAM", check_mshybrid_vram),
        ("Intel NPU (OpenVINO)", check_openvino_npu),
        ("SQLite + sqlite-vec", check_sqlite_vec),
        ("WSL2 .wslconfig Clamp", check_wslconfig),
        ("Docker CE in WSL2", check_docker_wsl),
        ("LUCCA_HOME Layout", check_lucca_home),
    ]

    all_passed = True
    for label, fn in checks:
        ok, detail = fn()
        status_tag = "[PASS]" if ok else "[FAIL]"
        print(f"{status_tag} {label:<24}: {detail}")
        if not ok:
            all_passed = False

    print("=" * 68)
    if all_passed:
        print("[SUCCESS] All Spike 0.1 environment criteria passed!")
        return 0
    else:
        print("[WARN] Some environment criteria failed. See details above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_env_check())
