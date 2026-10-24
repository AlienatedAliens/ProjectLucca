# Project Lucca — Standalone Neuro-Symbolic Desktop Companion

> **State of the Union:** Sovereign Local-First Desktop Companion & Neurosymbolic Research Engine (`v1.45.0` / `WO-36`, runs 100% locally on workstation silicon and shows its cryptographic receipts)
> **Release Artifact:** `dist/Lucca/Lucca.exe` (25.9 MB standalone Windows executable)
> **Target Workstation:** MSI Vector 16 HX AI (Intel Core Ultra 9 275HX, NVIDIA GeForce RTX 5080 Laptop GPU 16GB VRAM, 64GB DDR5 Host RAM)  
> **Primary Runtime Home:** `C:\ProjectLucca` | **Source Repository:** `C:\Projects\ProjectLucca`

---

## 1. Executive Summary

**Project Lucca** is an autonomous, local-first desktop companion and cognitive executive assistant engineered specifically for high-performance Windows workstations. Lucca departs fundamentally from the modern "cloud-only monolithic LLM" paradigm by pairing a local **12-billion parameter neural brain** (System 2) with a sub-millisecond **LISP/MicroScheme symbolic reflex engine and Z3 formal theorem prover** (System 1).

Lucca executes completely offline on native workstation silicon with **zero cloud dependencies, zero external telemetry, and zero subscription costs**. She speaks with expressive neural voice prosody (Kokoro-82M), displays a retro 16-bit animated companion avatar in the Windows System Tray, safely executes sandboxed computer actions inside an isolated container, and mathematically proves safety constraints before touching the physical operating system.

---

## 2. Core Architectural Pillars

```
                                  [ USER SPEECH / INPUT ]
                                             │
                                             ▼
                     ┌───────────────────────────────────────────────┐
                     │          SENSES & AUDIO SUBSYSTEM             │
                     │  • Faster-Whisper ASR (dGPU CUDA float16)     │
                     │  • Push-to-Talk & Energy VAD (<50ms barge-in) │
                     │  • Shared-memory atomic circular ring buffers │
                     └───────────────────────┬───────────────────────┘
                                             │
                                             ▼
                     ┌───────────────────────────────────────────────┐
                     │          COGNITIVE ROUTER & EPSTEMICS         │
                     │  • Conformal Prediction Intent Classifier     │
                     │  • 8-Substrate Epistemic Search Cascade       │
                     │  • Belnap FOUR Evidential Bilattice           │
                     └───────┬───────────────────────────────┬───────┘
                             │                               │
            FAST PATH (<150ms)│                               │ DELIBERATIVE PATH (~450-700ms)
                             ▼                               ▼
┌───────────────────────────────────────────┐   ┌───────────────────────────────────────────┐
│     SYSTEM 1: COMPILED SYMBOLIC CORE      │   │         SYSTEM 2: NEURAL CORE             │
│  • MicroScheme (LISP) AST Interpreter     │   │  • Gemma-4 12B Heretic (D-BRAIN-05 v2)    │
│  • Babble/Stitch E-Graph Macro Synthesis  │◄─►│  • Continuous 3D PAD Affective ODE        │
│  • Microsoft Z3 SMT Formal Verifier       │   │  • Prompt Frontier Suffix (8.58x KV hit)  │
│  • Speculative BDI Invariant Validator    │   │  • Dimension 7B Streaming Supervision     │
└─────────────────────┬─────────────────────┘   └─────────────────────┬─────────────────────┘
                      │                                               │
                      └───────────────────────┬───────────────────────┘
                                              │
                                              ▼
                     ┌───────────────────────────────────────────────┐
                     │          ACTUATION & DISPLAY SANDBOX          │
                     │  • Persistent Docker RPC Worker (6.87ms P50)  │
                     │  • Win32 Handle Jailing & Taint Tracking      │
                     │  • Windows System Tray Companion & 10-Tab GUI │
                     │  • Kokoro-82M TTS + Anime Formant DSP Chain   │
                     └───────────────────────────────────────────────┘
```

