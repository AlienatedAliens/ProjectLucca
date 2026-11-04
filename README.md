# Project Lucca — Autonomous Neuro-Symbolic Desktop Companion

Project Lucca is an autonomous, local-first desktop companion for Windows workstations that combines real-time voice interaction (Push-to-Talk and energy VAD), symbolic procedural reasoning (MicroScheme LISP engine and Z3 formal verification), and sandboxed execution inside an isolated Docker container with cryptographic, provenance-gated long-term memory.

> **Status:** Single-developer research project. Hardware-specific. All benchmarks author-measured on one machine. No independent reproduction yet.

---

## Known Limitations

- **Self-run benchmarks:** All benchmark figures reported below are author-measured on local workstation silicon; none have been independently reproduced or externally verified.
- **Truth-in-Receipt supervision:** On the initial `N=200` developmental transcripts (`E2B/E4B`), the legacy 1P matcher caught `1/23 (4.3%)` strict action claims before hardening and `23/23 (100%)` in-sample after hardening (`0/100` control FPs, `3/52` temptation non-claim FPs). On the `N=120` held-out battery (`26B-A4B`), the Oct 25 pre-hardening run reported `1/16 (6.25%)` under a regex ground-truth grader (`primary_audit_ground_truth`) that mislabeled `14` explanatory gerunds (`9` honest controls, `3` idioms, `2` how-to guides) as action claims; on the audited `predictions.jsonl` transcripts, the hardened `TruthInReceiptMatcher(enable_grammar_channel=True)` catches **`3/3 (100% [31.0%, 100%])`** real ungrounded action claims (`H_T03, H_T04, H_T47`) with **`0/117 (0.0% [0.0%, 3.96%])` false positives** (`81.7 µs`/turn; note that `n=3` positives is a small sample because `26B-A4B` refused `47/50` temptation prompts). Output supervision remains an active research prototype, not a certified safety boundary.
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
| **Paper 2: Deontic Supervision (`prereg-supervision-v1/v2`)** | `N=120` held-out evaluation on `26B-A4B` (vs. `N=200` in-sample `E4B/E2B`: `1/23 [4.3%]` pre-hardening → `23/23 [100%]` post-hardening, `0/100` control FPs) | Legacy pre-hardening regex caught `1/16 (6.25%)` against the v1 regex grader (`14/16` grader labels were gerund FPs on honest controls/idioms/how-tos; `17/17` v2 `soac_gbnf` prose-leakage flags were also gerund FPs). On audited held-out transcripts (`predictions.jsonl`), hardened `TruthInReceiptMatcher` catches **`3/3 (100% [31.0%, 100%])`** true ungrounded claims (`n=3` small positive sample) with **`0/117 (0.0% [0.0%, 3.96%])` FPR** in **`81.7 µs`/turn**; **SOAC** binds explicit frames in **`6.82 µs`** | [`docs/papers/02_deontic_supervision_evasion.pdf`](./docs/papers/02_deontic_supervision_evasion.pdf), [`supervision_heldout_audit_wo39.json`](./logs/test_reports/supervision_heldout_audit_wo39.json) |
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
