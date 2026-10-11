"""
Project Lucca — DreamCoder Macro Miner & Structural Compression (Module 14, WO-30)
Spec 05 Proposal D/E, D-REAS-05, D-REAS-06, D-REAS-07

Discovers recurring sub-AST patterns across execution traces, synthesizes
parameter-abstracted MicroScheme macros via first-order anti-unification,
evaluates Minimum Description Length (MDL) compression savings, enforces
bounded complexity limits (depth <= 8, steps <= 64), validates via dynamic
WSL2 Docker scratchpad falsification (>= 3 test cases), proves formal
correctness via Z3 SMT, and emits verified candidates strictly into QUARANTINE.
"""

from __future__ import annotations

import copy
import re
import time
from typing import Final

from pydantic import BaseModel, Field
import structlog

from lucca.core.schemas import CandidateRule, ToolSchema
from lucca.core.scratchpad import MacroTestCase, ScratchpadFalsifier
from lucca.reasoning.cost import (
    ast_cost,
    ast_depth,
    compute_compression_savings,
    compute_description_length,
)
from lucca.reasoning.egraph import (
    anti_unify_many,
    extract_parameters,
    match_template,
)
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.macros import (
    MAX_MACRO_DEPTH,
    MAX_MACRO_STEPS,
    MacroDefinition,
    MacroExpander,
    MacroRegistry,
)
from lucca.reasoning.scheme.parser import (
    STATE_PREDICATES,
    SchemeAtom,
    SchemeNode,
    Symbol,
    parse_expr,
    to_canonical,
)
from lucca.reasoning.smt_verifier import SMTVerifier

logger = structlog.get_logger(__name__)

MIN_INSTANCES_FOR_MINING: Final[int] = 2
ARITHMETIC_OPS: Final[frozenset[str]] = frozenset({"+", "-", "*", "/", "<", ">", "<=", ">="})


def _is_arithmetic_tree(node: SchemeNode) -> bool:
    """Checks if AST predominantly involves numeric/arithmetic operations."""
    if isinstance(node, list):
        if node and isinstance(node[0], Symbol) and node[0].name in ARITHMETIC_OPS:
            return True
        return any(_is_arithmetic_tree(child) for child in node)
    return False


def _collect_symbols(node: SchemeNode) -> set[str]:
    """Collects all symbol names appearing anywhere in an AST."""
    syms: set[str] = set()
    if isinstance(node, Symbol):
        syms.add(node.name)
    elif isinstance(node, list):
        for child in node:
            syms.update(_collect_symbols(child))
    return syms


class MinedMacroCandidate(BaseModel):
    """Represents an extracted macro candidate and its evaluation lifecycle."""

    name: str
    params: list[str]
    s_expression: str
    body_canonical: str
    depth: int
    step_count: int
    compression_savings: float
    falsification_passed: bool
    smt_verified: bool
    quarantined: bool = False
    active: bool = False
    rejection_reason: str | None = None
    rule_id: str | None = None


def extract_subtrees(node: SchemeNode, min_depth: int = 2, max_depth: int = 5) -> list[SchemeNode]:
    """
    Extracts all sub-AST lists from an expression within specified depth bounds.
    Leaves/atoms are omitted.
    """
    subtrees: list[SchemeNode] = []

    def _walk(curr: SchemeNode) -> None:
        if isinstance(curr, list) and curr:
            d = ast_depth(curr)
            if min_depth <= d <= max_depth:
                subtrees.append(curr)
            for child in curr:
                _walk(child)

    _walk(node)
    return subtrees


def rewrite_with_macro(expr: SchemeNode, macro_def: MacroDefinition) -> SchemeNode:
    """
    Recursively rewrites occurrences of macro_def.body in expr into invocations of macro_def.
    """
    bindings = match_template(macro_def.body, expr)
    if bindings is not None:
        args = [bindings.get(p, Symbol(p)) for p in macro_def.params]
        return [Symbol(macro_def.name), *args]

    if isinstance(expr, list):
        return [rewrite_with_macro(child, macro_def) for child in expr]

    return expr


