-- Migration 0004: Execution Triples Persistence (Spec §5, S1 Contract)

CREATE TABLE IF NOT EXISTS execution_triples (
    triple_id TEXT PRIMARY KEY,
    proposal_json TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    outcome_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_triples_created ON execution_triples(created_at);
