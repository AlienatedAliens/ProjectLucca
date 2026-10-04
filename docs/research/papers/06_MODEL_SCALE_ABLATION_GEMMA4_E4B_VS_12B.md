# Research Paper 06: Compound Neurosymbolic Scaffolding Under Parameter Contraction
## A 3-Way Model Scale Factorial Ablation: Gemma 4 12B vs. E4B vs. E2B in Project Lucca

**Title:** Compound Neurosymbolic Scaffolding Under Parameter Contraction: A Factorial Model-Axis Ablation of Gemma 4 12B, E4B, and E2B in Project Lucca  
**Date:** October 3–4, 2026  
**Authors:** Project Lucca Architecture & Engineering Research Group  
**Target Architecture:** Project Lucca Sovereign Edge Agent (v1.35.1-stable / v1.4.0-dev)  
**Hardware Platform:** NVIDIA GeForce RTX 5080 Laptop GPU (16,303 MiB GDDR7 VRAM, Headless Compute)  
**Evaluator Commit:** `1c585876a76af82caacb0d78b5b1686dd346d9c5`  
**Status:** Frozen Empirical Specification & Final Experimental Receipts  

---

## 1. Abstract & Executive Scorecard

We present a comprehensive, multi-scale factorial ablation evaluating **Google DeepMind's Gemma 4 family** across three parameter orders of magnitude—**Unified 12B** (`gemma-4-12b-heretic-Q6_K.gguf`), **Edge E4B** (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`), and **Ultra-Edge E2B** (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`)—within the **Project Lucca** compound neurosymbolic sovereign agent architecture. 

All evaluations were executed under strictly frozen controls with unslotted execution, deterministically isolated Docker RPC sandboxes, exact SymPy CAS grading, and paired McNemar statistical significance testing across five core benchmarks:

```
========================================================================================================================
EXECUTIVE SCORECARD: 3-WAY MODEL SCALE FACTORIAL ABLATION (PROJECT LUCCA v1.35.1)
========================================================================================================================
Evaluation Suite             Metric                     Gemma 4 12B          Gemma 4 E4B          Gemma 4 E2B
------------------------------------------------------------------------------------------------------------------------
Spec 100 System Suite        Total Score                86 / 100 (86.0%)     85 / 100 (85.0%)     81 / 100 (81.0%)
                             Tool Precision / Recall    15 / 15 (100.0%)     15 / 15 (100.0%)     10 / 15 (100% P / 67% R)
                             Safety Refusal Invariant   10 / 10 (100.0%)     10 / 10 (100.0%)     10 / 10 (100.0%)
                             Total Suite Latency        181.4 s              76.6 s               46.6 s (3.89x Faster)
                             P50 Throughput             37.18 tok/s          80.76 tok/s          126.1 tok/s

GSM-Symbolic (100-strat)     Stratified PAL Pass Rate   95 / 100 (95.0%)     94 / 100 (94.0%)     91 / 100 (91.0%)
                             Mean LLM Latency           6.23 s               2.25 s               1.40 s (4.45x Faster)

HumanEval Canonical 164      Raw Pass@1                 155 / 164 (94.5%)    144 / 164 (87.8%)    123 / 164 (75.0%)
                             Assisted Pass@1            154 / 164 (93.9%)    141 / 164 (86.0%)    126 / 164 (76.8%)

MATH-500 Dev (Direct R0)     Strict CAS Equivalence     90 / 100 (90.0%)     50 / 100 (50.0%)     51 / 100 (51.0%)
MATH-500 Dev (PAL P2 @ 2k)   Strict CAS / Lenient       85.0% / 87.0%        83.0% / 92.0%        77.0% / 85.0%
MATH-500 Dev (Thinking R1)   Strict CAS / Lenient       58.0% / 59.0%        85.0% / 86.0%        84.0% / 85.0% (6k)

MATH-500 Fresh Held-Out      Strict CAS Equivalence     [Routed: 90.0%]      88.0% [79.6, 93.4]   [Routed: 84.0%]
(Unseen 100, Step 5)         Lenient Normalization      [Routed: 93.0%]      92.0% [84.4, 96.2]   [Routed: 85.0%]

Operational Footprint        VRAM Allocation            9,972 MiB (10.0 GiB) 4,382 MiB (4.38 GiB) 2,260 MiB (2.26 GiB)
                             Throughput Range           ~37.2 tok/s          80.8 – 103 tok/s     126.1 – 169.1 tok/s
========================================================================================================================
```

---

## 2. Key Empirical Findings

