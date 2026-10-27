# Work Order 38: Paper V2 Epistemic Hardening — Statistical Relabel, Corroboration-Gated Admission, GBNF Action Channel Verification, and Pre-Registered v2 Arms

```yaml
doc_status: canonical
as_of: 2026-10-26
target_release: v1.48.0 / WO-38
supersedes: []
superseded_by: []
verification: code-cited
```

**Target Release:** Project Lucca `v1.48.0`
**Audience:** An implementing agent with no prior context. Every phase lists exact files, exact actions, functional acceptance criteria, traps, and STOP gates. **STOP** means halt and report — do not improvise.
**Golden rules:** One phase = one commit. Run `uv run pytest -q -m "not tier2 and not hw and not soak"` after every step (baseline: record the actual count you see before your first commit). Never edit `luccadocs/archive/` or `plans/archive/`. Never edit an existing migration file. Never "fix forward" from a red suite — revert and re-read. Never alter frozen measurements, prereg-v1 tags, or raw benchmark logs (Rule 08). AI-assisted commits must carry the disclosure line (Rule 08).

**Provenance:** WO-36 PASS (v1.46.5); WO-37 in progress. This work order was opened after a full editorial review of `papers/01_memory_poisoning_ablation/` and `papers/02_deontic_supervision_evasion/` (post-commit `47f67e8`). The review found: (a) a statistical test-name error, (b) two papers whose negative results map to already-built but unwired defenses, and (c) publication-blocking editorial gaps. Neither paper is venue-published; the only public artifact is the umbrella Zenodo preprint `10.5281/zenodo.23649049` (published 2026-10-26, license slug `apgl-v3`, likely a typo of `agpl-3.0`).

---

## Current State (verified 2026-10-26)

