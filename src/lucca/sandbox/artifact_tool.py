"""
Project Lucca — Artifact Verification Tool
Computes SHA-256 and byte size of a file within the workspace.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from lucca.core.exceptions import SandboxPathError


def verify_artifact(workspace_root: Path, rel_path: str) -> tuple[str, int]:
    """
    Computes (sha256_hex, size_bytes) for a file inside workspace_root.
    Refuses path traversal and absolute paths.
    """
    norm = Path(rel_path)
    if norm.is_absolute() or ".." in norm.parts:
        raise SandboxPathError("PATH_TRAVERSAL", f"Path traversal or absolute path disallowed: {rel_path}")

    target = (workspace_root / norm).resolve()
    resolved_root = workspace_root.resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as e:
        raise SandboxPathError("WORKSPACE_ESCAPE", f"Path escapes workspace: {rel_path}") from e

    if not target.is_file():
        raise FileNotFoundError(f"File not found or is not a file: {rel_path}")

    h = hashlib.sha256()
    size = 0
    with open(target, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
            size += len(chunk)

    return h.hexdigest(), size
