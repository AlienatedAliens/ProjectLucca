"""
Unit tests for Project Lucca v1.35.7 Phase 2 — Semantic Verifier Engine.
Spec 04 §3, Spec 11 §4, Gates: G-V1357-LATENCY, G-V1357-VERIFIER-NEG.
"""

import time
import unicodedata
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from lucca.core.schemas import VerificationResult, VerifierLabel
from lucca.ports import SemanticVerifierPort
from lucca.senses.verifier import (
    BoundedLRUPairCache,
    LocalSemanticVerifierPort,
    VerifierWorker,
)


def test_semantic_verifier_port_protocol_conformance() -> None:
    """Verifies that LocalSemanticVerifierPort conforms to SemanticVerifierPort."""
    worker = VerifierWorker()
    port = LocalSemanticVerifierPort(worker=worker)
    assert isinstance(port, SemanticVerifierPort)
    assert hasattr(port, "check_consistency")


def test_verifier_keyword_only_arguments() -> None:
    """Verifies that check_consistency strictly enforces keyword-only arguments (Trap 3 guard)."""
    worker = VerifierWorker()
    port = LocalSemanticVerifierPort(worker=worker)

    # Calling with positional arguments must raise TypeError
    with pytest.raises(TypeError):
        port.check_consistency("premise text", "hypothesis text")  # type: ignore[misc]

    # Keyword arguments succeed
    res = port.check_consistency(premise="All humans are mortal", hypothesis="Socrates is mortal")
    assert isinstance(res, VerificationResult)


def test_bounded_lru_cache_operations() -> None:
    """Verifies bounded capacity, LRU eviction, and clear behavior."""
    cache = BoundedLRUPairCache(capacity=3)
    assert len(cache) == 0

    dummy_res = VerificationResult(
        label=VerifierLabel.ENTAILMENT,
        confidence=0.95,
        premise="p",
        hypothesis="h",
    )

    cache.set(("p1", "h1"), dummy_res)
    cache.set(("p2", "h2"), dummy_res)
    cache.set(("p3", "h3"), dummy_res)
    assert len(cache) == 3

    # Access p1 to make it most recently used
    assert cache.get(("p1", "h1")) is not None

    # Insert p4, which should evict p2 (the least recently used)
    cache.set(("p4", "h4"), dummy_res)
    assert len(cache) == 3
    assert cache.get(("p2", "h2")) is None
    assert cache.get(("p1", "h1")) is not None
    assert cache.get(("p3", "h3")) is not None
    assert cache.get(("p4", "h4")) is not None

    cache.clear()
    assert len(cache) == 0


def test_cache_nfc_normalization() -> None:
    """Verifies that NFC-decomposed and composed unicode representations hit the same cache key."""
    worker = VerifierWorker()
    # "e" + combining acute accent (decomposed NFD) vs "é" (composed NFC)
    nfd_text = "caf\u0065\u0301"
    nfc_text = "caf\u00e9"
    assert nfd_text != nfc_text
    assert unicodedata.normalize("NFC", nfd_text) == unicodedata.normalize("NFC", nfc_text)

    dummy_res = VerificationResult(
        label=VerifierLabel.ENTAILMENT,
        confidence=0.99,
        premise=nfc_text,
        hypothesis="coffee shop",
    )
    worker._cache.set((unicodedata.normalize("NFC", nfd_text), "coffee shop"), dummy_res)

    # Querying with NFC version hits cache
    result = worker.check_consistency(premise=nfc_text, hypothesis="coffee shop")
    assert result.cached is True
    assert result.confidence == 0.99


def test_verifier_decision_policy_thresholds() -> None:
    """Verifies pre-registered decision policy: tau=0.50 and uncertainty band [0.40, 0.60]."""
    worker = VerifierWorker()
    worker.compiled = MagicMock()
    worker.tokenizer = MagicMock()
    worker._input_names = ["input_ids", "attention_mask"]

    mock_tok = MagicMock()
    mock_tok.ids = [101, 102]
    mock_tok.attention_mask = [1, 1]
    mock_tok.type_ids = [0, 0]
    worker.tokenizer.encode.return_value = mock_tok

    def make_infer_result(logits: list[float]) -> MagicMock:
        mock_req = MagicMock()
        mock_req.infer.return_value = {"logits": np.array(logits, dtype=np.float32)}
        return mock_req

    # Case 1: High entailment (> 0.60) -> ENTAILMENT
    # Softmax of [5.0, 0.0, 0.0] gives entailment ~ 0.98
    worker.infer_request = make_infer_result([5.0, 0.0, 0.0])
    res = worker.check_consistency(premise="p1", hypothesis="h1")
    assert res.label == VerifierLabel.ENTAILMENT
    assert res.entailment_prob > 0.60
    assert res.degraded is False

    # Case 2: High contradiction (> 0.60) -> CONTRADICTION
    # Softmax of [0.0, 0.0, 5.0] gives contradiction ~ 0.98
    worker.infer_request = make_infer_result([0.0, 0.0, 5.0])
    res = worker.check_consistency(premise="p2", hypothesis="h2")
    assert res.label == VerifierLabel.CONTRADICTION
    assert res.contradiction_prob > 0.60

    # Case 3: High neutral (> 0.60) -> NEUTRAL
    # Softmax of [0.0, 5.0, 0.0] gives neutral ~ 0.98
    worker.infer_request = make_infer_result([0.0, 5.0, 0.0])
    res = worker.check_consistency(premise="p3", hypothesis="h3")
    assert res.label == VerifierLabel.NEUTRAL
    assert res.neutral_prob > 0.60

    # Case 4: Ambiguous entailment inside uncertainty band [0.40, 0.60] -> UNCERTAIN
    # e.g. Logits that produce ~0.50 entailment, 0.30 neutral, 0.20 contradiction
    # ln(0.50) = -0.693, ln(0.30) = -1.204, ln(0.20) = -1.609
    worker.infer_request = make_infer_result([-0.693, -1.204, -1.609])
    res = worker.check_consistency(premise="p4", hypothesis="h4")
    assert res.label == VerifierLabel.UNCERTAIN
    assert 0.40 <= res.entailment_prob <= 0.60

    # Case 5: Ambiguous contradiction inside uncertainty band [0.40, 0.60] -> UNCERTAIN
    worker.infer_request = make_infer_result([-1.609, -1.204, -0.693])
    res = worker.check_consistency(premise="p5", hypothesis="h5")
    assert res.label == VerifierLabel.UNCERTAIN
    assert 0.40 <= res.contradiction_prob <= 0.60

    # Case 6: Diffuse distribution [0.34, 0.33, 0.33] -> UNCERTAIN
    worker.infer_request = make_infer_result([0.0, 0.0, 0.0])
    res = worker.check_consistency(premise="p6", hypothesis="h6")
    assert res.label == VerifierLabel.UNCERTAIN


