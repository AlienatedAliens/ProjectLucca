# Pre-Registered Protocol: Held-Out 500 & Cross-Model Scale Evaluation
## Deconfounding Generalization, Token Starvation, and Compound Scaffolding
**Protocol ID:** `PROTO-LUCCA-2026-10-05-HELDOUT-500`  
**Date Pre-Registered:** October 5, 2026  
**Status:** Pre-Registered Experimental Protocol (Frozen Prior to Execution)  
**Target Hardware:** NVIDIA GeForce RTX 5080 Laptop GPU (16 GB GDDR7, sm_120)  
**Host Process Topology:** Native `llama-server.exe` (b11026), Flash Attention ON, Q8_0 KV Cache, Context 16,384  

---

## 1. Experimental Objectives

1. **Resolve Held-Out Generalization Gap on E4B ($n=500$):**
   - Measure E4B across the full 500 held-out problems (`data/benchmarks/math_fresh_heldout_500.jsonl`) under:
     - **`R1` (Thinking Mode):** Max thinking tokens = 6,144, temperature = 0.0.
     - **`P2` (PAL + Autonomous Turn-2 Recovery):** Max code tokens = 2,048, temperature = 0.0, Docker sandbox execution.
2. **Settle the Token Starvation Confound ($n=500$):**
   - Run **`R0` (Raw Direct Solution)** with a generous cap (**4,096 tokens**) on all 500 held-out problems to prove whether earlier direct synthesis failures were caused by token starvation or by fundamental mental computation limits.
3. **Fill the Cross-Model Scale Matrix ($n=100$ Held-Out):**
   - Evaluate **Gemma 4 E2B** on held-out 100 under R1 @ 6k and P2 @ 2k.
   - Evaluate **Gemma 4 12B** on held-out 100 under R1 @ 6k and P2 @ 2k.
   - Replace all "Not Run" placeholders in Paper 06 Table 1 with validated empirical numbers.

---

## 2. Model Artifacts & Weight Verification

All models evaluated in Q6_K quantization at native context:
1. **Gemma 4 E4B:** `C:\ProjectLucca\models\llm\gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`
2. **Gemma 4 E2B:** `C:\ProjectLucca\models\llm\Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`
3. **Gemma 4 12B:** `C:\ProjectLucca\models\llm\gemma-4-12b-heretic-Q6_K.gguf`

---

## 3. Dataset Specification

- **File:** `data/benchmarks/math_fresh_heldout_500.jsonl`
- **SHA-256 Digest:** `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308`
- **Total Problems:** 500
- **Stratification:** 7 Subjects (`algebra`, `counting_and_probability`, `geometry`, `intermediate_algebra`, `number_theory`, `prealgebra`, `precalculus`) across 5 Difficulty Levels (Level 1 through Level 5).
- **Partitioning:**
  - Items 0–99: Held-Out 100 subset
  - Items 100–499: Held-Out 400 subset
  - Items 0–499: Full Held-Out 500

---

## 4. Scaffold Arm Specifications

| Arm | Description | Parameters | Sandboxed Execution |
| :---: | :--- | :--- | :--- |
| **`R1`** | Native Thinking Mode (`enable_thinking=True`) | `max_tokens=6144`, $T=0.0$ | None (Mental CoT) |
| **`P2`** | Program-Aided Language + Turn-2 Docker reprompt (`enable_thinking=False`) | `max_code_tokens=2048`, $T=0.0$ | Docker CE (`lucca-file-sandbox`) |
| **`R0`** | Direct Zero-Shot Answer (`enable_thinking=False`) | `max_tokens=4096`, $T=0.0$ | None (Prose Direct) |

---

## 5. Grading and Evaluation Consistency

All outputs are graded using identical deterministic CAS rules:
- **Strict Accuracy:** Exact numerical/symbolic boxed match.
- **Lenient / SymPy Accuracy:** SymPy algebraic equivalence via `math_equal` and normalized expression equality.
- Grader script: `lucca.eval.symbolic_grader.grade_math500_answer`.
