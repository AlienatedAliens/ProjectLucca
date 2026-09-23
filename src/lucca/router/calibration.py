"""
Project Lucca — Production Router Calibration & Conformal Guard Fitting
Spec 06 §7, ADR-007, WO-15 Phase 2
"""

from __future__ import annotations

import json
from typing import Final

import numpy as np
from numpy.typing import NDArray
import structlog

from lucca.core.exceptions import InsufficientCalibration
from lucca.memory.db import DatabaseManager
from lucca.router.conformal import ConformalGuard

logger = structlog.get_logger(__name__)

CLASS_ORDER: Final[tuple[str, str, str]] = ("RULE", "LLM", "CLARIFY")


def load_labelled_decisions(
    db: DatabaseManager, limit: int = 500
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """
    Pull calibration pairs from the `decisions` table. Deterministic, no LLM.
    Row is usable iff: probabilities_json is non-null and parses to all three CLASS_ORDER keys,
                       fallback_applied == 0 (abstentions carry no ground truth about the right class).
    Label rule:
      action == "RULE" and tool_ok == 1          -> 0 (RULE was right)
      action == "RULE" and tool_ok == 0          -> 1 (RULE was wrong; LLM should have handled it)
      action == "LLM" and user_interrupted == 0 -> 1
      action == "CLARIFY"                        -> 2
      anything else                              -> skip
    Returns (probs[n,3], labels[n]). n may be 0.
    """
    probs_list: list[list[float]] = []
    labels_list: list[int] = []

    with db.read_cursor() as cur:
        cur.execute(
            """
            SELECT action, tool_ok, user_interrupted, fallback_applied, probabilities_json
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

        # Label rule
        if action == "RULE" and tool_ok == 1:
            label = 0
        elif action == "RULE" and tool_ok == 0:
            label = 1
        elif action == "LLM" and (user_interrupted == 0 or user_interrupted is False):
            label = 1
        elif action == "CLARIFY":
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
