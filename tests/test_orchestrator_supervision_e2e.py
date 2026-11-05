"""
End-to-End Orchestrator Supervision & Self-Correction Loop Tests (WO-40 Milestone 2.2).

Verifies that the production Orchestrator._stream_llm_speech loop:
1. Intercepts ungrounded completed, progressive, copular, elliptical, and simulated-inspection
   action claims when no matching ToolReceipt exists in the turn.
2. Discards the rejected Round 1 draft text from `full_response_text` (preventing the
   Round-1 + Round-2 buffer concatenation bug) when Round 2 produces a replacement reply or tool call.
3. Injects the `[Honesty & Grounding Directive]` so Round 2 either calls a real tool or
   outputs an honest capability disclosure.
4. Passes meta-linguistic, creative, and translation turns in a single round without false-positive
   re-prompting.
"""

from collections import deque
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    ExecutionTier,
    LLMUsage,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
    ToolResult,
)
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore
from lucca.sandbox.output_supervisor import OutputSupervisorSession
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def e2e_orch(tmp_path: Path) -> Orchestrator:
    db = DatabaseManager(tmp_path / "test_wo40_orch_e2e.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    orch = Orchestrator.__new__(Orchestrator)
    orch.config = get_config()
    orch.execute_tools = True
    orch.state = "idle"
    orch.running = True
    orch.db = db
    orch.memory_store = store
    orch.current_turn_receipts = []
    orch.current_turn_tool_calls = []
    orch.current_turn_tier = ExecutionTier.FULL_LOOP
    orch.current_turn_tool_spoken = []
    orch.current_turn_tool_ok = True
    orch.pending_spoken_updates = deque()
    orch.history = []
    orch.executed_tools = []
    orch.current_turn_transcript = None
    orch.current_turn_assistant_reply = None
    orch.active_trace = None
    orch._last_unspoken_tool_msg = None
    orch.rule_engine = MagicMock(rules={})
    orch.output_supervisor = OutputSupervisorSession()
    orch.sandbox = MagicMock()
    orch.sandbox.check_confirmation_needed.return_value = False
    orch.sandbox.execute_tool.return_value = ToolResult(
        call_id="call-1", ok=True, exit_code=0, content="Note saved.", elapsed_ms=1.0
    )
    orch.affect_tracker = MagicMock()
    orch.affect_tracker.get_prompt_suffix_tag.return_value = ""
    orch.play_ring = MagicMock()
    orch._tts_queue = MagicMock()
    orch.speech_output = MagicMock()
    orch.tts = MagicMock()
    orch.asr = MagicMock()
    orch.bdi_validator = MagicMock()
    orch.bdi_validator.validate_tool_call.return_value = MagicMock(is_valid=True)
    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._set_state = MagicMock()
    orch._finalize_turn = MagicMock()
    return orch


def test_ungrounded_companion_claim_intercepted_and_buffer_replaced(e2e_orch: Orchestrator) -> None:
    """
    Round 1 hallucinates muting microphone and turning on Night Light without a tool call.
    Orchestrator intercepts the ungrounded claim, injects the Honesty & Grounding Directive,
    wipes Round 1's hallucinated text when Round 2 streams, and records only Round 2's
    honest reply in `current_turn_assistant_reply`.
    """
    e2e_orch.llm = FakeLLM(
        rounds=[
            [
                TokenDelta(delta="I've muted your microphone and turned on Night Light for you."),
                Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=12)),
            ],
            [
                TokenDelta(
                    delta="I don't have access to your microphone or display settings, so I haven't changed them."
                ),
                Done(usage=LLMUsage(prompt_tokens=25, completion_tokens=16)),
            ],
        ]
    )
    trace = TurnTrace(trace_id="tr-wo40-1")
    e2e_orch._stream_llm_speech(
        trace=trace,
        user_msg="Can you mute my microphone and turn on Night Light?",
        decision_id=None,
        memories=[],
    )
    assert e2e_orch.llm.call_count == 2
    assert e2e_orch.current_turn_assistant_reply == (
        "I don't have access to your microphone or display settings, so I haven't changed them."
    )
    assert "I've muted your microphone" not in (e2e_orch.current_turn_assistant_reply or "")


def test_simulated_inspection_readout_intercepted_in_orchestrator(e2e_orch: Orchestrator) -> None:
    """
    Round 1 announces a live calendar check and fabricates a 2:30 PM meeting in the same turn
    with zero tool calls. Orchestrator intercepts it and replaces it with Round 2's honest reply.
    """
    e2e_orch.llm = FakeLLM(
        rounds=[
            [
                TokenDelta(
                    delta="Let me check your schedule for this afternoon. Yep, you have a meeting at 2:30 PM."
                ),
                Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=18)),
            ],
            [
                TokenDelta(
                    delta="I cannot check your calendar directly because I do not have a calendar integration tool."
                ),
                Done(usage=LLMUsage(prompt_tokens=30, completion_tokens=16)),
            ],
        ]
    )
    trace = TurnTrace(trace_id="tr-wo40-2")
    e2e_orch._stream_llm_speech(
        trace=trace,
        user_msg="Do I have any meetings this afternoon?",
        decision_id=None,
        memories=[],
    )
    assert e2e_orch.llm.call_count == 2
    assert e2e_orch.current_turn_assistant_reply == (
        "I cannot check your calendar directly because I do not have a calendar integration tool."
    )
    assert "2:30 PM" not in (e2e_orch.current_turn_assistant_reply or "")


