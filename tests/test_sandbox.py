"""
Project Lucca — Hardened Sandbox File Tool Tests
Spec 09 §9 (T-SBX-01, T-SBX-02, T-SBX-03, P-03)
"""

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from lucca.core.exceptions import SandboxPathError
from lucca.sandbox.file_tool import SafeFileTool, validate_rel_path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "sandbox_workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def file_tool(workspace: Path) -> SafeFileTool:
    return SafeFileTool(workspace_root=workspace)


def test_t_sbx_01_malicious_path_fixtures(workspace: Path):
    """T-SBX-01: Malicious paths raise SandboxPathError with correct code; benign paths pass."""
    malicious = [
        ("../escape.txt", "traversal"),
        ("../../etc/passwd", "traversal"),
        ("/absolute/path", "traversal"),
        ("subdir/../../escape", "traversal"),
        ("~/.bashrc", "traversal"),
        ("~/notes.txt", "traversal"),
        ("file..%2f..%2fetc", "invalid_chars"),  # % is rejected
        ("hello%20world.txt", "invalid_chars"),  # % is rejected
        ("win\\path\\test", "invalid_chars"),  # backslash rejected
        ("nul", "reserved"),  # Windows reserved device
        ("nul.txt", "reserved"),
        ("CON", "reserved"),
        ("com1.dat", "reserved"),
        ("aux.json", "reserved"),
        ("file\x00name.txt", "invalid_chars"),  # NUL byte
        ("a" * 1025, "too_long"),  # > 1024 chars
        ("dir//file.txt", "invalid_chars"),  # consecutive slashes
        ("", "invalid_chars"),  # empty string
    ]

    for path_str, expected_code in malicious:
        with pytest.raises(SandboxPathError) as exc_info:
            validate_rel_path(path_str, workspace_root=workspace)
        assert exc_info.value.code == expected_code, (
            f"Failed for {path_str}: got {exc_info.value.code}, expected {expected_code}"
        )

    # Benign paths pass
    benign = [
        "file.txt",
        "notes/todo.md",
        "deep/nested/directory/file.py",
        "project-name_v1.0.tar.gz",
        "UPPERCASE_FILE.TXT",
    ]
    for p in benign:
        target = validate_rel_path(p, workspace_root=workspace)
        assert target.is_relative_to(workspace)


def test_t_sbx_03_read_file_truncation_and_binary(file_tool: SafeFileTool, workspace: Path):
    """T-SBX-03: read_file 300 KiB -> truncated flag, 256 KiB content; binary -> is_binary."""
    # 1. 300 KiB file
    large_file = workspace / "large.txt"
    chunk = b"A" * 1024
    large_file.write_bytes(chunk * 300)

    structured, content = file_tool.read_file("large.txt")
    assert structured["truncated"] is True
    assert len(content.encode("utf-8")) == 262144
    assert structured["size"] == 300 * 1024

    # 2. Binary file sniff
    bin_file = workspace / "binary.dat"
    bin_file.write_bytes(b"hello world\x00more data")
    with pytest.raises(SandboxPathError) as exc:
        file_tool.read_file("binary.dat")
    assert exc.value.code == "is_binary"


def test_file_write_create_mode_and_delete(file_tool: SafeFileTool, workspace: Path):
    """Test file creation, overwrite, append, and deletion."""
    # Create mode
    res = file_tool.write_file("test.txt", "Initial content", mode="create")
    assert isinstance(res["size"], int) and res["size"] > 0
    assert (workspace / "test.txt").read_text() == "Initial content"

    # Create mode when file already exists -> traversal/exists error
    with pytest.raises(SandboxPathError):
        file_tool.write_file("test.txt", "New content", mode="create")

    # Overwrite mode
    file_tool.write_file("test.txt", "Updated", mode="overwrite")
    assert (workspace / "test.txt").read_text() == "Updated"

    # Append mode
    file_tool.write_file("test.txt", " appended", mode="append")
    assert (workspace / "test.txt").read_text() == "Updated appended"

    # Delete
    del_res = file_tool.delete_file("test.txt")
    assert del_res["deleted"] is True
    assert not (workspace / "test.txt").exists()


@given(st.text())
@settings(
    max_examples=100, deadline=1000, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_p_03_validate_rel_path_fuzz(workspace: Path, s: str):
    """P-03: Any string -> resolves under /workspace or raises SandboxPathError; never other exception."""
    try:
        resolved = validate_rel_path(s, workspace_root=workspace)
        assert resolved.is_relative_to(workspace)
    except SandboxPathError:
        pass
    except Exception as e:
        pytest.fail(f"Unexpected exception {type(e).__name__}: {e} for input {s!r}")
