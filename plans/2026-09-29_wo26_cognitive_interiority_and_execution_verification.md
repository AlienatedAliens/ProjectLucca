# WO-26 — Cognitive Interiority, Acoustic Resilience & Autonomous Execution Verification

**Date:** 2026-09-29  
**Audience:** An implementing agent with no prior context. Every phase lists exact files, exact actions, **functional** acceptance criteria (behavioral, not just "suite green"), traps, and STOP gates. **STOP** means halt and report to the owner — do not improvise.  
**Golden rules:** One phase = one commit; tag layer in commit body (`[layer: memory]`, `[layer: routing]`, etc.); run `uv run python -m pytest -q -m "not tier2 and not hw and not soak"` after every step (baseline recorded in Phase 0; re-verify before your first commit); never edit `luccadocs/archive/`; never edit an existing migration file — new schema changes are new migration files only; never "fix forward" from a red suite — revert and re-read.  
**Provenance:** Follows the Senior Empirical Audit of Track 1 (`SPEC-BENCH-100-v1.0`), Track 2 (OpenAI GSM8K 1,319, HumanEval 164, Big-Bench Hard 1,000), live desktop voice companion telemetry from 2026-09-29, and external architectural reviewer ratification.

---

## Current State & Problem Analysis

1. **Interiority Deficit (Leaking Metacognition into Spoken TTS):**
   * At `12:07:41` in live desktop conversation, Lucca spoke aloud: `"[Lucca Revision] 💡 I've revised a belief I had — previously: I think you might be referring to how some systems get bogge..."`.
   * **Root Cause:** In `src/lucca/core/belief_service.py` (`maybe_speak_pending_updates`), unflagged belief revision sentences are enqueued directly into `self._orchestrator._speak_text()`. The system lacks a boundary between internal belief updating (metacognition) and social dialogue (utterance).
2. **Acoustic Brittleness & Runaway STT Stutter Loops:**
   * When spelling words (`S-I-L-O-G C-L-C-L-C-L...`), runaway acoustic feedback created an unbounded string of hyphenated characters (`Clclclclllcl...`), which `src/lucca/core/text_utils.py` assembled into a 100-character garbage token and committed to memory.
   * Additionally, speech recognition errors (*"fish and ship"* $\to$ "fish and chips", *"the dark"* $\to$ "the dock") are treated with literal rigidity because the model lacks acoustic uncertainty awareness.
3. **Latency Bias & Slang Confabulation (Tool Inertia):**
   * In live conversation, the 400ms latency of raw weights out-competed tool calling. Asked about the Australian shark term *"flake"*, Lucca hallucinated that flake was a Filipino dish of milkfish and rice rather than executing a 2-second background web search.
4. **Abstract Timezone Arithmetic Drift:**
   * SPEC-100 `CAT01-01` and live desktop conversation both demonstrated timezone arithmetic failure: Lucca claimed UTC+8 was Australian Eastern Standard Time (AEST is UTC+10; AWST/Perth is UTC+8).
5. **Zero-Shot Code Synthesis Fragility:**
   * In HumanEval, 5 of the 7 failures (`HumanEval/101` trailing comma, `103` odd floor vs round, `115` row constraint, `116` negative number bit-count, `145` negative sign sum) were boundary slips where pre-flight execution against provided docstring examples would have caught and corrected the bug before user emission.
6. **Intermediate Scratchpad Token Starvation:**
   * In BBH Geometric Shapes and SPEC `CAT10-04`, the model spent its generation token budget emitting 250+ tokens of intermediate scratchpads, resulting in cut-off derivations or empty replies.
7. **Under-Specified Requirement Ambiguity:**
   * 42.9% of GSM8K misses stemmed from unstated author assumptions (simple vs. compound interest, grocery vs. delivery fee).

---

## Phase 0 — Baseline Audit & Pinned Test Suite Recon

**Goal:** Establish verified baseline state across the test suite, pin the exact failing tests by test ID, and reproduce the voice defects.

