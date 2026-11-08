# WO-43 Master Charter & Branch Protocol — Codebase Modularization, Organ Activation, Deduplication & High-Power Empirical Expansion

**Work Order:** `WO-43` (Target Release: `v1.51.0`)
**Authoring Date:** November 8, 2026
**Frozen Pre-Refactor Commit:** `543f5cc`
**Frozen Git Tag:** `v1.50.0-frozen-pre-wo43` (pushed to `origin`)
**Frozen Recovery Branch:** `freeze/v1.50.0-wo42-baseline` (pushed to `origin`)
**Active Working Branch:** `refactor/wo43-modularization-and-power`

---

## 1. Purpose & Engineering Scope

This specification suite governs `WO-43`. No production file in `src/lucca/` may be modified outside the step-by-step manifests defined in Documents `01` through `06` of this directory.

`WO-43` addresses four verified structural and empirical findings from the `v1.50.0` audit:
1. **Five God-Objects & Copy-Paste Bloat:** `orchestrator.py` (`5,243` lines), `corroboration.py` (`2,407` lines), `output_supervisor.py` (`2,263` lines), `cascade.py` (`2,241` lines), and `cegis_unshackled.py` (`2,004` lines) accumulated multiple work orders inline, including `1,535` lines of duplicated SQL/receipt loops in `corroboration.py` and `725` lines of superseded CEGIS code in `cegis_python.py`.
2. **Eight Built-but-Unwired Subsystems (`11,147` Lines in `src/lucca/` + `942` Lines in `orchestrator.py`):** Across `WO-20` through `WO-34`, eight complete subsystems (`win32_security.py`, `git_dag.py`, `convergence.py`, `latent_probe.py`, `orchestrator.py:1234-2175` deduction/planning, `consolidation.py` + `compression.py` + `scratchpad.py` + `mcts.py` + `abduction.py` + `topology.py`, `working.py` + `pipeline_tracer.py`, and `spatial_dsl.py` + `arc_primitives.py`) were unit-tested in isolation but never wired into the live turn pipeline (`TurnPipeline`, `Orchestrator`, `SafeFileTool`, `MemoryCommitService`).
3. **NLI `UNCERTAIN` Fail-Open Paths & Static Lint Debt:** Ten downstream consumers of `VerifierWorker.verify()` only check `== NLIVerdict.CONTRADICTION` and treat `NLIVerdict.UNCERTAIN` as a pass-through; `uv run lint` currently reports `1,249` Ruff diagnostics and `716` Mypy errors; `scripts/` holds `326` files (`77,775` lines) of mixed active and historical scripts.
4. **Underpowered Evaluation Strata in Paper 1:** The Contrastive Companion Battery (`data/benchmarks/contrastive_battery.jsonl`) has $N = 30$ ($n = 10$ per stratum: Recall, Introspection, Abstention), yielding $\pm 18\%\text{ to }\pm 26\%$ 95% Wilson CIs and $p = 1.000$ on $+10\text{ pp}$ and $-10\text{ pp}$ differences. Memory Poisoning (`memory_poisoning_v2.jsonl`) has $N = 100$ ($n = 40, 30, 30$), where $0/30$ errors leaves a $11.4\%$ upper 95% Wilson bound.

---

## 2. Non-Negotiable Golden Rules

1. **Branch Isolation:** All work executes on `refactor/wo43-modularization-and-power`. `master`, `main`, `freeze/v1.50.0-wo42-baseline`, and tag `v1.50.0-frozen-pre-wo43` must never be force-pushed or modified during Phases 1–5.
2. **Fowler's Two Hats Invariant (Strict Separation of Structural Moves vs. Behavioral Changes):**
   - A commit that extracts, splits, or deduplicates code **must not alter runtime behavior**.
   - A commit that changes runtime behavior (such as wiring `BelnapLatentInvestigator` into `UNCERTAIN` call sites or wiring `TracebackDivergenceGuard` into `_stream_llm_speech`) **must happen in its own dedicated sub-step commit** after the structural extraction commit is verified green.
