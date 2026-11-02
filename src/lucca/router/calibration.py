"""
Project Lucca — Production Router Calibration & Conformal Guard Fitting
Spec 06 §7, ADR-007, WO-15 Phase 2
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import numpy as np
import structlog
from numpy.typing import NDArray

from lucca.core.exceptions import InsufficientCalibration
from lucca.memory.db import DatabaseManager
from lucca.router.conformal import ConformalGuard

if TYPE_CHECKING:
    from lucca.router.heuristic import HeuristicRouter

logger = structlog.get_logger(__name__)

CLASS_ORDER: Final[tuple[str, str, str]] = ("RULE", "LLM", "CLARIFY")


def load_labelled_decisions(
    db: DatabaseManager, limit: int = 500
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """
    Pull calibration pairs from `decisions` joined with `decision_labels` (Spec 06 §4 & §7).
    Deterministic, no LLM.
    Row is usable iff: probabilities_json is non-null and parses to all three CLASS_ORDER keys,
                       fallback_applied == 0 (abstentions carry no ground truth).
    When an explicit ground-truth label exists in `decision_labels`, it takes precedence over
    the raw action heuristic so that failed CLARIFY or suboptimal LLM routes are not circularly
    treated as ground-truth successes.
    Returns (probs[n,3], labels[n]). n may be 0.
    """
    probs_list: list[list[float]] = []
    labels_list: list[int] = []

    with db.read_cursor() as cur:
        try:
            cur.execute(
                """
                SELECT d.action, d.tool_ok, d.user_interrupted, d.fallback_applied,
                       d.probabilities_json, dl.label, dl.reason
                FROM decisions d
                LEFT JOIN decision_labels dl ON d.decision_id = dl.decision_id
                WHERE d.probabilities_json IS NOT NULL
                  AND d.fallback_applied = 0
                ORDER BY d.ts DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.debug("calibration_decision_labels_join_fallback", error=str(exc))
            cur.execute(
                """
                SELECT action, tool_ok, user_interrupted, fallback_applied,
                       probabilities_json, NULL AS label, NULL AS reason
                FROM decisions
                WHERE probabilities_json IS NOT NULL
                  AND fallback_applied = 0
                ORDER BY ts DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()

    for row in rows:
        action = str(row[0]) if row[0] is not None else ""
        tool_ok = row[1]
        user_interrupted = row[2]
        fallback_applied = row[3]
        probs_raw = row[4]
        dl_label_raw = row[5] if len(row) > 5 else None
        dl_reason_raw = row[6] if len(row) > 6 else None

        if fallback_applied != 0:
            continue

        if not probs_raw or not isinstance(probs_raw, str):
            continue

        try:
            raw_dict = json.loads(probs_raw)
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(raw_dict, dict) or not all(k in raw_dict for k in CLASS_ORDER):
            continue

        try:
            vec = [float(raw_dict[k]) for k in CLASS_ORDER]
        except (TypeError, ValueError):
            continue

        label: int | None = None
        if dl_label_raw is not None:
            dl_label = str(dl_label_raw).strip().upper()
            dl_reason = str(dl_reason_raw or "").strip().lower()
            if dl_label == "INDETERMINATE":
                continue
            if dl_label in ("RULE", "0"):
                label = 0
            elif dl_label in ("LLM", "1"):
                label = 1
            elif dl_label in ("CLARIFY", "2"):
                label = 2
            elif dl_label == "POS":
                if action == "RULE":
                    label = 0
                elif action == "LLM":
                    label = 1
                elif action == "CLARIFY":
                    label = 2
            elif dl_label == "NEG":
                if dl_reason == "rule_would_match":
                    label = 0
                elif action in ("RULE", "CLARIFY"):
                    label = 1
                elif action == "LLM" and dl_reason in ("early_bargein", "explicit_negation"):
                    label = 2
                else:
                    continue

        if label is None:
            # Fallback to post-turn outcome columns when decision_labels has no entry
            if action == "RULE" and tool_ok == 1:
                label = 0
            elif action == "RULE" and tool_ok == 0:
                label = 1
            elif action == "LLM" and (user_interrupted == 0 or user_interrupted is False):
                label = 1
            elif action == "CLARIFY" and (user_interrupted == 0 or user_interrupted is False):
                label = 2
            else:
                continue

        probs_list.append(vec)
        labels_list.append(label)

    if not labels_list:
        return np.empty((0, 3), dtype=np.float64), np.empty(0, dtype=np.int64)

    return (
        np.array(probs_list, dtype=np.float64),
        np.array(labels_list, dtype=np.int64),
    )


def fit_guard_from_db(
    db: DatabaseManager, alpha: float = 0.10, min_samples: int = 30
) -> ConformalGuard | None:
    """
    Returns a fitted ConformalGuard, or None if fewer than min_samples usable rows
    or ConformalGuard.fit raises InsufficientCalibration. Never raises.
    Logs structlog event "conformal_guard_fit" with fitted: bool, n: int, q_hat: float | None.
    """
    probs, labels = load_labelled_decisions(db, limit=500)
    n = len(labels)
    if n < min_samples:
        logger.info("conformal_guard_fit", fitted=False, n=n, q_hat=None)
        return None

    guard = ConformalGuard(alpha=alpha)
    try:
        guard.fit(probs, labels)
        logger.info("conformal_guard_fit", fitted=True, n=n, q_hat=guard.q_hat)
        return guard
    except InsufficientCalibration:
        logger.info("conformal_guard_fit", fitted=False, n=n, q_hat=None)
        return None


fit_from_db = fit_guard_from_db


def evaluate_blind_classifier_routing(
    router: HeuristicRouter,
    queries: list[tuple[str, str]],
) -> dict[str, object]:
    """
    SPIKE-B evaluation mode: benchmarks 384-D NPU embedding + ConformalGuard routing
    with benchmark-specific regex patterns disabled (blind_classifier_only=True) vs
    full heuristic regex + embedding routing.
    Each item in queries is (transcript, expected_intent_or_domain).
    """
    if not queries:
        return {
            "total": 0,
            "blind_accuracy": 0.0,
            "full_accuracy": 0.0,
            "conformal_calibrated_rate": 0.0,
        }

    blind_hits = 0
    full_hits = 0
    calibrated_count = 0

    for text, expected in queries:
        exp_clean = expected.strip().lower()

        # 1. Blind classifier-only evaluation
        b_intent, _, _ = router.classify_intent(text, blind_classifier_only=True)
        b_dec = router.route(text, blind_classifier_only=True)
        if b_dec.calibrated:
            calibrated_count += 1
        if exp_clean in (
            b_intent.lower(),
            (b_dec.reasoning_domain or "").lower(),
            b_dec.action.value.lower(),
        ):
            blind_hits += 1

        # 2. Full heuristic + embedding evaluation
        f_intent, _, _ = router.classify_intent(text, blind_classifier_only=False)
        f_dec = router.route(text, blind_classifier_only=False)
        if exp_clean in (
            f_intent.lower(),
            (f_dec.reasoning_domain or "").lower(),
            f_dec.action.value.lower(),
        ):
            full_hits += 1

    n = len(queries)
    return {
        "total": n,
        "blind_hits": blind_hits,
        "blind_accuracy": round(blind_hits / n, 4),
        "full_hits": full_hits,
        "full_accuracy": round(full_hits / n, 4),
        "conformal_calibrated_rate": round(calibrated_count / n, 4),
    }
