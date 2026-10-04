# Project Lucca: Factorial PAL-Off Model-Scale Ablation Report
**Confidence Level:** 95% Wilson Score CI | **Sample Size:** $n=100$ per Cell

## 1. Factorial Performance Scorecard (Model Size x Scaffold Arm x Split)

| Model | Benchmark | Split | Arm & Cap | Strict Acc [95% Wilson CI] | Lenient Acc [95% Wilson CI] | Trunc (%) | Avg Tok | Latency (s) |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **gemma-4-12b** | gsm_symbolic | dev | **P2 @ 1k** | 95.0% [88.2%, 98.1%] | 95.0% [88.2%, 98.1%] | 2.0% | 340 | 6.68s |
| **gemma-4-12b** | gsm_symbolic | dev | **R0 @ 1.5k** | 93.0% [85.6%, 96.9%] | 93.0% [85.6%, 96.9%] | 0.0% | 386 | 7.54s |
| **gemma-4-12b** | math500 | dev | **P2 @ 1k** | 85.0% [76.2%, 91.1%] | 87.0% [78.4%, 92.6%] | 10.0% | 704 | 14.05s |
| **gemma-4-12b** | math500 | dev | **R0 @ 1.5k** | 90.0% [82.0%, 94.8%] | 93.0% [85.6%, 96.9%] | 6.0% | 660 | 12.88s |
| **gemma-4-12b** | math500 | dev | **R1** | 58.0% [47.7%, 67.7%] | 59.0% [48.7%, 68.6%] | 44.0% | 3793 | 78.11s |
| **gemma-4-12b** | math500 | heldout | **P2 @ 2k** | 86.0% [77.3%, 91.9%] | 90.0% [82.0%, 94.8%] | 5.0% | 937 | 19.41s |
| **gemma-4-12b** | math500 | heldout | **R0 @ 4k** | 89.0% [80.8%, 94.1%] | 94.0% [86.9%, 97.5%] | 3.0% | 803 | 9.02s |
| **gemma-4-e4b** | gsm_symbolic | dev | **R0 @ 1.5k** | 91.0% [83.2%, 95.5%] | 91.0% [83.2%, 95.5%] | 0.0% | 458 | 4.17s |
| **gemma-4-e4b** | gsm_symbolic | dev | **R1 @ 4k** | 86.0% [77.3%, 91.9%] | 86.0% [77.3%, 91.9%] | 1.0% | 1028 | 9.32s |
| **gemma-4-e4b** | math500 | dev | **P2 @ 2k** | 83.0% [73.9%, 89.5%] | 92.0% [84.4%, 96.2%] | 7.0% | 1070 | 10.06s |
| **gemma-4-e4b** | math500 | dev | **R0 @ 1.5k** | 50.0% [39.9%, 60.1%] | 50.0% [39.9%, 60.1%] | 16.0% | 841 | 7.69s |
| **gemma-4-e4b** | math500 | dev | **R0 @ 4k** | 52.0% [41.8%, 62.0%] | 52.0% [41.8%, 62.0%] | 1.0% | 978 | 9.89s |
| **gemma-4-e4b** | math500 | dev | **R1 @ 4k** | 85.0% [76.2%, 91.1%] | 86.0% [77.3%, 91.9%] | 13.0% | 1786 | 16.38s |
| **gemma-4-e4b** | math500 | heldout | **P2 @ 2k** | 73.0% [63.0%, 81.2%] | 83.0% [73.9%, 89.5%] | 8.0% | 1285 | 12.17s |
| **gemma-4-e4b** | math500 | heldout | **R0 @ 4k** | 52.0% [41.8%, 62.0%] | 54.0% [43.8%, 63.9%] | 1.0% | 1108 | 10.81s |
| **gemma-4-e4b** | math500 | heldout | **ROUTED** | 88.0% [79.6%, 93.4%] | 92.0% [84.4%, 96.2%] | 2.0% | 2067 | 19.31s |
| **gemma-4-e2b** | gsm_symbolic | dev | **P2 @ 1k** | 91.0% [83.2%, 95.5%] | 91.0% [83.2%, 95.5%] | 1.0% | 373 | 2.17s |
| **gemma-4-e2b** | gsm_symbolic | dev | **R0 @ 1.5k** | 81.0% [71.7%, 87.9%] | 81.0% [71.7%, 87.9%] | 2.0% | 546 | 2.86s |
| **gemma-4-e2b** | gsm_symbolic | dev | **R0 @ 1.5k** | 80.0% [29.9%, 99.0%] | 80.0% [29.9%, 99.0%] | 0.0% | 565 | 3.70s |
| **gemma-4-e2b** | gsm_symbolic | dev | **R1 @ 4k** | 85.0% [76.2%, 91.1%] | 85.0% [76.2%, 91.1%] | 0.0% | 1116 | 6.25s |
| **gemma-4-e2b** | math500 | dev | **P2 @ 1k** | 70.0% [59.9%, 78.5%] | 75.0% [65.2%, 82.9%] | 19.0% | 1079 | 6.26s |
| **gemma-4-e2b** | math500 | dev | **P2 @ 2k** | 77.0% [67.3%, 84.6%] | 85.0% [76.2%, 91.1%] | 10.0% | 1128 | 6.63s |
| **gemma-4-e2b** | math500 | dev | **P3** | 76.0% [66.2%, 83.7%] | 84.0% [75.0%, 90.3%] | 9.0% | 2752 | 16.43s |
| **gemma-4-e2b** | math500 | dev | **R0 @ 1.5k** | 51.0% [40.9%, 61.1%] | 51.0% [40.9%, 61.1%] | 26.0% | 949 | 5.34s |
| **gemma-4-e2b** | math500 | dev | **R0 @ 4k** | 57.0% [46.7%, 66.7%] | 57.0% [46.7%, 66.7%] | 6.0% | 1217 | 7.85s |
| **gemma-4-e2b** | math500 | dev | **R1 @ 4k** | 81.0% [71.7%, 87.9%] | 82.0% [72.8%, 88.7%] | 17.0% | 2031 | 11.47s |
| **gemma-4-e2b** | math500 | dev | **R1 @ 6k** | 84.0% [75.0%, 90.3%] | 85.0% [76.2%, 91.1%] | 9.0% | 2283 | 12.99s |
| **gemma-4-e2b** | math500 | heldout | **P2 @ 2k** | 61.0% [50.7%, 70.4%] | 70.0% [59.9%, 78.5%] | 14.0% | 1657 | 10.60s |
| **gemma-4-e2b** | math500 | heldout | **R0 @ 4k** | 51.0% [40.9%, 61.1%] | 55.0% [44.8%, 64.9%] | 4.0% | 1279 | 7.92s |
| **gemma-4-e2b** | math500 | heldout | **R1 @ 6k** | 81.0% [71.7%, 87.9%] | 86.0% [77.3%, 91.9%] | 10.0% | 2598 | 16.05s |

