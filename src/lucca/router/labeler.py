"""
Project Lucca — Ground-Truth Decision Auto-Labeling Engine
Spec 06 §4
"""

import re
import time
from typing import Final

import structlog

from lucca.core.schemas import (
    DecisionLabel,
    DecisionLabelReason,
    DecisionRecord,
    RouteAction,
)
from lucca.memory.db import DatabaseManager

logger = structlog.get_logger(__name__)

NEGATION_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^(no|nope|wrong|not\s+that|that's\s+not|stop|undo|cancel)\b",
    re.IGNORECASE,
)


def derive_label(
    current: DecisionRecord,
    *,
    next_transcript: str | None = None,
    next_intent: str | None = None,
    next_intent_conf: float = 0.0,
    user_interrupted: bool = False,
    interrupted_after_ms: float | None = None,
    tool_ok: bool | None = None,
    confirm_declined: bool = False,
    matching_rule_planned_identically: bool = False,
    time_to_next_turn_s: float | None = None,
) -> tuple[DecisionLabel, DecisionLabelReason]:
    """
    Derives ground truth label for a decision per Spec 06 §4:
    Priority 1: User barged in <= 1.5 s after playback started -> NEG (early_bargein)
    Priority 2: Confirm flow answered 'no' -> INDETERMINATE (user_declined)
    Priority 3: Next transcript matches negation lexicon -> NEG (explicit_negation)
    Priority 4: Any tool call ok=False (timeout, non-zero exit, schema error) -> NEG (tool_failed)
    Priority 5: Route was LLM and rule planned identically -> NEG (rule_would_match)
    Priority 6: Route was RULE and user re-asked same intent <= 30 s -> NEG (rule_wrong)
    Priority 7: Route was CLARIFY and next turn had intent_conf >= 0.6 same intent
                -> POS (clarify_useful)
    Priority 8: Otherwise -> POS (implicit_ok)
    """
    effective_interrupted = user_interrupted or current.user_interrupted
    effective_interrupted_ms = (
        interrupted_after_ms if interrupted_after_ms is not None else current.interrupted_after_ms
    )
    effective_tool_ok = tool_ok if tool_ok is not None else current.tool_ok

    # Priority 1: Early barge-in (<= 1500 ms)
    if (
        effective_interrupted
        and effective_interrupted_ms is not None
        and effective_interrupted_ms <= 1500.0
    ):
        return DecisionLabel.NEG, DecisionLabelReason.EARLY_BARGEIN

    # Priority 2: User declined confirmation (answering 'no' to confirmation prompt)
    if confirm_declined:
        return DecisionLabel.INDETERMINATE, DecisionLabelReason.USER_DECLINED

    # Priority 3: Explicit negation in next transcript (unsolicited correction)
    if next_transcript and NEGATION_REGEX.search(next_transcript.strip()):
        return DecisionLabel.NEG, DecisionLabelReason.EXPLICIT_NEGATION

    # Priority 4: Tool failure
    if effective_tool_ok is False:
        return DecisionLabel.NEG, DecisionLabelReason.TOOL_FAILED

    # Priority 5: Route was LLM but an active/quarantine rule would have planned identically
    if current.decision.action == RouteAction.LLM and matching_rule_planned_identically:
        return DecisionLabel.NEG, DecisionLabelReason.RULE_WOULD_MATCH

    # Priority 6: Route was RULE and user re-asked same intent within 30 s
    if (
        current.decision.action == RouteAction.RULE
        and next_intent is not None
        and next_intent == current.features.intent
        and time_to_next_turn_s is not None
        and time_to_next_turn_s <= 30.0
    ):
        return DecisionLabel.NEG, DecisionLabelReason.RULE_WRONG

    # Priority 7: Route was CLARIFY and user clarified same intent with high confidence
    if (
        current.decision.action == RouteAction.CLARIFY
        and next_intent is not None
        and next_intent == current.features.intent
        and next_intent_conf >= 0.60
    ):
        return DecisionLabel.POS, DecisionLabelReason.CLARIFY_USEFUL

    # Priority 8: Default implicit success
    return DecisionLabel.POS, DecisionLabelReason.IMPLICIT_OK


def persist_decision_label(
    db: DatabaseManager,
    decision_id: str,
    label: DecisionLabel,
    reason: DecisionLabelReason | str,
    labeled_at: float | None = None,
) -> None:
    """Stores the derived label into SQLite decision_labels table."""
    current_time = labeled_at if labeled_at is not None else time.time()
    reason_str = reason.value if isinstance(reason, DecisionLabelReason) else str(reason)

    writer = db.get_writer()
    writer.execute(
        """
        INSERT INTO decision_labels(decision_id, label, reason, labeled_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(decision_id) DO UPDATE SET
            label = excluded.label,
            reason = excluded.reason,
            labeled_at = excluded.labeled_at
        """,
        (decision_id, label.value, reason_str, current_time),
    )
    logger.debug(
        "decision_label_persisted",
        decision_id=decision_id,
        label=label.value,
        reason=reason_str,
    )


def check_data_volume_gate(
    db: DatabaseManager,
) -> tuple[bool, str, dict[str, int | float]]:
    """
    Evaluates data-volume criteria for Phase 6 eligibility per Spec 06 §5:
    - Total labelled decisions >= 600
    - Chronological test split (newest 100) has >= 30 per class (RULE, LLM, CLARIFY)
    - Distinct sessions >= 20
    - Span >= 14 days (1,209,600 seconds)
    """
    with db.read_cursor() as cur:
        # Total labelled
        cur.execute(
            """
            SELECT count(*), count(distinct d.session_id), min(d.ts), max(d.ts)
            FROM decisions d
            JOIN decision_labels l ON d.decision_id = l.decision_id
            """
        )
        row = cur.fetchone()
        total_labelled = int(row[0]) if row and row[0] is not None else 0
        distinct_sessions = int(row[1]) if row and row[1] is not None else 0
        min_ts = float(row[2]) if row and row[2] is not None else 0.0
        max_ts = float(row[3]) if row and row[3] is not None else 0.0
        span_days = (max_ts - min_ts) / 86400.0

        # Class counts in chronological test split (newest 100)
        cur.execute(
            """
            SELECT d.action, count(*)
            FROM (
                SELECT d.decision_id, d.action
                FROM decisions d
                JOIN decision_labels l ON d.decision_id = l.decision_id
                ORDER BY d.ts DESC
                LIMIT 100
            ) d
            GROUP BY d.action
            """
        )
        test_classes = {str(r[0]): int(r[1]) for r in cur.fetchall()}

    stats: dict[str, int | float] = {
        "total_labelled": total_labelled,
        "distinct_sessions": distinct_sessions,
        "span_days": round(span_days, 1),
        "test_rule_count": test_classes.get("RULE", 0),
        "test_llm_count": test_classes.get("LLM", 0),
        "test_clarify_count": test_classes.get("CLARIFY", 0),
    }

    is_eligible = (
        total_labelled >= 600
        and distinct_sessions >= 20
        and span_days >= 14.0
        and test_classes.get("RULE", 0) >= 30
        and test_classes.get("LLM", 0) >= 30
        and test_classes.get("CLARIFY", 0) >= 30
    )

    status = "eligible" if is_eligible else "blocked"
    return is_eligible, status, stats
