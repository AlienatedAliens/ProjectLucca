"""
Project Lucca — Safe Scratchpad Note Tool
Spec 1.1.2 §2, Spec 10 §4, T2 Native Tools
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from lucca.core.config import get_config
from lucca.core.exceptions import SandboxPathError

# Safe note name pattern: alphanumeric, hyphen, underscore, dot
SAFE_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_\.\-]+$")


class SafeNoteTool:
    """
    Scratchpad note management tool operating in an isolated notes directory.
    Completely separated from the user workspace.
    """

    def __init__(self, notes_dir: Path | str | None = None) -> None:
        if notes_dir is not None:
            self.notes_dir = Path(notes_dir)
        else:
            self.notes_dir = Path(get_config().resolve_path("notes"))
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_note_path(self, name: str) -> Path:
        clean_name = name.strip()
        if not clean_name:
            raise SandboxPathError("invalid_name", "Note name cannot be empty")
        if not SAFE_NAME_RE.match(clean_name) or ".." in clean_name:
            msg = (
                f"Invalid note name: '{name}'. Must be alphanumeric, underscores, hyphens, or dots."
            )
            raise SandboxPathError("invalid_name", msg)

        target = (self.notes_dir / clean_name).resolve()
        notes_resolved = self.notes_dir.resolve()
        if not target.is_relative_to(notes_resolved):
            raise SandboxPathError(
                "path_traversal", f"Path traversal attempted in note name: {name}"
            )
        return target

    def write_note(
        self, name: str, content: str, append: bool = False
    ) -> tuple[dict[str, JsonValue], str]:
        """Writes or appends to a scratchpad note file."""
        path = self._resolve_note_path(name)
        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)

        action = "appended" if append else "written"
        msg = f"Note '{name}' {action} successfully ({len(content.encode('utf-8'))} bytes)."
        structured: dict[str, JsonValue] = {
            "name": name,
            "path": str(path),
            "bytes": len(content.encode("utf-8")),
            "appended": append,
        }
        return structured, msg

    def read_note(self, name: str) -> tuple[dict[str, JsonValue], str]:
        """Reads the full text of a scratchpad note file."""
        path = self._resolve_note_path(name)
        if not path.exists() or not path.is_file():
            structured: dict[str, JsonValue] = {"name": name, "found": False}
            return structured, f"Note '{name}' not found."

        text = path.read_text(encoding="utf-8")
        structured = {
            "name": name,
            "found": True,
            "size": len(text),
        }
        return structured, text
