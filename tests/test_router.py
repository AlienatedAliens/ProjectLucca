"""
Project Lucca — Executive Router & Conformal Guard Mechanical Tests
Spec 06 §8 (T-RTR-01, T-RTR-03, T-RTR-06, T-RTR-07, T-RTR-08)
"""

from pathlib import Path

import numpy as np
import pytest

from lucca.core.exceptions import InsufficientCalibration
from lucca.router.conformal import ConformalGuard
from lucca.router.heuristic import HeuristicRouter


def test_t_rtr_01_word_boundary_adversarial_lexicon():
    """T-RTR-01: Adversarial fixtures must not trigger false positive launch_app."""
    router = HeuristicRouter()

    # Adversarial cases that must NOT match launch_app
    adversarial = [
        "start with the second file",
        "run over to the store",
        "open up about your feelings",
        "start off by reading chapter one",
    ]
    for text in adversarial:
        intent, _, _ = router.classify_intent(text)
        assert intent != "launch_app", (
            f"Adversarial text '{text}' incorrectly classified as launch_app"
        )

    # Positive cases that MUST match launch_app
    positives = [
        "open calculator",
        "launch notepad please",
        "start the browser",
        "run calc",
    ]
    for text in positives:
        intent, _, entities = router.classify_intent(text)
        assert intent == "launch_app", f"Positive text '{text}' failed to classify as launch_app"
        assert len(entities["app"]) >= 1


def test_t_rtr_03_decision_logging(tmp_path: Path):
    """T-RTR-03: route() logs decision record to JSONL."""
    log_file = tmp_path / "decisions.jsonl"
    router = HeuristicRouter(log_path=log_file)

    decision = router.route("open calculator", any_active_rule_fired=False)
    assert decision.action == "LLM"
    assert log_file.exists()

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "open calculator" in lines[0]
    assert "launch_app" in lines[0]


def test_t_rtr_06_insufficient_calibration():
    """T-RTR-06: ConformalGuard.fit with n=5, alpha=0.05 raises InsufficientCalibration."""
    guard = ConformalGuard(alpha=0.05)
    cal_probs = np.ones((5, 3)) / 3.0
    cal_labels = np.array([0, 1, 2, 0, 1])

    with pytest.raises(InsufficientCalibration):
        guard.fit(cal_probs, cal_labels)


def test_t_rtr_07_synthetic_conformal_coverage():
    """T-RTR-07: Synthetic 3-class data (n_cal=200): empirical coverage near 1 - alpha."""
    alpha = 0.10
    guard = ConformalGuard(alpha=alpha)

    rng = np.random.default_rng(42)
    n_cal = 200
    # Simulate well-calibrated probabilities
    cal_probs = rng.dirichlet((5, 3, 2), size=n_cal)
    cal_labels = np.array([rng.choice(3, p=cal_probs[i]) for i in range(n_cal)])

    guard.fit(cal_probs, cal_labels)
    assert guard.q_hat is not None

    # Test coverage on 500 test points
    n_test = 500
    test_probs = rng.dirichlet((5, 3, 2), size=n_test)
    test_labels = np.array([rng.choice(3, p=test_probs[i]) for i in range(n_test)])

    covered = 0
    for i in range(n_test):
        pred_set = guard.predict_set(test_probs[i])
        if test_labels[i] in pred_set:
            covered += 1

    empirical_coverage = covered / n_test
    # Check coverage is within [1 - alpha - 0.05, 1 - alpha + 0.08]
    assert (1.0 - alpha - 0.05) <= empirical_coverage <= 1.0


def test_t_rtr_08_set_size_fallback_policy():
    """T-RTR-08: Set size != 1 forces fallback to LLM."""
    guard = ConformalGuard(alpha=0.10)
    # Manually set q_hat to trigger set size of 2
    guard.q_hat = 0.60
    probs = np.array([0.45, 0.45, 0.10])
    # 1 - 0.45 = 0.55 <= 0.60 -> indices 0 and 1 are in set
    action, pred_set, fallback = guard.decide(probs)
    assert len(pred_set) == 2
    assert fallback is True
    assert action == "LLM"
