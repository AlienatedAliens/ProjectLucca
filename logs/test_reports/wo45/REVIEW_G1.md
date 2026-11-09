# WO-45 Reviewer Sign-off — Gate G0 + G1

Reviewer: Zoo · Reviewed HEAD: `2587be2` · Date: 2026-11-09

## Verdict: **G1 APPROVED WITH CONDITIONS**

You may proceed to G2. Conditions C-1 through C-4 must land as the **first commits of G2**, before any G2 experiment runs.

## Independently verified (reviewer re-ran these)

| Check | Result |
| :-- | :-- |
| Baseline hashes (R-00) | All 4 frozen artifacts are byte-identical to `baseline_hashes.json` (360 report `d335733f…`, 360 REPORT.md `e90b4cec…`, lock `aeabb67c…`, corpus `db685e70…`). PASS |
| Commit discipline | 13 commits `c9706a1..2587be2`, one per task, `wo45(R-xx)` prefix, no squash. PASS |
| R-01 | `findstr /s /i "ed25519"` over papers, luccadocs, README and packet: 0 hits. PASS |
| R-02 | `findstr /s /i "deontic_ov"`: 0 hits. PASS |
| R-03 / R-04 | `191/300`, `290/300`, `49/50` now appear only inside retraction notes. PASS (see C-1) |
| R-08 | `build_launch_command` imported (`:40`) and called (`:242`). Arm A is batched before Arm B. Reuse branch removed. 26B-A4B tier label fixed. Provenance fields added. PASS (see C-3) |
| R-09 | The 60 report is now independent (`1591cc10…`), labelled as an in-sample dev smoke test, and has no live matrix copied in. Pre-fix numbers are labelled *not reproducible*. PASS |
| R-20 / R-23 / R-30 | Disclosures present in the README, the packet and Paper 4 (`main.tex`). `ctx=8192` is labelled in the packet and Paper 4. PASS (R-23 correctly marked PARTIAL) |
| Static gates | 40 passed (agent output; reviewer did not re-run). ACCEPTED |

## Conditions (fix first in G2)

**C-1 (R-04): the 50/50 was measured on older code.** `wo42_locked_holdout_150_report.json` locked `proof_policy.py = 9d810176…` and `neural_hazard_classifier.py = b5f08f10…`. Current files are `af188c46…` and `a37decbe…` (+399 lines in `82b1da8`). Also, the JSON key is `subsystems.proof_policy`, not `LOCKED_HZD`. Wherever `50/50 LOCKED_HZD` is cited, write: "`subsystems.proof_policy` = 50/50, measured on the WO-42 code state (2026-11-06); not re-run on WO-44 code." Optionally re-run that 50-item set once on current code, report the result as a new artifact, and change nothing afterwards.

**C-2 (README notice, item 4): "spliced cached 26B-A4B results" is itself unsourced.** The evidence only shows the harness *supported* reuse via `LUCCA_BENCH_REUSE_MODELS`. Which rows, if any, were reused in the final `82b1da8` report is unknown. Either cite a terminal log or log line that proves which model was reused, or rewrite it as: "the harness supported splicing cached per-model results; whether any row in the final report was reused cannot be determined from the artifacts." Apply the same fix to the packet's warning block. Do not replace one unsourced claim with another.

**C-3 (R-08 / R-05): the harness changes have never been run.** No artifact shows the new harness executing. G2 must include one full fresh run of the new harness on all 4 models into `web_evidentiary_burden_360_v2_report.json`, with every model row carrying `provenance: "fresh"`. Until that exists:
- the latency and VRAM numbers (0.49 / 0.65 / 1.50 / 1.60 s) stay attributed to the `82b1da8` harness;
- they keep the `ctx=8192` label.

Also confirm that `LLMSettings(... ctx=8192 ...)` at `:137-151` is a deliberate benchmark profile, or switch it to production `65536` and say which in the report.

**C-4 (wording): "Crucial disclosures" in the packet §2.2.** Change it to "Disclosures". This is the throat-clearing pattern from AGENTS.md §2.9.

## Reminders for G2/G3
- R-06 (end-to-end gate latency) must time the *combined* `evaluate_web_evidence_burden()` call, NPU and CPU, reporting p50/p95/p99. Not a sum of means.
- R-22 ablation and R-31 baselines run on the existing 360 and must be labelled "post-hoc analysis on the WO-44 corpus".
- **G3 (R-10) stop rule.** Commit the judge prompts and rubric *before* the judges see any reply. Grep the prompts for the forbidden terms listed in the executor prompt, rule 8. Then stop after G3 for review, as the executor prompt requires.
