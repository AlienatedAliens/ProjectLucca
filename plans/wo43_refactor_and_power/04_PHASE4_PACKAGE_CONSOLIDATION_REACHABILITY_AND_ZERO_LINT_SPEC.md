# WO-43 Phase 4 Specification — Package Consolidation, 100% Runtime Reachability Gate & Zero-Error `ruff`/`mypy` Remediation

**Phase:** `Phase 4 of 6`
**Prerequisite:** Phase 3 completed and signed off by the Independent Auditor Subagent.
**Commits in Phase 4:** `4` atomic commits (`Sub-steps 4.1` through `4.4`).

---

## 1. Sub-Step 4.1 — Package Consolidation (`evaluation` $\to$ `eval`, `speech` $\to$ `senses`) & Dead Shell Removal

### 1.1 Exact Problem
1. `src/lucca/eval/` (`contrastive_grader.py`) and `src/lucca/evaluation/` (`in_d_grader.py`) split evaluation grading across two sibling packages.
2. `src/lucca/senses/` and `src/lucca/speech/` split audio/TTS/STT engines across two sibling packages.
3. `src/lucca/senses/stt.py` (`16` lines) is an empty placeholder stub (`0` callers), and `src/lucca/core/reflection.py` (`33` lines) is a legacy re-export shim (`0` callers in `src/lucca/`).

### 1.2 Exact Change Manifest
| Target | Action |
| :--- | :--- |
| `src/lucca/evaluation/in_d_grader.py` | Move canonical implementation into `src/lucca/eval/in_d_grader.py`; convert `src/lucca/evaluation/in_d_grader.py` into a 3-line deprecation re-export shim (`from lucca.eval.in_d_grader import *`) and wire `lucca-admin eval-contrastive` / `lucca-admin eval-ind` in `src/lucca/admin.py` so both graders are reachable from `lucca.admin`. |
| `src/lucca/senses/stt.py` & `src/lucca/core/reflection.py` | Check `tests/` for any direct imports; repoint any legacy test import of `lucca.core.reflection` to `lucca.memory.reflection` and delete `src/lucca/senses/stt.py` (`-16` lines) and `src/lucca/core/reflection.py` (`-33` lines). |
| `src/lucca/tools/lint.py` | Wire `lucca.tools.lint` into `src/lucca/admin.py` (`lucca-admin lint-check`) or move into `scripts/` so `src/lucca/tools/` is not an orphaned package. |

---

## 2. Sub-Step 4.2 — `scripts/` Triage (`326` Files / `77,775` LOC $\to$ `<= 25` Canonical CLI Scripts) & Transitive Runtime-Reachability Gate

### 2.1 Exact Problem
1. `scripts/` contains `326` top-level files (`77,775` lines), 90%+ of which are one-off `WO-01` through `WO-42` historical migration/training/debug scripts.
2. [`test_dead_code_register_no_unreferenced_symbols`](../../tests/test_static_gates.py) (`L985`) scans `scripts/` and `tests/` alongside `src/`, allowing modules in `src/lucca/` that have **zero callers in `src/lucca/`** to pass the dead-code gate if an old script in `scripts/` or test in `tests/` imports them.

### 2.2 Exact Change Manifest
| Target | Action |
| :--- | :--- |
| `scripts/` $\to$ `scripts/archive/wo01_wo42/` | Keep only the `<= 25` active canonical scripts in top-level `scripts/` (specifically: `prove_integrity.py`, `run_contrastive_eval.py`, `run_memory_poisoning_eval_v2.py`, `run_deontic_supervision_eval_v2.py`, `eval_wo42_blind_300.py`, `eval_wo42_locked_holdout.py`, `run_wo42_live_4model_matrix.py`, `compute_wo42_statistical_power.py`, `verify_manifests.py`, `check_hardware_budget.py`, and scripts directly referenced by `pyproject.toml`, `tests/`, or `prove_integrity.py`). Move all ~300 historical work-order scripts into `scripts/archive/wo01_wo42/`. |
| `tests/test_static_gates.py` | Add `test_all_src_modules_transitively_reachable_from_runtime()`:<br>• Parses the AST of every `.py` file under `src/lucca/`.<br>• Computes the transitive import closure starting from runtime entrypoints (`lucca.main`, `lucca.admin`, `lucca.core.orchestrator`, `lucca.ui.app`).<br>• Asserts that **0 modules in `src/lucca/` are unreachable from the runtime entrypoints**. Includes a positive control proving that a synthetic unreferenced module triggers failure. |

