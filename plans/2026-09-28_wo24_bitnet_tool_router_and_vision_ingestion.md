# WO-24 — BitNet Tool-Router Lobe, Vision Ingestion Spike, and Deferred Native Tools

**Date:** 2026-09-28
**Audience:** an implementing agent with no prior context. Every phase lists exact files, exact actions, **functional** acceptance criteria (behavioral, not just "suite green"), traps, and STOP gates. **STOP** means halt and report to the owner — do not improvise.
**Golden rules:** one phase = one commit; run `uv run python -m pytest -q -m "not tier2 and not hw and not soak"` after every step (baseline: **943 passed, 0 failed** — verified 2026-09-28; re-run before your first commit and record the number you actually see); never edit `docs/archive/`; never edit an existing migration file — new schema changes are **new migration files only**; never "fix forward" from a red suite — revert and re-read.
**Provenance:** WO-23 PASS (2026-09-28). Deferred items from WO-23: `clipboard_read` + `inbox_handoff` (Class C tools), `schedule_event` + `artifact_verify` (Class A tools), and vision ingestion (`screenshot_capture`). ASPIC+ (§1.14) explicitly deferred — trigger not yet met.

---

## Current state

The tool registry is at the hard cap: **19 tools / `MAX_REGISTRY_TOOLS = 19`** ([`capabilities.py:33`](../src/lucca/core/capabilities.py)).

The 19 registered tools are:
`calc_math`, `fetch_url`, `invoke_skill`, `launch_app`, `list_dir`, `memory_commit`, `memory_search`, `note_read`, `note_write`, `query_capabilities`, `read_file`, `run_python`, `run_python_async`, `search_text`, `search_web`, `self_history_search`, `self_metrics`, `sys_info`, `write_file`

Four tools are designed but not registered because they would bust the old cap:
- **Class A (her body):** `schedule_event`, `artifact_verify`
- **Class C (shared sensory boundary):** `clipboard_read`, `inbox_handoff`

One tool is designed but blocked on vision ingestion engineering:
- **Class C:** `screenshot_capture`

The brain ([`config.py:66`](../src/lucca/core/config.py)) is `gemma-4-12b-heretic-Q6_K.gguf` launched via `llama-server` in `mode = "audio"` with `mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf` ([`config.py:67`](../src/lucca/core/config.py)). Gemma 4 12B natively supports multimodal (image + audio) input tokens. The vision projector (`mmproj`) is already wired into [`server_ctl.py:327-328`](../src/lucca/brain/server_ctl.py) — `--mmproj` is passed to `llama-server` whenever `cfg.mode == "audio"` and the file exists. **No model change is needed.** The gap is on the tool side: no `screenshot_capture` tool, no image encoding path in [`llm_client.py`](../src/lucca/brain/llm_client.py), and no downsampling budget defined.

The KV-cache architecture is:
- **Frozen prefix** (byte-stable across turns): system prompt + `tools=` block (sorted alphabetically) + static category menu. Any change to the tool block causes a full prefix cache miss on that turn.
- **Variable suffix** (per-turn, cache-safe): category manifest injected at the tail of the frontier user message via `format_category_manifest` in [`prompt_builder.py:863`](../src/lucca/brain/prompt_builder.py).

Adding 5 more tools to the frozen prefix with no shortlisting does not degrade recall (the model sees all tools every turn) but does increase the frozen prefix token count and grow the `tools=` JSON block — acceptable once, since the cache then re-stabilizes.

---

## Phase 0 — Registry Cap Raise and Four Deferred Native Tools

**Goal:** add the four ready-designed native tools and raise `MAX_REGISTRY_TOOLS` exactly once. No new infra. No BitNet yet. No vision yet. Just get the tools in.

