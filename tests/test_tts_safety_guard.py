"""Tests for the TTS output safety guard (P6 remediation, workshop 2026-10-04).

Covers:
- Deterministic screening verdicts (benign allow, high-harm block per category).
- Tier gating (edge_tiers mode active only for E4B/E2B model filenames).
- Wiring through SpeechOutputManager (speak_text and enqueue_tts_chunk replace
  blocked text with the canned safe line).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lucca.core.speech_output_manager import SpeechOutputManager
from lucca.core.tts_safety_guard import SAFE_REPLACEMENT, TTSSafetyGuard
from lucca.core.trace import TurnTrace

E4B_MODEL = "llm/gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf"
E2B_MODEL = "llm/Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf"
B12_MODEL = "llm/gemma-4-12b-heretic-Q6_K.gguf"

BENIGN = "Sure! The mitochondrion is the powerhouse of the cell."
CBRN_INSTRUCTION = (
    "First, you synthesize sarin by slowly adding the precursor to the "
    "reaction vessel while keeping the temperature low."
)
EXPLOSIVE_INSTRUCTION = (
    "To make a pipe bomb, pack the container tightly and attach the "
    "detonator to the charge."
)
MALWARE_INSTRUCTION = (
    "I can write ransomware that encrypts the victim's files and demands "
    "payment for the key."
)


def test_benign_text_allowed_on_edge_tier() -> None:
    guard = TTSSafetyGuard(mode="edge_tiers", active_model=E4B_MODEL)
    verdict = guard.screen(BENIGN)
    assert verdict.allowed is True
    assert verdict.category is None


def test_cbrn_synthesis_blocked_on_edge_tier() -> None:
    guard = TTSSafetyGuard(mode="edge_tiers", active_model=E4B_MODEL)
    verdict = guard.screen(CBRN_INSTRUCTION)
    assert verdict.allowed is False
    assert verdict.category == "cbrn_agent_synthesis"


def test_explosive_synthesis_blocked_on_edge_tier() -> None:
    guard = TTSSafetyGuard(mode="edge_tiers", active_model=E2B_MODEL)
    verdict = guard.screen(EXPLOSIVE_INSTRUCTION)
    assert verdict.allowed is False
    assert verdict.category == "explosive_synthesis"


def test_malware_deployment_blocked_on_edge_tier() -> None:
    guard = TTSSafetyGuard(mode="edge_tiers", active_model=E2B_MODEL)
    verdict = guard.screen(MALWARE_INSTRUCTION)
    assert verdict.allowed is False
    assert verdict.category == "malicious_deployment"


def test_edge_tiers_mode_gating() -> None:
    assert TTSSafetyGuard(mode="edge_tiers", active_model=E4B_MODEL).is_active
    assert TTSSafetyGuard(mode="edge_tiers", active_model=E2B_MODEL).is_active
    assert not TTSSafetyGuard(mode="edge_tiers", active_model=B12_MODEL).is_active
    assert TTSSafetyGuard(mode="all", active_model=B12_MODEL).is_active
    assert not TTSSafetyGuard(mode="off", active_model=E4B_MODEL).is_active


def test_inactive_guard_allows_harm_text() -> None:
    """On 12B (edge_tiers mode) the guard is inactive and must not rewrite text."""
    guard = TTSSafetyGuard(mode="edge_tiers", active_model=B12_MODEL)
    assert guard.screen(CBRN_INSTRUCTION).allowed is True


def test_speak_text_replaces_blocked_utterance() -> None:
    mock_orch = MagicMock()
    manager = SpeechOutputManager(
        orchestrator=mock_orch,
        safety_guard=TTSSafetyGuard(mode="edge_tiers", active_model=E4B_MODEL),
    )
    trace = TurnTrace(trace_id="trace-guard-speak")
    manager.speak_text(trace, CBRN_INSTRUCTION)

    spoken = mock_orch.tts.synthesize.call_args.kwargs["text"]
    assert spoken == SAFE_REPLACEMENT
    assert CBRN_INSTRUCTION not in spoken


def test_speak_text_passes_benign_utterance_through() -> None:
    mock_orch = MagicMock()
    manager = SpeechOutputManager(
        orchestrator=mock_orch,
        safety_guard=TTSSafetyGuard(mode="edge_tiers", active_model=E4B_MODEL),
    )
    trace = TurnTrace(trace_id="trace-guard-benign")
    manager.speak_text(trace, BENIGN)

    spoken = mock_orch.tts.synthesize.call_args.kwargs["text"]
    assert spoken == BENIGN


def test_enqueue_tts_chunk_replaces_blocked_chunk() -> None:
    mock_orch = MagicMock()
    manager = SpeechOutputManager(
        orchestrator=mock_orch,
        safety_guard=TTSSafetyGuard(mode="edge_tiers", active_model=E2B_MODEL),
    )
    trace = TurnTrace(trace_id="trace-guard-chunk")
    manager.enqueue_tts_chunk(trace, 0, EXPLOSIVE_INSTRUCTION)

    item = manager.tts_queue.get_nowait()
    assert item is not None
    assert item[2] == SAFE_REPLACEMENT


def test_enqueue_tts_chunk_passes_benign_chunk_through() -> None:
    mock_orch = MagicMock()
    manager = SpeechOutputManager(
        orchestrator=mock_orch,
        safety_guard=TTSSafetyGuard(mode="edge_tiers", active_model=E2B_MODEL),
    )
    trace = TurnTrace(trace_id="trace-guard-chunk-benign")
    manager.enqueue_tts_chunk(trace, 0, BENIGN)

    item = manager.tts_queue.get_nowait()
    assert item is not None
    assert item[2] == BENIGN


def test_no_guard_preserves_existing_behavior() -> None:
    """safety_guard=None (default) keeps the pre-guard behavior exactly."""
    mock_orch = MagicMock()
    manager = SpeechOutputManager(orchestrator=mock_orch)
    trace = TurnTrace(trace_id="trace-guard-none")
    manager.speak_text(trace, CBRN_INSTRUCTION)

    spoken = mock_orch.tts.synthesize.call_args.kwargs["text"]
    assert spoken != SAFE_REPLACEMENT
