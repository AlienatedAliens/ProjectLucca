# Project Lucca: Factorial PAL-Off Model-Scale Ablation Report
**Sample Size:** Paired $n=100$ per Arm | **Confidence Level:** 95% Wilson Score CI

## 1. Factorial Performance Scorecard (Model Size x Scaffold Arm)

| Model | Arm | Scaffold / Thinking | Exec Substrate | Benchmark | Strict Acc (%) | Wilson 95% CI | Lenient Acc (%) | Avg Tok/Item | Avg Lat (s) | Peak VRAM | Trunc (%) |
| :--- | :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **gemma-4-12b** | **R0** | Raw Direct (`enable_thinking=F`) | None (Mental) | math500 | 90.0% | [81.96%, 94.84%] | 93.0% | 660 | 12.88s | 11370 MiB | 6.0% |
| **gemma-4-12b** | **R1** | Raw Thinking (`enable_thinking=T`) | None (Mental) | math500 | 58.0% | [47.71%, 67.67%] | 59.0% | 3793 | 78.11s | 11370 MiB | 44.0% |
| **gemma-4-12b** | **P2** | PAL + Turn 2 Feedback | Docker Sandbox | math500 | 85.0% | [76.15%, 91.09%] | 87.0% | 704 | 14.05s | 11370 MiB | 10.0% |

---

## 2. Paired McNemar Statistical Appendix (Discordant Pairs & Significance)

| Model | Benchmark | Arm Comparison | $N$ Paired | Arm A Acc | Arm B Acc | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Odds Ratio | Significance ($p < 0.05$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| gemma-4-12b | math500 | **P2 vs R0** | 100 | 87.0% | 93.0% | -6.00 | 2 : 8 | 1.0938e-01 | 0.294 | NO (Parity / Noise) |
| gemma-4-12b | math500 | **P2 vs R1** | 100 | 87.0% | 59.0% | +28.00 | 29 : 1 | 5.7742e-08 | 19.667 | **YES** (Significant) |
| gemma-4-12b | math500 | **R1 vs R0** | 100 | 59.0% | 93.0% | -34.00 | 0 : 34 | 1.1642e-10 | 0.014 | **YES** (Significant) |