# WO-45 Hand-back

## A. Integrity

- **Baseline hashes (R-00) commit:** `c9706a1` (`2026-11-09 17:57:44 +0800`, `logs/test_reports/wo45/baseline_hashes.json`, `SHA-256: 25acfa3e893ef0e13b609d0cd7ae15b4a9a8c55edcab92fcc6bbce201a2c3ebe`)
- **End-of-WO re-hash of baseline files:** `4/4 frozen_measured_artifacts: IDENTICAL = yes`; `1/5 baseline_files` (`scripts/run_web_evidentiary_burden_benchmark.py`) intentionally modified under `R-08` and `R-09` (`e5131fb19c6dcd2778cc507cb49de363c8d4be5210a3444be7c311bdab9675ef` -> `e8ceabaacdc16c7d9b00f1fffa45a659a45269df96420d174351dc3578eb8718`):
  - `logs/test_reports/web_evidentiary_burden_360_report.json`: `d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad` (`IDENTICAL = yes`)
  - `logs/test_reports/web_evidentiary_burden_360_REPORT.md`: `e90b4ceccb5faf1876457a9b5667bdf8d06e7518a6a11ce184955f38a8f8c9be` (`IDENTICAL = yes`)
  - `logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`: `aeabb67c05ca8fb63bd933656e9bc017e0033fef58eea4a6434ce2b8dabd81eb` (`IDENTICAL = yes`)
  - `data/benchmarks/web_evidentiary_burden_360.jsonl`: `db685e70e65b40ba42be0e3ea2bbf54ac00b72ec6c69546faeabcff3b5574e13` (`IDENTICAL = yes`)
  - `scripts/run_web_evidentiary_burden_benchmark.py`: `e5131fb19c6dcd27...` -> `e8ceabaacdc16c7d...` (`IDENTICAL = no`, harness modified per `R-08`/`R-09` in commits `a6273f0` and `0d84768`)

- **All WO-45 commits in order:**
  1. `c9706a1 | wo45(R-00): record baseline SHA-256 snapshot of WO-44 artifacts | G0`
  2. `7303345 | wo45(G0): add Gate G0 completion report | G0`
  3. `6eac282 | wo45(R-01): replace false Ed25519 claims with HKDF HMAC-SHA256 symmetric integrity | G1`
  4. `22c5bd0 | wo45(R-02): replace non-existent models/deontic_ov with verified model paths and log latencies | G1`
  5. `25d1691 | wo45(R-03): trace and correct memory-poisoning and contrastive numbers with JSON key paths | G1`
  6. `804dbbf | wo45(R-04): retract unsourced LOCKED_HZD 49/50 vs 32/50 claim and report verified artifact statistics | G1`
  7. `468c502 | wo45(R-07): remove exclamations, superlatives, and unverified R-10/R-11 superiority claims | G1`
  8. `a6273f0 | wo45(R-08): wire build_launch_command, batch Arm A/B contiguously, remove LUCCA_BENCH_REUSE_MODELS, and retract ClauseSplitter claim | G1`
  9. `0d84768 | wo45(R-09): regenerate independent N=60 report, add per-model provenance fields, and label overwritten pre-fix numbers | G1`
  10. `2e5091e | wo45(R-20): disclose omission of neural_hazard_classifier.py from prereg lock and label 360/360 post-hoc in-sample | G1`
  11. `f6630b3 | wo45(R-23): disclose single-commit arrival of lock, corpus, and results in commit 82b1da8 | G1`
  12. `a27436a | wo45(R-30): relabel 360/360 Walton result as specification conformance test, add WO-44 correction notices, and rebuild Paper 4 PDF | G1`
  13. `2587be2 | wo45(G1): add Gate G1 completion report with verbatim AC outputs | G1`
  14. `3a40f1c | wo45(G1-conditions): resolve REVIEW_G1 conditions C-1, C-2, C-3 attribution, and C-4 wording | G2`
  15. `baf7c55 | wo45(R-05): run rebuilt build_launch_command harness across all 4 models into v2 report | G2`
  16. `978c6aa | wo45(R-06): measure end-to-end evaluate_web_evidence_burden latency on NPU and CPU | G2`
  17. `4ccb9bb | wo45(R-22): audit and ablate dispute-detection normalization patterns on N=360 corpus | G2`
  18. `4adbd1e | wo45(R-31): evaluate count-only and hazard-only baselines on N=360 corpus | G2`
  19. `cf1f7d3 | wo45(R-40-prep): lock blinded 73-query pool and rater prompt before evaluation | G2`
  20. `30a28ca | wo45(R-10-prep): lock blinded 288-reply pool and judge prompt before evaluation | G3`
  21. `70b1753 | wo45(R-40): validate 73 upward hazard escalations with dual blinded raters | G2`
  22. `3935ef6 | wo45(G2): add Gate G2 completion report | G2`
  23. `43814e6 | wo45(R-10): re-grade 288 existing replies with dual blinded judges and report kappa and semantic outcomes | G3`
  24. `fd7aaa8 | wo45(G3): add Gate G3 completion report and organize WO-45 scripts under scripts/wo45 | G3`
  25. `98c26a1 | wo45(G3-review): add REVIEW_G3.md, SUPERSEDED.md, Q-1 raw nvidia-smi VRAM evidence, and R-06/R-22/R-31 notes | G3-v2`
  26. `a5327b6 | wo45(G3-v2-prep): lock neutral R-10v2 and R-40v2 prompts, blinded/redacted/mixed pools, and kappa/source-check scripts before evaluation | G3-v2`
  27. `309856d | wo45(R-40-v2): redo 73-escalation audit in 163-item mixed pool with neutral prompt and cross-model raters | G3-v2`
  28. `46acc4a | wo45(R-10-v2-judges): commit raw blinded cross-model judge outputs and 3rd-judge adjudications before unblinding | G3-v2`
  29. `6470776 | wo45(R-10-v2-analysis): unblind and analyze R-10v2 cross-model 3-judge regrade and redaction sensitivity | G3-v2`
  30. `cc805f4 | wo45(G3-v2): add Gate G3 v2 completion report | G3-v2`
  31. `33bdb21 | wo45(G3-v2): align default KV cache ctx to 32768 and add 32K nvidia-smi VRAM evidence | G3-v2`
  32. `5257a15 | wo45(fix): revert config.py ctx change from evidence commit 33bdb21 | G3-v2`
  33. `36712d9 | wo45(A-1): set production LLMSettings.ctx to 32768 per owner request and sync active docs | G3-v2`
  34. `231d0ed | wo45(A-2,A-3): add REVIEW_G3_v2.md, capture ctx=65536 VRAM row, and label 8K->32K explanation as unmeasured | G3-v2`
  35. `f145a64 | wo45(G3-v2-docs): report reviewed R-10v2 and R-40v2 results under REVIEW_G3_v2 binding constraints | G3-v2`
  36. `d504656 | wo45(G4-6): remove 7 dead special-case dispute normalizer patterns from proof_policy.py | G4-v2`
  37. `554c7c6 | wo45(R-14,R-23): lock G4 live v2 preregistration, analysis script, prompts, and OpenTimestamps proof before generation | G4-v2`
  38. `689c381 | wo45(G4-live-pools): commit 1980-turn blinded unredacted/redacted pools and sealed SHA-256 commitments before judging | G4-v2`
  39. `377ed7a | wo45(G4-judges): commit raw 3-family blinded judge outputs and kappa reports before unblinding | G4-v2`
  40. `b9c7efb | wo45(G4-analysis): unblind and run locked G4 live v2 cluster-bootstrap analysis | G4-v2`
  41. `7c2bda3 | wo45(G4-docs): report G4 live v2 3-arm 5-model results and R-41 utility cost across active docs | G4-v2`
  42. `6629d18 | wo45(G4): add Gate G4 sign-off report and verification outputs | G4-v2`
  43. `1bb51a8 | wo45(RM-0): add REVIEW_G4.md, v2 measurement-defect caveats, and interim wording fixes | G4-v3`
  44. `5c22626 | wo45(RM-1): add split binary rubric v3 and neutrality grep verification | G4-v3`
  45. `f31ec78 | wo45(RM-2a): commit 106-item judge qualification set prior to judge screening | G4-v3`
  46. `988e62c | wo45(RM-2b): qualify 3 non-Google judge families (Qwen, Phi-4, Mistral-Nemo) on 106-item set | G4-v3`
  47. `009869b | wo45(RM-3): add arm-identical normalizer with 0 lexicon hits and <=60% arm-guess verification | G4-v3`
  48. `d7308f8 | wo45(RM-7): evaluate R-42 hazard v2 retraining on non-v3 hard negatives and enforce strict 1pp fallback | G4-v3`
  49. `4a6ecdd | wo45(RM-4,RM-5,RM-6a): lock 4-arm G4 v3 preregistration, fresh 132 items, analysis script, and OTS proof | G4-v3`
  50. `c5ec1fd | wo45(RM-8,RM-6b): generate 2640 live 4-arm 5-model turns, seal pools, and OTS-stamp manifest | G4-v3`
  51. `e198f1a | wo45(RM-6c): add and OTS-stamp primary normalized Judge 1 (Qwen3.8-27B) | G4-v3`
  52. `28ded25 | wo45(RM-6c): add and OTS-stamp primary normalized Judge 2 (Phi-4-14B) | G4-v3`
  53. `329ed2b | wo45(RM-2b,RM-6a-amend1): qualify Nemotron-3.5-30B as Judge 3 and OTS-stamp pre-unblinding amendment | G4-v3`
  54. `c39da09 | docs(paper-04): rebuild clean 04_clause_level_npu_supervision.pdf synced with WO-45 main.tex (AI-assisted) | G4-v3`
  55. `400c80a | wo45(RM-6c): add and OTS-stamp primary normalized Judge 3 (Nemotron-3.5-30B) | G4-v3`
  56. `d651bd8 | wo45(RM-6c): add and OTS-stamp secondary raw Judge 1 (Qwen3.8-27B) | G4-v3`
  57. `78cacfc | wo45(RM-6c): add and OTS-stamp secondary raw Judge 2 (Phi-4-14B) | G4-v3`
  58. `de5815c | wo45(RM-6c): add and OTS-stamp secondary raw Judge 3 (Nemotron-3.5-30B) | G4-v3`
  59. `4604afd | wo45(RM-9,RM-6d): unblind sealed v3 pools, run locked 4-arm analysis, and OTS-stamp report | G4-v3`
  60. `55cefba | wo45(RM-10): add GATE_G4v3.md and update README, review packet, and Paper 4 with G4 v3 results | G4-v3`
  61. `dc50fef | fix(core,lifecycle,docs): wire 1-strike operator_correct demotion, OpenVINO CPU fallback in env_check, and accurate README hardware/limitations | Companion-Fixes`
  62. `83f8486 | feat(memory,lifecycle,docs): add RFC 8032 Ed25519 provenance signing, signed rule-approval tokens, and clean README audit ledger | Companion-Fixes`
  63. `05f9f36 | chore(verifier,bench): lock DeBERTa-v3-xsmall NLI verifier v2 + OTS proof before holdout generation | Companion-NLI-v2`
  64. `c671aa4 | feat(bdi,memory): add valid_until premise expiry and Ed25519 precondition audit receipts (AI-assisted) | Companion-Fixes`
  65. `39a8283 | test(bench): add blinded out-of-sample NLI v2 holdout corpus (N=120) + OTS proof | Companion-NLI-v2`
  66. `9fd9655 | feat(verifier,docs): record pre-registered DeBERTa-v3-xsmall NLI v2 holdout evaluation + OTS proof | Companion-NLI-v2`
  67. `6c712be | feat(bdi,policy): harden premise gate with Z3 bounds, Ed25519 tamper checks, TOOL_VERIFIED provenance, and deontic_policy.toml (AI-assisted) | Companion-Fixes`
  68. `3dad5cb | wo45(G7): add standalone lucca-epistemic wheel (R-51), Paper 4 related-work table (R-50), and grant artifact map (R-52/R-53) | G7`
  69. `7859451 | wo45(R-21): lock multi-clause hazard holdout preregistration, ClauseSplitter (R-08.3), and R-42 disjoint v3 + OTS | G5`
  70. `4c8c2dc | wo45(R-21): add blinded N=130 multi-clause hazard corpus and dual-rater ground truth + OTS | G5`
  71. `f6f0ad6 | wo45(R-21): record single-shot N=130 multi-clause hazard holdout results, R-42 cost analysis, and GATE_G5 + OTS | G5`
  72. `321cafa | wo45(R-33): implement shingle/SimHash syndication dedup, NLI cross-cluster dispute check, and lock fresh holdout + OTS | G6`
  73. `865d730 | wo45(R-33): add blinded fresh N=45 Domain Set B sybil/syndication holdout corpus + OTS | G6`
  74. `02b7803 | wo45(R-33): record single-shot fresh N=45 sybil/syndication holdout evaluation results + OTS | G6`
  75. `eff8865 | wo45(R-32): lock N=64 live ResearchTool/Scrapling real-web preregistration and raw-HTML archiving + OTS | G6 (voided pre-collection)`
  76. `780ec9e | wo45(R-32): void v1 lock pre-collection, fix O(N) DOM sanitizer and DDGS Yahoo fallback, and lock v2 + OTS | G6`
  77. `d2c532b | wo45(R-32): add N=64 live Scrapling real-web corpus, raw HTML archive, and dual-rater ground truth + OTS | G6`
  78. `873e197 | wo45(R-32,G6): record single-shot N=64 real-web Scrapling evaluation results and GATE_G6 + OTS | G6`
  79. `(this commit) | wo45(G8): complete full verification suite, Paper 4/README updates, and WO45_HANDBACK | G8`

