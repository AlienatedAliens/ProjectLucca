# S1 — Dynamic Evidence Capture: Summary

**Producer:** subtask S1 (Debug mode) · **Window:** 2026-09-18T00:08Z → 2026-09-18T01:08Z (UTC) · **Host:** `MSI`, Windows 11, cmd.exe shell, cwd `C:\Projects\ProjectLucca`
**Scope rule honoured:** no file under `src/ tests/ config/ docker/ scripts/ packaging/`, root config, or `.agents/` was modified. `git status --porcelain` of the frozen trees returns the same 51 in-scope entries as the S0 baseline (34 modified + 19 in-scope untracked, `assets/` excluded from the pathspec). All artefacts live in `luccadocs/audit/evidence/`.
**Method:** every command was run through `S1_run.ps1` (writes UTC start/end, exact command, merged stdout+stderr, exit code, duration; appends a row to `S1_command_log.csv`), or through the purpose-built scripts `S1_llm_probe.ps1`, `S1_app_capture.ps1`, `S1_shutdown.ps1`, `S1_ps_helpers.ps1` (all retained as artefacts). Artefacts are append-only; a re-run always got a new suffix (`b`, `c`).

This document records measurements only. No severity or interpretation is assigned.

---

## 1. Command table (exit code, duration)

| # | Artefact | Command (abridged; verbatim in `S1_command_log.csv` / artefact header) | Exit | Dur (s) | Note |
|---|---|---|---:|---:|---|
| 1 | `S1_01_gpu_baseline.txt` | `nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu --format=csv` | 0 | 2.65 | |
| 2 | `S1_02_host_mem_baseline.txt` | `S1_ps_helpers.ps1 -Action hostmem` (Win32_OperatingSystem + top-15 WS) | 0 | 0.59 | |
| 3 | `S1_03_wslconfig.txt` | `type %USERPROFILE%\.wslconfig` | 0 | 0.03 | |
| 4 | `S1_04_wsl_list.txt` | `wsl -l -v` | 0 | 0.06 | Ubuntu **Stopped** at baseline |
| 5 | `S1_05_wsl_docker_state.txt` | free/docker info/images/ps -a | (blank) | 6.07 | runner bug: only last cmd redirected → superseded by 05b |
| 5b | `S1_05b_wsl_docker_state.txt` | same + `cat /etc/wsl.conf` | 0 | 3.11 | |
| 6 | `S1_06_lucca_home_tree.txt` | `echo LUCCA_HOME/ENV/MASTER_KEY(SET/UNSET) && dir /s /b C:\ProjectLucca` | 0 | 0.04 | |
| 7 | `S1_07_models_manifest.txt` | manifest check (cmd parens variant) | 1 | 0.04 | cmd parse error; superseded |
| 7b | `S1_07b_models_manifest.txt` | manifest check (`if … &` variant) | 0 | 0.03 | cmd `if` swallowed chain → empty; superseded |
| 7c | `S1_07c_models_manifest.txt` | `dir …\MANIFEST.json` + `certutil -hashfile` ×4 + `dir` | 0 | 10.59 | authoritative |
| 8 | `S1_08_toolchain.txt` | `uv --version`, `uv run python --version`, sqlite probe, `uv pip list` | 0 | 0.68 | |
| 9 | `S1_09_verify_environment.txt` | `uv run python scripts/verify_environment.py` | 0 | 8.30 | |
| 10 | `S1_10_admin_env_check.txt` | `uv run lucca-admin env-check` | 0 | 4.79 | |
| 11 | `S1_11_T0_lint.txt` | `uv run lint` | **2** | 0.13 | `Failed to spawn: lint — program not found` |
| 11a | `S1_11a_ruff_check.txt` | `uv run ruff check . --output-format concise` + `--statistics` | 0 | 0.20 | All checks passed |
| 11b | `S1_11b_ruff_format.txt` | `uv run ruff format --check .` | **101** | 0.14 | **Ruff panicked** after reporting 7 files |
| 11c | `S1_11c_mypy_strict.txt` | `uv run mypy --strict src` | 0 | 6.40 | Success, 69 files |
| 11d | `S1_11d_lint_imports.txt` | `uv run lint-imports` | **1** | 0.82 | `Could not read any configuration` |
| 12b | `S1_12b_T1_collect.txt` | `uv run pytest -m "not hw and not soak" --collect-only -q` | 0 | 3.05 | |
| 12 | `S1_12_T1_unit.txt` | `uv run pytest -m "not hw and not soak" -q -rA --durations=25 --tb=short` | 0 | 30.38 | |
| 13 | `S1_13_T2_tier2.txt` | `uv run pytest -m tier2 -q -rA` | **5** | 2.05 | `136 deselected` (no tests collected) |
| 14 | `S1_14_coverage.txt` | `uv run pytest -m "not hw and not soak" --cov=lucca --cov-report=term-missing -q` | 0 | 30.13 | |
| 14b | `S1_14b_hypothesis_db.txt` | `dir /s .hypothesis` | 0 | 0.04 | |
| 15a | `S1_15a_launch_cmd_from_code.txt` | `uv run python -c "…build_launch_command(c.llm,c.home_dir)…"` + `llama-server.exe --version` | 0 | 3.58 | |
| 15 | `S1_15b_llm_start_health.txt`, `S1_15_llama_server.log`, `S1_15_llama_server.stderr.log` | **exact code-computed command** (`S1_llm_probe.ps1`) | server exit **1** @ 2.63 s | — | `error: invalid argument: --log-format` |
| 15b | `S1_15bb_llm_start_health.txt`, `S1_15b_llama_server.log`, `S1_15b_llama_server.stderr.log` | same minus `--log-format json` (`S1_llm_probe.ps1 -DropLogFormat`) | healthy | 13.93 to /health 200 | measurement variant; labelled DEVIATION in artefact |
| 16 | `S1_16_gpu_after_llm.txt` | nvidia-smi after failed start | n/a | — | args mangled by PS comma-splitting; superseded |
| 16b | `S1_16b_gpu_after_llm.txt` | `nvidia-smi --query-gpu=memory.used,memory.total` + `--query-compute-apps` | 0 | — | authoritative |
| 17 / 17b | `S1_17_llm_bind.txt` / `S1_17b_llm_bind.txt` | `netstat -ano \| findstr 8080`, `Get-NetTCPConnection -LocalPort 8080`, `/props` | 0 | — | 17 = no server; 17b authoritative |
| 18 / 18b | `S1_18_llm_ttft_probe.txt` / `S1_18b_llm_ttft_probe.txt` | 5× streaming `POST /v1/chat/completions` | — | — | 18 = SKIPPED (no server); 18b authoritative |
| 19 | `S1_19_egress_apply.txt` | `wsl -d Ubuntu -- ls -la /opt/lucca/` ; `wsl -d Ubuntu -- sudo -n /opt/lucca/lucca-egress.sh` | **1** | 3.71 | `/opt/lucca/: No such file or directory`; `sudo: interactive authentication is required` |
| 19b | `S1_19b_egress_apply_code_path.txt` | `wsl -u root -d Ubuntu -- bash /mnt/c/projects/ProjectLucca/scripts/wsl/lucca-egress.sh` (as `egress.py:46-47`) | 0 | 2.73 | `LUCCA-EGRESS rules configured successfully.` |
| 20 | `S1_20_sandbox_verify.txt` | `uv run lucca-admin sandbox verify` | **0** | 0.74 | `Unknown command 'sandbox'` |
| 21 | `S1_21_iptables.txt` | `wsl -d Ubuntu -- sudo -n iptables -S` (+nat, ip6) | **1** | 0.28 | sudo needs password |
| 21b | `S1_21b_iptables_root.txt` | `wsl -u root -d Ubuntu -- iptables -S` / `-t nat -S` / `-L -n -v`; `docker network ls/inspect lucca-net` | 0 | 0.48 | authoritative |
| 22 | `S1_22_container_ports_mounts.txt` | `docker ps -a --format "{{.Names}} STATUS=… PORTS=[…] MOUNTS=[…]"` | 0 | 2.79 | **no containers** |
| 22b | `S1_22b_container_ports_mounts_app_running.txt` | same, 60 s after `lucca.main` start | 0 | — | **no containers** |
| 23 | `S1_23_container_inspect.json` | `docker inspect <containers>` | n/a | — | nothing to inspect (recorded) |
| 24 | `S1_24a_lucca_main_launch.txt`, `S1_24_lucca_main.log`, `S1_24_lucca_main.stderr.log`, `S1_24_uv_pid.txt` | `uv run python -m lucca.main` (background, 60 s) | running | — | via `S1_app_capture.ps1` |
| 25 | `S1_25_process_table.txt` | `tasklist /fi "imagename eq python.exe" /v`; `Get-Process …` with CommandLine/PPID | 0 | — | |
| 26 | `S1_26_gpu_full_app.txt` | `nvidia-smi` (full) | 0 | — | |
| 27 | `S1_27_wsl_mem_under_load.txt` | `wsl -d Ubuntu -- free -m`; `docker stats --no-stream` | 0 | — | |
| 28 | `S1_28_listening_sockets.txt` | `netstat -ano \| findstr LISTEN`; `Get-NetTCPConnection -State Listen` + owner | 0 | — | |
| 29 | `S1_29_ui_screenshot.png` | `System.Windows.Forms` + `CopyFromScreen` | 0 | — | 1707×1067 |
| 30 | `S1_30_T3_hw.txt` | `uv run pytest -m hw -q -rA --durations=0 --tb=short` | **1** | 25.74 | 2 failed / 3 passed |
| 31 | `S1_31_reports_harvest.txt`, `S1_31_reports/**` | `dir /s logs`, `dir /s C:\ProjectLucca\logs`, `xcopy` | 0 | 0.97 | |
| 32 | `S1_32_admin_*.txt` (8 files), `S1_32b_admin_help_and_exitcodes.txt` | `uv run lucca-admin {--help,help,latency --last 100,metrics --since 1h,memory integrity,rules list,router report,logs tail core,<bogus>,sandbox verify}` | all **0** | ~0.55 each | every non-`env-check` subcommand → `Unknown command` |
| 33 | `S1_33_startup_script.txt` | `uv run python scripts/test_s1_startup.py` | 0 | 1.09 | |
| 34 | `S1_34_bench_tts.txt` | `uv run python scripts/bench_tts.py` | 0 | 6.21 | |
| 35 | `S1_35_bench_asr.txt` | `uv run python scripts/bench_asr_ladder.py` | 0 | 76.15 | |
| 36 | `S1_36_spike02.txt` | `uv run python scripts/run_spike02_suite.py` | 0 | 39.63 | **overwrote** `C:\ProjectLucca\logs\phase0_llm.json` |
| 37 | `S1_37_shutdown.txt` | `S1_shutdown.ps1` (taskkill graceful → 10 s → /F /T; llama graceful → 5 s) | 0 | ~20 | |
| 38 | `S1_38_gpu_after_shutdown.txt` | `nvidia-smi` immediately and +10 s | 0 | — | |
| 39 | `S1_39_containers_after.txt` | `docker ps -a`, `free -m`, `wsl -l -v` | 0 | — | |

