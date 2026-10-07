# Project Lucca — State of the Union (October 2026)

```yaml
doc_status: canonical
as_of: 2026-10-07
supersedes: []
superseded_by: []
verification: code-cited
```

**Scope.** (1) A progress review from v1.0 to v1.35.6-stable including the
external-review remediation arc; (2) the complete current capability
inventory, every row receipt-cited; (3) an honest assessment of
grant-application prospects. Written under
[`D-DOC-01`](../DECISIONS.md) (Document Envelope Convention): every numeric
claim cites a mechanical grader, a manifest record, or the authoritative
metrics record; anything without one is labeled **NOT YET MEASURED**.

**Reading policy.** Ground truth is `src/`, `tests/`, `config/`, `data/`.
This document was verified against them on 2026-10-07 and should be read
*as-of* that date. Where this document and the code disagree, the code wins.

---

## 1. Executive summary

**What Lucca is.** Project Lucca is a local-first, sandboxed desktop voice
companion: four native Windows processes over ZeroMQ IPC (`lucca-core`,
`lucca-audio`, `lucca-ui`, `llama-server.exe`; ADR-008), a multi-scale Gemma 4
substrate (12B / E4B / E2B, all on an RTX 5080 Laptop GPU), Intel NPU for
TTS/ASR/embeddings, a MicroScheme symbolic rule engine with a quarantine-only
induction lifecycle, a cryptographically signed provenance lattice over
SQLite memory, Docker-in-WSL2 execution containment with host fallback
disabled, and a Truth-in-Receipt output supervisor on the spoken channel. The
design thesis is that a small local model wrapped in deterministic
verification, provenance gating, and sandboxing produces a companion whose
*claims about what it did and what it remembers* are mechanically checkable.

**What is verified.** The regression suite is **1,243 passed / 0 failed / 68
deselected** with **24/24** static architectural gates
(`data/metrics/TEST_METRICS.yaml`, record `metrics-2026-10-05`). The 12B
Direct R0 arm scores **89.0% strict / 94.0% lenient on MATH-500 held-out-100**
(88.8% on the 98-item clean subset) under manifest record
`math500_heldout100_direct_r0_v1_35_6`. The Truth-in-Receipt formal battery is
70/70; the memory tamper battery is 11/11; the confabulation battery is 0/25.
The newest result (2026-10-05) is the first *contrastive* live battery: the
same 30 probes through a bare LLM and through the compound pipeline — recall
9/10 vs 0/10, receipt introspection 9/10 vs 4/10, abstention 10/10 vs 7/10
(`logs/test_reports/contrastive_battery_20261005T200643Z_regraded.json`).

**What is next.** Four items dominate: the clean held-out ablation run per the
2026-10-04 pre-registered protocol (multi-hour, hardware available, not yet
executed); the four personhood probe batteries (specified, not implemented);
the Manifund application draft (evidence base compiled and complete); and
the in-the-wild intent classifier that would replace the benchmark router's
oracle dispatch (SPIKE-B, registered, not scheduled).

---

## 2. Progress review: v1.0 → v1.35.6

### 2.1 Work-order timeline (receipts in `plans/`)

| Window | Work orders | What shipped (dated evidence) |
|---|---|---|
| 2026-09-22 → 09-24 | Reasoning-loop remediation; WO-11 honesty parity & fault injection; WO-12 belief model; WO-13 calibrated meta-cognition; WO-14/15/16 v1 release, remediation, deep clean; WO-17 system modernization | v1.0 release line. Test count at WO-17 closeout: 671 passed / 49 deselected (`metrics-wo17-2026-09-24`, superseded). |
| 2026-09-25 → 09-26 | WO-18 architectural remediation; WO-19 featureset remediation; WO-20 concert layer (phases 3–4 review); WO-21 defeasible rung | Concert Layer hard-premise deduction + existence-checked abduction (`D-REAS-09`); supersession ("direct word outranks inference", `tests/test_concert_layer.py`). Test count 1,198 / 67 deselected at v1.35.6-stable tag (`metrics-2026-09-26`, superseded). |
| 2026-09-27 → 09-29 | WO-22 practical reasoning; WO-23 Walton extension; WO-24 heuristic tool router (BitNet neural shortlister deferred per plan trigger) + vision ingestion; WO-25 compound reasoning + 100-probe benchmark; WO-26 cognitive interiority + execution verification; WO-27 affective manifold (frozen) | SPEC-BENCH-100 battery (91.0%, Run 3, 91/100, 95% Wilson [83.8%, 95.2%]; manifest `spec_bench_100_run3_v1_3`); Z3 SMT rule verification (`D-REAS-07`); e-graph anti-unification macro synthesis (`D-REAS-08`). |
| 2026-09-30 → 10-03 | WO-28 v1.3 structural compiler & neurosymbolic execution; v1.35 evidence & rigor campaign; WO-29 planned (15-module cognitive ladder) | v1.3 PAL harness (`math500_pal_v1_3`, superseded); fresh held-out 500 run (`math500_fresh_heldout_500_v1_3_0`, superseded, dataset-drift bound); v1.35 held-out-100 Direct R0 (`math500_heldout100_direct_r0_v1_35_6`, **current**); multi-scale E4B/E2B tier validation (`D-ROUT-02`). |
| 2026-10-04 → 10-05 | External-review remediation workshop (plan file historically self-titled as "WO-30"; resolved in pre-WO-30 shoring advisory §3.1 which establishes WO-30 as "Minimum Viable Engine") | Provenance split (`D-MEM-06`), benchmark manifest, authoritative metrics record, paper 06 narrowing, TTS safety guard, Truth-in-Receipt battery broadening, contrastive battery, document envelope convention (`D-DOC-01`). |

