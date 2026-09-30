# Project Lucca — Antigravity Workspace Guidelines & Operational Rules

## 1. Project Overview & Role
You are operating inside the **Project Lucca** repository (`C:\projects\ProjectLucca`, runtime root: `C:\ProjectLucca`).
Lucca is an autonomous, local-first, sandboxed desktop companion with real-time push-to-talk voice, symbolic procedural reasoning (MicroScheme), three-tier execution architecture, and provenance-gated long-term memory.

## 2. Hard Invariants & Non-Negotiables

1. **Never Promote Freeform LLM Narration into Memory:**
   - Any memory commit must carry an authentic cryptographic envelope signed by an authorized domain signer (`UserSpeechSigner` for `USER_EXPLICIT`, `DerivedFactSigner` for `USER_DERIVED`, `ToolResultSigner` for `TOOL_VERIFIED` / `ASSISTANT_ACTION`, `LispAssertionSigner` for `LISP_ASSERTION`, `AssistantUtteranceSigner` for `ASSISTANT_UTTERANCE` / `ASSISTANT_BELIEF`, or `CoherenceBreachSigner` for `COHERENCE_BREACH`).
   - `TOOL_CONTENT_UNTRUSTED` (unverified file/web bodies) is never memory-eligible without explicit user action.
   - `LLM_NARRATION` is strictly rejected by the `ProvenanceGate`; there is no signer for it (`ADR-006`).

2. **Strict Hardware Budget Discipline:**
   - **dGPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB GDDR7, Blackwell `sm_120`, dedicated compute engine `Disp.A: Off`). Native Windows `llama-server.exe` running `gemma-4-12b-heretic-Q6_K.gguf` (`D-BRAIN-05` v2; `enable_thinking=false` mandatory for companion tiers, thinking reserved for explicit deep reasoning) with 16K context baseline / 32K context v1.3.0 default (`src/lucca/core/config.py`), Q8_0 KV cache, and Flash Attention. Dedicated compute mode frees dGPU from desktop DWM allocations.
   - **iGPU**: Intel(R) Graphics (Arrow Lake-HX Xe-LPG) driving Windows desktop display and UI, completely offloading display tasks from the RTX 5080.
   - **Intel NPU**: Intel(R) AI Boost NPU (`PCI\VEN_8086&DEV_AD1D`) accessed natively on Windows 11 via OpenVINO (`device="NPU"`). Workloads: Kokoro TTS (INT8), Silero VAD / Faster-Whisper ASR, and 384-D vector embeddings (`all-MiniLM-L6-v2`). **Never attempt to run NPU workloads inside WSL2 or Docker.**
   - **System RAM**: 64 GB DDR5-5600 shared pool. WSL2 memory clamped to 4.5 GB (`4608MB`) via `.wslconfig`.
   - **CPU**: Intel Core Ultra 9 275HX (24 cores / 24 threads). Hosts Orchestrator, MicroScheme LISP engine, SQLite WAL + `sqlite-vec` + FTS5, and tree models (LightGBM/XGBoost on CPU, never on NPU).

3. **Three-Tier Execution Architecture (`D-ARCH-05`):**
   - **`REFLEX`**: Strictly restricted to critical emergency/safety commands (`shutdown`, `pause`, `mute`, `stop`, `halt`) via `EMERGENCY_REFLEX_PATTERN`. Bypasses neural inference and speaks canned confirmation in $<150\text{ms}$.
   - **`ACT_THEN_NARRATE`**: Standard procedural rules execute deterministically in the sandbox, then prompt the companion brain (Gemma-4 12B) to narrate results in Lucca's companion voice without robotic canned responses.
   - **`FULL_LOOP`**: Open-ended conversation and multi-step tool calls with convergence-based tool loop (runaway cap M=8), intermediate verbal thinking cues (`D-BRAIN-03`), and strict grounded narration contracts (`D-BRAIN-04`).

4. **Symbolic Rule Engine & Safe Induction:**
   - **Pure Plans**: MicroScheme rules are pure `State → Plan` functions with gas metering (1,000 gas limit) and zero global mutation.
   - **Typed Accessors (`D-SEC-04`)**: Rules use typed accessors (`entity-str`, `entity-int`, `entity-num`) enforcing schema validation before tool dispatch.
   - **Bounded Macro System (`D-REAS-05`)**: Compile-time macro expansion enforces `MAX_MACRO_DEPTH = 8` and `MAX_MACRO_STEPS = 64`. Macros cannot shadow primitive operators.
   - **Quarantine Invariant (`D-REAS-06`)**: Induced rules from SQLite history ($N \ge 3$) are registered **strictly into `QUARANTINE` mode**. Automatic promotion to `ACTIVE` is prohibited. Promotion requires 5 distinct shadow clusters with 0 errors and explicit operator approval via `lucca-admin`.

