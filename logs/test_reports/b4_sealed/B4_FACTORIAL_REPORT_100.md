# B4 Clean Held-Out Factorial Ablation Report (12B Model)
**Dataset:** `data/benchmarks/math_b4_sealed_100.jsonl` (SHA-256 `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b`)
**Decoding:** Greedy $T=0.0$, seed 42, `cache_prompt: false` | **Sample Size:** $N=100$ items stratified across 7 MATH subjects
**Execution Date:** 2026-10-07 | **Grader:** v1.35 dual grader (strict `sympy_cas_normalized` + lenient `sympy_cas_lenient_normalization`, SHA `f1caae15...fdbd`)

## 1. Factorial Scorecard

| Arm | Description | Substrate | Strict Acc (%) | 95% Wilson CI | Lenient Acc (%) | 95% Wilson CI | Truncations | Elapsed (s) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **R0** | Raw Direct (cap 4096) | Native text | 93.0% | [85.62%, 96.90%] | 94.0% | [86.88%, 97.54%] | 0% | 1632.5s |
| **P2** | PAL + Turn 2 Feedback (cap 2048) | Docker sandbox | 87.0% | [78.44%, 92.62%] | 92.0% | [84.39%, 96.23%] | 0% | 1817.7s |
| **R1** | Thinking mode (think 6144) | Native text CoT | 46.0% | [36.09%, 56.22%] | 46.0% | [36.09%, 56.22%] | 55% | 9414.6s |

## 2. Paired McNemar Statistical Appendix ($N=100$ Paired Items)

| Comparison | Metric | Arm A Acc | Arm B Acc | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Odds Ratio | Significance ($p < 0.05$) |

| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **P2 vs R0** | Strict | 87.0% | 93.0% | -6.0 | 1 : 7 | 7.0312e-02 | 0.200 | No (Parity / Noise) |
| **R1 vs P2** | Strict | 46.0% | 87.0% | -41.0 | 3 : 44 | 2.4647e-10 | 0.079 | **YES** |
| **R1 vs R0** | Strict | 46.0% | 93.0% | -47.0 | 0 : 47 | 1.4211e-14 | 0.011 | **YES** |
| **P2 vs R0** | Lenient | 92.0% | 94.0% | -2.0 | 2 : 4 | 6.8750e-01 | 0.556 | No (Parity / Noise) |
| **R1 vs P2** | Lenient | 46.0% | 92.0% | -46.0 | 0 : 46 | 2.8422e-14 | 0.011 | **YES** |
| **R1 vs R0** | Lenient | 46.0% | 94.0% | -48.0 | 0 : 48 | 7.1054e-15 | 0.010 | **YES** |