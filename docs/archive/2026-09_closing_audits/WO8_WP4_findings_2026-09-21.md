# WO-8 Findings — WP-4 Session (2026-09-21)

Actionable defect register produced during WP-4 (Seeded RAG harness). Each
finding lists evidence, root cause, impact, and the concrete next action so an
auditor or the next work package can pick them up directly.

Baseline for this run: `master @ be9bb67` (WP-3) + WP-4 working tree.
Full T1 run: `uv run pytest -m "not tier2 and not hw and not soak" -q` →
**535 passed / 3 failed / 22 deselected** (164 s). The 22 deselected are the
marker-tiered tests (`tier2` / `hw` / `soak`) — by design: T1 is the
fake-backed unit+property tier; `hw` tests additionally fail fast in
`conftest.py` when llama-server is down. Full T2 tier run:
`uv run pytest -m tier2 -q` → **9 passed / 1 failed** (F-WO8-07).

---

## F-WO8-01 — WP-3 A1 live pack seeds invalid `kind` literals (FIXED in WP-4)

- **Severity:** S1 (blocks every WP-3 `@hw` test at seeding time)
- **Status:** ✅ Fixed in this working tree (WP-4 commit)
- **Evidence:** `UnsignedPayload.kind` is a strict `Literal`
  ([`src/lucca/core/schemas.py:281`](../../src/lucca/core/schemas.py:281)) —
  valid values: `transcript, fact, tool_fact, rule_assertion,
  assistant_utterance, action_receipt, belief, coherence_breach,
  session_summary, user_model`. The WP-3 seeder used four values outside that
  set, which raise `pydantic_core.ValidationError` the moment the live pack
  runs:
  - [`tests/test_a1_live_hw.py:431`](../../tests/test_a1_live_hw.py:431) `kind="tool_result"` → `tool_fact`
  - [`tests/test_a1_live_hw.py:474`](../../tests/test_a1_live_hw.py:474) `kind="utterance"` → `assistant_utterance`
  - [`tests/test_a1_live_hw.py:798`](../../tests/test_a1_live_hw.py:798) `kind="opinion"` → `belief`
  - [`tests/test_a1_live_hw.py:1138`](../../tests/test_a1_live_hw.py:1138) `kind="tool_result"` → `tool_fact`
- **Why it slipped:** `test_a1_live_hw.py` is `@pytest.mark.hw` and therefore
  deselected from the T1 baseline ("25/25"); the seeder had never executed.
- **Action taken:** all four literals corrected; re-run of the T3 hw pack
  required to confirm end-to-end (llama-server dependent).

## F-WO8-02 — `_check_functional_coherence()` API drift breaks A1 coherence test

- **Severity:** S2 (T1 red; A1 §5.4 coverage silently lost)
- **Status:** ❌ Open — pre-existing at `be9bb67` (verified: failure is in
  test/orchestrator API surface untouched by WP-4)
- **Evidence:**
  `tests/test_a1_autobiographical_memory.py::test_functional_coherence_mismatch_detection_and_breach_commit`
  calls `orch._check_functional_coherence(narration=..., tool_calls=...)` →
  `TypeError: Orchestrator._check_functional_coherence() got an unexpected
  keyword argument 'tool_calls'`
  ([`tests/test_a1_autobiographical_memory.py:474`](../../tests/test_a1_autobiographical_memory.py:474)).
- **Root cause:** the WP-2 runtime-wiring refactor changed the
  `_check_functional_coherence` signature (receipts are now read from
  `current_turn_receipts` / tool-call state) without updating this caller.
- **Impact:** the mismatch→COHERENCE_BREACH commit path has no passing test.
- **Action:** update the test to drive the current signature (or the
  `_finalize_turn` path used by the wiring tests), keeping the ≤ 2 % mismatch
  assertion intact.

## F-WO8-03 — `_record_tool_receipt` ValidationError on non-string tool output

- **Severity:** S2 (T1 red; reveals missing output coercion in production path)
- **Status:** ❌ Open — pre-existing at `be9bb67`
- **Evidence:**
  `tests/test_fast_path_sync.py::test_fast_path_sync_records_tool_executions_in_history`
  → `pydantic_core.ValidationError: 2 validation errors for ToolReceipt`
  (`output` / `error` must be `str`)
  ([`src/lucca/core/orchestrator.py:1072`](../../src/lucca/core/orchestrator.py:1072),
  triggered from [`tests/test_fast_path_sync.py:69`](../../tests/test_fast_path_sync.py:69)).
- **Root cause:** `_record_tool_receipt` forwards `output`/`error` from the
  tool result verbatim. When a `ToolResult` carries a non-`str` payload (in the
  test, a `MagicMock` `stderr`; in production, any structured object), Pydantic
  rejects it instead of the code coercing with `str(...)` / `""` defaults.
- **Impact:** any tool adapter returning non-string content crashes the
  receipt path mid-turn rather than degrading gracefully.
- **Action:** coerce in `_record_tool_receipt`
  (`output=str(output) if output is not None else None`, same for `error`) and
  add a regression test with a non-string `ToolResult.content`.

## F-WO8-04 — `test_tool_chaining` bare-Orchestrator fixture missing `current_turn_receipts`

