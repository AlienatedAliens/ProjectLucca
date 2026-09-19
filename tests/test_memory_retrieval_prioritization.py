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
