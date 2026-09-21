"""
Project Lucca — Rung L2 Shadow Telemetry & Contrastive Evaluation Test Suite
Spec 1.1.2 §5 (S1 Contract), §6.2 (Rung L2), §9 (Ladder Acceptance Tests)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import ulid

from lucca.admin import run_rules_cli
from lucca.core.capabilities import get_default_native_tools
from lucca.core.schemas import (
    CandidateRule,
    Plan,
    Say,
    ToolCall,
)
from lucca.memory.db import DatabaseManager
from lucca.reasoning.lifecycle import (
    RuleLifecycleManager,
    check_plan_and_core_agreement,
)
from lucca.reasoning.replay import ReplayEngine
from lucca.reasoning.scheme.parser import parse_rule
from lucca.reasoning.stats import mcnemar_test, wilson_score_interval


@pytest.fixture
def temp_db(tmp_path: Path) -> DatabaseManager:
    db_path = tmp_path / "test_l2_memory.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()
    yield db
    db.close()


def _insert_dummy_decisions(
    db: DatabaseManager,
    count: int,
    intent: str = "math_eval",
    transcript: str = "calculate 1 + 1",
    entities: dict[str, list[str]] | None = None,
    user_interrupted: bool = False,
    tool_calls: list[dict[str, object]] | None = None,
) -> None:
    """Helper to insert real-schema decision records for Dream-RSI replay testing."""
    if entities is None:
        entities = {"expr": ["1 + 1"]}
    if tool_calls is None:
        tool_calls = [{"call_id": "c1", "tool": "run_python", "args": {"code": "1 + 1"}}]

    writer = db.get_writer()
    writer.execute("BEGIN IMMEDIATE")
    try:
        for i in range(count):
            dec_id = str(ulid.ULID())
            trace_id = f"trace-{dec_id}"
            feats = {
                "transcript": transcript,
                "transcript_lower": transcript.lower(),
                "intent": intent,
                "intent_conf": 0.95,
                "entities": entities,
                "hour_local": 14,
                "weekday": 2,
                "apps_running": [],
                "last_tool": None,
                "last_tool_ok": None,
                "session_turns": i,
                "mode": "transcript",
            }
            writer.execute(
                """
                INSERT INTO decisions (
                    decision_id, trace_id, session_id, ts, features_json,
                    action, probabilities_json, prediction_set_json, fallback_applied,
                    elapsed_us, router_version, executed_path, tool_calls_json,
                    tool_ok, user_interrupted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dec_id,
                    trace_id,
                    "session-1",
                    time.time() - (count - i),
                    json.dumps(feats),
                    "ACT_THEN_NARRATE",
                    "{}",
                    "[]",
                    0,
                    1200,
                    "0.1.0",
                    "RULE",
                    json.dumps(tool_calls),
                    1,
                    1 if user_interrupted else 0,
                ),
            )
        writer.execute("COMMIT")
    except Exception:
        writer.execute("ROLLBACK")
        raise


# -----------------------------------------------------------------------------
# 1. Statistical Verification Tests (Wilson Score Interval & McNemar)
# -----------------------------------------------------------------------------


def test_wilson_score_interval_mathematical_properties() -> None:
    """Validates boundary conditions, Newcombe continuity correction, and clamping."""
    # N=0 returns full uncertainty [0.0, 1.0]
    lb0, ub0 = wilson_score_interval(0, 0)
    assert lb0 == 0.0 and ub0 == 1.0

    # successes=0 lower bound is clamped to 0.0
    lb_zero, ub_zero = wilson_score_interval(0, 50)
    assert lb_zero == 0.0
    assert 0.0 < ub_zero < 0.1

    # successes=total upper bound is clamped to 1.0
    lb_full, ub_full = wilson_score_interval(50, 50)
    assert ub_full == 1.0
    assert 0.9 < lb_full < 1.0

    # Intermediate known case: 10 successes in 20 trials (50% empirical)
    lb_half, ub_half = wilson_score_interval(10, 20)
    assert 0.25 < lb_half < 0.35
    assert 0.65 < ub_half < 0.75
    assert lb_half < 0.5 < ub_half

    # Invalid arguments raise ValueError
    with pytest.raises(ValueError, match="Invalid binomial counts"):
        wilson_score_interval(-1, 10)
    with pytest.raises(ValueError, match="Invalid binomial counts"):
        wilson_score_interval(15, 10)


