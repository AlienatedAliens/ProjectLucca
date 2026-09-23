# 05 — Test-Strategy Gap Analysis: A1 Self-Model, Seeded RAG, FULL_LOOP, Research

**Author:** Zoo (Fable 5.1), reviewer role
**Date:** 2026-09-21T17:00Z
**Baseline commit:** `9506ced` (Rung A1 delivered)
**Trigger:** Owner question after A1 sign-off — *"Do we actually have live tests and fuzz tests for all of the new systems? Should we not be testing seeded RAG, multi-step thinking, research abilities? Where are we now?"*
**Companion document:** [`docs/WORK_ORDER_gemini_8_test_hardening.md`](../WORK_ORDER_gemini_8_test_hardening.md) — the executable work order derived from this analysis.

Method: every claim below is backed by a file:line reference or a command that was run on 2026-09-21. No coverage number here is estimated.

---

## 1. Headline answer

**No.** The systems delivered in L2 and A1 are covered at **T1 (unit, fake-backed) only**. There is no T3 live-hardware coverage and no property/fuzz coverage for anything added in A1. Seeded-RAG recall, multi-step FULL_LOOP with the real model, and live research (`search_web → fetch_url → narrate`) have **zero** gated tests. The A1 §3 acceptance metrics (Wilson LB ≥ 0.90, ≤ 2 % ungrounded claims) were computed against scripted `FakeLLM` output and therefore do **not** satisfy the ratified spec, which states those metrics "are the A1 acceptance tests" ([spec §7 row 1](../specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md:107)).

Beyond test coverage, the analysis surfaced **two functional gaps** that any live test would have exposed immediately (F-TS-03, F-TS-04). A1 should be re-labelled **"implemented, T1-verified, not ratified"** until Work Order #8 closes.

---

## 2. What the reported "520 passed" actually exercised

[`pyproject.toml:109`](../../pyproject.toml:109):

```toml
addopts = "-m 'not hw and not soak and not tier2'"
markers = ["hw: ...", "soak: ...", "tier2: ..."]
```

Consequences:

| Tier | Command | 2026-09-21 result | Notes |
|---|---|---|---|
| T0 static | `uv run ruff check/format`, `tests/test_static_gates.py` | green | Zero-`Any` gate intact |
| T1 unit + property | `uv run pytest` (default) | **520 passed** | This is the number in the A1 handover |
| T2 fake-backed integration | `uv run pytest -m tier2` | **6 passed** (run by reviewer) | Not run by the A1 session |
| T3 live hardware | `uv run pytest -m hw` | **5 collected, 0 for A1/L2**; `llama-server` **not running** (`curl :8080/health` → exit 7; dGPU 0 MiB used) | Nothing live was executed for A1 |
| T4 soak | `uv run pytest -m soak` | **0 tests exist** | Marker registered, never used |

The A1 session also ran `uv run pytest -m "not live_hardware"`. **`live_hardware` is not a registered marker** — the filter was a no-op that produced the same T1 set. The handover's "Full Regression Test Suite" row is therefore T1 only.

---

## 3. Findings

Severity: **S1** blocks ratification · **S2** must close before the next ladder rung · **S3** hygiene.

### F-TS-01 (S2) — Test-tier reporting is misleading by default
- **Evidence:** §2 above; [`docs/HANDOVER_gemini_7_a1_complete.md`](../HANDOVER_gemini_7_a1_complete.md) reports "Full Regression Test Suite … 520 PASSED" without tier qualification.
- **Gap:** No CI-style tier table is produced; phantom marker names pass silently (`pytest` warns on unknown `-m` expressions only under `--strict-markers`).
- **Required:** `--strict-markers` in `addopts`; every handover carries a per-tier table with the exact command and count; add `net` marker for tests requiring egress.

### F-TS-02 (S1) — A1 §3 metrics ratified against synthetic narration
- **Evidence:** [`tests/test_a1_autobiographical_memory.py:47-48`](../../tests/test_a1_autobiographical_memory.py:47) imports `FakeLLM`/`FakeTTS`; no `hw` marker anywhere in the file.
- **Spec requirement:** §3.1 "N ≥ 50 self-questions … Wilson LB ≥ 0.90" measures *her* answers, i.e. Gemma-4 narration conditioned on Substrate 7 evidence. §3.3 "≤ 2 % ungrounded action claims" measures *her* spoken claims vs receipts. A `FakeLLM` that emits the expected string cannot fail these tests — they verify the plumbing, not the property.
- **Skill rule violated:** *"Synthetic data never satisfies a human gate."*
- **Required:** T3 live pack (WO-8 WP-3) that runs the 50-probe battery and the coherence battery against live `llama-server` and records Wilson intervals into `logs/test_reports/`.

