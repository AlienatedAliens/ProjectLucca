# Project Lucca — Model Strategy & Inference Pipeline Specification

**Status:** Canonical Strategy & Operational Deployment (Ratified per D-BRAIN-05)  
**Version:** 0.3.0  
**Updated:** September 2026  
**Audience:** System Architects, Core Engineers, AI Researchers  

---

## 1. Executive Summary

This document specifies the ratified inference architecture for Project Lucca:
1. **Cascade / Transcript-First Pipeline (Option D)**: Fast synchronous ASR followed by structured text LLM inference, memory grounding, and deterministic rule execution.
2. **Primary Neural Brain (`D-BRAIN-05`)**: **Mistral NeMo 12B Instruct Abliterated (Q6_K GGUF)** served natively on Windows by `llama-server.exe` with `--chat-template mistral-v3`.
3. **Execution Tiers (`D-ARCH-05`)**: Sub-150ms Emergency Reflexes (`REFLEX`), Act-Then-Narrate natural voice for procedural rules (`ACT_THEN_NARRATE`), and multi-step tool loops with spoken thinking cues (`FULL_LOOP`).

This design supersedes the audio-native Ultravox 8B architecture by resolving the **Audio-Native Pre-Processing Blindspot**, eliminating corporate preachy refusal alignment without compromising safety, and operating comfortably within a 12.5 GB resident VRAM clamp on the RTX 5080 Laptop GPU.

---

## 2. Pipeline Analysis: Cascade Architecture (Ratified Option D)

```
[User Speech] ──► PCM Audio (16 kHz)
                        │
                        ▼
       Energy VAD Trimming + Faster-Whisper ASR
                        │ (~120–180 ms)
                        ▼
                [Exact Transcript]
                        │
       ┌────────────────┴────────────────────────┐
       ▼                                         ▼
[Emergency Reflex?]                       [Standard Turn]
       │                                         │
Heuristic Router (< 1 ms)                 Heuristic Router (< 1 ms)
       │                                         │
       ▼                                  ┌──────┴─────────────────────┐
TIER 1: REFLEX                            ▼                            ▼
- Direct cancellation / mute       TIER 2: ACT-THEN-NARRATE     TIER 3: FULL-LOOP
- Zero LLM latency                 - Sandbox rule plan          - Memory Retrieval (2048 tok)
- Total E2E: < 150 ms              - Tool output trace          - NeMo 12B reasoning
                                   - NeMo companion voice       - Spoken verbal cues
                                     narration                  - Multi-step tool calls (M<=3)
                                   - Total E2E: ~450–600 ms     - Total E2E: ~650–850 ms
```

### 2.1 The "Audio-Native Pre-Processing Blindspot" (Why Cascade Won)
In the original pre-audit design (Option B), audio was fed directly into `llama-server` via base64 `input_audio`. While this achieved a low Time-To-First-Token (TTFT), it introduced severe structural failures:

1. **Inability to Query Turn-Specific Memory**: In a conversational companion, memory retrieval must evaluate what the user *just said*. In audio-native mode, no text query exists when the turn begins; the memory system was blind to the active utterance.
2. **Loss of Deterministic Rule Interception**: High-confidence voice commands (such as "mute audio", "pause", "open calculator") should never touch a multi-billion parameter LLM. In cascade mode, the router identifies the intent in $<1\text{ms}$ and fires a deterministic MicroScheme rule.
3. **Indirect Prompt Injection & Sanitization Gap**: In cascade mode, transcripts are tagged with cryptographic provenance (`USER_EXPLICIT`), sanitized, and enclosed in safety boundaries before hitting the model. In audio-native mode, raw speech tokens passed directly into the backbone embeddings.
4. **The Parallel ASR Failure**: Running Whisper in parallel speculatively failed because by the time Whisper transcribes audio (150–220 ms), an audio-native model has already generated initial speech tokens.

---

## 3. Hardware Budget & Resource Constraints

All inference operations are strictly bounded to the physical constraints of the workstation:
- **Host GPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB GDDR7 VRAM, Blackwell `sm_120`).
- **Resident VRAM Clamp (`D-BRAIN-05`)**: $\le 12.5\text{ GB}$ (12,800 MB) maximum resident footprint for `llama-server` (leaving $\ge 3.5\text{ GB}$ dedicated to Windows DWM, display rendering, browser hardware acceleration, and NPU offload).
- **Observed Live Footprint**: **10,748 MiB** resident VRAM at steady-state with 16,384 context. Temperature stable at 42°C.
- **KV Cache Budget**: `ctx-size = 16384` with `cache-type-k = q8_0` and `cache-type-v = q8_0` ($\approx 2.1\text{ GB}$ resident KV cache).
- **Inference Server**: Native Windows `llama-server.exe` built with CUDA 12.8, Flash Attention enabled (`--flash-attn`), and Mistral v3 chat template (`--chat-template mistral-v3`).

---

## 4. Candidate Brain Matrix & Deployment Status

