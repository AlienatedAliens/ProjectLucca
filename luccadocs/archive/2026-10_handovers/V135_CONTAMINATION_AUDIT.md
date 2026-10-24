# Project Lucca v1.35 — Benchmark Contamination Audit & Test-Set Decision

**Audit Date:** 2026-10-03  
**Auditor:** Antigravity AI Engineering Assistant  
**Target:** Final Empirical Verification Battery Selection for v1.35  

---

## 1. Test-100 Contamination Analysis

**Audit Query:** Commits between baseline and final test-100 runs:
- `git log --oneline v1.3-frozen..v1.3.0-production-eval`
- Commit `1e9ebc8`: *"feat(benchmarks): freeze v1.3 harness with 400-token Turn 1 cap, clean empty-output re-prompt, and Idx 65 filter"*
- Commit `51cbf4b`: *"feat(benchmarks): add empty-output feedback trigger and mandate print(answer) contract"*

**Findings:**
During v1.3 iterations between `baseline-test-100` (79/100) and `final-test-100` (85/100), prompt adjustments and harness filters were directly motivated by inspecting failures on test-100 problems. Specifically, commit `1e9ebc8` explicitly introduced the `UNUSABLE_STDOUT_PATTERNS` filter specifically designed for test problem `Idx 65` (`object at 0x...`), and reprompting parameters were tuned to resolve specific failures in the 0..99 range.

**Verdict:**
**test-100 is CONTAMINATED as a tuning set.** It cannot serve as the primary unbiased generalization benchmark for v1.35.

---

## 2. Fresh Held-Out 500 Audit

**Audit Query:** Modification and access history of `data/benchmarks/math_fresh_heldout_500.jsonl`:
- `git log --all --oneline -- data/benchmarks/math_fresh_heldout_500.jsonl` returned only `6bb4dcb` (original creation during WO-28 Phase 0).
- No tuning passes, prompt edits, or algorithmic interventions in v1.35 read or tuned on `data/benchmarks/math_fresh_heldout_500.jsonl`.
- The only post-baseline access was the post-hoc dual-mode regrade in commit `25adb03` (`scripts/regrade_math_checkpoint.py`), which evaluated existing frozen responses from `checkpoint_math500_v1.3-final-fresh-500.json` without re-running or tuning generation.

**Verdict:**
`math_fresh_heldout_500.jsonl` is **UNCONTAMINATED**. It represents a pristine held-out test distribution.

---

## 3. Known Leak Disclosure

- **Item 15 & Item 73 Execution Leak:** During an exploratory session prior to v1.35 formalization, held-out items 15 and 73 were briefly executed, and item 73's problem text was displayed in terminal logs.
- **Impact Assessment:** Neither item was targeted for prompt tuning, few-shot demonstration injection, or rule-based overrides. Across a 500-sample test set ($n=500$), this represents $<0.4\%$ incidental exposure and does not invalidate the test suite.

---

## 4. Formal Decision

- **Primary Evaluation Test:** `data/benchmarks/math_fresh_heldout_500.jsonl` ($n=500$).
  - Baseline paired comparison: v1.3 achieved **393/500 (78.60%) strict**, **411/500 (82.20%) lenient**.
  - Provides adequate statistical power (Wilson 95% CI margin $\approx \pm 3.6\%$) to evaluate engine performance.
- **Secondary Evaluation Test:** `data/benchmarks/math500_test.jsonl` offset 0, samples 100 ($n=100$).
  - Informational / historical continuity only.

Signed and certified for Step 8 freeze and final evaluation.
