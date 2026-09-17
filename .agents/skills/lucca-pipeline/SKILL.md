---
name: lucca-pipeline
description: Operational skill for developing, running diagnostics, and testing Project Lucca inside Antigravity IDE. Covers environment verification, WSL2/Docker health checks, Phase 1-6 testing harnesses, and latency benchmarks.
---

# Project Lucca Operational Skill

This skill provides step-by-step procedures for operating and developing Project Lucca within Antigravity IDE.

## 1. Environment Verification Workflow
To verify the host hardware and environment configuration:
```powershell
uv run python scripts/verify_environment.py
```
This diagnostic script checks:
- Windows 11 host RAM allocation and `.wslconfig` clamping status.
- Intel NPU presence via OpenVINO.
- Audio input/output devices (WASAPI).
- WSL2 and Docker daemon connectivity.

## 2. Running Phase-by-Phase Acceptance Suites
Always run the specific phase verification suite before declaring a phase complete:

* **Phase 1 (Ears + Voice):**
  ```powershell
  uv run pytest tests/test_phase1_latency.py -s -v
  ```
* **Phase 2 (Tools + Sandbox):**
  ```powershell
  uv run pytest tests/test_phase2_sandbox.py -v
  ```
* **Phase 3 (Memory & Provenance):**
  ```powershell
  uv run pytest tests/test_provenance_gate.py tests/test_hybrid_memory.py -v
  ```
* **Phase 4 & 5 (LISP Engine & Promotion):**
  ```powershell
  uv run pytest tests/test_micro_scheme.py tests/test_promotion_gate.py -v
  ```
* **Phase 6 (Calibrated Classifier):**
  ```powershell
  uv run pytest tests/test_calibrated_router.py -v
  ```

## 3. Launching Background Workers
- **WSL2 vLLM Server:**
  ```powershell
  wsl -d Ubuntu -e bash -c "cd /home/user/vllm && vllm serve fixie-ai/ultravox-v0_5-llama-3_1-8b --gpu-memory-utilization 0.62 --port 8000"
  ```
- **Windows Host Audio Agent:**
  ```powershell
  uv run python -m lucca.main
  ```