5. **Sandboxed Action Execution & Async Protocol:**
   - Direct host execution fallback is disabled by default (`use_direct_fallback = False` per `D-AUD-13`); tool operations run inside Docker CE in WSL2.
   - Strict Pydantic argument schemas (`LaunchAppArgs`, `FetchUrlArgs`, etc.) validate all tool dispatches (`D-SEC-04`).
   - Long background tasks run asynchronously under `AsyncTaskManager` with unique ULID task IDs (`D-SAND-03`).
   - Absolute shell ban: `cmd.exe` and `powershell.exe` are strictly blacklisted from application launching (`D-AUD-10`).

6. **Code Quality & Typing Gates:**
   - Python 3.12+ managed with `uv`. Formatted and checked with `ruff`.
   - **Zero `Any` Invariant (`D-AUD-01`)**: Strictly typed interfaces; verified by `tests/test_static_gates.py`.
   - Pydantic v2 schemas for all cross-boundary IPC and data contracts (`src/lucca/core/schemas.py`).

---

## 3. Master Documentation Directory

**Canonical Active Documentation:**
- **Decisions Register**: [`docs/DECISIONS.md`](./docs/DECISIONS.md) — All 25 ratified ADRs (`D-AUD-01` through `D-EVAL-01`).
- **Master System Architecture**: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) (v2.0.0) — Process topology, IPC, cognitive tiers, memory, rules, and security.
- **Model Strategy**: [`docs/MODEL_STRATEGY.md`](./docs/MODEL_STRATEGY.md) (v2.0.0) — Cascade pipeline, Gemma-4 12B deployment and prompt architecture.
- **User Guide**: [`docs/USER_GUIDE_WHAT_LUCCA_DOES.md`](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md) — Complete user guide and capabilities overview.
- **Compound Reasoning Specification**: [`docs/specs/COMPOUND_REASONING_100_SPEC.md`](./docs/specs/COMPOUND_REASONING_100_SPEC.md) — 10-domain 100-probe cognitive benchmark battery (`SPEC-BENCH-100-v1.0`).
- **Action Log & V2 Backlog**: [`docs/V2_ACTION_LOG.md`](./docs/V2_ACTION_LOG.md) and [`docs/V2_BACKLOG.md`](./docs/V2_BACKLOG.md).
- **Capability Roadmap**: [`docs/specs/STUDIO_CAPABILITY_ROADMAP.md`](./docs/specs/STUDIO_CAPABILITY_ROADMAP.md) — Studio taxonomy and capability ladder.
- **Release Audit**: [`docs/audit/findings/V1_RELEASE_AUDIT.md`](./docs/audit/findings/V1_RELEASE_AUDIT.md) — Release audit and verification evidence.
- **Audio Concurrency Contract**: [`docs/adr/0009_audio_concurrency_contract.md`](./docs/adr/0009_audio_concurrency_contract.md).

**Historical Archives:**
- Archived specifications and audits into [`docs/archive/`](./docs/archive/).

---

## 4. Key Settled Facts Every Agent Must Know
- **LLM**: Native Windows `llama-server.exe` running `gemma-4-12b-heretic-Q6_K.gguf` with stock llama.cpp (≥ b11026), `--jinja` and GGUF-embedded chat template, `enable_thinking=false` mandatory for companion tiers, 16,384 context default, Q8_0 KV cache, flash attention, and 12.5 GB (12,800 MB) resident VRAM clamp (`D-BRAIN-05` v2). (Control parameter ablation model: `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` at ~4B effective params; NeMo deprecated and pinned for rollback).
- **Cognitive & Academic Verification**: Validated under Three-Track Empirical Battery:
  - Track 1 (`SPEC-BENCH-100-v1.0`): **91.0% pass rate**, 100.0% path policy compliance, 100.0% epistemic faithfulness.
  - Track 2 (Standard Academic Battery): GSM8K PAL **100.0%**, Canonical HumanEval 164 tasks **95.73% pass@1**, Big-Bench Hard (Full 1,000 Tasks) **92.40% (924/1,000)**: Boolean **99.2%**, Geometry **84.0%**, Tracking **100.0%**, Dyck **86.4%**.
  - Track 3 (Modern 2024-2025 Academic Benchmarks): GSM-Symbolic **100.0% (100/100)** in 527.4s, HumanEval-Plus **91.46% pass@1 (150/164)** in 1,016.8s (10 preflight rescues), MATH-500 PAL **77.0% strict / 87.0% SymPy** (69.6% L5, 1,149.7s).
- **ASR**: Faster-Whisper on CPU/NPU runs on every turn to produce ground-truth text transcripts.
- **Memory**: SQLite WAL + FTS5 BM25 + `sqlite-vec` in `data/memory.sqlite` with 2,048-token quota and multi-factor prioritization (`D-MEM-03`). Fast-path context sync preserves multi-turn memory (`D-ARCH-06`). (Chroma retired).
- **Sandboxing**: Docker CE inside Ubuntu WSL2 with host fallback disabled (`D-AUD-13`).
- **Process Topology**: Four native host processes + ZeroMQ IPC (`lucca-core`, `lucca-audio`, `lucca-ui`, `llama-server` per ADR-008).
