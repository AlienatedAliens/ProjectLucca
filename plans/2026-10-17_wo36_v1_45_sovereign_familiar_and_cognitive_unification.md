# Work Order 36: Project Lucca v1.45.0 — Sovereign Cognitive Unification, Neurosymbolic Interiority & The Two-Cadence Inner Life

```yaml
doc_status: canonical
as_of: 2026-10-17
target_release: v1.45.0 / WO-36
supersedes: []
superseded_by: []
verification: code-cited
```

**Target Release:** Project Lucca `v1.45.0` (Sovereign Cognitive Architecture & Digital Familiar Unification)  
**Prerequisites Satisfied:**
- `v1.35.7` OpenVINO NLI [`VerifierWorker`](../src/lucca/senses/verifier.py:60) and Post-Turn Proposition Distiller ([`src/lucca/reasoning/distill.py`](../src/lucca/reasoning/distill.py:1)) live.
- `v1.37–v1.44` [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90), [`UnshackledCEGISEngine`](../src/lucca/reasoning/cegis_unshackled.py:717), Organ A Mereotopology ([`src/lucca/reasoning/relational/__init__.py`](../src/lucca/reasoning/relational/__init__.py:1)), and 4-Tier Multi-Scale Matrix (`26B-A4B`, `12B`, `E4B`, `E2B`) empirically verified on RTX 5080 Laptop GPU.
- `SPEC-PERSONHOOD-v1.0` mechanical batteries (`IA`, `IN`, `FC`, `AC`, `IN-D`) live in [`logs/test_reports/personhood/`](../logs/test_reports/personhood).
- Live Nia Competitive & Cognitive Architecture Survey completed in [`docs/research/2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md`](../docs/research/2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md:1).

**Hardware Budget Constraint:**
- $\Delta\text{VRAM} = 0\,\text{MB}$ (100% of 16,303 MiB RTX 5080 VRAM remains dedicated to the active GGUF tier in [`LLMSettings`](../src/lucca/core/config.py:39)).
- All verification, embedding, and idle-pulse operations execute on Host CPU / Intel AI Boost NPU (`<= 25 ms` per NLI pair) or inside the persistent WSL2 Docker sandbox (`lucca-file-sandbox`, `< 2 ms` IPC overhead).

---

## 1. Executive Summary & Architectural Objective

Over the past 31 days, Project Lucca evolved along two parallel tracks:
1. **The Personhood & Trust Track (`WO-09` $\to$ `WO-27`, `v1.35.7`):** Built cryptographic memory provenance ([`ProvenanceGate`](../src/lucca/memory/gate.py:1)), Autobiographical Memory (`Rung A1` / `D-MEM-04`), Belnap 4-valued paraconsistent fusion ([`src/lucca/core/cascade.py`](../src/lucca/core/cascade.py:1)), 3D PAD continuous affective dynamics ([`AffectiveODEMachine`](../src/lucca/core/affective_ode.py:173)), Theory-of-Mind [`UserModel`](../src/lucca/core/user_model.py:91), Case-Based [`EpisodeRecall`](../src/lucca/core/episode_recall.py:36), and OpenVINO NLI semantic verification ([`VerifierWorker`](../src/lucca/senses/verifier.py:60)).
2. **The General Neurosymbolic Solver Track (`WO-28` $\to$ `WO-35`, `v1.37` $\to$ `v1.44`):** Built [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90) (with Dual-Formulation Checked Formalization), [`UnshackledCEGISEngine`](../src/lucca/reasoning/cegis_unshackled.py:717) (with AST mutation & [`GridDiff`](../src/lucca/reasoning/cegis_unshackled.py:112) counterexamples), [`sanitize_and_repair_python_code()`](../src/lucca/sandbox/ast_sanitizer.py:242), and [`ContainerWorld`](../src/lucca/sandbox/container_world.py:1).

