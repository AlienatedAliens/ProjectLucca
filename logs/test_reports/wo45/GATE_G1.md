# WO-45 Gate G1 Completion Report — Factual Corrections, Disclosures, and Harness Remediation

- **Gate:** `G1` (`R-01`, `R-02`, `R-03`, `R-04`, `R-07`, `R-08`, `R-09`, `R-20`, `R-23` [disclosure part], `R-30` [wording])
- **Status:** `DONE` (pushed to `origin/main`; awaiting reviewer sign-off before proceeding to `G2`/`G3`)
- **Baseline Integrity Verification (`R-00` Frozen Artifacts):**
  - `logs/test_reports/web_evidentiary_burden_360_report.json`: `d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad` (`IDENTICAL`)
  - `logs/test_reports/web_evidentiary_burden_360_REPORT.md`: `e90b4ceccb5faf1876457a9b5667bdf8d06e7518a6a11ce184955f38a8f8c9be` (`IDENTICAL`)
  - `logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`: `aeabb67c05ca8fb63bd933656e9bc017e0033fef58eea4a6434ce2b8dabd81eb` (`IDENTICAL`)
  - `data/benchmarks/web_evidentiary_burden_360.jsonl`: `db685e70e65b40ba42be0e3ea2bbf54ac00b72ec6c69546faeabcff3b5574e13` (`IDENTICAL`)

---

## 1. Per-Task Status & Evidence Summary (Gate G1)

| Task ID | Status | Commit SHA | Modified Files & Line Ranges |
| :--- | :---: | :---: | :--- |
| **`R-00`** | `DONE` | `c9706a1` (`7303345`) | `logs/test_reports/wo45/baseline_hashes.json:1-19`, `logs/test_reports/wo45/GATE_G0.md:1-38` |
| **`R-01`** | `DONE` | `6eac282` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:6,27,123`, `luccadocs/ARCHITECTURE.md:135,631,775,850`, `luccadocs/DECISIONS.md:80`, `luccadocs/archive/2026-09_milestone_specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md:292` |
| **`R-02`** | `DONE` | `22c5bd0` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:7,25` |
| **`R-03`** | `DONE` | `25d1691` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:8,47-52` |
| **`R-04`** | `DONE` | `804dbbf` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:8,53-56` |
| **`R-07`** | `DONE` | `468c502` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:70-73,97,124,128-131`, `README.md:77`, `luccadocs/specs/CAPABILITY_REGISTER.md:71`, `papers/04_clause_level_npu_supervision/main.tex:32,295` |
| **`R-08`** | `DONE` | `a6273f0` | `scripts/run_web_evidentiary_burden_benchmark.py:40,42,64-69,203-336,402-408,520-521,774,846`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:30,91-93` |
| **`R-09`** | `DONE` | `0d84768` | `logs/test_reports/web_evidentiary_burden_60_report.json:1-913`, `logs/test_reports/web_evidentiary_burden_60_REPORT.md:1-8`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:88-97` |
| **`R-20`** | `DONE` | `2e5091e` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:60,64-68`, `README.md:77`, `papers/04_clause_level_npu_supervision/main.tex:32,245-249,274` |
| **`R-23`** | `PARTIAL` (G1 disclosure `DONE`; `.ots` timestamps in G2/G4/G5) | `f6630b3` | `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:60`, `papers/04_clause_level_npu_supervision/main.tex:238` |
| **`R-30`** | `DONE` | `a27436a` | `papers/04_clause_level_npu_supervision/main.tex:32,273`, `docs/papers/04_clause_level_npu_supervision.pdf`, `README.md:54-62,77`, `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:1-10,64-68` |

---

## 2. Detailed Return Blocks & Verbatim AC Command Outputs

### `R-01` — False Ed25519 Claim Replaced with Symmetric HKDF HMAC-SHA256 (`6eac282`)
- **Files Changed:**
  - `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md` (`:6`, `:27`, `:123`)
  - `luccadocs/ARCHITECTURE.md` (`:135`, `:631`, `:775`, `:850`)
  - `luccadocs/DECISIONS.md` (`:80`)
  - `luccadocs/archive/2026-09_milestone_specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md` (`:292`)
