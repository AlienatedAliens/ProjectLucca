# WO-23 — Walton Scheme Completion & Operational Polish

**Date:** 2026-09-27
**Audience:** an implementing agent with no prior context. Every phase lists exact files, exact actions, **functional** acceptance criteria (behavioral, not just "suite green"), traps, and STOP gates. **STOP** means halt and report to the owner — do not improvise.
**Golden rules:** one phase = one commit; run `uv run python -m pytest -q -m "not tier2 and not hw and not soak"` after every step (baseline: **920 passed, 0 failed** — verified 2026-09-27; re-run before your first commit and record the number you actually see); never edit `docs/archive/`; never edit an existing migration file; never "fix forward" from a red suite — revert and re-read.
**Provenance:** full deferred-item reassessment 2026-09-27 (all 15 backlog items, 12 DESIGN_DEBT items, WO-22 deferrals, roadmap deferrals). Baseline claims independently re-verified by reviewer; ITEM-028 found already RESOLVED and excluded from scope.

---

## Phase 0 — WO-23a: Operational Cleanups

**Goal:** clear the triggered operational debt before new reasoning work.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/router/` + `src/lucca/core/` | **ITEM-018** (V2_ACTION_LOG F12): extract a single shared `normalize_transcript(text: str) -> str` into `src/lucca/core/text_utils.py` (new). Apply it **once, at the ASR boundary**, so the HeuristicRouter and the MicroScheme rule evaluator consume *identical* text — do NOT give each consumer its own normalizer (two normalizers is how this divergence was born). Router reads the normalized string; rule engine receives the same string. Add parity tests: for a fixture corpus (punctuation, casing, contractions), `router.sees == rule_engine.sees` for every utterance. |
| `src/lucca/router/heuristic.py` (or the JSONL writers' module) | **ITEM-023**: calendar-day rotation for `logs/decisions.jsonl` (and any sibling JSONL trace logs): on write, if the file's date ≠ today, rotate to `decisions-YYYY-MM-DD.jsonl`; retain the most recent **14** rotated files, delete older; retention count read from config (existing config pattern), never hardcoded. Rotation must be crash-safe (rotate on open, not on close). Tests: rotation on date rollover, retention pruning, no data loss across rotation boundary. |
| `tests/test_a1_property.py` | **B-04**: remove the stale `xfail(strict=True)`-era comments at lines ~786/~811 (the receipt-aware WP-2 checker shipped in WO-20; the tests pass). Comment-only change, no behavior. |
| `docs/research/LUCCA_REASONING_CAPABILITY.md` | **D-01/D-02**: update **Status** (currently "WO-20 in flight" — stale): WO-20, WO-21, WO-22 all SHIPPED; refresh the reasoning-ladder section to reflect the live concert layer, defeasible rung (authority scheme), means-ends planner, and fault-model diagnosis. Cross-check against `docs/V2_BACKLOG.md` and `docs/DECISIONS.md` — no superseded-term violations (the static staleness lint in `tests/test_static_gates.py` must stay green). |
| `docs/V2_ACTION_LOG.md` | Flip dispositions: **ITEM-017 → RESOLVED** (WO-22 Phase 1, `d7a352a`), **ITEM-021 → RESOLVED** (WO-22 Phase 2, `f366704`), **ITEM-028 → RESOLVED** (already covered: [`sanitize_for_voice`](../src/lucca/brain/chunker.py) wraps `normalise_text` and is applied at every TTS choke point — `orchestrator.py` ×3, `speech_output_manager.py:270`), **ITEM-018 / ITEM-023 → IN WO-23**. **ITEM-022 → stays DEFERRED** (owner decision 2026-09-27: defer until a recurring tuning task actually needs it — do not externalize heuristics speculatively). |

**Functional acceptance:**
- A narration containing `**bold**`, `*emphasis*`, and a code fence reaches the TTS with zero markdown (regression-proof the existing `sanitize_for_voice` coverage with a test if one doesn't exist).
- Router and rule engine never observe different text for the same utterance (property test).
- JSONL logs rotate at UTC date boundary; 15th-oldest file is pruned; no line is lost or duplicated.
- Suite green vs **920-passed** baseline (record your actual count).

**Traps:**
- **TRAP 1:** do not "fix" ITEM-028 by adding a second sanitizer — it is already resolved; adding one creates two code paths that can drift. Verify, don't rebuild.
- **TRAP 2:** the shared `normalize_transcript` must live in ONE module imported by both consumers — a re-export from a second module still counts as one definition.
- **TRAP 3:** log rotation must not hold the file open across the rotation check (Windows file-lock semantics — rotate by rename-then-recreate, not truncate-in-place).

**STOP gate:** none. Proceed.

---

## Phase 1 — WO-23b: Walton Scheme Extension (SIGN, ANALOGY, CONSEQUENCE, PRECEDENT)

**Goal:** complete the corroboration engine's argumentation coverage: all 5 ratified Walton schemes dispatch real critical-question evaluators; only AUTHORITY is implemented today ([`corroboration.py:312`](../src/lucca/core/corroboration.py) raises `NotImplementedError` for the rest).

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/corroboration.py` | Implement the 4 remaining schemes in the same dispatch pattern as AUTHORITY: **SIGN** (symptom→cause: does the observed sign actually indicate the claimed state? independent source of the sign?), **ANALOGY** (is the precedent case relevantly similar? relevant-similarity and relevant-difference questions), **CONSEQUENCE** (does the claimed consequence follow? does the bad/good outcome actually follow from the action?), **PRECEDENT** (is the cited precedent binding/parallel? was it decided on the same facts?). Each scheme: typed `CQResult` per critical question (SATISFIED / VIOLATED / UNKNOWN + evidence), same confidence-adjustment discipline as AUTHORITY (bounded deltas, no scheme may exceed the confidence ceiling). |
| `src/lucca/core/orchestrator.py` | Premise-shape → scheme detection: when a source-conditioned claim arrives, classify its premise shape (expert citation → AUTHORITY, observable indicator → SIGN, case comparison → ANALOGY, causal claim → CONSEQUENCE, prior ruling → PRECEDENT) and dispatch to the matching evaluator. Ambiguous shapes → AUTHORITY fallback with a recorded `conditions` note (never silently pick). |
| `tests/test_corroboration.py` | Per-scheme positive AND negative controls: each scheme's critical questions can SATISFY and VIOLATE on seeded receipts; unknown TLD / malformed sources degrade honestly (no crash); **static gate: every value of the `Scheme` enum is dispatchable** — a test that iterates `Scheme` and asserts no `NotImplementedError` escapes (this is the idiot-proofing: a future 6th scheme stub fails this test loudly). |

