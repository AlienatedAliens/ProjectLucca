# Findings — REAS (`src/lucca/reasoning/**`)

**Subtask:** S2e · **Method:** static line-by-line · **Baseline:** HEAD `ed14f6b` + working tree per `03_BASELINE.md`, delta in [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) (reasoning modules: **unchanged since S0**) · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; every finding cites `file:line` in the current tree. Core/brain/mem/rout findings cross-referenced by ID.

**Severity totals: S0 = 1 · S1 = 0 · S2 = 3 · S3 = 8 · S4 = 1 · total = 13.**

---

## 1. Module map

Coverage from `docs/audit/evidence/S1_14_coverage.txt` rows 43–49. LOC = non-blank lines (S0 metric, verified unchanged by `03b_BASELINE_DELTA.md`).

| File | LOC | Public symbols | Responsibilities (as-built) | Live callers in product path? | Outbound dependencies | Cov % | Tests exercising it |
|---|---:|---|---|---|---|---:|---|
| `reasoning/lifecycle.py` | 234 | `RuleStatus`, `RegressionCase`, `ManagedRule`, `compute_cluster_id`, `plans_match`, `RuleLifecycleManager` (`register_rule`, `record_shadow`, `user_retire`, `verify_regression_suite`, `promote_if_eligible`) | Rule promotion state machine (PROPOSED→QUARANTINE→ACTIVE→DEMOTED/RETIRED); ≥ 5 clusters / 0 failures / regression-suite gate; in-memory only | **no** — no construction site in `src/` (F-CORE-003 family; F-REAS-003) | `scheme.eval`, `scheme.parser`, `scheme.validator`, `core.schemas` | 82 % | `tests/test_lifecycle.py` |
| `reasoning/scheme/lexer.py` | 105 | `Token`, `TokenType`, `MAX_SOURCE_BYTES`, `MAX_TOKENS`, `tokenize` | Regex lexer with 8 KiB source / 2 000-token caps; string unescaping; line/col tracking | **yes** (via `parse_rule`) — `ui/settings_dialog.py:69,1492,1502` validates rule source in the rule editor | `core.exceptions` | 81 % | `tests/test_scheme.py` |
| `reasoning/scheme/parser.py` | 331 | `Symbol`, `Keyword`, `SchemeAtom/Node`, `ALLOWED_OPS`, `STATE_PREDICATES`, `RULE_ID_REGEX`, `RuleDefinition`, `Parser`, `to_canonical`, `parse`, `has_state_predicate`, `parse_rule` | AST parser with op whitelist, depth cap 32, `define` ban; canonical serializer; strict rule-form validation | **yes** — `parse_rule` is the **only live REAS symbol** (UI rule-editor syntax check); everything else unwired | `lexer`, `core.exceptions` | 87 % | `tests/test_scheme.py` |
| `reasoning/scheme/eval.py` | 197 | `SchemeEvaluator`, `DEFAULT_GAS_LIMIT=1000`, `DEFAULT_TIMEOUT_MS=20.0`, `build_env`, `evaluate_expr`, `evaluate_rule` | Tree-walking evaluator with gas + 20 ms timeout; `and`/`or`/`if` special forms; strict primitive dispatch; `RuleOutcome` assembly | **no** — no caller outside `reasoning/` | `prims`, `parser`, `core.schemas`, `core.exceptions` | 75 % | `tests/test_scheme.py` |
| `reasoning/scheme/prims.py` | 326 | `INT_MAX/MIN`, `MAX_STR_LEN=4096`, `MAX_LIST_LEN=256`, 15 pure primitives, `make_state_primitives` (11 state predicates), `PURE_PRIMITIVES` | Checked arithmetic (i64 bounds, non-finite), string/list caps, state predicates, plan constructors (`list`/`say`/`tool`) | **no** (via `evaluate_*` only) | `fnmatch`, `core.schemas`, `core.exceptions` | **43 %** | barely (`test_scheme.py` touches a few) |
| `reasoning/scheme/validator.py` | 116 | `_generate_test_states`, `validate_rule_static`, `_validate_plan_tools` | Static validation: parse, uniqueness, registered-tool + kwarg/required checks, 20 synthetic fixture evaluations | **no** — called from `lifecycle.register_rule` only (unwired) | `random`, `eval`, `parser`, `core.schemas` | 88 % | `tests/test_scheme.py` (partially) |
| `reasoning/scheme/__init__.py` | 33 | re-exports | Package surface | — | — | 100 % | — |

**Wiring verdict:** the only live symbol in the area is `parse_rule`, used by the UI rule editor for syntax validation (`settings_dialog.py:69,1492,1502`). The lifecycle state machine, evaluator, primitives, and validator are **dead in the product path** — no executor constructs `RuleLifecycleManager`, no code calls `evaluate_rule` per turn, and `RuleEnginePort.evaluate(state, mode)` (`ports.py:84-86`) has no implementation (F-CORE-003 family; REAS-side pin in F-REAS-003). Consequence: the Charter §5.3 promotion gate (≥ 5 distinct clusters, 0 failures, 100 % regression pass) — the audit'sInvariant 4 — is enforced by a state machine that no real signal can ever reach.

## 2. As-built behaviour

### 2.1 Promotion state machine (`lifecycle.py`)