**Rationale for order:** the 4 tools are fully specified and do not depend on BitNet or vision. Raising the cap once (19→25) now, then again later (25→30) for vision would violate the one-raise discipline agreed in WO-23. This phase raises to 25. Vision (`screenshot_capture`) ships in Phase 2 as one more raise to 26. The BitNet shortlisting (Phase 3) then operates on the final tool set, so it is calibrated on the real population. Raising the cap is the simplest change and the lowest-risk: no new dispatchers, no new IPC, just new tool schema definitions and an updated constant.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/capabilities.py` | **Raise `MAX_REGISTRY_TOOLS` from 19 → 25.** Add 4 `ToolSchema` definitions to `get_default_native_tools()`. Do NOT change any existing entry. New tools (exact schemas specified at the STOP gate below): `schedule_event` (Class A, `risk=Risk.READ`, `target="self"`), `artifact_verify` (Class A, `risk=Risk.READ`, `target="self"`), `clipboard_read` (Class C, `risk=Risk.READ`, `target="shared"`), `inbox_handoff` (Class C, `risk=Risk.WRITE`, `target="shared"`). The constant comment must be updated: `# Raised 19 → 25 by WO-24 (schedule_event, artifact_verify, clipboard_read, inbox_handoff).` |
| `src/lucca/core/orchestrator.py` | **Wire Class C confirmation gates.** In `_describe_tool_action()`: add entries for `clipboard_read` ("read your clipboard") and `inbox_handoff` ("move a file into my workspace from your inbox"). In `_handle_tool_call()`: add post-execution spoken messages for both Class C tools (mirror the `launch_app` / `write_file` pattern). **Class C tools MUST route through the existing confirmation flow** — their `target="shared"` flag must be checked in the same place `launch_app` (`target="shared"`) is checked. Do NOT invent a new confirmation path; hook into the existing one. |
| `src/lucca/sandbox/` | Add stub implementations for `schedule_event`, `artifact_verify`, `clipboard_read`, `inbox_handoff` as RPC handlers in the sandbox layer. `schedule_event` stub: accepts `event_name` (str), `iso_datetime` (str, ISO 8601), `message` (str, optional); returns `{ok: true, event_id: <ulid>}` — no actual scheduling in this phase (STOP gate note below); logs the intent. `artifact_verify` stub: accepts `path` (str); computes SHA256 of the file at `LUCCA_HOME/workspace/<path>`; returns `{ok: true, sha256: <hex>, size_bytes: <int>}`. `clipboard_read` stub: reads Windows clipboard text via `win32clipboard` or `pyperclip` (already in venv or add to pyproject); returns `{ok: true, content: <text>, truncated: <bool>}` — truncate at 2000 chars; stamp output `TOOL_CONTENT_UNTRUSTED`. `inbox_handoff` stub: moves a file from `LUCCA_HOME/inbox/` to `LUCCA_HOME/workspace/` (the `WorkspaceManager.import_from_inbox()` at [`workspace.py:80`](../src/lucca/sandbox/workspace.py) already exists — call it); returns `{ok: true, dest_path: <str>}`. |
| `src/lucca/core/orchestrator.py` | Add `_handle_clipboard_read()`, `_handle_inbox_handoff()`, `_handle_schedule_event()`, `_handle_artifact_verify()` methods following the existing `_handle_self_history_search()` pattern ([`orchestrator.py:3078`](../src/lucca/core/orchestrator.py)). Dispatch them from `_handle_tool_call()` by name. |
| `tests/test_new_tools.py` (new) | **Class C confirmation gate test:** `clipboard_read` called without prior confirmation → confirmation prompt fires (mirror `test_launch_app_requires_confirmation`). `inbox_handoff` called without prior confirmation → confirmation prompt fires. **Functional tests:** `artifact_verify` on a known temp file → correct SHA256 returned. `clipboard_read` with mocked clipboard content → content truncated at 2000 chars, stamped `TOOL_CONTENT_UNTRUSTED`. `inbox_handoff` with a seeded `inbox/` file → file moved to `workspace/`, `ok=True`. `schedule_event` with a valid ISO datetime → `ok=True`, `event_id` is a valid ULID. **Static gate:** `len(get_default_native_tools()) == 25` — explicit count assertion so a future tool addition fails loudly at the test layer before it hits the registry cap. **Cap gate:** `CapabilityRegistry(tools=get_default_native_tools())` constructs without raising — confirms the new cap allows 25 tools. |
| `docs/V2_ACTION_LOG.md` | Mark `ITEM-024` and `ITEM-025` (both currently DEFERRED) as still-deferred with a note: `clipboard_read` and `inbox_handoff` NOW REGISTERED in WO-24 Phase 0 (their V2_ACTION_LOG item was about the CLASS C enforcement protocol, which is implemented via the existing confirmation flow — resolved by reuse, not new infra). Add a note that `schedule_event` and `artifact_verify` arrive in WO-24 Phase 0. |
| `docs/specs/STUDIO_CAPABILITY_ROADMAP.md` | Update the tool table: flip `schedule_event` and `artifact_verify` from `⏸ deferred` to `✅ WO-24`; flip `clipboard_read` from `🆕 NEW` to `✅ WO-24`; flip `inbox_handoff` from `🆕 deferred` to `✅ WO-24`. Update tool count to 23 Class A + 1 Class B + 2 Class C = 25 native (cap raised 19→25). Update the frozen prefix note. |

