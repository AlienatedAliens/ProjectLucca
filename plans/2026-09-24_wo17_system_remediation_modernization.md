# WO-17 — System Remediation & Modernization Plan (v2, Amended)

**Date:** 2026-09-24
**Status:** Ratified for implementation (supersedes the v1 chat draft)
**Scope:** Comprehensive rollup of all defects and architectural bottlenecks identified during live workstation user testing, plus six latent defects discovered during adversarial plan review.
**Approach:** Implementation of Solution B (Open-Predicate Knowledge Graph) alongside targeted fixes for runtime memory wiring, arithmetic tool gating, telemetry, routing, audio queue stability, confirmation provenance, and extraction hygiene.

---

## 1. Executive Summary & Root Cause Matrix

During live user testing on native hardware, the system experienced several cascading failures across the memory, reasoning, security, and senses subsystems. Every failure was traced to a specific code invariant. Rows 1–9 are the original live-test findings (all verified against the code during review). Rows 10–15 are latent defects discovered during adversarial review of v1 of this plan — they do not yet have user-visible symptoms only because the memory subsystem is dormant (row 1); they activate the moment Phase 1 lands.

| # | User-Visible Failure | Root Cause in Code | Subsystem |
|---|----------------------|--------------------|-----------|
| 1 | Memory completely empty across all live sessions | `main.py:179` calls `Orchestrator()` with no arguments; `self.memory_store` and `self.db` default to `None` (`orchestrator.py:241`). Every commit path early-returns. | Memory / Main |
| 2 | "Cancelled" on memory commit | `memory_commit` is classified as `Risk.WRITE` in `policy.py:47`; pauses for PTT voice confirmation and fails closed on natural speech via the anchored `^(yes\|yeah\|…)` regex at `policy.py:21`. | Sandbox Policy |
| 3 | Cannot store nationality ("Australian") | Closed whitelist of 23 predicates in `schemas.py:270` (`FACT_PREDICATES`) omits nationality; `lives_in` was the only available approximation. | Core Schemas |
| 4 | Blocked from math after web search | `SequenceGuard` in `policy.py:222` treats all `run_python` as `Risk.WRITE` and unconditionally bans it in turns that used `search_web`/`fetch_url`. | Sandbox Security |
| 5 | Confirmation Paradox | `service.py:128` checks `SequenceGuard` before checking if the user already gave explicit voice confirmation (`confirmed=True`). | Sandbox Service |
| 6 | Timezone blindness & wrong guesses | `system_tools.py:159` generates naive local time without UTC offset or timezone identifiers. | System Telemetry |
| 7 | "No verified record of what I last told you" | Conversational references ("what did I last tell you") are misrouted toward long-term SQLite memory. **Attribution caveat:** the cited `heuristic.py:240` `mem_pattern` does not literally match that utterance; the exact failing phrasing must be reproduced in a test first so the pre-filter lands at the layer that actually misroutes (heuristic router vs. epistemic cascade). | Router / Cascade |
| 8 | Interrupted for saying "run the numbers" | `coherence.py:388` (`detect_promised_action_claims`) matches "run" as an unexecuted tool promise, forcing a false apology. | Coherence Guard |
| 9 | `tts_queue_full_sentinel_failed` | `orchestrator.py:280` bounds `_tts_queue` to 8 items; GPU token generation easily outpaces CPU Kokoro synthesis on long turns. | Audio Pipeline |
| 10 | **(Latent, CRITICAL)** Phase 4's naive fix opens a TM-03 exfiltration bypass | The `confirmed` parameter is overloaded: the EpistemicSearchCascade self-confirms its own internal dispatches (`cascade.py:856`, `cascade.py:878`, `cascade.py:1104`). Letting `confirmed=True` override `SequenceGuard` lets cascade `read_file` → `fetch_url` sequences bypass the exfiltration sequence ban. | Sandbox Security / Cascade |
| 11 | **(Latent, HIGH)** Negation & reported-speech blindness in passive extraction | `_extract_passive_facts` (`orchestrator.py:1044`) filters interrogatives and hypotheticals but not negations or attribution. "My name is not Sean" extracts `is_named: "not"`; "He said my name is Sean" commits quoted speech as user fact. Quote-grounding passes both because the user literally said the words. | Memory / Extraction |
| 12 | **(Latent, HIGH)** Phase 1 fallback creates a second uncoordinated NPU client | `LocalEmbeddingPort()` (`embed.py:148`) constructs an in-process `EmbedWorker` that probes `device="NPU"` and compiles an OpenVINO graph in the supervisor process, contending with the `lucca-npu` child (Kokoro/VAD/ASR) and stalling boot on first NPU compile. | Senses / Embedding |
| 13 | **(Latent, MEDIUM)** Open predicates fragment supersession | Supersession is keyed on predicate string (`orchestrator.py:1032`). Open vocabulary drifts (`nationality_is` vs `nationality` vs `is_australian`), producing parallel divergent facts that never supersede and surface as contradictions in retrieval. | Memory / Schema |
| 14 | **(Latent, MEDIUM)** Per-commit `ThreadPoolExecutor` churn + inline embedding latency | Every commit spawns a fresh single-use thread pool (`orchestrator.py:944, 1017, 1098, 1139, 1237, 1432, 2652`). Dormant today; once Phase 1 wires memory live, every turn finalization pays thread-spawn × ~5 commit sites + embedding + WAL write, blocking the turn loop. | Memory / Performance |
| 15 | **(Latent, LOW)** TTS overflow policy is silent-drop + premature EOS | Full queue silently drops chunks (`orchestrator.py:2093, 2114` — audible mid-sentence gaps); sentinel-put failure at `2123–2126` falls through to `FLAG_EOS` at `2128` while the worker still has backlog (tail truncation). Queue depth alone preserves both failure modes. | Audio Pipeline |