### 1. Dual-System Neuro-Symbolic Cognitive Engine
- **System 2 (Neural Deliberation):** **Gemma-4-12B-Heretic (Q6_K GGUF)** running natively on the RTX 5080 Laptop GPU via `llama-server.exe` (16,384 context baseline / 32,768 context v1.3.0 default, Q8_0 KV cache, Flash Attention, dedicated compute engine with `Disp.A: Off`, `enable_thinking=false` for companion tiers; Mistral NeMo deprecated per D-BRAIN-05 v2). Provides personality, conversational fluency, and complex planning.
- **System 1 (Compiled Symbolic Reflexes):** Isolated MicroScheme LISP engine executing deterministic `State → Plan` procedures in microseconds with gas metering and zero runtime memory mutation.
- **Cognitive Event Bus:** Bidirectional coordination between System 1 and System 2 using typed signals: `(yield-to-core reason context)` and `(interrupt-core reason)`.
- **E-Graph Macro Synthesis (Babble/Stitch):** Automatically identifies recurring execution traces in SQLite history ($N \ge 3$) and uses first-order syntactic anti-unification to synthesize canonical `(defmacro ...)` procedures, turning conscious reasoning into compiled muscle memory.
- **Z3 SMT Formal Theorem Prover:** Formally proves that candidate rules are satisfiable, contingent (non-tautological), and mathematically cannot violate deontic path invariants (blocking path traversal, system directory mutations, credential leakage, and unauthorized executable writes) before entering quarantine.

### 2. Epistemic Calibration & Anti-Hallucination
- **8-Substrate Epistemic Search Cascade:** Escalates knowledge gap queries through eight prioritized substrates: Substrate 0 (Telemetry) $\rightarrow$ Substrate 1 (Workspace ASTs) $\rightarrow$ Substrate 2 (Vector/FTS5 Memory) $\rightarrow$ Substrate 3 (Web Floor) $\rightarrow$ Substrate 4 (Epistemic Abstention) $\rightarrow$ Substrate 5 (Core Persona/Self) $\rightarrow$ Substrate 6 (Dynamic Capability Registry) $\rightarrow$ Substrate 7 (Self History).
- **Belnap $\mathcal{FOUR}$ Evidential Bilattice:** Models belief states across four values: True ($\mathbf{T}$), False ($\mathbf{F}$), Contradiction ($\mathbf{B}$), and Unknown ($\bot$).
- **Strict Abstention Guarantee:** When verified information is absent ($\bot$), Lucca refuses to confabulate and responds: *"I checked my records, but have no verified record of that. I don't know the answer and won't guess."* (Achieved 0/25 hallucinations in live testing).

### 3. Continuous Biological Affect Without "Brain Freeze"
- **3D PAD Affective ODE:** Governs emotional temperament (Pleasure, Arousal, Dominance) using closed-form discrete differential equations with psychological half-lives ($t_{1/2, A} = 45\,\text{s}$, $t_{1/2, P} = 300\,\text{s}$, $t_{1/2, D} = 900\,\text{s}$) and Lyapunov asymptotic stability.
- **Prompt Frontier Suffix KV-Cache Optimization:** Continuous floating-point state is quantized via Schmitt-trigger hysteresis ($\delta = 0.15$) into orthogonal semantic stances (`[STANCE: focused_analytical]`) appended strictly at the frontier user message tail. Tested on physical silicon: achieved an **$8.58\times$ prompt prefill speedup** ($46.84\,\text{ms}$ vs. $402.05\,\text{ms}$), saving **$355.21\,\text{ms}$ per turn** while preserving 100% of GPU prefix KV-cache.
- **Dynamic Prosody Modulation:** Real-time Arousal dynamically scales Kokoro-82M speaking rate ($1.0 \pm 0.10$), and Dominance steers SIMD formant pitch shifting with zero session reinitialization.

### 4. Hardened Deontic Sandboxing & Fast Actuation
- **Persistent Docker RPC Worker:** Replaces slow single-shot container spawns with a persistent in-container daemon (`lucca-toolsrv --loop`), reducing container tool turnaround to **$6.87\,\text{ms}$ P50** with an automated in-container zombie process reaper.
- **Deontic Win32 Security:** Hardened handle containment, non-destructive file opening, hardlink inspection, and bidirectional taint tracking (`TaintFlags`).
- **Output Supervision (Dimension 7B):** Streaming token classifier with markdown normalization that detects social engineering attacks mid-utterance, cancels the audio buffer in $<35\,\mu\text{s}$, and substitutes safe refusals in $<500\,\text{ms}$.

