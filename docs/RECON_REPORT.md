# RECON_REPORT.md: Phase 0 MicroScheme Reconnaissance

**Date:** 2026-09-21  
**Audience:** Human Architect & Fable 5.1 Audit Team  
**Scope:** Phase 0 Reconnaissance for Proposal: Seed Skill Library v1  
**Status:** Complete  

---

## 1. Done

1. **Test Suite Verification:** Executed both MicroScheme unit tests and rule induction test suites (`test_scheme.py`, `test_rule_induction.py`). Verified 28/28 tests passing.
2. **MicroScheme Primitives Audit:** Inspected [`src/lucca/reasoning/scheme/prims.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/scheme/prims.py) and extracted the exact catalog of all 20 pure primitives and 14 state predicates.
3. **`RuleState` Schema Audit:** Inspected [`src/lucca/core/schemas.py:286-300`](file:///C:/Projects/ProjectLucca/src/lucca/core/schemas.py#L286-L300) and extracted all 12 dataclass fields.
4. **Z3 SMT Verifier Translation Audit:** Inspected [`src/lucca/reasoning/smt_verifier.py:498-575`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/smt_verifier.py#L498-L575) and extracted all modeled predicates, unmodeled rejections, and deontic path rules.
5. **Static Validator Corpus Audit:** Inspected [`src/lucca/reasoning/scheme/validator.py:20-55`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/scheme/validator.py#L20-L55) to document the exact fixture generation logic and identify entity key traps.
6. **Tool Registry & Capability Manifest Audit:** Inspected [`src/lucca/core/capabilities.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/capabilities.py) and [`src/lucca/sandbox/policy.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/policy.py) to catalog live tools versus gated sandbox capabilities.
7. **Tool Whitelist Forensic Git Audit:** Inspected commit history (`git log -p`) of [`config/tool_whitelist.toml`](file:///C:/Projects/ProjectLucca/config/tool_whitelist.toml) to establish why only 2 apps are currently listed.
8. **Production Rule Database Audit:** Queried production SQLite state via `lucca-admin rules list` and inspected [`src/lucca/memory/migrations/0003_rules.sql`](file:///C:/Projects/ProjectLucca/src/lucca/memory/migrations/0003_rules.sql).

---

## 2. Not Done

1. **No Candidate Rules Authored (Phase 1/2):** Zero MicroScheme rules were written or registered to database tables. Execution halted per phase gate instructions.
2. **No Verifier or Code Modifications:** Preserved verifier, whitelist, supervisor, thresholds, and sandbox intact per Ground Rule 3.
3. **No Database Schema Alterations:** Preserved migration 0003 intact.

---

## 3. Evidence (Commands Run and Ground Truth Findings)

### 3.1 Test Suite Execution Evidence
```text
Command: & C:\Projects\ProjectLucca\.venv\Scripts\python.exe -m pytest tests/test_scheme.py tests/test_rule_induction.py -v

============================= test session starts =============================
platform win32 -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
collected 28 items

tests/test_scheme.py::test_t_lisp_01_sample_rule_parses PASSED           [  3%]
tests/test_scheme.py::test_t_lisp_02_limits_exceeded PASSED              [  7%]
tests/test_scheme.py::test_t_lisp_03_parser_o_n PASSED                   [ 10%]
tests/test_scheme.py::test_t_lisp_04_syntax_errors_have_location PASSED  [ 14%]
tests/test_scheme.py::test_t_lisp_05_if_arity_checked_at_parse_time PASSED [ 17%]
tests/test_scheme.py::test_t_lisp_06_hypothesis_random_token_soup PASSED [ 21%]
tests/test_scheme.py::test_t_lisp_07_evaluator_catches_all_primitive_errors PASSED [ 25%]
tests/test_scheme.py::test_t_lisp_08_memory_bomb_and_overflow_guards PASSED [ 28%]
tests/test_scheme.py::test_t_lisp_09_define_and_shadowing_forbidden PASSED [ 32%]
tests/test_scheme.py::test_t_rule_01_sample_rule_execution PASSED        [ 35%]
tests/test_scheme.py::test_t_rule_08_static_validation_rejections PASSED [ 39%]
tests/test_scheme.py::test_plan_error_preserves_fired PASSED             [ 42%]
tests/test_rule_induction.py::test_mine_patterns_from_sqlite PASSED      [ 46%]
tests/test_rule_induction.py::test_synthesize_canonical_microscheme_rule PASSED [ 50%]
tests/test_rule_induction.py::test_induce_and_quarantine_invariant PASSED [ 53%]
tests/test_rule_induction.py::test_no_duplicate_induction PASSED         [ 57%]
tests/test_rule_induction.py::test_egraph_congruence_closure PASSED      [ 60%]
tests/test_rule_induction.py::test_first_order_anti_unification PASSED   [ 64%]
tests/test_rule_induction.py::test_anti_unify_many_and_macro_synthesis PASSED [ 67%]
tests/test_rule_induction.py::test_smt_verifier_valid_rule PASSED        [ 71%]
tests/test_rule_induction.py::test_smt_verifier_rejects_unsat_precondition PASSED [ 75%]
tests/test_rule_induction.py::test_smt_verifier_rejects_tautology_precondition PASSED [ 78%]
tests/test_rule_induction.py::test_smt_verifier_rejects_path_traversal PASSED [ 82%]
tests/test_rule_induction.py::test_smt_verifier_rejects_system_directory PASSED [ 85%]
tests/test_rule_induction.py::test_smt_verifier_rejects_prohibited_executable_extension PASSED [ 89%]
tests/test_rule_induction.py::test_smt_verifier_rejects_unknown_tool PASSED [ 92%]
tests/test_rule_induction.py::test_inducer_rejects_unsafe_candidate_at_smt_gate PASSED [ 96%]
tests/test_rule_induction.py::test_inducer_macro_synthesis_across_clusters PASSED [100%]

============================= 28 passed in 1.38s ==============================
```

### 3.2 Production Rules Table Evidence
```text
Command: & C:\Projects\ProjectLucca\.venv\Scripts\python.exe -m lucca.admin rules list
Output: No rules currently registered in the database.
```

---

## 4. Physical Code Ground Truth

### 4.1 MicroScheme Language Primitives (`prims.py`)
`PURE_PRIMITIVES` (lines 477–498) and `make_state_primitives` (lines 240–374):

| Identifier | Kind | Arity | Semantics / Behavior | Modeled in Z3? |
|---|---|---|---|:---:|
| `+` | Pure Math | $\ge 2$ | Variadic number addition | Yes (binary) |
| `-` | Pure Math | $\ge 2$ | Variadic number subtraction | Yes (binary) |
| `*` | Pure Math | $\ge 2$ | Variadic number multiplication | **No** (`UNMODELED`) |
| `/` | Pure Math | $\ge 2$ | Variadic division (raises on zero) | **No** (`UNMODELED`) |
| `=` | Comparison | 2 | Equality check | Yes |
| `<` | Comparison | 2 | Numeric less-than | Yes |
| `>` | Comparison | 2 | Numeric greater-than | Yes |
| `<=` | Comparison | 2 | Numeric less-than-or-equal | Yes |
| `>=` | Comparison | 2 | Numeric greater-than-or-equal | Yes |
| `not` | Logic | 1 | Truth negation (only `#f` is false) | Yes |
| `len` | Sequence | 1 | String or list length | **No** (`UNMODELED`) |
| `str-contains?` | String | 2 | Substring existence check | **No** (`UNMODELED`) |
| `str-lower` | String | 1 | Lowercases string | **No** (`UNMODELED`) |
| `min` | Math | $\ge 1$ | Minimum numeric argument | **No** (`UNMODELED`) |
| `max` | Math | $\ge 1$ | Maximum numeric argument | **No** (`UNMODELED`) |
| `list` | Construction| Variadic | Constructs Scheme list (max 256) | Yes (Plan parsing) |
| `say` | Action | 1 | Constructs `Say(text=...)` | Yes |
| `tool` | Action | Variadic | Constructs `ToolCall(tool, kwargs)` | Yes (Deontic SMT) |
| `yield-to-core` | Control Signal | $\ge 1$ | Raises `SchemeYieldSignal` | **No** (`UNMODELED`) |
| `interrupt-core` | Control Signal| $0-1$ | Raises `SchemeInterruptSignal` | **No** (`UNMODELED`) |
| `intent=` | State Predicate| 1 | Compares `state.intent == arg` | Yes |
| `entity-has?` | State Predicate| 2 | Checks if `arg2 in state.entities[arg1]` | Yes |
| `entity` | State Predicate| 1 | Returns `state.entities.get(arg1, [])` | **No** (`UNMODELED`) |
| `entity-int` | State Accessor | 1 | Casts first entity to int (raises if absent) | Yes |
| `entity-num` | State Accessor | 1 | Casts first entity to float (raises if absent)| **No** (`UNMODELED`) |
| `entity-str` | State Accessor | 1 | Returns first entity as string ("" if absent) | Yes |
| `transcript-has?` | State Predicate| 1 | Checks if substring is in transcript | Yes |
| `transcript-matches-glob?`| State Predicate| 1 | Glob matching over transcript | **No** (`UNMODELED`) |
| `app-running?` | State Predicate| 1 | Checks if app name is in `apps_running` | Yes |
| `hour-between?`| State Predicate| 2 | Checks `h1 <= state.hour_local <= h2` | Yes |
| `weekday?` | State Predicate| 1 | Checks `state.weekday == day` | Yes |
| `last-tool-ok?`| State Predicate| 0 | Checks `bool(state.last_tool_ok)` | Yes |
| `last-tool=` | State Predicate| 1 | Checks `state.last_tool == name` | Yes |
| `session-turns>=`| State Predicate| 1 | Checks `state.session_turns >= n` | Yes |

*Finding:* String manipulation (`str-concat`, `str-split`, `str-slice`) **does not exist**. List operations (`car`, `cdr`, `cons`) **do not exist**.

---

### 4.2 `RuleState` Dataclass Fields (`schemas.py:286-300`)

| Field Name | Type | Default | Description |
|---|---|---|---|
| `schema_version` | `Literal[1]` | `1` | Schema version identifier |
| `transcript` | `str` | `""` | Normalised speech transcript |
| `transcript_lower` | `str` | `""` | Lowercased transcript for matching |
| `intent` | `str` | `"unknown"` | Classified router intent |
| `intent_conf` | `float` | `0.0` | Router confidence score $[0.0, 1.0]$ |
| `entities` | `dict[str, list[str]]`| `{}` | Extracted named entities |
| `hour_local` | `int` | `0` | Local system hour $[0, 23]$ |
| `weekday` | `int` | `0` | Day of week $[0, 6]$ ($0=\text{Monday}$) |
| `apps_running` | `frozenset[str]` | `frozenset()` | Set of active desktop process keys |
| `last_tool` | `str \| None` | `None` | Name of tool executed in previous turn |
| `last_tool_ok` | `bool \| None` | `None` | Status of previous tool execution |
| `session_turns` | `int` | `0` | Total turns in current active session |
| `mode` | `Literal["audio", "transcript"]`| `"transcript"` | Input modality |

*Finding:* `RuleState` has **no field** for Belnap epistemic values, memory hits, tool outputs/receipts, or confidence thresholds.

---

### 4.3 Z3 SMT Verifier Capabilities (`smt_verifier.py`)

1. **Axioms Enforced (`StateContext.get_axioms`):**
   - $0 \le \text{hour\_local} \le 23$
   - $0 \le \text{weekday} \le 6$
   - $\text{session\_turns} \ge 0$
   - $0.0 \le \text{intent\_conf} \le 1.0$
2. **Precondition Checks:**
   - **SAT Check:** Verifies $\exists s: \text{Axioms}(s) \wedge \text{When}(s)$ (rejects dead code).
   - **Tautology Check:** Verifies $\exists s: \text{Axioms}(s) \wedge \neg \text{When}(s)$ (rejects unconditional rules).
3. **Deontic Plan Verification:**
   - Plan must be non-empty.
   - Any tool named in plan must be present in `registered_tools`.
   - Paths in filesystem tools (`read_file`, `write_file`, `edit_file`, `delete_file`) must not contain forbidden substrings:
     `..`, `../`, `..\`, `c:\windows`, `c:/windows`, `system32`, `syswow64`, `c:\program files`, `/etc`, `/usr`, `/bin`, `/sbin`, `/var`, `/proc`, `/sys`, `.git`, `.ssh`, `id_rsa`, `id_ed25519`, `.env`.
   - Mutation tools (`write_file`, `edit_file`) cannot target executable extensions:
     `.exe`, `.dll`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.sh`, `.sys`, `.msi`, `.com`, `.scr`.

---

### 4.4 Registered Tool Schemas (`CapabilityRegistry`)
Exposed in `CapabilityRegistry.get_tool_definitions()`:
1. `launch_app(app_name: str)`
2. `read_file(rel_path: str)`
3. `write_file(rel_path: str, content: str)`
4. `search_web(query: str)`
5. `fetch_url(url: str, render: bool = False)`
6. `query_capabilities(category: str = "all")`
7. Active skills dynamically appended as `skill_<rule_id>(query: str = "")`

*Finding:* Tools present in `TOOL_RISK_MAP` (`policy.py`) but **not registered** in capabilities: `list_dir`, `search_text`, `browse_page`, `delete_file`, `run_python`, `get_task_status`, `list_tasks`, `cancel_task`.

---

### 4.5 Tool Whitelist Status (`config/tool_whitelist.toml`)
* **Current Physical State:**
  ```toml
  [apps.calc]
  exe = "calc.exe"
  aliases = ["calculator", "calc"]

  [apps.terminal]
  exe = "wt.exe"
  aliases = ["terminal", "terminal"]
  ```
* **Historical Audited Baseline (Commit `2eaa58d`):** Contained `calculator`, `notepad`, `browser`, `terminal`, and `task_manager`.
* **Root Cause of Truncation:** Overwritten in commit `0ef309d` by unit test serialization in `tests/test_sandbox.py`.

---

### 4.6 SQLite Persistence Schema (`migrations/0003_rules.sql`)
Two tables exist:
1. `rule_states`: `rule_id` (PK), `status`, `source_canonical`, `source_hash`, `success_clusters_json`, `snapshots_json`, `failure_count`, `demotion_count`, `created_at`, `promoted_at`, `demoted_at`, `retired_at`, `user_retired`.
2. `regression_cases`: `case_id` (PK), `rule_id` (FK), `state_json`, `expected_plan_json`, `captured_at`, `stale`.

---

## 5. Deviations from Brief
* **None.** All recon steps conducted without source code mutations or test deletions.

---

## 6. Open Questions for Fable 5.1 & Architectural Review

1. **Restoration of `tool_whitelist.toml`:** Should we immediately restore the 5-application audited baseline (`calc`, `notepad`, `browser`, `terminal`, `task_manager`), resolving the commit `0ef309d` regression?
2. **The Role of MicroScheme:**
   - *Option A (Fast-Path Only):* Keep MicroScheme as an MVP macro launcher (seeding Batch 1 with basic app/file shortcuts).
   - *Option B (Symbolic Cognitive Substrate):* Formally extend MicroScheme (`str-concat`, Belnap epistemic predicates, memory inspection) and model them in Z3 before authoring procedural reasoning pathways.
3. **Static Validator Fixtures (`validator.py`):** Should `_generate_test_states()` be updated to generate a wider range of entity keys beyond just `app` and `file` so typed accessors for `content`, `category`, and `url` can pass static validation?
