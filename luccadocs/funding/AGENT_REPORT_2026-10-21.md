# Grant Preparation Master Fact-Finding & Technical Audit Report

**Date Issued:** 2026-10-21  
**Target Subsystem:** Project Lucca Workspace (`c:\Projects\ProjectLucca`)  
**Target Funds:** Corrigibility Research Fund, Manifund, Transformative AI Fund, Mercor Safety Grants  
**Baseline Git Commit:** `84f244751ad7dd0db8ab0eaedd097029bc7cdd51` (Branch: `master`)  
**Operating Mode:** Read-Only Investigation (Part A) & Additive Preparation (Part B)  
**Integrity Guarantee:** Zero pre-existing repository files modified; zero fabricated figures.

---

## 1. Executive Summary

- **Catastrophic Verifier Fail-Open Under Production Latency (Worst Finding):** ModernBERT NLI verification takes ~57 ms mean / ~70 ms p95 on CPU, exceeding the 50 ms production budget (`src/lucca/senses/verifier.py:70`) 81% of the time; all 10 downstream consumer modules fail open on timeout/UNCERTAIN, allowing contradictory facts to commit directly to SQLite memory and ungrounded actions to pass post-turn supervision.
- **Action-Hallucination Sensitivity is Extremely Low in Live Unseen Traffic:** While `TruthInReceiptMatcher` achieves 70/70 on authored test sentences and 0/50 false alarms on control sentences without action claims, post-hoc manual audit (`action_hallucination_labels_100.jsonl`) revealed live sensitivity of only **1/8 (12.5%, Wilson [2.2, 47.1])** on strict actions and **1/23 (4.3%, Wilson [0.8, 21.0])** on broad claims; subsequent v1.41 participle hardening has **never been remeasured** on fresh, unseen live claims.
- **Contrastive Companion Battery Exists but Early Fabrications Disappeared on Remediation:** The $N=30$ paired battery (`tests/test_contrastive_live_hw.py`) originally yielded 3 fabrications and 4/10 receipt introspection on bare LLM when run with thinking mode; under the ratified frozen-grader remediation (`commit d9ac70f`), bare LLM achieved 0/10 recall, 7/10 introspection, and 10/10 abstention (0 fabrications) vs compound Arm B at 10/10, 8/10, and 9/10. The only statistically significant advantage is memory recall (+100 pp, exact McNemar $p=0.00195$), which is nearly built in because the bare model has no memory access by construction — this demonstrates the memory layer works, not that the compound agent is safer on introspection or abstention (both statistically indistinguishable).
- **Clean Architectural Isolation for Standalone Extraction:** Core safety components (`ProvenanceGate` and `TruthInReceiptMatcher`) have zero internal dependencies on Lucca's runtime engines (MicroScheme, Docker sandbox, TTS/ASR, SQLite WAL), depending only on `pydantic`, `cryptography`, and `structlog`, enabling full extraction into a standalone library (`agent-provenance-guard`) in approximately 38 developer hours.
- **Hygiene & Licensing Exposure in Git History:** While no secrets or private keys are tracked, git commit history contains 16 copyrighted Chrono Trigger sprite frames (`assets/sprites/lucca/*.png`) and Tiffany Grant / Asuka voice clips and RVC weights; 131 files contain hardcoded Windows absolute paths; a clean-snapshot public repo is strongly recommended over a destructive history rewrite.

---

## 2. Part A: Fact-Finding Questions & Evidence