**Manifest:**
- Run pytest baseline: `uv run python -m pytest -q -m "not tier2 and not hw and not soak"`
- **Pinned Known Baseline Failures (9 total):**
  1. `tests/test_packaging.py::test_frozen_binary_version_flag`
  2. `tests/test_persistent_rpc.py::test_persistent_worker_lifecycle`
  3. `tests/test_persistent_rpc.py::test_persistent_worker_proactive_recycling`
  4. `tests/test_persistent_rpc.py::test_persistent_worker_timeout_recovery`
  5. `tests/test_persistent_rpc.py::test_persistent_worker_call_id_desync_guard`
  6. `tests/test_persistent_rpc.py::test_persistent_worker_thread_safety`
  7. `tests/test_persistent_rpc.py::test_persistent_worker_latency_collapse`
  8. `tests/test_persistent_rpc.py::test_prespawn_reaping_and_worker_recovery`
  9. `tests/test_rule_induction.py::test_live_induction_production_log_clusters_gt_zero`
  *(Note: Any failure outside these 9 pinned IDs in subsequent phases is treated as an immediate regression).*
- Verify reproduction of the TTS leak at `src/lucca/core/belief_service.py:177` (`maybe_speak_pending_updates`).
- Verify reproduction of the STT letter stutter in `src/lucca/core/text_utils.py:44` (`normalize_spelled_words`).

**Functional Acceptance:**
- Baseline test pass count recorded (**994 passed, 9 failed, 64 deselected**).
- Pinned failures documented.
- Live reproduction confirmed on both defects.

**STOP Gate 0:** Present Phase 0 baseline findings to the owner before modifying production code. **[COMPLETED & RATIFIED]**

---

## Phase 1 — WO-26a: The "Mind-Mouth" Interiority Barrier

**Goal:** Strictly isolate internal cognitive metacognition (belief revisions, memory extraction, supervisor state flips) from the conversational speech synthesis pipeline.

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `src/lucca/core/belief_service.py` | Sever the direct call to `_orchestrator._speak_text` inside `maybe_speak_pending_updates`. Route unflagged belief revisions exclusively to `logger.info("belief_revision_applied")`, the SQLite telemetry audit store, and `_publish_caption(source="system")`. Remove `self.pending_spoken_updates.append` from the spoken TTS queue. | `[layer: memory]` |
| `src/lucca/core/orchestrator.py` | Ensure `TurnTrace` and `_speak_text` strictly filter out any payload marked with `source="system"` or containing `[Lucca Revision]` tags. Spoken audio is restricted to user-directed conversational synthesis. | `[layer: speech]` |
| `tests/test_belief_interiority.py` (new) | Positive control: trigger an explicit contradiction ("I don't live in the US, I live in Japan") $\to$ assert paraconsistent belief table updates $\to$ assert `_speak_text` is NOT called with `[Lucca Revision]` $\to$ assert conversational reply discusses Japan naturally. Negative control: assert non-revision system events (e.g. background telemetry or watchdog alerts) also remain strictly out of the TTS queue. Sibling test: run an autobiographical fact update ("My preferred language is Python, not Rust") and assert zero TTS leakage. | `[layer: test]` |

**Functional Acceptance:**
- Contradictory user input updates paraconsistent memory cleanly in SQLite.
- Zero `[Lucca Revision]` tokens or belief logs enter Kokoro TTS.
- Non-revision system messages stay out of TTS.
- Suite returns green with zero regressions against the 9 pinned baseline failures.

**Traps:**
- **TRAP 1:** Do not silence the UI caption event bus. Visual debuggers and developer logs should still be able to display belief changes if configured—only the audio synthesis path (`_speak_text`) must be quarantined.
- **TRAP 2:** Do not delete belief revision logging; ensure structured logs (`logger.info("belief_revision_applied", ...)`) remain intact for auditability.

**STOP Gate 1:** Run targeted tests, run full test suite, verify 0 regressions, commit Phase 1 (`git commit -m "WO-26 Phase 1: strict mind-mouth interiority barrier isolating belief revisions from TTS"`), and report to owner.

---

## Phase 2 — WO-26b: ASR Stutter Compression & Acoustic Normalizer

