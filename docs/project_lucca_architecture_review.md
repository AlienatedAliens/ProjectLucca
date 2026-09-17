# Project Lucca — Architectural Research & Technical Deep-Dive

## Executive Summary & Verdict

Project Lucca's design brief represents an **exceptionally mature, disciplined, and production-grade architecture** for a local AI companion. It avoids the common traps of modern agent frameworks (unbounded LLM loops, hallucinated memory pollution, brittle code-gen, uncalibrated routing) and replaces them with **measurable acceptance criteria, strict provenance boundaries, hardware-aware execution, and symbolic rule compilation**.

This document provides a component-by-component research breakdown, validates the technical assumptions, identifies critical platform/driver constraints, and proposes concrete architectural patterns to ensure seamless execution across all phases.

---

## 1. System Topology & Host vs. Sandbox Partitioning

### The Intel NPU vs. WSL2 Reality Check
A critical architectural consideration involves the physical split between the Windows 11 Host, WSL2, and Docker containers:

> [!WARNING]
> **Intel NPU is Not Exposed Inside WSL2 or Linux Containers.**
> As of late 2024 / 2026, Intel's NPU driver (via OpenVINO / Level Zero / DirectML) does not provide kernel device nodes (`/dev/accel/accel0`) into WSL2 virtual machines. Inside WSL2 or a Linux Docker container, `openvino.Core().available_devices` only detects `CPU` and `GPU`. The NPU is accessible **exclusively on the Windows 11 host**.

Conversely, **vLLM** has first-class Linux support and runs optimally within WSL2 with NVIDIA CUDA passthrough (`sm_120`), but running vLLM natively on Windows requires extensive Triton and POSIX emulation workarounds.

### Recommended System Partition Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            WINDOWS 11 HOST                                  │
│  - Push-to-Talk Mic Capture (sounddevice / PyAudio)                         │
│  - Silero VAD (ONNX / OpenVINO)                                             │
│  - Kokoro TTS (OpenVINO INT8 -> Native Intel NPU)                           │
│  - Audio Output & Sprite / Lip-Sync Driver (Pygame / PyQt6 / Raylib)        │
│  - ModernBERT Router / Classifier (OpenVINO INT8 -> Native Intel NPU)      │
│  - Orchestrator Core & LISP Engine (Python 3.12+ CPU)                       │
│  - Three-Tier Memory: ChromaDB (Disk/CPU) + NetworkX (Disk/CPU)             │
│                                │                                            │
│        gRPC / Unix Socket /    │ HTTP (localhost:8000)                      │
│        Named Pipe              │                                            │
│                                ▼                                            │
│  ┌────────────────────────────────────────────────────────┐                 │
│  │                    WSL2 SUBSYSTEM                      │                 │
│  │  - vLLM Server: Ultravox 8B (RTX 5080 16GB, CUDA 12.8) │                 │
│  │    (Dedicated 10GB VRAM, NVFP8 / Q6 GGUF)              │                 │
│  └────────────────────────────────────────────────────────┘                 │
│                                │                                            │
│        Docker Engine API /     │ Isolated IPC                               │
│        Restricted Bridge       │                                            │
│                                ▼                                            │
│  ┌────────────────────────────────────────────────────────┐                 │
│  │               DOCKER SANDBOX (WSL2 / Linux)            │                 │
│  │  - File Tool (Chrooted to mounted workspace volume)    │                 │
│  │  - Playwright Headless Browser (Read-only web fetch)    │                 │
│  │  - Ephemeral Workspace + Persistent Volume separation  │                 │
│  │  - Network egress: Blocked RFC1918 / Local Subnet       │                 │
│  └────────────────────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Hardware Budget & Resource Allocation (MSI Vector 16 HX AI)

### A. System RAM (16GB Total) — The Primary Physical Bottleneck
The host has 16GB of system RAM shared across Windows 11, WSL2, OpenVINO NPU buffers, Playwright, and Python runtimes. This is the tightest constraint in the system.

