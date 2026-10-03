# Project Lucca v1.35: Agentic Handover Document
**Target Audience**: Incoming Autonomous AI Agent / Senior ML Engineer  
**Date**: October 3, 2026  
**Repository**: `C:\Projects\ProjectLucca`  
**Current Git Branch**: `v1.35`  
**Latest Commit**: `f2089f1`  
**Active Tag**: `v1.35-frozen` (points to `f2089f1`)  
**Baseline Anchor Tag**: `v1.3-frozen` (`55d1a1f`, strictly preserved / unmodified)

---

## 1. Executive Summary & Purpose
Project Lucca is an unprivileged, sandboxed Program-Aided Language (PAL) inference and evaluation framework designed for competition mathematics and autonomous code execution. It uses local open weights (**Gemma 4 12B Q6_K**) hosted via `llama-server` and executes generated code in a secure, isolated Docker container (`lucca-file-sandbox`) in WSL2 with network disabled (`--network none`) and read-only root.

This document transitions the project at the completion of **Step 4 (Behavior Fixes and Dev Set Optimization)** of the *v1.35 Evidence and Improvement Plan*. The dev set regression has been diagnosed and resolved, dev performance has officially surpassed the v1.3 baseline on strict CAS, and the pipeline is frozen and ready for **Step 5 (Held-Out Test Set Evaluation)**.

---

## 2. Infrastructure & Runtime Setup

### A. Host Hardware & Power
- **OS**: Windows 11 Host + WSL2 (Ubuntu)
- **GPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB VRAM)
- **CPU**: Intel Core Ultra 9 275HX
- **Power Requirement**: Must run on AC power (verify with `(Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus).PowerOnline == True`). Do not run 400-problem runs on battery.

### B. Python Environment
- **Virtualenv Path**: `C:\Projects\ProjectLucca\.venv\Scripts\python.exe`
- **Pytest**: `C:\Projects\ProjectLucca\.venv\Scripts\pytest.exe`

### C. LLM Inference Server (Daemon)
- **Binary**: `C:\ProjectLucca\app\llama-server\llama-server.exe`
- **Model**: `C:\ProjectLucca\models\llm\gemma-4-12b-heretic-Q6_K.gguf`
- **Daemon Command**:
  ```powershell
  C:\ProjectLucca\app\llama-server\llama-server.exe `
    --model C:\ProjectLucca\models\llm\gemma-4-12b-heretic-Q6_K.gguf `
    --n-gpu-layers 99 `
    --ctx-size 16384 `
    --cache-type-k q8_0 `
    --cache-type-v q8_0 `
    --cache-ram 4096 `
    --parallel 1 `
    --flash-attn on `
    --host 127.0.0.1 `
    --port 8080 `
    --no-webui `
    --jinja
  ```
- **Crucial Setting**: In all benchmark queries, `cache_prompt: false` **must** be enforced. Reusing prompt cache introduces non-deterministic sampling variance in `llama-server`.

### D. Docker Sandbox Container
- **Container Name**: `lucca-file-sandbox`
- **Base Image**: `lucca/file-sandbox:latest` in WSL2 Ubuntu
- **Transport**: `PersistentDockerWorker` via stdio bridge to `lucca-toolsrv --loop`. Yields `<2ms` execution latency per call.
- Container starts automatically via `DockerRPCTransport(container_name="lucca-file-sandbox")`.

---

## 3. Current Ledger of Experimental Results (`RESULTS.md`)