### 2.3 Verification (Sub-Step 4.2)
```powershell
uv run pytest tests/test_static_gates.py -q
uv run python scripts/prove_integrity.py --offline
```

---

## 3. Sub-Step 4.3 — Zero-Error `ruff check src tests` Remediation (`1,249` Errors $\to$ `0` Errors)

### 3.1 Breakdown of Current `1,249` Ruff Diagnostics
- `797` `E501` (line too long `> 100` chars)
- `241` `F401` (unused imports)
- `110` `F841` (unused local variables)
- `44` `E402` (module-level import not at top of file)
- `28` `I001` (unsorted import blocks)
- `29` miscellaneous (`F541`, `E712`, `B007`, `UP035`, etc.)

### 3.2 Anti-Slop Remediation Rules
1. **Forbidden:** Adding blanket `# noqa` comments or disabling `F401`, `F841`, `I001`, or `E402` globally in `pyproject.toml`.
2. **Procedure:**
   - Run `uv run ruff check --fix src tests` to cleanly resolve safe auto-fixable unused imports (`F401`) and import sorting (`I001`), then run `pytest` immediately to confirm no side-effect or re-export import was removed. (In `__init__.py` or re-export modules like `output_supervisor.py`, declare `__all__ = [...]` so Ruff recognizes intentional re-exports without `# noqa`).
   - Fix all `110` `F841` unused local variables by removing dead assignments or prefixing intentionally ignored unpack bindings with `_`.
   - Fix all `44` `E402` mid-file imports by moving imports to top-of-file (except where `sys.path` or Win32 DLL initialization precedes the import).
   - Format long lines (`E501`) across `src/` and `tests/` so `uv run ruff check src tests` exits with code `0` (`0` errors).

---

## 4. Sub-Step 4.4 — Zero-Error `mypy src` Remediation (`716` Errors in `113` Files $\to$ `0` Errors) & Static Lint Gate

### 4.1 Anti-Slop Typing Rules
1. **Forbidden:** Blanket `# type: ignore` spam or weakening `pyproject.toml` `[tool.mypy]` strictness flags.
2. **Procedure (Package-by-Package):**
   - Fix type annotations in `src/lucca/core/`, `src/lucca/memory/`, `src/lucca/sandbox/`, `src/lucca/reasoning/`, `src/lucca/brain/`, `src/lucca/senses/`, `src/lucca/router/`, and `src/lucca/ui/` (resolving `Optional` narrowing, `Protocol` attribute declarations, `JsonValue` narrowing, and OpenVINO/PySide6 third-party stub boundaries).
   - Verify `uv run mypy src` reports: `Success: no issues found`.
3. **Permanent Static Gate in `tests/test_static_gates.py`:**
   - Add `test_zero_ruff_and_mypy_errors()` in `tests/test_static_gates.py` that runs `ruff check src tests` and `mypy src` via `subprocess.run` and asserts returncode `0` on both.

### 4.2 Verification (Sub-Steps 4.3 & 4.4)
```powershell
uv run ruff check src tests
# Expected: All checks passed! (exit code 0)
uv run mypy src
# Expected: Success: no issues found (exit code 0)
uv run lint-imports
# Expected: Contracts: 7 kept, 0 broken
uv run pytest tests/ -q -m "not tier2 and not hw and not soak"
```

---

## 5. Phase 4 Independent Subagent Audit Gate (Mandatory STOP Before Phase 5)

Spawn a read-only `research` subagent to verify:
1. `test_all_src_modules_transitively_reachable_from_runtime()` passes with `0` unreachable modules in `src/lucca/`.
2. Top-level `scripts/` has `<= 25` active scripts and historical scripts are cleanly archived under `scripts/archive/wo01_wo42/`.
3. `uv run ruff check src tests` and `uv run mypy src` both return `0` errors without unauthorized `# noqa` or `# type: ignore` suppressions.
4. All unit tests and static gates pass.
