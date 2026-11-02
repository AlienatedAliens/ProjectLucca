# Project Lucca — Research Papers & Technical Reports

```yaml
doc_status: canonical
as_of: 2026-11-03
release_baseline: v1.47.0 (WO-39)
verification: artifact-sourced (RESULTS.md, V1_RELEASE_AUDIT.md & data/benchmarks/MANIFEST.yaml)
```

> [!IMPORTANT]
> **WO-39 (2026-11-03) Implementation & Decontamination Sync:** All six papers and technical reports in this directory have been synchronized with the `WO-39` codebase state: (1) removal of `SPEC-BENCH-100` prompt/router leaks, hardcoded ARC solvers, `STATIC_RFC_DEFINITIONS`, `mock_calls`, and simulated receipt minting; (2) Organ 1 Belnap $\mathcal{FOUR}$ + OpenNARS Beta$(w^+, w^-)$ unification, fail-closed `ProvenanceGate`, and Study 1 autobiographical memory prompt partitioning (`_render_partitioned_memories`); (3) Organ 2 System 2 $\to$ System 1 myelination via `impasse_backlog` and CBR 4 Rs in `EpisodicCodeCache`; (4) Organ 3 `DreamRetrospective` real trace/impasse induction, `SkillLibrary` shadow sandbox, AST symbol grounding, and ACT-R activation; (5) Organ 4 MCTS + Koza GP crossover, Z3 abductive hole solving across `test_cases`, E-Graph `cost_fn` extraction, and `SpeculativeBDIValidator` AST + Z3 resource verification; and (6) Organ 5–6 parameterized `spatial_dsl` + metamorphic invariance, $k$-order recursive Theory-of-Mind `ContainerWorld`, `decision_labels` conformal calibration, Whisper `"Lucca"` hotword/phonetic normalization, and Hann-windowed OLA pitch shifting.

This directory holds two **submission candidates** and four **technical reports**. None has been peer-reviewed. Each document states its evidence type up front and ends with a "What Is NOT Claimed" section. Historical research notes are in [`luccadocs/archive/2026-10_audits_and_research/research/`](../archive/2026-10_audits_and_research/research/).

---

## 1. Status at a Glance

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
