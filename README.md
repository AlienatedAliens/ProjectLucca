# Project Lucca — Standalone Neuro-Symbolic Desktop Companion

> **State of the Union:** 100% Complete & Production Frozen on Native Workstation Silicon  
> **Release Artifact:** `dist/Lucca/Lucca.exe` (25.9 MB standalone Windows executable)  
> **Target Workstation:** MSI Vector 16 HX AI (Intel Core Ultra 9 275HX, NVIDIA GeForce RTX 5080 Laptop GPU 16GB VRAM, 16GB Host RAM)  
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
                     │  • Intel NPU / OpenVINO Faster-Whisper ASR    │
                     │  • Push-to-Talk & Energy VAD (<50ms barge-in) │
                     │  • Shared-memory atomic circular ring buffers │
                     └───────────────────────┬───────────────────────┘
                                             │
                                             ▼
                     ┌───────────────────────────────────────────────┐
                     │          COGNITIVE ROUTER & EPSTEMICS         │
                     │  • Conformal Prediction Intent Classifier     │
                     │  • 5-Substrate Epistemic Search Cascade       │
                     │  • Belnap FOUR Evidential Bilattice           │
                     └───────┬───────────────────────────────┬───────┘
                             │                               │
            FAST PATH (<150ms)│                               │ DELIBERATIVE PATH (~450-700ms)
                             ▼                               ▼
┌───────────────────────────────────────────┐   ┌───────────────────────────────────────────┐
│     SYSTEM 1: COMPILED SYMBOLIC CORE      │   │         SYSTEM 2: NEURAL CORE             │
│  • MicroScheme (LISP) AST Interpreter     │   │  • Mistral NeMo 12B Instruct Abliterated  │
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
- **System 2 (Neural Deliberation):** **Mistral NeMo 12B Instruct Abliterated (Q6_K GGUF)** running natively on the RTX 5080 Laptop GPU via `llama-server.exe` (16,384 context, Q8_0 KV cache, Flash Attention, 12.5 GB resident clamp). Provides personality, conversational fluency, and complex planning.
- **System 1 (Compiled Symbolic Reflexes):** Isolated MicroScheme LISP engine executing deterministic `State → Plan` procedures in microseconds with gas metering and zero runtime memory mutation.
- **Cognitive Event Bus:** Bidirectional coordination between System 1 and System 2 using typed signals: `(yield-to-core reason context)` and `(interrupt-core reason)`.
- **E-Graph Macro Synthesis (Babble/Stitch):** Automatically identifies recurring execution traces in SQLite history ($N \ge 3$) and uses first-order syntactic anti-unification to synthesize canonical `(defmacro ...)` procedures, turning conscious reasoning into compiled muscle memory.
- **Z3 SMT Formal Theorem Prover:** Formally proves that candidate rules are satisfiable, contingent (non-tautological), and mathematically cannot violate deontic path invariants (blocking path traversal, system directory mutations, credential leakage, and unauthorized executable writes) before entering quarantine.

### 2. Epistemic Calibration & Anti-Hallucination
- **5-Substrate Epistemic Search Cascade:** Escalates knowledge gap queries through five prioritized substrates: Substrate 0 (Telemetry) $\rightarrow$ Substrate 1 (Workspace ASTs) $\rightarrow$ Substrate 2 (Vector/FTS5 Memory) $\rightarrow$ Substrate 3 (Web Floor) $\rightarrow$ Substrate 4 (Epistemic Abstention).
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

---

## 3. Physical Hardware Placement