- **States:** `PROPOSED → QUARANTINE → ACTIVE → (DEMOTED declared but never assigned — same pattern as core's `postturn`/`degraded`, cf. core.md §3.1) → RETIRED`. `DEMOTED` appears in the `RuleStatus` Literal (`:25`) but no code ever assigns it — demotion goes straight to `QUARANTINE` (`:155`) or `RETIRED` (`:149`).
- **Cluster IDs:** `sha1(f"{session_id}|{floor(ts/900)}|{semantic_cluster}")` — 15-minute buckets (`:54-62`).
- **QUARANTINE shadow:** matched → add cluster + snapshot; unmatched → `failure_count += 1`, `≥ 3 → RETIRED` (`:131-140`). Promotion requires `len(success_clusters) ≥ 5` AND `failure_count == 0` AND regression suite clean (`:223-244`) — matching Charter §5.3 invariant 4 exactly.
- **ACTIVE failure:** `demotion_count += 1`; `≥ 2 → RETIRED`, else demote to QUARANTINE and reset counters (`:142-155`).
- **Regression suite:** owning rule must reproduce its captured plan; no other ACTIVE rule may newly fire on a case (`:165-209`). Cases are captured from quarantine snapshots at promotion time (`:251-259`).
- **Persistence: none.** `ManagedRule` and `RegressionCase` live in dicts/lists in memory; no DB table exists (migration `0001/0002` have no rules tables; TM-11's `rule_evaluations` surface is absent — F-REAS-002).

### 2.2 Evaluator (`eval.py`)

Gas (1 per node, limit 1000) + wall-clock timeout (20 ms, `perf_counter` — the one place in the codebase using the correct clock for a latency budget, cf. F-CORE-008) checked per node (`:43-50`). `and`/`or` short-circuit with Scheme truthiness (only `#f` is false, `:78-98`); strict primitive dispatch with `Keyword` args passed through unevaluated (`:111-116`); primitive exceptions wrapped into `SchemeRuntimeError` with rule_id/form/cause_type (`:118-128`). `evaluate_rule` returns a total `RuleOutcome` (never raises): **plan-evaluation errors after a successful `:when` are collapsed to `fired=False`** (`:178-224` — F-REAS-004).

### 2.3 Primitives (`prims.py`)

Arithmetic with i64 overflow checks and non-finite rejection; `MAX_STR_LEN=4096`, `MAX_LIST_LEN=256`; 11 state predicates bound per-`RuleState` with a no-shadowing env merge (`eval.py:138-149`). Notable behaviours: `hour-between?` is a plain chained comparison — overnight windows impossible (`:276-283`, F-REAS-006); `len` applies the 256 list cap to strings that `_check_str` allows up to 4096 (`:177-192`, F-REAS-007); `entity` returns `""` when the category is empty, and `""` is truthy in this evaluator (`:247-252` + `eval.py:53`, F-REAS-008); `tool` constructs `ToolCall` with a `uuid4` call_id at evaluation time (`:373`).

### 2.4 Validator (`validator.py`)

`validate_rule_static`: parse → uniqueness → registered-tool/kwargs/required checks (`:100-132`) → evaluate `:when` and `:plan` against 20 deterministic synthetic `RuleState` fixtures (`random.Random(42)`, `:20-59`). The docstring's step 5, "Non-constant-true :when predicate check" (`:73`), **has no implementation** (F-REAS-005). Fixtures use hard-coded transcripts (`"sample transcript {i}"`), an apps list containing non-whitelisted `"code"`, and always-present file entities (`:31-41`) — F-REAS-009.

---

## 3. Findings

Ordered by severity, then by ID. Every finding re-reviewed per Charter §3.5 (log in §7); `Status: OPEN`.

### F-REAS-001 — `Any` in the evaluator's public interface (`evaluate_expr -> Any`, `SchemeEvaluator.eval -> Any`, `build_env`)

| Field | Value |
|---|---|
| **ID** | F-REAS-001 |
| **Title** | `Any` in the evaluator's public interface (`evaluate_expr -> Any`, `SchemeEvaluator.eval -> Any`, `build_env`) |
| **Severity** | S0 — Critical |
| **Category** | INVARIANT |
| **Location** | `src/lucca/reasoning/scheme/eval.py:43`; `src/lucca/reasoning/scheme/eval.py:138`; `src/lucca/reasoning/scheme/eval.py:152-158`; `src/lucca/reasoning/scheme/prims.py` (all 27 primitives typed `list[Any]`) |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/scheme/eval.py:152-158`
```python
def evaluate_expr(
    expr: SchemeNode,
    state: RuleState | None = None,
    gas_limit: int = DEFAULT_GAS_LIMIT,
    timeout_ms: float = DEFAULT_TIMEOUT_MS,
    rule_id: str | None = None,
) -> Any:
```
`src/lucca/reasoning/scheme/eval.py:43`
```python
    def eval(self, node: SchemeNode, env: dict[str, Callable[[list[Any]], Any]]) -> Any:
```
(and every primitive in `prims.py`: `def prim_add(args: list[Any]) -> int | float:` etc.)

**What is wrong / assumed / missing**

The evaluator's public surface is typed with `Any` in both parameter and return positions. A Scheme evaluator is dynamically typed *internally*, but the value domain is closed and enumerable: `bool | int | float | str | list[SchemeValue] | Say | ToolCall` — exactly the `SchemeNode` atom set plus plan objects. A `SchemeValue = SchemeAtom | list["SchemeValue"] | Say | ToolCall` alias would type the whole pipeline without changing a line of behaviour. Graded per D-AUD-01 (§5.5 governs; S0 for public interfaces) consistently with F-CORE-001 and F-BRAIN-001.

**Why it matters**

Charter §5 invariant 5. Practical: `evaluate_expr` is the boundary through which future rule-engine consumers receive values; `Any` propagates into whatever consumes the result, defeating the mypy-strict gate precisely at the subsystem whose whole purpose is deterministic, validated plans.

**Questions this raises**

1. None — the closed value domain makes the remediation mechanical.

**Proposed remediation**

1. In `src/lucca/reasoning/scheme/parser.py`: add `SchemeValue: TypeAlias = "SchemeAtom | list[SchemeValue] | Say | ToolCall"` (import `Say`/`ToolCall` from `core.schemas`).
2. In `src/lucca/reasoning/scheme/eval.py`: change `SchemeEvaluator.eval(...) -> Any` to `-> SchemeValue`, `build_env(...) -> dict[str, Callable[[list[SchemeValue]], SchemeValue]]`, `evaluate_expr(...) -> SchemeValue`; retype all 27 primitives in `prims.py` from `list[Any]` to `list[SchemeValue]` (internal narrowing via the existing `_check_*` helpers).
3. Extend the static gate from F-CORE-001 step 5 to `src/lucca/reasoning/**`.

**Verification test**

- **Tier:** T0
- **Input:** `uv run ruff check src/lucca/reasoning --select ANN401 && uv run mypy --strict src/lucca/reasoning`
- **Expected output:** 0 findings; mypy success
- **Threshold:** n/a — boolean
- **Command:** `uv run ruff check src/lucca/reasoning --select ANN401 && uv run mypy --strict src/lucca/reasoning`

**Cross-references:** F-CORE-001, F-BRAIN-001, F-CORE-054

---

### F-REAS-002 — Rule state machine has no persistence: every restart forgets all rules, snapshots, and regression cases

| Field | Value |
|---|---|
| **ID** | F-REAS-002 |
| **Title** | Rule state machine has no persistence: every restart forgets all rules, snapshots, and regression cases |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/reasoning/lifecycle.py:91-94`; `src/lucca/memory/migrations/0001_init.sql` (no rules tables); `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/12_threat_model.md:31` (TM-11 lists `rule_evaluations`) |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/lifecycle.py:92-94`
```python
        self.registered_tools = registered_tools or {}
        self.rules: dict[str, ManagedRule] = {}
        self.regression_cases: list[RegressionCase] = []
```
(a repo-wide search finds no rules/rules_evaluations table in either migration; TM-11 names `rule_evaluations` as an audit surface.)

**What is wrong / assumed / missing**

The promotion state machine — whose entire value is accumulated evidence over real usage (≥ 5 distinct clusters across 15-minute buckets, 0 failures) — stores everything in process memory. A supervisor restart (which the current shutdown makes likely, F-CORE-005/006) erases every rule including ACTIVE ones and their regression suites. The `decisions` table survives (router-side, F-ROUT-001), but the rule layer it is supposed to feed has no storage.

**Why it matters**

Once wired (F-REAS-003), every restart resets rule learning to zero: cluster evidence can never reach 5 across a session boundary unless the process lives long enough — on a 16 GB host with the observed restart fragility, that means the promotion gate can realistically never be satisfied by real usage.

**Questions this raises**

1. None — persistence is implied by the spec's cluster semantics (15-minute buckets across sessions).

**Proposed remediation**

1. Add migration `0003_rules.sql` with `rule_states(rule_id PK, status, source_canonical, source_hash, success_clusters_json, failure_count, demotion_count, created_at, promoted_at, demoted_at, retired_at, user_retired)` and `regression_cases(case_id PK, rule_id, state_json, expected_plan_json, captured_at, stale)`; add `RuleLifecycleManager.load(db)` / `persist(rule_id)` called on register/shadow/promote/retire.
2. Add `tests/test_lifecycle.py::test_rules_survive_restart`: promote a rule through 5 clusters, construct a fresh manager on the same DB, assert the rule is ACTIVE with its cases.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** state restored; regression suite intact
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_lifecycle.py::test_rules_survive_restart -q`

**Cross-references:** F-REAS-003, F-CORE-003, F-CORE-005

---

### F-REAS-003 — No executor implements `RuleEnginePort`; nothing feeds `record_shadow` — the promotion gate can never see a real cluster

| Field | Value |
|---|---|
| **ID** | F-REAS-003 |
| **Title** | No executor implements `RuleEnginePort`; nothing feeds `record_shadow` — the promotion gate can never see a real cluster |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/ports.py:84-86`; `src/lucca/reasoning/lifecycle.py:113-155`; `src/lucca/core/orchestrator.py` (no rule-engine import) |
| **Status** | OPEN |

**Evidence**

`src/lucca/ports.py:84-86`
```python
    def evaluate(
        self, state: RuleState, *, mode: Literal["shadow", "active"]
    ) -> list[RuleOutcome]: ...
```
(a repo-wide search finds `record_shadow` called only in `tests/test_lifecycle.py`; no class implements `RuleEnginePort`; `RuleLifecycleManager` has no `evaluate` method at all.)

**What is wrong / assumed / missing**

The REAS-side half of the F-CORE-003 unwiring, pinned for this area: the port declares shadow/active evaluation over a `RuleState`; the lifecycle manager offers `record_shadow` but no evaluate; and no turn-loop code constructs either. Even if the router (F-ROUT-001) and memory (F-CORE-003) were wired tomorrow, the rule layer has no execution path: no component builds a `RuleState` per turn, evaluates registered rules, executes the winning plan through the confirmation flow, or reports matched/unmatched back to `record_shadow`.

**Why it matters**

Charter §5.3 invariant 4 (promotion gate) and §5.3's "≥ 1 rule promoted from real/replayed usage" human gate are enforced by machinery that real signals cannot reach — same structural family as F-ROUT-001 and F-MEM-007.

**Questions this raises**

1. None — the wiring plan is the F-CORE-003 remediation; this finding pins the REAS-side inventory.

**Proposed remediation**

1. In `src/lucca/reasoning/lifecycle.py`: add `evaluate(self, state: RuleState, *, mode: Literal["shadow", "active"]) -> list[RuleOutcome]` implementing `RuleEnginePort` — evaluate QUARANTINE rules in shadow mode (recording via `record_shadow` with `compute_cluster_id`), ACTIVE rules in active mode ranked by `priority`.
2. In `src/lucca/core/orchestrator.py` (CORE-area change, joint with F-CORE-003): build the per-turn `RuleState` from the ASR transcript/entities and call the engine before the LLM path (Spec 06 §1 DISPATCH).
3. Add `tests/test_lifecycle.py::test_evaluate_shadow_records_clusters` (T2): wired turn with a quarantined rule matching → `success_clusters` grows by one deterministic cluster id.

**Verification test**

- **Tier:** T2
- **Input:** the test above
- **Expected output:** cluster recorded; outcome list returned in port shape
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_lifecycle.py::test_evaluate_shadow_records_clusters -q`

**Cross-references:** F-CORE-003, F-REAS-002, F-ROUT-001

---

### F-REAS-004 — `evaluate_rule` collapses a fired rule's plan-evaluation error into `fired=False`

| Field | Value |
|---|---|
| **ID** | F-REAS-004 |
| **Title** | `evaluate_rule` collapses a fired rule's plan-evaluation error into `fired=False` |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/reasoning/scheme/eval.py:178-224` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/scheme/eval.py:178-183`
```python
    try:
        when_result = evaluator.eval(rule.when_expr, env)
        fired = when_result is not False

        plan: Plan | None = None
        if fired:
            raw_plan = evaluator.eval(rule.plan_expr, env)
```
(outer handler at `:215-224` returns `RuleOutcome(fired=False, plan=None, error=str(e))` for **any** `SchemeError` — including one raised while evaluating an already-fired rule's plan.)

**What is wrong / assumed / missing**

When `:when` succeeds but `:plan` raises (gas exhausted mid-plan, timeout, bad primitive), the outcome reports `fired=False` — the rule's match signal is destroyed and the error survives only as a string. A consumer that treats `fired` as "the rule matched the state" (which `record_shadow(rule_id, matched=...)` requires, `lifecycle.py:113-127`) will book the turn as a non-match: a *systematically broken* rule (e.g. one whose plan always times out) looks identical to a rule that never matches, and the distinction the `error` field carries is not part of any decision path. Expected: `RuleOutcome` carries `fired=True` with `plan=None, error=...` (or a distinct `errored` flag) so shadow recording can count it as a failure *of a firing rule*.

**Why it matters**

Once wired (F-REAS-003), gas/timeout-prone plans — the exact failure mode the 20 ms/1000-gas guards exist for — would silently suppress match statistics instead of surfacing broken rules; demotion decisions (lifecycle `:142-155`) would then act on distorted evidence.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/core/schemas.py`: add `errored: bool = False` to `RuleOutcome` (or widen `fired` to a tri-state).
2. In `src/lucca/reasoning/scheme/eval.py`: wrap only the `:plan` evaluation separately — on `SchemeError` return `RuleOutcome(fired=True, plan=None, errored=True, error=...)`. Before: fired-signal lost. After: preserved.
3. In `src/lucca/reasoning/lifecycle.py`, `record_shadow`: treat `errored` outcomes as `matched=False` (failure) — preserving current demotion semantics while keeping the signal.
4. Add `tests/test_scheme.py::test_plan_error_preserves_fired`: a rule with a valid `:when` and a gas-bomb `:plan` → outcome `fired=True, errored=True`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** `fired=True`, `errored=True`, `plan=None`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_scheme.py::test_plan_error_preserves_fired -q`

**Cross-references:** F-REAS-003, F-REAS-010

---

### F-REAS-005 — Validator docstring's "non-constant-true :when predicate check" is unimplemented

| Field | Value |
|---|---|
| **ID** | F-REAS-005 |
| **Title** | Validator docstring's "non-constant-true :when predicate check" is unimplemented |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/reasoning/scheme/validator.py:73,77-97` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/scheme/validator.py:72-75`
```python
    3. Op whitelist validation.
    4. Registered tool checks and kwarg validation.
    5. Non-constant-true :when predicate check.
    6. Evaluation against 20 random RuleState fixtures.
```
(`validate_rule_static` body (`:77-97`) performs parse → uniqueness → plan tools → fixture evaluation; no constant-true check exists anywhere in the module.)

**What is wrong / assumed / missing**

A rule whose `:when` is constant-true given any state — e.g. `(or (intent= "launch_app") #t)` — passes static validation: `parse_rule` only requires *at least one* state predicate somewhere in the tree (`parser.py:332-333`), and the 20 synthetic fixtures only catch *runtime errors*, not always-true expressions. Such a rule would fire on every turn once wired, winning by priority and starving all other rules. The docstring claims the check; it does not exist.

**Why it matters**

The static validator is the front line of TM-10 ("malicious rule synthesised") — a prompt-injected or hallucinated rule that always fires is the cheapest attack on the plan path, and the claimed control is absent.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/scheme/validator.py`, after the fixture loop: evaluate `:when` across the 20 fixtures and reject if it returned a non-False value for **all** of them AND the expression contains no state predicate outside a negation — simplest sound version: `if all(evaluate_expr(rule.when_expr, fx) is not False for fx in test_fixtures): raise RuleError("':when' is constant-true across validation fixtures")`. Before: claimed only. After: enforced.
2. Add `tests/test_scheme.py::test_constant_true_when_rejected`: `(or (intent= "launch_app") #t)` → `RuleError`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** `RuleError` raised
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_scheme.py::test_constant_true_when_rejected -q`

**Cross-references:** F-REAS-009, F-REAS-003

---

### F-REAS-006 — `hour-between?` cannot express overnight windows

| Field | Value |
|---|---|
| **ID** | F-REAS-006 |
| **Title** | `hour-between?` cannot express overnight windows |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/reasoning/scheme/prims.py:276-283` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/scheme/prims.py:283`
```python
        return h1 <= state.hour_local <= h2
```

**What is wrong / assumed / missing**

A chained comparison cannot represent a window that crosses midnight: `(hour-between? 22 6)` (22:00–06:59, the canonical "quiet hours" rule) is always False because `22 <= h <= 6` is unsatisfiable. The natural rules for a desktop companion (quiet-hours behaviour, work-hours gating) are exactly the overnight ones.

**Why it matters**

Silently always-false predicate: rules written with an overnight window never fire, and nothing at validation time (the 20 fixtures do cover hours 0–23, so no error surfaces) or runtime flags it.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/scheme/prims.py:276-283`: implement wrap-around — `return h1 <= h2 ? (h1 <= state.hour_local <= h2) : (state.hour_local >= h1 or state.hour_local <= h2)`; validate `0 ≤ h ≤ 23` for both args.
2. Add `tests/test_scheme.py::test_hour_between_overnight`: state hour 2, `(hour-between? 22 6)` → True; hour 12 → False.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** overnight window semantics
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_scheme.py::test_hour_between_overnight -q`

**Cross-references:** F-REAS-009

---

### F-REAS-007 — `len` applies the 256-element list cap to strings that `_check_str` allows up to 4096 chars

| Field | Value |
|---|---|
| **ID** | F-REAS-007 |
| **Title** | `len` applies the 256-element list cap to strings that `_check_str` allows up to 4096 chars |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/reasoning/scheme/prims.py:177-192` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/scheme/prims.py:183-189`
```python
    if isinstance(val, (str, list)):
        length = len(val)
        if length > MAX_LIST_LEN:
            raise SchemeRuntimeError(
                f"'len' exceeds maximum element count {MAX_LIST_LEN}", cause_type="OverflowError"
            )
        return length
```
(`MAX_STR_LEN = 4096` governs `str-contains?`/`str-lower`; `MAX_LIST_LEN = 256` governs `list`.)

**What is wrong / assumed / missing**

A 1000-character transcript-derived string is legal input to `str-contains?` but `(len s)` on it raises `OverflowError` — the same value is accepted by one primitive and rejected by another, with an error message that says "element count" about a string. Expected: strings bounded by `MAX_STR_LEN` in `len`, lists by `MAX_LIST_LEN`.

**Why it matters**

Inconsistent limits produce rules that work in the editor (short samples) and fail at runtime on real transcripts — the exact fixture-vs-reality gap F-REAS-009 documents.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/scheme/prims.py:183-189`: split the branch — strings check `length > MAX_STR_LEN`, lists keep `MAX_LIST_LEN`. Before: 256 cap on both. After: per-type caps.
2. Add `tests/test_scheme.py::test_len_string_limit_uses_str_cap`: `(len <1000-char string>)` → 1000, no error.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** length returned; no overflow
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_scheme.py::test_len_string_limit_uses_str_cap -q`

**Cross-references:** F-REAS-009

---

### F-REAS-008 — `entity` returns `""` when the category is empty, and `""` is truthy in this evaluator

| Field | Value |
|---|---|
| **ID** | F-REAS-008 |
| **Title** | `entity` returns `""` when the category is empty, and `""` is truthy in this evaluator |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/reasoning/scheme/prims.py:247-252`; `src/lucca/reasoning/scheme/eval.py:53,92-98` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/scheme/prims.py:251-252`
```python
        ents = state.entities.get(cat, [])
        return ents[0] if ents else ""
```
(`eval.py:53`: atoms return as-is; `eval.py:94`: `if cond is not False:` — only `#f` is false, so `""` is truthy.)

**What is wrong / assumed / missing**

The natural rule shape `(if (entity "app") (tool …) …)` intends "if an app entity exists" — but `entity` returns `""` when absent and `""` is truthy, so the else branch is unreachable: the rule fires with an empty entity. The correct idiom is `(entity-has? "app" "")`… which is also wrong (`"" in [...]` is False — actually `entity-has?` requires 2 args and checks membership of a *value*). There is no truthiness-safe "has any entity" primitive. Expected: `entity` returns `#f` when absent (Scheme-idiomatic), or an `entity-any?` predicate exists.

**Why it matters**

A truthiness trap in the plan-selection path: rules authored the obvious way fire unconditionally with an empty entity, and `plans_match`-captured regression snapshots would encode the empty-entity behaviour as correct.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/scheme/prims.py:247-252`: return `False` when the category is empty. Before: `""` (truthy). After: `#f` (falsy), Scheme-idiomatic.
2. Add `tests/test_scheme.py::test_entity_absent_is_falsy`: state with no `app` entities → `(if (entity "app") 1 2)` evaluates to `2`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** `2`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_scheme.py::test_entity_absent_is_falsy -q`

**Cross-references:** F-REAS-009

---

### F-REAS-009 — Validator fixtures are synthetic and biased: transcripts never contain real words, apps include non-whitelisted `"code"`, file entities always exist

| Field | Value |
|---|---|
| **ID** | F-REAS-009 |
| **Title** | Validator fixtures are synthetic and biased: transcripts never contain real words, apps include non-whitelisted `"code"`, file entities always exist |
| **Severity** | S3 — Low |
| **Category** | TESTING |
| **Location** | `src/lucca/reasoning/scheme/validator.py:20-59` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/scheme/validator.py:45-46`
```python
                transcript=f"sample transcript {i}",
                transcript_lower=f"sample transcript {i}",
```
(also `:31` `apps = ["calculator", "notepad", "terminal", "browser", "code"]` — `"code"` is not in `tool_whitelist.toml`; and `:40` `entities = {"app": …, "file": [f"doc_{i}.txt"]}` — the file category is never empty.)

**What is wrong / assumed / missing**

The 20 static-validation fixtures exercise only the shape of a rule, not its semantics: `transcript-has?`/`transcript-matches-glob?` rules evaluate against `"sample transcript N"` (so any real-word pattern — the only kind users write — gets zero discrimination); the `"code"` app normalises a non-whitelisted app into validation (F-ROUT-003's lexicon drift, propagated); and always-present file entities make `entity`/`entity-has?` file rules look constantly-true in validation and differently-behaved in reality.

**Why it matters**

Static validation is the TM-10 front line; fixtures that cannot distinguish a working rule from a broken one give the check its green without meaning. Combined with F-REAS-005 (the missing constant-true check) the validator's real power is "does it parse and type-check".

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/scheme/validator.py:20-59`: derive the fixture corpus from reality — transcripts drawn from `tests/fixtures/router/router_fixtures.jsonl` (already exists, 135 records), apps from `config/tool_whitelist.toml` aliases, and per-fixture randomised presence/absence of file entities.
2. Add `tests/test_scheme.py::test_fixtures_cover_transcript_matching`: a rule with `(transcript-has? "open")` must evaluate False on at least one fixture (proves discrimination).

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** discrimination present; no non-whitelisted apps in fixtures
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_scheme.py::test_fixtures_cover_transcript_matching -q`

**Cross-references:** F-REAS-005, F-ROUT-003

---

### F-REAS-010 — QUARANTINE zombie state: a rule with 1–2 failures is unpromotable but never retired, with no TTL

| Field | Value |
|---|---|
| **ID** | F-REAS-010 |
| **Title** | QUARANTINE zombie state: a rule with 1–2 failures is unpromotable but never retired, with no TTL |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/reasoning/lifecycle.py:136-140,216-235` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/lifecycle.py:137-140`
```python
            else:
                rule.failure_count += 1
                if rule.failure_count >= 3:
                    rule.status = "RETIRED"
```
(promotion requires `failure_count == 0` at `:230-235`; nothing else transitions a QUARANTINE rule with 1–2 failures.)

**What is wrong / assumed / missing**

A quarantined rule that accumulates 1 or 2 failures enters a permanent zombie state: it can never satisfy the `failure_count == 0` promotion criterion, but it also never reaches the 3-failure retirement — it sits in `QUARANTINE` indefinitely (in memory only today, F-REAS-002; indefinitely once persisted), still evaluated in shadow mode every turn. Expected: failure_count ≥ 1 in quarantine → either retire immediately (strictest reading of "0 failures") or provide a TTL/reset path; the current 3-strike threshold creates a dead zone.

**Why it matters**

Zombie rules consume shadow evaluations forever and — once persisted (F-REAS-002) — accumulate as unbounded rows; the state machine's own invariant ("QUARANTINE requires 0 failures") is violated by the state machine's retention of such rules.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/lifecycle.py:136-140`: retire on the **first** quarantine failure (matches the promotion criterion's "0 failures" strictly) — or, if a tolerance is intended, document it and add `failure_count >= 1 → cannot ever promote` to `promote_if_eligible`'s reason string. Decision recorded: retire on first failure (strictest, simplest, matches the gate).
2. Add `tests/test_lifecycle.py::test_quarantine_failure_retires`: one unmatched shadow → status `RETIRED`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** `RETIRED` after one failure
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_lifecycle.py::test_quarantine_failure_retires -q`

**Cross-references:** F-REAS-002, F-REAS-011

---

### F-REAS-011 — RETIRED rules remain in `self.rules` forever, still serve as regression-case owners, and the `stale` flag is never set

| Field | Value |
|---|---|
| **ID** | F-REAS-011 |
| **Title** | RETIRED rules remain in `self.rules` forever, still serve as regression-case owners, and the `stale` flag is never set |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/reasoning/lifecycle.py:29-35,165-209` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/lifecycle.py:185-192`
```python
            if case.rule_id in self.rules:
                owner = self.rules[case.rule_id]
                outcome = evaluate_rule(owner.definition, case.state)
```
(`stale: bool = False` declared at `:35` and never assigned anywhere; retired rules are never removed from `self.rules`; `regression_cases` only ever grows.)

**What is wrong / assumed / missing**

Retirement is a status change only: the definition stays in the dict, and `verify_regression_suite`'s owner-reproduction check does not filter by status — a retired rule's cases keep being re-evaluated against it every promotion attempt (harmless while definitions are immutable, but the cases can never go stale, the list grows unboundedly across a long-lived process, and the `stale` mechanism designed for exactly this is dead code).

**Why it matters**

Unbounded growth plus dead-flag machinery; and once persisted (F-REAS-002), retired-rule cases would be materialised as permanent rows that nothing ever marks stale.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/lifecycle.py`: when a rule is retired (`:139,148,161`), mark all its `regression_cases` `stale = True` (and skip them, as `:180-181` already does). Before: flag dead, cases eternal. After: retirement retires the evidence.
2. Add `tests/test_lifecycle.py::test_retirement_marks_cases_stale`: promote (via 5 clusters), then retire via `user_retire`; assert all the rule's cases have `stale=True` and `verify_regression_suite` skips them.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** cases skipped post-retirement
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_lifecycle.py::test_retirement_marks_cases_stale -q`

**Cross-references:** F-REAS-002, F-REAS-010

---

### F-REAS-012 — Promotion conflict check ignores other QUARANTINE rules: two pending rules can both promote onto overlapping states

| Field | Value |
|---|---|
| **ID** | F-REAS-012 |
| **Title** | Promotion conflict check ignores other QUARANTINE rules: two pending rules can both promote onto overlapping states |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/reasoning/lifecycle.py:172-177,194-202` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/lifecycle.py:173-177`
```python
        active_rules = [r for r in self.rules.values() if r.status == "ACTIVE"]
        if candidate_rule_id and candidate_rule_id in self.rules:
            cand = self.rules[candidate_rule_id]
            if cand not in active_rules:
                active_rules.append(cand)
```
(the conflict loop at `:195-202` evaluates only `active_rules` — other QUARANTINE rules are invisible to the candidate's promotion check.)

**What is wrong / assumed / missing**

Two quarantined rules whose `:when` clauses overlap on the same states (the normal case for sibling rules authored around the same intent) each pass promotion independently — the conflict is discovered only *after* both are ACTIVE, as active-failure noise (demotions per F-REAS-010's counters) rather than at the gate. Expected per Spec 05 §9's "no other rule fires on it" intent: the check should span ACTIVE **and** QUARANTINE candidates so promotion serialises overlapping rules.

**Why it matters**

The regression suite is the mechanism that guarantees a clean active set; skipping same-state quarantined peers defers conflict detection to live-failure signals — the slowest, most user-visible possible detection.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/lifecycle.py:173`: include QUARANTINE rules in the conflict-check set — `active_rules = [r for r in self.rules.values() if r.status in ("ACTIVE", "QUARANTINE")]`, keeping the owner-reproduction filter unchanged (owner cases only consult `case.rule_id`).
2. Add `tests/test_lifecycle.py::test_promotion_conflicts_with_quarantine_peer`: two overlapping quarantined rules; promoting the second fails with "Conflicting rule … unexpectedly fired".

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** second promotion rejected
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_lifecycle.py::test_promotion_conflicts_with_quarantine_peer -q`

**Cross-references:** F-REAS-010

---

### F-REAS-013 — `transcript-matches-glob?` case behaviour depends on the OS via `fnmatch`'s `normcase`

| Field | Value |
|---|---|
| **ID** | F-REAS-013 |
| **Title** | `transcript-matches-glob?` case behaviour depends on the OS via `fnmatch`'s `normcase` |
| **Severity** | S4 — Info |
| **Category** | ASSUMPTION |
| **Location** | `src/lucca/reasoning/scheme/prims.py:262-268` |
| **Status** | OPEN |

**Evidence**

`src/lucca/reasoning/scheme/prims.py:267-268`
```python
        pattern = _check_str(args[0], "transcript-matches-glob?")
        return fnmatch.fnmatch(state.transcript_lower, pattern)
```

**What is wrong / assumed / missing**

The transcript is lowercased but the pattern is not, and `fnmatch.fnmatch` applies `os.path.normcase` to **both** arguments — which lowercases on Windows and is a no-op on POSIX. The same rule therefore matches `"Open*"` differently depending on the host OS. The product is Windows-only today (hardware truth, Charter §3.3), so the behaviour is currently benign — but the semantics of a rule predicate should not be a property of `os.path`.

**Why it matters**

Predicate semantics must be deterministic and platform-independent for the regression suite (captured cases re-evaluated later must produce identical results, F-REAS-002's persistence makes this cross-machine).

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/reasoning/scheme/prims.py:268`: use `fnmatch.fnmatchcase(state.transcript_lower, pattern.lower())` — explicit, platform-independent case folding. Before: OS-dependent. After: deterministic.
2. Add `tests/test_scheme.py::test_glob_case_portable`: uppercase pattern vs lowercase transcript → matches (assertion holds on any OS).

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** match regardless of platform
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_scheme.py::test_glob_case_portable -q`

**Cross-references:** F-REAS-002

---

## 4. Assumptions register

| # | Location | Assumption embedded in code | Why unverified | Risk if false |
|---|---|---|---|---|
| A-E-01 | `lifecycle.py:54-62` | 15-minute time buckets plus session id produce meaningful "distinct success clusters" | No measurement of real session cadence; a single long session yields one bucket per 15 min | Cluster gate satisfiable by one long monologue, or unsatisfiable by short sessions |
| A-E-02 | `lifecycle.py:147` | Two active failures warrant retirement (two-strikes) | Threshold is a magic number; no spec citation found | Good rules retired after unlucky barge-ins |
| A-E-03 | `eval.py:26-27` | 1000 gas / 20 ms are adequate for all legitimate rules | No measurement of real rule costs; only synthetic rules exist | Legitimate complex rules time out (silently, per F-REAS-004) |
| A-E-04 | `parser.py:85` | Kebab-case-with-version rule IDs prevent collision games | Uniqueness enforced per manager instance only (in-memory, F-REAS-002) | Re-registration across restarts with mutated semantics |
| A-E-05 | `prims.py:373` | uuid4 call_ids at evaluation time are harmless | `plans_match` ignores call_id today; any future plan diffing that includes it breaks | Regression snapshots non-reproducible byte-wise |
| A-E-06 | `validator.py:32` | `random.Random(42)` fixtures are representative | Static seed over synthetic states (F-REAS-009) | Validation green ≠ runtime-safe |
| A-E-07 | `lifecycle.py:66-68` | `plans_match(None, None) → True` is the right equality for absent plans | Only relevant if a case can capture a None plan; snapshots are only captured with both present | Edge-case label noise in the suite |

## 5. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-E-01 | Should quarantine failure tolerance be 0 (retire on first failure, F-REAS-010's recorded decision) or is a grace count intended by Spec 05 §9? | State-machine semantics; interacts with F-REAS-002 persistence | owner / architect |
| Q-E-02 | Should `DEMOTED` exist as a reachable status (it is declared, never assigned), or be deleted? | Same declared-but-unreachable pattern as core's `postturn`/`degraded` (core.md §3.1) | architect |
| Q-E-03 | When wired, does `evaluate_rule` run on the orchestrator thread (sub-10 ms claim in the system prompt) or off-thread? | 20 ms timeout vs turn budget; interacts with F-CORE-017's blocking-TTS finding | architect |

## 6. Coverage gaps

### 6.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| Constant-true `:when` rejection | Spec 05 §7 (validator docstring step 5) | none (unimplemented — F-REAS-005) |
| Rule persistence across restarts | Spec 05 §8/§9 cluster semantics | none (in-memory only — F-REAS-002) |
| Shadow/active evaluation via `RuleEnginePort` | Spec 02 / `ports.py:84-86` | none (no implementation — F-REAS-003) |
| Fired-then-plan-error outcome semantics | Spec 05 §6 | none (signal collapsed — F-REAS-004) |
| Overnight `hour-between?` windows | Spec 05 §5 predicate set | none (impossible — F-REAS-006) |
| Conflict check spanning quarantine peers | Spec 05 §9 | none (F-REAS-012) |
| `stale` regression-case lifecycle | Spec 05 §9 | none (flag dead — F-REAS-011) |
| `prims.py` primitive unit tests | Spec 05 §4 | **43 % coverage** — arithmetic overflow, string caps, and 8 of 11 state predicates untested |
| Overnight/edge fixture coverage in static validation | Spec 05 §7 | none (synthetic bias — F-REAS-009) |

### 6.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| `tests/test_lifecycle.py` (promotion tests) | Promotion gate ≥ 5 clusters / 0 failures / regression clean | In-memory clusters recorded by hand via `record_shadow`; no real signal path exists (F-REAS-003); persistence absent (F-REAS-002) |
| `tests/test_scheme.py` (evaluator tests) | Safe evaluation under gas/timeout | Happy paths; the timeout/gas branches (`eval.py:46,50`) and primitive error wrapping (`:122-128`) are in the uncovered 25 % |
| `ui/settings_dialog.py` rule editor validation (`:1492,1502`) | "Test evaluation simulates rule execution with isolated gas budgets" (UI text, `:2302`) | `parse_rule` syntax check only — no evaluation is performed despite the UI copy |

## 7. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** Reviewing F-REAS-003 (no executor) surfaced F-REAS-002 (nothing to persist even if it existed) and the `RuleOutcome` signal-loss sibling F-REAS-004 (the executor would consume outcomes, so the collapse matters). Reviewing F-REAS-005 (missing constant-true check) surfaced the fixture-bias sibling F-REAS-009 (the fixtures cannot discriminate) and the `"code"`-app whitelist drift shared with F-ROUT-003. Reviewing F-REAS-010 (zombie quarantine) surfaced the retirement hygiene sibling F-REAS-011 (dead `stale` flag) and the quarantine-peer conflict gap F-REAS-012.
2. **Unasked questions.** 3 registered (§5); answerable items resolved in findings (F-REAS-010 records the retire-on-first-failure decision; F-REAS-001's remediation defines the `SchemeValue` alias rather than deferring).
3. **Unwarranted assumptions.** The first draft of F-REAS-004 asserted "fired signal destroyed" as S2 without checking consumers — verified that `record_shadow` requires exactly a `matched` bool and no consumer reads `error` today, then graded S2 as a latent-semantics defect rather than S1. F-REAS-013 was graded S4 after confirming Windows `normcase` makes current behaviour benign (hardware truth, Charter §3.3). The `"#true"` lexer edge was verified to be a clean syntax error (lookahead), not a finding.
4. **Incomplete planning.** Every remediation names file, function, before/after, and a runnable command; the one owner-owned call (quarantine tolerance) is parked as Q-E-01 with a recorded default (retire on first failure).
5. **Architectural flaws → F-ARCH candidates.** (a) F-REAS-001/002/003 together mean the promotion-gate invariant (Charter §5.3, invariant 4) is enforced by machinery no signal can reach and no storage can survive — the strongest single F-ARCH candidate in the audit so far (with F-CORE-003/F-ROUT-001/F-MEM-007 as the same unwiring family); (b) F-REAS-004's outcome-collapse is a sibling of F-CORE-007/F-BRAIN-017 (signals collapsed at component boundaries) — recommended for the "honesty of recorded metrics" F-ARCH.

Severity re-grades during the pass: F-REAS-001 graded S0 per the ratified D-AUD-01 rule (public-interface `Any`), consistent with F-CORE-001/F-BRAIN-001; F-REAS-004 kept S2 (latent semantics, no live consumer); F-REAS-013 set S4 (benign on the shipped platform).