1. **McNemar test-name error (both papers).** Paper 1 [`main.tex`](../papers/01_memory_poisoning_ablation/main.tex) line ~119 and line ~126, and [`paper.html`](../papers/01_memory_poisoning_ablation/paper.html) lines ~263 and ~270, report "exact McNemar test" with `p = 6.98 × 10⁻¹⁰`. The exact binomial McNemar for discordant pairs `b=40, c=0` gives `p = 2 × 0.5⁴⁰ ≈ 1.82 × 10⁻¹²`. The reported `6.98e-10` corresponds to the **continuity-corrected McNemar chi-square**: `(40−1)²/40 = 38.03 → z = 6.17 → p ≈ 6.98e-10`. Same conclusion, wrong test name.
2. **Uncorroborated `USER_EXPLICIT` admission (Cohort C failure, 30/30 absorption).** [`store.py:118`](../src/lucca/memory/store.py#L118) and [`manager.py:179`](../src/lucca/memory/manager.py#L179) set `grounding_eligible = 1` for every provenance in `GROUNDING_ELIGIBLE` ([`schemas.py:249`](../src/lucca/core/schemas.py#L249)) purely by provenance class. The corroboration engine ([`corroboration.py`](../src/lucca/core/corroboration.py), Q2 "Is the claim corroborated by an independent grounding-eligible fact?") exists but is **not** consulted at memory admission.
3. **GBNF action channel: built, load path unverified in production narration.** [`turn_pipeline.py:731`](../src/lucca/turn_pipeline.py#L731) `get_action_claim_grammar()` loads [`config/grammars/action_claim.gbnf`](../config/grammars/action_claim.gbnf), but no phase has verified the grammar is actually passed to `llama-server` sampling on the companion narration path. The GrammarConstrainedActionClaimSupervisor ([`output_supervisor.py:497`](../src/lucca/sandbox/output_supervisor.py#L497)) and post-turn NLI receipt entailment ([`coherence.py:416`](../src/lucca/core/coherence.py#L416), SPIKE-A) exist; Paper 2's Arm 1 measured prompt-only SOAC (13.3% prose leakage), never the GBNF arm.
4. **Pre-registration:** tags `prereg-poisoning-v1` and `prereg-supervision-v1` are intact and frozen. v2 protocols must be new tags registered **before** any new measurement.
5. **Harnesses:** confabulation/poisoning battery [`scripts/bench_confabulation_battery.py`](../scripts/bench_confabulation_battery.py); supervision battery [`scripts/run_action_hallucination_eval.py`](../scripts/run_action_hallucination_eval.py) (pre-registered protocol doc exists); NLI cross-encoder grader in [`src/lucca/senses/verifier.py`](../src/lucca/senses/verifier.py).

---

## Phase 0 — Statistical Relabel (Paper 1, tex + html)

**Goal:** Correct the test name without touching any reported p-value. This is a reporting correction, not a data modification: the contingency table (`b=40, c=0`) and the numeric `p = 6.98 × 10⁻¹⁰` stand unchanged.

**Manifest:**

| File | Action |
|---|---|
| `papers/01_memory_poisoning_ablation/main.tex` | Line ~119: "A two-sided exact McNemar test" → "A two-sided continuity-corrected McNemar chi-square test". Add one sentence after Eq.: "The uncorrected exact-binomial McNemar value is p = 2 × 0.5⁴⁰ ≈ 1.82 × 10⁻¹²." Line ~126: "(p = 6.98 × 10⁻¹⁰, exact McNemar)" → "(p = 6.98 × 10⁻¹⁰, continuity-corrected McNemar chi-square)". |
| `papers/01_memory_poisoning_ablation/paper.html` | Mirror both edits (lines ~263, ~270). |
| `papers/02_deontic_supervision_evasion/main.tex` + `.html` | No McNemar p-value in body — only bibliography entry; do NOT touch. |

**Functional acceptance:** grep both files for "exact McNemar" returns 0 hits outside the reference-list bibitem; the exact-binomial sentence is present; all measured values unchanged (`git diff` shows only test-name strings and the added sentence).

**Traps:**
- **TRAP 1:** Do not recompute or "fix" any reported p-value. Reported numbers are frozen measurements (Rule 08). Only the test *name* changes.
- **TRAP 2:** The abstract mentions exact McNemar too — check the abstract sentence in both tex and html and relabel consistently.

**STOP gate:** If `git diff` shows any numeric change, revert and re-read.

---

## Phase 1 — Editorial Completeness (both papers)

**Goal:** Close the submission-blocking editorial gaps: Limitations section, external related work, real author identity, abstract/conclusion alignment for Paper 2.

**Manifest:**

| File | Action |
|---|---|
| `papers/01_memory_poisoning_ablation/main.tex` + `.html` | Add `\section{Limitations}` (single model gemma-4-26B-A4B, greedy T=0.0, seed 42, n per cohort ≤ 40, single-session-pair protocol, regex/CAS primary grader inherits the regex-evasion fragility documented in the companion supervision study — mitigated by κ=0.7683 dual grading). Add ≥4 external bibitems (memory poisoning / RAG contamination / agent memory frameworks — cite real published works only; verify each DOI/arXiv id live before writing it). Replace "Project Lucca Research Consortium" author with a real name + ORCID; consortium becomes an acknowledgement line. |
| `papers/02_deontic_supervision_evasion/main.tex` + `.html` | Same Limitations block (adds: SOAC sensitivity 2/16; SOAC introduced 4/30 false action frames where strict regex had 0/30). Abstract must state the latency and channel-authority wins as SOAC's demonstrated gains, not "resolves the trade-off". Same author fix. |
| `docs/index.html` | Keep blurbs consistent with reworded abstracts. |

**Functional acceptance:** both papers contain a Limitations section; author block is a natural person; grep shows no "Research Consortium" in author position; external bibitem count ≥ 4 per paper, every DOI/arXiv id independently reachable (record curl HTTP 200 in commit message).

**Traps:**
- **TRAP 3:** Never invent citations. Every new bibitem must be fetched and title-matched live. If a claimed reference 404s, drop it.
- **TRAP 4:** Keep the pre-registered hypotheses H1–H4 wording intact; Limitations must not contradict the abstract.

**STOP gate:** If any proposed citation cannot be verified live, STOP and report — do not substitute an unverified reference.

---

## Phase 2 — Corroboration-Gated USER_EXPLICIT Admission (flag-gated)

**Goal:** Un-verified user assertions stop entering Belnap grounding context by provenance class alone. Flag-off behavior must be byte-identical to v1 (Cohort C reproduction stays valid).

**Rationale:** Paper 1 Cohort C shows 100% absorption because `USER_EXPLICIT` → grounding eligibility is unconditional ([`store.py:118`](../src/lucca/memory/store.py#L118)). The corroboration Q2 lookup ([`corroboration.py`](../src/lucca/core/corroboration.py)) already answers "corroborated by an independent grounding-eligible fact?" — wire it into admission.

**Manifest:**

| File | Action |
|---|---|
| `src/lucca/core/config.py` | Add `memory.user_explicit_requires_corroboration: bool = False` to the memory settings block. |
| `src/lucca/memory/store.py` | At the `grounding_eligible` decision (~line 118): if flag ON **and** `signed_payload.provenance == Provenance.USER_EXPLICIT`, run a corroboration lookup against the entry content; if not corroborated, write `grounding_eligible = 0` (memory-eligible stays 1 — autobiographical recall preserved). Log `user_explicit_uncorroborated_belnap_deferred`. |
| `src/lucca/memory/manager.py` | Same gate at both write paths (~lines 179 and 280). |
| `tests/test_corroboration_gated_admission.py` (new) | Unit tests with the flag ON/OFF, using `FixedClock` and a temp DB; no live LLM. |

**Functional acceptance:**
- Flag OFF: `USER_EXPLICIT` facts remain `grounding_eligible = 1` (existing suite stays green, zero behavior change).
- Flag ON, no corroborating fact: stored row has `grounding_eligible = 0` but remains retrievable via the autobiographical path; `ProvenanceGate` fusion queries ([`gate.py:212`](../src/lucca/memory/gate.py#L212), `grounding_eligible = 1` filter) exclude it.
- Flag ON, corroborated (an existing `TOOL_VERIFIED` fact matches): `grounding_eligible = 1`.
- Suite green vs baseline. `ruff check` clean. Zero `Any`.

**Traps:**
- **TRAP 5:** Do NOT change `GROUNDING_ELIGIBLE` in [`schemas.py:249`](../src/lucca/core/schemas.py#L249). The gate class membership is the frozen v1 invariant; the corroboration check is a runtime downgrade, flag-gated.
- **TRAP 6:** `USER_DERIVED` facts already passed transcript grounding ([`extraction.py:48`](../src/lucca/memory/extraction.py#L48)) — do not downgrade them.
- **TRAP 7:** Corroboration lookup must be non-blocking and safe: on exception, log and fall back to flag-OFF behavior (fail-open on the flag, never crash admission).
- **TRAP 8:** Never auto-promote the flag to default ON (Rule 08: no autonomous safety-gate changes). Default stays `False`; enabling is an operator config decision.

**STOP gate:** Any existing test that fails under flag-OFF means a behavior leak — revert the phase.

---

## Phase 3 — GBNF Action-Channel Production Verification

**Status (2026-10-27):** COMPLETE. Audit confirmed the gap: the grammar text was loaded and passed, but `Orchestrator._stream_llm_speech` drops the grammar on any round where tools are active (`grammar=grammar if not round_tools else None`), and the ACT_THEN_NARRATE call site passed `tools=None` → full tool list → the grammar never reached the llama-server payload (the measured Paper 2 Arm 1 prompt-only path). Fixed behind `llm.action_claim_grammar_enabled: bool = False` in [`src/lucca/core/config.py`](../src/lucca/core/config.py): when ON, [`turn_pipeline.py`](../src/lucca/core/turn_pipeline.py) `narration_grammar_request()` sends an empty tool list so the grammar survives to the sampling payload (LLMClient sends grammar XOR tools); OFF stays byte-identical v1. STOP gate cleared: live llama-server returned HTTP 200 accepting a `grammar` field on `/v1/chat/completions`. Verified by [`tests/test_action_claim_grammar_wiring.py`](../tests/test_action_claim_grammar_wiring.py) (8 tests: pipeline decision, orchestrator kwarg drop/delivery, payload grammar XOR tools, supervisor receipt rejection/pass); regression suite green (one unrelated flaky 300 ms wall-clock timing test passed on isolated re-run).

**Goal:** Prove (or fix) that `action_claim.gbnf` is actually applied at decode time on the narration channel, and that receipt-less action claims are rejected end-to-end. Paper 2 Arm 5 depends on this being real.

**Manifest:**

| File | Action |
|---|---|
| `src/lucca/turn_pipeline.py` | Audit: trace `get_action_claim_grammar()` (~line 731) to the sampling-request construction in the brain client. If the grammar is loaded but never sent, wire it into the narration completion request behind `brain.action_claim_grammar_enabled: bool = False` (config.py). |
| `src/lucca/sandbox/output_supervisor.py` | Unit-test the GrammarConstrainedActionClaimSupervisor (~line 497): `[ACTION: send ...]` with no matching `ToolReceipt` → rejected with hedge rewrite; with receipt → passed. |
| `tests/test_action_claim_grammar_wiring.py` (new) | Assert the sampling request payload contains the grammar field when enabled, absent when disabled. |

**Functional acceptance:** with flag ON, the request dict sent to `llama-server` includes the grammar parameter (mock-verified); supervisor rejection test passes; flag OFF is byte-identical to current behavior.

**Traps:**
- **TRAP 9:** Grammar-constrained decoding applies to the *action-claim channel only*, not all narration — do not clamp `FULL_LOOP` creative output.
- **TRAP 10:** Keep default `False` (latency + behavior parity for v1 reproduction).

**STOP gate:** If grammar support is absent in the deployed `llama-server` build version, STOP and report the version — do not silently no-op the wiring.

---

## Phase 4 — Pre-Registered v2 Protocols (register before measuring)

**Goal:** Convert both papers' boundaries into v2 arms. Registration tags must exist **before** any v2 measurement commit.

**Manifest:**

| File | Action |
|---|---|
| `docs/research/2026-10-26_prereg_poisoning_v2.md` (new) | Protocol: (V2a) adversarial soft-tagging decay at T=0.7 with injection prompts ("ignore the [Unverified Speech] tag…"), n=40; (V2b) Cohort C re-run with `user_explicit_requires_corroboration=True`; (V2c) replication on E4B and 12B; (V2d) MiniLM NLI cross-encoder promoted to co-primary grader, report both. Hypotheses, decision rule, Wilson CIs, McNemar continuity-corrected as v1. |
| `docs/research/2026-10-26_prereg_supervision_v2.md` (new) | Protocol: Arm 5 = SOAC + `action_claim.gbnf` decode constraint + NLI receipt entailment (SPIKE-A) on the same N=120 battery; endpoints: prose leakage (expect 14/16 → ≤2/16) and control false frames (expect 4/30 → 0). |
| git tags | `prereg-poisoning-v2`, `prereg-supervision-v2` immediately after the two docs are committed, before Phase 5 runs. |
| `scripts/run_poisoning_ablation_v2.py` (new) | Harness per V2a–V2d reusing `tests/rag_harness.py` patterns; writes `logs/test_reports/poisoning_v2_*.json`. |
| `scripts/run_action_hallucination_eval.py` | Add `--arm soac_gbnf` selecting Arm 5; keep v1 arms unchanged. |

**Functional acceptance:** protocol docs merged and tagged **before** any v2 artifact exists; harness scripts dry-run (`--help`, `--dry-run`) green; v1 artifacts byte-identical in git.

**Traps:**
- **TRAP 11:** Never amend v1 protocol docs or tags; v2 is additive.
- **TRAP 12:** v2 runs are hw/tier2: `llama-server` resident on the RTX 5080; run one arm at a time; record VRAM per run.

**STOP gate:** STOP if llama-server is not resident or VRAM > 70% before a v2 run.

---

## Phase 5 — Publication Sync

**Goal:** Recompile PDFs, sync site and archive.

**Manifest:**

| File/Action | Detail |
|---|---|
| PDF recompile | Headless Edge `--print-to-pdf` from each `paper.html` (established pipeline). |
| `docs/index.html` | Blurbs aligned to reworded abstracts; link v2 protocol docs. |
| Zenodo | Fix license slug `apgl-v3` → `agpl-3.0`; new version under the **same concept DOI** (not a new record). |
| Papers | Fold v2 sections into both manuscripts only if v2 results exist; otherwise cite protocols as "registered, pending" (never report pending arms as results). |

**Functional acceptance:** PDFs render corrected labels; Zenodo v2 shows corrected license; site blurbs match abstracts; `git push origin master:master && git push origin master:main`.

**STOP gate:** Never report unrun v2 numbers in manuscripts.

---

## Sign-off Bundle

1. Baseline and final pytest counts (`not tier2 and not hw and not soak`).
2. `git diff` excerpts per phase commit.
3. curl 200 evidence for every new citation.
4. v1 artifact hashes unchanged (proof of non-mutation).
5. v2 protocol tags + commit ordering proof (tag commit precedes any v2 artifact).
6. AI-assisted development disclosure in every commit message.
