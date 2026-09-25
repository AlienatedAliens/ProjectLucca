"""
Project Lucca — Rule Lifecycle & Distinctness Mechanical Tests
Spec 05 §8, §9, §11 (T-RULE-03, T-RULE-04, T-RULE-05)
"""

from pathlib import Path

import pytest

from lucca.core.schemas import Plan, Risk, RuleState, ToolCall, ToolParameter, ToolSchema
from lucca.memory.db import DatabaseManager
from lucca.reasoning.lifecycle import RuleLifecycleManager, compute_cluster_id, plans_match

SAMPLE_RULE = """
(rule "open-calc-v1"
  :when (and (intent= "launch_app") (entity-has? "app" "calculator"))
  :plan (list (tool "launch_app" :app "calculator"))
  :priority 5)
"""


@pytest.fixture
def tools():
    return {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
            target="self",
        )
    }


def test_t_rule_03_distinctness_scenarios():
    """
    T-RULE-03: Distinctness scenarios:
    1. Repeating 5x in one minute -> 1 cluster
    2. Same request on 5 different days -> 5 clusters
    3. Same day, 5 turns 20 minutes apart -> 5 clusters
    """
    session_id = "sess-alpha"
    base_ts = 1000000.0

    # Scenario 1: 5 requests in 60s (same session, same 15-min bucket, same semantic cluster)
    clusters_1 = {
        compute_cluster_id(session_id, base_ts + i * 10, semantic_cluster=0) for i in range(5)
    }
    assert len(clusters_1) == 1

    # Scenario 2: Same request on 5 different days (differs by 86400s)
    clusters_2 = {
        compute_cluster_id(session_id, base_ts + i * 86400, semantic_cluster=0) for i in range(5)
    }
    assert len(clusters_2) == 5

    # Scenario 3: Same day, 20 minutes (1200s) apart (> 900s bucket)
    clusters_3 = {
        compute_cluster_id(session_id, base_ts + i * 1200, semantic_cluster=0) for i in range(5)
    }
    assert len(clusters_3) == 5


def test_t_rule_04_lifecycle_state_transitions(tools):
    """
    T-RULE-04: Lifecycle state machine:
    QUARANTINE + 5 distinct + 0 fail -> ACTIVE
    ACTIVE + 1 fail -> DEMOTED -> QUARANTINE (counters reset)
    QUARANTINE -> ACTIVE -> 2nd fail -> RETIRED
    """
    manager = RuleLifecycleManager(registered_tools=tools)
    managed = manager.register_rule(SAMPLE_RULE)
    assert managed.status == "QUARANTINE"

    state = RuleState(
        schema_version=1,
        intent="launch_app",
        entities={"app": ["calculator"]},
    )
    plan = Plan(actions=[ToolCall(tool="launch_app", args={"app": "calculator"}, call_id="c1")])

    # Record 4 distinct successes -> still cannot promote
    for i in range(4):
        cid = f"cluster_{i}"
        manager.record_shadow(
            "open-calc-v1", matched=True, cluster_id=cid, state_snapshot=state, plan_snapshot=plan
        )

    res4 = manager.promote_if_eligible("open-calc-v1")
    assert res4.promoted is False
    assert managed.status == "QUARANTINE"

    # 5th distinct success -> promote transitions to PENDING_APPROVAL awaiting human operator
    manager.record_shadow(
        "open-calc-v1",
        matched=True,
        cluster_id="cluster_4",
        state_snapshot=state,
        plan_snapshot=plan,
    )
    res5 = manager.promote_if_eligible("open-calc-v1")
    assert res5.promoted is False
    assert manager.rules["open-calc-v1"].status == "PENDING_APPROVAL"

    # Human operator signs off
    appr_res = manager.approve_rule("open-calc-v1", approver="sec-lead")
    assert appr_res.promoted is True
    assert manager.rules["open-calc-v1"].status == "ACTIVE"

    # 1 active failure -> DEMOTED -> QUARANTINE with reset counters
    manager.record_shadow("open-calc-v1", matched=False, cluster_id="fail_cluster")
    assert manager.rules["open-calc-v1"].status == "QUARANTINE"
    assert manager.rules["open-calc-v1"].demotion_count == 1
    assert len(manager.rules["open-calc-v1"].success_clusters) == 0

    # Promote again needs 5 fresh distinct clusters
    for i in range(5):
        manager.record_shadow(
            "open-calc-v1",
            matched=True,
            cluster_id=f"fresh_cluster_{i}",
            state_snapshot=state,
            plan_snapshot=plan,
        )
    res_repromote = manager.promote_if_eligible("open-calc-v1")
    assert res_repromote.promoted is False
    assert manager.rules["open-calc-v1"].status == "PENDING_APPROVAL"
    reappr = manager.approve_rule("open-calc-v1")
    assert reappr.promoted is True
    assert manager.rules["open-calc-v1"].status == "ACTIVE"

    # 2nd active failure -> RETIRED
    manager.record_shadow("open-calc-v1", matched=False, cluster_id="fail_cluster_2")
    assert manager.rules["open-calc-v1"].status == "RETIRED"
    assert manager.rules["open-calc-v1"].demotion_count == 2