def test_mcnemar_test_contingency() -> None:
    """Validates exact binomial (b+c < 25) and Edwards continuity-corrected chi-square."""
    # Zero discordance -> p = 1.0
    assert mcnemar_test(0, 0) == 1.0
    assert mcnemar_test(5, 5) == 1.0

    # Small sample (b+c < 25): exact binomial
    # b=0, c=10 -> P(X=0) * 2 = 2 * (0.5)^10 = 0.001953125
    p_exact = mcnemar_test(0, 10)
    assert pytest.approx(p_exact, rel=1e-3) == 0.001953125

    # Large sample (b+c >= 25): Edwards continuity-corrected chi2
    p_large = mcnemar_test(25, 5)
    assert p_large < 0.001

    with pytest.raises(ValueError, match="Discordant counts must be non-negative"):
        mcnemar_test(-1, 5)


def test_rule_of_three_ucl() -> None:
    """Spec §6.1: 0 failures in n clusters bounds failure rate to ~3/n, never to 'safe'."""
    from lucca.reasoning.stats import rule_of_three_ucl

    # No evidence at all -> total uncertainty
    assert rule_of_three_ucl(0) == 1.0

    # 5 clean clusters -> UCL ~45% (the documented "5 clusters => <=60% failure bound"
    # is the looser 3/n approximation; the exact one-sided bound is 1 - 0.05^(1/5))
    ucl5 = rule_of_three_ucl(5)
    assert 0.40 < ucl5 < 0.50
    assert ucl5 < 0.60  # strictly tighter than the 3/n approximation

    # Monotonically decreasing with more evidence, never reaches 0
    ucl50 = rule_of_three_ucl(50)
    assert 0.0 < ucl50 < ucl5
    assert rule_of_three_ucl(500) < ucl50

    with pytest.raises(ValueError, match="confidence must be in"):
        rule_of_three_ucl(5, confidence=1.5)


# -----------------------------------------------------------------------------
# 2. Dream-RSI Replay Engine & Zero Synthetic Padding Invariant
# -----------------------------------------------------------------------------


def test_replay_insufficient_history_fails_closed(temp_db: DatabaseManager) -> None:
    """Enforces Zero Synthetic Padding: candidate rule refuses if N_real < 50."""
    # Insert only 5 interaction episodes (N_real = 5 < 50)
    _insert_dummy_decisions(temp_db, count=5)

    rule_source = """
    (rule "calc-test-v1"
      :when (intent= "math_eval")
      :plan (list (tool "run_python" :code "1 + 1"))
      :priority 10)
    """
    rule_def = parse_rule(rule_source)
    engine = ReplayEngine(min_episodes=50)

    episodes = engine.load_past_episodes(temp_db, limit=50)
    assert len(episodes) == 5

    report = engine.replay_candidate_rule(rule_def, episodes)
    assert report.passed is False
    assert report.n_real == 5
    assert report.min_required == 50
    assert any("INSUFFICIENT_HISTORY: N_real=5 < 50" in r for r in report.reasons)


def test_replay_passes_clean_rule_on_50_real_schema_episodes(temp_db: DatabaseManager) -> None:
    """Verifies a clean rule passes Dream-RSI replay when 50 real episodes are present."""
    _insert_dummy_decisions(temp_db, count=50)

    rule_source = """
    (rule "calc-test-v1"
      :when (intent= "math_eval")
      :plan (list (tool "run_python" :code "1 + 1"))
      :priority 10)
    """
    rule_def = parse_rule(rule_source)
    engine = ReplayEngine(min_episodes=50)

    episodes = engine.load_past_episodes(temp_db, limit=50)
    assert len(episodes) == 50

    report = engine.replay_candidate_rule(rule_def, episodes)
    assert report.passed is True
    assert report.n_real == 50
    assert report.errors == 0
    assert report.misfires == 0
    assert report.fires == 50
    assert any("REPLAY_PASSED" in r for r in report.reasons)