---

## 2. Phase-by-Phase Remediation Plan

### Phase 1: Runtime Memory Subsystem Wiring (Critical Foundation)

**Changes Required:**

`src/lucca/core/orchestrator.py` — Provide automated fallback defaults in `Orchestrator.__init__` so standalone instances and production supervisor processes always have live memory handles:

```python
# Fallback database and memory store initialization
if db is not None:
    self.db = db
else:
    from lucca.memory.db import DatabaseManager
    db_path = self.config.home_dir / "data" / "memory.sqlite"
    self.db = DatabaseManager(db_path=db_path)
if memory_store is not None:
    self.memory_store = memory_store
else:
    from lucca.memory.store import MemoryStore
    from lucca.senses.embed import LocalEmbeddingPort
    key = (
        master_key
        or getattr(self.config, "master_key", None)
        or b"01234567890123456789012345678901"
    )
    self.memory_store = MemoryStore(
        db=self.db,
        master_key=key,
        embedding_port=LocalEmbeddingPort(),
    )
```

`src/lucca/main.py` — Explicitly construct `DatabaseManager` and `MemoryStore` in `main.py` before spawning `Orchestrator(db=db, memory_store=memory_store)`.

**Amendments from review (rows 12, 14 + key hygiene):**

1. **CPU-forced fallback embedder (row 12).** The supervisor-process fallback embedder must be constructed with an explicit CPU device (e.g. `LocalEmbeddingPort(worker=EmbedWorker(device="CPU"))` or an equivalent constructor override). 384-D MiniLM on the Core Ultra 9 275HX is ~10–20 ms — irrelevant at commit frequency — and this avoids duplicate model memory, uncoordinated NPU queue contention with the `lucca-npu` child, and the first-run OpenVINO NPU compile stall during boot. The NPU remains the embedding device inside the `lucca-npu` worker process only.
2. **No silent hardcoded key.** The `b"0123456789..."` dev key is consistent with existing internal fallbacks but must not ship silently in the production boot path. Load from config/keystore; if unavailable, emit a `FATAL`-grade boot warning (stderr + boot banner) before proceeding with the dev key.
3. **Persistent commit executor (row 14).** Replace the per-commit `with ThreadPoolExecutor(max_workers=1)` blocks (7 sites) with a single persistent single-worker executor (or a commit queue drained by a dedicated `core-mem` thread) created in `__init__` alongside the TTS worker, and shut it down in `stop()`.

**Verify:** Confirm that `_commit_transcript`, `_commit_assistant_utterance`, and `_commit_action_receipts` write rows into `C:\ProjectLucca\data\memory.sqlite` with valid HMAC-SHA256 signatures on every turn, and that turn-finalization latency does not regress by more than 50 ms p95.

### Phase 2: Solution B — Open-Predicate Knowledge Graph

**Changes Required:**

`src/lucca/core/schemas.py`:
- Deprecate the rigid 23-item `FACT_PREDICATES` frozenset restriction.
- Introduce a predicate syntax validator (2-char minimum is intentional; document it):

