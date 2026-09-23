"""
Project Lucca — Shared Decision Seeding Test Helper
WO-15 §4.4
"""

from __future__ import annotations

import json
import time
from typing import Final

from lucca.memory.db import DatabaseManager

_DEFAULT_PROBS: Final[dict[str, float]] = {"RULE": 1.0, "LLM": 0.0, "CLARIFY": 0.0}


def _insert_decision(
    db: DatabaseManager,
    decision_id: str,
    intent: str,
    transcript: str,
    tool_name: str | None = None,
    args: dict[str, object] | None = None,
    tool_ok: int = 1,
    ts: float | None = None,
    action: str | None = None,
    probabilities: dict[str, float] | None = _DEFAULT_PROBS,
    fallback_applied: int = 0,
    user_interrupted: int = 0,
) -> None:
    now = ts if ts is not None else time.time()
    features: dict[str, object] = {
        "transcript": transcript,
        "transcript_lower": transcript.lower(),
        "intent": intent,
        "intent_conf": 0.95 if tool_ok else 0.50,
        "entities": {},
        "hour_local": 10,
        "weekday": 2,
        "apps_running": [],
        "session_turns": 1,
        "mode": "transcript",
    }
    if args and "app" in args:
        features["entities"] = {"app": [str(args["app"])]}
    elif args and "path" in args:
        features["entities"] = {"file": [str(args["path"])]}

    tool_calls: list[dict[str, object]] = []
    if tool_name and args is not None:
        tool_calls.append({"tool": tool_name, "args": args, "call_id": f"call-{decision_id}"})

    act = action if action is not None else ("RULE" if tool_ok else "LLM")
    probs_str = json.dumps(probabilities)

    with db.get_writer() as cur:
        cur.execute(
            """
            INSERT INTO decisions(
                decision_id, trace_id, session_id, ts, features_json, action,
                probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                user_interrupted, interrupted_after_ms, counterfactual_rule_fired
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                f"trace-{decision_id}",
                "session-proof",
                now,
                json.dumps(features),
                act,
                probs_str,
                json.dumps([act]),
                fallback_applied,
                250,
                "heuristic-1.0",
                "ACT_THEN_NARRATE" if act == "RULE" else "FULL_LOOP",
                json.dumps(tool_calls) if tool_calls else None,
                tool_ok,
                150.0,
                user_interrupted,
                0.0,
                0,
            ),
        )
