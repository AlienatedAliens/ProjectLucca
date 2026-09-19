# Project Lucca — System Architecture Specification (Post-Audit Baseline)

**Status:** Canonical Post-Audit Architecture Baseline (supersedes all pre-audit specs under `docs/archive/`)  
**Version:** 0.2.0  
**Updated:** September 2026  
**Charter Reference:** Ratified per D-AUD-19 (documentation from code truth) following Phase 0–8 remediation.

---

## 1. Executive Summary & System Philosophy

Project Lucca is an autonomous, local-first desktop companion agent designed for high-performance Windows workstations (specifically optimized for hybrid Intel Core Ultra NPU + NVIDIA GeForce RTX dGPU architectures). 

The system provides low-latency voice interaction, dynamic prompt memory retrieval, intent-routed action execution, sandboxed tool operation, and continuous self-improving reasoning without relying on external cloud APIs.

```
                      ┌────────────────────────────────────────┐
                      │          Desktop User (PTT / UI)       │
                      └──────────────────┬─────────────────────┘
                                         │ Alt-Gr / Audio / Text
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                PROCESS TOPOLOGY                                        │
│                                                                                        │
│  ┌───────────────────────┐   ZeroMQ IPC Bus / Rings    ┌────────────────────────────┐  │
│  │     lucca-audio       │ ◄─────────────────────────► │         lucca-npu          │  │
│  │  (WASAPI In/Out, VAD, │                             │ (Intel NPU OpenVINO ASR &  │  │
│  │   Ring Mutex, PTT)    │                             │  Kokoro TTS w/ DSP Chain)  │  │
│  └───────────┬───────────┘                             └─────────────┬──────────────┘  │
│              │                                                       │                 │
│              │ Audio Frames (Shared Ring Buffers)                    │ Transcripts     │
│              ▼                                                       ▼ & Audio Chunks  │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                  lucca-core                                      │  │
│  │  - Orchestrator Turn Loop            - MicroScheme Rule Lifecycle Manager        │  │
│  │  - Heuristic & Conformal Router      - SQLite-vec & FTS5 Hybrid Memory Store     │  │
│  │  - Streaming Chunker & TTS Queue     - Isolated Docker / WSL2 Sandbox Service    │  │
│  └───────────────────────────────────────────┬──────────────────────────────────────┘  │
│                                              │ HTTP / Slots SSE Stream                 │
│                                              ▼                                         │
│                                 ┌─────────────────────────┐                            │
│                                 │      llama-server       │                            │
│                                 │ (CUDA 12.8 native GGUF: │                            │
│                                 │  Ultravox / Mistral-12B)│                            │
│                                 └─────────────────────────┘                            │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Process Topology & IPC Infrastructure

The runtime is strictly decoupled into four coordinated operating system processes supervised with exponential restart backoff:

| Process | Executable / Entrypoint | Hardware Domain | Memory Budget | Primary Role |
|---|---|---|---|---|
| **`lucca-core`** | `python -m lucca.main` | Host CPU (Thread pool) | $\le 900\text{ MB}$ RSS | Turn orchestration, state machine, memory gating, routing, rule reasoning, tool execution. |
| **`lucca-audio`** | `python -m lucca.senses.audio_proc` | Host Audio (WASAPI) | $\le 80\text{ MB}$ RSS | 16 kHz capture & 24 kHz playback streams, VAD trimming, ring buffer memory control, PTT polling. |
| **`lucca-npu`** | `python -m lucca.senses.npu_proc` | Intel NPU / GPU | $\le 450\text{ MB}$ RSS | OpenVINO Whisper-large-v3-turbo transcription, ONNX Kokoro-v1.0 TTS synthesis + Anime DSP chain. |
| **`llama-server`**| `llama-server.exe` | NVIDIA dGPU (CUDA 12.8)| $\le 9.5\text{ GB}$ VRAM | In-process KV cache (q8_0, 8192 ctx), streaming token generation, GBNF grammar enforcement. |

### Inter-Process Communication (IPC)
Communication across process boundaries strictly respects the port allocations in `lucca.core.config.IPCSettings`:
- **Control Port (`tcp://127.0.0.1:47001`)**: ZeroMQ `REQ/REP` pattern for synchronous control queries (ping/pong health checks, process lifecycle commands).
- **Event Bus Port (`tcp://127.0.0.1:47002`)**: ZeroMQ `PUB/SUB` pattern for asynchronous broadcast events (UI state updates, speech captions, telemetry, shutdown signals).
- **Ingest Port (`tcp://127.0.0.1:47003`)**: ZeroMQ `PUSH/PULL` socket (`RCVHWM=1000`) for high-throughput sensor telemetry (PTT down/up, audio sequence indices, user text input).

### Shared Memory Rings & Named Mutexes
Audio transfers between `lucca-audio`, `lucca-core`, and `lucca-npu` bypass socket serialization using shared memory ring buffers (`lucca_capture_ring` and `lucca_playback_ring`):
- **NamedRingMutex**: Cross-process atomic updates to ring headers (`read_index`, `write_index`, `flags`) are synchronized using platform-native named mutexes (`Global\lucca_ring_mutex_<name>`).
- **Stale Slice Detection**: `read_slice(start_seq, end_seq)` mechanically asserts that requested audio sequence intervals have not been overwritten by buffer wraps; overrun windows are safely discarded with zero-speech reporting (`vad_speech_ms=0`).
- **Barge-in Flags**: Atomic flags `FLAG_ABORT` and `FLAG_EOS` in the header communicate immediate audio interruption and playback completion.

---

## 3. Turn Lifecycle & Concurrency Disciplines

