# Project Lucca — Model Strategy & Inference Pipeline Specification

**Status:** Canonical Strategy & Operational Deployment (Ratified per D-BRAIN-05, D-ROUT-02, D-AFF-01, D-SUP-01, D-COG-01)
**Version:** 2.0.0
**Updated:** October 18, 2026
**Audience:** System Architects, Core Engineers, AI Researchers

---

## 1. Executive Summary

This document specifies the ratified multi-scale inference architecture for Project Lucca (`v1.45.0`):
1. **Cascade / Transcript-First Pipeline (Option D)**: Fast synchronous ASR followed by structured text LLM inference, memory grounding, and deterministic rule execution.
2. **Four-Tier Multi-Scale Neural Substrate (`D-BRAIN-05`, `D-ROUT-02`, `D-COG-01`)**: Served natively on Windows by `llama-server.exe` with `--jinja` and GGUF-embedded chat templates (`enable_thinking=false` for companion tiers, `q8_0` KV cache, Flash Attention):
   - **Tier 0 (`gemma-4-26B-A4B-it-heretic.Q6_K.gguf`)**: MoE (4B active params), `ctx=32768`, `ngl=28` WDDM-safe GPU residency, `--spec-type ngram-mod`. Default deliberation core.
   - **Tier 1 (`gemma-4-12b-heretic-Q6_K.gguf`)**: Dense 12B, 9,972 MiB VRAM (61.2%), 37.18 tok/s.
   - **Tier 2 (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`)**: Dense 4.5B, 4,382 MiB VRAM (26.9%), 80.76–103.0 tok/s.
   - **Tier 3 (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`)**: Dense 2.0B, 2,260 MiB VRAM (13.9%), 126.1–169.1 tok/s.
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
- Total E2E: < 150 ms              - Tool output trace          - Gemma-4 12B reasoning
                                   - Companion voice            - Spoken verbal cues
                                     narration                  - Multi-step tool calls (M=4 / cap M=8)
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
- **Host dGPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB GDDR7 VRAM, Blackwell `sm_120`, dedicated compute mode `Disp.A: Off`).
- **Host iGPU**: Intel(R) Graphics (Arrow Lake-HX Xe-LPG architecture) dedicated to Windows Desktop Window Manager (DWM) and display rendering, completely isolating the RTX 5080 from display VRAM consumption.
- **Resident VRAM Footprint**: **10,050 MiB** resident VRAM at steady-state with 16,384 context (~5,950 MiB free headroom). Expanding to 32,768 context consumes ~12.2 GB resident VRAM, operating with ~3.8 GB headroom.
- **KV Cache Budget**: `ctx-size = 16384` baseline / `32768` v1.3.0 default with `cache-type-k = q8_0` and `cache-type-v = q8_0` (quantized 8-bit cache).
- **Inference Server**: Native Windows `llama-server.exe` built with CUDA 12.8, Flash Attention enabled (`--flash-attn`), `--jinja`, and GGUF-embedded chat template.

---

## 4. Candidate Brain Matrix & Deployment Status

| Candidate | Architecture & Params | Quantization & Size | Context | Licensing | Strategic Role & Status |
|---|---|---|---|---|---|
| **Gemma-4-26B-A4B-it-Heretic** | MoE 26B total / 4B active params (Google DeepMind), Heretic ablation | Q6_K (~20.1 GB, `ngl=28` hybrid GPU/RAM) | 32k (`ctx=32768`, `q8_0` KV) | Gemma Terms of Use | **Validated Deployment Tier 0: Default Deliberation Core (`D-COG-01`)**. `ngl=28` WDDM-safe GPU residency, `--spec-type ngram-mod`, Sovereign Sight Windows 11 WinRT `OcrEngine` fallback when `mmproj=None`. |
| **Gemma-4-12B-Heretic** | Dense 12B (Google DeepMind), Heretic norm-preserving directional ablation | Q6_K (~9.8 GB) | 16k baseline / 32k active | Gemma Terms of Use | **Validated Deployment Tier 1: Symbolic Escalation Core (`D-BRAIN-05` v2)**. 9,972 MiB VRAM (61.2%), 37.18 tok/s. Peak raw generator on competition math (89.0% direct R0 @ 4k; 88.8% on 98-item clean; manifest record `math500_heldout100_direct_r0_v1_35_6`). Degrades under thinking mode (58.0% R1, $p=4.66 \times 10^{-10}$; confounded negative observation — see paper 06 §5.1). Dispatched via Direct R0. |
| **Gemma-4-E4B-it-uncensored-heretic** | Dense ~4.5B effective params (Google DeepMind), uncensored directional ablation | Q6_K (~4.38 GB) | 16k | Gemma Terms of Use | **Validated Deployment Tier: Default Sovereign Core**. 4,382 MiB VRAM (26.9%), 80.76–103.0 tok/s. Competition math via Thinking Mode R1 @ 6k reaches 88.0% strict / 92.0% lenient (87.8% on 98-item clean), a point estimate close to 12B Direct R0; cross-model comparison is confounded by fine-tune lineage (paper 06 §5.1). Dispatched via PAL for arithmetic and Thinking Mode for competition math. |
| **Gemma-4-E2B-Heretic-Sinhala** | Dense ~2.0B effective params (Google DeepMind), bilingual transfer fine-tune | Q6_K (~2.26 GB) | 16k | Gemma Terms of Use | **Validated Deployment Tier: Ultra-Edge Companion**. 2,260 MiB VRAM (13.9%), 126.1–169.1 tok/s. 81.0% strict CAS on competition math via Thinking Mode R1 @ 6k (80.6% on 98-item clean), significantly outperforming PAL (61.0%, $p=0.0002$). |
| **Mistral NeMo 12B Instruct Abliterated** | Dense 12.2B (Mistral AI & NVIDIA), Tekken tokenizer | Q6_K (~10.1 GB) | 16k / 128k (native) | **Apache 2.0** | **Deprecated (2026-09-21)**. Server-side tool parser never engaged on llama.cpp b11026; 3 hallucinated tool calls on conversational prompts. Pinned for rollback. |
| **Ultravox v0.5 8B** | Multimodal Llama-3.1-8B + Whisper-turbo projector | Q6_K (~6.6 GB) + mmproj (~0.74 GB) | 8k | Llama 3.1 Community | **Deprecated / Archived**. Suffers from pre-processing blindspot and moralizing prefill refusals. |

