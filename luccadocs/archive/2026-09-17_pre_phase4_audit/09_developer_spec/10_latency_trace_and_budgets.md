# Spec 10 — Latency Trace Schema, Per-Stage Budgets, Context Budget

Canonical numbers from [`07_contradiction_register.md`](../07_contradiction_register.md) §A. Every turn produces one `TurnTrace`; no latency claim is valid unless it comes from this trace.

## 1. Trace points (monotonic ns, converted to ms relative to `t_key_release`)

| Point | Emitted by | Meaning |
|---|---|---|
| `t_key_press` | audio | PTT down (OS timestamp) |
| `t_key_release` | audio | PTT up (OS timestamp) — **latency origin** |
| `t_vad_done` | audio | trimmed span computed |
| `t_asr_sent` / `t_asr_done` | core / npu | transcript request/response |
| `t_route_done` | core | router decision |
| `t_llm_sent` | core | HTTP request sent |
| `t_llm_first_token` | core | first `TokenDelta` or `ToolCallStart` |
| `t_first_chunk` | core | first `TTSChunk` emitted by chunker |
| `t_tts_first_sent` / `t_tts_first_done` | core / npu | first chunk synth |
| `t_first_sample` | audio | first non-silent frame written to device (**latency end**) |
| `t_llm_done` | core | `Done` event |
| `t_tts_last_done` | npu | last chunk synthesised |
| `t_playback_done` | audio | ring drained after EOS |
| `t_posturn_done` | core | memory/decision commits finished |

Plus counters: `tokens_out`, `chunks`, `underruns`, `interrupted`, `mode` (audio|transcript), `route`, `tts_device`, `asr_device`.

Persisted: `logs\traces.jsonl` (one line per turn) and SQLite `turn_traces`. `lucca-admin latency --last 100` prints the table below with median/p95 per stage.

## 2. Stage budgets (audio mode, B primary)

| Stage | From → to | Budget median | Gate p95 | Notes |
|---|---|---|---|---|
| S1 PTT→dispatch | `t_key_release → t_llm_sent` | 15 ms | 30 | VAD trim + wav encode + HTTP send; ASR runs in parallel |
| S2 TTFT | `t_llm_sent → t_llm_first_token` | 180 ms | 300 | *Phase 0 measured; estimate 140–180* |
| S3 first chunk | `t_llm_first_token → t_first_chunk` | 90 ms | 150 | ≥ 24 chars at ~60–90 tok/s ≈ 8–12 tokens |
| S4 TTS first | `t_first_chunk → t_tts_first_done` | 150 ms | 180 | device ladder gate |
| S5 to speaker | `t_tts_first_done → t_first_sample` | 40 ms | 80 | 60 ms jitter buffer partially overlaps synth |
| **Total** | `t_key_release → t_first_sample` | **≈ 475 ms** | **600 median / 800 p95** | canonical gate |

Transcript mode adds S1b `t_key_release → t_asr_done` (budget 250 ms, p95 400) before S2, i.e. total ≈ 700 ms median expected; the Phase 1 gate in transcript mode is **median ≤ 800 ms, p95 ≤ 1 000 ms** and must be reported as transcript mode.

Regression rule: any stage's rolling 20-turn median exceeding its budget by > 25 % for two consecutive sessions raises `latency.regression{stage}` in logs and UI tooltip.

## 3. Secondary budgets

| Item | Gate |
|---|---|
| Barge-in: key-down → silence | ≤ 30 ms |
| Barge-in: key-down → LLM slot idle | ≤ 100 ms |
| Router `route()` | ≤ 2 ms (heuristic), ≤ 15 ms (classifier + NPU encode) |
| Rule engine, all rules | ≤ 5 ms for 50 rules |
| Memory retrieval (hybrid, k=8) | ≤ 25 ms p95 |
| Memory commit (POSTTURN, off critical path) | ≤ 60 ms |
| Extraction LLM call (POSTTURN) | ≤ 2 s; skipped if a new PTT arrives |
| Boot warm / cold | ≤ 25 s / ≤ 120 s |
| Audio callback | < 2 ms p99 |
| Idle CPU (all Lucca processes) | ≤ 3 % of one core; idle RAM per ADR-008 |

## 4. Context token budget (8 192 ctx)

| Section | Tokens | Notes |
|---|---|---|
| System prompt | ≤ 350 | persona, rules of engagement, tool-use instructions |
| Tool schemas | ≤ 600 | 6–8 tools; trimmed descriptions |
| Memory block | ≤ 600 | k ≤ 8 hits, 160 chars each |
| Session summary | ≤ 300 | rolling |
| History (6 exchanges, text) | ≤ 1 200 | truncate oldest first |
| Current audio | ≈ 375 | 30 s max ≈ 12.5 tok/s Whisper-turbo projector output |
| Reply reserve | 512 | `max_tokens` |
| **Total** | **≈ 3 950** | leaves > 4 k headroom for tool results injected mid-turn (each capped 1 500 tokens) |

Prompt builder must place sections in this order so the static prefix (system + tools) is cacheable by `llama-server`.

## 5. Measurement harness (`tests/hw/test_latency_e2e.py`, marker `hw`)

- 20 utterances from `tests/fixtures/utterances/*.wav` injected via a **virtual PTT** (`ptt.inject` debug message) and a **loopback capture** of the playback device (WASAPI loopback) to detect `t_first_sample` independently of the audio process's own claim (cross-check ≤ 15 ms).
- Reports per-stage median/p95, VRAM before/after, RSS of each process, underruns, mode, devices → `logs\latency_report_<ts>.md`.
- Assertions: canonical gates; 10 consecutive turns without crash/desync (desync = loopback-detected audio start differs from `t_first_sample` by > 50 ms); VRAM slope ≤ 20 MB/turn.
- Also run once in transcript mode; both reports are required for Phase 1 sign-off.
