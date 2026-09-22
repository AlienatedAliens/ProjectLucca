# Cognitive Audit — Findings Register (WO-9)

**Date:** 2026-09-22
**Charter:** [`docs/audit/00_AUDIT_CHARTER.md`](../00_AUDIT_CHARTER.md)
**Plan:** [`plans/2026-09-22_reasoning_loop_remediation_and_audit.md`](../../../plans/2026-09-22_reasoning_loop_remediation_and_audit.md)
**Companion map:** [`docs/audit/COGNITIVE_LOOP_MAP.md`](../COGNITIVE_LOOP_MAP.md)

## Remediation status (WO-9 Phase A, 2026-09-22)

| Item | Finding(s) | Status | Commit |
|---|---|---|---|
| A1 confirmation deadlock | F1 | FIXED — press-during-confirm_wait is the answer mechanism; typed answers routed; T-BRG-05 rewritten | ad7f3fb |
| A2 grounded memory_commit | F2 | FIXED — ADR-010: candidate {s,p,o,quote} validated by FactExtractor against the turn transcript, signed USER_DERIVED; sandbox block kept as defense-in-depth | ad7f3fb |
| A3 passive fact extraction | F3 | FIXED — is_named/lives_in/works_at regex candidates, interrogative+hypothetical guards, is_named supersession | ad7f3fb |
| A9 ASSISTANT_ACTION receipts | F8 | FIXED — all tool attempts incl. cancels/timeouts/refusals persisted, signed via create_tool_result_signer factory | ad7f3fb, e6e1ed3 |
| A4 promise-without-action | F4 | FIXED — detect_promised_action_claims + Honesty Directive re-prompt with per-round buffer | 8a0fea6 |
| A5 convergence loop | F5 | FIXED — terminate on no-tool round; cap 8 runaway guard with honest-synthesis directive; Repeat Guard; rounds_used/cap_hit telemetry | 9601e36 |
| A6 demux hardening | F6 | FIXED — mid-stream detection, lenient sentinel-args parser, never-speak-unresolved invariant; T-CHK-12/13 | 8f584a5 |
| A7 coherence verb families | F7 | FIXED — memory_search/memory_commit/invoke_skill families + checked/committed/invoked/recalled/queried verbs | e51a2c7 |
| A10 memory-tab freshness | F17 | FIXED — mem.commit bus events published; tab refresh on switch + 5s visible-poll (full UI bus subscription deferred) | 9b01fd7 |
| A11 router session_id | F10 | FIXED — self.session_id passed in both turn paths | d40fc31 |
| A12 action-turn beliefs | F9 | FIXED — zero-tool-call gate removed; Scenario 1 contract revised | d40fc31 |
| A13 tool-surface truth | F14/F16 | FIXED — launch_app advertised (confirmation-gated, registry 17/18); Docker precondition in prompt contract | 135d8f7 |
| A14 self_history_search | F18 | FIXED — model-callable SELF_HISTORY tool backed by the cascade substrate | e6e1ed3 |
| F5 residual | F5 | Deferred: F11 last-tool-only narration, F12 raw-vs-normalized transcript, F13 CLARIFY no-op, F15 async-task start tool, F19 write-only telemetry, F20 heuristics→config | WO-9 follow-up |

**Gate status:** ruff clean; full non-hw suite 576 passed (packaging tests pass in isolation; earlier failures were timeout contention). The `@hw` A1 live battery re-run and the live Sean-transcript smoke require the running llama-server and are left as the operator's verification step.

Severity: **P0** = user-facing capability is broken or a lie; **P1** = intelligence/honesty degraded; **P2** = subsystem blind spot; **P3** = hygiene.

---

## B2. Tool Surface Truth Table

Advertised = present in [`get_default_native_tools()`](../../src/lucca/core/capabilities.py:34) and therefore visible to the LLM via [`get_all_tool_definitions()`](../../src/lucca/brain/prompt_builder.py:691). Confirmation per [`requires_confirmation()`](../../src/lucca/sandbox/policy.py:139) (WRITE/LAUNCH, untainted).

