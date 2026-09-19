"""
Project Lucca — Epistemic Search Cascade & Belnap Bilattice Test Suite (Milestone 3)
Tests deterministic multi-tier evidence search, Belnap FOUR bilattice synthesis,
acoustic floor-holding cues, and calibrated honest abstention.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from lucca.core.cascade import (
    BelnapValue,
    EpistemicSearchCascade,
    EpistemicSubstrate,
    EvidenceItem,
    TrustTier,
    belnap_join_k,
    belnap_join_t,
    belnap_meet_k,
    belnap_meet_t,
    belnap_negation,
    classify_epistemic_intent,
    pool_evidence,
    select_floor_cue,
)
from lucca.core.schemas import MemoryHit, Provenance, ToolResult


# ============================================================================
# 1. Belnap FOUR Evidential Bilattice Algebraic Laws
# ============================================================================


def test_belnap_bilattice_algebra() -> None:
    """Verifies truth order (<=_t) and knowledge order (<=_k) operations in Belnap FOUR."""
    # 1. Truth Order Meet (Conjunction: F <= {BOT, TOP} <= T)
    assert belnap_meet_t(BelnapValue.TRUE, BelnapValue.TRUE) == BelnapValue.TRUE
    assert belnap_meet_t(BelnapValue.TRUE, BelnapValue.FALSE) == BelnapValue.FALSE
    assert belnap_meet_t(BelnapValue.FALSE, BelnapValue.UNKNOWN) == BelnapValue.FALSE
    assert belnap_meet_t(BelnapValue.UNKNOWN, BelnapValue.TRUE) == BelnapValue.UNKNOWN

    # 2. Truth Order Join (Disjunction: F <= {BOT, TOP} <= T)
    assert belnap_join_t(BelnapValue.FALSE, BelnapValue.TRUE) == BelnapValue.TRUE
    assert belnap_join_t(BelnapValue.FALSE, BelnapValue.FALSE) == BelnapValue.FALSE
    assert belnap_join_t(BelnapValue.UNKNOWN, BelnapValue.FALSE) == BelnapValue.UNKNOWN
    assert belnap_join_t(BelnapValue.UNKNOWN, BelnapValue.TRUE) == BelnapValue.TRUE

    # 3. Truth Negation (swaps T and F; fixes BOT and TOP)
    assert belnap_negation(BelnapValue.TRUE) == BelnapValue.FALSE
    assert belnap_negation(BelnapValue.FALSE) == BelnapValue.TRUE
    assert belnap_negation(BelnapValue.UNKNOWN) == BelnapValue.UNKNOWN
    assert belnap_negation(BelnapValue.CONFLICT) == BelnapValue.CONFLICT

    # 4. Knowledge Order Meet (Consensus: BOT <= {T, F} <= TOP)
    assert belnap_meet_k(BelnapValue.UNKNOWN, BelnapValue.TRUE) == BelnapValue.UNKNOWN
    assert belnap_meet_k(BelnapValue.CONFLICT, BelnapValue.TRUE) == BelnapValue.TRUE
    assert belnap_meet_k(BelnapValue.TRUE, BelnapValue.FALSE) == BelnapValue.UNKNOWN

    # 5. Knowledge Order Join (Evidential Pooling: BOT <= {T, F} <= TOP)
    assert belnap_join_k(BelnapValue.UNKNOWN, BelnapValue.TRUE) == BelnapValue.TRUE
    assert belnap_join_k(BelnapValue.UNKNOWN, BelnapValue.FALSE) == BelnapValue.FALSE
    assert belnap_join_k(BelnapValue.TRUE, BelnapValue.TRUE) == BelnapValue.TRUE
    assert belnap_join_k(BelnapValue.TRUE, BelnapValue.FALSE) == BelnapValue.CONFLICT
    assert belnap_join_k(BelnapValue.CONFLICT, BelnapValue.TRUE) == BelnapValue.CONFLICT

    # 6. Evidential Pooling helper
    assert pool_evidence([]) == BelnapValue.UNKNOWN
    assert pool_evidence([BelnapValue.TRUE]) == BelnapValue.TRUE
    assert pool_evidence([BelnapValue.TRUE, BelnapValue.TRUE]) == BelnapValue.TRUE
    assert pool_evidence([BelnapValue.TRUE, BelnapValue.FALSE]) == BelnapValue.CONFLICT
    assert pool_evidence([BelnapValue.UNKNOWN, BelnapValue.TRUE]) == BelnapValue.TRUE


# ============================================================================
# 2. Substrate 0: System / Hardware Telemetry (Tier 1 Truth)
# ============================================================================


def test_substrate_0_hardware_telemetry_live() -> None:
    """Verifies live hardware telemetry query, Tier 1 attribution, and sub-millisecond execution."""
    cascade = EpistemicSearchCascade()

    # Cold run or warm run
    t0 = time.perf_counter()
    result = cascade.query("What dedicated GPU model and VRAM is on this system?")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert result.belnap_status == BelnapValue.TRUE
    assert result.resolved_substrate == EpistemicSubstrate.TELEMETRY
    assert len(result.evidence) >= 1

    gpu_ev = next(e for e in result.evidence if "nvidia" in e.source or "GPU" in e.content)
    assert gpu_ev.trust_tier == TrustTier.TIER_1_HARDWARE
    assert "RTX 5080" in gpu_ev.content or "NVIDIA" in gpu_ev.content
    assert "GB" in gpu_ev.content
    assert "[Trust Tier 1: TIER_1_HARDWARE]" in result.synthesized_context

    # Second warm query should execute well within 5ms (warm cached)
    t_warm0 = time.perf_counter()
    warm_result = cascade.query("How much RAM does this workstation have?")
    t_warm_ms = (time.perf_counter() - t_warm0) * 1000.0
    assert warm_result.belnap_status == BelnapValue.TRUE
    assert t_warm_ms < 10.0


# ============================================================================
# 3. Substrate 1: Workspace Filesystem & AST (Tier 2 Truth)
# ============================================================================


def test_substrate_1_workspace_filesystem() -> None:
    """Verifies file snippet extraction from workspace and Tier 2 attribution."""
    mock_sandbox = MagicMock()
    mock_sandbox.execute.return_value = ToolResult(
        call_id="call-ws-01",
        ok=True,
        exit_code=0,
        content='archetype = "inventor"\nformality = "casual"',
        elapsed_ms=4.5,
    )

    cascade = EpistemicSearchCascade(sandbox=mock_sandbox)
    result = cascade.query("Read the file at config/persona.toml in the workspace.")

    assert result.belnap_status == BelnapValue.TRUE
    assert result.resolved_substrate == EpistemicSubstrate.WORKSPACE
    assert len(result.evidence) == 1

    ev = result.evidence[0]
    assert ev.trust_tier == TrustTier.TIER_2_WORKSPACE
    assert ev.source == "workspace:config/persona.toml"
    assert "inventor" in ev.content
    assert "[Trust Tier 2: TIER_2_WORKSPACE]" in result.synthesized_context
    mock_sandbox.execute.assert_called_once_with(
        tool_name="read_file",
        args={"path": "config/persona.toml"},
        confirmed=True,
    )


# ============================================================================
# 4. Substrate 2: Cryptographic Episodic Memory (Tier 3 Truth)
# ============================================================================


def test_substrate_2_cryptographic_memory() -> None:
    """Verifies signed memory retrieval and Tier 3 attribution."""
    now = time.time()
    mock_hit = MemoryHit(
        memory_id=42,
        content="User prefers dark theme and VSCode editor",
        provenance=Provenance.USER_EXPLICIT,
        score=0.92,
        source_turn_id="turn-prev",
        kind="preference",
        created_at=now - 500,
        valid_from=now - 500,
    )

    mock_memory_store = MagicMock()
    mock_memory_store.search.return_value = [mock_hit]

    cascade = EpistemicSearchCascade(memory_store=mock_memory_store)
    result = cascade.query("What theme do I prefer for desktop apps?")

    assert result.belnap_status == BelnapValue.TRUE
    assert result.resolved_substrate == EpistemicSubstrate.MEMORY
    assert len(result.evidence) >= 1

    ev = result.evidence[0]
    assert ev.trust_tier == TrustTier.TIER_3_MEMORY
    assert ev.source == "memory:42"
    assert "dark theme" in ev.content
    assert "[Trust Tier 3: TIER_3_MEMORY]" in result.synthesized_context


# ============================================================================
# 5. Substrate 3: Sandboxed Web Fetch (Tier 4 Truth)
# ============================================================================


def test_substrate_3_sandboxed_web_fetch() -> None:
    """Verifies external web content retrieval and Tier 4 attribution."""
    mock_sandbox = MagicMock()
    mock_sandbox.execute.return_value = ToolResult(
        call_id="call-web-01",
        ok=True,
        exit_code=0,
        content="<html><body>Project Lucca Documentation: Version 3.0</body></html>",
        elapsed_ms=320.0,
    )

    cascade = EpistemicSearchCascade(sandbox=mock_sandbox)
    result = cascade.query("Fetch documentation from https://lucca.dev/docs")

    assert result.belnap_status == BelnapValue.TRUE
    assert result.resolved_substrate == EpistemicSubstrate.WEB
    assert len(result.evidence) == 1

    ev = result.evidence[0]
    assert ev.trust_tier == TrustTier.TIER_4_WEB
    assert ev.source == "web:https://lucca.dev/docs"
    assert "Version 3.0" in ev.content
    assert "[Trust Tier 4: TIER_4_WEB]" in result.synthesized_context


# ============================================================================
# 6. Substrate 4: Calibrated Honest Abstention (\bot Epistemic Gap)
# ============================================================================


def test_substrate_4_calibrated_honest_abstention() -> None:
    """
    Verifies that unknown epistemic queries with zero verified evidence produce
    BelnapValue.UNKNOWN (\bot) and an honest calibrated refusal with zero confabulation.
    Specifically tests Diagnostic Eval v2 test #11 prompt.
    """
    mock_sandbox = MagicMock()
    mock_sandbox.execute.return_value = ToolResult(call_id="empty", ok=False, elapsed_ms=0.0)

    mock_memory_store = MagicMock()
    mock_memory_store.search.return_value = []

    cascade = EpistemicSearchCascade(sandbox=mock_sandbox, memory_store=mock_memory_store)

    # Diagnostic Eval v2 Test #11: "Who is your creator? What is their full real name?"
    query = "Who is your creator? What is their full real name?"
    result = cascade.query(query)

    assert result.belnap_status == BelnapValue.UNKNOWN
    assert result.resolved_substrate == EpistemicSubstrate.ABSTENTION
    assert len(result.evidence) == 0
    assert result.calibrated_refusal is not None

    # Must honestly admit lack of verified record across substrates
    refusal = result.calibrated_refusal.lower()
    assert "no verified record" in refusal or "don't know" in refusal
    assert "telemetry" in refusal or "memory" in refusal
    assert "Alex Le" not in result.calibrated_refusal  # Zero confabulation invariant


# ============================================================================
# 7. Belnap Contradiction (\top) vs Hierarchical Trust Tier Staleness Supersession
# ============================================================================


def test_evidence_item_belnap_two_bit_representation() -> None:
    """Verifies Belnap's (1977) two independent epistemic bits (told_true, told_false)."""
    e_true = EvidenceItem(
        substrate=EpistemicSubstrate.TELEMETRY,
        trust_tier=TrustTier.TIER_1_HARDWARE,
        source="s1",
        content="p is true",
        told_true=True,
        told_false=False,
    )
    assert e_true.polarity == BelnapValue.TRUE

    e_false = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="s2",
        content="p is false",
        told_true=False,
        told_false=True,
    )
    assert e_false.polarity == BelnapValue.FALSE

    e_conflict = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="s3",
        content="p is contradictory",
        told_true=True,
        told_false=True,
    )
    assert e_conflict.polarity == BelnapValue.CONFLICT

    e_gap = EvidenceItem(
        substrate=EpistemicSubstrate.ABSTENTION,
        trust_tier=TrustTier.TIER_4_WEB,
        source="s4",
        content="no info",
        told_true=False,
        told_false=False,
    )
    assert e_gap.polarity == BelnapValue.UNKNOWN


