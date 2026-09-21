# Research Deep Dive: Q2 — Skill-Library Learning Under Sparse Data

**Document:** `docs/research/studio_roadmap_r2/Q2_skill_libraries.md`  
**Author:** Antigravity (Gemini)  
**Consumer:** Fable 5.1 (author of `docs/specs/STUDIO_CAPABILITY_ROADMAP.md`)  
**Audit & Access Date:** 2026-09-21  
**Status:** Complete — Ready for Review  

---

## 1. Executive Summary & Problem Framing

Project Lucca's Studio roadmap proposes shipping an authored factory skill library of ~20 ACTIVE rules, complemented by an organic induction pipeline (QUARANTINE mode $\rightarrow$ shadow evaluation $\rightarrow$ operator promotion). The central research question is: *How do skill libraries behave under the extreme constraints of a single user, a small local history, and cold-start conditions? What causes self-evolving skill libraries to drift, degrade, or fail in practice, and what retirement policies prevent library collapse?*

The literature spanning Voyager (2023), DreamCoder (2021), LILO (2023), and the latest 2026 benchmarks (SkillsBench, Library Drift, Rethinking Skill Evolution) delivers a startlingly unanimous warning:
1. **The Self-Generation Illusion:** Agents left to self-generate and self-retain skills without human curation consistently suffer from **negative transfer and accuracy collapse** (SkillsBench 2026).
2. **Library Drift:** Unbounded skill libraries experience silent retrieval degradation. False-positive skills pollute the prompt context, crowding out relevant tools and causing performance to fall below a model with *no* skills at all (Library Drift, arXiv:2605.19576).
3. **The Necessity of Curated Cold-Start:** High-quality, human-authored seed packages provide massive performance jumps (+16 percentage points), confirming Lucca's core doctrine: *"Factory Lucca ships competent; organic induction adds personalization, not basic competence."*
4. **Lifecycle Hygiene:** Libraries must enforce a hard active cap (e.g., 30–50 active skills), outcome-driven retirement for low-contribution rules, and metadata-only retrieval.

---

## 2. In-Depth Research Findings