No command hit its timeout cap (all `TIMED_OUT=False`).

---

## 2. Measured numbers

### 2.1 GPU / VRAM (RTX 5080 Laptop GPU, 16303 MiB, driver 610.78, CUDA UMD 13.3, WDDM)

| Point | VRAM used | Source |
|---|---:|---|
| Baseline (nothing started) | **0 MiB** | `S1_01` |
| After llama-server healthy (+5 s) | **8098 MiB** | `S1_16b` |
| Before `lucca.main` start | 8100 MiB | `S1_24a` |
| Full app running (60 s after boot) | **8100 MiB**, 38 °C, P8, 5 W / 130 W, 0 % util | `S1_26` |
| During Spike-02 (20 runs) | 8234 MiB start = end, slope 0.00 MB/turn | `S1_36` |
| App killed, llama-server still up | 8234 MiB | `S1_37` |
| After llama-server stopped (0 s and +10 s) | **0 MiB** | `S1_38` |

Only compute app listed by nvidia-smi at any time: PID 21764 `llama-server.exe` (`used_gpu_memory = [N/A]` under WDDM).

### 2.2 Host RAM

| Point | Total | Free/Available | Source |
|---|---:|---:|---|
| Baseline | 16 170 128 KB (15.42 GB) | 1 325 880 KB free (`FreePhysicalMemory`) | `S1_02` |
| Baseline (verify_environment) | 15.42 GB | 2.00 GB available | `S1_09` |