def test_replay_rejects_failing_or_buggy_rule(temp_db: DatabaseManager) -> None:
    """Verifies runtime errors and misfires cause immediate replay rejection."""
    # 1. Runtime exception in rule evaluation (e.g. division by zero in condition)
    _insert_dummy_decisions(temp_db, count=50)

    rule_buggy = """
    (rule "calc-err-v1"
      :when (and (intent= "math_eval") (= 1 (/ 1 0)))
      :plan (list (say "crash"))
      :priority 10)
    """
    rule_def = parse_rule(rule_buggy)
    engine = ReplayEngine(min_episodes=50)

    episodes = engine.load_past_episodes(temp_db, limit=50)
    report = engine.replay_candidate_rule(rule_def, episodes)
    assert report.passed is False
    assert report.errors > 0
    assert any("RUNTIME_ERRORS" in r for r in report.reasons)

    # 2. Misfire on dangerous intent
    _insert_dummy_decisions(temp_db, count=1, intent="dangerous", transcript="delete system")
    episodes_with_danger = engine.load_past_episodes(temp_db, limit=50)

    # Rule that indiscriminately fires on anything
    rule_loose = """
    (rule "loose-fire-v1"
      :when (hour-between? 0 24)
      :plan (list (say "fire"))
      :priority 10)
    """
    rule_loose_def = parse_rule(rule_loose)
    rep_misfire = engine.replay_candidate_rule(rule_loose_def, episodes_with_danger)
    assert rep_misfire.passed is False
    assert rep_misfire.misfires > 0
    assert any("MISFIRES" in r for r in rep_misfire.reasons)


# -----------------------------------------------------------------------------
# 3. Contrastive Shadow Logging & Agreement Logic (ModularRSI §3.3)
# -----------------------------------------------------------------------------


def test_contrastive_agreement_logic() -> None:
    """Tests the formal check_plan_and_core_agreement predicate across cases."""
    # Case 1: Matching tool calls
    p_tool = Plan(actions=[ToolCall(tool="run_python", args={"code": "1 + 1"}, call_id="c1")])
    core_tool = [ToolCall(tool="run_python", args={"code": "1 + 1"}, call_id="c2")]
    assert check_plan_and_core_agreement(p_tool, core_tool, core_path="RULE") is True

    # Argument mismatch
    core_diff_arg = [ToolCall(tool="run_python", args={"code": "2 + 2"}, call_id="c3")]
    assert check_plan_and_core_agreement(p_tool, core_diff_arg, core_path="RULE") is False

    # Tool name mismatch
    core_diff_tool = [ToolCall(tool="read_file", args={"rel_path": "x.txt"}, call_id="c4")]
    assert check_plan_and_core_agreement(p_tool, core_diff_tool, core_path="RULE") is False

    # Case 2: Abstention / Yield
    p_empty = Plan(actions=[])
    # Agreed if core handled conversationally without tool
    assert check_plan_and_core_agreement(p_empty, None, core_path="LLM") is True
    # Disagreed if core invoked a tool
    assert check_plan_and_core_agreement(p_empty, core_tool, core_path="LLM") is False

    # Case 3: Pure Say
    p_say = Plan(actions=[Say(text="Hello operator.")])
    assert check_plan_and_core_agreement(p_say, None, core_path="LLM") is True
    assert check_plan_and_core_agreement(p_say, core_tool, core_path="LLM") is False


def test_contrastive_shadow_logging_and_summary(temp_db: DatabaseManager) -> None:
    """Verifies persisting paired contrastive shadow logs and computing Wilson/McNemar summary."""
    tools = get_default_native_tools()
    manager = RuleLifecycleManager(registered_tools=tools, db=temp_db)

    rule_source = """
    (rule "contrast-test-v1"
      :when (intent= "math_eval")
      :plan (list (tool "run_python" :code "1 + 1"))
      :priority 10)
    """
    managed = manager.register_rule(rule_source)
    rule_id = managed.rule_id

    # Log 10 agreeing turns where both rule and core succeeded
    plan = Plan(actions=[ToolCall(tool="run_python", args={"code": "1 + 1"}, call_id="c1")])
    core_tool = [ToolCall(tool="run_python", args={"code": "1 + 1"}, call_id="c2")]

    for i in range(10):
        manager.log_contrastive_shadow_pair(
            rule_id=rule_id,
            trace_id=f"tr-{i}",
            rule_plan=plan,
            core_tool_calls=core_tool,
            core_path="RULE",
            rule_outcome_signal="tool_exit_zero",
            core_outcome_signal="tool_exit_zero",
        )

    # Log 2 discordant turns: rule better (b: rule ok, core errored)
    for i in range(10, 12):
        manager.log_contrastive_shadow_pair(
            rule_id=rule_id,
            trace_id=f"tr-{i}",
            rule_plan=plan,
            core_tool_calls=core_tool,
            core_path="LLM",
            rule_outcome_signal="tool_exit_zero",
            core_outcome_signal="error",
        )

    summary = manager.get_contrastive_summary(rule_id)
    assert summary["total_turns"] == 12
    assert summary["b_rule_better"] == 2
    assert summary["c_core_better"] == 0
    assert summary["rate_label"] == "Execution-Reliability Rate (S1)"

    # Check Wilson intervals
    ag_interval = summary["agreed_interval"]
    assert isinstance(ag_interval, list)
    assert 0.0 <= ag_interval[0] <= ag_interval[1] <= 1.0

    rel_interval = summary["rule_reliability_interval"]
    assert isinstance(rel_interval, list)
    assert 0.0 <= rel_interval[0] <= rel_interval[1] <= 1.0