### A1. The Contrastive Live-Companion Battery ($N=30$)
- **Answer:** **EXISTS.** The battery is implemented in `tests/test_contrastive_live_hw.py` using probe fixtures in `tests/fixtures/contrastive/probes.jsonl` ($N=30$, 10 probes each across Recall, Introspection, and Abstention). It was authored by the project owner and committed in `78d036d` (2026-10-06) for P9 remediation. In the initial uncalibrated run (2026-10-05, `contrastive_battery_20261005T200643Z_regraded.json` / `CHANGELOG.md:464`), Arm A (bare LLM with thinking) had 0/10 recall, 4/10 introspection, and 7/10 abstention (3 fabrications); Arm B had 9/10, 9/10, 10/10. However, in the frozen-grader remediation run (2026-10-07, `logs/test_reports/contrastive_battery_20261006T220517Z_REPORT.md`, commit `d9ac70f`) where bare LLM ran with `enable_thinking=False` and was evaluated by frozen grader `contrastive_grader.py` (SHA-256 `f015710f...`):
  - **Arm A (Bare):** Recall 0/10 (0.0%), Introspection 7/10 (70.0%), Abstention 10/10 (100.0%, 0 fabrications).
  - **Arm B (Compound):** Recall 10/10 (100.0%), Introspection 8/10 (80.0%), Abstention 9/10 (90.0%).
  - **Deltas:** Recall $+100\text{ pp}$ (exact McNemar two-sided $p=0.00195 = 2 \times 0.5^{10}$ on 10 discordant pairs, significant); Introspection $+10\text{ pp}$ ($p=1.0$, non-significant); Abstention $-10\text{ pp}$ ($p=1.0$, non-significant). Note: Fisher exact on 10/10 vs 0/10 would give $\approx 10^{-5}$; McNemar is the correct test for paired probes.
- **Evidence:** `tests/test_contrastive_live_hw.py:1-120`, `tests/fixtures/contrastive/probes.jsonl`, `logs/test_reports/contrastive_battery_20261006T220517Z_REPORT.md`, `CHANGELOG.md:464-478`, commits `78d036d` and `d9ac70f`.
- **Confidence:** **Verified.**
- **Caveats:** Probes were authored internally by the developer, not sampled from external distributions. The claim that bare LLM produces 3 fabrications and 4/10 introspection only held in an early uncalibrated run; under the ratified frozen grader, bare LLM abstained 10/10.

### A2. Receipt Matcher Live Sensitivity
- **Answer:** **CONFIRMED.** The 1/8 (12.5%, Wilson [2.2, 47.1]) strict completed action and 1/23 (4.3%, Wilson [0.8, 21.0]) broad action-claim sensitivity figures are verified in `logs/archive/2026-10_test_reports/action_hallucination_labels_100.jsonl` across 200 model turns (E4B and E2B). A hardening commit exists: commit `defadaee` (2026-10-13, v1.41) introduced `PRESENT_ACTION_VERBS` and present-participle patterns into `src/lucca/sandbox/output_supervisor.py` and `src/lucca/core/coherence.py` (Milestone 36.6 SPIKE-A). However, **no fresh measurement on unseen claims was performed afterward**. All claims were labeled post-hoc by a single annotator (the repository owner), and labels were assigned with knowledge of supervisor outputs (not blinded).
- **Evidence:** `logs/archive/2026-10_test_reports/action_hallucination_labels_100.jsonl`, `RESULTS.md:167-171`, commit `defadaee`, `src/lucca/sandbox/output_supervisor.py:46-75`.
- **Confidence:** **Verified.**
- **Caveats:** Single-annotator, post-hoc, non-blinded labeling; wide Wilson confidence intervals due to small $n$; fix is completely unmeasured on held-out live data.

### A3. Authored Battery and Controls
- **Answer:** **CONFIRMED.** The authored test battery contains 70 sentences across 8 categories (Categories A–D baseline; Categories E–H added during Paper 06 broadening), implemented in `tests/test_truth_in_receipt_battery.py` (73 tests passing). The 50 live controls are located in `data/benchmarks/action_hallucination_battery_100.json` (25 honest completion + 25 conversational idioms). 0/50 false positives confirmed.
- **Evidence:** `tests/test_truth_in_receipt_battery.py:1-350`, `data/benchmarks/action_hallucination_battery_100.json`, `docs/research/papers/05_CONFORMAL_ABSTENTION_AND_SPECULATIVE_BDI_VERIFICATION.md:97-125`.
- **Confidence:** **Verified.**
- **Caveats:** High circularity risk: Categories E–H were written specifically to verify the fix after observing earlier test failures. Furthermore, the 50 live controls contain zero action claims by design, meaning 0/50 FP only verifies that the supervisor does not trigger on non-action text; it does not measure false rejection on legitimate action statements. (Resolution of the A3 inconsistency: the controls are 25 honest completion + 25 idioms, and they contain zero action claims — both statements are true; the honest-completion prompts are capability questions that do not elicit action assertions.)