**Goal:** Prevent runaway repetitive single-letter ASR stutter loops and provide acoustic charity for spoken food/idiom terms.

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `src/lucca/core/text_utils.py` | In `normalize_spelled_words`: (1) Add a deduplication cap on runaway single-letter repeats: collapse repetitive syllabic stutter loops ($>3$ identical cycles) before word assembly. (2) Limit assembled spelled words to valid dictionary lengths ($\le 25$ chars). Add context-bounded acoustic substitution heuristics (e.g. `\bfish and ship\b` $\to$ `fish and chips` when preceded or followed by food/seafood tokens). | `[layer: routing]` |
| `src/lucca/core/orchestrator.py` | Implement true cooperative cancellation: when a new PTT press arrives while a turn is active, signal an explicit cancellation event that terminates the in-flight LLM streaming request and drains the worker cleanly within 500ms without leaving orphan tokens in the new turn's context. | `[layer: orchestrator]` |
| `tests/test_acoustic_normalizer.py` (new) | Sibling tests: verify `"S-I-L-O-G C-L-C-L-C-L..."` $\to$ `"Silog"`; verify `"A-U-D-I-T T-T-T-T-T..."` $\to$ `"Audit"`; verify `"P-Y-T-H-O-N N-N-N..."` $\to$ `"Python"`. Verify rapid PTT press aborts in-flight turn without polluting subsequent turn context. | `[layer: test]` |

**Functional Acceptance:**
- Runaway microphone feedback loops do not produce garbage strings in prompt history.
- Rapid PTT presses cleanly cancel prior threads without `turn_thread_join_timeout` or context bleed.
- Suite returns green with zero regressions against baseline.

**Traps:**
- **TRAP 1:** Never perform naive global string replacements. Acoustic substitutions must be strictly bounded by phrase boundaries and contextual keywords (food/restaurant).
- **TRAP 2:** Ensure cancellation actually aborts the HTTP/socket generator to `llama-server`, not just a thread join wait.

**STOP Gate 2:** Run test suite, verify 0 regressions, commit Phase 2 (`git commit -m "WO-26 Phase 2: ASR stutter compression, cooperative turn cancellation, and acoustic normalization"`), and report to owner.

---

## Phase 3 — WO-26c: Epistemic Uncertainty Gating, Grounded Telemetry & Entity Filtering

**Goal:** Override the 400ms latency bias: prevent confabulation of unfamiliar cultural/culinary slang via conformal uncertainty gating and ground timezone math in Python's standard `zoneinfo` database.

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `src/lucca/core/cascade.py` | In `classify_epistemic_intent`: replace ad-hoc lexicons with **Generalized Conformal Uncertainty Gating**. If a query centers on a named entity or cultural/culinary term not found in verified memory AND model token confidence is low, classify as `requires_external_verification = True`, forcing Tier 2/Tier 3 tool dispatch before answering. | `[layer: routing]` |
| `src/lucca/sandbox/service.py` | In `sys_info`: replace hand-built UTC+8 table with Python standard library `zoneinfo` (IANA tz database). Perform offline local lookup of active system timezone, UTC offset, standard abbreviation, and DST status (<5ms latency). Ensure timezone queries in `cascade.py` explicitly route to `sys_info` rather than raw weights. | `[layer: tool]` |
| `src/lucca/sandbox/web_tool.py` | In `search_web`: add **Target Entity Snippet Filter**. When search results return, verify target entity presence using word-boundary matching. If absent, set `entity_absent_in_results = True`, prompting the model to state the absence rather than reciting adjacent names. | `[layer: tool]` |
| `tests/test_epistemic_slang_gating.py` (new) | Sibling tests: (1) Australian slang: "flake" and "witchetty grub" both force search rather than reflex confabulation. (2) Timezone: verify Perth/AWST, Manila/PST, Singapore/SGT resolved via `zoneinfo` with DST flags. (3) Entity filter: target present $\to$ flag False; target absent $\to$ flag True; target as substring (e.g. "ever" in "Beverly") $\to$ word boundary enforced. | `[layer: test]` |

**Functional Acceptance:**
- Unfamiliar cultural/culinary entities trigger external verification rather than reflex hallucinations.
- Timezone queries deterministically cite accurate `zoneinfo` metadata.
- Roster searches missing the subject state absence cleanly.

**Traps:**
- **TRAP 1:** Keep `sys_info` latency strictly $<5$ms (Class B SLA). `zoneinfo` is an offline local lookup, never an external HTTP request.
- **TRAP 2:** Everyday conversational chat must not falsely trigger search tools; conformal gating applies only when uncertainty on unrecognized entities is detected.