Turn execution follows the normative state progression defined in ADR-0009 and Spec 10:

```
[IDLE] ──► PTT Down (t_key_press)
  │
  ├──► [LISTENING] (User speaking into capture ring)
  │
  ├──► PTT Up (t_key_release) ──► VAD Trimmed (t_vad_done)
  │
  ├──► [THINKING] ──► Intent Routing / Memory Retrieval / LLM Dispatch (t_llm_sent)
  │                      │
  │                      ├──► First Token Delta (t_llm_first_token)
  │                      ├──► Streaming Chunker Clause (t_first_chunk)
  │                      └──► Async Synthesis Queue ──► TTS First Done (t_tts_first_done)
  │
  ├──► [SPEAKING] ──► Speaker First Audio Sample (t_first_sample)
  │                      │
  │                      └──► Synthesis Finishes ──► Ring Drained (t_playback_done)
  │
  └──► [POSTTURN] ──► Decision Labels & Transcript Provenance Committed (t_postturn_done)
        │
        └──► [IDLE]
```

### Concurrency Rules
1. **Per-Stream LLM Abort Registry**: Abort signals are tracked via a concurrent registry keyed by `trace_id`. Aborting an active or stale turn never corrupts subsequent turns or global client state.
2. **Worker Thread Bounded Join**: On barge-in (user presses PTT while assistant is speaking or thinking), the orchestrator clears active synthesis queues, signals the abort event, and cleanly joins the prior worker thread with a bounded timeout before starting the new turn.
3. **Decoupled TTS Worker**: Kokoro TTS synthesis runs on a dedicated background worker (`core-tts`) connected via a bounded queue (`_tts_queue: queue.Queue(maxsize=8)`). Token streaming from `llama-server` is never blocked by audio synthesis latency.
4. **Non-Blocking Voice Confirmation**: Spoken responses during `confirm_wait` are stashed immediately on the ingest thread as raw slice coordinates and transcribed exclusively by the waiting turn worker thread.

---

## 4. Subsystems: Memory, Routing, Reasoning & Sandbox

### 4.1 Hybrid Memory & Cryptographic Provenance
- **Engine**: SQLite 3 with `sqlite-vec` (dense vector embeddings) and `FTS5` (BM25 full-text search).
- **Provenance Gate**: Every memory mutation must cross the `ProvenanceGate` verified with HMAC/Ed25519 digital signatures. Four authorized tiers exist: `USER_EXPLICIT`, `SYSTEM_FACT`, `INFERRED`, `TOOL_CONTENT_UNTRUSTED`.
- **Bi-temporal Audit Trail**: Updates and deletions never delete original envelopes in place; mutations insert superseding rows with continuous audit timestamps.
- **Prompt Injection Defense**: Memory blocks formatted into LLM context are bounded by character quotas ($\le 600\text{ chars}$) and wrapped in security delimiters (`[USER_MEMORY_BLOCK_START: UNTRUSTED] ... [USER_MEMORY_BLOCK_END]`).

### 4.2 Executive Router & Decision Telemetry
- **Intent Classifier**: Maps transcripts to structured intents (`LAUNCH_APP`, `SYSTEM_CONTROL`, `CALCULATE`, `SEARCH`, `CONVERSATION`).
- **Deterministic Action**: High-confidence rule intents route directly to `RULE` execution without invoking the LLM, responding in $< 150\text{ ms}$.
- **Conformal Prediction**: Ambiguous intents falling below conformal thresholds yield fallback sets preventing hallucinated tool actions.
- **Audit Logging**: Every routing decision is persisted to `logs/decisions.jsonl` and SQLite `decision_records` with zero fabricated probability values.

### 4.3 MicroScheme Rule Engine
- **Language**: Pure, sandboxed dialect of Scheme (`MicroScheme`) with strictly bounded computational resources (gas limit: 1000, recursion limit: 50).
- **Lifecycle Management**: Candidate rules transition through `DRAFT` $\rightarrow$ `SHADOW` $\rightarrow$ `QUARANTINE` $\rightarrow$ `PROMOTED`.
- **Zero-Failure Invariant**: Promoted rules are executed with priority; a single failure in production instantly demotes the rule back to quarantine.
- **Persistence**: Rule definitions and regression fixture histories survive process restarts in `rules.db`.

### 4.4 Sandboxed Tool Execution
- **Isolation Baseline**: The direct host fallback is disabled by default (`use_direct_fallback = False`). Tool execution defaults strictly to containerized Docker / WSL2 sandboxes:
  - File tools: Isolated container with `--network none` and restricted volume mounts.
  - Web tools: Ephemeral container with network egress restricted by `scripts/wsl/lucca-egress.sh` iptables rules (host LAN blocked, IPv6 disabled).
- **Whitelisting**: Application launching is strictly governed by `config/tool_whitelist.toml`. Arbitrary system commands (`cmd.exe`, `powershell.exe`) are forbidden.

---

## 5. Graceful Teardown & Supervisor Contract

Ordered shutdown follows Spec 01 §7 and prevents state corruption or dangling shared memory:
1. **Offline Broadcast**: UI publishes `ui.state = offline` and sends `ui.quit` to the event bus.
2. **Turn Abort**: Active turn worker threads and TTS synthesis queues are immediately drained and joined.
3. **Buffer Flush & Unlink**: Shared memory rings assert `FLAG_ABORT`, release mutex handles, and cleanly unlink from the OS.
4. **Child Process Teardown**: Supervisor terminates child processes gracefully via `SIGINT`/`SIGBREAK`, waiting up to 3.0s before issuing `SIGKILL`.