### F-TS-03 (S1) — Reflection engine and belief formation are not wired into the runtime
- **Evidence:**
  - `ReflectionEngine` is constructed only in [`src/lucca/admin.py:597`](../../src/lucca/admin.py:597) and [`src/lucca/ui/settings_dialog.py:426`](../../src/lucca/ui/settings_dialog.py:426). Zero references in `orchestrator.py`, `main.py`, or any supervisor/scheduler.
  - `Provenance.ASSISTANT_BELIEF` payloads are created **only inside** [`reflection.py:190`](../../src/lucca/memory/reflection.py:190) and [`:275`](../../src/lucca/memory/reflection.py:275) (i.e. during a revision). No runtime path forms an *initial* belief. The Individuation goal (§3.2) therefore has no production data source — there is nothing to be consistent about.
  - `detect_and_handle_contradiction()` returns a `spoken_update` string ([`reflection.py:205`](../../src/lucca/memory/reflection.py:205)); no caller speaks it. Spec §7 row 4 mandates "spoken once at the next natural turn boundary … so nothing changes silently."
  - Nightly roll-up exists as `lucca-admin memory rollup` only; no scheduler.
- **Gap:** The revision pipeline is reachable from the operator CLI and Studio but is dead in the companion loop. A live test that seeds a belief, then delivers a `USER_EXPLICIT` correction via a real turn and asks "what do you believe about X now?" would fail today.
- **Required:** WO-8 WP-2 (minimal wiring + tests). This is a code change, not only a test change — flagged explicitly so the owner can accept or reject scope.

### F-TS-04 (S1) — Functional-coherence monitor is a weak verb regex
- **Evidence:** [`orchestrator.py:818-831`](../../src/lucca/core/orchestrator.py:818):
  ```python
  pattern = r"\bi (?:have )?(?:saved|wrote|written|updated|launched|opened|ran|created|deleted)\b"
  claimed_action = bool(re.search(pattern, reply_low))
  if claimed_action and not tool_calls: return "…breach…"
  ```
- **False negatives (spec-relevant):** the check only tests `not tool_calls`. A turn where `write_file` **executed and failed** (`ok=False`) while narration says "I saved it" is exactly the §3.3 negative case ("a narrated action with no receipt … recorded as a coherence breach") and is **not detected**. Verb/tool mismatch ("I launched Notepad" after a `read_file` receipt) is not detected. Passive/gerund claims ("your note is saved", "launching it now", "done — file written") are not detected.
- **False positives:** "I ran into a problem", "I have written poetry before", "I opened up to you about that" all trigger a breach commit, polluting her autobiographical record with fake breaches (which then carry +0.3 importance per §7 row 3).
- **No fuzzing:** zero `hypothesis` strategies target this function.
- **Required:** receipt-aware checker (verb-class → tool-family map; requires a **successful** receipt in the same trace) + adversarial narration corpus + hypothesis fuzz (WO-8 WP-1, WP-2).

### F-TS-05 (S2) — No property/fuzz coverage of the A1 memory layer
- **Evidence:** `hypothesis` is used in 8 files (`test_scheme`, `test_sandbox`, `test_ring_buffer`, `test_provenance`, `test_memory_db`, `test_ipc_codec`, `test_chunker`, `test_extended_fuzzing`). None targets: the `mem_bi_eligible` trigger + `grounding_eligible` partition; the 5-flag decision in [`reflection.py:126-154`](../../src/lucca/memory/reflection.py:126); the review-queue state machine (queue → approve/reject, double-decide, decide-after-supersede); Substrate 7 Belnap isolation in [`cascade.py:947`](../../src/lucca/core/cascade.py:947); importance arithmetic (clamping at 1.0, decay interaction, roll-up thresholds at exactly 0.2 / 30 d).
- **Required:** WO-8 WP-1.

### F-TS-06 (S1) — Seeded RAG has no end-to-end recall/abstention test
- **Evidence:** [`tests/test_memory_retrieval_prioritization.py`](../../tests/test_memory_retrieval_prioritization.py:11) has one test of the context formatter's ordering. [`test_memory_db.py:838`](../../tests/test_memory_db.py:838) fuzzes FTS5 query robustness. [`test_epistemic_cascade.py`](../../tests/test_epistemic_cascade.py) is fake-backed. No test: seeds N signed memories (+ distractors) → runs a real or fake turn → asserts the prompt (T2) / narration (T3) contains the right memory and **abstains** when the fact is absent.
- **Why it matters:** D-ARCH-06 fast-path context sync and D-MEM-03 prioritisation are the mechanism by which A1's "what were we doing last time?" works. Their interaction with the new `grounding_eligible=0` rows (which must appear as *recollection*, not *evidence*) is untested end-to-end.
- **Required:** WO-8 WP-4 — a seeded corpus fixture and both a T2 (FakeLLM captures prompt) and T3 (live narration, Wilson interval) variant.

