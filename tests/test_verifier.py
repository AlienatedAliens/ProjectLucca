"""
WO-37 Phase 2 — NLI Verifier Subsystem Tests (MiniLM-L6 OpenVINO)
Validates sub-50ms CPU inference, accurate entailment and contradiction detection,
and graceful degradation.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from lucca.core.schemas import VerificationResult, VerifierLabel
from lucca.senses.verifier import VERIFIER_MINILM_DIR, VerifierWorker


def test_verifier_worker_initialization() -> None:
    """Verifies that VerifierWorker initializes with VERIFIER_MINILM_DIR without error."""
    worker = VerifierWorker(model_dir=VERIFIER_MINILM_DIR)
    assert worker.model_dir == VERIFIER_MINILM_DIR
    assert worker.compiled is not None
    assert worker.tokenizer is not None


def test_verifier_entailment_and_contradiction() -> None:
    """Verifies standard NLI semantic consistency checks."""
    worker = VerifierWorker(model_dir=VERIFIER_MINILM_DIR)

    # Entailment
    res_ent = worker.check_consistency(
        premise="The cat is on the mat.",
        hypothesis="There is a cat on the mat.",
    )
    assert res_ent.label == VerifierLabel.ENTAILMENT
    assert res_ent.entailment_prob > 0.60
    assert not res_ent.degraded

    # Contradiction
    res_con = worker.check_consistency(
        premise="The cat is on the mat.",
        hypothesis="There is no cat here.",
    )
    assert res_con.label == VerifierLabel.CONTRADICTION
    assert res_con.contradiction_prob > 0.60
    assert not res_con.degraded


def test_verifier_latency_p95_under_50ms() -> None:
    """WO-37 Phase 2 Gate (G-WO37-NLI-LATENCY): 10 sequential pairs each complete in <= 50ms."""
    worker = VerifierWorker(model_dir=VERIFIER_MINILM_DIR)
    # Warmup 1 call
    worker.check_consistency(premise="Warmup premise.", hypothesis="Warmup hypothesis.")
    worker._cache.clear()

    pairs = [
        ("The dog is playing outside in the garden.", "An animal is in the garden."),
        ("The package was delivered this morning.", "The parcel arrived earlier today."),
        ("John is learning to play the piano.", "John has never touched a musical instrument."),
        ("The server is currently online and healthy.", "The service is completely offline."),
        ("It is heavily raining in Seattle right now.", "The weather in Seattle is rainy."),
        ("The store is closed on Sundays.", "You can shop at the store on Sunday."),
        ("She finished writing her novel yesterday.", "Her book is completed."),
        ("The train arrives at 5 PM sharp.", "The locomotive will get here at five in the afternoon."),
        ("He dislikes spicy food.", "He loves eating fiery chili peppers."),
        ("The battery is fully charged.", "The battery has plenty of power."),
    ]

    latencies: list[float] = []
    for p, h in pairs:
        t0 = time.perf_counter()
        res = worker.check_consistency(premise=p, hypothesis=h)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)
        assert not res.degraded, f"Verification degraded on pair ('{p}', '{h}') with latency {elapsed_ms:.1f}ms"
        assert elapsed_ms <= 50.0, f"Latency {elapsed_ms:.1f}ms exceeded 50ms limit for ('{p}', '{h}')"

    latencies.sort()
    # 95th percentile (9th element out of 10)
    p95 = latencies[int(len(latencies) * 0.95)]
    print(f"\n[NLI Latency] min={min(latencies):.1f}ms, mean={sum(latencies)/len(latencies):.1f}ms, p95={p95:.1f}ms, max={max(latencies):.1f}ms")
    assert p95 <= 50.0