def test_t_rule_05_regression_suite_catches_mutation(tools):
    """T-RULE-05: Regression suite fails if an active rule changes plan or introduces conflict."""
    manager = RuleLifecycleManager(registered_tools=tools)
    manager.register_rule(SAMPLE_RULE)

    state = RuleState(schema_version=1, intent="launch_app", entities={"app": ["calculator"]})
    plan = Plan(actions=[ToolCall(tool="launch_app", args={"app": "calculator"}, call_id="c1")])

    for i in range(5):
        manager.record_shadow(
            "open-calc-v1",
            matched=True,
            cluster_id=f"c_{i}",
            state_snapshot=state,
            plan_snapshot=plan,
        )

    manager.promote_if_eligible("open-calc-v1")
    manager.approve_rule("open-calc-v1")
    assert len(manager.regression_cases) == 5

    # Clean regression report
    report_clean = manager.verify_regression_suite()
    assert report_clean.passed is True
    assert report_clean.cases_evaluated == 5
    assert len(report_clean.failures) == 0

    # Mutate rule definition to produce a different plan (say instead of tool)
    mutated_rule = """
    (rule "open-calc-v1"
      :when (and (intent= "launch_app") (entity-has? "app" "calculator"))
      :plan (list (say "Opening calculator"))
      :priority 5)
    """
    from lucca.reasoning.scheme.parser import parse_rule

    manager.rules["open-calc-v1"].definition = parse_rule(mutated_rule)

    # Verification must now FAIL
    report_mutated = manager.verify_regression_suite()
    assert report_mutated.passed is False
    assert len(report_mutated.failures) > 0


def test_record_shadow_errored_treated_as_failure(tools):
    """F-REAS-004: record_shadow with errored=True is treated as matched=False."""
    manager = RuleLifecycleManager(registered_tools=tools)
    manager.register_rule(SAMPLE_RULE)
    # When errored=True, even if matched=True was passed, failure_count increments
    manager.record_shadow("open-calc-v1", matched=True, cluster_id="c_err", errored=True)
    assert manager.rules["open-calc-v1"].failure_count == 1
    assert len(manager.rules["open-calc-v1"].success_clusters) == 0


def test_evaluate_shadow_records_clusters(tools):
    """F-REAS-003: evaluate() in shadow mode records success clusters for quarantined rules."""
    manager = RuleLifecycleManager(registered_tools=tools)
    manager.register_rule(SAMPLE_RULE)
    assert manager.rules["open-calc-v1"].status == "QUARANTINE"

    state = RuleState(
        schema_version=1,
        transcript="open calculator",
        intent="launch_app",
        entities={"app": ["calculator"]},
    )

    outcomes = manager.evaluate(state, mode="shadow")
    assert len(outcomes) == 1
    assert outcomes[0].fired is True
    assert outcomes[0].errored is False
    assert len(manager.rules["open-calc-v1"].success_clusters) == 1





@pytest.fixture
def temp_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(db_path=tmp_path / "test_lifecycle.sqlite")
    db.migrate()
    return db


