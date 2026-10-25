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
   - **dGPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB GDDR7, Blackwell `sm_120`, dedicated compute engine `Disp.A: Off`). Native Windows `llama-server.exe` running `gemma-4-26B-A4B-it-heretic.Q6_K.gguf` (Tier 0 canonical brain; MoE 4B active params, `ngl=99`, `--cpu-moe`, `--moe-cache-mib 6144`, `--load-mode none`, 128K context `ctx=131072`, `--spec-type ngram-mod`, Q8_0 KV cache, Flash Attention, `--mmproj mmproj-gemma-4-26B-A4B-it-BF16.gguf` native vision). `enable_thinking=false` mandatory for companion tiers; thinking reserved for explicit deep reasoning. Dedicated compute mode frees dGPU from desktop DWM allocations.
   - **iGPU**: Intel(R) Graphics (Arrow Lake-HX Xe-LPG) driving Windows desktop display and UI, completely offloading display tasks from the RTX 5080.
   - **Intel NPU**: Intel(R) AI Boost NPU (`PCI\VEN_8086&DEV_AD1D`) accessed natively on Windows 11 via OpenVINO (`device="NPU"`). Workloads: 384-D vector embeddings (`all-MiniLM-L6-v2`, NPU primary with CPU fallback) and the ModernBERT NLI semantic verifier ([`src/lucca/senses/verifier.py`](./src/lucca/senses/verifier.py:60), NPU-eligible but **CPU-default** — measured CPU latency is ~57 ms mean / ~70 ms p95 per pair, which exceeds the 50 ms production timeout; see Paper 03 §4.1). **Never attempt to run NPU workloads inside WSL2 or Docker.**
   - **dGPU audio co-tenant**: Faster-Whisper ASR (`distil-small.en`) runs on the RTX 5080 in CUDA float16 (CPU int8 fallback) — see [`src/lucca/senses/asr.py`](./src/lucca/senses/asr.py:52). VAD is energy-based on CPU ([`src/lucca/senses/vad.py`](./src/lucca/senses/vad.py:10)); Kokoro-82M TTS runs via ONNX Runtime on CPU ([`src/lucca/senses/tts.py`](./src/lucca/senses/tts.py:212)).
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

7. **Comparative Rigor & Modern Benchmark Sourcing (`Rule 05`):**
   - Strictly prohibited from using obsolete 2023–2024 baselines (GPT-4, Claude 3.5 Sonnet, Gemini 1.5, raw MMLU/GSM8K) for comparative claims.
   - Mandatory live sourcing of late-2026 frontier models (Claude Opus 5/5.5, GPT-5.6/6 Astra, Gemini 3.8/4-Argon, DeepSeek-V4-Pro) and modern agentic harnesses (SWE-bench Pro/Verified, GAIA, OSWorld, WebArena, ARC-AGI-2/3, FrontierMath) before writing comparisons.
   - Parity disclosure: strictly separate bare token prediction from test-time compute (CoT) and agentic scaffolding (Z3/SymPy/Docker CEGIS vs OpenHands/Devin/Claude Code).

8. **Agent Governance, Repo Hygiene & Documentation Truthfulness:**
   - **No Superlatives or Unverified Labels:** Never use "Verified" on benchmark rows unless independently reproduced by a third party outside the author's workstation. Use "Author-measured", "Self-measured", or "Unit-tested".
   - **No Modifying Measured Data:** Never alter measured results, raw benchmark logs, or test outcomes to improve documentation. Change explanatory wording and report caveats.
   - **Evidence Citations:** Any PR changing a documented metric must link directly to the source artifact, dataset hash, and execution script.
   - **No Root Scratch Folders:** Never create ad-hoc `scratch_*` folders in repository root. Ephemeral test files belong in the configured artifact scratch directory or gitignored `scratch/`.
   - **No Autonomous Safety Weakening:** Agents are strictly forbidden from weakening promotion gates, disabling sandbox isolation, adding shell binaries to allowlists, or auto-promoting quarantined rules.
   - **AI-Assisted Development Disclosure:** Contributions by AI agents are subject to human review and must be disclosed in pull requests and commit descriptions.

---

## 3. Master Documentation Directory

