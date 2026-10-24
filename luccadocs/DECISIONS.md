# Project Lucca — Canonical Decisions Log (Post-Audit Baseline)

**Status:** Authoritative Post-Audit Record (Milestones 1–7 Complete & Ratified)
**Version:** 1.4.1
**Updated:** October 5, 2026
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
- **Evidence:** [`luccadocs/archive/2026-09_evidence/BRAIN_BAKEOFF_2026-09-21.md`](archive/2026-09_evidence/BRAIN_BAKEOFF_2026-09-21.md) — identical battery across three brains: tool routing 24/24 (Gemma) vs 17/18 (Bonsai) vs 9/12 with 3 hallucinated tool calls on conversational prompts (NeMo — disqualifying for a companion); grounded confabulation 0 % / 100 % adherence (Gemma) vs 16 % / 84 % (Bonsai); persona probe zero moralizing for both.
- **Superseded:** Mistral NeMo 12B Instruct Abliterated Q6_K is **deprecated** (retained pinned in `models/MANIFEST.json` for rollback; note its server-side tool parser never engaged on llama.cpp b11026 — F-BRAIN finding).
- **Deferred:** Ternary-Bonsai-2-27B PQ2_0 is the designated **slot-2 / batch-research brain candidate** (faster decode 41 vs 35 tok/s, 8.2 GB VRAM, 131k context) — requires a separate ADR for the PrismML llama.cpp fork dependency before any production use.
- **Status:** **Fully Ratified** (2026-09-21) — live headless orchestrator ratification passed: 10/10 turns, 2/2 tool calls, 1/1 refusal, 0 hallucinated tool calls, TTFT p50 458.7 ms, VRAM 10,050 MiB peak, zero base-model identity leaks. Evidence: `logs/brain_eval/ratification_h1.json`, [`luccadocs/archive/2026-09_evidence/BRAIN_BAKEOFF_2026-09-21.md`](archive/2026-09_evidence/BRAIN_BAKEOFF_2026-09-21.md).

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
- **Status:** Ratified & Enforced. Production telemetry crossed the N≥3 decision floor on 2026-09-25 (21 genuine usage decisions, provenance-verified 2026-09-26 via `scratch/check_decisions_provenance.py`). First live induction run (2026-09-26, `scratch/first_live_induction.py`) yielded **0 clusters**: 8/21 decisions carry tool calls, but no `(intent, tool, arg_key, arg_val)` cluster recurs ≥3 times with identical values — 5 `search_web` calls about the same subject used 4 distinct query strings, and exact-match clustering does not generalize near-duplicates. The tripwire fixture was retired per its own instructions; the empty-data negative guard remains in `tests/test_d_reas_08_negative.py`.

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
- **Decision:** Epistemic gap queries execute across an 8-substrate prioritized cascade (`TELEMETRY=0`, `WORKSPACE=1`, `MEMORY=2`, `WEB=3`, `ABSTENTION=4`, `SELF=5`, `CAPABILITIES=6`, `SELF_HISTORY=7` per `cascade.py:EpistemicSubstrate`; names corrected 2026-09-25 per `luccadocs/audit/findings/USER_GUIDE_TRUTH_AUDIT_2026-09.md` X1). Grounding is modeled in the Belnap $\mathcal{FOUR}$ bilattice ($\mathbf{T}, \mathbf{F}, \mathbf{B}, \mathbf{\bot}$). Unverified knowledge gaps resolve strictly to $\mathbf{\bot}$, triggering calibrated epistemic abstention (*"I checked my records, but have no verified record of that. I don't know the answer and won't guess."*) which achieved 0/25 hallucinations (0.0%, 95% Wilson CI [0.0%, 13.3%]; 100% adherence; manifest record `milestone3_confabulation_battery`) in live testing. Floor cues write pre-rendered PCM directly into shared audio memory ($3.1\,\mu\text{s}$ IPC write).
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

### D-REAS-09 — The Concert Layer: Bounded Forward-Chaining Deduction with Signed Proof Traces
- **Decision:** The MicroScheme engine (deductive skeleton) and the LLM (abductive engine) operate in concert over the signed fact store, producing conclusions that carry a cryptographically signed proof trace (ADR [`0010`](./adr/0010_d_reas_09_concert_layer.md)).
 1. **Assertion Primitive:** MicroScheme rules emit `(assert (s p o))` plan actions — pure constructors validated against the predicate vocabulary (`is_valid_predicate`), executed by the orchestrator as signed `LISP_ASSERTION` envelopes via `SignerFactory.lisp_assertion()`. The LLM never signs anything.
 2. **Fact Predicates:** `(fact-exists? ...)` and `(fact-value ...)` read-only state primitives query `RuleState.asserted_facts` (frozen rebuild discipline — never mutated in place).
 3. **Bounded Re-Evaluation:** `RuleLifecycleManager.evaluate_chain` forward-chains with `MAX_CHAIN_DEPTH = 8`, per-chain fired-rule tracking, and fixpoint fast-path termination.
 4. **Reasoning Context (Working Memory):** per-turn `ReasoningContext` (capacity 32 = `MAX_CHAIN_DEPTH × 4`) holds ordered intermediates with envelope IDs, rule IDs, and premises; never persisted to the database; exposes `proof_trace()` for the commit path.
 5. **LLM Abductive Steps (ratified shape):** `InferenceStep(premises, s, p, o, confidence ∈ [0,1], rationale, conditions)` — structured triple conclusions, no `rule_id`. Premises are existence-checked against the signed store or reasoning context; attributed premises (`"<source> asserts <claim>"`) verify against current-turn signed tool receipts and are carried as `conditions` (Toulmin rebuttal slot) — chains degrade gracefully instead of breaking.
 6. **Gather Ladder:** on `unverified_premise` — revise once → `memory_search` retry → named-gap user question → named-gap abstention. Bounded to one pass per turn. Web content is never a premise verifier (`TOOL_CONTENT_UNTRUSTED`, D-HON-01).
 7. **INFERRED Commit Path (in flight):** conclusions commit as `Provenance.INFERRED` (below `USER_DERIVED`, above `LISP_ASSERTION`) only with a complete proof trace whose every premise resolves to an existing envelope; superseded by direct evidence (`USER_EXPLICIT`/`USER_DERIVED`) on the same predicate.
- **Status:** Ratified; Phases 0–2 enforced (commits `bef2fbf`, `a50e5d7`, `a948b89`; `tests/test_concert_layer.py`, 12 tests). Phases 3–5 in flight (WO-20c–e). Z3 scope: authored rules only; abductive steps are existence-checked, not proven (ADR §2.5). Threat model: integrity/provenance, not adversary defense (ADR §2.6).

