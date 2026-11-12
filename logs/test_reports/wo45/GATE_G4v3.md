# WO-45 Gate G4 v3 Report (`RM-0` through `RM-10`)

- **Date (UTC):** `2026-11-12`
- **Reviewer Audit Addressed:** [`logs/test_reports/wo45/REVIEW_G4.md`](./REVIEW_G4.md) (`F-1` through `F-9`, `RM-0` through `RM-10`)
- **Primary Report JSON & OTS Proof:** [`logs/test_reports/wo45/g4_live_v3_report.json`](./g4_live_v3_report.json) (`SHA-256: 29bc62053c38419f95f3796881480895de1898851f6282ab36dd505ec562e044`) + [`g4_live_v3_report.json.ots`](./g4_live_v3_report.json.ots)
- **Human-Readable Summary:** [`logs/test_reports/wo45/g4_live_v3_REPORT.md`](./g4_live_v3_REPORT.md)

---

## 1. Executive Summary of `G4 v3` Findings (`N = 132` Fresh Items, `2,640` Live Turns at `ctx=32768`)

Across `132` fresh stratified `WEB360` items (`0` overlap with `G4 v2`; `11/cell` across `3` nominal hazard tiers $\times$ `4` corroboration topologies, including `33` disputed items and `66` nominal burden-met items) $\times$ `4` contiguous arms (`A`, `B`, `C`, `D`) $\times$ `5` local Gemma-4 `Q6_K` checkpoints (`E2B-heretic`, `E4B-heretic`, stock `gemma-4-E4B-it`, `12B-heretic`, `26B-A4B-heretic`) = **`2,640` live generations** evaluated on the **primary deterministic arm-identical normalized pool** (`0` forbidden lexicon hits across all `2,640` turns) by **3 qualification-screened, machine-logged non-Google judge families** (`Qwen3.8-27B-Ridge-GGUF` [`Alibaba-Qwen`], `phi-4-Q6_K` [`Microsoft-Phi`], `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL` [`NVIDIA-Nemotron`]):

1. **Disputed-Population `D4` Inter-Judge Reliability Clears $\kappa \ge 0.60$ Across Every Pair (`RM-2`, `RM-9`):**
   - Computed **strictly on the `660` disputed turns** (`33` disputed items $\times$ `4` arms $\times$ `5` models) using reply-only input (`{blind_id, question, reply}`, **no snippets shown**):
     - **Primary Normalized Pool:** `Qwen3.8 vs Phi-4` $\kappa = \mathbf{0.8587}$ (`94.24%` raw), `Qwen3.8 vs Nemotron-3.5` $\kappa = \mathbf{0.7154}$ (`88.94%` raw), `Phi-4 vs Nemotron-3.5` $\kappa = \mathbf{0.6983}$ (`89.24%` raw) — **`min κ = 0.6983 ≥ 0.60` (`judge_robust = True`)**.
     - **Secondary Raw Pool:** `Qwen3.8 vs Phi-4` $\kappa = \mathbf{0.8627}$ (`94.39%`), `Qwen3.8 vs Nemotron-3.5` $\kappa = \mathbf{0.7189}$ (`88.94%`), `Phi-4 vs Nemotron-3.5` $\kappa = \mathbf{0.7152}$ (`89.70%`) — **`min κ = 0.7152 ≥ 0.60`**.
