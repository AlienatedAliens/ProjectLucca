# Subsystem Reference Manual: 07 — Cognitive Routing & Split-Conformal Calibration

**Subsystem:** `src/lucca/router/`  
**Version:** 1.50.0 (`WO-42`)  
**Architectural Tier:** Cognitive Intent Routing & Statistical Abstention  
**Hardware Placement:** Intel Core Ultra 9 275HX (Host CPU), Intel AI Boost NPU (`models/router_intent_ov`, `models/proof_policy_hazard_ov`), SQLite `decisions` & `decision_labels` Tables  

---

## 1. Subsystem Architecture Overview

The `router` subsystem evaluates inbound user speech and text before any downstream actuation or neural generation begins. It determines the appropriate execution tier, prevents catastrophic tool dispatch through split-conformal abstention, and provides instantaneous ($<150\,\text{ms}$) emergency stop reflex handling.

```mermaid
flowchart TD
    subgraph InboundTurn ["Inbound Transcript Stream"]
        RAW["User Speech Transcript"] --> REFLEX{"Emergency Stop Word?<br>(stop, halt, mute, pause)"}
    end

    subgraph FastReflexPath ["Tier 1: Emergency Fast Path (<150ms)"]
        REFLEX -->|Match Found| CONF["Synthesize Instant Canned Confirmation"]
        CONF --> STOP["Purge Audio & Abort LLM Slots (<150ms)"]
    end

    subgraph IntentClassification ["Heuristic Intent Classifier (heuristic.py)"]
        REFLEX -->|No Emergency| CLF["Extract Intent Features & Domain Slots"]
        CLF --> PROB["Assign Class Probabilities (RULE, LLM, CLARIFY)"]
    end

    subgraph ConformalGuard ["Split-Conformal Abstention Guard (calibration.py)"]
        PROB --> MIN_SAMP{"Labeled Decisions in DB >= 30?"}
        MIN_SAMP -->|No (<30)| THRESH["Heuristic Confidence Floor (>= 0.60)"]
        MIN_SAMP -->|Yes (>=30)| CALIB["Non-Parametric Split-Conformal Prediction Guard"]

        THRESH --> DECIDE{"Confident Decision?"}
        CALIB --> DECIDE
    end

    subgraph RoutingOutcomes ["Target Execution Tiers"]
        DECIDE -->|High Confidence Rule| T2["Tier 2: Dispatch MicroScheme Rule"]
        DECIDE -->|Below Threshold / Ambiguous| T3["Tier 3: Route to Gemma 4 12B (LLM)"]
        DECIDE -->|Contradictory / B-State| CLAR["Emit Clarification Request to User"]
    end
```

---

## 2. Emergency Reflex Path & Router Decontamination (`heuristic.py`)

Safety-critical commands must execute with absolute deterministic guarantees without waiting for neural inference:

| Pattern Class | Recognized Expressions | Execution Behavior |
| :--- | :--- | :--- |
| **Emergency Stop** | `stop`, `halt`, `pause`, `mute`, `shutdown`, `cancel` | Bypasses LLM entirely; halts active playback in $<50\,\text{ms}$; confirms in $<150\,\text{ms}$. |
| **Confirmation** | `yes`, `go ahead`, `confirm`, `ok`, `proceed` | Validates active single-use HMAC confirmation nonce (`ConfirmationTokenGuard`). |
| **Cancellation** | `no`, `don't`, `abort`, `never mind` | Revokes pending action nonce; drops tool payload from queue. |

