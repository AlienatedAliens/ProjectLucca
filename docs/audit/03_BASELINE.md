# 03 — Audit Baseline

Captured by subtask **S0** on **2026-09-17T23:54Z – 2026-09-17T23:57Z (UTC)** from `c:\Projects\ProjectLucca`, shell `powershell.exe` (Windows PowerShell 5.1, invoked from cmd). Nothing was committed, staged, or modified outside `docs/`. All commands below are read-only with respect to the frozen trees.

Line counts use `(Get-Content <file> | Measure-Object -Line).Lines`. Byte sizes are `FileInfo.Length`. `__pycache__/` directories (12 under `src/` + `tests/`) and their `.pyc` contents are excluded from the inventory as build artefacts. Binary files are listed with size but no line count.

---

## 1. Git HEAD

```
$ git rev-parse HEAD
ed14f6b44fc233c94f01c9f9f3c1f68619e026e7

$ git branch --show-current
master
```

## 2. Working tree status (`git status --porcelain`, captured **before** the `docs/` archive move)

```
 M config/persona.toml
 M pyproject.toml
 M src/lucca/brain/llm_client.py
 M src/lucca/brain/prompt_builder.py
 M src/lucca/core/config.py
 M src/lucca/core/ipc_schemas.py
 M src/lucca/core/orchestrator.py
 M src/lucca/main.py
 M src/lucca/memory/tokens.py
 M src/lucca/router/heuristic.py
 M src/lucca/router/labeler.py
 M src/lucca/sandbox/file_tool.py
 M src/lucca/sandbox/policy.py
 M src/lucca/sandbox/service.py
 M src/lucca/sandbox/web_tool.py
 M src/lucca/senses/__init__.py
 M src/lucca/senses/asr.py
 M src/lucca/senses/audio_proc.py
 M src/lucca/senses/embed.py
 M src/lucca/senses/npu_proc.py
 M src/lucca/senses/ptt.py
 M src/lucca/senses/ring_buffer.py
 M src/lucca/senses/tts.py
 M src/lucca/senses/vad.py
 M src/lucca/ui/__init__.py
 M src/lucca/ui/app.py
 M src/lucca/ui/input_bar.py
 M src/lucca/ui/settings_dialog.py
 M src/lucca/ui/speech_bubble.py
 M src/lucca/ui/sprite.py
 M src/lucca/ui/states.py
 M tests/test_sandbox.py
 M tests/test_ui_widgets.py
 M uv.lock
?? Lucca.spec
?? assets/icon.ico
?? assets/icon.png
?? docs/IMPLEMENTATION_PROMPT_2026-09-17_persona_llm_ui.md
?? docs/UI_USER_GUIDE.md
?? launch_lucca.bat
?? packaging/
?? scripts/create_desktop_shortcut.ps1
?? scripts/make_shortcut.py
?? src/lucca/brain/server_ctl.py
?? src/lucca/memory/manager.py
?? src/lucca/sandbox/system_tools.py
?? src/lucca/senses/dsp_chain.py
?? src/lucca/ui/commorose.py
?? src/lucca/ui/telemetry_hud.py
?? src/lucca/ui/theme.py
?? tests/test_dsp_chain.py
?? tests/test_gguf_parser.py
?? tests/test_persona_toml.py
?? tests/test_prompt_builder.py
?? tests/test_server_ctl.py
```

**Interpretation.** The working tree is **dirty**: 34 tracked files modified, 21 untracked paths. The audit target is the on-disk tree (HEAD + these uncommitted changes), not HEAD alone. Several in-scope "extra" features exist **only** as untracked files (`server_ctl.py`, `memory/manager.py`, `system_tools.py`, `dsp_chain.py`, `commorose.py`, `telemetry_hud.py`, `theme.py`, `packaging/`, `Lucca.spec`, `launch_lucca.bat`) — they have never been committed. Any later subtask that finds the tree differs from this listing must stop and report.

The two `?? docs/…` entries were untracked at capture time and have since been moved (untracked → untracked) into `docs/archive/2026-09-17_pre_phase4_audit/`; all other tracked `docs/**` files now show as renames/deletions in `git status` because of the archive move performed by S0.

## 3. Recent history (`git log --oneline -20`)

The repository has **13 commits in total**; the command returned all of them.

