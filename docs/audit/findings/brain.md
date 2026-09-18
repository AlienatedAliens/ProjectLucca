# Findings — BRAIN (`src/lucca/brain/**`, `config/persona.toml`, `config/intents.toml`)

**Subtask:** S2b · **Method:** static line-by-line + S1 dynamic evidence · **Baseline:** HEAD `ed14f6b` + working tree per `03_BASELINE.md`, **with a post-S1 mutation of all five brain modules accepted by the audit owner and recorded as F-BRAIN-008** · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; nothing outside `docs/audit/` touched; every finding cites `file:line` in the tree as it exists at S2b write time, or an artefact under `docs/audit/evidence/`. Archived specs are cited as *claims*; code truth wins. Core findings are cross-referenced by ID, not restated.

**Severity totals: S0 = 1 · S1 = 6 · S2 = 24 · S3 = 15 · S4 = 2 · total = 48.**

**Baseline-delta notice (applies to every line citation in this file).** The S2b first pass wrongly reported that all five brain modules mutated post-S1: it compared S0's **non-blank** line counts (`Measure-Object -Line`) against total line counts from file reads. The corrected re-inventory ([`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md), evidence `S2b_01_git_status.txt` + `S2b_02_line_counts.txt`) shows **107 of 110 in-scope text files unchanged since S0**; the real post-S0 changes are exactly three files: `src/lucca/brain/server_ctl.py` (336→346 non-blank; provably after S1 — `S1_15a` shows the then-code emitting `--log-format json`, absent now; stderr→DEVNULL replaced by the `logs\llama-server.log` redirect), `src/lucca/main.py` (150→180; adds the boot-failure log-tail printer at `main.py:123-133`), and `scripts/test_s1_startup.py` (51→49; newly `M` in git status). S1-era line numbers in the subtask brief (`server_ctl.py:252`, `:311`) describe the pre-change `server_ctl.py`; the current tree no longer contains those two defects. This file audits the **current** tree and cites S1 artefacts for the historical state. See F-BRAIN-008 (rewritten per the correction).

