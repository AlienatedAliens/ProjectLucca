"""
Project Lucca — Scale, Concurrency & Collision Battery (Reasoning Engine)
Spec 05, Spec 09, Spec 14, D-REAS-06, D-AUD-01
Exhaustive verification of system behavior under volume and concurrency:
1. Volume stress: 50 distinct mined macro rules admitted to QUARANTINE in SQLite.
2. Multi-threaded concurrency: 8 concurrent threads evaluating turn states in shadow mode.
3. Priority collision: deterministic resolution across competing rules matching the same turn.
4. Shadow error tracking: failure accumulation and isolation in rule_states.
5. Strict D-REAS-06 promotion guard: 0 induced rules reach ACTIVE without human operator approval.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
import pytest

from lucca.core.schemas import Risk, RuleState, ToolParameter, ToolSchema
from lucca.memory.db import DatabaseManager
from lucca.reasoning.lifecycle import ManagedRule, RuleLifecycleManager
from lucca.reasoning.scheme.parser import parse_rule


@pytest.fixture
def temp_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "scale_test.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    return db


@pytest.fixture
def mock_tools() -> dict[str, ToolSchema]:
    return {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
            target="self",
        ),
    }


def test_volume_50_mined_macros_in_quarantine(temp_db: DatabaseManager, mock_tools: dict[str, ToolSchema]) -> None:
    """
    Registers 50 candidate rules into SQLite and verifies query responsiveness
    and quarantine state preservation.
    """
    lifecycle = RuleLifecycleManager(registered_tools=mock_tools, db=temp_db)

    t0 = time.perf_counter()
    for i in range(50):
        rule_src = f"""
        (rule "mined-pattern-{i}-v1"
          :when (and (intent= "launch_app") (entity-has? "app" "app_{i}"))
          :plan (list (tool "launch_app" :app "app_{i}"))
          :priority {i % 10})
        """
        r_def = parse_rule(rule_src)
        managed = ManagedRule(
            rule_id=f"mined-pattern-{i}-v1",
            status="QUARANTINE",
            definition=r_def,
            is_induced=True,
        )
        lifecycle.rules[managed.rule_id] = managed
        lifecycle.persist(managed.rule_id)

    elapsed_insert = (time.perf_counter() - t0) * 1000.0
    assert elapsed_insert < 2000.0, f"Inserting 50 rules took too long: {elapsed_insert:.2f}ms"

    # Query SQLite directly to verify all 50 exist in QUARANTINE
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT count(*) FROM rule_states WHERE status = 'QUARANTINE'")
        count = cur.fetchone()[0]
        assert count == 50, f"Expected 50 rules in QUARANTINE, got {count}"


def test_concurrency_sqlite_multithreaded_shadow_eval(
    temp_db: DatabaseManager,
    mock_tools: dict[str, ToolSchema],
) -> None:
    """
    Simulates 8 concurrent worker threads evaluating turns and recording shadow matches
    simultaneously against SQLite without lock contention.
    """
    lifecycle = RuleLifecycleManager(registered_tools=mock_tools, db=temp_db)

    # Register 10 candidate rules
    for i in range(10):
        rule_src = f"""
        (rule "concurrent-cand-{i}-v1"
          :when (and (intent= "launch_app") (entity-has? "app" "calc"))
          :plan (list (tool "launch_app" :app "calc"))
          :priority 1)
        """
        r_def = parse_rule(rule_src)
        managed = ManagedRule(
            rule_id=f"concurrent-cand-{i}-v1",
            status="QUARANTINE",
            definition=r_def,
            is_induced=True,
        )
        lifecycle.rules[managed.rule_id] = managed
        lifecycle.persist(managed.rule_id)

    simulated_state = RuleState(
        schema_version=1,
        transcript="launch calculator",
        transcript_lower="launch calculator",
        intent="launch_app",
        intent_conf=0.95,
        entities={"app": ["calc"]},
        hour_local=12,
        weekday=2,
        apps_running=frozenset(),
        session_turns=1,
    )

    def worker_task(thread_id: int) -> int:
        fired_total = 0
        for _ in range(15):
            outcomes = lifecycle.evaluate(simulated_state, mode="shadow")
            fired_total += sum(1 for o in outcomes if o.fired)
        return fired_total

    workers = 8
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker_task, tid) for tid in range(workers)]
        results = [f.result() for f in futures]

    # Each worker did 15 evaluations where all 10 rules fired = 150 fired per worker
    for r in results:
        assert r == 150, f"Worker returned unexpected fired count: {r}"


def test_macro_priority_collision_resolution(mock_tools: dict[str, ToolSchema]) -> None:
    """
    Verifies that rules matching the exact same state are ordered strictly by priority (highest first).
    """
    lifecycle = RuleLifecycleManager(registered_tools=mock_tools)

    # Register 5 active rules with priorities 1, 2, 5, 3, 4
    priorities = [1, 2, 5, 3, 4]
    for p in priorities:
        rule_src = f"""
        (rule "priority-rule-p{p}-v1"
          :when (and (intent= "launch_app") (entity-has? "app" "calc"))
          :plan (list (say "p{p}"))
          :priority {p})
        """
        r_def = parse_rule(rule_src)
        managed = ManagedRule(
            rule_id=f"priority-rule-p{p}-v1",
            status="ACTIVE",
            definition=r_def,
        )
        lifecycle.rules[managed.rule_id] = managed

    simulated_state = RuleState(
        schema_version=1,
        transcript="launch calculator",
        transcript_lower="launch calculator",
        intent="launch_app",
        intent_conf=0.95,
        entities={"app": ["calc"]},
        hour_local=12,
        weekday=2,
        apps_running=frozenset(),
        session_turns=1,
    )

    outcomes = lifecycle.evaluate(simulated_state, mode="active")
    fired_ids = [o.rule_id for o in outcomes if o.fired]

    expected_order = [
        "priority-rule-p5-v1",
        "priority-rule-p4-v1",
        "priority-rule-p3-v1",
        "priority-rule-p2-v1",
        "priority-rule-p1-v1",
    ]
    assert fired_ids == expected_order, f"Rule priority resolution order failed: {fired_ids} != {expected_order}"


def test_consecutive_failure_shadow_tracking(
    temp_db: DatabaseManager,
    mock_tools: dict[str, ToolSchema],
) -> None:
    """
    Verifies that errored rule executions in shadow mode increment failure count
    and persist into SQLite.
    """
    lifecycle = RuleLifecycleManager(registered_tools=mock_tools, db=temp_db)

    rule_src = """
    (rule "failing-cand-v1"
      :when (intent= "launch_app")
      :plan (list (say "fail"))
      :priority 1)
    """
    r_def = parse_rule(rule_src)
    managed = ManagedRule(
        rule_id="failing-cand-v1",
        status="QUARANTINE",
        definition=r_def,
        is_induced=True,
    )
    lifecycle.rules[managed.rule_id] = managed
    lifecycle.persist(managed.rule_id)

    # Record 3 shadow errors
    for _ in range(3):
        lifecycle.record_shadow("failing-cand-v1", matched=False, errored=True)

    assert managed.failure_count == 3

    # Check persistence in SQLite
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT failure_count FROM rule_states WHERE rule_id = 'failing-cand-v1'")
        db_failures = cur.fetchone()[0]
        assert db_failures == 3, f"Expected 3 failures in DB, got {db_failures}"


def test_zero_active_promotion_guard_under_stress(
    temp_db: DatabaseManager,
    mock_tools: dict[str, ToolSchema],
) -> None:
    """
    D-REAS-06 Stress Test: 50 induced candidate rules are subjected to promotion attempts
    with various cluster counts (0 to 10).
    Invariant: Exactly 0 induced rules may be promoted to ACTIVE without human operator approval.
    """
    lifecycle = RuleLifecycleManager(registered_tools=mock_tools, db=temp_db)

    promoted_count = 0
    for i in range(50):
        rule_id = f"induced-rule-stress-{i}-v1"
        rule_src = f"""
        (rule "{rule_id}"
          :when (intent= "launch_app")
          :plan (list (say "hi"))
          :priority 1)
        """
        r_def = parse_rule(rule_src)
        managed = ManagedRule(
            rule_id=rule_id,
            status="QUARANTINE",
            definition=r_def,
            is_induced=True,
            success_clusters={f"cluster_{c}" for c in range(i % 12)},  # Clusters range from 0 to 11
        )
        lifecycle.rules[rule_id] = managed
        lifecycle.persist(rule_id)

        promo = lifecycle.promote_if_eligible(rule_id)
        if promo.promoted:
            promoted_count += 1

    assert promoted_count == 0, f"CRITICAL: {promoted_count} induced rules promoted to ACTIVE! D-REAS-06 violated!"
    # Verify in DB that status remains non-ACTIVE
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT count(*) FROM rule_states WHERE status = 'ACTIVE'")
        active_in_db = cur.fetchone()[0]
        assert active_in_db == 0, f"Expected 0 ACTIVE rules in SQLite, got {active_in_db}"