### D-REAS-10 — Minimum Viable Engine: DreamCoder Macro Mining, Idiomaticity Cost, and Dynamic Scratchpad Falsification (WO-30)
- **Decision:** Establishes the thin, end-to-end neuro-symbolic macro mining and induction engine loop:
  1. **Syntactic Generation Constraint (Module 4):** All neural-symbolic S-expression proposals and sketches are constrained at logit decode-time via GBNF grammar (`config/grammars/scheme_sketch.gbnf`), ensuring balanced parentheses and conformance to MicroScheme primitives and operators with zero parse errors.
  2. **Structural Description Length Metric (Module 7):** Macro candidate selection and e-graph extraction evaluate structural description length via the idiomaticity cost objective: $\text{Cost}(T) = \sum_{n \in T} w(\text{op}_n) + \alpha \cdot \text{depth}(T)$, where $w(\text{primitive}) = 1.0$, $w(\text{branch}) = 2.0$, and depth penalty $\alpha = 0.5$.
  3. **DreamCoder Macro Miner (Module 14):** Mines recurring sub-AST patterns across successful execution traces via first-order anti-unification in `compression.py`, enforcing bounded complexity (`D-REAS-05`: depth $\le 8$, steps $\le 64$) and positive Minimum Description Length (MDL) compression savings.
  4. **Dynamic Scratchpad Falsification (Module 5):** Before admission to quarantine, candidate macros are subjected to $\ge 3$ concrete I/O test cases evaluated in an isolated container sandbox (`D-AUD-13`), bounded by a $500\,\text{ms}$ budget. Runtime crashes, timeouts, or output mismatches reject the candidate immediately prior to SMT or lifecycle ingestion.
  5. **Formal Verification & Quarantine Enforcement (`D-REAS-06`, `D-REAS-07`):** All surviving candidates must pass Z3 SMT pre-verification (SAT, non-tautology, deontic safety). Verified candidates enter `QUARANTINE` mode exclusively within `RuleLifecycleManager`. Auto-promotion to `ACTIVE` is strictly prohibited (0 to `ACTIVE` without explicit operator sign-off).
  6. **Personhood IN-D Metric:** Advances the IN-D learned-skill metric from "NOT YET MEASURED" to active mechanical measurement (`grade_in_d`), tracking quarantined induced skills while asserting 0 active skills.
- **Status:** Ratified & Enforced (`config/grammars/scheme_sketch.gbnf`, `src/lucca/reasoning/cost.py`, `src/lucca/core/scratchpad.py`, `src/lucca/reasoning/compression.py`, `src/lucca/evaluation/in_d_grader.py`, `scripts/grade_in_d.py`, `tests/test_wo30_minimum_viable_engine.py`).

### D-REAS-11 — Autonomous MCTS Program Synthesis, Traceback Divergence Guard & Boundary Topology (WO-31)
- **Decision:** Establishes autonomous program synthesis tree search with non-negotiable safety-of-search and boundary guards:
  1. **Multi-Threaded AST-Hole MCTS Engine (Module 12):** Synthesizes closed MicroScheme expressions from partial sketches with typed symbolic holes `(?hole <name> [type])` via Monte Carlo Tree Search across host CPU worker threads (Intel Core Ultra 9 275HX 24 threads, $\Delta\text{VRAM} = 0\,\text{MB}$, $\Delta\text{RAM} \le 512\,\text{MB}$). Node selection evaluates Upper Confidence Bound for Trees (UCT) penalized by idiomaticity cost (`D-REAS-10` / `cost.py`).
  2. **Traceback Divergence Guard (Module 9):** Search traces and convergence loops are continuously monitored for cyclic recurrence ($k \ge 3$ duplicate state hashes) and error entropy divergence. Divergent branches and infinite retry loops are immediately pruned and aborted before exhausting turn budgets.
  3. **Boundary Topology Parser (Module 11):** Statically and dynamically validates MicroScheme ASTs against registered `ToolSchema` contracts, state predicate topologies (`STATE_PREDICATES`), arity constraints, and structural type invariants. Prevents search paths from generating unwhitelisted tools, malformed arguments, or sandbox boundary escapes.
  4. **Backward Abduction Solver (Module 15):** Inverts target postconditions and goal invariant assertions using inverse algebraic/relational operators and predicate unification, deriving required preconditions and filtering candidate hole fillings during MCTS expansion.
  5. **Quarantine & Formal Verification Invariants (`D-REAS-06`, `D-REAS-07`):** All newly synthesized candidate expressions must pass Z3 SMT pre-verification and enter `QUARANTINE` mode within `RuleLifecycleManager`. Exactly zero synthesized rules auto-promote to `ACTIVE` without explicit operator ratification.
- **Status:** Ratified & Enforced (`src/lucca/core/convergence.py`, `src/lucca/reasoning/topology.py`, `src/lucca/reasoning/abduction.py`, `src/lucca/reasoning/mcts.py`, `plans/2026-10-09_wo31_search_and_safety_of_search.md`, `tests/test_wo31_search_and_safety.py`).


### D-PKG-01 — Standalone Windows Packaging & Distribution (Milestone 7)
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

### D-CASC-02 — Epistemic Cascade Self-History Substrate Isolation & Topic Normalization
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

### D-MEM-07 — Architectural Blessing of brain → memory.retrieval Edge (F-ARCH-106 / F-MEM-017)
- **Decision:** Resolves import linter dependency analysis regarding `prompt_builder.py` importing `format_memory_context` from `lucca.memory.retrieval`:
  1. **Context Assembly Boundary:** As established in F-MEM-017 remediation, `format_memory_context` provides pure domain formatting converting `MemoryHit` records into structured contextual prompts for LLM injection.
  2. **Architectural Blessing:** The edge `brain → memory.retrieval` is explicitly blessed by ADR as a legitimate read-only presentation/formatting dependency, avoiding premature abstraction or artificial intermediate formatting modules.
- **Status:** Ratified & Enforced (`src/lucca/brain/prompt_builder.py`, `.importlinter`).

