# ADR-007 — Compiled rules are pure `State → Plan` functions; the orchestrator executes plans under a risk policy

**Status:** Accepted 2026-09-17 (D-13). Preserves AGENTS.md invariant #4 (N ≥ 5 distinct successes, 0 failures, 100 % regression).
**Supersedes:** docs 01/02/05 rule examples using `call-tool`, `emit-speech`, `intent-matches`, `user-authorized`, `$1.head`; the notion that a rule "executes".

## Context

Docs describe rules as "pure" yet give them `call-tool` side effects. Shadow mode ("evaluate but don't act") was undefined mechanically. Four incompatible DSLs appear across docs; `micro_scheme.py` parses none of them. Rules that call tools directly bypass the LLM *and* any user confirmation — a WRITE or LAUNCH could fire from a pattern match alone.

## Decision

1. A rule is two pure expressions over a **frozen `RuleState` snapshot** (spec 05 defines the schema — transcript, intent features, entities, time bucket, active app, last tool outcomes, session counters):
   - `when` → boolean (gas-metered, no I/O, no mutation).
   - `plan` → a list of `ToolCall{tool, args}` **data**, plus optional `say` text. No primitive in the DSL performs I/O.
2. **Evaluation modes**
   - `SHADOW` (quarantine): compute `plan`; compare structurally to what the LLM path *actually* executed this turn (`tool` names equal, `args` equal after canonicalisation, same order). Match ⇒ success; mismatch ⇒ failure; LLM path executed nothing but rule planned something (or vice-versa) ⇒ failure. No side effects ever.
   - `ACTIVE`: orchestrator receives the plan and executes it **through the same tool bridge and risk policy as LLM-originated tool calls**. Rules never get a privileged path.
3. **Risk policy** (spec 12): each registered tool has `risk ∈ {READ, WRITE, LAUNCH, NETWORK}`. READ/NETWORK-fetch plans execute immediately. WRITE/LAUNCH plans always require the spoken confirmation flow, regardless of origin (rule or LLM). A rule cannot lower a tool's risk.
4. **Regression case** = `(RuleState snapshot, expected Plan)` captured from each of the ≥ 5 shadow successes at promotion time. `verify_regression_suite(rule)` re-evaluates every stored case for **all** active rules and passes only if each produces its expected plan (and `when` is unchanged for cases where it fired). Vacuous `return True` is forbidden; a rule with zero regression cases cannot be promoted.
5. **Conflict resolution** when several active rules fire: most-specific `when` (more conjuncts) → earliest promoted → if still tied, do not act; fall through to LLM and log `RULE_CONFLICT`.
6. **Lifecycle:** `PROPOSED → QUARANTINE → ACTIVE ⇄ DEMOTED → RETIRED` (spec 05 §Lifecycle). One ACTIVE failure → DEMOTED (counters reset, `demotion_count += 1`); second demotion → RETIRED. Failures where the user cancelled or barged-in within 1.5 s of the plan starting are `INDETERMINATE`, not failures.

## Consequences

- Shadow mode is safe by construction (nothing to execute) and cheap (< 1 ms).
- The LLM and rules share one execution path and one confirmation UX; there is exactly one place to audit side effects.
- Rules need the state schema fixed and versioned; changing `RuleState` invalidates regression cases → schema version stored with each case.
- The DSL can stay tiny (no lambdas, no loops) because plans are data; gas metering remains as defence-in-depth for `when`.

## Growth path — from decision pathways to domain-specific reasoning (Phase 7+, requires ADR-011)

The v1 grammar (`when → plan`) is intentionally the *smallest* form of the original vision: LISP-based, domain-specific, learned reasoning pathways. It was narrowed so that shadow evaluation is well-defined, the confirmation gate cannot be bypassed, and one grammar exists instead of four. The narrowing is a **starting point, not the ceiling**. The intended expansion, in order, each gated on a concrete promoted rule that *needs* it:

| Step | Capability added | What it enables | Safety condition that must hold |
|---|---|---|---|
| G1 | Conditionals **inside** `:plan` (`(if <pure-expr> <action> <action>)`) using only `RuleState` | "open the file in Notepad if it's `.txt`, else in the browser" | plan remains data-only; every branch statically validated; shadow diff compares the *taken* branch |
| G2 | **Sequenced plans with intermediate results**: `(step id (tool …))` then later steps may reference `(result id :field)` | "list the inbox, then read the newest file, then summarise" | each step's result schema is the tool's declared output model; plan executes step-by-step through the same risk policy; a WRITE/LAUNCH step still confirms; shadow mode compares the LLM's actual sequence |
| G3 | **Rule composition**: `(invoke "other-rule-id")` in a plan, depth ≤ 3, no cycles (static check) | reuse of promoted sub-habits; hierarchical task decomposition | callee must be ACTIVE; regression suites include composed cases; demoting a callee demotes callers |
| G4 | `let` bindings and a bounded set of pure helpers (string/date/list ops) | readable rules; fewer LLM-proposed duplicates | still no `lambda`, no user recursion; gas/timeout unchanged |
| G5 | **HTN-style methods**: a rule may declare a goal and a method list; a tiny planner (pyhop/GTPyhop-class, ~200 lines) chooses among promoted methods | genuine multi-step domain planning over learned skills | planner output is still a data `Plan`; total steps ≤ 8; every method individually promoted through the same gate |
| G6 | Rules that **assert facts** (`(assert (s p o))`) with `LISP_ASSERTION` provenance | learned inference ("if the user says 'my boss', bind to `works_at` entity") | assertion grounding: subject/object must come from `RuleState.entities`; gate unchanged |

Non-goals even at G6: arbitrary recursion, `eval`, network or file I/O from inside the interpreter, rules that alter other rules, regex. The reflection prompt and GBNF grammar grow with each step; the promotion gate (≥ 5 distinct-cluster successes, 0 failures, regression suite) never loosens.

## Alternatives

| Option | Why not |
|---|---|
| Rules call tools directly | Bypasses risk policy; shadow mode impossible without mocking every tool. |
| Rules emit natural-language instructions to the LLM | Reintroduces LLM nondeterminism into a path whose point is determinism. |
| Full Scheme with `lambda`/recursion | Not needed for `State → Plan`; adds gas/timeouts/ReDoS/memory-bomb surface. Revisit only with a concrete rule that requires it. |
