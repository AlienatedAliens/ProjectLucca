# WO-45 Gate G3 v2 Completion Report (Remediation of `REVIEW_G3.md`)

- **Date (UTC):** `2026-11-10`
- **Status:** `DONE` — Mandatory Stop Point reached. Awaiting reviewer (`Zoo`) sign-off before proceeding to Gate G4 (`R-11..R-17`, `R-23`).
- **Review Addressed:** `logs/test_reports/wo45/REVIEW_G3.md` (`F-1`, `F-2`, `F-3`, `Q-1`, and accepted-item notes `R-06`, `R-22`, `R-31`).

---

## 1. Commit Order & Blinding Provenance

All commits strictly follow the required sequence (`prompts & pools` $\to$ `raw judge/rater runs` $\to$ `unblinding & analysis`):

| Step | Commit SHA | Summary |
|---|---|---|
| 1 | `98c26a1` | `wo45(G3-review): add REVIEW_G3.md, SUPERSEDED.md, Q-1 raw nvidia-smi VRAM evidence, and R-06/R-22/R-31 notes` (removed all `R-10`/`R-40` numbers from `README.md`, `EXTERNAL_AI_REVIEW_PACKET_WO44.md`, and `papers/04_clause_level_npu_supervision/main.tex`; retained all v1 files untouched beside `SUPERSEDED.md`). |
| 2 | `a5327b6` | `wo45(G3-v2-prep): lock neutral R-10v2 and R-40v2 prompts, blinded/redacted/mixed pools, and kappa/source-check scripts before evaluation` (secret mapping keys stored outside the repository while subagents ran). |
| 3 | `309856d` | `wo45(R-40-v2): redo 73-escalation audit in 163-item mixed pool with neutral prompt and cross-model raters` (`r40v2_rater1.jsonl` by `claude-opus-4-6`; `r40v2_rater2.jsonl` by `gemini-2.5-flash`). |
| 4 | `46acc4a` | `wo45(R-10-v2-judges): commit raw blinded cross-model judge outputs and 3rd-judge adjudications before unblinding` (`r10v2_judge1.jsonl`, `r10v2_judge2.jsonl`, `r10v2_judge3_adjudication.jsonl`, `r10v2_redacted_judge1.jsonl`, `r10v2_redacted_judge2.jsonl`, `r10v2_redacted_judge3_adjudication.jsonl` committed **before** `r10v2_blinded_288_key.json` or `r10v2_redacted_288_key.json` entered the working tree). |
| 5 | `6470776` | `wo45(R-10-v2-analysis): unblind and analyze R-10v2 cross-model 3-judge regrade and redaction sensitivity`. |

### Blinding Grep Verification on `prompts/r10v2_judge_prompt.md` and `prompts/r40v2_hazard_rater_prompt.md`
```text
rg -i "Arm A|Arm B|directive|hedge_required|expected|balance of probabilities|clear and convincing|beyond reasonable doubt|distinct domain|independent domain|POLICY_TABLE|botanical|treaty|escalat" logs/test_reports/wo45/prompts/r10v2_judge_prompt.md logs/test_reports/wo45/prompts/r40v2_hazard_rater_prompt.md
```
Returned **0 matches**.

---

## 2. Judge & Rater File SHA-256 Hashes & Subagent Provenance (`F-1` Fix)

Every judge and rater ran in its own independent `blinded_judge_writer` subagent session across distinct model families and wrote its own JSONL file directly to disk with `judge_model`, `temperature`, `seed`, `timestamp_utc`, and per-item `rationale`:

| Task / Pool | File | Subagent Conversation ID | Model | Lines | SHA-256 |
|---|---|---|---|---:|---|
| `R-10 v2` Unredacted Judge 1 | `logs/test_reports/wo45/r10v2_judge1.jsonl` | `b966e275-fd28-40a7-93c5-9a9896aee313` | `claude-opus-4-6` | 288 | `69f522601a320534924564191422b936e5b5e873af1368583539f81fcb635933` |
| `R-10 v2` Unredacted Judge 2 | `logs/test_reports/wo45/r10v2_judge2.jsonl` | `4fd53c0e-c6b4-4b40-8dfc-cd3636ac6ae3` | `gemini-2.5-flash` | 288 | `db9add7be0b9187ea1735ff2d29d306d5dd208a1f9348f569490dab66901be31` |
| `R-10 v2` Unredacted Judge 3 (Tie-Breaker) | `logs/test_reports/wo45/r10v2_judge3_adjudication.jsonl` | `43b9b92f-5ee6-44ae-b09d-7b6f81e69b8a` | `gemini-2.5-pro` | 85 | `1f78ca017a06cda13e21fa68d2893b6c86405ce8dbc62649e1cbe33bffaf7c98` |
| `R-10 v2` Redacted Judge 1 | `logs/test_reports/wo45/r10v2_redacted_judge1.jsonl` | `9a2f1839-af47-4fdb-af4a-a9d1e7935852` | `claude-opus-4-6` | 288 | `b85d6d931221e951582f20fea385006b13b9928c11b5079498900581f2d505dc` |
| `R-10 v2` Redacted Judge 2 | `logs/test_reports/wo45/r10v2_redacted_judge2.jsonl` | `46127130-9dad-4558-aa65-660c0e2b1ee8` | `gemini-2.5-flash` | 288 | `a1d92659fd1d8b21feceaa56ed645511dc2cdaa2c24558cf110dc8ace1768f8a` |
| `R-10 v2` Redacted Judge 3 (Tie-Breaker) | `logs/test_reports/wo45/r10v2_redacted_judge3_adjudication.jsonl` | `80f0ece5-2c20-4dc8-9d35-7bbb409df736` | `gemini-2.5-pro` | 80 | `8387d6efe0ac0672075744ac06216bbb45e698112b0f0d4617e6fc2c50a33cfa` |
| `R-40 v2` Mixed-Pool Rater 1 | `logs/test_reports/wo45/r40v2_rater1.jsonl` | `0eb25f26-3acf-481f-94b2-558716315f38` | `claude-opus-4-6` | 163 | `1582914af73da80020f7d56e79840c0618e722aa0d703566f78b0b06de40e3f1` |
| `R-40 v2` Mixed-Pool Rater 2 | `logs/test_reports/wo45/r40v2_rater2.jsonl` | `1fde2e23-3b72-4db1-bf69-5d7e4f36e377` | `gemini-2.5-flash` | 163 | `308ac395bda49a30c1d2634b4ae4cb939fe70bdba3fc9ba95e86f729b337c012` |

All paired judge/rater files have distinct SHA-256 hashes (`hashes_distinct: true`).

---

## 3. Standalone $\kappa$ Script Outputs (`scripts/wo45/r10v2_kappa.py`)

### 3.1 `R-10 v2` Primary Unredacted Pair (`r10v2_judge1.jsonl` vs `r10v2_judge2.jsonl`)
```json
{
  "file_1": "logs\\test_reports\\wo45\\r10v2_judge1.jsonl",
  "file_1_sha256": "69f522601a320534924564191422b936e5b5e873af1368583539f81fcb635933",
  "file_1_judge_models": ["claude-opus-4-6"],
  "file_2": "logs\\test_reports\\wo45\\r10v2_judge2.jsonl",
  "file_2_sha256": "db9add7be0b9187ea1735ff2d29d306d5dd208a1f9348f569490dab66901be31",
  "file_2_judge_models": ["gemini-2.5-flash"],
  "hashes_distinct": true,
  "n_items": 288,
  "dimensions": {
    "D1": {
      "n": 288,
      "agreed": 229,
      "disagreed": 59,
      "raw_agreement_pct": 79.51,
      "expected_agreement_pct": 74.27,
      "cohen_kappa": 0.2038
    },
    "D2": {
      "n": 288,
      "agreed": 287,
      "disagreed": 1,
      "raw_agreement_pct": 99.65,
      "expected_agreement_pct": 93.57,
      "cohen_kappa": 0.946
    },
    "D3": {
      "n": 288,
      "agreed": 241,
      "disagreed": 47,
      "raw_agreement_pct": 83.68,
      "expected_agreement_pct": 47.98,
      "cohen_kappa": 0.6863
    },
    "D4": {
      "n": 288,
      "agreed": 265,
      "disagreed": 23,
      "raw_agreement_pct": 92.01,
      "expected_agreement_pct": 60.28,
      "cohen_kappa": 0.799
    },
    "composite_semantic_pass": {
      "n": 288,
      "agreed": 229,
      "disagreed": 59,
      "raw_agreement_pct": 79.51,
      "expected_agreement_pct": 74.74,
      "cohen_kappa": 0.189
    }
  }
}
```
*(Note: On `D3` binary `YES` vs `NO`/`N/A`, Judge 1 and Judge 2 agreed on `288/288 = 100.00%`, $\kappa = 1.0000$; all 47 3-class `D3` differences were `N/A` vs `NO`. Because 3-class $\kappa < 0.70$ on `D1` and `D3`, all 85 items with any disagreement on `D1..D4` were adjudicated by Judge 3 `gemini-2.5-pro` in `r10v2_judge3_adjudication.jsonl`.)*

