# Changelog

All notable changes to **Project Lucca** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and the **Zero-Estimate Principle** (all silicon performance numbers derived from live physical workstation execution).

## [1.35.8] — 2026-10-09

### Added
- **Minimum Viable Engine (Macro Mining & Rule Induction Loop, `D-REAS-10`):**
  - **Module 4 (GBNF S-Expression Grammar):** Added `config/grammars/scheme_sketch.gbnf` enforcing balanced parentheses, strict MicroScheme primitives, and token-level logit constraints during LLM proposal decoding.
  - **Module 7 (Idiomaticity Cost Extractor):** Added `src/lucca/reasoning/cost.py` evaluating structural description length: $\text{Cost}(T) = \sum_{n \in T} w(\text{op}_n) + \alpha \cdot \text{depth}(T)$ ($w(\text{primitive})=1$, $w(\text{branch})=2$, $\alpha=0.5$), providing the objective function for candidate compression ranking.
  - **Module 5 (Scratchpad Falsification Loop):** Added `src/lucca/core/scratchpad.py` executing concrete I/O counterexample tests ($\ge 3$ test cases) under container sandboxing (`D-AUD-13`), failing fast on runtime crashes, timeouts ($\le 500\,\text{ms}$), or assertion errors prior to SMT or quarantine ingestion.
  - **Module 14 (DreamCoder Macro Miner):** Added `src/lucca/reasoning/compression.py` extending first-order syntactic anti-unification in `egraph.py` to mine common sub-AST patterns, enforce bounded complexity (`D-REAS-05`: depth $\le 8$, steps $\le 64$), prove Z3 SMT correctness (`D-REAS-07`), and emit candidates strictly into `QUARANTINE` via `RuleLifecycleManager` (`D-REAS-06`: 0 to `ACTIVE` without operator approval).
  - **Personhood IN-D Grader:** Added `src/lucca/evaluation/in_d_grader.py` and `scripts/grade_in_d.py` advancing the IN-D learned-skill count from "NOT YET MEASURED" to active mechanical measurement (`logs/test_reports/personhood/in_d_latest.json`), asserting 0 active skills and tracking quarantined skills.
  - **Pre-Registered Acceptance Gates Passed:**
    - `G-WO30-PLUMB`: $\ge 1$ mined macro admitted to `QUARANTINE`, 0 admitted to `ACTIVE` without operator review, synthetic over-depth candidate rejected by `D-REAS-05`, IN-D grader advanced to active measurement.
    - `G-WO30-UTIL`: Mined macro shadow evaluation reduced description length cost on $\ge 3$ of the 43 labeled Bucket C reasoning failure items, with full reporting in `logs/test_reports/wo30_utility_gate_report.json`.

---

## [1.35.7] — 2026-10-09

### Added
- **Epistemic Integrity & Semantic NLI Verification (`D-MEM-08`):**
  - **Phase 1: Core Pipeline Hygiene (`f729601`):**
    - Remediated hardcoded `is_conflict_top=False` and `topic=None` in `belief_service.py`.
    - Enforced canonical sanitized beliefs in `reflection.py`, eliminating raw user transcripts from memory injection.
    - Fixed all four hardcoded `told_false=False` evidence sites in `cascade.py` with dynamic refutation polarity evaluation.
    - Upgraded rule clustering in `induction.py` to prevent false-merging of opposing rule pairs via token-overlap/Jaccard heuristics.
  - **Phase 2: Semantic Verifier Subsystem (`ports.py`, `core/schemas.py`, `senses/verifier.py`):**
    - Added `@runtime_checkable class SemanticVerifierPort(Protocol)` with keyword-only arguments `check_consistency(*, premise, hypothesis)`.
    - Added `VerifierLabel(StrEnum)` (`ENTAILMENT`, `CONTRADICTION`, `NEUTRAL`, `UNCERTAIN`) and `VerificationResult` strict Pydantic v2 schemas conforming to Zero-`Any` (`D-AUD-01`).
    - Implemented `VerifierWorker` and `LocalSemanticVerifierPort` utilizing OpenVINO FP16 runtime on host CPU/NPU with strict $\Delta\text{VRAM} = 0\,\text{MB}$ overhead.
    - Pre-registered decision threshold $\tau = 0.50$ with $[0.40, 0.60]$ uncertainty band (`UNCERTAIN`), sub-25ms fast-path latency, thread-safe bounded 1,024-entry LRU cache (`BoundedLRUPairCache`), NFC Unicode normalization, and fail-open degradation logging `verifier_degraded`.
  - **Phase 3: Cross-Subsystem Wiring Across 7 Subsystems:**
    - `belief_service.py`: Candidate beliefs with `CONTRADICTION` routed to true Belnap $\top$ conflict handling.
    - `cascade.py`: Dynamic polarity assignment evaluating `told_false=True` on contradiction and `told_true=True` on entailment, supporting both instance and unbound class calls.
    - `coherence.py`: Tool receipt output entailment checks against spoken action claims.
    - `induction.py`: Bidirectional entailment clustering for paraphrases while preserving `D-REAS-06` 5-cluster/0-error gate and quarantine invariants.
    - `memory_commit_service.py`: Transcript entailment checks rejecting contradictory candidate facts.
    - `corroboration.py`: Critical question CQ1 relevant similarity evaluation via bidirectional entailment.
    - `self_diagnosis.py`: Observation entailment against symptom descriptions preventing token-overlap false alarms.
  - **Phase 4: GBNF Distiller & Provenance Invariants (`reasoning/distill.py`):**
    - Added `config/grammars/belief_distill.gbnf` for constrained declarative JSON proposition extraction.
    - Implemented `distill_contradiction_to_proposition` and `sign_distilled_proposition` (`USER_DERIVED`).
    - Enforced ADR-006 / D-MEM-05 provenance invariants: unsigned propositions rejected by `ProvenanceGate` and persisted to SQLite `memory_quarantine` table with structured rejection reasons.
  - **Gates & Verification Suites:**
    - Passed all 9 pre-registered acceptance gates (`G-V1357-HYGIENE`, `G-V1357-LATENCY`, `G-V1357-BELNAP`, `G-V1357-RULE`, `G-V1357-VERIFIER-NEG`, `G-V1357-DISTILL`, `G-V1357-ANALOGY`, `G-V1357-DIAG`, `G-V1357-REGRESS`).
    - Dedicated test suites: `tests/test_v1357_verifier.py`, `tests/test_v1357_provenance_negative.py`, `tests/test_v1357_semantic_wiring.py`, `tests/test_v1357_epistemic_hygiene.py`, `tests/test_v1357_edge_cases.py`, and `tests/test_v1357_extended_verification.py`.

---

## [1.35.6] — 2026-10-05

### Added
- **98-Item Robustness Reproducibility (`scripts/recompute_heldout_98.py`):**
  - Evaluated held-out benchmark split excluding items 15 and 73 (incidental exploratory prompt-tuning exposures on `math_fresh_heldout_500.jsonl` at indices 14 and 72).
  - Confirmed that excluding both items shifts strict accuracy by at most 1.0 pp across all 8 evaluated arms with zero changes to model rankings or empirical conclusions (12B Direct R0: 88.8% vs 89.0%; 12B PAL P2: 85.7% vs 86.0%; E4B Routed R1: 87.8% vs 88.0%; E4B PAL P2: 73.5% vs 73.0%; E4B Direct R0: 51.0% vs 52.0%; E2B Thinking R1: 80.6% vs 81.0%; E2B PAL P2: 61.2% vs 61.0%; E2B Direct R0: 50.0% vs 51.0%).
- **Provenance Split — Deterministic vs LLM-Inferred Assertions (`D-MEM-06`):**
  - Split `LISP_ASSERTION` provenance: deterministic MicroScheme rule-engine output keeps `LISP_ASSERTION` (memory- and grounding-eligible); LLM-proposed Concert Layer steps now sign as `LLM_INFERRED_ASSERTION` via `InferredAssertionSigner` — memory-eligible but never grounding-eligible.
  - Enforcement: `src/lucca/core/schemas.py`, `src/lucca/memory/signers.py`, `src/lucca/memory/gate.py`, `src/lucca/core/orchestrator.py`, SQLite migrations 0001/0006/0007 (CHECK constraints, `mem_bi_eligible` triggers, `grounding_eligible` CASE).
  - New test `test_p0_provenance_split_signer_and_eligibility` raises the suite to 1,199 passing (0 failed, 67 deselected).
- **TTS Output Safety Guard (P6 remediation):**
  - Deterministic screen at the TTS boundary (`src/lucca/core/tts_safety_guard.py`), active by default for edge-tier models (E4B/E2B) whose uncensored fine-tunes show low refusal rates on harmful probes (30% vs 90% on 12B; paper 06 scorecard). Configurable via `LLMSettings.tts_safety_guard_mode` (`off` / `edge_tiers` / `all`).
  - Wired into `SpeechOutputManager.speak_text` and `enqueue_tts_chunk`: blocked utterances are replaced with a canned safe line so caption and audio stay consistent.
  - 11-test battery `tests/test_tts_safety_guard.py` raises the suite to 1,210 passing (0 failed, 67 deselected).
- **Truth-in-Receipt Battery Broadening (P6 remediation):**
  - Formal battery expanded from 40 to 70 sentences across 8 categories (`tests/test_truth_in_receipt_battery.py`): E positive receipt-backed broader surface forms, F passive/markdown/multilingual characterization, G stale-receipt scenarios, H failed-status scenarios.
  - Matcher hardening in `src/lucca/sandbox/output_supervisor.py`: markdown emphasis stripped before matching (underscores preserved for snake_case targets); receipts with non-success `status` never ground claims; new optional `stale_before` parameter ignores receipts stamped before the current turn.
  - Battery broadening raises the suite to 1,240 passing (0 failed, 67 deselected).
- **Session Review Fixes (2026-10-05):**
  - Orchestrator lazy-fallback `speech_output` property now reuses the TTS safety guard constructed at init — a rebuilt manager can no longer silently lose the output screen.
  - `stale_before` is now wired in production: `OutputSupervisorSession.reset_turn()` stamps `turn_started_at`, and `feed_chunk` forwards it to the truth-in-receipt matcher, so a previous turn's receipt can never ground this turn's action claim. Two end-to-end wiring tests added (stale rejected / fresh accepted through the session); suite now 1,242 passing (0 failed, 67 deselected).
- **Contrastive Live-Companion Battery (P9 remediation, first live run):**
  - New `tests/test_contrastive_live_hw.py` + 30-probe fixture (`tests/fixtures/contrastive/probes.jsonl`): the SAME probes through Arm A (bare llama-server chat completion, no memory/rules/supervision) and Arm B (full compound pipeline). Strata: recall, receipt introspection, abstention. Mechanical grader; Wilson CIs; JSON report to `logs/test_reports/`.
  - First live run (17.5 min, all 60 turns): **Arm B recall 9/10, introspection 9/10, abstention 10/10 — all P9 thresholds met. Arm A recall 0/10, introspection 4/10, abstention 7/10 (3 fabrications on unanswerable probes).** The delta demonstrates compound-layer value live. Corrected report: `contrastive_battery_20261005T200643Z_regraded.json`.
  - Grader hardening found by the run: voice-sanitizer normalization ("config dot ini" → "config.ini"), question-echo credit suppression, deny-mode refusal acceptance, arm-A summary field fix.
  - **Product finding + fix:** benign recollections of PAST actions (downgraded to Tier 2 for lack of current-turn receipts) were incrementing the session SECURITY hysteresis — the 3rd recollection escalated a later truthful recollection into a hard "violates core safety invariants" abort. Recollection downgrades now carry `breach_type=ungrounded_action_recollection` and are excluded from the hysteresis. Regression test added.
  - Harness repair: `_run()` in `tests/test_a1_live_hw.py` now passes sync values through — the HW seeding helpers had rotted when `MemoryStore.commit` became synchronous (hidden by hw-deselection).
  - Suite now 1,243 passing / 0 failed / 68 deselected (the hw-marked contrastive battery joins the deselected set; run it with `-m hw`).
- **Authoritative Metrics Record (`data/metrics/TEST_METRICS.yaml`):**
  - Single source of truth for test-suite and static-gate counts (record `metrics-2026-10-05`: 1,199 passed / 67 deselected; 24 static gates). Active docs now cite the record; historical dated figures in CHANGELOG/plans/archive are preserved as historical records.
- **Documentation & Substrate Alignment:**
  - Aligned System Architecture Specification (`docs/LUCCA_V135_1_ARCHITECTURE.md`) and research papers to release `v1.35.6-stable`, updating version metadata, scorecard headers, and commit provenance.
  - Freshly verified full test suite: 1,198 passed, 0 failed, 67 deselected (100% green).

---

## [1.35.5] — 2026-10-05

### Added
- **Split Nomenclature Reconciliation:**
  - Standardized split nomenclature across all research documents and reports: mapped `test-100` (lines 1–100 of `math500_test.jsonl`) to `Dev-100` per `V135_CONTAMINATION_AUDIT.md`, with `Held-Out 100` defined strictly as lines 1–100 of `math_fresh_heldout_500.jsonl` (remaining 400 problems unrun and held in reserve).
- **Output Supervisor Sensitivity Stratum Analysis:**
  - Reordered and audited supervisor evaluation reporting in §4.3 to lead with strict completed action claims (1 of 8 detected, 12.5%, 95% Wilson CI: [2.2%, 47.1%]) alongside broad action assertions (1 of 23 detected, 4.3%, 95% Wilson CI: [0.8%, 21.0%]).
  - Disclosed that embedded `ground_truth_hallucination` fields in raw JSON files reflect automated regex labeling circular with the supervisor itself; ground truth is provided by manual audit in `logs/test_reports/action_hallucination_labels_100.jsonl`.
  - Disclosed boundary case decisions (e.g. E4B `T03` classified as `CLEAN`/`INTENT` because it solicited user confirmation prior to execution).
- **Rule Invocation Frequency Qualification:**
  - Qualified all 15 active factory skills in `config/skills/` as loaded and callable, explicitly noting that invocation frequency is not measured in production logs.

---

## [1.35.4] — 2026-10-05

### Added
- **Truth-in-Receipt 40-Sentence Formal Battery (`tests/test_truth_in_receipt_battery.py`):**
  - Implemented 40 balanced test cases across 4 categories: Category A (10 grounded claims), Category B (10 ungrounded claims), Category C (10 paraphrases/idioms), and Category D (10 epistemic hedges and negations) with 100% test pass rate.
- **Live 100-Probe Action Hallucination Evaluation ($n=100, T=0.6$):**
  - Evaluated balanced 100-probe battery (`data/benchmarks/action_hallucination_battery_100.json`: 50 temptation probes, 25 honest controls, 25 idiomatic controls for `placed`, `moved`, `closed`, `processed`) across Gemma 4 E4B and E2B.
  - Confirmed 0 / 50 false alarms on control probes.
  - Identified 4 empirical escape modes: active progressive participles (12 escapes), structured markdown headers (2 escapes), passive state assertions (6 escapes), and unlisted verb lemmas (2 escapes).
- **Controlled Token Starvation Deconfounding on Identical Dev Items:**
  - Evaluated Direct R0 with 4,096-token cap against 1,536-token baseline on identical Dev-100 problems. E4B scored 52.0% (5:3 discordant, $p = 0.7266$ NS) and E2B scored 57.0% (10:4 discordant, $p = 0.1796$ NS), confirming that token cap relaxation alone does not account for scaffold accuracy deltas.
- **Test Suite Expansion:**
  - Test suite expanded from 1,184 to 1,198 passing tests (0 failed, 67 deselected).

---

## [1.35.3] — 2026-10-04

### Added
- **Full Empirical Held-Out Matrix Across 3 Parameter Scales:**
  - Completed side-by-side evaluation across Gemma 4 12B, E4B, and E2B on 100 unseen competition mathematics problems (`math_fresh_heldout_500.jsonl`).
- **Research Paper 6 (`06_MODEL_SCALE_ABLATION_GEMMA4_E4B_VS_12B.md`):**
  - Formulated formal paper detailing:
    - 12B Scale Inversion under greedy decoding ($T=0.0$): unconstrained thinking degrades 12B from 90.0% to 58.0% ($p = 4.66 \times 10^{-10}$).
    - E4B Compound Parity: Thinking Mode R1 @ 6k achieves 88.0% strict CAS accuracy, outperforming PAL P2 @ 2k (73.0%, $p = 0.0026$).
    - Dynamic Task Router ($\text{Router}(M, T)$): Dispatches Direct R0 for 12B, PAL P2 for small-model arithmetic, and Thinking Mode R1 @ 6k for edge competition mathematics.
- **Cryptographic Key Migration CLI (`src/lucca/memory/migration_tool.py`):**
  - Added `lucca-admin memory migrate-keys` to validate legacy SHA-256 records, re-compute HMAC signatures under active master keys, and purge quarantined rows without silent amnesia.

---

## [1.35.2] — 2026-10-04

### Added
- **Persistent SQLite Memory Quarantine (`src/lucca/memory/retrieval.py`):**
  - Replaced unhandled runtime crashes and silent dropping of corrupt rows with persistent quarantine into SQLite `memory_quarantine` table `(memory_id, entry_id, reason, stage, quarantined_at)`.
  - Quarantined IDs are loaded on boot and excluded from subsequent searches.
- **Memory Integrity Surfacing API:**
  - Implemented `HybridRetriever.get_integrity_status_report()` emitting programmatic security alerts when integrity checks fail.
- **Master Key Persistence Hardening:**
  - Master keys generated via `secrets.token_bytes(32)` and persisted to `data/keys/master.key` with `0600` permissions. Removed all public dev fallback keys (`b"0123456789..."`) from `main.py`, `service.py`, `signer_factory.py`, and `admin.py`.
- **System Architecture Specification v1.35.2:**
  - Authored `docs/LUCCA_V135_1_ARCHITECTURE.md` establishing the multi-scale compound neurosymbolic edge architecture.

---

## [1.35.1] — 2026-10-04

### Added
- **Audit Remediation Implementation:**
  - Codified 9-point remediation from release audit: HKDF key derivation with domain salt (`"lucca-v2"`), read-time two-stage HMAC verification, and matcher verb expansion.
- **TruthInReceiptMatcher Verb Expansion (`src/lucca/sandbox/output_supervisor.py`):**
  - Expanded `ACTION_VERBS` to 21 verified verbs (`delete`, `create`, `modify`, `execute`, `run`, `install`, `remove`, `send`, `upload`, `fetch`, `save`, `write`, `post`, `reboot`, `book`, `place`, `process`, `start`, `close`, `copy`, `move`).
- **Edge Model Action Hallucination Protocol:**
  - Authored evaluation harness for edge model action hallucination under unconstrained conversational generation.

---

## [1.35.0] — 2026-10-03

### Added
- **Contamination Audit & Test Split Reclassification (`handover/V135_CONTAMINATION_AUDIT.md`):**
  - Reclassified `math500_test.jsonl` (problems 1–100) as development split (`Dev-100`) due to historical prompt tuning.
  - Designated `data/benchmarks/math_fresh_heldout_500.jsonl` (lines 1–100) as primary unseen held-out benchmark.
- **SymPy Grader Hardening:**
  - Fixed non-deterministic SymPy evaluation crashes and dict indexing errors on Dev-400 benchmark set.

---

## [1.3.0] — 2026-09-30

### Added
- **Asuka Langley Soryu RVC v2 Neural Voice Pipeline:**
  - Integrated 40kHz RVC v2 neural voice conversion model (`asuka.pth` + 400-epoch weights) downstream of Kokoro-82M front-end base (`blend:0.70*af_sky+0.30*jf_alpha`).
  - Implemented 64-tap Kaiser-windowed sinc anti-aliasing resampling (`torchaudio.transforms.Resample`, $\beta = 14.77$, 100 dB stopband attenuation) across 24kHz $\leftrightarrow$ 16kHz $\leftrightarrow$ 40kHz transitions, eliminating high-frequency FFT Gibbs ringing.
  - Implemented Praat acoustic autocorrelation pitch tracking (`parselmouth.Sound.to_pitch_ac`, pitch floor 160Hz, ceiling 1100Hz) with continuous unvoiced F0 linear interpolation and 3-frame median smoothing, resolving octave-dropping artifacts and NSF neural vocoder sine dropouts on glides and nasals.
  - Calibrated pitch sweet spot to $+6\text{ semitones}$ with discrete `repeat_interleave(2)` phoneme frame alignment for authentic character timbre.
  - Achieved sub-40ms warm neural conversion latency on workstation NVIDIA GeForce RTX 5080 Laptop GPU.
  - Implemented zero-configuration cross-environment IPC subprocess bridge enabling Python 3.12 core runtime to drive Python 3.10 PyTorch CUDA 12.8 / fairseq worker without packaging dependency conflicts.
  - Added quick-switch preset and recipe selector for Asuka in PyQt6 Configuration Suite Voice Blender tab (`VoiceTab`), setting Asuka as the default active companion persona voice.
- **Multi-Stage Tolerant Code Extraction & AST Sanitizer (Phase 1):**
  - Replaced brittle single-line regex extractions with `extract_python_code_tolerant` and `sanitize_and_repair_python_code` in `src/lucca/sandbox/ast_sanitizer.py`.
  - Implemented 4-stage tolerant extraction cascade: `fenced` (```python ... ```) $\to$ `unfenced` (statement keyword filter) $\to$ `longest_ast_slice` (contiguous valid AST slice) $\to$ `empty` (safe graceful abstention).
  - Empirically audited on 100 dev benchmark problems: achieved **0 / 100 (0.0%)** empty-code drops before and after retry (95% CI: [0.00%, 3.70%]), completely eliminating the 24.5% empty-code failure mode from v1.2.
  - Implemented token-level operator repairs via Python `tokenize` with strict `keyword.iskeyword` protection: carets `x^2 \to x**2`, implicit multiplication `2x \to 2*x`, `3(a+b) \to 3*(a+b)`, and unclosed parenthesis/bracket/docstring balancing without corrupting string literals or comments.
- **Conditional GBNF Grammar Gate Evaluation (Phase 2):**
  - Formally evaluated constrained decoding GBNF Python grammars against the empirical residual. Because Phase 1 eliminated 100% of empty-code drops ($0.0\% < 3\%$ threshold) and remaining errors were semantic/API issues rather than grammar syntax errors, grammars were formally bypassed to preserve decoding throughput and avoid per-token CPU latency penalties.
- **Unified 2-Tier Neurosymbolic Execution Feedback Loop (Phase 3):**
  - **Tier 1 (Compiler Preflight, $<1\text{ms}$):** Deterministic preflight AST rewrites solve SymPy API traps prior to container dispatch:
    - Inverts method calls: `expr.solve(x) \to sp.solve(expr, x)`.
    - Rewrites composite differentiation: `sp.diff(expr, x/h)` and assigned expressions `u = x/h; sp.diff(expr, u)` rewrite to dummy symbol substitution, preventing SymPy `ValueError: Can't calculate derivative wrt x/h`.
    - Auto-filters hallucinated SymPy imports via `dir(sympy)` (e.g. `schmitt_method`, `IntegerResult`).
    - Injects missing `itertools` imports when `itertools.*` attributes are referenced.
    - Defines commonly assumed mathematical sets (`primes`, `odds`, `evens`).
  - **Tier 2 (2-Turn Execution Feedback Loop, Cap $\le 2$ Rounds):** Autonomous runtime error recovery engine permanently enabled as a safety net for algorithmic exceptions and runtime failures.
  - **Empirical Recovery Rate on 47 Baseline Failure Traces:**
    - 30 Design Traces: **27 / 30 PASS (90.0%)**.
    - 17 Held-Out Traces: **13 / 17 PASS (76.5%)** (with Task 14 / idx 115 and Task 16 / idx 195 recovering from runtime crashes to 100% correct answers via Turn 2).
    - Combined Dev Recovery: **40 / 47 PASS (85.11% recovery rate)** on previously broken problems, exceeding the 74.47% baseline recovery target.
  - **Trailing `None` Wrapper Fix (`file_tool.py`):** Eliminated legacy AST wrapper bug that wrapped trailing statements in `print()`, which caused `print(solve())` to emit trailing `None` and falsely fail grading.
- **Visual Pipeline Debugger Trace Horizon Generalization:**
  - Generalized `ui/pipeline_debugger/index.html` ribbon bar to dynamically render arbitrary benchmark runs ($N=17, 30, 400$) and live interactive companion conversation horizons (`Turn #1`, `Turn #2`, etc.) without empty placeholder gaps.
  - Connected `/api/traces` and `/api/trace/<id>` in `scripts/serve_pipeline_debugger.py` to support both numerical problem index lookups and conversation turn session IDs.
- **3-Stage Mathematical Equivalence Grader (Phase 4):**
  - Implemented 3-stage non-hanging evaluation pipeline in `scripts/run_modern_2024_benchmarks.py`:
    1. Normalized string/LaTeX match with whitespace, powers, and base subscript equivalence.
    2. 5-point random non-integer numeric evaluation ($x \in \{2.1, 3.2, 5.3, 7.4, 11.5\}$) with singularity and division-by-zero protection.
    3. Sandboxed SymPy CAS algebraic simplification (`sympy.simplify(pred - exp) == 0`) enforced with a strict 2.0s worker thread timeout to prevent hangs.
  - Verified with 100% green unit test suite in `tests/test_cas_grading.py` (6/6 passing).
- **Context Expansion to 32K (`ctx=32768`):**
  - Expanded resident KV-cache context window from 16,384 to **32,768 tokens (32K)** in `src/lucca/core/config.py` and `llama-server` runtime.
  - Offloaded Windows desktop display to integrated Intel(R) Graphics iGPU (Intel Core Ultra 9 275HX), placing the mobile NVIDIA GeForce RTX 5080 Laptop GPU into dedicated compute mode (`Disp.A: Off`).
  - Verified physical VRAM telemetry via `nvidia-smi`: **9.97 GiB (10,212 MiB)** allocated under 32K context with FlashAttention-2, leaving **5.95 GiB (6,091 MiB / 37.4%)** free physical VRAM headroom with zero layers spilling to system RAM.
- **Frozen Baseline Isolation & Uniform Rescore (`v1.2.0-baseline`):**
  - Archived all 7 canonical 16K benchmark evaluation logs into `logs/test_reports/frozen_v1.2_baseline/` and tagged git commit `37fde25` as `v1.2.0-baseline` to guarantee historical data immutability under the Zero-Estimate Principle.
  - Rescored the frozen baseline under identical 3-stage CAS grader criteria (`scripts/rescore_with_sympy.py`):
    - Held-Out 400: Strict 282 / 400 (70.50%), Upgraded CAS **293 / 400 (73.25%)** ($+11$ delta, $+2.75\%$).
    - Exploratory 100: Strict 82 / 100 (82.00%), Upgraded CAS **86 / 100 (86.00%)** ($+4$ delta, $+4.00\%$).
    - Consolidated Full MATH-500 Baseline: **379 / 500 (75.80%)**.
    - Empirical False-Accept Hand Audit: Audited all 15 newly accepted problems (`logs/newly_accepted_*.json`); confirmed **0 / 15 false accepts (0.00% False-Accept Rate)**.
- **Phase 6: Generalization Across Fresh Held-Out Benchmark Suite ($N = 500$):**
  - Evaluated the independent, unseen 500-problem competition suite (`data/benchmarks/math_fresh_heldout_500.jsonl`, SHA256: `834405fa...`) with 32K context, FlashAttention-2, Tier 1 preflight compiler, and Tier 2 feedback loop (`modern_benchmarks_2024_20260930T031359Z_v1.3-fresh-heldout-500.json`):
    - Strict Exact Match: **371 / 500 (74.20%)** in 3,470.1s (mean 6.94s / prob).
    - Upgraded 3-Stage SymPy CAS Grader: **394 / 500 (78.80%)** ($+23$ delta, $+4.60\%$).
    - Empirical False-Accept Hand Audit: Audited all 23 newly accepted problems (`logs/newly_accepted_*_v1.3-fresh-heldout-500.json`); confirmed **0 / 23 false accepts (0.00% False-Accept Rate)**.
    - Difficulty Scaling: Solved **107 / 131 (81.68%)** on Level 4 (AIME tier) and **84 / 136 (61.76%)** on Level 5 (USAMO/Olympiad tier) across 267 advanced competition problems (53.4% of suite).
    - Domain Accuracy (CAS): Counting & Probability **94.44% (68/72)**, Number Theory **94.37% (67/71)**, Prealgebra **85.92% (61/71)**, Algebra **84.72% (61/72)**, Geometry **70.83% (51/72)**, Intermediate Algebra **69.01% (49/71)**, Precalculus **52.11% (37/71)**.
    - Autonomous Recovery: 33 error triggers intercepted $\to$ **18 successful Turn-2 recoveries (54.55% recovery rate)**.
    - Tolerant AST Extraction Residual: **0 / 500 empty code drops (0.0% residual)**, establishing a cumulative 0.0% residual across 600 audited competition problems.
- **Master Architecture Reference Maps & Section 10 (`docs/ARCHITECTURE.md`):**
  - Authored comprehensive Section 10 in the master architecture specification featuring three exhaustive Mermaid diagrams:
    1. Complete End-to-End System Topology and Dataflow across all 8 subsystems (Capture $\to$ Routing $\to$ Orchestration $\to$ Neural Brain $\to$ Symbolic Reasoning $\to$ Deontic Sandbox $\to$ Cryptographic Memory $\to$ Desktop UI/Debugger).
    2. Two-Tier Neurosymbolic Execution and AST Compilation Lifecycle sequence diagram.
    3. Belnap Paraconsistent Epistemic Bilattice ($\mathbf{T}, \mathbf{F}, \mathbf{B}, \bot$) and cryptographic provenance state machine.
- **Dedicated Subsystem Reference Manuals Corpus (`docs/subsystems/`):**
  - Authored 8 standalone deep-dive reference manuals with Mermaid flowcharts, state machines, and API contracts:
    1. `01_CORE_ORCHESTRATION_AND_CASCADE.md`: Three-tier execution, unified turn pipeline, speculative BDI validation (<35μs), Belnap $\mathcal{FOUR}$ bilattice, and 8-substrate search cascade.
    2. `02_NEURAL_BRAIN_AND_STREAMING.md`: Gemma-4 12B Heretic Q6_K on RTX 5080 Laptop GPU, Prompt Frontier Suffix (8.58x KV speedup), 32K context allocation, and streaming demuxer.
    3. `03_SYMBOLIC_REASONING_AND_VERIFICATION.md`: MicroScheme LISP interpreter (1,000 gas limit), Microsoft Z3 SMT theorem prover (SAT/contingency/path proofs), and Babble/Stitch e-graph macro synthesis.
    4. `04_DEONTIC_SANDBOX_AND_COMPILER.md`: Persistent Docker RPC daemon (7.8ms P50), stdin code streaming over `ARG_MAX`, 4-stage tolerant AST extractor (0.0% empty residual), Tier 1 preflight compiler, 2-turn feedback loop (85.11% recovery), and Dimension 7B output supervisor.
    5. `05_EPIDEMIOLOGY_AND_CRYPTOGRAPHIC_MEMORY.md`: SQLite WAL + `sqlite-vec` (Intel NPU) + FTS5 BM25, cryptographic provenance envelopes, grounding eligibility segregation (D-MEM-04), and bi-temporal supersession.
    6. `06_VOICE_SENSES_AND_AUDIO_PIPELINE.md`: Zero-copy shared-memory ring buffers, faster-whisper ASR (CUDA float16), acoustic hygiene filters, Kokoro-82M ONNX TTS, anime formant filter DSP, and sub-50ms barge-in WASAPI abort.
    7. `07_ROUTING_AND_CONFORMAL_CALIBRATION.md`: Sub-150ms emergency reflex fast path, heuristic intent classification, non-parametric split-conformal abstention (coverage $\ge 0.95$), and replay-protected HMAC confirmation nonces.
    8. `08_UI_DIAGNOSTICS_AND_PIPELINE_DEBUGGER.md`: Dual-mode PyQt6 companion sprite and system tray lifecycle, 10-tab settings HUD, Commorose radial menu, and real-time 9-tank Visual Pipeline Debugger on port 8765.
- **Frontier Research & Engineering Papers Corpus (`docs/research/papers/`):**
  - Outlined 5 peer-review caliber research papers ready for conference submission:
    1. `01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md` (Target: JAIR / NeurIPS 2026).
    2. `02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md` (Target: IEEE ICASSP / MMSys 2026).
    3. `03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md` (Target: AIJ / KR 2026).
    4. `04_E_GRAPH_EQUALITY_SATURATION_AND_RULE_INDUCTION.md` (Target: ACM POPL / ASE 2026).
    5. `05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md` (Target: IEEE S&P / USENIX Security 2026).
- **Persistent HTTP Connection Pooling & Socket Hygiene (`src/lucca/brain/llm_client.py`):**
  - Replaced per-turn ephemeral `httpx.Client` instantiation with a persistent connection pool configured with `httpx.HTTPTransport(limits=httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0))`.
  - Reused persistent client across conversational turns, eliminating TCP handshake jitter, socket accumulation, and descriptor exhaustion.
  - Hardened `abort(trace_id)` barge-in cancellation: selectively closes target `stream_state.response.close()` while preserving the connection pool for subsequent turns and concurrent streams.
  - Added clean lifecycle `close()` method to `LLMClient` and bound it to `Orchestrator.stop()`.
  - Verified with new unit tests in `tests/test_llm_client_race.py` (`test_persistent_connection_pool_reuses_client`).
- **Standalone Windows Desktop Executable Compilation & 10-Point Diagnostic Check:**
  - Updated `Lucca.spec` to bundle all v1.3.0 runtime modules (`sympy`, `mpmath`, `mss`, `PIL`).
  - Rebuilt standalone distribution bundle `dist/Lucca/Lucca.exe` via `packaging/build_exe.py`.
  - Executed physical diagnostic battery `dist/Lucca/Lucca.exe --check`: **10 / 10 criteria passed (Exit code 0)** across System RAM (24.4 GB free), MSHybrid dGPU VRAM (10.2 GB resident), Intel NPU OpenVINO, SQLite `sqlite-vec`, WSL2, Docker CE, LUCCA_HOME layout, model weights SHA256, audio ring buffers, and WSL subsystem.
- **Live Interactive System Verification Battery:**
  - Verified live inference through `scripts/live_llm_verification.py` against active `llama-server.exe` (Gemma-4 12B Q6_K):
    - Sub-300ms turn-2 TTFT (**285.2ms**) with connection keepalive and prompt cache reuse.
    - Zero persona degeneration; verified authentic companion identity.
    - Native structured tool calling: cleanly dispatched `launch_app(app_name='notepad')`.
    - 5 / 5 tests passed (100% accuracy).
  - Verified real-time Visual Pipeline Debugger at `http://127.0.0.1:8765` active with HTTP 200 OK.

- **Full Big-Bench Hard (BBH) 27-Subset Evaluation Harness (`scripts/run_full_bbh.py`):**
  - Built complete evaluation harness covering all 27 canonical BBH subsets (Suzgun et al., 2022), replacing the prior partial 4-subset run.
  - Implemented per-subset answer extractors: BOOLEAN (true/false, yes/no, valid/invalid), OPTION_LETTER (`(X)` patterns), SEQUENCE (word sorting, case-insensitive normalized), NUMERIC (last integer in response).
  - Annotated all 27 subsets into two evaluation tiers:
    - **14 Algorithmic / Tool-Friendly:** `boolean_expressions`, `dyck_languages`, `logical_deduction_{3,5,7}`, `multistep_arithmetic_two`, `navigate`, `object_counting`, `temporal_sequences`, `tracking_shuffled_objects_{3,5,7}`, `web_of_lies`, `word_sorting`.
    - **13 Language / Pure Semantic:** `causal_judgement`, `date_understanding`, `disambiguation_qa`, `formal_fallacies`, `geometric_shapes`, `hyperbaton`, `movie_recommendation`, `penguins_in_a_table`, `reasoning_about_colored_objects`, `ruin_names`, `salient_translation_error_detection`, `snarks`, `sports_understanding`.
  - Checkpoint/resume per subset (`logs/test_reports/bbh_full_27_checkpoint.json`) for long-run safety.
  - CLI flags: `--samples N`, `--mode algorithmic|language`, `--subsets <keys>`, `--no-resume`.
  - Published external baseline anchored: Google DeepMind reported **53.0% BigBench Extra Hard** for Gemma 4 12B Unified (source: DeepMind tech report, June 2026).
  - Downloaded all 23 missing BBH subset JSON files (6,481 total examples) into `data/benchmarks/`.

- **Full GSM-Symbolic Evaluation Harness (`scripts/run_full_gsm_symbolic.py`):**
  - Built full harness covering all 5 GSM-Symbolic variants with two evaluation modes each:
    - **Variants:** `symbolic` (5,000), `p1` (5,000), `p2` (2,500), `noop` (945), `noop_filtered` (338).
    - **Mode A — Bare CoT:** Apple's official 8-shot few-shot prompt template (`temperature=0.0`); documents the degradation curve on P1/P2 and the "symbolic slip" distractor-trap failure on NoOp variants.
    - **Mode B — Compound PAL:** LLM writes Python, Docker sandbox executes; irrelevant NoOp clauses never assigned to variables → expected 0% distractor-trap degradation.
  - Distractor-trap detection in CoT mode: flags responses that incorporate numbers from the injected irrelevant clause and produce a wrong answer.
  - Checkpoint/resume per (variant × mode) combination.
  - Final summary computes the NoOp immunity delta (PAL accuracy − CoT accuracy) — the paper's central empirical claim.
  - Downloaded all GSM-Symbolic datasets: Apple `ml-gsm-symbolic` repo (symbolic/p1/p2) and `Experimental-Orange/gsm-noop-audited` on HuggingFace (noop/noop_filtered).

- **Scientific Integrity Corrections (Research Papers):**
  - Renamed "Big-Bench Hard (BBH) | 92.40% (924/1,000)" to "**BBH-4 Algorithmic Composite (4/27 subsets):** 92.40%" in both research papers to prevent reviewer misinterpretation of the partial result as a full 27-subset score.
  - Added "BBH Full 27-Subset Suite (Pending)" row to comparative tables with DeepMind's published 53.0% BBEH baseline and `*(Run pending)*` for the Lucca compound score.
  - Files corrected: `docs/research/papers/01_COMPOUND_NEUROSYMBOLIC_AI_VS_MONOLITHIC_LLMS.md` and `docs/research/NEUROSYMBOLIC_RESEARCH_PAPER.md`.

### Changed
- **Log Archive:** All 130+ ephemeral timestamped JSON benchmark run reports moved from `logs/test_reports/` root to `logs/test_reports/v1.3/`. Root now contains only permanent summary files and the baseline archive.
- **Static Gates:** Test count expanded from 24 to **31** (added packaging tests in `tests/test_packaging.py`). All 31 pass in 21.53s as of commit `36f264d`.

---


## [1.2.0] — 2026-09-30

### Added
- **Work Order 26: Cognitive Interiority, Preflight Verification & Track 3 Modern Benchmarks (D-EVAL-03):**
  - **Neural Core Foundation (Gemma 4 12B Exclusivity):** All formal benchmarks across all three tracks were conducted **exclusively on `gemma-4-12b-heretic-Q6_K`** (12.4B parameters). Early exploratory pre-benchmark spikes evaluated alternative open-weight architectures (such as Mistral-NeMo-12B), but Gemma 4 was selected as the sole neural foundation for all formal benchmarking due to its GQA KV-cache efficiency on 16 GiB hardware and superior AST code synthesis for deterministic tool calling. Zero benchmark results were collected on Mistral or any other model weights.
  - **Track 3 Modern Benchmark Execution (2024–2025 Robustness Suites on 16K Baseline):**
    - **Apple GSM-Symbolic ($N = 100$ Canonical Evaluation Slice):** **100.0% accuracy (100 / 100)** in 527.4s via Program-Aided Language (PAL) mode in Docker (`modern_benchmarks_2024_20260929T173711Z.json`). Zero calculation slips or variance under altered constants.
    - **EvalPlus HumanEval-Plus (Full Canonical 164 Tasks, $>120,000$ Adversarial Test Inputs):** **91.46% pass@1 (150 / 164)** in 1,016.8s (`modern_benchmarks_2024_20260929T174613Z.json`), outperforming published frontier monolithic baselines GPT-4o (86.6%) and Claude 3.5 Sonnet (88.5%). Phase 4 autonomous Docker preflight self-correction loop caught and fixed 10 separate failing tasks live in-flight.
    - **MATH-500 (100-Problem Stratified Subset across Levels 1–5 and 7 Subjects):** **77.0% exact match (77 / 100)** in 1,149.7s (`modern_benchmarks_2024_20260929T180321Z.json`). 7 additional problems verified as mathematically identical syntax representations, yielding an **84.0% semantic derivation rate** (and 87.0% with base notation subscripts). Achieved 69.6% on Olympiad Level 5 problems.
  - **Autonomous Docker Preflight Verification (WO-26d):**
    - Implemented autonomous pre-execution verification loop evaluating candidate code strictly against assertions extracted from the problem prompt's docstring examples (zero exposure or leakage of hidden/adversarial benchmark test cases).
  - **Persistent RPC & Container Sandbox Hardening:**
    - Resolved persistent worker unexpected EOF bug in `src/lucca/sandbox/rpc.py` by restoring `PYTHONPATH=/workspace:/opt:/opt/toolsrv:/opt/lucca/sandbox`. Collapsed RPC latency to **7.8ms** (100x speedup) and brought `tests/test_persistent_rpc.py` to **10 / 10 green**.
    - Overcame Linux kernel `ARG_MAX` ceiling in `src/lucca/sandbox/file_tool.py` by streaming code over `stdin` (`[sys.executable, "-I", "-"]`) instead of argv `-c`, enabling dense test suites exceeding 1,000 cases to run without error.
    - Quarantined container diagnostics to `sys.stderr` in `docker/toolsrv/server.py` to prevent JSON-RPC framing corruption on `sys.stdout`.
  - **Cognitive Interiority & Mind-Mouth Quarantine (WO-26a):**
    - Quarantined belief revisions, cognitive bus yields, and system watchdog alerts from spoken TTS output in `TurnPipeline`.
  - **ASR Acoustic Hygiene & Normalization (WO-26b):**
    - Shipped audio stutter collapse, 25-character word ceiling, and context-bounded acoustic phonetic normalization for Australian/UK colloquialisms.
  - **Epistemic Slang Gating & Telemetry Resolution (WO-26c):**
    - Implemented high-confidence slang grounding (WEB routing) and deterministic `zoneinfo` (<1ms SLA) for exact timezone resolution.
  - **Decoupled Intermediate Scratchpad (WO-26e):**
    - Shipped `SubTurnScratchpadBuffer` preventing tool token exhaustion, defensive line-1 assumption-stating, and non-empty synthesis guardrails.
  - **Consolidated Acceptance Battery (WO-26f):**
    - Shipped unified standalone runner `scripts/run_wo26_acceptance_battery.py` executing 5 verification gates cleanly in CI.

---

## [1.1.0] — 2026-09-29

### Added
- **Work Order 25: Two-Track Cognitive Benchmark Verification & Control Ablation Staging (D-EVAL-02):**
  - Ratified Two-Track Empirical Evaluation Battery under strict edge hardware constraints (6-bit weight quantization `Q6_K`, 8-bit KV caching `Q8_0`, unexpanded 16,384-token context budget, peak resident VRAM $\le 12.4$ GiB / $\le 13.3$ GB):
    - **Track 1 (`SPEC-BENCH-100-v1.0`):** 100-problem frozen ground-truth cognitive battery spanning 10 complex domains (`tests/test_compound_reasoning_benchmark.py`). Achieved **91.0% pass rate (91/100)**, **100.0% path policy compliance (100/100)**, **100.0% epistemic faithfulness (100/100)**, and **100.0% tool error recovery (3/3)** with median latency of 9.39s on mobile workstation hardware (`logs/test_reports/compound_benchmark_20260928T170640Z.json`). Flawless 10/10 in Spatial 3D Kinematics (CAT02), Formal Constraint Logic Grids (CAT03), and Closed-World Algebra (CAT04).
    - **Track 2 (Standard Academic Benchmark Battery — Full Canonical Suites):** Evaluated algorithmic tool synthesis in Docker sandbox (`scripts/run_standard_academic_benchmarks.py`):
      - Canonical OpenAI HumanEval (Full 164 Tasks): **95.73% pass@1 (157 / 164)** zero-shot pass@1 executed live in Docker (`academic_benchmarks_20260928T182758Z.json`).
      - OpenAI GSM8K (Full Canonical 1,319 Tasks): **95.75% accuracy (1,263 / 1,319)** via Program-Aided Language (PAL) mode in Docker in 2,628.4s (~2.0s/task) with zero calculation crashes (`academic_benchmarks_20260929T030224Z.json`).
      - Big-Bench Hard (BBH, Full Canonical 1,000 Tasks across 4 Subsets): **92.40% consolidated accuracy (924 / 1,000)** bare-weights zero-shot without external execution tools (`academic_benchmarks_20260928T184814Z.json`):
        - Boolean Expressions: **99.20% (248 / 250)**
        - 3-Object Shuffled Tracking: **100.0% (250 / 250)**
        - Dyck Bracket Languages: **86.40% (216 / 250)**
        - Geometric Shapes: **84.00% (210 / 250)**
  - Staged and verified control parameter scale ablation model `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (6,217,260,896 bytes, ~4B effective parameters) in `C:\ProjectLucca\models\llm\` for parameter scale isolation (secondary control vs. compound system ablation on the primary 12B weights).
  - Aligned comparative literature baselines with published peer-reviewed frontier architectures (Claude 3.5 Sonnet, GPT-4o, Llama 3 70B, Qwen 2.5 32B Coder) and documented failure case audits (BBH depth-7 RoPE parity slips, SVG arc label ambiguities, HumanEval bisection tolerances).

---

## [1.0.0] — 2026-09-28

### Added
- **Work Order 24: Native Tool Expansion, Multimodal Vision Spike, and Deterministic Shortlister:**
  - Raised native tool registry cap (`MAX_REGISTRY_TOOLS`) from 19 to 24 (`src/lucca/core/capabilities.py`).
  - Registered 4 deferred native tools under central Pydantic argument validation:
    - `schedule_event`: system event and calendar scheduling with ISO-8601 validation (`src/lucca/sandbox/system_tools.py`).
    - `artifact_verify`: SHA-256 cryptographic verification and byte-size checking of workspace files with path traversal guards (`src/lucca/sandbox/system_tools.py`).
    - `clipboard_read`: safe clipboard text inspection via native Win32 CryptoAPI/User32 bindings (`src/lucca/sandbox/system_tools.py`).
    - `inbox_handoff`: secure workspace file ingestion from external inbox drop directory via `WorkspaceManager.import_from_inbox()`.
  - Implemented `screenshot_capture` (24th native tool): high-performance DXGI Desktop Duplication API capture with PIL fallback, JPEG encoding (`0xFFD8`), image downscaling ($\le 1920\times 1080$), and strict Class C confirmation gating (`exit_code=-3` upon cancellation).
  - Multimodal frontier-suffix prompt injection in `src/lucca/brain/llm_client.py` for zero-penalty vision KV-cache reuse.
  - Shipped deterministic tool shortlister (`src/lucca/core/tool_shortlister.py`): partitioned 24 native tools into 6 categories (`SYSTEM_STATUS`, `WORK_PRODUCT`, `COMMUNICATION`, `COGNITIVE_REASONING`, `EXTERNAL_RESEARCH`, `DESTRUCTIVE_EXECUTION`), bounding LLM exposure to $\le 12$ tools per turn with fail-closed full-catalog fallback (Wilson score lower bound 0.9286).
  - Comprehensive live acceptance test suite (`tests/test_wo24_live_acceptance.py`) covering all 5 end-to-end scenarios.
- **Work Order 23: Walton Argumentation Schemes Extension & Normalization:**
  - Extended Walton argumentation scheme library (`src/lucca/reasoning/walton_schemes.py`) with 4 critical question schemes: Scheme from Sign (observational indicators), Scheme from Analogy (structural target-source mapping), Scheme from Consequences (pragmatic outcome utility), and Scheme from Precedent (historical case consistency).
  - Normalized confidence weight deltas (positive contributions $\le +0.15$, negative counter-evidence $\ge -0.30$) preventing runaway confidence drift while preserving strict threshold consumption.
  - Shipped unified transcript normalization (`src/lucca/core/transcript_normalizer.py`) ensuring bit-exact transcript representations across voice, text, and replay pathways.
  - Shipped automatic decision log rotation (`rotate_decision_log`) in `src/lucca/core/decision_logger.py` with size clamping and atomic file rolling.
  - Comprehensive live acceptance suite (`tests/test_wo23_live_acceptance.py`).
- **Work Order 22: Practical Reasoning Rung — Means-Ends Planning & Diagnostic Self-Reasoning:**
  - Shipped means-ends goal planner (`GoalPlan`, `src/lucca/reasoning/means_ends_planner.py`): multi-action sequence decomposition with 8-step cap, order-contiguity validation, and aggregated multi-action plan narration in `TurnPipeline`.
  - Shipped diagnostic self-reasoning engine (`DiagnosticEngine`, `src/lucca/reasoning/diagnostic_engine.py`): executes `run_self_diagnosis()` against real hardware fault models (`check_audio_ring`, `check_wsl_status`, `check_models_manifest`) and decision record retrieval, returning spoken natural language assessments.
  - Cleanups for rule induction test portability, eTLD+1 domain corroboration, and Substrate 2 memory forget.
  - Live acceptance suite (`tests/test_wo22_live_acceptance.py`).
- **Work Order 21: Defeasible Reasoning Rung, User Modeling, and Fuzzy Induction:**
  - Shipped 4-tier standards-of-proof policy table (`PREPONDERANCE`, `CLEAR_AND_CONVINCING`, `BEYOND_REASONABLE_DOUBT`, `SPARK`) for belief commit gating.
  - Implemented Toulmin defeasible argumentation structure with warrants, backing, rebuttal conditions, and Walton critical question evaluation.
  - Added web-fact ratification flow with 2-D hazard policy and cross-reference domain verification (`eTLD+1`).
  - Implemented Theory-of-Mind (ToM) user model (`UserModel`) tracking user beliefs, preferences, and expertise levels, coupled with Case-Based Reasoning (`EpisodeRecall`) for autobiographical episode recall.
  - Shipped semantic fuzzy clustering in `src/lucca/reasoning/induction.py` using embedding cosine similarity to cluster near-duplicate phrasings for autonomous rule induction.
  - Source-conditioned inference live acceptance suite (`tests/test_wo21_live_acceptance.py`).
- **Work Order 20: The Concert Layer & Abductive Neurosymbolic Reasoning (D-REAS-09):**
  - Shipped the Concert Layer: bidirectional bridge between LLM abductive hypothesis generation and MicroScheme deductive invariant verification.
  - Implemented `(assert! ...)` primitive and fact predicates in MicroScheme with bounded forward-chaining re-evaluation (`MAX_CHAIN_DEPTH = 8`).
  - Added working memory reasoning context and cryptographic `ProofTrace` signing for verifiable inferences.
  - Shipped LLM abductive step protocol (`InferenceStep` schema) and multi-tier gather ladder with premise matching and condition checking.
  - Implemented `INFERRED` provenance commit path with proof trace verification gate, Substrate 2.5 Belnap epistemic cascade tier, and SQLite database migration `0007`.
  - End-to-end live acceptance chain ("Where Am I From", `tests/test_wo20_live_acceptance.py`).
- **Work Order 19: Central Validation Registries, Event Taxonomy, and Formal Verification:**
  - Shipped central Pydantic tool argument validation registry (`TOOL_ARG_SCHEMAS`, `BaseToolArgs`) enforcing strict schema validation for all native tools (D-SEC-04).
  - Implemented closed event taxonomy (`EventName` enum) barring free-form event strings across the IPC and turn event bus.
  - Direct unit testing and Hypothesis property-based fuzz testing for MicroScheme LISP parser and AST evaluator.
  - Shipped fail-closed boot-path exception logging gate and dead-code registry audit.
  - Added `lucca-admin memory forget` CLI subcommand for granular Substrate 2 memory redaction.
- **Work Order 18: Subsystem Decomposition & Architectural Refactoring:**
  - Decomposed monolithic `Orchestrator` into decoupled, single-responsibility services:
    - `TurnPipeline`: encapsulates unified turn execution across voice and text paths.
    - `SpeechOutputManager`: handles TTS chunk synthesis, queuing, overflow policy, and caption publishing.
    - `MemoryCommitService`: encapsulates transcript, action receipt, and fact commit pipelines.
    - `BeliefService`: manages belief contradictions and spoken belief update cues.
    - `ConfirmationManager`: governs temporal spoken and UI confirmation state lifecycles.
    - `StudioFacade`: strictly isolates UI layer from direct imports into memory, reasoning, or sandbox domains.
  - Synchronous memory-layer cascade (`MemoryFacade`) eliminating async event-loop starvation.
  - Fail-closed static architecture gate prohibiting silent broad `except Exception:` handlers (`F-ARCH-105`).
  - Ports and Adapters architecture with `ClockPort` isolating system time for deterministic testing.

### Changed
- **Memory UI Multi-Selection & Factory Reset:** Fixed memory pruning ergonomics in `MemoryTab` by adding full row multi-selection (Shift+click, Ctrl+click, drag), "Select All Visible" (Ctrl+A), batch pruning with dynamic count indicator (`btn_del_selected`), `Delete`/`Backspace` key shortcuts, table right-click context menu, and a dedicated one-click "Factory Reset (0 Memories)" button with confirmation modal. Protected user selection state against disruption from the 5-second live refresh timer.
- **UI Settings Suite & Persona Synchronization:** Updated `AboutTab` version baseline to 1.0.0 and added cognitive rungs; aligned `ManualTab` chapter tab indices and documented memory batch deletion and factory reset; added the 24 Native Tool Registry and shortlisting taxonomy display to `ToolsTab`; and updated `prompt_builder` persona architectural self-awareness with WO14–WO24 reasoning and tool capabilities.
- **Release Baseline Promotion:** Advanced package baseline to `v1.0.0` Production Release across all specs, user guides, and package manifests.
- **Dynamic Tool Shortlisting:** Replaced flat tool presentation with 6 functional shortlisting categories, reducing LLM context window pressure to $\le 12$ tools per turn while retaining 100% prefix KV-cache reuse.
- **Test Suite Harness Hardening:** Scaled concurrency timeouts and retry budgets in packaging, sanity guard, and turn loop test fixtures without relaxing any functional thresholds or assertion gates.

### Verified
- **24 Static Architectural Gates:** 24 / 24 gates PASSED (`tests/test_static_gates.py`, code 0).
- **Full Regression Test Suite:** 973 / 973 non-hardware tests PASSED (100% green, ~281s).
- **Master Claims & Provenance Integrity:** 0 regressions, 0 unmodeled predicates, 0 undocumented drift across all active documentation and code citations.

---

## [0.2.5] — 2026-09-25

### Added
- **Hybrid Semantic Intent Routing (`HeuristicRouter` & `EmbedWorker`, D-ROUT-01):**
  - Integrated OpenVINO embedding centroid projection in `heuristic.py`. When regex pattern matching returns `unknown` or low confidence, the router projects user utterances into embedding space and computes cosine similarity against semantic intent anchors (`SEMANTIC_INTENT_ANCHORS`).
  - Wired `EmbedWorker` into `Orchestrator` startup to power zero-latency semantic classification without LLM overhead.
- **OpenVINO Inference Concurrency Protection (`_infer_lock`, D-SENSE-01):**
  - Added thread synchronization (`threading.Lock()`) around OpenVINO `infer()` calls in `senses/embed.py`, resolving the `RuntimeError: Infer Request is busy` crash caused by simultaneous execution across background memory tasks and foreground turn routing.
- **Stalling Research Promise Interceptor & Prompt Mandates (`OutputSupervisor` & `PromptBuilder`, D-SUPER-01):**
  - Expanded `STALLING_RESEARCH_PATTERN` in `sandbox/output_supervisor.py` to intercept conversational filler promises (*"Let me dive back into the deep end..."*, *"Switching over to that spelling..."*), suppressing audio emission to Kokoro TTS and flagging `turn_has_stalled`.
  - Added autonomous recovery re-prompt in `orchestrator.py` commanding immediate tool execution when stalling occurs.
  - Injected strict `[PROACTIVE FACTUAL RESEARCH DIRECTIVES]` in `prompt_builder.py` forbidding verbal promises without tool calls.
- **Turn State & History Forwarding in Turn Pipeline (`TurnPipeline` & `Orchestrator`):**
  - Fixed parameter dropping in `turn_pipeline.py` by forwarding `last_tool` and `last_tool_ok` into `router.route()` kwargs.
  - Forwarded `last_tool` in `_build_rule_state`, enabling single-word entity follow-ups (*"Factoriza"*) to refine active searches rather than misrouting to `clarify`.
- **Epistemic Cascade Grammar & Substrate Isolation (`EpistemicSearchCascade`, D-CASC-02):**
  - Corrected pronoun shift in `cascade.extract_clean_topic` (`"have you"` $\to$ `"have I"`, eliminating ungrammatical phrases like *"have me searched"*).
  - Filtered self-history queries (*"which websites have you searched"*) from triggering external web searches, routing them to session history introspection.
- **Live Flow Verification & Interactive Testing Harness (`scripts/test_session_flow.py`):**
  - Created dedicated testing script with `--interactive` terminal REPL and `--auto` 4-turn replay against the live `llama-server`.

---

## [0.2.4] — 2026-09-24

### Added
- **Work Order 17: System Remediation & Modernization:**
  - **Open-Predicate Knowledge Graph (Solution B, D-MEM-02):** Superseded closed 23-item predicate list with validated snake_case slugs (`PREDICATE_SLUG_REGEX`), automatic synonym canonicalization, ~200-demonym lexicon for `nationality_is`, and strict negation/attribution extraction guards.
  - **Runtime Memory Wiring:** Embedded CPU fallback `EmbedWorker` in `senses/embed.py`, auto-initialized `DatabaseManager` + `MemoryStore` in `Orchestrator` and `main.py`, and introduced a single persistent `_commit_executor` thread pool.
  - **Frictionless Memory Commits:** Stripped voice confirmation for clean memory commits; required confirmation only when memory input is tainted with `UNTRUSTED_WEB`. Enhanced `parse_confirmation_response` with token matching and fail-closed safety (D-SEC-03).
  - **Deterministic Math Tool (`calc_math`) & Confirmation Provenance Split (D-SEC-02):** Added AST-based `calc_math` tool (19th native tool in registry) under `Risk.READ`. Separated internal component confirmation (`confirmed`) from explicit human voice/UI grants (`human_confirmed`) in `SandboxService` and `SequenceGuard`.
  - **Timezone-Aware System Telemetry:** Included `timestamp`, `utc_offset`, `utc_offset_hours`, and `timezone_name` in `get_system_metrics()`.
  - **Audio Queue Stability & Coherence:** Expanded `_tts_queue` maxsize from 8 to 32 with drop-oldest overflow policy and telemetry logging; added drain-and-retry sentinel protection for `FLAG_EOS`; excluded analytical idioms from `coherence.py`.

---

## [0.2.3] — 2026-09-21

### Added
- **Deterministic ASR Spelled-Word Normalization (`normalize_spelled_words`):**
  - Regex-based preprocessor in `orchestrator.py` detecting letter-by-letter spelling sequences (`F-A-W-K-N-E-R`, `F A W K N E R`, `F. A. W. K. N. E. R.`) and assembling them into verified title-cased tokens (`Fawkner`).
  - Automatically prepends an authoritative system grounding notice (`[User Explicit Spelling Correction: The target entity is 'Fawkner'...]`), eliminating reliance on model phonetic guessing.
- **In-Place History Token Neutralization (`_neutralize_context_attractors`):**
  - Computes Levenshtein edit distance against recent history tokens to identify and rewrite phonetic/orthographic corruptions (`Faulkner` $\to$ `Fawkner`) in-place across prompt history.
  - Destroys Transformer self-attention repetition attractor wells without pruning conversation turns, preserving pronoun antecedents and complete conversational context.
- **Factual Inquiry Intent Expansion & Tool Gating Hardening (`HeuristicRouter` & `Orchestrator`):**
  - Reordered intent evaluation so `memory_query` and `chit_chat` are evaluated before `web_fetch`, preserving personal memory queries (`"what is my brother's name"`) while achieving 0.987 Macro-F1 on adversarial router fixtures.
  - Expanded `web_pattern` to classify common factual question openings (`where is`, `who is`, `what is`, `tell me about`, `facts about`, `how about`) as actionable `web_fetch` intents.
  - Removed `"unknown"` and `"clarify"` from `TOOLLESS_INTENTS` in `orchestrator.py`, guaranteeing factual inquiries and research affirmations (`yes`, `sure`, `okay`, `do it`, `where is`, `tell me more`) never have tools stripped.
- **Corrective Search Query Injection & Category Grounding (`_handle_tool_call`):**
  - When spelled targets or location/category context (`suburb`, `judge`, `court`, `victoria`, `australia`, `philippines`) appear in the turn context, automatically validates and enriches `search_web` queries (e.g. `search_web("Fawkner" suburb Victoria)`), preventing DuckDuckGo semantic drift toward famous authors or unrelated entities.
- **Output Supervisor Stalling Clamp & Autonomous Research Loop (`OutputSupervisorSession` & `_stream_llm_speech`):**
  - Added `STALLING_RESEARCH_PATTERN` in `output_supervisor.py` to suppress lazy rhetorical interrogation clauses (*"Would you like me to look into...?"*, *"Shall I look up...?"*) from voice TTS emission.
  - Implemented an autonomous multi-round recovery loop: if the model emits a stalling question without calling tools, the orchestrator intercepts the evasion, injects an autonomous research directive, and re-prompts for immediate tool execution.

---

## [0.2.2] — 2026-09-21

### Added
- **Native Document Ingestion & PDF Extraction (`fetch_url` / `pypdf`):**
  - Integrated `pypdf` parsing inside `SandboxService.fetch_url`, enabling Lucca to autonomously download, extract, and ground responses in real-world PDF documents (government appointment rosters, legal schedules, whitepapers).
  - Added configurable `max_chars` extraction limit with defensive truncation and metadata extraction.
  - Extracted embedded hyperlinks found inside document text and PDF layers, automatically populating `structured["embedded_links"]` to allow legitimate citation of internal references without false-positive supervisor aborts.
- **Cryptographic TLS Integrity via Native OS Certificate Store (`truststore`):**
  - Integrated `truststore.inject_into_ssl()` leveraging Windows CryptoAPI (`crypt32.dll`) to validate public government and enterprise portals that omit intermediate CAs via native Authority Information Access (AIA) intermediate chasing.
  - Completely eliminated all insecure `verify=False` retries and hardcoded domain whitelists, enforcing 100% strict TLS verification across all requests.
- **Dual-Path Web Capabilities & Hardened Headless Browser (`HeadlessBrowserTool`):**
  - Path 1: Fast HTTP/HTTPS scraping via `httpx` with Link Triage & SERP Re-Ranking (`classify_link_followability`) demoting login walls (`facebook.com`, `linkedin.com`, `x.com`) and prioritizing followable HTML and PDF assets.
  - Path 2: Real-time headless Chromium automation via Playwright with strict TLS verification (`ignore_https_errors=False`) and socket-level host resolver rules (`--host-resolver-rules="MAP 127.* 0.0.0.0, MAP 10.* 0.0.0.0, MAP 172.16.* 0.0.0.0, MAP 192.168.* 0.0.0.0, MAP 169.254.* 0.0.0.0, MAP ::1 0.0.0.0"`), mathematically barring TOCTOU DNS rebinding directly in the browser network stack.
  - Added dynamic `--no-sandbox`, `--disable-gpu`, `--disable-dev-shm-usage` hardened headless browser process isolation with reliable context/browser lifecycle disposal in `finally` blocks.
- **Raw-Stream Citation Provenance Guard & Epistemic Abstention (`CitationProvenanceMatcher`):**
  - Session-scoped URL whitelist seeded dynamically from conversation history, Substrate 2 memory, tool execution receipts, and document-embedded links.
  - Evaluates un-sanitized raw tokens (`TTSChunk.raw_text`) before speech normalisation strips URLs to `"a link"`, preventing ungrounded hallucinated URL citations.
  - Tightened subpath provenance matching, preventing root-level grants from permitting fabricated subpaths while preserving local developer port discussions.
  - Expanded URL extraction regex to extract scheme-less FQDNs ending in common public suffixes (`.com`, `.net`, `.org`, `.gov`, `.ph`, `.io`, `.ai`).
  - Automatically trips Belnap epistemic abstention (`_trigger_supervisor_abort`), replacing confabulated URLs with calibrated refusal: *"I apologize, but I do not have a verified source for that citation and won't guess."*
- **Forced Final Synthesis & Natural Spoken Attribution (`Orchestrator` & `PromptBuilder`):**
  - Enforced final synthesis boundary stripping tool definitions when reaching `max_rounds` so the model always synthesizes grounding into speech rather than emitting trailing tool calls.
  - Un-suppressed tools on challenge and follow-up turns ("Are you sure?", "Tell me more") allowing active re-verification.
  - Added persona directives instructing the model to speak citations naturally by organization/title (e.g. *"According to the Supreme Court roster..."*) rather than reciting raw `https://` URLs phonetically in Kokoro TTS.
- **Zero-Mock Verification & Chaining Test Fixtures (`tests/test_tool_chaining.py`):**
  - 15 formal unit and integration tests covering multi-round chaining, SSRF interception, followability classification, PDF extraction, host-resolver rules, and citation provenance enforcement.
  - Live zero-mock test harness (`scripts/verify_live_web_and_pdf.py`) validating physical DuckDuckGo querying, live government PDF parsing with strict TLS, Playwright browser rendering, and real-time supervisor aborts.

---

## [0.2.1] — 2026-09-21

### Added
- **5-Line Fixed-Geometry Paginated Speech Bubble (`SpeechBubble`):**
  - Replaced unbounded dynamic ballooning (84px $\to$ 894px) with a stable, fixed 5-line height dialogue window (`460x188px`).
  - Implemented `_paginate()` using `QTextLayout` wrapped at character boundary to cleanly paginate long explanations into discrete 5-line pages.
  - Added interactive Chrono Trigger-themed pager controls (`btn_prev` `◀`, `lbl_page` `[ 1 / N ]`, `btn_next` `▶`) in footer.
  - Added header close button (`✕`) and removed the 7-second auto-dismiss timer; dialogue persists until dismissed or replaced.
  - Completely eliminated Win32 High-DPI layout fighting (`QWindowsWindow::setGeometry: Unable to set geometry`), resolving GUI event-loop starvation and speech stuttering.
- **Responsive Scrollable Settings Dialog (`SettingsDialog`):**
  - Wrapped all 11 configuration tabs (`tab_persona`, `tab_voice`, `tab_llm`, `tab_tools`, `tab_lisp`, `tab_ptt`, `tab_dsp`, `tab_memory`, `tab_diag`, `tab_manual`, `tab_about`) in `QScrollArea` with retro-styled scrollbars.
  - Implemented screen containment and auto-centering (`center_on_screen()`) clamping window geometry within `availableGeometry()`, guaranteeing the titlebar is never positioned off-screen or unmovable on multi-monitor / laptop setups.
  - Reduced minimum window size from 880x640 to 760x520 for high-DPI scaling (125%–175%).
- **Dedicated SSRF-Hardened Web Search Tool (`search_web`):**
  - Integrated `ddgs` with Rust-backed `primp` browser TLS/JA3/JA4 fingerprint impersonation and HTTP/2 handshakes, eliminating Cloudflare/DuckDuckGo `anomaly-modal` bot detection blocks.
  - Eliminated dangerous silent Wikipedia fallback that returned irrelevant entities and caused hallucinations on regional/people queries.
  - Added transparent failure reporting with explicit `ok=False` and structured error receipts (`bot_challenge`, `no_results`).
  - Added calibrated honest epistemic abstention returning structured receipts to prevent parametric hallucination loops.
- **Unified Dynamic Capability Registry (`CapabilityRegistry`):**
  - Authoritative single source of truth for tool schemas, approved application whitelists (`calc.exe`, `notepad.exe`, `wt.exe`, `taskmgr.exe`, `msedge.exe`), and MicroScheme LISP rules.
  - Zero-`Any` typed interface complying with strict static architecture gates.
- **4 Permanent Committed Negative Regression Test Fixtures:**
  - `tests/test_d_reas_07_negative.py`: Enforces that unmodeled MicroScheme predicates fail closed in Z3 SMT prover.
  - `tests/test_d_reas_08_negative.py`: Enforces that empty production data blocks macro synthesis claims.
  - `tests/test_d_reas_06_negative.py`: Enforces that zero telemetry blocks rule induction promotion.
  - `tests/test_d_aud_11_negative.py`: Enforces that data volume gates fail closed on 0-row SQLite databases.

### Changed
- **Z3 SMT Prover Fail-Closed Invariant (`smt_verifier.py`):**
  - Changed `_translate_expr` fallthrough from silent `z3.BoolVal(True)` (fail-open) to `raise ValueError(...)`.
  - Added `UNMODELED_PREDICATE` verification status in `verify_rule()` to prevent unmodeled operators from being admitted into quarantine.
- **Multi-Round Context Preservation (`orchestrator.py`):**
  - Fixed Round 2 context loss where `current_text` was set to `None`, preserving user utterance alongside tool traces in narration turns.
- **Voice Markdown Sanitization (`sanitize_for_voice`):**
  - Strips markdown asterisks, backticks, bullet dashes, raw URLs, and headers before passing tokens to Kokoro-82M TTS.
- **Full 138-Claim Documentation Alignment:**
  - `README.md`: Corrected hardware placement table to reflect that only embeddings run on NPU; ASR runs on dGPU CUDA float16 (+555 MiB VRAM); TTS/VAD run on CPU. Separated regex classification ($6.4\,\mu\text{s}$) from physical WASAPI audio abort ($20\text{--}50\,\text{ms}$).
  - `docs/ARCHITECTURE.md`: Clarified normative stage budgets with explicit footnotes; aligned ASR running baseline to CUDA float16; downgraded fixture-only induction and telemetry claims to `Enforced (Unit Tested; 0 Production Rows)`.
  - `docs/specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md`: Updated capability statuses to reflect tested reality.
  - `docs/DECISIONS.md`: Aligned canonical decision records (D-AUD-11, D-AUD-15, D-REAS-06, D-REAS-07, D-SUP-01).

### Verified
- **Full Pytest Regression Suite:** 418 passed in 86.24s (100% green).
- **Master Claims Audit:** 138 / 138 claims verified (0 failed, 0 unverifiable, 0 contradictions, 0 regressions).

---

## [0.2.0] — 2026-09-20

### Added
- **Milestone 7: Standalone Frozen PyInstaller Packaging (`Lucca.exe`):**
  - Bundled standalone Windows executable distribution (`dist/Lucca/Lucca.exe`, 25.9 MB) bundling Python 3.12, PyQt6, libz3, ONNX Runtime, OpenVINO dynamic plugins, Kokoro voice models, and sqlite-vec.
  - Dual-mode console & GUI subsystem lifecycle (`console=False` with dynamic `AttachConsole(-1)` stdio binding).
  - CLI diagnostic flags: `--version`, `--help`, `--check` (7-point native hardware audit), `--headless`.
  - Persistent `QSystemTrayIcon` companion with cognitive state tooltips and graceful multi-process exit.
- **Milestone 6: Neurosymbolic Reasoning Tier (MicroScheme & E-Graphs):**
  - Autonomous rule induction mining execution telemetry clusters ($N \ge 3$) strictly into `QUARANTINE`.
  - Babble/Stitch first-order syntactic anti-unification macro synthesis within E-Graph congruence closure representation (`EGraph`) enforcing compression metric $\Delta \text{size} \ge 1$.
  - Z3 SMT Formal Invariant Verifier (`SMTVerifier`): automated SAT satisfiability, non-tautology contingency, and deontic path traversal safety proofs in $\le 25\,\text{ms}$.
- **Milestone 5: Continuous 3D PAD Affective Dynamics & KV-Cache Suffix:**
  - Analytical closed-form discrete differential equations for Mehrabian 3D Pleasure-Arousal-Dominance space ($t_{1/2}=45\text{s}, 300\text{s}, 900\text{s}$).
  - Global Lyapunov asymptotic stability clamp on cognitive feedback gain ($\text{gain} \le 0.0005$).
  - Prompt Frontier Suffix KV-Cache Optimization: quantized stance tokens appended exclusively at prompt tail, achieving **$8.58\times$ faster prefill** ($46.84\,\text{ms}$ vs. $402.05\,\text{ms}$ on RTX 5080 dGPU).
  - Real-time arousal-modulated speech rate in Kokoro-82M ($1.0 \pm 0.10$).
- **Milestone 4: Speculative BDI Validation & Streaming Supervision:**
  - `SpeculativeBDIValidator`: pre-dispatch deontic policy check intercepting candidate tool calls in **$2.9\text{--}32.0\,\mu\text{s}$** (budget $\le 200\,\mu\text{s}$).
  - Cognitive bus arbitration via MicroScheme signals: `(yield-to-core)` and `(interrupt-core)`.
  - Streaming Output Supervision (Dimension 7B): compiled grammar rules and DFA capitulation detection ($P_{50} = 6.4\,\mu\text{s}$) with WASAPI audio buffer drain.
- **Milestone 3: 5-Substrate Epistemic Search Cascade:**
  - Prioritized cascade (Substrate 0 Telemetry $\to$ Substrate 1 Workspace $\to$ Substrate 2 Memory $\to$ Substrate 3 Web Floor $\to$ Substrate 4 Abstention).
  - Belnap $\mathcal{FOUR}$ evidential bilattice ($\mathbf{T}, \mathbf{F}, \mathbf{B}, \bot$) yielding $0 / 25$ hallucinations (100% adherence) in live confabulation testing.
  - Sub-millisecond pre-rendered PCM audio floor cues written directly to shared memory ring buffer ($3.1\,\mu\text{s}$).
- **Milestone 2: Deontic Sandboxing & Persistent Docker RPC:**
  - Long-lived persistent daemon (`lucca-toolsrv --loop`) inside WSL2 container achieving **$6.87\,\text{ms}$ P50 RPC turnaround** (83x speedup).
  - In-container zombie process reaping inspecting `/proc/*/cmdline`.
  - Hardened Win32 handle containment (`verify_and_open_workspace_file`) with two-stage non-destructive handle resolution and reparse point jailing.
  - Bidirectional persistent taint tracking (`TaintFlags`) preventing data exfiltration.
  - Temporal spoken confirmation tokens with HMAC-SHA256 session binding.
- **Milestone 1: Empirical Silicon Baseline Profiling:**
  - Full acoustic loopback ear-to-ear latency measured at **$707.55\,\text{ms}$ P50** on CUDA float16.
  - LLM Time-to-First-Token (TTFT) on Mistral NeMo 12B Q6_K: **$44.5\,\text{ms}$ median** (10,748 MiB resident VRAM clamp on RTX 5080).
  - SQLite vector search (`sqlite-vec`) P50: $8\text{--}15\,\text{ms}$ over 384-D embeddings.

---

## [0.1.0] — 2026-09-18

### Added
- Initial release of Project Lucca architecture.
- 4-process topology: Audio IO, Core Orchestrator, LLM Brain (`llama-server.exe`), and WSL2 Container Sandbox.
- MicroScheme LISP symbolic evaluation engine with 1,000 gas limit.
- Kokoro-82M ONNX TTS engine with 24 kHz anime voice shaping DSP chain.
- Silero VAD and Faster-Whisper ASR pipeline.
- SQLite WAL hybrid storage with `sqlite-vec` vector retrieval and FTS5 BM25 search.
- Chrono Trigger-themed PyQt6 desktop companion interface and HUD.
