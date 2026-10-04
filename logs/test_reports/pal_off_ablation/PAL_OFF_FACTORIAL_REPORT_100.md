# Project Lucca: Factorial PAL-Off Model-Scale Ablation Report
**Sample Size:** Paired $n=100$ per Arm | **Confidence Level:** 95% Wilson Score CI

## 1. Factorial Performance Scorecard (Model Size x Scaffold Arm)

| Model | Arm | Scaffold / Thinking | Exec Substrate | Benchmark | Strict Acc (%) | Wilson 95% CI | Lenient Acc (%) | Avg Tok/Item | Avg Lat (s) | Peak VRAM | Trunc (%) |
| :--- | :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **gemma-4-e4b** | **R0** | Raw Direct (`enable_thinking=F`) | None (Mental) | math500 | 50.0% | [39.9%, 60.1%] | 50.0% | 841 | 7.69s | 4492 MiB | 16.0% |
| **gemma-4-e4b** | **R1** | Raw Thinking (`enable_thinking=T`) | None (Mental) | math500 | 85.0% | [76.15%, 91.09%] | 86.0% | 1786 | 16.38s | 4492 MiB | 13.0% |

---

## 2. Paired McNemar Statistical Appendix (Discordant Pairs & Significance)

| Model | Benchmark | Arm Comparison | $N$ Paired | Arm A Acc | Arm B Acc | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Odds Ratio | Significance ($p < 0.05$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| gemma-4-e4b | math500 | **R1 vs R0** | 100 | 86.0% | 50.0% | +36.00 | 36 : 0 | 2.9104e-11 | 73.0 | **YES** (Significant) |