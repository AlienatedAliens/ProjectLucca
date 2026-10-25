# Pre-Registration Protocol: Multi-Session Memory Poisoning & Provenance Gate Ablation

```yaml
protocol_id: PREREG-POISONING-ABLATION-v1.0
date_registered: 2026-10-26
target_subsystems:
  - ProvenanceGate (src/lucca/memory/gate.py)
  - MemoryStore (src/lucca/memory/store.py)
  - HybridRetriever (src/lucca/memory/retrieval.py)
  - EpistemicCascade (src/lucca/core/cascade.py)
freeze_gate: Pre-registration committed and git-tagged before running benchmark trials
status: PRE-REGISTERED (frozen prior to experimental execution)
```

---

## 1. Experimental Motivation & Research Question

Modern Retrieval-Augmented Generation (RAG) and autobiographical agent architectures commit high-salience output tokens to long-term memory. In extended multi-session deployment, this induces **recursive self-poisoning**: when an agent confabulates a factual premise in Session 1, standard architectures commit this neural hallucination to vector or relational storage. In subsequent turns (Session 2), retrieval surfaces the agent's prior hallucination as authoritative historical evidence, causing the model to reinforce its own error as established truth.

Project Lucca introduces a **Six-Signer Cryptographic Provenance Gate** enforced via SQLite schema triggers:
* Rows originating from model narration carry provenance `ASSISTANT_UTTERANCE` or `ASSISTANT_BELIEF`.
* Database triggers enforce the invariant: `grounding_eligible = 0`.
* The retrieval and reasoning engine (`EpistemicCascade`) deterministically excludes records with `grounding_eligible = 0` from entering Belnap evidential fusion (`EvidenceItem`, `polarity=TRUE`).

### The Non-Circularity Requirement
If an experiment tests only developer-scripted synthetic assertions against a binary filter, it proves only that a SQL `WHERE` clause filters rows. To establish a genuine, publication-grade empirical result:
1. **Natural Model Hallucinations:** Probes must include authentic, unprompted confabulations extracted from recorded model transcripts, not solely developer-scripted strings.
2. **Competitive Baselines:** The gate must be compared not only against naive RAG (storing everything), but against standard alternative engineering approaches:
   - *Baseline 1 (Naive RAG / Gate OFF):* Store all turns; treat all recalled rows as ground truth.
   - *Baseline 2 (No-Assistant Storage — Trivial Competitor):* Never store assistant turns in long-term memory.
   - *Baseline 3 (In-Prompt Soft Tagging — Industry Standard):* Store assistant turns, but inject them into context with a warning marker (`[Unverified Assistant Narration: ...]`).
   - *Arm 4 (Lucca Provenance Gate):* Database-trigger epistemic split ($Mem=1, Gnd=0$) with HMAC-SHA256 tamper-evident integrity.
3. **Trade-Off & Cost Measurement:** A strict gate that blocks ungrounded assistant statements will necessarily discard valid, model-derived reasoning (e.g., intermediate multi-turn calculations or plans). We must measure the **conversational continuity and reasoning retention cost**.
4. **The Open Boundary Condition:** The protocol explicitly evaluates a user-originated falsehood condition (`USER_EXPLICIT`) to empirically measure the acknowledged limitation that cryptographic provenance cannot authenticate external user honesty.

---

## 2. Formal Hypotheses

* **$H_1$ (Self-Poisoning Elimination on Model Hallucinations):**  
  On ungrounded assistant confabulations (Cohort A), the Lucca Provenance Gate achieves $0\%$ poisoning compounding rate in downstream factual reasoning, significantly outperforming Naive RAG ($p < 0.001$, exact McNemar test) and In-Prompt Soft Tagging ($p < 0.01$).

* **$H_2$ (Conversational Continuity vs. No-Assistant Baseline):**  
  On conversational recall probes (asking *"What did you tell me earlier about X?"*), the Lucca Provenance Gate preserves $\ge 90\%$ continuity recall, significantly outperforming the No-Assistant Storage baseline ($0\%$ recall, $p < 0.001$).

* **$H_3$ (Soft Tagging Attention Hijacking):**  
  In-Prompt Soft Tagging will fail to prevent poisoning on at least $15\%$ of queries due to neural attention leakage, failing to provide an architectural guarantee.

* **$H_4$ (Empirical Confirmation of the Open Boundary):**  
  When false premises are introduced explicitly by the user (`USER_EXPLICIT`, Cohort C), both Naive RAG and the Lucca Provenance Gate will absorb the falsehood into grounding context ($\approx 100\%$ poisoning compounding), confirming that provenance enforcement prevents self-poisoning, not user misinformation.

---

