-- Migration 0007: Support INFERRED provenance in existing databases (WO-20 Phase 4)
-- Widens provenance_envelopes CHECK constraint to include 'INFERRED' and updates mem_bi_eligible trigger.
-- For new databases, 0001 and 0006 also declare 'INFERRED' for consistency, while this migration ensures
-- upgrades succeed on existing databases where 0001-0006 already executed.

PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS mem_bi_eligible;

CREATE TABLE IF NOT EXISTS provenance_envelopes_new (
  entry_id            TEXT PRIMARY KEY,
  provenance          TEXT NOT NULL CHECK(provenance IN (
                        'USER_EXPLICIT',
                        'USER_EXPLICIT_LOWCONF',
                        'USER_DERIVED',
                        'TOOL_VERIFIED',
                        'TOOL_CONTENT_UNTRUSTED',
                        'LISP_ASSERTION',
                        'LLM_INFERRED_ASSERTION',
                        'INFERRED',
                        'ASSISTANT_UTTERANCE',
                        'ASSISTANT_ACTION',
                        'ASSISTANT_BELIEF',
                        'COHERENCE_BREACH'
                      )),
  kind                TEXT NOT NULL,
  signer_id           TEXT NOT NULL,
  signature           TEXT NOT NULL,
  content_sha256      TEXT NOT NULL,
  nonce               TEXT NOT NULL,
  created_at          REAL NOT NULL,
  trace_id            TEXT NOT NULL,
  session_id          TEXT NOT NULL,
  asr_model           TEXT,
  asr_avg_logprob     REAL,
  audio_sha256        TEXT,
  tool_name           TEXT,
  tool_call_id        TEXT,
  tool_exit_code      INTEGER,
  confidence          REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  payload_json        TEXT NOT NULL,
  grounding_eligible  INTEGER NOT NULL DEFAULT 1 CHECK(grounding_eligible IN (0, 1))
);

INSERT INTO provenance_envelopes_new(
  entry_id, provenance, kind, signer_id, signature, content_sha256, nonce,
  created_at, trace_id, session_id, asr_model, asr_avg_logprob, audio_sha256,
  tool_name, tool_call_id, tool_exit_code, confidence, payload_json, grounding_eligible
)
SELECT
  entry_id, provenance, kind, signer_id, signature, content_sha256, nonce,
  created_at, trace_id, session_id, asr_model, asr_avg_logprob, audio_sha256,
  tool_name, tool_call_id, tool_exit_code, confidence, payload_json, grounding_eligible
FROM provenance_envelopes;

DROP TABLE provenance_envelopes;

ALTER TABLE provenance_envelopes_new RENAME TO provenance_envelopes;

CREATE UNIQUE INDEX IF NOT EXISTS ux_env_nonce ON provenance_envelopes(nonce, content_sha256);
CREATE INDEX IF NOT EXISTS ix_env_grounding ON provenance_envelopes(grounding_eligible);

CREATE TRIGGER mem_bi_eligible BEFORE INSERT ON memories BEGIN
  SELECT RAISE(ABORT, 'provenance not memory-eligible')
  WHERE (SELECT provenance FROM provenance_envelopes WHERE entry_id = new.entry_id)
        NOT IN (
          'USER_EXPLICIT',
          'USER_DERIVED',
          'TOOL_VERIFIED',
          'LISP_ASSERTION',
          'LLM_INFERRED_ASSERTION',
          'INFERRED',
          'ASSISTANT_UTTERANCE',
          'ASSISTANT_ACTION',
          'ASSISTANT_BELIEF',
          'COHERENCE_BREACH'
        );
END;

PRAGMA foreign_keys = ON;