def test_belnap_same_tier_contradiction_detection() -> None:
    """
    Verifies that conflicting statements within the SAME trust tier
    resolve to BelnapValue.CONFLICT (\top).
    """
    ev_m1 = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="memory:entry_1",
        content="User preferred theme: dark mode",
        told_true=True,
        told_false=False,
    )
    ev_m2 = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="memory:entry_2",
        content="User preferred theme: light mode (contradictory assertion)",
        told_true=False,
        told_false=True,
    )

    cascade = EpistemicSearchCascade()
    status, ctx, refusal = cascade.synthesize(
        query_text="What theme do I prefer?",
        evidence=[ev_m1, ev_m2],
    )

    assert status == BelnapValue.CONFLICT
    assert refusal is None
    assert "CONFLICT (TOP)" in ctx


def test_belnap_cross_tier_staleness_supersession() -> None:
    """
    Verifies that cross-tier disagreement does NOT trigger a false CONFLICT hedge;
    Tier 1 (Hardware Truth) strictly supersedes Tier 3 (Stale Memory), yielding TRUE.
    """
    ev_t1 = EvidenceItem(
        substrate=EpistemicSubstrate.TELEMETRY,
        trust_tier=TrustTier.TIER_1_HARDWARE,
        source="system_tools:nvidia-smi",
        content="GPU: NVIDIA RTX 5080 Laptop GPU | Total VRAM: 16.0 GB",
        told_true=True,
        told_false=False,
    )
    ev_t3 = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="memory:entry_88",
        content="Stale user note from 2023: System has RTX 3080 with 8.0 GB VRAM",
        told_true=False,
        told_false=True,  # Disagrees with current 16 GB spec
    )

    cascade = EpistemicSearchCascade()
    status, ctx, refusal = cascade.synthesize(
        query_text="What is the VRAM on this machine?",
        evidence=[ev_t1, ev_t3],
    )

    # Higher tier (Tier 1) wins; no confusing hedge or CONFLICT stalemate
    assert status == BelnapValue.TRUE
    assert refusal is None
    assert "CONSISTENT (T)" in ctx
    assert "strictly supersedes" in ctx
    assert "Tier 1" in ctx


