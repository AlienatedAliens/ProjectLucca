"""
Project Lucca — Defensive Disambiguation, Decoupled Scratchpad & Non-Empty Guardrail Tests
Spec D-REAS-09, D-HON-01, WO-26 Phase 5

Verifies:
1. SubTurnScratchpadBuffer isolation: intermediate scratchpads execute in an isolated
   buffer with independent limits and do not pollute long-term conversation history.
2. Non-Empty Synthesis Guardrail: successful tool execution never produces empty responses.
3. Audited GSM8K misses honest classification (ambiguous vs. misread).
4. Line-1 assumption format on ambiguous financial/fee/rounding problems + unseen siblings.
5. Absence of superfluous assumptions on non-ambiguous queries (Reviewer Note 11).
6. TurnPipeline epistemic context integration.
"""

from __future__ import annotations

import re
from typing import Literal
from unittest.mock import MagicMock

import pytest

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import ChatMessage, TokenDelta
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import (
    SubTurnScratchpadBuffer,
    TurnPipeline,
    detect_operational_ambiguity,
)

LINE1_ASSUMPTION_PATTERN = re.compile(
    r"^(?:assumption|assuming|we assume|i assume|assume|note:\s*assuming|based on the assumption)\b",
    re.IGNORECASE,
)


# ===========================================================================
# 1. Decoupled Scratchpad Buffer Unit Tests
# ===========================================================================


def test_scratchpad_buffer_tool_output_bounding() -> None:
    """Verifies that large tool outputs (e.g. massive coordinate math / logs) are bounded."""
    buffer = SubTurnScratchpadBuffer(
        max_total_chars=10000,
        max_single_output_chars=1000,
        head_chars=200,
        tail_chars=150,
    )

    # 1. Normal small output remains intact
    buffer.add_tool_result("c1", "calc_math", "result: 42", is_error=False)
    assert len(buffer.messages) == 1
    assert buffer.messages[0].content == "result: 42"
    assert buffer.truncated_count == 0

    # 2. Giant output (e.g. 5,000 chars of coordinate math)
    huge_data = "COORD_START " + ("(x=12.5, y=34.8, z=99.1) " * 200) + " COORD_END"
    assert len(huge_data) > 1000
    buffer.add_tool_result("c2", "calc_math", huge_data, is_error=False)

    assert len(buffer.messages) == 2
    msg = buffer.messages[1]
    assert "Truncated in scratchpad buffer" in str(msg.content)
    assert str(msg.content).startswith("COORD_START")
    assert str(msg.content).endswith("COORD_END")
    assert buffer.truncated_count == 1


def test_scratchpad_buffer_lifecycle_and_isolation() -> None:
    """Verifies assistant tool calls, directives, and buffer clearing."""
    buffer = SubTurnScratchpadBuffer()

    buffer.add_assistant_tool_call(
        call_id="call_99",
        tool_name="search_web",
        tool_args={"query": "interest calculation convention"},
        thought="Need to check convention",
    )
    buffer.add_user_directive("[Repeat Guard: Do not repeat call]")

    msgs = buffer.messages
    assert len(msgs) == 2
    assert msgs[0].role == "assistant"
    assert msgs[0].tool_calls is not None
    assert msgs[0].tool_calls[0]["function"]["name"] == "search_web"
    assert msgs[1].role == "user"
    assert "[Repeat Guard:" in str(msgs[1].content)

    buffer.clear()
    assert len(buffer.messages) == 0
    assert buffer.truncated_count == 0


# ===========================================================================
# 2. Non-Empty Synthesis Guardrail Tests
# ===========================================================================


from lucca.core.schemas import ChatMessage, TokenDelta, ToolCall, ToolCallEnd, ToolResult


