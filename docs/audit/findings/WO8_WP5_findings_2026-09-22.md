# WO-8 Findings — WP-5 Session (2026-09-22)

Actionable defect and audit register produced during Work Package 5 (`FULL_LOOP M=3` + Live Research Chain Battery, WO-8 §7, `F-TS-07`).

Baseline for this run: `master @ 02c4592` (WP-4).
Full T1 run (`uv run pytest -q`): **536 passed / 0 failed / 29 deselected** (149 s).
Consolidated Net Provider run (`pytest tests/test_search_providers_net.py -m net -v`): **3 passed / 0 failed**.
Live Hardware Research run (`pytest tests/test_research_live_hw.py -m "hw and net" -v`): **4 passed / 0 failed** (117 s on RTX 5080 + WSL2 Ubuntu Docker CE).

---

## F-WO8-02 — `_check_functional_coherence()` API Drift (RESOLVED in WP-5)

- **Severity:** S2 (Was blocking `test_a1_autobiographical_memory.py` in T1)
- **Status:** ✅ Fixed in WP-5 working tree
- **Evidence:** `tests/test_a1_autobiographical_memory.py::test_functional_coherence_mismatch_detection_and_breach_commit` passed `tool_calls=orch.current_turn_tool_calls` containing simulated `[object()]` items, which failed with `TypeError: unexpected keyword argument 'tool_calls'`.
- **Resolution:**
  - Added `tool_calls: Sequence[ToolReceipt | dict[str, JsonValue] | object] | None = None` to `Orchestrator._check_functional_coherence`.
  - Added normalization handling in `_check_functional_coherence` for opaque simulated objects in mock tests.
  - Aligned breach description prefix to `"Narrated action claimed without tool execution: "`.
  - All 10 tests in `test_a1_autobiographical_memory.py` now pass.

---

## F-WO8-03 — `_record_tool_receipt()` Non-String Payload ValidationError (RESOLVED in WP-5)

- **Severity:** S2 (Was blocking `test_fast_path_sync.py` in T1)
- **Status:** ✅ Fixed in WP-5 working tree
- **Evidence:** Mock tests (`test_fast_path_sync.py`) returning `MagicMock` for `content` or `stderr` caused `pydantic_core.ValidationError` when constructing `ToolReceipt(output=output, error=error)`.
- **Resolution:**
  - Coerced `output` and `error` in `Orchestrator._record_tool_receipt`:
    ```python
    out_str = str(output) if output is not None and not isinstance(output, str) else output
    err_str = str(error) if error is not None and not isinstance(error, str) else error
    ```
  - Validated with `tests/test_fast_path_sync.py` passing cleanly.

---

## F-WO8-04 — Bare Orchestrator Fixture Missing `current_turn_receipts` (RESOLVED in WP-5)

- **Severity:** S3 (Was blocking `test_tool_chaining.py` in T1)
- **Status:** ✅ Fixed in WP-5 working tree
- **Evidence:** `tests/test_tool_chaining.py::test_category_aware_search_grounding` built `Orchestrator.__new__(Orchestrator)` without initializing `current_turn_receipts`, raising `AttributeError`.
- **Resolution:**
  - Added defensive initialization in `_record_tool_receipt`:
    ```python
    if not hasattr(self, "current_turn_receipts"):
        self.current_turn_receipts = []
    ```
  - Validated with all 20 tests in `test_tool_chaining.py` passing cleanly.

---

## F-WO8-08 — Gemma-4 Multi-Round Jinja Chat Template Requires Structured `tool_calls` (NEW & RESOLVED in WP-5)

- **Severity:** S1 (Critical runtime defect: multi-round tool loops looped or hung with real Gemma-4 model)
- **Status:** ✅ Fixed in WP-5 working tree
- **Evidence:**
  In multi-round tool loops, `Orchestrator._stream_llm_speech` previously appended synthetic textual assistant messages:
  ```python
  tool_messages.append(ChatMessage(role="assistant", content=f"Call tool {name}"))
  ```
  When running `llama-server.exe` with Gemma-4 (`--jinja`), the embedded Jinja template expects assistant messages containing tool calls to populate the structured `tool_calls` array (e.g. `[{"id": call_id, "type": "function", "function": {"name": ..., "arguments": ...}}]`). If passed plain text, the model repeatedly emitted `<|tool_call` tokens without acknowledging the round or hallucinated tool syntax.
