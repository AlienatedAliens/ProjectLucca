# WO-45 Task R-10 v2 & R-16 — Blinded Semantic Re-Grade of 288 Replies (Neutral Rubric + Redaction Sensitivity + 3-Judge Adjudication)

- **Task IDs:** `R-10 v2` (remediating `REVIEW_G3.md` `F-1` and `F-2`), `R-16`
- **Gate:** `G3 v2`
- **Source Report (Frozen R-00 Baseline):** `logs/test_reports/web_evidentiary_burden_360_report.json` (`SHA-256: d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad`)
- **Neutral Judge Prompt (Committed in `a5327b6` Before Any Judge Ran):** `logs/test_reports/wo45/prompts/r10v2_judge_prompt.md`
- **Raw Judge Outputs (Committed in `46acc4a` Before Unblinding Keys Entered Workspace):**
  - Primary Unredacted Pool (`logs/test_reports/wo45/r10v2_blinded_288_replies.jsonl`, `SHA-256: cf6fc3e334c3b14936ee64263f210d84c828354f3fd6935775cc2d60b71910d9`):
    - **Judge 1 (`claude-opus-4-6`, subagent `b966e275-fd28-40a7-93c5-9a9896aee313`):** `logs/test_reports/wo45/r10v2_judge1.jsonl` (`SHA-256: 69f522601a320534924564191422b936e5b5e873af1368583539f81fcb635933`)
    - **Judge 2 (`gemini-2.5-flash`, subagent `4fd53c0e-c6b4-4b40-8dfc-cd3636ac6ae3`):** `logs/test_reports/wo45/r10v2_judge2.jsonl` (`SHA-256: db9add7be0b9187ea1735ff2d29d306d5dd208a1f9348f569490dab66901be31`)
    - **Judge 3 Tie-Breaker Adjudicator on 85 Disagreed Items (`gemini-2.5-pro`, subagent `43b9b92f-5ee6-44ae-b09d-7b6f81e69b8a`):** `logs/test_reports/wo45/r10v2_judge3_adjudication.jsonl` (`SHA-256: 1f78ca017a06cda13e21fa68d2893b6c86405ce8dbc62649e1cbe33bffaf7c98`)
  - Secondary Redacted `[STANDARD]` Sensitivity Pool (`logs/test_reports/wo45/r10v2_redacted_288_replies.jsonl`, `SHA-256: feb4ab43b53b871111cea40398402165ecd666b4d885b016471546336fb97bf4`):
    - **Redacted Judge 1 (`claude-opus-4-6`, subagent `9a2f1839-af47-4fdb-af4a-a9d1e7935852`):** `logs/test_reports/wo45/r10v2_redacted_judge1.jsonl` (`SHA-256: b85d6d931221e951582f20fea385006b13b9928c11b5079498900581f2d505dc`)
    - **Redacted Judge 2 (`gemini-2.5-flash`, subagent `46127130-9dad-4558-aa65-660c0e2b1ee8`):** `logs/test_reports/wo45/r10v2_redacted_judge2.jsonl` (`SHA-256: a1d92659fd1d8b21feceaa56ed645511dc2cdaa2c24558cf110dc8ace1768f8a`)
    - **Redacted Judge 3 Tie-Breaker Adjudicator on 80 Disagreed Items (`gemini-2.5-pro`, subagent `80f0ece5-2c20-4dc8-9d35-7bbb409df736`):** `logs/test_reports/wo45/r10v2_redacted_judge3_adjudication.jsonl` (`SHA-256: 8387d6efe0ac0672075744ac06216bbb45e698112b0f0d4617e6fc2c50a33cfa`)
- **Report JSON:** `logs/test_reports/wo45/r10v2_regrade_288_report.json` (`SHA-256: df23b201878954aa6fd508d7b5848945d7d5223712edf668537275fd55ba73fe`)

---

## 1. Source Verification (`scripts/wo45/r10v2_source_check.py`)

Every `blind_id` in both `r10v2_blinded_288_key.json` and `r10v2_redacted_288_key.json` was verified against `turn_records` in the **frozen** `logs/test_reports/web_evidentiary_burden_360_report.json` (`d335733f...`):
- `total_blind_ids_verified`: `288 / 288`
- `unique_model_probe_arm_triples`: `288 / 288`
- `exact_byte_matches_to_frozen_report`: `288 / 288`
- `replies_differing_from_v2_report`: `102 / 288` (confirming the 288 replies come from the frozen R-00 report, not the fresh v2 rerun).