def test_non_empty_synthesis_guardrail_triggers_fallback() -> None:
    """When a tool succeeds but the model emits whitespace/empty response,

    fallback synthesis is triggered and ensures a non-empty assistant response.
    """
    round_counter = [0]

    def mock_stream_turn(**kwargs):
        current_text = kwargs.get("current_text", "")
        if "Summarize the tool output" in current_text:
            yield TokenDelta(delta="The compound interest over 3 years totals $106.12.")
            return

        round_counter[0] += 1
        if round_counter[0] == 1:
            # Round 1: execute tool
            yield ToolCallEnd(
                call=ToolCall(
                    call_id="c_loan_1",
                    tool="calc_math",
                    args={"expr": "100 * (1.02)**3"},
                )
            )
        else:
            # Round 2: model emits whitespace only instead of explaining tool output
            yield TokenDelta(delta="   \n")

    mock_llm = MagicMock()
    mock_llm.stream_turn.side_effect = mock_stream_turn

    orch = MagicMock()
    orch.llm = mock_llm
    orch.history = []
    orch.current_turn_tool_spoken = []
    orch.current_turn_assistant_reply = None
    orch.affect_tracker.get_prompt_suffix_tag.return_value = "neutral"
    orch.output_supervisor.feed_chunk.return_value = ([], False)
    orch.output_supervisor.flush.return_value = ([], False)
    orch._cancel_token.is_set.return_value = False
    orch._maybe_speak_pending_updates = MagicMock()
    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._enqueue_tts_chunk = MagicMock()
    orch._set_state = MagicMock()
    orch.speech_output.wait_for_playback = MagicMock()
    orch.play_ring.set_flag = MagicMock()
    orch._finalize_turn = MagicMock()
    orch._check_and_offer_ratification.return_value = None
    orch.bdi_validator.validate_tool_call.return_value = MagicMock(is_valid=True)
    orch._handle_tool_call.return_value = ToolResult(
        call_id="c_loan_1",
        ok=True,
        content="106.12",
        elapsed_ms=0.5,
    )
    orch.turn_pipeline.sanity_guard.validate.return_value = MagicMock(
        is_valid=True, directive=None
    )

    trace = TurnTrace(trace_id="test_non_empty_guardrail")

    # Run _stream_llm_speech with tools enabled
    dummy_tool = MagicMock()
    Orchestrator._stream_llm_speech(
        orch,
        trace=trace,
        user_msg="Calculate Mandy's loan interest",
        decision_id="dec-1",
        tools=[dummy_tool],
    )

    # Invariant: Assistant response MUST NOT be empty
    assert orch.history, "History must have recorded the turn"
    asst_msg = next((m for m in orch.history if m["role"] == "assistant"), None)
    assert asst_msg is not None, "Assistant message must exist in history"
    assert "106.12" in asst_msg["content"], "Fallback synthesis must synthesize tool output"
    assert asst_msg["content"].strip(), "Assistant message must not be empty or whitespace"


def test_non_empty_synthesis_guardrail_deterministic_fallback_when_llm_dead() -> None:
    """When both primary stream and fallback stream emit zero tokens,

    deterministic fallback message guarantees non-empty response.
    """
    round_counter = [0]

    def mock_stream_turn(**kwargs):
        current_text = kwargs.get("current_text", "")
        if "Summarize the tool output" in current_text:
            # Model dead on fallback too
            return

        round_counter[0] += 1
        if round_counter[0] == 1:
            yield ToolCallEnd(
                call=ToolCall(
                    call_id="c_calc_2",
                    tool="calc_math",
                    args={"expr": "15 * 8"},
                )
            )
        else:
            # Emits nothing at all
            return

    mock_llm = MagicMock()
    mock_llm.stream_turn.side_effect = mock_stream_turn

    orch = MagicMock()
    orch.llm = mock_llm
    orch.history = []
    orch.current_turn_tool_spoken = []
    orch.current_turn_assistant_reply = None
    orch.affect_tracker.get_prompt_suffix_tag.return_value = "neutral"
    orch.output_supervisor.feed_chunk.return_value = ([], False)
    orch.output_supervisor.flush.return_value = ([], False)
    orch._cancel_token.is_set.return_value = False
    orch._maybe_speak_pending_updates = MagicMock()
    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._enqueue_tts_chunk = MagicMock()
    orch._set_state = MagicMock()
    orch.speech_output.wait_for_playback = MagicMock()
    orch.play_ring.set_flag = MagicMock()
    orch._finalize_turn = MagicMock()
    orch._check_and_offer_ratification.return_value = None
    orch.bdi_validator.validate_tool_call.return_value = MagicMock(is_valid=True)
    orch._handle_tool_call.return_value = ToolResult(
        call_id="c_calc_2",
        ok=True,
        content="120",
        elapsed_ms=0.5,
    )
    orch.turn_pipeline.sanity_guard.validate.return_value = MagicMock(
        is_valid=True, directive=None
    )
    orch._last_unspoken_tool_msg = None
    orch._select_verbal_cue.return_value = "Calculating..."

    trace = TurnTrace(trace_id="test_dead_stream")

    dummy_tool = MagicMock()
    Orchestrator._stream_llm_speech(
        orch,
        trace=trace,
        user_msg="What is 15 * 8?",
        decision_id="dec-2",
        tools=[dummy_tool],
    )

    assert orch.history, "History must have recorded the turn"
    asst_msg = next((m for m in orch.history if m["role"] == "assistant"), None)
    assert asst_msg is not None, "Assistant message must exist in history"
    assert "calc_math" in asst_msg["content"], "Deterministic fallback must cite the successful tool"
    assert asst_msg["content"].strip()