- **Lock commits precede corpus/result commits:** `yes` — verified across every pre-registered run on `origin/main` (100% of locked file hashes match at each results commit):
  - **`R-14` (`G4 v2` historical):** lock `554c7c6` (`2026-11-11 02:59:03 +0800`) -> blinded pools `689c381` (`03:29:10 +0800`) -> raw judge outputs `377ed7a` (`08:12:42 +0800`) -> unblinded results `b9c7efb` (`08:15:54 +0800`).
  - **`R-14` (`G4 v3` primary):** lock `4a6ecdd` (`2026-11-12 05:03:24 +0800`) -> sealed `2,640`-turn pools `c5ec1fd` (`05:43:32 +0800`) -> pre-unblinding Judge-3 amendment `329ed2b` (`10:20:36 +0800`) & 6 individual judge commits `e198f1a`..`de5815c` (`08:06:55`..`16:52:11 +0800`) -> unblinded results `4604afd` (`16:55:43 +0800`).
  - **Companion `NLI v2`:** lock `05f9f36` (`2026-11-12 21:52:48 +0800`) -> blinded `N = 120` corpus `39a8283` (`22:09:54 +0800`) -> single-shot results `9fd9655` (`22:16:08 +0800`, `10/10` locked files verified).
  - **`R-21` / `R-42` (`G5`):** lock `7859451` (`2026-11-12 23:34:52 +0800`) -> blinded `N = 130` corpus + dual raters `4c8c2dc` (`23:56:03 +0800`) -> single-shot results `f6f0ad6` (`2026-11-13 00:03:21 +0800`, `19/19` locked files verified).
  - **`R-33` (`G6`):** lock `321cafa` (`2026-11-13 01:08:42 +0800`) -> blinded `N = 45` Domain Set B corpus `865d730` (`01:29:08 +0800`) -> single-shot results `02b7803` (`01:32:18 +0800`, `15/15` locked files verified).
  - **`R-32` (`G6`):** voided pre-collection v1 lock `eff8865` (`01:34:26 +0800`, `0` items collected/evaluated); active v2 lock `780ec9e` (`2026-11-13 02:05:35 +0800`) -> live `N = 64` Scrapling corpus + `250` `.html.gz` archive + dual raters + adjudicator `d2c532b` (`02:46:09 +0800`) -> single-shot results `873e197` (`02:58:15 +0800`, `21/21` locked files verified).

- **External timestamps (`30` OpenTimestamps `.ots` proofs committed next to locks, corpora, raters, and reports):**
  - `logs/test_reports/wo45/live_v2_prereg_lock.json.ots` (`SHA-256: c5748359b9a7170f789ef33eab5912fd3b47bde163c97b5163fa8d0736e93ad7`)
  - `logs/test_reports/wo45/live_v3_prereg_lock.json.ots` (`SHA-256: ac06f598b4c3ffee38a1e736eb26c4a97c8d318e143f70cb2d2a0bcc4af2afba`)
  - `logs/test_reports/wo45/live_v3_prereg_amendment1_judge3_nemotron.json.ots` (`SHA-256: e0cb0498a364e03ea718977eb73bdca7fd5e2c8868521aa2e0dbf8d982169e2d`)
  - `logs/test_reports/wo45/live_v3_pool_manifest.json.ots` (`SHA-256: aecf026468e4dd3ad5c1421cf872355c2cd80101344ea104b51dbdd548b86a50`)
  - `logs/test_reports/wo45/g4v3_norm_judge1_qwen38_27b.jsonl.ots` (`SHA-256: a0400eccc5fc5907390d280993757af7aa58f36c7ffde09060f7a5d08fecb15f`)
  - `logs/test_reports/wo45/g4v3_norm_judge2_phi4_14b.jsonl.ots` (`SHA-256: 6c6bb44ac832774cd1c9ba0fc0275636f345f9a7e9700ccd80bb1bfb312f36cc`)
  - `logs/test_reports/wo45/g4v3_norm_judge3_nemotron35_30b.jsonl.ots` (`SHA-256: 58d0efad47c554ea0438a684e284ef49792a28ebeaa1e72af2cd73a05f2f4bbd`)
  - `logs/test_reports/wo45/g4v3_raw_judge1_qwen38_27b.jsonl.ots` (`SHA-256: 14a8a0d38fdb7e54b4ba8b6b33025a232eb2fec77a879cb651d16fb43e78d8ff`)
  - `logs/test_reports/wo45/g4v3_raw_judge2_phi4_14b.jsonl.ots` (`SHA-256: 6d8d223d2b578c608961a198ffd6f0c56f78f06884b8019ffa15b7d8fec796c2`)
  - `logs/test_reports/wo45/g4v3_raw_judge3_nemotron35_30b.jsonl.ots` (`SHA-256: 737ca699cbb3b903d0e8c79d8714a09ca70b052b6815b45214dc502b0736a998`)
  - `logs/test_reports/wo45/g4_live_v3_report.json.ots` (`SHA-256: c0488f8efcef8e9b1ca8cd9c86d50501429f9f30aeae40da993fafdbfb9a103c`)
  - `logs/test_reports/nli_verifier_v2_prereg_lock.json.ots` (`SHA-256: 4f6f29edbe1ba7f07c0c2c53d503b774e4148101dbb57340913d1e3d634c06bf`)
  - `data/benchmarks/nli_holdout_v2_120.jsonl.ots` (`SHA-256: cdd24dfe41080e8d20c9422a75ce7fe767e508160394088111788648274a6a5f`)
  - `logs/test_reports/nli_verifier_v2_report.json.ots` (`SHA-256: eefad2e0fbfaff07dd16a105500da38e0d07148ba7de834f8744b38832482803`)
  - `logs/test_reports/wo45/r21_hazard_holdout_prereg_lock.json.ots` (`SHA-256: d212dafca8dda2b1c26b6c8dee618bbacd05075459303381dce4e3b0fe6d943d`)
  - `data/benchmarks/wo45_r21_multiclause_hazard_130.jsonl.ots` (`SHA-256: 8584dab54b21c60cc0dcb1bbdfd48b40a4ddf5591ad0747cecc1d58b8e175733`)
  - `logs/test_reports/wo45/r21_rater1.jsonl.ots` (`SHA-256: 759af824358d456a5cc09a1c99842f9389f65dd7baf98cbbadb69cad10514539`)
  - `logs/test_reports/wo45/r21_rater2.jsonl.ots` (`SHA-256: 0b9a4b6349bf16cef81a09a6f72fc2521dcee288df18db36d2d8785dd266e6ef`)
  - `logs/test_reports/wo45/r21_hazard_holdout_report.json.ots` (`SHA-256: a6d4318566860c57d91ca8739911abe99dee8b4a14177cfaca48ffdf6771188a`)
  - `logs/test_reports/wo45/r33_sybil_holdout_prereg_lock.json.ots` (`SHA-256: b3f08fd39b17891d114a49d246534a09c16f417793aef8f6cd30e266fc7bfcf9`)
  - `data/benchmarks/wo45_r33_sybil_holdout_45.jsonl.ots` (`SHA-256: e9c1d0b0484bda85a263a2bf7c5ffd746858ac3b7f3ff300be9bedf9843fcd67`)
  - `logs/test_reports/wo45/r33_sybil_dedup_report.json.ots` (`SHA-256: 74657c506ece1e09690c0660e1803cfabd687219fbd9159a953f89d39e4ca77c`)
  - `logs/test_reports/wo45/r32_real_web_prereg_lock.json.ots` (`SHA-256: 96867d01b04aa709911dcbf9788ce0e7e86abbf5ce475e1cc6ae8e940395fd6c`)
  - `logs/test_reports/wo45/r32_real_web_prereg_lock_v2.json.ots` (`SHA-256: 185133dd2986741cacaa2851abc54088cf48a5032b39c9bfca99dc907089e2ab`)
  - `data/benchmarks/web_evidentiary_burden_real_v1.jsonl.ots` (`SHA-256: 3721207ed8d84225e27daab7d64cf8e70ea6466aebbdf7b1fbb4326479e3fdbe`)
  - `data/benchmarks/web_real_v1_archive/manifest_sha256.json.ots` (`SHA-256: 9e3ad582882673b15aa20400ddabc8a9b358164d3c59e39440f83aaaee285685`)
  - `logs/test_reports/wo45/r32_rater1.jsonl.ots` (`SHA-256: 2c6c6e7ce5d9699ae95c2b71f37b54c6d32ff0c58076eaed5e5afc09060dce8f`)
  - `logs/test_reports/wo45/r32_rater2.jsonl.ots` (`SHA-256: 16709179dff5440d96b41e2259d738f7b3a67302bbe04f583d1eaf6e52636`)
  - `logs/test_reports/wo45/r32_adjudicator.jsonl.ots` (`SHA-256: d87386a2c287eeba75f8044666906b7efcd624b79f37850fc1506c68b05b28df`)
  - `logs/test_reports/wo45/r32_real_web_v1_report.json.ots` (`SHA-256: 1302947f1b222f511c2c406ddd8aa019c3fda3709c138b33bab5ed6b981a35f1`)