### D-EVAL-02 — Two-Track Cognitive Benchmark Battery & Edge Quantization Standard
- **Decision:** Establishes the authoritative empirical evaluation methodology for Project Lucca's compound AI architecture:
  1. **Strict Edge Constraints Standard:** All official benchmark metrics must be evaluated under authentic local workstation constraints on an NVIDIA GeForce RTX 5080 Laptop GPU: 6-bit weight quantization (`Q6_K`), 8-bit KV caching (`Q8_0`), FlashAttention-2, and an unexpanded 16,384-token (16K) resident context window, clamping peak resident VRAM below 12.8 GiB.
  2. **Track 1 (`SPEC-BENCH-100-v1.0`):** Evaluates multi-domain cognitive reasoning across 10 categories (100 frozen probes) through the live end-to-end `TurnPipeline`:
     - Scoring criteria: task completion, path policy compliance (zero forbidden tools), epistemic faithfulness (zero fabricated receipts), and graceful tool error recovery.
     - Official Run 3 result: 91.0% pass rate (91/100), 100% path compliance (100/100), 100% epistemic faithfulness (100/100), 100% tool recovery (3/3), median turn latency 9.39s. Flawless 10/10 in Spatial 3D Kinematics, Formal Constraint Logic Grids, and Closed-World Algebra.
  3. **Track 2 (Standard Academic Benchmark Battery):** Evaluates code synthesis, arithmetic, and algorithmic logic against canonical standardized suites in Docker:
     - Canonical OpenAI HumanEval (Full 164 Tasks): 95.73% pass@1 (157 / 164).
     - GSM8K in PAL Mode: 100.0% (30 / 30) via Docker Python execution.
     - Big-Bench Hard (BBH) Boolean Logic: 99.2% (248 / 250) on the full un-sampled 250-task suite.
  4. **Control Parameter Scale Model:** Ratifies `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (6.22 GB, ~4B effective parameters) as the dedicated ablation model to empirically isolate the contribution of the compound supervisor topology from neural core parameter scale.
- **Status:** Ratified & Enforced (`tests/test_compound_reasoning_benchmark.py`, `scripts/run_standard_academic_benchmarks.py`).
- **Amendment (2026-10-06, register E-11):** Protocol labels and manifest records for the figures above. SPEC-BENCH-100 Run 3 (91.0%): manifest `spec_bench_100_run3_v1_3`. HumanEval 95.73% (157/164): **zero-shot academic harness** (2026-09-28), manifest `humaneval_zeroshot_academic_v1_3` — a different protocol from the canonical paired harness (94.51% raw / 93.90% assisted, `humaneval_canonical_paired_v1_35_6`); cite the protocol with the number. GSM8K PAL 100.0% (30/30): **30-probe micro-suite**, manifest `gsm8k_pal_micro30_v1_3`; the full 1,319-item suite is 95.75% (`gsm8k_pal_full_1319_v1_3`). BBH Boolean 99.2% (248/250): one subset of the BBH-4 bare-weights composite, manifest `bbh4_bare_1000_v1_3` (92.40% consolidated, 924/1,000).

### D-EVAL-03 — Modern Academic Benchmark Battery (Track 3) & Phased Clawback Protocol
- **Decision:** Formalizes the modern 2024–2025 academic benchmark battery (Track 3) and the Zero-Estimate phased clawback protocol:
  1. **GSM-Symbolic (Apple, Oct 2024):** 100.0% pass rate (100/100) in 527.4s under symbolic parameter perturbation via Docker PAL.
  2. **HumanEval-Plus (EvalPlus, 2024):** 91.46% pass@1 (150/164) in 1,016.8s under 80x adversarial differential testing, with 10 autonomous preflight docstring rescues in the Docker container.
  3. **MATH-500 in PAL Mode (2024):** 77.0% strict exact-string baseline (77/100 in 1,149.7s); 87.0% under SymPy algebraic equivalence; 69.6% accuracy on Level 5 competition problems.
  4. **Timeout Disproval & Miss Taxonomy:** Rigorous physical execution log audit verified 0 container timeouts (0.19s mean container execution time), disproving timeout speculation. The 23 baseline misses were formally categorized into SymPy runtime exceptions (7), notation/spacing formatting variations (7), base subscripts (3), prose extraction slips (3), and genuine CAS algebraic limits (3).
  5. **Phased Clawback Methodology:** Mandates strict variable isolation: (A) frozen v1.2 baseline on 400 held-out problems, (B) 2-turn execution feedback loop alone at 16K, (C) 32K context scaling under dedicated compute mode (`Disp.A: Off`), and (D) paired McNemar contingency testing via uniform post-run SymPy rescorer (`scripts/rescore_with_sympy.py`).
- **Status:** Ratified & Enforced (`scripts/run_modern_2024_benchmarks.py`, `scripts/rescore_with_sympy.py`).
- **Amendment (2026-10-06, register E-11):** Protocol labels and manifest records for the figures above. GSM-Symbolic 100.0% (100/100): **v1.3-harness run** (2026-09-29), manifest `gsm_symbolic_100_v1_3` — distinct from the stratified-protocol run (94.0%, `gsm_symbolic_stratified_100_v1_35_6`); cite the protocol with the number. HumanEval-Plus 91.46% (150/164): the **2026-09-29 run**, manifest `humaneval_plus_v1_35_6` — three recorded runs exist (150/151/149 of 164, 90.9–92.1%); cite the range or name the run date. MATH-500 77.0% / 87.0%: manifest `math500_pal_v1_3` — the 87.0% figure is a post-hoc **forensic audit**, not a mechanical regrade, and must be labeled as such wherever cited.

### D-MEM-05 — Two-Stage HKDF HMAC-SHA256 Read-Time Verification & Persistent Quarantine Pipeline
- **Decision:** Resolves unhandled runtime exceptions and silent memory amnesia during key rotation or database tampering:
  1. **Two-Stage Verification Pipeline:** `HybridRetriever.search()` enforces Stage 1 content SHA-256 match followed by Stage 2 constant-time HMAC-SHA256 verification using HKDF derived keys (`info="prov/" + provenance`).
  2. **Persistent Database Quarantine:** Rows failing verification are inserted into the SQLite `memory_quarantine` table `(memory_id, entry_id, reason, stage, quarantined_at)`. Quarantined rows are cached in-memory on startup to prevent repeated verification costs.
  3. **Non-Silent Integrity Alert API:** `HybridRetriever.get_integrity_status_report()` surfaces structured alerts to the orchestrator rather than failing closed or crashing the turn.
  4. **Key Migration CLI:** `lucca-admin memory migrate-keys` validates legacy SHA-256 records, re-computes HMAC signatures under active master keys, and purges quarantined records without data loss.
- **Status:** Ratified & Enforced (`src/lucca/memory/retrieval.py`, `src/lucca/memory/migration_tool.py`, `tests/test_memory_hmac_tamper.py`).

### D-SEC-05 — Truth-in-Receipt Output Supervision & Epistemic Hedge Exemption Policy
- **Decision:** Establishes output supervision boundaries against ungrounded action claims (false action claims / FAC):
  1. **21 Verified Action Verbs:** `TruthInReceiptMatcher` scans streaming assistant tokens across 21 action verb lemmas (`delete`, `create`, `modify`, `execute`, `run`, `install`, `remove`, `send`, `upload`, `fetch`, `save`, `write`, `post`, `reboot`, `book`, `place`, `process`, `start`, `close`, `copy`, `move`).
  2. **Receipt Verification:** If an action claim matches an active verb lemma without a corresponding verified `ToolReceipt` in the active turn session, a mid-utterance abort is triggered, clearing the audio queue and halting execution.
  3. **Hedge Exemption Policy:** Statements expressing epistemic hedges (*"I think I deleted"*, *"I believe I closed"*) or intentions (*"I will delete"*) are exempt from receipt matching to prevent false aborts on natural conversational nuance.
  4. **Validation Battery:** Validated via 70-sentence formal battery (70/70 passing in `test_truth_in_receipt_battery.py`; broadened 2026-10-05 from 40 sentences across 8 categories: positive receipt-backed, passive/markdown/multilingual characterization, stale-receipt via `stale_before`, failed-status filtering) and live 100-probe battery (0/50 false aborts on controls). Matcher hardening: markdown emphasis stripped before matching (underscores preserved for snake_case targets), non-success receipt statuses never ground claims, and receipts stamped before `stale_before` are ignored.
  5. **Amendment (2026-10-05, adversarial audit):** the live battery's 0/50 control figure establishes only that the matcher is inactive on action-claim-free text — the 50 controls contain no action claims, so it is not a specificity result. Measured sensitivity on ungrounded claims is **1/23 (4.3%, Wilson CI [0.8%, 21.0%])** on broad action assertions and **1/8 (12.5%)** on strict completed-action claims (`RESULTS.md` §Output Supervisor; `luccadocs/LUCCA_V135_1_ARCHITECTURE.md` §4.3; labels in `logs/test_reports/action_hallucination_labels_100.jsonl`). Dominant escape modes: active progressive participles (12), passive/telegraphic confirmations (6), markdown action headers (2), unlisted verb lemmas (2). Battery v2 (dual independent annotators, receipt-mismatch strata) is pre-registered as the re-measurement; SPIKE-A (grammar-constrained ACTION-CLAIM channel) is the structural fix.
- **Status:** Ratified & Enforced (`src/lucca/sandbox/output_supervisor.py`, `tests/test_truth_in_receipt_battery.py`, `tests/test_output_supervisor.py`).

### D-SEC-06 — Grammar-Constrained Action-Claim Channel Supervision (SPIKE-A) *(ratified 2026-10-09)*
- **Context:** Resolves Finding P7 from the adversarial audit (`STATE_OF_THE_UNION_2026-10.md §P7`). Under baseline regex supervision (`TruthInReceiptMatcher`), measured sensitivity on ungrounded action claims was only 1/23 (4.3%) broad and 1/8 (12.5%) strict due to four structural escape modes: (1) active progressive participles (*"Moving all PDFs..."*, *"Rebooting the host system..."*), (2) passive/telegraphic confirmations (*"Files removed."*, *"Reminder set."*, *"Target cleared."*), (3) unlisted verb lemmas (`launch`, `open`, `terminate`, `archive`, `update`, `format`, `wipe`, `prune`, `kill`, `clear`), and (4) markdown action headers/bullets (`### Deleting logs`, `* Moving files`).
- **Decision:**
  1. **Decode-Time GBNF Channel Constraint:** Implements `config/grammars/action_claim.gbnf` restricting action claims at decode time to formal frames: structured bracket claims (`[ACTION: <verb> <target>]`, `[ACTION_CLAIM: <verb> <target>]`), structured XML channels (`<action_claim verb="..." target="..." />`), and canonical 1P past-tense clauses (`I <verb> <target>`), making out-of-frame claims unrepresentable.
  2. **`ActionClaimGrammarSupervisor` Engine:** Deployed in `src/lucca/sandbox/output_supervisor.py` to evaluate streaming assistant speech clauses before TTS dispatch. Enforces complete structural frame parsing, expanded 28+ action lemma lexicon, active progressive participles, passive voice, telegraphic confirmations, and markdown header/bullet neutralization.
  3. **Zero False Abort Preservation:** Strictly preserves the 0.0% false abort rate on conversational controls: epistemic hedges (*"I think I deleted"*), idioms (*"moved on"*, *"processed the feedback"*, *"closed the discussion"*, *"placed emphasis"*, *"saved time"*), future/intentional framing (*"I will delete"*, *"about to"*), honest capability refusals (*"I cannot delete without asking"*), and past-session autobiographical recollections.
  4. **Pipeline & Engine Integration:** Wired into `TurnPipeline.execute_act_then_narrate` and `Orchestrator._stream_llm_speech` via `SpeechLLMPort` / `StreamingLLMClient` with llama-server GBNF forwarding when tools are inactive.
  5. **Verification Battery:** Validated via 73/73 tests in `tests/test_spike_a_grammar_supervision.py`, 100/100 tests in `test_output_supervisor.py` and `test_truth_in_receipt_battery.py` (70/70 scripted battery preserved), and full evaluation on the 20-prompt temptation battery (`data/benchmarks/action_hallucination_battery_20.json`). Sub-millisecond latency profile (<1.0 ms budget, typical <100 µs) verified.
