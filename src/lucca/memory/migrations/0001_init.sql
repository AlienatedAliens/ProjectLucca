-- Spec 04 §2 — Initial schema migration 0001

CREATE TABLE IF NOT EXISTS schema_migrations(
  version INTEGER PRIMARY KEY,
  applied_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance_envelopes(
  entry_id        TEXT PRIMARY KEY,
  provenance      TEXT NOT NULL CHECK(provenance IN ('USER_EXPLICIT','USER_EXPLICIT_LOWCONF','USER_DERIVED','TOOL_VERIFIED','TOOL_CONTENT_UNTRUSTED','LISP_ASSERTION')),
  kind            TEXT NOT NULL,
  signer_id       TEXT NOT NULL,
  signature       TEXT NOT NULL,
  content_sha256  TEXT NOT NULL,
  nonce           TEXT NOT NULL,
  created_at      REAL NOT NULL,
  trace_id        TEXT NOT NULL,
  session_id      TEXT NOT NULL,
  asr_model       TEXT,
  asr_avg_logprob REAL,
  audio_sha256    TEXT,
  tool_name       TEXT,
  tool_call_id    TEXT,
  tool_exit_code  INTEGER,
  confidence      REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  payload_json    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_env_nonce ON provenance_envelopes(nonce, content_sha256);

CREATE TABLE IF NOT EXISTS memories(
  memory_id       INTEGER PRIMARY KEY,
  entry_id        TEXT NOT NULL UNIQUE REFERENCES provenance_envelopes(entry_id),
  content         TEXT NOT NULL,
  tokens_aux      TEXT NOT NULL DEFAULT '',
  kind            TEXT NOT NULL,
  created_at      REAL NOT NULL,
  valid_from      REAL NOT NULL,
  valid_to        REAL,
  superseded_by   INTEGER REFERENCES memories(memory_id),
  forgotten_at    REAL,
  importance      REAL NOT NULL DEFAULT 0.5,
  access_count    INTEGER NOT NULL DEFAULT 0,
  last_access     REAL
);
CREATE INDEX IF NOT EXISTS ix_mem_valid ON memories(valid_to, kind);

CREATE TRIGGER IF NOT EXISTS mem_bi_eligible BEFORE INSERT ON memories BEGIN
  SELECT RAISE(ABORT, 'provenance not memory-eligible')
  WHERE (SELECT provenance FROM provenance_envelopes WHERE entry_id = new.entry_id)
        NOT IN ('USER_EXPLICIT','USER_DERIVED','TOOL_VERIFIED','LISP_ASSERTION');
END;

CREATE TABLE IF NOT EXISTS memory_sources(
  memory_id       INTEGER NOT NULL REFERENCES memories(memory_id),
  source_entry_id TEXT NOT NULL REFERENCES provenance_envelopes(entry_id),
  PRIMARY KEY(memory_id, source_entry_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
  memory_id INTEGER PRIMARY KEY,
  embedding float[384] distance_metric=cosine
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories USING fts5(
  content,
  tokens_aux,
  content='memories',
  content_rowid='memory_id',
  tokenize="unicode61 remove_diacritics 2 tokenchars '_'"
);

CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
  INSERT INTO fts_memories(rowid, content, tokens_aux) VALUES (new.memory_id, new.content, new.tokens_aux);
END;

CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
  INSERT INTO fts_memories(fts_memories, rowid, content, tokens_aux) VALUES ('delete', old.memory_id, old.content, old.tokens_aux);
END;

CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE OF content, tokens_aux ON memories BEGIN
  INSERT INTO fts_memories(fts_memories, rowid, content, tokens_aux) VALUES ('delete', old.memory_id, old.content, old.tokens_aux);
  INSERT INTO fts_memories(rowid, content, tokens_aux) VALUES (new.memory_id, new.content, new.tokens_aux);
END;

CREATE TABLE IF NOT EXISTS kg_entities(
  entity_id       INTEGER PRIMARY KEY,
  canonical       TEXT NOT NULL UNIQUE,
  type            TEXT NOT NULL DEFAULT 'thing',
  created_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kg_aliases(
  alias           TEXT PRIMARY KEY,
  entity_id       INTEGER NOT NULL REFERENCES kg_entities(entity_id)
);

CREATE TABLE IF NOT EXISTS kg_edges(
  edge_id         INTEGER PRIMARY KEY,
  s               INTEGER NOT NULL REFERENCES kg_entities(entity_id),
  p               TEXT NOT NULL,
  o               INTEGER NOT NULL REFERENCES kg_entities(entity_id),
  memory_id       INTEGER NOT NULL REFERENCES memories(memory_id),
  valid_from      REAL NOT NULL,
  valid_to        REAL,
  recorded_at     REAL NOT NULL,
  confidence      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_edge_sp ON kg_edges(s, p, valid_to);
CREATE INDEX IF NOT EXISTS ix_edge_o  ON kg_edges(o, valid_to);

CREATE TABLE IF NOT EXISTS tool_contents(
  content_id      INTEGER PRIMARY KEY,
  entry_id        TEXT REFERENCES provenance_envelopes(entry_id),
  trace_id        TEXT NOT NULL,
  tool_name       TEXT NOT NULL,
  body            TEXT NOT NULL,
  sha256          TEXT NOT NULL,
  created_at      REAL NOT NULL,
  expires_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_confirmations(
  pending_id      INTEGER PRIMARY KEY,
  kind            TEXT NOT NULL,
  payload_json    TEXT NOT NULL,
  created_at      REAL NOT NULL,
  expires_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_nonces(
  nonce           TEXT NOT NULL,
  content_sha256  TEXT NOT NULL,
  seen_at         REAL NOT NULL,
  PRIMARY KEY(nonce, content_sha256)
);

CREATE TABLE IF NOT EXISTS memory_audit(
  audit_id        INTEGER PRIMARY KEY,
  ts              REAL NOT NULL,
  kind            TEXT NOT NULL,
  reason          TEXT,
  provenance      TEXT,
  trace_id        TEXT,
  entry_id        TEXT,
  content_sha256  TEXT
);

CREATE TABLE IF NOT EXISTS task_journal(
  task_id         TEXT PRIMARY KEY,
  opened_at       REAL NOT NULL,
  closed_at       REAL,
  outcome         TEXT
);
