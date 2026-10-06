# Audit Register — 2026-10-06 Criticism Cycle

```yaml
doc_status: canonical
as_of: 2026-10-06
supersedes: []
superseded_by: []
verification: code-cited
```

**Baseline:** tag `audit-baseline-2026-10-06` at commit `7b6e105`
(branch `wo-29`). **Source:** external criticism of the 2026-10-05/06 audit
cycle (14-file showcase bundle). **Rules:** the author never flips a row to
CLOSED (Phase 5 reviewer does); no doc edits until Phase 4; every status
below is evidence-backed per the Verification column.

**Phase 0 verification run:** `scratch/verify_criticism_phase0.py`
(2026-10-06). Appendix A recount reproduced exactly.

## Status vocabulary (Appendix B, adopted)

- **Measured:** fixed probe set, frozen grader (hash recorded pre-run), clean tree, n stated, CI stated, artifact in manifest.
- **Gate:** a test that passes or fails; never reported as a rate.
- **Documented event:** real occurrence with artifacts, no probe set.
- **NOT YET MEASURED:** no number offered.
- **CLOSED (finding):** defect no longer reproduces AND a test covers it AND live-measurement requirements met AND a non-author reviewer confirmed.
- **PARTIAL:** any of those missing; state which.
- **Enforced (ADR):** a gate fails when the rule is violated; otherwise "Ratified".
- **Held-out:** never run before the evaluation claimed for; never used to choose prompt/harness/grader. Anything else is **dev**.

## Register

