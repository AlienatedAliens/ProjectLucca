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

A conclusion of a completed chain commits as a **new provenance class `INFERRED`**:

- Signed by a new `DeducedFactSigner` (constructed only in the orchestrator's chain finalizer — never LLM-reachable, per ADR-006 discipline).
- The envelope's `structured` field carries the **proof trace**: the ordered list of `(step_kind, rule_id | "llm", premises, conclusion, envelope_id)`.
- `grounding_eligible = 1`, but at a **Belnap trust tier strictly below** `USER_EXPLICIT` and `TOOL_VERIFIED`, and below `USER_DERIVED` (verbatim-grounded). The cascade fuses `INFERRED` facts with an explicit "deduced, confidence c" frame.
- `confidence < 1.0` mandatory; set to the minimum step confidence in the chain.
- A `INFERRED` fact can be **superseded** by a `USER_EXPLICIT`/`USER_DERIVED` fact on the same predicate (direct evidence outranks deduction — the "Australian" case: a later direct statement supersedes the deduced value).

## 2.5 The Riskiest Box: What Z3 Does and Does Not Verify

A candid scoping note, prompted by external review: the concert loop's "premises real? rule Z3-verified?" box compresses two very different checks, and conflating them is the single biggest design risk.

- **Z3 verifies *authored rules* only.** MicroScheme rules written by the operator or promoted from quarantine are formally verified (SAT, non-tautology, deontic invariants) before they may fire. This is tractable because rules are already in a formal language.
- **Abductive steps are *existence-checked*, not proven.** When the LLM proposes an `InferenceStep`, the orchestrator checks that each premise *exists as a signed fact in the store* — a lookup, not a proof. The *inference itself* (does the conclusion follow?) is **not** Z3-verified for abductive steps; it is marked `INFERRED` with the step's confidence, and superseded by direct evidence later.
- **Out of scope for v1:** translating natural-language premises into Z3-checkable form (whole-problem autoformalization). External work (Logic-LM, LINC) shows this fails badly on real benchmarks; step-level existence-checking is the narrow, honest v1 answer. Formalizing NL premises is a research problem, not an engineering formality, and it is explicitly deferred.

## 2.6 Threat Model for "Cryptographically Signed"

The signatures are for **integrity, provenance, and tamper-evidence of her own reasoning trail** — so she can trust her past derivations and the operator can audit them — not defense against an external adversary. This is a local, single-user companion; "cryptographic" here means *accountability* (a conclusion can't be silently altered or forged after the fact), not confidentiality or access control.

## 3. Honesty Invariants (non-negotiable)

1. Intermediates (`LISP_ASSERTION`) are **working memory**: memory-eligible, grounding-eligible *only within the chain's reasoning context*, and rolled up with the session summary unless promoted into a `INFERRED` conclusion.
2. No `INFERRED` fact may be created without a complete proof trace; a trace with an unverified premise is rejected at the gate.
3. The LLM never signs anything. It proposes; LISP validates and signs; the gate admits.
4. Deduced facts are always *marked* — the cascade and the prompt builder must frame them as deductions with confidence, never as direct knowledge.

## 4. Why this is the rung

The live test proved the abductive engine works (the LLM deduced correctly with web verification) and proved the missing half: the conclusion had no evidence path. This ADR supplies it — and supplies it in the only form consistent with the project's doctrine: every intermediate signed, every step validated, every conclusion replayable. Not "the model reasons" — **the model proposes, the symbolic layer disposes, and the proof is on file.**

## 5. Out of scope (explicit)

- Backward chaining / unification (Prolog-style). Forward-chaining only, bounded.
- Probabilistic inference beyond step-confidence propagation (min over chain).
- Autonomous chain induction (learning new inference rules from chains) — deferred to a later rung; chains are authored or operator-promoted only in v1 of this layer.
