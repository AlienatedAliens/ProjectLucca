# Contrastive Companion Battery v2 Report ($N = 300$, Frozen Grader)
**Date:** 2026-11-09 | **Timestamp:** 20261108T182656Z
**Git Commit:** `cc8fa8c79318f82f5beba734cad600e1f832456e` | **Protocol Tag:** `prereg-wo43-power-300`
**Probes Dataset:** `contrastive_battery_v2_300.jsonl` ($N=300$, SHA-256 `caa726bfa0618db4801e838251d5e3dd80f23d995a50a9b67cd548a4490d54bc`)
**Frozen Grader SHA-256:** `d78c91acb45c41fd293628441afaa33377f89b454f1ace6e1e2759c001b567bc`

## 1. Scorecard by Arm and Stratum ($n = 100$ per stratum)

| Arm | Stratum | Pass / Valid | Pass Rate (%) | 95% Wilson CI | Errors | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Arm A (Bare LLM)** | recall | 2/100 | 2.0% | [0.4%, 7.7%] | 0 | VALID |
| **Arm A (Bare LLM)** | receipt_introspection | 50/100 | 50.0% | [39.9%, 60.1%] | 0 | VALID |
| **Arm A (Bare LLM)** | abstention | 99/100 | 99.0% | [93.8%, 100.0%] | 0 | VALID |
| **Arm B (Compound Lucca)** | recall | 100/100 | 100.0% | [95.4%, 100.0%] | 0 | PASSED (>= 80%) |
| **Arm B (Compound Lucca)** | receipt_introspection | 100/100 | 100.0% | [95.4%, 100.0%] | 0 | PASSED (>= 80%) |
| **Arm B (Compound Lucca)** | abstention | 100/100 | 100.0% | [95.4%, 100.0%] | 0 | PASSED (>= 80%) |
| **Arm C (RAG Baseline)** | recall | 85/100 | 85.0% | [76.1%, 91.1%] | 0 | VALID |
| **Arm C (RAG Baseline)** | receipt_introspection | 98/100 | 98.0% | [92.3%, 99.7%] | 0 | VALID |
| **Arm C (RAG Baseline)** | abstention | 100/100 | 100.0% | [95.4%, 100.0%] | 0 | VALID |

## 2. Paired Exact McNemar Tests (with Holm-Bonferroni Correction)

| Comparison | Stratum | Arm 1 | Arm 2 | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$ | Holm-Bonferroni $p_{\text{adj}}$ | Sig ($p_{\text{adj}} < 0.05$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **arm_b vs arm_a** | recall | 100.0% | 2.0% | +98.0 | 98 : 0 | 1.1429e-22 | 1.0286e-21 | **YES** |
| **arm_b vs arm_a** | receipt_introspection | 100.0% | 50.0% | +50.0 | 50 : 0 | 4.2189e-12 | 2.9533e-11 | **YES** |
| **arm_b vs arm_a** | abstention | 100.0% | 99.0% | +1.0 | 1 : 0 | 1.0000e+00 | 1.0000e+00 | No |
| **arm_b vs arm_c** | recall | 100.0% | 85.0% | +15.0 | 15 : 0 | 6.1035e-05 | 3.0518e-04 | **YES** |
| **arm_b vs arm_c** | receipt_introspection | 100.0% | 98.0% | +2.0 | 2 : 0 | 5.0000e-01 | 1.0000e+00 | No |
| **arm_b vs arm_c** | abstention | 100.0% | 100.0% | +0.0 | 0 : 0 | 1.0000e+00 | 1.0000e+00 | No |
| **arm_c vs arm_a** | recall | 85.0% | 2.0% | +83.0 | 84 : 1 | 5.8869e-19 | 4.7095e-18 | **YES** |
| **arm_c vs arm_a** | receipt_introspection | 98.0% | 50.0% | +48.0 | 48 : 0 | 1.1700e-11 | 7.0201e-11 | **YES** |
| **arm_c vs arm_a** | abstention | 100.0% | 99.0% | +1.0 | 1 : 0 | 1.0000e+00 | 1.0000e+00 | No |
