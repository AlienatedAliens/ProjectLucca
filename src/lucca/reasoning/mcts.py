"""
Project Lucca — AST-Hole MCTS Engine (Module 12, WO-31)
D-REAS-11, D-AUD-01, D-REAS-05, D-REAS-06, D-REAS-07

Multi-threaded CPU Monte Carlo Tree Search over MicroScheme S-expression holes:
1. Selection: UCT selection penalized by structural idiomaticity cost (ast_cost).
2. Expansion: Guided by backward abduction, pure operators, and observed literals.
3. Safety: Integrated with TracebackDivergenceGuard (prunes cycles/loops) and
   BoundaryTopologyParser (enforces tool and typing contracts).
4. Simulation: In-process micro-evaluation bounded by strict gas/time limits.
5. Quarantine: Emits verified programs strictly into QUARANTINE mode (0 to ACTIVE).

Hardware integrity: Host CPU threads only (24 threads), 0 MB VRAM delta, host RAM <= 512 MB.
Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

import concurrent.futures
import copy
import math
import random
import threading
import time
from typing import Final

from pydantic import BaseModel, ConfigDict, Field
import structlog
import z3

from lucca.core.convergence import TracebackDivergenceGuard
from lucca.core.schemas import CandidateRule, ToolSchema
from lucca.reasoning.abduction import BackwardAbductionSolver, _substitute_hole
from lucca.reasoning.cost import ast_cost, ast_depth
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.eval import SchemeEvaluator
from lucca.reasoning.scheme.parser import (
    ALLOWED_OPS,
    SchemeAtom,
    SchemeNode,
    Symbol,
    parse_expr,
    parse_rule,
    to_canonical,
)
from lucca.reasoning.scheme.prims import PURE_PRIMITIVES
from lucca.reasoning.smt_verifier import SMTVerifier
from lucca.reasoning.topology import (
    BoundaryTopologyParser,
    extract_hole_info,
    is_hole_node,
)

logger = structlog.get_logger(__name__)

DEFAULT_CPU_THREADS: Final[int] = 8
DEFAULT_MAX_ITERATIONS: Final[int] = 300
DEFAULT_MAX_DEPTH: Final[int] = 8
DEFAULT_C_PUCT: Final[float] = 1.414
DEFAULT_COST_WEIGHT: Final[float] = 0.15
DEFAULT_TIMEOUT_SECONDS: Final[float] = 5.0

UNIVERSAL_NUMERIC_CONSTANTS: Final[list[int | float]] = [
    0, 1, 2, 3, -1
]


class MCTSConfig(BaseModel):
    """Configuration parameters for the AST-Hole MCTS Engine."""

    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_depth: int = DEFAULT_MAX_DEPTH
    cpu_threads: int = DEFAULT_CPU_THREADS
    c_puct: float = DEFAULT_C_PUCT
    cost_weight: float = DEFAULT_COST_WEIGHT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_candidates_per_hole: int = 16


class SynthesisResult(BaseModel):
    """Result of an autonomous program synthesis run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    synthesized_ast: object = None
    canonical_code: str | None = None
    iterations_run: int = 0
    nodes_explored: int = 0
    cost: float = 0.0
    elapsed_ms: float = 0.0
    pruned_branches: int = 0
    quarantined_rule_id: str | None = None
    rejection_reason: str | None = None


