# Project Lucca — Benchmark & Experiment Reproduction Guide

This guide provides step-by-step instructions for reproducing Project Lucca's unit test suites, static architectural gates, and cognitive benchmarks.

> **Status & Call for Independent Reproduction:**  
> All reported metrics in this repository are author-measured on a single development workstation (`Intel Core Ultra 9 275HX`, `NVIDIA GeForce RTX 5080 Laptop GPU`, native Windows 11 64-bit). Independent reproduction by third-party researchers on alternative hardware is actively sought.

---

## 1. System Requirements

### Hardware Requirements
- **dGPU (Inference & ASR):** NVIDIA GeForce RTX 4080/5080 Laptop GPU (16 GB GDDR7) or desktop equivalent (`compute_capability >= 8.9`).
  - *Dedicated Compute Mode:* In Windows Display Settings, set display output to Intel iGPU to ensure 100% of dGPU VRAM is dedicated to compute.
- **CPU:** Multi-core x86_64 processor (Intel Core Ultra 9 275HX or equivalent AMD Ryzen 9).
- **RAM:** 32 GB minimum (64 GB recommended for concurrent Docker + GGUF model residency).
- **Storage:** 100 GB free SSD storage (NVMe recommended for fast GGUF weight loading).

### Software Requirements
- **OS:** Windows 11 Pro / Enterprise 64-bit (Build >= 22631).
- **WSL2:** Ubuntu 22.04 LTS or 24.04 LTS.
- **Docker CE:** Running inside Ubuntu WSL2 (Docker Desktop or native Docker engine in WSL2).
- **Python:** Python 3.12+ managed via `uv`.
- **NVIDIA Drivers:** Version >= 560.xx supporting CUDA 12.6+.

---

## 2. Environment Verification

Before running any benchmarks, verify that your local environment passes all hardware and runtime checks:

```powershell
# 1. Check Python dependencies and virtual environment
uv sync

# 2. Run the 10-point environmental self-diagnostic
uv run python -m lucca.core.env_check
```

---

## 3. Tier 0 & Tier 1 Test Suites (No GPU Required)

The deterministic test suite validates all symbolic reasoning, AST compilers, Z3 constraint solving, cryptographic provenance gates, and UI state logic without requiring live GPU inference:

### 3.1 Static Architectural Gates (24 Gates, ~6s)
Verifies strict zero-`Any` typing, lack of fabricated metrics, model manifests, and architectural contracts:
```powershell
uv run pytest -q tests/test_static_gates.py
```
*Expected Result:* `24 passed in ~6s (100% green)`

### 3.2 Full Scaffolding & Scaffolding Regression Suite (~90s)
Runs the entire deterministic unit and integration test battery:
```powershell
uv run pytest -q -m "not tier2 and not hw and not soak and not net"
```
*Expected Result:* `1,679+ passed, 1 skipped, 73 deselected in ~90s`

#### Understanding the 73 Deselected Tests
The 73 deselected tests are intentionally excluded from fast CPU-only regression runs because they require active local hardware or long-running processes:
- **Live Neural Brain Tests (`@pytest.mark.tier2`, 21 tests):** Requires native `llama-server.exe` with loaded Gemma weights (`test_a1_live_hw.py`, `test_capability_assessment_live_hw.py`, `test_rag_live_hw.py`).
- **Live Hardware Audio Rings (`@pytest.mark.hw`, 24 tests):** Tests shared-memory audio buffers, WASAPI capture, and real-time push-to-talk state transitions (`test_phase1_live_hw.py`, `test_phase2_live_hw.py`).
- **Live Docker Container Execution (13 tests):** Validates raw container RPC, cgroup resource limits, and network namespace confinement (`test_milestone2_container_execution.py`).
- **External Network Search (`@pytest.mark.net`, 3 tests):** Validates live duckduckgo / web search failover against public search APIs (`test_search_providers_net.py`).
- **Soak & Rollup Endurance Tests (`@pytest.mark.soak`, 2 tests):** Multi-hour, 150-turn conversational stress runs (`test_soak_live_hw.py`, `test_soak_memory_growth.py`).
- **Process Supervisor Lifecycle Tests (10 tests):** Tests multi-process SIGTERM coordination across ZeroMQ channels.

