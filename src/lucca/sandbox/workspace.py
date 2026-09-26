"""
Project Lucca — Workspace Lifecycle Manager
Spec 09 §3, D-08
Manages isolated workspace lifecycle under LUCCA_HOME workspace.
"""

import shutil
import time
from pathlib import Path

import structlog

from lucca.core.config import get_config
from lucca.core.exceptions import SandboxPathError

logger = structlog.get_logger(__name__)

MAX_WORKSPACE_BYTES: int = 1024 * 1024 * 1024  # 1 GiB


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
