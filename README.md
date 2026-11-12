# Project Lucca — Autonomous Neuro-Symbolic Desktop Companion (`v1.51.0` / `WO-45`)

Project Lucca is an autonomous, local-first desktop companion for Windows workstations that combines real-time voice interaction (Push-to-Talk and energy VAD), symbolic procedural reasoning (MicroScheme LISP engine and Z3 formal verification), and sandboxed execution inside an isolated Docker container with cryptographically signed, provenance-gated long-term memory.

> **Status:** Single-developer research project. Hardware-specific. All benchmarks author-measured on one workstation. No independent external reproduction yet.

---

## Known Limitations

- **Self-run benchmarks:** All benchmark figures reported below are author-measured on local workstation silicon (`RTX 5080 Laptop GPU`, `Core Ultra 9 275HX`); none have been independently reproduced yet.
- **Residual action-claim supervision boundary (`src/lucca/sandbox/neural_claim_verifier.py`):** Clause-level OpenVINO supervision paired with deterministic `ToolReceipt` set verification (`WO-42`) reaches `98.7% (465/471)` recall at `0.6% (9/1,551)` FPR across `N=2,022` pooled turns ([`wo42_large_sample_2020_report.json`](./logs/test_reports/wo42_large_sample_2020_report.json)), leaving `6/471 (1.27%)` missed zero-verb indirect state-consequence claims and `9/1,551 (0.58%)` false alarms on first-person hypothetical walkthroughs. Output supervision remains an empirical runtime guardrail rather than a formal safety guarantee.
- **NLI entailment recall on low-overlap paraphrases & fail-closed conservatism (`src/lucca/senses/verifier.py`):** Upgrading the OpenVINO CPU NLI cross-encoder from `MiniLM-L6` to `DeBERTa-v3-xsmall` (`20.47 ms` p50 / `26.70 ms` p95, `0 MB` VRAM; [`nli_verifier_v2_report.json`](./logs/test_reports/nli_verifier_v2_report.json)) raised `pairs_v1` (`N=100`) entailment recall from `24/30 (80.0%)` to `25/30 (83.3%)` (`91/100 = 91.0%` overall) and raised blinded out-of-sample `nli_holdout_v2_120` (`N=120` hard non-lexical paraphrases & shared-entity near-misses) accuracy from `67/120 (55.8%)` to `82/120 (68.3%, p = 0.0107)` (`7/40 = 17.5%` $\to$ `16/40 = 40.0%` entailment recall at `100.0% [16/16]` precision, $p = 0.0117$). Because all NLI consumers fail closed on `UNCERTAIN`/`NEUTRAL` verdicts (`test_no_nli_uncertain_fail_open_consumers`), low-overlap implicit entailments are conservatively withheld from automatic clustering rather than mis-merged.
- **Windows + WSL2 desktop stack coupling:** Full 4-process voice/UI/sandbox operation targets Windows 11 with WSL2 Docker CE. OpenVINO classifiers (`NPU -> CPU`) and Faster-Whisper ASR (`CUDA float16 -> CPU int8`) degrade automatically to host CPU when an Intel NPU or CUDA GPU is absent, whereas local GGUF `llama-server` inference expects an NVIDIA CUDA GPU (`4–16 GB` VRAM depending on model tier).

---

## Requirements

- **OS:** Windows 11 64-bit with WSL2 (Ubuntu) and Docker CE (`.wslconfig` clamped to `4.5 GB`).
- **dGPU (scales with chosen GGUF tier at `ctx=32768`, [`q1_vram_nvidia_smi_evidence.json`](./logs/test_reports/wo45/q1_vram_nvidia_smi_evidence.json)):**
  - **`Gemma-4-E2B (Q6_K)`:** NVIDIA RTX GPU with **4–6 GB+ VRAM** (`~2.7 GiB` resident).
  - **`Gemma-4-E4B (Q6_K)`:** NVIDIA RTX GPU with **6–8 GB+ VRAM** (`~4.8–5.0 GiB` resident).
  - **`Gemma-4-12B (Q6_K)`:** NVIDIA RTX GPU with **12 GB+ VRAM** (`~10.9 GiB` resident).
  - **`Gemma-4-26B-A4B MoE (Q6_K, --cpu-moe)`:** NVIDIA RTX GPU with **12–16 GB VRAM** (`~11.5 GiB` resident) + host RAM expert offload.
