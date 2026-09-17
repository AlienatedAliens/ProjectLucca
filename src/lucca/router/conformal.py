"""
Project Lucca — Conformal Prediction Guard
Spec 06 §7, ADR-007
"""

import math

import numpy as np
from numpy.typing import NDArray

from lucca.core.exceptions import InsufficientCalibration


class ConformalGuard:
    """
    Split-conformal prediction set generator providing finite-sample coverage guarantees.
    Enforces that ambiguous sets (len != 1) fall back to the LLM path.
    """

    def __init__(self, alpha: float = 0.10) -> None:
        if not (0.0 < alpha < 1.0):
            raise ValueError(f"Alpha must be in (0, 1), got {alpha}")
        self.alpha = alpha
        self.q_hat: float | None = None

    def fit(self, cal_probs: NDArray[np.float64], cal_labels: NDArray[np.int64]) -> None:
        n = len(cal_labels)
        if n == 0 or n < math.ceil(1.0 / self.alpha) - 1:
            raise InsufficientCalibration(
                f"Calibration sample size {n} is too small for alpha {self.alpha}. "
                f"Requires n >= {math.ceil(1.0 / self.alpha) - 1}."
            )

        q_level = math.ceil((n + 1) * (1.0 - self.alpha)) / n
        if q_level > 1.0:
            raise InsufficientCalibration(
                f"Calculated quantile level {q_level:.4f} > 1.0 for n={n}, alpha={self.alpha}"
            )

        scores = 1.0 - cal_probs[np.arange(n), cal_labels]
        self.q_hat = float(np.quantile(scores, q_level, method="higher"))

    def predict_set(self, probs: NDArray[np.float64]) -> list[int]:
        if self.q_hat is None:
            raise RuntimeError("ConformalGuard must be fitted before calling predict_set()")
        return [k for k in range(len(probs)) if (1.0 - probs[k]) <= self.q_hat]

    def decide(
        self, probs: NDArray[np.float64], class_names: list[str] | None = None
    ) -> tuple[str, list[str], bool]:
        """
        Applies conformal decision policy:
        len(set) == 1 -> act with single predicted class, fallback_applied = False.
        len(set) != 1 -> fallback_applied = True, action = "LLM".
        """
        names = class_names if class_names is not None else ["RULE", "LLM", "CLARIFY"]
        set_indices = self.predict_set(probs)
        pred_set = [names[idx] for idx in set_indices]

        if len(pred_set) == 1:
            return pred_set[0], pred_set, False
        else:
            return "LLM", pred_set, True
