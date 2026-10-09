"""
Project Lucca — Traceback Divergence Guard (Module 9, WO-31)
D-REAS-11, D-AUD-01

Monitors search traces, turn convergence loops, and reasoning chains to detect:
1. State-hash recurrence (cycles & oscillations of length 1..k).
2. Repetitive drift and token/state stagnation.
3. Traceback error entropy explosion without progress.
4. Token budget and search depth runaway limits.

Provides real-time branch pruning for MCTS and orchestrator loop abortion.
Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import math
from typing import Final
from collections import Counter

from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_MAX_RECURRENCE: Final[int] = 3
DEFAULT_MAX_STEPS: Final[int] = 64
DEFAULT_WINDOW_SIZE: Final[int] = 10
DEFAULT_SIMILARITY_THRESHOLD: Final[float] = 0.95


class DivergenceReason(str, Enum):
    """Classification of detected search/loop divergence."""

    STATE_CYCLE = "state_cycle"
    REPETITIVE_DRIFT = "repetitive_drift"
    ERROR_ENTROPY_EXPLOSION = "error_entropy_explosion"
    TOKEN_RAMBLE_LIMIT = "token_ramble_limit"


class DivergenceReport(BaseModel):
    """Evaluation result for a search trace or convergence step."""

    diverged: bool
    reason: DivergenceReason | None = None
    cycle_count: int = 0
    entropy: float = 0.0
    detail: str = ""
    step_count: int = 0


def hash_state(state_repr: str) -> str:
    """Computes a normalized deterministic SHA-256 state hash."""
    normalized = " ".join(state_repr.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def compute_shannon_entropy(items: list[str]) -> float:
    """Computes Shannon entropy H(X) in bits over a collection of discrete items."""
    if not items:
        return 0.0
    total = len(items)
    counts = Counter(items)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def detect_periodic_cycle(
    sequence: list[str],
    min_period: int = 1,
    max_period: int = 5,
    min_repeats: int = 2,
) -> tuple[bool, int, list[str]]:
    """
    Detects periodic repetitions at the tail of a sequence.
    Returns (has_cycle, period_length, repeated_pattern).
    """
    n = len(sequence)
    if n < min_period * min_repeats:
        return False, 0, []

    for period in range(min_period, min(max_period + 1, n // min_repeats + 1)):
        pattern = sequence[-period:]
        repeats = 0
        idx = n - period
        while idx >= 0:
            if sequence[idx : idx + period] == pattern:
                repeats += 1
                idx -= period
            else:
                break
        if repeats >= min_repeats:
            return True, period, pattern

    return False, 0, []


def jaccard_token_similarity(s1: str, s2: str) -> float:
    """Computes token Jaccard similarity between two strings."""
    tokens1 = set(s1.split())
    tokens2 = set(s2.split())
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


class TracebackDivergenceGuard:
    """
    Guards reasoning search trees and turn convergence loops against
    degenerative cycling, repetition stagnation, and error entropy explosion.
    """

    def __init__(
        self,
        max_recurrence: int = DEFAULT_MAX_RECURRENCE,
        max_steps: int = DEFAULT_MAX_STEPS,
        window_size: int = DEFAULT_WINDOW_SIZE,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        self.max_recurrence = max_recurrence
        self.max_steps = max_steps
        self.window_size = window_size
        self.similarity_threshold = similarity_threshold

        self._state_hashes: list[str] = []
        self._raw_states: list[str] = []
        self._error_signatures: list[str] = []
        self._entropy_history: list[float] = []
        self._step_count: int = 0

    @property
    def step_count(self) -> int:
        return self._step_count

    def reset(self) -> None:
        """Resets all tracking buffers."""
        self._state_hashes.clear()
        self._raw_states.clear()
        self._error_signatures.clear()
        self._entropy_history.clear()
        self._step_count = 0

    def record_step(
        self,
        state_repr: str,
        error_signature: str | None = None,
    ) -> DivergenceReport:
        """
        Records a single search or turn step and returns divergence diagnosis.
        """
        self._step_count += 1
        h = hash_state(state_repr)
        self._state_hashes.append(h)
        self._raw_states.append(state_repr)
        if error_signature:
            self._error_signatures.append(error_signature)

        # 1. Step Runaway Guard
        if self._step_count > self.max_steps:
            logger.warn("divergence_guard_step_limit_exceeded", steps=self._step_count)
            return DivergenceReport(
                diverged=True,
                reason=DivergenceReason.TOKEN_RAMBLE_LIMIT,
                step_count=self._step_count,
                detail=f"Exceeded maximum allowable search steps ({self.max_steps})",
            )

        # 2. State-Hash Exact Recurrence (Global and Periodic)
        hash_counts = Counter(self._state_hashes)
        recurrent_count = hash_counts[h]
        if recurrent_count >= self.max_recurrence:
            logger.warn(
                "divergence_guard_state_cycle_detected",
                state_hash=h,
                recurrence=recurrent_count,
            )
            return DivergenceReport(
                diverged=True,
                reason=DivergenceReason.STATE_CYCLE,
                cycle_count=recurrent_count,
                step_count=self._step_count,
                detail=f"State hash {h} repeated {recurrent_count} times (limit: {self.max_recurrence})",
            )

        # Check periodic cycle at tail (e.g. A -> B -> A -> B)
        has_periodic, period, pattern = detect_periodic_cycle(
            self._state_hashes, min_period=1, max_period=4, min_repeats=self.max_recurrence
        )
        if has_periodic:
            logger.warn(
                "divergence_guard_periodic_cycle_detected",
                period=period,
                pattern=pattern,
            )
            return DivergenceReport(
                diverged=True,
                reason=DivergenceReason.STATE_CYCLE,
                cycle_count=len(pattern),
                step_count=self._step_count,
                detail=f"Periodic cycle detected of period {period} repeating >= {self.max_recurrence} times",
            )

        # 3. Repetitive Drift / Stagnation
        if len(self._raw_states) >= 3:
            recent = self._raw_states[-3:]
            sim_1_2 = jaccard_token_similarity(recent[0], recent[1])
            sim_2_3 = jaccard_token_similarity(recent[1], recent[2])
            if sim_1_2 >= self.similarity_threshold and sim_2_3 >= self.similarity_threshold:
                return DivergenceReport(
                    diverged=True,
                    reason=DivergenceReason.REPETITIVE_DRIFT,
                    step_count=self._step_count,
                    detail=f"Consecutive states stagnant with token similarity >= {self.similarity_threshold:.2f}",
                )

        # 4. Error Entropy Explosion / Stagnation
        if len(self._error_signatures) >= self.window_size:
            recent_errors = self._error_signatures[-self.window_size :]
            entropy = compute_shannon_entropy(recent_errors)
            self._entropy_history.append(entropy)

            # If all errors in window are identical (stuck in same crash loop)
            if len(set(recent_errors)) == 1:
                return DivergenceReport(
                    diverged=True,
                    reason=DivergenceReason.STATE_CYCLE,
                    cycle_count=self.window_size,
                    entropy=0.0,
                    step_count=self._step_count,
                    detail=f"Identical error signature repeated continuously across {self.window_size} steps",
                )

            # If entropy is persistently high and error count is maximal without progress
            if entropy > 2.5 and len(recent_errors) == self.window_size:
                return DivergenceReport(
                    diverged=True,
                    reason=DivergenceReason.ERROR_ENTROPY_EXPLOSION,
                    entropy=entropy,
                    step_count=self._step_count,
                    detail=f"Error signature entropy diverged ({entropy:.2f} bits) across window",
                )

        current_entropy = (
            compute_shannon_entropy(self._error_signatures[-self.window_size :])
            if self._error_signatures
            else 0.0
        )

        return DivergenceReport(
            diverged=False,
            reason=None,
            cycle_count=recurrent_count,
            entropy=current_entropy,
            detail="Normal convergence",
            step_count=self._step_count,
        )

    def should_prune(self, history: list[str]) -> bool:
        """
        Lightweight stateless check for MCTS branch pruning.
        Returns True if history exhibits cycling or excessive duplication.
        """
        if not history:
            return False
        if len(history) > self.max_steps:
            return True

        hashes = [hash_state(s) for s in history]
        counts = Counter(hashes)
        if any(c >= self.max_recurrence for c in counts.values()):
            return True

        has_cycle, _, _ = detect_periodic_cycle(
            hashes, min_period=1, max_period=4, min_repeats=self.max_recurrence
        )
        return has_cycle