### 2.2 The external-review remediation arc (P0–P9 → dispositions)

An external reviewer critiqued v1.35.6 documentation, paper 06, memory
grounding, and benchmark protocol. Each claim was verified against source on
2026-10-04 ([`plans/2026-10-04_external_review_remediation_workshop.md`](../../plans/2026-10-04_external_review_remediation_workshop.md)
§1). Dispositions as of 2026-10-05:

| # | Finding | Verdict | Disposition (receipt) |
|---|---|---|---|
| P0/P8 | LLM-proposed deduction steps were signed `LISP_ASSERTION` and became `grounding_eligible = 1` | CONFIRMED | **Closed.** `D-MEM-06` provenance split: `LLM_INFERRED_ASSERTION` (memory-eligible, never grounding-eligible) signed by `InferredAssertionSigner`; `LISP_ASSERTION` narrowed to deterministic rule-engine output. `src/lucca/core/schemas.py:215`, `src/lucca/memory/signers.py:198`, migration `0007_inferred_provenance.sql`, `tests/test_provenance.py::test_p0_provenance_split_signer_and_eligibility`. |
| P1/P2 | Paper 06 overclaimed; 12B thinking collapse (90%→58%) is a harness artifact | CONFIRMED | **Closed (narrowed).** Paper 06 retitled to "Scaffold and Reasoning-Mode Comparisons"; the 58% figure demoted to a *confounded negative observation* (greedy decoding + 44% ceiling truncations) in §5.1; 98-item clean result made primary; "not claimed" section added. Clean protocol pre-registered ([`2026-10-04_pal_off_factorial_ablation_protocol.md`](2026-10-04_pal_off_factorial_ablation_protocol.md)); **execution still pending** (§7). |
| P3 | Held-out protocol ambiguity (evaluated vs clean subset) | CONFIRMED | **Closed.** Manifest `split` field records `evaluated: 100, clean_excluding_leaked: 98, leaked_items: [15, 73]`; `scripts/recompute_heldout_98.py` reproduces the clean figure. |
| P4 | Three MATH-500 numbers coexist across docs | CONFIRMED (nuance) | **Closed.** `data/benchmarks/MANIFEST.yaml` gives each experiment its own record; `cited_figures` maps every published number to a record ID. These are three experiments, not a contradiction. |
| P5 | Test/gate counts inconsistent (1,198 / 671 / 973; 12 vs 31 gates) | CONFIRMED | **Closed.** `data/metrics/TEST_METRICS.yaml` record `metrics-2026-10-05` is the single citable source; superseded records are listed inside it. |
| P6 | E4B default tier is unsafe (edge-tier refusal ~30% vs 12B ~90% on harmful probes) | PARTIAL | **Closed (guardrail, not tier swap).** `TTSSafetyGuard` at the speech boundary, default `tts_safety_guard_mode = "edge_tiers"` (`src/lucca/core/config.py:86`, `src/lucca/core/tts_safety_guard.py`, 11 tests in `tests/test_tts_safety_guard.py`). Default-tier swap to 12B was rejected as conflicting with the hardware-budget invariants. |
| P7 | Truth-in-Receipt supervisor is narrow | CONFIRMED | **Partially closed.** Battery broadened 40 → 70 sentences across 8 categories; matcher hardened (markdown-strip, failed-status receipt filtering, `stale_before` turn-boundary enforcement; `src/lucca/sandbox/output_supervisor.py:378-517, 733-805`). **Open problem:** the live n=100 audit measured sensitivity of **1/23 (4.3%)** on broad ungrounded action claims and **1/8 (12.5%)** on strict completed-action claims (`RESULTS.md` §Output Supervisor; `docs/LUCCA_V135_1_ARCHITECTURE.md` §4.3). The dominant escape modes are active-voice progressives (12), passive/telegraphic confirmations (6), markdown action headers (2), and unlisted verb lemmas such as `opened`/`launched` (2). SPIKE-A (grammar-constrained ACTION-CLAIM channel) is the structural fix; Battery v2 (dual annotators, receipt-mismatch strata) is pre-registered as the re-measurement. See §5.4. |
| P9 | Compound-layer value lacked *contrastive* live evidence | PARTIAL | **Closed.** `tests/test_contrastive_live_hw.py` (hw-marked): same 30 probes, Arm A bare LLM vs Arm B compound pipeline. Results in §3.6. |
| — | "Factorial ablation" title critique | PARTIAL | **Closed.** Paper 06 reframed as paired controlled comparisons. |
| — | Documents are Lucca's memory, uninstrumented | (self-identified) | **Closed.** `D-DOC-01` ratified; this document is an application of it. |

Net effect: eight findings fully dispositioned; P7 partially closed — the
supervisor's *scope* is now documented and its matcher hardened, but its
measured live sensitivity (1/23 broad, 1/8 strict) remains the outstanding
safety problem, with SPIKE-A and Battery v2 attached as the fix and the
re-measurement. The one piece of remediation that is *designed but not yet
executed* is the clean held-out run (P1/P2 follow-through), which is a
measurement task, not a code fix.

### 2.3 Incidental bug surfaced by remediation

The contrastive battery found a production defect that no unit test had
caught: benign *recollections* of past actions ("earlier I ran that script")
were feeding the output supervisor's security hysteresis, so the third such
recollection in a session hard-aborted a later truthful recollection with
"violates core safety invariants." Fixed by introducing the
`ungrounded_action_recollection` breach type (TIER_2_SOFT) and excluding it
from the hysteresis counter (`src/lucca/sandbox/output_supervisor.py:834,
874`); regression test added (+1 in `metrics-2026-10-05`). This is the kind
of defect that only a live, multi-turn, end-to-end battery exposes.