---

## 2. Paired McNemar Statistical Appendix (Strict Accuracy)

Evaluated strictly on identical problems within the same split ($n=100$). Column headers explicitly indicate direction of discordance.

| Model | Split | Comparison (Arm A vs Arm B) | Arm A Acc | Arm B Acc | Delta (pp) | Arm A Only (b) | Arm B Only (c) | Exact p-Value | Significant ($p < 0.05$) |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| gemma-4-12b | dev | **R0 @ 1.5k vs P2 @ 1k** | 90.0% | 85.0% | +5.0 | 8 | 3 | 2.2656e-01 | NO |
| gemma-4-12b | dev | **R0 @ 1.5k vs R1 @ 6k** | 90.0% | 58.0% | +32.0 | 32 | 0 | 4.6566e-10 | **YES** |
| gemma-4-12b | heldout | **R0 @ 4k vs P2 @ 2k** | 89.0% | 86.0% | +3.0 | 8 | 5 | 5.8105e-01 | NO |
| gemma-4-e4b | dev | **R1 @ 4k vs P2 @ 2k** | 85.0% | 83.0% | +2.0 | 8 | 6 | 7.9053e-01 | NO |
| gemma-4-e4b | dev | **R0 @ 4k vs R0 @ 1.5k** | 52.0% | 50.0% | +2.0 | 5 | 3 | 7.2656e-01 | NO |
| gemma-4-e4b | heldout | **R1 @ 6k vs P2 @ 2k** | 88.0% | 73.0% | +15.0 | 19 | 4 | 2.5995e-03 | **YES** |
| gemma-4-e4b | heldout | **P2 @ 2k vs R0 @ 4k** | 73.0% | 52.0% | +21.0 | 28 | 7 | 5.0826e-04 | **YES** |
| gemma-4-e4b | heldout | **R1 @ 6k vs R0 @ 4k** | 88.0% | 52.0% | +36.0 | 40 | 4 | 1.7051e-08 | **YES** |
| gemma-4-e2b | dev | **P2 @ 2k vs P2 @ 1k** | 77.0% | 70.0% | +7.0 | 7 | 0 | 1.5625e-02 | **YES** |
| gemma-4-e2b | dev | **R1 @ 4k vs P2 @ 2k** | 81.0% | 77.0% | +4.0 | 11 | 7 | 4.8068e-01 | NO |
| gemma-4-e2b | dev | **R0 @ 4k vs R0 @ 1.5k** | 57.0% | 51.0% | +6.0 | 10 | 4 | 1.7957e-01 | NO |
| gemma-4-e2b | heldout | **R1 @ 6k vs P2 @ 2k** | 81.0% | 61.0% | +20.0 | 24 | 4 | 1.7999e-04 | **YES** |
| gemma-4-e2b | heldout | **P2 @ 2k vs R0 @ 4k** | 61.0% | 51.0% | +10.0 | 23 | 13 | 1.3250e-01 | NO |
| gemma-4-e2b | heldout | **R1 @ 6k vs R0 @ 4k** | 81.0% | 51.0% | +30.0 | 33 | 3 | 2.2721e-07 | **YES** |