| Process / Component | Host Location | Expected RAM Footprint | Mitigation / Optimization |
|---|---|---|---|
| Windows 11 Base OS + Services | Host | 3.8 GB – 4.5 GB | Minimal background apps |
| vLLM Host Runtime in WSL2 | WSL2 | 2.5 GB – 3.5 GB | Set `memory=4GB` in `.wslconfig` |
| OpenVINO NPU Runtimes (Kokoro + BERT) | Host | ~500 MB – 800 MB | Zero-copy NPU shared buffers |
| Python Orchestrator, ChromaDB, NetworkX | Host | ~600 MB – 1.0 GB | SQLite-backed Chroma, no huge cache |
| Docker Sandbox + Playwright Chromium | Docker / WSL2 | ~1.0 GB – 1.8 GB | Headless, single tab, killed between calls |
| **Total Concurrently Active** | — | **~8.4 GB – 11.6 GB** | **Leaves 4.4GB – 7.6GB safety margin** |

> [!IMPORTANT]
> **WSL2 Memory Clamping**: By default, WSL2 can allocate up to 50% or 80% of host RAM on demand, which would trigger Windows paging when Playwright runs. Create `%USERPROFILE%\.wslconfig` with:
> ```ini
> [wsl2]
> memory=5GB
> swap=4GB
> localhostForwarding=true
> ```

### B. VRAM Allocation (RTX 5080 16GB)
- **Model:** Ultravox 8B (e.g., `fixie-ai/ultravox-v0_5-llama-3_2-1b` or `ultravox-v0_5-llama-3_1-8b`).
- **Quantization:**
  - **Q6_K (GGUF)**: Base weights = ~6.2 GB; Whisper encoder = ~1.2 GB; Total weights = ~7.4 GB.
  - **NVFP8 (W8A8)**: Base weights = ~8.0 GB; Whisper encoder = ~1.2 GB; Total weights = ~9.2 GB.
- **KV Cache Budget:** Set vLLM `--gpu-memory-utilization 0.65` (~10.4 GB ceiling).
- **Headroom Remaining:** ~5.6 GB VRAM free, ensuring no OOM spikes under high concurrent context or CUDA graph allocations.

---

## 3. Detailed Component & Phase Feasibility

### Phase 1: Ears + Voice (Ultravox ↔ Kokoro Pipeline)

#### 1. Ultravox 8B via vLLM on RTX 5080 (Blackwell SM120)
- **Status:** vLLM has native support for Ultravox (`vllm.model_executor.models.ultravox`).
- **Blackwell Compatibility:** RTX 5080 requires CUDA 12.8+ and `TORCH_CUDA_ARCH_LIST=12.0`. 
- **Inference Pattern:** Audio is passed as base64 or raw PCM tensor into the vLLM OpenAI-compatible endpoint with the `<|audio|>` token tag.
- **Quantization Recommendation:** Use **FP8 (W8A8)** or **GGUF (via vllm-gguf-plugin)**. On Blackwell architecture, native FP8 tensor cores offer superior throughput and lower latency than GGUF dequantization.

#### 2. Kokoro TTS (OpenVINO INT8 on Intel NPU)
- **Model Characteristics:** 82M parameters, StyleTTS2 / ISTFTNet architecture.
- **NPU Compatibility:** OpenVINO natively supports compiling Kokoro for Intel NPU via the `NPU` device plugin.
- **Phonemization Dependency:** Kokoro requires `espeak-ng` or `misaki` for G2P (grapheme-to-phoneme). On Windows, bundle `espeak-ng.dll` or use the pure-Python `misaki` phonemizer to avoid missing C-library dependencies.
- **Latency Optimization (Streaming Chunking):** To achieve the 300–600ms latency target:
  - Do **not** wait for the full LLM response.
  - Accumulate streaming tokens from Ultravox until the first sentence terminator (`.`, `!`, `?`, or `,` after $\ge 6$ tokens).
  - Immediately dispatch the sentence chunk to Kokoro on the NPU while Ultravox generates the remainder.
  - Overlap audio playback of chunk $k$ with NPU synthesis of chunk $k+1$.

