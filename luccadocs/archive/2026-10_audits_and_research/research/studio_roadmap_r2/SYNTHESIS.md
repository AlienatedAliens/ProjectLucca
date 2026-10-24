# Synthesis for Fable 5.1: External Evidence & Roadmap Revisions

**Document:** `luccadocs/research/studio_roadmap_r2/SYNTHESIS.md`  
**Author:** Antigravity (Gemini)  
**Consumer:** Fable 5.1 (author of `luccadocs/specs/STUDIO_CAPABILITY_ROADMAP.md`)  
**Audit & Completion Date:** 2026-09-21  
**Status:** Complete — Ready for Roadmap Revision & Owner Ratification  

---

## 1. Top Executive Summary: Decisions This Research Changes

1. **T1 (Registry Sync):** Freeze tool schemas in an alphabetically-sorted prefix block; dynamic per-turn mutations destroy `llama-server`'s KV cache, spiking TTFT by 1.5–3.0s. Cap candidate tools in the prompt to $\le 16$.
2. **L1 (Skill Packages):** Enforce an active cap of $\le 30$ skills to prevent "library drift" and context exhaustion. Vectorize only `meta_info.json`, never embedding raw S-expression `plan.scm`.
3. **L2 (Shadow Upgrades):** Mandate Dream-RSI offline replay simulation across 50 past turns before live shadowing. Use paired McNemar testing on the frozen suite.
4. **L3 (Induction Viewer):** Require contrastive natural language diffs (*"What Lucca does today"* vs. *"What this rule will do"*) to prevent operator review fatigue and rubber-stamping.
5. **T4 (Outcome Telemetry):** Add an automated circuit breaker demoting active rules to `QUARANTINE` if failure rate exceeds 10% across a 10-turn rolling window. Report Wilson score intervals.
6. **C1 (Experience Bank):** Implement non-parametric mathematical `Recall` (kernel-weighted historical hit rate) and **strictly omit verbalized `Reflect`**, which breaks down below 27B (XConf §K).
7. **C2 (Difficulty Gating):** Confirm When2Think difficulty-aware routing to bypass thinking mode on easy turns, locking in Lucca's 282 ms speakable TTFT.
8. **Section 8 (Citations):** Correct 6 erroneous citation IDs/attributions (SCRC, Pel, LLM+AL, PsychoAgent, DAMM, Library Drift [152]) and purge ghost citation `2609.13770`.

---

## 2. Roadmap Impact Table (Rung by Rung: T1 through C2)

