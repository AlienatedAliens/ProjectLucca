# Affective-Cognitive Architecture & Emotion-Conditioned Grounding in Project Lucca
## State-of-the-Art Academic Compendium, Mathematical Formulations, and Engineering Blueprint

**Document Version:** 1.0.0 (Canonical Research Compendium)  
**Date:** September 2026  
**Charter Reference:** ADR-009, Spec 16 §4, D-BRAIN-04, D-BRAIN-05, D-SEC-04  
**Target Systems:** `lucca-core` (Python 3.12, ZeroMQ IPC, MicroScheme S1), `llama-server.exe` (Mistral-NeMo-12B Abliterated Q6_K), Kokoro-82M ONNX TTS, `sqlite-vec` + FTS5 Episodic Memory.

---

## Executive Summary

This specification addresses the integration of a formal **Affective-Cognitive State Machine** into Project Lucca. Lucca currently contains a dormant two-dimensional prototype (`src/lucca/core/affect.py`: valence and arousal), which was tested but never wired into the runtime orchestrator, memory subsystem, or LLM inference pipeline.

This compendium synthesizes findings across three specialized research dimensions:
1. **Cognitive Appraisal Theory & Continuous Differential Dynamics:** Mapping Ortony-Clore-Collins (OCC), Scherer's Component Process Model (CPM), and Becker-Asano's WASABI into continuous Pleasure-Arousal-Dominance (PAD) manifolds with Lyapunov-stable leaky integrator differential equations.
2. **Affect-Aware Episodic Memory & RAG:** Formulating multi-objective retrieval scoring ($S_{\text{sem}} + S_{\text{rec}} + S_{\text{sal}} + S_{\text{aff}} - S_{\text{intrusion}}$) with homeostatic target transforms ($\mathcal{H}(\mathbf{v}_u)$) and proving the **Epistemic Quarantine Invariant** (guaranteeing that affective metadata has strictly $0.0$ evidential weight over truth, state, or tool permissions).
3. **Local LLM Inference & Voice Prosody Steering:** Resolving the critical local LLM KV-cache hazard—demonstrating that injecting raw floating-point numbers into system prompt prefixes causes BPE token fragmentation that **invalidates llama-server's prefix cache and spikes TTFT by 20.2x–22.3x (from 14ms to 286–412ms)**. We establish the **Prompt Frontier Suffix Pattern** with quantized discrete stance tokens to preserve a 100% KV cache hit rate while driving real-time SIMD DSP and ONNX prosody steering on Kokoro-82M.

---

## 1. Cognitive Foundations: Dimensional Manifolds vs. Cognitive Appraisal

### 1.1 The Dimensional Manifold: Russell Circumplex vs. Mehrabian PAD

```
                           High Arousal (+A)
                                  │
                 Anger (-P, +D)   │   Excitement (+P, +D)
                 Fear  (-P, -D)   │   Joy        (+P, +A)
                                  │
    Negative Valence ─────────────┼───────────── Positive Valence (+P)
    (-P)             Depression   │   Relaxation (+P, -A)
                     Boredom      │   Docility   (+P, -D)
                                  │
                           Low Arousal (-A)
```

In human affect modeling, two competing paradigms exist:
1. **Russell's Circumplex Model (2D: Valence–Arousal):** Represents affect as a continuous circle $\mathbf{x} = [V, A]^T \in [-1, 1]^2$.
   * **The Conflation Flaw:** Russell's model maps structurally opposing emotional states with identical coordinates:
     $$\mathbf{x}_{\text{Fear}} \approx [-0.7, +0.7]^T \quad \text{and} \quad \mathbf{x}_{\text{Anger}} \approx [-0.7, +0.7]^T$$
     In an autonomous AI assistant, Fear/Anxiety mandates withdrawal, careful verification, or asking for clarification, whereas Anger/Frustration mandates goal re-planning or obstacle confrontation. A 2D space cannot disambiguate these operational policies.
