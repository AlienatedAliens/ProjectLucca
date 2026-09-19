"""
Project Lucca — Rule DSL Lifecycle State Machine & Regression Suite
Spec 05 §8, §9, ADR-007
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Literal

import structlog

from lucca.core.exceptions import SchemeSyntaxError
from lucca.core.schemas import (
    CandidateRule,
    Plan,
    PromotionResult,
    RegressionReport,
    RuleOutcome,
    RuleState,
    Say,
    ToolCall,
    ToolSchema,
)
from lucca.memory.db import DatabaseManager
from lucca.reasoning.scheme.eval import evaluate_rule
from lucca.reasoning.scheme.parser import RuleDefinition, parse_rule
from lucca.reasoning.scheme.validator import validate_rule_static

logger = structlog.get_logger(__name__)

RuleStatus = Literal["PROPOSED", "QUARANTINE", "PENDING_APPROVAL", "ACTIVE", "DEMOTED", "RETIRED"]


@dataclass
class RegressionCase:
    case_id: str
    rule_id: str
    state: RuleState
    expected_plan: Plan
    captured_at: float
    stale: bool = False


@dataclass
class ManagedRule:
    rule_id: str
    status: RuleStatus
    definition: RuleDefinition
    success_clusters: set[str] = field(default_factory=set)
    snapshots: list[tuple[RuleState, Plan]] = field(default_factory=list)
    failure_count: int = 0
    demotion_count: int = 0
    created_at: float = field(default_factory=time.time)
    promoted_at: float | None = None
    demoted_at: float | None = None
    retired_at: float | None = None
    user_retired: bool = False


def compute_cluster_id(session_id: str, turn_ts: float, semantic_cluster: int = 0) -> str:
    """
    Computes deterministic cluster ID per Spec 05 §8:
    sha1(f"{session_id}|{floor(turn_ts / 900)}|{semantic_cluster}")
    900s = 15 minute buckets.
    """
    bucket = math.floor(turn_ts / 900)
    raw = f"{session_id}|{bucket}|{semantic_cluster}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def plans_match(p1: Plan | None, p2: Plan | None) -> bool:
    """Canonical plan equality per Spec 05 §6: ignores ephemeral call_id."""
    if p1 is None or p2 is None:
        return p1 is p2
    if len(p1.actions) != len(p2.actions):
        return False
    for a1, a2 in zip(p1.actions, p2.actions, strict=True):
        if type(a1) is not type(a2):
            return False
        if isinstance(a1, ToolCall) and isinstance(a2, ToolCall):
            if a1.tool.lower() != a2.tool.lower():
                return False
            if a1.args != a2.args:
                return False
        elif isinstance(a1, Say) and isinstance(a2, Say):
            if a1.text != a2.text:
                return False
    return True


class RuleLifecycleManager:
    """
    State machine enforcing the strict promotion invariants of Spec 05 §9:
    QUARANTINE requires >= 5 distinct clusters, 0 failures, and 100% regression suite pass.
    """

    def __init__(
        self,
        registered_tools: dict[str, ToolSchema] | None = None,
        db: DatabaseManager | None = None,
        require_human_approval: bool = True,
    ) -> None:
        self.registered_tools = registered_tools or {}
        self.db = db
        self.require_human_approval = require_human_approval
        self.rules: dict[str, ManagedRule] = {}
        self.regression_cases: list[RegressionCase] = []
        if self.db is not None:
            self.load()

    def register_rule(self, source: str) -> ManagedRule:
        """
        Validates rule statically. If valid, transitions PROPOSED -> QUARANTINE.
        """
        rule_def = validate_rule_static(
            source,
            registered_tools=self.registered_tools,
            existing_rule_ids=set(self.rules.keys()),
        )
        managed = ManagedRule(
            rule_id=rule_def.rule_id,
            status="QUARANTINE",
            definition=rule_def,
        )
        self.rules[rule_def.rule_id] = managed
        if self.db is not None:
            self.persist(rule_def.rule_id)
        return managed

    def register_candidate(self, cand: CandidateRule) -> str:
        """Implements RuleEnginePort.register_candidate."""
        managed = self.register_rule(cand.s_expression)
        return managed.rule_id

    def evaluate(self, state: RuleState, *, mode: Literal["shadow", "active"]) -> list[RuleOutcome]:
        """
        Evaluates registered rules per Spec 02 & Spec 05 §6/§8.
        - shadow mode: evaluates QUARANTINE rules and records clusters to success_clusters.
        - active mode: evaluates ACTIVE rules ranked by priority descending.
        """
        outcomes: list[RuleOutcome] = []
        if mode == "shadow":
            quarantine_rules = [r for r in self.rules.values() if r.status == "QUARANTINE"]
            for r in quarantine_rules:
                outcome = evaluate_rule(r.definition, state)
                outcomes.append(outcome)
                cluster_id = compute_cluster_id(
                    session_id=state.transcript or "turn",
                    turn_ts=time.time(),
                    semantic_cluster=0,
                )
                if outcome.fired and not outcome.errored:
                    self.record_shadow(
                        r.rule_id,
                        matched=True,
                        cluster_id=cluster_id,
                        state_snapshot=state,
                        plan_snapshot=outcome.plan,
                    )
                elif outcome.errored:
                    self.record_shadow(
                        r.rule_id,
                        matched=False,
                        cluster_id=cluster_id,
                        errored=True,
                    )
        elif mode == "active":
            active_rules = sorted(
                [r for r in self.rules.values() if r.status == "ACTIVE"],
                key=lambda r: r.definition.priority,
                reverse=True,
            )
            for r in active_rules:
                outcome = evaluate_rule(r.definition, state)
                outcomes.append(outcome)

        return outcomes

    def record_shadow(
        self,
        rule_id: str,
        matched: bool = False,
        cluster_id: str = "",
        indeterminate: bool = False,
        state_snapshot: RuleState | None = None,
        plan_snapshot: Plan | None = None,
        errored: bool = False,
    ) -> None:
        """
        Records shadow execution outcome per Spec 05 §6 & §9.
        Barge-in / cancel -> indeterminate=True (ignored).
        """
        if indeterminate or rule_id not in self.rules:
            return

        if errored:
            matched = False

        rule = self.rules[rule_id]

        if rule.status == "QUARANTINE":
            if matched:
                rule.success_clusters.add(cluster_id)
                if state_snapshot and plan_snapshot:
                    rule.snapshots.append((state_snapshot, plan_snapshot))
            else:
                rule.failure_count += 1
                if rule.failure_count >= 3:
                    rule.status = "RETIRED"
                    rule.retired_at = time.time()

        elif rule.status == "ACTIVE":
            if not matched:
                # Active failure -> demotion
                rule.demotion_count += 1
                rule.demoted_at = time.time()
                if rule.demotion_count >= 2:
                    rule.status = "RETIRED"
                    rule.retired_at = time.time()
                else:
                    # Reset counters and demote to QUARANTINE
                    rule.success_clusters.clear()
                    rule.failure_count = 0
                    rule.snapshots.clear()
                    rule.status = "QUARANTINE"

        if self.db is not None:
            self.persist(rule_id)

    def user_retire(self, rule_id: str) -> None:
        """User explicitly retired this rule (e.g. 'stop doing X')."""
        if rule_id in self.rules:
            rule = self.rules[rule_id]
            rule.status = "RETIRED"
            rule.user_retired = True
            rule.retired_at = time.time()
            if self.db is not None:
                self.persist(rule_id)

    def verify_regression_suite(self, candidate_rule_id: str | None = None) -> RegressionReport:
        """
        Evaluates active rules against all stored regression cases per Spec 05 §9.
        Case passes if owning rule reproduces its plan and no other rule fires on it.
        """
        failures: list[str] = []
        cases_run = 0

        active_rules = [r for r in self.rules.values() if r.status == "ACTIVE"]
        if candidate_rule_id and candidate_rule_id in self.rules:
            cand = self.rules[candidate_rule_id]
            if cand not in active_rules:
                active_rules.append(cand)

        for case in self.regression_cases:
            if case.stale:
                continue
            cases_run += 1

            # 1. Owning rule reproduction check
            if case.rule_id in self.rules:
                owner = self.rules[case.rule_id]
                outcome = evaluate_rule(owner.definition, case.state)
                if not outcome.fired or not plans_match(outcome.plan, case.expected_plan):
                    failures.append(
                        f"Case {case.case_id}: Owning rule '{case.rule_id}' "
                        "failed to reproduce plan"
                    )

            # 2. Conflict introduction check (no other active rule should newly fire)
            for r in active_rules:
                if r.rule_id != case.rule_id:
                    outcome = evaluate_rule(r.definition, case.state)
                    if outcome.fired:
                        failures.append(
                            f"Case {case.case_id}: Conflicting rule '{r.rule_id}' "
                            "unexpectedly fired"
                        )

        passed = len(failures) == 0
        return RegressionReport(
            passed=passed,
            cases_evaluated=cases_run,
            failures=failures,
        )

    def promote_if_eligible(self, rule_id: str) -> PromotionResult:
        if rule_id not in self.rules:
            return PromotionResult(promoted=False, rule_id=rule_id, reason="Rule not registered")

        rule = self.rules[rule_id]
        if rule.status != "QUARANTINE":
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Rule is in state {rule.status}, must be QUARANTINE",
            )

        if len(rule.success_clusters) < 5:
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Insufficient distinct success clusters: {len(rule.success_clusters)} < 5",
            )

        if rule.failure_count > 0:
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Quarantine failures must be 0, got {rule.failure_count}",
            )

        # Run regression suite
        report = self.verify_regression_suite(candidate_rule_id=rule_id)
        if not report.passed:
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Regression suite failed: {report.failures}",
            )

        # Promotion criteria satisfied
        if self.require_human_approval:
            rule.status = "PENDING_APPROVAL"
            if self.db is not None:
                self.persist(rule_id)
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=(
                    "Met quarantine criteria (>=5 distinct clusters, 0 failures, "
                    "regression clean); transitioned to PENDING_APPROVAL awaiting human approval"
                ),
            )

        # Autonomous promotion criteria satisfied: promote to ACTIVE
        rule.status = "ACTIVE"
        rule.promoted_at = time.time()

        # Capture regression cases from snapshots
        existing_case_ids = {c.case_id for c in self.regression_cases}
        for idx, (state, plan) in enumerate(rule.snapshots):
            cid = f"{rule_id}-case-{idx + 1}"
            if cid not in existing_case_ids:
                case = RegressionCase(
                    case_id=cid,
                    rule_id=rule_id,
                    state=state,
                    expected_plan=plan,
                    captured_at=time.time(),
                )
                self.regression_cases.append(case)

        if self.db is not None:
            self.persist(rule_id)

        return PromotionResult(
            promoted=True,
            rule_id=rule_id,
            reason=(
                "Met all promotion criteria: >=5 distinct clusters, "
                "0 failures, regression suite clean"
            ),
        )

    def approve_rule(self, rule_id: str, approver: str = "human") -> PromotionResult:
        """
        Explicit human-in-the-loop promotion gate.
        Validates criteria and transitions a PENDING_APPROVAL or QUARANTINE rule to ACTIVE.
        """
        if rule_id not in self.rules:
            return PromotionResult(promoted=False, rule_id=rule_id, reason="Rule not registered")

        rule = self.rules[rule_id]
        if rule.status not in ("PENDING_APPROVAL", "QUARANTINE"):
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Rule is in state {rule.status}, must be PENDING_APPROVAL or QUARANTINE",
            )

        if len(rule.success_clusters) < 5:
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Insufficient distinct success clusters: {len(rule.success_clusters)} < 5",
            )

        if rule.failure_count > 0:
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Quarantine failures must be 0, got {rule.failure_count}",
            )

        report = self.verify_regression_suite(candidate_rule_id=rule_id)
        if not report.passed:
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Regression suite failed: {report.failures}",
            )

        rule.status = "ACTIVE"
        rule.promoted_at = time.time()
        logger.info(
            "Rule promoted to ACTIVE via human approval",
            rule_id=rule_id,
            approver=approver,
        )

        existing_case_ids = {c.case_id for c in self.regression_cases}
        for idx, (state, plan) in enumerate(rule.snapshots):
            cid = f"{rule_id}-case-{idx + 1}"
            if cid not in existing_case_ids:
                case = RegressionCase(
                    case_id=cid,
                    rule_id=rule_id,
                    state=state,
                    expected_plan=plan,
                    captured_at=time.time(),
                )
                self.regression_cases.append(case)

        if self.db is not None:
            self.persist(rule_id)

        return PromotionResult(
            promoted=True,
            rule_id=rule_id,
            reason=f"Approved by {approver} and promoted to ACTIVE",
        )

    def load(self, db: DatabaseManager | None = None) -> None:
        """Loads rules and regression cases from SQLite (Spec 05 §9, F-REAS-002)."""
        if db is not None:
            self.db = db
        if self.db is None:
            return

        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT
                    rule_id, status, source_canonical, source_hash,
                    success_clusters_json, snapshots_json, failure_count,
                    demotion_count, created_at, promoted_at, demoted_at,
                    retired_at, user_retired
                FROM rule_states
                """
            )
            for row in cur.fetchall():
                rule_id = str(row[0])
                status_raw = str(row[1])
                status: RuleStatus = "QUARANTINE"
                if status_raw == "ACTIVE":
                    status = "ACTIVE"
                elif status_raw == "PENDING_APPROVAL":
                    status = "PENDING_APPROVAL"
                elif status_raw == "PROPOSED":
                    status = "PROPOSED"
                elif status_raw == "DEMOTED":
                    status = "DEMOTED"
                elif status_raw == "RETIRED":
                    status = "RETIRED"
                source_canonical = str(row[2])
                clusters_list: list[str] = json.loads(row[4])
                success_clusters = set(clusters_list)
                snapshots_raw = json.loads(row[5]) if row[5] else []
                snapshots: list[tuple[RuleState, Plan]] = [
                    (RuleState.model_validate(s), Plan.model_validate(p)) for s, p in snapshots_raw
                ]
                failure_count = int(row[6])
                demotion_count = int(row[7])
                created_at = float(row[8])
                promoted_at = float(row[9]) if row[9] is not None else None
                demoted_at = float(row[10]) if row[10] is not None else None
                retired_at = float(row[11]) if row[11] is not None else None
                user_retired = bool(row[12])

                try:
                    rule_def = parse_rule(source_canonical)
                except (SchemeSyntaxError, ValueError):  # noqa: S112
                    continue

                managed = ManagedRule(
                    rule_id=rule_id,
                    status=status,
                    definition=rule_def,
                    success_clusters=success_clusters,
                    snapshots=snapshots,
                    failure_count=failure_count,
                    demotion_count=demotion_count,
                    created_at=created_at,
                    promoted_at=promoted_at,
                    demoted_at=demoted_at,
                    retired_at=retired_at,
                    user_retired=user_retired,
                )
                self.rules[rule_id] = managed

            cur.execute(
                """
                SELECT case_id, rule_id, state_json, expected_plan_json, captured_at, stale
                FROM regression_cases
                """
            )
            self.regression_cases.clear()
            for row in cur.fetchall():
                case_id = str(row[0])
                case_rule_id = str(row[1])
                state = RuleState.model_validate(json.loads(row[2]))
                expected_plan = Plan.model_validate(json.loads(row[3]))
                captured_at = float(row[4])
                stale = bool(row[5])
                case = RegressionCase(
                    case_id=case_id,
                    rule_id=case_rule_id,
                    state=state,
                    expected_plan=expected_plan,
                    captured_at=captured_at,
                    stale=stale,
                )
                self.regression_cases.append(case)

    def persist(self, rule_id: str) -> None:
        """Persists a rule and its regression cases to SQLite (Spec 05 §9, F-REAS-002)."""
        if self.db is None or rule_id not in self.rules:
            return

        rule = self.rules[rule_id]
        writer = self.db.get_writer()
        snapshots_json = json.dumps(
            [[s.model_dump(mode="json"), p.model_dump(mode="json")] for s, p in rule.snapshots]
        )
        clusters_json = json.dumps(sorted(list(rule.success_clusters)))

        try:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                """
                INSERT INTO rule_states (
                    rule_id, status, source_canonical, source_hash,
                    success_clusters_json, snapshots_json, failure_count,
                    demotion_count, created_at, promoted_at, demoted_at,
                    retired_at, user_retired
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    status=excluded.status,
                    success_clusters_json=excluded.success_clusters_json,
                    snapshots_json=excluded.snapshots_json,
                    failure_count=excluded.failure_count,
                    demotion_count=excluded.demotion_count,
                    promoted_at=excluded.promoted_at,
                    demoted_at=excluded.demoted_at,
                    retired_at=excluded.retired_at,
                    user_retired=excluded.user_retired
                """,
                (
                    rule.rule_id,
                    rule.status,
                    rule.definition.source_canonical,
                    rule.definition.source_hash,
                    clusters_json,
                    snapshots_json,
                    rule.failure_count,
                    rule.demotion_count,
                    rule.created_at,
                    rule.promoted_at,
                    rule.demoted_at,
                    rule.retired_at,
                    1 if rule.user_retired else 0,
                ),
            )

            cases_for_rule = [c for c in self.regression_cases if c.rule_id == rule_id]
            for c in cases_for_rule:
                writer.execute(
                    """
                    INSERT INTO regression_cases (
                        case_id, rule_id, state_json, expected_plan_json, captured_at, stale
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(case_id) DO UPDATE SET
                        state_json=excluded.state_json,
                        expected_plan_json=excluded.expected_plan_json,
                        stale=excluded.stale
                    """,
                    (
                        c.case_id,
                        c.rule_id,
                        json.dumps(c.state.model_dump(mode="json")),
                        json.dumps(c.expected_plan.model_dump(mode="json")),
                        c.captured_at,
                        1 if c.stale else 0,
                    ),
                )

            writer.execute("COMMIT")
        except Exception:
            writer.execute("ROLLBACK")
            raise
