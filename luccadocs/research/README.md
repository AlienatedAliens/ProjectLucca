# Project Lucca — Research Papers & Technical Reports

```yaml
doc_status: canonical
as_of: 2026-10-19
release_baseline: v1.45.0 (WO-36)
verification: artifact-sourced (RESULTS.md, V1_RELEASE_AUDIT.md & data/benchmarks/MANIFEST.yaml)
```

This directory holds two **submission candidates** and four **technical reports**. None has been peer-reviewed. Each document states its evidence type up front and ends with a "What Is NOT Claimed" section. Historical research notes are in [`luccadocs/archive/2026-10_audits_and_research/research/`](../archive/2026-10_audits_and_research/research/).

---

## 1. Status at a Glance

| ID | File | Status | One-line claim | Blocking work before submission |
| :--- | :--- | :--- | :--- | :--- |
| **Paper 06** | [`06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md`](./papers/06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md) | **Primary candidate** | On two small Gemma 4 fine-tunes, Thinking beat PAL on held-out competition math (+15 / +20 pp, paired); on a 12B fine-tune PAL did not beat Direct. | None strictly blocking for a workshop. Strongly recommended: sampled-decoding thinking arm at 12B; stock-weights replication. |
| **Paper 03** | [`03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md`](./papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md) | **Secondary candidate** | A storage-layer separation between "what the agent said" and "what it may cite as evidence," enforced by signers and SQLite triggers. | ~~NLI verifier precision/recall on a small hand-labeled set (≈100 pairs).~~ **Done (2026-10-20):** 100-pair single-annotator set measured — contradiction P/R = 1.000/1.000 at 500 ms timeout (93.0% accuracy, macro F1 0.942), but the production 50 ms timeout degrades 81% of pairs to `UNCERTAIN` on CPU (mean latency 57 ms), collapsing effective contradiction recall to 0.075. Remaining: second-annotator agreement pass; reconcile timeout budget with measured latency (or move verifier to NPU). |
| **TR-01** | [`01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md`](./papers/01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md) | Overview / index | — | Not intended for submission. |
| **TR-02** | [`02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md`](./papers/02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md) | Technical report | Barge-in < 50 ms; 8.58× prefill from prompt suffixing. | Archived per-trial latencies (P50/P95/max); suffix-with-floats control arm; multi-turn cache measurement. |
| **TR-04** | [`04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md`](./papers/04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md) | Design note | A gated lifecycle for agent-authored rules. | An induction-quality evaluation on a synthetic recurring workload. `IN-D = 0`. |
| **TR-05** | [`05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md`](./papers/05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md) | Threat model | Layered policy enforcement for local agent tool use. | Human-labeled C1 calibration; external/adversarial red-team. |

---

## 2. Why These Two

**Paper 06** is the strongest candidate because its core comparisons are *paired within the same weights*, so they survive the fine-tune/quantization confound that undermines every cross-model statement. It uses a dev/held-out split, a pre-registered sealed set, exact McNemar tests, Wilson intervals, a leak disclosure with a 98-item recomputation, and bit-for-bit reproduction under `cache_prompt: false`. The headline is modest and specific — which is what makes it publishable. It fits a short-paper or workshop track on efficient / small-model reasoning or on tool-augmented LLMs.

**Paper 03** is a design-and-mechanism contribution whose central claim (provenance-gated grounding at the storage layer) can be verified by reading the schema and the tests, independent of any benchmark. Its weakness is that every evaluation battery is authored by the project; the paper now says so explicitly. The NLI verifier measurement gap (§4.1 of the paper) was closed on 2026-10-20 with a 100-pair hand-labeled evaluation (`scripts/eval_nli_precision_recall.py`): the classifier itself is strong (contradiction P/R = 1.000/1.000 at a 500 ms timeout), but the production 50 ms timeout fails open on 81% of pairs on this CPU, so the paper's `<25 ms` latency claim is now flagged as unmet on this hardware. The remaining caveats are the single-annotator labeling and the timeout/latency reconciliation. It fits a workshop on trustworthy or safe LLM agents, or on agent memory.

The four TRs document real engineering and are useful as supplementary material or as a repository a reviewer can inspect, but none currently has an evaluation that would carry a standalone submission.

---

## 3. Recommended Pre-Submission Work, Ranked

Ordered by expected impact on acceptance odds for **Paper 06** first, then **Paper 03**. All run on the existing workstation.

1. **Sampled-decoding Thinking arm at 12B (Paper 06).** Rerun R1 on Dev-100 and B4 Sealed 100 with the model card's recommended temperature and a repetition penalty. Either it recovers (and the confounded greedy result can be dropped) or it does not (and becomes a real finding). Estimated cost: two ~2.5 h GPU runs.
2. **Stock-weights replication of the within-model grid (Paper 06).** Rerun R0/P2/R1 on Held-Out 100 with stock instruction-tuned Gemma 4 at 2B / ~4.5B / 12B. If the within-model ordering holds, the paper gains a robustness section; if the cross-model gap narrows, the "phase shift" language — already removed — stays removed. This is the most expensive item (~3 models × 3 arms × 100 items).
3. ~~**NLI verifier precision/recall (Paper 03).**~~ **Completed 2026-10-20.** 100 hand-labeled pairs (`data/benchmarks/nli_eval/pairs_v1.jsonl`) evaluated via `scripts/eval_nli_precision_recall.py` on CPU. Clean run (500 ms timeout): 93.0% accuracy, macro F1 0.942, contradiction P/R = 1.000/1.000. Production run (50 ms timeout): 81/100 pairs degraded to `UNCERTAIN` (mean latency 57 ms > 50 ms budget), effective contradiction recall 0.075. Artifacts: `data/benchmarks/nli_eval/results_cpu_t500/` and `data/benchmarks/nli_eval/results/`. Follow-ups: second-annotator agreement pass; raise the production timeout or move the verifier to the NPU.
4. **Equal-budget CRUXEval baseline (TR-01 index).** Give the Direct arm the same number of attempts and the same verifier as CEGIS. Not needed for either submission, but required before the 70.25% → 82.75% figure is cited anywhere external.
5. **Audit the E4B/E2B Direct-math prompt, extractor, and grader (Paper 06).** Before attributing 51–52% to the model, spot-check 20 failures per model for extraction or formatting artifacts. If a harness bug is found, the within-model deltas change.

---

## 4. Live Literature & Peer Architecture Survey

- **[`2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md`](./2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md):** Documentation-based survey of contemporaneous agent-memory systems (`qca-cycle`, `nmem`, `agidb`, `NeuSymMS`, `The EpisTwin`). No peer system was executed; comparisons are feature-level only.