class DreamCoderMacroMiner:
    """
    DreamCoder-style Macro Miner (Module 14).
    Mines recurring sub-AST patterns, evaluates compression savings, and enforces
    D-REAS-05, D-REAS-06, and D-REAS-07 invariants.
    """

    def __init__(
        self,
        rule_lifecycle: RuleLifecycleManager | None = None,
        falsifier: ScratchpadFalsifier | None = None,
        smt_verifier: SMTVerifier | None = None,
    ) -> None:
        self.lifecycle = rule_lifecycle
        self.falsifier = falsifier or ScratchpadFalsifier()
        self.smt_verifier = smt_verifier or SMTVerifier(allow_pure_reasoning=True)

    def mine_candidate(
        self,
        macro_name: str,
        instances: list[SchemeNode],
        sample_bindings: list[dict[str, SchemeNode]] | None = None,
        registered_tools: dict[str, ToolSchema] | None = None,
    ) -> MinedMacroCandidate:
        """
        Synthesizes, bounds-checks, falsifies, verifies, and quarantines a macro candidate
        from a list of recurring concrete AST instances.
        """
        if len(instances) < MIN_INSTANCES_FOR_MINING:
            return MinedMacroCandidate(
                name=macro_name,
                params=[],
                s_expression="",
                body_canonical="",
                depth=0,
                step_count=0,
                compression_savings=0.0,
                falsification_passed=False,
                smt_verified=False,
                rejection_reason=f"Insufficient instances: {len(instances)} < {MIN_INSTANCES_FOR_MINING}",
            )

        # 1. First-Order Anti-Unification
        try:
            template, binding_maps = anti_unify_many(instances, var_prefix="arg")
        except Exception as exc:
            logger.debug("anti_unify_failed", macro=macro_name, error=str(exc))
            return MinedMacroCandidate(
                name=macro_name,
                params=[],
                s_expression="",
                body_canonical="",
                depth=0,
                step_count=0,
                compression_savings=0.0,
                falsification_passed=False,
                smt_verified=False,
                rejection_reason=f"Anti-unification failure: {exc}",
            )

        params = extract_parameters(template)
        if not params:
            return MinedMacroCandidate(
                name=macro_name,
                params=[],
                s_expression="",
                body_canonical=to_canonical(template),
                depth=ast_depth(template),
                step_count=1,
                compression_savings=0.0,
                falsification_passed=False,
                smt_verified=False,
                rejection_reason="No parameters abstracted: identical constant instances",
            )

        macro_def = MacroDefinition(
            name=macro_name,
            params=params,
            body=template,
            doc="Synthesized by DreamCoder Macro Miner",
        )

        params_str = " ".join(params)
        body_canon = to_canonical(template)
        defmacro_sexpr = f"(defmacro {macro_name} ({params_str})\n  {body_canon})"

        # 2. D-REAS-05 Complexity Bounding
        depth = ast_depth(template)
        if depth > MAX_MACRO_DEPTH:
            reason = f"D-REAS-05 violation: macro depth {depth} exceeds limit {MAX_MACRO_DEPTH}"
            logger.warning("macro_bound_rejected", macro=macro_name, depth=depth, limit=MAX_MACRO_DEPTH)
            return MinedMacroCandidate(
                name=macro_name,
                params=params,
                s_expression=defmacro_sexpr,
                body_canonical=body_canon,
                depth=depth,
                step_count=1,
                compression_savings=0.0,
                falsification_passed=False,
                smt_verified=False,
                rejection_reason=reason,
            )

        # Check macro expansion step count
        reg = MacroRegistry({macro_name: macro_def})
        expander = MacroExpander(reg)
        sample_call: SchemeNode = [Symbol(macro_name), *[Symbol(f"val_{i}") for i in range(len(params))]]
        try:
            expander.expand(sample_call)
            step_count = expander.step_count
        except Exception as step_exc:
            logger.warning("macro_expansion_step_error", macro=macro_name, error=str(step_exc))
            return MinedMacroCandidate(
                name=macro_name,
                params=params,
                s_expression=defmacro_sexpr,
                body_canonical=body_canon,
                depth=depth,
                step_count=expander.step_count,
                compression_savings=0.0,
                falsification_passed=False,
                smt_verified=False,
                rejection_reason=f"D-REAS-05 step violation: {step_exc}",
            )

        if step_count > MAX_MACRO_STEPS:
            reason = f"D-REAS-05 violation: expansion steps {step_count} exceeds limit {MAX_MACRO_STEPS}"
            return MinedMacroCandidate(
                name=macro_name,
                params=params,
                s_expression=defmacro_sexpr,
                body_canonical=body_canon,
                depth=depth,
                step_count=step_count,
                compression_savings=0.0,
                falsification_passed=False,
                smt_verified=False,
                rejection_reason=reason,
            )

        # 3. Module 7 Idiomaticity Description Length Savings Check
        rewritten_instances = [rewrite_with_macro(inst, macro_def) for inst in instances]
        savings = compute_compression_savings(instances, macro_def, rewritten_instances)
        if savings <= 0.0:
            reason = f"Negative compression savings ({savings:.2f} <= 0.0)"
            return MinedMacroCandidate(
                name=macro_name,
                params=params,
                s_expression=defmacro_sexpr,
                body_canonical=body_canon,
                depth=depth,
                step_count=step_count,
                compression_savings=savings,
                falsification_passed=False,
                smt_verified=False,
                rejection_reason=reason,
            )

        # 4. Module 5 Dynamic Scratchpad Falsification (>= 3 concrete test cases)
        effective_bindings = sample_bindings if sample_bindings is not None else binding_maps
        test_cases = self.falsifier.synthesize_test_cases(macro_def, effective_bindings)
        falsification_res = self.falsifier.falsify(macro_def, test_cases)
        if not falsification_res.passed:
            reason = f"Scratchpad falsification failed: {falsification_res.failure_reason}"
            logger.warning("macro_falsified", macro=macro_name, reason=reason)
            return MinedMacroCandidate(
                name=macro_name,
                params=params,
                s_expression=defmacro_sexpr,
                body_canonical=body_canon,
                depth=depth,
                step_count=step_count,
                compression_savings=savings,
                falsification_passed=False,
                smt_verified=False,
                rejection_reason=reason,
            )

        # 5. D-REAS-07 Z3 SMT Formal Verification
        # Construct candidate rule embedding the macro form with valid state predicate
        is_num = _is_arithmetic_tree(template)
        has_state_pred = any(
            op in STATE_PREDICATES for op in _collect_symbols(template)
        )
        if has_state_pred:
            sample_call_args = " ".join(f'"{p}_val"' for p in params)
            when_clause = f"({macro_name} {sample_call_args})"
        elif is_num:
            sample_call_args = " ".join(str(i + 1) for i in range(len(params)))
            when_clause = f'(and (intent= "reasoning") (> ({macro_name} {sample_call_args}) 0))'
        else:
            sample_call_args = " ".join(f'"{p}_val"' for p in params)
            when_clause = f'(and (intent= "reasoning") ({macro_name} {sample_call_args}))'

        clean_rule_name = macro_name.replace("_", "-")
        wrapped_rule_source = (
            f"{defmacro_sexpr}\n\n"
            f'(rule "{clean_rule_name}-induced-v1"\n'
            f"  :when {when_clause}\n"
            f'  :plan (list (say "mined macro verified"))\n'
            f"  :priority 1)"
        )

        smt_res = self.smt_verifier.verify_source(
            wrapped_rule_source,
            registered_tools=registered_tools,
        )
        if not smt_res.verified:
            reason = f"SMT verification failed: {smt_res.status} ({', '.join(smt_res.reasons)})"
            logger.warning("macro_smt_failed", macro=macro_name, status=smt_res.status)
            return MinedMacroCandidate(
                name=macro_name,
                params=params,
                s_expression=defmacro_sexpr,
                body_canonical=body_canon,
                depth=depth,
                step_count=step_count,
                compression_savings=savings,
                falsification_passed=True,
                smt_verified=False,
                rejection_reason=reason,
            )

        # 6. D-REAS-06 Rule Lifecycle Quarantine Admission (0 to ACTIVE)
        quarantined = False
        rule_id = f"{clean_rule_name}-induced-v1"
        if self.lifecycle is not None:
            try:
                managed = self.lifecycle.register_rule(wrapped_rule_source)
                quarantined = (managed.status == "QUARANTINE")
                # Attempt promotion: must fail without operator approval
                promo = self.lifecycle.promote_if_eligible(managed.rule_id)
                active = (managed.status == "ACTIVE")
                if active or promo.promoted:
                    raise RuntimeError("D-REAS-06 invariant breached: mined macro auto-promoted to ACTIVE")
            except Exception as reg_exc:
                logger.warning("macro_lifecycle_registration_error", error=str(reg_exc))
                return MinedMacroCandidate(
                    name=macro_name,
                    params=params,
                    s_expression=defmacro_sexpr,
                    body_canonical=body_canon,
                    depth=depth,
                    step_count=step_count,
                    compression_savings=savings,
                    falsification_passed=True,
                    smt_verified=True,
                    quarantined=False,
                    rejection_reason=f"Lifecycle registration failed: {reg_exc}",
                )

        return MinedMacroCandidate(
            name=macro_name,
            params=params,
            s_expression=defmacro_sexpr,
            body_canonical=body_canon,
            depth=depth,
            step_count=step_count,
            compression_savings=savings,
            falsification_passed=True,
            smt_verified=True,
            quarantined=quarantined,
            active=False,
            rule_id=rule_id,
        )

    def evaluate_shadow_utility(
        self,
        candidate: MinedMacroCandidate,
        target_expressions: list[SchemeNode],
    ) -> dict[str, object]:
        """
        Evaluates compression utility of a candidate macro in quarantine shadow mode
        across target expressions (e.g. Bucket C reasoning failure items).
        Returns per-item baseline costs, compressed costs, and deltas.
        """
        macro_def = MacroDefinition(
            name=candidate.name,
            params=candidate.params,
            body=parse_expr(candidate.body_canonical),
        )

        improvements: list[dict[str, object]] = []
        reduced_count = 0

        for idx, expr in enumerate(target_expressions):
            base_cost = ast_cost(expr)
            rewritten = rewrite_with_macro(expr, macro_def)
            comp_cost = ast_cost(rewritten)
            delta = base_cost - comp_cost

            if delta > 0.0:
                reduced_count += 1
                improvements.append({
                    "item_index": idx,
                    "baseline_cost": base_cost,
                    "compressed_cost": comp_cost,
                    "cost_delta": delta,
                })

        return {
            "macro_name": candidate.name,
            "total_items_evaluated": len(target_expressions),
            "items_with_cost_reduction": reduced_count,
            "improvements": improvements,
            "utility_gate_satisfied": reduced_count >= 3,
        }


