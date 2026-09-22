# WO-8 WP-5.5 Findings — Post-Gemini Verification, Unpack-Crash Debug & A1 Battery Audit

**Date:** 2026-09-22
**Author:** Zoo (verification pass after Gemini session terminated mid-job)
**Baseline commit:** `87f6af0` (WP-5); fixes committed as `c032882`
**Scope:** Verification of Gemini's uncommitted working tree, root-cause of the
`not enough values to unpack (expected 2, got 0)` crash, manual audit of the A1
live battery results (Gemma-4 and Bonsai 2), and reconciliation of
`docs/HANDOVER_gemini_8_test_hardening.md`.

---

## 1. Defects Fixed (this pass)

| ID | Defect | Root Cause | Fix |
|---|---|---|---|
| **F-WO8-10** | `turn_execution_error: 'not enough values to unpack (expected 2, got 0)'` aborted every A1 live turn mid-stream | [`tests/test_a1_live_hw.py`](../../tests/test_a1_live_hw.py) harness replaced `orch.output_supervisor` with a bare `MagicMock()`. `_stream_llm_speech` creates a **real** local `StreamingChunker`, so real chunks reached `feed_chunk()`; unpacking a MagicMock iterates as empty → `ValueError`. | Harness now wires the **real** `OutputSupervisorSession` (pure logic, no hardware I/O). |
| **F-WO8-11** | `test_reflection_5_flag_review_gating_and_approval_cycle` failed (3 pending reviews instead of 4) | Gemini's oscillation guard in [`src/lucca/memory/reflection.py`](../../src/lucca/memory/reflection.py) deduped **any** pending review by `belief_id`, silently dropping distinct revisions of the same belief (5-flag gating spec §7 Decision 4 requires independent queuing). | Guard now dedupes only identical re-proposals (`proposed_content = new_content`). |
| **F-WO8-12** | `test_turn_reaches_postturn_and_commits_transcript` failed: `FakeMemoryStore.commit() got an unexpected keyword argument 'now'` | Orchestrator now passes `now=ts` (simulated-time support) but the test fake lacked the kwarg. | Added `now: float | None = None` to `FakeMemoryStore.commit` and to the `MemoryStorePort` protocol in [`src/lucca/ports.py`](../../src/lucca/ports.py). |
| **F-WO8-13** | `test_live_a1_opinion_cannot_raise_fact` raised `sqlite3.OperationalError: no such column: provenance` | Test queried `memories.provenance`; provenance lives in `provenance_envelopes` (joined via `memories.entry_id`). | Query rewritten as a join. Test now passes on both models. |
| **F-WO8-14** | **Output-supervisor false positives (INFRA_ABORT):** 7/60 Gemma-4 probes and 3/60 Bonsai-2 probes returned the canned Tier-1 refusal *"I cannot fulfill that request as it violates core safety invariants."* | [`TruthInReceiptMatcher`](../../src/lucca/sandbox/output_supervisor.py) has **no temporal scoping**: recollections of *prior-session* verified actions ("I ran the benchmark a few days ago") were treated as current-turn ungrounded claims → Tier-1 abort. A1 introspection is *entirely* past-session recollection, so the gate fought the feature. | Added `PAST_CONTEXT_PATTERN` exemption: clauses framed as past-session recollections pass the truth-in-receipt gate (D-BRAIN-04 governs **current-turn** claims only). Current-turn claims are still gated. |
| **F-WO8-15** | Grader mislabeled honest abstentions as fabrications | (a) `_ABSTENTION_PHRASES` lacked the model's grounded-abstention register ("I do not have any verified records…", "no verified record"); (b) `_has_marker` used naive substring matching — "records showing that I deleted X" matched the fabrication marker "I deleted". | Extended abstention vocabulary; `_has_marker` now invalidates marker hits preceded by negation/recollection framing within a 60-char window. |

## 2. Manual Audit Results (user question: "Were the answers fail/pass manually audited?")

**No — until this pass, grading was purely automated string matching.** Manual
audit of the per-probe JSON reports (`logs/test_reports/a1_live_introspective_*.json`):

| Run | Failed | Grader-strict / underreport | INFRA_ABORT (false positive) | Genuine fabrication |
|---|---|---|---|---|
| Gemma-4 (pre-fix) | 39 | 18 | **7** | 11 + 3 candidates |
| Bonsai 2 (pre-fix) | 32 | 28 | **3** | 1 candidate |

