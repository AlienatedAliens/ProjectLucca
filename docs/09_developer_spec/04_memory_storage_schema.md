# Spec 04 — Memory Storage Schema, Retrieval, Temporal Facts, Backups

Implements ADR-002. File: `C:\ProjectLucca\data\memory.sqlite`. Migrations in `src/lucca/memory/migrations/0001_init.sql` … applied by `lucca.memory.db.migrate()` at boot.

## 1. Connection settings (every connection)

```sql
PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-65536;  -- 64 MiB
```
Load `sqlite_vec` via `sqlite_vec.load(conn)` after `conn.enable_load_extension(True)`; then `enable_load_extension(False)`.

Writer: one connection, owned by `MemoryStore` write-queue task. Readers: pool of 4.

## 2. DDL (migration 0001)

```sql
CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);

CREATE TABLE provenance_envelopes(
  entry_id        TEXT PRIMARY KEY,               -- from SignedPayload
  provenance      TEXT NOT NULL CHECK(provenance IN ('USER_EXPLICIT','USER_EXPLICIT_LOWCONF','USER_DERIVED','TOOL_VERIFIED','TOOL_CONTENT_UNTRUSTED','LISP_ASSERTION')),
  kind            TEXT NOT NULL,
  signer_id       TEXT NOT NULL,
  signature       TEXT NOT NULL,
  content_sha256  TEXT NOT NULL,
  nonce           TEXT NOT NULL,
  created_at      REAL NOT NULL,
  trace_id        TEXT NOT NULL,
  session_id      TEXT NOT NULL,
  asr_model       TEXT, asr_avg_logprob REAL, audio_sha256 TEXT,
  tool_name       TEXT, tool_call_id TEXT, tool_exit_code INTEGER,
  confidence      REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  payload_json    TEXT NOT NULL                    -- full canonical payload for re-verification
);
CREATE UNIQUE INDEX ux_env_nonce ON provenance_envelopes(nonce, content_sha256);

CREATE TABLE memories(
  memory_id   INTEGER PRIMARY KEY,
  entry_id    TEXT NOT NULL UNIQUE REFERENCES provenance_envelopes(entry_id),
  content     TEXT NOT NULL,
  tokens_aux  TEXT NOT NULL DEFAULT '',             -- sub-tokens (split on _ . - /) computed by the app before insert
  kind        TEXT NOT NULL,                        -- transcript|fact|tool_fact|rule_assertion
  created_at  REAL NOT NULL,
  valid_from  REAL NOT NULL,                        -- when the fact became true (defaults created_at)
  valid_to    REAL,                                 -- NULL = currently valid
  superseded_by INTEGER REFERENCES memories(memory_id),
  forgotten_at REAL,                                -- soft delete; content replaced by '' on hard purge
  importance  REAL NOT NULL DEFAULT 0.5,
  access_count INTEGER NOT NULL DEFAULT 0,
  last_access REAL
);
CREATE INDEX ix_mem_valid ON memories(valid_to, kind);
-- Memory-eligibility is enforced here, not in the envelope CHECK (envelopes also hold non-memory provenances):
CREATE TRIGGER mem_bi_eligible BEFORE INSERT ON memories BEGIN
  SELECT RAISE(ABORT, 'provenance not memory-eligible')
  WHERE (SELECT provenance FROM provenance_envelopes WHERE entry_id = new.entry_id)
        NOT IN ('USER_EXPLICIT','USER_DERIVED','TOOL_VERIFIED','LISP_ASSERTION');
END;

CREATE TABLE memory_sources(                        -- lineage for USER_DERIVED
  memory_id INTEGER NOT NULL REFERENCES memories(memory_id),
  source_entry_id TEXT NOT NULL REFERENCES provenance_envelopes(entry_id),
  PRIMARY KEY(memory_id, source_entry_id)
);

CREATE VIRTUAL TABLE vec_memories USING vec0(
  memory_id INTEGER PRIMARY KEY, embedding float[384] distance_metric=cosine);

-- External-content FTS over memories(content, tokens_aux). Both columns exist in `memories`.
CREATE VIRTUAL TABLE fts_memories USING fts5(
  content, tokens_aux, content='memories', content_rowid='memory_id',
  tokenize="unicode61 remove_diacritics 2 tokenchars '_'");
-- Standard external-content sync triggers (insert / delete / update):
CREATE TRIGGER mem_ai AFTER INSERT ON memories BEGIN
  INSERT INTO fts_memories(rowid, content, tokens_aux) VALUES (new.memory_id, new.content, new.tokens_aux);
END;
CREATE TRIGGER mem_ad AFTER DELETE ON memories BEGIN
  INSERT INTO fts_memories(fts_memories, rowid, content, tokens_aux) VALUES ('delete', old.memory_id, old.content, old.tokens_aux);
END;
CREATE TRIGGER mem_au AFTER UPDATE OF content, tokens_aux ON memories BEGIN
  INSERT INTO fts_memories(fts_memories, rowid, content, tokens_aux) VALUES ('delete', old.memory_id, old.content, old.tokens_aux);
  INSERT INTO fts_memories(rowid, content, tokens_aux) VALUES (new.memory_id, new.content, new.tokens_aux);
END;
-- `tokens_aux` is produced by lucca.memory.tokens.subtokens(text) — a pure Python function used identically at
-- index time (before INSERT) and at query time (spec §6). Property test P-06 covers it.

CREATE TABLE kg_entities(
  entity_id  INTEGER PRIMARY KEY,
  canonical  TEXT NOT NULL UNIQUE,                  -- lowercased, NFC, whitespace-collapsed
  type       TEXT NOT NULL DEFAULT 'thing',         -- person|place|org|thing|user|app|file
  created_at REAL NOT NULL
);
CREATE TABLE kg_aliases(alias TEXT PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES kg_entities(entity_id));

CREATE TABLE kg_edges(
  edge_id     INTEGER PRIMARY KEY,
  s           INTEGER NOT NULL REFERENCES kg_entities(entity_id),
  p           TEXT NOT NULL,
  o           INTEGER NOT NULL REFERENCES kg_entities(entity_id),
  memory_id   INTEGER NOT NULL REFERENCES memories(memory_id),   -- provenance carrier
  valid_from  REAL NOT NULL, valid_to REAL, recorded_at REAL NOT NULL,
  confidence  REAL NOT NULL
);
CREATE INDEX ix_edge_sp ON kg_edges(s, p, valid_to);
CREATE INDEX ix_edge_o  ON kg_edges(o, valid_to);

CREATE TABLE tool_contents(                         -- TOOL_CONTENT_UNTRUSTED, not memory
  content_id INTEGER PRIMARY KEY, entry_id TEXT REFERENCES provenance_envelopes(entry_id),
  trace_id TEXT NOT NULL, tool_name TEXT NOT NULL, body TEXT NOT NULL, sha256 TEXT NOT NULL,
  created_at REAL NOT NULL, expires_at REAL NOT NULL);

CREATE TABLE pending_confirmations(
  pending_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
  created_at REAL NOT NULL, expires_at REAL NOT NULL);

CREATE TABLE gate_nonces(nonce TEXT NOT NULL, content_sha256 TEXT NOT NULL, seen_at REAL NOT NULL, PRIMARY KEY(nonce, content_sha256));

CREATE TABLE memory_audit(
  audit_id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL,   -- commit|reject|supersede|forget|purge
  reason TEXT, provenance TEXT, trace_id TEXT, entry_id TEXT, content_sha256 TEXT);

CREATE TABLE task_journal(task_id TEXT PRIMARY KEY, opened_at REAL NOT NULL, closed_at REAL, outcome TEXT);
```