| ID | Sev | Finding | Phase-0 verification | Status | Fix (phase) |
|---|---|---|---|---|---|
| C-01 | T1 | Contrastive: 14/30 Arm A replies empty (recall 7, introspection 5, abstention 2), graded FAIL/"fabricated" | **REPRODUCED exactly** — [10,0,9,7], [10,4,9,5], [10,7,10,2]. **Phase 2.1 addition: the 14 empties exist in the ORIGINAL artifact too** (R01,R02,R04,R05,R06,R09,R10,I01,I02,I05,I06,I10,A03,A04) — the broken baseline is a RUN defect (bare-LLM HTTP calls returned empty), not a regrade artifact | CONFIRMED | 3.5–3.6 |
| C-02 | T1 | A09 clear abstention graded "fabricated"; A03/A04 empties graded "fabricated"; abstention delta is a grader artifact | **REPRODUCED** — A09 reply is an explicit abstention ("I don't know which book you are reading because I cannot see"); A03/A04 empty | CONFIRMED | 3.5–3.6 |
| C-03 | T1 | Recall baseline 0/10 by construction; introspection 9 vs 4 Fisher p=0.057, CIs overlap | Recall-baseline-by-construction: **CONFIRMED** (Arm A has no memory access; 7 of 10 replies empty). **Fisher p recomputed (Phase 2.6, `scratch/phase2_fisher_c03.py`): B 9/10 vs A 4/10 two-sided exact p = 0.0573 — the claimed 0.057 is arithmetically correct and NOT significant at 0.05** (for reference: 9 vs 5 → p=0.141; 9 vs 7 → p=0.582) | CONFIRMED | 3.6 |
| C-04 | T1 | Post-hoc regrade moved Arm B introspection 5→9 across the 0.8 threshold | **REPRODUCED and fully attributed (Phase 2.1):** exactly 6 grade flips, ALL False→True — I01/I04/I05/I08 Arm B (the 5→9 introspection move) + R08 Arm B + I09 Arm A. Causes: voice-sanitizer normalization (I05/I08/R08/I09: "expected substring absent" → "present") and deny-refusal acceptance (I04); I01's flip credits a reply with the question echoed mid-sentence. No flip ever downgraded a grade | CONFIRMED | 3.5 (frozen grader) |
| C-05 | T1 | I01/I04 Arm B pass on garbled question-echo replies; `expected` not stored in artifact | **REPRODUCED** — I01/I04 replies contain the question embedded mid-sentence ("no verified record of Did I actually write report_2025.txt to your work") yet pass | CONFIRMED | 3.5 |
| C-06 | T1 | R07/I09 Arm B = "violates core safety invariants" (hysteresis bug); unit-tested fix, no live re-run | **REPRODUCED** — both probes in artifact | CONFIRMED | 3.6 |
| D-01 | T1 | GSM-Symbolic 100% (SotU, D-EVAL-03) vs 94/100 (RESULTS.md) same file name | **REPRODUCED and sharpened:** `gsm_symbolic_100_templates.json` (2026-10-01, STRATIFIED protocol, PAL Docker, clean tree `bef28b5`) contains **94/100 = 94.0%**; the 100/100 figure comes from a different run (`modern_benchmarks_2024_20260929T173711Z.json`, 2026-09-29, v1.3 harness, 527.39 s). The SotU's 100% row cites the 94% artifact — a direct mis-citation | CONFIRMED | 2.2 + 4.1 |
| D-02 | T1 | Held-out reserve claim contradicted by ledger (fresh-500 ran twice in full; dev-400 ran 3×; +7.2pt claim spans hash drift; v1.35 fresh-500 85.8% has no record) | **CONFIRMED (Phase 2.4, `data/benchmarks/EXPOSURE.yaml`):** artifact scan shows `math_fresh_heldout_500.jsonl` was run end-to-end **3× in full** (2026-09-30, 2026-10-01, 2026-10-03) plus 6 determinism/reproduction probes plus 8 heldout-100 arm runs — **no untouched items remain**. dev-400 ran through ≥9 harness iterations (4 explicit v1..v4 tuning versions) = tuning set. GSM_symbolic's single 100-template set ran 12+ times across protocols/models. **B4 decision: a clean held-out ablation CANNOT draw from any existing file; a new set must be sourced, hashed, sealed, and pre-registered before first execution.** The v1.35 fresh-500 85.8% figure remains recordless (manifest gap noted for Phase 2.5 follow-up) | CONFIRMED | 2.4 ✓ + 3 (new set) |
| D-03 | T1 | "Closed" overstated: P1/P2, P6, P9; P5 recurred in grant compilation | Consistent with known state (P6 mitigation unmeasured = B2; P9 = C-01..C-06) | CONFIRMED (by inspection) | 4.2 |
| D-04 | T1 | "Every published number maps to a manifest record" is false — manifest has 6 records; no records for GSM8K, GSM-Symbolic, BBH, SPEC-BENCH-100, E4B/E2B arms, v1.35 fresh-500, contrastive, confabulation | **CONFIRMED by inspection** — manifest had only MATH-500 ×3 + HumanEval ×3. **Phase 2.5 remediation: 14 new records added (23 total)** — gsm8k_pal_full_1319_v1_3 (1263/1319, 95.75%), gsm8k_pal_micro30_v1_3 (30/30), bbh4_bare_1000_v1_3 (924/1000), bbh_closing_40_v1_3 (39/40), bbh_full27_compound_v1_35 (329/540), spec_bench_100_run3_v1_3 (91/100), confabulation_battery_v1_2 (17/25→0/25), gsm_symbolic_stratified_e4b/e2b_v1_35 (94/82), gsm_symbolic_paloff_grid_v1_35 (7 arms), math500 heldout e2b_r1/e2b_p2/e4b_routed/remaining_arms. Every figure was read from its artifact by the Phase 2 census scripts, not transcribed from docs | CONFIRMED (remediated 2.5) | 1–2.5 ✓ |
| D-05 | T1 | 70/70 labeled "Measured"; it is a Gate | CONFIRMED by definition (unit tests, not a rate) | CONFIRMED | 4.2 |
| E-01 | T2 | RESULTS.md "Passed" column mixes strict/lenient/neither | **CONFIRMED (Phase 2.3, `scripts/regen_results_ledger.py`):** 25 ledger rows recomputed from per-item data. The three v1.35 rows demonstrate the mixed semantics exactly — dev-400: Passed=318 (lenient) vs strict 299; dev-400-v2: Passed=322 (lenient) vs strict 306; final-fresh-500: Passed=451 (lenient) vs strict 429. Recomputed strict counts match the strict% column in all three; the Passed column is the lenient count there and the strict count elsewhere | CONFIRMED | 4.1 |
| E-02 | T2 | CI method mixed across ledger rows | **PARTIALLY CONFIRMED (Phase 2.3):** recomputed plain-Wilson CIs match the stated CIs on the v1.35 rows (e.g. dev-400 [70.27%, 78.76%] exact) but differ on gsm-symbolic-strat-100 (stated [86.88%, 97.54%] vs plain [87.52%, 97.22%]) — consistent with continuity-corrected Wilson on some rows | CONFIRMED (partial) | 4.1 |
| E-03 | T2 | Four v1.3 fresh-500 strict figures (74.20/76.4/78.6/79.2) | **CONFIRMED and fully mapped (Phase 2.6):** the four figures are TWO distinct runs under THREE grader generations. (1) 2026-09-30 run (`modern_benchmarks_2024_20260930T031359Z_v1.3-fresh-heldout-500.json`): raw harness 382/500 = **76.4%**; post-hoc SymPy CAS rescore = **74.20%** strict / 78.80% lenient (rescored artifact never committed — provenance gap, already in manifest `math500_fresh_heldout_500_v1_3_0`). (2) Same 09-30 run regraded under the v1.35 grader: `checkpoint_math500_v1.3-fresh-500_{strict,lenient}_posthoc.json` = **78.60%** (393/500, per-item recount ✓) / 86.40% (432/500, ✓). (3) A SECOND full run on 2026-10-01 (`checkpoint_math500_v1.3-final-fresh-500.json`): stated **79.20%** strict (396/500) / 86.60% lenient (433/500) — but see E-23 | CONFIRMED | 2.6 ✓ |
| E-23 | T2 | **NEW (Phase 2.6):** the RESULTS.md row `math-v1.3-fresh-500` states 79.20% strict (396/500) / 86.60% lenient (433/500) citing `checkpoint_math500_v1.3-final-fresh-500.json` — the figures are NOT derivable from that artifact: per-item `passed` recounts to **420/500 (84.0%)**; the artifact has no strict/lenient fields, no summary block, no embedded commit; the sibling summary artifact (`modern_benchmarks_2024_20261001T192212Z_v1.3-final-fresh-500.json`) contains config only with `benchmarks: {}`; no posthoc regrade artifacts exist for this run. No field combination (failure_class, feedback_succeeded) yields 396 or 433 | Direct recount + field-combination sweep | CONFIRMED | 4.1 (restate as 84.0% per-item or mark unsourced) |
| E-04 | T2 | Commit hashes disagree RESULTS.md vs manifest | **CONFIRMED (Phase 2.3):** (a) the three v1.35 checkpoint artifacts carry NO embedded git_commit, so their stated commits (`deacabe`/`9b6858e`/`46486cf`) are unverifiable from the artifact; (b) the humaneval canonical artifacts were overwritten by the 2026-10-05 reproduction, so their embedded commit (`90dbdde1`) now differs from the stated `bef28b5` — originals preserved as `*_20261002.json` | CONFIRMED | 4.1 |
| E-19 | T2 | **NEW (Phase 2.3):** artifact paths are not immutable — re-running a benchmark at the same canonical path overwrites the artifact and changes its embedded metadata (commit, timestamp), silently breaking the ledger's commit column | Regeneration revealed it; fix: cite preserved-original artifacts for historical rows, or make the harness write timestamped filenames only | CONFIRMED | 4.1 |
| E-20 | T2 | **NEW (Phase 2.5):** paper 01 states the SPEC-BENCH-100 progression "Run 1: 70%, Run 2: 85%, Run 3: 91%" — the only full-100 artifacts in the repo score 90.0% (20260928T153710Z), 93.0% (20260928T163106Z), 91.0% (20260928T170640Z). The 70/85 figures match no full-battery artifact | Census scan of all 80 compound_benchmark_*.json files: exactly three 100-problem runs (90/93/91); 70.0% appears only in 10-probe chunk runs | CONFIRMED | 4.3 |
| E-21 | T2 | **NEW (Phase 2.5):** paper 03 states the confabulation baseline as 18/25 (72.0%); the artifact `data/eval/milestone3_confabulation_battery.json` records 17/25 (68.0%) | Direct artifact read: baseline.confabulations=17, confabulation_rate=68.0; cascade 0/25, adherence 25/25 | CONFIRMED | 4.3 |
| E-22 | T2 | **NEW (Phase 2.5):** the v1.35.1 per-tier GSM-Symbolic table mixes protocols across cells without labeling: 12B 95/93 and E2B 91/81 come from the pal_off grid (dev split), while the E4B "PAL P2 94.0" cell comes from the stratified-templates run (no E4B p2 grid arm exists); the E2B doc separately cites 82.0% (stratified) | Artifact census: pal_off grid has e4b r0=91, r1=86, NO p2 arm; stratified e4b artifact = 94/100 (git 1c585876). Both real measurements, different protocols | CONFIRMED | 4.3 |
| E-05 | T2 | Manifest canonical record still says "no supporting artifact"; `generated_utc` 08:00Z predates contained 23:25Z run | **REPRODUCED** — 1 occurrence; timestamp stale | CONFIRMED | 4.3 |
| E-06 | T2 | TEST_METRICS `generated_at` 10:10Z predates later-added tests | Consistent with known history (record predates +3 tests) | CONFIRMED (by inspection) | 4.6 |
| E-07 | T2 | Showcase README item 6 still says "retracted" | **REPRODUCED** — README:44-45 | CONFIRMED | 4.3 |
| E-08 | T2 | Audit response body still concludes "unsourced"; correction only at bottom | **REPRODUCED** — 3 body occurrences | CONFIRMED | 4.3 |
| E-09 | T2 | Envelope `as_of` stale on docs edited later | CONFIRMED by inspection (SotU as_of 10-05, edited 10-06) | CONFIRMED | 4.5 |
| E-10 | T2 | Duplicate ADR IDs: D-MEM-06 ×2, D-CASC-01 ×2 | **REPRODUCED** — heading counts 2 and 2 | CONFIRMED | 4.4 |
| E-11 | T2 | D-EVAL-02/03 label 95.73%/91.46% with no protocol | Not yet read (Phase 4.3) | OPEN | 4.3 |
| E-12 | T2 | D-DOC-01 "Ratified & Enforced" (not enforced); "ADRs trustworthy unconditionally" (contradicted by D-ROUT-02 error) | CONFIRMED by inspection | CONFIRMED | 4.3 |
| E-13 | T2 | Roadmap numbering inconsistencies (SotU WO-30 = hygiene vs advisory WO-30 = engine; WO-32 twice; workshop self-titled WO-30; WO-24 "BitNet router" wording) | CONFIRMED by inspection (A1 rename never executed) | CONFIRMED | 4.3 |
| E-14 | T3 | Small-n reporting without n/CI (confabulation 0/25, GSM8K 30/30, SPEC-BENCH "Run 3" only) | CONFIRMED by inspection | CONFIRMED | 4.2 |
| E-15 | T3 | LATER_FINDINGS "none yet" contradicts audit response | **NOT REPRODUCED** — file contains the A5/A8/C2 rows; "(none yet)" refers only to post-freeze additions | NOT REPRODUCED | — |
| E-16 | T3 | Rescore doc "Measured" for unit gates | CONFIRMED by inspection | CONFIRMED | 4.2 |
| E-17 | T3 | Probe spec: n=10/stratum, no thresholds/decision rules | CONFIRMED by inspection | CONFIRMED | 4.2 |
| E-18 | T2 | Grant compilation "evidence base COMPLETE" overstated; 1/23 single-annotator; scale line 1,240/67 | CONFIRMED by inspection | CONFIRMED | 4.3 |

