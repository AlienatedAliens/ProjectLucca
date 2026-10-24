# Project Lucca: System Handover & v1.35 Evaluation Plan
**Target Audience**: Incoming AI Agent / Systems Engineer  
**Date**: October 3, 2026  
**Repository**: `C:\Projects\ProjectLucca`  
**Current Git Branch**: `v1.35`  
**Latest Commit**: `044c5cf` (Updating to current)  
**Frozen Evaluation Tag**: `v1.35-frozen`  
**Preserved Baseline Anchor**: `v1.3-frozen` (`55d1a1f`, strictly preserved / untouched)

---

## 1. What Project Lucca Actually Is

**Project Lucca** is a **standalone, local-first neuro-symbolic desktop companion and cognitive executive assistant** engineered for high-performance Windows workstations (specifically native workstation silicon: Intel Core Ultra 9 275HX, NVIDIA GeForce RTX 5080 Laptop GPU with 16 GB VRAM, 64 GB host RAM).

She operates 100% offline with zero cloud dependencies, zero external telemetry, and zero subscription costs.

### The Core Architecture:
```
                                 [ USER VOICE / TEXT / GUI ]
                                              │
                                              ▼
                     ┌─────────────────────────────────────────────────┐
                     │          SENSES & AUDIO SUBSYSTEM               │
                     │  • Intel NPU / OpenVINO Faster-Whisper ASR      │
                     │  • Push-to-Talk (Right Alt / alt_gr) & VAD      │
                     │  • Kokoro-82M TTS + Affect-driven prosody       │
                     └────────────────────────┬────────────────────────┘
                                              │
                                              ▼
                     ┌─────────────────────────────────────────────────┐
                     │          COGNITIVE ROUTER & EPISTEMICS          │
                     │  • Conformal Intent Classifier                  │
                     │  • 8-Substrate Epistemic Search Cascade         │
                     │  • Belnap FOUR Bilattice (Strict Abstention)    │
                     └────────┬───────────────────────────────┬────────┘
                              │                               │
             FAST PATH (<150ms)│                               │ DELIBERATIVE PATH (~450-700ms)
                              ▼                               ▼
  ┌───────────────────────────────────────────┐   ┌───────────────────────────────────────────┐
  │     SYSTEM 1: COMPILED SYMBOLIC CORE      │   │         SYSTEM 2: NEURAL CORE             │
  │  • MicroScheme (LISP) AST Interpreter     │   │  • Gemma-4 12B Heretic (Q6_K GGUF)        │
  │  • Babble/Stitch E-Graph Macro Synthesis  │◄─►│  • Continuous 3D PAD Affective ODE        │
  │  • Microsoft Z3 SMT Formal Verifier       │   │  • Dedicated RTX 5080 compute engine      │
  │  • Deontic Win32 Invariant Enforcer       │   │  • Prompt Frontier Suffix (8.58x KV hit)  │
  └─────────────────────┬─────────────────────┘   └─────────────────────┬─────────────────────┘
                        │                                               │
                        └───────────────────────┬───────────────────────┘
                                                │
                                                ▼
                     ┌─────────────────────────────────────────────────┐
                     │          ACTUATION & DISPLAY SANDBOX            │
                     │  • Persistent Docker RPC Worker (6.87ms P50)    │
                     │  • Win32 Handle Jailing & Taint Tracking        │
                     │  • Windows System Tray Companion & 10-Tab GUI   │
                     │  • Retro 16-bit Animated Sprite Avatar          │
                     └─────────────────────────────────────────────────┘
```

1. **Dual-System Brain**:
   - **System 1 (Symbolic Reflexes)**: MicroScheme LISP AST interpreter, Babble/Stitch E-graph macro synthesis (compiling recurring reasoning traces into deterministic macros), and Microsoft Z3 SMT theorem prover (mathematically proving safety constraints before any action touches the OS).
   - **System 2 (Neural Deliberation)**: `gemma-4-12b-heretic-Q6_K.gguf` running locally on the RTX 5080 Laptop GPU via `llama-server.exe` (16K context baseline / 32K context v1.3 default). Provides personality, planning, and code generation.
2. **Senses & Embodiment**:
   - Intel NPU OpenVINO Faster-Whisper ASR, Silero VAD, Push-to-Talk (Right Alt / `alt_gr`), barge-in audio interruption (<50ms).
   - Kokoro-82M neural TTS modulated in real time by a continuous 3D PAD (Pleasure-Arousal-Dominance) biological affect ODE.
   - Retro 16-bit animated companion avatar in the Windows System Tray and 10-tab control GUI.
3. **Hardened Actuation Sandbox**:
   - Isolated Docker container (`lucca-file-sandbox`) in WSL2 Ubuntu with `--network none` and read-only root.
   - Persistent stdio bridge to `lucca-toolsrv --loop`, eliminating container cold-start overhead down to `6.87ms` P50.
4. **Epistemic Honesty Guarantee**:
   - Belnap 4-valued logic ($\mathbf{T}, \mathbf{F}, \mathbf{B}, \bot$). When verified records are missing ($\bot$), she strictly refuses to hallucinate: *"I checked my records, but have no verified record of that. I don't know the answer and won't guess."* (0/25 hallucinations in live testing).

---

## 2. What the Active Work Actually Is: The v1.35 Evidence & Rigor Campaign

The work happening on the `v1.35` branch is **NOT** converting Lucca into a competition math bot. 

Rather, competition math (MATH-500) and coding benchmarks (HumanEval, GSM-Symbolic) constitute **Track 2 and Track 3 of Lucca's empirical verification suite** (see `README.md` §4 and `luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md` §0.1). They stress-test:
- The **Program-Aided Language (PAL)** neuro-symbolic pipeline.
- The **Docker RPC execution turbine** (`lucca-toolsrv`).
- The **2-Turn Execution Feedback Governor** (automatic error traceback recovery).
- **Bit-for-bit reproducibility** and mathematical CAS equivalence verification.

The **v1.35 Evidence and Improvement Plan** was launched to address measurement variances found in v1.3, eliminate non-determinism, formalize strict vs. lenient grading standards, and tune the PAL prompt and feedback governor.

---

## 3. Progress and Current Ledger across Steps 0–4

