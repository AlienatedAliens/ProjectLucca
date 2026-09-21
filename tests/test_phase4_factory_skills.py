"""
Phase 4 (L1b-pilot): Acceptance Tests for 7 Factory Pilot Skills
Spec 1.1.2 §3, §13 Ladder (L1b-pilot), Handover #4 §4.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.capabilities import dispatch_invoke_skill, get_default_native_tools
from lucca.core.exceptions import SchemeYieldSignal
from lucca.core.schemas import RuleState, ToolCall, ToolResult
from lucca.reasoning.lifecycle import RuleLifecycleManager


@pytest.fixture
def skills_engine():
    """RuleLifecycleManager initialized with repo config/skills/."""
    skills_dir = Path("config/skills")
    tools = get_default_native_tools()
    engine = RuleLifecycleManager(skills_dir=skills_dir, registered_tools=tools)
    return engine


def test_factory_skills_registered_and_active(skills_engine: RuleLifecycleManager) -> None:
    """Assert the 7 L1b-pilot factory skills are loaded and ACTIVE (barge-in stays RETIRED)."""
    expected_skills = {
        "calc-eval-v1": (True, ["cognitive_core", "self"]),
        "unit-convert-v1": (True, ["cognitive_core"]),
        "quick-fact-v1": (True, ["information"]),
        "define-term-v1": (True, ["information"]),
        "time-greeting-v1": (False, ["companion"]),
        "plan-decompose-v1": (False, ["cognitive_core"]),
        "correction-ack-v1": (False, ["cognitive_core"]),
    }

    assert len(expected_skills) == 7
    # D3 (Phase 4 gate) still holds: RuleState.interrupted is never populated by the
    # orchestrator, so barge-in-sorry-v1 must not be ACTIVE with an unreachable trigger.
    barge = skills_engine.rules.get("barge-in-sorry-v1")
    assert barge is None or barge.status != "ACTIVE"

    for skill_id, (expected_exposed, expected_cats) in expected_skills.items():
        assert skill_id in skills_engine.rules, f"Missing factory skill {skill_id}"
        managed = skills_engine.rules[skill_id]
        assert managed.status == "ACTIVE", f"{skill_id} is not ACTIVE"
        assert managed.expose_as_tool is expected_exposed, (
            f"{skill_id} expose_as_tool mismatch: expected {expected_exposed}, got {managed.expose_as_tool}"
        )
        for cat in expected_cats:
            assert cat in managed.categories, f"{skill_id} missing category {cat}"


def test_each_factory_skill_fires_expected_plan(skills_engine: RuleLifecycleManager) -> None:
    """
    Test that each factory skill fires on its trigger turn according to the entity-absent invariant:
    - Missing entity -> yields to core (no confabulation)
    - Present entity -> dispatches tool action
    - Over-fire guards (D4) and reachable predicates (D2) verified
    """
    # 1. calc-eval-v1
    # 1a. Entity absent -> yields to core
    state_calc_no_entity = RuleState(
        transcript="please calculate 10 + 5",
        transcript_lower="please calculate 10 + 5",
        intent="chit_chat",
        entities={},
    )
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(state_calc_no_entity, mode="active")
    assert exc_info.value.reason == "calc: no expression"
    assert exc_info.value.context.get("need") == "expr"

    # 1b. Entity present (e.g. via invoke_skill args merge) -> runs tool
    state_calc_with_entity = RuleState(
        transcript="calculate",
        transcript_lower="calculate",
        intent="chit_chat",
        entities={"expr": ["10 + 5"]},
    )
    outcomes = skills_engine.evaluate(state_calc_with_entity, mode="active")
    calc_out = next((o for o in outcomes if o.rule_id == "calc-eval-v1"), None)
    assert calc_out is not None and calc_out.fired is True
    assert calc_out.plan is not None
    assert len(calc_out.plan.actions) == 1
    action = calc_out.plan.actions[0]
    assert isinstance(action, ToolCall)
    assert action.tool == "run_python"
    assert action.args.get("code") == "10 + 5"

    # 2. unit-convert-v1
    # 2a. Entity absent -> yields to core
    state_conv_no_entity = RuleState(
        transcript="convert 10 km to miles",
        transcript_lower="convert 10 km to miles",
        intent="chit_chat",
        entities={},
    )
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(state_conv_no_entity, mode="active")
    assert exc_info.value.reason == "convert: no expression"
    assert exc_info.value.context.get("need") == "expr"

    # 2b. Entity present -> runs tool
    state_conv_with_entity = RuleState(
        transcript="convert",
        transcript_lower="convert",
        intent="chit_chat",
        entities={"expr": ["10 * 0.621371"]},
    )
    outcomes = skills_engine.evaluate(state_conv_with_entity, mode="active")
    conv_out = next((o for o in outcomes if o.rule_id == "unit-convert-v1"), None)
    assert conv_out is not None and conv_out.fired is True
    assert conv_out.plan is not None
    action = conv_out.plan.actions[0]
    assert isinstance(action, ToolCall)
    assert action.tool == "run_python"
    assert action.args.get("code") == "10 * 0.621371"

    # 3. quick-fact-v1 (reachable predicate "fact about" + D1 entity branch)
    # 3a. Entity absent -> yields to core
    state_fact_no_entity = RuleState(
        transcript="tell me a quick fact about penguins",
        transcript_lower="tell me a quick fact about penguins",
        intent="chit_chat",
        entities={},
    )
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(state_fact_no_entity, mode="active")
    assert exc_info.value.reason == "fact: no topic"
    assert exc_info.value.context.get("need") == "topic"

    # 3b. Entity present -> runs tool
    state_fact_with_entity = RuleState(
        transcript="quick fact about",
        transcript_lower="quick fact about",
        intent="chit_chat",
        entities={"topic": ["penguins"]},
    )
    outcomes = skills_engine.evaluate(state_fact_with_entity, mode="active")
    fact_out = next((o for o in outcomes if o.rule_id == "quick-fact-v1"), None)
    assert fact_out is not None and fact_out.fired is True
    assert fact_out.plan is not None
    action = fact_out.plan.actions[0]
    assert isinstance(action, ToolCall)
    assert action.tool == "search_web"
    assert action.args.get("query") == "penguins"

    # 4. define-term-v1
    # 4a. Entity absent -> yields to core
    state_def_no_entity = RuleState(
        transcript="what is machine learning",
        transcript_lower="what is machine learning",
        intent="chit_chat",
        entities={},
    )
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(state_def_no_entity, mode="active")
    assert exc_info.value.reason == "define: no term"
    assert exc_info.value.context.get("need") == "term"

    # 4b. Entity present -> runs tool
    state_def_with_entity = RuleState(
        transcript="what is",
        transcript_lower="what is",
        intent="chit_chat",
        entities={"term": ["machine learning"]},
    )
    outcomes = skills_engine.evaluate(state_def_with_entity, mode="active")
    def_out = next((o for o in outcomes if o.rule_id == "define-term-v1"), None)
    assert def_out is not None and def_out.fired is True
    assert def_out.plan is not None
    action = def_out.plan.actions[0]
    assert isinstance(action, ToolCall)
    assert action.tool == "search_web"
    assert action.args.get("query") == "machine learning"

    # 5. time-greeting-v1 (D4 over-fire fix: session_turns < 1 and hour 5..11)
    # 5a. Morning first turn -> fires
    state_greet_first = RuleState(
        transcript="hello there",
        transcript_lower="hello there",
        intent="chit_chat",
        hour_local=8,
        session_turns=0,
    )
    outcomes = skills_engine.evaluate(state_greet_first, mode="active")
    greet_out = next((o for o in outcomes if o.rule_id == "time-greeting-v1"), None)
    assert greet_out is not None and greet_out.fired is True
    assert greet_out.plan is not None
    assert greet_out.plan.actions[0].text == "Good morning! How can I help you today?"

    # 5b. Morning subsequent turn -> does NOT fire
    state_greet_subsequent = RuleState(
        transcript="hello again",
        transcript_lower="hello again",
        intent="chit_chat",
        hour_local=8,
        session_turns=2,
    )
    outcomes = skills_engine.evaluate(state_greet_subsequent, mode="active")
    greet_sub_out = next((o for o in outcomes if o.rule_id == "time-greeting-v1"), None)
    assert greet_sub_out is None or greet_sub_out.fired is False

    # 5c. Evening first turn -> does NOT fire
    state_greet_evening = RuleState(
        transcript="hello",
        transcript_lower="hello",
        intent="chit_chat",
        hour_local=20,
        session_turns=0,
    )
    outcomes = skills_engine.evaluate(state_greet_evening, mode="active")
    greet_eve_out = next((o for o in outcomes if o.rule_id == "time-greeting-v1"), None)
    assert greet_eve_out is None or greet_eve_out.fired is False

    # 6. plan-decompose-v1 (yield-to-core)
    state_plan = RuleState(
        transcript="please explain step by step how to build a house",
        transcript_lower="please explain step by step how to build a house",
        intent="chit_chat",
    )
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(state_plan, mode="active")
    assert exc_info.value.reason == "multi-step task"
    assert exc_info.value.context.get("mode") == "plan"

    # 7. correction-ack-v1 (yield-to-core)
    state_corr = RuleState(
        transcript="actually that is incorrect",
        transcript_lower="actually that is incorrect",
        intent="chit_chat",
    )
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(state_corr, mode="active")
    assert exc_info.value.reason == "operator correction"
    assert exc_info.value.context.get("salience") == "high"

    # 8. interrupted? primitive evaluates cleanly, but no ACTIVE skill fires on it alone
    #    (barge-in-sorry-v1 is RETIRED until the orchestrator populates RuleState.interrupted).
    state_barge = RuleState(
        transcript="wait hold on",
        transcript_lower="wait hold on",
        intent="chit_chat",
        interrupted=True,
    )
    outcomes = skills_engine.evaluate(state_barge, mode="active")
    assert all(o.rule_id != "barge-in-sorry-v1" for o in outcomes)
    assert not any(o.errored for o in outcomes)


def test_invoke_skill_dispatch_and_refusal(skills_engine: RuleLifecycleManager) -> None:
    """
    Assert invoke_skill dispatches exposed skills #1-4 by skill_id when their category is in the manifest,
    and unexposed skills correctly refuse with skill_not_exposed.
    """
    # 1. calc-eval-v1 (exposed, in manifest)
    ok, msg, payload = dispatch_invoke_skill(
        skill_id="calc-eval-v1",
        args={"expr": "5 * 5"},
        rule_engine=skills_engine,
        manifest_skill_ids={"calc-eval-v1", "unit-convert-v1"},
    )
    assert ok is True
    assert "dispatched" in msg
    assert payload is not None and payload["skill_id"] == "calc-eval-v1"

    # 2. quick-fact-v1 (exposed, in manifest)
    ok, msg, payload = dispatch_invoke_skill(
        skill_id="quick-fact-v1",
        args={"topic": "physics"},
        rule_engine=skills_engine,
        manifest_skill_ids={"quick-fact-v1", "define-term-v1"},
    )
    assert ok is True
    assert "dispatched" in msg

    # Refusals for unexposed skills
    for unexposed_id in [
        "time-greeting-v1",
        "plan-decompose-v1",
        "correction-ack-v1",
    ]:
        ok, reason, _ = dispatch_invoke_skill(
            skill_id=unexposed_id,
            args={},
            rule_engine=skills_engine,
            manifest_skill_ids={unexposed_id},
        )
        assert ok is False
        assert reason == "skill_not_exposed", (
            f"Expected {unexposed_id} to refuse with 'skill_not_exposed', got '{reason}'"
        )

    # Refusal for retired barge-in-sorry-v1
    ok, reason, _ = dispatch_invoke_skill(
        skill_id="barge-in-sorry-v1",
        args={},
        rule_engine=skills_engine,
        manifest_skill_ids=set(),
    )
    assert ok is False
    assert reason in {"skill_not_exposed", "unknown_skill"}


def test_shadow_quarantine_mechanics_survive_launch_app_removal(
    skills_engine: RuleLifecycleManager,
) -> None:
    """
    Replaces the retired-rule test per C5:
    Registers a copy of calc-eval-v1 as calc-eval-shadow-v1 in QUARANTINE mode,
    runs one turn containing 'calculate', proves cluster count increments to 1/5 and 0 failures,
    then retires calc-eval-shadow-v1.
    """
    shadow_rule_src = """
    (rule "calc-eval-shadow-v1"
      :when (transcript-has? "calculate")
      :plan (if (= (entity-str "expr") "")
                (list (yield-to-core "calc: no expression" :need "expr"))
                (list (tool "run_python" :code (entity-str "expr"))))
      :priority 5)
    """
    managed = skills_engine.register_rule(shadow_rule_src)
    assert managed.status == "QUARANTINE"

    # Evaluate turn containing "calculate" with entity in shadow mode
    state = RuleState(
        transcript="can you calculate 100 / 4",
        transcript_lower="can you calculate 100 / 4",
        intent="chit_chat",
        entities={"expr": ["100 / 4"]},
    )
    shadow_outcomes = skills_engine.evaluate(state, mode="shadow")
    shadow_out = next((o for o in shadow_outcomes if o.rule_id == "calc-eval-shadow-v1"), None)
    assert shadow_out is not None
    assert shadow_out.fired is True
    assert shadow_out.errored is False

    # Check cluster count incremented
    rule_entry = skills_engine.rules["calc-eval-shadow-v1"]
    assert len(rule_entry.success_clusters) >= 1
    assert rule_entry.failure_count == 0

    # Retire rule afterwards so it does not count against 30-cap
    skills_engine.user_retire("calc-eval-shadow-v1")
    assert rule_entry.status == "RETIRED"


def test_run_python_c6_sandbox_paths() -> None:
    """
    Asserts C6 dual-path contract for run_python:
    1. Realistic mock Sandbox RPC at ToolResult boundary (ok=True, stdout numeric output).
    2. Non-Docker container isolation disabled fallback (ok=False, structured policy_violation).
    """
    from lucca.sandbox.service import SandboxService

    # 1. Mocked successful execution path
    mock_rpc_success = MagicMock()
    mock_rpc_success.use_direct_fallback = False
    mock_rpc_success.is_docker_available.return_value = True
    mock_rpc_success.execute.return_value = ToolResult(
        call_id="call-c6-success",
        ok=True,
        exit_code=0,
        content="25\n",
        structured={"stdout": "25\n"},
        elapsed_ms=10.0,
    )

    service_success = SandboxService()
    service_success.rpc = mock_rpc_success
    result_success = service_success.execute_tool(
        call_id="call-c6-success",
        tool_name="run_python",
        args={"code": "5 * 5"},
        confirmed=True,
    )
    assert result_success.ok is True
    assert result_success.exit_code == 0
    assert result_success.content == "25\n"

    # 2. No-Docker policy_violation path
    mock_rpc_nodocker = MagicMock()
    mock_rpc_nodocker.use_direct_fallback = False
    mock_rpc_nodocker.is_docker_available.return_value = False

    service_nodocker = SandboxService()
    service_nodocker.rpc = mock_rpc_nodocker
    result_nodocker = service_nodocker.execute_tool(
        call_id="call-c6-nodocker",
        tool_name="run_python",
        args={"code": "5 * 5"},
        confirmed=True,
    )
    assert result_nodocker.ok is False
    assert result_nodocker.exit_code == -1
    assert "policy_violation" in result_nodocker.stderr
