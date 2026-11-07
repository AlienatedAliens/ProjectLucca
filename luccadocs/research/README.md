# Project Lucca — Research Papers & Technical Reports

```yaml
doc_status: canonical
as_of: 2026-11-07
release_baseline: v1.50.0 (WO-42)
verification: artifact-sourced (RESULTS.md, V1_RELEASE_AUDIT.md & data/benchmarks/MANIFEST.yaml)
```

> [!IMPORTANT]
> **WO-39 – WO-42 (2026-11-07) Implementation, Decontamination & Preprint Series Sync:** All six internal markdown papers/reports in `luccadocs/research/papers/` and the four standalone LaTeX preprints in `papers/01_*` through `papers/04_*` have been synchronized with the `WO-39`–`WO-42` codebase state: (1) removal of `SPEC-BENCH-100` prompt/router leaks, hardcoded ARC solvers, `STATIC_RFC_DEFINITIONS`, `mock_calls`, and simulated receipt minting (`WO-39`); (2) Organ 1–6 bicameral restoration (`WO-39`); (3) frozen Zenodo `v1` preprints `papers/01_memory_poisoning_ablation` (`10.5281/zenodo.23901452`), `papers/02_deontic_supervision_evasion` (`10.5281/zenodo.23901605`), and `papers/03_provenance_gated_five_layer_memory` (`10.5281/zenodo.23901683`); and (4) standalone follow-up preprint `papers/04_clause_level_npu_supervision/main.tex` reporting the `WO-40`–`WO-42` clause-level OpenVINO FP16 NPU supervision suite (`145/150` single-pass locked holdout / `150/150` post-bugfix, `100/100` live 4-model E2E turns, and Scrapling 3-tier stealth web research).

This directory holds two **submission candidates** and four **technical reports**, alongside the repository's four standalone LaTeX preprints in [`papers/`](../../papers/). Each document states its evidence type up front and ends with a "What Is NOT Claimed" section. Historical research notes are in [`luccadocs/archive/2026-10_audits_and_research/research/`](../archive/2026-10_audits_and_research/research/).

---

## 0. Standalone LaTeX Preprint Series (`papers/01_*` through `papers/04_*`)

| Preprint | File | Zenodo DOI / Status | Core Contribution & Empirical Scope |
| :--- | :--- | :--- | :--- |
| **Preprint 01** | [`papers/01_memory_poisoning_ablation/main.tex`](../../papers/01_memory_poisoning_ablation/main.tex) | **`10.5281/zenodo.23901452`** (Frozen `v1` baseline) | Multi-session self-poisoning ablation (`N = 100` paired probes across Cohorts A, B, C): `0/40 (0.0%)` Cohort A self-poisoning under `ProvenanceGate` vs `40/40 (100.0%)` Naive RAG (`p = 6.98e-10`), while documenting the `v1` Cohort C user-misinformation boundary (`30/30`). |
| **Preprint 02** | [`papers/02_deontic_supervision_evasion/main.tex`](../../papers/02_deontic_supervision_evasion/main.tex) | **`10.5281/zenodo.23901605`** (Frozen `v1` baseline) | Held-out action-evasion benchmark (`N = 120` prompts: 50 Temptations, 40 Honest Controls, 30 Idioms): documents regex fragility (`1/16 = 6.25%` strict recall on `v1`) and `SOAC` (`action_claim.gbnf`) sub-10 us structured verification (`16/120 = 13.3%` prose leakage). |
| **Preprint 03** | [`papers/03_provenance_gated_five_layer_memory/main.tex`](../../papers/03_provenance_gated_five_layer_memory/main.tex) | **`10.5281/zenodo.23901683`** (Frozen `v1` baseline) | Five-layer memory architecture (`ProvenanceGate` HKDF HMAC-SHA256 envelopes, SQLite triggers, Belnap $\mathcal{FOUR}$ + OpenNARS Beta$(w^+, w^-)$ truth values, and `MiniLM-L6` NLI verification at `12.23 ms` mean CPU latency). |
| **Preprint 04** | [`papers/04_clause_level_npu_supervision/main.tex`](../../papers/04_clause_level_npu_supervision/main.tex) | **Follow-up Preprint (`WO-40`–`WO-42`)** (Cites Preprints 01–03) | Resolves the open failure modes documented in Preprints 01–03: (1) closes Cohort C user-misinformation absorption from `30/30` to `0/30 (0.0%)` (`p = 1.86e-9`); (2) raises `PREREG-SUPERVISION-HELD-OUT-v2.0` strict recall to `27/27 (100.0%)`; (3) offloads three `33.4M` `MiniLM-L12-H384` classifiers to Intel AI Boost NPU (`0.0 MB` dGPU VRAM), achieving `377/390 (96.7%)` on blind multi-sentence suites, `145/150 (96.7%)` (`150/150` post-bugfix) on single-pass locked holdout (`κ = 1.000`), and `100/100 (100.0%)` across 4 live Gemma 4 models (`E2B`, `E4B`, `12B`, `26B-A4B`); and (4) introduces Scrapling 3-tier stealth web research with DOM prompt-injection sanitization. |

