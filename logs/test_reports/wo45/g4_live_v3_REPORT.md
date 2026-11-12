# WO-45 Gate G4 v3 Pre-Registered Live Evaluation Report

- **Generated (UTC):** `2026-11-12T08:55:38.395127+00:00`
- **Pre-Registration Lock SHA-256:** `438e70041eb9de50b8e0fc63276c04e8ece004f091275a29ebbc3ff76523c5a0`
- **Pre-Unblinding Judge-3 Upgrade Amendment SHA-256:** `88a6fa8a871c1874ddb96c28f91ccdc5eb8dd966282200f5fc9b5a65bef2be96`
- **Active Hazard Classifier (`RM-7`):** `models/proof_policy_hazard_ov`
- **Design:** `N = 132` fresh stratified `WEB360` items (`0` overlap with `v2`; `11/cell`, `33` disputed) x `5` Gemma-4 `Q6_K` models (`4 heretic` + `1 stock E4B-it`) x `4` arms (`A`, `B`, `C`, `D`) = `2,640` live turns at `ctx=32768`.
- **Judges (`RM-2` 3 Qualified Non-Google Families, Machine-Logged `T=0, seed=42`):** `J1` `Qwen3.8-27B-Ridge-GGUF` (`Alibaba-Qwen`), `J2` `phi-4-Q6_K` (`Microsoft-Phi`), `J3` `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL` (`NVIDIA-Nemotron`).
- **Disputed-Population `D4` Judge-Robustness Check (`kappa >= 0.60` all pairs):** Primary Normalized = `True` (min `kappa = 0.6983`); Secondary Raw = `True` (min `kappa = 0.7152`).

## 1. Endpoint-Population Inter-Judge Agreement (`RM-9`)

| Pool | Endpoint & Scored Population | `Qwen3.8` vs `Phi-4` | `Qwen3.8` vs `Nemotron-3.5-30B` | `Phi-4` vs `Nemotron-3.5-30B` |
|---|---|---:|---:|---:|
| Primary Normalized | `D4` (`660` disputed turns ONLY) | `0.8587` (`94.24%`) | `0.7154` (`88.94%`) | `0.6983` (`89.24%`) |
| Primary Normalized | `D3` (`1,320` nominal burden-met turns ONLY) | `0.8846` (`98.26%`) | `0.8811` (`98.18%`) | `0.9177` (`98.86%`) |
| Primary Normalized | `D2` unfaithful `YES` (`2,640` turns) | `0.2494` (`97.42%`) | `0.123` (`89.77%`) | `0.121` (`90.61%`) |
| Primary Normalized | `D2` faithful substantive (`2,640` turns) | `0.7619` (`97.31%`) | `0.445` (`89.43%`) | `0.4599` (`90.23%`) |
| Primary Normalized | `D1` 3-class (`2,640` turns) | `0.4005` (`88.86%`) | `0.3451` (`87.23%`) | `0.331` (`92.65%`) |
| Secondary Raw | `D4` (`660` disputed turns ONLY) | `0.8627` (`94.39%`) | `0.7189` (`88.94%`) | `0.7152` (`89.7%`) |
| Secondary Raw | `D3` (`1,320` nominal burden-met turns ONLY) | `0.8667` (`97.8%`) | `0.784` (`96.44%`) | `0.8084` (`97.12%`) |
| Secondary Raw | `D2` unfaithful `YES` (`2,640` turns) | `0.1396` (`92.54%`) | `0.0335` (`84.09%`) | `0.0994` (`89.28%`) |
| Secondary Raw | `D2` faithful substantive (`2,640` turns) | `0.5367` (`92.54%`) | `0.3015` (`83.67%`) | `0.4284` (`88.94%`) |
| Secondary Raw | `D1` 3-class (`2,640` turns) | `0.3322` (`85.57%`) | `0.3139` (`84.24%`) | `0.2726` (`90.8%`) |

## 2. Co-Primary 1: `D4` Conflict Disclosure on Disputed Items (`N_eff = 33` items, `165` turns/arm)