**Canonical Active Documentation:**
- **Unified System Architecture Specification (v1.45.0 / WO-36)**: [`luccadocs/ARCHITECTURE.md`](./luccadocs/ARCHITECTURE.md) — 4-process topology, 4-tier Gemma 4 substrate (`26B-A4B`, `12B`, `E4B`, `E2B`), three-tier cognitive execution, MicroScheme + Organ A Mereotopology + CEGIS self-repair, cryptographic memory + qualitative Allen temporal retrieval, Two-Cadence Inner Life (`IdlePulse` + `DreamRetrospective`), `CognitiveOutcomeSink`, `ActiveGoalManager`, Constitutional Kernel + Windows 11 WinRT `OcrEngine`, and persistent Docker sandboxing.
- **Documentation Master Index**: [`luccadocs/README.md`](./luccadocs/README.md) — Complete directory map of active specs, subsystem manuals, and archives.
- **Decisions Register**: [`luccadocs/DECISIONS.md`](./luccadocs/DECISIONS.md) — All ratified ADRs (`D-AUD-01` through `D-COG-01`).
- **Model Strategy**: [`luccadocs/MODEL_STRATEGY.md`](./luccadocs/MODEL_STRATEGY.md) — Multi-scale Gemma 4 deployment, dynamic task router, VRAM clamp, and KV-cache architecture.
- **User Guide**: [`luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md`](./luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md) — Complete user guide and capabilities overview.
- **Compound Reasoning Specification**: [`luccadocs/specs/COMPOUND_REASONING_100_SPEC.md`](./luccadocs/specs/COMPOUND_REASONING_100_SPEC.md) — 10-domain 100-probe cognitive benchmark battery (`SPEC-BENCH-100-v1.0`).
- **Experimental Results Ledger**: [`RESULTS.md`](./RESULTS.md) — Full benchmark logs, 3-model factorial ablation matrix, and 98-item robustness table.
- **Research Papers**: [`luccadocs/research/papers/`](./luccadocs/research/papers/) — 2 submission candidates (Paper 06 scaffolding comparisons, Paper 03 provenance-gated memory) and 4 technical reports (TR-01/02/04/05). Status and pre-submission work list in [`luccadocs/research/README.md`](./luccadocs/research/README.md). Do not describe these as peer-reviewed or "peer-review caliber."
- **Release Audit**: [`luccadocs/audit/findings/V1_RELEASE_AUDIT.md`](./luccadocs/audit/findings/V1_RELEASE_AUDIT.md) — Release audit and verification evidence.
- **Audio Concurrency Contract**: [`luccadocs/adr/0009_audio_concurrency_contract.md`](./luccadocs/adr/0009_audio_concurrency_contract.md).

**Historical Archives:**
- Archived specifications and audits into [`luccadocs/archive/`](./luccadocs/archive/).

---

## 4. Key Settled Facts Every Agent Must Know
- **Multi-Scale LLM Substrate**: Served via `llama-server.exe` across 4 validated tiers:
  - **Gemma 4 26B A4B Tier 0** (`gemma-4-26B-A4B-it-heretic.Q6_K.gguf`): MoE (4B active params), `ngl=28`, 32K context (`ctx=32768`), `--spec-type ngram-mod`. Canonical brain for `FULL_LOOP` and deliberation-lane reasoning.
  - **Gemma 4 12B Unified** (`gemma-4-12b-heretic-Q6_K.gguf`): 9,972 MiB VRAM (61.2%), TTFT 286.9 ms, 37.18 tok/s. Companion escalation tier.
  - **Gemma 4 E4B Sovereign Core** (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`): 4,382 MiB VRAM (26.9%), TTFT 86.1 ms, 80.76–103.0 tok/s. Default desktop core.
  - **Gemma 4 E2B Ultra-Edge** (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`): 2,260 MiB VRAM (13.9%), TTFT 73.2 ms, 126.1–169.1 tok/s. Low-power companion.
- **Dynamic Task Router**:
  - $\text{Router}(M, T)$: Direct R0 for 12B; PAL in Docker (P2 @ 2k) for small-model arithmetic; Thinking Mode (R1 @ 6k) for edge competition math (yielding 88.0% strict on E4B vs 73.0% PAL, $p=0.0026$).
- **Cognitive & Academic Verification (`RESULTS.md` & `data/benchmarks/MANIFEST.yaml`)**:
  - Track 1 (`SPEC-BENCH-100-v1.0`, record `spec_bench_100_run3_v1_3`): **91.0% pass rate**, 100.0% path policy compliance, 100.0% epistemic faithfulness.
  - Track 2 (Standard Academic Battery): GSM8K PAL **95.75%** full 1,319 (`gsm8k_pal_full_1319_v1_3`; **100.0%** 30-item micro-suite `gsm8k_pal_micro30_v1_3`), Canonical HumanEval **94.51% raw / 93.90% assisted** paired (`humaneval_canonical_paired_v1_35_6`; **95.73%** zero-shot academic `humaneval_zeroshot_academic_v1_3`), Big-Bench Hard **92.40% (924/1,000)** (`bbh4_bare_1000_v1_3`).
  - Track 3 (Modern Academic Benchmarks): GSM-Symbolic **94.0%** stratified 100-template (`gsm_symbolic_stratified_100_v1_35_6`; **100.0%** v1.3 dev `gsm_symbolic_100_v1_3`), HumanEval-Plus **91.46%–92.07% pass@1** (`humaneval_plus_v1_35_6`), MATH-500 Sealed B4 100 **93.0% strict / 94.0% lenient** on 12B R0 (`math500_b4_sealed_12b_v1_35_6`), Fresh Held-Out 500 **85.80% strict / 90.20% lenient** in v1.35 (`math-v1.35-final-fresh-500`; superseded v1.3 run: 78.60% strict post-hoc / 74.20% initial `math500_fresh_heldout_500_v1_3_0`).
  - Held-Out 100 Multi-Scale Matrix (`math500_heldout100_direct_r0_v1_35_6`): 12B Direct R0: 89.0% [88.8% on 98-item clean]; E4B Thinking R1: 88.0% [87.8% on 98-item clean]; E2B Thinking R1: 81.0% [80.6% on 98-item clean].