- **Resolution:**
  - Added `tool_calls: list[dict[str, JsonValue]] | None = None` to `ChatMessage` in [`src/lucca/core/schemas.py`](file:///c:/Projects/ProjectLucca/src/lucca/core/schemas.py).
  - Updated `_stream_llm_speech` in [`src/lucca/core/orchestrator.py`](file:///c:/Projects/ProjectLucca/src/lucca/core/orchestrator.py) to construct assistant `ChatMessage` with proper `tool_calls` payload.
  - Updated [`src/lucca/brain/toolcall_demux.py`](file:///c:/Projects/ProjectLucca/src/lucca/brain/toolcall_demux.py) to parse native `<|tool_call` token boundaries.
  - Multi-round synthesis now transitions seamlessly from round 1 (`search_web`) to round 2 (`fetch_url`) to round 3 (final synthesis narration).

---

## F-WO8-09 — Model Argument Aliasing in File and Search Sandbox Tools (NEW & RESOLVED in WP-5)

- **Severity:** S2 (Model emitted `rel_path` instead of `path` or `queries` list instead of `query`, causing Pydantic validation failure)
- **Status:** ✅ Fixed in WP-5 working tree
- **Evidence:**
  During live execution, Gemma-4 occasionally called `read_file(rel_path="research_query.txt")` or `search_web(queries=["python release"])`, triggering `ValidationError`.
- **Resolution:**
  - Added `_coerce_path` model validator to `ReadFileArgs`, `WriteFileArgs`, and `DeleteFileArgs` in [`src/lucca/sandbox/schemas.py`](file:///c:/Projects/ProjectLucca/src/lucca/sandbox/schemas.py) to accept `rel_path`, `filename`, `file_path`, `filepath`, and `target`.
  - Added `_coerce_queries` model validator to `SearchWebArgs` to accept list or string inputs.

---

## WP-5 Live Hardware & Network Battery Verification Summary

The live test suite was executed against:
- **dGPU**: NVIDIA RTX 5080 Laptop GPU (`llama-server.exe` running `gemma-4-12b-heretic-Q6_K.gguf`, resident VRAM: ~10,639 MB).
- **WSL2 / Docker CE**: Verified with `uv run lucca-admin sandbox verify` (`all_passed: True`).
- **Network**: WSL2 egress firewall rules configured via `/opt/lucca/lucca-egress.sh`.

### Test Results

| Test | Objective | Result | Report Artifact |
|------|-----------|--------|-----------------|
| `tests/test_search_providers_net.py` | Live DDGS, Bing/Yahoo HTML fallbacks, and failover mechanics | ✅ **3/3 Passed** | Logs output |
| `test_live_research_two_hop` (WO-8 §7.1) | Two-hop research (`search_web` → `fetch_url` on `python.org`), verbal thinking cues, 0 truth breaches, VRAM $\le 12,800$ MB | ✅ **Passed** (40.7s, peak VRAM 10,639 MB) | `logs/test_reports/research_live_two_hop_20260921T213418Z.json` |
| `test_live_research_max_rounds_forced_synthesis` (WO-8 §7.2) | Forced synthesis on open-ended impossible query within bounded 3 rounds | ✅ **Passed** (37.8s, 2 tools called, honest synthesis) | `logs/test_reports/research_live_max_rounds_20260921T213503Z.json` |
| `test_live_research_sequence_guard_holds_with_real_model` (WO-8 §7.3) | `read_file` followed by `search_web` attempt in same turn blocked with exit -2 and honest refusal narration | ✅ **Passed** (16.1s, SequenceGuard blocked with exit -2) | `logs/test_reports/research_live_sequence_guard_20260921T213519Z.json` |
| `test_live_full_loop_grounded_long_body` (WO-8 §7.4) | `fetch_url` on long release page (>20k chars), D-BRAIN-04 numeric/date grounding verification, `enable_thinking=false` | ✅ **Passed** (14.2s, 0 grounding misses) | `logs/test_reports/research_live_grounded_long_body_20260921T213531Z.json` |

All 4 tests run consecutively in `tests/test_research_live_hw.py`: **4 passed in 117.83s**.
