# ADR-008 — Process topology: four Lucca processes + external `llama-server`, ZeroMQ IPC, shared-memory audio ring

**Status:** Accepted 2026-09-17 (D-14)
**Supersedes:** docs 03/05 which describe a "hexagonal architecture" and a single "Python orchestrator" without stating process boundaries.

## Context

Python 3.12 has a GIL. A single process containing the WASAPI callback, JSON parsing, SQLite writes, OpenVINO inference calls, and a Qt event loop **will** produce audio underruns and UI stalls regardless of MMCSS priority. Crash isolation is also needed: an OpenVINO NPU driver fault must not kill the voice loop or lose in-flight memory writes. No document specified how many processes exist, how they talk, or how they start and stop.

## Decision

| Process | Owns | Must never | RAM **cap** (alarm threshold; estimates are in spec 11 §4) |
|---|---|---|---|
| `lucca-audio` | WASAPI capture (16 kHz) and playback (24 kHz) streams via `sounddevice`, PTT hook, Silero VAD (CPU ONNX), jitter buffer, RMS envelope publisher | import torch/openvino/sqlite/Qt; block > 2 ms in the callback | ≤ 150 MB |
| `lucca-core` | Orchestrator state machine, router, rule engine, memory (sole SQLite writer), LLM client (`llama-server` HTTP), sandbox clients, provenance gate, reflection scheduler | open audio devices; render UI | ≤ 900 MB |
| `lucca-npu` | OpenVINO runtime: Whisper (NPU), Kokoro (device per ladder), embeddings (NPU), intent encoder (NPU); compile-cache management | touch SQLite; hold provenance keys | ≤ 2.2 GB (models resident) |
| `lucca-ui` | PyQt6 overlay, confirm prompts, tray icon | anything else | ≤ 100 MB |
| `llama-server.exe` | LLM inference | — | ≤ 0.8 GB host |

### IPC

- **Control plane:** ZeroMQ over `tcp://127.0.0.1:<port>` (ports in `config\lucca.toml`), one `ROUTER` socket in `lucca-core`, `DEALER` in each peer; plus a `PUB/SUB` bus for events (`turn.started`, `tts.chunk`, `audio.rms`, `ui.state`). Every message = 4-byte big-endian length + UTF-8 JSON validated by a Pydantic v2 model in `lucca.core.ipc_schemas` (zero `Any`; dynamic tool args use `JsonValue`). Message envelope: `{type, trace_id, ts_ns, payload}`.
- **Audio plane:** PCM never crosses ZMQ. `multiprocessing.shared_memory` ring buffers: `cap_ring` (16 kHz int16, 60 s), `play_ring` (24 kHz int16, 30 s), each with a 64-byte header (`write_idx`, `read_idx`, `seq`, `flags`) updated atomically via `struct` + a named `Semaphore`. `lucca-npu` writes TTS PCM into `play_ring`; `lucca-audio` drains it.
- **Barge-in:** `lucca-audio` publishes `ptt.pressed` on the PUB bus **and** sets `play_ring.flags |= ABORT`; `lucca-audio` itself zeroes playback within one buffer period (≤ 10 ms) without waiting for core.

### Lifecycle

`lucca-core` is the supervisor (`lucca.main`): starts `llama-server.exe`, then `lucca-npu` (warm compile cache, self-test), `lucca-audio`, `lucca-ui`; health-checks each every 2 s over ZMQ `ping`; restarts a dead child with exponential backoff (1, 2, 4, 8 s; give up after 5 and enter DEGRADED mode with a spoken/visual notice). Ordered shutdown reverses this and flushes the SQLite write queue first. Details in spec 11.

## Consequences

- Real-time audio thread lives in a process with nothing else to contend with.
- Any single component can crash and be restarted without losing memory integrity (SQLite is owned by one process, written in transactions).
- Cost: process startup time (~3–6 s total warm), IPC schema discipline, shared-memory bookkeeping. All acceptable.
- Python 3.13 free-threading is **not** assumed; this design does not need it.

## Alternatives

| Option | Why not |
|---|---|
| Single process, threads + MMCSS | GIL; one crash kills all; unmeasurable jitter. |
| `asyncio` only | Doesn't address GIL for CPU-bound OpenVINO calls or Qt. |
| gRPC | Heavier than needed; ZMQ + Pydantic is sufficient and dependency-light. |
| Named pipes / raw sockets | Reimplementing ZMQ's framing and reconnect. |
| Run Kokoro inside `lucca-audio` | Couples the real-time thread to model inference; rejected. |
