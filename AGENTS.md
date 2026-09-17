# Project Lucca — Antigravity Workspace Guidelines & Operational Rules

## 1. Project Overview & Role
You are operating inside the **Project Lucca** repository (`C:\projects\ProjectLucca`).
Lucca is a local-first, sandboxed desktop companion with real-time push-to-talk voice, symbolic reasoning compilation (LISP), and three-tier provenance-gated memory.

## 2. Hard Invariants & Non-Negotiables
1. **Never Promote Freeform LLM Narration into Memory:**
   - Any memory commit must originate from `USER_EXPLICIT` (verbatim Whisper transcript), `USER_DERIVED` (quote-grounded extraction from a `USER_EXPLICIT` source), `TOOL_VERIFIED` (structural facts of sandbox execution), or `LISP_ASSERTION`. `TOOL_CONTENT_UNTRUSTED` (file/page bodies) is never memory-eligible without a user act.
   - `LLM_NARRATION` is strictly rejected by the `ProvenanceGate`; there is no signer for it (ADR-006).
2. **Strict Hardware Budget Discipline:**
   - Host is an MSI Vector 16 HX AI with 16GB System RAM, Arrow Lake Core Ultra 9 275HX, and RTX 5080 16GB VRAM (Blackwell `sm_120`).
   - WSL2 is memory-clamped to 4.5GB via `.wslconfig`. Do not spawn heavy background processes in WSL2.
   - **Intel NPU is Accessible ONLY from Native Windows 11.** Never attempt to run OpenVINO NPU workloads inside WSL2 or Docker.
   - Tree models (XGBoost/LightGBM) run on CPU, **never on NPU** (OpenVINO lacks `TreeEnsembleClassifier` support).
3. **Phased Build Discipline:**
   - Implement strictly phase-by-phase (Phase 0 spikes, then Phase 1 through Phase 6) per `docs/11_phase_plan_v2.md`.
   - Do NOT proceed to the next phase until the current phase's sign-off bundle in `docs/10_testing_matrix_v2.md` §4 is green and its report files exist. Phases 4–6 contain human gates; synthetic data never satisfies them.
   - Never edit a threshold to make a test pass; record the measured value in `docs/14_blockers.md` and stop.
4. **Symbolic Rule Promotion Gate:**
   - Never compile a LISP rule from a single interaction.
   - Must achieve $N \ge 5$ distinct cluster successes with 0 failures before promotion from quarantine.
   - Must pass 100% of historical regression test cases.
5. **Code Standards:**
   - Python 3.12+ using `uv`.
   - Pydantic v2 schemas for all cross-boundary IPC and data contracts (`src/lucca/core/schemas.py`).
   - Strict typing with zero `Any` in public interfaces.

## 3. Documentation Reference Directory

**Precedence:** `docs/13_decisions_log.md` and `docs/07_contradiction_register.md` override docs 00–05 wherever they conflict. Read order for implementers: 13 → 07 → `08_adr/` → `09_developer_spec/` → 10 → 11.

Authoritative (2026-09-17 final review):
- Decisions Log: `docs/13_decisions_log.md`
- Contradiction Register & canonical values: `docs/07_contradiction_register.md`
- ADRs: `docs/08_adr/ADR-001..008`
- Developer Specs: `docs/09_developer_spec/01..12`
- Testing Matrix v2: `docs/10_testing_matrix_v2.md`
- Phase Plan v2: `docs/11_phase_plan_v2.md`
- Prior Art Survey: `docs/12_prior_art_survey.md`
- Defect index: `docs/06_critical_review_findings.md`

Historical (superseded where the register says so):
- Original Brief: `docs/00_original_build_brief.md`
- Recursive Audit & Flaw Proofs: `docs/01_recursive_architecture_audit_and_flaw_analysis.md`
- Systems Research & Prior Art: `docs/02_systems_research_prior_art_and_alternatives.md`
- Hardware Topology & IPC: `docs/03_enterprise_hardware_topology_and_ipc_spec.md`
- Mechanical Testing Matrix v1: `docs/04_deep_mechanical_testing_and_verification_matrix.md`
- Master System Specification v1: `docs/05_lucca_system_architecture_master_spec.md`

Key settled facts every agent must know: LLM = `llama-server` natively on Windows with Ultravox Q6_K GGUF (vLLM retired); Whisper runs on every turn (Ultravox emits no transcript); storage = SQLite+FTS5+sqlite-vec (Chroma retired); Docker CE inside Ubuntu WSL2 (Desktop unsupported); runtime root `C:\ProjectLucca`; four host processes + ZMQ (ADR-008).
