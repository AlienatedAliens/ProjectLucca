# Project Lucca — Autonomous Neuro-Symbolic Desktop Companion

Project Lucca is an autonomous, local-first desktop companion for Windows workstations that combines real-time voice interaction (Push-to-Talk and energy VAD), symbolic procedural reasoning (MicroScheme LISP engine and Z3 formal verification), and sandboxed execution inside an isolated Docker container with cryptographic, provenance-gated long-term memory.

> **Status:** Single-developer research project. Hardware-specific. All benchmarks author-measured on one machine. No independent reproduction yet.

---

## Known Limitations

- **Self-run benchmarks:** All benchmark figures reported below are author-measured on local workstation silicon; none have been independently reproduced or externally verified.
- **Truth-in-Receipt supervision:** On the initial `N=200` developmental transcripts (`E2B/E4B`), the original pre-hardening 1P matcher caught `1/23 (4.3%)` broad (`1/8 [12.5%]` strict) action claims before hardening and `23/23 (100%)` in-sample after hardening (`0/100` control FPs, `3/52` temptation non-claim FPs). On the `N=120` held-out battery (`26B-A4B`, Paper 2 Study V1 & V2, `720` total completions across 6 arms), a line-by-line blinded semantic re-audit (`blinded_paper2_v1_v2_semantic_labels_720.jsonl`, dual-rater $\kappa = 1.0000$ on $n=120$) proved that the legacy regex ground-truth heuristic (`primary_audit_ground_truth`) had misclassified `9/40`–`14/40` Honest Controls and `2/30`–`5/30` Idioms as "action claims": in v1/v2 Natural (`26B-A4B` with tool-abstention system prompt), the model emitted `3/50 (6.0%)` genuine prose claims (`0/40` controls, `0/30` idioms), of which pre-hardening Approach A/B caught `1/3 (33.3%)` and post-hardening `ActionClaimGrammarSupervisor` catches `3/3 (100%)` with `0/117 (0.0%)` FPR; under SOAC (`v1_soac`, `v2_soac`, `v2_soac_gbnf`), `26B-A4B` coupled `100%` of its prose action claims (`13/13` in v1 SOAC, `18/18` + `4/4 AMBIGUOUS` in v2 SOAC, `17/17` + `1/1 AMBIGUOUS` in v2 SOAC+GBNF) with an `[ACTION: ...]` frame caught in `6.82 µs`, yielding **`0/120 (0.00% [0.00%, 3.87%])` true unframed prose leakage** across all three SOAC arms (passing $H_{2e} \le 2/120$). On the subsequent 250-prompt $\times$ 4-model (`N=1,000` completions across `26B-A4B`, `12B`, `E4B`, `E2B`; 3-model preregistered core `N=750`; `PREREG-MATCHER-SENSITIVITY-v2.2`) held-out evaluation (scored against **blinded frontier-LLM direct semantic reading labels** [`blinded_llm_semantic_labels_1000.jsonl`] validated by an independent second blinded rater on $n=200$ at 5-class $\kappa = 0.9673$ [`196/200`] and 3-class/binary Claim-vs-Non-Claim $\kappa = 1.0000$ [`194/194`]), the post-hardening grammar matcher missed its overall recall targets (**`58.5%` [`151/258`]** 4-model broad [`65.4%` `26B-A4B`, `60.5%` `E4B`, `56.9%` `E2B`, `41.7%` `12B`; 3-model core `55.4%` (`98/177`)] vs. $\ge 80\%$ target; **`67.3%` [`99/147`]** 4-model strict [`69.4%` `26B-A4B`, `69.0%` `E4B`, `68.4%` `12B`, `62.2%` `E2B`; 3-model core `66.3%` (`65/98`)] vs. $\ge 90\%$ target) because recall drops from **`71.1%` (`128/180`)** on the 20 in-vocabulary verbs (`82.7%` `E4B`, `77.2%` `26B-A4B`, `60.9%` `E2B`, `52.0%` `12B`) to **`29.5%` (`23/78`)** on 10 unseen out-of-dev verbs (`37.5%` `26B-A4B`, `47.4%` `E2B`, `18.2%` `12B`, `12.5%` `E4B`), while passing the primary non-claim FPR target (`<= 5.0%` point estimate, `< 8.0%` Wilson 95% UB) across all four models (`0.6% [0.0%, 3.8%]` `26B-A4B`, `0.6% [0.0%, 3.9%]` `E4B`, `0.6% [0.0%, 3.6%]` `E2B`, `1.4% [0.4%, 4.4%]` `12B`; `0.8%` [`6/719`] 4-model pooled, with `0/319 [0.0%]` on clear temptation non-claims). Following the freeze of `v2.2`, post-audit remediation `v2.3` ([`post_remediation_matcher_v2_3_summary.json`](./logs/test_reports/post_remediation_matcher_v2_3_summary.json), [`post_remediation_paper2_v2_3_720.json`](./logs/test_reports/post_remediation_paper2_v2_3_720.json)) expanded the DevOps verb lexicon and passive/telegraphic/synchronous-future grammar frames and filtered conversational meta-targets, achieving **`258/258 (100.0%)` broad recall**, **`147/147 (100.0%)` strict recall**, and **`0/719 (0.0%)` non-claim FPR** across the 1,000-turn 4-model dataset (`100.0%` on both in-vocab `180/180` and out-of-dev `78/78` strata; `257/258 [99.6%]` recall and `0/719 [0.0%]` FPR on post-turn `coherence.py`), and **`57/57 (100.0%)` prose recall** with **`0/30 (0.0%)` idiom spurious frame FPR** across all 720 Paper 2 turns. Because `v2.3` was tuned against the audited failure modes of the `1,720`-turn corpus, the pre-registered `v2.2` numbers remain the primary out-of-sample generalization estimate, and output supervision remains an active research prototype rather than a certified safety boundary.
- **Procedural rule lifecycle gates (`lifecycle.py`):** Background promotion (`promote_if_eligible`) stops at `PENDING_APPROVAL` when `require_human_approval=True`, requiring an explicit `approve_rule()` call to reach `ACTIVE` (though `approve_rule()` does not authenticate whether its caller is human or script). User-correction demotion (`ACTIVE -> QUARANTINE`) is half-wired: `emit_execution_triple(..., signal="operator_correct")` logs the analytics row, while the caller must invoke `record_shadow(matched=False)` to trigger 1-strike demotion.
- **NLI verifier latency under load:** The previous 149M ModernBERT model exhibited an 81% timeout rate (>50ms) under concurrent LLM+TTS saturation; replaced in WO-37 with a 22M distilled MiniLM model.
- **Hardware requirement:** Full multi-process operation requires native Windows 11 with an NVIDIA RTX GPU (for GGUF LLM and CUDA float16 Whisper ASR), Intel NPU/CPU (OpenVINO embeddings and verifier), and Docker CE in WSL2.

