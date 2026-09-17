# Spec 11 — Configuration, Observability, RAM Budget, Dependencies, Static Gates, Admin CLI

## 1. Configuration (`pydantic-settings`)

Precedence (highest first): CLI flags → environment variables (`LUCCA_*`) → `%LUCCA_HOME%\config\lucca.toml` → `%LUCCA_HOME%\config\.env` (secrets only) → built-in defaults. `LUCCA_HOME` default `C:\ProjectLucca`; dev default `<repo>\.lucca_home` when `LUCCA_ENV=dev`. **No absolute path may appear in source.**

```toml
# lucca.toml (defaults shown)
[env]      mode = "prod"                    # prod|dev
[paths]    # all relative to LUCCA_HOME; overriding is allowed but discouraged
models = "models"  data = "data"  workspace = "workspace"  inbox = "inbox"  logs = "logs"  cache = "cache"
[llm]      mode = "audio"                   # audio|transcript (ADR-001)
host = "127.0.0.1"  port = 8080  ctx = 8192  kv_type = "q8_0"  max_tokens = 512  temperature = 0.6
model = "llm/ultravox-v0_5-llama-3_1-8b-Q6_K.gguf"  mmproj = "llm/mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf"
text_model = ""                                              # cascade uses the same backbone file without --mmproj (ADR-001 R-07); set only if S10 shows the backbone is unusable as text-only
[asr]      model = "asr/whisper-large-v3-turbo-ov"  device_ladder = ["NPU","GPU","CPU"]  lowconf_logprob = -0.5
[tts]      model = "tts/kokoro-v1"  voice = "af_heart"  device_ladder = ["NPU","GPU","CPU"]  speak_code = false  speak_urls = false
[audio]    capture_device = ""  playback_device = ""  capture_rate = 16000  playback_rate = 24000  exclusive = false  jitter_ms = 60
[ptt]      key = "right ctrl"  mode = "hold"  max_seconds = 29.5  swallow = false
[memory]   k = 8  memory_tokens = 600  audio_retention_days = 7  backup_daily = true
[router]   version = "heuristic"           # heuristic|classifier
[rules]    gas_limit = 1000  timeout_ms = 20  promote_min_clusters = 5
[reflection] enabled = true  idle_seconds = 60  min_new_decisions = 10  min_interval_minutes = 10
[sandbox]  wsl_distro = "Ubuntu"  file_mem_mb = 768  web_mem_mb = 512  allow_render = false
[ipc]      ctl_port = 47001  bus_port = 47002  ingest_port = 47003
[ui]       enabled = true  fps_active = 30  fps_idle = 5
[log]      level = "INFO"  json = true  retention_days = 30
```
`.env`: `LUCCA_MASTER_KEY=<base64 32 bytes>` only. Validation errors print the field path and exit code 2.

## 2. Logging & metrics

- `structlog` → JSON lines, one file per process per day: `logs\<proc>-YYYYMMDD.jsonl`; fields `ts, level, proc, event, trace_id, **kv`. Never log transcripts at INFO (privacy) — DEBUG only, off by default. Never log keys, tool bodies > 200 chars.
- Latency traces per spec 10 → `logs\traces.jsonl` + `turn_traces` table.
- Counters/gauges in SQLite `metrics(ts, name, value, labels_json)` sampled every 10 s: `rss_mb{proc}`, `vram_mb`, `underruns`, `turns`, `rejects{provenance}`, `rule_fired{status}`, `router_fallback`, `wsl_mem_mb`. `lucca-admin metrics --since 1h`.
- Event taxonomy prefixes: `boot.*, turn.*, asr.*, tts.*, llm.*, mem.*, rule.*, router.*, sbx.*, ui.*, sys.*`. New events require adding to `lucca/core/events.py` enum (test enforces no free-form event names).

## 3. Error taxonomy (`lucca/core/exceptions.py`)

`LuccaError` → `ConfigError`, `BootError`, `IPCError`, `LLMError{Unavailable,Timeout,Protocol}`, `ASRError`, `TTSError`, `MemoryError_{CommitFailed,Locked,Integrity}`, `ProvenanceRejected`, `GroundingError`, `SchemeError{Syntax,Runtime,Gas,Timeout}`, `RuleError{Conflict,Validation}`, `SandboxError{Path,Timeout,Protocol,Egress}`, `LauncherError{NotWhitelisted,RateLimited}`, `RouterError{InsufficientCalibration}`. Every `except Exception` in `src/` must re-raise as one of these or log with `exc_info` and continue — bare `except: pass` is banned by ruff config (`BLE001`, `S110`).

## 4. Host RAM budget (canonical **estimates** — the per-process **caps** that trigger alarms are in ADR-008; all measured in Phase 0 and re-baselined)