#### Latency Budget Verification (Target: 300–600ms)
- Push-to-Talk release to buffer send: ~10ms
- Ultravox Audio Encoder (Whisper pass on RTX 5080): ~35ms
- Ultravox TTFT (Time to First Token) on Blackwell: ~45ms
- Token generation for first clause (8 tokens @ 120 tok/s): ~65ms
- Kokoro NPU synthesis of first clause (~1.2s audio): ~110ms
- Audio buffer fill to soundcard start: ~25ms
- **Estimated Total Latency:** **~290ms – 380ms** (well within the 300–600ms target).

---

### Phase 2: Tools + Sandbox

#### 1. Path-Traversal Protection
Standard `../` sanitization via string matching is notoriously flawed due to symlinks and URL decoding.
**Enforced Pattern:**
```python
import os
from pathlib import Path


def resolve_safe_path(workspace_root: Path, user_path: str) -> Path:
    # Resolve canonical absolute path resolving all symlinks
    canonical_root = workspace_root.resolve(strict=True)
    target = (canonical_root / user_path).resolve()

    # Verify target is strictly within the workspace directory
    if not target.is_relative_to(canonical_root):
        raise PermissionError(f"Access denied: path '{user_path}' escapes workspace sandbox.")
    return target
```

#### 2. Container Network Egress Clamping
To prevent local-subnet exploration (SSRF, lateral movement):
- Docker run options: `--cap-drop=ALL --security-opt=no-new-privileges:true`
- Egress iptables filter blocking RFC1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`) while permitting DNS (port 53) and public web outbound (80/443).

#### 3. The "App-Launcher" Architectural Dilemma
- If the tool sandbox runs inside Docker/WSL2, an isolated container **cannot and should not** arbitrarily execute host Windows executables.
- **Solution:** A **Mediated Host Bridge**.
  - The sandbox communicates tool requests back to the Host Orchestrator.
  - For `app_launch`, the tool in the container emits a structured intent `{"tool": "launch_app", "app_id": "..."}`.
  - The **Host Orchestrator** checks an immutable local whitelist (e.g. `{"notepad": "notepad.exe", "calc": "calc.exe", "vscode": "code.cmd"}`) and launches via `subprocess.Popen` on Windows.
  - Arbitrary executable paths or shell scripts from the sandbox are rejected.

---

### Phase 3: Three-Tier Memory & Anti-Hallucination Gate

```
                  ┌────────────────────────────────────────┐
                  │          CANDIDATE MEMORY ENTRY        │
                  │  - content: str                        │
                  │  - timestamp: float                    │
                  │  - provenance: ProvenanceTag           │
                  │  - signature / verification token      │
                  └───────────────────┬────────────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   PROVENANCE WRITE GATE   │
                        └─────────────┬─────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            │                                                   │
   [ Provenance Matches ]                              [ Provenance is ]
   - USER_EXPLICIT_STATEMENT                           - LLM_NARRATION
   - VERIFIED_TOOL_OUTPUT                              - UNVERIFIED_INFERENCE
   - DETERMINISTIC_LISP_ASSERTION                      - NULL / UNKNOWN
            │                                                   │
            ▼                                                   ▼
