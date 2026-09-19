# Project Lucca — Local Desktop Companion Agent

> **Canonical System Specification & Workspace Guide**  
> Target Host: MSI Vector 16 HX AI (Core Ultra 9 275HX / Arrow Lake-HX, RTX 5080 16GB VRAM, 16GB System RAM)  
> Primary Runtime Root: `C:\ProjectLucca` | Development Repository: `C:\Projects\ProjectLucca`

---

## 1. Overview

**Project Lucca** is a local-first, autonomous desktop companion and cognitive executive assistant engineered specifically for high-performance Windows workstations. Lucca combines sub-millisecond symbolic procedural reflexes with local 12-billion-parameter neural reasoning to deliver an authentic, voice-driven companion experience with zero cloud dependencies.

### Core Architecture Highlights
- **Primary Brain (`D-BRAIN-05`)**: **Mistral NeMo 12B Instruct Abliterated (Q6_K GGUF)** served by native Windows `llama-server.exe` with `--chat-template mistral-v3`, 16,384 context size, Q8_0 KV cache, flash attention, and a 12.5 GB (12,800 MB) resident VRAM clamp (leaving >5.2 GB headroom on the 16 GB RTX 5080 Laptop GPU for desktop DWM and applications).
- **Three-Tier Execution Architecture (`D-ARCH-05`)**:
  - `REFLEX`: Immediate canned response (<150ms) strictly confined to emergency safety commands (`shutdown`, `pause`, `mute`, `stop`, `halt`).
  - `ACT_THEN_NARRATE`: Standard action rules execute deterministically in the sandbox, then prompt NeMo 12B to narrate results in Lucca's companion voice, eliminating robotic canned phrases.
  - `FULL_LOOP`: Open-ended reasoning and multi-step tool calls (up to $M=3$ rounds) with intermediate spoken verbal thinking cues (`D-BRAIN-03`) and strict grounded narration contracts (`D-BRAIN-04`).
- **Compiled Symbolic Reasoning (MicroScheme LISP)**:
  - Pure `State → Plan` functions in an isolated Scheme DSL with gas metering and zero runtime memory mutation.
  - Typed entity accessors (`entity-str`, `entity-int`, `entity-num`) enforcing schema validation (`D-SEC-04`).
  - Compile-time hygienic macro expansion system (`D-REAS-05`) with hard bounds (`MAX_MACRO_DEPTH = 8`, `MAX_MACRO_STEPS = 64`).
  - Autonomous Safe Rule Induction (`D-REAS-06`) mining recurring SQLite patterns ($N \ge 3$) and registering candidate rules exclusively in `QUARANTINE` mode.
  - Skill-as-Tool Exposure (`D-REAS-04`): Promoted active rules dynamically surface as OpenAI-compatible tool definitions (`skill_<rule_id>`), allowing System 2 to invoke compiled System 1 skills.
- **Cryptographic Associative Memory (`D-MEM-03`, `D-ARCH-06`)**:
  - SQLite WAL + FTS5 BM25 + `sqlite-vec` 384-D vector embeddings (`all-MiniLM-L6-v2` on Intel NPU/CPU).
  - Scaled 2,048-token working memory quota (~8,192 chars) with multi-factor prioritized truncation: `USER_EXPLICIT` $\rightarrow$ `TOOL_VERIFIED` $\rightarrow$ `TOOL_CONTENT_UNTRUSTED`.
  - Fast-Path Context Synchronization into LLM history to eliminate multi-turn conversational amnesia.
- **Sandboxing & Async Tasks (`D-AUD-13`, `D-SEC-04`, `D-SAND-03`)**:
  - Containerized WSL2/Docker CE sandbox with strict egress filtering and host execution fallback disabled by default.
  - Strict Pydantic argument schemas for all tool dispatches (`LaunchAppArgs`, `FetchUrlArgs`, etc.).
  - Long Asynchronous Task Protocol (`AsyncTaskManager`) tracking background jobs with unique ULID IDs, cooperative cancellation, and sandboxed query tools (`get_task_status`, `list_tasks`, `cancel_task`).
- **Real-Time Audio Pipeline**: Push-to-Talk (PTT) with energy VAD trimming, `faster-whisper` transcription on CPU/NPU, Kokoro-82M ONNX TTS (24 kHz `genki_heroine` voice), anime formant DSP chain, and instant barge-in cancellation via atomic shared memory ring buffers (`D-AUD-16`, `ADR-0009`).

---

## 2. Master Documentation Index (`docs/`)

