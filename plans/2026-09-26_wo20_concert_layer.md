# Work Order 20 — The Concert Layer (Execution Manual)

**Status:** Planned (pending owner ratification of [`docs/adr/0010_d_reas_09_concert_layer.md`](../docs/adr/0010_d_reas_09_concert_layer.md))
**Date:** 2026-09-26
**Audience:** an implementing agent with no prior context. Every phase lists exact files, exact actions, **functional** acceptance criteria (behavioral, not just "suite green"), traps, and STOP gates. **STOP** means halt and report to the owner — do not improvise.
**Golden rules:** one phase = one commit; run `uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"` after every step (baseline: **707 passed, 0 failed**); never edit `docs/archive/`; never "fix forward" from a red suite — revert and re-read.

---

## Phase 0 — WO-20a0: Interrogative-Guard Bug Fix (live-test Finding 1)

**Goal:** stop question-shaped utterances from producing passive facts. Live evidence: `user origin_is though` (memory_id 107, garbage) and `user nationality_is Australian` (memory_id 124, true but question-sourced) both bypassed the guard.

**Root cause:** `_INTERROGATIVE_PATTERN` in `src/lucca/core/orchestrator.py` (grep for it) requires a literal trailing `?` and an opener from a fixed list. ASR transcripts often lack terminal punctuation, and openers like "So" are unlisted.

**Manifest:**
1. In the passive-extraction path (grep `_maybe_extract_facts` — now in `src/lucca/core/memory_commit_service.py` post-decomposition), replace the punctuation-dependent interrogative check with a structural one: an utterance is a question if (a) it matches the existing pattern, OR (b) it starts with an interrogative opener word (`who what when where why how which whose whom can could should would will do does did is are was were have has had may might must so`) **regardless of trailing punctuation**, OR (c) ASR `avg_logprob`-weighted rising intonation marker if available (skip (c) if no such field — do not invent one).
2. Add a value sanitizer for `origin_is`/`lives_in`: reject captures that are single stopwords (`though`, `not`, `no`, `never`, `nobody`, `none`, `really`, `actually`, `just`).

**Functional acceptance (behavioral, not mechanical):**
- `tests/test_grounded_memory_commit.py` gains: `"Do you know where I am from though"` (no `?`) produces **zero** candidates; `"So does that mean you remember that I'm Australian"` produces **zero** candidates; `"I'm from Melbourne"` still produces `origin_is Melbourne`.
- The existing 21 tests in that file still pass unchanged.

**Verify:** `uv run python -m pytest tests/test_grounded_memory_commit.py tests/test_static_gates.py -q` → green.

---

## Phase 1 — WO-20a: Assertion Primitive & Fact Predicates

**Goal:** rules can assert signed intermediates and match on them.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/schemas.py` | Add `AssertFact(BaseModel)` plan action: `s: str, p: str, o: str` (predicate validated by `is_valid_predicate`). Add it to the `Plan` action union. |
| `src/lucca/reasoning/scheme/prims.py` | Add `(assert (s p o))` primitive producing an `AssertFact` action in the plan (pure — no side effects in the prim). Add `fact-exists?` and `fact-value` predicates reading `RuleState.asserted_facts`. |
| `src/lucca/core/schemas.py` (`RuleState`) | Add `asserted_facts: frozenset[tuple[str, str, str]] = frozenset()`. |
| `src/lucca/core/orchestrator.py` | In plan execution (grep for where `ToolCall`/`Say` actions are executed), handle `AssertFact`: sign with `LispAssertionSigner` (via `SignerFactory`) and commit to the store. Rebuild `RuleState.asserted_facts` after each assertion. |
| `src/lucca/reasoning/lifecycle.py` | Re-evaluation loop: after a plan containing `AssertFact` executes, rebuild state and re-evaluate, bounded by `MAX_CHAIN_DEPTH = 8` and the existing gas limit. Halt on fixpoint. |

**Functional acceptance:**
- `tests/test_concert_layer.py` (new): register rule A (`:when trigger → (assert (user likes tiramisu))`) and rule B (`:when (fact-exists? (user likes tiramisu)) → (say "noted")`). Fire A; assert B fires on the rebuilt state in the same turn; assert the store contains a `LISP_ASSERTION` envelope for the fact, verifiable by `ProvenanceGate.admit`.
- A rule asserting inside a 9-deep chain halts at depth 8 with a logged `chain_depth_exceeded`, no crash.
- A rule whose plan asserts nothing causes **zero** re-evaluations (fixpoint fast-path).

**Traps:**
- **TRAP 1:** the prim must be pure. If `(assert ...)` writes to the store inside `prims.py`, the purity invariant (D-REAS-05) is dead. Assertion is an *action*, executed by the orchestrator.
- **TRAP 2:** `LispAssertionSigner` construction must go through `SignerFactory` — never inline (WO-18b discipline).
- **TRAP 3:** `asserted_facts` must be rebuilt, never mutated in place — `RuleState` is frozen.

**STOP gate:** none. Proceed.

---

## Phase 2 — WO-20b: Reasoning Context (Working Memory)

**Goal:** a chain-scoped scratchpad holding signed intermediates with provenance, isolated from long-term memory until a conclusion commits.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/reasoning_context.py` (new) | `ReasoningContext`: ordered list of `(envelope_id, s, p, o, confidence, step_kind)`; `add_intermediate()`, `premises_for(conclusion)`, `proof_trace()`; bounded at `MAX_CHAIN_DEPTH * 4` entries. |
| `src/lucca/core/orchestrator.py` | Create one `ReasoningContext` per deduction turn; pass to the re-evaluation loop; expose `proof_trace()` to the commit path (Phase 4). |

