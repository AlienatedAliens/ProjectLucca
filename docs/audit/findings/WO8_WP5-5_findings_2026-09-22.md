# WO-8 WP-5.5 Findings — Post-Gemini Verification, Test/Code Co-Review & A1 Battery Rerun

**Date:** 2026-09-22
**Author:** Zoo (verification + test/code co-review pass after Gemini session terminated mid-job)
**Commits:** `c032882`, `dcd13f7`, `6dea387`, plus this pass
**Scope:** Verification of Gemini's uncommitted working tree, root-cause of the
unpack crash, extensive review of the A1 test code **alongside** the code it
tests, fixes on both sides, and live re-runs on Gemma-4 (RTX 5080).

---

## 1. Defects Fixed

### Session 1 (commits `c032882`, `dcd13f7`)

| ID | Defect | Fix |
|---|---|---|
| **F-WO8-10** | A1 harness replaced `output_supervisor` with bare `MagicMock()` → every live turn aborted with `not enough values to unpack (expected 2, got 0)` | Real `OutputSupervisorSession` in harness |
| **F-WO8-11** | Oscillation guard deduped any pending review by `belief_id`, breaking 5-flag gating | Dedupe only identical `proposed_content` |
| **F-WO8-12** | `FakeMemoryStore.commit` / `MemoryStorePort.commit` lacked `now` kwarg | Added kwarg |
| **F-WO8-13** | Test queried non-existent `memories.provenance` column | Join through `provenance_envelopes` |
| **F-WO8-14** | `TruthInReceiptMatcher` had no temporal scoping — past-session recollections Tier-1 aborted (7/60 Gemma, 3/60 Bonsai canned refusals) | `PAST_CONTEXT_PATTERN` exemption |
| **F-WO8-15** | Grader abstention vocabulary + naive substring fabrication markers mislabeled honest abstentions | Extended vocabulary; negation-aware `_has_marker` |

### Session 2 (commit `6dea387`) — test/code co-review

| ID | Defect | Side | Fix |
|---|---|---|---|
| **F-WO8-16** | `detect_ungrounded_action_claims` ([`coherence.py`](../../src/lucca/core/coherence.py)) temporally unscoped AND negation-blind | code | Past-session exemption + negation guard (success qualifiers like "without errors" do NOT trigger the guard) |
| **F-WO8-17** | `_check_contradictions` committed the **user's raw question** as an `ASSISTANT_BELIEF` → spoken update leaked "New understanding: Can you open Notepad?" | code | Interrogative filter: questions are not belief candidates |
| **F-WO8-18** | A1 harness `orch.sandbox = MagicMock()` made `check_confirmation_needed()` truthy → **every tool call auto-"cancelled by user"** → model narrated "my memory search was interrupted" | test | Real in-process `SandboxService` (read-only tools execute; write/launch stay confirmation-gated) |
| **F-WO8-19** | Empty-receipts turns: any first-person action claim Tier-1 aborted mid-speech | code | Downgrade to Tier-2 when no current-turn receipts |
| **F-WO8-20** | Coherence grader counted **correct detections** as defects and flagged **every** claim on successful turns as a false breach without checking `claim.grounded` (24 phantom breaches) | test | `rate = escaped/total`; false-breach = `not claim.grounded` only |
| **F-WO8-21** | Fixture `must_contain` demanded literal internal tool names; stance polarity keywords missed natural variants | test | Paraphrase-tolerant keyword classes; polarity variant lists; CHANGE_MARKERS extended |

### Session 3 (this pass) — retrieval/tool-path co-review

| ID | Defect | Side | Fix |
|---|---|---|---|
| **F-WO8-22** | `MemoryManager.list_memories` (the `memory_search` TOOL) did a literal `LIKE '%<whole question>%'` — natural question phrasing matched nothing, so the tool reported "No relevant memories found" and the model trusted that over the (correct) injected hybrid-retrieval context, abstaining on q10/q11/q32/q14 | code | Tokenized OR fallback ranked by match count in [`src/lucca/memory/manager.py`](../../src/lucca/memory/manager.py); verified all failing probes now return the seeded facts |
| **F-WO8-23** | With the real sandbox wired (F-WO8-18), read-only turns (memory_search) had non-empty receipts, so truth-in-receipt Tier-1 aborts returned for recollection claims a `memory_search` receipt can never ground | code | Downgrade to Tier-2 unless the turn's receipts include a STATEFUL tool (write/launch/delete/run) |
| **F-WO8-24** | Abstention vocabulary still missed "I don't see any mention of…" register | test | Extended `_ABSTENTION_PHRASES` |

