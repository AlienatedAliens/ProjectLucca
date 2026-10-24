# Spec 07 — Audio Pipeline: PTT, Capture, VAD, ASR (NPU), TTS device ladder, Playback, Barge-in

Owned by `lucca-audio` (real-time) and `lucca-npu` (inference). Nothing in this spec runs in `lucca-core` except orchestration messages.

## 1. Devices and streams

| Stream | API | Rate | Format | Block | Latency setting |
|---|---|---|---|---|---|
| Capture | `sounddevice.InputStream`, WASAPI **shared** mode | 16 000 Hz | int16 mono | 320 samples (20 ms) | `latency='low'` |
| Playback | `sounddevice.OutputStream`, WASAPI shared | 24 000 Hz | int16 mono | 480 samples (20 ms) | `latency='low'` |

No resampling anywhere. Exclusive mode is a config option (`audio.exclusive=true`) and is off by default (it steals the device from other apps). Device selection by name substring in `config\lucca.toml`; default = Windows default endpoints; hot-plug → reopen stream, log `audio.device_changed`.

Callback rules (both streams): no allocation, no logging, no locks other than the ring semaphore try-acquire; copy in/out of the shared-memory ring only. Measured callback time must be < 2 ms p99 (T-AUD-01 instruments with `perf_counter_ns` into a lock-free array).

## 2. Push-to-talk

- Key: `right ctrl` hold-to-talk (D-10), configurable (`ptt.key`, `ptt.mode = hold|toggle`).
- Implementation: Win32 low-level keyboard hook (`SetWindowsHookExW(WH_KEYBOARD_LL)`) in a dedicated thread in `lucca-audio`. **Timestamp = `QueryPerformanceCounter` read as the first statement of the hook callback** (`time.perf_counter_ns()`); LL hooks are invoked within ~1 ms of the hardware event, which is adequate for a latency origin. `KBDLLHOOKSTRUCT.time` (GetTickCount-based, 10–16 ms granularity) is recorded only as a cross-check and never used for budgets. The hook thread must pump messages and return from the callback in < 1 ms (post to a queue; no logging in the callback). Key event is **not** swallowed (return `CallNextHookEx`) unless `ptt.swallow=true`.
- Known limitation (documented in user guide): hooks do not receive input while an elevated (UAC) window has focus. Fallback: tray-icon toggle button.
- Pre-roll: capture ring is always running; on press, `capture_seq_start = write_idx − 0.2 s` (200 ms pre-roll catches clipped first syllables).
- Auto-release at **29.5 s** held (Whisper/Ultravox 30 s window). Speak nothing; UI shows "max length".
- Debounce: presses < 150 ms apart are one press. Releases with `vad_speech_ms < 250` → `ptt.released{empty=true}` → core says nothing, UI flashes "didn't catch that".

## 3. VAD (Silero, CPU, ONNX Runtime)

Runs in `lucca-audio` on 32 ms windows over the captured span after release (not in the callback): trims leading/trailing non-speech (pad 100 ms each side), reports `vad_speech_ms`. Threshold 0.5. It never decides *when* to stop — PTT does. Cost ≤ 15 ms for a 10 s clip on one core.

## 4. ASR (`lucca-npu`)

