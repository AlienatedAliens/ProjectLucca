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
| **Static Architectural Gates** | Structural invariants, zero-`Any`, provenance, staleness lint | 24 / 24 gates PASSED (code 0) | [`tests/test_static_gates.py`](./tests/test_static_gates.py) |

---

## Documentation & Community

- **Reproduction Guide:** [`REPRODUCING.md`](./REPRODUCING.md) — Step-by-step reproduction instructions, dataset hashes, and one-command benchmark targets.
- **System Glossary:** [`luccadocs/GLOSSARY.md`](./luccadocs/GLOSSARY.md) — Plain-English definitions of cognitive architecture terms.
- **Security Policy & Threat Model:** [`SECURITY.md`](./SECURITY.md) and [`luccadocs/security/THREAT_MODEL.md`](./luccadocs/security/THREAT_MODEL.md) — Vulnerability reporting, attack surfaces, and verified defense invariants.
- **Contributing:** [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) — Development guidelines and invariants.
- **Third-Party Notices:** [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md) — Upstream runtime, library, and foundation model licenses.

---

## Research

See [`luccadocs/research/README.md`](./luccadocs/research/README.md) for research roadmap, experimental logs, and technical reports. Research papers are working drafts, not peer-reviewed.

---

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later). See [LICENSE](./LICENSE). Upstream components retain their original licenses per [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
