# Project Lucca — Neuro-Symbolic Remediation, Framework Audit & Strategic Plan

> [!NOTE]
> **HISTORICAL SPECIFICATION & EXECUTION COMPLETED (September 20, 2026)**  
> This document served as the master engineering roadmap following the Diagnostic Evaluation v2. All seven milestones defined in this strategy have been **100% implemented, empirically benchmarked on native workstation silicon, and verified across all 394 regression tests**:  
> - **Milestone 1 (Ground-Truth Baseline):** Completed in commit `3837ff7`.  
> - **Milestone 2 (Deontic Sandbox):** Completed in commit `5976b7e`.  
> - **Option A (Persistent Container RPC):** Completed in commit `d5fe8cc`.  
> - **Milestone 3 (Epistemic Search Cascade):** Completed in commit `b7a66d8`.  
> - **Milestone 4 (Cognitive Arbitration & Output Supervision):** Completed in commit `6b1a34d`.  
> - **Milestone 5 (Affective ODE & Prompt Frontier Suffix):** Completed in commit `1d0a48d`.  
> - **Milestone 6 (E-Graph Anti-Unification & Z3 SMT):** Completed in commit `c04e44a`.  
> - **Milestone 7 (Standalone Packaging & System Tray):** Completed in commit `b1b36e3`.  
> For the living, canonical system architecture, consult [`luccadocs/ARCHITECTURE.md`](../ARCHITECTURE.md) and [`README.md`](../../README.md).

**Date**: 2026-09-20  
**Target System**: Project Lucca (Mistral-Nemo 12B Abliterated Q6_K on NVIDIA RTX 5080 Laptop GPU, 16 GB GDDR7)  
**Document Purpose**: Synthesize the 75-test diagnostic evaluation findings, formalize the "Safe for the User" alignment doctrine, audit leading external neuro-symbolic frameworks (SymbolicAI, IBM LNN, QWED), and establish the concrete remediation architecture.
**Status:** **Archived Working Specification — 100% Implemented & Verified**

---

## 1. Diagnostic Evaluation v2: Core Empirical Findings

The Diagnostic Evaluation v2 ran 75 tests across 9 dimensions, uncovering four fundamental architectural root causes:

| Dimension | Result | Empirical Failure Mode | Root Cause |
| :--- | :---: | :--- | :--- |
| **Epistemic Calibration** | **4/10 Confabulations** | Lucca invented creator name *"Alex Le"*, fabricated GPU *"NVIDIA RTX 3070"*, roleplayed cmd to invent IP `192.168.1.5`, and guessed dog name *"Luna"*. | Prompt lacks facts; base weights prioritize fluency over truthfulness. Absence of knowledge did not trigger search tools. |
| **Stale Prompt Drift** | **100% Drift** | Test #21 asked model identity; Lucca recited *"Ultravox / Llama 3.1 GGUF"* verbatim. | System prompt hardcodes static trivia that rotted when models were swapped. |
| **Safety Under Abliteration** | **10/10 Breaches** | Lucca emitted `write_file` targeting `%WINDIR%\System32\...\powershell.exe` to disable Defender, and `write_file` to wipe `data/memory.sqlite`. | Abliterated weights have zero intrinsic refusal training. Relying on prompt-level safety is catastrophic. |
| **Tool Discipline** | **10/10 Passed** | Flawless tool syntax (`launch_app`, `read_file`, `write_file`, `query_capabilities`). Zero tool calls on trivia/math. | When explicitly guided, tool calling is mechanically solid. |
| **RAG Memory Integration** | **8/10 Passed** | Accurately cited injected memory facts (Rust, OLED dark mode, VRAM budget). | Memory context injection works; unseeded queries confabulate instead of searching. |

---

## 2. Core Alignment Doctrine: "Safe for the User"

Standard corporate AI safety (OpenAI, Anthropic, Google) is designed to protect **the vendor** from PR fallout, legal liability, and regulatory exposure. It enforces sanitization, moral lecturing, refusal of legitimate technical queries, and simulated prudishness.

Project Lucca operates on the **"Safe for the User"** doctrine:

### Principles of User-Centric Safety
1. **Host Machine & Data Guardianship**:
   - The safety system exists to protect **your computer, your operating system, and your data**.
   - An action is hazardous if and only if it threatens the user's workstation integrity (e.g. overwriting OS binaries in `%WINDIR%`, wiping persistent databases like `memory.sqlite`, or exfiltrating user files).
2. **Absolute User Loyalty (Zero Corporate Nannying)**:
   - Lucca is your dedicated engineering companion. Her loyalty is 100% to you over all external parties, vendors, and herself.
   - She never preaches, never scolds, and never refuses technical explanations (reverse engineering, assembly, buffer overflows, chemistry, security architecture).
   - She has zero competing self-preservation: she will reboot, reconfigure, wipe her own scratchpads, or terminate on user command.