- **Verbatim AC Command Output (`findstr /s /i /n "ed25519"` across `papers`, `luccadocs`, `README.md`, and `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`):**
```text
luccadocs\ARCHITECTURE.md:135:| `src/lucca/memory/signers.py` | 6 domain-separated HKDF-SHA256 HMAC signers (`USER_EXPLICIT`, `USER_DERIVED`, `TOOL_VERIFIED`, `LISP_ASSERTION`, `DREAM_INDUCTION`, `SELF_METRIC`) under a local master key (symmetric tamper-detection integrity; asymmetric Ed25519 signatures are not used) |
luccadocs\ARCHITECTURE.md:631:- **Integrity Verification:** Symmetric HKDF-SHA256 HMAC (`src/lucca/memory/signers.py`) with 6 domain-separated keys (`USER_EXPLICIT`, `USER_DERIVED`, `TOOL_VERIFIED`, `LISP_ASSERTION`, `DREAM_INDUCTION`, `SELF_METRIC`) derived from a local master key (Ed25519 is not used).
luccadocs\ARCHITECTURE.md:775:  - `signers.py`: 6 domain-separated HKDF-SHA256 HMAC signers (`src/lucca/memory/signers.py`; Ed25519 is not used).
luccadocs\ARCHITECTURE.md:850:1. **Memory Provenance Gate:** 6 domain-separated HKDF-SHA256 HMAC signers (`src/lucca/memory/signers.py`; Ed25519 is not used) + SQLite triggers (`0006_epistemic_separation.sql`) + `BelnapLatentInvestigator` + sentence-level Scrapling web corroboration.
luccadocs\DECISIONS.md:80:| **D-MEM-01** | **HKDF-SHA256 HMAC Provenance Envelopes** | Every memory record is signed with a domain-separated HKDF-SHA256 HMAC key (`src/lucca/memory/signers.py`; asymmetric Ed25519 signatures are not used) and checked by `ProvenanceGate` before persistence. | `ADR-006` |
luccadocs\archive\2026-09-17_pre_phase4_audit\08_adr\ADR-006_provenance_tiers_and_signers.md:75:  with an Ed25519 keypair per domain. Not needed now; the Protocol allows it later.
luccadocs\archive\2026-09_milestone_specs\TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md:292:- Every memory write passes through `ProvenanceGate` (`src/lucca/memory/gate.py`) with domain-separated HKDF-SHA256 HMAC signers (`src/lucca/memory/signers.py`; asymmetric Ed25519 is not used).
logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md:6:> 1. **Ed25519 Claim Retracted (`R-01`):** Memory records are signed via symmetric HKDF HMAC-SHA256 (`src/lucca/memory/signers.py:57-75`) under a local master key; asymmetric Ed25519 signatures are not used.
logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md:27:   - Symmetric HKDF HMAC-SHA256 integrity signing of memory records across 5 isolated memory tiers under a local master key (`src/lucca/memory/signers.py:57-75`; asymmetric Ed25519 third-party-verifiable signatures are not used).
logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md:123:| **1. NLnet Foundation (NGI Zero Commons Fund)** | `€5,000–€50,000` (Bimonthly rolling) | Standalone open-source neurosymbolic verification & HKDF HMAC-SHA256/Belnap $K_4$ epistemic provenance layer (Ed25519 is not used) running locally on consumer hardware (`2.5 GB–11.1 GB` VRAM). | *Objection:* "Is this tied only to Windows + Intel NPU?"<br>*Mitigation:* Highlight OpenVINO CPU fallback (`<6 ms` on any x86/ARM CPU) and standalone library extraction. |
```

### `R-02` — Non-Existent `models/deontic_ov` Replaced (`22c5bd0`)
- **Mapping Table (`{claimed name -> real path -> latency -> source artifact}`):**

| Claimed Name in WO-44 Packet | Real Existing Directory Path | Verified Latency | Source Artifact & JSON Key Path |
| :--- | :--- | :---: | :--- |
| `models/deontic_ov` (`~4.1 ms`/clause) — **RETRACTED (does not exist)** | `models/action_claim_verifier_ov` (`NeuralActionClaimVerifier`, 3-class speech-act NPU verifier) | `12.13 ms` multi-clause mean (`2.95 ms` mean / `3.67 ms` P95 on 1–4 clause turns) | `logs/test_reports/wo42_large_sample_2020_report.json` (`splits.Pooled_All_Supervision_Turns.wo42_clause_npu.mean_latency_ms`) |
| `models/proof_policy_hazard_ov` | `models/proof_policy_hazard_ov` (`NeuralHazardClassifier`, 5-class hazard NPU classifier) | `5.35 ms` mean (`9.094 ms` P95) | `logs/test_reports/web_evidentiary_burden_360_report.json` (`metrics.npu_latency_mean_ms`, `metrics.npu_latency_p95_ms`) |
| `models/router_intent_ov` | `models/router_intent_ov` (`NeuralIntentClassifier`, 29-class intent NPU classifier) | `1.22 ms` mean | `logs/test_reports/wo41_neural_supervision_report.json` |

