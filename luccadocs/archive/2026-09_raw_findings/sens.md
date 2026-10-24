# Findings — SENS (`src/lucca/senses/**`)

**Subtask:** S2g · **Method:** static line-by-line + S1 dynamic evidence · **Baseline:** HEAD `ed14f6b` + working tree per `03_BASELINE.md`, delta in [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) (senses modules: **unchanged since S0**) · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; every finding cites `file:line` in the current tree or an artefact under `luccadocs/audit/evidence/`. Cross-area findings cross-referenced by ID.

**Severity totals: S0 = 0 · S1 = 2 · S2 = 6 · S3 = 7 · S4 = 0 · total = 15.**

---

## 1. Module map

Coverage from `luccadocs/audit/evidence/S1_14_coverage.txt` rows 64–72. LOC = non-blank lines (S0 metric, verified unchanged by `03b_BASELINE_DELTA.md`).

| File | LOC | Public symbols | Responsibilities (as-built) | Live callers in product path? | Outbound dependencies | Cov % | Tests |
|---|---:|---|---|---|---|---:|---|
| `senses/asr.py` | 99 | `ASRWorker` (`transcribe`) | faster-whisper transcription — **hard-coded `distil-small.en`, CPU int8, English-only** (F-SENS-001) | **yes** — `orchestrator.py:97,355` (in-process, F-CORE-002) and `npu_proc.py:49,120` | `faster_whisper`, `numpy` | 82 % | none direct (FakeASR used in turn tests) |
| `senses/tts.py` | 177 | `VOICE_RECIPES`, `enhance_anime_expressive_punctuation`, `get_available_voices`, `parse_voice_blend`, `TTSWorker` (`synthesize`) | Kokoro ONNX synthesis, voice blends, direct playback-ring writes; **silent af_sarah fallback** (F-SENS-004) | **yes** — `orchestrator.py:363` (in-process) and `npu_proc.py:50,132`; UI preview (`settings_dialog.py:72-77`) | `kokoro_onnx`, `numpy`, `ring_buffer` | **32 %** | none direct (FakeTTS used) |
| `senses/vad.py` | 51 | `EnergyVAD` (`process`) | Frame-RMS energy VAD, fixed −42 dBFS threshold, no hysteresis | **yes** — `audio_proc.py:64,109` | `numpy` | **0 %** | none |
| `senses/ptt.py` | 119 | `PTTListener` (`start`, `stop`, `set_key`, `is_key_down`) | 5 ms `GetAsyncKeyState` polling, debounce 150 ms, 29.5 s auto-release | **yes** — `audio_proc.py:77,277` | `ctypes` (Windows) | **0 %** | none |
| `senses/ring_buffer.py` | 220 | `SharedAudioRing`, `get_capture_ring`, `get_playback_ring`, `FLAG_ABORT/EOS` | Shared-memory PCM rings (16 kHz/60 s cap, 24 kHz/30 s play); **non-atomic header RMW** (F-SENS-002) | **yes** — audio/npu/core processes | `multiprocessing.shared_memory`, `numpy` | 85 % | `tests/test_ring_buffer.py` |
| `senses/embed.py` | 129 | `EmbedWorker` (`embed_text`), `LocalEmbeddingPort` | MiniLM OpenVINO on NPU (reshape 128) / CPU fallback; **zero-vector fallback** (F-SENS-011) | **yes** — `npu_proc.py:51,160`; `LocalEmbeddingPort` for memory (unwired) | `openvino`, `tokenizers` | 73 % | none direct |
| `senses/dsp_chain.py` | 212 | `AnimeDSPConfig`, `AnimeVoiceDSP`, filter helpers | Anime voice DSP chain (highpass, presence EQ, shelf, comp, exciter, limiter) — **preview-only, never applied in the TTS path** (F-SENS-015) | **UI only** — `settings_dialog.py:71,1750` | `scipy.signal` | 93 % | `tests/test_dsp_chain.py` |
| `senses/audio_proc.py` | 326 | `AudioProcess` (`start`, `stop`), `main` | `lucca-audio` process: sounddevice capture/playback callbacks, PTT, VAD, ZMQ ingest/ctl/bus, jitter adaptation | **yes** — `main.py:16,85` | `sounddevice`, `zmq`, `ptt`, `vad`, `ring_buffer` | **0 %** | none |
| `senses/npu_proc.py` | 174 | `NPUProcess`, `main` | `lucca-npu` process: ctl/bus loop serving asr/tts/embed requests; **loads all three models at construction** (answers core Q-03) | **yes** — `main.py:17,79` | `zmq`, `asr`, `tts`, `embed` | **0 %** | none |

**Wiring verdict:** everything in SENS is live — but the *role assignment* is the F-CORE-002 drift: ASR/TTS/embed run **both** in the core process (orchestrator constructs its own workers) and in the `lucca-npu` child (which loads the same models again at construction, `npu_proc.py:49-51` — this answers core Q-03: the ~865 MB child in `S1_25` is the NPU process double-loading models). The ctl-protocol path (`asr.transcribe`/`tts.synthesize` over ZMQ, `npu_proc.py:116-145`) is fully implemented and **never used** — the orchestrator calls its in-process workers directly.

## 2. As-built behaviour notes

- **Capture path:** sounddevice 16 kHz int16 callback → `cap_ring.write` (20 ms blocks) → PTT press snapshots `write_idx − 200 ms` pre-roll (`audio_proc.py:84-101`); release computes VAD over the slice and publishes `ptt.released` with absolute seq bounds.
- **Playback path:** TTS writes 24 kHz int16 directly into `play_ring`; the output callback gates on a jitter buffer (config `audio.jitter_ms`), publishes `audio.rms` for lip-flap, detects first non-silent sample for `t_first_sample`, adapts jitter +20 ms per 3 underruns (`:211-224`), and completes on drain+EOS.
- **Barge-in:** PTT press while playing → `play_ring.set_flag(FLAG_ABORT)` + bus/ctl `play.abort`; TTS checks the flag before and after synthesis; `read()` drains on ABORT.
- **Health protocol:** `sys.ping` → `sys.pong` with **hard-coded** `rss_mb` (50.0 audio, 250.0 npu — F-SENS-005) and `compile_cache_hit=True` (`npu_proc.py:111`).

