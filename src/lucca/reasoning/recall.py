"""
Project Lucca — Non-Parametric Experience Bank Recall
Spec 06 §4 (C1 Recall Path), Spec 1.1.2 §6.2
Deterministic lookup of past interaction episodes from SQLite decisions and
execution_triples tables without LLM inference.
"""

from __future__ import annotations

import json
import re
from typing import Final

import structlog
from pydantic import JsonValue

from lucca.core.schemas import RecallEpisode
from lucca.memory.db import DatabaseManager

logger = structlog.get_logger(__name__)

RECALL_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "about",
        "been",
        "before",
        "did",
        "doing",
        "earlier",
        "ever",
        "for",
        "happened",
        "have",
        "last",
        "recently",
        "say",
        "session",
        "tell",
        "that",
        "this",
        "time",
        "were",
        "what",
        "when",
        "with",
        "wrong",
        "you",
    }
)


def tokenize_query(query_text: str) -> list[str]:
    """Tokenize query text into lowercase terms >= 3 chars, filtering stop words."""
    if not query_text.strip():
        return []
    return [
        t.lower()
        for t in re.findall(r"\b[a-zA-Z0-9_\-.]+\b", query_text)
        if len(t) >= 3 and t.lower() not in RECALL_STOP_WORDS
    ]


def recall_past_episodes(
    db: DatabaseManager,
    query_text: str,
    limit: int = 5,
) -> list[RecallEpisode]:
    """
    C1 Experience Bank Recall: deterministic retrieval of past interaction episodes
    from SQLite decisions and execution_triples tables without any LLM inference.
    """
    if not query_text.strip():
        return []

    tokens = tokenize_query(query_text)
    if not tokens:
        return []

    candidates: list[RecallEpisode] = []

    try:
        with db.read_cursor() as cur:
            # 1. Query decisions table
            cur.execute(
                """
                SELECT decision_id, features_json, action, executed_path,
                       tool_calls_json, tool_ok, ts
                FROM decisions
                ORDER BY ts DESC
                LIMIT 100
                """
            )
            for did, feat_raw, act, exec_p, tc_raw, tok, ts in cur.fetchall():
                transcript = ""
                intent = ""
                if feat_raw:
                    try:
                        f_dict = json.loads(feat_raw) if isinstance(feat_raw, str) else {}
                        if isinstance(f_dict, dict):
                            transcript = str(f_dict.get("transcript", ""))
                            intent = str(f_dict.get("intent", ""))
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        logger.debug("recall_features_json_parse_error", error=str(exc))

                target_str = f"{transcript} {intent} {act} {exec_p or ''} {tc_raw or ''}".lower()
                score = sum(1 for t in tokens if t in target_str)

                if score > 0:
                    if tok is True or tok == 1:
                        tok_str = "succeeded"
                    elif tok is False or tok == 0:
                        tok_str = "failed"
                    else:
                        tok_str = "unverified"

                    summary = (
                        f"Historical turn '{transcript}': routed {act} via {exec_p} ({tok_str})"
                    )

                    tool_calls_obj: JsonValue = None
                    if tc_raw and isinstance(tc_raw, str):
                        try:
                            tool_calls_obj = json.loads(tc_raw)
                        except (json.JSONDecodeError, TypeError, ValueError) as exc:
                            logger.debug("recall_tool_calls_json_parse_error", error=str(exc))

                    payload: dict[str, JsonValue] = {
                        "transcript": transcript,
                        "intent": intent,
                        "action": str(act or ""),
                        "executed_path": str(exec_p or ""),
                        "tool_calls": tool_calls_obj,
                        "tool_ok": bool(tok) if tok is not None else None,
                    }

                    candidates.append(
                        RecallEpisode(
                            source="decisions",
                            record_id=str(did),
                            ts=float(ts or 0.0),
                            match_score=score,
                            tokens_total=len(tokens),
                            summary=summary,
                            payload=payload,
                        )
                    )

            # 2. Query execution_triples table
            cur.execute(
                """
                SELECT triple_id, proposal_json, decision_json, outcome_json, created_at
                FROM execution_triples
                ORDER BY created_at DESC
                LIMIT 50
                """
            )
            for tr_id, prop_j, dec_j, out_j, cat_ts in cur.fetchall():
                target_str = f"{prop_j} {dec_j} {out_j}".lower()
                score = sum(1 for t in tokens if t in target_str)
                if score > 0:
                    prop_obj: JsonValue = None
                    dec_obj: JsonValue = None
                    out_obj: JsonValue = None
                    try:
                        prop_obj = json.loads(prop_j) if isinstance(prop_j, str) else None
                        dec_obj = json.loads(dec_j) if isinstance(dec_j, str) else None
                        out_obj = json.loads(out_j) if isinstance(out_j, str) else None
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        logger.debug("recall_triples_json_parse_error", error=str(exc))

                    summary = f"Execution action in triple {tr_id}: {out_j}"
                    payload_triple: dict[str, JsonValue] = {
                        "triple_id": str(tr_id),
                        "proposal": prop_obj,
                        "decision": dec_obj,
                        "outcome": out_obj,
                    }

                    candidates.append(
                        RecallEpisode(
                            source="execution_triples",
                            record_id=str(tr_id),
                            ts=float(cat_ts or 0.0),
                            match_score=score,
                            tokens_total=len(tokens),
                            summary=summary,
                            payload=payload_triple,
                        )
                    )

        candidates.sort(key=lambda ep: (ep.match_score, ep.ts), reverse=True)
        return candidates[:limit]
    except Exception as exc:  # noqa: BLE001
        logger.warning("recall_episodes_failed", error=str(exc))
        return []