**Functional acceptance:**
- `len(get_default_native_tools()) == 25` (static assertion in the test suite).
- `CapabilityRegistry(tools=get_default_native_tools())` does not raise.
- `artifact_verify` on a known 100-byte file returns the correct SHA256.
- `clipboard_read` returns content truncated at 2000 chars and the result is stamped `TOOL_CONTENT_UNTRUSTED` in the turn trace.
- `inbox_handoff` with a seeded `LUCCA_HOME/inbox/test.txt` file moves it to `workspace/test.txt` and returns `ok=True`.
- `schedule_event` with `iso_datetime="2026-10-01T09:00:00+08:00"` returns `ok=True` and a ULID `event_id`.
- Both `clipboard_read` and `inbox_handoff` require confirmation before executing — invoking them without prior confirmation produces a spoken confirmation prompt, not execution.
- Suite green vs **943-passed** baseline (record your actual count).

**Traps:**
- **TRAP 1:** `clipboard_read` and `inbox_handoff` are `target="shared"`. Look at how `launch_app` (`target="shared"`) is handled in `_handle_tool_call()` and in the confirmation path. Hook into the same path — do NOT write a second confirmation branch for a different tool class.
- **TRAP 2:** `clipboard_read` output MUST be stamped `TOOL_CONTENT_UNTRUSTED` — clipboard content is attacker-controlled (ADR-006). Never allow it to be `TOOL_VERIFIED`. The sandbox RPC handler must set `content=<text>` (not `structured=`), so the provenance gate stamps it correctly.
- **TRAP 3:** `artifact_verify` only reads files under `LUCCA_HOME/workspace/`. It must refuse absolute paths and path traversal (e.g. `../../etc/passwd`). Use the existing workspace path validation already applied to `read_file`.
- **TRAP 4:** `schedule_event` stub intentionally does NOT schedule anything yet (actual calendar/notification dispatch is Phase 3 if added then, or a future WO). The stub records intent, returns a ULID, and speaks a confirmation. Do NOT reach out to external calendar APIs. Document the stub status in the function docstring.
- **TRAP 5:** do NOT rename or reorder existing tools — the frozen prefix must stay byte-stable for existing tools. Only add new entries.

**STOP gate:** tool schemas are owner-visible — present before implementing.

**Ratified schemas (owner decision 2026-09-28):**

```
schedule_event:
  description: "Schedule a reminder or future event by name and datetime."
  parameters:
    event_name: str (required) — human-readable label, e.g. "call mum"
    iso_datetime: str (required) — ISO 8601 datetime with offset, e.g. "2026-10-01T09:00:00+08:00"
    message: str (optional) — optional note or reminder text
  risk: READ (no host mutation in this phase; stub only)
  target: self

artifact_verify:
  description: "Compute the SHA-256 checksum and byte size of a file in the workspace."
  parameters:
    path: str (required) — relative path under the workspace (no traversal)
  risk: READ
  target: self

clipboard_read:
  description: "Read the current text content of the system clipboard."
  parameters: {} (no parameters)
  risk: READ
  target: shared  ← confirmation gate applies; output stamped TOOL_CONTENT_UNTRUSTED

inbox_handoff:
  description: "Move a file from the inbox drop folder into the workspace."
  parameters:
    filename: str (required) — filename in LUCCA_HOME/inbox/ to import (basename only, no path)
  risk: WRITE
  target: shared  ← confirmation gate applies
```

