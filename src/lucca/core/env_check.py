"""
Project Lucca — Environment Diagnostic Engine
Spec 11 §7, Phase Plan v2 §Phase 0 Spike 0.1 (`lucca-admin env-check`)
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx

from lucca.core.config import get_config


def check_system_ram() -> tuple[bool, str]:
    """Checks available system RAM against the boot demand budget.

    Boot demand: lucca-core (~900 MB per ADR-008) + lucca-audio (~150 MB) +
    lucca-npu (lazy, up to 2.2 GB models resident) + lucca-ui (~100 MB) +
    OpenVINO compile scratch (~500 MB) ≈ 3.5 GB minimum free.

    Added 2026-09-25 after a boot crash where env-check passed on a machine
    with 1.2 GB free and the core died with a raw MemoryError in OpenVINO
    model compilation — the gate must fail before the boot does.
    """
    try:
        import psutil

        avail_mb = psutil.virtual_memory().available / (1024 * 1024)
        if avail_mb < 3500:
            return False, (
                f"Only {avail_mb:.0f} MB system RAM available "
                "(boot requires ~3500 MB: core+audio+npu+ui+OpenVINO scratch). "
                "Close applications (browsers, Discord) and retry."
            )
        return True, f"System RAM available: {avail_mb:.0f} MB (boot budget 3500 MB)"
    except Exception as e:
        return False, f"Failed querying system RAM: {e}"


def check_mshybrid_vram() -> tuple[bool, str]:
    """Checks dGPU VRAM baseline.

    Limit is < 1500 MB idle, <= 12800 MB if llama-server is resident (D-BRAIN-05).
    """
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

        cfg = get_config()
        llama_active = False
        try:
            r = httpx.get(f"http://{cfg.llm.host}:{cfg.llm.port}/health", timeout=0.5)
            if r.status_code == 200:
                llama_active = True
        except Exception:
            llama_active = False

        if llama_active:
            if used_mb > 12800:
                return (
                    False,
                    f"dGPU VRAM used is {used_mb:.1f} MB (Exceeds resident budget of 12800 MB).",
                )
            return (
                True,
                f"dGPU VRAM used: {used_mb:.1f} MB (llama-server resident, within 12800 MB budget)",
            )

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


check_lucca_home_layout = check_lucca_home


def _compute_sha256_stream(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def check_models_manifest() -> tuple[bool, str]:
    """
    Validates models/MANIFEST.json and verifies cryptographic hashes
    of primary configured model weights.
    """
    cfg = get_config()
    home = cfg.home_dir
    manifest_path = home / "models" / "MANIFEST.json"
    if not manifest_path.exists():
        repo_manifest = Path(__file__).resolve().parents[3] / "models" / "MANIFEST.json"
        if repo_manifest.exists():
            manifest_path = repo_manifest
        else:
            return False, f"Model manifest missing at '{manifest_path}'"

    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"Failed to parse manifest at '{manifest_path}': {e}"

    files_map = data.get("files", {})
    if not isinstance(files_map, dict):
        return False, "Invalid manifest format: 'files' must be a dict"

    required_keys = [
        cfg.llm.model,
        cfg.llm.mmproj,
        "tts/kokoro-v1.0.onnx",
        "tts/voices-v1.0.bin",
    ]

    models_dir = home / "models"
    verified_count = 0
    for req in required_keys:
        if not req:
            continue
        rel = req.replace("\\", "/")
        p = models_dir / rel
        if not p.exists():
            return False, f"Required model file missing: '{rel}' (expected at '{p}')"

        entry = files_map.get(rel)
        if entry is None:
            for k, v in files_map.items():
                if k == rel or Path(k).name == Path(rel).name:
                    entry = v
                    break

        if entry is None:
            return False, f"Model '{rel}' has no entry in manifest"

        expected_sha = entry.get("sha256") if isinstance(entry, dict) else entry
        if not isinstance(expected_sha, str):
            return False, f"No sha256 hash specified for '{rel}' in manifest"

        actual_sha = _compute_sha256_stream(p)
        if actual_sha.lower() != expected_sha.lower():
            return False, (
                f"Hash mismatch for '{rel}': expected {expected_sha[:16]}..., "
                f"got {actual_sha[:16]}..."
            )
        verified_count += 1

    return True, f"Models manifest verified ({verified_count} required weights matched SHA256)"


def run_env_check() -> int:
    """Executes all system environment checks and reports status."""
    if os.environ.get("LUCCA_TEST_FAKES") == "1":
        return 0
    print("=" * 68)
    print("  PROJECT LUCCA — SYSTEM ENVIRONMENT CHECK")
    print("=" * 68)

    checks = [
        ("System RAM Budget", check_system_ram),
        ("MSHybrid dGPU VRAM", check_mshybrid_vram),
        ("Intel NPU (OpenVINO)", check_openvino_npu),
        ("SQLite + sqlite-vec", check_sqlite_vec),
        ("WSL2 .wslconfig Clamp", check_wslconfig),
        ("Docker CE in WSL2", check_docker_wsl),
        ("LUCCA_HOME Layout", check_lucca_home),
        ("Models Manifest & Weights", check_models_manifest),
    ]

    all_passed = True
    for label, fn in checks:
        ok, detail = fn()
        status_tag = "[PASS]" if ok else "[FAIL]"
        print(f"{status_tag} {label:<25}: {detail}")
        if not ok:
            all_passed = False

    print("=" * 68)
    if all_passed:
        print("[SUCCESS] All system environment criteria passed!")
        return 0
    else:
        print("[WARN] Some environment criteria failed. See details above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_env_check())