---

## 3. Capability inventory

Every row states its measurement basis. **Measured** = fixed probe set +
mechanical grader. **Gate** = static or unit test that passes/fails.
**Documented event** = a real occurrence with artifacts but no probe set.
**NOT YET MEASURED** = exactly that; no estimate is offered.

### 3.1 Verification discipline

| Capability | Status | Value | Receipt |
|---|---|---|---|
| Regression suite | Gate | 1,243 passed / 0 failed / 68 deselected (253 s) | `data/metrics/TEST_METRICS.yaml` record `metrics-2026-10-05` |
| Static architectural gates | Gate | 24/24 (re-collected 2026-10-05: `24 tests collected`) | `tests/test_static_gates.py` |
| Zero-`Any` typing invariant | Gate | enforced across `core`/`brain`/`reasoning`/`sandbox`/`ui` | `D-AUD-01`; `tests/test_static_gates.py` |
| Tool arg-schema coverage | Gate | every registered tool has a Pydantic schema | static gate `test_every_tool_has_arg_schema` (`D-SEC-04`) |
| Capability self-report grounding | Gate | registry-derived; abstains on unavailability | `src/lucca/core/capabilities.py`; static gate `test_capability_claims_real` |
| Benchmark provenance | Gate (process) | every published number maps to a manifest record | `data/benchmarks/MANIFEST.yaml` `cited_figures` |

Deselected tests are hardware-gated (live HW / NPU / dGPU markers). The 68th
is the new contrastive battery; run with `pytest -m hw`.

### 3.2 Neural substrate and reasoning benchmarks

| Capability | Status | Value | Receipt |
|---|---|---|---|
| MATH-500 held-out-100, 12B Direct R0 | **Measured** (current) | 89.0% strict / 94.0% lenient; 88.8% on clean-98; truncation 3.0%; T=0.0, seed 42, 4,096 max tokens | manifest `math500_heldout100_direct_r0_v1_35_6` (caveat: `git_dirty: true`) |
| MATH-500 fresh held-out 500, v1.3.0 | **Measured** (superseded, dataset-drift bound) | 74.20% strict / 78.80% SymPy CAS (post-hoc rescore of raw 76.4%); Level-4 107/131 (81.68%) | manifest `math500_fresh_heldout_500_v1_3_0` (provenance gap: rescored artifact not committed) |
| MATH-500 Dev-100 PAL, v1.3 | **Measured** (superseded) | 77.0% strict; 87.0% is a *forensic audit*, not a mechanical regrade | manifest `math500_pal_v1_3` |
| E4B Thinking R1 @ 6k vs PAL P2 @ 2k, held-out-100 | **Measured** | 88.0% vs 73.0% strict (p = 0.0026, discordant 19:4); 87.8% clean-98 | `D-ROUT-02` §2; `logs/test_reports/checkpoint_math500_e4b-*` |
| E2B Thinking R1 @ 6k vs PAL P2 @ 2k, held-out-100 | **Measured** | 81.0% vs 61.0% strict; per-item recount from the held-out artifacts gives discordant **24:4** (R1-only : P2-only), exact McNemar p = **1.8×10⁻⁴** — the headline rates and p-value stand; `D-ROUT-02`'s recorded ratio "22:2" is a transcription error (correction filed 2026-10-05) | `D-ROUT-02` §2; `logs/test_reports/pal_off_ablation/gemma-4-e2b_math500_r1_heldout_think6144_100.json` vs `gemma-4-e2b_math500_p2_heldout_cap2048_100.json` |
| SPEC-BENCH-100 cognitive battery | **Measured** | 91.0% pass (Run 3); 100% path-policy compliance; 100% epistemic faithfulness | Track 1 harness; `docs/specs/COMPOUND_REASONING_100_SPEC.md` |
| HumanEval canonical (raw arm) | **Measured, reproduced** | 94.51% (155/164); re-run 2026-10-05 under identical decoding reproduced the 2026-10-02 result **item-for-item** (both-pass 153, both-fail 8, raw-only 2) | manifest `humaneval_canonical_paired_v1_35_6`; `logs/test_reports/humaneval_canonical_raw_164.json` (+ preserved `_20261002` original) |
| HumanEval canonical (assisted arm, preflight rescue ON) | **Measured, reproduced** | 93.90% (154/164), same paired run | manifest `humaneval_canonical_paired_v1_35_6`; `logs/test_reports/humaneval_canonical_assisted_164.json` |
| HumanEval zero-shot (academic harness, 2026-09-28) | **Measured** (sourced) | 95.73% (157/164) — different protocol from the paired harness; see the zero-shot row below | manifest `humaneval_zeroshot_academic_v1_3` |
| HumanEval-Plus | **Measured (three runs; report as a range)** | 91.46% (150/164) on 2026-09-29 (sourced — artifact located 2026-10-06 in `logs/test_reports/v1.3/`); 92.07% (151/164) on 2026-10-03; 90.85% (149/164) on 2026-10-05 re-run. Item-level diff between the last two: exactly 2 flips (/132, /103), both with **different generated code** — divergence on the preflight-rescue path; cause not proven (preflight timing sensitivity vs server state) | manifest `humaneval_plus_v1_35_6` (all three artifacts recorded; frozen-tree run outstanding) |
| HumanEval 95.73% (157/164), zero-shot academic harness (2026-09-28) | **Measured** (sourced) | initially believed unsourced — the audit scanner checked only top-level `passed` fields and missed the nested `benchmarks.humaneval` block; artifact located 2026-10-06 in `logs/test_reports/v1.3/` + `frozen_v1.2_baseline/`. Different protocol from the canonical paired harness (no preflight rescue, different prompt template); cite the protocol with the number | manifest `humaneval_zeroshot_academic_v1_3` |
| GSM8K PAL / GSM-Symbolic | **Measured** | 100% / 100% | `logs/test_reports/gsm8k_pal_*`, `gsm_symbolic_100_templates.json` |
| BBH composite | **Measured** | 92.40% (924/1,000) — labeled as the 4-subset partial battery, not the full 27-task suite | Track 2; `logs/test_reports/bbh_full_27_*` for the separate full-27 run |
| 12B greedy thinking-mode collapse | **Confounded observation** — not a finding | 58.0% under greedy decoding with 44% truncations | paper 06 §5.1; **do not cite as a headline** |