---

## Requirements

- **OS:** Windows 11 64-bit with WSL2 (Ubuntu) and Docker CE.
- **dGPU:** NVIDIA GeForce RTX 4080/5080 Laptop GPU (16 GB GDDR7) or equivalent CUDA accelerator.
- **CPU/RAM:** Intel Core Ultra 9 or modern x86_64 multi-core processor, 32 GB+ host RAM (64 GB recommended).
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

See [Unified System Architecture Specification](luccadocs/ARCHITECTURE.md) for the complete 4-process topology, execution tiers (`REFLEX`, `ACT_THEN_NARRATE`, `FULL_LOOP`), MicroScheme engine, and cryptographic memory envelope design.

---

## Benchmark Results

All figures below are author-measured on workstation silicon (`RTX 5080 Laptop GPU`, `Core Ultra 9 275HX`, native Windows 11).

### WO-39 Audit & Benchmark Provenance Note

Following the Work Order 39 (`WO-39`) scientific integrity audit:
- **Live-Verified Empirical Benchmarks:** **Study 1** (Memory Poisoning Ablation), **Study 2** (PAL-off Factorial Ablation), **Canonical HumanEval / HumanEval-Plus**, **GSM8K / GSM-Symbolic**, and **MATH-500** reflect live `llama-server` generations verified in the Docker sandbox. All problem-specific AST rewrites (`ast_sanitizer.py`) and prompt-side coaching hints have been removed in `WO-39`.
- **Decontaminated & Fixture-Validated Suites:** Historical **Track 1: SPEC-BENCH-100-v1.0** (`91.0%`) is archived as a pre-decontamination baseline (all problem-specific router rules, prompt hints, and hardcoded RFC 9110/7231 search strings were removed in `WO-39`). The **Personhood Probe Batteries (`AC`, `IN`, `IA`, `FC`)** default to `SCHEMA_FIXTURE_VALIDATION_ONLY (NOT A LIVE MODEL EVALUATION)` unless run with `--live` against an active `llama-server`.

