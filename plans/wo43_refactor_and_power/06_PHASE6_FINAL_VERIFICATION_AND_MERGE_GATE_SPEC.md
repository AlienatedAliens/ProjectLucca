# WO-43 Phase 6 Specification — Full-System Verification, Paper/Doc Synchronization & Merge Gate

**Phase:** `Phase 6 of 6`
**Prerequisite:** Phases 1 through 5 completed and signed off by Independent Auditor Subagents.
**Commits in Phase 6:** `2` atomic commits (`Sub-step 6.1` Paper & Active Documentation Synchronization, `Sub-step 6.2` Final Integrity Proof & Branch Merge to `master`/`main`).

---

## 1. Sub-Step 6.1 — Synchronize Papers 1–4 & Active Documentation

### 1.1 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `papers/01_provenance_gated_memory/main.tex` | Update the Contrastive Companion Battery table from $N = 30$ ($n = 10$ per stratum) to include the pre-registered $N = 300$ ($n = 100$ per stratum) evaluation results, exact 95% Wilson CIs, and Holm-Bonferroni corrected McNemar $p$-values. Update the Memory Poisoning table with the $N = 300$ ($n = 100$ per cohort) v3 results (`[0.0%, 3.7%]` 95% Wilson CI on 0-error cohorts) and document the live `BelnapLatentInvestigator` ($\bot$/$\top$) fail-closed integration. |
| `papers/02_neurosymbolic_action_supervision/main.tex`, `papers/03_bicameral_npu_gpu_orchestration/main.tex`, `papers/04_clause_level_npu_supervision/main.tex` | Synchronize module paths (`speech_stream_pipeline.py`, `tool_dispatcher.py`, `deduction_runner.py`, `code_preflight_service.py`, `walton_schemes/`, `supervisor_lexicon.py`, `action_claim_grammar.py`, `receipt_truth_matcher.py`, `cascade_intent.py`, `cascade_substrates.py`, `cegis_grid_diff.py`, `cegis_sandbox.py`, `cegis_mutator.py`) and updated LOC metrics. |
| Active Documentation (`README.md`, `AGENTS.md`, `GEMINI.md`, `luccadocs/README.md`, `luccadocs/ARCHITECTURE.md`, `luccadocs/DECISIONS.md`, `luccadocs/CAPABILITY_TRUTH_MATRIX.md`, `luccadocs/EVALUATION_SCORECARD.md`, `luccadocs/funding/EVIDENCE_LEDGER.md`, `luccadocs/funding/README_FUNDERS.md`, `plans/README.md`, `pyproject.toml`) | Bump release baseline to `v1.51.0` (`WO-43`), update module maps, LOC tables, static gate counts, and empirical benchmark tables (`Contrastive v2 N=300`, `Memory Poisoning v3 N=300`). |

---

## 2. Sub-Step 6.2 — Full-System Verification & Merge Gate Checklist

Every command below must exit with code `0` on `refactor/wo43-modularization-and-power` before merging to `master` and `main`:

```powershell
# 1. Static & Anti-Cheat Gates (including new LOC ceiling, AST parity, NLI fail-closed, runtime reachability, and zero-lint gates)
uv run pytest tests/test_static_gates.py -v

# 2. Architectural Import-Linter Contracts (7/7 kept)
uv run lint-imports

# 3. Zero-Error Linter & Type-Checker Verification
uv run ruff check src tests
uv run mypy src

# 4. Full Unit & Integration Test Suite
uv run pytest tests/ -q -m "not tier2 and not hw and not soak"

# 5. Locked 150-Item Holdout & 300-Item Blind Benchmark Parity
uv run python scripts/eval_wo42_locked_holdout.py
uv run python scripts/eval_wo42_blind_300.py

# 6. End-to-End Cryptographic & Manifest Integrity Proof
uv run python scripts/prove_integrity.py
```

---

## 3. Final Independent Subagent Audit & Merge Protocol

1. Spawn a fresh read-only `research` subagent to audit the complete diff `v1.50.0-frozen-pre-wo43..refactor/wo43-modularization-and-power` against all 7 specification documents in `plans/wo43_refactor_and_power/`.
2. Once the auditor confirms **100% pass across all 6 phases**:
   ```powershell
   git checkout master
   git merge --no-ff refactor/wo43-modularization-and-power -m "Merge WO-43 (v1.51.0): God-object decomposition, 8-organ runtime activation, zero-lint remediation, and N=300 statistical power expansion"
   git tag -a v1.51.0-wo43-complete -m "Project Lucca v1.51.0 (WO-43 Complete)"
   git push origin master
   git push origin master:main
   git push origin v1.51.0-wo43-complete
   ```