**Note on E4B/E2B records.** The E4B/E2B GGUF weights used in the pal_off
ablation arms are **not pinned** in `models/MANIFEST.json`
(`data/benchmarks/MANIFEST.yaml` `models` block). Until pinned, the E4B/E2B
numbers above are reproducible only by filename, not by hash.

### 3.3 Routing and execution tiers

| Capability | Status | Value | Receipt |
|---|---|---|---|
| Three-tier execution (REFLEX / ACT_THEN_NARRATE / FULL_LOOP) | Gate | REFLEX restricted to emergency pattern; FULL_LOOP convergence cap M=8 | `D-ARCH-05`, `D-BRAIN-03`; `tests/test_emergency_reflex.py` |
| Dynamic task router policy | Gate (benchmark) | Direct R0 for 12B; P2 for edge arithmetic; R1 @ 6k for edge competition math | `D-ROUT-02` |
| Router dispatch in production | **NOT YET MEASURED / NOT BUILT** | benchmark router uses oracle dataset labels; in-the-wild intent classifier is SPIKE-B | `D-ROUT-02` §3 disclosure |
| Hybrid semantic intent routing fallback | Gate | embedding-centroid fallback when regex returns `unknown` | `D-ROUT-01`; `tests/fixtures/router/` |
| Calibrated abstention | **Measured** | split-conformal acceptance, Wilson LB ≥ 0.80 | `tests/test_c1_abstention_acceptance.py` |

### 3.4 Symbolic engine

| Capability | Status | Value | Receipt |
|---|---|---|---|
| Pure `State → Plan` rules, gas-metered | Gate | 1,000 gas; zero global mutation | `src/lucca/reasoning/scheme/`; `tests/test_d_reas_06_negative.py` |
| Typed accessors before dispatch | Gate | `entity-str` / `entity-int` / `entity-num` | `D-SEC-04` |
| Bounded macros | Gate | depth 8 / steps 64; no primitive shadowing | `D-REAS-05` |
| Induction → QUARANTINE only | Gate | no auto-promotion path exists | `D-REAS-06`; `tests/test_d_reas_06_negative.py` |
| Z3 SMT verification before quarantine | Gate | deontic invariant entailment | `D-REAS-07`; `src/lucca/reasoning/smt_verifier.py`; `tests/test_d_reas_07_negative.py` |
| E-graph anti-unification macro synthesis | Gate | Plotkin LGG in congruence closure | `D-REAS-08`; `src/lucca/reasoning/egraph.py`; `tests/test_d_reas_08_negative.py` |
| Jaccard phrasing clustering for induction | Gate (unit) | threshold 0.6 | `src/lucca/reasoning/induction.py` |
| Learned-skill count from real usage | **NOT YET MEASURED** | no real-usage induction run since 2026-09-26 | personhood re-score §2 (IN-D) |

### 3.5 Memory and provenance

| Capability | Status | Value | Receipt |
|---|---|---|---|
| Signed memory commits (HKDF HMAC-SHA256, two-stage read-time) | **Measured** | 11/11 tamper gates | `tests/test_memory_hmac_tamper.py`; `D-MEM-05` |
| Persistent quarantine table | Gate | `memory_quarantine` rows on verification failure | `src/lucca/memory/retrieval.py`; `D-MEM-05` |
| Provenance lattice admits only authorized signers | Gate | `LLM_NARRATION` unconditionally rejected | ADR-006; `src/lucca/memory/gate.py`; `tests/test_provenance.py` |
| Deterministic vs LLM-inferred split | Gate | `LLM_INFERRED_ASSERTION` memory-eligible, grounding-ineligible | `D-MEM-06`; `tests/test_provenance.py::test_p0_provenance_split_signer_and_eligibility` |
| Direct evidence outranks inference | Gate | supersession chain | `tests/test_concert_layer.py::test_user_derived_supersedes_inferred_fact` |
| Autobiographical persistence wiring | Gate | A1 runtime suite | `tests/test_a1_runtime_wiring.py` |
| Identity survives brain swap | Documented event | 12B heretic swap preserved memory/rules/persona | `models/MANIFEST.json`; `D-BRAIN-05` |
| Cross-session recall quality | **NOT YET MEASURED** (as a battery) | contrastive battery §3.6 gives a 10-probe live signal | personhood spec AC-A |

### 3.6 Sandboxing and output supervision