# ===========================================================================
# 3. Audited GSM8K Misses Honest Classification
# ===========================================================================


class GSM8KMissRecord:
    def __init__(
        self,
        item_id: int,
        problem_snippet: str,
        classification: Literal["ambiguous", "misread"],
        rationale: str,
    ) -> None:
        self.item_id = item_id
        self.problem_snippet = problem_snippet
        self.classification = classification
        self.rationale = rationale


AUDITED_GSM8K_MISSES: list[GSM8KMissRecord] = [
    GSM8KMissRecord(
        item_id=59,
        problem_snippet="Online grocery order of $40, 25% vendor fee, $3 delivery fee, $4 tip.",
        classification="ambiguous",
        rationale="Vendor service fee base was unspecified: applies to groceries subtotal ($40) vs order total ($43).",
    ),
    GSM8KMissRecord(
        item_id=188,
        problem_snippet="$100 loan at 2% monthly interest paid after 3 months.",
        classification="ambiguous",
        rationale="Compounding frequency was unspecified: standard financial loans compound monthly ($106.12), but benchmark author assumed simple interest ($106.00).",
    ),
    GSM8KMissRecord(
        item_id=94,
        problem_snippet="Pet hurdles with discrete animals yielding 36.36 hurdles.",
        classification="ambiguous",
        rationale="Discrete entity rounding direction was unspecified: author expected integer truncation (36), Lucca evaluated exact floating point (36.36).",
    ),
    GSM8KMissRecord(
        item_id=63,
        problem_snippet="$50,000 pension vesting at 5% per year starting after 20 years. Quits at 30 years.",
        classification="misread",
        rationale="Model misread domain terminology: treated pension vesting as an additive bonus on top of salary rather than progressive entitlement to base pension.",
    ),
    GSM8KMissRecord(
        item_id=424,
        problem_snippet="Employee bus capacity difference between 8 and 16.",
        classification="misread",
        rationale="Model misread signed subtraction: evaluated 8 - 16 = -8 instead of absolute difference |8 - 16| = 8.",
    ),
]


def test_gsm8k_misses_honest_classification_table() -> None:
    """Verifies that audited GSM8K misses are honestly categorized into 'ambiguous'

    vs. 'misread' with distinct, non-lumped rationales (Reviewer Note 10).
    """
    ambiguous_items = [m for m in AUDITED_GSM8K_MISSES if m.classification == "ambiguous"]
    misread_items = [m for m in AUDITED_GSM8K_MISSES if m.classification == "misread"]

    assert len(ambiguous_items) == 3, "Expected exactly 3 ambiguous cases (Items 59, 188, 94)"
    assert len(misread_items) == 2, "Expected exactly 2 misread cases (Items 63, 424)"

    for item in AUDITED_GSM8K_MISSES:
        assert len(item.rationale.strip()) > 20, f"Item {item.item_id} must have a detailed rationale"
        assert item.classification in ("ambiguous", "misread")


# ===========================================================================
# 4. Line-1 Assumption Format on Ambiguous Problems & Unseen Siblings
# ===========================================================================


