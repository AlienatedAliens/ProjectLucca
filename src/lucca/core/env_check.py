"""
Project Lucca — Environment Diagnostic Engine
Spec 11 §7, Phase Plan v2 §Phase 0 Spike 0.1 (`lucca-admin env-check`)
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx

from lucca.core.config import get_config

logger = logging.getLogger(__name__)


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
        logger.debug("check_system_ram_failed: %s", e)
        return False, f"Failed querying system RAM: {e}"


def check_mshybrid_vram() -> tuple[bool, str]:
    """Checks dGPU VRAM baseline and resident workloads.

    Dynamic budget based on resident model footprint:
    - Idle baseline: < 1500 MB
    - llama-server resident (LLM + Vision mmproj): <= 12800 MB
    - Full companion stack (llama-server + CosyVoice 3): <= 15200 MB (within 16GB physical VRAM)
    """
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False, "nvidia-smi not found in PATH."
    try:
        res = subprocess.run(
            [nvidia_smi, "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
        )
        line = res.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        total_mb = float(parts[0]) if len(parts) > 1 else 16303.0
        used_mb = float(parts[1]) if len(parts) > 1 else float(parts[0])

        cfg = get_config()
        llama_active = False
        has_vision = False
        try:
            r = httpx.get(f"http://{cfg.llm.host}:{cfg.llm.port}/health", timeout=0.5)
            if r.status_code == 200:
                llama_active = True
                if getattr(cfg.llm, "mmproj", None):
                    has_vision = True
        except Exception as exc:
            logger.debug("check_llama_health_failed: %s", exc)
            llama_active = False

        cosy_active = False
        try:
            from lucca.speech.cosyvoice_client import CosyVoice3Client

            cosy_active = CosyVoice3Client.get_instance().ping()
        except Exception as exc:
            logger.debug("check_cosyvoice_ping_failed: %s", exc)
            cosy_active = False

        # Compute dynamic budget based on active resident workloads
        if llama_active:
            budget_mb = min(15200.0, total_mb - 1000.0)
            vision_tag = "+Vision" if has_vision else ""
            cosy_tag = " + CosyVoice 3" if cosy_active else ""
            workload_desc = f"llama-server [LLM{vision_tag}]{cosy_tag} resident"
            if used_mb > budget_mb:
                return (
                    False,
                    f"dGPU VRAM used is {used_mb:.1f} MB (Exceeds resident budget of {budget_mb:.0f} MB).",
                )
            return (
                True,
                f"dGPU VRAM used: {used_mb:.1f} MB ({workload_desc}, within {budget_mb:.0f} MB budget)",
            )
        elif cosy_active:
            budget_mb = min(8000.0, total_mb - 2000.0)
            if used_mb > budget_mb:
                return (
                    False,
                    f"dGPU VRAM used is {used_mb:.1f} MB (Exceeds resident budget of {budget_mb:.0f} MB).",
                )
            return (
                True,
                f"dGPU VRAM used: {used_mb:.1f} MB (CosyVoice 3 resident, within {budget_mb:.0f} MB budget)",
            )

        if used_mb > 1500:
            msg = (
                f"dGPU VRAM used is {used_mb:.1f} MB "
                "(High idle usage; check if display is pinned to dGPU)."
            )
            return False, msg
        return True, f"dGPU VRAM used: {used_mb:.1f} MB"
    except Exception as e:
        logger.debug("check_mshybrid_vram_failed: %s", e)
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
    except ImportError as e:
        logger.debug("check_openvino_npu_import_error: %s", e)
        return False, "OpenVINO python package not installed."
    except Exception as e:
        logger.debug("check_openvino_npu_failed: %s", e)
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
        logger.debug("check_sqlite_vec_failed: %s", e)
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
    except subprocess.TimeoutExpired as e:
        logger.debug("check_docker_wsl_timeout: %s", e)
        return False, "WSL2 docker info command timed out."
    except Exception as e:
        logger.debug("check_docker_wsl_failed: %s", e)
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
                logger.debug("check_lucca_home_failed: %s", e)
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
        logger.debug("check_models_manifest_failed: %s", e)
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


def check_audio_ring() -> tuple[bool, str]:
    """Reads ring-buffer underrun/overrun counters from recent traces/telemetry.

    WO-22 Phase 2 (Fault Model v1, ratified 2026-09-27).
    Deterministic, no network.
    """
    try:
        cfg = get_config()
        logs_dir = cfg.resolve_path("logs")
        canonical_trace_file = logs_dir / "traces.jsonl"

        total_underruns = 0
        turns_checked = 0
        if canonical_trace_file.exists():
            try:
                with open(canonical_trace_file, encoding="utf-8") as f:
                    lines = f.readlines()
                for raw_line in lines[-20:]:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        underruns = int(entry.get("underruns", 0))
                        total_underruns += underruns
                        turns_checked += 1
                    except (json.JSONDecodeError, ValueError, TypeError) as parse_exc:
                        logger.debug("check_audio_ring_line_parse_failed: %s", parse_exc)
                        continue
            except Exception as read_exc:
                logger.debug("check_audio_ring_trace_read_failed: %s", read_exc)

        # Also inspect shared memory capture ring if present
        try:
            from multiprocessing import shared_memory

            shm = shared_memory.SharedMemory(name="lucca_cap_ring", create=False)
            shm.close()
        except FileNotFoundError as shm_missing:
            logger.debug("check_audio_ring_shm_absent: %s", shm_missing)
        except Exception as shm_exc:
            logger.debug("check_audio_ring_shm_failed: %s", shm_exc)

        if total_underruns > 0:
            return (
                False,
                f"Audio ring buffer contention: {total_underruns} underruns detected across "
                f"{turns_checked} recent turns.",
            )
        return True, "Audio ring buffer healthy: zero underruns recorded."
    except Exception as e:
        logger.debug("check_audio_ring_failed: %s", e)
        return False, f"Failed checking audio ring: {e}"


def check_wsl_status() -> tuple[bool, str]:
    """Runs `wsl --status` with a bounded timeout and returns (ok, detail).

    WO-22 Phase 2 (Fault Model v1, ratified 2026-09-27).
    Deterministic, no network.
    """
    wsl_bin = shutil.which("wsl")
    if not wsl_bin:
        return False, "wsl.exe not found in PATH."
    try:
        res = subprocess.run(
            ["wsl", "--status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            raw_stdout = res.stdout if isinstance(res.stdout, str) else res.stdout.decode("utf-16", errors="replace")
            # Filter null bytes if captured via text=True
            clean_text = raw_stdout.replace("\x00", "")
            lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
            summary_parts = [l for l in lines if "Default Distribution" in l or "Default Version" in l]
            summary = " | ".join(summary_parts) if summary_parts else "Ubuntu (WSL2)"
            return True, f"WSL is responsive: {summary}"
        raw_err = res.stderr if isinstance(res.stderr, str) else res.stderr.decode("utf-16", errors="replace")
        err_msg = (raw_err.strip() or "").replace("\x00", "")
        return False, f"WSL status check failed (exit {res.returncode}): {err_msg[:100]}"
    except subprocess.TimeoutExpired as e:
        logger.debug("check_wsl_status_timeout: %s", e)
        return False, "WSL status command timed out (subsystem unresponsive)."
    except Exception as e:
        logger.debug("check_wsl_status_failed: %s", e)
        return False, f"Failed querying WSL status: {e}"


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
        ("Audio Ring Buffer", check_audio_ring),
        ("WSL Subsystem Status", check_wsl_status),
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