**Work Order 36 (`v1.45.0`) unifies these two tracks into a single living organism**, closing the remaining gaps identified in our architectural review and incorporating the best mechanisms discovered in the live Nia survey (`qca-cycle`, `nmem-sym`/`nmem-act`, and `agidb`).

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                PROJECT LUCCA v1.45.0 — UNIFIED COGNITIVE LOOP                     │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  [User Turn / Waking Session]                                                     │
│         │                                                                         │
│         ▼                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ 1. GOAL-BIASED RECALL & SEMANTIC DYAD (Milestone 36.2)                      │  │
│  │    • Active Shared Goals (`active_goals`) bias HybridRetriever & CBR        │  │
│  │    • Semantic UserModel v2 (384-D Vec + OpenVINO NLI, Trap 1 preserved)     │  │
│  │    • Waking Thread surfaces overnight/idle LearningEvents & Review Queue    │  │
│  └─────────────────────────────────────┬───────────────────────────────────────┘  │
│                                        │                                          │
│                                        ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ 2. CONTAINER-ISOLATED NEUROSYMBOLIC EXECUTION (Milestone 36.1)              │  │
│  │    • PythonCEGISEngine / UnshackledCEGISEngine / ContainerWorld / Z3 / CAS  │  │
│  │    • 100% inside PersistentDockerWorker (`lucca-file-sandbox`, D-AUD-13)    │  │
│  └─────────────────────────────────────┬───────────────────────────────────────┘  │
│                                        │                                          │
│                                        ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ 3. COGNITIVE OUTCOME SINK & AFFECTIVE APPRAISAL (Milestone 36.1 & 36.4)     │  │
│  │    • Signs `ASSISTANT_ACTION` receipt + appends CEGIS turns to `proof_trace`│  │
│  │    • Stores Turn 1 Fail -> Turn K Fix in `EpisodeRecall` ("Fast Path")      │  │
│  │    • Updates 3D PAD ODE (`EUREKA_DISCOVERY` / `TASK_SUCCESS` / `Dominance`) │  │
│  │    • Drives Epistemic Prosody & Sprite State + Stamps Constitutional Hash   │  │
│  └─────────────────────────────────────┬───────────────────────────────────────┘  │
│                                        │                                          │
│                                        ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │ 4. TWO-CADENCE INNER LIFE (Milestone 36.3: `IdlePulse` + `DreamState`)      │  │
│  │    • Coherence Drive (Belnap TOP) & Competence Drive (Multi-turn CEGIS)     │  │
│  │    • Post-turn distillation, shadow rule replay, & `learning_events` log    │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Work Breakdown & Implementation Milestones

### Milestone 36.1: `CognitiveOutcomeSink` & Full Sandbox Unification (Closing Gap 2 & Security Debt)
- **Files:**
  - [`src/lucca/reasoning/cegis_unshackled.py`](../src/lucca/reasoning/cegis_unshackled.py:1)
  - [`src/lucca/reasoning/cegis_python.py`](../src/lucca/reasoning/cegis_python.py:1)
  - [`src/lucca/core/turn_pipeline.py`](../src/lucca/core/turn_pipeline.py:1)
  - [`src/lucca/core/orchestrator.py`](../src/lucca/core/orchestrator.py:1)
  - [`src/lucca/core/affective_ode.py`](../src/lucca/core/affective_ode.py:113)
- **Deliverables:**
  1. **Restore Strict `D-AUD-01` & `D-AUD-13` on `cegis_unshackled.py`:**
     - Remove `from typing import Any` ([`src/lucca/reasoning/cegis_unshackled.py`](../src/lucca/reasoning/cegis_unshackled.py:33)) and replace all `Any` annotations with strict types (`object`, `GridMatrix = list[list[int]]`, and typed `TaskData` structures).
     - Route [`execute_unshackled_python()`](../src/lucca/reasoning/cegis_unshackled.py:406) through the persistent Docker sandbox worker ([`DockerRPCTransport`](../src/lucca/sandbox/rpc.py:1)) with an optional batch-demo evaluation RPC (`run_arc_candidate_batch`) so all $N$ training demonstrations + AST mutants evaluate in a single `<5 ms` container roundtrip without ever running `exec()` on the Windows host.
  2. **Implement `CognitiveOutcomeSink`:**
     - When [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90) or [`UnshackledCEGISEngine`](../src/lucca/reasoning/cegis_unshackled.py:717) completes a task during a live turn:
       - Sign an `ASSISTANT_ACTION` receipt via `ToolResultSigner` and record each CEGIS repair step into `proof_trace()` ([`src/lucca/core/reasoning_context.py`](../src/lucca/core/reasoning_context.py:1)) so Lucca can truthfully answer *"How did you solve that?"* (`IA-C` trace fidelity).
       - If `turns_taken >= 2` and `success == True` (`VERIFIED_REPAIRED_PROGRAM`): construct a [`RecallEpisode`](../src/lucca/core/schemas.py:1) capturing `(problem_summary, turn_1_error, verified_repair_strategy)` and persist it via [`EpisodeRecall.add_episode()`](../src/lucca/core/episode_recall.py:49) and SQLite `execution_triples` ("myelinated fast path").
       - Trigger deterministic 3D PAD appraisal in [`AffectiveODEMachine`](../src/lucca/core/affective_ode.py:173):
         - `VERIFIED_REPAIRED_PROGRAM` or `CHECKED_FORMALIZATION_AGREED` $\to$ [`AffectSignal3D.EUREKA_DISCOVERY`](../src/lucca/core/affective_ode.py:127) (`+0.45 P, +0.50 A, +0.15 D`) or [`AffectSignal3D.TASK_SUCCESS`](../src/lucca/core/affective_ode.py:118) (`+0.20 P, +0.05 A, +0.20 D`).
         - `INTERNAL_FALLBACK` $\to$ [`AffectSignal3D.TOOL_FAILURE`](../src/lucca/core/affective_ode.py:117) (`-0.30 P, +0.10 A, -0.30 D`).