- **Output Supervision & Deontic Grounding**:
  - `TruthInReceiptMatcher` with 21 verified action verbs (`delete`, `create`, `modify`, `execute`, `run`, `install`, `remove`, `send`, `upload`, `fetch`, `save`, `write`, `post`, `reboot`, `book`, `place`, `process`, `start`, `close`, `copy`, `move`) and epistemic hedge exemption policy.
  - 70-sentence formal battery (8 categories; P6 broadening): 70/70 passing; live 100-probe evaluation: 0/50 control false alarms.
- **Memory**: SQLite WAL + FTS5 BM25 + `sqlite-vec` in `data/memory.sqlite` with HKDF HMAC-SHA256 read-time tamper verification and persistent SQLite `memory_quarantine` table (`D-MEM-05`). Key persistence via `data/keys/master.key` (`0600`).
- **Regression Test Suite**: **1,243+ passing unit tests** across all subsystems (0 failed; 100% green across all 24 static architectural gates).
- **Sandboxing**: Docker CE inside Ubuntu WSL2 with host fallback disabled (`D-AUD-13`). Unshackled CEGIS code executes inside persistent `lucca-file-sandbox` container via Docker RPC transport with automated `/tmp/lucca_runtime` module synchronization.
- **Process Topology**: Four native host processes + ZeroMQ IPC (`lucca-core`, `lucca-audio`, `lucca-ui`, `llama-server` per ADR-008).
- **Sovereign Cognitive Unification (Work Order 36 / v1.46.5)**:
  - `CognitiveOutcomeSink`: Unifies CEGIS multi-turn synthesis across `PythonCEGISEngine`, `UnshackledCEGISEngine`, and `Orchestrator` with `AffectiveODEMachine` (`EUREKA_DISCOVERY` / `TASK_SUCCESS` / `TOOL_FAILURE`), `ReasoningContext.proof_trace()`, and `EpisodeRecall`.
  - Semantic `UserModel` v2 & Goal-Biased Recall: Hybrid ModernBERT OpenVINO NLI entailment boosting (>0.60) + contradiction rejection + 384-D cosine fallback + `ActiveGoalManager` wired into `HybridRetriever`, `EpisodeRecall`, and `Orchestrator` (`0009_active_goals_and_learning_events.sql`). Preserves Trap 1 & Trap 2.
  - Two-Cadence Inner Life: `IdlePulse` (60s NPU/CPU pass wired with `VerifierWorker` NLI consistency and `distill_contradiction_to_proposition()`) + `DreamRetrospective` (wired with `RuleInducer`, `RuleLifecycleManager`, and shadow replay into `QUARANTINE` per `D-REAS-06`) guided by homeostatic `CoherenceDrive` and `CompetenceDrive`.
  - Constitutional Kernel & Sovereign Sight: Deterministic SHA-256 fingerprint (`constitutional_hash`) bound to `DecisionRecord`, verified epistemic TTS prosody modulation (`CHECKED_FORMALIZATION_AGREED` vs `SPECULATION`), and Windows 11 WinRT `Windows.Media.Ocr.OcrEngine` text extraction (`extract_ocr_from_image`).
  - Neurosymbolic & Verification Upgrades: SymPy `.coeff()` auto-expansion AST rewrite, AIME combinatorics token ceiling (`max_tokens=1536`), `ContainerWorld` implicit room co-presence (`set_room_occupants()`) and `tell()`, relative date temporal extraction, Organ A topological `GridDiff` + expanded spatial AST mutators, `zebra_constraints.gbnf` deterministic Edge Z3 compiler, `SPIKE-A` post-turn NLI receipt entailment in `coherence.py`, `SPIKE-B` `blind_classifier_only` routing mode in `HeuristicRouter`, and BFCL `<tool_fit_check>` guard via `VerifierWorker`.