- Primary: OpenVINO GenAI `WhisperPipeline` with `whisper-large-v3-turbo` stateful IR, device `NPU`, `language="en"`, `task="transcribe"`, `return_timestamps=True`. Compile cache in `cache\ov\`. Warm-up at boot with a 1 s silent clip.
- Fallback ladder (automatic at boot, recorded in `sys.selftest_result.asr_device`): `NPU` → `GPU` (Arc iGPU) → `CPU` faster-whisper `distil-whisper-small` int8 (CTranslate2). Ladder step taken if compile fails **or** self-test latency for a 3 s clip > 400 ms.
- Output normalisation: NFC, strip leading/trailing space, collapse whitespace, keep punctuation and case (Whisper's), drop bracketed non-speech tags (`[BLANK_AUDIO]`, `(laughs)`).
- `avg_logprob` from segments (mean weighted by duration) → provenance confidence (spec 03).
- Gates: T-ASR-01 WER on the frozen 40-clip set (`tests/fixtures/asr/`, own recordings + LibriSpeech-clean subset) ≤ **8 %** on NPU/GPU, ≤ 10 % on CPU fallback; T-ASR-02 latency for 3 s clip ≤ 300 ms p95 (NPU), ≤ 500 ms (CPU); T-ASR-03 empty/silent clip → `text==""`, no exception; T-ASR-04 29.5 s clip → completes ≤ 1.5 s.

## 5. TTS (`lucca-npu`) — device ladder (D-07)

Model: Kokoro-82M, voice default `af_heart` (config). G2P via `misaki` (bundled, no espeak dependency for English; if `espeak-ng` is absent, non-English is disabled and logged — resolves doc 01 L70).

Ladder evaluated at boot self-test, result stored and reported in `ui.state` tooltip and logs:

| Step | Device | Method | Take next step if |
|---|---|---|---|
| 1 | NPU | OpenVINO IR with **static-shape buckets** for phoneme length {64, 128, 256}; pad to bucket; output trimmed by predicted total duration | compile error **or** first-chunk latency for the 1.2 s reference clause > 180 ms **or** RTF > 0.35 |
| 2 | GPU (Intel Arc iGPU) | OpenVINO GPU plugin, dynamic shapes | first-chunk > 180 ms or RTF > 0.35 |
| 3 | CPU | ONNX Runtime int8 (`kokoro-onnx`), 4 intra-op threads pinned away from audio thread | always accepted; record numbers |

Device is asserted via `compiled_model.get_property("EXECUTION_DEVICES")` and written into `tts.done.device`. Phase 1 acceptance reports the device reached; NPU is preferred, not required (D-07 rewording).

Streaming contract: each `tts.synthesize` chunk (from spec 08) is synthesised whole (Kokoro is not token-streaming), written into `play_ring` in 20 ms frames as soon as available; `tts.done` after last frame. Core pipelines chunk N+1 synthesis while chunk N plays (queue depth 2). Gate T-TTS-01: first-chunk latency ≤ 180 ms (1.2 s clause) on the selected device; T-TTS-02: RTF ≤ 0.35 for a 6 s paragraph; T-TTS-03: 200 consecutive chunks, RSS growth ≤ 30 MB.

## 6. Playback and jitter buffer

- Playback starts when `play_ring` holds ≥ **60 ms** of audio (jitter buffer) *or* `EOS` is set. Adaptive: after ≥ 3 underruns in a turn, +20 ms (max 120 ms); decays −10 ms per clean turn (min 60 ms).
- Underrun = callback needed N samples, ring had fewer, and `EOS` not set: output zeros, increment counter, emit `audio.underrun` (rate-limited 1/s).
- Between chunks, if ring runs dry and `EOS` not set → silence (counted as underrun only if a `tts.synthesize` is in flight > 400 ms — otherwise it is expected inter-sentence gap).
- `audio.first_sample_played` is emitted at the first callback that writes a frame with peak > −50 dBFS — this is the **latency end mark** (spec 10).
- RMS envelope (20 ms, dBFS) published for lip-sync.

## 7. Barge-in (normative sequence)

Trigger: `ptt.pressed` while turn state ∈ {THINKING, SPEAKING, CONFIRM_WAIT}.

1. `lucca-audio` (locally, ≤ 1 callback period = 20 ms): set `play_ring.flags |= ABORT`; output zeros; reset ring indices; publish `ptt.pressed{interrupts_trace_id}`.
2. `lucca-core` (≤ 50 ms): `SpeechLLMPort.abort()`; `TTSPort.abort()`; chunker `reset()`; mark current `DecisionRecord.user_interrupted=True, interrupted_after_ms`; discard unspoken chunks; state → LISTENING for the new turn.
3. `lucca-npu`: on `tts.abort`, drop queued chunks; if a synth is mid-flight, discard its output (check `trace_id` before writing to ring).
4. Memory: the interrupted assistant turn is **not** stored as history beyond the text actually spoken (track spoken prefix by chunk completion).

Gates: T-BRG-01 audio silence within 30 ms of key-down (measured by loopback capture); T-BRG-02 no frames from the old `trace_id` appear in the ring after abort (seq tagging); T-BRG-03 LLM slot idle within 100 ms; T-BRG-04 new turn's `t_key_release → first_sample` latency unaffected (within 10 % of non-barge-in median).

## 8. Multi-turn context (audio mode)

- Current user turn: `input_audio` (wav, 16 kHz, trimmed by VAD).
- History: last **6** exchanges as text — user turns = Whisper transcripts, assistant turns = *spoken* text (chunks actually played). Older turns summarised into one paragraph every 10 turns by the LLM off-critical-path (`kind="summary"`, not memory — session-only).
- Token budget (spec 10 §Context): system 350 + memory 600 + history 1 200 + summary 300 + audio ≈ 375 + reply ≤ 512 → ≈ 3 350 of 8 192.

## 9. RAM/time budget for `lucca-npu` (*estimates; measure in Phase 0*)

| Component | RSS | Compile (cold/warm) |
|---|---|---|
| OpenVINO runtime + NPU plugin | 250 MB | — |
| Whisper-large-v3-turbo IR (NPU) | 900–1 100 MB | 40–90 s / ≤ 5 s |
| Kokoro (NPU buckets ×3 or CPU int8) | 250–400 MB | 10–30 s / ≤ 2 s |
| MiniLM embed + intent encoder (NPU) | 120 MB | 5 s / ≤ 1 s |
| Total | ≈ 1.6–2.0 GB | ≤ 120 s cold, ≤ 10 s warm |