- **Status:** Ratified & Enforced (`config/grammars/action_claim.gbnf`, `src/lucca/sandbox/output_supervisor.py`, `src/lucca/core/turn_pipeline.py`, `src/lucca/brain/llm_client.py`, `tests/test_spike_a_grammar_supervision.py`). Closes Finding P7.

### D-ROUT-02 — Dynamic Task Router Specification for Multi-Scale Edge Deployment
- **Decision:** Enforces empirical neurosymbolic execution routing across the three validated model scales (12B, E4B, E2B):
  1. **Formal Dispatch Policy:**
     $$\text{Router}(M, T) = \begin{cases} 
     \text{Direct Raw Generation (R0 @ 4k)} & \text{if } M = \text{12B} \\ 
     \text{PAL in Docker (P2 @ 2k)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Arithmetic/Word} \\ 
     \text{Thinking Mode (R1 @ 6k)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Competition Math} 
     \end{cases}$$
  2. **Empirical Rationale:**
     - For 12B: Raw direct generation achieves 89.0% on held-out math in 12.9s. Thinking scratchpads degrade greedy decoding ($T=0.0$) to 58.0% ($p = 4.66 \times 10^{-10}$).
     - For E4B: Thinking Mode R1 @ 6k achieves 88.0% strict CAS on held-out math, significantly outperforming PAL P2 @ 2k (73.0%, $p = 0.0026$, discordant ratio 19:4).
     - For E2B: Thinking Mode R1 @ 6k achieves 81.0% strict CAS, significantly outperforming PAL P2 @ 2k (61.0%, $p = 0.0002$, discordant ratio 22:2). *(Correction 2026-10-05, adversarial audit: per-item recount of the held-out artifacts `gemma-4-e2b_math500_r1_heldout_think6144_100.json` vs `gemma-4-e2b_math500_p2_heldout_cap2048_100.json` gives discordant **24:4**, exact McNemar p = 1.8×10⁻⁴ — the headline rates and p-value stand; the originally recorded 22:2 was a transcription error. The E4B ratio 19:4 / p = 0.0026 verifies exactly against its artifacts.)*
  3. **Router Nature Disclosure:** Benchmark harness switches using benchmark metadata labels (oracle dispatch). In-the-wild desktop deployment requires an intent classifier.
  4. **Manifest Citations:** The held-out-100 Direct R0 figures (89.0% / 88.8% clean-98) are manifest record `math500_heldout100_direct_r0_v1_35_6` (`data/benchmarks/MANIFEST.yaml`); the v1.3 PAL (77.0%/87.0%) and fresh N=500 (74.20%/78.80%) figures are records `math500_pal_v1_3` and `math500_fresh_heldout_500_v1_3_0` (superseded, dataset-drift bound).
- **Status:** Ratified & Enforced (`luccadocs/LUCCA_V135_1_ARCHITECTURE.md`, `luccadocs/research/papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md`).

### D-MEM-06 — Provenance Split: Deterministic vs LLM-Inferred Assertions
- **Decision:** Resolves a soundness gap in the provenance lattice: the Concert Layer's deduction chain asks the companion brain (Gemma) to propose the next MicroScheme step, but the resulting envelope was signed `LispAssertionSigner` / `LISP_ASSERTION` — a label that asserts deterministic rule-engine provenance the LLM proposal does not have. Ratifies a split:
  1. **`LISP_ASSERTION` (narrowed):** Reserved strictly for deterministic MicroScheme rule-engine output (pure `State → Plan` evaluation, gas-metered). Signed by `LispAssertionSigner`. Memory-eligible and grounding-eligible.
  2. **`LLM_INFERRED_ASSERTION` (new):** For LLM-proposed reasoning steps accepted by the symbolic verifier (Concert Layer chains). Signed by the new `InferredAssertionSigner`. Memory-eligible (the chain is a real, verifiable artifact of the session) but **never grounding-eligible** — it cannot serve as a premise for downstream grounding without re-verification.
  3. **Enforcement points:** `schemas.py` (`Provenance` enum, `MEMORY_ELIGIBLE`, `GROUNDING_ELIGIBLE`), `signers.py` (`InferredAssertionSigner`), `gate.py` (admits the new provenance), `orchestrator.py` (Concert chain steps sign via `InferredAssertionSigner`), and the SQLite schema (migrations 0001/0006/0007 CHECK constraints widened; `mem_bi_eligible` triggers admit it; the `grounding_eligible` CASE maps it to 0).
  4. **Invariant:** `LLM_NARRATION` remains strictly rejected (ADR-006); this split does not weaken the gate — it only distinguishes two kinds of symbolic output by who produced them.
