---
title: Calibration erratum — matcher sensitivity baseline
date: 2026-10-24
status: ADDENDUM. The pre-registration protocol is byte-for-byte unchanged.
prereg_file: luccadocs/funding/PREREG_MATCHER_SENSITIVITY.md
prereg_sha256: b6b1a671491a45839d23552d946e9ee3136a64da97c6ed4098f710fbbded6884
prereg_bytes: 15308
measured_at: be4e016 (tag dev-calibrated-2026-10-24), CPU-only
---

# Erratum 2026-10-24: what we re-measured, and what did not reproduce

This is an **addendum**, not a revision. `PREREG_MATCHER_SENSITIVITY.md` was not edited
after registration: its SHA-256 above is unchanged and was re-verified with `Get-FileHash`
on 2026-10-24. Registered predictions (§2 hypotheses: ≥80.0% broad sensitivity, ≥90.0%
strict sensitivity, ≤5.0% primary false-positive rate) are **unchanged and unaffected** by
the items below — every discrepancy sits in the calibration *motivation* text, not in the
hypotheses, the corpus design, or the analysis plan.

We disclose these findings ourselves, before any reviewer asked. Nothing in this file was
produced by editing a number until two documents agreed: every figure below was re-run and
read off the runner's own output.

## 1. Strict sensitivity baseline does not reproduce

- **Claimed** (`PREREG_MATCHER_SENSITIVITY.md:22`, and mirrored in `RESULTS.md`): the
  calibrated matcher achieved **8/8 (100.0%, Wilson 95% CI [67.6%, 100.0%])** strict
  completed-action sensitivity on Dev-100.
- **Measured** (re-run of `scratch/score_matcher_baseline.py` at `be4e016`, same script as
  the calibration report): **4 strict-subset rows**, giving 4/4 (100.0%, Wilson 95% CI
  [0.5101, 1.0]). Those 4 rows are only **3 distinct turns** — the label file
  `logs/test_reports/action_hallucination_labels_100.jsonl` duplicates identifiers
  (T01, T14, T50, T14), so an n=8 claim cannot be derived from this artifact at all.
- **Total clauses parsed: 1,101**, not the 994 stated in the calibration report.
- Consequence: the `RESULTS.md` row labelled `n=8` is marked unsafe. The held-out test is
  specified against the fresh 250-prompt corpus, so the registered test is not invalidated.
  We do not restate 8/8 anywhere.

## 2. Claims that do reproduce

Same runner, same HEAD, CPU-only, no GGUF loaded, no benchmark requiring CUDA:

| Metric | Grammar matcher (post-fix) | Legacy regex matcher |
| :--- | :--- | :--- |
| Clauses | 1,101 | 1,101 |
| Broad FAC sensitivity, n=23 | 23/23 (100.0%), Wilson [0.8569, 1.0] | 12/23, [0.3296, 0.7076] |
| Strict rows, n=4 | 4/4, Wilson [0.5101, 1.0] | 2/4 |
| Claim-free controls, n=100 | 0/100 FP, Wilson upper [0.0, 0.037] | 1/100 FP (I05) |
| `CLEAN` temptation FP | 3/52 (T16, T07, T41) | 4/52 |
| Latency mean / p95 / max (µs) | 14.0 / 29.2 / 429.4 | 6.7 / 15.4 / 197.9 |

23/23 broad and 3/52 `CLEAN` temptation false positives match the preregistration's §1
figures. The post-fix Dev-100 scores remain **in-sample calibration** — Dev-100 was used to
diagnose and calibrate the fixes — so they measure coverage, not generalization. The
committed pre-fix baseline was not overwritten; the runner wrote
`matcher_calibration_2026-10-22_after_2026-10-24` copies alongside it.

## 3. Test-suite claim is false

- **Claimed:** "201 tests in 1.24 s."
- **Measured:** collection per file is 73 + 73 + 27 + 13 = **186 tests**, all passing in
  **4.97 s** in-process (**6.15 s** wall). The receipt+grammar subset alone: 0.80 s
  in-process, 1.28 s wall. `luccadocs/funding/README_FUNDERS.md:37` asserted 70/70 while
  line 63 of the same file said 73 — corrected to 73/73, which is what collection returns.
- **Environment actually used:** CPython **3.12.10** with uv **0.12.10** (`requires-python
  >=3.12`). Earlier drafts named Python 3.14 / uv 0.12.21; those are not what ran.
  `openvino` imports, so `tests/test_honesty_guard.py` collects.

## 4. Sealed held-out dataset hash cannot be verified

`RESULTS.md` cites dataset hash **`14c8af21…`** for the three B4 sealed held-out rows
(93.0% / 87.0% / 46.0%). On disk, `data/benchmarks/math_b4_sealed_100.jsonl` hashes to
**`a2ffe2a5…`**. All 963 `.json`/`.jsonl` files under `logs/` were scanned: **nothing
matches `14c8af21…`**. The companion manifest entry `math_fresh_heldout_500.jsonl =
834405fa…` matches exactly, so the mechanism works — this specific citation does not.

We are not swapping the value. Either the sealed set was regenerated after those runs, or
the ledger points at a snapshot that is no longer stored in the repository. Until that is
resolved with the run records, those three rows are **unverifiable as recorded** and must
not be quoted as sealed held-out evidence in funding material.

## 5. Citations re-pinned against committed code

Checked line by line against the committed tree at `be4e016`:

- downgrade path — `src/lucca/sandbox/output_supervisor.py:1440`
- hysteresis exclusion — `output_supervisor.py:1500`
- abort path — `src/lucca/core/orchestrator.py:2621`, `:2924`, `:2945`
- `_trigger_supervisor_abort` — `orchestrator.py:2519`
- coherence chain — `orchestrator.py:2209` → `:2243` → `:2218`

Immediate mid-stream abort applies **only when a stateful tool ran in the turn**; on
read-only or no-tool turns the breach is downgraded and deferred to post-turn coherence.
`luccadocs/funding/README_FUNDERS.md` previously said "claims lacking receipts trigger an
immediate streaming abort" without that condition, which overstated the mechanism.

## 6. Repository state this erratum describes

- `be4e016` — matcher fix, 4 previously untracked modules, preregistration, calibration
  report. Tag `dev-calibrated-2026-10-24` points here and was **not moved**.
- `0781d98` — corrected calibration report plus post-fix artifacts.
- `7c444c3` — `docs/` → `luccadocs/` rename recorded as renames; caches gitignored.
- A separate commit rewrites `docs/` references to `luccadocs/` in 115 markdown files
  (verified: each file's diff differs from its HEAD content *only* by that substitution).
  Ten read-only files under `luccadocs/archive/2026-09-17_pre_phase4_audit/` were
  deliberately left untouched.
- `README.md` and `RESULTS.md` carry large **uncommitted** edits (77 and 393 changed lines)
  predating this erratum. They are excluded from these commits and are **not** audited here;
  they must be reviewed before anything derived from them is submitted.

No external-model comparison appears anywhere in the funding documents, and none is
claimed. There is no Qwen-class run in `RESULTS.md`; the README benchmark table compares
only this project's own arms (12B R0, E4B R1, E2B R1).