```python
PREDICATE_SLUG_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

def is_valid_predicate(p: str) -> bool:
    """Validates predicate format (lowercase snake_case identifier, 2–41 chars)."""
    return bool(PREDICATE_SLUG_REGEX.match(p.strip()))
```

`src/lucca/memory/gate.py` & `src/lucca/memory/extraction.py`:
- Update `check_fact_grounding`: replace `fact.p not in PREDICATES` with `not is_valid_predicate(fact.p)`.
- **Preserve the Core Security Invariant:** retain strict verbatim quote grounding: `quote ⊆ transcript_NFC ∧ (s,o ∈ quote ∨ fuzzy ≥ 90)`. Facts cannot enter memory unless the user literally spoke the words in that turn, signed with `USER_DERIVED`.

`src/lucca/core/capabilities.py`:
- Update the `memory_commit` tool prompt description to inform the model that it can use natural descriptive predicates (e.g. `nationality_is`, `diet_is`, `has_skill`, `lives_in`).
- **Prompt the model with the user's existing in-memory predicates** so it reuses them (see amendment 3 below).

Passive Fact Extraction (`orchestrator.py:176–200`) — expand `_PASSIVE_FACT_PATTERNS` with a **closed demonym lexicon** (not a loose regex):

```python
# ~200-entry closed set of nationality adjectives (demonyms), e.g.:
_DEMONYMS: Final[frozenset[str]] = frozenset({"australian", "american", "british", ...})

# nationality_is fires only when the captured token is in _DEMONYMS:
(
    "nationality_is",
    re.compile(r"\b(?:i am|i'm)\s+([a-z][a-z\-']{2,30})\b", re.IGNORECASE),
),  # post-filter: m.group(1).lower() in _DEMONYMS
(
    "origin_is",
    re.compile(r"\b(?:i'm from|i am from|originally from)\s+([A-Za-z\s\-']{2,40}?)(?:[.,!?;]|$)", re.IGNORECASE),
)
```

**Amendments from review (rows 11, 13 + ADR hygiene):**

1. **ADR-010 supersession (mandatory).** The comment at `schemas.py:265–269` states the closed vocabulary is "deliberately NOT config-editable — widening this set changes what can be laundered into long-term memory" (WO-9 A2 / ADR-010). Solution B is defensible because the real security boundary is quote-grounding, but a new ADR must be ratified in `luccadocs/DECISIONS.md` formally superseding ADR-010's closed-vocabulary clause and restating the invariant as: *predicate vocabulary is open; grounding (verbatim quote + USER_DERIVED signature) is the laundering boundary.* Without this, `tests/test_static_gates.py` and future audits will flag the drift.
2. **Negation & reported-speech guards (row 11).** Extend the skip logic alongside `_HYPOTHETICAL_MARKERS` with:
   - a negation window check: `not|n't|never|no longer` appearing between the trigger phrase and the capture group voids the candidate (fixes "My name is not Sean" → `is_named: "not"`);
   - reported-speech markers: `he said|she told|they said|my friend said|quote` void the candidate (fixes attribution blindness).
   These guards apply to all passive patterns, existing and new.
3. **Predicate canonicalization (row 13).** Add a synonym → canonical-slug map at the gate (e.g. `nationality` → `nationality_is`, `resides_in` → `lives_in`) so supersession keeps working under an open vocabulary; the `memory_commit` tool description must list predicates already present in the user's memory to bias the model toward reuse.
4. **Stale error copy.** Update the `memory_commit` validation error at `orchestrator.py:2550` ("p (closed predicate)") to describe the slug format instead.

### Phase 3: Frictionless Memory Commits & Resilient Voice Confirmation

**Changes Required (amended classification approach):**

`src/lucca/sandbox/policy.py` — **Do not** reclassify `memory_commit` as `Risk.READ` (READ tools escape `UNTRUSTED_WEB` taint escalation entirely, letting a web-tainted turn commit memory with no confirmation). Instead, follow the existing `note_write` precedent in `requires_confirmation()`:

```python
def requires_confirmation(tool_name: str, taint: TaintFlags = TaintFlags.CLEAN) -> bool:
    risk = classify_risk(tool_name)
    if tool_name == "note_write":
        return bool(taint & TaintFlags.UNTRUSTED_WEB)
    if tool_name == "memory_commit":
        # Saving a personal fact the user just spoke is quote-grounded and
        # provenance-signed; never halt the conversation for it unless the
        # turn is web-tainted.
        return bool(taint & TaintFlags.UNTRUSTED_WEB)
    if taint & TaintFlags.UNTRUSTED_WEB:
        if risk in (Risk.WRITE, Risk.LAUNCH, Risk.NETWORK):
            return True
    return risk in (Risk.WRITE, Risk.LAUNCH)
```

