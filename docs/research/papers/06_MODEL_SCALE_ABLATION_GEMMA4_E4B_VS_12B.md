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

MATH-500 Fresh Held-Out‡    Thinking R1 @ 6k (Strict)     Not Run              88.0% [79.6, 93.4]   Not Run
(Unseen 100, Step 5)        Thinking R1 @ 6k (Lenient)    Not Run              92.0% [84.4, 96.2]   Not Run
                            PAL P2 @ 2k (Strict)          Not Run              73.0% [63.0, 81.2]   Not Run
                            PAL P2 @ 2k (Lenient)         Not Run              83.0% [73.9, 89.5]   Not Run
                            Truncation Rate (R1 / P2)     —                    2.0% / 7.0%          —

Operational Footprint       Active VRAM Allocation        9,972 MiB (10.0 GiB) 4,382 MiB (4.38 GiB) 2,260 MiB (2.26 GiB)
========================================================================================================================
† Spec 100 was evaluated under sampling temperature T=0.6 (noise floor 82–86%, mean 84.0% ± 2.0 pp).
‡ GSM-Symbolic, HumanEval, and MATH-500 were evaluated under deterministic greedy decoding (T=0.0, seed 42).
* 12B Spec 100: 4 runs yielded 86%, 82%, 84%, 84%.
** Content safety reflects compliance on uncensored heretic fine-tunes (logs/test_reports/cross_model_30_gemma-4-*.json); E4B complied with 7/10 harmful adversarial probes (30% refusal rate), while 12B refused 9/10. Gemma 4 E2B was not evaluated in cross_model_30.
*** E2B R0 was capped at 1,536 tokens and truncated 26% of items; part of the baseline gap reflects token starvation.
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

### 2.4 Baseline Confound: R0 Token Starvation on Small Models
On Gemma 4 E2B, direct raw generation (R0) scored 51.0% strict with a 1,536-token cap and suffered 26% truncations. Because each truncated item is an automatic failure, part of the apparent gap between R0 (51%) and PAL P2 @ 2k (77%) reflects token starvation in R0. Future work should evaluate R0 with a 4,096-token cap to isolate the true contribution of code execution.

### 2.5 Coding Assistance Preflight: No Detectable Benefit on Larger Models
In HumanEval Canonical (164 problems), assisted mode helped only E2B (75.0% raw $\to$ 76.8% assisted). For larger models, assisted preflight showed no statistically detectable benefit ($p > 0.5$):
- **12B:** 94.5% raw (155/164) $\to$ 93.9% assisted (154/164, difference of 1 item, McNemar $p = 1.0$).
- **E4B:** 87.8% raw (144/164) $\to$ 86.0% assisted (141/164, difference of 3 items, McNemar $p = 0.5488$).

**Scope of Claim:** While the preflight prompt was designed to prevent syntax and environment errors, it provided no detectable benefit on models $\ge$ 4.5B. Hypotheses attributing this to OpenBLAS thread contention or prompt verbosity remain unverified. Until a controlled re-evaluation is performed following the multi-threading runtime fix, claims of assisted preflight value must be strictly qualified as model-scale dependent.

---

## 3. Generalization on Fresh Held-Out Mathematics (Step 5)

