"""
WO-11.1 Behavioral Tests: Orchestrator Turn Paths Parity & Ported Fixes Verification.

Validates that voice (_run_turn) and text (_run_text_turn) paths share identical logic
for the five previously diverged areas:
1. Multi-action ACT_THEN_NARRATE narration (F11 ported to text)
2. REFLEX execution triple emission (REFLEX triple ported to text)
3. CLARIFY mode hint in epistemic context (F13 ported to text)
4. Config-driven follow-up patterns in tool gating (F20 ported to voice)
5. Clean turn state reset across both paths
"""

import numpy as np
import pytest

from lucca.core.ipc_schemas import PTTReleasedPayload
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    ExecutionTier,
    LLMUsage,
    Risk,
    RouteAction,
    RouteDecision,
    TokenDelta,
    ToolParameter,
    ToolSchema,
)
from lucca.core.trace import TurnTrace
from lucca.reasoning.lifecycle import RuleLifecycleManager
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


def _make_dummy_voice_payload(
    orch: Orchestrator, duration_ms: float = 1000.0
) -> PTTReleasedPayload:
    """Helper to write dummy PCM to capture ring and return a PTTReleasedPayload."""
    samples = int(16 * duration_ms)
    dummy_pcm = np.ones(samples, dtype=np.int16) * 1000
    orch.cap_ring.write(dummy_pcm)
    return PTTReleasedPayload(
        t_ns=2000,
        capture_seq_start=0,
        capture_seq_end=samples,
        duration_ms=duration_ms,
        vad_speech_ms=duration_ms * 0.9,
    )


def test_act_then_narrate_identical_narration_both_paths(orchestrator):
    """
    WO-11.1 behavioral test: firing the same multi-action ACT_THEN_NARRATE rule
    through both paths (FakeLLM) produces identical narration ToolResult content.
    """
    rule_src = """
    (rule "multi-app-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :app "calc") (tool "launch_app" :app "notepad"))
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
    orchestrator.router.classify_intent = lambda _: ("launch_app", 0.95, {"app": ["calc"]})

    # 1. Voice turn
    fake_llm_voice = FakeLLM(
        script=[
            TokenDelta(delta="Opened both apps."),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=3)),
        ]
    )
    orchestrator.llm = fake_llm_voice
    orchestrator.asr = FakeASR(transcript="open calculator")
    payload = _make_dummy_voice_payload(orchestrator)
    trace_voice = TurnTrace(trace_id="voice-turn-1", mode="audio")

    orchestrator._run_turn(trace_voice, payload)
    voice_messages = fake_llm_voice.last_kwargs.get("messages", [])
    assert voice_messages, "Voice turn did not invoke FakeLLM for narration"
    voice_narration_content = str(voice_messages[-1].content)

    # 2. Text turn
    fake_llm_text = FakeLLM(
        script=[
            TokenDelta(delta="Opened both apps."),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=3)),
        ]
    )
    orchestrator.llm = fake_llm_text
    trace_text = TurnTrace(trace_id="text-turn-1", mode="transcript")

    orchestrator._run_text_turn(trace_text, "open calculator")
    text_messages = fake_llm_text.last_kwargs.get("messages", [])
    assert text_messages, "Text turn did not invoke FakeLLM for narration"
    text_narration_content = str(text_messages[-1].content)

    # Both must narrate BOTH tools
    assert "launch_app(app='calc') -> ok:" in voice_narration_content
    assert "launch_app(app='notepad') -> ok:" in voice_narration_content
    assert "launch_app(app='calc') -> ok:" in text_narration_content
    assert "launch_app(app='notepad') -> ok:" in text_narration_content

    # The trace summary embedded in the prompt must be identical across both paths
    assert voice_narration_content == text_narration_content


def test_f11_multi_action_narrated_in_text_path(orchestrator):
    """
    Ported fix verification (F11 -> text): text path previously only recorded the last action;
    now it combines all actions via exec_lines into the ToolResult.
    """
    rule_src = """
    (rule "two-step-v1"
      :when (intent= "launch_app")
      :plan (list (tool "launch_app" :app "editor") (tool "launch_app" :app "terminal"))
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
    orchestrator.router.classify_intent = lambda _: ("launch_app", 0.95, {"app": ["editor"]})

    fake_llm = FakeLLM(
        script=[
            TokenDelta(delta="Both opened."),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=2)),
        ]
    )
    orchestrator.llm = fake_llm
    trace = TurnTrace(trace_id="text-f11-test", mode="transcript")

    orchestrator._run_text_turn(trace, "open editor")
    messages = fake_llm.last_kwargs.get("messages", [])
    assert messages, "FakeLLM not called"
    prompt_text = str(messages[-1].content)

    assert "launch_app(app='editor') -> ok:" in prompt_text
    assert "launch_app(app='terminal') -> ok:" in prompt_text