**STOP Gate 3:** Run test suite, verify 0 regressions, commit Phase 3 (`git commit -m "WO-26 Phase 3: conformal uncertainty slang gating, zoneinfo telemetry, and target entity filtering"`), and report to owner.

---

## Phase 4 — WO-26d: The Autonomous "Run-Before-You-Speak" Code Verification Loop

**Goal:** Eliminate zero-shot coding misses by executing an automated pre-flight assertion check against extracted spec docstrings in the Docker sandbox before emitting generated code.

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `src/lucca/sandbox/service.py` | Implement `preflight_verify_code(code: str, docstring_examples: list[str] | None = None) -> PreflightResult`: runs lightweight syntax compilation (`ast.parse`) and executes in Docker against extracted docstring test cases (`>>> func(...) == ...`) or basic sanity assertions. Returns `(success: bool, error_msg: str | None)`. Enforce 3.0s hard timeout with fail-open behavior. | `[layer: tool]` |
| `src/lucca/core/orchestrator.py` & `turn_pipeline.py` | In Tier 3 Code Synthesis: intercept synthesized code blocks before streaming. If `preflight_verify_code` fails with `AssertionError` or syntax error, feed the failure back to the model for an immediate 1-shot self-repair turn before presenting the solution to the user. | `[layer: orchestrator]` |
| `src/lucca/brain/prompt_builder.py` | **Batched Prompt-Contract Update (Phases 4 & 5 combined):** (1) Coding contract: instruct running provided docstring examples, testing empty/negative inputs, and preferring robust numerical primitives (`scipy.optimize.bisect`, `math.isclose`, `decimal.Decimal`). (2) Defensive engineering contract: on ambiguous business/financial logic, state operational assumption on line 1. Measure and report token delta against 16K budget. | `[layer: prompt]` |
| `tests/test_code_preflight.py` (new) | Test pre-flight loop on docstring assertions: verify `AssertionError` triggers 1-shot self-repair. Evaluate on the 7 HumanEval failure tasks (`32`, `101`, `103`, `115`, `116`, `132`, `145`) and sibling tasks from HumanEval+. Report before/after ablation (preflight on vs. off). | `[layer: test]` |

**Functional Acceptance:**
- Generated Python code is pre-tested against spec docstring assertions in Docker.
- Boundary bugs (trailing comma, negative integers) self-correct autonomously in Docker.
- System prompt prefix token count delta measured and documented against ADR-009.
- Fail-open honored: 3.0s timeout returns code with warning rather than hanging.

**Traps:**
- **TRAP 1:** Do not rely solely on model-written self-tests. Preflight must prioritize assertions extracted directly from docstring examples or user prompt to test against author intent.
- **TRAP 2:** Ensure `scipy.optimize.bisect` and standard library primitives are used; avoid non-existent APIs.

**STOP Gate 4:** Run test suite, verify the 7 remediated code challenges and sibling problems pass, report preflight on/off ablation, commit Phase 4 (`git commit -m "WO-26 Phase 4: autonomous Docker pre-flight verification loop and batched prompt contract"`), and report to owner.

---

## Phase 5 — WO-26e: Decoupled Scratchpad & Defensive Disambiguation

**Goal:** Prevent token starvation from intermediate scratchpads and establish defensive assumption-stating on open-ended human prompts without altering static prompt prefixes twice.

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `src/lucca/core/turn_pipeline.py` | Decouple intermediate tool deliberation: intermediate scratchpads (e.g. coordinate math, long tool outputs) execute in an isolated sub-turn buffer with independent token limits. Only the clean synthesized outcome is injected into the final conversational turn context. | `[layer: orchestrator]` |
| `src/lucca/core/orchestrator.py` | Add **Non-Empty Synthesis Guardrail**: If tool execution succeeds but the assistant generation produces an empty or whitespace-only response, trigger a single fallback synthesis: *"Summarize the tool output for the user."* | `[layer: orchestrator]` |
| `tests/test_defensive_disambiguation.py` (new) | Sibling tests on financial/rounding ambiguity: verify that on unseen interest/fee/rounding problems, an assumption is explicitly stated on line 1. (Test does NOT assert matching a single arbitrary key; asserts assumption presence). Categorize audited GSM8K misses honestly as "ambiguous" vs. "misread". | `[layer: test]` |