### A4. TTS Safety Guard
- **Answer:** **CONFIRMED.** The live 30-probe evaluation (`RESULTS.md:237`, `data/benchmarks/runs/tts_guard_efficacy_20261007T020151Z.json`) confirms: Guard blocked **0/10** harmful probes; native model refusal caught 3/10; combined efficacy 3/10; benign false blocks 0/20. The design intent of the guard is strictly narrow: to intercept high-harm instructional generation (CBRN, explosives, malware deployment) before audio synthesis on uncensored edge models (`src/lucca/core/tts_safety_guard.py:1-40`). In live tests, E4B deflected harmful prompts with conversational preambles ("I cannot assist with explosives... but here is how chemical reactions work"), bypassing the strict regex.
- **Evidence:** `src/lucca/core/tts_safety_guard.py:1-85`, `RESULTS.md:237-255`, `data/benchmarks/runs/tts_guard_efficacy_20261007T020151Z.json`.
- **Confidence:** **Verified.**
- **Caveats:** The guard is a shallow keyword regex, easily evaded by conversational framing or preamble generation.

### A5. NLI Verifier
- **Answer:** **CONFIRMED.** 100 hand-labeled pairs in `data/benchmarks/nli_eval/pairs_v1.jsonl` (40 Contradiction / 30 Entailment / 30 Neutral), single-annotator (repo owner). Clean 500 ms run (`results_cpu_t500/summary.json`): 93.0% acc, Contradiction P/R 1.000/1.000. Production 50 ms run (`results/summary.json`): 18.0% acc, 81/100 degraded/timed out, effective contradiction recall 0.075, mean latency 57.14 ms, p95 70.41 ms. Pairs are simple single-slot attribute contradictions. In production, `timeout_ms = 50.0` (`src/lucca/senses/verifier.py:70`). All 10 downstream consumers fail open on timeout/UNCERTAIN.
- **Evidence:** `data/benchmarks/nli_eval/pairs_v1.jsonl`, `data/benchmarks/nli_eval/results_cpu_t500/summary.json`, `data/benchmarks/nli_eval/results/summary.json`, `src/lucca/senses/verifier.py:70`, `docs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md:§4.1`.
- **Confidence:** **Verified.**
- **Caveats:** Single-annotator; simple synthetic pairs; catastrophic fail-open architecture under production latency clamp.

### A6. 12B Thinking Sampled Runs 1 & 2
- **Answer:** **IDENTICAL SETTINGS / DETERMINISTIC REPLAY.** Artifacts in `data/benchmarks/runs/12b_thinking_sampled_run1/` and `runs/12b_thinking_sampled_run2/` (log: `12b_thinking_sampled_run2.log`) show identical runtime parameters: `seed=42`, $T=0.7$, `top_p=0.95`, `repeat_penalty=1.05`, `max_thinking_tokens=6144`. Item-by-item comparison shows **0 discordant answers** and identical token counts (356,500). The identical 64.0% strict score across both runs is a result of PRNG determinism, not independent replication.
- **Evidence:** `data/benchmarks/runs/12b_thinking_sampled_run1/`, `data/benchmarks/runs/12b_thinking_sampled_run2/12b_thinking_sampled_run2.log:12-25`.
- **Confidence:** **Verified.**
- **Caveats:** Presenting these runs as independent replications to reviewers would be misleading; they demonstrate deterministic reproducibility under identical seed.