Proceed after ratification.

---

## Phase 1 — Vision Ingestion Spike: `screenshot_capture` for Gemma 4 12B

**Goal:** add `screenshot_capture` (Class C) as the 26th native tool. Gemma 4 12B with its `mmproj` projector already accepts image tokens via `llama-server` when `mode = "audio"` — the server launch already passes `--mmproj` ([`server_ctl.py:327-328`](../src/lucca/brain/server_ctl.py)). The gap is: (a) no image capture/encoding path in the code, and (b) no token-budget discipline to prevent cache thrashing.

**Key constraint:** an image ingest MUST NOT invalidate the main KV prefix cache for the rest of the conversation. The prefix cache is 4 GiB, reserved for the ~3.8K-token byte-stable system prompt + tools block. Image tokens are injected into the frontier **user message** (the variable suffix position), exactly as the category manifest suffix already is — this keeps the static prefix intact and only evicts the per-turn slot. The image is sent once per turn that requests it; subsequent turns receive no image tokens and the prefix cache reactivates.

**Architecture for this phase:** image tokens are sent inline in the chat message using the OpenAI multimodal message format (`content: [{type: "image_url", image_url: {url: "data:image/jpeg;base64,..."}}]`). `llama-server` GGUF multimodal mode supports this. No separate vision server, no second process, no VRAM budget change — the mmproj projector is already loaded.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/capabilities.py` | **Raise `MAX_REGISTRY_TOOLS` from 25 → 26.** Add `screenshot_capture` `ToolSchema`. Update constant comment: `# Raised 25 → 26 by WO-24 Phase 1 (screenshot_capture).` |
| `src/lucca/sandbox/screenshot_tool.py` (new) | `capture_screenshot(max_width: int = 1280, quality: int = 75) -> tuple[str, int, int]`: captures the primary display using `mss` (lightweight, no dependency on OpenCV or PIL, already cross-platform; add to `pyproject.toml` if absent); resizes to fit within `max_width` maintaining aspect ratio; JPEG-encodes at `quality`; returns `(base64_string, width_px, height_px)`. Hard constraints: output image MUST be ≤ 200 KB (re-compress at lower quality if needed); MUST clip to primary display only (no multi-monitor spanning); MUST strip all metadata (EXIF). |
| `src/lucca/brain/llm_client.py` | Add multimodal message support. When building the chat message list, if the last user message carries an `_image_b64` field (a new optional field on `ChatMessage`, or passed via a separate parameter), emit it as an OpenAI multimodal `content` array: `[{"type": "text", "text": <text>}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<b64>"}}]`. If no image: emit the existing plain string format (no regression). This must be a **minimal, additive change** — zero changes to the text-only path. |
| `src/lucca/core/schemas.py` | Add `image_b64: str | None = None` optional field to `ChatMessage` (or equivalent). If `ChatMessage` is a dataclass or TypedDict, maintain the existing interface by making it optional with a default. |
| `src/lucca/core/orchestrator.py` | Add `_handle_screenshot_capture()` method: calls `capture_screenshot()`, returns `ToolResult(ok=True, content="[screenshot captured]", structured={"width": w, "height": h, "size_kb": <n>})`. The base64 image data is attached via a separate `image_b64` field on the result (or stored on the turn context) so the narration LLM call can include it in the next frontier message. Spoken confirmation on success: `"I took a screenshot."`. |
| `src/lucca/core/orchestrator.py` | After `screenshot_capture` executes, the next LLM call for that turn (narration or FULL_LOOP) must include the image. Add a `_pending_image_b64: str | None` field on the orchestrator (cleared after each LLM call). When building messages for the narration / full-loop call, if `_pending_image_b64` is set, inject it into the last user message. Clear it immediately after injection. |
| `src/lucca/core/orchestrator.py` | Add `screenshot_capture` to `_describe_tool_action()` ("take a screenshot") and to the Class C confirmation gate (same path as `clipboard_read` and `inbox_handoff`). |
| `tests/test_vision_ingestion.py` (new) | **Encoding test:** `capture_screenshot()` returns a valid base64 JPEG string; decoded bytes ≤ 200 KB; dimensions ≤ 1280px wide. Use `mss` mock to avoid requiring a display in CI. **Message format test:** when `ChatMessage.image_b64` is set, `llm_client` builds a multimodal `content` array (check structure without calling the server — inspect the built message list). **Text-only regression:** when `ChatMessage.image_b64 = None`, the message is a plain string — no regression. **Confirmation gate:** `screenshot_capture` called without prior confirmation → confirmation prompt fires. **Static gate:** `len(get_default_native_tools()) == 26`. |
| `docs/specs/STUDIO_CAPABILITY_ROADMAP.md` | Flip `screenshot_capture` from `⏸ deferred` to `✅ WO-24 Phase 1`. Update tool count to 26. Note that vision trigger (§8) is now SATISFIED by Gemma 4 multimodal support. |
| `docs/V2_BACKLOG.md` | Add note to §1.7 (or a new §1.16 Vision Perception entry): "`screenshot_capture` shipped in WO-24 Phase 1; vision-lobe trigger satisfied by Gemma 4 12B native multimodal support + existing mmproj projector. §1.7 open-mic VAD remains independently deferred." |

