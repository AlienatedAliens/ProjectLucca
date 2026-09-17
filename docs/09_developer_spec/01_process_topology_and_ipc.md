# Spec 01 — Process Topology, IPC Contracts, Startup/Shutdown

Implements ADR-008. Audience: implementer (weaker model) — every value here is normative unless marked *estimate*.

## 1. Processes and entry points

| Process | Module | Entry | Depends on |
|---|---|---|---|
| supervisor + core | `lucca.main` → `lucca.core.app` | `python -m lucca.main` | — |
| audio | `lucca.senses.audio_proc` | spawned by supervisor (`multiprocessing.Process`, `spawn` context) | `sounddevice`, `numpy`, `onnxruntime` (Silero) |
| npu | `lucca.senses.npu_proc` | spawned | `openvino`, `openvino-genai`, `kokoro-onnx`/OpenVINO IR, `numpy` |
| ui | `lucca.ui.app` | spawned | `PyQt6`, `pyzmq` |
| llama-server | external exe | `subprocess.Popen` by supervisor | CUDA 12.8 runtime |

Package layout (create all `__init__.py`):

```
src/lucca/
  main.py                 supervisor entry
  core/   config.py schemas.py ipc_schemas.py exceptions.py app.py orchestrator.py risk_policy.py trace.py
  senses/ audio_proc.py ptt.py vad.py ring_buffer.py npu_proc.py asr.py tts.py embed.py
  brain/  llm_client.py prompt_builder.py chunker.py toolcall_demux.py reflection.py
  memory/ db.py migrations/ store.py retrieval.py gate.py signers.py extraction.py
  reasoning/ scheme/ (lexer.py parser.py eval.py prims.py) rules.py lifecycle.py regression.py
  router/ heuristic.py features.py classifier.py conformal.py labeling.py decisions.py
  sandbox/ client.py file_tool.py web_tool.py launcher.py container_spec.py
  ui/     app.py sprite.py states.py
```

## 2. Message envelope (all ZMQ traffic)

Wire: `uint32 big-endian length` + UTF-8 JSON. Max frame 1 MiB (reject larger; audio never travels here).

```python
class Envelope(BaseModel):
    v: Literal[1] = 1
    type: str                      # dotted, e.g. "turn.start"
    trace_id: str                  # ULID; one per user turn
    ts_ns: int                     # time.monotonic_ns() of sender
    src: Literal["core","audio","npu","ui"]
    payload: JsonValue             # validated by type-specific model after dispatch
```

Every `type` has exactly one Pydantic payload model in `lucca/core/ipc_schemas.py`. Unknown `type` → NACK + log; never crash.

## 3. Sockets

| Name | Pattern | Bind (core) | Connect | Purpose |
|---|---|---|---|---|
| `ctl` | ROUTER (core) / DEALER (peers) | `tcp://127.0.0.1:47001` | audio, npu, ui | request/response |
| `bus` | PUB (core) / SUB (peers) | `tcp://127.0.0.1:47002` | all | fan-out events |
| `ingest` | PULL (core) / PUSH (peers) | `tcp://127.0.0.1:47003` | audio, npu, ui | peer → core events |

Ports configurable; startup fails if bind fails (no fallback ports — avoids two instances).

Heartbeat: core sends `sys.ping` every 2 s on `ctl`; peer replies `sys.pong{rss_mb, queue_depth}` within 500 ms; 3 misses → peer considered dead → restart policy (§7).

## 4. Message catalogue (normative)

### audio → core (`ingest`)
| type | payload | when |
|---|---|---|
| `ptt.pressed` | `{t_ns}` | key down (OS timestamp) |
| `ptt.released` | `{t_ns, capture_seq_start, capture_seq_end, duration_ms, vad_speech_ms}` | key up; capture bounded in `cap_ring` |
| `audio.underrun` | `{count}` | playback underrun detected |
| `audio.first_sample_played` | `{trace_id, t_ns}` | first non-silent frame of a turn hit the device |
| `audio.rms` | `{t_ns, dbfs}` | every 20 ms while playing (also on `bus` for UI) |

### core → npu (`ctl`)
| type | payload | reply |
|---|---|---|
| `asr.transcribe` | `{trace_id, capture_seq_start, capture_seq_end}` | `asr.result{text, segments[{t0,t1,text,avg_logprob}], avg_logprob, model, audio_sha256, elapsed_ms}` |
| `tts.synthesize` | `{trace_id, chunk_id, text, voice, is_first}` | `tts.done{chunk_id, samples, elapsed_ms, device}`; PCM into `play_ring` |
| `tts.abort` | `{trace_id}` | `tts.aborted` |
| `embed.text` | `{texts[]}` | `embed.result{vectors[][], dim, elapsed_ms}` |
| `intent.encode` | `{text}` | `intent.result{vector[], elapsed_ms}` |
| `sys.selftest` | `{}` | `sys.selftest_result{asr_device, tts_device, embed_device, compile_cache_hit}` |

### core → audio (`ctl`)
| type | payload |
|---|---|
| `play.begin` | `{trace_id}` — arms `play_ring`, resets seq |
| `play.abort` | `{trace_id}` — zero output, drain ring |
| `capture.mark` | `{trace_id}` — snapshot ring indices |

### core → ui (`bus`)
| type | payload |
|---|---|
| `ui.state` | `{state: idle|listening|thinking|speaking|confirm|offline|degraded, detail}` |
| `ui.confirm` | `{prompt_text, action_summary, timeout_s}` |
| `ui.caption` | `{text}` (optional on-screen transcript) |

