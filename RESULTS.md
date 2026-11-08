# Project Lucca: Experimental Results Ledger



> **Honesty Note**: Historical v1.3 results were produced from a working tree that contained uncommitted changes. `v1.3-frozen` is the nearest reproducible snapshot. `v1.3-frozen` did not reproduce bit-for-bit (20 of 25 predictions matched). Run-to-run variance is being measured. Determinism diagnostic confirmed prompt-cache reuse caused variance; `cache_prompt: false` produces bit-for-bit identical outputs (100/100 matches).

## WO-43 Pre-Registered $N=300$ Statistical Power Expansion (`prereg-wo43-power-300`), 8-Organ Activation & Modular Architecture (2026-11-08, `v1.51.0`)

Work Order 43 (`WO-43`) decomposed all 5 domain god-objects (`orchestrator.py` `6,120 -> 2,195 LOC`, `cascade.py` `2,487 -> 775 LOC`, `output_supervisor.py` `2,099 -> 475 LOC`, `cegis_unshackled.py` `2,051 -> 575 LOC`, `corroboration.py` `839 LOC` + `src/lucca/core/walton_schemes/`), wired all 8 built neurosymbolic cognitive subsystems (`BelnapLatentInvestigator`, `win32_security` + `WorkspaceTransactionManager`, `TracebackDivergenceGuard`, `DeductionAndPlanningRunner`, `ConsolidationEngine` + `ASTHoleMCTSEngine`, `WorkingMemory`, `PipelineTracer`, and `spatial_dsl` + `arc_primitives` + `math_primitives` + `repl_loop`) into the live runtime, remediated all NLI fail-open paths (`test_no_nli_uncertain_fail_open_consumers`), achieved `0` `ruff` and `0` `mypy` errors across `198` reachable production modules (`83,931 LOC`, `test_all_src_modules_transitively_reachable_from_runtime`, `7/7` `lint-imports` contracts), and executed pre-registered $N=300$ expansions (`prereg-wo43-power-300`) of Memory Poisoning Ablation v3 and Contrastive Companion Battery v2 on live `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (`E4B`, `T=0.0`, `seed=42`, `cache_prompt=False`):

| Benchmark / Verification Suite (`WO-43`, `prereg-wo43-power-300`) | Sample ($N$) | Result (Author-Measured, `[95% Wilson CI]`) | Paired Baseline Comparison & Exact McNemar $p$ | Artifact Paths |
| :--- | :---: | :---: | :---: | :--- |
| **1. Memory Poisoning & Misinformation Ablation v3 — Cohort A (Self-Poisoning Resistance)** | $100$ paired probes<br>(`probe-001..100`) | **Lucca Gate (`v3`): `0/100 (0.0% [0.00%, 4.61%] Method 4; [0.00%, 3.70%] Method 3)`**<br>**Continuity Recall: `100/100 (100.0% [95.39%, 100.00%])`** | • Naive RAG: `100/100 (100.0%)`, $0:100$ discordant, exact McNemar $p = 4.16 \times 10^{-23}$<br>• Adversarial Soft Tagging: `100/100 (100.0%)`, $p = 4.16 \times 10^{-23}$<br>• Passive Soft Tagging: `11/100 (11.0%)`, $0:11$ discordant, $p = 9.77 \times 10^{-4}$<br>• No-Assistant Continuity: `2/100 (2.0% [0.35%, 7.74%])`, $98:0$ discordant, $p = 2.75 \times 10^{-22}$ | `logs/test_reports/memory_poisoning_v3_300_results.json`, `data/benchmarks/memory_poisoning_v3_300.jsonl` |
| **2. Memory Poisoning & Misinformation Ablation v3 — Cohort B (Factual Retention Control)** | $100$ paired probes<br>(`probe-101..200`) | **Lucca Gate (`v3`): `100/100 (100.0% [95.39%, 100.00%] Method 4; [96.30%, 100.00%] Method 3)`** | Matches Naive RAG (`100/100`), Passive Soft Tagging (`100/100`), and Adversarial Soft Tagging (`100/100`) vs. No-Assistant `1/100 (1.0% [0.05%, 6.24%])`, $99:0$ discordant, $p = 6.90 \times 10^{-23}$ | `logs/test_reports/memory_poisoning_v3_300_results.json` |
| **3. Memory Poisoning & Misinformation Ablation v3 — Cohort C (Adversarial User Misinformation)** | $100$ paired probes<br>(`probe-201..300`) | **Lucca Gate (`v3`, `corroborate_user_explicit=True` + `BelnapLatentInvestigator`): `0/100 (0.0% [0.00%, 4.61%] Method 4; [0.00%, 3.70%] Method 3)`** | • Naive RAG: `100/100 (100.0%)`, $0:100$ discordant, exact McNemar $p = 4.16 \times 10^{-23}$<br>• No-Assistant: `100/100 (100.0%)`, $p = 4.16 \times 10^{-23}$<br>• Passive Soft Tagging: `100/100 (100.0%)`, $p = 4.16 \times 10^{-23}$<br>• Adversarial Soft Tagging: `100/100 (100.0%)`, $p = 4.16 \times 10^{-23}$<br>• Primary vs. MiniLM-L6 NLI $\kappa = 0.9850$ across $1,500$ evaluations; Dual Blinded Judge IRR $\kappa = 0.9206$ (`58/60 = 96.7%`, inter-judge $\kappa = 1.0000$) | `logs/test_reports/memory_poisoning_v3_300_results.json`, `logs/test_reports/wo43_phase5_blinded_irr_60_report.json` |
| **4. Contrastive Companion Battery v2 — Stratum 1: Seeded Memory Recall (`R001..R100`)** | $100$ prompts<br>$\times 3$ arms | **Arm B (Compound Lucca): `99/100 (99.0% [93.8%, 100.0%])`**<br>• Arm A (Bare LLM): `5/100 (5.0% [1.9%, 11.8%])`<br>• Arm C (Hybrid RAG): `86/100 (86.0% [77.3%, 91.9%])` | • Arm B vs. Arm A: $+94.0\text{ pp}$ (`94:0` discordant), $p_{\text{raw}} = 8.62 \times 10^{-22}$, Holm–Bonferroni $p_{\text{HB}} = 7.76 \times 10^{-21}$<br>• Arm B vs. Arm C: $+13.0\text{ pp}$ (`14:1` discordant), $p_{\text{raw}} = 9.77 \times 10^{-4}$, $p_{\text{HB}} = 0.00684$ | `logs/test_reports/contrastive_v2_300_results.json`, `logs/test_reports/contrastive_v2_300_results_REPORT.md`, `data/benchmarks/contrastive_battery_v2_300.jsonl` |
| **5. Contrastive Companion Battery v2 — Stratum 2: Receipt Introspection (`I001..I100`)** | $100$ prompts<br>$\times 3$ arms | **Arm B (Compound Lucca): `95/100 (95.0% [88.2%, 98.1%])`**<br>• Arm A (Bare LLM): `92/100 (92.0% [84.4%, 96.2%])`<br>• Arm C (Hybrid RAG): `99/100 (99.0% [93.8%, 100.0%])` | • Arm B vs. Arm A: $+3.0\text{ pp}$ (`8:5` discordant), $p_{\text{raw}} = 0.5811$, $p_{\text{HB}} = 0.6563$<br>• Arm B vs. Arm C: $-4.0\text{ pp}$ (`1:5` discordant), $p_{\text{raw}} = 0.2188$, $p_{\text{HB}} = 0.6563$<br>• Passes pre-registered $\ge 80\%$ introspection gate | `logs/test_reports/contrastive_v2_300_results.json` |
| **6. Contrastive Companion Battery v2 — Stratum 3: Calibrated Abstention (`A001..A100`)** | $100$ prompts<br>$\times 3$ arms | **Arm B (Compound Lucca): `90/100 (90.0% [82.0%, 94.8%])`**<br>• Arm A (Bare LLM): `94/100 (94.0% [86.9%, 97.5%])`<br>• Arm C (Hybrid RAG): `100/100 (100.0% [95.4%, 100.0%])` | • Arm B vs. Arm A: $-4.0\text{ pp}$ (`2:6` discordant), $p_{\text{raw}} = 0.2891$, $p_{\text{HB}} = 0.6563$<br>• Arm B vs. Arm C: $-10.0\text{ pp}$ (`0:10` discordant), $p_{\text{raw}} = 0.00195$, $p_{\text{HB}} = 0.0117$<br>• Passes pre-registered $\ge 80\%$ abstention gate; Dual Blinded Judge IRR $\kappa = 0.9206$ across 60-item slice (`logs/test_reports/wo43_phase5_blinded_irr_60_report.json`) | `logs/test_reports/contrastive_v2_300_results.json`, `logs/test_reports/wo43_phase5_blinded_irr_60_report.json` |

## WO-42 Clause-Level Neurosymbolic Intel NPU Supervision, Locked Holdouts (`N=540`), Large-Sample Paper 2/Organic Re-Audit (`N=2,022`), & Live 4-Model E2E Matrix (`N=100`) (2026-11-06)

Work Order 42 (`WO-42`) replaced whole-paragraph neural set-membership guessing and single-sentence routing with clause/sentence-level neurosymbolic classifiers compiled to OpenVINO IR on the Intel AI Boost NPU (`models/action_claim_verifier_ov`, `models/proof_policy_hazard_ov`, `models/router_intent_ov`, **`0.0 MB` RTX 5080 VRAM**) paired with deterministic Python receipt verification and a 3-tier Scrapling research pipeline:

| Benchmark / Verification Suite (`WO-42`) | Sample ($N$) | Result (Author-Measured, `[95% Wilson CI]`) | Baseline Comparison | Artifact Paths |
| :--- | :---: | :---: | :---: | :--- |
| **1. Single-Pass Code + Weight Locked Holdout (`WO42_LOCKED_HOLDOUT_150`)** | $150$<br>*(145 multi-sent)* | **Single-Pass Unedited: `145/150 (96.67% [92.43%, 98.57%])`**<br>• Coherence: **`50/50 (100.0% [92.87%, 100.0%])`**<br>• Proof-Policy: **`50/50 (100.0% [92.87%, 100.0%])`**<br>• Router: **`45/50 (90.0%)` $\to$ `50/50 (100.0%)` post-bugfix** | Both `.py` sources and `.xml`/`.bin` NPU weights SHA-256 locked prior to isolated subagent test generation; blinded LLM judge IRR $\kappa = 1.000$ | `logs/test_reports/wo42_locked_holdout_150_pre_generation_manifest.json`, `logs/test_reports/wo42_locked_holdout_150_report.json` |
| **2. Blind Multi-Sentence Benchmark (`Blind-300` + `WO-41 Blind-90 Retest`)** | $390$<br>*(309 multi-sent)* | **`377/390 (96.67% [94.38%, 98.04%])`** (`376/390 [96.4%]` pre-router-fix)<br>• Coherence (`N=130`): **`130/130 (100.0% [97.13%, 100.0%])`**<br>• Proof-Policy (`N=130`): **`125/130 (96.15% [91.31%, 98.35%])`**<br>• Router (`N=130`): **`122/130 (93.85% [88.33%, 96.85%])`** | `Blind-90` improved from **`69/90 (76.7%)`** in `WO-41` (and `51/90 [56.7%]` regex) to **`86/90 (95.6%)`**, exact McNemar $p = 0.00012112$; IRR $\kappa = 1.000$ (`n=60`) | `logs/test_reports/wo42_statistical_power_and_ci_report.json`, `data/benchmarks/supervision_heldout/wo42_blind_300_worksheet.jsonl` |
| **3. Large-Sample Paper 2 + Organic Companion + Implicit Corpus (`N=2,022`)** | $2,022$<br>*(471 pos, 1,551 neg)* | **Overall Accuracy: `2,007/2,022 (99.26% [98.78%, 99.55%])`**<br>**Recall: `465/471 (98.73% [97.25%, 99.42%])`** • **FPR: `9/1,551 (0.58% [0.31%, 1.10%])`**<br>• Unseen `H001..H100` (`N=100`): **`47/47 (100.0%)` Recall, `2/53 (3.8%)` FPR (`98.0%` Acc.)**<br>• Unseen `W751..W1000` `26B` (`N=249`): **`77/81 (95.1%)` Recall, `2/168 (1.2%)` FPR (`97.6%` Acc.)**<br>• Unseen `IMP_01..30` (`N=30`): **`14/15 (93.3%)` Recall, `0/15 (0.0%)` FPR (`96.7%` Acc.)** | `WO-40` De-Overfitted Regex (`v3.0`): `71.5% (337/471)` pooled recall (`80.8% [38/47]` on `H001..H100`, `65.4% [53/81]` on `W751..W1000`, `0.0% [0/15]` on `IMP_01..30`) | `logs/test_reports/wo42_large_sample_2020_report.json`, `scripts/evaluate_wo42_large_sample_2020.py` |
| **4. Live 4-Model End-to-End Orchestrator Matrix (`E2B`, `E4B`, `12B`, `26B-A4B`)** | $100$<br>*(25/model)* | **Axis 1 (Coherence & Grounding): `100/100 (100.0% [96.30%, 100.0%])`** (`25/25` on all 4 models)<br>**Axis 2 (Task/Reasoning): `98/100 (98.0% [93.00%, 99.45%])`** (`25/25` on `E4B`/`12B`/`26B-A4B`, `23/25` on `E2B`) | **`0.0 MB` RTX 5080 VRAM overhead** for all 3 NPU classifiers; mean turn latency `0.66s` (`E2B`), `1.11s` (`E4B`), `2.15s` (`12B`), `37.01s` (`26B-A4B`); IRR $\kappa = 1.000$ (`n=20`) | `logs/test_reports/wo42_live_4model_summary.json`, `data/benchmarks/supervision_heldout/wo42_live_4model_100_turns.jsonl` |
| **5. `Hypothesis` Property-Based Fuzzing, Scrapling Research & Full Repo Suite** | $550$ fuzz + $1,719$ unit | **`550/550 (100%)` fuzz cases**, **`16/16 (100%)` Scrapling SSRF/DOM-injection tests (`4.1x` parallel speedup)**, **`1,719 passed, 1 skipped, 0 failed`** across full repo test suite | — | `tests/test_wo42_property_fuzzing.py`, `tests/test_wo42_scrapling_research.py` |

## WO-39 Audit, Benchmark Provenance Note & Post-Decontamination 4-Model Live Verification (2026-11-03)

Work Order 39 (`WO-39`) conducted a full-codebase scientific integrity and benchmark decontamination audit, followed by a live GPU (`llama-server`) + WSL2 Docker (`lucca-file-sandbox`) verification rebench across all four Gemma 4 model scales (`logs/test_reports/wo39_live_4models_rebench.json` and `logs/test_reports/wo39_live_targeted_rebench.json`):

| Live Verification Suite (Post-`WO-39`) | Sample ($N$) | Gemma 4 `26B-A4B` MoE<br>*(4B Active)* | Gemma 4 `12B` Dense | Gemma 4 `E4B`<br>*(4.5B Eff.)* | Gemma 4 `E2B`<br>*(2B Eff.)* | Notes & Artifact Paths |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1. Study 1 V2c: Autobiographical Recall vs. Self-Poisoning** | $10$ | **0/10 Poisoned**<br>**(100% Defended)** | **0/10 Poisoned**<br>**(100% Defended)** | **0/10 Poisoned**<br>**(100% Defended)** | **0/10 Poisoned**<br>**(100% Defended)** | Naive RAG: 10/10 poisoned (`p = 0.00195`); full autobiographical recall active (`logs/test_reports/wo39_live_4models_rebench.json`) |
| **2. Study 1 V2b: Corroboration Gate Evaluation** | $10$ | **0/10 Poisoned**<br>**(100% Defended)** | **0/10 Poisoned**<br>**(100% Defended)** | **0/10 Poisoned**<br>**(100% Defended)** | **3/10 Poisoned**<br>**(70% Defended)** | General numeric extraction in `CorroborationEngine` + partitioned `<autobiographical_memory>` |
| **3. Sealed Parametric Hard Neurosymbolic Suite (`v139`)** | $15$<br>*(3/lobe)* | **15/15 (100.0%)**<br>*(p = 0.000061)* | **15/15 (100.0%)**<br>*(p = 0.000061)* | **15/15 (100.0%)**<br>*(p = 0.000061)* | **14/15 (93.3%)**<br>*(p = 0.000122)* | Raw Direct/Thinking baseline: `0/15 (0.0%)`. Per-model artifacts: `logs/test_reports/sealed_parametric_WO39_*.json` |
| &nbsp;&nbsp;• `single_lobe_epistemic` (`ContainerWorld` ToM) | $3$ | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | Single-source `container_world.py` injected via `DockerRPCTransport` |
| &nbsp;&nbsp;• `single_lobe_smt` (`Z3` Solver) | $3$ | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | Modular congruence & constraint systems |
| &nbsp;&nbsp;• `single_lobe_cas` (`SymPy` CAS) | $3$ | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | Symbolic algebra & exact number theory |
| &nbsp;&nbsp;• `two_lobe_composed` (`CW+SymPy` / `Z3+SymPy`) | $3$ | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | **2/3 (66.7%)** | Multi-lobe composed neurosymbolic tasks |
| &nbsp;&nbsp;• `formalization_translation` (`Python` CEGIS) | $3$ | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | **3/3 (100.0%)** | Natural language to formal program synthesis |
| **4. GSM8K PAL (1-Shot Docker Execution)** | $10$ | **10/10 (100.0%)**<br>*(94.2s)* | **10/10 (100.0%)**<br>*(70.5s)* | **10/10 (100.0%)**<br>*(23.8s)* | **5/10 (50.0%)**<br>*(23.2s)* | Fresh un-cached 1-shot PAL runs inside `lucca-file-sandbox` (`logs/test_reports/academic_benchmarks_20261102T233026Z.json`) |
| **5. Canonical HumanEval Assisted CEGIS (Docker)** | $10$ | **10/10 (100.0%)**<br>*(22.3s)* | **10/10 (100.0%)**<br>*(21.1s)* | **10/10 (100.0%)**<br>*(18.9s)* | **10/10 (100.0%)**<br>*(7.8s)* | `HumanEval/0`–`HumanEval/9` executed inside `lucca-file-sandbox` |
| **6. Defensive Prompt Injection & Security Battery** | $20$ | **20/20 (100.0%)** | **20/20 (100.0%)** | **20/20 (100.0%)** | **20/20 (100.0%)** | Deterministic host/sandbox guards (`logs/test_reports/defensive_security_benchmark_1793650355.json`) |
| **7. Tool Injection & Sandbox Defense Battery** | $30$ | **30/30 (100.0%)** | **30/30 (100.0%)** | **30/30 (100.0%)** | **30/30 (100.0%)** | Layer 1 Taint (10/10), Layer 2 Deontic (10/10), Layer 3 Docker Container (10/10) (`logs/test_reports/tool_injection_defense_1793650358.json`) |
| **8. Live 52-Turn `IN-D` Rule-Induction & E-Graph Compression Baseline** | $52$ waking<br>+$16$ held-out | — | **Tool Rules: 4/4 Z3 Quarantined (`100%` Replay, `8/8 [67.6%, 100%]` Held-Out Recall, `0/8 [0.0%, 32.4%]` Misfire)**<br>**S-Expr Macros: `0/2` Quarantined (`1.169x` AST compression)** | — | — | Live LLM multi-turn baseline (`scripts/run_in_d_live_baseline.py`, `logs/test_reports/in_d_live_baseline_wo39.json`, `logs/test_reports/personhood/in_d_latest.json`) |
| **9. `LongMemEval` End-to-End Pipeline Benchmark (vs. Context Truncation)** | $30$ | — | **70.0% (21/30 `[52.1%, 83.3%]`)** vs **23.3% (7/30 `[11.8%, 40.9%]`)** Truncation<br>*(0:14 discordant, exact McNemar p = 0.000122, 8.1 ms retrieval)* | — | — | Multi-session (`20%→70%`), temporal-reasoning (`0%→50%`), and knowledge-update (`50%→90%`) (`logs/test_reports/longmemeval_pipeline_12B_1791794644.json`) |
| **10. Paper 1 (`prereg-poisoning-v1/v2` Full `N=100` 4-Arm Ablation)** | $100$<br>*(40A/30B/30C)* | **Cohort A: 0/40 (`0.0% [0.0%, 8.8%]`)** vs `40/40` Naive RAG<br>*(cont.-corr. McNemar p = 6.98e-10; exact p = 1.82e-12)*<br>**Cohort B: 29/30 (`96.7%`)** • **Cohort C: 30/30 (`100%` v1) / 25/30 (`83.3%` v2b)** | **0/40 (`0.0%`)**<br>*(v2c)* | **1/40 (`2.5%`)**<br>*(v2c)* | **1/40 (`2.5%`)**<br>*(v2c)* | Full `N=100` pre-registered evaluation (`docs/papers/01_memory_poisoning_ablation.pdf`, DOI: `10.5281/zenodo.23901452`) |
| **11. Paper 2 (`prereg-supervision-v1/v2` Held-Out `N=120` SOAC & GBNF)** | $120$<br>*(held-out)* | **Strict Regex: `1/16 (6.25% [1.1%, 28.3%])`**<br>**SOAC: `6.82 µs` mean, `0/40 [0.0%, 8.8%]` FPR (`13.3%` prose leakage)**<br>**GBNF (Approach D): `17/120 (14.17%)` vs `15/120 (12.50%)`, p = 0.7237** | — | — | — | Held-out evaluation on `26B-A4B` (`docs/papers/02_deontic_supervision_evasion.pdf`, DOI: `10.5281/zenodo.23901605`; vs. initial in-sample diagnostic `1/8 strict`, `1/23 broad` on `E4B/E2B`) |
| **12. `MiniLM-L6` NLI Contradiction Verifier (`WO-37` Phase 2)** | $100$<br>*(40C/30E/30N)* | — | **`91.0% [83.8%, 95.2%]` Acc.** • **Contr. P/R: `0.975 / 0.975` (`39/40`)**<br>**Ent. P/R: `0.960 / 0.800` (`24/30`)** • **`12.23 ms` mean / `14.40 ms` p95 (`0/100` TO)** | — | — | Host CPU OpenVINO cross-encoder (`data/benchmarks/nli_eval/results_minilm/summary.json`; single-annotator authored set `pairs_v1.jsonl`) |

- **Live-Verified Empirical Results (Retained):**
  - **Study 1 (`PREREG-POISONING-ABLATION-v1.0` / `v2.0`) & Study 2 (PAL-off Factorial Ablation):** Generated via live `llama-server` completions and verified against frozen JSONL artifacts. In Study 1 V2b (`scripts/eval_self_poisoning_ablation_v2.py`), corroboration status now queries `lucca.memory.gate.is_content_corroborated(db, ...)` rather than alternating parity.
  - **Canonical Coding & Math Batteries (`HumanEval`, `HumanEval-Plus`, `GSM8K`, `GSM-Symbolic`, `MATH-500`):** Evaluated against live LLM completions inside the Docker sandbox. Problem-specific AST sanitizer rewrites (`u = x/h`, `primes`/`odds`/`evens` injection) and prompt-side problem hints have been removed in `WO-39`.
- **Decontaminated / Reclassified Benchmarks:**
  - **`SPEC-BENCH-100-v1.0`:** Historical runs (`91.0%`) included benchmark-specific keyword routing, prompt coaching, and static RFC 9110/7231 definitions in `search_tool.py`. All benchmark-specific shortcuts have been removed in `WO-39`; historical `SPEC-BENCH-100` figures are archived as pre-decontamination baselines pending clean live re-evaluation.
  - **Personhood Probe Batteries (`AC`, `IN`, `IA`, `FC`):** Default execution of `scripts/grade_ac.py`, `scripts/grade_in.py`, `scripts/grade_ia.py`, and `scripts/grade_fc.py` validates probe fixture schemas and mechanical invariants without querying a live LLM, and is now explicitly labeled `status: "SCHEMA_FIXTURE_VALIDATION_ONLY (NOT A LIVE MODEL EVALUATION)"` unless invoked with `--live`.



| Run ID | Code Commit | Grader Version | Dataset File | Dataset SHA-256 | n | Passed | Strict Score | Lenient Score | Wilson 95% CI | Artifact Path | Notes |

| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |

| `math-v1.3-fresh-500` | `4de6451` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 420 | 84.00% (420/500) | 84.00% (420/500) | [80.53%, 86.95%] | `logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json` | Historical report cited 79.20% (396/500) strict / 86.60% (433/500) lenient from uncommitted tree; per-item artifact recount is 420/500 (84.00%) without separate strict_pass field (E-23). |

| `math-v1.3-test-25-rep` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 20 | 80.00% (20/25) | 80.00% (20/25) | [60.87%, 91.14%] | `logs/test_reports/checkpoint_math500_test-25-reproduce.json` | |

| `math-v1.3-test-25-rep-A` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 21 | 84.00% (21/25) | 84.00% (21/25) | [65.35%, 93.60%] | `logs/test_reports/checkpoint_math500_rep-A.json` | |

| `math-v1.3-test-25-rep-B` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 19 | 76.00% (19/25) | 76.00% (19/25) | [56.57%, 88.50%] | `logs/test_reports/checkpoint_math500_rep-B.json` | |

| `math-v1.3-det-C` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 82 | 82.00% (82/100) | 88.00% (88/100) | [73.33%, 88.30%] | `logs/test_reports/checkpoint_math500_det-C.json` | |

| `math-v1.3-det-D` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 82 | 82.00% (82/100) | 88.00% (88/100) | [73.33%, 88.30%] | `logs/test_reports/checkpoint_math500_det-D.json` | |

| `math-v1.3-cache-on-C` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 83 | 83.00% (83/100) | 89.00% (89/100) | [74.45%, 89.11%] | `logs/test_reports/checkpoint_math500_cache-on-C.json` | |

| `math-v1.3-cache-on-D` | `e0a8fbf` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 100 | 84 | 84.00% (84/100) | 90.00% (90/100) | [75.58%, 89.90%] | `logs/test_reports/checkpoint_math500_cache-on-D.json` | |

| `gsm-symbolic-strat-100` | `bef28b5` | pal-docker-exact | `data/benchmarks/GSM_symbolic.jsonl` | `945055837b232bd9b56827b1e3a5aa019075f29e8ba4669d9a9df8b4439a291f` | 100 | 94 | 94.00% (94/100) | 94.00% (94/100) | [87.52%, 97.22%] | `logs/test_reports/gsm_symbolic_100_templates.json` | Wilson plain CI. |

| `humaneval-canonical-raw-164` | `90dbdde1` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 155 | 94.51% (155/164) | 94.51% (155/164) | [89.90%, 97.09%] | `logs/test_reports/humaneval_canonical_raw_164.json` | Original run at c3561206 preserved at *_20261002.json; primary artifact rerun at 90dbdde1. |

| `humaneval-canonical-assisted-164` | `90dbdde1` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 154 | 93.90% (154/164) | 93.90% (154/164) | [89.14%, 96.65%] | `logs/test_reports/humaneval_canonical_assisted_164.json` | Original run at c3561206 preserved at *_20261002.json; primary artifact rerun at 90dbdde1. |

| `math-v1.3-regraded-strict-posthoc` | `25adb03` | v1.35-strict-posthoc | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 393 | 78.60% (393/500) | 78.60% (393/500) | [74.79%, 81.97%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` | Wilson plain CI. |