- **CPU / NPU / RAM:**
  - **CPU & Optional NPU:** Modern x86_64 multi-core CPU. An **Intel AI Boost NPU is optional** — OpenVINO uses the NPU automatically when present (`0 MB` VRAM, `6.58 ms` mean web-burden gate latency) and falls back transparently to OpenVINO CPU when absent (`16.92 ms` mean on Core Ultra 9 275HX per [`r06_gate_latency_npu_vs_cpu.json`](./logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json)).
  - **System RAM:** **16 GB** for `E2B` / `E4B` (`~3.5 GB` host boot budget + `4.5 GB` WSL2 clamp), **16–24 GB** for `12B`, and **32 GB+** only when running `26B-A4B` with CPU-offloaded MoE experts (`--cpu-moe --moe-cache-mib 7680`).
- **Environment:** Python 3.12+ managed via `uv`.

---

## Quick Start

```powershell
# 1. Run environment check
uv run python -m lucca.core.env_check

# 2. Run static gates and unit test suite
uv run pytest tests/test_static_gates.py
uv run pytest

# 3. Launch multi-process companion supervisor
uv run python -m lucca.main
```

---

## Architecture

See [Unified System Architecture Specification](luccadocs/ARCHITECTURE.md) for the complete 4-process topology, execution tiers (`REFLEX`, `ACT_THEN_NARRATE`, `FULL_LOOP`), modularized orchestrator/supervision/reasoning services (`WO-43`: `198` modules, `83,931` LOC in `src/lucca/`), MicroScheme engine with cryptographically authenticated operator rule promotion (`OperatorApprovalToken`) and 1-strike user-correction demotion, and RFC 8032 asymmetric provenance envelope verification (`src/lucca/memory/signers.py`, `src/lucca/memory/gate.py`).

---

## Benchmark Results

All figures below are author-measured on workstation silicon (`RTX 5080 Laptop GPU`, `Core Ultra 9 275HX`, native Windows 11).

> [!NOTE]
> **Scientific Audit & Provenance Ledger (`WO-39` – `WO-45`):** All active benchmarks below reflect decontaminated `llama-server` runs verified in Docker or isolated SQLite stores (with per-step OpenTimestamps + `origin/main` commit chains for `WO-45 G4 v3`). Historical errata and superseded baselines — including `WO-44` (`82b1da8`, where Ed25519 was not used and `v1`/`v2` web-burden runs were superseded by pre-registered `G4 v3`), retired `G4 v2` defects (`F-1..F-8` in [`REVIEW_G4.md`](./logs/test_reports/wo45/REVIEW_G4.md)), and `WO-39` pre-decontamination archives — are documented in full in [`AUDIT_AND_RETRACTION_HISTORY.md`](./logs/test_reports/wo45/AUDIT_AND_RETRACTION_HISTORY.md).