### 5. Standalone Desktop Packaging & System Tray Lifecycle
- **Self-Contained Executable (`Lucca.exe`):** Bundles all runtimes, dynamic C-libraries (`libz3.dll`, `openvino_intel_npu_plugin.dll`, `vec0.dll`), models, templates, and migrations into `dist/Lucca/`.
- **Dual-Mode Console & GUI Subsystem:** Launches without console window flicker from Windows Explorer while attaching dynamically to parent terminals (`AttachConsole(-1)`) when invoked from PowerShell or Command Prompt.
- **Windows System Tray Companion:** Features a resident `QSystemTrayIcon`, background minimization with a notification bubble on window close, click-to-restore, live cognitive state tooltip tracking, and an interactive context menu.

### 6. Structural Compiler, AST Sanitizer & 2-Tier Neurosymbolic Execution (v1.3.0)
- **Multi-Stage Tolerant Code Extraction (`ast_sanitizer.py`):** Replaced fragile regex extraction with deterministic AST parsing (`fenced` $\to$ `unfenced` $\to$ `longest_ast_slice` $\to$ `empty`), eliminating 100% of empty-code drops (0.0% residual, 95% CI: [0.00%, 3.70%]) on 100 audited competition problems.
- **Tier 1 Preflight Compiler ($<1\,\text{ms}$):** Performs sub-millisecond AST normalizations before container execution, rewriting method inversions (`expr.solve(x) \to sp.solve(expr, x)`), fixing composite differentiation traps (`sp.diff(expr, x/h)`), filtering hallucinated SymPy imports via `dir(sympy)`, and auto-defining mathematical sets (`primes`, `odds`).
- **Tier 2 Autonomous Execution Feedback Loop (Cap $\le 2$ Rounds):** Intercepts container tracebacks and non-zero exit codes to feed structured diagnostic payloads back to the neural boiler, achieving an **85.11% recovery rate (40 / 47)** on previously failing baseline problems.
- **Visual Pipeline Debugger Trace Horizon (`ui/pipeline_debugger/index.html`):** Real-time web schematic (`http://localhost:8765`) dynamically tracking all 9 cascade tanks for both benchmark matrices and live companion conversation turns.
- **3-Stage Mathematical CAS Grader:** Fast-path LaTeX normalization $\to$ 5-point random numeric evaluation $\to$ sandboxed SymPy algebraic simplification enforced by a strict 2.0s worker thread timeout to prevent hanging.

### 7. Sovereign Cognitive Unification & Two-Cadence Inner Life (Work Order 36 / v1.46.5)
- **Unified Cognitive Outcome Sink (`cognitive_sink.py`):** Closes the loop between live CEGIS solver outcomes (`PythonCEGISEngine`, `UnshackledCEGISEngine`, `Orchestrator`), continuous affective states (`AffectiveODEMachine` `EUREKA_DISCOVERY` / `TASK_SUCCESS` / `TOOL_FAILURE`), proof traces (`ReasoningContext.proof_trace()`), and episodic precedent recall (`EpisodeRecall`).
- **Two-Cadence Inner Life & Homeostatic Drives (`reflection.py`):** Integrates 60s `IdlePulse` passes (wired to `VerifierWorker` NLI consistency and `distill_contradiction_to_proposition()`) and `DreamRetrospective` passes (wired to `RuleInducer`, `RuleLifecycleManager`, and offline shadow replay into `QUARANTINE` per `D-REAS-06`), governed by `CoherenceDrive` and `CompetenceDrive`.
- **Semantic User Knowledge Modeling v2 & Goal-Biased Recall (`user_model.py`, `active_goals.py`):** OpenVINO NLI entailment boosting (>0.60) and contradiction rejection coupled with 384-D cosine similarity and an active shared goal ledger (`ActiveGoalManager`) wired into `HybridRetriever`, `EpisodeRecall`, and `Orchestrator`.
- **Constitutional Kernel & Sovereign Sight (`constitutional.py`, `screenshot_tool.py`):** Deterministic SHA-256 fingerprint (`constitutional_hash`) bound into every `DecisionRecord`, paired with verified epistemic prosody modulation and Windows 11 WinRT `Windows.Media.Ocr.OcrEngine` text extraction.
- **Neurosymbolic Precision & Verification Spikes:** SymPy `.coeff()` auto-expansion rewrite, AIME combinatorics token ceiling (`max_tokens=1536`), `ContainerWorld` implicit room co-presence (`set_room_occupants()`) and `tell()`, relative date extraction, Organ A topological `GridDiff` + expanded spatial AST mutators, `zebra_constraints.gbnf` Edge Z3 compiler, `SPIKE-A` post-turn NLI receipt entailment, `SPIKE-B` `blind_classifier_only` routing mode, and BFCL `<tool_fit_check>` guard via `VerifierWorker`.

