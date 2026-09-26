# D-REAS-09 — The Concert Layer: Bounded Forward-Chaining Deduction with Signed Proof Traces

**Status:** Proposed (pending owner ratification)
**Date:** 2026-09-26
**Origin:** Live deduction test 2026-09-26 (operator led the companion through a multi-step abductive chain; the chain succeeded but the conclusion could not be committed — `o_not_grounded` — because quote-grounding is single-turn-verbatim and deduction has no evidence path)
**Depends on:** D-REAS-06 (quarantine invariant), D-REAS-07 (Z3 verification), D-MEM-04 (grounding partition), ADR-006 (provenance signers)

---

## 1. Decision

Lucca gains a **concert layer**: multi-step deductive/abductive reasoning in which the MicroScheme engine (deductive skeleton) and the LLM (abductive engine) operate in concert over the signed fact store, producing conclusions that carry a **cryptographically signed proof trace** and are committable to memory as evidence.

Four mechanisms:

1. **Assertion primitive.** Rules may emit `(assert (s p o))` as a plan action. The executor (never the rule — purity invariant D-REAS-05 holds) signs the fact with `LispAssertionSigner` and commits it as `LISP_ASSERTION`. Rules remain pure `State → Plan`; assertion is an *executed plan action*, exactly as `ToolCall` and `Say` are today.

2. **Fact predicates.** `RuleState` gains a bounded `asserted_facts: frozenset[(s, p, o)]` view (current chain's intermediates + grounding-eligible store facts matching the chain's working set), and the evaluator gains `fact-exists?` / `fact-value` predicates so rules can match on intermediates.

3. **Bounded re-evaluation.** After any plan executes an `assert` action, the turn pipeline rebuilds `RuleState` and re-evaluates the rule set, up to `MAX_CHAIN_DEPTH = 8` (the D-REAS-05 macro-depth discipline) and the existing 1,000-gas limit per evaluation. The loop halts on fixpoint (no new assertions), depth, or gas — never unbounded.

4. **LLM abductive steps.** In deduction mode, the LLM emits **structured inference steps** (Pydantic `InferenceStep`: `premises: list[str]`, `conclusion: str`, `confidence: float`) instead of prose. The orchestrator validates every premise against the signed store; valid steps are signed as `LISP_ASSERTION` intermediates; invalid steps are rejected with a machine-readable reason the model may revise against or abstain from.

## 2. The Commit Path (solving the live-test refusal)

A conclusion of a completed chain commits as a **new provenance class `DEDUCED`**:

- Signed by a new `DeducedFactSigner` (constructed only in the orchestrator's chain finalizer — never LLM-reachable, per ADR-006 discipline).
- The envelope's `structured` field carries the **proof trace**: the ordered list of `(step_kind, rule_id | "llm", premises, conclusion, envelope_id)`.
- `grounding_eligible = 1`, but at a **Belnap trust tier strictly below** `USER_EXPLICIT` and `TOOL_VERIFIED`, and below `USER_DERIVED` (verbatim-grounded). The cascade fuses `DEDUCED` facts with an explicit "deduced, confidence c" frame.
- `confidence < 1.0` mandatory; set to the minimum step confidence in the chain.
- A `DEDUCED` fact can be **superseded** by a `USER_EXPLICIT`/`USER_DERIVED` fact on the same predicate (direct evidence outranks deduction — the "Australian" case: a later direct statement supersedes the deduced value).

## 3. Honesty Invariants (non-negotiable)

1. Intermediates (`LISP_ASSERTION`) are **working memory**: memory-eligible, grounding-eligible *only within the chain's reasoning context*, and rolled up with the session summary unless promoted into a `DEDUCED` conclusion.
2. No `DEDUCED` fact may be created without a complete proof trace; a trace with an unverified premise is rejected at the gate.
3. The LLM never signs anything. It proposes; LISP validates and signs; the gate admits.
4. Deduced facts are always *marked* — the cascade and the prompt builder must frame them as deductions with confidence, never as direct knowledge.

## 4. Why this is the rung

The live test proved the abductive engine works (the LLM deduced correctly with web verification) and proved the missing half: the conclusion had no evidence path. This ADR supplies it — and supplies it in the only form consistent with the project's doctrine: every intermediate signed, every step validated, every conclusion replayable. Not "the model reasons" — **the model proposes, the symbolic layer disposes, and the proof is on file.**

## 5. Out of scope (explicit)

- Backward chaining / unification (Prolog-style). Forward-chaining only, bounded.
- Probabilistic inference beyond step-confidence propagation (min over chain).
- Autonomous chain induction (learning new inference rules from chains) — deferred to a later rung; chains are authored or operator-promoted only in v1 of this layer.