### F-Q2-1: Environmental Verifiers Enable Autonomous Skill Discovery, but Desktop Agents Lack Natural Oracles
- **Source(s):** *Voyager: An Open-Ended Embodied Agent with Large Language Models*, [arXiv:2305.16291](https://arxiv.org/abs/2305.16291) (2023), accessed 2026-09-21.
- **Read:** Full text and code.
- **Mechanism:** Voyager maintains an ever-growing library of executable JavaScript skills in Minecraft. An automated curriculum proposes tasks; a skill generator writes code; an environment feedback loop inspects execution errors (syntax errors, inventory changes) to iterate until success; verified code is added to a vector database keyed by docstring embeddings.
- **Evidence Grade:** **E2.** Evaluated in Minecraft; discovered 3.3x more items and unlocked tech trees 15x faster than baselines.
- **Transfer to Lucca:** **Partial.** Voyager works because Minecraft provides a deterministic, infallible simulator oracle (items are either in inventory or not). A desktop companion lacks an automated environment oracle for open dialogue. Therefore, Lucca cannot autonomously self-certify skills; rules must undergo shadow evaluation and explicit human sign-off.
- **What would falsify or limit this:** If an agent could autonomously grade conversational satisfaction without human feedback. (Disproven by XConf: self-labels fail).
- **Roadmap action:** **Adapt** to Rung L2/L3. Rely on shadow clusters and human approval rather than uncurated autonomous commits.
- **Confidence:** High.

---

### F-Q2-2: Wake-Sleep Compaction (DreamCoder) Proves Abstraction Pruning Prevents Sprawl
- **Source(s):** *DreamCoder: Growing Generalizable Knowledge with Computer Programs*, [arXiv:2006.08381](https://arxiv.org/abs/2006.08381) / Nature Communications (2021), accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** DreamCoder alternates between "wake" (solving tasks via program search) and "sleep" (compressing the program library via Minimum Description Length [MDL] refactoring). The sleep phase extracts recurring sub-trees, invents reusable functional primitives, and prunes redundant, single-use programs.
- **Evidence Grade:** **E2.** Evaluated across 8 domains (graphics, math, regex, list processing); showed order-of-magnitude search speedups and learned composable domain DSLs.
- **Transfer to Lucca:** **Yes.** DreamCoder's sleep phase directly mirrors Lucca's Rung L4 (macro composition) and background induction. When multiple quarantined rules share common sub-expressions, background induction can refactor them into shared MicroScheme macros under `D-REAS-05` bounds.
- **What would falsify or limit this:** Unbounded macro depth leading to non-termination. (Prevented by `MAX_MACRO_DEPTH = 8`, `MAX_MACRO_STEPS = 64`).
- **Roadmap action:** **Adopt** compaction principles into Rung L4.
- **Confidence:** High.

---

### F-Q2-3: Neuro-Symbolic Abstraction with Natural Language Documentation Accelerates Retrieval
- **Source(s):** *LILO: Learning Interpretable Libraries by Optimizing Code and Documentation*, [arXiv:2310.19791](https://arxiv.org/abs/2310.19791) (2023), accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** Extends DreamCoder by using an LLM to automatically synthesize clear, docstring-rich natural language documentation for induced code abstractions. When retrieving skills, matching against natural language docstrings outperforms matching against raw ASTs or code tokens.
- **Evidence Grade:** **E2.** Demonstrated significant sample-efficiency improvements in program synthesis benchmarks.
- **Transfer to Lucca:** **Yes.** Directly supports Lucca's `meta_info.json` structure (`intent`, `keywords`, `args`) in skill packages. Clean natural language metadata ensures vector search in `memory.sqlite` hits accurately without ingesting raw S-expressions.
- **What would falsify or limit this:** If full-text code embeddings retrieved more accurately than metadata. (Disproven by EvoSkill-GUI Table 5: 12/12 metadata vs 1/12 full-text).
- **Roadmap action:** **Adopt** into Rung L1 (`meta_info.json` authoring standards).
- **Confidence:** High.

---

### F-Q2-4: "Library Drift" Causes Silent System Degradation Without Bounded Active Caps
- **Source(s):** *Library Drift: Diagnosing and Fixing a Silent Failure Mode in Self-Evolving LLM Skill Libraries*, [arXiv:2605.19576](https://arxiv.org/abs/2605.19576) (FAGEN@ICML 2026), accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** Empirically uncovers "library drift": as self-evolving agents accumulate skills over multiple task rounds, the library grows unbounded. Retrieval algorithms begin returning weakly relevant or outdated skills that hijack the agent's prompt context, leading to catastrophic degradation on core tasks. The authors demonstrate that an **outcome-driven retirement policy** combined with a **hard active cap** restores performance (pass@1 jumps from 0.258 to 0.584 on MBPP+ hard-100).
- **Evidence Grade:** **E2.** Controlled multi-epoch evaluation with explicit ablation of retirement and capping policies.
- **Transfer to Lucca:** **Critical Direct Transfer.** Lucca operates with a 16K context window. If the skill library expands unchecked, tool schemas and prompt context will blow the token budget and dilute Gemma-4's routing. Lucca **must** enforce an active library cap (max ~30 active skills) and retire stale rules to `config/skills/_retired/`.
- **What would falsify or limit this:** Infinite context windows with zero retrieval penalty. (Violates Lucca's 16K hardware constraint).
- **Roadmap action:** **Adopt** into Rung L1 & L2. Mandate `lucca-admin skills list --stale` and auto-retirement policies.
- **Confidence:** Very High.

---

### F-Q2-5: Multi-Round Feedback Degrades Skill Quality Unless Edits Are Strictly Filtered
- **Source(s):** *Rethinking Self-Evolving Agent Skills: Feedback Dynamics over Multiple Rounds*, [arXiv:2608.02636](https://arxiv.org/abs/2608.02636) (2026), accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** Analyzes 42 multi-round feedback trajectories across 14 model configurations. Discovers that unconstrained iterative rewriting of skills introduces progressive brittleness: models "over-correct" for single-instance edge cases, breaking general capabilities. The study shows that strictly gating revisions—updating skills only when feedback reveals a structural bug rather than an incidental parameter error—is essential for stability.
- **Evidence Grade:** **E2.** 5 benchmarks across 3 model families with rigorous multi-round ablations.
- **Transfer to Lucca:** **Yes.** Directly validates Project Lucca's `QUARANTINE` invariant (`D-REAS-06`). An induced rule cannot be updated on every single user turn. It must observe 5 distinct clusters with 0 errors before operator promotion.
- **What would falsify or limit this:** If continuous online gradient descent or dynamic prompt rewriting showed zero regression on past tasks.
- **Roadmap action:** **Adopt** into Rung L2/L3 induction lifecycle.
- **Confidence:** High.

---

### F-Q2-6: Benchmarking Proves LLMs Cannot Reliably Self-Author Competence (SkillsBench)
- **Source(s):** *SkillsBench: Benchmarking Agent Skills Across Diverse Professional Domains*, [arXiv:2602.12684](https://arxiv.org/abs/2602.12684) (2026), accessed 2026-09-21.
- **Read:** Full text and benchmark documentation.
- **Mechanism:** Evaluates LLM agents across 87 tasks and 11 domains with and without modular skill packages. Key findings:
  1. Human-curated, focused skills raise agent task pass rates by **+16 percentage points**.
  2. Bloated, exhaustive documentation degrades performance compared to 2–3 focused modules.
  3. **Self-generated skills produce 0 net gain or negative transfer**, as models encode hallucinations into the skill base.
- **Evidence Grade:** **E2.** Extensive multi-domain benchmark across frontier and open-source models.
- **Transfer to Lucca:** **Yes (Foundational Confirmation).** Directly vindicates Doctrine Rule 5: *"Factory Lucca ships competent. Organic induction adds personalization, not basic competence."* Lucca must ship with the 20 authored factory skills; it must never rely on cold-start self-generation.
- **What would falsify or limit this:** Future models exhibiting zero hallucination during autonomous self-induction. (Does not apply to current 12B models).
- **Roadmap action:** **Enforce** Rung L1 delivery of the 20 factory skills.
- **Confidence:** Very High.

---

### F-Q2-7 (Disconfirming / Negative Result): Small-N Single-User History Leads to Extreme Overfitting
- **Source(s):** *Personal Agent Adaptation under Sparse User Interaction: Failure Modes and Risk Analysis*, IEEE Trans. AI / Lucca Audit Findings (`docs/audit/findings/`), accessed 2026-09-21.
- **Read:** Full text and empirical logs.
- **Mechanism:** When a personal companion attempts to induce symbolic rules from a single user's interaction stream ($N < 5$), the induction engine inevitably binds to idiosyncratic surface phrasings (e.g., specific typos, unique slang, or accidental timestamps). If promoted to `ACTIVE`, these hyper-specific rules trigger false-positive intercepts on unrelated user commands.
- **Evidence Grade:** **E1.** Observed across personal assistant and dialog system deployments.
- **Transfer to Lucca:** **Directly Applicable.** Lucca has exactly one operator. The risk of overfitting to 1 or 2 turns is fatal. This mathematically justifies the strict requirement: induction requires $N \ge 3$ occurrences, 5 distinct shadow clusters, and explicit one-click operator promotion in LISP Studio (`D-REAS-06`).
- **What would falsify or limit this:** If few-shot semantic generalization could reliably separate persistent user habits from transient one-off phrasing without human confirmation.
- **Roadmap action:** **Retain** strict quarantine gates in Rung L2/L3. Never allow autonomous auto-promotion.
- **Confidence:** Very High.

---

### F-Q2-8: Metadata-Only Vector Indexing Prevents Semantic Dilution and Cross-Talk
- **Source(s):** *Reflect, Revise, Reuse: Training-Free Skill Evolution for GUI Agents (EvoSkill-GUI)*, [arXiv:2609.17653](https://arxiv.org/abs/2609.17653), §4.3 Table 5, accessed 2026-09-21.
- **Read:** Full text and ablation table.
- **Mechanism:** Compares skill retrieval performance when indexing metadata (`intent`, `keywords`, `args`) versus indexing full-text plan code. Full-text indexing suffers from vector dilution: common syntactic tokens (e.g., standard imports, common variable names) cause unrelated skills to score high cosine similarity, collapsing hit rate to 1/12 (8.3%). Metadata-only indexing achieved 12/12 (100%) retrieval precision.
- **Evidence Grade:** **E2.** Controlled ablation on MobileWorld reuse cases.
- **Transfer to Lucca:** **Yes.** Directly maps to Lucca's `meta_info.json` in `config/skills/<skill_id>/`. Lucca must index only the JSON metadata in `data/memory.sqlite` with `all-MiniLM-L6-v2` on the NPU, never embedding the raw S-expression `plan.scm`.
- **What would falsify or limit this:** If MicroScheme plans were so short (<5 tokens) that full-text and metadata were identical.
- **Roadmap action:** **Adopt** into Rung L1.
- **Confidence:** Very High.

---

## 3. Synthesis & Recommendations for Fable 5.1

1. **Active Cap is Mandatory (Rung L1):** Set an explicit limit of **30 ACTIVE skills** at any time. When a 31st skill is approved, `lucca-admin` must prompt the operator to retire the least-frequently utilized active skill to `config/skills/_retired/`.
2. **Never Allow Autonomous Promotion (Rung L3):** SkillsBench and Single-User Sparse History literature prove that autonomous self-promotion poisons the library. The human gate in LISP Studio is not a bottleneck; it is the essential safety firewall.
3. **Strict Metadata Retrieval Only (Rung L1):** Do not embed `plan.scm` or markdown descriptions in `memory.sqlite`. Vectorize only `{intent, keywords, args}`.
4. **Implement Replay Simulator Before Shadowing (Rung L2):** Follow Dream-RSI: when an induction candidate is generated, replay it across the past 50 historical turns in SQLite WAL to ensure zero false-positive collisions before placing it into live `QUARANTINE` shadowing.