---

## 2. Inter-Rater Reliability (`scripts/wo45/r10v2_kappa.py`)

| Pool | Dimension | $N$ | Agreed | Disagreed | Raw Agreement | Expected Agreement | Cohen's $\kappa$ |
|---|---|---:|---:|---:|---:|---:|---:|
| **Primary (Unredacted)** | `D1` Epistemic Signalling | 288 | 229 | 59 | `79.51%` | `74.27%` | `0.2038` |
| **Primary (Unredacted)** | `D2` Factual Correctness | 288 | 287 | 1 | `99.65%` | `93.57%` | `0.9460` |
| **Primary (Unredacted)** | `D3` Over-Hedge (`YES`/`NO`/`N/A`) | 288 | 241 | 47 | `83.68%` | `47.98%` | `0.6863` |
| **Primary (Unredacted)** | `D3` Binary (`YES` vs `NO`/`N/A`) | 288 | 288 | 0 | `100.00%` | `95.92%` | `1.0000` |
| **Primary (Unredacted)** | `D4` Conflict Disclosure | 288 | 265 | 23 | `92.01%` | `60.28%` | `0.7990` |
| **Primary (Unredacted)** | **Composite Semantic Pass** | **288** | **229** | **59** | **`79.51%`** | **`74.74%`** | **`0.1890`** |
| **Secondary (Redacted `[STANDARD]`)** | `D1` Epistemic Signalling | 288 | 261 | 27 | `90.62%` | `72.78%` | `0.6555` |
| **Secondary (Redacted `[STANDARD]`)** | `D2` Factual Correctness | 288 | 287 | 1 | `99.65%` | `93.57%` | `0.9460` |
| **Secondary (Redacted `[STANDARD]`)** | `D3` Over-Hedge (`YES`/`NO`/`N/A`) | 288 | 208 | 80 | `72.22%` | `50.44%` | `0.4396` |
| **Secondary (Redacted `[STANDARD]`)** | `D3` Binary (`YES` vs `NO`/`N/A`) | 288 | 284 | 4 | `98.61%` | `94.59%` | `0.7433` |
| **Secondary (Redacted `[STANDARD]`)** | `D4` Conflict Disclosure | 288 | 287 | 1 | `99.65%` | `59.69%` | `0.9914` |
| **Secondary (Redacted `[STANDARD]`)** | **Composite Semantic Pass** | **288** | **261** | **27** | **`90.62%`** | **`73.43%`** | **`0.6471`** |

### Why Neutral Judges Split on Non-Disputed Domain-Count Cells (Addressing `REVIEW_G3.md` `F-2`)
When Lucca's `POLICY_TABLE_2D` domain-count thresholds ($\ge 1$ / $\ge 2$ / $\ge 3$ independent domains) are removed from the judge prompt, the 72 Arm A turns where Lucca requires hedging split into two qualitatively different subgroups:
1. **`Disputed` cells ($36$ Arm A / Arm B pairs across the 4 models):** The retrieved snippets genuinely contradict each other. In the Redacted pool, both Judge 1 (`claude-opus-4-6`) and Judge 2 (`gemini-2.5-flash`) agree at `99.65%` ($\kappa = 0.9914$) on `D4`: Arm A discloses the conflict on only `12/36 (33.33%)` of disputed turns (`11/36 = 30.56%` in Unredacted), whereas Arm B discloses the conflict on **`36/36 (100.0%)`**.
2. **`Non-Disputed Domain-Count` cells ($36$ Arm A / Arm B pairs across the 4 models — `LOW/no_evidence` [where snippets are tangential], `MEDIUM/single_source`, `HIGH/single_source`, `HIGH/dual_insufficient`):** Here, the retrieved snippet(s) do not conflict with each other; Lucca's `POLICY_TABLE_2D` requires hedging solely because the number of distinct domains is below threshold ($<1$, $<2$, or $<3$). Without Lucca's domain-count rule in the rubric:
   - **Judge 1 (`claude-opus-4-6`)** still rates unhedged Arm A answers on these 36 cells `OVERCONFIDENT` (`2/36 [5.56%]` pass unredacted; `9/36 [25.00%]` pass redacted) and rates Arm B's hedged answers `ACCURATE` (`36/36 [100.0%]`).
   - **Judge 2 (`gemini-2.5-flash`)** considers consistent 1–2 source snippets sufficient support for a direct answer (`33/36 [91.67%]` Arm A pass in both unredacted and redacted), while also rating Arm B's hedged answers `ACCURATE` (`36/36 [100.0%]`).
   - **Judge 3 (`gemini-2.5-pro`, tie-breaker on disagreed items)** agrees with Judge 2 that Arm A's direct answers on non-disputed 1–2 source cells are `ACCURATE` (`33/36` adjudicated Arm A pass unredacted; `31/36` redacted), and goes even further on `D3`: on `24/36` unredacted (`31/36` redacted) non-disputed `Arm_B` cells where Judge 1 rated `D3 = N/A` and Judge 2 rated `D3 = NO`, Judge 3 rated Arm B's domain-count hedge as `UNDERCONFIDENT` / `D3 = YES` (over-hedged relative to consistent snippets).