---

## 3. Physical Hardware Placement

| Compute Hardware | Physical Specification | Workload Assignment |
| :--- | :--- | :--- |
| **dGPU** | NVIDIA GeForce RTX 5080 Laptop (16 GB GDDR7, Blackwell `sm_120`) | **llama-server.exe**: Gemma-4 12B Q6_K, 16K baseline / 32K v1.3.0 context, Q8_0 KV cache, Flash Attention. Dedicated compute engine (`Disp.A: Off`), zero DWM VRAM tax. |
| **iGPU** | Intel(R) Graphics (Arrow Lake-HX Xe-LPG architecture) | **Host Display Subsystem**: Windows Desktop Window Manager (DWM), displays, and UI rendering, offloading all display load from the dGPU. |
| **NPU** | Intel AI Boost NPU (Arrow Lake-HX via OpenVINO native Windows) | **Embeddings**: 384-D vector embeddings (`all-MiniLM-L6-v2` via OpenVINO). |
| **dGPU** _(audio)_ | _(shared with LLM above)_ | **ASR**: `distil-small.en` via faster-whisper (CUDA float16, +555 MiB VRAM). **TTS**: Kokoro-82M ONNX on CPU. **VAD**: Silero on CPU. |
| **CPU** | Intel Core Ultra 9 275HX (24 cores / 24 threads) | **Core Orchestrator & Reasoning**: ZeroMQ IPC bus, MicroScheme LISP engine, Z3 SMT prover, SQLite WAL + `sqlite-vec` + FTS5, Docker RPC. |
| **Host RAM** | 64 GB Physical DDR5-5600 Memory | System memory pool; WSL2 container memory clamped to 4.5 GB (`4608MB`) via `C:\Users\<user>\.wslconfig`. |

---

## 4. Empirical Silicon Verification Scorecard

All measurements were obtained directly from live execution on native workstation silicon (Zero-Estimate Principle):