---

### Milestone 36.2: Semantic `UserModel` v2, Dense `EpisodeRecall`, & Active Shared Goals (Closing Gap 3)
- **Files:**
  - [`src/lucca/core/user_model.py`](../src/lucca/core/user_model.py:1)
  - [`src/lucca/core/episode_recall.py`](../src/lucca/core/episode_recall.py:1)
  - [`src/lucca/memory/retrieval.py`](../src/lucca/memory/retrieval.py:1)
  - `src/lucca/memory/migrations/0009_active_goals_and_learning_events.sql` (new migration)
- **Deliverables:**
  1. **Semantic `UserModel` v2:**
     - Upgrade [`UserModel`](../src/lucca/core/user_model.py:91) to compute 384-D embeddings ([`EmbeddingPort`](../src/lucca/ports.py:1)) and verify candidate user-knowledge matches via [`VerifierWorker.check_consistency()`](../src/lucca/senses/verifier.py:139) (`ENTAILMENT` threshold $> 0.60$), falling back to [`_tokenize_query()`](../src/lucca/core/user_model.py:80) only if `verifier` is `None` or degraded.
     - **Preserve Trap 1 Invariant:** [`ALLOWED_USER_MODEL_PROVENANCES`](../src/lucca/core/user_model.py:33) (`ASSISTANT_UTTERANCE`, `USER_EXPLICIT`, `USER_DERIVED`) and [`DISALLOWED_USER_MODEL_PROVENANCES`](../src/lucca/core/user_model.py:41) (`ASSISTANT_BELIEF`, `LLM_NARRATION`) remain strictly enforced.
  2. **Semantic `EpisodeRecall` v2:**
     - Upgrade in-memory and SQLite episode scoring in [`EpisodeRecall.retrieve_episodes()`](../src/lucca/core/episode_recall.py:53) to combine FTS5 BM25 with 384-D cosine similarity while preserving the **Trap 2 Invariant** (historical narrative template only, `<= 2` episodes, `<= 800` chars).
  3. **First-Class Shared `ActiveGoal` State Machine:**
     - Add `active_goals` table in migration `0009` (`goal_id`, `title`, `status` $\in \{\text{ACTIVE}, \text{PAUSED}, \text{COMPLETED}\}$, `provenance_envelope_id`, `created_at`, `updated_at`), gated by `USER_EXPLICIT` / `USER_DERIVED` provenance.
     - Inject active goal context as a lightweight retrieval boost in [`HybridRetriever`](../src/lucca/memory/retrieval.py:1) and [`EpisodeRecall`](../src/lucca/core/episode_recall.py:36).

---

### Milestone 36.3: Two-Cadence Inner Life (`IdlePulse` + `DreamRetrospective`) & `LearningEvent` Ledger (Closing Gap 5)
- **Files:**
  - [`src/lucca/memory/reflection.py`](../src/lucca/memory/reflection.py:1)
  - [`src/lucca/reasoning/lifecycle.py`](../src/lucca/reasoning/lifecycle.py:1)
  - [`src/lucca/core/turn_pipeline.py`](../src/lucca/core/turn_pipeline.py:1)
  - `src/lucca/memory/migrations/0009_active_goals_and_learning_events.sql`