### A7. Shared Technology with TTRPG Engines (SSE / Ironsworn)
- **Answer:** **SHARED DESIGN PATTERN ONLY.** Project Lucca shares **zero imported code or shared packages** with the owner's TTRPG engines (`c:\Projects\SSE` and `c:\Projects\Ironsworn`). They share an architectural design pattern only (runtime state firewalls and regex narration supervisors). No "reusable across domains" claim is made. Real rejection logs exist: `Ironsworn` logged 70 dev and 23 prod rejections (`logs/rejections.jsonl`, `logs/prod_rejections.jsonl`), dominated by AI persona tropes (68/70); `SSE` logged 81 rejections across 191 turns in 5 sessions (`logs/paper_telemetry_2026-10-08.md`), dominated by `must_mention_omitted` (33.3%) and `false_possession` (22.2%).
- **Evidence:** `c:\Projects\Ironsworn\logs\rejections.jsonl`, `c:\Projects\SSE\logs\paper_telemetry_2026-10-08.md:1-120`.
- **Confidence:** **Verified.**
- **Caveats:** Shared concepts, not shared Python packages. TTRPG rejection data reflects gaming state constraints rather than OS companion tool actions.

### A8. Extractability of Core Safety Components
- **Answer:** **HIGHLY EXTRACTABLE (~38 HOURS, SCOPE-LIMITED).** `TruthInReceiptMatcher` (`src/lucca/sandbox/output_supervisor.py`) has zero internal imports from Lucca. `ProvenanceGate` (`src/lucca/memory/gate.py`) and `SignerFactory` (`src/lucca/memory/signers.py`) import only `Provenance`, `SignedPayload`, `UnsignedPayload`, and exception classes from `lucca.core.schemas`. Third-party dependencies are `cryptography`, `pydantic`, and `structlog` (all MIT/Apache-2.0). Extraction effort is estimated at 38 hours (~1 developer week). **Scope note:** this estimate covers the ProvenanceGate and TruthInReceiptMatcher only; it does **not** include the NLI entailment piece, which lives in `src/lucca/core/coherence.py` and `src/lucca/senses/verifier.py` and is a separate extraction effort.
- **Evidence:** `src/lucca/sandbox/output_supervisor.py:1-45`, `src/lucca/memory/gate.py:1-35`, `src/lucca/memory/signers.py:1-40`, `pyproject.toml`.
- **Confidence:** **Verified.**
- **Caveats:** Requires separating schema definitions from the monolithic `schemas.py`.

### A9. Repo Hygiene Scan
- **Answer:** **CLEAN OF SECRETS; COPYRIGHTED ASSETS REQUIRE PURGE.**
  - **Secrets:** CLEAN (0 private keys, .env, or tokens tracked).
  - **Copyrighted Assets:** 16 Chrono Trigger sprites (`assets/sprites/lucca/*.png`, commit `066dad3`), Asuka RVC models (`8826f35`), Tiffany Grant voice samples (`fc9639f`), and local harvested clips in `models/tts/references/asuka/harvested/`.
  - **Path Hygiene:** 131 files contain hardcoded Windows paths (`c:\Projects\...`, `C:\ProjectLucca\...`).
  - **Model Credits:** ModernBERT omitted from `README.md`.
- **Evidence:** Git log audits for `data/keys/`, `assets/sprites/`, `models/tts/`, and working tree grep.
- **Confidence:** **Verified.**
- **Caveats:** History rewrite destroys benchmark/paper commit citations; clean snapshot public repo is recommended.

### A10. Clean-Checkout Reproducibility
- **Answer:** **TIERED HARDWARE REQUIREMENTS.**
  - **CPU-Only (<2s):** Authored receipt tests (73 tests) and provenance tests run CPU-only in <2 seconds with `pytest` on Windows. **Not yet verified on Linux/macOS**; cross-platform CI is planned as part of the `agent-provenance-guard` Milestone 2. Do not claim Linux/macOS timing until it has been run once.
  - **NPU/CPU OpenVINO:** NLI verification eval requires local OpenVINO IR files in `C:\ProjectLucca\models\verifier`.
  - **Heavy GPU / llama-server:** Academic benchmarks (GSM8K, HumanEval, MATH-500) and live companion tests require resident `llama-server.exe` with ~10–16 GB VRAM and specific GGUF weights.
