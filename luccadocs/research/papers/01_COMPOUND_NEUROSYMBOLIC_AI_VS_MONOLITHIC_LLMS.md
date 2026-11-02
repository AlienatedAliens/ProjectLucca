# Technical Report TR-01: Project Lucca — Architecture Overview and Benchmark Index
## A Local, Auditable, Fail-Closed Compound Agent on a Single 16 GiB Laptop GPU (Overview; Not a Standalone Submission)

```yaml
doc_status: canonical
as_of: 2026-11-03
release_baseline: v1.47.0 (WO-39)
submission_status: overview_only (defers all empirical claims to Paper 06, Paper 03, and RESULTS.md)
verification: artifact-sourced (RESULTS.md & data/benchmarks/MANIFEST.yaml)
```

**Authors:** Project Lucca Architecture & Engineering Research Group
**Date:** November 3, 2026 (`v1.47.0` / `WO-39` Baseline)
**Hardware Platform:** NVIDIA GeForce RTX 5080 Laptop GPU (16,303 MiB GDDR7 VRAM, `Disp.A: Off`), Intel Core Ultra 9 275HX (24 cores), Intel AI Boost NPU (OpenVINO), 64 GB DDR5-5600

---

## 1. Purpose and Status

This report is an **index and overview**, not a results paper. It describes the architecture of Project Lucca at `v1.47.0` (`WO-39`), lists every benchmark the project has run with a pointer to the artifact and the paper that analyzes it, and states — once, in one place — the honesty boundaries that apply to all of them.

Empirical claims live in two places and nowhere else:
- **Paper 06** ([`06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md`](./06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md)) for all MATH-500 / GSM-Symbolic / HumanEval arm comparisons and the paired statistics.
- **Paper 03** ([`03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md`](./03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md)) for the memory-provenance mechanism and its authored batteries.

Papers 02, 04, and 05 are technical reports describing subsystems (audio concurrency, rule lifecycle, sandbox policy); they document mechanisms and test coverage and do not make benchmark claims beyond what [`RESULTS.md`](../../../RESULTS.md:1) records.

**Changes from prior versions of this document.** Earlier drafts of TR-01 carried a table of published bare-weights scores for the Gemma 4 family and competitor models attributed to vendor reports we could not locate or verify. That table has been removed; no external-model baseline numbers appear in this report. Earlier drafts also stated a 12B thinking-mode "collapse" as a finding, mislabeled a dev-split E2B GSM-Symbolic result as a stratified-template result, and led with the peak rather than mean Spec-100 score; all three are corrected below.

### 1.1 WO-39 (2026-11-03) Implementation & Decontamination Sync
Work Order 39 (`WO-39`: Total Decontamination & Bicameral Mind Restoration) audited and remediated benchmark contamination and stubbed cognitive organs across the codebase:
1. **Benchmark Decontamination:** Removed `SPEC-BENCH-100` prompt/router leaks from `prompt_builder.py` and `heuristic.py`, deleted the 8 hardcoded ARC solver functions (`solve_arc_task_1..8`) from `spatial_dsl.py`, stripped `STATIC_RFC_DEFINITIONS` and `mock_calls` from `search_tool.py` and `rpc.py`, removed problem-specific magic constants from `mcts.py` (`UNIVERSAL_NUMERIC_CONSTANTS = [0, 1, 2, 3, -1]`), removed `run_python_simulated` fake receipt minting from `orchestrator.py`, and removed hardware spoofing strings from `system_tools.py` and `pipeline_tracer.py`.
2. **Six General Reasoning Organs Restored:**
   - **Organ 1 (Epistemic & Truth-Maintenance Kernel):** Unified Belnap $\mathcal{FOUR}$ with OpenNARS/Beta$(w^+, w^-)$ evidence counts (`positive_evidence`, `negative_evidence`, `nars_frequency`, `nars_confidence`) in `cascade.py`, enforced fail-closed `ProvenanceGate.is_content_corroborated(None, ...) -> False` and removed the `"<source> asserts <claim>"` regex bypass in `gate.py`, and implemented Study 1 autobiographical memory partitioning (`_render_partitioned_memories`) in `prompt_builder.py`.
   - **Organ 2 (Bicameral Myelination & CBR):** Wired waking-to-sleep myelination via `cognitive_outcome_sink` and `impasse_backlog` in `orchestrator.py`, and implemented the full 4-R Case-Based Reasoning cycle (`retrieve_precedent`, `adapt_and_reuse`, `revise_solution`, `retain_episode`) in `EpisodicCodeCache`.
   - **Organ 3 (Wake-Sleep Consolidation & Skill Library):** Replaced `:code "print(1)"` stubs in `DreamRetrospective` with real trace & `impasse_backlog` extraction, wired `RuleInductionEngine` to `DreamCoderMiner` + `EGraph`, and upgraded `SkillLibrary` (`reasoning/skills.py`) with `verify_in_shadow_sandbox`, `_check_ast_symbol_grounding`, NARS $(w^+, w^-)$ scoring, and ACT-R base-level + spreading activation.
   - **Organ 4 (Neurosymbolic Program Synthesis & Deontic Verification):** Upgraded `ASTHoleMCTSEngine` with Koza GP subtree crossover/mutation over `test_cases`, `BackwardAbductionSolver.solve_holes_z3` thread-safe Z3 solving across `test_cases`, `EGraph.extract_best` using `cost_fn`, `DreamCoderMiner` macro expansion prior to Z3 verification, `SMTVerifier` arithmetic/division safety, and `SpeculativeBDIValidator` Python AST + Z3 resource bound verification.
   - **Organ 5 (General Spatial & Mereotopological Reasoning):** Replaced hardcoded ARC solvers with general parameterized `rotate_grid`/`reflect_grid`/`translate_grid`/`crop_grid`/`overlay_grid` primitives in `spatial_dsl.py` and enforced `check_metamorphic_invariance` in `spatial_scheme.py`.
   - **Organ 6 ($k$-Order ToM, Conformal Calibration & Audio DSP):** Unified `ContainerWorld` (`container_world.py`) with $k$-order recursive Theory-of-Mind perspective filtering (`_project_world_for_observer` + `query_recursive`), joined `decisions` with `decision_labels` (`POS`/`NEG`/`INDETERMINATE`) in `calibration.py`, added `ast.parse` preflight validation in `git_dag.py`, added Whisper `"Lucca"` hotword/phonetic wake-word normalization (`asr.py`, `stt.py`), and implemented Hann-windowed overlap-add (OLA) pitch shifting (`apply_pitch_shift` in `dsp_chain.py`).

---

## 2. What the System Is

Project Lucca is a locally hosted desktop agent whose design goal is **auditability under failure**: every action is signed, every memory write is provenance-gated, every tool call passes a schema and a fail-closed policy check, and every neurosymbolic result carries a receipt. The LLM is treated as a replaceable component.

### 2.1 Neural substrate (`D-BRAIN-05`, `D-ROUT-02`)
Four GGUF tiers served by native Windows `llama-server.exe`, one resident at a time, all `Q6_K` weights with `q8_0` KV cache ([`models/MANIFEST.json`](../../../models/MANIFEST.json:1)):

| Tier | File | Notes |
| :--- | :--- | :--- |
| 0 | `gemma-4-26B-A4B-it-heretic.Q6_K.gguf` | MoE, 4B active, `ngl=28`, `ctx=32768`, `--spec-type ngram-mod` |
| 1 | `gemma-4-12b-heretic-Q6_K.gguf` | Dense 12B, 9,972 MiB resident |
| 2 | `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` | Dense ~4.5B effective, 4,382 MiB |
| 3 | `Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf` | Dense ~2B effective, imatrix quant, Sinhala bilingual fine-tune, 2,260 MiB |

All four are **community abliterated fine-tunes**, not stock Google weights. This matters for every cross-tier comparison (see §4.1).

### 2.2 Reasoning lobes (container-isolated, `D-AUD-13`)
- [`PythonCEGISEngine`](../../../src/lucca/reasoning/cegis_python.py:90): generates a program, executes it in the persistent `lucca-file-sandbox` Docker container, and on failure feeds the traceback back for one repair turn. Includes a dual-formulation check (`SYMBOLIC` + `BRUTE_FORCE` consensus) and an AST preflight pass ([`ast_sanitizer.py`](../../../src/lucca/sandbox/ast_sanitizer.py:242)) that rewrites common SymPy misuse before first execution and blocks `eval`/`exec`/`compile`/`getattr` bypasses.
- [`UnshackledCEGISEngine`](../../../src/lucca/reasoning/cegis_unshackled.py:717): grid-abduction variant with an object-level `GridDiff` (Organ A mereotopology, [`mereo.py`](../../../src/lucca/reasoning/relational/mereo.py:1)), general parameterized spatial primitives ([`spatial_dsl.py`](../../../src/lucca/reasoning/spatial_dsl.py:1)), metamorphic invariance verification ([`spatial_scheme.py`](../../../src/lucca/reasoning/spatial_scheme.py:1)), and deterministic AST mutators, batch-evaluated in one container round-trip.
- Z3 SMT ([`smt_verifier.py`](../../../src/lucca/reasoning/smt_verifier.py:1)) with arithmetic/division safety and a grammar-constrained constraint compiler for small models; [`ContainerWorld`](../../../src/lucca/sandbox/container_world.py:1) for $k$-order recursive Theory-of-Mind belief-state simulation (`_project_world_for_observer` + `query_recursive`); Allen interval algebra ([`allen.py`](../../../src/lucca/reasoning/relational/allen.py:1)) for temporal queries.
- [`CognitiveOutcomeSink`](../../../src/lucca/core/cognitive_sink.py:1) (`WO-36` & `WO-39`): signs an `ASSISTANT_ACTION` receipt for each solver outcome, persists multi-turn repair episodes to [`EpisodeRecall`](../../../src/lucca/core/episode_recall.py:36) and [`EpisodicCodeCache`](../../../src/lucca/memory/episodic_code_cache.py:1) (4-R CBR), and feeds unresolved impasses into `Orchestrator.impasse_backlog` for sleep-phase `DreamRetrospective` consolidation.

### 2.3 Memory, routing, actuation
Described in Papers 03, 05, and 04 respectively. Hardware partition: the dGPU holds the LLM weights and KV cache plus a small CUDA float16 Whisper ASR model (`distil-small.en`, ~+555 MiB; CPU int8 fallback); TTS, VAD, and embeddings run on the CPU; the OpenVINO MiniLM-L6 NLI verifier (`models/verifier_minilm`) runs CPU-default (NPU-eligible; measured 12.23 ms mean / 14.40 ms p95 per pair on CPU with 0/100 timeouts under 50 ms — see Paper 03 §4.1). Display composition runs on the integrated Intel GPU.

---

## 3. Benchmark Index

Every row points to a committed artifact. Figures are copied from [`RESULTS.md`](../../../RESULTS.md:1) or [`data/benchmarks/MANIFEST.yaml`](../../../data/benchmarks/MANIFEST.yaml:1); interpretation is deferred to the cited paper or marked *unanalyzed*.

| Suite | Model / Arm | Result | Artifact | Analysis | Caveat |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **MATH-500 Held-Out 100** | 12B R0 / E4B R1 / E2B R1 | 89.0% / 88.0% / 81.0% strict | `logs/test_reports/pal_off_ablation/*` | Paper 06 §3 | Within-model arm comparisons clean; cross-model descriptive only |
| **MATH-500 B4 Sealed 100** | 12B R0 / P2 / R1 | 93.0% / 87.0% / 46.0% strict | `logs/test_reports/b4_sealed/*` | Paper 06 §3.5 | Pre-registered, zero exposure; R1 greedy-confounded |
| **MATH-500 Fresh 500** | 12B PAL-with-feedback | 85.80% strict / 90.20% lenient (429 / 451 of 500) | `logs/test_reports/checkpoint_math500_v1.35-final-fresh-500.json` | Paper 06 fn.**** | Single arm, single run; lines 1–100 overlap the Held-Out 100; not comparable to R0 |
| **GSM-Symbolic (100 stratified templates)** | 12B PAL | 94.0% (94/100) `[87.5%, 97.2%]` | `logs/test_reports/gsm_symbolic_100_templates.json` | Paper 06 Table 1 | Bit-for-bit reproduced under `cache_prompt: false` |
| **GSM-Symbolic (100 stratified templates)** | E4B PAL / E2B PAL | 94.0% / 82.0% | `gsm_symbolic_100_templates_e4b.json` / `_e2b.json` | Paper 06 fn.‡ | — |
| **GSM-Symbolic (dev grid, pal_off)** | E2B PAL vs R0 | 91.0% vs 81.0% (+10 pp, $p=0.021$) | pal_off grid | Paper 06 Table 1 | **Dev split, not stratified templates** (corrected label) |
| **GSM8K full** | 12B PAL | 95.75% (1,263/1,319) | `gsm8k_pal_full_1319_v1_3` | — | Single arm; no Direct baseline run on full set |
| **HumanEval canonical** | 12B raw / assisted | 94.51% / 93.90% (155 / 154 of 164) | `logs/test_reports/humaneval_canonical_*_164.json` | Paper 06 §2.6 | Paired; assisted preflight showed no detectable benefit at 12B |
| **HumanEval-Plus** | 12B | 91.46–92.07% (150–151/164, 3 runs) | `humaneval_plus_v1_35_6` | — | — |
| **BBH-4 subsets** | 12B direct | 92.40% (924/1,000) | `bbh4_bare_1000_v1_3` | — | 4 of 27 subsets; full-27 artifact exists, unanalyzed |
| **CRUXEval-Input (full 400)** | Tier 0 CEGIS vs Direct | 82.75% vs 70.25% (`0:50` discordant) | `logs/test_reports/full_uncurated/cruxeval_input_400_full_tier0.json` | *unanalyzed* | **Not equal-budget**: CEGIS arm had a verifier and a second attempt; Direct had one attempt and no verifier. Lift is an upper bound until an equal-budget baseline is run |
| **AIME 2024 (N=10)** | 12B CEGIS vs greedy Thinking | 8/10 vs 1/10 | `aime_sympy_diagnostic_12B_V138_*.json` | *diagnostic only* | N=10, greedy decoding, no repetition penalty; not a headline |
| **Spec-100 (internal)** | 12B / E4B / E2B, $T=0.6$ | **84.0% mean** (82–86% over 4 runs) / 85.0% / 81.0% | `data/eval/audit_results_100_gemma4-*.json` | Paper 06 Table 1 | Internal suite; historical runs prior to `WO-39` Milestone 1.1 prompt/router decontamination |

---

## 4. Honesty Boundaries Common to All Reports (`D-DOC-01`)

1. **Fine-tune / quantization confound.** The three dense tiers differ in parameter count, fine-tune lineage, and quantization recipe simultaneously. No cross-tier number in any report should be read as an effect of model size until the within-model grid is rerun on stock weights (Paper 06 §5.1).
2. **Non-significance is not equivalence.** $N=100$ paired tests have ~30% power for a 5-point gap. "Not significant" means "no evidence of difference at this sample size."
3. **Equal-budget baselines are missing for CEGIS.** The CRUXEval and AIME lifts compare a two-attempt-with-verifier arm against a one-attempt-no-verifier arm. An equal-budget baseline (same attempts, same verifier) has not been run; until it is, those lifts are upper bounds.
4. **Greedy thinking-mode numbers are confounded.** Every 12B thinking-mode result was produced at $T=0.0$ without repetition penalty and shows 44–55% ceiling truncation. They are negative observations about that configuration, not about thinking mode.
5. **Internal and authored suites are not benchmarks (`WO-39` disclosure).** Spec-100, the confabulation battery, the security batteries, and the TTS guard battery were written by the project. In `WO-39` Milestone 1.1, benchmark-specific prompt hints (`prompt_builder.py`) and router triggers (`heuristic.py`) for `SPEC-BENCH-100`, along with `STATIC_RFC_DEFINITIONS` in `search_tool.py` and the 8 hardcoded ARC solvers in `spatial_dsl.py`, were removed so that live evaluations measure genuine general reasoning.
6. **Dev-slice shrinkage.** Where both a curated dev slice and a full/uncurated split exist, the full split has scored 11–17 points lower (CRUXEval 92–94% → 82.75%; ConceptARC 43.75% → 28.6%). Only full or pre-registered splits are cited as results.
7. **Not yet measured.** Equal-budget CEGIS baseline; sampled-decoding thinking at 12B; stock-weights replication; `SPIKE-A` live sensitivity; `<tool_fit_check>` on BFCL irrelevance; external red-team of the sandbox.