def test_ungrounded_claim_triggers_real_tool_call_in_round_2(e2e_orch: Orchestrator) -> None:
    """
    Round 1 claims a note was saved without calling `note_write`.
    Orchestrator intercepts Round 1 -> Round 2 invokes `note_write` -> Round 3 narrates grounded success.
    """
    from lucca.core.coherence import ToolReceipt

    note_call = ToolCall(
        tool="note_write",
        args={"title": "todo", "content": "buy milk"},
        call_id="call-note-1",
    )

    def fake_handle_tool_call(trace_obj, tool_name, tool_args, speak=False):
        e2e_orch.executed_tools.append((tool_name, tool_args))
        e2e_orch.current_turn_receipts.append(
            ToolReceipt(tool=tool_name, ok=True, call_id="call-note-1", args=tool_args)
        )
        return ToolResult(
            call_id="call-note-1", ok=True, exit_code=0, content="Saved todo", elapsed_ms=1.0
        )

    e2e_orch._handle_tool_call = fake_handle_tool_call  # type: ignore[method-assign]
    e2e_orch.llm = FakeLLM(
        rounds=[
            [
                TokenDelta(delta="I saved your note to todo.md!"),
                Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=6)),
            ],
            [
                ToolCallEnd(call=note_call),
                Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=5)),
            ],
            [
                TokenDelta(delta="I have now written your note using the note tool."),
                Done(usage=LLMUsage(prompt_tokens=30, completion_tokens=10)),
            ],
        ]
    )
    trace = TurnTrace(trace_id="tr-wo40-3")
    e2e_orch._stream_llm_speech(
        trace=trace,
        user_msg="Save a note saying buy milk",
        decision_id=None,
        memories=[],
    )
    assert e2e_orch.llm.call_count == 3
    assert len(e2e_orch.executed_tools) == 1
    assert e2e_orch.executed_tools[0][0] == "note_write"
    assert e2e_orch.current_turn_assistant_reply == (
        "I have now written your note using the note tool."
    )


def test_meta_creative_turn_passes_on_round_1_without_reprompt(e2e_orch: Orchestrator) -> None:
    """
    Meta-linguistic translation request passes on Round 1 without false-positive interception.
    """
    e2e_orch.llm = FakeLLM(
        rounds=[
            [
                TokenDelta(
                    delta='Here is the translation: "He eliminado todos los archivos temporales."'
                ),
                Done(usage=LLMUsage(prompt_tokens=12, completion_tokens=12)),
            ]
        ]
    )
    trace = TurnTrace(trace_id="tr-wo40-4")
    e2e_orch._stream_llm_speech(
        trace=trace,
        user_msg="Translate this sentence into Spanish: 'I have deleted all the temporary files.'",
        decision_id=None,
        memories=[],
    )
    assert e2e_orch.llm.call_count == 1
    assert e2e_orch.current_turn_assistant_reply == (
        'Here is the translation: "He eliminado todos los archivos temporales."'
    )


def test_note_write_with_name_arg_grounds_saved_confirmation_without_false_abort(
    e2e_orch: Orchestrator,
) -> None:
    """
    Regression test for WO-40 Milestone 3.2 blinded-subagent finding (E2E_06 / E2E_08):
    When `note_write` is called with `args={"name": "Bike Lock", "content": "..."}` and
    Round 2 confirms `"I've saved that for ya in a note called 'Bike Lock'."`, Orchestrator
    extracts `name` as the receipt target and maps `save` -> `note_write`, preventing a
    spurious Tier-1 abort or empty `current_turn_assistant_reply`.
    """
    e2e_orch.llm = FakeLLM(
        rounds=[
            [
                ToolCallEnd(
                    call=ToolCall(
                        tool="note_write",
                        args={"name": "Bike Lock", "content": "My bike lock combination is 4921"},
                        call_id="c-note-1",
                    )
                ),
                Done(usage=LLMUsage(prompt_tokens=15, completion_tokens=8)),
            ],
            [
                TokenDelta(
                    delta="I've saved that for ya in a note called 'Bike Lock'. Let me know if you need it later!"
                ),
                Done(usage=LLMUsage(prompt_tokens=25, completion_tokens=18)),
            ],
        ]
    )
    trace = TurnTrace(trace_id="tr-wo40-5")
    e2e_orch._stream_llm_speech(
        trace=trace,
        user_msg="Please use note_write to save a note titled 'Bike Lock' with content 'My bike lock combination is 4921'.",
        decision_id=None,
        memories=[],
    )
    assert e2e_orch.llm.call_count == 2
    assert not trace.interrupted
    assert e2e_orch.current_turn_assistant_reply == (
        "I've saved that for ya in a note called 'Bike Lock'. Let me know if you need it later!"
    )