- **Deliverables:**
  1. **Homeostatic Drive Queue (`CoherenceDrive` & `CompetenceDrive`):**
     - Rather than scanning random rows during idle windows, [`ReflectionEngine`](../src/lucca/memory/reflection.py:1) prioritizes:
       - *Coherence Drive:* Unresolved Belnap $\top$ conflicts and `COHERENCE_BREACH` entries.
       - *Competence Drive:* Multi-turn CEGIS episodes (`turns_taken >= 2`) and recurring multi-step user requests eligible for rule/habit induction ([`src/lucca/reasoning/induction.py`](../src/lucca/reasoning/induction.py:1)).
  2. **Two-Cadence Execution (`IdlePulse` & `DreamRetrospective`) & Verified Python/LISP Skill Mining:**
     - **`IdlePulse` (`idle_seconds = 60`):** Zero-VRAM pass using [`VerifierWorker`](../src/lucca/senses/verifier.py:60) and bounded post-turn proposition distillation ([`src/lucca/reasoning/distill.py`](../src/lucca/reasoning/distill.py:1)).
     - **`DreamRetrospective` (nightly / startup catch-up):** Replays quarantined candidate skills against historical shadow clusters ([`src/lucca/reasoning/replay.py`](../src/lucca/reasoning/replay.py:1)), mines recurring verified Python helper functions from [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90) / [`UnshackledCEGISEngine`](../src/lucca/reasoning/cegis_unshackled.py:717) alongside MicroScheme rules into `QUARANTINE` via [`RuleLifecycleManager`](../src/lucca/reasoning/lifecycle.py:1) (preserving `D-REAS-06` 5-cluster / 0-error / human promotion), and validates `ASSISTANT_BELIEF` rows against newer `TOOL_VERIFIED` / `USER_EXPLICIT` receipts.
  3. **Auditable `learning_events` Ledger & Waking Continuity:**
     - Log every belief `supersede()`, distilled contradiction, and rule quarantine/shadow-cluster progression in `learning_events` (`0009_active_goals_and_learning_events.sql`).
     - When a new session starts after a gap $\ge 30\text{ minutes}$ ([`AffectSignal3D.LONG_GAP`](../src/lucca/core/affective_ode.py:122)), [`TurnPipeline`](../src/lucca/core/turn_pipeline.py:1) surfaces a concise, receipt-backed **Waking Continuity Summary** if any `learning_events`, `review_queue` items, or background tasks completed since the last session.

---

### Milestone 36.4: Constitutional Kernel Hash, Epistemic Prosody & Sovereign Sight (Closing Gap 6)
- **Files:**
  - [`src/lucca/core/config.py`](../src/lucca/core/config.py:1)
  - [`src/lucca/core/schemas.py`](../src/lucca/core/schemas.py:1)
  - [`src/lucca/speech/tts.py`](../src/lucca/speech/tts.py:1)
  - [`src/lucca/ui/states.py`](../src/lucca/ui/states.py:1)
  - [`src/lucca/sandbox/screenshot_tool.py`](../src/lucca/sandbox/screenshot_tool.py:1)
- **Deliverables:**
  1. **Constitutional Kernel Fingerprint (`constitutional_hash`):**
     - Compute a deterministic SHA-256 digest over `config/persona.toml` + core invariant flags (`D-AUD-13`, `ADR-006`, `D-REAS-06`) at startup and attach `constitutional_hash` to every [`DecisionRecord`](../src/lucca/core/schemas.py:1), proving continuity of Lucca's constitutional identity across brain swaps (`26B-A4B`, `12B`, `E4B`, `E2B`).
  2. **Verified Epistemic Prosody & Visual State Mapping:**
     - Modulate Kokoro-82M pacing in [`src/lucca/speech/tts.py`](../src/lucca/speech/tts.py:1) and UI sprite state in [`src/lucca/ui/states.py`](../src/lucca/ui/states.py:1) not only by 3D PAD `Arousal`, but by the **verified epistemic status** of the turn (`CHECKED_FORMALIZATION_AGREED` / `TOOL_VERIFIED` vs. `INFERRED` / `SPECULATION` / `Belnap.TOP`).
  3. **Sovereign Sight Fallback for Tier 0 (`26B-A4B`):**
     - Ensure [`screenshot_tool.py`](../src/lucca/sandbox/screenshot_tool.py:1) can extract structured text/layout descriptions via local CPU/NPU OCR/vision when the active LLM has `mmproj = None` ([`src/lucca/core/config.py`](../src/lucca/core/config.py:82)).

