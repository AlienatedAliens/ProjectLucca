"""
Project Lucca — Rule DSL Lifecycle State Machine & Regression Suite
Spec 05 §8, §9, ADR-007
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import structlog
import ulid
from pydantic import JsonValue

from lucca.core.capabilities import get_default_native_tools
from lucca.core.config import get_resource_path
from lucca.core.exceptions import SchemeSyntaxError
from lucca.core.schemas import (
    CandidateRule,
    Decision,
    ExecutionTriple,
    Outcome,
    Plan,
    PromotionResult,
    Proposal,
    RegressionReport,
    RuleOutcome,
    RuleState,
    Say,
    SkillMeta,
    ToolCall,
    ToolSchema,
)
from lucca.memory.db import DatabaseManager
from lucca.reasoning.replay import ReplayEngine, ReplayReport
from lucca.reasoning.scheme.eval import evaluate_rule
from lucca.reasoning.scheme.parser import RuleDefinition, parse_rule
from lucca.reasoning.scheme.validator import validate_rule_static
from lucca.reasoning.stats import mcnemar_test, wilson_score_interval

logger = structlog.get_logger(__name__)

RuleStatus = Literal["PROPOSED", "QUARANTINE", "PENDING_APPROVAL", "ACTIVE", "DEMOTED", "RETIRED"]


def get_default_tool_schemas() -> dict[str, ToolSchema]:
    """Returns baseline tool schemas for static rule validation (T1.1, §0.0 C1)."""
    return get_default_native_tools()


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
    expose_as_tool: bool = False
    categories: list[str] = field(default_factory=list)
    skill_meta: SkillMeta | None = None
    is_induced: bool = False
    replay_passed: bool = False
    replay_report: ReplayReport | None = None


def compute_cluster_id(
    session_id: str,
    turn_ts: float,
    semantic_cluster: int = 0,
) -> str:
    """
    Computes a canonical cluster identifier per Spec 05 §8.
    Distinctness requirements:
    - Same request across distinct 15-minute time buckets -> distinct clusters
    - Same session within a 15-minute bucket -> identical cluster
    - Distinct semantic clusters -> distinct clusters
    """
    time_bucket = int(math.floor(turn_ts / 900.0))
    raw = f"{session_id}:{time_bucket}:{semantic_cluster}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def plans_match(p1: Plan, p2: Plan) -> bool:
    """Checks semantic equality between two plans."""
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


def check_plan_and_core_agreement(
    rule_plan: Plan | None,
    core_tool_calls: list[ToolCall] | None = None,
    core_path: str = "LLM",
) -> bool:
    """
    Determines whether a rule's proposed plan agreed with the core execution on that turn.
    Spec 1.1.2 §6.2 (ModularRSI §3.3).
    """
    if rule_plan is None or not rule_plan.actions:
        # Rule did not propose actions or yielded to core
        if (not core_tool_calls) and core_path in ("LLM", "CLARIFY"):
            return True
        return False

    rule_actions = rule_plan.actions
    rule_tool_calls = [a for a in rule_actions if isinstance(a, ToolCall)]

    if rule_tool_calls:
        if not core_tool_calls or len(core_tool_calls) != len(rule_tool_calls):
            return False
        for rt, ct in zip(rule_tool_calls, core_tool_calls, strict=True):
            if rt.tool.lower() != ct.tool.lower():
                return False
            if rt.args != ct.args:
                return False
        return True

    rule_says = [a for a in rule_actions if isinstance(a, Say)]
    if rule_says and not rule_tool_calls:
        if (not core_tool_calls) and core_path in ("LLM", "CLARIFY"):
            return True
        return False

    return False


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
        skills_dir: Path | str | None = None,
    ) -> None:
        self.registered_tools = (
            registered_tools if registered_tools is not None else get_default_tool_schemas()
        )
        self.db = db
        self.require_human_approval = require_human_approval
        self.skills_dir = Path(skills_dir) if skills_dir is not None else None
        self.rules: dict[str, ManagedRule] = {}
        self.regression_cases: list[RegressionCase] = []
        self.latest_triples: list[ExecutionTriple] = []
        if self.db is not None:
            self.load()
        if self.skills_dir is not None:
            self.load_skills(self.skills_dir)

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
        managed.is_induced = True
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

    def emit_shadow_triple(
        self,
        rule_id: str,
        plan: Plan | list[ToolCall | Say] | None = None,
        state_snapshot: RuleState | None = None,
        evidence_refs: list[str] | None = None,
    ) -> ExecutionTriple:
        """Emits an S1 execution triple for shadow evaluation per Spec §5 and S1.3."""
        if plan is None:
            actions: list[ToolCall | Say] = []
        elif isinstance(plan, Plan):
            actions = plan.actions
        else:
            actions = list(plan)

        refs = list(evidence_refs or [])
        if not refs and state_snapshot and state_snapshot.transcript:
            refs = [state_snapshot.transcript]

        proposal = Proposal(
            rule_id=rule_id,
            plan=actions,
            confidence=1.0,
            gas_estimate=0,
            evidence_refs=refs,
        )
        decision = Decision(
            proposal_id=proposal.proposal_id,
            verdict="escalated",
            reason_code="SHADOW_EVAL",
        )
        outcome = Outcome(
            decision_id=decision.decision_id,
            signal="abstained",
            detail="shadow evaluation, not executed",
        )
        triple = ExecutionTriple(
            proposal=proposal,
            decision=decision,
            outcome=outcome,
        )
        self.latest_triples.append(triple)
        if self.db is not None:
            self.db.record_execution_triple(triple)
        return triple

    def emit_execution_triple(
        self,
        rule_id: str,
        plan: Plan | list[ToolCall | Say],
        verdict: Literal["accepted", "overridden", "escalated"] = "accepted",
        reason_code: str = "ACTIVE_EXECUTION",
        signal: Literal[
            "tool_exit_zero",
            "pydantic_valid",
            "operator_confirm",
            "operator_correct",
            "abstained",
        ] = "tool_exit_zero",
        detail: str = "",
        evidence_refs: list[str] | None = None,
    ) -> ExecutionTriple:
        """Emits an S1 execution triple for active executions per Spec §5 and S1.3."""
        actions = plan.actions if isinstance(plan, Plan) else list(plan)
        proposal = Proposal(
            rule_id=rule_id,
            plan=actions,
            confidence=1.0,
            gas_estimate=0,
            evidence_refs=list(evidence_refs or []),
        )
        decision = Decision(
            proposal_id=proposal.proposal_id,
            verdict=verdict,
            reason_code=reason_code,
        )
        outcome = Outcome(
            decision_id=decision.decision_id,
            signal=signal,
            detail=detail,
        )
        triple = ExecutionTriple(
            proposal=proposal,
            decision=decision,
            outcome=outcome,
        )
        self.latest_triples.append(triple)
        if self.db is not None:
            self.db.record_execution_triple(triple)
        return triple

    def record_shadow(
        self,
        rule_id: str,
        matched: bool = False,
        cluster_id: str = "",
        indeterminate: bool = False,
        state_snapshot: RuleState | None = None,
        plan_snapshot: Plan | None = None,
        errored: bool = False,
        evidence_refs: list[str] | None = None,
    ) -> ExecutionTriple | None:
        """
        Records shadow execution outcome per Spec 05 §6 & §9 and S1.3.
        Barge-in / cancel -> indeterminate=True (ignored).
        """
        if indeterminate or rule_id not in self.rules:
            return None

        if errored:
            matched = False

        rule = self.rules[rule_id]
        triple: ExecutionTriple | None = None

        if rule.status == "QUARANTINE":
            if matched:
                rule.success_clusters.add(cluster_id)
                if state_snapshot and plan_snapshot:
                    rule.snapshots.append((state_snapshot, plan_snapshot))
                triple = self.emit_shadow_triple(
                    rule_id=rule_id,
                    plan=plan_snapshot,
                    state_snapshot=state_snapshot,
                    evidence_refs=evidence_refs,
                )
            else:
                rule.failure_count += 1
                if rule.failure_count >= 3:
                    rule.status = "RETIRED"
                    rule.retired_at = time.time()
                if errored:
                    triple = self.emit_shadow_triple(
                        rule_id=rule_id,
                        plan=plan_snapshot,
                        state_snapshot=state_snapshot,
                        evidence_refs=evidence_refs,
                    )

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

        return triple

    def user_retire(self, rule_id: str) -> None:
        """User explicitly retired this rule (e.g. 'stop doing X')."""
        if rule_id in self.rules:
            rule = self.rules[rule_id]
            rule.status = "RETIRED"
            rule.user_retired = True
            rule.retired_at = time.time()
            if rule.skill_meta is not None:
                rule.skill_meta = rule.skill_meta.model_copy(update={"status": "RETIRED"})
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

    def replay_candidate(self, rule_id: str, limit: int = 50) -> ReplayReport:
        """
        Evaluates a candidate rule offline against recorded episodes from SQLite decisions table.
        Enforces Dream-RSI: N_real >= min_episodes (50) and 0 errors/misfires.
        Spec 1.1.2 §6.2 (Rung L2).
        """
        if rule_id not in self.rules:
            return ReplayReport(
                evaluated_rule_id=rule_id,
                passed=False,
                n_real=0,
                min_required=limit,
                reasons=[f"Rule '{rule_id}' is not registered"],
            )

        rule = self.rules[rule_id]
        engine = ReplayEngine(min_episodes=limit)
        if self.db is None:
            rep = ReplayReport(
                evaluated_rule_id=rule_id,
                passed=False,
                n_real=0,
                min_required=limit,
                reasons=["No database configured for Dream-RSI replay"],
            )
            rule.replay_passed = False
            rule.replay_report = rep
            return rep

        episodes = engine.load_past_episodes(self.db, limit=limit)
        report = engine.replay_candidate_rule(rule.definition, episodes)
        rule.replay_passed = report.passed
        rule.replay_report = report
        return report

    def log_contrastive_shadow_pair(
        self,
        rule_id: str,
        trace_id: str,
        rule_plan: Plan | None,
        core_tool_calls: list[ToolCall] | None,
        core_path: str = "LLM",
        rule_outcome_signal: str | None = None,
        core_outcome_signal: str | None = None,
        ts: float | None = None,
    ) -> None:
        """Records paired contrastive shadow evaluation log to SQLite per Spec §6.2."""
        if self.db is None:
            return
        agreed = check_plan_and_core_agreement(
            rule_plan=rule_plan,
            core_tool_calls=core_tool_calls,
            core_path=core_path,
        )
        rule_plan_json = json.dumps(rule_plan.model_dump(mode="json")) if rule_plan else "{}"
        core_action_data = {
            "path": core_path,
            "tool_calls": [tc.model_dump(mode="json") for tc in (core_tool_calls or [])],
        }
        core_action_json = json.dumps(core_action_data)
        log_id = str(ulid.ULID())
        self.db.record_contrastive_shadow_log(
            log_id=log_id,
            rule_id=rule_id,
            trace_id=trace_id,
            ts=ts if ts is not None else time.time(),
            rule_plan_json=rule_plan_json,
            core_action_json=core_action_json,
            agreed=agreed,
            rule_outcome_signal=rule_outcome_signal,
            core_outcome_signal=core_outcome_signal,
        )

    def get_contrastive_summary(self, rule_id: str, limit: int = 100) -> dict[str, JsonValue]:
        """
        Computes contrastive summary statistics for a rule per Spec 1.1.2 §5, §6.2.
        Calculates Wilson 95% score intervals on agreement and reliability rates,
        paired McNemar test discordance, and explicit S1 semantics labeling.
        """
        empty_res: dict[str, JsonValue] = {
            "rule_id": rule_id,
            "total_turns": 0,
            "agreed_count": 0,
            "agreed_rate": 0.0,
            "agreed_interval": [0.0, 1.0],
            "b_rule_better": 0,
            "c_core_better": 0,
            "mcnemar_p_value": 1.0,
            "mcnemar_significant": False,
            "rule_reliability_rate": 0.0,
            "rule_reliability_interval": [0.0, 1.0],
            "core_reliability_rate": 0.0,
            "core_reliability_interval": [0.0, 1.0],
            "rate_label": "Execution-Reliability Rate (S1)",
            "records": [],
        }
        if self.db is None:
            return empty_res

        records = self.db.list_contrastive_shadow_logs(rule_id=rule_id, limit=limit)
        total_turns = len(records)
        if total_turns == 0:
            return empty_res

        agreed_count = sum(1 for r in records if bool(r.get("agreed", False)))
        agreed_rate = float(agreed_count) / float(total_turns)
        ag_lb, ag_ub = wilson_score_interval(agreed_count, total_turns)

        b = 0
        c = 0
        rule_ok_count = 0
        core_ok_count = 0

        for rec in records:
            r_sig = str(rec.get("rule_outcome_signal") or "")
            c_sig = str(rec.get("core_outcome_signal") or "")

            r_ok = r_sig in ("tool_exit_zero", "pydantic_valid", "operator_confirm", "abstained")
            c_ok = c_sig in ("tool_exit_zero", "pydantic_valid", "operator_confirm")

            r_bad = r_sig in ("error", "gas_exhausted", "pydantic_invalid")
            c_bad = c_sig in ("operator_correct", "error", "tool_exit_nonzero", "pydantic_invalid")

            if r_ok:
                rule_ok_count += 1
            if c_ok:
                core_ok_count += 1

            if r_ok and c_bad:
                b += 1
            elif c_ok and r_bad:
                c += 1

        p_val = mcnemar_test(b, c)
        sig = p_val < 0.05 and (b + c) >= 10

        r_rel = float(rule_ok_count) / float(total_turns)
        r_lb, r_ub = wilson_score_interval(rule_ok_count, total_turns)

        c_rel = float(core_ok_count) / float(total_turns)
        c_lb, c_ub = wilson_score_interval(core_ok_count, total_turns)

        return {
            "rule_id": rule_id,
            "total_turns": total_turns,
            "agreed_count": agreed_count,
            "agreed_rate": agreed_rate,
            "agreed_interval": [ag_lb, ag_ub],
            "b_rule_better": b,
            "c_core_better": c,
            "mcnemar_p_value": p_val,
            "mcnemar_significant": sig,
            "rule_reliability_rate": r_rel,
            "rule_reliability_interval": [r_lb, r_ub],
            "core_reliability_rate": c_rel,
            "core_reliability_interval": [c_lb, c_ub],
            "rate_label": "Execution-Reliability Rate (S1)",
            "records": records[:20],
        }

    def promote_if_eligible(self, rule_id: str, require_replay: bool = False) -> PromotionResult:
        if rule_id not in self.rules:
            return PromotionResult(promoted=False, rule_id=rule_id, reason="Rule not registered")

        rule = self.rules[rule_id]
        if rule.status != "QUARANTINE":
            return PromotionResult(
                promoted=False,
                rule_id=rule_id,
                reason=f"Rule is in state {rule.status}, must be QUARANTINE",
            )

        if (rule.is_induced or require_replay) and not rule.replay_passed:
            report = self.replay_candidate(rule_id, limit=50)
            if not report.passed:
                return PromotionResult(
                    promoted=False,
                    rule_id=rule_id,
                    reason=f"Dream-RSI offline replay failed: {'; '.join(report.reasons)}",
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

    def approve_rule(
        self, rule_id: str, approver: str = "human", require_replay: bool = False
    ) -> PromotionResult:
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

        if (rule.is_induced or require_replay) and not rule.replay_passed:
            report = self.replay_candidate(rule_id, limit=50)
            if not report.passed:
                return PromotionResult(
                    promoted=False,
                    rule_id=rule_id,
                    reason=f"Dream-RSI offline replay failed: {'; '.join(report.reasons)}",
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

    def load_skills(self, skills_dir: Path | str | None = None) -> int:
        """
        Loads ACTIVE skills from config/skills/ (excluding _retired/)
        per Spec 1.1.2 §3, L1a.3.
        """
        target_dir: Path | None = None
        if skills_dir is not None:
            target_dir = Path(skills_dir)
        else:
            try:
                target_dir = get_resource_path("config/skills")
            except Exception:  # noqa: BLE001
                target_dir = Path("config/skills")

        if target_dir is None or not target_dir.exists() or not target_dir.is_dir():
            return 0

        count = 0
        for child in sorted(target_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_") or child.name.startswith("."):
                continue
            meta_file = child / "meta_info.json"
            plan_file = child / "plan.scm"
            if not meta_file.exists() or not plan_file.exists():
                continue
            try:
                meta = SkillMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                if meta.status != "ACTIVE":
                    continue
                plan_src = plan_file.read_text(encoding="utf-8")
                rule_def = parse_rule(plan_src)
                existing = self.rules.get(meta.id)
                if existing is not None:
                    existing.status = "ACTIVE"
                    existing.definition = rule_def
                    existing.expose_as_tool = meta.expose_as_tool
                    existing.categories = list(meta.categories)
                    existing.skill_meta = meta
                else:
                    managed = ManagedRule(
                        rule_id=meta.id,
                        status="ACTIVE",
                        definition=rule_def,
                        expose_as_tool=meta.expose_as_tool,
                        categories=list(meta.categories),
                        skill_meta=meta,
                    )
                    self.rules[meta.id] = managed
                count += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("failed_to_load_skill", skill_dir=str(child), error=str(e))
        return count

    def get_active_skill_metas(self) -> list[SkillMeta]:
        """Returns SkillMeta for all ACTIVE rules per Spec 1.1.2 §3, L1a.3."""
        metas: list[SkillMeta] = []
        for r in self.rules.values():
            if r.status == "ACTIVE":
                if r.skill_meta is not None:
                    metas.append(r.skill_meta)
                else:
                    metas.append(
                        SkillMeta(
                            id=r.rule_id,
                            intent=r.definition.rule_id,
                            status="ACTIVE",
                            categories=r.categories,
                            expose_as_tool=r.expose_as_tool,
                        )
                    )
        return metas
