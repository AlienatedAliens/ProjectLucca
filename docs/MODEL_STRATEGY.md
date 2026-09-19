# Project Lucca — Model Strategy & Inference Pipeline Specification

**Status:** Canonical Strategy & Evaluation Baseline  
**Version:** 0.2.0  
**Updated:** September 2026  
**Audience:** System Architects, Core Engineers, AI Researchers  

---

## 1. Executive Summary

This document evaluates the two primary inference architectures available to Project Lucca:
1. **Audio-Native Multimodal Pipeline (Option B)**: Direct audio token projection via Ultravox.
2. **Cascade / Transcript-First Pipeline (Option D)**: Fast synchronous ASR followed by structured text LLM inference.

It details the fundamental architectural trade-offs between both approaches, formally records the **Audio-Native Pre-Processing Blindspot**, benchmarks our hardware constraints on Blackwell/Ada mobile silicon, and specifies the candidate LLM evaluation roadmap including **Mistral NeMo 12B**, **gpt-oss-20b**, and **Ultravox 8B**.

---

## 2. Pipeline Analysis: Audio-Native vs. Cascade

```
────────────────────────────────────────────────────────────────────────────────────────
OPTION B: AUDIO-NATIVE PIPELINE (Ultravox v0.5 8B)
────────────────────────────────────────────────────────────────────────────────────────
[User Speech] ──► PCM Audio (16 kHz)
                        │
                        ├──► [Direct Multimodal Forward Pass]
                        │    Ultravox mmproj + Llama-3.1-8B ──► First Token (~180 ms)
                        │    (BLIND to turn intent, memories, and rules)
                        │
                        └──► [Parallel Speculative ASR]
                             Whisper-turbo (~150-220 ms) ──► Transcript arrives TOO LATE
                                                             to guide initial response.

────────────────────────────────────────────────────────────────────────────────────────
OPTION D: CASCADE / TRANSCRIPT-FIRST PIPELINE (Mistral NeMo 12B / gpt-oss-20b)
────────────────────────────────────────────────────────────────────────────────────────
[User Speech] ──► PCM Audio (16 kHz)
                        │
                        ▼
           OpenVINO Whisper-large-v3-turbo (NPU / GPU)
                        │ (~120–180 ms)
                        ▼
                [Exact Transcript]
                        │
       ┌────────────────┴────────────────────────┐
       ▼                                         ▼
[Deterministic Intent?]                [Conversational Intent]
       │                                         │
Heuristic Router (< 2 ms)              Hybrid Memory Retrieval (k=8, < 25 ms)
       │                               (Vector + FTS search ON CURRENT QUERY)
       ▼                                         │
Direct MicroScheme Rule                          ▼
(Bypasses LLM entirely!)               Augmented Prompt + Context Block
       │                                         │
Total E2E: ~150 ms                               ▼
                              Text LLM: Mistral NeMo 12B / gpt-oss-20b
                                       │ (TTFT ~180–220 ms)
                                       ▼
                             Streaming Chunker + Kokoro TTS
                                       │
                               Total E2E: ~550–650 ms
```

### 2.1 The "Audio-Native Pre-Processing Blindspot"
In the original pre-audit design (Option B), audio was fed directly into `llama-server` via base64 `input_audio`. While this achieved an impressive cold Time-To-First-Token (TTFT), it introduced an unavoidable structural limitation:

1. **Inability to Query Turn-Specific Memory**: In a conversational agent, the most important memory retrieval happens on what the user *just said* (e.g., "What was the name of the restaurant I liked in Kyoto?"). In audio-native mode, no text query exists when the turn begins; the memory system can only retrieve facts based on prior history.
2. **Loss of Deterministic Rule Interception**: High-confidence voice commands (such as "mute audio", "set timer", "open calculator") should never touch a multi-billion parameter LLM. In cascade mode, the router identifies the intent and fires a 5 ms MicroScheme rule, executing the entire turn in ~150 ms. In audio-native mode, every utterance must pass through the LLM.
3. **Indirect Prompt Injection & Sanitization Gap**: In cascade mode, transcripts are tagged with provenance, sanitized, and enclosed in safety boundaries before hitting the model. In audio-native mode, audio adversarial attacks or unvetted speech tokens pass directly into the backbone embeddings.
4. **The Parallel ASR Failure**: Spec 10 attempted to mitigate this by running Whisper in parallel speculatively. However, by the time Whisper transcribes the audio (150–220 ms), the LLM has already generated its first audio-chunk tokens. Information retrieved from the parallel pass cannot alter tokens already emitted.

---

## 3. Hardware Budget & Resource Constraints

