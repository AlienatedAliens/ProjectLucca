# Work Order 31: Search & Safety-of-Search (v1.5.0 Cognitive Engine)

```yaml
doc_status: canonical
as_of: 2026-10-09
supersedes: []
superseded_by: []
verification: code-cited
```

**Target Release:** Project Lucca v1.5.0 Cognitive Engine Baseline  
**Prerequisites Satisfied:** WO-30 Minimum Viable Engine complete & hardened (`v1.35.8-stable`, commit `5002f8b`; 23 hardening tests; SQLite concurrency hardened; static gates: 24/24 passing).  
**Hardware Budget Constraint:** $\Delta\text{VRAM} = 0\,\text{MB}$ strictly enforced (RTX 5080 Laptop GPU dedicated 100% to LLM deliberation), Host CPU threads only (Intel Core Ultra 9 275HX 24 threads), $\Delta\text{RAM} \le 512\,\text{MB}$.

---

## 1. Architectural Purpose & Scope

Following the successful delivery of **Work Order 30** (DreamCoder macro mining, idiomaticity cost extraction, and dynamic scratchpad falsification), **Work Order 31** scales Lucca to autonomous program synthesis while establishing non-negotiable safety-of-search guards.

In autonomous neuro-symbolic program synthesis, search over combinatorial program spaces risks runaway cycles, degenerate hallucination loops, API boundary violations, and unguided branch explosion. WO-31 addresses these risks through a tightly integrated four-module architecture:

```
                      Target Specification / Goal Postcondition
                                        │
                                        ▼
                  [Module 15: Backward Abduction Solver]
                      (Inverts postconditions to preconditions;
                       generates constrained hole candidates)
                                        │
                                        ▼
                    [Module 12: AST-Hole MCTS Engine]
                  ┌────────────────────────────────────────┐
                  │ 1. Selection: UCT with cost penalty    │
                  │ 2. Expansion: Typed hole filling       │◄────┐
                  │ 3. Simulation: Fast scratchpad rollout │     │
                  │ 4. Backpropagation: Q & N updates      │     │
                  └───────────────────┬────────────────────┘     │
                                      │                          │
                   Candidate Branch   │                          │
                                      ▼                          │
                  [Module 11: Boundary Topology Parser]          │
                  (Static/dynamic contract validator; rejects    │ Prunes
                   tool signature, arity, and type breaches)     │ Branch
                                      │                          │
                                      ▼                          │
                  [Module 9: Traceback Divergence Guard]         │
                  (Cycle detector & entropy drift monitor;       │
                   prunes recurrence loops & rambling)───────────┘
                                      │
                                      ▼
                        Verified Closed Program AST
                                      │
                                      ▼
                        [Z3 SMT Verification (D-REAS-07)]
                                      │
                                      ▼
                        [RuleLifecycleManager (D-REAS-06)]
                        (Enters QUARANTINE mode; 0 to ACTIVE)
```

---

## 2. Module Specifications & Interfaces

### Module 9: Traceback Divergence Guard (`src/lucca/core/convergence.py`)
- **Foundation:** Integrates with turn convergence checks and MCTS search traces.
- **Function:** Monitors state-hash recurrence, trace edit distance / token repetition, and traceback error entropy. Detects cyclic deadlocks ($k \ge 3$ repeated states) and divergent error entropy, terminating runaway loops and pruning unproductive search branches.
- **Interface:**
  ```python
  class DivergenceReason(str, Enum):
      STATE_CYCLE = "state_cycle"
      REPETITIVE_DRIFT = "repetitive_drift"
      ERROR_ENTROPY_EXPLOSION = "error_entropy_explosion"
      TOKEN_RAMBLE_LIMIT = "token_ramble_limit"

  class DivergenceReport(BaseModel):
      diverged: bool
      reason: DivergenceReason | None
      cycle_count: int
      entropy: float
      detail: str

  class TracebackDivergenceGuard:
      def __init__(self, max_recurrence: int = 3, max_entropy_slope: float = 1.5, max_steps: int = 64) -> None: ...
      def record_step(self, state_repr: str, error_signature: str | None = None) -> DivergenceReport: ...
      def should_prune(self, history: list[str]) -> bool: ...
      def reset(self) -> None: ...
  ```

### Module 11: Boundary Topology Parser (`src/lucca/reasoning/topology.py`)
- **Foundation:** Extends structural AST validation in `src/lucca/sandbox/ast_sanitizer.py` and `src/lucca/reasoning/scheme/parser.py`.
- **Function:** Statically and dynamically validates MicroScheme expressions against registered `ToolSchema` contracts, predicate signatures (`STATE_PREDICATES`), arity constraints, and structural type invariants. Prevents search paths from emitting malformed tool calls, invalid predicate shapes, or unsafe sandbox escapes.
- **Interface:**
  ```python
  class BoundaryViolationType(str, Enum):
      TOOL_NOT_FOUND = "tool_not_found"
      ARITY_MISMATCH = "arity_mismatch"
      ARGUMENT_TYPE_MISMATCH = "argument_type_mismatch"
      FORBIDDEN_OPERATOR = "forbidden_operator"
      PREDICATE_SIGNATURE_INVALID = "predicate_signature_invalid"
      SANDBOX_BOUNDARY_BREACH = "sandbox_boundary_breach"

  class BoundaryViolation(BaseModel):
      violation_type: BoundaryViolationType
      operator: str
      detail: str
      node_canonical: str

  class TopologyValidationResult(BaseModel):
      is_valid: bool
      violations: list[BoundaryViolation]

  class BoundaryTopologyParser:
      def __init__(self, registered_tools: list[ToolSchema] | None = None) -> None: ...
      def validate_ast(self, node: SchemeNode) -> TopologyValidationResult: ...
      def check_safe_to_execute(self, node: SchemeNode) -> bool: ...
  ```

