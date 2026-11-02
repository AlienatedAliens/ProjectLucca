# WO-28 — Version 1.3: Structural Compiler & Neurosymbolic Execution Architecture (The Regex Purge & Multi-Rung Ablation Ladder)

**Date:** 2026-09-30  
**Target Release:** Project Lucca Version 1.3.0  
**Audience:** Implementing engineers and autonomous coding agents. Every phase specifies exact files, exact architectural transformations, strict functional acceptance criteria, explicit failure traps, and mandatory STOP gates.  
**Reviewer Notes Status:** **Ratified and Governing.** All instructions in the Reviewer Advisory Notes below are binding constraints.

---

## 0. Governing Reviewer Advisory Notes

```
REVIEWER NOTES FOR WO-28 (advisory, governing constraints from an outside review)

Context: The goal is to improve Lucca's real-world reliability, not to maximize
a benchmark score. Where a note conflicts with the WO, raise it at the relevant
STOP gate and let the owner decide. Do not silently deviate. At each gate state
what was verified, what was NOT verified, and where you disagreed with these
notes. Prefer "not verified" over implied success.

REVISED SEQUENCE
 Phase 0: Baseline, git safety, pinned known failures, fresh held-out frozen
 Phase 1: Tolerant extraction + AST sanitizer (was Phase 2)
 Phase 2: GBNF grammars, CONDITIONAL on measured extraction residual
 Phase 3: Unified execution-feedback loop (merges old Phase 5 with WO-26 Phase 4)
 Phase 4: Grader recalibration (numeric fast path + sandboxed SymPy)
 Phase 5: Router / sanity_guard changes, CONDITIONAL on replay evidence
 Phase 6: Ablation ladder + fresh held-out evaluation

GLOBAL RULES
1. One variable per rung. Context size (16K vs 32K) is its own rung. Run v1.3
   at 16K first to isolate the architectural delta. Measure VRAM with nvidia-smi
   at each context size. The earlier 12.1-12.4 GiB at 16K conflicts with the
   "~10 GiB at 32K" figure in the draft, so trust measurements, not estimates.
2. Dev vs held-out discipline.
   - The 400 MATH-500 problems and the 164 HumanEval-Plus problems are now DEV
     sets (audited, and tuned against in WO-26). Use them for before/after
     deltas only. Do not claim generalization from them.
   - Generalization claims require FRESH problems: e.g. a random slice from the
     MATH test pool outside MATH-500, drawn and frozen BEFORE looking at
     results, with the seed and IDs recorded. Report N and a confidence
     interval.
   - The 47 logged failure traces are also dev data. Split them: design against
     ~30, hold out ~17 for the final check.
3. Measurement changes get re-baselined. Any grader change requires re-scoring
   v1.2 under the identical grader. Never compare across graders.
4. Pin the known-failing baseline tests by test ID in Phase 0. "1066+ passed"
   is ambiguous without the failing list.
5. Record harness config in every report: prompts, decoding params, token
   budget, context size, grader version, git SHA.
6. Tag each commit by layer (extraction / grammar / feedback / grader /
   router / guard). Do not fix benchmark label artifacts.
7. The 284 regex count is not a goal. Scope regex removal to the three observed
   failure clusters (tool/code extraction, sanity_guard false rejections,
   router keyword collisions). Do not purge working regexes for their own sake.
```

---

## 1. Problem Analysis & Forensic Evidence

### 1.1 The Forensic Problem: Three Failure Clusters
A comprehensive static code audit across `ProjectLucca/src/` revealed 284 raw regular expression invocations. Per the governing notes, our focus is strictly scoped to the **three failure clusters** responsible for real-world defects:
1. **Cluster A: Tool & Code Extraction Drops (`cascade.py`, `turn_pipeline.py`):**
   - In our 400-problem held-out trial, **83.1% of failures were runtime formatting or syntax crashes**, not fundamental math logic errors.
   - **24.5% of misses** in the feedback run were empty-code extractions (markdown fence drops, leading thought tags, or unclosed backticks causing empty strings to be sent to Docker).
2. **Cluster B: Sanity Guard False Rejections (`sanity_guard.py`):**
   - Hardcoded regex heuristics (e.g. `r"divisible by (\d+)"` and `r"(\d+)\s*years? of age"`) attempting to police physical assertions caused false-positive blocks on valid reasoning.
3. **Cluster C: Router Keyword Collisions (`heuristic.py`):**
   - 17 keyword patterns like `r"\b(read|view|show|cat)\b"` caused semantic misrouting whenever everyday conversation touched technical vocabulary.