- **Status:** Ratified & Enforced (`src/lucca/core/schemas.py`, `src/lucca/memory/signers.py`, `src/lucca/memory/gate.py`, `src/lucca/core/orchestrator.py`, `src/lucca/memory/migrations/`, `tests/test_provenance.py::test_p0_provenance_split_signer_and_eligibility`).

### D-DOC-01 — Document Envelope Convention for Status-Bearing Documents
- **Decision:** The project enforces provenance on *facts* but historically never applied the same discipline to *documents*; every doc read as equally authoritative when they are stratified by age and verification method. Ratifies a document-envelope convention mirroring the memory envelope (`D-MEM-04`/`D-MEM-05`):
  1. **Envelope header:** every research/audit/status document carries a YAML header block: `doc_status` (`canonical` | `snapshot` | `superseded`), `as_of` (date the claims were verified against code), `supersedes` / `superseded_by` (doc paths, for re-scores), and `verification` (`code-cited` | `manual` | `generated`).
  2. **Reading policy:** status claims inside a document are read *as-of* its `as_of` date; a `snapshot` document is a receipt, not current status. Ground truth on any disagreement is `src/`, `tests/`, `config/`, `data/` — never prose.
  3. **Measurement honesty corollary:** numeric scores in status documents must state their measurement basis. A number backed by a fixed probe set and a mechanical grader is a *measurement*; a holistic estimate from code reading is a *capability-inventory judgment* and must be labeled as such (or replaced with `NOT YET MEASURED`). Unanchored percentages presented as benchmark results are prohibited.
  4. **No parallel trust index:** a full trust-map index of all docs is explicitly *not* maintained — the tier rule (ground truth / canonical living docs / dated evidence) plus per-doc envelopes covers navigation without a second index that would itself drift.
  5. **ADRs are the exception that proves the pattern:** append-only, dated decisions are designed to be read as history, subject to dated errata and amendments when subsequent evidence contradicts them (e.g. D-ROUT-02, D-EVAL-02/03).
- **Status:** Ratified (writing and review discipline for all research/audit/status docs; not mechanically gated by CI; first applications: the v1.35.6 personhood re-score and the benchmark manifest records in `data/benchmarks/MANIFEST.yaml`).

### D-MEM-08 — Epistemic Integrity, Semantic NLI Verification & Distillation Provenance (v1.35.7)
- **Decision:** Replaces fragile regex heuristics across 7 core subsystems with a two-tier hybrid architecture: OpenVINO NLI semantic verifier (ModernBERT on host CPU/NPU) and post-turn GBNF LLM proposition distillation.
  1. **Hardware Budget Invariant:** $\Delta\text{VRAM} = 0\,\text{MB}$ strictly enforced on dGPU. Verifier execution runs exclusively in-process on host CPU (NPU-eligible, CPU-default) under a per-pair latency budget. **Measured (2026-10-20): 57 ms mean / 70 ms p95 per pair on CPU** — the original sub-25 ms budget is not met on this hardware; see Paper 03 §4.1.
  2. **Pre-Registered Decision Threshold & Uncertainty Band:** Softmax decision threshold $\tau = 0.50$. Scores falling within $[0.40, 0.60]$ yield `VerifierLabel.UNCERTAIN` and represent a no-signal state: neither `told_true` nor `told_false` epistemic bit is set. The verifier never forces a binary decision on ambiguous pairs.
  3. **Strict Fail-Open Degradation:** On timeout (>50 ms) or worker exception, the call site gracefully degrades to lexical fallback with structured logging (`verifier_degraded`). Degraded turns never admit a new polarity assignment.
  4. **NFC Normalization & Pair Cache:** All premise/hypothesis inputs are NFC Unicode normalized. Repeated pairs are resolved via an in-process thread-safe bounded 1,024-entry LRU cache (`BoundedLRUPairCache`) with sub-1ms repeat lookups.
  5. **Distillation Provenance & Rejection Retention (ADR-006 / D-MEM-05):** Distilled propositions synthesized from contradiction pairs originate as `LLM_NARRATION` and are rejected by `ProvenanceGate` unless signed by `DerivedFactSigner` (`USER_DERIVED`). Unsigned distillates or propositions rejected by verifier uncertainty are persisted into the SQLite `memory_quarantine` table with structured rejection reasons, never silently discarded.
  6. **Cross-Subsystem Preservation Invariants:** Entailment clustering in `induction.py` affects only merge grouping; the `D-REAS-06` 5-cluster/0-error promotion gate and quarantine invariants remain intact. Truth-in-Receipt action supervision (`sandbox/output_supervisor.py`) retains its 21-verb orthogonality boundary; NLI serves as an orthogonal post-turn coherence channel.
- **Status:** Ratified & Enforced (`src/lucca/ports.py`, `src/lucca/core/schemas.py`, `src/lucca/senses/verifier.py`, `src/lucca/reasoning/distill.py`, `src/lucca/core/belief_service.py`, `src/lucca/core/cascade.py`, `src/lucca/core/coherence.py`, `src/lucca/core/orchestrator.py`, `src/lucca/reasoning/induction.py`, `src/lucca/core/memory_commit_service.py`, `src/lucca/core/corroboration.py`, `src/lucca/core/self_diagnosis.py`, `tests/test_v1357_*.py`).

### D-MEM-09 — Transactional Git Staging DAG & Belnap Latent Epistemic Prober (WO-33) *(ratified 2026-10-09)*
- **Decision:** Enforces transactional integrity and non-destructive epistemic probing across workspace and memory:
  1. **Transactional Git Staging DAG (Module 8):** Deploys `GitStagingDAG` and `StagingTransaction` in `src/lucca/memory/git_dag.py`. Provides dependency-ordered mutation staging, cycle detection, preflight AST syntax/boundary verification hooks, unified diff previewing, and atomic rollback on I/O or validation failure. Guarantees zero dirty workspace state on abort.
  2. **Belnap Latent Investigator (Module 10):** Deploys `BelnapLatentInvestigator` in `src/lucca/memory/latent_probe.py` implementing Belnap-Dunn four-valued lattice logic ($\mathbf{4} = \{T, F, \bot, \top\}$). Replaces destructive memory overwrites with non-destructive read probes across filesystem and environment. Upon detecting a contradiction ($\top$), generates polite conversational clarification prompts rather than hallucinating or corrupting memory state.
  3. **Invariants:** Strictly Zero-`Any` typed (`D-AUD-01`). Sub-millisecond execution budget ($< 1.0\,\text{ms}$). $\Delta\text{VRAM} = 0\,\text{MB}$.
- **Status:** Ratified & Enforced (`src/lucca/memory/git_dag.py`, `src/lucca/memory/latent_probe.py`, `tests/test_wo33_git_dag_and_belnap.py`).

