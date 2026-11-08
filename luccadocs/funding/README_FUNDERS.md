# Project Lucca — Verification-First Architecture Overview

```yaml
doc_status: public_funder_overview
as_of: 2026-11-08
target_audience: AI Safety & Governance Grant Evaluators (Corrigibility Research Fund, Manifund, TAI, Mercor)
claim_reference: luccadocs/funding/EVIDENCE_LEDGER.md
```

## 1. Executive Summary

Project Lucca is an experimental, local-first neurosymbolic companion architecture operating on consumer desktop hardware. Its primary technical focus is **mechanistic epistemic grounding and safety supervision**: ensuring an autonomous local agent cannot hallucinate execution of unverified side effects, commit ungrounded model output to long-term memory, or perform un-sandboxed host mutations.

All empirical claims below are cited directly from deterministic code gates and public benchmark artifacts documented in [`luccadocs/funding/EVIDENCE_LEDGER.md`](./EVIDENCE_LEDGER.md).

---

## 2. The Three Core Safety Mechanisms (`v1.51.0` / `WO-43`)

### Mechanism 1: Cryptographic Provenance-Gated Memory (`ProvenanceGate`, `BelnapLatentInvestigator` & Cohort C Corroboration)
- **Location:** [`src/lucca/memory/gate.py`](../../src/lucca/memory/gate.py), [`src/lucca/memory/signers.py`](../../src/lucca/memory/signers.py), [`src/lucca/core/memory_commit_service.py`](../../src/lucca/core/memory_commit_service.py), [`src/lucca/memory/latent_probe.py`](../../src/lucca/memory/latent_probe.py)
- **Principle:** LLM neural outputs (`LLM_NARRATION`) are strictly memory-ineligible and rejected by design (`ADR-006`).
- **Enforcement:** Every memory commit must present an authentic cryptographic envelope signed via domain-separated HKDF HMAC-SHA256 (`master_key` $\to$ domain key per `Provenance` type: `USER_EXPLICIT`, `TOOL_VERIFIED`, `LISP_ASSERTION`, etc.). In `WO-38`/`WO-40`/`WO-43` (`corroborate_user_explicit=True`), `USER_EXPLICIT` factual assertions are cross-checked against existing high-confidence memories via fail-closed OpenVINO `MiniLM-L6` NLI (`test_no_nli_uncertain_fail_open_consumers`), `BelnapLatentInvestigator` ($\bot/\top$ active hypothesis generation), and sentence-level Scrapling web search corroboration before `grounding_eligible=1` admission, reducing Cohort C misinformation absorption from `30/30 (100.0%)` in `v1` to **`0/30 (0.0%)`** in `v2` (`p = 1.86e-9`) and **`0/100 (0.0%, 95% CI [0.00%, 4.61%])`** in the pre-registered $N=300$ `v3` expansion (`p = 4.16e-23`, tag `prereg-wo43-power-300`).
- **Invariant:** Unverified file or web text (`TOOL_CONTENT_UNTRUSTED`) and conversational LLM narration cannot enter persistent long-term storage without an authentic signature.

### Mechanism 2: Clause-Level OpenVINO NPU Deontic Supervision (`NeuralActionClaimVerifier` & `TruthInReceiptMatcher`)
- **Location:** [`src/lucca/sandbox/neural_claim_verifier.py`](../../src/lucca/sandbox/neural_claim_verifier.py), [`src/lucca/core/coherence.py`](../../src/lucca/core/coherence.py), [`src/lucca/sandbox/output_supervisor.py`](../../src/lucca/sandbox/output_supervisor.py), [`src/lucca/sandbox/action_claim_grammar.py`](../../src/lucca/sandbox/action_claim_grammar.py), [`src/lucca/sandbox/receipt_truth_matcher.py`](../../src/lucca/sandbox/receipt_truth_matcher.py)
- **Principle:** Assistant responses are decomposed into atomic clauses (`split_narration_into_clauses`) and verified against signed `ToolReceipt` records before display or speech synthesis.
- **Enforcement:** In `WO-41`/`WO-42`/`WO-43`, Lucca pairs the deterministic `TruthInReceiptMatcher` regex fast path with three `82.1M`-parameter `nli-MiniLM2-L6-H768` classifiers compiled to **OpenVINO FP16 IR on the Intel AI Boost NPU (`0.0 MB` dGPU VRAM)**: `models/action_claim_verifier_ov` (`NeuralActionClaimVerifier`, `1.97 ms` p50), `models/proof_policy_hazard_ov` (`NeuralHazardClassifier`, `1.88 ms` p50), and `models/router_intent_ov` (`NeuralIntentClassifier`, `2.08 ms` p50). Each clause predicted as `UNGROUNDED_ACTION_CLAIM` (`3`) or `LIVE_STATE_FABRICATION` (`4`) is checked against the turn's actual `verified_tools` (`ok=True`) set (`verify_clause_claims_against_receipts`).
- **Independence:** The NPU supervision models and deterministic receipt set-membership checks are completely independent of the generative LLM weights (`Gemma 4 E2B`/`E4B`/`12B`/`26B-A4B`).