3. **Feathers' Characterization Gate Before Every Extraction:**
   - Before extracting any class or method from a god-object, the implementing agent must run (and if missing, add) characterization tests locking the exact return values, state mutations (`self.current_turn_receipts`, `self.history`, `self.pending_spoken_updates`), and emitted `Envelope` events.
4. **One Sub-Step = One Atomic Git Commit:**
   - Never combine multiple sub-steps into a single commit. Stage explicit file paths only (`git add <file1> <file2>`); `git add -A` and `git add .` are forbidden per `AGENTS.md` Rule 8.
5. **Hard Rollback Rule (No "Fixing Forward"):**
   - After every sub-step edit, execute:
     ```powershell
     uv run pytest tests/test_static_gates.py -q
     uv run lint-imports
     uv run pytest tests/ -q -m "not tier2 and not hw and not soak"
     ```
   - If any previously passing test fails during a structural extraction, **do not improvise fixes across unrelated files**. Run `git checkout -- src tests`, diagnose the missed state or import dependency against the phase specification, update the sub-step table if needed, and re-apply cleanly.
6. **Mandatory Blinded Independent Subagent Audit Between Phases:**
   - At the end of each phase (Phases 1 through 6), the implementing agent **must** invoke a fresh read-only `research` subagent with the phase's `Independent Auditor Prompt & Checklist`. The next phase cannot begin until the auditor verifies zero regressions, zero silent deletions, zero unauthorized `# noqa` / `# type: ignore` suppressions, and 100% compliance with the phase's Definition of Done.
7. **Anti-Slop Documentation Standard (`AGENTS.md` Rule 9):**
   - Every docstring, comment, commit message, benchmark report, and paper update produced under `WO-43` must pass `test_no_ai_slop_in_papers_and_docs` in `tests/test_static_gates.py`.

---

## 3. Master Quantitative Baseline & Target Ledger

| Metric / Artifact | Frozen Baseline (`543f5cc`) | Post-`WO-43` Mandatory Target | Enforcing Gate |
| :--- | :--- | :--- | :--- |
| `src/lucca/core/orchestrator.py` | `5,243` total lines (`4,813` non-blank) | **`<= 2,200` total lines** | `test_orchestrator_loc_and_decomposition_gate` |
| `src/lucca/core/corroboration.py` | `2,407` total lines (`2,224` non-blank) | **`<= 850` total lines** (`~1,185` lines of duplicate loops removed) | `test_corroboration_loc_and_walton_parity_gate` |
| `src/lucca/sandbox/output_supervisor.py` | `2,263` total lines (`2,087` non-blank) | **`<= 500` total lines** | `test_output_supervisor_loc_and_split_gate` |
| `src/lucca/core/cascade.py` | `2,241` total lines (`2,037` non-blank) | **`<= 800` total lines** | `test_cascade_loc_and_split_gate` |
| `src/lucca/reasoning/cegis_unshackled.py` | `2,004` total lines (`1,793` non-blank) | **`<= 750` total lines** (`cegis_python.py` `725` lines retired) | `test_cegis_loc_and_split_gate` |
| Disconnected `src/lucca/` Modules | `28` modules (`11,147` lines) unreachable from runtime | **`0` unreachable modules** (`100%` transitive reachability from runtime entrypoints) | `test_all_src_modules_transitively_reachable_from_runtime` |
| NLI `UNCERTAIN` Consumer Seams | `10` call sites fail open on `UNCERTAIN` | **`0` fail-open call sites** (Belnap `NEITHER` $\bot$ / `BOTH` $\top$ routing) | `test_no_nli_uncertain_fail_open_consumers` |
| `uv run lint-imports` | `7 kept, 0 broken` | **`7+ kept, 0 broken`** | `uv run lint-imports` |
| `uv run ruff check src tests` | `1,249` errors | **`0` errors** | `test_zero_ruff_and_mypy_errors` |
| `uv run mypy src` | `716` errors in `113` files | **`0` errors** | `test_zero_ruff_and_mypy_errors` |
| Active `scripts/` Directory | `326` files (`77,775` lines) | **`<= 25` canonical CLI scripts** (historical scripts in `scripts/archive/wo01_wo42/`) | `test_scripts_directory_hygiene` |
| Contrastive Companion Battery | $N = 30$ ($10$ per stratum; $\pm 22\%$ CI; $p = 1.000$) | **$N = 300$ ($100$ per stratum; $\le \pm 7.8\%$ CI; $\ge 80\%$ power for $\Delta \ge 12\text{ pp}$)** | `test_contrastive_v2_power_and_integrity` |
| Memory Poisoning Battery | $N = 100$ ($40/30/30$; $0/30$ upper CI $= 11.4\%$) | **$N = 300$ ($100/100/100$; $0/100$ upper CI $= 3.7\%$)** | `test_memory_poisoning_v3_power_and_integrity` |
| Locked Holdout (`150` items) | `145/150` (`96.67%`) / `150/150` post-bugfix | **`150/150` (`100.0%`) post-bugfix (`0` regressions)** | `scripts/eval_wo42_locked_holdout.py` |

