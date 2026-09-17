# Project Lucca — Antigravity Workspace Guidelines & Operational Rules

## 1. Project Overview & Role
You are operating inside the **Project Lucca** repository (`C:\projects\ProjectLucca`).
Lucca is a local-first, sandboxed desktop companion with real-time push-to-talk voice, symbolic reasoning compilation (LISP), and three-tier provenance-gated memory.

## 2. Hard Invariants & Non-Negotiables
1. **Never Promote Freeform LLM Narration into Memory:**
   - Any memory commit must originate from `USER_EXPLICIT` (speech transcription), `TOOL_VERIFIED` (sandbox output), or `LISP_ASSERTION`.
   - `LLM_NARRATION` is strictly rejected by the `ProvenanceGate`.
2. **Strict Hardware Budget Discipline:**
   - Host is an MSI Vector 16 HX AI with 16GB System RAM, Arrow Lake Core Ultra 9 275HX, and RTX 5080 16GB VRAM (Blackwell `sm_120`).
   - WSL2 is memory-clamped to 4.5GB via `.wslconfig`. Do not spawn heavy background processes in WSL2.
   - **Intel NPU is Accessible ONLY from Native Windows 11.** Never attempt to run OpenVINO NPU workloads inside WSL2 or Docker.
   - Tree models (XGBoost/LightGBM) run on CPU, **never on NPU** (OpenVINO lacks `TreeEnsembleClassifier` support).
3. **Phased Build Discipline:**
   - Implement strictly phase-by-phase (Phase 1 through Phase 6).
   - Do NOT proceed to the next phase until the current phase's acceptance criteria in `docs/00_original_build_brief.md` and `docs/04_deep_mechanical_testing_and_verification_matrix.md` are 100% satisfied with passing test execution.
4. **Symbolic Rule Promotion Gate:**
   - Never compile a LISP rule from a single interaction.
   - Must achieve $N \ge 5$ distinct cluster successes with 0 failures before promotion from quarantine.
   - Must pass 100% of historical regression test cases.
5. **Code Standards:**
   - Python 3.12+ using `uv`.
   - Pydantic v2 schemas for all cross-boundary IPC and data contracts (`src/lucca/core/schemas.py`).
   - Strict typing with zero `Any` in public interfaces.

## 3. Documentation Reference Directory
- Original Brief: `docs/00_original_build_brief.md`
- Recursive Audit & Flaw Proofs: `docs/01_recursive_architecture_audit_and_flaw_analysis.md`
- Systems Research & Prior Art: `docs/02_systems_research_prior_art_and_alternatives.md`
- Hardware Topology & IPC: `docs/03_enterprise_hardware_topology_and_ipc_spec.md`
- Mechanical Testing Matrix: `docs/04_deep_mechanical_testing_and_verification_matrix.md`
- Master System Specification: `docs/05_lucca_system_architecture_master_spec.md`