┌───────────────────────────┐                       ┌───────────────────────┐
│ WRITE COMMITTED           │                       │ HARD REJECT           │
│ - ChromaDB (Vector)       │                       │ - Raise / Log Drop    │
│ - NetworkX (Knowledge KG) │                       │ - Memory Unaltered    │
└───────────────────────────┘                       └───────────────────────┘
```

#### 1. Provenance Tag Architecture
The "Hallucination-Write Test" hard requirement is guaranteed structurally:
- Only data structures instantiated by the push-to-talk speech parser (`USER_EXPLICIT`) or the sandbox container output handler (`TOOL_OUTPUT`) receive valid `ProvenanceTag` cryptographically signed or object-typed in-memory.
- The LLM's conversational reply generator produces raw text strings. If the LLM narrates *"I have saved your document to /etc/passwords and your favorite color is magenta,"* the memory manager inspects the origin. Because it lacks a `TOOL_OUTPUT` or `USER_EXPLICIT` envelope, the commit is **instantly dropped**.

#### 2. Hybrid Retrieval (Dense + Sparse RRF)
- Pure cosine vector search fails on literal identifiers (e.g., error codes like `ERR_403_INVALID_TOKEN`, file names, exact serials).
- **Architecture:** Combine ChromaDB (Dense, e.g. `bge-small-en-v1.5` or `all-MiniLM-L6-v2`) with BM25 (Sparse, via `rank-bm25` or SQLite FTS5).
- Merge using **Reciprocal Rank Fusion (RRF)**:
  $$RRF\_Score(d) = \sum_{m \in \{Dense, Sparse\}} \frac{1}{k + rank_m(d)} \quad (k = 60)$$

---

### Phase 4: Executive Router (Heuristic Baseline)

The heuristic router must balance three dispatch branches:
1. `DIRECT_TO_LLM`: Conversational banter, brainstorming, emotional reflection, open-ended explanations.
2. `CHECK_LISP_FIRST`: Known parameterized tasks (e.g., *"clean my workspace"*, *"summarize downloads folder"*, *"check system status"*).
3. `CALL_COMPILED_TOOL`: Direct invocation of registered sandbox tools.

**Telemetry Logging Schema (`DecisionRecord`):**
```python
@dataclass(frozen=True)
class DecisionRecord:
    record_id: str
    user_query: str
    active_context_summary: dict
    heuristic_decision: str  # "DIRECT_TO_LLM" | "CHECK_LISP_FIRST" | "CALL_TOOL"
    execution_time_ms: float
    user_satisfaction: bool  # Implicit: no correction in next turn; Explicit: feedback
    tool_success: bool | None
    ground_truth_optimal_action: str | None
