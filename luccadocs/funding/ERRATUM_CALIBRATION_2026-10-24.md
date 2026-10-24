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
- `ce75ccc` — rewrites `docs/` references to `luccadocs/` in 115 markdown files (verified:
  each file's diff differs from its HEAD content *only* by that substitution). Ten read-only
  files under `luccadocs/archive/2026-09-17_pre_phase4_audit/` were deliberately left
  untouched. A relative-link sweep of the funding documents and `README.md` found exactly
  one remaining dead target (`./luccadocs/LUCCA_V135_1_ARCHITECTURE.md`, now pointing at
  `archive/2026-10_architecture_snapshots/`); that repair is **uncommitted**, because
  `README.md` already carries unrelated uncommitted edits.
- `6c90748` (tag `freeze-docs-2026-10-24`) — the funding-facing corrections described above
  plus this erratum. `dev-calibrated-2026-10-24` still points at `be4e016`.
- `README.md` and `RESULTS.md` carry large **uncommitted** edits (77 and 393 changed lines)
  predating this erratum. They are excluded from these commits and are **not** audited here;
  they must be reviewed before anything derived from them is submitted.

No external-model comparison appears anywhere in the funding documents, and none is
claimed. There is no Qwen-class run in `RESULTS.md`; the README benchmark table compares
only this project's own arms (12B R0, E4B R1, E2B R1).

## 7. Unregistered capability claims found in the research papers (owner decision pending)

An independent Rule-05 sweep of `luccadocs/research/papers/01_*.md` and `04_*.md` found
comparative claims with **no matching row in `RESULTS.md` or `data/benchmarks/MANIFEST.yaml`**
and no fetched external source:

- **Paper 01:76** - AIME 2024 "12B CEGIS 8/10 vs greedy Thinking 1/10". No AIME row exists in
  either ledger. The four archived V138 runs report `sympy_pct` 0.0 / 50.0 / 0.0 / 80.0, and
  two further REBENCH runs 60.0 / 80.0: the 8/10 is the single favourable run of six, and the
  sibling 30-problem artifact shows `direct_passed 0, thinking_passed 1`.
- **Paper 01:75** - CRUXEval-Input full 400, "CEGIS 82.75% vs Direct 70.25%". The raw JSON
  reproduces 331/400 and 281/400, but there is no ledger record (only `dev_50`, `sealed_100`)
  and the two arms differ in attempts and verifier, so it is not a capability lift.
- **Paper 01:77** - Spec-100 "84.0% mean (82-86% over 4 runs)": five 12B runs exist
  (86, 86, 84, 84, 82 -> mean 84.4%), and the 91.0% it dismisses belongs to a different
  harness (`spec_bench_100_run3_v1_3`), not that series.
- **Paper 01:73** - HumanEval-Plus band "91.46-92.07%" silently drops the lowest of the three
  runs it counts (MANIFEST has 151/164, 149/164 = 90.9%, 150/164).
- **Paper 01:70** - "+10 pp, p = 0.021": the 91.0 / 81.0 scores are confirmed in the
  `pal_off` artifacts, but no McNemar artifact exists; 0.021 appears only in
  `logs/test_reports/ood_generality_audit_1791730293.json`.
- **Paper 01:88** - ConceptARC "43.75% -> 28.6%": the "full 160" artifact reports
  `total_tasks 14, test_accuracy 0.2857`; 43.75% is a train-accuracy figure from a different
  artifact. Mismatched splits.
- **Paper 04:94 / TR-04:23** - plan-step latency "462.15 ms (12B) vs 0.14 ms (MicroScheme),
  50 recurrent invocations": no artifact anywhere contains 462.15 or a plan-step measurement.
- **Paper 01:26** - the assertion that TR-02/04/05 make no benchmark claims beyond `RESULTS.md`
  is false: TR-04 carries a latency table and an L1b/L2/L3/T4 scorecard with no ledger rows.
- **Code anchors** - `cegis_unshackled.py:717` (`UnshackledCEGISEngine` is at 1044),
  `cegis_python.py:90` (class at 94), `episode_recall.py:36` (class at 51).

These are **not edited here**. Registering a `MANIFEST.yaml` row for the exact run, or deleting
the lift claim, is the project owner's decision - one of those two is required for every item
above before submission. No number was changed to make documents agree.

## 8. Headline systems result in Paper 02 has no raw artifact

- **Paper 02:117 (abstract line 33, Contribution 2 lines 137-138, and `README.md:129`)** -
  "8.58x faster (46.84 ms vs 402.05 ms)" KV-cache-prefix reuse, cited to
  `logs/archive/2026-10_test_reports/bench_thinking_cache_hw.json`. That JSON contains only
  thinking-mode TTFT arms (`ttft_p50` 268.17 / 6061.32 / 269.36 ms). It contains no
  affect-injection arms and none of `402.05`, `46.84`, `18/892`, or `849/849` - in the archive
  copy or the `logs/test_reports` copy. The related "849/849 (100.0%)" also conflicts with
  `IMPLEMENTATION_WALKTHROUGH.md:702-703`, which records 849 cached / 41 uncached of 892.
- **Paper 02:32** - barge-in "<50 ms on all 50 trials" and "18.42 ms P50 slot release": no
  artifact anywhere. Grepping `logs/test_reports/`, `RESULTS.md` and
  `luccadocs/adr/0009_audio_concurrency_contract.md` for `barge`, `18.42`, `slot release`
  returns only test names.
- **Paper 02:25** - Ultravox "reduces TTFT in isolation" is an external comparison with no
  `RESULTS.md` row and no fetched URL+date. `luccadocs/archive/2026-09-17_pre_phase4_audit/14_phase0_results.md:101`
  measured 79.8 ms TTFT, and `F-BRAIN-002` records that backbone as a renamed Llama-3.1-8B.
- **Paper 03:108** - "68.4% Provenance Alignment" gate-disabled baseline exists nowhere;
  SPEC-BENCH run 3 records 91% pass / 100% faithfulness (`MANIFEST.yaml:629,1850`,
  `DECISIONS.md:345`).
- **Paper 03:112** - "P95 <= 45.0 ms" is a threshold assertion in `tests/test_memory_db.py:296`,
  not a measurement (the file's own docstring at :236 says 25 ms).
- **Paper 03:30, :93** - `user_model.py:91` is a blank line; `class UserModel` is at 105.
- **MISMATCH** - ear-to-ear 707.55 ms P50 comes from `data/eval/milestone1_baseline/loopback_cuda_raw.json`,
  measured from physical speech end at milestone 1, not `t_key_release` at v1.45.0; and
  44.5 / 54.9 ms cached TTFT is a 10-run warm slot in `ARCHITECTURE.md:261` /
  `MODEL_STRATEGY.md:108`, not part of the N=50 session it is quoted inside.

Verified clean in the same sweep, and safe to cite as-is: the NLI verifier figures
(93.0% / F1 0.942 / contradiction P-R 1.000 / 56.0-71.95 ms clean; 18.0% / recall 0.075 /
81 of 100 degraded / 57.14-70.41 ms at the 50 ms timeout) match
`data/benchmarks/nli_eval/results_cpu_t500/summary.json` exactly; the TTS guard block rates
match `tts_guard_efficacy_20261007T020151Z.json` and `RESULTS.md:233-261`; the matcher
baseline 12.5% / 4.3% matches `RESULTS.md:155-169`; confabulation 17/25 -> 0/25 matches
`MANIFEST` `confabulation_battery_v1_2`; the Allen 169-cell table really has 169 entries.