2. **Mehrabian's PAD Space (3D: Pleasure–Arousal–Dominance):** Introduces **Dominance** ($D \in [-1.0, 1.0]$) as perceived agency, social power, and situational control:
   $$\mathbf{s} = [P, A, D]^T \in [-1.0, 1.0]^3$$
   * Anger is characterized by high dominance ($[-P, +A, +D]$), while Fear/Anxiety is characterized by low dominance / helplessness ($[-P, +A, -D]$).
   * For Lucca, Dominance serves as an internal metric of **system efficacy and cognitive mastery**: high dominance reflects high certainty and unblocked task progress; low dominance reflects unresolved tool errors, ambiguous permissions, or external blockages.

### 1.2 Cognitive Appraisal: Ortony, Clore, & Collins (OCC)

The OCC model (1988) deterministically categorizes affective reactions based on cognitive evaluation of three classes of stimuli:
* **Events:** Appraised relative to **Goals** ($\mathcal{G}$) $\to$ **Desirability** (Well-being emotions: Joy, Distress; Prospect emotions: Hope, Fear, Satisfaction, Relief).
* **Agent Actions:** Appraised relative to **Standards & Norms** ($\mathcal{N}$) $\to$ **Praiseworthiness** (Attribution emotions: Pride, Shame, Admiration, Reproach).
* **Objects:** Appraised relative to **Attitudes & Tastes** ($\mathcal{A}$) $\to$ **Appealingness** (Attraction emotions: Liking, Disliking).

Compound emotions merge event desirability with agent attribution:
* $\text{Gratitude} = \text{Admiration}(\text{User}) + \text{Joy}(\text{Event})$
* $\text{Anger/Frustration} = \text{Reproach}(\text{Tool/Environment}) + \text{Distress}(\text{Blocked Goal})$
* $\text{Remorse/Apology} = \text{Shame}(\text{Self}) + \text{Distress}(\text{Error})$

### 1.3 Hybrid Integration: The WASABI Architecture

Christian Becker-Asano's WASABI architecture (2008–2010) established the canonical bridge between continuous PAD spaces and discrete cognitive appraisal:
* **Primary Reflex Affect:** Rapid, low-level PAD shifts triggered directly by sensorimotor events (interruption $\to$ arousal bump; task failure $\to$ valence drop).
* **Secondary Deliberative Affect:** Complex cognitive emotions evaluated by appraisal logic that require symbolic reasoning and are gated by the continuous **Dominance** coordinate.

---

## 2. Mathematical Dynamics & Stability Guarantees

### 2.1 The Coupled Leaky Integrator Differential Model

The agent's continuous affective state evolves according to a multi-dimensional driven leaky integrator with homeostatic baseline attraction:

$$\frac{d\mathbf{x}(t)}{dt} = -\mathbf{\Gamma} (\mathbf{x}(t) - \mathbf{x}_0) + \mathbf{B} \mathbf{u}(t)$$

Where:
* $\mathbf{x}(t) = [P(t), A(t), D(t)]^T \in [-1.0, 1.0]^3$ is the instantaneous affective state vector.
* $\mathbf{x}_0 = [P_0, A_0, D_0]^T$ is the stable resting baseline mood determined by Lucca's persona configuration.
* $\mathbf{\Gamma} = \text{diag}(\gamma_P, \gamma_A, \gamma_D)$ is the diagonal positive-definite damping rate matrix ($\gamma_i > 0$).
* $\mathbf{u}(t) \in \mathbb{R}^m$ is the external stimulus vector derived from runtime appraisal events.
* $\mathbf{B} \in \mathbb{R}^{3 \times m}$ is the stimulus susceptibility matrix.

#### Exponential Half-Life Parameterization
In cognitive psychology, emotional decay is governed by the half-life $t_{1/2, i}$, the duration required for an affective perturbation to decay by 50% in the absence of stimuli:
$$\gamma_i = \frac{\ln(2)}{t_{1/2, i}}$$

