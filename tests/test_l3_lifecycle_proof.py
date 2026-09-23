"""
Project Lucca — L3 Lifecycle Proof (Rung L3, D-REAS-06)
Work Order 14, Phase 4

Proves one induced rule completes the full end-to-end lifecycle:
1. Induction: Seed >=3 recurring successful interactions (+ >=50 total history turns).
2. QUARANTINE: RuleInducer synthesizes MicroScheme rule and registers into QUARANTINE.
3. Replay: RuleLifecycleManager.replay_candidate() passes Dream-RSI offline replay.
4. Shadow Evaluation: Accumulate 5 clean shadow clusters via record_shadow() / emit_shadow_triple().
5. Review / Staging: promote_if_eligible() transitions rule to PENDING_APPROVAL.
6. Approval: approve_rule() promotes candidate to ACTIVE.
7. Execution: Active rule executes and produces valid ToolCall plan.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from lucca.core.schemas import Plan, Risk, RuleState, ToolCall, ToolParameter, ToolSchema
from lucca.memory.db import DatabaseManager
from lucca.reasoning.induction import RuleInducer
from lucca.reasoning.lifecycle import RuleLifecycleManager
from tests.helpers.decisions import _insert_decision


def test_l3_full_lifecycle_proof(tmp_path: Path) -> None:
    """
    Rung L3 Lifecycle Acceptance Gate:
    One induced rule completes the full lifecycle:
    induce -> QUARANTINE -> replay -> 5 clean shadow clusters -> PENDING_APPROVAL -> ACTIVE
    """
    # 1. Initialize DB and Lifecycle Manager
    db_file = tmp_path / "lifecycle_proof.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    tools = {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
            target="self",
        ),
        "read_file": ToolSchema(
            name="read_file",
            description="Read file",
            parameters={"path": ToolParameter(type="string", description="File path")},
            risk=Risk.READ,
            target="self",
        ),
    }

    rule_engine = RuleLifecycleManager(
        registered_tools=tools,
        db=db,
        require_human_approval=True,
    )

    # 2. Seed interaction history:
    # Need >= 50 total turns for Dream-RSI replay requirement
    # With >= 3 identical calculator launches to trigger induction
    now = time.time()
    for i in range(5):
        _insert_decision(
            db=db,
            decision_id=f"dec-calc-{i}",
            intent="launch_app",
            transcript="open calculator",
            tool_name="launch_app",
            args={"app": "calculator"},
            tool_ok=1,
            ts=now - (100.0 - i),
        )

    # 47 filler past episodes (chit chat, read file, etc.)
    for j in range(47):
        _insert_decision(
            db=db,
            decision_id=f"dec-filler-{j}",
            intent="file_read" if j % 2 == 0 else "chit_chat",
            transcript=f"read file doc_{j}.txt" if j % 2 == 0 else "hello there",
            tool_name="read_file" if j % 2 == 0 else None,
            args={"path": f"doc_{j}.txt"} if j % 2 == 0 else None,
            tool_ok=1,
            ts=now - (200.0 - j),
        )

    # Verify history count >= 50
    with db.read_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM decisions")
        total_seeded = cur.fetchone()[0]
    assert total_seeded >= 50, f"Expected >= 50 seeded turns, got {total_seeded}"

    # 3. Induce rule: must land exclusively in QUARANTINE (D-REAS-06)
    inducer = RuleInducer(db=db, rule_engine=rule_engine, min_frequency=3)
    quarantined_candidates = inducer.induce_and_quarantine()
    assert len(quarantined_candidates) == 1, (
        f"Expected 1 candidate induced, got {len(quarantined_candidates)}"
    )

    candidate = quarantined_candidates[0]
    rule_id = candidate.rule_id
    assert rule_id in rule_engine.rules
    managed_rule = rule_engine.rules[rule_id]
    assert managed_rule.status == "QUARANTINE"
    assert managed_rule.is_induced is True

    # 4. Dream-RSI Offline Replay: replay candidate against past 50 episodes
    replay_report = rule_engine.replay_candidate(rule_id=rule_id, limit=50)
    assert replay_report.passed is True, f"Replay failed: {replay_report.reasons}"
    assert replay_report.n_real >= 50
    assert managed_rule.replay_passed is True

    # 5. Shadow Evaluation: accumulate 5 clean shadow clusters
    test_state = RuleState(
        transcript="open calculator",
        transcript_lower="open calculator",
        intent="launch_app",
        intent_conf=0.95,
        entities={"app": ["calculator"]},
        hour_local=12,
        weekday=3,
        apps_running=frozenset(),
        last_tool=None,
        last_tool_ok=None,
        session_turns=1,
        mode="transcript",
    )
    expected_plan = Plan(
        actions=[ToolCall(tool="launch_app", args={"app": "calculator"}, call_id="call-test-1")]
    )

    for cluster_idx in range(1, 6):
        triple = rule_engine.record_shadow(
            rule_id=rule_id,
            matched=True,
            cluster_id=f"cluster-{cluster_idx}",
            state_snapshot=test_state,
            plan_snapshot=expected_plan,
        )
        assert triple is not None
        assert triple.decision.verdict == "escalated"
        assert triple.outcome.signal == "abstained"

    assert len(managed_rule.success_clusters) == 5
    assert managed_rule.failure_count == 0

    # 6. Promotion check: requires human approval -> transitions to PENDING_APPROVAL
    promo_result = rule_engine.promote_if_eligible(rule_id=rule_id)
    assert promo_result.promoted is False
    assert managed_rule.status == "PENDING_APPROVAL"

    # 7. Owner promotion via approve_rule() -> transitions to ACTIVE
    approve_result = rule_engine.approve_rule(
        rule_id=rule_id,
        approver="operator-lucca-admin",
    )
    assert approve_result.promoted is True, f"Approval failed: {approve_result.reason}"
    assert managed_rule.status == "ACTIVE"
    assert managed_rule.promoted_at is not None

    # 8. Active Execution: verify the newly ACTIVE rule executes and yields plan
    active_outcomes = rule_engine.evaluate(test_state, mode="active")
    fired_outcomes = [o for o in active_outcomes if o.fired]
    assert len(fired_outcomes) == 1
    fired = fired_outcomes[0]
    assert fired.rule_id == rule_id
    assert fired.plan is not None
    assert len(fired.plan.actions) == 1
    action = fired.plan.actions[0]
    assert isinstance(action, ToolCall)
    assert action.tool == "launch_app"
    assert action.args == {"app": "calculator"}