- **Severity:** S3 (T1 red; test fixture drift only)
- **Status:** ❌ Open — pre-existing at `be9bb67`
- **Evidence:**
  `tests/test_tool_chaining.py::test_category_aware_search_grounding` →
  `AttributeError: 'Orchestrator' object has no attribute
  'current_turn_receipts'`
  ([`src/lucca/core/orchestrator.py:1071`](../../src/lucca/core/orchestrator.py:1071),
  triggered from [`tests/test_tool_chaining.py:595`](../../tests/test_tool_chaining.py:595)).
- **Root cause:** the test builds `Orchestrator.__new__(Orchestrator)` with a
  hand-rolled attribute list that predates the WP-2 receipt wiring; the new
  `_handle_tool_call → _record_tool_receipt` path requires
  `current_turn_receipts`.
- **Impact:** search-query grounding behaviour (category/location keyword
  preservation) is untested.
- **Action:** add `orch.current_turn_receipts = []` (and
  `current_turn_tool_spoken`/`current_turn_tool_ok` if still required) to the
  fixture, or switch the test to the shared wiring fixture from
  `test_a1_runtime_wiring.py`.

## F-WO8-05 — T0 mypy gate red: 286 pre-existing errors in `src/` (23 files)

- **Severity:** S2 (T0 gate cannot go green; blocks "Ratified (T0–T4)" checklist item "Zero-`Any` gate … green")
- **Status:** ❌ Open — pre-existing; none of the errors are in WP-4 files
  (WP-4 touches `tests/` only; mypy runs on `src` only)
- **Evidence:** `uv run python -m lucca.tools.lint` step 3
  (`python -m mypy src`) → `Found 286 errors in 23 files`. Hotspots:
  `core/orchestrator.py` (JsonValue union handling, ~60+ errors),
  `sandbox/system_tools.py:179`, `sandbox/win32_security.py` (ctypes `Any`),
  `brain/toolcall_demux.py:123` (list invariance), `ui/speech_bubble.py`,
  `ui/telemetry_hud.py`, `reasoning/stats.py:166`.
- **Impact:** the WO-8 sign-off checklist requires the zero-`Any` gate green;
  the current debt must be burned down or explicitly scoped out by the owner.
- **Action:** dedicated mypy-burn-down work package, ordered by file error
  count (orchestrator.py first). Do **not** silence with blanket
  `# type: ignore` — per D-AUD-01 the gate exists to catch real contract drift.

## F-WO8-06 — Seeded-RAG T2 finding: same-entity near-miss distractors fuse above cross-channel floor (fixture corrected)

- **Severity:** S4 (harness calibration, resolved)
- **Status:** ✅ Resolved in fixture design
- **Evidence:** first T2 run: probe `a06` ("What is my dog's favourite park?")
  retrieved distractor `d01` ("My dog's birthday is in June.") at RRF score
  0.032 ≥ floor 0.0246 (`1.5/(RRF_K+1)`, i.e. dense+sparse cross-channel
  agreement). With a 70-row corpus, any question naming a present entity
  dual-channel-retrieves that entity's rows — correct retrieval behaviour, not
  a pipeline defect.
- **Resolution:** abstention probes must target **absent entities** (the class
  the other 9 probes already used, e.g. rabbit/sister/passport). `a06` was
  redesigned to "What is my horse's name?" with the same pet-name guards. The
  floor definition (cross-channel RRF agreement) is retained and documented in
  [`tests/test_rag_seeded_tier2.py`](../../tests/test_rag_seeded_tier2.py).
- **Lesson for WP-5/WP-6:** retrieval-level assertions must be calibrated
  against corpus topology; reply-level (T3) judgements remain the authority for
  abstention behaviour.

## F-WO8-07 — Supervisor ordered-shutdown test times out on Windows (forrtl control-BREAK)

- **Severity:** S3 (T2 red; environment-sensitive, not a WP-4 regression)
- **Status:** ❌ Open — pre-existing at `be9bb67`
- **Evidence:**
  `tests/test_lifecycle_supervisor.py::test_sigterm_triggers_ordered_shutdown`
  → `subprocess.TimeoutExpired` after the 5 s shutdown window; stderr shows
  `forrtl: error (200): program aborting due to control-BREAK event` from the
  spawned `python -m lucca.main` process
  ([`tests/test_lifecycle_supervisor.py:191`](../../tests/test_lifecycle_supervisor.py:191)).
- **Root cause:** the supervisor's Fortran-linked native dependencies
  (e.g. numpy/MKL/OpenVINO runtimes) install their own CTRL_BREAK handler that
  aborts the process before the Python `signal`-based ordered-shutdown path can
  finish and flush; the child dies with forrtl abort instead of exiting 0
  within 5 s.
- **Impact:** F-CORE-006 (ordered shutdown ≤ 5 s) has no reliable green
  evidence on this workstation.
- **Action:** either (a) assert on the shutdown *log sequence* ("Ordered
  shutdown initiated..." + child exit within an enlarged, documented window)
  instead of process exit, or (b) suppress the native CTRL_BREAK handler in the
  child under `LUCCA_TEST_FAKES=1`. Owner to pick; do not delete the test.

---

## Reproduction commands

```powershell
:: Full T1 (4 failures at time of writing: F-WO8-02/03/04 + none from WP-4)
uv run pytest -m "not tier2 and not hw and not soak" -q

:: T0 gate (fails at mypy step: F-WO8-05)
uv run python -m lucca.tools.lint

:: WP-4 T2 harness
$env:LUCCA_TEST_TIER="T2"; uv run pytest -m tier2 -q

:: WP-4 T3 live battery (requires llama-server per WO §9)
$env:LUCCA_TEST_TIER="T3"; uv run pytest -m hw -q
```