Update the docstring at `policy.py:145–149`, which currently documents the deliberate non-exemption.

`src/lucca/sandbox/policy.py:21–24` (Fuzzy Confirmation Matching) — upgrade `parse_confirmation_response` with rapid token-set matching:

```python
CONFIRM_TOKENS = frozenset({"yes", "yeah", "yep", "confirm", "sure", "proceed", "ok", "okay", "do it", "go ahead"})
CANCEL_TOKENS = frozenset({"no", "nope", "cancel", "stop", "abort", "nevermind", "dont", "don't"})
```

Strip leading punctuation and hesitation markers ("uh", "um"), then perform token-overlap matching so natural speech ("yeah, please do", "confirm that") parses reliably as confirm. Fail-closed (`unknown` → cancel) semantics are preserved for genuinely unrecognized input.

**Amendment — confirmation binding:** `ConfirmationTokenManager` (`policy.py:68`, HMAC token binding per Milestone 2 §2.7) currently has zero call sites; live confirmation is regex-on-transcript only, so a "yes" confirms whatever happens to be pending with no binding to the specific tool/args. Either (a) wire token binding into the voice confirmation flow, or (b) ratify the divergence in the same ADR amendment as Phase 2. Decision required before Phase 3 sign-off.

### Phase 4: Arithmetic Tool Separation & SequenceGuard Fix

**Changes Required:**

Dedicated Arithmetic Tool (`calc_math`) in `src/lucca/core/capabilities.py`:

```python
"calc_math": ToolSchema(
    name="calc_math",
    description="Safely evaluate mathematical expressions and arithmetic (e.g. '1982 - 1917', '53 * 72 / 4', 'abs(a - b)').",
    parameters={
        "expr": ToolParameter(type="string", description="Mathematical expression to evaluate", required=True),
    },
    risk=Risk.READ,
    target="self",
)
```

Execution Handler (`service.py`) — evaluate expressions using Python's `ast` module (standard arithmetic operators, `math` constants and functions; no filesystem/network/name resolution beyond the allowlist).

Allow `calc_math` in `SequenceGuard` (`policy.py:222–229`) — because `calc_math` is `Risk.READ`, it bypasses the sequence guard. Multi-step workflows (`search_web` → `fetch_url` → `calc_math`) execute cleanly in a single turn.

**Resolve the Confirmation Paradox (`service.py:127–138`) — AMENDED (row 10, CRITICAL):**

The v1 fix (`if not allowed and not confirmed`) is **rejected**: the `confirmed` flag is overloaded — the EpistemicSearchCascade self-confirms its own internal dispatches (`cascade.py:856, 878, 1104`), so a blanket override would let cascade-internal `read_file` → `fetch_url` sequences bypass the TM-03 exfiltration ban.

Instead, split the confirmation provenance:

```python
# service.py
def execute_tool(
    self,
    call_id: str,
    tool_name: str,
    args: dict[str, JsonValue],
    confirmed: bool = False,
    human_confirmed: bool = False,   # NEW: only set from the PTT/text voice-confirmation path
) -> ToolResult:
    allowed, reason = self.guard.check_and_record(tool_name)
    if not allowed:
        # A human voice grant may override the single-turn *sequence* block only.
        # The exfiltration token check (policy.py:232-243) is NEVER overridable.
        if not (human_confirmed and self.guard.is_sequence_block(reason)):
            return ToolResult(ok=False, exit_code=-2, stderr=reason, ...)
```

- `human_confirmed=True` is set exclusively by the orchestrator's voice/text confirmation path after `parse_confirmation_response` returns `"confirm"`.
- Cascade and other internal callers continue passing `confirmed=True` (which satisfies the confirmation check at step 2 but never overrides the guard).
- `SequenceGuard` gains a reason classifier (or returns a structured block code) so only sequence blocks — not egress blocks — are human-overridable.

### Phase 5: Timezone-Aware Telemetry & Temporal Grounding

**Changes Required:**

`src/lucca/sandbox/system_tools.py:158–167` — update `get_system_metrics()` to emit timezone-aware metadata:

```python
now_local = datetime.now().astimezone()
metrics: dict[str, JsonValue] = {
    "timestamp": now_local.isoformat(),
    "utc_offset": now_local.strftime("%z"),              # e.g. "+0800"
    "utc_offset_hours": round(now_local.utcoffset().total_seconds() / 3600.0, 1),
    "timezone_name": time.tzname[time.daylight],          # e.g. "AWST" or "W. Australia Standard Time"
    ...
}
```

**Amendment:** exclude `timestamp` (and the new tz fields) from the 1-second `_SYS_METRICS_CACHE` fast path (`system_tools.py:144`) — recompute the time fields on every call even when hardware metrics are served from cache, so temporal grounding is never stale.

**Result:** Lucca directly observes `+0800` in her telemetry rather than guessing her location from ambiguous naive timestamps.

### Phase 6: Router Conversational Context Separation

**Changes Required:**

`src/lucca/router/heuristic.py:240–245` — add a pre-filter before `memory_query` to identify conversational references:

```python
RECENT_CONTEXT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(what did (?:i|you) (?:just|last) (?:say|tell|ask|do)|repeat (?:that|what)|what was that)\b",
    re.IGNORECASE,
)
```

If `RECENT_CONTEXT_PATTERN.search(text)` matches:
- Classify as `chit_chat` or a new `context_query` intent with `ExecutionTier.FULL_LOOP`.
- Bar routing to Substrate 2 (Epistemic Memory Cascade).
- Answer directly from in-memory dialogue history (`self.history[-2:]`).

**Amendment (row 7 attribution caveat):** before placing the pre-filter, add a failing test that reproduces the exact live-test utterance(s) end-to-end. The cited `mem_pattern` at `heuristic.py:240` does not literally match "what did I last tell you" — the misroute may originate in the epistemic cascade rather than the heuristic router. The pre-filter must land at the layer the test proves responsible; if both layers can misroute, guard both.

### Phase 7: Coherence & Audio Stability Refinements

**Changes Required:**

`src/lucca/core/coherence.py:94–122` — add analytical idioms to `EXCLUDED_IDIOMS`:

```python
EXCLUDED_IDIOMS: tuple[str, ...] = (
    ...,
    "run the numbers",
    "run the math",
    "run through that",
    "run a check",
)
```

`src/lucca/core/orchestrator.py:280` — increase TTS queue depth from 8 to 32:

```python
self._tts_queue: queue.Queue[...] = queue.Queue(maxsize=32)
```

**Amendments (row 15):**

1. **Sentinel failure must not truncate.** When the done-sentinel `put` at `orchestrator.py:2123` fails, drain-and-retry (or block with a longer timeout) before falling through; never set `FLAG_EOS` (`orchestrator.py:2128`) while the worker backlog still contains unsynthesized chunks.
2. **Drop-oldest, not drop-new.** On chunk overflow (`orchestrator.py:2093, 2114`), evict the oldest queued chunk so the *current* sentence completes, and emit a `tts_queue_overflow` telemetry event (not just a log line) so the HUD can surface degraded audio.

---

## 3. ADR & Documentation Amendments Required

| Amendment | File | Rationale |
|-----------|------|-----------|
| New ADR superseding ADR-010's closed-vocabulary clause; restates the laundering boundary as quote-grounding + `USER_DERIVED` signature under an open predicate vocabulary | `luccadocs/DECISIONS.md` | Phase 2 changes what can enter long-term memory; the invariant must be re-ratified, not just re-coded |
| Confirmation binding decision: wire `ConfirmationTokenManager` into the voice flow OR ratify regex-only confirmation | `luccadocs/DECISIONS.md` | `policy.py:68` is currently dead code; the live flow diverges from Milestone 2 §2.7 |
| `human_confirmed` provenance split (Phase 4) documented as a TM-03 refinement | `luccadocs/DECISIONS.md` + `luccadocs/ARCHITECTURE.md` | Prevents future regressions where internal auto-confirm is mistaken for a human grant |

## 4. Codebase Invariant & Static Gate Verification

Every proposed modification was cross-referenced against the repository's active static gates:

- **Zero-Any Invariant (`tests/test_static_gates.py`):** All new arguments, schemas, and return types must use strict Pydantic models or `JsonValue` / primitives. No `typing.Any` introduced in core, brain, reasoning, or sandbox. This applies to the new `human_confirmed` parameter, the `calc_math` handler, and the predicate validator.
- **Grounding-Eligible Provenance (`tests/test_grounded_memory_commit.py`):** Solution B preserves `check_fact_grounding()`: the user quote must remain a verbatim substring of the transcript signed with `USER_DERIVED`. Opening the predicate vocabulary does not bypass quote verification.
- **Parity Tests (`test_orchestrator_parity.py`):** Changes in `Orchestrator` must apply identically across both voice and text turn pipelines — in particular the `human_confirmed` flag must be settable from both the PTT voice path (`orchestrator.py:2739`) and the text confirmation path (`orchestrator.py:836`).
- **Hardware Budget:** The Phase 1 CPU-forced embedder keeps the NPU exclusively owned by the `lucca-npu` worker; no new dGPU or NPU residents are introduced. WSL2/RAM clamps are untouched.

## 5. Verification & Testing Matrix

| Subsystem | Test Command | Verification Target |
|-----------|--------------|---------------------|
| Memory Wiring | `pytest tests/test_a1_runtime_wiring.py tests/test_memory_db.py` | `memory.sqlite` tables populate live during turn finalization; finalize latency ≤ +50 ms p95; embedder device is CPU in supervisor process. *(Note: `test_a1_runtime_wiring.py` is net-new — budget for writing it.)* |
| Open Predicates | `pytest tests/test_grounded_memory_commit.py` | `nationality_is` commits successfully with verbatim quote grounding; "My name is not Sean" and "He said my name is Sean" produce **zero** facts; predicate canonicalization maps synonyms to canonical slugs. |
| Math & SequenceGuard | `pytest tests/test_tool_chaining.py tests/test_sandbox.py` | `search_web` → `calc_math` passes; cascade-internal `read_file` → `fetch_url` remains **blocked** even with `confirmed=True`; human voice confirmation overrides sequence block but never egress block. *(Note: `test_tool_chaining.py` is net-new.)* |
| Telemetry & Timezone | `pytest tests/test_t2_native_tools.py` | `self_metrics` returns `utc_offset`, `utc_offset_hours`, `timezone_name`; timestamp is fresh on every call (not served from the 1 s cache). |
| Router Context | `pytest tests/test_router.py` | The exact reproduced live-test utterance classifies as `context_query`/`chit_chat` and never reaches Substrate 2. |
| Audio Stability | `pytest tests/test_output_supervisor.py` + HW soak | 32-deep queue; sentinel failure never sets `FLAG_EOS` with backlog; overflow emits `tts_queue_overflow` event. |
| Static Gates | `pytest tests/test_static_gates.py` | 0 `Any` violations across all modified files. |
| Full Regression | `pytest` | 100% green pass on the full non-HW suite (653+ tests). |

## 6. Implementation Order & Dependencies

1. **Phase 1** (foundation — everything else is moot while memory is `None`), including the CPU embedder, key warning, and persistent executor amendments.
2. **Phase 4** (security-critical: the `human_confirmed` split must land *with or before* any guard-override behavior).
3. **Phase 3** (depends on Phase 4's confirmation provenance split).
4. **Phase 2** (ADR amendment first, then code; includes negation/attribution guards and canonicalization).
5. **Phases 5, 6, 7** (independent; can parallelize after Phase 1).

---

## 7. Execution Verification & Sign-off Certificate

**Execution Date:** 2026-09-24  
**Full Non-HW Suite:** 671 passed, 49 deselected  
**Ruff Cleanliness:** 0 lint errors across `src/` and `tests/`  

| Phase | Subsystem | Test Targets | Result |
|---|---|---|:---:|
| **1** | Memory wiring / CPU embedder / executor | `test_a1_runtime_wiring`, `test_memory_db` | ✅ 24/24 |
| **2** | Open-predicate KG (Solution B) | `test_grounded_memory_commit`, `test_grounding` | ✅ 27/27 |
| **3** | Frictionless commits / voice confirmation | `test_confirmation`, `test_t2_native_tools` | ✅ 16/16 |
| **4** | `calc_math` / SequenceGuard / `human_confirmed` | `test_sandbox`, `test_tool_chaining`, `test_capabilities` | ✅ 50/50 |
| **5** | Timezone telemetry | `test_t2_native_tools` | ✅ 6/6 |
| **6** | Context misrouting | `test_router`, `test_epistemic_cascade` | ✅ 36/36 |
| **7** | Coherence idioms / TTS queue | `test_output_supervisor` | ✅ 25/25 |
| **Static** | Zero-`Any` Invariant | `test_static_gates` | ✅ 12/12 |

