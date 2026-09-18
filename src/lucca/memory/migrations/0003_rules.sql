-- Migration 0003: Rule States & Regression Cases Persistence (Spec 05 §9, F-REAS-002)

CREATE TABLE IF NOT EXISTS rule_states (
    rule_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source_canonical TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    success_clusters_json TEXT NOT NULL DEFAULT '[]',
    snapshots_json TEXT NOT NULL DEFAULT '[]',
    failure_count INTEGER NOT NULL DEFAULT 0,
    demotion_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    promoted_at REAL,
    demoted_at REAL,
    retired_at REAL,
    user_retired INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rule_states_status ON rule_states(status);

CREATE TABLE IF NOT EXISTS regression_cases (
    case_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL REFERENCES rule_states(rule_id),
    state_json TEXT NOT NULL,
    expected_plan_json TEXT NOT NULL,
    captured_at REAL NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_regression_cases_rule ON regression_cases(rule_id);
