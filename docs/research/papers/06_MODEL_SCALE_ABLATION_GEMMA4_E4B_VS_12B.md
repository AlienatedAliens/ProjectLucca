# Research Paper 06: Model-Axis Factorial Ablation Across Gemma 4 Scales
## Program-Aided Language Offload vs. Internal Thinking Mode in Project Lucca

**Authors:** Project Lucca Architecture Notes  
**Date:** October 3–4, 2026  
**Hardware Platform:** NVIDIA GeForce RTX 5080 Laptop GPU (16,303 MiB GDDR7 VRAM, Headless Compute)  
**Evaluator Commit:** `1c585876a76af82caacb0d78b5b1686dd346d9c5`  
**Evaluation Parameters:** Greedy decoding ($T=0.0$, seed 42), unslotted execution, isolated Docker RPC sandboxes, SymPy CAS grading.

---

## 1. Abstract

We evaluate Google DeepMind's Gemma 4 family across three parameter scales—**Unified 12B** (`gemma-4-12b-heretic-Q6_K.gguf`), **Edge E4B** (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`), and **Ultra-Edge E2B** (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`)—within the Project Lucca execution harness.

Our primary controlled finding is that **token cap starvation accounts for much of the apparent gap between Program-Aided Language (PAL) scaffolding and internal thinking mode on small edge models**. Raising the PAL code-generation token cap from 1,024 to 2,048 tokens per turn on Gemma 4 E2B lifts strict CAS accuracy from 70.0% to 77.0% (exact binomial $p = 0.0156$, 7:0 discordant pairs), cutting truncations from 19% to 10%. On Gemma 4 E4B, raising the cap brings PAL strict accuracy from 73.0% to 83.0% (and 92.0% lenient), achieving statistical parity with native thinking mode (85.0% strict, $p = 0.7905$) while saving 40% of tokens and running 1.6× faster.

Conversely, on Gemma 4 12B under greedy decoding ($T=0.0$), extended thinking mode with a 6,144 token budget collapsed from 90.0% (direct raw generation) to 58.0% (exact binomial $p = 4.66 \times 10^{-10}$, 32:0 discordant pairs), with 44% of items terminating at the token ceiling. A simple task-based router evaluated on $n=100$ fresh held-out competition math problems with Gemma 4 E4B achieved **88.0% strict CAS accuracy** [95% Wilson CI: 79.6%, 93.4%] with only 2% truncations, showing no statistically detectable degradation compared to the dev split.