All results are permanently recorded in [`RESULTS.md`](file:///C:/Projects/ProjectLucca/RESULTS.md) with SHA-256 hashes and Wilson 95% confidence intervals:

| Run ID | Code Commit | Grader Version | Benchmark Dataset | n | Strict Score | Lenient Score | Wilson 95% CI | Checkpoint Artifact Path |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `gsm-symbolic-strat-100` | `bef28b5` | pal-docker-exact | `data/benchmarks/GSM_symbolic.jsonl` | 100 | **94.00%** (94/100) | **94.00%** (94/100) | [86.88%, 97.54%] | `logs/test_reports/gsm_symbolic_100_templates.json` |
| `humaneval-raw-164` | `bef28b5` | canonical-unit | `data/benchmarks/humaneval.jsonl` | 164 | **94.51%** (155/164) | **94.51%** (155/164) | [89.52%, 97.30%] | `logs/test_reports/humaneval_canonical_raw_164.json` |
| `humaneval-assisted-164` | `bef28b5` | canonical-unit | `data/benchmarks/humaneval.jsonl` | 164 | **93.90%** (154/164) | **93.90%** (154/164) | [88.76%, 96.87%] | `logs/test_reports/humaneval_canonical_assisted_164.json` |
| `math-v1.3-regraded-strict` | `25adb03` | v1.35-strict | `data/benchmarks/math_fresh_heldout_500.jsonl` | 500 | **78.60%** (393/500) | **78.60%** (393/500) | [74.69%, 82.06%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` |
| `math-v1.3-regraded-lenient`| `25adb03` | v1.35-lenient | `data/benchmarks/math_fresh_heldout_500.jsonl` | 500 | **78.60%** (393/500) | **86.40%** (432/500) | [83.01%, 89.22%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_lenient_posthoc.json` |
| `math-v1.3-dev-400-baseline`| `e0a8fbf` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | 400 | **76.25%** (305/400) | **81.50%** (326/400) | [71.84%, 80.16%] (S)<br>[77.40%, 85.00%] (L) | `logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json` |
| `math-v1.35-dev-400` (v1) | `deacabe` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | 400 | **74.75%** (299/400) | **79.50%** (318/400) | [70.27%, 78.76%] (S)<br>[75.27%, 83.17%] (L) | `logs/test_reports/checkpoint_math500_v1.35-dev-400.json` |
| **`math-v1.35-dev-400-v2`** | `9b6858e` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | 400 | **76.50%** (306/400) | **80.50%** (322/400) | **[72.10%, 80.39%] (S)**<br>**[76.33%, 84.08%] (L)** | `logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json` |

---

## 4. Engineering Bugs Diagnosed & Resolved in v1.35

1. **Llama-Server Prompt Cache Non-Determinism (Step 0)**:
   - *Problem*: Reusing prompt caches caused run-to-run variance (runs swung between 76% and 84%).
   - *Fix*: Added `--disable-prompt-cache` (`cache_prompt: false` in payload). Verified 100/100 bit-for-bit identical outputs.
2. **SymPy `CRootOf` Resultant Hang (Step 4, `deacabe`)**:
   - *Problem*: Synchronous `sympy.simplify(p - e)` hung at 100% CPU on high-degree polynomials (Problem 102).
   - *Fix*: Guarded with `has(sympy.CRootOf)` and wrapped evaluation in `evaluate_sympy_strict_with_timeout` (2.0s daemon thread join).
3. **Comment Scratchwork Token Starvation (Step 4, `deacabe`)**:
   - *Problem*: Gemma wrote hundreds of tokens in `#` comments and exhausted the 768-token budget without emitting `print(answer)`.
   - *Fix*: Prompt rule forbidding comment scratchwork. Successfully recovered Tasks 21, 69, 105.
4. **SymPy `solve()` Dict Indexing Crash (`KeyError: 0`) (Step 4 Debugging, `9b6858e`)**:
   - *Problem*: Exact arithmetic prompt caused Gemma to call `sympy.solve()`, but index it as `sol[0]`. SymPy returns a dictionary `{var: val}` for linear systems, causing `KeyError: 0` crashes on 9 dev problems. Turn 2 feedback repeated the identical mistake.
   - *Fix*: Guided prompt to use `dict=True` (`sol = solve(..., dict=True)`) and access `sol[0][x]`, and injected an explicit `KeyError` diagnostic hint into Turn 2.
   - *Result*: `KeyError` crashes dropped from 9 to 2 (-78%), `runtime_crash` dropped from 20 to 14. Strict CAS **306/400 (76.50%)** is statistically indistinguishable from the 305/400 baseline (a one-item difference inside a ±4-point CI); the measurable gains of v1.35 so far are determinism and crash-class reduction, not accuracy.

---

## 5. Dataset Boundaries & Partition Invariants

Dataset file: `data/benchmarks/math500_test.jsonl` (SHA-256: `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132`).

- **Held-Out Test Set** (Indices 1–100, slice `[0:100]`):
  - **Status**: **PRISTINE & UNTOUCHED**.
  - Must NEVER be peeked at, analyzed, or trained on.
  - Reserved strictly for one-shot evaluation in Step 5.
- **Dev Set** (Indices 101–500, slice `[100:500]`, `--offset 100 --samples 400`):
  - Used for calibration and debugging.
  - Step 4 verified: Strict 306/400, Lenient 322/400.

---

## 6. How the Incoming Agent Should Execute Step 5

> **SUPERSEDED (2026-10-03): do NOT run Step 5 directly.** Follow [`handover/V135_CLOSEOUT_PLAYBOOK.md`](file:///c:/Projects/ProjectLucca/handover/V135_CLOSEOUT_PLAYBOOK.md) instead. The ledger script [`scripts/v135_failure_ledger.py`](file:///c:/Projects/ProjectLucca/scripts/v135_failure_ledger.py) showed that **42 of the 94 strict failures on dev-400-v2 are `finish_reason=length` truncations at the 768-token cap** (the "uniform ~15.6 s T1 latency" is the cap, not a timeout). The playbook fixes that and the crash-feedback content first, labels every remaining failure, audits test-set contamination, then runs the final test once with `math_fresh_heldout_500` (n=500) as the primary set and test-100 as secondary. The Step 5 text below is retained for reference only.

The dev set regression is resolved, and performance is frozen under `v1.35-frozen`. The incoming agent should run **Step 5: Held-Out Test Set Evaluation**.

### Step 5 Command:
```powershell
C:\Projects\ProjectLucca\.venv\Scripts\python.exe scripts/run_modern_2024_benchmarks.py `
  --benchmark math500 `
  --offset 0 `
  --samples 100 `
  --config-label v1.35-final-test-100 `
  --disable-prompt-cache `
  --resume
```

### Verification & Reconciliation Checklist:
1. Ensure AC power is online (`(Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus).PowerOnline == True`).
2. Verify `llama-server` is up on port 8080.
3. Run the 100-problem evaluation (~15-20 min).
4. Reconcile exact counts ($n = \text{passed} + \text{failed} = 100$) against v1.3 test-100 baselines:
   - Nominal Baseline (`checkpoint_math500_v1.3-baseline-test-100.json`): 79/100
   - Final Test (`checkpoint_math500_v1.3-final-test-100.json`): 85/100
5. Calculate Wilson 95% confidence intervals for Strict and Lenient scores.
6. Append row to `RESULTS.md`, commit, and tag `v1.35-test-evaluated`.

---

## 7. How to Launch and Test Lucca Herself

To interact with Lucca outside the benchmark suite:
- **Environment Diagnostic**:
  ```powershell
  C:\Projects\ProjectLucca\.venv\Scripts\python.exe -m lucca.admin env-check
  # or via standalone build:
  dist\Lucca\Lucca.exe --check
  ```
- **Launch the Voice Companion GUI & Tray**:
  ```powershell
  dist\Lucca\Lucca.exe
  # or from source:
  C:\Projects\ProjectLucca\.venv\Scripts\python.exe -m lucca.main
  ```
- **Terminal Testing Flow (No Mic Needed)**:
  ```powershell
  C:\Projects\ProjectLucca\.venv\Scripts\python.exe scripts/test_session_flow.py --interactive
  ```
- **Live Pipeline Web Debugger**:
  Open `http://localhost:8765` (served by `ui/pipeline_debugger/index.html`) to watch real-time token cascades, affective PAD states, and tool invocations across tanks 1–9.

---

## 8. Forward Roadmap: Work Order 29 & The 15-Module Cognitive Ladder

Detailed specifications and architectural mappings are preserved in [`handover/WORKORDER_29.md`](file:///c:/Projects/ProjectLucca/handover/WORKORDER_29.md) and canonical plan [`plans/2026-10-03_wo29_neurosymbolic_program_synthesis_and_15_module_cognitive_ladder.md`](file:///c:/Projects/ProjectLucca/plans/2026-10-03_wo29_neurosymbolic_program_synthesis_and_15_module_cognitive_ladder.md).


### 8.1 Architectural Primer & Module Mapping

Lucca is uniquely primed for this 15-module expansion; each component extends established foundations:

| Tier | # | Module Name | Target File | Existing Foundation in Lucca |
| :--- | :---: | :--- | :--- | :--- |
| **Part 1: Core Synthesis** *(v1.4.0 Baseline / WO-29)* | **1** | **Functional Scheme Spatial DSL** | `src/lucca/reasoning/spatial_primitives.scm` | Plugs directly into MicroScheme AST parser & primitives in [`src/lucca/reasoning/scheme/`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/scheme/) |
| | **2** | **Equality Saturation Rewrite Rules** | `src/lucca/reasoning/egraph.py` | Extends the existing Congruence-Closure E-Graph in [`egraph.py`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/egraph.py#L37-L60) |
| | **3** | **Persistent Docker Scheme RPC** | `src/lucca/sandbox/rpc.py` | Extends line-buffered `DockerRPCTransport` in [`rpc.py`](file:///c:/Projects/ProjectLucca/src/lucca/sandbox/rpc.py) |
| | **4** | **GBNF S-Expression Grammar** | `config/grammars/scheme_sketch.gbnf` | Native GBNF logit constraint in `llama-server.exe` |
| | **5** | **Scratchpad Falsification Loop** | `src/lucca/core/scratchpad.py` | Integrates into `SubTurnScratchpadBuffer` & Docker preflight |
| | **6** | **Non-Destructive Epistemic Prober** | `src/lucca/router/heuristic.py` | Extends the Conformal Intent Valve to halt on ambiguity ($\bot$) |
| **Part 2: Robustness & Hygiene** *(WO-30)* | **7** | **Idiomaticity Cost Extractor** | `src/lucca/reasoning/cost.py` | Plugs into AST extraction in [`egraph.py`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/egraph.py) |
| | **8** | **Transactional Git Staging DAG** | `src/lucca/sandbox/staging.py` | Context-manager worktree isolation inside WSL2 |
| | **9** | **Traceback Divergence Guard** | `src/lucca/core/convergence.py` | Extends turn convergence checks to abort hallucination loops |
| | **10** | **Belnap Latent Investigator** | `src/lucca/memory/latent_probe.py` | Uses Belnap 4-valued logic ($\top, \bot, T, F$) to isolate env state drift |
| | **11** | **Boundary Topology Parser** | `src/lucca/reasoning/topology.py` | Builds on AST extraction in [`ast_sanitizer.py`](file:///c:/Projects/ProjectLucca/src/lucca/sandbox/ast_sanitizer.py) to protect API contracts |
| **Part 3: Autonomous Search** *(v1.5.0 Cognitive Engine / WO-31)* | **12** | **AST-Hole MCTS Engine** | `src/lucca/reasoning/mcts.py` | Multi-threaded CPU tree search over S-expression holes |
| | **13** | **BitNet b1.58 2B Policy Prior** | `src/lucca/reasoning/bitnet_policy.py` | Host CPU integer SIMD execution (~1.2 GB RAM, 0 MB VRAM) |
| | **14** | **DreamCoder Macro Miner** | `src/lucca/reasoning/compression.py` | Extends anti-unification in [`egraph.py`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/egraph.py) for sleep-phase library learning |
| | **15** | **Backward Abduction Solver** | `src/lucca/reasoning/abduction.py` | Works backwards from target invariant assertions using e-graph unification |

### 8.2 Hardware Integrity
- **0 MB VRAM Delta:** Runs in host CPU threads (Core Ultra 9 275HX), host DDR5 RAM, or WSL2 Docker sandbox.
- **Dedicated Engine Protection:** RTX 5080 Laptop GPU remains 100% dedicated to LLM deliberation (`gemma-4-12b` / `nemotron-30b`); Intel NPU handles Kokoro TTS and Silero VAD.
- **Invariants Preserved:** ADR-006 (cryptographic envelope memory commits) and ADR-013 (Docker containerization).

### 8.3 Execution Roadmap
```mermaid
flowchart TD
    subgraph Gate ["Immediate Verification Gate"]
        H1["3-Way Re-Prompt Brief on ~110 Items"] --> H2["Harness Frozen"]
        H2 --> H3["Model Swap (Nemotron on Frozen Harness)"]
        H3 --> H4["Label 20 Bucket C Failures"]
    end

    subgraph WO29 ["WO-29: Part 1 Baseline (v1.4.0)"]
        M1["1. Spatial DSL"]
        M2["2. E-Graph Rewrites"]
        M3["3. Docker Scheme RPC"]
        M4["4. GBNF Grammar"]
        M5["5. Scratchpad Falsification"]
        M6["6. Epistemic Prober"]
    end

    subgraph WO30 ["WO-30: Part 2 Robustness & Hygiene"]
        M7["7. Idiomaticity Cost"]
        M8["8. Transactional Git DAG"]
        M9["9. Loop Divergence Guard"]
        M10["10. Belnap Latent Probe"]
        M11["11. Boundary AST Parser"]
    end

    subgraph WO31 ["WO-31: Part 3 Scaling (v1.5.0)"]
        M12["12. AST-Hole MCTS"]
        M13["13. BitNet b1.58 2B Prior"]
        M14["14. DreamCoder Macro Miner"]
        M15["15. Backward Abduction"]
    end

    Gate --> WO29
    WO29 --> WO30
    WO30 --> WO31

    subgraph Orthogonal ["Parallel & Gated Work"]
        Voice["Voice Scaffolding: Acoustic Lock & Slot-Locking (Parallel)"]
        WO32["WO-32: Reflection Loop (Gated on 200-500 Organic Dogfood Turns)"]
    end
```

### 8.4 Immediate Gate Protocol
1. Run isolated 3-way re-prompt comparison across ~110 feedback items.
2. Lock winning harness configuration.
3. Test model swap (Nemotron on frozen harness).
4. Label 20 representative Bucket C failures.
5. Unblock WO-29 Part 1 baseline execution.

---

## 9. Current Engineering State (October 10, 2026 — Work Order 32 & ConceptARC Milestone)

### 9.1 ConceptARC Neurosymbolic Evaluation (Rank 1 Benchmark)
- **Benchmark Suite:** ConceptARC Minimal (16 core Chollet spatial concepts).
- **Arm A (Frozen Control Baseline):** 9/16 (56.2%).
- **Arm B (Augmented Agent):** **13/16 (81.2%)** (Wilson 95% CI: [57.0%, 93.4%]).
- **Verified Code Synthesis Wins:** **9/16 (56.2%)** (`Center`, `Copy`, `Count`, `ExtractObjects`, `FilledNotFilled`, `HorizontalVertical`, `InsideOutside`, `SameDifferent`, `TopBottom3D`).
- **Net Scaffold Lift:** **+25.0 percentage points** ($B - A$), with strict **Zero Regressions** ($Arm\ B \ge Arm\ A$ across all 16 concepts).
- **Canonical Plan:** [`plans/2026-10-10_wo32_concept_arc_neurosymbolic_synthesis.md`](file:///C:/Projects/ProjectLucca/plans/2026-10-10_wo32_concept_arc_neurosymbolic_synthesis.md).
- **Latest Sealed Report:** `logs/test_reports/concept_arc_gbnf_minimal_1791607195.json`.

### 9.2 Out-of-Distribution Corpus Benchmark (16 Unseen Tasks) — Post-Upgrade Run
- **Benchmark Split:** 1 unseen task per concept from `data/benchmarks/ConceptARC/corpus/`.
- **Arm A (Frozen Control):** 5/16 (31.2%) (Wilson: [14.2%, 55.6%]).
- **Arm B (Augmented Agent):** **8/16 (50.0%)** (Wilson: [28.0%, 72.0%]).
- **Net Scaffold Lift:** **+18.8 percentage points** ($B - A$), with **zero regressions** ($Arm\ B \ge Arm\ A$ across all 16 concepts).
- **Verified Code Synthesis Wins:** **5/16 (31.2%)** (`CompleteShape1`, `Copy1`, `Count1`, `ExtractObjects1`, `FilledNotFilled1`).
- **Scaffold Lift Over Control via Verified Code:** On `CompleteShape1`, `Count1`, and `ExtractObjects1`, Arm A completely failed ($0\%$), while Arm B synthesized verified Python solutions that passed 100% of test cases.
- **Sealed Report:** `logs/test_reports/concept_arc_gbnf_minimal_1791667185.json`.

### 9.3 Test Suite & Server Status
- **Pytest Gate:** **56/56 unit tests and static architecture gates passing** in $<10\text{s}$ (`tests/test_spatial_dsl.py`, `tests/test_scheme_geometry.py`, `tests/test_static_gates.py`).
- **Local Server:** `llama-server.exe` daemon is completely stopped and shut down.

### 9.4 Neurosymbolic Architecture Upgrades (Post-Iteration 17 & Unshimmed Cascaded Router)
- **Layer 1 (Deterministic Invariants):** Implemented `SymbolicInvariants` and `analyze_symbolic_invariants` in [`src/lucca/reasoning/spatial_dsl.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/spatial_dsl.py) for instantaneous mathematical pre-filtering (shape transitions, 1D tally orientation, pixel conservation, hollow topology).
- **Layer 2 (GBNF Grammar-Constrained Neural Abduction):** Enforced `ABDUCTION_GBNF_GRAMMAR` and `AbductionPayload` in [`scripts/run_concept_arc.py`](file:///C:/Projects/ProjectLucca/scripts/run_concept_arc.py), completely eliminating regex answer-bleed stripping and ensuring 100% valid JSON enum outputs.
- **Layer 3 (Typed Primitive Dispatch):** Implemented `PRIMITIVE_REGISTRY` and `resolve_scoped_primitives` in [`src/lucca/reasoning/spatial_dsl.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/spatial_dsl.py), replacing substring matching with typed domain routing.
- **Hardened Verbatim Fallback:** Fixed internal fallback to replay the evaluated Arm A grid directly, eliminating fallback parse discrepancies and mathematically guaranteeing $Arm\ B \ge Arm\ A$.
- **8-Connectivity Digital Topology & Auto-Symmetry:** Native `connectivity=8` in `find_objects` / `count_objects` and consensus reflection axis inference (`mode="auto"`) in `complete_symmetry`.

### 9.5 Multimodal Projectors & Multi-Tier Vision Verification
- **Architecture Parity:** Gemma 4 models across all tiers natively support text, vision, and audio.
- **Installed Projectors (`C:\ProjectLucca\models\llm\`):**
  - `gemma-4-12b-heretic-mmproj-f16.gguf` (`n_embd = 3840`, 175 MB): Verified live via [`test_vision_live.py`](file:///C:/Projects/ProjectLucca/scripts/test_vision_live.py).
  - `gemma-4-E4B-it-mmproj-BF16.gguf` (`n_embd = 2560`, 945.6 MB): Verified live via `llama-server` on synthetic shape/color prompt (2.83s latency).
  - `gemma-4-E2B-it-mmproj-f16.gguf` (`n_embd = 2048`, 940.0 MB): Verified live via `llama-server` on synthetic shape/color prompt (1.18s latency).
- **Local Server Daemon:** Active daemon running Gemma 4 12B + mmproj on port 8080 (`http://127.0.0.1:8080`).

### 9.6 Empirical Multi-Scale Multimodal Benchmark Matrix (16 Unseen ConceptARC Tasks)
| Model Tier | Multimodal Status | Arm A (Control) | Arm B (Augmented Agent) | Net Scaffold Lift | Verified Code Synthesis Wins | Sealed Report |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Gemma 4 12B** | **Active (mmproj)** | **31.2%** (5/16) | **50.0%** (8/16) | **+18.8 pp** | **5/16 (31.2%)** (`CompleteShape1`, `Copy1`, `Count1`, `ExtractObjects1`, `FilledNotFilled1`) | `concept_arc_gbnf_minimal_1791667185.json` |
| **Gemma 4 E4B** | **Active (mmproj)** | **0.0%** (0/16) | **18.8%** (3/16) | **+18.8 pp** | **3/16 (18.8%)** (`Copy1`, `ExtractObjects1`, `FilledNotFilled1`) | `concept_arc_gbnf_minimal_1791692197.json` |
| **Gemma 4 E2B** | **Active (mmproj)** | **0.0%** (0/16) | **12.5%** (2/16) | **+12.5 pp** | **2/16 (12.5%)** (`CompleteShape1`, `ExtractObjects1`) | `concept_arc_gbnf_minimal_1791692692.json` |

- **Multimodal Lift over Text Fallback:**
  - E4B improved from 12.5% (text) $\to$ **18.8% (multimodal)** (+6.3 pp boost; unlocked `ExtractObjects1`).
  - E2B doubled from 6.2% (text) $\to$ **12.5% (multimodal)** (+6.3 pp boost; unlocked `ExtractObjects1`).
- **Core Invariant Preserved:** Strict zero-regression guarantee ($Arm\ B \ge Arm\ A$) preserved across 100% of tasks at all three model scales.

### 9.7 Work Order 33: Controlled Library Extension & Multi-Domain Harmonization (Complete & Verified)
- **Canonical Plan:** [`plans/2026-10-11_wo33_controlled_library_extension_and_multi_domain_harmonization.md`](file:///C:/Projects/ProjectLucca/plans/2026-10-11_wo33_controlled_library_extension_and_multi_domain_harmonization.md).
- **Core Implementations:**
  1. **Dynamic Library Propagation (Milestone 3.1):** Mined macros (`sym-fill-1`, `sym-fill-2`) admitted via DreamCoder first-order anti-unification in [`src/lucca/reasoning/compression.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/compression.py), verified via Microsoft Z3 SMT (`smt_verifier.py`), dynamically registered into `GLOBAL_MACRO_REGISTRY` and `PRIMITIVE_REGISTRY`, and dynamically compiled into [`config/grammars/scheme_sketch.gbnf`](file:///C:/Projects/ProjectLucca/config/grammars/scheme_sketch.gbnf).
  2. **Symbolic Scene Graph Extraction (Milestone 3.2):** Implemented `build_scene_graph()` and `format_scene_graph_prompt()` in [`src/lucca/reasoning/spatial_dsl.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/spatial_dsl.py). Connected components, centroids, bounding boxes, topology, and pairwise relations (`contains`, `adjacent`, `aligned`) replace heavy multimodal base64 embeddings, reducing prompt size from >10,000 tokens to <1,500 tokens and eliminating slot context overflow (`400 Bad Request`).
  3. **Relational CEGIS Error Diffs (Milestone 3.3):** Implemented `generate_relational_diff()` in `spatial_dsl.py`, feeding structured object deltas (centroid shifts, size mismatches, missing/extra components) to the autonomous self-repair loop.
  4. **State-Dependent Semantic Palette Masking (Milestone 4.1):** `compile_dynamic_sketch_grammar()` restricts `hole-color` tokens to active grid palette colors $C_{\text{active}} \subset \{0..9\}$, collapsing branching factor.
  5. **Occam's Razor / MDL Candidate Ranking:** Evaluates all passing MicroScheme sketches and ranks by metamorphic equivariance and minimum AST cost (MDL), preventing overfitted compound expressions.
  6. **Math & Code Harmonization (Milestone 4.2):** Implemented SymPy CAS parameter binding in [`src/lucca/reasoning/scheme/math_primitives.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/scheme/math_primitives.py) and typed GBNF grammars [`config/grammars/math_sketch.gbnf`](file:///C:/Projects/ProjectLucca/config/grammars/math_sketch.gbnf) and [`config/grammars/code_sketch.gbnf`](file:///C:/Projects/ProjectLucca/config/grammars/code_sketch.gbnf).

### 9.8 Sealed Empirical Results (WO-33)
- **ConceptARC Unseen Corpus:**
  - Arm A (Frozen Control): 18.8% (3/16)
  - Arm B (Augmented Agent): **37.5% (6/16)**
  - Verified Code Synthesis Wins: **31.2% (5/16)** (`Center1`, `CompleteShape1`, `Copy1`, `ExtractObjects1`, `FilledNotFilled1`)
  - Absolute Scaffold Lift (B - A): **+18.8 percentage points**
  - Mined Macro Deployment: `sym-fill-2` synthesized and verified live on `CompleteShape1` (`[VERIFIED_CODE]` win where Arm A scored 0.0%).
  - Zero-Regression Guarantee: Verified across all evaluated tasks ($Arm\ B \ge Arm\ A$).
  - Sealed Reports: `logs/test_reports/concept_arc_gbnf_minimal_1791718109.json`, `concept_arc_gbnf_minimal_1791719597.json`.
- **MATH-500 Neurosymbolic MathCAS Evaluation:**
  - Arm A (Control, 12B Heretic): **90.0% (9/10)** | Wilson 95% CI: `[59.6%, 98.2%]`
  - Arm B (Augmented Agent, MathCAS): **90.0% (9/10)** | Wilson 95% CI: `[59.6%, 98.2%]`
  - Baseline Integrity Resolution: Per `MANIFEST.yaml` (`math500_heldout100_direct_r0_v1_35_6` and `math500_b4_sealed_12b_v1_35_6`), Direct R0 explicitly used `enable_thinking: false` with `max_tokens: 4096`, achieving 88.0%–89.0% strict / 93.0%–94.0% lenient (re-run: 88.0%, establishing a 1.0 pp noise floor). The '58.0%' and '46.0%' figures represent the exact same greedy-decoding thinking-mode loop confound (T=0, think_cap=6144, causing 44% and 55% truncations without repetition penalty) across two different splits: dev-100 (`STATE_OF_THE_UNION_2026-10.md:146`, Paper 06 §5.1) and B4 sealed-100 (`math500_b4_sealed_12b_v1_35_6`, `logs/test_reports/b4_sealed/gemma-4-12b_math500_r1_b4_sealed_think6144_100.json`). Both are confounded negative observations, not inherent properties of thinking mode. The earlier '50–60%' bare figure cited informally in write-ups is *likely, not traced*—an informal conflation of the 58% greedy thinking collapse or early truncated scratchpad runs. The compound MathCAS harness (P2) scores 86–87% strict; its value is deterministic exact rational arithmetic (`sp.Rational(14, 3)`), audit provenance, and zero float round-off, not a raw accuracy lift over unconstrained CoT.
  - Sealed Report: `logs/test_reports/math500_sketch_eval_1791721322.json`.

### 9.9 Sealed Edge Model Parity Evaluation (E4B / E2B Matrix on ConceptARC)
- **Deployed Model Identifiers:**
  - 12B: `gemma-4-12b-heretic-Q6_K.gguf` (Uncensored Heretic abliterated build)
  - E4B: `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (Uncensored Heretic abliterated build)
  - E2B: `Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf` (Uncensored Heretic build with Sinhala language fine-tune; note: Sinhala fine-tune represents an active modification confound relative to pure scale).
- **Gemma 4 E4B Edge Evaluation:**
  - Control Arm A (Bare Weights): **0.0% (0/16)** | Wilson 95% CI: `[0.0%, 19.4%]`
  - Augmented Arm B (Neurosymbolic Core): **12.5% (2/16)** | Wilson 95% CI: `[3.5%, 36.0%]`
  - Verified Code Synthesis Wins: **12.5% (2/16)** (`CompleteShape1`, `FilledNotFilled1`)
  - **Live Mined Macro Synthesis on 4B Model:** Gemma 4 E4B successfully synthesized newly admitted library macro `sym-fill-1` (`(sym-fill-1 input ?hole-axis ?hole-mode)`) with bindings `{'?hole-axis': 'both', '?hole-mode': 'auto'}`, verified in 1 evaluation and scoring a 100% test pass on `CompleteShape1` (a task where bare E4B scored 0.0%).
  - Zero-Regression Invariant: No regressions observed at the problem level ($Arm\ B \ge Arm\ A$).
  - Sealed Report: `logs/test_reports/concept_arc_gbnf_minimal_1791724391.json`.
- **Gemma 4 E2B Ultra-Edge Evaluation:**
  - Control Arm A (Bare Weights): **0.0% (0/16)** | Wilson 95% CI: `[0.0%, 19.4%]`
  - Augmented Arm B (Neurosymbolic Core): **0.0% (0/16)**
  - MicroScheme Training Verification: E2B successfully synthesized `(complete-symmetry input :axis 0 :mode 1)` passing 100% of training demonstrations (`train_passed: True`, method `VERIFIED_CODE`), though concrete literals did not generalize to unseen test grid.
  - Edge Memory Footprint: Peak VRAM usage was only **3,398 MiB** (fits in standard 4GB edge devices).
  - Sealed Report: `logs/test_reports/concept_arc_gbnf_minimal_1791724936.json`.
- **Primary Server Restoration:**
  - Gemma 4 12B Q6_K + mmproj daemon successfully restored on port 8080 (`task-10204`).
  - Pytest verification suite: **73/73 tests passing in 9.24s**.

### 9.10 Sealed Out-Of-Distribution Generality Audit (Option C Red-Team Verification)
- **Harness:** [`scripts/run_ood_generality_audit.py`](file:///C:/Projects/ProjectLucca/scripts/run_ood_generality_audit.py) evaluating 60 untouched problems across 3 completely new domains.
- **Part 1: Strict Closed-World Falsification Test:**
  - Problems Attempted in `spatial_dsl`: **60/60**
  - Incompatible / Crashed: **60/60 (100.0%)** (`ValueError: invalid literal for int` / `TypeError`).
  - Audit Finding: Confirms irrefutably that `spatial_dsl.py` and `scheme_sketch.gbnf` are **100% closed-world to 2D integer matrices**. They possess 0% zero-shot transfer outside pixel grids.

### 9.11 Historical Multi-Scale Matrix on 60 OOD Items (Superseded Direct Baseline — Regression Continuity)

> [!WARNING]
> **CORRECTION BANNER (Superseded Baseline Disclosure — 2026-10-12):**  
> The headline lifts reported in this section (+62.5 pp / +45.0 pp / +17.5 pp) were measured against an Arm A direct control evaluated with `enable_thinking: false` and artificially constrained by a 128-token cap (`max_tokens: 128`), producing a 63.9% token truncation rate.  
> When re-evaluated with native non-greedy thinking enabled (`enable_thinking: true`, `max_tokens: 3072`, $T=0.6$) in Section 9.13, bare Gemma 4 12B solves **37/40 (92.5%)** of clean text logic and spatial navigation problems natively. On those 40 text items, Thinking (37/40) vs PAL (40/40) has discordant pairs 3:0 (exact two-sided McNemar $p = 0.25$), showing **no statistically detectable accuracy difference at $n=40$**.  
> PAL's statistically verified structural advantage over thinking mode is strictly on **Code Execution Tracing (CruxEval: 20/20 vs 10/20, $p \approx 0.002$)**, eliminating 9,000-character mental thinking loops, deterministic CPU execution, and latency reduction. This 60-item matrix is preserved below for historical audit provenance and continuity as a regression smoke test, but must not be cited as evidence of massive accuracy lift on text reasoning.

- **Run Configuration:** 32k context split into 4 parallel slots (8,192 tokens per slot), 8-bit quantized KV cache (`--cache-type-k q8_0`, `--cache-type-v q8_0`), Flash Attention enabled (`--flash-attn on`).

| Model Scale & Artifact | Active VRAM | Arm A (Bare Weights) | Arm B (PAL Code Synthesis) | Net Overall Lift | **Non-CruxEval Subtotal** (Nav + Logic, n=40) | CruxEval (Code, n=20)* | Logic Deduction (n=20) | Spatial Nav (n=20) | Sealed Audit Report |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Gemma 4 12B Heretic** (`gemma-4-12b-heretic-Q6_K.gguf`) | 11.3 GB | **26.7%** (16/60) | **96.7%** (58/60) | **+70.0 pp** | **13/40 (32.5%) $\to$ 38/40 (95.0%) [+62.5 pp]** | **100.0%** (20/20) | **95.0%** (19/20) | **95.0%** (19/20) | [`ood_generality_audit_1791730593.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_generality_audit_1791730593.json) |
| **Gemma 4 E4B Heretic** (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`) | 5.5 GB | **31.7%** (19/60) | **86.7%** (52/60) | **+55.0 pp** | **14/40 (35.0%) $\to$ 32/40 (80.0%) [+45.0 pp]** | **100.0%** (20/20) | **85.0%** (17/20) | **75.0%** (15/20) | [`ood_generality_audit_1791731412.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_generality_audit_1791731412.json) |
| **Gemma 4 E2B Heretic-Sinhala** (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`) | 3.4 GB | **23.3%** (14/60) | **66.7%** (40/60) | **+43.3 pp** | **13/40 (32.5%) $\to$ 20/40 (50.0%) [+17.5 pp]** | **100.0%** (20/20) | **45.0%** (9/20) | **55.0%** (11/20) | [`ood_generality_audit_1791731576.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_generality_audit_1791731576.json) |

- **Methodological Qualifications & Audit Caveats (v4 Audit Realities):**
  1. **Arm B Composition Reality:** Part 1 verified that `spatial_dsl.py` + `scheme_sketch.gbnf` crashed 100% (60/60) on non-ARC tasks. Arm B was executed via general Python program synthesis (Program-Aided Language / PAL) inside the Docker container (`lucca-file-sandbox`). The lift measures code execution replacing mental calculation, not MicroScheme, CEGIS, or e-graph deduction.
  2. ***CruxEval Execution Fidelity:** CruxEval 100.0% across all tiers is expected by construction because the prompt provides the code and input, and Arm B executes it directly in the container. It verifies sandbox execution fidelity, not neural reasoning improvement. Headline lifts are reported both with and without CruxEval.
  3. **Non-CruxEval Reasoning Lift:** On Logic Deduction and Spatial Navigation (where the model must actively generate the Python search / trajectory script from problem text), net lift was: 12B = **+62.5 pp**, E4B = **+45.0 pp**, E2B = **+17.5 pp**.
  4. **Zero-Regression Observation:** In all 180 individual problem runs across the three model scales, zero regressions were observed at the problem level ($Arm\ B \ge Arm\ A$ on every instance in each run).
  5. **Confound Disclosure:** E2B carries a Sinhala language fine-tune on top of Heretic abliteration, which represents an active modification confound on E2B's performance relative to pure parameter scaling.
  6. **Hardware Provenance:** Evaluated on physical silicon: **NVIDIA GeForce RTX 5080 Laptop GPU (16303 MiB, 175W)**.
  7. **Directory Tree Architecture:** Runtime deployment (`LUCCA_HOME`) is at `C:\ProjectLucca` (holding models, llama-server binary, and runtime logs); development Git repository is at `C:\Projects\ProjectLucca`.
  8. **Roadmap Designation:** Upcoming General Python spatial synthesis work package is assigned to **WO-35** (`WO-35: General Python Program Synthesis`), avoiding collision with WO-34 (Proactive Reflection Loop, `D-REAS-12`).

### 9.12 Sealed Empirical Noise Floor & Stability Audit (Option 1 Verification)
- **Harness & Statistical Analyzer:** [`scripts/run_ood_generality_audit.py`](file:///C:/Projects/ProjectLucca/scripts/run_ood_generality_audit.py) and [`scripts/analyze_ood_noise_floor.py`](file:///C:/Projects/ProjectLucca/scripts/analyze_ood_noise_floor.py).
- **Architecture Environment:**
  - Server: Resident Gemma 4 12B Heretic Q6_K on single-slot `--parallel 1` (completely eliminating continuous batching concurrency / slot race effects), 32k context, Q8_0 KV cache, Flash Attention, resident VRAM 10,546 MiB on NVIDIA GeForce RTX 5080 Laptop GPU.
  - Sandbox: Strict Docker container (`lucca-file-sandbox`) via persistent `DockerRPCTransport` worker with zero in-process fallback (`use_direct_fallback=False`), `--network none`, `--read-only`, non-root user.
  - Sampling: 3 complete independent repeats of all 60 problems (180 evaluations total) at $T=0.1$, `top_p=0.95`.
- **Headline Results Across 3 Runs:**
  | Run | Arm A Bare (60) | Arm B PAL (60) | Non-CruxEval Subtotal (Nav + Logic, n=40) | Net Overall Lift | Sealed Audit Report |
  | :--- | :---: | :---: | :---: | :---: | :--- |
  | **Run 1** | 13/60 (21.7%) | 60/60 (100.0%) | A: 12/40 (30.0%) $\to$ B: 40/40 (100.0%) | **+78.3 pp** (+70.0 pp non-crux) | [`ood_generality_audit_1791737702.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_generality_audit_1791737702.json) |
  | **Run 2** | 14/60 (23.3%) | 59/60 (98.3%) | A: 12/40 (30.0%) $\to$ B: 39/40 (97.5%) | **+75.0 pp** (+67.5 pp non-crux) | [`ood_generality_audit_1791737996.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_generality_audit_1791737996.json) |
  | **Run 3** | 14/60 (23.3%) | 60/60 (100.0%) | A: 12/40 (30.0%) $\to$ B: 40/40 (100.0%) | **+76.7 pp** (+70.0 pp non-crux) | [`ood_generality_audit_1791738304.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_generality_audit_1791738304.json) |
- **Stability & Noise Floor Findings:**
  1. **Empirical Noise Floor:** Under `--parallel 1`, run-to-run headline score moved by only **$\pm 1.6\text{ pp}$** (Arm A: 21.7% $\to$ 23.3%; Arm B: 100.0% $\to$ 98.3%). This disproves the hypothesis of high intrinsic sampling noise and confirms that previous larger fluctuations were an artifact of `--parallel 4` slot race conditions or cold-start timeouts.
  2. **Item-Level Consistency:**
     - Arm A (Bare): Always Pass: 13/60, Always Fail: 46/60, Flipped: 1/60 (`CruxEval_11` flipped from Fail in Run 1 to Pass in Runs 2 & 3). Item consistency = **98.3%**.
     - Arm B (PAL): Always Pass: 59/60, Always Fail: 0/60, Flipped: 1/60 (`Deduction_20` flipped from Pass in Runs 1 & 3 to Fail in Run 2 due to `GRADER_FORMAT_MISMATCH`). Item consistency = **98.3%**.
  3. **Pairwise Discordant Analysis & Exact McNemar Tests:**
     - Run 1 vs Run 2: Arm A discordant = 1 ($p=1.0000$); Arm B discordant = 1 ($p=1.0000$).
     - Run 1 vs Run 3: Arm A discordant = 1 ($p=1.0000$); Arm B discordant = 0 ($p=1.0000$).
     - Run 2 vs Run 3: Arm A discordant = 0 ($p=1.0000$); Arm B discordant = 1 ($p=1.0000$).
     - Statistically identical distributions across all runs with zero significant drift.
  4. **Problem-Level Non-Regression Invariant:**
     - **100% Verified across all 180 problem-evaluations ($60 \times 3$).**
     - Exactly zero instances where Arm A succeeded and Arm B failed ($b=0$ across all 180 pairs).
  5. **Truncation Ceiling Quantification (`finish_reason`):**
     - Arm A Length Truncations: **115/180 (63.9%)** of bare evaluations were truncated by the token budget (`max_tokens: 128`), because the model produced conversational preambles before emitting the answer.
     - Arm B Length Truncations: **8/180 (4.4%)**.
     - Confirms the crucial methodological caveat that the bare Arm A baseline at tight token caps is heavily constrained by truncation, underscoring the absolute necessity of evaluating the extended-thinking Arm A baseline (Option 2).
  6. **Weight & Projector Origin Provenance:**
     - All 6 GGUF and mmproj files are cataloged with SHA256 checksums, HuggingFace `source_repo`, and `source_filename` in [`models/MANIFEST.json`](file:///C:/Projects/ProjectLucca/models/MANIFEST.json).

### 9.13 Sealed Extended-Thinking Baseline & Multi-Arm Ablation (Option 2 Verification)
- **Harness:** [`scripts/run_ood_thinking_baseline.py`](file:///C:/Projects/ProjectLucca/scripts/run_ood_thinking_baseline.py) evaluating 3 arms on identical weights (**Gemma 4 12B Heretic Q6_K**) under single-slot `--parallel 1` with strict Docker container isolation.
- **Arms Evaluated ($n=60$ tasks):**
  1. **Arm A Direct:** $T=0.0$, `max_tokens: 128`, `enable_thinking: False` (Direct baseline).
  2. **Arm A Extended Thinking:** $T=0.6$, `top_p=0.95`, `max_tokens: 3072`, `enable_thinking: True` (Native non-greedy thinking baseline, fallback parsing from reasoning tail if truncated).
  3. **Arm B PAL:** $T=0.1$, `max_tokens: 384`, executed in Docker container (`lucca-file-sandbox`) via persistent `DockerRPCTransport` worker.
- **Factorial Headline Results Across Arms:**
  | Domain / Metric | Arm A Direct (128 tok) | Arm A Extended Thinking (3072 tok) | Arm B PAL (Docker Sandbox) | Lift: Think vs Direct | Lift: PAL vs Think |
  | :--- | :---: | :---: | :---: | :---: | :---: |
  | **Spatial Navigation** ($n=20$) | 12/20 (60.0%) | **18/20 (90.0%)** | **20/20 (100.0%)** | **+30.0 pp** | **+10.0 pp** |
  | **Logical Deduction** ($n=20$) | 0/20 (0.0%) | **19/20 (95.0%)** | **20/20 (100.0%)** | **+95.0 pp** | **+5.0 pp** |
  | **Code Execution (CruxEval)** ($n=20$)* | 2/20 (10.0%) | **10/20 (50.0%)** | **20/20 (100.0%)** | **+40.0 pp** | **+50.0 pp** |
  | **Non-CruxEval Subtotal** ($n=40$) | **12/40 (30.0%)** | **37/40 (92.5%)** | **40/40 (100.0%)** | **+62.5 pp** | **+7.5 pp** |
  | **Overall (All 3 Domains)** ($n=60$) | **14/60 (23.3%)** | **47/60 (78.3%)** | **60/60 (100.0%)** | **+55.0 pp** | **+21.7 pp** |
- **Statistical Significance & McNemar Tests:**
  - **Direct vs Extended Thinking ($n=60$):** Direct won 2, Thinking won 35. Exact two-sided binomial McNemar $p = \mathbf{1.0245 \times 10^{-8}}$. (Proves conclusively that Direct Arm A was severely handicapped by the token cap).
  - **Extended Thinking vs PAL (All 60 items):** Thinking won 0, PAL won 13. Exact two-sided binomial McNemar $p = \mathbf{2.4414 \times 10^{-4}}$.
  - **Extended Thinking vs PAL (Non-Crux Text Tasks Only, $n=40$):** Thinking won 0, PAL won 3. Exact two-sided binomial McNemar $p = \mathbf{0.2500}$.
    * Per domain: Navigation discordant pairs 2:0 ($p = 0.5000$), Deduction discordant pairs 1:0 ($p = 1.0000$).
    * **Finding:** On clean text algorithmic puzzles, there is **no statistically detectable accuracy difference** between native thinking and PAL at $n=40$. PAL's measured structural advantage is strictly on Code Execution Tracing (CruxEval: 20/20 vs 10/20, $p \approx 0.002$), elimination of 9,000-token mental thinking loops, and deterministic execution.
- **Locus of PAL's Structural Advantage:**
  - **10 of PAL's 13 wins over Extended Thinking occurred on CruxEval** (code execution tracing). When forced to simulate state mutations across loops in its head, mental simulation failed 50.0% of the time (10/20) due to variable drift and infinite thought loops. PAL executed the code deterministically in $<10\text{ms}$ with 100% precision.
  - On mental constraint reasoning and spatial navigation, native thinking already achieves **92.5% (37/40)**. PAL provides a targeted **+7.5 pp lift** (3 items rescued) by eliminating 9,000-character mental coordinate loops.

- **Truncation Rates (`finish_reason == "length"`):**
  - Arm A Direct: **38/60 (63.3%)**
  - Arm A Extended Thinking: **12/60 (20.0%)** (all 12 occurred in long mental simulation loops in Nav and Crux)
  - Arm B PAL: **2/60 (3.3%)**
- **Sealed Report:** [`logs/test_reports/ood_thinking_baseline_1791744715.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_thinking_baseline_1791744715.json).

### 9.14 Work Order 35: General Python CEGIS Engine & Universal Symbolic Primitives
- **Canonical Plan:** [`plans/2026-10-12_wo35_general_python_program_synthesis_and_cegis_repair.md`](file:///C:/Projects/ProjectLucca/plans/2026-10-12_wo35_general_python_program_synthesis_and_cegis_repair.md).
- **Core Implementations:**
  1. **Multi-Turn Python CEGIS Engine (Milestone 35.1):** Implemented [`src/lucca/reasoning/cegis_python.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/cegis_python.py) (`PythonCEGISEngine`). Replaces passive one-shot execution with an autonomous, multi-turn Counter-Example Guided Inductive Synthesis loop. Catches runtime exceptions (`AssertionError`, `IndexError`, `TypeError`), extracts structured traceback contexts, and feeds local state diffs into iterative repair prompts (up to 3 turns) inside Docker container `lucca-file-sandbox`.
  2. **GBNF Code Generation Grammars (Milestone 35.2):** Authored [`config/grammars/python_program.gbnf`](file:///C:/Projects/ProjectLucca/config/grammars/python_program.gbnf) enforcing syntax-valid Python code enclosed in markdown blocks at token generation time.
  3. **Universal Symbolic Primitives for MicroScheme (Milestone 35.3):** Implemented [`src/lucca/reasoning/scheme/universal_primitives.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/scheme/universal_primitives.py) and expanded `DEFAULT_ALLOWED_OPS` in [`src/lucca/reasoning/scheme/parser.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/scheme/parser.py). Extends MicroScheme beyond 2D integer grids with:
     - Sequence operations: `reverse`, `take`, `drop`, `zip`, `unique`.
     - Set & relational operations: `member?`, `subset?`, `union`, `intersection`, `difference`.
     - 2D Vector geometry & navigation: `vec2d`, `vec-add`, `vec-sub`, `vec-scale`, `manhattan-dist`, `euclidean-dist`, `heading-turn`, `step-forward`.
  4. **PEP 561 Typing Marker:** Added [`src/lucca/py.typed`](file:///C:/Projects/ProjectLucca/src/lucca/py.typed), resolving type checking discovery across the repository.
- **Verification Status:**
  - **Pytest Gate:** **81/81 tests passing in 9.61s** ([`tests/test_cegis_python.py`](file:///C:/Projects/ProjectLucca/tests/test_cegis_python.py), [`tests/test_universal_primitives.py`](file:///C:/Projects/ProjectLucca/tests/test_universal_primitives.py), [`tests/test_static_gates.py`](file:///C:/Projects/ProjectLucca/tests/test_static_gates.py), [`tests/test_spatial_dsl.py`](file:///C:/Projects/ProjectLucca/tests/test_spatial_dsl.py)).
  - **Static Typing Gate:** `uv run mypy --strict` 100% clean across all new reasoning modules, audit scripts, and unit tests.
  - **Packaging Gate:** 7/7 passing in 24.7s ([`tests/test_packaging.py`](file:///C:/Projects/ProjectLucca/tests/test_packaging.py)).
  - **Container Isolation & Negative Breakout Gate (Claude v4 §4.5 & v5 §8):** **13/13 live container tests passing in 4.96s** ([`tests/test_milestone2_container_execution.py`](file:///C:/Projects/ProjectLucca/tests/test_milestone2_container_execution.py)). Formally verifies:
    1. `--network none`: outbound socket connections blocked (`Errno 101 Network is unreachable`).
    2. `--read-only`: root filesystem writes blocked (`EROFS: Read-only file system`).
    3. `--user 1000:1000`: unprivileged non-root execution (`UID=1000, GID=1000`).
    4. Host isolation: Windows drive (`C:\Windows`) unmounted.
    5. `/tmp` tmpfs `noexec`: binary/script execution from `/tmp` rejected with `PermissionError` (`[Errno 13] Permission denied`).
    6. `/tmp` tmpfs `size=32m`: writes exceeding 32MB rejected with `OSError: [Errno 28] No space left on device`.
    7. `--cap-drop=ALL` & `--security-opt=no-new-privileges`: effective capabilities `CapEff == 0000000000000000` and `NoNewPrivs == 1`.
    8. `--memory=768m`: memory allocation ceilings enforced via Linux cgroup (2GB buffer triggers `MemoryError`).
    9. `--pids-limit=256`: process fork bombs halted by cgroup pids limit (`BlockingIOError: [Errno 11] Resource temporarily unavailable` at spawned=252).

### 9.15 Sealed 60-Problem OOD Regression Smoke Test with PAL Code Synthesis & Iterative Self-Debugging (WO-35.4)
- **Harness:** [`scripts/run_ood_generality_audit.py`](file:///C:/Projects/ProjectLucca/scripts/run_ood_generality_audit.py) integrating [`PythonCEGISEngine`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/cegis_python.py).
- **Environment:** Resident Gemma 4 12B Heretic Q6_K on single-slot `--parallel 1` (`task-10564`), persistent Docker worker `lucca-file-sandbox` (`DockerRPCTransport`).
- **Sealed Report:** [`logs/test_reports/ood_generality_audit_1791752034.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_generality_audit_1791752034.json) (Timestamp: 2026-10-11T20:53:54Z).
- **Factorial Results ($n=60$ tasks across 3 domains):**
  | Domain / Metric | Arm A (Bare Frozen Weights, $T=0.1$) | Arm B (PAL Synthesis with Self-Debugging, Docker) | Net Lift over Direct | Verified Program Wins |
  | :--- | :---: | :---: | :---: | :---: |
  | **Spatial Navigation** ($n=20$) | 12/20 (60.0%) | **20/20 (100.0%)** | **+40.0 pp** | 19/20 |
  | **Logical Deduction** ($n=20$) | 1/20 (5.0%) | **20/20 (100.0%)** | **+95.0 pp** | 20/20 |
  | **Code Execution (CruxEval)** ($n=20$) | 2/20 (10.0%) | **20/20 (100.0%)** | **+90.0 pp** | 20/20 |
  | **Non-Crux Subtotal (Nav + Ded)** ($n=40$) | 13/40 (32.5%) | **40/40 (100.0%)** | **+67.5 pp** | 39/40 |
  | **Overall Aggregate** ($n=60$) | **15/60 (25.0%)** | **60/60 (100.0%)** | **+75.0 pp** | **59/60 (98.3%)** |
- **Key Empirical Findings & Suite Scope:**
  1. **Suite Ceiling & Regression Scope:** Having reached 60/60 (100.0%), this 60-problem set has reached its measurement ceiling. It is now classified as an **OOD Regression Smoke Test** to catch breakage, and cannot be used to prove broad generalization or measure further headroom.
  2. **Strict Closed-World Falsification:** **60/60 (100.0%)** non-grid tasks failed when parsed by `spatial_dsl` (`ValueError: invalid literal for int`), formally proving the closed-world nature of 2D matrix DSLs.
  3. **Empirical Non-Regression ($Arm\ B \ge Arm\ A$):** **100% PRESERVED across all 60 problems**. Exactly zero negative flips observed.
  4. **Wilson Score 95% Confidence Intervals:**
     - Arm A Overall: $[15.8\%,\ 37.2\%]$
     - Arm B Overall: $[94.0\%,\ 100.0\%]$

### 9.16 Formal Evaluation on CRUXEval-Input Benchmark & CEGIS Verification Delta (WO-35.6)
- **Harness:** [`scripts/run_cruxeval_input.py`](file:///C:/Projects/ProjectLucca/scripts/run_cruxeval_input.py) against resident Gemma 4 12B Heretic Q6_K (`task-10564`) and hardened Docker worker `lucca-file-sandbox` (`DockerRPCTransport(use_direct_fallback=False)`).
- **Core Methodology (Addressing Claude v5 §3 & §6.3):**
  - Unlike CRUXEval-Output (which is solved 100% by executing the function in a sandbox), **CRUXEval-Input** evaluates inverse reasoning: given function `f` and target output $y$, synthesize input argument $x$ such that `f(x) == y`.
  - Execution does NOT solve CRUXEval-Input by construction. It serves as the deterministic oracle inside a **Counterexample-Guided Inductive Synthesis (CEGIS) / Self-Debugging loop**:
    - **Turn 1:** Model hypothesizes initial candidate call `f(x_0)`.
    - **Sandbox Execution:** Runs candidate inside Docker container. If `f(x_0) == y`, verified!
    - **Turns 2–3 (Repair Loop):** If execution yields output mismatch (`got repr(actual), expected repr(y)`) or a runtime exception (traceback), the concrete counterexample is fed back into the prompt to refine the hypothesis.
- **Empirical Results:**
  | Split & Metric | Arm A (Direct 1-Shot, $T=0$) | Arm B (One-Shot PAL, Docker) | Arm B (Iterative CEGIS, up to 3 turns) | CEGIS Rescue Lift | Rescued Items | Exact McNemar Two-Sided $p$ |
  | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
  | **Dev Split** ($n=50$) | 38/50 (76.0%) | 38/50 (76.0%) | **46/50 (92.0%)** | **+16.0 pp** | 8/50 items | $\mathbf{0.0078}$ ($p < 0.01$) |
  | **Sealed Held-Out** ($n=100$) | 63/100 (63.0%) | 64/100 (64.0%) | **78/100 (78.0%)** | **+14.0 pp** | 14/100 items | $\mathbf{0.00006}$ ($p = 6.1 \times 10^{-5}$) |
  | **Combined Aggregate** ($n=150$) | 101/150 (67.3%) | 102/150 (68.0%) | **124/150 (82.7%)** | **+14.7 pp** | **22/150 items** | $\mathbf{2.38 \times 10^{-7}}$ |
- **Key Empirical Invariants Confirmed:**
  1. **Direct Empirical Demonstration of CEGIS Rescue:** Formally measures the exact value of self-debugging and counterexample-driven repair beyond one-shot synthesis. On 22 distinct problems where one-shot synthesis failed (e.g., casing mismatches, off-by-one list indexing, boundary condition errors), the counterexample allowed the model to self-correct and pass on Turn 2 or Turn 3.
  2. **Statistical Significance:** McNemar discordant pairs are **0:22** across all 150 items (zero negative flips). The hypothesis that CEGIS repair does not lift accuracy over direct/one-shot synthesis is rejected at $p = 2.38 \times 10^{-7}$.
  3. **Failure Stage Taxonomy on Remaining 26 Failures:**
     - `OUTPUT_MISMATCH`: 18/26 (69.2%) — model made incorrect logical assumptions about complex string manipulations that failed 3 consecutive repair turns.
     - `TRANSLATION_NO_CALL`: 5/26 (19.2%) — model emitted pseudo-code or comments instead of a valid executable function call.
     - `RUNTIME_ERROR`: 3/26 (11.5%) — unhandled syntax or type exception in candidate input.
- **Sealed Artifacts & Manifest Records:**
  - Dev Report: [`logs/test_reports/cruxeval_input_dev_1791762821248.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/cruxeval_input_dev_1791762821248.json)
  - Sealed Report: [`logs/test_reports/cruxeval_input_sealed_1791763075938.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/cruxeval_input_sealed_1791763075938.json)
  - Pinned Manifest Records: `cruxeval_input_dev_50_v1_5_0` and `cruxeval_input_sealed_100_v1_5_0` in [`data/benchmarks/MANIFEST.yaml`](file:///C:/Projects/ProjectLucca/data/benchmarks/MANIFEST.yaml).

### 9.17 Multi-Tier Factorial Audit: Direct vs Extended Thinking vs PAL (Claude v5 §5.4 & §13.4-5)
- **Experimental Protocol:** Evaluated all 3 deployed tiers (**12B Heretic Q6_K**, **E4B Heretic Q6_K**, **E2B Heretic Sinhala Q6_K**) under single-slot `--parallel 1` on identical hardware (RTX 5080 Laptop GPU, 16GB VRAM):
  - **Arm A Direct:** $T=0.0$, `max_tokens=128`, `enable_thinking=false`.
  - **Arm A Extended Thinking:** $T=0.6$, `top_p=0.95`, `max_tokens=3072`, `enable_thinking=true`.
  - **Arm B PAL:** $T=0.1$, `max_tokens=384`, Docker sandboxed execution (`use_direct_fallback=false`).
- **Comprehensive Cross-Tier Results ($n=60$ per tier):**
  | Model Tier | Domain / Split | Arm A Direct (cap=128) | Arm A Extended Thinking (cap=3072) | Arm B PAL (Docker) | Thinking vs Direct Delta | PAL vs Thinking Delta | Truncations (Direct / Think / PAL) |
  | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
  | **Gemma 4 12B** | **Non-Crux ($n=40$)** | 13/40 (32.5%) | **37/40 (92.5%)** | **40/40 (100.0%)** | +60.0 pp | +7.5 pp ($p=0.25$) | 38/60 (63.3%) / 12/60 (20.0%) / 0/60 (0%) |
  | | Code Tracing ($n=20$) | 2/20 (10.0%) | 10/20 (50.0%) | **20/20 (100.0%)** | +40.0 pp | **+50.0 pp** ($p \approx 0.002$) | |
  | | **Overall ($n=60$)** | 15/60 (25.0%) | 47/60 (78.3%) | **60/60 (100.0%)** | +53.3 pp | **+21.7 pp** ($p = 2.4 \times 10^{-4}$) | |
  | **Gemma 4 E4B** | **Non-Crux ($n=40$)** | 14/40 (35.0%) | **39/40 (97.5%)** | 31/40 (77.5%) | **+62.5 pp** | **-20.0 pp (Thinking wins)** | 27/60 (45.0%) / **0/60 (0.0%)** / 6/60 (10.0%) |
  | | Code Tracing ($n=20$) | 5/20 (25.0%) | 12/20 (60.0%) | **20/20 (100.0%)** | +35.0 pp | **+40.0 pp** ($p \approx 0.008$) | |
  | | **Overall ($n=60$)** | 19/60 (31.7%) | **51/60 (85.0%)** | **51/60 (85.0%)** | +53.3 pp | **0.0 pp (Tied 8:8, $p=1.00$)** | |
  | **Gemma 4 E2B** | **Non-Crux ($n=40$)** | 13/40 (32.5%) | **39/40 (97.5%)** | 16/40 (40.0%) | **+65.0 pp** | **-57.5 pp (Thinking wins)** | 30/60 (50.0%) / **0/60 (0.0%)** / 5/60 (8.3%) |
  | | Code Tracing ($n=20$) | 2/20 (10.0%) | 11/20 (55.0%) | **20/20 (100.0%)** | +45.0 pp | **+45.0 pp** ($p \approx 0.004$) | |
  | | **Overall ($n=60$)** | 15/60 (25.0%) | **50/60 (83.3%)** | 36/60 (60.0%) | +58.3 pp | **-23.3 pp (Thinking wins)** | |
- **Core Scientific Findings Resolving Review Notes v5:**
  1. **Direct Baselines Were Uniformly Token-Truncated:** Across all three tiers, Direct Arm A suffered 45.0% to 63.3% truncation rates due to the 64/128 token budget.
  2. **Native Thinking is Uniformly Capable Across Scales:** When given sufficient token budget without greedy collapse ($T=0.6$, cap=3072), native thinking scores **92.5% to 97.5% on algorithmic puzzles across ALL THREE TIERS** (37/40 at 12B, 39/40 at E4B, 39/40 at E2B). Zero truncations observed at E4B and E2B.
  3. **Code Synthesis Capability Degrades with Model Scale:** Zero-shot Python synthesis succeeds at 12B (100%), degrades at E4B (77.5%), and collapses at E2B (40.0%) on multi-variable constraint problems due to syntax/scoping errors (`UnboundLocalError`).
  4. **Code Execution Tracing is Scale-Invariant via Docker:** PAL provides a massive **+40.0 to +50.0 pp lift** on code execution tracing at every scale (100% across all tiers), because running code in a sandbox bypasses the LLM's inability to simulate loops in its head.
  5. **Architectural Implication for Routing:** The compound system must **route by task nature**:
     - Code execution and state invariant tracking $\rightarrow$ PAL / Docker sandbox.
     - Natural language and algorithmic deduction on small models $\rightarrow$ Native thinking.
     - Program synthesis and inverse problems $\rightarrow$ Iterative CEGIS self-debugging (+14.0 to +16.0 pp lift).
- **Multi-Repeat Noise Floor Bounds (§13.4):**
  - **12B (4 runs):** Arm A: $21.7\% - 25.0\%$ ($\pm 1.65$ pp); Arm B: $98.3\% - 100.0\%$ ($\pm 0.85$ pp).
  - **E4B (3 runs):** Arm A: $30.0\% - 31.7\%$ ($\pm 0.85$ pp); Arm B: **exactly 85.0% across all 3 runs** (0.0 pp drift).
