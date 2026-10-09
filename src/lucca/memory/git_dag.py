"""
Project Lucca — Transactional Git Staging DAG (Module 8 / WO-33)
Spec: plans/2026-10-03_wo29_neurosymbolic_program_synthesis_and_15_module_cognitive_ladder.md §2

Implements an in-memory Directed Acyclic Graph (DAG) for staging filesystem modifications,
enforcing dependency ordering, cycle detection, preflight AST/syntax validation,
and atomic commit/rollback semantics with zero dirty workspace state.

Invariants:
- Zero-Any typing discipline strictly enforced (D-AUD-01).
- Hardware budget: ΔVRAM = 0 MB, ΔRAM <= 50 MB.
- Sub-millisecond DAG validation and cycle detection.
- Atomic commit with automatic rollback on validation or I/O failure.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
import difflib
from enum import Enum
import hashlib
from pathlib import Path
import time
from typing import Final

from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)


class OperationType(str, Enum):
    """Supported filesystem operation primitives in the staging DAG."""

    WRITE_FILE = "WRITE_FILE"
    DELETE_FILE = "DELETE_FILE"
    CREATE_DIR = "CREATE_DIR"
    APPLY_DIFF = "APPLY_DIFF"


class DAGError(Exception):
    """Base exception for staging DAG operations."""


class CycleDetectedError(DAGError):
    """Raised when a dependency cycle is detected in the staging DAG."""


class MissingDependencyError(DAGError):
    """Raised when an operation depends on an unregistered op_id."""


class StagedOperation(BaseModel):
    """A discrete filesystem mutation node in the staging DAG."""

    op_id: str
    op_type: OperationType
    path: Path
    content: str | None = None
    expected_hash: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)

    def compute_content_hash(self) -> str | None:
        """Computes SHA-256 hash of staged content if present."""
        if self.content is None:
            return None
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class TransactionCommitResult(BaseModel):
    """Outcome report for an executed staging transaction commit."""

    success: bool
    operations_executed: int
    files_created: list[Path] = Field(default_factory=list)
    files_modified: list[Path] = Field(default_factory=list)
    files_deleted: list[Path] = Field(default_factory=list)
    dirs_created: list[Path] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    error_message: str | None = None


class GitStagingDAG:
    """
    Directed Acyclic Graph governing staged workspace mutations.
    Nodes are StagedOperations; directed edges point from dependencies to dependent ops.
    """

    def __init__(self) -> None:
        self.operations: dict[str, StagedOperation] = {}
        self._adj: dict[str, list[str]] = defaultdict(list)
        self._rev_adj: dict[str, list[str]] = defaultdict(list)

    def add_operation(self, op: StagedOperation) -> None:
        """Registers a staged operation node and its dependency edges."""
        if op.op_id in self.operations:
            raise ValueError(f"Operation '{op.op_id}' is already registered in DAG")

        self.operations[op.op_id] = op
        for dep_id in op.dependencies:
            self._adj[dep_id].append(op.op_id)
            self._rev_adj[op.op_id].append(dep_id)

    def validate_dependencies(self) -> None:
        """Validates that all declared dependency op_ids exist in the DAG."""
        for op in self.operations.values():
            for dep_id in op.dependencies:
                if dep_id not in self.operations:
                    raise MissingDependencyError(
                        f"Operation '{op.op_id}' depends on missing operation '{dep_id}'"
                    )

    def has_cycle(self) -> bool:
        """Checks for cycle presence using depth-first search."""
        self.validate_dependencies()
        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited

        for op_id in self.operations:
            visited[op_id] = 0

        def _dfs(node: str) -> bool:
            visited[node] = 1
            for neighbor in self._adj.get(node, []):
                state = visited.get(neighbor, 0)
                if state == 1:
                    return True
                if state == 0 and _dfs(neighbor):
                    return True
            visited[node] = 2
            return False

        return any(visited[op_id] == 0 and _dfs(op_id) for op_id in self.operations)

    def topological_order(self) -> list[StagedOperation]:
        """
        Computes valid execution order using Kahn's algorithm.
        Raises CycleDetectedError if the graph contains dependencies forming a cycle.
        """
        self.validate_dependencies()

        in_degree: dict[str, int] = {op_id: 0 for op_id in self.operations}
        for op_id in self.operations:
            for dep_id in self.operations[op_id].dependencies:
                in_degree[op_id] += 1

        queue: deque[str] = deque([op_id for op_id, deg in in_degree.items() if deg == 0])
        ordered: list[StagedOperation] = []

        while queue:
            curr = queue.popleft()
            ordered.append(self.operations[curr])
            for dependent in self._adj.get(curr, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(ordered) != len(self.operations):
            raise CycleDetectedError("Dependency cycle detected in GitStagingDAG")

        return ordered

    def compute_diffs(self) -> dict[Path, str]:
        """
        Computes unified diffs for all staged file modifications against disk state
        without applying changes.
        """
        diffs: dict[Path, str] = {}
        for op in self.operations.values():
            if op.op_type in (OperationType.WRITE_FILE, OperationType.APPLY_DIFF):
                orig_text = ""
                if op.path.exists() and op.path.is_file():
                    try:
                        orig_text = op.path.read_text(encoding="utf-8")
                    except Exception as exc:
                        logger.debug("staged_diff_read_failed", path=str(op.path), error=str(exc))
                        orig_text = "<binary or unreadable>"
                new_text = op.content or ""
                diff_lines = list(
                    difflib.unified_diff(
                        orig_text.splitlines(keepends=True),
                        new_text.splitlines(keepends=True),
                        fromfile=str(op.path),
                        tofile=f"{op.path} (staged)",
                    )
                )
                diffs[op.path] = "".join(diff_lines)
            elif op.op_type == OperationType.DELETE_FILE:
                orig_text = ""
                if op.path.exists() and op.path.is_file():
                    try:
                        orig_text = op.path.read_text(encoding="utf-8")
                    except Exception as exc:
                        logger.debug("staged_diff_delete_read_failed", path=str(op.path), error=str(exc))
                        orig_text = ""
                diff_lines = list(
                    difflib.unified_diff(
                        orig_text.splitlines(keepends=True),
                        [],
                        fromfile=str(op.path),
                        tofile="/dev/null",
                    )
                )
                diffs[op.path] = "".join(diff_lines)
        return diffs


# Type alias for preflight validation hook
ValidatorHook = Callable[[StagedOperation], tuple[bool, str | None]]


class StagingTransaction:
    """
    Context manager and controller for atomic workspace transactions.
    Supports staging writes, deletes, preflight hooks, commit, and safe rollback.
    """

    def __init__(
        self,
        workspace_root: Path | None = None,
        validators: list[ValidatorHook] | None = None,
    ) -> None:
        self.workspace_root = workspace_root or Path.cwd()
        self.dag = GitStagingDAG()
        self.validators: list[ValidatorHook] = validators or []
        self._op_counter = 0
        self._in_transaction = False
        self._backups: dict[Path, str | None] = {}  # None indicates file didn't exist
        self._created_dirs: list[Path] = []

    def __enter__(self) -> StagingTransaction:
        self.begin()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if exc_type is not None:
            logger.warning("transaction_aborted_due_to_exception", error=str(exc_val))
            self.rollback()
        elif self._in_transaction:
            # If not explicitly committed, rollback by default
            self.rollback()

    def begin(self) -> None:
        """Starts a new staging transaction session."""
        self.dag = GitStagingDAG()
        self._op_counter = 0
        self._backups.clear()
        self._created_dirs.clear()
        self._in_transaction = True

    def _next_op_id(self, prefix: str = "op") -> str:
        self._op_counter += 1
        return f"{prefix}_{self._op_counter:04d}"

    def stage_write(
        self,
        path: Path | str,
        content: str,
        dependencies: list[str] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Stages a file write operation."""
        p = Path(path)
        op_id = self._next_op_id("write")
        op = StagedOperation(
            op_id=op_id,
            op_type=OperationType.WRITE_FILE,
            path=p,
            content=content,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        self.dag.add_operation(op)
        return op_id

    def stage_delete(
        self,
        path: Path | str,
        dependencies: list[str] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Stages a file deletion operation."""
        p = Path(path)
        op_id = self._next_op_id("delete")
        op = StagedOperation(
            op_id=op_id,
            op_type=OperationType.DELETE_FILE,
            path=p,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        self.dag.add_operation(op)
        return op_id

    def stage_mkdir(
        self,
        path: Path | str,
        dependencies: list[str] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Stages a directory creation operation."""
        p = Path(path)
        op_id = self._next_op_id("mkdir")
        op = StagedOperation(
            op_id=op_id,
            op_type=OperationType.CREATE_DIR,
            path=p,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        self.dag.add_operation(op)
        return op_id

    def run_preflight_validation(self) -> list[str]:
        """
        Executes all configured validator hooks over staged operations in dependency order.
        Returns list of error messages (empty if all pass).
        """
        errors: list[str] = []
        ordered_ops = self.dag.topological_order()
        for op in ordered_ops:
            for validator in self.validators:
                try:
                    passed, reason = validator(op)
                    if not passed:
                        errors.append(
                            f"Validation failed for op '{op.op_id}' ({op.path}): {reason or 'Unknown reason'}"
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("validator_execution_error", op_id=op.op_id, error=str(exc))
                    errors.append(f"Validator error on '{op.op_id}': {exc}")
        return errors

    def commit(self, dry_run: bool = False) -> TransactionCommitResult:
        """
        Executes preflight validation and applies all staged operations atomically.
        If any validation or filesystem operation fails, automatically rolls back.
        """
        t_start = time.perf_counter()

        # 1. Check for cycles and get topological execution order
        try:
            ordered_ops = self.dag.topological_order()
        except CycleDetectedError as exc:
            return TransactionCommitResult(
                success=False,
                operations_executed=0,
                error_message=f"Cannot commit cyclic DAG: {exc}",
                elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
            )

        # 2. Run preflight validators
        val_errors = self.run_preflight_validation()
        if val_errors:
            err_msg = "; ".join(val_errors)
            logger.warning("staging_preflight_failed", errors=val_errors)
            return TransactionCommitResult(
                success=False,
                operations_executed=0,
                error_message=f"Preflight validation failed: {err_msg}",
                elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
            )

        if dry_run:
            self._in_transaction = False
            return TransactionCommitResult(
                success=True,
                operations_executed=len(ordered_ops),
                elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
            )

        # 3. Snapshot disk state for rollback safety
        created_files: list[Path] = []
        modified_files: list[Path] = []
        deleted_files: list[Path] = []
        dirs_created: list[Path] = []

        try:
            for op in ordered_ops:
                target = op.path
                if op.op_type in (OperationType.WRITE_FILE, OperationType.APPLY_DIFF):
                    if target.exists():
                        if target not in self._backups:
                            self._backups[target] = target.read_text(encoding="utf-8")
                        modified_files.append(target)
                    else:
                        if target not in self._backups:
                            self._backups[target] = None  # Did not exist
                        created_files.append(target)

                    # Ensure parent dir exists
                    if not target.parent.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(op.content or "", encoding="utf-8")

                elif op.op_type == OperationType.CREATE_DIR:
                    if not target.exists():
                        target.mkdir(parents=True, exist_ok=True)
                        self._created_dirs.append(target)
                        dirs_created.append(target)

                elif op.op_type == OperationType.DELETE_FILE:
                    if target.exists():
                        if target not in self._backups:
                            self._backups[target] = target.read_text(encoding="utf-8")
                        target.unlink()
                        deleted_files.append(target)

            self._in_transaction = False
            elapsed = (time.perf_counter() - t_start) * 1000.0
            return TransactionCommitResult(
                success=True,
                operations_executed=len(ordered_ops),
                files_created=created_files,
                files_modified=modified_files,
                files_deleted=deleted_files,
                dirs_created=dirs_created,
                elapsed_ms=elapsed,
            )

        except Exception as exc:
            logger.error("staging_commit_failed_rolling_back", error=str(exc))
            self.rollback()
            return TransactionCommitResult(
                success=False,
                operations_executed=0,
                error_message=f"I/O error during commit: {exc}",
                elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
            )

    def rollback(self) -> None:
        """
        Restores workspace to baseline state:
        - Reverts modified files to pre-transaction content
        - Deletes newly created files
        - Re-creates deleted files from backup
        - Cleans up created empty directories
        """
        logger.info("reverting_staging_transaction", backup_count=len(self._backups))
        for path, backup_content in self._backups.items():
            try:
                if backup_content is None:
                    # File did not exist prior to transaction -> remove it
                    if path.exists():
                        path.unlink()
                else:
                    # File existed -> restore original content
                    if not path.parent.exists():
                        path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(backup_content, encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                logger.error("rollback_restore_error", path=str(path), error=str(exc))

        # Clean up newly created directories in reverse order
        for d in reversed(self._created_dirs):
            try:
                if d.exists() and d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            except Exception as exc:  # noqa: BLE001
                logger.debug("cleanup_dir_skipped", path=str(d), error=str(exc))

        self._backups.clear()
        self._created_dirs.clear()
        self._in_transaction = False