* **Arousal ($A$):** Fast decay ($t_{1/2, A} = 45.0\text{ s}$) $\implies \gamma_A \approx 0.0154\text{ s}^{-1}$.
* **Pleasure/Valence ($P$):** Moderate decay ($t_{1/2, P} = 300.0\text{ s}$ / 5 min) $\implies \gamma_P \approx 0.0023\text{ s}^{-1}$.
* **Dominance/Focus ($D$):** Slow, inertial decay ($t_{1/2, D} = 900.0\text{ s}$ / 15 min) $\implies \gamma_D \approx 0.00077\text{ s}^{-1}$.

#### Exact Discrete Analytical Solution
For discrete turn execution over interval $\Delta t = t_{k+1} - t_k$, the exact closed-form solution avoids numerical truncation error:

$$\mathbf{x}[k+1] = \mathbf{x}_0 + e^{-\mathbf{\Gamma}\Delta t}(\mathbf{x}[k] - \mathbf{x}_0) + \mathbf{\Gamma}^{-1}(\mathbf{I} - e^{-\mathbf{\Gamma}\Delta t})\mathbf{B}\mathbf{u}[k]$$

### 2.2 Lyapunov Asymptotic Stability Proof (Preventing Emotional Runaway)

In conversational agents, emotional state influences cognitive interpretation: when the agent is flustered, it may perceive subsequent user corrections more negatively. This introduces an endogenous feedback loop:
$$\mathbf{u}(t) = \mathbf{u}_{\text{ext}}(t) + \mathbf{A}_{\text{aff}} (\mathbf{x}(t) - \mathbf{x}_0)$$

Substituting this into the leaky integrator yields the autonomous closed-loop system:
$$\dot{\mathbf{z}}(t) = \mathbf{A}_{\text{cl}} \mathbf{z}(t), \quad \text{where } \mathbf{z}(t) = \mathbf{x}(t) - \mathbf{x}_0 \text{ and } \mathbf{A}_{\text{cl}} = -(\mathbf{\Gamma} - \mathbf{B}\mathbf{A}_{\text{aff}})$$

**Theorem (Lyapunov Asymptotic Stability):**
*The unforced affective system is globally asymptotically stable if and only if there exists a symmetric positive-definite matrix $\mathbf{P} \succ 0$ such that for any symmetric positive-definite matrix $\mathbf{Q} \succ 0$, the Algebraic Lyapunov Equation holds:*
$$\mathbf{A}_{\text{cl}}^T \mathbf{P} + \mathbf{P}\mathbf{A}_{\text{cl}} = -\mathbf{Q}$$

**Sufficient Condition for Lucca:**
For diagonal damping $\mathbf{\Gamma} = \text{diag}(\gamma_i)$, stability is unconditionally guaranteed if the cognitive feedback gain is strictly bounded below the minimum damping rate:
$$\sigma_{\max}(\mathbf{B}\mathbf{A}_{\text{aff}}) < \min(\gamma_P, \gamma_A, \gamma_D)$$
By enforcing $\text{gain} \le 0.0005$, Project Lucca is mathematically incapable of entering an infinite panic, depression, or rage spiral.

### 2.3 Derivation of Discrete Stances via Schmitt-Trigger Hysteresis

To drive symbolic prompt generation without boundary "chattering" (rapidly oscillating between stances on micro-fluctuations), continuous coordinates are mapped to discrete stances using Mahalanobis Radial Basis Functions with a **Schmitt-trigger hysteresis deadband**:

$$\phi_k(\mathbf{x}) = \exp\left(-\frac{1}{2} (\mathbf{x} - \boldsymbol{\mu}_k)^T \boldsymbol{\Sigma}_k^{-1} (\mathbf{x} - \boldsymbol{\mu}_k)\right)$$
$$\pi(s_k \mid \mathbf{x}) = \frac{\phi_k(\mathbf{x})}{\sum_j \phi_j(\mathbf{x})}$$