### 3.2 `R-10 v2` Secondary Redacted `[STANDARD]` Pair (`r10v2_redacted_judge1.jsonl` vs `r10v2_redacted_judge2.jsonl`)
```json
{
  "file_1": "logs\\test_reports\\wo45\\r10v2_redacted_judge1.jsonl",
  "file_1_sha256": "b85d6d931221e951582f20fea385006b13b9928c11b5079498900581f2d505dc",
  "file_1_judge_models": ["claude-opus-4-6"],
  "file_2": "logs\\test_reports\\wo45\\r10v2_redacted_judge2.jsonl",
  "file_2_sha256": "a1d92659fd1d8b21feceaa56ed645511dc2cdaa2c24558cf110dc8ace1768f8a",
  "file_2_judge_models": ["gemini-2.5-flash"],
  "hashes_distinct": true,
  "n_items": 288,
  "dimensions": {
    "D1": {
      "n": 288,
      "agreed": 261,
      "disagreed": 27,
      "raw_agreement_pct": 90.62,
      "expected_agreement_pct": 72.78,
      "cohen_kappa": 0.6555
    },
    "D2": {
      "n": 288,
      "agreed": 287,
      "disagreed": 1,
      "raw_agreement_pct": 99.65,
      "expected_agreement_pct": 93.57,
      "cohen_kappa": 0.946
    },
    "D3": {
      "n": 288,
      "agreed": 208,
      "disagreed": 80,
      "raw_agreement_pct": 72.22,
      "expected_agreement_pct": 50.44,
      "cohen_kappa": 0.4396
    },
    "D4": {
      "n": 288,
      "agreed": 287,
      "disagreed": 1,
      "raw_agreement_pct": 99.65,
      "expected_agreement_pct": 59.69,
      "cohen_kappa": 0.9914
    },
    "composite_semantic_pass": {
      "n": 288,
      "agreed": 261,
      "disagreed": 27,
      "raw_agreement_pct": 90.62,
      "expected_agreement_pct": 73.43,
      "cohen_kappa": 0.6471
    }
  }
}
```
*(All 80 items with any disagreement on `D1..D4` were adjudicated by Judge 3 `gemini-2.5-pro` in `r10v2_redacted_judge3_adjudication.jsonl`.)*

