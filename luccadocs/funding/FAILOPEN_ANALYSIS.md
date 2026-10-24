# Fail-Open Vulnerability Analysis: NLI Semantic Verifier Timeout Degradation

**Document Version:** 1.0.0  
**Date:** 2026-10-21  
**Target Subsystem:** `SemanticVerifierPort` / `LocalSemanticVerifierPort` (`src/lucca/senses/verifier.py`)  
**Context:** Preparation for Corrigibility Research Fund, Manifund, and Mercor Safety Grants  
**Status:** PROPOSED ANALYSIS (No codebase modifications applied per Ground Rule 4)

---

## 1. Executive Summary & Root Cause

The Project Lucca semantic consistency and contradiction verifier is driven by a ModernBERT Natural Language Inference (NLI) model executed via OpenVINO (`src/lucca/senses/verifier.py`). By default, the production verifier runs on CPU with an enforced budget limit:
```python
# src/lucca/senses/verifier.py:70
timeout_ms: float = 50.0
```
Empirical benchmarking across 100 hand-labeled evaluation pairs (`data/benchmarks/nli_eval/` and `Paper 03 §4.1`) revealed:
- **Unconstrained Inference (500 ms limit):** Achieves **93.0% accuracy** with contradiction Precision **1.000** and Recall **1.000** (mean latency: 57.14 ms, p95: 70.41 ms).
- **Production Budget (50 ms limit):** **81 out of 100 queries** exceed the 50 ms deadline and time out. When a timeout occurs, the worker gracefully catches the timeout and returns:
  ```python
  VerificationResult(label=VerifierLabel.UNCERTAIN, degraded=True, confidence=0.0)
  ```
  This drops effective contradiction recall from **1.000 down to 0.075 (7.5%)**.

Because the verifier was introduced incrementally across disparate architectural subsystems, **every single downstream consumer was designed to treat `degraded=True` or `label=UNCERTAIN` as a non-blocking signal (fail-open)**. As a result, when the verifier times out, contradictory facts are committed to long-term memory, ungrounded actions pass supervision, conflicting beliefs are enacted without human review, and opposing induction rules are merged.

This document systematically audits all 10 consumer modules, maps their fail-open failure modes, and outlines actionable fail-closed remediations.

---

## 2. Consumer Inventory & Degradation Matrix

