# WO-43 Phase 3 Specification — Domain God-Objects Deduplication, Decomposition & Spatial CEGIS Wiring

**Phase:** `Phase 3 of 6`
**Prerequisite:** Phase 2 completed and signed off by the Independent Auditor Subagent.
**Target God-Objects:**
1. [`src/lucca/core/corroboration.py`](../../src/lucca/core/corroboration.py) (`2,407` lines $\to$ **`<= 850` lines**; `-1,185` lines of duplicated loops deleted)
2. [`src/lucca/sandbox/output_supervisor.py`](../../src/lucca/sandbox/output_supervisor.py) (`2,263` lines $\to$ **`<= 500` lines**)
3. [`src/lucca/core/cascade.py`](../../src/lucca/core/cascade.py) (`2,241` lines $\to$ **`<= 800` lines**)
4. [`src/lucca/reasoning/cegis_unshackled.py`](../../src/lucca/reasoning/cegis_unshackled.py) (`2,004` lines $\to$ **`<= 750` lines**; `cegis_python.py` `725` lines retired; `spatial_dsl` / `arc_primitives` wired)

**Commits in Phase 3:** `5` atomic commits (`Sub-steps 3.1` through `3.5`).

---

## 1. Sub-Step 3.1 — Deduplicate & Decompose `corroboration.py` (`2,407` $\to$ `<= 850` Lines; Net Deletion of `~1,185` Lines)

### 1.1 Exact Problem
In [`src/lucca/core/corroboration.py:697-2232`](../../src/lucca/core/corroboration.py), the 5 Walton critical-question evaluators (`_evaluate_authority_questions` `313` lines, `_evaluate_sign_questions` `301` lines, `_evaluate_analogy_questions` `328` lines, `_evaluate_consequence_questions` `304` lines, `_evaluate_precedent_questions` `271` lines = **`1,535` lines**) are 80% copy-pasted clones of the same 3 procedural blocks:
1. Concatenating receipt text (`str(getattr(r, "output", "") or "") + ...`, repeated **15 times**) + calling `compute_proposition_alignment` + fallback SQL query on `memories JOIN provenance_envelopes`.
2. Independent corroboration lookup (`SELECT m.entry_id, m.content, e.signer_id, e.payload_json FROM memories m JOIN provenance_envelopes e ...`, parsing `json.loads(payload_json_str)`, checking `verify_source_independence`, repeated **5 times**).
3. Dispute / counter-evidence lookup across `receipts` and `memories` (repeated **5 times**).

### 1.2 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `src/lucca/core/walton_schemes/__init__.py` & `src/lucca/core/walton_schemes/evaluators.py` (new) | 1. Write 3 shared, parameterized helper functions (`~180` lines total):<br>  – `extract_normalized_receipt_text(receipt: object) -> str`<br>  – `collect_independent_corroboration(claim: str, like_patterns: Sequence[str], step: InferenceStep, store: object, receipts: Sequence[object], verifier: SemanticVerifierPort | None, initial_sources: Sequence[str], initial_signers: Sequence[str]) -> tuple[list[str], list[str]]`<br>  – `collect_dispute_evidence(claim: str, sql_like_clauses: Sequence[tuple[str, Sequence[str]]], receipt_predicate: Callable[[str, float, bool], bool], step: InferenceStep, store: object, receipts: Sequence[object], verifier: SemanticVerifierPort | None) -> tuple[list[str], list[str], list[str]]`<br>2. Express `_evaluate_authority_questions`, `_evaluate_sign_questions`, `_evaluate_analogy_questions`, `_evaluate_consequence_questions`, and `_evaluate_precedent_questions` using those 3 shared helpers (`~50–70` lines per scheme = `~300` lines total instead of `1,535` lines). |
| `src/lucca/core/corroboration.py` | Import and re-export the 5 `_evaluate_*_questions` functions from `lucca.core.walton_schemes.evaluators` so all existing callers and unit tests importing from `lucca.core.corroboration` work without modification. `corroboration.py` drops from `2,407` lines to **`<= 850` lines**. |
| `tests/test_static_gates.py` | Add `test_corroboration_loc_and_walton_parity_gate()` asserting `corroboration.py <= 850` lines and `evaluators.py <= 550` lines (enforcing the net `~1,100+` line deduplication permanently). |

### 1.3 Verification (Sub-Step 3.1)
```powershell
uv run pytest tests/ -k "corroboration or walton or defeasible" -q
uv run pytest tests/test_static_gates.py -q
uv run lint-imports
uv run pytest tests/ -q -m "not tier2 and not hw and not soak"
```

---

## 2. Sub-Step 3.2 — Deduplicate & Decompose `output_supervisor.py` (`2,263` $\to$ `<= 500` Lines)

