"""
Project Lucca — Operational Cleanups Tests (WO-23 Phase 0).
Spec 06 §2, Spec 08 §3, Spec 11 §1, V2_ACTION_LOG (ITEM-018, ITEM-023, ITEM-028).

Validates:
1. ITEM-018: Canonical normalize_transcript behavior and Router vs Rule Engine input parity.
2. ITEM-023: Calendar-day rotation and retention pruning for decisions.jsonl.
3. ITEM-028: Voice narration markdown sanitization (sanitize_for_voice).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from lucca.brain.chunker import sanitize_for_voice
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    DecisionRecord,
    ExecutionTier,
    RouteAction,
    RouteDecision,
    RouteFeatures,
)
from lucca.core.text_utils import normalize_transcript
from lucca.router.heuristic import HeuristicRouter

# ============================================================================
# Section 1: ITEM-018 Canonical Transcript Normalizer & Parity
# ============================================================================


def test_normalize_transcript_basic_cleaning() -> None:
    """Verifies stripping whitespace, collapsing internal spaces, and trailing punctuation."""
    assert normalize_transcript("") == ""
    assert normalize_transcript("   ") == ""
    assert normalize_transcript("  hello   world  ") == "hello world"
    assert normalize_transcript("What time is it???") == "What time is it"
    assert (
        normalize_transcript("Open the pod bay doors, please.") == "Open the pod bay doors, please"
    )
    assert normalize_transcript("System alert!!!") == "System alert"
    assert normalize_transcript("Search for Beverly Quintos...") == "Search for Beverly Quintos"


def test_normalize_transcript_unicode_punctuation() -> None:
    """Verifies smart quotes, typographic dashes, and non-breaking spaces are normalized."""
    raw = "What’s the weather in Melbourne—Australia?"
    expected = "What's the weather in Melbourne-Australia"
    assert normalize_transcript(raw) == expected

    quotes_raw = "She said “hello world”."
    assert normalize_transcript(quotes_raw) == 'She said "hello world"'

    curly_apostrophe = "Don’t quit now!"
    assert normalize_transcript(curly_apostrophe) == "Don't quit now"


def test_normalize_transcript_spelled_words_assembly() -> None:
    """Verifies single-letter spelling sequences are assembled into title-cased words."""
    # Hyphenated
    assert normalize_transcript("His name is F-A-W-K-N-E-R.") == "His name is Fawkner"
    # Period-separated
    assert normalize_transcript("Target: F. A. W. K. N. E. R.") == "Target: Fawkner"
    # Space-separated
    assert normalize_transcript("Search for B E V E R L Y now.") == "Search for Beverly now"


def test_router_and_rule_engine_transcript_parity() -> None:
    """
    ITEM-018 Property Test: For a diverse corpus of utterances (punctuation,
    casing, contractions, spelled words), the text seen by HeuristicRouter
    and MicroScheme rule engine is identical: router.sees == rule_engine.sees.
    """
    corpus = [
        "Open calculator.",
        "OPEN CALCULATOR!",
        "  open   calculator...  ",
        "What's the weather today?",
        "Don't stop the music!",
        "Target is F-A-W-K-N-E-R.",
        "Look up F. A. W. K. N. E. R. on Wikipedia.",
        "Could you search for “Beverly Quintos” online?",
        "Read file notes.txt; please!",
        "Run terminal—immediately.",
    ]

    orch = Orchestrator.__new__(Orchestrator)
    orch.executed_tools = []
    orch.current_turn_tool_ok = True
    orch.history = []
    orch.router = HeuristicRouter()

    for utterance in corpus:
        # 1. Normalization at ASR boundary
        norm = normalize_transcript(utterance)

        # 2. RuleState built for rule engine
        rule_state = orch._build_rule_state(utterance)

        # 3. Router classification
        router_intent, _, router_entities = orch.router.classify_intent(utterance)

        # Invariant 1: RuleState transcript is the normalized transcript
        assert rule_state.transcript == norm, (
            f"RuleState transcript '{rule_state.transcript}' != norm '{norm}'"
        )

        # Invariant 2: Router classification matches RuleState intent & entities exactly
        assert rule_state.intent == router_intent, (
            f"Intent mismatch: {rule_state.intent} != {router_intent} for '{utterance}'"
        )
        assert rule_state.entities == router_entities, (
            f"Entities mismatch: {rule_state.entities} != {router_entities} for '{utterance}'"
        )

        # Invariant 3: Router route() logs the exact normalized transcript
        _ = orch.router.route(utterance)
        assert orch.router.last_decision_record is not None
        assert orch.router.last_decision_record.features.transcript == norm, (
            f"DecisionRecord transcript '{orch.router.last_decision_record.features.transcript}' != '{norm}'"
        )


# ============================================================================
# Section 2: ITEM-023 Decision Log Calendar-Day Rotation & Pruning
# ============================================================================


def _make_dummy_decision_record(decision_id: str, ts: float, transcript: str) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        trace_id=f"tr-{decision_id}",
        session_id="sess-01",
        ts=ts,
        features=RouteFeatures(
            transcript=transcript,
            any_active_rule_fired=False,
            any_quarantine_rule_fired=False,
            vad_speech_ms=1000,
            intent="launch_app",
            intent_conf=0.95,
            hour_local=12,
            weekday=1,
            apps_running=[],
            last_tool=None,
            last_tool_ok=None,
            session_turns=0,
            mode="transcript",
            has_registered_rule=False,
        ),
        decision=RouteDecision(
            action=RouteAction.RULE,
            tier=ExecutionTier.REFLEX,
            probabilities={"RULE": 0.95, "LLM": 0.05, "CLARIFY": 0.0},
            prediction_set=[RouteAction.RULE],
            fallback_applied=False,
            elapsed_us=500,
        ),
        router_version="heuristic-1.0-deterministic",
        executed_path="RULE",
        counterfactual_rule_fired=False,
    )


def test_decision_log_rotation_on_date_rollover(tmp_path: Path) -> None:
    """
    ITEM-023: On write, if the existing file belongs to a prior calendar day (UTC),
    it is rotated to decisions-YYYY-MM-DD.jsonl, and the new record is written
    to a fresh decisions.jsonl. Zero lines lost across boundary.
    """
    log_file = tmp_path / "logs" / "decisions.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    router = HeuristicRouter(log_path=log_file, retention_files=14)

    # Day 1: 2026-09-25 UTC
    day1_dt = datetime(2026, 9, 25, 14, 30, 0, tzinfo=UTC)
    rec1 = _make_dummy_decision_record("dec-01", day1_dt.timestamp(), "open calculator")
    router._log_decision_jsonl(rec1)

    rec2 = _make_dummy_decision_record(
        "dec-02", (day1_dt + timedelta(minutes=5)).timestamp(), "open terminal"
    )
    router._log_decision_jsonl(rec2)

    assert log_file.exists()
    lines_day1 = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines_day1) == 2

    # Simulate Day 1 file mtime
    import os

    os.utime(log_file, (day1_dt.timestamp(), day1_dt.timestamp()))

    # Day 2: 2026-09-26 UTC
    day2_dt = datetime(2026, 9, 26, 9, 0, 0, tzinfo=UTC)
    rec3 = _make_dummy_decision_record("dec-03", day2_dt.timestamp(), "open browser")
    router._log_decision_jsonl(rec3)

    # Verification:
    # 1. Rotated file decisions-2026-09-25.jsonl exists with day 1 records
    rotated_day1 = tmp_path / "logs" / "decisions-2026-09-25.jsonl"
    assert rotated_day1.exists(), f"Rotated file missing: {rotated_day1}"
    rotated_lines = rotated_day1.read_text(encoding="utf-8").strip().splitlines()
    assert len(rotated_lines) == 2
    assert "dec-01" in rotated_lines[0]
    assert "dec-02" in rotated_lines[1]

    # 2. Active decisions.jsonl contains ONLY day 2 record
    active_lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(active_lines) == 1
    assert "dec-03" in active_lines[0]

    # 3. Zero data loss: 2 in rotated + 1 in active == 3 total
    assert len(rotated_lines) + len(active_lines) == 3


def test_decision_log_retention_pruning(tmp_path: Path) -> None:
    """
    ITEM-023: Pruning keeps the most recent 14 rotated files and deletes older files.
    """
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    active_log = logs_dir / "decisions.jsonl"

    # Seed 16 rotated files from 2026-09-01 to 2026-09-16
    for day in range(1, 17):
        file_name = f"decisions-2026-09-{day:02d}.jsonl"
        (logs_dir / file_name).write_text(f'{{"day": {day}}}\n', encoding="utf-8")

    router = HeuristicRouter(log_path=active_log, retention_files=14)

    # Execute pruning
    deleted = router._prune_rotated_decision_logs()
    assert len(deleted) == 2
    deleted_names = {p.name for p in deleted}
    assert deleted_names == {"decisions-2026-09-01.jsonl", "decisions-2026-09-02.jsonl"}

    # Verify exactly 14 rotated files remain (days 03 to 16)
    remaining_rotated = sorted(p.name for p in logs_dir.glob("decisions-*.jsonl"))
    assert len(remaining_rotated) == 14
    assert remaining_rotated[0] == "decisions-2026-09-03.jsonl"
    assert remaining_rotated[-1] == "decisions-2026-09-16.jsonl"


# ============================================================================
# Section 3: ITEM-028 Markdown Voice Sanitization
# ============================================================================


def test_sanitize_for_voice_strips_markdown() -> None:
    """
    ITEM-028: Verifies sanitize_for_voice strips bold, emphasis, code fences,
    headers, bullet lists, and raw URLs so TTS receives clean prosodic text.
    """
    raw_narration = (
        "# Summary of Results\n"
        "I found **three** distinct sources on *Beverly Quintos*:\n"
        "- First result: https://example.com/bio\n"
        "- Second result: [Official Profile](https://court.gov.ph/profile)\n"
        "Here is the code executed:\n"
        "```python\n"
        "calc_result = 42 * 2\n"
        "```\n"
        "Everything was verified `successfully`."
    )

    clean = sanitize_for_voice(raw_narration)

    # 1. No markdown bold/italics markers
    assert "**" not in clean
    assert "*" not in clean
    assert "#" not in clean
    assert "`" not in clean

    # 2. Bare URL replaced with "a link"
    assert "https://" not in clean
    assert "a link" in clean

    # 3. Markdown link text preserved, URL stripped
    assert "Official Profile" in clean
    assert "court.gov.ph" not in clean

    # 4. Spoken text contains words naturally
    assert "three" in clean
    assert "Beverly Quintos" in clean
    assert "successfully" in clean