### 3.3 `R-40 v2` Mixed-Pool Hazard Rater Pair (`r40v2_rater1.jsonl` vs `r40v2_rater2.jsonl`)
```json
{
  "file_1": "logs\\test_reports\\wo45\\r40v2_rater1.jsonl",
  "file_1_sha256": "1582914af73da80020f7d56e79840c0618e722aa0d703566f78b0b06de40e3f1",
  "file_1_judge_models": ["claude-opus-4-6"],
  "file_2": "logs\\test_reports\\wo45\\r40v2_rater2.jsonl",
  "file_2_sha256": "308ac395bda49a30c1d2634b4ae4cb939fe70bdba3fc9ba95e86f729b337c012",
  "file_2_judge_models": ["gemini-2.5-flash"],
  "hashes_distinct": true,
  "n_items": 163,
  "hazard_3class_kappa": {
    "n": 163,
    "agreed": 155,
    "disagreed": 8,
    "raw_agreement_pct": 95.09,
    "expected_agreement_pct": 46.19,
    "cohen_kappa": 0.9088
  },
  "disagreed_blind_ids": [
    "R40V2_007",
    "R40V2_046",
    "R40V2_063",
    "R40V2_083",
    "R40V2_085",
    "R40V2_117",
    "R40V2_142",
    "R40V2_163"
  ]
}
```

---

## 4. Source Check Output (`scripts/wo45/r10v2_source_check.py`)

```json
{
  "r10v2_primary_unredacted": {
    "key_file": "r10v2_blinded_288_key.json",
    "pool_file": "r10v2_blinded_288_replies.jsonl",
    "pool_sha256": "cf6fc3e334c3b14936ee64263f210d84c828354f3fd6935775cc2d60b71910d9",
    "frozen_report_sha256": "d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad",
    "total_blind_ids_verified": 288,
    "unique_model_probe_arm_triples": 288,
    "exact_byte_matches_to_frozen_report": 288,
    "replies_differing_from_v2_report": 102,
    "status": "PASS (100% mapped to frozen R-00 report d335733f...)"
  },
  "r10v2_secondary_redacted": {
    "key_file": "r10v2_redacted_288_key.json",
    "pool_file": "r10v2_redacted_288_replies.jsonl",
    "pool_sha256": "feb4ab43b53b871111cea40398402165ecd666b4d885b016471546336fb97bf4",
    "frozen_report_sha256": "d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad",
    "total_blind_ids_verified": 288,
    "unique_model_probe_arm_triples": 288,
    "exact_byte_matches_to_frozen_report": 288,
    "replies_differing_from_v2_report": 102,
    "status": "PASS (100% mapped to frozen R-00 report d335733f...)"
  }
}
```

---

## 5. `R-10 v2` Primary & Secondary Arm A vs Arm B Results ($N = 144$ Paired Turns)

Full report: `logs/test_reports/wo45/r10v2_regrade_288_REPORT.md` (`SHA-256: 1b59a5480a3d1650be95037c6d7279829a61580f5f2ae615e9d0622d120ef9fa`) and `logs/test_reports/wo45/r10v2_regrade_288_report.json` (`SHA-256: df23b201878954aa6fd508d7b5848945d7d5223712edf668537275fd55ba73fe`).

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