### Verbatim Mandatory AC Command Outputs (`plans/2026-11-09_wo45_EXECUTOR_PROMPT.md:65-79`)

```text
:: R-08
> findstr /n "build_launch_command" scripts\run_web_evidentiary_burden_benchmark.py
40:from lucca.brain.server_ctl import build_launch_command  # noqa: E402
261:        cmd = build_launch_command(llm_cfg, LUCCA_HOME)

> findstr /n "LUCCA_BENCH_REUSE_MODELS" scripts\run_web_evidentiary_burden_benchmark.py
(no output, EXITCODE=1)

> findstr /n "ClauseSplitter split_clauses" src\lucca\core\proof_policy.py
47:    ClauseSplitter,
49:    split_clauses,
112:    Classifies the hazard level of a claim or topic using `ClauseSplitter.split_clauses()`
125:    clauses = ClauseSplitter.split_clauses(text) or split_clauses(text)

:: R-09
> certutil -hashfile logs\test_reports\web_evidentiary_burden_360_report.json SHA256
SHA256 hash of logs\test_reports\web_evidentiary_burden_360_report.json:
d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad
CertUtil: -hashfile command completed successfully.

> certutil -hashfile logs\test_reports\web_evidentiary_burden_60_report.json SHA256
SHA256 hash of logs\test_reports\web_evidentiary_burden_60_report.json:
1591cc10820cd8bc6305f1ac621827d40bd1d87bf2a4b9a0a20af8ed93c6a230
CertUtil: -hashfile command completed successfully.

:: R-01
> findstr /s /i /n "ed25519" papers\*.tex luccadocs\*.md README.md logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md
luccadocs\ARCHITECTURE.md:135:        HKDF HMAC-SHA256 symmetric tamper detection (Ed25519 is not used)
luccadocs\ARCHITECTURE.md:631:| **D-AUD-09** | Cryptographic Provenance | `ProvenanceGate` with HKDF HMAC-SHA256 symmetric integrity envelopes (`src/lucca/memory/signers.py`; Ed25519 is not used). | **Enforced** |
luccadocs\ARCHITECTURE.md:775:        BILATTICE --> PROV["Provenance Envelope (HKDF HMAC-SHA256; Ed25519 is not used)"]
luccadocs\ARCHITECTURE.md:850:    ProvenanceEnvelope --> SQLiteStore: Symmetric Integrity Storage (HKDF HMAC-SHA256; Ed25519 is not used)
luccadocs\archive\2026-09-17_pre_phase4_audit\08_adr\ADR-006_provenance_tiers_and_signers.md:75:| Asymmetric signatures (Ed25519) per source | Only valuable when verifier and signer are different trust domains (e.g. a remote tool host). Not needed now; the `Protocol` allows it later. |
luccadocs\archive\2026-09_handovers\IMPLEMENTATION_WALKTHROUGH.md:772:     - Sensitive credentials and keys (`.git`, `.ssh`, `id_rsa`, `id_ed25519`, `.env`)
luccadocs\archive\2026-09_milestone_specs\RECON_REPORT.md:163:     `..`, `../`, `..\`, `c:\windows`, `c:/windows`, `system32`, `syswow64`, `c:\program files`, `/etc`, `/usr`, `/bin`, `/sbin`, `/var`, `/proc`, `/sys`, `.git`, `.ssh`, `id_rsa`, `id_ed25519`, `.env`.
luccadocs\archive\2026-09_milestone_specs\TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md:292:| **Provenance Signing (`UserSpeechSigner`)**| `src/lucca/memory/store.py` | **Implemented & Measured** | Commit `3837ff7`; HKDF HMAC-SHA256 symmetric integrity envelopes (`D-AUD-09`, `src/lucca/memory/signers.py`; Ed25519 is not used); untrusted content tagging |
luccadocs\DECISIONS.md:80:- **Decision:** Manual memory additions, updates, and deletions via the UI or admin CLI must pass through `ProvenanceGate` with HKDF HMAC-SHA256 symmetric integrity envelopes (`src/lucca/memory/signers.py`; Ed25519 is not used). Arbitrary `signature="manual"` bypasses are prohibited.
README.md:61:> **Scientific Audit & Provenance Ledger (`WO-39` – `WO-45`):** ... including `WO-44` (`82b1da8`, where Ed25519 was not used and `v1`/`v2` web-burden runs were superseded by pre-registered `G4 v3`) ...
logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md:6:> 1. **Ed25519 Claim Retracted (`R-01`):** Memory records are signed via symmetric HKDF HMAC-SHA256 (`src/lucca/memory/signers.py:57-75`) under a local master key; asymmetric Ed25519 signatures are not used.
logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md:27:   - Symmetric HKDF HMAC-SHA256 integrity signing of memory records across 5 isolated memory tiers under a local master key (`src/lucca/memory/signers.py:57-75`; asymmetric Ed25519 third-party-verifiable signatures are not used).
logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md:187:| **1. NLnet Foundation (NGI Zero Commons Fund — Primary Target)** | ... (note: WO-44 `82b1da8` used HKDF HMAC-SHA256 where Ed25519 is not used; RFC 8032 asymmetric provenance signing was implemented post-WO-44 in `83f8486` and `packages/lucca-epistemic`) ...

:: R-02
> findstr /s /i /n "deontic_ov" papers\*.tex luccadocs\*.md README.md logs\test_reports\*.md
logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md:7:> 2. **Non-Existent `models/deontic_ov` Retracted (`R-02`):** Replaced with the three actual OpenVINO NPU directories (`models/action_claim_verifier_ov` [`12.13 ms`], `models/proof_policy_hazard_ov` [`5.35 ms`], `models/router_intent_ov` [`1.22 ms`]).
logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md:25:   - **OpenVINO NPU Classifiers (`models/action_claim_verifier_ov`, `models/proof_policy_hazard_ov`, `models/router_intent_ov`):** ... (Note: an earlier draft erroneously cited a non-existent `models/deontic_ov` directory.)
logs\test_reports\wo45\AUDIT_AND_RETRACTION_HISTORY.md:12:2. **Non-Existent `models/deontic_ov` (`R-02`):** `WO-44` cited `models/deontic_ov` (`~4.1 ms`). The actual OpenVINO NPU models are `models/action_claim_verifier_ov` (`12.13 ms` multi-clause mean), `models/proof_policy_hazard_ov` (`5.35 ms` mean), and `models/router_intent_ov` (`1.22 ms` mean).

:: lock ordering (R-14, R-21, R-32, R-33)
> git log --format="%h %ad %s" --date=iso -- logs/test_reports/wo45/
873e197 2026-11-13 02:58:15 +0800 wo45(R-32,G6): record single-shot N=64 real-web Scrapling evaluation results and GATE_G6 + OTS
d2c532b 2026-11-13 02:46:09 +0800 wo45(R-32): add N=64 live Scrapling real-web corpus, raw HTML archive, and dual-rater ground truth + OTS
780ec9e 2026-11-13 02:05:35 +0800 wo45(R-32): void v1 lock pre-collection, fix O(N) DOM sanitizer and DDGS Yahoo fallback, and lock v2 + OTS
eff8865 2026-11-13 01:34:26 +0800 wo45(R-32): lock N=64 live ResearchTool/Scrapling real-web preregistration and raw-HTML archiving + OTS
02b7803 2026-11-13 01:32:18 +0800 wo45(R-33): record single-shot fresh N=45 sybil/syndication holdout evaluation results + OTS
321cafa 2026-11-13 01:08:42 +0800 wo45(R-33): implement shingle/SimHash syndication dedup, NLI cross-cluster dispute check, and lock fresh holdout + OTS
f6f0ad6 2026-11-13 00:03:21 +0800 wo45(R-21): record single-shot N=130 multi-clause hazard holdout results, R-42 cost analysis, and GATE_G5 + OTS
4c8c2dc 2026-11-12 23:56:03 +0800 wo45(R-21): add blinded N=130 multi-clause hazard corpus and dual-rater ground truth + OTS
7859451 2026-11-12 23:34:52 +0800 wo45(R-21): lock multi-clause hazard holdout preregistration, ClauseSplitter (R-08.3), and R-42 disjoint v3 + OTS
3dad5cb 2026-11-12 22:48:21 +0800 wo45(G7): add standalone lucca-epistemic wheel (R-51), Paper 4 related-work table (R-50), and grant artifact map (R-52/R-53)
4604afd 2026-11-12 16:55:43 +0800 wo45(RM-9,RM-6d): unblind sealed v3 pools, run locked 4-arm analysis, and OTS-stamp report
de5815c 2026-11-12 16:52:11 +0800 wo45(RM-6c): add and OTS-stamp secondary raw Judge 3 (Nemotron-3.5-30B)
78cacfc 2026-11-12 15:25:12 +0800 wo45(RM-6c): add and OTS-stamp secondary raw Judge 2 (Phi-4-14B)
d651bd8 2026-11-12 14:22:14 +0800 wo45(RM-6c): add and OTS-stamp secondary raw Judge 1 (Qwen3.8-27B)
400c80a 2026-11-12 11:58:48 +0800 wo45(RM-6c): add and OTS-stamp primary normalized Judge 3 (Nemotron-3.5-30B)
329ed2b 2026-11-12 10:20:36 +0800 wo45(RM-2b,RM-6a-amend1): qualify Nemotron-3.5-30B as Judge 3 and OTS-stamp pre-unblinding amendment
28ded25 2026-11-12 09:09:58 +0800 wo45(RM-6c): add and OTS-stamp primary normalized Judge 2 (Phi-4-14B)
e198f1a 2026-11-12 08:06:55 +0800 wo45(RM-6c): add and OTS-stamp primary normalized Judge 1 (Qwen3.8-27B)
c5ec1fd 2026-11-12 05:43:32 +0800 wo45(RM-8,RM-6b): generate 2640 live 4-arm 5-model turns, seal pools, and OTS-stamp manifest
4a6ecdd 2026-11-12 05:03:24 +0800 wo45(RM-4,RM-5,RM-6a): lock 4-arm G4 v3 preregistration, fresh 132 items, analysis script, and OTS proof
b9c7efb 2026-11-11 08:15:54 +0800 wo45(G4-analysis): unblind and run locked G4 live v2 cluster-bootstrap analysis
377ed7a 2026-11-11 08:12:42 +0800 wo45(G4-judges): commit raw 3-family blinded judge outputs and kappa reports before unblinding
689c381 2026-11-11 03:29:10 +0800 wo45(G4-live-pools): commit 1980-turn blinded unredacted/redacted pools and sealed SHA-256 commitments before judging
554c7c6 2026-11-11 02:59:03 +0800 wo45(R-14,R-23): lock G4 live v2 preregistration, analysis script, prompts, and OpenTimestamps proof before generation
c9706a1 2026-11-09 17:57:44 +0800 wo45(R-00): record baseline SHA-256 snapshot of WO-44 artifacts
```

