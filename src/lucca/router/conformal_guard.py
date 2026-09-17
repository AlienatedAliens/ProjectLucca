"""
Project Lucca — Conformal Prediction Guard & Safe Fallback
Computes distribution-free prediction sets and safely escalates ambiguous queries.
"""

from typing import List, Dict
from lucca.core.schemas import RouteAction

class ConformalPredictionGuard:
    def __init__(self, alpha: float = 0.05, quantile_threshold: float = 0.82):
        self._alpha = alpha
        self._quantile_threshold = quantile_threshold

    def compute_prediction_set(self, class_probabilities: Dict[RouteAction, float]) -> List[RouteAction]:
        """
        Constructs the conformal prediction set C(x) given calibrated class probabilities.
        C(x) = { y in Y : (1 - P(y|x)) <= quantile_threshold }
        """
        prediction_set = []
        for action, prob in class_probabilities.items():
            non_conformity = 1.0 - prob
            if non_conformity <= self._quantile_threshold:
                prediction_set.append(action)
        return prediction_set

    def resolve_action(self, class_probabilities: Dict[RouteAction, float]) -> RouteAction:
        """
        Applies safe fallback decision rule:
        - If exactly 1 action is in the prediction set, dispatch that action.
        - If |C(x)| > 1 (high ambiguity) or |C(x)| == 0 (out-of-distribution),
          fall back immediately to SAFE_FALLBACK_ESCALATE.
        """
        pred_set = self.compute_prediction_set(class_probabilities)
        if len(pred_set) == 1:
            return pred_set[0]
        return RouteAction.SAFE_FALLBACK_ESCALATE