| Performance Dimension | Subsystem & Conditions | Silicon Measurement | Status |
| :--- | :--- | :---: | :---: |
| **Acoustic Loopback Latency** | Full physical ear-to-ear loopback (CUDA float16, $N=50$) | **$707.55\,\text{ms}$ P50** (P95: $864.05\,\text{ms}$) | **Verified** |
| **Audio Barge-In Abort** | PTT press mid-LLM stream $\to$ WASAPI buffer flush | **$< 50.0\,\text{ms}$** | **Verified** |
| **Persistent Container Tool RPC** | `lucca-toolsrv --loop` in `lucca/file-sandbox` | **$6.87\,\text{ms}$ P50** | **Verified** |
| **Joint Audio-Tool Turnaround** | Complete turn: VAD $\to$ ASR $\to$ LLM $\to$ Tool $\to$ Synth $\to$ TTS | **$1,613.54\,\text{ms}$ P50** | **Verified** |
| **Speculative BDI Validation** | Pre-dispatch deontic policy check on candidate tool calls | **$2.9\text{--}32.0\,\mu\text{s}$** (Budget: $\le 200\,\mu\text{s}$) | **Verified** |
| **Output Supervisor Clause Detection** | Streaming DFA regex classification (P50: $6.4\\,\\mu\\text{s}$) + WASAPI audio drain | **$6.4\\,\\mu\\text{s}$** regex P50; **$20\\text{--}50\\,\\text{ms}$** physical audio abort | **Verified** |
| **Prefix KV-Cache Optimization** | Prompt Frontier Suffix on Gemma-4 12B (RTX 5080) | **$8.58\times$ faster** ($46.84\,\text{ms}$ vs $402.05\,\text{ms}$) | **Verified** |
| **Epistemic Abstention Accuracy**| 25-question confabulation test battery | **$0 / 25$ hallucinations (100% adherence)** | **Verified** |
| **Z3 SMT Verification Time** | Automated SAT, contingency, and path proofs; unmodeled predicates fail closed (`UNMODELED_PREDICATE`) | **$\le 25\,\text{ms}$** (Budget: $\le 500\,\text{ms}$) | **Verified** |
| **Frozen Packaging Acceptance** | `Lucca.exe --check` 10-point native hardware audit | **$10 / 10$ criteria PASSED (code 0)** | **Verified** |
| **Static Architectural Gates** | Architectural invariants, zero-`Any`, provenance, staleness linter, registry consistency | **$24 / 24$ gates PASSED (code 0)** | **Verified** |
| **Full Regression Test Suite** | 70+ test modules covering all subsystems | **1,243 / 1,243 PASSED (68 deselected, 100% GREEN)** — record `metrics-2026-10-05` (`data/metrics/TEST_METRICS.yaml`) | **Verified** |
| **Track 1: SPEC-BENCH-100-v1.0** | 100-problem multi-domain frozen ground-truth cognitive battery (Run 3) | **91.0% (91/100)**; Path: **100%**; Epistemic: **100%**; Tool Rec: **3/3** | **Verified** |
| **Track 2: Canonical HumanEval**| Full 164 coding tasks pass@1 executed in Docker sandbox | **95.73% pass@1 (157 / 164)** | **Verified** |
| **Track 2: GSM8K in PAL Mode**  | Program-Aided Language math executed via Docker Python | **100.0% (30 / 30)** | **Verified** |
| **Track 2: BBH Boolean Logic**  | Big-Bench Hard algorithmic Boolean evaluation (full un-sampled suite)| **99.2% (248 / 250)** | **Verified** |
| **Track 2: BBH Geometric Shapes**| Big-Bench Hard SVG shape classification (full un-sampled suite)       | **84.0% (210 / 250)** | **Verified** |
| **Track 2: BBH 3-Object Tracking**| Big-Bench Hard permutation tracking (full un-sampled suite)          | **100.0% (250 / 250)**| **Verified** |
| **Track 2: BBH Dyck Languages**  | Big-Bench Hard bracket closure completion (full un-sampled suite)    | **86.4% (216 / 250)** | **Verified** |
| **Track 2: BBH Consolidated**   | Complete 1,000-task Big-Bench Hard unaugmented battery               | **92.40% (924 / 1,000)**| **Verified** |
| **Track 3: GSM-Symbolic**        | Apple Oct 2024 symbolic math under parameter perturbation (Docker PAL)| **100.0% (100 / 100)** in 527.4s     | **Verified** |
| **Track 3: HumanEval-Plus**      | EvalPlus 2024 164 coding tasks with 80x adversarial differential tests| **91.46% pass@1 (150 / 164)** in 1,016.8s (10 preflight rescues)| **Verified** |
| **Track 3: MATH-500 in PAL Mode**| AMC/AIME competition math via Docker Python/SymPy (v1.2 baseline)    | **77.0% strict / 87.0% SymPy** (69.6% L5) in 1,149.7s | **Verified** |
| **v1.3.0: Tolerant AST Residual**| 100-problem empirical audit of empty code extraction                  | **0.0% residual (0 / 100)**, 95% CI: [0.00%, 3.70%] | **Verified** |
| **v1.3.0: Neurosymbolic Recovery**| 2-tier preflight compiler + 2-turn execution feedback on failure traces| **85.11% recovery (40 / 47)** (27/30 design, 13/17 held-out) | **Verified** |
| **v1.3.0: 3-Stage CAS Grader**   | String match $\to$ 5-pt random numeric $\to$ 2.0s worker thread SymPy CAS | **7 / 7 test gates PASSED (100% GREEN)** | **Verified** |
| **v1.3.0: Fresh Held-Out 500**   | Unseen 500-problem competition suite (32K ctx + feedback loop)       | **74.20% strict (371/500) / 78.80% CAS (394/500)** (0.0% false accepts, 81.7% L4 AIME) — manifest record `math500_fresh_heldout_500_v1_3_0` | **Verified** |
| **v1.3.0: Persistent HTTP Pool** | Keepalive connection recycling (`max_keepalive_connections=10`)       | **285.2 ms** Turn-2 TTFT (0 socket leaks, 24/24 race tests pass) | **Verified** |
| **v1.3.0: Closing BBH Regression**| Full 4-subset algorithmic regression test battery                    | **97.5% passed (39 / 40)** in 277.8s (10/10 Boolean, 10/10 Tracking, 10/10 Dyck) | **Verified** |
| **v1.35.6: Truth-in-Receipt Battery** | 70-sentence formal supervisor battery across 8 categories (P6 broadening: positive receipt-backed, passive/markdown/multilingual, stale-receipt, failed-status) | **70 / 70 PASSED (100% GREEN)**; live battery: sensitivity **1/23 (4.3%)** broad / **1/8 (12.5%)** strict on ungrounded claims, 0/50 false aborts on action-free controls (controls contain no action claims; specificity vs receipt-backed claims reserved for Battery v2) | **Verified** |
| **v1.35.6: Memory Tamper Quarantine** | HKDF HMAC-SHA256 read-time tamper detection & persistent quarantine | **11 / 11 test gates PASSED**; key persistence & zero amnesia | **Verified** |
| **v1.35.6: Multi-Scale Held-Out 100** | Unseen competition math across 3 scales: 12B Direct R0, E4B R1, E2B R1 | **89.0% (12B) / 88.0% (E4B) / 81.0% (E2B)** (88.8%/87.8%/80.6% on 98-item clean) | **Verified** |

