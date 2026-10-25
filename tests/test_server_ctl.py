"""
Unit tests for lucca.brain.server_ctl
Spec 02, Spec 08, ADR-001, WI-3, WI-6
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from lucca.brain.server_ctl import (
    build_launch_command,
    compute_sha256,
    is_healthy,
    scan_model_registry,
    start_server,
    verify_model_files,
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


def test_start_server_rejects_hash_mismatch(tmp_path: Path) -> None:
    """Verifies that start_server refuses to spawn when model weights fail SHA256 verification."""
    llama_dir = tmp_path / "app" / "llama-server"
    llama_dir.mkdir(parents=True)
    (llama_dir / "llama-server.exe").touch()

    model_dir = tmp_path / "models" / "llm"
    model_dir.mkdir(parents=True)
    model_path = model_dir / "test-model.gguf"
    model_path.write_bytes(b"corrupted model data")

    manifest_path = tmp_path / "models" / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(
            {
                "files": {
                    "llm/test-model.gguf": {
                        "sha256": "e" * 64,
                        "size_bytes": 100,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = LLMSettings(
        model="models/llm/test-model.gguf",
        mode="transcript",
    )

    with pytest.raises(RuntimeError, match="Model hash mismatch for test-model.gguf"):
        start_server(cfg, tmp_path)


def test_start_server_accepts_verified_weights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that start_server succeeds when model weights match SHA256 pin."""
    llama_dir = tmp_path / "app" / "llama-server"
    llama_dir.mkdir(parents=True)
    (llama_dir / "llama-server.exe").touch()

    model_dir = tmp_path / "models" / "llm"
    model_dir.mkdir(parents=True)
    model_path = model_dir / "test-model.gguf"
    model_bytes = b"valid model binary content"
    model_path.write_bytes(model_bytes)

    real_hash = hashlib.sha256(model_bytes).hexdigest()
    manifest_path = tmp_path / "models" / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(
            {
                "files": {
                    "llm/test-model.gguf": {
                        "sha256": real_hash,
                        "size_bytes": len(model_bytes),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = LLMSettings(
        model="models/llm/test-model.gguf",
        mode="transcript",
    )

    called: list[list[str]] = []

    def mock_popen(cmd: list[str], **kwargs: object) -> str:
        called.append(cmd)
        return "mock_proc"

    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    proc = start_server(cfg, tmp_path)
    assert proc == "mock_proc"
    assert len(called) == 1


def test_compute_sha256(tmp_path: Path) -> None:
    """Verifies compute_sha256 matches hashlib output."""
    sample = tmp_path / "sample.bin"
    content = b"testing sha256 streaming implementation"
    sample.write_bytes(content)
    assert compute_sha256(sample) == hashlib.sha256(content).hexdigest()


def test_verify_model_files_missing_manifest(tmp_path: Path) -> None:
    """Verifies verify_model_files raises FileNotFoundError if manifest is missing."""
    cfg = LLMSettings(model="models/llm/missing.gguf")
    with pytest.raises(FileNotFoundError):
        verify_model_files(cfg, tmp_path)


def test_build_launch_command_speculative_decoding(tmp_path: Path) -> None:
    """Verifies launch command construction for ngram, draft model, and both."""
    llama_dir = tmp_path / "app" / "llama-server"
    llama_dir.mkdir(parents=True)
    (llama_dir / "llama-server.exe").touch()

    model_dir = tmp_path / "models" / "llm"
    model_dir.mkdir(parents=True)
    (model_dir / "target.gguf").touch()
    (model_dir / "draft.gguf").touch()

    # 1. N-Gram only
    cfg_ngram = LLMSettings(
        model="models/llm/target.gguf",
        spec_type="ngram-mod",
        kv_type_k="q8_0",
        kv_type_v="q4_0",
        ngl=24,
    )
    cmd1 = build_launch_command(cfg_ngram, tmp_path)
    assert "--spec-type" in cmd1
    assert "ngram-mod" in cmd1
    assert "--cache-type-k" in cmd1 and "q8_0" in cmd1
    assert "--cache-type-v" in cmd1 and "q4_0" in cmd1
    assert "--n-gpu-layers" in cmd1 and "24" in cmd1
    assert "--spec-draft-model" not in cmd1

    # 2. Draft model only
    cfg_draft = LLMSettings(
        model="models/llm/target.gguf",
        spec_type="draft-simple",
        draft_model="models/llm/draft.gguf",
        draft_ngl=99,
        draft_n_max=4,
        draft_kv_type_k="q8_0",
        draft_kv_type_v="q4_0",
        cpu_moe=True,
        moe_expert_cache_mib=4096,
    )
    cmd2 = build_launch_command(cfg_draft, tmp_path)
    assert "--spec-type" in cmd2
    assert "draft-simple" in cmd2
    assert "--spec-draft-model" in cmd2
    assert str(model_dir / "draft.gguf") in cmd2
    assert "--spec-draft-ngl" in cmd2 and "99" in cmd2
    assert "--spec-draft-n-max" in cmd2 and "4" in cmd2
    assert "--spec-draft-type-k" in cmd2 and "q8_0" in cmd2
    assert "--spec-draft-type-v" in cmd2 and "q4_0" in cmd2
    assert "--cpu-moe" in cmd2
    assert "--moe-cache-mib" in cmd2 and "4096" in cmd2

    # 3. Both (draft-simple,ngram-mod)
    cfg_both = LLMSettings(
        model="models/llm/target.gguf",
        spec_type="draft-simple,ngram-mod",
        draft_model="models/llm/draft.gguf",
    )
    cmd3 = build_launch_command(cfg_both, tmp_path)
    assert "--spec-type" in cmd3
    assert "draft-simple,ngram-mod" in cmd3
    assert "--spec-draft-model" in cmd3


def test_derive_quant_from_filename_dotted() -> None:
    from lucca.brain.server_ctl import _derive_quant_from_filename
    assert _derive_quant_from_filename("gemma-4-26B-A4B-it-heretic.Q6_K.gguf") == "Q6_K"
    assert _derive_quant_from_filename("model-f16.gguf") == "F16"
    assert _derive_quant_from_filename("unknown-model.gguf") == "UNKNOWN"
