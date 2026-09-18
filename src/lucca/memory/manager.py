"""
Project Lucca — Human-Readable, Auditable Memory & Learning Manager
Provides administrative CRUD and search capabilities over SQLite-vec memory tables.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from lucca.memory.db import DatabaseManager


class MemoryManager:
    """Manages viewing, searching, adding, editing, and pruning memories."""

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self.db = db or DatabaseManager()

    def get_connection(self) -> sqlite3.Connection:
        return self.db.get_connection()

    def list_memories(
        self, search: str = "", include_forgotten: bool = False
    ) -> list[dict[str, Any]]:
        """List memories with optional text filter."""
        conn = self.get_connection()
        try:
            query = """
                SELECT
                    m.memory_id,
                    m.entry_id,
                    m.content,
                    m.kind,
                    m.created_at,
                    m.valid_from,
                    m.importance,
                    m.forgotten_at,
                    p.provenance,
                    p.confidence
                FROM memories m
                LEFT JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE (m.forgotten_at IS NULL OR ? = 1)
            """
            params: list[Any] = [1 if include_forgotten else 0]

            if search.strip():
                query += " AND (m.content LIKE ? OR m.kind LIKE ? OR p.provenance LIKE ?)"
                term = f"%{search.strip()}%"
                params.extend([term, term, term])

            query += " ORDER BY m.created_at DESC"

            cur = conn.execute(query, params)
            rows = cur.fetchall()

            result = []
            for r in rows:
                result.append(
                    {
                        "memory_id": r["memory_id"],
                        "entry_id": r["entry_id"],
                        "content": r["content"],
                        "kind": r["kind"],
                        "created_at": r["created_at"],
                        "valid_from": r["valid_from"],
                        "importance": float(r["importance"]),
                        "forgotten_at": r["forgotten_at"],
                        "provenance": r["provenance"] or "USER_EXPLICIT",
                        "confidence": float(r["confidence"])
                        if r["confidence"] is not None
                        else 1.0,
                    }
                )
            return result
        finally:
            conn.close()

    def add_memory(
        self,
        content: str,
        kind: str = "fact",
        importance: float = 0.8,
        provenance: str = "USER_EXPLICIT",
    ) -> int:
        """Adds a human-audited or manually inserted memory record."""
        now = time.time()
        entry_id = f"aud-{uuid.uuid4().hex[:12]}"
        nonce = uuid.uuid4().hex
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        conn = self.db.get_writer()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # 1. Insert provenance envelope
            conn.execute(
                """
                INSERT INTO provenance_envelopes (
                    entry_id, provenance, kind, signer_id, signature,
                    content_sha256, nonce, created_at, trace_id, session_id,
                    confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    provenance,
                    kind,
                    "ui-admin",
                    "manual",
                    content_hash,
                    nonce,
                    now,
                    "ui-admin-trace",
                    "ui-admin-session",
                    1.0,
                    json.dumps({"content": content, "source": "ui-manual"}),
                ),
            )

            # 2. Insert memories row
            cur = conn.execute(
                """
                INSERT INTO memories (
                    entry_id, content, tokens_aux, kind, created_at,
                    valid_from, importance, access_count
                ) VALUES (?, ?, '', ?, ?, ?, ?, 0)
                """,
                (entry_id, content, kind, now, now, importance),
            )
            mem_id = cur.lastrowid or 0

            # 3. Insert into fts_memories if exists
            try:
                conn.execute(
                    "INSERT INTO fts_memories(rowid, content) VALUES (?, ?)",
                    (mem_id, content),
                )
            except Exception:  # noqa: BLE001, S110
                pass

            conn.execute("COMMIT")
            return mem_id
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def update_memory(
        self, memory_id: int, new_content: str, importance: float | None = None
    ) -> bool:
        """Updates an existing memory's content or importance."""
        conn = self.db.get_writer()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if importance is not None:
                conn.execute(
                    "UPDATE memories SET content = ?, importance = ? WHERE memory_id = ?",
                    (new_content, importance, memory_id),
                )
            else:
                conn.execute(
                    "UPDATE memories SET content = ? WHERE memory_id = ?",
                    (new_content, memory_id),
                )

            # Update FTS
            try:
                conn.execute("DELETE FROM fts_memories WHERE rowid = ?", (memory_id,))
                conn.execute(
                    "INSERT INTO fts_memories(rowid, content) VALUES (?, ?)",
                    (memory_id, new_content),
                )
            except Exception:  # noqa: BLE001, S110
                pass

            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def delete_memory(self, memory_id: int, hard: bool = True) -> bool:
        """Deletes or marks a memory as forgotten."""
        conn = self.db.get_writer()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if hard:
                cur = conn.execute(
                    "SELECT entry_id FROM memories WHERE memory_id = ?", (memory_id,)
                )
                row = cur.fetchone()
                entry_id = row[0] if row else None

                conn.execute("DELETE FROM memory_sources WHERE memory_id = ?", (memory_id,))
                try:
                    conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (memory_id,))
                except Exception:  # noqa: BLE001, S110
                    pass
                try:
                    conn.execute("DELETE FROM fts_memories WHERE rowid = ?", (memory_id,))
                except Exception:  # noqa: BLE001, S110
                    pass
                conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
                if entry_id:
                    conn.execute("DELETE FROM provenance_envelopes WHERE entry_id = ?", (entry_id,))
            else:
                conn.execute(
                    "UPDATE memories SET forgotten_at = ? WHERE memory_id = ?",
                    (time.time(), memory_id),
                )

            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_stats(self) -> dict[str, Any]:
        """Returns statistics on memory database."""
        conn = self.get_connection()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM memories WHERE forgotten_at IS NULL")
            active_count = cur.fetchone()[0]

            cur = conn.execute("SELECT COUNT(*) FROM memories WHERE forgotten_at IS NOT NULL")
            forgotten_count = cur.fetchone()[0]

            db_size_bytes = 0
            if Path(self.db.db_path).exists():
                db_size_bytes = Path(self.db.db_path).stat().st_size

            return {
                "active_memories": active_count,
                "forgotten_memories": forgotten_count,
                "total_memories": active_count + forgotten_count,
                "db_size_kb": round(db_size_bytes / 1024, 1),
                "db_path": str(self.db.db_path),
            }
        finally:
            conn.close()
