"""
Project Lucca — Rule DSL Lifecycle State Machine & Regression Suite
Spec 05 §8, §9, ADR-007
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Literal

from lucca.core.schemas import (
    Plan,
    PromotionResult,
    RegressionReport,
    RuleState,
    Say,
    ToolCall,
    ToolSchema,
)
from lucca.reasoning.scheme.eval import evaluate_rule
from lucca.reasoning.scheme.parser import RuleDefinition
from lucca.reasoning.scheme.validator import validate_rule_static

RuleStatus = Literal["PROPOSED", "QUARANTINE", "ACTIVE", "DEMOTED", "RETIRED"]


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

    def __init__(self, registered_tools: dict[str, ToolSchema] | None = None) -> None:
        self.registered_tools = registered_tools or {}
        self.rules: dict[str, ManagedRule] = {}
        self.regression_cases: list[RegressionCase] = []

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
        return managed

    def record_shadow(
        self,
        rule_id: str,
        matched: bool,
        cluster_id: str,
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

    def user_retire(self, rule_id: str) -> None:
        """User explicitly retired this rule (e.g. 'stop doing X')."""
        if rule_id in self.rules:
            rule = self.rules[rule_id]
            rule.status = "RETIRED"
            rule.user_retired = True
            rule.retired_at = time.time()

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

        # Promotion criteria satisfied: promote to ACTIVE
        rule.status = "ACTIVE"
        rule.promoted_at = time.time()

        # Capture regression cases from snapshots
        for idx, (state, plan) in enumerate(rule.snapshots):
            case = RegressionCase(
                case_id=f"{rule_id}-case-{idx + 1}",
                rule_id=rule_id,
                state=state,
                expected_plan=plan,
                captured_at=time.time(),
            )
            self.regression_cases.append(case)

        return PromotionResult(
            promoted=True,
            rule_id=rule_id,
            reason=(
                "Met all promotion criteria: >=5 distinct clusters, "
                "0 failures, regression suite clean"
            ),
        )
