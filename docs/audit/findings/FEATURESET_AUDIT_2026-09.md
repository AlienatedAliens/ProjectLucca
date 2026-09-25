# Project Lucca — Featureset Audit & Remediation (WO-19)

**Status:** Complete audit, findings pending owner ratification
**Date:** 2026-09-25
**Scope:** All ten feature areas (brain, core, memory, reasoning, router, sandbox, senses, ui, root, ports) — 100 modules, ~35,700 lines (AST splitlines count)
**Method:** AST-based subsystem metrics (`scratch/audit_subsystems.py`), dead-code detection (`scratch/audit_deadcode.py`), manual spot-checks of all security-relevant hits, Nia research pass on validation-dispatch patterns
**Companion:** [`ARCHITECTURAL_DEBT_AUDIT_2026-09.md`](./ARCHITECTURAL_DEBT_AUDIT_2026-09.md) (F-ARCH series, WO-18). This audit covers *feature-area health*; that one covers *cross-cutting architecture*. No overlap in findings.

---

## 0. Subsystem Scorecard

| Subsystem | Modules | Lines | Broad exc (silent) | Async fns | Health |
|---|---|---|---|---|---|
| router | 5 | 1,044 | 3 (0) | 0 | **A** — best-tested, zero silent handlers |
| brain | 6 | 2,448 | 7 (5) | 0 | B+ — lean; `server_ctl` silent handlers need logging |
| memory | 12 | 3,033 | 13 (3) | 10 | B+ — async count is F-ARCH-101's, fixed by WO-18a |
| reasoning | 16 | 5,182 | 22 (9) | 0 | **C** — scheme engine core has zero direct tests (F-FEAT-03) |
| senses | 10 | 2,070 | 6 (5) | 1 | B — live but hardware-bound; coverage is hw-marked |
| sandbox | 18 | 5,586 | 43 (30) | 0 | **C** — most broad excepts; S1 validation gap (F-FEAT-01) |
| core | 17 | 10,455 | 52 (17) | 0 | C+ — orchestrator/settings debt is WO-18's; cascade clean |
| ui | 10 | 6,017 | 35 (34) | 0 | **D** — worst subsystem; 34/35 silent; god dialog |
| (root: main/admin/ports) | 4 | 1,557 | 18 (18) | 11 | C — boot path fully silent; dead port definitions |

---

## F-FEAT-01 (S1) — `run_python` / `run_python_async` Bypass D-SEC-04 Schema Validation

**Evidence:** [`sandbox/service.py`](../../src/lucca/sandbox/service.py) validates arguments per tool with Pydantic — `LaunchAppArgs` (:283), `FetchUrlArgs` (:310), `SearchWebArgs` (:383), `CalcMathArgs` (:417), `MemorySearchArgs` (:469), `MemoryCommitArgs` (:523), `NoteWriteArgs` (:560), `NoteReadArgs` (:597), `SysInfoArgs` (:654). The `run_python`/`run_python_async` branch (:785) goes **straight to execution with no validation**. `RunPythonArgs` exists in [`sandbox/schemas.py:73`](../../src/lucca/sandbox/schemas.py:73) and is referenced by nothing (AST-verified dead).

**Why S1:** D-SEC-04 mandates strict Pydantic schemas for *all* tool dispatches. The single most powerful tool — arbitrary code execution — is the one tool without it. Any malformed/missing `code` arg reaches the container unvalidated; error behavior is undefined instead of a clean schema refusal.

**Rectification (WO-19a), research-backed:** the Nia pass confirms the industry-standard pattern is a **central validation registry** — a dispatch-time `tool_name → ArgsModel` map where validation happens in one place and a *missing entry refuses dispatch*, replacing per-branch try/except discipline. This makes "every tool is validated" a structural property (statically testable) rather than per-branch hygiene:
1. Build `TOOL_ARG_SCHEMAS: dict[str, type[BaseModel]]` covering all 19 tools; validate at the top of `execute_tool` before any branch.
2. Wire `RunPythonArgs` (add `timeout_s`, `max_output_bytes` bounds while there).
3. Static gate: every tool in `get_default_native_tools()` has a registry entry.

## F-FEAT-02 (S2) — Dead Code Register (63 candidates, triaged)