```
ed14f6b feat(ui): add live speech bubble, manual text chat, context menu, and anime voice actress default
cc63361 fix(ui): eliminate white edge artifacts using dual-sheet chromakey mask extraction
22ac549 feat(senses): add Alt-Gr (VK_RMENU) / Right-Alt support to PTTListener by default
e1139f7 fix(env_check): recognize resident llama-server under canonical 9500 MB dGPU budget
066dad3 feat(ui): integrate Chrono Trigger Lucca 2D sprite sheet, transparent frame atlas, and IPC state animations with RMS lip-sync
b75ce27 feat(router): complete Phase 4 Executive Router, Decision Logging & Auto-Labeling + Affect Layer (Spec 06, ADR-008, ADR-009)
f91fbfa feat(memory): complete Phase 3 Memory & Knowledge Subsystem (ADR-002, ADR-006, Spec 03, Spec 04)
2eaa58d feat(phase2): complete hardened split sandboxes, host launcher, egress policy, and live hardware verification
0c673dc feat(phase1): complete ears and voice pipeline with live hardware verification
401151a feat(phase0): complete feasibility spikes, benchmarks, and results report
18b0508 feat: rewrite 7 scaffold modules and verify T1 tests
be304e6 Step 1 Complete: Dependencies updated per Spec 11, uv.lock generated, canonical .wslconfig configured, core ports/schemas established (zero-Any), lucca-admin env-check implemented, static gates green (ruff/mypy)
0b5b973 Initial commit: Complete Project Lucca documentation suite, Antigravity IDE workspace configuration, and core architecture scaffolding
```

Note for `DRIFT` auditors: commit `b75ce27` cites an **ADR-009** that does not exist in the archived docs set (archived ADRs: 001–008 and 010).

## 4. Root directory listing

Directories present at repo root (including hidden):

```
.agents  .git  .hypothesis  .mypy_cache  .pytest_cache  .ruff_cache  .venv  .vscode
assets  build  config  dist  docker  docs  packaging  scripts  src  tests
```

`build/` and `dist/` are PyInstaller outputs (untracked/ignored). `.venv/` is the `uv` environment. None of these are inventoried below.

## 5. File inventory with line counts

### 5.1 `src/` — 71 files, **14,905 lines**

| Path | Bytes | Lines |
|---|---:|---:|
| `src/lucca/__init__.py` | 77 | 2 |
| `src/lucca/admin.py` | 597 | 22 |
| `src/lucca/brain/chunker.py` | 7580 | 196 |
| `src/lucca/brain/llm_client.py` | 7608 | 174 |
| `src/lucca/brain/prompt_builder.py` | 26262 | 584 |
| `src/lucca/brain/server_ctl.py` | 13136 | 336 |
| `src/lucca/brain/toolcall_demux.py` | 5645 | 130 |
| `src/lucca/core/__init__.py` | 61 | 1 |
| `src/lucca/core/affect.py` | 7965 | 183 |
| `src/lucca/core/config.py` | 4997 | 132 |
| `src/lucca/core/env_check.py` | 6526 | 165 |
| `src/lucca/core/events.py` | 1863 | 64 |
| `src/lucca/core/exceptions.py` | 5009 | 140 |
| `src/lucca/core/ipc_schemas.py` | 6167 | 166 |
| `src/lucca/core/orchestrator.py` | 26601 | 608 |
| `src/lucca/core/schemas.py` | 10526 | 310 |
| `src/lucca/core/trace.py` | 2178 | 61 |
| `src/lucca/main.py` | 5885 | 150 |
| `src/lucca/memory/db.py` | 4566 | 113 |
| `src/lucca/memory/entities.py` | 3334 | 90 |
| `src/lucca/memory/extraction.py` | 5804 | 154 |
| `src/lucca/memory/gate.py` | 4949 | 115 |
| `src/lucca/memory/manager.py` | 8921 | 217 |
| `src/lucca/memory/migrations/0001_init.sql` | 5352 | 135 |
| `src/lucca/memory/migrations/0002_decisions.sql` | 1369 | 36 |
| `src/lucca/memory/retrieval.py` | 9845 | 223 |
| `src/lucca/memory/signers.py` | 5103 | 121 |
| `src/lucca/memory/store.py` | 21437 | 481 |
| `src/lucca/memory/tokens.py` | 4264 | 182 |
| `src/lucca/memory/working.py` | 1967 | 50 |
| `src/lucca/ports.py` | 3797 | 92 |
| `src/lucca/reasoning/lifecycle.py` | 9253 | 234 |
| `src/lucca/reasoning/scheme/__init__.py` | 603 | 33 |
| `src/lucca/reasoning/scheme/eval.py` | 7362 | 197 |
| `src/lucca/reasoning/scheme/lexer.py` | 3854 | 105 |
| `src/lucca/reasoning/scheme/parser.py` | 12331 | 331 |
| `src/lucca/reasoning/scheme/prims.py` | 13388 | 326 |
| `src/lucca/reasoning/scheme/validator.py` | 4690 | 116 |
| `src/lucca/router/conformal.py` | 2336 | 51 |
| `src/lucca/router/heuristic.py` | 13755 | 332 |
| `src/lucca/router/labeler.py` | 7171 | 174 |
| `src/lucca/sandbox/container_spec.py` | 3022 | 101 |
| `src/lucca/sandbox/egress.py` | 6410 | 172 |
| `src/lucca/sandbox/file_tool.py` | 13345 | 315 |
| `src/lucca/sandbox/launcher.py` | 8894 | 206 |
| `src/lucca/sandbox/policy.py` | 2830 | 77 |
| `src/lucca/sandbox/rpc.py` | 12019 | 289 |
| `src/lucca/sandbox/service.py` | 8526 | 200 |
| `src/lucca/sandbox/system_tools.py` | 9174 | 224 |
| `src/lucca/sandbox/web_tool.py` | 6738 | 166 |
| `src/lucca/sandbox/workspace.py` | 4307 | 102 |
| `src/lucca/senses/__init__.py` | 0 | 0 |
| `src/lucca/senses/asr.py` | 3379 | 99 |
| `src/lucca/senses/audio_proc.py` | 13255 | 326 |
| `src/lucca/senses/dsp_chain.py` | 8432 | 212 |
| `src/lucca/senses/embed.py` | 5511 | 129 |
| `src/lucca/senses/npu_proc.py` | 6639 | 174 |
| `src/lucca/senses/ptt.py` | 5103 | 119 |
| `src/lucca/senses/ring_buffer.py` | 9095 | 220 |
| `src/lucca/senses/tts.py` | 7842 | 177 |
| `src/lucca/senses/vad.py` | 2087 | 51 |
| `src/lucca/ui/__init__.py` | 0 | 0 |
| `src/lucca/ui/app.py` | 17990 | 420 |
| `src/lucca/ui/commorose.py` | 10105 | 254 |
| `src/lucca/ui/input_bar.py` | 8072 | 219 |
| `src/lucca/ui/settings_dialog.py` | 120134 | 2100 |
| `src/lucca/ui/speech_bubble.py` | 13510 | 321 |
| `src/lucca/ui/sprite.py` | 11771 | 260 |
| `src/lucca/ui/states.py` | 1666 | 62 |
| `src/lucca/ui/telemetry_hud.py` | 14065 | 352 |
| `src/lucca/ui/theme.py` | 6026 | 226 |