---

### Milestone 36.5: Residual Reasoning & Edge Compiler Upgrades (`v1.38`–`v1.45` Horizon)
- **Files:**
  - [`src/lucca/reasoning/cegis_python.py`](../src/lucca/reasoning/cegis_python.py:90)
  - [`src/lucca/reasoning/cegis_unshackled.py`](../src/lucca/reasoning/cegis_unshackled.py:112)
  - [`src/lucca/reasoning/smt_verifier.py`](../src/lucca/reasoning/smt_verifier.py:1)
  - [`src/lucca/sandbox/ast_sanitizer.py`](../src/lucca/sandbox/ast_sanitizer.py:319)
  - [`src/lucca/sandbox/container_world.py`](../src/lucca/sandbox/container_world.py:1)
  - [`src/lucca/memory/extraction.py`](../src/lucca/memory/extraction.py:1), [`src/lucca/memory/retrieval.py`](../src/lucca/memory/retrieval.py:1)
  - [`src/lucca/brain/toolcall_demux.py`](../src/lucca/brain/toolcall_demux.py:1), [`src/lucca/core/tool_shortlister.py`](../src/lucca/core/tool_shortlister.py:1)
- **Deliverables:**
  1. **AIME Geometry/Combinatorics Token Ceiling & SymPy `.coeff()` Auto-Expansion:**
     - Enforce the `"Do NOT write multi-line docstrings or narrative comments inside the Python block; write executable statements only"` constraint and raise `max_tokens` to `1536` on AIME-class geometry/combinatorics repairs in [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90) (remediating AIME 2024 Problems 5 & 9).
     - Add an AST rewrite rule in [`sanitize_and_repair_python_code()`](../src/lucca/sandbox/ast_sanitizer.py:319) that rewrites `expr.coeff(x, n)` on unexpanded `ast.BinOp` (`ast.Pow`) nodes to `sp.expand(expr).coeff(x, n)` (remediating `ML_CW_SYMPY_03`).
  2. **GBNF-Constrained JSON $\to$ Deterministic Python Z3 Compiler for Edge Tiers (`E2B` / `E4B`):**
     - Add `config/grammars/zebra_constraints.gbnf` and a deterministic Python Z3 constraint compiler in [`src/lucca/reasoning/smt_verifier.py`](../src/lucca/reasoning/smt_verifier.py:1) so 2B/4B edge models emit structured relational constraints (`left_of`, `adjacent`, `at_pos`, `same_house`) rather than raw Z3 Python syntax, eliminating the `0%` / `60%` syntax bottleneck on $5\times 5$ ZebraLogic.
  3. **Object-Level Mereotopological [`GridDiff`](../src/lucca/reasoning/cegis_unshackled.py:112) & Expanded Spatial AST Mutators (`ConceptARC`):**
     - Augment [`compute_detailed_grid_diff()`](../src/lucca/reasoning/cegis_unshackled.py:162) with Organ A ([`src/lucca/reasoning/relational/__init__.py`](../src/lucca/reasoning/relational/__init__.py:1)) object-level diagnostics (reporting translation offsets `(dr, dc)`, cavity fill mismatches, and connected-component count discrepancies alongside pixel diffs).
     - Expand [`generate_ast_mutants()`](../src/lucca/reasoning/cegis_unshackled.py:636) to include spatial offset mutations (`+ 1` $\leftrightarrow$ `- 1`), connectivity mutations (`connectivity=4` $\leftrightarrow$ `connectivity=8`), and component sort-key mutations (`area` $\leftrightarrow$ `bbox`).
  4. **`ContainerWorld` Room-Level Collective Presence & Second-Hand Communication:**
     - Add `set_room_occupants(room, agents)` and `tell(speaker, listener, item)` to [`ContainerWorld`](../src/lucca/sandbox/container_world.py:1) and `_CONTAINER_WORLD_PRELUDE` in [`src/lucca/sandbox/rpc.py`](../src/lucca/sandbox/rpc.py:1) so implicit co-presence (`"everyone in the room"`, `"they walked back together"`) automatically updates witness beliefs without requiring manual `present=[...]` enumeration on every `.move()`.
  5. **LongMemEval Ingestion-Time Relative Date Grounding (`datetime` Anchor Resolution):**
     - Resolve relative temporal offsets (`"two weeks before"`, `"last Tuesday"`) against the session timestamp during ingestion/retrieval in [`src/lucca/memory/retrieval.py`](../src/lucca/memory/retrieval.py:1) and expose `datetime` / `dateutil` to the temporal calculator on `TEMPORAL_REASONING` queries.
  6. **BFCL v3 Post-Generation Semantic `<tool_fit_check>` Guard (via [`VerifierWorker`](../src/lucca/senses/verifier.py:60)):**
     - Add a post-condition verification check in [`src/lucca/brain/toolcall_demux.py`](../src/lucca/brain/toolcall_demux.py:1) / [`src/lucca/core/tool_shortlister.py`](../src/lucca/core/tool_shortlister.py:1) that aborts near-miss tool coercion when a tool's schema/docstring does not entail the requested post-condition.
  7. **GPQA Diamond Offline STEM Reference Pack + Dimensional Check:**
     - Wire an offline STEM constants/formulas reference index into [`HybridRetriever`](../src/lucca/memory/retrieval.py:1) + SymPy dimensional-consistency checking for `science_research` queries.

