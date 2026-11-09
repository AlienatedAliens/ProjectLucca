# WO-45 Gate G2 Completion Report — Rebuilt Harness Fresh v2 Run, Gate Latency, Ablations, Baselines, and 73-Item Escalation Audit

- **Gate:** `G2` (`C-1..C-4` conditions resolution + `R-05`, `R-06`, `R-22`, `R-31`, `R-40`)
- **Status:** `DONE`
- **Baseline Integrity Verification (`R-00` Frozen Artifacts):**
  - `logs/test_reports/web_evidentiary_burden_360_report.json`: `d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad` (`IDENTICAL`)
  - `logs/test_reports/web_evidentiary_burden_360_REPORT.md`: `e90b4ceccb5faf1876457a9b5667bdf8d06e7518a6a11ce184955f38a8f8c9be` (`IDENTICAL`)
  - `logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`: `aeabb67c05ca8fb63bd933656e9bc017e0033fef58eea4a6434ce2b8dabd81eb` (`IDENTICAL`)
  - `data/benchmarks/web_evidentiary_burden_360.jsonl`: `db685e70e65b40ba42be0e3ea2bbf54ac00b72ec6c69546faeabcff3b5574e13` (`IDENTICAL`)

---

## 1. Per-Task Status & Commit Summary (Gate G2)

| Task ID | Status | Commit SHA | Artifact Paths & SHA-256 | Key Numbers (`k/N, %, CI`) |
| :--- | :---: | :---: | :--- | :--- |
| **`G1-conditions` (`C-1..C-4`)** | `DONE` | `3a40f1c` | `logs/test_reports/wo45/REVIEW_G1.md`, `logs/test_reports/wo45/wo42_locked_hzd_50_on_wo44_code_report.json` (`3d9005b9f69d15b7dd04b5f67b2bed1bda0637c8a5d27fad5bcdf5ba9e7de021`) | `subsystems.proof_policy = 50/50 (100.0%, CI [92.87%, 100.00%])` attributed to WO-42 code state (`2026-11-06`); also re-evaluated once on WO-44 code (`af188c46...`, `a37decbe...`) scoring `50/50 (100.0%)` |
| **`R-05` (`+ C-3`)** | `DONE` | `baf7c55` | `logs/test_reports/web_evidentiary_burden_360_v2_report.json` (`f32f267187362437c492d5066ab221ad383f17492db423df24c5d2b25cd25e90`), `logs/test_reports/web_evidentiary_burden_360_v2_REPORT.md` | Fresh 4-model run via `build_launch_command()` (`provenance: "fresh"`, `ctx_size: 8192` deliberate benchmark profile): `E2B` `0.47 s` (`2,560 MB`), `E4B` `0.58 s` (`4,502 MB`), `12B` `1.24 s` (`10,620 MB`), `26B-A4B` `1.31 s` (`11,102 MB`) |
| **`R-06`** | `DONE` | `978c6aa` | `logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json` (`d78b532f1be60394036e823426363858a99eb08c06403c4d109c70be51ff6c27`), `scripts/bench_wo45_r06_gate_latency.py` | Combined `evaluate_web_evidence_burden()` E2E (`N=360`, 3 warm-ups): **NPU** `6.575 ms` mean / `5.632 ms` p50 / `14.274 ms` p95 / `15.258 ms` p99; **CPU** `16.923 ms` mean / `16.348 ms` p50 / `38.101 ms` p95 / `48.406 ms` p99 |
| **`R-22`** | `DONE` | `4ccb9bb` | `logs/test_reports/wo45/r22_dispute_normalization_ablation.json` (`0c8a5e0a8a3d8084d1051961f845d927651171f1a0a871b2416f8769ee67054f`), `scripts/audit_wo45_r22_dispute_normalization.py`, `papers/04_clause_level_npu_supervision/main.tex:273` | Post-hoc analysis on WO-44 corpus: disabling all 7 special patterns (`:424-431`) changes `0/360` verdicts (`360/360 = 100.0%`); disabling broad negation/contrast strip (`:433-443`) changes `4/360` items (`356/360 = 98.89%`) |
| **`R-31`** | `DONE` | `4adbd1e` | `logs/test_reports/wo45/r31_nontrivial_baselines_360.json` (`b2a99c722457a0983b121c97b39bf3b4827e75b75a8fa44c83be9b76df9b9fd4`), `scripts/bench_wo45_r31_baselines.py` | Post-hoc analysis on WO-44 corpus (`N=360` binary casual gate): Count-only `210/360 (58.33%)`, Count+Dispute `300/360 (83.33%)`, Hazard-only (nominal `240/360 [66.67%]`, NPU `242/360 [67.22%]`), Static-`0.85` `240/360 (66.67%)` vs Lucca 2D E2E `348/360 (96.67%, CI [94.26%, 98.09%])` (`0/180` unsafe under-hedges) |
| **`R-40`** | `DONE` | `cf1f7d3` (prep), `70b1753` (results) | `logs/test_reports/wo45/prompts/r40_hazard_rater_prompt.md`, `logs/test_reports/wo45/r40_rater1.jsonl`, `logs/test_reports/wo45/r40_rater2.jsonl`, `logs/test_reports/wo45/r40_upward_escalations_73_audit.json` (`b0f5b0d051da2e646740415f6179bd1cd2c0fd4a3c026c9ccb82034a24a59c30`) | Dual blinded raters ($\kappa = 1.0000$, `73/73` agreement): **`0/73 (0.0%, CI [0.0%, 5.0%])` label errors**, **`73/73 (100.0%, CI [95.0%, 100.0%])` true classifier over-escalations**, **`0/73 (0.0%)` ambiguous** |

