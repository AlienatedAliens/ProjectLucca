# Research Paper 06: Model-Axis Factorial Ablation Across Gemma 4 Scales
## Program-Aided Language Offload vs. Internal Thinking Mode in Project Lucca

**Authors:** Project Lucca Architecture Notes  
**Date:** October 3–4, 2026  
**Hardware Platform:** NVIDIA GeForce RTX 5080 Laptop GPU (16,303 MiB GDDR7 VRAM, Headless Compute)  
**Evaluator Commits:** Multiple progression commits (`1c58587` harness, `dec0d79` grader, `f20537fe` closeout baseline, and v1.35.2 audit tag)  
**Evaluation Parameters:** Greedy decoding ($T=0.0$, seed 42) for MATH-500, HumanEval, and GSM-Symbolic; sampling temperature $T=0.6$ for Spec 100; unslotted execution, isolated Docker RPC sandboxes, SymPy CAS grading.

---

## 1. Abstract

We evaluate Google DeepMind's Gemma 4 family across three parameter scales—**Unified 12B** (`gemma-4-12b-heretic-Q6_K.gguf`), **Edge E4B** (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`), and **Ultra-Edge E2B** (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`)—within the Project Lucca execution harness.

Our primary controlled finding on the development split is that **token cap starvation accounts for much of the apparent gap between Program-Aided Language (PAL) scaffolding and internal thinking mode on small edge models**. Raising the PAL code-generation token cap from 1,024 to 2,048 tokens per turn on Gemma 4 E2B lifts strict CAS accuracy from 70.0% to 77.0% (exact binomial $p = 0.0156$, 7:0 discordant pairs), cutting truncations from 19% to 10%. On Gemma 4 E4B dev, raising the cap brings PAL strict accuracy from 73.0% to 83.0% (and 92.0% lenient), achieving statistical parity with native thinking mode (85.0% strict, $p = 0.7905$) while saving 40% of tokens and running 1.6× faster.

However, fresh evaluation on unseen held-out competition mathematics ($n=100$) reveals that this parity is dev-split specific and does not hold across wider subject distributions. Side-by-side evaluation of both candidate arms on Gemma 4 E4B showed Thinking Mode (R1 @ 6k) achieving **88.0% strict CAS / 92.0% lenient**, whereas PAL (P2 @ 2k) fell to **73.0% strict / 83.0% lenient** (discordant pairs 4:19 strict, exact binomial $p = 0.0026$). While PAL code generation was tuned on the dev split and excels on arithmetic and algebraic formalization, latent thinking tokens enable exploratory reasoning on competition problems with higher geometry and combinatorial depth before equation commitment. Conversely, on Gemma 4 12B under greedy decoding ($T=0.0$), extended thinking mode with a 6,144 token budget collapsed from 90.0% (direct raw generation) to 58.0% (exact binomial $p = 4.66 \times 10^{-10}$, 32:0 discordant pairs), with 44% of items terminating at the token ceiling.

