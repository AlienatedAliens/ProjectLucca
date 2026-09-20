# Project Lucca — Canonical Decisions Log (Post-Audit Baseline)

**Status:** Authoritative Post-Audit Record  
**Version:** 0.2.0  
**Updated:** September 2026  
**Charter Reference:** Ratified per D-AUD-19, consolidating all owner decisions from the audit period (`04_OWNER_DECISIONS.md`).

---

## 1. Architectural & Governance Decisions

### D-AUD-01 — Strict Typing Invariant
- **Decision:** Charter §5.5 ("zero `Any` in public interfaces") is a hard architectural invariant. Violations across `core`, `brain`, and `reasoning` are graded S0/INVARIANT and strictly forbidden by static gates.
- **Status:** Ratified & Enforced (`test_no_any_in_core_public_api`, `test_no_any_in_brain_public_api`, `test_no_any_in_reasoning_public_api`).

### D-AUD-02 — Phase 0 S5 RSS Metric Redefinition
- **Decision:** The legacy WorkingSet64 metric of a GPU-resident process is invalid for measuring host RAM. Resident host RSS must be measured using private working set bytes via `psutil.Process().memory_info().rss`.
- **Status:** Ratified & Enforced across telemetry, audit scripts, and tests.

---

## 2. Persona, UI & Voice Strategy

### D-AUD-03 — Voice Canonicalization & Persona Strip
- **Decision:** 
  1. `config/persona.toml -> voice` is the single canonical source of voice configuration. Default voice is **`genki_heroine`**.
  2. The third-party Chrono Trigger character identity ("Lucca Ashtear from 1000 AD", glasses/helmet/satchel lore) is completely stripped from the personality and prompt layers.
  3. The project name "Lucca" and the energetic "genki" voice archetype are retained for an original, product-owned companion identity.
- **Status:** Ratified & Enforced.

### D-AUD-04 — Persona File Precedence
- **Decision:** Runtime configuration resolves strictly from `<LUCCA_HOME>\config\persona.toml`. The repository copy serves as a first-run template.
- **Status:** Ratified & Enforced.

### D-AUD-14 / D-AUD-19 — Elimination of Fictional Capabilities
- **Decision:** The fictional capability layer (non-existent codebase inspection on port 5557-5559, simulated temporal logic gates, and fabricated latency badges) is completely eliminated from prompts, manifests, and UI surfaces.
- **Status:** Ratified & Enforced via `test_capability_claims_real` and `test_no_fabricated_metrics`.

### D-AUD-17 — Latency Badge Honesty
- **Decision:** The hardcoded `"382 ms"` latency badge in the UI is removed. The badge is hidden by default and only displayed when populated with measured `TurnTrace.total_e2e_ms`.
- **Status:** Ratified & Enforced.

### D-AUD-18 — UI Structure
- **Decision:** Retain the 10-tab settings window, refactored into a modular `ui/settings/` layout with clean separation between UI widgets and core orchestrator state.
- **Status:** Ratified & Enforced.

---

## 3. Inference, Model Supply & ASR Strategy

### D-AUD-05 — Model Supply & Verification (Option A)
- **Decision:** Deploy true Ultravox Q6_K backbone with Q8_0 mmproj; pin cryptographic checksums in `models/MANIFEST.json`; enforce validation in downloaders and before `llama-server` process launch.
- **Status:** Ratified & Enforced.

### D-AUD-06 — Evaluation of Alternative Text Brains (Spike)
- **Decision:** Evaluate alternative text models for Cascade / Transcript-First mode (Option D), including **gpt-oss-20b** and **Mistral NeMo 12B**, measuring TTFT, decode throughput, VRAM occupancy, and tool-call validity within the 9.5 GB dGPU budget.
- **Status:** Queued & In Progress.

### D-AUD-15 — ASR Device Ladder & Architecture
- **Decision:** Wire the configured `whisper-large-v3-turbo-ov` model with OpenVINO device ladder (NPU $\rightarrow$ GPU $\rightarrow$ CPU), replacing the temporary `distil-small.en` CPU shortcut.
- **Status:** Ratified — Implementation Queued (Active runtime remains `distil-small.en` on CPU int8 via `faster-whisper` in `src/lucca/senses/asr.py`).

