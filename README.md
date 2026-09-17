# Project Lucca — Local Desktop Companion Agent

> **Enterprise Documentation Suite & Workspace for Antigravity IDE**  
> Target Host: MSI Vector 16 HX AI (Core Ultra 9 275HX / Arrow Lake-HX, RTX 5080 16GB VRAM, 16GB System RAM)

---

## 1. Overview for Reviewers & Collaborators

This repository contains the complete architecture, research foundation, physical compute specifications, and initial structural scaffolding for **Project Lucca**—a local-first, sandboxed desktop companion agent featuring:
- **Push-to-Talk Voice & 2D Avatar:** Sub-400ms end-to-end response time using Ultravox 8B (vLLM) and Kokoro TTS (OpenVINO INT8 on Intel NPU).
- **Three-Tier Provenance Memory:** Strict anti-hallucination write gate forbidding LLM narration from polluting long-term memory; hybrid dense + sparse (RRF) retrieval; knowledge graph.
- **Compiled Symbolic Reasoning:** Self-improving LISP/Scheme rule engine with a mandatory 5-strike qualification promotion gate and regression test suites.
- **Calibrated Dual-Brain Router:** Frozen ModernBERT semantic encoder (NPU) + XGBoost decision router (CPU) + Conformal Prediction fallback.
- **Isolated Sandbox:** Docker container in WSL2 with blocked local-subnet (RFC1918) egress, path-traversal protection, and host-mediated application launcher.

---

## 2. Master Documentation Index (`docs/`)

All system design documents, recursive audit logs, research surveys, and specifications are located in [`docs/`](./docs/):

| File | Title & Description | Primary Purpose |
|---|---|---|
| **[`00_original_build_brief.md`](./docs/00_original_build_brief.md)** | **Original Build Brief** | The foundational design brief, hardware budgets, phase dependencies, and original acceptance criteria. |
| **[`01_recursive_architecture_audit_and_flaw_analysis.md`](./docs/01_recursive_architecture_audit_and_flaw_analysis.md)** | **Recursive Flaw & Audit Log** | Line-by-line recursive interrogation of all assumptions, edge cases, failure modes (FM-01 through FM-06), and hardware contention traps. |
| **[`02_systems_research_prior_art_and_alternatives.md`](./docs/02_systems_research_prior_art_and_alternatives.md)** | **Systems Research & Prior Art** | Comprehensive literature review: Ultravox vs Moshi; Kokoro vs StyleTTS2; OpenHands vs E2B; MemGPT vs HippoRAG; Voyager vs Reflexion; RouteLLM & Conformal Prediction. |
| **[`03_enterprise_hardware_topology_and_ipc_spec.md`](./docs/03_enterprise_hardware_topology_and_ipc_spec.md)** | **Hardware Topology & IPC Spec** | Physical compute mapping (Domain A Windows Host, Domain B WSL2, Domain C Docker Sandbox), 4.5GB RAM clamping (`.wslconfig`), OpenVINO NPU caching, and Blackwell sm_120 CUDA 12.8 recipes. |
| **[`04_deep_mechanical_testing_and_verification_matrix.md`](./docs/04_deep_mechanical_testing_and_verification_matrix.md)** | **Mechanical Verification Matrix** | Exact mathematical formulations ($\text{ECE} \le 0.045$, $\text{Brier} \le 0.12$, $\text{RRF} \ge +0.20$), security penetration fuzzers, provenance gates, and regression test suites. |
| **[`05_lucca_system_architecture_master_spec.md`](./docs/05_lucca_system_architecture_master_spec.md)** | **Master System Architecture** | Typed Pydantic v2 data contracts, Micro-Scheme S-expression EBNF grammar, gas-metered execution semantics, and manuals for users, agents, and developers. |
| **[`project_lucca_architecture_review.md`](./docs/project_lucca_architecture_review.md)** | **Architectural Review & Feasibility** | High-level feasibility synthesis, latency budgets, and hardware allocation reality checks. |

---

## 3. Antigravity IDE Configuration

This workspace is fully configured for **Antigravity IDE**:

* **Workspace Rules:** [`GEMINI.md`](./GEMINI.md) and [`AGENTS.md`](./AGENTS.md) at the project root define non-negotiable operational invariants.
* **Modular Agent Rules:**
  - [`01_hardware_discipline.md`](./.agents/rules/01_hardware_discipline.md): Enforces compute engine partitioning, 4.5GB WSL2 clamp, and native Windows NPU execution.
  - [`02_memory_provenance.md`](./.agents/rules/02_memory_provenance.md): Enforces the `ProvenanceTag` gate and hard rejection of `LLM_NARRATION`.
  - [`03_lisp_promotion_gate.md`](./.agents/rules/03_lisp_promotion_gate.md): Mandates the 5-strike qualification rule and regression suite before rule activation.
  - [`04_code_quality_and_typing.md`](./.agents/rules/04_code_quality_and_typing.md): Enforces Python 3.12, strict Pydantic typing, and test-first development.
* **Operational Skill:** [`.agents/skills/lucca-pipeline/SKILL.md`](./.agents/skills/lucca-pipeline/SKILL.md) provides guided commands for environment verification, running phase tests, and starting background servers.
* **IDE Controls:**
  - `.vscode/settings.json`: Configures interpreter, pytest runner, formatting with ruff, and file nesting.
  - `.vscode/tasks.json`: Pre-configured Antigravity tasks (Verify Hardware, Run Tests, Clamp WSL2 Memory).
  - `.vscode/launch.json`: Debugging profiles for orchestrator and test harnesses.

---

## 4. Key Questions & Vectors for Review (For Claude Fable 5.1)

When reviewing these documents and planning adjustments, we suggest focusing on:
1. **Host-Sandbox Bridge Interface:** Review the proposed JSON-RPC / socket bridge between the Windows Host Orchestrator and the Docker sandbox in WSL2 (`docs/03_enterprise_hardware_topology_and_ipc_spec.md`). Does this strike the right balance between low latency and strict isolation?
2. **Context Rolling Window Strategy:** Scrutinize the multi-turn audio context compaction strategy in `docs/01_recursive_architecture_audit_and_flaw_analysis.md`. Is keeping raw audio embeddings for $k \le 2$ turns and text for older turns optimal for maintaining conversational coherence without bloating KV cache?
3. **LISP Grammar & Primitives:** Review the S-expression grammar in `docs/05_lucca_system_architecture_master_spec.md` (Section 4). Are there additional HTN/STRIPS planner primitives needed for multi-step desktop tasks?
4. **Conformal Quantile Tuning:** Review the conformal prediction non-conformity threshold formulation in `docs/04_deep_mechanical_testing_and_verification_matrix.md`.

---

## 5. Quickstart & Verification

To verify the local hardware configuration:
```powershell
uv run python scripts/verify_environment.py
```

To configure WSL2 memory clamping:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_wslconfig.ps1
```