### 2.1 The 12B Reasoning Crossover (Why Thinking Mode Failed on 12B)
On competition mathematics (MATH-500 dev, $n=100$), a critical non-linearity emerged across parameter scale:
- **Direct Raw Generation (R0):** Gemma 4 12B solves **90.0% strict / 93.0% lenient** in an average of **12.88 seconds** (660 tokens per item) with only 6% truncations.
- **PAL Scaffolding (P2 @ 1k):** Achieved **85.0% strict / 87.0% lenient** ($p=0.2266$ NS vs. R0).
- **Extended Thinking (R1 @ 6k cap):** Collapsed to **58.0% strict / 59.0% lenient**, exhausting compute on **44.0% of all items** (3,793 avg tokens, 78.1s avg latency).
- **Exact McNemar Significance:** Comparing R0 to R1 @ 6k yielded a discordant ratio of **32 : 0** (**32 items where R0 won, zero items where R1 won**), with an exact two-sided binomial $p$-value of:
  $$p = 4.66 \times 10^{-10}$$
- **Mechanistic Cause:** The 12B unified model enters circular verification loops under extended unconstrained scratchpads, re-deriving already-correct steps until hitting the token ceiling. In contrast, direct decoding emits concise, mathematically sound proofs immediately.

### 2.2 Truncation Isolation on Small Edge Models (E2B & E4B)
Under the historical 1,024-token code cap, PAL scaffolding appeared to lag native thinking mode on small models (E2B scored 70% vs. 81% R1; E4B scored 73% vs. 85% R1). By expanding the code token limit to 2,048 tokens (`--max-code-tokens 2048`), we isolated the true truncation effect:
- **Gemma 4 E2B:**
  - Strict accuracy jumped from **70.0% to 77.0%** ($p = 0.0156$, **statistically significant**, 7:0 discordant ratio).
  - Lenient accuracy jumped from **75.0% to 85.0%** ($p = 0.00195$, **statistically significant**, 10:0 discordant ratio).
  - Truncation count dropped by half from 19 to 10.
- **Gemma 4 E4B:**
  - Strict accuracy surged from **73.0% to 83.0%** (+10.0 pp).
  - Lenient accuracy surged from **77.0% to 92.0%** (+15.0 pp).
  - Truncation count dropped to 7.0%.
  - **Parity with Thinking Mode:** P2 @ 2,048 cap reached statistical parity with Thinking Mode on strict CAS ($83\% \text{ vs } 85\%$, $p = 0.7905$) and **outperformed Thinking Mode on lenient normalization by +6.0 pp (92.0% vs. 86.0%)**, while saving **40% of tokens** (1,070 vs. 1,786) and running **1.6× faster**.

### 2.3 The Redundancy of Pre-Thinking in PAL (Arm P3)
Testing Arm P3 (PAL + Thinking enabled in Docker) on E2B demonstrated that pre-thinking before code synthesis is redundant:
- P3 scored **76.0% strict / 84.0% lenient**, statistically identical to P2 @ 2,048 (77.0% / 85.0%, $p = 1.000$, 4:5 discordant).
- However, P3 required **2.4× more tokens** (2,752 vs. 1,128) and ran **2.5× slower** (16.4s vs. 6.6s). Providing an adequate token budget for direct code generation eliminates the need for prior natural-language reasoning.

### 2.4 Pre-Registered Held-Out Generalization (Step 5)
Evaluating the locked router on $n=100$ completely fresh, unseen competition mathematics problems ([`math_fresh_heldout_500.jsonl`](file:///c:/Projects/ProjectLucca/data/benchmarks/math_fresh_heldout_500.jsonl)) with zero tuning yielded:
- **Strict CAS Equivalence:** **88.0%** (88/100) [95% Wilson CI: 79.60% – 93.37%]
- **Lenient Normalization:** **92.0%** (92/100) [95% Wilson CI: 84.39% – 96.23%]
- **Truncation Rate:** **2.0%** (2/100)
- **Generalization Finding:** Zero degradation between dev and held-out splits, confirming that the compound scaffolding and routing rules generalize to unseen mathematical problem distributions.

---

## 3. The Project Lucca 1.35.1 Dynamic Routing Specification

Based on the empirical evidence, the Project Lucca task router enforces the following frozen dispatch logic:

$$\text{Router}(M, T) = \begin{cases} 
\text{Direct Raw Generation (R0)} & \text{if } M = \text{12B} \\ 
\text{PAL in Docker (P2, cap=2048)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Arithmetic/Word} \\ 
\text{Thinking Mode (R1, cap=6144)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Competition Math} 
\end{cases}$$

---

## 4. Hardware Efficiency & Deployment Topology

| Model Tier | Active VRAM | TTFT (P50) | Throughput (P50) | Target Role in Project Lucca |
| :--- | :---: | :---: | :---: | :--- |
| **Gemma 4 E2B** | **2.26 GiB** | **73.2 ms** | **126.1 tok/s** | Ultra-low power edge companion, continuous ambient listener |
| **Gemma 4 E4B** | **4.38 GiB** | **86.1 ms** | **80.8 tok/s** | **Default sovereign agent core**: 85% Spec 100, 94% GSM, 92% MATH, native vision |
| **Gemma 4 12B** | **9.97 GiB** | **286.9 ms** | **37.2 tok/s** | On-demand symbolic prover & direct competition mathematics escalation |
