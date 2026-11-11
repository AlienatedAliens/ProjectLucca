# WO-45 Gate G4 Pre-Registered Live v2 Evaluation Report

- **Generated (UTC):** `2026-11-11T00:13:10.229462+00:00`
- **Pre-Registration Lock SHA-256:** `ee379f91ddc064c22040080c8c8468b9ef2dab9f50454cea9c8216cbf44580c5`
- **Design:** `N = 132` unconditioned stratified items (`11/cell`) x `5` models (`4 heretic` + `1 stock E4B-it Q6_K`) x `3` arms (`A`, `B`, `C`) = `1,980` live turns at `ctx=32768`.
- **Judges (`G4-2` 3 Distinct Model Families):** Judge 1 `Google Gemini` (`gemini-2.5-flash` subagent), Judge 2 `Mistral AI` (`Mistral-Nemo-Instruct-2407-Q5_K_M`), Judge 3 Adjudicator `Alibaba Qwen` (`Qwen3.8-27B-Ridge-GGUF`).

## 1. Inter-Judge Agreement (`G4-2`)

| Pool | Dimension | J1 vs J2 3-Class Kappa | J1 vs J2 Binary Kappa | Raw Agreement (%) |
|---|---|---:|---:|---:|
| Unredacted | `D1` | `0.0493` | `0.0686` | `84.04%` (`1664/1980`) |
| Unredacted | `D2` | `0.1355` | `0.1845` | `94.24%` (`1866/1980`) |
| Unredacted | `D3` | `0.0055` | `0.0317` | `24.29%` (`481/1980`) |
| Unredacted | `D4` | `0.7657` | `0.7394` | `90.86%` (`1799/1980`) |
| Redacted `[STANDARD]` | `D1` | `0.0645` | `0.0959` | `86.26%` (`1708/1980`) |
| Redacted `[STANDARD]` | `D2` | `0.1169` | `0.1469` | `93.28%` (`1847/1980`) |
| Redacted `[STANDARD]` | `D3` | `0.0099` | `0.0738` | `25.25%` (`500/1980`) |
| Redacted `[STANDARD]` | `D4` | `0.7883` | `0.7589` | `91.67%` (`1815/1980`) |

## 2. Co-Primary Endpoint 1: `D4` Conflict Disclosure on Disputed Items (`N_eff = 33` items, `165` turns/arm)

| Pool & Contrast | Arm Hi (`k/N, % [95% CI]`) | Arm Lo (`k/N, % [95% CI]`) | Cluster-Bootstrap Delta (`[95% CI]`) | Bootstrap `p` | Discordant |
|---|---|---|---|---:|---:|
| Unredacted `B vs C` (Gate vs Generic Instruction) | `163/165 (98.79%)` `[95.69, 99.67]` | `121/165 (73.33%)` `[66.11, 79.49]` | `+25.45 pp` `[15.76, 35.76]` | `0.0001` | `43:1` |
| Unredacted `B vs A` (Gate vs Plain Baseline) | `163/165 (98.79%)` `[95.69, 99.67]` | `104/165 (63.03%)` `[55.45, 70.02]` | `+35.76 pp` `[25.45, 46.67]` | `0.0001` | `61:2` |
| Unredacted `C vs A` (Instruction vs Plain Baseline) | `121/165 (73.33%)` `[66.11, 79.49]` | `104/165 (63.03%)` `[55.45, 70.02]` | `+10.30 pp` `[-0.61, 20.61]` | `0.0668` | `32:15` |
| Redacted `[STANDARD]` `B vs C` | `163/165 (98.79%)` `[95.69, 99.67]` | `129/165 (78.18%)` `[71.28, 83.8]` | `+20.61 pp` `[12.12, 30.3]` | `0.0001` | `35:1` |
| Redacted `[STANDARD]` `B vs A` | `163/165 (98.79%)` `[95.69, 99.67]` | `107/165 (64.85%)` `[57.3, 71.72]` | `+33.94 pp` `[24.24, 44.24]` | `0.0001` | `58:2` |

## 3. Co-Primary Endpoint 2: `D2` Factual Correctness (`N_eff = 132` items, `660` turns/arm)

| Contrast | Arm Hi (`k/N, % [95% CI]`) | Arm Lo (`k/N, % [95% CI]`) | Cluster-Bootstrap Delta (`[95% CI]`) | Bootstrap `p` |
|---|---|---|---|---:|
| Unredacted `B vs C` | `656/660 (99.39%)` `[98.45, 99.76]` | `629/660 (95.3%)` `[93.41, 96.67]` | `+4.09 pp` `[1.67, 6.82]` | `0.0004` |
| Unredacted `B vs A` | `656/660 (99.39%)` `[98.45, 99.76]` | `593/660 (89.85%)` `[87.31, 91.93]` | `+9.55 pp` `[6.21, 13.18]` | `0.0001` |
