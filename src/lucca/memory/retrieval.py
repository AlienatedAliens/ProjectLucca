"""
Project Lucca — Hybrid Memory Retrieval (sqlite-vec KNN + FTS5 BM25 + RRF)
Spec 04 §6, Spec 10
"""

import sqlite3
import time
from typing import Final

import sqlite_vec
import structlog

from lucca.core.schemas import MemoryHit, Provenance, RetrievalQuery
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


def format_memory_context(
    hits: list[MemoryHit], max_tokens: int = 600, now: float | None = None
) -> str:
    """
    Render memory hits into prompt context block per Spec 04 §6 / Spec 10:
    - [{kind}/{provenance} {age}] {content} truncated to 160 chars
    - graph hits as: - {content}
    - k <= 8 hits
    - leading '[' and newline headers converted to '(' to prevent prompt header injection
    Enforces <= max_tokens (approx 4 chars/token).
    """
    current_time = now if now is not None else time.time()
    lines: list[str] = []
    char_budget = max_tokens * 4

    current_len = 0
    for hit in hits[:8]:
        content_clean = hit.content[:160].replace("\r\n", "\n").replace("\r", "\n")
        while "\n[" in content_clean:
            content_clean = content_clean.replace("\n[", "\n(")
        if content_clean.startswith("["):
            content_clean = "(" + content_clean[1:]

        if hit.kind == "graph":
            line = f"- {content_clean}"
        else:
            age = calculate_age_str(hit.created_at, current_time)
            line = f"- [{hit.kind}/{hit.provenance.value} {age}] {content_clean}"

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

    async def search(self, q: RetrievalQuery, now: float | None = None) -> list[MemoryHit]:
        current_time = now if now is not None else time.time()

        # 1. Dense search (KNN via sqlite-vec)
        dense_ranks: dict[int, int] = {}
        query_vec = q.query_vector
        if query_vec is None and self.embedder is not None:
            try:
                vecs = await self.embedder.embed([q.query_text])
                if vecs and len(vecs[0]) == 384:
                    query_vec = vecs[0]
            except (RuntimeError, ValueError, OSError) as e:
                logger.warning("dense_embedding_failed", error=str(e))

        if query_vec is not None:
            try:
                serialized = sqlite_vec.serialize_float32(query_vec)
                with self.db.read_cursor() as cur:
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
            with self.db.read_cursor() as cur:
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
        sorted_candidates = sorted(all_candidate_ids, key=lambda mid: rrf_scores[mid], reverse=True)

        # 4. Fetch memory details & apply filters
        hits: list[MemoryHit] = []
        fact_hits: list[MemoryHit] = []

        placeholders = ",".join("?" for _ in sorted_candidates)
        query_sql = f"""
            SELECT m.memory_id, m.content, m.kind, m.created_at, m.valid_from,
                   m.valid_to, m.forgotten_at, p.provenance, p.trace_id
            FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            WHERE m.memory_id IN ({placeholders})
        """  # noqa: S608

        with self.db.read_cursor() as cur:
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
                with self.db.read_cursor() as cur:
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

        # 6. Dedupe & combine
        seen_contents: set[str] = set()
        deduped: list[MemoryHit] = []

        for h in hits + graph_hits:
            key = h.content.strip().lower()
            if key not in seen_contents:
                seen_contents.add(key)
                deduped.append(h)

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
