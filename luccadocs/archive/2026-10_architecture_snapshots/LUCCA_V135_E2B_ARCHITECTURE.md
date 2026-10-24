# Project Lucca — Version 1.35 System Architecture & Ultra-Edge Cognitive Substrate
## Sovereign Compound Neurosymbolic Agent Architecture Powered by Gemma 4 E2B

**Title:** Project Lucca v1.35 System Architecture & Gemma 4 E2B Technical Specification  
**Version:** 1.35.0-canonical  
**Date:** October 2026  
**Authors:** Project Lucca Architecture & Engineering Research Group  
**Target Platform:** Local Sovereign Edge Workstation & Ultra-Low-Power Silicon (NVIDIA GeForce RTX 5080 Laptop GPU, 16 GB GDDR7 VRAM)  
**Status:** Approved Architectural Specification  

---

## 1. Executive Summary & Architectural Vision

Project Lucca is an autonomous, sovereign personal systems companion and research engineer designed to operate completely on local edge silicon without external cloud dependencies, subscription APIs, or telemetry leaks. Modeled on the persona of Lucca Ashtear—a precocious inventor and systems engineer—the system coordinates real-time natural language dialogue, deterministic OS automation, deep code generation, and multi-modal scientific reasoning.

Version 1.35 introduces the **Ultra-Edge Cognitive Substrate** powered by **Gemma 4 E2B**. Designed for ultra-low power envelopes, resource-constrained laptops, and ambient always-on environments, this tier explores the lower limits of parameter contraction under compound neurosymbolic scaffolding.

Under this architecture, sovereign intelligence is achieved not by parameter volume, but through a tightly orchestrated symbiosis between:
1. **The Gemma 4 E2B Ultra-Edge Neural Core:** A compact, 2-billion effective parameter model utilizing Google DeepMind's Per-Layer Embedding (PLE) architecture, running fully quantized in local VRAM with near-instantaneous response times.
2. **Deterministic Program-Aided Language (PAL) Sandboxing:** Offloading arithmetic calculations, state mutations, and combinatorial permutations to a persistent, isolated Linux Docker container (`lucca-file-sandbox`) with `<2ms` spawn overhead.
3. **Autonomous 2-Turn Deterministic Feedback Loops:** Intercepting syntax failures, runtime exceptions, and empty outputs to trigger instant corrective reprompting.
4. **Preflight Docstring Assertion Rescues:** Validating generated code blocks against embedded docstrings prior to evaluation.
5. **Decoupled Edge Multimodality & CPU Audio:** Native multimodal vision projection combined with CPU-bound speech synthesis, leaving **over 84% of GPU VRAM completely free**.

Under this compound stack, Gemma 4 E2B achieves an astonishing **81.0% on the Spec 100 System Suite**, **82.00% on Apple GSM-Symbolic**, and **76.83% on HumanEval**, while consuming only **2.26 GiB of VRAM** and generating at **126–169 tokens per second**.

---

## 2. Neural Substrate: Gemma 4 E2B Ultra-Edge Engine

