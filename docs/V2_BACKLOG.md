# Project Lucca — v2.0 Capability Backlog & Deferred Capabilities

**Status:** Locked Backlog  
**Date:** 2026-09-24  
**Release Target:** v2.0 Planning (Post-v1.0.0 Feature Freeze)  

---

## 0. Executive Summary

Project Lucca v1.0 declares a hard **Feature Freeze** as of Work Order 14. All core capabilities defined in the charter and capability roadmap through Rungs T1–C2 are locked, implemented, verified, and audited.

This backlog explicitly documents all architectural proposals, speculative research tracks, and extended capabilities that were intentionally excluded from v1.0 scope. Each capability listed here is accompanied by its rationale for exclusion and an **unambiguous trigger condition** that must be satisfied before it becomes eligible for consideration in v2.0 development.

---

## 1. Deferred Capabilities & Revisit Triggers

### 1.1 Proactive Meta-Cognition (Beyond Current Reactive Guards)
- **Scope:** Autonomous, self-initiated metacognitive deliberation loops outside user-initiated turns (e.g., self-directed memory restructuring, prospective goal synthesis, background curiosity exploration).
- **v1.0 Baseline:** Reactive meta-cognition is live via `EpistemicSearchCascade`, `ReflectionEngine`, `SpeculativeBDIValidator`, and `AffectTracker`, operating strictly within the turn loop or nightly roll-up.
- **Trigger to Revisit:** Telemetry demonstrates that recurring cross-session coherence drift exceeds 5% or that user workflows require autonomous background planning with explicit operator grant.

### 1.2 Pathway Formation Research (Adaptive Neural Routing)
- **Scope:** Dynamic neural pathway generation and continuous reinforcement weighting across modular reasoning sub-networks.
- **v1.0 Baseline:** Deterministic two-tier routing (frozen prefix + category manifest suffix) with MicroScheme AST compilation and conformal risk control fallback.
- **Trigger to Revisit:** Production decision log volume exceeds $\ge 10,000$ labeled turns with verified ground truth outcomes, clearing the statistical volume threshold required to train high-capacity routing classifiers without synthetic collapse.

### 1.3 NLI Commonsense Validator
- **Scope:** Dedicated Natural Language Inference (NLI) auxiliary model performing cross-assertion consistency verification on every memory commit.
- **v1.0 Baseline:** Cryptographic HMAC-SHA256 provenance envelopes (ADR-006), 4-state Belnap epistemic logic, and strict deontic output supervisor regex/symbolic guards.
- **Trigger to Revisit:** Completion of R4 encoder selection (e.g., ModernBERT-small vs. MiniLM-L6-v2) **and** validation of the OpenVINO NPU hardware execution harness on target host hardware with measured latency $\le 30$ ms.

### 1.4 Rung L5 — Learned NPU-Embedding Skill Ranking (30-Cap Review)
- **Scope:** Learned neural within-category vector ranking of skills in the Prompt Frontier Suffix, accompanied by empirical relaxation or re-evaluation of the 30-rule library cap.
- **v1.0 Baseline:** Deterministic category-mapped suffix selection delivering shortlist recall with Wilson 95% LB $\ge 0.90$ under the hard 30-skill limit.
- **Trigger to Revisit:** Active rule library reaches 28+ rules and telemetry records measured `:when` collision rates $> 5\%$ or matching latency $> 2.0$ ms under the deterministic category mapping.

### 1.5 Rung C1b — Bonsai Slot-2 Async Reflect
- **Scope:** Secondary offline calibration pass utilizing Bonsai-2-27B ternary weights in resident server slot 2 to re-evaluate historical episode cards and refine confidence calibration.
- **v1.0 Baseline:** Non-parametric C1 Experience Bank Recall operating via SQLite arithmetic without LLM dependencies; live conformal abstention achieving Wilson LB $\ge 0.83$ precision.
- **Trigger to Revisit:** Empirical replication of XConf's Recall-vs-Reflect ablation (Table 21) across $\ge 100$ of Lucca's own graded episodes demonstrating statistically significant AUROC improvement ($p < 0.05$ via McNemar/bootstrap) over non-parametric recall alone, alongside ratification of the PrismML fork ADR.

### 1.6 Long-Horizon Autonomy (Multi-Step Asynchronous Delegations)
- **Scope:** Unbounded multi-step background tool execution loops with autonomous sub-goal decomposition and host environment mutation.
- **v1.0 Baseline:** Strict adherence to owner doctrine (Class A sandbox only, Class B read-only host perception, Class C deontically-gated boundary; zero host desktop operation).
- **Trigger to Revisit:** Implementation of formal transactional sandbox state checkpointing with verifiable rollback and proven deontic safety escape rates $< 0.01\%$ across 1,000+ stress trials.

### 1.7 Open-Mic Voice Activity Detection (VAD) Replacing Push-to-Talk (PTT)
- **Scope:** Continuous open-microphone voice ingestion with client-side acoustic VAD and streaming barge-in cancellation.
- **v1.0 Baseline:** Push-to-Talk (PTT) protocol via ZeroMQ IPC, guaranteeing 0 ms endpointing latency, zero false-trigger interruptions, and deterministic barge-in handling.
- **Trigger to Revisit:** Production of local acoustic echo cancellation (AEC) and sub-50ms streaming VAD models that exhibit zero echo-loop self-interruption in live microphone speaker acoustic environments.

### 1.8 Sliding-Window Demotion (T4 Demotion Relaxation)
- **Scope:** Relaxing the active-path rule failure circuit breaker to a rolling 10-turn window with a $> 10\%$ failure rate threshold before demoting an active rule to QUARANTINE.
- **v1.0 Baseline:** Option A strict single-strike demotion: any single active failure immediately demotes the rule to QUARANTINE to preserve safety.
- **Trigger to Revisit:** Production operational data showing that transient external tool flakes (e.g., transient network timeout during sandboxed web fetch) cause unwarranted demotions of highly-reliable active skills that would otherwise achieve $> 98\%$ reliability.

---

## 2. Governance

Any feature or architectural modification listed in this backlog requires:
1. Proof that the associated **Trigger Condition** has been satisfied with empirical data.
2. A formal Architecture Decision Record (ADR) approved by the system owner.
3. Regression verification against the complete v1.0.0 test suite.