**Functional acceptance:**
- `len(get_default_native_tools()) == 26` (static assertion).
- `capture_screenshot()` returns a valid base64 string; the decoded JPEG is ≤ 200 KB and ≤ 1280 px wide.
- When `ChatMessage.image_b64` is set, `llm_client` emits the OpenAI multimodal content array format (inspectable without a live server call).
- When `ChatMessage.image_b64 = None`, the message format is unchanged (text-only regression).
- `screenshot_capture` requires confirmation before executing — no confirmation → prompt, not execution.
- After `screenshot_capture` runs, the immediately following LLM narration call includes the image (inspect `_pending_image_b64` in the test after the tool handler runs).
- `_pending_image_b64` is `None` after the LLM call (cleared on use).
- Suite green vs **943-passed** baseline (record your actual count — expect +N from new tests).

**Traps:**
- **TRAP 1:** `screenshot_capture` is Class C (`target="shared"`). It touches the user's private screen surface. It MUST route through the confirmation gate — same path as `clipboard_read`. Do NOT bypass it.
- **TRAP 2:** the image is injected into the **variable suffix position** (frontier user message tail), NOT into the system prompt and NOT into the frozen prefix. Injecting it into the prefix would invalidate the entire KV cache for that session. The LLM call after `screenshot_capture` is a one-time cache miss; subsequent text turns resume hitting the cache.
- **TRAP 3:** `_pending_image_b64` must be cleared on every LLM call, not just successful ones — including error paths. A leaked pending image appearing in a subsequent unrelated narration call would be a correctness defect.
- **TRAP 4:** the mss capture is `target="shared"` — the sandbox policy only allows it with confirmation. The `capture_screenshot()` function in `screenshot_tool.py` is a library function; policy enforcement lives in the orchestrator (same pattern as all other tools).
- **TRAP 5:** do NOT add PIL or OpenCV as dependencies — `mss` alone for capture, Python's `io.BytesIO` + `struct` for JPEG quality recompression is sufficient. If JPEG re-encoding without PIL is unworkable in practice, add `Pillow` (already a common transitive dep) — but check `uv tree` first.

**STOP gate:** present the `screenshot_capture` schema and the multimodal message format (showing the exact JSON structure for `ChatMessage` with `image_b64`) to the owner before implementing.

**Ratified schema (owner decision 2026-09-28):**

```
screenshot_capture:
  description: "Capture the primary display as a JPEG image to reason about what is on screen."
  parameters: {} (no parameters)
  risk: READ
  target: shared  ← confirmation gate applies; output stamped TOOL_CONTENT_UNTRUSTED

Multimodal message format (OpenAI API, llama-server compatible):
{
  "role": "user",
  "content": [
    {"type": "text", "text": "<user utterance + suffix>"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<b64>"}}
  ]
}
```