All candidate models must operate strictly within the hardware limits of the target workstation platform:
- **Host GPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB GDDR7 VRAM, Blackwell architecture).
- **VRAM Clamp**: $\le 9.5\text{ GB}$ maximum resident footprint for `llama-server` (leaving $\ge 6.5\text{ GB}$ for display, Windows DWM, NPU fallback, and desktop applications).
- **KV Cache Budget**: `ctx-size = 8192` with `cache-type-k = q8_0` and `cache-type-v = q8_0` ($\approx 550\text{ MB}$ at 8k context).
- **Inference Server**: Native Windows `llama-server.exe` built with CUDA 12.8, Flash Attention enabled (`--flash-attn`), and Jinja template support (`--jinja`).

---

## 4. Candidate Brain Matrix

| Candidate | Architecture & Params | Quantization & Size | Context | Licensing | Key Strengths & Strategic Role |
|---|---|---|---|---|---|
| **Ultravox v0.5** *(Current)* | Multimodal Llama-3.1-8B + Whisper-turbo projector | Q6_K (~6.6 GB) + mmproj (~0.74 GB) $\approx 7.34\text{ GB}$ | 8k | Llama 3.1 Community | **Audio-Native Primary / Fallback**. Lowest TTFT (~180 ms), but subject to the pre-processing blindspot. |
| **Mistral NeMo 12B** *(New)* | Dense 12.2B (Mistral AI & NVIDIA), Tekken tokenizer | Q4_K_M (~7.47 GB) or Q5_K_M (~8.69 GB) | 128k (native) | **Apache 2.0** | **Prime Candidate for Cascade Primary**. Fits in 9.5 GB budget. Exceptional reasoning, strict tool calling adherence, 128k context, zero multimodal overhead. |
| **gpt-oss-20b** *(D-AUD-06)* | MoE ~21B total / ~3.6B active (or specialized 20B) | MXFP4 or Q4_K_M (~11.0 GB) | 32k–128k | Apache 2.0 | **Deep Reasoning Candidate**. High decode tok/s via sparse active parameters. Risk: reasoning traces and memory footprint may push mobile VRAM boundaries. |
| **Meta-Llama-3.1-8B** | Dense 8.0B | Q6_K (~6.6 GB) | 128k | Llama 3.1 Community | **Lean Text Baseline**. Highly optimized prompt formats, drop-in replacement for Ultravox text mode without mmproj. |

---

## 5. Comparative Latency Budgets (Spec 10 §2)

Both pipelines are governed by formal stage latency budgets enforced via `lucca-admin latency`:

| Stage | From $\rightarrow$ To | Audio Mode (Option B) | Cascade Mode (Option D) | Primary Mechanism |
|---|---|---|---|---|
| **S1 PTT $\rightarrow$ Dispatch** | `t_key_release → t_llm_sent` | 15 ms median / 30 ms p95 | — | VAD trim + WAV encode + HTTP send |
| **S1b ASR** | `t_key_release → t_asr_done` | *(parallel background)* | 180 ms median / 250 ms p95 | OpenVINO Whisper-turbo on NPU/GPU |
| **Router / Memory** | `t_asr_done → t_llm_sent` | — | 15 ms median / 25 ms p95 | Heuristic router + SQLite-vec query |
| **S2 TTFT** | `t_llm_sent → t_llm_first_token`| 180 ms median / 300 ms p95 | 180 ms median / 280 ms p95 | GPU inference (prefill + first decode)|
| **S3 First Chunk** | `t_llm_first_token → t_first_chunk` | 90 ms median / 150 ms p95 | 90 ms median / 150 ms p95 | Streaming chunker clause boundary |
| **S4 TTS First** | `t_first_chunk → t_tts_first_done` | 150 ms median / 180 ms p95 | 150 ms median / 180 ms p95 | Kokoro ONNX on NPU/CPU |
| **S5 To Speaker** | `t_tts_first_done → t_first_sample` | 40 ms median / 80 ms p95 | 40 ms median / 80 ms p95 | Jitter buffer overlap + WASAPI write|
| **Total E2E** | `t_key_release → t_first_sample` | **$\approx 475\text{ ms}$ (Gate: $\le 600$)** | **$\approx 655\text{ ms}$ (Gate: $\le 800$)** | Canonical Turn Latency Gate |

*Note: Cascade mode adds ~180 ms for ASR, but in exchange guarantees full contextual memory retrieval, intent routing, and prompt injection defense prior to token generation.*

---

## 6. Supply-Chain Security & Weight Verification

In accordance with F-ARCH-004 and Spec 12 (TM-08), all model weights are cryptographically verified against SHA256 checksums before loading:

1. **Pinned Manifest (`models/MANIFEST.json`)**:
   Every deployed weight file is registered with its exact byte count, upstream Hugging Face repository, source filename, and SHA256 hash.
2. **Download Enforcement (`scripts/download_llm_models.py`)**:
   Downloads compute rolling SHA256 digests in 1 MiB chunks. Corrupted or tampered downloads are automatically unlinked and rejected.
3. **Pre-flight Enforcement (`server_ctl.start_server` & `env_check`)**:
   `llama-server` refuses to launch if any weight file deviates from its pinned checksum.