---

## 4. Document Index in `plans/wo43_refactor_and_power/`

1. **[`00_MASTER_CHARTER_AND_BRANCH_PROTOCOL.md`](./00_MASTER_CHARTER_AND_BRANCH_PROTOCOL.md)** — Master Charter, Golden Rules, Baseline/Target Ledger, and Rollback Protocol.
2. **[`01_PHASE1_HYGIENE_BELNAP_NLI_AND_SANDBOX_WIRING_SPEC.md`](./01_PHASE1_HYGIENE_BELNAP_NLI_AND_SANDBOX_WIRING_SPEC.md)** — Working-Tree Hygiene, Belnap 4-Valued NLI `UNCERTAIN` Fail-Closed Wiring (`latent_probe.py`), and Windows TOCTOU + Transactional File DAG Wiring (`win32_security.py`, `git_dag.py`).
3. **[`02_PHASE2_ORCHESTRATOR_DECOMPOSITION_AND_ORGAN_WIRING_SPEC.md`](./02_PHASE2_ORCHESTRATOR_DECOMPOSITION_AND_ORGAN_WIRING_SPEC.md)** — Decomposing `orchestrator.py` (`5,243` $\to$ `<= 2,200` lines) and Wiring `TracebackDivergenceGuard`, `DeductionAndPlanningRunner`, `ConsolidationEngine`, `WorkingMemory`, and `PipelineTracer`.
4. **[`03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md`](./03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md)** — Deduplicating and Decomposing `corroboration.py`, `output_supervisor.py`, `cascade.py`, and `cegis_unshackled.py` + Wiring `spatial_dsl` / `arc_primitives` into CEGIS.
5. **[`04_PHASE4_PACKAGE_CONSOLIDATION_REACHABILITY_AND_ZERO_LINT_SPEC.md`](./04_PHASE4_PACKAGE_CONSOLIDATION_REACHABILITY_AND_ZERO_LINT_SPEC.md)** — Merging `evaluation` $\to$ `eval` and `speech` $\to$ `senses`, Archiving `scripts/`, Enforcing 100% Runtime Reachability, and Burning Down `1,249` Ruff + `716` Mypy Errors to Zero.
6. **[`05_PHASE5_STATISTICAL_POWER_EXPANSION_SPEC.md`](./05_PHASE5_STATISTICAL_POWER_EXPANSION_SPEC.md)** — Pre-Registered $N = 300$ Contrastive Companion Battery v2 and $N = 300$ Memory Poisoning Battery v3 Authoring, Blinded IRR Grading, and Live Multi-Arm Execution.
7. **[`06_PHASE6_FINAL_VERIFICATION_AND_MERGE_GATE_SPEC.md`](./06_PHASE6_FINAL_VERIFICATION_AND_MERGE_GATE_SPEC.md)** — Full-System Integrity Verification, Live 4-Model E2E Matrix Check, Paper/Doc Synchronization, Final Audit, and Branch Merge Protocol.
