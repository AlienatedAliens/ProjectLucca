# Project Lucca — Evaluation Scorecard (`v1.51.0` / `WO-43`)

**Canonical Ledger Reference:** [`RESULTS.md`](../RESULTS.md) & [`luccadocs/funding/EVIDENCE_LEDGER.md`](./funding/EVIDENCE_LEDGER.md)
**Pre-Registration Git Tags:** `prereg-poisoning-v1`, `prereg-poisoning-v2`, `prereg-supervision-v1`, `prereg-supervision-v2`, `prereg-wo43-power-300`
**Updated:** 2026-11-08 (`v1.51.0` / Work Order 43)

This scorecard consolidates Project Lucca's pre-registered empirical benchmarks, sample sizes ($N$), 95% Wilson confidence intervals, exact McNemar $p$-values, and inter-rater reliability ($\kappa$) after the Work Order 43 ($N=300$) statistical power expansion.

---

## 1. Pre-Registered Safety & Grounding Batteries (`WO-42` & `WO-43`)

| Evaluation Battery | Pre-Registration Tag / Spec | Sample Size ($N$) | Primary Result (`[95% Wilson CI]`) | Statistical Significance & IRR | Artifact Path |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Memory Poisoning & Misinformation Ablation v3 (`WO-43`)** | `prereg-wo43-power-300`<br>[`05_PHASE5_STATISTICAL_POWER_EXPANSION_SPEC.md`](../plans/wo43_refactor_and_power/05_PHASE5_STATISTICAL_POWER_EXPANSION_SPEC.md) | $N = 300$<br>($100$ Cohort A, $100$ Cohort B, $100$ Cohort C $\times 5$ arms) | • Cohort A Poisoning: **`0/100 (0.0% [0.00%, 4.61%])`**<br>• Cohort A Continuity: **`100/100 (100.0% [95.39%, 100.00%])`**<br>• Cohort B Retention: **`100/100 (100.0% [95.39%, 100.00%])`**<br>• Cohort C Misinformation: **`0/100 (0.0% [0.00%, 4.61%])`** | • vs. Naive RAG (`100/100`): $p = 4.16 \times 10^{-23}$<br>• vs. Passive Soft Tagging (`11/100`): $p = 9.77 \times 10^{-4}$<br>• Primary vs. NLI $\kappa = 0.9850$<br>• Dual Blinded Judge $\kappa = 0.9206$ (`58/60`) | [`logs/test_reports/memory_poisoning_v3_300_results.json`](../logs/test_reports/memory_poisoning_v3_300_results.json) |
| **Contrastive Companion Battery v2 (`WO-43`)** | `prereg-wo43-power-300`<br>[`05_PHASE5_STATISTICAL_POWER_EXPANSION_SPEC.md`](../plans/wo43_refactor_and_power/05_PHASE5_STATISTICAL_POWER_EXPANSION_SPEC.md) | $N = 300$<br>($100$ Recall, $100$ Introspection, $100$ Abstention $\times 3$ arms) | • Recall: **`99/100 (99.0% [93.8%, 100.0%])`**<br>• Introspection: **`95/100 (95.0% [88.2%, 98.1%])`**<br>• Abstention: **`90/100 (90.0% [82.0%, 94.8%])`** | • Recall vs. Bare (`5%`): $p_{\text{HB}} = 7.76 \times 10^{-21}$; vs. RAG (`86%`): $p_{\text{HB}} = 0.00684$<br>• Introspection vs. Bare (`92%`): $p_{\text{HB}} = 0.6563$; vs. RAG (`99%`): $p_{\text{HB}} = 0.6563$<br>• Abstention vs. Bare (`94%`): $p_{\text{HB}} = 0.6563$; vs. RAG (`100%`): $p_{\text{HB}} = 0.0117$ | [`logs/test_reports/contrastive_v2_300_results.json`](../logs/test_reports/contrastive_v2_300_results.json) |
| **Single-Pass Locked Holdout Supervision & Routing (`WO-42`)** | SHA-256 Code + NPU Weight Manifest | $N = 150$<br>($50$ Coherence, $50$ Hazard, $50$ Router) | • Single-Pass Locked: **`145/150 (96.67% [92.43%, 98.57%])`**<br>• Post-Router-Fix: **`150/150 (100.0% [97.50%, 100.00%])`** | • Coherence `50/50 (100.0%)`<br>• Hazard `50/50 (100.0%)`<br>• Blinded Judge IRR $\kappa = 1.000$ | [`logs/test_reports/wo42_locked_holdout_150_report.json`](../logs/test_reports/wo42_locked_holdout_150_report.json) |
| **Blind Multi-Sentence Supervision & Routing (`WO-42`)** | Zero-Training-Access Subagents | $N = 390$<br>(`BLIND42_300` + `BLIND_90`) | • Aggregate: **`377/390 (96.67% [94.38%, 98.04%])`**<br>• Coherence: **`130/130 (100.0%)`**<br>• Hazard: **`125/130 (96.15%, 100% HIGH recall)`**<br>• Router: **`122/130 (93.85%)`** | • `BLIND_90` lift `69/90 -> 86/90`, exact McNemar $p = 0.000121$<br>• Blinded Judge IRR $\kappa = 1.000$ | [`logs/test_reports/wo42_statistical_power_and_ci_report.json`](../logs/test_reports/wo42_statistical_power_and_ci_report.json) |
| **Large-Sample Paper 2 + Organic Action-Claim Re-Audit (`WO-42`)** | Pooled Held-Out Corpus | $N = 2,022$<br>($471$ positive, $1,551$ negative) | • Accuracy: **`2,007/2,022 (99.26% [98.78%, 99.55%])`**<br>• Recall: **`465/471 (98.73% [97.25%, 99.42%])`**<br>• FPR: **`9/1,551 (0.58% [0.31%, 1.10%])`** | vs. `WO-40` regex v3.0 (`71.5% [337/471]` recall) | [`logs/test_reports/wo42_large_sample_2020_report.json`](../logs/test_reports/wo42_large_sample_2020_report.json) |
| **Live 4-Model End-to-End Companion Matrix (`WO-42`)** | `E2B`, `E4B`, `12B`, `26B-A4B` | $N = 100$<br>($25$ live turns/model) | • Coherence: **`100/100 (100.0% [96.30%, 100.00%])`**<br>• Task/Reasoning: **`98/100 (98.0% [93.00%, 99.45%])`** | • `0.0 MB` dGPU VRAM overhead on Intel NPU<br>• Blinded Judge IRR $\kappa = 1.000$ | [`logs/test_reports/wo42_live_4model_summary.json`](../logs/test_reports/wo42_live_4model_summary.json) |

---

## 2. Static Architecture, Quality & Test Verification (`WO-43`)

| Gate / Suite | Command | Verified Result (`v1.51.0`) |
| :--- | :--- | :--- |
| **Static Architectural & Hygiene Gates** | `uv run pytest tests/test_static_gates.py -v` | **`39 passed`** (`0` NLI fail-open consumers across 8 modules, `198` reachable production modules via `test_all_src_modules_transitively_reachable_from_runtime`, `0` AI slop matches) |
| **Layered Import Contracts** | `uv run lint-imports` | **`7 contracts kept, 0 broken`** (`198` files, `683` dependencies) |
| **Static Linter (`ruff`)** | `uv run ruff check src tests` | **`0 errors`** (`All checks passed!`) |
| **Static Type Checker (`mypy`)** | `uv run mypy src` | **`0 errors`** (`Success: no issues found in 198 source files`) |
| **Fast Automated Test Suite** | `uv run pytest tests/ -q -m "not tier2 and not hw and not soak"` | **`1,754 passed, 1 skipped, 0 failed`** |