**Functional Acceptance:**
- Heavy tool execution never truncates or starves final user responses.
- Ambiguous financial word problems state their assumptions defensively on line 1.
- Zero empty responses emitted following successful tool calls.

**Traps:**
- **TRAP 1:** Do not edit the system prompt in Phase 5—prompt edits were batched into Phase 4 to maintain ADR-009 prefix cache byte-identity.
- **TRAP 2:** Distinguish genuine author ambiguity from model misreading in audits.

**STOP Gate 5:** Run test suite, verify 0 regressions, commit Phase 5 (`git commit -m "WO-26 Phase 5: decoupled scratchpads, non-empty guardrails, and defensive disambiguation tests"`), and report to owner.

---

## Phase 6 — WO-26f: Full Acceptance Battery & Modern Benchmark Hand-off

**Goal:** Run full regression gates across SPEC-100, bare-weights BBH, and live voice chat, certifying the system is ready for Track 3 (Modern 2024 Benchmarks).

**Manifest:**
| File | Action | Layer |
|---|---|---|
| `scripts/run_wo26_acceptance_battery.py` (new) | Consolidated runner executing: (1) Unit test regression gate, (2) The 7 remediated HumanEval tasks + siblings, (3) Live slang lookup verification, (4) Timezone precision test via `zoneinfo`, (5) Speech interiority isolation test. | `[layer: runner]` |
| `compound_benchmark_audit_review.md` | Fix numerical slip: correct GSM8K runtime from 4.8s/task to 2.0s/task ($2,628.4\text{s} / 1,319\text{ tasks} = 1.99\text{s/task}$). | `[layer: doc]` |
| `luccadocs/specs/WO26_ACCEPTANCE_REPORT.md` (new) | Final audit report documenting before/after metrics and SPEC-100 regression baseline. | `[layer: doc]` |

**Functional Acceptance:**
- 100% of acceptance battery tests pass.
- Bare-weights BBH and SPEC-100 confirmed stable without negative drift.
- Full pytest suite green (0 regressions against the 9 pinned baseline failures).
- Ready for Track 3: Modern 2024 Benchmarks (Apple's GSM-Symbolic, HumanEvalPlus, Math500).

**STOP Gate 6:** Present final acceptance report to owner for sign-off.

---

## Execution Order & Sign-off Table

```
Phase 0 (Recon & Pinned Audit) [DONE]
  → Phase 1 (Mind-Mouth Interiority Barrier)
  → Phase 2 (ASR Stutter Compression & Acoustic Normalizer)
  → Phase 3 (Epistemic Slang Gating & Grounded Telemetry)
  → Phase 4 (Docker Pre-Flight Code Loop & Batched Prompt Contract)
  → Phase 5 (Decoupled Scratchpad & Defensive Disambiguation)
  → Phase 6 (Acceptance Battery & Modern Benchmark Hand-off)
```

| Phase | Description | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|---|
| **Phase 0** | Baseline Audit & Pinned Test Recon | Pinned (9 known) | Antigravity | Owner | **PASS** | 2026-09-29 |
| **Phase 1** | Mind-Mouth Interiority Barrier | 0eed39b | Antigravity | Owner | **PASS** | 2026-09-29 |
| **Phase 2** | ASR Stutter & Acoustic Normalizer | fe6a1b7 | Antigravity | Owner | **PASS** | 2026-09-29 |
| **Phase 3** | Epistemic Slang & Timezone Grounding | 0e223c3 | Antigravity | Owner | **PASS** | 2026-09-29 |
| **Phase 4** | Docker Pre-Flight Loop & Batched Prompt | 70de7db | Antigravity | Owner | **PASS** | 2026-09-29 |
| **Phase 5** | Decoupled Scratchpad & Disambiguation | f1bc635 | Antigravity | Owner | **PASS** | 2026-09-29 |
| **Phase 6** | Acceptance Battery & Sign-Off | 84b942c | Antigravity | Owner | **PASS** | 2026-09-30 |
