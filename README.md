# Project Lucca — Local Desktop Companion Agent

> **Enterprise Documentation Suite & Workspace for Antigravity IDE**  
> Target Host: MSI Vector 16 HX AI (Core Ultra 9 275HX / Arrow Lake-HX, RTX 5080 16GB VRAM, 16GB System RAM)

---

## 1. Overview for Reviewers & Collaborators

This repository contains the complete architecture, research foundation, physical compute specifications, and initial structural scaffolding for **Project Lucca**—a local-first, sandboxed desktop companion agent featuring:
- **Push-to-Talk Voice & 2D Avatar:** typically under half a second to first audio (≤ 600 ms median gate) using Ultravox 8B served by `llama-server` natively on Windows (Q6_K GGUF), Whisper on the Intel NPU, and Kokoro TTS (NPU preferred, iGPU/CPU ladder).
- **Provenance-Gated Memory:** capability-signed write gate; LLM narration can never become memory; verbatim transcripts + quote-grounded derived facts; SQLite + FTS5 + `sqlite-vec` hybrid retrieval; bi-temporal knowledge graph.
- **Compiled Symbolic Reasoning:** rules are pure `State → Plan` functions in a tiny Scheme DSL; promoted only after ≥ 5 distinct-cluster shadow successes, 0 failures, and a passing regression suite.
- **Calibrated Router:** heuristic first, then LightGBM (CPU) + MiniLM encoder (NPU) with a real split-conformal guard, gated on a statistically adequate data floor.
- **Split Sandboxes:** Docker CE in WSL2; a file sandbox with no network and a web sandbox with no files; ordered egress allow-list with default drop; host-mediated launcher with spoken confirmation.

Runtime install root: `C:\ProjectLucca` (see decision D-08). Development repo: `C:\Projects\ProjectLucca`.

---

## 2. Master Documentation Index (`docs/`)

**Read order for implementers:** `13` → `07` → `08_adr/*` → `09_developer_spec/*` → `10` → `11`. Where the newer documents (06–13) conflict with the originals (00–05), **the newer documents win**; the contradiction register lists every such case with line references.

### 2.1 Authoritative set (2026-09-17 final review)

| File | Purpose |
|---|---|
| [`13_decisions_log.md`](./docs/13_decisions_log.md) | Every architectural decision, its status, evidence, and what it supersedes. **Start here.** |
| [`07_contradiction_register.md`](./docs/07_contradiction_register.md) | Every inconsistency across docs 00–05/code with the canonical value and line refs. |
| [`08_adr/`](./docs/08_adr/) | ADR-001 engine · 002 storage · 003 egress · 004 split sandboxes · 005 UI · 006 provenance · 007 rules-as-plans · 008 process topology. |
| [`09_developer_spec/`](./docs/09_developer_spec/) | 01 topology+IPC · 02 ports · 03 provenance · 04 storage schema · 05 rule DSL+lifecycle · 06 router+labeling · 07 audio+barge-in · 08 chunker · 09 sandbox · 10 latency budgets · 11 config/observability · 12 threat model. |
| [`10_testing_matrix_v2.md`](./docs/10_testing_matrix_v2.md) | Tiered tests, property tests, hardware/soak reports, phase sign-off bundles. Supersedes doc 04 where they differ. |
| [`11_phase_plan_v2.md`](./docs/11_phase_plan_v2.md) | Phase 0 spikes, Phases 1–6 acceptance, human gates, deferred scope. |
| [`12_prior_art_survey.md`](./docs/12_prior_art_survey.md) | Comparable projects and alternatives with verification status. |
| [`06_critical_review_findings.md`](./docs/06_critical_review_findings.md) | Defect index for `src/`, build files, and docs 00–05, mapped to fixes. |
| [`HANDOVER_2026-09-17_critical_review.md`](./docs/HANDOVER_2026-09-17_critical_review.md) | Full narrative of the final review's findings. |
| [`RESEARCH_REPORT_2026-09-17_engine_decision.md`](./docs/RESEARCH_REPORT_2026-09-17_engine_decision.md) + [`_review_notes.md`](./docs/RESEARCH_REPORT_2026-09-17_review_notes.md) | External fact-check that settled the engine decision, with the reviewer's re-grading of each claim. |

### 2.2 Original set (historical; superseded where the register says so)

| File | Title |
|---|---|
| [`00_original_build_brief.md`](./docs/00_original_build_brief.md) | Original Build Brief |
| [`01_recursive_architecture_audit_and_flaw_analysis.md`](./docs/01_recursive_architecture_audit_and_flaw_analysis.md) | Recursive Flaw & Audit Log |
| [`02_systems_research_prior_art_and_alternatives.md`](./docs/02_systems_research_prior_art_and_alternatives.md) | Systems Research & Prior Art |
| [`03_enterprise_hardware_topology_and_ipc_spec.md`](./docs/03_enterprise_hardware_topology_and_ipc_spec.md) | Hardware Topology & IPC Spec |
| [`04_deep_mechanical_testing_and_verification_matrix.md`](./docs/04_deep_mechanical_testing_and_verification_matrix.md) | Mechanical Verification Matrix (v1) |
| [`05_lucca_system_architecture_master_spec.md`](./docs/05_lucca_system_architecture_master_spec.md) | Master System Architecture (v1) |
| [`project_lucca_architecture_review.md`](./docs/project_lucca_architecture_review.md) | Architectural Review & Feasibility |

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

## 4. Review Questions — Resolved

The four review vectors originally posed here were answered in the final review:
1. **Host–sandbox bridge:** `docker exec` JSON-over-stdio, no published ports, no Docker socket exposure — spec 09 §1.
2. **Context rolling window:** current turn as raw audio, all prior user turns as Whisper text (Ultravox emits no transcript; fixie-ai recommends text history) — spec 07 §8. The "k ≤ 2 raw audio turns" strategy previously attributed to doc 01 was never written there.
3. **LISP grammar:** one canonical `(rule … :when … :plan …)` form with a closed primitive list; HTN/PDDL deferred to Phase 7+ — spec 05, ADR-007.
4. **Conformal quantile:** computed from a calibration split with `⌈(n+1)(1−α)⌉/n`, never hard-coded; data floor of 600 decisions — spec 06 §5–7.

---

## 5. Quickstart & Verification

```powershell
uv sync --frozen
uv run lucca-admin env-check          # GPU mode, NPU, Docker CE in WSL2, sqlite-vec, LUCCA_HOME layout
powershell -ExecutionPolicy Bypass -File scripts/setup_wslconfig.ps1   # writes the canonical .wslconfig (register §C)
uv run pytest -m "not hw and not soak" # Tier 0–2
uv run python -m lucca.main           # start Lucca (spawns llama-server + 4 processes)
```

Until `lucca-admin` exists, `uv run python scripts/verify_environment.py` remains the environment check.

## 6. Privacy

Nothing leaves the machine except sandboxed web fetches to public hosts on ports 80/443. No telemetry. Retention: audio 7 days, tool bodies 24 h, logs 30 days, transcripts until you say "forget". `lucca-admin memory export` dumps everything Lucca remembers in readable form. See spec 11 §8 and spec 12.
