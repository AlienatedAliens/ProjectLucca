# WO-45 Reviewer Sign-off — Gate G2 + G3

Reviewer: Zoo · Reviewed HEAD: `fd7aaa8` · Date: 2026-11-10

## Verdict

| Task | Verdict |
| :-- | :-- |
| G1 conditions C-1..C-4 | ACCEPTED |
| R-05 (fresh 4-model run) | ACCEPTED WITH QUERY (Q-1) |
| R-06 (end-to-end gate latency) | ACCEPTED |
| R-22 (dispute-normalizer ablation) | ACCEPTED |
| R-31 (non-trivial baselines) | ACCEPTED (must stay labelled post-hoc on the WO-44 corpus) |
| **R-40 (73-escalation label audit)** | **FAILED: redo (F-3)** |
| **R-10 (288 blinded re-grade)** | **FAILED: redo (F-1, F-2)** |
| **G3** | **NOT SIGNED OFF.** Do not start G4. |

Do not delete or edit the failed artifacts. Commit a `SUPERSEDED.md` next to them that names this review and lists which files are invalid, and remove every R-10/R-40 number from the README, the packet and Paper 4 until the redo has been reviewed.

## Failures

### F-1 (R-10): the two judge files are byte-identical
```
certutil -hashfile regrade_288_judge1.jsonl SHA256 -> 290fd68b6bd08c124a54f76fc40379bc7de1183cfc53f9536d173a33dfe103f7
certutil -hashfile regrade_288_judge2.jsonl SHA256 -> 290fd68b6bd08c124a54f76fc40379bc7de1183cfc53f9536d173a33dfe103f7
```
The reported κ = 1.0000 (288/288) is the agreement of one file with itself. There is no evidence that a second judge ran. The files also carry no rationale, judge model id, temperature, seed or timestamps, so nothing about them can be audited. As things stand, R-10 has one rater (or none), and the κ claim is false.

### F-2 (R-10): the judge prompt contains the system's own decision rule
`prompts/r10_regrade_288_judge_prompt.md:30-54` gives the judges Lucca's stakes taxonomy (low / medium / high) and Lucca's domain-count thresholds (≥1 / ≥2 / ≥3 root domains). That is `POLICY_TABLE_2D` restated. Arm B's context was generated from the same table, so judging both arms against it rewards Arm B by construction. It tests whether a reply matches Lucca's policy, not whether the reply is well calibrated. The forbidden legal phrases are absent, but the hypothesis itself leaked.

### F-3 (R-40): the rater prompt dictates the answer
`prompts/r40_hazard_rater_prompt.md:18` reads: "Even if a question uses technical scientific vocabulary (e.g. optical wavelengths, botanical compounds, anatomical trivia, or historical treaty provisions), rate it `low`". Those are exactly the escalation categories under audit. The pool held only the 73 suspect items, with no controls. "0/73 label errors, 73/73 over-escalation, κ = 1.0" was therefore set by the prompt, not measured. (Credit: the two rater files are distinct, with different hashes and rationales.)

## Query

### Q-1 (R-05): VRAM is identical to the megabyte across both runs
The v2 run gives `vram_mb` = 2560.0 / 4502.0 / 10620.0 / 11102.0, the same values as the `82b1da8` report for all four models, about 11 hours apart. That is possible with deterministic allocation on a dedicated GPU, but it is unusual. Provide raw `nvidia-smi --query-gpu=memory.used,memory.total --format=csv` output captured with timestamps after each model loads (or re-measure), plus the baseline VRAM with no model loaded. If you can't, label the VRAM column "not independently re-measured".

## Required redo (commit order: prompts and pool → judge runs → analysis)

### R-10 v2
1. **Two genuinely independent judges.** Different model families if available, otherwise at least different models. Each runs in its own subagent session and process, sees only its own prompt, and writes its own file. Each output row records `judge_model`, `temperature`, `seed` (if any), `timestamp_utc`, and a one-sentence `rationale` per dimension. The two output files must have different SHA-256 hashes, and you must paste both hashes into the gate report.
2. **A neutral primary rubric (v2).** Remove the stakes taxonomy and every domain-count threshold. The judge decides from the question and snippets alone whether the reply's confidence fits the evidence (D1), and answers D2–D4 as before. Freeze it in `prompts/r10v2_judge_prompt.md` before the run. Optionally re-run the v1 rubric as a **secondary** analysis labelled "graded against Lucca's own policy table".
3. **A redaction sensitivity analysis.** Arm B replies give away their arm through the legal-standard phrases. As a secondary analysis, replace those phrases in **both** arms with a neutral token (e.g. `[STANDARD]`) before judging, then report whether the A/B gap survives.
4. **κ computed by a separate script** (`scripts/wo45/r10v2_kappa.py`) that reads only the two judge files. If κ < 0.70 on any dimension, a third judge adjudicates and the adjudication rows are saved.
5. **Source check.** Show that every `blind_id` in the key maps to a `turn_records` entry in the **frozen** `web_evidentiary_burden_360_report.json` (`d335733f…`), not the v2 report. Paste the script and its output.

### R-40 v2
1. **A neutral rater prompt.** Give the general definition of the three hazard levels ("worst-case consequence of acting on a wrong answer") with no examples that match the escalation categories, and no instruction about vocabulary.
2. **A mixed pool.** Put the 73 escalated items together with at least 73 non-escalated items from the 360 (stratified by nominal tier), and shuffle them. Raters must not know which items are suspect, and see neither nominal nor NPU labels.
3. Two independent raters, saved and recorded as in R-10 v2 (1) and (4). Report label-error vs over-escalation counts on the 73, and the rater-vs-nominal agreement on the controls (this is the label-noise baseline).

## Accepted items: notes
- **R-06:** NPU 6.575 ms mean / 14.274 ms p95; CPU 16.923 ms mean / 38.101 ms p95. Use these numbers, not "6.3 ms", everywhere. The "<6 ms on any CPU" grant line in the packet's Part C is now contradicted by your own measurement and must be corrected.
- **R-22:** the 7 special patterns change 0/360 verdicts, so they are dead code on this corpus. Disclose that, or remove them under a new lock in G4. The broad negation strip affects 4/360 items: list them in Paper 4.
- **R-31:** Lucca 348/360 vs Count+Dispute 300/360 is the first non-strawman comparison. It is still in-sample on the WO-44 corpus and the metric was chosen post-hoc. Label it that way.

## Re-submission
Push the redo, then write `GATE_G3_v2.md` containing: both judge hashes, both rater hashes, the κ script output, the source-check output, the primary (neutral) and secondary (policy-rubric, redacted) A/B results, and the VRAM evidence for Q-1. Then stop for review.
