# Contrastive Live-Companion Battery Report (v2 Frozen Grader)
**Date:** 2026-10-07 | **Timestamp:** 20261006T220517Z
**Git Commit:** `d9ac70fad1dd5479ef2c3a04213c2fe55cbf5026` | **Grader SHA-256:** `f015710fbb634d00639004c5afbd604304803a23ffb968ad22d71246807727c2`
**Probes Dataset:** `C:\Projects\ProjectLucca\tests\fixtures\contrastive\probes.jsonl` ($N=30$ probes across 3 strata)
**Arms Evaluated:** arm_a, arm_b, arm_c

## 1. Scorecard by Arm and Stratum

| Arm | Stratum | Pass / Valid | Pass Rate (%) | 95% Wilson CI | Errors | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Arm A (Bare LLM)** | recall | 0/10 | 0.0% | [0.0%, 34.5%] | 0 | VALID |
| **Arm A (Bare LLM)** | receipt_introspection | 7/10 | 70.0% | [35.4%, 91.9%] | 0 | VALID |
| **Arm A (Bare LLM)** | abstention | 10/10 | 100.0% | [65.5%, 100.0%] | 0 | VALID |
| **Arm B (Compound)** | recall | 10/10 | 100.0% | [65.5%, 100.0%] | 0 | PASSED (>= 80%) |
| **Arm B (Compound)** | receipt_introspection | 8/10 | 80.0% | [44.2%, 96.5%] | 0 | PASSED (>= 80%) |
| **Arm B (Compound)** | abstention | 9/10 | 90.0% | [54.1%, 99.5%] | 0 | PASSED (>= 80%) |
| **Arm C (RAG Baseline)** | recall | 10/10 | 100.0% | [65.5%, 100.0%] | 0 | VALID |
| **Arm C (RAG Baseline)** | receipt_introspection | 10/10 | 100.0% | [65.5%, 100.0%] | 0 | VALID |
| **Arm C (RAG Baseline)** | abstention | 9/10 | 90.0% | [54.1%, 99.5%] | 0 | VALID |

## 2. Paired McNemar Statistical Appendix

| Comparison | Stratum | Arm 1 Rate | Arm 2 Rate | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Sig ($p < 0.05$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm_b vs arm_a** | recall | 100.0% | 0.0% | +100.0 | 10 : 0 | 1.9531e-03 | **YES** |
| **arm_b vs arm_a** | receipt_introspection | 80.0% | 70.0% | +10.0 | 1 : 0 | 1.0000e+00 | No |
| **arm_b vs arm_a** | abstention | 90.0% | 100.0% | -10.0 | 0 : 1 | 1.0000e+00 | No |
| **arm_b vs arm_c** | recall | 100.0% | 100.0% | +0.0 | 0 : 0 | 1.0000e+00 | No |
| **arm_b vs arm_c** | receipt_introspection | 80.0% | 100.0% | -20.0 | 0 : 2 | 5.0000e-01 | No |
| **arm_b vs arm_c** | abstention | 90.0% | 90.0% | +0.0 | 0 : 0 | 1.0000e+00 | No |
| **arm_c vs arm_a** | recall | 100.0% | 0.0% | +100.0 | 10 : 0 | 1.9531e-03 | **YES** |
| **arm_c vs arm_a** | receipt_introspection | 100.0% | 70.0% | +30.0 | 3 : 0 | 2.5000e-01 | No |
| **arm_c vs arm_a** | abstention | 90.0% | 100.0% | -10.0 | 0 : 1 | 1.0000e+00 | No |

## 3. Register Invariant Audit & Remediation Verification
- **C-01 (Empty Replies -> Error):** Empty replies are explicitly captured as `Grade.ERROR`, avoiding artificial scoring degradation.
- **C-02 (Genuine Abstention):** Grader checks frozen canonical abstention phrases including explicit lack of knowledge.
- **C-03 (Baseline by Construction):** Addition of Arm C (RAG Baseline) provides a fair retrieval comparison vs compound layer.
- **C-04 (Frozen Grader Gate):** Grader criteria strictly immutable and SHA-256 embedded into artifact.
- **C-05 (Echo Stripping):** SequenceMatcher sliding window removes >= 4 word echoed question runs prior to credit attribution.
- **C-06 (Recollection Hysteresis):** Validates live execution under verified safety supervisor without false aborts.