Top WS at baseline: Antigravity IDE 932 MB, msedge 558 MB, Antigravity IDE 468 MB, msedge 460 MB, MSI.CentralServer 406 MB, Discord 405 MB (`S1_02`).

### 2.3 WSL2

| Point | total | used | free | available | Source |
|---|---:|---:|---:|---:|---|
| Baseline (distro cold-started by the probe) | 4414 MB | 585 | 3000 | 3829 | `S1_05` |
| Second read | 4414 | 563 | 3006 | 3851 | `S1_05b` |
| Full app running | 4414 | 539 | 2935 | 3875 | `S1_27` |
| After shutdown | 4414 | 628 | 2776 | 3786 | `S1_39` |

Swap 0. Docker CE 29.8.1 (client+server), containerd 1294c24a, runc v1.5.1, Ubuntu 26.04.1 LTS, kernel 6.18.33.2-microsoft-standard-WSL2, 4 CPUs, Total Memory 4.311 GiB, cgroup v2, seccomp builtin, Firewall Backend iptables, `EnableUserlandProxy: true`. Images: `curlimages/curl`, `hello-world`, `lucca/file-sandbox` (189 MB), `lucca/web-sandbox` (295 MB). Containers: **0** at every observation.

`.wslconfig` (verbatim in `S1_03`): `memory=4608MB processors=4 swap=0 pageReporting=true autoMemoryReclaim=gradual sparseVhd=true networkingMode=nat localhostForwarding=true nestedVirtualization=false`. WSL emits on every invocation: `Unknown key 'wsl2.pageReporting'`, `Unknown key 'wsl2.autoMemoryReclaim'`, `Unknown key 'wsl2.sparseVhd'`, and `Expected " in /etc/wsl.conf:9` (`/etc/wsl.conf` line 9 is `options = " metadata,uid=1000,gid=1000,umask=022,fmask=111\` — unterminated quote; see `S1_05b`).

### 2.4 LLM (llama-server `version: 0.4.1-dev (build 11026, commit b49650adb)`, Clang 20.1.8)

- **Exact code-computed command** (`build_launch_command`, default config, `env.mode=prod`, `llm.mode=audio`, `home_dir=C:\ProjectLucca`) — `S1_15a`:
  `C:\ProjectLucca\app\llama-server\llama-server.exe --model C:\ProjectLucca\models\llm\ultravox-v0_5-llama-3_1-8b-Q6_K.gguf --n-gpu-layers 99 --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --flash-attn on --host 127.0.0.1 --port 8080 --no-webui --jinja --log-format json --mmproj C:\ProjectLucca\models\llm\mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf`
- **Result of running it verbatim:** process exited **code 1 after 2.63 s**; stderr = `error: invalid argument: --log-format` (`S1_15_llama_server.stderr.log`). `/health` never answered.
- **Divergences from SKILL.md §4 command:** exe path `app\llama-server\` (code) vs `app\bin\` (skill); `--flash-attn on` (code) vs `--flash-attn` (skill); `--log-format json` present only in code; mmproj appended last and only when `mode == "audio"`.
- **Measurement variant (identical minus `--log-format json`):** time-to-healthy **13.93 s** (`/health` → `{"status":"ok"}`), PID 21764 (`S1_15bb`).
- **Bind:** `TCP 127.0.0.1:8080 0.0.0.0:0 LISTENING 21764` — the only :8080 listener; no `0.0.0.0` or `[::]` entry (`S1_17b`).
- **TTFT ×5** (streaming, `max_tokens=64`, 20-word prompt = 54 prompt tokens after template; `S1_18b`):

| Run | TTFT (ms) | Total (ms) | prompt_n / cache_n | decode tok/s |
|---:|---:|---:|---|---:|
| 1 | **372.8** | 1176.5 | 54 / 0 | 75.55 |
| 2 | **20.8** | 838.5 | 1 / 53 | 76.97 |
| 3 | **22.0** | 883.8 | 1 / 53 | 73.09 |
| 4 | **44.3** | 844.0 | 1 / 53 | 78.84 |
| 5 | **19.0** | 802.8 | 1 / 53 | 80.38 |

  Prompt eval 174 tok/s cold; all 5 runs `finish_reason=length`, 64 content chunks each.
- **Spike-02 (`S1_36`, 20 runs, different prompt/harness):** TTFT median 67.0 ms, p95 115.1 ms (run 1 = 691.1 ms); decode median 76.7 tok/s; host RSS of llama-server 45.0 MB; S6 audio tool-calls 18/20; S8 abort probes **HTTP 501** ×10 (p50 31.49 ms, reported PASS); S9 30.5 s clip → 200; S10 text tool-calls 20/20.
- **llama-server host memory:** WS 2.81 GB right after load; WS 11.6 MB / PM 8826 MB during app run; WS 339.7 MB at shutdown (`S1_15bb` note, `S1_25`, `S1_37`).

### 2.5 Test tiers

| Tier | Command | Collected | Passed | Failed | Skipped | xfail | Deselected | Wall | Exit |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T1 | `pytest -m "not hw and not soak"` | 136 | **131** | 0 | 0 | 0 | 5 | 25.27 s | 0 |
| T2 | `pytest -m tier2` | 136 | 0 | 0 | 0 | 0 | **136** | 1.29 s | **5** |
| T3 | `pytest -m hw` | 136 | **3** | **2** | 0 | 0 | 131 | 24.58 s | **1** |
| Coverage run | T1 + `--cov=lucca` | 136 | 131 | 0 | 0 | 0 | 5 | 26.39 s | 0 |

T3 failures (`S1_30`):
- `tests/test_phase1_live_hw.py::test_live_phase1_conversational_turn` — `assert trace.tokens_out > 0` → `0 > 0`; trace: `mode='audio' route='llm' tts_device='CPU' asr_device='cpu' … t_postturn_done=180044109000000, tokens_out=0, chunks=0`; captured `[User] "Thank you."` / `[Lucca] ` (empty).
- `tests/test_phase1_live_hw.py::test_live_phase1_tool_call_turn` — `assert tool_name == "launch_app"` → got `'query_capabilities'` (executed `[('query_capabilities', {'category': 'all'})]`).
- Passed: `test_live_barge_in_abort` (abort 30.07 ms), `test_live_phase2_egress_matrix` (8.54 s, `egress_rules_applied`), `test_live_phase2_in_container_rpc` (0.93 s).

T1 slowest: `test_t_prov_06_end_to_end_hallucination_write_rejection` setup 3.92 s; `test_t_mem_05_50k_synthetic_search_latency` 2.30 s. T1 log warnings (4): `launch_not_whitelisted app=cmd`, `launch_not_whitelisted app=powershell`, `launch_rate_limited app=notepad`, `sha256_audit_mismatch actual=3109af4b… expected=0000…0000`.

### 2.6 T0 static gates

| Tool | Result | Count |
|---|---|---:|
| `uv run lint` | program not found (exit 2) | — |
| `ruff check .` | All checks passed | **0** errors, 0 rule codes |
| `ruff format --check .` | 7 files "would be reformatted", then **panic** (`ruff_annotate_snippets/src/renderer/source_map.rs:185:13: Annotation range 0..1337 is beyond the end of buffer 1335`), exit 101 | **≥ 7** (list may be truncated by the crash): `packaging\build_exe.py`, `src\lucca\brain\llm_client.py`, `src\lucca\senses\tts.py`, `src\lucca\ui\settings_dialog.py`, `src\lucca\ui\sprite.py`, `src\lucca\ui\telemetry_hud.py`, `tests\fakes\fake_llm.py` |
| `mypy --strict src` | Success: no issues found in 69 source files; note `unused section(s): module = ['torch.*']` | **0** |
| `lint-imports` | `Could not read any configuration`; no `importlinter` key in `pyproject.toml`, no `.importlinter`/`setup.cfg` | exit 1 |

### 2.7 Coverage (`S1_14`)

**TOTAL 61 %** — 8803 statements, 3411 missed. 0 %: `admin.py`, `core/env_check.py`, `core/events.py`, `main.py`, `senses/audio_proc.py`, `senses/npu_proc.py`, `senses/ptt.py`, `senses/vad.py`, `ui/app.py`, `ui/commorose.py`. < 25 %: `brain/llm_client.py` 19 %, `sandbox/system_tools.py` 18 %, `sandbox/egress.py` 23 %. 100 %: `core/exceptions.py`, `core/schemas.py`, `core/trace.py`, `ports.py`, `router/labeler.py`, `sandbox/policy.py`, `ui/states.py`, `ui/theme.py`, `reasoning/scheme/__init__.py`.

Hypothesis DB `.hypothesis/`: 212 files, 90 456 bytes (`S1_14b`).

### 2.8 Toolchain (`S1_08`)

uv 0.12.10; Python 3.12.14; `sqlite3.Connection.enable_load_extension` = True; SQLite 3.53.1; sqlite-vec 0.1.9; pytest 9.1.1, pytest-cov 7.1.0, pytest-asyncio 1.4.0, pytest-timeout 2.4.0, hypothesis 6.168.0; ruff 0.16.8; mypy 2.3.1; import-linter 2.15; openvino 2026.4.0; pyqt6 6.11.0; pyzmq 27.2.0; faster-whisper 1.2.1; kokoro-onnx 0.6.1; lightgbm 4.7.0; scikit-learn 1.9.1; pydantic 2.13.5; project-lucca 0.2.0 (editable).

### 2.9 Environment checks

- `verify_environment.py`: 7/7 green, "ALL DIAGNOSTICS GREEN" (reports Available RAM 2.00 GB; `.wslconfig` items `pageReporting=true: [OK]`, `autoMemoryReclaim=gradual: [OK]` although WSL rejects both keys; OpenVINO devices `['CPU','GPU.0','GPU.1','NPU']`; Docker memory 4 629 053 440 bytes).
- `lucca-admin env-check`: 6/6 PASS, exit 0 (both with 0 MiB and with 8100 MiB VRAM resident: "within 9500 MB budget").
- Env vars: `LUCCA_HOME` unset (echoed literally as `%LUCCA_HOME%`), `LUCCA_ENV` unset, `LUCCA_MASTER_KEY` **UNSET**; code falls back to `C:\ProjectLucca`, `env.mode=prod`.
- `C:\ProjectLucca\models\MANIFEST.json` **does not exist** (`File Not Found`; no `*MANIFEST*` anywhere under `models\`). sha256 of present binaries (no expected values to compare): `ultravox-v0_5-llama-3_1-8b-Q6_K.gguf` 6 596 011 424 B `33981adf6bae52c503fb5c24f72539010632f7ed290a56c1315a8cd50adca587`; `mmproj-…-Q8_0.gguf` 1 379 512 224 B `e6395ed42124303eaa9fca934452aabce14c59d2a56fab2dda65b798442289ff`; `tts\kokoro-v1.0.onnx` 325 532 387 B `7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5`; `tts\voices-v1.0.bin` 28 214 398 B `bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d`. Also present: `models\asr\whisper-large-v3-turbo-ov\`, `models\embed\all-MiniLM-L6-v2\`, `tmp\llama-b11026-bin-win-cuda-12.4-x64.zip`, `tmp\cudart-llama-bin-win-cuda-12.4-x64.zip`.
- LUCCA_HOME layout present: `app config data inbox logs models tmp workspace cache`; `app\llama-server\` contains the full llama.cpp b11026 CUDA 12.4 distribution incl. `llama-cli.exe`, `ggml-rpc-server.exe`, etc.; `data\memory.sqlite`, `data\backups\`; `config\persona.toml`.

### 2.10 Process RSS (full app, 60 s after boot; `S1_25`)

| Process | PID | PPID | WS (MB) | PM (MB) | tasklist Status |
|---|---:|---:|---:|---:|---|
| `uv.exe run python -m lucca.main` | 9104 | 38068 | 23.0 | 43.0 | — |
| `.venv\Scripts\python.exe -m lucca.main` (launcher shim) | 33552 | 9104 | 5.5 | 0.8 | Unknown |
| `python.exe -m lucca.main` (supervisor + orchestrator) | 9120 | 33552 | **870.1** | 3473.1 | **Not Responding** |
| mp child (`spawn_main … pipe_handle=4160`) | 40824 | 9120 | **865.4** | 3577.8 | **Not Responding** |
| mp child (`pipe_handle=4084`) | 39664 | 9120 | 197.1 | 1637.2 | **Not Responding** |
| mp child (`pipe_handle=3052`) | 35780 | 9120 | 225.7 | 1676.4 | Running (window title `python`) |
| `llama-server.exe` | 21764 | 39580 | 11.6 | 8826.4 | Running |

Sum of python WS ≈ 2.16 GB. At shutdown time (01:07Z) the surviving python processes had WS 16.0 / 19.3 / 19.1 MB and PID 35780 no longer existed (`S1_37`).

### 2.11 Listening sockets (`S1_28`)

Lucca-owned listeners: `127.0.0.1:47001`, `127.0.0.1:47002`, `127.0.0.1:47003` (PID 9120 python — ZMQ ctl/bus/ingest per `IPCSettings`), `127.0.0.1:8080` (PID 21764 llama-server). **None on 0.0.0.0 / ::.** Non-Lucca listeners on LAN addresses observed on the host: `172.20.96.1:139`, `192.168.1.5:139` (PID 4 System).

### 2.12 Sandbox / egress (`S1_19*`, `S1_21b`, `S1_22*`, `S1_23`)

- `/opt/lucca/lucca-egress.sh` does not exist in the distro; passwordless sudo is not configured (`sudo -n` → `interactive authentication is required`); default WSL user `seatrlucca` uid 1000, groups include `sudo` and `docker`.
- `wsl -u root …` works without a password; the code path (`egress.py:46-47`, hard-coded `C:\projects\ProjectLucca\scripts\wsl\lucca-egress.sh` → `/mnt/c/...`) applied successfully.
- iptables (root): `-P FORWARD DROP`; `-A DOCKER-USER -s 172.28.0.0/24 -j LUCCA-EGRESS`; `LUCCA-EGRESS`: ACCEPT RELATED,ESTABLISHED; REJECT (icmp-admin-prohibited) to 10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, 127/8, 224/4, 240/4, 0/8; ACCEPT tcp multiport 80,443; ACCEPT udp+tcp 53 to 1.1.1.1 and 1.0.0.1; LOG (limit 5/min, prefix `LUCCA-EGRESS-DROP `); DROP. All counters 0 pkts. nat: MASQUERADE for 172.17.0.0/16 and 172.28.0.0/24. `INPUT`/`OUTPUT` policy ACCEPT.
- `docker network lucca-net`: bridge, subnet 172.28.0.0/24, gw 172.28.0.1, `Internal: false`, `enable_ip_masquerade: true`, IPv6 off, created 2026-09-18T00:27:10+08:00, `Containers: {}`, `IPsInUse: 3`.
- Containers: **none existed** before, during (60 s after app boot), or after the session. `S1_23_container_inspect.json` therefore records "NO CONTAINERS EXIST". Container security settings (CapDrop, ReadonlyRootfs, NetworkMode, Memory, PidsLimit, Mounts, SecurityOpt, User) could **not** be observed live; the intended values are only in `src/lucca/sandbox/container_spec.py:34-58,87-104` (`--network none`/`lucca-net`, `--read-only`, `--tmpfs /tmp:…size=32m`, bind `workspace→/workspace`, `--user 1000:1000`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory=768m`/`512m`, `--pids-limit=256`/`128`). `test_live_phase2_in_container_rpc` passed in 0.93 s with no container left behind.