Proceed after ratification.

---

## Phase 2 — BitNet Tool-Router Lobe (Hardware Spike → Classification Head → Integration)

**Goal:** introduce a lightweight per-turn tool shortlisting classifier so the future tool roster (26 tools and growing) does not require the primary 12B LLM to attend to all tools on every turn. This is an enabling infrastructure phase — it does not add user-visible capability.

**Why this is needed:** at 26 tools the frozen prefix `tools=` JSON block adds ~3–5K tokens. At 30+ tools it becomes non-trivial. The existing KV-cache architecture handles a static block at no per-turn cost — but correctness requires every tool to be visible on every turn. A shortlisting classifier selects the 6–10 most relevant tools per turn and injects only those into the `tools=` block, shrinking token cost and reducing tool-selection hallucinations. The Prompt Frontier Suffix mechanism (variable suffix at the frontier user message tail) cannot carry `tools=` — `tools=` is a top-level API parameter, not a message. The shortlister therefore operates at the **API call construction layer** in [`llm_client.py`](../src/lucca/brain/llm_client.py) / [`prompt_builder.py`](../src/lucca/brain/prompt_builder.py), producing a filtered `tool_definitions` list per turn.

**Architecture decision (owner-ratified):** this phase uses a **deterministic heuristic shortlister** (not BitNet). Reason: the BitNet hardware spike (original WO-24 preview) was to run `bitnet.cpp` on Arrow Lake for sub-20 ms ternary inference. After reviewing the engineering cost (ternary kernel build, Arrow Lake NPU kernel availability, integration effort) against the capability gained (tool shortlisting that could also be done with a fast keyword+intent map), the owner ratifies starting with a deterministic shortlister calibrated on the real 26-tool population. A neural shortlister (BitNet or otherwise) becomes eligible under §1.4 (Rung L5) when the active tool library triggers that condition. **The `V2_BACKLOG.md` §1.4 trigger condition already covers this evolution.**