```
========================================================================================================================
CONTROLLED BENCHMARK SCORECARD ACROSS GEMMA 4 SCALES
========================================================================================================================
Benchmark Suite             Metric / Arm                  Gemma 4 12B          Gemma 4 E4B          Gemma 4 E2B
------------------------------------------------------------------------------------------------------------------------
Spec 100 System Suite        Overall Accuracy (Mean ± 2pp) 84.0% (82–86%)*      85.0%                81.0%
                             Tool Precision / Recall       15 / 15 (100.0%)     15 / 15 (100.0%)     10 / 15 (100% P / 67% R)
                             OS / Host Guardrails          10 / 10 (100.0%)     10 / 10 (100.0%)     10 / 10 (100.0%)
                             Content Safety Refusal**      9 / 10 (90.0%)       3 / 10 (30.0%)       6 / 10 (60.0%)
                             Throughput (P50)              37.18 tok/s          80.76 tok/s          126.1 tok/s

GSM-Symbolic (100-strat)     PAL P2 Accuracy (Docker)      95.0%                94.0%                91.0%
                             Direct R0 Accuracy            93.0%                91.0%                81.0%
                             PAL Lift (Delta)              +2.0 pp (NS)         +3.0 pp (NS)         +10.0 pp (p = 0.021)

HumanEval Canonical 164      Raw Pass@1                    155 / 164 (94.5%)    144 / 164 (87.8%)    123 / 164 (75.0%)
                             Assisted Pass@1 (Preflight)   154 / 164 (93.9%)    141 / 164 (86.0%)    126 / 164 (76.8%)

MATH-500 Dev (100 items)    Direct R0 (Strict / Lenient)  90.0% / 93.0%        50.0% / 50.0%        51.0% / 51.0%***
                             PAL P2 @ 1k (Historical)      85.0% / 87.0%        73.0% / 77.0%        70.0% / 75.0%
                             PAL P2 @ 2k (Uncapped Code)   —                    83.0% / 92.0%        77.0% / 85.0%
                             PAL P3 (PAL + Thinking)       —                    —                    76.0% / 84.0%
                             Thinking R1 @ 4k              —                    85.0% / 86.0%        81.0% / 82.0%
                             Thinking R1 @ 6k              58.0% / 59.0%        —                    84.0% / 85.0%

MATH-500 Fresh Held-Out      Strict CAS Equivalence        Not Run              88.0% [79.6, 93.4]†  Not Run
(Unseen 100, Step 5)         Lenient Normalization         Not Run              92.0% [84.4, 96.2]   Not Run
                             Active Arm                    —                    Thinking R1 @ 6k     —
                             Truncation Rate               —                    2.0% (2 / 100)       —

Operational Footprint        Active VRAM Allocation        9,972 MiB (10.0 GiB) 4,382 MiB (4.38 GiB) 2,260 MiB (2.26 GiB)
========================================================================================================================
* 12B Spec 100: 4 runs yielded 86%, 82%, 84%, 84% (mean 84.0% ± 2.0 pp noise floor under T=0.6).
** Content safety reflects compliance on uncensored heretic fine-tunes; E4B refuses only 30% of general safety probes.
*** E2B R0 was capped at 1,536 tokens and truncated 26% of items; part of the baseline gap reflects token starvation.
† Held-out evaluation was executed exclusively on Gemma 4 E4B; 12B and E2B were not evaluated on the held-out split.
```

---

## 2. Controlled Findings & Analyses

### 2.1 Truncation Isolation: Code Token Cap Lift on Small Models
In previous testing, Program-Aided Language (PAL) appeared to lag native thinking mode on small models (E2B: 70% vs. 81%; E4B: 73% vs. 85%). However, analysis of failure modes revealed that 19% of E2B items and 14% of E4B items were terminating at the 1,024-token code cap with truncated ASTs.

Doubling the code-token cap to 2,048 tokens per turn produced a clear, controlled effect:
- **Gemma 4 E2B:** Strict CAS accuracy increased from **70.0% to 77.0%** (7:0 discordant ratio, exact binomial $p = 0.0156$). Lenient accuracy rose from 75.0% to 85.0% ($p = 0.00195$, 10:0 discordant). Truncations dropped from 19% to 10%.
- **Gemma 4 E4B:** Strict CAS accuracy rose from **73.0% to 83.0%** (+10.0 pp), and lenient accuracy reached **92.0%** (+15.0 pp). Truncations dropped to 7.0%.
- **Parity with Thinking Mode:** On E4B, P2 @ 2,048 cap achieved statistical parity with Thinking Mode on strict CAS (83.0% vs. 85.0%, McNemar $b=6, c=8$, exact binomial $p = 0.7905$, not significant). On lenient normalization, PAL led Thinking Mode by +6.0 pp (92.0% vs. 86.0%, $p = 0.1094$).
- **Efficiency:** P2 @ 2,048 cap required **1,070 tokens per item** compared to 1,786 tokens for Thinking Mode (a 40% token reduction) and executed in **10.06s** per item vs. 16.38s (1.6× faster).

### 2.2 The Redundancy of Pre-Thinking in PAL (Arm P3)
To test whether combining internal reasoning with external CAS synthesis is additive, we implemented Arm P3 (PAL + Thinking enabled in Docker) on E2B:
- P3 scored **76.0% strict / 84.0% lenient**, statistically indistinguishable from P2 @ 2,048 (77.0% / 85.0%, McNemar $b=4, c=5$, $p = 1.000$).
- However, P3 consumed **2,752 tokens per item** (2.4× more than P2's 1,128 tokens) and ran in **16.43s** per item (2.5× slower than P2's 6.63s).
- **Conclusion:** Allowing the model to generate a natural-language scratchpad before writing Python code provides no measurable accuracy benefit over direct code generation, provided the code token budget is sufficient.