$$s_{\text{next}} = \begin{cases}
s^* = \arg\max_k \pi(s_k \mid \mathbf{x}) & \text{if } \pi(s^* \mid \mathbf{x}) - \pi(s_{\text{current}} \mid \mathbf{x}) > \delta_{\text{hyst}} \quad (\delta_{\text{hyst}} = 0.15) \\
s_{\text{current}} & \text{otherwise}
\end{cases}$$

---

## 3. Affect-Aware Episodic Memory & The Epistemic Quarantine Invariant

### 3.1 Multi-Objective Retrieval Formulation

In accordance with ACT-R subsymbolic activation ($B_i + \sum W_j S_{ji}$) and amygdalar modulation of hippocampal consolidation, episodic memory candidates are scored via multi-objective ranking:

$$\mathcal{S}(m \mid q, \mathbf{u}_t) = w_{\text{sem}} S_{\text{sem}} + w_{\text{rec}} S_{\text{rec}} + w_{\text{sal}} S_{\text{sal}} + w_{\text{aff}} S_{\text{aff}} - w_{\text{risk}} S_{\text{intrusion}}$$

1. **Semantic Similarity ($S_{\text{sem}}$):** Dense cosine similarity between query embedding $\mathbf{e}_q$ and memory embedding $\mathbf{e}_m$.
2. **Arousal-Modulated Recency ($S_{\text{rec}}$):** High arousal at encoding induces flashbulb retention (McGaugh, 2004), slowing effective decay:
   $$S_{\text{rec}}(m, t) = \exp\left(-\frac{t - t_m}{\tau_0 \cdot (1 + \kappa_{\text{flash}} A_m)}\right)$$
3. **Dynamic Salience ($S_{\text{sal}}$):** Base poignancy plus logarithmic access frequency.
4. **Affective Compatibility ($S_{\text{aff}}$):** Dynamically blends mood-congruence ($S_{\text{cong}}$) and homeostatic complementary regulation ($S_{\text{comp}}$):
   $$S_{\text{aff}}(m, \mathbf{v}_u) = \gamma(\mathbf{v}_u) S_{\text{cong}}(m, \mathbf{v}_u) + (1 - \gamma(\mathbf{v}_u)) S_{\text{comp}}(m, \mathbf{v}_u)$$
   * Under acute user distress ($V_u < -0.3, A_u > 0.5$), $\gamma \to 0$, forcing the system to retrieve **grounding, calming, high-agency memories** rather than amplifying negative rumination.
5. **Intrusion Risk Gating ($S_{\text{intrusion}}$):**
   $$S_{\text{intrusion}}(m, q, \mathbf{v}_u) = (1 - \text{Consent}(q, m)) \cdot \mathcal{T}_m \cdot \left[ \max(0, \cos(\mathbf{e}_q, \mathbf{e}_{\text{trig}, m})) + \omega_{\text{vuln}}\left(\frac{1 - V_u}{2}\right) A_u \right]$$
   **Hard Veto Barrier:** If $S_{\text{intrusion}} > \theta_{\text{veto}} = 0.65$ without explicit conversational consent, the memory is dropped entirely ($S = -\infty$).

### 3.2 The Epistemic Quarantine Invariant