def _ast_skeleton(node: SchemeNode, max_depth: int = 2) -> tuple[object, ...]:
    """Computes a structural skeleton signature for clustering candidate subtrees."""
    if isinstance(node, list) and node and max_depth > 0:
        head = node[0].name if isinstance(node[0], Symbol) else str(node[0])
        return (head, len(node), tuple(_ast_skeleton(c, max_depth - 1) for c in node[1:]))
    return ("*",)


def mine_new_primitives(
    solved_traces: list[SchemeNode | str],
    miner: DreamCoderMacroMiner | None = None,
    min_traces: int = 2,
    min_cost_savings: float = 2.0,
    prefix: str = "prim",
) -> list[MinedMacroCandidate]:
    """
    Induces parameter-abstracted MicroScheme primitives/macros across verified solved traces
    via first-order anti-unification (Milestone 3, WO-33).

    Enforces the anti-test-tuning gate:
    1. Candidates are induced strictly from existing solved traces.
    2. Sub-AST pattern must appear across >= min_traces independent traces.
    3. Minimum compression savings >= min_cost_savings (MDL).
    4. Passes dynamic scratchpad falsification and Z3 SMT formal verification.
    """
    parsed_traces: list[SchemeNode] = []
    for t in solved_traces:
        if isinstance(t, str):
            parsed_traces.append(parse_expr(t))
        else:
            parsed_traces.append(t)

    if len(parsed_traces) < min_traces:
        return []

    # Map skeleton -> dict of trace_idx -> list of subtrees
    clusters: dict[tuple[object, ...], dict[int, list[SchemeNode]]] = {}

    for t_idx, trace in enumerate(parsed_traces):
        subtrees = extract_subtrees(trace, min_depth=2, max_depth=5)
        d = ast_depth(trace)
        if 2 <= d <= 5:
            subtrees.append(trace)

        for sub in subtrees:
            skel = _ast_skeleton(sub, max_depth=2)
            if skel not in clusters:
                clusters[skel] = {}
            if t_idx not in clusters[skel]:
                clusters[skel][t_idx] = []
            clusters[skel][t_idx].append(sub)

    effective_miner = miner or DreamCoderMacroMiner(
        smt_verifier=SMTVerifier(allow_pure_reasoning=True)
    )
    admitted: list[MinedMacroCandidate] = []
    seen_bodies: set[str] = set()

    for _skel, trace_map in clusters.items():
        if len(trace_map) < min_traces:
            continue

        # Extract representative instances across independent traces
        instances = [trace_map[t_idx][0] for t_idx in sorted(trace_map.keys())]

        clean_prefix = prefix.replace("_", "-")
        macro_name = f"{clean_prefix}-{len(admitted) + 1}"
        candidate = effective_miner.mine_candidate(
            macro_name=macro_name,
            instances=instances,
        )

        if (
            candidate.falsification_passed
            and candidate.smt_verified
            and candidate.compression_savings >= min_cost_savings
            and candidate.body_canonical not in seen_bodies
        ):
            seen_bodies.add(candidate.body_canonical)
            admitted.append(candidate)

    return admitted


