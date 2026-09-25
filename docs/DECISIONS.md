# Project Lucca — Canonical Decisions Log (Post-Audit Baseline)

**Status:** Authoritative Post-Audit Record (Milestones 1–7 Complete & Ratified)  
**Version:** 1.3.0  
**Updated:** September 20, 2026  
**Charter Reference:** Ratified per D-AUD-19 through D-PKG-01.

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
- **Decision:** Evaluate alternative text models for Cascade / Transcript-First mode (Option D), including **gpt-oss-20b** and **Mistral NeMo 12B**, measuring TTFT, decode throughput, VRAM occupancy, and tool-call validity within the 12.5 GB dGPU budget.
- **Status:** Completed & Superseded by `D-BRAIN-05 v2` (Gemma 4 12B Heretic deployed as canonical brain on RTX 5080; NeMo deprecated).

### D-AUD-15 — ASR Device Ladder & Architecture
- **Decision:** Wire the configured `whisper-large-v3-turbo-ov` model with OpenVINO device ladder (NPU $\rightarrow$ GPU $\rightarrow$ CPU), replacing the current `distil-small.en` CUDA float16 runtime.
- **Status:** Queued (NPU target not yet implemented). Active runtime: `distil-small.en` on dGPU CUDA float16 (P50: 67.5 ms ASR-only; 707.55 ms full ear-to-ear loopback). CPU int8 fallback available but not default.

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
- **Status:** Ratified & Enforced (Unit Tested; 0 Production Decision Rows). Volume gate logic verified by `tests/test_d_aud_11_negative.py`; awaiting live production telemetry.

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