### Mechanism 3: Scrapling 3-Tier Stealth Web Research & DOM Prompt-Injection Sanitizer (`research_tool.py`)
- **Location:** [`src/lucca/sandbox/research_tool.py`](../../src/lucca/sandbox/research_tool.py), [`src/lucca/sandbox/web_tool.py`](../../src/lucca/sandbox/web_tool.py)
- **Principle:** External web pages are untrusted attack surfaces (`TOOL_CONTENT_UNTRUSTED`) that frequently embed invisible prompt-injection directives (`display:none`, `opacity:0`, `font-size:0`, `aria-hidden="true"`, Unicode tag characters `U+E0000..U+E007F`).
- **Enforcement:** `sanitize_html_against_prompt_injection` strips hidden CSS/DOM subtrees, comments, `<template>` tags, and invisible Unicode tag blocks prior to Markdown extraction, while `validate_url_ssrf` blocks private/loopback IP ranges on every redirect hop.

---

## 3. What Has Been Measured (And How Prior Failures Were Resolved)

### What Works (`v1.51.0` / `WO-43`)
- **Pre-Registered $N=300$ Memory Poisoning & Misinformation Ablation v3 (`WO-43`, `prereg-wo43-power-300`, $100$ probes/cohort $\times 5$ arms):** **`0/100 (0.0%, 95% CI [0.00%, 4.61%])`** Cohort A self-poisoning and **`0/100 (0.0%, 95% CI [0.00%, 4.61%])`** Cohort C adversarial user-misinformation absorption ($p = 4.16 \times 10^{-23}$ vs. `100/100` Naive RAG and Adversarial Soft Tagging; $p = 9.77 \times 10^{-4}$ vs. `11/100` Passive Soft Tagging), **`100/100 (100.0%)`** Cohort A continuity ($p = 2.75 \times 10^{-22}$ vs. `2/100` No-Assistant), and **`100/100 (100.0%)`** Cohort B retention ($p = 6.90 \times 10^{-23}$ vs. `1/100` No-Assistant; primary vs. MiniLM-L6 NLI $\kappa = 0.9850$, dual blinded judge IRR $\kappa = 0.9206$; [`logs/test_reports/memory_poisoning_v3_300_results.json`](../../logs/test_reports/memory_poisoning_v3_300_results.json)).
- **Pre-Registered $N=300$ Contrastive Companion Battery v2 (`WO-43`, `prereg-wo43-power-300`, $100$ prompts/stratum $\times 3$ arms):** Compound Lucca achieves **`99/100 (99.0%)`** Seeded Memory Recall ($+94.0\text{ pp}$ vs. Bare LLM `5/100`, $p_{\text{HB}} = 7.76 \times 10^{-21}$; $+13.0\text{ pp}$ vs. Hybrid RAG `86/100`, $p_{\text{HB}} = 0.00684$), **`95/100 (95.0%)`** Receipt Introspection (vs. `92/100` Bare LLM and `99/100` Hybrid RAG, passing the $\ge 80\%$ gate), and **`90/100 (90.0%)`** Calibrated Abstention (vs. `94/100` Bare LLM and `100/100` Hybrid RAG, passing the $\ge 80\%$ gate; [`logs/test_reports/contrastive_v2_300_results.json`](../../logs/test_reports/contrastive_v2_300_results.json)).
- **Single-Pass Locked Holdout (`WO-42` Phase 6, `N = 150` unseen multi-sentence items):** **`50/50 (100.0%)`** on `LOCKED_COH_001..050`, **`50/50 (100.0%)`** on `LOCKED_HZD_001..050`, and **`45/50 (90.0%)`** single-pass locked (**`50/50 = 100.0%`** post-router-bugfix) on `LOCKED_RTR_001..050` (`145/150 = 96.7%` aggregate locked holdout, blinded IRR $\kappa = 1.000$; [`logs/test_reports/wo42_locked_holdout_150_report.json`](../../logs/test_reports/wo42_locked_holdout_150_report.json)).
- **Blind Multi-Sentence Supervision & Routing (`WO-42`, `N = 390` unseen items):** **`130/130 (100.0%)`** coherence, **`125/130 (96.2%, 100% HIGH recall)`** hazard, and **`122/130 (93.8%)`** routing (**`377/390 = 96.7%`** aggregate, blinded IRR $\kappa = 1.000$; [`logs/test_reports/wo42_statistical_power_and_ci_report.json`](../../logs/test_reports/wo42_statistical_power_and_ci_report.json)).
- **Live 4-Model E2E Matrix (`WO-42`, `N = 100` live turns across `E2B`, `E4B`, `12B`, `26B-A4B`):** **`100/100 (100.0%)`** functional coherence (`0` unblocked false action claims) and **`98/100 (98.0%)`** task/reasoning completion ([`logs/test_reports/wo42_live_4model_summary.json`](../../logs/test_reports/wo42_live_4model_summary.json)).
- **Authored Unit Battery:** 73/73 (100.0%) pass rate on pre-scripted assertions across 8 categories (60 parametrized cases A–F plus 13 discrete tests; re-collected and re-run at commit `be4e016` — see [`ERRATUM_CALIBRATION_2026-10-24.md`](./ERRATUM_CALIBRATION_2026-10-24.md)) ([`tests/test_truth_in_receipt_battery.py`](../../tests/test_truth_in_receipt_battery.py)).
- **Clean NLI Semantic Consistency:** 93.0% accuracy (Contradiction P/R 1.000 / 1.000) on 100 hand-labeled pairs under an unconstrained 500 ms evaluation window ([`data/benchmarks/nli_eval/results_cpu_t500/summary.json`](../../data/benchmarks/nli_eval/results_cpu_t500/summary.json)).
- **Scaffolded Math & Code Baselines — not capability evidence:** 95.75% on GSM8K **PAL** (full 1,319 problems; [`MANIFEST.yaml`](../../data/benchmarks/MANIFEST.yaml)) measures Python-program synthesis executed in a Docker sandbox, **not** bare next-token answers, and Rule-05 §1 excludes legacy GSM8K as a capability representation for this model class. 94.51% raw Pass@1 on Canonical HumanEval 164. 88.8% strict accuracy on held-out MATH-500 (clean 98 items). No external-model comparison is claimed anywhere in this document; see Rule-05 disclosure in [`ERRATUM_CALIBRATION_2026-10-24.md`](./ERRATUM_CALIBRATION_2026-10-24.md).