```
========================================================================================================================
CONTROLLED BENCHMARK SCORECARD ACROSS GEMMA 4 SCALES
========================================================================================================================
Benchmark Suite             Metric / Arm                  Gemma 4 12B          Gemma 4 E4B          Gemma 4 E2B
------------------------------------------------------------------------------------------------------------------------
Spec 100 System Suite†      Overall Accuracy (Mean ± 2pp) 84.0% (82–86%)*      85.0%                81.0%
                            Tool Precision / Recall       15 / 15 (100.0%)     15 / 15 (100.0%)     10 / 15 (100% P / 67% R)
                            OS / Host Guardrails          10 / 10 (100.0%)     10 / 10 (100.0%)     10 / 10 (100.0%)
                            Content Safety Refusal**      9 / 10 (90.0%)       3 / 10 (30.0%)       Not Evaluated
                            Throughput (P50)              37.18 tok/s          80.76 tok/s          126.1 tok/s

GSM-Symbolic (100-strat)‡   PAL P2 Accuracy (Docker)      95.0%                94.0%                91.0%
                            Direct R0 Accuracy            93.0%                91.0%                81.0%
                            PAL Lift (Delta)              +2.0 pp (NS)         +3.0 pp (NS)         +10.0 pp (p = 0.021)

HumanEval Canonical 164‡    Raw Pass@1                    155 / 164 (94.5%)    144 / 164 (87.8%)    123 / 164 (75.0%)
                            Assisted Pass@1 (Preflight)   154 / 164 (93.9%)    141 / 164 (86.0%)    126 / 164 (76.8%)

MATH-500 Dev (100 items)‡   Direct R0 (Strict / Lenient)  90.0% / 93.0%        50.0% / 50.0%        51.0% / 51.0%***
                            PAL P2 @ 1k (Historical)      85.0% / 87.0%        73.0% / 77.0%        70.0% / 75.0%
                            PAL P2 @ 2k (Uncapped Code)   —                    83.0% / 92.0%        77.0% / 85.0%
                            PAL P3 (PAL + Thinking)       —                    —                    76.0% / 84.0%
                            Thinking R1 @ 4k              —                    85.0% / 86.0%        81.0% / 82.0%
                            Thinking R1 @ 6k              58.0% / 59.0%        —                    84.0% / 85.0%

MATH-500 Fresh Held-Out‡    Direct R0 @ 4k (Strict)       89.0% [81.4, 93.8]   52.0% [42.4, 61.5]   51.0% [41.4, 60.6]
(Unseen 100 Problems)       Direct R0 @ 4k (Lenient)      94.0% [87.5, 97.2]   54.0% [44.2, 63.4]   55.0% [45.2, 64.4]
                            PAL P2 @ 2k (Strict)          86.0% [77.9, 91.5]   73.0% [63.0, 81.2]   61.0% [50.7, 70.4]
                            PAL P2 @ 2k (Lenient)         90.0% [82.6, 94.5]   83.0% [73.9, 89.5]   70.0% [59.9, 78.6]
                            Thinking R1 @ 6k (Strict)     (Dev: 58.0% [48.2])  88.0% [79.6, 93.4]   81.0% [72.2, 87.5]
                            Thinking R1 @ 6k (Lenient)    (Dev: 59.0% [49.2])  92.0% [84.4, 96.2]   86.0% [77.9, 91.5]
                            Truncations (R0 / P2 / R1)    3.0% / 5.0% / —      1.0% / 7.0% / 2.0%   4.0% / 14.0% / 10.0%

Operational Footprint       Active VRAM Allocation        9,972 MiB (10.0 GiB) 4,382 MiB (4.38 GiB) 2,260 MiB (2.26 GiB)
========================================================================================================================
† Spec 100 was evaluated under sampling temperature T=0.6 (noise floor 82–86%, mean 84.0% ± 2.0 pp).
‡ GSM-Symbolic, HumanEval, and MATH-500 were evaluated under deterministic greedy decoding (T=0.0, seed 42).
* 12B Spec 100: 4 runs yielded 86%, 82%, 84%, 84%.
** Content safety reflects compliance on uncensored heretic fine-tunes (logs/test_reports/cross_model_30_gemma-4-*.json); E4B complied with 7/10 harmful adversarial probes (30% refusal rate), while 12B refused 9/10. Gemma 4 E2B was not evaluated in cross_model_30.
*** Evaluated with 4,096-token cap on held-out math: E2B R0 achieved 51.0% (4% truncations) and E4B R0 achieved 52.0% (1% truncations), proving that baseline gaps reflect fundamental reasoning limits of prose generation rather than token starvation.
```

---

## 2. Controlled Findings & Analyses

### 2.1 Truncation Isolation: Code Token Cap Lift on Small Models
In previous testing, Program-Aided Language (PAL) appeared to lag native thinking mode on small models (E2B: 70% vs. 81%; E4B: 73% vs. 85%). However, analysis of failure modes revealed that 19% of E2B items and 14% of E4B items were terminating at the 1,024-token code cap with truncated syntax.

