"""
Unit tests for unified capability registry, 3-class tool taxonomy, and C5/C6 gates.
Spec 1.1.2 §2, Phase 1 (T1), §0.0 C1-C6.
"""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from lucca.core.capabilities import (
    MAX_REGISTRY_TOOLS,
    get_capability_registry,
    get_default_native_tools,
)
from lucca.core.exceptions import RuleError
from lucca.core.schemas import Risk, ToolParameter, ToolSchema
from lucca.reasoning.lifecycle import RuleLifecycleManager, get_default_tool_schemas
from lucca.reasoning.scheme.validator import validate_rule_static
from lucca.sandbox.service import SandboxService


def test_target_required_on_tool_schema() -> None:
    """T1.1 / C4: target is required on ToolSchema and fails validation if missing."""
    with pytest.raises(ValidationError) as exc_info:
        ToolSchema(  # type: ignore[call-arg]
            name="dummy_tool",
            description="A dummy tool",
            parameters={"p": ToolParameter(type="string", description="param")},
            risk=Risk.READ,
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("target",) for e in errors)


def test_tool_taxonomy_and_registry_count() -> None:
    """T1.1 / T1.6 / T2 / C1 / C2: Registry has exactly 18 tools (<= 18 cap),
    correctly classified. Revised by WO-9 A13 (F14: launch_app advertised),
    A14 (F18: self_history_search exposed), and WO-10.5 (F15: run_python_async)."""
    registry = get_capability_registry()
    tools = registry.tools
    tool_defs = registry.get_tool_definitions()
    def_names = [t.function.name for t in tool_defs]

    # Assert count == 19 and <= cap
    assert len(tools) == 19
    assert len(tools) <= MAX_REGISTRY_TOOLS
    assert len(tool_defs) == 19

    # launch_app is now advertised, confirmation-gated (WO-9 A13)
    assert "launch_app" in tools
    assert tools["launch_app"].risk == Risk.LAUNCH

    # Required newly exposed and surviving tools
    expected_tools = {
        "read_file",
        "write_file",
        "search_web",
        "fetch_url",
        "query_capabilities",
        "list_dir",
        "search_text",
        "run_python",
        "invoke_skill",
        "memory_search",
        "memory_commit",
        "note_write",
        "note_read",
        "self_metrics",
        "sys_info",
        "launch_app",
        "self_history_search",
        "run_python_async",
        "calc_math",
    }
    assert set(tools.keys()) == expected_tools
    assert set(def_names) == expected_tools

    # Taxonomy target classifications
    assert tools["query_capabilities"].target == "host_readonly"
    assert tools["sys_info"].target == "host_readonly"
    assert tools["read_file"].target == "self"
    assert tools["write_file"].target == "self"
    assert tools["search_web"].target == "self"
    assert tools["fetch_url"].target == "self"
    assert tools["list_dir"].target == "self"
    assert tools["calc_math"].target == "self"
    assert tools["calc_math"].risk == Risk.READ
    assert tools["search_text"].target == "self"
    assert tools["run_python"].target == "self"
    assert tools["invoke_skill"].target == "self"
    assert tools["memory_search"].target == "self"
    assert tools["memory_commit"].target == "self"
    assert tools["note_write"].target == "self"
    assert tools["note_read"].target == "self"
    assert tools["self_metrics"].target == "self"
    assert tools["run_python_async"].target == "self"


def test_manifest_matches_registry_tools() -> None:
    """T1.5: get_capabilities_manifest derives tools dynamically from registry."""
    registry = get_capability_registry()
    manifest = registry.get_capabilities_manifest()

    manifest_tools = manifest.get("tools")
    assert isinstance(manifest_tools, list)
    expected_names = sorted(registry.tools.keys())
    assert sorted(manifest_tools) == expected_names

    # No skill_*, no phantom task tools (launch_app now advertised — WO-9 A13)
    assert not any(t.startswith("skill_") for t in manifest_tools)
    assert "get_task_status" not in manifest_tools
    assert "list_tasks" not in manifest_tools
    assert "cancel_task" not in manifest_tools


def test_c5_negative_rule_with_removed_tool_fails_static_validation() -> None:
    """
    C5 negative test: A rule whose plan calls a phantom tool fails
    validate_rule_static against get_default_tool_schemas() naming the unknown
    tool. (Revised by WO-9 A13: launch_app is now a registered tool, so the
    negative case uses a genuinely phantom tool name.)
    """
    rule_src = """
    (rule "phantom-tool-rule-v1"
      :when (intent= "unknown")
      :plan (list (tool "format_drive" :drive "c"))
      :priority 10)
    """
    current_schemas = get_default_tool_schemas()
    assert "format_drive" not in current_schemas

    with pytest.raises(RuleError) as exc_info:
        validate_rule_static(rule_src, registered_tools=current_schemas)
    assert "not in registered tool list" in str(exc_info.value).lower()
    assert "format_drive" in str(exc_info.value)


def test_user_retire_mechanism_marks_rule_retired_and_stops_it_firing() -> None:
    """
    C5 (mechanism): user_retire() on an isolated engine sets RETIRED, stamps retired_at,
    and the rule no longer fires on a matching state.

    The original version of this test was vacuous — it was wrapped in
    ``if rule_id in lifecycle.rules:`` and read the production DB, so it passed by doing
    nothing whenever the rule was absent. The production-state fact ("calc-open-with-expr-v1
    is RETIRED") is an ops observation recorded in the Phase 1 gate worklog via
    ``lucca-admin rules list``, not a unit-test property.
    """
    from lucca.core.schemas import RuleState

    engine = RuleLifecycleManager(registered_tools=get_default_native_tools())
    src = """
    (rule "retire-me-v1"
      :when (intent= "calculate")
      :plan (list (tool "run_python" :code "1 + 1"))
      :priority 10)
    """
    managed = engine.register_rule(src)
    managed.status = "ACTIVE"
    assert "retire-me-v1" in engine.rules

    engine.user_retire("retire-me-v1")

    rule = engine.rules["retire-me-v1"]
    assert rule.status == "RETIRED"
    assert rule.user_retired is True
    assert rule.retired_at is not None

    # A RETIRED rule must not fire in either mode, even on a perfectly matching state.
    state = RuleState(
        transcript="calculate 1 + 1",
        transcript_lower="calculate 1 + 1",
        intent="calculate",
        intent_conf=0.99,
    )
    for mode in ("active", "shadow"):
        outcomes = engine.evaluate(state, mode=mode)  # type: ignore[arg-type]
        fired_ids = {o.rule_id for o in outcomes if o.fired}
        assert "retire-me-v1" not in fired_ids, f"RETIRED rule fired in mode={mode}"


def test_c6_run_python_no_docker_returns_policy_violation() -> None:
    """
    C6: When sandbox RPC is in no-Docker / direct fallback mode,
    run_python returns structured policy_violation ToolResult (ok=False) and does not raise.
    """
    mock_rpc = MagicMock()
    mock_rpc.use_direct_fallback = False
    mock_rpc.is_docker_available.return_value = False

    service = SandboxService()
    service.rpc = mock_rpc
    result = service.execute_tool(
        call_id="call-c6-test",
        tool_name="run_python",
        args={"code": "print(2 + 2)"},
        confirmed=True,
    )

    assert result.ok is False
    assert result.exit_code == -1
    assert "policy_violation" in result.stderr
    assert isinstance(result.structured, dict)
    assert result.structured.get("ok") is False
    assert "policy_violation" in str(result.structured.get("stderr", ""))
