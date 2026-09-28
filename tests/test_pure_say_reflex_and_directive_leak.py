"""
Project Lucca — Pure Say Reflex & Directive Leak Prevention Tests
Verifies that:
1. Pure say rules (like time-greeting-v1) dispatch to ExecutionTier.REFLEX and speak directly without LLM invocation.
2. LLMClient merges any trailing assistant narration directives into the user prompt so llama-server never treats them as an assistant prefill.
"""

from unittest.mock import MagicMock, patch

from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import build_narration_messages
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import ExecutionTier, Plan, RouteAction, RuleOutcome, Say, ToolResult
from lucca.core.trace import TurnTrace


def test_pure_say_rule_dispatches_as_reflex_without_llm():
    """Verify that a rule with only Say actions executes as REFLEX and does NOT invoke the LLM."""
    orch = Orchestrator(execute_tools=False)
    orch.llm.stream_turn = MagicMock()
    spoken_chunks: list[str] = []
    orch._speak_text = MagicMock(side_effect=lambda trace, text: spoken_chunks.append(text))

    trace = TurnTrace(
        trace_id="test-greet-001",
        session_id="test-sess",
        origin="text",
        mode="transcript",
    )

    # Simulate a winning pure-say rule outcome
    greet_plan = Plan(actions=[Say(text="Good morning! How can I help you today?")])
    outcome = RuleOutcome(
        rule_id="time-greeting-v1",
        fired=True,
        plan=greet_plan,
        gas_used=10,
        elapsed_us=50,
    )

    # Route decision returning RULE but tier default
    route_dec = MagicMock()
    route_dec.action = RouteAction.RULE
    route_dec.tier = ExecutionTier.ACT_THEN_NARRATE

    from lucca.core.turn_pipeline import TurnInput

    inp = TurnInput(user_text="Hello, Luca.", trace=trace, origin="text", mode="transcript")

    # Run dispatch in pipeline
    pipeline = orch.turn_pipeline
    with patch.object(orch.rule_engine, "evaluate", return_value=[outcome]), patch.object(
        orch.router, "route", return_value=route_dec
    ):
        pipeline.run(inp)

    # 1. LLM must NOT have been called
    orch.llm.stream_turn.assert_not_called()

    # 2. Greeting must have been spoken directly
    assert any("Good morning! How can I help you today?" in c for c in spoken_chunks)

    # 3. History must record the clean spoken greeting, not directives
    assert len(orch.history) >= 2
    last_assistant = orch.history[-1]
    assert last_assistant["role"] == "assistant"
    assert "Good morning! How can I help you today?" in str(last_assistant["content"])
    assert "Directive:" not in str(last_assistant["content"])
    assert "[System Executed" not in str(last_assistant["content"])


def test_llm_client_merges_assistant_directives_into_user_message():
    """Verify LLMClient merges trailing assistant directives so llama-server receives no assistant prefill."""
    mock_res = ToolResult(
        call_id="call-456",
        ok=True,
        content="Meeting scheduled for 3 PM",
        elapsed_ms=5.0,
    )
    msgs = build_narration_messages(
        tool_name="read_file",
        tool_args={"path": "calendar.txt"},
        tool_result=mock_res,
        user_text="What is on my calendar?",
    )

    # In msgs, msgs[-1] has role="assistant" with Directive
    assert msgs[-1].role == "assistant"
    assert "Directive:" in str(msgs[-1].content)

    captured_payload: dict[str, object] = {}

    def fake_stream(*args: object, **kwargs: object) -> object:
        captured_payload.update(kwargs.get("json", {}))
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_ctx
        mock_ctx.__exit__.return_value = None
        mock_ctx.status_code = 200
        mock_ctx.iter_lines.return_value = iter(["data: [DONE]"])
        return mock_ctx

    import httpx

    with patch.object(httpx.Client, "stream", fake_stream):
        client = LLMClient(base_url="http://localhost:9999")
        list(client.stream_turn(messages=msgs))

    payload_messages = captured_payload.get("messages", [])
    assert len(payload_messages) >= 2

    # The payload MUST NOT end with role="assistant" (which would trigger assistant prefill leak)
    assert payload_messages[-1].get("role") != "assistant"

    # The last message must be role="user" and contain both user text and the directive
    last_msg = payload_messages[-1]
    assert last_msg.get("role") == "user"
    content_str = str(last_msg.get("content", ""))
    assert "What is on my calendar?" in content_str
    assert "Meeting scheduled for 3 PM" in content_str
    assert "Directive:" in content_str