**Functional acceptance:**
- A claim supported by a symptom ("NPU load is zero but TTS is slow") routes to SIGN and evaluates its critical questions — not to a `NotImplementedError`.
- Confidence deltas remain bounded and standards-of-proof thresholds unchanged; scheme choice is recorded in the evaluation trace.
- The 4 new schemes each have at least one SATISFIED and one VIOLATED test case.

**Traps:**
- **TRAP 1:** the `Scheme` enum already has all 5 values and `critical_questions()` dispatches by string value — keep the string-normalization path; do not introduce a second dispatch table.
- **TRAP 2:** eTLD+1 source normalization (WO-22 Phase 0) applies to ALL schemes — alias dedupe and distinct-domain invariants must hold for every new scheme's Q2-style corroboration question.
- **TRAP 3:** diagnoses/evaluations remain `INFERRED`-style hedged outputs — never asserted as facts (D-HON-01 register applies to scheme results too).

**STOP gate:** ~~the 4 scheme definitions (premise shapes + critical question sets + confidence deltas) are owner-visible — present before implementing.~~ **RATIFIED 2026-09-27 by owner (after reviewer audit), with normalized deltas:**
- **Thresholds:** the 4 schemes consume the existing ratified table unchanged — BALANCE_OF_PROBABILITIES **0.50** / CLEAR_AND_CONVINCING **0.75** / BEYOND_REASONABLE_DOUBT **0.95** ([`schemas.py`](../src/lucca/core/schemas.py) `PROOF_STANDARD_THRESHOLDS`, fail-closed per [`proof_policy.py`](../src/lucca/core/proof_policy.py)). The proposal's "BEYOND_A_REASONABLE_DOUBT (0.90)" / "PREPONDERANCE (0.51)" were misstatements — corrected; no new thresholds, no renamed standards.
- **Deltas normalized to the ratified AUTHORITY family** (positives ≤ +0.15, negatives ≥ −0.30): SIGN +0.15 / −0.25; ANALOGY +0.12 / −0.30; CONSEQUENCE +0.15 / −0.30 (was −0.35); PRECEDENT **+0.15** (was +0.18) / −0.25 / −0.20. Rationale: identical epistemic events must cost the same regardless of detecting scheme; magnitudes are uncalibrated priors until corroboration telemetry exists; PRECEDENT's provenance strength is captured by its CQ2 grounding-eligibility *gate*, not a larger bonus. Per-scheme delta differentiation becomes eligible only via a future data-earned calibration pass.
- **Everything else as proposed:** premise-shape cues, CQ sets, eTLD+1 uniformity, `min(0.95, …)` ceiling / `max(0.00, …)` floor, AUTHORITY fallback with recorded condition.
**Reviewer audit record (pre-ratification):** the proposal listed "BEYOND_A_REASONABLE_DOUBT (0.90)" and "PREPONDERANCE (0.51)" — both contradict the ratified table; and PRECEDENT +0.18 / CONSEQUENCE −0.35 exceeded the AUTHORITY family (+0.10 / −0.30). Owner resolved by normalizing (see above).

