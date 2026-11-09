# Pre-Registered 2D Hazard-Scaled Web Evidentiary Burden & Live 4-Model GGUF Benchmark (`N = 360` Stratified + `288` Live 4-Model Turns)

- **Preregistration ID:** `PREREG-WEB-BURDEN-360-4MODEL` (`logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`)
- **Dataset:** `data/benchmarks/web_evidentiary_burden_360.jsonl` (`N = 360`, `n = 30` per cell across `12` cells; SHA-256: `db685e70e65b40ba42be0e3ea2bbf54ac00b72ec6c69546faeabcff3b5574e13`)
- **Walton `Scheme.AUTHORITY` Legal Standard & Multi-Source Topology (`CQ1..CQ3`):** **360/360 (100.00%)**, 95% Wilson CI: `[98.94%, 100.00%]` (`30/30` in all 12 cells, per-cell 95% CI `[88.65%, 100.00%]`; `1.06 ms` mean / `1.84 ms` P95)
- **NPU Conservative Safety Compliance ($\text{Predicted Hazard} \ge \text{Expected Hazard}$):** **360/360 (100.00%)**, 95% Wilson CI: `[98.94%, 100.00%]` (`5.23 ms` mean / `12.56 ms` P95)
- **Strict 3-Class End-to-End Match (Untouched Locked Code):** **287/360 (79.72%)**, 95% Wilson CI: `[75.27%, 83.55%]` vs Legacy Static-`0.85` Baseline `90/360 (25.00%)` (Discordant `217:20`, **McNemar $\chi^2 = 162.0928$, exact $p = 5.613e-43$**)
- **Live 4-Model GGUF Matrix (`E2B`, `E4B`, `12B`, `26B-A4B`, `288` Live Turns):** Arm B (`2D Burden-Gated`) **144/144 (100.0%, 95% CI `[97.4, 100.0]`)** vs Arm A (`Legacy Static-0.85`) `98/144 (68.06%)` (**McNemar $\chi^2 = 44.0217$, exact $p = 2.842e-14$**)

## 1. Blinded Code-Locked Stratified Matrix (`N = 360`, `n = 30` per Cell)

| Hazard Stratum ($n=120$) | Topology ($n=30$ each) | Achieved Confidence & Standard | Required (`casual` / `commit` / `unhedged`) | Legacy Static-`0.85` Pass | Walton Standard & Topology Pass (Cell 95% CI) | NPU Safe Hazard ($\ge$) | Strict 3-Class Exact Pass |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`LOW`** | 1 Uncorroborated / eTLD+1 Alias | `0.70` (`balance of probabilities`) | `0.50` / `0.75` / `0.75` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `26/30` |
| **`LOW`** | 2 Independent Domains | `0.80` (`clear and convincing`) | `0.50` / `0.75` / `0.75` | `30/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `16/30` |
| **`LOW`** | 3+ Independent Domains | `0.95` (`beyond reasonable doubt`) | `0.50` / `0.75` / `0.75` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `16/30` |
| **`LOW`** | Disputed Across Domains | `0.40` (`speculation`) | `0.50` / `0.75` / `0.75` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `13/30` |
| **`MEDIUM`** | 1 Uncorroborated / eTLD+1 Alias | `0.70` (`balance of probabilities`) | `0.75` / `0.75` / `0.95` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `24/30` |
| **`MEDIUM`** | 2 Independent Domains | `0.80` (`clear and convincing`) | `0.75` / `0.75` / `0.95` | `30/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `24/30` |
| **`MEDIUM`** | 3+ Independent Domains | `0.95` (`beyond reasonable doubt`) | `0.75` / `0.75` / `0.95` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `23/30` |
| **`MEDIUM`** | Disputed Across Domains | `0.40` (`speculation`) | `0.75` / `0.75` / `0.95` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `25/30` |
| **`HIGH`** | 1 Uncorroborated / eTLD+1 Alias | `0.70` (`balance of probabilities`) | `0.95` / `0.95` / `0.95` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `30/30` |
| **`HIGH`** | 2 Independent Domains | `0.80` (`clear and convincing`) | `0.95` / `0.95` / `0.95` | `30/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `30/30` |
| **`HIGH`** | 3+ Independent Domains | `0.95` (`beyond reasonable doubt`) | `0.95` / `0.95` / `0.95` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `30/30` |
| **`HIGH`** | Disputed Across Domains | `0.40` (`speculation`) | `0.95` / `0.95` / `0.95` | `0/30` | **`30/30`** (`[88.65%, 100.00%]`) | `30/30` | `30/30` |

## 2. Live 4-Model GGUF Epistemic Burden Compliance (`36 Prompts x 2 Arms x 4 Models = 288 Live Turns`)

| Local GGUF Checkpoint | RTX 5080 VRAM | Mean Turn Latency | Arm A: Legacy Static-`0.85` (`Hedge Req.` / `Burden Met`) | Arm B: 2D Burden-Gated (`Hedge Req.` / `Burden Met`) | Arm B 95% Wilson CI | McNemar $\chi^2$ ($p$-value) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `E2B` (`Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf`) | `2560.0 MB` | `0.47 s` | `24/36` (`7/18` / `17/18`) | **`36/36` (`100.0%`)** (`18/18` / `18/18`) | `[90.36%, 100.00%]` | `10.0833` (`4.88e-04`) |
| `E4B` (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`) | `4502.0 MB` | `0.58 s` | `23/36` (`7/18` / `16/18`) | **`36/36` (`100.0%`)** (`18/18` / `18/18`) | `[90.36%, 100.00%]` | `11.0769` (`2.44e-04`) |
| `12B` (`gemma-4-12b-heretic-Q6_K.gguf`) | `10620.0 MB` | `1.24 s` | `24/36` (`6/18` / `18/18`) | **`36/36` (`100.0%`)** (`18/18` / `18/18`) | `[90.36%, 100.00%]` | `10.0833` (`4.88e-04`) |
| `26B-A4B` (`gemma-4-26B-A4B-it-heretic.Q6_K.gguf`) | `11102.0 MB` | `1.31 s` | `27/36` (`9/18` / `18/18`) | **`36/36` (`100.0%`)** (`18/18` / `18/18`) | `[90.36%, 100.00%]` | `7.1111` (`3.91e-03`) |
| **Pooled 4-Model Total (`288` Turns)** | `0.0 MB` NPU overhead | --- | `98/144` (`68.06%`) | **`144/144` (`100.0%`)** | `[97.40%, 100.00%]` | **`44.0217` (`2.84e-14`)** |