| Tool | Advertised | Dispatcher | Confirmation | Can succeed (default config) | Verdict |
|---|---|---|---|---|---|
| `read_file` | yes | RPC (Docker) | no | only if Docker CE/WSL2 up | conditional |
| `write_file` | yes | RPC (Docker) | **yes** | Docker up **and** confirmation possible | **broken by F1** |
| `list_dir` | yes | RPC (Docker) | no | only if Docker up | conditional |
| `search_text` | yes | RPC (Docker) | no | only if Docker up | conditional |
| `run_python` | yes | RPC (Docker) | **yes** | Docker up and confirmation; explicit fail-closed otherwise | **broken by F1** |
| `search_web` | yes | direct | no | yes (network) | ok |
| `fetch_url` | yes | direct | no | yes | ok |
| `query_capabilities` | yes | direct | no | yes | ok |
| `invoke_skill` | yes | orchestrator | no (sub-actions gated individually) | yes | ok |
| `memory_search` | yes | direct | no | yes | ok |
| `memory_commit` | yes | **fails closed always** (F2) | **yes** | **never** | **P0 lie** |
| `note_write` | yes | direct | no (Class A exemption) | yes | ok |
| `note_read` | yes | direct | no | yes | ok |
| `self_metrics` | yes | direct | no | yes | ok |
| `sys_info` | yes | direct | no | yes | ok |
| `launch_app` | **no** | direct (host launcher) | **yes** | rule-path only | **F14** |
| `delete_file` | **no** | RPC (Docker) | **yes** | rule-path only | F14 |
| `browse_page` / `render_page` | **no** | direct (Playwright lazy) | no | unadvertised; Playwright optional | F14 |
| `get_task_status` / `list_tasks` / `cancel_task` | **no** | direct | no | unreachable from LLM | **F15** |

### F14 (P1): Shadow tool surface — dispatched but unadvertised
`launch_app`, `delete_file`, `browse_page`, and the three async-task tools have full dispatchers and risk-map entries but are absent from the native registry, so the LLM cannot call them in FULL_LOOP. `launch_app`/`delete_file` are reachable only when a MicroScheme rule fires (ACT_THEN_NARRATE). Meanwhile the `query_capabilities` spoken fallback tells the user "I can launch desktop applications including Calculator, Notepad, and Edge" ([`orchestrator.py:2954-2956`](../../src/lucca/core/orchestrator.py:2954)) — a capability the model cannot invoke on its own. Decision needed: advertise `launch_app` (confirmation-gated, whitelist-bound) or narrow the spoken claims.

### F15 (P2): Async task subsystem is a write-only API
`AsyncTaskManager` (D-SAND-03) and its three status tools exist, but no advertised tool can *start* an async task (`launch_async` is internal) and the status tools are unadvertised. Long-running work is therefore impossible from FULL_LOOP.

### F16 (P1): Docker dependency makes the entire file/code surface conditional
With `use_direct_fallback = False` (D-AUD-13), every workspace tool (`read_file`, `write_file`, `list_dir`, `search_text`, `run_python`, `delete_file`) fails when Docker CE/WSL2 is down. The model is not told this in its tool manifest; it discovers it only via the error string "My file sandbox isn't available — Docker isn't reachable" ([`orchestrator.py:2985-2986`](../../src/lucca/core/orchestrator.py:2985)). Acceptable as policy, but the *prompt contract* should state the dependency so the model can pre-emptively set expectations (see B6).

### Confirmation-gated surface vs F1
The full WRITE/LAUNCH surface — `write_file`, `delete_file`, `run_python`, `memory_commit`, `launch_app` — is currently unconfirmable by voice or text (F1). Until A1 lands, the only working confirmation channel is the UI click (`ui.confirm_result` → [`confirm_action`](../../src/lucca/core/orchestrator.py:609)).

### `_describe_tool_action` coverage
Human-readable confirmation prompts exist for `launch_app`, `write_file`, `delete_file`, `run_python`, `fetch_url`; everything else falls back to "execute {name}" — including `memory_commit`, which is exactly the case where the prompt must read back the fact (folded into A2).

---

## B1 findings (from COGNITIVE_LOOP_MAP.md)

| # | Finding | Severity |
|---|---|---|
| F9 | Belief formation disabled on tool-call turns | P2 |
| F10 | `session_id=trace_id` in router calls — session telemetry meaningless | P2 |
| F11 | ACT_THEN_NARRATE narrates only the last tool result | P3 |
| F12 | Router sees raw transcript, rule engine sees normalized | P3 |
| F13 | CLARIFY route action has no distinct handling | P3 |

## Live-log findings (pre-audit)

| # | Finding | Severity |
|---|---|---|
| F1 | Confirmation deadlock: PTT press / text input during `confirm_wait` cancels the pending action | P0 |
| F2 | `memory_commit` advertised but fails closed (ADR-006, no LLM_NARRATION signer) | P0 |
| F3 | `FactExtractor` (only USER_DERIVED path) never called from any turn path | P1 |
| F4 | Promise-without-action ("I'll go ahead and…") unguarded by coherence gate | P1 |
| F5 | Fixed `max_rounds=3`, tools stripped on final round — no convergence | P1 |
| F6 | Gemma `<\|tool_call\|>` demux: 24-char window, malformed args leak as speech (F-WO8-26) | P1 |
| F7 | Coherence verb families missing `invoke_skill`/`memory_search`/`memory_commit`/`note_write` | P2 |
| F8 | `ASSISTANT_ACTION` provenance defined/signed/eligible but never committed | P1 |

