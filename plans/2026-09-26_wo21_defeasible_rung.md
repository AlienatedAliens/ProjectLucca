# WO-21 — The Defeasible Rung: Source-Conditioned Beliefs, Corroboration & Standards of Proof

**Date:** 2026-09-26
**Audience:** an implementing agent with no prior context. Every phase lists exact files, exact actions, **functional** acceptance criteria (behavioral, not just "suite green"), traps, and STOP gates. **STOP** means halt and report to the owner — do not improvise.
**Golden rules:** one phase = one commit; run `uv run python -m pytest -q -m "not tier2 and not hw and not soak"` after every step (baseline: **733 passed, 0 failed** — re-verify independently before Phase 1); never edit `docs/archive/`; never "fix forward" from a red suite — revert and re-read; never edit an existing migration file — new schema changes are **new migration files only** (WO-20 Phase 4 BOUNCE lesson).
**Research grounding:** [`docs/research/REASONING_BREADTH_RESEARCH_PASS_2026-09.md`](../docs/research/REASONING_BREADTH_RESEARCH_PASS_2026-09.md) (Walton schemes, subjective logic, Toulmin, standards of proof). Backlog entry: [`docs/V2_BACKLOG.md`](../docs/V2_BACKLOG.md) §1.9–1.12.

---

## Phase 0 — WO-21a: Baseline Verification & Cosmetic Debt

**Goal:** confirm the 733 baseline independently and clear the two known cosmetic items.

**Manifest:**
| File | Action |
|---|---|
| (none — verification only) | Run the full suite; record the count. If ≠ 733 passed, STOP and report. |
| `src/lucca/memory/retrieval.py` | Renderer wording: `[deduced, confidence c]` → `[inferred, confidence c]` (the tier is INFERRED; the word "deduced" launders certainty — same reasoning as the DEDUCED→INFERRED rename, commit `b4ddd49`). Update `tests/test_concert_layer.py` assertions that check `"deduced, confidence"`. |
| `src/lucca/core/orchestrator.py` | Gather-ladder user-question wording (line ~1433): replace the hardcoded `"where do you live or what is the background here?"` with a template naming the actual missing premise: `f"I don't have anything verified about {missing_premise} — can you tell me about it?"`. Keep the personal/non-personal split if useful, but the gap must be named. |

**Functional acceptance:**
- Renderer and cascade output contain `inferred, confidence` and never `deduced, confidence`.
- A gather-ladder termination speaks a question containing the actual missing premise string.

**Traps:** do not touch the tier ordering or the gate; wording only.

**STOP gate:** none. Proceed.

---

## Phase 1 — WO-21b: Standards-of-Proof Policy Table

**Goal:** different consumers of a belief require different confidence standards (the legal analogy: balance of probabilities / clear and convincing / beyond reasonable doubt). Make the existing raw `confidence` float *systematic and testable*.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/schemas.py` | `ProofStandard(StrEnum)`: `SPECULATION`, `BALANCE_OF_PROBABILITIES`, `CLEAR_AND_CONVINCING`, `BEYOND_REASONABLE_DOUBT`. `PROOF_STANDARDS: dict[ProofStandard, float]` = `{SPECULATION: 0.0, BALANCE_OF_PROBABILITIES: 0.5, CLEAR_AND_CONVINCING: 0.75, BEYOND_REASONABLE_DOUBT: 0.95}`. Helper `standard_for_confidence(c: float) -> ProofStandard`. |
| `src/lucca/core/proof_policy.py` (new) | `required_standard(consumer: str) -> ProofStandard` — the policy table: `casual_mention → BALANCE_OF_PROBABILITIES`, `memory_commit_inferred → CLEAR_AND_CONVINCING`, `unhedged_assertion → BEYOND_REASONABLE_DOUBT`, `irreversible_action → BEYOND_REASONABLE_DOUBT`. Unknown consumer → `BEYOND_REASONABLE_DOUBT` (fail-closed). |
| `src/lucca/core/cascade.py` | The memory-context renderer labels each INFERRED fact with its standard: `[inferred, confidence 0.82 — balance of probabilities]`. |
| `src/lucca/core/orchestrator.py` | `finalize_chain` refuses to commit an INFERRED conclusion whose confidence < `CLEAR_AND_CONVINCING` (0.75) — below that, the chain result stays a working-memory intermediate and is spoken as speculation, never committed. |
| `tests/test_proof_policy.py` (new) | Table completeness, fail-closed unknown consumer, boundary values (0.5/0.75/0.95 exactly), finalize_chain refusal below 0.75, commit at ≥ 0.75. |

**Functional acceptance:**
- A chain concluding with confidence 0.60 does NOT commit; the spoken output frames it as speculation ("I think… but I'm not sure enough to keep it").
- A chain concluding at 0.80 commits as INFERRED.
- The prompt context shows the standard label.

**Traps:**
- **TRAP 1:** never lower a threshold to make a test pass. The table is owner-ratified constants.
- **TRAP 2:** `finalize_chain` refusal must not lose the work — the intermediate stays in the ReasoningContext and the proof trace remains available.

**STOP gate:** the threshold values (0.5 / 0.75 / 0.95) and the consumer→standard mapping are owner-visible. Present the table before implementing; do not choose alone.

---

## Phase 2 — WO-21c: Corroboration Engine (Walton Critical Questions)

**Goal:** confidence becomes *evidence-derived*, not LLM-self-reported. Implement the argument-from-authority scheme's critical questions as a dispatch table over the signed store: is the source credible (prior ratified facts from it)? is the claim corroborated elsewhere? is it disputed elsewhere?

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/corroboration.py` (new) | `Scheme(StrEnum)`: `AUTHORITY`, `SIGN`, `ANALOGY`, `CONSEQUENCE`, `PRECEDENT` (v1 implements AUTHORITY fully; others raise `NotImplementedError` with a typed reason). `critical_questions(scheme, step: InferenceStep, store) -> list[CriticalQuestionResult]` — each result: `{question, answer: satisfied|failed|unknown, evidence: entry_ids}`. AUTHORITY questions: (1) *Does a signed receipt prove the source asserted the claim?* (2) *Is the claim corroborated by an independent grounding-eligible fact?* (3) *Is the claim disputed by any grounding-eligible fact?* |
| `src/lucca/core/orchestrator.py` | In `run_deduction_step`: after premise validation, run `critical_questions` for each step with attributed premises. Adjust the step's effective confidence: corrobored → `min(1.0, conf + 0.1)`; disputed → `max(0.0, conf - 0.3)` and the dispute is added to `conditions`. Record question results in the ReasoningContext entry (`structured` via `to_dict()`). |
| `tests/test_corroboration.py` (new) | Corroborated claim gets boosted; disputed claim gets docked + condition added; unknown stays flat; AUTHORITY q1 failure (no receipt) → premise already unverified (integration with Phase 3 of WO-20). |

