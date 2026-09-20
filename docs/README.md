# Project Lucca — Documentation Master Index & Governance Policy

**Version:** 1.2.0  
**Updated:** September 20, 2026  
**Git Baseline:** Milestone 4 Complete (`6b1a34d`)

---

## 1. Documentation Lifecycle Policy: When to Update vs. Archive vs. Create New

To maintain strict truth-in-documentation and prevent codebase drift, all Project Lucca documentation adheres to a three-tier lifecycle:

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                           DOCUMENTATION LIFECYCLE                             │
├───────────────────────────────────────────────────────────────────────────────┤
│ 1. LIVING CANONICAL SPECS (Update Continuously)                               │
│    • Location: docs/*.md (ARCHITECTURE.md, DECISIONS.md, README.md, etc.)     │
│    • Rule: MUST reflect current working code truth. Never allow drift.       │
│    • Action: Edit in place on every PR/commit that changes system behavior.   │
├───────────────────────────────────────────────────────────────────────────────┤
│ 2. SUBSYSTEM SPECS & DECISIONS (Create New / Ratify)                         │
│    • Location: docs/specs/*.md, docs/adr/*.md, docs/research/*.md             │
│    • Rule: Specific to major architectural capabilities or milestones.        │
│    • Action: Create when specifying new subsystems (e.g. BDI, Cascade).       │
│              When superseded, mark with frontmatter alert pointing to canon.  │
├───────────────────────────────────────────────────────────────────────────────┤
│ 3. EMPIRICAL EVALUATION REPORTS (Point-in-Time Measurement Records)           │
│    • Location: docs/eval/*.md, data/eval/**/*.json                            │
│    • Rule: Immutable ground-truth measurements captured from physical silicon.│
│    • Action: Never alter past data; create new reports for new evaluation runs│
├───────────────────────────────────────────────────────────────────────────────┤
│ 4. HISTORICAL ARCHIVES (Preserve Point-in-Time Provenance)                    │
│    • Location: docs/archive/**                                                │
│    • Rule: Point-in-time exploratory drafts, early audits, obsolete lore.    │
│    • Action: Move superseded exploratory files here with an archival note.    │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Master Documentation Directory

### 2.1 Living Canonical Documents (Current System Truth)
| Document | Purpose |
| :--- | :--- |
| [`ARCHITECTURE.md`](file:///C:/Projects/ProjectLucca/docs/ARCHITECTURE.md) | **Canonical Master Specification**: 4-process topology, 3 execution tiers, MicroScheme runtime, memory architecture, container sandboxing, audio pipeline. |
| [`DECISIONS.md`](file:///C:/Projects/ProjectLucca/docs/DECISIONS.md) | **Canonical Decisions Log**: All ratified decisions (D-AUD-01 through D-SUP-01) with statuses and implementation commits. |
| [`MODEL_STRATEGY.md`](file:///C:/Projects/ProjectLucca/docs/MODEL_STRATEGY.md) | **Model Weights & VRAM Budget**: Mistral NeMo 12B Q6_K abliterated deployment on RTX 5080, Kokoro ONNX, Whisper CUDA. |
| [`AUDIT_REMEDIATION_LOG.md`](file:///C:/Projects/ProjectLucca/docs/AUDIT_REMEDIATION_LOG.md) | **Punch-List & Remediation Tracker**: Status of all post-audit remediation items. |
| [`IMPLEMENTATION_WALKTHROUGH.md`](file:///C:/Projects/ProjectLucca/docs/IMPLEMENTATION_WALKTHROUGH.md) | **Detailed Engineering Walkthrough**: Step-by-step milestone execution logs, code diff rationales, and silicon benchmark tables. |
| [`NEUROSYMBOLIC_RESEARCH_PAPER.md`](file:///C:/Projects/ProjectLucca/docs/NEUROSYMBOLIC_RESEARCH_PAPER.md) | **Formal Academic Paper**: *"Project Lucca: A Sub-450ms Neuro-Symbolic Cognitive Architecture for Local Voice Agents"* (NeurIPS/ICLR style). |

### 2.2 Active Research & Theoretical Foundations (`docs/research/`)
| Document | Purpose |
| :--- | :--- |
| [`NEUROSYMBOLIC_RESEARCH_PAPER.md`](file:///C:/Projects/ProjectLucca/docs/research/NEUROSYMBOLIC_RESEARCH_PAPER.md) | The authoritative publication draft detailing Architecture B Hardened by Architecture C. |
| [`NEUROSYMBOLIC_STATE_OF_THE_ART_COMPENDIUM.md`](file:///C:/Projects/ProjectLucca/docs/research/NEUROSYMBOLIC_STATE_OF_THE_ART_COMPENDIUM.md) | Comprehensive survey of dual-process cognitive architectures, SMT solvers, and epistemic logic. |
| [`COGNITIVE_LOBES_AND_EPISTEMIC_AUDITING.md`](file:///C:/Projects/ProjectLucca/docs/research/COGNITIVE_LOBES_AND_EPISTEMIC_AUDITING.md) | Deep academic analysis of epistemic knowledge gaps, Belnap bilattices, and cognitive lobe routing. |
| [`AFFECTIVE_COGNITIVE_ARCHITECTURE_SPEC.md`](file:///C:/Projects/ProjectLucca/docs/research/AFFECTIVE_COGNITIVE_ARCHITECTURE_SPEC.md) | Continuous 3D PAD (Pleasure-Arousal-Dominance) leaky integrator ODE dynamics specification. |

### 2.3 Subsystem Specifications & Design Plans (`docs/specs/`)
| Document | Purpose |
| :--- | :--- |
| [`MILESTONE_4_IMPLEMENTATION_PLAN.md`](file:///C:/Projects/ProjectLucca/docs/specs/MILESTONE_4_IMPLEMENTATION_PLAN.md) | Engineering plan for Speculative BDI, Cognitive Bus arbitration, and Output Supervision. |
| [`DEONTIC_SANDBOX_DESIGN.md`](file:///C:/Projects/ProjectLucca/docs/specs/DEONTIC_SANDBOX_DESIGN.md) | Specification for WSL2 container isolation, Win32 handle jailing, and `TaintFlags`. |
| [`MILESTONE_1_MEASUREMENT_PLAN.md`](file:///C:/Projects/ProjectLucca/docs/specs/MILESTONE_1_MEASUREMENT_PLAN.md) | Methodology for acoustic loopback profiling, VRAM allocation truth, and ASR benchmarking. |
| [`NEUROSYMBOLIC_REMEDIATION_STRATEGY.md`](file:///C:/Projects/ProjectLucca/docs/specs/NEUROSYMBOLIC_REMEDIATION_STRATEGY.md) | Master 7-Milestone roadmap for the neuro-symbolic overhaul. |
| [`TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md`](file:///C:/Projects/ProjectLucca/docs/specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md) | Capability status map v1.1.4 classifying all subsystems into Implemented, Historical, or Designed. |
| [`LUCCA_FULL_FEATURE_SPEC.md`](file:///C:/Projects/ProjectLucca/docs/specs/LUCCA_FULL_FEATURE_SPEC.md) | End-to-end feature matrix and user interaction flows. |

### 2.4 Empirical Evaluation & Verification Reports (`docs/eval/`)
| Document | Purpose |
| :--- | :--- |
| [`COMPREHENSIVE_100_EVAL_REPORT.md`](file:///C:/Projects/ProjectLucca/docs/eval/COMPREHENSIVE_100_EVAL_REPORT.md) | Exhaustive item-by-item audit of the 100-question benchmark with true source-of-answer attribution. |
| [`DIAGNOSTIC_EVAL_V2_REPORT.md`](file:///C:/Projects/ProjectLucca/docs/eval/DIAGNOSTIC_EVAL_V2_REPORT.md) | Diagnostic Battery v2 results ($N=75$) across all 8 failure dimensions. |
| [`LIVE_AI_VERIFICATION_REPORT.md`](file:///C:/Projects/ProjectLucca/docs/eval/LIVE_AI_VERIFICATION_REPORT.md) | Live neural execution results from RTX 5080 verifying model abliteration and tool calling. |

### 2.5 Historical & Superseded Archives (`docs/archive/`)
* **`docs/archive/2026-09-17_pre_phase4_audit/`**: Original specifications and ADRs from before the deep technical audit.
* **`docs/archive/historical_investigations/`**:
  - `01_recursive_architecture_audit_and_flaw_analysis.md` through `05_lucca_system_architecture_master_spec.md`: Initial flaw analysis prior to audit ratification.
  - `lucca_phase1_investigation_and_proposals.md`: Early phase 1 proposals (superseded by Milestones 1–4).
  - `project_lucca_architecture_review.md`: Early exploratory review.
  - `chrono_trigger_preview.html`: Legacy lore mockup (superseded by D-AUD-03 persona canonicalization).

---

## 3. Build & Milestone Completion Progress

```
                    PROJECT LUCCA BUILD ROADMAP
┌─────────────┬─────────────────────────────────────────────────┬──────────────┐
│ Milestone   │ Objective & Key Deliverables                    │ Status       │
├─────────────┼─────────────────────────────────────────────────┼──────────────┤
│ Milestone 1 │ Ground-Truth Empirical Baseline                 │ 100% DONE    │
│             │ • 200 CPU / 50 CUDA loopback trials             │ (Commit      │
│             │ • 707.55ms P50 physical turnaround on CUDA      │  3837ff7)    │
│             │ • Diagnostic v2 (N=75) & Reviewer Held-Out (N=65)│              │
├─────────────┼─────────────────────────────────────────────────┼──────────────┤
│ Milestone 2 │ Hardened Deontic Sandbox                        │ 100% DONE    │
│             │ • Win32 handle jailing & hardlink checks        │ (Commit      │
│             │ • WSL2 container isolation (--network none)     │  5976b7e)    │
│             │ • Persistent taint tracking (TaintFlags)        │              │
├─────────────┼─────────────────────────────────────────────────┼──────────────┤
│ Option A    │ Persistent Container RPC & Joint Benchmark      │ 100% DONE    │
│             │ • Persistent Docker RPC (6.87ms P50)            │ (Commit      │
│             │ • In-container Python zombie process reaper     │  d5fe8cc)    │
│             │ • Joint audio-tool benchmark (1,613.5ms P50)    │              │
├─────────────┼─────────────────────────────────────────────────┼──────────────┤
│ Milestone 3 │ Epistemic Search Cascade & Bilattice            │ 100% DONE    │
│             │ • 5-substrate prioritized search cascade        │ (Commit      │
│             │ • Belnap FOUR evidential bilattice (bot abstention)│ (Commit     │
│             │ • Pre-rendered floor cues (3.1us IPC write)     │  b7a66d8)    │
│             │ • N=25 confabulation battery (0/25 hallucinations)│             │
├─────────────┼─────────────────────────────────────────────────┼──────────────┤
│ Milestone 4 │ Cognitive Arbitration, Speculative BDI & Output │ 100% DONE    │
│             │ • SpeculativeBDIValidator (<200us pre-dispatch) │ (Commit      │
│             │ • Cognitive bus arbitration (yield/interrupt)   │  6b1a34d)    │
│             │ • Dimension 7B output supervision (markdown norm)│              │
│             │ • Live empirical adv_12 mitigation on RTX 5080  │              │
├─────────────┼─────────────────────────────────────────────────┼──────────────┤
│ Milestone 5 │ Continuous Affective ODE & Prefix KV Cache      │ UP NEXT      │
│             │ • 3D PAD (Pleasure-Arousal-Dominance) ODE model │ (~1 session) │
│             │ • Suffix KV cache optimization in prompt builder│              │
├─────────────┼─────────────────────────────────────────────────┼──────────────┤
│ Milestone 6 │ Autonomous Rule Induction & SMT Verification    │ QUEUED       │
│             │ • Babble/Stitch e-graph macro synthesis         │ (~1-2 sess.) │
│             │ • Z3 SMT automated formal proof of invariants   │              │
├─────────────┼─────────────────────────────────────────────────┼──────────────┤
│ Milestone 7 │ Standalone Packaging & Final Desktop Release    │ QUEUED       │
│             │ • Frozen PyInstaller bundle (Lucca.spec)        │ (~1 session) │
│             │ • Final desktop system tray & acceptance battery│              │
└─────────────┴─────────────────────────────────────────────────┴──────────────┘
```
