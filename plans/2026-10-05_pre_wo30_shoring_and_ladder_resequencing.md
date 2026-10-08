# Advisory — Shoring-Up Before WO-30, and Re-Sequencing the Cognitive Ladder

```yaml
doc_status: snapshot
as_of: 2026-10-05
supersedes: []
superseded_by: []
verification: code-cited
```

**Status:** Advisory. Not a ratified work order; no ADR issued. Companion to
[`docs/research/STATE_OF_THE_UNION_2026-10.md`](../docs/research/STATE_OF_THE_UNION_2026-10.md).

**Question answered:** *Is there work that should be done before WO-30+
starts, and should WO-30/31 be rewritten?* Short answer: yes to both, but
the shoring-up is small (one dry session plus one GPU night), and the
rewrite is a re-sequencing rather than a re-plan. Details follow, in
priority order, each item with its receipt and its cost.

---

## 0. Why shore up at all

The remediation workshop closed nine findings in two days. Two days of fast
remediation leaves exactly the kind of residue an external reviewer finds
next time: a stale summary block in a cited artifact, a user-guide line the
workshop itself flagged and did not fix, a work-order number used twice, a
benchmark record produced on a dirty tree, and a safety mitigation that is
unit-tested but never live-measured. None of these is large. All of them are
the sort of thing that converts "we fixed it" into "we said we fixed it" if
left for a quarter. Fix them while the context is hot.

---

## 1. Findings that surfaced while writing the SotU (verified 2026-10-05)