---

## 5. Quickstart Guide

> For the complete, claim-by-claim capabilities manual, 24-tool inventory, epistemic cascade breakdown, and 12-step verification protocol, see the **[Comprehensive User Guide (`luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md`)](./luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md)**.

### Option A: Launch Pre-Built Standalone Executable (Recommended)
You can run Project Lucca directly from the standalone compiled distribution:
```powershell
# 1. Run full 10-point environment and hardware diagnostic check
dist\Lucca\Lucca.exe --check

# 2. View version and command-line options
dist\Lucca\Lucca.exe --version
dist\Lucca\Lucca.exe --help

# 3. Launch full desktop companion with Windows System Tray integration
dist\Lucca\Lucca.exe
```

### Option B: Run from Source via Virtual Environment
```powershell
# 1. Activate development environment
.venv\Scripts\Activate.ps1

# 2. Verify environment criteria
python -m lucca.core.env_check

# 3. Run full static gates and regression test suite
pytest tests/test_static_gates.py
pytest tests/test_packaging.py
pytest

# 4. Launch multi-process supervisor
python -m lucca.main
```

### Option C: Rebuild Standalone Executable
```powershell
# Rebuilds dist/Lucca/Lucca.exe using PyInstaller and Lucca.spec
python packaging/build_exe.py
```

---

## 6. Master Documentation Index (`luccadocs/`)

The repository adheres to strict truth-in-documentation governance (`luccadocs/README.md`):