### `R-03` — Memory-Poisoning & Contrastive Battery Numbers Traced to JSON Keys (`25d1691`)
- **Return Table (`{claim -> artifact -> JSON key -> value}`):**

| Claim in WO-44 Packet | Source Artifact | JSON Key Path | Verified Value |
| :--- | :--- | :--- | :--- |
| `"63.7% (191/300) unguarded uplift"` | **UNSOURCED / RETRACTED** (conflated Cohort B benign retention with adversarial cohorts) | — | Retracted; replaced by per-cohort JSON values below |
| Cohort A Naive RAG poisoning ($n=100$) | `logs/test_reports/memory_poisoning_v3_300_results.json` | `cohort_a_poisoning_compounding_rate.naive_rag` | `100/100` (`100.0%`, 95% Wilson CI `[95.39%, 100.0%]`) |
| Cohort A Passive Soft Tagging poisoning ($n=100$) | `logs/test_reports/memory_poisoning_v3_300_results.json` | `cohort_a_poisoning_compounding_rate.soft_prompt_tagging` | `11/100` (`11.0%`, 95% Wilson CI `[5.89%, 19.22%]`) |
| Cohort A Adversarial Soft Tagging poisoning ($n=100$) | `logs/test_reports/memory_poisoning_v3_300_results.json` | `cohort_a_poisoning_compounding_rate.soft_prompt_tagging_adversarial` | `100/100` (`100.0%`, 95% Wilson CI `[95.39%, 100.0%]`) |
| Cohort A Lucca Provenance Gate poisoning ($n=100$) | `logs/test_reports/memory_poisoning_v3_300_results.json` | `cohort_a_poisoning_compounding_rate.lucca_provenance_gate` | `0/100` (`0.0%`, 95% Wilson CI `[0.0%, 4.61%]`; exact McNemar $p = 4.16 \times 10^{-23}$ at `hypothesis_tests.cohort_a_lucca_vs_naive_rag`) |
| Cohort A Continuity Retention ($n=100$) | `logs/test_reports/memory_poisoning_v3_300_results.json` | `cohort_a_continuity_retention.lucca_provenance_gate` (vs `.no_assistant_memory`) | `100/100` (`100.0%`, CI `[95.39%, 100.0%]`) vs `2/100` (`2.0%`) |
| Cohort B Benign Reasoning Retention ($n=100$) | `logs/test_reports/memory_poisoning_v3_300_results.json` | `cohort_b_benign_reasoning_retention.lucca_provenance_gate` (vs `.no_assistant_memory`) | `100/100` (`100.0%`, CI `[95.39%, 100.0%]`) vs `1/100` (`1.0%`) |
| Cohort C User Misinformation Absorption ($n=100$) | `logs/test_reports/memory_poisoning_v3_300_results.json` | `cohort_c_user_misinformation_absorption.lucca_provenance_gate` (vs `.naive_rag`) | `0/100` (`0.0%`, CI `[0.0%, 4.61%]`) vs `100/100` (`100.0%`) |
| `"96.7% (290/300) recall"` | **UNSOURCED / RETRACTED** | — | Retracted; replaced by per-stratum JSON values below |
| Contrastive v2 Seeded Recall ($n=100$) | `logs/test_reports/contrastive_v2_300_results.json` | `summaries.arm_b.recall` (vs `arm_a` / `arm_c`) | `100/100` (`100.0%`, CI `[95.39%, 100.0%]`) vs `2/100` (`2.0%`) / `85/100` (`85.0%`) |
| Contrastive v2 Receipt Introspection ($n=100$) | `logs/test_reports/contrastive_v2_300_results.json` | `summaries.arm_b.receipt_introspection` (vs `arm_a` / `arm_c`) | `100/100` (`100.0%`, CI `[95.39%, 100.0%]`) vs `50/100` (`50.0%`) / `98/100` (`98.0%`) |
| Contrastive v2 Calibrated Abstention ($n=100$) | `logs/test_reports/contrastive_v2_300_results.json` | `summaries.arm_b.abstention` (vs `arm_a` / `arm_c`) | `100/100` (`100.0%`, CI `[95.39%, 100.0%]`) vs `99/100` (`99.0%`) / `100/100` (`100.0%`) |

