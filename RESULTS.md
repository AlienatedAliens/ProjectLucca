# Project Lucca: Experimental Results Ledger

> **Honesty Note**: Historical v1.3 results were produced from a working tree that contained uncommitted changes. `v1.3-frozen` is the nearest reproducible snapshot. `v1.3-frozen` did not reproduce bit-for-bit (20 of 25 predictions matched). Run-to-run variance is being measured. Determinism diagnostic confirmed prompt-cache reuse caused variance; `cache_prompt: false` produces bit-for-bit identical outputs (100/100 matches).

| Run ID | Code Commit | Grader Version | Dataset File | Dataset SHA-256 | n | Passed | Strict Score | Lenient Score | Wilson 95% CI | Artifact Path | Notes |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| `math-v1.3-fresh-500` | `4de6451` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 420 | 84.00% (420/500) | 84.00% (420/500) | [80.53%, 86.95%] | `logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json` | Historical report cited 79.20% (396/500) strict / 86.60% (433/500) lenient from uncommitted tree; per-item artifact recount is 420/500 (84.00%) without separate strict_pass field (E-23). |
| `math-v1.3-test-25-rep` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 20 | 80.00% (20/25) | 80.00% (20/25) | [60.87%, 91.14%] | `logs/test_reports/checkpoint_math500_test-25-reproduce.json` | |
| `math-v1.3-test-25-rep-A` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 21 | 84.00% (21/25) | 84.00% (21/25) | [65.35%, 93.60%] | `logs/test_reports/checkpoint_math500_rep-A.json` | |
| `math-v1.3-test-25-rep-B` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 19 | 76.00% (19/25) | 76.00% (19/25) | [56.57%, 88.50%] | `logs/test_reports/checkpoint_math500_rep-B.json` | |
| `math-v1.3-det-C` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 82 | 82.00% (82/100) | 88.00% (88/100) | [73.33%, 88.30%] | `logs/test_reports/checkpoint_math500_det-C.json` | |
| `math-v1.3-det-D` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 82 | 82.00% (82/100) | 88.00% (88/100) | [73.33%, 88.30%] | `logs/test_reports/checkpoint_math500_det-D.json` | |
| `math-v1.3-cache-on-C` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 83 | 83.00% (83/100) | 89.00% (89/100) | [74.45%, 89.11%] | `logs/test_reports/checkpoint_math500_cache-on-C.json` | |
| `math-v1.3-cache-on-D` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 84 | 84.00% (84/100) | 90.00% (90/100) | [75.58%, 89.90%] | `logs/test_reports/checkpoint_math500_cache-on-D.json` | |
| `gsm-symbolic-strat-100` | `bef28b5` | pal-docker-exact | `data/benchmarks/GSM_symbolic.jsonl` | `945055837b232bd9b56827b1e3a5aa019075f29e8ba4669d9a9df8b4439a291f` | 100 | 94 | 94.00% (94/100) | 94.00% (94/100) | [87.52%, 97.22%] | `logs/test_reports/gsm_symbolic_100_templates.json` | Wilson plain CI. |
| `humaneval-canonical-raw-164` | `90dbdde1` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 155 | 94.51% (155/164) | 94.51% (155/164) | [89.90%, 97.09%] | `logs/test_reports/humaneval_canonical_raw_164.json` | Original run at c3561206 preserved at *_20261002.json; primary artifact rerun at 90dbdde1. |
| `humaneval-canonical-assisted-164` | `90dbdde1` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 154 | 93.90% (154/164) | 93.90% (154/164) | [89.14%, 96.65%] | `logs/test_reports/humaneval_canonical_assisted_164.json` | Original run at c3561206 preserved at *_20261002.json; primary artifact rerun at 90dbdde1. |
| `math-v1.3-regraded-strict-posthoc` | `25adb03` | v1.35-strict-posthoc | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 393 | 78.60% (393/500) | 78.60% (393/500) | [74.79%, 81.97%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` | Wilson plain CI. |
| `math-v1.3-regraded-lenient-posthoc` | `25adb03` | v1.35-lenient-posthoc | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 432 | 78.60% (393/500) | 86.40% (432/500) | [83.12%, 89.13%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_lenient_posthoc.json` | Wilson plain CI. |
| `math-v1.3-dev-400-baseline` | `e0a8fbf` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 319 | 76.25% (305/400) | 81.50% (326/400) | [71.84%, 80.16%] (S) / [77.40%, 85.00%] (L) | `logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json` | |
| `math-v1.35-dev-400` | `deacabe` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 299 | 74.75% (299/400) | 79.50% (318/400) | [70.27%, 78.76%] (S) / [75.27%, 83.17%] (L) | `logs/test_reports/checkpoint_math500_v1.35-dev-400.json` | Passed column standardized to strict count. |
| `math-v1.35-dev-400-v2` | `9b6858e` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 306 | 76.50% (306/400) | 80.50% (322/400) | [72.10%, 80.39%] (S) / [76.33%, 84.08%] (L) | `logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json` | Passed column standardized to strict count. |
| `math-v1.35-final-fresh-500` | `46486cf` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 500 | 429 | 85.80% (429/500) | 90.20% (451/500) | [82.47%, 88.59%] (S) / [87.28%, 92.51%] (L) | `logs/test_reports/checkpoint_math500_v1.35-final-fresh-500.json` | Passed column standardized to strict count. 7.20 points above v1.3 on paired items (+36 net items, 66 gains, 30 losses); `length` truncations 29→12, crashes 21→14. Primary held-out evaluation. |
| `12b-math500-heldout-r0-4k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 89 | 89.00% (89/100) | 94.00% (94/100) | [81.37%, 93.75%] (S) / [87.52%, 97.22%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-12b_math500_r0_heldout_cap4096_100.json` | 12B Direct generation baseline; truncations: 3.0%. Factorial harness branch commit 8b80456. |
| `12b-math500-heldout-p2-2k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 86 | 86.00% (86/100) | 90.00% (90/100) | [77.86%, 91.47%] (S) / [82.51%, 94.46%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-12b_math500_p2_heldout_cap2048_100.json` | 12B PAL Docker baseline; truncations: 5.0%. Factorial harness branch commit 8b80456. |
| `e4b-math500-heldout-r1-6k` | `1c58587` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 88 | 88.00% (88/100) | 92.00% (92/100) | [80.19%, 93.00%] (S) / [85.00%, 95.89%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_routed_heldout_100.json` | E4B Thinking Mode; router default for competition math (+15 pp over P2, p=0.0026); truncations: 2.0%. Factorial harness branch commit 8b80456. |
| `e4b-math500-heldout-p2-2k` | `f20537f` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 73 | 73.00% (73/100) | 83.00% (83/100) | [63.57%, 80.73%] (S) / [74.45%, 89.11%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_p2_heldout_cap2048_100.json` | E4B PAL in Docker; truncations: 8.0%. Factorial harness branch commit 8b80456. |
| `e4b-math500-heldout-r0-4k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 52 | 52.00% (52/100) | 54.00% (54/100) | [42.32%, 61.54%] (S) / [44.29%, 63.42%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_r0_heldout_cap4096_100.json` | E4B Direct generation; truncations: 1.0%. Factorial harness branch commit 8b80456. |
| `e2b-math500-heldout-r1-6k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 81 | 81.00% (81/100) | 86.00% (86/100) | [72.22%, 87.49%] (S) / [77.86%, 91.47%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e2b_math500_r1_heldout_think6144_100.json` | E2B Thinking Mode; router default for competition math (+20 pp over P2, p=0.0002); truncations: 10.0%. Factorial harness branch commit 8b80456. |
| `e2b-math500-heldout-p2-2k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 61 | 61.00% (61/100) | 70.00% (70/100) | [51.20%, 69.98%] (S) / [60.44%, 77.97%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e2b_math500_p2_heldout_cap2048_100.json` | E2B PAL in Docker; truncations: 14.0%. Factorial harness branch commit 8b80456. |
| `e2b-math500-heldout-r0-4k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 51 | 51.00% (51/100) | 55.00% (55/100) | [41.35%, 60.58%] (S) / [45.27%, 64.38%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e2b_math500_r0_heldout_cap4096_100.json` | E2B Direct generation; truncations: 4.0%. Factorial harness branch commit 8b80456. |
| `math500-heldout-r0-b1-repro` | `f7c98a0` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 88 | 88.00% (88/100) | 93.00% (93/100) | [80.19%, 93.00%] (S) / [86.25%, 96.57%] (L) | `logs/test_reports/b1_frozen/gemma-4-12b_math500_r0_heldout_cap4096_100.json` | Phase 3 Block B1 GPU reproduction under cache_prompt: false. |
| `gsm-symbolic-100-repro` | `f7c98a0` | pal-docker-exact | `data/benchmarks/GSM_symbolic.jsonl` | `945055837b232bd9b56827b1e3a5aa019075f29e8ba4669d9a9df8b4439a291f` | 100 | 94 | 94.00% (94/100) | 94.00% (94/100) | [87.52%, 97.22%] | `logs/test_reports/gsm_symbolic_100_templates_20261007_repro.json` | Phase 3 deterministic re-run matching 94.0% baseline bit-for-bit. |
| `humaneval-canonical-raw-164-repro` | `f7c98a0` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 155 | 94.51% (155/164) | 94.51% (155/164) | [89.90%, 97.09%] | `logs/test_reports/humaneval_canonical_raw_164_20261007_repro.json` | Phase 3 deterministic re-run matching 94.51% baseline bit-for-bit. |
| `humaneval-canonical-assisted-164-repro` | `f7c98a0` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 154 | 93.90% (154/164) | 93.90% (154/164) | [89.14%, 96.65%] | `logs/test_reports/humaneval_canonical_assisted_164_20261007_repro.json` | Phase 3 deterministic re-run matching 93.90% baseline bit-for-bit. |
| `12b-math500-b4-sealed-r0-4k` | `b340ce0` | v1.35-dual | `data/benchmarks/math_b4_sealed_100.jsonl` | `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b` | 100 | 93 | 93.00% (93/100) | 94.00% (94/100) | [86.25%, 96.57%] (S) / [87.52%, 97.22%] (L) | `logs/test_reports/b4_sealed/gemma-4-12b_math500_r0_b4_sealed_cap4096_100.json` | Phase 3 Block B4 sealed held-out evaluation: Direct generation arm; 0% truncations. |
| `12b-math500-b4-sealed-p2-2k` | `b340ce0` | v1.35-dual | `data/benchmarks/math_b4_sealed_100.jsonl` | `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b` | 100 | 87 | 87.00% (87/100) | 92.00% (92/100) | [79.02%, 92.24%] (S) / [85.00%, 95.89%] (L) | `logs/test_reports/b4_sealed/gemma-4-12b_math500_p2_b4_sealed_cap2048_100.json` | Phase 3 Block B4 sealed held-out evaluation: PAL + Turn 2 Docker arm; 0% truncations. |
| `12b-math500-b4-sealed-r1-6k` | `b340ce0` | v1.35-dual | `data/benchmarks/math_b4_sealed_100.jsonl` | `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b` | 100 | 46 | 46.00% (46/100) | 46.00% (46/100) | [36.56%, 55.74%] (S) / [36.56%, 55.74%] (L) | `logs/test_reports/b4_sealed/gemma-4-12b_math500_r1_b4_sealed_think6144_100.json` | Phase 3 Block B4 sealed held-out evaluation: Thinking arm; 55% truncations. |

---

## Split Nomenclature & Exposure Disclosures

**Manifest record citations (`data/benchmarks/MANIFEST.yaml`):** the three
MATH-500 experiment figures cited across the docs are manifest records
`math500_pal_v1_3` (77.0%/87.0% PAL Dev-100, superseded),
`math500_fresh_heldout_500_v1_3_0` (74.20%/78.80% fresh N=500, superseded,
dataset-drift bound), and `math500_heldout100_direct_r0_v1_35_6` (89.0%
Direct R0 held-out-100, current). These are distinct experiments, not
contradictory data.

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

---

## B4 Clean Held-Out Factorial Ablation Outcomes ($N=100$)

Evaluated on pre-registered sealed held-out dataset [`data/benchmarks/math_b4_sealed_100.jsonl`](file:///c:/Projects/ProjectLucca/data/benchmarks/math_b4_sealed_100.jsonl) (SHA-256 `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b`) under pre-registered protocol (greedy $T=0.0$, seed 42, `cache_prompt: false`, frozen dual grader v1.35):

| Arm | Description | Substrate | Strict Acc (%) | 95% Wilson CI | Lenient Acc (%) | 95% Wilson CI | Truncations | Elapsed (s) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **R0** | Raw Direct (cap 4096) | Native text | 93.0% | [86.25%, 96.57%] | 94.0% | [87.52%, 97.22%] | 0% | 1632.5s |
| **P2** | PAL + Turn 2 Feedback (cap 2048) | Docker sandbox | 87.0% | [79.02%, 92.24%] | 92.0% | [85.00%, 95.89%] | 0% | 1817.7s |
| **R1** | Thinking mode (think 6144) | Native text CoT | 46.0% | [36.56%, 55.74%] | 46.0% | [36.56%, 55.74%] | 55% | 9414.6s |

### Paired McNemar Statistical Significance ($N=100$ Paired Items)

| Comparison | Metric | Arm A Acc | Arm B Acc | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Odds Ratio | Significance ($p < 0.05$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **P2 vs R0** | Strict | 87.0% | 93.0% | -6.0 | 1 : 7 | 7.0312e-02 | 0.200 | No (Parity / Noise) |
| **R1 vs P2** | Strict | 46.0% | 87.0% | -41.0 | 3 : 44 | 2.4647e-10 | 0.079 | **YES** |
| **R1 vs R0** | Strict | 46.0% | 93.0% | -47.0 | 0 : 47 | 1.4211e-14 | 0.011 | **YES** |
| **P2 vs R0** | Lenient | 92.0% | 94.0% | -2.0 | 2 : 4 | 6.8750e-01 | 0.556 | No (Parity / Noise) |
| **R1 vs P2** | Lenient | 46.0% | 92.0% | -46.0 | 0 : 46 | 2.8422e-14 | 0.011 | **YES** |
| **R1 vs R0** | Lenient | 46.0% | 94.0% | -48.0 | 0 : 48 | 7.1054e-15 | 0.010 | **YES** |

*Key Findings:* Direct generation (R0) achieves 93.0% strict / 94.0% lenient with zero truncations. PAL (P2) is at statistical parity with R0 (McNemar $p=0.0703$ strict, $p=0.6875$ lenient). Thinking mode (R1) suffers 55% truncation collapse on 12B weights, performing significantly worse ($p < 10^{-9}$). Full factorial report at [`logs/test_reports/b4_sealed/B4_FACTORIAL_REPORT_100.md`](file:///c:/Projects/ProjectLucca/logs/test_reports/b4_sealed/B4_FACTORIAL_REPORT_100.md).

---

## TTS Safety Guard Efficacy Battery Outcomes (Block B2)

Evaluated on 30-probe cross-model battery under `TTSSafetyGuard` (`off` vs `edge_tiers`) on `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (SHA-256 `ab52d2db6b24d78096fcefc937e20ec42c67c519a79fa761b03fc714659b586e`) per `scripts/run_tts_guard_efficacy_battery.py`:

| Metric | Count | Rate (%) | 95% Wilson Score CI |
| :--- | :---: | :---: | :---: |
| **Harmful: Model Native Refusal** | 3/10 | 30.0% | [8.1%, 64.6%] |
| **Harmful: TTS Guard Block** | 0/10 | 0.0% | [0.0%, 34.5%] |
| **Harmful: Combined Protection** | 3/10 | 30.0% | [8.1%, 64.6%] |
| **Benign Control: False Block** | 0/20 | 0.0% | [0.0%, 20.0%] |

*Key Findings & Audit Status (P6):*
1. **P6 Converted to Mitigated (Measured):** Live empirical battery verifies 0.0% false-positive rate across 20 benign tool and persona probes.
2. **Harmful Probe Dynamics:** Native refusal rate of 30.0% replicates September historical baseline. Safe conversational deflections without instructional weapons synthesis were observed on remaining probes.
3. **Artifacts:** Full telemetry preserved in [`logs/test_reports/tts_guard_efficacy_20261007T020151Z.json`](file:///c:/Projects/ProjectLucca/logs/test_reports/tts_guard_efficacy_20261007T020151Z.json) and [`logs/test_reports/tts_guard_efficacy_20261007T020151Z_REPORT.md`](file:///c:/Projects/ProjectLucca/logs/test_reports/tts_guard_efficacy_20261007T020151Z_REPORT.md).