**Verified dead (purge candidates):**
- **12 exception classes never raised or caught**: `ASRError`, `BootError`, `GroundingError`, `LLMProtocolError`, `LLMTimeout`, `LauncherNotWhitelisted`, `LauncherRateLimited`, `MemoryIntegrity`, `MemoryLocked`, `RuleConflict`, `SandboxEgressError`, `TTSFailed` ([`core/exceptions.py`](../../src/lucca/core/exceptions.py)). Either wire them (WO-18c's typed-exception conversion is the natural consumer) or delete.
- **`EventName` taxonomy** ([`core/events.py:9`](../../src/lucca/core/events.py:9)): the observability spec's "no free-form event names" enforcement is **inert** — the enum is referenced by nothing, so event names are effectively free-form today.
- **Dead operational surfaces**: `MemoryStore.export_jsonl` (Spec 04 §8 export path, never called), `SessionTelemetryLogger` ([`sandbox/system_tools.py:244`](../../src/lucca/sandbox/system_tools.py:244)), `policy.add_taint`, `service.get_tool_risk`, `server_ctl.restart_server`, `workspace.import_from_inbox`/`check_size_limit`, `capabilities.get_tool`/`get_tools`, `macros.all_macros`, `output_supervisor.reset_session`, `chunker.spoken_prefix`, `llm_client.active_client`.
- **Dead IPC payloads** (verify against `decode_envelope` registry before purging): `CaptureMarkPayload`, `SysPingPayload`, `SysSelfTestPayload`, `TTSAbortPayload`, `TTSChunkDone`, `Transcript`.

**False positives (do NOT purge):** Qt framework overrides (`paintEvent`, `mouse*Event` — called by Qt), Pydantic `@field_validator` methods (`validate_skill_id`, `validate_categories` — called dynamically), the 5 dead ports already owned by F-ARCH-102/WO-18d.

## F-FEAT-03 (S2) — MicroScheme Engine Core Has Zero Direct Tests

**Evidence:** the formally-verified execution language's core modules have **no direct test imports** (AST-verified against all of `tests/`): `scheme/parser.py` (598 lines), `scheme/prims.py` (504), `scheme/eval.py` (299), `scheme/macros.py` (156), `scheme/validator.py` (151), `scheme/lexer.py` (123). Coverage is *indirect* via lifecycle/skills/golden-trace tests. The archived test strategy shows `test_scheme` hypothesis fuzzing existed in an earlier tree — it did not survive into the current one.

**Why S2:** this is the sandboxed execution language that every rule, skill, and induced candidate runs in. A parser or prim regression would be caught only indirectly, after passing through the lifecycle layer — the worst place for the weakest direct testing.

**Rectification (WO-19c):** restore direct unit + hypothesis fuzz tests for parser (round-trip, depth-bomb, memory-bomb), prims (each primitive's type contract), eval (gas metering, purity), macros (depth-8/step-64 bounds), validator (constant-true, unmodeled-predicate fail-closed).

## F-FEAT-04 (S3) — Boot Path Is Fully Silent

**Evidence:** `main.py` 10/10 broad excepts silent, `admin.py` 8/8 silent, `core/env_check.py` 7/7 silent. The boot diagnostics path — the code that runs when things are *already broken* — swallows its own failures without a log line. Folded into WO-18c's exception hygiene (same fix, same gate).

## F-FEAT-05 (S3) — Coverage Gaps in Live Hardware-Bound Modules

`senses/audio_proc.py` (410 lines), `senses/npu_proc.py` (257), `senses/ptt.py` (138) are **live** (spawned by [`main.py:70-71`](../../src/lucca/main.py:70) per ADR-008) with zero direct test imports; coverage is via `hw`-marked live tests only. `sandbox/system_tools.py` (278) and `memory/entities.py` (104) likewise. Acceptable for hardware paths; `system_tools` and `entities` are not hardware-bound and should get unit tests (WO-19e).

## F-FEAT-06 (S3) — `ui` Subsystem Is the Worst-Health Area

6,017 lines, 34/35 broad excepts silent, `settings_dialog.py` at 3,221 lines/84 methods (AST count), `ui/app.py` 649 lines/35 methods/18 getattr sites. Owned by F-ARCH-104/WO-18e; this audit adds the exception-hygiene numbers to its scope.

---

## Positive Findings (verified)

- **router** is the model subsystem: 1,044 lines, zero silent handlers, direct tests for heuristic/conformal/calibration/labeler.
- **memory gate/signers/retrieval**: 16–33 test files each; the provenance core is the best-tested code in the tree.
- **`core/schemas.py`**: 55 importing test files; the contract layer is thoroughly pinned.
- **`core/cascade.py`**: zero silent handlers, 13 test files.
- **audio_proc/npu_proc are live**, not dead — the ADR-008 four-process topology is real (contradicting the archived drift finding's era).

---

## Remediation Plan — WO-19

| Phase | Content | Severity | Acceptance |
|---|---|---|---|
| **WO-19a** | Central tool-arg validation registry (`TOOL_ARG_SCHEMAS` dispatch map, missing entry = refuse); wire `RunPythonArgs` with bounds; static gate "all 19 tools have validators" | S1 | Gate green; `run_python` with malformed args → clean schema refusal; full suite green |
| **WO-19b** | Dead-code purge: verified-dead symbols from F-FEAT-02 (after `decode_envelope` registry check for IPC payloads); `EventName` either wired into the event bus or deleted by ADR | S2 | Suite green after each deletion batch; dead-code detector re-run → 0 true positives |
| **WO-19c** | MicroScheme direct test restoration: parser/prims/eval/macros/validator/lexer unit + hypothesis fuzz | S2 | Each scheme module has direct test imports; fuzz battery green |
| **WO-19d** | Boot-path logging (folded into WO-18c) | S3 | Zero silent handlers in main/admin/env_check |
| **WO-19e** | Unit tests for `system_tools`, `memory/entities` | S3 | Direct test imports exist |

**Sequencing:** WO-19a is independent and S1 — it can land **before** WO-18a (it is a security gap, not a refactor). WO-19b/c after WO-18a (smaller diff). WO-19d rides WO-18c. WO-19e anytime.

**Process doctrine applies:** every gate ships with positive controls; every accepted state gets a ratchet (validator-registry gate, dead-code gate, scheme-coverage gate); `docs/audit/baseline.json` updated at completion.

## Verification

```powershell
uv run python scratch/audit_subsystems.py   # subsystem scorecard
uv run python scratch/audit_deadcode.py     # dead-code register
uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"
```