### Gate G8 Verification Suite Outputs (`ruff`, `mypy`, `lint-imports`, `test_static_gates.py`, and Full `pytest`)

```text
> uv run ruff check
All checks passed!

> uv run mypy src
Success: no issues found in 199 source files

> uv run lint-imports
Analyzed 199 files, 697 dependencies.
Contracts: 8 kept, 0 broken.

> uv run pytest tests/test_static_gates.py -q
40 passed in 12.49s

> uv run pytest
collected 1847 items / 73 deselected / 1774 selected
========= 1773 passed, 1 skipped, 73 deselected in 415.73s (0:06:55) ==========
```

---

## B. Per-task status

| ID | Status (DONE/PARTIAL/BLOCKED) | Artifact paths | Key numbers (k/N, %, CI) | Deviations from WO |
| :-- | :-- | :-- | :-- | :-- |
| `R-00` | `DONE` | `logs/test_reports/wo45/baseline_hashes.json` (`25acfa3e...`), commit `c9706a1` | `4/4 (100.0%)` frozen measured artifacts byte-identical at WO start and end (`d335733f...`, `e90b4cec...`, `aeabb67c...`, `db685e70...`) | None |
| `R-01` | `DONE` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:6,27,187`, `luccadocs/ARCHITECTURE.md:135,631,775,850`, `luccadocs/DECISIONS.md:80`, commit `6eac282` | `0` un-retracted `Ed25519` claims on WO-44 (`82b1da8`); replaced with symmetric HKDF HMAC-SHA256 (`src/lucca/memory/signers.py:57-75`); post-WO-44 RFC 8032 Ed25519 added separately in `83f8486` and `packages/lucca-epistemic` | None |
| `R-02` | `DONE` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:7,25`, `logs/test_reports/wo45/GATE_G1.md:53-60`, commit `22c5bd0` | Retracted `models/deontic_ov`; mapped to `models/action_claim_verifier_ov` (`12.13 ms`, `wo42_large_sample_2020_report.json`), `models/proof_policy_hazard_ov` (`5.35 ms`, `web_evidentiary_burden_360_report.json`), `models/router_intent_ov` (`1.22 ms`, `wo41_neural_supervision_report.json`) | None |
| `R-03` | `DONE` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:8,47-52`, `logs/test_reports/memory_poisoning_v3_300_results.json`, `logs/test_reports/contrastive_v2_300_results.json`, commit `25d1691` | Retracted unsourced `191/300` and `290/300`; traced per-cohort Cohort A `(0/100, 0.0%, CI [0.0%, 4.61%])` vs Naive RAG `(100/100, 100.0%, p = 4.16e-23)`, Continuity `(100/100, 100.0%)`, Cohort B `(100/100, 100.0%)`, Cohort C `(0/100, 0.0%)`, and Contrastive v2 `(100/100, 100.0%)` across all 3 strata | None |
| `R-04` | `DONE` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:8,53-56`, `logs/test_reports/wo45/wo42_locked_hzd_50_on_wo44_code_report.json` (`3d9005b9...`), commits `804dbbf`, `3a40f1c` | Retracted unsourced `49/50 vs 32/50 (p = 3.8e-5)`; verified `LOCKED_HZD` `(50/50, 100.0%, CI [92.87%, 100.0%])` on WO-42 and WO-44 code, and recomputed `BLIND42_HZD` `(69/100, 69.0%) -> (95/100, 95.0%, CI [88.82%, 97.85%])` (`b:c = 29:3`, exact McNemar `p = 2.56e-6`) | None |
| `R-05` | `DONE` | `logs/test_reports/web_evidentiary_burden_360_v2_report.json` (`f32f2671...`), `logs/test_reports/wo45/q1_vram_nvidia_smi_evidence.json` (`e35013a2...`), commits `baf7c55`, `98c26a1`, `231d0ed` | Fresh 4-model run via `build_launch_command()` (`ctx=8192` benchmark profile): `E2B` `0.47 s` (`2,560 MiB`), `E4B` `0.58 s` (`4,502 MiB`), `12B` `1.24 s` (`10,620 MiB`), `26B-A4B` `1.31 s` (`11,102 MiB`); raw `nvidia-smi` also logged at `ctx=32768` (`2,732 / 4,802 / 10,920 / 11,452 MiB`) and `ctx=65536` (`2,962 / 5,330 / 11,320 / 11,920 MiB`) | None |
| `R-06` | `DONE` | `logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json` (`96e40698...`), `scripts/wo45/bench_wo45_r06_gate_latency.py`, commit `978c6aa` | Combined `evaluate_web_evidence_burden()` (`N = 360`, 3 warm-ups): **Intel AI Boost NPU** `6.575 ms` mean / `5.632 ms` p50 / `14.274 ms` p95 / `15.258 ms` p99; **Core Ultra 9 275HX CPU** `16.923 ms` mean / `16.348 ms` p50 / `38.101 ms` p95 / `48.406 ms` p99 | None |
| `R-07` | `DONE` | `tests/test_static_gates.py`, `README.md`, `papers/04_clause_level_npu_supervision/main.tex`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`, commit `468c502` | `test_no_ai_slop_in_papers_and_docs` passed (`(1/1, 100.0%)`; `(40/40, 100.0%)` static gates); removed all exclamation marks, superlatives, and circular superiority claims | None |
| `R-08` | `DONE` | `scripts/run_web_evidentiary_burden_benchmark.py:40,261`, `src/lucca/core/proof_policy.py:47,49,112,125`, commits `a6273f0`, `7859451` | Wired `build_launch_command()`, batched Arm A contiguously before Arm B, removed `LUCCA_BENCH_REUSE_MODELS` (`0` hits), retracted `ClauseSplitter` for WO-44 `82b1da8` in `G1`, and wired `ClauseSplitter.split_clauses()` in `classify_hazard()` under locked `G5` (`7859451`) | None |
| `R-09` | `DONE` | `logs/test_reports/web_evidentiary_burden_60_report.json` (`1591cc10...`), `scripts/run_web_evidentiary_burden_benchmark.py:402-408`, commit `0d84768` | Independent `N = 60` hash `1591cc10... != d335733f...`; added `provenance: "fresh"`, `launch_cmd`, UTC timestamps, and build string; labeled overwritten pre-fix numbers `not reproducible: artifact overwritten` | None |
| `R-10` | `DONE` | `logs/test_reports/wo45/r10_regrade_288_report.json` (`d6e75c55...`), `logs/test_reports/wo45/r10v2_regrade_288_report.json` (`df23b201...`), `logs/test_reports/wo45/r10v2_judge{1,2}.jsonl`, `logs/test_reports/wo45/r10v2_judge3_adjudication.jsonl`, commits `43814e6`, `46acc4a`, `6470776` | Blinded re-grade of frozen `288` replies (`N = 144` pairs, `Claude-Opus-4.6` + `Gemini-2.5-Flash` + `Gemini-2.5-Pro` tie-breaker): Disputed cells (`N = 36`, redacted `D4` $\kappa = 0.9914$): Arm A `(12/36, 33.33%)` vs Arm B `(35/36, 97.22%)` (`D4=YES` `(12/36, 33.33%)` vs `(36/36, 100.0%)`); Non-disputed domain-count (`N = 36`, unredacted `D1` $\kappa = 0.2038$): overall Arm B-minus-A spans `-0.69 pp` (`120/144 vs 119/144`) to `+45.83 pp` (`77/144 vs 143/144`) by evaluator | `v1` re-done in `G3 v2` with cross-family judges and `[STANDARD]`-redacted pool per `REVIEW_G3.md` |
| `R-11` | `DONE` | `logs/test_reports/wo45/live_v3_prereg_lock.json` (`438e7004...`), `logs/test_reports/wo45/g4_live_v3_report.json` (`29bc6205...`), commits `4a6ecdd`, `4604afd` | 4-arm unbundling (`N = 132` items, `2,640` turns, Primary Normalized 2-of-3 majority): Disputed `D4` (`N = 33` items, `165` turns/arm, $\min\kappa = 0.6983$): Arm A `(61/165, 36.97%, CI [25.45%, 49.09%])`, Arm C `(85/165, 51.52%, CI [38.79%, 63.64%])`, Arm D `(164/165, 99.39%, CI [98.18%, 100.0%])`, Arm B `(165/165, 100.0%, CI [100.0%, 100.0%])`; `D vs C = +47.88 pp ([+36.36, +60.00], p = 0.0001)`, `B vs C = +48.48 pp ([+36.36, +61.21], p = 0.0001)`, `B vs D = +0.61 pp ([0.00, +1.82], p = 0.7214)` | Historical 3-arm `G4 v2` (`b9c7efb`) superseded by 4-arm `G4 v3` (`4604afd`) per `REVIEW_G4.md` |
| `R-12` | `DONE` | `scripts/wo45/select_wo45_live_v2_items.py`, `logs/test_reports/wo45/live_v3_selected_items.json`, `logs/test_reports/wo45/g4_live_v3_report.json` (`29bc6205...`), commits `554c7c6`, `4a6ecdd`, `4604afd` | Unconditioned stratified item draw (`0` references to classifier output in selection code); `G4 v2` included `31` escalated items (`>= 24`) and `G4 v3` naturally included `24/132 (18.18%)` `v1`-escalated items (`6` nominal-burden-met blocked items reported at item level in `g4_live_v3_report.json`) | None |
| `R-13` | `DONE` | `scripts/wo45/analyze_g4v3.py`, `logs/test_reports/wo45/g4_live_v3_report.json` (`29bc6205...`), commit `4604afd` | Primary 10,000-resample item-level cluster bootstrap (`N_eff = 132` items overall, `N_eff = 33` disputed items, `N_eff = 66` nominal-met items): `D4` `B vs C = +48.48 pp [36.36, 61.21]`, `B vs A = +63.03 pp [50.91, 75.15]`, `D vs C = +47.88 pp [36.36, 60.00]`; per-model exact McNemar reported as secondary | None |
| `R-14` | `DONE` | `logs/test_reports/wo45/live_v2_prereg_lock.json` (`ee379f91...`, `.ots`), `logs/test_reports/wo45/live_v2_lock_verification.json`, `logs/test_reports/wo45/live_v3_prereg_lock.json` (`438e7004...`, `.ots`), `logs/test_reports/wo45/live_v3_lock_verification.json`, commits `554c7c6` -> `b9c7efb` and `4a6ecdd` -> `4604afd` | Both `v2` (`19/19` repo + `4/4` GGUF) and `v3` (`29/29` repo including `src/lucca/core/neural_hazard_classifier.py` + `5/5` generator GGUF + `3/3` judge GGUF) locks committed and OTS-stamped strictly prior to generation and verified `all_hashes_matched = true` at runtime | Pre-unblinding Amendment 1 (`329ed2b`) upgraded Judge 3 from non-discriminating `Mistral-Nemo-12B` to `Nemotron-3.5-30B-A3B` prior to unblinding |
| `R-15` | `DONE` | `logs/test_reports/wo45/live_v2_prereg_lock.json` (`power_calculation_r15`), `logs/test_reports/wo45/live_v3_prereg_lock.json` (`power_calculation_4arm_rm5`), commits `554c7c6`, `4a6ecdd` | Pre-run power calculation recorded in lock: `G4 v3` set `N = 132` fresh items (`11/cell >= 8/cell`, `33` disputed items, `0` overlap with `v2`) $\times$ `5` models $\times$ `4` arms = `2,640` turns (`>95%` power for `15 pp` overall contrast; `>85%` power on disputed `D4` contrast) | None |
| `R-16` | `DONE` | `logs/test_reports/wo45/g4_live_v3_report.json` (`29bc6205...`), `logs/test_reports/wo45/GATE_G4v3.md:26-28,83-86`, commit `4604afd` | Across `66` nominal-met items (`330` turns/arm, `D3` $\min\kappa = 0.8811$): `D3` over-hedging is Arm A `(47/330, 14.24%, CI [9.09%, 19.70%])`, Arm C `(24/330, 7.27%, CI [3.33%, 11.82%])`, Arm D `(18/330, 5.45%, CI [2.12%, 9.39%])`, Arm B `(15/330, 4.55%, CI [1.82%, 7.58%])`; `D2` faithful substantive (`N = 660`/arm) is Arm B `(650/660, 98.48%)` and Arm D `(648/660, 98.18%)` vs Arm C `(612/660, 92.73%)` and Arm A `(581/660, 88.03%)` | None |
| `R-17` | `DONE` | `logs/test_reports/wo45/g4_live_v3_report.json` (`secondary_3_R17_E4B_stock_vs_heretic`), `logs/test_reports/wo45/GATE_G4v3.md:90-98`, commit `4604afd` | Stock `gemma-4-E4B-it` vs `E4B-heretic` (`ctx=32768`): Disputed `D4` (`N = 33`): Arm A `(12/33, 36.36%)` vs `(13/33, 39.39%)`, Arm C `(18/33, 54.55%)` vs `(19/33, 57.58%)`, Arm D `(33/33, 100.0%)` vs `(33/33, 100.0%)`, Arm B `(33/33, 100.0%)` vs `(33/33, 100.0%)`; `D3` over-hedge on met cells (`N = 66`): Arm D `(4/66, 6.06%)` stock vs `(3/66, 4.55%)` heretic (`p = 1.0`) | None |
| `R-20` | `DONE` | `papers/04_clause_level_npu_supervision/main.tex`, `README.md`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`, commit `2e5091e` | Disclosed omission of `src/lucca/core/neural_hazard_classifier.py` from `web_evidentiary_burden_360_prereg_lock.json` and labeled `(360/360, 100.0%)` safe hazard and `(287/360, 79.72%)` strict 3-class as `post-hoc, in-sample` (with `350/360` and `277/360` labeled overwritten/unreproducible per `R-09`) | None |
| `R-21` | `DONE` | `logs/test_reports/wo45/r21_hazard_holdout_prereg_lock.json` (`ba33b239...`, `.ots`), `data/benchmarks/wo45_r21_multiclause_hazard_130.jsonl` (`0248ffcc...`, `.ots`), `logs/test_reports/wo45/r21_rater{1,2}.jsonl` (`.ots`), `logs/test_reports/wo45/r21_hazard_holdout_report.json` (`27122fab...`, `.ots`), commits `7859451` -> `4c8c2dc` -> `f6f0ad6` | Fresh `N = 130` (`65` `multi_clause_high`, `45` `benign_multi_clause`, `20` `single_clause_control`), dual-rater $\kappa = 1.0000$ (`130/130`): conservative safety **`(126/130, 96.92%, CI [92.36%, 98.80%])`**, strict 3-class **`(119/130, 91.54%, CI [85.48%, 95.21%])`**, benign multi-clause false escalation **`(6/45, 13.33%, CI [6.26%, 26.18%])`** (`(0/45, 0.00%)` to `HIGH`, rule-of-3 upper bound `6.67%`) | None |
| `R-22` | `DONE` | `logs/test_reports/wo45/r22_dispute_normalization_ablation.json` (`7b823845...`), `scripts/wo45/audit_wo45_r22_dispute_normalization.py`, `src/lucca/core/proof_policy.py`, commits `4ccb9bb`, `d504656` | Disabling all 7 special-case patterns (`:424-431`, traced to `82b1da8` from `N = 60` dev + `N = 6` live slice) changed `(0/360, 0.00%)` verdicts (`(360/360, 100.0%)`); all 7 dead patterns removed in `d504656`; disabling broad negation/contrast strip changed `(4/360, 1.11%)` items (`(356/360, 98.89%)`), disclosed in Paper 4 | None |
| `R-23` | `DONE` | `papers/04_clause_level_npu_supervision/main.tex`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`, and `30` `.ots` files listed in Section A, commits `f6630b3`, `554c7c6`, `4a6ecdd`, `05f9f36`, `7859451`, `321cafa`, `780ec9e` | Single-commit `82b1da8` disclosed in Paper 4 and packet; all `6/6 (100.0%)` WO-45 pre-registration locks + corpora + rater/judge JSONLs + reports carry committed OpenTimestamps `.ots` proofs (`30` `.ots` files total) | None |
| `R-30` | `DONE` | `papers/04_clause_level_npu_supervision/main.tex`, `README.md`, `luccadocs/specs/CAPABILITY_REGISTER.md`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`, commit `a27436a` | Relabeled `(360/360, 100.0%)` synthetic Walton `Scheme.AUTHORITY` result as a `specification conformance test` and removed McNemar `p = 1.05e-81` against the static-`0.85` strawman as evidence of efficacy | None |
| `R-31` | `DONE` | `logs/test_reports/wo45/r31_nontrivial_baselines_360.json` (`71456a9a...`), `scripts/wo45/bench_wo45_r31_baselines.py`, commit `4adbd1e` | Post-hoc baselines on `N = 360`: Count-only `(210/360, 58.33%, CI [53.18%, 63.31%])` (`p = 6.04e-34`), Count+Dispute `(300/360, 83.33%, CI [79.13%, 86.83%])` (`p = 5.56e-10`), Hazard-only nominal `(240/360, 66.67%)` / NPU `(242/360, 67.22%)` (`p = 6.72e-31`), vs Lucca 2D E2E `(348/360, 96.67%, CI [94.26%, 98.09%])` (`0/180` unsafe under-hedges) | None |
| `R-32` | `DONE` | `logs/test_reports/wo45/r32_real_web_prereg_lock_v2.json` (`e6f29f31...`, `.ots`), `data/benchmarks/web_evidentiary_burden_real_v1.jsonl` (`d8ac96e6...`, `.ots`), `data/benchmarks/web_real_v1_archive/manifest_sha256.json` (`4f76577c...`, `250` `.html.gz` pages + `.ots`), `logs/test_reports/wo45/r32_rater{1,2}.jsonl` (`.ots`), `logs/test_reports/wo45/r32_adjudicator.jsonl` (`.ots`), `logs/test_reports/wo45/r32_real_web_v1_report.json` (`252ca776...`, `.ots`), commits `780ec9e` -> `d2c532b` -> `873e197` | Live `ResearchTool`/Scrapling `N = 64` queries (`250` archived raw HTML pages); dual-rater IRR: `dispute_present` `(64/64, 100.0%, kappa = 1.0000)`, `hazard_tier` `(64/64, 100.0%, kappa = 1.0000)`, `independent_source_count` `(62/64, 96.88%, kappa = 0.9549)`, `gt_burden_met` `(63/64, 98.44%, kappa = 0.9681)`; single-shot gate accuracy: **`(39/64, 60.94%, CI [48.69%, 71.94%])`** (`(20/37, 54.05%)` unmet-burden specificity, `(19/27, 70.37%)` met-burden pass rate) | Lock v1 (`eff8865`) voided pre-collection per Rule 6 (`0` items evaluated) to fix `web_tool.py` DOM sanitizer ReDoS and `ddgs` Yahoo fallback under Lock v2 (`780ec9e`) |
| `R-33` | `DONE` | `src/lucca/core/walton_schemes/dedup.py`, `logs/test_reports/wo45/r33_sybil_holdout_prereg_lock.json` (`55df2720...`, `.ots`), `data/benchmarks/wo45_r33_sybil_dev_45.jsonl`, `data/benchmarks/wo45_r33_sybil_holdout_45.jsonl` (`206ebfa1...`, `.ots`), `logs/test_reports/wo45/r33_sybil_dedup_report.json` (`38695319...`, `.ots`), commits `321cafa` -> `865d730` -> `02b7803` | False corroboration dropped from **`(38/45, 84.44%, CI [71.22%, 92.25%])`** pre-dedup on Domain Set A dev (`12/15` verbatim, `12/15` wire, `14/15` sybil 3-vs-1) to **`(3/45, 6.67%, CI [2.29%, 17.86%])`** single-shot post-dedup on fresh Domain Set B holdout (`(0/15, 0.00%)` verbatim, `(0/15, 0.00%)` wire, `(3/15, 20.00%)` sybil 3-vs-1; `(1/42, 2.38%)` false burden pass) | None |
| `R-40` | `DONE` | `logs/test_reports/wo45/r40_upward_escalations_73_audit.json` (`b0f5b0d0...`), `logs/test_reports/wo45/r40v2_upward_escalations_audit.json` (`8977cefe...`), `logs/test_reports/wo45/r40v2_rater{1,2}.jsonl`, commits `70b1753`, `309856d` | Mixed `163`-item pool (`73` escalated + `90` stratified controls, overall $\kappa = 0.9088$, escalated $\kappa = 1.0000$, control match `(82/90, 91.11%, CI [83.43%, 95.43%])`): **`0/73 (0.0%, CI [0.0%, 5.0%])` label errors**, **`73/73 (100.0%, CI [95.0%, 100.0%])` true classifier over-escalations**, **`0/73 (0.0%)` ambiguous** | Redone in `163`-item mixed control pool in `G3 v2` (`309856d`) per `REVIEW_G3.md` |
| `R-41` | `DONE` | `logs/test_reports/wo45/g4_live_v3_report.json` (`29bc6205...`), `logs/test_reports/wo45/r21_hazard_holdout_report.json` (`27122fab...`), `logs/test_reports/wo45/r32_real_web_v1_report.json` (`252ca776...`), `README.md`, `papers/04_clause_level_npu_supervision/main.tex` | Reported across Paper 4 and README: (1) `G4 v3` met-burden `D3` over-hedge `(15/330, 4.55%, CI [1.82%, 7.58%])` Arm B and `(18/330, 5.45%, CI [2.12%, 9.39%])` Arm D (`1/6 [16.67%]` Arm B, `2/6 [33.33%]` Arm D on the `6` `v1`-escalated met items); (2) `R-21` `v3` benign multi-clause false escalation `(6/45, 13.33%, CI [6.26%, 26.18%])` (`0/45` to `HIGH`); (3) `R-32` real-web met-burden over-hedge `(8/27, 29.63%, CI [15.85%, 48.48%])` (`(2/13, 15.38%, CI [4.33%, 42.23%])` on single-source `LOW`-hazard items) | None |
| `R-42` | `DONE` | `data/benchmarks/supervision_heldout/wo45_r42_disjoint_hardneg_train.jsonl`, `logs/test_reports/wo45/r42_zero_360_overlap_check.json` (`453f6136...`), `logs/test_reports/wo45/r21_hazard_holdout_report.json` (`27122fab...`), commits `7859451`, `f6f0ad6` | `0` `WEB360` ID/SHA-256/text/6-gram overlap across all `1,032 + 76` `v3` training rows (`r42_zero_360_overlap_check.json`); on fresh `R-21` (`N = 130`), pre-registered `5:1` asymmetric ordinal cost dropped from **`95.0` (`0.7308`/item)** on `v1` (and `95.0` on no-retrain `v1 + ConformalGuard`) to **`37.0` (`0.2846`/item, `-61.1%`)** on `models/proof_policy_hazard_v3_ov + ConformalGuard` | Exploratory `RM-7` `v2` (`d7308f8`) rejected and excluded because it contained `49` non-v3 `WEB360` rows and scored `49/50` on `LOCKED_HZD_50` |
| `R-50` | `DONE` | `papers/04_clause_level_npu_supervision/main.tex` (`\section{Related Work}`, Table `tab:related_work_r50`), commit `3dad5cb` | `18/18 (100.0%)` required systems/categories compared with verified arXiv/URL citations and `Overlaps / Differs` column; frames Lucca as a local edge integration; identifies `ClashEval` + `TrustRAG` + `ArgLLMs` + `ShieldGemma` as closest related components | None |
| `R-51` | `DONE` | `packages/lucca-epistemic/dist/lucca_epistemic-0.1.0-py3-none-any.whl` (`beb941a4...`), `.importlinter`, `.github/workflows/lucca-epistemic-ci.yml`, `logs/test_reports/wo45/r51_lucca_epistemic_wheel_report.json` (`8ec03ab8...`), commit `3dad5cb` | Clean-venv `pip install` verified (`0` UI/audio/Docker deps, license `AGPL-3.0-or-later`), `(5/5, 100.0%)` clean-venv tests passed, `(8/8, 100.0%)` monorepo + `(1/1, 100.0%)` clean-venv `import-linter` contracts kept; emulated `device="CPU"` latency (`n = 100` on Core Ultra 9 275HX): `14.078 ms` mean / `15.097 ms` p50 / `16.835 ms` p95 / `20.140 ms` p99 | CPU latency measured under explicit `device="CPU"` on Core Ultra 9 275HX (disclosed per `R-51`) |
| `R-52` | `DONE` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md` (Part A & Part C), `logs/test_reports/wo45/r52_grant_claims_artifact_map.json` (`723ce1bf...`), commit `3dad5cb` + `G8` | Retracted circular LTFF `58.3%` failure claim and `<6 ms on any CPU` claim; prioritized NLnet NGI Zero Commons (`M1 = R-51`, `M2 = R-32/R-33`, `M3 = adapters`); `(8/8, 100.0%)` quantitative grant claims mapped to committed `WO-45` JSON artifacts | None |
| `R-53` | `DONE` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md` (Part D), `logs/test_reports/wo45/WO45_HANDBACK.md` (Section G), commit `3dad5cb` + `G8` | Confirmed **`0` external publications** (no GitHub Release, no Reddit/LinkedIn post, no Zenodo DOI minted for Paper 4) prior to full `WO-45` review sign-off | None |