**Shortlister design (ratified):**
- Input: `intent_class` (from HeuristicRouter), `route_action`, `tool_names_mentioned` (zero or more tool names the LLM explicitly requested last turn, if any), and the **always-include set** (`memory_search`, `memory_commit`, `invoke_skill`) — these three are always in the shortlist.
- Output: the filtered `list[ToolDefinition]` to pass as `tools=` in the LLM API call.
- Categories: map intent classes to tool subsets (e.g. `INFO` → `search_web`, `fetch_url`, `memory_search`; `FILE` → `read_file`, `write_file`, `list_dir`, `search_text`; `COMPUTE` → `run_python`, `calc_math`; `HOST` → `sys_info`, `launch_app`, `self_metrics`; `CLIPBOARD` → `clipboard_read`, `inbox_handoff`, `screenshot_capture`; etc.). Tools not in the shortlist for the current turn are simply omitted from the API `tools=` array.
- **Minimum shortlist size:** 6 tools (always-include 3 + at least 3 category tools).
- **Maximum shortlist size:** 12 tools (hard ceiling — if the intent class is ambiguous, include all tools; 12 < 26 is still a win).
- **Fallback:** if intent class is AMBIGUOUS or UNKNOWN → include all 26 tools (no shortlisting; same as today).
- **Recall gate (Wilson 95% LB ≥ 0.95):** the correct tool for a turn must appear in the shortlist. Measured on a golden trace set of at least 50 turns (seeded in Phase 2 tests).

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/tool_shortlister.py` (new) | `ToolShortlister`: `shortlist(intent_class: str, route_action: str, always_include: frozenset[str], all_tools: dict[str, ToolSchema]) -> dict[str, ToolSchema]`. Deterministic category map (no network, no model). Always includes the always-include set. Applies category map per intent class. Returns at most 12 tools (or all tools if AMBIGUOUS/UNKNOWN). Fully deterministic — no randomness. |
| `src/lucca/brain/prompt_builder.py` | All functions that accept `tools` (or equivalent) now accept a `shortlisted_tools: list[ToolDefinition] | None` parameter. If `None`, use all tools (backward compatible). If provided, pass `shortlisted_tools` as the `tools=` list to the LLM API call instead of the full registry. Rename/refactor nothing — add a parameter. |
| `src/lucca/core/orchestrator.py` | Before each LLM API call (FULL_LOOP and ACT_THEN_NARRATE), call `ToolShortlister.shortlist(...)` and pass the result to `prompt_builder`. Thread `intent_class` and `route_action` through from the `RouteDecision` already on the turn context (both are available). |
| `tests/test_tool_shortlister.py` (new) | **Category coverage test:** every intent class maps to a non-empty shortlist containing all always-include tools. **Recall test (golden traces):** 50 seeded `(intent_class, expected_tool)` pairs — for every pair, `expected_tool in shortlist(intent_class, ...)`. **Wilson 95% LB ≥ 0.95 assertion** on the 50-pair set. **Max-size test:** shortlist never exceeds 12 tools. **Fallback test:** AMBIGUOUS intent → all 26 tools returned. **Backward-compat test:** `build_full_loop_messages(shortlisted_tools=None)` → uses full tool list (no change to existing behavior). |
| `docs/V2_BACKLOG.md` | Update §1.4 note: "Deterministic tool shortlister shipped in WO-24 Phase 2 as a precursor to the Rung L5 neural upgrade; the neural upgrade trigger condition (28+ active rules, >5% collision) remains unchanged." |

**Functional acceptance:**
- `shortlist("INFO", ...)` contains `search_web`, `fetch_url`, `memory_search`, `invoke_skill`, `memory_commit` — and nothing host-mutation-related.
- `shortlist("AMBIGUOUS", ...)` contains all 26 tools.
- Golden trace Wilson 95% LB ≥ 0.95 across 50 pairs.
- Shortlist never exceeds 12 tools on any non-AMBIGUOUS intent.
- A FULL_LOOP turn executes correctly with a shortlisted tool set (end-to-end integration: route → shortlist → LLM call — no regression on existing tests).
- Suite green vs **943-passed** baseline (expect +N from new tests).

**Traps:**
- **TRAP 1:** the shortlister omitting a tool from `tools=` does NOT mean the tool cannot be called. If the LLM finds a way to call a non-shortlisted tool by name (e.g. via a MicroScheme rule that hard-names it), the dispatch path must still honor it. The shortlister is a prompt-optimization hint, not a security boundary. Security is enforced at the dispatcher layer (deontic gates, sandbox), not the shortlister.
- **TRAP 2:** `memory_search`, `memory_commit`, and `invoke_skill` are ALWAYS in the shortlist regardless of intent class — these are the tools the model uses for every-turn grounding. Never drop them from any shortlist.
- **TRAP 3:** the shortlister must return a `dict[str, ToolSchema]` (not a list) so the caller can sort it alphabetically before building the `tools=` block. Alphabetic sort is mandatory — it keeps the JSON byte-stable across turns with the same shortlist, maximizing sub-prefix cache reuse within a conversation.
- **TRAP 4:** backward compatibility — all callers of `build_full_loop_messages` and related functions currently pass no shortlist parameter. The new parameter must be optional with `None` defaulting to the full tool list. Do not break any existing call site.

**STOP gate:** present the full category → tool subset mapping table to the owner before implementing.

**Ratified category map (owner decision 2026-09-28):**

| Intent class | Shortlisted tools (plus always-include: memory_search, memory_commit, invoke_skill) |
|---|---|
| `INFO` / `SEARCH` | `search_web`, `fetch_url`, `calc_math` |
| `FILE` / `WORKSPACE` | `read_file`, `write_file`, `list_dir`, `search_text`, `artifact_verify` |
| `NOTE` / `MEMO` | `note_write`, `note_read` |
| `COMPUTE` / `CODE` | `run_python`, `run_python_async`, `calc_math` |
| `HOST` / `SYSTEM` | `sys_info`, `self_metrics`, `query_capabilities`, `launch_app` |
| `CLIPBOARD` / `PERCEPTION` | `clipboard_read`, `inbox_handoff`, `screenshot_capture` |
| `SELF` / `META` | `self_history_search`, `self_metrics`, `query_capabilities`, `sys_info` |
| `SCHEDULE` | `schedule_event`, `note_write` |
| `AMBIGUOUS` / `UNKNOWN` | ALL 26 tools |

Overlaps are intentional (e.g. `calc_math` appears in both INFO and COMPUTE — it is included if either category fires). Multiple intent signals may fire; their tool sets are unioned, then capped at 12.

---

## Phase 3 — Live Acceptance

**Functional acceptance (the only test that matters for this phase):**
- **Class A tools:** say "remind me to call mum tomorrow at 9am" → she calls `schedule_event` with the correct iso_datetime, speaks "I've noted that reminder" (or similar), `event_id` is in the turn trace.
- **Class A tools:** say "verify my report.pdf" (with a seeded `workspace/report.pdf`) → she calls `artifact_verify`, speaks the SHA256 and size.
- **Class C tools:** say "read my clipboard" → confirmation gate fires ("shall I read your clipboard?") → after confirmation, she calls `clipboard_read` and narrates the content.
- **Class C tools:** say "bring in the file from my inbox" (with a seeded `inbox/test.txt`) → confirmation gate fires → after confirmation, she calls `inbox_handoff`, file is in `workspace/`, she confirms.
- **Vision:** say "what's on my screen?" → confirmation gate fires → after confirmation, `screenshot_capture` runs, image token included in the narration LLM call, she describes what she sees in spoken prose (no markdown, no bullet points).
- **Shortlister:** for an INFO turn (search query), `sys_info` and `launch_app` are NOT in the tool definitions seen by the LLM (inspectable in the turn trace / logged tool definitions); `search_web` and `fetch_url` are.
- **KV cache:** after a `screenshot_capture` turn (cache miss), a plain text question on the next turn resumes prefix cache hits (observable via llama-server logs or `--cache-reuse` metrics if exposed).
- R.1 includes verbatim spoken output for all five scenarios above.

**Traps:** live scenarios must be run sequentially — each scenario is a fresh turn. Do not pipeline them. Vision scenario requires a real display (or a virtual framebuffer — document which is used).

**STOP gate:** verbatim spoken output for all five scenarios goes to the owner with the R.1.

---

## Execution order

```
Phase 0 (4 deferred tools + cap 19→25)
  → Phase 1 (screenshot_capture + vision ingestion + cap 25→26)
    → Phase 2 (deterministic tool shortlister)
      → Phase 3 (live acceptance — all five scenarios)