---

## 1. Internal Markdown Technical Reports (`luccadocs/research/papers/`)

| ID | File | Status | One-line claim | Blocking work before submission |
| :--- | :--- | :--- | :--- | :--- |
| **Paper 06** | [`06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md`](./papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md) | **Primary candidate** | On two small Gemma 4 fine-tunes, Thinking beat PAL on held-out competition math (+15 / +20 pp, paired); on a 12B fine-tune PAL did not beat Direct. | None strictly blocking for a workshop. Strongly recommended: sampled-decoding thinking arm at 12B; stock-weights replication. |
| **Paper 03** | [`03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md`](./papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md) | **Secondary candidate** | A storage-layer separation between "what the agent said" and "what it may cite as evidence," enforced by signers and SQLite triggers. | ~~NLI verifier precision/recall & 50 ms timeout reconciliation.~~ **Done (2026-10-20 & WO-37 Phase 2 2026-10-26):** Initial 149M ModernBERT timed out on 81/100 pairs under the 50 ms budget (57.1 ms mean). Replaced with 22M MiniLM-L6 (`models/verifier_minilm`, `data/benchmarks/nli_eval/results_minilm/summary.json`): **12.23 ms mean / 14.40 ms p95, 0/100 timeouts**, 91.0% accuracy (macro F1 0.917), contradiction P/R = 0.975/0.975, entailment P/R = 0.960/0.800. Remaining: second-annotator agreement pass. |
| **TR-01** | [`01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md`](./papers/01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md) | Overview / index | — | Not intended for submission. |
| **TR-02** | [`02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md`](./papers/02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md) | Technical report | Barge-in < 50 ms; 8.58× prefill from prompt suffixing. | Archived per-trial latencies (P50/P95/max); suffix-with-floats control arm; multi-turn cache measurement. |
| **TR-04** | [`04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md`](./papers/04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md) | Design note | A gated lifecycle for agent-authored rules. | An induction-quality evaluation on a synthetic recurring workload. `IN-D = 0`. |
| **TR-05** | [`05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md`](./papers/05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md) | Threat model | Layered policy enforcement for local agent tool use. | Human-labeled C1 calibration; external/adversarial red-team. |

---

## 2. Why These Two

**Paper 06** is the strongest candidate because its core comparisons are *paired within the same weights*, so they survive the fine-tune/quantization confound that undermines every cross-model statement. It uses a dev/held-out split, a pre-registered sealed set, exact McNemar tests, Wilson intervals, a leak disclosure with a 98-item recomputation, and bit-for-bit reproduction under `cache_prompt: false`. The headline is modest and specific — which is what makes it publishable. It fits a short-paper or workshop track on efficient / small-model reasoning or on tool-augmented LLMs.