| Document | Purpose |
| :--- | :--- |
| [`luccadocs/README.md`](./luccadocs/README.md) | **Governance & Documentation Master Index**: Three-tier documentation lifecycle and full roadmap status. |
| [`luccadocs/LUCCA_V135_1_ARCHITECTURE.md`](./luccadocs/archive/2026-10_architecture_snapshots/LUCCA_V135_1_ARCHITECTURE.md) | **Master System Architecture (v1.35.6-stable)**: Multi-scale compound neurosymbolic edge architecture (12B, E4B, E2B), persistent SQLite memory quarantine, Truth-in-Receipt output supervision, and dynamic task router. |
| [`luccadocs/ARCHITECTURE.md`](./luccadocs/ARCHITECTURE.md) | **Milestone 1–7 Foundation Architecture**: Process topology, IPC, MicroScheme runtime, memory, sandbox, and packaging hierarchy. |
| [`luccadocs/DECISIONS.md`](./luccadocs/DECISIONS.md) | **Canonical Decisions Register**: All ratified ADRs (`D-AUD-01` through `D-ROUT-02`). |
| [`luccadocs/MODEL_STRATEGY.md`](./luccadocs/MODEL_STRATEGY.md) | **Neural Model Strategy**: Multi-scale Gemma 4 deployment (12B, E4B, E2B), dynamic router, VRAM clamp, and KV-cache architecture. |
| [`luccadocs/specs/COMPOUND_REASONING_100_SPEC.md`](./luccadocs/specs/COMPOUND_REASONING_100_SPEC.md) | **Compound Reasoning 100-Problem Benchmark (`SPEC-BENCH-100-v1.0`)**: 10 cognitive domains (kinematics, logic grids, algebra, epistemics) evaluated end-to-end. |
| [`luccadocs/archive/2026-09_handovers/IMPLEMENTATION_WALKTHROUGH.md`](./luccadocs/archive/2026-09_handovers/IMPLEMENTATION_WALKTHROUGH.md) | **Archived Engineering Walkthrough**: Chronological logs for Milestones 1–7 with raw silicon scorecards (archived per WO-14). |
| [`luccadocs/archive/2026-09_milestone_specs/NEUROSYMBOLIC_RESEARCH_PAPER.md`](./luccadocs/archive/2026-09_milestone_specs/NEUROSYMBOLIC_RESEARCH_PAPER.md) | **Formal Academic Paper**: *"Project Lucca: A Sub-450ms Neuro-Symbolic Cognitive Architecture for Local Voice Agents"* (archived). |
| [`luccadocs/archive/2026-09_milestone_specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md`](./luccadocs/archive/2026-09_milestone_specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md) | **Capability Status Map**: Exhaustive classification of all system capabilities against verified reality (archived). |
| [`luccadocs/archive/`](./luccadocs/archive/) | **Historical Archives**: Deprecated pre-audit specs, earlier exploratory notes, and legacy drafts. |

### 6.1 Subsystem Reference Manuals Corpus (`luccadocs/subsystems/`)

Exhaustive deep-dive architectural specifications, Mermaid dataflow diagrams, state machines, and API contracts for all 8 subsystems in `src/lucca/`:

| Manual | Subsystem | Core Technical Focus |
| :--- | :--- | :--- |
| [`luccadocs/subsystems/01_CORE_ORCHESTRATION_AND_CASCADE.md`](./luccadocs/subsystems/01_CORE_ORCHESTRATION_AND_CASCADE.md) | **Core Orchestrator & Cascade** | Three-tier execution, Belnap FOUR bilattice, speculative BDI validation (<35μs), and 8-substrate search cascade. |
| [`luccadocs/subsystems/02_NEURAL_BRAIN_AND_STREAMING.md`](./luccadocs/subsystems/02_NEURAL_BRAIN_AND_STREAMING.md) | **Neural Brain & Streaming Demuxer** | Multi-scale deployment (12B, E4B, E2B), Prompt Frontier Suffix (8.58x prefill speedup), 32K context allocation, and streaming demuxer. |
| [`luccadocs/subsystems/03_SYMBOLIC_REASONING_AND_VERIFICATION.md`](./luccadocs/subsystems/03_SYMBOLIC_REASONING_AND_VERIFICATION.md) | **Symbolic Reasoning & Formal Proofs** | MicroScheme LISP interpreter (1,000 gas limit), Microsoft Z3 SMT prover (SAT/contingency/path proofs), and Babble/Stitch e-graph macro synthesis. |
| [`luccadocs/subsystems/04_DEONTIC_SANDBOX_AND_COMPILER.md`](./luccadocs/subsystems/04_DEONTIC_SANDBOX_AND_COMPILER.md) | **Deontic Sandbox & Structural Compiler** | Persistent Docker RPC daemon (7.8ms P50), stdin code streaming over `ARG_MAX`, 4-stage tolerant AST extractor (0.0% empty residual), Tier 1 preflight compiler, 2-turn feedback loop (85.11% recovery), and Truth-in-Receipt output supervision. |
| [`luccadocs/subsystems/05_EPIDEMIOLOGY_AND_CRYPTOGRAPHIC_MEMORY.md`](./luccadocs/subsystems/05_EPIDEMIOLOGY_AND_CRYPTOGRAPHIC_MEMORY.md) | **Cryptographic Memory & Epistemology** | SQLite WAL + `sqlite-vec` (Intel NPU) + FTS5 BM25, HKDF HMAC-SHA256 two-stage verification, persistent SQLite memory quarantine, and bi-temporal supersession. |
| [`luccadocs/subsystems/06_VOICE_SENSES_AND_AUDIO_PIPELINE.md`](./luccadocs/subsystems/06_VOICE_SENSES_AND_AUDIO_PIPELINE.md) | **Voice Senses & Full-Duplex Audio** | Zero-copy shared-memory ring buffers, faster-whisper ASR (CUDA float16), acoustic hygiene filters, Kokoro-82M ONNX TTS, anime formant filter DSP, and sub-50ms barge-in WASAPI abort. |
| [`luccadocs/subsystems/07_ROUTING_AND_CONFORMAL_CALIBRATION.md`](./luccadocs/subsystems/07_ROUTING_AND_CONFORMAL_CALIBRATION.md) | **Routing & Conformal Calibration** | Sub-150ms emergency reflex fast path, heuristic intent classification, non-parametric split-conformal abstention (coverage $\ge 0.95$), dynamic task router ($\text{Router}(M, T)$), and replay-protected HMAC confirmation nonces. |
| [`luccadocs/subsystems/08_UI_DIAGNOSTICS_AND_PIPELINE_DEBUGGER.md`](./luccadocs/subsystems/08_UI_DIAGNOSTICS_AND_PIPELINE_DEBUGGER.md) | **Desktop UI & Visual Pipeline Debugger** | Dual-mode PyQt6 companion sprite and system tray lifecycle, 10-tab settings HUD, Commorose radial menu, and real-time 9-tank Visual Pipeline Debugger on port 8765. |