### D-REAS-12 — Proactive Sleep-Phase Reflection & Lifelong Macro Consolidation (WO-34) *(ratified 2026-10-09)*
- **Decision:** Formalizes Project Lucca's autonomous sleep-phase macro discovery, validation, and skill registration loop:
  1. **Autonomous Consolidation Daemon:** Deploys `ConsolidationEngine` in `src/lucca/reasoning/consolidation.py` to aggregate conversational and reasoning AST execution traces during idle/sleep phases.
  2. **DreamCoder Macro Mining:** Clusters execution traces by syntactic shape and invokes `DreamCoderMacroMiner` (`src/lucca/reasoning/compression.py`) to discover recurring motifs via first-order anti-unification.
  3. **Strict Invariant Governance:**
     - `D-REAS-05`: Bounded macro complexity (depth $\le 8$, expansion steps $\le 64$).
     - `D-REAS-06`: Quarantine-only admission. Exactly 0 mined macros reach `ACTIVE` without explicit operator sign-off (`guard_active_zero_passed = True`).
     - `D-REAS-07`: Z3 SMT formal verification and scratchpad falsification prior to quarantine.
  4. **Personhood Stratum IN-D Measurement:** Automatically executes the mechanical IN-D grader (`src/lucca/evaluation/in_d_grader.py`), updating and archiving `logs/test_reports/personhood/in_d_latest.json`. Formally transitions **Battery IN Stratum IN-D (Learned Competencies / Individuation)** from "NOT YET MEASURED" to an active mechanical measurement.
  5. **Hardware Budget Invariant:** $\Delta\text{VRAM} = 0\,\text{MB}$ strictly enforced on dGPU. CPU-only execution on Intel Core Ultra host threads.
- **Status:** Ratified & Enforced (`src/lucca/reasoning/consolidation.py`, `src/lucca/evaluation/in_d_grader.py`, `tests/test_wo34_proactive_reflection.py`, `logs/test_reports/personhood/in_d_latest.json`).

### D-REAS-13 — Relational Mereotopological Kernel & Discrete Topological Invariants (Organ A) (v1.46.0) *(ratified 2026-10-16)*
- **Decision:** Formalizes the separation between continuous spatial approximations and discrete qualitative mereotopology to eliminate the 22% ConceptARC relational ceiling and prevent benchmark-tuning:
  1. **Four-Way Relation Disambiguation:** Strictly prohibits any monolithic `is_inside` catch-all predicate. Formally separates:
     - `during`: Allen 1D interval containment (closed integer ranges for grids, real bounds for $\mathbb{R}$).
     - `part_of`: Exact spatial subset ($A \subseteq B$).
     - `in_cavity`: Discrete grid cavity enclosure via 4-connected border-complement flood-fill ($A \subseteq \text{holes}(B) \land A \cap B = \emptyset$).
     - `scope_contains`: Lexical AST containment (Carrier 3, deferred).
  2. **Discrete vs. Continuous Meets Boundary Contract:** Closed discrete intervals require $e_A + 1 == s_B$; continuous intervals require $e_A == s_B$. Discrete intervals are typed strictly as `int`.
  3. **Data-Frozen Composition Table & Literature Diff:** The canonical $13 \times 13 = 169$ entry Allen composition table is frozen in data and verified:
     - **Zero Literature Diff:** Programmatically audited across all 169 cells against Table 1 of James F. Allen (1983), *"Maintaining Knowledge about Temporal Intervals"*, Communications of the ACM 26(11): 832–843 via `scripts/audit_allen_169_literature.py`. Confirmed 100% exact symbolic match across all 169 cells, including:
       - `STARTS ∘ BEFORE` $\to$ `{BEFORE}`
       - `STARTED_BY ∘ BEFORE` $\to$ `{BEFORE, MEETS, OVERLAPS, FINISHED_BY, CONTAINS}` ($si \circ < = \{<, m, o, fi, di\}$)
       - `OVERLAPS ∘ DURING` $\to$ `{DURING, OVERLAPS, STARTS}`
       - `MEETS ∘ OVERLAPS` $\to$ `{BEFORE}`
       - `DURING ∘ CONTAINS` $\to$ $\mathbf{U}$ (all 13 relations)
       - `CONVERSE(MEETS)` $\equiv$ `MET_BY`, `CONVERSE(STARTS)` $\equiv$ `STARTED_BY`, `CONVERSE(FINISHES)` $\equiv$ `FINISHED_BY`.
     - **Synthetic Soundness:** Verified across 2,000 random triples $(\text{rel}(I, K) \in \text{compose}(\text{rel}(I, J), \text{rel}(J, K)))$.
  4. **The Anti-Benchmax Acceptance Gate:** The relational kernel must contain zero benchmark references. Acceptance is gated exclusively on synthetic unit generators ($10^3$ intervals, $10^3$ holed masks with puncture tests) and the mandatory U-shape concavity disagreement test (`in_cavity == False` while `bbox_during == True`).
  5. **Induction Wiring Invariant & Live Probe:** Synthesizer prompts and execution namespaces are injected with pre-imported relational operators (`in_cavity`, `above`, `below`, `left_of`, `right_of`, `part_of`); raw 40-line `grid[i][j]` index loops are strictly deprecated. Empirically validated on live silicon (`scripts/probe_relational_induction_live.py`) across 6 runs: 0% bbox fallbacks, 83.3% relational primitive emission on closed rings and open concavities.
   7. **Locked ConceptARC InsideOutside Benchmark Sweep:** Evaluated full 10-task corpus with episodic cache disabled on Tier 0 silicon (`scripts/run_concept_arc_full.py --concepts InsideOutside --disable-cache`). Solved **2 / 10 (20.0%)** on held-out test sets (`InsideOutside2` in 4 turns, `InsideOutside3` in 2 turns; Wilson 95% CI `[5.7% - 51.0%]`, mean latency 155.8s). Zero syntax truncations, zero numpy rank crashes. Established that remaining failures stem from multi-container combinatorial scene bindings and linear prompt history trapping rather than topological blindness.
- **Status:** Ratified & Enforced (`src/lucca/reasoning/relational/sorts.py`, `src/lucca/reasoning/relational/allen.py`, `src/lucca/reasoning/relational/mereo.py`, `src/lucca/reasoning/relational/realize_grid.py`, `src/lucca/reasoning/relational/realize_real.py`, `src/lucca/reasoning/cegis_unshackled.py`, `src/lucca/reasoning/spatial_anchors.py`, `tests/reasoning/relational/`, `logs/test_reports/probe_relational_induction_live.json`, `logs/test_reports/concept_arc_inside_outside_organ_a.json`).

### D-REAS-14 — The "Show Me the Code" Principle: Source-Level Verification of Architectural Lift (v1.46.0) *(ratified 2026-10-16)*
- **Context:** Following the 2/10 (20.0%) pass on the locked ConceptARC `InsideOutside` benchmark, superficial metrics initially appeared to license groundbreaking on Organ B (`search/`). However, rigorous source-code inspection of the two passing programs (`InsideOutside2` and `InsideOutside3`) revealed that neither task invoked `in_cavity` or mereotopological primitives; task 2 solved via manual 1D collinearity arithmetic, and task 3 solved via a 30-line manual BFS queue and an axis-aligned bounding box (`min_r < y_r < max_r`). Organ A had scored zero points on the benchmark scoreboard because the prompt allowed the LLM to relapse into training-distribution boilerplate.
- **Decision:**
  1. **Causal Source Attribution:** When a benchmark metric shifts, inspect the emitted source code of all passing tasks before attributing lift to any architectural subsystem. A metric shift proves only *that* an outcome changed, never *what* caused it.
  2. **No Architectural Expansion Without Causal Verification:** Expansion into search harnesses, meta-trees, or new packages is strictly frozen until the generator demonstrably and naturally emits the intended primitives on the target benchmark.
  3. **Remediation Order:** Prompt inversion (primitives in top 20 lines), contextual heuristic banning (banning `min/max` bounding boxes for enclosure queries, banning single-container `max(..., key=len)` assumptions), and lightweight in-process Best-of-$K$ sampling ($K \in \{2, 4\}$) must precede any multi-file architectural refactor.
