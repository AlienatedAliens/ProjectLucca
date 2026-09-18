"""
Unit tests for lucca.brain.server_ctl
Spec 02, Spec 08, ADR-001, WI-3, WI-6
"""

from pathlib import Path

from lucca.brain.server_ctl import (
    build_launch_command,
    is_healthy,
    scan_model_registry,
)
from lucca.core.config import LLMSettings


def test_build_launch_command_text_mode(tmp_path: Path) -> None:
    """Verifies build_launch_command with text mode does not include --mmproj."""
    llama_dir = tmp_path / "app" / "llama-server"
    llama_dir.mkdir(parents=True)
    (llama_dir / "llama-server.exe").touch()

    model_dir = tmp_path / "models" / "llm"
    model_dir.mkdir(parents=True)
    model_path = model_dir / "test-model.gguf"
    model_path.touch()

    cfg = LLMSettings(
        model="models/llm/test-model.gguf",
        mmproj="models/llm/mmproj-test.gguf",
        mode="transcript",
        ctx=4096,
        kv_type="q8_0",
        host="127.0.0.1",
        port=8080,
    )

    cmd = build_launch_command(cfg, tmp_path)

    assert str(llama_dir / "llama-server.exe") in cmd[0]
    assert "--model" in cmd
    assert str(model_path) in cmd
    assert "--ctx-size" in cmd
    assert "4096" in cmd
    assert "--cache-type-k" in cmd
    assert "q8_0" in cmd
    assert "--cache-type-v" in cmd
    assert "q8_0" in cmd
    assert "--flash-attn" in cmd
    assert "on" in cmd
    assert "--host" in cmd
    assert "127.0.0.1" in cmd
    assert "--port" in cmd
    assert "8080" in cmd
    # In text mode, --mmproj should NOT be present even if file existed
    assert "--mmproj" not in cmd


def test_build_launch_command_audio_mode_with_mmproj(tmp_path: Path) -> None:
    """Verifies build_launch_command includes --mmproj iff mode == 'audio' and mmproj exists."""
    llama_dir = tmp_path / "app" / "llama-server"
    llama_dir.mkdir(parents=True)
    (llama_dir / "llama-server.exe").touch()

    model_dir = tmp_path / "models" / "llm"
    model_dir.mkdir(parents=True)
    model_path = model_dir / "ultravox.gguf"
    model_path.touch()

    mmproj_path = model_dir / "mmproj-ultravox.gguf"
    mmproj_path.touch()

    cfg = LLMSettings(
        model="models/llm/ultravox.gguf",
        mmproj="models/llm/mmproj-ultravox.gguf",
        mode="audio",
        ctx=8192,
        kv_type="f16",
        host="127.0.0.1",
        port=8080,
    )

    cmd = build_launch_command(cfg, tmp_path)
    assert "--mmproj" in cmd
    idx = cmd.index("--mmproj")
    assert cmd[idx + 1] == str(mmproj_path)


def test_build_launch_command_audio_mode_missing_mmproj(tmp_path: Path) -> None:
    """Verifies build_launch_command omits --mmproj if mmproj file does not exist."""
    llama_dir = tmp_path / "app" / "llama-server"
    llama_dir.mkdir(parents=True)
    (llama_dir / "llama-server.exe").touch()

    model_dir = tmp_path / "models" / "llm"
    model_dir.mkdir(parents=True)
    model_path = model_dir / "ultravox.gguf"
    model_path.touch()

    cfg = LLMSettings(
        model="models/llm/ultravox.gguf",
        mmproj="models/llm/nonexistent_mmproj.gguf",
        mode="audio",
        ctx=8192,
        kv_type="f16",
        host="127.0.0.1",
        port=8080,
    )

    cmd = build_launch_command(cfg, tmp_path)
    assert "--mmproj" not in cmd


def test_is_healthy_closed_port() -> None:
    """Verifies is_healthy returns False on an unused/closed localhost port."""
    # Port 59199 is typically unused
    assert not is_healthy("127.0.0.1", 59199, timeout=0.2)


def test_scan_model_registry(tmp_path: Path) -> None:
    """Verifies scanning model directory, assigning audio compatibility badges."""
    models_dir = tmp_path / "models" / "llm"
    models_dir.mkdir(parents=True)

    # Create dummy gguf files
    (models_dir / "llama-3-8b-instruct-q4_k_m.gguf").touch()
    (models_dir / "ultravox-v0.4-q4_k_m.gguf").touch()
    (models_dir / "mmproj-ultravox-f16.gguf").touch()

    registry = scan_model_registry(
        models_dir, active_model_rel="llm/llama-3-8b-instruct-q4_k_m.gguf"
    )

    # mmproj should be filtered from main list
    names = [entry["filename"] for entry in registry]
    assert "llama-3-8b-instruct-q4_k_m.gguf" in names
    assert "ultravox-v0.4-q4_k_m.gguf" in names
    assert "mmproj-ultravox-f16.gguf" not in names

    # Check badges
    llama_entry = next(e for e in registry if "llama" in e["filename"])
    assert llama_entry["is_active"] is True
    assert llama_entry["badge_type"] == "transcript"

    ultravox_entry = next(e for e in registry if "ultravox" in e["filename"])
    # Paired mmproj was present in the dir
    assert ultravox_entry["badge_type"] == "audio"
    assert "🎙" in ultravox_entry["badge"]
