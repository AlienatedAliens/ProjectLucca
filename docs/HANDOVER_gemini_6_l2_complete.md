# Handover #6 — Studio Build: Rung L2 Complete (Shadow Telemetry Upgrades)

**To:** Zoo (Fable 5.1, architect) & Project Lucca Team  
**From:** Gemini (implementation)  
**Date:** 2026-09-21  
**Spec of record:** [`docs/specs/STUDIO_CAPABILITY_ROADMAP.md`](./specs/STUDIO_CAPABILITY_ROADMAP.md) v1.1.2 §6.2, §9, §13  
**Scope Delivered:** Ladder rung **L2** (Dream-RSI Replay-Before-Shadow, Contrastive Shadow Logging, Wilson/McNemar Telemetry Statistics, Orchestrator Wiring, Admin CLI & LISP Studio UI).

---

## 1. Summary of Deliverables

### 1.1 Dream-RSI Replay Engine & Zero Synthetic Padding Invariant
- **Implementation:** [`src/lucca/reasoning/replay.py`](../src/lucca/reasoning/replay.py) (`ReplayEngine`, `ReplayReport`).
- **Data Source of Record:** Historical interaction episodes are reconstructed loss-free from SQLite `decisions.features_json` + `user_interrupted` (as established in architectural audit; `TurnTrace` is purely latency profiling and contains no transcripts/entities under Lucca's privacy posture).
- **Strict Invariant Enforced:** Zero synthetic padding. A candidate rule evaluated offline requires $N_{\text{real}} \ge 50$ real recorded interaction turns, 0 runtime exceptions/gas exhaustions, and 0 misfires (such as firing on `intent="dangerous"`). If $N_{\text{real}} < 50$ (as in production currently, where $N=2$), the gate fails closed with `INSUFFICIENT_HISTORY: N_real < 50` and candidate rules remain safely in `QUARANTINE`.
- **Promotion & Approval Gate:** [`RuleLifecycleManager.promote_if_eligible`](../src/lucca/reasoning/lifecycle.py) and [`approve_rule`](../src/lucca/reasoning/lifecycle.py) evaluate `replay_candidate` on induced candidate rules and refuse promotion if offline replay has not passed.

### 1.2 Contrastive Shadow Logging & ModularRSI Agreement Logic
- **Database Schema:** [`src/lucca/memory/migrations/0005_contrastive_shadow.sql`](../src/lucca/memory/migrations/0005_contrastive_shadow.sql) creates table `contrastive_shadow_logs` (`log_id`, `rule_id`, `trace_id`, `ts`, `rule_plan_json`, `core_action_json`, `agreed`, `rule_outcome_signal`, `core_outcome_signal`). Applied to test fixtures and runtime database `C:/ProjectLucca/data/memory.sqlite`.
- **Formal Agreement Predicate:** [`check_plan_and_core_agreement`](../src/lucca/reasoning/lifecycle.py) implements the ModularRSI §3.3 definition:
  1. *Tool Proposals:* Matches tool name and semantically validates all kwargs against core executed tools.
  2. *Yield-to-Core:* Agrees if the core handled the request conversationally (LLM narration/clarification) without a tool.
  3. *Pure Say:* Agrees if the core responded without tool dispatch.
- **Orchestrator Wiring:** [`src/lucca/core/orchestrator.py`](../src/lucca/core/orchestrator.py) saves `shadow_outcomes` during both voice (`_run_turn`) and text (`_run_text_turn`) turns, and persists paired contrastive logs with observable outcome signals in `_finalize_turn`.

### 1.3 Statistical Rigor & S1 Semantics Labeling
- **Implementation:** [`src/lucca/reasoning/stats.py`](../src/lucca/reasoning/stats.py).
- **Wilson Score Interval:** Two-tailed Wilson score confidence interval with Newcombe (1998, Method 4) continuity correction, clamped to $[0.0, 1.0]$.
- **Paired McNemar Test:** Exact two-tailed binomial test for small samples ($b + c < 25$), Edwards continuity-corrected $\chi^2$ (df = 1) for large samples ($b + c \ge 25$).
- **Doctrine & S1 Semantics:** All reliability rates derived from observable signals (`tool_exit_zero`, `pydantic_valid`, `operator_confirm`, `operator_correct`, `user_interrupted`) are explicitly labeled **Execution-Reliability Rate (S1)** ("the tool didn't crash / valid AST"), never conflated with task success ("it helped the user").

### 1.4 Admin CLI & LISP Studio UI Integration
- **Admin CLI ([`src/lucca/admin.py`](../src/lucca/admin.py)):**
  - `lucca-admin rules replay <rule_id>`: Runs Dream-RSI offline replay against the 50 most recent recorded episodes and prints structured pass/refusal diagnostics.
  - `lucca-admin rules report`: Displays Rich table of all registered rules, cluster counts with Wilson 95% intervals, contrastive agreement rates, discordant counts ($b$ rule-better, $c$ core-better), McNemar p-value, and S1 execution-reliability rates.
- **Studio UI ([`src/lucca/ui/settings_dialog.py`](../src/lucca/ui/settings_dialog.py)):**
  - Added dedicated **Shadow Telemetry & Contrastive Evaluation (Rung L2)** panel in Tab 4 (`λ LISP Studio`).
  - Includes "▶ Run Offline Replay (50 Episodes)" button with live status reporting, real-time Wilson confidence intervals, and explicit S1 disclaimer footer.

---

## 2. Verification & Test Evidence

### 2.1 Targeted L2 Test Suite (`tests/test_l2_replay_and_contrastive.py`)
9 dedicated unit and integration tests covering all acceptance criteria:
- `test_wilson_score_interval_mathematical_properties`: Validates $N=0, 50, 20$, boundary clamping, and continuity correction.
- `test_mcnemar_test_contingency`: Validates exact binomial ($p=0.00195$) and Edwards continuity-corrected $\chi^2$.
- `test_replay_insufficient_history_fails_closed`: Verifies $N_{\text{real}} < 50$ refuses replay without synthetic padding.
- `test_replay_passes_clean_rule_on_50_real_schema_episodes`: Validates replay pass across 50 real-schema turns with 0 errors.
- `test_replay_rejects_failing_or_buggy_rule`: Injected runtime errors and dangerous intent misfires fail replay.
- `test_contrastive_agreement_logic`: Validates paired plan equality across tool calls, yields, and static say actions.
- `test_contrastive_shadow_logging_and_summary`: Validates SQLite persistence and summary statistics generation.
- `test_candidate_promotion_requires_replay_pass`: Verifies quarantine promotion fails closed until 50 real episodes clear replay.
- `test_admin_rules_replay_and_report_cli`: End-to-end CLI execution of `replay` and `report`.

### 2.2 Test Run Results
- `uv run pytest tests/test_l2_replay_and_contrastive.py -v` → **9 passed in 0.79s**
- `uv run pytest tests/test_static_gates.py -q` → **10 passed in 2.21s** (Zero-`Any` across core, brain, reasoning, sandbox, and ui)
- `uv run pytest tests/test_frozen_regression_harness.py -q` → **9 passed in 0.47s**
- `uv run pytest tests/test_memory_db.py -q` → **17 passed in 12.18s**
- `uv run pytest tests -q` → **508 passed, 0 failed, 11 deselected in 94.74s**
- `uv run ruff check src tests` → **0 errors**
- `uv run ruff format --check src tests` → **clean (167 files)**

---

## 3. Files Modified and Created

| File | Status | Description |
|---|---|---|
| [`src/lucca/memory/migrations/0005_contrastive_shadow.sql`](../src/lucca/memory/migrations/0005_contrastive_shadow.sql) | **NEW** | Migration 5 creating `contrastive_shadow_logs` table and index |
| [`src/lucca/reasoning/stats.py`](../src/lucca/reasoning/stats.py) | **NEW** | Wilson score interval (Newcombe 1998) & Paired McNemar test |
| [`src/lucca/reasoning/replay.py`](../src/lucca/reasoning/replay.py) | **NEW** | Dream-RSI offline replay engine with zero synthetic padding |
| [`tests/test_l2_replay_and_contrastive.py`](../tests/test_l2_replay_and_contrastive.py) | **NEW** | Comprehensive 9-test suite for Rung L2 |
| [`src/lucca/memory/db.py`](../src/lucca/memory/db.py) | MODIFIED | Added `record_contrastive_shadow_log` and `list_contrastive_shadow_logs` |
| [`src/lucca/reasoning/lifecycle.py`](../src/lucca/reasoning/lifecycle.py) | MODIFIED | Added `check_plan_and_core_agreement`, `replay_candidate`, `log_contrastive_shadow_pair`, `get_contrastive_summary`, and wired replay into promotion |
| [`src/lucca/core/orchestrator.py`](../src/lucca/core/orchestrator.py) | MODIFIED | Track shadow outcomes in voice/text turns and persist paired contrastive logs in `_finalize_turn` |
| [`src/lucca/admin.py`](../src/lucca/admin.py) | MODIFIED | Added `rules replay <rule_id>` and `rules report` subcommands |
| [`src/lucca/ui/settings_dialog.py`](../src/lucca/ui/settings_dialog.py) | MODIFIED | Added Shadow Telemetry & Contrastive Evaluation panel in Tab 4 |
| [`tests/test_memory_db.py`](../tests/test_memory_db.py) | MODIFIED | Updated migration version assertion to 5 |

---

## 4. Next Step on the Studio Ladder
- **Rung L3 (Induction Viewer & Full Acceptance Test):**
  - Contrastive plain-English diffs: *"What Lucca does today"* vs *"What this rule will do"*.
  - Evidence display: the inducing historical turns shown verbatim alongside candidate.
  - Acceptance test: A rule Lucca induces herself from $\ge 3$ repeated interactions enters `QUARANTINE`, clears replay + 5 live shadow clusters with 0 errors, survives contrastive review, and is promoted by operator.

---

## 5. Zoo (Fable 5.1) Gate Review — 2026-09-21T15:35Z — **APPROVED after 3 fixes**

Independently re-verified: replay fails closed with `INSUFFICIENT_HISTORY` at N_real < 50 (no synthetic padding); `decisions.features_json` genuinely carries `transcript`/`entities` so replayed `RuleState`s are real; replay gate is scoped to `is_induced` (authored factory skills bypass, per spec §6.3); test bodies read — insufficient-history, 50-episode pass, runtime-error rejection, dangerous misfire, agreement cases, summary stats, promotion gate, CLI end-to-end all real.

| # | Severity | Finding | Fix (this commit) |
|---|---|---|---|
| G1 | Latent crash | `stats.py` called `math.erfcinv`, which does not exist in the stdlib — any non-standard `confidence` would raise `AttributeError` at runtime | Replaced with an 80-iteration bisection on `math.erfc`; invalid confidence raises `ValueError` |
| G2 | S1 semantics | Orchestrator labeled a no-tool, non-interrupted core turn `tool_exit_zero` — crediting the core with a tool success it never performed, inflating McNemar `c_ok` | No-tool turns now emit `abstained` (S1 Outcome enum); `tool_exit_zero` requires an actual tool execution |
| G3 | Spec §6.1 violation | `rules report` and the Studio panel displayed a Wilson CI on shadow-cluster counts — clusters are not iid Bernoulli trials, and §6.1 mandates the Rule-of-Three correction in Studio UI copy and promotion prompts | New `rule_of_three_ucl(n)` (exact one-sided bound `1 - 0.05^(1/n)`); both surfaces now show `n/5 (0 err -> fail <= X%)`; covered by `test_rule_of_three_ucl` |

Post-fix gates (real output): `ruff check src tests` clean; `ruff format --check` clean (167 files); targeted L2/lifecycle/memory/admin/frozen/static-gates 61 passed; full suite **509 passed, 0 failed, 11 deselected** (108.7 s).

Advisory (not blocking): `r_ok` in `get_contrastive_summary` counts `abstained` as rule reliability — a rule that yields every turn shows 100% execution-reliability. Defensible under the S1 label (abstention is not a crash) but worth a footnote when T4 builds the circuit breaker on these rates.