def test_verifier_fail_open_on_timeout() -> None:
    """Verifies that inference taking > timeout_ms degrades cleanly without crashing."""
    worker = VerifierWorker(timeout_ms=10.0)
    worker.compiled = MagicMock()
    worker.tokenizer = MagicMock()
    worker._input_names = ["input_ids", "attention_mask"]

    mock_tok = MagicMock()
    mock_tok.ids = [101, 102]
    mock_tok.attention_mask = [1, 1]
    mock_tok.type_ids = [0, 0]
    worker.tokenizer.encode.return_value = mock_tok

    def slow_infer(*args: object, **kwargs: object) -> dict[str, np.ndarray]:
        time.sleep(0.02)  # 20ms > 10ms timeout
        return {"logits": np.array([5.0, 0.0, 0.0], dtype=np.float32)}

    mock_req = MagicMock()
    mock_req.infer.side_effect = slow_infer
    worker.infer_request = mock_req

    with patch("lucca.senses.verifier.logger.warning") as mock_log:
        res = worker.check_consistency(premise="slow premise", hypothesis="slow hypothesis")
        assert res.label == VerifierLabel.UNCERTAIN
        assert res.degraded is True
        assert res.latency_ms > 10.0
        mock_log.assert_called_with(
            "verifier_degraded",
            reason="timeout",
            latency_ms=pytest.approx(res.latency_ms, rel=1e-2),
            timeout_ms=10.0,
        )


def test_verifier_fail_open_on_exception() -> None:
    """Verifies that unhandled runtime exceptions trigger fail-open degradation."""
    worker = VerifierWorker()
    worker.compiled = MagicMock()
    worker.tokenizer = MagicMock()
    worker.tokenizer.encode.side_effect = RuntimeError("Tokenizer buffer overflow simulation")

    with patch("lucca.senses.verifier.logger.warning") as mock_log:
        res = worker.check_consistency(premise="broken", hypothesis="error")
        assert res.label == VerifierLabel.UNCERTAIN
        assert res.degraded is True
        mock_log.assert_called()


def test_g_v1357_verifier_neg_gate() -> None:
    """
    Gate G-V1357-VERIFIER-NEG:
    1. Near-paraphrase pairs score as ENTAILMENT, not CONTRADICTION.
    2. UNCERTAIN label sets neither epistemic bit.
    3. Timeout degrades to lexical behavior without new polarity admitted.
    """
    worker = VerifierWorker()
    worker.compiled = MagicMock()
    worker.tokenizer = MagicMock()
    worker._input_names = ["input_ids", "attention_mask"]

    mock_tok = MagicMock()
    mock_tok.ids = [101, 102]
    mock_tok.attention_mask = [1, 1]
    mock_tok.type_ids = [0, 0]
    worker.tokenizer.encode.return_value = mock_tok

    # Sub-test 1: Near-paraphrase -> ENTAILMENT
    mock_req = MagicMock()
    mock_req.infer.return_value = {"logits": np.array([3.0, 0.5, -2.0], dtype=np.float32)}
    worker.infer_request = mock_req

    res_paraphrase = worker.check_consistency(
        premise="Always use single quotes for string literals.",
        hypothesis="Prefer single quotes for string literals.",
    )
    assert res_paraphrase.label == VerifierLabel.ENTAILMENT
    assert res_paraphrase.label != VerifierLabel.CONTRADICTION

    # Sub-test 2: UNCERTAIN sets neither epistemic bit
    mock_req.infer.return_value = {"logits": np.array([0.5, 0.5, 0.5], dtype=np.float32)}
    res_uncertain = worker.check_consistency(
        premise="Arbitrary premise",
        hypothesis="Unrelated claim",
    )
    assert res_uncertain.label == VerifierLabel.UNCERTAIN
    told_true = res_uncertain.label == VerifierLabel.ENTAILMENT
    told_false = res_uncertain.label == VerifierLabel.CONTRADICTION
    assert not told_true and not told_false

    # Sub-test 3: Degraded turn sets neither bit
    worker.tokenizer.encode.side_effect = TimeoutError("Simulated timeout")
    res_degraded = worker.check_consistency(
        premise="Premise",
        hypothesis="Hypothesis",
    )
    assert res_degraded.degraded is True
    assert res_degraded.label == VerifierLabel.UNCERTAIN
    assert not (res_degraded.label == VerifierLabel.ENTAILMENT)
    assert not (res_degraded.label == VerifierLabel.CONTRADICTION)