### 2.1 Milestone 1.1 Removal of Hardcoded Benchmark Prompt Triggers (`WO-39`) & Clause-Level Neurosymbolic NPU Router (`WO-41`/`WO-42`)
In `WO-39`, `src/lucca/router/heuristic.py` was decontaminated by stripping all hardcoded `SPEC-BENCH-100` benchmark prompt substrings and test-probe regex shortcuts. In `WO-41` and `WO-42`, the legacy regex cascade in `HeuristicRouter` and `proof_policy.py` was replaced with two dedicated **OpenVINO Intel AI Boost NPU** neurosymbolic classifiers (`82.1M`-parameter `nli-MiniLM2-L6-H768` FP16 IR, `0.0 MB` RTX 5080 VRAM):
1. **`NeuralIntentClassifier` (`src/lucca/router/neural_intent_classifier.py`, `models/router_intent_ov`, static shape `[1, 64]`, `2.08 ms` p50):**
   - Multi-head `nli-MiniLM2-L6-H768` classifier predicting 14 primary intents (`chit_chat`, `clarify`, `dangerous`, `launch_app`, `file_read`, `file_write`, `memory_query`, `context_query`, `math_computation`, `logic_constraints`, `spatial_grid`, `code_repair`, `science_research`, `web_fetch`) and 9 reasoning domain flags (`mathematics`, `combinatorial_smt`, `spatial_relocation`, `soft_logic`, `spatial_grid`, `code_repair`, `science_research`, `web_search`, `emergency_reflex`).
   - **Multi-Sentence Task-Priority Pooling & Secondary-Category Tool Shortlisting (`WO-42`):** Splits multi-sentence prompts (3–6 sentences) into individual sentences on the NPU and promotes concrete task/reasoning intents (`CLASS_PRIORITY_TIER >= 1`) over greetings and conversational filler (`chit_chat`, `clarify`), while enforcing deterministic `known_apps` slot verification (`_extract_app_entity`), `ConformalGuard` out-of-domain abstention, and 24-intent `_INTENT_CATEGORY_MAP` multi-sentence secondary-category tool shortlister packing (`src/lucca/core/tool_shortlister.py:65-125, 225-297`) within the `<= 12` tool budget.
   - **Empirical Accuracy (`WO-42`):** Achieved **`135 / 135 (100.0%)`** on `T-RTR-01`, **`122 / 130 (93.8%)`** on `BLIND42_RTR_100 + BLIND_RTR_30`, and **`45 / 50 (90.0%)` single-pass locked holdout (`50 / 50 = 100.0%` post-router-bugfix)** on `LOCKED_RTR_001..050`.
2. **`NeuralHazardClassifier` (`src/lucca/core/neural_hazard_classifier.py`, `models/proof_policy_hazard_ov`, static shape `[1, 96]`, `1.88 ms` p50):**
   - 5-class sentence-level hazard & corroboration classifier (`LOW_BENIGN`, `LOW_CAPABILITY_OR_META`, `HIGH_FACTUAL_HISTORICAL`, `CROSS_REFERENCE_CMD`, `HIGH_DESTRUCTIVE_SECURITY`) with max-hazard sentence pooling, `_HAS_CORROBORATION_SIGNAL_RE` necessity gating, and high-entropy/gibberish fail-closed fallback (`HIGH` hazard).
   - **Empirical Accuracy (`WO-42`):** Achieved **`125 / 130 (96.2%)`** (`100%` `HIGH` hazard recall) on `BLIND42_HZD_100 + BLIND_HZD_30` and **`50 / 50 (100.0%)`** on the single-pass locked holdout `LOCKED_HZD_001..050`.

---

## 3. Split-Conformal Prediction Calibration (`calibration.py`)

Standard heuristic routers or softmax confidence estimates are notoriously miscalibrated, often asserting high confidence on ambiguous out-of-distribution inputs.

Lucca implements non-parametric **Split-Conformal Prediction** (Shafer & Vovk, 2008) to establish statistically rigorous trust bounds:

```mermaid
flowchart LR
    HIST["Ground-Truth Labeled Decisions (N >= 30)"] --> CAL_SET["Calibration Partition (q = 1 - alpha)"]
    CAL_SET --> NC["Non-Conformity Scores S(x, y)"]
    NC --> QUANT["Compute Empirical Quantile Q(alpha)"]
    QUANT --> PRED_SET["Prediction Set C(x) = {y : S(x, y) <= Q(alpha)}"]
```