| Tenant | Steady RSS | Note |
|---|---|---|
| Windows 11 + shell + drivers | 4 500 MB | doc 01 L28 |
| `llama-server.exe` | 600 MB* | weights in VRAM |
| `lucca-core` | 700 MB* | Python, SQLite cache 64 MB, networkx view |
| `lucca-npu` | 1 900 MB* | spec 07 §9 |
| `lucca-audio` | 120 MB* | |
| `lucca-ui` | 90 MB* | PyQt6 |
| WSL2 VM (clamp) | 4 608 MB | pinned when running; contains dockerd + sandbox |
| **Total** | **≈ 12 500 MB** | alarm ≥ 13 500; hard stop (refuse reflection/extraction) ≥ 14 500 |

Sandbox inside WSL2: kernel+init 400 + dockerd 300 + file-sandbox ≤ 768 + web-sandbox ≤ 512 (+ js 1 024 on demand) → ≤ 3 000 MB peak of 4 608.

VRAM: 9.5 GB gate (register B1). dGPU baseline < 300 MB in MSHybrid.

## 5. Dependencies (`pyproject.toml` — replace current list)

Runtime: `pydantic>=2.7`, `pydantic-settings>=2.3`, `httpx>=0.27`, `pyzmq>=26`, `numpy>=1.26,<2.3`, `sounddevice>=0.4.7`, `onnxruntime>=1.18` (Silero, CPU Kokoro), `openvino>=2025.1`, `openvino-genai>=2025.1`, `openvino-tokenizers>=2025.1`, `kokoro-onnx>=0.3` (or `kokoro` + `misaki[en]`), `sqlite-vec>=0.1.6`, `rapidfuzz>=3.9`, `structlog>=24`, `psutil>=6`, `PyQt6>=6.7`, `lightgbm>=4.3`, `scikit-learn>=1.5`, `python-ulid>=2`, `rich>=13`.
Sandbox images (not host): `httpx`, `trafilatura`, `playwright` (js image only).
Dev: `pytest>=8`, `pytest-asyncio`, `pytest-timeout`, `hypothesis>=6.100`, `mypy>=1.10`, `ruff>=0.5`, `import-linter>=2`, `pytest-cov`, `faster-whisper` (CPU ASR fallback + WER tests), `jiwer` (WER).
**Removed:** `chromadb`, `rank-bm25`, `pynput`, any `vllm`, `networkx` stays (view only).
`uv lock` committed; CI runs `uv sync --frozen`.

## 6. Static gates (Tier 0; all must pass before any PR merges)

| Tool | Config | Gate |
|---|---|---|
| `ruff` | `select = ["E","F","W","I","B","BLE","S","UP","ANN","PL"]`, `ANN401` (no `Any`) enabled, `S110/S112` (bare except) enabled | 0 findings |
| `mypy --strict` | `disallow_any_explicit = true` for `src/lucca/core`, `ports`, all `*_schemas.py`; `warn_return_any` | 0 errors |
| `import-linter` | contracts: layers `ui/senses/sandbox/brain/reasoning/router/memory → core`; forbidden `brain → memory.signers`; forbidden `reasoning.scheme → {memory,sandbox,brain}`; forbidden `senses.audio_proc → {openvino,torch,sqlite3,PyQt6}`; independence `senses.audio_proc | ui` | pass |
| AST tests | signer construction allow-list (spec 03); event-name enum; no `shell=True`; no `pickle` import outside tests; no `os.startfile` | pass |
| `pytest -m "not hw and not soak"` | Tier 1–2 | pass, coverage ≥ 85 % on `core, memory, reasoning, router, brain.chunker, sandbox.file_tool` |

## 7. Admin CLI (`lucca-admin`, `src/lucca/admin.py`)

`env-check` (all boot checks, exit code per failure), `latency [--last N] [--mode]`, `metrics --since`, `memory export|search|forget <id>|prune --kind transcript --older-than 180d|integrity|backup|restore <file>` (`prune` is opt-in; default retention of transcripts is indefinite), `rules list|show <id>|retire <id>|regress`, `router report`, `sandbox verify|rebuild|reset-workspace`, `models verify` (sha256 of every model file against `models\MANIFEST.json`), `replay <session_id>` (deterministic re-run of a recorded session with FakeClock/FakeRandom — used for human gates, D-09), `logs tail <proc>`.

## 8. Privacy & retention (user-facing, also in README)

- Nothing leaves the machine except sandbox web fetches to public 80/443 (no telemetry anywhere; `trafilatura`/`httpx` UA identifies Lucca).
- Audio clips 7 days; transcripts until "forget"; tool bodies 24 h; logs 30 days; traces 90 days; backups 14 d/8 w.
- `lucca-admin memory export` gives a full human-readable dump; `forget` is a first-class voice command.