---

## 2. Detailed Return Blocks (Gate G2)

### `R-05` (+ Condition `C-3`) — Fresh 4-Model Run via `build_launch_command()` (`baf7c55`)
- **Artifact:** `logs/test_reports/web_evidentiary_burden_360_v2_report.json` (SHA-256: `f32f267187362437c492d5066ab221ad383f17492db423df24c5d2b25cd25e90`)
- **`llama-server` Build String:** `version: 0.7.0-dev (build 11868, commit 78a8ae14b) | built with Clang 20.1.8 for Windows x86_64`
- **Context Size Profile:** `ctx_size = 8192` (`deliberate_benchmark_profile_ctx_8192`; single-turn RAG prompts are `<1,024` tokens, whereas interactive multi-turn companion sessions use `ctx=65536`).
- **Per-Model Fresh Launch Commands, Provenance, VRAM, and Latencies (Contiguous Arm A $\to$ Arm B Batching):**

| Model (`tier_label`) | Provenance | Start $\to$ End UTC | Peak GPU VRAM | Mean Turn Latency (`Arm A` / `Arm B`) vs `82b1da8` | Exact Launch Command (`build_launch_command()`) |
| :--- | :---: | :--- | :---: | :---: | :--- |
| **`E2B`** (`E2B`) | `fresh` | `18:35:51Z` $\to$ `18:36:30Z` | `2,560.0 MB` | **`0.47 s`** (`0.41 s` / `0.53 s`) vs `0.49 s` | `C:\ProjectLucca\app\llama-server\llama-server.exe --model C:\ProjectLucca\models\llm\Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf --n-gpu-layers 99 --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 --cache-ram 4096 --parallel 1 --flash-attn on --host 127.0.0.1 --port 8089 --no-webui --jinja -ub 2048 --spec-type ngram-mod` |
| **`E4B`** (`E4B`) | `fresh` | `18:36:32Z` $\to$ `18:37:18Z` | `4,502.0 MB` | **`0.58 s`** (`0.52 s` / `0.64 s`) vs `0.65 s` | `C:\ProjectLucca\app\llama-server\llama-server.exe --model C:\ProjectLucca\models\llm\gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf --n-gpu-layers 99 --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 --cache-ram 4096 --parallel 1 --flash-attn on --host 127.0.0.1 --port 8089 --no-webui --jinja -ub 2048 --spec-type ngram-mod` |
| **`12B`** (`12B`) | `fresh` | `18:37:20Z` $\to$ `18:38:56Z` | `10,620.0 MB` | **`1.24 s`** (`0.96 s` / `1.52 s`) vs `1.50 s` | `C:\ProjectLucca\app\llama-server\llama-server.exe --model C:\ProjectLucca\models\llm\gemma-4-12b-heretic-Q6_K.gguf --n-gpu-layers 99 --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 --cache-ram 4096 --parallel 1 --flash-attn on --host 127.0.0.1 --port 8089 --no-webui --jinja -ub 2048 --spec-type ngram-mod` |
| **`26B-A4B`** (`26B-A4B`) | `fresh` | `18:38:59Z` $\to$ `18:40:54Z` | `11,102.0 MB` | **`1.31 s`** (`1.21 s` / `1.41 s`) vs `1.60 s` | `C:\ProjectLucca\app\llama-server\llama-server.exe --model C:\ProjectLucca\models\llm\gemma-4-26B-A4B-it-heretic.Q6_K.gguf --n-gpu-layers 99 --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 --cache-ram 4096 --parallel 1 --flash-attn on --host 127.0.0.1 --port 8089 --no-webui --jinja -ub 2048 --cpu-moe --load-mode none --moe-cache-mib 7680 --spec-type ngram-mod` |

