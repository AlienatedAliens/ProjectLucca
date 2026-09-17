"""
Project Lucca — Workspace Lifecycle Manager
Spec 09 §3, D-08
Manages isolated workspace lifecycle under C:\\ProjectLucca\\workspace.
"""

import shutil
import time
from pathlib import Path

import structlog

from lucca.core.config import get_config
from lucca.core.exceptions import SandboxPathError

logger = structlog.get_logger(__name__)

MAX_WORKSPACE_BYTES: int = 1024 * 1024 * 1024  # 1 GiB
MAX_INBOX_IMPORT_BYTES: int = 200 * 1024 * 1024  # 200 MB


class WorkspaceManager:
    """
    Manages the lifecycle and hygiene of the task workspace.
    Ensures safe creation, inbox copying, size auditing, and clean wipes.
    """

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        inbox_root: Path | str | None = None,
    ) -> None:
        self.config = get_config()
        self.workspace_root = (
            Path(workspace_root) if workspace_root else self.config.resolve_path("workspace")
        )
        self.inbox_root = Path(inbox_root) if inbox_root else self.config.resolve_path("inbox")

        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.inbox_root.mkdir(parents=True, exist_ok=True)

    def reset_workspace(self, max_retries: int = 3, delay_s: float = 0.2) -> bool:
        """
        Deletes every entry under workspace/.
        Retries on Windows sharing violations (3x with 200ms delay).
        Returns True if completely empty, False if any file remained locked.
        """
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        for item in self.workspace_root.iterdir():
            deleted = False
            for attempt in range(max_retries):
                try:
                    if item.is_dir() and not item.is_symlink():
                        shutil.rmtree(item)
                    else:
                        item.unlink(missing_ok=True)
                    deleted = True
                    break
                except (PermissionError, OSError) as exc:
                    logger.debug(
                        "workspace_clean_retry",
                        item=item.name,
                        attempt=attempt + 1,
                        error=str(exc),
                    )
                    time.sleep(delay_s)

            if not deleted:
                logger.warning("workspace_entry_locked", item=item.name)

        remaining = list(self.workspace_root.iterdir())
        is_clean = len(remaining) == 0
        if is_clean:
            logger.info("workspace_reset_complete", path=str(self.workspace_root))
        else:
            logger.error("workspace_reset_incomplete", remaining=[p.name for p in remaining])
        return is_clean

    def import_from_inbox(self, filename: str) -> Path:
        """
        Copies a user-named file from inbox/ into workspace/.
        Enforces 200 MB limit and safe filename check.
        """
        clean_name = Path(filename).name
        if not clean_name or clean_name != filename:
            raise SandboxPathError(
                "invalid_chars", f"Filename '{filename}' is not a plain filename"
            )

        src = self.inbox_root / clean_name
        if not src.exists() or not src.is_file():
            raise SandboxPathError("not_found", f"File '{clean_name}' not found in inbox")

        file_size = src.stat().st_size
        if file_size > MAX_INBOX_IMPORT_BYTES:
            raise SandboxPathError(
                "too_large",
                f"Inbox file '{clean_name}' size {file_size} exceeds {MAX_INBOX_IMPORT_BYTES} B",
            )

        dst = self.workspace_root / clean_name
        shutil.copy2(src, dst)
        logger.info("inbox_file_imported", file=clean_name, size=file_size)
        return dst

    def get_total_size(self) -> int:
        """Calculates total size of all files under workspace in bytes."""
        total = 0
        for p in self.workspace_root.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except (OSError, ValueError):
                    pass
        return total

    def check_size_limit(self) -> tuple[bool, int]:
        """Checks if total size is within 1 GiB limit."""
        size = self.get_total_size()
        return (size <= MAX_WORKSPACE_BYTES), size