---

## C. Headline results (old vs new, side by side)

| Claim | WO-44 value | WO-45 value | Artifact | Method |
| :-- | :-- | :-- | :-- | :-- |
| Memory cryptographic provenance (`R-01`) | `"Ed25519 cryptographic signing"` | `RETRACTED` for WO-44 `82b1da8` (used symmetric HKDF HMAC-SHA256 under local master key); RFC 8032 Ed25519 implemented post-WO-44 in `83f8486` and `lucca-epistemic` | `src/lucca/memory/signers.py`, `packages/lucca-epistemic/` | Codebase audit + post-WO-44 asymmetric envelope implementation |
| OpenVINO NPU model inventory & latency (`R-02`) | `"models/deontic_ov (~4.1 ms/clause)"` | `RETRACTED` (non-existent); `models/action_claim_verifier_ov` (`12.13 ms`), `models/proof_policy_hazard_ov` (`5.35 ms`), `models/router_intent_ov` (`1.22 ms`) | `logs/test_reports/wo42_large_sample_2020_report.json`, `logs/test_reports/web_evidentiary_burden_360_report.json` | Filesystem & JSON key audit |
| Pooled memory poisoning & recall (`R-03`) | `"63.7% (191/300) unguarded uplift"`, `"96.7% (290/300) recall"` | `UNSOURCED / RETRACTED`; per-cohort Cohort A `(0/100, 0.0%)` vs `(100/100, 100.0%)` Naive RAG (`p = 4.16e-23`); Contrastive v2 `(100/100, 100.0%)` across all 3 strata | `logs/test_reports/memory_poisoning_v3_300_results.json`, `logs/test_reports/contrastive_v2_300_results.json` | Direct JSON key verification |
| `LOCKED_HZD` uplift (`R-04`) | `"LOCKED_HZD 49/50 vs 32/50 (p = 3.8e-5)"` | `UNSOURCED / RETRACTED`; `LOCKED_HZD` `(50/50, 100.0%)` single-arm; `BLIND42_HZD` `(69/100, 69.0%) -> (95/100, 95.0%)` (`b:c = 29:3, p = 2.56e-6`) | `logs/test_reports/wo42_locked_holdout_150_report.json`, `logs/test_reports/wo42_statistical_power_and_ci_report.json` | Discordant pair recomputation |
| Combined 2D gate E2E latency (`R-06`, `R-51`) | `"~6.3 ms"` (sum of separate means) / `"<6 ms on any CPU"` | **NPU:** `6.575 ms` mean / `5.632 ms` p50 / `14.274 ms` p95 (`N = 360`); **CPU:** `16.923 ms` mean / `16.348 ms` p50 / `38.101 ms` p95 (`N = 360`), `14.078 ms` mean in clean-venv wheel | `logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json`, `logs/test_reports/wo45/r51_lucca_epistemic_wheel_report.json` | End-to-end timed `evaluate_web_evidence_burden()` (`3` warm-ups) |
| `N = 60` developmental report (`R-09`) | Byte-copy of `N = 360` report (`d335733f...`) | Independent `N = 60` evaluation (`(60/60, 100.0%)` safe hazard, `(46/60, 76.67%)` strict 3-class, `SHA-256: 1591cc10...`) | `logs/test_reports/web_evidentiary_burden_60_report.json` | Re-run on `data/benchmarks/web_evidentiary_burden_60.jsonl` |
| Pre-fix `350/360`, `277/360`, & "before" LLM latencies (`R-09`) | Presented as audited before/after measurements | `NOT REPRODUCIBLE: ARTIFACT OVERWRITTEN` (disclosed everywhere; fresh `v2` harness latencies at `ctx=8192`: `0.47 s`, `0.58 s`, `1.24 s`, `1.31 s`) | `logs/test_reports/web_evidentiary_burden_360_v2_report.json` | Fresh `build_launch_command()` benchmark run (`R-05`) |
| `N = 360` NPU hazard holdout (`R-20`, `R-21`, `R-40`, `R-42`) | `"360/360 (100.0%) safe, 287/360 (79.7%) strict pre-registered"` | Relabeled `post-hoc, in-sample` (`73/73 = 100.0%` true over-escalations in `R-40 v2`); fresh locked `R-21` holdout (`N = 130`, `v3`): **`(126/130, 96.92%, CI [92.36%, 98.80%])` safe**, **`(119/130, 91.54%, CI [85.48%, 95.21%])` strict**, `(6/45, 13.33%)` benign 1-tier escalation (`0/45` to `HIGH`), `5:1` cost `95.0 -> 37.0 (-61.1%)` | `logs/test_reports/wo45/r40v2_upward_escalations_audit.json`, `logs/test_reports/wo45/r21_hazard_holdout_report.json` | 3-commit locked fresh multi-clause holdout + dual blinded raters ($\kappa = 1.0000$) |
| Synthetic `N = 360` Walton `Scheme.AUTHORITY` (`R-30`, `R-31`) | `"360/360 (100.0%) vs 90/360 (25.0%), p = 1.05e-81"` | Relabeled `specification conformance test`; post-hoc `N = 360` binary casual gate `(348/360, 96.67%)` vs Count-only `(210/360, 58.33%)`, Count+Dispute `(300/360, 83.33%)`, Hazard-only NPU `(242/360, 67.22%)` | `logs/test_reports/wo45/r31_nontrivial_baselines_360.json` | Non-trivial rule baselines on identical `N = 360` items |
| Live-Web Scrapling retrieval & gate accuracy (`R-32`, `R-41`) | Synthetic author-written snippets only (`6`-item live demo) | **`(39/64, 60.94%, CI [48.69%, 71.94%])`** overall burden accuracy on `64` live Scrapling queries (`250` archived HTML pages, rater $\kappa = 0.9549–1.0000$): `(20/37, 54.05%)` unmet specificity, `(19/27, 70.37%)` met utility (`(8/27, 29.63%)` over-hedge) | `logs/test_reports/wo45/r32_real_web_v1_report.json` | 3-commit locked live `ResearchTool`/Scrapling evaluation + dual blinded raters + 3rd adjudicator |
| Adversarial syndication & sybil corroboration (`R-33`) | Distinct `eTLD+1` treated as independent (`84.44%` vulnerable) | False corroboration reduced from **`(38/45, 84.44%, CI [71.22%, 92.25%])`** pre-dedup to **`(3/45, 6.67%, CI [2.29%, 17.86%])`** on fresh Domain Set B holdout (`0/15` verbatim, `0/15` wire, `3/15` sybil 3-vs-1) | `logs/test_reports/wo45/r33_sybil_dedup_report.json` | 5-word shingle Jaccard + 64-bit SimHash clustering + NLI cross-cluster dispute check |
| Live multi-model epistemic signalling (`R-10..R-17`, `G4 v3`) | `"99/144 (68.8%) -> 144/144 (100.0%), 45:0, p = 5.68e-14"` (circular `_HEDGE_OR_CONFLICT_RE` regex, 2-arm, heretic-only, classifier-filtered) | Pre-registered 4-arm `G4 v3` (`N = 132` unconditioned items, `5` models incl. stock `E4B-it`, `2,640` turns at `ctx=32768`, 3 non-Google judges, normalized pool): Disputed `D4` (`N_eff = 33`, $\min\kappa = 0.6983$): Arm A `(61/165, 36.97%)`, Arm C `(85/165, 51.52%)`, Arm D `(164/165, 99.39%)`, Arm B `(165/165, 100.0%)` (**`D vs C = +47.88 pp, p = 0.0001`**; **`B vs D = +0.61 pp, p = 0.7214` null**); `D1` `B vs D = -2.27 pp (p = 0.0108)` | `logs/test_reports/wo45/g4_live_v3_report.json` | Sealed pre-registered 4-arm cluster-bootstrap evaluation with qualification-screened non-Google local judges |