### ui → core (`ingest`)
| `ui.confirm_result` | `{accepted: bool, via: "voice"|"click"|"timeout"}` |

## 5. Shared-memory audio rings

```
name            rate   dtype  capacity   writer     reader
lucca_cap_ring  16000  int16  60 s       audio      npu (asr)      # audio writes continuously while PTT held
lucca_play_ring 24000  int16  30 s       npu (tts)  audio
```

Header (64 bytes): `magic u32 | version u16 | rate u32 | write_idx u64 | read_idx u64 | seq u64 | flags u32 | pad`. Flags: `ABORT=1`, `EOS=2`. Indices are monotonically increasing sample counts; position = idx mod capacity. Writers update `write_idx` **after** copying samples (release semantics via `struct.pack_into` + `threading`/`multiprocessing` `Semaphore` post). Readers never block in the audio callback; they read what is available and fill the remainder with zeros (counted as underrun only if a turn is active and `EOS` not set).

`capture_seq_start/end` in `ptt.released` are absolute sample indices so ASR reads exactly the PTT window plus 200 ms pre-roll.

## 6. Turn state machine (`lucca-core`)

```
IDLE ─ptt.pressed→ LISTENING ─ptt.released→ DISPATCH
DISPATCH: in parallel  (a) asr.transcribe          (b) llm.request(audio)   [mode=audio]
          sequential   (a) asr.transcribe → router → (b) llm.request(text)  [mode=transcript]
DISPATCH ─rule fires (plan) & router=RULE→ EXECUTE_PLAN (abort LLM)   ─first token→ SPEAKING
SPEAKING ─chunk→ tts.synthesize …  ─EOS & ring drained→ POSTTURN
POSTTURN: memory commits, decision log, labels for previous turn, ui.state idle → IDLE
Any state ─ptt.pressed→ BARGE_IN: play.abort, tts.abort, llm.abort, mark turn interrupted → LISTENING
Any state ─peer dead→ DEGRADED (speak notice once) ; recover on pong
```

Confirm flow: `EXECUTE_PLAN` or LLM tool call with risk WRITE/LAUNCH → `CONFIRM_WAIT`: `ui.confirm` + TTS prompt; next PTT utterance transcribed; regex `^(yes|yeah|do it|go ahead)` → proceed, `^(no|cancel|stop)` → cancel, else cancel + "cancelled"; timeout 15 s → cancel.

## 7. Startup / shutdown (supervisor)

Startup order and gates (each step logs `boot.step{name, ms, ok}`):

1. Load config (`config\lucca.toml`, `.env`), validate; fail-closed on default master key unless `LUCCA_ENV=dev`.
2. Environment checks (`scripts/verify_environment.py` logic in-process): GPU mode baseline VRAM < 300 MB; NPU visible to OpenVINO; `sqlite3.enable_load_extension` works; Docker CE reachable in WSL (`wsl -d Ubuntu -- docker info`); `LUCCA_HOME` layout exists (create missing dirs).
3. Open SQLite, run migrations, `PRAGMA integrity_check` (quick) → fail if not `ok`.
4. Start `llama-server.exe`; poll `GET /health` ≤ 60 s.
5. Spawn `lucca-npu`; wait `sys.selftest_result` ≤ 90 s (cold compile allowed; cache warms).
6. Spawn `lucca-audio`; wait `sys.pong`; open rings.
7. Spawn `lucca-ui`; `ui.state idle`.
8. Apply WSL egress rules (`wsl -d Ubuntu -- sudo /opt/lucca/lucca-egress.sh`), ensure `lucca-net` exists; pull/build sandbox images if missing (not on critical path — background).
9. Speak "ready" (or "ready, transcript mode" if cascade) — ≤ 25 s total warm target, ≤ 120 s cold.

Restart policy: child exit → restart after 1, 2, 4, 8, 16 s; after 5 failures in 10 min → DEGRADED, no further restarts until user action. `llama-server` death → DEGRADED immediately (speak "my brain is offline"); memory and rules remain usable for READ plans.

Shutdown (Ctrl-C, tray Quit, `WM_CLOSE`): `ui.state offline` → `play.abort` → stop accepting turns → flush SQLite write queue (≤ 5 s) → `VACUUM INTO` if last backup > 24 h → terminate children (SIGTERM, 3 s, then kill) → terminate `llama-server`.

## 8. Failure modes table

| ID | Failure | Detection | Response | Test |
|---|---|---|---|---|
| FM-01 | `lucca-npu` crash mid-TTS | missed pongs / socket close | `play.abort`; restart; replay pending chunk | T-IPC-04 |
| FM-02 | playback underrun | `audio.underrun` | log; if > 3 per turn → increase jitter buffer 20 ms (max 120 ms) | T-AUD-06 |
| FM-03 | `llama-server` hang | request > 10 s no first token | abort slot; retry once; then DEGRADED | T-LLM-09 |
| FM-04 | SQLite locked | `OperationalError` | retry 3× with backoff; else raise, turn fails loudly | T-MEM-11 |
| FM-05 | ring overflow (PTT > 60 s) | write_idx − read_idx > cap | auto-release PTT at 29.5 s prevents; assert | T-AUD-03 |
| FM-06 | UI crash | missed pongs | restart; voice loop unaffected | T-IPC-05 |
| FM-07 | two instances | bind fails | exit with message | T-BOOT-02 |