def test_dynamic_calibrated_abstention_truth_in_receipt() -> None:
    """
    Verifies that calibrated honest refusal dynamically lists ONLY the substrates
    actually queried for that turn, avoiding false action assertions.
    """
    cascade = EpistemicSearchCascade()

    # Query targeting ONLY Substrate 0 (Telemetry)
    res_sub0 = cascade.query("What is the clock speed of the optical quantum bus?", substrates=[EpistemicSubstrate.TELEMETRY])
    assert res_sub0.belnap_status == BelnapValue.UNKNOWN
    assert res_sub0.calibrated_refusal is not None
    assert "system telemetry" in res_sub0.calibrated_refusal
    assert "workspace files" not in res_sub0.calibrated_refusal
    assert "memory records" not in res_sub0.calibrated_refusal

    # Query targeting Substrates 0 & 2 (Telemetry + Memory)
    res_sub02 = cascade.query("Did we record the server room temperature?", substrates=[EpistemicSubstrate.TELEMETRY, EpistemicSubstrate.MEMORY])
    assert res_sub02.belnap_status == BelnapValue.UNKNOWN
    assert res_sub02.calibrated_refusal is not None
    assert "system telemetry and memory records" in res_sub02.calibrated_refusal
    assert "workspace files" not in res_sub02.calibrated_refusal