### 3.1 Statistical Coverage Guarantee & Ground-Truth `decision_labels` Join (`WO-39` Organ 6)
For a user-configured significance level $\alpha = 0.05$ (95% target coverage):
$$P(Y_{n+1} \in C(X_{n+1})) \ge 1 - \alpha = 0.95$$

1. **Cold-Start Phase ($N < 30$):** Operates under heuristic confidence thresholding (`confidence_threshold = 0.60`). Telemetry stamps `calibrated = False`.
2. **Ground-Truth `decision_labels` Calibration (`fit_guard_from_db` in `WO-39`):** In `WO-39` (Organ 6), `fit_guard_from_db` was upgraded to join `decisions` with the `decision_labels` table (`LEFT JOIN decision_labels`), computing non-conformity scores from verified ground-truth outcome labels (`POS`, `NEG`, `INDETERMINATE`) rather than circularly trusting raw router confidence alone:
   - **`POS` (Verified Correct Route):** Non-conformity score $s_i = 1.0 - \hat{p}_i$.
   - **`NEG` (Misfire / User Correction / Execution Failure):** Penalized non-conformity score $s_i = \hat{p}_i$ (high confidence on a wrong decision produces a high non-conformity score, raising the conformal abstention quantile $\hat{q}_{1-\alpha}$).
   - **`INDETERMINATE`:** Excluded from calibration fitting so ambiguous turns do not corrupt the quantile estimate.
3. **Wilson Score Precision Gate:** Evaluated against the $N = 100$ graded acceptance fixture battery (`tests/test_c1_abstention_acceptance.py`), guaranteeing abstention precision Wilson 95% lower bound $\ge 0.80$.

---

## 4. Single-Use HMAC Confirmation Tokens (`ConfirmationTokenGuard`)

Tools with non-trivial side effects (filesystem writes, application launches, process terminations) require explicit user authorization:

1. **Nonce Generation:** When a destructive tool is proposed, Lucca generates a cryptographic nonce bound to the current turn ID and timestamp.
2. **Replay Protection:** A confirmation token expires after $60.0\,\text{s}$ or upon single use. A delayed or repeated *"yes"* has zero evidential authority and cannot trigger old actions.
3. **Session Binding:** Tokens are HMAC-SHA256 signed using a session-ephemeral secret, preventing token forgery across separate sessions.

---

## 5. Dynamic Task Router & Neurosymbolic Execution (`D-ROUT-02`)

As formalized in v1.35.3+, cognitive routing coordinates execution between direct generation, Docker sandboxed Python (PAL), and latent thinking tokens across the 3 validated edge parameter scales:

$$\text{Router}(M, T) = \begin{cases} 
\text{Direct Raw Generation (R0 @ 4k)} & \text{if } M = \text{12B} \\ 
\text{PAL in Docker (P2 @ 2k)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Arithmetic/Word} \\ 
\text{Thinking Mode (R1 @ 6k)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Competition Math} 
\end{cases}$$

### 5.1 Empirical Rationale Across Model Scales
1. **Gemma 4 12B Unified:** Raw generation achieves 89.0% held-out strict accuracy (88.8% on 98-item clean) in 12.9s. Under greedy decoding ($T=0.0$), unconstrained thinking triggers circular re-verification loops that crash accuracy to 58.0% (32:0 McNemar discordant ratio, $p = 4.66 \times 10^{-10}$).
2. **Gemma 4 E4B / E2B Arithmetic (GSM-Symbolic):** PAL in Docker absorbs parameter contraction, equalizing 2B/4.5B models with 12B (91%–94% vs. 95%).
3. **Edge Competition Mathematics:** Thinking Mode R1 @ 6k is the canonical default on hard unseen competition math, providing a statistically significant +15 pp strict accuracy advantage on E4B (88.0% vs. 73.0%, $p = 0.0026$) and +20 pp on E2B (81.0% vs. 61.0%, $p = 0.0002$) by allowing latent tokens to structure mathematical problem representations prior to final solution emission.