---

## 3. Findings

Ordered by severity, then by ID. Every finding re-reviewed per Charter §3.5 (log in §7); `Status: OPEN`.

### F-SENS-001 — ASR ignores the configured model and device ladder entirely: `distil-small.en` CPU int8, English-only, is hard-coded

| Field | Value |
|---|---|
| **ID** | F-SENS-001 |
| **Title** | ASR ignores the configured model and device ladder entirely: `distil-small.en` CPU int8, English-only, is hard-coded |
| **Severity** | S1 — High |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/senses/asr.py:42-48,88`; `src/lucca/core/config.py:49-53`; `luccadocs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/07_audio_pipeline_and_barge_in.md` §4 |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/asr.py:42-48`
```python
            # Use distil-small.en int8 for fast CPU transcription
            self.model = faster_whisper.WhisperModel(
                "distil-small.en",
                device="cpu",
                compute_type="int8",
                cpu_threads=6,
            )
```
`src/lucca/senses/asr.py:88`
```python
            language="en",
```
(`ASRSettings` defaults `model="asr/whisper-large-v3-turbo-ov"` with a `device_ladder` (`config.py:49-53`); the on-disk model dir `models\asr\whisper-large-v3-turbo-ov\` exists (`S1_07c`); `asr.py` reads neither — `self.config` is loaded at `:32` and never consulted for model/device.)

**What is wrong / assumed / missing**

The shipped ASR is a different, smaller, **English-only** model on a different device than the one configured and specified: `whisper-large-v3-turbo` via OpenVINO with an NPU→GPU→CPU device ladder. Consequences: (a) the entire `device_ladder` mechanism is dead; (b) non-English speech cannot be transcribed at all (`language="en"` forced); (c) the `S1_35` NPU benchmark (which loaded the OV model directly and measured RTF 1.09 on GPU) measured a model the product never uses; (d) the accuracy/latency budgets in Spec 07 were written against large-v3-turbo. Which side is right: the config/spec — a hard-coded model defeats the configuration system and the Phase-1 sign-off basis.

**Why it matters**

Main-path transcription quality/language capability silently different from everything the documentation, benchmarks, and configuration claim; also the root of the low-confidence gating gap (F-SENS-016).

**Questions this raises**

1. Was `distil-small.en` a deliberate Phase-1 CPU speed choice? No decisions-log entry exists.

**Proposed remediation**

1. In `src/lucca/senses/asr.py`, `_init_model()`: honour `self.config.asr.model` (OpenVINO IR path → `openvino` Core pipeline; `.gguf`/HF name → faster-whisper) and walk `self.config.asr.device_ladder` with a health probe per device. Before: hard-coded distil-small.en/CPU. After: configured model on the first healthy ladder device.
2. Remove the hard-coded `language="en"` (derive from config or auto-detect).
3. Add `tests/test_senses.py::test_asr_honours_config`: patch config model to a fixture whisper-tiny; assert the worker reports the configured backend string.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** backend reflects config, not the hard-code
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_asr_honours_config -q`

**Cross-references:** F-CORE-002, F-SENS-016, F-CORE-049

---

### F-SENS-002 — Shared-ring headers are read-modify-written with no atomics: concurrent writers/flag-setters lose updates

| Field | Value |
|---|---|
| **ID** | F-SENS-002 |
| **Title** | Shared-ring headers are read-modify-written with no atomics: concurrent writers/flag-setters lose updates |
| **Severity** | S1 — High |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/senses/ring_buffer.py:81-132,155-177,214-216` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/ring_buffer.py:123-129`
```python
    def set_flag(self, flag: int) -> None:
        _, _, _, w, r, seq, f = self._read_header()
        self._write_header(w, r, seq, f | flag)
```
(identical read-modify-write pattern in `clear_flag`, `write` (`:155,176`), and `read` (`:186,215`); the `:175` comment claims "release semantics" but there are no atomics, barriers, or interlocked operations — plain `struct.pack_into` over shared memory.)

**What is wrong / assumed / missing**

The header is shared between up to three processes (core, audio, npu) and multiple threads each (sounddevice callbacks, TTS thread, ctl loop), and every operation rewrites the **entire** header from a stale snapshot. Concrete interleavings: (a) TTS thread's `write` (advances `w_idx`) racing the audio process's `set_flag(FLAG_ABORT)` (writes back the *old* `w_idx`) → the just-written audio is orphaned or duplicated; (b) two flag setters racing → one flag lost (barge-in ABORT swallowed → playback continues after barge-in); (c) `read` advancing `r_idx` racing `write` → lost-update on either pointer. Which side is right: correctness — "lock-free" requires atomics (e.g. `InterlockedCompareExchange` via ctypes, or a small mutex in a control header), not RMW over shared memory.

**Why it matters**

The rings are the only IPC for the real-time audio path; a lost ABORT flag is a barge-in failure (the Spec 10 ≤ 30 ms gate) and a lost `w_idx` is audible corruption — both intermittent and unreproducible in the 0 %-coverage audio process.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/ring_buffer.py`: protect header mutations with a named Windows mutex (`ctypes.windll.kernel32.CreateMutexW` around RMW sections) **or** split the header into per-field slots written with `InterlockedExchange64` via `ctypes`; minimal sound version first: one process-wide named mutex per ring guarding `set_flag`/`clear_flag`/`write`/`read` header updates (data area stays lock-free).
2. Add `tests/test_ring_buffer.py::test_concurrent_flag_and_write_no_loss`: two threads hammering `write` + `set_flag(FLAG_ABORT)` for 10 k iterations; assert final `w_idx` equals total written and the ABORT flag is set.

**Verification test**

- **Tier:** T1
- **Input:** the race test above
- **Expected output:** no lost updates under concurrency
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ring_buffer.py::test_concurrent_flag_and_write_no_loss -q`

**Cross-references:** F-CORE-011, F-SENS-003

---

### F-SENS-003 — `read_slice` does not validate that the requested window is still inside the ring: stale PTT windows return overwritten garbage silently

| Field | Value |
|---|---|
| **ID** | F-SENS-003 |
| **Title** | `read_slice` does not validate that the requested window is still inside the ring: stale PTT windows return overwritten garbage silently |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/senses/ring_buffer.py:218-242` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/ring_buffer.py:229-240`
```python
        start_pos = start_seq % self.capacity_samples
        first_part_samples = min(n_samples, self.capacity_samples - start_pos)
        second_part_samples = n_samples - first_part_samples
```
(no check that `start_seq ≥ w_idx − capacity_samples`; the modulo silently maps an overwritten window onto current buffer contents.)

**What is wrong / assumed / missing**

The capture ring holds 60 s. If the audio process stalls, or a PTT window's start falls more than 60 s behind `write_idx` (auto-release caps at 29.5 s, but pre-roll + scheduling delays under load can exceed the boundary after heavy playback writes to the *same* shared-memory module — no, separate rings; the realistic trigger is a stalled/suspended audio process), `read_slice` returns bytes that have been overwritten by newer audio — and the ASR transcribes whatever that garbage decodes to, which then becomes the turn's `USER_EXPLICIT` text. Expected: `read_slice` returns an empty (or raises) when `start_seq < w_idx − capacity_samples`, flagged distinctly.

**Why it matters**

Silent garbage-in to the transcription path with no signal path to the user — the worst failure shape for a voice product (confidently wrong transcript). Also: the header `seq` field (`:19,88-91`) is never incremented anywhere — dead.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/ring_buffer.py`, `read_slice()`: compute `oldest = w_idx - capacity_samples`; if `start_seq < oldest`, return `np.zeros(0)` **and** expose a validity flag (or raise `SchemeError`-style `RingWindowStale`); have `audio_proc._on_ptt_released` report `vad_speech_ms=0` on stale windows so the orchestrator's silence guard handles it.
2. Add `tests/test_ring_buffer.py::test_read_slice_stale_window_detected`: write capacity+1000 samples; `read_slice(w_idx - capacity - 500, w_idx - capacity - 100)` → empty result / stale flag.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** stale window detected, no garbage returned
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ring_buffer.py::test_read_slice_stale_window_detected -q`

**Cross-references:** F-SENS-002, F-CORE-003 (silence guard)

---

### F-SENS-004 — TTS synthesis failures silently fall back to the `af_sarah` voice

| Field | Value |
|---|---|
| **ID** | F-SENS-004 |
| **Title** | TTS synthesis failures silently fall back to the `af_sarah` voice |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/senses/tts.py:191-196` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/tts.py:191-196`
```python
        try:
            samples_f32, sr = self.engine.create(clean_text, voice=resolved_voice, speed=s)
        except Exception:  # noqa: BLE001
            # Fallback to default voice if custom/blended voice encounters issues
            fallback_voice = self.resolve_voice_style("af_sarah")
            samples_f32, sr = self.engine.create(clean_text, voice=fallback_voice, speed=s)
```

**What is wrong / assumed / missing**

Any exception during synthesis with the configured/blended voice (e.g. a blend recipe referencing a missing vector, or a Kokoro internal error) is swallowed and the chunk is re-synthesised with `af_sarah` — the companion's voice **silently changes mid-reply**, with no log, no bus event, and no trace marker. If the fallback also raises, the exception escapes to the turn thread (F-CORE-017's blocking path). Expected: log the fallback (`tts_voice_fallback`) with the original error, and surface a `voice_fallback` flag in `TTSDonePayload` so the UI/HUD can show the degraded state.