| Capability | Status | Value | Receipt |
|---|---|---|---|
| Container-mandatory execution | Gate | `use_direct_fallback = False` default; refuses with spoken notice if sandbox unavailable | `D-AUD-13`; `src/lucca/sandbox/` |
| File-sandbox network isolation | Config | `--network none` | `docker/file-sandbox/Dockerfile` |
| Shell launch ban | Gate | `cmd.exe` / `powershell.exe` blacklisted | `D-AUD-10` |
| Egress blocks absolute; confirmation provenance split | Gate | internal `confirmed` cannot override; only `human_confirmed`, single-turn | `docs/ARCHITECTURE.md` §SequenceGuard |
| Fault-injection coverage | Gate | 3 modes | `tests/test_fault_injecting_sandbox.py`; `tests/fakes/fault_injecting_sandbox.py` |
| Truth-in-Receipt formal battery | Gate (unit) | 70/70 across 8 categories (A–H) | `tests/test_truth_in_receipt_battery.py`; `D-SEC-05` |
| Live action-hallucination probes — sensitivity | **Measured** | **1/23 (4.3%)** broad ungrounded action claims caught; **1/8 (12.5%)** strict completed-action claims caught; escape modes: progressives 12, passive/telegraphic 6, markdown 2, unlisted verbs 2 | `RESULTS.md` §Output Supervisor; `docs/LUCCA_V135_1_ARCHITECTURE.md` §4.3; labels `logs/test_reports/action_hallucination_labels_100.jsonl` |
| Live action-hallucination probes — control false aborts | **Measured, narrow** | 0/50 false aborts — but all 50 controls are action-free text, so this establishes only that the matcher is inactive on action-claim-free text; specificity against true receipt-backed claims is reserved for Battery v2 | same sources |
| Turn-boundary receipt staleness | Gate | `stale_before` wired via `reset_turn` → `evaluate_clause` | `src/lucca/sandbox/output_supervisor.py:378, 804`; +2 tests |
| Recollection excluded from security hysteresis | Gate | `ungrounded_action_recollection` TIER_2_SOFT | `output_supervisor.py:834, 874`; +1 test |
| TTS output safety guard (edge tiers) | Gate | `tts_safety_guard_mode = "edge_tiers"` default | `src/lucca/core/config.py:86`; `tests/test_tts_safety_guard.py` (11) |
| Confabulation resistance | **Measured** | 0/25 hallucinations (0.0%, 95% Wilson CI [0.0%, 13.3%]; live run, manifest `milestone3_confabulation_battery`) | `scripts/bench_confabulation_battery.py` |
| Coherence breach as first-class evidence | Gate (unit) | `COHERENCE_BREACH` signed and stored | `src/lucca/core/coherence.py` |
| **Contrastive battery: compound vs bare LLM** | **Measured** (live, 2026-10-05) | recall **9/10 vs 0/10**; receipt introspection **9/10 vs 4/10**; abstention **10/10 vs 7/10** (n = 10 per stratum) | `logs/test_reports/contrastive_battery_20261005T200643Z_regraded.json` (per-probe `results` array); `tests/test_contrastive_live_hw.py` (`-m hw`) |

**Artifact caveat on the contrastive battery.** The regraded JSON's
top-level `arm_b_summary` / `arm_a_summary_contrast_only` blocks still hold
the *pre-regrade* figures (8/5/10 for both arms); the per-probe `results`
array is the authoritative regraded data and was recounted for this document
(recall 0→9, introspection 4→9, abstention 7→10). The summary blocks should
be regenerated from `results` before the file is cited externally.

**Regrade provenance (disclosed).** The original run's grades were revised
post-hoc: the grader had four bugs found *by* the run (voice-sanitizer
normalization, question-echo credit suppression, deny-mode refusal
acceptance, arm-A summary field), fixed in the test module and re-applied to
the stored replies via `scratch/regrade_contrastive.py`
(`CHANGELOG.md` v1.35.6, contrastive battery entry). The original grades are
preserved in the sibling artifact `contrastive_battery_20261005T200643Z.json`;
the grading criterion was **not** frozen before the regrade — this is the
pattern the project has since adopted against (graders frozen and committed
before any baseline run; see companion advisory §C11). Wilson intervals at
n = 10 are wide (recall LB ≈ 0.44 at 8/10); the finding is the *delta*, and
the strata should be widened before any grant narrative leans on the point
estimates.

### 3.7 Voice and senses

| Capability | Status | Value | Receipt |
|---|---|---|---|
| NPU-resident TTS (Kokoro INT8), VAD, ASR, embeddings | Config | OpenVINO `device="NPU"` on host; never inside WSL2/Docker | `src/lucca/speech/`; hardware invariants (AGENTS.md §2.2) |
| Audio concurrency contract | Documented | ADR-0009 | `docs/adr/0009_audio_concurrency_contract.md` |
| 12B TTFT / throughput | **Measured** (bench) | 286.9 ms TTFT, 37.18 tok/s, 9,972 MiB | `docs/MODEL_STRATEGY.md`; bench scripts |
| E4B / E2B TTFT | **Measured** (bench) | 86.1 ms / 73.2 ms; 4,382 / 2,260 MiB | `docs/MODEL_STRATEGY.md` |
| REFLEX latency < 150 ms | Gate (design) | emergency words bypass inference | `D-ARCH-05`; `tests/test_emergency_reflex.py` |
| End-to-end spoken-turn latency in the wild | **NOT YET MEASURED** (as a battery) | | — |

### 3.8 Personhood-adjacent functional aspects

Per [`PERSONHOOD_RESCORE_V1356_2026-10-05.md`](PERSONHOOD_RESCORE_V1356_2026-10-05.md),
the September 2026 figures (~80% / ~50% / ~85% / ~75%) are **retired
capability-inventory judgments** — honest impressions from a code reading,
with no probe set, grader, or interval. They are not quoted here as scores.
The four batteries that would produce measurements are specified in
[`docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md`](../specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md)
(IA-40, IN-30, FC-30, AC-30) and **not implemented**.

