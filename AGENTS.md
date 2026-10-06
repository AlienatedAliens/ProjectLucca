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
- **System Architecture Specification (v1.35.6-stable)**: [`docs/LUCCA_V135_1_ARCHITECTURE.md`](./docs/LUCCA_V135_1_ARCHITECTURE.md) — Multi-scale compound edge architecture (12B, E4B, E2B), persistent SQLite memory quarantine, Truth-in-Receipt output supervision, and dynamic task router.
- **Foundation System Architecture (v2.0.0)**: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — Process topology, IPC, cognitive tiers, memory, rules, and security for Milestones 1–7.
- **Decisions Register**: [`docs/DECISIONS.md`](./docs/DECISIONS.md) — All ratified ADRs (`D-AUD-01` through `D-ROUT-02`).
- **Model Strategy**: [`docs/MODEL_STRATEGY.md`](./docs/MODEL_STRATEGY.md) — Multi-scale Gemma 4 deployment, dynamic task router, VRAM clamp, and KV-cache architecture.
- **User Guide**: [`docs/USER_GUIDE_WHAT_LUCCA_DOES.md`](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md) — Complete user guide and capabilities overview.
- **Compound Reasoning Specification**: [`docs/specs/COMPOUND_REASONING_100_SPEC.md`](./docs/specs/COMPOUND_REASONING_100_SPEC.md) — 10-domain 100-probe cognitive benchmark battery (`SPEC-BENCH-100-v1.0`).
- **Experimental Results Ledger**: [`RESULTS.md`](./RESULTS.md) — Full benchmark logs, 3-model factorial ablation matrix, and 98-item robustness table.
- **Research Papers**: [`docs/research/papers/`](./docs/research/papers/) — 6 peer-review caliber papers, including Paper 6 on small-model compound scaling (`06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md`).
- **Release Audit**: [`docs/audit/findings/V1_RELEASE_AUDIT.md`](./docs/audit/findings/V1_RELEASE_AUDIT.md) — Release audit and verification evidence.
- **Audio Concurrency Contract**: [`docs/adr/0009_audio_concurrency_contract.md`](./docs/adr/0009_audio_concurrency_contract.md).

**Historical Archives:**
- Archived specifications and audits into [`docs/archive/`](./docs/archive/).

---

## 4. Key Settled Facts Every Agent Must Know
- **Multi-Scale LLM Substrate**: Served via `llama-server.exe` across 3 validated edge tiers:
  - **Gemma 4 12B Unified** (`gemma-4-12b-heretic-Q6_K.gguf`): 9,972 MiB VRAM (61.2%), TTFT 286.9 ms, 37.18 tok/s. Used for complex symbolic escalation.
  - **Gemma 4 E4B Sovereign Core** (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`): 4,382 MiB VRAM (26.9%), TTFT 86.1 ms, 80.76–103.0 tok/s. Default desktop core.
  - **Gemma 4 E2B Ultra-Edge** (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`): 2,260 MiB VRAM (13.9%), TTFT 73.2 ms, 126.1–169.1 tok/s. Low-power companion.
- **Dynamic Task Router**:
  - $\text{Router}(M, T)$: Direct R0 for 12B; PAL in Docker (P2 @ 2k) for small-model arithmetic; Thinking Mode (R1 @ 6k) for edge competition math (yielding 88.0% strict on E4B vs 73.0% PAL, $p=0.0026$).
- **Cognitive & Academic Verification**: Validated under Three-Track Empirical Battery + Multi-Scale Held-Out Matrix:
  - Track 1 (`SPEC-BENCH-100-v1.0`): **91.0% pass rate**, 100.0% path policy compliance, 100.0% epistemic faithfulness.
  - Track 2 (Standard Academic Battery): GSM8K PAL **100.0%**, Canonical HumanEval **95.73% pass@1**, Big-Bench Hard **92.40% (924/1,000)**.
  - Track 3 (Modern Academic Benchmarks): GSM-Symbolic **100.0%**, HumanEval-Plus **91.46% pass@1**, MATH-500 Fresh Held-Out 500 **74.20% strict / 78.80% SymPy CAS** (81.7% Level 4 AIME; manifest record `math500_fresh_heldout_500_v1_3_0`).
  - Held-Out 100 Multi-Scale Matrix: 12B Direct R0: 89.0% [88.8% on 98-item clean]; E4B Thinking R1: 88.0% [87.8% on 98-item clean]; E2B Thinking R1: 81.0% [80.6% on 98-item clean].
- **Output Supervision & Deontic Grounding**:
  - `TruthInReceiptMatcher` with 21 verified action verbs (`delete`, `create`, `modify`, `execute`, `run`, `install`, `remove`, `send`, `upload`, `fetch`, `save`, `write`, `post`, `reboot`, `book`, `place`, `process`, `start`, `close`, `copy`, `move`) and epistemic hedge exemption policy.
  - 70-sentence formal battery (8 categories; P6 broadening): 70/70 passing; live 100-probe evaluation: 0/50 control false alarms.
- **Memory**: SQLite WAL + FTS5 BM25 + `sqlite-vec` in `data/memory.sqlite` with HKDF HMAC-SHA256 read-time tamper verification and persistent SQLite `memory_quarantine` table (`D-MEM-05`). Key persistence via `data/keys/master.key` (`0600`).
- **Regression Test Suite**: **1,243 passing unit tests** across all subsystems (0 failed, 68 deselected; record `metrics-2026-10-05` in `data/metrics/TEST_METRICS.yaml`).
- **Sandboxing**: Docker CE inside Ubuntu WSL2 with host fallback disabled (`D-AUD-13`).
- **Process Topology**: Four native host processes + ZeroMQ IPC (`lucca-core`, `lucca-audio`, `lucca-ui`, `llama-server` per ADR-008).
