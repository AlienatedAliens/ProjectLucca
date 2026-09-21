"""
Tests for Batch 2 Procedural Capabilities & System 1 / System 2 Execution
Proposals A, B, I, J (D-REAS-04, D-ARCH-05, D-BRAIN-03, D-BRAIN-04)
"""

import pytest

from lucca.brain.prompt_builder import (
    build_narration_messages,
    get_all_tool_definitions,
)
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    ExecutionTier,
    LLMUsage,
    Risk,
    RouteAction,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
    ToolParameter,
    ToolResult,
    ToolSchema,
)
from lucca.reasoning.lifecycle import ManagedRule, RuleLifecycleManager
from lucca.reasoning.scheme.parser import parse_rule
from lucca.router.heuristic import EMERGENCY_REFLEX_PATTERN, HeuristicRouter
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


@pytest.fixture
def orchestrator():
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=False)
    yield orch
    orch.stop()
    orch.cap_ring.close()
    orch.cap_ring.unlink()
    orch.play_ring.close()
    orch.play_ring.unlink()


def test_emergency_reflex_routing():
    """Verify emergency commands route to REFLEX tier while actions route to ACT_THEN_NARRATE."""
    router = HeuristicRouter()

    # Emergency reflex utterances
    for emergency in ["shut down", "pause", "mute", "stop right now", "halt"]:
        assert EMERGENCY_REFLEX_PATTERN.search(emergency) is not None
        decision = router.route(
            transcript=emergency,
            any_active_rule_fired=True,
            any_quarantine_rule_fired=False,
            vad_speech_ms=500,
        )
        assert decision.action == RouteAction.RULE
        assert decision.tier == ExecutionTier.REFLEX

    # Standard action utterances (non-emergency)
    decision = router.route(
        transcript="open calculator",
        any_active_rule_fired=True,
        any_quarantine_rule_fired=False,
        vad_speech_ms=500,
    )
    assert decision.action == RouteAction.RULE
    assert decision.tier == ExecutionTier.ACT_THEN_NARRATE

    decision = router.route("stop immediately")
    assert decision.action == RouteAction.RULE
    assert decision.tier == ExecutionTier.REFLEX

    # Normal utterance routes to FULL_LOOP or ACT_THEN_NARRATE
    decision = router.route("tell me a joke")
    assert decision.action == RouteAction.LLM
    assert decision.tier == ExecutionTier.FULL_LOOP


def test_skill_as_tool_generation():
    """T1.5: Flat skill catalog retired; get_all_tool_definitions contains registry tools only."""
    rule_src = """
    (rule "calc-launcher-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :app "calc"))
      :priority 5)
    """
    rule_def = parse_rule(rule_src)
    managed = ManagedRule(rule_id="calc-launcher-v1", status="ACTIVE", definition=rule_def)

    # Test combined tool definitions: no flat skill_* entries
    all_tools = get_all_tool_definitions([managed])
    tool_names = [t.function.name for t in all_tools]
    assert "read_file" in tool_names
    assert "invoke_skill" in tool_names
    assert not any(name.startswith("skill_") for name in tool_names)


def test_act_then_narrate_execution(orchestrator):
    """Proposal B / D-ARCH-05: Standard action rule executes tool and prompts NeMo for narration."""
    rule_src = """
    (rule "open-calc-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :app "calculator"))
      :priority 10)
    """
    tools = {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
            target="self",
        )
    }
    orchestrator.rule_engine = RuleLifecycleManager(registered_tools=tools)
    managed = orchestrator.rule_engine.register_rule(rule_src)
    managed.status = "ACTIVE"

    # Setup FakeLLM for narration stream
    narration_script = [
        TokenDelta(delta="I've got the calculator up and running for you!"),
        Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=10)),
    ]
    orchestrator.llm = FakeLLM(script=narration_script)

    # Trigger text turn
    orchestrator._on_user_text(ts_ns=1000, user_text="open calculator")
    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=5.0)

    # Verify tool was executed in orchestrator
    assert len(orchestrator.executed_tools) >= 1
    assert orchestrator.executed_tools[-1][0] == "launch_app"

    # Verify LLM was invoked for narration
    assert orchestrator.llm.call_count == 1

    # Verify history recorded user message, tool execution trace, and LLM narration
    assert len(orchestrator.history) >= 2
    user_entry = orchestrator.history[-2]
    assistant_entry = orchestrator.history[-1]
    assert user_entry["role"] == "user"
    assert user_entry["content"] == "open calculator"
    assert assistant_entry["role"] == "assistant"
    assert "calculator" in assistant_entry["content"].lower()