### F-TS-07 (S1) — Multi-step FULL_LOOP and research abilities untested against the real model and real network
- **Evidence:** [`tests/test_tool_chaining.py:53-136`](../../tests/test_tool_chaining.py:53) covers `search_web → fetch_url → narrate`, max-rounds boundary, forced synthesis and SequenceGuard — every round scripted by `FakeLLM`, `search_web`/`fetch_url` monkeypatched. [`test_batch2_execution.py:150`](../../tests/test_batch2_execution.py:150) covers verbal thinking cues, fake-backed. The only live tool test, [`test_phase1_live_hw.py:114`](../../tests/test_phase1_live_hw.py:114), is a **single-round** `calc_01.wav` tool call. Real search providers are exercised only by ungated scripts (`scripts/probe_search_providers.py`, `scripts/test_ddgs_live.py`, `scripts/check_*.py`) with no assertions and no report artefact.
- **Unverified live properties:** that Gemma-4 actually *chooses* a second round after seeing tool messages; that the M=3 cap and forced final synthesis hold with real token streams; that `enable_thinking=false` narration stays grounded (D-BRAIN-04) when the fetched body is long; that verbal cues (D-BRAIN-03) are emitted between real rounds; that in-container `fetch_url` obeys egress rules while the model drives it.
- **Required:** WO-8 WP-5 (`hw` + `net` markers).

### F-TS-08 (S2) — Soak tier is empty
- **Evidence:** `soak` marker registered; `grep -r "mark.soak" tests/` → 0.
- **Why it matters for A1:** every turn now commits an `ASSISTANT_UTTERANCE` row and possibly a `COHERENCE_BREACH`. Unbounded growth of `memories`/`provenance_envelopes`, WAL size, FTS index, and retrieval p95 under thousands of turns has never been measured. The roll-up is the intended pressure valve and has never run against a large corpus.
- **Required:** WO-8 WP-6.

### F-TS-09 (S3) — Environment check will not be green
- **Evidence (2026-09-21):** `wsl -d Ubuntu -- docker info` succeeded (Docker CE 29.8.1) but WSL emitted: `Unknown key 'wsl2.pageReporting'`, `'wsl2.autoMemoryReclaim'`, `'wsl2.sparseVhd'` in `C:\Users\seatr\.wslconfig:5-7`, and `Expected " in /etc/wsl.conf:9`. Those three keys belong under `[experimental]`, not `[wsl2]`; the `wsl.conf` line has an unquoted value.
- **Required:** WO-8 WP-0.

---

## 4. Coverage matrix (2026-09-21)

| Capability | T1 unit | T1 property/fuzz | T2 fake integration | T3 live hw | T4 soak |
|---|---|---|---|---|---|
| Provenance gate / signers (pre-A1) | ✅ | ✅ `test_provenance` | ✅ | — | — |
| A1 signers, `grounding_eligible`, trigger | ✅ | ❌ | — | ❌ | ❌ |
| ReflectionEngine 5-flag gating | ✅ | ❌ | ❌ (not wired) | ❌ | ❌ |
| Review queue CLI/UI | ✅ CLI | ❌ | — | — | — |
| Substrate 7 SELF_HISTORY + abstention | ✅ | ❌ | ❌ | ❌ | — |
| Coherence breach monitor | ✅ (happy path) | ❌ | ❌ | ❌ | — |
| Seeded RAG recall / abstention | ❌ | FTS only | ❌ | ❌ | ❌ |
| FULL_LOOP M=3 chaining + verbal cues | ✅ | ❌ | ✅ (fake) | ❌ single-round only | ❌ |
| Research: real `search_web`/`fetch_url` | ❌ mocked | URL-scheme fuzz | ❌ | ❌ (scripts only) | — |
| Sandbox egress / RPC | ✅ | ✅ | ✅ | ✅ `test_phase2_live_hw` | — |
| Voice turn TTFT / barge-in | — | — | — | ✅ `test_phase1_live_hw` | — |
| Frozen regression (100 scenarios) | ✅ | — | — | — | — |

---

## 5. Target test architecture (what "done" looks like)

1. **T1 property layer** — `hypothesis` strategies over A1 state: envelopes × eligibility × supersession chains; flag-decision table; review-queue transitions; narration corpus for the coherence checker. Runs in the default `pytest` set.
2. **T2 seeded harness** — a reusable fixture `seeded_memory_corpus` (≥ 40 signed facts, ≥ 20 distractors, ≥ 10 "never happened" probes) driving an `Orchestrator` with `FakeLLM` that *records* the built prompt. Asserts retrieval, eligibility framing (evidence vs recollection), and abstention text. Marked `tier2`.
3. **T3 live pack** — `tests/test_a1_live_hw.py` and `tests/test_research_live_hw.py`, marked `hw` (+ `net` where egress is needed). Same corpus and probe sets as T2, but the assertion is on real Gemma-4 narration, with Wilson 95 % intervals written to `logs/test_reports/a1_live_<ts>.json`. Thresholds come from the spec and are **never** edited to pass.
4. **T4 soak** — 2 000-turn fake-backed endurance (RSS, WAL, FTS, retrieval p95, roll-up effect) plus a 60-minute live variant.
5. **Reporting** — every handover carries the tier table from §2 with real counts per command; `--strict-markers` enforced.

---

## 6. Disposition

- A1 status changed from "Complete & Verified" to **"Implemented — T1/T2 green — T3/T4 not attempted — 2 functional gaps (F-TS-03, F-TS-04)"**.
- Ladder does **not** advance to L3 until Work Order #8 closes and this reviewer signs the resulting handover.
- All findings are transcribed as work packages in [`docs/WORK_ORDER_gemini_8_test_hardening.md`](../WORK_ORDER_gemini_8_test_hardening.md).
