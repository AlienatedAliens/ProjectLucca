"""
Project Lucca — SQLite + WAL + sqlite-vec Database Manager
Spec 04 §1, §2, ADR-002
"""

import json
import re
import sqlite3
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

import sqlite_vec
import structlog
from pydantic import JsonValue

from lucca.core.schemas import Decision, ExecutionTriple, Outcome, Proposal

logger = structlog.get_logger(__name__)

DEFAULT_DB_PATH: Final[Path] = Path(r"C:\ProjectLucca\data\memory.sqlite")
MIGRATIONS_DIR: Final[Path] = Path(__file__).parent / "migrations"


def configure_connection(conn: sqlite3.Connection) -> None:
    """Apply standard pragmas and load sqlite-vec extension per Spec 04 §1."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-65536;")  # 64 MiB

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


class DatabaseManager:
    """
    Manages SQLite connections with WAL mode, busy timeout, and sqlite-vec.
    Ensures single-writer discipline and forward migration execution.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._writer_conn: sqlite3.Connection | None = None
        self._write_lock = threading.Lock()
        self._is_closed = False

    @contextmanager
    def write_transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides thread-safe atomic transaction on dedicated writer connection."""
        with self._write_lock:
            writer = self.get_writer()
            writer.execute("BEGIN IMMEDIATE")
            try:
                yield writer
                writer.execute("COMMIT")
            except Exception:
                writer.execute("ROLLBACK")
                raise

    def get_connection(self) -> sqlite3.Connection:
        """Create a fresh configured SQLite connection."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode; we manage transactions explicitly
        )
        conn.row_factory = sqlite3.Row
        configure_connection(conn)
        return conn

    def get_writer(self) -> sqlite3.Connection:
        """Return the dedicated writer connection."""
        if self._writer_conn is None:
            self._writer_conn = self.get_connection()
        return self._writer_conn

    def migrate(self, migrations_dir: Path = MIGRATIONS_DIR) -> list[int]:
        """
        Run forward schema migrations idempotently.
        Returns list of applied migration versions.
        """
        conn = self.get_writer()
        # Ensure schema_migrations table exists
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations("
            "version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
        )

        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_migrations")
        applied_versions = {int(row[0]) for row in cur.fetchall()}

        applied: list[int] = []
        if not migrations_dir.exists():
            return applied

        sql_files = sorted(migrations_dir.glob("*.sql"))
        for f in sql_files:
            match = re.match(r"^(\d+)_", f.name)
            if not match:
                continue
            version = int(match.group(1))
            if version in applied_versions:
                continue

            logger.info("applying_memory_migration", version=version, file=f.name)
            sql_script = f.read_text(encoding="utf-8")
            now = time.time()

            try:
                conn.executescript(sql_script)
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, now),
                )
                applied.append(version)
            except Exception:
                logger.error("migration_failed", version=version, exc_info=True)
                raise

        return applied

    @contextmanager
    def read_cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Scoped reader connection cursor."""
        conn = self.get_connection()
        try:
            yield conn.cursor()
        finally:
            conn.close()

    def check_integrity(self) -> bool:
        """Run PRAGMA integrity_check and return True if ok."""
        with self.read_cursor() as cur:
            cur.execute("PRAGMA integrity_check;")
            row = cur.fetchone()
            return row is not None and row[0] == "ok"

    def record_execution_triple(self, triple: ExecutionTriple) -> None:
        """Persists an execution triple (Proposal, Decision, Outcome) to SQLite WAL."""
        prop_json = json.dumps(triple.proposal.model_dump(mode="json"))
        dec_json = json.dumps(triple.decision.model_dump(mode="json"))
        out_json = json.dumps(triple.outcome.model_dump(mode="json"))
        with self.write_transaction() as writer:
            writer.execute(
                """
                INSERT INTO execution_triples (
                    triple_id, proposal_json, decision_json, outcome_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(triple_id) DO UPDATE SET
                    proposal_json=excluded.proposal_json,
                    decision_json=excluded.decision_json,
                    outcome_json=excluded.outcome_json,
                    created_at=excluded.created_at
                """,
                (triple.triple_id, prop_json, dec_json, out_json, triple.created_at),
            )

    def get_execution_triple(self, triple_id: str) -> ExecutionTriple | None:
        """Reads an execution triple from SQLite by triple_id."""
        with self.read_cursor() as cur:
            cur.execute(
                """
                SELECT triple_id, proposal_json, decision_json, outcome_json, created_at
                FROM execution_triples
                WHERE triple_id = ?
                """,
                (triple_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return ExecutionTriple(
                triple_id=str(row[0]),
                proposal=Proposal.model_validate(json.loads(row[1])),
                decision=Decision.model_validate(json.loads(row[2])),
                outcome=Outcome.model_validate(json.loads(row[3])),
                created_at=float(row[4]),
            )

    def list_execution_triples(self, limit: int = 100) -> list[ExecutionTriple]:
        """Lists recent execution triples ordered by created_at DESC."""
        with self.read_cursor() as cur:
            cur.execute(
                """
                SELECT triple_id, proposal_json, decision_json, outcome_json, created_at
                FROM execution_triples
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            triples: list[ExecutionTriple] = []
            for row in cur.fetchall():
                triples.append(
                    ExecutionTriple(
                        triple_id=str(row[0]),
                        proposal=Proposal.model_validate(json.loads(row[1])),
                        decision=Decision.model_validate(json.loads(row[2])),
                        outcome=Outcome.model_validate(json.loads(row[3])),
                        created_at=float(row[4]),
                    )
                )
            return triples

    def record_contrastive_shadow_log(
        self,
        log_id: str,
        rule_id: str,
        trace_id: str,
        ts: float,
        rule_plan_json: str,
        core_action_json: str,
        agreed: bool,
        rule_outcome_signal: str | None = None,
        core_outcome_signal: str | None = None,
    ) -> None:
        """Persists a paired contrastive shadow evaluation log per Spec §6.2 (Rung L2)."""
        writer = self.get_writer()
        writer.execute("BEGIN IMMEDIATE")
        try:
            writer.execute(
                """
                INSERT OR REPLACE INTO contrastive_shadow_logs (
                    log_id, rule_id, trace_id, ts, rule_plan_json, core_action_json,
                    agreed, rule_outcome_signal, core_outcome_signal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    rule_id,
                    trace_id,
                    ts,
                    rule_plan_json,
                    core_action_json,
                    1 if agreed else 0,
                    rule_outcome_signal,
                    core_outcome_signal,
                ),
            )
            writer.execute("COMMIT")
        except Exception:
            writer.execute("ROLLBACK")
            raise

    def list_contrastive_shadow_logs(
        self, rule_id: str | None = None, limit: int = 100
    ) -> list[dict[str, JsonValue]]:
        """Lists paired contrastive shadow logs ordered by ts DESC."""
        with self.read_cursor() as cur:
            if rule_id is not None:
                cur.execute(
                    """
                    SELECT log_id, rule_id, trace_id, ts, rule_plan_json, core_action_json,
                           agreed, rule_outcome_signal, core_outcome_signal
                    FROM contrastive_shadow_logs
                    WHERE rule_id = ?
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (rule_id, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT log_id, rule_id, trace_id, ts, rule_plan_json, core_action_json,
                           agreed, rule_outcome_signal, core_outcome_signal
                    FROM contrastive_shadow_logs
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            records: list[dict[str, JsonValue]] = []
            for row in cur.fetchall():
                records.append(
                    {
                        "log_id": str(row[0]),
                        "rule_id": str(row[1]),
                        "trace_id": str(row[2]),
                        "ts": float(row[3]),
                        "rule_plan_json": str(row[4]),
                        "core_action_json": str(row[5]),
                        "agreed": bool(row[6]),
                        "rule_outcome_signal": row[7],
                        "core_outcome_signal": row[8],
                    }
                )
            return records

    def close(self) -> None:
        """Close all connections."""
        if self._writer_conn is not None:
            self._writer_conn.close()
            self._writer_conn = None
        self._is_closed = True