def test_multi_step_tool_loop_with_verbal_cues(orchestrator):
    """Proposal I / D-BRAIN-03: Multi-step tool loop emits verbal thinking cues and re-prompts NeMo."""
    spoken_cues: list[str] = []

    # Mock _speak_text to capture verbal cues
    orig_speak = orchestrator._speak_text

    def mock_speak(trace, text):
        spoken_cues.append(text)
        orig_speak(trace, text)

    orchestrator._speak_text = mock_speak

    # Round 1: NeMo emits ToolCallEnd for read_file
    round_1 = [
        ToolCallEnd(
            call=ToolCall(tool="read_file", args={"path": "notes.txt"}, call_id="c-read-1")
        ),
    ]
    # Round 2: NeMo receives tool result and provides final grounded response
    round_2 = [
        TokenDelta(delta="According to notes.txt, your meeting is at 3 PM."),
        Done(usage=LLMUsage(prompt_tokens=25, completion_tokens=11)),
    ]

    orchestrator.llm = FakeLLM(rounds=[round_1, round_2])
    orchestrator.cascade.classify_intent = lambda _text: (False, [], "")

    orchestrator._on_user_text(ts_ns=2000, user_text="what time is my meeting in notes.txt?")
    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=5.0)

    # Verify tool was executed
    assert len(orchestrator.executed_tools) >= 1
    assert orchestrator.executed_tools[0][0] == "read_file"

    # Verify verbal thinking cue was emitted before tool execution
    assert any("file" in cue.lower() or "checking" in cue.lower() for cue in spoken_cues)

    # Verify LLM had 2 rounds
    assert orchestrator.llm.call_count == 2

    # Verify history contains final assistant response
    assert len(orchestrator.history) >= 2
    assistant_entry = orchestrator.history[-1]
    assert "3 PM" in assistant_entry["content"]


def test_skill_tool_invocation_from_llm(orchestrator):
    """Proposal A: LLM calling skill_<rule_id> triggers rule evaluation and sandbox execution."""
    rule_src = """
    (rule "calc-app-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :app "calc"))
      :priority 5)
    """
    tools = {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
            target="self",
        )
    }
    orchestrator.rule_engine = RuleLifecycleManager(registered_tools=tools)
    managed = orchestrator.rule_engine.register_rule(rule_src)
    managed.status = "ACTIVE"
    managed.expose_as_tool = True

    # LLM calls invoke_skill
    round_1 = [
        ToolCallEnd(
            call=ToolCall(
                tool="invoke_skill",
                args={"skill_id": "calc-app-v1", "args": {"query": "open calculator"}},
                call_id="c-skill-1",
            )
        ),
    ]
    round_2 = [
        TokenDelta(delta="The calculator skill has been executed successfully."),
        Done(usage=LLMUsage(prompt_tokens=30, completion_tokens=8)),
    ]

    orchestrator.llm = FakeLLM(rounds=[round_1, round_2])

    orchestrator._on_user_text(ts_ns=3000, user_text="please start the calculator tool")
    if orchestrator.active_turn_thread:
        orchestrator.active_turn_thread.join(timeout=5.0)

    # Verify skill was executed through _handle_tool_call and executed underlying launch_app
    tool_names = [call[0] for call in orchestrator.executed_tools]
    assert "invoke_skill" in tool_names
    assert "launch_app" in tool_names
    assert orchestrator.llm.call_count == 2


def test_narration_grounding_provenance():
    """Proposal J / D-BRAIN-04: Narration prompt enforces strict grounding in tool trace blocks."""
    mock_res = ToolResult(
        call_id="call-xyz",
        ok=True,
        content="File size: 1024 bytes. Modified: 2026-09-19.",
        elapsed_ms=12.5,
    )

    messages = build_narration_messages(
        tool_name="read_file",
        tool_args={"path": "report.pdf"},
        tool_result=mock_res,
        user_text="What is the size of report.pdf?",
    )

    assert len(messages) == 3
    system_msg = messages[0].content
    user_msg = messages[1].content
    narration_msg = messages[2].content

    # Verify anti-hallucination constraint in system prompt
    assert "ground your statements strictly in the verified facts" in system_msg
    assert "Never fabricate facts, statuses, numerical metrics" in system_msg

    # Verify user message preserved
    assert user_msg == "What is the size of report.pdf?"

    # Verify tool trace block contents and grounding directive in narration message
    assert "[System Executed Tool Trace: read_file" in narration_msg
    assert "report.pdf" in narration_msg
    assert "File size: 1024 bytes" in narration_msg
    assert "Grounding your response strictly in the tool execution output above" in narration_msg
    assert "without fabricating metrics or unverified facts" in narration_msg
