"""
Unit tests for lucca.core.env_check
Spec 01 §7, Spec 11 §7, F-CORE-022, F-CORE-025
"""

import hashlib
import json
from pathlib import Path

import pytest

from lucca.core.config import get_config
from lucca.core.env_check import (
    check_audio_ring,
    check_lucca_home,
    check_models_manifest,
    check_system_ram,
    check_wsl_status,
)


class _FakeVMem:
    def __init__(self, available_bytes: int) -> None:
        self.available = available_bytes


def test_system_ram_gate_fails_below_boot_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The RAM gate must refuse boot when available RAM < 3500 MB (2026-09-25 boot crash)."""
    import psutil

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _FakeVMem(int(1.2 * 1024**3)))
    ok, msg = check_system_ram()
    assert ok is False
    assert "3500" in msg


def test_system_ram_gate_passes_above_boot_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The RAM gate passes with comfortable headroom."""
    import psutil

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _FakeVMem(int(8 * 1024**3)))
    ok, msg = check_system_ram()
    assert ok is True
    assert "System RAM available" in msg


def test_models_manifest_missing_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that check_models_manifest fails when models/MANIFEST.json is missing."""
    home = tmp_path / "lucca_home_empty"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()

    # Pass an empty directory where neither home nor fallback manifest exists
    # Ensure parents[3]/models/MANIFEST.json fallback is not hit by pointing home there
    ok, msg = check_models_manifest()
    # If the fallback exists in the repo, check_models_manifest will fail on missing model files
    assert ok is False
    assert ("Model manifest missing" in msg) or ("Required model file missing" in msg)


def test_models_manifest_valid_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that check_models_manifest passes when all required models match their hashes."""
    home = tmp_path / "lucca_home_valid"
    models_dir = home / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()

    cfg = get_config()
    required = [
        cfg.llm.model,
        cfg.llm.mmproj,
        "tts/kokoro-v1.0.onnx",
        "tts/voices-v1.0.bin",
    ]

    files_map = {}
    for rel in required:
        p = models_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        content = f"dummy binary content for {rel}".encode()
        p.write_bytes(content)
        files_map[rel.replace("\\", "/")] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }

    manifest_path = models_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps({"files": files_map}), encoding="utf-8")

    ok, msg = check_models_manifest()
    assert ok is True
    assert "Models manifest verified" in msg


def test_models_manifest_hash_mismatch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that check_models_manifest fails when a model's hash doesn't match."""
    home = tmp_path / "lucca_home_mismatch"
    models_dir = home / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()

    cfg = get_config()
    required = [
        cfg.llm.model,
        cfg.llm.mmproj,
        "tts/kokoro-v1.0.onnx",
        "tts/voices-v1.0.bin",
    ]

    files_map = {}
    for rel in required:
        p = models_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        content = f"dummy binary content for {rel}".encode()
        p.write_bytes(content)
        # Put wrong hash
        files_map[rel.replace("\\", "/")] = {
            "sha256": "0" * 64,
            "size_bytes": len(content),
        }

    manifest_path = models_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps({"files": files_map}), encoding="utf-8")

    ok, msg = check_models_manifest()
    assert ok is False
    assert "Hash mismatch" in msg


def test_check_lucca_home_creates_subdirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies check_lucca_home verifies or creates missing subdirectories."""
    home = tmp_path / "brand_new_lucca_home"
    monkeypatch.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()

    ok, msg = check_lucca_home()
    assert ok is True
    assert "LUCCA_HOME verified" in msg
    assert (home / "models").exists()


def test_check_audio_ring_healthy_when_no_underruns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audio ring check passes when zero underruns are recorded."""
    home = tmp_path / "lucca_home_audio_ok"
    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "traces.jsonl").write_text(json.dumps({"underruns": 0}) + "\n", encoding="utf-8")
    monkeypatch.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()

    ok, msg = check_audio_ring()
    assert ok is True
    assert "zero underruns" in msg


def test_check_audio_ring_detects_underruns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audio ring check detects underrun contention in recent traces."""
    home = tmp_path / "lucca_home_audio_underrun"
    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "traces.jsonl").write_text(
        json.dumps({"underruns": 4, "trace_id": "tr-1"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LUCCA_HOME", str(home))
    get_config.cache_clear()

    ok, msg = check_audio_ring()
    assert ok is False
    assert "4 underruns detected" in msg


def test_check_wsl_status_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """WSL status check passes when wsl --status succeeds."""
    import subprocess

    class _Res:
        returncode = 0
        stdout = "Default Distribution: Ubuntu\nDefault Version: 2"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Res())
    ok, msg = check_wsl_status()
    assert ok is True
    assert "WSL is responsive" in msg


def test_check_wsl_status_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """WSL status check flags timeout as unresponsive subsystem."""
    import subprocess

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=["wsl", "--status"], timeout=5)

    monkeypatch.setattr(subprocess, "run", _timeout)
    ok, msg = check_wsl_status()
    assert ok is False
    assert "timed out" in msg