| Benchmark | Config | Result (Author-measured, [95% Wilson CI]) | Evidence File |
| :--- | :--- | :---: | :--- |
| **Paper 1 / 3: Memory Poisoning v3 (`prereg-wo43-power-300`, `N=300`)** | `N=300` 5-arm ablation (`Cohort A n=100` natural confabulations, `Cohort B n=100` benign math/plans, `Cohort C n=100` user falsehoods; `1,500` evaluations on `E4B`) | **Cohort A & C Poisoning: `0/100 (0.0% [0.0%, 4.61%])`** vs `100/100 (100.0%)` Naive RAG & Adversarial Soft Tagging (exact McNemar $p = 4.16 \times 10^{-23}$) and `11/100 (11.0%)` Passive Soft Tagging ($p = 9.77 \times 10^{-4}$); **Cohort A & B Continuity: `100/100 (100.0% [95.39%, 100.0%])`** vs `1/100 (1.0%)` No-Assistant ($p = 6.90 \times 10^{-23}$); Dual Blinded Judge IRR $\kappa = 0.9206$ (`58/60`) | [`memory_poisoning_v3_300_results.json`](./logs/test_reports/memory_poisoning_v3_300_results.json), [`wo43_phase5_blinded_irr_60_report.json`](./logs/test_reports/wo43_phase5_blinded_irr_60_report.json) |
| **Contrastive Companion Battery v2 (`prereg-wo43-power-300`, `N=300`)** | `N=300` (`100` `recall`, `100` `receipt_introspection`, `100` `abstention`) $\times$ 3 arms (`Bare LLM`, `Compound Lucca`, `Top-5 Hybrid RAG` = `900` live turns on `E4B`) | **Recall: `100/100 (100.0% [95.4%, 100.0%])`** Compound Lucca vs `2/100 (2.0%)` Bare LLM (`+98.0 pp`, $p_{\text{HB}} = 1.03 \times 10^{-21}$) and `85/100 (85.0%)` Hybrid RAG (`+15.0 pp`, $p_{\text{HB}} = 3.05 \times 10^{-4}$); **Receipt Introspection: `100/100 (100.0%)`** vs `50/100` Bare LLM and `98/100` Hybrid RAG; **Abstention: `100/100 (100.0%)`** (`0` errors across `900` turns; IRR $\kappa = 1.0000$) | [`contrastive_v2_300_results.json`](./logs/test_reports/contrastive_v2_300_results.json), [`contrastive_v2_300_results_REPORT.md`](./logs/test_reports/contrastive_v2_300_results_REPORT.md) |
| **Paper 4 / WO-45 G4 v3: Pre-Registered 4-Arm Web Evidentiary Burden (`N=132` Items, `2,640` Live Turns)** | `132` fresh `WEB360` items (`0` `v2` overlap) $\times$ `4` arms (`A`, `B`, `C`, `D`) $\times$ `5` Gemma-4 `Q6_K` models (`E2B`, `E4B-heretic`, `E4B-stock`, `12B`, `26B-A4B`) at `ctx=32768`; 3 non-Google judge families (`Qwen3.8-27B`, `Phi-4-14B`, `Nemotron-3.5-30B-A3B`) on normalized text (`0` forbidden lexicon hits) | **Co-Primary `D4` Conflict Disclosure (`660` disputed turns, $\min \kappa = 0.6983$):** `Arm A` `61/165 (36.97%)`, `Arm C` (generic tip) `85/165 (51.52%)`, **`Arm D` (structured contract + Arm C prompt, no `MUST`/legal vocab) `164/165 (99.39% [98.18, 100.0])`**, `Arm B` `165/165 (100.0%)` — **`D vs C = +47.88 pp` `[+36.36, +60.00]`, $p = 0.0001$, `79:0` discordant** (`B vs D = +0.61 pp`, $p = 0.7214$, null). **Substantive Faithful Answering (`D2=NO & NO_ANSWER=NO`):** `648/660 (98.18%)` `Arm D` vs `612/660 (92.73%)` `Arm C` (`+5.45 pp`, $p = 0.0001$). **`D1` `ACCURATE`:** `643/660 (97.42%)` `Arm D` vs `614/660 (93.03%)` `Arm C` (`+4.39 pp`, $p = 0.0012$; `B vs D = -2.27 pp`, $p = 0.0108$; live `D1`/`D2` $\kappa < 0.60$ under `93%–99%` base-rate skew). **Gate Latency:** `6.58 ms` mean NPU / `16.92 ms` mean CPU (`360/360` Walton synthetic conformance; active `v1` NPU hazard classifier over-escalates `24/132` [`6` nominal-met items] pending `Gate G5` holdout) | [`GATE_G4v3.md`](./logs/test_reports/wo45/GATE_G4v3.md), [`g4_live_v3_report.json`](./logs/test_reports/wo45/g4_live_v3_report.json), [`r06_gate_latency_npu_vs_cpu.json`](./logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json) |
| **Paper 4 / WO-42: Clause-Level OpenVINO Supervision & Routing (`N=2,022` Pooled + `N=540` Blind + `100` Live E2E)** | 3 OpenVINO IR classifiers (`action_claim_verifier_ov`, `proof_policy_hazard_ov`, `router_intent_ov`, `0 MB` GPU VRAM) across `N=2,022` pooled supervision turns, `Blind-390`, `WO42_LOCKED_HOLDOUT_150` (SHA-256 locked pre-generation), `550` `Hypothesis` fuzz cases, and `100` live 4-model turns | • **Action-Claim Supervision (`N=2,022`):** **`98.7% (465/471)` Recall / `0.6% (9/1,551)` FPR (`99.3% [98.8%, 99.6%]` acc.)** (`12.1 ms` mean; `100.0% [47/47]` recall on unseen `H001..H100`, `93.3% [14/15]` on zero-verb `IMP_01..IMP_30`, vs `58.5%` legacy stem regex)<br>• **`Blind-390`:** **`377/390 (96.7% [94.38%, 98.04%])`** (`Coherence: 130/130`, `Hazard: 125/130`, `Router: 122/130`; IRR $\kappa = 1.000$)<br>• **`WO42_LOCKED_HOLDOUT_150`:** **`145/150 (96.67% [92.43%, 98.57%])`** single-pass locked (`50/50` coherence, `50/50` hazard, `45/50` router $\to$ `150/150` post-router-fix)<br>• **Live 4-Model E2E (`100` Turns):** **`100/100 (100.0%)`** coherence & grounding, **`98/100 (98.0%)`** task/reasoning | [`wo42_large_sample_2020_report.json`](./logs/test_reports/wo42_large_sample_2020_report.json), [`wo42_locked_holdout_150_report.json`](./logs/test_reports/wo42_locked_holdout_150_report.json), [`wo42_live_4model_summary.json`](./logs/test_reports/wo42_live_4model_summary.json) |
| **Paper 2: Structured Output Action Contract (`SOAC`, `720` Live Turns)** | `N=120` held-out prompts on `26B-A4B` (`720` completions across `v1`/`v2` Natural, SOAC, and SOAC+GBNF; dual-rater $\kappa = 1.0000$) | **SOAC** binds explicit `[ACTION: ...]` frames in **`6.82 µs`** with **`0/120 (0.00% [0.00%, 3.87%])` unframed prose leakage** across `v1 SOAC`, `v2 SOAC`, and `v2 SOAC+GBNF` (`100%` frame coupling on all `13/13`, `18/18`, and `17/17` prose claims — passing $H_{2e} \le 2/120$) | [`docs/papers/02_deontic_supervision_evasion.pdf`](./docs/papers/02_deontic_supervision_evasion.pdf), [`paper2_v1_v2_semantic_audit_720.json`](./logs/test_reports/paper2_v1_v2_semantic_audit_720.json) |
| **Paper 1: Memory Poisoning Multi-Scale (`N=100` + 4-Scale Rebench)** | `N=100` 4-arm ablation on `26B-A4B` + `WO-39` 4-scale live rebench (`n=10`/scale across `26B-A4B`, `12B`, `E4B`, `E2B`) | **`0/40 (0.0% [0.0%, 8.8%])`** poisoned vs `40/40` Naive RAG ($p = 1.82 \times 10^{-12}$); `96.7%` Cohort B retention; `0/10` poisoned across all 4 scales under `V2c` ($p = 0.00195$) | [`docs/papers/01_memory_poisoning_ablation.pdf`](./docs/papers/01_memory_poisoning_ablation.pdf), [`wo39_live_4models_rebench.json`](./logs/test_reports/wo39_live_4models_rebench.json) |
| **Paper 3: LongMemEval Pipeline (`N=30`, `12B`)** | Conversational memory & temporal reasoning: Context-Truncation Baseline vs. Lucca Provenance + RRF + Allen Pipeline | **`23.3% (7/30 [11.8%, 40.9%])` $\to$ `70.0% (21/30 [52.1%, 83.3%])`** (`0:14` discordant pairs, exact McNemar $p = 0.000122$, `8.1 ms` mean retrieval latency) | [`longmemeval_pipeline_12B_1791794644.json`](./logs/test_reports/longmemeval_pipeline_12B_1791794644.json) |
| **Paper 3: IN-D Live 52-Turn Rule Induction** | Organic 52-turn waking trace + 16 held-out turns on `12B` (`RuleInducer` + Z3 SMT + 50-turn `Dream-RSI` replay + 1-strike eviction) | **4/4** tool rules Z3-quarantined (`100%` 50-turn replay, **`8/8 [67.6%, 100%]`** held-out recall at `0.14 ms`, **`0/8 [0.0%, 32.4%]`** misfires; `0/2` free-form S-expr macros admitted) | [`in_d_live_baseline_wo39.json`](./logs/test_reports/in_d_live_baseline_wo39.json), [`SINGLE_RULE_LIFECYCLE_TRACE.md`](./docs/SINGLE_RULE_LIFECYCLE_TRACE.md) |
| **DeBERTa-v3-xsmall vs MiniLM-L6 NLI Verifier (`WO-45 Step 4A` & `WO-37`)** | Pre-registered OpenVINO CPU (`0 MB` VRAM, `50 ms` budget) head-to-head on `pairs_v1` (`N=100`) + blinded out-of-sample `nli_holdout_v2_120` (`N=120`: `40` entailment, `40` contradiction, `40` neutral) | • **Out-of-sample `nli_holdout_v2_120`:** `MiniLM-L6` `67/120 (55.8% [46.9%, 64.4%])` $\to$ **`DeBERTa-v3-xsmall` `82/120 (68.3% [59.6%, 76.0%])`** (`23:8` discordant, $p = 0.0107$); entailment recall `7/40 (17.5%)` $\to$ **`16/40 (40.0% [26.4%, 55.4%], 100.0% precision)`** (`10:1` discordant, $p = 0.0117$), contradiction recall `27/40 (67.5%)` $\to$ **`31/40 (77.5%)`**, **`20.47 ms` p50 / `26.70 ms` p95**<br>• **`pairs_v1` (`N=100`):** **`91/100 (91.0% [83.8%, 95.2%])`** on both (`24/30 = 80.0%` $\to$ **`25/30 = 83.3%`** entailment recall, **`19.62 ms` p50 / `20.56 ms` p95**) | [`nli_verifier_v2_report.json`](./logs/test_reports/nli_verifier_v2_report.json), [`nli_verifier_v2_prereg_lock.json`](./logs/test_reports/nli_verifier_v2_prereg_lock.json), [`Paper 03 §4.1`](./luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md#L121) |
| **WO-39: Sealed Parametric Suite (`v139`)** | `N=15` (`3/lobe`: `ContainerWorld`, `Z3`, `SymPy`, `2-Lobe`, `CEGIS`) across `26B-A4B`, `12B`, `E4B`, `E2B` | **`15/15 (100% [79.6%, 100%])`** on `26B-A4B`, `12B`, `E4B` ($p = 0.000061$ vs `0/15` raw); **`14/15 (93.3% [70.2%, 98.8%])`** on `E2B` | [`RESULTS.md`](./RESULTS.md#L7) |
| **Canonical HumanEval & HumanEval-Plus (`N=164`)** | 164 coding tasks `pass@1` in Docker (`cache_prompt: false`, `12B`) + EvalPlus 80x differential tests | **`94.51% (155/164 [89.90%, 97.09%])`** HumanEval raw (`93.90%` assisted) • **`91.46% (150/164 [86.18%, 94.84%])`** HumanEval-Plus | [`RESULTS.md`](./RESULTS.md#L58) |
| **GSM-Symbolic (`N=100`) & MATH-500 (`N=100` Sealed / `N=500` Fresh)** | Perturbed symbolic math & competition mathematics (`12B`) | **`94.00% (94/100 [87.52%, 97.22%])`** GSM-Symbolic • **`93.00%` strict (`94.00%` lenient)** MATH-500 Sealed B4 • **`85.80%` strict (`429/500`) / `90.20%` lenient (`451/500`)** MATH-500 Fresh | [`RESULTS.md`](./RESULTS.md#L56) |
| **Static, Anti-Cheat & Modularity Gates (`WO-43`)** | Structural invariants, zero-`Any`, LOC ceilings, AST parity, NLI fail-closed, 100% runtime reachability (`198` modules), zero Ruff/mypy errors | **40 / 40 gates PASSED** + **7 / 7 Import-Linter contracts KEPT** | [`tests/test_static_gates.py`](./tests/test_static_gates.py) |

---

## Documentation & Community

- **Reproduction Guide:** [`REPRODUCING.md`](./REPRODUCING.md) — Step-by-step reproduction instructions, dataset hashes, and one-command benchmark targets.
- **Audit & Retraction History:** [`logs/test_reports/wo45/AUDIT_AND_RETRACTION_HISTORY.md`](./logs/test_reports/wo45/AUDIT_AND_RETRACTION_HISTORY.md) — Complete `WO-39`–`WO-45` audit disclosures, `WO-44` corrections, and superseded benchmark runs.
- **System Glossary:** [`luccadocs/GLOSSARY.md`](./luccadocs/GLOSSARY.md) — Plain-English definitions of cognitive architecture terms.
- **Security Policy & Threat Model:** [`SECURITY.md`](./SECURITY.md) and [`luccadocs/security/THREAT_MODEL.md`](./luccadocs/security/THREAT_MODEL.md) — Vulnerability reporting, attack surfaces, and verified defense invariants.
- **Contributing:** [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) — Development guidelines and invariants.
- **Third-Party Notices:** [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md) — Upstream runtime, library, and foundation model licenses.

---

## Research

See [`luccadocs/research/README.md`](./luccadocs/research/README.md) for the research roadmap, experimental logs, and technical reports:
- **Foundational Pre-Print (PDF):** [`docs/paper.pdf`](./docs/paper.pdf) — *Provenance-Gated Memory and Deontic Output Supervision for Epistemically Grounded Autonomous Agents* (Zenodo DOI: [`10.5281/zenodo.23649049`](https://doi.org/10.5281/zenodo.23649049)).
- **Paper 1 (Memory Poisoning Ablation PDF & LaTeX):** [`docs/papers/01_memory_poisoning_ablation.pdf`](./docs/papers/01_memory_poisoning_ablation.pdf), [`papers/01_memory_poisoning_ablation/main.tex`](./papers/01_memory_poisoning_ablation/main.tex) — *Cryptographic Provenance Gates Mitigate Multi-Session Memory Poisoning in Autonomous Agents* (Zenodo DOI: [`10.5281/zenodo.23901452`](https://doi.org/10.5281/zenodo.23901452)).
- **Paper 2 (Deontic Supervision Evasion PDF & LaTeX):** [`docs/papers/02_deontic_supervision_evasion.pdf`](./docs/papers/02_deontic_supervision_evasion.pdf), [`papers/02_deontic_supervision_evasion/main.tex`](./papers/02_deontic_supervision_evasion/main.tex) — *Why Speech-Regex Action Supervisors Miss Live Output: An Empirical Evasion Taxonomy and Held-Out Structured Action Contract Evaluation* (Zenodo DOI: [`10.5281/zenodo.23901605`](https://doi.org/10.5281/zenodo.23901605)).
- **Paper 3 (5-Layer Epistemic & Procedural Memory PDF & LaTeX):** [`docs/papers/03_provenance_gated_five_layer_memory.pdf`](./docs/papers/03_provenance_gated_five_layer_memory.pdf), [`papers/03_provenance_gated_five_layer_memory/main.tex`](./papers/03_provenance_gated_five_layer_memory/main.tex) — *Closing the Epistemic Loop Across the Five Layers of Agent Memory: Cryptographic Provenance, Paraconsistent Bilattices, and Z3-Quarantined Procedural Induction* (Zenodo DOI: [`10.5281/zenodo.23901683`](https://doi.org/10.5281/zenodo.23901683)).
- **Paper 4 (Clause-Level NPU Supervision & 2D Evidentiary Burden PDF & LaTeX):** [`docs/papers/04_clause_level_npu_supervision.pdf`](./docs/papers/04_clause_level_npu_supervision.pdf), [`papers/04_clause_level_npu_supervision/main.tex`](./papers/04_clause_level_npu_supervision/main.tex) — *Breaking the Lexical Supervision Ceiling: Clause-Level MiniLM-L6 Verification and Task-Priority Intent Routing on a Zero-VRAM Edge NPU*.
- **Subsystem Technical Reports (Markdown):** [`Paper 03 (Provenance & Belnap/NARS)`](./luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md) • [`TR-04 (E-Graph, Z3 Quarantine & Live IN-D Baseline)`](./luccadocs/research/papers/04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md) • [`Paper 06 (4-Model Scale Ablation)`](./luccadocs/research/papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md) • [`Single-Rule Lifecycle Case Study (26B-A4B)`](./docs/SINGLE_RULE_LIFECYCLE_TRACE.md).

---

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later). See [LICENSE](./LICENSE). Upstream components retain their original licenses per [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