---

## Phase 2 — Deferred to WO-24 (owner decision 2026-09-27)

`clipboard_read` + `inbox_handoff` (Class C tools) ship in **WO-24 Phase 2** together with the registry cap raise (19→30) and BitNet shortlisting, so `MAX_REGISTRY_TOOLS` is raised exactly once and the tools arrive into their final routing architecture. Rationale: two cap raises means two prompt-suffix re-verifications for no capability gain — the tools are ready but not urgent.

---

## Phase 2 (this WO) — Live Acceptance

**Functional acceptance (the only test that matters for this phase):**
- **Walton schemes:** present 4 live claims, one per new scheme, each with seeded source receipts → she evaluates the correct scheme per premise shape, speaks the critical-question outcome with hedge, and a VIOLATED question produces a `conditions`-carried inference (defeasible, not refuted).
- **ITEM-018:** an utterance with trailing punctuation + mixed casing routes identically through the router and matches the same rule as its normalized form.
- **Rotation:** simulate a date boundary → old file rotated, retention pruned, next write lands in the new file; no lost decisions.
- R.1 includes verbatim spoken output for the scheme scenarios.

**Traps:** fault injection / date mocking must be fixture-scoped — no leakage into other tests.

**STOP gate:** verbatim spoken output goes to the owner with the R.1.

---

## Execution order

```
Phase 0 (cleanups) → Phase 1 (Walton schemes) → Phase 2 (live acceptance)
```

## Review protocol (unchanged)

R.1 package per phase: one commit hash, verbatim full-suite output, verbatim phase-verify output, self-check table, out-of-scope observations. Reviewer independently re-runs scope audit, diff read, verify, trap audit, gate quality (positive AND negative controls on new gates), suite state vs the **920-passed baseline** (as of 2026-09-27; re-baseline at implementation start). PASS logged; BOUNCE gets the failing row + exact fix; two bounces → STOP, escalate to owner.

## R.4 Phase sign-off log

| Phase | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|
| 0 (operational cleanups) | `5f296cf` | Gemini (implementer) | Zoo (independent re-run: 927 passed / 0 failed; rotation rename-then-recreate + config retention verified; parity + sanitization regression tests confirmed) | PASS | 2026-09-27 |
| 1 (walton schemes) | | | | | |
| 2 (live acceptance) | | | | | |

## WO-24 preview (not part of this work order)

BitNet tool-router lobe: Phase 0 hardware spike (bitnet.cpp on Arrow Lake — may run in **parallel** with WO-23 as scratch-only research; nothing lands in `src/` until its own plan is ratified), Phase 1 classification head, Phase 2 integration: raise `MAX_REGISTRY_TOOLS` 19→30, register `schedule_event` + `artifact_verify` + `clipboard_read` + `inbox_handoff`, shortlist tools per turn. Phase 3 live acceptance.

## Explicitly deferred (unchanged)

ITEM-019 (no clarification latency observed), ITEM-020 (needs §1.6 transactional sandbox), ITEM-022 (owner-deferred 2026-09-27), ITEM-024–027, §1.1–§1.8, §1.14, §1.15, `screenshot_capture` (vision lobe trigger), domain lobes, C1b slot-2, L5 ranking — all behind their existing triggers; see [`docs/V2_BACKLOG.md`](../docs/V2_BACKLOG.md).