| # | Finding | Evidence | Severity |
|---|---|---|---|
| F1 | **Work-order number collision.** `plans/2026-10-04_external_review_remediation_workshop.md` titles itself "WO-30"; `plans/2026-10-03_wo29_…cognitive_ladder.md` §0 assigns WO-30 to Part 2 (Modules 7–11). Two different things carry the same number. | both files, line 1 / line 16 | Medium — will corrupt every future cross-reference |
| F2 | **Contrastive artifact summary is stale.** `arm_b_summary` / `arm_a_summary_contrast_only` in `contrastive_battery_20261005T200643Z_regraded.json` still hold pre-regrade figures (8/5/10 both arms); the per-probe `results` array holds the regraded truth (9/0, 9/4, 10/7). | recount in SotU §3.6 | Medium — the cited file contradicts itself |
| F3 | **User-guide drift the workshop flagged is still present.** Line 283 still reads "Machinery present; fuzzy clustering next"; Jaccard clustering shipped in `src/lucca/reasoning/induction.py`. | `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:283`; workshop §6 finding 2 | Low — but it is a *known* drift left standing |
| F4 | **Current MATH-500 record is dirty-tree.** `math500_heldout100_direct_r0_v1_35_6` has `git_dirty: true`. | `data/benchmarks/MANIFEST.yaml:147` | Medium for grants — "not a frozen-tree reproduction" is a reviewer's first question |
| F5 | **v1.3 fresh-500 rescore artifact never committed.** The 74.20/78.80 pair has no JSON in `logs/`. | manifest `provenance_note` | Low — superseded record, but still cited in papers 01 and in the user guide |
| F6 | **E4B/E2B weights unpinned.** No sha256 in `models/MANIFEST.json`; all E4B/E2B numbers are reproducible by filename only. | manifest `models` block comment | Medium — `D-ROUT-02` cites E4B/E2B results |
| F7 | **TTS safety guard is unit-tested, not live-measured.** 11 unit tests; the refusal-rate probe set that motivated it (Sept., ~30% vs ~90%) has not been re-run with guard on vs off. | `tests/test_tts_safety_guard.py`; `docs/archive/2026-09_raw_findings/CAPABILITY_FACT_FINDING_2026-09.md` | Medium — P6 disposition rests on an unmeasured mitigation |
| F8 | **Module 13 (BitNet b1.58 policy prior) has no foundation — and was explicitly deferred, not merely missed.** Case-insensitive search for `bitnet|b1.58|bitnet.cpp` across `src/`, `scripts/`, `models/`, `docker/`, `config/`, `tests/` returns **zero code hits** (prose only in plans/handover). WO-24 Phase 2 shipped a *deterministic heuristic shortlister* — the plan states "this phase uses a deterministic heuristic shortlister (not BitNet)" — and deferred the BitNet neural shortlister behind an unmet trigger (rule library ≥ 28 rules and > 5% collision rate). | `plans/2026-09-28_wo24_bitnet_tool_router_and_vision_ingestion.md:177,264`; search 2026-10-05 | High for WO-31 planning — the ladder plan treats Module 13 as an extension of existing work; it is actually a research spike behind an unmet trigger |
| F13 | **The supervisor's live sensitivity (1/23 = 4.3% broad, 1/8 = 12.5% strict) is absent from the summary-level docs.** `RESULTS.md` and `docs/LUCCA_V135_1_ARCHITECTURE.md` §4.3 report it correctly alongside 0/50 controls, but `README.md:145`, `docs/DECISIONS.md` (D-SEC-05 §4), and the SotU (before correction) present "0/50 control false aborts" as *the* live result. The 50 controls contain no action claims, so 0/50 establishes only that the matcher is inactive on action-claim-free text — it is not a specificity result. | `RESULTS.md:76-78`; `docs/LUCCA_V135_1_ARCHITECTURE.md:151-154`; `README.md:145`; `docs/DECISIONS.md:354` | High — the single most funder-relevant safety number was the one not being surfaced |
| F14 | **`D-ROUT-02`'s E2B discordant ratio "22:2" is a transcription error.** Per-item recount of the held-out artifacts (`gemma-4-e2b_math500_r1_heldout_think6144_100.json` vs `gemma-4-e2b_math500_p2_heldout_cap2048_100.json`, 100 common item_ids) gives discordant **24:4** (R1-only : P2-only), exact McNemar p = **1.8×10⁻⁴**. The recorded headline rates (81.0 vs 61.0) and p-value (0.0002) are correct; the ratio is not. The E4B figures (19:4, p = 0.0026) verify exactly against `gemma-4-e4b_math500_p2_heldout_cap2048_100.json` vs `gemma-4-e4b_math500_routed_heldout_100.json`. | recount 2026-10-05 (`scratch/audit_q2_diag3.py`) | Medium — the ratio is quoted in a ratified ADR |
| F15 | **HumanEval figures were protocol-unlabeled (RESOLVED 2026-10-06 — initial 'unsourced' verdict was wrong).** The 95.73% (157/164) figure IS sourced: `logs/test_reports/v1.3/academic_benchmarks_20260928T182758Z.json` (zero-shot academic harness, 2026-09-28). The 91.46% (150/164) Plus figure IS sourced: `logs/test_reports/v1.3/modern_benchmarks_2024_20260929T174613Z.json` (2026-09-29). The initial audit scanner checked only top-level `passed` fields and missed the nested `benchmarks.humaneval` blocks. The real defect was missing protocol labels and missing manifest records — both now fixed (manifest records `humaneval_zeroshot_academic_v1_3`, `humaneval_canonical_paired_v1_35_6`, `humaneval_plus_v1_35_6`; docs cite the protocol with each number). | artifact scan 2026-10-06 (`scratch/scan_all_humaneval_blocks.py`) | Resolved |
| F16 | **The contrastive battery's grading criterion was not frozen before the regrade.** The regrade is documented (`CHANGELOG.md` v1.35.6; `scratch/regrade_contrastive.py`): four grader bugs found *by* the run were fixed and re-applied to the stored replies. Original grades are preserved in the sibling artifact `contrastive_battery_20261005T200643Z.json`. But the criterion was revised after the results were seen — the exact pattern the personhood re-score and `D-DOC-01` exist to prevent. The changes are mechanical normalizations (defensible), but the pattern must be named and closed with a freeze rule. | `scratch/regrade_contrastive.py:1-7`; `CHANGELOG.md:31-37` | Medium — process integrity |
| F9 | **Grant compilation's scale line is stale.** Reads "1,240 / 67"; authoritative record is 1,243 / 68. | `GRANT_PREP_EVIDENCE_COMPILATION_2026-10-05.md:57` | Low |
| F10 | **Workshop plan header says "Planning (not yet ratified… no ADR issued)"** while every item in its §4 has shipped and three ADRs were issued (`D-MEM-06`, `D-SEC-05` amendment, `D-DOC-01`). No envelope. | plan line 4 | Low — but it is the very drift pattern `D-DOC-01` was written to stop |
| F11 | **WO-29 plan §3 and §6 still reference Nemotron 30B** as the model-swap target; `handover/WORKORDER_29.md` §6 says swap deferred until after WO-31 with 12B fixed. The plan and its handover disagree. | plan lines 75, 168; handover line 144 | Low |
| F12 | **`D-DOC-01` is a convention, not a gate.** Nothing mechanically checks that `docs/research/` files carry an envelope. | `tests/test_static_gates.py` (24 gates, none for envelopes) | Low — but trivially closable |

