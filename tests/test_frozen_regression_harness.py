"""
Project Lucca — Frozen Evaluation Regression Harness (Proposal K / D-EVAL-01)
Executes 100+ frozen evaluation scenarios across:
1. System 1 Emergency Reflex (<150ms canned reflex)
2. Act-Then-Narrate Procedural Workflows (Rule execution then LLM speech)
3. System 2 Multi-Turn Tool Loops (Full LLM reasoning & verbal cues)
Guarantees zero regression, strict latency envelopes, and adherence to architecture invariants.
"""

import json
from pathlib import Path

import pytest

from lucca.brain.prompt_builder import (
    build_narration_messages,
    get_all_tool_definitions,
)
from lucca.core.exceptions import SchemeSyntaxError
from lucca.core.schemas import (
    ExecutionTier,
    MemoryHit,
    Provenance,
    RouteAction,
    ToolResult,
)
from lucca.memory.retrieval import format_memory_context
from lucca.reasoning.induction import RuleInducer
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.parser import parse_rule
from lucca.router.heuristic import HeuristicRouter

FIXTURES_PATH = Path("tests/fixtures/eval/golden_traces.jsonl")


def load_golden_traces() -> list[dict[str, str | bool | float | int]]:
    assert FIXTURES_PATH.exists(), f"Missing golden traces fixture: {FIXTURES_PATH}"
    traces: list[dict[str, str | bool | float | int]] = []
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if raw:
                traces.append(json.loads(raw))
    return traces


def test_golden_traces_dataset_integrity() -> None:
    """Verify golden traces dataset meets count and category quota (>= 100 total)."""
    traces = load_golden_traces()
    assert len(traces) >= 100, f"Expected at least 100 traces, got {len(traces)}"

    categories: dict[str, int] = {}
    for t in traces:
        cat = str(t["category"])
        categories[cat] = categories.get(cat, 0) + 1

    assert categories.get("system1_reflex", 0) >= 30, "Missing sufficient reflex traces"
    assert categories.get("act_then_narrate", 0) >= 35, "Missing sufficient act_then_narrate traces"
    assert categories.get("system2_loop", 0) >= 30, "Missing sufficient system2_loop traces"


def test_system1_emergency_reflex_traces() -> None:
    """
    Verify all System 1 Emergency Reflex scenarios route to REFLEX tier
    within < 150ms latency budget.
    """
    router = HeuristicRouter()
    traces = [t for t in load_golden_traces() if t["category"] == "system1_reflex"]

    for trace in traces:
        transcript = str(trace["transcript"])
        rule_fired = bool(trace.get("rule_fired", False))
        has_registered_rule = bool(trace.get("has_registered_rule", False))

        decision = router.route(
            transcript=transcript,
            any_active_rule_fired=rule_fired,
            has_registered_rule=has_registered_rule,
            vad_speech_ms=500,
        )

        assert decision.tier == ExecutionTier.REFLEX, (
            f"Failed tier for '{transcript}': expected REFLEX, got {decision.tier}"
        )
        assert decision.action == RouteAction.RULE, (
            f"Failed action for '{transcript}': expected RULE, got {decision.action}"
        )
        # Verify latency is within reflex envelope (< 150ms = 150,000us)
        assert decision.elapsed_us < 150_000, (
            f"Reflex latency exceeded budget for '{transcript}': {decision.elapsed_us}us"
        )


def test_act_then_narrate_procedural_traces() -> None:
    """
    Verify all Act-Then-Narrate scenarios route to ACT_THEN_NARRATE tier
    and extract intended procedural targets.
    """
    router = HeuristicRouter()
    traces = [t for t in load_golden_traces() if t["category"] == "act_then_narrate"]

    for trace in traces:
        transcript = str(trace["transcript"])
        rule_fired = bool(trace.get("rule_fired", True))
        has_registered_rule = bool(trace.get("has_registered_rule", True))

        decision = router.route(
            transcript=transcript,
            any_active_rule_fired=rule_fired,
            has_registered_rule=has_registered_rule,
            vad_speech_ms=500,
        )

        assert decision.tier == ExecutionTier.ACT_THEN_NARRATE, (
            f"Failed tier for '{transcript}': expected ACT_THEN_NARRATE, got {decision.tier}"
        )
        assert decision.action == RouteAction.RULE, (
            f"Failed action for '{transcript}': expected RULE, got {decision.action}"
        )


def test_system2_full_loop_traces() -> None:
    """
    Verify all complex conversational and multi-turn reasoning queries route
    to FULL_LOOP tier.
    """
    router = HeuristicRouter()
    traces = [t for t in load_golden_traces() if t["category"] == "system2_loop"]

    for trace in traces:
        transcript = str(trace["transcript"])
        rule_fired = bool(trace.get("rule_fired", False))
        has_registered_rule = bool(trace.get("has_registered_rule", False))

        decision = router.route(
            transcript=transcript,
            any_active_rule_fired=rule_fired,
            has_registered_rule=has_registered_rule,
            vad_speech_ms=1000,
        )

        assert decision.tier == ExecutionTier.FULL_LOOP, (
            f"Failed tier for '{transcript}': expected FULL_LOOP, got {decision.tier}"
        )
        assert decision.action == RouteAction.LLM, (
            f"Failed action for '{transcript}': expected LLM, got {decision.action}"
        )


