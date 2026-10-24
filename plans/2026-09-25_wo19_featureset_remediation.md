# Work Order 19 — Featureset Remediation (Execution Manual)

**Status:** Planned (pending owner ratification)
**Date:** 2026-09-25
**Audience:** an implementing agent with no prior context. Every step lists exact files, exact actions, verification, and rollback. **STOP** means halt and ask the owner.
**Findings source:** [`luccadocs/audit/findings/FEATURESET_AUDIT_2026-09.md`](../luccadocs/audit/findings/FEATURESET_AUDIT_2026-09.md) (F-FEAT-01…07)
**Golden rules:** one phase = one commit; run `uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"` after every step; never edit `luccadocs/archive/`; never "fix forward" from a red suite — revert and re-read.

---

## Phase 1 — WO-19a: Central Tool-Arg Validation Registry (F-FEAT-01, S1 — do first)

**Goal:** every tool dispatch validates its arguments against a Pydantic schema *in one place*; a tool with no registered schema is refused. Closes the `run_python`/`run_python_async` gap (the only tools currently unvalidated).

### 1.1 Exact change manifest

| Step | File | Action |
|---|---|---|
| 1 | `src/lucca/sandbox/schemas.py` | Add `TOOL_ARG_SCHEMAS: dict[str, type[BaseModel]]` mapping **all 19** tool names to their Args models. The models already exist for 17 tools (see `service.py` branches); add `RunPythonArgs` (fields: `code: str` required, `timeout_s: int = 15` le=60, `max_output_bytes: int = 65536` le=262144) and entries for `read_file`, `write_file`, `list_dir`, `search_text`, `query_capabilities`, `self_metrics`, `self_history_search`, `invoke_skill`, `launch_app` (exists), `run_python_async` (reuse `RunPythonArgs`). |
| 2 | `src/lucca/sandbox/service.py` | At the **top** of `execute_tool`, before any branch: look up `TOOL_ARG_SCHEMAS[tool_name]`; missing entry → return fail-closed `ToolResult(ok=False, stderr="schema_not_registered")`; `model_validate(args)` failure → return the existing ValidationError refusal shape (copy the pattern at :282-290). **Leave the existing per-branch validations in place** — they also use the parsed values; do not delete them in this phase. |
| 3 | `src/lucca/core/orchestrator.py` | **TRAP — read this twice.** `memory_commit` (:3299) and `invoke_skill` dispatch **orchestrator-side**, bypassing `SandboxService.execute_tool`. Validate their args against the same `TOOL_ARG_SCHEMAS` map inside `_handle_memory_commit` (:2813) and the `invoke_skill` handler, using the same refusal shape. |
| 4 | `tests/test_static_gates.py` | New gate `test_every_tool_has_arg_schema`: import `get_default_native_tools` and `TOOL_ARG_SCHEMAS`; assert the key sets are equal. Positive control: assert the gate fails when a dummy tool name is removed from the map (test the test). |
| 5 | `tests/test_sandbox_schemas.py` | Add: `run_python` with missing `code` → refusal; `run_python` with `timeout_s=9999` → refusal; `run_python` with valid args → reaches the container branch (mock RPC). |

### 1.2 Traps
- **TRAP 1:** forgetting step 3 — the registry looks complete but the two most sensitive tools still bypass it.
- **TRAP 2:** changing the refusal *shape*. Tests assert on existing `ToolResult` fields; copy the existing ValidationError branch exactly.
- **TRAP 3:** `invoke_skill` args are skill-defined, not fixed-schema. Validate only the envelope (`skill_id: str` required, `args: dict` optional) — do not try to validate skill-specific args here.

### 1.3 Verify
```powershell
uv run python -m pytest tests/test_sandbox_schemas.py tests/test_static_gates.py -q
uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"
```

---

## Phase 2 — WO-19b: Dead-Code Purge (F-FEAT-02)

**Prerequisite:** WO-18c merged (it may claim some exception classes for typed-exception conversion).

### 2.1 Procedure (one batch = one commit)

1. **Batch 0 — IPC payload check (no deletions).** Read `src/lucca/core/ipc_schemas.py:decode_envelope`. If it maps type strings to payload classes via a registry dict, the class names appear there and the AST scan already counted them as referenced — so `CaptureMarkPayload`, `SysPingPayload`, `SysSelfTestPayload`, `TTSAbortPayload`, `TTSChunkDone`, `Transcript` are dead only if absent from that registry. Confirm by grep: `grep -n "CaptureMarkPayload\|SysPingPayload\|SysSelfTestPayload\|TTSAbortPayload\|TTSChunkDone" src/ tests/` → expect zero hits outside `ipc_schemas.py` itself before deleting.
2. **Batch 1 — dead operational surfaces.** Delete: `MemoryStore.export_jsonl` (store.py:534), `SessionTelemetryLogger` (system_tools.py:244), `policy.add_taint` (policy.py:230), `service.get_tool_risk` (service.py:234), `server_ctl.restart_server` (server_ctl.py:488), `workspace.import_from_inbox` + `check_size_limit`, `capabilities.get_tool`/`get_tools`, `macros.all_macros`, `output_supervisor.reset_session`, `chunker.spoken_prefix`, `llm_client.active_client`. Suite green after the batch.
3. **Batch 2 — exception classes.** After WO-18c, delete whichever of the 12 unraised classes it did not claim (list in FEATURESET_AUDIT F-FEAT-02). Suite green.
4. **Batch 3 — `EventName`.** **STOP — owner decision:** wire `EventName` into the event bus (restores the no-free-form-event-names enforcement) or delete it. Recommend wire (the observability spec wants it).
5. Promote `scratch/audit_deadcode.py` (with the Qt-override and `@field_validator` false-positive exclusions) into a static gate.

### 2.2 Traps
- **TRAP 1:** Qt `paintEvent`/`mouse*Event` and Pydantic `@field_validator` methods are framework-called — the detector's exclusion list must keep them or the gate will false-positive forever.
- **TRAP 2:** `export_jsonl` is cited in Spec 04 §8. Deleting code does not require editing the archived spec — archives are immutable. Note the deletion in the commit message.

---

## Phase 3 — WO-19c: MicroScheme Direct Test Restoration (F-FEAT-03)

**Goal:** every `src/lucca/reasoning/scheme/*.py` module gets direct unit tests (today: zero direct imports from `tests/`).

### 3.1 What to write (patterns to copy)

| Module | Tests | Copy patterns from |
|---|---|---|
| `lexer.py` | token stream round-trips; `MAX_SOURCE_BYTES`/`MAX_TOKENS` bombs refused | `tests/test_ipc_codec.py` (frame limits) |
| `parser.py` | parse→AST round-trip; `MAX_NESTING_DEPTH` bomb; `RULE_ID_REGEX` accept/reject table | `tests/test_persona_toml.py` (table-driven) |
| `prims.py` | every primitive's type contract; `MAX_STR_LEN`/`MAX_LIST_LEN` bounds; `entity-str/int/num` on missing keys | `tests/test_sandbox_schemas.py` |
| `eval.py` | gas metering (1,000-gas program aborts deterministically); purity (no global mutation across two evals); timeout | `tests/test_lifecycle.py` |
| `macros.py` | depth-8 and step-64 bounds; macro cannot shadow prims | `tests/test_d_reas_07_negative.py` (negative-test shape) |
| `validator.py` | constant-true rejection; unmodeled-predicate fail-closed | `tests/test_d_reas_07_negative.py` |
| fuzz | hypothesis: random s-expressions never crash parser/eval (only raise typed errors) | `tests/test_extended_fuzzing.py` (existing hypothesis setup) |

**Acceptance:** `uv run python scratch/audit_subsystems.py` shows zero `NO TESTS` flags under `reasoning/scheme/`; new tests green.

---

## Phase 4 — WO-19d: Boot-Path Logging (rides WO-18c)

`main.py` (10), `admin.py` (8), `core/env_check.py` (7) silent handlers get `logger.debug` minimum. Same gate as WO-18c covers them.

## Phase 5 — WO-19e: Coverage for `system_tools` + `memory/entities`

Unit tests: `system_tools` metrics functions (mock `psutil`/`nvidia-smi` subprocess), `entities.py` KG resolution against an in-memory DB (pattern: `tests/test_memory_db.py`).

## Phase 6 — WO-19f: `admin memory forget` CLI (F-FEAT-07)

1. `src/lucca/admin.py`: add `memory forget <entry_id>` subcommand calling `MemoryStore.forget([entry_id], user_confirmed=True)` — **never** `MemoryManager.delete_memory` (the F-MEM-001/003 gate-bypass path).
2. Test in `tests/test_admin.py`: forget soft-deletes, writes a `memory_audit` row, preserves the provenance envelope.
3. Update the user guide's §2.4 note to point at the now-real command.

## Sequencing

```
WO-19a (now) ──> WO-18a ──> WO-19b (after WO-18c) ──> WO-19c ──> WO-19e/f (anytime)
```

**Parity invariant:** 680-test suite green at every commit boundary; `luccadocs/audit/baseline.json` updated at completion.

---

## Amendment v2 (2026-09-26) — Post-WO-18 Landscape Corrections

**Read this before executing any phase.** WO-18 changed the ground this plan was written on. The phases and traps are unchanged; the *locations and some contents* are corrected here. Where this amendment conflicts with the phase text above, **this amendment wins.**

### A2.1 — Locate by grep, never by line number
The orchestrator was decomposed (3,471 → 2,437 lines). Every `:LINE` citation in this plan is stale. Use these locators instead:
- `memory_commit` orchestrator-side dispatch: `grep -rn '"memory_commit"' src/lucca/core/orchestrator.py` (handler: `def _handle_memory_commit` — still on `Orchestrator`, was NOT extracted).
- `invoke_skill` dispatch: `grep -rn 'invoke_skill' src/lucca/core/orchestrator.py src/lucca/core/capabilities.py`.
- ValidationError refusal shape to copy: `grep -n 'ValidationError' src/lucca/sandbox/service.py` (first branch).

### A2.2 — WO-19a: SandboxPort now exists
WO-18d ratified `SandboxPort` ([`src/lucca/ports.py`](../src/lucca/ports.py)) with `execute_tool(call_id, tool_name, args, confirmed, human_confirmed)`. The `TOOL_ARG_SCHEMAS` registry must be consistent with that signature. When the registry lands, consider declaring it adjacent to the port (same module or `sandbox/schemas.py`) so the contract and the validation map can't drift — note which you chose in the review package.

### A2.3 — WO-19b batch 1 corrections
- **Remove `get_tool_risk` from the purge list.** It is now a declared method on the ratified `SandboxPort` — deleting it breaks the contract. (Flagged in the WO-18d review; the plan was not updated at the time.)
- **All 12 unraised exception classes are purgeable.** WO-18c is complete and claimed none of them for typed-exception conversion (it added logging only). No STOP needed for batch 2 beyond the standard suite-green check.

### A2.4 — WO-19f is 80% done already
WO-18e delivered `StudioFacade.forget_memory(memory_id, user_confirmed=True)` ([`src/lucca/core/studio_facade.py`](../src/lucca/core/studio_facade.py)) routing through `MemoryStore.forget(user_confirmed=True)` — exactly the prescribed path. WO-19f shrinks to: (1) add `admin memory forget <entry_id>` in `src/lucca/admin.py` calling the same `MemoryStore.forget` path (NOT `MemoryManager.delete_memory`); (2) the `tests/test_admin.py` test (soft-delete + audit row + envelope preserved); (3) update the user guide §2.4 note. Copy the facade's call pattern; do not design a new one.

### A2.5 — New gate/test patterns to copy (post-WO-18)
- New static gates: follow `test_speech_output_manager_decomposition` / `test_ui_no_direct_domain_imports` in `tests/test_static_gates.py` (AST presence/absence + exact-once markers + positive controls).
- New test files: follow `tests/test_studio_facade.py` / `tests/test_speech_output_manager.py` (construction with fakes, `__new__`-resilience case).
- The silent-except gate (`test_no_silent_broad_excepts`) is live — any handler you touch must log or re-raise.

### A2.6 — Suite baseline for reviews
Current green baseline is **696 passed** (not 680), 20 static gates, 7/7 import contracts, 3 known environmental failures (D-REAS-08 tripwire, 2 IPv6 SSRF). R.2 suite-state checks compare against *this* baseline.

---

## Review Protocol — every phase comes back for review before the next begins

**No phase is "done" when the implementer says it is.** Each phase ends with a review gate executed by a different agent (or the owner) than the one that implemented it.

### R.1 Review package (implementer submits)

1. Commit hash (one per phase — two commits = automatic fail).
2. Verbatim full output of `uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"` and `tests/test_static_gates.py`.
3. Verbatim output of the phase's own Verify commands (empty grep results shown as empty).
4. Completed self-check against the phase's manifest (every row marked).
5. List of out-of-scope observations (not fixes).

### R.2 Reviewer checklist (independent re-verification — never trust the package)

| # | Check | How |
|---|---|---|
| 1 | **Scope audit** | `git show --stat <hash>` — every changed file must be in the phase manifest. Anything else → **bounce**. |
| 2 | **Diff read** | Full diff. Bounce on: behavior changes in a refactor phase, deleted/weakened tests, unjustified `type: ignore`/`noqa`, `luccadocs/archive/` edits. |
| 3 | **Independent verify** | Re-run the phase's Verify commands; outputs must match the package. |
| 4 | **Trap audit** | Check each listed trap against the diff (e.g., WO-19a: orchestrator-side `memory_commit`/`invoke_skill` validation actually present; refusal shape unchanged; WO-19b: no Qt/Pydantic false-positive deletions). |
| 5 | **Gate quality** | New static gates must include their positive control (proof the gate can fail). |
| 6 | **Suite state** | 680+ green; only the two known pre-existing failures (D-REAS-08 tripwire, frozen binary), unchanged in character. |

### R.3 Verdicts

- **PASS** — logged below; next phase may begin.
- **BOUNCE** — reviewer writes the failing R.2 row + exact fix required; implementer fixes only that and resubmits the whole package. Two bounces on one phase → **STOP**, escalate to owner.

### R.4 Phase sign-off log

| Phase | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|
| 1 (WO-19a validation registry) | `4efea24` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-26 |
| 2 (WO-19b dead-code purge) | `757a6da` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-27 |
| 3 (WO-19c scheme tests) | `48edc9d` | implementing agent | reviewer (Zoo) | **PASS** (reviewer patch: `test_scheme_eval.py` gas-vs-timeout race — timeout disabled in gas-exhaustion test for determinism) | 2026-09-27 |
| 4 (WO-19d boot logging) | `62d3ce3` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-27 |
| 5 (WO-19e coverage) | `239f731` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-27 |
| 6 (WO-19f forget CLI) | `2550632` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-27 |