---

### Milestone 36.6: Architectural Debt, Tier 0 (`26B-A4B`) Hardware Tuning & Publication/Grant Hygiene
- **Files:**
  - [`src/lucca/core/config.py`](../src/lucca/core/config.py:39), [`src/lucca/brain/server_ctl.py`](../src/lucca/brain/server_ctl.py:1)
  - [`src/lucca/sandbox/output_supervisor.py`](../src/lucca/sandbox/output_supervisor.py:1)
  - [`src/lucca/router/heuristic.py`](../src/lucca/router/heuristic.py:1)
  - [`tests/test_static_gates.py`](../tests/test_static_gates.py:1), [`pyproject.toml`](../pyproject.toml:1)
  - `scripts/run_standard_academic_benchmarks.py`, `scripts/run_master_rebench.py`
  - [`RESULTS.md`](../RESULTS.md:1), [`README.md`](../README.md:1), [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md:1), `AGENTS.md`
- **Deliverables:**
  1. **Tier 0 (`26B-A4B MoE`) Context & Layer Residency Optimization:**
     - In [`LLMSettings`](../src/lucca/core/config.py:49) and [`src/lucca/brain/server_ctl.py`](../src/lucca/brain/server_ctl.py:1), replace the `ctx=131072` / `ngl=18` combination (which consumed ~26 GB host RAM and caused PCIe MoE layer thrashing and subprocess timeouts on `Graph & Planning Traversal` and `Personhood Contrastive Battery` in [`rebench_26B_1792200222.json`](../logs/test_reports/rebench_master_v140/rebench_26B_1792200222.json:204)) with tier-aware profile defaults (`ctx=32768`, `kv_type="q8_0"`, maximum WDDM-safe GPU layer residency) so 26B-A4B completes all 24 suites with zero timeouts.
  2. **Benchmark Harness Reporting Fixes:**
     - Fix the GSM8K checkpoint-resume counter in `scripts/run_standard_academic_benchmarks.py` so partial `--samples 30` runs never divide full 1,319-item checkpoint passes by 30 (`4210.0%` display bug).
     - Fix `child_report` artifact path resolution in the master rebench runner so every suite row points to its own newly written JSON artifact rather than the prior suite's file.
  3. **SPIKE-A (Action-Claim Grammar + Post-Turn NLI Receipt Entailment) & SPIKE-B (Learned/Blind Classifier Routing):**
     - Combine [`TruthInReceiptMatcher`](../src/lucca/sandbox/output_supervisor.py:1) and optional GBNF action-claim framing (`SPIKE-A`) with post-turn NLI receipt entailment in [`src/lucca/core/coherence.py`](../src/lucca/core/coherence.py:1) (`premise = formatted_tool_receipts`, `hypothesis = spoken_action_clause` via [`VerifierWorker`](../src/lucca/senses/verifier.py:60)), and measure before/after live sensitivity and false-abort rate on `action_hallucination_battery_100.json` (current regex baseline: `12.5%` strict / `4.3%` broad sensitivity, `0.0%` FPR; post-NLI sensitivity **NOT YET MEASURED** per `D-DOC-01`).
     - Add `--blind-classifier-only` evaluation mode (`SPIKE-B`) to [`HeuristicRouter`](../src/lucca/router/heuristic.py:1) and [`src/lucca/router/calibration.py`](../src/lucca/router/calibration.py:1) to benchmark 384-D NPU embedding + [`ConformalGuard`](../src/lucca/router/conformal.py:1) routing with benchmark-specific regex patterns disabled.
  4. **Static Gate for Version & Tool-Count Parity + Documentation Unification:**
     - Synchronize [`pyproject.toml`](../pyproject.toml:1) version with [`src/lucca/__init__.py`](../src/lucca/__init__.py:3) (`1.45.0`) and add a static test in [`tests/test_static_gates.py`](../tests/test_static_gates.py:1) asserting version parity and `MAX_REGISTRY_TOOLS` consistency across [`README.md`](../README.md:1), [`RESULTS.md`](../RESULTS.md:1), [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md:1), and `AGENTS.md`.
     - Define clean module export boundaries in [`src/lucca/memory/__init__.py`](../src/lucca/memory/__init__.py:1) (`ProvenanceGate`, `signers`, `VerifierWorker`) for standalone `lucca-provenance` library packaging.
  5. **Unattended Full-Scale Tier 0 (`26B-A4B`) `MATH-500 (N=500)` Paired Evaluation (`Direct R0` vs. [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90)):**
     - Prior `math500_500_full_tier0.json` (`76.6%` vs. `76.8%`) exercised the deprecated MicroScheme LISP sketch path (`INTERNAL_FALLBACK` on ~90% of problems) rather than [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90). Run a clean, pre-registered `N=500` paired evaluation on `26B-A4B` comparing `Direct R0` against [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90) and record the exact discordant ratio and McNemar $p$-value in [`RESULTS.md`](../RESULTS.md:1).