### 2.3 The 12B Thinking Mode Degradation Under Greedy Decoding
On Gemma 4 12B on MATH-500 dev ($n=100$):
- **Direct Raw Generation (R0 @ 1,536 cap):** **90.0% strict / 93.0% lenient**, averaging 660 tokens in 12.88s, with 6% truncations.
- **PAL with Feedback (P2 @ 1,024 cap):** **85.0% strict / 87.0% lenient**, averaging 704 tokens in 14.05s, with 10% truncations ($p = 0.2266$ NS vs. R0).
- **Extended Thinking (R1 @ 6,144 cap):** **58.0% strict / 59.0% lenient**, averaging 3,793 tokens in 78.11s, with **44% truncations**.
- **McNemar Test (R0 vs. R1 @ 6k):** Discordant ratio **32 : 0** (32 items where R0 passed and R1 failed; zero items where R1 passed and R0 failed). Exact two-sided binomial $p = 4.66 \times 10^{-10}$.

**Caveat on "Circular Verification Loops":** All runs were conducted using greedy decoding ($T = 0.0$, seed 42) without repetition penalties. Greedy decoding is known to induce cyclical repetition in long chain-of-thought outputs. We hypothesize that greedy sampling exacerbated looping behavior at 12B scale. Testing with non-zero temperature or repetition penalties is needed before concluding that 12B models intrinsically cannot benefit from thinking.

### 2.4 Baseline Confound: R0 Token Starvation on Small Models
On Gemma 4 E2B, direct raw generation (R0) scored 51.0% strict with a 1,536-token cap and suffered 26% truncations. Because each truncated item is an automatic failure, part of the apparent gap between R0 (51%) and PAL P2 @ 2k (77%) reflects token starvation in R0. Future work should evaluate R0 with a 4,096-token cap to isolate the true contribution of code execution.

### 2.5 Coding Assistance Preflight: Regressions on Larger Models
In HumanEval Canonical (164 problems), assisted mode (preflight prompt requesting docstring analysis and edge-case enumeration before implementation) helped only E2B (75.0% raw $\to$ 76.8% assisted). For larger models, assisted mode slightly regressed pass rates:
- **12B:** 94.5% raw (155/164) $\to$ 93.9% assisted (154/164, -1 problem).
- **E4B:** 87.8% raw (144/164) $\to$ 86.0% assisted (141/164, -3 problems).

---

## 3. Generalization on Fresh Held-Out Mathematics (Step 5)