Observations for later subtasks (not findings yet): `src/lucca/senses/__init__.py` and `src/lucca/ui/__init__.py` are 0 bytes while `git status` marks both as modified; `src/lucca/ui/settings_dialog.py` is 2,100 lines / 120 KB, ~14 % of all `src/` lines in a single module; there is no `__init__.py` in `brain/`, `memory/`, `reasoning/`, `router/`, or `sandbox/` (namespace packages).

### 5.2 `tests/` — 30 text files (4,188 lines) + 24 binary fixtures

| Path | Bytes | Lines |
|---|---:|---:|
| `tests/conftest.py` | 459 | 17 |
| `tests/fakes/fake_asr.py` | 656 | 20 |
| `tests/fakes/fake_llm.py` | 1258 | 35 |
| `tests/fakes/fake_tts.py` | 1338 | 35 |
| `tests/fixtures/audio_tool_calls/browser_01.wav` | 35542 | (binary) |
| `tests/fixtures/audio_tool_calls/browser_02.wav` | 41686 | (binary) |
| `tests/fixtures/audio_tool_calls/browser_03.wav` | 36908 | (binary) |
| `tests/fixtures/audio_tool_calls/browser_04.wav` | 42368 | (binary) |
| `tests/fixtures/audio_tool_calls/calc_01.wav` | 42368 | (binary) |
| `tests/fixtures/audio_tool_calls/calc_02.wav` | 60800 | (binary) |
| `tests/fixtures/audio_tool_calls/calc_03.wav` | 51244 | (binary) |
| `tests/fixtures/audio_tool_calls/calc_04.wav` | 49196 | (binary) |
| `tests/fixtures/audio_tool_calls/notepad_01.wav` | 36224 | (binary) |
| `tests/fixtures/audio_tool_calls/notepad_02.wav` | 44416 | (binary) |
| `tests/fixtures/audio_tool_calls/notepad_03.wav` | 43734 | (binary) |
| `tests/fixtures/audio_tool_calls/notepad_04.wav` | 34860 | (binary) |
| `tests/fixtures/audio_tool_calls/taskmgr_01.wav` | 44416 | (binary) |
| `tests/fixtures/audio_tool_calls/taskmgr_02.wav` | 53292 | (binary) |
| `tests/fixtures/audio_tool_calls/taskmgr_03.wav` | 53974 | (binary) |
| `tests/fixtures/audio_tool_calls/taskmgr_04.wav` | 41686 | (binary) |
| `tests/fixtures/audio_tool_calls/terminal_01.wav` | 37590 | (binary) |
| `tests/fixtures/audio_tool_calls/terminal_02.wav` | 46464 | (binary) |
| `tests/fixtures/audio_tool_calls/terminal_03.wav` | 44416 | (binary) |
| `tests/fixtures/audio_tool_calls/terminal_04.wav` | 36224 | (binary) |
| `tests/fixtures/audio_tool_calls/test_30_5s.wav` | 976044 | (binary) |
| `tests/fixtures/audio_tool_calls/test_3s_tone.wav` | 96044 | (binary) |
| `tests/fixtures/conversational_hello.wav` | 65580 | (binary) |
| `tests/fixtures/conversational_speech.wav` | 54656 | (binary) |
| `tests/fixtures/grounding/40_pairs.jsonl` | 7321 | 40 |
| `tests/fixtures/retrieval/identifiers.jsonl` | 6142 | 30 |
| `tests/fixtures/retrieval/paraphrase20.jsonl` | 3952 | 20 |
| `tests/fixtures/router/labeling_pairs.jsonl` | 7953 | 30 |
| `tests/fixtures/router/router_fixtures.jsonl` | 9530 | 135 |
| `tests/test_affect.py` | 2810 | 66 |
| `tests/test_chunker.py` | 5482 | 128 |
| `tests/test_confirmation.py` | 6589 | 189 |
| `tests/test_dsp_chain.py` | 5740 | 121 |
| `tests/test_gguf_parser.py` | 3205 | 88 |
| `tests/test_grounding.py` | 11950 | 282 |
| `tests/test_ipc_codec.py` | 4240 | 114 |
| `tests/test_lifecycle.py` | 5783 | 138 |
| `tests/test_memory_db.py` | 30019 | 699 |
| `tests/test_persona_toml.py` | 4587 | 108 |
| `tests/test_phase1_live_hw.py` | 7563 | 167 |
| `tests/test_phase2_live_hw.py` | 3016 | 91 |
| `tests/test_prompt_builder.py` | 5169 | 122 |
| `tests/test_provenance.py` | 8744 | 207 |
| `tests/test_ring_buffer.py` | 4120 | 115 |
| `tests/test_router.py` | 16558 | 373 |
| `tests/test_sandbox.py` | 13818 | 305 |
| `tests/test_scheme.py` | 8748 | 209 |
| `tests/test_server_ctl.py` | 4611 | 117 |
| `tests/test_turn_loop.py` | 4669 | 116 |
| `tests/test_ui_widgets.py` | 2738 | 71 |