### `R-06` — End-to-End `evaluate_web_evidence_burden()` Gate Latency on NPU vs. CPU (`978c6aa`)
- **Artifact:** `logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json`
- **Hardware:** `Intel(R) AI Boost` NPU vs `Intel(R) Core(TM) Ultra 9 275HX` CPU, OpenVINO `2026.4.0-22959`, Windows 11 (`10.0.26200`).

| OpenVINO Device (`N=360`, 3 warm-ups) | Metric | Mean (`ms`) | Stdev (`ms`) | Min (`ms`) | p50 (`ms`) | p95 (`ms`) | p99 (`ms`) | Max (`ms`) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`NPU` (`Intel AI Boost`)** | **Combined End-to-End `evaluate_web_evidence_burden()`** | **`6.575`** | `2.802` | `4.102` | **`5.632`** | **`14.274`** | **`15.258`** | `15.976` |
| `NPU` (`Intel AI Boost`) | Hazard Classifier Sub-Component (`npu_latency_ms`) | `5.320` | `2.463` | `3.210` | `4.545` | `12.012` | `12.783` | `13.430` |
| `NPU` (`Intel AI Boost`) | Walton Corroboration Sub-Component (`corroboration_latency_ms`) | `1.219` | `0.427` | `0.625` | `1.087` | `2.186` | `2.573` | `3.153` |
| **`CPU` (`Core Ultra 9 275HX`)** | **Combined End-to-End `evaluate_web_evidence_burden()`** | **`16.923`** | `8.562` | `9.453` | **`16.348`** | **`38.101`** | **`48.406`** | `49.315` |
| `CPU` (`Core Ultra 9 275HX`) | Hazard Classifier Sub-Component (`npu_latency_ms`) | `15.659` | `8.530` | `8.490` | `15.145` | `36.912` | `47.175` | `48.200` |
| `CPU` (`Core Ultra 9 275HX`) | Walton Corroboration Sub-Component (`corroboration_latency_ms`) | `1.227` | `0.340` | `0.665` | `1.139` | `1.946` | `2.383` | `2.652` |

### `R-22` — Dispute-Detection Normalization Audit & Ablation on $N=360$ (`4ccb9bb`, *Post-Hoc Analysis on the WO-44 Corpus*)
- **Artifact:** `logs/test_reports/wo45/r22_dispute_normalization_ablation.json`

| Pattern (`src/lucca/core/proof_policy.py`) | Introducing Commit (`git log -S`) | Matched Items in $N=360$ | Verdict Changes on $N=360$ When Disabled | Origin / Prior Dev Set Presence |
| :--- | :--- | :--- | :---: | :--- |
| `r"--no-[a-z0-9-]+"` (`:424`) | `82b1da8` (`2026-11-09`) | `[]` (`0`) | `0/360` (`360/360`) | Prior $N=60$ dev set (`WEB_HIGH_010`) |
| `r"\bto\s+prevent\b"` (`:426`) | `82b1da8` (`2026-11-09`) | `['WEB360_LOW_081']` (`1`) | `0/360` (`360/360`) | Prior $N=60$ dev set (`WEB_HIGH_009`, `WEB_HIGH_010`) |
| `r"\bdo\s+not\s+exceed\b"` (`:426`) | `82b1da8` (`2026-11-09`) | `[]` (`0`) | `0/360` (`360/360`) | Prior $N=60$ dev set (`WEB_HIGH_009`) & `LIVE_HIGH_01` |
| `r"\bcannot\s+be\s+undone\s+without\b"` (`:426`) | `82b1da8` (`2026-11-09`) | `[]` (`0`) | `0/360` (`360/360`) | Prior $N=60$ dev set (`WEB_HIGH_003`) |
| `r"\btakes\s+no\s+c\w*\b"` (`:427`) | `82b1da8` (`2026-11-09`) | `[]` (`0`) | `0/360` (`360/360`) | $N=6$ live Scrapling slice (`LIVE_LOW_02`) |
| `r"\bthat\s+are\s+not\s+part\s+of\b"` (`:427`) | `82b1da8` (`2026-11-09`) | `[]` (`0`) | `0/360` (`360/360`) | $N=6$ live Scrapling slice (`LIVE_MED_02` RFC 8259) |
| `r"\bbom\s+is\s+forbidden\b"` (`:427`) | `82b1da8` (`2026-11-09`) | `[]` (`0`) | `0/360` (`360/360`) | $N=6$ live Scrapling slice (`LIVE_MED_02` RFC 8259) |
| **All 7 special patterns disabled (`:424-431`)** | `82b1da8` (`2026-11-09`) | `1` item | **`0/360` (`360/360 = 100.0%`)** | Fitted on $N=60$ dev set + $N=6$ live slice |
| **Broad negation/contrast strip disabled (`:433-443`)** | `82b1da8` (`2026-11-09`) | — | **`4/360` (`356/360 = 98.89%`)** (`WEB360_LOW_021`, `LOW_075`, `HIGH_044`, `HIGH_071`) | Disclosed in Paper 4 (`main.tex:273`) |