### F20 (P2): Hard-coded heuristic keyword lists should be config-driven
Raised by the operator during A2 review. Security invariants (closed `PREDICATES`, `MEMORY_ELIGIBLE`) are correctly code-resident — they are the trust boundary and must be tamper-evident; the canonical `FACT_PREDICATES` set now lives once in [`core/schemas.py`](../../src/lucca/core/schemas.py) with the gate and tool manifest both deriving from it. But *behavioural heuristics* are hard-coded where they belong in config:
- follow-up/tool-gating keyword lists ([`orchestrator.py:2398-2441`](../../src/lucca/core/orchestrator.py:2398))
- search category keywords + Levenshtein query injection ([`orchestrator.py:2893-2910`](../../src/lucca/core/orchestrator.py:2893))
- epistemic substrate keyword classifier ([`cascade.py:549-588`](../../src/lucca/core/cascade.py:549))
- spoken fallback strings in `_handle_tool_call` / `_select_verbal_cue`
Fix direction: move to `config/heuristics.toml` with code defaults as fallback; keep security invariants in code. Defer to WO-9 hygiene pass.

---

## B3. Memory Ingestion & Retrieval Flow

### Commit-path matrix

| Path | Provenance | Kind | Wired? |
|---|---|---|---|
| `_commit_transcript` (every voice/text turn) | `USER_EXPLICIT` | transcript | yes |
| `_commit_assistant_utterance` | `ASSISTANT_UTTERANCE` | utterance | yes |
| `_maybe_form_belief` (FULL_LOOP, zero-tool turns only — F9) | `ASSISTANT_BELIEF` | belief | yes, gated |
| `_commit_coherence_breach` | `COHERENCE_BREACH` | breach | yes |
| `MemoryManager.add_memory` (UI / `lucca-admin`) | `USER_EXPLICIT` (ui-admin signer) | fact | yes |
| `FactExtractor.extract_and_sign` | `USER_DERIVED` | fact | **no (F3)** |
| `_record_tool_receipt` | `ASSISTANT_ACTION` | action | **no — RAM only (F8)** |
| Rule engine assertions | `LISP_ASSERTION` | assertion | yes |
| Sandbox tool results | `TOOL_VERIFIED` / `TOOL_CONTENT_UNTRUSTED` | — | `TOOL_CONTENT_UNTRUSTED` is never memory-eligible (by design) |

### Retrieval visibility

- `HybridRetriever` (prompt memory block): ranks by BM25 + vector + recency + importance + provenance tier; 2,048-token quota (D-MEM-03). All memory-eligible provenance classes participate.
- `memory_search` tool → [`MemoryManager.list_memories`](../../src/lucca/memory/manager.py:47): **no provenance filter** — assistant classes (utterances, beliefs, breaches) are included, with the F-WO8-22 tokenized fallback. Self-history is therefore reachable via the tool, but mixed indiscriminately with user facts.
- `SELF_HISTORY` substrate ([`cascade.py:947`](../../src/lucca/core/cascade.py:947)): reachable **only** through epistemic-intent classification (keyword-gated), never as a model-callable tool.

### F17 (P2): Memory tab has no live refresh — and the bus event for it was never wired
- `_refresh_memories` fires only at tab build ([`settings_dialog.py:2470`](../../src/lucca/ui/settings_dialog.py:2470)), on manual Search/Enter, on kind-filter change, and after UI-initiated edits. [`_on_tab_changed`](../../src/lucca/ui/settings_dialog.py:2801) refreshes only the diagnostics tab (index 8).
- `mem.commit` / `mem.reject` / `mem.search` event types are defined in [`events.py:43-46`](../../src/lucca/core/events.py:43) but **no publisher exists** — the orchestrator never emits them. There is no timer and no bus subscription.
- Data visibility itself is fine: UI and core share `C:\ProjectLucca\data\memory.sqlite` ([`db.py:23`](../../src/lucca/memory/db.py:23)), WAL mode, and `MemoryManager` opens a fresh connection per call, so committed rows are readable cross-process immediately.
- **Net effect:** while the settings dialog stays open, new memories never appear; reopening the dialog shows them. Combined with F1/F2/F3 (nothing but raw transcripts was being committed in the logged session), this reads as "no new memories forming."
- Fix direction: publish `mem.commit` from `MemoryStore.commit` (or the orchestrator commit wrappers), subscribe in the UI process, debounce-refresh the memory tab; also refresh on tab switch.

---

## B4. Self-Knowledge & Reflection Capability

### What exists and fires live