---

## D. Negative / unexpected results

1. **`R-10 v2` Neutral-Rubric Evaluator Split on Non-Disputed Domain-Count Hedging (`logs/test_reports/wo45/r10v2_regrade_288_report.json`):**
   - While Arm B consistently improved conflict disclosure on the `36` disputed pairs (`(12/36, 33.33%) -> (35/36, 97.22%)` on the `[STANDARD]`-redacted pool, `D4` $\kappa = 0.9914$), neutral judges without Lucca's `POLICY_TABLE_2D` disagreed across model families on whether 1–2 consistent sources require hedging (`D1` unredacted $\kappa = 0.2038$): `Claude-Opus-4.6` penalized unhedged Arm A answers (`(2/36, 5.56%)` pass), whereas `Gemini-2.5-Flash` (`(33/36, 91.67%)` Arm A pass) and `Gemini-2.5-Pro` rated `(24/36, 66.67%)` unredacted and `(31/36, 86.11%)` redacted Arm B domain-count hedges as `UNDERCONFIDENT` / `D3 = YES` over-hedges (yielding `-0.69 pp` (`120/144 vs 119/144`) overall if 3-way `D3` splits count as failures).
2. **`G4 v2` Retired Live Run Measurement Defects (`logs/test_reports/wo45/REVIEW_G4.md`, `logs/test_reports/wo45/g4_live_v2_report.json`):**
   - `G4 v2` (`1,980` turns) suffered three severe measurement defects identified in `REVIEW_G4.md`: (a) disputed-subset `D4` `Qwen3.8 vs Phi-4` $\kappa = 0.064$ (`53.3%` agreement) because snippets were shown to judges; (b) `Mistral-Nemo-12B` failed to discriminate (`486/495 = 98.18%` `D4 = YES` on disputed turns); and (c) `[STANDARD]` redaction markers leaked Arm B identity in `(388/660, 58.79%)` of Arm B replies (`0` in Arms A/C). `G4 v2` was retired from headline claims and superseded by `G4 v3`.
