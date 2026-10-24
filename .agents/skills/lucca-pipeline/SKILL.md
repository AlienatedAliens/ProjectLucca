---
name: lucca-pipeline
description: Operational skill for developing, running diagnostics, and testing Project Lucca inside Antigravity IDE. Covers environment verification, WSL2/Docker CE health checks, tiered test execution (T0 static → T4 soak), Phase 0–6 sign-off bundles, and latency/VRAM reports.
---

# Project Lucca Operational Skill

Authoritative references: [`luccadocs/DECISIONS.md`](../../../luccadocs/DECISIONS.md), [`luccadocs/ARCHITECTURE.md`](../../../luccadocs/ARCHITECTURE.md), [`luccadocs/MODEL_STRATEGY.md`](../../../luccadocs/MODEL_STRATEGY.md). If a command here disagrees with those documents, the documents win.

## 1. Environment verification

```powershell
uv sync --frozen
uv run lucca-admin env-check
uv run python -m lucca.core.env_check
```
Checks (all must be green before boot): MSHybrid GPU mode (dGPU baseline VRAM within 12,800 MB budget via `nvidia-smi`), CUDA 12.8 runtime, Intel NPU visible to OpenVINO **on Windows** (never inside WSL2), `sqlite3.enable_load_extension` + `sqlite-vec` load, `.wslconfig` equals the canonical block (`memory=4608MB`, `processors=4`, `swap=0`, `pageReporting=true`, `autoMemoryReclaim=gradual`, `networkingMode=nat`), **Docker CE inside the Ubuntu distro** (`wsl -d Ubuntu -- docker info`; Docker Desktop is unsupported), `LUCCA_HOME` layout (`C:\ProjectLucca\{app,config,models,data,workspace,inbox,logs,cache,tmp}`), model files present with sha256 matching `models\MANIFEST.json`, `LUCCA_MASTER_KEY` set and not a dev default when `LUCCA_ENV=prod`.

## 2. Test tiers

```powershell
uv run lint                                             # T0: ruff, mypy --strict, import-linter, AST tests
uv run pytest -m "not tier2 and not hw and not soak"    # T1 unit + property tests
uv run pytest -m tier2                                  # T2 fake-backed integration (orchestrator loop with Fake* adapters)
uv run pytest -m hw                                     # T3 real hardware; writes logs\test_reports\*.json
uv run pytest -m soak                                   # T4 endurance (~1 h)
uv run pytest tests/test_frozen_regression_harness.py   # Golden frozen regression suite (100 scenarios)
```
Never edit a threshold to make a test pass. Record any regressions and stop.

## 3. Phase sign-off

Run the validation suite; verify all gates pass. Synthetic data never satisfies a human gate.

## 4. Background services

- **LLM (native Windows, D-BRAIN-05 v2 — Gemma-4-12B-Heretic Q6_K):**
  ```powershell
  & "C:\ProjectLucca\app\llama-server\llama-server.exe" --model "C:\ProjectLucca\models\llm\gemma-4-12b-heretic-Q6_K.gguf" --n-gpu-layers 99 --ctx-size 32768 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --flash-attn --host 127.0.0.1 --port 8080 --no-webui --jinja
  ```
  Health: `curl http://127.0.0.1:8080/health`. Default 32K context (`ctx=32768`) in v1.3.0 (16K context in v1.2 baseline). Normally started by the supervisor (`uv run python -m lucca.main`); start manually only for development/benchmarks.
- **Alternative LLM (Ultravox Q6_K multimodal, D-AUD-05):**
  ```powershell
  & "C:\ProjectLucca\app\bin\llama-server.exe" --model "C:\ProjectLucca\models\llm\ultravox-v0_5-llama-3_1-8b-Q6_K.gguf" --mmproj "C:\ProjectLucca\models\llm\mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf" --n-gpu-layers 99 --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --flash-attn --host 127.0.0.1 --port 8080 --no-webui --jinja
  ```
- **Lucca (supervisor spawns audio/npu/ui processes):**
  ```powershell
  uv run python -m lucca.main
  ```
- **Sandbox egress rules (idempotent; also run at WSL boot and by the supervisor):**
  ```powershell
  wsl -d Ubuntu -- sudo /opt/lucca/lucca-egress.sh
  uv run lucca-admin sandbox verify     # positive-controlled egress table
  ```

## 5. Diagnostics

```powershell
uv run lucca-admin latency --last 100         # per-stage medians/p95 from logs\traces.jsonl
uv run lucca-admin metrics --since 1h         # RSS per process, VRAM, underruns, rejects
uv run lucca-admin memory integrity           # PRAGMA integrity_check + backup age
uv run lucca-admin rules list                 # lifecycle states, clusters, failures
uv run lucca-admin router report              # data-volume gate + classifier metrics with CIs
uv run lucca-admin logs tail core             # structured JSON logs
```

## 6. Hard rules for this skill

- Never run OpenVINO/NPU workloads inside WSL2 or Docker.
- Never run tree models (LightGBM/XGBoost) on the NPU.
- Never expose `llama-server` on anything but `127.0.0.1`.
- Never publish sandbox container ports or expose the Docker socket to Windows.
- Never mount anything but `C:\ProjectLucca\workspace` into a container.