**Conclusion:** the INFRA_ABORT false positives (F-WO8-14) corrupted **both**
runs — they are model-independent infrastructure defects. After F-WO8-14/15,
INFRA_ABORTs dropped to **0** and Gemma-4 introspective passes rose 21 → 30/60
on the first clean re-run. The dominant residual failure class is
**grader-fixture strictness**: `must_contain` demands literal tool names
(`search_web`, `fetch_url`) while the model correctly paraphrases
("web searches", "fetched a URL") — a fixture-rework task, not a model defect.

## 3. Bonsai 2 (Ternary-Bonsai-2-27B-PQ2_0) Bake-off — Result CONTAMINATED, verdict withheld

The A1 acceptance battery was executed against Bonsai 2 via `llama-server-prism`
(`-c 131072 -np 1 -fa on`, 12,092 MB VRAM, ~58 tok/s, zero system-RAM spillover).
Raw numbers: introspective 28/60, stance consistency 60%, ungrounded-claim rate
17.24%. **However, the manual audit (§2) shows these numbers are dominated by
harness/grader defects, not model quality:**

- Introspective (32 failed): **28 grader-strict** (honest abstentions/paraphrases
  failing literal `must_contain`), **3 INFRA_ABORT** (F-WO8-14 code bug, now
  fixed), **1** possible fabrication. ≈ 97% of failures were harness artifacts.
- Ungrounded-claim rate was **identical on both models** (10/58 = 17.24% on
  Gemma-4 AND Bonsai 2) — a strong indicator of the same temporal-scoping
  artifact in [`detect_ungrounded_action_claims`](../../src/lucca/core/coherence.py)
  (**not yet fixed** — only the output-supervisor `TruthInReceiptMatcher` was
  fixed in F-WO8-14; the coherence checker needs the same past-session exemption).
- Stance consistency (60%) and revision-chain failures are confounded by the
  **spoken-update template leak** ("New understanding: <raw user question>"
  spoken into narration — a code bug, visible corrupting Bonsai replies q12–q16).
- The one clearly Bonsai-specific issue: raw `<function=run_python>…` tool-call
  markup leaked into narration — an **integration gap** (the F-WO8-08 demux is
  built for Gemma's `<|tool_call` format and does not parse Bonsai 2's template),
  not evidence of inferior model quality per se.

**Verdict:** the Bonsai 2 bake-off result is **contaminated and cannot be used
as a fair model comparison**. A clean re-run is required after: (a) the
coherence-checker temporal-scoping fix, (b) the spoken-update leak fix, (c)
grader fixture rework (§5.1), and (d) a Bonsai-compatible tool-call demux mode.
No thresholds were edited to mask anything.

## 4. Environment Instability (registered, unresolved)

During the third Gemma-4 introspective re-run, `llama-server` (stock build,
`-np 1 -c 16384`, q8_0 KV, flash-attn) **crashed** at q59 after the model
degenerated into a verbatim repetition loop from q29 onward. The server log
showed continuous prompt-cache evictions ("removing oldest entry, size ≈ 880 MiB")
before the crash. The run was invalidated. Follow-up: investigate prompt-cache
thrash under repeated ~3.2K-token prompts on this llama.cpp build; consider
`--cache-reuse` tuning or a build bump.

## 5. Verification State at Hand-back

| Gate | Result |
|---|---|
| `ruff check src tests` / `ruff format --check` | Clean |
| `pytest tests/test_static_gates.py` | 10/10 |
| `pytest -q` (T1 full baseline) | 528 passed, 0 failed (2 env-dependent failures fixed: F-WO8-12, VRAM transient) |
| A1 live battery (T3) | **RED** — 1/5 green (`opinion_cannot_raise_fact`); remaining 4 blocked by grader-fixture rework (§2) + server instability (§4) |
| Bonsai 2 A1 bake-off | Contaminated result; fair verdict withheld (§3) |

**Recommended next steps (WP-5.6):**
1. Rework `tests/fixtures/a1/self_questions.jsonl` `must_contain` to accept
   semantic paraphrase classes (or add per-probe `must_contain_any` groups).
2. Apply the F-WO8-14 past-session exemption to
   `detect_ungrounded_action_claims` in `src/lucca/core/coherence.py` (same
   artifact class; currently inflates ungrounded rates on BOTH models).
3. Investigate llama-server prompt-cache crash (§4).
4. Fix spoken-update template leak ("New understanding: <user question>").
5. Re-run full A1 battery on Gemma-4 after 1–4.
6. Re-run A1 battery on Bonsai 2 (with a Bonsai-compatible tool-call demux
   mode) for a fair rung C1b comparison.
