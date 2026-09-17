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

## Alternatives

| Option | Why not |
|---|---|
| Rules call tools directly | Bypasses risk policy; shadow mode impossible without mocking every tool. |
| Rules emit natural-language instructions to the LLM | Reintroduces LLM nondeterminism into a path whose point is determinism. |
| Full Scheme with `lambda`/recursion | Not needed for `State → Plan`; adds gas/timeouts/ReDoS/memory-bomb surface. Revisit only with a concrete rule that requires it. |