| Compute Hardware | Physical Specification | Workload Assignment |
| :--- | :--- | :--- |
| **dGPU** | NVIDIA GeForce RTX 5080 Laptop (16 GB GDDR7, Blackwell `sm_120`) | **llama-server.exe**: Mistral NeMo 12B Q6_K, 16K context, Q8_0 KV cache, Flash Attention ($\le 12.5\text{ GB}$ clamp). |
| **NPU** | Intel AI Boost NPU (Arrow Lake-HX via OpenVINO native Windows) | **Embeddings**: 384-D vector embeddings (`all-MiniLM-L6-v2` via OpenVINO). |
| **dGPU** _(audio)_ | _(shared with LLM above)_ | **ASR**: `distil-small.en` via faster-whisper (CUDA float16, +555 MiB VRAM). **TTS**: Kokoro-82M ONNX on CPU. **VAD**: Silero on CPU. |
| **CPU** | Intel Core Ultra 9 275HX (24 cores / 32 threads) | **Core Orchestrator & Reasoning**: ZeroMQ IPC bus, MicroScheme LISP engine, Z3 SMT prover, SQLite WAL + `sqlite-vec` + FTS5, Docker RPC. |
| **Host RAM** | 16 GB Physical Host Memory | System memory pool; WSL2 container memory clamped to 4.5 GB (`4608MB`) via `C:\Users\<user>\.wslconfig`. |

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
| **Prefix KV-Cache Optimization** | Prompt Frontier Suffix on NeMo 12B (RTX 5080) | **$8.58\times$ faster** ($46.84\,\text{ms}$ vs $402.05\,\text{ms}$) | **Verified** |
| **Epistemic Abstention Accuracy**| 25-question confabulation test battery | **$0 / 25$ hallucinations (100% adherence)** | **Verified** |
| **Z3 SMT Verification Time** | Automated SAT, contingency, and path proofs; unmodeled predicates fail closed (`UNMODELED_PREDICATE`) | **$\le 25\,\text{ms}$** (Budget: $\le 500\,\text{ms}$) | **Verified** |
| **Frozen Packaging Acceptance** | `Lucca.exe --check` 7-point native hardware audit | **$7 / 7$ criteria PASSED (code 0)** | **Verified** |
| **Static Architectural Gates** | Zero `Any` types across `core`, `brain`, `reasoning` | **$8 / 8$ gates PASSED (code 0)** | **Verified** |
| **Full Regression Test Suite** | 52 test modules covering all subsystems | **$394 / 394$ PASSED (100% GREEN in 97.49s)** | **Verified** |

---

## 5. Quickstart Guide

### Option A: Launch Pre-Built Standalone Executable (Recommended)
You can run Project Lucca directly from the standalone compiled distribution:
```powershell
# 1. Run full 7-point environment and hardware diagnostic check
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

## 6. Master Documentation Index (`docs/`)

The repository adheres to strict truth-in-documentation governance (`docs/README.md`):

| Document | Purpose |
| :--- | :--- |
| [`docs/README.md`](./docs/README.md) | **Governance & Documentation Master Index**: Three-tier documentation lifecycle and full roadmap status. |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | **Master System Architecture**: Process topology, IPC, MicroScheme runtime, memory, sandbox, and packaging hierarchy. |
| [`docs/DECISIONS.md`](./docs/DECISIONS.md) | **Canonical Decisions Register**: All ratified ADRs (`D-AUD-01` through `D-PKG-01`). |
| [`docs/MODEL_STRATEGY.md`](./docs/MODEL_STRATEGY.md) | **Neural Model Strategy**: Mistral NeMo 12B Q6_K abliterated deployment, VRAM clamp, and KV-cache architecture. |
| [`docs/IMPLEMENTATION_WALKTHROUGH.md`](./docs/IMPLEMENTATION_WALKTHROUGH.md) | **Complete Engineering Walkthrough**: Chronological logs for Milestones 1–7 with raw silicon scorecards. |
| [`docs/NEUROSYMBOLIC_RESEARCH_PAPER.md`](./docs/NEUROSYMBOLIC_RESEARCH_PAPER.md) | **Formal Academic Paper**: *"Project Lucca: A Sub-450ms Neuro-Symbolic Cognitive Architecture for Local Voice Agents"*. |
| [`docs/specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md`](./docs/specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md) | **Capability Status Map**: Exhaustive classification of all system capabilities against verified reality. |
| [`docs/archive/`](./docs/archive/) | **Historical Archives**: Deprecated pre-audit specs, earlier exploratory notes, and legacy drafts. |

---

## 7. Security & Operational Invariants

1. **Zero Cloud Exfiltration:** Zero audio recordings, text transcripts, memory entries, or tool parameters leave the local workstation.
2. **Container Jailing:** Filesystem mutations occur strictly inside isolated WSL2 Docker containers (`--network none`); host execution fallback is hardcoded to false.
3. **Shell Blacklist:** `cmd.exe`, `powershell.exe`, `.bat`, `.ps1`, and interactive shells are strictly banned from execution.
4. **SMT Invariant Enforcement:** All procedural rules must pass formal Z3 satisfiability, non-tautology, and deontic path traversal proofs before registration.
5. **Human Promotion Gate:** Induced rules are registered strictly in `QUARANTINE` mode; automatic promotion to active execution is structurally impossible.
6. **Epistemic Truth Invariance:** Affective states have strictly $0.0$ evidential weight over truth evaluations or security permissions.
