"""Unit tests for WO-43 Phase 1.3: Win32 Handle Security (`win32_security.py`)
and Transactional Staging DAG (`git_dag.py`) wiring into `SafeFileTool`.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lucca.core.exceptions import SandboxPathError
from lucca.memory.git_dag import StagingTransaction, WorkspaceTransactionManager
from lucca.sandbox.file_tool import SafeFileTool


def test_workspace_transaction_manager_alias() -> None:
    """Proves WorkspaceTransactionManager is exported from lucca.memory.git_dag."""
    assert WorkspaceTransactionManager is StagingTransaction


@pytest.mark.skipif(os.name != "nt", reason="Win32 kernel handle security requires Windows")
def test_safe_file_tool_uses_win32_security_handles_and_blocks_hardlinks(
    tmp_path: Path,
) -> None:
    """Proves SafeFileTool.read_file and write_file route through win32_security on Windows
    and reject hardlinked files before truncation.
    """
    ws = tmp_path / "ws"
    ft = SafeFileTool(workspace_root=ws)

    with (
        patch(
            "lucca.sandbox.file_tool.write_workspace_file_handle",
            wraps=__import__(
                "lucca.sandbox.win32_security", fromlist=["write_workspace_file_handle"]
            ).write_workspace_file_handle,
        ) as spy_write,
        patch(
            "lucca.sandbox.file_tool.read_workspace_file_handle",
            wraps=__import__(
                "lucca.sandbox.win32_security", fromlist=["read_workspace_file_handle"]
            ).read_workspace_file_handle,
        ) as spy_read,
    ):
        w_meta = ft.write_file("hello.txt", "verified handle content", mode="create")
        assert w_meta["size"] == len("verified handle content")
        assert spy_write.call_count == 1

        r_meta, r_text = ft.read_file("hello.txt")
        assert r_text == "verified handle content"
        assert r_meta["size"] == len("verified handle content")
        assert spy_read.call_count == 1

    # Hardlink test: create a hardlink outside the workspace pointing to ws/hello.txt
    external_link = tmp_path / "hardlink_outside.txt"
    os.link(ws / "hello.txt", external_link)
    try:
        with pytest.raises(SandboxPathError) as exc_info:
            ft.write_file("hello.txt", "attempt overwrite via hardlinked file", mode="overwrite")
        assert exc_info.value.code == "hard_link"
        assert (ws / "hello.txt").read_text(encoding="utf-8") == "verified handle content"
    finally:
        if external_link.exists():
            external_link.unlink()


def test_safe_file_tool_apply_patch_transactional_ast_validation_and_rollback(
    tmp_path: Path,
) -> None:
    """Proves SafeFileTool.apply_patch validates Python AST via WorkspaceTransactionManager
    and rolls back on syntax errors.
    """
    ws = tmp_path / "ws_patch"
    ft = SafeFileTool(workspace_root=ws)
    original_code = "def compute(x: int) -> int:\n    return x + 1\n"
    ft.write_file("module.py", original_code, mode="create")

    # 1. Valid patch succeeds
    meta, msg = ft.apply_patch("module.py", "return x + 1", "return x + 2")
    assert meta["applied"] is True
    assert "Successfully applied patch" in msg
    _, updated_code = ft.read_file("module.py")
    assert "return x + 2" in updated_code

    # 2. Invalid syntax patch is rejected by WorkspaceTransactionManager preflight AST hook
    with pytest.raises(SandboxPathError) as exc_info:
        ft.apply_patch("module.py", "return x + 2", "return (x + ")
    assert exc_info.value.code == "patch_validation_failed"
    assert "Python syntax error" in str(exc_info.value)

    # Disk state must remain untouched at the valid state
    _, after_failed = ft.read_file("module.py")
    assert after_failed == updated_code


def test_safe_file_tool_execute_transaction_atomic_multi_file_rollback(
    tmp_path: Path,
) -> None:
    """Proves SafeFileTool.execute_transaction commits valid multi-file batches atomically
    and rolls back all files if any file fails preflight validation.
    """
    ws = tmp_path / "ws_tx"
    ft = SafeFileTool(workspace_root=ws)
    ft.write_file("a.py", "X = 1\n", mode="create")

    # 1. Multi-file transaction where second file has invalid Python syntax -> fails & preserves a.py
    res_fail = ft.execute_transaction(
        [
            {"op_type": "WRITE_FILE", "path": "a.py", "content": "X = 99\n"},
            {"op_type": "WRITE_FILE", "path": "b.py", "content": "def broken(:\n    pass\n"},
        ]
    )
    assert res_fail["success"] is False
    assert "Python syntax error" in str(res_fail["error_message"])
    _, a_content = ft.read_file("a.py")
    assert a_content == "X = 1\n"
    assert not (ws / "b.py").exists()

    # 2. Valid multi-file transaction commits both files atomically
    res_ok = ft.execute_transaction(
        [
            {"op_type": "WRITE_FILE", "path": "a.py", "content": "X = 42\n"},
            {"op_type": "WRITE_FILE", "path": "b.py", "content": "Y = X * 2\n"},
        ]
    )
    assert res_ok["success"] is True
    assert res_ok["operations_executed"] == 2
    _, a_after = ft.read_file("a.py")
    _, b_after = ft.read_file("b.py")
    assert a_after == "X = 42\n"
    assert b_after == "Y = X * 2\n"
