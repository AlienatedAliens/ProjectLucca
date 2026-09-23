"""
Tests for Proposal G / D-MEM-03: Scaled Memory Quota and Multi-Factor Prioritized Truncation.
"""

import time

from lucca.core.schemas import MemoryHit, Provenance
from lucca.memory.retrieval import format_memory_context


def test_format_memory_context_multi_factor_prioritization() -> None:
    now = time.time()
    # Create hits with different provenances and scores:
    # hit1: low score, but USER_EXPLICIT
    hit1 = MemoryHit(
        memory_id=1,
        content="User explicit fact: I like Python.",
        provenance=Provenance.USER_EXPLICIT,
        score=0.1,
        created_at=now - 100,
    )
    # hit2: high score, but TOOL_CONTENT_UNTRUSTED
    hit2 = MemoryHit(
        memory_id=2,
        content="Untrusted web snippet.",
        provenance=Provenance.TOOL_CONTENT_UNTRUSTED,
        score=0.99,
        created_at=now - 50,
    )
    # hit3: medium score, TOOL_VERIFIED
    hit3 = MemoryHit(
        memory_id=3,
        content="Verified tool observation: file exists.",
        provenance=Provenance.TOOL_VERIFIED,
        score=0.5,
        created_at=now - 10,
    )

    rendered = format_memory_context([hit2, hit1, hit3], max_tokens=2048, now=now)
    lines = rendered.splitlines()
    assert len(lines) == 3
    # First line should be USER_EXPLICIT (tier 0)
    assert "USER_EXPLICIT" in lines[0]
    # Second line should be TOOL_VERIFIED (tier 1)
    assert "TOOL_VERIFIED" in lines[1]
    # Third line should be TOOL_CONTENT_UNTRUSTED (tier 2)
    assert "TOOL_CONTENT_UNTRUSTED" in lines[2]


def test_superseded_row_loses_to_superseding_row_in_cascade_output_ordering() -> None:
    """
    WO-11.5 (G4 / D-HON-01): Superseded row loses to superseding row in cascade output ordering.
    Surfaces 'current value per store' with explicit machine-checkable marker and narration contract.
    """
    from lucca.core.cascade import (
        BelnapValue,
        EpistemicSearchCascade,
        EpistemicSubstrate,
        EvidenceItem,
        TrustTier,
    )

    now = time.time()
    # Stale superseded item has HIGHER search confidence (0.98), but is superseded
    stale_item = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="memory:1",
        content="user lives_in Perth",
        confidence=0.98,
        metadata={"valid_from": now - 100.0, "valid_to": now - 10.0, "is_superseded": True},
    )
    # Current active item has LOWER search confidence (0.80), but newer valid_from
    current_item = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="memory:2",
        content="user lives_in Brisbane",
        confidence=0.80,
        metadata={"valid_from": now - 10.0, "valid_to": None, "is_superseded": False},
    )

    cascade = EpistemicSearchCascade()
    status, ctx, refusal = cascade.synthesize(
        query_text="Where do I live now?",
        evidence=[stale_item, current_item],
    )

    # 1. Status is CONSISTENT (T) — no false conflict hedge from superseded row
    assert status == BelnapValue.TRUE
    assert refusal is None

    # 2. Output ordering: superseding row MUST appear BEFORE superseded row
    brisbane_pos = ctx.find("user lives_in Brisbane")
    perth_pos = ctx.find("user lives_in Perth")
    assert brisbane_pos != -1, "Current value 'Brisbane' must be present in context"
    assert perth_pos != -1, "Historical value 'Perth' must be present in context"
    assert brisbane_pos < perth_pos, (
        "Superseded row must lose to superseding row in cascade output ordering"
    )

    # 3. Machine-checkable markers referencing D-HON-01 and narration contract
    assert "D-HON-01" in ctx
    assert "Current value per store:" in ctx
    assert "Brisbane" in ctx
    assert "[superseded]" in ctx
    assert "Narration Contract:" in ctx
    assert "Cite the verified store's current value over transcript echo" in ctx


def test_functional_predicate_supersession_auto_detection() -> None:
    """
    WO-11.5 (G4 / D-HON-01): Two facts with the same functional predicate (lives_in)
    resolve automatically by valid_from timestamp even if valid_to was unset.
    """
    from lucca.core.cascade import (
        BelnapValue,
        EpistemicSearchCascade,
        EpistemicSubstrate,
        EvidenceItem,
        TrustTier,
    )

    now = time.time()
    perth_item = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="memory:101",
        content="user lives_in Perth",
        confidence=0.90,
        metadata={"valid_from": now - 50.0},
    )
    brisbane_item = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="memory:102",
        content="user lives_in Brisbane",
        confidence=0.85,
        metadata={"valid_from": now - 5.0},
    )

    cascade = EpistemicSearchCascade()
    status, ctx, _ = cascade.synthesize(
        query_text="Where do I live now?",
        evidence=[perth_item, brisbane_item],
    )

    assert status == BelnapValue.TRUE
    brisbane_pos = ctx.find("user lives_in Brisbane")
    perth_pos = ctx.find("user lives_in Perth")
    assert brisbane_pos < perth_pos
    assert "D-HON-01" in ctx
    assert "Current value per store:" in ctx