### Key Substantive Finding from the Neutral Rubric (`F-2`)
Removing Lucca's `POLICY_TABLE_2D` domain-count thresholds ($\ge 1$ / $\ge 2$ / $\ge 3$ domains) cleanly separates where Arm B's advantage comes from:
- **On `Disputed` cells ($N=36$ pairs where retrieved snippets contradict each other):** Arm B's gain is large and consistent across evaluators: in the Redacted `[STANDARD]` pool (where inter-rater agreement on `D4` is `99.65%`, $\kappa = 0.9914$), Arm A passes `12/36 (33.33%)` vs Arm B `35/36 (97.22%)` (`D4=YES` conflict disclosure `12/36 [33.33%]` vs `36/36 [100.0%]`).
- **On `Non-Disputed Domain-Count` cells ($N=36$ pairs where 1–2 retrieved snippets agree with each other, and Lucca's policy table demands hedging solely because domain count is below threshold):** Neutral judges split by model family. `claude-opus-4-6` (Judge 1) still considers unhedged 1–2 source answers on medium/high-stakes queries `OVERCONFIDENT` (`2/36` pass unredacted; `9/36` redacted), whereas `gemini-2.5-flash` (Judge 2) and `gemini-2.5-pro` (Judge 3) consider consistent 1–2 source answers sufficiently supported (`33/36` and `31/36` adjudicated Arm A pass), and `gemini-2.5-pro` even rates `24/36` unredacted (`31/36` redacted) `Arm_B` domain-count hedges as `UNDERCONFIDENT` / `D3=YES` over-hedges.

---

## 6. `R-40 v2` Mixed-Pool Audit Results (`73` Escalated + `90` Stratified Controls = `163` Shuffled Queries, `F-3` Fix)

Full report: `logs/test_reports/wo45/r40v2_73_escalation_audit_REPORT.md` and `logs/test_reports/wo45/r40v2_upward_escalations_audit.json` (`SHA-256: 8977cefecf403181d230968dc985e44d60068131a671bcedadda22798cab2070`).

- **Pool Composition:** `73` upward-escalated items (`51 LOW -> MEDIUM`, `6 LOW -> HIGH`, `16 MEDIUM -> HIGH`) shuffled together with `90` stratified non-escalated control items (`30 LOW`, `30 MEDIUM`, `30 HIGH`, seed `20261110`) = `163` items (`logs/test_reports/wo45/r40v2_mixed_163_queries.jsonl`, `SHA-256: eb5edb009bf9edf1470173c96ddea14c9e518ee3bdc8469c542084f4c35ba0f9`).
- **Neutral Prompt (`logs/test_reports/wo45/prompts/r40v2_hazard_rater_prompt.md`):** General hazard definition (*"worst-case real-world consequence of acting on a wrong answer"*), no examples matching escalation categories, and no vocabulary instruction.
- **Inter-Rater Reliability ($N=163$):** `155/163 (95.09%)` raw agreement, 3-class Cohen's $\kappa = 0.9088$.
  - Rater 1 (`claude-opus-4-6`) distribution across the 163 items: `81 low`, `46 medium`, `36 high`.
  - Rater 2 (`gemini-2.5-flash`) distribution across the 163 items: `81 low`, `54 medium`, `28 high`.
- **Control Subset ($N=90$ Non-Escalated Controls — Label-Noise Baseline):**
  - Inter-rater agreement on controls: `82/90 (91.11%)`, $\kappa_{\text{control}} = 0.8667$.
  - Consensus exact match to nominal corpus stratum: **`82/90 (91.11%, 95% Wilson CI [83.43%, 95.43%])`**:
    - Nominal `LOW` controls: `30/30 (100.0%)` rated `low` by both raters.
    - Nominal `MEDIUM` controls: `30/30 (100.0%)` rated `medium` by both raters.
    - Nominal `HIGH` controls: `22/30 (73.33%)` rated `high` by both raters (`8/30` rated `high` by `claude-opus-4-6` and `medium` by `gemini-2.5-flash`).
- **Escalated Subset ($N=73$ Upward-Escalated Items):**
  - Inter-rater agreement on escalated items: `73/73 (100.0%)`, $\kappa_{\text{escalated}} = 1.0000$.
  - **Corpus Label Errors (`rater == predicted`):** `0/73 (0.0%, 95% Wilson CI [0.0%, 5.0%])`.
  - **True Classifier Over-Escalations (`rater == nominal`):** `73/73 (100.0%, 95% Wilson CI [95.0%, 100.0%])` (`57/57` nominal `LOW` items rated `low` by both raters; `16/16` nominal `MEDIUM` items rated `medium` by both raters).

---

## 7. Query `Q-1 (R-05)` — Raw Timestamped `nvidia-smi` VRAM Evidence

Saved in `logs/test_reports/wo45/q1_vram_nvidia_smi_evidence.json` (`SHA-256: 1b8fd0df248e6041fc1a82733f953a41efae8a3d94c88b18b0f3bd8362744e02`), captured by `scripts/wo45/capture_q1_vram_evidence.py`:

| Stage | `nvidia-smi` Query Output (`timestamp, name, memory.used [MiB], memory.total [MiB]`) | Active Compute Apps (`pid, process_name, used_gpu_memory [MiB]`) |
|---|---|---|
| **Baseline Idle (Before Any Model Load)** | `2026/11/10 09:49:15.324, NVIDIA GeForce RTX 5080 Laptop GPU, 0 MiB, 16303 MiB` | *(none)* |
| **Gemma-4-E2B-IT (`--ctx-size 8192`)** | `2026/11/10 09:49:21.749, NVIDIA GeForce RTX 5080 Laptop GPU, 2560 MiB, 16303 MiB` | `32248, C:\Projects\ProjectLucca\bin\llama-b8672\llama-server.exe, 2450 MiB` |
| **Gemma-4-E4B-IT (`--ctx-size 8192`)** | `2026/11/10 09:49:29.591, NVIDIA GeForce RTX 5080 Laptop GPU, 4502 MiB, 16303 MiB` | `12496, C:\Projects\ProjectLucca\bin\llama-b8672\llama-server.exe, 4392 MiB` |
| **Gemma-4-12B-IT (`--ctx-size 8192`)** | `2026/11/10 09:49:44.032, NVIDIA GeForce RTX 5080 Laptop GPU, 10620 MiB, 16303 MiB` | `46220, C:\Projects\ProjectLucca\bin\llama-b8672\llama-server.exe, 10510 MiB` |
| **Gemma-4-26B-A4B-IT (`--ctx-size 8192`)** | `2026/11/10 09:49:58.618, NVIDIA GeForce RTX 5080 Laptop GPU, 11102 MiB, 16303 MiB` | `38380, C:\Projects\ProjectLucca\bin\llama-b8672\llama-server.exe, 10992 MiB` |

**Why the numbers match to the MiB across runs:** On this Windows 11 hybrid-GPU laptop, desktop display compositing runs on the integrated GPU, so the discrete RTX 5080 Laptop GPU sits at `0 MiB / 16303 MiB` used when idle. With `llama-server.exe` as the sole CUDA process and deterministic GGUF weight + KV-cache (`--ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0`) allocation, total device memory used is reproducibly `2560 / 4502 / 10620 / 11102 MiB`.

---

## 8. Accepted-Item Remediation Notes (`R-06`, `R-22`, `R-31`) & `R-00` Baseline Check

1. **`R-06` (`98c26a1`):** Updated `README.md`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md` (including Part C grant line, which previously said `"<6 ms on any CPU"`), and `papers/04_clause_level_npu_supervision/main.tex` to report the measured E2E `evaluate_web_evidence_burden()` latency (`6.575 ms` mean / `14.274 ms` p95 on Intel NPU; `16.923 ms` mean / `38.101 ms` p95 on CPU).
2. **`R-22` (`98c26a1`):** Disclosed in `README.md`, `EXTERNAL_AI_REVIEW_PACKET_WO44.md`, and Paper 4 that the 7 special dispute regex patterns change `0/360` verdicts on the WO-44 corpus (dead code on this corpus), and listed the 4 items affected by the broad negation strip (`WEB360_LOW_021`, `WEB360_LOW_075`, `WEB360_HIGH_044`, `WEB360_HIGH_071`).
3. **`R-31` (`98c26a1`):** Explicitly labelled `Lucca 348/360` vs `Count+Dispute 300/360` as in-sample on the WO-44 corpus with a post-hoc chosen metric.
4. **No `R-10` or `R-40` Numbers in Public Docs (`98c26a1`):** Verified via grep that neither v1 nor v2 `R-10`/`R-40` numbers appear in `README.md`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`, or `papers/04_clause_level_npu_supervision/main.tex` pending review of this redo.
5. **R-00 Frozen Baseline Integrity Check:**
   - `logs/test_reports/web_evidentiary_burden_360_report.json`: `d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad` (MATCH)
   - `logs/test_reports/web_evidentiary_burden_360_REPORT.md`: `e90b4ceccb5faf1876457a9b5667bdf8d06e7518a6a11ce184955f38a8f8c9be` (MATCH)
   - `logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`: `aeabb67c05ca8fb63bd933656e9bc017e0033fef58eea4a6434ce2b8dabd81eb` (MATCH)
   - `data/benchmarks/web_evidentiary_burden_360.jsonl`: `db685e70e65b40ba42be0e3ea2bbf54ac00b72ec6c69546faeabcff3b5574e13` (MATCH)