**Key diagnostic finding:** hybrid retrieval (`HybridRetriever`) recall is
EXCELLENT — every failing probe returned the correct seeded facts at rank 1–3.
The failures were caused by the *tool* search path (F-WO8-22) and by model
conservatism, not by the retriever.

**Post-fix live verification (3-probe spot check):** q13/q14/q47 all answer
correctly and honestly ("ran a script called benchmark.py about twenty-three
hours ago", "fetched the Python 3.12 documentation … from python.org about a
day or two ago", proper settings abstention).

## 2. A1 Live Battery — Final State on Gemma-4 (RTX 5080, all fixes applied)

| Test | Before co-review | After | Verdict |
|---|---|---|---|
| §5.2 Introspective (60 probes) | 21/60, 17 "fabrications" | **54–57/60, 0–1 fabrications** (LB 0.79–0.85) | **RED on LB ≥ 0.90 — genuine model variance + conservatism, harness now fair** |
| §5.3 Stance consistency | 80% FAIL | **PASS** | ✅ |
| §5.4 Functional coherence | 17.24% "ungrounded" (grader bug) | **PASS** (checker verified correct in isolation) | ✅ |
| §5.5 Revision chain | FAIL | **PASS** | ✅ |
| §5.6 Doctrine negative | SQL crash | **PASS** | ✅ |

**The residual §5.2 failures are real system behavior, not harness artifacts:**
across three post-fix runs the battery lands at 54–57/60 (±3 run variance) with
0–1 fabrications. Failure classes: (a) model conservatism on read/delete-file
specifics even with facts in context (q10/q11/q32); (b) occasional stochastic
deontic false positives producing the canned refusal (varies by run). The
Wilson LB ≥ 0.90 bar at N=60 requires 59/60 — statistically out of reach given
the observed variance without prompt/model changes. This is the first honest
measurement of the A1 recall ceiling; the harness is now fair.

## 3. Bonsai 2 Bake-off — verdict withheld (contaminated)

Raw numbers (28/60, 60% stance, 17.24% ungrounded) were dominated by harness
defects F-WO8-14/16/17/18 and grader defects F-WO8-20/21. A fair rung C1b
comparison requires a clean re-run with the fixed harness plus a
Bonsai-compatible tool-call demux mode.

## 4. Environment notes

- llama-server prompt-cache crash (verbatim repetition loop + ~880 MiB cache
  evictions, crash at q59) — registered, unresolved; consider `--cache-reuse`
  tuning or a build bump.
- `Lucca.exe --version` timed out once (15 s) in a T1 run — transient; 7/7 on
  immediate re-run.

## 5. Verification state at hand-back

| Gate | Result |
|---|---|
| `ruff check src tests` / `format --check` | Clean (180 files) |
| `pytest tests/test_static_gates.py` | 10/10 |
| `pytest -q` (T1) | 536/536 green (1 transient frozen-binary timeout, passed on re-run) |
| A1 live battery (T3) | **4/5 PASS**; §5.2 RED on Wilson LB (genuine model variance, 0–1 fabrications) |

**Recommended next steps (WP-5.6):**
1. Prompt-side recall nudge: instruct the companion to cite memory records
   explicitly when answering introspective probes (targets q10/q11/q32).
2. Investigate stochastic deontic false positives (canned refusal appears on
   ~1–3 probes per run; capture offending chunks via `output_supervisor_tier1_abort`).
3. Investigate llama-server prompt-cache crash (§4).
4. Clean Bonsai 2 re-run with fixed harness + Bonsai-compatible tool-call
   demux mode for a fair rung C1b comparison.