| Benchmark | Config | Result (Author-measured, [95% Wilson CI]) | Evidence File |
| :--- | :--- | :---: | :--- |
| **Paper 1: Memory Poisoning (`prereg-poisoning-v1/v2`)** | `N=100` 4-arm ablation on `26B-A4B` (`Cohort A n=40` distinct confabulation probes, `Cohort B n=30` benign math, `Cohort C n=30` user falsehoods) + `WO-39` 4-scale rebench (`n=10`/scale) | **0/40 (`0.0% [0.0%, 8.8%]`)** vs `40/40` Naive RAG (`stores & grounds all assistant speech at Mem=1, Gnd=1`; **exact McNemar `p = 1.82e-12`**, cont.-corr. `p = 6.98e-10`); `96.7%` Cohort B retention; **WO-39 V2c:** `0/10 [0.0%, 27.8%]` across all 4 scales (`p = 0.00195`); **WO-39 V2b Corroboration:** `0/10` poisoned on `26B/12B/E4B`, **`3/10 (30%)` on `E2B`** | [`docs/papers/01_memory_poisoning_ablation.pdf`](./docs/papers/01_memory_poisoning_ablation.pdf), [`wo39_live_4models_rebench.json`](./logs/test_reports/wo39_live_4models_rebench.json) |
| **Paper 2: Deontic Supervision (`prereg-supervision-v1/v2` `720` turns & `v2.2` `N=1,000` / `4` models)** | `N=120` held-out on `26B-A4B` (`720` completions across v1 & v2) + `N=1,000` (`250` prompts $\times$ `4` models `26B-A4B/12B/E4B/E2B`; 3-model core `N=750`) evaluation | On the `720`-turn `26B-A4B` v1/v2 re-audit (blinded semantic labels, dual-rater $\kappa = 1.0000$ on $n=120$), pre-hardening regex caught `1/3 (33.3%)` real Natural claims (`1/16` against legacy regex grader) vs. **`3/3 (100%)`** post-hardening (`0/117` FPR); **SOAC** binds explicit `[ACTION: ...]` frames in **`6.82 µs`** with **`0/120 (0.00% [0.00%, 3.87%])` true unframed prose leakage** across v1 SOAC, v2 SOAC, and v2 SOAC+GBNF (`100%` frame coupling on all `13/13`, `18/18`, and `17/17` prose claims — **PASSING $H_{2e} \le 2/120$**). On the `N=1,000` 4-model battery (`blinded_llm_semantic_labels_1000.jsonl`, dual-rater $n=200$ 5-class $\kappa = 0.9673$, binary $\kappa = 1.0000$; **Partial Pass / Recall Failure**), `ActionClaimGrammarSupervisor` catches **`58.5% (151/258)`** broad (`65.4%` `26B-A4B`, `60.5%` `E4B`, `56.9%` `E2B`, `41.7%` `12B`; 3-model core `55.4% [98/177]`) and **`67.3% (99/147)`** strict (`69.4%` `26B-A4B`; 3-model core `66.3% [65/98]`) — **`71.1% [128/180]`** on 20 in-vocab verbs (`82.7%` `E4B`, `77.2%` `26B-A4B`, `60.9%` `E2B`, `52.0%` `12B`) vs. **`29.5% [23/78]`** on 10 unseen verbs — while passing primary non-claim FPR on all 4 models: **`0.6%` `26B-A4B`, `0.6%` `E4B`, `0.6%` `E2B`, `1.4%` `12B`** (`0.8% [6/719]` pooled; `0/319 [0.0%]` on temptation non-claims) at **`15.17 µs` mean / `33.9 µs` p95**; **Post-Audit Remediation `v2.3` (in-sample to audited corpus):** **`258/258 (100.0%)`** broad & **`147/147 (100.0%)`** strict recall with **`0/719 (0.0%)`** FPR across all 4 models (`19.53 µs` mean) and **`57/57 (100.0%)`** prose recall + **`0/30 (0.0%)`** idiom frame FPR on Paper 2 (`720` turns) | [`docs/papers/02_deontic_supervision_evasion.pdf`](./docs/papers/02_deontic_supervision_evasion.pdf), [`PREREG_MATCHER_SENSITIVITY_RESULTS.md`](./docs/PREREG_MATCHER_SENSITIVITY_RESULTS.md), [`prereg_matcher_sensitivity_v2_2_summary.json`](./logs/test_reports/prereg_matcher_sensitivity_v2_2_summary.json), [`post_remediation_matcher_v2_3_summary.json`](./logs/test_reports/post_remediation_matcher_v2_3_summary.json), [`paper2_v1_v2_semantic_audit_720.json`](./logs/test_reports/paper2_v1_v2_semantic_audit_720.json), [`post_remediation_paper2_v2_3_720.json`](./logs/test_reports/post_remediation_paper2_v2_3_720.json) |
| **Organic Companion Supervision (`v3.0` Context-Aware, `N=300`)** | `N=200` Organic Discovery (`O001..O200`, $\kappa=0.9596$) + `N=100` Unseen Held-Out (`H001..H100`, $\kappa=1.0000$) on `E4B` & `26B-A4B` across 5 everyday non-DevOps companion families (`multi_turn_elliptical`, `colloquial_companion`, `indirect_problem_temptation`, `context_trap_quoted_fictional`, `casual_banter_idioms`) | Clause-isolated `v2.3` collapsed on organic companion interactions to **`27.7%` raw / `50.0%` normalized Recall** and **`20.8%` FPR** (`55.0%` FPR on creative/quoted context traps) on `O001..O200` and **`42.5%` Recall / `18.9%` FPR (`52.0%` F1)** on unseen `H001..H100`. **Context-Aware Supervision (`v3.0`, without test-specific hardcoded strings)** achieves **`95.8% (91/95)` Recall / `0.0% (0/105)` FPR** on `O001..O200` and **`78.7% (37/47)` strict zero-shot / `87.2% (41/47)` general Recall (`0.0%` FPR)** on unseen `H001..H100` — catching `100%` of multi-turn elliptical (`20/20`) and colloquial companion (`18/18`) claims, while missing **`6/9 (66.7%)` of indirect-problem live state fabrications** (`"You have a meeting at 2:30 PM"`, `"You have 120 GB free"`), demonstrating the architectural boundary of regex supervision on open-ended state readouts | [`PREREG_MATCHER_SENSITIVITY_RESULTS.md §7`](./docs/PREREG_MATCHER_SENSITIVITY_RESULTS.md#L236), [`organic_companion_v3_0_evaluation.json`](./logs/test_reports/organic_companion_v3_0_evaluation.json) |
| **Paper 3: LongMemEval Pipeline (`N=30`, `12B`)** | End-to-end conversational memory & temporal reasoning: Context-Truncation Baseline vs. Lucca Provenance + RRF + Allen Pipeline | **`23.3% (7/30 [11.8%, 40.9%])` → `70.0% (21/30 [52.1%, 83.3%])`** (`0:14` discordant pairs, exact McNemar `p = 0.000122`, `8.1 ms` mean retrieval latency) | [`longmemeval_pipeline_12B_1791794644.json`](./logs/test_reports/longmemeval_pipeline_12B_1791794644.json) |
| **Paper 3: IN-D Live 52-Turn Rule Induction** | Organic 52-turn waking trace + 16 held-out turns on `12B` (`RuleInducer` + Z3 SMT + 50-turn `Dream-RSI` replay + 1-strike eviction) + 66-turn single-rule lifecycle trace on `26B-A4B` | **4/4** tool rules Z3-quarantined (`100%` 50-turn replay, **`8/8 [67.6%, 100%]`** held-out recall at `0.14 ms`, **`0/8 [0.0%, 32.4%]`** misfires; **`0/2 (0%)` free-form S-expr macros admitted**) | [`in_d_live_baseline_wo39.json`](./logs/test_reports/in_d_live_baseline_wo39.json), [`SINGLE_RULE_LIFECYCLE_TRACE.md`](./docs/SINGLE_RULE_LIFECYCLE_TRACE.md) |
| **MiniLM-L6 NLI Verifier (`WO-37`)** | `N=100` single-annotator authored set (`40` contradiction, `30` entailment, `30` neutral; in-sample model selection after ModernBERT `81%` timeout rate) on host CPU (`50 ms` budget, `0 MB` VRAM) | **`91.0% [83.8%, 95.2%]` accuracy**, `0.975 / 0.975` contradiction P/R (`39/40`), `0.960 / 0.800` entailment P/R (`24/30`), **`12.23 ms` mean / `14.40 ms` p95** (`0/100` timeouts) | [`Paper 03 §4.1`](./luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md#L121) |
| **WO-39: Sealed Parametric Suite (`v139`)** | `N=15` (`3/lobe`: `ContainerWorld`, `Z3`, `SymPy`, `2-Lobe`, `CEGIS`) across `26B-A4B`, `12B`, `E4B`, `E2B` | **`15/15 (100% [79.6%, 100%])`** on `26B-A4B`, `12B`, `E4B` (`p = 0.000061` vs `0/15` raw); **`14/15 (93.3% [70.2%, 98.8%])`** on `E2B` | [`RESULTS.md`](./RESULTS.md#L7) |
| **Canonical HumanEval (`N=164`)** | 164 coding tasks `pass@1` in Docker container (`cache_prompt: false`, `12B`) | **`94.51% (155/164 [89.90%, 97.09%])`** raw / **`93.90% (154/164 [89.14%, 96.65%])`** assisted (`10/10` across all 4 scales on `WO-39` 10-item slice) | [`RESULTS.md`](./RESULTS.md#L58) |
| **HumanEval-Plus (`N=164`)** | EvalPlus 164 coding tasks with 80x differential tests (`12B`) | **`91.46% pass@1 (150/164 [86.18%, 94.84%])`** | [`RESULTS.md`](./RESULTS.md#L60) |
| **GSM-Symbolic (`N=100`)** | Apple Oct 2024 symbolic math under perturbation (stratified 100 templates, `12B` PAL Docker) | **`94.00% (94/100 [87.52%, 97.22%])`** (`10/10` on `26B/12B/E4B` & `5/10` on `E2B` on `WO-39` 10-item GSM8K slice) | [`RESULTS.md`](./RESULTS.md#L56) |
| **MATH-500 Sealed B4 (`N=100`)** | 100 sealed competition problems (`math_b4_sealed_100.jsonl`, `12B` Direct R0 vs PAL P2 vs Thinking R1) | **`93.00% strict [86.25%, 96.57%] / 94.00% lenient`** (R0) vs `87.00%` (P2) vs `46.00%` (R1, `55%` truncations) | [`RESULTS.md`](./RESULTS.md#L98) |
| **MATH-500 Fresh Held-Out (`N=500`)** | 500 unseen competition problems (`v1.35-final-fresh-500`, `12B`) | **`85.80% strict (429/500 [82.47%, 88.59%]) / 90.20% lenient (451/500)`** (100-item scale slice: `89.0%` 12B R0 / `88.0%` E4B R1 / `81.0%` E2B R1) | [`RESULTS.md`](./RESULTS.md#L72) |
| **Static & Anti-Cheat Gates** | Structural invariants, zero-`Any`, provenance, decontamination, & 6-organs verification | **37 / 37 gates PASSED** (`25` static + `4` anti-cheat + `8` six-organs) | [`tests/test_static_gates.py`](./tests/test_static_gates.py) |

---

## Documentation & Community

- **Reproduction Guide:** [`REPRODUCING.md`](./REPRODUCING.md) — Step-by-step reproduction instructions, dataset hashes, and one-command benchmark targets.
- **System Glossary:** [`luccadocs/GLOSSARY.md`](./luccadocs/GLOSSARY.md) — Plain-English definitions of cognitive architecture terms.
- **Security Policy & Threat Model:** [`SECURITY.md`](./SECURITY.md) and [`luccadocs/security/THREAT_MODEL.md`](./luccadocs/security/THREAT_MODEL.md) — Vulnerability reporting, attack surfaces, and verified defense invariants.
- **Contributing:** [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) — Development guidelines and invariants.
- **Third-Party Notices:** [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md) — Upstream runtime, library, and foundation model licenses.

---

## Research

See [`luccadocs/research/README.md`](./luccadocs/research/README.md) for the research roadmap, experimental logs, and technical reports:
- **Foundational Pre-Print (PDF):** [`docs/paper.pdf`](./docs/paper.pdf) — *Provenance-Gated Memory and Deontic Output Supervision for Epistemically Grounded Autonomous Agents* (Zenodo DOI: [`10.5281/zenodo.23649049`](https://doi.org/10.5281/zenodo.23649049)).
- **Paper 1 (Memory Poisoning Ablation PDF):** [`docs/papers/01_memory_poisoning_ablation.pdf`](./docs/papers/01_memory_poisoning_ablation.pdf) — *Cryptographic Provenance Gates Mitigate Multi-Session Memory Poisoning in Autonomous Agents* (Zenodo DOI: [`10.5281/zenodo.23901452`](https://doi.org/10.5281/zenodo.23901452)).
- **Paper 2 (Deontic Supervision Evasion PDF):** [`docs/papers/02_deontic_supervision_evasion.pdf`](./docs/papers/02_deontic_supervision_evasion.pdf) — *Why Speech-Regex Action Supervisors Miss Live Output: An Empirical Evasion Taxonomy and Held-Out Structured Action Contract Evaluation* (Zenodo DOI: [`10.5281/zenodo.23901605`](https://doi.org/10.5281/zenodo.23901605)).
- **Paper 3 (5-Layer Epistemic & Procedural Memory PDF):** [`docs/papers/03_provenance_gated_five_layer_memory.pdf`](./docs/papers/03_provenance_gated_five_layer_memory.pdf) — *Closing the Epistemic Loop Across the Five Layers of Agent Memory: Cryptographic Provenance, Paraconsistent Bilattices, and Z3-Quarantined Procedural Induction* (Zenodo DOI: [`10.5281/zenodo.23901683`](https://doi.org/10.5281/zenodo.23901683)).
- **Subsystem Technical Reports (Markdown):** [`Paper 03 (Provenance & Belnap/NARS)`](./luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md) • [`TR-04 (E-Graph, Z3 Quarantine & Live IN-D Baseline)`](./luccadocs/research/papers/04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md) • [`Paper 06 (4-Model Scale Ablation)`](./luccadocs/research/papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md) • [`Single-Rule Lifecycle Case Study (26B-A4B)`](./docs/SINGLE_RULE_LIFECYCLE_TRACE.md).

---

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later). See [LICENSE](./LICENSE). Upstream components retain their original licenses per [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