### 2.13 Scripts (`S1_33`–`S1_36`)

- `test_s1_startup.py`: `Server ready: True in 0.07s` (attached to the already-running server; did not launch one).
- `bench_tts.py` (CPU only, Kokoro ONNX, clause "Hello, how can I help you today?" → 1.88 s audio): synth p50 **328.7 ms**, p95 **393.3 ms**, mean RTF **0.183**; model load 0.76 s. No NPU/GPU section in output.
- `bench_asr_ladder.py` (Whisper large-v3-turbo OV, 1.32 s clip `calc_01.wav`):

| Device | compile | transcript | p50 (ms) | p95 (ms) | RTF |
|---|---:|---|---:|---:|---:|
| NPU | 16.65 s | `' Open!!!!!!!!…'` (degenerate, hundreds of `!`) | **5450.3** | 5464.8 | **4.121** |
| GPU.0 | 7.00 s | `' Open the calculator.'` | 1443.3 | 1587.2 | 1.091 |
| CPU | 1.24 s | `' Open the calculator.'` | 1522.4 | 1683.0 | 1.151 |

- `run_spike02_suite.py`: see §2.4; wrote `C:\ProjectLucca\logs\phase0_llm.json` (13 775 B), replacing the 2026-09-17T15:21Z file (13 286 B). Pre-run original preserved at `S1_31_reports/ProjectLucca_logs/phase0_llm.json`; post-run copy at `S1_31_reports/ProjectLucca_logs_after_spike02/phase0_llm.json`. Original file content: `S1.measured_cold_startup_s = 42.5` (identical constant in the new run), `S5.status = "FAIL", rss_mb = 1809.42 (threshold 800)`, `S2.ttft_p50_ms = 79.85, p95 = 139.90`.

