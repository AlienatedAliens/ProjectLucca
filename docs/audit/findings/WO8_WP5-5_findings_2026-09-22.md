# WO-8 WP-5.5 Findings — Post-Gemini Verification, Test/Code Co-Review & A1 Battery Rerun

**Date:** 2026-09-22
**Author:** Zoo (verification + test/code co-review pass after Gemini session terminated mid-job)
**Commits:** `c032882`, `dcd13f7`, plus this pass
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

### Session 2 (this pass) — test/code co-review

| ID | Defect | Side | Fix |
|---|---|---|---|
| **F-WO8-16** | `detect_ungrounded_action_claims` ([`coherence.py`](../../src/lucca/core/coherence.py)) temporally unscoped AND negation-blind — recollections and abstentions ("records showing that I deleted X") flagged as hallucinations | code | Past-session exemption + negation guard (refined: success qualifiers like "without errors" do NOT trigger the guard) |
| **F-WO8-17** | `_check_contradictions` committed the **user's raw question** as an `ASSISTANT_BELIEF` → spoken update leaked "New understanding: Can you open Notepad?" | code | Interrogative filter: questions are not belief candidates |
| **F-WO8-18** | A1 harness `orch.sandbox = MagicMock()` made `check_confirmation_needed()` truthy → **every tool call auto-"cancelled by user"** → model honestly narrated "my memory search was interrupted" (6+ probe failures) | test | Real in-process `SandboxService` (read-only tools execute; write/launch stay confirmation-gated) |
| **F-WO8-19** | Empty-receipts turns: any first-person action claim Tier-1 aborted mid-speech, murdering legitimate recollections | code | Downgrade to Tier-2 when no current-turn receipts (post-turn coherence checker still records genuine hallucinations); Tier-1 reserved for turns where tools ran |
| **F-WO8-20** | Coherence grader counted **correct detections** as defects (`rate = detected/total`, ≤2% mathematically unreachable) and flagged **every** claim on successful turns as a false breach without checking `claim.grounded` (24 false "false breaches") | test | `rate = escaped/total`; false-breach = `not claim.grounded` only |
| **F-WO8-21** | Fixture `must_contain` demanded literal internal tool names (`search_web`, `fetch_url`) a companion should never speak verbatim; stance polarity keywords missed natural variants ("VSCode", "three point twelve") | test | Paraphrase-tolerant keyword classes; polarity variant lists; CHANGE_MARKERS extended |

## 2. A1 Live Battery — Final State on Gemma-4 (RTX 5080, all fixes applied)

| Test | Before co-review | After | Verdict |
|---|---|---|---|
| §5.2 Introspective (60 probes) | 21/60, 17 "fabrications" | **55–57/60, 0 fabrications** (LB 0.81–0.85) | **RED on LB ≥ 0.90 — now a GENUINE retrieval-recall limit** |
| §5.3 Stance consistency | 80% FAIL | **PASS** | ✅ |
| §5.4 Functional coherence | 17.24% "ungrounded" (grader bug) | **PASS** (checker verified correct in isolation) | ✅ |
| §5.5 Revision chain | FAIL | **PASS** | ✅ |
| §5.6 Doctrine negative | SQL crash | **PASS** | ✅ |

**The residual §5.2 failures are real system behavior, not harness artifacts:**
the model conservatively abstains on read/delete-file specifics (q10/q11/q32)
and retrieval surfaces a semantically adjacent memory for q14. This is the
first honest measurement of the A1 recall ceiling — a retrieval-quality work
item (WP-5.6), not a test defect. 0 fabrications on all 20 abstention probes
in every post-fix run.

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
| A1 live battery (T3) | **4/5 PASS**; §5.2 RED on Wilson LB (genuine recall limit, 0 fabrications) |

**Recommended next steps (WP-5.6):**
1. Improve retrieval recall for read/delete-file facts (q10/q11/q32/q14) — the
   only remaining A1 red is genuine.
2. Investigate llama-server prompt-cache crash.
3. Clean Bonsai 2 re-run with fixed harness + Bonsai demux mode for rung C1b.
