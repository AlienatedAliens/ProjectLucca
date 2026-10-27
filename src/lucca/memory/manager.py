"""
Project Lucca — Human-Readable, Auditable Memory & Learning Manager
Provides administrative CRUD and search capabilities over SQLite-vec memory tables.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Literal, cast

from lucca.core.config import get_config
from lucca.core.schemas import Provenance, UnsignedPayload
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import ProvenanceGate, resolve_grounding_eligible
from lucca.memory.signers import BaseProvenanceSigner, UserSpeechSigner

logger = logging.getLogger(__name__)


_DEFAULT_KEY = b"__DEFAULT_UNSET_KEY__"


class MemoryManager:
    """Manages viewing, searching, adding, editing, and pruning memories."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        master_key: bytes | None = _DEFAULT_KEY,
    ) -> None:
        self.db = db or DatabaseManager()
        if master_key is _DEFAULT_KEY:
            cfg = get_config()
            master_key = cfg.master_key.encode("utf-8") if cfg.master_key else None
        if master_key is not None and len(master_key) < 32:
            raise ValueError(f"Master key must be at least 32 bytes, got {len(master_key)}")
        self.master_key = master_key
        self.gate: ProvenanceGate | None = (
            ProvenanceGate(master_key=master_key) if master_key else None
        )

    def get_connection(self) -> sqlite3.Connection:
        return self.db.get_connection()

    def list_memories(
        self,
        search: str = "",
        include_forgotten: bool = False,
        include_superseded: bool = False,
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
                    m.valid_to,
                    m.superseded_by,
                    m.importance,
                    m.forgotten_at,
                    p.provenance,
                    p.confidence
                FROM memories m
                LEFT JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE (m.forgotten_at IS NULL OR ? = 1)
                  AND (m.valid_to IS NULL OR ? = 1)
            """
            params: list[Any] = [1 if include_forgotten else 0, 1 if include_superseded else 0]

            if search.strip():
                query += " AND (m.content LIKE ? OR m.kind LIKE ? OR p.provenance LIKE ?)"
                term = f"%{search.strip()}%"
                params.extend([term, term, term])

            query += " ORDER BY m.created_at DESC"

            cur = conn.execute(query, params)
            rows = cur.fetchall()

            # Tokenized fallback (F-WO8-22): a full-phrase LIKE fails for natural
            # question phrasing ("Did you read any files last session?" matches
            # nothing), which made the memory_search tool report empty results
            # even when relevant memories existed. Fall back to OR-matching the
            # individual significant tokens, ranked by match count.
            if not rows and search.strip():
                tokens = [
                    t for t in re.split(r"[^a-zA-Z0-9_.\-]+", search.strip().lower()) if len(t) >= 3
                ][:8]
                if tokens:
                    like_clauses = " OR ".join(["m.content LIKE ? OR m.kind LIKE ?"] * len(tokens))
                    token_params: list[Any] = []
                    for t in tokens:
                        token_params.extend([f"%{t}%", f"%{t}%"])
                    fallback_sql = f"""
                        SELECT m.memory_id, m.entry_id, m.content, m.kind, m.created_at,
                               m.valid_from, m.valid_to, m.superseded_by, m.importance,
                               m.forgotten_at, p.provenance, p.confidence,
                               ({" + ".join(["(m.content LIKE ?)"] * len(tokens))}) AS match_count
                        FROM memories m
                        LEFT JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                        WHERE (m.forgotten_at IS NULL OR ? = 1)
                          AND (m.valid_to IS NULL OR ? = 1)
                          AND ({like_clauses})
                        ORDER BY match_count DESC, m.created_at DESC
                    """  # noqa: S608
                    fb_params: list[Any] = [f"%{t}%" for t in tokens]
                    fb_params.extend(
                        [1 if include_forgotten else 0, 1 if include_superseded else 0]
                    )
                    fb_params.extend(token_params)
                    cur = conn.execute(fallback_sql, fb_params)
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
                        "valid_to": r["valid_to"],
                        "superseded_by": r["superseded_by"],
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
        kind: Literal["transcript", "fact", "tool_fact", "rule_assertion"] = "fact",
        importance: float = 0.8,
        provenance: Provenance | str = Provenance.USER_EXPLICIT,
        signer: BaseProvenanceSigner | None = None,
    ) -> int:
        """Adds a human-audited or manually inserted memory record through the provenance gate."""
        if self.master_key is None or self.gate is None:
            raise ValueError("master_key is required for MemoryManager to sign and admit memories")

        prov_enum = Provenance(provenance) if isinstance(provenance, str) else provenance
        active_signer = signer or UserSpeechSigner(master_key=self.master_key, signer_id="ui-admin")
        now = time.time()
        unsigned = UnsignedPayload(
            provenance=prov_enum,
            kind=kind,
            content=content,
            trace_id="ui-admin-trace",
            session_id="ui-admin-session",
            created_at=now,
            nonce=uuid.uuid4().hex,
            confidence=1.0,
        )
        signed = active_signer.sign(unsigned)
        admitted = self.gate.admit(signed, now=now)
        admitted_payload = admitted.payload

        conn = self.db.get_writer()
        grounding_el = resolve_grounding_eligible(
            admitted_payload.provenance, content, self.db
        )
        try:
            conn.execute("BEGIN IMMEDIATE")
            # 1. Insert provenance envelope
            conn.execute(
                """
                INSERT INTO provenance_envelopes (
                    entry_id, provenance, kind, signer_id, signature,
                    content_sha256, nonce, created_at, trace_id, session_id,
                    confidence, payload_json, grounding_eligible
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    admitted_payload.entry_id,
                    admitted_payload.provenance.value,
                    admitted_payload.kind,
                    admitted_payload.signer_id,
                    admitted_payload.signature,
                    admitted_payload.content_sha256,
                    admitted_payload.nonce,
                    admitted_payload.created_at,
                    admitted_payload.trace_id,
                    admitted_payload.session_id,
                    admitted_payload.confidence,
                    json.dumps(admitted_payload.model_dump()),
                    grounding_el,
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
                (admitted_payload.entry_id, content, kind, now, now, importance),
            )
            mem_id = cur.lastrowid or 0

            # 3. Insert into fts_memories if exists
            try:
                conn.execute(
                    "INSERT INTO fts_memories(rowid, content) VALUES (?, ?)",
                    (mem_id, content),
                )
            except Exception as exc:  # noqa: BLE001, S110
                logger.debug("fts_insert_failed: %s", exc)

            conn.execute("COMMIT")
            return mem_id
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def update_memory(
        self, memory_id: int, new_content: str, importance: float | None = None
    ) -> bool:
        """Updates an existing memory via bi-temporal supersession (F-MEM-002)."""
        if self.master_key is None or self.gate is None:
            raise ValueError("master_key is required for MemoryManager to sign and admit memories")

        # 1. Fetch old memory to preserve kind and original importance if not specified
        with self.db.read_cursor() as cur:
            cur.execute(
                "SELECT memory_id, kind, importance FROM memories WHERE memory_id = ?",
                (memory_id,),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Memory #{memory_id} not found")
            kind_str = str(row["kind"])
            valid_kind = (
                kind_str
                if kind_str in ("transcript", "fact", "tool_fact", "rule_assertion")
                else "fact"
            )
            kind = cast(Literal["transcript", "fact", "tool_fact", "rule_assertion"], valid_kind)
            orig_importance = float(row["importance"])

        target_importance = importance if importance is not None else orig_importance

        # 2. Construct and sign new payload via ProvenanceGate
        now = time.time()
        signer = UserSpeechSigner(master_key=self.master_key, signer_id="ui-admin")
        unsigned = UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind=kind,
            content=new_content,
            trace_id=f"ui-admin-edit-{uuid.uuid4().hex[:8]}",
            session_id="ui-admin-session",
            created_at=now,
            nonce=uuid.uuid4().hex,
            confidence=1.0,
        )
        signed = signer.sign(unsigned)
        admitted = self.gate.admit(signed, now=now)
        admitted_payload = admitted.payload

        conn = self.db.get_writer()
        grounding_el = resolve_grounding_eligible(
            admitted_payload.provenance, new_content, self.db
        )
        try:
            conn.execute("BEGIN IMMEDIATE")

            # 3. Insert new provenance envelope
            conn.execute(
                """
                INSERT INTO provenance_envelopes (
                    entry_id, provenance, kind, signer_id, signature,
                    content_sha256, nonce, created_at, trace_id, session_id,
                    confidence, payload_json, grounding_eligible
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    admitted_payload.entry_id,
                    admitted_payload.provenance.value,
                    admitted_payload.kind,
                    admitted_payload.signer_id,
                    admitted_payload.signature,
                    admitted_payload.content_sha256,
                    admitted_payload.nonce,
                    admitted_payload.created_at,
                    admitted_payload.trace_id,
                    admitted_payload.session_id,
                    admitted_payload.confidence,
                    json.dumps(admitted_payload.model_dump()),
                    grounding_el,
                ),
            )

            # 4. Insert new memory row
            cur = conn.execute(
                """
                INSERT INTO memories (
                    entry_id, content, tokens_aux, kind, created_at,
                    valid_from, importance, access_count
                ) VALUES (?, ?, '', ?, ?, ?, ?, 0)
                """,
                (admitted_payload.entry_id, new_content, kind, now, now, target_importance),
            )
            new_memory_id = int(cur.lastrowid or 0)

            # 5. Insert into fts_memories if exists
            try:
                conn.execute(
                    "INSERT INTO fts_memories(rowid, content) VALUES (?, ?)",
                    (new_memory_id, new_content),
                )
            except Exception as exc:  # noqa: BLE001, S110
                logger.debug("fts_update_failed: %s", exc)

            # 6. Mark old memory as superseded
            conn.execute(
                "UPDATE memories SET valid_to = ?, superseded_by = ? WHERE memory_id = ?",
                (now, new_memory_id, memory_id),
            )

            # 7. Close old KG edges
            conn.execute(
                "UPDATE kg_edges SET valid_to = ? WHERE memory_id = ? AND valid_to IS NULL",
                (now, memory_id),
            )

            # 8. Insert audit row
            conn.execute(
                """
                INSERT INTO memory_audit (
                    ts, kind, reason, provenance, trace_id, entry_id, content_sha256
                ) VALUES (?, 'supersede', ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    f"ui-edit superseding memory {memory_id} with {new_memory_id}",
                    admitted_payload.provenance.value,
                    admitted_payload.trace_id,
                    admitted_payload.entry_id,
                    admitted_payload.content_sha256,
                ),
            )

            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def delete_memory(self, memory_id: int, hard: bool = False) -> bool:
        """Marks memory forgotten and audits while preserving immutable envelope (F-MEM-003)."""
        now = time.time()
        conn = self.db.get_writer()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("SELECT entry_id FROM memories WHERE memory_id = ?", (memory_id,))
            row = cur.fetchone()
            entry_id = row[0] if row else None

            # Always soft-delete: set forgotten_at (Spec 04 §8 / TM-11)
            conn.execute(
                "UPDATE memories SET forgotten_at = ? WHERE memory_id = ?",
                (now, memory_id),
            )

            # Clean up vector search index and close active KG edges
            try:
                conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (memory_id,))
            except Exception as exc:  # noqa: BLE001, S110
                logger.debug("vec_delete_failed: %s", exc)
            conn.execute(
                "UPDATE kg_edges SET valid_to = ? WHERE memory_id = ? AND valid_to IS NULL",
                (now, memory_id),
            )

            # Record audit row with immutable provenance envelope preserved
            conn.execute(
                "INSERT INTO memory_audit (ts, kind, reason, entry_id) VALUES (?, 'forget', ?, ?)",
                (now, f"User confirmed forget for memory {memory_id}", entry_id),
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

    def list_review_queue(self, status: str = "PENDING") -> list[dict[str, object]]:
        """Lists items from review_queue with optional status filter."""
        conn = self.get_connection()
        try:
            cur = conn.execute(
                """
                SELECT r.review_id, r.belief_id, m.content as old_content,
                       r.proposed_content, r.proposed_confidence, r.reason_entry_id,
                       r.trigger_reason, r.created_at, r.status
                FROM review_queue r
                LEFT JOIN memories m ON r.belief_id = m.memory_id
                WHERE (? = 'ALL' OR r.status = ?)
                ORDER BY r.created_at ASC
                """,
                (status, status),
            )
            rows = cur.fetchall()
            return [
                {
                    "review_id": str(r[0]),
                    "belief_id": int(r[1]) if r[1] is not None else None,
                    "old_content": str(r[2]) if r[2] is not None else "",
                    "proposed_content": str(r[3]),
                    "proposed_confidence": float(r[4]),
                    "reason_entry_id": str(r[5]),
                    "trigger_reason": str(r[6]),
                    "created_at": float(r[7]),
                    "status": str(r[8]),
                }
                for r in rows
            ]
        finally:
            conn.close()

    def mark_topic_review_required(self, topic: str) -> None:
        """Marks a topic as review-required."""
        clean = topic.strip().lower()
        conn = self.db.get_writer()
        conn.execute(
            "INSERT OR IGNORE INTO review_required_topics (topic, created_at) VALUES (?, ?)",
            (clean, time.time()),
        )

    def list_review_required_topics(self) -> list[str]:
        """Lists all review-required topics."""
        conn = self.get_connection()
        try:
            cur = conn.execute("SELECT topic FROM review_required_topics ORDER BY topic ASC")
            return [str(row[0]) for row in cur.fetchall()]
        finally:
            conn.close()

    def unmark_topic_review_required(self, topic: str) -> None:
        """Removes a topic from the review-required list."""
        clean = topic.strip().lower()
        conn = self.db.get_writer()
        conn.execute(
            "DELETE FROM review_required_topics WHERE lower(topic) = ?",
            (clean,),
        )
