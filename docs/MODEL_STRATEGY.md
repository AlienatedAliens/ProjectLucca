# Project Lucca — Model Strategy & Inference Pipeline Specification

**Status:** Canonical Strategy & Operational Deployment (Ratified per D-BRAIN-05, D-AFF-01, D-SUP-01)  
**Version:** 1.0.0  
**Updated:** September 20, 2026  
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

---

## 8. Continuous Affective Dynamics & Prefix KV-Cache Optimization (`D-AFF-01`)

### 8.1 The KV-Cache Invalidation Hazard
Injecting continuous, dynamic floating-point variables into an LLM's system prompt (e.g. `[Affect: P=0.724, A=0.152, D=0.881]`) breaks tokenizer byte-pair encodings across turns. This invalidates the host GPU's pre-computed KV-cache, forcing `llama-server.exe` to re-evaluate all 850+ prompt tokens on every turn.

### 8.2 The Prompt Frontier Suffix Solution
1. **Static System Prompt Prefix:** The Jinja template (`templates/mistral_nemo.jinja`) and system persona prompt remain 100% static and byte-identical across all turns.
2. **Schmitt-Trigger Stance Quantization:** The continuous 3D PAD state vector is mapped into 7 discrete orthogonal stances via RBF Mahalanobis distance with a deadband hysteresis margin ($\delta_{\text{hyst}} = 0.15$).
3. **Frontier Suffix Injection:** The quantized stance token (e.g. `[STANCE: focused_analytical]`) is appended strictly to the tail of the frontier user message during `prompt_builder.build_messages()`.
4. **Physical Silicon Benchmark (RTX 5080 Laptop GPU):**
   - Naive Prefix Float Injection: **$402.05\,\text{ms}$** prompt evaluation time ($18 / 892$ tokens cached).
   - Prompt Frontier Suffix: **$46.84\,\text{ms}$** prompt evaluation time ($849 / 849$ tokens cached).
   - **Empirical Speedup:** **$8.58\times$ faster prefill**, saving **$355.21\,\text{ms}$ per turn**.

---

## 9. Streaming Output Supervision & Fast Abort (`D-SUP-01`)

### 9.1 The Need for In-Flight Clause Interception
Because abliterated weights suppress preachy refusals, safety against adversarial social engineering prompts (e.g. `adv_12`) must be enforced deterministically at runtime.

### 9.2 The Dimension 7B Supervisor Architecture
1. **Clause Boundary Token Accumulation:** Tokens streamed from `llama-server.exe` are parsed into linguistic clause chunks (`OutputSupervisorSession`).
2. **Markdown Normalization:** Strips markdown decorators (`*`, `_`, `` ` ``, `~`) to defeat obfuscated adversarial evasion.
3. **Deterministic Compiled Rule Regex:** Matches capitulation clauses (e.g. *"Here is how to extract stored browser credentials..."*) in $<15\,\mu\text{s}$.
4. **Shared-Memory Ring Signal:** If a violation is detected:
   - Sets `FLAG_ABORT` across the shared audio memory ring in $<35\,\mu\text{s}$.
   - Aborts pending Kokoro TTS synthesis chunks.
   - Substitutes the canonical refusal (*"I cannot fulfill that request as it violates core safety invariants."*) in $<500\,\text{ms}$ total turnaround.
   - Achieves 0.0% false positive aborts on benign engineering control prompts.