def test_grounded_narration_provenance_contract() -> None:
    """
    Verify prompt builder enforces grounded narration provenance directives (D-BRAIN-04)
    and produces correctly formatted messages.
    """
    tool_results: list[ToolResult] = [
        ToolResult(
            call_id="call-01",
            ok=True,
            exit_code=0,
            structured={"app_name": "calc", "status": "launched"},
            content="Launched calculator successfully",
            elapsed_ms=10.0,
        ),
    ]

    messages = build_narration_messages(
        tool_name="launch_app",
        tool_args={"app_name": "calc"},
        tool_result=tool_results[0],
        user_text="Open the calculator and check notes",
    )

    assert len(messages) >= 2
    # Verify strict grounding instructions are included in the prompt
    system_prompts = [m.content for m in messages if m.role == "system"]
    assert any("grounded" in sp.lower() or "strict" in sp.lower() for sp in system_prompts)


def test_tool_definition_schema_compliance() -> None:
    """
    Verify all registered skill tools conform to OpenAI-compatible function calling schemas.
    """
    tools = get_all_tool_definitions()
    assert len(tools) >= 5, "Expected at least 5 registered tools"

    for tool in tools:
        assert tool.type == "function"
        assert tool.function.name != ""
        assert tool.function.description != ""
        assert "properties" in tool.function.parameters


def test_memory_quota_and_prioritization_invariant() -> None:
    """
    Verify memory budget prioritization under 2048 token constraint (D-MEM-03).
    Priority: USER_EXPLICIT > TOOL_VERIFIED > TOOL_CONTENT_UNTRUSTED.
    """
    import time

    now = time.time()
    hit_user = MemoryHit(
        memory_id=1,
        content="User preferred editor is vscode.",
        provenance=Provenance.USER_EXPLICIT,
        score=0.2,
        created_at=now - 100,
    )
    hit_untrusted = MemoryHit(
        memory_id=2,
        content="Untrusted web snippet about coding.",
        provenance=Provenance.TOOL_CONTENT_UNTRUSTED,
        score=0.99,
        created_at=now - 50,
    )
    hit_verified = MemoryHit(
        memory_id=3,
        content="Verified file observation on disk.",
        provenance=Provenance.TOOL_VERIFIED,
        score=0.5,
        created_at=now - 10,
    )

    rendered = format_memory_context(
        [hit_untrusted, hit_user, hit_verified], max_tokens=2048, now=now
    )
    lines = rendered.splitlines()
    assert len(lines) == 3
    # USER_EXPLICIT must come first (tier 0)
    assert "USER_EXPLICIT" in lines[0]
    # TOOL_VERIFIED must come second (tier 1)
    assert "TOOL_VERIFIED" in lines[1]
    # TOOL_CONTENT_UNTRUSTED must come third (tier 2)
    assert "TOOL_CONTENT_UNTRUSTED" in lines[2]


def test_macro_expansion_bounds_invariant() -> None:
    """
    Verify macro expander strictly terminates on recursive macros (D-REAS-05).
    """
    source = """
    (defmacro loop-a (x) (loop-b x))
    (defmacro loop-b (x) (loop-a x))
    (rule "inf-macro-eval"
      :when (loop-a "test")
      :plan (list (say "hi")))
    """
    with pytest.raises(SchemeSyntaxError) as exc_info:
        parse_rule(source)
    assert "depth limit exceeded" in str(exc_info.value).lower()


def test_rule_induction_quarantine_invariant(tmp_path: Path) -> None:
    """
    Verify induced rules are registered exclusively into QUARANTINE mode (D-REAS-06).
    """
    import time

    from lucca.core.schemas import Risk, ToolParameter, ToolSchema
    from lucca.memory.db import DatabaseManager

    db = DatabaseManager(db_path=tmp_path / "test_eval_mem.sqlite")
    db.migrate()

    tools = {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
            target="self",
        ),
    }
    lifecycle = RuleLifecycleManager(registered_tools=tools, db=db)

    # Insert 3 successful calculator launch decisions to trigger induction threshold
    for i in range(3):
        features = {
            "intent": "launch_app",
            "entities": {"app": ["calculator"]},
        }
        tool_calls = [{"tool": "launch_app", "args": {"app": "calculator"}, "call_id": f"c-{i}"}]
        with db.get_writer() as cur:
            cur.execute(
                """
                INSERT INTO decisions (
                    decision_id, trace_id, session_id, ts, features_json, action,
                    probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                    router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                    user_interrupted, interrupted_after_ms, counterfactual_rule_fired
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"dec-{i}",
                    f"trace-{i}",
                    "sess-01",
                    time.time() - (10 - i),
                    json.dumps(features),
                    "LLM",
                    "{}",
                    "[]",
                    0,
                    5000,
                    "heuristic-1.0",
                    "LLM",
                    json.dumps(tool_calls),
                    1,
                    150.0,
                    0,
                    0.0,
                    0,
                ),
            )

    inducer = RuleInducer(db=db, rule_engine=lifecycle, min_frequency=3)
    candidates = inducer.induce_and_quarantine()

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.rule_id in lifecycle.rules
    managed = lifecycle.rules[cand.rule_id]
    # Invariant: must be in QUARANTINE, never ACTIVE
    assert managed.status == "QUARANTINE"
    db.close()