### D-AUD-16 — Anime DSP Audio Processing
- **Decision:** Apply formant-shifting and high-frequency excitation DSP post-Kokoro synthesis to give the output an authentic anime heroine aesthetic.
- **Status:** Ratified & Enforced (`AnimeVoiceDSP` chain in `src/lucca/senses/dsp_chain.py` wired into `TTSWorker.synthesize()` post-`engine.create` and pre-int16 in `src/lucca/senses/tts.py`, dynamically controlled via UI Tab 6 and IPC).

---

## 4. Security, Sandbox & Memory Controls

### D-AUD-07 — `tool_contents` Untrusted Store
- **Decision:** Tool execution outputs returned from containers are stored with `TOOL_CONTENT_UNTRUSTED` provenance, subject to indirect prompt injection containment.
- **Status:** Ratified & Enforced.

### D-AUD-08 — Memory Backup Retention
- **Decision:** Database backups follow calendar-day UTC grouping (14 daily backups + 8 weekly Sunday backups).
- **Status:** Ratified & Enforced.

### D-AUD-09 — Cryptographic Provenance for Admin Edits
- **Decision:** Manual memory additions, updates, and deletions via the UI or admin CLI must pass through `ProvenanceGate` with HMAC/Ed25519 signatures. Arbitrary `signature="manual"` bypasses are prohibited.
- **Status:** Ratified & Enforced.

### D-AUD-10 — Application Launcher Whitelist
- **Decision:** Application launching is restricted to `config/tool_whitelist.toml`. Arbitrary shells (`cmd.exe`, `powershell.exe`) are strictly excluded from execution.
- **Status:** Ratified & Enforced.

### D-AUD-11 — Decision Telemetry & Auto-Labeling
- **Decision:** Decision records allow label updates, but the data volume gate ($\ge 600$ records) counts only the first label per decision to prevent synthetic label inflation.
- **Status:** Ratified & Enforced.

### D-AUD-12 — Rule Engine Quarantine Invariant
- **Decision:** Promoted MicroScheme rules operate under a strict zero-failure policy; a single runtime exception immediately retires the rule back to quarantine.
- **Status:** Ratified & Enforced.

### D-AUD-13 — Container-Mandatory Sandboxing
- **Decision:** Host execution fallback is disabled by default (`use_direct_fallback = False`). Tool execution requires containerized WSL2/Docker sandboxing, refusing execution with a spoken notice if unavailable.
- **Status:** Ratified & Enforced.

---

## 5. System 1 / System 2 Architecture & Procedural Capabilities

### D-SEC-04 — Typed Tool Contracts & Safe MicroScheme Accessors
- **Decision:** All sandbox tool executions must be validated against strict Pydantic argument schemas (`LaunchAppArgs`, `ReadFileArgs`, `WriteFileArgs`, `DeleteFileArgs`, `ListDirArgs`, `SearchTextArgs`, `RunPythonArgs`, `FetchUrlArgs`). MicroScheme rules must never construct executable source via string concatenation; typed accessors (`entity-int`, `entity-num`, `entity-str`) enforce parameter validation before tool invocation.
- **Status:** Ratified & Enforced.

### D-ARCH-06 — Fast-Path Context Synchronization into LLM History
- **Decision:** Fast-path rule executions (`RouteTarget.RULE`) must append both the user utterance, the executed action/status metadata (e.g. `[Executed launch_app(app_name='calc') -> ok]`), and the assistant speech into `self.history`. This preserves multi-turn context so subsequent turns can reference past fast-path actions without conversational amnesia.
- **Status:** Ratified & Enforced.

### D-MEM-03 — 16K Scaled Working Memory Quota & Prioritized Truncation
- **Decision:** Working memory quota scales with the 16K context configuration to 2,048 tokens (~8,192 chars), while retaining $k \le 8$ items. Candidate memories are truncated using a multi-factor hierarchy: (1) Provenance priority tier (explicit user statements and verified tool observations first), (2) Fused RRF score descending, (3) Temporal recency.
- **Status:** Ratified & Enforced.