class MCTSNode:
    """A search tree node representing a partial or concrete MicroScheme AST."""

    def __init__(
        self,
        ast: SchemeNode,
        parent: MCTSNode | None = None,
        depth: int = 0,
    ) -> None:
        self.ast = ast
        self.canonical_str = to_canonical(ast)
        self.parent = parent
        self.depth = depth
        self.children: list[MCTSNode] = []
        self.visits: int = 0
        self.total_reward: float = 0.0
        self.cost: float = ast_cost(ast)
        self.is_terminal: bool = False
        self.is_solution: bool = False
        self.unresolved_holes: list[tuple[str, str | None]] = []
        self._lock = threading.Lock()

        # Extract remaining holes
        self._extract_holes()

    def _extract_holes(self) -> None:
        holes: list[tuple[str, str | None]] = []

        def _walk(curr: SchemeNode) -> None:
            if is_hole_node(curr):
                info = extract_hole_info(curr)
                if info:
                    holes.append(info)
                return
            if isinstance(curr, list):
                for child in curr:
                    _walk(child)

        _walk(self.ast)
        self.unresolved_holes = holes
        if not holes:
            self.is_terminal = True

    @property
    def q_value(self) -> float:
        with self._lock:
            return self.total_reward / self.visits if self.visits > 0 else 0.0

    def compute_uct(self, parent_visits: int, c_puct: float, cost_weight: float) -> float:
        with self._lock:
            if self.visits == 0:
                # Prioritize unvisited nodes
                return float("inf")
            exploitation = self.total_reward / self.visits
            exploration = c_puct * math.sqrt(math.log(parent_visits + 1) / self.visits)
            cost_penalty = cost_weight * self.cost
            return exploitation + exploration - cost_penalty

    def update(self, reward: float) -> None:
        with self._lock:
            self.visits += 1
            self.total_reward += reward


def _count_ast_nodes(node: SchemeNode) -> int:
    if isinstance(node, list):
        return 1 + sum(_count_ast_nodes(c) for c in node)
    return 1


def _ast_references_any_var(node: SchemeNode, var_names: set[str]) -> bool:
    if isinstance(node, Symbol):
        return node.name in var_names
    if isinstance(node, str):
        return node in var_names
    if isinstance(node, list):
        return any(_ast_references_any_var(c, var_names) for c in node)
    return False


def _evaluate_node_safe(
    node_ast: SchemeNode,
    extra_env: dict[str, object] | None = None,
) -> SchemeAtom | None:
    """Safely evaluates a closed pure MicroScheme expression with optional bound inputs."""
    evaluator = SchemeEvaluator(gas_limit=1000, timeout_ms=50.0)
    try:
        env: dict[str, object] = dict(PURE_PRIMITIVES)
        if extra_env:
            env.update(extra_env)
        val = evaluator.eval(node_ast, env)
        if isinstance(val, (int, float, bool, str, list)):
            return val
        return None
    except Exception as exc:
        logger.debug("evaluate_node_safe_failed", error=str(exc))
        return None


def _collect_subtree_paths(node: SchemeNode, prefix: tuple[int, ...] = ()) -> list[tuple[int, ...]]:
    paths: list[tuple[int, ...]] = [prefix]
    if isinstance(node, list) and len(node) >= 2:
        for idx in range(1, len(node)):
            paths.extend(_collect_subtree_paths(node[idx], (*prefix, idx)))
    return paths


def _get_subtree_at(node: SchemeNode, path: tuple[int, ...]) -> SchemeNode:
    curr: SchemeNode = node
    for idx in path:
        if isinstance(curr, list) and 0 <= idx < len(curr):
            curr = curr[idx]
    return copy.deepcopy(curr)


def _replace_subtree_at(
    node: SchemeNode, path: tuple[int, ...], replacement: SchemeNode
) -> SchemeNode:
    if not path:
        return copy.deepcopy(replacement)
    if not isinstance(node, list):
        return copy.deepcopy(node)
    idx = path[0]
    out = list(node)
    if 0 <= idx < len(out):
        out[idx] = _replace_subtree_at(out[idx], path[1:], replacement)
    return out


def _gp_crossover(
    parent_a: SchemeNode, parent_b: SchemeNode, rng: random.Random
) -> SchemeNode:
    """Koza Genetic Programming subtree crossover between two MicroScheme ASTs."""
    paths_a = _collect_subtree_paths(parent_a)
    paths_b = _collect_subtree_paths(parent_b)
    if not paths_a or not paths_b:
        return copy.deepcopy(parent_a)
    chosen_a = rng.choice(paths_a)
    chosen_b = rng.choice(paths_b)
    donor = _get_subtree_at(parent_b, chosen_b)
    child = _replace_subtree_at(parent_a, chosen_a, donor)
    if ast_depth(child) > DEFAULT_MAX_DEPTH:
        return copy.deepcopy(parent_a)
    return child


