"""
Project Lucca — Rule Lifecycle & Distinctness Mechanical Tests
Spec 05 §8, §9, §11 (T-RULE-03, T-RULE-04, T-RULE-05)
"""

import pytest

from lucca.core.schemas import Plan, Risk, RuleState, ToolCall, ToolParameter, ToolSchema
from lucca.reasoning.lifecycle import RuleLifecycleManager, compute_cluster_id

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

    # 5th distinct success -> promote succeeds
    manager.record_shadow(
        "open-calc-v1",
        matched=True,
        cluster_id="cluster_4",
        state_snapshot=state,
        plan_snapshot=plan,
    )
    res5 = manager.promote_if_eligible("open-calc-v1")
    assert res5.promoted is True
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
    assert res_repromote.promoted is True
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
