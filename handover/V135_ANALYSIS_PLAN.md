# Project Lucca v1.35 — Analysis Plan

**Date:** 2026-10-03  
**Status:** Frozen as `v1.35.1-frozen`  
**Execution Condition:** Pre-registered before running final test sets. Zero post-run modifications permitted.

---

## Pre-Registered Evaluation Plan

> Primary metric: strict CAS. Primary set: fresh_heldout_500, label `v1.35-final-fresh-500`. Comparison: paired per-item vs `checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` (393/500). Report: strict, lenient, Wilson 95% CI, paired gains/losses, failure-class counts. Secondary: test-100, label `v1.35-final-test-100`, vs v1.3 final-test-100 (85/100), informational only (CI ±8–9 pts). **No code or prompt change after this run. Result is reported as-is.**

---

## Detailed Evaluation Specifications

### 1. Primary Evaluation Battery: Fresh Held-Out 500
- **Dataset:** `data/benchmarks/math_fresh_heldout_500.jsonl` ($n=500$)
- **Configuration Label:** `v1.35-final-fresh-500`
- **Harness Flags:** `--benchmark math500 --dataset-path data/benchmarks/math_fresh_heldout_500.jsonl --samples 500 --config-label v1.35-final-fresh-500 --disable-prompt-cache --resume`
- **Baseline Reference:** `checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` (Score: 393/500 strict, 78.60% [74.77%, 82.01%])
- **Metrics to Report:**
  - Strict Accuracy ($k/500$) & Wilson 95% Confidence Interval
  - Lenient Accuracy ($k/500$) & Wilson 95% Confidence Interval
  - Paired per-item comparison against v1.3 baseline (Gains, Losses, Net churn)
  - Failure classification breakdown (`runtime_crash`, `finish_reason=length`, etc.)
  - Ledger artifact: `logs/test_reports/v135_final_fresh500_ledger.md`

### 2. Secondary Evaluation Battery: Test-100 (Informational)
- **Dataset:** `data/benchmarks/math500_test.jsonl` offset 0, samples 100 ($n=100$)
- **Configuration Label:** `v1.35-final-test-100`
- **Harness Flags:** `--benchmark math500 --offset 0 --samples 100 --config-label v1.35-final-test-100 --disable-prompt-cache --resume`
- **Baseline Reference:** v1.3 `final-test-100` (85/100)
- **Note:** Deemed contaminated as a tuning set per `handover/V135_CONTAMINATION_AUDIT.md`. Included solely for historical continuity.

### 3. Reporting and Done Protocol
- Results will be appended to `RESULTS.md` with file SHA-256 hashes and Wilson score intervals.
- The Git tag `v1.35-test-evaluated` will be created immediately upon test closeout.
- No tuning, prompting, or code adjustments will be performed regardless of outcome.