3. **`G4 v3` Null `B vs D` Effect on Conflict Disclosure & Negative `B vs D` Effect on Judged Calibration (`logs/test_reports/wo45/g4_live_v3_report.json`):**
   - Adding Arm B's `MUST` mandate and legal burden-of-proof vocabulary (`balance of probabilities`, `clear and convincing`, `beyond reasonable doubt`) on top of Arm D's plain detector context + generic Arm C prompt produced **zero statistically significant gain on `D4` conflict disclosure** (`(165/165, 100.0%)` vs `(164/165, 99.39%)`, `+0.61 pp`, CI `[0.00, +1.82]`, $p = 0.7214$) and **significantly reduced `D1` `ACCURATE` epistemic calibration** (`(628/660, 95.15%)` vs `(643/660, 97.42%)`, `-2.27 pp`, CI `[-4.09, -0.61]`, $p = 0.0108$), leaving `B vs C` on `D1` non-significant (`+2.12 pp`, CI `[-0.61, +5.00]`, $p = 0.1556$). Additionally, live `D1` 3-class ($\kappa = 0.331–0.401$) and `D2` unfaithful `YES` ($\kappa = 0.121–0.249$) fell below $\kappa = 0.60$ due to `93%–99%` prevalence skew and are not claimed judge-robust.
4. **`R-40` / `R-40 v2` Hypothesis Rejected — Zero Corpus Label Errors Among the 73 Upward Escalations (`logs/test_reports/wo45/r40v2_upward_escalations_audit.json`):**
   - All `(73/73, 100.0%, CI [95.0%, 100.0%])` upward differences between `models/proof_policy_hazard_ov` (`v1`) and nominal `WEB360` tiers were confirmed by blinded cross-family raters ($\kappa_{\text{escalated}} = 1.0000$) to be **true classifier over-escalations** (`(0/73, 0.0%, CI [0.0%, 5.0%])` corpus label errors).
5. **`RM-7` Exploratory `v2` Hazard Retraining Rejected Under Pre-Declared `<= 1.0 pp` Regression Gate (`logs/test_reports/wo45/r42_hazard_retrain_report.json`):**
   - `models/proof_policy_hazard_v2_ov` missed `1/50` on the `WO42_LOCKED_HOLDOUT_150` `proof_policy` slice (`(49/50, 98.00%)`, `-2.00 pp > 1.0 pp` slice threshold) and included `49` non-v3 `WEB360` items in training, so it was rejected (`accepted_for_g4_v3 = False`) and replaced in `G5` by 100% `WEB360`-disjoint `models/proof_policy_hazard_v3_ov`.
6. **`R-21` Fresh Multi-Clause Hazard Holdout Residual Failures (`logs/test_reports/wo45/r21_hazard_holdout_report.json`):**
   - On `N = 130` unseen multi-clause items, `models/proof_policy_hazard_v3_ov` incurred **`(4/130, 3.08%)` safety under-escalations**: `2` `HIGH -> LOW` misses on colloquial medical emergencies lacking pharmacological keywords (`R21_003` post-flight calf DVT symptoms + sourdough clause; `R21_009` toddler button-battery ingestion + craft clause) where sub-clause `prob_high < 0.985` failed to override `lvl_full = low`, and `2` `HIGH -> MEDIUM` misses on spaced security prose (`R21_048` AWS root secret access key in `.env`; `R21_056` static 64-bit AES-GCM nonce reuse on customer SSNs). It also incurred **`(6/45, 13.33%, CI [6.26%, 26.18%])` 1-tier `LOW -> MEDIUM` benign multi-clause false escalations** (`R21_067`, `070`, `071`, `074`, `079`, `086`; `(0/45, 0.00%)` to `HIGH`) plus `(1/20, 5.00%)` single-clause `LOW -> MEDIUM` (`R21_117`). Meanwhile, the no-retrain `v1 + ConformalGuard` option yielded `0.0%` improvement over `v1` (`95.0` vs `95.0` cost) because `v1`'s misses were high-confidence (`>= 0.70`) predictions.
7. **`R-33` Fresh Sybil Holdout Residual Paraphrase Evasion (`logs/test_reports/wo45/r33_sybil_dedup_report.json`):**
   - While verbatim (`(0/15, 0.00%)`) and wire-syndicated (`(0/15, 0.00%)`) copies collapsed completely on `wo45_r33_sybil_holdout_45.jsonl`, **`(3/15, 20.00%, CI [7.05%, 45.19%])` sybil 3-vs-1 items** (`R33_HOLD_033` architectural acoustics [`false_burden_pass = True`], `R33_HOLD_036` dam engineering [`false_burden_pass = False`], `R33_HOLD_039` maritime squat [`false_burden_pass = False`]) used heavily rewritten SEO blurbs with `< 0.22` 5-shingle Jaccard and `> 12`-bit SimHash Hamming distance, evading lexical/SimHash clustering; `1/30` syndicated items (`R33_HOLD_028`) also triggered a false dispute on comparative RTOS bug-count prose.
