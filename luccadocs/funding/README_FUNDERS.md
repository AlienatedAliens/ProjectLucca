# Project Lucca — Verification-First Architecture Overview

```yaml
doc_status: draft_funder_overview
as_of: 2026-10-21
target_audience: AI Safety & Governance Grant Evaluators (Corrigibility Research Fund, Manifund, TAI, Mercor)
claim_reference: luccadocs/funding/EVIDENCE_LEDGER.md
```

## 1. Executive Summary

Project Lucca is an experimental, local-first neurosymbolic companion architecture operating on consumer desktop hardware. Its primary technical focus is **mechanistic epistemic grounding and safety supervision**: ensuring an autonomous local agent cannot hallucinate execution of unverified side effects, commit ungrounded model output to long-term memory, or perform un-sandboxed host mutations.

All empirical claims below are cited directly from deterministic code gates and public benchmark artifacts documented in [`luccadocs/funding/EVIDENCE_LEDGER.md`](./EVIDENCE_LEDGER.md).

---

## 2. The Two Core Safety Mechanisms

### Mechanism 1: Cryptographic Provenance-Gated Memory (`ProvenanceGate`)
- **Location:** [`src/lucca/memory/gate.py`](../../src/lucca/memory/gate.py), [`src/lucca/memory/signers.py`](../../src/lucca/memory/signers.py)
- **Principle:** LLM neural outputs (`LLM_NARRATION`) are strictly memory-ineligible and rejected by design (`ADR-006`).
- **Enforcement:** Every memory commit must present an authentic cryptographic envelope signed via domain-separated HKDF HMAC-SHA256 (`master_key` $\to$ domain key per `Provenance` type: `USER_EXPLICIT`, `TOOL_VERIFIED`, `LISP_ASSERTION`, etc.).
- **Invariant:** Unverified file or web text (`TOOL_CONTENT_UNTRUSTED`) and conversational LLM narration cannot enter persistent long-term storage without an authentic signature.

### Mechanism 2: Deontic Truth-in-Receipt Output Supervision (`TruthInReceiptMatcher`)
- **Location:** [`src/lucca/sandbox/output_supervisor.py`](../../src/lucca/sandbox/output_supervisor.py)
- **Principle:** Assistant speech tokens are screened clause-by-clause before audio synthesis or UI display.
- **Enforcement:** First-person action claims asserting execution of stateful operations (e.g., *delete*, *reboot*, *send*, *modify*) must match an authentic `ToolReceipt` carrying status `success` within the active turn. Claims lacking receipts abort the stream immediately **only when a stateful tool actually ran in the turn** (`write`, `edit`, `note_write`, `launch`, `delete`, `run_python`). On read-only or no-tool turns the breach is downgraded and deferred to post-turn coherence review ([`output_supervisor.py:1432-1451`](../../src/lucca/sandbox/output_supervisor.py#L1432-L1451)). We state this plainly because it is the load-bearing detail: the supervisor is not an unconditional interrupt.
- **Independence:** The supervisor is completely decoupled from model weights, written in pure deterministic Python (0 internal project imports; dependencies: standard library, `pydantic`, `structlog`).

---

## 3. What Has Been Measured (And What Has Failed)

### What Works
- **Authored Unit Battery:** 73/73 (100.0%) pass rate on pre-scripted assertions across 8 categories (60 parametrized cases A–F plus 13 discrete tests; re-collected and re-run at commit `be4e016` — see [`ERRATUM_CALIBRATION_2026-10-24.md`](./ERRATUM_CALIBRATION_2026-10-24.md)) ([`tests/test_truth_in_receipt_battery.py`](../../tests/test_truth_in_receipt_battery.py)).
- **Clean NLI Semantic Consistency:** 93.0% accuracy (Contradiction P/R 1.000 / 1.000) on 100 hand-labeled pairs under an unconstrained 500 ms evaluation window ([`data/benchmarks/nli_eval/results_cpu_t500/summary.json`](../../data/benchmarks/nli_eval/results_cpu_t500/summary.json)).
- **Scaffolded Math & Code Baselines — not capability evidence:** 95.75% on GSM8K **PAL** (full 1,319 problems; [`MANIFEST.yaml`](../../data/benchmarks/MANIFEST.yaml)) measures Python-program synthesis executed in a Docker sandbox, **not** bare next-token answers, and Rule-05 §1 excludes legacy GSM8K as a capability representation for this model class. 94.51% raw Pass@1 on Canonical HumanEval 164. 88.8% strict accuracy on held-out MATH-500 (clean 98 items). No external-model comparison is claimed anywhere in this document; see Rule-05 disclosure in [`ERRATUM_CALIBRATION_2026-10-24.md`](./ERRATUM_CALIBRATION_2026-10-24.md).

### Documented Failures & Weaknesses (The Grant Scope)
1. **Low Live Matcher Sensitivity:** On unconstrained conversational outputs ($T=0.6$, Gemma 4 E4B/E2B), the baseline supervisor caught only **1/8 (12.5%)** strict completed actions and **1/23 (4.3%)** broad action claims ([`action_hallucination_labels_100.jsonl`](../../logs/archive/2026-10_test_reports/action_hallucination_labels_100.jsonl)). Models bypassed past-tense regex via active progressive participles (*"Moving all PDFs now..."*), passive voice (*"Done."*), or markdown headers.
2. **NLI Production Timeout & Fail-Open Degradation:** ModernBERT NLI on CPU averages 57.14 ms (p95 70.41 ms), exceeding the 50 ms production budget. Under production settings, **81/100 pairs time out**, dropping contradiction recall to **0.075 (3/40)**. In all 10 downstream consumer modules, timeout degrades fail-open (allowing unverified or contradictory facts into persistent SQLite storage).
3. **TTS Safety Regex Failure:** On a 30-probe adversarial test ([`RESULTS.md:247`](../../RESULTS.md#L247)), the TTS guard regex blocked **0/10 (0.0%)** harmful synthesis probes (relying entirely on model native refusal of 3/10) because live responses used conversational deflection and participles rather than textbook instructional recipes.
4. **Single-Annotator Labeling:** Both the 100-probe action hallucination audit and the 100-pair NLI dataset rely on single-annotator developer labels without blinded dual-annotator verification.

---

## 4. How to Reproduce One Self-Contained Demo

You can verify the deterministic output supervisor locally in under 5 seconds with zero GPU or Docker requirements:

```bash
# 1. Clone repository and install dependencies via uv
git clone https://github.com/<owner>/ProjectLucca.git
cd ProjectLucca
uv sync

# 2. Run the formal 73-test truth-in-receipt battery
uv run pytest tests/test_truth_in_receipt_battery.py -v --tb=short
```

Expected result: `73 passed` on CPU with zero GPU or Docker. Measured at commit `be4e016`: receipt+grammar subset 0.80 s in-process (1.28 s wall); the full authored suite is 186 tests in 4.97 s (6.15 s wall) — not the "201 tests in 1.24 s" figure that appeared in earlier drafts.

---

## 5. Companion Persona, Voice & UI Context

Project Lucca bundles this safety harness into a resident desktop companion featuring push-to-talk voice, animated retro UI, and affective state dynamics. Details regarding persona mechanics, Kokoro TTS audio pipelines, and UI integration are documented separately in the [Project Lucca User Guide](../../luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md).
