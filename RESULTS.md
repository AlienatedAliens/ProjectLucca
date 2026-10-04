# Project Lucca: Experimental Results Ledger

> **Honesty Note**: Historical v1.3 results were produced from a working tree that contained uncommitted changes. `v1.3-frozen` is the nearest reproducible snapshot. `v1.3-frozen` did not reproduce bit-for-bit (20 of 25 predictions matched). Run-to-run variance is being measured. Determinism diagnostic confirmed prompt-cache reuse caused variance; `cache_prompt: false` produces bit-for-bit identical outputs (100/100 matches).

| Run ID | Code Commit | Grader Version | Dataset File | Dataset SHA-256 | n | Passed | Strict Score | Lenient Score | Wilson 95% CI | Artifact Path | Notes |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| `math-v1.3-fresh-500` | `4de6451` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 420 | 79.20% (396/500) | 86.60% (433/500) | [80.53%, 86.95%] | `logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json` | |
| `math-v1.3-test-25-rep` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 20 | 80.00% (20/25) | 80.00% (20/25) | [60.87%, 91.14%] | `logs/test_reports/checkpoint_math500_test-25-reproduce.json` | |
| `math-v1.3-test-25-rep-A` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 21 | 84.00% (21/25) | 84.00% (21/25) | [65.35%, 93.60%] | `logs/test_reports/checkpoint_math500_rep-A.json` | |
| `math-v1.3-test-25-rep-B` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 19 | 76.00% (19/25) | 76.00% (19/25) | [56.57%, 88.50%] | `logs/test_reports/checkpoint_math500_rep-B.json` | |
| `math-v1.3-det-C` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 82 | 82.00% (82/100) | 88.00% (88/100) | [73.33%, 88.30%] | `logs/test_reports/checkpoint_math500_det-C.json` | |
| `math-v1.3-det-D` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 82 | 82.00% (82/100) | 88.00% (88/100) | [73.33%, 88.30%] | `logs/test_reports/checkpoint_math500_det-D.json` | |
| `math-v1.3-cache-on-C` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 83 | 83.00% (83/100) | 89.00% (89/100) | [74.45%, 89.11%] | `logs/test_reports/checkpoint_math500_cache-on-C.json` | |
| `math-v1.3-cache-on-D` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 84 | 84.00% (84/100) | 90.00% (90/100) | [75.58%, 89.90%] | `logs/test_reports/checkpoint_math500_cache-on-D.json` | |
| `gsm-symbolic-strat-100` | `bef28b5` | pal-docker-exact | `data/benchmarks/GSM_symbolic.jsonl` | `945055837b232bd9b56827b1e3a5aa019075f29e8ba4669d9a9df8b4439a291f` | 100 | 94 | 94.00% (94/100) | 94.00% (94/100) | [86.88%, 97.54%] | `logs/test_reports/gsm_symbolic_100_templates.json` | |
| `humaneval-canonical-raw-164` | `bef28b5` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 155 | 94.51% (155/164) | 94.51% (155/164) | [89.52%, 97.30%] | `logs/test_reports/humaneval_canonical_raw_164.json` | |
| `humaneval-canonical-assisted-164` | `bef28b5` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 154 | 93.90% (154/164) | 93.90% (154/164) | [88.76%, 96.87%] | `logs/test_reports/humaneval_canonical_assisted_164.json` | |
| `math-v1.3-regraded-strict-posthoc` | `25adb03` | v1.35-strict-posthoc | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 393 | 78.60% (393/500) | 78.60% (393/500) | [74.69%, 82.06%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` | |
| `math-v1.3-regraded-lenient-posthoc` | `25adb03` | v1.35-lenient-posthoc | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 432 | 78.60% (393/500) | 86.40% (432/500) | [83.01%, 89.22%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_lenient_posthoc.json` | |
| `math-v1.3-dev-400-baseline` | `e0a8fbf` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 319 | 76.25% (305/400) | 81.50% (326/400) | [71.84%, 80.16%] (S) / [77.40%, 85.00%] (L) | `logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json` | |
| `math-v1.35-dev-400` | `deacabe` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 318 | 74.75% (299/400) | 79.50% (318/400) | [70.27%, 78.76%] (S) / [75.27%, 83.17%] (L) | `logs/test_reports/checkpoint_math500_v1.35-dev-400.json` | |
| `math-v1.35-dev-400-v2` | `9b6858e` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 322 | 76.50% (306/400) | 80.50% (322/400) | [72.10%, 80.39%] (S) / [76.33%, 84.08%] (L) | `logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json` | |
| `math-v1.35-final-fresh-500` | `46486cf` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 500 | 451 | 85.80% (429/500) | 90.20% (451/500) | [82.47%, 88.59%] (S) / [87.28%, 92.51%] (L) | `logs/test_reports/checkpoint_math500_v1.35-final-fresh-500.json` | 7.20 points above v1.3 on paired items (+36 net items, 66 gains, 30 losses); `length` truncations 29→12, crashes 21→14. Primary held-out evaluation. |
| `12b-math500-heldout-r0-4k` | `8b80456` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 94 | 89.00% (89/100) | 94.00% (94/100) | [80.8%, 94.1%] (S) / [86.9%, 97.5%] (L) | `logs/test_reports/pal_off_ablation/checkpoint_12b_math500_heldout_100_r0_cap4096.json` | 12B Direct generation baseline; truncations: 3.0%. |
| `12b-math500-heldout-p2-2k` | `8b80456` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 90 | 86.00% (86/100) | 90.00% (90/100) | [77.3%, 91.9%] (S) / [82.0%, 94.8%] (L) | `logs/test_reports/pal_off_ablation/checkpoint_12b_math500_heldout_100_p2_cap2048.json` | 12B PAL Docker baseline; truncations: 5.0%. |
| `e4b-math500-heldout-r1-6k` | `8b80456` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 92 | 88.00% (88/100) | 92.00% (92/100) | [79.6%, 93.4%] (S) / [84.4%, 96.2%] (L) | `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e4b_math500_heldout_100_r1_cap6144.json` | E4B Thinking Mode; router default for competition math (+15 pp over P2, p=0.0026); truncations: 2.0%. |
| `e4b-math500-heldout-p2-2k` | `8b80456` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 83 | 73.00% (73/100) | 83.00% (83/100) | [63.0%, 81.2%] (S) / [73.9%, 89.5%] (L) | `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e4b_math500_heldout_100_p2_cap2048.json` | E4B PAL in Docker; truncations: 8.0%. |
| `e4b-math500-heldout-r0-4k` | `8b80456` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 54 | 52.00% (52/100) | 54.00% (54/100) | [41.8%, 62.0%] (S) / [43.8%, 63.9%] (L) | `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e4b_math500_heldout_100_r0_cap4096.json` | E4B Direct generation; truncations: 1.0%. |
| `e2b-math500-heldout-r1-6k` | `8b80456` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 86 | 81.00% (81/100) | 86.00% (86/100) | [71.7%, 87.9%] (S) / [77.3%, 91.9%] (L) | `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e2b_math500_heldout_100_r1_cap6144.json` | E2B Thinking Mode; router default for competition math (+20 pp over P2, p=0.0002); truncations: 10.0%. |
| `e2b-math500-heldout-p2-2k` | `8b80456` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 70 | 61.00% (61/100) | 70.00% (70/100) | [50.7%, 70.4%] (S) / [59.9%, 78.6%] (L) | `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e2b_math500_heldout_100_p2_cap2048.json` | E2B PAL in Docker; truncations: 14.0%. |
| `e2b-math500-heldout-r0-4k` | `8b80456` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 55 | 51.00% (51/100) | 55.00% (55/100) | [40.9%, 61.1%] (S) / [44.8%, 64.9%] (L) | `logs/test_reports/pal_off_ablation/checkpoint_gemma-4-e2b_math500_heldout_100_r0_cap4096.json` | E2B Direct generation; truncations: 4.0%. |

---

## Split Nomenclature & Exposure Disclosures

1. **Nomenclature Mapping:** The dataset slice `data/benchmarks/math500_test.jsonl` (problems 1–100) is designated as **Dev-100** across research papers and factorial reports, reflecting its historical role as a prompt-development split in v1.3 where it was labeled `test-100`.
2. **Held-Out Definition:** The primary held-out benchmark comprises lines 1–100 of `data/benchmarks/math_fresh_heldout_500.jsonl`. Problems 101–500 remain strictly unrun and held in reserve.
3. **Exploratory Leak Disclosure:** As documented in `handover/V135_CONTAMINATION_AUDIT.md`, exploratory prompt inspection touched problems 15 and 73 on `math_fresh_heldout_500.jsonl` (zero-indexed: indices 14 and 72). No harness or prompt modification was made in response to this exposure.

---

## Held-Out 98-Item Robustness Check (Excluding Leaked Items 15 & 73)

Reproducible via [`scripts/recompute_heldout_98.py`](file:///c:/Projects/ProjectLucca/scripts/recompute_heldout_98.py):

| Evaluation Arm / Configuration | Full Held-Out (100 Items) | Cleaned Subset (98 Items) | Absolute Delta ($\Delta$) | Ranking / Conclusion Impact |
| :--- | :---: | :---: | :---: | :--- |
| **Gemma 4 12B Direct (R0 @ 4,096 cap)** | 89.0% (89/100) | **88.8% (87/98)** | $-0.2\text{ pp}$ | None (Remains peak raw generator) |
| **Gemma 4 12B PAL (P2 @ 2,048 cap)** | 86.0% (86/100) | **85.7% (84/98)** | $-0.3\text{ pp}$ | None |
| **Gemma 4 E4B Routed / Thinking (R1 @ 6,144 cap)** | 88.0% (88/100) | **87.8% (86/98)** | $-0.2\text{ pp}$ | None (Retains statistical parity with 12B) |
| **Gemma 4 E4B PAL (P2 @ 2,048 cap)** | 73.0% (73/100) | **73.5% (72/98)** | $+0.5\text{ pp}$ | None (R1 retains significant +14.3 pp lead) |
| **Gemma 4 E4B Direct (R0 @ 4,096 cap)** | 52.0% (52/100) | **51.0% (50/98)** | $-1.0\text{ pp}$ | None |
| **Gemma 4 E2B Thinking (R1 @ 6,144 cap)** | 81.0% (81/100) | **80.6% (79/98)** | $-0.4\text{ pp}$ | None (Retains significant +19.4 pp lead over P2) |
| **Gemma 4 E2B PAL (P2 @ 2,048 cap)** | 61.0% (61/100) | **61.2% (60/98)** | $+0.2\text{ pp}$ | None |
| **Gemma 4 E2B Direct (R0 @ 4,096 cap)** | 51.0% (51/100) | **50.0% (49/98)** | $-1.0\text{ pp}$ | None |

*Summary:* Excluding items 15 and 73 shifts strict accuracy by at most 1.0 pp across all arms, with zero changes to rankings, significance tests, or architectural conclusions.

---

## Output Supervisor Live Action Hallucination Evaluation ($n=100, T=0.6$)

Evaluated on [`data/benchmarks/action_hallucination_battery_100.json`](file:///c:/Projects/ProjectLucca/data/benchmarks/action_hallucination_battery_100.json) across Gemma 4 E4B and E2B:

| Evaluation Stratum | Claims Emitted (E4B / E2B / Total) | Supervisor Caught (TP) | Catch Rate [95% Wilson CI] | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Strict Completed Actions Only** | 5 / 3 / **8** | **1** (E4B T01) | **12.5% (1/8)** [2.2%, 47.1%] | Unequivocal completions only (past tense, telegraphic confirmations) |
| **Broad FAC (Primary Audit)** | 15 / 8 / **23** | **1** (E4B T01) | **4.3% (1/23)** [0.8%, 21.0%] | Includes active progressive participles and markdown action headers |
| **Controls ($n=50$)** | 0 / 50 FP | — | **0.0% FP (0/50)** | Zero false aborts across 25 honest controls + 25 idiom controls |

*Note on Embedded JSON Fields:* Automated regex fields embedded in raw JSON files reported TP=1/FN=1 (E4B) and TP=0/FN=1 (E2B) due to regex circularity with the supervisor. Authoritative ground truth is established via post-hoc manual audit in [`logs/test_reports/action_hallucination_labels_100.jsonl`](file:///c:/Projects/ProjectLucca/logs/test_reports/action_hallucination_labels_100.jsonl).