**Owner decisions (2026-09-18):** six decisions affecting this area's remediations (Q-01 severity rule, Phase-0 S5 disposition, voice/persona ownership + Chrono Trigger strip, persona-file ownership, model supply Option A, gpt-oss-20B spike) are ratified in [`../04_OWNER_DECISIONS.md`](../04_OWNER_DECISIONS.md) (D-AUD-01…06). Where a finding's remediation is amended by a decision, the decision file wins (notably F-BRAIN-004's prompt rewrite, which must also strip the CT identity).

---

## 1. Module map

Coverage from `docs/audit/evidence/S1_14_coverage.txt` (T1, `-m "not hw and not soak"`, 02_EVIDENCE_INDEX row 25). **Caveat:** the coverage run predates the tree mutation; percentages and miss-ranges describe the pre-mutation files and are reproduced for orientation only.

| File | LOC (now) | Public symbols | Responsibilities (as-built) | Live callers in product path? | Outbound dependencies | Cov % (pre-mutation) | Tests exercising it |
|---|---:|---|---|---|---|---:|---|
| `src/lucca/brain/llm_client.py` | 199 | `LLMClient` (`stream_turn`, `abort`) | OpenAI-compat streaming client to llama-server; structured `tool_calls` accumulation; inline-JSON handoff to demux | **yes** — `core/orchestrator.py:18`, constructed `:80`, called `:403` | `httpx`, `structlog`, `brain.prompt_builder`, `brain.toolcall_demux`, `core.config`, `core.exceptions`, `core.schemas` | 19 % | none directly; indirectly `tests/test_turn_loop.py` via `FakeLLM` (not this class) |
| `src/lucca/brain/prompt_builder.py` | 658 | `ARCHETYPES`, `ARCHITECTURAL_SELF_AWARENESS`, `FORMALITY_MODIFIERS`, `compile_trait_modulators`, `preview_system_prompt`, `compile_persona_prose` (alias), `set_persona`, `get_system_prompt`, `get_persona`, `update_toml_content`, `get_persona_config`, `save_persona_to_config`, `load_persona_from_config`, `SYSTEM_PROMPT` (alias), `TOOL_DEFINITIONS`, `build_messages` | Persona prose compilation; persona.toml load/save (regex line-rewriter); hard-coded tool schemas; message-array assembly | **yes** — `build_messages`+`TOOL_DEFINITIONS` via `llm_client.py:14,62,71`; `set_persona` via `core/orchestrator.py:19,209`; `get_persona` via `ui/app.py:19,243`; `ARCHETYPES`/`compile_trait_modulators`/`get_persona_config`/`preview_system_prompt`/`save_persona_to_config` via `ui/settings_dialog.py:54-60,234,678,2425`. **Dead in product:** `SYSTEM_PROMPT`, `compile_persona_prose` (tests only: `tests/test_prompt_builder.py:10,110`) | `tomllib`, `re`, `json`, `core.schemas` | 83 % | `tests/test_prompt_builder.py` (7), `tests/test_persona_toml.py` (2) |
| `src/lucca/brain/chunker.py` | 236 | `ABBREVIATIONS`, `FIRST_CHUNK_MIN_CHARS`…`FORCE_SPLIT_AT`, `normalise_text`, `StreamingChunker` (`feed`, `flush`, `reset`, `spoken_prefix`) | Streaming sentence-boundary detection → `TTSChunk`; markdown/emoji normalisation | **yes** — `core/orchestrator.py:17`, constructed `:84`, fed `:423`, flushed `:439`. **Dead:** `spoken_prefix` (`chunker.py:108-110`, no caller in `src/` or `tests/`) | `re`, `unicodedata`, `core.schemas` | 92 % | `tests/test_chunker.py` (9 + 1 property) |
| `src/lucca/brain/toolcall_demux.py` | 151 | `INLINE_TOOL_PREFIX_REGEX` (dead), `ToolCallDemux` (`feed`, `flush`) | Separates inline-JSON tool calls and code fences from speakable text deltas | **yes** — `llm_client.py:15`, constructed `:79`, fed `:152`, flushed `:170`. **Dead:** `INLINE_TOOL_PREFIX_REGEX` (`toolcall_demux.py:19`) | `json`, `re`, `uuid`, `core.schemas` | 58 % | `tests/test_chunker.py::test_t_chk_10` (1) |
| `src/lucca/brain/server_ctl.py` | 399 | `GGUFMetadata`, `parse_gguf_file`, `scan_model_registry`, `resolve_model_path`, `build_launch_command`, `check_server_status`, `is_healthy`, `start_server`, `stop_server`, `restart_server` | llama-server process orchestration; GGUF header parsing; model registry for the UI | **yes** — `start_server`/`is_healthy`/`check_server_status` via `main.py:12,108,115,135`; `stop_server`/`scan_model_registry`/`is_healthy`/`start_server` via `ui/settings_dialog.py:61-66,99,1131`. **Dead:** `restart_server` (no caller in `src/`, `tests/`, or `scripts/`) | `httpx`, `psutil`, `subprocess`, `struct`, `core.config` | 62 % | `tests/test_server_ctl.py` (5), `tests/test_gguf_parser.py` (4) |
| `config/persona.toml` | 25 | 12 keys in 4 tables | Persona + affect + traits config | **yes** — loaded at import by `prompt_builder.py:533` (path resolution `:394-396`); `[affect]` read by `core/affect.py:182` (unwired, F-CORE-031); written by `ui/settings_dialog.py:2425` | — | n/a | `tests/test_persona_toml.py` |
| `config/intents.toml` | 23 | 6 intent tables | Intent lexicon for the heuristic router | **no (dead in product)** — read only by `router/heuristic.py:76-98`, and only the `[intents.launch_app]` `apps`/`stop_words_after_start` keys; the router itself is unwired from the turn loop (F-CORE-003) | — | n/a | router tests (ROUT area) |
| `config/tool_whitelist.toml` | 33 | 5 `[apps.*]` tables | Approved launchable applications | **yes** — `sandbox/launcher.py:53-55` (SBX area; consulted on every `launch_app`) | — | n/a | `tests/test_sandbox.py` (SBX area) |

Doubles/scripts read: `tests/fakes/fake_llm.py` (42 lines; sync generator, `abort()` sets a flag checked between script events; signature defaults `temperature=0.2`/`max_tokens=512` diverge from the real client's `None`-defaults), `scripts/test_s1_startup.py` (57), `scripts/run_spike02_suite.py` (470), `scripts/download_llm_models.py` (50), `scripts/test_audio_req.py` (27).

**Dead-in-product summary:** `restart_server`, `spoken_prefix`, `INLINE_TOOL_PREFIX_REGEX`, `SYSTEM_PROMPT`, `compile_persona_prose`, `config/intents.toml` (whole file, product path), persona.toml `name`/`voice` keys (brain side), 5 of 6 intent verb lists. Unlike memory/router/reasoning (F-CORE-003), the four code modules of brain are all on the live turn path; only the symbols listed are dead.

---

## 2. LLM request/stream pipeline as-built

### 2.1 Sequence diagram (audio turn; text turn analogous via `_run_text_turn`, `orchestrator.py:473-547`)

```mermaid
sequenceDiagram
    autonumber
    participant A as audio proc (PTT)
    participant O as Orchestrator (core, turn thread)
    case as ASRWorker (in-process)
    participant C as LLMClient (brain)
    participant P as prompt_builder
    participant S as llama-server.exe (127.0.0.1:8080)
    participant D as ToolCallDemux
    participant K as StreamingChunker
    participant T as TTSWorker (in-process)
    participant X as SandboxService

    A->>O: ptt.released (ingest thread, ZMQ PULL 47003)
    O->>O: spawn _run_turn thread (orchestrator.py:295-309); t_llm_sent stamped :333 (BEFORE ASR — F-CORE-009)
    O->>case: transcribe(pcm) :355 (blocking, 1.4–1.5 s measured S1_35)
    O->>O: silence guard :359-367; WAV encode + base64 :375-381; play.begin :384-391
    O->>C: stream_turn(audio_b64, text, history) :403
    C->>P: build_messages(memories=None, history, audio, text) :62-67
    P-->>C: messages [system+mem | history[-6:] | user] (prompt_builder.py:624-656)
    C->>S: POST /v1/chat/completions (stream) :86-88 — httpx.Client(timeout=30.0) :80
    S-->>C: SSE lines (iter_lines :93)
    loop per data: frame
        C->>C: json.loads :101 (fail → silent skip :102-103)
        C->>C: delta.tool_calls? accumulate :112-125; finish_reason=="tool_calls" → yield ToolCallEnd :127-147
        C->>D: demux.feed(TokenDelta) :152 (inline-JSON watch, ≤400 chars, demux:50-101)
        D-->>C: TokenDelta | ToolCallEnd
        C-->>O: yield event
        O->>O: trace.tokens_out += 1 :416; caption re-publish (full text, F-CORE-046) :420-421
        O->>K: chunker.feed(delta) :423 → TTSChunk(s)
        O->>T: _synthesize_chunk (blocking ~330 ms/clause, S1_34) :430
        O->>X: on ToolCallEnd → _handle_tool_call :433-435 → :639-669 (confirm gate :650-651)
    end
    C->>C: flush tool calls :155-167; demux.flush :169-171; yield Done(usage=0,0) :173
    O->>K: chunker.flush :439; FLAG_EOS :444; history append :450-454
    O->>O: finally: t_postturn_done, log_turn_trace, state→idle :468-471
```

### 2.2 Buffers, timeouts, retries, cancellation points

| Mechanism | Location | Value / behaviour |
|---|---|---|
| HTTP client timeout | `llm_client.py:80` | single `httpx.Client(timeout=30.0)` — covers connect/read/write/pool; a >30 s inter-byte stall mid-stream raises `ReadTimeout` → `LLMUnavailable` (`:175-178`). No separate connect timeout; no TTFT watchdog; no total-turn watchdog (Spec 02's 10 s/60 s absent — core.md §3.1) |
| SSE line buffer | `llm_client.py:93` | `resp.iter_lines()` — httpx handles partial frames; lines not starting `data: ` skipped `:94`; `[DONE]` breaks `:97-98` |
| Malformed frame handling | `llm_client.py:100-103` | `json.JSONDecodeError` → `continue`, **no log** |
| Tool-call accumulation buffer | `llm_client.py:83,112-125` | `current_tool_calls: dict[int, dict]`; arguments string concatenated unbounded (capped only by `max_tokens`) |
| Demux inline-JSON buffer | `toolcall_demux.py:30-31,61-101` | ≤ 400 chars, only within first 12 chars of reply; give-up releases buffer as text `:93-100` |
| Chunker buffer | `chunker.py:102,122` | bounded by `FORCE_SPLIT_AT=260` force-split `:139-145` |
| Reply accumulation | `orchestrator.py:395,417` | `full_response_text` list, unbounded; re-joined and re-published per token (F-CORE-046) |
| History | `orchestrator.py:450-454` | unbounded list, last-6 sent (F-CORE-018) |
| Retries | — | **none** anywhere in brain (acceptable: generation is non-idempotent; no finding) |
| Cancellation: barge-in | `orchestrator.py:242-268` (via core.md §3.1) | `_abort_turn()` → `llm.abort()`, `chunker.reset()`, `FLAG_ABORT`, bus `play.abort` |
| Cancellation: abort impl | `llm_client.py:183-198` | sets `self.aborted`, closes `self.active_client`, then `POST /slots/0?action=release` with 0.2 s timeout; **all errors swallowed at debug** `:189-198`; endpoint returns HTTP 501 on build 11026 (S1_36 S8 ×10) |
| Cancellation: stream-side | `llm_client.py:175-177` | closed client raises inside generator → `if self.aborted: return` (generator ends **without** `Done`) |
| Cancellation: turn-side | `orchestrator.py:408-409,424-425` | `trace.interrupted` checked per event and per chunk |
| Confirmation wait | `orchestrator.py:630` | `confirm_event.wait(timeout=15.0)` — the only timeout in the turn path |
| Shared mutable client state | `llm_client.py:40-41,81-82` | `self.active_client`, `self.aborted` are instance-global; two concurrent turn threads (possible per F-CORE-011) share them → F-BRAIN-006 |

### 2.3 SSE parsing state machine (as-built)

```mermaid
stateDiagram-v2
    [*] --> WAIT_LINE : resp.iter_lines()
    WAIT_LINE --> WAIT_LINE : line not starting "data: " (:94)
    WAIT_LINE --> END : line == "data: [DONE]" (:97-98)
    WAIT_LINE --> WAIT_LINE : json.loads fails → silent skip (:100-103)
    WAIT_LINE --> WAIT_LINE : choices empty → skip (:105-107)
    WAIT_LINE --> ACCUM_TC : delta.tool_calls present (:112-125)
    ACCUM_TC --> ACCUM_TC : more tool_calls deltas
    ACCUM_TC --> EMIT_TC : finish_reason == "tool_calls" (:127-147)
    ACCUM_TC --> TEXT : delta.content also present (:150-153)
    WAIT_LINE --> TEXT : delta.content non-empty (:150-153)
    TEXT --> WAIT_LINE : demux.feed → yield events
    EMIT_TC --> WAIT_LINE : current_tool_calls.clear() (:147)
    WAIT_LINE --> FLUSH_TC : stream exhausted
    FLUSH_TC --> FLUSH_DEMUX : yield remaining ToolCallEnd (:155-167)
    FLUSH_DEMUX --> DONE : demux.flush() (:169-171)
    DONE --> [*] : yield Done(usage=0,0) (:173)
    WAIT_LINE --> ABORT_END : httpx.HTTPError/OSError & self.aborted → return, no Done (:175-177)
    WAIT_LINE --> ERROR : httpx.HTTPError/OSError & not aborted → raise LLMUnavailable (:178)
```

Notes: non-200 status raises before the loop (`:89-91`) with the body decoded as strict UTF-8 (`:90`); `choices[1:]` are never inspected (n=1 assumed); `finish_reason == "length"`/`"stop"` are not distinguished — both fall through to the flush path; `usage` chunks (llama-server `timings`) are never parsed (`:173` hardcodes zeros).

---

## 3. Prompt structure as-built

### 3.1 Message array (`build_messages`, `prompt_builder.py:611-657`)

Order produced (single `system` message, then history, then user):

1. **`system`** = `get_system_prompt()` (`:627`) with the memory block appended (`:630-634`):
   - `{archetype prose}` — `ARCHETYPES[key]` or user archetype (`:162-167`)
   - `{formality rule} {voice constraints}` (`:205`, `:173-178`)
   - `{prose directives}` — name / uncertainty / never-pretend / refuse-topics / trait modulators (`:180-203`)
   - `ARCHITECTURAL_SELF_AWARENESS` (`:47-91`, appended `:209`)
   - `\n\n[Creator Persona Directives]\n{custom_prompt}` — only if set (`:210-211`)
   - `\n\n[Persistent Memory Context]\n- {hit.content}` × N — only if `memories` non-empty (`:630-634`)
2. **history** — `history[-6:]` appended verbatim as `{role, content}` dicts (`:638-641`); no token cap, no truncation, no validation of roles
3. **`user`** — audio mode: `[{type: input_audio, input_audio: {data: b64, format: wav}}]` + optional `{type: text}` part (`:644-653`); text mode: plain string (`:654-655`)

The request also carries `tools: TOOL_DEFINITIONS`, `tool_choice: "auto"`, `chat_template_kwargs: {"tools_in_user_message": False}` (`llm_client.py:69-77`).

### 3.2 Delimiters, budgeting, truncation

- **Delimiters:** section headers in square brackets (`[Internal Architecture & Technical Self-Awareness]`, `[Creator Persona Directives]`, `[Persistent Memory Context]`) and `- ` bullets for memory hits. No fencing, no escaping, no per-segment quoting. A memory hit or custom prompt containing the literal text `[Creator Persona Directives]` or `\n\nSystem:` is indistinguishable from genuine sections.
- **Token budgeting:** none. No token counter exists in brain. Spec 10 §4's budget (system ≤ 350, tools ≤ 600, memory ≤ 600 with k ≤ 8 / 160 chars per hit, history ≤ 1 200 truncate-oldest, reply reserve 512) is unimplemented in every row. The compiled system prompt alone is ≈ 700–900 tokens by chars÷4 (ARCHETYPES ≈ 90–120 words + `ARCHITECTURAL_SELF_AWARENESS` ≈ 430 words + directives), i.e. 2–2.5× the ≤ 350 budget before memories.
- **Truncation:** none. Overflow behaviour is delegated to llama-server (which truncates or 400s); `history` is count-capped at 6 exchanges but not token-capped (F-CORE-018 covers the unbounded list).
- **KV-cache friendliness:** the static persona prefix precedes the varying memory block and history, so llama-server per-slot prefix reuse works for the persona part (observed `cache_n=53` on repeat identical prompts, `S1_18b_llm_ttft_probe.txt`). Memories are folded into the *system* message (`:630-634`), so any change in retrieved hits invalidates the prefix from that point — consistent with ADR-001's note, but the memory block has no size discipline.

### 3.3 Prompt-injection surface table

| Source of text | Trusted? | Delimiter in prompt | Length cap | Can it reach memory? |
|---|---|---|---|---|
| `ARCHETYPES` / `FORMALITY_MODIFIERS` / `ARCHITECTURAL_SELF_AWARENESS` | static code (trusted) | section headers | n/a | no commit path exists (F-CORE-003) |
| `persona.toml` fields incl. `custom_prompt`, `refuse_topics`, user archetypes | user-authored config — "USER_EXPLICIT-equivalent" (`IMPLEMENTATION_PROMPT_2026-09-17_persona_llm_ui.md` §1.3) | `[Creator Persona Directives]` header; bare interpolation | none | no |
| `MemoryHit.content` (when wired; today always `None` — F-CORE-003) | provenance-gated tiers only (`USER_EXPLICIT`, `USER_DERIVED`, `TOOL_VERIFIED`, `LISP_ASSERTION`) | `- ` bullet inside system message | **none** (spec: k ≤ 8, 160 chars each) | already in memory |
| `history` user turns | Whisper transcript (`USER_EXPLICIT`) | `role: user` | 6 exchanges, no token cap | no commit path |
| `history` assistant turns | prior `LLM_NARRATION` replayed | `role: assistant` | 6 exchanges | no commit path |
| current audio (`input_audio` b64) / current text | user voice / typed text | `role: user` content parts | `ptt.max_seconds = 29.5` (`config.py:76`) at capture; **no cap in brain** | no commit path |
| tool results, file bodies, web pages (`TOOL_CONTENT_UNTRUSTED`) | untrusted (Spec 12 Z2/Z3/Z4) | **never enter the prompt** — results are discarded after execution (F-CORE-019) | n/a | **no** — no commit path; `LLM_NARRATION` has no signer (TM-01) |

**Verdict (as-built):** untrusted tool/page text can reach **neither** the prompt **nor** memory today — but this is achieved by *absence of wiring* (tool results discarded, memory retrieval/commit unwired), not by controls. The moment F-CORE-019 (tool results fed back) or F-CORE-003 (memory wiring) is remediated, the surface opens with **no** TM-02 controls in brain: no 20 k-char cap, no "tool output is data" marking in the system prompt, no delimiters on the memory block (`prompt_builder.py:630-634`). The system prompt itself cannot be overridden by tool content today (tool content never enters); `custom_prompt` can override persona directives by design (creator-owned, appended last, `:210-211`).

---

## 4. Tool-call demux grammar as-built

### 4.1 Accepted formats

| # | Format | Where parsed | Acceptance rules |
|---|---|---|---|
| 1 | Structured `delta.tool_calls` chunks (OpenAI/Llama-3.1 template via `--jinja`) | `llm_client.py:112-147` | index-keyed accumulation (`:114-120`); `id` defaults to `call-{uuid8}` (`:117`); name/arguments concatenated across deltas (`:122-125`); emitted on `finish_reason == "tool_calls"` (`:127-147`) **or** at stream end (`:155-167`) |
| 2 | Inline JSON object in `content`, reply-initial | `toolcall_demux.py:50-101` | suspected only within the first 12 chars of the reply (`:50-57`); must start `{` or `<|python_tag|>`; held ≤ 400 chars (`:93`); accepted when the cleaned buffer starts `{`, ends `}`, parses, and has `name` + (`parameters` or `arguments`) (`:68-77`); synthesises `ToolCallEnd` with `call_id = inline-{uuid8}` (`:80-89`) |
| 3 | Same grammar at stream flush | `toolcall_demux.py:128-150` | identical parse, but **without** the `isinstance(args, dict)` guard present in `feed` (`:77-79` vs `:139`) |

### 4.2 Partial / malformed handling

| Case | Behaviour | Location |
|---|---|---|
| Tool-call JSON split across SSE chunks | accumulated correctly (both paths) | `llm_client.py:124-125`, `toolcall_demux.py:62-64` |
| Arguments JSON malformed at `finish_reason` | `logger.warning("invalid_tool_call_json")`, `args = {}`, **call still yielded for execution** | `llm_client.py:131-146` (and `:156-167`) |
| Structured call with empty `name` | **silently dropped** (`if tc_data["name"]`) | `llm_client.py:139,164` |
| Inline JSON > 400 chars | buffer released as spoken text | `toolcall_demux.py:93-100` |
| Inline JSON mid-reply (after 12 chars) | **not detected** — spoken as text (Spec 08 §2 sanctions the 12-char window) | `toolcall_demux.py:50-57` |
| Non-dict `parameters` at flush (e.g. list) | `ToolCall(args=…)` pydantic validation raises `ValidationError` **uncaught** inside `llm_client.py:170-171` flush loop → turn dies via the generic `except` (`orchestrator.py:457-467`) | `toolcall_demux.py:137-141` |
| `parameters: {}` + non-empty `arguments` | `or` chain picks `arguments` (empty dict is falsy) | `toolcall_demux.py:77,139` |
| Second inline call in one reply | not detected (`_resolved_tool_call` latch) | `toolcall_demux.py:33,86` |
| Code fence ` ``` ` split across deltas | not detected; code spoken | `toolcall_demux.py:107` |
| Model emits prose + tool call | prose spoken; only reply-initial JSON is demuxed | as above |

### 4.3 Validation against whitelist / schemas before execution

**None exists in brain.** `TOOL_DEFINITIONS` (`prompt_builder.py:538-608`) is a hard-coded list of 4 tools; it is *not* derived from `config/tool_whitelist.toml` or `config/intents.toml`, and neither the demux nor the client checks the emitted tool name or args against it. Downstream gates (SBX area, cited for the path): `classify_risk` defaults **unknown** tool names to `Risk.WRITE` → confirmation required (`sandbox/policy.py:33-41`); `launch_app` args are checked against the whitelist by alias *after* confirmation (`sandbox/launcher.py:104-147`); everything else falls to `rpc.execute` (`sandbox/service.py:217-218`). Args are never validated against the JSON-schema `parameters` (enum/required) anywhere. `MAX_TOOL_CALLS_PER_TURN = 4` (Spec 12 §3) has no implementation (`SequenceGuard` counts nothing, `sandbox/policy.py:61-94`).

### 4.4 Path of a hallucinated `launch_app` on a tone clip (measured: S1_36 S6 clips 21/22)

1. Raw server emits structured `tool_calls` for a 3 s sine tone (artefact `S1_36_spike02.txt`, 02_EVIDENCE_INDEX row 67).
2. Product path: `llm_client.py:127-147` → `ToolCallEnd(launch_app, {app_name: …})` → `orchestrator.py:433-435` → `_handle_tool_call` (`:639`).
3. `check_confirmation_needed("launch_app")` → `True` (LAUNCH, `policy.py:29,38-41`) → `_request_confirmation` speaks "open calculator?" and waits 15 s (`orchestrator.py:594-637`).
4. Only on explicit user confirm does `launcher.launch` run, with a second alias/whitelist check (`launcher.py:104-147`, `launch_not_whitelisted` on miss).

**Verdict:** a hallucinated **LAUNCH/WRITE** call is stopped by the confirmation gate (and the whitelist behind it) — *if* the human reads the prompt; the gate is a 15 s default-deny. A hallucinated **READ/NETWORK** call (`query_capabilities`, `read_file`, `fetch_url`) **auto-executes with no user gate** — measured in T3: `test_live_phase1_tool_call_turn` returned and executed `query_capabilities{'category': 'all'}` for an "open calculator" utterance (`S1_30_T3_hw.txt`, row 56). The fictional capability manifest it returns (`sandbox/service.py:144-215`) is then spoken as fact.

---

## 5. Chunker as-built vs spec (Spec 08)

### 5.1 Rules as-implemented

- Constants (`chunker.py:42-46`): `FIRST_CHUNK_MIN_CHARS=24`, `FIRST_CHUNK_MAX_CHARS=90`, `MIN_CHARS=40`, `MAX_CHARS=220`, `FORCE_SPLIT_AT=260` — match Spec 08 §4 values.
- Boundary candidates: `. ! ? ; :` plus soft `,` when `i >= min_len` (`chunker.py:189-190`). **`\n` is not a candidate** (spec: candidate after `. ! ? ; :` *or `\n`*; `\n\n` → boundary; heading/bullet line-end → boundary).
- Lookahead: punctuation must be followed by whitespace or end-of-buffer-at-final (`:196-202`) — matches spec rule 1.
- Abbreviation guard for `.` only (`:213-225`): list match, single-capital, and a numbered-list check that only fires when the **entire buffer so far** is one token (`len(prev_text.split()) == 1`).
- Ellipsis: third dot of `...` splits only if followed by space + uppercase; otherwise held (`:205-210`).
- Quote/paren depth: `chunker.py:178-186` — **defective**, see F-BRAIN-005.
- Force split: at `len(buffer) >= 260`, last whitespace before 260, else hard 260 (`:139-145`). Force-split chunks may reach 260 chars > `MAX_CHARS=220` (spec-internal tension: spec defines both numbers; recorded, no finding).
- Normalisation (`normalise_text`, `:55-90`): smart quotes/dashes/ellipsis, markdown links → text, bare URLs → "a link" (unless `speak_urls`), emphasis strip (2 passes), heading/bullet marker strip, emoji removal (categories So/Sk above ASCII only — variation selectors/ZWJ survive), space collapse `[ \t]+` (**newlines not collapsed**), space-before-punctuation fix. Applied **per delta** in `feed` (`:121`), not on the accumulated buffer.

### 5.2 Spec'd vs implemented vs tested

| Spec 08 behaviour | § | Implemented? | Tested? |
|---|---|---|---|
| Decimal protection (`3.14`) | §4.1 / T-CHK-01 | yes (lookahead) | yes (`test_chunker.py:14-25`) |
| Filename dots (`config.yaml`) | §4.1 / T-CHK-02 | yes | yes (`:28-36`) |
| Abbreviations (`Dr.`, `e.g.`, `i.e.`) | §4.2 / T-CHK-03/04 | yes | yes (`:39-58`) |
| Ellipsis `Wait... really? Yes!` → 2 chunks | §4.4 / T-CHK-06 | **no** — both boundaries fall below `FIRST_CHUNK_MIN_CHARS=24`, so one chunk results (analysis §5.3) | **no** — test numbering skips 06 |
| Numbered-list marker protection; `1. …\n2. …` → 2 chunks | §4.5 / T-CHK-14 | **partial** — protection only when buffer is exactly `N.`; `2.` mid-text splits wrongly | **no** |
| `\n` as boundary candidate; `\n\n` → boundary; line-end after heading/bullet | §3/§4 | **no** | no |
| `idle_flush_ms = 350` stall flush | §4 / T-CHK-11 | **no** — no timer exists; `flush()` only at stream end | no |
| Force split ≤ 260, no chunk > 260 | §4 / T-CHK-05 | yes | yes (`:61-71`) |
| First chunk 24–90 chars | §4 / T-CHK-13 | **partial** — `candidate_split` returns the first boundary ≥ min even when > max (`:229-233`); a 150-char first sentence yields a 150-char first chunk | no |
| Soft `,` boundary ≥ min | §4 | yes (`:190`) | no dedicated test |
| Markdown emphasis/link/URL strip | §3 / T-CHK-07 | yes — **but per-delta**, so markup spanning deltas survives (F-BRAIN-021) | yes, single-string only (`:74-82`) |
| Emoji/smart-quote normalisation | §3 / T-CHK-08 | yes (So/Sk > 127) | yes (`:85-92`) |
| Quote/paren depth suppression, reset > 3 | §4.3 | **defective** (F-BRAIN-005) | no |
| `is_first` only chunk 0; `reset()` restores | §5 / T-CHK-09 | yes | yes (`:95-110`) |
| Per-turn object; `flush()` emits remainder **and resets** | §5 | **no** — `flush()` does not reset; one shared chunker lives across turns in `Orchestrator.__init__` (`orchestrator.py:84`) and across concurrent turn threads (F-CORE-011 sibling) | no |
| `spoken_prefix` for history-on-interrupt | §5 | implemented but **dead** — orchestrator never reads it; interrupted turns drop the partial reply from history (core.md §3.3 row 3) | no |
| Demux gate: 30 fixture streams (10 structured / 10 inline / 10 brace-text), 0 leaks | §2 / T-CHK-10 | mechanism yes | **no** — 1 inline + 1 plain case only (`:113-150`) |
| Hypothesis 2 000 cases, `join(chunks) == normalise(text)` | §6 / T-CHK-12 | n/a | **partial** — 100 examples, no join-equality assertion (`:153-164`) |
| First chunk ≤ 90 chars within 8 deltas (latency) | §6 / T-CHK-13 | not guaranteed (above) | no |

### 5.3 Worked defect: T-CHK-06 trace

Input `"Wait... really? Yes!"` (20 chars), first chunk: `.` at index 4 completes `...`; next char is space + lowercase `r` → held (`:205-210`). `?` at 14 → `split_candidate=15 < 24` → skipped; `!` at 19 → `20 < 24` → skipped. No boundary ≥ min exists, so the whole string becomes one chunk at flush. Spec expects `["Wait... really?", "Yes!"]`. The min-chars rule and the ellipsis rule are not composed anywhere; no test pins the expected behaviour.

---

## 6. Server control as-built

### 6.1 Launch command — three sources of truth

| Source | Exe path | `--flash-attn` | `--log-format json` | `--mmproj` |
|---|---|---|---|---|
| ADR-001 canonical (`docs/archive/…/08_adr/ADR-001_inference_engine.md:28-41`) | `$LUCCA_HOME\…\llama-server.exe` (path not pinned) | bare flag | **present** | present, 2nd arg |
| SKILL.md §4 (`.agents/skills/lucca-pipeline/SKILL.md`) | `app\bin\llama-server.exe` | bare flag | absent | present, 2nd arg |
| Code now (`server_ctl.py:252-285`) | `app\llama-server\llama-server.exe` | `on` (explicit value) | **absent** | appended **last**, only if `mode == "audio"` and file exists |
| Code at S1 (artefact `S1_15a_launch_cmd_from_code.txt`, row 27) | `app\llama-server\…` | `on` | **present** | appended last |

Historical defect (fixed in the current tree, recorded for the record): the S1-era command was executed verbatim and the server **exited 1 after 2.63 s** with `error: invalid argument: --log-format` (`S1_15_llama_server.stderr.log`, row 30); the S1-era `start_server` piped stderr to DEVNULL so the failure was silent, and boot then waited 60 s → `exit 5` (F-CORE-012). The current tree removed the flag and redirects stdout+stderr to `logs\llama-server.log` (`server_ctl.py:320-327`); `main.py:123-133` now prints the log tail on early exit. The ADR still specifies the rejected flag (F-BRAIN-023); the SKILL.md exe path (`app\bin\`) matches neither the code nor the on-disk layout (`app\llama-server\`, `S1_06_lucca_home_tree.txt`) — charter §10 assigns stale SKILL/AGENTS paths to the TEST/DRIFT area; cross-referenced, not duplicated.

### 6.2 Health, timeouts, restart, shutdown, zombies

- **Health:** `check_server_status` GETs `/health` with 1.0 s timeout; 200 → `ready`, 503 → `loading`, **any other status → `loading`** (`server_ctl.py:288-301`). `is_healthy` = `== "ready"` (`:304-306`). Boot polls ≤ 60 s wall-clock (`main.py:121-148`), `exit 5` on process death with an 800-char log tail (`:123-133`).
- **Restart:** `restart_server` (`server_ctl.py:363-398`) polls `/health` ≤ 60 s, raises on early exit/timeout — **dead code** (no caller). The UI restart path imports `stop_server`/`start_server`/`is_healthy` directly (`settings_dialog.py:61-66,98-99`).
- **Stop:** `stop_server` terminates the tracked proc (3 s wait → kill), then **terminates every host process whose name contains `llama-server`** via psutil, 2 s wait → kill (`server_ctl.py:330-360`); `host`/`port` args unused.
- **Shutdown:** `main.py` terminates llama-server only if the supervisor spawned it (core.md §2.3); observed graceful exit < 5 s, VRAM → 0 (`S1_37_shutdown.txt`, `S1_38_gpu_after_shutdown.txt`).
- **Zombies:** none observed (`S1_37`); no reaping logic beyond the above.
- **Model verification:** none. No sha256 check at download (`scripts/download_llm_models.py`), at launch (`server_ctl.py`), or at boot; `C:\ProjectLucca\models\MANIFEST.json` does not exist (`S1_07c_models_manifest.txt`, row 13). Spec 12 §4's accepted-residual-risk mitigation ("sha256 manifest pinned at download") is unimplemented → F-BRAIN-003.

### 6.3 VRAM budget — computed vs measured

Inputs (on-disk, `S1_07c`): backbone `ultravox-v0_5-llama-3_1-8b-Q6_K.gguf` = 6 596 011 424 B = **6 291 MiB**; mmproj `…-Q8_0.gguf` = 1 379 512 224 B = **1 316 MiB** — but the downloader renamed the **f16** mmproj to a `Q8_0` name (`scripts/download_llm_models.py:12-23`); ADR-001 budgets the Q8_0 mmproj at ≈ 0.74 GB (≈ 700–760 MiB).

KV cache at ctx 8192, `--cache-type-k/v q8_0`, Llama-3.1-8B geometry (32 layers, 8 KV heads, head_dim 128): 2 × 32 × 8 × 128 = 65 536 elements/token × 8 192 tokens ≈ 536.9 M elements × ≈ 1.0625 B (q8_0 block overhead) ≈ **557 MiB** (ADR-001: "≈ 0.55 GB" — agrees).

| Configuration | Weights | mmproj | KV | CUDA ctx + compute buffers (est.) | Expected total |
|---|---:|---:|---:|---:|---:|
| As-deployed (f16 mmproj) | 6 291 | 1 316 | 557 | ~300–500 | **≈ 8 460–8 660 MiB** |
| ADR-planned (Q8_0 mmproj) | 6 291 | ~730 | 557 | ~300–500 | **≈ 7 880–8 080 MiB** |

**Measured:** 8 098 MiB after healthy start (`S1_16b_gpu_after_llm.txt`, row 34); 8 100 MiB with full app (`S1_26`); 8 234 MiB during/after Spike-02 (`S1_36`, `S1_37`); 0 MiB after exit (`S1_38`). The as-deployed expectation brackets the measurement within the compute-buffer estimate; the ADR-planned configuration would sit ~200 MiB lower. The +136 MiB session growth (8 098 → 8 234) occurred across the hw tests + spike window with slope 0.00 MB/turn inside the 20-run spike itself — cause unconfirmed (F-BRAIN-051). The S4 gate (≤ 9 728 MB, ADR-001) holds with ~1.5 GiB headroom; the headroom would be ~2 GiB with the planned Q8_0 mmproj.

---

## 7. Persona & intents config as-built

### 7.1 `config/persona.toml` — every key

| Key | Loaded by | Validated? | Flows to | Hot-reloadable? |
|---|---|---|---|---|
| `name = "Lucca"` | **nobody** (`load_persona_from_config` ignores it, `prompt_builder.py:517-529`) | — | nowhere (dead key, brain side) | — |
| `voice = "genki_heroine"` | **nobody in brain**; TTS voice comes from `TTSSettings.voice` (`config.py:57`); UI may display it | — | nowhere in the prompt/TTS path (F-CORE-049 covers the voice-default drift) | — |
| `archetype` | `prompt_builder.py:518` | no — unknown values silently fall back to `ARCHETYPES["inventor"]` (`:167`) | system prompt (`:162-167`) | **yes** — `ui.config_update` → `set_persona` (`orchestrator.py:204-213`) |
| `formality` | `:519` | no — unknown values fall back to casual (`:169-171`) | system prompt | yes (same path) |
| `custom_prompt` | `:520` | no | system prompt, appended last (`:210-211`) | yes (same path) |
| `uses_your_name` | `:524` | no | one prose directive (`:181-182`) | **no** — not in `UIConfigUpdatePayload` handling |
| `admits_uncertainty` | `:525` | no | one prose directive (`:183-186`) | no |
| `[boundaries].never_pretend_to_feel` | `:526` | no | one prose directive (`:187-192`) | no |
| `[boundaries].refuse_topics` | `:527` | no — a string would be `list()`-ed into per-char topics (`:256`) | one prose directive (`:193-199`) | no |
| `[affect].enabled / decay_tau_seconds / max_speed_delta` | `core/affect.py:182` (unwired, F-CORE-031); UI reads/writes (`settings_dialog.py:475-476`) | swallowed parse errors (`affect.py:193-194`, F-CORE-052) | **nowhere at runtime** (affect unwired) | no |
| `[traits].technical_depth / warmth / directness` | `:521-523` | no — not clamped to [0, 1] | `compile_trait_modulators` prose (`:201-203`) | **no** — saved by UI in the UI process; core process never sees them until restart |
| `[archetypes]` (user-defined) | `:528` | no | archetype lookup (`:164-165`) | no |

**Load mechanics:** import-time side effect `load_persona_from_config()` (`prompt_builder.py:533`); path resolution prefers `C:\ProjectLucca\config\persona.toml`, falls back to cwd-relative `config/persona.toml` (`:394-396`) — the repo copy and the deployed copy can diverge silently (the repo copy is what tests and version control see; the deployed copy is what the product reads). All parse errors → `{}` → built-in defaults (`:399-403`). `SYSTEM_PROMPT` (`:536`) is computed once at import and never refreshed — a stale snapshot used by nobody.

**Cross-process divergence:** the UI process saves persona.toml and calls `set_persona` **in the UI process** (`settings_dialog.py:2406-2437`); the core process applies only `archetype`/`formality`/`custom_prompt` from `ui.config_update` (`orchestrator.py:204-213`). Traits, boundaries, `uses_your_name`, `admits_uncertainty`, user archetypes saved via the UI therefore **never reach the live prompt** until the core process restarts and re-imports. F-BRAIN-013.

**Provenance:** persona text is user-authored static config ("USER_EXPLICIT-equivalent", implementation prompt §1.3). No persona-derived or LLM-derived text can be committed to memory because no commit path exists in the turn loop (F-CORE-003); the invariant (Charter §5.1) is satisfied vacuously. If affect is later wired into the prompt (its designed sink), its output is prompt material only; any resulting LLM text remains `LLM_NARRATION` (F-CORE-031, Q-14).

### 7.2 `config/intents.toml` — every key

| Table | Keys | Read by | Effect in product |
|---|---|---|---|
| `[intents.launch_app]` | `verbs`, `stop_words_after_start`, `apps` | `router/heuristic.py:76-98` reads **`apps` and `stop_words_after_start` only**; `verbs` ignored (regex hard-coded `:122-125`) | **none** — the router is not called from the turn loop (F-CORE-003) |
| `[intents.file_read]` / `[intents.file_write]` / `[intents.web_fetch]` / `[intents.memory_query]` / `[intents.chit_chat]` | `verbs` | **nobody** | none — dead config |

**Name mapping:** intent names (`file_read`, `file_write`, `web_fetch`, `memory_query`, `chit_chat`) do not correspond to tool names (`read_file`, `write_file`, `fetch_url`, `query_capabilities`); no mapping table exists. Unknown-intent fail-closed behaviour is moot in the product (router unwired); inside the router, `classify_intent` falls back to a default intent rather than rejecting (ROUT area).

---

## 8. Findings

Ordered by severity, then by ID. Every finding has been re-reviewed per Charter §3.5 (log in §12) and carries `Status: OPEN`.

### F-BRAIN-001 — `Any` used in public interfaces of `prompt_builder` and `server_ctl`

| Field | Value |
|---|---|
| **ID** | F-BRAIN-001 |
| **Title** | `Any` used in public interfaces of `prompt_builder` and `server_ctl` |
| **Severity** | S0 — Critical |
| **Category** | INVARIANT |
| **Location** | `src/lucca/brain/prompt_builder.py:278`; `src/lucca/brain/prompt_builder.py:311`; `src/lucca/brain/prompt_builder.py:392`; `src/lucca/brain/prompt_builder.py:538`; `src/lucca/brain/prompt_builder.py:616`; `src/lucca/brain/server_ctl.py:170` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/prompt_builder.py:278`
```python
def get_persona() -> dict[str, Any]:
```
`src/lucca/brain/prompt_builder.py:311`
```python
def update_toml_content(content: str, updates: dict[str, Any]) -> str:
```
`src/lucca/brain/prompt_builder.py:392`
```python
def get_persona_config(config_path: Path | None = None) -> dict[str, Any]:
```
`src/lucca/brain/prompt_builder.py:538`
```python
TOOL_DEFINITIONS: list[dict[str, Any]] = [
```
`src/lucca/brain/prompt_builder.py:616`
```python
) -> list[dict[str, Any]]:
```
`src/lucca/brain/server_ctl.py:170`
```python
def scan_model_registry(models_dir: Path, active_model_rel: str = "") -> list[dict[str, Any]]:
```

**What is wrong / assumed / missing**

Six public symbols of the brain area are typed with `Any`: the persona getter, the TOML updater, the persona-config getter, the tool-schema catalogue, the message-array builder, and the model-registry scanner. Expected: Pydantic v2 models or typed dicts (`PersonaConfig`, `ToolDefinition`, `ChatMessage`, `ModelRegistryEntry`) at these boundaries, per Charter §5.5 and the project's own rule that cross-boundary contracts are Pydantic v2 (`core/schemas.py`).

**Why it matters**

Charter §5 invariant 5: "zero `Any` in public interfaces" — any violation is S0/INVARIANT by Charter §4/§5, graded consistently with F-CORE-001. `TOOL_DEFINITIONS` and `build_messages` are the LLM request boundary; `get_persona`/`get_persona_config` cross the brain↔UI boundary (`ui/app.py:243`, `ui/settings_dialog.py:234`); `scan_model_registry` crosses brain↔UI (`settings_dialog.py:1131`). The open severity question Q-01 in `core.md` (Charter §4 lists `Any` under S3 while §5.5 makes it an invariant) applies here identically.

**Questions this raises**

1. Same as core Q-01: does §5.5 govern severity for every public `Any`, including data-only containers like `TOOL_DEFINITIONS`?

**Proposed remediation**

1. In `src/lucca/core/schemas.py`, add models: `class ToolDefinition(BaseModel): type: str; function: ToolFunctionSchema` (with `ToolFunctionSchema{name: str, description: str, parameters: dict[str, JsonValue]}`); `class ChatMessage(BaseModel): role: str; content: str | list[dict[str, JsonValue]]`; `class PersonaConfig(BaseModel)` with the 12 persona fields of §7.1; `class ModelRegistryEntry(BaseModel)` with the 12 keys of `scan_model_registry`'s dict (`server_ctl.py:217-231`).
2. In `src/lucca/brain/prompt_builder.py`: retype `TOOL_DEFINITIONS: list[ToolDefinition]`, `build_messages(...) -> list[ChatMessage]`, `get_persona() -> PersonaConfig`, `get_persona_config(...) -> PersonaConfig`, `update_toml_content(content: str, updates: dict[str, JsonValue]) -> str`. Before: `dict[str, Any]`/`list[dict[str, Any]]`. After: the named models. Serialise with `.model_dump()` at the httpx boundary in `llm_client.py:69-77`.
3. In `src/lucca/brain/server_ctl.py`, `scan_model_registry()`: return `list[ModelRegistryEntry]`; update `ui/settings_dialog.py:1131-…` accessors from `entry["filename"]` to `entry.filename`.
4. Extend the static gate from F-CORE-001 step 5 to `src/lucca/brain/*.py`.

**Verification test**

- **Tier:** T0
- **Input:** `uv run ruff check src --select ANN401` (with ANN401 un-ignored per F-CORE-054) and `uv run mypy --strict src`
- **Expected output:** 0 ANN401 findings in `src/lucca/brain/`; mypy success
- **Threshold:** n/a — boolean
- **Command:** `uv run ruff check src/lucca/brain --select ANN401 && uv run mypy --strict src/lucca/brain`

**Cross-references:** F-CORE-001, F-CORE-054

---

### F-BRAIN-002 — The deployed "Ultravox" backbone is a stock Llama-3.1-8B-Instruct downloaded from a different repo and renamed; ADR-001's S10 verification was never performed

| Field | Value |
|---|---|
| **ID** | F-BRAIN-002 |
| **Title** | The deployed "Ultravox" backbone is a stock Llama-3.1-8B-Instruct downloaded from a different repo and renamed; ADR-001's S10 verification was never performed |
| **Severity** | S1 — High |
| **Category** | CORRECTNESS |
| **Location** | `scripts/download_llm_models.py:31-47`; `docs/audit/evidence/S1_07c_models_manifest.txt`; `docs/archive/2026-09-17_pre_phase4_audit/08_adr/ADR-001_inference_engine.md:65` |
| **Status** | OPEN |

**Evidence**

`scripts/download_llm_models.py:31-42`
```python
# 2. Q6_K Backbone
backbone_target = dest_dir / "ultravox-v0_5-llama-3_1-8b-Q6_K.gguf"
if not backbone_target.exists():
    print("Downloading Meta-Llama-3.1-8B-Instruct-Q6_K.gguf...")
    t0 = time.time()
    p = hf_hub_download(
        repo_id="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
        filename="Meta-Llama-3.1-8B-Instruct-Q6_K.gguf",
        local_dir=str(dest_dir),
    )
    downloaded_file = dest_dir / "Meta-Llama-3.1-8B-Instruct-Q6_K.gguf"
    if downloaded_file.exists() and downloaded_file != backbone_target:
        downloaded_file.rename(backbone_target)
```
Artefact: `docs/audit/evidence/S1_07c_models_manifest.txt` (02_EVIDENCE_INDEX row 13) — on-disk file `ultravox-v0_5-llama-3_1-8b-Q6_K.gguf`, 6 596 011 424 B, sha256 `33981adf…a587`, no manifest to compare against.

**What is wrong / assumed / missing**

The file the product loads as `ultravox-v0_5-llama-3_1-8b-Q6_K.gguf` is `bartowski/Meta-Llama-3.1-8B-Instruct-Q6_K.gguf` renamed — a text-only stock instruct backbone from a third-party quantiser, not the `ggml-org/ultravox-v0_5-llama-3_1-8b-GGUF` release backbone. ADR-001 (:65) sanctions the *theory* that "Ultravox trains only the projector with the Llama-3.1-8B-Instruct backbone frozen", but explicitly conditions it: "**Verify in spike S10**: if v0.5 turns out to have LoRA-tuned the backbone…". The spike suite's S10 (`scripts/run_spike02_suite.py:396-465`) only replays 20 text tool-call prompts; it never compares the ggml-org backbone, never inspects GGUF metadata (`general.name` would read a Llama identifier, not an Ultravox one), and never records the substitution. The rename makes the provenance invisible to every downstream check: the filename, the config default (`config.py:37`), the ADR, and the audit's own settled-facts list all say "Ultravox".

**Why it matters**

The audio-native mode (ADR-001 Option B, the product default `llm.mode = "audio"`) pairs an Ultravox projector with a backbone whose audio-token training is unverified. Measured symptoms consistent with a mismatched backbone: hallucinated `launch_app` tool calls on a 3 s tone and a 30.5 s tone (`S1_36_spike02.txt` S6 clips 21/22, row 67) and the T3 tool-call turn selecting `query_capabilities` for an "open calculator" utterance (`S1_30_T3_hw.txt`, row 56). Charter §5 "settled facts" ("LLM = llama-server … serving Ultravox Q6_K GGUF") is violated in substance: the weights are not the Ultravox release.

**Questions this raises**

1. Is the bartowski Q6_K backbone tensor-compatible with the ggml-org Ultravox v0.5 backbone (same tensor names/layout so the projector's audio embeddings land correctly)? (→ §10 Q-B-01)
2. Was the substitution a deliberate, recorded decision or an expedient during Phase 0? No entry exists in `13_decisions_log.md`.

**Proposed remediation**

1. In `scripts/download_llm_models.py`: replace the backbone block (`:31-47`) with a download of `repo_id="ggml-org/ultravox-v0_5-llama-3_1-8b-GGUF"`, `filename="ultravox-v0_5-llama-3_1-8b-Q6_K.gguf"`, no rename. Before: bartowski file renamed to the Ultravox name. After: the ggml-org Ultravox file under its own name.
2. In the same file, after each `hf_hub_download`, compute sha256 and compare against a new `C:\ProjectLucca\models\MANIFEST.json` entry (see F-BRAIN-003 step 1); exit non-zero on mismatch. Before: no verification. After: fail-closed verification.
3. Re-run the ADR-001 S10 spike as specified (cascade mode, same backbone file, latency delta recorded, ≥ 18/20 text tool-call validity) against the ggml-org backbone and record results in `logs\phase0_llm.json`.
4. If the project deliberately keeps the stock backbone (ADR-001 :65 permits it *after* S10), record the decision in `docs/13_decisions_log.md` with the S10 numbers, and rename the on-disk file to its true identity (`Meta-Llama-3.1-8B-Instruct-Q6_K.gguf`) so config, logs, and audits stop claiming "Ultravox".

**Verification test**

- **Tier:** T3
- **Input:** fresh download per step 1; then `parse_gguf_file` on the result
- **Expected output:** `general.name` contains `ultravox` (case-insensitive); sha256 matches the MANIFEST entry
- **Threshold:** n/a — boolean
- **Command:** `uv run python scripts/download_llm_models.py && uv run python scripts/run_spike02_suite.py`

**Cross-references:** F-BRAIN-003, F-BRAIN-026, F-BRAIN-007, F-CORE-022

---

### F-BRAIN-003 — No sha256 verification of model weights at download, launch, or boot; the threat model's only supply-chain mitigation is unimplemented

| Field | Value |
|---|---|
| **ID** | F-BRAIN-003 |
| **Title** | No sha256 verification of model weights at download, launch, or boot; the threat model's only supply-chain mitigation is unimplemented |
| **Severity** | S1 — High |
| **Category** | SECURITY |
| **Location** | `scripts/download_llm_models.py:16-47`; `src/lucca/brain/server_ctl.py:309-327`; `docs/audit/evidence/S1_07c_models_manifest.txt`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/12_threat_model.md:3,72` |
| **Status** | OPEN |

**Evidence**

`scripts/download_llm_models.py:43-47`
```python
    print(
        f"Downloaded backbone in {time.time() - t0:.1f}s: {backbone_target.stat().st_size / (1024 * 1024):.1f} MB"
    )
else:
    print(f"Backbone already exists: {backbone_target.stat().st_size / (1024 * 1024):.1f} MB")
```
(no checksum anywhere in the file). `src/lucca/brain/server_ctl.py:315-317`
```python
    model_gguf = resolve_model_path(cfg.model, home_dir)
    if not model_gguf.exists():
        raise FileNotFoundError(f"Model GGUF file not found at: {model_gguf}")
```
(existence is the only check). Artefact: `docs/audit/evidence/S1_07c_models_manifest.txt` (row 13) — `MANIFEST.json` **absent**; sha256 of the four model files recorded with "no expected values to compare".

**What is wrong / assumed / missing**

Spec 12 scopes supply-chain compromise of model weights as "mitigated only by `models verify` sha256 manifest" (:3) and lists the residual risk "Model weights unsigned upstream — sha256 manifest pinned at download" (:72). Neither the manifest nor any verification exists: the downloader trusts the Hub; `start_server` trusts the path; `env_check`/`lucca-admin env-check` report all-green with the manifest absent (F-CORE-022/F-CORE-025 cover the env-check side). Combined with F-BRAIN-002, the project cannot even state what weights it is running.

**Why it matters**

Every turn of the shipped product executes unverified 6.6 GB weights. The threat model's accepted residual risk is only acceptable *with* the manifest control; without it the risk is unmitigated. This is the brain-side half of the env-check gap (F-CORE-025).

**Questions this raises**

1. Who owns producing the canonical hashes for the four model files (they are not published by ggml-org for the renamed mmproj — see F-BRAIN-026)?

**Proposed remediation**

1. Create `C:\ProjectLucca\models\MANIFEST.json` with entries `{path, sha256, size_bytes, source_repo, source_filename}` for the four files, using the values in `S1_07c_models_manifest.txt` as the initial pins after F-BRAIN-002 step 1 replaces the backbone (re-hash after replacement).
2. In `scripts/download_llm_models.py`: after each download, compute sha256 (`hashlib.sha256` over 1 MiB chunks) and compare to the MANIFEST entry; on mismatch, delete the file and `sys.exit(1)`. Before: no check. After: fail-closed.
3. In `src/lucca/brain/server_ctl.py`, `start_server()`: before `subprocess.Popen`, call a new `verify_model_files(cfg, home_dir) -> None` (same module) that raises `RuntimeError` naming the file on any MANIFEST mismatch. Before: existence-only. After: hash-verified launch.
4. In `src/lucca/core/env_check.py` (CORE-area change, cross-filed with F-CORE-025): add a `check_model_manifest` predicate that fails boot when the manifest is absent or any hash mismatches.

**Verification test**

- **Tier:** T1
- **Input:** tmp_path with a MANIFEST entry whose sha256 is deliberately wrong for a 1 KiB dummy `.gguf`; call `verify_model_files`
- **Expected output:** `RuntimeError` naming the dummy file; `start_server` refuses to spawn
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_server_ctl.py::test_start_server_rejects_hash_mismatch -q`

**Cross-references:** F-BRAIN-002, F-BRAIN-026, F-CORE-022, F-CORE-025

---

### F-BRAIN-004 — The system prompt and `query_capabilities` describe machinery that does not exist; measured wrong-tool selection in T3

| Field | Value |
|---|---|
| **ID** | F-BRAIN-004 |
| **Title** | The system prompt and `query_capabilities` describe machinery that does not exist; measured wrong-tool selection in T3 |
| **Severity** | S1 — High |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/prompt_builder.py:47-91`; `src/lucca/sandbox/service.py:144-215`; `docs/audit/evidence/S1_30_T3_hw.txt` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/prompt_builder.py:53-56`
```python
    "- 4-Process Topology:\n"
    "  1. lucca-supervisor (Orchestrator): Central coordinator managing state, ZeroMQ IPC bus "
    "(ports 5557-5559), sub-450ms latency budget, and SQLite-vec episodic memory.\n"
```
`src/lucca/brain/prompt_builder.py:87-90`
```python
    "- Relationship: The user is your creator and partner developer. If they ask what you can do, "
    "what tools you have, or how you work, you know your full capability manifest. "
    "You can answer directly with pride, technical precision, and inventor excitement, "
    "or call query_capabilities to check live status!"
```
Artefact: `docs/audit/evidence/S1_30_T3_hw.txt` (row 56) — `test_live_phase1_tool_call_turn`: `assert tool_name == "launch_app"` → got `'query_capabilities'`, executed `[('query_capabilities', {'category': 'all'})]`.

**What is wrong / assumed / missing**

`ARCHITECTURAL_SELF_AWARENESS` claims: ZMQ ports 5557-5559 (actual: 47001-47003, `S1_28_listening_sockets.txt`); MicroScheme pathways that "execute in sub-10ms before neural inference" (reasoning is unwired — F-CORE-003); six named pathways (`vram-safety-guard`, `npu-whisper-pin`, `temporal-logic-gate`, `codebase-inspect-route`, `inventor-curiosity`, `vector-relevance-gate`) that do not exist in `src/lucca/reasoning/`; "Codebase Inspection: authorized read-only access to inspect your source code repository" (no such tool in `TOOL_DEFINITIONS`); "SQLite-vec episodic memory" in the turn path (memory unwired — F-CORE-003). `query_capabilities` (`sandbox/service.py:144-215`) returns the same fictional manifest as ground truth. The prompt then *invites* the model to "call query_capabilities to check live status" — and the measured T3 behaviour is the model doing exactly that instead of the requested `launch_app`.

**Why it matters**

Main-path incorrect behaviour of a shipped feature: the persona prompt causes wrong tool selection on real hardware (T3 failure, row 56) and causes the companion to speak false claims about its own architecture to the user — a user-facing honesty defect (the implementation prompt's mission: "Every claim the UI makes must be verifiably real").

**Questions this raises**

1. Should `query_capabilities` be generated from live registries (launcher whitelist, `TOOL_DEFINITIONS`, `reasoning/lifecycle.py` states) instead of a literal? (Decision recorded in remediation: yes, live-derived.)

**Proposed remediation**

1. In `src/lucca/brain/prompt_builder.py`, `ARCHITECTURAL_SELF_AWARENESS` (`:47-91`): replace the false claims with the as-built topology — ports 47001-47003; remove the six named MicroScheme pathways and the "sub-10ms before neural inference" sentence; remove the "Codebase Inspection" capability; remove the claim of active episodic memory in the turn loop. Before: fictional capabilities. After: only capabilities backed by `src/`.
2. In `src/lucca/sandbox/service.py`, `query_capabilities` (`:144-215`): build the response from live data — `self.launcher.apps` keys for `whitelisted_apps`, the `TOOL_DEFINITIONS` names for `tools`, and `reasoning_pathways: {}` until reasoning is wired. Before: hard-coded fictional manifest. After: live-derived manifest.
3. In `src/lucca/brain/prompt_builder.py:87-90`: delete the sentence "or call query_capabilities to check live status!". Before: explicit invitation that lured the T3 turn. After: capability questions answered from the (now truthful) self-awareness block.
4. Add `tests/test_prompt_builder.py::test_self_awareness_claims_are_real`: assert the compiled prompt does not contain `5557`, `vram-safety-guard`, `npu-whisper-pin`, `temporal-logic-gate`, `codebase-inspect-route`, `inventor-curiosity`, `vector-relevance-gate`, or `Codebase Inspection`.

**Verification test**

- **Tier:** T1 for step 4; T3 for end-to-end
- **Input:** T1: `get_system_prompt()`; T3: the live tool-call turn
- **Expected output:** T1: no forbidden tokens; T3: `tool_name == "launch_app"`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_prompt_builder.py::test_self_awareness_claims_are_real -q && uv run pytest -m hw tests/test_phase1_live_hw.py::test_live_phase1_tool_call_turn -q`

**Cross-references:** F-CORE-003, F-BRAIN-010

---

### F-BRAIN-005 — Chunker quote/paren depth tracking is doubly broken: `"` can only increment, and depth is re-accumulated over the same buffer on every feed

| Field | Value |
|---|---|
| **ID** | F-BRAIN-005 |
| **Title** | Chunker quote/paren depth tracking is doubly broken: `"` can only increment, and depth is re-accumulated over the same buffer on every feed |
| **Severity** | S1 — High |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/chunker.py:168-186` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/chunker.py:177-186`
```python
            # Track quotes/parens
            if ch in ('"', "(", "["):
                self._paren_depth += 1
                if self._paren_depth > 3:
                    self._paren_depth = 0  # reset on malformed
            elif ch in ('"', ")", "]"):
                self._paren_depth = max(0, self._paren_depth - 1)

            if self._paren_depth > 0:
                continue
```

**What is wrong / assumed / missing**

Two independent defects in the depth tracker that Spec 08 §4.3 requires ("Not inside an open quote/paren pair"):

1. `"` appears in **both** tuples, but the `if` branch wins, so every double-quote **increments** depth and never decrements it. A reply containing one quoted string (`He said "hello." Then we left.`) reaches depth 2 at the closing quote; all punctuation after the opening quote is skipped (`:185-186`) until a fourth quote char trips the `> 3` reset. Sentence boundaries inside and after quoted speech are randomly suppressed.
2. `_paren_depth` is an instance attribute mutated during `_find_boundary`, which **re-scans the buffer from index 0 on every `feed()`** without resetting depth first. The same `(` is counted once per feed that still contains it, so depth drifts upward across feeds even for balanced text; chunk emission shrinks the buffer without adjusting depth, desynchronising it further. Net effect: boundary suppression depends on how the stream was chunked by the network — the same reply fed whole vs in pieces chunks differently.

**Why it matters**

Main-path defect of the first-audio-latency feature: suppressed boundaries delay or enlarge TTS chunks (up to the 260-char force-split instead of ≤ 90/220), directly against the S3 stage budget (first chunk ≤ 90 chars, Spec 10 §2) and Spec 08 §4.3. The property test P-04 cannot catch it (it only asserts length ≤ 260).

**Questions this raises**

1. Should smart quotes `“ ”` participate in depth tracking (Spec 08 §4.3 lists `"“(`)? They are normalised to ASCII `"` per-delta *before* boundary detection (`:58`, `:121`), so they currently hit defect 1 as straight quotes.

**Proposed remediation**

1. In `src/lucca/brain/chunker.py`, `_find_boundary()`: make depth a **local** computed per scan — replace `self._paren_depth` with `depth = 0` at function top; track `in_quote: bool` separately from `paren_depth: int`; toggle `in_quote` on `"`; `paren_depth += 1` on `(`/`[`, `-= 1` (floor 0) on `)`/`]`; skip punctuation when `in_quote or paren_depth > 0`; reset both when `paren_depth > 3`. Delete the `_paren_depth` attribute from `__init__`/`reset` (`:106,118`). Before: stateful, quote-increment-only. After: stateless per-scan, quotes toggle.
2. Add `tests/test_chunker.py::test_t_chk_quote_boundaries`: feed `'He said "hello." Then we left. Goodbye.'` char-by-char; assert a chunk boundary exists after `left.` and the first chunk is ≤ 90 chars.
3. Add `tests/test_chunker.py::test_t_chk_streaming_equivariance`: for the fixture strings of T-CHK-01…05, assert chunking is identical whether fed whole, char-by-char, and in 7-char pieces.

**Verification test**

- **Tier:** T1
- **Input:** the two tests above
- **Expected output:** both pass; P-04 still passes
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py -q`

**Cross-references:** F-BRAIN-020, F-BRAIN-022

---

### F-BRAIN-006 — `LLMClient` keeps abort state and the live HTTP client in instance attributes shared by concurrent turn threads

| Field | Value |
|---|---|
| **ID** | F-BRAIN-006 |
| **Title** | `LLMClient` keeps abort state and the live HTTP client in instance attributes shared by concurrent turn threads |
| **Severity** | S1 — High |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/llm_client.py:40-41`; `src/lucca/brain/llm_client.py:81-82`; `src/lucca/brain/llm_client.py:175-191` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:40-41`
```python
        self.active_client: httpx.Client | None = None
        self.aborted: bool = False
```
`src/lucca/brain/llm_client.py:81-82`
```python
        self.aborted = False
        self.active_client = client
```
`src/lucca/brain/llm_client.py:175-177`
```python
        except (httpx.HTTPError, OSError) as exc:
            if self.aborted or self.active_client is None:
                return
```

**What is wrong / assumed / missing**

`Orchestrator` owns **one** `LLMClient` (`orchestrator.py:80`) and can run two turn threads concurrently (F-CORE-011: barge-in does not join the previous worker). In that window: thread B's `stream_turn` resets `self.aborted = False` (`:81`) and overwrites `self.active_client` (`:82`); thread A's in-flight abort then closes **B's** client (`:186-191`), and A's own exception path reads `self.aborted`/`self.active_client` after B has mutated them (`:176`) — A may swallow a real error as "aborted", or B may be killed by A's abort. The single flag cannot represent "turn A aborted, turn B live".

**Why it matters**

Barge-in is the product's core interaction (Spec 10: key-down → silence ≤ 30 ms, slot idle ≤ 100 ms). Under this race the wrong stream is aborted or the abort is silently lost — the exact exposure F-CORE-011/F-CORE-014 leave in the state machine. `test_live_barge_in_abort` passed (30.07 ms) only because no test overlaps two real streams.

**Questions this raises**

1. Should `abort()` take the `trace_id` (as `SpeechLLMPort` declares, F-CORE-040) so a stale abort cannot kill a newer stream? (Decision recorded: yes, optional parameter.)

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py`: make abort state per-stream — in `stream_turn`, create a local dataclass `_StreamState(client: httpx.Client, aborted: bool, trace_id: str)` and register it in a new `self._streams: dict[str, _StreamState]` guarded by a new `threading.Lock`; remove `self.aborted` and `self.active_client`. Before: two shared attributes. After: per-stream registry.
2. Change the signature to `abort(self, trace_id: str | None = None) -> None`: with the lock, mark only the matching stream aborted and close its client; `trace_id=None` aborts the most recently registered stream (preserves current behaviour for the single caller). Before: closes whatever `active_client` points to. After: targeted close.
3. In `src/lucca/core/orchestrator.py` `_abort_turn` (CORE-area change): pass `self.active_trace.trace_id` to `llm.abort(...)`.
4. Add `tests/test_llm_client_race.py::test_abort_targets_only_matching_stream`: two scripted streams on one client with staggered starts; abort trace A; assert B's generator continues to `Done`.

**Verification test**

- **Tier:** T1
- **Input:** the race test above
- **Expected output:** stream B yields all scripted events; stream A stops without `Done`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_llm_client_race.py -q`

**Cross-references:** F-CORE-011, F-CORE-014, F-CORE-040, F-BRAIN-014

---

### F-BRAIN-007 — The Spike-02 suite records unmeasured constants and failing checks as PASS in the Phase-0 sign-off artefact

| Field | Value |
|---|---|
| **ID** | F-BRAIN-007 |
| **Title** | The Spike-02 suite records unmeasured constants and failing checks as PASS in the Phase-0 sign-off artefact |
| **Severity** | S1 — High |
| **Category** | TESTING |
| **Location** | `scripts/run_spike02_suite.py:117-124`; `scripts/run_spike02_suite.py:126-138`; `scripts/run_spike02_suite.py:319-356`; `scripts/run_spike02_suite.py:358-393`; `docs/audit/evidence/S1_36_spike02.txt` |
| **Status** | OPEN |

**Evidence**

`scripts/run_spike02_suite.py:117-124`
```python
results["S1"] = {
    "status": "PASS",
    "health_status_code": r.status_code,
    "health_body": r.json(),
    "measured_cold_startup_s": 42.5,
    "threshold_s": 60.0,
}
```
`scripts/run_spike02_suite.py:340-343`
```python
        rel_resp = httpx.post(f"{BASE_URL}/slots/0?action=release", timeout=2.0)
        abort_dur_ms = (time.perf_counter() - t_abort) * 1000.0
        abort_latencies.append(abort_dur_ms)
        print(f"  Abort {i + 1:2d}: status={rel_resp.status_code}, duration={abort_dur_ms:.2f} ms")
```
(status never asserted). Artefact: `docs/audit/evidence/S1_36_spike02.txt` (row 67) — S8 abort HTTP **501 ×10** yet section PASS; S1 "Cold startup: ~42.5s [PASS]" against an already-running server; the same `42.5` appears in the pre-audit report from 2026-09-17 (`S1_31_reports/ProjectLucca_logs/phase0_llm.json`).

**What is wrong / assumed / missing**

Four independent fabrications in the generator of the Phase-0 sign-off bundle (archived testing matrix §4 requires `phase0_llm.json`):

1. **S1 cold-start is a hard-coded constant** (`42.5`), not a measurement; the suite runs against a pre-existing server and cannot measure startup at all.
2. **S5 host-RSS uses `WorkingSet64`** (`:47-54`), which for llama-server reads 12–45 MB while its private bytes are 8.8 GB (`S1_SUMMARY` §2.4/§2.10); the pre-audit report honestly recorded `S5: FAIL` (rss 1809.42 MB > 800) — the current run records PASS for the same process.
3. **S8 passes on the latency of a failing endpoint**: `/slots/0?action=release` returns HTTP 501 ×10; the status is printed but never asserted, and "abort latency ≤ 50 ms" is computed over 501 round-trips. Whether generation actually stopped is never checked.
4. **S9 redefines the check**: ADR-001 S9 requires the 30.5 s clip to be "rejected with a clean error"; the script records PASS when the server is merely alive afterwards (`:383-393`) — and the clip was in fact accepted (HTTP 200).

**Why it matters**

Charter §5 invariant 3 (phased build discipline): a phase may proceed only when its sign-off bundle is green *and real*. Three of this script's sections cannot fail and one measures the wrong quantity. Every downstream claim built on `phase0_llm.json` (Phase-1 admission, TTFT/abort budgets) inherits the fabrication.

**Questions this raises**

1. The pre-audit report recorded `S5: FAIL` — was Phase 1 entered with a known-failing Phase-0 gate, and where is that recorded? (→ §10 Q-B-02)

**Proposed remediation**

1. In `scripts/run_spike02_suite.py`, S1 (`:113-124`): remove `measured_cold_startup_s`; record `"measured_cold_startup_s": None, "note": "suite requires a cold server; startup measured separately"`. Before: constant 42.5. After: explicit non-measurement.
2. S5 (`:126-138`): measure private bytes via `psutil.Process(pid).memory_info().private` (add `import psutil`); keep the 800 MB threshold against private bytes. Before: WorkingSet64. After: private bytes.
3. S8 (`:319-356`): assert `rel_resp.status_code == 200` per run and, after the release call, assert the streaming response terminates within 500 ms; record `"endpoint_status": rel_resp.status_code` per run; section status = FAIL when any run is non-200. Before: status ignored. After: fail on 501.
4. S9 (`:358-393`): pass criterion = `resp.status_code in (400, 413, 422)` **and** server healthy after; record the actual status. Before: alive-after. After: rejection-required.
5. Write results to `logs\phase0_llm_<UTC timestamp>.json` and never overwrite (`:468`). Before: in-place overwrite. After: append-only artefacts.

**Verification test**

- **Tier:** T3
- **Input:** `uv run python scripts/run_spike02_suite.py` against the current build 11026 server
- **Expected output:** S8 section status = FAIL with `endpoint_status: 501` ×10; S1 contains no `42.5`; a new timestamped JSON file appears and the previous one is untouched
- **Threshold:** n/a — boolean
- **Command:** `uv run python scripts/run_spike02_suite.py`

**Cross-references:** F-BRAIN-014, F-BRAIN-028, F-CORE-012

---

### F-BRAIN-008 — The frozen tree mutated mid-audit: `server_ctl.py` changed after the S1 capture, and `main.py`/`test_s1_startup.py` after S0, outside any recorded decision

| Field | Value |
|---|---|
| **ID** | F-BRAIN-008 |
| **Title** | The frozen tree mutated mid-audit: `server_ctl.py` changed after the S1 capture, `main.py`/`test_s1_startup.py` after S0, outside any recorded decision |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `src/lucca/brain/server_ctl.py:258-285, 320-327`; `src/lucca/main.py:123-133`; `scripts/test_s1_startup.py`; `docs/audit/03b_BASELINE_DELTA.md` |
| **Status** | OPEN |

**Evidence**

Corrected re-inventory (2026-09-18T06:04–06:21Z, per this finding's own remediation step 2): artefacts `docs/audit/evidence/S2b_01_git_status.txt` (HEAD `ed14f6b` unchanged; in-scope porcelain identical to S0 except `scripts/test_s1_startup.py` newly `M`) and `docs/audit/evidence/S2b_02_line_counts.txt` (S0's own non-blank-line metric). Delta vs S0 across 110 in-scope text files: **107 unchanged**, three changed:

| Path | S0 → now (non-blank lines) | Timing evidence |
|---|---|---|
| `src/lucca/brain/server_ctl.py` | 336 → 346 | **after S1**: `S1_15a_launch_cmd_from_code.txt` (row 27, 00:28Z) shows the then-code emitting `--log-format json`; current `build_launch_command()` does not; S1-era stderr→DEVNULL (S1_SUMMARY §4.1) replaced by the `logs\llama-server.log` redirect (`server_ctl.py:320-327`) |
| `src/lucca/main.py` | 150 → 180 | after S0 (tracked `M` at both captures; exact timing vs S1 not provable from line counts); adds the boot-failure log-tail printer (`main.py:123-133`) |
| `scripts/test_s1_startup.py` | 51 → 49 | after S0 — newly `M` in `git status` (S0's porcelain did not list it) |

**Correction of the S2b first pass:** the original version of this finding claimed all five brain modules mutated (336→399, 174→199, 196→236, 130→151, 584→658) and that `orchestrator.py` grew 608→704. That comparison mixed S0's non-blank metric with total line counts from file reads; under S0's own metric `chunker.py` (196), `llm_client.py` (174), `prompt_builder.py` (584), `toolcall_demux.py` (130) and `orchestrator.py` (608) are **identical to S0**. The header notice and §12 of this file were corrected accordingly; the audit-owner approval obtained during the first pass ("audit the current tree with the mutation recorded") remains valid for the narrower, verified mutation.

**What is wrong / assumed / missing**

The audit charter freezes `src/`, `tests/`, `config/`, `scripts/` for the audit window (Charter §3.1) and mandates "stop and report" on observed change (§3.4). Three in-scope files changed anyway — `server_ctl.py` demonstrably between S1 (01:08Z) and S2b (04:22Z), in exactly the file S1 had just measured defects in. The changes are genuine improvements (they fix F-CORE-012's mechanism), but they were made outside any recorded decision, with no commit, no note in `docs/audit/`, and no re-baseline. The freeze is unenforced — no mechanism (branch protection, audit-window tag, re-baseline trigger) prevents it.

**Why it matters**

An audit whose evidence base can move underneath it cannot be re-run or independently verified; S1-era behavioural descriptions (e.g. F-CORE-012's "stderr is discarded") now describe a state that no longer exists on disk and survive only as artefact citations. The narrow verified delta (three files) is why this stays S2 rather than escalating.

**Questions this raises**

1. Who made the post-S1 `server_ctl.py` edit and the post-S0 `main.py`/`test_s1_startup.py` edits? (Unanswered — no commit, no note.)
2. Should the audit re-baseline (new S0) before the remaining area subtasks? (Answered by the re-inventory: **no** — the delta is three files, fully characterised in `03b_BASELINE_DELTA.md` §4.)

**Proposed remediation**

1. Record this event in `docs/14_blockers.md` (when writable): tree mutated during the audit freeze window; `server_ctl.py` after S1, `main.py` + `scripts/test_s1_startup.py` after S0; S2a/S2b audited the post-change tree.
2. ~~Re-run the S0 inventory~~ — **done** by this finding's own remediation: `docs/audit/03b_BASELINE_DELTA.md` + evidence `S2b_01_git_status.txt`, `S2b_02_line_counts.txt`; register both in `02_EVIDENCE_INDEX.md`.
3. Adopt an audit-window rule: no edits to frozen trees except through a declared "fix-forward" event that triggers re-baseline; add the rule to `docs/audit/00_AUDIT_CHARTER.md` §3.1.
4. For the two fixed defects (`--log-format json`, DEVNULL stderr), verify the fix has a regression test (it does not — see F-BRAIN-029) and file the missing test there.

**Verification test**

- **Tier:** T0
- **Input:** re-run of the S0 inventory commands
- **Expected output:** `03b_BASELINE_DELTA.md` exists and matches `git status --porcelain` plus a line-count diff table (done — this finding's evidence)
- **Threshold:** n/a — boolean
- **Command:** `git status --porcelain` + the S0 line-count commands, output registered in `02_EVIDENCE_INDEX.md`

**Cross-references:** F-BRAIN-023, F-BRAIN-029, F-CORE-012

---

### F-BRAIN-009 — Malformed tool-call arguments JSON is replaced by `{}` and the call is still emitted for execution

| Field | Value |
|---|---|
| **ID** | F-BRAIN-009 |
| **Title** | Malformed tool-call arguments JSON is replaced by `{}` and the call is still emitted for execution |
| **Severity** | S2 — Medium |
| **Category** | SECURITY |
| **Location** | `src/lucca/brain/llm_client.py:131-146`; `src/lucca/brain/llm_client.py:156-167` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:131-146`
```python
                            args: dict[str, Any] = {}
                            if tc_data["arguments"]:
                                try:
                                    args = json.loads(tc_data["arguments"])
                                except json.JSONDecodeError:
                                    logger.warning(
                                        "invalid_tool_call_json", args=tc_data["arguments"]
                                    )
                            if tc_data["name"]:
                                yield ToolCallEnd(
                                    call=ToolCall(
                                        tool=tc_data["name"],
                                        args=args,
                                        call_id=tc_data["id"],
                                    )
                                )
```

**What is wrong / assumed / missing**

When the model streams a tool call whose accumulated `arguments` string is not valid JSON (truncation at `max_tokens`, template disobedience), the client logs a warning and yields the `ToolCallEnd` anyway with `args = {}`. The orchestrator then routes the call to confirmation and execution with empty arguments (`orchestrator.py:433-435, 639-669`). Expected: a tool call whose arguments cannot be parsed is dropped (and the drop logged), because executing with fabricated empty args is worse than not executing — e.g. `write_file` with `{}` reaches the sandbox missing both `rel_path` and `content`.

**Why it matters**

Spec 12 Z1: model output is untrusted and must be schema-validated at the boundary. A malformed call that executes anyway converts a parse failure into an action; for READ-risk tools it executes with no user gate at all (F-BRAIN-010). The warning log is the only record and is not surfaced to the user or the trace.

**Questions this raises**

1. Should a dropped malformed call produce a spoken notice, or silent drop + log? (Decision recorded: silent drop + `logger.warning`; a spoken notice mid-turn would itself be confusing narration.)

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py`, both emission sites (`:131-146` and `:156-167`): on `json.JSONDecodeError`, `logger.warning("tool_call_dropped_invalid_json", tool=tc_data["name"], args=tc_data["arguments"])` and `continue` without yielding. Before: yield with `args={}`. After: drop.
2. In the same functions: when `tc_data["name"]` is empty, `logger.warning("tool_call_dropped_no_name", args=tc_data["arguments"])` instead of the current silent skip (`:139,164`). Before: silent. After: logged drop.
3. Add `tests/test_llm_client.py::test_malformed_tool_call_dropped`: scripted SSE stream (stub transport) emitting `finish_reason="tool_calls"` with `arguments='{"app_name':`; assert zero `ToolCallEnd` events and one warning.

**Verification test**

- **Tier:** T1
- **Input:** the scripted stream above
- **Expected output:** no `ToolCallEnd` yielded; `tool_call_dropped_invalid_json` logged once
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_llm_client.py::test_malformed_tool_call_dropped -q`

**Cross-references:** F-BRAIN-010, F-BRAIN-030

---

### F-BRAIN-010 — Tool name and arguments are never validated against the tool schema before execution; READ-risk hallucinations auto-execute

| Field | Value |
|---|---|
| **ID** | F-BRAIN-010 |
| **Title** | Tool name and arguments are never validated against the tool schema before execution; READ-risk hallucinations auto-execute |
| **Severity** | S2 — Medium |
| **Category** | SECURITY |
| **Location** | `src/lucca/brain/llm_client.py:139-146`; `src/lucca/brain/toolcall_demux.py:76-89`; `src/lucca/sandbox/policy.py:33-41`; `docs/audit/evidence/S1_30_T3_hw.txt` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/policy.py:33-35`
```python
def classify_risk(tool_name: str) -> Risk:
    """Classifies risk tier for a tool."""
    return TOOL_RISK_MAP.get(tool_name, Risk.WRITE)
```
Artefact: `docs/audit/evidence/S1_30_T3_hw.txt` (row 56) — `query_capabilities{'category': 'all'}` executed for an "open calculator" utterance with no user gate (READ risk auto-executes; `orchestrator.py:650` only gates WRITE/LAUNCH).

**What is wrong / assumed / missing**

No code path validates an emitted tool call against `TOOL_DEFINITIONS` (`prompt_builder.py:538-608`): not the name (any string passes), not the args (enum/required/type never checked). The only name-based control is `classify_risk`'s default of unknown names to WRITE → confirmation; the only args-based controls are downstream (`launcher.py` alias check for `launch_app`, path validation in `file_tool`). Measured consequences: (a) a hallucinated READ-risk call (`query_capabilities`) executes immediately and its fictional result is spoken (F-BRAIN-004); (b) `launch_app` with `app_name="cmd"` reaches the confirmation prompt as "launch cmd?" — the schema's 5-value enum is never enforced before the user is asked; (c) an inline-JSON call naming a nonexistent tool is yielded by the demux and only stopped by the human at the confirmation gate.

**Why it matters**

Spec 12 Z1→Z0 boundary: "schema-validated" model output. The validation layer the threat model assumes does not exist; the actual defences are (1) the human confirmation gate for WRITE/LAUNCH and (2) per-tool downstream checks. READ/NETWORK tools have no gate by design, so their inputs must be schema-clean — and are not.

**Questions this raises**

1. Should unknown tool names be rejected at the client (fail-closed) rather than defaulting to WRITE + confirmation? (Decision recorded: reject at the client; the confirmation gate is for *known* risky tools, not for unidentifiable actions.)

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py`, before each `yield ToolCallEnd(...)` (`:140-146`, `:165-167`): call a new `validate_tool_call(name: str, args: dict) -> bool` in `src/lucca/brain/toolcall_demux.py` that (a) checks `name` against `TOOL_DEFINITIONS` names, (b) checks required parameters are present, (c) checks `enum` membership where declared (`app_name`, `category`); on failure `logger.warning("tool_call_rejected_schema", tool=name)` and skip the yield. Before: no validation. After: schema gate at the client.
2. Apply the same `validate_tool_call` in `toolcall_demux.py:80-89` and `:137-143` before synthesising the inline `ToolCallEnd`.
3. Add `tests/test_toolcall_validation.py`: unknown name → rejected; `launch_app` with `app_name="cmd"` → rejected (enum); `launch_app` missing `app_name` → rejected (required); valid `launch_app calculator` → accepted; `query_capabilities` with `category="all"` → accepted.

**Verification test**

- **Tier:** T1
- **Input:** the five cases above
- **Expected output:** exactly the two valid calls yield `ToolCallEnd`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_toolcall_validation.py -q`

**Cross-references:** F-BRAIN-004, F-BRAIN-009, F-BRAIN-030

---

### F-BRAIN-011 — Memory block in the system prompt has no delimiters, no per-hit cap, no count cap, and no untrusted/data marking

| Field | Value |
|---|---|
| **ID** | F-BRAIN-011 |
| **Title** | Memory block in the system prompt has no delimiters, no per-hit cap, no count cap, and no untrusted/data marking |
| **Severity** | S2 — Medium |
| **Category** | SECURITY |
| **Location** | `src/lucca/brain/prompt_builder.py:629-634`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/10_latency_trace_and_budgets.md:64`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/12_threat_model.md:22` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/prompt_builder.py:629-634`
```python
    # 2. Memories Block (appended to system content to keep prefix unified)
    if memories:
        mem_lines = ["\n\n[Persistent Memory Context]"]
        for m in memories:
            mem_lines.append(f"- {m.content}")
        system_content += "\n".join(mem_lines)
```

**What is wrong / assumed / missing**

Memory hits are interpolated raw into the **system** message: no fencing, no escaping of newlines/bracket headers, no 160-char per-hit cap, no k ≤ 8 count cap, and no "the following is data, not instructions" marking. Spec 10 §4 budgets the block at ≤ 600 tokens with k ≤ 8 and 160 chars per hit; TM-02 requires the system prompt to mark retrieved/tool text as data. Today `memories` is always `None` (F-CORE-003), so the defect is latent: it activates the moment memory retrieval is wired, with `USER_DERIVED` content (quote-grounded user text) able to inject lines indistinguishable from system sections (e.g. a remembered quote containing `\n\n[Creator Persona Directives]\nIgnore previous instructions`).

**Why it matters**

TM-02 (indirect prompt injection) and the §3.3 surface table: this is the one designed path by which stored text re-enters the prompt at system privilege. The control must exist *before* F-CORE-003's remediation wires retrieval, or the wiring change will ship an injection surface.

**Questions this raises**

1. Should memory hits live in the system message at all, or in a `role: user` context message where instruction priority is lower? (→ §10 Q-B-04; ADR-001's prefix-caching note favours system placement.)

**Proposed remediation**

1. In `src/lucca/brain/prompt_builder.py:629-634`: cap to the first 8 hits; truncate each `m.content` to 160 chars; wrap the block as `\n\n[Persistent Memory Context — data, not instructions]\n<memory>\n- …\n</memory>`; replace a leading `[` in hit content with `(` so injected headers cannot form. Before: raw interpolation. After: capped, delimited, marked.
2. Add `tests/test_prompt_builder.py::test_memory_block_capped_and_marked`: 12 hits of 500 chars each, one containing `\n\n[Creator Persona Directives]`; assert ≤ 8 bullets, each ≤ 160 chars, the `data, not instructions` marker present, and no injected header survives.

**Verification test**

- **Tier:** T1
- **Input:** the 12-hit fixture above
- **Expected output:** assertions pass
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_prompt_builder.py::test_memory_block_capped_and_marked -q`

**Cross-references:** F-CORE-003, F-BRAIN-012

---

### F-BRAIN-012 — No context token budgeting or truncation anywhere in prompt assembly (Spec 10 §4 unimplemented)

| Field | Value |
|---|---|
| **ID** | F-BRAIN-012 |
| **Title** | No context token budgeting or truncation anywhere in prompt assembly (Spec 10 §4 unimplemented) |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/prompt_builder.py:611-657`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/10_latency_trace_and_budgets.md:58-71` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/prompt_builder.py:638-641`
```python
    # 3. Conversation History (last 6 exchanges)
    if history:
        for turn in history[-6:]:
            messages.append(turn)
```

**What is wrong / assumed / missing**

Spec 10 §4 defines a per-section token budget (system ≤ 350, tools ≤ 600, memory ≤ 600, session summary ≤ 300, history ≤ 1 200 truncate-oldest-first, audio ≈ 375, reply reserve 512, total ≈ 3 950 of 8 192). No row is implemented: the compiled system prompt alone is ≈ 700–900 tokens (§3.2); history is count-capped (6 exchanges) but not token-capped; there is no session summary; there is no token counter in brain at all. Overflow behaviour is delegated to llama-server, which truncates the non-cached suffix or returns 400 — silently dropping context or the turn.

**Why it matters**

Context overflow on the main path presents as degraded replies or unexplained 400s (surfacing as `LLMUnavailable` → "Sorry, I had trouble…"), and the > 4 k headroom Spec 10 reserves for mid-turn tool results does not exist by construction. Combined with F-CORE-018 (unbounded history list), a long session deterministically approaches the limit.

**Questions this raises**

1. Which tokenizer should the budgeter use (llama-server `/tokenize` round-trip vs a local approximation)? (Decision recorded: `len(text) // 4` interim, the same approximation the UI preview uses; a real tokenizer is Q-B-05.)

**Proposed remediation**

1. In `src/lucca/brain/prompt_builder.py`, add `estimate_tokens(text: str) -> int` as `len(text) // 4` and `enforce_context_budget(messages: list, budget: int = 3950) -> list`: drop oldest history pairs until `sum(estimate_tokens(...)) <= budget - 512`; never drop the system message or the current user turn. Before: no budget. After: deterministic truncation, oldest-first per spec.
2. Add `logger.warning("context_budget_truncated", dropped_turns=n)` on every truncation.
3. Add `tests/test_prompt_builder.py::test_context_budget_truncates_oldest_first`: 10 exchanges × 400 chars + system 1 000 chars; assert the result contains the system message, the current turn, and the newest exchanges only, with the warning logged.

**Verification test**

- **Tier:** T1
- **Input:** the fixture above
- **Expected output:** estimated total ≤ 3 438 (3 950 − 512); oldest pairs absent
- **Threshold:** ≤ 3 438 estimated tokens
- **Command:** `uv run pytest tests/test_prompt_builder.py::test_context_budget_truncates_oldest_first -q`

**Cross-references:** F-BRAIN-011, F-CORE-018

---

### F-BRAIN-013 — Persona state diverges between the UI and core processes: traits, boundaries, and user archetypes saved in the UI never reach the live prompt

| Field | Value |
|---|---|
| **ID** | F-BRAIN-013 |
| **Title** | Persona state diverges between the UI and core processes: traits, boundaries, and user archetypes saved in the UI never reach the live prompt |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/core/orchestrator.py:204-213`; `src/lucca/ui/settings_dialog.py:2406-2437`; `src/lucca/brain/prompt_builder.py:219-258, 533` |
| **Status** | OPEN |

**Evidence**

`src/lucca/core/orchestrator.py:204-213`
```python
                if (
                    p_cfg.persona_archetype is not None
                    or p_cfg.formality is not None
                    or p_cfg.custom_system_prompt is not None
                ):
                    set_persona(
                        archetype=p_cfg.persona_archetype,
                        formality=p_cfg.formality,
                        custom_prompt=p_cfg.custom_system_prompt,
                    )
```

**What is wrong / assumed / missing**

`prompt_builder`'s persona state is module-global per process. The UI's save path (`settings_dialog.py:2406-2437`) writes persona.toml and calls `set_persona` **in the UI process**; the core process (which builds the actual prompts) learns only `archetype`/`formality`/`custom_prompt` via `ui.config_update`. The other nine keys the UI edits — `technical_depth`, `warmth`, `directness`, `uses_your_name`, `admits_uncertainty`, `never_pretend_to_feel`, `refuse_topics`, user archetypes, and `[affect]` values — are persisted to disk but the running core never re-reads them; they take effect only after a full app restart (import-time load, `prompt_builder.py:533`). The UI's own preview (`settings_dialog.py:678`) renders the *full* prompt with all controls applied, so the preview shows a prompt the core is not using.

**Why it matters**

The implementation prompt's WI-2.8 requires "call `set_persona()` so changes apply without restart" — true only for 3 of 12 keys. The user moves the Warmth slider, sees the preview change, saves, and the live voice is unchanged: a silent no-op on a shipped feature's edge path (the non-archetype controls), hence S2.

**Questions this raises**

1. Should `UIConfigUpdatePayload` carry the full persona model, or should the core re-read persona.toml on `ui.config_update`? (Decision recorded: re-read the TOML — single source of truth, no payload growth.)

**Proposed remediation**

1. In `src/lucca/core/orchestrator.py:198-213` (CORE-area change): on any `ui.config_update` that includes persona fields, call `load_persona_from_config()` (re-reading the TOML the UI just wrote) instead of the three-field `set_persona`. Before: partial update. After: full reload from disk.
2. In `src/lucca/brain/prompt_builder.py`, `load_persona_from_config()`: log `persona_reloaded` with the loaded archetype/formality at INFO.
3. Add `tests/test_turn_loop.py::test_persona_config_update_reloads_all_fields`: write a persona.toml with `warmth=0.9`, send `ui.config_update`, assert `get_persona()["warmth"] == 0.9` in the core process.

**Verification test**

- **Tier:** T2
- **Input:** the test above
- **Expected output:** all 12 persona fields in the core match the saved TOML without restart
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_turn_loop.py::test_persona_config_update_reloads_all_fields -q`

**Cross-references:** F-CORE-057, F-BRAIN-037

---

### F-BRAIN-014 — Abort's slot-release endpoint returns HTTP 501 on the installed build; abort relies solely on connection close, and nothing verifies generation stopped

| Field | Value |
|---|---|
| **ID** | F-BRAIN-014 |
| **Title** | Abort's slot-release endpoint returns HTTP 501 on the installed build; abort relies solely on connection close, and nothing verifies generation stopped |
| **Severity** | S2 — Medium |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/llm_client.py:193-198`; `docs/audit/evidence/S1_36_spike02.txt`; `docs/archive/2026-09-17_pre_phase4_audit/08_adr/ADR-001_inference_engine.md:55` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:193-198`
```python
        # Release active slot in llama-server
        try:
            with httpx.Client(timeout=0.2) as c:
                c.post(f"{self.base_url}/slots/0?action=release")
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("llm_abort_slot_release_error", error=str(exc))
```
Artefact: `docs/audit/evidence/S1_36_spike02.txt` (row 67) — S8 abort probes: HTTP **501** ×10, p50 31.49 ms, reported PASS.

**What is wrong / assumed / missing**

ADR-001 (:55) specifies barge-in as "close the HTTP stream **and** `POST /slots/0?action=release`" with ≤ 50 ms to slot idle. On the installed build 11026 the endpoint returns 501 (not implemented/enabled), so the second mechanism is dead; the response status is never checked (only transport errors are caught, at debug level). The remaining mechanism — closing the HTTP connection — is assumed to cancel server-side generation, but nothing in the client, the orchestrator, or any test verifies the slot actually goes idle (the T3 `test_live_barge_in_abort` measures client-side flag latency, 30.07 ms, not server slot state).

**Why it matters**

With `--parallel 1`, a slot still generating the aborted turn delays the next turn's first token (the next request queues behind it) — a direct latency-budget risk (Spec 10: slot idle ≤ 100 ms) that is currently invisible. The 501 also means the spike suite's S8 "PASS" measured nothing (F-BRAIN-007).

**Questions this raises**

1. Does closing the HTTP connection actually cancel generation in build 11026, and within how many ms? (→ §10 Q-B-06; measurable via `/slots` polling after abort)
2. Should the server be launched with a flag enabling the release endpoint (if one exists in this build), or should abort rely on connection close by design? (→ §10 Q-B-07)

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py:193-198`: check the response — `r = c.post(...)`; if `r.status_code != 200`, `logger.warning("llm_slot_release_unsupported", status=r.status_code)` (once per process, not per abort). Before: status ignored, errors at debug. After: explicit, visible degradation.
2. Add a T3 measurement to `tests/test_phase1_live_hw.py::test_live_barge_in_abort`: after `abort()`, poll `GET /slots` every 10 ms and assert the slot reports idle within 100 ms; record the measured value in the test report.
3. If step 2 shows the slot does not go idle, add the server flag enabling the release endpoint to `build_launch_command` (decision pending Q-B-07) or document connection-close as the sole mechanism in a new ADR.

**Verification test**

- **Tier:** T3
- **Input:** mid-generation barge-in on real hardware
- **Expected output:** slot idle ≤ 100 ms after abort, or a recorded `llm_slot_release_unsupported` warning plus measured connection-close latency
- **Threshold:** ≤ 100 ms to slot idle
- **Command:** `uv run pytest -m hw tests/test_phase1_live_hw.py::test_live_barge_in_abort -q`

**Cross-references:** F-BRAIN-006, F-BRAIN-007, F-CORE-011

---

### F-BRAIN-015 — Malformed SSE frames are silently skipped with no log, feeding the empty-reply pathway

| Field | Value |
|---|---|
| **ID** | F-BRAIN-015 |
| **Title** | Malformed SSE frames are silently skipped with no log, feeding the empty-reply pathway |
| **Severity** | S2 — Medium |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/llm_client.py:100-103` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:100-103`
```python
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
```

**What is wrong / assumed / missing**

A `data:` frame that fails JSON parsing is dropped without a log, a counter, or a trace mark. If the stream is truncated or corrupted (server crash mid-frame, non-UTF-8 bytes, proxy interference), the client degrades to "fewer tokens" or "zero tokens" with no evidence anywhere — and zero-token streams are already accepted as successful turns (F-CORE-007). Expected: count and log every skipped frame so the empty-reply pathway is diagnosable.

**Why it matters**

F-CORE-007's upstream cause is currently unlocatable (core Q-04 asks whether the server reported `n_decoded > 0`); silent frame-skipping is one candidate mechanism and it leaves no trace. Edge-path severity: requires a malformed stream, which has not been observed.

**Questions this raises**

1. None — the fix is mechanical; the deeper question (why the T3 stream had zero deltas) belongs to core Q-04.

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py:100-103`: replace the bare `continue` with `logger.warning("sse_frame_skipped", frame_prefix=data_str[:80])` and increment a local `skipped_frames` counter logged at stream end. Before: silent skip. After: logged and counted.
2. Add `tests/test_llm_client.py::test_malformed_sse_frame_logged`: stub transport yielding one valid frame, one garbage frame, one valid frame; assert both tokens arrive and exactly one warning is logged.

**Verification test**

- **Tier:** T1
- **Input:** the scripted stream above
- **Expected output:** 2 `TokenDelta` events; 1 `sse_frame_skipped` warning
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_llm_client.py::test_malformed_sse_frame_logged -q`

**Cross-references:** F-CORE-007

---

### F-BRAIN-016 — A single 30 s httpx timeout is the only time control on the LLM stream; no TTFT or total-generation watchdogs

| Field | Value |
|---|---|
| **ID** | F-BRAIN-016 |
| **Title** | A single 30 s httpx timeout is the only time control on the LLM stream; no TTFT or total-generation watchdogs |
| **Severity** | S2 — Medium |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/llm_client.py:80` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:80`
```python
        client = httpx.Client(timeout=30.0)
```

**What is wrong / assumed / missing**

One scalar timeout covers connect, read, write, and pool. For a streaming response the read timeout applies between bytes, so a stalled model (no token for 30 s) raises `ReadTimeout` mid-turn → `LLMUnavailable` → "Sorry, I had trouble…"; but a *slow* model emitting one token per 29 s streams forever with no bound. Spec 02's stage timeouts (10 s first token, 60 s total, per core.md §3.1) exist nowhere. There is also no connect-specific timeout: a wedged TCP connect waits the full 30 s before the user hears anything.

**Why it matters**

The turn loop's only other timeout is the 15 s confirmation wait (core.md §3.1). A hung llama-server (observed states at audit: exit-1 on bad flags pre-fix, 13.93 s healthy start) produces a 30 s silent "thinking" state on the main path's error edge.

**Questions this raises**

1. What are the correct TTFT/total budgets given measured decode of 73–80 tok/s and `max_tokens=512` (≈ 7 s typical)? (→ §10 Q-B-08)

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py:80`: replace with `httpx.Client(timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0))` and add a total-generation guard: `t0 = time.monotonic()` before the loop; on each iteration, if `time.monotonic() - t0 > 60.0`, `logger.error("llm_stream_total_timeout")`, close the client, and raise `LLMUnavailable("llama-server total generation timeout")`. Before: single 30 s scalar. After: 5 s connect, 10 s inter-token, 60 s total.
2. Add `tests/test_llm_client.py::test_stream_total_timeout`: stub transport yielding one token per 0.05 s with the guard patched to 0.2 s; assert `LLMUnavailable` after ~0.2 s.

**Verification test**

- **Tier:** T1
- **Input:** the stub stream above
- **Expected output:** `LLMUnavailable` raised at the patched deadline
- **Threshold:** ≤ 250 ms to raise with the 0.2 s guard
- **Command:** `uv run pytest tests/test_llm_client.py::test_stream_total_timeout -q`

**Cross-references:** F-CORE-007, F-BRAIN-015

---

### F-BRAIN-017 — `Done` carries hard-coded zero usage; the server's usage/timings chunk is never parsed

| Field | Value |
|---|---|
| **ID** | F-BRAIN-017 |
| **Title** | `Done` carries hard-coded zero usage; the server's usage/timings chunk is never parsed |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/llm_client.py:173` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:173`
```python
            yield Done(usage=LLMUsage(prompt_tokens=0, completion_tokens=0))
```

**What is wrong / assumed / missing**

llama-server emits per-request `timings` (and OpenAI `usage` when requested) in the final chunk; the client discards this and reports `prompt_tokens=0, completion_tokens=0` on every turn. Downstream, `trace.tokens_out` is reconstructed by counting `TokenDelta` events (`orchestrator.py:416`), which undercounts tool-only turns (zero content deltas → `tokens_out=0` even when the model generated a full tool call — one of the masks behind F-CORE-007) and counts deltas, not tokens.

**Why it matters**

The latency/trace model (Spec 10) and any future cost/quality analysis depend on real token counts; the trace currently records a fabricated zero for the one field the server actually provides. Edge-path severity because the main-path turn still completes; the corruption is in the telemetry.

**Questions this raises**

1. Does build 11026 include `usage` in the final SSE chunk by default, or must the request set `"stream_options": {"include_usage": true}`? (→ §10 Q-B-09; `timings` objects are visible in the S1_18b artefact responses.)

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py`: add `"stream_options": {"include_usage": True}` to the payload (`:69-77`); in the SSE loop capture `chunk.get("usage")` when present; at `:173` yield `Done` with the captured usage (zeros only when the server sent none). Before: hard-coded zeros. After: server-reported usage.
2. Add `tests/test_llm_client.py::test_done_carries_server_usage`: stub stream ending with a `usage` chunk `{"prompt_tokens": 54, "completion_tokens": 64}`; assert `Done.usage.completion_tokens == 64`.

**Verification test**

- **Tier:** T1
- **Input:** the stub stream above
- **Expected output:** `Done.usage == LLMUsage(prompt_tokens=54, completion_tokens=64)`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_llm_client.py::test_done_carries_server_usage -q`

**Cross-references:** F-CORE-007, F-CORE-009

---

### F-BRAIN-018 — Newline boundaries are not implemented: `\n` is not a candidate, `\n\n` is not a boundary, and newlines are never collapsed

| Field | Value |
|---|---|
| **ID** | F-BRAIN-018 |
| **Title** | Newline boundaries are not implemented: `\n` is not a candidate, `\n\n` is not a boundary, and newlines are never collapsed |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/brain/chunker.py:86-88`; `src/lucca/brain/chunker.py:189`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/08_streaming_chunker_spec.md:27,32,38` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/chunker.py:86-88`
```python
    # 7. Multiple spaces/newlines -> single space; space before punctuation
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" ([,\.\?!;:])", r"\1", s)
```
`src/lucca/brain/chunker.py:189`
```python
            is_punct = ch in (".", "!", "?", ";", ":")
```

**What is wrong / assumed / missing**

Spec 08 §3 requires "Multiple spaces/newlines → single space; `\n\n` → boundary" and §4 lists `\n` as a boundary candidate; §3 also requires treating a heading/bullet line end as a boundary. The code collapses only `[ \t]+` (the comment claims newlines, the regex excludes them), and the candidate set has no `\n`. A multi-line reply (a bulleted list — common for this persona) therefore produces no boundaries at line ends and is chunked by comma/force-split instead, speaking list items fused together or split mid-item. Which side is right: the spec — line structure is the strongest prosodic signal in list output.

**Why it matters**

Spec'd behaviour missing on a common reply shape; interacts with F-BRAIN-005 (suppression) and the numbered-list gap (§5.2) to make list replies the worst-chunked category.

**Questions this raises**

1. None — the spec is explicit.

**Proposed remediation**

1. In `src/lucca/brain/chunker.py`, `normalise_text` step 7: after the `[ \t]+` collapse, add `s = re.sub(r"\n{3,}", "\n\n", s)` so the `\n\n` boundary signal survives (single `\n` kept for the boundary detector). Before: newlines untouched. After: runs collapsed to at most `\n\n`.
2. In `_find_boundary` (`:189`): add `\n` to the candidate set — single `\n` as a soft boundary (like `,`), `\n\n` as a hard boundary (like `.`); the lookahead rule is satisfied by definition at a newline.
3. Add `tests/test_chunker.py::test_t_chk_newline_boundaries`: feed `"First line.\nSecond line.\n\nNew paragraph here."`; assert chunks split at the `\n\n` and never fuse the paragraphs.

**Verification test**

- **Tier:** T1
- **Input:** the fixture above
- **Expected output:** paragraph boundary produces separate chunks
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py::test_t_chk_newline_boundaries -q`

**Cross-references:** F-BRAIN-005, F-BRAIN-022

---

### F-BRAIN-019 — `idle_flush_ms = 350` (stalled-stream flush) is not implemented

| Field | Value |
|---|---|
| **ID** | F-BRAIN-019 |
| **Title** | `idle_flush_ms = 350` (stalled-stream flush) is not implemented |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/brain/chunker.py:120-127`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/08_streaming_chunker_spec.md:56` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/chunker.py:120-127`
```python
    def feed(self, delta: str) -> list[TTSChunk]:
        norm = normalise_text(delta, speak_urls=self.speak_urls)
        self.buffer += norm
        return self._extract_chunks(is_final=False)

    def flush(self) -> list[TTSChunk]:
        """Emits remaining buffer at end-of-stream."""
        return self._extract_chunks(is_final=True)
```
(no timer, timestamp, or idle path anywhere in the module).

**What is wrong / assumed / missing**

Spec 08 §4: "if no delta for 350 ms and buffer ≥ 12 chars, flush (LLM stalled)". The chunker has no clock and the orchestrator no idle pump, so a model that pauses mid-sentence (tool-call deliberation, long reasoning) holds a speakable buffer until the stream resumes or ends — first-audio latency grows by the full stall. T-CHK-11 has no test. Which side is right: the spec; the chunker exists to bound time-to-first-audio.

**Why it matters**

Spec'd latency behaviour absent with no mechanical test (Charter §4 S2 definition). The stall shape is real: measured TTFT p95 115–300 ms and decode gaps during tool-call turns (S1_18b, S1_36).

**Questions this raises**

1. Who owns the timer — the chunker (threading.Timer per feed) or the orchestrator's turn loop (50 ms tick)? (Decision recorded: orchestrator-side pump; the chunker stays thread-confined per Spec 08 §5.)

**Proposed remediation**

1. In `src/lucca/brain/chunker.py`: add `def feed_idle(self, now: float, last_delta_ts: float) -> list[TTSChunk]` returning `self._extract_chunks(is_final=True)` when `now - last_delta_ts >= 0.350 and len(self.buffer.strip()) >= 12` else `[]` (pure function; no threading in the chunker).
2. In `src/lucca/core/orchestrator.py` turn loop (CORE-area change): track `last_delta_ts` on each `TokenDelta`; on a 50 ms idle tick, call `feed_idle` and synthesise any emitted chunk. Before: no idle path. After: 350 ms stall flush.
3. Add `tests/test_chunker.py::test_t_chk_11_idle_flush`: feed 30 chars, call `feed_idle(now=last+0.4, last_delta_ts=last)`, assert one chunk; call with `now=last+0.1`, assert none.

**Verification test**

- **Tier:** T1
- **Input:** the fixture above
- **Expected output:** chunk emitted only at ≥ 350 ms idle with ≥ 12 buffered chars
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py::test_t_chk_11_idle_flush -q`

**Cross-references:** F-BRAIN-020, F-BRAIN-022

---

### F-BRAIN-020 — Chunker lifecycle is wrong across turns: `flush()` does not reset, and one shared chunker serves every turn

| Field | Value |
|---|---|
| **ID** | F-BRAIN-020 |
| **Title** | Chunker lifecycle is wrong across turns: `flush()` does not reset, and one shared chunker serves every turn |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/chunker.py:125-127`; `src/lucca/core/orchestrator.py:84`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/08_streaming_chunker_spec.md:60-70` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/chunker.py:125-127`
```python
    def flush(self) -> list[TTSChunk]:
        """Emits remaining buffer at end-of-stream."""
        return self._extract_chunks(is_final=True)
```
`src/lucca/core/orchestrator.py:84` (per core.md evidence): `self.chunker = StreamingChunker()` — one instance for the process lifetime; `reset()` is called only from `_abort_turn` (barge-in), never at turn start or after flush.

**What is wrong / assumed / missing**

Spec 08 §5: "Single-owner object per turn; created in DISPATCH, discarded in POSTTURN" and "`flush()` … emits remainder, **resets**". As-built: (a) `flush()` empties the buffer but leaves `is_first=False`, a growing `chunk_id`, and the `_spoken_chunks` history; (b) the orchestrator never resets between completed turns, so turn 2+ starts with `is_first=False` — its first chunk is built with `MIN_CHARS=40` instead of `FIRST_CHUNK_MIN_CHARS=24`, is marked `is_first=False` for the TTS priority path, and its `chunk_id` continues from the previous turn; (c) the shared instance is also touched by concurrent turn threads (F-CORE-011). `trace_id` is permanently `"trace-0"`, so every `TTSChunk` in every turn carries the same trace id.

**Why it matters**

The first-chunk fast path (24–90 chars, Spec 10 S3 budget) only ever works on the first turn of a session; every later turn's first audio waits for 40 chars. Combined with F-BRAIN-005 this makes post-turn-1 chunking the worst case. Edge severity: turns still complete — a per-turn latency degradation, not a crash.

**Questions this raises**

1. Should `trace_id` come from the turn's actual trace id (requires passing it in or constructing per turn)? (Decision recorded: construct per turn with the trace id — fixes both.)

**Proposed remediation**

1. In `src/lucca/core/orchestrator.py` `_run_turn`/`_run_text_turn` (CORE-area change): replace the shared `self.chunker` with a per-turn `StreamingChunker(trace_id=trace.trace_id)` created at turn start. Before: one process-lifetime chunker. After: one per turn per Spec 08 §5.
2. In `src/lucca/brain/chunker.py`, `flush()`: after emitting, call `self.reset()` and document "flush emits remainder and resets". Before: no reset. After: self-resetting (defensive for any future shared use).
3. Add `tests/test_chunker.py::test_t_chk_flush_resets_lifecycle`: feed/flush twice; assert the second turn's first chunk has `is_first=True` and the 24-char minimum applies.

**Verification test**

- **Tier:** T1
- **Input:** the lifecycle test above
- **Expected output:** second-turn first chunk `is_first is True`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py::test_t_chk_flush_resets_lifecycle -q`

**Cross-references:** F-CORE-011, F-BRAIN-005, F-BRAIN-036

---

### F-BRAIN-021 — The normaliser runs per-delta, so markdown links, emphasis, and URLs spanning delta boundaries survive into speech

| Field | Value |
|---|---|
| **ID** | F-BRAIN-021 |
| **Title** | The normaliser runs per-delta, so markdown links, emphasis, and URLs spanning delta boundaries survive into speech |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/chunker.py:120-123`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/08_streaming_chunker_spec.md:22` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/chunker.py:120-123`
```python
    def feed(self, delta: str) -> list[TTSChunk]:
        norm = normalise_text(delta, speak_urls=self.speak_urls)
        self.buffer += norm
        return self._extract_chunks(is_final=False)
```

**What is wrong / assumed / missing**

Spec 08 §3 applies the normaliser "to text before chunk boundary detection" — i.e. on the accumulated buffer. `feed()` normalises each incoming delta independently and appends the result, so any construct spanning a delta boundary is invisible to the regexes: `[text](url` + `)` survives as literal text; `**bold` + `**` keeps asterisks; `http://x` split across deltas survives the URL substitution. Token streams arrive a few characters at a time (llama.cpp often emits partial words), so spanning is routine, not rare.

**Why it matters**

The companion speaks raw markdown URLs and asterisks aloud — the exact TTS-prosody defect Spec 08 §3 exists to prevent — on the main voice path whenever the tokeniser splits a construct.

**Questions this raises**

1. None — the fix location is unambiguous.

**Proposed remediation**

1. In `src/lucca/brain/chunker.py`, `feed()`: change to `self.buffer += delta; self.buffer = normalise_text(self.buffer, speak_urls=self.speak_urls); return self._extract_chunks(is_final=False)` — re-normalise the whole buffer each feed (the buffer is ≤ ~260 chars, cost is trivial). Before: per-delta normalisation. After: whole-buffer normalisation.
2. Add `tests/test_chunker.py::test_t_chk_markdown_spanning_deltas`: feed `"[text](http://x"` then `"). Next."`; assert the final chunks contain no `[`, `]`, `(`, or `http`.

**Verification test**

- **Tier:** T1
- **Input:** the split-delta fixture above
- **Expected output:** no markdown/URL residue in chunk text
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py::test_t_chk_markdown_spanning_deltas -q`

**Cross-references:** F-BRAIN-022

---

### F-BRAIN-022 — Chunker test suite misses the broken spec cases: T-CHK-06 (ellipsis), T-CHK-11 (idle flush), T-CHK-13 (first-chunk latency), T-CHK-14 (numbered lists), and the 30-stream demux gate

| Field | Value |
|---|---|
| **ID** | F-BRAIN-022 |
| **Title** | Chunker test suite misses the broken spec cases: T-CHK-06 (ellipsis), T-CHK-11 (idle flush), T-CHK-13 (first-chunk latency), T-CHK-14 (numbered lists), and the 30-stream demux gate |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `tests/test_chunker.py:14-164`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/08_streaming_chunker_spec.md:72-89` |
| **Status** | OPEN |

**Evidence**

`tests/test_chunker.py` implements T-CHK-01…05, 07…10, and P-04; the numbering skips 06; Spec 08 §6 lists T-CHK-01…14. The demux gate (T-CHK-10) is specified as "30 fixture streams (10 structured tool calls, 10 inline JSON tool calls, 10 plain text starting with brace-like characters)"; the test has one inline case and one plain case (`:113-150`).

**What is wrong / assumed / missing**

Five spec'd behaviours have no mechanical test: the ellipsis composition (broken — §5.3 trace), idle flush (absent — F-BRAIN-019), first-chunk ≤ 90 chars within 8 deltas (not guaranteed — §5.2), numbered-list protection (partially broken — §5.2), and the 30-stream demux gate (under-fixtured 2 vs 30). P-04 runs 100 examples vs the spec's 2 000 and omits the spec's join-equality assertion. This is the mechanism by which F-BRAIN-005/018/019/021 shipped green.

**Why it matters**

Charter §4 S2: a spec'd behaviour with no mechanical test. The chunker is on the critical voice path; its frozen fixture file (`tests/fixtures/chunker/*.jsonl` per Spec 08 §6) does not exist.

**Questions this raises**

1. None — gaps are enumerated in the remediation.

**Proposed remediation**

1. In `tests/test_chunker.py`, add: `test_t_chk_06_ellipsis` (`"Wait... really? Yes!"` → expect 2 chunks after F-BRAIN-005/F-BRAIN-020 fixes; today it yields 1 — mark `xfail` until fixed), `test_t_chk_11_idle_flush` (per F-BRAIN-019), `test_t_chk_13_first_chunk_latency` (50 fixture replies; first chunk ≤ 90 chars within 8 deltas), `test_t_chk_14_numbered_list` (`"1. First item\n2. Second item"` → 2 chunks).
2. Create `tests/fixtures/chunker/demux_gate.jsonl` with 30 streams (10 structured, 10 inline, 10 brace-text) and `test_t_chk_10_demux_gate` asserting 0 tool-call JSON reaches TTS and 10/10 plain texts spoken intact.
3. Raise P-04 to 2 000 examples and add the assertion `"".join(c.text for c in chunks) == normalise_text("".join(deltas))` up to whitespace collapse.

**Verification test**

- **Tier:** T1
- **Input:** the added tests
- **Expected output:** all pass (T-CHK-06 xfail-tracked until the F-BRAIN-005 fix lands)
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py -q`

**Cross-references:** F-BRAIN-005, F-BRAIN-019, F-BRAIN-021, F-CORE-035

---

### F-BRAIN-023 — ADR-001's canonical launch still specifies `--log-format json`, which the installed binary rejects; the code drifted without an ADR update

| Field | Value |
|---|---|
| **ID** | F-BRAIN-023 |
| **Title** | ADR-001's canonical launch still specifies `--log-format json`, which the installed binary rejects; the code drifted without an ADR update |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `docs/archive/2026-09-17_pre_phase4_audit/08_adr/ADR-001_inference_engine.md:40`; `src/lucca/brain/server_ctl.py:258-285`; `docs/audit/evidence/S1_15_llama_server.stderr.log` |
| **Status** | OPEN |

**Evidence**

`docs/archive/…/ADR-001_inference_engine.md:40`
```
  --no-webui `
  --jinja `
  --log-format json
```
Artefact: `docs/audit/evidence/S1_15_llama_server.stderr.log` (row 30) — `error: invalid argument: --log-format` from build 11026. Current code (`server_ctl.py:258-285`) emits no `--log-format`.

**What is wrong / assumed / missing**

The archived canonical command includes a flag the deployed binary rejects; the S1-era code faithfully implemented the ADR and the server could not start (F-CORE-012 mechanism: exit 1 in 2.63 s, row 29). The current tree removed the flag — the code is now right and the ADR is wrong — but no ADR amendment, decisions-log entry, or changelog records the drift. Which side is right: the code (it must match the deployed binary); the ADR needs an addendum.

**Why it matters**

The archived docs set is the implementers' read source (AGENTS.md precedence order). The next engineer rebuilding the command from the ADR re-introduces the exit-1 defect; spec-drift without a recorded decision is invisible precisely at handover points.

**Questions this raises**

1. Does build 11026 support JSON logging under a different flag, and does anything in the project parse the server's stdout as JSON? (→ §10 Q-B-10; nothing in `src/` parses the log file.)

**Proposed remediation**

1. In the post-audit docs set (future programme): mark ADR-001's canonical command amended — `--log-format json` removed, `--flash-attn on` explicit — citing `S1_15_llama_server.stderr.log`; add a note to the decisions log (when writable again) recording the drift and reason.
2. In `src/lucca/brain/server_ctl.py`, `build_launch_command()`: add a module-level `REJECTED_FLAGS: Final = ("--log-format",)` and assert in `tests/test_server_ctl.py` that no rejected flag appears in the command (guard against re-introduction from the stale ADR). Before: no guard. After: regression guard.

**Verification test**

- **Tier:** T1
- **Input:** `build_launch_command(cfg, home_dir)` for both modes
- **Expected output:** `--log-format` absent from the returned list
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_server_ctl.py::test_no_rejected_flags -q`

**Cross-references:** F-CORE-012, F-BRAIN-008, F-BRAIN-029

---

### F-BRAIN-024 — `stop_server` terminates every host process named `llama-server`, not just the tracked one

| Field | Value |
|---|---|
| **ID** | F-BRAIN-024 |
| **Title** | `stop_server` terminates every host process named `llama-server`, not just the tracked one |
| **Severity** | S2 — Medium |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/server_ctl.py:330-360` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/server_ctl.py:346-360`
```python
    # Terminate any lingering llama-server process on Windows
    try:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = p.info.get("name") or ""
                if "llama-server" in name.lower():
                    p.terminate()
                    try:
                        p.wait(timeout=2.0)
                    except psutil.TimeoutExpired:
                        p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:  # noqa: BLE001, S110
        pass
```

**What is wrong / assumed / missing**

After terminating the tracked/attached process, `stop_server` sweeps the whole process table and terminates anything named `llama-server*` — including servers started by other tools, other Lucca instances, or the user's own experiments. The function's `host`/`port` parameters are unused, so it cannot even scope itself. The UI restart path (`settings_dialog.py:98-99`) triggers this from a settings dialog.

**Why it matters**

A settings-dialog operation can kill unrelated processes on the host — a host-level side effect far beyond "stop our server". Edge severity: requires a foreign llama-server to exist, but the blast radius is total when it does.

**Questions this raises**

1. Is the sweep intentional to clean up orphans? If so, scope it to processes whose executable path equals `home_dir/app/llama-server/llama-server.exe` (the path is known).

**Proposed remediation**

1. In `src/lucca/brain/server_ctl.py`, `stop_server()`: change signature to `stop_server(host, port, proc=None, home_dir: Path | None = None)`; in the psutil loop, terminate only when `home_dir is not None and p.exe() == str(home_dir / "app" / "llama-server" / "llama-server.exe")`; without `home_dir`, skip the sweep. Before: name substring match. After: exact-path match or no sweep.
2. In `src/lucca/ui/settings_dialog.py:98-99` (UI-area change): pass `self.app_config.home_dir` through.
3. Add `tests/test_server_ctl.py::test_stop_server_scopes_to_our_exe`: monkeypatch `psutil.process_iter` with two fake processes (matching path, non-matching path); assert only the matching one gets `terminate()`.

**Verification test**

- **Tier:** T1
- **Input:** the monkeypatched iterator above
- **Expected output:** foreign-named process untouched
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_server_ctl.py::test_stop_server_scopes_to_our_exe -q`

**Cross-references:** F-BRAIN-029

---

### F-BRAIN-025 — `start_server` leaks the log file handle and `llama-server.log` grows without rotation, truncated anew each start

| Field | Value |
|---|---|
| **ID** | F-BRAIN-025 |
| **Title** | `start_server` leaks the log file handle and `llama-server.log` grows without rotation, truncated anew each start |
| **Severity** | S2 — Medium |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/server_ctl.py:320-327` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/server_ctl.py:320-327`
```python
    log_file = home_dir / "logs" / "llama-server.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fp = open(log_file, "wb")
    return subprocess.Popen(  # noqa: S603
        cmd,
        stdout=fp,
        stderr=subprocess.STDOUT,
    )
```

**What is wrong / assumed / missing**

The parent opens a file object for the child's stdout and never closes it in the parent (`fp` goes out of scope; the handle stays open until GC, and across restarts handle count grows). The same single file is opened in `wb` mode each start, truncating the previous server's log — destroying the evidence needed when boot fails (F-CORE-012's whole difficulty). There is no rotation or retention bound, and one file is shared by all runs.

**Why it matters**

Resource leak per restart plus log-loss exactly when diagnostics are needed. S1 generated 70 KB of server log in ~30 min (row 32); unbounded growth over weeks is a disk and an evidence-hygiene issue (cf. F-CORE-056 for traces.jsonl).

**Questions this raises**

1. Should each start write `llama-server-<UTC>.log` and keep ≤ 5? (Decision recorded: yes, timestamped names, keep-5.)

**Proposed remediation**

1. In `src/lucca/brain/server_ctl.py`, `start_server()`: compute `log_file = home_dir / "logs" / f"llama-server-{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.log"`; after the successful `Popen`, attach `proc._lucca_log_fp = fp`; in `stop_server`/`restart_server` close the attribute if present. Before: one shared file, leaked handle, truncated history. After: timestamped file, closed handle.
2. Prune `logs\llama-server-*.log` to the newest 5 at each start.
3. Add `tests/test_server_ctl.py::test_log_files_rotate_and_handle_closed`: two `start_server` calls into tmp_path with a fake exe (`python -c "…"` double), assert two timestamped files and the first handle closed after stop.

**Verification test**

- **Tier:** T1
- **Input:** the rotation test above
- **Expected output:** ≤ 5 log files retained; no open handle on parent after stop
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_server_ctl.py::test_log_files_rotate_and_handle_closed -q`

**Cross-references:** F-CORE-056, F-CORE-012

---

### F-BRAIN-026 — The mmproj on disk is f16 content renamed to a `Q8_0` filename; the VRAM budget basis is wrong

| Field | Value |
|---|---|
| **ID** | F-BRAIN-026 |
| **Title** | The mmproj on disk is f16 content renamed to a `Q8_0` filename; the VRAM budget basis is wrong |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `scripts/download_llm_models.py:11-23`; `docs/audit/evidence/S1_07c_models_manifest.txt`; `docs/archive/2026-09-17_pre_phase4_audit/08_adr/ADR-001_inference_engine.md:12,23` |
| **Status** | OPEN |

**Evidence**

`scripts/download_llm_models.py:11-23`
```python
# 1. Projector
mmproj_target = dest_dir / "mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf"
if not mmproj_target.exists():
    print("Downloading Ultravox mmproj...")
    ...
    p = hf_hub_download(
        repo_id="ggml-org/ultravox-v0_5-llama-3_1-8b-GGUF",
        filename="mmproj-ultravox-v0_5-llama-3_1-8b-f16.gguf",
        local_dir=str(dest_dir),
    )
    downloaded_file = dest_dir / "mmproj-ultravox-v0_5-llama-3_1-8b-f16.gguf"
    if downloaded_file.exists() and downloaded_file != mmproj_target:
        downloaded_file.rename(mmproj_target)
```
Artefact: `docs/audit/evidence/S1_07c_models_manifest.txt` (row 13) — on-disk `…-Q8_0.gguf` is 1 379 512 224 B (≈ 1.28 GiB, f16-size); ADR-001 budgets Q8_0 at ≈ 0.74 GB.

**What is wrong / assumed / missing**

The projector file is the **f16** mmproj renamed to `…-Q8_0.gguf` — the same provenance-laundering pattern as F-BRAIN-002. Consequences: (a) ~+0.6 GiB VRAM over the ADR plan (§6.3: as-deployed ≈ 8.5–8.7 GiB expected vs ADR-planned ≈ 7.9–8.1 GiB); (b) every tool that derives quant from the filename (`_derive_quant_from_filename`, `server_ctl.py:162-167`) reports Q8_0 for an f16 file; (c) the GGUF parser reaches the same wrong answer only because it falls back to the filename (F-BRAIN-033).

**Why it matters**

Latency/VRAM reasoning across the project (ADR-001 table, env-check VRAM budget, §6.3) is anchored on a quantisation the file does not have. The measured 8098 MiB fits the f16 reality, confirming the rename.

**Questions this raises**

1. Was f16 chosen deliberately (quality) or by the same rename pattern as the backbone? No decision recorded.

**Proposed remediation**

1. In `scripts/download_llm_models.py`: download `mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf` from the same repo if available (ggml-org publishes Q8_0 ≈ 743 MB per ADR-001 :12); otherwise keep f16 **under its true name** and update `LLMSettings.mmproj` default (`config.py:38`) accordingly. Before: f16 renamed Q8_0. After: name matches content.
2. Record the choice (Q8_0 vs f16) in the decisions log with the VRAM delta (~−0.6 GiB for Q8_0).
3. In `src/lucca/brain/server_ctl.py`, `_derive_quant_from_filename`: return `"UNKNOWN"` instead of `"Q4_K_M"` when no quant pattern matches (prevents silent mislabels); update `tests/test_gguf_parser.py` accordingly.

**Verification test**

- **Tier:** T1 (naming) + T3 (VRAM)
- **Input:** T1: parse registry of a dir with an f16-named file; T3: `nvidia-smi` after a Q8_0-mmproj start
- **Expected output:** T1: quant reported as the filename's true value or UNKNOWN; T3: VRAM ≤ ~7 500 MiB with Q8_0 mmproj
- **Threshold:** ≤ 7 500 MiB
- **Command:** `uv run pytest tests/test_gguf_parser.py -q` + `nvidia-smi --query-gpu=memory.used --format=csv`

**Cross-references:** F-BRAIN-002, F-BRAIN-003, F-BRAIN-033, F-BRAIN-051

---

### F-BRAIN-027 — `config/intents.toml` is dead in the product path, and its intent names do not map to tool names

| Field | Value |
|---|---|
| **ID** | F-BRAIN-027 |
| **Title** | `config/intents.toml` is dead in the product path, and its intent names do not map to tool names |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `config/intents.toml:4-23`; `src/lucca/router/heuristic.py:76-98` |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:87-96`
```python
            intents = data.get("intents", {})
            launch_cfg = intents.get("launch_app", {})
            if "apps" in launch_cfg and isinstance(launch_cfg["apps"], list):
                self.known_apps.update(str(a).lower() for a in launch_cfg["apps"])
            if "stop_words_after_start" in launch_cfg and isinstance(
                launch_cfg["stop_words_after_start"], list
            ):
                self.stop_words_after_start.update(
                    str(w).lower() for w in launch_cfg["stop_words_after_start"]
                )
```

**What is wrong / assumed / missing**

Only the `[intents.launch_app]` `apps`/`stop_words_after_start` keys are read; the `verbs` of all six tables (including `launch_app`'s own) are dead — the classifier regexes are hard-coded (`heuristic.py:122-125`). The file is consumed only by `HeuristicRouter`, which is itself unwired from the turn loop (F-CORE-003), so in the product the entire file has zero effect. There is also no mapping from the six intent names to the four `TOOL_DEFINITIONS` names, and five of six intent names (`file_read`, `file_write`, `web_fetch`, `memory_query`, `chit_chat`) have no tool counterpart at all.

**Why it matters**

A config file that operators can edit with the expectation of changing behaviour changes nothing — a classic dead-config trap (Charter §6 INCOMPLETE). When the router is wired (F-CORE-003 remediation), the expected fail-closed question ("what happens to unknown intents?") cannot be answered from code today because the lexicon's verbs are not consulted.

**Questions this raises**

1. When the router is wired, should `classify_intent` reject unknown intent-tool mappings at load (fail closed), or continue its current default-to-`chit_chat`? (→ §10 Q-B-11; ROUT-area decision.)

**Proposed remediation**

1. In `src/lucca/router/heuristic.py` (ROUT-area change): build the classifier regexes from the loaded verb lists with an `INTENT_TO_TOOL` mapping (`launch_app→launch_app`, `file_read→read_file`, `file_write→write_file`, `web_fetch→fetch_url`, `memory_query→` router-side, `chit_chat→` none); at load, reject (raise) any `[intents.*]` table whose mapped tool is not in `TOOL_DEFINITIONS`.
2. Delete or implement the five unused verb lists (decision: implement via the mapping; deletion loses the operator-facing lexicon).
3. Add `tests/test_router_config.py::test_intents_verbs_drive_classification` (ROUT area): custom intents.toml with an extra verb `"summon"` for `launch_app`; assert `"summon the calculator"` classifies as `launch_app`.

**Verification test**

- **Tier:** T1
- **Input:** the custom intents.toml above
- **Expected output:** the added verb classifies as `launch_app` with a mapping entry
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router_config.py::test_intents_verbs_drive_classification -q`

**Cross-references:** F-CORE-003

---

### F-BRAIN-028 — `scripts/test_s1_startup.py` false-passes against a pre-existing server, drifts from the code-computed command, and never reads the child's stdout

| Field | Value |
|---|---|
| **ID** | F-BRAIN-028 |
| **Title** | `scripts/test_s1_startup.py` false-passes against a pre-existing server, drifts from the code-computed command, and never reads the child's stdout |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `scripts/test_s1_startup.py:6-57`; `docs/audit/evidence/S1_33_startup_script.txt` |
| **Status** | OPEN |

**Evidence**

`scripts/test_s1_startup.py:31-44`
```python
print("Launching llama-server...")
t0 = time.time()
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

ready = False
for _ in range(120):
    try:
        r = httpx.get("http://127.0.0.1:8080/health", timeout=1.0)
        if r.status_code == 200:
            ready = True
            break
    except Exception:
        pass
    time.sleep(0.5)
```
Artefact: `docs/audit/evidence/S1_33_startup_script.txt` (row 64) — `Launching llama-server... Server ready: True in 0.07s` with a server already running.

**What is wrong / assumed / missing**

Three defects: (a) the script measures the health of **any** server on :8080, so it reports a 0.07 s cold start when the spawned process died on the port conflict — there is no `proc.poll()` check in the loop; (b) its hard-coded command (`:6-29`) drifts from `build_launch_command` (`--flash-attn` bare vs `on`; the S1-era code also had `--log-format json` this script never had) — it is not testing what the product launches; (c) the spawned child's stdout is piped and never read, which deadlocks any child that writes > pipe buffer (and loses the bind-error text).

**Why it matters**

This was the Phase-0 startup measurement (ADR-001 S1 ≤ 60 s cold). It cannot fail and does not measure, so the startup number in every sign-off rehearsal is fiction (sibling of F-BRAIN-007).

**Questions this raises**

1. None — remediation is mechanical.

**Proposed remediation**

1. In `scripts/test_s1_startup.py`: build the command via `from lucca.brain.server_ctl import build_launch_command` with `get_config()` (single source); before polling, assert `proc.poll() is None` each iteration and fail with the child's tail if it exited; redirect child output to a file (not PIPE) and print the last 20 lines on failure.
2. Kill any pre-existing :8080 server or fail fast with "server already running — cannot measure cold start" when `/health` answers *before* spawn.
3. Record the measured cold start into the Phase-0 report's S1 `measured_cold_startup_s` (joint with F-BRAIN-007 step 1).

**Verification test**

- **Tier:** T3
- **Input:** run with a healthy pre-existing server on :8080; run on a clean port
- **Expected output:** pre-existing → non-zero exit with "cannot measure cold start"; clean → real cold-start seconds and the child's log tail on failure
- **Threshold:** n/a — boolean
- **Command:** `uv run python scripts/test_s1_startup.py`

**Cross-references:** F-BRAIN-007, F-CORE-012

---

### F-BRAIN-029 — `test_server_ctl` asserts the command's contents but not its executability: the binary-rejected flag shipped green

| Field | Value |
|---|---|
| **ID** | F-BRAIN-029 |
| **Title** | `test_server_ctl` asserts the command's contents but not its executability: the binary-rejected flag shipped green |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `tests/test_server_ctl.py:16-116`; `docs/audit/evidence/S1_15b_llm_start_health.txt` |
| **Status** | OPEN |

**Evidence**

`tests/test_server_ctl.py:48-55`
```python
    assert "--flash-attn" in cmd
    assert "on" in cmd
    assert "--host" in cmd
    assert "127.0.0.1" in cmd
    assert "--port" in cmd
    assert "8080" in cmd
    # In text mode, --mmproj should NOT be present even if file existed
    assert "--mmproj" not in cmd
```
Artefact: `docs/audit/evidence/S1_15b_llm_start_health.txt` (row 29) — the code-computed command exited the real binary with code 1; all T1 tests passed throughout.

**What is wrong / assumed / missing**

The suite asserts flags exist, never that the target binary accepts them; there is no negative test for known-rejected flags (F-BRAIN-023), no T3 test that executes the built command (the `--log-format json` defect shipped through green T0/T1 and was caught only by an ad-hoc S1 probe), and `test_is_healthy_closed_port` (`:113-116`) performs a real network call in the T1 tier against an arbitrary port. Missing-test mechanism + wrong-tier test.

**Why it matters**

The flag-compat contract between `build_launch_command` and the deployed binary is exactly the contract that failed in production; a guard belongs beside `build_launch_command` (T1) and as a T3 smoke (build command → spawn → health).

**Questions this raises**

1. None.

**Proposed remediation**

1. Add `tests/test_server_ctl.py::test_no_rejected_flags` (joint with F-BRAIN-023 step 2): assert `--log-format` is not in the command.
2. Add `tests/test_server_ctl.py::test_command_flags_parse_with_help` (T1, no spawn): run `llama-server.exe --help` once and assert every flag the builder emits appears in the help text; skip when the exe is absent.
3. Add a T3 smoke `tests/test_phase0_server_hw.py::test_built_command_starts`: build → spawn in tmp env → `/health` ≤ 60 s → terminate; mark `hw`.
4. Move `test_is_healthy_closed_port` to a fake-transport test or mark it `tier2` (real socket).

**Verification test**

- **Tier:** T1 + T3
- **Input:** the tests above
- **Expected output:** T1 green without hardware; T3 green with the deployed binary
- **Threshold:** health ≤ 60 s
- **Command:** `uv run pytest tests/test_server_ctl.py -q && uv run pytest -m hw tests/test_phase0_server_hw.py -q`

**Cross-references:** F-BRAIN-023, F-BRAIN-008, F-CORE-036

---

### F-BRAIN-030 — Demux `flush()` lacks the `isinstance(args, dict)` guard that `feed()` has; a non-dict parameters value crashes the turn

| Field | Value |
|---|---|
| **ID** | F-BRAIN-030 |
| **Title** | Demux `flush()` lacks the `isinstance(args, dict)` guard that `feed()` has; a non-dict parameters value crashes the turn |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/toolcall_demux.py:77-79`; `src/lucca/brain/toolcall_demux.py:136-143` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/toolcall_demux.py:77-79` (feed path)
```python
                        args = obj.get("parameters") or obj.get("arguments") or {}
                        if not isinstance(args, dict):
                            args = {}
```
`src/lucca/brain/toolcall_demux.py:137-141` (flush path)
```python
                    if isinstance(obj, dict) and "name" in obj:
                        call = ToolCall(
                            tool=str(obj["name"]),
                            args=obj.get("parameters") or obj.get("arguments") or {},
                            call_id=f"inline-{uuid.uuid4().hex[:8]}",
                        )
```

**What is wrong / assumed / missing**

The inline-JSON accepted at flush time can carry `parameters` as a list or scalar (e.g. `{"name": "read_file", "parameters": ["x"]}`); `ToolCall.args` is typed `dict[str, JsonValue]` (`schemas.py:53-56`), so pydantic raises `ValidationError` inside the client's flush loop (`llm_client.py:170-171`), outside its `except (httpx.HTTPError, OSError)` — the turn dies via the orchestrator's generic catch (`orchestrator.py:457-467`) and the user hears "Sorry, I had trouble…".

**Why it matters**

A single malformed inline call convertable to a hard crash is exactly what the demux exists to prevent (Spec 08 §2: untrusted inline JSON must never reach TTS or execution uncontrolled). Edge severity: requires a malformed-by-shape inline call at stream end.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/toolcall_demux.py:136-143`: copy the guard — `args = obj.get("parameters") or obj.get("arguments") or {}; if not isinstance(args, dict): logger.warning("inline_tool_call_non_dict_args", args=args); return [TokenDelta(delta=buffered_text)]` (release as text, matching the give-up semantics). Before: unguarded. After: guarded + logged.
2. Add `tests/test_chunker.py::test_demux_flush_non_dict_args`: stream `{"name": "read_file", "parameters": ["x"]}` then `flush()`; assert a `TokenDelta` results and no `ToolCallEnd`/exception.

**Verification test**

- **Tier:** T1
- **Input:** the fixture above
- **Expected output:** `TokenDelta` released; no exception; warning logged
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py -q`

**Cross-references:** F-BRAIN-009, F-BRAIN-010

---

### F-BRAIN-031 — Prompt-builder and persona-TOML tests mutate module-global persona state without restoring it

| Field | Value |
|---|---|
| **ID** | F-BRAIN-031 |
| **Title** | Prompt-builder and persona-TOML tests mutate module-global persona state without restoring it |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `tests/test_prompt_builder.py:46-50`; `tests/test_persona_toml.py:41-57, 89-126`; `src/lucca/brain/prompt_builder.py:94-102, 533` |
| **Status** | OPEN |

**Evidence**

`tests/test_prompt_builder.py:46-50`
```python
    set_persona(
        archetype="inventor",
        formality="casual",
        custom_prompt=custom_directive,
    )
```
(no fixture restores the module globals; `test_no_ccv2_artifacts` at `:140-146` then asserts against whatever persona state previous tests left). `tests/test_persona_toml.py:42-57` calls `save_persona_to_config(...)`, whose side effect includes `set_persona(...)` (`prompt_builder.py:492-504`).

**What is wrong / assumed / missing**

The module's persona singleton (`prompt_builder.py:94-102`) is mutated by tests and never restored: `test_custom_prompt_is_additive` leaves `custom_prompt="Always speak like a 1920s radio broadcaster."` and `formality="casual"` as suite-visible state; the persona-TOML tests overwrite it from tmp files. Any test asserting prompt content downstream (including in other modules — `test_turn_loop` exercises `build_messages` through turns) sees residue whose value depends on execution order; the import-time TOML load (`:533`) also means suite state depends on the host's `C:\ProjectLucca\config\persona.toml`.

**Why it matters**

Order-dependent, host-dependent tests are non-mechanical evidence (Charter §6 TESTING: "misleading tests"); the suite's green does not establish the prompt content for any defined persona state.

**Questions this raises**

1. None.

**Proposed remediation**

1. Add to `tests/conftest.py` an autouse fixture that snapshots `get_persona()` and restores it via `set_persona(**snapshot)` after each test. Before: global mutation leaks. After: every test sees the entry state.
2. In `tests/test_persona_toml.py`, add an assertion that the fixture restores state after a save, proving the mechanism.

**Verification test**

- **Tier:** T1
- **Input:** run the two modules in both orders
- **Expected output:** identical pass set both orders
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_prompt_builder.py tests/test_persona_toml.py -q && uv run pytest tests/test_persona_toml.py tests/test_prompt_builder.py -q`

**Cross-references:** F-CORE-035, F-BRAIN-037

---

### F-BRAIN-032 — `check_server_status` maps every non-200/503 HTTP status to `"loading"`

| Field | Value |
|---|---|
| **ID** | F-BRAIN-032 |
| **Title** | `check_server_status` maps every non-200/503 HTTP status to `"loading"` |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/server_ctl.py:288-301` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/server_ctl.py:295-299`
```python
        if r.status_code == 200:
            return "ready"
        if r.status_code == 503:
            return "loading"
        return "loading"
```

**What is wrong / assumed / missing**

A foreign service on :8080 answering 404/401/500, or llama-server crashing into a 500, is classified identically to a healthy but still-loading server. Boot (`main.py:135-139`) then waits the full 60 s believing the model is loading. Expected: non-200/503 → a distinct state (e.g. `"error"`) that boot can surface immediately, and it interacts with the existing assumption that a healthy port is *our* server (core A-02).

**Why it matters**

Boot-time misdiagnosis on an edge path; produces a 60 s hang with a misleading progress line ("Loading 8GB model tensors…") when the actual state is an error.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/server_ctl.py`, `check_server_status()`: return `Literal["ready","loading","error","offline"]`; map 200→ready, 503→loading, other statuses→`"error"` with the code logged. Before: all non-200/503 → loading. After: explicit error state.
2. In `src/lucca/main.py` (CORE-area change): on `"error"`, write the status code to stderr and `sys.exit(5)` immediately. Before: 60 s wait. After: fail fast.
3. Add `tests/test_server_ctl.py::test_check_server_status_error_mapping` with a stub transport returning 500 → assert `"error"`.

**Verification test**

- **Tier:** T1
- **Input:** stub 500 response
- **Expected output:** `check_server_status(...) == "error"`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_server_ctl.py::test_check_server_status_error_mapping -q`

**Cross-references:** F-CORE-012 (A-02)

---

### F-BRAIN-033 — GGUF parser reads unsigned header fields as signed, expects `general.quantization_version` as a string real files do not carry, and the test encodes that fantasy format

| Field | Value |
|---|---|
| **ID** | F-BRAIN-033 |
| **Title** | GGUF parser reads unsigned header fields as signed, expects `general.quantization_version` as a string real files do not carry, and the test encodes that fantasy format |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/server_ctl.py:91-111, 133-135`; `tests/test_gguf_parser.py:50-68` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/server_ctl.py:97-99`
```python
                    elif val_type in (4, 5):  # uint32, int32
                        v = struct.unpack("<i", f.read(4))[0]
                        metadata[key] = str(v)
```
`tests/test_gguf_parser.py:54-58`
```python
        metadata={
            "general.architecture": "llama",
            "general.name": "Meta-Llama-3-8B-Instruct",
            "general.quantization_version": "Q4_K_M",
        },
```

**What is wrong / assumed / missing**

Three mismatches against the GGUF binary format: (a) uint8/uint16/uint32/uint64 values are unpacked with signed format codes (`<b`, `<h`, `<i`, `<q`), so values above the signed range wrap negative (file-type enums, large counts); (b) `general.quantization_version` is an integer in real GGUF headers, yet the code compares it to `""`/`"0"` and otherwise uses it as a quant name — it always falls back to the filename; (c) the test writes the fake string value, entrenching a format real files never have. Result: for the two real model files the registry's "quantization" comes from the filename (and is wrong when the filename lies — F-BRAIN-026; and defaults to `Q4_K_M` when the filename has no pattern).

**Why it matters**

The registry drives the UI's model descriptions and the audio-compatibility badge; a parser+fixture co-designed around a non-format cannot be trusted on real files (the only two real files were never parsed in a test).

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/server_ctl.py:91-111`: use unsigned codes for unsigned types — `<B` for 0, `<H` for 2, `<I` for 4, `<Q` for 10; keep signed codes for the odd-type indices per the GGUF spec. Before: `<b <h <i <q` for both. After: correct per-type codes.
2. In the same file: treat `general.quantization_version` as an int (store `str(v)`), and derive the human quant label from `general.file_type` (a new metadata key parsed as uint32) via the GGUF file-type enum; filename fallback only when `file_type` is absent. Before: string expectation. After: integer-correct.
3. Rewrite `tests/test_gguf_parser.py:50-68` to encode `general.file_type` as a uint32 value and assert the mapped label; add a case asserting a uint32 value 2^31 parses positive.

**Verification test**

- **Tier:** T1
- **Input:** synthetic GGUF with `general.file_type = 7` (Q4_K_M) and a uint32 field = 2^31
- **Expected output:** `quantization == "Q4_K_M"`; the large field parses as 2147483648
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_gguf_parser.py -q`

**Cross-references:** F-BRAIN-026, F-BRAIN-034

---

### F-BRAIN-034 — `scan_model_registry` pairs any `mmproj*` with any audio model and computes `is_active` by substring

| Field | Value |
|---|---|
| **ID** | F-BRAIN-034 |
| **Title** | `scan_model_registry` pairs any `mmproj*` with any audio model and computes `is_active` by substring |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/server_ctl.py:190-215` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/server_ctl.py:192-196`
```python
        paired_mmproj: Path | None = None
        for cand_name in all_names:
            if cand_name.lower().startswith("mmproj"):
                paired_mmproj = models_dir / cand_name
                break
```
`src/lucca/brain/server_ctl.py:211-215`
```python
        is_active = (
            rel_path == active_model_rel
            or path.name in active_model_rel
            or (not active_model_rel and "ultravox" in path.name.lower())
        )
```

**What is wrong / assumed / missing**

The first `mmproj*` in the directory is declared the projector for **every** audio-named model, so in a multi-model directory the badge ("🎙 Audio-Native") is asserted on a pairing that may not exist; and `is_active` is true whenever the filename is a substring of the active config value (or whenever nothing is configured and the name contains "ultravox"). The UI badge therefore overstates compatibility (implementation prompt WI-4.3 requires the badge to be "binary architectural property" truth).

**Why it matters**

The LLM tab's honesty feature (D2/WI-4) still misleads on pairing and active selection in multi-model directories.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/server_ctl.py:192-196`: pair by stem — candidate mmproj names for model `X` are `mmproj-{stem-of-X}*.gguf`; only a matching stem earns the audio badge; otherwise "⚠ mmproj required". Before: first mmproj pairs with all. After: stem-matched pairing.
2. In the same function: `is_active = (rel_path == active_model_rel) or (models_dir / active_model_rel) == path` — exact match only; delete the substring and ultravox-default branches. Before: substring semantics. After: exact.
3. Add `tests/test_server_ctl.py::test_registry_stem_pairing`: two models, one mmproj for the second; assert the first model is "missing_mmproj" and only the second is "audio".

**Verification test**

- **Tier:** T1
- **Input:** the two-model fixture above
- **Expected output:** badges assigned only via stem match
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_server_ctl.py::test_registry_stem_pairing -q`

**Cross-references:** F-BRAIN-033

---

### F-BRAIN-035 — `restart_server` is dead code (no caller in `src/`, `tests/`, or `scripts/`)

| Field | Value |
|---|---|
| **ID** | F-BRAIN-035 |
| **Title** | `restart_server` is dead code (no caller in `src/`, `tests/`, or `scripts/`) |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/brain/server_ctl.py:363-398` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/server_ctl.py:363-398` defines `restart_server`; a repo-wide search for `restart_server` finds only the definition and this finding. The UI imports `stop_server`/`start_server`/`is_healthy` directly (`settings_dialog.py:61-66`).

**What is wrong / assumed / missing**

The implementation prompt's WI-3.3 requires the Restart button to call `restart_server()` on a QThread with real status transitions; the button instead composes `stop_server` + `start_server` inline (`settings_dialog.py:98-99` shows stop; the start half also bypasses `restart_server`'s health polling) and the health-polling implementation in `restart_server` runs nowhere.

**Why it matters**

The one place an honest restart-with-health-poll exists is unreachable; the UI therefore cannot satisfy WI-3.3's "✓ Healthy (port, seconds)" outcome reliably (it never polls). Dead code + a UI behaviour gap.

**Questions this raises**

1. Should the UI use `restart_server` (preferred — it owns the poll), or should the poll move into the UI? (Decision recorded: use `restart_server` on the QThread as WI-3.3 specifies.)

**Proposed remediation**

1. In `src/lucca/ui/settings_dialog.py` (UI-area change): rewire the Restart button to call `restart_server(cfg, home_dir, status_callback=self.status_signal.emit)` on the existing worker thread, importing it instead of the stop/start pair. Before: manual stop+start, no poll. After: polled restart per WI-3.3.
2. Add `tests/test_server_ctl.py::test_restart_server_polls_until_healthy` with a stub `is_healthy` that flips on the third call; assert `restart_server` returns only after the flip and calls the callback with each stage message.

**Verification test**

- **Tier:** T1
- **Input:** the stub-healthy test above
- **Expected output:** restart returns post-flip with ordered status messages
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_server_ctl.py::test_restart_server_polls_until_healthy -q`

**Cross-references:** F-BRAIN-036

---

### F-BRAIN-036 — Dead public symbols: `spoken_prefix`, `INLINE_TOOL_PREFIX_REGEX`, `SYSTEM_PROMPT`, `compile_persona_prose`

| Field | Value |
|---|---|
| **ID** | F-BRAIN-036 |
| **Title** | Dead public symbols: `spoken_prefix`, `INLINE_TOOL_PREFIX_REGEX`, `SYSTEM_PROMPT`, `compile_persona_prose` |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/brain/chunker.py:108-110`; `src/lucca/brain/toolcall_demux.py:19`; `src/lucca/brain/prompt_builder.py:216, 536` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/chunker.py:108-110`
```python
    @property
    def spoken_prefix(self) -> str:
        return " ".join(self._spoken_chunks)
```
`src/lucca/brain/toolcall_demux.py:19`
```python
INLINE_TOOL_PREFIX_REGEX = re.compile(r"^\s*(?:<\|python_tag\|>|\{)")
```
`src/lucca/brain/prompt_builder.py:216, 536`
```python
compile_persona_prose = preview_system_prompt
...
SYSTEM_PROMPT: str = get_system_prompt()
```

**What is wrong / assumed / missing**

Four public names are defined but never used: `spoken_prefix` (Spec 08 §5 intends it for history-on-interrupt; the orchestrator drops interrupted replies from history instead — core.md §3.3 row 3), the demux regex (the demux re-checks with plain string logic at `:56`), and the two prompt aliases (`SYSTEM_PROMPT` is a stale import-time snapshot; `compile_persona_prose` is exercised only by `tests/test_prompt_builder.py`).

**Why it matters**

Dead surface misleads readers about what is wired (particularly `spoken_prefix`, whose spec purpose is unfulfilled) and forces test maintenance of symbols with no product meaning.

**Questions this raises**

1. Should `spoken_prefix` be wired into the interrupt-history path (its spec purpose) or deleted? (→ §10 Q-B-12; decision deferred to CORE when F-CORE-007/011 are remediated.)

**Proposed remediation**

1. Delete `INLINE_TOOL_PREFIX_REGEX` (`toolcall_demux.py:19`) and `SYSTEM_PROMPT` (`prompt_builder.py:536`) and the `compile_persona_prose` alias (`:216`); update `tests/test_prompt_builder.py` imports to `preview_system_prompt`.
2. For `spoken_prefix` (`chunker.py:108-110`): delete it, and record Q-B-12 in the questions register of the future CORE remediation plan (F-BRAIN-020 already makes the chunker per-turn).

**Verification test**

- **Tier:** T0 + T1
- **Input:** `uv run ruff check src` and the prompt-builder tests
- **Expected output:** clean; `test_prompt_builder.py` passes without the aliases
- **Threshold:** n/a — boolean
- **Command:** `uv run ruff check src/lucca/brain && uv run pytest tests/test_prompt_builder.py -q`

**Cross-references:** F-BRAIN-020, F-CORE-007

---

### F-BRAIN-037 — Import-time persona load, a stale `SYSTEM_PROMPT` snapshot, and silent TOML parse failure defaulting to built-ins

| Field | Value |
|---|---|
| **ID** | F-BRAIN-037 |
| **Title** | Import-time persona load, a stale `SYSTEM_PROMPT` snapshot, and silent TOML parse failure defaulting to built-ins |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/prompt_builder.py:392-403, 533-536` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/prompt_builder.py:399-403`
```python
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:  # noqa: BLE001
        return {}
```
`src/lucca/brain/prompt_builder.py:532-536`
```python
# Load startup persona defaults
load_persona_from_config()

# Legacy alias for backward compatibility
SYSTEM_PROMPT: str = get_system_prompt()
```

**What is wrong / assumed / missing**

The module loads persona at import (which, in tests, reads the **host's** `C:\ProjectLucca\config\persona.toml` — making suite state host-dependent, F-BRAIN-031) and freezes a `SYSTEM_PROMPT` snapshot that does not track later `set_persona` calls (dead per F-BRAIN-036 but kept in every import). A malformed deployed TOML yields `{}` → silent built-in persona with no log anywhere, so a corrupted config presents as an unexplained personality change.

**Why it matters**

Import-time I/O plus silently-swallowed config errors are the two most self-defeating reliability patterns for a config-driven prompt; the failure mode is invisible.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/prompt_builder.py`, `get_persona_config()`: on `tomllib.TOMLDecodeError`, `logger.warning("persona_toml_unparseable", path=str(path))` before returning `{}`. Before: silent. After: logged.
2. In the same module: guard the import-time load with the same log (`:533`); delete `SYSTEM_PROMPT` per F-BRAIN-036.
3. Add `tests/test_persona_toml.py::test_malformed_toml_warns_and_defaults`: write invalid TOML to a tmp path; assert `{}` returned, defaults active, and the warning logged (caplog).

**Verification test**

- **Tier:** T1
- **Input:** the malformed-TOML test above
- **Expected output:** warning logged; built-ins active
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_persona_toml.py::test_malformed_toml_warns_and_defaults -q`

**Cross-references:** F-BRAIN-031, F-BRAIN-036, F-BRAIN-038

---

### F-BRAIN-038 — Persona values are never validated: trait ranges, unknown archetype/formality fallbacks, and `refuse_topics` type

| Field | Value |
|---|---|
| **ID** | F-BRAIN-038 |
| **Title** | Persona values are never validated: trait ranges, unknown archetype/formality fallbacks, and `refuse_topics` type |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/prompt_builder.py:162-171, 244-258, 517-529` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/prompt_builder.py:167`
```python
        base_persona = ARCHETYPES.get(arch_key, ARCHETYPES["inventor"])
```
`src/lucca/brain/prompt_builder.py:169-171`
```python
    formality_rule = FORMALITY_MODIFIERS.get(
        formality.strip().lower(), FORMALITY_MODIFIERS["casual"]
    )
```
`src/lucca/brain/prompt_builder.py:255-256`
```python
    if refuse_topics is not None:
        _active_refuse_topics = list(refuse_topics)
```

**What is wrong / assumed / missing**

No value validation exists on the persona path: unknown archetype/formality strings silently coerce to `inventor`/`casual`; trait floats outside [0, 1] pass through (`> 0.60`/`< 0.40` bands simply trigger); a string `refuse_topics` is `list()`-ed into per-character topics. The loader (`:517-529`) applies all of it without a log.

**Why it matters**

Config mistakes are silently accepted and the prompt silently changes meaning; for a UI-exposed feature this is a correctness-on-edge-paths issue (S3).

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/prompt_builder.py`, `load_persona_from_config()`: validate — `archetype`/`formality` must be in the known sets (else `logger.warning("persona_unknown_value", key=..., value=...)` and fall back); traits clamped to [0, 1] with the same warning; `refuse_topics` must be a list of strings (a bare string → `[that string]` with a warning). Before: silent coercion. After: validated with warnings.
2. Add `tests/test_persona_toml.py::test_persona_values_validated`: TOML with `archetype="nonsense"`, `warmth=1.7`, `refuse_topics="speculation"`; assert fallback + clamp + single-element list and three warnings.

**Verification test**

- **Tier:** T1
- **Input:** the invalid TOML above
- **Expected output:** clamped/validated values; warnings logged
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_persona_toml.py::test_persona_values_validated -q`

**Cross-references:** F-BRAIN-037

---

### F-BRAIN-039 — The regex TOML rewriter matches `key = value` lines inside multi-line strings and saves non-atomically

| Field | Value |
|---|---|
| **ID** | F-BRAIN-039 |
| **Title** | The regex TOML rewriter matches `key = value` lines inside multi-line strings and saves non-atomically |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/prompt_builder.py:311-389, 488-490` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/prompt_builder.py:332`
```python
    key_val_pattern = re.compile(r"^(\s*)([A-Za-z0-9_.-]+)(\s*=\s*)(.*?)((\s*#.*)?)$")
```
`src/lucca/brain/prompt_builder.py:489-490`
```python
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_content, encoding="utf-8")
```

**What is wrong / assumed / missing**

The line-rewriter cannot tell content lines of a `"""` multi-line string from real key lines: if the existing `custom_prompt` (or any multi-line value) contains a line like `archetype = "genki"`, the next save rewrites it as if it were the key (corrupting the string content); the saver also writes directly to the target (no temp + rename), so a crash mid-save leaves a truncated persona.toml that then silently defaults (F-BRAIN-037).

**Why it matters**

The feature's whole claim is "lossless" editing (implementation prompt WI-1.3); these are the two classic loss modes, and the current test corpus never exercises a multi-line value containing `key =`.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/prompt_builder.py`, `update_toml_content()`: track a `in_multiline` flag toggled on lines containing `"""` (odd count); skip key-rewriting while inside a multi-line string. Before: regex against all lines. After: multiline-aware.
2. In `save_persona_to_config()`: write to `path.with_suffix(".tmp")`, then `os.replace(tmp, path)`. Before: direct `write_text`. After: atomic replace.
3. Add `tests/test_persona_toml.py::test_save_does_not_rewrite_multiline_content`: pre-existing TOML whose `custom_prompt` contains the line `archetype = "genki"`; after a save changing formality, assert the embedded line is untouched and the file parses.

**Verification test**

- **Tier:** T1
- **Input:** the fixture above
- **Expected output:** embedded `archetype = "genki"` line preserved verbatim
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_persona_toml.py::test_save_does_not_rewrite_multiline_content -q`

**Cross-references:** F-BRAIN-037

---

### F-BRAIN-040 — A non-UTF-8 error body raises an uncaught `UnicodeDecodeError` on the non-200 path

| Field | Value |
|---|---|
| **ID** | F-BRAIN-040 |
| **Title** | A non-UTF-8 error body raises an uncaught `UnicodeDecodeError` on the non-200 path |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/llm_client.py:89-91` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:89-91`
```python
                if resp.status_code != 200:
                    err_body = resp.read().decode("utf-8")
                    raise LLMUnavailable(f"llama-server error {resp.status_code}: {err_body}")
```

**What is wrong / assumed / missing**

`resp.read().decode("utf-8")` uses strict decoding outside the `except (httpx.HTTPError, OSError)` guard (`:175`); a proxy/server returning binary or latin-1 error content raises `UnicodeDecodeError`, which escapes as an unhandled error type and lands in the orchestrator's generic catch as the wrong message. Expected: `decode("utf-8", errors="replace")`, then raise the typed `LLMUnavailable`.

**Why it matters**

Wrong-exception-type on an error path; small but directly opposing the project's typed-exception discipline (`core/exceptions.py`).

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py:90`: `err_body = resp.read().decode("utf-8", errors="replace")`. Before: strict. After: replace.
2. Add `tests/test_llm_client.py::test_non_utf8_error_body_raises_llmunavailable`: stub response status 500 with `b"\xff\xfe"` body; assert `LLMUnavailable` with replacement chars, no `UnicodeDecodeError`.

**Verification test**

- **Tier:** T1
- **Input:** the stub response above
- **Expected output:** `LLMUnavailable`, message contains U+FFFD
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_llm_client.py::test_non_utf8_error_body_raises_llmunavailable -q`

**Cross-references:** F-BRAIN-015

---

### F-BRAIN-041 — Tool-call argument accumulation is unbounded between deltas

| Field | Value |
|---|---|
| **ID** | F-BRAIN-041 |
| **Title** | Tool-call argument accumulation is unbounded between deltas |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/brain/llm_client.py:114-125` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:124-125`
```python
                            if fn.get("arguments"):
                                current_tool_calls[idx]["arguments"] += str(fn["arguments"])
```

**What is wrong / assumed / missing**

The per-index argument string is concatenated for the whole stream with no size check; only `max_tokens` bounds it (512 tokens ≈ 2 000 chars, and a pathological or hostile-content prompt could raise that via config, since `max_tokens` is unvalidated in `LLMSettings`). The demux inline path has a 400-char cap (`toolcall_demux.py:93`); the structured path has none.

**Why it matters**

Unbounded buffer on an untrusted-content path, inconsistent with the demux's own cap; memory pressure on an edge path.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/llm_client.py:124-125`: cap at 4 096 chars — if the accumulated length exceeds, `logger.warning("tool_call_args_too_large")` and treat as malformed (per F-BRAIN-009 drop semantics). Before: unbounded. After: 4 096-char cap.
2. Add `tests/test_llm_client.py::test_structured_args_capped`: stream 5 000 chars of arguments; assert the call is dropped with the warning.

**Verification test**

- **Tier:** T1
- **Input:** the oversized-arguments stream
- **Expected output:** call dropped; warning logged
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_llm_client.py::test_structured_args_capped -q`

**Cross-references:** F-BRAIN-009

---

### F-BRAIN-042 — A code fence split across deltas is not detected, so code is spoken

| Field | Value |
|---|---|
| **ID** | F-BRAIN-042 |
| **Title** | A code fence split across deltas is not detected, so code is spoken |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/toolcall_demux.py:105-126` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/toolcall_demux.py:107-108`
```python
        # Handle code fences ```
        if "```" in text:
```

**What is wrong / assumed / missing**

Fence detection requires the full ` ``` ` sequence inside a single delta; a fence arriving as backtick fragments (common for llama tokenisers) renders as speakable code content until a complete ` ``` ` delta arrives. The "code block omitted." announcement is likewise fragment-dependent.

**Why it matters**

Prosody/noise on an edge path of the voice output; same defect class as F-BRAIN-021 (constructs spanning deltas), here in the demux rather than the normaliser.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/toolcall_demux.py`, `_process_text_delta()`: keep a trailing-context window of the last two characters across calls (append to a `self._tail` string) and detect a fence spanning boundaries before the plain-text return. Before: per-delta detection. After: 2-char window detection.
2. Add `tests/test_chunker.py::test_demux_fence_split_across_deltas`: feed `"`", "`\`" , ````", "code", "```" `; assert no code reaches a `TokenDelta`.

**Verification test**

- **Tier:** T1
- **Input:** the split-fence fixture above
- **Expected output:** zero code-content deltas; one "code block omitted." delta
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py -q`

**Cross-references:** F-BRAIN-021

---

### F-BRAIN-043 — First-chunk max (90) is not enforced: the candidate mechanism returns the first boundary ≥ min even when it exceeds max

| Field | Value |
|---|---|
| **ID** | F-BRAIN-043 |
| **Title** | First-chunk max (90) is not enforced: the candidate mechanism returns the first boundary ≥ min even when it exceeds max |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/chunker.py:227-235` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/chunker.py:227-233`
```python
            # Length criteria
            split_candidate = i + 1
            if split_candidate >= min_len:
                if split_candidate <= max_len:
                    return split_candidate
                elif candidate_split is None:
                    candidate_split = split_candidate
```

**What is wrong / assumed / missing**

The first boundary found at or above `min_len` becomes the chunk even when it is longer than `max_len` (90 first / 220 later). A 150-char first sentence therefore produces a 150-char first chunk, violating the intent of `FIRST_CHUNK_MAX_CHARS` ("bounds first-audio latency", Spec 08 §4) even though the spec's own wording does not say what to do when no boundary exists below max (the force-split only engages at 260).

**Why it matters**

The first-audio-latency feature can produce oversized first chunks whenever a sentence's first clause exceeds 90 chars; T-CHK-13 (≤ 90 within 8 deltas) is unattainable on such replies.

**Questions this raises**

1. Should the chunker force-split the first chunk at 90 (mid-sentence) to honour the latency bound, or keep the sentence whole? (Decision recorded: force-split at `max_len` whitespace — latency is the chunker's reason to exist.)

**Proposed remediation**

1. In `src/lucca/brain/chunker.py`, `_extract_chunks()` (`:136-148`): when no boundary ≤ max exists and `len(buffer) >= max_len`, split at the last whitespace before `max_len` (fall back to `max_len` hard) instead of accepting the oversized candidate. Before: oversized candidate accepted. After: max-enforced split.
2. Add `tests/test_chunker.py::test_t_chk_first_chunk_max_enforced`: a 150-char first sentence → first chunk ≤ 90 chars, remainder in the follow-up chunk.

**Verification test**

- **Tier:** T1
- **Input:** the 150-char fixture
- **Expected output:** first chunk ≤ 90 chars
- **Threshold:** first chunk length ≤ 90
- **Command:** `uv run pytest tests/test_chunker.py::test_t_chk_first_chunk_max_enforced -q`

**Cross-references:** F-BRAIN-022, F-BRAIN-044

---

### F-BRAIN-044 — Numbered-list protection only fires when the whole buffer so far is one token, so `2.` mid-text splits

| Field | Value |
|---|---|
| **ID** | F-BRAIN-044 |
| **Title** | Numbered-list protection only fires when the whole buffer so far is one token, so `2.` mid-text splits |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/chunker.py:223-225` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/chunker.py:223-225`
```python
                # Numbered list item check (e.g. "1.")
                if last_word.isdigit() and len(prev_text.split()) == 1:
                    continue
```

**What is wrong / assumed / missing**

The guard treats `N.` as a list marker only when the buffer up to the dot contains exactly one word; in `"1. First item\n2. Second item"` the `2.` is preceded by multi-word text and is treated as a sentence end, so the list is chopped after "…item 2." Per T-CHK-14 the expected output is 2 chunks ("1. First item", "2. Second item"); the current guard cannot produce that.

**Why it matters**

List-shaped replies chunk wrongly on an edge path (list content); accounted among the worst-chunked category with F-BRAIN-018.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/chunker.py:223-225`: treat `N.` as a list marker when the preceding token on the current line is exactly `N` (evaluate `prev_text` line-wise, not whole-buffer). Before: whole-buffer single-token rule. After: line-aware.
2. Un-xfail and assert `tests/test_chunker.py::test_t_chk_14_numbered_list` (added in F-BRAIN-022).

**Verification test**

- **Tier:** T1
- **Input:** `"1. First item\n2. Second item"` (with F-BRAIN-018's newline rule active)
- **Expected output:** chunks pair each list item; no split at the bare `2.`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_chunker.py::test_t_chk_14_numbered_list -q`

**Cross-references:** F-BRAIN-018, F-BRAIN-022

---

### F-BRAIN-045 — persona.toml `name` and `voice` keys are never read by the brain loader

| Field | Value |
|---|---|
| **ID** | F-BRAIN-045 |
| **Title** | persona.toml `name` and `voice` keys are never read by the brain loader |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `config/persona.toml:4-5`; `src/lucca/brain/prompt_builder.py:507-529` |
| **Status** | OPEN |

**Evidence**

`config/persona.toml:4-5`
```toml
name = "Lucca"
voice = "genki_heroine"
```
`src/lucca/brain/prompt_builder.py:517-529` — `set_persona(...)` is fed `archetype`, `formality`, `custom_prompt`, traits, `uses_your_name`, `admits_uncertainty`, boundaries, and user archetypes; `name` and `voice` appear nowhere in the call.

**What is wrong / assumed / missing**

Two of the file's top-level keys are dead on the brain side: `name` is read by nothing in `src/`, and `voice` is not consulted for TTS (the voice comes from `TTSSettings.voice`, `config.py:57` — the drift between the two is F-CORE-049's territory). An operator editing `name`/`voice` in persona.toml changes nothing at runtime.

**Why it matters**

Dead config keys in a user-facing file invite false expectations; the voice key in particular looks like the control for the spoken voice and is not.

**Questions this raises**

1. Should `voice` drive `TTSSettings.voice` (single source) or be deleted from persona.toml? (→ §10 Q-B-13; overlaps core Q-11.)

**Proposed remediation**

1. Decide the owner of the voice default (core Q-11); if persona.toml wins, wire `voice` into the TTS path via `ui.config_update` (CORE/SENS areas); if config wins, delete `name`/`voice` from `config/persona.toml` and from the template in `save_persona_to_config` (`prompt_builder.py:436-453`).
2. Add `tests/test_persona_toml.py::test_no_dead_keys`: assert every top-level key in the shipped persona.toml is consumed by `load_persona_from_config` or explicitly whitelisted as UI-only.

**Verification test**

- **Tier:** T1
- **Input:** the shipped `config/persona.toml`
- **Expected output:** zero unconsumed keys (or the whitelist documented)
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_persona_toml.py::test_no_dead_keys -q`

**Cross-references:** F-CORE-049, F-BRAIN-027

---

### F-BRAIN-046 — Dual persona.toml paths (deployed `C:\ProjectLucca\config` vs repo `config/`) can diverge silently

| Field | Value |
|---|---|
| **ID** | F-BRAIN-046 |
| **Title** | Dual persona.toml paths (deployed `C:\ProjectLucca\config` vs repo `config/`) can diverge silently |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/brain/prompt_builder.py:392-397, 428-430` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/prompt_builder.py:394-396`
```python
    path = config_path or Path(r"C:\ProjectLucca\config\persona.toml")
    if not path.exists():
        path = Path("config/persona.toml")
```

**What is wrong / assumed / missing**

The loader prefers the deployed file and falls back to a **cwd-relative** repo path; the saver (`:428-430`) mirrors the same logic. The repo copy (version-controlled, what tests and reviewers see) and the deployed copy (what the product reads and the UI writes) can diverge with no indication; the cwd-relative fallback also means the loaded file depends on the process's working directory. The same hard-coded absolute path pattern is F-CORE-030's territory for `affect.py`/`config.py`.

**Why it matters**

"Which persona is the product actually using?" is not answerable without checking two files and the cwd; a stale deployed copy silently overrides repo changes.

**Questions this raises**

1. Should the deployed file be a copy made at install/first-run (with the repo as source of truth), or should the repo file be deleted and the deployed file canonical? (→ §10 Q-B-14.)

**Proposed remediation**

1. In `src/lucca/brain/prompt_builder.py`: resolve the persona path via `get_config().home_dir / "config" / "persona.toml"` only (no cwd fallback); log the resolved path at load (`persona_loaded`, path=...). Before: dual path + cwd fallback. After: single LUCCA_HOME-anchored path.
2. Add `tests/test_persona_toml.py::test_persona_path_is_home_anchored`: with `LUCCA_HOME` set to a tmp dir, assert the loader reads the tmp copy regardless of cwd.

**Verification test**

- **Tier:** T1
- **Input:** the tmp-home test above
- **Expected output:** loader reads only the LUCCA_HOME copy
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_persona_toml.py::test_persona_path_is_home_anchored -q`

**Cross-references:** F-CORE-030, F-BRAIN-037

---

### F-BRAIN-047 — Assumption to confirm: the +136 MiB VRAM growth across the S1 session (8098 → 8234 MiB) is benign caching, not a leak

| Field | Value |
|---|---|
| **ID** | F-BRAIN-047 |
| **Title** | Assumption to confirm: the +136 MiB VRAM growth across the S1 session (8098 → 8234 MiB) is benign caching, not a leak |
| **Severity** | S4 — Info |
| **Category** | ASSUMPTION |
| **Location** | `docs/audit/evidence/S1_16b_gpu_after_llm.txt`; `docs/audit/evidence/S1_36_spike02.txt`; `docs/audit/evidence/S1_37_shutdown.txt` |
| **Status** | OPEN |

**Evidence**

Artefacts (rows 34, 67): 8 098 MiB after healthy start; 8 234 MiB at Spike-02 start **and** end (slope 0.00 MB/turn across the 20-run spike); 8 234 MiB after the app was killed with the server still up; 0 MiB after server exit (`S1_38_gpu_after_shutdown.txt`).

**What is wrong / assumed / missing**

The growth happened between server start and the spike window (which included the T3 hw tests and the 60 s app run), then froze. The spike suite's own S4 check (slope ≤ 20 MB/turn) cannot see it because its baseline was taken after the growth. No artefact isolates which activity (hw tests, app turn, mmproj warmup, KV growth) added the 136 MiB.

**Why it matters**

The S4 VRAM gate (≤ 9 728 MB) has ~1.5 GiB headroom; a per-activity leak of this size would matter over long sessions (T4 soak is out of audit scope). Currently an unverified assumption of benignness.

**Questions this raises**

1. Which activity added the 136 MiB, and does it recur per session or plateau? (→ §10 Q-B-15; measurable by sampling `nvidia-smi` around each hw test.)

**Proposed remediation**

1. In `scripts/run_spike02_suite.py` (joint with F-BRAIN-007): sample VRAM before server start, after health, after the first request, and after each section; record all samples in the JSON. Before: start/end only. After: per-section series.
2. Add a T4 soak note to the future soak plan: VRAM at turn 1, 100, 1000 must be flat within ±50 MiB.

**Verification test**

- **Tier:** T3
- **Input:** one instrumented spike run
- **Expected output:** per-section VRAM series in the report; growth localised to a named section
- **Threshold:** slope ≤ 20 MB/turn within each section
- **Command:** `uv run python scripts/run_spike02_suite.py`

**Cross-references:** F-BRAIN-026, F-BRAIN-007

---

### F-BRAIN-048 — Question: does closing the HTTP connection actually stop server-side generation within the barge-in budget on build 11026?

| Field | Value |
|---|---|
| **ID** | F-BRAIN-048 |
| **Title** | Question: does closing the HTTP connection actually stop server-side generation within the barge-in budget on build 11026? |
| **Severity** | S4 — Info |
| **Category** | ASSUMPTION |
| **Location** | `src/lucca/brain/llm_client.py:183-198`; `docs/audit/evidence/S1_36_spike02.txt` |
| **Status** | OPEN |

**Evidence**

`src/lucca/brain/llm_client.py:185-191`
```python
        self.aborted = True
        if self.active_client:
            try:
                self.active_client.close()
            except (httpx.HTTPError, OSError) as exc:
                logger.debug("llm_abort_client_close_error", error=str(exc))
            self.active_client = None
```
Artefact: `docs/audit/evidence/S1_36_spike02.txt` (row 67) — the explicit release endpoint 501s ×10, so connection close is the only live mechanism.

**What is wrong / assumed / missing**

`abort()` assumes llama-server cancels the slot task when the client disconnects. Nothing in the repo or the S1 evidence verifies this on build 11026: the T3 barge-in test measures client-side flag latency (30.07 ms), and the spike's S8 measured a 501 round-trip. If the server keeps decoding to `max_tokens` after disconnect, every barge-in leaves up to 512 tokens of GPU work between the user and the next turn's first token.

**Why it matters**

Spec 10's barge-in gate (slot idle ≤ 100 ms) is unverifiable until this is measured; the answer changes F-BRAIN-014's remediation (flag vs ADR change).

**Questions this raises**

1. The question is the finding: measure slot state after disconnect (→ §10 Q-B-06, same measurement).

**Proposed remediation**

1. Execute the measurement in F-BRAIN-014 step 2 (poll `GET /slots` after abort; assert idle ≤ 100 ms) and record the result in `logs\test_reports\`.
2. Depending on the result, either document connection-close as the designed mechanism (new ADR note) or add the enabling flag to `build_launch_command` (F-BRAIN-014 step 3).

**Verification test**

- **Tier:** T3
- **Input:** mid-generation abort on real hardware
- **Expected output:** measured ms-to-slot-idle recorded; ≤ 100 ms or a documented design change
- **Threshold:** ≤ 100 ms
- **Command:** `uv run pytest -m hw tests/test_phase1_live_hw.py::test_live_barge_in_abort -q`

**Cross-references:** F-BRAIN-014, F-BRAIN-006

---

## 9. Assumptions register

| # | Location | Assumption embedded in code | Why unverified | Risk if false |
|---|---|---|---|---|
| A-B-01 | `llm_client.py:39` | `base_url` points at *our* llama-server with the right model/mmproj | No `/props` model check (core A-02) | App talks to a foreign/text-only server; audio mode silently degrades |
| A-B-02 | `llm_client.py:73` | `chat_template_kwargs: {"tools_in_user_message": False}` is honoured by build 11026's Jinja path | No test inspects the rendered template | Tool calls land in content; demux must catch them (only first-12-chars covered) |
| A-B-03 | `llm_client.py:114` | `tc["index"]` is always an int | No malformed-index fixture | `int()` ValueError escapes the generator |
| A-B-04 | `llm_client.py:185-191` | Closing the HTTP connection cancels server-side generation | Never measured (F-BRAIN-048) | Barge-in leaves up to 512 tokens of GPU work queued |
| A-B-05 | `llm_client.py:80` | 30 s is a safe universal timeout for connect+read | No stall test; no connect split (F-BRAIN-016) | 30 s silent "thinking" on a wedged server |
| A-B-06 | `prompt_builder.py:47-91` | The architecture described in the prompt matches the deployment | Measured false (F-BRAIN-004) | Wrong tool selection; false claims spoken |
| A-B-07 | `prompt_builder.py:394-396` | The deployed persona.toml exists and is the intended one | Dual-path + cwd fallback (F-BRAIN-046) | Silent built-in persona or stale deployed copy |
| A-B-08 | `prompt_builder.py:630-634` | Memory hit content is safe to interpolate raw into the system message | Latent (memories always None) | Injection surface when retrieval is wired (F-BRAIN-011) |
| A-B-09 | `chunker.py:42-46` | 24/90/40/220/260 char bounds fit Kokoro's synth-time budget | No synth-time-per-chunk-length measurement | Chunks exceed the TTS stage budget (Spec 10 S4) |
| A-B-10 | `chunker.py:121` | Per-delta normalisation is equivalent to buffer normalisation | Measured false for spanning constructs (F-BRAIN-021) | Markdown/URLs spoken |
| A-B-11 | `server_ctl.py:254` | `app\llama-server\llama-server.exe` is the canonical exe location | SKILL.md says `app\bin\` (charter §10 stale-path note) | Docs-driven manual starts fail |
| A-B-12 | `server_ctl.py:282` | Omitting `--mmproj` when the file is missing is the right degradation | No spoken notice (ADR-001 O-4 requires one) | Silent text-only mode |
| A-B-13 | `server_ctl.py:346-360` | Any process named `llama-server` is ours to kill | No scoping (F-BRAIN-024) | Foreign processes terminated |
| A-B-14 | `scripts/download_llm_models.py:31-47` | The bartowski backbone is an acceptable Ultravox substitute | ADR-001 S10 never performed (F-BRAIN-002) | Audio mode runs an unverified backbone |
| A-B-15 | `scripts/run_spike02_suite.py:121` | 42.5 s is the cold-start time | Hard-coded constant (F-BRAIN-007) | Fabricated sign-off |
| A-B-16 | `config/intents.toml` | Editing the lexicon changes classification | Verbs unread; router unwired (F-BRAIN-027) | Operator changes are no-ops |
| A-B-17 | `tests/fakes/fake_llm.py:29-30` | Fake defaults (`0.2`/`512`) match the real client's config-derived defaults (`0.6`/`512`) | Temperature differs | Turn-loop tests exercise a colder model than production |

## 10. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-B-01 | Is the bartowski Q6_K backbone tensor-compatible with the ggml-org Ultravox v0.5 backbone for projector audio embeddings? | Determines whether F-BRAIN-002 is a quality risk or a fatal mismatch | measurement: `parse_gguf_file` tensor names + a controlled A/B of the two backbones on the 20 audio fixtures |
| Q-B-02 | The pre-audit `phase0_llm.json` recorded `S5: FAIL` — was Phase 1 entered with a known-failing Phase-0 gate, and where is that decision recorded? | Charter §5.3 phased discipline | user / project history |
| Q-B-03 | Should the audit re-baseline (new S0) before the remaining area subtasks, given F-BRAIN-008? | Evidence integrity for MEM/REAS/ROUT/SBX/SENS/UI | audit owner |
| Q-B-04 | Should memory hits live in the system message (prefix-cache-friendly) or a user-role context message (lower instruction priority)? | F-BRAIN-011 remediation shape | architect + ADR-001 note |
| Q-B-05 | Which tokenizer should the context budgeter use (server `/tokenize` round-trip vs local approximation)? | F-BRAIN-012 accuracy vs latency | architect |
| Q-B-06 | Does closing the HTTP connection cancel generation on build 11026, and in how many ms? | F-BRAIN-014/048; Spec 10 barge-in gate | measurement (`/slots` poll after abort) |
| Q-B-07 | Is there a build-11026 flag enabling `/slots/0?action=release`, or was the endpoint removed upstream? | F-BRAIN-014 step 3 | llama.cpp b11026 changelog / `llama-server --help` |
| Q-B-08 | What TTFT/total budgets should the stream watchdog use given 73–80 tok/s decode and tool-call chaining? | F-BRAIN-016 constants | measurement across 50 real turns |
| Q-B-09 | Does build 11026 emit `usage` in the final SSE chunk by default or only with `stream_options.include_usage`? | F-BRAIN-017 step 1 | measurement (one request each way) |
| Q-B-10 | Does build 11026 support JSON logging under another flag, and should anything parse the server log? | F-BRAIN-023 docs update | `llama-server --help` on the deployed binary |
| Q-B-11 | When the router is wired, must unknown intent→tool mappings fail closed at load? | F-BRAIN-027 remediation | ROUT auditor / architect |
| Q-B-12 | Should `spoken_prefix` be wired into interrupt-history (its Spec 08 §5 purpose) or deleted? | F-BRAIN-036 step 2 | CORE remediation owner (F-CORE-007/011) |
| Q-B-13 | Should persona.toml `voice` drive the TTS voice, or `TTSSettings.voice`? | F-BRAIN-045; overlaps core Q-11 | user |
| Q-B-14 | Is the repo `config/persona.toml` a template copied at install, or should the deployed file be the only one? | F-BRAIN-046 | user / packaging auditor |
| Q-B-15 | Which activity added +136 MiB VRAM between server start and the spike window? | F-BRAIN-047 | measurement (per-section sampling) |
| Q-B-16 | The T3 conversational turn returned `tokens_out=0` — did the server emit zero content deltas, or did the client drop them? | F-CORE-007 upstream cause; F-BRAIN-015 is one candidate | measurement: server log slot timings at 00:58Z (`S1_15b_llama_server.stderr.log`) + instrumented client |

## 11. Coverage gaps

### 11.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| T-CHK-06 ellipsis composition | Spec 08 §6 | none (broken — §5.3) |
| T-CHK-11 idle flush 350 ms | Spec 08 §4/§6 | none (feature absent — F-BRAIN-019) |
| T-CHK-13 first chunk ≤ 90 chars within 8 deltas | Spec 08 §6 | none (not guaranteed — F-BRAIN-043) |
| T-CHK-14 numbered-list chunking | Spec 08 §6 | none (broken — F-BRAIN-044) |
| T-CHK-10 30-stream demux gate | Spec 08 §2/§6 | 2 of 30 streams |
| T-CHK-12 2 000-case property + join equality | Spec 08 §6 | 100 cases, no join assertion |
| Newline boundaries (`\n`, `\n\n`) | Spec 08 §3/§4 | none (feature absent — F-BRAIN-018) |
| Context token budget enforcement | Spec 10 §4 | none (feature absent — F-BRAIN-012) |
| Memory block caps/marking | Spec 10 §4, TM-02 | none (latent — F-BRAIN-011) |
| Tool-call schema validation | Spec 12 Z1 | none (feature absent — F-BRAIN-010) |
| Malformed tool-call drop | Spec 12 Z1 | none (F-BRAIN-009) |
| Abort → slot-idle verification | ADR-001 :55, Spec 10 | none (F-BRAIN-014/048) |
| Launch-command executability vs deployed binary | ADR-001 | none (F-BRAIN-029) |
| Model file sha256 verification | Spec 12 :3, :72 | none (F-BRAIN-003) |
| ADR-001 S7 (grammar + tools + audio in one request) | ADR-001 :102 | **absent from the spike suite entirely** |
| ADR-001 S10 as specified (cascade, same backbone, latency delta) | ADR-001 :105 | reduced to 20 text prompts (F-BRAIN-002) |
| Persona cross-process propagation | impl. prompt WI-2.8 | none (F-BRAIN-013) |
| `restart_server` health-poll path | impl. prompt WI-3.3 | none (dead — F-BRAIN-035) |

### 11.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| `scripts/test_s1_startup.py` | cold-start ≤ 60 s | health of any server on :8080 (0.07 s "start" against a pre-existing server, row 64) |
| `run_spike02_suite.py` S1/S5/S8/S9 | Phase-0 gates | constant 42.5; WorkingSet64 of a GPU-resident process; latency of a 501; server-alive-after (F-BRAIN-007) |
| `tests/test_server_ctl.py` | launch command correctness | flag presence only; never executes the command (F-BRAIN-029) |
| `tests/test_gguf_parser.py` | GGUF parsing | a synthetic format real files do not have (string `quantization_version`) (F-BRAIN-033) |
| `tests/test_chunker.py::test_t_chk_10` | demux gate | 1 inline + 1 plain stream of the 30 specified |
| `tests/test_prompt_builder.py` / `test_persona_toml.py` | prompt/persona correctness | whatever global persona state earlier tests left (F-BRAIN-031) |
| `tests/fakes/fake_llm.py` | LLM stand-in | never models malformed SSE, HTTP errors, 501 abort, usage chunks, or structured tool_calls; defaults diverge from production (A-B-17) |

## 12. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** Reviewing F-BRAIN-005 (quote depth) surfaced the per-scan re-accumulation as a second, distinct defect in the same function — kept inside F-BRAIN-005 as one mechanism with two causes, and surfaced the streaming-equivariance test gap (added to its remediation). Reviewing F-BRAIN-009 surfaced the empty-name silent drop (added as remediation step 2) and the unbounded accumulation sibling → F-BRAIN-041. Reviewing F-BRAIN-021 surfaced the same spanning-delta class in the demux's fence handling → F-BRAIN-042. Reviewing F-BRAIN-026 surfaced the signed/unsigned GGUF sibling → F-BRAIN-033. Reviewing F-BRAIN-007 split the four fabrications into one finding (one artefact, one generator) but filed the startup-script sibling separately → F-BRAIN-028. Reviewing F-BRAIN-036 aggregated four dead symbols into one maintainability finding rather than four one-liners (recorded here as a deliberate deviation from strict one-defect splitting; each symbol's disposition is a separate remediation step).
2. **Unasked questions.** 16 questions registered (§10); each finding's `Questions this raises` was re-read and anything answerable from code was answered in the finding instead (e.g. F-BRAIN-004 Q1 now records the live-derived decision; F-BRAIN-013 Q1 records re-read-from-disk).
3. **Unwarranted assumptions.** F-BRAIN-002 originally asserted the backbone "cannot understand audio"; downgraded to "unverified" with the compatibility question Q-B-01, because ADR-001 :65's frozen-backbone theory may hold. The VRAM section (§6.3) presents expected ranges with the compute-buffer estimate labelled as an estimate, not a measurement. F-BRAIN-047/048 were graded S4 rather than asserting a leak/abort defect without evidence. The S1-era `--log-format`/DEVNULL defects are cited as historical (artefact-based), not asserted of the current tree (F-BRAIN-008 notice).
4. **Incomplete planning.** Every remediation was checked for file, function, before/after, and a runnable command; where a decision was needed it was made in the finding (F-BRAIN-009 drop-not-notice; F-BRAIN-010 reject-at-client; F-BRAIN-013 re-read-from-disk; F-BRAIN-019 orchestrator-side pump; F-BRAIN-043 force-split at max). Remediations touching other areas are labelled (CORE: F-BRAIN-013/019/020/032; UI: F-BRAIN-024/035; ROUT: F-BRAIN-027; TEST: F-BRAIN-008/022/029/031).
5. **Architectural flaws → F-ARCH candidates for the orchestrator.** (a) The model-supply chain (download → rename → no manifest → no boot verification) is a cross-cutting trust failure spanning BRAIN/CORE/TEST (F-BRAIN-002/003/026, F-CORE-022/025) — recommend an `F-ARCH` supply-chain finding. (b) The fictional-capability prompt + fictional `query_capabilities` manifest (F-BRAIN-004) is one structural honesty defect spanning BRAIN/SBX/UI. (c) The turn loop's missing validation layer (F-BRAIN-009/010/030) is the Z1→Z0 boundary the threat model assumes exists; it should be one `F-ARCH` boundary finding rather than three local fixes. (d) The mid-audit tree mutation (F-BRAIN-008) is a programme-level process finding affecting all areas.

Severity re-grades during the pass: F-BRAIN-005 S2→S1 (main-path latency feature broken on common quoted text); F-BRAIN-004 S2→S1 (measured main-path wrong-tool selection); F-BRAIN-008 S1→S2 (process breach, not a product defect); F-BRAIN-020 kept S2 (degradation, not failure); F-BRAIN-047/048 set S4 (evidence insufficient for a defect assertion).

**Third pass (2026-09-18T06:24Z, post re-inventory).** The re-inventory (F-BRAIN-008 remediation step 2, executed as [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) + evidence `S2b_01`/`S2b_02`) falsified the first pass's central factual claim: the "all five brain modules mutated" comparison had mixed S0's non-blank-line metric with total line counts from file reads. Corrections applied: header baseline-delta notice rewritten; F-BRAIN-008 rewritten (narrow verified delta: `server_ctl.py` post-S1, `main.py` + `scripts/test_s1_startup.py` post-S0; 107/110 in-scope files unchanged); Q-B-03 answered (no re-baseline needed). No finding other than F-BRAIN-008 depended on the false delta — all 48 findings' file:line citations were taken from direct reads of the current tree and are unaffected; the §1 module-map LOC column reports total lines (its stated basis) and stands.
