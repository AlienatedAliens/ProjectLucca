# Project Lucca: Factorial PAL-Off Model-Scale Ablation Report
**Sample Size:** Paired $n=5$ per Arm | **Confidence Level:** 95% Wilson Score CI

## 1. Factorial Performance Scorecard (Model Size x Scaffold Arm)

| Model | Arm | Scaffold / Thinking | Exec Substrate | Benchmark | Strict Acc (%) | Wilson 95% CI | Lenient Acc (%) | Avg Tok/Item | Avg Lat (s) | Peak VRAM | Trunc (%) |
| :--- | :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **gemma-4-e2b** | **R0** | Raw Direct (`enable_thinking=F`) | None (Mental) | gsm_symbolic | 80.0% | [29.88%, 98.95%] | 80.0% | 565 | 3.70s | 2372 MiB | 0.0% |

---

## 2. Paired McNemar Statistical Appendix (Discordant Pairs & Significance)

| Model | Benchmark | Arm Comparison | $N$ Paired | Arm A Acc | Arm B Acc | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Odds Ratio | Significance ($p < 0.05$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |