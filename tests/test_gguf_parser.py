"""
Unit tests for GGUF binary header parser in lucca.brain.server_ctl
Spec 02, WI-3, WI-6
"""

import struct
from pathlib import Path

from lucca.brain.server_ctl import parse_gguf_file


def _encode_str(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _create_synthetic_gguf(
    path: Path,
    version: int = 3,
    tensor_count: int = 290,
    metadata: dict[str, str] | None = None,
) -> None:
    """Writes a valid binary GGUF file header with given metadata."""
    if metadata is None:
        metadata = {}

    buf = bytearray()
    # Magic
    buf.extend(b"GGUF")
    # Version
    buf.extend(struct.pack("<I", version))
    # Tensor count
    buf.extend(struct.pack("<Q", tensor_count))
    # KV count
    buf.extend(struct.pack("<Q", len(metadata)))

    for k, v in metadata.items():
        # Key
        buf.extend(_encode_str(k))
        # Value type: 8 = string
        buf.extend(struct.pack("<I", 8))
        buf.extend(_encode_str(v))

    path.write_bytes(bytes(buf))


def test_parse_valid_gguf_file(tmp_path: Path) -> None:
    """Verifies parsing of a valid GGUF file with architecture, name, and quantization."""
    gguf_path = tmp_path / "Meta-Llama-3-8B-Instruct-Q4_K_M.gguf"
    _create_synthetic_gguf(
        gguf_path,
        version=3,
        tensor_count=291,
        metadata={
            "general.architecture": "llama",
            "general.name": "Meta-Llama-3-8B-Instruct",
            "general.quantization_version": "Q4_K_M",
        },
    )

    meta = parse_gguf_file(gguf_path)
    assert meta.is_valid_gguf is True
    assert meta.magic == "GGUF"
    assert meta.version == 3
    assert meta.tensor_count == 291
    assert meta.architecture == "llama"
    assert meta.name == "Meta-Llama-3-8B-Instruct"
    assert meta.quantization == "Q4_K_M"
    assert meta.file_size_bytes > 0


def test_parse_gguf_filename_quant_fallback(tmp_path: Path) -> None:
    """Verifies that quantization falls back to parsing the filename if not in metadata."""
    gguf_path = tmp_path / "custom-model-Q8_0.gguf"
    _create_synthetic_gguf(
        gguf_path,
        version=3,
        tensor_count=100,
        metadata={
            "general.architecture": "mistral",
            "general.name": "custom-model",
        },
    )

    meta = parse_gguf_file(gguf_path)
    assert meta.is_valid_gguf is True
    assert meta.architecture == "mistral"
    assert meta.quantization == "Q8_0"


def test_parse_corrupted_magic(tmp_path: Path) -> None:
    """Verifies that a file without 'GGUF' magic returns is_valid_gguf=False."""
    bad_path = tmp_path / "corrupt.gguf"
    bad_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")

    meta = parse_gguf_file(bad_path)
    assert meta.is_valid_gguf is False
    assert meta.magic == "RIFF"
    assert meta.tensor_count == 0


def test_parse_nonexistent_file(tmp_path: Path) -> None:
    """Verifies that a nonexistent path returns empty invalid metadata without raising."""
    nonexistent = tmp_path / "does_not_exist.gguf"
    meta = parse_gguf_file(nonexistent)
    assert meta.is_valid_gguf is False
    assert meta.magic == ""
    assert meta.file_size_bytes == 0


def test_parse_gguf_filename_quant_fallback_unknown(tmp_path: Path) -> None:
    """Verifies that quantization falls back to 'UNKNOWN' if not in metadata and not in filename."""
    gguf_path = tmp_path / "custom-model-unlabelled.gguf"
    _create_synthetic_gguf(
        gguf_path,
        version=3,
        tensor_count=100,
        metadata={
            "general.architecture": "mistral",
            "general.name": "custom-model",
        },
    )

    meta = parse_gguf_file(gguf_path)
    assert meta.is_valid_gguf is True
    assert meta.architecture == "mistral"
    assert meta.quantization == "UNKNOWN"