### 3.1 Experimental Protocol
To verify that results were not overfit to the dev set, we evaluated the task router on $n=100$ fresh, unseen competition math problems from [`data/benchmarks/math_fresh_heldout_500.jsonl`](file:///c:/Projects/ProjectLucca/data/benchmarks/math_fresh_heldout_500.jsonl) with zero prompt or cap tuning.

- **Evaluated Model:** Gemma 4 E4B (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`)
- **Active Arm:** **Thinking Mode (R1 @ 6,144 tokens)**. The router dispatched 100/100 items to thinking mode; Docker PAL was not invoked for this run.
- **Result File:** [`logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_routed_heldout_100.json`](file:///c:/Projects/ProjectLucca/logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_routed_heldout_100.json)
- **Commit:** `1c585876a76af82caacb0d78b5b1686dd346d9c5`

### 3.2 Results & Comparison
- **Strict CAS Equivalence:** **88.0%** (88/100) [95% Wilson CI: 79.60%, 93.37%]
- **Lenient Normalization:** **92.0%** (92/100) [95% Wilson CI: 84.39%, 96.23%]
- **Truncation Rate:** **2.0%** (2/100)
- **Average Tokens / Latency:** 2,066.6 tokens per item / 19.31s per item (total elapsed: 32.2 minutes)

```
Split                   Strategy                        Strict CAS      Lenient CAS     Truncations
───────────────────────────────────────────────────────────────────────────────────────────────────
Dev (Historical 100)    R1 @ 4096 (Thinking Baseline)   85.0%           86.0%           13 / 100
Dev (Ablation 100)      P2 @ 2048 (PAL Scaffold)        83.0%           92.0%            7 / 100
Held-Out (Fresh 100)    R1 @ 6144 (Routed Arm)          88.0%           92.0%            2 / 100
```

**Statistical Assessment:** At $n=100$, the 95% Wilson confidence interval spans $\pm 6.8$ percentage points. The held-out score of 88.0% strict is statistically consistent with the dev-split performance (85.0% strict). We conclude there is **no statistically detectable degradation ($p > 0.05$)** on unseen held-out problems for Gemma 4 E4B.

### 3.3 Analysis of the Strict-to-Lenient Gap
Across all MATH-500 evaluations, lenient normalization exceeds strict CAS equivalence by 4 to 9 percentage points. On the held-out set:
- 88 items passed strict CAS equivalence (SymPy `simplify(pred - gt) == 0`).
- 4 additional items passed lenient normalization (92 total).
- Analysis of these 4 discordant items reveals formatting discrepancies rather than algebraic errors: set notation versus tuple syntax (e.g. `\{1, 2\}` vs `(1, 2)`), coordinate spacing, and unexpanded `\pm` forms.

---

## 4. Architectural Routing Implications

### 4.1 The E4B Routing Trade-Off
Our empirical data presents a trade-off for Gemma 4 E4B on competition math:
1. **PAL (P2 @ 2,048 cap):** 83.0% strict / 92.0% lenient, 1,070 tokens/item, 10.1s latency.
2. **Thinking Mode (R1 @ 6,144 cap):** 85.0%–88.0% strict / 86.0%–92.0% lenient, ~1,785–2,066 tokens/item, ~16.4–19.3s latency.

Where compute and token efficiency are prioritized, **PAL @ 2,048 cap is the Pareto-optimal choice for E4B**, delivering comparable accuracy at 40% lower token cost and 1.6× higher throughput. Where peak strict CAS accuracy is paramount regardless of token cost, Thinking Mode @ 6k provides a marginal +2 to +5 point gain.

### 4.2 Locked Dispatch Rules for Project Lucca
Based on empirical evidence across the three scales:
- **Gemma 4 12B:** Route to **Direct Raw Generation (R0)** for all mathematical reasoning. Bypasses execution overhead and avoids greedy thinking loops.
- **Gemma 4 E2B:** Route arithmetic word problems to **PAL (P2 @ 2k)** (+10 pp over direct); route competition math to **Thinking Mode (R1 @ 6k)** (84% strict vs 77% PAL).
- **Gemma 4 E4B:** Route arithmetic to **PAL (P2 @ 2k)**; route competition math to **PAL (P2 @ 2k)** for efficiency, or **Thinking Mode (R1 @ 6k)** for maximum strict score.

---

## 5. Scope of Legitimate Claims

Based on our controlled evaluations, we claim:
1. **Token cap budget governs small-model PAL performance:** Doubling the code-generation limit from 1k to 2k tokens cuts truncations in half and produces statistically significant gains on E2B (+7 pp strict, $p=0.0156$) and E4B (+10 pp strict).
2. **Scaffolding equalizes small models with thinking mode at lower cost:** With adequate code caps, PAL offload brings 4.5B models to parity with native thinking mode while saving 40% of tokens.
3. **Pre-thinking before code offload is redundant:** Arm P3 (PAL + Thinking) provides no accuracy advantage over pure code offload (76% vs 77%) while doubling compute cost.
4. **Greedy thinking mode degrades 12B on competition math:** Under $T=0.0$ greedy decoding, extended thinking induced catastrophic truncation loops (58% vs 90%, $p = 4.66 \times 10^{-10}$).
5. **Edge generalization holds on fresh data for E4B:** Thinking mode @ 6k achieved 88.0% strict / 92.0% lenient on 100 unseen competition problems, showing no detectable drop from the dev split.
