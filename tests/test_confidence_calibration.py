"""
Unit tests for Proactive Epistemic Confidence Calibration (WO-13.2).
Spec: docs/DECISIONS.md (D-META-01), STUDIO_CAPABILITY_ROADMAP §7.1.
Verifies non-parametric calibration: weak/conflicted evidence triggers calibrated
framing while high-confidence records remain crisp and assertive.
Zero-Any invariant enforced.
"""

from __future__ import annotations

from lucca.brain.prompt_builder import (
    build_messages,
    build_narration_messages,
    get_epistemic_calibration_directive,
)
from lucca.core.schemas import MemoryHit, MemoryProvenance, ToolResult


def test_high_confidence_memory_no_hedging() -> None:
    """High-confidence verified records (c >= 0.85) should not trigger calibration hedges."""
    high_conf_hit = MemoryHit(
        memory_id=101,
        content="User's primary project repository is located at C:\\Projects\\ProjectLucca",
        provenance=MemoryProvenance.USER_EXPLICIT,
        score=0.92,
        kind="fact",
        created_at=1700000000.0,
        valid_from=1700000000.0,
        confidence=0.95,
    )

    directive = get_epistemic_calibration_directive(memories=[high_conf_hit])
    assert directive is None, f"Expected None for c=0.95, got: {directive}"

    msgs = build_messages(memories=[high_conf_hit], current_text="Where is my project repo?")
    system_text = msgs[0].content
    assert isinstance(system_text, str)
    assert "[Epistemic Calibration Directive:" not in system_text
    assert "User's primary project repository is located" in system_text


def test_low_confidence_memory_triggers_calibration_hedge() -> None:
    """Low-confidence belief or memory (c < 0.70) must inject the calibrated framing directive."""
    low_conf_hit = MemoryHit(
        memory_id=102,
        content="I think your favorite weekend hobby might be woodworking.",
        provenance=MemoryProvenance.ASSISTANT_BELIEF,
        score=0.65,
        kind="belief",
        created_at=1700000000.0,
        valid_from=1700000000.0,
        confidence=0.55,
    )

    directive = get_epistemic_calibration_directive(memories=[low_conf_hit])
    assert directive is not None
    assert "[Epistemic Calibration Directive:" in directive
    assert "low confidence (<0.70)" in directive
    assert "woodworking" in directive

    msgs = build_messages(memories=[low_conf_hit], current_text="What do I like doing on weekends?")
    system_text = msgs[0].content
    assert isinstance(system_text, str)
    assert "[Epistemic Calibration Directive:" in system_text


def test_belnap_top_conflict_triggers_calibration_hedge() -> None:
    """Epistemic cascade conflict (Belnap TOP) must trigger calibrated framing."""
    epistemic_ctx = (
        "[Substrate 2: Memory] Belnap TOP (Conflict): "
        "User stated both 'I live in Seattle' and 'I live in New York'. "
        "Confidence: 0.85 vs 0.85."
    )

    directive = get_epistemic_calibration_directive(epistemic_context=epistemic_ctx)
    assert directive is not None
    assert "conflicting evidence" in directive
    assert "Belnap TOP" in directive

    msgs = build_messages(epistemic_context=epistemic_ctx, current_text="Where do I live?")
    system_text = msgs[0].content
    assert isinstance(system_text, str)
    assert "[Epistemic Calibration Directive:" in system_text


def test_belnap_bot_epistemic_gap_triggers_calibration_hedge() -> None:
    """Epistemic cascade knowledge gap (Belnap BOT) must trigger calibrated framing."""
    epistemic_ctx = (
        "[Substrate 4: Abstention] Belnap BOT (Unknown): "
        "No verified record found across telemetry, workspace, or memory."
    )

    directive = get_epistemic_calibration_directive(epistemic_context=epistemic_ctx)
    assert directive is not None
    assert "unverified knowledge gap" in directive
    assert "Belnap BOT" in directive


def test_narration_messages_includes_calibration_directive() -> None:
    """Act-Then-Narrate messages must include calibration directive when memories have c < 0.70."""
    low_conf_hit = MemoryHit(
        memory_id=103,
        content="Tentative note: build script might be using CMake instead of Ninja",
        provenance=MemoryProvenance.ASSISTANT_BELIEF,
        score=0.50,
        kind="belief",
        created_at=1700000000.0,
        valid_from=1700000000.0,
        confidence=0.60,
    )
    tool_res = ToolResult(
        call_id="call-build-01",
        ok=True,
        content="ninja: no work to do.",
        elapsed_ms=12.5,
    )

    msgs = build_narration_messages(
        tool_name="run_command",
        tool_args={"cmd": "ninja"},
        tool_result=tool_res,
        user_text="Did the build succeed?",
        memories=[low_conf_hit],
    )
    system_text = msgs[0].content
    assert isinstance(system_text, str)
    assert "[Epistemic Calibration Directive:" in system_text