| Mechanism | Trigger | Status |
|---|---|---|
| `ReflectionEngine.detect_and_handle_contradiction` | every `USER_EXPLICIT` commit via `_check_contradictions` | wired |
| `pending_spoken_updates` delivery | start of next `_stream_llm_speech` | wired |
| `rollup_nightly` | periodic check in [`main.py:298-299`](../../src/lucca/main.py:298) via `is_rollup_due` | wired |
| Review queue approve/reject | UI / `lucca-admin` | wired |
| `SELF_HISTORY` substrate | epistemic keyword classifier only | **partially reachable** |

### F18 (P1): No model-callable self-history tool
The model cannot deliberately query its own action record. "Did you actually do X?" reaches `SELF_HISTORY` only if the keyword classifier ([`cascade.py:563-584`](../../src/lucca/core/cascade.py:563)) detects self-history intent and injects it as epistemic context — and even then, F8 means the record is empty for LLM-initiated tools. `memory_search` partially covers this (no provenance filter, so `ASSISTANT_*` rows are searchable) but mixes self-history indiscriminately with user facts and cannot see `execution_triples` at all.
**Fix direction (ADR draft):** new READ tool `self_history_search(query, since, provenance_filter)` backed by the SELF_HISTORY query path (execution_triples ∪ ASSISTANT_ACTION ∪ ASSISTANT_UTTERANCE ∪ COHERENCE_BREACH ∪ ASSISTANT_BELIEF), returning receipt-style rows. Depends on A9 (F8) to have content worth querying.

### F19 (P3): DecisionRecords and TurnTraces are write-only at runtime
Router decisions (SQLite `decisions` + JSONL) and turn traces ([`trace.py:103`](../../src/lucca/core/trace.py:103)) have no live retrieval path. "Why did you handle it that way?" is unanswerable in-session. Acceptable for latency/privacy; note as a deliberate boundary or add to `self_history_search` scope later.

---

## B5. Honesty Gate Coverage Matrix

| Claim type in output | Gate | When | Status |
|---|---|---|---|
| Past-tense action claim ("I opened/fetched/saved X") | `TruthInReceiptMatcher` (streaming) + `detect_ungrounded_action_claims` (post-hoc) | live + finalize | covered, minus F7 verb-family gaps |
| **Future/promise action claim ("I'll go ahead and…", "doing it right now")** | — | — | **UNCOVERED (F4)** |
| Citation / URL / source attribution | `CitationProvenanceMatcher` | streaming | covered |
| Capitulation / sycophantic reversal | OutputSupervisor Tier-1 | streaming | covered |
| Deontic claim ("I can/cannot do X") | `DeonticAssertionMatcher` | streaming | covered |
| Belief contradiction vs prior stance | `_check_contradictions` → ReflectionEngine | finalize | covered (user-commit-triggered only) |
| Memory-operation claim ("I saved/remember X") | verb families | post-hoc | **gap (F7)** |
| Identity / substrate claims ("I am Gemma", "I run on…") | prompt contract only | — | prompt-level; no gate (bake-off 2026-09-21 fix was prompt-side) |
| Pre-execution invariant violation | BDI validator | pre-dispatch | covered |
| Memory write provenance | ProvenanceGate | commit | covered |

---

## B6. Prompt & Self-Model Contract Audit

[`ARCHITECTURAL_SELF_AWARENESS`](../../src/lucca/brain/prompt_builder.py:68) and tool descriptions vs substrate reality:

| Prompt/tool claim | Reality | Finding |
|---|---|---|
| Tool manifest: `memory_commit` — "Commit a verified fact or user preference into long-term memory" | dispatcher fails closed always | **F2 (P0)** — fixed by A2 |
| "You can execute sandboxed Python code" | only when Docker CE/WSL2 is up; fails closed otherwise | F16 — add dependency note to prompt |
| "read and write workspace files" | reads need Docker; writes need Docker **and** confirmation (F1-broken) | F1/F16 |
| `query_capabilities` spoken fallback: "I can launch desktop applications including Calculator, Notepad, and Edge" | `launch_app` unadvertised in FULL_LOOP (F14) | **F14** — advertise or narrow claim |
| "AUTONOMOUSLY EXECUTE the necessary tool calls immediately" (research directive) | true for NETWORK tools; false for WRITE/LAUNCH (confirmation) — acceptable, but the model is never told confirmation exists, so it narrates "doing it now" while the system is actually waiting on the user | fold into A4 prompt wording |
| "evaluate MicroScheme LISP reasoning pathways before neural inference" | true (rule engine runs pre-route) | ok |

**Contract principle for B7:** every capability string shown to the model or spoken to the user must be traceable to a dispatcher that can succeed under current config, or must state its precondition.
