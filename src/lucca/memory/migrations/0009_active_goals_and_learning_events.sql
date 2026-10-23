-- Migration 0009: Active Goals State Machine & Learning Events Ledger (WO-36 Milestone 36.2 & 36.3)
-- Implements first-class shared active goals and an auditable ledger for inner life learning events.

CREATE TABLE IF NOT EXISTS active_goals (
    goal_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'ABANDONED')),
    priority INTEGER NOT NULL DEFAULT 1,
    provenance TEXT NOT NULL CHECK (provenance IN ('USER_EXPLICIT', 'USER_DERIVED')),
    provenance_envelope_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_active_goals_status ON active_goals(status);
CREATE INDEX IF NOT EXISTS idx_active_goals_provenance ON active_goals(provenance);

CREATE TABLE IF NOT EXISTS learning_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'BELIEF_SUPERSEDED',
        'CONTRADICTION_RESOLVED',
        'RULE_QUARANTINED',
        'RULE_PROMOTED',
        'CEGIS_REPAIR_MYELINATED',
        'SKILL_MINED',
        'IDLE_PULSE_DISTILL'
    )),
    topic TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    provenance_envelope_id TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_learning_events_type ON learning_events(event_type);
CREATE INDEX IF NOT EXISTS idx_learning_events_topic ON learning_events(topic);
CREATE INDEX IF NOT EXISTS idx_learning_events_created ON learning_events(created_at);
