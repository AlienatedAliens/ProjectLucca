"""
Unit tests for invoke_skill dispatch contract.
Spec 1.1.2 §2.3, Phase 1 (T1.2).
"""

from unittest.mock import MagicMock

import pytest

from lucca.core.capabilities import dispatch_invoke_skill, get_default_native_tools
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import ToolResult
from lucca.core.trace import TurnTrace
from lucca.reasoning.lifecycle import RuleLifecycleManager
from tests.fakes.fake_asr import FakeASR


@pytest.fixture
def rule_engine():
    tools = get_default_native_tools()
    engine = RuleLifecycleManager(registered_tools=tools)

    # 1. Active & exposed
    active_src = """
    (rule "active-skill-v1"
      :when (intent= "calculate")
      :plan (list (tool "run_python" :code "1 + 1"))
      :priority 10)
    """
    m_active = engine.register_rule(active_src)
    m_active.status = "ACTIVE"
    m_active.expose_as_tool = True

    # 2. Active but NOT exposed
    unexposed_src = """
    (rule "unexposed-skill-v1"
      :when (intent= "calculate")
      :plan (list (tool "run_python" :code "2 + 2"))
      :priority 10)
    """
    m_unexposed = engine.register_rule(unexposed_src)
    m_unexposed.status = "ACTIVE"
    m_unexposed.expose_as_tool = False

    # 3. Quarantined skill (even if expose_as_tool is True)
    quarantine_src = """
    (rule "quarantine-skill-v1"
      :when (intent= "calculate")
      :plan (list (tool "run_python" :code "3 + 3"))
      :priority 10)
    """
    m_quarantine = engine.register_rule(quarantine_src)
    m_quarantine.status = "QUARANTINE"
    m_quarantine.expose_as_tool = True

    return engine


def test_invoke_skill_contract_unit(rule_engine: RuleLifecycleManager) -> None:
    """Tests all 5 dispatch contract conditions on dispatch_invoke_skill directly."""
    # (a) Active & exposed & in manifest -> OK
    ok, msg, payload = dispatch_invoke_skill(
        skill_id="active-skill-v1",
        args={"query": "test"},
        rule_engine=rule_engine,
        manifest_skill_ids={"active-skill-v1", "other-v1"},
    )
    assert ok is True
    assert "dispatched" in msg
    assert payload is not None
    assert payload["skill_id"] == "active-skill-v1"

    # (b) Not in manifest -> skill_not_in_manifest
    ok, reason, payload = dispatch_invoke_skill(
        skill_id="active-skill-v1",
        args={"query": "test"},
        rule_engine=rule_engine,
        manifest_skill_ids={"other-v1"},  # active-skill-v1 absent
    )
    assert ok is False
    assert reason == "skill_not_in_manifest"
    assert payload is not None and payload["error"] == "skill_not_in_manifest"

    # (c) QUARANTINE skill -> skill_not_exposed
    ok, reason, payload = dispatch_invoke_skill(
        skill_id="quarantine-skill-v1",
        args={},
        rule_engine=rule_engine,
        manifest_skill_ids={"quarantine-skill-v1"},
    )
    assert ok is False
    assert reason == "skill_not_exposed"
    assert payload is not None and payload["error"] == "skill_not_exposed"

    # (d) Unknown skill -> unknown_skill
    ok, reason, payload = dispatch_invoke_skill(
        skill_id="nonexistent-skill-v1",
        args={},
        rule_engine=rule_engine,
        manifest_skill_ids={"nonexistent-skill-v1"},
    )
    assert ok is False
    assert reason == "unknown_skill"
    assert payload is not None and payload["error"] == "unknown_skill"

    # (e) expose_as_tool: false -> skill_not_exposed
    ok, reason, payload = dispatch_invoke_skill(
        skill_id="unexposed-skill-v1",
        args={},
        rule_engine=rule_engine,
        manifest_skill_ids={"unexposed-skill-v1"},
    )
    assert ok is False
    assert reason == "skill_not_exposed"
    assert payload is not None and payload["error"] == "skill_not_exposed"


def test_orchestrator_invoke_skill_execution(rule_engine: RuleLifecycleManager) -> None:
    """Tests invoke_skill execution end-to-end through Orchestrator._handle_tool_call."""
    from tests.fakes.fake_tts import FakeTTS

    orchestrator = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    try:
        orchestrator.rule_engine = rule_engine
        trace = TurnTrace(trace_id="test-invoke-trace", t_capture_start=0)

        # Set manifest for current turn
        orchestrator.current_manifest_skill_ids = {"active-skill-v1"}

        # Mock sandbox execution for sub-tool
        orchestrator.sandbox.execute_tool = MagicMock(
            return_value=ToolResult(
                call_id="c-sub",
                ok=True,
                exit_code=0,
                content="2",
                elapsed_ms=1.0,
            )
        )

        # (a) Dispatch ACTIVE exposed skill in manifest -> plan executes
        res_ok = orchestrator._handle_tool_call(
            trace=trace,
            name="invoke_skill",
            args={"skill_id": "active-skill-v1", "args": {"query": "calc"}},
            speak=False,
        )
        assert res_ok is not None
        assert res_ok.ok is True
        assert "active-skill-v1" in str(res_ok.content)

        # (b) Not in manifest -> skill_not_in_manifest
        orchestrator.current_manifest_skill_ids = {"other-skill-v1"}
        res_not_in_manifest = orchestrator._handle_tool_call(
            trace=trace,
            name="invoke_skill",
            args={"skill_id": "active-skill-v1"},
            speak=False,
        )
        assert res_not_in_manifest is not None
        assert res_not_in_manifest.ok is False
        assert res_not_in_manifest.stderr == "skill_not_in_manifest"
        assert res_not_in_manifest.structured == {
            "error": "skill_not_in_manifest",
            "skill_id": "active-skill-v1",
        }

        # (c) QUARANTINE skill -> skill_not_exposed
        orchestrator.current_manifest_skill_ids = {"quarantine-skill-v1"}
        res_quarantine = orchestrator._handle_tool_call(
            trace=trace,
            name="invoke_skill",
            args={"skill_id": "quarantine-skill-v1"},
            speak=False,
        )
        assert res_quarantine is not None
        assert res_quarantine.ok is False
        assert res_quarantine.stderr == "skill_not_exposed"

        # (d) Unknown skill -> unknown_skill
        orchestrator.current_manifest_skill_ids = {"nonexistent-skill-v1"}
        res_unknown = orchestrator._handle_tool_call(
            trace=trace,
            name="invoke_skill",
            args={"skill_id": "nonexistent-skill-v1"},
            speak=False,
        )
        assert res_unknown is not None
        assert res_unknown.ok is False
        assert res_unknown.stderr == "unknown_skill"

        # (e) expose_as_tool: false -> skill_not_exposed
        orchestrator.current_manifest_skill_ids = {"unexposed-skill-v1"}
        res_unexposed = orchestrator._handle_tool_call(
            trace=trace,
            name="invoke_skill",
            args={"skill_id": "unexposed-skill-v1"},
            speak=False,
        )
        assert res_unexposed is not None
        assert res_unexposed.ok is False
        assert res_unexposed.stderr == "skill_not_exposed"
    finally:
        orchestrator.stop()
        orchestrator.cap_ring.close()
        orchestrator.cap_ring.unlink()
        orchestrator.play_ring.close()
        orchestrator.play_ring.unlink()