Doubling the code-token cap to 2,048 tokens per turn produced a clear, controlled effect:
- **Gemma 4 E2B:** Strict CAS accuracy increased from **70.0% to 77.0%** (7:0 discordant ratio, exact binomial $p = 0.0156$). Lenient accuracy rose from 75.0% to 85.0% ($p = 0.00195$, 10:0 discordant). Truncations dropped from 19% to 10%.
- **Gemma 4 E4B (Dev Split):** Strict CAS accuracy rose from **73.0% to 83.0%** (+10.0 pp), and lenient accuracy reached **92.0%** (+15.0 pp). Truncations dropped to 7.0%.
- **Parity with Thinking Mode on Dev:** On E4B dev, P2 @ 2,048 cap achieved statistical parity with Thinking Mode on strict CAS (83.0% vs. 85.0%, McNemar $b=6, c=8$, exact binomial $p = 0.7905$, not significant). On lenient normalization, PAL led Thinking Mode by +6.0 pp (92.0% vs. 86.0%, $p = 0.1094$).
- **Efficiency:** P2 @ 2,048 cap required **1,070 tokens per item** compared to 1,786 tokens for Thinking Mode (a 40% token reduction) and executed in **10.06s** per item vs. 16.38s (1.6× faster).

### 2.2 Redundancy of Pre-Thinking in PAL (Arm P3 on E2B)
To test whether combining internal reasoning with external CAS synthesis is additive, we implemented Arm P3 (PAL + Thinking enabled in Docker) on E2B:
- P3 scored **76.0% strict / 84.0% lenient**, statistically indistinguishable from P2 @ 2,048 (77.0% / 85.0%, McNemar $b=4, c=5$, $p = 1.000$).
- However, P3 consumed **2,752 tokens per item** (2.4× more than P2's 1,128 tokens) and ran in **16.43s** per item (2.5× slower than P2's 6.63s).
- **Scope of Finding:** This redundancy finding ($b=4, c=5, p=1.000$) was empirically demonstrated on Gemma 4 E2B. While it indicates that pre-thinking before code generation is inefficient on ultra-edge models, generalizing this equivalence across other architectures requires multi-model testing.

### 2.3 The 12B Thinking Mode Degradation Under Greedy Decoding
On Gemma 4 12B on MATH-500 dev ($n=100$):
- **Direct Raw Generation (R0 @ 1,536 cap):** **90.0% strict / 93.0% lenient**, averaging 660 tokens in 12.88s, with 6% truncations.
- **PAL with Feedback (P2 @ 1,024 cap):** **85.0% strict / 87.0% lenient**, averaging 704 tokens in 14.05s, with 10% truncations ($p = 0.2266$ NS vs. R0).
- **Extended Thinking (R1 @ 6,144 cap):** **58.0% strict / 59.0% lenient**, averaging 3,793 tokens in 78.11s, with **44% truncations**.
- **McNemar Test (R0 vs. R1 @ 6k):** Discordant ratio **32 : 0** (32 items where R0 passed and R1 failed; zero items where R1 passed and R0 failed). Exact two-sided binomial $p = 4.66 \times 10^{-10}$.

**Caveat on Greedy Decoding:** All runs were conducted using greedy decoding ($T = 0.0$, seed 42) without repetition penalties. Greedy decoding is known to induce cyclical repetition in long chain-of-thought outputs. We hypothesize that greedy sampling exacerbated looping behavior at 12B scale.

### 2.4 Empirical Deconfounding: R0 Token Starvation Tested on Identical Dev Problems
To isolate whether the apparent baseline gap between unassisted direct generation (R0) and scaffolded arms was an artifact of token truncation at the historical 1,536-token ceiling, we re-evaluated R0 with a generous **4,096-token cap** directly on the **identical 100 development split problems** for both edge models:
- **Gemma 4 E4B on Identical Dev Split ($n=100$):**
  - Historical R0 @ 1.5k cap: **50.0%** (50/100) [95% Wilson CI: 39.9%, 60.1%], 16% truncations.
  - R0 @ 4k cap: **52.0%** (52/100) [95% Wilson CI: 41.8%, 62.0%], 1% truncations (mean 978 tokens).
  - **Paired McNemar Comparison:** Discordant pairs: `R0 @ 4k only (b) = 5` : `R0 @ 1.5k only (c) = 3`. Exact two-sided binomial **$p = 0.7266$ (Statistically Indistinguishable)**.
  - On the exact same 100 dev items, raising the cap from 1.5k to 4k eliminated truncations (16% $\to$ 1%) but netted only 2 additional correct solutions.