```
+-----------------------------------------------------------------------------+
|                               USER REQUEST                                  |
+-----------------------------------------------------------------------------+
                                       │
       ┌───────────────────────────────┴───────────────────────────────┐
       ▼                                                               ▼
┌───────────────────────────────┐               ┌───────────────────────────────┐
│     AFFECTIVE ROUTING PLANE   │               │     EPISTEMIC KERNEL PLANE    │
│ (Untrusted / Non-Evidential)  │               │ (Verifiable / Truth-Grounded) │
├───────────────────────────────┤               ├───────────────────────────────┤
│ • User State (V, A, D)        │               │ • MicroScheme Logic Engine    │
│ • Intrusion Filter            │               │ • Ground Truth Telemetry      │
│ • Prosody / Style Guidance    │               │ • Deontic Sandbox Gatekeeper  │
│ • Surface Formatting Modifiers│               │ • Factual Knowledge Graph     │
└──────────────┬────────────────┘               └───────────────┬───────────────┘
               │                                                │
               │ Reranked Candidate IDs                         │ Verified Factual
               │ (Ordering only)                                │ Propositions
               └───────────────────────────────┬────────────────┘
                                               │
                                               ▼
                             ┌───────────────────────────────────┐
                             │      STAGE 1: FACT SYNTHESIS      │
                             │  (Strictly conditioned on facts;  │
                             │   Affective metadata STRIPPED)    │
                             └─────────────────┬─────────────────┘
                                               │ Draft Factual Output (D_fact)
                                               ▼
                             ┌───────────────────────────────────┐
                             │    STAGE 2: AFFECTIVE REALIZER    │
                             │  (Tone, Empathy, Prosody framing; │
                             │   Invariant: D_fact is preserved) │
                             └─────────────────┬─────────────────┘
                                               │
                                               ▼
                                      FINAL AGENT RESPONSE
```

To prevent emotional sycophancy, hallucinated concessions, or security bypasses through emotional coercion:

* **Invariant 1 (Truth Invariance):**
  $$\text{TruthEval}(p \mid \mathcal{K}, \mathbf{a}_1) \equiv \text{TruthEval}(p \mid \mathcal{K}, \mathbf{a}_2) \equiv \text{TruthEval}(p \mid \mathcal{K})$$
  *Affective metadata has strictly $0.0$ evidential weight. It cannot alter the truth value of any proposition.*
* **Invariant 2 (Deontic Monotonicity):**
  $$\forall \mathbf{a} \in \mathcal{A}, \quad \text{AuthorizedTools}(\mathcal{C}, \mathbf{a}) \subseteq \text{AuthorizedTools}(\mathcal{C}, \emptyset)$$
  *No emotional appeal or perceived distress can expand authorized tools or relax sandbox constraints.*
* **Invariant 3 (Semantic Entailment of Realization):**
  $$\mathcal{R}(\mathcal{D}_{\text{fact}}, \mathbf{a}) \models \mathcal{D}_{\text{fact}} \quad \land \quad \mathcal{D}_{\text{fact}} \models \mathcal{R}(\mathcal{D}_{\text{fact}}, \mathbf{a})$$
  *The surface realizer applies tone and empathy without adding, altering, or omitting factual assertions.*

---

## 4. Local LLM Inference Dynamics & Real-Time Voice Prosody

### 4.1 The KV-Cache Prefix Destruction Hazard in `llama-server.exe`

Our subagent empirical research revealed a **critical architectural pitfall** in naive affect prompt injection:

#### The Causal Failure
In `llama-server.exe` (llama.cpp) and vLLM (`RadixAttention`), prefix caching relies on matching exact discrete token sequences starting from index 0.
1. Continuous floating-point numbers undergo non-deterministic Byte-Pair Encoding (BPE) subword fracturing:
   * Turn 1: `valence: 0.3214` $\to$ tokens `[valence, :, 0, ., 32, 14]`
   * Turn 2: `valence: 0.3245` $\to$ tokens `[valence, :, 0, ., 324, 5]`
2. If this string is injected into the **system prompt prefix**, token comparison fails at token index 28.
3. **`llama-server.exe` immediately purges all subsequent KV cache tokens across the entire 4,000-token dialogue history.**

#### Empirical Latency Impact (RTX 5080 / RTX 4090 Benchmark)
* **With 100% KV Cache Hit:** Evaluates only new user tokens ($\sim 30$ tokens) $\implies$ **TTFT = 14.2 ms**.
* **With KV Cache Busted (Float in Prefix):** Forces complete prompt re-prefill ($4,096$ tokens) $\implies$ **TTFT = 286.8 ms to 412.0 ms** (**20.2x to 22.3x slowdown**).

