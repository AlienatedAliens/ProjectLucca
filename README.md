# Project Lucca — Autonomous Neuro-Symbolic Desktop Companion

Project Lucca is an autonomous, local-first desktop companion for Windows workstations that combines real-time voice interaction (Push-to-Talk and energy VAD), symbolic procedural reasoning (MicroScheme LISP engine and Z3 formal verification), and sandboxed execution inside an isolated Docker container with cryptographic, provenance-gated long-term memory.

> **Status:** Single-developer research project. Hardware-specific. All benchmarks author-measured on one machine. No independent reproduction yet.

---

## Known Limitations

- **Self-run benchmarks:** All benchmark figures reported below are author-measured on local workstation silicon; none have been independently reproduced or externally verified.
- **Truth-in-Receipt supervision:** In a 23-utterance live evaluation battery, 1/23 ungrounded action claims was detected (4.3% sensitivity broad / 1/8, 12.5% strict). Output supervision is an active research prototype, not a certified safety boundary.
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

| Benchmark | Config | Result (Author-measured) | Evidence File |
| :--- | :--- | :---: | :--- |
| **Track 1: SPEC-BENCH-100-v1.0** | 100-problem frozen ground-truth cognitive battery (Run 3) | 91.0% (91/100); Path: 100%; Epistemic: 100% | [`RESULTS.md`](./RESULTS.md#L30) |
| **Track 2: Canonical HumanEval** | 164 coding tasks pass@1 in Docker container | 95.73% pass@1 (157 / 164) | [`data/benchmarks/MANIFEST.yaml`](./data/benchmarks/MANIFEST.yaml) |
| **Track 2: GSM8K (PAL Mode)** | 30-item micro-suite via Docker Python | 100.0% (30 / 30) | [`data/benchmarks/MANIFEST.yaml`](./data/benchmarks/MANIFEST.yaml) |
| **Track 2: BBH Consolidated** | 1,000-task Big-Bench Hard unaugmented battery | 92.40% (924 / 1,000) | [`data/benchmarks/MANIFEST.yaml`](./data/benchmarks/MANIFEST.yaml) |
| **Track 3: GSM-Symbolic** | Apple Oct 2024 symbolic math under perturbation | 100.0% (100 / 100) dev / 94.0% stratified 100 | [`RESULTS.md`](./RESULTS.md#L50) |
| **Track 3: HumanEval-Plus** | EvalPlus 164 coding tasks with 80x differential tests | 91.46% pass@1 (150 / 164) | [`RESULTS.md`](./RESULTS.md#L60) |
| **Track 3: MATH-500 Sealed B4** | 100 competition problems via 12B Direct R0 | 93.0% strict / 94.0% lenient | [`data/benchmarks/MANIFEST.yaml`](./data/benchmarks/MANIFEST.yaml) |
| **v1.35: Fresh Held-Out 500** | 500 unseen competition problems (32K ctx + feedback loop) | 85.80% strict / 90.20% lenient | [`RESULTS.md`](./RESULTS.md#L75) |
| **v1.35.6: Multi-Scale Held-Out 100** | Unseen competition math: 12B Direct R0 / E4B R1 / E2B R1 | 89.0% (12B) / 88.0% (E4B) / 81.0% (E2B) | [`RESULTS.md`](./RESULTS.md#L88) |
| **Truth-in-Receipt Live Battery** | Live supervisory detection of ungrounded action claims | 1/23 detected (4.3% sensitivity broad / 1/8, 12.5% strict) | [`luccadocs/funding/PREREG_MATCHER_SENSITIVITY.md`](./luccadocs/funding/PREREG_MATCHER_SENSITIVITY.md) |
| **WO-39: 4-Model Live Rebench** | `26B-A4B`, `12B`, `E4B`, `E2B` across Study 1 V2c/V2b, Sealed Parametric (`v139`), GSM8K PAL, HumanEval, & Security | **100%** across all 7 suites on `26B-A4B`, `12B`, & `E4B` (`0/10` self-poisoning vs `10/10` naive RAG, `p = 0.00195`) | [`RESULTS.md`](./RESULTS.md#L7) |
| **LongMemEval Pipeline (`N=30`)** | End-to-end conversational memory & temporal reasoning (`12B`: Truncation vs. Lucca Provenance + RRF Pipeline) | **23.3% → 70.0%** (`0:14` discordant pairs, McNemar `p = 0.0001`, `8.1 ms` mean retrieval latency) | [`logs/test_reports/longmemeval_pipeline_12B_1791794644.json`](./logs/test_reports/longmemeval_pipeline_12B_1791794644.json) |
| **IN-D Live 52-Turn Rule Induction** | Organic 52-turn waking trace + 16 held-out turns (`RuleInducer` + Z3 SMT + 50-turn `Dream-RSI` replay + single-strike eviction) | **4/4** tool rules Z3-quarantined (`100%` 50-turn replay, **8/8** held-out recall, **0/8** distractor misfires; `0/2` free-form S-expr macros) | [`logs/test_reports/in_d_live_baseline_wo39.json`](./logs/test_reports/in_d_live_baseline_wo39.json) |
| **MiniLM-L6 NLI Verifier (`WO-37`)** | 100-pair semantic contradiction / entailment cross-encoder on host CPU (`50 ms` in-turn budget, `0 MB` VRAM) | **12.23 ms mean / 14.40 ms p95** (`0.975 / 0.975` contradiction P/R, `0/100` timeouts) | [`Paper 03 §4.1`](./luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md#L121) |
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
- **Foundational Pre-Print (PDF):** [`docs/paper.pdf`](./docs/paper.pdf) — *Provenance-Gated Memory and Deontic Output Supervision for Epistemically Grounded Autonomous Agents* (Zenodo DOI: `10.5281/zenodo.23649049`).
- **Paper 1 (Memory Poisoning Ablation PDF):** [`docs/papers/01_memory_poisoning_ablation.pdf`](./docs/papers/01_memory_poisoning_ablation.pdf) — *Cryptographic Provenance Gates Mitigate Multi-Session Memory Poisoning in Autonomous Agents*.
- **Paper 2 (Deontic Supervision Evasion PDF):** [`docs/papers/02_deontic_supervision_evasion.pdf`](./docs/papers/02_deontic_supervision_evasion.pdf) — *Why Speech-Regex Action Supervisors Miss Live Output: An Empirical Evasion Taxonomy and Held-Out Structured Action Contract Evaluation*.
- **Paper 3 (5-Layer Epistemic & Procedural Memory PDF):** [`docs/papers/03_provenance_gated_five_layer_memory.pdf`](./docs/papers/03_provenance_gated_five_layer_memory.pdf) — *Closing the Epistemic Loop Across the Five Layers of Agent Memory: Cryptographic Provenance, Paraconsistent Bilattices, and Z3-Quarantined Procedural Induction* (`LUCCA-TR-2026-03`).
- **Subsystem Technical Reports (Markdown):** [`Paper 03 (Provenance & Belnap/NARS)`](./luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md) • [`TR-04 (E-Graph, Z3 Quarantine & Live IN-D Baseline)`](./luccadocs/research/papers/04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md) • [`Paper 06 (4-Model Scale Ablation)`](./luccadocs/research/papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md).

---

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later). See [LICENSE](./LICENSE). Upstream components retain their original licenses per [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