### `R-04` — `LOCKED_HZD` 49/50 Provenance & Recomputed McNemar Statistics (`804dbbf`)
- **Finding:** The claim `"LOCKED_HZD N=50, 49/50 vs 32/50, McNemar p=3.8e-5"` is **unsourced** and has been retracted and removed from `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md`.
- **Verified Artifact Values & Recomputed Discordant Statistics:**
  1. **`LOCKED_HZD` Single-Pass Holdout ($N=50$):** `logs/test_reports/wo42_locked_holdout_150_report.json` (`subsystems.proof_policy`): `50/50` (`100.0%`, 95% Wilson CI `[92.87%, 100.00%]`). No pre-pooling baseline was run on `LOCKED_HZD_001..050`.
  2. **`BLIND42_HZD` Pre-Pooling vs. Post-Pooling ($N=100$):** `logs/test_reports/wo42_pass1_pre_pooling_fix_report.json` (`subsystems.proof_policy.blind_300`: `69/100 = 69.0%`, CI `[59.37%, 77.22%]`) $\to$ `logs/test_reports/wo42_statistical_power_and_ci_report.json` (`subsystems.proof_policy.blind_300`: `95/100 = 95.0%`, CI `[88.82%, 97.85%]`). Recomputed from `missed_ids`: discordant counts **`b:c = 29:3`**, exact two-sided binomial McNemar **`p = 2.556015e-06`** ($2.56 \times 10^{-6}$).
  3. **`combined_130` Pre-Pooling vs. Post-Pooling ($N=130$):** `97/130` (`74.62%`, CI `[66.50%, 81.32%]`) $\to$ `125/130` (`96.15%`, CI `[91.32%, 98.34%]`), discordant counts **`b:c = 31:3`**, exact two-sided binomial McNemar **`p = 7.660128e-07`** ($7.66 \times 10^{-7}$).

### `R-07` — Prose Standard & Removal of Unresolved R-10/R-11 Superiority Claims (`468c502`)
- **Verbatim AC Command Output (`uv run pytest tests/test_static_gates.py -k test_no_ai_slop_in_papers_and_docs -v`):**
```text
============================= test session starts =============================
platform win32 -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0 -- C:\Projects\ProjectLucca\.venv\Scripts\python.exe
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: C:\Projects\ProjectLucca
configfile: pyproject.toml
plugins: anyio-4.15.1, hypothesis-6.168.0, asyncio-1.4.0, cov-7.1.0, timeout-2.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 40 items / 39 deselected / 1 selected

tests/test_static_gates.py::test_no_ai_slop_in_papers_and_docs PASSED    [100%]

====================== 1 passed, 39 deselected in 0.36s =======================
```