**Paper 03** is a design-and-mechanism contribution whose central claim (provenance-gated grounding at the storage layer) can be verified by reading the schema and the tests, independent of any benchmark. Its weakness is that every evaluation battery is authored by the project; the paper now says so explicitly. Both the NLI verifier measurement gap and the 50 ms timeout bottleneck (§4.1 of the paper) are closed: after the 2026-10-20 evaluation showed the 149M ModernBERT classifier timing out on 81/100 pairs under the 50 ms budget (57.1 ms mean CPU latency), WO-37 Phase 2 (2026-10-26) replaced it with the 22M MiniLM-L6 cross-encoder (`models/verifier_minilm`, `data/benchmarks/nli_eval/results_minilm/summary.json`), achieving 12.23 ms mean / 14.40 ms p95 latency on CPU with 0/100 timeouts, 91.0% accuracy, and 0.975/0.975 contradiction P/R. The remaining caveat is single-annotator labeling on `pairs_v1.jsonl`. It fits a workshop on trustworthy or safe LLM agents, or on agent memory.

The four TRs document real engineering and are useful as supplementary material or as a repository a reviewer can inspect, but none currently has an evaluation that would carry a standalone submission.

---

## 3. Recommended Pre-Submission Work, Ranked

Ordered by expected impact on acceptance odds for **Paper 06** first, then **Paper 03**. All run on the existing workstation.

1. **Sampled-decoding Thinking arm at 12B (Paper 06).** Rerun R1 on Dev-100 and B4 Sealed 100 with the model card's recommended temperature and a repetition penalty. Either it recovers (and the confounded greedy result can be dropped) or it does not (and becomes a real finding). Estimated cost: two ~2.5 h GPU runs.
2. **Stock-weights replication of the within-model grid (Paper 06).** Rerun R0/P2/R1 on Held-Out 100 with stock instruction-tuned Gemma 4 at 2B / ~4.5B / 12B. If the within-model ordering holds, the paper gains a robustness section; if the cross-model gap narrows, the "phase shift" language — already removed — stays removed. This is the most expensive item (~3 models × 3 arms × 100 items).
3. ~~**NLI verifier precision/recall & 50 ms timeout reconciliation (Paper 03).**~~ **Completed 2026-10-20 & 2026-10-26 (WO-37 Phase 2).** 100 hand-labeled pairs (`data/benchmarks/nli_eval/pairs_v1.jsonl`) evaluated via `scripts/eval_nli_precision_recall.py` on CPU. Initial 149M ModernBERT: 93.0% accuracy at 500 ms (`results_cpu_t500/`), but 81/100 timeouts at 50 ms (`results/`, mean 57.1 ms). Replaced in WO-37 Phase 2 with 22M MiniLM-L6 (`models/verifier_minilm`, `results_minilm/summary.json`): **12.23 ms mean / 14.40 ms p95, 0/100 timeouts**, 91.0% accuracy, macro F1 0.917, contradiction P/R = 0.975/0.975, entailment P/R = 0.960/0.800. Remaining follow-up: second-annotator agreement pass.
4. **Equal-budget CRUXEval baseline (TR-01 index).** Give the Direct arm the same number of attempts and the same verifier as CEGIS. Not needed for either submission, but required before the 70.25% → 82.75% figure is cited anywhere external.
5. **Audit the E4B/E2B Direct-math prompt, extractor, and grader (Paper 06).** Before attributing 51–52% to the model, spot-check 20 failures per model for extraction or formatting artifacts. If a harness bug is found, the within-model deltas change.

---

## 4. Live Literature & Peer Architecture Survey

- **[`2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md`](./2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md):** Documentation-based survey of contemporaneous agent-memory systems (`qca-cycle`, `nmem`, `agidb`, `NeuSymMS`, `The EpisTwin`). No peer system was executed; comparisons are feature-level only.
