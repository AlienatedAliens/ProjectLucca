# ADR-0009 — Audio path concurrency contract: per-resource ownership, lock discipline, and barge-in synchronisation

**Status:** Accepted 2026-09-19
**Supersedes:** F-ARCH-006 (undefined concurrency model across audio path)
**Related:** ADR-008 (process topology), Spec 01 §4-5, Spec 07 §2, Spec 10 §1-4

---

## 1. Context

The Lucca system topology spans multiple processes (`lucca-core`, `lucca-audio`, `lucca-npu`, `lucca-ui`, and `llama-server`) communicating via ZeroMQ IPC and two shared-memory PCM ring buffers (`cap_ring` and `play_ring`). Within each process, multiple concurrent execution contexts exist:
- `lucca-audio`: Sounddevice input callback, Sounddevice output callback, PTT poller thread, ZMQ event publisher.
- `lucca-core`: Ingest thread (`_handle_ingest_message`), Turn worker thread (`_run_turn` / `_run_text_turn`), TTS synthesis worker thread (`core-tts`), and ZMQ socket loops.

Prior to this contract (as documented in `F-ARCH-006`), resource ownership and concurrency rules were undefined:
1. Shared-ring headers were modified via raw read-modify-write without atomics or mutex synchronisation (`F-SENS-002`), causing lost updates between concurrent writers and flag setters.
2. `read_slice` did not validate if the requested capture window had already been overwritten (`F-SENS-003`).
3. `LLMClient` kept global mutable abort state shared across turn threads (`F-BRAIN-006`).
4. Barge-in never joined active turn threads (`F-CORE-011`), and worker `finally` blocks unconditionally forced state to `idle` (`F-CORE-014`).
5. Voice confirmation executed blocking ASR inside the ingest thread under `_turn_lock` (`F-CORE-015`).
6. Kokoro TTS synthesis blocked the LLM token streaming loop inline without a queue (`F-CORE-017`).

---

## 2. Resource Ownership & Concurrency Matrix

Every shared resource in the audio path has exactly one primary owner and strictly specified cross-thread/cross-process access rules:

| Resource | Primary Owner | Writers | Readers | Synchronisation & Invariants | Permitted Blocking |
|---|---|---|---|---|---|
| **`cap_ring` (Header)** | `lucca-audio` | `lucca-audio` (input callback) | `lucca-core`, `lucca-audio` | Mutex-guarded RMW. Monotonic sequence counter. | Non-blocking (try-lock or bounded mutex < 1 ms). |
| **`cap_ring` (Data)** | `lucca-audio` | `lucca-audio` (input callback) | `lucca-core` (turn worker) | Lock-free circular int16 buffer. `read_slice` checks `start_seq >= w_idx - capacity`. | Non-blocking. |
| **`play_ring` (Header)** | Shared (`core` / `audio`) | `lucca-core` (TTS worker), `lucca-audio` (flag setter) | `lucca-audio` (output callback), `lucca-core` | Mutex-guarded RMW. Flags (`ABORT`, `EOS`) updated atomically. | Mutex < 2 ms. |
| **`play_ring` (Data)** | `lucca-core` | `lucca-core` (TTS worker) | `lucca-audio` (output callback) | Lock-free circular int16 buffer. Drain on `FLAG_ABORT`. | Non-blocking. |
| **`ingest_sock` & `_turn_lock`** | `lucca-core` (ingest thread) | `lucca-core` (ingest loop) | `lucca-core` (ingest loop) | Ingest loop holds `_turn_lock` for routing/dispatch only. | Max 5 ms. Heavy I/O or model inference strictly forbidden. |
| **`active_turn_thread`** | `lucca-core` (`Orchestrator`) | Turn worker thread | `Orchestrator` lifecycle | Single active worker thread per turn. Previous worker joined on barge-in. | Bounded join: `timeout=0.5s`. |
| **`_tts_queue`** | `lucca-core` | Turn worker thread | TTS worker thread (`core-tts`) | `queue.Queue(maxsize=8)`. Drained on abort. | Bounded put (`timeout=2.0s`). Worker blocks on queue get. |
| **`LLMClient` Streams** | `lucca-brain` (`LLMClient`) | Turn worker threads | Turn worker threads | Per-stream registry `_StreamState` keyed by `trace_id` guarded by lock. | Thread-safe HTTP streaming. Targeted abort by `trace_id`. |
| **`StreamingChunker`** | Turn Worker | Current turn thread | Current turn thread | Per-turn instance created in `_run_turn`. No cross-turn sharing. | Single-threaded per instance. |