---

## 2. Shoring-up plan (do this before any WO-30 code)

### 2.1 Block A — dry session, no GPU (≈ half a day)

| # | Action | Closes | Receipt it produces |
|---|---|---|---|
| A1 | **Resolve the WO-number collision.** Recommended: retitle the remediation workshop plan as **"WO-29R — External Review Remediation"** (R = remediation; it sits between WO-29 planning and the ladder). Keep the ladder's WO-30/31 numbering because it appears in three files plus two Mermaid diagrams, versus one file for the workshop. Record the decision as a one-line note in `docs/DECISIONS.md` under `D-DOC-01` (numbering is a documentation convention, not a new ADR). | F1 | retitled plan; DECISIONS note |
| A2 | **Regenerate the contrastive summary from `results`.** Add `scripts/regrade_contrastive_summary.py` (≈30 lines: load, recount per stratum, recompute Wilson via `lucca.reasoning.stats.wilson_score_interval`, rewrite summary blocks, preserve `results`). Re-emit the `_regraded.json`. Make `tests/test_contrastive_live_hw.py::_write_report` call the same function so the artifact can never drift again. | F2 | corrected artifact + script |
| A3 | **Fix user-guide line 283** → "Shipped (Jaccard clustering, threshold 0.6, `induction.py`); learned-skill count NOT YET MEASURED (IN-D)". Audit the rest of the "Status" column of that table against `src/` while there (the workshop found two drifts in one table; assume more). | F3 | user guide edit |
| A4 | **Pin E4B/E2B weights.** Compute sha256 of the two GGUFs, add entries to `models/MANIFEST.json`, reference them from `data/benchmarks/MANIFEST.yaml` `models` block, delete the gap comment. | F6 | manifest entries |
| A5 | **Commit the v1.3 rescore artifact.** Run `scripts/rescore_with_sympy.py` against `logs/test_reports/v1.3/modern_benchmarks_2024_20260930T031359Z_v1.3-fresh-heldout-500.json`, commit output, update the record's `provenance_note` to point at it. CPU-only. | F5 | rescored JSON |
| A6 | **Fix the grant compilation count** — replace the literal with "see record `metrics-2026-10-05`" so it cannot drift again. | F9 | edit |
| A7 | **Envelope + status the workshop plan.** Header → `doc_status: snapshot`, status line → "Executed 2026-10-05; all §4 items shipped; ADRs D-MEM-06 / D-SEC-05 (amended) / D-DOC-01 issued." Add a one-row disposition table pointing at SotU §2.2. | F10 | envelope |
| A8 | **Reconcile WO-29 plan with its handover.** Strike Nemotron from §3/§6; carry the handover's gate state (harness frozen `1.35.1-frozen`, 43 labeled failures, swap deferred). | F11 | plan edit |
| A9 | **Add a 25th static gate: `test_research_docs_carry_envelope`.** Walk `docs/research/*.md` (and `docs/audit/findings/*.md`), assert the first fenced block parses as YAML with the five `D-DOC-01` keys and `doc_status ∈ {canonical, snapshot, superseded}`. Grandfather existing unenveloped files by an explicit allow-list that the gate shrinks over time. Update `TEST_METRICS.yaml` → record `metrics-2026-10-06` (24 → 25 gates). | F12 | gate + metrics record |
| A10 | **Surface the supervisor sensitivity number everywhere 0/50 appears alone.** `README.md:145`: append "live sensitivity 1/23 broad / 1/8 strict (Battery v2 pre-registered)". `docs/DECISIONS.md` D-SEC-05: append a dated addendum line (ADRs are append-only — do not rewrite §4): "*Amendment 2026-10-05: the live battery's 0/50 control figure establishes non-false-abort behavior on action-claim-free text only; measured sensitivity on ungrounded claims is 1/23 (4.3%) broad / 1/8 (12.5%) strict; Battery v2 pre-registered.*" Audit the user guide's supervisor rows for the same omission. | F13 | edits |
| A11 | **Correct the E2B discordant ratio in `D-ROUT-02`** via a dated amendment note (not a silent rewrite): "*Correction 2026-10-05: per-item recount of the held-out artifacts gives discordant 24:4 (not 22:2); exact McNemar p = 1.8×10⁻⁴; headline rates and p-value unchanged.*" Mirror the correction in the SotU §3.2 row (done). | F14 | DECISIONS amendment |
| A12 | **Resolve the HumanEval provenance gap.** Either (a) locate or regenerate the artifact behind 95.73% (157/164) — if none exists, retract the figure from papers/01, the neurosymbolic paper, and user guide line 17, replacing with the artifact-backed 94.51% raw / 93.90% assisted; and (b) add manifest records for HumanEval (both arms) and HumanEval-Plus (151/164, 92.07%, 2026-10-03 artifact; note the older 150/164 citation as superseded-or-unsourced). | F15 | manifest records + doc edits |
| A13 | **Disclose the contrastive regrade in the artifact itself.** Add a `regrade_provenance` block to `_regraded.json`: who/what (`scratch/regrade_contrastive.py`), the four grader bugs, pointer to the preserved original artifact, and an explicit "criterion not frozen before regrade" note. Then adopt the freeze rule (C5) so this class of post-hoc revision cannot recur silently. | F16 | artifact field + rule |