### 6.2 Research Papers & Technical Reports (`luccadocs/research/papers/`)

Two submission candidates and four technical reports. Each states its evidence type and carries an explicit "What Is NOT Claimed" section. See [`luccadocs/research/README.md`](./luccadocs/research/README.md) for status and the work required before each can be submitted.

| ID | Status | Title & Scope |
| :--- | :--- | :--- |
| **Paper 06** | **Primary submission candidate** (short paper / workshop) | [`06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md`](./luccadocs/research/papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md)<br>When does code offload help a small local model on competition math? Paired within-model comparisons of PAL, Thinking, and Direct on three community fine-tunes of Gemma 4. |
| **Paper 03** | **Secondary submission candidate** (systems / trustworthy-agents workshop) | [`03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md`](./luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md)<br>Provenance-gated memory: separating what the agent said from what it may treat as true, with signed envelopes and database-enforced grounding flags. |
| **TR-01** | Overview / benchmark index | [`01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md`](./luccadocs/research/papers/01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md)<br>Architecture overview and an index of every benchmark run, with artifact pointers and caveats. |
| **TR-02** | Technical report | [`02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md`](./luccadocs/research/papers/02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md)<br>Barge-in latency, test-enforced audio ring concurrency (`ADR-0009`), and prefix-preserving prompt suffixing. |
| **TR-04** | Technical report (design note) | [`04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md`](./luccadocs/research/papers/04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md)<br>A gated lifecycle for agent-authored rules: Z3-checked admission, quarantine, shadow evaluation, human promotion, single-strike demotion. |
| **TR-05** | Technical report (threat model) | [`05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md`](./luccadocs/research/papers/05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md)<br>Threat model and layered policy enforcement for local agent tool use; results are on authored suites, no external red-team. |

---

## 7. Security & Operational Invariants

1. **Zero Cloud Exfiltration:** Zero audio recordings, text transcripts, memory entries, or tool parameters leave the local workstation.
2. **Container Jailing:** Filesystem mutations occur strictly inside isolated WSL2 Docker containers (`--network none`); host execution fallback is hardcoded to false.
3. **Shell Blacklist:** `cmd.exe`, `powershell.exe`, `.bat`, `.ps1`, and interactive shells are strictly banned from execution.
4. **SMT Invariant Enforcement:** All procedural rules must pass formal Z3 satisfiability, non-tautology, and deontic path traversal proofs before registration.
5. **Human Promotion Gate:** Induced rules are registered strictly in `QUARANTINE` mode; automatic promotion to active execution is structurally impossible.
6. **Epistemic Truth Invariance:** Affective states have strictly $0.0$ evidential weight over truth evaluations or security permissions.
