# Project Lucca — Studio Capability Roadmap & Seed Content Specification

**Status:** Proposed (Zoo) — doctrine, taxonomy, S1, L1a ratified by reviewer; T1 ratified conditional on fixes 1 & 4 (applied in v1.1.1); category design adopted (v1.1.2); L1b unblocked by the §4.2 expressibility table
**Version:** 1.1.2 (supersedes 1.1.1; adopts the reviewer's frozen-prefix + category-suffix design, retires `format_skill_tools`)
**Date:** 2026-09-21
**Author:** Zoo (Fable 5.1)
**Evidence base:** `docs/research/studio_roadmap_r2/` (T0 citation audit, Q1–Q7 tracks, SYNTHESIS.md); 7 verified preprints read in full; code evidence from `src/lucca/core/schemas.py`, `src/lucca/reasoning/scheme/prims.py`, `src/lucca/core/orchestrator.py`, `src/lucca/brain/prompt_builder.py`
**Depends on:** D-BRAIN-05 v2 (Gemma-4 primary, ratified), config-driven brain selection, first authored rule in QUARANTINE (`calc-open-with-expr-v1`, shadow telemetry live)

---

## 0. Changelog

### v1.1.1 → v1.1.2 (reviewer category design, adopted)

1. **T1 re-architected as frozen prefix + category suffix:** the ≤18 native tools (now including `invoke_skill`) and a static 7-category menu form the byte-stable prefix; the chosen category's invokable-skill manifest is injected per turn at the frontier-user-message tail via the existing Prompt Frontier Suffix mechanism (verified at [`prompt_builder.py:811`](../src/lucca/brain/prompt_builder.py): "Appended exclusively at the tail of the frontier user message, preserving 100% prefix KV cache"). Category selection is deterministic (router intent + entities → category, no LLM call) with a rate-limited, logged LLM fallback.
2. **`format_skill_tools` retired:** the D-REAS-04 Proposal A mechanism ([`prompt_builder.py:753`](../src/lucca/brain/prompt_builder.py)) exposed every ACTIVE rule as a native `skill_<id>` tool in the `tools=` payload — an unbounded flat catalog in the cache-critical prefix, exactly the BFCL failure mode. Replaced by the single native `invoke_skill(skill_id, args)` dispatch tool + per-turn category manifest in the suffix. Deterministic rules fire from `:when` against `RuleState` and never enter the prompt.
3. **Categories in `meta_info.json`:** ≤2 per skill from the 7-category menu (4 packs + 3 tool targets); induced rules assigned categories from plan tool classes, confirmed at promotion.
4. **30-cap clarified:** it governs the rule library (per-turn matching cost + `:when`-collision risk), not LLM exposure. It stands at ship; revisited at L5 review with collision-rate and matching-latency telemetry rather than raised on argument.
5. **L5 pulled forward and re-scoped:** the deterministic category mechanism delivers Decision-1 Option B without neural infrastructure; NPU-embedding within-category ranking becomes a post-C1 refinement.
6. **New metrics:** shortlist recall (correct skill in the injected manifest) with Wilson 95% lower bound ≥ 0.90; T1 cache test now spans ≥3 categories; hallucinated-`skill_id` rejection tested.

### v1.1.0 → v1.1.1 (reviewer items 1–8)

1. **T1 contradiction resolved (item 1):** the per-turn shortlist is gone. Factory registry is capped at **≤18 tools total** (18 in v1.0.0 after WO-9 A13/A14), frozen in one alphabetically-sorted schema block, byte-stable across turns; it changes only on explicit Studio edit (rare; cache miss accepted). Per-turn dynamic shortlisting is deferred to rung L5. Tool list trimmed accordingly: `sys_resources`/`sys_specs`/`sys_processes` merged into one `sys_info` tool with an `op` parameter; `schedule_event`, `artifact_verify`, `screenshot_capture` deferred.
2. **Expressibility table added (item 2, §4.3):** built from code, not recon. `RuleState` carries `last_tool` (name) and `last_tool_ok` (bool) — **never the result payload** ([`schemas.py:286-299`](../src/lucca/core/schemas.py)). `say` takes a static string; there is no string-interpolation primitive ([`prims.py:387-393`](../src/lucca/reasoning/scheme/prims.py)). Rules therefore never consume tool results; result narration is the LLM's job in ACT_THEN_NARRATE via `build_narration_messages` ([`orchestrator.py:1454`](../src/lucca/core/orchestrator.py), [`prompt_builder.py:828`](../src/lucca/brain/prompt_builder.py)). All 16 factory skills tagged; `late-night-brevity` and `induction-watch` reclassified out of the skill system; `artifact-check` deferred with its tool.
3. **L1 acceptance strengthened (item 3):** static validation + Z3 (SAT and contingent) + ≥2 golden traces per skill required before ACTIVE.
4. **Class B provenance fixed (item 4):** `sys_info` output stamped `TOOL_CONTENT_UNTRUSTED` — process names and command lines are attacker-controlled.
5. **Statistics fixed (item 5):** C1 acceptance restated as Wilson 95% lower bound ≥ 0.80 at N≥100 (45/50 has a Wilson interval of roughly 79–96%, so "≥90% on 50 turns" was not a testable criterion). S1 contract now states explicitly that `tool_exit_zero`/`pydantic_valid` measure *execution success* ("didn't crash"), not *task success* ("it helped").
6. **C2 cache test added (item 6):** turn-alternation sequence asserting no-think TTFT stays ≤350 ms after a thinking turn.
7. **Separate budgets stated (item 7, §3):** the 30-skill cap (rule-engine matching) and the 18-tool cap (LLM prompt catalog) are independent; skills never consume prompt-catalog slots.
8. **Pel/LLM+AL graded honestly with passages (item 8, §10):** Pel → "directly supports the principle, E3 evidence"; LLM+AL → "directly supports, E2". EvoSkill-GUI Table 5 independently spot-checked by the author against the local PDF.

### v1.0.0 → v1.1.0 (T0 audit, Q1–Q7 synthesis, external critique, 4 owner decisions)

Citation errata (6 IDs, 2 attributions, ghost purge); new rung S1 (typed Proposal/Decision/Outcome); C1 restricted to non-parametric Recall (XConf 27B cliff; Bonsai ternary caveat) with gated optional C1b; T1 frozen-schema redesign; L1 hard cap 30 ACTIVE + `_retired/`; Rule of Three correction (5 clusters ⇒ ≤60% failure bound; clusters prove intent recurrence, not safety); L2 replay-before-shadow + contrastive logging + McNemar/Wilson statistics; L3 plain-English diffs + induced-rule acceptance test; T4 auto-demote circuit breaker (>10% failure over 10-turn window); T3 gates at dispatcher layer; L4 macro bounds + intermediate validation; confabulation claims with Clopper-Pearson intervals and N≥100 requirement; whitelist two-commit history; explicit deferrals (lobes, NLI validator, L5 shortlisting, open-mic VAD); rhetoric stripped (affect = inspectable behavioral-state machine, no claim of felt experience).

---

## 1. Purpose & Design Doctrine

LISP Studio and Tool Studio are the authoring environments for Lucca's procedural mind: Tool Studio manages her *body* (the tools she can invoke), LISP Studio manages her *habits* (the reasoning pathways that turn perception into action).

**Doctrine (owner-ratified, 2026-09-21):**

1. **Lucca never operates the user's desktop.** No `launch_app` on the host, no window management, no voice launcher.
2. **Class A (her body) is the default population.** Tools acting only on her sandbox need no confirmation gates.
3. **Class B is read-only host perception.** She may *look* at the machine but never mutate it.
4. **Class C is the shared sensory band.** The only surfaces where the user's world and Lucca's world touch, and the only surfaces requiring deontic gates.
5. **Factory Lucca ships competent.** A starter library of authored skills (ACTIVE, unit-tested) plus a full native tool belt. Organic induction (QUARANTINE → shadow → promotion) adds *personalization*, not basic competence.
6. **Nothing is asserted without a traceable cause.** Every memory commit carries a cryptographic provenance envelope (ADR-006); every experience-bank outcome is grounded in an external signal (tool exit code, Pydantic validation, explicit operator feedback) — never LLM self-judgment (XConf §C: self-labeled banks inflate confidence +0.13 to +0.25 on exactly the confidently-wrong episodes the bank exists to catch).

---

## 2. Tool Taxonomy

Every tool carries a `target` field in its schema: `self | host_readonly | shared`.

### 2.1 Class A — Her Body (`target: self`)

Acts only on Lucca's sandbox and her own substrate. Ships enabled. No confirmation. Output stamped `TOOL_VERIFIED` (contents originate inside her sandbox).

| Tool | Status | Description |
|---|---|---|
| `run_python` | ⚠️ sandbox-only today | Exists in the sandbox RPC layer ([`rpc.py:704`](../src/lucca/sandbox/rpc.py), [`file_tool.py:292`](../src/lucca/sandbox/file_tool.py)) but **not in the LLM-facing registry** — T1 exposes it. **Docker-gated:** returns `policy_violation` on the non-Docker path. Deterministic computation — the anti-guessing calculator. **Scope limit:** a contained Class A tool only (CodeAct contradiction resolution, SYNTHESIS §3.1); never the planning substrate. |
| `read_file` / `write_file` | ✅ in registry | Workspace file ops. |
| `list_dir` / `search_text` | ⚠️ sandbox-only today | Exist in the sandbox RPC layer ([`rpc.py:630-703`](../src/lucca/sandbox/rpc.py)) but **not in the LLM-facing registry** — T1 exposes them. |
| `fetch_url` / `search_web` | ✅ in registry | Sandboxed egress senses. **Note:** response bodies are external content → stamped `TOOL_CONTENT_UNTRUSTED` (pre-existing behavior, unchanged). |
| `memory_search` / `memory_commit` | 🆕 NEW | Provenance-gated recall as explicit, inspectable tools. |
| `note_write` / `note_read` | 🆕 NEW | Scratchpad, distinct from user-facing workspace. |
| `self_metrics` | 🆕 NEW | Her own latency / VRAM / gas usage / tool success rates. |
| `invoke_skill` | 🆕 NEW | Single native dispatch for deliberately-invokable skills (`skill_id`, `args`). The per-turn category manifest in the suffix tells the model what is available; dispatched plan actions inherit their own class gates at the dispatcher. Replaces per-skill native tool definitions (see §2.4). |
| ~~`schedule_event`~~ | ⏸ deferred | Her sense of time. Deferred to keep the factory registry ≤18. |
| ~~`artifact_verify`~~ | ⏸ deferred | SHA256 + manifest check. Deferred with the `artifact-check` skill. |

**Latency contract:** Class A tools < 50 ms (local) / < 2,000 ms (network). Synchronous tools exceeding 500 ms must be preceded by a `D-BRAIN-03` verbal thinking cue so the voice loop never goes silent (F-Q5-4).

**Count: 13 Class A tools at factory (including `invoke_skill`).**

### 2.2 Class B — Read-Only Host Perception (`target: host_readonly`)

| Tool | Status | Description |
|---|---|---|
| `query_capabilities` | ✅ in registry ([`capabilities.py:244-267`](../src/lucca/core/capabilities.py)) | The live Class B tool today: hardware telemetry via `system_tools.get_system_metrics()` plus tool/rule/app listings. **v1.1.0–v1.1.2 omitted it from the taxonomy by error.** T1 classifies it `host_readonly`. |
| `sys_info` | 🆕 T2 (supersedes `query_capabilities`' hardware category; `sys_resources` never existed under that name) | Single tool, `op: resources \| specs \| processes`. When `sys_info` ships, `query_capabilities` narrows to the capability manifest only. |

**Policy (corrected per reviewer item 4):** output stamped **`TOOL_CONTENT_UNTRUSTED`** — process names, command lines, and driver strings are attacker-controlled host text, and must never become memory-eligible without explicit user action. No confirmation gate (nothing mutable); read-only enforced at the tool layer. Latency < 500 ms.

**Count: 1 Class B tool at T1 gate (`query_capabilities`); `sys_info` arrives with T2.**

### 2.3 Class C — Shared Sensory Boundary (`target: shared`)

| Tool | Status | Description |
|---|---|---|
| `clipboard_read` | 🆕 NEW | She reads what the user copied, to reason about it. |
| `inbox_handoff` | 🆕 deferred (**v1.1.0–v1.1.2 wrongly marked this "exists"** — only `WorkspaceManager.import_from_inbox()` at [`workspace.py:80`](../src/lucca/sandbox/workspace.py) exists, a Python method, not a tool) | File drop-in for her workspace. Ships with T3 alongside `clipboard_read`. |
| ~~`screenshot_capture`~~ | ⏸ deferred | Screen perception. Deferred to the vision-lobe trigger (§8). |

**Enforcement:** deontic confirmation enforced **at the tool dispatcher layer** (`capabilities.py`), never as a prompt instruction — LLMs treat negative prompt rules as obstacles to circumvent (F-Q7-1/F-Q7-3). Any memory commit derived from Class C context is stamped `TOOL_CONTENT_UNTRUSTED` (ADR-006).

**Count: 0 Class C tools at T1 gate; 2 after T3. Registry at T1 gate: 9 tools** (`read_file`, `write_file`, `search_web`, `fetch_url`, `query_capabilities`, `list_dir`, `search_text`, `run_python`, `invoke_skill`). **Full factory after T2+T3+WO-9: 18** (at cap; further native tools require retirement or the L5 refinement).

### 2.4 T1 Schema Presentation — Frozen Prefix + Category Suffix (reviewer design, adopted)

The prompt has two parts with different stability contracts:

- **Frozen prefix (byte-stable across turns):** system prompt + the ≤18 native tools in `tools=` (13 Class A incl. `invoke_skill` + 1 Class B + 2 Class C) + a **static category menu** (7 categories: the four skill packs + the three tool targets). Changes only on explicit Studio edit; the resulting single cache miss is accepted.
- **Variable suffix (per-turn, cache-safe):** the chosen category's invokable-skill manifest (skill_id + one-line description + arg summary) injected at the **tail of the frontier user message** via the existing Prompt Frontier Suffix mechanism ([`prompt_builder.py:811`](../src/lucca/brain/prompt_builder.py) — "Appended exclusively at the tail of the frontier user message, preserving 100% prefix KV cache"), composing with the stance tag. Because the suffix sits after all static content, the prefix cache survives category changes.

**Category selection (deterministic first):** the heuristic router's existing intent class + entities map to a category with no LLM call (microseconds). **LLM fallback:** if no deterministic mapping fires, the model may request a category from the static menu, limited to 1 request per turn; every fallback is logged to `failure_examples/` for the induction pipeline.

**Skill-as-tool exposure is the exception, not the rule.** Deterministic rules fire from `:when` conditions against `RuleState` and never enter the prompt (the rule engine evaluates outside the LLM). Only skills the LLM should invoke *deliberately* are exposed — via the single native `invoke_skill(skill_id, args)` dispatch tool in the frozen prefix, with the per-turn category manifest in the suffix naming the valid `skill_id`s. A `skill_id` not in the current manifest is rejected at the dispatcher (negative-tested).

**Retired mechanism:** `format_skill_tools` ([`prompt_builder.py:753`](../src/lucca/brain/prompt_builder.py), D-REAS-04 Proposal A) exposed every ACTIVE rule as a native `skill_<id>` tool in `tools=` — an unbounded flat catalog in the cache-critical prefix, exactly the BFCL >16–20 failure mode. It is replaced by `invoke_skill` + the category manifest.

### 2.5 Whitelist History (documented per critique)

`config/tool_whitelist.toml` was truncated from 5 apps to 2 in commit `0ef309d` — not a design decision but **test pollution**: `tests/test_sandbox.py` serialized to the real config file. H3 restored the audited 5-app suite from `2eaa58d` and added `tests/test_tool_whitelist.py` as the regression test. Under the no-host-desktop doctrine (§1), the file becomes **vestigial after T1** — retained for rollback only. Restoring it was correct regardless: the alternative was a silently corrupted config in the tree.

---

## 3. Skill Package Format (LISP Studio)

Every skill is a **directory**, not a single rule (EvoSkill-GUI + AREX-Skill structure, both verified):

```
config/skills/<skill_id>/
├── meta_info.json        # retrieval metadata: id, intent, keywords, args, status, version,
│                         #   categories (≤2 from the 7-category menu), expose_as_tool (bool)
├── plan.scm              # the MicroScheme rule (pure State → Plan, gas-metered)
├── backup.md             # alternative trigger patterns when primary fails
├── recover.md            # what to do when the plan errors or preconditions break
└── failure_examples/     # recorded shadow failures (feeds induction)
    └── failure_001.json
```

**Retrieval:** metadata-based only (intent + keywords + args + status). Verified: EvoSkill-GUI §4.3 Table 5 — metadata retrieval 12/12 correct-skill reuse vs. 1/12 full-text (independently spot-checked by the author against the local PDF, page 8: "Average / Hit Rate 0.8753 / 0.4050, 12/12, 1/12"). **Only `meta_info.json` is vectorized** into `memory.sqlite`; raw `plan.scm` is never embedded.

**Library bound (owner Decision 1: A now, B later):**
- Hard cap of **30 ACTIVE skills** (16 factory + ≤14 induced). Exceeding 30 triggers an explicit retirement prompt in LISP Studio. This cap governs the **rule library** — per-turn matching cost and `:when`-collision risk (two rules matching the same state, priority conflicts, unintended shadowing), both of which grow with library size. It stands at ship and is revisited at L5 review with collision-rate and matching-latency telemetry, not raised on argument.
- `config/skills/_retired/` exists from day one; retired skills remain on disk but leave the retrieval index.
- **Categories:** every skill declares ≤2 categories in `meta_info.json` from the 7-category menu (Pack 1 Cognitive Core, Pack 2 Information, Pack 3 Host Perception, Pack 4 Companion, `self`, `host_readonly`, `shared`). Induced rules are assigned categories from the tool classes their plans use, confirmed by the operator at promotion. The category mechanism bounds what is *exposed to the LLM* per turn (§2.4); it does not relax the 30-cap on the rule library.
- **L5 (pulled forward, re-scoped):** the deterministic category mechanism of §2.4 delivers Decision-1 Option B without neural infrastructure. The NPU-embedding variant (learned within-category ranking) is re-scoped as a post-C1 refinement (§8).

**Separate budgets (reviewer item 7):** the 30-skill cap and the 18-tool cap are **independent**. Skills are matched by the MicroScheme engine against `RuleState` outside the LLM prompt; the LLM never sees the rule catalog. The 30-cap bounds rule-engine matching latency and retrieval precision. The 18-cap bounds the LLM's `tool_calls` catalog reliability (BFCL). A skill whose plan calls a tool does not consume a prompt-catalog slot.

**Registration:** `lucca-admin skills register <dir>`.

**Lifecycle:** authored skills ship ACTIVE after the L1 acceptance gate (§9); induced skills enter QUARANTINE per D-REAS-06. Automatic promotion is prohibited, permanently.

---

## 4. Seed Content

### 4.1 What a Rule Can and Cannot See (code evidence)

`RuleState` ([`schemas.py:286-299`](../src/lucca/core/schemas.py)) carries exactly: `transcript`, `transcript_lower`, `intent`, `intent_conf`, `entities`, `hour_local`, `weekday`, `apps_running`, **`last_tool` (name only)**, **`last_tool_ok` (bool only)**, `session_turns`, `mode`. **There is no tool-result payload in rule state.**

The 14 state predicates ([`prims.py:358-373`](../src/lucca/reasoning/scheme/prims.py)): `intent=`, `entity-has?`, `entity`, `entity-int`, `entity-num`, `entity-str`, `transcript-has?`, `transcript-matches-glob?`, `app-running?`, `hour-between?`, `weekday?`, `last-tool-ok?`, `last-tool=`, `session-turns>=`.

The plan constructors ([`prims.py:376-498`](../src/lucca/reasoning/scheme/prims.py)): `list`, `say` (**static string only** — no interpolation primitive exists), `tool` (name + literal/entity-derived kwargs), `yield-to-core`, `interrupt-core`. Pure primitives: arithmetic, comparison, `not`, `len`, `str-contains?`, `str-lower`, `min`, `max`.

**Consequence:** a rule is a pure `State → Plan` function evaluated once per turn. It cannot read a tool result. Results reach the user through the **orchestrator**: the plan executes, then `build_narration_messages(tool_name, tool_args, tool_result, user_text)` hands the result to the LLM for ACT_THEN_NARRATE narration ([`orchestrator.py:1454`](../src/lucca/core/orchestrator.py), [`prompt_builder.py:828`](../src/lucca/brain/prompt_builder.py)). `last_tool`/`last_tool_ok` exist so the **next turn's** evaluation can react to what happened (e.g., "last tool failed → yield to core").

### 4.2 Factory Skill Library — Expressibility Table (reviewer item 2)

| Skill | Class | How it works, concretely |
|---|---|---|
| `calc-eval` | **Tool-call + narrate** | `(tool run_python :code (entity-str "expr"))` → orchestrator executes → LLM narrates the numeric result. The rule's own `say` is a static lead-in ("Computing that."); it cannot say the result. |
| `memory-brief` | **Tool-call + narrate** | `memory_search` → LLM synthesizes. Commit path: `memory_commit` with entity content + provenance tag — **dispatcher currently fails closed** (Handoff #5 gate F1): an LLM-issued commit is `LLM_NARRATION`, for which no signer exists (ADR-006). A legitimate path (rule-engine dispatch with entity-derived content → `ExtractorSigner`/`USER_DERIVED`, or a confirmation turn signed on the user's own utterance) requires an ADR before the tool is enabled. |
| `note-take` | **Tool-call + static say** | `note_write` with entity content → static confirmation. |
| `self-health` | **Tool-call + narrate** | `self_metrics` → LLM narrates with behavioral-state conditioning. |
| `quick-fact` | **Tool-call + narrate** | `search_web` → LLM extracts and narrates with source attribution. The "extract" step is the LLM, not the rule. |
| `define-term` | **Tool-call + narrate** | `search_web` or `memory_search` → LLM defines. |
| `unit-convert` | **Tool-call + narrate** | `run_python` with dimensional check → LLM narrates. |
| `recent-context` | **Tool-call + narrate** | `memory_search` (recency-weighted) → LLM summarizes. |
| `resource-report` | **Tool-call + narrate** | `sys_info op=resources` → LLM summarizes. |
| `sys-specs` | **Tool-call + narrate** | `sys_info op=specs` → LLM answers. |
| `proc-top` | **Tool-call + narrate** | `sys_info op=processes` → LLM summarizes top-N. |
| `session-recap` | **Tool-call + narrate** | `memory_search` (today, recency) → LLM digests. |
| `time-greeting` | **Pure say** | `hour-between?` selects among static greeting strings via `if`. |
| ~~`barge-in-sorry`~~ | **Primitive exists, wiring + semantics BLOCKED** (Phase 4 gate 2026-09-21; re-confirmed Handoff #5 gate) | `RuleState.interrupted` and the `interrupted?` predicate now exist (schema, prims, Z3), but `Orchestrator._build_rule_state` never populates the field from the audio-layer barge-in event, so the trigger is still unreachable in production — it fires only in test fixtures. Shipped ACTIVE twice with an unreachable trigger; **retired at both gates**. Re-enable requires (a) orchestrator wiring: previous turn's `TurnTrace.interrupted` → next `RuleState.interrupted`; (b) a predicate that yields to core when the barge-in transcript carries content (the user must be *answered*, not apologised to); (c) a router-reachable golden trace (no `barge_in` intent exists). |
| `plan-decompose` | **Yield-shortcut** | Decomposition is LLM work: `(yield-to-core "multi-step task" :mode "plan")`. |
| `correction-ack` | **Yield-shortcut** | `(yield-to-core "operator correction" :salience "high")`. |
| ~~`artifact-check`~~ | ⏸ deferred | Deferred with the `artifact_verify` tool. |
| ~~`late-night-brevity`~~ | **Not a rule — reclassified** | Stance conditioning lives in the prompt builder (behavioral-state feature), not the rule engine. Implemented as a prompt-builder feature, not a skill. |
| ~~`induction-watch`~~ | **Not a rule — reclassified** | Cross-turn pattern counting is the induction pipeline's telemetry job (D-REAS-06 watches history). Rules have no cross-turn pattern state. Implemented orchestrator-side, not as a skill. |

**Factory library: 15 ACTIVE skills** (12 tool-call + narrate, 1 pure-say, 2 yield-shortcut) + 1 blocked-on-primitive (`barge-in-sorry`). Per the reviewer's instruction, L1b starts with the tool-call-shortcut skills.

**Phase 4 gate finding (2026-09-21) — the "entity-absent" invariant.** The heuristic router extracts exactly `file`, `url`, `quoted`, `app` and emits exactly `dangerous, launch_app, file_read, file_write, memory_query, chit_chat, web_fetch, clarify, unknown`. Any tool-call skill whose plan reads an entity the router does not extract (`expr`, `topic`, `term`, …) has **two paths**: the deterministic `:when` path, where the entity is absent, and the `invoke_skill` path, where the LLM supplies it via `args` (merged into `entities` at [`orchestrator.py:2149-2151`](../src/lucca/core/orchestrator.py)). **The plan must branch on entity presence: yield to core when absent, call the tool when present.** A placeholder default (`"2 + 2"`, `"news"`) in the absent branch is a confabulated action and violates doctrine §1.6. Golden traces must cover the absent path (fire, no tool) as well as the present path.

### 4.3 Seed Tools (new, per taxonomy)

Priority order: `memory_search`/`memory_commit` → `note_write`/`note_read` → `sys_info` → `self_metrics` → `clipboard_read`. Deferred: `schedule_event`, `artifact_verify`, `screenshot_capture`.

---

## 5. The S1 Contract — Typed Proposal / Decision / Outcome

**Problem:** `yield-to-core`, contrastive shadow logging (L2), router abstention (C1), and the induction viewer (L3) all presuppose a typed record passing between the rule engine and the LLM core.

**Contract (Pydantic v2, `src/lucca/core/schemas.py`):**

```python
class Proposal(BaseModel):      # emitted by S1 (rule engine)
    rule_id: str
    plan: list[PlanStep]        # typed tool calls + say steps
    confidence: float           # from rule metadata + Recall hit rate (post-C1)
    gas_estimate: int
    evidence_refs: list[str]    # TurnTrace IDs of inducing episodes

class Decision(BaseModel):      # emitted by arbiter / S2
    proposal_id: str
    verdict: Literal["accepted", "overridden", "escalated"]
    reason_code: str            # machine-readable, e.g. "LOW_RECALL_HIT_RATE"

class Outcome(BaseModel):       # grounded, never self-judged
    decision_id: str
    signal: Literal["tool_exit_zero", "pydantic_valid", "operator_confirm",
                    "operator_correct", "abstained"]
    detail: str
```

**Rules:**
- `Outcome.signal` comes only from external observables. **Gemma-4 never grades its own induced rules** (XConf §C).
- Every shadow evaluation, promotion decision, and experience-bank episode is a `(Proposal, Decision, Outcome)` triple persisted to SQLite WAL.
- **Semantics caveat (reviewer item 5b):** `tool_exit_zero` and `pydantic_valid` measure **execution success** ("the tool didn't crash"), not **task success** ("it helped the user"). The experience-bank hit rate built on these signals is an *execution-reliability* rate until `operator_confirm`/`operator_correct` signals accumulate. Studio UI and reports must label it as such; the two rate types are never conflated.

---

## 6. Shadow, Induction & Lifecycle

### 6.1 What Shadow Clusters Prove — and What They Don't (Rule of Three correction)

Under the frequentist Rule of Three (3/N), 5 shadow clusters with 0 errors bounds a rule's failure rate only to **≤60%**. Shadow clusters therefore demonstrate **intent recurrence** (the pattern is real and repeated), never safety. Safety is established by Z3 SMT verification, gas metering (1,000 gas limit), typed accessors (D-SEC-04), and macro bounds (D-REAS-05). Documentation, Studio UI copy, and promotion prompts must say this explicitly. The promotion gate remains: ≥5 distinct shadow clusters, 0 errors, explicit operator approval.

### 6.2 L2 — Shadow Telemetry Upgrades

1. **Replay-before-shadow (Dream-RSI, verified):** candidate induced rules are first evaluated offline against the 50 most recent recorded `TurnTrace` episodes. Rules that would have errored or misfired on past turns are rejected at zero user cost before consuming live shadow budget.
2. **Contrastive shadow logging (ModularRSI §3.3, verified):** each shadow evaluation logs the paired contrast — the rule's plan output vs. what the core LLM did on the same turn.
3. **Statistics:** paired McNemar tests for Studio metrics; Wilson score intervals on all rates. Binary pass/fail has no power at N < 50.

### 6.3 L3 — Induction Viewer & the Acceptance Test That Matters

1. **Contrastive plain-English diffs:** *"What Lucca does today"* vs. *"What this rule will do"* — never raw S-expressions (review fatigue → rubber-stamping, F-Q7-5).
2. **Evidence display:** the 5 inducing historical turns shown verbatim alongside the candidate.
3. **Promotion:** one click, operator-only, permanent prohibition on automation.
4. **Acceptance test:** L3 passes only when a rule Lucca **induced herself** from ≥3 repeated interactions enters QUARANTINE, clears replay + 5 live shadow clusters with 0 errors, survives contrastive review, and is promoted by the owner via `lucca-admin`. The 16 authored factory skills bypass quarantine and prove nothing about this path. `calc-open-with-expr-v1` (authored, currently 1/5 clusters) validates mechanics only.

### 6.4 T4 — Outcome Telemetry & Circuit Breaker (owner Decision 2, Option A)

- Per-tool and per-rule success/failure persisted, queryable via `lucca-admin tools report` and `lucca-admin rules report`, with Wilson score intervals.
- **Circuit breaker:** single active-path failure triggers immediate demotion to QUARANTINE and the user is alerted (F-Q7-4, intentionally strict single-strike circuit breaker for v1.0; sliding-window relaxation deferred to v2).

### 6.5 L4 — Macro Composition (corrected per reviewer item 2)

- `MAX_MACRO_DEPTH = 8`, `MAX_MACRO_STEPS = 64` (D-REAS-05, unchanged).
- **Intermediate validation is orchestrator-side, not rule-side.** The orchestrator executes plan actions sequentially and schema-validates each `ToolResult` before dispatching the next action; a failed validation aborts the plan and yields to core. **Rules cannot inspect intermediate results within a plan** — `RuleState` carries no result payload (§4.1). Conditional branching on a tool result requires `yield-to-core` and re-evaluation on the next turn, where `last_tool`/`last_tool_ok` are visible (Q1 track: "Intermediate Observations Require Yielding").

---

## 7. Confidence & Difficulty Gating

### 7.1 C1 — Experience Bank (Recall-only)

**Design (corrected per XConf §K and the Bonsai analysis):**

- Store per-turn episodes as S1-contract triples plus `{task_embedding, stated_confidence}`.
- **Recall (implemented):** non-parametric, kernel-weighted historical hit rate over the k=50 nearest past episodes (task embedding + stated confidence key), computed arithmetically in SQLite. No LLM call. Size-invariant per XConf App. J.
- **Reflect (omitted):** verbalized self-reading of past episode cards collapses below 27B dense parameters (XConf §K Fig. 14b). Gemma-4 is 12B. Bonsai-2-27B is 2-bit ternary — its parameter count is a label, not a measurement of the dense-27B capability XConf evaluated. Neither clears the cliff by default.

**Uses of Recall:**
- **Router abstention:** historical hit rate for the current confidence band below threshold → route to FULL_LOOP (S2). Conformal framing per Selective Conformal Risk Control (arXiv:2512.12844).
- **Validator severity weighting:** claims from domains where Lucca's past confidence was poorly calibrated get lower severity weight.

### 7.2 C1b — Optional: Bonsai Slot-2 Async Reflect (gated experiment)

Reflect has no latency budget — it is a calibration pass, not a turn. The two-slot topology (one resident server at a time, validated in the bake-off) permits an **asynchronous** Reflect job on Bonsai in slot 2, re-calibrating the experience bank while the companion is idle.

**Gate (must pass before implementation):** run XConf's Recall-vs-Reflect ablation (App. D, Table 21) on ≥100 of Lucca's own graded episodes with Bonsai. If Reflect adds AUROC over Recall alone, ternary-27B clears the cliff *for our data* and C1b proceeds. If not, the experiment closes and the fork dependency is avoided. Also requires the PrismML fork ADR (bake-off prerequisite #7: pin commit `9a9394a89`, CUDA arch 120, binary SHA256).

**Expected value is modest:** XConf finds Recall alone within .02 AUROC of the blend on most cells; Reflect's margin concentrates on silent-failure domains, and Lucca's tool outcomes are mostly *visible* (exit codes, operator corrections).

### 7.3 C2 — Difficulty-Aware Thinking (When2Think, adapted)

`enable_thinking` becomes per-turn, not global:
- Router estimates difficulty from: intent class, entity count, tool-call requirement, Recall hit rate for similar turns.
- Easy turns → `enable_thinking=false` (fast path; measured TTFT ~280–290 ms on both brains).
- Hard turns → `enable_thinking=true` (reserved for explicit deep-reasoning requests per D-BRAIN-05 v2).

**Constraints:** reasoning tokens add 400–1,200 ms TTFT (measured: Gemma thinking 1,933 ms vs no-think 288 ms). When2Think is a post-training RL method; Lucca adapts the *principle* as a routing-time heuristic — no weight fine-tuning. **Cache interaction (reviewer item 6):** toggling `enable_thinking` changes the rendered template and can invalidate the prefix cache; the two template variants must both stay warm — see the C2 acceptance test (§9).

---

## 8. Deferred Capabilities (explicit, with triggers)

| Capability | Status | Trigger to revisit |
|---|---|---|
| **Domain lobes** (tiny encoder + retrieval index + macro library + tool policy per domain) | Deferred | Induction telemetry shows a recurring domain cluster (≥3 distinct induced rules in one domain, or ≥20 turns/week in one intent family). No lobe without evidence of a recurring domain. |
| **NLI commonsense validator** | Deferred | R4 encoder selection complete (ModernBERT-small vs MiniLM-L6-v2 on OpenVINO NPU) **and** NPU deployment path validated. MiniCheck/DecoVer are the reference designs. |
| **Dynamic skill shortlisting** (owner Decision 1, Option B) | **Pulled forward as the deterministic category mechanism (§2.4)**; NPU-embedding refinement deferred to post-C1 | The category menu + deterministic router mapping delivers Option B without neural infrastructure. The NPU-embedding variant (learned within-category ranking) is gated on the NPU embedding path existing for memory retrieval. |
| **Open-mic VAD** | Deferred indefinitely as primary mode | PTT is technically superior for this use case (0 ms endpointing, no self-interruption; open-mic VAD adds 400–800 ms dead air + echo-loop self-interruption per LiveKit/Pipecat issue trackers). May ship as an optional secondary mode. |
| `schedule_event`, `artifact_verify`, `screenshot_capture` | Deferred | Registry headroom or the vision-lobe trigger. |

---

## 9. Implementation Ladder (acceptance-tested)

| Rung | Status | Deliverable | Acceptance test / Evidence |
|---|---|---|---|
| **T1** | **DONE** | 3-class taxonomy in `capabilities.py`; `launch_app` removed; `target` field enforced; **frozen prefix (≤18 native tools + static 7-category menu) + category manifest via Prompt Frontier Suffix; `invoke_skill` dispatch; `format_skill_tools` retired** | `capabilities.py` 3-class taxonomy, frozen prefix. Prefix **byte-identical across 10 consecutive turns spanning ≥3 different categories** (a repeated-category sequence is not a valid test); suffix varies with category while the prefix cache holds (TTFT p95 ≤ 350 ms across category switches); registry ≤18 asserted; negative tests: out-of-class arg rejected, `skill_id` not in the current manifest rejected; **shortlist recall: correct skill in the injected manifest, Wilson 95% lower bound ≥ 0.90 on the category-selection eval set** (report intervals, not point estimates); every LLM category fallback logged to `failure_examples/` |
| **S1** | **DONE** | `Proposal`/`Decision`/`Outcome` Pydantic schemas + WAL persistence | `lifecycle.py` emit_shadow_triple / emit_execution_triple. Every shadow evaluation and promotion produces a complete triple; negative test: `Outcome.signal` from LLM self-judgment rejected by schema; reports label execution-reliability vs task-success rates separately |
| **L1** | **DONE** | Skill package format + 16 factory skills ACTIVE + `_retired/` + 30-cap enforced | 16 factory skills in `config/skills/`, `lucca-admin skills` CLI. **Per skill, before ACTIVE:** fires on its trigger turn; passes the frozen-regression harness; passes `validate_rule_static`; passes Z3 verification (SAT and contingent cases); ships with ≥2 golden traces (fire + no-fire); Studio-editable. 31st ACTIVE skill triggers retirement prompt; only `meta_info.json` present in the vector index |
| **T2** | **DONE** | Native tools: `memory_search/commit`, `note_write/read`, `sys_info`, `self_metrics` | 18 tools in `capabilities.py` with Risk classification. Each fires from a live turn; `sys_info` output stamped `TOOL_CONTENT_UNTRUSTED` (negative test: a hostile process name in the output cannot enter memory); Class A < 50 ms, Class B < 500 ms; >500 ms synchronous tool preceded by verbal cue |
| **L2** | **DONE** | Replay-before-shadow + contrastive logging + Studio telemetry | `replay.py`, contrastive shadow in `lifecycle.py`. Candidate rule replayed against 50 past turns before first live shadow; contrastive pair logged per evaluation; McNemar + Wilson intervals in Studio |
| **A1** *(ratified 2026-09-21 as [`D-MEM-04`](../DECISIONS.md); spec [`AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md`](./AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md))* | **DONE** | Autobiographical memory & self-model: `ASSISTANT_UTTERANCE` / `ASSISTANT_BELIEF` (memory-eligible, **not** grounding-eligible), `ASSISTANT_ACTION` receipts, `COHERENCE_BREACH` records, `SELF_HISTORY` cascade substrate, evidence-gated belief revision via `supersede(reason)` — autonomous unless flagged for review; importance-weighted retention with nightly roll-up | `reflection.py`, belief revision, review queue, nightly rollup. Introspective Accuracy Wilson LB ≥ 0.90 at N ≥ 50 self-probes; fabricated-recollection negative test abstains; unexplained opinion drift ≤ 5% across sessions ≥ 7 days apart; every stance change has a reasoned supersession and is spoken once; flagged revisions wait in the Studio review queue; cross-time narration-vs-receipt mismatch ≤ 2%; 0 supersession-chain violations; a stored opinion can never raise a fact's Belnap value; a revision without a grounding-eligible reason is rejected |
| **L3** | **DONE** | Induction viewer: plain-English diffs + 5 inducing turns + one-click promote | `induction.py`, quarantine-shadow-promote lifecycle. **One induced rule completes the full lifecycle** (induce → QUARANTINE → replay → 5 clean clusters → contrastive review → owner promotion) |
| **T3** | **DONE** | Class C gates at dispatcher layer | Risk enum, UNTRUSTED stamping, dispatcher gates. Negative test: unconfirmed Class C call rejected at `capabilities.py` even when the LLM emits it; confirmed call succeeds; Class C-derived memory stamped `TOOL_CONTENT_UNTRUSTED` |
| **L4** | **DONE** | Macro composition with orchestrator-side intermediate validation | D-REAS-05 macro bounds, `smt_verifier.py`. Composition test passes; depth-9 and step-65 macros rejected; a mid-plan `ToolResult` failing schema validation aborts the plan and yields to core; negative test proving a rule cannot read an intermediate result |
| **T4** | **DONE** | Outcome telemetry + circuit breaker | `stats.py` Wilson intervals, auto-demotion in `lifecycle.py`. `lucca-admin rules report` shows Wilson intervals after 50 turns; single active-path failure triggers immediate demotion to QUARANTINE (intentionally strict for v1.0; sliding-window relaxation deferred to v2) |
| **C1** | **DONE** | Experience bank: episode store + Recall + router abstention | Episode store and Recall path live (`src/lucca/reasoning/recall.py`). Conformal abstention verified in WO-14 / WO-15. **Abstention precision: Wilson 95% lower bound ≥ 0.80 at N≥100 graded turns** (achieved 96.08%, Wilson LB = 0.8541 on N=100 turns in `tests/test_c1_abstention_acceptance.py::test_c1_conformal_abstention_acceptance` and offline twin `test_c1_abstention_offline`; report: `logs/test_reports/c1_abstention_acceptance_20260924T045336Z.json`); no LLM call in the Recall path |
| **C1b** | **DEFERRED** | (Optional, gated) Bonsai slot-2 async Reflect | Recall-vs-Reflect AUROC ablation on ≥100 graded episodes shows Reflect adds value; PrismML fork ADR ratified |
| **C2** | **DONE** | Difficulty-aware thinking | WO-13.3 dynamic thinking, explicit-only scoping. Easy turns skip thinking (TTFT < 350 ms); hard-turn accuracy ≥ baseline on the hard eval slice; **turn-alternation cache test: in an alternating easy/hard sequence, no-think turns after a thinking turn keep p95 TTFT ≤ 350 ms (both template variants stay cache-warm)** |
| **L5** | **DEFERRED** | (Re-scoped, post-C1) NPU-embedding refinement of within-category skill ranking; **30-cap review with telemetry** | Learned ranking beats deterministic category order on the skill retrieval eval (shortlist-recall Wilson LB ≥ 0.90 maintained); cap review uses measured `:when`-collision rate and rule-matching latency, not argument |

**Order:** T1 → S1 → L1 → T2 → L2 → **A1** → L3 → T3 → L4 → T4 → C1 → C2. (C1b, L5 gated/deferred.)


**Measurement integrity:** all rates reported with Wilson score intervals; all before/after comparisons use paired tests (McNemar for binary outcomes). The confabulation battery moves to **N≥100** so the Clopper-Pearson upper bound tightens below 4% (current: 0/25 → upper bound 13.72%; 0/100 → 3.62%).

---

## 10. Research Grounding (corrected per T0 audit; grades re-checked per reviewer item 8)

| Design decision | Source | Grade |
|---|---|---|
| Skill package 3-layer format | EvoSkill-GUI (arXiv:2609.17653); Repo-To-Skill/AREX (arXiv:2609.02749) | Directly supports |
| Two-tier category routing (category menu → per-turn manifest) | AREX-Skill (arXiv:2609.02749) — hierarchical skill routing with progressive disclosure | Directly supports |
| Metadata-based retrieval > full-text (12/12 vs 1/12) | EvoSkill-GUI §4.3 Table 5 | Directly supports — **independently spot-checked by the author against the local PDF** (page 8: "Average / Hit Rate 0.8753 / 0.4050, 12/12, 1/12") |
| Contrastive shadow analysis | ModularRSI (arXiv:2609.14857) §3.3 | Directly supports |
| Replay-before-live shadowing | Dream-RSI (arXiv:2609.14858) | Directly supports |
| Skill revision via isolated critic | EvoSkill-GUI §3.3 (information isolation Eqs. 8a–8c) | Directly supports |
| Library cap + retirement | Library Drift (arXiv:2605.19576, ref [152] in arXiv:2609.11873v2); Rethinking Skill Evolution (arXiv:2608.02636, ref [153] ibid.); SkillsBench | Directly supports |
| Experience bank; self-labeled banks fail; 27B Reflect cliff | XConf (arXiv:2609.17708) §C, §K Fig. 14b | Directly supports |
| Conformal routing abstention | Selective Conformal Risk Control (arXiv:2512.12844, Xu/Guo/Wei) | Directly supports (theory) |
| Difficulty-aware thinking | When2Think (arXiv:2609.19671) | Analogy (RL training → runtime routing heuristic) |
| Quarantine/shadow governance | Q-Evolve (arXiv:2603.04419); PANDO (arXiv:2605.24785); Vera (industry test-quarantine framework — no valid arXiv ID; inspiration only) | Analogy / Inspiration |
| RSI autonomy ladder (Lucca = L4) | The Last AI Built by Humans (arXiv:2609.11873) §3.5 | Directly supports |
| Affect-stamped memory | PsychoAgent (arXiv:2608.07438); DAMM (architectural pattern, no arXiv ID) | Directly supports / Inspiration |
| Grammar-level capability bounding via homoiconicity | Pel (arXiv:2505.13453, Mohammadi). Passage (Q1 track, F-Q1-4): "Pel is a minimal Lisp-inspired language designed as a constrained-decoding target for LLMs. Because Lisp is homoiconic (code is data), capabilities (e.g., I/O, network) can be disabled simply by pruning grammar symbols rather than building complex OS sandboxes." | **Directly supports the principle; evidence grade E3** (single-author experiments, BEACON workflows) |
| Two-stage verify: formal action language + solver-checked preconditions | LLM+AL (arXiv:2501.00830, Ishay & Lee, AAAI 2025). Passage (Q1 track, F-Q1-5): "Translates natural language user goals into the formal action language BC+, which is executed by an automated Answer Set Programming reasoner (CPLUS2ASP). If an action's preconditions are unsatisfied by the current world state, the solver mathematically proves plan infeasibility and triggers an LLM repair prompt." | **Directly supports; evidence grade E2** (near-perfect accuracy where standalone GPT-4 and Gemini Ultra failed on causal hallucinations) |
| Dual verification (syntactic + executable) | DecoVer (ACL 2026) | Directly supports |
| CodeAct containment (run_python as tool, never substrate) | CodeAct (ICML 2024) vs Pel/LLM+AL contradiction, resolved SYNTHESIS §3.1 | Resolved |
| PTT > open-mic VAD for desktop companion | LiveKit/Pipecat issue trackers (F-Q5) | Directly supports |
| Rule of Three (5 clusters ⇒ ≤60% failure bound) | Frequentist statistics (3/N); SYNTHESIS §4.2 | Directly supports |

**Purged:** arXiv:2609.13770 (offline specialist distillation; no architectural connection to runtime skill packages).

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Library drift degrades retrieval | Hard cap 30 ACTIVE; `_retired/`; retirement prompt in Studio (Decision 1A) |
| Induced rules encode task-specific shortcuts | Contrastive diff review before promotion; replay-before-shadow; plain-English diffs in the viewer |
| Experience bank poisoned by self-labeled outcomes | S1 contract: `Outcome.signal` from external observables only; schema rejects LLM self-judgment |
| Execution-reliability mistaken for task-success | S1 semantics caveat (§5); separate rate labels in Studio and reports |
| Class B/C tools leak attacker-controlled text into memory | `TOOL_CONTENT_UNTRUSTED` stamp on `sys_info`, Class C, and egress content; dispatcher-layer gate |
| Thinking-mode latency breaks voice budget | Difficulty gate; thinking only on hard turns; turn-alternation cache test (C2) |
| Shadow telemetry mistaken for safety proof | Rule of Three correction documented in §6.1, Studio UI copy, and promotion prompts |
| Post-promotion distribution shift | T4 circuit breaker: auto-demote at >10% failure over 10-turn window |
| KV-cache invalidation from schema mutation | T1: one frozen sorted block, ≤18 tools, changes only on Studio edit; byte-identity asserted across mixed-intent turns |
| Tool overload on 12B brain | Registry capped ≤18 native tools; skill exposure bounded per turn by the category manifest |
| Wrong category hides the right skill | Shortlist-recall metric (Wilson LB ≥ 0.90) on the category-selection eval; LLM category fallback (rate-limited, logged to `failure_examples/`); dispatcher rejects out-of-manifest `skill_id`s |
| Macro cascading errors | Orchestrator-side intermediate validation; abort + yield on violation; rules cannot read intermediate results by construction |
| Skills assumed to do what rules can't express | §4.2 expressibility table; skills tagged tool-call+narrate / pure-say / yield-shortcut before authoring |

---

## 12. Owner Decisions Log

| # | Decision | Choice | Date |
|---|---|---|---|
| 1 | Active skill library bound | **A now, B later:** hard cap 30; dynamic shortlisting deferred to rung L5 | 2026-09-21 |
| 2 | Demotion circuit breaker | **Option A:** auto-demote ACTIVE → QUARANTINE at >10% failure over 10-turn window, with user alert | 2026-09-21 |
| 3 | Section 8 errata | **Approved:** 6 ID corrections, 2 attribution fixes, ghost purge (applied in §10) | 2026-09-21 |
| 4 | Verbalized Reflect on C1 | **Approved omission:** Recall-only; C1b gated experiment for Bonsai slot-2 Reflect | 2026-09-21 |
| 5 | Reviewer ratification scope | Doctrine, taxonomy, S1, L1a ratified; T1 ratified conditional on fixes 1 & 4 (applied in v1.1.1); L1b held pending §4.2 expressibility table (delivered in v1.1.1 from code evidence) | 2026-09-21 |

---

## 13. Immediate Next Steps (Gemini handoff #4)

1. **T1:** Refactor `capabilities.py` to the 3-class taxonomy; remove `launch_app`; add `target` field; freeze the ≤18-tool prefix + static category menu; implement the category manifest via the Prompt Frontier Suffix; add `invoke_skill`; retire `format_skill_tools`; byte-identity test across ≥3 categories.
2. **S1:** Implement `Proposal`/`Decision`/`Outcome` schemas + WAL persistence; wire shadow evaluation to emit triples; separate execution-reliability vs task-success rate labels.
3. **L1a:** Skill-package directory format; `lucca-admin skills register/list/retire`; `_retired/` + 30-cap.
4. **L1b-pilot (dependency-corrected):** author the 8 skills whose tool dependencies exist today — 4 tool-call (`calc-eval`, `unit-convert` via `run_python`; `quick-fact`, `define-term` via `search_web`), 2 pure-say (`time-greeting`, `barge-in-sorry`), 2 yield-shortcut (`plan-decompose`, `correction-ack`). The remaining 8 tool-call skills require T2 tools (`memory_search`, `note_write`, `sys_info`, `self_metrics`) and move to handoff #5 after T2. Each skill must pass static validation, Z3 (SAT + contingent), and ship ≥2 golden traces before ACTIVE.
5. **Verify:** full T1 suite + frozen regression harness + KV-cache byte-identity assertion + existing QUARANTINE rule still shadows correctly.

*Owner approval gate: v1.1.2 resolves the reviewer's items 1–8 and adopts the category design. L1b may start with the tool-call-shortcut skills per the reviewer's instruction.*