**Functional acceptance:**
- Seed the store with two independent sources asserting the same claim → the step's effective confidence is higher than proposed.
- Seed a disputing fact → confidence docked, dispute named in `conditions`, and the final INFERRED commit (if it survives the Phase 1 standard) carries the dispute condition.

**Traps:**
- **TRAP 1:** corroboration counts *independent* sources — two receipts from the same fetch/domain do not corroborate. Dedupe by source.
- **TRAP 2:** never let corroboration push confidence to 1.0 (certainty laundering); cap at 0.95.

**STOP gate:** the confidence adjustment arithmetic (+0.1 / −0.3 / cap 0.95) is owner-visible — present before implementing.

---

## Phase 3 — WO-21d: Web-Fact Ratification Flow

**Goal:** she proactively offers durable web findings for ratification; your "yes" — not the web — is the trust root.

**Manifest:**
| File | Action |
|---|---|
| `config/tool_whitelist.toml` (or a new `config/domain_whitelist.toml`) | `ratification_domains` list — domains she may proactively ask about. Ship with a small default (e.g., `docs.python.org`) and document that the owner curates it. |
| `src/lucca/core/orchestrator.py` | After a `fetch_url`/`search_web` receipt whose content contains a durable-fact-shaped claim AND the domain is whitelisted: append to the turn's spoken output a ratification offer: *"I found on {domain} that {claim} — want me to remember that?"*. On user confirmation (next turn, via the existing confirmation grammar), commit `USER_DERIVED` with `structured = {source_url, fetch_receipt_entry_id, confirmed_by_user: true}`. Non-whitelisted domains: never prompt. |
| `src/lucca/memory/gate.py` | `USER_DERIVED` commits with `confirmed_by_user` must reference a real `fetch_receipt_entry_id` envelope — fabricated-URL ratification attempts are rejected (`ProvenanceRejected`). |
| `tests/test_ratification.py` (new) | Whitelisted domain → offer spoken; user yes → USER_DERIVED committed with source metadata; user no → nothing committed; non-whitelisted → no offer; fabricated receipt id → gate rejection. |

**Functional acceptance:**
- The full loop: fetch → offer → "yes" → fact committed and grounding-eligible → a later deduction can use it as a premise.
- The whitelist is friction control only: a whitelisted domain NEVER auto-commits without your yes.

**Traps:**
- **TRAP 1:** the offer must be one per turn maximum — no nagging loops.
- **TRAP 2:** the committed fact's provenance signer is `DerivedFactSigner` (your ratification), never any web signer.

**STOP gate:** the default whitelist contents and the offer phrasing are owner-visible.

---

## Phase 4 — WO-21e: Theory-of-Mind & Case-Based Stubs