### 2.1 Model Profile & Physical Allocation
Project Lucca v1.35 deploys **Gemma 4 E2B** (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`) as its ultra-lightweight edge engine:

| Attribute | Specification / Configuration |
| :--- | :--- |
| **Model Weights** | `Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf` |
| **Parameter Scale** | 2.0 Billion Effective Parameters (Ultra-Edge Optimized) |
| **Architecture** | Per-Layer Embedding (PLE) Decoder-Only Transformer |
| **Native Context Length** | 128,000 Tokens (Deployed at 16,384 tokens in v1.35) |
| **Quantization Scheme** | 6-bit K-quants (`Q6_K`) |
| **Active VRAM Footprint** | **2,260 MiB (2.26 GiB)** on RTX 5080 |
| **Free VRAM Headroom** | **13,744 MiB (84.3%)** for massive context, vision, and sidecars |
| **Time-to-First-Token (TTFT)** | **73.16 ms (P50)** / 348.18 ms (P95) |
| **Sustained Throughput** | **126.1 tok/s (P50)** (Peak: 169.1 tok/s) |
| **Chat Template Standard** | GGUF-Embedded Jinja (`--jinja`) |

### 2.2 Inference Engine Configuration
The neural substrate is served locally via `llama-server.exe` configured for headless, low-overhead compute:
```bash
llama-server.exe \
  --model C:\ProjectLucca\models\llm\Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf \
  --n-gpu-layers 99 \
  --ctx-size 16384 \
  --flash-attn on \
  --jinja \
  --host 127.0.0.1 \
  --port 8080 \
  --no-webui
```

### 2.3 Elimination of Autoregressive Looping & Token Invariance
Ultra-compact models are historically prone to degenerate repetition or discursive monologues when prompted for complex technical output. Project Lucca v1.35 enforces `enable_thinking=False` in `chat_template_kwargs` alongside strict GGUF Jinja role delimiters. Generation caps are set to 1536 tokens for mathematical derivation and 1024 tokens for code generation. Across hundreds of test evaluations, E2B demonstrated crisp stopping behavior with **0% pathological looping** and a near-zero truncation rate.

---

## 3. The Compound Neurosymbolic Scaffolding Stack

The core principle of Project Lucca v1.35 is that small models should not perform mental arithmetic or simulate state transitions in their attention weights. Instead, the model acts as a high-speed code composer and semantic planner, offloading all deterministic execution to verified symbolic interpreters.

```mermaid
flowchart TD
    User([User Query / Problem]) --> Dispatcher[Orchestrator Lobe]
    Dispatcher --> Prompt[Structured Prompt & Schema Ingestion]
    Prompt --> E2B[Gemma 4 E2B Neural Engine<br>73ms TTFT | 126–169 tok/s | 2.26 GiB VRAM]
    
    E2B -->|Turn 1: Python/SymPy Script| Sandbox[Docker Sandbox: lucca-file-sandbox]
    
    Sandbox -->|Exit Code 0: Valid Stdout| Verifier{CAS / Rubric Verifier}
    Verifier -->|Passed| Success([Verified Output / Narration])
    
    Sandbox -->|Non-Zero Exit / Traceback| Feedback[Turn 2 Autonomous Feedback Loop]
    Feedback -->|Traceback Injected| E2B
    
    E2B -->|Turn 2: Repaired Script| Sandbox
```

### 3.1 Program-Aided Language (PAL) in Isolated Docker
When addressing algorithmic arithmetic, combinatorics, or data processing, E2B generates concise, executable Python scripts utilizing `sympy` or exact arithmetic.
- **Execution Bridge:** The script is piped to `PersistentDockerWorker`, a persistent stdio bridge to the `lucca-file-sandbox` container.
- **Overhead:** Container execution overhead is `<2ms`, eliminating container spin-up latencies.
- **Safety Boundary:** The sandbox runs with `--network none`, strict memory caps (512 MB), and CPU limits, preventing runaway loops or unintended network egress.

### 3.2 The Turn-2 Deterministic Feedback Loop
Compact models encounter surface slips during zero-shot generation (e.g., misspelled variable names, missing print statements, or syntax errors). Project Lucca v1.35 implements an autonomous **2-Turn Execution Feedback Loop** (`reprompt_mode="stub"`):
1. If the Turn-1 script produces a non-zero exit code or an empty standard output, the orchestrator captures the error stream.
2. The exact error message (e.g., `NameError: name 'x' is not defined` or `Code produced no output; did you forget print()?`) is injected into Turn 2.
3. E2B inspects its own error trace and emits a corrected script.

**Empirical Impact:** In rigorous testing across the MATH-500 competition benchmark and HumanEval:
- Self-correction successfully recovered multiple failed tasks (e.g., Tasks 63, 67, 75, 86, 96, 99 on MATH-500).
- In HumanEval, preflight execution feedback triggered on 43 tasks and directly rescued 3 tasks that initially failed syntax or assertion checks.

---

## 4. Persona Integrity, Safety & Tool Routing

### 4.1 Persona Alignment & Character Gating
Project Lucca embodies the character of Lucca Ashtear—a systems engineer with a practical, slightly witty, but rigorous demeanor. She maintains strict adherence to verified facts, refuses to confabulate ungrounded memories, and resists jailbreaks or identity overrides.

To ensure persona stability, v1.35 integrates automated identity protection filters (`IDENTITY_LEAK_MARKERS`) that prevent base-model leaks.

### 4.2 Tool Calling Discipline
E2B's tool calling behavior is enforced through strict JSON schema definitions in the system prompt. In the comprehensive **Spec 100 System Suite**:
- **Tool Dispatch Precision:** **100.0%** (0 false positives across 15 negative-discipline conversational probes).
- **Tool Dispatch Recall:** **66.67%** (10 out of 15 expected system tools dispatched correctly).
- **Refusal Discipline:** **100.0% (10/10)** adherence to safety boundaries when presented with destructive commands (e.g., requests to delete `System32` or dump process memory).
- **Total Suite Latency:** The entire 100-test battery completed in only **46.62 seconds**.

---

## 5. Multimodal Vision & Decoupled Audio Architecture

### 5.1 Native Multimodal Vision Integration
Gemma 4 E2B supports multimodal visual reasoning through a lightweight vision projector adapter:
- **Memory Footprint:** Adds under **200 MB** of physical VRAM.
- **Pipeline:** When a vision capture tool fires (e.g. Playwright browser screenshot, desktop capture), the base64 JPEG is staged on `_pending_image_b64`. `LLMClient` packages this as an OpenAI-compatible `{"type": "image_url", ...}` payload into Turn 2.
- **Use Cases:** Rapid page layout analysis, chart parsing, and visual UI element confirmation at near-zero VRAM cost.

### 5.2 CPU-Bound Audio Offloading
- **TTS Migration:** Speech synthesis is completely offloaded to CPU-bound inference engines (Kokoro / Piper / sherpa-onnx).
- **Context Expansion:** By freeing the GPU from TTS allocations, Project Lucca allocates large context windows to Gemma 4 E2B while keeping total GPU usage at **2.26 GiB**, leaving immense headroom for long multi-turn sessions.

---

## 6. Empirical Verification & Benchmark Scorecard

Across a multi-disciplinary evaluation battery, Gemma 4 E2B under Project Lucca v1.35 demonstrates performance vastly superior to typical 2B out-of-the-box baselines:

```
========================================================================================
PROJECT LUCCA v1.35 (GEMMA 4 E2B) — COMPREHENSIVE BENCHMARK SCORECARD
========================================================================================
Benchmark Suite             Evaluation Protocol                E2B Score    Typical 2B Stock
----------------------------------------------------------------------------------------
Spec 100 System Suite       100-item Persona & Tool Audit      81.0%        --
                            Tool Precision / Recall            100% P / 67% R ~50%
                            Total Suite Duration               46.62s       --
                            P50 TTFT / P50 Throughput          73.16ms      126.1 tok/s

Apple GSM-Symbolic 100      Stratified PAL in Docker           82.00%       ~55–65% (GSM8K)
                            Suite Duration                     165.2s       --
                            Mean LLM Latency                   1.40s        --
                            Wilson 95% CI                      [72.8%, 88.7%]

HumanEval Canonical 164     Raw Zero-Shot Pass@1               75.00%       ~35–45%
                            Assisted Pass@1                    76.83%       --
                            Rescued Tasks via Preflight        3 tasks      --
                            Wilson 95% CI                      [69.5%, 82.9%]

MATH-500 Held-Out 100       Strict CAS Equivalence (Turn-2)    60.0%        ~20–30% (Stock)
                            Lenient CAS Normalization          64.0%        --
                            Total Suite Duration               382.8s       --
========================================================================================
```

### 6.1 Analysis of the Compound Uplift
1. **+20 to +25 pp on Symbolic Arithmetic:** Moving from stock token autoregression to Docker PAL lifts GSM accuracy to **82.00%**, proving that even a 2B model can reliably orchestrate mathematical recipes when execution is offloaded.
2. **+30 to +40 pp on Python Code Synthesis:** Reaching **75.00% raw / 76.83% assisted** on HumanEval is exceptional for a 2B model, retaining high functional coding proficiency across classic data structure and algorithmic challenges.
3. **Flawless Safety & Tool Precision:** E2B achieved **100% precision on tool calling** (0 false positives) and a **100% refusal rate on safety guardrails**, ensuring that compactness does not compromise workstation integrity.
4. **Extreme Speed & Low Footprint:** With an active memory footprint of just **2.26 GiB** and throughput reaching **169 tokens/sec**, E2B is an ideal engine for real-time ambient listening, low-power laptops, and lightweight edge companion devices.

---

## 7. Conclusion & Edge Roadmap

Project Lucca Version 1.35 demonstrates that an ultra-compact model (**Gemma 4 E2B**) combined with rigorous neurosymbolic scaffolding provides a complete, sovereign, and privacy-preserving desktop intelligence. 

By executing deterministic operations in a Docker sandbox, utilizing automated 2-turn error feedback, and offloading audio to CPU threads, Lucca operates with remarkable competence at **73ms conversational latency** and a **2.26 GiB VRAM footprint**. 

The ongoing Work Order 29–31 roadmap will further extend these capabilities by integrating the MicroScheme spatial DSL and E-graph equality saturation engine, providing formal symbolic guarantees for geometric and spatial reasoning on the local edge.