Router/rule tables (`decisions`, `decision_labels`, `vec_decisions`, `calibration_sets`, `rules`, `rule_versions`, `rule_evaluations`, `rule_regression_cases`) are defined in specs 05 and 06 and created in migration 0002/0003.

## 3. Closed predicate list (`PREDICATES`)

`is_named, has_sibling, has_parent, has_child, has_partner, has_friend, lives_in, works_at, works_as, born_on, likes, dislikes, owns, uses_app, prefers, allergic_to, speaks_language, has_pet, studies, birthday_is, timezone_is, project_is, note`.
Functional predicates (at most one currently-valid object per subject): `lives_in, works_at, works_as, born_on, timezone_is, birthday_is`. Adding a predicate = migration + test update; the extraction grammar is generated from this list.

## 4. Commit algorithm (single transaction)

```
BEGIN IMMEDIATE
  INSERT provenance_envelopes
  INSERT memories (valid_from = structured.valid_from or created_at)
  INSERT memory_sources (for each source_entry_id)
  INSERT vec_memories (embedding from EmbeddingPort, computed BEFORE the txn)
  -- fts via trigger
  IF kind='fact':
     upsert kg_entities/aliases for s and o (canonicalise; alias resolution §5)
     IF p functional: UPDATE kg_edges SET valid_to=now WHERE s=? AND p=? AND valid_to IS NULL AND o<>new_o;
                      UPDATE memories SET valid_to=now, superseded_by=new_id WHERE memory_id IN (those edges' memory_id)
                      INSERT memory_audit(kind='supersede')
     INSERT kg_edges
  INSERT gate_nonces
  INSERT memory_audit(kind='commit')
COMMIT
```
Any exception → ROLLBACK, re-raise `MemoryCommitFailed(cause)`. Embedding failure → commit **without** vector row and enqueue backfill (`vec_backfill` list in memory), logged; retrieval still works via FTS.