### 2.1 Exact Problem
[`src/lucca/sandbox/output_supervisor.py`](../../src/lucca/sandbox/output_supervisor.py) (`2,263` lines) mixes:
- `L283–809` (`527` lines): static verb-stem dictionaries (`EXPANDED_STEM_MAP`) and 25 compiled regex globals (many duplicated in `coherence.py` and `neural_claim_verifier.py`).
- `ActionClaimGrammarSupervisor` (`L953–1496`, `544` lines).
- `TruthInReceiptMatcher` (`L1499–1900`, `402` lines) and `CitationProvenanceMatcher` (`L1937–2042`, `106` lines).
- `DeonticAssertionMatcher` (`L122–278`, `157` lines) and `OutputSupervisorSession` (`L2045–2263`, `219` lines).

### 2.2 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `src/lucca/sandbox/supervisor_lexicon.py` (new) | Move `EXPANDED_STEM_MAP`, verb stem helpers, and compiled regex constants (`L283–809`) into `supervisor_lexicon.py`, deduplicating shared verb stems with `coherence.py`. |
| `src/lucca/sandbox/action_claim_grammar.py` (new) | Move `ActionClaimGrammarSupervisor` (`L953–1496`) and its helper dataclasses into `action_claim_grammar.py`. |
| `src/lucca/sandbox/receipt_truth_matcher.py` (new) | Move `TruthInReceiptMatcher` and `CitationProvenanceMatcher` (`L1499–2042`) into `receipt_truth_matcher.py`. |
| `src/lucca/sandbox/output_supervisor.py` | Retain `OutputSupervisorSession`, `DeonticAssertionMatcher`, and explicit `__all__` re-exports of every moved symbol so all external imports (`from lucca.sandbox.output_supervisor import ...`) remain 100% backwards-compatible. `output_supervisor.py` drops from `2,263` lines to **`<= 500` lines**. |
| `tests/test_static_gates.py` | Add `test_output_supervisor_loc_and_split_gate()` asserting `output_supervisor.py <= 500` lines. |

### 2.3 Verification (Sub-Step 3.2)
```powershell
uv run pytest tests/ -k "supervisor or coherence or matcher or wo40 or wo42" -q
uv run python scripts/eval_wo42_locked_holdout.py
# Expected: 150/150 (100.0%) on locked holdout, 0 regressions
```

---

## 3. Sub-Step 3.3 — Decompose `cascade.py` (`2,241` $\to$ `<= 800` Lines)

### 3.1 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `src/lucca/core/cascade_intent.py` (new) | Move `classify_epistemic_intent` (`L580–925`, `346` lines) and all epistemic intent regex/keyword pattern tables (`L250–579`, `~330` lines) into `cascade_intent.py`. |
| `src/lucca/core/cascade_substrates.py` (new) | Move the substrate query backend implementations (`query_substrate_self_history`, `query_substrate_0_telemetry`, `query_substrate_1_workspace`, `query_substrate_2_episodic`, `query_substrate_3_semantic`, `query_substrate_4_procedural`, `query_substrate_5_web`, `query_substrate_6_sandbox` = `~780` lines) into `CascadeSubstrateAdapters` in `cascade_substrates.py`. |
| `src/lucca/core/cascade.py` | Retain `EpistemicSubstrate`, `SubstrateHit`, `CascadeResult`, `EpistemicSearchCascade` orchestration + synthesis, and re-export `classify_epistemic_intent`. `cascade.py` drops from `2,241` lines to **`<= 800` lines**. |
| `tests/test_static_gates.py` | Add `test_cascade_loc_and_split_gate()` asserting `cascade.py <= 800` lines. |

---

## 4. Sub-Step 3.4 — Retire Superseded `cegis_python.py` (`-725` Lines) & Decompose `cegis_unshackled.py` (`2,004` $\to$ `<= 750` Lines)

### 4.1 Exact Problem
1. [`src/lucca/reasoning/cegis_python.py`](../../src/lucca/reasoning/cegis_python.py) (`725` lines) is an older `WO-35` v1 CEGIS loop with **zero callers in `src/lucca/`**; live code uses `UnshackledCEGISEngine` in `cegis_unshackled.py`.
2. [`src/lucca/reasoning/cegis_unshackled.py`](../../src/lucca/reasoning/cegis_unshackled.py) (`2,004` lines) mixes 2D grid diffing/ANSI rendering (`L92–424`, `333` lines), restricted Python sandbox execution (`L582–1074`, `493` lines), AST mutant generation (`L1168–1342`, `175` lines), and `UnshackledCEGISEngine` (`L1345–2004`, `660` lines).