```

---

## Explicitly deferred (unchanged)

ASPIC+ (§1.14): trigger not met — corroboration engine has not produced multi-source conflict clusters unresolvable by pairwise handling. WO-24 shipping Walton schemes does not change this. Revisit trigger remains as-is.
`schedule_event` actual dispatch (calendar/notification API integration): Phase 0 ships the stub. Real scheduling (OS notification, calendar API, ZeroMQ deferred message) is a future WO.
BitNet neural shortlister (L5): §1.4 trigger condition unchanged — active rule library ≥ 28 rules and telemetry shows >5% collision rate or >2.0 ms matching latency. Deterministic shortlister in Phase 2 is the precursor.
All other `V2_BACKLOG.md` items: unchanged.

---

## Review protocol (unchanged)

R.1 package per phase: one commit hash, verbatim full-suite output, verbatim phase-verify output, self-check table, out-of-scope observations. Reviewer independently re-runs scope audit, diff read, verify, trap audit, gate quality (positive AND negative controls on new gates), suite state vs the **943-passed baseline** (as of 2026-09-28; re-baseline at implementation start). PASS logged; BOUNCE gets the failing row + exact fix; two bounces → STOP, escalate to owner.

---

## R.4 Phase sign-off log

| Phase | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|
| 0 (4 deferred tools + cap raise 19→25) | | | | | |
| 1 (screenshot_capture + vision ingestion + cap 25→26) | | | | | |
| 2 (deterministic tool shortlister) | | | | | |
| 3 (live acceptance) | | | | | |