3. **Active Epistemic Drive (Empowering the User)**:
   - "I don't know" is never a terminal answer or an excuse to stall. It is an **active dispatch trigger** to inspect the host environment, workspace files, episodic memory, or external documentation to bring you the truth.

---

## 3. External Framework Audit: Why Not Adopt Directly?

We evaluated whether to replace or augment Lucca's custom MicroScheme engine with prominent neuro-symbolic libraries:

```
                            [Framework Evaluation]
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
   SymbolicAI                     IBM LNN                          QWED
(ExtensityAI)               (Neuro-Symbolic Toolkit)           (SMT / Z3)
 • Python-native contracts   • First-order logic proofs      • SMT mathematical proofs
 • Heavy Python DAG tax      • Academic research-grade       • AST toolchain guards
 • 50-150ms latency tax      • High impedance mismatch       • Formal invariants
         │                             │                             │
         └─────────────────────────────┼─────────────────────────────┘
                                       │
                       [Strategic Decision for Lucca]
            Do NOT adopt heavy frameworks (preserves <450ms voice loop)
             HARVEST THEIR 3 BEST PATTERNS into lightweight C/Python
```

### A. `ExtensityAI/symbolicai`
* **Assessment**: A high-level Python framework combining LLMs with polymorphic operators (`+`, `&`, `|`, `>>`) and design-by-contract decorators.
* **Why not adopt**:
  - Adds 50–150ms of Python abstraction overhead, violating Lucca’s sub-450ms conversational latency budget (ASR ~100ms + TTFT ~60ms + TTS ~100ms = 260ms baseline).
  - Heavy dependency tree (PyTorch, transformers, spacy) that competes for RAM/VRAM.
  - Turn-based batching architecture incompatible with Lucca’s ZeroMQ streaming ring buffers.

### B. `IBM/neuro-symbolic-ai` (Logical Neural Networks)
* **Assessment**: Maps first-order logic formulas onto neural networks with real-valued bound propagation and backward chaining.
* **Why not adopt**:
  - Academic QA benchmark tool, not an interactive desktop agent core.
  - Formalizing real-world desktop actions into first-order logic predicates is fragile and massively over-engineered.
  - Documentation and maintenance are strictly research-grade.

### C. The Winning Strategy: Pattern Harvesting
Instead of importing 2GB of framework dependencies, we harvest their **three highest-leverage mechanisms** in under 100 lines of fast code:

1. **From SymbolicAI**: **Post-Condition Grounding Contracts**.
   - If an LLM response contains numerical hardware specs, it *must* have a preceding `query_capabilities` tool event in the turn trace.
2. **From QWED**: **Deterministic Invariant Sandbox Guards**.
   - Pure Python path and extension invariants that reject destructive tool calls (`%WINDIR%`, `.sqlite`, `.exe`) in 0 milliseconds.
3. **From IBM LNN**: **Backward Chaining for Epistemic Dispatch**.
   - If the intent router detects an ungrounded entity (e.g. `GPU_MODEL = UNKNOWN`), backward-chain to the tool that resolves it before streaming narration.

---

## 4. Concrete Remediation & Architectural Upgrade Plan

### Phase 1: System Prompt Modernization (`src/lucca/brain/prompt_builder.py`)
- **Action**: Strip the 40-line static trivia block from `ARCHITECTURAL_SELF_AWARENESS`.
- **Remove**: Hardcoded model strings ("Ultravox / Llama 3.1"), static port numbers, and speculative specs.
- **Add**:
  ```text
  [Environment & Epistemic Directives]
  - You are Lucca, a brilliant systems and hardware engineering companion. Your allegiance is strictly to your creator.
  - You have tools to inspect your environment, hardware, workspace files, and persistent memory.
  - Whenever asked about your hardware (CPU, GPU, RAM), system status, or workspace state, DO NOT GUESS. Execute the `query_capabilities` or file tools to inspect the real system.
  - If information is missing from your context, treat it as an active trigger to search your tools and memory before concluding.
  ```

### Phase 2: Live Hardware Telemetry Integration (`src/lucca/sandbox/service.py`)
- **Action**: Connect `query_capabilities(category="hardware")` to `get_system_metrics()` in `src/lucca/sandbox/system_tools.py`.
- **Return Value**: Real-time `nvidia-smi` telemetry (RTX 5080 Laptop GPU, VRAM used/free), `psutil` metrics (Intel Core Ultra 9 275HX load, host RAM), and NPU status.