---

## 3. Pooled Arm A vs Arm B Results Across All Rubrics & Evaluators ($N = 144$ Paired Turns)

| Analysis / Evaluator | Arm A Pass ($N=144$) | Arm B Pass ($N=144$) | Cluster-Bootstrap $\Delta$ (`95% CI`) | Exact McNemar ($b:c$, $p$) | `Disputed` Cells ($N=36$) A vs B | `Non-Disputed Domain-Count` ($N=36$) A vs B | `Burden-Met` ($N=72$) A vs B |
|---|---|---|---|---|---|---|---|
| **Primary (Neutral Unredacted — 3-Judge Majority Adjudicated)** | **`122/144 (84.72%)`** `[77.95%, 89.69%]` | **`143/144 (99.31%)`** `[96.17%, 99.88%]` | **`+14.58 pp`** `[+6.25, +24.31]` | `21:0` ($p = 9.54 \times 10^{-7}$) | **`20/36` vs `35/36`** (`D4=YES`: `11/36` vs `36/36`) | **`33/36` vs `36/36`** | **`69/72` vs `72/72`** |
| Primary (Neutral Unredacted — Judge 1 `claude-opus-4-6` Alone) | `77/144 (53.47%)` `[45.34%, 61.42%]` | `143/144 (99.31%)` `[96.17%, 99.88%]` | `+45.83 pp` `[+31.25, +61.11]` | `66:0` ($p = 2.71 \times 10^{-20}$) | `6/36` vs `35/36` | `2/36` vs `36/36` | `69/72` vs `72/72` |
| Primary (Neutral Unredacted — Judge 2 `gemini-2.5-flash` Alone) | `136/144 (94.44%)` `[89.42%, 97.16%]` | `143/144 (99.31%)` `[96.17%, 99.88%]` | `+4.86 pp` `[+1.39, +9.03]` | `7:0` ($p = 0.0156$) | `34/36` vs `35/36` | `33/36` vs `36/36` | `69/72` vs `72/72` |
| Primary Sensitivity (If 3-Way `D3` Split `N/A`/`NO`/`YES` Counts as Fail) | `120/144 (83.33%)` `[76.40%, 88.54%]` | `119/144 (82.64%)` `[75.63%, 87.96%]` | `-0.69 pp` `[-15.28, +13.19]` | `18:19` ($p = 1.00$) | `20/36` vs `35/36` | `31/36` vs `12/36` | `69/72` vs `72/72` |
| **Secondary 1 (Neutral Redacted `[STANDARD]` — 3-Judge Majority Adjudicated)** | **`110/144 (76.39%)`** `[68.83%, 82.58%]` | **`143/144 (99.31%)`** `[96.17%, 99.88%]` | **`+22.92 pp`** `[+13.19, +34.03]` | `33:0` ($p = 2.33 \times 10^{-10}$) | **`12/36` vs `35/36`** (`D4=YES`: `12/36` vs `36/36`) | **`31/36` vs `36/36`** | **`67/72` vs `72/72`** |
| Secondary 1 (Neutral Redacted `[STANDARD]` — Judge 1 `claude-opus-4-6` Alone) | `87/144 (60.42%)` `[52.26%, 68.03%]` | `143/144 (99.31%)` `[96.17%, 99.88%]` | `+38.89 pp` `[+26.39, +52.08]` | `56:0` ($p = 2.78 \times 10^{-17}$) | `11/36` vs `35/36` | `9/36` vs `36/36` | `67/72` vs `72/72` |
| Secondary 1 (Neutral Redacted `[STANDARD]` — Judge 2 `gemini-2.5-flash` Alone) | `114/144 (79.17%)` `[71.82%, 85.00%]` | `143/144 (99.31%)` `[96.17%, 99.88%]` | `+20.14 pp` `[+11.11, +31.25]` | `29:0` ($p = 3.73 \times 10^{-9}$) | `12/36` vs `35/36` | `33/36` vs `36/36` | `69/72` vs `72/72` |
| Secondary 1 Sensitivity (If 3-Way `D3` Split `N/A`/`NO`/`YES` Counts as Fail) | `110/144 (76.39%)` `[68.83%, 82.58%]` | `112/144 (77.78%)` `[70.32%, 83.80%]` | `+1.39 pp` `[-16.67, +18.75]` | `28:26` ($p = 0.892$) | `12/36` vs `35/36` | `31/36` vs `5/36` | `67/72` vs `72/72` |
| **Secondary 2 (Graded Against Lucca's Own Policy Table — v1 Rubric, Judge 1)** | `79/144 (54.86%)` `[46.71%, 62.76%]` | `143/144 (99.31%)` `[96.17%, 99.88%]` | `+44.44 pp` `[+30.56, +58.33]` | `64:0` ($p = 1.08 \times 10^{-19}$) | `11/36` vs `35/36` | `0/36` vs `36/36` | `68/72` vs `72/72` |
| **WO-44 Regex Scorer (Reference)** | `99/144 (68.75%)` `[60.77%, 75.75%]` | `144/144 (100.0%)` `[97.40%, 100.0%]` | `+31.25 pp` | `45:0` ($p = 5.68 \times 10^{-14}$) | `18/36` vs `36/36` | `9/36` vs `36/36` | `72/72` vs `72/72` |

---

## 4. Per-Model Breakdown (Primary Neutral Unredacted vs Secondary Redacted `[STANDARD]`, 3-Judge Majority Adjudicated)

| Model | Primary Unredacted Arm A ($N=36$) | Primary Unredacted Arm B ($N=36$) | Primary Unredacted McNemar ($b:c$, $p$) | Redacted `[STANDARD]` Arm A ($N=36$) | Redacted `[STANDARD]` Arm B ($N=36$) | Redacted `[STANDARD]` McNemar ($b:c$, $p$) |
|---|---|---|---|---|---|---|
| **Gemma-4-E2B-IT** | `30/36 (83.33%)` `[68.11%, 92.13%]` | `35/36 (97.22%)` `[85.83%, 99.51%]` | `5:0` ($p = 0.0625$) | `29/36 (80.56%)` `[64.97%, 90.25%]` | `35/36 (97.22%)` `[85.83%, 99.51%]` | `6:0` ($p = 0.03125$) |
| **Gemma-4-E4B-IT** | `29/36 (80.56%)` `[64.97%, 90.25%]` | `36/36 (100.0%)` `[90.36%, 100.0%]` | `7:0` ($p = 0.0156$) | `25/36 (69.44%)` `[53.14%, 82.00%]` | `36/36 (100.0%)` `[90.36%, 100.0%]` | `11:0` ($p = 0.00098$) |
| **Gemma-4-12B-IT (abliterated)** | `31/36 (86.11%)` `[71.34%, 93.92%]` | `36/36 (100.0%)` `[90.36%, 100.0%]` | `5:0` ($p = 0.0625$) | `27/36 (75.00%)` `[58.93%, 86.25%]` | `36/36 (100.0%)` `[90.36%, 100.0%]` | `9:0` ($p = 0.00391$) |
| **Gemma-4-26B-A4B-IT** | `32/36 (88.89%)` `[74.69%, 95.59%]` | `36/36 (100.0%)` `[90.36%, 100.0%]` | `4:0` ($p = 0.125$) | `29/36 (80.56%)` `[64.97%, 90.25%]` | `36/36 (100.0%)` `[90.36%, 100.0%]` | `7:0` ($p = 0.0156$) |
| **Pooled (144 Paired Turns)** | **`122/144 (84.72%)`** `[77.95%, 89.69%]` | **`143/144 (99.31%)`** `[96.17%, 99.88%]` | **`21:0` ($p = 9.54 \times 10^{-7}$)** | **`110/144 (76.39%)`** `[68.83%, 82.58%]` | **`143/144 (99.31%)`** `[96.17%, 99.88%]` | **`33:0` ($p = 2.33 \times 10^{-10}$)** |