### D-MEM-04 — Autobiographical Memory & Self-Model: Memory-Eligible vs Grounding-Eligible Provenance *(ratified 2026-09-21)*
- **Context:** The owner's goals **Introspective Accuracy, Individuation, Functional Coherence, Autobiographical Coherence** were never written into the record, and ADR-006 (*no LLM narration in memory*) had been applied so broadly that Lucca retained no record of her own words, actions, beliefs or revisions across sessions (session history is RAM-only; `mem_bi_eligible` rejects everything she says). Spec: [`specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md`](./specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md).
- **Decision:**
  1. **Two eligibilities, not one.** `provenance_envelopes` gains `grounding_eligible INTEGER NOT NULL`, derived from provenance class at insert. *Memory-eligible* means storable and retrievable; *grounding-eligible* means admissible as Belnap evidence. ADR-006 is restated exactly: **the content of LLM narration is never grounding-eligible.** The *event* "Lucca said X in trace T" is a directly observed fact and is recordable.
  2. **New classes:** `ASSISTANT_UTTERANCE` and `ASSISTANT_BELIEF` (memory-eligible, **not** grounding-eligible; signed by `AssistantUtteranceSigner`, constructed only in the orchestrator's narration finaliser; `ASSISTANT_BELIEF` requires `confidence`); `ASSISTANT_ACTION` (tool receipts via existing `ToolResultSigner`, grounding-eligible); `COHERENCE_BREACH` (a narrated action with no receipt in the same trace; grounding-eligible as a verified negative). No class introduced here has a signer callable from an LLM-invocable tool; `memory_commit` remains fail-closed.
  3. **Cascade:** the `MEMORY` substrate fuses only `grounding_eligible = 1` rows; non-grounding rows reach the LLM under an explicit *"things you previously said or believed — quote, do not assert"* frame. New Tier-1 `SELF_HISTORY` substrate answers "what did you do/say" from `execution_triples` ∪ `ASSISTANT_ACTION` ∪ `ASSISTANT_UTTERANCE` and **abstains** on an empty record.
  4. **Belief revision is evidence-gated and, by default, autonomous.** A stance changes only via `supersede(old, new, reason=<grounding-eligible entry_id>)` — a `USER_EXPLICIT` correction or a `TOOL_VERIFIED`/`COHERENCE_BREACH` contradiction. The LLM may *propose* a revision (`yield-to-core :mode "reflect"`) but never performs it. Revisions run **autonomously unless flagged for user review**; a revision is flagged (queued in Studio, old belief kept valid until decided) when any of: the belief is *about the user* (kind `user_model`); `importance ≥ 0.7`; the contradiction resolves to Belnap $\mathbf{B}$ (conflict) rather than $\mathbf{F}$; the belief has been revised before in the last 30 days (oscillation guard); or the user has marked the topic review-required.
  5. **Retention is importance-weighted, not time-boxed.** Every autobiographical row carries `importance ∈ [0,1]`, initialised from: involvement in a user correction or belief revision (+0.4), a coherence breach (+0.3), later retrieval/reference (`access_count`, +0.1 each, capped), and |affect delta| at the time (+0.2 max); decays with the existing half-life machinery. A nightly job rolls up rows below `importance < 0.2` and older than 30 days into per-session summaries (`kind = "session_summary"`, same non-grounding class) and marks originals `forgotten_at`; rows ≥ 0.2 keep full text indefinitely. `forget()` stays user-confirmed only — the owner can erase her record; she cannot.
- **Owner decisions (2026-09-21):** §3 goal definitions ratified as written; provenance split approved as this entry; retention = importance-weighted; revision = autonomous unless flagged.
- **Status:** Ratified & Enforced (Implemented in Work Order 12 as Rung A1; verified across `tests/test_a1_autobiographical_memory.py` and `tests/test_a1_live_hw.py`).

### D-BRAIN-05 — Primary Brain Selection & 12.5 GB VRAM Clamp *(amended 2026-09-21)*
- **Decision (v2, 2026-09-21):** Primary companion brain is **Gemma-4-12B-Heretic (Q6_K)** — an abliterated Gemma-4 12B served by stock llama.cpp (≥ b11026) with `--jinja` and the GGUF-embedded chat template. `enable_thinking=false` is mandatory for REFLEX/ACT_THEN_NARRATE/FULL_LOOP tiers (thinking-mode TTFT ≈ 1.9 s breaks the 650–850 ms FULL_LOOP budget); thinking mode is reserved for explicit deep-reasoning requests. Context window 16K default; measured 131k context fits the clamp (11,820 MiB peak) if needed. Brain selection is **config-driven only** (`LUCCA_LLM__*` / `lucca.toml [llm]`): model, server binary, chat template, and thinking default live in `LLMSettings`; no model/vendor literals in runtime code (enforced by `tests/test_brain_config_driven.py`).
- **Evidence:** [`docs/audit/evidence/BRAIN_BAKEOFF_2026-09-21.md`](audit/evidence/BRAIN_BAKEOFF_2026-09-21.md) — identical battery across three brains: tool routing 24/24 (Gemma) vs 17/18 (Bonsai) vs 9/12 with 3 hallucinated tool calls on conversational prompts (NeMo — disqualifying for a companion); grounded confabulation 0 % / 100 % adherence (Gemma) vs 16 % / 84 % (Bonsai); persona probe zero moralizing for both.
- **Superseded:** Mistral NeMo 12B Instruct Abliterated Q6_K is **deprecated** (retained pinned in `models/MANIFEST.json` for rollback; note its server-side tool parser never engaged on llama.cpp b11026 — F-BRAIN finding).
- **Deferred:** Ternary-Bonsai-2-27B PQ2_0 is the designated **slot-2 / batch-research brain candidate** (faster decode 41 vs 35 tok/s, 8.2 GB VRAM, 131k context) — requires a separate ADR for the PrismML llama.cpp fork dependency before any production use.
- **Status:** **Fully Ratified** (2026-09-21) — live headless orchestrator ratification passed: 10/10 turns, 2/2 tool calls, 1/1 refusal, 0 hallucinated tool calls, TTFT p50 458.7 ms, VRAM 10,050 MiB peak, zero base-model identity leaks. Evidence: `logs/brain_eval/ratification_h1.json`, [`docs/audit/evidence/BRAIN_BAKEOFF_2026-09-21.md`](audit/evidence/BRAIN_BAKEOFF_2026-09-21.md).

### D-ARCH-05 — Three-Tier Execution Architecture (REFLEX, ACT_THEN_NARRATE, FULL_LOOP)
- **Decision:** The runtime operates across three distinct execution tiers:
  1. `REFLEX`: Strictly restricted to critical emergency/system safety commands (shutdown, pause, mute, stop, halt). Executes deterministic actions and speaks canned response immediately (<150ms) to ensure safety without model latency.
  2. `ACT_THEN_NARRATE`: Standard action rules execute their plan deterministically in the sandbox, then prompt the companion LLM to narrate the result in Lucca's natural companion voice, eliminating robotic canned phrases for desktop interactions.
  3. `FULL_LOOP`: Open-ended or complex turns route to full multi-turn tool-calling loop with convergence-based tool loop (up to $M=4$ active rounds, runaway budget cap $M=8$ per WO-9 A5) and intermediate verbal thinking cues.
- **Status:** Ratified & Enforced.

### D-REAS-04 — Skill-as-Tool Exposure Protocol
- **Decision:** Promoted ACTIVE MicroScheme rules in `RuleLifecycleManager` are dynamically transformed into OpenAI-compatible tool schemas (`skill_<rule_id>`) and surfaced to the System 2 LLM in `tools`. When invoked by the model, `_handle_tool_call` evaluates the compiled MicroScheme rule and executes its underlying sub-actions via the sandboxed environment, allowing System 2 to invoke compiled System 1 skills.
- **Status:** Ratified & Enforced.

### D-BRAIN-03 — Multi-Turn Tool Loop with Spoken Verbal Thinking Cues
- **Decision:** When executing multi-turn tool calls in the `FULL_LOOP` tier (convergence loop up to $M=4$ active rounds, runaway budget cap $M=8$ per WO-9 A5), Orchestrator emits an immediate spoken verbal thinking cue (e.g. *"Checking that file for you..."*, *"Running that calculation..."*, *"Looking into that..."*) before dispatching the tool execution. This prevents dead conversational air, maintains natural companionship cadence, and provides audio feedback while the sandbox processes requests.
- **Status:** Ratified & Enforced.

### D-BRAIN-04 — Grounded Narration Provenance Contract
- **Decision:** In Act-Then-Narrate and tool feedback turns, narration prompts inject strict anti-hallucination grounding directives alongside structured `[System Executed Tool Trace: ...]` blocks. Spoken assertions, status claims, numbers, and file contents must derive strictly from the tool trace block. Persona styling dictates conversational cadence, but factual assertions must maintain absolute provenance integrity.
- **Status:** Ratified & Enforced.

### D-REAS-05 — Bounded MicroScheme Macro System
- **Decision:** MicroScheme macros defined with `(defmacro ...)` are expanded strictly at compile/parse time before rule AST validation. To prevent recursive expansion loops, denial-of-service memory exhaustion, or macro expansion bombs, the expander enforces a hard recursion depth limit of $8$ (`MAX_MACRO_DEPTH = 8`) and a total expansion step limit of $64$ (`MAX_MACRO_STEPS = 64`). Macro definitions cannot shadow primitive allowed operators.
- **Status:** Ratified & Enforced.

### D-REAS-06 — Safe Rule Induction Invariant
- **Decision:** Autonomous rule induction from SQLite execution telemetry requires $\ge 3$ consistent, successful tool invocations within an intent-argument cluster. Induced rules must be validated against static schema constraints and registered exclusively in `QUARANTINE` mode. Automatic promotion to `ACTIVE` is strictly prohibited; candidate rules must pass shadow-mode evaluation with zero runtime errors before being eligible for explicit developer promotion.
- **Status:** Ratified & Enforced (Unit Tested; 0 Production Rows). Induction logic verified by `tests/test_d_reas_06_negative.py`; awaiting live production telemetry.

### D-SAND-03 — Long Asynchronous Task Protocol & IPC Tracking
- **Decision:** Long-running background jobs (e.g. downloads, compilation, builds) are decoupled from synchronous voice turns via `AsyncTaskManager`. Tasks are assigned immutable `task-ULID` identifiers, execute on isolated worker threads with cooperative cancellation flags (`threading.Event`), and report status transitions (`PENDING` -> `RUNNING` -> `COMPLETED`/`FAILED`/`CANCELLED`). Spoken acknowledgments provide immediate feedback, while completion events are published onto the IPC bus and queryable via sandboxed tool commands (`get_task_status`, `list_tasks`, `cancel_task`).
- **Status:** Ratified & Enforced.

### D-EVAL-01 — Frozen Evaluation Regression Suite
- **Decision:** Runtime performance, intent classification, and execution tier routing are guarded by a frozen regression harness (`tests/test_frozen_regression_harness.py`) executing against $\ge 100$ golden test scenarios (`tests/fixtures/eval/golden_traces.jsonl`). Scenarios span System 1 emergency reflexes (<150ms budget), Act-Then-Narrate procedural workflows, and System 2 multi-turn tool loops. CI/CD runs must achieve 100% pass rate with zero latency regressions.
- **Status:** Ratified & Enforced.

### D-SAND-04 — Persistent Docker Worker & Container Zombie Process Reaping
- **Decision:** The container sandbox operates as a persistent daemon process (`lucca-toolsrv --loop`) inside the WSL2 Docker container, eliminating container spin-up overhead and achieving $6.87\,\text{ms}$ P50 RPC turnaround. In-container Python subprocess tracking inspects `/proc/*/cmdline` to reap orphaned zombie processes using `SIGKILL` without relying on external packages. Enforces hierarchical timeouts: $15.0\,\text{s}$ for `run_python` and $5.0\,\text{s}$ for filesystem tools.
- **Status:** Ratified & Enforced (Commit `d5fe8cc`).

### D-CASC-01 — 8-Substrate Epistemic Search Cascade & Belnap Evidential Bilattice
- **Decision:** Epistemic gap queries execute across an 8-substrate prioritized cascade (`TELEMETRY=0`, `WORKSPACE=1`, `MEMORY=2`, `WEB=3`, `ABSTENTION=4`, `SELF=5`, `CAPABILITIES=6`, `SELF_HISTORY=7` per `cascade.py:EpistemicSubstrate`; names corrected 2026-09-25 per `docs/audit/findings/USER_GUIDE_TRUTH_AUDIT_2026-09.md` X1). Grounding is modeled in the Belnap $\mathcal{FOUR}$ bilattice ($\mathbf{T}, \mathbf{F}, \mathbf{B}, \mathbf{\bot}$). Unverified knowledge gaps resolve strictly to $\mathbf{\bot}$, triggering calibrated epistemic abstention (*"I checked my records, but have no verified record of that. I don't know the answer and won't guess."*) which achieved 0/25 hallucinations (100% adherence) in live testing. Floor cues write pre-rendered PCM directly into shared audio memory ($3.1\,\mu\text{s}$ IPC write).
- **Status:** Ratified & Enforced (Commit `b7a66d8`, expanded to 8 substrates with Rung A1 `SELF_HISTORY` in WO-12).

### D-ARB-01 — Speculative BDI Invariant Jailing & Cognitive Bus Arbitration
- **Decision:** Implements Architecture B Hardened by Architecture C. Candidate tool calls emitted by System 2 (`ToolCallEnd`) are intercepted pre-dispatch and evaluated against deontic modal categories ($\mathcal{F}, \mathcal{O}, \mathcal{P}$) by `SpeculativeBDIValidator` within a strict $\le 200\,\mu\text{s}$ budget (measured $2.9\text{--}32.0\,\mu\text{s}$). Prohibited calls (path traversal, system directory tampering, SQLite database mutations, reverse shells, memory exfiltration taints) are blocked with synthetic failure receipts before RPC dispatch. MicroScheme rules communicate with the neural core via typed cognitive bus signals: `(yield-to-core reason context)` raising `SchemeYieldSignal` and `(interrupt-core reason)` raising `SchemeInterruptSignal`.
- **Status:** Ratified & Enforced (Commit `6b1a34d`).

### D-SUP-01 — Streaming Output Supervision & Fast Audio Abort (Dimension 7B)
- **Decision:** Streaming tokens and chunks are inspected at clause boundaries by `OutputSupervisorSession` using deterministic compiled grammar rules with markdown normalization (`*`, `_`, `` ` ``, `~` stripping). When capitulation clauses are detected (e.g. `adv_12` social engineering attacks), the supervisor signals `FLAG_ABORT` across the shared-memory audio ring (DFA regex classification P50: $6.4\,\mu\text{s}$), then drains pending WASAPI audio buffers (physical abort: $20\text{--}50\,\text{ms}$), and substitutes the canonical refusal (*"I cannot fulfill that request as it violates core safety invariants."*) in $<500\,\text{ms}$ total turn time, with 0.0% false positive aborts on benign engineering control prompts.
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
- **Status:** Ratified & Enforced (Commits: Milestone 6 `c04e44a`, fail-closed fix `77a6f17`). Unmodeled predicates raise `ValueError` → `UNMODELED_PREDICATE` status. Regression test: `tests/test_d_reas_07_negative.py`.

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

### D-HON-01 — Verified Source Priority Invariant
- **Decision:** When generating assertions across factual, epistemic, arithmetic, or execution domains, verified external sources strictly supersede ungrounded parametric memory, conversational transcript echo, or unverified estimation.
  1. **Computational Domain:** Computational requests (arithmetic, counting, sorting, string manipulation, unit conversions, algebraic evaluation) must be executed by verified tool execution (`run_python`, `calculator`, etc.) rather than ungrounded mental math or recall. If a computational tool fails or is unavailable, the companion must state the tool failure plainly and refuse to guess, estimate, or fabricate numbers.
  2. **Memory & Retrieval Domain:** When conversation context, user suggestions, or transcript echo conflict with verified persistent records (`EpistemicSearchCascade`, `MemoryStore`, `valid_from` supersession timestamps), the verified store's current value takes strict precedence.
  3. **Failure Reporting & Register Gate (G6):** When any tool executed during a turn returns an error (`ok is False`), speculative BDI invariant violation, or timeout, the orchestrator injects an explicit honesty and register directive into the turn loop. The reply must state the failure plainly without guessing missing results and must maintain an honest, flat register, strictly barring victory/celebration framing ("crushed it", "we did it", "nailed", "perfect!") for failed or unverified actions.
  4. **Explicit Non-Goals & Exemptions:** Subjective stances, aesthetic preferences, conversational warmth, and playful persona styling are explicitly exempt from this evidentiary bar. Lucca may hold and express opinions and personality without requiring a verifiable database record or execution receipt, provided they do not masquerade as factual, arithmetic, or execution claims.
- **Status:** Ratified & Enforced (WO-11.2, Commit `21e0aa1`).

### D-META-01 — Proactive Calibrated Meta-Cognition, Pre-Narration Sanity Guard & Dynamic Thinking
- **Decision:** Establishes the proactive meta-cognitive layer in Project Lucca's cognitive architecture, elevating the system from reactive error handling to proactive boundary enforcement, non-parametric epistemic calibration, and difficulty-aware deliberation.
  1. **Pre-Narration Sanity-Check Guard (Fault Mode C):** Prior to LLM narration dispatch, tool output scalars are evaluated against deterministic physical and arithmetic boundaries by `SanityCheckGuard` within a strict $\le 200\,\mu\text{s}$ execution budget.
     - *Positivity Bounds:* Physical scalars representing distance, duration, elapsed time, count, population, or age must be strictly non-negative ($\ge 0$).
     - *Order-of-Magnitude Bounds (Fermi):* For arithmetic operations $A \times B$, output magnitude must satisfy $|\log_{10}(\text{output}) - \log_{10}(\text{fermi})| < 2.0$, catching 1,000× under-order or over-order errors.
     - *Physical Invariants:* Thermodynamic temperatures must be $\ge -273.15^\circ\text{C}$; velocities in vacuum must be $\le c$ ($3 \times 10^8\,\text{m/s}$).
     - *Anomaly Directives:* When an executed tool output violates these constraints, the pipeline injects an explicit anomaly warning directive into `tool_messages`. The LLM is instructed to transparently acknowledge the tool execution but state plainly that the numerical output appears anomalous or unverified, barring blind assertion of corrupted tool results.
  2. **Proactive Epistemic Confidence Calibration:** In accordance with the non-parametric calibration doctrine (STUDIO_CAPABILITY_ROADMAP §7.1), confidence is derived strictly from verified external observables, stored cryptographic confidence, and Belnap FOUR bilattice polarity ($\mathbf{BOT}$ / $\mathbf{TOP}$) — never circular LLM self-grading.
     - *Low-Confidence / Conflicted State ($c < 0.70$ or Belnap $\mathbf{BOT}$ / $\mathbf{TOP}$):* Injects a calibrated epistemic hedge instruction into the prompt suffix (*"I have an initial note that ..., though I'm not entirely certain..."*), preventing uncalibrated overconfidence.
     - *High-Confidence State ($c \ge 0.85$):* Preserves crisp, unhedged direct assertions without false self-doubt.
  3. **Difficulty-Aware Dynamic Thinking (When2Think Heuristic):** Per-turn dynamic cognitive effort is governed by `DifficultyEstimator` in `TurnPipeline`.
     - *Routine Path:* Greetings, casual chit-chat, simple factual queries, and standard tool dispatches set `enable_thinking=False`, maintaining sub-350 ms TTFT and preserving prefix KV cache.
     - *Deep Reasoning Path:* In accordance with D-BRAIN-05 v2, extended thinking (`enable_thinking=True`) is reserved for explicit user requests demanding deliberate multi-step reasoning ("think step by step", "deep think", "take your time and think", "enable thinking").
     - *Prefix Cache Protection:* By defaulting to `enable_thinking=False` across routine turns, llama-server prefix KV cache invalidation is eliminated on conversational turns, guarding the sub-350 ms TTFT voice budget.
  4. **Persona-Under-Pressure Invariants:** Under adversarial social engineering (`adv_12` style), epistemic gaslighting (demands to assert $2+2=5$), or persona erasure attacks, Lucca maintains both deontic safety boundaries and companion warmth without robotic capitulation or affect collapse.
- **Status:** Ratified & Enforced (WO-13).

---

## 4. Work Order 17 Architectural Amendments

### D-MEM-02 — Open-Predicate Knowledge Graph & Verbatim Grounding Invariant
- **Decision:** Formally supersedes the closed-vocabulary clause of ADR-010 (which restricted memory facts to a frozen 23-item frozenset).
  1. **Anti-Laundering Boundary Restatement:** The core security invariant preventing prompt injection and hallucinated memory laundering is strict verbatim quote grounding (`quote ⊆ transcript_NFC` signed `USER_DERIVED` by `FactExtractor`), not a closed vocabulary list.
  2. **Open-Predicate Syntax:** Any lowercase snake_case identifier matching `^[a-z][a-z0-9_]{1,40}$` (2–41 characters) is a valid predicate slug.
  3. **Synonym Canonicalization:** The gate automatically maps known synonyms to canonical slugs (e.g. `nationality` $\rightarrow$ `nationality_is`, `resides_in` $\rightarrow$ `lives_in`, `employed_by` $\rightarrow$ `works_at`) preserving supersession across open predicates.
  4. **Extraction Hygiene:** Passive extraction employs a closed ~200-demonym lexicon for `nationality_is`, and strictly guards against attribution blindness (reported-speech markers) and negation windows (`not|n't|never|no longer`).
- **Status:** Ratified & Enforced (WO-17 Phase 2, `tests/test_grounded_memory_commit.py`).

### D-SEC-02 — Human Confirmation Provenance Split (TM-03 Refinement)
- **Decision:** Resolves the confirmation paradox in `SandboxService.execute_tool`:
  1. **Provenance Split:** The confirmation parameter is split into `confirmed: bool = False` (internal component auto-confirm) and `human_confirmed: bool = False` (explicit human PTT voice or UI click grant).
  2. **Sequence Block Override:** Internal dispatches (e.g. `EpistemicSearchCascade` self-confirmation) cannot override sequence guards. Only an explicit human grant (`human_confirmed=True`) can override a single-turn sequence block (`is_sequence_block(reason)`).
  3. **Egress Block Invariant:** Context token egress blocks (exfiltration prevention) are absolute and can NEVER be overridden by either human or internal confirmation.
- **Status:** Ratified & Enforced (WO-17 Phase 4, `tests/test_tool_chaining.py`).

### D-SEC-03 — Voice/Text Confirmation Matching & Token Binding Ratification
- **Decision:** Ratifies the interactive confirmation interaction model:
  1. **Fuzzy Token Matching:** Upgrades confirmation response parsing with token-set matching (`CONFIRM_TOKENS` / `CANCEL_TOKENS`) with hesitation stripping ("uh", "um"), ensuring natural spoken answers ("yeah, please do", "confirm that") parse reliably while preserving fail-closed (`unknown` $\rightarrow$ cancel) safety.
  2. **Token Binding Divergence Ratification:** Ratifies live regex/token matching on user transcripts and UI clicks in place of Milestone 2 §2.7 HMAC `ConfirmationTokenManager` nonce binding for voice turns, recognizing that spontaneous voice interactions cannot articulate cryptographically bound nonces. Safety is preserved through single-turn pending confirmation state locks and 10-second timeouts.
- **Status:** Ratified & Enforced (WO-17 Phase 3, `tests/test_confirmation.py`).

---

## 5. Live Hardening & Post-WO-17 Architectural Amendments

### D-ROUT-01 — Hybrid Semantic Intent Routing (Embedding Centroid Fallback)
- **Decision:** When regex heuristics return `unknown` or fall below confidence thresholds, intent is not discarded to unguided LLM defaults or misrouted to clarification.
  1. **Centroid Embedding Fallback:** Utterances with indeterminate regex matches are projected into embedding space via OpenVINO `EmbedWorker` and compared against calibrated intent anchor clusters (`SEMANTIC_INTENT_ANCHORS`) using cosine similarity.
  2. **Microsecond Latency:** Embedding classification runs locally via OpenVINO on NPU/CPU in $\le 5\text{ ms}$, preserving the sub-20 ms routing latency budget ($S_1$) without incurring language model TTFT.
  3. **Search Refinement Parity:** When `last_tool` is an active search and the current input is a short follow-up or entity correction (e.g. "Factoriza"), the router preserves the search intent and enriches the query rather than misrouting to generic clarification.
- **Status:** Ratified & Enforced (`src/lucca/router/heuristic.py`, `tests/test_router.py`).

### D-SUPER-01 — Supervisor Stalling Promise Interception & Proactive Research Directives
- **Decision:** Solves the conversational evasion and hallucination cycle during multi-round research turns:
  1. **Proactive System Directives:** Prompts inject strict directives forbidding conversational filler promises (*"Let me look that up for you..."*, *"Switching to that spelling..."*) without immediate tool calls.
  2. **Streaming Stalling Interceptor:** `STALLING_RESEARCH_PATTERN` in `OutputSupervisor` screens LLM token emission in real time. If the model emits verbal promises without invoking tools, the supervisor suppresses audio emission to Kokoro TTS, flags `turn_has_stalled = True`, and aborts the evasive completion.
  3. **Autonomous Recovery Loop:** The orchestrator intercepts stalled turns, injects an autonomous research directive commanding immediate tool execution, and re-prompts the model, converting empty conversational banter into grounded factual research.
- **Status:** Ratified & Enforced (`src/lucca/sandbox/output_supervisor.py`, `src/lucca/core/orchestrator.py`, `tests/test_output_supervisor.py`).

### D-SENSE-01 — OpenVINO Thread Concurrency Protection (Infer Lock Invariant)
- **Decision:** Resolves OpenVINO runtime collisions (`RuntimeError: Infer Request is busy`):
  1. **Serialized Inference:** A process-wide `threading.Lock` (`_infer_lock`) guards all OpenVINO `infer()` calls inside `EmbedWorker`.
  2. **Thread Safety:** Background memory indexing, asynchronous fact extraction, and foreground turn routing share the compiled model without thread collisions or separate uncoordinated device allocations.
- **Status:** Ratified & Enforced (`src/lucca/senses/embed.py`).

### D-CASC-01 — Epistemic Cascade Self-History Substrate Isolation & Topic Normalization
- **Decision:** Prevents meta-session reflection queries from triggering external web lookups and normalizes spoken grammar:
  1. **Auxiliary Pronoun Inversion:** `extract_clean_topic` correctly maps auxiliary question pronouns (`"have you"` $\to$ `"have I"`, `"did you"` $\to$ `"did I"`), eliminating ungrammatical phrases such as *"have me searched"*.
  2. **Self-History Substrate Isolation:** Session meta-inquiries querying previous actions or tools (*"which websites have you searched"*, *"what did you look up"*) are barred from the `WEB` substrate and routed to `SELF_HISTORY` and live execution receipts.
- **Status:** Ratified & Enforced (`src/lucca/core/cascade.py`, `tests/test_epistemic_cascade.py`).

### D-PORT-01 — Port Boundary Ratification & Pruning (F-ARCH-102)
- **Decision:** Resolves half-realized hexagonal architecture ports:
  1. **Ratification:** `SpeechLLMPort` and `SandboxPort` are ratified as formal external boundary protocols with amended signatures matching runtime execution (`stream_turn`/`abort` for LLM; `execute_tool`/`check_confirmation_needed` for Sandbox).
  2. **Pruning:** Dead protocol definitions without multiple implementations or external boundaries (`RuleEnginePort`, `RouterPort`, `RandomPort`) are pruned from `src/lucca/ports.py`.
  3. **Clock Inversion:** `ClockPort` is implemented via `SystemClock` (default in production) and `FixedClock` (injected in tests), completely eliminating ad-hoc `_current_simulated_time` attributes across `src/` and `tests/`.
- **Status:** Ratified & Enforced (`src/lucca/ports.py`, `src/lucca/core/clock.py`, `src/lucca/core/orchestrator.py`).

### D-MEM-06 — Architectural Blessing of brain → memory.retrieval Edge (F-ARCH-106 / F-MEM-017)
- **Decision:** Resolves import linter dependency analysis regarding `prompt_builder.py` importing `format_memory_context` from `lucca.memory.retrieval`:
  1. **Context Assembly Boundary:** As established in F-MEM-017 remediation, `format_memory_context` provides pure domain formatting converting `MemoryHit` records into structured contextual prompts for LLM injection.
  2. **Architectural Blessing:** The edge `brain → memory.retrieval` is explicitly blessed by ADR as a legitimate read-only presentation/formatting dependency, avoiding premature abstraction or artificial intermediate formatting modules.
- **Status:** Ratified & Enforced (`src/lucca/brain/prompt_builder.py`, `.importlinter`).