Test modules: 22. Fake adapters: 3. JSONL fixtures: 5 (255 records total). WAV fixtures: 24.

### 5.3 `config/` — 3 files, **63 lines**

| Path | Bytes | Lines |
|---|---:|---:|
| `config/intents.toml` | 878 | 16 |
| `config/persona.toml` | 776 | 20 |
| `config/tool_whitelist.toml` | 620 | 27 |

### 5.4 `docker/` — 3 files, **196 lines**

| Path | Bytes | Lines |
|---|---:|---:|
| `docker/file-sandbox/Dockerfile` | 417 | 10 |
| `docker/toolsrv/server.py` | 6624 | 177 |
| `docker/web-sandbox/Dockerfile` | 378 | 9 |

### 5.5 `scripts/` — 15 files, **1,066 lines**

| Path | Bytes | Lines |
|---|---:|---:|
| `scripts/bench_asr_ladder.py` | 2075 | 47 |
| `scripts/bench_tts.py` | 1358 | 32 |
| `scripts/create_desktop_shortcut.ps1` | 427 | 9 |
| `scripts/download_llm_models.py` | 1832 | 44 |
| `scripts/generate_test_audio.py` | 2323 | 53 |
| `scripts/make_shortcut.py` | 751 | 19 |
| `scripts/run_spike02_suite.py` | 17140 | 423 |
| `scripts/setup_wslconfig.ps1` | 1633 | 34 |
| `scripts/test_audio_req.py` | 744 | 22 |
| `scripts/test_faster_whisper.py` | 1014 | 25 |
| `scripts/test_kokoro_npu_buckets.py` | 658 | 15 |
| `scripts/test_kokoro_ov.py` | 818 | 22 |
| `scripts/test_s1_startup.py` | 1250 | 51 |
| `scripts/verify_environment.py` | 8870 | 234 |
| `scripts/wsl/lucca-egress.sh` | 1871 | 36 |