**Why it matters**

The voice is the persona (D-AUD-03: `genki_heroine` blend is canonical); a silent swap to a different voice is a user-visible correctness failure that looks like a glitch and is undiagnosable after the fact.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/tts.py:191-196`: `logger.warning("tts_voice_fallback", voice=raw_spec, error=…)` before the fallback attempt; add `voice_fallback: bool = False` to `TTSDonePayload` and set it on the fallback path.
2. Add `tests/test_senses.py::test_broken_voice_falls_back_with_signal`: stub engine whose `create` raises for the configured voice; assert fallback used, warning logged, and `voice_fallback=True` in the payload.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** fallback + warning + payload flag
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_broken_voice_falls_back_with_signal -q`

**Cross-references:** F-CORE-017, D-AUD-03

---

### F-SENS-005 — The health protocol reports hard-coded fake `rss_mb` values

| Field | Value |
|---|---|
| **ID** | F-SENS-005 |
| **Title** | The health protocol reports hard-coded fake `rss_mb` values |
| **Severity** | S2 — Medium |
| **Category** | UX |
| **Location** | `src/lucca/senses/audio_proc.py:301-309`; `src/lucca/senses/npu_proc.py:91-99` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/npu_proc.py:97`
```python
                payload=SysPongPayload(rss_mb=250.0, queue_depth=0).model_dump(),