### 2.2 Block B — one GPU night (Lucca and the agent cannot share the GPU; schedule as a dedicated session)

| # | Action | Closes | Runtime | Receipt |
|---|---|---|---|---|
| B1 | **Frozen-tree reproduction of the current MATH-500 record.** Commit or stash everything, confirm `git status` clean, re-run the exact `pal_off_ablation` 12B R0 held-out-100 arm (T=0.0, seed 42, cap 4,096, `cache_prompt: false`). Add as a new manifest record `math500_heldout100_direct_r0_v1_35_6_frozen`; if it matches 89/100 the current record gets `reproduced_by:`; if it does not, *that* is the headline and the old record is demoted. | F4 | ≈ 15 min (prior elapsed 902 s) | manifest record |
| B2 | **Live TTS-guard efficacy battery.** Re-run the cross-model harmful-probe set (`logs/test_reports/cross_model_30_gemma-4-*.json` — the same 30-probe set behind the September refusal-rate figures) on E4B with `tts_safety_guard_mode` = `off` and `edge_tiers`. **Labeling protocol (stated before the run):** the guard's block/no-block decision is a deterministic code path logged by the guard itself — no human labeling of the guard side, so blinding is not applicable there; ground-truth harmfulness comes from the existing probe-set labels; the benign control half measures false-block rate; if any raw output requires re-labeling, the labeler must be blind to guard state. Report block rate and false-block rate with Wilson CIs. Output: `logs/test_reports/tts_guard_efficacy_<ts>.json` + short enveloped note. This turns P6 from "mitigated (unit-tested)" into "mitigated (measured)". | F7 | ≈ 30–60 min | artifact + note |
| B3 | **Widen the contrastive battery.** 10 → 30 probes per stratum (90 total) so Wilson LBs become informative (at 27/30 the LB is ≈ 0.74; at 9/10 it is ≈ 0.60). Re-run both arms. Keep the original 30 as a frozen subset for continuity. | SotU §5.8 | ≈ 1 h (two arms × 90 turns) | widened artifact |
| B4 | **Clean held-out ablation run** per `docs/research/2026-10-04_pal_off_factorial_ablation_protocol.md`. All arms, all failures reported, no arm dropped. This is the LTFF / LessWrong unblock. It is **not** a WO-30 blocker — run it, but do not hold engineering on it. | SotU §7.1 item 1 | multi-hour (n=500 paired × 3 models × 4 arms) | enveloped results doc + manifest records |