| Candidate | Architecture & Params | Quantization & Size | Context | Licensing | Strategic Role & Status |
|---|---|---|---|---|---|
| **Mistral NeMo 12B Instruct Abliterated** | Dense 12.2B (Mistral AI & NVIDIA), Tekken tokenizer | Q6_K (~10.1 GB) | 16k (active) / 128k (native) | **Apache 2.0** | **Deployed Primary Brain (`D-BRAIN-05`)**. Exceptional reasoning, strict tool calling, suppresses preachy refusals without erotic drift. 10.5 GB live VRAM. |
| **Ultravox v0.5 8B** | Multimodal Llama-3.1-8B + Whisper-turbo projector | Q6_K (~6.6 GB) + mmproj (~0.74 GB) | 8k | Llama 3.1 Community | **Deprecated / Archived**. Suffers from pre-processing blindspot and moralizing prefill refusals. |
| **gpt-oss-20b** | MoE ~21B total / ~3.6B active | MXFP4 / Q4_K_M (~11.0 GB) | 32k–128k | Apache 2.0 | **Future Deep Reasoning Research**. Evaluated for future 64GB RAM / external accelerator topologies. |
| **Meta-Llama-3.1-8B** | Dense 8.0B | Q6_K (~6.6 GB) | 128k | Llama 3.1 Community | **Lean Fallback Baseline**. Lightweight text fallback if extreme VRAM pressure occurs. |

---

## 5. Comparative Latency Budgets & Measured Performance

| Stage | From $\rightarrow$ To | Target Budget (Spec 10) | Live Measured Benchmark | Mechanism |
|---|---|---|---|---|
| **S1 PTT $\rightarrow$ Dispatch** | `t_key_release → t_llm_sent` | $\le 20\text{ ms}$ | Target Budget | VAD trim + WAV encode |
| **S1b ASR** | `t_key_release → t_asr_done` | $\le 180\text{ ms}$ | ~140–180 ms | Faster-Whisper on CPU/NPU |
| **Router / Memory** | `t_asr_done → t_llm_sent` | $\le 15\text{ ms}$ | **< 1.0 ms (Router)**<br>~8–15 ms (SQLite-vec) | Heuristic router + sqlite-vec |
| **S2 TTFT** | `t_llm_sent → t_llm_first_token`| $\le 180\text{ ms}$ | **44.5 ms median / 54.9 ms p95** | NeMo 12B Q6_K on RTX 5080 |
| **S3 First Chunk** | `t_llm_first_token → t_first_chunk` | $\le 100\text{ ms}$ | ~60–90 ms | Streaming chunker clause boundary |
| **S4 TTS First** | `t_first_chunk → t_tts_first_done` | $\le 160\text{ ms}$ | ~130–150 ms | Kokoro ONNX on NPU/CPU |
| **S5 To Speaker** | `t_tts_first_done → t_first_sample` | $\le 40\text{ ms}$ | ~20–35 ms | Ring buffer overlap + WASAPI write |
| **Total E2E (Full-Loop)**| `t_key_release → t_first_sample` | **$\le 800\text{ ms}$** | **~620–750 ms** | Canonical Turn Latency Gate |
| **Total E2E (Reflex)**   | `t_key_release → t_first_sample` | **$\le 150\text{ ms}$** | **~85–120 ms** | MicroScheme Reflex Gate |

---

## 6. Grounded Narration & Multi-Step Tool Protocol

### 6.1 Grounded Narration Provenance Contract (`D-BRAIN-04`)
In Tier 2 (`ACT_THEN_NARRATE`) turns, the prompt builder injects strict anti-hallucination provenance instructions:
```text
[System Executed Tool Trace: launch_app({'app_name': 'calculator'}) -> Status: ok. Content: Launched calculator]
Directive: The action above has completed. Grounding your response strictly in the tool execution output above without fabricating metrics or unverified facts, speak to the user naturally in your companion persona (1-2 brief conversational sentences).
```

### 6.2 Multi-Step Tool Loop with Verbal Cues (`D-BRAIN-03`)
In Tier 3 (`FULL_LOOP`) turns requiring multi-step tool calls:
1. When NeMo emits a tool call (e.g. `read_file`), Orchestrator emits an immediate spoken thinking cue:
   - *"Checking that file for you..."*
   - *"Running that calculation..."*
   - *"Looking into that..."*
2. Tool execution occurs in the sandbox while the user hears the audio cue.
3. NeMo is re-prompted with `ToolResult` up to $M=3$ rounds before streaming final speech.

---

## 7. Supply-Chain Security & Weight Verification

In accordance with F-ARCH-004 and Spec 12 (TM-08), all model weights are cryptographically verified against SHA256 checksums before loading:

1. **Pinned Manifest (`models/MANIFEST.json`)**:
   Every deployed weight file is registered with its exact byte count, upstream repository, source filename, and SHA256 hash.
   - `Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf`: `8cef81a30f78d927c73a693c4c9e4c5f939e60ea9b2518e38d6df022ee7b2434`
2. **Download Enforcement (`scripts/download_llm_models.py`)**:
   Downloads verify rolling SHA256 digests in 1 MiB chunks. Corrupted downloads are unlinked immediately.
3. **Pre-flight Enforcement (`server_ctl.start_server` & `env_check`)**:
   `llama-server` refuses to launch if any weight file deviates from its pinned checksum.
