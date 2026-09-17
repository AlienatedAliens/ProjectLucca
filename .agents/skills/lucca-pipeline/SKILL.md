---
name: lucca-pipeline
description: Operational skill for developing, running diagnostics, and testing Project Lucca inside Antigravity IDE. Covers environment verification, WSL2/Docker CE health checks, tiered test execution (T0 static → T4 soak), Phase 0–6 sign-off bundles, and latency/VRAM reports.
---

# Project Lucca Operational Skill

Authoritative references: [`docs/13_decisions_log.md`](../../../docs/13_decisions_log.md), [`docs/10_testing_matrix_v2.md`](../../../docs/10_testing_matrix_v2.md), [`docs/11_phase_plan_v2.md`](../../../docs/11_phase_plan_v2.md). If a command here disagrees with those documents, the documents win.

## 1. Environment verification

```powershell
uv sync --frozen
uv run lucca-admin env-check        # preferred once implemented
uv run python scripts/verify_environment.py   # interim
```
Checks (all must be green before Phase 0): MSHybrid GPU mode (dGPU baseline VRAM < 300 MB via `nvidia-smi`), CUDA 12.8 runtime, Intel NPU visible to OpenVINO **on Windows** (never inside WSL2), `sqlite3.enable_load_extension` + `sqlite-vec` load, `.wslconfig` equals the canonical block (`memory=4608MB`, `processors=4`, `swap=0`, `pageReporting=true`, `autoMemoryReclaim=gradual`, `networkingMode=nat`), **Docker CE inside the Ubuntu distro** (`wsl -d Ubuntu -- docker info`; Docker Desktop is unsupported), `LUCCA_HOME` layout (`C:\ProjectLucca\{app,config,models,data,workspace,inbox,logs,cache,tmp}`), model files present with sha256 matching `models\MANIFEST.json`, `LUCCA_MASTER_KEY` set and not a dev default when `LUCCA_ENV=prod`.

## 2. Test tiers

```powershell
uv run lint                                   # T0: ruff, mypy --strict, import-linter, AST tests
uv run pytest -m "not tier2 and not hw and not soak"   # T1 unit + property tests
uv run pytest -m tier2                        # T2 fake-backed integration (orchestrator loop with Fake* adapters)
uv run pytest -m hw                           # T3 real hardware; writes logs\test_reports\*.json
uv run pytest -m soak                         # T4 endurance (~1 h)
```
Never edit a threshold to make a test pass. Record the measured value in `docs/14_blockers.md` and stop.

## 3. Phase sign-off

Run the bundle in `docs/10_testing_matrix_v2.md` §4 for the phase; attach the report files it names (`phase0_llm.json`, `latency_report_*.md` for **both** audio and transcript modes, `sandbox_verify_*.md`, `retrieval_bench_*.md`, `report-<sha>.md`). Phases 4–6 additionally have **human gates** (`11_phase_plan_v2.md`): ≥ 100 labelled decisions, ≥ 1 rule promoted from real/replayed usage, ≥ 600-decision data floor. Synthetic data never satisfies a human gate.

## 4. Background services

- **LLM (native Windows, ADR-001):**
  ```powershell
  & "$env:LUCCA_HOME\app\bin\llama-server.exe" --model "$env:LUCCA_HOME\models\llm\ultravox-v0_5-llama-3_1-8b-Q6_K.gguf" --mmproj "$env:LUCCA_HOME\models\llm\mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf" --n-gpu-layers 99 --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --flash-attn --host 127.0.0.1 --port 8080 --no-webui --jinja
  ```
  Health: `curl http://127.0.0.1:8080/health`. Normally started by the supervisor; start manually only for Phase 0 spikes.
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
