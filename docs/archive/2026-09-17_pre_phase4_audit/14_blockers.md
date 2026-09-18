# Phase 0 Blockers & Threshold Discrepancy Report

**Date:** 2026-09-17  
**Rule:** `docs/00_START_HERE_implementer.md` §4:  
> "A threshold cannot be met on the real hardware: do **not** change it. Write the measured value, the test ID, and the environment to `docs/14_blockers.md` and stop that phase. Someone will decide."

---

## 1. Blocker: Spike 0.3 — Whisper ASR Latency on Real Hardware

- **Test ID:** `T-ASR-02` / Phase 0 Spike 0.3
- **Specification Reference:** `docs/11_phase_plan_v2.md` L18, `docs/09_developer_spec/07_audio_pipeline_and_barge_in.md` L35
- **Specified Threshold:** `WER ≤ 8 %, 3 s clip ≤ 300 ms p95 (NPU), ≤ 500 ms (CPU)`
- **Target Environment:** MSI Laptop, Intel Core Ultra 9 275HX, Intel AI Boost NPU (`NPU`), Intel Arc Graphics (`GPU.0`), Windows 11 Pro 64-bit, OpenVINO GenAI 2026.4.

### Measured Hardware Values:
1. **Intel NPU (`OpenVINO/whisper-large-v3-turbo-int8-ov` via `WhisperPipeline`):**
   - **Result:** **FAIL / DEFECT**
   - **Transcription:** `' Open!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!...'`
   - **Latency (p50 / p95):** **5670.0 ms / 5704.0 ms** (RTF: 4.287)
   - **Root Cause:** OpenVINO GenAI 2026.4 NPU Level-Zero lowering fails to trigger EOS / stop-token suppression correctly in the autoregressive decoder loop for Whisper, resulting in token repetition up to `max_new_tokens` (5.67 seconds).
2. **Intel Arc iGPU (`GPU.0`):**
   - **Result:** **100% Accurate** (`' Open the calculator.'`)
   - **Latency (p50 / p95):** **1472.3 ms / 2574.2 ms** (RTF: 1.113)
   - **Discrepancy:** 1472 ms > 300 ms threshold.
3. **Host CPU (`faster-whisper` `distil-small.en` int8 on 8 threads):**
   - **Result:** **100% Accurate** (`' Open the calculator.'`)
   - **Latency (p50 / p95):** **963.8 ms / 993.3 ms** (RTF: 0.730)
   - **Discrepancy:** 963 ms > 500 ms CPU threshold.

### Architectural Context & Decision Required:
Because **Option B (Ultravox Q6_K native audio)** passed all acceptance criteria with **79.8 ms median TTFT**, Whisper does **NOT** sit on the critical voice path in Option B (it runs asynchronously for user history and memory extraction). However, the standalone ASR threshold of ≤ 300 ms on NPU is currently unachievable due to the OpenVINO NPU decoder defect.  
**Decision required by architect / user:** Approve using Arc iGPU (1472 ms) or CPU `faster-whisper` (963 ms) as asynchronous background transcript generator, or adjust T-ASR-02 threshold for background execution.

---

## 2. Blocker: Spike 0.4 — Kokoro First-Chunk Latency on CPU

- **Test ID:** `T-TTS-01` / Phase 0 Spike 0.4
- **Specification Reference:** `docs/11_phase_plan_v2.md` L19, `docs/09_developer_spec/07_audio_pipeline_and_barge_in.md` L51
- **Specified Threshold:** `First-chunk ≤ 180 ms on the selected device`
- **Target Environment:** Intel Core Ultra 9 275HX, `kokoro-onnx` ONNX Runtime int8 on CPU (selected after NPU and iGPU compilation failed).

### Measured Hardware Values:
- **Selected Device:** **Host CPU** (via `kokoro-onnx` ONNX Runtime)
  - NPU compilation failed: Level0 compiler error `Bounds are not provided for shape [..., -9223372036854775808]` (dynamic intermediate dimensions in ISTFT / AdaIN).
  - Intel Arc iGPU compilation failed: OpenVINO GPU plugin error `Mode 'linear_onnx' supports only 2D or 4D, 5D tensors` (3D linear interpolation in vocoder unsupported).
- **Real-Time Factor (RTF):** **0.198** (Target: ≤ 0.35 — **PASSED**).
- **Latency for 1.88 s Reference Clause:** **p50 = 363.9 ms, p95 = 413.0 ms**.
- **Discrepancy:** 363.9 ms > 180 ms threshold for the 1.88 s reference clause.

### Architectural Context & Decision Required:
Kokoro synthesizes audio at an RTF of 0.198 (5x faster than real-time). Synthesizing shorter conversational chunks (e.g. 0.6–0.9 s initial phrases like "Opening calculator now...") takes ~120–170 ms (≤ 180 ms). However, for a 1.88 s reference clause, whole-sentence synthesis takes 363.9 ms on CPU.  
**Decision required by architect / user:** Accept CPU Kokoro based on RTF = 0.198 and chunk-sized first-phrase synthesis (Spec 08 first-chunk threshold 24–90 chars), or re-baseline T-TTS-01 for whole-clause synthesis on CPU.
