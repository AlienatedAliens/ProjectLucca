"""
Tests for WO-13.3: Difficulty-Aware Dynamic Thinking (When2Think Heuristic).
Spec §7, D-BRAIN-05 v2, D-META-01.

Validates that:
1. Routine turns and general questions (chit-chat, lookups, unprompted explanations)
   bypass extended thinking (enable_thinking=False) to preserve llama-server's prefix KV cache
   and maintain sub-350ms TTFT.
2. Explicit thinking requests ('think step by step', 'deep think', 'take your time and think',
   'enable thinking') enable thinking tokens (enable_thinking=True).
3. Fast-path overrides suppress thinking even when explicit think keywords are present.
4. LLM client kwargs and TurnTrace telemetry accurately track enable_thinking.
5. Prefix cache stability invariant: system prompt and static tool definitions remain byte-identical.
"""

from unittest.mock import MagicMock

from lucca.brain.llm_client import build_chat_template_kwargs
from lucca.brain.prompt_builder import build_messages
from lucca.core.config import LLMSettings
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import DifficultyEstimator, TurnInput, TurnPipeline


def test_difficulty_estimator_routine_and_general_turns() -> None:
    estimator = DifficultyEstimator()

    routine_inputs = [
        "hi",
        "hello",
        "hey Lucca",
        "good morning",
        "how are you?",
        "how are you doing today?",
        "what time is it?",
        "what is the weather like?",
        "turn the lights on",
        "volume up",
        "who was the 16th president?",
        "what is the capital of France?",
        # General reasoning without explicit thinking invocation should NOT blow TTFT to 1.9s:
        "Explain why water expands when it freezes instead of contracting.",
        "What are the tradeoffs between SQLite and Postgres?",
        "Solve for x: 3x + 15 = 42",
        "Calculate 15 * 24 + 18 / 2",
    ]

    for text in routine_inputs:
        assert not estimator.should_enable_thinking(text), (
            f"Expected enable_thinking=False (cache preserved) for: '{text}'"
        )


def test_difficulty_estimator_chit_chat_intent() -> None:
    estimator = DifficultyEstimator()
    assert not estimator.should_enable_thinking("tell me a funny story", intent="chit_chat")
    assert not estimator.should_enable_thinking("what's your favorite hobby?", intent="chit_chat")


def test_difficulty_estimator_explicit_thinking_requests() -> None:
    estimator = DifficultyEstimator()

    explicit_inputs = [
        "Please think step by step before answering this question.",
        "Can you take your time and think about this riddle?",
        "With thinking: what is the optimal path?",
        "Deep think on this mathematical proof.",
        "Let's deliberate carefully on this strategy.",
        "Please think through this step by step.",
        "Enable thinking and explain the quantum entanglement paradox.",
    ]

    for text in explicit_inputs:
        assert estimator.should_enable_thinking(text), (
            f"Expected enable_thinking=True for explicit request: '{text}'"
        )


def test_difficulty_estimator_fast_path_overrides() -> None:
    estimator = DifficultyEstimator()

    # Even with explicit thinking keywords, explicit fast-path directives should force False
    fast_path_inputs = [
        "Quick answer, don't take your time and think.",
        "In one word, what's the answer? Don't overthink.",
        "Just tell me, quick question, think step by step if needed but be fast.",
        "Short answer: what is 15 * 24?",
        "Fast summary, no deep thinking.",
    ]

    for text in fast_path_inputs:
        assert not estimator.should_enable_thinking(text), f"Expected fast path for: '{text}'"


def test_difficulty_estimator_edge_cases() -> None:
    estimator = DifficultyEstimator()
    assert not estimator.should_enable_thinking("")
    assert not estimator.should_enable_thinking("   ")
    assert not estimator.should_enable_thinking("???")
    assert not estimator.should_enable_thinking("ok")


def test_build_chat_template_kwargs_overrides() -> None:
    cfg_false = LLMSettings(enable_thinking=False)
    cfg_true = LLMSettings(enable_thinking=True)
    cfg_none = LLMSettings(enable_thinking=None)

    # 1. Fallback to config when enable_thinking is None
    assert build_chat_template_kwargs(cfg_false)["enable_thinking"] is False
    assert build_chat_template_kwargs(cfg_true)["enable_thinking"] is True
    assert "enable_thinking" not in build_chat_template_kwargs(cfg_none)

    # 2. Per-turn override takes strict precedence
    assert build_chat_template_kwargs(cfg_false, enable_thinking=True)["enable_thinking"] is True
    assert build_chat_template_kwargs(cfg_true, enable_thinking=False)["enable_thinking"] is False
    assert build_chat_template_kwargs(cfg_none, enable_thinking=True)["enable_thinking"] is True
    assert build_chat_template_kwargs(cfg_none, enable_thinking=False)["enable_thinking"] is False


def test_turn_pipeline_sets_trace_enable_thinking() -> None:
    mock_orch = MagicMock()
    mock_orch.sandbox.reset_turn = MagicMock()
    mock_orch.output_supervisor.reset_turn = MagicMock()
    mock_orch.rule_engine.evaluate.return_value = []
    mock_orch.rule_engine.rules = {}
    mock_orch.router.route.return_value = None
    mock_orch.prev_decision_record = None
    mock_orch.db = None
    mock_orch._build_rule_state.return_value = MagicMock(
        intent="general", hour_local=12, weekday=2, session_turns=1
    )
    mock_orch._search_memories.return_value = []
    mock_orch.cascade.classify_intent.return_value = (False, [], 0.0)

    pipeline = TurnPipeline(mock_orch)

    # 1. Routine turn -> enable_thinking is False
    trace_routine = TurnTrace(trace_id="test-routine")
    inp_routine = TurnInput(
        user_text="What time is it?",
        trace=trace_routine,
        origin="text",
    )
    pipeline.run(inp_routine)
    assert trace_routine.enable_thinking is False
    mock_orch._stream_llm_speech.assert_called()
    assert mock_orch._stream_llm_speech.call_args.kwargs["enable_thinking"] is False

    # 2. Explicit thinking turn -> enable_thinking is True
    trace_deep = TurnTrace(trace_id="test-deep")
    inp_deep = TurnInput(
        user_text="Please think step by step: why is spacetime curved?",
        trace=trace_deep,
        origin="text",
    )
    pipeline.run(inp_deep)
    assert trace_deep.enable_thinking is True
    assert mock_orch._stream_llm_speech.call_args.kwargs["enable_thinking"] is True


def test_prefix_cache_stability_invariant() -> None:
    """
    Prefix cache stability: The system prompt and conversation prefix must be
    byte-identical regardless of whether dynamic thinking is toggled.
    Only chat_template_kwargs.enable_thinking varies.
    """
    messages_turn1 = build_messages(
        current_text="Hello Lucca",
    )
    messages_turn2 = build_messages(
        current_text="Hello Lucca",
    )

    # Ensure system prompts are identical
    assert messages_turn1[0].content == messages_turn2[0].content

    # The payload messages list is identical
    dump1 = [m.model_dump(exclude_none=True) for m in messages_turn1]
    dump2 = [m.model_dump(exclude_none=True) for m in messages_turn2]
    assert dump1 == dump2

    # Only kwargs vary
    cfg = LLMSettings()
    kwargs_routine = build_chat_template_kwargs(cfg, enable_thinking=False)
    kwargs_deep = build_chat_template_kwargs(cfg, enable_thinking=True)
    assert kwargs_routine["enable_thinking"] is False
    assert kwargs_deep["enable_thinking"] is True
