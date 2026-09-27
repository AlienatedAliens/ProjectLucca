-- Migration 0008: Decision & TurnTrace FTS5 Index (ITEM-021)
-- Allows DiagnosisEngine to query in-session decision history via FTS5

CREATE VIRTUAL TABLE IF NOT EXISTS fts_decisions USING fts5(
    decision_id UNINDEXED,
    trace_id,
    transcript,
    intent,
    action,
    executed_path,
    tool_calls,
    error,
    tokenize="unicode61 remove_diacritics 2 tokenchars '_'"
);

CREATE TRIGGER IF NOT EXISTS trg_decisions_ai AFTER INSERT ON decisions BEGIN
    INSERT INTO fts_decisions(decision_id, trace_id, transcript, intent, action, executed_path, tool_calls, error)
    VALUES (
        new.decision_id,
        new.trace_id,
        coalesce(json_extract(new.features_json, '$.transcript'), ''),
        coalesce(json_extract(new.features_json, '$.intent'), ''),
        coalesce(new.action, ''),
        coalesce(new.executed_path, ''),
        coalesce(new.tool_calls_json, ''),
        ''
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_decisions_ad AFTER DELETE ON decisions BEGIN
    DELETE FROM fts_decisions WHERE decision_id = old.decision_id;
END;

-- Backfill any existing decisions
INSERT INTO fts_decisions(decision_id, trace_id, transcript, intent, action, executed_path, tool_calls, error)
SELECT
    decision_id,
    trace_id,
    coalesce(json_extract(features_json, '$.transcript'), ''),
    coalesce(json_extract(features_json, '$.intent'), ''),
    coalesce(action, ''),
    coalesce(executed_path, ''),
    coalesce(tool_calls_json, ''),
    ''
FROM decisions;
