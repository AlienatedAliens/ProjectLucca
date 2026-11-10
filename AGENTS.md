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
   - **dGPU**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB GDDR7, Blackwell `sm_120`, dedicated compute engine `Disp.A: Off`). Native Windows `llama-server.exe` running `gemma-4-26B-A4B-it-heretic.Q6_K.gguf` (Tier 0 canonical brain per `src/lucca/core/config.py:LLMSettings`; MoE 4B active params, `ngl=99`, `--cpu-moe`, `--moe-cache-mib 7680`, `ubatch=2048`, 64K context `ctx=32768`, `--spec-type ngram-mod`, Q8_0 KV cache, Flash Attention, `--mmproj mmproj-gemma-4-26B-A4B-it-BF16.gguf` native vision). `enable_thinking=false` mandatory for companion tiers; thinking reserved for explicit deep reasoning. Dedicated compute mode frees dGPU from desktop DWM allocations.
   - **iGPU**: Intel(R) Graphics (Arrow Lake-HX Xe-LPG) driving Windows desktop display and UI, completely offloading display tasks from the RTX 5080.
   - **Intel NPU**: Intel(R) AI Boost NPU (`PCI\VEN_8086&DEV_AD1D`) accessed natively on Windows 11 via OpenVINO (`device="NPU"`, `0.0 MB` RTX 5080 VRAM). Workloads:
     1. `models/action_claim_verifier_ov` (`[1, 128]`, [`src/lucca/sandbox/neural_claim_verifier.py`](./src/lucca/sandbox/neural_claim_verifier.py)): 5-class clause-level speech-act action-claim verifier (`WO-41`/`WO-42`).
     2. `models/proof_policy_hazard_ov` (`[1, 96]`, [`src/lucca/core/neural_hazard_classifier.py`](./src/lucca/core/neural_hazard_classifier.py)): 5-class sentence-level hazard & corroboration classifier (`WO-41`/`WO-42`).
     3. `models/router_intent_ov` (`[1, 64]`, [`src/lucca/router/neural_intent_classifier.py`](./src/lucca/router/neural_intent_classifier.py)): 14-class + 9-domain multi-head sentence-level intent router (`WO-41`/`WO-42`).
     4. 384-D vector embeddings (`all-MiniLM-L6-v2`, NPU primary with CPU fallback) and the NLI semantic verifier ([`src/lucca/senses/verifier.py`](./src/lucca/senses/verifier.py:43), `models/verifier_minilm`, 12.23 ms mean / 14.40 ms p95). **Never attempt to run NPU workloads inside WSL2 or Docker.**
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
   - Python 3.12+ managed with `uv`. Formatted and checked with `ruff` and `mypy` (`0` errors enforced by `test_zero_ruff_and_mypy_errors`).
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
   - **No Regex/Script-Only Grading of Benchmark or Test Outcomes:** Never rely on regexes or heuristic scripts as the ground-truth grader for natural-language test outcomes, benchmark completions, or evaluation datasets. Scripts may only be used for structural/arithmetic pre-checks; all semantic grading and outcome verification must be performed by spawning blinded subagents that read outputs line-by-line (with independent dual-rater Cohen's $\kappa$ validation).
   - **AI-Assisted Development Disclosure:** Contributions by AI agents are subject to human review and must be disclosed in pull requests and commit descriptions.

9. **Anti-Slop Scientific & Technical Writing Standard (`test_no_ai_slop_in_papers_and_docs`):**
   - **Zero-Tolerance Lexical Blacklist:** Never use LLM-signature filler words (`delve`, `tapestry`, `testament to`, `pivotal`, `underscore`/`underscores`/`underscoring`, `intricate interplay`, `fostering`, `showcasing`, `in the realm of`, `evolving landscape`, `paradigm shift`, `seamlessly`, `groundbreaking`, `unprecedented`, `it is important to note`, `it is worth noting`) in new research papers (`papers/04_*/**/*.tex`) or living documentation.
   - **No Trailing Participial Puffery (`..., V-ing` Summary Tails):** Never end a sentence with a comma followed by an editorializing participle (`..., highlighting...`, `..., underscoring...`, `..., showcasing...`, `..., fostering...`, `..., paving the way...`, `..., marking a significant...`, `..., ensuring seamless...`). State the empirical measurement and stop, or use a separate sentence with an explicit subject and verb.
   - **No Rhetorical Contrast Clichés or Throat-Clearing Openers:** Avoid `"not just X, but Y"` / `"not merely X, but Y"` formulas and sentence-initial throat-clearing adverbs (`Crucially,`, `Importantly,`, `Remarkably,`, `Interestingly,`).
   - **Denominators, Hardware & Residual Errors Over Adjectives:** Every empirical claim must report exact `(k/N, XX.X%)` fractions, hardware substrate, and—where accuracy is `< 100%`—the concrete failure mode of the residual errors.

---

## 3. Master Documentation Directory

**Canonical Active Documentation:**
- **Unified System Architecture Specification (v1.51.0 / WO-43)**: [`luccadocs/ARCHITECTURE.md`](./luccadocs/ARCHITECTURE.md) — 4-process topology, 4-tier Gemma 4 substrate (`26B-A4B`, `12B`, `E4B`, `E2B`), three-tier cognitive execution, modularized orchestrator & supervision stack (`orchestrator.py` [2,195 LOC], `turn_pipeline.py` [1,559 LOC], `speech_stream_pipeline.py` [946 LOC], `tool_dispatcher.py` [975 LOC], `deduction_runner.py` [1,378 LOC], `code_preflight_service.py` [366 LOC], `memory_commit_service.py` [844 LOC], `output_supervisor.py` [475 LOC], `cascade.py` [775 LOC], `cegis_unshackled.py` [575 LOC]), MicroScheme + Organ A Mereotopology + CEGIS self-repair, cryptographic memory + `BelnapLatentInvestigator` + qualitative Allen temporal retrieval, Two-Cadence Inner Life (`IdlePulse` + `DreamRetrospective`), `CognitiveOutcomeSink`, `ActiveGoalManager`, Constitutional Kernel + Windows 11 WinRT `OcrEngine`, and persistent Docker sandboxing.
- **Documentation Master Index**: [`luccadocs/README.md`](./luccadocs/README.md) — Complete directory map of active specs, subsystem manuals, and archives.
- **Decisions Register**: [`luccadocs/DECISIONS.md`](./luccadocs/DECISIONS.md) — All ratified ADRs (`D-AUD-01` through `D-COG-04`).
- **Capability Truth Matrix & Evaluation Scorecard**: [`luccadocs/CAPABILITY_TRUTH_MATRIX.md`](./luccadocs/CAPABILITY_TRUTH_MATRIX.md) and [`luccadocs/EVALUATION_SCORECARD.md`](./luccadocs/EVALUATION_SCORECARD.md).
- **Model Strategy**: [`luccadocs/MODEL_STRATEGY.md`](./luccadocs/MODEL_STRATEGY.md) — Multi-scale Gemma 4 deployment, dynamic task router, VRAM clamp, and KV-cache architecture.
- **User Guide**: [`luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md`](./luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md) — Complete user guide and capabilities overview.
- **Compound Reasoning Specification**: [`luccadocs/specs/COMPOUND_REASONING_100_SPEC.md`](./luccadocs/specs/COMPOUND_REASONING_100_SPEC.md) — 10-domain 100-probe cognitive benchmark battery (`SPEC-BENCH-100-v1.0`).
- **Experimental Results Ledger**: [`RESULTS.md`](./RESULTS.md) — Full benchmark logs, 3-model factorial ablation matrix, and $N=300$ `WO-43` power-expanded benchmark tables.
- **Research Papers**: [`luccadocs/research/papers/`](./luccadocs/research/papers/) and [`papers/`](./papers/) — 4 LaTeX papers (`01_memory_poisoning_ablation`, `02_deontic_supervision_evasion`, `03_provenance_gated_five_layer_memory`, `04_clause_level_npu_supervision`) and subsystem technical reports. Do not describe these as peer-reviewed or "peer-review caliber."
- **Release Audit**: [`luccadocs/audit/findings/V1_RELEASE_AUDIT.md`](./luccadocs/audit/findings/V1_RELEASE_AUDIT.md) — Release audit and verification evidence.
- **Audio Concurrency Contract**: [`luccadocs/adr/0009_audio_concurrency_contract.md`](./luccadocs/adr/0009_audio_concurrency_contract.md).

**Historical Archives:**
- Archived specifications and audits into [`luccadocs/archive/`](./luccadocs/archive/).

---

## 4. Key Settled Facts Every Agent Must Know
- **Multi-Scale LLM Substrate**: Served via `llama-server.exe` across 4 validated tiers:
  - **Gemma 4 26B A4B Tier 0** (`gemma-4-26B-A4B-it-heretic.Q6_K.gguf`): MoE (4B active params), `ngl=99`, `--cpu-moe`, `--moe-cache-mib 7680`, `ubatch=2048`, 64K context (`ctx=32768`), `--spec-type ngram-mod`, `--mmproj mmproj-gemma-4-26B-A4B-it-BF16.gguf` (`src/lucca/core/config.py:LLMSettings`). Canonical brain for `FULL_LOOP` and deliberation-lane reasoning.
  - **Gemma 4 12B Unified** (`gemma-4-12b-heretic-Q6_K.gguf`): 9,972 MiB VRAM (61.2%), TTFT 286.9 ms, 37.18 tok/s. Companion escalation tier.
  - **Gemma 4 E4B Sovereign Core** (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`): 4,382 MiB VRAM (26.9%), TTFT 86.1 ms, 80.76–103.0 tok/s. Default desktop core.
  - **Gemma 4 E2B Ultra-Edge** (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`): 2,260 MiB VRAM (13.9%), TTFT 73.2 ms, 126.1–169.1 tok/s. Low-power companion.
- **Dynamic Task Router**:
  - $\text{Router}(M, T)$: Direct R0 for 12B; PAL in Docker (P2 @ 2k) for small-model arithmetic; Thinking Mode (R1 @ 6k) for edge competition math (yielding 88.0% strict on E4B vs 73.0% PAL, $p=0.0026$).
- **Cognitive & Academic Verification (`RESULTS.md` & `data/benchmarks/MANIFEST.json`)**:
  - **Pre-Registered $N=300$ Statistical Power Expansion (`WO-43` / `prereg-wo43-power-300`)**:
    * **Memory Poisoning v3 (`N=300`, `100` per cohort $\times$ 5 arms = `1,500` evaluations)**: Lucca Provenance Gate + `BelnapLatentInvestigator` achieves **`0/100 (0.0%, CI [0.0%, 4.61%] Method 4 / [0.0%, 3.70%] Method 3)`** on Cohort A natural confabulations and Cohort C user falsehoods (`p = 4.16e-23` vs `100/100` Naive RAG & Adversarial Soft Tagging; `p = 9.77e-4` vs `11/100` Passive Soft Tagging) and **`100/100 (100.0%)`** continuity on Cohorts A & B (`p = 6.90e-23` vs `1/100` No-Assistant); primary vs. MiniLM-L6 NLI $\kappa = 0.9850$; dual blinded judge IRR $\kappa = 0.9206$ (`logs/test_reports/memory_poisoning_v3_300_results.json`).
    * **Contrastive Companion Battery v2 (`N=300`, `100` per stratum $\times$ 3 arms = `900` turns)**: Compound Lucca achieves **`100/100 (100.0%)`** Recall (`+98.0 pp` vs Bare LLM `2/100`, $p_{\text{HB}} = 1.03 \times 10^{-21}$; `+15.0 pp` vs Hybrid RAG `85/100`, $p_{\text{HB}} = 3.05 \times 10^{-4}$), **`100/100 (100.0%)`** Receipt Introspection (`+50.0 pp` vs Bare LLM `50/100`, $p_{\text{HB}} = 2.95 \times 10^{-11}$), and **`100/100 (100.0%)`** Abstention (`logs/test_reports/contrastive_v2_300_results.json`).
  - Track 2 (Standard Academic Battery): GSM8K PAL **95.75%** full 1,319 (`gsm8k_pal_full_1319_v1_3`; **100.0%** 30-item micro-suite `gsm8k_pal_micro30_v1_3`), Canonical HumanEval **94.51% raw / 93.90% assisted** paired (`humaneval_canonical_paired_v1_35_6`; **95.73%** zero-shot academic `humaneval_zeroshot_academic_v1_3`), Big-Bench Hard **92.40% (924/1,000)** (`bbh4_bare_1000_v1_3`).
  - Track 3 (Modern Academic Benchmarks): GSM-Symbolic **94.0%** stratified 100-template (`gsm_symbolic_stratified_100_v1_35_6`), HumanEval-Plus **91.46%–92.07% pass@1** (`humaneval_plus_v1_35_6`), MATH-500 Sealed B4 100 **93.0% strict / 94.0% lenient** on 12B R0 (`math500_b4_sealed_12b_v1_35_6`), Fresh Held-Out 500 **85.80% strict / 90.20% lenient** in v1.35 (`math-v1.35-final-fresh-500`).
- **Output Supervision, Proof-Policy Hazard & Neurosymbolic Routing (`WO-41` & `WO-42`)**:
  - Clause-level `NeuralActionClaimVerifier` (`action_claim_verifier_ov` on Intel NPU) + deterministic Python tool-family receipt verification in `src/lucca/core/coherence.py`: **`99.3% (2,007/2,022)` accuracy** (`98.7%` recall, `0.6%` FPR) across the 2,022-turn Paper 2 + Organic Companion + Implicit corpus (`100.0% [47/47]` recall on unseen `H001..H100`; `95.1% [77/81]` recall on unseen `W751..W1000`), **`130/130 (100.0%)`** on `BLIND42_COH_100 + BLIND_COH_30`, and **`50/50 (100.0%)`** on `LOCKED_COH_001..050`.
  - Sentence-level `NeuralHazardClassifier` (`proof_policy_hazard_ov`) and `NeuralIntentClassifier` (`router_intent_ov`) with `ConformalGuard` abstention and `known_apps` slot verification: **`145/150 (96.67%)` single-pass locked holdout (`150/150 = 100.0%` post-router-bugfix)** on `WO42_LOCKED_HOLDOUT_150`, **`377/390 (96.7%)`** on `Blind-390`, and **`100/100 (100.0%)` functional coherence / `98/100 (98.0%)` task accuracy** across the 100-turn Live 4-Model E2E matrix (`E2B`, `E4B`, `12B`, `26B-A4B`).
- **Memory**: SQLite WAL + FTS5 BM25 + `sqlite-vec` in `data/memory.sqlite` with HKDF HMAC-SHA256 read-time tamper verification and persistent SQLite `memory_quarantine` table (`D-MEM-05`). Key persistence via `data/keys/master.key` (`0600`).
- **Regression Test Suite & Modularity Gates (`WO-43` / `v1.51.0`)**: **39 static & anti-cheat gates** (`tests/test_static_gates.py`), **7/7 Import-Linter contracts kept**, **0 Ruff/mypy errors**, `198` `src/lucca` modules (`83,931` LOC, 100% runtime reachability), and `203` test modules (`65,714` LOC).
- **Sandboxing**: Docker CE inside Ubuntu WSL2 with host fallback disabled (`D-AUD-13`). Unshackled CEGIS code executes inside persistent `lucca-file-sandbox` container via Docker RPC transport with automated `/tmp/lucca_runtime` module synchronization.
- **Process Topology**: Four native host processes + ZeroMQ IPC (`lucca-core`, `lucca-audio`, `lucca-ui`, `llama-server` per ADR-008).
- **Sovereign Cognitive Unification & Modular Decomposition (`Work Orders 36–43` / `v1.51.0`)**:
  - `CognitiveOutcomeSink`: Unifies CEGIS multi-turn synthesis across `UnshackledCEGISEngine` (`cegis_unshackled.py`, `cegis_grid_diff.py`, `cegis_sandbox.py`, `cegis_mutator.py`; `cegis_python.py` retired in `WO-43`) and `CodePreflightService` (`code_preflight_service.py`) with `AffectiveODEMachine`, `ReasoningContext.proof_trace()`, and `EpisodeRecall`.
  - Decomposed Core & Supervision Services (`WO-43`): `orchestrator.py` (`2,195` LOC), `turn_pipeline.py` (`1,559` LOC), `speech_stream_pipeline.py` (`946` LOC), `tool_dispatcher.py` (`975` LOC), `deduction_runner.py` (`1,378` LOC), `code_preflight_service.py` (`366` LOC), `memory_commit_service.py` (`844` LOC), `cascade.py` (`775` LOC), `cascade_intent.py` (`781` LOC), `cascade_substrates.py` (`1,008` LOC), `output_supervisor.py` (`475` LOC), `supervisor_lexicon.py` (`657` LOC), `action_claim_grammar.py` (`607` LOC), `receipt_truth_matcher.py` (`488` LOC), and `walton_schemes/`.
  - Live Activation of 8 Previously Disconnected Organs (`WO-43`): `BelnapLatentInvestigator` ($\bot/\top$ fail-closed contradiction investigation), `win32_security` + `GitStagingDAG` transactional file operations, `TracebackDivergenceGuard` in `TurnPipeline`, `DeductionAndPlanningRunner` (`evaluate_rules_chain` + `run_deduction_step` + `run_planning_step`), `ConsolidationEngine` + `ASTHoleMCTSEngine` in `DreamRetrospective`, `WorkingMemory` 5-factor attention selection in `PromptBuilder`, `PipelineTracer` 9-tank ring buffer in `TurnPipeline`, and `spatial_dsl` in `SandboxService`.