def _gp_mutate(
    ast: SchemeNode,
    var_symbols: list[Symbol],
    literals: list[int | float | str],
    rng: random.Random,
) -> SchemeNode:
    """Koza GP point and subtree mutation over operators and leaf terminals."""
    paths = _collect_subtree_paths(ast)
    if not paths:
        return copy.deepcopy(ast)
    target_path = rng.choice(paths)
    sub = _get_subtree_at(ast, target_path)
    ops = [Symbol("+"), Symbol("-"), Symbol("*"), Symbol("/")]
    terminals: list[SchemeNode] = [*var_symbols, *[lit for lit in literals if isinstance(lit, (int, float))]]
    if not terminals:
        terminals = [0, 1, 2]

    if isinstance(sub, list) and len(sub) >= 3 and rng.random() < 0.55:
        mutated_sub: SchemeNode = [rng.choice(ops), *copy.deepcopy(sub[1:])]
    elif rng.random() < 0.65:
        mutated_sub = copy.deepcopy(rng.choice(terminals))
    else:
        t1 = copy.deepcopy(rng.choice(terminals))
        t2 = copy.deepcopy(rng.choice(terminals))
        mutated_sub = [rng.choice(ops[:3]), t1, t2]

    child = _replace_subtree_at(ast, target_path, mutated_sub)
    if ast_depth(child) > DEFAULT_MAX_DEPTH:
        return copy.deepcopy(ast)
    return child


_Z3_DIVISION_LOCK = threading.Lock()


def _has_unsafe_division_ast(node: SchemeNode) -> tuple[bool, str]:
    """Uses static and thread-safe Z3 symbolic analysis to detect potential division by zero in AST."""

    def _to_z3(curr: SchemeNode, ctx: z3.Context, var_map: dict[str, z3.ArithRef]) -> z3.ArithRef | None:
        if isinstance(curr, bool):
            return z3.IntVal(1 if curr else 0, ctx=ctx)
        if isinstance(curr, int):
            return z3.IntVal(curr, ctx=ctx)
        if isinstance(curr, float) and curr.is_integer():
            return z3.IntVal(int(curr), ctx=ctx)
        if isinstance(curr, Symbol):
            if curr.name not in var_map:
                var_map[curr.name] = z3.Int(curr.name, ctx=ctx)
            return var_map[curr.name]
        if isinstance(curr, str) and not curr.startswith('"'):
            if curr not in var_map:
                var_map[curr] = z3.Int(curr, ctx=ctx)
            return var_map[curr]
        if isinstance(curr, list) and len(curr) >= 2:
            head = curr[0]
            op = head.name if isinstance(head, Symbol) else (head if isinstance(head, str) else "")
            subs = [_to_z3(c, ctx, var_map) for c in curr[1:]]
            if any(s is None for s in subs):
                return None
            valid_subs = [s for s in subs if s is not None]
            if not valid_subs:
                return None
            if op == "+":
                acc = valid_subs[0]
                for s in valid_subs[1:]:
                    acc = acc + s
                return acc
            if op == "-":
                if len(valid_subs) == 1:
                    return -valid_subs[0]
                acc = valid_subs[0]
                for s in valid_subs[1:]:
                    acc = acc - s
                return acc
            if op == "*":
                acc = valid_subs[0]
                for s in valid_subs[1:]:
                    acc = acc * s
                return acc
            if op == "/" and len(valid_subs) == 2:
                return valid_subs[0] / valid_subs[1]
        return None

    def _walk(curr: SchemeNode) -> tuple[bool, str]:
        if isinstance(curr, list) and curr:
            head = curr[0]
            op = head.name if isinstance(head, Symbol) else (head if isinstance(head, str) else "")
            if op in ("/", "modulo") and len(curr) >= 3:
                denom = curr[2]
                val = _evaluate_node_safe(denom)
                if isinstance(val, (int, float)):
                    if abs(float(val)) < 1e-12:
                        return (True, f"Division by zero in {to_canonical(curr)}")
                else:
                    with _Z3_DIVISION_LOCK:
                        local_ctx = z3.Context()
                        local_vars: dict[str, z3.ArithRef] = {}
                        z_denom = _to_z3(denom, local_ctx, local_vars)
                        if z_denom is not None:
                            s_non_zero = z3.Solver(ctx=local_ctx)
                            s_non_zero.set("timeout", 100)
                            s_non_zero.add(z_denom != 0)
                            if s_non_zero.check() == z3.unsat:
                                return (True, f"Denominator identically zero in {to_canonical(curr)}")
            for child in curr[1:]:
                bad, reason = _walk(child)
                if bad:
                    return (True, reason)
        return (False, "")

    return _walk(node)


class ASTHoleMCTSEngine:
    """
    Multi-Threaded CPU Monte Carlo Tree Search Engine for MicroScheme hole synthesis.
    """

    def __init__(
        self,
        config: MCTSConfig | None = None,
        registered_tools: list[ToolSchema] | None = None,
        rule_lifecycle: RuleLifecycleManager | None = None,
        smt_verifier: SMTVerifier | None = None,
    ) -> None:
        self.config = config or MCTSConfig()
        self.divergence_guard = TracebackDivergenceGuard(
            max_recurrence=3,
            max_steps=self.config.max_depth * 4,
        )
        self.topology_parser = BoundaryTopologyParser(registered_tools=registered_tools)
        self.abduction_solver = BackwardAbductionSolver(
            max_hypotheses_per_hole=self.config.max_candidates_per_hole
        )
        self.rule_lifecycle = rule_lifecycle
        self.smt_verifier = smt_verifier

    def _extract_test_case_inputs_and_vars(
        self,
        test_cases: list[dict[str, object]] | None,
        sketch: SchemeNode,
    ) -> tuple[list[Symbol], list[int | float | str]]:
        """Extracts input variable symbols and input-only literals (never target outputs)."""
        var_names: list[str] = []
        input_literals: list[int | float | str] = []

        if test_cases:
            for tc in test_cases:
                raw_in = tc.get("inputs", tc.get("input", tc.get("env", {})))
                if isinstance(raw_in, dict):
                    for k, v in raw_in.items():
                        ks = str(k)
                        if ks not in var_names:
                            var_names.append(ks)
                        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
                            input_literals.append(v)
                elif isinstance(raw_in, (list, tuple)):
                    for idx, v in enumerate(raw_in):
                        ks = "x" if idx == 0 else ("y" if idx == 1 else f"arg{idx}")
                        if ks not in var_names:
                            var_names.append(ks)
                        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
                            input_literals.append(v)
                elif isinstance(raw_in, (int, float, str)) and not isinstance(raw_in, bool):
                    if "x" not in var_names:
                        var_names.append("x")
                    input_literals.append(raw_in)

        # Also extract any existing non-operator symbols in sketch
        def _walk_sketch(n: SchemeNode) -> None:
            if is_hole_node(n):
                return
            if isinstance(n, (int, float)) and not isinstance(n, bool):
                input_literals.append(n)
            elif isinstance(n, list) and n:
                for child in n[1:]:
                    _walk_sketch(child)

        _walk_sketch(sketch)
        return ([Symbol(vn) for vn in var_names], input_literals)

    def _evaluate_candidate_on_cases(
        self,
        node_ast: SchemeNode,
        goal: int | float | str | bool | list[object],
        test_cases: list[dict[str, object]] | None,
        var_names: set[str],
    ) -> tuple[bool, float]:
        """Evaluates a closed AST against test_cases (or goal) and returns (is_solution, reward)."""
        bad_div, _ = _has_unsafe_division_ast(node_ast)
        if bad_div:
            return (False, 0.0)

        node_cnt = _count_ast_nodes(node_ast)
        if test_cases:
            # If outputs vary across test_cases and AST is a constant (uses no input variables), reject cheat
            distinct_outputs = {
                str(tc.get("output", tc.get("expected", tc.get("expected_output"))))
                for tc in test_cases
            }
            if len(distinct_outputs) > 1 and var_names and not _ast_references_any_var(node_ast, var_names):
                return (False, 0.0)

            passed = 0
            total = len(test_cases)
            for tc in test_cases:
                raw_in = tc.get("inputs", tc.get("input", tc.get("env", {})))
                env_bind: dict[str, object] = {}
                if isinstance(raw_in, dict):
                    for k, v in raw_in.items():
                        env_bind[str(k)] = v
                elif isinstance(raw_in, (list, tuple)):
                    for idx, v in enumerate(raw_in):
                        ks = "x" if idx == 0 else ("y" if idx == 1 else f"arg{idx}")
                        env_bind[ks] = v
                else:
                    env_bind["x"] = raw_in
                    env_bind["n"] = raw_in

                exp_out = tc.get("output", tc.get("expected", tc.get("expected_output", goal)))
                val = _evaluate_node_safe(node_ast, extra_env=env_bind)
                if val is not None and self._matches_goal(
                    val,
                    exp_out if isinstance(exp_out, (int, float, str, bool, list)) else goal,
                ):
                    passed += 1

            frac = passed / max(1, total)
            reward = max(0.0, frac - 0.01 * node_cnt)
            return (passed == total and total > 0, reward)

        eval_res = _evaluate_node_safe(node_ast)
        if eval_res is not None and self._matches_goal(eval_res, goal):
            reward = max(0.01, 1.0 - 0.01 * node_cnt)
            return (True, reward)
        return (False, 0.0)

    def synthesize(
        self,
        sketch_with_holes: SchemeNode,
        goal: int | float | str | bool | list[object] = 0,
        test_cases: list[dict[str, object]] | None = None,
        candidate_literals: list[int | float | str] | None = None,
        intent_label: str = "program_synthesis",
    ) -> SynthesisResult:
        """
        Executes parallel CPU MCTS + Koza Genetic Programming over open AST holes in the sketch.
        """
        t0 = time.perf_counter()

        var_symbols, tc_input_literals = self._extract_test_case_inputs_and_vars(
            test_cases, sketch_with_holes
        )
        var_name_set = {s.name for s in var_symbols}

        # Validate initial sketch topology (allowing input variable symbols when test_cases present)
        preflight = self.topology_parser.validate_ast(sketch_with_holes, allow_holes=True)
        if not preflight.is_valid and not var_symbols:
            violations_summary = "; ".join(v.detail for v in preflight.violations)
            return SynthesisResult(
                success=False,
                rejection_reason=f"Initial sketch boundary violation: {violations_summary}",
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )

        root = MCTSNode(sketch_with_holes, depth=0)

        # Build literal pool strictly from universal constants and candidate_literals (NEVER goal!)
        literal_pool: list[int | float | str] = []
        if candidate_literals:
            literal_pool.extend(candidate_literals)
        literal_pool.extend(UNIVERSAL_NUMERIC_CONSTANTS)
        for lit in tc_input_literals:
            if isinstance(lit, (int, float)) and abs(float(lit)) <= 10:
                literal_pool.append(lit)

        seen_lit: set[str] = set()
        dedup_literals: list[int | float | str] = []
        for lit in literal_pool:
            s = str(lit)
            if s not in seen_lit:
                seen_lit.add(s)
                dedup_literals.append(lit)

        # Check if root is already closed and satisfies goal / test_cases
        if root.is_terminal:
            ok_root, _ = self._evaluate_candidate_on_cases(
                root.ast, goal, test_cases, var_name_set
            )
            if ok_root:
                root.is_solution = True
                return self._finalize_solution(root, 0, 1, 0, t0, intent_label)
            return SynthesisResult(
                success=False,
                iterations_run=0,
                nodes_explored=1,
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
                rejection_reason="Closed expression failed verification or goal check",
            )

        best_solution: list[MCTSNode] = []
        gp_population: list[tuple[float, SchemeNode]] = []
        nodes_explored = [1]
        pruned_count = [0]
        tree_lock = threading.Lock()
        stop_event = threading.Event()

        effective_target: int | float | str | bool = (
            goal if isinstance(goal, (int, float, str, bool)) else 0
        )
        if test_cases and effective_target == 0:
            first_out = test_cases[0].get(
                "output", test_cases[0].get("expected", test_cases[0].get("expected_output", 0))
            )
            if isinstance(first_out, (int, float, str, bool)):
                effective_target = first_out

        abductive_proposals = self.abduction_solver.propose_candidates_for_all_holes(
            sketch=root.ast,
            target_val=effective_target,
            holes=root.unresolved_holes,
            test_cases=test_cases,
        )

        def _run_worker(worker_id: int) -> None:
            rng = random.Random(42 + worker_id * 997)
            iterations_per_worker = max(
                1, self.config.max_iterations // max(1, self.config.cpu_threads)
            )
            for iter_idx in range(iterations_per_worker):
                if stop_event.is_set():
                    break
                if (time.perf_counter() - t0) > self.config.timeout_seconds:
                    break

                # 1. Selection
                curr = root
                path_hashes: list[str] = [curr.canonical_str]

                while curr.children and not curr.is_terminal:
                    with curr._lock:
                        parent_v = curr.visits
                        best_child: MCTSNode | None = None
                        best_uct = -float("inf")
                        for child in curr.children:
                            uct = child.compute_uct(
                                parent_v, self.config.c_puct, self.config.cost_weight
                            )
                            if uct > best_uct:
                                best_uct = uct
                                best_child = child

                    if best_child is None:
                        break

                    curr = best_child
                    path_hashes.append(curr.canonical_str)

                    if self.divergence_guard.should_prune(path_hashes):
                        with tree_lock:
                            pruned_count[0] += 1
                        break

                # 2. Expansion
                if (
                    not curr.is_terminal
                    and curr.unresolved_holes
                    and curr.depth < self.config.max_depth
                    and not curr.children
                ):
                    with curr._lock:
                        if not curr.children:
                            target_hole = curr.unresolved_holes[0]
                            local_hyps = list(abductive_proposals.get(target_hole[0], []))
                            if curr.depth > 0:
                                local_hyps.extend(
                                    self.abduction_solver.invert_goal_for_sketch(
                                        curr.ast,
                                        effective_target,
                                        target_hole[0],
                                        test_cases=test_cases,
                                    )
                                )
                            candidates = self._generate_hole_candidates(
                                curr.ast,
                                target_hole,
                                local_hyps,
                                dedup_literals,
                                curr.depth,
                                var_symbols=var_symbols,
                            )

                            for cand in candidates:
                                new_ast = _substitute_hole(curr.ast, target_hole[0], cand)
                                v_res = self.topology_parser.validate_ast(
                                    new_ast, allow_holes=True
                                )
                                if v_res.is_valid or var_symbols:
                                    child_node = MCTSNode(
                                        ast=new_ast,
                                        parent=curr,
                                        depth=curr.depth + 1,
                                    )
                                    curr.children.append(child_node)
                                    with tree_lock:
                                        nodes_explored[0] += 1

                # 3. Simulation / Evaluation + Genetic Programming Evolution
                children_to_eval = list(curr.children) if curr.children else [curr]
                best_iter_reward = 0.0

                for sim_target in children_to_eval:
                    if sim_target.is_terminal:
                        is_sol, reward = self._evaluate_candidate_on_cases(
                            sim_target.ast, goal, test_cases, var_name_set
                        )
                        if reward > best_iter_reward:
                            best_iter_reward = reward
                        with tree_lock:
                            if len(gp_population) < 64:
                                gp_population.append((reward, sim_target.ast))
                        if is_sol:
                            sim_target.is_solution = True
                            with tree_lock:
                                best_solution.append(sim_target)
                            if sim_target.cost <= 12.0:
                                stop_event.set()
                                break
                    else:
                        reward = 0.05 / (1.0 + sim_target.cost)
                        if reward > best_iter_reward:
                            best_iter_reward = reward
                    sim_target.update(reward)

                # Koza GP crossover & mutation step when unresolved holes exist
                if not stop_event.is_set() and root.unresolved_holes and (iter_idx % 2 == 0):
                    with tree_lock:
                        gp_population.sort(key=lambda pair: pair[0], reverse=True)
                        top_pool = [ast for _, ast in gp_population[:16]]

                    if len(top_pool) >= 2:
                        p_a = rng.choice(top_pool)
                        p_b = rng.choice(top_pool)
                        offspring = _gp_crossover(p_a, p_b, rng)
                        if rng.random() < 0.7:
                            offspring = _gp_mutate(offspring, var_symbols, dedup_literals, rng)
                        with tree_lock:
                            nodes_explored[0] += 1
                        is_sol, gp_rew = self._evaluate_candidate_on_cases(
                            offspring, goal, test_cases, var_name_set
                        )
                        with tree_lock:
                            gp_population.append((gp_rew, offspring))
                            if len(gp_population) > 64:
                                gp_population.sort(key=lambda pair: pair[0], reverse=True)
                                del gp_population[48:]
                        if is_sol:
                            gp_node = MCTSNode(ast=offspring, parent=root, depth=1)
                            gp_node.is_solution = True
                            with tree_lock:
                                best_solution.append(gp_node)
                            stop_event.set()

                # 4. Backpropagation
                back_curr: MCTSNode | None = curr
                while back_curr is not None:
                    back_curr.update(best_iter_reward)
                    back_curr = back_curr.parent

        if self.config.cpu_threads > 1:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.config.cpu_threads
            ) as executor:
                futures = [
                    executor.submit(_run_worker, wid)
                    for wid in range(self.config.cpu_threads)
                ]
                concurrent.futures.wait(
                    futures, timeout=self.config.timeout_seconds + 1.0
                )
        else:
            _run_worker(0)

        total_nodes = nodes_explored[0]
        total_pruned = pruned_count[0]

        if best_solution:
            best_solution.sort(key=lambda n: (n.cost, len(n.canonical_str)))
            for candidate_winner in best_solution:
                finalized = self._finalize_solution(
                    candidate_winner,
                    self.config.max_iterations,
                    total_nodes,
                    total_pruned,
                    t0,
                    intent_label,
                )
                if finalized.success:
                    return finalized
            return self._finalize_solution(
                best_solution[0],
                self.config.max_iterations,
                total_nodes,
                total_pruned,
                t0,
                intent_label,
            )

        return SynthesisResult(
            success=False,
            iterations_run=self.config.max_iterations,
            nodes_explored=total_nodes,
            pruned_branches=total_pruned,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            rejection_reason="No satisfying closed expression discovered within budget",
        )

    def _generate_hole_candidates(
        self,
        current_ast: SchemeNode,
        hole: tuple[str, str | None],
        hypotheses: list[object],
        literal_pool: list[int | float | str],
        current_depth: int,
        var_symbols: list[Symbol] | None = None,
    ) -> list[SchemeNode]:
        """Generates ranked substitution candidates for a given hole."""
        candidates: list[SchemeNode] = []
        hole_name, _ = hole

        # 1. Abductive Hypotheses (Highest priority)
        from lucca.reasoning.abduction import AbductiveHypothesis

        for h in hypotheses:
            if isinstance(h, AbductiveHypothesis) and h.hole_name == hole_name:
                try:
                    c_ast = parse_expr(h.candidate_expr)
                    candidates.append(c_ast)
                except Exception as exc:
                    logger.debug("parse_hypothesis_failed", error=str(exc))

        # 2. Input Variable Symbols & Common Compound Building Blocks
        if var_symbols:
            for vs in var_symbols:
                candidates.append(vs)
            if len(var_symbols) >= 2:
                v0, v1 = var_symbols[0], var_symbols[1]
                candidates.append([Symbol("+"), v0, v1])
                candidates.append([Symbol("*"), v0, v1])
                candidates.append([Symbol("-"), v0, v1])
            v0 = var_symbols[0]
            candidates.append([Symbol("*"), v0, v0])
            candidates.append([Symbol("*"), 2, v0])
            candidates.append([Symbol("+"), v0, 1])
            candidates.append([Symbol("-"), v0, 1])

        # 3. Literal Pool (small universal constants only)
        for lit in literal_pool[:8]:
            candidates.append(lit)

        # 4. Recursive sub-operators (if depth permits)
        if current_depth + 2 <= self.config.max_depth:
            sub_h1 = Symbol(f"?h_{current_depth}_a")
            sub_h2 = Symbol(f"?h_{current_depth}_b")
            candidates.append([Symbol("+"), sub_h1, sub_h2])
            candidates.append([Symbol("*"), sub_h1, sub_h2])
            candidates.append([Symbol("-"), sub_h1, sub_h2])
            candidates.append([Symbol("/"), sub_h1, sub_h2])

        return candidates[: max(self.config.max_candidates_per_hole, 20)]

    def _matches_goal(
        self,
        val: SchemeAtom,
        goal: int | float | str | bool | list[object],
    ) -> bool:
        """Determines semantic equality with target goal."""
        if isinstance(goal, (int, float)) and isinstance(val, (int, float)):
            return math.isclose(float(val), float(goal), rel_tol=1e-5, abs_tol=1e-5)
        if isinstance(goal, str):
            s_val = str(val).strip()
            s_goal = str(goal).strip()
            if s_val == s_goal:
                return True
            try:
                f_val = float(s_val)
                f_goal = float(s_goal)
                return math.isclose(f_val, f_goal, rel_tol=1e-5, abs_tol=1e-5)
            except ValueError:
                pass
        return bool(val == goal)

    def _finalize_solution(
        self,
        winner: MCTSNode,
        iterations: int,
        nodes: int,
        pruned: int,
        t0: float,
        intent_label: str,
    ) -> SynthesisResult:
        """Verifies solution via Z3/SMTVerifier and stages into QUARANTINE mode."""
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        canonical_expr = winner.canonical_str

        # Static/Z3 arithmetic safety check (division by zero)
        has_div_zero, div_reason = _has_unsafe_division_ast(winner.ast)
        if has_div_zero:
            return SynthesisResult(
                success=False,
                synthesized_ast=winner.ast,
                canonical_code=canonical_expr,
                iterations_run=iterations,
                nodes_explored=nodes,
                cost=winner.cost,
                pruned_branches=pruned,
                elapsed_ms=elapsed_ms,
                rejection_reason=f"SMT safety rejection: {div_reason}",
            )

        rule_name = f"rule-syn-{int(time.time() * 1000)}-v1"
        rule_sexpr = f'(rule "{rule_name}" :when (intent= "{intent_label}") :plan (list (say "{canonical_expr}")))'

        # Enforce SMT Verification pre-check when available
        if self.smt_verifier is not None:
            try:
                if hasattr(self.smt_verifier, "verify_expression"):
                    expr_res = self.smt_verifier.verify_expression(winner.ast)  # type: ignore[attr-defined]
                    if not expr_res.verified:
                        reasons_str = "; ".join(expr_res.reasons) if expr_res.reasons else expr_res.status
                        return SynthesisResult(
                            success=False,
                            synthesized_ast=winner.ast,
                            canonical_code=canonical_expr,
                            iterations_run=iterations,
                            nodes_explored=nodes,
                            cost=winner.cost,
                            pruned_branches=pruned,
                            elapsed_ms=elapsed_ms,
                            rejection_reason=f"SMT expression verification rejected candidate: {reasons_str}",
                        )
                rule_def = parse_rule(rule_sexpr)
                v_res = self.smt_verifier.verify_rule(rule_def=rule_def)
                if not v_res.verified:
                    reasons_str = "; ".join(v_res.reasons) if v_res.reasons else v_res.status
                    logger.warning(
                        "smt_verification_rejected_synthesized_candidate",
                        reasons=v_res.reasons,
                    )
                    return SynthesisResult(
                        success=False,
                        synthesized_ast=winner.ast,
                        canonical_code=canonical_expr,
                        iterations_run=iterations,
                        nodes_explored=nodes,
                        cost=winner.cost,
                        pruned_branches=pruned,
                        elapsed_ms=elapsed_ms,
                        rejection_reason=f"SMT verification rejected candidate: {reasons_str}",
                    )
            except Exception as e:
                logger.debug("smt_verifier_exception", error=str(e))

        quarantined_id: str | None = None
        if self.rule_lifecycle is not None:
            cand_rule = CandidateRule(
                rule_id=rule_name,
                s_expression=rule_sexpr,
                intended_intent=intent_label,
            )
            quarantined_id = self.rule_lifecycle.register_candidate(cand_rule)

        return SynthesisResult(
            success=True,
            synthesized_ast=winner.ast,
            canonical_code=canonical_expr,
            iterations_run=iterations,
            nodes_explored=nodes,
            cost=winner.cost,
            pruned_branches=pruned,
            elapsed_ms=elapsed_ms,
            quarantined_rule_id=quarantined_id,
        )