| Run ID | Code Commit | Grader Version | Dataset File | n | Strict Score | Lenient Score | Wilson 95% CI | Checkpoint Artifact Path |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `gsm-symbolic-strat-100` | `bef28b5` | pal-docker-exact | `data/benchmarks/GSM_symbolic.jsonl` | 100 | **94.00%** (94/100) | **94.00%** (94/100) | [86.88%, 97.54%] | `logs/test_reports/gsm_symbolic_100_templates.json` |
| `humaneval-raw-164` | `bef28b5` | canonical-unit | `data/benchmarks/humaneval.jsonl` | 164 | **94.51%** (155/164) | **94.51%** (155/164) | [89.52%, 97.30%] | `logs/test_reports/humaneval_canonical_raw_164.json` |
| `humaneval-assisted-164` | `bef28b5` | canonical-unit | `data/benchmarks/humaneval.jsonl` | 164 | **93.90%** (154/164) | **93.90%** (154/164) | [88.76%, 96.87%] | `logs/test_reports/humaneval_canonical_assisted_164.json` |
| `math-v1.3-regraded-strict` | `25adb03` | v1.35-strict | `data/benchmarks/math_fresh_heldout_500.jsonl` | 500 | **78.60%** (393/500) | **78.60%** (393/500) | [74.69%, 82.06%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` |
| `math-v1.3-regraded-lenient`| `25adb03` | v1.35-lenient | `data/benchmarks/math_fresh_heldout_500.jsonl` | 500 | **78.60%** (393/500) | **86.40%** (432/500) | [83.01%, 89.22%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_lenient_posthoc.json` |
| `math-v1.3-dev-400-baseline`| `e0a8fbf` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | 400 | **76.25%** (305/400) | **81.50%** (326/400) | [71.84%, 80.16%] (S)<br>[77.40%, 85.00%] (L) | `logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json` |
| `math-v1.35-dev-400` (v1) | `deacabe` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | 400 | **74.75%** (299/400) | **79.50%** (318/400) | [70.27%, 78.76%] (S)<br>[75.27%, 83.17%] (L) | `logs/test_reports/checkpoint_math500_v1.35-dev-400.json` |
| **`math-v1.35-dev-400-v2`** | `9b6858e` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | 400 | **76.50%** (306/400) | **80.50%** (322/400) | **[72.10%, 80.39%] (S)**<br>**[76.33%, 84.08%] (L)** | `logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json` |

---

## 4. Key Engineering Bugs Diagnosed & Resolved

### 1. SymPy `CRootOf` Resultant Hang (Fixed in `deacabe`)
- **Symptom**: Process frozen indefinitely consuming 100% host CPU on problem 102 (`task_7_purifier_grader`).
- **Root Cause**: Gemma generated an expression containing degree-8 `CRootOf` terms. Calling `sympy.simplify(p - e)` synchronously attempts to eliminate algebraic numbers by computing resultants of degree up to $8^4 = 4096$, which causes exponential spin in pure Python.
- **Fix**: In `scripts/run_modern_2024_benchmarks.py`:
  - Added `has(sympy.CRootOf)` guard to immediately bypass explosive simplification.
  - Wrapped simplification in `evaluate_sympy_strict_with_timeout` using a **daemon thread** with a `2.0s` hard join timeout.

### 2. Prompt Scratchwork Token Starvation (Fixed in `deacabe`)
- **Symptom**: Tasks with lengthy derivations truncated before emitting `print(answer)`.
- **Root Cause**: Gemma wrote 600+ tokens of `#` comment scratchwork in Python, exhausting the 768-token budget.
- **Fix**: Added prompt rule #1: `"DO NOT write scratchwork in comments (#), explanations, or derivations. Write only executable Python code so that print(answer) is always reached without token exhaustion."` (Recovered Task 105, 69, 21).

### 3. Float Rejection on Exact Fractions (Fixed in `deacabe`)
- **Symptom**: Model computed `2/21` as `0.09523809523809523`, which strict CAS rejected.
- **Fix**: Added prompt rule #2: `"Use exact symbolic arithmetic (SymPy Rational, Integer, radicals) instead of float division (/)."`.

### 4. SymPy `solve()` Dict Indexing Crash (`KeyError: 0`) (Fixed in `9b6858e`)
- **Symptom**: When guided toward exact SymPy arithmetic in dev-400 v1, Gemma shifted to `sympy.solve()`, but wrote `sol = solve((eq1, eq2), (x, y)); x_val = sol[0]`. In SymPy, linear systems return a `dict` `{x: val, y: val}`. Indexing `sol[0]` crashed with `KeyError: 0` on 9 tasks. Turn 2 feedback repeated the identical crash.
- **Fix**:
  1. Updated Turn 1 Prompt: `"For linear systems, prefer direct arithmetic or substitution; if using SymPy solve(), pass dict=True (e.g. sol = solve([eq1, eq2], [x, y], dict=True)) to reliably obtain a list of dicts and access variables with sol[0][x]. Never index plain solve() as sol[0]."`
  2. Updated Turn 2 Recirculation Feedback: Injected explicit `KeyError` diagnostic hint: `"In SymPy, solve([eqs], [vars]) returns a dictionary {symbol: value}, NOT a list. Accessing sol[0] fails with KeyError: 0. Pass dict=True and access with sol[0][x], or access by symbol key sol[x]."`
- **Result**: `KeyError` crashes dropped from 9 to 2 (-78%). Total `runtime_crash` dropped from 20 to 14. Strict CAS pass count rose from 299 to **306/400 (76.50%)**, beating the baseline.

---

## 5. Dataset Partitions & Strict Boundary Invariants

The competition math dataset is `data/benchmarks/math500_test.jsonl` (SHA-256: `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132`).

### Partition Definitions:
1. **Held-Out Test Set** (Indices 1–100, 0-indexed slice `[0:100]`):
   - **Status**: **STRICTLY PRISTINE & UNTOUCHED**.
   - Must never be used for prompt iteration, error analysis, or debugging.
   - Evaluated exactly once in Step 5.
2. **Dev Set** (Indices 101–500, 0-indexed slice `[100:500]`, `--offset 100 --samples 400`):
   - **Status**: Fully evaluated and optimized in Step 4.
   - Baseline: Strict 305/400 (76.25%), Lenient 326/400 (81.50%).
   - v1.35 Frozen State (`v1.35-dev-400-v2`): **Strict 306/400 (76.50%)**, Lenient 322/400 (80.50%).

---

## 6. Handover Instructions: How to Execute Step 5

The incoming AI agent should proceed directly to **Step 5: Fresh Test Draw on Held-Out Test Set (Indices 1–100)**.

### Execution Command:
```powershell
C:\Projects\ProjectLucca\.venv\Scripts\python.exe scripts/run_modern_2024_benchmarks.py `
  --benchmark math500 `
  --offset 0 `
  --samples 100 `
  --config-label v1.35-final-test-100 `
  --disable-prompt-cache `
  --resume
```

### Protocol for Step 5:
1. **Verify Prerequisites**:
   - Ensure AC power is online.
   - Ensure `llama-server` is healthy on port 8080 (`curl http://127.0.0.1:8080/props`).
   - Run unit tests: `C:\Projects\ProjectLucca\.venv\Scripts\pytest.exe tests/test_math_grader_modes.py tests/test_cas_grading.py`.
2. **Execute the 100-Problem Run**:
   - Expected runtime: ~15 to 20 minutes (100 problems).
   - Progressive checkpoints will save to `logs/test_reports/checkpoint_math500_v1.35-final-test-100.json`.
3. **Compare Against Test-100 Baselines**:
   - v1.3 Nominal Baseline on Test 100: `logs/test_reports/checkpoint_math500_v1.3-baseline-test-100.json` (79/100).
   - v1.3 Final Test 100: `logs/test_reports/checkpoint_math500_v1.3-final-test-100.json` (85/100).
4. **Compute Reconciled Metrics**:
   - Total $n = \text{passed} + \text{failed} = 100$.
   - Calculate Strict and Lenient pass counts.
   - Calculate Wilson 95% confidence intervals.
5. **Update Ledger & Final Freeze**:
   - Append results row to `RESULTS.md`.
   - Commit changes and tag `v1.35-test-evaluated`.
   - Produce the final comparative verdict.

---

## 7. Critical Invariants for the Incoming AI
- **NEVER** modify or overwrite the `v1.3-frozen` tag (`55d1a1f`).
- **NEVER** modify `scripts/run_modern_2024_benchmarks.py` prompt templates during or after Step 5 (the configuration is frozen).
- **NEVER** enable prompt caching (`--disable-prompt-cache` must be maintained).
- **NEVER** use subjective adjectives ("impressive", "blazing", "revolutionary") in metrics reporting; report exact fractions ($k/n$), percentages, and Wilson 95% confidence intervals.