```
(`audio_proc.py:307`: `rss_mb=50.0` — both constants, never measured; `psutil` is already a dependency in the package.)

**What is wrong / assumed / missing**

The heartbeat/health channel — the mechanism Spec 01 §3 and ADR-008 rely on for liveness and resource monitoring — reports invented memory numbers. Any consumer (the missing supervisor heartbeat, F-CORE-005; a future HUD) would display fabricated RSS. `queue_depth=0` is likewise constant.

**Why it matters**

Honesty of recorded metrics (the F-ARCH family); and the heartbeat is the natural place to detect the runaway RSS the 16 GB host cares about (core A-01).

**Questions this raises**

1. None.

**Proposed remediation**

1. In both `sys.ping` handlers: `rss_mb=round(psutil.Process().memory_info().rss / 1048576, 1)` and a real queue depth (len of the last ingest backlog or 0 with a `not_tracked` note). Before: constants. After: measured.
2. Add `tests/test_senses.py::test_pong_rss_is_measured`: call the handler; assert `rss_mb > 0` and equals the process RSS within 1 MB.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** measured RSS
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_pong_rss_is_measured -q`

**Cross-references:** F-CORE-005, F-CORE-009, F-SBX-011

---

### F-SENS-006 — `ui.talk_release` fabricates a 1 s duration when the payload omits it

| Field | Value |
|---|---|
| **ID** | F-SENS-006 |
| **Title** | `ui.talk_release` fabricates a 1 s duration when the payload omits it |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/senses/audio_proc.py:339-345` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/audio_proc.py:341-345`
```python
                    elif env.type == "ui.talk_release":
                        dur_ms = 1000.0
                        if isinstance(env.payload, dict) and "duration_ms" in env.payload:
                            dur_ms = float(str(env.payload["duration_ms"]))
                        self._on_ptt_released(env.ts_ns, dur_ms)
```

**What is wrong / assumed / missing**

The quick-chat "talk" button's release synthesises a `ptt.released` with `duration_ms=1000.0` when the payload lacks the field — downstream this feeds `PTTReleasedPayload.duration_ms`, the label engines (`EARLY_BARGEIN ≤ 1500 ms` thresholds) and the trace. A real press-and-hold of 4 s released via the UI path with a missing field is recorded as 1 s; the VAD slice is computed from the *real* ring window, so duration and audio disagree. Expected: compute the duration from `env.ts_ns − last talk_press ts_ns` (both available) or make the field required in the payload schema.

**Why it matters**

Fabricated timing on a user-facing input path feeding labelling thresholds — same honesty family; also makes UI-originated turns indistinguishable from 1 s voice presses in telemetry.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/audio_proc.py`: track `self._talk_press_ts_ns` on `ui.talk_press`; on release compute `dur_ms = (env.ts_ns − self._talk_press_ts_ns) / 1e6`; only fall back to 1000.0 when the press timestamp is missing, and log `talk_duration_fabricated` when it does.
2. Add `tests/test_senses.py::test_talk_release_duration_measured`: press/release 2 s apart → `PTTReleasedPayload.duration_ms ≈ 2000`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** measured duration
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_talk_release_duration_measured -q`

**Cross-references:** F-ROUT-006, F-CORE-009

---

### F-SENS-007 — `enhance_anime_expressive_punctuation` mutates LLM output before TTS, desynchronising speech from captions/history

| Field | Value |
|---|---|
| **ID** | F-SENS-007 |
| **Title** | `enhance_anime_expressive_punctuation` mutates LLM output before TTS, desynchronising speech from captions/history |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/senses/tts.py:33-58` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/tts.py:46-57`
```python
    interjections = [
        ("Oh wow.", "Oh wow!"),
        ("No way.", "No way!"),
        ...
    ]
    for orig, repl in interjections:
        result = result.replace(orig, repl)

    result = re.sub(r"\b(wait|well|listen),\s*", r"\1... ", result, flags=re.IGNORECASE)
```

**What is wrong / assumed / missing**

The function rewrites the assistant's words ("Yes." → "Yes!", "wait," → "wait... ") before synthesis. Consumers of the *unmodified* text — the speech-bubble caption (`orchestrator.py:420-421`), the history record (`:450-454`), and `spoken_prefix` — diverge from what is actually spoken whenever a pattern matches. Also its guard (`:42`: skip if `http://`/`https://` present) is confused about ordering: the chunker has already replaced URLs with "a link" before TTS sees the text, so the guard never triggers for URL-bearing replies. The function is currently called only from the UI test-preview (`settings_dialog.py:894`), not the TTS path — but it is exported as the production enhancement hook and documented as such.

**Why it matters**

Text-fidelity boundary: spoken audio must match the caption and the recorded history (provenance and debugging both rely on it); canned rewrites make the divergence unreconstructable.

**Questions this raises**

1. None.

**Proposed remediation**