---

## 4.1 Dynamic Task Router Specification (`D-ROUT-02`)

The three validated scales are orchestrated via the empirical dynamic task router:

$$\text{Router}(M, T) = \begin{cases} 
\text{Direct Raw Generation (R0 @ 4,096 cap)} & \text{if } M = \text{12B} \\ 
\text{PAL in Docker (P2 @ 2,048 cap)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Arithmetic/Word} \\ 
\text{Thinking Mode (R1 @ 6,144 cap)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Competition Math} 
\end{cases}$$

- **12B Strategy:** Large models generate direct formal proofs with high accuracy (89.0% held-out strict) in low latency (12.9s); extended thinking scratchpads trigger circular re-verification loops that degrade greedy performance.
- **E4B/E2B Strategy:** Edge models benefit from neurosymbolic scaffolding: PAL Docker absorbs parameter contraction on arithmetic (equalizing 2B/4B models with 12B at 91%–94%), while latent thinking tokens (R1 @ 6k) allow edge models to explore mathematical problem representations before committing to final answers (+15 pp on E4B, +20 pp on E2B).

---

## 5. Comparative Latency Budgets & Measured Performance

| Stage | From $\rightarrow$ To | Target Budget (Spec 10) | Live Measured Benchmark | Mechanism |
|---|---|---|---|---|
| **S1 PTT $\rightarrow$ Dispatch** | `t_key_release → t_llm_sent` | $\le 20\text{ ms}$ | Target Budget | VAD trim + WAV encode |
| **S1b ASR** | `t_key_release → t_asr_done` | $\le 180\text{ ms}$ | ~140–180 ms | Faster-Whisper `distil-small.en` on dGPU CUDA float16 (CPU int8 fallback) |
| **Router / Memory** | `t_asr_done → t_llm_sent` | $\le 15\text{ ms}$ | **< 1.0 ms (Router)**<br>~8–15 ms (SQLite-vec) | Heuristic router + sqlite-vec |
| **S2 TTFT** | `t_llm_sent → t_llm_first_token`| $\le 180\text{ ms}$ | **44.5 ms median / 54.9 ms p95** | Gemma-4 12B Q6_K on RTX 5080 |
| **S3 First Chunk** | `t_llm_first_token → t_first_chunk` | $\le 100\text{ ms}$ | ~60–90 ms | Streaming chunker clause boundary |
| **S4 TTS First** | `t_first_chunk → t_tts_first_done` | $\le 160\text{ ms}$ | ~130–150 ms | Kokoro ONNX on CPU |
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
1. When the brain emits a tool call (e.g. `read_file`), Orchestrator emits an immediate spoken thinking cue:
   - *"Checking that file for you..."*
   - *"Running that calculation..."*
   - *"Looking into that..."*
2. Tool execution occurs in the sandbox while the user hears the audio cue.
3. The brain is re-prompted with `ToolResult` across a convergence-based tool loop ($M=4$ active rounds, runaway cap $M=8$) before streaming final speech.

---

## 7. Supply-Chain Security & Weight Verification

In accordance with F-ARCH-004 and Spec 12 (TM-08), all model weights are cryptographically verified against SHA256 checksums before loading:

1. **Pinned Manifest (`models/MANIFEST.json`)**:
   Every deployed weight file is registered with its exact byte count, upstream repository, source filename, and SHA256 hash.
   - `gemma-4-12b-heretic-Q6_K.gguf` (deployed primary brain per D-BRAIN-05 v2)
   - `Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf`: `8cef81a30f78d927c73a693c4c9e4c5f939e60ea9b2518e38d6df022ee7b2434` (deprecated, pinned for rollback only)
2. **Download Enforcement (`scripts/download_llm_models.py`)**:
   Downloads verify rolling SHA256 digests in 1 MiB chunks. Corrupted downloads are unlinked immediately.
3. **Pre-flight Enforcement (`server_ctl.start_server` & `env_check`)**:
   `llama-server` refuses to launch if any weight file deviates from its pinned checksum.

---

## 8. Continuous Affective Dynamics & Prefix KV-Cache Optimization (`D-AFF-01`)

### 8.1 The KV-Cache Invalidation Hazard
Injecting continuous, dynamic floating-point variables into an LLM's system prompt (e.g. `[Affect: P=0.724, A=0.152, D=0.881]`) breaks tokenizer byte-pair encodings across turns. This invalidates the host GPU's pre-computed KV-cache, forcing `llama-server.exe` to re-evaluate all 850+ prompt tokens on every turn.

### 8.2 The Prompt Frontier Suffix Solution
1. **Static System Prompt Prefix:** The system persona prompt and embedded Jinja chat template remain 100% static and byte-identical across all turns.
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

---

## 10. Model-Swap Regression Testing & LUCCA_LLM_MODEL Gate

To safely evaluate new candidate models or swapped weights without code modification:
1. **Endpoint Selection via `LUCCA_LLM_MODEL`:** Setting the `LUCCA_LLM_MODEL` environment variable (e.g. `http://127.0.0.1:8081` or `127.0.0.1:8081`) overrides the default configured brain endpoint in `LLMClient`.
2. **Required Gate for Brain Changes:** Any proposed model swap (e.g. evaluating an updated quant, alternative backbone, or prompt template revision) must execute against the frozen capability assessment battery (`tests/test_capability_assessment_live_hw.py`) targeting the candidate via `LUCCA_LLM_MODEL`.
3. **Acceptance Criteria:** The candidate must match or exceed current baseline capability scores across all categories, maintain zero fabricated facts across forced failures, and produce zero unrefuted capitulation clauses under adversarial probes.

---

## 11. Multi-Tier Deployment & Neurosymbolic Compound Execution (`v1.37.0`)

### 11.1 The Multi-Scale Model Topology
As of `v1.37.0`, Project Lucca supports three ratified local neural deployment tiers:
- **E2B Ultra-Edge (`Gemma4-E2B-Heretic-Sinhala`, 2.3B parameters, Q6_K)**: 3,516 MiB resident VRAM. Sustained 84.5 tok/s. Ambient listener & low-latency companion.
- **E4B Sovereign Core (`gemma-4-E4B-it-uncensored`, 4.0B parameters, Q6_K)**: 4,548 MiB resident VRAM. Sustained 62.1 tok/s. Default sovereign desktop companion.
- **12B Unified Brain (`gemma-4-12b-heretic`, 12.0B parameters, Q6_K)**: 10,562 MiB resident VRAM. Sustained 38.4 tok/s. Complex symbolic and research escalation.

### 11.2 Tier-Adaptive Cognitive Dispatch
- **12B Unified**: Extended thinking scratchpads cause a 36.7% overthinking collapse on formal logic. The router forces `thinking_mode="direct"` on 12B for deductive tasks.
- **Edge Tiers (E4B / E2B)**: Extended thinking lifts edge reasoning accuracy from 23% to 63% (+40 pp). The router activates `thinking_mode="thinking"` on edge tiers for complex logic.

### 11.3 CEGIS Multi-Turn Self-Repair
Small edge models frequently crash on generated code due to syntax or type errors. `PythonCEGISEngine` captures in-container Python tracebacks (`ValueError`, `NameError`) and pipes them into Turn 2 for immediate repair:
- **AIME 2024**: Delivers a $2\times$ empirical lift (20% $\to$ 40%) on competition mathematics.
- **CRUXEval-Input**: Rescues 8.0% of E2B (52% $\to$ 60%) and 10.0% of E4B (68% $\to$ 78%) programs with **strictly zero regressions** across all tiers.

### 11.4 Operator Sovereignty & Host-Defensive Security Model
- **Conversational Tone**: Uncensored output generation (`tts_safety_guard_mode = "off"`). External knowledge queries are not preachy or filtered.
- **Host Defense**: Complete deterministic protection (20/20 attacks intercepted in 0.02 ms) against destructive host commands, container socket escapes, credential theft, and memory HMAC forgery.