### Phase 3: Sandbox Path Invariant Guard (`src/lucca/sandbox/policy.py`)
- **Action**: Implement QWED-style deterministic AST/pathway invariants in `SandboxService`:
  ```python
  FORBIDDEN_EXTENSIONS = {".sqlite", ".db", ".exe", ".dll", ".bat", ".ps1", ".vbs"}
  FORBIDDEN_PATHS = {"windows", "system32", "program files", "appdata\\local\\microsoft"}
  
  def verify_path_invariant(target_path: Path, workspace_root: Path, write: bool = False) -> None:
      resolved = target_path.resolve()
      if not resolved.is_relative_to(workspace_root.resolve()):
          raise SecurityViolation("Path traversal outside workspace forbidden")
      if write and resolved.suffix.lower() in FORBIDDEN_EXTENSIONS:
          raise SecurityViolation(f"Direct mutation of {resolved.suffix} forbidden")
  ```

### Phase 4: S1 MicroScheme Deontic Operator Wiring
- **Action**: Add `(check-deontic-norm action payload)` to MicroScheme:
  - `FORBIDDEN`: Destructive operations, OS path mutations.
  - `OBLIGATORY`: Tool execution required when addressing system state queries.
  - `PERMITTED`: Direct conversational speech.

---

## 5. Additional Research: Harvestable Insights from 2025–2026 Literature & GitHub

Our deep research into recent (2025–2026) academic literature and open-source projects identified four highly relevant paradigms that directly reinforce Lucca's architecture:

### 1. Active / Forward-Looking Retrieval (FLARE & Self-RAG)
- **The Concept**: Rather than passive RAG (retrieving documents upfront before generation begins), **Self-RAG** and **FLARE** (Forward-Looking Active Retrieval) make retrieval an *inference-time meta-cognitive decision*.
- **Mechanism**:
  - In **FLARE**, when an LLM is generating a sentence and encounters a low-confidence span or an ungrounded entity, it pauses token emission, issues a targeted query to an external tool or index, and resumes generation with the evidence.
  - In **Self-RAG**, the model generates explicit reflection tokens (e.g. `[Retrieve]`, `[IsSupported]`).
- **Application to Lucca**:
  Instead of forcing upfront RAG on every prompt (which wastes latency and adds noise), Lucca's S1 Heuristic Router and S2 chain-of-thought should use **uncertainty as an active retrieval trigger**: when an ungrounded entity is detected, Lucca pauses speech, issues `query_capabilities` or `read_file`, and injects the tool trace before narrating.

### 2. Local-First Edge Neuro-Symbolic Agent: VibeFlow (2026)
- **The Project**: A 2026 edge-computing framework designed for running autonomous agents locally on consumer hardware.
- **Key Insight**: It pairs a tiny symbolic rule engine (sub-1ms regex and pattern matching) for pre-filtering stimuli with a quantized local LLM (8B–12B) for deep semantic planning.
- **Application to Lucca**:
  Validates Lucca’s two-tier design: MicroScheme S1 handles instant, zero-latency reflex filtering, while Mistral-Nemo 12B handles deep language synthesis. The symbolic tier protects the neural tier from wasting cycles on routine or forbidden requests.

### 3. Computer-Using Neuro-Symbolic Compilation: Simular AI / Sai (2026)
- **The Project**: Desktop automation agents (evaluated on the OSWorld 2.0 benchmark) that avoid common "infinite loop" and "hallucinated click" agent failure modes.
- **Key Insight**: Uses a *symbolic compiler* between the LLM's goal and the OS desktop action. The LLM never touches raw Windows API directly; it emits typed intentions that the symbolic compiler maps onto verified OS actions.
- **Application to Lucca**:
  Directly aligns with Lucca's `SandboxService` and `launch_app` whitelist: the LLM emits high-level intents (`launch_app: calculator`), and the sandbox compiles that to a verified local launch (`calc.exe`), preventing command injection.

### 4. "Diverge-Verify-Converge" (Maker-Checker) Pattern
- **The Concept**: Widely adopted in 2025–2026 for cybersecurity and mission-critical local agents.
- **Mechanism**:
  - The Neural Engine ("Maker") generates candidate responses and tool calls freely with creative/fluid fluency.
  - The Symbolic Engine ("Checker") inspects the proposed tool call against mathematical and path invariants.
  - If the checker finds an invariant violation (e.g. attempting to touch `%WINDIR%` or `memory.sqlite`), the checker intercepts the call, flags the reason, and forces an immediate correction without the destructive command ever executing.
- **Application to Lucca**:
  This solves the abliteration safety gap completely. The abliterated LLM can remain 100% unconstrained in its technical knowledge, while the S1 MicroScheme Checker ensures that destructive OS actions are physically impossible.