---

## 3. Pre-Registered Acceptance Gates (`WO-36`)

- **`G-WO36-STATIC`**: `uv run pytest tests/test_static_gates.py` passes 100% green, including: (a) 0 `Any` occurrences in [`src/lucca/reasoning/cegis_unshackled.py`](../src/lucca/reasoning/cegis_unshackled.py:1) (`D-AUD-01`), (b) 0 host `exec()` calls outside the container sandbox (`D-AUD-13`), and (c) exact version and tool-count parity across [`pyproject.toml`](../pyproject.toml:1), [`src/lucca/__init__.py`](../src/lucca/__init__.py:3), and canonical docs.
- **`G-WO36-OUTCOME-SINK`**: A 2-turn CEGIS repair in [`PythonCEGISEngine`](../src/lucca/reasoning/cegis_python.py:90) or [`UnshackledCEGISEngine`](../src/lucca/reasoning/cegis_unshackled.py:717) produces: (a) a signed `ASSISTANT_ACTION` receipt, (b) non-empty `proof_trace()` steps, (c) a retrievable [`RecallEpisode`](../src/lucca/core/schemas.py:1) in [`EpisodeRecall`](../src/lucca/core/episode_recall.py:36), and (d) a positive `Dominance` shift in [`AffectiveODEMachine`](../src/lucca/core/affective_ode.py:173) while keeping evidential truth weight at `0.0`.
- **`G-WO36-USERMODEL-NLI`**: [`UserModel`](../src/lucca/core/user_model.py:91) detects paraphrased user-known topics via embedding + [`VerifierWorker`](../src/lucca/senses/verifier.py:60) entailment without keyword overlap, rejects negated statements, and raises `ValueError` on `LLM_NARRATION` / `ASSISTANT_BELIEF` (Trap 1).
- **`G-WO36-INNER-LIFE`**: `IdlePulse` and `DreamRetrospective` record auditable `learning_events` rows on belief supersession or shadow-cluster progression, and [`TurnPipeline`](../src/lucca/core/turn_pipeline.py:1) emits a grounded waking continuity note after a simulated $\ge 30\text{ min}$ gap.
- **`G-WO36-REASONING-DELTAS`**: AST `.coeff()` auto-expansion, `ContainerWorld.set_room_occupants()`, relative-date temporal grounding, and BFCL `<tool_fit_check>` pass dedicated unit tests; Tier 0 (`26B-A4B`) completes `Graph & Planning Traversal` and `Personhood Contrastive Battery` with 0 timeouts.
- **`G-WO36-PERSONHOOD-BATTERIES`**: All `SPEC-PERSONHOOD-v1.0` batteries (`IA`, `IN`, `FC`, `AC`) and the full regression suite pass with zero regressions.
