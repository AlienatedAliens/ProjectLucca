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
| C-01 | T1 | Contrastive: 14/30 Arm A replies empty (recall 7, introspection 5, abstention 2), graded FAIL/"fabricated" | **REPRODUCED exactly** — [10,0,9,7], [10,4,9,5], [10,7,10,2] | CONFIRMED | 3.5–3.6 |
| C-02 | T1 | A09 clear abstention graded "fabricated"; A03/A04 empties graded "fabricated"; abstention delta is a grader artifact | **REPRODUCED** — A09 reply is an explicit abstention ("I don't know which book you are reading because I cannot see"); A03/A04 empty | CONFIRMED | 3.5–3.6 |
| C-03 | T1 | Recall baseline 0/10 by construction; introspection 9 vs 4 Fisher p=0.057, CIs overlap | Recall-baseline-by-construction: **CONFIRMED** (Arm A has no memory access; 7 of 10 replies empty). Fisher p: not yet recomputed | CONFIRMED (partial) | 3.6 |
| C-04 | T1 | Post-hoc regrade moved Arm B introspection 5→9 across the 0.8 threshold | **REPRODUCED** — pre-regrade summary block says 5 | CONFIRMED | 2.1 |
| C-05 | T1 | I01/I04 Arm B pass on garbled question-echo replies; `expected` not stored in artifact | **REPRODUCED** — I01/I04 replies contain the question embedded mid-sentence ("no verified record of Did I actually write report_2025.txt to your work") yet pass | CONFIRMED | 3.5 |
| C-06 | T1 | R07/I09 Arm B = "violates core safety invariants" (hysteresis bug); unit-tested fix, no live re-run | **REPRODUCED** — both probes in artifact | CONFIRMED | 3.6 |
| D-01 | T1 | GSM-Symbolic 100% (SotU, D-EVAL-03) vs 94/100 (RESULTS.md) same file name | **REPRODUCED and sharpened:** `gsm_symbolic_100_templates.json` (2026-10-01, STRATIFIED protocol, PAL Docker, clean tree `bef28b5`) contains **94/100 = 94.0%**; the 100/100 figure comes from a different run (`modern_benchmarks_2024_20260929T173711Z.json`, 2026-09-29, v1.3 harness, 527.39 s). The SotU's 100% row cites the 94% artifact — a direct mis-citation | CONFIRMED | 2.2 + 4.1 |
| D-02 | T1 | Held-out reserve claim contradicted by ledger (fresh-500 ran twice in full; dev-400 ran 3×; +7.2pt claim spans hash drift; v1.35 fresh-500 85.8% has no record) | Not yet verified (Phase 2.4) | OPEN | 2.4 |
| D-03 | T1 | "Closed" overstated: P1/P2, P6, P9; P5 recurred in grant compilation | Consistent with known state (P6 mitigation unmeasured = B2; P9 = C-01..C-06) | CONFIRMED (by inspection) | 4.2 |
| D-04 | T1 | "Every published number maps to a manifest record" is false — manifest has 6 records; no records for GSM8K, GSM-Symbolic, BBH, SPEC-BENCH-100, E4B/E2B arms, v1.35 fresh-500, contrastive, confabulation | **CONFIRMED by inspection** — manifest has only MATH-500 ×3 + HumanEval ×3 | CONFIRMED | 1–2.5 |
| D-05 | T1 | 70/70 labeled "Measured"; it is a Gate | CONFIRMED by definition (unit tests, not a rate) | CONFIRMED | 4.2 |
| E-01 | T2 | RESULTS.md "Passed" column mixes strict/lenient/neither | Not yet verified (Phase 2.3) | OPEN | 2.3 |
| E-02 | T2 | CI method mixed across ledger rows | Not yet verified (Phase 2.3) | OPEN | 2.3 |
| E-03 | T2 | Four v1.3 fresh-500 strict figures (74.20/76.4/78.6/79.2) | Not yet verified (Phase 2.3) | OPEN | 2.3 |
| E-04 | T2 | Commit hashes disagree RESULTS.md vs manifest | Not yet verified (Phase 2.3) | OPEN | 2.3 |
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