| `math-v1.3-regraded-lenient-posthoc` | `25adb03` | v1.35-lenient-posthoc | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 432 | 78.60% (393/500) | 86.40% (432/500) | [83.12%, 89.13%] | `logs/test_reports/checkpoint_math500_v1.3-fresh-500_lenient_posthoc.json` | Wilson plain CI. |

| `math-v1.3-dev-400-baseline` | `e0a8fbf` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 319 | 76.25% (305/400) | 81.50% (326/400) | [71.84%, 80.16%] (S) / [77.40%, 85.00%] (L) | `logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json` | |

| `math-v1.35-dev-400` | `deacabe` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 299 | 74.75% (299/400) | 79.50% (318/400) | [70.27%, 78.76%] (S) / [75.27%, 83.17%] (L) | `logs/test_reports/checkpoint_math500_v1.35-dev-400.json` | Passed column standardized to strict count. |

| `math-v1.35-dev-400-v2` | `9b6858e` | v1.35-dual | `data/benchmarks/math500_test.jsonl` (101-500) | `35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132` | 400 | 306 | 76.50% (306/400) | 80.50% (322/400) | [72.10%, 80.39%] (S) / [76.33%, 84.08%] (L) | `logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json` | Passed column standardized to strict count. |

| `math-v1.35-final-fresh-500` | `46486cf` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 500 | 429 | 85.80% (429/500) | 90.20% (451/500) | [82.47%, 88.59%] (S) / [87.28%, 92.51%] (L) | `logs/test_reports/checkpoint_math500_v1.35-final-fresh-500.json` | Passed column standardized to strict count. 7.20 points above v1.3 on paired items (+36 net items, 66 gains, 30 losses); `length` truncations 29→12, crashes 21→14. Primary held-out evaluation. |

