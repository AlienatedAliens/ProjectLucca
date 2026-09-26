-- Migration 0006: Autobiographical Memory, Provenance Split & Review Queue (Spec D-MEM-04, Rung A1)

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
  tool_name, tool_call_id, tool_exit_code, confidence, payload_json,
  CASE
    WHEN provenance IN ('TOOL_CONTENT_UNTRUSTED', 'ASSISTANT_UTTERANCE', 'ASSISTANT_BELIEF') THEN 0
    ELSE 1
  END AS grounding_eligible
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
          'INFERRED',
          'ASSISTANT_UTTERANCE',
          'ASSISTANT_ACTION',
          'ASSISTANT_BELIEF',
          'COHERENCE_BREACH'
        );
END;

CREATE TABLE IF NOT EXISTS review_queue (
  review_id           TEXT PRIMARY KEY,
  belief_id           INTEGER REFERENCES memories(memory_id),
  proposed_content    TEXT NOT NULL,
  proposed_confidence REAL NOT NULL,
  reason_entry_id     TEXT NOT NULL REFERENCES provenance_envelopes(entry_id),
  trigger_reason      TEXT NOT NULL,
  created_at          REAL NOT NULL,
  status              TEXT NOT NULL CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED')),
  decided_at          REAL,
  decided_by          TEXT
);
CREATE INDEX IF NOT EXISTS ix_review_queue_status ON review_queue(status);

CREATE TABLE IF NOT EXISTS review_required_topics (
  topic               TEXT PRIMARY KEY,
  created_at          REAL NOT NULL
);

PRAGMA foreign_keys = ON;