### 5.6 `packaging/` — 1 file, **83 lines**

| Path | Bytes | Lines |
|---|---:|---:|
| `packaging/build_exe.py` | 3426 | 83 |

### 5.7 Root files — 9 files, **2,353 lines** (364 excluding `uv.lock`)

| Path | Bytes | Lines |
|---|---:|---:|
| `.env.example` | 542 | 15 |
| `.gitignore` | 545 | 45 |
| `AGENTS.md` | 3989 | 44 |
| `GEMINI.md` | 3759 | 44 |
| `launch_lucca.bat` | 102 | 5 |
| `Lucca.spec` | 1272 | 42 |
| `pyproject.toml` | 2713 | 98 |
| `README.md` | 8094 | 71 |
| `uv.lock` | 397307 | 1989 |

### 5.8 Totals

| Scope | Text files | Lines |
|---|---:|---:|
| `src/` | 71 | 14,905 |
| `tests/` | 30 | 4,188 |
| `config/` | 3 | 63 |
| `docker/` | 3 | 196 |
| `scripts/` | 15 | 1,066 |
| `packaging/` | 1 | 83 |
| **Code + tests + config (six trees)** | **123** | **20,501** |
| Root files excluding `uv.lock` | 8 | 364 |
| **Audit-relevant total (excl. `uv.lock`)** | **131** | **20,865** |
| `uv.lock` | 1 | 1,989 |
| **Grand total, everything measured** | **132** | **22,854** |

Binary files (not counted): 24 WAV fixtures under `tests/fixtures/`. Not inventoried: `assets/` (icons + sprite PNGs), `.agents/`, `.vscode/`, caches, `.venv/`, `build/`, `dist/`, `docs/`.

## 6. `pyproject.toml` — verbatim extracts (read-only)

### 6.1 `[project.scripts]`

```toml
[project.scripts]
lucca-admin = "lucca.admin:main"
lucca = "lucca.main:main"
```

### 6.2 `[tool.pytest.ini_options]` (markers and surrounding config)

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
python_files = ["test_*.py"]
pythonpath = [".", "src"]
asyncio_mode = "auto"
markers = [
    "hw: Hardware-dependent tests (NPU/dGPU/Audio)",
    "soak: Long-running stability and soak tests",
]
```

Only two markers are registered: `hw` and `soak`. There is no marker for tier (T0–T3) or for `docker`/`wsl`-dependent tests; `TEST` auditors should check whether `test_phase2_live_hw.py` and `test_sandbox.py` rely on unregistered markers or on skip logic.

### 6.3 Other build-relevant facts (for reference)

- `[project]` `name = "project-lucca"`, `version = "0.2.0"`, `requires-python = ">=3.12"`.
- Build backend: `hatchling`; wheel packages `["src/lucca"]`.
- `[tool.ruff]` `line-length = 100`, `target-version = "py312"`, select `E F W I B BLE S UP ANN PL`; broad per-file ignores for `tests/*`, `scripts/*`, `packaging/*`, `**/ui/*`, `**/sandbox/*`, `**/senses/*`, `**/env_check.py`.
- `[tool.mypy]` `disallow_untyped_defs = true`, `warn_return_any = true`; `ignore_missing_imports` for `sounddevice openvino kokoro_onnx sqlite_vec zmq PyQt6 transformers faster_whisper ulid psutil torch`.
- `[dependency-groups] dev = ["pyinstaller>=6.22.3"]` in addition to `[project.optional-dependencies] dev`.

## 7. Archive operation record (performed by S0)

- Destination: `docs/archive/2026-09-17_pre_phase4_audit/`
- Items moved: 2 directories (`08_adr/`, `09_developer_spec/`) + 26 loose `.md` files → **47 files, 512,415 bytes**, relative structure preserved. Zero move failures. `docs/` contained only `archive/` afterwards.
- `ARCHIVE_INDEX.md` generated (UTF-8, no BOM) with SHA-256 for all 47 files; index timestamp `2026-09-17T23:56:15Z`.
- Read-only attribute applied to all 48 files in the archive (47 + index); verified `IsReadOnly = True` on 48/48.
- Anomaly: the first index generation used the default (ANSI) encoding for reading headings and produced mojibake for em-dashes; it was regenerated with `-Encoding UTF8` and rewritten before the read-only pass. No archived source file was touched.