### 4.2 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `src/lucca/reasoning/cegis_grid_diff.py` (new) | Move `ARC_PALETTE_NAMES`, `CellMismatch`, `GridDiff`, `compute_detailed_grid_diff`, `render_grid_ansi`, `render_grid_side_by_side` (`L92–424`, `333` lines) into `cegis_grid_diff.py`. |
| `src/lucca/reasoning/cegis_sandbox.py` (new) | Move `_build_restricted_cegis_globals`, `execute_unshackled_python`, `execute_unshackled_python_batch`, and timeout watchdog helpers (`L582–1074`, `493` lines) into `cegis_sandbox.py`. |
| `src/lucca/reasoning/cegis_mutator.py` (new) | Move `generate_ast_mutants` and AST mutation visitors (`L1168–1342`, `175` lines) into `cegis_mutator.py`. |
| `src/lucca/reasoning/cegis_unshackled.py` | Retain `UnshackledCEGISEngine`, `CEGISRunResult`, and backwards-compatible re-exports of moved symbols (plus compatibility aliases `PythonCEGISEngine`, `CEGISResult`, `CEGISTrace`, `parse_python_exception` so any test importing `cegis_python` can import from `cegis_unshackled`). Delete `src/lucca/reasoning/cegis_python.py` (`-725` lines). `cegis_unshackled.py` drops from `2,004` lines to **`<= 750` lines**. |
| `tests/test_static_gates.py` | Add `test_cegis_loc_and_split_gate()` asserting `cegis_unshackled.py <= 750` lines and `not (repo_root / "src/lucca/reasoning/cegis_python.py").exists()`. |

---

## 5. Sub-Step 3.5 (Behavioral Organ Activation) — Wire Spatial DSL (`spatial_dsl.py`, `spatial_scheme.py`, `arc_primitives.py`, `repl_loop.py`) & Relational Modules (`mereo.py`, `realize_real.py`, `math_primitives.py`, `universal_primitives.py`) Into `cegis_sandbox.py` and `SchemeEvaluator`

### 5.1 Exact Problem
[`src/lucca/router/heuristic.py:553-575`](../../src/lucca/router/heuristic.py) sets `exposed_libraries = ["arc_primitives"]` and `solver_tool = "arc_primitives"` on 2D spatial/grid prompts, **but `cegis_sandbox.py` (`_build_restricted_cegis_globals`) and `SchemeEvaluator` (`build_env`) never inject `arc_primitives`, `spatial_dsl`, `spatial_scheme`, `math_primitives`, `universal_primitives`, or `mereo`!**

### 5.2 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `src/lucca/reasoning/cegis_sandbox.py` | In `_build_restricted_cegis_globals(exposed_libraries: Sequence[str] | None = None)`: when `"arc_primitives"` or `"spatial_dsl"` is requested (or when `input_grid` is a 2D `list[list[int]]`), expose the pure functions from `lucca.reasoning.arc_primitives`, `lucca.reasoning.spatial_dsl`, `lucca.reasoning.spatial_scheme`, and `lucca.reasoning.relational.mereo` inside the sandboxed globals dictionary. |
| `src/lucca/reasoning/scheme/prims.py` & `src/lucca/reasoning/scheme/eval.py` | Register the pure primitives from `math_primitives.py`, `universal_primitives.py`, `skills.py`, and `relational/realize_real.py` into `build_env()` so MicroScheme evaluation has access to the complete primitive library in live turns. |
| `src/lucca/admin.py` | Wire a `lucca-admin repl` CLI subcommand invoking `lucca.reasoning.repl_loop` (`TaskRegistry` / interactive CEGIS REPL) so `repl_loop.py` is directly accessible from the admin CLI entrypoint. |
| `tests/unit/test_spatial_and_scheme_wiring.py` (new) | Add unit tests verifying that 2D grid synthesis tasks in `execute_unshackled_python` can call `arc_primitives` (`get_objects`, `rotate_90`, `gravity_drop`) and `spatial_dsl` (`analyze_symbolic_invariants`, `crop_grid`), and that `SchemeEvaluator` resolves `math_primitives` and `universal_primitives`. |

### 5.3 Expected Runtime Differences When Online
- **2D Spatial & Mathematical Primitives Available in Sandbox Synthesis:** When Lucca synthesizes Python or MicroScheme code for grid, geometry, or symbolic math tasks, the sandbox no longer has to reinvent flood-fill, connected-component labeling, bounding boxes, or mereotopological relations (`RCC-8` in `mereo.py`) from scratch in raw loops—those tested primitives are pre-bound in the restricted sandbox globals.

---

## 6. Phase 3 Independent Subagent Audit Gate (Mandatory STOP Before Phase 4)

Spawn a read-only `research` subagent to verify:
1. All 4 domain god-objects meet their hard LOC ceilings (`corroboration.py <= 850`, `output_supervisor.py <= 500`, `cascade.py <= 800`, `cegis_unshackled.py <= 750`).
2. `cegis_python.py` (`725` lines) is removed and `~1,185` lines of duplicate loops in `corroboration.py` are eliminated.
3. `spatial_dsl.py`, `spatial_scheme.py`, `arc_primitives.py`, `repl_loop.py`, `mereo.py`, `realize_real.py`, `math_primitives.py`, and `universal_primitives.py` are wired into the runtime/CLI.
4. `scripts/eval_wo42_locked_holdout.py` scores `150/150` (`100.0%`) and the full `pytest` + `lint-imports` suites pass.