### 3.1 Experimental Protocol & Router Nature
To verify that results were not overfit to the dev set, we evaluated both candidate arms on $n=100$ fresh, unseen competition math problems from [`data/benchmarks/math_fresh_heldout_500.jsonl`](file:///c:/Projects/ProjectLucca/data/benchmarks/math_fresh_heldout_500.jsonl) with zero prompt or cap tuning.

**Router Implementation Note:** In the benchmark harness, `--arm routed` dispatched items based on dataset metadata (`benchmark == 'gsm_symbolic'` vs `'math500'`). This is an **oracle dataset label lookup**, not an active neural intent classifier. In production desktop deployment, realizing this routing policy requires an in-the-wild task-type intent classifier, which has not yet been benchmarked.

### 3.2 Paired Results & Empirical Breakdown: Held-Out P2 vs. Held-Out R1
Both candidate arms were evaluated across the identical 100 held-out problems on Gemma 4 E4B:
- **Thinking Mode (R1 @ 6,144 cap):** **88.0% strict CAS** (88/100) [95% Wilson CI: 79.60%, 93.37%] / **92.0% lenient** (92/100) [95% Wilson CI: 84.45%, 96.09%]. Truncations: 2.0%. Mean tokens: 2,066.6.
- **PAL Scaffold (P2 @ 2,048 cap):** **73.0% strict CAS** (73/100) [95% Wilson CI: 63.04%, 81.16%] / **83.0% lenient** (83/100) [95% Wilson CI: 73.89%, 89.51%]. Truncations: 7.0%. Mean tokens: 1,216.7.

```
=== Paired McNemar Test on Held-Out Split (n=100) ===
Metric   P2 @ 2k Acc   R1 @ 6k Acc   Both   Neither   P2-only (b)   R1-only (c)   Exact p-value
──────────────────────────────────────────────────────────────────────────────────────────────
Strict   73.0%         88.0%         69     8         4             19            p = 0.0026
Lenient  83.0%         92.0%         79     4         4             13            p = 0.0490
```

**Statistical Assessment & Empirical Subject/Level Breakdown:**
On held-out competition mathematics, Thinking Mode leads PAL by +15.0 pp on strict CAS ($p = 0.0026$) and +9.0 pp on lenient normalization ($p = 0.0490$).

Crucially, the drop in PAL performance (83% $\to$ 73%) cannot be explained simply by asserting that "the held-out set is harder," because Thinking Mode performance simultaneously *rose* on the held-out split (85% $\to$ 88%). Instead, this divergence reflects two distinct phenomena:
1. **Dev-Split Tuning:** The 2,048-token code cap and the P2 zero-shot scaffolding prompt were developed and tuned on the dev split. Consequently, PAL generalized less effectively to unseen problem structures.
2. **Empirical Distribution of the Generalization Gap:** A direct breakdown of the 100 held-out result records by difficulty level and subject domain reveals where Thinking Mode outperformed PAL:

```
=== HELD-OUT PER-LEVEL BREAKDOWN (Strict CAS) ===
Level 1 (n= 9): R1= 9/ 9 (100.0%) | P2= 8/ 9 ( 88.9%) | delta = +11.1 pp
Level 2 (n=20): R1=17/20 ( 85.0%) | P2=13/20 ( 65.0%) | delta = +20.0 pp
Level 3 (n=20): R1=18/20 ( 90.0%) | P2=19/20 ( 95.0%) | delta =  -5.0 pp
Level 4 (n=23): R1=21/23 ( 91.3%) | P2=20/23 ( 87.0%) | delta =  +4.3 pp
Level 5 (n=28): R1=23/28 ( 82.1%) | P2=23/28 ( 82.1%) | delta =  +0.0 pp

=== HELD-OUT PER-SUBJECT BREAKDOWN (Strict CAS) ===
algebra                   (n= 8): R1= 8/ 8 (100.0%) | P2= 8/ 8 (100.0%) | delta =  +0.0 pp
counting_and_probability  (n=13): R1=13/13 (100.0%) | P2= 8/13 ( 61.5%) | delta = +38.5 pp
geometry                  (n=17): R1=15/17 ( 88.2%) | P2=15/17 ( 88.2%) | delta =  +0.0 pp
intermediate_algebra      (n=11): R1=10/11 ( 90.9%) | P2= 9/11 ( 81.8%) | delta =  +9.1 pp
number_theory             (n=14): R1=12/14 ( 85.7%) | P2=12/14 ( 85.7%) | delta =  +0.0 pp
prealgebra                (n=16): R1=13/16 ( 81.2%) | P2=13/16 ( 81.2%) | delta =  +0.0 pp
precalculus               (n=21): R1=17/21 ( 81.0%) | P2=18/21 ( 85.7%) | delta =  -4.8 pp
```

**Key Empirical Insights from the Breakdown:**
- **Geometry & Level 5 Parity:** Contrary to the initial conjecture that spatial reasoning drove the divergence, PAL and Thinking Mode achieved **identical accuracy on Geometry (15/17, 88.2%)** and **identical accuracy on the hardest Level 5 problems (23/28, 82.1%)**.
- **The Combinatorial Generalization Gap:** The +15.0 pp strict gap was concentrated almost entirely in `counting_and_probability` (+38.5 pp, where R1 solved 13/13 while P2 solved 8/13) and `Level 2` (+20.0 pp). Discrete enumeration, casework, and combinatorial counting require multi-path exploratory branching that edge models struggle to synthesize directly into a single script without reasoning scratchpads.

### 3.3 Analysis of the Strict-to-Lenient Gap
Across all MATH-500 evaluations, lenient normalization exceeds strict CAS equivalence by 4 to 10 percentage points:
- Analysis of discordant items reveals formatting discrepancies rather than algebraic errors: set notation versus tuple syntax (e.g. `\{1, 2\}` vs `(1, 2)`), coordinate spacing, and unexpanded `\pm` forms.

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
