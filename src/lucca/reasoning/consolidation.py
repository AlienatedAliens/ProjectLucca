"""
Project Lucca — Proactive Reflection & Macro Consolidation Loop (Module 14 / WO-34)
Spec: plans/2026-10-03_wo29_neurosymbolic_program_synthesis_and_15_module_cognitive_ladder.md §4
Spec: docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md §2 (Battery IN - Stratum IN-D)

Autonomous idle/sleep-phase background daemon that aggregates reasoning and conversation traces,
extracts recurring sub-AST patterns via DreamCoder anti-unification, validates complexity
bounds (D-REAS-05) and formal semantics (Z3 SMT + scratchpad falsification), admits verified
macros strictly into QUARANTINE mode (D-REAS-06: 0 to ACTIVE), and updates the IN-D
(Learned Competencies / Individuation) stratum scorecard.

Invariants:
- Zero-Any typing discipline strictly enforced (D-AUD-01).
- Hardware budget: ΔVRAM = 0 MB, ΔRAM <= 50 MB, execution exclusively on host CPU.
- D-REAS-05: Depth <= 8, step count <= 64.
- D-REAS-06: Exactly 0 induced rules promoted to ACTIVE without explicit operator sign-off.
- Updates and maintains logs/test_reports/personhood/in_d_latest.json.
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Final

from pydantic import BaseModel, Field
import structlog

from lucca.core.scratchpad import ScratchpadFalsifier
from lucca.evaluation.in_d_grader import INDGraderReport, grade_in_d, save_in_d_report
from lucca.reasoning.compression import DreamCoderMacroMiner, MinedMacroCandidate
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.parser import SchemeNode, Symbol, parse_expr
from lucca.reasoning.smt_verifier import SMTVerifier

logger = structlog.get_logger(__name__)


class ConsolidationConfig(BaseModel):
    """Configuration governing the proactive sleep-phase consolidation loop."""

    idle_threshold_seconds: float = 30.0
    max_traces_per_cycle: int = 50
    min_instances_for_macro: int = 2
    smt_timeout_ms: int = 500
    auto_update_in_d_scorecard: bool = True


class ConsolidationCycleResult(BaseModel):
    """Outcome report for an executed consolidation sleep cycle."""

    cycle_id: str
    traces_examined: int
    macros_mined: int
    quarantined_macro_ids: list[str] = Field(default_factory=list)
    active_macro_ids: list[str] = Field(default_factory=list)
    in_d_quarantined_count: int = 0
    in_d_active_count: int = 0
    in_d_guard_passed: bool = True
    elapsed_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)


class ConsolidationEngine:
    """
    Manages autonomous sleep-phase macro discovery, validation, and skill registration.
    """

    def __init__(
        self,
        config: ConsolidationConfig | None = None,
        lifecycle_manager: RuleLifecycleManager | None = None,
        smt_verifier: SMTVerifier | None = None,
        falsifier: ScratchpadFalsifier | None = None,
    ) -> None:
        self.config = config or ConsolidationConfig()
        self.lifecycle_manager = lifecycle_manager or RuleLifecycleManager()
        self.smt_verifier = smt_verifier or SMTVerifier(timeout_ms=self.config.smt_timeout_ms)
        self.falsifier = falsifier or ScratchpadFalsifier()
        self.compressor = DreamCoderMacroMiner(
            rule_lifecycle=self.lifecycle_manager,
            smt_verifier=self.smt_verifier,
            falsifier=self.falsifier,
        )
        self._trace_buffer: list[SchemeNode] = []
        self._cycle_counter: int = 0

    def record_trace(self, expr: SchemeNode | str) -> None:
        """Buffers an AST trace from a conversational or reasoning execution turn."""
        if isinstance(expr, str):
            try:
                parsed = parse_expr(expr)
                self._trace_buffer.append(parsed)
            except Exception as exc:  # noqa: BLE001
                logger.warning("failed_parsing_trace_for_consolidation", expr=expr, error=str(exc))
        else:
            self._trace_buffer.append(expr)

    def record_traces(self, exprs: list[SchemeNode | str]) -> None:
        """Buffers multiple AST traces."""
        for expr in exprs:
            self.record_trace(expr)

    def clear_trace_buffer(self) -> None:
        """Clears accumulated trace buffer."""
        self._trace_buffer.clear()

    @property
    def buffer_size(self) -> int:
        """Current number of pending traces in memory buffer."""
        return len(self._trace_buffer)

    def run_consolidation_cycle(self) -> ConsolidationCycleResult:
        """
        Executes a complete sleep-phase consolidation cycle:
        1. Pulls accumulated traces up to max_traces_per_cycle.
        2. Clusters traces by syntactic shape and mines recurring patterns.
        3. Enforces D-REAS-05 (complexity bounds) and D-REAS-06 (quarantine admission, 0 to ACTIVE).
        4. Mechanically grades and updates IN-D (Learned Competencies) stratum scorecard.
        """
        t0 = time.perf_counter()
        self._cycle_counter += 1
        cycle_id = f"cycle_{self._cycle_counter:04d}_{int(time.time())}"
        errors: list[str] = []

        active_traces = self._trace_buffer[: self.config.max_traces_per_cycle]
        quarantined_ids: list[str] = []
        active_ids: list[str] = []

        if len(active_traces) < self.config.min_instances_for_macro:
            elapsed = (time.perf_counter() - t0) * 1000.0
            logger.info(
                "consolidation_skipped_insufficient_traces",
                count=len(active_traces),
                min_required=self.config.min_instances_for_macro,
            )
            report = self.get_in_d_report()
            return ConsolidationCycleResult(
                cycle_id=cycle_id,
                traces_examined=len(active_traces),
                macros_mined=0,
                in_d_quarantined_count=report.learned_skills_quarantined,
                in_d_active_count=report.learned_skills_active,
                in_d_guard_passed=report.guard_active_zero_passed,
                elapsed_ms=elapsed,
            )

        # Cluster traces by outer shape
        clusters: dict[str, list[SchemeNode]] = {}
        for tr in active_traces:
            shape_key = "atom"
            if isinstance(tr, list) and tr:
                first = tr[0]
                op_name = first.name if isinstance(first, Symbol) else str(first)
                shape_key = f"{op_name}:{len(tr)}"
            clusters.setdefault(shape_key, []).append(tr)

        mined_candidates: list[MinedMacroCandidate] = []
        for cluster_idx, (shape_key, instances) in enumerate(clusters.items()):
            if len(instances) >= self.config.min_instances_for_macro:
                try:
                    macro_name = f"macro-induced-{cluster_idx + 1}"
                    cand = self.compressor.mine_candidate(
                        macro_name=macro_name,
                        instances=instances,
                    )
                    mined_candidates.append(cand)
                except Exception as exc:  # noqa: BLE001
                    logger.error("consolidation_mining_error", shape=shape_key, error=str(exc))
                    errors.append(f"Macro mining error on {shape_key}: {exc}")

        for cand in mined_candidates:
            if cand.quarantined and cand.rule_id:
                quarantined_ids.append(cand.rule_id)
            if cand.active and cand.rule_id:
                active_ids.append(cand.rule_id)

        # Enforce D-REAS-06 invariant: 0 mined macros may reach ACTIVE
        if active_ids:
            err = f"D-REAS-06 breach: {len(active_ids)} mined macros reached ACTIVE mode"
            logger.error("d_reas_06_breach_detected", active_ids=active_ids)
            errors.append(err)

        # Grade IN-D learned skill metric
        in_d_report = self.get_in_d_report()
        if self.config.auto_update_in_d_scorecard:
            try:
                save_in_d_report(in_d_report)
            except Exception as exc:  # noqa: BLE001
                logger.warning("save_in_d_report_failed", error=str(exc))
                errors.append(f"IN-D report save failed: {exc}")

        elapsed = (time.perf_counter() - t0) * 1000.0
        return ConsolidationCycleResult(
            cycle_id=cycle_id,
            traces_examined=len(active_traces),
            macros_mined=len(mined_candidates),
            quarantined_macro_ids=quarantined_ids,
            active_macro_ids=active_ids,
            in_d_quarantined_count=in_d_report.learned_skills_quarantined,
            in_d_active_count=in_d_report.learned_skills_active,
            in_d_guard_passed=in_d_report.guard_active_zero_passed and (len(active_ids) == 0),
            elapsed_ms=elapsed,
            errors=errors,
        )

    def get_in_d_report(self) -> INDGraderReport:
        """Computes current IN-D stratum report via mechanical grader."""
        return grade_in_d(lifecycle_manager=self.lifecycle_manager)