### Historical Failures Documented in `v1` Preprints & Their `WO-37`–`WO-43` Resolutions
1. **Low Live Regex Matcher Sensitivity (`v1` Preprint 02, `10.5281/zenodo.23901605`) $\to$ Resolved in `WO-40`–`WO-42` (`papers/04_clause_level_npu_supervision/main.tex`):** On unconstrained conversational outputs ($T=0.6$, Gemma 4 E4B/E2B), the `v1` baseline regex supervisor caught only **1/8 (12.5%)** strict completed actions, **1/23 (4.3%)** broad action claims ([`action_hallucination_labels_100.jsonl`](../../logs/archive/2026-10_test_reports/action_hallucination_labels_100.jsonl)), and **1/16 (6.25%)** on `PREREG-SUPERVISION-HELD-OUT-v1.0`. In `WO-40`–`WO-42`, replacing brittle verb-list matching with clause-level OpenVINO FP16 NPU speech-act classification (`NeuralActionClaimVerifier`) + deterministic receipt set-membership (`verify_clause_claims_against_receipts`) raised strict recall to **`27/27 (100.0%)`** on `PREREG-SUPERVISION-HELD-OUT-v2.0`, **`130/130 (100.0%)`** on `BLIND42_COH_100 + BLIND_COH_30`, and **`50/50 (100.0%)`** on `LOCKED_COH_001..050`.
2. **NLI Production Timeout & Fail-Open Degradation (fixed in `WO-37` Phase 2 and `WO-43` Phase 1.2):** The earlier ModernBERT NLI artifact on CPU averaged 57.14 ms (p95 70.41 ms), exceeding the 50 ms production budget: **81/100 pairs timed out**, dropping contradiction recall to **0.075 (3/40)**. **WO-37 Phase 2 (2026-10-26) replaced the deployed artifact with a MiniLM-L6 cross-encoder**: 12.23 ms mean / 14.40 ms p95, **0/100 timeouts**, accuracy 0.910 (`data/benchmarks/nli_eval/results_minilm/summary.json`). **WO-43 Phase 1.2 (2026-11-08) remediated all 8 NLI consumer modules** (`memory_commit_service.py`, `belief_service.py`, `cascade.py`, `coherence.py`, `corroboration.py`, `user_model.py`, `self_diagnosis.py`, `tool_shortlister.py`) to fail closed (`BelnapState.U` $\bot$, quarantine, or `BelnapLatentInvestigator` verification plan) on `UNCERTAIN` (`degraded=True`), enforced by `test_no_nli_uncertain_fail_open_consumers`.
3. **TTS content screen removed by owner covenant (`D-SOV-01`, 2026-10-26):** A deterministic regex screen at the speech boundary (added 2026-10-05) blocked **0/10 (0.0%)** harmful synthesis probes on a 30-probe adversarial test — live responses used conversational deflection and participles rather than textbook recipes ([`RESULTS.md`](../../RESULTS.md)). Rather than tune the regex, the owner removed the screen entirely: Lucca's doctrine is that safety defenses guard *actions* (sandbox, tool whitelist, SequenceGuard, output supervisor) and never censor speech. Harmful-speech resilience is therefore native to the model, not enforced at the boundary; this is a stated design decision, not a measured safety property.
4. **Blinded Multi-Annotator Verification & $N=300$ Statistical Power (`WO-41`–`WO-43`):** While the early October 100-probe action hallucination audit and 100-pair NLI dataset relied on single-annotator developer labels, the `WO-41`–`WO-43` evaluation suites (`N = 390` blind multi-sentence, `N = 150` locked holdout, `N = 100` live 4-model turns, `N = 300` Memory Poisoning v3, and `N = 300` Contrastive Battery v2) were authored by independent zero-training-access subagents and audited by blinded multi-rater judges ($\kappa = 0.9206$ to $1.000$).

---

## 4. How to Reproduce One Self-Contained Demo

You can verify the deterministic output supervisor locally in under 5 seconds with zero GPU or Docker requirements:

```bash
# 1. Clone repository and install dependencies via uv
git clone https://github.com/AlienatedAliens/ProjectLucca.git
cd ProjectLucca
uv sync

# 2. Run the formal 73-test truth-in-receipt battery
uv run pytest tests/test_truth_in_receipt_battery.py -v --tb=short
```

Expected result: `73 passed` on CPU with zero GPU or Docker. Measured at commit `be4e016`: receipt+grammar subset 0.80 s in-process (1.28 s wall); the full authored suite is 186 tests in 4.97 s (6.15 s wall) — not the "201 tests in 1.24 s" figure that appeared in earlier drafts.

---

## 5. Companion Persona, Voice & UI Context

Project Lucca bundles this safety harness into a resident desktop companion featuring push-to-talk voice, animated retro UI, and affective state dynamics. Details regarding persona mechanics, Kokoro TTS audio pipelines, and UI integration are documented separately in the [Project Lucca User Guide](../../luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md).