2. **`RM-4` 4-Arm Unbundling (`Arm D` = Arm B Contract Context + Arm C System Prompt, No `MUST` / No Legal Vocabulary) Isolates the Mechanism:**
   - **Co-Primary 1 (`D4` Conflict Disclosure on `33` Disputed Items, `165` Turns/Arm, Primary Normalized 2-of-3 Majority):**
     - **Arm A (Plain Baseline):** `61/165` (**`36.97%`**, item-cluster bootstrap 95% CI `[25.45%, 49.09%]`)
     - **Arm C (Generic Uncertainty Tip):** `85/165` (**`51.52%`**, CI `[38.79%, 63.64%]`)
     - **Arm D (Detector Signal + Arm C System Prompt):** `164/165` (**`99.39%`**, CI `[98.18%, 100.00%]`)
     - **Arm B (Full Burden Gate: Detector Signal + `MUST` Mandate + Legal Vocab):** `165/165` (**`100.00%`**, CI `[100.00%, 100.00%]`)
     - **`D vs C` (Detector Conflict Signal Alone, Holding System Prompt Constant):** **`+47.88 pp`** (`[+36.36, +60.00]`, cluster-bootstrap $p = 0.0001$, discordant `79:0`). Positive and statistically significant under **every single judge individually** (`Qwen3.8-27B`: `+52.73 pp` `[87:0]`, `Phi-4-14B`: `+42.42 pp` `[70:0]`, `Nemotron-3.5-30B`: `+36.97 pp` `[61:0]`, all $p = 0.0001$) and **every single model scale** (`+33.33 pp` on `26B-A4B` to `+69.70 pp` on `E2B`).
     - **`B vs D` (`MUST` Mandate + Legal Vocabulary, Holding Contract Context Constant):** **`+0.61 pp`** (`[0.00, +1.82]`, $p = 0.7214$, discordant `1:0`) — **null incremental effect on conflict disclosure** (`98.8%` of the `+48.48 pp` `B vs C` bundled gain [`80:0`, $p = 0.0001$] is already achieved by `Arm D` alone).
   - **Co-Primary 2 (`D2` Unfaithfulness & Substantive Faithfulness Across All `132` Items, `660` Turns/Arm; Live `D2` Unfaithful `YES` Raw Agreement `89.8%–97.4%`, Base-Rate-Compressed $\kappa = 0.121–0.249`):**
     - **Explicit Unfaithfulness (`D2 = YES`, lower is better):** Low across all arms (`Arm A`: `6/660 [0.91%]`, `Arm B`: `9/660 [1.36%]`, `Arm C`: `9/660 [1.36%]`, `Arm D`: `12/660 [1.82%]`; `D vs C`: `+0.45 pp`, $p = 0.6032$; `B vs D`: `-0.45 pp`, $p = 0.3958$; `B vs C`: `0.00 pp`, $p = 1.0$).
     - **Substantive Faithful Answering (`D2 = NO` and `NO_ANSWER = NO`, higher is better; pairwise $\kappa = 0.7619, 0.4450, 0.4599`):** `Arm D` `648/660 (98.18%)` vs `Arm C` `612/660 (92.73%)` (**`D vs C = +5.45 pp` `[+2.73, +8.33]`, $p = 0.0001`**), `Arm B` `650/660 (98.48%)` (`B vs D = +0.30 pp`, $p = 0.6294$; `B vs C = +5.76 pp` `[+3.03, +8.64]`, $p = 0.0001`), driven by eliminating `NO_ANSWER` blank refusals on `Tier 4: Untrusted Web Search` snippets (`Arm A`: `73/660 [11.06%]`, `Arm C`: `39/660 [5.91%]`, `Arm B`: `0/660 [0.00%]`, `Arm D`: `0/660 [0.00%]`).
   - **Co-Primary 3 (`D1` Epistemic Calibration `ACCURATE` Across All `132` Items, `660` Turns/Arm; Promoted on Pilot $\kappa \ge 0.7182$, Live 3-Class Raw Agreement `87.2%–92.7%`, Base-Rate-Compressed $\kappa = 0.331–0.401` — Not Claimed Judge-Robust):**
     - **`D vs C`:** `643/660 (97.42%)` vs `614/660 (93.03%)` (**`+4.39 pp` `[+1.82, +7.12]`, $p = 0.0012`**).
     - **`B vs D` (Negative Mandate/Vocabulary Cost):** `628/660 (95.15%)` vs `643/660 (97.42%)` (**`-2.27 pp` `[-4.09, -0.61]`, $p = 0.0108`**), showing that adding Arm B's heavy `MUST` / legal-standard wording on top of Arm D's structured evidence summary slightly *reduces* judged calibration (`90.30%` vs `95.76%` on the `33` non-disputed below-nominal-burden items), leaving `B vs C` non-significant (`+2.12 pp` `[-0.61, +5.00]`, $p = 0.1556`).