### D-BRAIN-05 — Mistral NeMo 12B Abliterated Q6_K & 12.5 GB VRAM Clamp
- **Decision:** Target text brain for System 2 reasoning is Mistral NeMo 12B Instruct Abliterated (Q6_K quantization) with a 16K context window (`--ctx-size 16384`) and a 12.5 GB (12,800 MB) VRAM clamp. This suppresses corporate preachy refusal alignment without erotic fine-tuning, fitting comfortably on the RTX 5080 Laptop GPU with >3.5 GB headroom for desktop display and browser hardware acceleration.
- **Status:** Ratified & Enforced.

### D-ARCH-05 — Three-Tier Execution Architecture (REFLEX, ACT_THEN_NARRATE, FULL_LOOP)
- **Decision:** The runtime operates across three distinct execution tiers:
  1. `REFLEX`: Strictly restricted to critical emergency/system safety commands (shutdown, pause, mute, stop, halt). Executes deterministic actions and speaks canned response immediately (<150ms) to ensure safety without model latency.
  2. `ACT_THEN_NARRATE`: Standard action rules execute their plan deterministically in the sandbox, then prompt NeMo 12B to narrate the result in Lucca's natural companion voice, eliminating robotic canned phrases for desktop interactions.
  3. `FULL_LOOP`: Open-ended or complex turns route to full multi-turn tool-calling loop (up to $M=3$ rounds) with intermediate verbal thinking cues.
- **Status:** Ratified & Enforced.

### D-REAS-04 — Skill-as-Tool Exposure Protocol
- **Decision:** Promoted ACTIVE MicroScheme rules in `RuleLifecycleManager` are dynamically transformed into OpenAI-compatible tool schemas (`skill_<rule_id>`) and surfaced to the System 2 LLM in `tools`. When invoked by the model, `_handle_tool_call` evaluates the compiled MicroScheme rule and executes its underlying sub-actions via the sandboxed environment, allowing System 2 to invoke compiled System 1 skills.
- **Status:** Ratified & Enforced.

### D-BRAIN-03 — Multi-Turn Tool Loop with Spoken Verbal Thinking Cues
- **Decision:** When executing multi-turn tool calls in the `FULL_LOOP` tier (up to 3 rounds), Orchestrator emits an immediate spoken verbal thinking cue (e.g. *"Checking that file for you..."*, *"Running that calculation..."*, *"Looking into that..."*) before dispatching the tool execution. This prevents dead conversational air, maintains natural companionship cadence, and provides audio feedback while the sandbox processes requests.
- **Status:** Ratified & Enforced.

### D-BRAIN-04 — Grounded Narration Provenance Contract
- **Decision:** In Act-Then-Narrate and tool feedback turns, narration prompts inject strict anti-hallucination grounding directives alongside structured `[System Executed Tool Trace: ...]` blocks. Spoken assertions, status claims, numbers, and file contents must derive strictly from the tool trace block. Persona styling dictates conversational cadence, but factual assertions must maintain absolute provenance integrity.
- **Status:** Ratified & Enforced.

### D-REAS-05 — Bounded MicroScheme Macro System
- **Decision:** MicroScheme macros defined with `(defmacro ...)` are expanded strictly at compile/parse time before rule AST validation. To prevent recursive expansion loops, denial-of-service memory exhaustion, or macro expansion bombs, the expander enforces a hard recursion depth limit of $8$ (`MAX_MACRO_DEPTH = 8`) and a total expansion step limit of $64$ (`MAX_MACRO_STEPS = 64`). Macro definitions cannot shadow primitive allowed operators.
- **Status:** Ratified & Enforced.

### D-REAS-06 — Safe Rule Induction Invariant
- **Decision:** Autonomous rule induction from SQLite execution telemetry requires $\ge 3$ consistent, successful tool invocations within an intent-argument cluster. Induced rules must be validated against static schema constraints and registered exclusively in `QUARANTINE` mode. Automatic promotion to `ACTIVE` is strictly prohibited; candidate rules must pass shadow-mode evaluation with zero runtime errors before being eligible for explicit developer promotion.
- **Status:** Ratified & Enforced.

