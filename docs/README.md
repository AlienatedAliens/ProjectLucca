# Project Lucca — Documentation Master Index & System Truth

**Version:** 2.0.0  
**Updated:** September 24, 2026  
**Git Baseline:** Project Lucca v1.0.0 Production Release (`master`)

---

## 1. Documentation Lifecycle Policy & Governance

To maintain strict truth-in-documentation and eliminate codebase drift, all Project Lucca documentation adheres to a disciplined lifecycle enforced by automated static gates (`tests/test_static_gates.py`):

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                           DOCUMENTATION LIFECYCLE                             │
├───────────────────────────────────────────────────────────────────────────────┤
│ 1. LIVING CANONICAL SPECS (Actively Maintained & Lint-Guarded)                 │
│    • Location: Active files in docs/*.md, AGENTS.md, GEMINI.md, README.md     │
│    • Rule: MUST reflect current working code truth in src/lucca/. Zero drift. │
│    • Gate: test_active_docs_staleness_lint fails CI if stale terms linger.   │
├───────────────────────────────────────────────────────────────────────────────┤
│ 2. SUBSYSTEM SPECIFICATIONS (Living Capability Architectures)                 │
│    • Location: docs/specs/*.md, docs/adr/*.md                                 │
│    • Rule: Governs active subsystems (Autobiographical Memory, Studio, etc.).│
│    • Action: Edit in place on capability updates; retire to archive if stale. │
├───────────────────────────────────────────────────────────────────────────────┤
│ 3. HISTORICAL ARCHIVES (Preserved Read-Only Provenance)                       │
│    • Location: docs/archive/**, logs/archive/**                               │
│    • Rule: Point-in-time exploratory drafts, early audits, pre-v1.0 specs.   │
│    • Action: Safely preserved for historical provenance; never edited.        │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Active Master Documentation Directory

The following documents form the **authoritative, active documentation corpus** for Project Lucca v1.0.0:

### 2.1 Core Architectural & Operational Specifications
| Document | Purpose & Code Truth Alignment |
| :--- | :--- |
| [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) | **Canonical Master Specification**: 4-process topology (`lucca-core`, `lucca-audio`, `lucca-ui`, `llama-server`), 3 execution tiers (`REFLEX`, `ACT_THEN_NARRATE`, `FULL_LOOP`), MicroScheme runtime, memory architecture, Docker container sandboxing, Kokoro audio pipeline, and canonical decisions verification table. |
| [`docs/DECISIONS.md`](./DECISIONS.md) | **Canonical Decisions Register**: All 27 ratified decisions (`D-AUD-01` through `D-META-01`) with implementation statuses, code citations, and test links. |
| [`docs/MODEL_STRATEGY.md`](./MODEL_STRATEGY.md) | **Model Strategy & Inference Specification**: Gemma-4-12B-Heretic Q6_K deployment on RTX 5080 Laptop GPU (12.5 GB resident VRAM clamp), Prompt Frontier Suffix KV-cache optimization ($8.58\times$ prefill speedup), and Dimension 7B output supervision. |
| [`docs/USER_GUIDE_WHAT_LUCCA_DOES.md`](./USER_GUIDE_WHAT_LUCCA_DOES.md) | **End-to-End User Guide**: Capabilities overview, quickstart instructions, 23 native tools, 15 active rules, Rung A1 autobiographical memory, honest abstention procedures, and the 12-step verification battery. |
| [`docs/specs/STUDIO_CAPABILITY_ROADMAP.md`](./specs/STUDIO_CAPABILITY_ROADMAP.md) | **Studio Capability Roadmap**: Tool Studio & LISP Studio taxonomy, Class A/B/C safety gates, ≤23 tool registry cap, 30 active rule cap, and the capability progression ladder. |
| [`docs/specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md`](./specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md) | **Autobiographical Memory Specification**: Recovered companion goals, Rung A1 self-model, `ASSISTANT_ACTION` vs `ASSISTANT_UTTERANCE` provenance split, and evidence-gated belief revisions. |
| [`docs/adr/0009_audio_concurrency_contract.md`](./adr/0009_audio_concurrency_contract.md) | **Audio Concurrency Contract**: Shared-memory ring buffer concurrency, push-to-talk state transitions, and sub-50ms barge-in abort mechanics. |

### 2.2 Operational Logs & Release Verification
| Document | Purpose |
| :--- | :--- |
| [`docs/V2_ACTION_LOG.md`](./V2_ACTION_LOG.md) | **v1.0 Action Log & Bug Tracker**: Consolidated catalog of all findings extracted from WO-8 through WO-15 audits, documenting 19 resolved items (8 BUG_V1, 6 DOC_DRIFT, 5 TEST_GAP) and 12 deferred items. |
| [`docs/V2_BACKLOG.md`](./V2_BACKLOG.md) | **v2 Deferred Backlog**: 12 formally deferred capabilities (DESIGN_DEBT) with explicit empirical revisit triggers (multi-user, screen perception, continuous open-mic, unprompted reflection). |
| [`docs/audit/findings/V1_RELEASE_AUDIT.md`](./audit/findings/V1_RELEASE_AUDIT.md) | **v1.0 Release Audit & WO-16 Deep Clean Certificate**: Verification evidence across all 12 static gates, 653 non-HW tests, C1 split-conformal abstention, and A1 autobiographical introspective accuracy. |

---

## 3. Historical Archive Structure (`docs/archive/`)

Historical drafts, pre-v1.0 work order dumps, and superseded specifications have been moved out of the active path into named archives to guarantee that all active documents reflect live code:

| Archive Directory | Description |
| :--- | :--- |
| `docs/archive/2026-09_audit_framework/` | WO-8 audit charters, finding templates, evidence index, baselines, and test gap analyses. |
| `docs/archive/2026-09_eval_reports/` | Historical evaluation runs (Comprehensive 100, Diagnostic v2, Live AI Verification). |
| `docs/archive/2026-09_evidence/` | Silicon benchmark and latency evidence runs (Brain Bakeoff, S1 Summary). |
| `docs/archive/2026-09_closing_audits/` | Work Orders 8, 11, 12, and 13 closing audits and research sub-reports. |
| `docs/archive/2026-09_milestone_specs/` | Superseded milestone plans, exploratory specs, audit remediation logs, and resolved tickets. |
| `docs/archive/2026-09_raw_findings/` | Raw audit dumps from early modules (`arch`, `brain`, `core`, `drift`, `mem`, `reas`, `rout`, `sbx`, `sens`, `test`, `ui`). |
| `docs/archive/2026-09_handovers/` | Inter-agent handover logs from earlier development milestones. |
| `logs/archive/pre_v1.0/` | Pre-v1.0 raw test logs and diagnostic outputs (71 log files preserved). |

---

## 4. Key Architectural Truths (v1.0.0 Locked Baseline)

Every active document aligns with the following ground-truth facts verified in code and tests:

1. **Neural Core (`D-BRAIN-05 v2`)**: Native Windows `llama-server.exe` running `gemma-4-12b-heretic-Q6_K.gguf` with stock llama.cpp (≥ b11026), `--jinja` embedded chat template, `enable_thinking=false` mandatory for companion tiers (thinking reserved for explicit deep reasoning), 16,384 context default, and $\le 12.5\text{ GB}$ (12,800 MB) resident VRAM clamp on RTX 5080 Laptop GPU.
2. **Execution Tiers (`D-ARCH-05`)**:
   - `REFLEX`: Critical emergency commands (`stop`, `halt`, `pause`, `mute`, `shutdown`) bypass neural inference (<150 ms).
   - `ACT_THEN_NARRATE`: MicroScheme rules execute deterministically, companion brain narrates results naturally.
   - `FULL_LOOP`: Open-ended reasoning with convergence-based tool loop (up to $M=4$ active rounds, runaway budget cap $M=8$ per WO-9 A5) and intermediate spoken thinking cues (`D-BRAIN-03`).
3. **Actuation Sandbox & Native Tools**: 23 native tools (`get_default_native_tools()` in `src/lucca/core/capabilities.py`), capped at `MAX_REGISTRY_TOOLS = 23`. Container operations execute in Docker CE inside WSL2 (`use_direct_fallback = False`).
4. **Symbolic Core & Skills**: 15 active MicroScheme rules (`config/skills/`), capped at 30 in `src/lucca/reasoning/lifecycle.py`. Statically validated and formally verified via Z3 SMT (`SMTVerifier`).
5. **Epistemic Search Cascade (`D-CASC-01`)**: 8 prioritized substrates (`TELEMETRY=0`, `WORKSPACE=1`, `MEMORY=2`, `REASONING=3`, `SENSES=4`, `SYSTEM=5`, `WEB_FLOOR=6`, `SELF_HISTORY=7` in `src/lucca/core/cascade.py:EpistemicSubstrate`), Belnap $\mathcal{FOUR}$ bilattice, honest epistemic abstention ($\bot$).
6. **Autobiographical Memory (`D-MEM-04` / Rung A1)**:
   - Tool receipts signed by `ToolResultSigner` as `ASSISTANT_ACTION` (`grounding_eligible = 1`).
   - Spoken utterances signed by `AssistantUtteranceSigner` as `ASSISTANT_UTTERANCE` (`memory_eligible = 1, grounding_eligible = 0` — conversational continuity without self-reinforcing confabulation).
   - Retrospection answered via Substrate 7 (`SELF_HISTORY`).
   - Beliefs managed via `ReflectionEngine` with evidence-gated `supersede()` and 5-criterion flagged Studio review queue.
7. **Quality & Verification Gates**:
   - 12 static architectural gates in `tests/test_static_gates.py` (zero `Any` public API, provenance contracts, staleness linter).
   - 671 non-hardware regression tests passing (100% green).
   - C1 split-conformal abstention acceptance gate passing (Wilson LB $\ge 0.80$).
   - A1 live hardware introspective accuracy passing (50 self-questions battery).