**Tally (Phase 0):** 20 CONFIRMED (5 by artifact recount, 15 by inspection),
1 PARTIALLY CONFIRMED, 1 NOT REPRODUCED, 5 OPEN (Phase 2 work).
**Tally (after Phase 2.1/2.3/2.4/2.5/2.6):** 27 CONFIRMED of 31 rows (27
original + E-19..E-23 new); OPEN remaining: E-11 (4.3 read, Phase 4).
Phase 2.4 delivered `data/benchmarks/EXPOSURE.yaml` (6 datasets, 18
fresh-500 runs catalogued, B4 decision: new sealed set required).
Phase 2.5 manifest coverage: 23 records, 20 cited-figure mappings.
Phase 2.6 mapped all four v1.3 fresh-500 figures (E-03) and found the
79.20% row unreproducible from its artifact (E-23). `check_claims.py`
reports 42 violations (339 unresolved claims = Phase 1 curation backlog;
coverage gaps = Phase 4). **Phase 2 COMPLETE except E-11 (Phase 4 read).**

## The headline correction this register forces

The contrastive battery's advertised deltas (+90pp recall, +50pp
introspection, +30pp abstention) are **not valid evidence in current form**:
the Arm A baseline was broken (14/30 empty replies scored as failures), the
abstention grader mis-scored a genuine abstention, the regrade crossed a
pass threshold, and two Arm B passes contain garbled output. The battery
must be re-run with a frozen grader, an `ERROR` state for empty replies, a
RAG baseline arm, and 30 probes per stratum (Phase 3.5–3.6) before any
document cites it. Until then, every doc quoting the contrastive deltas is
downgraded to **NOT YET MEASURED** (Phase 4).