---

## 3. Invariants & Guarantees

### Invariant 1: Ingest Thread Non-Blocking Guarantee
The `lucca-core` ingest thread processes all ZMQ control and event messages. To guarantee responsive barge-in (Spec 10 budget ≤ 30 ms):
- The ingest thread MUST NEVER execute ASR transcription (`transcribe`), LLM inference, file I/O, or blocking network requests while holding `_turn_lock`.
- Voice confirmation audio is handed off via `_confirm_audio = payload` and `_confirm_event.set()`. The waiting turn worker executes ASR outside the ingest thread.

### Invariant 2: Shared Audio Ring Mutex Protection
All mutations to shared audio ring headers (`write_idx`, `read_idx`, `seq`, `flags`) in `SharedAudioRing` MUST be protected by a mutex lock. This guarantees:
- Concurrent `set_flag(FLAG_ABORT)` and `write()` operations never drop flags or overwrite indices.
- Reading `read_slice` verifies window freshness: if `start_seq < write_idx - capacity_samples`, the window is stale and returns empty audio / error flag rather than returning overwritten samples.

### Invariant 3: Per-Stream LLM Abort State
`LLMClient` must track stream states in a per-stream dictionary `self._streams: dict[str, _StreamState]` guarded by a lock:
- Calling `abort(trace_id)` aborts ONLY the stream matching `trace_id`.
- If `trace_id` is omitted, the most recently registered active stream is targeted.
- An abort on an old turn never cancels a newly started turn's HTTP connection or corrupts its error handling.

### Invariant 4: Barge-In Thread Join & State Discipline
When a barge-in event occurs (`_on_ptt_pressed` in `speaking`, `thinking`, or `confirm_wait`):
1. Instant abort flag: `play_ring.set_flag(FLAG_ABORT)`.
2. Cancel pending confirmation: `_pending_confirmation_active = False`, `_confirm_event.set()`.
3. Targeted LLM abort: `self.llm.abort(trace_id=self.active_trace.trace_id)`.
4. TTS queue drain: drain all pending items from `_tts_queue`.
5. Thread join: If `self.active_turn_thread` is alive and not current thread, join with `timeout=0.5`.
6. State ownership in worker `finally`: Worker `finally` blocks ONLY set state to `idle` if `self.active_trace is trace and not trace.interrupted`. A superseded worker never overwrites state.

### Invariant 5: Decoupled TTS Synthesis Queue
Speech LLM token streaming and Kokoro TTS synthesis are separated by a bounded queue (`_tts_queue: queue.Queue(maxsize=8)`):
- The turn worker streams tokens from the LLM, feeds the per-turn chunker, and enqueues chunks without waiting for Kokoro (~330 ms per clause).
- A dedicated background thread (`core-tts`) drains the queue and executes synthesis.
- On turn completion, an EOS sentinel (`None`) is enqueued and awaited.
- On barge-in, the queue is drained immediately so stale chunks are never synthesised.

---

## 4. Verification

This contract is verified across the following test suites:
- Static contract verification: `tests/test_static_gates.py` checks ADR-0009 invariants.
- Shared-memory race tests: `tests/test_ring_buffer.py::test_concurrent_flag_and_write_no_loss` and `test_read_slice_stale_window_detected`.
- LLM client concurrency: `tests/test_llm_client_race.py::test_abort_targets_only_matching_stream`.
- Turn loop concurrency & barge-in: `tests/test_turn_loop.py::test_barge_in_then_second_turn_is_clean` and `test_stale_worker_does_not_reset_state`.
- Ingest non-blocking confirmation: `tests/test_confirmation.py::test_voice_confirmation_does_not_block_ingest`.
- TTS non-blocking streaming: `tests/test_turn_loop.py::test_tts_does_not_block_token_consumption`.
