# Pre-Registered Research Protocol: PAL-Off Factorial Model-Scale Ablation
## Deconfounding Compound Neurosymbolic Scaffolding vs. Neural Model Weights in Project Lucca

**Protocol ID:** `PROTO-LUCCA-2026-10-04-PAL-OFF`  
**Date Pre-Registered:** October 4, 2026  
**Authors:** Project Lucca Architecture & Engineering Research Group  
**Status:** Pre-Registered Experimental Protocol (Frozen Prior to Execution)  
**Target Silicon:** NVIDIA GeForce RTX 5080 Laptop GPU (16,303 MiB GDDR7 VRAM, Headless Compute)  

---

## 1. Core Research Question

> **How much of Project Lucca's benchmark performance derives from external compound scaffolding (PAL Docker execution, SymPy CAS evaluation, and Turn-2 error feedback), versus the intrinsic reasoning capacity of the neural model weights?**

Prior evaluations established that Project Lucca's compound stack achieves high scores on GSM-Symbolic (94% on 12B/E4B, 82% on E2B) and MATH-500 (86% on 12B, 73% on E4B, 60% on E2B). However, critics can reasonably argue that raw models were handicapped because native thinking (`enable_thinking=True`) was disabled during PAL code generation.

This study implements a clean **$2 \times 3$ factorial design (Model Scale $\times$ Scaffolding Arm)** on paired problem sets to rigorously deconfound scaffolding from neural capacity.

---

## 2. Experimental Factors & Study Design

### 2.1 Factor A: Model Scale (3 Tiers, Controlled Q6_K)
1. **Gemma 4 12B Unified:** `gemma-4-12b-heretic-Q6_K.gguf` (SHA256: `EA50EC1E...`)
2. **Gemma 4 E4B Edge:** `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (4.5B Effective PLE parameters)
3. **Gemma 4 E2B Ultra-Edge:** `Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf` (2.0B Effective PLE parameters)
*(Sanity Arm: Official upstream `google/gemma-4-E2B-it` Q6_K tested alongside Heretic build on R0, R1, P2).*

### 2.2 Factor B: Scaffolding Arms (4 Levels)

| Arm Code | Name | Description | Thinking Mode | Max Tokens | Execution Substrate |
| :---: | :--- | :--- | :---: | :---: | :--- |
| **`R0`** | **Raw Direct** | Direct prose solution; final answer in `\boxed{...}`; text regex extraction. | `False` | 1,536 | None (Mental) |
| **`R1`** | **Raw Thinking** | Unconstrained native CoT reasoning (`<|channel>thought`); final answer in `\boxed{...}`. | `True` | **4,096** | None (Mental) |
| **`P1`** | **PAL Turn-1** | Program-Aided Language; model writes Python/SymPy script; Docker execution; single turn. | `False` | 1,024 | Docker Container |
| **`P2`** | **PAL + Turn-2** | PAL with autonomous Turn-2 error traceback & empty stdout reprompting. | `False` | 1,024 / turn | Docker Container |

---

## 3. Benchmark Suites & Statistical Power

### 3.1 Sample Sizes ($n=500$ Paired Design)
To overcome the sampling noise of $n=100$ (where $\pm 5\text{--}8$ pp falls within confidence intervals), this ablation evaluates:
1. **Full MATH-500 Test Set ($n=500$):** All 500 problems across 7 competition subjects and 5 difficulty levels.
2. **GSM-Symbolic Stratified Battery ($n=500$):** 5 stratified instances across 100 distinct templates.

### 3.2 Grader Invariance
The exact same Computer Algebra System (SymPy CAS equivalence with strict and lenient fallback) and numeric matchers are applied uniformly across all arms (`R0`, `R1`, `P1`, `P2`), guaranteeing that the evaluation grader is not a hidden variable.

### 3.3 Statistical Testing
- Every comparison between arms is strictly **paired** on identical problem IDs.
- Significance is evaluated using **exact two-tailed McNemar's tests** on discordant pairs.
- Uncertainty is reported via **Wilson 95% Score Confidence Intervals**.
- Effect sizes are quantified via Odds Ratios (OR) and absolute percentage point deltas ($\Delta$).

---

## 4. Pre-Registered Hypotheses

Prior to executing the benchmark runs, the following hypotheses are formally registered:

1. **Hypothesis 1 (Edge Arithmetic Scaffolding Lift):**  
   On GSM-Symbolic, $P_2 > R_0$ for Gemma 4 E2B by at least **$\ge 10.0$ percentage points**, confirming that mental arithmetic severely penalizes ultra-compact edge models.
2. **Hypothesis 2 (Parameter Contraction Scaling):**  
   The scaffolding lift ($P_2 - R_0$) inversely scales with model size:  
   $$\Delta_{\text{E2B}} > \Delta_{\text{E4B}} > \Delta_{\text{12B}}$$
3. **Hypothesis 3 (Thinking Mode Asymmetry):**  
   Native thinking mode ($R_1$) will substantially narrow the gap on GSM-Symbolic (bringing $R_1 \approx P_2$), but will **fail to close the gap on MATH-500**, where calculation precision requires symbolic CAS.
4. **Hypothesis 4 (Derivation Bound Invariance):**  
   On MATH-500, `genuine_derivation_miss` rates will remain roughly invariant between $R_1$ and $P_2$, confirming that neither CoT thinking nor PAL execution can compensate for conceptual modeling deficits.

---

## 5. Formal Decision Rules

The experimental findings will be interpreted against pre-established decision gates:

| Outcome Condition | Scientific Conclusion | Action / Framing |
| :--- | :--- | :--- |
| **Condition A: $P_2 - R_1 \ge +10.0$ pp** (95% CI excludes 0) | **Definitive Scaffolding Superiority:** Compound scaffolding extractable reasoning exceeds native thinking tokens. | Scaffold-uplift claim is ratified unconditionally. |
| **Condition B: $\|P_2 - R_1\| \le 5.0$ pp** | **Accuracy Parity with Operational Superiority:** Scaffolding matches thinking accuracy while eliminating token bloat. | Reframe thesis: "Identical accuracy with deterministic safety, exact mathematics, $5\times$ lower latency, and zero KV cache bloat." |
| **Condition C: $R_1 > P_2$ by $\ge 5.0$ pp** | **Intrinsic Thinking Superiority:** Native CoT tokens explore hypothesis space better than discrete Python scripts. | Report transparently; analyze the Pareto frontier between accuracy gain vs. latency and VRAM cost. |

---

## 6. Execution Controls & Telemetry Collection

1. **Greedy Determinism:** `temperature = 0.0`, `seed = 42`.
2. **Context & Cache:** Context length 16,384 tokens; `cache_prompt = False`.
3. **Truncation Monitoring:** For $R_1$, the token cap is expanded to **4,096 tokens**, and every occurrence of `finish_reason == "length"` is logged.
4. **Hardware Telemetry:**
   - Pre-run and post-run VRAM query via `nvidia-smi`.
   - Prompt tokens, completion tokens, and thinking tokens logged per item.
   - Time-to-First-Token (TTFT) and total generation latency.
5. **Pretraining Contamination Disclosure:**
   GSM8K, MATH, and HumanEval are acknowledged to exist in web pretraining data. Absolute scores may reflect memorization; therefore, **paired relative deltas ($\Delta$) between arms** represent the sole reliable signal.