```
Logging 100+ verified decisions creates the non-synthetic dataset needed for Phase 6.

---

### Phase 5: Reflection Loop & LISP Symbolic Reasoning

#### Why S-Expressions (LISP) instead of Python Code-Gen?
1. **Safety & Sandboxing:** Python `exec()` or `eval()` can break out of any sandbox or leak process state. A minimal Scheme / S-expression evaluator written in 250 lines of Python has **zero** arbitrary code execution capability.
2. **Homoiconicity:** Code is data. A LISP rule is represented directly as nested lists:
   ```scheme
   (rule (name "workspace_cleanup")
         (pattern (intent "clean_files") (older_than_days 7))
         (action (tool_call "fs_delete_pattern" "*.tmp" 7)))
   ```
3. **Deterministic Static Analysis:** Dependency trees, pre-conditions (STRIPS/HTN), and invariant violations can be proven before execution.

#### Gating Mechanics
- **5-Strike Promotion Gate:**
  A candidate rule proposed by the LLM reflection pass is written to `quarantine_rules.json`. Each time a live user request matches the candidate rule, the rule is evaluated in *shadow mode* (evaluated alongside the standard path). If shadow output matches ground-truth user intent with zero failures across $\ge 5$ distinct sessions, it is promoted to `active_rules.lisp`.
- **Demotion Path:** Any contradictory observation (e.g. user says *"no, that's not what I wanted"*, or a tool error occurs) immediately triggers a demotion counter. At 1 failure, the rule is reverted to quarantine.
- **Reflection Apply-Rate Telemetry:**
  $$\text{Apply Rate} = \frac{\text{Promoted Rules}}{\text{Reflection Worker Executions}}$$
  If Apply Rate $< 0.05$ after 50 runs, raise an alarm indicating prompt degradation or overly restrictive candidate proposals.

---

### Phase 6: Trained Dual Classifier

#### 1. Hardware-Aware Model Split
As confirmed in research, **OpenVINO does not support ONNX `TreeEnsembleClassifier` or `ZipMap` operators**. Therefore:
- **Semantic Text Classifier (ModernBERT / DistilBERT):**
  - Runs on the **Intel NPU** via OpenVINO INT8.
  - Takes raw user text and extracts intent embeddings / category logits.
- **Tabular / Structured Router (XGBoost / LightGBM):**
  - Runs on the **Host CPU** using native C++ bindings (`xgboost.predict` / `lightgbm`).
  - Inputs: Text embedding features (from NPU), state features (recent tool call counts, task depth, time of day, active flags).
  - CPU inference latency for a 50-tree LightGBM model is $< 0.5\text{ms}$ on Arrow Lake P-cores.

#### 2. Calibration & Conformal Prediction
- **Calibration:** Raw tree scores or softmax outputs are uncalibrated. Fit an **Isotonic Regression** or **Platt Scaler** on the validation log split. Validate using **Brier Score** ($BS = \frac{1}{N}\sum (f_t - o_t)^2$) and Expected Calibration Error (ECE $\le 0.05$).
- **Conformal Fallback:**
  Compute non-conformity scores $\alpha_i = 1 - \hat{P}(y_i \mid x)$. If the conformal prediction set contains multiple actions or the confidence is below significance level $1 - \epsilon$, trigger the **Safe Default**: escalate to full Ultravox LLM reasoning or prompt the user for clarification.

---

## 4. Phase-by-Phase Risk Matrix & Mitigation Guide

| Phase | Identified Risk | Impact | Concrete Mitigation |
|---|---|---|---|
| **Phase 1** | RTX 5080 (Blackwell) CUDA mismatch | Build failure on default wheels | Use PyTorch $\ge 2.6$ with CUDA 12.8; build vLLM with `TORCH_CUDA_ARCH_LIST=12.0` |
| **Phase 1** | OpenVINO NPU in WSL2 | NPU undetected, falls back to CPU | Run Kokoro & OpenVINO on **Windows Host**, not inside WSL2 |
| **Phase 2** | App launcher breaks sandbox | Security breach or execution failure | Use Host-Mediated Whitelist Bridge via local IPC |
| **Phase 2** | Playwright memory leak | 16GB RAM exhaustion | Run single-instance headless browser; terminate browser context per call |
| **Phase 3** | Hallucination leakage into memory | Agent memory corruption | Strict `ProvenanceTag` verification gate on all write paths |
| **Phase 5** | Reflection worker silent no-op | Rules never get generated | Enforce telemetry tracking of candidate generation & apply rate |
| **Phase 6** | OpenVINO TreeEnsemble failure | Engine crashes on NPU model load | Keep XGBoost/LightGBM on native CPU; keep only encoders on NPU |

---

## 5. Architectural Recommendations & Next Steps

1. **Adopt the Split Host/WSL2 Architecture Immediately:**
   Do not attempt to containerize the entire agent into WSL2. Keep senses (mic/speaker), TTS (Kokoro on NPU), sprite UI, and the orchestrator on native Windows 11. Run vLLM in WSL2 with GPU passthrough, and run tools in Docker.
2. **Prioritize Streaming in Phase 1:**
   Do not wait for full LLM sequence generation before initiating Kokoro synthesis. Implement the sliding sentence-buffer mechanism on Day 1 of Phase 1 to guarantee hitting the 300–600ms latency target.
3. **Use a Zero-Dependency Micro-LISP for Phase 5:**
   Implement a Norvig-style S-expression interpreter in pure Python rather than bringing in heavy external Scheme/Racket runtimes. This ensures 100% control, deterministic debugging, and instantaneous execution.