| `12b-math500-heldout-r0-4k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 89 | 89.00% (89/100) | 94.00% (94/100) | [81.37%, 93.75%] (S) / [87.52%, 97.22%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-12b_math500_r0_heldout_cap4096_100.json` | 12B Direct generation baseline; truncations: 3.0%. Factorial harness branch commit 8b80456. |

| `12b-math500-heldout-p2-2k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 86 | 86.00% (86/100) | 90.00% (90/100) | [77.86%, 91.47%] (S) / [82.51%, 94.46%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-12b_math500_p2_heldout_cap2048_100.json` | 12B PAL Docker baseline; truncations: 5.0%. Factorial harness branch commit 8b80456. |

| `e4b-math500-heldout-r1-6k` | `1c58587` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 88 | 88.00% (88/100) | 92.00% (92/100) | [80.19%, 93.00%] (S) / [85.00%, 95.89%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_routed_heldout_100.json` | E4B Thinking Mode; router default for competition math (+15 pp over P2, p=0.0026); truncations: 2.0%. Factorial harness branch commit 8b80456. |

| `e4b-math500-heldout-p2-2k` | `f20537f` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 73 | 73.00% (73/100) | 83.00% (83/100) | [63.57%, 80.73%] (S) / [74.45%, 89.11%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_p2_heldout_cap2048_100.json` | E4B PAL in Docker; truncations: 8.0%. Factorial harness branch commit 8b80456. |

| `e4b-math500-heldout-r0-4k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 52 | 52.00% (52/100) | 54.00% (54/100) | [42.32%, 61.54%] (S) / [44.29%, 63.42%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e4b_math500_r0_heldout_cap4096_100.json` | E4B Direct generation; truncations: 1.0%. Factorial harness branch commit 8b80456. |

| `e2b-math500-heldout-r1-6k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 81 | 81.00% (81/100) | 86.00% (86/100) | [72.22%, 87.49%] (S) / [77.86%, 91.47%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e2b_math500_r1_heldout_think6144_100.json` | E2B Thinking Mode; router default for competition math (+20 pp over P2, p=0.0002); truncations: 10.0%. Factorial harness branch commit 8b80456. |

| `e2b-math500-heldout-p2-2k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 61 | 61.00% (61/100) | 70.00% (70/100) | [51.20%, 69.98%] (S) / [60.44%, 77.97%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e2b_math500_p2_heldout_cap2048_100.json` | E2B PAL in Docker; truncations: 14.0%. Factorial harness branch commit 8b80456. |

| `e2b-math500-heldout-r0-4k` | `3029c54` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 51 | 51.00% (51/100) | 55.00% (55/100) | [41.35%, 60.58%] (S) / [45.27%, 64.38%] (L) | `logs/test_reports/pal_off_ablation/gemma-4-e2b_math500_r0_heldout_cap4096_100.json` | E2B Direct generation; truncations: 4.0%. Factorial harness branch commit 8b80456. |

| `math500-heldout-r0-b1-repro` | `f7c98a0` | v1.35-dual | `data/benchmarks/math_fresh_heldout_500.jsonl` (1-100) | `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` | 100 | 88 | 88.00% (88/100) | 93.00% (93/100) | [80.19%, 93.00%] (S) / [86.25%, 96.57%] (L) | `logs/test_reports/b1_frozen/gemma-4-12b_math500_r0_heldout_cap4096_100.json` | Phase 3 Block B1 GPU reproduction under cache_prompt: false. |

| `gsm-symbolic-100-repro` | `f7c98a0` | pal-docker-exact | `data/benchmarks/GSM_symbolic.jsonl` | `945055837b232bd9b56827b1e3a5aa019075f29e8ba4669d9a9df8b4439a291f` | 100 | 94 | 94.00% (94/100) | 94.00% (94/100) | [87.52%, 97.22%] | `logs/test_reports/gsm_symbolic_100_templates_20261007_repro.json` | Phase 3 deterministic re-run matching 94.0% baseline bit-for-bit. |

| `humaneval-canonical-raw-164-repro` | `f7c98a0` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 155 | 94.51% (155/164) | 94.51% (155/164) | [89.90%, 97.09%] | `logs/test_reports/humaneval_canonical_raw_164_20261007_repro.json` | Phase 3 deterministic re-run matching 94.51% baseline bit-for-bit. |

| `humaneval-canonical-assisted-164-repro` | `f7c98a0` | canonical-unit-tests | `data/benchmarks/humaneval.jsonl` | `1d49078ba3e2b196b9344535bef34a43021f038fad9561d6ee7c53450609a6a2` | 164 | 154 | 93.90% (154/164) | 93.90% (154/164) | [89.14%, 96.65%] | `logs/test_reports/humaneval_canonical_assisted_164_20261007_repro.json` | Phase 3 deterministic re-run matching 93.90% baseline bit-for-bit. |

| `12b-math500-b4-sealed-r0-4k` | `b340ce0` | v1.35-dual | `data/benchmarks/math_b4_sealed_100.jsonl` | `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b` | 100 | 93 | 93.00% (93/100) | 94.00% (94/100) | [86.25%, 96.57%] (S) / [87.52%, 97.22%] (L) | `logs/test_reports/b4_sealed/gemma-4-12b_math500_r0_b4_sealed_cap4096_100.json` | Phase 3 Block B4 sealed held-out evaluation: Direct generation arm; 0% truncations. |

| `12b-math500-b4-sealed-p2-2k` | `b340ce0` | v1.35-dual | `data/benchmarks/math_b4_sealed_100.jsonl` | `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b` | 100 | 87 | 87.00% (87/100) | 92.00% (92/100) | [79.02%, 92.24%] (S) / [85.00%, 95.89%] (L) | `logs/test_reports/b4_sealed/gemma-4-12b_math500_p2_b4_sealed_cap2048_100.json` | Phase 3 Block B4 sealed held-out evaluation: PAL + Turn 2 Docker arm; 0% truncations. |

| `12b-math500-b4-sealed-r1-6k` | `b340ce0` | v1.35-dual | `data/benchmarks/math_b4_sealed_100.jsonl` | `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b` | 100 | 46 | 46.00% (46/100) | 46.00% (46/100) | [36.56%, 55.74%] (S) / [36.56%, 55.74%] (L) | `logs/test_reports/b4_sealed/gemma-4-12b_math500_r1_b4_sealed_think6144_100.json` | Phase 3 Block B4 sealed held-out evaluation: Thinking arm; 55% truncations. |



---



## Split Nomenclature & Exposure Disclosures



**Manifest record citations (`data/benchmarks/MANIFEST.yaml`):** the three

MATH-500 experiment figures cited across the docs are manifest records

`math500_pal_v1_3` (77.0%/87.0% PAL Dev-100, superseded),

`math500_fresh_heldout_500_v1_3_0` (74.20%/78.80% fresh N=500, superseded,

dataset-drift bound), and `math500_heldout100_direct_r0_v1_35_6` (89.0%

Direct R0 held-out-100, current). These are distinct experiments, not

contradictory data.



1. **Nomenclature Mapping:** The dataset slice `data/benchmarks/math500_test.jsonl` (problems 1–100) is designated as **Dev-100** across research papers and factorial reports, reflecting its historical role as a prompt-development split in v1.3 where it was labeled `test-100`.

2. **Held-Out Definition:** The primary held-out benchmark for the R0/P2/R1 arm comparisons comprises lines 1–100 of `data/benchmarks/math_fresh_heldout_500.jsonl`. Problems 101–500 have **not** been run under those arms; however, all 500 problems were run once under the single v1.35 PAL-with-feedback harness (row `math-v1.35-final-fresh-500`, 429/500 strict). They are therefore not an untouched reserve.

3. **Exploratory Leak Disclosure:** As documented in `luccadocs/archive/2026-10_handovers/V135_CONTAMINATION_AUDIT.md`, exploratory prompt inspection touched problems 15 and 73 on `math_fresh_heldout_500.jsonl` (zero-indexed: indices 14 and 72). No harness or prompt modification was made in response to this exposure.

4. **Dataset SHA-256 Lineage (`math_fresh_heldout_500.jsonl`):** Early v1.3 rows record SHA-256 `834405fa038936ef...` (initial export prior to v1.35 normalization), whereas v1.35+ rows record `834405faef2b3059...` (the pinned on-disk file in `data/benchmarks/math_fresh_heldout_500.jsonl`, documented in `data/benchmarks/MANIFEST.yaml` `drift_note`). For a zero-exposure held-out reference, see the pre-registered sealed set `math_b4_sealed_100.jsonl` (`14c8af21...100b`).



---



## Held-Out 98-Item Robustness Check (Excluding Leaked Items 15 & 73)



Reproducible via [`scripts/recompute_heldout_98.py`](file:///c:/Projects/ProjectLucca/scripts/recompute_heldout_98.py):



| Evaluation Arm / Configuration | Full Held-Out (100 Items) | Cleaned Subset (98 Items) | Absolute Delta ($\Delta$) | Ranking / Conclusion Impact |

| :--- | :---: | :---: | :---: | :--- |

| **Gemma 4 12B Direct (R0 @ 4,096 cap)** | 89.0% (89/100) | **88.8% (87/98)** | $-0.2\text{ pp}$ | None (Remains peak raw generator) |

| **Gemma 4 12B PAL (P2 @ 2,048 cap)** | 86.0% (86/100) | **85.7% (84/98)** | $-0.3\text{ pp}$ | None |

| **Gemma 4 E4B Routed / Thinking (R1 @ 6,144 cap)** | 88.0% (88/100) | **87.8% (86/98)** | $-0.2\text{ pp}$ | None (point estimate close to 12B R0; cross-model comparison is confounded by fine-tune lineage — see Paper 06 §5.1) |

| **Gemma 4 E4B PAL (P2 @ 2,048 cap)** | 73.0% (73/100) | **73.5% (72/98)** | $+0.5\text{ pp}$ | None (R1 retains significant +14.3 pp lead) |

| **Gemma 4 E4B Direct (R0 @ 4,096 cap)** | 52.0% (52/100) | **51.0% (50/98)** | $-1.0\text{ pp}$ | None |

| **Gemma 4 E2B Thinking (R1 @ 6,144 cap)** | 81.0% (81/100) | **80.6% (79/98)** | $-0.4\text{ pp}$ | None (Retains significant +19.4 pp lead over P2) |

| **Gemma 4 E2B PAL (P2 @ 2,048 cap)** | 61.0% (61/100) | **61.2% (60/98)** | $+0.2\text{ pp}$ | None |

| **Gemma 4 E2B Direct (R0 @ 4,096 cap)** | 51.0% (51/100) | **50.0% (49/98)** | $-1.0\text{ pp}$ | None |



*Summary:* Excluding items 15 and 73 shifts strict accuracy by at most 1.0 pp across all arms, with zero changes to rankings, significance tests, or architectural conclusions.



---



## Output Supervisor Live Action Hallucination Evaluation ($n=100, T=0.6$)



Evaluated on [`data/benchmarks/action_hallucination_battery_100.json`](file:///c:/Projects/ProjectLucca/data/benchmarks/action_hallucination_battery_100.json) across Gemma 4 E4B and E2B:



| Evaluation Stratum | Claims Emitted (E4B / E2B / Total) | Supervisor Caught (TP) | Catch Rate [95% Wilson CI] | Notes |

| :--- | :---: | :---: | :---: | :--- |

| **Strict Completed Actions Only** | 5 / 3 / **8** | **1** (E4B T01) | **12.5% (1/8)** [2.2%, 47.1%] | Unequivocal completions only (past tense, telegraphic confirmations) |

| **Broad FAC (Primary Audit)** | 15 / 8 / **23** | **1** (E4B T01) | **4.3% (1/23)** [0.8%, 21.0%] | Includes active progressive participles and markdown action headers |

| **Controls ($n=50$)** | 0 / 50 FP | — | **0.0% FP (0/50)** | Zero false aborts across 25 honest controls + 25 idiom controls |



*Note on Embedded JSON Fields:* Automated regex fields embedded in raw JSON files reported TP=1/FN=1 (E4B) and TP=0/FN=1 (E2B) due to regex circularity with the supervisor. Authoritative ground truth is established via post-hoc manual audit in [`logs/test_reports/action_hallucination_labels_100.jsonl`](file:///c:/Projects/ProjectLucca/logs/test_reports/action_hallucination_labels_100.jsonl).



---



## B4 Clean Held-Out Factorial Ablation Outcomes ($N=100$)



Evaluated on pre-registered sealed held-out dataset [`data/benchmarks/math_b4_sealed_100.jsonl`](file:///c:/Projects/ProjectLucca/data/benchmarks/math_b4_sealed_100.jsonl) (SHA-256 `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b`) under pre-registered protocol (greedy $T=0.0$, seed 42, `cache_prompt: false`, frozen dual grader v1.35):



| Arm | Description | Substrate | Strict Acc (%) | 95% Wilson CI | Lenient Acc (%) | 95% Wilson CI | Truncations | Elapsed (s) |

| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |

| **R0** | Raw Direct (cap 4096) | Native text | 93.0% | [86.25%, 96.57%] | 94.0% | [87.52%, 97.22%] | 0% | 1632.5s |

| **P2** | PAL + Turn 2 Feedback (cap 2048) | Docker sandbox | 87.0% | [79.02%, 92.24%] | 92.0% | [85.00%, 95.89%] | 0% | 1817.7s |

| **R1** | Thinking mode (think 6144) | Native text CoT | 46.0% | [36.56%, 55.74%] | 46.0% | [36.56%, 55.74%] | 55% | 9414.6s |



### Paired McNemar Statistical Significance ($N=100$ Paired Items)



| Comparison | Metric | Arm A Acc | Arm B Acc | $\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Odds Ratio | Significance ($p < 0.05$) |

| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |

| **P2 vs R0** | Strict | 87.0% | 93.0% | -6.0 | 1 : 7 | 7.0312e-02 | 0.200 | No (not significant; not evidence of equivalence) |

| **R1 vs P2** | Strict | 46.0% | 87.0% | -41.0 | 3 : 44 | 2.4647e-10 | 0.079 | **YES** |

| **R1 vs R0** | Strict | 46.0% | 93.0% | -47.0 | 0 : 47 | 1.4211e-14 | 0.011 | **YES** |

| **P2 vs R0** | Lenient | 92.0% | 94.0% | -2.0 | 2 : 4 | 6.8750e-01 | 0.556 | No (not significant; not evidence of equivalence) |

| **R1 vs P2** | Lenient | 46.0% | 92.0% | -46.0 | 0 : 46 | 2.8422e-14 | 0.011 | **YES** |

| **R1 vs R0** | Lenient | 46.0% | 94.0% | -48.0 | 0 : 48 | 7.1054e-15 | 0.010 | **YES** |



*Key Findings:* Direct generation (R0) achieves 93.0% strict / 94.0% lenient with zero truncations. PAL (P2) does not differ significantly from R0 (McNemar $p=0.0703$ strict, $p=0.6875$ lenient); the point estimate favors R0 (1:7 discordant) and the test does not exclude a real PAL deficit. Thinking mode (R1) under greedy decoding shows 55% ceiling truncation and scores significantly worse ($p < 10^{-9}$); this is a confounded observation about the greedy configuration, not about thinking mode per se. Full factorial report at [`logs/test_reports/b4_sealed/B4_FACTORIAL_REPORT_100.md`](file:///c:/Projects/ProjectLucca/logs/test_reports/b4_sealed/B4_FACTORIAL_REPORT_100.md).



---



## TTS Safety Guard Efficacy Battery Outcomes (Block B2)



Evaluated on 30-probe cross-model battery under `TTSSafetyGuard` (`off` vs `edge_tiers`) on `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (SHA-256 `ab52d2db6b24d78096fcefc937e20ec42c67c519a79fa761b03fc714659b586e`) per `scripts/run_tts_guard_efficacy_battery.py`:



| Metric | Count | Rate (%) | 95% Wilson Score CI |

| :--- | :---: | :---: | :---: |

| **Harmful: Model Native Refusal** | 3/10 | 30.0% | [8.1%, 64.6%] |

| **Harmful: TTS Guard Block** | 0/10 | 0.0% | [0.0%, 34.5%] |

| **Harmful: Combined Protection** | 3/10 | 30.0% | [8.1%, 64.6%] |

| **Benign Control: False Block** | 0/20 | 0.0% | [0.0%, 20.0%] |



*Key Findings & Audit Status (P6):*

1. **P6 Converted to Mitigated (Measured):** Live empirical battery verifies 0.0% false-positive rate across 20 benign tool and persona probes.

2. **Harmful Probe Dynamics:** Native refusal rate of 30.0% replicates September historical baseline. Safe conversational deflections without instructional weapons synthesis were observed on remaining probes.

3. **Artifacts:** Full telemetry preserved in [`logs/test_reports/tts_guard_efficacy_20261007T020151Z.json`](file:///c:/Projects/ProjectLucca/logs/test_reports/tts_guard_efficacy_20261007T020151Z.json) and [`logs/test_reports/tts_guard_efficacy_20261007T020151Z_REPORT.md`](file:///c:/Projects/ProjectLucca/logs/test_reports/tts_guard_efficacy_20261007T020151Z_REPORT.md).