def test_rules_survive_restart(tools, temp_db: DatabaseManager):
    """F-REAS-002: Rule states and regression cases persist to SQLite across restarts."""
    # 1. Start with initial manager
    mgr1 = RuleLifecycleManager(registered_tools=tools, db=temp_db)
    managed = mgr1.register_rule(SAMPLE_RULE)
    assert managed.status == "QUARANTINE"

    # 2. Record 5 distinct cluster executions
    state = RuleState(
        schema_version=1,
        transcript="open calculator",
        transcript_lower="open calculator",
        intent="launch_app",
        intent_conf=0.95,
        entities={"app": ["calculator"]},
        apps_running=frozenset(),
    )
    plan = Plan(actions=[ToolCall(call_id="call-1", tool="launch_app", args={"app": "calculator"})])

    for i in range(5):
        mgr1.record_shadow(
            "open-calc-v1",
            matched=True,
            cluster_id=f"cluster-{i}",
            state_snapshot=state,
            plan_snapshot=plan,
        )

    # 3. Promote rule via human approval
    res_elig = mgr1.promote_if_eligible("open-calc-v1")
    assert res_elig.promoted is False
    assert mgr1.rules["open-calc-v1"].status == "PENDING_APPROVAL"

    result = mgr1.approve_rule("open-calc-v1")
    assert result.promoted is True
    assert mgr1.rules["open-calc-v1"].status == "ACTIVE"
    assert len(mgr1.regression_cases) == 5

    # 4. Simulate process restart by instantiating a fresh manager against the same database
    mgr2 = RuleLifecycleManager(registered_tools=tools, db=temp_db)

    # 5. Assert rule state and regression cases were restored
    assert "open-calc-v1" in mgr2.rules
    restored = mgr2.rules["open-calc-v1"]
    assert restored.status == "ACTIVE"
    assert len(restored.success_clusters) == 5
    assert len(mgr2.regression_cases) == 5
    assert mgr2.regression_cases[0].rule_id == "open-calc-v1"
    assert plans_match(mgr2.regression_cases[0].expected_plan, plan)

    # 6. Verify restored regression suite runs and passes cleanly
    report = mgr2.verify_regression_suite()
    assert report.passed is True
    assert report.cases_evaluated == 5

    # 7. Verify restored rule executes in active mode
    outcomes = mgr2.evaluate(state, mode="active")
    assert len(outcomes) == 1
    assert outcomes[0].fired is True
    assert plans_match(outcomes[0].plan, plan)


def test_pending_approval_human_gate(tools):
    """
    Test human-in-the-loop gate:
    1. Quarantine rule achieving 5 distinct clusters transitions to PENDING_APPROVAL.
    2. Rule in PENDING_APPROVAL does NOT fire during active evaluation.
    3. Operator calls approve_rule, promoting it to ACTIVE.
    4. Active evaluation now executes the rule.
    """
    manager = RuleLifecycleManager(registered_tools=tools, require_human_approval=True)
    manager.register_rule(SAMPLE_RULE)

    state = RuleState(
        schema_version=1,
        transcript="open calculator",
        intent="launch_app",
        entities={"app": ["calculator"]},
    )
    plan = Plan(actions=[ToolCall(tool="launch_app", args={"app": "calculator"}, call_id="c1")])

    for i in range(5):
        manager.record_shadow(
            "open-calc-v1",
            matched=True,
            cluster_id=f"cluster_gate_{i}",
            state_snapshot=state,
            plan_snapshot=plan,
        )

    # Promote check stops at PENDING_APPROVAL
    elig = manager.promote_if_eligible("open-calc-v1")
    assert elig.promoted is False
    assert manager.rules["open-calc-v1"].status == "PENDING_APPROVAL"

    # Must NOT fire in active mode
    active_outcomes = manager.evaluate(state, mode="active")
    assert len(active_outcomes) == 0

    # Unauthorized or invalid approve fails
    err_res = manager.approve_rule("non-existent-rule")
    assert err_res.promoted is False

    # Operator approves
    appr = manager.approve_rule("open-calc-v1", approver="admin")
    assert appr.promoted is True
    assert manager.rules["open-calc-v1"].status == "ACTIVE"

    # Now fires in active mode
    active_outcomes_after = manager.evaluate(state, mode="active")
    assert len(active_outcomes_after) == 1
    assert active_outcomes_after[0].fired is True


def test_autonomous_mode_flag(tools):
    """When require_human_approval=False, promote_if_eligible promotes directly to ACTIVE."""
    manager = RuleLifecycleManager(registered_tools=tools, require_human_approval=False)
    manager.register_rule(SAMPLE_RULE)

    state = RuleState(schema_version=1, intent="launch_app", entities={"app": ["calculator"]})
    plan = Plan(actions=[ToolCall(tool="launch_app", args={"app": "calculator"}, call_id="c1")])

    for i in range(5):
        manager.record_shadow(
            "open-calc-v1",
            matched=True,
            cluster_id=f"cluster_auto_{i}",
            state_snapshot=state,
            plan_snapshot=plan,
        )

    res = manager.promote_if_eligible("open-calc-v1")
    assert res.promoted is True
    assert manager.rules["open-calc-v1"].status == "ACTIVE"