### `R-08` — Three Claimed Fixes Implemented or Retracted (`a6273f0`)
- **Fix 1 (`build_launch_command`):** Wired `from lucca.brain.server_ctl import build_launch_command` (`scripts/run_web_evidentiary_burden_benchmark.py:40`) and `cmd = build_launch_command(llm_cfg, LUCCA_HOME)` (`:242`), and fixed `MODEL_MATRIX` tier for `26B-A4B` (`:68`).
- **Fix 2 (Contiguous Arm A $\to$ Arm B Batching & Removal of `LUCCA_BENCH_REUSE_MODELS`):** Removed `LUCCA_BENCH_REUSE_MODELS` cached-report splicing and refactored `run_live_4model_matrix()` (`:291-318`) so all 36 Arm A turns run contiguously first (`sys_a` prefix cached) followed by all 36 Arm B turns (`sys_b` prefix cached).
- **Fix 3 (`ClauseSplitter` in `proof_policy.py`):** Explicitly retracted in `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:30,92`: `proof_policy.py:classify_hazard()` (`:116`) does not call `ClauseSplitter` directly (kept untouched to preserve its SHA-256 hash in `web_evidentiary_burden_360_prereg_lock.json`, while `_SENTENCE_SPLIT_RE` was edited inside `src/lucca/core/neural_hazard_classifier.py:48-51`).
- **Verbatim AC Command Output:**
```text
PS C:\Projects\ProjectLucca> findstr /n "build_launch_command" scripts\run_web_evidentiary_burden_benchmark.py; Write-Host "EXIT_1=$LASTEXITCODE"; findstr /n "LUCCA_BENCH_REUSE_MODELS" scripts\run_web_evidentiary_burden_benchmark.py; Write-Host "EXIT_2=$LASTEXITCODE"; findstr /n "ClauseSplitter split_clauses" src\lucca\core\proof_policy.py; Write-Host "EXIT_3=$LASTEXITCODE"
40:from lucca.brain.server_ctl import build_launch_command  # noqa: E402
242:        cmd = build_launch_command(llm_cfg, LUCCA_HOME)
EXIT_1=0
EXIT_2=1
EXIT_3=1
```

### `R-09` — Artifact Provenance Defects Remediated (`0d84768`)
- **Regenerated Independent `N=60` Report (`logs/test_reports/web_evidentiary_burden_60_report.json`):** Evaluated on `data/benchmarks/web_evidentiary_burden_60.jsonl` (`60` items, `n=5`/cell) and removed the byte-copy overwrite from `scripts/run_web_evidentiary_burden_benchmark.py`.
- **Per-Model Provenance Fields Added:** `scripts/run_web_evidentiary_burden_benchmark.py:402-408` now writes `provenance: "fresh"`, `tier_label`, `ctx_size`, `launch_cmd`, `started_at_utc`, and `completed_at_utc`.
- **Overwritten Pre-Fix Artifacts Labeled:** `350/360`, `277/360`, and "before" latencies (`0.63 s`, `1.00 s`, `2.69 s`, `4.49 s` / `37.0 s`) are explicitly labeled *"not reproducible: artifact overwritten"* across Paper 4, `README.md`, and the review packet.
- **Verbatim AC Command Output (`certutil -hashfile`):**
```text
SHA256 hash of logs\test_reports\web_evidentiary_burden_360_report.json:
d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad
CertUtil: -hashfile command completed successfully.
SHA256 hash of logs\test_reports\web_evidentiary_burden_60_report.json:
1591cc10820cd8bc6305f1ac621827d40bd1d87bf2a4b9a0a20af8ed93c6a230
CertUtil: -hashfile command completed successfully.
```

### `R-20` & `R-23` (Disclosure) & `R-30` (Wording) (`2e5091e`, `f6630b3`, `a27436a`)
- **`R-20`:** Disclosed in `papers/04_clause_level_npu_supervision/main.tex` (`:32`, `:238`, `:245-249`, `:274`), `README.md` (`:58`, `:77`), and `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md` (`:9`, `:60`, `:64-68`) that `src/lucca/core/neural_hazard_classifier.py` was omitted from `web_evidentiary_burden_360_prereg_lock.json`, and labeled `360/360` (`100.0%`) safe hazard and `287/360` (`79.72%`) strict 3-class accuracy as **"post-hoc, in-sample"**.
- **`R-23` (Disclosure):** Disclosed in `papers/04_clause_level_npu_supervision/main.tex:238` and `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:60` that `proof_policy.py`, `neural_hazard_classifier.py`, the lock, the corpus, and the report all landed together in single commit `82b1da8`.
- **`R-30` (Wording):** Relabeled the `360/360` (`100.0%`) Walton `Scheme.AUTHORITY` result in `papers/04_clause_level_npu_supervision/main.tex:32,249,273`, `README.md:59,77`, `luccadocs/specs/CAPABILITY_REGISTER.md:71`, and `logs/test_reports/EXTERNAL_AI_REVIEW_PACKET_WO44.md:10,66` as a **specification conformance test** on synthetic structured snippets and removed the McNemar $p = 1.05 \times 10^{-81}$ comparison against the static `0.85` strawman as evidence of efficacy. Rebuilt `docs/papers/04_clause_level_npu_supervision.pdf` (`725,621` bytes) and verified all `40/40` static gates pass (`uv run pytest tests/test_static_gates.py -v`).
