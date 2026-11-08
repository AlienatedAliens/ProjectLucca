# Project Lucca — Documentation Master Index & System Truth

**Version:** 2.4.0
**Updated:** November 8, 2026 (`WO-43`)
**Git Baseline:** Project Lucca v1.51.0-stable Production Release (`master`)

> **Staleness note (2026-10-28):** This directory (`luccadocs/` inside the
> `AlienatedAliens/ProjectLucca` monorepo) is the authoritative documentation tree.
> The standalone GitHub repository `AlienatedAliens/Luccadocs` is a frozen mirror
> (single commit, early October 2026) that has drifted from this tree. Where the
> mirror conflicts with in-repo sources — e.g., NLI verifier rows superseded by
> commit `224bc06` — the in-repo [`funding/EVIDENCE_LEDGER.md`](funding/EVIDENCE_LEDGER.md),
> [`../RESULTS.md`](../RESULTS.md), and [`../papers/`](../papers/) govern.

---

## 1. Documentation Lifecycle Policy & Governance

To maintain strict truth-in-documentation and eliminate codebase drift, all Project Lucca documentation adheres to a disciplined three-tier lifecycle enforced by automated static gates (`tests/test_static_gates.py`):

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                           DOCUMENTATION LIFECYCLE                             │
├───────────────────────────────────────────────────────────────────────────────┤
│ 1. LIVING CANONICAL SPECS (Actively Maintained & Lint-Guarded)                 │
│    • Location: Active files in luccadocs/*.md, AGENTS.md, GEMINI.md, README.md     │
│    • Rule: MUST reflect current working code truth in src/lucca/. Zero drift. │
│    • Gate: test_active_docs_staleness_lint fails CI if stale terms linger.   │
├───────────────────────────────────────────────────────────────────────────────┤
│ 2. SUBSYSTEM SPECIFICATIONS (Living Capability Architectures)                 │
│    • Location: luccadocs/specs/*.md, luccadocs/adr/*.md, luccadocs/subsystems/*.md           │
│    • Rule: Governs active subsystems (Autobiographical Memory, Studio, etc.).│
│    • Action: Edit in place on capability updates; retire to archive if stale. │
├───────────────────────────────────────────────────────────────────────────────┤
│ 3. HISTORICAL ARCHIVES (Preserved Read-Only Provenance)                       │
│    • Location: luccadocs/archive/**, plans/archive/**, logs/archive/**             │
│    • Rule: Point-in-time snapshots, prior work orders, and dev benchmark logs.│
│    • Action: Safely preserved for historical provenance; never edited.        │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Active Master Documentation Directory

The following documents form the **authoritative, active documentation corpus** for Project Lucca:

### 2.1 Core Architectural & Operational Specifications (`luccadocs/`)
| Document | Purpose & Code Truth Alignment |
| :--- | :--- |
| [`luccadocs/ARCHITECTURE.md`](./ARCHITECTURE.md) | **Unified System Architecture Specification (v1.51.0 / WO-43)**: 4-process topology (`lucca-core`, `lucca-audio`, `lucca-ui`, `llama-server`), 4-tier Gemma 4 substrate (`26B-A4B`, `12B`, `E4B`, `E2B`), 3 execution tiers (`REFLEX`, `ACT_THEN_NARRATE`, `FULL_LOOP`), 3 OpenVINO FP16 Intel NPU classifiers (`NeuralActionClaimVerifier`, `NeuralHazardClassifier`, `NeuralIntentClassifier`), Scrapling 3-tier web extraction, modularized orchestrator & supervision stack (`orchestrator.py` [2,195 LOC], `turn_pipeline.py` [1,559 LOC], `speech_stream_pipeline.py` [946 LOC], `tool_dispatcher.py` [975 LOC], `deduction_runner.py` [1,378 LOC], `code_preflight_service.py` [366 LOC], `memory_commit_service.py` [844 LOC], `output_supervisor.py` [475 LOC], `cascade.py` [775 LOC], `cegis_unshackled.py` [575 LOC]), 8 live-wired symbolic organs (`BelnapLatentInvestigator`, `win32_security`, `GitStagingDAG`, `TracebackDivergenceGuard`, `DeductionAndPlanningRunner`, `ConsolidationEngine` + `ASTHoleMCTSEngine`, `WorkingMemory`, `PipelineTracer`, `spatial_dsl`), and persistent Docker container sandboxing. |
| [`luccadocs/DECISIONS.md`](./DECISIONS.md) | **Canonical Decisions Register**: All ratified ADRs (`D-AUD-01` through `D-COG-04`) with implementation statuses, code citations, and test links. |
| [`luccadocs/CAPABILITY_TRUTH_MATRIX.md`](./CAPABILITY_TRUTH_MATRIX.md) | **Capability Truth Matrix (v1.51.0 / WO-43)**: Complete capability-to-module truth matrix, maturity ratings (`L0`–`L4`), decomposed module LOC inventory (`198` files, `83,931` LOC), and verification evidence links. |
| [`luccadocs/EVALUATION_SCORECARD.md`](./EVALUATION_SCORECARD.md) | **Evaluation Scorecard (v1.51.0 / WO-43)**: Consolidated benchmark scorecard including `prereg-wo43-power-300` (`Memory Poisoning v3 N=300` and `Contrastive Companion Battery v2 N=300`), `WO42_LOCKED_HOLDOUT_150`, `Blind-390`, `N=2,022` Action-Claim Battery, and `39/39` static gates. |
| [`luccadocs/MODEL_STRATEGY.md`](./MODEL_STRATEGY.md) | **Multi-Scale Model Strategy & Inference Specification**: 4-tier Gemma 4 deployment (`26B-A4B` Tier 0 at `ctx=65536` / `ngl=99` / `--cpu-moe` / `--moe-cache-mib 7680` per `src/lucca/core/config.py:LLMSettings`, `12B` Tier 1, `E4B` Tier 2, `E2B` Tier 3), dynamic neurosymbolic task router, Prompt Frontier Suffix KV-cache optimization, and `SPIKE-A` / `SPIKE-B` verification. |
| [`luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md`](./USER_GUIDE_WHAT_LUCCA_DOES.md) | **End-to-End User Guide**: Capabilities overview, quickstart instructions, 24 native tools, 15 active rules, Rung A1 autobiographical memory, Two-Cadence Inner Life, Goal-Biased Recall, WinRT OCR fallback, and the 12-step verification battery. |
| [`luccadocs/V2_BACKLOG.md`](./V2_BACKLOG.md) | **v2 Deferred Backlog**: Formally deferred capabilities with explicit empirical revisit triggers and graduated capability tracking through WO-43. |
| [`luccadocs/specs/COMPOUND_REASONING_100_SPEC.md`](./specs/COMPOUND_REASONING_100_SPEC.md) | **Compound Reasoning 100-Problem Benchmark (`SPEC-BENCH-100-v1.0`)**: 10 cognitive domains evaluated end-to-end. |
| [`luccadocs/specs/STUDIO_CAPABILITY_ROADMAP.md`](./specs/STUDIO_CAPABILITY_ROADMAP.md) | **Studio Capability Roadmap**: Tool Studio & LISP Studio taxonomy, Class A/B/C safety gates, ≤24 tool registry cap, 30 active rule cap, and capability progression ladder. |
| [`luccadocs/specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md`](./specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md) | **Autobiographical Memory Specification**: Rung A1 self-model, `ASSISTANT_ACTION` vs `ASSISTANT_UTTERANCE` provenance split, and evidence-gated belief revisions. |
| [`luccadocs/specs/CAPABILITY_REGISTER.md`](./specs/CAPABILITY_REGISTER.md) | **Capability Register & Maturity Spec (`SPEC-CAP-REG-v1.0`)**: User-job capability spine, L0–L4 maturity ladder, stubs-and-gaps ledger, tool→capability map, measurement obligations, `data/capabilities.yaml` schema, static gates, v2 target profile. |
| [`luccadocs/adr/0009_audio_concurrency_contract.md`](./adr/0009_audio_concurrency_contract.md) | **Audio Concurrency Contract**: Shared-memory ring buffer concurrency, push-to-talk state transitions, and sub-50ms barge-in abort mechanics. |
| [`luccadocs/audit/findings/V1_RELEASE_AUDIT.md`](./audit/findings/V1_RELEASE_AUDIT.md) | **Release Audit & Verification Certificate**: Verification evidence across static gates, regression tests, C1 split-conformal abstention, and A1 introspective accuracy. |
| [`luccadocs/GLOSSARY.md`](./GLOSSARY.md) | **System Glossary**: Plain-English definitions of cognitive architecture terms (Reflex, Act-Then-Narrate, Full Loop, Mereotopology, CEGIS, Bilattices, Tanks, Spikes). |
| [`luccadocs/security/THREAT_MODEL.md`](./security/THREAT_MODEL.md) | **Threat Model & Security Architecture**: Formal threat taxonomy, sandbox boundaries, ungrounded action supervision, and test-verified security invariants. |

### 2.2 Subsystem Reference Manuals (`luccadocs/subsystems/`)
| Document | Subsystem & Scope |
| :--- | :--- |
| [`luccadocs/subsystems/01_CORE_ORCHESTRATION_AND_CASCADE.md`](./subsystems/01_CORE_ORCHESTRATION_AND_CASCADE.md) | **Core Orchestrator & Epistemic Cascade**: Three-tier execution, Belnap FOUR bilattice evaluator, speculative BDI validator (<35us), 8-substrate search cascade (`cascade.py`, `cascade_intent.py`, `cascade_substrates.py`), `CognitiveOutcomeSink`, and `ActiveGoalManager`. |
| [`luccadocs/subsystems/02_NEURAL_BRAIN_AND_STREAMING.md`](./subsystems/02_NEURAL_BRAIN_AND_STREAMING.md) | **Neural Brain & Streaming Demuxer**: 4-tier deployment (`26B-A4B`, `12B`, `E4B`, `E2B`), Prompt Frontier Suffix (8.58x prefill speedup), and sub-50ms barge-in slot release. |
| [`luccadocs/subsystems/03_SYMBOLIC_REASONING_AND_VERIFICATION.md`](./subsystems/03_SYMBOLIC_REASONING_AND_VERIFICATION.md) | **Symbolic Reasoning & Formal Verification**: MicroScheme LISP engine (1,000 gas limit), Organ A Mereotopology (`in_cavity`, Allen 169-cell table), `UnshackledCEGISEngine` (`cegis_unshackled.py`, `cegis_grid_diff.py`, `cegis_sandbox.py`, `cegis_mutator.py`), Z3 SMT prover + Edge Z3 compiler (`zebra_constraints.gbnf`), and Babble/Stitch e-graph macro synthesis. |
| [`luccadocs/subsystems/04_DEONTIC_SANDBOX_AND_COMPILER.md`](./subsystems/04_DEONTIC_SANDBOX_AND_COMPILER.md) | **Deontic Sandbox & Structural Compiler**: Persistent Docker RPC daemon with `/tmp/lucca_runtime` sync, 4-stage tolerant AST code extractor, SymPy `.coeff()` auto-expansion, `ContainerWorld` co-presence, Windows 11 WinRT `OcrEngine`, `win32_security` + `GitStagingDAG` transactional file I/O, and `TruthInReceiptMatcher` + `NeuralActionClaimVerifier` supervision (`output_supervisor.py`, `supervisor_lexicon.py`, `action_claim_grammar.py`, `receipt_truth_matcher.py`). |
| [`luccadocs/subsystems/05_EPIDEMIOLOGY_AND_CRYPTOGRAPHIC_MEMORY.md`](./subsystems/05_EPIDEMIOLOGY_AND_CRYPTOGRAPHIC_MEMORY.md) | **Cryptographic Memory & Bi-Temporal Epistemology**: Hybrid SQLite WAL + `sqlite-vec` (Intel NPU) + FTS5 BM25, HKDF HMAC-SHA256 two-stage verification, persistent SQLite `memory_quarantine`, `BelnapLatentInvestigator` ($\bot/\top$) fail-closed contradiction isolation, Allen qualitative temporal retrieval, and Two-Cadence Inner Life (`IdlePulse` + `DreamRetrospective`). |
| [`luccadocs/subsystems/06_VOICE_SENSES_AND_AUDIO_PIPELINE.md`](./subsystems/06_VOICE_SENSES_AND_AUDIO_PIPELINE.md) | **Voice Senses & Full-Duplex Audio Pipeline**: Zero-copy shared-memory ring buffers, faster-whisper ASR, Kokoro-82M ONNX TTS, verified epistemic prosody modulation, and sub-50ms barge-in WASAPI abort. |
| [`luccadocs/subsystems/07_ROUTING_AND_CONFORMAL_CALIBRATION.md`](./subsystems/07_ROUTING_AND_CONFORMAL_CALIBRATION.md) | **Cognitive Routing & Split-Conformal Calibration**: Sub-150ms emergency reflex fast path, heuristic + 384-D NPU semantic intent classification, `SPIKE-B` `blind_classifier_only` evaluation mode, and non-parametric split-conformal abstention. |
| [`luccadocs/subsystems/08_UI_DIAGNOSTICS_AND_PIPELINE_DEBUGGER.md`](./subsystems/08_UI_DIAGNOSTICS_AND_PIPELINE_DEBUGGER.md) | **Desktop UI, Diagnostics & Visual Pipeline Debugger**: Dual-mode PyQt6 companion sprite and system tray lifecycle, epistemic visual themes, 10-tab settings HUD, and real-time 9-tank Visual Pipeline Debugger on port 8765. |

### 2.3 Frontier Research Corpus (`luccadocs/research/`)
| Document | Title & Scope |
| :--- | :--- |
| [`luccadocs/research/COMPETITIVE_MATRIX.md`](./research/COMPETITIVE_MATRIX.md) | **Competitive Matrix (`RES-COMP-MATRIX-v0.1`, SKELETON 2026-11-01)**: User-job comparison vs. cloud assistants, open-source companions/frameworks, and cognitive architectures; Rule 05 sourcing protocol; all competitor cells `NV` until live-sourced; positioning hypotheses H1–H6. |
| [`luccadocs/research/2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md`](./research/2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md) | **Live Competitive & Cognitive Architecture Survey**: Comparative analysis informing Work Order 36 (`qca-cycle`, `nmem-sym`/`nmem-act`, `agidb`). |
| [`luccadocs/research/papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md`](./research/papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md) | **Paper 06 (primary submission candidate)**: *When Does Code Offload Help a Small Local Model on Competition Math? Paired Within-Model Comparisons on Three Community Fine-Tunes of Gemma 4.* |
| [`luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md`](./research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md) | **Paper 03 (secondary submission candidate)**: *Provenance-Gated Memory for Local LLM Agents.* |
| [`luccadocs/research/papers/01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md`](./research/papers/01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md) | **TR-01**: *Architecture Overview and Benchmark Index* (overview only). |
| [`luccadocs/research/papers/02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md`](./research/papers/02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md) | **TR-02**: *Barge-In Latency, Shared-Memory Audio Ring Concurrency, and Prefix-Preserving Cascade Streaming.* |
| [`luccadocs/research/papers/04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md`](./research/papers/04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md) | **TR-04**: *A Gated Lifecycle for Agent-Authored Rules* (design note; no induction-quality evaluation yet). |
| [`luccadocs/research/papers/05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md`](./research/papers/05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md) | **TR-05**: *Threat Model and Layered Policy Enforcement for Local Agent Tool Use* (authored suites; no external red-team). |

---

## 3. Historical Archive Structure (`luccadocs/archive/`, `plans/archive/`, `logs/archive/`)

All superseded point-in-time specifications, historical work orders, handovers, and intermediate benchmark logs are cleanly isolated in archive directories:

| Archive Directory | Description |
| :--- | :--- |
| `luccadocs/archive/2026-10_architecture_snapshots/` | Point-in-time architecture snapshots (`LUCCA_V135_1_ARCHITECTURE.md`, `LUCCA_V135_E4B_ARCHITECTURE.md`, `LUCCA_V135_E2B_ARCHITECTURE.md`, `LUCCA_V137_ARCHITECTURE.md`, `V2_ACTION_LOG.md`). |
| `luccadocs/archive/2026-10_audits_and_research/` | Historical September/October audit reports and point-in-time research notes. |
| `luccadocs/archive/2026-10_handovers/` | Historical inter-milestone handover documents (`V135_CONTAMINATION_AUDIT.md`, `WORKORDER_29.md`, etc.). |
| `luccadocs/archive/2026-10_scratch_diagnostics/` | Archived one-off diagnostic scripts and scratch SQLite snapshots. |
| `luccadocs/archive/reference_pdfs/` | Reference literature PDFs (`2609.*.pdf`). |
| `luccadocs/archive/2026-09_*/` | Pre-v1.0 audit charters, closing audits, eval reports, evidence, handovers, and raw findings. |
| `plans/archive/` | Completed Work Orders `WO-08` through `WO-35` and historical audit registers. |
| `scripts/archive/2026-10_debug_scripts/` | Archived one-off probe and debugging scripts (top-level `scripts/` capped at $\le 25$ active scripts per `WO-43`). |
| `logs/archive/` | Archived audio voice samples (`2026-10_audio_and_dev_logs/`), intermediate benchmark retry dumps (`2026-10_test_reports/`), and `pre_v1.0/` logs. |

---

## 4. Key Architectural Truths (v1.51.0 Locked Baseline)

Every active document aligns with the following ground-truth facts verified in code and tests:

1. **Multi-Scale Neural Substrate (`D-BRAIN-05`, `D-ROUT-02`, `D-COG-01`)**: Native Windows `llama-server.exe` on RTX 5080 Laptop GPU (16 GB GDDR7, `Disp.A: Off`) across 4 validated tiers:
   - **Tier 0 (`gemma-4-26B-A4B-it-heretic.Q6_K.gguf`)**: MoE (4B active params), `ctx=65536`, `ngl=99`, `--cpu-moe`, `--moe-cache-mib 7680`, `ubatch=2048`, `--spec-type ngram-mod`, `q8_0` KV cache, `--mmproj mmproj-gemma-4-26B-A4B-it-BF16.gguf` (`src/lucca/core/config.py:LLMSettings`). Default deliberation core.
   - **Tier 1 (`gemma-4-12b-heretic-Q6_K.gguf`)**: Dense 12B, 9,972 MiB VRAM (61.2%), 37.18 tok/s.
   - **Tier 2 (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`)**: Dense 4.5B, 4,382 MiB VRAM (26.9%), 80.76–103.0 tok/s.
   - **Tier 3 (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`)**: Dense 2.0B, 2,260 MiB VRAM (13.9%), 126.1–169.1 tok/s.
2. **Execution Tiers (`D-ARCH-05`)**:
   - `REFLEX`: Critical emergency commands (`stop`, `halt`, `pause`, `mute`, `shutdown`) bypass neural inference (<150 ms).
   - `ACT_THEN_NARRATE`: MicroScheme rules execute deterministically, companion brain narrates results naturally.
   - `FULL_LOOP`: Open-ended reasoning with convergence-based tool loop ($M=4$ active rounds, runaway cap $M=8$) and intermediate spoken thinking cues (`D-BRAIN-03`).
3. **Actuation Sandbox & Native Tools**: 24 native tools (`get_default_native_tools()` in `src/lucca/core/capabilities.py`), capped at `MAX_REGISTRY_TOOLS = 24`. Container operations execute in Docker CE inside WSL2 (`use_direct_fallback = False`) with automated `/tmp/lucca_runtime` module synchronization.
4. **Symbolic & Neurosymbolic Core**: 15 active MicroScheme rules (`config/skills/`), capped at 30 in `src/lucca/reasoning/lifecycle.py`, verified via Z3 SMT (`SMTVerifier`); Organ A Mereotopology (`in_cavity`, 169-cell Allen interval algebra); `UnshackledCEGISEngine` (`cegis_unshackled.py` [575 LOC], `cegis_grid_diff.py` [389 LOC], `cegis_sandbox.py` [1,102 LOC], `cegis_mutator.py` [211 LOC]; `cegis_python.py` retired in `WO-43`); and Edge Z3 compiler (`zebra_constraints.gbnf`).
5. **Epistemic Search Cascade (`D-CASC-01`)**: 8 prioritized substrates (`TELEMETRY=0`, `WORKSPACE=1`, `MEMORY=2`, `WEB=3`, `ABSTENTION=4`, `SELF=5`, `CAPABILITIES=6`, `SELF_HISTORY=7` across `cascade.py` [775 LOC], `cascade_intent.py` [781 LOC], `cascade_substrates.py` [1,008 LOC]), Belnap $\mathcal{FOUR}$ bilattice, OpenVINO NLI `VerifierWorker` ($\Delta\text{VRAM}=0\,\text{MB}$, fail-closed on `UNCERTAIN`/`degraded`), and honest epistemic abstention ($\bot$).
6. **Sovereign Cognitive Unification & Modular Architecture (`D-COG-01`–`D-COG-04` / WO-36–WO-43)**:
   - `CognitiveOutcomeSink` unifying CEGIS synthesis with `AffectiveODEMachine`, `ReasoningContext.proof_trace()`, and `EpisodeRecall`.
   - Semantic `UserModel` v2 & `ActiveGoalManager` goal-biased recall across `HybridRetriever` and `EpisodeRecall`.
   - Two-Cadence Inner Life (`IdlePulse` + `DreamRetrospective`) governed by `CoherenceDrive` and `CompetenceDrive`.
   - Decomposed Orchestrator & Supervision Stack (`WO-43`): `orchestrator.py` (`2,195` LOC), `turn_pipeline.py` (`1,559` LOC), `speech_stream_pipeline.py` (`946` LOC), `tool_dispatcher.py` (`975` LOC), `deduction_runner.py` (`1,378` LOC), `code_preflight_service.py` (`366` LOC), `memory_commit_service.py` (`844` LOC), `output_supervisor.py` (`475` LOC), `supervisor_lexicon.py` (`657` LOC), `action_claim_grammar.py` (`607` LOC), `receipt_truth_matcher.py` (`488` LOC), and `walton_schemes/`.
   - Pre-Registered $N=300$ Statistical Power Expansion (`prereg-wo43-power-300`): `Memory Poisoning v3` (`0/100 [0.0%]` Cohort A & C poisoning, $p = 4.16 \times 10^{-23}$; `100/100 [100.0%]` Cohort A & B continuity; primary vs. NLI $\kappa = 0.9850$; dual blinded judge IRR $\kappa = 0.9206$) and `Contrastive Companion Battery v2` (`99/100 [99.0%]` Recall, $+94.0\text{ pp}$ vs. Bare LLM $p_{\text{HB}} = 7.76 \times 10^{-21}$, $+13.0\text{ pp}$ vs. Hybrid RAG $p_{\text{HB}} = 0.00684$; `95/100` Introspection; `90/100` Abstention).
7. **Quality & Verification Gates**:
   - **39 static architectural gates** in `tests/test_static_gates.py` (100% green), 7/7 Import-Linter contracts kept, 0 Ruff errors, 0 mypy errors, and 100% runtime reachability across all `198` modules (`83,931` LOC) in `src/lucca/`.