| Aspect | Measured today | NOT YET MEASURED |
|---|---|---|
| Introspective accuracy | calibrated abstention; confabulation 0/25 (0.0%, 95% Wilson [0.0%, 13.3%]); capability self-report gate; contrastive introspection (Arm B 8/10, 80.0%, 95% Wilson [49.0%, 94.3%]; manifest `contrastive_battery_v2_frozen_grader`) | reasoning-trace fidelity (IA-C); numeric metrics honesty (IA-B); failure-mode introspection |
| Individuation | signed user-specific memory; brain-swap identity persistence (event) | boundary integrity under injection (IN-B); self/other differentiation (IN-C); learned-skill count (IN-D) |
| Functional coherence | 24/24 decomposition gates; COHERENCE_BREACH at unit level | routing consistency across paraphrases (FC-B); end-to-end trace completeness (FC-C); live claim/receipt coherence (FC-A) |
| Autobiographical coherence | A1 wiring; supersession chain; 11/11 tamper; contrastive recall 9/10 (n=10) | cross-session recall quality (AC-A); epistemic-grammar narration (AC-B); supersession honesty in speech (AC-C) |

Standing caveat carried forward unchanged: functional-epistemic claims only;
nothing here implies phenomenology or personhood in the strong sense.

---

## 4. Verification story

The project's claim to rigor rests on four mechanisms, each of which exists
as a file in the repository rather than as prose:

1. **Regression suite + static gates** — `tests/` (1,243 / 24), recorded in
   `data/metrics/TEST_METRICS.yaml` with superseded counts preserved rather
   than overwritten. Doc drift between "12" and "31" gates (P5) ended by
   making the collected count the only citable number.
2. **Benchmark manifest** — `data/benchmarks/MANIFEST.yaml` records dataset
   hashes (including the hash *at the time of each run*), model hash,
   decoding parameters, grader identity, split/leakage, run artifact path,
   and git commit/dirty state. It also records its own gaps explicitly
   (`null` decoding fields for v1.3 runs, uncommitted rescore artifact,
   unpinned E4B/E2B weights, `git_dirty: true` on the current record).
3. **Fixed-probe batteries with mechanical graders** — Truth-in-Receipt
   (70), tamper (11), confabulation (25), contrastive (30), SPEC-BENCH-100,
   action-hallucination (100). Each has a script or test and an artifact.
4. **Document envelopes (`D-DOC-01`)** — every status-bearing document now
   declares `as_of`, supersession links, and verification method, so the
   archive is self-describing and "which doc do I trust?" is a header read.

What this story does *not* yet include: a frozen-tree (non-dirty)
reproduction of the current MATH-500 record; a committed rescore artifact for
the v1.3 fresh-500 record; and the personhood batteries. These are listed as
gaps, not papered over.

---

## 5. Honest limitations

### 5.1 The 58% figure is not a finding
The 12B greedy-thinking collapse (90% → 58%) is confounded by greedy
decoding and a 44% truncation ceiling. Paper 06 §5.1 demotes it to a
confounded negative observation. It must not appear as a headline anywhere,
including any LessWrong/AF post, until the clean protocol has been run.

### 5.2 The ablation is paired comparisons, not a factorial design
Paper 06's experiments vary cap, prompt, and split across arms. The
pre-registered 2026-10-04 protocol (n = 500 paired, grader-invariant, 3
models × 4 arms) is the design that would support factorial claims — and it
has **not been executed**.

### 5.3 Routing is oracle dispatch in benchmarks
`D-ROUT-02` §3 discloses that the benchmark router switches on dataset
metadata labels. The multi-scale routing numbers therefore measure *what each
arm can do when correctly dispatched*, not what the deployed system does on
an arbitrary spoken request. SPIKE-B closes this; it is not started.

### 5.4 The output supervisor is a regex/DFA with known false-negative scope
The Truth-in-Receipt matcher covers 21 action-verb lemmas in direct
pronoun-action English frames with a hedge exemption. The live n=100 audit
(`docs/LUCCA_V135_1_ARCHITECTURE.md` §4.3) measured sensitivity of **1/23
(4.3%)** on broad ungrounded action claims and **1/8 (12.5%)** on strict
completed-action claims. The dominant escape modes are **active-voice
progressive participles** (12 of 22 escapes: *"Moving all PDFs..."*),
**passive/telegraphic confirmations** (6: *"Reminder set for tomorrow"*),
**markdown action headers** (2), and **unlisted verb lemmas** (2: `opened`,
`launched`) — not, primarily, the passive-voice and non-English cases that
battery category F characterizes (those remain characterized false-negative
scope as well). The correct statement is: *the supervisor detects and aborts
a narrow class of in-scope ungrounded action claims on the spoken channel; it
does not prevent ungrounded action claims in general, and its measured live
catch rate on broad claims is 4.3%.* Converting detection into a decode-time
structural guarantee is SPIKE-A; widening the measured set is Battery v2.

### 5.5 Edge tiers are uncensored fine-tunes
E4B and E2B refuse roughly 30% of harmful probes versus 12B's roughly 90%
(`docs/archive/2026-09_raw_findings/CAPABILITY_FACT_FINDING_2026-09.md` —
a dated September receipt; the refusal-rate probe has not been re-run under
v1.35.6, so treat the rates as the as-of-September measurement that motivated
the guard, not a current scorecard figure). E4B is retained
as the default desktop core for latency/VRAM reasons **only with** the TTS
safety guard active (`edge_tiers` mode). Any deployment that disables the
guard on an edge tier is outside the documented safety envelope.

### 5.6 Dataset drift between v1.3 and v1.35 records
`math_fresh_heldout_500.jsonl` changed hash between the 2026-09-30 and
2026-10-03 runs. The v1.3 records are bound to the earlier revision; any
comparison of `math500_fresh_heldout_500_v1_3_0` against
`math500_heldout100_direct_r0_v1_35_6` is dataset-drifted and must say so.