| Rung | Deliverable | Supporting Findings | Weakening Findings & Hardware Constraints | Recommended Change to Roadmap Spec | Confidence |
|---|---|---|---|---|---|
| **T1** | Dynamic capability registry sync | DecoVer (dual verification); Pel (grammar sandboxing) | `llama-server` prefix cache invalidates if tool schemas mutate per-turn (F-Q4-6); BFCL proves 12B models collapse past 16–20 tools (F-Q4-1). | **Adapt:** Freeze tool definitions in an alphabetically-sorted static prefix block. Cap prompt tool catalog to $\le 16$ candidate tools using dynamic shortlisting. | **High** |
| **L1** | Skill package format & 20 factory skills | EvoSkill-GUI (12/12 metadata retrieval, F-Q2-8); SkillsBench (+16 pp curated gain, F-Q2-6) | "Library Drift" (Zhang et al. 2026, F-Q2-4) shows unbounded libraries cause silent accuracy degradation; Minton's Utility Problem (F-Q3-4). | **Adapt:** Set a hard active cap of **$\le 30$ ACTIVE skills**. Mandate vectorizing only `meta_info.json` in `memory.sqlite`. Define `_retired/` directory. | **High** |
| **T2** | Native tools (`memory`, `notes`, `sys`, `metrics`) | LLMCompiler (parallel dispatch, F-Q1-2); LiveKit / Pipecat (verbal cues mask tool latency, F-Q5-4) | Network and sandboxed process execution take 500–2,000 ms, breaking sub-second voice budget without intermediate feedback. | **Adopt:** Implement native tools with Class A/B/C target policy. Preserve `D-BRAIN-03` verbal thinking cues before launching synchronous tools. | **High** |
| **L2** | Shadow telemetry in Studio UI | ModularRSI (contrastive trajectory pairs, F-Q1-6, F-Q7-5); Dream-RSI (replay simulator, F-Q2-2) | Under the Rule of Three (F-Q6-1), 5 shadow clusters only bounds failure rate to $\le 60\%$. Purely empirical shadowing cannot prove safety. | **Adapt:** Add Dream-RSI offline replay simulation across 50 past turns before live shadowing. Use paired McNemar tests for Studio metrics. | **High** |
| **L3** | Induction viewer & candidate promotion | Soar (chunking resolved impasses, F-Q3-2); Q-Evolve / PANDO (distillation gating) | Human review fatigue causes 95%+ rubber-stamping if presented with raw S-expressions (F-Q7-5); single-user small-$N$ overfits (F-Q2-7). | **Adapt:** Render contrastive plain-English diffs and show the 5 inducing historical turns. Maintain permanent prohibition of automated promotion. | **High** |
| **T3** | Class C gates (`clipboard`, `screenshot`) | USENIX Security sandbox leakage audits (F-Q7-1); ARC obstacle-to-workaround threat (F-Q7-3) | LLMs treat negative prompt rules as obstacles to circumvent; prompt-based deontic gates fail without host OS architectural enforcement. | **Adopt:** Enforce deontic confirmation at the tool dispatcher layer (`capabilities.py`), never trusting LLM self-restraint. | **High** |
| **L4** | Macro composition under `D-REAS-05` | ACT-R (production compilation, F-Q3-3); DreamCoder (MDL compression, F-Q2-2) | Static multi-step plans suffer from cascading error propagation if intermediate tool returns diverge (F-Q1-7); macro explosion. | **Adapt:** Enforce `MAX_MACRO_DEPTH = 8` and `MAX_MACRO_STEPS = 64`. Mandate intermediate schema validation between macro steps. | **High** |
| **T4** | Outcome telemetry & tool reports | Trajectory-level multi-factor scoring (F-Q6-6); Canary deployment patterns (F-Q7-6) | Binary pass/fail metrics have low statistical power at $N < 50$. Promoted rules can experience post-promotion distribution shift (F-Q7-4). | **Adopt:** Implement an automated circuit breaker: auto-demote active rules to `QUARANTINE` if failure rate exceeds 10% over 10 turns. Compute Wilson score intervals. | **High** |
| **C1** | Experience bank (XConf-lite) | XConf §C (ground-truth outcome labels required, self-labels fail, F-Q6-4); Selective Conformal Risk Control | XConf §K Figure 14b proves verbalized `Reflect` collapses on models $<27\text{B}$ (F-Q6-4). 12B Gemma-4 cannot do verbalized reflection. | **Adapt:** Implement **non-parametric mathematical `Recall` only** (kernel-weighted hit rate over $k=50$ past episodes). **Omit verbalized `Reflect`**. | **High** |
| **C2** | Difficulty-aware thinking (When2Think) | When2Think (IDAC reward shaping toggles THINK/NOTHINK dynamically, F-Q4-5) | Generating reasoning tokens adds 400–1,200 ms to TTFT; running thinking mode on routine conversational turns destroys voice budget. | **Adopt:** Route easy turns to `enable_thinking=false` (TTFT ~280 ms); route complex turns to `enable_thinking=true`. | **High** |

---

## 3. Contradictions Between Sources & Resolution for Lucca

### 1. Imperative Code Actions (CodeAct) vs. Pure Action Languages (Pel, LLM+AL, DecoVer)
- **The Contradiction:** CodeAct (ICML 2024) claims LLMs perform up to 20% better when writing executable Python code in an interactive REPL rather than structured tool calls. Conversely, Pel (Mohammadi 2025) and LLM+AL (AAAI 2025) argue that imperative Python is inherently unsafe, non-deterministic, and impossible to verify with formal reasoners.
- **Resolution for Lucca:** CodeAct's model is accepted *only* as a contained Class A tool (`run_python` sandbox for exact arithmetic), but **strictly rejected as the planning substrate**. Lucca's cognitive orchestrator must remain pure MicroScheme: gas-metered, verifiable by Z3 SMT, and bounded.

### 2. Unbounded Lifelong Learning (Voyager) vs. Library Drift (Zhang et al. 2026) & SkillsBench (2026)
- **The Contradiction:** Voyager (2023) advocates for an "ever-growing, unbounded" library of self-generated skills. In contrast, Library Drift (2026) and SkillsBench (2026) demonstrate that unbounded self-generation causes silent retrieval decay, false-positive injection, and net-negative transfer.
- **Resolution for Lucca:** Voyager's unbounded accumulation works only in video games with synthetic environment oracles. For a desktop companion, Library Drift's findings govern: Lucca **must cap active skills ($\le 30$)**, retire stale rules, and ship with 20 curated factory skills.