# -----------------------------------------------------------------------------
# 4. Candidate Rule Promotion Requires Dream-RSI Replay Pass
# -----------------------------------------------------------------------------


def test_candidate_promotion_requires_replay_pass(temp_db: DatabaseManager) -> None:
    """Verifies that induced candidate rules cannot promote without passing Dream-RSI replay."""
    tools = get_default_native_tools()
    manager = RuleLifecycleManager(registered_tools=tools, db=temp_db)

    rule_source = """
    (rule "induced-calc-v1"
      :when (intent= "math_eval")
      :plan (list (tool "run_python" :code "1 + 1"))
      :priority 10)
    """
    cand = CandidateRule(
        rule_id="induced-calc-v1",
        s_expression=rule_source,
        intended_intent="math_eval",
    )
    rule_id = manager.register_candidate(cand)
    assert manager.rules[rule_id].is_induced is True

    # 1. Fails closed when database has N_real = 0 < 50
    plan = Plan(actions=[ToolCall(tool="run_python", args={"code": "1 + 1"}, call_id="c1")])
    # Record 5 success clusters
    for i in range(5):
        manager.record_shadow(
            rule_id,
            matched=True,
            cluster_id=f"cl-{i}",
            plan_snapshot=plan,
        )

    res_fail = manager.promote_if_eligible(rule_id)
    assert res_fail.promoted is False
    assert "Dream-RSI offline replay failed" in res_fail.reason
    assert "INSUFFICIENT_HISTORY" in res_fail.reason

    # 2. Populate 50 episodes in DB -> replay passes and promotion succeeds
    _insert_dummy_decisions(temp_db, count=50)
    res_pass = manager.promote_if_eligible(rule_id)
    assert res_pass.promoted is False  # Transitions to PENDING_APPROVAL
    assert manager.rules[rule_id].status == "PENDING_APPROVAL"

    res_appr = manager.approve_rule(rule_id)
    assert res_appr.promoted is True
    assert manager.rules[rule_id].status == "ACTIVE"


# -----------------------------------------------------------------------------
# 5. Admin CLI: rules replay & rules report
# -----------------------------------------------------------------------------


def test_admin_rules_replay_and_report_cli(
    temp_db: DatabaseManager, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifies lucca-admin rules replay and rules report subcommands."""
    tools = get_default_native_tools()
    manager = RuleLifecycleManager(registered_tools=tools, db=temp_db)

    rule_source = """
    (rule "admin-calc-v1"
      :when (intent= "math_eval")
      :plan (list (tool "run_python" :code "1 + 1"))
      :priority 10)
    """
    manager.register_rule(rule_source)
    db_file = temp_db.db_path

    # 1. Replay with 0 episodes -> exit code 1
    code_fail = run_rules_cli("replay", rule_id="admin-calc-v1", db_path=db_file)
    assert code_fail == 1
    captured_fail = capsys.readouterr().out
    assert "FAILED: Replay Refused" in captured_fail
    assert "INSUFFICIENT_HISTORY" in captured_fail

    # 2. Populate 50 episodes -> exit code 0
    _insert_dummy_decisions(temp_db, count=50)
    code_pass = run_rules_cli("replay", rule_id="admin-calc-v1", db_path=db_file)
    assert code_pass == 0
    captured_pass = capsys.readouterr().out
    assert "SUCCESS: Replay Passed" in captured_pass

    # 3. Report subcommand displays S1 semantics and Wilson intervals
    code_report = run_rules_cli("report", db_path=db_file)
    assert code_report == 0
    captured_report = capsys.readouterr().out
    assert "admin-calc-v1" in captured_report
    assert "(S1)" in captured_report
    assert "S1 Contract" in captured_report