### 3.3 Truth-in-Receipt Formal Battery (73 Tests, <1s)
Validates the syntactic action verb extractor, receipt unifier, and epistemic hedge exemption policy:
```powershell
uv run pytest -q tests/test_truth_in_receipt_battery.py
```
*Expected Result:* `73 passed in ~0.5s`

---

## 4. Headline Cognitive Benchmark Reproduction

### Benchmark Configuration Distinction
It is critical to distinguish between two fundamentally different evaluation configurations:
1. **Direct Model Baseline (Direct R0):** Bare token prediction from the neural brain without tool invocation, code execution, or compiler preflight.
2. **Compound Neurosymbolic Scaffold (PAL + Feedback Loop):** Multi-turn execution where the model writes Python/SymPy code, executes it inside Docker CE, parses runtime stdout/stderr, and uses compiler preflight rewrites with 2-turn error recovery.

### 4.1 Track 1: Compound Cognitive Battery (`SPEC-BENCH-100-v1.0`)
- **Dataset:** `data/benchmarks/spec_bench_100_v1_0.jsonl` (SHA-256: `35dc4108...`)
- **Sample Size:** 100 problems across 10 cognitive domains (MicroScheme LISP, Allen temporal algebra, mereotopology, deontic planning).
- **Execution Command:**
  ```powershell
  uv run python -m lucca.benchmarks.run_spec_bench --dataset data/benchmarks/spec_bench_100_v1_0.jsonl --output logs/test_reports/spec_bench_run.json
  ```
- **Author Result:** 91.0% pass rate (91/100). Path policy compliance: 100.0%. Epistemic faithfulness: 100.0%.
- **Caveat:** Authored benchmark designed specifically to test compound cognitive integration.

### 4.2 Track 2: Canonical HumanEval (pass@1 in Docker)
- **Dataset:** OpenAI HumanEval (164 coding tasks).
- **Execution Command:**
  ```powershell
  uv run python -m lucca.benchmarks.run_humaneval --container-rpc --output logs/test_reports/humaneval_run.json
  ```
- **Author Result:** 95.73% pass@1 (157 / 164) assisted via compiler preflight and execution feedback.
- **Caveat:** Evaluated under a 2-turn execution-feedback loop in Docker; bare direct model pass@1 is substantially lower (~72%).

### 4.3 Track 2: GSM8K PAL Mode
- **Author Result:** 100.0% on 30-item micro-suite (30/30, Wilson 95% CI: 88.7%–100.0%); 95.75% on full 1,319-problem dataset (`gsm8k_pal_full_1319_v1_3`).
- **Caveat:** Note the sample size disparity: micro-suite is $n=30$.

### 4.4 Track 3: MATH-500 Held-Out 100
- **Dataset:** `data/benchmarks/math_fresh_heldout_500.jsonl` (lines 1-100).
- **Author Result:** 89.0% on 12B Direct R0 (88.8% on 98-item clean held-out set); 88.0% on E4B Thinking Mode R1 @ 6k; 81.0% on E2B Thinking Mode R1 @ 6k.
- **Caveat:** Problems 15 and 73 were subject to exploratory prompt inspection during early development. A clean 98-item evaluation excluding both problems is available via `scripts/recompute_heldout_98.py`.

---

## 5. Contamination Check Methodology

To ensure benchmark integrity against public weights:
1. **HumanEval & GSM8K:** Training set data leakage checks were conducted against Gemma 4 pretraining disclosures.
2. **Held-Out Slices:** Problems in `math_fresh_heldout_500.jsonl` were partitioned prior to AST rewrite tuning. Any item touched during development is explicitly quarantined and disclosed in `handover/V135_CONTAMINATION_AUDIT.md`.
3. **Exact Script & Model Checksums:** All benchmark runs are pinned to specific model SHA-256 hashes defined in `models/MANIFEST.json` and dataset hashes in `data/benchmarks/MANIFEST.yaml`.