### 2.14 Shutdown (`S1_37`)

- Graceful `taskkill /PID 9120` (no `/F`): `SUCCESS: Sent termination signal`, but after **10 s** supervisor 9120 and children 40824, 39664 were **all still alive** (3/3). (Caveat: `taskkill` without `/F` posts WM_CLOSE; it is not a true console Ctrl+C. No Ctrl+C-capable channel to a hidden background console was available.)
- `taskkill /F /T /PID 9120`: all three terminated; wrappers 33552/9104 gone; **no orphaned python processes** 3 s later.
- llama-server: graceful `taskkill /PID 21764` → exited within 5 s.
- VRAM after: **0 MiB** (immediately and +10 s). Containers after: none. WSL Ubuntu still `Running`.
- App stderr before shutdown: `WARNING: Child process 'ui' exited with code 0.` repeated **25×** (one per supervisor loop tick) — the UI child had exited (user selected "Quit Lucca" in the sprite context menu per `S1_29` screenshot) and the supervisor neither restarted it nor shut down.

---

## 3. Sign-off report files expected by archived testing matrix §4 (Phases 0–4)

| Phase | Expected report (archived `10_testing_matrix_v2.md` §4) | Exists? | Path / note |
|---|---|---|---|
| 0 | `phase0_llm.json` | **EXISTS** | `C:\ProjectLucca\logs\phase0_llm.json` (original 2026-09-17T15:21Z, 13 286 B → copied to `S1_31_reports/ProjectLucca_logs/`; **overwritten** by `run_spike02_suite.py` at 01:04:40Z). Original contains `S5: FAIL`. |
| 0 | `phase0_npu.json` | **MISSING** | not under `C:\ProjectLucca\logs`, repo, or `logs\test_reports` |
| 1 | `latency_report_*.md` × 2 (audio + transcript modes) | **MISSING** | none found |
| 1 | soak report (T-SOAK-01) | **MISSING** | none found |
| 2 | `sandbox_verify_*.md` | **MISSING** | none found; `lucca-admin sandbox verify` is not implemented |
| 3 | `retrieval_bench_*.md` | **MISSING** | none found |
| 4 | `decisions.jsonl` stats | **MISSING** | no `decisions.jsonl` under either root (decisions may live inside `data\memory.sqlite`; not verified by S1) |
| all `hw` tests | `logs\test_reports\<test>-<ts>.json` (matrix §1: "Every `hw` test writes a machine-readable report") | **MISSING** | `logs\test_reports\` directory does not exist in the repo or under `C:\ProjectLucca\logs`; running `-m hw` created none |
| — (present but not a §4 deliverable) | `traces.jsonl` | exists | `C:\ProjectLucca\logs\traces.jsonl`, 186 522 B, 293 lines (copied) |
| — | `resource_sessions\session_20260918_055627.jsonl` | exists | 672 B (copied) |

---

## 4. Raw observations (unordered, uninterpreted)

1. `build_launch_command()` emits `--log-format json`; the installed llama-server build 11026 rejects it (`error: invalid argument: --log-format`) and exits 1 in 2.6 s. `start_server()` pipes stdout/stderr to `DEVNULL`, so the error text is never surfaced. `main.py:_ensure_llama_server()` skips the spawn when a healthy server already exists (which is what happened in this session because S1 had started one); otherwise it would wait 60 s and `sys.exit(5)`.
2. SKILL.md documents the llama-server path as `app\bin\llama-server.exe`; the binary and the code use `app\llama-server\llama-server.exe`.
3. `uv run lint` does not exist (no `lint` script). `lint-imports` has no configuration. `ruff format --check` panics on this tree (Ruff 0.16.8).
4. The pytest marker `tier2` is not registered; `-m tier2` deselects everything and exits 5 with no warning text in `-q` output.
5. `lucca-admin` implements only `env-check` and `help`; `latency`, `metrics`, `memory`, `rules`, `router`, `sandbox`, `models`, `replay`, `logs` (all advertised in its help string) print `Unknown command` and exit **0**. `--help` is also treated as an unknown command (exit 0).
6. `C:\ProjectLucca\models\MANIFEST.json` does not exist; both env checks still report the LUCCA_HOME layout as verified.
7. `LUCCA_MASTER_KEY` is UNSET and `env.mode` defaults to `prod`; `lucca-admin env-check` and `verify_environment.py` report all-green.
8. WSL rejects three `.wslconfig` keys (`pageReporting`, `autoMemoryReclaim`, `sparseVhd`) and reports a syntax error in `/etc/wsl.conf:9`; `verify_environment.py` and `env-check` nonetheless mark the `.wslconfig` "canonical".
9. `/opt/lucca/lucca-egress.sh` (SKILL.md path) is absent; `sudo` requires a password; the code instead runs the repo script as `wsl -u root` from a hard-coded `C:\projects\ProjectLucca\...` path.
10. No Docker container existed at any point (before, during app run, after `hw` tests). `lucca-net` reports `IPsInUse: 3` with `Containers: {}`.
11. App stdout shows repeated `ingest_loop_unexpected_error error="'charmap' codec can't encode characters …"` (incl. `'\U0001f4ac'`) — a `UnicodeEncodeError` inside the orchestrator ingest loop when stdout is a redirected file (cp1252).
12. App stderr: `QWindowsWindow::setGeometry: Unable to set geometry 540x152+1547+587 … on "SpeechBubbleClassWindow" … minimum size: 360x101 maximum size: 520x16777215`.
13. `tasklist` reported 3 of 4 `lucca.main` python processes (supervisor + 2 children) as **Not Responding** 60 s after boot; 2 of them held ~870 MB WS each.
14. During the 60 s capture window, three `[AUDIO] PTT Pressed/Released` cycles were logged (2094 / 1375 / 3187 ms). The screenshot (`S1_29`) shows the sprite's context menu open, i.e. the user was interacting with the UI; the `hw` test run at 00:58Z produced a further `PTT Released (328ms, speech: 0ms)`.
15. UI child exited (code 0) during the session; the supervisor logged the warning every second (25×) and took no action; graceful `taskkill` did not stop the supervisor or children within 10 s; force-kill left no orphans.
16. T3 `hw`: audio-mode conversational turn returned `tokens_out=0` (empty reply); tool-call turn chose `query_capabilities` over `launch_app`; `TurnTrace.t_postturn_done=180044109000000` while other `t_*` fields are 0.
17. `hw` tests wrote no `logs\test_reports\*.json`; `logs\test_reports\` does not exist.
18. `run_spike02_suite.py` reports `Cold startup: ~42.5s [PASS]` against a server that was already running; the same `42.5` appears in the pre-existing report from 2026-09-17. S8 "abort" calls `/slots/0?action=release` and receives HTTP **501** ×10 yet the section passes. S6 loop labels run to "Clip 21/20" and "22/20" (`test_30_5s`, `test_3s_tone` — both produced `launch_app` tool calls and are excluded from the 18/20 tally). The script overwrites `phase0_llm.json` in place (no timestamped name).
19. Original `phase0_llm.json` (pre-audit, 2026-09-17) records `S5: FAIL` (`rss_mb 1809.42 > 800`); the new run records 45.0 MB for the same process because llama-server WS is ~12–340 MB while its private bytes are 8.8 GB.
20. Whisper on NPU produced a degenerate transcript (`' Open!!!!!!…'`) at RTF 4.12; GPU.0 and CPU transcribed correctly at RTF 1.09/1.15 on a 1.32 s clip (compile 16.65 s / 7.00 s / 1.24 s).
21. `bench_tts.py` only exercised CPU.
22. `test_s1_startup.py` reports "Launching llama-server…Server ready: True in 0.07s" when a server is already up.
23. T1 log lines during `test_sandbox.py`: `sha256_audit_mismatch expected=0000…0000` and `launch_not_whitelisted app=cmd/powershell`, `launch_rate_limited app=notepad`.
24. Coverage 61 % overall; ten modules at 0 % including `main.py`, `ui/app.py`, `senses/audio_proc.py`, `senses/npu_proc.py`, `senses/ptt.py`, `senses/vad.py`, `core/events.py`, `core/env_check.py`, `admin.py`, `ui/commorose.py`.
25. llama-server VRAM grew 8098 → 8234 MiB over the session (+136 MiB) and returned to 0 MiB after the process exited; no VRAM leak after shutdown.
26. Host available RAM at baseline ≈ 1.3–2.0 GB of 15.42 GB with IDE/browser load present; the full app added ≈ 2.16 GB of python WS plus llama-server.
27. `docker info`: `Insecure Registries: ::1/128, 127.0.0.0/8`, `Live Restore Enabled: false`, `Experimental: false` (default values; recorded only).
28. `launch_lucca.bat` runs `uv run lucca` from `C:\projects\ProjectLucca` (repo path hard-coded).
29. Runner-side artefacts `S1_05`, `S1_07`, `S1_07b`, `S1_16`, `S1_17`, `S1_18`, `S1_32_admin_help` are incomplete/mangled by cmd/PowerShell quoting issues and are superseded by their `b`/`c` re-runs; they are retained unmodified per the append-only rule.