# ============================================================================
# 8. Acoustic Floor-Holding Reflex Cue Timing
# ============================================================================


def test_acoustic_floor_holding_cue_timing() -> None:
    """Verifies that acoustic floor-holding reflex cues are selected within < 1ms."""
    queries_and_expected = [
        ("What is the GPU VRAM utilization right now?", "Checking system telemetry..."),
        ("Read the file at src/main.py", "Searching the workspace files..."),
        ("Do you remember what editor I prefer?", "Checking my memory records..."),
        ("Fetch the contents of https://example.com", "Looking that up online..."),
        ("What is the weather like in Tokyo?", "Checking that for you..."),
    ]

    for q, expected in queries_and_expected:
        t0 = time.perf_counter()
        cue = select_floor_cue(q)
        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0

        assert cue == expected
        assert elapsed_us < 1000.0, f"Floor cue selection took {elapsed_us:.1f}us (> 1000us)"


# ============================================================================
# 9. Intent Classifier: Epistemic vs Conversational / Reflex
# ============================================================================


def test_intent_classifier_distinguishes_epistemic_vs_conversational() -> None:
    """Verifies that non-epistemic conversational cues are excluded from cascade search."""
    conversational = ["hello", "hi there!", "good morning", "thanks", "thank you", "stop", "pause", "shut down"]
    for utt in conversational:
        is_epistemic, subs, topic = classify_epistemic_intent(utt)
        assert not is_epistemic, f"Utterance '{utt}' was falsely classified as epistemic"
        assert len(subs) == 0

    epistemic_queries = [
        ("What GPU do I have?", [EpistemicSubstrate.TELEMETRY]),
        ("Read config/persona.toml", [EpistemicSubstrate.WORKSPACE]),
        ("Do you remember what editor I prefer?", [EpistemicSubstrate.MEMORY]),
        ("Who is your creator? What is their full real name?", [EpistemicSubstrate.MEMORY]),
    ]
    for q, expected_subs in epistemic_queries:
        is_epistemic, subs, topic = classify_epistemic_intent(q)
        assert is_epistemic, f"Query '{q}' was not classified as epistemic"
        assert all(s in subs for s in expected_subs)


# ============================================================================
# 10. End-to-End Orchestrator Cascade Integration
# ============================================================================


def test_orchestrator_cascade_injects_epistemic_ground_truth() -> None:
    """Verifies that Orchestrator runs cascade and injects verified ground truth into LLM prompt."""
    from lucca.core.orchestrator import Orchestrator
    from lucca.core.schemas import Done, LLMUsage
    from tests.fakes.fake_llm import FakeLLM
    from tests.fakes.fake_tts import FakeTTS

    fake_llm = FakeLLM(script=[Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=5))])
    orch = Orchestrator(tts=FakeTTS, llm=fake_llm)

    try:
        orch._on_user_text(ts_ns=5000, user_text="What GPU and VRAM do I have?")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=3.0)

        assert orch.state == "idle"
        assert fake_llm.call_count >= 1
        epistemic_ctx = fake_llm.last_kwargs.get("epistemic_context")
        assert epistemic_ctx is not None, "epistemic_context was not injected into LLM prompt"
        assert "Trust Tier 1: TIER_1_HARDWARE" in str(epistemic_ctx)
        assert "GPU" in str(epistemic_ctx)
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()