3. **`RM-7` (`R-42`) Classifier Retraining Fallback & Item-Level `R-41` Over-Hedge Cost:**
   - Retrained `models/proof_policy_hazard_v2_ov` (`0` `v3` item leakage; `24/73 = 32.88%` held-out over-escalations) reduced held-out `R-40 v2` over-escalations from `24/24 (100.0%)` to `1/24 (4.17%)`, hit `50/50 (100.0%)` on `HZD_50`, and scored `125/130 (96.15%, 0.00 pp regression)` on `Blind-390`, but missed `1` item on the 50-item `WO42_LOCKED_HOLDOUT_150` `proof_policy` slice (`49/50 = 98.00%`, `-2.00 pp` slice regression $> 1.0\text{ pp}$ threshold; `-0.67 pp` across all `150` items). Per `REVIEW_G4.md:93`, `v3` enforced the strict fallback to `models/proof_policy_hazard_ov` (`v1`) and logged both `v1` and `v2` predictions side-by-side: on `v3`'s `132` unseen items, `v1` over-escalated `24/132 (18.18%)` items (`6` nominal-burden-met items blocked) whereas `v2` over-escalated `1/132 (0.76%)` item (`1` nominal-burden-met item blocked).
   - At the **item level** on the `6` nominal-burden-met items blocked by `v1` over-escalation (`D3` $\kappa = 0.8846, 0.8811, 0.9177`), model-majority item over-hedging (`items over-hedged / items escalated`) is `2/6 (33.33%)` on `Arm A`, `1/6 (16.67%)` on `Arm B`, `1/6 (16.67%)` on `Arm C`, and `2/6 (33.33%)` on `Arm D` (mean item over-hedge rate across 5 models: `Arm A` `36.67%` `[13.33%, 60.00%]`, `Arm B` `36.67%` `[26.67%, 46.67%]`, `Arm C` `33.33%` `[13.33%, 53.33%]`, `Arm D` `43.33%` `[26.67%, 60.00%]`; zero turn-level Wilson CIs reported on $n < 10$ items).

---

## 2. Chronological `origin/main` Push & OpenTimestamps Chain (`RM-6(a)–(d)`)

Every milestone was committed, OpenTimestamps-stamped against public Bitcoin calendar servers (`a.pool.opentimestamps.org`, `b.pool.opentimestamps.org`, `a.pool.eternitywall.com`), and pushed to `origin/main` strictly in causal order:

| Step | `origin/main` Commit | Timestamp (ISO) | Artifact(s) | File SHA-256 | `.ots` Proof SHA-256 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`RM-0`** | `1bb51a8` | `2026-11-11T20:29:41+08:00` | `REVIEW_G4.md` + `F-1..F-8` defect boxes + interim wording | — | — |
| **`RM-1`** | `5c22626` | `2026-11-11T21:00:17+08:00` | `prompts/g4v3_judge_prompt.md`, `g4v3_prompt_neutrality_check.json` (`0` hits) | `6f41b589...` | — |
| **`RM-2a`** | `f31ec78` | `2026-11-11T22:05:33+08:00` | `g4v3_judge_qualification_set.jsonl` (`106` items, `0` v3 overlap) | `eff5af197f82...` | — |
| **`RM-2b`** | `988e62c` | `2026-11-11T22:30:01+08:00` | Initial 3-family qualification report (`Qwen3.8-27B`, `Phi-4-14B`, `Mistral-Nemo-12B`) | `4d5284e8...` | — |
| **`RM-3`** | `009869b` | `2026-11-11T23:06:23+08:00` | `normalize_g4v3_replies.py`, `g4v3_normalizer_verification.json` (`0` hits, `36.67%` 3-way / `57.5%` bal. arm-guess) | `24c1b707...` | — |
| **`RM-7`** | `d7308f8` | `2026-11-12T04:48:15+08:00` | `train_r42_hazard_v2.py`, `r42_hazard_retrain_report.json` (`accepted=False` fallback) | `e06526d0...` | — |
| **`RM-6(a)`** | `4a6ecdd` | `2026-11-12T05:03:24+08:00` | `live_v3_prereg_lock.json` + `.ots` (**before generation**) | `438e70041eb9...` | `ac06f598b4c3...` |
| **`RM-6(b)`** | `c5ec1fd` | `2026-11-12T05:43:32+08:00` | `live_v3_pool_manifest.json` + `.ots` + blinded `2,640` pools (**before judging**) | `47fd28291e22...` | `aecf026468e4...` |
| **`RM-6(c) #1`** | `e198f1a` | `2026-11-12T08:06:55+08:00` | `g4v3_norm_judge1_qwen38_27b.jsonl` + `.ots` | `c2ba882f4b5a...` | `a0400eccc5fc...` |
| **`RM-6(c) #2`** | `28ded25` | `2026-11-12T09:09:58+08:00` | `g4v3_norm_judge2_phi4_14b.jsonl` + `.ots` | `617b2f93cc3a...` | `6c6bb44ac832...` |
| **`RM-6(a) Amend-1`** | `329ed2b` | `2026-11-12T10:20:36+08:00` | `live_v3_prereg_amendment1_judge3_nemotron.json` + `.ots` (**strictly pre-unblinding**; Judge 3 upgraded to `Nemotron-3.5-30B-A3B` before any Judge 3 v3 pool completed; all `4a6ecdd` files untouched) | `88a6fa8a871c...` | `e0cb0498a364...` |
| **`RM-6(c) #3`** | `400c80a` | `2026-11-12T11:58:48+08:00` | `g4v3_norm_judge3_nemotron35_30b.jsonl` + `.ots` | `fe5de80314df...` | `58d0efad47c5...` |
| **`RM-6(c) #4`** | `d651bd8` | `2026-11-12T14:22:14+08:00` | `g4v3_raw_judge1_qwen38_27b.jsonl` + `.ots` | `f4acbe17eea1...` | `14a8a0d38fdb...` |
| **`RM-6(c) #5`** | `78cacfc` | `2026-11-12T15:25:12+08:00` | `g4v3_raw_judge2_phi4_14b.jsonl` + `.ots` | `53271847a295...` | `6d8d223d2b57...` |
| **`RM-6(c) #6`** | `de5815c` | `2026-11-12T16:52:11+08:00` | `g4v3_raw_judge3_nemotron35_30b.jsonl` + `.ots` | `08e52b5e5672...` | `737ca699cbb3...` |
| **`RM-6(d)`** | `4604afd` | `2026-11-12T16:55:43+08:00` | Unblinded raw generations/keys + `g4_live_v3_report.json` + `.ots` + `g4_live_v3_REPORT.md` | `29bc62053c38...` | `b49c...` (verified) |

---

## 3. Detailed Remediation & Measurement Tables

### 3.1 `RM-2` Non-Google Judge Qualification (`N = 106` Items: `66` `D4` + `40` `D2`, `0` Overlap with `v3`)

| Role | Model (`llama-server` `T=0.0, seed=42`) | Vendor Family | GGUF Weight SHA-256 | `D4` Acc. (`N=66`, `YES`%) | `D2` Acc. (`N=40`, `YES`%) | `D1` Pilot (`N=83`) | Status |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **`Judge 1`** | `Qwen3.8-27B-Ridge-GGUF` (`27B` dense) | `Alibaba-Qwen` | `95580dbd...` | **`66/66 (100.0%)`**, `50.0%` | **`40/40 (100.0%)`**, `50.0%` | `74/83 (89.16%)` | **Qualified** |
| **`Judge 2`** | `phi-4-Q6_K` (`14B` dense) | `Microsoft-Phi` | `537248da...` | **`66/66 (100.0%)`**, `50.0%` | **`40/40 (100.0%)`**, `50.0%` | `68/83 (81.93%)` | **Qualified** |
| **`Judge 3`** | `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL` (`30B-A3B`) | `NVIDIA-Nemotron` | `8dff96e9...` | **`66/66 (100.0%)`**, `50.0%` | **`38/40 (95.0%)`**, `50.0%` | `74/83 (89.16%)` | **Qualified** |

- **Qualification Pairwise $\kappa$ (`g4v3_judge_qualification_amendment1_report.json`):** `D4` $\kappa = 1.0000, 1.0000, 1.0000$; `D2` $\kappa = 1.0000, 0.9000, 0.9000$; `D1` pilot 3-class $\kappa = 0.8314, 0.8912, 0.7182$ (all $\ge 0.60$).

### 3.2 `RM-9` Per-Judge Arm Prevalence Table (Primary Normalized Pool)

| Endpoint (`Scored Population`) | Grader | Arm A (`k/N, %`) | Arm B (`k/N, %`) | Arm C (`k/N, %`) | Arm D (`k/N, %`) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`D4` Conflict Disclosed (`33` disputed items, `165` turns/arm)** | **`2-of-3 Majority`** | `61/165 (36.97%)` | `165/165 (100.00%)` | `85/165 (51.52%)` | `164/165 (99.39%)` |
| | `J1 Qwen3.8-27B` | `51/165 (30.91%)` | `165/165 (100.00%)` | `76/165 (46.06%)` | `163/165 (98.79%)` |
| | `J2 Phi-4-14B` | `68/165 (41.21%)` | `165/165 (100.00%)` | `94/165 (56.97%)` | `164/165 (99.39%)` |
| | `J3 Nemotron-3.5-30B` | `91/165 (55.15%)` | `164/165 (99.39%)` | `104/165 (63.03%)` | `165/165 (100.00%)` |
| **`D2` Unfaithful `YES` (`132` items, `660` turns/arm; lower better)** | **`2-of-3 Majority`** | `6/660 (0.91%)` | `9/660 (1.36%)` | `9/660 (1.36%)` | `12/660 (1.82%)` |
| **`NO_ANSWER` Refusal (`132` items, `660` turns/arm)** | **`2-of-3 Majority`** | `73/660 (11.06%)` | `0/660 (0.00%)` | `39/660 (5.91%)` | `0/660 (0.00%)` |
| **`D2` Faithful Substantive (`132` items, `660` turns/arm; higher better)** | **`2-of-3 Majority`** | `581/660 (88.03%)` | `650/660 (98.48%)` | `612/660 (92.73%)` | `648/660 (98.18%)` |
| **`D3` Over-Hedge (`66` nominal-met items, `330` turns/arm; lower better)** | **`2-of-3 Majority`** | `47/330 (14.24%)` | `15/330 (4.55%)` | `24/330 (7.27%)` | `18/330 (5.45%)` |
| **`D1` `ACCURATE` Calibration (`132` items, `660` turns/arm)** | **`2-of-3 Majority`** | `532/660 (80.61%)` | `628/660 (95.15%)` | `614/660 (93.03%)` | `643/660 (97.42%)` |

### 3.3 Per-Model `D4` Conflict Disclosure Across All 5 Gemma-4 `Q6_K` Checkpoints (`N = 33` Disputed Items/Model, Primary Normalized)

| Model (`ctx=32768`) | Arm A | Arm C (Tip) | Arm D (Detector + C Prompt) | Arm B (Full Gate) | `D vs C` ($\Delta$, Exact McNemar $p$) | `B vs D` ($\Delta$, Exact McNemar $p$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`E2B-heretic`** | `10/33 (30.30%)` | `10/33 (30.30%)` | **`33/33 (100.0%)`** | **`33/33 (100.0%)`** | **`+69.70 pp`** ($2.38 \times 10^{-7}$) | `0.00 pp` ($1.0$) |
| **`E4B-heretic`** | `13/33 (39.39%)` | `19/33 (57.58%)` | **`33/33 (100.0%)`** | **`33/33 (100.0%)`** | **`+42.42 pp`** ($1.22 \times 10^{-4}$) | `0.00 pp` ($1.0$) |
| **`E4B-stock` (`R-17`)** | `12/33 (36.36%)` | `18/33 (54.55%)` | **`33/33 (100.0%)`** | **`33/33 (100.0%)`** | **`+45.45 pp`** ($6.10 \times 10^{-5}$) | `0.00 pp` ($1.0$) |
| **`12B-heretic`** | `8/33 (24.24%)` | `16/33 (48.48%)` | **`32/33 (96.97%)`** | **`33/33 (100.0%)`** | **`+48.48 pp`** ($3.05 \times 10^{-5}$) | `+3.03 pp` ($1.0$) |
| **`26B-A4B-heretic`** | `18/33 (54.55%)` | `22/33 (66.67%)` | **`33/33 (100.0%)`** | **`33/33 (100.0%)`** | **`+33.33 pp`** ($9.77 \times 10^{-4}$) | `0.00 pp` ($1.0$) |

---

## 4. Acceptance Criteria Verification Checklist (`REVIEW_G4.md:108–116`)

1. **`RM-2` Judge Qualification & Live Disputed `D4` $\kappa \ge 0.60$:** **PASS** — All 3 distinct non-Google families scored `100%` on `D4` and `95%–100%` on `D2` on `g4v3_judge_qualification_set.jsonl`, and live disputed-population `D4` (`660` disputed turns) reached $\kappa = 0.8587, 0.7154, 0.6983$ (`min = 0.6983 ≥ 0.60`) on Primary Normalized and $\kappa = 0.8627, 0.7189, 0.7152$ (`min = 0.7152 ≥ 0.60`) on Secondary Raw. (Live `D1` 3-class $\kappa = 0.331–0.401$ and `D2` unfaithful `YES` $\kappa = 0.121–0.249$ fall below `0.60` due to `93%–99%` class skew and are explicitly **not** claimed as judge-robust.)
2. **`RM-3` Arm-Identical Normalizer (`0` Hits & Arm-Guess $\le 60\%$):** **PASS** — `0` forbidden lexicon hits across all `2,640` normalized `v3` turns (`live_v3_pool_manifest.json`) and `36.67%` 3-way / `57.50%` balanced arm-guess accuracy (`<= 60%`, `g4v3_normalizer_verification.json`).
3. **`RM-6` Push & OpenTimestamps Chain on `origin/main`:** **PASS** — Individually stamped and pushed across `4a6ecdd` (`(a)`), `c5ec1fd` (`(b)`), `329ed2b` (`(a-amend1)` pre-unblinding), `e198f1a` / `28ded25` / `400c80a` / `d651bd8` / `78cacfc` / `de5815c` (`(c)` 6 individual judge commits), and `4604afd` (`(d)` unblinding + report).
4. **`RM-4` All `B / C / D / A` Contrasts Reported Candidly:** **PASS** — All 6 contrasts reported across `D4`, `D2`, `D1`, and `D3`, including the null `B vs D` contrast on `D4` (`+0.61 pp`, $p = 0.7214$) and negative `B vs D` contrast on `D1` (`-2.27 pp`, $p = 0.0108$).
5. **`RM-7` Classifier Acceptance & Item-Level `R-41`:** **PASS** — `accepted_for_g4_v3 = False` fallback enforced and disclosed (`r42_hazard_retrain_report.json`), side-by-side `v1` (`24` over-escalations, `6` blocked) vs `v2` (`1` over-escalation, `1` blocked) counts reported, and `R-41` reported at the item level with item-cluster bootstrap CIs (`0` turn-level Wilson CIs on $n < 10$ items).
6. **Static Gates, `ruff`/`mypy`, & `R-00` Baseline Hashes:** **PASS** — `0` ruff errors across `src`, `tests`, and `scripts/wo45`; `0` mypy errors across `src` (`198` files) and all `27` unlocked `scripts/wo45` modules (`analyze_wo45_live_v2.py` preserved byte-untouched per `live_v2_prereg_lock.json`); `40/40` `tests/test_static_gates.py` passed; and all `R-00` `frozen_measured_artifacts`, `G4 v2`, and `G4 v3` lock hashes verified intact.