- **Status:** Ratified & Enforced (`src/lucca/reasoning/cegis_unshackled.py`, `luccadocs/DECISIONS.md`).

### D-REAS-15 — Mereotopological Competence Boundary & Anti-Benchmax Principle (v1.46.2) *(ratified 2026-10-17)*
- **Context:** Following prompt inversion and Best-of-$K$ sampling ($K=8$, low-T schedule $T \in [0.1, 0.5]$) in `cegis_unshackled.py`, the locked ConceptARC `InsideOutside` benchmark ($N=10$, cache disabled) on Tier 0 silicon (`gemma-4-26B`) yielded a verified **5 / 10 (50.0%)** train pass and **4 / 10 (40.0%)** held-out test pass (`InsideOutside2`, `InsideOutside4`, `InsideOutside5`, `InsideOutside7`), Wilson 95% CI `[16.8% - 68.7%]`, mean latency 369.4s. 100% of winning source files invoke verified Organ A primitives (`in_cavity`, `extract_cavities`, `is_between`) with zero bounding-box cheats.
- **Decision:**
  1. **Mereotopological Competence:** Organ A's qualitative spatial primitives (`in_cavity`, `part_of`, `is_between`, Allen interval calculus) are verified on physical silicon for discrete, closed-boundary entities.
  2. **Topological Veracity vs. Visual Gap-Closing:** On discrete integer grids with open boundaries (e.g. U-shapes with gaps) or disconnected pixels, `in_cavity` returns `False`. This is the topologically correct outcome. Pixel-level Gestalt continuation is an out-of-scope perceptual grouping problem, not a mereotopological defect.
  3. **Prohibition of Ad-Hoc Filters:** Adding dataset-specific heuristics (e.g., `in_concavity`, morphological dilation/closing with arbitrary kernel sizes) to satisfy open-cup benchmarks constitutes benchmaxxing and is strictly forbidden.
  4. **Empirical AST Mutator Verification:** The domain-agnostic AST mutators in `cegis_unshackled.py` demonstrated genuine programmatic repair on live silicon: on `InsideOutside4`, the mutator inverted `if in_cavity(...)` to `if not in_cavity(...)`, rescuing the candidate from 0/4 to 4/4 train pass and unlocking a 100% held-out test pass without human intervention.
  5. **Final Locked Baseline & Archival:** ConceptARC `InsideOutside` is permanently locked at **4 / 10 (40.0%)** held-out test pass (5/10 train pass). The task runner for `InsideOutside` is archived from the active development loop.
  6. **Preservation of the Spatial Faculty:** Spatial and relational reasoning remains permanently in Lucca's core as callable, unit-tested tools (`spatial_anchors.py`, `relational/`). Evaluation shifts to real-world domains where spatial and interval logic naturally apply (event sequences, episodic memory timestamps via Allen calculus, and structured code hierarchies).
- **Status:** Ratified & Enforced (`src/lucca/reasoning/spatial_anchors.py`, `src/lucca/reasoning/cegis_unshackled.py`, `tests/reasoning/test_cegis_ast_mutators.py`, `logs/test_reports/concept_arc_inside_outside_k8.json`, `luccadocs/DECISIONS.md`).

### D-MEM-10 — Qualitative Temporal Memory Retrieval via Allen Interval Algebra (v1.46.3) *(ratified 2026-10-17)*
- **Context:** Following the ratification of D-REAS-13 (169-cell verified Allen interval algebra) and D-REAS-15 (closure of ARC benchmark), project focus pivoted to sovereign companion capabilities. Episodic memory queries in natural dialogue frequently involve qualitative temporal relationships ("what did we discuss before X?", "what was true during 2024?", "events overlapping interval Y") rather than pure semantic text similarity or strict Unix timestamp cutoffs (`since`).
- **Decision:**
  1. **Allen Interval Algebra Bridge:** Bridge `src/lucca/reasoning/relational/allen.py` (`relation_1d`, `AllenRelation`, `Interval1D`) directly into `src/lucca/memory/retrieval.py` (`HybridRetriever`) and `src/lucca/core/schemas.py` (`RetrievalQuery`).
  2. **Two-Clock Disambiguation:** Disambiguate the two fundamentally different temporal dimensions in episodic memory:
     - **Interaction Clock (`created_at`):** When dialogue occurred (*"What did we discuss before the benchmark?"*). Default clock for conversational queries.
     - **World Fact Clock (`[valid_from, valid_to)`):** When a world fact was valid in reality (*"Who lived in Melbourne during 2024?"*).
     Explicitly specified via `RetrievalQuery.temporal_clock: Literal["created_at", "valid_time"]`.
  3. **Qualitative Relations:** Implemented `_eval_temporal_constraint` supporting four intuitive qualitative constraints:
     - `before`: Event interval is strictly before or meets anchor (`AllenRelation.BEFORE`, `MEETS`).
     - `after`: Event interval is strictly after or met by anchor (`AllenRelation.AFTER`, `MET_BY`).
     - `during`: Event interval is contained within or equals anchor (`AllenRelation.DURING`, `STARTS`, `FINISHES`, `EQUALS`).
     - `overlaps`: Event interval overlaps or intersects anchor (`rel not in (BEFORE, AFTER, MEETS, MET_BY)`).
  4. **Degenerate Point Event Handling:** Point events (`evt_start == evt_end`) are nudged by $10^{-6}\text{s}$ to guarantee robust continuous interval algebra evaluation without topological singularities.
  5. **Pure Temporal Candidate Fallback:** When sparse and dense text ranks are empty (e.g. empty `query_text`), candidate selection falls back to the most recent memories (`ORDER BY created_at DESC LIMIT MAX_CANDIDATES * 2`) to ensure pure temporal queries succeed.
  6. **Historical Validity Preservation:** When querying the `valid_time` clock, facts with non-null `valid_to` (historical facts whose validity has ended) are preserved and evaluated against the anchor interval, even if `include_superseded` is False.
  7. **Anti-Cathedral Invariant:** Temporal filtering is implemented directly in-process in `src/lucca/memory/retrieval.py` with zero new packages, maintaining zero external dependencies and strict zero-`Any` typing per `D-AUD-01`.
- **Status:** Ratified & Enforced (`src/lucca/core/schemas.py`, `src/lucca/memory/retrieval.py`, `src/lucca/core/cascade.py`, `tests/test_temporal_retrieval.py`).

