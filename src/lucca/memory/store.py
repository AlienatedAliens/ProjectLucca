"""
Project Lucca — SQLite-backed Memory Store & Graph Engine
Spec 04 §1-§8, ADR-002, ADR-006
"""

import datetime
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

import sqlite_vec
import structlog

from lucca.core.exceptions import (
    MemoryCommitFailed,
    MemoryStoreReadOnly,
    ProvenanceRejected,
)
from lucca.core.schemas import (
    GROUNDING_ELIGIBLE,
    Admitted,
    Edge,
    MemoryHit,
    MemoryId,
    Provenance,
    RetrievalQuery,
    SignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.entities import resolve_entity
from lucca.memory.extraction import FUNCTIONAL_PREDICATES
from lucca.memory.gate import ProvenanceGate
from lucca.memory.retrieval import HybridRetriever
from lucca.memory.tokens import subtokens
from lucca.ports import EmbeddingPort

logger = structlog.get_logger(__name__)

DEFAULT_BACKUP_DIR: Final[Path] = Path(r"C:\ProjectLucca\data\backups")


class MemoryStore:
    """
    Core persistent memory storage implementing MemoryStorePort.
    Guarantees atomic single-transaction commits, bi-temporal supersession,
    cryptographic provenance gates, and hybrid dense/sparse retrieval.
    """

    def __init__(
        self,
        db: DatabaseManager,
        master_key: bytes,
        embedding_port: EmbeddingPort | None = None,
        backup_dir: Path | str = DEFAULT_BACKUP_DIR,
    ) -> None:
        self.db = db
        self.master_key = master_key
        self.embedding_port = embedding_port
        self.backup_dir = Path(backup_dir) if isinstance(backup_dir, str) else backup_dir

        self.gate = ProvenanceGate(master_key=master_key, db=db)
        self.retriever = HybridRetriever(db=db, embedder=embedding_port, master_key=master_key)

        self.read_only: bool = False
        self.vec_backfill: list[int] = []
        self._write_lock: threading.Lock = threading.Lock()
        self._fault_hook_before_commit: Callable[[], None] | None = None

    def commit(
        self,
        payload: SignedPayload | Admitted,
        now: float | None = None,
    ) -> MemoryId:
        """
        Commit a signed payload into persistent storage in a single transaction (Spec 04 §4).
        """
        if self.read_only:
            raise MemoryStoreReadOnly("MemoryStore is in read-only mode")

        current_time = now if now is not None else time.time()

        # Provenance verification gate
        if isinstance(payload, Admitted):
            signed_payload = payload.payload
        elif isinstance(payload, SignedPayload):
            admitted = self.gate.admit(payload, now=current_time)
            signed_payload = admitted.payload
        else:
            msg = f"Expected Admitted or SignedPayload, got {type(payload).__name__}"
            raise ProvenanceRejected(msg)

        # Compute embedding before transaction (Spec 04 §4)
        embedding: list[float] | None = None
        if self.embedding_port is not None:
            try:
                vecs = self.embedding_port.embed([signed_payload.content])
                if vecs and len(vecs[0]) == 384:
                    embedding = vecs[0]
            except Exception as exc:  # noqa: BLE001
                logger.warning("embedding_failed_enqueuing_backfill", error=str(exc))

        with self._write_lock:
            conn = self.db.get_writer()
            cursor = conn.cursor()
            conn.execute("BEGIN IMMEDIATE")
            try:
                # 1. Insert provenance envelope
                asr_model = signed_payload.asr.model if signed_payload.asr else None
                asr_avg_logprob = signed_payload.asr.avg_logprob if signed_payload.asr else None
                audio_sha256 = signed_payload.asr.audio_sha256 if signed_payload.asr else None
                tool_name = signed_payload.tool.tool if signed_payload.tool else None
                tool_call_id = signed_payload.tool.call_id if signed_payload.tool else None
                tool_exit_code = signed_payload.tool.exit_code if signed_payload.tool else None

                grounding_eligible = 1 if signed_payload.provenance in GROUNDING_ELIGIBLE else 0
                cursor.execute(
                    """
                    INSERT INTO provenance_envelopes(
                        entry_id, provenance, kind, signer_id, signature, content_sha256,
                        nonce, created_at, trace_id, session_id, asr_model, asr_avg_logprob,
                        audio_sha256, tool_name, tool_call_id, tool_exit_code, confidence,
                        payload_json, grounding_eligible
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signed_payload.entry_id,
                        signed_payload.provenance.value,
                        signed_payload.kind,
                        signed_payload.signer_id,
                        signed_payload.signature,
                        signed_payload.content_sha256,
                        signed_payload.nonce,
                        signed_payload.created_at,
                        signed_payload.trace_id,
                        signed_payload.session_id,
                        asr_model,
                        asr_avg_logprob,
                        audio_sha256,
                        tool_name,
                        tool_call_id,
                        tool_exit_code,
                        signed_payload.confidence,
                        signed_payload.model_dump_json(),
                        grounding_eligible,
                    ),
                )

                # 2. Insert memories (valid_from = structured.valid_from or created_at)
                valid_from = signed_payload.created_at
                importance = 0.5
                if signed_payload.structured is not None:
                    if "valid_from" in signed_payload.structured:
                        vf_val = signed_payload.structured["valid_from"]
                        if isinstance(vf_val, (int, float)):
                            valid_from = float(vf_val)
                    if "importance" in signed_payload.structured:
                        imp_val = signed_payload.structured["importance"]
                        if isinstance(imp_val, (int, float)):
                            importance = max(0.0, min(1.0, float(imp_val)))
                elif signed_payload.provenance == Provenance.COHERENCE_BREACH:
                    importance = 0.8

                aux_tokens = subtokens(signed_payload.content)
                cursor.execute(
                    """
                    INSERT INTO memories(
                        entry_id, content, tokens_aux, kind, created_at, valid_from,
                        valid_to, superseded_by, forgotten_at, importance, access_count
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, 0)
                    """,
                    (
                        signed_payload.entry_id,
                        signed_payload.content,
                        aux_tokens,
                        signed_payload.kind,
                        signed_payload.created_at,
                        valid_from,
                        importance,
                    ),
                )
                if cursor.lastrowid is None:
                    raise MemoryCommitFailed("Failed to insert memory: lastrowid is None")
                memory_id = int(cursor.lastrowid)

                # 3. Insert memory_sources
                for src_id in signed_payload.source_entry_ids:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO memory_sources(memory_id, source_entry_id)
                        VALUES (?, ?)
                        """,
                        (memory_id, src_id),
                    )

                # 4. Insert vec_memories
                if embedding is not None:
                    serialized_vec = sqlite_vec.serialize_float32(embedding)
                    cursor.execute(
                        "INSERT INTO vec_memories(memory_id, embedding) VALUES (?, ?)",
                        (memory_id, serialized_vec),
                    )
                else:
                    self.vec_backfill.append(memory_id)

                # 5. Knowledge Graph updates for kind='fact'
                if signed_payload.kind == "fact" and signed_payload.structured is not None:
                    s_surface = str(signed_payload.structured.get("s", "user"))
                    p_pred = str(signed_payload.structured.get("p", "note"))
                    o_surface = str(signed_payload.structured.get("o", ""))

                    s_id, _ = resolve_entity(conn, s_surface, now=signed_payload.created_at)
                    o_id, _ = resolve_entity(conn, o_surface, now=signed_payload.created_at)

                    # Direct evidence (USER_EXPLICIT / USER_DERIVED) supersedes INFERRED facts on the same predicate
                    if signed_payload.provenance in (Provenance.USER_EXPLICIT, Provenance.USER_DERIVED):
                        cursor.execute(
                            """
                            SELECT k.edge_id, k.memory_id
                            FROM kg_edges k
                            JOIN memories m ON k.memory_id = m.memory_id
                            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                            WHERE k.s = ? AND k.p = ? AND k.valid_to IS NULL
                              AND e.provenance = 'INFERRED'
                            """,
                            (s_id, p_pred),
                        )
                        for old_edge_id, old_mid in cursor.fetchall():
                            cursor.execute(
                                "UPDATE kg_edges SET valid_to = ? WHERE edge_id = ?",
                                (signed_payload.created_at, old_edge_id),
                            )
                            cursor.execute(
                                """
                                UPDATE memories SET valid_to = ?, superseded_by = ?
                                WHERE memory_id = ?
                                """,
                                (signed_payload.created_at, memory_id, old_mid),
                            )
                            cursor.execute(
                                """
                                INSERT INTO memory_audit(
                                    ts, kind, reason, provenance, trace_id, entry_id
                                )
                                VALUES (?, 'supersede', ?, ?, ?, ?)
                                """,
                                (
                                    current_time,
                                    f"Direct evidence ({signed_payload.provenance.value}) supersedes INFERRED fact on {p_pred}",
                                    signed_payload.provenance.value,
                                    signed_payload.trace_id,
                                    signed_payload.entry_id,
                                ),
                            )

                    # Functional predicate supersession
                    if p_pred in FUNCTIONAL_PREDICATES:
                        query = """
                            SELECT k.edge_id, k.memory_id
                            FROM kg_edges k
                            JOIN memories m ON k.memory_id = m.memory_id
                            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                            WHERE k.s = ? AND k.p = ? AND k.valid_to IS NULL AND k.o <> ?
                        """
                        if signed_payload.provenance == Provenance.INFERRED:
                            query += " AND e.provenance NOT IN ('USER_EXPLICIT', 'USER_DERIVED')"
                        cursor.execute(query, (s_id, p_pred, o_id))
                        old_edges = cursor.fetchall()
                        for old_edge_id, old_mid in old_edges:
                            cursor.execute(
                                "UPDATE kg_edges SET valid_to = ? WHERE edge_id = ?",
                                (signed_payload.created_at, old_edge_id),
                            )
                            cursor.execute(
                                """
                                UPDATE memories SET valid_to = ?, superseded_by = ?
                                WHERE memory_id = ?
                                """,
                                (signed_payload.created_at, memory_id, old_mid),
                            )
                            cursor.execute(
                                """
                                INSERT INTO memory_audit(
                                    ts, kind, reason, provenance, trace_id, entry_id
                                )
                                VALUES (?, 'supersede', ?, ?, ?, ?)
                                """,
                                (
                                    current_time,
                                    f"Functional predicate {p_pred} supersession",
                                    signed_payload.provenance.value,
                                    signed_payload.trace_id,
                                    signed_payload.entry_id,
                                ),
                            )

                    # Insert new edge
                    cursor.execute(
                        """
                        INSERT INTO kg_edges(
                            s, p, o, memory_id, valid_from, recorded_at, confidence
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            s_id,
                            p_pred,
                            o_id,
                            memory_id,
                            valid_from,
                            current_time,
                            signed_payload.confidence,
                        ),
                    )

                # 6. Insert gate_nonces
                cursor.execute(
                    "INSERT INTO gate_nonces(nonce, content_sha256, seen_at) VALUES (?, ?, ?)",
                    (signed_payload.nonce, signed_payload.content_sha256, current_time),
                )

                # 7. Insert memory_audit
                cursor.execute(
                    """
                    INSERT INTO memory_audit(
                        ts, kind, provenance, trace_id, entry_id, content_sha256
                    )
                    VALUES (?, 'commit', ?, ?, ?, ?)
                    """,
                    (
                        current_time,
                        signed_payload.provenance.value,
                        signed_payload.trace_id,
                        signed_payload.entry_id,
                        signed_payload.content_sha256,
                    ),
                )

                # Fault injection hook for crash testing (T-MEM-10)
                if self._fault_hook_before_commit is not None:
                    self._fault_hook_before_commit()

                conn.execute("COMMIT")
                return memory_id

            except Exception as exc:
                conn.execute("ROLLBACK")
                if isinstance(exc, (ProvenanceRejected, MemoryStoreReadOnly)):
                    raise
                raise MemoryCommitFailed(f"Memory commit transaction failed: {exc}") from exc

    def search(self, q: RetrievalQuery, now: float | None = None) -> list[MemoryHit]:
        """Hybrid retrieval query."""
        return self.retriever.search(q, now=now)

    def supersede(
        self,
        old: MemoryId,
        new: MemoryId,
        reason: str,
        now: float | None = None,
    ) -> None:
        """Mark old memory as superseded by new memory with evidence gating."""
        if self.read_only:
            raise MemoryStoreReadOnly("MemoryStore is in read-only mode")

        current_time = now if now is not None else time.time()
        with self._write_lock:
            conn = self.db.get_writer()
            conn.execute("BEGIN IMMEDIATE")
            try:
                # 1. Reason must be a grounding-eligible entry_id
                cur = conn.execute(
                    "SELECT grounding_eligible FROM provenance_envelopes WHERE entry_id = ?",
                    (reason,),
                )
                row = cur.fetchone()
                if not row or row[0] != 1:
                    raise ProvenanceRejected(
                        f"Revision reason '{reason}' must be an existing "
                        "grounding-eligible entry_id"
                    )

                # 2. Old memory must exist and not already be superseded
                cur_old = conn.execute(
                    "SELECT memory_id, valid_to FROM memories WHERE memory_id = ?",
                    (int(old),),
                )
                old_row = cur_old.fetchone()
                if not old_row:
                    raise KeyError(f"Memory #{old} not found")
                if old_row[1] is not None:
                    raise ValueError(f"Memory #{old} is already superseded")

                # 3. New memory must exist
                cur_new = conn.execute(
                    "SELECT memory_id FROM memories WHERE memory_id = ?",
                    (int(new),),
                )
                if not cur_new.fetchone():
                    raise KeyError(f"Memory #{new} not found")

                conn.execute(
                    "UPDATE memories SET valid_to = ?, superseded_by = ? WHERE memory_id = ?",
                    (current_time, int(new), int(old)),
                )
                conn.execute(
                    "UPDATE kg_edges SET valid_to = ? WHERE memory_id = ? AND valid_to IS NULL",
                    (current_time, int(old)),
                )
                conn.execute(
                    "INSERT INTO memory_audit(ts, kind, reason) VALUES (?, 'supersede', ?)",
                    (current_time, reason),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def forget(
        self,
        ids: list[MemoryId],
        *,
        user_confirmed: bool,
        now: float | None = None,
    ) -> None:
        """
        Soft-delete memories: sets forgotten_at, deletes vec/fts rows, and closes edges.
        Requires explicit user_confirmed=True.
        """
        if not user_confirmed:
            raise ValueError("Forgetting memories requires explicit user confirmation")

        if self.read_only:
            raise MemoryStoreReadOnly("MemoryStore is in read-only mode")

        current_time = now if now is not None else time.time()
        int_ids = [int(mid) for mid in ids]

        with self._write_lock:
            conn = self.db.get_writer()
            conn.execute("BEGIN IMMEDIATE")
            try:
                for mid in int_ids:
                    # 1. Fetch content for FTS delete
                    cur_old = conn.execute(
                        "SELECT content, tokens_aux FROM memories WHERE memory_id = ?", (mid,)
                    )
                    old_row = cur_old.fetchone()
                    if old_row:
                        old_content, old_tokens = old_row[0], old_row[1]
                        conn.execute(
                            """
                            INSERT INTO fts_memories(fts_memories, rowid, content, tokens_aux)
                            VALUES ('delete', ?, ?, ?)
                            """,
                            (mid, old_content, old_tokens),
                        )

                    # 2. Soft-delete memory row
                    conn.execute(
                        "UPDATE memories SET forgotten_at = ? WHERE memory_id = ?",
                        (current_time, mid),
                    )
                    # 3. Remove from vector index
                    conn.execute("DELETE FROM vec_memories WHERE memory_id = ?", (mid,))
                    # 4. Close KG edges
                    conn.execute(
                        "UPDATE kg_edges SET valid_to = ? WHERE memory_id = ? AND valid_to IS NULL",
                        (current_time, mid),
                    )
                    # 5. Audit
                    conn.execute(
                        "INSERT INTO memory_audit(ts, kind, reason) VALUES (?, 'forget', ?)",
                        (current_time, f"User confirmed forget for memory {mid}"),
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def hard_purge_all(self, user_confirmed: bool = False) -> dict[str, int]:
        """
        Permanently eradicates all records across all memory and reasoning stores:
        memories, knowledge graph, vector indices, FTS tables, decisions, and induced rules.
        Executes in a single atomic SQLite transaction with foreign-key-safe ordering.
        Requires explicit user_confirmed=True.
        """
        if not user_confirmed:
            raise ValueError("Hard purge requires explicit user confirmation")

        if self.read_only:
            raise MemoryStoreReadOnly("MemoryStore is in read-only mode")

        deleted_counts: dict[str, int] = {}
        with self._write_lock:
            conn = self.db.get_writer()
            conn.execute("BEGIN IMMEDIATE")
            try:
                # 0. Temporarily drop mem_ad trigger to prevent FTS5 shadow table mismatch
                conn.execute("DROP TRIGGER IF EXISTS mem_ad")

                def _del(tbl: str, is_virtual_fts: bool = False) -> int:
                    try:
                        cur = conn.execute(f'SELECT count(*) FROM "{tbl}"')
                        cnt = int(cur.fetchone()[0])
                        if is_virtual_fts:
                            conn.execute(f"INSERT INTO {tbl}({tbl}) VALUES('delete-all')")
                        else:
                            conn.execute(f'DELETE FROM "{tbl}"')
                        deleted_counts[tbl] = cnt
                        return cnt
                    except sqlite3.OperationalError:
                        deleted_counts[tbl] = 0
                        return 0

                # 1. Break self-referencing foreign keys in memories
                conn.execute("UPDATE memories SET superseded_by = NULL")

                # 2. Knowledge Graph (edges before entities to satisfy foreign keys)
                _del("kg_edges")
                _del("kg_aliases")
                _del("kg_entities")

                # 3. Decisions and Heuristic Router telemetry
                _del("decision_labels")
                _del("fts_decisions")
                _del("vec_decisions")
                _del("decisions")

                # 4. Rules and regression cases
                _del("regression_cases")
                _del("rule_states")

                # 5. Reviews, sources, execution triples
                _del("review_queue")
                _del("memory_sources")
                _del("tool_contents")
                _del("contrastive_shadow_logs")
                _del("execution_triples")

                # 6. Memories & Vector store
                _del("vec_memories")
                _del("memories")
                _del("fts_memories", is_virtual_fts=True)

                # 7. Re-create mem_ad trigger
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
                      INSERT INTO fts_memories(fts_memories, rowid, content, tokens_aux) VALUES ('delete', old.memory_id, old.content, old.tokens_aux);
                    END;
                """)

                # 8. Provenance envelopes, gate nonces, and audit logs
                _del("provenance_envelopes")
                _del("gate_nonces")
                _del("memory_audit")

                conn.execute("COMMIT")
                logger.info("memory_hard_purge_completed", deleted_counts=deleted_counts)
                return deleted_counts
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def graph_neighbors(self, entity: str, hops: int = 1) -> list[Edge]:
        """Find valid knowledge graph neighbors for entity (Spec 04 §6)."""
        edges: list[Edge] = []
        with self.db.read_cursor() as cur:
            # Resolve entity canonical name or alias
            s_can = entity.lower().strip()
            cur.execute(
                """
                SELECT e1.canonical, ed.p, e2.canonical
                FROM kg_edges ed
                JOIN kg_entities e1 ON ed.s = e1.entity_id
                JOIN kg_entities e2 ON ed.o = e2.entity_id
                WHERE (e1.canonical = ? OR e2.canonical = ?) AND ed.valid_to IS NULL
                """,
                (s_can, s_can),
            )
            for s, p, o in cur.fetchall():
                edges.append(Edge(source=str(s), relation=str(p), target=str(o)))
        return edges

    def backup(self, destination: Path | str | None = None) -> Path:
        """
        Execute VACUUM INTO backup snapshot and prune old backups per Spec 04 §8.
        Keeps 14 daily backups and 8 weekly (Sunday) backups.
        """
        now = datetime.datetime.now()
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        if destination is None:
            filename = f"memory-{now.strftime('%Y%m%d-%H%M')}.sqlite"
            dest_path = self.backup_dir / filename
        else:
            dest_path = Path(destination)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.exists():
            dest_path.unlink()

        conn = self.db.get_writer()
        # Escape path for SQLite string literal
        escaped_path = str(dest_path.resolve()).replace("'", "''")
        conn.execute(f"VACUUM INTO '{escaped_path}'")

        # Prune retention (14 daily, 8 weekly)
        self._prune_backups()
        return dest_path

    def _prune_backups(self) -> None:
        """Prune old backup files: retain 14 daily and 8 weekly (Sunday)."""
        backups = sorted(
            self.backup_dir.glob("memory-*.sqlite"),
            key=lambda p: p.name,
            reverse=True,
        )
        daily_kept = 0
        weekly_kept = 0

        for b in backups:
            try:
                date_part = b.name.replace("memory-", "").split("-")[0]
                dt = datetime.datetime.strptime(date_part, "%Y%m%d")
            except ValueError:
                continue

            is_sunday = dt.weekday() == 6
            keep = False
            if daily_kept < 14:
                daily_kept += 1
                keep = True
            elif is_sunday and weekly_kept < 8:
                weekly_kept += 1
                keep = True

            if not keep:
                try:
                    b.unlink()
                except OSError as e:
                    logger.warning("backup_prune_failed", file=b.name, error=str(e))

    def check_integrity(self) -> bool:
        """
        Run PRAGMA integrity_check (Spec 04 §8).
        If corrupted, sets read_only=True and returns False.
        """
        with self.db.read_cursor() as cur:
            cur.execute("PRAGMA integrity_check;")
            rows = cur.fetchall()
            if rows and rows[0][0] == "ok":
                return True

        self.read_only = True
        logger.error("sqlite_integrity_check_failed", details=[r[0] for r in rows])
        return False