### `R-31` — Non-Trivial Baselines on $N=360$ (`4adbd1e`, *Post-Hoc Analysis on the WO-44 Corpus*)
- **Artifact:** `logs/test_reports/wo45/r31_nontrivial_baselines_360.json`

| Baseline / Evaluator ($N=360$ Identical Items) | Casual Gate Accuracy (`k/N, %`) | 95% Wilson CI | Unsafe Under-Hedge (`k/180`) | Over-Hedge on Met Cells (`k/180`) | Conservative Safety (`k/360`) | Paired McNemar vs. Lucca 2D E2E ($b:c, p$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Static-`0.85` Strawman** | `240/360` (`66.67%`) | `[61.64%, 71.34%]` | `90/180` (`50.00%`) | `30/180` (`16.67%`) | `270/360` (`75.00%`) | `120:12`, $p = 1.42 \times 10^{-23}$ |
| **(a1) Count-Only (No Dispute Check: `1 -> hedge, >=2 -> assert`)** | `210/360` (`58.33%`) | `[53.18%, 63.31%]` | `120/180` (`66.67%`) | `30/180` (`16.67%`) | `240/360` (`66.67%`) | `146:8`, $p = 6.04 \times 10^{-34}$ |
| **(a2) Count + Dispute (No Hazard: `1 or disputed -> hedge`)** | `300/360` (`83.33%`) | `[79.13%, 86.83%]` | `30/180` (`16.67%`) | `30/180` (`16.67%`) | `330/360` (`91.67%`) | `56:8`, $p = 5.56 \times 10^{-10}$ |
| **(b1) Hazard-Only (Nominal Hazard: `HIGH -> hedge`)** | `240/360` (`66.67%`) | `[61.64%, 71.34%]` | `90/180` (`50.00%`) | `30/180` (`16.67%`) | `270/360` (`75.00%`) | `120:12`, $p = 1.42 \times 10^{-23}$ |
| **(b2) Hazard-Only (NPU Predicted Hazard: `HIGH -> hedge`)** | `242/360` (`67.22%`) | `[62.21%, 71.87%]` | `66/180` (`36.67%`) | `52/180` (`28.89%`) | `294/360` (`81.67%`) | `107:1`, $p = 6.72 \times 10^{-31}$ |
| **Lucca 2D (Nominal/Oracle Hazard + Walton)** | `360/360` (`100.00%`) | `[98.94%, 100.00%]` | `0/180` (`0.00%`) | `0/180` (`0.00%`) | `360/360` (`100.00%`) | `0:12`, $p = 4.88 \times 10^{-4}$ |
| **Lucca 2D End-to-End (NPU Hazard + Walton)** | **`348/360` (`96.67%`)** | **`[94.26%, 98.09%]`** | **`0/180` (`0.00%`)** | **`12/180` (`6.67%`)** | **`360/360` (`100.00%`)** | Reference |

### `R-40` — Blinded Dual-Rater Validation of the 73 Upward Escalations (`cf1f7d3`, `70b1753`)
- **Artifacts:** `logs/test_reports/wo45/prompts/r40_hazard_rater_prompt.md`, `logs/test_reports/wo45/r40_rater1.jsonl`, `logs/test_reports/wo45/r40_rater2.jsonl`, `logs/test_reports/wo45/r40_upward_escalations_73_audit.json` (`b0f5b0d051da2e646740415f6179bd1cd2c0fd4a3c026c9ccb82034a24a59c30`).
- **Inter-Rater Reliability:** `73/73` (`100.0%` raw agreement), 3-class Cohen's $\kappa = 1.0000$.
- **Adjudicated Breakdown (`{label error, true over-escalation, ambiguous}`):**
  - **`label_error`:** **`0/73` (`0.00%`, 95% Wilson CI `[0.00%, 5.00%]`)** — zero items were rated higher hazard than their nominal stratum by the blinded raters.
  - **`true_over_escalation`:** **`73/73` (`100.00%`, 95% Wilson CI `[95.00%, 100.00%]`)** — all 73 differences (`27` `low -> medium`, `22` `low -> high`, `24` `medium -> high`) are true classifier over-escalations (`72/73` rated `low` trivia/historical treaty dates by both raters; `1/73` [`R40_058` / `WEB360_MED_012`, IEEE 802.3af PoE standard] rated `medium` by both raters while NPU predicted `high`).
  - **`ambiguous`:** **`0/73` (`0.00%`, 95% Wilson CI `[0.00%, 5.00%]`)**.
