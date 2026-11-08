# Contrastive Companion Battery v2 Report ($N = 300$, Frozen Grader)
**Date:** 2026-11-08 | **Timestamp:** 20261108T075344Z
**Git Commit:** `f45ca9fbff438a7b1f001a91a03eea4073d7dbb2` | **Protocol Tag:** `prereg-wo43-power-300`
**Probes Dataset:** `contrastive_battery_v2_300.jsonl` ($N=300$, SHA-256 `f3836d3cbfe8125863eef5c329eb30238200db2515e01dfb2ec88e9747a82b0b`)
**Frozen Grader SHA-256:** `f015710fbb634d00639004c5afbd604304803a23ffb968ad22d71246807727c2`

## 1. Scorecard by Arm and Stratum ($n = 100$ per stratum)

| Arm | Stratum | Pass / Valid | Pass Rate (%) | 95% Wilson CI | Errors | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Arm A (Bare LLM)** | recall | 5/100 | 5.0% | [1.9%, 11.8%] | 0 | VALID |
| **Arm A (Bare LLM)** | receipt_introspection | 92/100 | 92.0% | [84.4%, 96.2%] | 0 | VALID |
| **Arm A (Bare LLM)** | abstention | 94/100 | 94.0% | [86.9%, 97.5%] | 0 | VALID |
| **Arm B (Compound Lucca)** | recall | 99/100 | 99.0% | [93.8%, 100.0%] | 0 | PASSED (>= 80%) |
| **Arm B (Compound Lucca)** | receipt_introspection | 95/100 | 95.0% | [88.2%, 98.1%] | 0 | PASSED (>= 80%) |
| **Arm B (Compound Lucca)** | abstention | 90/100 | 90.0% | [82.0%, 94.8%] | 0 | PASSED (>= 80%) |
| **Arm C (RAG Baseline)** | recall | 86/100 | 86.0% | [77.3%, 91.9%] | 0 | VALID |
| **Arm C (RAG Baseline)** | receipt_introspection | 99/100 | 99.0% | [93.8%, 100.0%] | 0 | VALID |
| **Arm C (RAG Baseline)** | abstention | 100/100 | 100.0% | [95.4%, 100.0%] | 0 | VALID |

## 2. Paired Exact McNemar Tests (with Holm-Bonferroni Correction)

| Comparison | Stratum | Arm 1 | Arm 2 | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$ | Holm-Bonferroni $p_{\text{adj}}$ | Sig ($p_{\text{adj}} < 0.05$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm_b vs arm_a** | recall | 99.0% | 5.0% | +94.0 | 94 : 0 | 8.6212e-22 | 7.7591e-21 | **YES** |
| **arm_b vs arm_a** | receipt_introspection | 95.0% | 92.0% | +3.0 | 8 : 5 | 5.8105e-01 | 6.5625e-01 | No |
| **arm_b vs arm_a** | abstention | 90.0% | 94.0% | -4.0 | 2 : 6 | 2.8906e-01 | 6.5625e-01 | No |
| **arm_b vs arm_c** | recall | 99.0% | 86.0% | +13.0 | 14 : 1 | 9.7656e-04 | 6.8359e-03 | **YES** |
| **arm_b vs arm_c** | receipt_introspection | 95.0% | 99.0% | -4.0 | 1 : 5 | 2.1875e-01 | 6.5625e-01 | No |
| **arm_b vs arm_c** | abstention | 90.0% | 100.0% | -10.0 | 0 : 10 | 1.9531e-03 | 1.1719e-02 | **YES** |
| **arm_c vs arm_a** | recall | 86.0% | 5.0% | +81.0 | 82 : 1 | 1.6182e-18 | 1.2946e-17 | **YES** |
| **arm_c vs arm_a** | receipt_introspection | 99.0% | 92.0% | +7.0 | 7 : 0 | 1.5625e-02 | 7.8125e-02 | No |
| **arm_c vs arm_a** | abstention | 100.0% | 94.0% | +6.0 | 6 : 0 | 3.1250e-02 | 1.2500e-01 | No |
