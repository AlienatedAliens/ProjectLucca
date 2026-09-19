"""
Tests for Proposal C / D-ARCH-06: Fast-Path Context Synchronization into LLM History.
"""

from unittest.mock import MagicMock

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Plan, RouteAction, RouteDecision, RuleOutcome, Say, ToolCall
from lucca.core.trace import TurnTrace


def test_fast_path_sync_records_tool_executions_in_history() -> None:
    # Construct minimal orchestrator mocks
    orch = Orchestrator.__new__(Orchestrator)
    orch.history = []
    orch.execute_tools = True
    orch.executed_tools = []
    orch.memory_store = None
    orch.current_turn_tool_calls = []
    orch.current_turn_tool_spoken = []
    orch.current_turn_tool_ok = True
    orch.play_ring = MagicMock()
    orch.sandbox = MagicMock()
    orch.sandbox.check_confirmation_needed.return_value = False
    orch.sandbox.execute_tool.return_value = MagicMock(ok=True, exit_code=0)
    orch.router = MagicMock()
    orch.router.last_decision_record = None
    orch.rule_engine = MagicMock()
    orch._publish_bus = MagicMock()
    orch._publish_caption = MagicMock()
    orch._speak_text = MagicMock()
    orch._finalize_turn = MagicMock()

    trace = TurnTrace(trace_id="test-trace")
    active_outcomes = [
        RuleOutcome(
            rule_id="calc-rule",
            fired=True,
            errored=False,
            gas_used=10,
            elapsed_us=50,
            plan=Plan(
                actions=[
                    ToolCall(tool="launch_app", args={"app_name": "calc"}, call_id="c1"),
                    Say(text="Opening Calculator."),
                ]
            ),
        )
    ]
    orch.rule_engine.rules = {}
    orch.rule_engine.evaluate.return_value = active_outcomes
    orch.router.classify_intent.return_value = ("launch_app", 0.99, {})
    orch.router.route.return_value = RouteDecision(
        action=RouteAction.RULE,
        target="RULE",
        intent="launch_app",
        confidence=0.99,
        rule_id="calc-rule",
        prediction_set=["RULE"],
        elapsed_us=100,
    )
    orch.prev_decision_record = None
    orch.db = None
    orch.tts = MagicMock()
    orch._build_rule_state = MagicMock()

    orch._run_text_turn(trace, "open calculator")

    assert len(orch.history) == 2
    assert orch.history[0] == {"role": "user", "content": "open calculator"}
    assert orch.history[1]["role"] == "assistant"
    assert "Opening Calculator." in orch.history[1]["content"]
    assert "[Executed launch_app(app_name='calc') -> ok]" in orch.history[1]["content"]
