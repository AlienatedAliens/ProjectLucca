"""
Project Lucca — Path-Traversal Protected Safe File Tool
Operates strictly within an isolated sandbox workspace root.
"""

from pathlib import Path
from typing import List
from lucca.core.exceptions import PathTraversalException

class SafeFileTool:
    def __init__(self, workspace_root: Path):
        self._workspace_root = workspace_root.resolve()
        self._workspace_root.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """
        Resolves the canonical path and verifies it resides strictly
        inside the workspace root.
        """
        # Block Windows special device names and UNC syntax
        normalized = relative_path.replace("\\", "/").strip()
        if normalized.startswith("//") or normalized.startswith("\\\\"):
            raise PathTraversalException(f"UNC paths are forbidden: '{relative_path}'")
        
        target = (self._workspace_root / normalized).resolve()
        
        try:
            target.relative_to(self._workspace_root)
        except ValueError:
            raise PathTraversalException(
                f"Access denied: path '{relative_path}' escapes workspace sandbox '{self._workspace_root}'"
            )
        
        return target

    def write_file(self, relative_path: str, content: str) -> str:
        safe_path = self._resolve_safe_path(relative_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {relative_path}"

    def read_file(self, relative_path: str) -> str:
        safe_path = self._resolve_safe_path(relative_path)
        if not safe_path.exists() or not safe_path.is_file():
            raise FileNotFoundError(f"File not found: '{relative_path}'")
        return safe_path.read_text(encoding="utf-8")

    def list_files(self, relative_path: str = ".") -> List[str]:
        safe_dir = self._resolve_safe_path(relative_path)
        if not safe_dir.is_dir():
            raise NotADirectoryError(f"Directory not found: '{relative_path}'")
        return [p.relative_to(self._workspace_root).as_posix() for p in safe_dir.rglob("*") if p.is_file()]