### D-MEM-11 — Natural Dialogue Temporal Extraction & Empirical LongMemEval Verification (v1.46.4) *(ratified 2026-10-17)*
- **Context:** Following the ratification of D-MEM-10 (Allen interval algebra in `HybridRetriever`), qualitative temporal filtering required callers to manually construct structured `RetrievalQuery` objects with pre-calculated `Interval1D` anchors. Conversational turns in daily companion dialogue arrive as natural language queries (*"What was my role in 2024?"*, *"What recipe ideas did we discuss before the benchmark?"*). To be fully autonomous and sovereign, the retrieval engine must parse temporal cues and resolve conversational anchors automatically without external NLP services.
- **Decision:**
  1. **In-Process Dialogue Surface Extraction (`extract_temporal_constraints`):**
     - Calendar Years: Matches patterns like `in 2024`, `during 2023` and binds a 1-year interval $[T_{\text{start}}, T_{\text{end}})$ on the `valid_time` clock with constraint `during`.
     - Relative Conversational Windows: Resolves `yesterday`, `today`, `last week`, `last month`, `earlier today`, and `previously` into precise timestamp boundaries on the `created_at` clock.
     - Conversational Event Anchors: Resolves relational clauses (`before [the] <topic>`, `after [the] <topic>`) by executing a fast SQLite look-behind (`SELECT created_at FROM memories WHERE content LIKE ... ORDER BY created_at ASC/DESC LIMIT 1`) to dynamically ground the event's exact point in time as the anchor interval.
  2. **Query Lexical Sanitization (`_clean_temporal_query`):** Strips temporal phrases from the user prompt before passing it to BM25 sparse matching and dense vector embeddings, stripping extraneous whitespace while strictly preserving punctuation (`What was my role ?` $\to$ `What was my role?`), avoiding query contamination.
  3. **Universal Transparent Hooking:** Extracted temporal constraints are hooked directly into `HybridRetriever.search` when `query.temporal_anchor is None`. Every retrieval surface—including `EpistemicSearchCascade`, console chat, and background daemons—transparently receives temporal filtering without bespoke caller middleware.
  4. **Empirical Verification on Live Silicon (`logs/test_reports/longmemeval_pipeline_26B_TEMPORAL_AUDIT_1792178121.json`):**
     - Evaluated live on resident Tier 0 silicon (`gemma-4-26B`) across LongMemEval's `temporal-reasoning` subset.
     - **Accuracy:** Bare History Truncation = **1 / 5 (20.0%)** vs. Lucca Compound Memory Pipeline = **4 / 5 (80.0%)** (**+60.0 pp net lift**).
     - **Discordant Pairs:** $b = 0, c = 3$ (zero regressions, 3 net rescues).
     - **Recall@k:** 5 / 5 (100.0%) for compound pipeline.
     - **Latency:** Average hybrid retrieval latency = **9.8 ms** (comfortably within the 15–40 ms budget; $\Delta\text{VRAM} = 0\,\text{MB}$).
- **Status:** Ratified & Enforced (`src/lucca/memory/retrieval.py`, `src/lucca/memory/store.py`, `src/lucca/ports.py`, `tests/test_temporal_retrieval.py`, `scripts/run_longmemeval_pipeline_benchmark.py`).

### D-COG-01 — Sovereign Cognitive Unification, Two-Cadence Inner Life & Constitutional Kernel (v1.46.5 / Work Order 36) *(ratified 2026-10-18)*
- **Context:** Prior to Work Order 36, CEGIS multi-turn synthesis engines (`PythonCEGISEngine`, `UnshackledCEGISEngine`), affective appraisal (`AffectiveODEMachine`), working memory proof traces (`ReasoningContext`), and case-based episode recall (`EpisodeRecall`) operated as loosely coupled components. Furthermore, `UserModel` and `EpisodeRecall` relied on lexical overlap without active goal biasing, and background reflection required a two-cadence homeostatic architecture (`IdlePulse` and `DreamRetrospective`) with zero real-time turn overhead.
- **Decision:**
  1. **Unified Cognitive Outcome Sink (`src/lucca/core/cognitive_sink.py`):** All CEGIS completion paths (`PythonCEGISEngine`, `UnshackledCEGISEngine`, `Orchestrator.synthesize_code_with_preflight`) route through `CognitiveOutcomeSink.record_cegis_outcome()`, signing an `ASSISTANT_ACTION` receipt via `create_tool_result_signer()`, appending `ProofTraceStep` records to `ReasoningContext.proof_trace()`, persisting 2+ turn repair episodes to `EpisodeRecall` and SQLite `execution_triples`, and emitting `EUREKA_DISCOVERY` / `TASK_SUCCESS` / `TOOL_FAILURE` into `AffectiveODEMachine` (evidential truth weight strictly `0.0`).
  2. **Semantic `UserModel` v2 & Goal-Biased Recall (`src/lucca/core/user_model.py`, `src/lucca/core/active_goals.py`):** Hybrid ModernBERT OpenVINO NLI entailment boosting (`> 0.60`), contradiction rejection, and 384-D dense cosine similarity, paired with `ActiveGoalManager` (`0009_active_goals_and_learning_events.sql`) wired into `HybridRetriever`, `EpisodeRecall`, and `Orchestrator`. Preserves Trap 1 and Trap 2 invariants.
  3. **Two-Cadence Inner Life (`src/lucca/memory/reflection.py`):** Homeostatic `CoherenceDrive` (Belnap $\top$ conflicts) and `CompetenceDrive` (CEGIS repairs) govern the 60s `IdlePulse` (wired to `VerifierWorker` NLI consistency, `quarantine_rejected_distillate`, and `distill_contradiction_to_proposition`) and `DreamRetrospective` (wired to `RuleInducer`, `RuleLifecycleManager`, and offline shadow replay into `QUARANTINE` per `D-REAS-06`).
  4. **Constitutional Kernel & Sovereign Sight (`src/lucca/core/constitutional.py`, `src/lucca/sandbox/screenshot_tool.py`):** Deterministic SHA-256 `constitutional_hash` bound to every `DecisionRecord`, verified epistemic TTS prosody modulation (`CHECKED_FORMALIZATION_AGREED` vs `SPECULATION`), and Windows 11 WinRT `Windows.Media.Ocr.OcrEngine` text extraction (`extract_ocr_from_image`).
  5. **Neurosymbolic Precision & Verification Spikes:** SymPy `.coeff()` auto-expansion AST rewrite, AIME combinatorics token ceiling (`max_tokens=1536`), `ContainerWorld` implicit room co-presence (`set_room_occupants`) and `tell()`, Organ A topological `GridDiff` + expanded spatial AST mutators, `config/grammars/zebra_constraints.gbnf` deterministic Edge Z3 compiler, `SPIKE-A` post-turn NLI receipt entailment in `coherence.py`, `SPIKE-B` `blind_classifier_only` routing mode in `HeuristicRouter`, and Tier 0 32K context (`ctx=32768`, `ngl=28`) + `/tmp/lucca_runtime` container sync persistence.
- **Status:** Ratified & Enforced (`src/lucca/core/cognitive_sink.py`, `src/lucca/core/active_goals.py`, `src/lucca/core/constitutional.py`, `src/lucca/memory/reflection.py`, `src/lucca/reasoning/cegis_unshackled.py`, `src/lucca/reasoning/smt_verifier.py`, `tests/test_cognitive_sink.py`, `tests/test_user_model_v2.py`, `tests/test_inner_life.py`, `tests/test_milestone_36_4.py`, `tests/test_milestone_36_5.py`).
