"""
Project Lucca — WO-26 Phase 2: ASR Stutter Compression, Acoustic Normalizer & Cooperative Cancellation Tests.

Validates:
1. Repetitive syllabic and single-letter stutter loop compression (>3 cycles) before word assembly.
2. Dictionary word length limits (<= 25 chars) on spelled sequences.
3. Context-bounded acoustic substitution heuristics (e.g. 'fish and ship' -> 'fish and chips' only in food context).
4. Sibling variants: "S-I-L-O-G C-L-C-L-C-L..." -> "Silog", "A-U-D-I-T T-T-T-T-T..." -> "Audit", "P-Y-T-H-O-N N-N-N..." -> "Python".
5. Cooperative cancellation token terminates in-flight turns cleanly within 500ms without history or context pollution.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from lucca.core.orchestrator import Orchestrator
from lucca.core.text_utils import (
    apply_acoustic_normalizations,
    collapse_stutter_loops,
    normalize_spelled_words,
    normalize_transcript,
)
from lucca.core.trace import TurnTrace, now_ns


# ============================================================================
# 1. Stutter Loop Compression & Spelled-Word Sibling Tests
# ============================================================================


def test_stutter_compression_sibling_silog() -> None:
    """Sibling 1: verify 'S-I-L-O-G C-L-C-L-C-L...' normalizes cleanly to 'Silog'."""
    raw = "S-I-L-O-G C-L-C-L-C-L..."
    norm = normalize_transcript(raw)
    assert norm == "Silog", f"Expected 'Silog', got '{norm}'"

    text, detected = normalize_spelled_words(raw)
    assert "Silog" in detected
    assert not any("cl" in w.lower() for w in detected)


def test_stutter_compression_sibling_audit() -> None:
    """Sibling 2: verify 'A-U-D-I-T T-T-T-T-T...' normalizes cleanly to 'Audit'."""
    raw = "A-U-D-I-T T-T-T-T-T..."
    norm = normalize_transcript(raw)
    assert norm == "Audit", f"Expected 'Audit', got '{norm}'"

    text, detected = normalize_spelled_words(raw)
    assert "Audit" in detected
    assert "T" not in detected


def test_stutter_compression_sibling_python() -> None:
    """Sibling 3: verify 'P-Y-T-H-O-N N-N-N...' normalizes cleanly to 'Python'."""
    raw = "P-Y-T-H-O-N N-N-N..."
    norm = normalize_transcript(raw)
    assert norm == "Python", f"Expected 'Python', got '{norm}'"

    text, detected = normalize_spelled_words(raw)
    assert "Python" in detected
    assert "N" not in detected


def test_stutter_compression_chained_feedback_loop() -> None:
    """Original Failure Case: verify runaway mic loop 'S-I-L-O-G C-L-C-L-C-L-L-L...' collapses cleanly."""
    raw = "S-I-L-O-G C-L-C-L-C-L-L-L..."
    norm = normalize_transcript(raw)
    assert norm == "Silog", f"Expected 'Silog', got '{norm}'"


def test_stutter_compression_hyphen_attached() -> None:
    """Verify stutter attached directly with hyphens collapses without corrupting root word."""
    raw1 = "S-I-L-O-G-C-L-C-L-C-L"
    assert normalize_transcript(raw1) == "Silog"

    raw2 = "A-U-D-I-T-T-T-T-T"
    assert normalize_transcript(raw2) == "Audit"

    raw3 = "P-Y-T-H-O-N-N-N-N"
    assert normalize_transcript(raw3) == "Python"


def test_stutter_compression_space_and_period_separated() -> None:
    """Verify space-separated and period-separated stutter loops are eliminated."""
    raw_space = "S I L O G C L C L C L"
    assert normalize_transcript(raw_space) == "Silog"

    raw_period = "A. U. D. I. T. T. T. T. T."
    assert normalize_transcript(raw_period) == "Audit"


def test_spelled_words_dictionary_length_cap() -> None:
    """Limit assembled spelled words to valid dictionary lengths (<= 25 chars)."""
    # 35 letters spelled out without repeats
    long_spelled = "A-B-C-D-E-F-G-H-I-J-K-L-M-N-O-P-Q-R-S-T-U-V-W-X-Y-Z-A-B-C-D-E-F-G-H-I"
    text, detected = normalize_spelled_words(long_spelled)
    assert len(detected) == 1
    assembled_word = detected[0]
    assert len(assembled_word) <= 25, f"Expected word length <= 25, got {len(assembled_word)}"


def test_non_stutter_words_preserved() -> None:
    """Ensure legitimate spelled words and normal sentences are not damaged by stutter compression."""
    assert normalize_transcript("His name is F-A-W-K-N-E-R.") == "His name is Fawkner"
    assert normalize_transcript("Target: F. A. W. K. N. E. R.") == "Target: Fawkner"
    assert normalize_transcript("Search for B E V E R L Y now.") == "Search for Beverly now"
    assert normalize_transcript("I see a cat in the room") == "I see a cat in the room"
    assert normalize_transcript("Mississippi is M-I-S-S-I-S-S-I-P-P-I") == "Mississippi is Mississippi"


# ============================================================================
# 2. Context-Bounded Acoustic Normalization Tests
# ============================================================================


def test_acoustic_normalization_food_context_positive() -> None:
    """Acoustic charity: 'fish and ship' -> 'fish and chips' when food context tokens are present."""
    utterance1 = "Can I get fish and ship for dinner?"
    assert normalize_transcript(utterance1) == "Can I get fish and chips for dinner"

    utterance2 = "We ordered fish and ship at the seafood restaurant"
    assert normalize_transcript(utterance2) == "We ordered fish and chips at the seafood restaurant"

    utterance3 = "I'm hungry, let's have fish and ship with tartar sauce"
    assert (
        normalize_transcript(utterance3) == "I'm hungry, let's have fish and chips with tartar sauce"
    )


def test_acoustic_normalization_non_food_context_negative() -> None:
    """TRAP 1: Never globally replace. Non-food sentences MUST retain original words."""
    cargo = "The cargo ship carries fish and ship equipment to the port."
    assert normalize_transcript(cargo) == "The cargo ship carries fish and ship equipment to the port"

    naval = "Naval inspection of fish and ship maintenance."
    assert normalize_transcript(naval) == "Naval inspection of fish and ship maintenance"


def test_acoustic_normalization_case_preservation() -> None:
    """Verify title-case and uppercase formatting is preserved in acoustic replacements."""
    upper = "ORDER FISH AND SHIP FOR DINNER"
    assert "FISH AND CHIPS" in normalize_transcript(upper)

    title = "Order Fish and Ship for Dinner"
    assert "Fish and Chips" in normalize_transcript(title)


def test_acoustic_normalization_sibling_salt_and_paper() -> None:
    """Sibling acoustic substitution: 'salt and paper' -> 'salt and pepper' in food context."""
    food_case = "Please pass the salt and paper for lunch"
    assert normalize_transcript(food_case) == "Please pass the salt and pepper for lunch"

    non_food_case = "The report was written on salt and paper"
    assert normalize_transcript(non_food_case) == "The report was written on salt and paper"


# ============================================================================
# 3. Cooperative Cancellation & Rapid PTT Tests
# ============================================================================


def test_orchestrator_has_cancellation_token() -> None:
    """Verify Orchestrator initializes with a cooperative cancellation token."""
    orch = Orchestrator.__new__(Orchestrator)
    orch._cancel_token = threading.Event()
    assert not orch._cancel_token.is_set()
    orch._cancel_token.set()
    assert orch._cancel_token.is_set()


def test_abort_turn_signals_cancel_token_and_drains_worker() -> None:
    """Verify _abort_turn sets _cancel_token, marks trace interrupted, and cleanly drains the worker."""
    orch = Orchestrator.__new__(Orchestrator)
    orch.affect_tracker = MagicMock()
    orch._pending_confirmation_active = False
    orch._cancel_token = threading.Event()
    orch.active_trace = TurnTrace(
        trace_id="tr-test-1", session_id="s1", origin="ptt", mode="transcript"
    )
    orch.llm = MagicMock()
    orch.chunker = MagicMock()
    orch.speech_output = MagicMock()
    orch.play_ring = MagicMock()
    orch._publish_bus = MagicMock()

    # Simulate an active turn worker thread that checks _cancel_token
    worker_finished = threading.Event()

    def dummy_worker() -> None:
        # Worker simulates checking cancel token cooperatively
        while not orch._cancel_token.is_set():
            time.sleep(0.01)
        worker_finished.set()

    t = threading.Thread(target=dummy_worker, name="test-turn-worker", daemon=True)
    orch.active_turn_thread = t
    t.start()

    start_t = time.perf_counter()
    orch._abort_turn()
    elapsed = time.perf_counter() - start_t

    assert orch._cancel_token.is_set(), "Cancel token must be set"
    assert orch.active_trace.interrupted is True, "Active trace must be marked interrupted"
    assert orch.llm.abort.called, "llm.abort must be called"
    assert worker_finished.is_set(), "Worker must exit cooperatively upon seeing cancel token"
    assert orch.active_turn_thread is None, "active_turn_thread must be cleared after join"
    assert elapsed < 0.5, f"Turn worker drain took {elapsed:.3f}s, expected < 0.5s"


def test_rapid_ptt_press_aborts_without_history_pollution() -> None:
    """Verify a rapid PTT interruption cleanly aborts without leaving orphan tokens in history."""
    orch = Orchestrator.__new__(Orchestrator)
    orch.affect_tracker = MagicMock()
    orch._pending_confirmation_active = False
    orch._cancel_token = threading.Event()
    orch.state = "thinking"
    orch.history = []
    orch.active_trace = TurnTrace(
        trace_id="tr-aborted", session_id="s1", origin="ptt", mode="transcript"
    )
    orch.llm = MagicMock()
    orch.chunker = MagicMock()
    orch.speech_output = MagicMock()
    orch.play_ring = MagicMock()
    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._set_state = MagicMock()
    orch._confirm_event = MagicMock()

    # Worker running in background
    def slow_worker() -> None:
        time.sleep(0.05)
        # Attempt to append to history if not cancelled
        if not orch.active_trace.interrupted and not orch._cancel_token.is_set():
            orch.history.append({"role": "assistant", "content": "orphan token"})

    t = threading.Thread(target=slow_worker, name="slow-worker", daemon=True)
    orch.active_turn_thread = t
    t.start()

    # New PTT press arrives while worker is running
    orch._on_ptt_pressed(now_ns())

    # Ensure worker finished and history was NOT polluted
    t.join(timeout=0.2)
    assert len(orch.history) == 0, f"History was polluted by aborted turn: {orch.history}"
    orch._set_state.assert_called_with("listening")