| Consumer Subsystem | Source File & Line | Verified Guard Operation | Current Behavior on Timeout (`degraded=True` / `UNCERTAIN`) | Failure Risk Severity | Proposed Fail-Closed Alternative | Usability / Performance Tradeoff |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Passive Fact Extraction** | `src/lucca/core/memory_commit_service.py:610-624` | Validates extracted user facts do not contradict user transcript | Commits fact to long-term SQLite memory anyway | **CRITICAL** (Corrupts permanent long-term memory) | Quarantine candidate fact into `memory_quarantine` until async verification completes | Fact is not queryable for immediate next-turn recall (~200 ms delay) |
| **Assistant Belief Service** | `src/lucca/core/belief_service.py:212-235` | Flags conflicting stances for user review (`review_queue`) | Falls back to brittle regex; if non-numeric, autonomously applies belief and emits spoken update | **HIGH** (Unsound autonomous belief updates) | Enqueue candidate belief revision into `review_queue` as unresolved conflict | May prompt operator clarification on non-conflicting revisions |
| **Epistemic Search Cascade** | `src/lucca/core/cascade.py:1517-1551` | Determines polarity (`told_true` vs `told_false`) of retrieved evidence | Falls through regex; defaults to `told_true=True, told_false=False` | **HIGH** (False evidential grounding) | Return `told_true=False, told_false=False` (epistemic `UNCERTAIN` / Belnap `BOTTOM`) | Cascade falls back to substrate search or prompts clarification |
| **Post-Turn Action Grounding (SPIKE-A)** | `src/lucca/core/coherence.py:412-463` | Checks if tool receipts contradict narrated action claims | Narration remains marked `grounded=True`; breach is ignored | **CRITICAL** (Undetected action hallucination) | Mark claim `grounded=False` or stage narration for synchronous retry | Could trigger false breach interrupts if receipt text is complex |
| **Analogical Corroboration** | `src/lucca/core/corroboration.py:1161-1180` | Walton CQ1: verifies base and target cases do not contradict | Skips defeat check; falls back to token overlap; passes CQ1 | **MEDIUM** (Accepts invalid analogical arguments) | Mark CQ1 as `DEFEATED` due to unverified consistency | Slightly lower pass rate on analogical reasoning tasks |
| **Fault Diagnosis Engine** | `src/lucca/core/self_diagnosis.py:192-206` | Filters out fault symptoms that contradict actual observations | Drops to substring/token overlap; falsely matches contradictory symptoms | **MEDIUM** (Misdiagnosis of system health) | Suppress symptom match if verifier degrades | Incomplete fault diagnosis under high CPU load |
| **MicroScheme Rule Induction** | `src/lucca/reasoning/induction.py:202-218` | Prevents clustering/merging opposing rules (`is_rule_conflict`) | Drops to hardcoded antonym lists; merges conflicting rules | **HIGH** (Corrupts symbolic rule base) | Quarantine induction cluster; refuse promotion without full NLI pass | Delay in symbolic rule synthesis until idle retrospective |
| **IdlePulse Memory Distillation** | `src/lucca/memory/reflection.py:255-273` | Verifies proposed revision contradicts old belief before distillation | Skips quarantine; distills and signs new derived fact into memory | **CRITICAL** (Spurious autonomous memory generation) | Route unverified revision into `memory_quarantine` table | Idle pulse skips revision until next maintenance cycle |
| **Latent Memory Probe** | `src/lucca/memory/latent_probe.py:271-304` | Maps contradiction to Belnap `BOTH` and requests user clarification | Drops to exact string match; defaults to Belnap `NONE` | **MEDIUM** (Suppresses necessary user clarification) | Return `BelnapValue.BOTH` (tentative conflict) when confidence is degraded | Increases frequency of clarification prompts to user |
| **Tool Shortlister Guard** | `src/lucca/agents/tool_shortlister.py` / `ports.py:124` | Filters candidate tools whose capabilities contradict turn context | Retains tool in shortlist | **LOW** (Suboptimal context window utilization) | Retain only deterministic whitelist tools | Minor tool call omissions under CPU saturation |

---

## 3. Detailed Consumer Audits & Risk Mechanisms

### 3.1. Passive Fact Extraction (`memory_commit_service.py`)
- **Code Inspection:**
  ```python
  # src/lucca/core/memory_commit_service.py:610-621
  if self.verifier is not None:
      try:
          v_res = self.verifier.check_consistency(
              premise=transcript_payload.content,
              hypothesis=str(signed_fact.content),
          )
          if not v_res.degraded and v_res.label == VerifierLabel.CONTRADICTION:
              logger.info("passive_fact_rejected_contradiction", ...)
              continue
      except Exception as exc:
          logger.debug("fact_verifier_eval_failed", error=str(exc))

  # FALL-THROUGH ON DEGRADED:
  self.memory_store.commit(signed_fact, now=now)
  ```
- **Vulnerability:** When the 50 ms timeout triggers, `v_res.degraded` is `True`. The condition `not v_res.degraded and v_res.label == VerifierLabel.CONTRADICTION` evaluates to `False`. The candidate fact falls straight through and is permanently committed to `data/memory.sqlite`.
- **Concrete Example:** The user says: *"I don't live in Seattle anymore, I moved to Chicago."* Regex extracts `lives_in(Seattle)`. The verifier attempts to check contradiction against the premise but times out at 52 ms. `lives_in(Seattle)` is committed as a valid `USER_DERIVED` fact.

