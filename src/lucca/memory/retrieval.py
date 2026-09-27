"""
Project Lucca — Hybrid Memory Retrieval (sqlite-vec KNN + FTS5 BM25 + RRF)
Spec 04 §6, Spec 10
"""

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
    hits: list[MemoryHit], max_tokens: int = 2048, now: float | None = None
) -> str:
    """
    Render memory hits into prompt context block per Spec 04 §6 / Spec 10 / D-MEM-03:
    - [{kind}/{provenance} {age}] {content} truncated to 160 chars
    - graph hits as: - {content}
    - sorted by multi-factor hierarchy: (provenance tier, -score, -created_at)
    - Enforces <= max_tokens (approx 4 chars/token).
    """
    current_time = now if now is not None else time.time()
    max_items = 8
    sorted_hits = sorted(
        hits,
        key=lambda h: (
            _provenance_tier(h.provenance),
            1 if h.valid_to is not None else 0,
            -h.score,
            -h.created_at,
        ),
    )
    lines: list[str] = []
    char_budget = max_tokens * 4

    current_len = 0
    for hit in sorted_hits[:max_items]:
        content_clean = hit.content[:160].replace("\r\n", "\n").replace("\r", "\n")
        while "\n[" in content_clean:
            content_clean = content_clean.replace("\n[", "\n(")
        if content_clean.startswith("["):
            content_clean = "(" + content_clean[1:]

        if hit.kind == "graph":
            line = f"- {content_clean}"
        else:
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
                line = f"{prefix} {content_clean}"
            else:
                conf_str = (
                    f" conf={hit.confidence:.2f}" if getattr(hit, "confidence", 1.0) < 0.85 else ""
                )
                line = f"- [{hit.kind}/{prov_val}{conf_str} {age}] {content_clean}"

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

    def __init__(self, db: DatabaseManager, embedder: EmbeddingPort | None = None) -> None:
        self.db = db
        self.embedder = embedder

    def search(self, q: RetrievalQuery, now: float | None = None) -> list[MemoryHit]:
        current_time = now if now is not None else time.time()

        # 1. Dense search (KNN via sqlite-vec)
        dense_ranks: dict[int, int] = {}
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
            if query_vec is not None:
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
                       m.valid_to, m.forgotten_at, p.provenance, p.trace_id, p.grounding_eligible,
                       p.confidence
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
                    source_turn_id=r["trace_id"],
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
