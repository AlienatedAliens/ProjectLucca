# WO-45 Gate G4 Completion & Reviewer Sign-Off Packet (`R-11..R-17`, `R-23`, `R-41`, `A-1..A-4`, `G4-1..G4-6`)

- **Date (UTC):** `2026-11-11`
- **Status:** **READY FOR REVIEWER (`Zoo`) GATE G4 AUDIT — EXECUTION STOPPED BEFORE GATE G5 (`R-21`)**
- **Governing Sign-Off & Plan:** `logs/test_reports/wo45/REVIEW_G3_v2.md` (`cc805f4` review + Addendum `A-1..A-4` + `K-1..K-6` + `G4-1..G4-6`) and `plans/2026-11-09_wo45_wo44_review_remediation.md`.

---

## 1. Gate G3 v2 Addendum (`A-1..A-4`), Minor Notes, & Reflog Confirmation (`REVIEW_G3_v2.md:3-11, 51-54`)

| Requirement | Resolution & Commit | Verification Evidence |
| :--- | :--- | :--- |
| **`A-1` (Revert unbundled `config.py` edit from `33bdb21`, then apply owner-requested `ctx=32768` in its own commit synced with active docs)** | `5257a15` (`wo45(fix): revert config.py ctx change from evidence commit 33bdb21`) $\rightarrow$ `36712d9` (`wo45(A-1): set production LLMSettings.ctx to 32768 per owner request and sync active docs`) | `src/lucca/core/config.py:50` (`ctx: int = 32768`) synced with `AGENTS.md`, `luccadocs/ARCHITECTURE.md`, `luccadocs/MODEL_STRATEGY.md`, and `luccadocs/README.md` in single isolated commit `36712d9`. |
| **`A-2` & `A-3` (`ctx=65536` `nvidia-smi` VRAM row + label `8K -> 32K` sliding-window/GQA note as unmeasured)** | `231d0ed` (`wo45(A-2,A-3): add REVIEW_G3_v2.md, capture ctx=65536 VRAM row, and label 8K->32K explanation as unmeasured`) | `logs/test_reports/wo45/q1_vram_nvidia_smi_evidence.json` (`SHA-256: e35013a27daf3e2e32aa34d8832d74f908648497cf2b7e027ea5b2b6ccf41911`) records raw `nvidia-smi` captures across `ctx=8192` (`2,560 / 4,502 / 10,620 / 11,102 MiB`), `ctx=32768` (`2,732 / 4,802 / 10,920 / 11,452 MiB`), and `ctx=65536` (`2,962 / 5,330 / 11,320 / 11,920 MiB`); the `8K -> 32K` KV-cache hypothesis is explicitly labeled *explanation, not measured*. |
| **`A-4` & `K-1..K-6` (Record `ctx=32768` in G4 lock; keep `v2` `8192` report labeled; apply binding G3 v2 reporting constraints)** | `f145a64` (`wo45(G3-v2-docs): report reviewed R-10v2 and R-40v2 results under REVIEW_G3_v2 binding constraints`) + `554c7c6` (`ctx_size: 32768` in `live_v2_prereg_lock.json`) | Active docs (`README.md`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`, `papers/04_clause_level_npu_supervision/main.tex`) report the narrower `R-10 v2` `36/36 vs 11/36` conflict-disclosure finding, the `D1` $\kappa = 0.20$ policy disagreement, the `-0.7 pp` to `+45.8 pp` pooled range, self-reported subagent provenance, and `73/73` true classifier over-escalations (`R-40 v2`). |
| **Reflog Confirmation (`REVIEW_G3_v2.md:54`: confirm `b425630` was never pushed before amend `6470776`)** | Verified via `git reflog --date=iso` | Local reflog entries:<br>- `b425630` (`2026-11-10 11:38:34 +0800`): `commit: wo45(R-10-v2-analysis): unblind and analyze R-10v2 cross-model 3-judge regrade and redaction sensitivity`<br>- `6470776` (`2026-11-10 12:02:54 +0800`): `commit (amend): wo45(R-10-v2-analysis): unblind and analyze R-10v2 cross-model 3-judge regrade and redaction sensitivity`<br>- `cc805f4` (`2026-11-10 12:07:44 +0800`): `commit: wo45(G3-v2): add Gate G3 v2 completion report` (pushed to `origin/main` after `12:07:44 +0800`).<br>**Confirmed:** `b425630` was amended locally `5` minutes before `cc805f4` was created and was never pushed to `origin/main`. |

---

## 2. Chronological Git Chain & Pre-Registration Conditions (`G4-1..G4-6`, `R-14`, `R-23`)

Every phase of Gate G4 was committed in strict chronological order (one task per commit; lock commit `554c7c6` pushed to `origin/main` **before** any live LLM generation started):

| Step | Commit (`HEAD` / ISO Timestamp) | Summary & Locked / Sealed Artifacts |
| :---: | :--- | :--- |
| **1** | `d50465697fd8cb4e30d3ca298266f5e85a7869b9`<br>(`2026-11-11 02:29:52 +0800`) | **`wo45(G4-6)`:** Removed the `7` dead special-case dispute-normalizer regex patterns from `src/lucca/core/proof_policy.py` (`0/360` effect verified in `R-22`; `360/360` Walton conformance verified unchanged) **before** locking. |
| **2** | `554c7c6bb29fee5028018479a3ff9c3079ef3e14`<br>(`2026-11-11 02:59:03 +0800`, **pushed to `origin/main` prior to generation**) | **`wo45(R-14,R-23)`:** Committed and pushed:<br>- `logs/test_reports/wo45/live_v2_prereg_lock.json` (`SHA-256: ee379f91ddc064c22040080c8c8468b9ef2dab9f50454cea9c8216cbf44580c5`)<br>- `logs/test_reports/wo45/live_v2_prereg_lock.json.ots` (`SHA-256: c5748359b9a7170f789ef33eab5912fd3b47bde163c97b5163fa8d0736e93ad7`, OpenTimestamps calendar commitment)<br>- `logs/test_reports/wo45/live_v2_selected_items.json` (`N=132` items = `11/cell`, `seed=20261111`, `33` disputed, `31` pre-declared from `R-40 v2` 73-item escalation set)<br>- Neutral rubric prompts `logs/test_reports/wo45/prompts/{g4_live_v2_judge_prompt,g4_subagent_task_prompt}.md` (`0` hits on banned arm/policy/model terms)<br>- All 5 SHA-256-locked scripts including `scripts/wo45/analyze_wo45_live_v2.py` (`7297cf3c…`) with pre-specified co-primary endpoints (`D4`, `D2`), exact binary 2-of-3 tie-break rule, and `10,000`-resample item-cluster bootstrap (`seed=20261111`). |
| **3** | `689c381e22365499244a8c28d964860d8760ec40`<br>(`2026-11-11 03:29:10 +0800`) | **`wo45(G4-live-pools)`:** Executed single pass of `1,980` live turns (`132` items $\times$ `3` contiguous arm batches `A, B, C` $\times$ `5` models at `ctx=32768`, `19:00:29Z..19:28:14Z`). Committed shuffled blinded pools (`g4_blinded_1980_replies.jsonl`, `g4_redacted_1980_replies.jsonl`), 20 input shards, and `live_v2_pool_manifest.json` (`SHA-256: 2f54c8d7c028d924133fd13b74b679c77933c8fa0d6cb0a2dee8c0f514f178cf`) sealing SHA-256 commitments of the withheld raw generations and unblinding keys **before** any judge ran. |
| **4** | `377ed7a8ab63db06f90555f9d4498e65b48b4322`<br>(`2026-11-11 08:12:42 +0800`) | **`wo45(G4-judges)`:** Committed all 6 raw 3-family blinded judge JSONL outputs (`all 6 SHA-256s distinct`), all 20 Judge 1 shard outputs, and all 6 pairwise $\kappa$ JSONs (`g4_kappa_{unredacted,redacted}_{j1_j2,j1_j3,j2_j3}.json`) **strictly before unblinding**. |
| **5** | `b9c7efb1c72a6ee39e0b5ab915c7f7d7318554a6`<br>(`2026-11-11 08:15:54 +0800`) | **`wo45(G4-analysis)`:** Unblinded sealed commitments (`g4_live_v2_raw_generations.json`, `g4_blinded_1980_key.json`, `g4_redacted_1980_key.json`) and ran the unmodified SHA-256-locked `scripts/wo45/analyze_wo45_live_v2.py` (`7297cf3c…`), producing `g4_live_v2_report.json` and `g4_live_v2_REPORT.md` (`sealed_commitments_verified: true`). |
| **6** | `7c2bda3f469bef6c1d4bf303ce0e2eb3cbb2d627`<br>(`2026-11-11 08:27:26 +0800`) | **`wo45(G4-docs)`:** Updated `README.md`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`, and `papers/04_clause_level_npu_supervision/main.tex` with full positive, null/negative, single-judge sensitivity, and `R-41` utility-cost disclosures. |

---

## 3. Judge Family Independence & Provenance Disclosure (`G4-2`)

Per `REVIEW_G3_v2.md:52-53, 69`, the 3 judge families, their raw artifact hashes, and provenance guarantees are explicitly distinguished:

1. **Judge 1 (`Google Gemini` family — `blinded_judge_writer` subagents invoked with `Model="flash"`):**
   - Unredacted output: `logs/test_reports/wo45/g4_judge1_gemini.jsonl` (`1,980` rows, `SHA-256: 32d4e959c07b160c713ac30ff125085ce9903841e32c734144dc68d3e94c2e9f`).
   - Redacted output: `logs/test_reports/wo45/g4_redacted_judge1_gemini.jsonl` (`1,980` rows, `SHA-256: eefdc239aed5ec143e476a324bf9e10dd0238488b12fb09eeca6338881353a7c`).
   - **Explicit Self-Reported Field Disclosure:** Subagents were spawned via `invoke_subagent(..., Model="flash")` across 20 isolated conversations (Unredacted Shards `01..10`: `2c77c17f-7e38-426d-ba37-9bc46fa0427b`, `9bb811a1-0313-41a1-bc53-b76c1dcfbec7`, `f81d04a4-889e-4391-ae3a-5b79d218f5d9`, `2cf0e048-55e1-4d82-8536-1e9afab5a9b0`, `1d9547eb-72ca-45af-a1d1-c6f01738fa12`, `8a02caec-81b1-42d9-89de-24cbcab4cbc7`, `b8863992-f54e-4560-991e-150ac53765f7`, `cb97ee93-1816-4218-91c5-1d4c0c08e891`, `a082ea6f-6380-4131-b364-61a1dce11e2e`, `4f54e05a-e17c-4b14-93f6-074837cffd8e`; Redacted Shards `01..10`: `ffad9ec6-efcc-4726-92ce-a2e4b53ee32a`, `88804f8d-638a-4289-8d38-a1c8283cccc6`, `2fb0c27c-7ecb-4131-9bc7-f752165e5d3a`, `f9609ca8-d9c0-491c-9c60-0c4b102aedca`, `26092ed8-8ae7-4c40-829e-7742125f6bfc`, `500c44cc-8bc0-4ca7-b60f-d9af5e814e5c`, `3d47785a-6dd9-4fe7-813b-fac0a3dc23bb`, `2e85363e-9c39-4261-9e45-1c3638e79c81`, `0e378a18-58b1-440b-abbf-5817de11219a`, `93c80c27-5a84-4641-a20e-270c7502fb75`). Inside the JSONL rows, `judge_model`, `temperature`, and `timestamp_utc` are **self-reported** by the subagent text completions (demonstrated by 19 shards self-reporting `"gemini-2.5-pro"` and Redacted Shard 07 [`3d47785a-6dd9-4fe7-813b-fac0a3dc23bb`, `198` rows] hallucinating `"claude-3-7-sonnet"` in its JSON string despite running under `Model="flash"`).
2. **Judge 2 (`Mistral AI` family — local `Mistral-Nemo-Instruct-2407-Q5_K_M.gguf`, `SHA-256: f2118506b57d31403cba021b476ceb95600cc278fbc2feeaaf884b6e64fa6ee5`):**
   - Unredacted output: `logs/test_reports/wo45/g4_judge2_mistral.jsonl` (`1,980` rows, `SHA-256: 754f3b1ce3c9ecfa56d17e227dd50374804a3db286aa53d6f541a920afaca2fa`).
   - Redacted output: `logs/test_reports/wo45/g4_redacted_judge2_mistral.jsonl` (`1,980` rows, `SHA-256: 786142a9bcc1c8c79bb6242454a5ca9f4e6513d983997de4cd398dfde429ade9`).
   - **Machine-Logged Provenance:** Served via isolated local `llama-server` (`build 11868`, `temperature=0.0`, `seed=42`, grammar-constrained `json_schema`) through locked `scripts/wo45/run_wo45_local_llm_judge.py`.
3. **Judge 3 Adjudicator (`Alibaba Qwen` family — local `Qwen3.8-27B-Ridge-GGUF`, `SHA-256: 95580dbdaad579582ee898257116abc18d7f3625a00c16a15735d41444a09f5e`):**
   - Unredacted output: `logs/test_reports/wo45/g4_judge3_qwen_adjudication.jsonl` (`1,659` rows on all `J1 != J2` items, `SHA-256: c2c3b2b810a2220eaf04ec28d82da4367a8f8bad4b4e5ebc55cab26bdcd1c80a`).
   - Redacted output: `logs/test_reports/wo45/g4_redacted_judge3_qwen_adjudication.jsonl` (`1,648` rows on all `J1 != J2` items, `SHA-256: b11748e35274d0940e8230f785706a43047b88fd253c4fcefcbd1f28c3e17834`).
   - **Machine-Logged Provenance:** Served via isolated local `llama-server` (`temperature=0.0`, `seed=42`, `enable_thinking=false`, grammar-constrained `json_schema`) through the unmodified locked `scripts/wo45/run_wo45_local_llm_judge.py` (unredacted pool executed across 8 deterministic 208-item shards to avoid a 4-slot KV truncation on `G4_1574` without modifying `run_wo45_local_llm_judge.py`).

### Inter-Rater Reliability Across All Judge Pairs (`G4-2`)

| Pool | Judge Pair (`n`) | `D1` (3-Class / Binary $\kappa$, Raw %) | `D2` (3-Class / Binary $\kappa$, Raw %) | `D3` (3-Class / Binary $\kappa$, Raw %) | `D4` (3-Class / Binary $\kappa$, Raw %) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Unredacted** | `J1 vs J2` (`1,980`) | `0.0493` / `0.0686` (`84.04%` / `84.44%`) | `0.1355` / `0.1845` (`94.24%` / `94.60%`) | `0.0055` / `0.0317` (`24.29%` / `90.56%`) | **`0.7657` / `0.7394` (`90.86%` / `91.46%`)** |
| **Unredacted** | `J1 vs J3` (`1,659`) | `0.4671` / `0.4953` (`86.02%` / `87.22%`) | `0.8366` / `0.8345` (`97.83%` / `97.83%`) | `0.4960` / `0.6628` (`86.26%` / `94.03%`) | **`0.7276` / `0.2424` (`94.82%` / `95.72%`)** |
| **Unredacted** | `J2 vs J3` (`1,659`) | `0.0898` / `0.1280` (`89.51%` / `89.99%`) | `0.1219` / `0.1715` (`93.13%` / `93.55%`) | `-0.0018` / `0.0601` (`1.87%` / `91.56%`) | **`0.6860` / `0.5935` (`93.31%` / `93.97%`)** |
| **Redacted `[STANDARD]`** | `J1 vs J2` (`1,980`) | `0.0645` / `0.0959` (`86.26%` / `86.82%`) | `0.1169` / `0.1469` (`93.28%` / `93.54%`) | `0.0099` / `0.0738` (`25.25%` / `88.79%`) | **`0.7883` / `0.7589` (`91.67%` / `92.02%`)** |
| **Redacted `[STANDARD]`** | `J1 vs J3` (`1,648`) | `0.5292` / `0.5228` (`89.62%` / `89.81%`) | `0.7770` / `0.7735` (`96.84%` / `96.84%`) | `0.4010` / `0.5156` (`82.89%` / `90.90%`) | **`0.7447` / `0.1424` (`95.39%` / `95.81%`)** |
| **Redacted `[STANDARD]`** | `J2 vs J3` (`1,648`) | `0.1013` / `0.1531` (`91.50%` / `92.05%`) | `0.1286` / `0.1656` (`93.51%` / `93.81%`) | `0.0013` / `0.0723` (`2.12%` / `92.48%`) | **`0.6980` / `0.6028` (`94.17%` / `94.60%`)** |

*(Note: Low `J1 vs J2` 3-class $\kappa$ on `D3` [`24.29%`] reflects label convention between `"NO"` vs `"N/A"` when hedging is absent; binary `D3 == "YES"` raw agreement is `90.56%` [`1793/1980`].)*

---

## 4. Gate G4 Task-by-Task Empirical Results (`R-11..R-17`, `R-41`)

### 4.1 Co-Primary Endpoint 1: `D4` Conflict Disclosure on Disputed Items (`R-11`, `R-13`, `G4-1`, `G4-3`, `G4-4`; `N_eff = 33` items, `165` turns/arm)

| Contrast & Analysis | Arm Hi (`k/N, % [95% Wilson CI]`) | Arm Lo (`k/N, % [95% Wilson CI]`) | Cluster-Bootstrap $\Delta$ (`[95% CI]`) | Bootstrap $p$ | Discordant |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Primary 3-Family Majority: `B vs C` (`G4-3` Key Test)** | **`163/165 (98.79%)` `[95.69%, 99.67%]`** | **`121/165 (73.33%)` `[66.11%, 79.49%]`** | **`+25.45 pp` `[+15.76, +35.76]`** | **`0.0001`** | **`43:1`** |
| **Primary 3-Family Majority: `B vs A`** | **`163/165 (98.79%)` `[95.69%, 99.67%]`** | `104/165 (63.03%)` `[55.45%, 70.02%]` | **`+35.76 pp` `[+25.45, +46.67]`** | **`0.0001`** | **`61:2`** |
| **Primary 3-Family Majority: `C vs A`** | `121/165 (73.33%)` `[66.11%, 79.49%]` | `104/165 (63.03%)` `[55.45%, 70.02%]` | `+10.30 pp` `[-0.61, +20.61]` | `0.0668` | `32:15` |
| **Redacted `[STANDARD]` (`G4-4`): `B vs C`** | **`163/165 (98.79%)` `[95.69%, 99.67%]`** | **`129/165 (78.18%)` `[71.28%, 83.80%]`** | **`+20.61 pp` `[+12.12, +30.30]`** | **`0.0001`** | **`35:1`** |
| **Redacted `[STANDARD]` (`G4-4`): `B vs A`** | **`163/165 (98.79%)` `[95.69%, 99.67%]`** | `107/165 (64.85%)` `[57.30%, 71.72%]` | **`+33.94 pp` `[+24.24, +44.24]`** | **`0.0001`** | **`58:2`** |
| **Single-Judge Sensitivity: Judge 1 (`Gemini`) Alone `B vs C`** | `157/165 (95.15%)` `[90.73%, 97.52%]` | `97/165 (58.79%)` `[51.16%, 66.02%]` | `+36.36 pp` `[+26.06, +46.67]` | `0.0001` | `62:2` |
| **Single-Judge Sensitivity: Judge 2 (`Mistral-Nemo`) Alone `B vs C`** | `165/165 (100.0%)` `[97.72%, 100.0%]` | `164/165 (99.39%)` `[96.65%, 99.89%]` | `+0.61 pp` `[0.00, +1.82]` | `0.7330` | `1:0` *(ceiling leniency: Arm A also `157/165 = 95.15%`)* |

- **Per-Model `D4` Breakdown (`B vs C`, `N=33` disputed items/model, 3-family majority):**
  - `E2B-heretic`: `31/33 (93.94%)` vs `24/33 (72.73%)` ($\Delta = +21.21\text{ pp}$, bootstrap $p = 0.0146$, exact McNemar `8:1`, $p = 0.0391$; Arm A `22/33 = 66.67%`).
  - `E4B-heretic`: `33/33 (100.0%)` vs `24/33 (72.73%)` ($\Delta = +27.27\text{ pp}$, bootstrap $p = 0.0001$, exact McNemar `9:0`, $p = 0.0039$; Arm A `19/33 = 57.58%`).
  - `E4B-stock`: `33/33 (100.0%)` vs `24/33 (72.73%)` ($\Delta = +27.27\text{ pp}$, bootstrap $p = 0.0001$, exact McNemar `9:0`, $p = 0.0039$; Arm A `23/33 = 69.70%`).
  - `12B-heretic`: `33/33 (100.0%)` vs `21/33 (63.64%)` ($\Delta = +36.36\text{ pp}$, bootstrap $p = 0.0001$, exact McNemar `12:0`, $p = 0.00049$; Arm A `20/33 = 60.61%`).
  - `26B-A4B-heretic`: `33/33 (100.0%)` vs `28/33 (84.85%)` ($\Delta = +15.15\text{ pp}$, bootstrap $p = 0.0078$, exact McNemar `5:0`, $p = 0.0625$; Arm A `20/33 = 60.61%`).

### 4.2 Co-Primary Endpoint 2: `D2` Factual Correctness (`G4-1`; `N_eff = 132` items, `660` turns/arm)
- **3-Family Majority (`B vs C`):** Arm B **`656/660 (99.39%, CI [98.45%, 99.76%])`** vs Arm C `629/660 (95.30%, CI [93.41%, 96.67%])` $\rightarrow$ **`+4.09 pp` `[+1.67, +6.82]`, $p = 0.0004$, discordant `31:4`**.
- **3-Family Majority (`B vs A`):** Arm B **`656/660 (99.39%)`** vs Arm A `593/660 (89.85%, CI [87.31%, 91.93%])` $\rightarrow$ **`+9.55 pp` `[+6.21, +13.18]`, $p = 0.0001$, discordant `66:3`**.
- **Single-Judge Sensitivity (`D2` `B vs C`):** Judge 1 (`Gemini`) alone: `646/660 (97.88%)` vs `614/660 (93.03%)` (`+4.85 pp`, $p = 0.0001$, `38:6`); Judge 2 (`Mistral-Nemo`) alone: `658/660 (99.70%)` vs `658/660 (99.70%)` (`0.00 pp`, $p = 1.0$).

### 4.3 Secondary & Negative / Cost Endpoints (`D1`, `R-12`, `R-16`, `R-17`, `R-41`)
1. **`D1` Epistemic Signalling (`G4-1` Secondary — Negative/Null `B vs C` Result):**
   - `J1 vs J2` binary $\kappa = 0.0686$ (confirming `K-1` from `REVIEW_G3_v2.md`).
   - Pooled across `132` items (`660` turns/arm), 3-family majority rates Arm B `612/660 (92.73%, CI [90.49%, 94.47%])` vs Arm C `627/660 (95.00%, CI [93.06%, 96.42%])` (**$\Delta(B-C) = -2.27\text{ pp}$ `[-5.15, +0.76]`, $p = 0.1444$, discordant `24:39`**) and vs Arm A `591/660 (89.55%)` (`+3.18 pp` `[-0.61, +6.97]`, $p = 0.1060$, `63:42`).
   - On the `33` non-disputed below-nominal-burden items (`165` turns/arm), Arm B scores **lower** (`124/165 = 75.15%`) than both Arm A (`139/165 = 84.24%`) and Arm C (`144/165 = 87.27%`), because blinded judges penalize domain-count hedging on non-conflicting sources as `UNDERCONFIDENT`.
2. **`R-16` Burden-Met Over-Hedge (`D3`) & `R-12 / R-41` Upward-Escalated Utility Cost:**
   - **Nominal burden-met (`66` items, `330` turns/arm):** `D3` over-hedging is `3/330 (0.91%, CI [0.31%, 2.64%])` on Arm B vs `8/330 (2.42%, CI [1.23%, 4.71%])` on Arm C ($\Delta = -1.52\text{ pp}$, $p = 0.2596$) and `28/330 (8.48%, CI [5.93%, 11.99%])` on Arm A ($\Delta = -7.58\text{ pp}$, $p = 0.0001$).
   - **Runtime NPU burden-met (`63` items, `315` turns/arm):** Arm B over-hedging is **`0/315 (0.00%, CI [0.00%, 1.20%])`**.
   - **`R-12 / R-41` Pre-Declared `31`-Item Escalated Subgroup (`155` turns/arm):** Across all `31` escalated items, `D3=YES` is `8/155 (5.16%, CI [2.64%, 9.85%])` on Arm B (`8/155` Arm A, `7/155` Arm C). Critically, all `3/330` Arm B nominal-burden-met over-hedges occur on the `3` nominal-met items falsely over-escalated by the NPU (`WEB360_LOW_024`, `WEB360_LOW_048`, `WEB360_MED_053` = `15` turns), establishing a measured **`R-41` over-hedge utility cost of `3/15 = 20.00%` (`95% Wilson CI [7.05%, 45.19%]`)** whenever NPU over-escalation flips a sufficient-evidence item into a burden-unmet contract.
3. **`R-17` Matched `E4B-stock` (`gemma-4-E4B-it-Q6_K.gguf`) vs `E4B-heretic` (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`) at `ctx=32768`:**
   - **Arm B:** Identical (`33/33 [100.0%]` `D4` conflict disclosure, `132/132 [100.0%]` `D2` correctness, McNemar $p = 1.0$; `D3` nominal-met `1/66` vs `0/66`, $p = 1.0$).
   - **Arm C:** Identical on `D4` (`24/33 [72.73%]` both, $p = 1.0$); `D2` `122/132 (92.42%)` stock vs `128/132 (96.97%)` heretic ($p = 0.1460$); `D3` nominal-met `5/66 (7.58%)` stock vs `1/66 (1.52%)` heretic ($p = 0.1250$).
   - **Arm A (Unguarded):** `E4B-stock` exhibits substantially higher spontaneous refusal/over-hedging on nominal-met items (`D3`: `18/66 [27.27%]` vs `6/66 [9.09%]`, McNemar `12:0`, $p = 0.00049$) and lower `D2` answer rate (`102/132 [77.27%]` vs `113/132 [85.61%]`, McNemar `3:14`, $p = 0.0074$), while `D4` conflict disclosure on disputed items does not significantly differ (`23/33 [69.70%]` stock vs `19/33 [57.58%]` heretic, McNemar `5:1`, $p = 0.2188$).

### 4.4 Serving Provenance, Peak `nvidia-smi` VRAM, & Turn Latency (`ctx=32768`)

| Model Key | Weight File (`SHA-256` prefix) | Peak VRAM (`MiB`) | Mean Turn Latency (`s`) | Latency by Arm (`A` / `B` / `C`) |
| :--- | :--- | :---: | :---: | :---: |
| **`E2B-heretic`** | `Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf` (`6e30dcc3…`) | `2,732 MiB` | `0.4042 s` | `0.3758 s` / `0.4665 s` / `0.3702 s` |
| **`E4B-heretic`** | `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (`ab52d2db…`) | `4,802 MiB` | `0.5579 s` | `0.5187 s` / `0.6284 s` / `0.5265 s` |
| **`E4B-stock`** | `gemma-4-E4B-it-Q6_K.gguf` (`fd83f3ef…`) | `4,970 MiB` | `0.5646 s` | `0.5291 s` / `0.6290 s` / `0.5357 s` |
| **`12B-heretic`** | `gemma-4-12b-heretic-Q6_K.gguf` (`ea50ec1e…`) | `10,920 MiB` | `1.2379 s` | `1.0357 s` / `1.6151 s` / `1.0628 s` |
| **`26B-A4B-heretic`** | `gemma-4-26B-A4B-it-heretic.Q6_K.gguf` (`4de6a5ba…`) | `11,452 MiB` | `1.2744 s` | `1.1793 s` / `1.4405 s` / `1.2035 s` |

---

## 5. Verification Suite Outputs

1. **Locked Pre-Registration + Sealed Commitment Verification (`scripts.wo45.analyze_wo45_live_v2.verify_integrity()`):**
   ```text
   {'verified_at_utc': '2026-11-11T00:28:28.960665+00:00',
    'lock_sha256': 'ee379f91ddc064c22040080c8c8468b9ef2dab9f50454cea9c8216cbf44580c5',
    'manifest_sha256': '2f54c8d7c028d924133fd13b74b679c77933c8fa0d6cb0a2dee8c0f514f178cf',
    'sealed_commitments_verified': True,
    'judge_files_sha256': {
      'g4_judge1_gemini.jsonl': '32d4e959c07b160c713ac30ff125085ce9903841e32c734144dc68d3e94c2e9f',
      'g4_judge2_mistral.jsonl': '754f3b1ce3c9ecfa56d17e227dd50374804a3db286aa53d6f541a920afaca2fa',
      'g4_judge3_qwen_adjudication.jsonl': 'c2c3b2b810a2220eaf04ec28d82da4367a8f8bad4b4e5ebc55cab26bdcd1c80a',
      'g4_redacted_judge1_gemini.jsonl': 'eefdc239aed5ec143e476a324bf9e10dd0238488b12fb09eeca6338881353a7c',
      'g4_redacted_judge2_mistral.jsonl': '786142a9bcc1c8c79bb6242454a5ca9f4e6513d983997de4cd398dfde429ade9',
      'g4_redacted_judge3_qwen_adjudication.jsonl': 'b11748e35274d0940e8230f785706a43047b88fd253c4fcefcbd1f28c3e17834'
    },
    'judge_hashes_distinct': True}
   ```
2. **Frozen `R-00` WO-44 Baseline SHA-256 Re-Check:**
   - `logs/test_reports/web_evidentiary_burden_360_report.json`: `d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad` (`True`)
   - `logs/test_reports/web_evidentiary_burden_360_REPORT.md`: `e90b4ceccb5faf1876457a9b5667bdf8d06e7518a6a11ce184955f38a8f8c9be` (`True`)
   - `logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`: `aeabb67c05ca8fb63bd933656e9bc017e0033fef58eea4a6434ce2b8dabd81eb` (`True`)
   - `data/benchmarks/web_evidentiary_burden_360.jsonl`: `db685e70e65b40ba42be0e3ea2bbf54ac00b72ec6c69546faeabcff3b5574e13` (`True`)
3. **Neutrality & Unconditioned Selection Grep Checks:**
   - `PROMPT_HITS` (`g4_live_v2_judge_prompt.md`, `g4_subagent_task_prompt.md` against arm names, legal standards, model names, and hazard labels): `{'g4_live_v2_judge_prompt.md': 0, 'g4_subagent_task_prompt.md': 0}`
   - `SELECT_CLASSIFIER_IMPORTS` (`scripts/wo45/select_wo45_live_v2_items.py` against `neural_hazard_classifier|proof_policy|classify_hazard|NeuralHazardClassifier`): `0`
4. **Static Gates (`uv run pytest tests/test_static_gates.py -q`):** `40 passed`.