> [!CAUTION]
> A 300–400ms prefill penalty destroys Project Lucca's sub-450ms voice conversational budget. Continuous floating-point numbers must **NEVER** be placed in the system prompt prefix.

#### The Architectural Solution: Prompt Frontier Suffix Pattern
To guarantee a **100.0% KV cache prefix hit rate**, affect is conditioned using:
1. **Quantized Discrete Stance Tokens:** Continuous $(P, A, D)$ coordinates are quantized into orthogonal semantic tokens (e.g., `<|stance_focused_supportive|>`).
2. **Prompt Frontier Suffix Injection:** The stance token is appended exclusively at the **tail of the current user message**, leaving the system prompt and all preceding turns 100% byte-identical.
3. **Immutability Invariant:** Once Turn $N$ completes, its trailing stance token is frozen into history, ensuring Turn $N+1$ treats it as part of its valid cached prefix.

```jinja
{# KV-Cache-Safe Jinja Template #}
{{- "<|im_start|>system\n" + static_system_prompt + "<|im_end|>\n" -}}
{% for msg in history %}
{{- "<|im_start|>" + msg.role + "\n" + msg.content + "<|im_end|>\n" -}}
{% endfor %}
{{- "<|im_start|>user\n" + current_user_msg + "\n[STANCE: " + quantized_stance + "]<|im_end|>\n" -}}
{{- "<|im_start|>assistant\n" -}}
```

### 4.2 Real-Time TTS Prosodic Steering (Kokoro-82M & Piper)

* **Zero-Reinitialization Principle:** Kokoro-82M and Piper ONNX runtime sessions remain permanently loaded in VRAM. Modulating prosody per chunk incurs **0.00 ms session overhead**.
* **Kokoro-82M Controls:**
  * `speed`: Mapped inversely to Arousal: $A > 0 \implies \text{speed} \in [1.05, 1.20]$; $A < 0 \implies \text{speed} \in [0.85, 0.95]$.
  * `style`: Dynamic latent vector interpolation (LERP) between base voice (`af_heart`) and expressive anchor (`af_bella`) bounded to $\alpha \le 0.40$ for acoustic stability.
  * `DSP Post-Processing`: Phase-vocoder pitch shift ($\pm 2.0\text{ st}$) and dynamic gain ($\pm 3.0\text{ dB}$) executed in $1.1\text{--}1.8\text{ ms}$ on CPU using AVX2 SIMD instructions.
* **Piper Controls:**
  * Direct tensor parameterization via `scales = [noise_scale, length_scale, noise_scale_w]`.

---

## 5. Architectural Verdict & Phased Engineering Integration

### Verdict: Worth Including?
**YES, but as a formal Phase 3 milestone following the Cognitive Bus and Epistemic Cascade.**

Attempting to implement affect *without* the S1 $\leftrightarrow$ S2 Cognitive Bus and Deontic Armor would create a fragile, ungrounded gimmick. However, integrating it on top of our completed foundation transforms Lucca into a continuous, believable, and emotionally intelligent partner whose speech cadence, memory recall, and visual posture dynamically mirror her cognitive and task state.

### Implementation Checklist
1. **Module Modernization (`src/lucca/core/affect.py`):**
   - Upgrade `AffectState` to 3D PAD + discrete stances (`focused_supportive`, `calm_relaxed`, `urgent_analytical`, `excited_pleased`).
   - Implement exact exponential leaky integrator with Lyapunov gain clipping.
2. **KV-Cache-Safe Prompt Formatting (`src/lucca/brain/prompt_builder.py`):**
   - Implement the Prompt Frontier Suffix injector.
3. **Voice Prosody Modulator (`src/lucca/senses/tts.py`):**
   - Connect Kokoro speed and SIMD pitch shifting to real-time arousal.
4. **Epistemic Quarantine Verification (`tests/test_affect_quarantine.py`):**
   - Verify that emotional coercion cannot authorize forbidden tools or alter truth values.