**Functional acceptance:**
- A 3-rule chain produces exactly 3 intermediates in order, each with a distinct envelope_id and the correct step_kind.
- `proof_trace()` returns the intermediates in firing order with premises resolvable to earlier entries.
- A second turn gets a fresh context (no leakage between turns).

**Traps:** the context is per-turn state — do not persist it to the DB (intermediates live as `LISP_ASSERTION` envelopes; the context is the *ordering* of them).

---

## Phase 3 — WO-20c: LLM Abductive-Step Protocol

**Goal:** the LLM proposes structured inference steps; the orchestrator validates and signs them.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/schemas.py` | `InferenceStep(BaseModel)`: `premises: list[str]`, `conclusion: str`, `confidence: float = Field(ge=0.0, le=1.0)`. |
| `src/lucca/brain/prompt_builder.py` | Deduction-mode prompt section: emit JSON steps, not prose; premises must reference facts from the provided signed context; confidence required. (Copy the grounded-narration contract's shape.) |
| `src/lucca/core/orchestrator.py` | Deduction loop: parse `InferenceStep`; validate each premise exists in the signed store or the `ReasoningContext`; valid → sign as `LISP_ASSERTION` and add to context; invalid → reject with `{"error": "unverified_premise", "premise": ...}` fed back to the model for one revision, then abstain. |

**Functional acceptance:**
- With a `FakeLLM` emitting a valid 2-step chain (premises present), both steps are signed and land in the context in order.
- With a `FakeLLM` emitting a step whose premise is absent, the step is rejected, the model gets the machine-readable reason, and a second (corrected) step is accepted. A second invalid step → honest abstention, no commit.
- A step with `confidence > 1.0` fails schema validation.

**Traps:**
- **TRAP 1:** the LLM never signs. Signing happens only in the orchestrator after validation.
- **TRAP 2:** premise validation must check the *signed store*, not the model's claims about the store.

**STOP gate:** the exact `InferenceStep` JSON shape is owner-visible — if you believe a field is missing (e.g., `rule_id` for authored inference rules), STOP and ask before adding it.

---

## Phase 4 — WO-20d: INFERRED Commit Path & Proof Trace

**Goal:** conclusions commit with their full signed derivation.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/schemas.py` | Add `Provenance.INFERRED`; add it to the grounding-eligible set at the tier below `USER_DERIVED` (grep `MEMORY_ELIGIBLE` / the Belnap tier mapping in `cascade.py`). |
| `src/lucca/memory/signers.py` | `DeducedFactSigner` + `create_deduced_fact_signer` (HKDF per ADR-006). Register in `SignerFactory`. |
| `src/lucca/memory/gate.py` | Admit `INFERRED` only with a non-empty `structured["proof_trace"]` whose every premise resolves to an existing envelope. |
| `src/lucca/core/orchestrator.py` | Chain finalizer: on fixpoint, commit the conclusion as `INFERRED` with `proof_trace = context.proof_trace()` and `confidence = min(step confidences)`. |
| `src/lucca/memory/store.py` | `INFERRED` facts are superseded by `USER_EXPLICIT`/`USER_DERIVED` facts on the same predicate. |

**Functional acceptance:**
- A completed chain commits a `INFERRED` fact; the gate verifies it; `proof_trace` replays (every premise resolves).
- A trace with a fabricated premise is rejected at the gate (`ProvenanceRejected`).
- A later `USER_DERIVED` fact on the same predicate supersedes the `INFERRED` one; the cascade prefers the direct evidence.
- The cascade frames the fact as "deduced, confidence c" in prompt context (grep the memory-context renderer).

**STOP gate:** the `INFERRED` Belnap tier placement (below `USER_DERIVED`, above `LISP_ASSERTION`) is an owner decision — present it, do not choose alone.

---

## Phase 5 — WO-20e: Live Acceptance — the "Where Am I From" Chain

**Goal:** the live-test scenario passes cold, with a proof trace, no leading.

**Functional acceptance (the only test that matters for this phase):**
- Scripted scenario (FakeLLM + seeded store): store contains `partner_is judge_in_philippines` and `tz = UTC+8`. User asks the deduction question. The system produces `user_likely_location Philippines` (step 1), then with `drop_bears → australian_folklore` produces `origin_likely Australia` (step 2), and commits `nationality_is Australian` as `INFERRED` with a 2-step proof trace — **without any operator leading**.
- The committed fact is superseded when the user then says "I'm Australian" (direct evidence wins).
- Full suite green at the 707 baseline + new tests.

---

## Review Protocol (same as WO-18/19)

Every phase returns the R.1 package: one commit hash, verbatim full-suite output, verbatim phase-verify output, self-check table, out-of-scope observations. The reviewer independently re-runs scope audit, diff read, verify commands, trap audit, gate quality (positive controls required on every new gate), and suite state against the **707-passed baseline**. PASS is logged; BOUNCE gets the failing row and the exact fix; two bounces → STOP, escalate to owner.

## Sequencing

```
Phase 0 (bug fix) → Phase 1 (assert+facts) → Phase 2 (context) → Phase 3 (LLM protocol) → Phase 4 (commit path) → Phase 5 (live acceptance)
```

Phase 0 is independent and can land immediately. Phases 1–2 are pure LISP (no LLM). Phase 3 is the design-heavy one — expect the most review attention there.

## R.4 Phase sign-off log

| Phase | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|
| 0 (interrogative-guard fix) | `bef2fbf` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-26 |
| 1 (assert + fact predicates) | `a50e5d7` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-26 |
| 2 (reasoning context) | `a948b89` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-26 |
| 2 (reasoning context) | | | | | |
| 3 (LLM abductive protocol) | | | | | |
| 4 (INFERRED commit path) | | | | | |
| 5 (live acceptance) | | | | | |