### 1.2 The Forensic Recovery Evidence
- When the 2-turn Docker execution feedback loop was triggered on valid code, the model recovered **35 out of 47 crashes (74.47% recovery rate)**.
- Therefore, eliminating empty extractions and unifying the feedback loop directly targets the primary failure mode of the system.

---

## 2. Phase-by-Phase Implementation Plan

```
   ┌────────────────────────────────────────────────────────┐
   │ Phase 0: Baseline, Git Safety & Fresh Held-Out Freeze  │
   └──────────────────────────┬─────────────────────────────┘
                              │
   ┌──────────────────────────▼─────────────────────────────┐
   │ Phase 1: Tolerant Extraction + AST Sanitizer           │
   └──────────────────────────┬─────────────────────────────┘
                              │
   ┌──────────────────────────▼─────────────────────────────┐
   │ Phase 2: GBNF Grammars (CONDITIONAL on residual)       │
   └──────────────────────────┬─────────────────────────────┘
                              │
   ┌──────────────────────────▼─────────────────────────────┐
   │ Phase 3: Unified Execution-Feedback Loop (Cap <= 2)    │
   └──────────────────────────┬─────────────────────────────┘
                              │
   ┌──────────────────────────▼─────────────────────────────┐
   │ Phase 4: Grader Recalibration & v1.2 Re-Baseline       │
   └──────────────────────────┬─────────────────────────────┘
                              │
   ┌──────────────────────────▼─────────────────────────────┐
   │ Phase 5: Router & Sanity Guard (CONDITIONAL on replay) │
   └──────────────────────────┬─────────────────────────────┘
                              │
   ┌──────────────────────────▼─────────────────────────────┐
   │ Phase 6: Ablation Ladder & Fresh Held-Out Evaluation   │
   └────────────────────────────────────────────────────────┘
```

---

### Phase 0 — Baseline, Git Safety, Pinned Failures & Fresh Held-Out Freeze

**Goal:** Cleanly commit all baseline modifications on `master`, record verified baseline test suite counts, document pinned known failures by ID, freeze the fresh held-out benchmark set, and verify that `v1.2.0-baseline` remains 100% cleanly checkoutable.

**Manifest:**
- Staged / Modified files:
  - `src/lucca/sandbox/ast_sanitizer.py`, `src/lucca/core/pipeline_tracer.py`, `tests/test_ast_sanitizer.py`
  - `src/lucca/core/affect.py`, `src/lucca/core/affective_ode.py`, `src/lucca/core/orchestrator.py`
  - `tests/test_trace.py`, `tests/test_honesty_guard.py`, `tests/test_brain_config_driven.py`
  - `plans/2026-09-29_wo27_affective_manifold_and_frontier_voice_frozen.md`
  - `plans/2026-09-30_wo28_v1_3_structural_compiler_and_neurosymbolic_execution.md`
- Fresh Held-Out Benchmark Dataset:
  - Script: `scripts/freeze_fresh_heldout_dataset.py`
  - Target: `data/benchmarks/math_fresh_heldout_500.jsonl` (drawn from `HuggingFaceTB/MATH` test set excluding MATH-500, with seed `20260930`).
- Hardware Telemetry (via `nvidia-smi` live):
  - Memory Used: **10,212 MiB** (~9.97 GiB)
  - Memory Free: **5,792 MiB** (~5.66 GiB)
  - Memory Total: **16,303 MiB** (~15.92 GiB)
  - Context Size: 32,768 tokens (Q8_0 KV cache + Flash Attention)

**Pinned Known Baseline Test Failures (2 total):**
1. `tests/test_packaging.py::test_frozen_binary_version_flag`
   - *Reason:* Asserts version `1.3.0` in output of `dist/Lucca/Lucca.exe --version`, which outputs `0.2.0` because the standalone PyInstaller executable has not been recompiled.
2. `tests/test_rule_induction.py::test_live_induction_production_log_clusters_gt_zero`
   - *Reason:* The production database `C:\ProjectLucca\data\memory.sqlite` currently contains 0 mined clusters.
*(67 tests deselected under `-k "not live_hw"`; all other **1,066 tests pass**).*

**Functional Acceptance:**
- Working tree is 100% clean (`git status` shows zero uncommitted changes).
- Commit created on `master` with tag `[layer: baseline]`.
- `git checkout v1.2.0-baseline` succeeds cleanly with zero file collisions.
- `git checkout master` returns cleanly to v1.3 head.
- `data/benchmarks/math_fresh_heldout_500.jsonl` generated and frozen with seed `20260930`.

**STOP Gate 0:** Present clean git status, pinned failure list, live `nvidia-smi` output, and fresh dataset hash to owner before Phase 1.

---

### Phase 1 — Tolerant Extraction + AST Sanitizer

**Goal:** Eliminate the 24.5% empty-code drops on the dev set without complex grammars by implementing a tolerant multi-stage fallback extractor and AST-level operator normalization.

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `src/lucca/sandbox/ast_sanitizer.py` | Implement multi-stage tolerant extractor `extract_python_code_tolerant(raw_text: str) -> str`: <br>1. Standard fenced markdown block (` ```python ... ``` `).<br>2. Unfenced indented or top-level code block.<br>3. Longest continuous slice that successfully parses via `ast.parse()`.<br>4. If code is still empty, flag `extraction_empty = True` and trigger 1 immediate retry.<br>5. Never pass empty string to Docker sandbox. | `[layer: extraction]` |
| `src/lucca/sandbox/ast_sanitizer.py` | Token-level operator repair via Python `tokenize` (normalize implicit multiplication `2 * x` and `^` $\to$ `**` while strictly preserving string literals like `"^"` and comments). | `[layer: extraction]` |
| `scripts/run_modern_2024_benchmarks.py` | Wire `extract_python_code_tolerant` into benchmark execution loop; log empty-code counter explicitly. | `[layer: extraction]` |
| `tests/test_ast_sanitizer.py` | Unit tests for all fallback stages, string literal preservation, and empty extraction retry flag. | `[layer: test]` |

**Functional Acceptance:**
- Evaluate empty-code rate before and after on the 47 known failure traces / dev set.
- Target: Residual empty-code drop rate drops from 24.5% to $<5\%$.
- String literals (`"^"`, `"x*y"`) inside strings and comments remain 100% untouched.
- Unit tests pass cleanly.

**STOP Gate 1:** Report the before/after empty-code rate on the dev set. If residual is negligible ($<3\%$), propose skipping Phase 2. Commit Phase 1 (`[layer: extraction]`).

---

### Phase 2 — GBNF Grammars (CONDITIONAL on Measured Extraction Residual)

**Goal:** If and only if Phase 1 leaves a material empty-code residual ($>5\%$), deploy GBNF grammars inside `llama-server` to constrain logits directly in C++.

**Manifest (Conditional):**
| File | Action | Layer |
|---|---|---|
| `src/lucca/sandbox/gbnf_engine.py` | GBNF grammar definition for structured code and tool-call JSON schemas. | `[layer: grammar]` |
| `src/lucca/brain/llm_client.py` | Support `grammar` payload to `/v1/chat/completions`. | `[layer: brain]` |
| `scripts/test_grammar.py` | Measure per-token CPU latency and tokens/sec with and without grammar on identical prompts. | `[layer: test]` |

**Governing Rules & Traps:**
- Proceed ONLY if Phase 1 leaves a material residual.
- Measure tokens/sec overhead; do NOT assume 0ms added latency.
- Do not constrain open-ended conversational turns (chat/chit-chat).
- Track token-budget truncation separately (grammars do not fix budget exhaustion).

**STOP Gate 2:** Report residual justification, tokens/sec benchmark, and A/B pass rate before committing Phase 2 (`[layer: grammar]`).

---

### Phase 3 — Unified Execution-Feedback Loop (Cap $\le 2$ Rounds)

**Goal:** Reconcile WO-26 Phase 4 preflight verification and Tier 3 execution feedback into ONE unified self-repair mechanism with a hard cap of 2 repair rounds total.

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `src/lucca/core/orchestrator.py` & `turn_pipeline.py` | Merge preflight docstring assertions and post-execution sandbox failures into a single feedback handler. Cap total repair turns to $\le 2$. | `[layer: feedback]` |
| `src/lucca/sandbox/service.py` | Provide structured error payload to the repair turn: `(traceback, stdout, original_spec_examples)`. Run docstring/spec examples as formal assertions. | `[layer: feedback]` |
| `src/lucca/core/pipeline_tracer.py` | Nanosecond telemetry tracking repair round count, recovery status, and attempt diffs. | `[layer: telemetry]` |
| `tests/test_execution_feedback.py` | Evaluate on the **47 logged real failure traces** split into **30 design traces** and **17 held-out traces**. | `[layer: test]` |

**Functional Acceptance:**
- Recovery rate on the 30 design traces meets or exceeds baseline 74.47% (35/47).
- Verify zero instances where self-repair converts a correct answer into an incorrect one.
- Hard cap of 2 rounds strictly enforced (fail-open returns best code with warning).
- Added latency for voice turn measured and reported.