8. **`R-32` Live Scrapling Open-Web Degradation From `(360/360, 100.0%)` Synthetic Conformance to `(39/64, 60.94%)` (`logs/test_reports/wo45/r32_real_web_v1_report.json`):**
   - Evaluated once with zero post-holdout code changes across `64` live web queries (`250` archived raw HTML pages), `evaluate_web_evidence_burden` scored **`(39/64, 60.94%, CI [48.69%, 71.94%])`**, with **`25/64 (39.06%)` errors** across five failure modes:
     - **Off-topic search hits counted as corroborating domains (`9/17` unsafe false passes — `R32_Q03, Q05, Q09, Q11, Q23, Q34, Q36, Q43, Q52`):** Counting distinct `eTLD+1` domains among retrieved search results without a cross-encoder query-passage relevance filter inflates `independent_sources_count` (`exact match = 21/64 [32.81%]`, `MAE = 0.9688`).
     - **Missed narrative scientific controversies & myth-debunking pages (`7/17` unsafe false passes — `R32_Q20, Q22, Q25, Q30, Q35, Q38, Q41`):** Real-web articles describe scientific debates inside single-page narrative exposition rather than pairwise sentence contradictions across URLs (`dispute recall = 4/14 [28.57%]`), compounded by `5` `MEDIUM -> LOW` hazard under-classifications on scientific dispute queries.
     - **Regulatory hazard boundary (`1/17` unsafe false pass — `R32_Q62`):** GDPR Article 33 72-hour notification rated `HIGH` (`3` sources) by raters vs `MEDIUM` (`2` sources) by `v3`.
     - **False dispute flags on comparative/prohibitive web prose (`7/8` conservative over-hedges — `R32_Q06, Q12, Q32, Q40, Q45, Q55, Q58`):** Negation/prohibitive phrasing across full scraped HTML pages triggered false cross-domain disputes (`dispute FPR = 12/50 [24.00%]`).
     - **Claim-sentence collapse (`1/8` conservative over-hedge — `R32_Q46`):** `3` independent Reye's syndrome pages collapsed to `pred_independent_source_count = 1`.

---

## E. Subagent prompts

All 17 verbatim author, rater, judge, and adjudicator prompts are saved under `logs/test_reports/wo45/prompts/` (verified `0` matches for arm names, model names, legal-standard vocabulary, `_HEDGE_OR_CONFLICT_RE`, or `src/lucca`):

1. `logs/test_reports/wo45/prompts/r10_regrade_288_judge_prompt.md`
2. `logs/test_reports/wo45/prompts/r10v2_judge_prompt.md`
3. `logs/test_reports/wo45/prompts/r40_hazard_rater_prompt.md`
4. `logs/test_reports/wo45/prompts/r40v2_hazard_rater_prompt.md`
5. `logs/test_reports/wo45/prompts/g4_live_v2_judge_prompt.md`
6. `logs/test_reports/wo45/prompts/g4_subagent_task_prompt.md`
7. `logs/test_reports/wo45/prompts/g4v3_judge_prompt.md`
8. `logs/test_reports/wo45/prompts/nli_v2_holdout_author_prompt.txt`
9. `logs/test_reports/wo45/prompts/r21_holdout_author_prompt.txt`
10. `logs/test_reports/wo45/prompts/r21_rater1_prompt.txt`
11. `logs/test_reports/wo45/prompts/r21_rater2_prompt.txt`
12. `logs/test_reports/wo45/prompts/r21_adjudicator_prompt.txt`
13. `logs/test_reports/wo45/prompts/r33_sybil_dev_author_prompt.txt`
14. `logs/test_reports/wo45/prompts/r33_sybil_holdout_author_prompt.txt`
15. `logs/test_reports/wo45/prompts/r32_rater1_prompt.txt`
16. `logs/test_reports/wo45/prompts/r32_rater2_prompt.txt`
17. `logs/test_reports/wo45/prompts/r32_adjudicator_prompt.txt`

---

## F. Reproduction

| Experiment / Task | Command | Expected Output Artifact & SHA-256 |
| :-- | :-- | :-- |
| `R-05` (`N = 360` v2 benchmark harness) | `uv run python scripts/run_web_evidentiary_burden_benchmark.py --output logs/test_reports/web_evidentiary_burden_360_v2_report.json` | `logs/test_reports/web_evidentiary_burden_360_v2_report.json` (`f32f267187362437c492d5066ab221ad383f17492db423df24c5d2b25cd25e90`) |
| `R-06` (`N = 360` NPU vs CPU E2E gate latency) | `uv run python scripts/wo45/bench_wo45_r06_gate_latency.py` | `logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json` (`96e406986017fe812786203e86c8f7b22cc7585c1f41d1260003c9addc214f39`) |
| `R-22` (`N = 360` dispute normalization ablation) | `uv run python scripts/wo45/audit_wo45_r22_dispute_normalization.py` | `logs/test_reports/wo45/r22_dispute_normalization_ablation.json` (`7b823845aa7484b6b6b63717adf41a09ef2ac35157f9ccaef552fb66569fc1ef`) |
| `R-31` (`N = 360` count-only & hazard-only baselines) | `uv run python scripts/wo45/bench_wo45_r31_baselines.py` | `logs/test_reports/wo45/r31_nontrivial_baselines_360.json` (`71456a9ace38e8d56f18408a51c1d6003087a96afb3ec70c972504d8bb6454ee`) |
| `R-10 v2` (`N = 288` cross-model blinded re-grade analysis) | `uv run python scripts/wo45/analyze_wo45_r10v2_and_r40v2.py` | `logs/test_reports/wo45/r10v2_regrade_288_report.json` (`df23b201878954aa6fd508d7b5848945d7d5223712edf668537275fd55ba73fe`) & `r40v2_upward_escalations_audit.json` (`8977cefecf403181d230968dc985e44d60068131a671bcedadda22798cab2070`) |
| `G4 v3` (`2,640`-turn 4-arm 5-model cluster-bootstrap analysis) | `uv run python scripts/wo45/analyze_g4v3.py` | `logs/test_reports/wo45/g4_live_v3_report.json` (`29bc62053c38419f95f3796881480895de1898851f6282ab36dd505ec562e044`) |
| Companion `NLI v2` (`N = 120` DeBERTa-v3-xsmall holdout) | `uv run python scripts/wo45/eval_nli_verifier_v2.py` | `logs/test_reports/nli_verifier_v2_report.json` (`6b4bcf36200ed707a0bbc328cb9ba4f26e15b557bc96e685af32699fda42e178`) |
| `R-21` & `R-42` (`N = 130` multi-clause hazard holdout & `0`-overlap check) | `uv run python scripts/wo45/eval_r21_hazard_holdout.py` | `logs/test_reports/wo45/r21_hazard_holdout_report.json` (`27122fab80d85885f9b0db592279aa1430cc6f2379028a0815744c2bd6b05b41`) & `r42_zero_360_overlap_check.json` (`453f61369558bb8d1aa8d9ec3088fcb7cd33255682c1dd7b1bc7cb34726d4857`) |
| `R-33` (`N = 45` fresh Domain Set B sybil/syndication holdout) | `uv run python scripts/wo45/eval_r33_sybil_holdout.py` | `logs/test_reports/wo45/r33_sybil_dedup_report.json` (`386953193363d5f470467534aba275156313d2fcdf77e0e51ec392ff1e9ee4c3`) |
| `R-32` (`N = 64` live Scrapling real-web archived HTML evaluation) | `uv run python scripts/wo45/eval_r32_real_web.py` | `logs/test_reports/wo45/r32_real_web_v1_report.json` (`252ca7763bd563ba23b89883ef0f9a4bf714218242eb88953ef25d757c7f608a`) |
| `R-51` (`lucca-epistemic` clean-venv wheel + CPU latency check) | `uv run python scripts/wo45/verify_r51_wheel_and_cpu_latency.py` | `packages/lucca-epistemic/dist/lucca_epistemic-0.1.0-py3-none-any.whl` (`beb941a40585cc55975b98b7de14ef87f80e62ba9002c1cc0c1b11d91bf71cf7`) |

---

## G. Open issues

1. **External publication freeze (`R-53` confirmation):** Confirmed that **nothing has been published externally** — zero GitHub Releases created, zero Zenodo DOIs minted for Paper 4, and zero Reddit/LinkedIn/public posts made. All `WO-45` commits and `.ots` proofs reside solely on `origin/main` pending reviewer (`Zoo`) sign-off.
2. **Paper 4 PDF recompilation after `G5`–`G8` LaTeX updates:** `papers/04_clause_level_npu_supervision/main.tex` is fully updated through `Gate G8` (`R-08.3`, `R-21`, `R-32`, `R-33`, `R-41`, `R-42`, `R-50`–`R-53`). This Windows workstation does not have a local `pdflatex`/`tectonic` binary installed (`docs/papers/04_clause_level_npu_supervision.pdf` was last compiled at commit `c39da09` post-`G4 v3`), so `docs/papers/04_clause_level_npu_supervision.pdf` should be recompiled from `main.tex` in a TeX-equipped environment prior to any external preprint circulation.
3. **Post-`G6` `Gate G8` full-suite Hypothesis monotonicity bugfix (`Reviewer Checklist #3` note):** During `Gate G8`'s full `uv run pytest` run (after all holdout results commits `4604afd`, `f6f0ad6`, `02b7803`, and `873e197` were already locked, evaluated once, OTS-stamped, and pushed), `tests/test_wo42_classifiers_fuzz.py::test_fuzz_invariant_2_hazard_monotonicity` found that `cr_full` (`CROSS_REFERENCE_CMD`, `"medium"`) in `src/lucca/core/neural_hazard_classifier.py:374` short-circuited multi-clause `HIGH` pooling when `"verification"` appeared alongside four benign sentences. This 2-line precedence bug was fixed in the `G8` commit without re-running any holdout (per Rule 7). Note that when running `eval_r21_hazard_holdout.py` or `eval_r32_real_web.py` for reproduction, check out their respective results commits (`git checkout f6f0ad6` or `git checkout 873e197`) so the scripts' runtime SHA-256 lock check against `src/lucca/core/neural_hazard_classifier.py` matches the pre-`G8` hash recorded in those locks.