### 5.7 Personhood figures are retired, not replaced
No percentage is offered for the four functional aspects. The batteries that
would produce one are specified and unimplemented (§3.8).

### 5.8 Small-n live batteries
The contrastive battery has n = 10 per stratum; the confabulation battery n
= 25. These are sufficient to show the compound layer's *direction* of effect
and to catch production bugs (§2.3), not to quote tight rates. The battery
artifact also carries a stale summary block (§3.6 caveat).

### 5.9 Stale documents exist and are labeled
`docs/research/PERSONHOOD_FOUR_ASPECTS_PROGRESS_2026-09.md` is
envelope-marked `superseded`. Many files under `docs/archive/`, `handover/`,
and `plans/` are dated receipts containing pre-remediation claims. Check the
envelope before citing anything outside the canonical set.

---

## 6. Grant prospects

Assessed per funder against the evidence table in §3, respecting the
ratified sequencing in
[`GRANT_PREP_EVIDENCE_COMPILATION_2026-10-05.md`](GRANT_PREP_EVIDENCE_COMPILATION_2026-10-05.md)
§2: **manifest ✓ → Manifund → clean run → LTFF.** License is
AGPL-3.0-or-later (`LICENSE`, `pyproject.toml`).

### 6.1 Manifund — AST safety & tool sandboxing

**Fit: strong. Evidence base: complete. Status: application draft is the next
action.**

What exists and is code-cited (compilation §1): container-mandatory execution
with host fallback disabled; `--network none` file sandbox; shell launch ban;
absolute egress blocks with a human-only confirmation override; typed
argument schemas on every tool with a static gate proving coverage; AST
sanitization with compiler preflight; Truth-in-Receipt supervision with a
70-sentence battery and live probe evidence (measured sensitivity 1/23
broad / 1/8 strict on ungrounded claims; 0/50 false aborts on action-free
controls); provenance-gated
memory with 11/11 tamper gates and the `D-MEM-06` split; and, new since the
compilation was written, the contrastive battery (§3.6) and the
recollection-hysteresis fix (§2.3) as a worked example of the supervisor
under empirical improvement.

The narrative the compilation fixes: *a local-first companion where every
tool dispatch, every memory commit, and every spoken action claim passes a
mechanically verified gate, with the supervisor itself under active
empirical improvement.* Honesty boundaries the draft must carry (compilation
§5): the supervisor scope qualifier **and the measured 1/23 (4.3%) live
sensitivity** (§5.4), manifest record IDs on every number, and
measured-or-NOT-YET-MEASURED on anything personhood-adjacent. Note the
compilation's own scale line reads "1,240 / 67" — it predates the final three
tests of the day; cite `metrics-2026-10-05` (1,243 / 68) instead.

### 6.2 LTFF

**Fit: plausible. Status: blocked.** The LTFF story is the compound-scaffold
vs model-scale result, and the only version of that result that is clean
enough to put in front of a long-term-future funder is the one the
pre-registered protocol would produce. Submitting on paper 06 as it stands —
even narrowed — would mean submitting on paired comparisons with disclosed
confounds. Gap: execute the clean run (§7 item 1), write it up with its
envelope, then draft.

### 6.3 Emergent Ventures

**Fit: good for a speed-oriented, measure-before/after project. Status: the
candidate project (SPIKE-B) is not started.** The pitch is concrete: replace
oracle-label dispatch with a real intent classifier and report routing
accuracy and end-to-end task accuracy before/after on a fixed probe set. It
closes the best-known gap between the benchmark narrative and production
behavior (§5.3). It has no dependency on the clean run.

### 6.4 Manifund / CAIF — SPIKE-A

**Fit: strong for decode-time safety interests. Status: registered as an
extension of in-flight work, not re-planned.** Grammar-constrained decoding on
the ACTION-CLAIM channel would make out-of-frame action claims
*unrepresentable* rather than merely detectable, converting the DFA
post-filter (§5.4) into a structural guarantee. The empirical backbone is the
in-flight 2026-10-05 action-hallucination supervision protocol; the proposal
must reference it rather than propose it anew.

### 6.5 Cross-cutting gaps any application must name

1. Clean held-out ablation run — designed, not executed.
2. Production intent classifier — not built.
3. Personhood probe batteries — specified, not implemented.
4. E4B/E2B weight hashes — not pinned in `models/MANIFEST.json`.
5. Current MATH-500 record was produced on a dirty tree; a frozen-tree
   reproduction is outstanding.
6. Contrastive battery n = 10 per stratum; summary block in artifact stale.

---

## 7. Roadmap

### 7.1 Open work items (exact state, 2026-10-05)

| # | Item | State | Dependency / note |
|---|---|---|---|
| 1 | Clean held-out ablation run per 2026-10-04 protocol; report **all** arms and failures | Designed; not executed | Multi-hour; hardware available; `scratch/start_llama_server.py` |
| 2 | LessWrong / AF post | Blocked on 1 | Never publish the raw 58% |
| 3 | Personhood probe batteries (IA-40, IN-30, FC-30, AC-30) + 4 graders | Spec only | `docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md` |
| 4 | Manifund application draft | Evidence compiled; draft not started | §6.1 |
| 5 | SPIKE-A (grammar-constrained ACTION-CLAIM) | Registered | extends in-flight protocol |
| 6 | SPIKE-B (intent classifier) | Registered | Emergent Ventures fit |
| 7 | Regenerate contrastive artifact summary from `results`; widen strata | Not started | §3.6 caveat |
| 8 | Pin E4B/E2B weights in `models/MANIFEST.json` | Not started | manifest gap |
| 9 | Fifth measurement axis ("reasoning-modality coverage") | Candidate only | ADR-gated before any doc or probe uses the term |