**STOP Gate 3:** Report recovery rate on 30 design traces and 17 held-out traces. Commit Phase 3 (`[layer: feedback]`).

---

### Phase 4 — Grader Recalibration & v1.2 Re-Baseline

**Goal:** Deploy a mathematically sound, non-hanging evaluation pipeline (normalized string match $\to$ random numeric evaluation $\to$ sandboxed SymPy with 2.0s timeout) and re-score the v1.2 baseline under the exact same grader.

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `scripts/run_modern_2024_benchmarks.py` | Implement 3-stage grader: <br>1. Normalized LaTeX/string match.<br>2. Fast-path numeric check at 5 random points ($x \in \{2, 3, 5, 7, 11\}$).<br>3. Sandboxed SymPy algebraic difference ($f(x) - g(x) == 0$) with strict 2.0s timeout. | `[layer: grader]` |
| `scripts/rescore_with_sympy.py` | Re-score v1.2 baseline held-out 400 checkpoint under the new grader to establish apples-to-apples baseline. | `[layer: evaluation]` |
| `tests/test_cas_grading.py` | Unit tests for grader timeout, division by zero protection, and algebraic equivalence. | `[layer: test]` |

**Functional Acceptance:**
- Grader never hangs on complex expressions (2.0s timeout enforced).
- Hand-audit 30 newly accepted answers from the re-scored baseline; report false-accept rate.
- Document exact v1.2 baseline score under new grader.

**STOP Gate 4:** Present re-scored v1.2 baseline and false-accept audit to owner. Commit Phase 4 (`[layer: grader]`).

---

### Phase 5 — Router & Sanity Guard Changes (CONDITIONAL on Replay Evidence)

**Goal:** Replay logged real turns through the proposed ONNX semantic router and sanity guard to determine whether changes are justified by evidence.

**Manifest (Conditional):**
| File | Action | Layer |
|---|---|---|
| `scripts/replay_logged_turns.py` (new) | Replay production SQLite turns through current vs proposed router; measure agreement and false-rejection rate. | `[layer: router]` |
| `src/lucca/router/semantic_router.py` | ONNX `bge-small-en-v1.5` router on CPU (if justified). Heuristics retained as fallback/tiebreaker. | `[layer: router]` |
| `src/lucca/core/sanity_guard.py` | Downgrade brittle regex rules to warnings or tool-verification triggers rather than outright rejections. | `[layer: guard]` |

**Governing Rules:**
- Skip this phase entirely if replay shows router/guard errors are rare on production logs.
- Measure actual ONNX latency on CPU (cold and warm) before setting latency gates.

**STOP Gate 5:** Report replay agreement and false-rejection rate. Commit Phase 5 (`[layer: router]`) if justified, or formally document skip.

---

### Phase 6 — Ablation Ladder & Fresh Held-Out Evaluation

**Goal:** Execute the full ablation ladder on the dev set, followed by the definitive evaluation of the final configuration on the fresh held-out dataset.

**Ablation Ladder Protocol:**
$$\begin{array}{rll}
\text{Rung 0a:} & \text{v1.2 Baseline (16K ctx, Old Grader)} & \text{[Dev-400 Set]} \\
\text{Rung 0b:} & \text{v1.2 Baseline (16K ctx, Recalibrated Grader)} & \text{[Dev-400 Set]} \\
\text{Rung 1:} & \text{+ Tolerant AST Extractor} & \text{[Dev-400 Set]} \\
\text{Rung 2:} & \text{+ (Conditional) GBNF Grammar} & \text{[Dev-400 Set]} \\
\text{Rung 3:} & \text{+ Unified 1-Shot Feedback Loop} & \text{[Dev-400 Set]} \\
\text{Rung 4:} & \text{+ (Conditional) Router / Guard Update} & \text{[Dev-400 Set]} \\
\text{Rung 5:} & \text{+ 32K Context Expansion (Isolated variable)} & \text{[Dev-400 Set]} \\
\hline
\mathbf{\text{Final Rung:}} & \mathbf{\text{Final v1.3 Configuration on Fresh Held-Out 500}} & \mathbf{\text{[Unseen Fresh Set]}}
\end{array}$$

**Functional Acceptance:**
- Complete ablation scorecard documented with error categorization (extraction, crash, wrong math, grader disagreement, truncation).
- Fresh held-out evaluation executed with zero prior exposure, reporting accuracy, sample count $N$, and 95% confidence intervals.
- Regression check on canonical BBH and SPEC-100 to ensure core persona and reasoning invariants remain intact.
- Tag final release as `v1.3.0`.
