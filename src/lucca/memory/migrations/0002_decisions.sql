-- Migration 0002: Decision Telemetry, Vec Decisions & Auto-Labels (Spec 06 §3 & §4)

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    ts REAL NOT NULL,
    features_json TEXT NOT NULL,
    action TEXT NOT NULL,
    probabilities_json TEXT NOT NULL,
    prediction_set_json TEXT NOT NULL,
    fallback_applied INTEGER DEFAULT 0,
    elapsed_us INTEGER NOT NULL,
    router_version TEXT NOT NULL,
    executed_path TEXT NOT NULL,
    tool_calls_json TEXT,
    tool_ok INTEGER,
    llm_first_token_ms REAL,
    user_interrupted INTEGER DEFAULT 0,
    interrupted_after_ms REAL,
    counterfactual_rule_fired INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_decisions_trace ON decisions(trace_id);

CREATE VIRTUAL TABLE IF NOT EXISTS vec_decisions USING vec0(
    decision_id TEXT PRIMARY KEY,
    embedding float[384] distance_metric=cosine,
    chunk_size=256
);

CREATE TABLE IF NOT EXISTS decision_labels (
    decision_id TEXT PRIMARY KEY REFERENCES decisions(decision_id),
    label TEXT NOT NULL,
    reason TEXT NOT NULL,
    labeled_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decision_labels_label ON decision_labels(label);