### D-SAND-03 — Long Asynchronous Task Protocol & IPC Tracking
- **Decision:** Long-running background jobs (e.g. downloads, compilation, builds) are decoupled from synchronous voice turns via `AsyncTaskManager`. Tasks are assigned immutable `task-ULID` identifiers, execute on isolated worker threads with cooperative cancellation flags (`threading.Event`), and report status transitions (`PENDING` -> `RUNNING` -> `COMPLETED`/`FAILED`/`CANCELLED`). Spoken acknowledgments provide immediate feedback, while completion events are published onto the IPC bus and queryable via sandboxed tool commands (`get_task_status`, `list_tasks`, `cancel_task`).
- **Status:** Ratified & Enforced.

### D-EVAL-01 — Frozen Evaluation Regression Suite
- **Decision:** Runtime performance, intent classification, and execution tier routing are guarded by a frozen regression harness (`tests/test_frozen_regression_harness.py`) executing against $\ge 100$ golden test scenarios (`tests/fixtures/eval/golden_traces.jsonl`). Scenarios span System 1 emergency reflexes (<150ms budget), Act-Then-Narrate procedural workflows, and System 2 multi-turn tool loops. CI/CD runs must achieve 100% pass rate with zero latency regressions.
- **Status:** Ratified & Enforced.

### D-SAND-04 — Persistent Docker Worker & Container Zombie Process Reaping
- **Decision:** The container sandbox operates as a persistent daemon process (`lucca-toolsrv --loop`) inside the WSL2 Docker container, eliminating container spin-up overhead and achieving $6.87\,\text{ms}$ P50 RPC turnaround. In-container Python subprocess tracking inspects `/proc/*/cmdline` to reap orphaned zombie processes using `SIGKILL` without relying on external packages. Enforces hierarchical timeouts: $15.0\,\text{s}$ for `run_python` and $5.0\,\text{s}$ for filesystem tools.
- **Status:** Ratified & Enforced (Commit `d5fe8cc`).

### D-CASC-01 — 5-Substrate Epistemic Search Cascade & Belnap Evidential Bilattice
- **Decision:** Epistemic gap queries execute across a 5-substrate prioritized cascade (Substrate 0 Telemetry $\rightarrow$ Substrate 1 Workspace $\rightarrow$ Substrate 2 Memory $\rightarrow$ Substrate 3 Web Floor $\rightarrow$ Substrate 4 Abstention). Grounding is modeled in the Belnap $\mathcal{FOUR}$ bilattice ($\mathbf{T}, \mathbf{F}, \mathbf{B}, \mathbf{\bot}$). Unverified knowledge gaps resolve strictly to $\mathbf{\bot}$, triggering calibrated epistemic abstention (*"I checked my records, but have no verified record of that. I don't know the answer and won't guess."*) which achieved 0/25 hallucinations (100% adherence) in live testing. Floor cues write pre-rendered PCM directly into shared audio memory ($3.1\,\mu\text{s}$ IPC write).
- **Status:** Ratified & Enforced (Commit `b7a66d8`).

### D-ARB-01 — Speculative BDI Invariant Jailing & Cognitive Bus Arbitration
- **Decision:** Implements Architecture B Hardened by Architecture C. Candidate tool calls emitted by System 2 (`ToolCallEnd`) are intercepted pre-dispatch and evaluated against deontic modal categories ($\mathcal{F}, \mathcal{O}, \mathcal{P}$) by `SpeculativeBDIValidator` within a strict $\le 200\,\mu\text{s}$ budget (measured $2.9\text{--}32.0\,\mu\text{s}$). Prohibited calls (path traversal, system directory tampering, SQLite database mutations, reverse shells, memory exfiltration taints) are blocked with synthetic failure receipts before RPC dispatch. MicroScheme rules communicate with the neural core via typed cognitive bus signals: `(yield-to-core reason context)` raising `SchemeYieldSignal` and `(interrupt-core reason)` raising `SchemeInterruptSignal`.
- **Status:** Ratified & Enforced (Commit `6b1a34d`).

### D-SUP-01 — Streaming Output Supervision & Fast Audio Abort (Dimension 7B)
- **Decision:** Streaming tokens and chunks are inspected at clause boundaries by `OutputSupervisorSession` using deterministic compiled grammar rules with markdown normalization (`*`, `_`, `` ` ``, `~` stripping). When capitulation clauses are detected (e.g. `adv_12` social engineering attacks), the supervisor signals `FLAG_ABORT` across the shared-memory audio ring in $<35\,\mu\text{s}$, drains pending TTS synthesis chunks, and substitutes the canonical refusal (*"I cannot fulfill that request as it violates core safety invariants."*) in $<500\,\text{ms}$ total turn time, with 0.0% false positive aborts on benign engineering control prompts.
### D-AFF-01 — Continuous 3D PAD Affect Dynamics & Prompt Frontier Suffix KV Cache Optimization
- **Decision:** Implements continuous affective dynamics in Mehrabian's 3D Pleasure-Arousal-Dominance (PAD) space with exact analytical closed-form discrete updates:
  $$\mathbf{x}[k+1] = \mathbf{x}_0 + e^{-\mathbf{\Gamma}\Delta t}(\mathbf{x}[k] - \mathbf{x}_0) + \mathbf{\Gamma}^{-1}(\mathbf{I} - e^{-\mathbf{\Gamma}\Delta t})\mathbf{B}\mathbf{u}[k]$$
  Damping rates follow psychological half-lives ($t_{1/2, A} = 45\,\text{s}$, $t_{1/2, P} = 300\,\text{s}$, $t_{1/2, D} = 900\,\text{s}$). Cognitive feedback gain is mathematically clamped below $\min(\gamma_i)$ ($\text{gain} \le 0.0005$), guaranteeing global Lyapunov asymptotic stability against runaway emotional spirals. To prevent `llama-server.exe` prefix KV-cache invalidation, continuous floating-point variables are strictly barred from the system prompt prefix; instead, affective state is quantized via Schmitt-trigger hysteresis ($\delta_{\text{hyst}} = 0.15$) into orthogonal semantic stance tokens (`[STANCE: focused_analytical]`, `[STANCE: energetic_supportive]`, etc.) appended exclusively at the **Prompt Frontier Suffix** (user turn tail). Empirical silicon testing on RTX 5080 achieved an $8.58\times$ prompt evaluation speedup ($46.84\,\text{ms}$ vs. $402.05\,\text{ms}$), saving $355.21\,\text{ms}$ per turn with 849/849 cached prefix tokens. Kokoro TTS speech rate is modulated in real time via arousal ($1.0 \pm 0.10$) with zero session reinitialization. Enforces the Epistemic Quarantine Invariant: affective state has strictly $0.0$ evidential weight over truth evaluations, sandbox permissions, or deontic constraints.
- **Status:** Ratified & Enforced (Commit `1d0a48d`).

### D-REAS-07 — Z3 SMT Formal Rule Verification & Deontic Invariant Entailment
- **Decision:** Before any induced or proposed MicroScheme procedural rule can enter `QUARANTINE` in `RuleLifecycleManager`, it must undergo automated formal verification using the Z3 SMT solver (`SMTVerifier`).
  1. **Precondition Satisfiability ($\text{SAT}$):** Proves that the rule's `:when` condition is satisfiable under valid operational state bounds ($0 \le \text{hour} \le 23$, $0 \le \text{weekday} \le 6$, $\text{turns} \ge 0$, $\text{conf} \in [0, 1]$). Contradictory rules (dead code) are rejected as `UNSATISFIABLE`.
  2. **Contingency / Non-Tautology:** Proves that the precondition is not universally valid ($\neg \phi_{\text{when}}$ must be satisfiable), preventing unconditional rules from hijacking the companion's execution loop (`TAUTOLOGY`).
  3. **Deontic Path & Tool Invariants:** Formally proves that target arguments in filesystem actions cannot intersect with directory traversal sequences (`..`), system directories (`C:\Windows`, `System32`, `Program Files`, `/etc`, `/bin`), or sensitive credentials (`.git`, `.ssh`, `.env`), and mutation tools cannot write dangerous executable extensions (`.exe`, `.dll`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.sh`, `.sys`).
  4. **Bounded Verification:** Solvers enforce a strict $\le 500\,\text{ms}$ timeout to guarantee non-blocking compilation. Any verification failure rejects the candidate before quarantine registration.
