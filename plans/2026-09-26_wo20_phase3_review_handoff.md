# HANDOFF — R.2 Review Completion for WO-20c Phase 3 (commit `e118936`)

**To:** implementing agent (Gemini), acting as completing reviewer
**From:** prior reviewer (Zoo) — session ended mid-review; steps 1–2 complete, steps 3–6 below are yours.
**Rule:** do NOT re-implement anything. You are completing an independent review.

---

## Step 1 — Scope audit: DONE (verified by prior reviewer)

5 files, +820/−0, all on-manifest:
- `src/lucca/core/schemas.py` — `InferenceStep` matches the ratified shape exactly: `premises: list[str]`, `s/p/o: str`, `p` validated by `is_valid_predicate`, `confidence ∈ [0,1]`, `rationale ≤ 500`, `conditions ≤ 8`.
- `src/lucca/core/reasoning_context.py` — `conditions` threaded through `ReasoningEntry`, `ProofTraceStep`, `add_intermediate()`, `proof_trace()`.
- `src/lucca/brain/prompt_builder.py` — `DEDUCTION_CONTRACT_SECTION` + `build_deduction_messages()`.
- `src/lucca/core/orchestrator.py` — `_validate_premise`, `_search_memory_for_premise`, `_parse_inference_steps`, `run_deduction_step` (gather ladder).

## Step 2 — Diff read: DONE. Trap verdicts (prior reviewer):

- **TRAP 1 (LLM never signs): PASS** — signing happens only inside `run_deduction_step` via `self._commit_lisp_assertion(AssertFact(...))` using `SignerFactory.lisp_assertion()`.
- **TRAP 2 (store-not-claims): PASS** — `_validate_premise` checks (a) current-turn signed tool receipts for attributed `"<source> asserts <claim>"` premises, (b) `ReasoningContext` intermediates, (c) grounding-eligible memory store rows. Never LLM self-attestation.
- **TRAP 3 (bounded ladder): PASS** — single pass: revise once → memory retry → named-gap question/abstention → return. No loops.

## Step 3 — YOUR JOB: independent verification

```
uv run python -m pytest tests/test_concert_layer.py tests/test_static_gates.py -q
# expect: 39 passed (18 concert + 21 gates)

uv run python -m pytest -q -m "not tier2 and not hw and not soak"
# expect: 727 passed, 46 deselected (implementer reported this)
```
If counts differ, report both numbers and **STOP** — do not fix forward.

## Step 4 — YOUR JOB: adjudicate three reviewer findings

- **F1 (likely bug — decides PASS vs BOUNCE):** `orchestrator.py` line ~1189 in `_search_memory_for_premise` constructs `RetrievalQuery(text=clean, limit=5)`. The canonical constructor elsewhere (e.g., `_search_memories`, line ~1017) uses `RetrievalQuery(query_text=..., k=8)`. If `text`/`limit` are not valid `RetrievalQuery` fields, this raises and is swallowed by the `except`, so the memory-retry ladder step only ever "works" via the DB-fallback path — the MemoryStore path would be dead code and the ladder test would pass for the wrong reason. **Verify** against the `RetrievalQuery` definition in `src/lucca/core/schemas.py` and determine whether `test_gather_ladder_memory_retry_recovers_unseeded_context` exercises the MemoryStore path or silently the fallback.
  - If `RetrievalQuery` accepts those kwargs → F1 disproven.
  - If not → **BOUNCE**: fix = correct the constructor kwargs (matching the canonical call), re-run Step 3, re-report.
- **F2 (style-gate risk):** `_validate_premise` uses `except Exception` with `# noqa: BLE001` (line ~1176) and has a `logger.debug` call inside — verify `test_no_silent_broad_excepts` does not flag it (logger presence should exempt it).
- **F3 (quality note, NOT blocking):** the gather-ladder user-question wording (line ~1433) is hardcoded ("where do you live or what is the background here?") regardless of which premise is missing. Should be a template naming the actual gap. Record as a WO-21 polish item; do not fix in this review.

## Step 5 — Verdict rules

**PASS** only if: Step 3 counts match AND F1 is disproven.
**BOUNCE** if: counts mismatch or F1 confirmed — BOUNCE includes the exact fix and re-review after the fix commit.

## Step 6 — Record and commit

In `plans/2026-09-26_wo20_concert_layer.md`, R.4 sign-off log (next empty row after Phase 2):

```
| 3 (LLM abductive protocol) | `e118936` | implementing agent | reviewer (Gemini) | **PASS/BOUNCE** | 2026-09-26 |
```

Commit as: `docs(wo-20): R.4 sign-off - Phase 3 <verdict> (e118936)`

If BOUNCE, add the F1 evidence as a note directly under the table.

---

## After sign-off

- **Phase 4 (WO-20d, INFERRED commit path) is STOP-gated:** the Belnap tier placement (below `USER_DERIVED`, above `LISP_ASSERTION`) must be presented to the owner before implementation. Do not proceed alone.
- `scratch/*.py` files are untracked debris — **never commit them**.
- Baseline for Phase 4 is whatever Step 3's full-suite count is (currently 727 passed).