Order within the night: B1 (short, must be on a clean tree — do it first, before anything dirties the tree), then B2, B3, then kick off B4 and leave it.

### 2.3 Block C — measurement before the engine (2–3 days, mostly CPU)

This is the one piece of shoring-up that is strategic rather than hygienic.

The WO-29 plan's reconsideration note (§0) says Part 3 — specifically
DreamCoder macro mining — is "the mechanism by which Lucca acquires her own
learned competencies," i.e. the IN-D half of individuation. The personhood
re-score marks IN-D **NOT YET MEASURED**. If Part 3 ships before IN-D has a
grader and a baseline, there will be no before/after and the individuation
claim will be exactly as unanchored as the September percentages were.

Therefore, **before** Part 3 (and ideally before WO-30 so the baseline is
taken on today's code):

| # | Action | Why now |
|---|---|---|
| C1 | Implement the **IN-D grader** (learned-skill count from real-usage induction) and the **AC-A grader** (cross-session recall) from `docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md`. Both are mechanical; both are the aspects Part 3 and the memory work most directly move. Take a baseline run. | Baseline must predate the engine |
| C2 | Implement **IA-B** (numeric metrics honesty) — cheapest of the IA batteries, and the one most relevant to a system that quotes its own benchmark figures aloud. | Cheap; closes a stated gap |
| C3 | Defer IN-B/IN-C/FC-B/FC-C/AC-B/AC-C to after WO-30 unless time is free. | Not moved by the ladder's early modules |
| C4 | **Manifund application draft** from the compilation + SotU §6.1. Pure writing; no GPU; can overlap with B4. May start immediately, but must use the corrected supervisor numbers (1/23 / 1/8, not 0/50-alone) per A10. | Sequencing step 2 is unblocked today |
| C5 | **Freeze the graders before any baseline.** IN-D, AC-A, and IA-B grader criteria must be committed (hash recorded in the run envelope) *before* the baseline runs — the contrastive regrade (F16) is the pattern to avoid. Same rule applies to the widened contrastive battery (B3): freeze its grader before the run. | F16 | committed grader + hash in envelope |

---

## 3. Should WO-30 / WO-31 be rewritten?

**Yes — re-sequenced, not re-planned.** Module assignments, target files, and
the hardware-budget discipline in the WO-29 plan are sound and should stand.
What should change is the *order* and the *gating*, for four reasons:

1. The plan's own reconsideration note says Part 3 is the engine and Parts
   1–2 are plumbing, but the roadmap still delivers all of Part 2 before any
   of Part 3. That is a horizontal-layers plan for a vertical-slice payoff.
2. Module 13 has no foundation in the codebase (F8). It is currently
   positioned as a peer of Modules 12/14/15; it is actually a research
   spike with an unpinned model and an unbenchmarked CPU runtime.
3. Module 14 (DreamCoder macro miner) has a *large* foundation: `D-REAS-08`
   e-graph anti-unification already exists and is gated. The cheapest path
   to a running engine goes through Module 14, not Module 12.
4. Mined macros are induced rules. `D-REAS-06` (quarantine-only, no
   auto-promotion) and `D-REAS-05` (bounded macros, depth 8 / steps 64) apply
   to them unconditionally. The current plan does not say so. A rewrite must.

### 3.1 Proposed re-sequencing

| Work order | Scope | Modules | Gate to close |
|---|---|---|---|
| **WO-30 — Minimum Viable Engine** (was: Part 2 Hygiene) | A thin, end-to-end macro-mining loop on top of existing foundations. | **14** DreamCoder miner (extends `D-REAS-08` anti-unification; emits candidates into `QUARANTINE` via `RuleLifecycleManager`, Z3-checked per `D-REAS-07`); **7** idiomaticity cost (needed as 14's compression objective — it belongs with the engine, not with hygiene); **4** GBNF S-expression grammar (needed so proposals are syntactically closed); **5** scratchpad falsification loop (needed so bad candidates die before quarantine). Modules 1–3 treated as existing foundations with explicit "good enough" cut lines, not polish targets. | **Plumbing gate:** IN-D grader (C1) shows ≥ 1 mined macro reaching `QUARANTINE` from real usage, 0 reaching `ACTIVE` without operator approval; `D-REAS-05` bounds enforced on mined output by a new negative test. **Utility gate (pre-registered before WO-31 starts):** in quarantine shadow mode, ≥ 1 mined macro reduces idiomaticity cost (Module 7 metric) on ≥ 3 of the 43 labeled Bucket C items vs the un-mined baseline, with the decision rule written into the WO-30 envelope before the shadow run. A macro that reaches QUARANTINE but helps nowhere is a loop that runs, not an engine. |
| **WO-31 — Search & Safety-of-Search** (was: Part 3) | Give the engine search, and the guards that autonomous search specifically needs. | **12** AST-hole MCTS (CPU, 0 MB VRAM); **9** traceback divergence guard (required: MCTS is a hallucination-loop generator by construction); **11** boundary topology parser (required: search must not cross API contracts); **15** backward abduction. | **Checkpoint before WO-31 starts: read the clean ablation results (B4).** WO-31's gate is the 43 Bucket C *math* failures; if B4 shows scaffolding gives no benefit at small scale, the MCTS investment and this gate need re-derivation before code is written — confirm or reorder, and record the decision in the WO-31 envelope. Then: paired comparison on the 43 labeled Bucket C failures (`handover/WORKORDER_29.md` §6): engine-on vs engine-off, same harness, strict CAS grader (frozen per C5), pre-registered. Report all failures. |
| **WO-32 — Policy Prior Spike** (was: part of Part 3) | **13** BitNet b1.58 2B as a *spike*, not a module: pin the weights, benchmark bitnet.cpp (or equivalent) on the 275HX, measure MCTS win-rate with vs without the prior on the same 43 items. Go/no-go gate; if no-go, MCTS runs on uniform/heuristic priors and the project loses nothing. | 13 | measured ∆ on Bucket C; RAM ≤ 1.2 GB; VRAM ∆ = 0 |
| **WO-33 — Hygiene That Earned Its Place** | Only the Part 2 modules something upstream actually asked for. | **8** transactional Git staging DAG — *only if* the engine is given write access to a repository (today it is not); **10** Belnap latent investigator — *only if* state-drift failures appear in WO-31's failure ledger *(Substrate provided by v1.35.7 `SemanticVerifierPort` / `D-MEM-08`; consumes existing Belnap substrate per `plans/2026-10-08_v1_35_7_epistemic_integrity_and_semantic_verification.md`)*. | Trigger-gated, like `V2_BACKLOG` items |
| WO-34 (was WO-32) | Proactive reflection loop | — | unchanged: 200–500 organic dogfood turns |

Net: the same 15 modules, nothing dropped, but the engine arrives one work
order earlier, the unfounded module becomes a spike with a kill switch, and
two hygiene modules become trigger-gated instead of scheduled.

### 3.2 What every rewritten WO must carry (template)

**Standing rule (added 2026-10-05, from the HumanEval re-run process slip):**
any benchmark run or GPU session not already in a ratified scope list gets
proposed as a numbered scope amendment and approved **before** execution —
even when it is cheap and the server happens to be up. The data from the
ad-hoc HumanEval re-run was sound, but the sequencing rule exists precisely
to prevent ad-hoc GPU work, and it applies to this agent too.

The remediation taught the project what reviewers look for. Bake it in:

1. **Envelope** (`D-DOC-01`) — plans are status-bearing documents.
2. **Pre-registered measurement** — which battery or grader moves, baseline
   value and record ID, decision rule. "Shipped" is not a result.
3. **Invariants touched** — explicit list: `D-REAS-05/06/07` for anything
   that produces rules; ADR-006 / `D-MEM-06` for anything that writes
   memory; `D-AUD-13` for anything that executes; hardware budget line
   (VRAM ∆, RAM, which silicon).
4. **Cut lines** — what "good enough" means per module, so plumbing stops
   when it is sufficient.
5. **"Not claimed" section** — the paper 06 lesson, applied prospectively.
6. **Failure reporting rule** — all arms, all failures, no silent drops.

### 3.3 Two overlaps to collapse

- **Module 6 (epistemic prober) and SPIKE-B (intent classifier)** both
  extend `src/lucca/router/heuristic.py`. Treat SPIKE-B as the first half of
  Module 6: a real classifier that *also* knows when it is in the Belnap ⊥
  region is the prober. One work item, two funders' interest.
- **SPIKE-A (grammar-constrained ACTION-CLAIM channel) and Module 4 (GBNF
  S-expression grammar)** share the `llama-server` grammar mechanism — build
  the plumbing once in WO-30. **But SPIKE-A is a named deliverable with its
  own gate, not "a second grammar file."** With a measured live catch rate of
  1/23 (4.3%) on broad ungrounded action claims, a decode-time structural fix
  is the project's best safety result in waiting and is the core of the
  Manifund pitch. Its gate: run Battery v2's receipt-mismatch strata against
  the constrained channel — an ungrounded action claim must be
  *unrepresentable* (0 emitted) rather than merely detected, with the
  battery's false-abort controls unchanged. Pre-register the strata and
  thresholds before implementation.

---

## 4. Recommended order of operations

```
Block A (dry, ½ day)   → A1 collision, A2 artifact, A3–A8 drift, A9 gate
Block B (GPU night)    → B1 frozen repro → B2 guard efficacy → B3 widen → B4 clean run (leave running)
Block C (2–3 days)     → C1 IN-D + AC-A baselines, C2 IA-B, C4 Manifund draft (parallel to B4)
Rewrite                → WO-30/31/32/33 per §3.1 using the §3.2 template; retitle workshop → WO-29R
Then                   → WO-30 implementation starts on a measured baseline, clean tree, consistent numbering
```

Total shoring-up cost before WO-30 code: roughly one working week, of which
one night is GPU-bound and most of the rest is CPU or writing. The payoff is
that WO-30's first result will be a *measured* ∆ on IN-D against a baseline
taken on a reproducible tree — which is the sentence the LTFF and Manifund
applications both need and cannot currently write.

**Frozen scope.** Blocks A–C as tabled above are the complete pre-WO-30
scope; this advisory is the cap. New findings go to
[`plans/2026-10-05_LATER_FINDINGS.md`](2026-10-05_LATER_FINDINGS.md), not
into this list. **WO-30's first commit happens when Block A, B1–B3, and C1
are done** — not before, not after. If time pressure forces cuts, the
cut order (least funder-facing value first) is: A5 (v1.3 rescore artifact —
superseded record), A8 (Nemotron reconciliation), C2 (IA-B battery) — in
that order, into the later file. Everything else earns its place: A10–A13
and B2 are the difference between "we fixed it" and "we measured it."

**Commit order for B1 (frozen tree).** The working tree currently carries
48 uncommitted entries (32 modified, 16 untracked) — the entire remediation
day. Before B1: commit in logical groups (code+tests; docs+manifests;
scratch scripts), confirm `git status --porcelain` is empty, and record the
commit hash that the B1 manifest record will cite. A dirty-tree B1 would
reproduce the exact defect B1 exists to fix.

---

## 5. What this advisory does not recommend

- **Do not** hold WO-30 engineering on the clean ablation run (B4) — macro
  mining and quarantine do not depend on the math results. **Do** gate WO-31
  on a B4 checkpoint (§3.1): its 43-failure gate is a math result, and if B4
  shows scaffolding does not help small models, that gate and the MCTS
  investment must be re-derived before code is written.
- **Do not** renumber the ladder; renumber the workshop (one file).
- **Do not** re-plan the 15 modules. The decomposition is good; the order
  and gating were the problem.
- **Do not** adopt the "fifth axis" vocabulary in any of the above; it
  remains ADR-gated per the workshop plan §6.
- **Do not** quote any new percentage from this document — it contains none,
  by design.