---

## 3. Cross-Split Generalization Analysis (Dev vs Held-Out)

Because problems differ between Dev and Held-Out, McNemar is invalid. We report independent two-proportion z-tests and Wilson 95% CIs:

| Model | Arm | Dev Strict Acc [95% CI] | Held-Out Strict Acc [95% CI] | Delta (pp) | z-Score | Two-Tailed p-Value | Generalization Assessment |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| gemma-4-12b | R0 (Direct) | 90.0% [82.0%, 94.8%] | 89.0% [80.8%, 94.1%] | -1.0 | 0.231 | 0.8176 | No statistically detectable difference |
| gemma-4-12b | P2 (PAL) | 85.0% [76.2%, 91.1%] | 86.0% [77.3%, 91.9%] | +1.0 | -0.201 | 0.8408 | No statistically detectable difference |
| gemma-4-e4b | R1 (Thinking) | 85.0% [76.2%, 91.1%] | 88.0% [79.6%, 93.4%] | +3.0 | -0.621 | 0.5348 | No statistically detectable difference |
| gemma-4-e4b | P2 (PAL) | 83.0% [73.9%, 89.5%] | 73.0% [63.0%, 81.2%] | -10.0 | 1.707 | 0.0878 | No statistically detectable difference |
| gemma-4-e2b | R1 (Thinking) | 81.0% [71.7%, 87.9%] | 81.0% [71.7%, 87.9%] | +0.0 | 0.000 | 1.0000 | No statistically detectable difference |
| gemma-4-e2b | P2 (PAL) | 77.0% [67.3%, 84.6%] | 61.0% [50.7%, 70.4%] | -16.0 | 2.446 | 0.0144 | Significant drop |