### Module 15: Backward Abduction Solver (`src/lucca/reasoning/abduction.py`)
- **Foundation:** Extends e-graph unification and pattern matching in `src/lucca/reasoning/egraph.py`.
- **Function:** Inverts target postconditions / goal assertions ($G$) to deduce required preconditions ($P$) and rank candidate hole fillings. Inverts arithmetic, relational, and spatial operations (e.g. $(= (+ a b) C) \implies a = C - b$) and resolves predicate unifications to provide goal-directed search heuristics.
- **Interface:**
  ```python
  class AbductiveHypothesis(BaseModel):
      hole_name: str
      candidate_expr: str
      preconditions: list[str]
      confidence: float
      heuristic_rank: int

  class BackwardAbductionSolver:
      def __init__(self, macro_registry: MacroRegistry | None = None) -> None: ...
      def invert_goal(self, goal_expr: SchemeNode, sketch: SchemeNode) -> list[AbductiveHypothesis]: ...
      def derive_preconditions(self, target_postcondition: SchemeNode) -> list[SchemeNode]: ...
  ```

### Module 12: AST-Hole MCTS Engine (`src/lucca/reasoning/mcts.py`)
- **Foundation:** Integrates MicroScheme AST representation, `SchemeEvaluator`, `IdiomaticityCostExtractor`, `TracebackDivergenceGuard`, `BoundaryTopologyParser`, and `BackwardAbductionSolver`.
- **Function:** Multi-threaded CPU Monte Carlo Tree Search over MicroScheme S-expression holes (`(?hole <name> [type])`). Evaluates nodes using UCT penalized by structural cost ($\text{Cost}(T)$), guided by abductive proposals, bounded by topology checks, and protected against divergence loops.
- **Interface:**
  ```python
  class MCTSConfig(BaseModel):
      max_iterations: int = 500
      max_depth: int = 8
      max_expansion_candidates: int = 16
      cpu_threads: int = 8
      c_puct: float = 1.414
      cost_weight: float = 0.25
      timeout_seconds: float = 5.0

  class SynthesisResult(BaseModel):
      success: bool
      synthesized_ast: SchemeNode | None
      canonical_code: str | None
      iterations_run: int
      nodes_explored: int
      cost: float
      elapsed_ms: float
      quarantined_rule_id: str | None = None

  class ASTHoleMCTSEngine:
      def __init__(self, config: MCTSConfig | None = None, ...) -> None: ...
      def synthesize(self, sketch_with_holes: SchemeNode, goal: SchemeNode, test_cases: list[dict[str, object]]) -> SynthesisResult: ...
  ```

---

## 3. Explicit Invariants & Boundary Contracts

1. **`D-AUD-01` (Zero-`Any` Invariant):** All public and internal type signatures in `convergence.py`, `topology.py`, `abduction.py`, and `mcts.py` must contain strictly zero `Any` types, enforced by `tests/test_static_gates.py`.
2. **`D-AUD-13` (Container Sandboxing):** Test cases involving environment or shell operations run strictly inside containerized sandboxes; pure MicroScheme AST evaluation runs in-process with strict gas limits.
3. **`D-REAS-05` (Bounded Complexity):** MCTS tree depth is bounded to $\le 8$, and synthesized expressions must not exceed max execution steps ($\le 64$).
4. **`D-REAS-06` (Quarantine-Only Induction):** Newly synthesized closed rules are staged exclusively in `QUARANTINE` mode within `RuleLifecycleManager`. Exactly zero rules auto-promote to `ACTIVE`.
5. **`D-REAS-07` (Z3 SMT Verification):** Synthesized expressions pass Z3 SMT non-tautology and satisfiability checks before admission to quarantine.
6. **Hardware Budget:** CPU threads only (Intel Core Ultra 9 275HX), $\Delta\text{VRAM} = 0\,\text{MB}$, $\Delta\text{RAM} \le 512\,\text{MB}$.

---

## 4. Pre-Registered Acceptance Gates

### Divergence Guard Gate (`G-WO31-GUARD`)
- Divergence guard detects state-hash cycles ($k \ge 3$) and error entropy explosion.
- Aborts loops and prunes branches with explicit structured reason and zero unhandled exceptions.

### Boundary Topology Gate (`G-WO31-TOPOLOGY`)
- Boundary parser validates ASTs against registered tool schemas and state predicates.
- Rejects undeclared tools, arity mismatches, forbidden shell operations, and invalid argument shapes prior to execution.

### Backward Abduction Gate (`G-WO31-ABDUCTION`)
- Solver inverts target assertions into valid candidate expressions and preconditions.
- Successfully resolves arithmetic and predicate inversions to guide hole candidates.

### Autonomous Search Gate (`G-WO31-SEARCH`)
- MCTS engine discovers valid fillings for typed AST holes across multi-threaded CPU workers.
- Yields closed, syntactically and semantically valid MicroScheme programs passing test cases within budget.

### Paired Comparison Gate (`G-WO31-PAIRED`)
- Evaluates the 43 labeled Bucket C reasoning failure items (`handover/WORKORDER_29.md` §6).
- Compares Engine-OFF (frozen LLM failure state) vs. Engine-ON (MCTS + safety guards).
- Confirms non-zero task resolutions under strict CAS grading while preserving 0 VRAM delta and quarantine invariants.
