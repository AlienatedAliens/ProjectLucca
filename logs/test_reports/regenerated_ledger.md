# Regenerated ledger (Phase 2.3) — stated vs recomputed

**Rows: 25 | mismatches: 13**

Wilson variant: plain (no continuity correction), 95%. Single function for all rows.

## math-v1.3-fresh-500
- artifact: `logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json`
- stated: passed=420 | strict%=79.20% (396/500) | lenient%=86.60% (433/500) | CI=[80.53%, 86.95%] | commit=`4de6451`
- recomputed: passed=420/500 | Wilson plain CI=[80.53%, 86.95%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-test-25-rep
- artifact: `logs/test_reports/checkpoint_math500_test-25-reproduce.json`
- stated: passed=20 | strict%=80.00% (20/25) | lenient%=80.00% (20/25) | CI=[60.87%, 91.14%] | commit=`55d1a1f`
- recomputed: passed=20/25 | Wilson plain CI=[60.87%, 91.14%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-test-25-rep-A
- artifact: `logs/test_reports/checkpoint_math500_rep-A.json`
- stated: passed=21 | strict%=84.00% (21/25) | lenient%=84.00% (21/25) | CI=[65.35%, 93.60%] | commit=`55d1a1f`
- recomputed: passed=21/25 | Wilson plain CI=[65.35%, 93.60%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-test-25-rep-B
- artifact: `logs/test_reports/checkpoint_math500_rep-B.json`
- stated: passed=19 | strict%=76.00% (19/25) | lenient%=76.00% (19/25) | CI=[56.57%, 88.50%] | commit=`55d1a1f`
- recomputed: passed=19/25 | Wilson plain CI=[56.57%, 88.50%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-det-C
- artifact: `logs/test_reports/checkpoint_math500_det-C.json`
- stated: passed=82 | strict%=82.00% (82/100) | lenient%=88.00% (88/100) | CI=[73.33%, 88.30%] | commit=`e0a8fbf`
- recomputed: passed=82/100 | Wilson plain CI=[73.33%, 88.30%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-det-D
- artifact: `logs/test_reports/checkpoint_math500_det-D.json`
- stated: passed=82 | strict%=82.00% (82/100) | lenient%=88.00% (88/100) | CI=[73.33%, 88.30%] | commit=`e0a8fbf`
- recomputed: passed=82/100 | Wilson plain CI=[73.33%, 88.30%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-cache-on-C
- artifact: `logs/test_reports/checkpoint_math500_cache-on-C.json`
- stated: passed=83 | strict%=83.00% (83/100) | lenient%=89.00% (89/100) | CI=[74.45%, 89.11%] | commit=`e0a8fbf`
- recomputed: passed=83/100 | Wilson plain CI=[74.45%, 89.11%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-cache-on-D
- artifact: `logs/test_reports/checkpoint_math500_cache-on-D.json`
- stated: passed=84 | strict%=84.00% (84/100) | lenient%=90.00% (90/100) | CI=[75.58%, 89.90%] | commit=`e0a8fbf`
- recomputed: passed=84/100 | Wilson plain CI=[75.58%, 89.90%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## gsm-symbolic-strat-100
- artifact: `logs/test_reports/gsm_symbolic_100_templates.json`
- stated: passed=94 | strict%=94.00% (94/100) | lenient%=94.00% (94/100) | CI=[86.88%, 97.54%] | commit=`bef28b5`
- recomputed: passed=94/100 | Wilson plain CI=[87.52%, 97.22%] | source=top-level summary | artifact commit=`bef28b59`
- match: YES | commit match: YES

## humaneval-canonical-raw-164
- artifact: `logs/test_reports/humaneval_canonical_raw_164.json`
- stated: passed=155 | strict%=94.51% (155/164) | lenient%=94.51% (155/164) | CI=[89.52%, 97.30%] | commit=`bef28b5`
- recomputed: passed=155/164 | Wilson plain CI=[89.90%, 97.09%] | source=top-level summary | artifact commit=`90dbdde1`
- match: YES | commit match: **NO**

## humaneval-canonical-assisted-164
- artifact: `logs/test_reports/humaneval_canonical_assisted_164.json`
- stated: passed=154 | strict%=93.90% (154/164) | lenient%=93.90% (154/164) | CI=[88.76%, 96.87%] | commit=`bef28b5`
- recomputed: passed=154/164 | Wilson plain CI=[89.14%, 96.65%] | source=top-level summary | artifact commit=`90dbdde1`
- match: YES | commit match: **NO**

## math-v1.3-regraded-strict-posthoc
- artifact: `logs/test_reports/checkpoint_math500_v1.3-fresh-500_strict_posthoc.json`
- stated: passed=393 | strict%=78.60% (393/500) | lenient%=78.60% (393/500) | CI=[74.69%, 82.06%] | commit=`25adb03`
- recomputed: passed=393/500 | Wilson plain CI=[74.79%, 81.97%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-regraded-lenient-posthoc
- artifact: `logs/test_reports/checkpoint_math500_v1.3-fresh-500_lenient_posthoc.json`
- stated: passed=432 | strict%=78.60% (393/500) | lenient%=86.40% (432/500) | CI=[83.01%, 89.22%] | commit=`25adb03`
- recomputed: passed=432/500 | Wilson plain CI=[83.12%, 89.13%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.3-dev-400-baseline
- artifact: `logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json`
- stated: passed=319 | strict%=76.25% (305/400) | lenient%=81.50% (326/400) | CI=[71.84%, 80.16%] (S) / [77.40%, 85.00%] (L) | commit=`e0a8fbf`
- recomputed: passed=319/400 | Wilson plain CI=[75.54%, 83.40%] | source=per-item passed (pre-v1.35 grader; no strict_pass field) | artifact commit=``
- match: YES | commit match: YES

## math-v1.35-dev-400
- artifact: `logs/test_reports/checkpoint_math500_v1.35-dev-400.json`
- stated: passed=318 | strict%=74.75% (299/400) | lenient%=79.50% (318/400) | CI=[70.27%, 78.76%] (S) / [75.27%, 83.17%] (L) | commit=`deacabe`
- recomputed: passed=299/400 | Wilson plain CI=[70.27%, 78.76%] | source=per-item strict_pass | artifact commit=``
- match: **NO** | commit match: YES

## math-v1.35-dev-400-v2
- artifact: `logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json`
- stated: passed=322 | strict%=76.50% (306/400) | lenient%=80.50% (322/400) | CI=[72.10%, 80.39%] (S) / [76.33%, 84.08%] (L) | commit=`9b6858e`
- recomputed: passed=306/400 | Wilson plain CI=[72.10%, 80.39%] | source=per-item strict_pass | artifact commit=``
- match: **NO** | commit match: YES

## math-v1.35-final-fresh-500
- artifact: `logs/test_reports/checkpoint_math500_v1.35-final-fresh-500.json`
- stated: passed=451 | strict%=85.80% (429/500) | lenient%=90.20% (451/500) | CI=[82.47%, 88.59%] (S) / [87.28%, 92.51%] (L) | commit=`46486cf`
- recomputed: passed=429/500 | Wilson plain CI=[82.47%, 88.59%] | source=per-item strict_pass | artifact commit=``
- match: **NO** | commit match: YES

## 12b-math500-heldout-r0-4k
- artifact: `logs/test_reports/pal_off_ablation/checkpoint_12b_math500_heldout_100_r0_cap4096.json`
- **ERROR: artifact missing**

## 12b-math500-heldout-p2-2k
- artifact: `logs/test_reports/pal_off_ablation/checkpoint_12b_math500_heldout_100_p2_cap2048.json`
- **ERROR: artifact missing**

## e4b-math500-heldout-r1-6k
- artifact: `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e4b_math500_heldout_100_r1_cap6144.json`
- **ERROR: artifact missing**

## e4b-math500-heldout-p2-2k
- artifact: `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e4b_math500_heldout_100_p2_cap2048.json`
- **ERROR: artifact missing**

## e4b-math500-heldout-r0-4k
- artifact: `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e4b_math500_heldout_100_r0_cap4096.json`
- **ERROR: artifact missing**

## e2b-math500-heldout-r1-6k
- artifact: `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e2b_math500_heldout_100_r1_cap6144.json`
- **ERROR: artifact missing**

## e2b-math500-heldout-p2-2k
- artifact: `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e2b_math500_heldout_100_p2_cap2048.json`
- **ERROR: artifact missing**

## e2b-math500-heldout-r0-4k
- artifact: `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e2b_math500_heldout_100_r0_cap4096.json`
- **ERROR: artifact missing**