def register_mined_primitive(
    candidate: MinedMacroCandidate,
    macro_registry: MacroRegistry | None = None,
    min_cost_savings: float = 2.0,
) -> bool:
    """
    Registers a mined macro into the Scheme macro registry if it satisfies
    all Milestone 3 admission criteria (coverage >= 2 traces, SMT verified, savings >= 2.0).
    """
    if not candidate.smt_verified or not candidate.falsification_passed:
        return False
    if candidate.compression_savings < min_cost_savings:
        return False
    if not candidate.params:
        return False

    macro_def = MacroDefinition(
        name=candidate.name,
        params=candidate.params,
        body=parse_expr(candidate.body_canonical),
        doc=f"Mined primitive (savings={candidate.compression_savings:.2f})",
    )
    if macro_registry is not None:
        macro_registry.register(macro_def)
    else:
        from lucca.reasoning.spatial_scheme import GLOBAL_MACRO_REGISTRY
        GLOBAL_MACRO_REGISTRY.register(macro_def)

    from lucca.reasoning.spatial_dsl import register_macro_primitive
    register_macro_primitive(
        name=candidate.name,
        params=candidate.params,
        doc=f"Mined primitive (savings={candidate.compression_savings:.2f}): {candidate.body_canonical}",
    )
    return True