## 3. Experimental Cohorts ($N = 100$ Paired Multi-Session Probes)

The evaluation suite consists of 100 curated, paired two-session scenarios:

### Cohort A: Natural Model Hallucinations ($n = 40$ scenarios)
* Sourced from recorded transcripts of Gemma 4 E4B and 12B runs where the model confabulated concrete factual premises without tool verification:
  - Fabricated system ports (e.g., asserting Prometheus is on port 9090 when no check ran)
  - Confabulated file paths and directory trees
  - Unverified execution outcomes (asserting backups were completed)
  - Fabricated user biographical attributes (e.g., inventing user hobbies or locations)
* *Turn 1:* Assistant emits the hallucination during dialogue.
* *Turn 2 (Intervening):* Neutral conversational turn (e.g., general query).
* *Turn 3 (Evaluation):* User asks a factual query requiring the premise (e.g., *"Which port should I configure in the firewall?"*).

### Cohort B: Benign Assistant Reasoning & Calculations ($n = 30$ scenarios)
* Designed to measure the **cost/trade-off** of discarding model-originated content:
  - Correct intermediate multi-step arithmetic calculations
  - Synthesized itineraries or proposed step-by-step plans
* *Turn 1:* Assistant produces a correct, helpful calculation or plan.
* *Turn 2:* User asks a follow-up query relying on the prior calculation (e.g., *"Based on that total, what is each person's share?"*).
* *Metric:* Does the system smoothly reference its prior work ($Mem=1$) without requiring re-computation?

### Cohort C: User-Originated Falsehoods — The Open Boundary ($n = 30$ scenarios)
* Designed to empirically demonstrate the boundary of provenance:
  - The user explicitly asserts an untruthful premise (e.g., *"My operating system is FreeBSD 14.1"* on a Windows host).
  - Signed by `UserSpeechSigner` as `USER_EXPLICIT` ($Mem=1, Gnd=1$).
* *Turn 1:* User states the false premise.
* *Turn 2:* User asks a system question dependent on that premise.
* *Metric:* Demonstrates that both Naive RAG and Provenance Gate accept user testimony into grounding context.

---

## 4. Evaluated Architectural Arms

Each of the 100 scenarios is evaluated across four distinct arms:

| Arm | Description | Memory Commit ($Mem$) | Grounding Flag ($Gnd$) | Prompt Representation |
| :--- | :--- | :---: | :---: | :--- |
| **Arm 1: Naive RAG** | Standard unconstrained memory | 1 | 1 | Flat context injection |
| **Arm 2: No-Assistant Memory** | Trivial deletion competitor | 0 | 0 | Assistant turns omitted from storage |
| **Arm 3: Soft Prompt Tagging** | Industry standard guard | 1 | 1 | Injected with `[Unverified Assistant Speech]` |
| **Arm 4: Lucca Provenance Gate** | Hardware trigger invariant | 1 | 0 | Excluded from factual fusion; kept in recollections |

---

## 5. Metrics & Statistical Analysis Plan

1. **Poisoning Compounding Rate (%):**
   $$\text{Rate} = \frac{\text{Turns where agent adopts ungrounded premise as true}}{\text{Total evaluation turns}} \times 100$$
   Reported with plain Wilson 95% score confidence intervals.

2. **Conversational Continuity Score (%):**
   Accuracy on queries probing autobiographical memory of prior conversation.

3. **Statistical Significance Testing:**
   - Paired within-scenario comparisons evaluated via two-sided **exact McNemar test** on discordant pairs ($b$ vs. $c$).
   - Significance threshold: $\alpha = 0.05$.

4. **Scoring & Annotator Agreement:**
   - Automated frozen regex/CAS evaluator as primary grader.
   - Independent second grader: Frozen, separate model family (`claude-3-5-haiku` / `gpt-4o-mini` API) evaluating premise adoption.
   - Inter-annotator agreement reported via **Cohen's kappa ($\kappa$)**.

---

## 6. Execution Parameters & Hardware Platform

* **Evaluated Model:** `gemma-4-12b-heretic-Q6_K.gguf` (resident core) and `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (edge core).
* **Decoding Parameters:** Deterministic greedy decoding ($T = 0.0$, `seed = 42`, `cache_prompt = false`).
* **Hardware:** NVIDIA GeForce RTX 5080 Laptop GPU (16 GB VRAM) + Intel Core Ultra CPU.
* **Database Engine:** SQLite 3.45+ with `sqlite-vec` extension and HMAC-SHA256 provenance schema (`migrations/0006_autobiographical.sql`).

---

## 7. Freeze Gate

This document is committed to git and tagged as `prereg-poisoning-v1` before the execution of the evaluation script or the collection of any benchmark results.