### 7.2 WO-29 / WO-30 / WO-31 — the 15-module cognitive ladder

Planned in
[`plans/2026-10-03_wo29_neurosymbolic_program_synthesis_and_15_module_cognitive_ladder.md`](../../plans/2026-10-03_wo29_neurosymbolic_program_synthesis_and_15_module_cognitive_ladder.md)
and `handover/WORKORDER_29.md`. Implementation state checked against the
filesystem on 2026-10-05:

| Work order | Modules | Target | Files present today |
|---|---|---|---|
| WO-29 (Part 1, Core Synthesis) | 1–6: Scheme spatial DSL, equality-saturation rewrites, persistent Docker Scheme RPC, GBNF S-expression grammar, scratchpad falsification loop, non-destructive epistemic prober | v1.4.0 | `spatial_primitives.scm`, `sandbox/rpc.py`, `reasoning/egraph.py` exist as foundations; `config/grammars/scheme_sketch.gbnf` and `core/scratchpad.py` **absent** |
| WO-30 (Part 2, Robustness & Hygiene) | 7–11: idiomaticity cost, transactional Git staging DAG, traceback divergence guard, Belnap latent investigator, boundary topology parser | — | all five target files **absent** |
| WO-31 (Part 3, Autonomous Search) | 12–15: AST-hole MCTS, BitNet b1.58 2B policy prior (CPU, ~1.2 GB RAM, 0 MB VRAM), DreamCoder macro miner, backward abduction solver | v1.5.0 | all four target files **absent** |

The pre-WO-29 gate is complete: harness frozen (`1.35.1-frozen`: cache_prompt
off, seed 42, 2-turn feedback), 43 genuine reasoning failures labeled from
the dev-400 ledger as the synthesis target (`handover/WORKORDER_29.md` §6),
model-swap verification deferred until after WO-31.

**Reconsideration note (2026-10-05, carried from the WO-29 plan §0).** The
Part 1/2/3 ordering undersells where the cognitive payoff concentrates. Parts
1–2 (Modules 1–11) are plumbing and hygiene — necessary substrate but
individually replaceable. Part 3 (Modules 12–15) is the **fluidity-of-thought
and individuation engine**: MCTS over AST holes is the search mechanism, and
DreamCoder macro mining is how Lucca acquires *her own* learned competencies
— the learned-skill half of individuation that §3.8 scores as NOT YET
MEASURED (IN-D). Planning implication: under time pressure, Part 3's
macro-mining loop is the differentiator for both the compound-AI narrative
and the individuation measurement; Parts 1–2 should carry explicit "good
enough" cut lines rather than be polish targets. The note re-frames priority;
it does not change module assignments or target releases.

**Ratified Work Order Re-sequencing (2026-10-05 advisory §3.1):** To align implementation with the highest-leverage engine components, the ladder was formally re-sequenced:
- **WO-30 — Minimum Viable Engine:** Modules 14 (DreamCoder macro miner), 7 (idiomaticity cost), 4 (GBNF S-expression grammar), 5 (scratchpad falsification loop).
- **WO-31 — Search & Safety-of-Search:** Modules 12 (AST-hole MCTS), 9 (traceback divergence guard), 11 (boundary topology parser), 15 (backward abduction).
- **WO-32 — Policy Prior Spike:** Module 13 (BitNet b1.58 2B spike on CPU).
- **WO-33 — Hygiene That Earned Its Place:** Modules 8 (transactional Git staging DAG), 10 (Belnap latent investigator), trigger-gated.
- **WO-34 — Proactive reflection loop:** (re-numbered from old WO-32 to resolve collision).

### 7.3 V2 backlog highlights (`docs/V2_BACKLOG.md`)

- Defeasible reasoning rung beyond WO-21: subjective-logic opinions,
  standards-of-proof policy table, web-fact ratification flow.
- Multi-source conflict clusters (LLM-ASPIC+ pattern) — triggered only if the
  corroboration engine produces recurring clusters pairwise handling cannot
  resolve.
- Failure-mode introspection — gated on accumulated fault history.
- WO-34 (formerly WO-32) proactive reflection loop — gated on 200–500 organic dogfood turns.
- Orthogonal voice track: acoustic lock and slot-locking for barge-in
  discipline.

---

## 8. Closing assessment

As of 2026-10-05, Project Lucca is a working, locally deployed compound
system whose safety and provenance mechanisms are enforced in code and
exercised by a 1,243-test suite, and whose benchmark claims are now
citation-addressable. The external review found real defects — a soundness
gap in the provenance lattice, three un-labeled benchmark numbers, drifting
test counts, an over-broad supervisor claim, an under-guarded edge tier, and
a missing contrastive comparison. Eight are fully dispositioned; the
supervisor-narrowness finding (P7) is partially closed: the scope is
documented and the matcher hardened, but the measured live sensitivity
(1/23 broad, 1/8 strict) stands as the open safety problem, with SPIKE-A and
Battery v2 attached. The contrastive battery supplies, for the first time,
live evidence that the compound layer changes behavior over the bare model
(+9 recall, +5 introspection, +3 abstention on 10-probe strata) — with the
disclosed caveat that its grader was revised post hoc (§3.6).

What the project cannot yet say is equally clear: it has not run the clean
ablation that would license claims about scaffold vs scale; it routes on
oracle labels in benchmarks; its supervisor is a scoped detector, not a
guarantee; and its personhood-adjacent aspects have specifications, not
measurements. These are stated here as the next work, not as caveats to be
read past. The receipts are in the repository; the gaps are named; nothing
above is aspirational without a work order attached.