| File | Status | Purpose |
| :--- | :---: | :--- |
| [`docs/DECISIONS.md`](./docs/DECISIONS.md) | **Canonical** | Complete register of all 25 ratified Architectural Decision Records (`D-AUD-01` through `D-EVAL-01`). **Start here.** |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | **Canonical** | Master System Architecture specification (v0.4.0): process topology, IPC, cognitive tiers, memory, rules, and security boundaries. |
| [`docs/MODEL_STRATEGY.md`](./docs/MODEL_STRATEGY.md) | **Canonical** | Model strategy specification: cascade pipeline, Mistral NeMo 12B Abliterated deployment, VRAM budgets, and prompt architecture. |
| [`docs/AUDIT_REMEDIATION_LOG.md`](./docs/AUDIT_REMEDIATION_LOG.md) | **Canonical** | Complete resolution log for architectural findings F-ARCH-001..008 and procedural upgrade Proposals A–K. |
| [`docs/adr/0009_audio_concurrency_contract.md`](./docs/adr/0009_audio_concurrency_contract.md) | **Canonical** | Audio concurrency, ring buffer mutexes, per-stream abort registry, and barge-in contracts. |
| [`docs/archive/2026-09-17_pre_phase4_audit/`](./docs/archive/2026-09-17_pre_phase4_audit/) | *Historical* | Archived pre-Phase-4 specification documents (00–14, original build briefs, and pre-audit research notes). |

---

## 3. Hardware Compute Placement

| Hardware Substrate | Physical Specification | Assigned System Workload |
| :--- | :--- | :--- |
| **dGPU** | NVIDIA GeForce RTX 5080 Laptop (16 GB GDDR7, Blackwell `sm_120`) | **llama-server.exe**: Mistral NeMo 12B Q6_K, 16K context, Q8_0 KV cache, flash attention ($\le 12.5\text{ GB}$ clamp). |
| **NPU** | Intel AI Boost NPU (Arrow Lake-HX via OpenVINO native Windows) | **Audio & Embeddings**: Kokoro TTS (INT8), Silero VAD / Faster-Whisper ASR, 384-D vector embeddings (`all-MiniLM-L6-v2`). |
| **CPU** | Intel Core Ultra 9 275HX (24 cores / 32 threads) | **Core Orchestrator**: ZeroMQ IPC bus, MicroScheme LISP engine, SQLite WAL + `sqlite-vec` + FTS5, LightGBM/XGBoost. |
| **Host RAM** | 16 GB Physical Host Memory | System memory pool; WSL2 container memory clamped to 4.5 GB (`4608MB`) via `.wslconfig`. |

---

## 4. Quickstart & Verification

### 1. Environment Verification
Verify that GPU VRAM, Intel NPU, WSL2 clamp, Docker CE, and model weights meet system criteria:
```powershell
uv run python -m lucca.core.env_check
```
*Expected output: All 7 criteria `[PASS]` and `[SUCCESS] All system environment criteria passed!`*

### 2. Run Test Suite & Static Gates
Execute automated regression and typing verification:
```powershell
# Run zero-Any static typing gates (D-AUD-01)
uv run pytest tests/test_static_gates.py

# Run Frozen Evaluation Regression Suite (110 golden traces across Reflex, Act-Then-Narrate, Full-Loop)
uv run pytest tests/test_frozen_regression_harness.py

# Run full procedural test suite
uv run pytest tests/test_sandbox_schemas.py tests/test_scheme_typed_accessors.py tests/test_fast_path_sync.py tests/test_memory_retrieval_prioritization.py tests/test_batch2_execution.py tests/test_scheme_macros.py tests/test_rule_induction.py tests/test_async_tasks.py tests/test_frozen_regression_harness.py tests/test_prompt_builder.py tests/test_sandbox.py tests/test_router.py
```

### 3. Start Project Lucca
```powershell
uv run python -m lucca.main
```

---

## 5. Security & Privacy Guarantees

1. **Zero Cloud Exfiltration**: Zero audio recordings, text transcripts, memory entries, or tool parameters leave the local workstation.
2. **Container Boundary**: File reading and writing occur strictly within isolated Docker WSL2 containers; host execution fallback is disabled by default (`D-AUD-13`).
3. **Absolute Shell Ban**: `cmd.exe` and `powershell.exe` are strictly blacklisted from application launching (`D-AUD-10`).
4. **Cryptographic Provenance**: Memories are signed with HMAC/Ed25519 envelopes; freeform LLM narration can never enter persistent memory without an explicit user act (`D-AUD-09`).