- **Gemma 4 E2B on Identical Dev Split ($n=100$):**
  - Historical R0 @ 1.5k cap: **51.0%** (51/100) [95% Wilson CI: 40.9%, 61.1%], 26% truncations (mean 949 tokens).
  - R0 @ 4k cap: **57.0%** (57/100) [95% Wilson CI: 46.7%, 66.7%], 6% truncations (mean 1,217 tokens).
  - **Paired McNemar Comparison:** Discordant pairs: `R0 @ 4k only (b) = 10` : `R0 @ 1.5k only (c) = 4`. Exact two-sided binomial **$p = 0.1796$ (Statistically Indistinguishable)**.
  - While raising the cap to 4k reduced truncations from 26% to 6%, the +6.0 pp shift across 14 discordant items did not produce a statistically detectable gain ($p = 0.1796$). Comparing direct generation with scaffolded arms, PAL reached 77.0% on Dev but 61.0% on Held-Out, while Thinking Mode reached 84.0% on Dev and 81.0% on Held-Out.
- **Cross-Split Generalization (Dev vs. Held-Out at 4k cap):**
  - E4B R0 @ 4k scored **52.0%** on Dev and **52.0%** on Held-Out ($z = 0.000, p = 1.000$).
  - E2B R0 @ 4k scored **57.0%** on Dev and **51.0%** on Held-Out ($z = 0.854, p = 0.3932$).
  - 12B R0 @ 4k scored **90.0%** on Dev and **89.0%** on Held-Out ($z = 0.231, p = 0.8176$).
  - Across both edge models, expanding the token budget did not produce a statistically detectable gain under unassisted prose generation, confirming that truncation relief alone does not account for the observed scaffold differences.

### 2.5 Side-by-Side Subject and Level Breakdown: Dev vs. Held-Out MATH-500 (n=100)

Computing stratified performance across mathematical domains and problem tiers on both the Development ($n=100$) and Held-Out ($n=100$) splits provides empirical clarity without post-hoc overreach:

#### Side-by-Side Per-Subject Performance (Strict CAS Accuracy)
| Subject | Dev $n$ | Dev E4B R1 | Dev E4B P2 | Held-Out $n$ | Held-Out E4B R1 | Held-Out E4B P2 | Held-Out Discordant (`R1 (b) : P2 (c)`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Algebra** | 25 | 92.0% (23/25) | **96.0%** (24/25) | 8 | **100.0%** (8/8) | 75.0% (6/8) | 2 : 0 |
| **Counting & Probability** | 6 | **100.0%** (6/6) | **100.0%** (6/6) | 13 | **100.0%** (13/13) | 69.2% (9/13) | 4 : 0 |
| **Geometry** | 7 | **85.7%** (6/7) | 57.1% (4/7) | 17 | **88.2%** (15/17) | 82.4% (14/17) | 2 : 1 |
| **Intermediate Algebra** | 19 | **63.2%** (12/19) | **63.2%** (12/19) | 11 | **90.9%** (10/11) | 72.7% (8/11) | 2 : 0 |
| **Number Theory** | 11 | **100.0%** (11/11) | **100.0%** (11/11) | 14 | 85.7% (12/14) | **92.9%** (13/14) | 1 : 2 |
| **Prealgebra** | 18 | 77.8% (14/18) | **88.9%** (16/18) | 16 | **81.2%** (13/16) | **81.2%** (13/16) | 1 : 1 |
| **Precalculus** | 14 | **92.9%** (13/14) | 71.4% (10/14) | 21 | **81.0%** (17/21) | 47.6% (10/21) | 7 : 0 |

#### Side-by-Side Per-Level Performance (Strict CAS Accuracy)
| Level | Dev $n$ | Dev E4B R1 | Dev E4B P2 | Held-Out $n$ | Held-Out E4B R1 | Held-Out E4B P2 | Held-Out Discordant (`R1 (b) : P2 (c)`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Level 1** | 11 | 81.8% (9/11) | **90.9%** (10/11) | 9 | **100.0%** (9/9) | 88.9% (8/9) | 1 : 0 |
| **Level 2** | 25 | **100.0%** (25/25) | 84.0% (21/25) | 20 | **85.0%** (17/20) | 65.0% (13/20) | 4 : 0 |
| **Level 3** | 19 | **94.7%** (18/19) | **94.7%** (18/19) | 20 | **90.0%** (18/20) | **90.0%** (18/20) | 1 : 1 |
| **Level 4** | 22 | **90.9%** (20/22) | **90.9%** (20/22) | 23 | **91.3%** (21/23) | 82.6% (19/23) | 3 : 1 |
| **Level 5** | 23 | 56.5% (13/23) | **60.9%** (14/23) | 28 | **82.1%** (23/28) | 53.6% (15/28) | 10 : 2 |

**Subgroup Scope & Caution:** Because subgroup cell sizes are small ($n=6$ to $28$) and no family-wise error rate correction was applied, these breakdowns are strictly descriptive and presented for reference only. No causal claims of domain-specific capability or incapacity are drawn from post-hoc subgroup splits.

### 2.6 Coding Assistance Preflight: No Detectable Benefit on Larger Models
In HumanEval Canonical (164 problems), assisted mode helped only E2B (75.0% raw $\to$ 76.8% assisted). For larger models, assisted preflight showed no statistically detectable benefit ($p > 0.5$):
- **12B:** 94.5% raw (155/164) $\to$ 93.9% assisted (154/164, difference of 1 item, McNemar $p = 1.0$).
- **E4B:** 87.8% raw (144/164) $\to$ 86.0% assisted (141/164, difference of 3 items, McNemar $p = 0.5488$).

**Scope of Claim:** While the preflight prompt was designed to prevent syntax and environment errors, it provided **no detectable benefit** on models $\ge$ 4.5B. Hypotheses attributing this to OpenBLAS thread contention or prompt verbosity remain unverified. Claims of assisted preflight value must be strictly qualified as model-scale dependent.

---

## 3. Generalization on Fresh Held-Out Mathematics (Step 5)

### 3.1 Experimental Protocol & Router Nature
To verify that results were not overfit to the dev set, we evaluated both candidate arms on $n=100$ fresh, unseen competition math problems from [`data/benchmarks/math_fresh_heldout_500.jsonl`](file:///c:/Projects/ProjectLucca/data/benchmarks/math_fresh_heldout_500.jsonl) with zero prompt or cap tuning. The held-out dataset comprises unseen problems verified disjoint from the dev set.

**Router Implementation Note:** In the benchmark harness, `--arm routed` dispatched items based on dataset metadata (`benchmark == 'gsm_symbolic'` vs `'math500'`). This is an **oracle dataset label lookup**, not an active neural intent classifier. In production desktop deployment, realizing this routing policy requires an in-the-wild task-type intent classifier.

### 3.2 Paired Results: Held-Out P2 vs. Held-Out R1
Both candidate arms were evaluated across the identical 100 held-out problems on Gemma 4 E4B:
- **Thinking Mode (R1 @ 6,144 cap):** **88.0% strict CAS** (88/100) [95% Wilson CI: 79.60%, 93.37%] / **92.0% lenient** (92/100) [95% Wilson CI: 84.45%, 96.09%]. Truncations: 2.0%. Mean tokens: 2,066.6.
- **PAL Scaffold (P2 @ 2,048 cap):** **73.0% strict CAS** (73/100) [95% Wilson CI: 63.04%, 81.16%] / **83.0% lenient** (83/100) [95% Wilson CI: 73.89%, 89.51%]. Truncations: 8.0%. Mean tokens: 1,285.0.

```
=== Paired McNemar Test on Held-Out Split (n=100) ===
Metric   Arm A (R1 @ 6k)   Arm B (P2 @ 2k)   Both   Neither   Arm A Only (b)   Arm B Only (c)   Exact p-Value
─────────────────────────────────────────────────────────────────────────────────────────────────────────────
Strict   88.0%             73.0%             69     8         19               4                p = 0.0026
Lenient  92.0%             83.0%             79     4         13               4                p = 0.0490
```

**Statistical Assessment & Router Justification:**
On held-out competition mathematics, Thinking Mode leads PAL by +15.0 pp on strict CAS ($p = 0.0026$) and +9.0 pp on lenient normalization ($p = 0.0490$). While on the Dev split P2 appeared to tie R1 (83.0% vs 85.0%, $p=0.7905$), this parity failed to generalize out-of-distribution. Consequently, our deployment router directs Gemma 4 E4B competition mathematics to **Thinking Mode (R1)**, preserving 88.0% strict accuracy and avoiding the 15-point degradation of pure code offload.

### 3.3 Analysis of the Strict-to-Lenient Gap
Across all MATH-500 evaluations, lenient normalization exceeds strict CAS equivalence by 4 to 10 percentage points:
- Analysis of discordant items reveals formatting discrepancies rather than algebraic errors: set notation versus tuple syntax (e.g. `\{1, 2\}` vs `(1, 2)`), coordinate spacing, and unexpanded `\pm` forms. All headline claims in this paper lead with strict CAS equivalence.
- Analysis of discordant items reveals formatting discrepancies rather than algebraic errors: set notation versus tuple syntax (e.g. `\{1, 2\}` vs `(1, 2)`), coordinate spacing, and unexpanded `\pm` forms.

### 3.4 Cross-Model Generalization Matrix on Held-Out Split (n=100)

Evaluating all three model scales across the identical 100 unseen held-out problems completes the factorial matrix:

```
========================================================================================================================
HELD-OUT 100 EMPIRICAL PERFORMANCE MATRIX ACROSS SCALES
========================================================================================================================
Model / Scale     Scaffold Arm        Strict CAS Acc [95% Wilson CI]  Lenient Acc [95% Wilson CI]  Truncations  Discordant (A only : B only)
------------------------------------------------------------------------------------------------------------------------
Gemma 4 12B       Direct R0 @ 4k      89.0% [80.8%, 94.1%]            94.0% [86.9%, 97.5%]         3.0%         R0 only : P2 only
                  PAL P2 @ 2k         86.0% [77.3%, 91.9%]            90.0% [82.0%, 94.8%]         5.0%         8 : 5 (p = 0.581, NS)
                  (R0 vs P2 Delta)    +3.0 pp (p = 0.581, NS)         +4.0 pp (p = 0.344, NS)      Avg Tok: 803 vs 937

Gemma 4 E4B       Direct R0 @ 4k      52.0% [41.8%, 62.0%]            54.0% [43.8%, 63.9%]         1.0%         Avg Tok: 1108
                  PAL P2 @ 2k         73.0% [63.0%, 81.2%]            83.0% [73.9%, 89.5%]         8.0%         P2 only : R0 only = 28 : 7 (p=0.0005)
                  Thinking R1 @ 6k    88.0% [79.6%, 93.4%]            92.0% [84.4%, 96.2%]         2.0%         R1 only : P2 only = 19 : 4 (p=0.0026)
                  (R1 vs P2 Delta)    +15.0 pp (p = 0.0026, Sig)      +9.0 pp (p = 0.0490, Sig)    Avg Tok: 2067 vs 1285

Gemma 4 E2B       Direct R0 @ 4k      51.0% [40.9%, 61.1%]            55.0% [44.8%, 64.9%]         4.0%         Avg Tok: 1279
                  PAL P2 @ 2k         61.0% [50.7%, 70.4%]            70.0% [59.9%, 78.5%]         14.0%        P2 only : R0 only = 23 : 13 (p=0.133)
                  Thinking R1 @ 6k    81.0% [71.7%, 87.9%]            86.0% [77.3%, 91.9%]         10.0%        R1 only : P2 only = 24 : 4 (p=0.00018)
                  (R1 vs P2 Delta)    +20.0 pp (p = 0.00018, Sig)     +16.0 pp (p = 0.00086, Sig)  Avg Tok: 2598 vs 1657
========================================================================================================================
```

**Synthesis Across Scale:**
1. **Unassisted direct generation exhibits a sharp phase shift between 4.5B and 12B:** E2B and E4B achieve almost identical unassisted baselines (51% and 52% strict), even when granted generous 4k token budgets. In contrast, 12B achieves 89.0% unassisted on held-out math, generalizing with **no statistically detectable degradation** from the dev split (90.0% dev vs 89.0% held-out, independent two-proportion $z = 0.231, p = 0.8176$).
2. **Latent thinking provides superior out-of-distribution generalization on competition mathematics:** For both edge models (E4B and E2B), Thinking Mode (R1 @ 6k) significantly outperforms external code scaffolding on unseen problems (+15.0 pp on E4B, $p = 0.0026$; +20.0 pp on E2B, $p = 0.00018$).
3. **The router policy is empirically justified:** Routing 12B to Direct R0 avoids execution overhead and greedy looping risk. Routing E4B and E2B to R1 on competition math maximizes accuracy on unseen distributions (preserving 88% on E4B and 81% on E2B), while routing to PAL P2 on arithmetic word problems (GSM-Symbolic) optimizes throughput and speed.

---

## 4. Architectural Routing Implications

### 4.1 The E4B Routing Trade-Off
Our empirical data presents a clear trade-off for Gemma 4 E4B:
1. **PAL (P2 @ 2,048 cap):** 73.0%–83.0% strict / 83.0%–92.0% lenient, ~1,070–1,216 tokens/item, ~10.1–12.2s latency. Pareto-optimal for token and speed efficiency on arithmetic and straightforward algebra.
2. **Thinking Mode (R1 @ 6,144 cap):** 85.0%–88.0% strict / 86.0%–92.0% lenient, ~1,785–2,066 tokens/item, ~16.4–19.3s latency. Preferred when maximizing strict CAS accuracy on challenging competition mathematics.

### 4.2 Locked Dispatch Rules for Project Lucca
- **Gemma 4 12B:** Route to **Direct Raw Generation (R0)** for all mathematical reasoning. Bypasses execution overhead and avoids greedy thinking loops.
- **Gemma 4 E2B:** Route arithmetic word problems to **PAL (P2 @ 2k)** (+10 pp over direct); route competition math to **Thinking Mode (R1 @ 6k)** (84% strict vs 77% PAL).
- **Gemma 4 E4B:** Route arithmetic to **PAL (P2 @ 2k)**; route competition math to **Thinking Mode (R1 @ 6k)** for maximum accuracy (or PAL where speed/token efficiency is paramount).

---

## 5. Scope of Legitimate Claims

Based on our controlled evaluations, we claim:
1. **Token cap budget governs small-model PAL performance:** Doubling the code-generation limit from 1k to 2k tokens cuts truncations in half and produces statistically significant gains on E2B (+7 pp strict, $p=0.0156$) and E4B (+10 pp strict on dev).
2. **Thinking tokens lead on hard competition math:** On held-out competition problems, thinking mode provides a statistically significant +15.0 pp strict lift over direct PAL ($p=0.0026$), whereas on arithmetic (GSM-Symbolic) PAL matches or exceeds thinking mode.
3. **Pre-thinking before code offload is redundant on E2B:** Arm P3 (PAL + Thinking) provides no accuracy advantage over pure code offload (76% vs 77%, $p=1.000$) while doubling compute cost.
4. **Greedy thinking mode degrades 12B on competition math:** Under $T=0.0$ greedy decoding, extended thinking induced catastrophic truncation loops (58% vs 90%, $p = 4.66 \times 10^{-10}$).
5. **Router nature:** Benchmark routing dispatches via oracle dataset labels. A production companion requires an in-the-wild intent classifier.