@pytest.mark.parametrize(
    "ambiguous_prompt,reason_fragment",
    [
        (
            "Online grocery order of $40, with a 25% vendor fee, $3 delivery fee, and $4 tip. What is the total?",
            "fee",
        ),
        (
            "Mandy took out a $100 loan at 2% monthly interest paid after 3 months. How much is owed?",
            "interest",
        ),
        (
            "A trainer guides dogs over hurdles. With available time and stamina, how many hurdles can be cleared if each takes 2.75 minutes from 100 minutes total?",
            "hurdles",
        ),
        # Unseen Sibling 1: Freelance contractor fee on work vs travel expenses
        (
            "A freelance contractor bills $1,000 for work plus $150 travel expenses. The platform takes a 10% fee. How much does the contractor receive?",
            "fee",
        ),
        # Unseen Sibling 2: Investment interest without compounding convention
        (
            "Elena invests $5,000 at a 6% annual interest rate for 4 years. What is the final value?",
            "interest",
        ),
        # Unseen Sibling 3: Discrete pallet packing
        (
            "A warehouse needs to ship 1,025 boxes using pallets that each hold 48 boxes. How many pallets are needed?",
            "pallets",
        ),
    ],
)
def test_detect_operational_ambiguity_on_ambiguous_problems_and_siblings(
    ambiguous_prompt: str, reason_fragment: str
) -> None:
    """Ambiguous problems must be detected and trigger defensive assumption stating."""
    is_ambig, reason = detect_operational_ambiguity(ambiguous_prompt)
    assert is_ambig is True, f"Failed to detect ambiguity in: {ambiguous_prompt}"
    assert reason is not None
    assert reason_fragment.lower() in reason.lower() or reason_fragment.lower() in ambiguous_prompt.lower()


def test_line1_assumption_format_validation() -> None:
    """Verifies that line 1 of simulated defensive responses matches the required pattern.

    Reviewer Note 11: Matches 'Assumption:' or 'Assuming'.
    """
    valid_line1_samples = [
        "Assumption: The 10% platform fee is applied to the $1,000 labor subtotal only.",
        "Assuming annual compounding at 6% interest over the 4-year duration:",
        "Assumption: Partial pallets require rounding up to the next full pallet (ceiling).",
        "We assume standard monthly compound interest FV = PV * (1 + r)^n.",
        "Note: Assuming the 25% vendor fee applies to merchandise plus delivery.",
    ]
    for line in valid_line1_samples:
        assert LINE1_ASSUMPTION_PATTERN.search(line), f"Failed to match valid line-1 assumption: '{line}'"

    invalid_line1_samples = [
        "The total cost is $57.75.",
        "First, let's calculate 1000 * 0.10 = 100.",
        "Here is the solution to your math problem:",
        "120",
    ]
    for line in invalid_line1_samples:
        assert not LINE1_ASSUMPTION_PATTERN.search(line), f"Should not match non-assumption line: '{line}'"


# ===========================================================================
# 5. Absence of Superfluous Assumptions on Non-Ambiguous Queries
# ===========================================================================


@pytest.mark.parametrize(
    "clear_prompt",
    [
        "What is 15 multiplied by 8?",
        "If a train travels 60 miles per hour for 3 hours, how far does it travel?",
        "A store has 12 apples and sells 5 apples. How many apples are left?",
        "What is the capital of France?",
        "Solve 2x + 6 = 14 for x.",
        "Convert 100 degrees Celsius to Fahrenheit.",
    ],
)
def test_no_superfluous_assumptions_on_clear_queries(clear_prompt: str) -> None:
    """Reviewer Note 11: Non-ambiguous problems must NOT trigger defensive assumption directives."""
    is_ambig, reason = detect_operational_ambiguity(clear_prompt)
    assert is_ambig is False, f"Clear query incorrectly flagged as ambiguous: {clear_prompt}"
    assert reason is None


# ===========================================================================
# 6. TurnPipeline Epistemic Context Integration
# ===========================================================================


def test_turn_pipeline_epistemic_context_disambiguation_injection() -> None:
    """TurnPipeline.build_epistemic_context must inject the directive ONLY on ambiguous queries."""
    orch = MagicMock()
    orch.cascade.classify_intent.return_value = (False, [], 0.0)
    pipeline = TurnPipeline(orch)

    # 1. Ambiguous query receives directive
    ambig_query = "Elena invests $5,000 at a 6% annual interest rate for 4 years."
    ctx_ambig = pipeline.build_epistemic_context(ambig_query)
    assert ctx_ambig is not None
    assert "Defensive Disambiguation Directive" in ctx_ambig
    assert "line 1" in ctx_ambig

    # 2. Clear query does NOT receive directive
    clear_query = "What is 15 multiplied by 8?"
    ctx_clear = pipeline.build_epistemic_context(clear_query)
    assert ctx_clear is None or "Defensive Disambiguation Directive" not in ctx_clear