**Goal:** two cheap consumers of SELF_HISTORY that make her feel continuous: don't re-explain what you know; recall what worked last time.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/user_model.py` (new) | `UserModel`: tracks topics the user has been told about (from ASSISTANT_UTTERANCE) and has confirmed (USER_EXPLICIT/USER_DERIVED). `known_topics(query) -> list[str]`. Exposed to the prompt builder as a directive: *"The user already knows: X, Y — do not re-explain unless asked."* |
| `src/lucca/core/episode_recall.py` (new) or extend `src/lucca/reasoning/recall.py` | CBR retrieve step: on tool failure or repeated question shape, retrieve the most similar past episode from `execution_triples`/SELF_HISTORY and inject: *"Last time (date), a similar situation occurred: {episode}. What you did: {action} — it {worked/failed}."* |
| `src/lucca/brain/prompt_builder.py` | Consume both: user-model directive + episode hint section (bounded, e.g., ≤ 2 episodes, ≤ 200 tokens total). |
| `tests/test_user_model.py`, `tests/test_episode_recall.py` (new) | Told-topic suppression; confirmed-topic recognition; episode retrieval on similar shape; bounded injection. |

**Functional acceptance:**
- Tell her a fact, ask her to explain the related topic → she does not re-state what you told her; the trace shows the user-model directive fired.
- Repeat a request shape that failed before → the prompt contains the past-episode hint.

**Traps:**
- **TRAP 1:** the user model is built ONLY from signed records (ASSISTANT_UTTERANCE, USER_EXPLICIT) — never from LLM narration beliefs.
- **TRAP 2:** episode hints are context, not commands — the model may deviate; the hint must be phrased as history, not instruction.

**STOP gate:** none (both are read-only context features). Proceed.

---

## Phase 5 — WO-21f: Fuzzy Clustering for Induction

**Goal:** fix the 0-cluster induction finding — near-duplicate phrasings must merge.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/reasoning/induction.py` | Replace exact-match clustering with near-duplicate clustering: normalize (lowercase, strip punctuation, stopword-light) then cluster by token-set Jaccard ≥ 0.6 (or embedding cosine ≥ 0.85 if the NPU embedder is available in-process — prefer the deterministic Jaccard for v1). |
| `tests/test_rule_induction.py` | Add: 4 phrasings of the same request ("what's my IP", "whats my ip", "tell me my ip address", "my ip?") → 1 cluster. Distinct requests stay separate. |

**Functional acceptance:**
- Re-run the live induction path (`scratch/first_live_induction.py` logic, moved to a proper test or admin command) against the production log: clusters > 0.

**Traps:** clustering must remain deterministic (no model calls) and bounded (N ≤ a few hundred decisions).

**STOP gate:** none. Proceed.

---

## Phase 6 — WO-21g: Live Acceptance — The Source-Conditioned Chain

**Goal:** the owner's original scenario, end to end.

**Functional acceptance (the only test that matters for this phase):**
- Scripted (FakeLLM + seeded store + seeded receipts): store has `user partner_is judge_in_philippines`, `user tz_is UTC+8`; a whitelisted fetch receipt asserts `"driver-582.11 fixes wsl-crash"`. The chain produces: `user likely_location Philippines` (corroborated, boosted), then a source-conditioned conclusion (`driver-582.11 likely_fixes user's wsl-crash`, confidence docked for the dispute condition if a dispute is seeded) committed as INFERRED **with the attributed premise in `conditions`**, standard-labeled in prompt context, and superseded when direct user evidence arrives.
- The spoken output names the condition: *"…if ars-technica is right about the driver fix."*

**Traps:** the whole scenario must run in ONE turn with no operator leading; every intermediate signed; the final commit passes the gate replay.

**STOP gate:** none — but the R.1 package for this phase must include the verbatim spoken output for owner review.

---

## Execution order & dependencies

```
Phase 0 (verify+cosmetics) → Phase 1 (standards) → Phase 2 (corroboration) → Phase 3 (ratification) → Phase 4 (ToM/CBR) → Phase 5 (fuzzy clustering) → Phase 6 (live acceptance)
```

Phase 5 is independent and may run anytime after Phase 0. Phases 1–3 are strictly ordered (corroboration adjusts confidence; standards gate the commit; ratification feeds premises).

## Review protocol (unchanged)

Every phase returns the R.1 package: one commit hash, verbatim full-suite output, verbatim phase-verify output, self-check table, out-of-scope observations. The reviewer independently re-runs scope audit, diff read, verify commands, trap audit, gate quality (positive controls required on every new gate), and suite state against the **733-passed baseline**. PASS is logged; BOUNCE gets the failing row and the exact fix; two bounces → STOP, escalate to owner.

## R.4 Phase sign-off log

| Phase | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|
| 0 (baseline + cosmetics) | `b81bf3c` | Gemini | Owner/Reviewer | PASS | 2026-09-27 |
| 1 (standards of proof) | `afb1fe7` | Gemini | Owner/Reviewer | PASS | 2026-09-27 |
| 2 (corroboration) | | | | | |
| 3 (ratification) | | | | | |
| 4 (ToM/CBR stubs) | | | | | |
| 5 (fuzzy clustering) | | | | | |
| 6 (live acceptance) | | | | | |