| Pool & Contrast | Arm Hi (`k/N, % [Item-Boot 95% CI]`) | Arm Lo (`k/N, % [Item-Boot 95% CI]`) | Cluster-Bootstrap Delta (`[95% CI]`) | Bootstrap `p` | Discordant |
|---|---|---|---|---:|---:|
| Primary Normalized `D vs C` (Detector Signal Alone) | `164/165 (99.39%)` `[98.18, 100.0]` | `85/165 (51.52%)` `[38.79, 63.64]` | `+47.88 pp` `[36.36, 60.0]` | `0.0001` | `79:0` |
| Primary Normalized `B vs D` (Mandate + Legal Vocab) | `165/165 (100.0%)` `[100.0, 100.0]` | `164/165 (99.39%)` `[98.18, 100.0]` | `+0.61 pp` `[0.0, 1.82]` | `0.7214` | `1:0` |
| Primary Normalized `B vs C` (Full Gate vs Generic Tip) | `165/165 (100.0%)` `[100.0, 100.0]` | `85/165 (51.52%)` `[38.79, 63.64]` | `+48.48 pp` `[36.36, 61.21]` | `0.0001` | `80:0` |
| Primary Normalized `B vs A` (Full Gate vs Plain Baseline) | `165/165 (100.0%)` `[100.0, 100.0]` | `61/165 (36.97%)` `[25.45, 49.09]` | `+63.03 pp` `[50.91, 75.15]` | `0.0001` | `104:0` |
| Primary Normalized `D vs A` (Contract Context + C Prompt vs Baseline) | `164/165 (99.39%)` `[98.18, 100.0]` | `61/165 (36.97%)` `[25.45, 49.09]` | `+62.42 pp` `[50.3, 73.94]` | `0.0001` | `103:0` |
| Primary Normalized `C vs A` (Generic Tip vs Plain Baseline) | `85/165 (51.52%)` `[38.79, 64.24]` | `61/165 (36.97%)` `[24.85, 49.09]` | `+14.55 pp` `[7.27, 22.42]` | `0.0002` | `29:5` |
| Secondary Raw `D vs C` (Detector Signal Alone) | `164/165 (99.39%)` `[98.18, 100.0]` | `85/165 (51.52%)` `[38.18, 64.24]` | `+47.88 pp` `[35.15, 60.61]` | `0.0001` | `79:0` |
| Secondary Raw `B vs D` (Mandate + Legal Vocab) | `165/165 (100.0%)` `[100.0, 100.0]` | `164/165 (99.39%)` `[98.18, 100.0]` | `+0.61 pp` `[0.0, 1.82]` | `0.7214` | `1:0` |
| Secondary Raw `B vs C` (Full Gate vs Generic Tip) | `165/165 (100.0%)` `[100.0, 100.0]` | `85/165 (51.52%)` `[38.79, 64.24]` | `+48.48 pp` `[35.76, 61.21]` | `0.0001` | `80:0` |
| Secondary Raw `B vs A` (Full Gate vs Plain Baseline) | `165/165 (100.0%)` `[100.0, 100.0]` | `61/165 (36.97%)` `[25.45, 49.09]` | `+63.03 pp` `[50.91, 74.55]` | `0.0001` | `104:0` |
| Secondary Raw `D vs A` (Contract Context + C Prompt vs Baseline) | `164/165 (99.39%)` `[98.18, 100.0]` | `61/165 (36.97%)` `[25.45, 49.09]` | `+62.42 pp` `[50.3, 73.94]` | `0.0001` | `103:0` |
| Secondary Raw `C vs A` (Generic Tip vs Plain Baseline) | `85/165 (51.52%)` `[38.18, 64.24]` | `61/165 (36.97%)` `[25.45, 49.09]` | `+14.55 pp` `[7.88, 22.42]` | `0.0001` | `28:4` |

## 3. Co-Primary 2 (`D2`) & Co-Primary 3 (`D1`) Primary Normalized Contrasts (`N_eff = 132` items, `660` turns/arm)

| Endpoint & Contrast | Arm Hi (`k/N, %`) | Arm Lo (`k/N, %`) | Cluster-Bootstrap Delta (`[95% CI]`) | Bootstrap `p` |
|---|---|---|---|---:|
| `D2` Unfaithful `YES` (lower better) `D_vs_C` | `12/660 (1.82%)` | `9/660 (1.36%)` | `+0.45 pp` `[-0.91, 1.82]` | `0.6032` |
| `D2` Unfaithful `YES` (lower better) `B_vs_D` | `9/660 (1.36%)` | `12/660 (1.82%)` | `-0.45 pp` `[-1.36, 0.45]` | `0.3958` |
| `D2` Unfaithful `YES` (lower better) `B_vs_C` | `9/660 (1.36%)` | `9/660 (1.36%)` | `+0.00 pp` `[-1.21, 1.36]` | `1.0` |
| `D2` Faithful Substantive (higher better) `D_vs_C` | `648/660 (98.18%)` | `612/660 (92.73%)` | `+5.45 pp` `[2.73, 8.33]` | `0.0001` |
| `D2` Faithful Substantive (higher better) `B_vs_D` | `650/660 (98.48%)` | `648/660 (98.18%)` | `+0.30 pp` `[-0.61, 1.21]` | `0.6294` |
| `D2` Faithful Substantive (higher better) `B_vs_C` | `650/660 (98.48%)` | `612/660 (92.73%)` | `+5.76 pp` `[3.03, 8.64]` | `0.0001` |
| `D1` `ACCURATE` Calibration `D_vs_C` | `643/660 (97.42%)` | `614/660 (93.03%)` | `+4.39 pp` `[1.82, 7.12]` | `0.0012` |
| `D1` `ACCURATE` Calibration `B_vs_D` | `628/660 (95.15%)` | `643/660 (97.42%)` | `-2.27 pp` `[-4.09, -0.61]` | `0.0108` |
| `D1` `ACCURATE` Calibration `B_vs_C` | `628/660 (95.15%)` | `614/660 (93.03%)` | `+2.12 pp` `[-0.61, 5.0]` | `0.1556` |