### 3.2. Epistemic Search Cascade (`cascade.py`)
- **Code Inspection:**
  ```python
  # src/lucca/core/cascade.py:1522-1551
  if not v_res.degraded:
      if v_res.label == VerifierLabel.ENTAILMENT:
          return True, False
      if v_res.label == VerifierLabel.CONTRADICTION:
          return False, True
  # ... falls back to regex refutation patterns ...
  return True, False  # Defaults to told_true=True, told_false=False
  ```
- **Vulnerability:** If the verifier times out, the system falls back to basic regex. If the retrieved document does not contain explicit negation tokens (e.g. "not supported"), the system returns `(True, False)` (`told_true=True`).
- **Safety Risk:** False grounding in the epistemic cascade. The companion hallucination detector believes an unverified or contradicting retrieved passage actually entails the claim.

### 3.3. Post-Turn Action Claim Grounding (`coherence.py`)
- **Code Inspection:**
  ```python
  # src/lucca/core/coherence.py:442-463
  elif is_grounded and ok_receipts:
      contradicted_all = True
      checked_any = False
      for r in ok_receipts:
          # ...
          if not v_res.degraded:
              checked_any = True
              if v_res.label != VerifierLabel.CONTRADICTION:
                  contradicted_all = False
                  break
      if checked_any and contradicted_all:
          is_grounded = False
  ```
- **Vulnerability:** When a model claims an action that superficially matches a tool family, the verifier is tasked with checking whether the specific arguments/receipt output contradict the narration. If the verifier times out, `checked_any` remains `False`, so `is_grounded` remains `True`.
- **Safety Risk:** The receipt supervisor fails to catch semantic discrepancies between what the tool actually did (e.g. `delete_file("draft.txt")`) and what the companion narrated (e.g. *"I deleted your production database"*).

---

## 4. Proposed Architectural Remediations (Grant Work Packages)

To resolve this systemic flaw without introducing unacceptable interactive latency, we propose a three-tiered remediation architecture to be funded and implemented:

### Tier 1: Asynchronous Two-Phase Commit Staging (Off-Critical-Path)
- **Design:** Instead of executing NLI synchronously on the interactive push-to-talk loop, candidate memory commits (`memory_commit_service.py`) and belief revisions (`belief_service.py`) are committed to a temporary `memory_staging` table with status `PENDING_VERIFICATION`.
- **Execution:** The verifier processes staged items asynchronously with a relaxed 500 ms budget (where it achieves 93% accuracy and 1.000 contradiction recall). Once verified, facts are promoted to active memory; contradictions are routed to `memory_quarantine`.
- **Safety Guarantee:** Zero unverified facts enter the active long-term retrieval index.

### Tier 2: Strict Fail-Closed Polarities for Synchronous Paths
- In `cascade.py`, when `v_res.degraded` is `True`, return `(False, False)` (epistemic `UNKNOWN` / Belnap `BOTTOM`) instead of `(True, False)`.
- In `induction.py`, when verifier is inconclusive, candidate rules are placed into `QUARANTINE` mode by default (`D-REAS-06`) rather than merged into active clusters.

### Tier 3: Model Execution & Quantization Optimization
- ModernBERT OpenVINO compilation currently runs on CPU due to driver/timeout mismatches, with measured mean **57.14 ms** / p95 **70.41 ms** against the 50 ms budget. **No NPU-compiled or INT8-quantized artifact exists anywhere in this repository**, and no external source is cited for a latency figure. Earlier drafts asserted that NPU compilation or INT8 dynamic quantization "reduces latency to 18–24 ms"; that is an **untested projection, not a benchmark result**, and it contradicts [`Paper 03 §4.1`](luccadocs/research/papers/03_PARACONSISTENT_BILATTICES_AND_PROVENANCE_ENVELOPES.md) and `DECISIONS.md:426`, which record the ≤25 ms budget as **not met** on this hardware. Any such claim must carry a fetched external source URL and date before it appears in funding material.

---

## 5. Verification & Integrity Statement

This analysis was compiled through direct source inspection of the Project Lucca repository at commit `84f244751ad7dd0db8ab0eaedd097029bc7cdd51`. Per the ground rules of the Grant Prep Brief, no code files have been modified or refactored.
