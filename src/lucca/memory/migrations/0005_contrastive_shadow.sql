-- Migration 0005: Contrastive Shadow Logs (Spec §6.2, Rung L2, ModularRSI §3.3)

CREATE TABLE IF NOT EXISTS contrastive_shadow_logs (
    log_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    ts REAL NOT NULL,
    rule_plan_json TEXT NOT NULL,
    core_action_json TEXT NOT NULL,
    agreed INTEGER NOT NULL,
    rule_outcome_signal TEXT,
    core_outcome_signal TEXT
);

CREATE INDEX IF NOT EXISTS idx_contrastive_rule ON contrastive_shadow_logs(rule_id);
CREATE INDEX IF NOT EXISTS idx_contrastive_ts ON contrastive_shadow_logs(ts);