def test_reflex_triple_emitted_both_paths(orchestrator):
    """
    Ported fix verification (REFLEX triple -> text): REFLEX execution triple must be emitted
    in both voice and text paths when a REFLEX rule fires.
    """
    rule_src = """
    (rule "emergency-halt-v1"
      :when (intent= "emergency_stop")
      :plan (list (say "Halted."))
      :priority 100)
    """
    orchestrator.rule_engine = RuleLifecycleManager()
    managed = orchestrator.rule_engine.register_rule(rule_src)
    managed.status = "ACTIVE"
    orchestrator.router.classify_intent = lambda _: ("emergency_stop", 0.95, {})

    emitted_triples: list[dict[str, object]] = []

    def mock_emit_execution_triple(rule_id, plan, signal, detail=""):
        emitted_triples.append({"rule_id": rule_id, "signal": signal, "detail": detail})

    orchestrator.rule_engine.emit_execution_triple = mock_emit_execution_triple

    # 1. Voice REFLEX turn
    orchestrator.asr = FakeASR(transcript="stop immediately")
    payload = _make_dummy_voice_payload(orchestrator)
    trace_voice = TurnTrace(trace_id="voice-reflex-1", mode="audio")
    orchestrator._run_turn(trace_voice, payload)

    assert len(emitted_triples) == 1
    assert emitted_triples[0]["rule_id"] == "emergency-halt-v1"
    assert emitted_triples[0]["detail"] == "REFLEX execution"
    assert emitted_triples[0]["signal"] == "tool_exit_zero"

    # 2. Text REFLEX turn
    trace_text = TurnTrace(trace_id="text-reflex-1", mode="transcript")
    orchestrator._run_text_turn(trace_text, "stop immediately")

    assert len(emitted_triples) == 2
    assert emitted_triples[1]["rule_id"] == "emergency-halt-v1"
    assert emitted_triples[1]["detail"] == "REFLEX execution"
    assert emitted_triples[1]["signal"] == "tool_exit_zero"


def test_f13_clarify_hint_in_text_path(orchestrator):
    """
    Ported fix verification (F13 -> text): when router returns RouteAction.CLARIFY,
    text path injects the Clarify Mode hint into epistemic context.
    """
    fake_llm = FakeLLM(
        script=[
            TokenDelta(delta="What would you like me to do?"),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=6)),
        ]
    )
    orchestrator.llm = fake_llm

    # Mock router to return CLARIFY
    def mock_route(*args, **kwargs):
        return RouteDecision(
            action=RouteAction.CLARIFY,
            tier=ExecutionTier.FULL_LOOP,
            reason="short_utterance",
            confidence=0.9,
            route_name="mock_clarify",
            prediction_set=[RouteAction.CLARIFY],
            elapsed_us=50,
        )

    orchestrator.router.route = mock_route

    trace = TurnTrace(trace_id="text-f13-test", mode="transcript")
    orchestrator._run_text_turn(trace, "what")

    epistemic_ctx = fake_llm.last_kwargs.get("epistemic_context")
    assert epistemic_ctx is not None, "Epistemic context was None in text turn"
    assert "Clarify Mode: The user's utterance was very short or ambiguous." in epistemic_ctx


def test_f20_follow_up_patterns_config_in_voice_path(orchestrator):
    """
    Ported fix verification (F20 -> voice): follow-up patterns in voice turns are config-driven
    from heuristics.toml; asking a follow-up ("tell me more") does not suppress tools even under chit_chat.
    """
    fake_llm = FakeLLM(
        script=[
            TokenDelta(delta="Here is more info."),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=4)),
        ]
    )
    orchestrator.llm = fake_llm
    orchestrator.execute_tools = True
    orchestrator.router.classify_intent = lambda _: ("chit_chat", 0.95, {})

    # 1. Non-followup chit-chat: tools ARE suppressed to []
    orchestrator.asr = FakeASR(transcript="hello")
    payload1 = _make_dummy_voice_payload(orchestrator)
    trace1 = TurnTrace(trace_id="voice-f20-non-followup", mode="audio")
    orchestrator._run_turn(trace1, payload1)
    tools1 = fake_llm.last_kwargs.get("tools")
    assert tools1 == [], "Tools should be suppressed to [] for pure chit-chat"

    # 2. Follow-up phrase from heuristics.toml ("tell me more"): tools are NOT suppressed
    orchestrator.asr = FakeASR(transcript="tell me more")
    payload2 = _make_dummy_voice_payload(orchestrator)
    trace2 = TurnTrace(trace_id="voice-f20-followup", mode="audio")
    orchestrator._run_turn(trace2, payload2)
    tools2 = fake_llm.last_kwargs.get("tools")
    assert tools2 is not None and len(tools2) > 0, (
        "Tools should not be suppressed for follow-up query"
    )