### 3. Open-Mic VAD (LiveKit/Pipecat) vs. Push-to-Talk Half-Duplex (Lucca ADR-009)
- **The Contradiction:** Modern voice agent frameworks prioritize "seamless, interruptible open-microphone conversation." However, their issue trackers reveal that acoustic echo feedback loops cause frequent self-interruption, while VAD silence thresholds add 400–800 ms of dead air.
- **Resolution for Lucca:** Lucca's Push-to-Talk (PTT) priority is technically superior for desktop companions: it provides 0 ms endpointing latency and completely eliminates self-interruption. Open-mic VAD should remain an optional secondary mode.

### 4. LLM-as-a-Judge vs. Ground-Truth Observables (XConf §C)
- **The Contradiction:** Many agent frameworks rely on LLM prompts to self-evaluate task success. XConf §C proves that LLM judges share blind spots with generators, inflating confidence on consensus-wrong items by $+0.13$ to $+0.25$.
- **Resolution for Lucca:** Never use Gemma-4 to autonomously grade its own induced rules. Ground truth must come from objective signals: tool exit codes ($0 = \text{success}$), Pydantic validation, and explicit operator feedback.

---

## 4. What We Could Not Find or Verify

1. **Intended Role of arXiv:2609.13770:**
   - Listed in line 6 of the roadmap header as one of the 8 curated papers, but absent from Section 8 and the body. The paper covers offline student model distillation without reasoning trajectories. We could find no architectural connection to Lucca's runtime skill packages. Recommendation: **Purge citation**.
2. **Mathematical Proof of Safety from 5 Shadow Clusters Alone:**
   - Under the frequentist Rule of Three ($3/N$), 5 trials with 0 errors only bounds failure rate to $\le 60\%$ ($p < 0.05$). We found no literature supporting claims that 5 shadow clusters alone proves high reliability. Safety is established by **Z3 SMT verification and gas bounds**, while shadow clusters merely demonstrate user intent recurrence.
3. **Verified Preprint for "Vera (2601.08421)":**
   - arXiv:2601.08421 is an online DPO preference learning paper. Vera is an industry agent test-quarantine framework, but its cited arXiv ID is invalid.
4. **Viability of Un-routed 30+ Flat Tool Catalogs on 12B Models:**
   - No benchmark or empirical study demonstrated reliable tool calling for 7B–14B models when presented with $>30$ candidate tools in a flat prompt. All literature mandates coarse-to-fine routing or dynamic shortlisting.

---

## 5. Open Questions Requiring Owner Decisions

### Decision 1: Active Skill Library Cap Threshold
- **Option A (Recommended):** Cap active skills at **30** (20 factory + 10 personal induced). Exceeding 30 triggers an explicit retirement prompt in LISP Studio.
- **Option B:** Dynamic shortlisting via NPU embeddings, allowing an arbitrary number of skills on disk but injecting only the top 10 relevant skills into the prompt context per turn.

### Decision 2: Automated Demotion Circuit Breaker Threshold
- **Option A (Recommended):** If an `ACTIVE` rule incurs $>10\%$ failure rate or user corrections over a rolling 10-turn window, automatically demote it to `QUARANTINE` and alert the user.
- **Option B:** Retain the rule in `ACTIVE` but display a warning badge in LISP Studio requiring manual operator demotion.

### Decision 3: Errata Cleanup in Section 8
- **Approve proposed errata:** Correct the 6 misattributed/erroneous citation IDs in Section 8 (SCRC $\rightarrow$ 2512.12844; Pel $\rightarrow$ 2505.13453; LLM+AL $\rightarrow$ 2501.00830; PsychoAgent $\rightarrow$ 2608.07438; DAMM $\rightarrow$ Architecture spec; Library Drift $\rightarrow$ [152] from 2609.11873v2) and delete ghost citation 2609.13770.

### Decision 4: Omission of Verbalized Reflect on Rung C1
- **Approve omission:** Restrict Rung C1 (Experience Bank) to **non-parametric mathematical Recall** (kernel-weighted hit rate over past episodes in SQLite WAL), omitting verbalized LLM reflection based on XConf's 27B model-scale cliff.
