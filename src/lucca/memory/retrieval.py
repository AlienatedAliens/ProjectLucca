"""
Project Lucca — Hybrid Memory Retrieval (sqlite-vec KNN + FTS5 BM25 + RRF)
Spec 04 §6, Spec 10
"""

import base64
import hashlib
import hmac
import json
import sqlite3
import time
from typing import Final

import sqlite_vec
import structlog

from lucca.core.schemas import (
    DecisionRecord,
    MemoryHit,
    Provenance,
    RetrievalQuery,
    RouteDecision,
    RouteFeatures,
    ToolCall,
    standard_for_confidence,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import canonicalize_unsigned_payload, derive_provenance_key
from lucca.memory.tokens import build_fts_query, subtokens
from lucca.ports import EmbeddingPort

logger = structlog.get_logger(__name__)

RRF_K_CONST: Final[int] = 60
MAX_CANDIDATES: Final[int] = 30


def calculate_age_str(created_at: float, now: float) -> str:
    """Format human-readable age string (e.g. 5m ago, 2h ago, 3d ago)."""
    delta_s = max(0.0, now - created_at)
    if delta_s < 60:
        return f"{int(delta_s)}s ago"
    if delta_s < 3600:
        return f"{int(delta_s // 60)}m ago"
    if delta_s < 86400:
        return f"{int(delta_s // 3600)}h ago"
    return f"{int(delta_s // 86400)}d ago"


def _provenance_tier(prov: object) -> int:
    val = prov.value.upper() if hasattr(prov, "value") else str(prov).upper()
    if "USER_EXPLICIT" in val:
        return 0
    if "USER_DERIVED" in val:
        return 1
    if "INFERRED" in val:
        return 2
    if "LISP" in val or "ASSERTION" in val:
        return 3
    if "VERIFIED" in val:
        return 4
    return 5


def format_memory_context(
    hits: list[MemoryHit],
    max_tokens: int = 2048,
    now: float | None = None,
    max_content_chars: int = 160,
    max_items: int = 8,
) -> str:
    """
    Render memory hits into prompt context block per Spec 04 §6 / Spec 10 / D-MEM-03:
    - [{kind}/{provenance} {age}] {content} truncated to max_content_chars (default 160)
    - graph hits as: - {content}
    - sorted by multi-factor hierarchy: (provenance tier, -score, -created_at)
    - Enforces <= max_tokens (approx 4 chars/token).

    Multi-session grouping (D-MEM-04):
    When hits span multiple distinct sessions (different source_turn_id prefixes or
    created_at buckets > 4h apart), hits are grouped by session and emitted with
    [Session N — {age}] headers. This enables cross-session synthesis by the LLM
    rather than presenting a flat ranked list that obscures temporal structure.
    """
    current_time = now if now is not None else time.time()
    sorted_hits = sorted(
        hits,
        key=lambda h: (
            _provenance_tier(h.provenance),
            1 if h.valid_to is not None else 0,
            -h.score,
            -h.created_at,
        ),
    )

    char_budget = max_tokens * 4

    def _clean_content(hit: MemoryHit) -> str:
        raw_text = hit.content[:max_content_chars] if max_content_chars > 0 else hit.content
        content_clean = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        while "\n[" in content_clean:
            content_clean = content_clean.replace("\n[", "\n(")
        if content_clean.startswith("["):
            content_clean = "(" + content_clean[1:]
        return content_clean

    def _format_hit(hit: MemoryHit, content_clean: str) -> str:
        if hit.kind == "graph":
            return f"- {content_clean}"
        age = calculate_age_str(hit.created_at, current_time)
        prov_val = (
            hit.provenance.value if hasattr(hit.provenance, "value") else str(hit.provenance)
        )
        if prov_val == "INFERRED":
            conf_val = getattr(hit, "confidence", 1.0)
            std_label = standard_for_confidence(conf_val).value
            prefix = (
                f"- [{hit.kind}/INFERRED inferred, confidence {conf_val:.2f} "
                f"— {std_label} {age}]"
            )
            return f"{prefix} {content_clean}"
        conf_str = (
            f" conf={hit.confidence:.2f}" if getattr(hit, "confidence", 1.0) < 0.85 else ""
        )
        return f"- [{hit.kind}/{prov_val}{conf_str} {age}] {content_clean}"

    # --- Multi-session grouping (D-MEM-04) ---
    # Group hits by session prefix derived from source_turn_id (e.g. "sess_1:turn_3" ->
    # "sess_1"), or by created_at 4-hour time bucket. Sessions sorted oldest-first so
    # the LLM sees a chronological narrative rather than a flat score-ranked list.
    SESSION_GAP_S = 4 * 3600  # 4 hours gap = distinct session

    def _session_key(hit: MemoryHit) -> str:
        tid = hit.source_turn_id or ""
        for sep in (":", "_turn", "-turn"):
            if sep in tid:
                return tid.split(sep)[0]
        if tid.startswith("sess"):
            return tid
        return str(int(hit.created_at // SESSION_GAP_S))

    session_keys_ordered: list[str] = []
    session_groups: dict[str, list[MemoryHit]] = {}
    for hit in sorted_hits[:max_items]:
        sk = _session_key(hit)
        if sk not in session_groups:
            session_keys_ordered.append(sk)
            session_groups[sk] = []
        session_groups[sk].append(hit)

    multi_session = len(session_groups) > 1

    lines: list[str] = []
    current_len = 0

    if multi_session:
        # Sort sessions oldest-first by min created_at of their hits
        session_keys_ordered.sort(
            key=lambda sk: min(h.created_at for h in session_groups[sk])
        )
        for s_num, sk in enumerate(session_keys_ordered, start=1):
            group_hits = sorted(session_groups[sk], key=lambda h: h.created_at)
            oldest_ts = group_hits[0].created_at
            sess_age = calculate_age_str(oldest_ts, current_time)
            header = f"[Session {s_num} — {sess_age}]"
            header_len = len(header) + 1
            if current_len + header_len > char_budget:
                break
            lines.append(header)
            current_len += header_len
            for hit in group_hits:
                content_clean = _clean_content(hit)
                line = _format_hit(hit, content_clean)
                line_len = len(line) + 1
                if current_len + line_len > char_budget:
                    break
                lines.append(line)
                current_len += line_len
    else:
        # Single-session: original flat rendering
        for hit in sorted_hits[:max_items]:
            content_clean = _clean_content(hit)
            line = _format_hit(hit, content_clean)
            line_len = len(line) + 1
            if current_len + line_len > char_budget:
                break
            lines.append(line)
            current_len += line_len

    return "\n".join(lines)


class HybridRetriever:
    """
    Executes hybrid retrieval combining dense cosine KNN (sqlite-vec)
    and sparse BM25 (FTS5) using Reciprocal Rank Fusion (k=60), followed
    by bi-temporal filtering and 1-hop KG expansion.
    """

    def __init__(
        self,
        db: DatabaseManager,
        embedder: EmbeddingPort | None = None,
        master_key: bytes | None = None,
        raise_on_tamper: bool = False,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.master_key = master_key  # None disables HMAC verification (dev/test only)
        self.raise_on_tamper = raise_on_tamper
        self.quarantined_memory_ids: list[int] = []
        self.user_integrity_warnings: list[str] = []
        self._load_persisted_quarantine_ids()

    def _load_persisted_quarantine_ids(self) -> None:
        """Loads all historically quarantined memory IDs from the database."""
        try:
            with self.db.read_cursor() as cur:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_quarantine'"
                )
                if cur.fetchone():
                    cur.execute("SELECT memory_id FROM memory_quarantine")
                    self.quarantined_memory_ids = [int(row[0]) for row in cur.fetchall()]
        except Exception as exc:
            logger.debug("load_persisted_quarantine_ids_failed", error=str(exc))

    def get_integrity_status_report(self) -> str | None:
        """Returns human-readable notice if any memories are currently quarantined."""
        self._load_persisted_quarantine_ids()
        count = len(self.quarantined_memory_ids)
        if count == 0:
            return None
        return f"Security notice: {count} {'memory' if count == 1 else 'memories'} failed cryptographic integrity checks and were quarantined."

    def _persist_quarantine(self, memory_id: int, entry_id: str | None, stage: str, reason: str) -> None:
        try:
            with self.db.get_writer() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS memory_quarantine ("
                    "memory_id INTEGER PRIMARY KEY, "
                    "entry_id TEXT, "
                    "reason TEXT NOT NULL, "
                    "stage TEXT NOT NULL, "
                    "quarantined_at REAL NOT NULL"
                    ")"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO memory_quarantine (memory_id, entry_id, reason, stage, quarantined_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (memory_id, entry_id, reason, stage, time.time()),
                )
                conn.commit()
        except Exception as q_err:
            logger.warning("persist_memory_quarantine_failed", memory_id=memory_id, error=str(q_err))

    def get_persisted_quarantine_records(self) -> list[dict[str, object]]:
        """Returns all memory records quarantined across sessions."""
        try:
            with self.db.read_cursor() as cur:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_quarantine'"
                )
                if not cur.fetchone():
                    return []
                cur.execute("SELECT memory_id, entry_id, reason, stage, quarantined_at FROM memory_quarantine ORDER BY quarantined_at DESC")
                return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            logger.debug("get_persisted_quarantine_records_failed", error=str(exc))
            return []

    def search(
        self,
        q: RetrievalQuery,
        now: float | None = None,
        mode: str = "hybrid",
    ) -> list[MemoryHit]:
        current_time = now if now is not None else time.time()

        # 1. Dense search (KNN via sqlite-vec)
        dense_ranks: dict[int, int] = {}
        query_vec = None
        if mode in ("hybrid", "dense"):
            query_vec = q.query_vector
            if query_vec is None and self.embedder is not None:
                try:
                    vecs = self.embedder.embed([q.query_text])
                    if vecs and len(vecs[0]) == 384:
                        query_vec = vecs[0]
                except (RuntimeError, ValueError, OSError) as e:
                    logger.warning("dense_embedding_failed", error=str(e))

        # 1-5. Execute read queries using a single read cursor
        with self.db.read_cursor() as cur:
            if query_vec is not None and mode in ("hybrid", "dense"):
                try:
                    serialized = sqlite_vec.serialize_float32(query_vec)
                    cur.execute(
                        "SELECT memory_id, distance FROM vec_memories "
                        "WHERE embedding MATCH ? "
                        "ORDER BY distance "
                        "LIMIT ?",
                        (serialized, MAX_CANDIDATES),
                    )
                    for rank, row in enumerate(cur.fetchall(), start=1):
                        dense_ranks[int(row[0])] = rank
                except sqlite3.Error as e:
                    logger.warning("vec_search_failed", error=str(e))

            # 2. Sparse search (BM25 via FTS5)
            sparse_ranks: dict[int, int] = {}
            if mode in ("hybrid", "bm25"):
                expanded_query = f"{q.query_text} {subtokens(q.query_text)}"
                fts_query_str = build_fts_query(expanded_query)

                try:
                    cur.execute(
                        "SELECT rowid, bm25(fts_memories) as score FROM fts_memories "
                        "WHERE fts_memories MATCH ? "
                        "ORDER BY score "
                        "LIMIT ?",
                        (fts_query_str, MAX_CANDIDATES),
                    )
                    for rank, row in enumerate(cur.fetchall(), start=1):
                        sparse_ranks[int(row[0])] = rank
                except sqlite3.Error as e:
                    logger.warning("fts_search_failed", error=str(e))

            # 3. Reciprocal Rank Fusion (k=60)
            all_candidate_ids = set(dense_ranks.keys()) | set(sparse_ranks.keys())
            if self.quarantined_memory_ids:
                all_candidate_ids -= set(self.quarantined_memory_ids)
            if not all_candidate_ids:
                return []

            rrf_scores: dict[int, float] = {}
            for mid in all_candidate_ids:
                score = 0.0
                if mid in dense_ranks:
                    score += 1.0 / (RRF_K_CONST + dense_ranks[mid])
                if mid in sparse_ranks:
                    score += 1.0 / (RRF_K_CONST + sparse_ranks[mid])
                rrf_scores[mid] = score

            # Sort candidates descending by RRF score
            sorted_candidates = sorted(
                all_candidate_ids, key=lambda mid: rrf_scores[mid], reverse=True
            )

            # 4. Fetch memory details & apply filters
            hits: list[MemoryHit] = []
            fact_hits: list[MemoryHit] = []

            placeholders = ",".join("?" for _ in sorted_candidates)
            query_sql = f"""
                SELECT m.memory_id, m.content, m.kind, m.created_at, m.valid_from,
                       m.valid_to, m.forgotten_at, p.provenance, p.trace_id, p.session_id, p.grounding_eligible,
                       p.confidence, p.content_sha256, p.signature, p.payload_json
                FROM memories m
                JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE m.memory_id IN ({placeholders})
            """  # noqa: S608

            cur.execute(query_sql, list(sorted_candidates))
            rows = {int(r[0]): r for r in cur.fetchall()}

            for mid in sorted_candidates:
                if mid not in rows:
                    continue
                r = rows[mid]

                # Integrity check — two-stage:
                # Stage 1: content_sha256 fast-fail (catches naive DB edits)
                # Stage 2: HMAC-SHA256 over payload_json (requires master_key; catches
                #           any edit that also updated content_sha256 in the envelope)
                _integrity_ok = True
                try:
                    stored_sha = r["content_sha256"]
                    actual_sha = hashlib.sha256(
                        str(r["content"]).encode("utf-8")
                    ).hexdigest()
                    if stored_sha and actual_sha != stored_sha:
                        logger.error(
                            "memory_retrieval_integrity_violation",
                            stage="content_sha256",
                            memory_id=mid,
                        )
                        _integrity_ok = False

                    if _integrity_ok and self.master_key is not None:
                        stored_sig = r["signature"]
                        payload_json_raw = r["payload_json"]
                        if stored_sig and payload_json_raw:
                            # Reconstruct canonical bytes the same way BaseProvenanceSigner.sign()
                            # does: parse the stored JSON, strip the 4 excluded fields, then
                            # re-serialize with sorted keys + compact separators.
                            # This matches canonicalize_unsigned_payload() exactly.
                            _EXCLUDED = {"signature", "signer_id", "entry_id", "content_sha256"}
                            try:
                                raw_dict = json.loads(payload_json_raw)
                                if "content" in raw_dict and raw_dict["content"] != r["content"]:
                                    logger.error(
                                        "memory_retrieval_integrity_violation",
                                        stage="payload_content_mismatch",
                                        memory_id=mid,
                                    )
                                    _integrity_ok = False
                                canon_dict = {k: v for k, v in raw_dict.items() if k not in _EXCLUDED}
                                canonical_bytes = json.dumps(
                                    canon_dict,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                    ensure_ascii=False,
                                ).encode("utf-8")
                            except (json.JSONDecodeError, AttributeError) as parse_err:
                                logger.warning(
                                    "memory_retrieval_payload_parse_error",
                                    memory_id=mid,
                                    error=str(parse_err),
                                )
                                canonical_bytes = None

                            if canonical_bytes is not None:
                                prov_enum = Provenance(r["provenance"])
                                derived_key = derive_provenance_key(self.master_key, prov_enum)
                                expected_raw = hmac.new(
                                    derived_key, canonical_bytes, hashlib.sha256
                                ).digest()
                                expected_sig = base64.b64encode(expected_raw).decode("ascii")
                                if not hmac.compare_digest(stored_sig, expected_sig):
                                    logger.error(
                                        "memory_retrieval_integrity_violation",
                                        stage="hmac",
                                        memory_id=mid,
                                    )
                                    _integrity_ok = False

                except (KeyError, IndexError, ValueError) as exc:
                    logger.warning(
                        "memory_retrieval_integrity_check_error",
                        memory_id=mid,
                        error=str(exc),
                    )

                if not _integrity_ok:
                    eid = str(r["entry_id"]) if "entry_id" in r.keys() else None
                    logger.error(
                        "memory_retrieval_integrity_quarantine",
                        stage="integrity_quarantine",
                        memory_id=mid,
                        entry_id=eid,
                        msg=f"Memory row {mid} failed integrity verification (SHA256/HMAC mismatch). Row quarantined.",
                    )
                    self.quarantined_memory_ids.append(mid)
                    self._persist_quarantine(
                        memory_id=mid,
                        entry_id=eid,
                        stage="hmac_or_sha256",
                        reason="Cryptographic integrity verification failed",
                    )
                    warn = f"Security notice: Memory record {mid} failed cryptographic verification and was quarantined."
                    if warn not in self.user_integrity_warnings:
                        self.user_integrity_warnings.append(warn)

                    if self.raise_on_tamper:
                        raise RuntimeError(
                            f"Memory integrity violation detected for memory_id={mid}. "
                            "The record may have been tampered with. Retrieval aborted."
                        )
                    # Quarantine: exclude from hits and continue retrieving valid rows
                    continue

                valid_to = r["valid_to"]
                forgotten_at = r["forgotten_at"]
                kind = str(r["kind"])
                created_at = float(r["created_at"])

                # Filters:
                # - forgotten_at IS NULL (always exclude forgotten memories)
                if forgotten_at is not None:
                    continue
                # - valid_to IS NULL unless include_superseded is True
                if valid_to is not None and not q.include_superseded:
                    continue
                # - kind filter
                if q.kinds is not None and kind not in q.kinds:
                    continue
                # - since timestamp filter
                if q.since is not None and created_at < q.since:
                    continue

                grounding_el = True
                try:
                    grounding_el = bool(r["grounding_eligible"])
                except (KeyError, IndexError):
                    pass

                conf_val = 1.0
                try:
                    if r["confidence"] is not None:
                        conf_val = float(r["confidence"])
                except (KeyError, IndexError, ValueError):
                    pass

                hit = MemoryHit(
                    memory_id=mid,
                    content=str(r["content"]),
                    provenance=Provenance(r["provenance"]),
                    score=rrf_scores[mid],
                    source_turn_id=r["trace_id"] or r["session_id"],
                    kind=kind,
                    created_at=created_at,
                    valid_from=float(r["valid_from"]),
                    valid_to=float(valid_to) if valid_to is not None else None,
                    grounding_eligible=grounding_el,
                    confidence=conf_val,
                )
                hits.append(hit)
                if kind == "fact":
                    fact_hits.append(hit)

                if len(hits) >= q.k:
                    break

            # 5. 1-hop KG expansion for fact hits
            min_score = hits[-1].score if hits else 0.01
            graph_score = 0.5 * min_score
            graph_hits: list[MemoryHit] = []

            if fact_hits:
                fact_ids = [int(h.memory_id) for h in fact_hits if isinstance(h.memory_id, int)]
                if fact_ids:
                    ph = ",".join("?" for _ in fact_ids)
                    edge_sql = f"""
                        SELECT ed.memory_id, e1.canonical, ed.p, e2.canonical, ed.valid_from
                        FROM kg_edges ed
                        JOIN kg_entities e1 ON ed.s = e1.entity_id
                        JOIN kg_entities e2 ON ed.o = e2.entity_id
                        WHERE ed.memory_id IN ({ph}) AND ed.valid_to IS NULL
                    """  # noqa: S608
                    cur.execute(edge_sql, fact_ids)
                    for erow in cur.fetchall():
                        s_name, p, o_name = str(erow[1]), str(erow[2]), str(erow[3])
                        graph_content = f"{s_name} {p} {o_name}"
                        graph_hit = MemoryHit(
                            memory_id=int(erow[0]),
                            content=graph_content,
                            provenance=Provenance.USER_DERIVED,
                            score=graph_score,
                            kind="graph",
                            created_at=current_time,
                            valid_from=float(erow[4]),
                        )
                        graph_hits.append(graph_hit)

        # 6. Dedupe & combine: prefer direct hits over graph expansions,
        # active over superseded, higher provenance tier, then score, recency
        hits_to_dedupe = sorted(
            hits + graph_hits,
            key=lambda h: (
                1 if h.kind == "graph" else 0,
                1 if h.valid_to is not None else 0,
                _provenance_tier(h.provenance),
                -h.score,
                -h.created_at,
            ),
        )
        seen_contents: set[str] = set()
        deduped: list[MemoryHit] = []

        for h in hits_to_dedupe:
            key = h.content.strip().lower()
            if key not in seen_contents:
                seen_contents.add(key)
                deduped.append(h)

        deduped.sort(key=lambda h: -h.score)
        result = deduped[: q.k]

        # 7. Batched access count and last_access update
        matched_mids = [int(h.memory_id) for h in result if isinstance(h.memory_id, int)]
        if matched_mids:
            try:
                writer = self.db.get_writer()
                ph = ",".join("?" for _ in matched_mids)
                writer.execute(
                    f"UPDATE memories SET access_count = access_count + 1, last_access = ? "  # noqa: S608
                    f"WHERE memory_id IN ({ph})",
                    [current_time, *matched_mids],
                )
            except sqlite3.Error as e:
                logger.warning("access_update_failed", error=str(e))

        return result

    def index_decision(self, record: DecisionRecord, error: str = "") -> None:
        """Indexes a DecisionRecord into in-session FTS5 retrieval cascade (ITEM-021)."""
        index_decision_record(self.db, record, error=error)

    def search_decisions(self, query: str, limit: int = 5) -> list[DecisionRecord]:
        """Queries past DecisionRecord rows via FTS5 search (ITEM-021)."""
        return search_decision_records(self.db, query, limit=limit)


def ensure_decision_fts(conn: sqlite3.Connection) -> None:
    """Ensures fts_decisions virtual table exists (ITEM-021)."""
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_decisions USING fts5(
                decision_id UNINDEXED,
                trace_id,
                transcript,
                intent,
                action,
                executed_path,
                tool_calls,
                error,
                tokenize="unicode61 remove_diacritics 2 tokenchars '_'"
            );
            """
        )
    except sqlite3.Error as e:
        logger.debug("ensure_decision_fts_failed", error=str(e))


def index_decision_record(db: DatabaseManager, record: DecisionRecord, error: str = "") -> None:
    """Indexes a DecisionRecord into SQLite decisions and fts_decisions table (ITEM-021)."""
    try:
        writer = db.get_writer()
        ensure_decision_fts(writer)

        cur = writer.cursor()
        cur.execute("SELECT 1 FROM decisions WHERE decision_id = ?", (record.decision_id,))
        if not cur.fetchone():
            action_val = (
                record.decision.action.value
                if hasattr(record.decision.action, "value")
                else str(record.decision.action)
            )
            probs_json = json.dumps(
                record.decision.probabilities if record.decision.probabilities is not None else {}
            )
            preds_json = json.dumps(
                [a.value if hasattr(a, "value") else str(a) for a in record.decision.prediction_set]
                if record.decision.prediction_set is not None
                else []
            )
            tool_calls_json = (
                json.dumps([tc.model_dump() for tc in record.tool_calls])
                if record.tool_calls
                else None
            )
            tool_ok_val = 1 if record.tool_ok else (0 if record.tool_ok is False else None)

            writer.execute(
                """
                INSERT INTO decisions(
                    decision_id, trace_id, session_id, ts, features_json, action,
                    probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                    router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                    user_interrupted, interrupted_after_ms, counterfactual_rule_fired
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.decision_id,
                    record.trace_id,
                    record.session_id,
                    record.ts,
                    json.dumps(record.features.model_dump(), ensure_ascii=False),
                    action_val,
                    probs_json,
                    preds_json,
                    1 if record.decision.fallback_applied else 0,
                    record.decision.elapsed_us,
                    record.router_version,
                    record.executed_path,
                    tool_calls_json,
                    tool_ok_val,
                    record.llm_first_token_ms,
                    1 if record.user_interrupted else 0,
                    record.interrupted_after_ms,
                    1 if record.counterfactual_rule_fired else 0,
                ),
            )

        # Upsert into fts_decisions
        writer.execute("DELETE FROM fts_decisions WHERE decision_id = ?", (record.decision_id,))
        tool_calls_str = " ".join(tc.tool for tc in record.tool_calls) if record.tool_calls else ""
        action_str = (
            record.decision.action.value
            if hasattr(record.decision.action, "value")
            else str(record.decision.action)
        )
        writer.execute(
            """
            INSERT INTO fts_decisions(
                decision_id, trace_id, transcript, intent, action, executed_path, tool_calls, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.decision_id,
                record.trace_id,
                record.features.transcript,
                record.features.intent,
                action_str,
                record.executed_path,
                tool_calls_str,
                error,
            ),
        )
    except sqlite3.Error as e:
        logger.warning("index_decision_record_failed", error=str(e), decision_id=record.decision_id)


def search_decision_records(
    db: DatabaseManager,
    query: str,
    limit: int = 5,
) -> list[DecisionRecord]:
    """Retrieves DecisionRecord rows matching the query via FTS5 with fallback
    to LIKE search (ITEM-021)."""
    if not query.strip():
        return []

    results: list[DecisionRecord] = []
    with db.read_cursor() as cur:
        ensure_decision_fts(cur.connection)
        matched_ids: list[str] = []

        try:
            expanded_q = f"{query} {subtokens(query)}"
            fts_q = build_fts_query(expanded_q)
            cur.execute(
                """
                SELECT decision_id FROM fts_decisions
                WHERE fts_decisions MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_q, limit),
            )
            matched_ids = [str(r[0]) for r in cur.fetchall()]
        except sqlite3.Error as e:
            logger.debug("fts_decisions_query_failed", error=str(e))

        if not matched_ids:
            tokens = [t.lower() for t in query.split() if len(t) >= 3]
            if tokens:
                clauses = " OR ".join(
                    "("
                    "features_json LIKE ? OR executed_path LIKE ? "
                    "OR action LIKE ? OR tool_calls_json LIKE ?"
                    ")"
                    for _ in tokens
                )
                params: list[object] = []
                for t in tokens:
                    pat = f"%{t}%"
                    params.extend([pat, pat, pat, pat])
                params.append(limit)
                try:
                    cur.execute(
                        f"""
                        SELECT decision_id FROM decisions
                        WHERE {clauses}
                        ORDER BY ts DESC
                        LIMIT ?
                        """,  # noqa: S608
                        params,
                    )
                    matched_ids = [str(r[0]) for r in cur.fetchall()]
                except sqlite3.Error as fallback_e:
                    logger.debug("decisions_like_fallback_failed", error=str(fallback_e))

        if not matched_ids:
            return []

        ph = ",".join("?" for _ in matched_ids)
        try:
            cur.execute(
                f"""
                SELECT decision_id, trace_id, session_id, ts, features_json, action,
                       probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                       router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                       user_interrupted, interrupted_after_ms, counterfactual_rule_fired
                FROM decisions
                WHERE decision_id IN ({ph})
                """,  # noqa: S608
                matched_ids,
            )
            row_map = {str(r["decision_id"]): r for r in cur.fetchall()}
            for did in matched_ids:
                if did not in row_map:
                    continue
                r = row_map[did]
                feat_dict = (
                    json.loads(r["features_json"])
                    if isinstance(r["features_json"], str)
                    else r["features_json"]
                )
                features = RouteFeatures.model_validate(feat_dict)
                probs = json.loads(r["probabilities_json"]) if r["probabilities_json"] else None
                preds = (
                    json.loads(r["prediction_set_json"])
                    if r["prediction_set_json"]
                    else [r["action"]]
                )
                tc_raw = json.loads(r["tool_calls_json"]) if r["tool_calls_json"] else []
                tool_calls = [ToolCall.model_validate(tc) for tc in tc_raw] if tc_raw else []

                decision = RouteDecision(
                    action=r["action"],
                    tier=features.tier,
                    probabilities=probs,
                    prediction_set=preds,
                    fallback_applied=bool(r["fallback_applied"]),
                    elapsed_us=int(r["elapsed_us"]),
                )

                rec = DecisionRecord(
                    decision_id=str(r["decision_id"]),
                    trace_id=str(r["trace_id"]),
                    session_id=str(r["session_id"]),
                    ts=float(r["ts"]),
                    features=features,
                    decision=decision,
                    router_version=str(r["router_version"]),
                    executed_path=str(r["executed_path"]),
                    tool_calls=tool_calls,
                    tool_ok=bool(r["tool_ok"]) if r["tool_ok"] is not None else None,
                    llm_first_token_ms=(
                        float(r["llm_first_token_ms"])
                        if r["llm_first_token_ms"] is not None
                        else None
                    ),
                    user_interrupted=bool(r["user_interrupted"]),
                    interrupted_after_ms=(
                        float(r["interrupted_after_ms"])
                        if r["interrupted_after_ms"] is not None
                        else None
                    ),
                    counterfactual_rule_fired=bool(r["counterfactual_rule_fired"]),
                )
                results.append(rec)
        except Exception as parse_e:  # noqa: BLE001
            logger.debug("decision_records_fetch_failed", error=str(parse_e))

    return results