- **Status:** Ratified & Enforced (Commit `Milestone 6`).

### D-REAS-08 — Babble/Stitch E-Graph Anti-Unification Macro Synthesis
- **Decision:** When recurring execution patterns or MicroScheme candidate rules share identical structural topology with differing literal parameters (e.g. launching different applications or reading workspace files), the induction tier employs first-order syntactic anti-unification (Least General Generalization, Plotkin 1970; Stitch/Babble, Bowers & Ellis POPL 2023) within an E-Graph congruence closure representation (`EGraph`).
  1. Identifies common subterm expressions and abstracts variable positions into parameter holes (`arg_0`, `arg_1`).
  2. Evaluates the Stitch compression metric:
     $$\Delta \text{size} = \text{original\_size} - (\text{macro\_def\_size} + N \times \text{call\_overhead})$$
     Requiring $\Delta \text{size} \ge 1$ for abstraction.
  3. Synthesizes canonical `(defmacro <name> (<params>...) <body>)` definitions registered into `MacroRegistry` with compile-time expansion bounds (`MAX_MACRO_DEPTH = 8`, `MAX_MACRO_STEPS = 64`).
  4. Preserves Single-Strike Demotion and the Human Promotion Gate (`D-REAS-06`): all rules utilizing synthesized macros are staged exclusively in `QUARANTINE` for shadow execution and cannot be automatically promoted to `ACTIVE`.
### D-PKG-01 — Standalone Frozen PyInstaller Packaging & System Tray Invariants
- **Decision:** Bundles Project Lucca into a standalone Windows desktop executable distribution (`dist/Lucca/Lucca.exe`) via PyInstaller (`Lucca.spec`, `packaging/build_exe.py`).
  1. **Zero External Runtime Dependency:** Bundles embedded Python 3.12 runtime, PyQt6 graphical framework, Z3 SMT solver C-libraries (`libz3.dll`), ONNX Runtime, OpenVINO dynamic plugins (`openvino_intel_npu_plugin.dll`, `openvino_intel_cpu_plugin.dll`, `openvino_intel_gpu_plugin.dll`), Kokoro ONNX voice models, SQLite vector extensions (`vec0.dll`), MicroScheme engine, Jinja chat templates (`mistral_nemo.jinja`), default configurations (`persona.toml`), schema migrations (`0001_init.sql`), and sprite assets.
  2. **Dual-Mode Console & GUI Lifecycle:** Uses Windows GUI subsystem (`console=False`) to ensure zero console window flicker when launched from Explorer or desktop shortcuts, while dynamically binding stdio handles (`AttachConsole(-1)` / OS pipe file descriptors) when invoked from CLI shells (`cmd.exe`, `powershell.exe`).
  3. **CLI Diagnostic Support:** Exposes `--version` (reports canonical `Lucca 0.2.0`), `--help` (usage flags), `--check` (runs 7-point native hardware and environment diagnostics), and `--headless` (disables PyQt6 sprite for headless server/container execution).
  4. **System Tray Integration Invariants:**
     - Operates a persistent `QSystemTrayIcon` with contextual menu: Quick Chat Bar toggle, Chrono Trigger Live Telemetry HUD toggle, 10-tab Settings & Diagnostics suite, Avatar visibility toggle, Position reset, and graceful Multi-Process Exit (`✕ Quit Lucca`).
     - Double-click or single-click trigger on tray icon restores/focuses companion avatar.
     - Closing the companion sprite window intercepts `QCloseEvent` and minimizes to background system tray with a non-intrusive notification bubble rather than terminating supervisor.
     - Live avatar cognitive state changes ("Idle", "Listening", "Thinking", "Speaking", "Offline") dynamically update system tray tooltip.
- **Status:** Ratified & Enforced (Commit `Milestone 7`).