1. Decide the enhancement point (decision recorded: apply inside the orchestrator *before* both caption and TTS, so all three consumers see the same text — or delete the function). Until then, in `src/lucca/senses/tts.py`: mark the function clearly preview-only in its docstring.
2. Add `tests/test_senses.py::test_enhancement_consumers_agree` (after the wiring decision): caption text == synthesised text for a sample containing "Yes."

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** identical strings across consumers
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_enhancement_consumers_agree -q`

**Cross-references:** F-CORE-046, F-BRAIN-021

---

### F-SENS-008 — TTS/embed hard-code `C:\ProjectLucca\models\tts\…` model paths

| Field | Value |
|---|---|
| **ID** | F-SENS-008 |
| **Title** | TTS/embed hard-code `C:\ProjectLucca\models\tts\…` model paths |
| **Severity** | S3 — Low |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/senses/tts.py:63,135-136`; `src/lucca/senses/embed.py:26` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/tts.py:135-136`
```python
        model_path = Path(r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx")
        voices_path = Path(r"C:\ProjectLucca\models\tts\voices-v1.0.bin")
```
(`embed.py:26`: `MODEL_DIR = Path(r"C:\ProjectLucca\models\embed\all-MiniLM-L6-v2")`; `get_available_voices` at `tts.py:63` repeats the voices path. `config.paths.models` and `resolve_path` exist and are ignored — F-CORE-030 family, SENS instances.)

**What is wrong / assumed / missing**

Three more hard-coded production roots bypass `LUCCA_HOME`; the TTSWorker silently disables itself (`engine = None` → zero-sample audio, core.md §3.3 row 6) when the hard-coded path is absent — on any non-default install the voice dies without a word.

**Why it matters**

Same portability/dev-prod conflation as F-CORE-030/F-MEM-013/F-SBX-012; and the failure mode (silent mute) is the harshest possible.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/tts.py:135-136` and `embed.py:26`: resolve via `get_config().resolve_path("models/tts/kokoro-v1.0.onnx")` etc.; when missing, `logger.error("tts_models_missing", paths=…)` once so the mute is diagnosable.
2. Add `tests/test_senses.py::test_tts_paths_follow_lucca_home` (T1, tmp-home): worker resolves models under the configured home.

**Verification test**

- **Tier:** T1
- **Input:** the tmp-home test above
- **Expected output:** paths resolved from config
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_tts_paths_follow_lucca_home -q`

**Cross-references:** F-CORE-030, F-MEM-013, F-SBX-012

---

### F-SENS-009 — `set_key("all")` binds two keys while the constructor's `"all"` binds six

| Field | Value |
|---|---|
| **ID** | F-SENS-009 |
| **Title** | `set_key("all")` binds two keys while the constructor's `"all"` binds six |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/senses/ptt.py:38,83-84` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/ptt.py:83-84`
```python
        elif k in ("all", "both", "default"):
            self.target_vks = [VK_RCONTROL, VK_RMENU]
```
(constructor `KEY_MAP["all"]` at `:38` = `[VK_RMENU, VK_MENU, VK_RCONTROL, VK_CONTROL, VK_RSHIFT, VK_SHIFT]` — note it also includes the *generic* `VK_MENU`/`VK_CONTROL`/`VK_SHIFT`, which `GetAsyncKeyState` reports for **left** variants too, so the constructor's "all" actually accepts Left-Alt/Left-Ctrl/Left-Shift against its documented "Right" semantics.)

**What is wrong / assumed / missing**

Two inconsistent definitions of "all": runtime rebind → 2 keys; construction → 6 keys including left-side and generic modifiers (which fire for ordinary typing shortcuts like Ctrl+C!). A user holding Ctrl+C to copy while Lucca listens would trigger a PTT press under the constructor mapping. Expected: one definition; and generic VKs (`VK_CONTROL`, `VK_MENU`, `VK_SHIFT`) should be dropped in favour of the right-side explicit codes per D-10/commit `22ac549`.

**Why it matters**

PTT mis-fires from ordinary editing shortcuts; the "Right-side only" promise of the default is not what the code does.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/ptt.py`: make `KEY_MAP["all"]` = `[VK_RMENU, VK_RCONTROL, VK_RSHIFT]` (right-side only) and `set_key("all"/"default")` use `KEY_MAP["all"]`. Before: divergent, includes generic/left codes. After: consistent right-side set.
2. Add `tests/test_senses.py::test_ptt_all_mapping_consistent`: constructor `key_name="all"` and `set_key("all")` produce identical `target_vks`; assert `VK_CONTROL not in target_vks`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** identical, right-side-only mappings
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_ptt_all_mapping_consistent -q`

**Cross-references:** F-CORE-049 (key-default drift)

---

### F-SENS-010 — Underrun-adaptive jitter grows monotonically and never resets between turns

| Field | Value |
|---|---|
| **ID** | F-SENS-010 |
| **Title** | Underrun-adaptive jitter grows monotonically and never resets between turns |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/senses/audio_proc.py:211-216` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/audio_proc.py:214-216`
```python
            if self.underrun_count % 3 == 0:
                self.jitter_ms = min(120, self.jitter_ms + 20)
                self.jitter_samples = (self.config.audio.playback_rate * self.jitter_ms) // 1000
```
(`jitter_ms` starts at `config.audio.jitter_ms`; `first_sample_emitted` resets per turn at `:312,328` but `jitter_ms`/`underrun_count` never do.)

**What is wrong / assumed / missing**

The adaptive jitter buffer is a ratchet: after a few underruns it sticks at up to 120 ms for the process lifetime, adding that latency to **every** subsequent first-sample (the Spec 10 S5 budget is 40 ms / 80 p95 — a ratcheted 120 ms jitter fails the canonical gate permanently from one bad patch). Expected: reset `jitter_ms` to config on `play.begin` (keep a learned average separately if desired).

**Why it matters**

One transient stall converts into a permanent latency regression that no trace field records (`underruns` trace counter is never populated either — F-CORE-009) — an invisible budget violation.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/audio_proc.py`, the `play.begin` handlers (`:310-314,326-330`): reset `self.jitter_ms = self.config.audio.jitter_ms; self.jitter_samples = …` alongside `first_sample_emitted = False`. Before: monotonic ratchet. After: per-turn reset.
2. Add `tests/test_senses.py::test_jitter_resets_per_turn`: force underruns to 120 ms; deliver `play.begin`; assert jitter back at config.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** jitter reset to configured value
- **Threshold:** jitter ≤ config after play.begin
- **Command:** `uv run pytest tests/test_senses.py::test_jitter_resets_per_turn -q`

**Cross-references:** F-CORE-009, F-CORE-017

---

### F-SENS-011 — `embed_text` returns all-zero vectors when the model or tokenizer is missing, silently poisoning retrieval

| Field | Value |
|---|---|
| **ID** | F-SENS-011 |
| **Title** | `embed_text` returns all-zero vectors when the model or tokenizer is missing, silently poisoning retrieval |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/senses/embed.py:81-84,114-121` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/embed.py:83-84`
```python
        if not texts or self.compiled is None:
            return [[0.0] * 384 for _ in texts], 384, 0.0
```
(also the no-tokenizer branch at `:114-121` feeds `input_ids=ones` — deterministic garbage embeddings; callers: `npu_proc.py:160`, `LocalEmbeddingPort` → `MemoryStore.commit`'s embedding slot, F-MEM-008's backfill queue would happily store them.)

**What is wrong / assumed / missing**

Absent model/tokenizer produces well-formed but meaningless vectors with `ok`-shaped results — cosine similarity against them is degenerate, so once memory retrieval is wired, every commit in a broken-embed environment is dense-search-poisoned with zero signal and no error anywhere. Expected: raise (or return a typed failure) when the model is unavailable; zero-vectors must never enter storage.

**Why it matters**

Silent data poisoning of the exact pipeline (F-CORE-003 wiring) whose retrieval quality the Phase-3 sign-off measured — with a failure mode invisible until search quality collapses.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/embed.py:81-84`: raise `EmbedUnavailable` (new typed error) when `compiled is None`/tokenizer missing; let `MemoryStore.commit`'s existing backfill path (F-MEM-008) handle the failure honestly.
2. Add `tests/test_senses.py::test_embed_missing_model_raises`: worker without model dir → raises; zero-vector path gone.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** typed error, no zero vectors
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_embed_missing_model_raises -q`

**Cross-references:** F-MEM-008, F-CORE-003

---

### F-SENS-012 — `lucca-npu` loads ASR+TTS+Embed models at construction and offers a ZMQ path the orchestrator never uses (answers core Q-03)

| Field | Value |
|---|---|
| **ID** | F-SENS-012 |
| **Title** | `lucca-npu` loads ASR+TTS+Embed models at construction and offers a ZMQ path the orchestrator never uses (answers core Q-03) |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/senses/npu_proc.py:45-51,116-186`; `src/lucca/core/orchestrator.py:87-97`; `luccadocs/audit/findings/core.md` Q-03 |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/npu_proc.py:49-51`
```python
        self.asr = ASRWorker()
        self.tts = TTSWorker(self.play_ring)
        self.embed = EmbedWorker()
```
(the full ZMQ request handlers for `asr.transcribe`/`tts.synthesize`/`embed.text` at `:116-186` are complete and correct — and unreachable, because the orchestrator constructs its own in-process workers instead, F-CORE-002.)

**What is wrong / assumed / missing**

This finding **answers core Q-03** from code: yes — `NPUProcess` loads Whisper (distil), Kokoro, and MiniLM at construction, which is the ~865 MB child in `S1_25`; the models are loaded twice on the host. The ZMQ service path is a complete, unused duplicate of the in-process path. `NPUProcess` also has no `stop()` — the poll loop exits only when the process is killed (main.py `terminate()`), so `ctx.term()` never runs (ZMQ linger warnings on shutdown).

**Why it matters**

Double model loading is the concrete RAM cost behind F-CORE-002; the unused-but-complete ZMQ path is either the fix (route core → npu over ctl) or dead weight to delete — the architecture decision is unrecorded.

**Questions this raises**

1. None — the decision belongs to the F-CORE-002 remediation (route-or-delete).

**Proposed remediation**

1. Per the F-CORE-002 remediation (route core→npu over ctl): keep this module as the serving side and delete the orchestrator's in-process workers; **or** delete `npu_proc.py`'s model workers and reduce the child to the embed role ADR-008 assigns. Decision deferred to that finding — do not half-fix here.
2. Add `stop()` to `NPUProcess` (set `running=False`, close sockets, `ctx.term()`) and call it from the process wrapper so shutdown is clean.
3. Add `tests/test_senses.py::test_npu_process_stop_terminates_loop` (T1 with sockets stubbed): `stop()` ends the poll loop.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** loop exits without ZMQ warnings
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_npu_process_stop_terminates_loop -q`

**Cross-references:** F-CORE-002, F-CORE-003, F-CORE-029

---

### F-SENS-013 — Selftest and sys.pong payloads contain hard-coded success values (`compile_cache_hit=True`, fake queue depth)

| Field | Value |
|---|---|
| **ID** | F-SENS-013 |
| **Title** | Selftest and sys.pong payloads contain hard-coded success values (`compile_cache_hit=True`, fake queue depth) |
| **Severity** | S3 — Low |
| **Category** | UX |
| **Location** | `src/lucca/senses/npu_proc.py:107-113`; `src/lucca/senses/audio_proc.py:307` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/npu_proc.py:111`
```python
                    compile_cache_hit=True,
```
(`queue_depth=0` in both pong handlers; `sys.selftest_result` is the boot gate Spec 01 §7.5 waits on — F-CORE-002 notes core never waits for it, so the fabricated field currently harms nothing, but any future boot gate would trust a constant.)

**What is wrong / assumed / missing**

The self-test reports a compile-cache hit it never measured and queue depths it never tracks. Honesty-of-telemetry family; benign today because the payload has no consumer.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/npu_proc.py:111`: set `compile_cache_hit=False` until an actual OpenVINO compile-cache check exists, and report `queue_depth` from the poller backlog or mark the field `None` (schema change in `ipc_schemas.py`).
2. Add `tests/test_senses.py::test_selftest_payload_honest` after the schema change.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** no hard-coded success fields
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_selftest_payload_honest -q`

**Cross-references:** F-SENS-005, F-CORE-009

---

### F-SENS-014 — ASR confidence gating is unimplemented: `avg_logprob` is computed but never compared to `config.asr.lowconf_logprob`

| Field | Value |
|---|---|
| **ID** | F-SENS-014 |
| **Title** | ASR confidence gating is unimplemented: `avg_logprob` is computed but never compared to `config.asr.lowconf_logprob` |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/senses/asr.py:107-118`; `src/lucca/core/config.py` (`asr.lowconf_logprob`); `luccadocs/audit/findings/mem.md` F-MEM-004 |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/asr.py:107-108`
```python
        full_text = " ".join(full_text_parts)
        avg_logprob = float(np.mean(logprobs)) if logprobs else 0.0
```
(the value is placed on `ASRResultPayload.avg_logprob` and travels to the orchestrator, which attaches no provenance at all — F-CORE-003; `config.asr.lowconf_logprob` exists as the designed threshold and has zero consumers.)

**What is wrong / assumed / missing**

The `USER_EXPLICIT` vs `USER_EXPLICIT_LOWCONF` decision — Spec 03's confidence gate and TM's "Whisper mis-hearing becomes USER_EXPLICIT" residual-risk control — is supposed to happen here on `avg_logprob`. It never does: no code compares the logprob to the configured threshold, so every transcript is implicitly high-confidence. This is the upstream half of F-MEM-004 (which found the LOWCONF tier has no consumer downstream): **both ends of the low-conf flow are missing**.

**Why it matters**

With the distil-small.en model (F-SENS-001) mis-hearings are common; without the gate every mis-hearing is eligible to become `USER_EXPLICIT` memory — the exact accepted-residual-risk scenario Spec 12 deferred to "Phase 7: dual-ASR agreement" on the assumption the confidence gate existed.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/asr.py`, `transcribe()`: set `payload.provenance_hint = "USER_EXPLICIT_LOWCONF" if avg_logprob < self.config.asr.lowconf_logprob else "USER_EXPLICIT"` (new field on `ASRResultPayload`), so the wiring consumer (F-REAS/F-MEM remediations) can sign accordingly.
2. Add `tests/test_senses.py::test_lowconf_threshold_applied`: stub model returning segments with `avg_logprob=-2.0` vs `-0.2`; assert the hint flips around the configured threshold.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** hint flips at the threshold
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_lowconf_threshold_applied -q`

**Cross-references:** F-MEM-004, F-SENS-001, F-CORE-003

---

### F-SENS-015 — The Anime DSP chain is preview-only: the production TTS path never applies it

| Field | Value |
|---|---|
| **ID** | F-SENS-015 |
| **Title** | The Anime DSP chain is preview-only: the production TTS path never applies it |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/senses/dsp_chain.py:183-256`; `src/lucca/senses/tts.py:168-216`; `src/lucca/ui/settings_dialog.py:1748-1751` |
| **Status** | OPEN |

**Evidence**

A repo-wide search: `AnimeVoiceDSP` is constructed **only** in `settings_dialog.py:1750` (the LLM-tab test-preview). `TTSWorker.synthesize` (`tts.py:190-216`) goes straight from `engine.create` to int16 conversion and ring write — no DSP call exists in the production path.

**What is wrong / assumed / missing**

The "Anime Voice DSP post-processing chain" — 212 lines of pitch-shift/EQ/compression/exciter that define the product's advertised voice aesthetic, with a working UI configuration surface — is applied only to the settings dialog's preview render. The shipped voice is raw Kokoro output. Which side is right: the feature's existence (Charter §2.1: shipped extras are first-class) says the chain belongs in the synthesis path; at minimum the UI must not present controls for a chain that never runs.

**Why it matters**

A fully built feature with a UI surface and zero production effect — the same shape as the affect layer (F-CORE-031) and the DSP settings the user can tune will do nothing audible.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/senses/tts.py`, `synthesize()`: after `engine.create` and before int16 conversion, apply `AnimeVoiceDSP(AnimeDSPConfig()).process(samples_f32, sr)` when `config` enables it (add `[senses] dsp_enabled: bool = True` or reuse the UI's persisted config); resample if the DSP chain assumes 24 kHz (it does).
2. Add `tests/test_senses.py::test_dsp_chain_applied_in_tts_path`: stub engine returning a known sine; assert the synthesised samples differ from raw with DSP enabled and match with it disabled.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** DSP applied in the production path
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_dsp_chain_applied_in_tts_path -q`

**Cross-references:** F-CORE-031, F-BRAIN-057

---

### F-SENS-016 — `EnergyVAD` has no hysteresis or hangover; brief dips split utterances

| Field | Value |
|---|---|
| **ID** | F-SENS-016 |
| **Title** | `EnergyVAD` has no hysteresis or hangover; brief dips split utterances |
| **Severity** | S4 — Info |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/senses/vad.py:48-65` |
| **Status** | OPEN |

**Evidence**

`src/lucca/senses/vad.py:50-59`
```python
        is_speech = frame_rms > self.threshold_linear

        speech_indices = np.where(is_speech)[0]
```
(speech_ms counts *voiced* frames only — a 100 ms consonant gap inside a sentence reduces `vad_speech_ms`, and start/end snap to first/last voiced frame with no hangover.)

**What is wrong / assumed / missing**

Fixed-threshold, no-hysteresis energy VAD under-reports speech for plosive gaps and breaths; `vad_speech_ms` feeds the orchestrator's silence guard (`vad_speech_ms < 100`, F-CORE-003 family) and the router's CLARIFY branch (`vad_speech_ms < 400`, F-ROUT-002) — so a quiet speaker with gaps can be misrouted to CLARIFY. Informational: the guard thresholds absorb most cases; a hangover of 2–3 frames and a lower speech-side threshold would be the standard fix.

**Why it matters**

VAD output gates two budget-relevant decisions; its brittleness is worth recording before tuning attempts begin.

**Questions this raises**

1. None.

**Proposed remediation**

1. Add a hangover (count trailing voiced-adjacent frames as speech) and a two-threshold onset/offset scheme in `src/lucca/senses/vad.py`; validate against the existing fixture WAVs.
2. Add `tests/test_senses.py::test_vad_hangover` (T1): synthetic speech with 120 ms gap → single segment.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** gap bridged
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_senses.py::test_vad_hangover -q`

**Cross-references:** F-ROUT-002, F-CORE-003

---

## 4. Assumptions register

| # | Location | Assumption embedded in code | Why unverified | Risk if false |
|---|---|---|---|---|
| A-N-01 | `asr.py:42-48` | distil-small.en CPU int8 meets the latency/accuracy budget | No product-path benchmark (S1_35 measured the OV model, not this) | TTFT budget consumed by slow ASR (F-CORE-010) |
| A-N-02 | `ring_buffer.py:22` | Big-endian header + plain RMW is safe across processes | No synchronisation (F-SENS-002) | Lost writes/flags under load |
| A-N-03 | `tts.py:63,71-86` | The hard-coded 54-voice list matches `voices-v1.0.bin` | Only verified when the file loads; mismatch → phantom voices in the UI picker | UI offers voices that fail at synthesis |
| A-N-04 | `embed.py:50-53` | NPU reshape to static 128 tokens always succeeds | NPU compile observed degenerate elsewhere (S1_35) | Embed worker silently on CPU (already handled) or raises |
| A-N-05 | `audio_proc.py:87` | 200 ms pre-roll is always available in the ring | Ring is 60 s; only stale after stalls (F-SENS-003) | Pre-roll wraps to garbage |
| A-N-06 | `ptt.py:89` | `GetAsyncKeyState` polling at 5 ms sees every press | Poll-based; a press+release inside 10 ms could be missed | Rare missed PTT |
| A-N-07 | `audio_proc.py:263` | Capture blocksize 320 (20 ms) keeps the callback under budget on this host | 0 % coverage, no latency measurement of the callback | Audible capture dropouts |
| A-N-08 | `dsp_chain.py` defaults | The anime DSP chain is wanted on the production voice | Feature exists but is unwired (F-SENS-015); owner decision D-AUD-03 changes the persona voice context | Chain applied or dropped contrary to owner intent |

## 5. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-N-01 | Is `distil-small.en` the intended shipped ASR (record it) or is the OV large-v3-turbo ladder the target (F-SENS-001)? | Determines the config/spec remediation direction and the Phase-1 latency basis | owner |
| Q-N-02 | Should the Anime DSP chain be wired into the production TTS path (F-SENS-015) or removed as preview-only? | Voice aesthetic vs raw Kokoro; interacts with D-AUD-03 voice decisions | owner |
| Q-N-03 | Should ASR/TTS run in `lucca-npu` via the complete ZMQ path, or in-process (delete one)? | F-SENS-012 / F-CORE-002 decision | architect |

## 6. Coverage gaps

### 6.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| Configured ASR model/device ladder | Spec 07 §4, `config.asr.*` | none (hard-coded — F-SENS-001) |
| Low-confidence gating threshold | Spec 03 (`asr.lowconf_logprob`) | none (F-SENS-014) |
| Ring header concurrency safety | Spec 01 §5 / Spec 07 §2 | none (race — F-SENS-002) |
| Stale capture-window detection | Spec 07 §2 | none (F-SENS-003) |
| TTS voice-fallback signalling | Spec 07 §5 | none (F-SENS-004) |
| Honest heartbeat payloads | Spec 01 §3 | none (F-SENS-005/013) |
| Anime DSP in the synthesis path | Charter §2.1 shipped feature | none (preview-only — F-SENS-015) |
| VAD segmentation quality | Spec 07 §3 | none (0 % coverage; F-SENS-016) |
| PTT debounce/auto-release | Spec 07 §1 | none (0 % coverage) |
| Jitter adaptation bounds | Spec 10 S5 | none (ratchet — F-SENS-010) |

### 6.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| `tests/test_dsp_chain.py` (93 % cov) | Anime DSP chain | Pure signal processing; the chain is never invoked in the production TTS path (F-SENS-015) |
| `tests/test_ring_buffer.py` (85 % cov) | Shared-memory IPC | Single-threaded behaviour only; the cross-process RMW race is untestable as written (F-SENS-002) |
| `tests/test_turn_loop.py` (via FakeTTS/FakeASR) | Voice pipeline | Fakes bypass `tts.py`/`asr.py` entirely — the real workers have no direct tests (tts 32 %) |

## 7. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** Reviewing F-SENS-001 (hard-coded ASR) surfaced the low-conf gating gap F-SENS-014 (the same file ignores the other half of its config). Reviewing F-SENS-002 (header race) surfaced F-SENS-003 (stale `read_slice` — the same unsynchronised-memory family). Reviewing F-SENS-005 (fake pong RSS) surfaced F-SENS-013 (fake selftest fields) and, via the sys.pong path, F-SENS-006 (fabricated talk duration). Reviewing the F-CORE-002 cross-reference surfaced F-SENS-012 (double model loading — answering core Q-03 from code).
2. **Unasked questions.** 3 registered (§5); decisions that could be made were recorded in findings (F-SENS-008 config-anchored paths; F-SENS-010 per-turn jitter reset; F-SENS-015 DSP-in-path pending Q-N-02).
3. **Unwarranted assumptions.** The first draft claimed the DSP chain "was dropped" — corrected to preview-only after finding the UI wiring. F-SENS-016 (VAD) was graded S4 after tracing its consumers' thresholds (100 ms/400 ms absorb the brittleness in most cases). The `"#true"`-style lexer-level checks done in REAS have no counterpart here; the `VOICE_ALIASES` single-entry map was verified deliberate (rename) and not filed.
4. **Incomplete planning.** Every remediation names file, function, before/after, and a runnable command; the two owner-owned calls (ASR model target, DSP wiring) are parked as Q-N-01/Q-N-02 with the architect call (route-or-delete NPU) as Q-N-03.
5. **Architectural flaws → F-ARCH candidates.** (a) F-SENS-001/014: the shipped ASR is neither the configured model nor confidence-gated — the ears of the system differ from every document; (b) F-SENS-002: the real-time IPC substrate lacks synchronisation — an F-ARCH "concurrency model undefined across the audio path" candidate spanning SENS/CORE; (c) F-SENS-012 answers and reinforces the F-CORE-002 double-loading architecture finding.

Severity re-grades during the pass: F-SENS-002 kept S1 (real-time barge-in gate depends on it); F-SENS-005 S3→S2 (the health channel is the designated liveness/resource mechanism per Spec 01 §3); F-SENS-016 set S4 (consumer thresholds absorb the brittleness today).
