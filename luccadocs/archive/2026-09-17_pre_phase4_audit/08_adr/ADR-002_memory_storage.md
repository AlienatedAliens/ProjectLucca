# ADR-002 — Memory Storage: single SQLite file (WAL) with FTS5 + `sqlite-vec`; networkx as in-memory view only

**Status:** Accepted 2026-09-17 (D-06)
**Supersedes:** doc 00 §Phase 3 "ChromaDB (vector) + networkx"; doc 05 memory block; `pyproject.toml` `chromadb`, `rank-bm25`.

## Context

The drafted stack was ChromaDB (dense vectors) + `rank-bm25` (sparse) + networkx serialized by pickle (graph) + an in-memory provenance gate. Problems identified in review:

| Problem | Source |
|---|---|
| ChromaDB pulls `onnxruntime`, `tokenizers`, a default embedding model downloaded on first run (offline-first violation), and posthog telemetry on by default (local-first violation). | review |
| ChromaDB uses SQLite internally and throws `database is locked` under concurrent writer/reader/reflection threads. | doc 01 L153 |
| `rank-bm25` rebuilds its index in O(N) on every add and exhibits IDF degeneracy when a term appears in > N/2 docs. | doc 01 L149–152 |
| networkx pickle = arbitrary-code-execution on tampered file; JSON alternative rewrites whole graph per mutation (150 ms+ at 5 k nodes). | doc 01 L147–148 |
| Four stores → four consistency domains; a memory commit could succeed in the vector store and fail in the graph with no rollback. | review |
| Provenance envelopes, decision logs, rule store, and calibration data had **no** designated storage at all. | review |

Verified: `sqlite-vec` ships Python 3.12 Windows wheels and loads alongside FTS5 in stock `sqlite3` (research 7.6). Corpus scale is small (tens of thousands of memories at most over years).

## Decision

One database file, `C:\ProjectLucca\data\memory.sqlite`, opened by **exactly one process** (`lucca-core`), `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. It holds:

| Concern | Mechanism |
|---|---|
| Dense retrieval | `sqlite-vec` virtual table `vec_memories(embedding float[384])`, cosine distance. |
| Sparse retrieval | FTS5 virtual table `fts_memories` with a **custom tokenizer pipeline**: `unicode61 remove_diacritics 2` plus a pre-tokenization step that also emits sub-tokens split on `_ . - /` so `ERR_403_INVALID_TOKEN` and `config.yaml` are matchable by parts. BM25 via built-in `bm25()` (lower = better; negate for RRF). |
| Knowledge graph | Relational tables `kg_entities`, `kg_edges` with bi-temporal columns; networkx graph is **rebuilt from these tables at startup** and used read-only for traversal/PPR. Never pickled. |
| Provenance | `provenance_envelopes` — every memory row references one; envelope carries provenance type, signer id, signature, source pointers, ASR confidence. |
| Working memory | Not persisted (in-process object); a `task_journal` table records task open/close for crash recovery only. |
| Router/classifier | `decisions`, `decision_labels`, `vec_decisions` (embeddings for cluster distinctness), `calibration_sets`. |
| Rules | `rules`, `rule_versions`, `rule_evaluations`, `rule_regression_cases`. |
| Audit | `memory_audit` append-only trigger log of every insert/update/delete on memory tables. |
| Schema versioning | `schema_migrations(version, applied_at)`; forward-only migrations in `lucca/memory/migrations/NNNN_*.sql`. |

Full DDL: spec 04.

### Access rules

1. Only `lucca-core` opens the file for writing. Other processes never touch it; they message `lucca-core`.
2. All writes go through a single `asyncio` write-queue coroutine → serialised transactions, no writer contention.
3. Reads use a separate connection pool (WAL allows concurrent readers).
4. A memory commit = **one transaction**: envelope insert → memory row → vec row → fts row → kg edges → audit. Any failure rolls back everything.
5. Backups: `VACUUM INTO 'data\backups\memory-YYYYMMDD-HHMM.sqlite'` daily at first idle ≥ 5 min; keep 14 dailies + 8 weeklies. Integrity: `PRAGMA integrity_check` weekly; failure → alert + refuse writes until restored.

### Hybrid retrieval (canonical)

```
dense_k   = top 30 by cosine (vec_memories)
sparse_k  = top 30 by bm25 (fts_memories)
rrf(d)    = Σ_{lists containing d} 1 / (60 + rank_list(d))
final     = top k by rrf, then graph-expand 1 hop on kg_edges for entities present, cap k_total = 8
```

Benchmarks and thresholds in testing matrix v2 (`Hit@1 ≥ 0.93` on the frozen identifier set; `Recall@3 ≥ 0.90` on the frozen paraphrase set).

## Consequences

**Positive**
- One file, one lock model, atomic commits across vector/text/graph/provenance.
- No network, no telemetry, no first-run downloads, no pickle.
- Zero extra services; backup = copy a file.
- Decision log and rule store finally have a home with referential integrity to memories.

**Negative / risks**
- `sqlite-vec` brute-force KNN is O(N); fine to ~100 k rows at 384-d (< 10 ms). If exceeded, add IVF partitioning or swap to `hnswlib` behind `VectorStorePort`. Alarm at 50 k rows.
- Custom FTS tokenization must be applied identically at index and query time — encapsulate in one function; property-test it.
- Single-writer design means `lucca-core` is a bottleneck for writes; acceptable at human conversation rates (< 10 writes/s).
- Extension loading requires `sqlite3.enable_load_extension(True)`; some embedded Pythons lack it — environment check asserts it.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep ChromaDB | Locking, RAM, telemetry, download, second consistency domain. Retained as an *adapter* behind `VectorStorePort` for anyone who insists. |
| LanceDB | Good, but adds Arrow runtime (~200 MB) and a second file format; no FTS5-equivalent tokenizer control. |
| FAISS / hnswlib + SQLite | Two stores again; index persistence separate from transactions. |
| Neo4j / Kùzu for graph | Overkill; extra process; the graph is small and traversal happens in networkx in memory. |
| NumPy brute-force cosine only | Viable and even simpler; rejected only because `sqlite-vec` keeps the vector inside the same transaction. Documented as the trivial fallback if `sqlite-vec` wheels break. |
