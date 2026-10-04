# Project Lucca: Factorial PAL-Off Model-Scale Ablation Report
**Sample Size:** Paired $n=2$ per Arm | **Confidence Level:** 95% Wilson Score CI

## 1. Factorial Performance Scorecard (Model Size x Scaffold Arm)

| Model | Arm | Scaffold / Thinking | Exec Substrate | Benchmark | Strict Acc (%) | Wilson 95% CI | Lenient Acc (%) | Avg Tok/Item | Avg Lat (s) | Peak VRAM | Trunc (%) |
| :--- | :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **gemma-4-e2b** | **R0** | Raw Direct (`enable_thinking=F`) | None (Mental) | gsm_symbolic | 50.0% | [2.67%, 97.33%] | 50.0% | 780 | 8.02s | 2372 MiB | 0.0% |
| **gemma-4-e2b** | **R1** | Raw Thinking (`enable_thinking=T`) | None (Mental) | gsm_symbolic | 100.0% | [19.79%, 100.0%] | 100.0% | 1212 | 6.84s | 2372 MiB | 0.0% |
| **gemma-4-e2b** | **P1** | PAL Turn 1 | Docker Sandbox | gsm_symbolic | 100.0% | [19.79%, 100.0%] | 100.0% | 484 | 5.11s | 2372 MiB | 0.0% |
| **gemma-4-e2b** | **P2** | PAL + Turn 2 Feedback | Docker Sandbox | gsm_symbolic | 100.0% | [19.79%, 100.0%] | 100.0% | 484 | 2.71s | 2372 MiB | 0.0% |
| **gemma-4-e2b** | **R0** | Raw Direct (`enable_thinking=F`) | None (Mental) | math500 | 50.0% | [2.67%, 97.33%] | 50.0% | 976 | 5.41s | 2372 MiB | 0.0% |
| **gemma-4-e2b** | **R1** | Raw Thinking (`enable_thinking=T`) | None (Mental) | math500 | 100.0% | [19.79%, 100.0%] | 100.0% | 1539 | 8.67s | 2372 MiB | 0.0% |
| **gemma-4-e2b** | **P1** | PAL Turn 1 | Docker Sandbox | math500 | 50.0% | [2.67%, 97.33%] | 50.0% | 631 | 3.85s | 2372 MiB | 50.0% |
| **gemma-4-e2b** | **P2** | PAL + Turn 2 Feedback | Docker Sandbox | math500 | 100.0% | [19.79%, 100.0%] | 100.0% | 1188 | 6.85s | 2372 MiB | 0.0% |

---

## 2. Paired McNemar Statistical Appendix (Discordant Pairs & Significance)

| Model | Benchmark | Arm Comparison | $N$ Paired | Arm A Acc | Arm B Acc | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Odds Ratio | Significance ($p < 0.05$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| gemma-4-e2b | gsm_symbolic | **P2 vs R0** | 2 | 100.0% | 50.0% | +50.00 | 1 : 0 | 1.0000e+00 | 3.0 | NO (Parity / Noise) |
| gemma-4-e2b | gsm_symbolic | **P2 vs R1** | 2 | 100.0% | 100.0% | +0.00 | 0 : 0 | 1.0000e+00 | 1.0 | NO (Parity / Noise) |
| gemma-4-e2b | gsm_symbolic | **R1 vs R0** | 2 | 100.0% | 50.0% | +50.00 | 1 : 0 | 1.0000e+00 | 3.0 | NO (Parity / Noise) |
| gemma-4-e2b | gsm_symbolic | **P2 vs P1** | 2 | 100.0% | 100.0% | +0.00 | 0 : 0 | 1.0000e+00 | 1.0 | NO (Parity / Noise) |
| gemma-4-e2b | math500 | **P2 vs R0** | 2 | 100.0% | 50.0% | +50.00 | 1 : 0 | 1.0000e+00 | 3.0 | NO (Parity / Noise) |
| gemma-4-e2b | math500 | **P2 vs R1** | 2 | 100.0% | 100.0% | +0.00 | 0 : 0 | 1.0000e+00 | 1.0 | NO (Parity / Noise) |
| gemma-4-e2b | math500 | **R1 vs R0** | 2 | 100.0% | 50.0% | +50.00 | 1 : 0 | 1.0000e+00 | 3.0 | NO (Parity / Noise) |
| gemma-4-e2b | math500 | **P2 vs P1** | 2 | 100.0% | 50.0% | +50.00 | 1 : 0 | 1.0000e+00 | 3.0 | NO (Parity / Noise) |