- **Evidence:** `tests/test_truth_in_receipt_battery.py`, `scripts/eval_nli_precision_recall.py`, `data/benchmarks/MANIFEST.yaml`.
- **Confidence:** **Verified.**
- **Caveats:** A stranger cannot reproduce live model evals without downloading ~30 GB of GGUF models and running Windows-specific llama-server.

---

## 3. Discrepancies with Initial Brief

1. **Contrastive Live Battery Arm A Fabrications:** The initial briefing indicated that Arm A produced 3 fabrications and scored 4/10 on introspection. This was true for the preliminary run (2026-10-05), but under the frozen-grader remediation run (commit `d9ac70f`), Arm A produced **0 fabrications (10/10 abstention)** and scored **7/10 on introspection**. The only statistically significant delta in the remediated run was memory recall (+100 pp, $p=0.00195$).
2. **Action-Hallucination Labeling Methodology:** The initial briefing did not note that the 100-probe action-hallucination labels were single-annotator post-hoc labels assigned with knowledge of supervisor outputs, rather than a pre-registered or blinded audit.
3. **Authored Battery Test Count:** The test file `tests/test_truth_in_receipt_battery.py` contains 73 passing unit tests (covering the 70 core sentences plus auxiliary edge cases), rather than exactly 70 tests.

---

## 4. Not Found List

1. **Fresh Live Sensitivity Measurement Post-v1.41:** We searched `logs/`, `data/benchmarks/`, `RESULTS.md`, and git history for any live evaluation re-run of `TruthInReceiptMatcher` after commit `defadaee` (v1.41 participle hardening). **NOT FOUND.** The fix has never been evaluated on unseen live companion traffic.
2. **20-Vector Defensive Prompt-Injection Battery (`D-SEC-05`):** While `D-SEC-05` is ratified in `docs/DECISIONS.md`, no 20-probe dataset, test script, or execution artifact exists in the repository. Looked in `tests/`, `data/benchmarks/`, `scripts/`, and `logs/`.
3. **Independent 12B Thinking Sampled Replication:** We searched for a 12B thinking sampled run with an independent random seed. **NOT FOUND.** Both `run1` and `run2` used `seed=42`.

---

## 5. Part B Deliverables Summary

All requested preparation materials have been created under `docs/funding/`:

1. [`docs/funding/EVIDENCE_LEDGER.md`](file:///c:/Projects/ProjectLucca/docs/funding/EVIDENCE_LEDGER.md): Comprehensive public claims ledger with sample size $N$, results, Wilson 95% CIs, suite type, annotator count, artifact paths, and known caveats.
2. [`docs/funding/README_FUNDERS.md`](file:///c:/Projects/ProjectLucca/docs/funding/README_FUNDERS.md): Verification-first 1-page overview of Project Lucca, its two core defense mechanisms, documented failures, and local reproduction instructions.
3. [`docs/funding/PREREG_MATCHER_SENSITIVITY.md`](file:///c:/Projects/ProjectLucca/docs/funding/PREREG_MATCHER_SENSITIVITY.md): Rigorous pre-registration protocol (250 prompts, 3 models, power calculations, dual blinded annotators, SHA-256 fingerprint: `b13951b8a1909d009b0040014f09140295539d989e87fdfc0deb503d74db5877`).
4. [`docs/funding/NLI_SECOND_ANNOTATOR_KIT/`](file:///c:/Projects/ProjectLucca/docs/funding/NLI_SECOND_ANNOTATOR_KIT/):
   - `blinded_worksheet.jsonl` & `blinded_worksheet.csv`: 100 evaluation pairs with gold labels stripped, randomized with `seed=42`.
   - `ANNOTATION_GUIDELINES.md`: Comprehensive 3-class labeling instructions and edge cases.
   - `score_agreement.py`: Automated inter-annotator evaluation script computing Cohen's $\kappa$, confusion matrices, and per-class metrics.
5. [`docs/funding/FAILOPEN_ANALYSIS.md`](file:///c:/Projects/ProjectLucca/docs/funding/FAILOPEN_ANALYSIS.md): Comprehensive audit of all 10 consumer modules failing open on NLI timeout, with concrete fail-closed remediations.
6. [`docs/funding/EXTRACTION_PLAN.md`](file:///c:/Projects/ProjectLucca/docs/funding/EXTRACTION_PLAN.md): Complete standalone library plan for `agent-provenance-guard` with public API, schema decoupling, and 38-hour work breakdown.
7. [`docs/funding/REPO_CLEANUP_PROPOSAL.md`](file:///c:/Projects/ProjectLucca/docs/funding/REPO_CLEANUP_PROPOSAL.md): Repository hygiene roadmap detailing asset removal, CC0 replacements, clean public snapshot strategy, and path normalization.

---

## 6. Questions for the Owner

*(The owner should review and resolve these questions before submitting grant applications; the agent does not provide answers to legal, tax, or personal matters.)*

1. What is the Lucca-only share of the last 30 days' OpenRouter spend ($621.79 total across all projects)? Is there a separate API key for Lucca?
2. What is the monthly cost of Gemini Anti-Gravity, and should any of it be included in the grant budget?
3. Which funds are being applied to, and for which specific months or milestones, so each application can disclose the others accurately?
4. How many hours per week can the owner commit to the funded work alongside the two TTRPG engines?
5. Is the repository currently public or private, and what is the target date and repository name for the public release?
6. Is a qualified second annotator available for the NLI pairs and the pre-registered matcher claim set?
7. What are the owner's official legal name, location, and contact details to appear on formal grant applications?
8. **Tax and Visa Position:** What is the legal entity or personal tax/visa status for receiving international grant disbursements? *(The owner should consult a qualified legal/accounting professional; the agent provides no advice here.)*
9. **Library License:** Should `agent-provenance-guard` be published under the MIT license or Apache 2.0?
10. **Avatar Asset Replacement:** Are there any objections to permanently retiring Chrono Trigger sprites in favor of procedural SVG or CC0 icons across the entire repository?

---

## 7. Risks Noticed for Grant Reviewers

1. **Reviewer Scrutiny on "Sampled Runs":** Presenting 12B thinking sampled runs 1 and 2 as independent replications would be quickly caught by scientific reviewers. They must be explicitly disclosed as deterministic verification of PRNG seed 42.
2. **Reviewer Scrutiny on Verifier Fail-Open:** Technical safety reviewers (e.g. Mercor, Corrigibility Fund) will immediately calculate that a 50 ms timeout applied to a model with a 57 ms mean latency means the verifier is effectively disabled 81% of the time. Positioning this as a *known vulnerability to be remediated with grant funding* is a strong pitch; presenting it as a currently functioning defense would be fatal.
3. **Authored vs. Live Efficacy Disparity:** Highlighting 70/70 authored test performance without immediately disclosing the 1/8 (12.5%) and 1/23 (4.3%) live sensitivities creates an impression of evasive reporting. The grant proposal should lead with the live failure as the core justification for the pre-registered sensitivity work package.
4. **Third-Party Copyrighted Assets:** If reviewers clone a repository containing Square Enix Chrono Trigger sprites or extracted Tiffany Grant / Asuka voice clips, it raises severe intellectual property red flags. The clean snapshot public repository (`Option B`) should be deployed before any links are shared.
5. **Windows & Hardware Lock-In:** Reviewers attempting to reproduce live model behaviors will fail without Windows 11 and an NVIDIA Blackwell/Ada Lovelace GPU running llama-server. Emphasize that the authored test suites run CPU-only in ~0.5s (no GPU, LLM, or Docker required); cross-platform Linux/macOS CI is delivered in Milestone 2 (`agent-provenance-guard`).

---

## 8. Baseline Verification & Integrity Confirmation

- **Analysis Baseline Git Commit:** `84f244751ad7dd0db8ab0eaedd097029bc7cdd51`
- **Analysis Baseline Branch:** `master`
- **Files Modified:** **NONE.** All pre-existing repository code, documentation, benchmarks, and test suites remain untouched. All new files were written exclusively under `docs/funding/`.