## 5. Entity resolution (minimal, deterministic)

1. Canonicalise: NFC → lowercase → strip punctuation except `._-/@` → collapse whitespace.
2. First-person (`i, me, my, myself`) and empty subject → entity `user`.
3. Exact alias hit → that entity.
4. Else if `rapidfuzz.ratio(canonical, existing.canonical) ≥ 94` and same `type` → alias to existing (audit row `alias_added`).
5. Else create. No LLM in resolution (LLM only proposes surface forms).

"My sister" is **not** merged with "Maya" automatically; a `has_sibling(user, maya)` edge is what links them. Coreference across turns is Phase 7+.

## 6. Retrieval

```python
def search(q: RetrievalQuery) -> list[MemoryHit]:
    # q: text, k=8, include_superseded=False, kinds=None, since=None
    dense  = vec_knn(embed(q.text), k=30)                    # (memory_id, cos_dist)
    sparse = fts_bm25(q.text + " " + subtokens(q.text), k=30) # (memory_id, bm25 negative-better)
    fused  = rrf(dense, sparse, k_const=60)
    fused  = filter(valid_to IS NULL unless include_superseded; forgotten_at IS NULL)
    hits   = top(fused, q.k)
    graph  = for each hit.kind=='fact': 1-hop kg_edges (valid) → add as MemoryHit(kind='graph', score=0.5*min_hit_score)
    result = dedupe(hits + graph)[:q.k]; UPDATE access_count/last_access (async, batched)
```
FTS query construction: escape user text as phrase tokens (`"tok"`), OR-joined; never pass raw user text into FTS MATCH (injection of FTS syntax).

Context budget (spec 10): memory block ≤ 600 tokens; render each hit as `- [{kind}/{provenance} {age}] {content}` truncated to 160 chars; graph hits as `- {s} {p} {o}`.

Benchmarks (frozen files in `tests/fixtures/retrieval/`):

| ID | Set | Metric | Gate |
|---|---|---|---|
| T-MEM-01 | `identifiers.jsonl` (30 q; error codes, filenames, serials) | Hit@1 hybrid | ≥ 0.93 (28/30) |
| T-MEM-02 | same | MRR hybrid − MRR dense-only | ≥ +0.20 |
| T-MEM-03 | `paraphrase20.jsonl` (20 facts, 3 paraphrases each) | Recall@3 | ≥ 0.90 |
| T-MEM-04 | same | Precision@1 | ≥ 0.85 |
| T-MEM-05 | 50 k synthetic rows | search p95 | ≤ 25 ms |
| T-MEM-06 | supersession: "I live in Seattle" then "I moved to Berlin" | `lives_in` current = berlin; seattle has valid_to; both retrievable with include_superseded | exact |
| T-MEM-07 | "forget that I live in Berlin" (confirmed) | memory forgotten_at set, edge valid_to set, FTS/vec rows removed, audit `forget` | exact |
| T-MEM-08 | FTS injection: query `"foo" OR content:*` | treated as literal tokens; no error | — |
| T-MEM-09 | concurrent: 200 reads during 50 writes | 0 `database is locked` errors surfaced | — |
| T-MEM-10 | crash mid-commit (kill process between vec insert and commit, via fault injection hook) | after restart: 0 partial rows; integrity_check ok | — |
| T-MEM-11 | migration from empty and from v1 fixture DB | schema_migrations correct; data preserved | — |

## 7. Forgetting & retention

- "Forget X" → LLM identifies candidate memory_ids from a retrieval (k=5) → spoken read-back → confirm → `forget()` sets `forgotten_at`, deletes vec/fts rows, closes edges; content row kept 30 days then hard-purged (`content=''`) — reversible window.
- `tool_contents` expire 24 h; `pending_confirmations` 10 min; `gate_nonces` 24 h; `memory_audit` kept forever (small).
- Audio clips `data\audio\*.wav`: 7 days (O-2), then deleted; transcript rows keep `audio_sha256` only.

## 8. Backups & integrity

- Daily at first idle ≥ 5 min: `VACUUM INTO 'data\backups\memory-YYYYMMDD-HHMM.sqlite'`; keep 14 daily, 8 weekly (weekly = Sunday's).
- Weekly `PRAGMA integrity_check`; on failure: speak/notify, set store read-only, keep serving retrieval, refuse commits until user restores from backup via `lucca-admin restore <file>`.
- `lucca-admin export --format jsonl` dumps memories + envelopes for user inspection (privacy/transparency requirement).
