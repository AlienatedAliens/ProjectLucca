# Research Plan: External Evidence for Lucca's Studio Capability Roadmap

**Document:** `docs/research/studio_roadmap_r2/PLAN.md`  
**Author:** Antigravity (Gemini)  
**Consumer:** Fable 5.1 (author of `docs/specs/STUDIO_CAPABILITY_ROADMAP.md`)  
**Owner Gate:** Human approval required before Phase 1 commences  
**Date:** 2026-09-21  

---

## 1. Context, Constraints & Methodological Protocol

### 1.1 Operating Environment & Hardware Budget Constraints
Every piece of evidence evaluated in this research brief must be strictly filtered through Project Lucca’s local-first hardware and architectural constraints:
1. **Model Backbone:** Native Windows `llama-server.exe` running `gemma-4-12b-heretic-Q6_K.gguf` (12.5 GB / 12,800 MiB resident VRAM clamp on 16 GB GDDR7 RTX 5080 Laptop GPU; 16K context; flash attention; Q8_0 KV cache).
2. **NPU Perception Lobe:** Intel Core Ultra 9 275HX Arrow Lake NPU accessed exclusively via OpenVINO (`device="NPU"`). Workloads: INT8 vector embeddings (`all-MiniLM-L6-v2`), Silero VAD, Faster-Whisper ASR, and Kokoro TTS.
3. **Reasoning Substrate:** Pure functional MicroScheme v2 (gas-metered to 1,000 instructions, max nesting depth 32, max AST tokens 2,000, 0 global mutations, Z3 SMT pre-verification) hosted on the host CPU alongside SQLite WAL + `sqlite-vec`.
4. **Execution Tiers:**
   - `REFLEX` (<150 ms, safety/emergency only, canned speech bypass).
   - `ACT_THEN_NARRATE` (procedural rules execute deterministically, then LLM synthesizes voice response).
   - `FULL_LOOP` (open dialogue and multi-step tool calls with intermediate spoken cues, target $p_{50} \le 850\text{ ms}$).
5. **Single-User Persona:** Single operator desktop companion, not a multi-tenant enterprise server.

### 1.2 Ground Rules & Non-Negotiables
- **No Fabricated Sources:** Every cited source must be directly inspected in this session with full URL and access date.
- **Reading Depth Disclosure:** Explicitly declare whether reading was abstract only, full text, code implementation, or issue tracker threads.
- **Separation of Fact and Inference:** Clear demarcation between what the source empirically showed versus what we infer for Lucca.
- **Mandatory Disconfirming Evidence:** Every question requires targeted negative-result searches (failures, limitations, scaling breakdowns).
- **Transfer Rigor:** Explicit evaluation of whether frontier-scale findings transfer to a local 12B model with sub-second latency targets.

### 1.3 Evidence Grading System
| Grade | Criteria |
|---|---|
| **E1** | Independently replicated across multiple labs/frameworks with publicly verified code and benchmarks. |
| **E2** | Primary authors' empirical evaluation with formal ablations and released code/data. |
| **E3** | Primary authors' experiments, but lacking ablations, missing code, or using unverified benchmarks. |
| **E4** | Theoretical framework, survey paper, architectural proposal, or position paper without empirical trials. |
| **E5** | Blog posts, marketing materials, README claims, or uncorroborated social media announcements. |

---

## 2. Track 0: Roadmap Citation Audit Plan

**Goal:** Audit all citations in `docs/specs/STUDIO_CAPABILITY_ROADMAP.md` (the 8 curated local PDFs and Section 8 references) to verify authenticity, extract exact figures, and assess support strength.

### 2.1 Target Documents & Exact Claims to Verify
Local PDF files are pre-staged in `docs/`:
1. **arXiv:2609.02749 (`2609.02749v1.pdf` — AREX-Skill):**
   - *Roadmap Attribution:* 3-layer skill package format; tool execution decoupling.
   - *Verification Target:* Verify exact package format, schema definitions, and empirical tool-use results.
2. **arXiv:2609.11873 (`2609.11873v2.pdf` — The Last AI Built by Humans):**
   - *Roadmap Attribution:* Recursive Self-Improvement (RSI) autonomy ladder (§3.5), mapping Lucca to Level 4.
   - *Verification Target:* Verify the RSI level definitions, safety governance requirements, and Level 4 criteria.
3. **arXiv:2609.13770 (`2609.13770v1.pdf`):**
   - *Roadmap Attribution:* Curated set paper; role in studio capability.
   - *Verification Target:* Title, authors, core mechanism, and exact relevance to skill/tool architecture.
4. **arXiv:2609.14857 (`2609.14857v1.pdf` — ModularRSI):**
   - *Roadmap Attribution:* Contrastive shadow analysis (§3.3); library drift and skill retirement (§6.6 ref [152]).
   - *Verification Target:* Locate §3.3 contrastive pair formulation, verify mathematical definition, and check library drift citations.
5. **arXiv:2609.14858 (`2609.14858v1.pdf` — Dream-RSI):**
   - *Roadmap Attribution:* Replay-before-live shadowing; historical execution traces as offline simulation environment.
   - *Verification Target:* Extract replay simulation protocol, off-policy evaluation bounds, and compute overhead.
6. **arXiv:2609.17653 (`2609.17653v1.pdf` — EvoSkill-GUI):**
   - *Roadmap Attribution:* 3-layer package structure (`meta_info.json`, `plan`, `backup.md`, `recover.md`, `failure_examples/`); Table 5 claim that metadata-based retrieval achieves "12/12 vs 1/12" correct reuse over full-text; information-isolated critic (Eqs. 8a–8c).
   - *Verification Target:* Inspect Table 5 directly in the PDF; verify the "12/12 vs 1/12" claim; verify Eqs. 8a–8c for critic isolation.
7. **arXiv:2609.17708 (`2609.17708v1.pdf` — XConf):**
   - *Roadmap Attribution:* Experience Bank (Recall + Reflect); claim in §C that self-labeled outcome banks fail.
   - *Verification Target:* Locate §C, verify empirical failure mode of self-labeled confidence, verify retrieval mechanism ($k=50$).
8. **arXiv:2609.19671 (`2609.19671v1.pdf` — When2Think):**
   - *Roadmap Attribution:* Difficulty-aware thinking; IDAC reward shaping; dynamic per-turn thinking budget.
   - *Verification Target:* Locate IDAC reward formulation, verify difficulty estimator design and latency trade-offs.
9. **Secondary References from Section 8:**
   - *Library Drift / Rethinking Skill Evolution* (ModularRSI refs [152], [153]).
   - *Selective Conformal Risk Control (2501.07689)*.
   - *Vera (2601.08421)*, *Q-Evolve (ICML 2026)*, *PANDO (2605.24785)*.
   - *PsychoAgent (2604.00931 / 2602.04119)*, *DAMM (2501.09211)*.
   - *Pel (2503.01188)*, *LLM+AL (2410.13421)*, *DecoVer (ACL 2026)*.

### 2.2 Extraction & Audit Methodology
- Parse local PDFs using Python PDF extraction scripts (`pypdf` / `pdfminer`) to verify exact text, tables, formulas, and references.
- Output file: `docs/research/studio_roadmap_r2/T0_citation_audit.md`.

---

## 3. Question-by-Question Research Methodology

### Q1: Result-Aware Bounded Planning
**Context:** Lucca’s MicroScheme rules are pure `State → Plan` functions. Once a tool executes, how do outputs safely re-enter the evaluator for sequential steps without sacrificing gas bounds, type safety, or Z3 decidability?

- **Refined Sub-Questions:**
  1. How do production neuro-symbolic systems pass intermediate tool outputs (strings, JSON, binary handles) back into pure functional evaluators?
  2. What effect or monadic systems preserve formal verification when intermediate tool results are non-deterministic?
  3. How do frameworks like ReWOO, LLMCompiler, and CodeAct handle data dependencies between steps without turning the DSL into an unmetered general-purpose Turing-complete language?
  4. What breaks when structured JSON tool receipts are injected into S-expressions?
- **Planned Primary Searches:**
  - `"result-aware" planning LLM symbolic action language`
  - `"typed dataflow" tool composition agent 2024 OR 2025 OR 2026`
  - `ReWOO OR LLMCompiler execution graph intermediate tool results`
  - `monadic effects OR effect system DSL agent verification`
  - `BDI agent tool result state update "belief revision"`
- **Planned Disconfirming / Failure Searches:**
  - `"error propagation" intermediate tool output failure multi-step agent`
  - `"type confusion" tool result parsing agent failure`
  - `undecidable OR state explosion symbolic planner dynamic tools`
- **Specific Lucca Transfer Gate:** Can the mechanism be evaluated within MicroScheme’s 1,000 gas limit and $\le 20\text{ ms}$ execution budget without invoking an LLM round-trip for intermediate data extraction?

---

### Q2: Skill-Library Learning Under Sparse Data
**Context:** Lucca serves a single user. Large-scale web agents assume thousands of diverse trajectories. How do skill libraries cold-start, avoid catastrophic drift, and scale when interaction history is small ($N < 50$)?

- **Refined Sub-Questions:**
  1. What is the minimum trajectory count ($N$) required for reliable skill induction in modern frameworks (Voyager successors, LILO, Cradle)?
  2. How do skill libraries degrade as library size grows ($K > 20$)? What causes library drift?
  3. Which retirement/pruning algorithms (e.g. utility-decay, usage-recency, clustering) prevent retrieval degradation?
  4. How can single-user idiosyncrasies be learned without overfitting to one-off task variations?
- **Planned Primary Searches:**
  - `"skill library" "cold start" LLM agents few-shot 2024 OR 2025 OR 2026`
  - `"library drift" agent skills retrieval degradation`
  - `LILO OR Voyager skill pruning retirement policy`
  - `"procedural memory" lifelong learning agent single user`
- **Planned Disconfirming / Failure Searches:**
  - `"skill library" failure modes OR "retrieval collapse"`
  - `"overfitting" learned skills agent repeated tasks`
  - `when does skill induction fail LLM agent`
- **Specific Lucca Transfer Gate:** Does the retrieval policy fit into NPU vector search ($<5\text{ ms}$) without requiring an LLM re-ranking pass?

---

### Q3: Classic Cognitive Architectures (Soar, ACT-R, CoALA)
**Context:** Decades of cognitive science refined procedural compilation and impasse resolution. What can Lucca borrow for her 20–30 rule library, and what should be rejected?

- **Refined Sub-Questions:**
  1. How does Soar’s impasse-driven subgoaling map to Lucca’s System 1 (MicroScheme) $\to$ System 2 (FULL_LOOP LLM) handoff?
  2. How does ACT-R compile declarative knowledge into production rules without runaway rule proliferation?
  3. Does CoALA’s (Cognitive Architectures for Language Agents) memory taxonomy hold up in production desktop companions?
  4. What architectural dead-ends in classic production systems (e.g. RETE algorithm memory scaling issues, conflict-resolution loops) must Lucca avoid?
- **Planned Primary Searches:**
  - `Soar "impasse driven learning" LLM agent hybrid`
  - `ACT-R procedural compilation production rules modern AI`
  - `CoALA memory architecture language agents evaluation`
  - `production rule systems RETE performance limits agents`
- **Planned Disconfirming / Failure Searches:**
  - `"production system" limitations OR "utility problem" ACT-R Soar`
  - `why cognitive architectures failed commercial agents`
  - `chunking over-generalization Soar critique`
- **Specific Lucca Transfer Gate:** Can production compilation operate deterministically without infinite subgoaling loops during real-time speech?

---

### Q4: Small-Model Tool Use (7B–14B) & Prompt/Cache Limits
**Context:** Lucca runs Gemma-4-12B-Heretic locally. Small models behave very differently from GPT-4o or Claude 3.5 Sonnet when handling tool definitions.

- **Refined Sub-Questions:**
  1. What is the quantitative degradation curve for 7B–14B models as tool definitions increase from 5 to 10, 15, and 25?
  2. How does constrained grammar decoding (GBNF / JSON schema enforcement) affect latency and token efficiency on llama.cpp?
  3. Does enabling reasoning/thinking tokens improve or impair structured JSON tool argument compliance?
  4. How does llama.cpp's KV cache prefix reuse behave under prompt mutations (e.g. sliding window, dynamic memory injection, variable tool definitions)?
- **Planned Primary Searches:**
  - `"small language models" tool calling accuracy degradation count 2024 OR 2025 OR 2026`
  - `llama.cpp grammar guided decoding latency benchmark GBNF`
  - `thinking tokens reasoning model tool call reliability "Gemma" OR "Qwen"`
  - `llama.cpp KV cache prefix reuse sliding window attention`
- **Planned Disconfirming / Failure Searches:**
  - `"tool hallucination" small models benchmark failures`
  - `GBNF constrained decoding throughput drop overhead`
  - `reasoning models failing structured tool calling`
- **Specific Lucca Transfer Gate:** Will 20 active tool schemas fit in Gemma-4's system prompt while maintaining $<300\text{ ms}$ TTFT and $>95\%$ argument schema accuracy?

---

### Q5: Open-Source Voice Agents & Audio Concurrency
**Context:** Voice companions must manage real-time streaming, barge-in, and turn-taking without awkward pauses or robotic clipping.

- **Refined Sub-Questions:**
  1. How do production open-source voice frameworks (Pipecat, LiveKit Agents, Daily, Vocode) structure their audio pipelines and concurrency contracts?
  2. How do they handle turn-taking detection (VAD threshold vs. semantic end-of-turn vs. acoustic pause detection)?
  3. What are the common failure modes and race conditions in barge-in handling (inspect closed-as-wontfix issues and bug threads)?
  4. How does Lucca’s 3-tier model (`REFLEX`, `ACT_THEN_NARRATE`, `FULL_LOOP`) compare to standard streaming LLM pipelines?
- **Planned Primary Searches:**
  - `Pipecat voice agent architecture pipeline turn taking`
  - `LiveKit Agents barge-in interruption handling VAD`
  - `real-time voice LLM latency breakdown audio buffer underrun`
  - `semantic turn-taking vs VAD conversational speech agent 2025 OR 2026`
- **Planned Disconfirming / Failure Searches:**
  - `Pipecat github issues barge-in race condition OR audio clipping`
  - `LiveKit agents issues interruption latency bug`
  - `voice agent conversational breakdown false interruption`
- **Specific Lucca Transfer Gate:** Does Lucca's ZeroMQ 4-byte big-endian IPC and shared-memory ring buffer match or exceed standard WebRTC/async audio pipelines?

---

### Q6: Evaluation with One User & Small Samples
**Context:** Standard AI evaluation relies on large validation splits ($N > 1,000$). How do we evaluate personal companion agents with one user, sequential history, and sample sizes of $N \le 50$?

- **Refined Sub-Questions:**
  1. What statistical methodologies (e.g. sequential analysis, permutation tests, SPRT, conservative binomial bounds) provide valid confidence intervals on $N \le 50$ trials?
  2. How can paired testing against frozen regression fixtures prevent silent behavioral drift during personal skill evolution?
  3. What are the known failure modes of LLM-as-a-judge when evaluating personal companion interactions (sycophancy, length bias, self-enhancement)?
  4. How do personal agents detect data contamination when user prompts mirror previous training or induction samples?
- **Planned Primary Searches:**
  - `"small sample" evaluation LLM agents sequential testing`
  - `sequential probability ratio test SPRT agent evaluation`
  - `frozen regression testing personalized agent skills`
  - `LLM-as-a-judge failure modes small sample bias 2024 OR 2025 OR 2026`
- **Planned Disconfirming / Failure Searches:**
  - `LLM-as-a-judge sycophancy personal agent evaluation failure`
  - `overfitting small N benchmark conversational agent`
  - `sequential testing false discovery rate agent evaluation`
- **Specific Lucca Transfer Gate:** Does the statistical confidence threshold justify the 5-cluster promotion gate in D-REAS-06?

---

### Q7: Safe Promotion of Learned Procedures & Sandboxing
**Context:** When Lucca induces a new procedural habit, how do we guarantee it cannot escape its sandbox, abuse permissions, or silently degrade existing capabilities?

- **Refined Sub-Questions:**
  1. What are the documented failure modes of shadow-mode evaluation in self-improving agents (e.g. false passes due to benign test contexts, distribution shift)?
  2. How do systems enforce capability containment when a tool or skill requests broader arguments over time?
  3. What automated rollback triggers (e.g. runtime anomaly score, user negative reinforcement, error spikes) are most reliable?
  4. How can deontic guards and Z3 SMT verification be maintained across composite or macro-expanded rules?
- **Planned Primary Searches:**
  - `"shadow deployment" autonomous agents failure modes`
  - `quarantine promotion safety gates self-improving AI`
  - `deontic constraints runtime enforcement tool use agents`
  - `automated rollback policies self-evolving software agents`
- **Planned Disconfirming / Failure Searches:**
  - `"shadow mode" false confidence safety bypass agents`
  - `self-improving agent security escape vulnerabilities`
  - `reward hacking induced rules agent failure`
- **Specific Lucca Transfer Gate:** Does the current quarantine state machine in `src/lucca/reasoning/lifecycle.py` protect against argument-escalation attacks?

---

## 4. Work Breakdown & Artifact Delivery Schedule

```
Phase 0: Research Plan & Ground Rules
  └── File: docs/research/studio_roadmap_r2/PLAN.md (THIS FILE)
  └── GATE: Stop and obtain human operator sign-off.

Phase 1: Track 0 — Roadmap Citation Audit
  └── File: docs/research/studio_roadmap_r2/T0_citation_audit.md
  └── Direct text extraction from 8 local PDFs + Section 8 papers.
  └── GATE: Stop for review.

Phase 2: Deep Dives — Q1 to Q3 (Planning, Libraries, Cognition)
  └── Files:
      ├── docs/research/studio_roadmap_r2/Q1_result_aware_planning.md
      ├── docs/research/studio_roadmap_r2/Q2_skill_libraries.md
      └── docs/research/studio_roadmap_r2/Q3_cognitive_architectures.md
  └── GATE: Stop for review.

Phase 3: Deep Dives — Q4 to Q7 (Small Models, Voice, Eval, Safety)
  └── Files:
      ├── docs/research/studio_roadmap_r2/Q4_small_model_tool_use.md
      ├── docs/research/studio_roadmap_r2/Q5_voice_agents.md
      ├── docs/research/studio_roadmap_r2/Q6_small_n_evaluation.md
      └── docs/research/studio_roadmap_r2/Q7_safe_promotion.md
  └── GATE: Stop for review.

Phase 4: Synthesis & Roadmap Impact for Fable 5.1
  └── Files:
      ├── docs/research/studio_roadmap_r2/SYNTHESIS.md (<=10 line core summary, Rung Impact Matrix T1..C2)
      └── docs/research/studio_roadmap_r2/INDEX.md (Master navigation index)
```

---

## 5. Phase 0 Report

- **Done:** Formulated complete research plan covering Track 0 and Questions Q1–Q7 with refined sub-questions, targeted primary/disconfirming searches, hardware transfer criteria, and evidence rubrics. Confirmed presence of all 8 local PDFs in `docs/`.
- **Not done:** Execution of Track 0 and literature searches (blocked awaiting human approval).
- **Evidence:** Verified existence of local PDF files in `c:\Projects\ProjectLucca\docs\`:
  - `2609.02749v1.pdf`, `2609.11873v2.pdf`, `2609.13770v1.pdf`, `2609.14857v1.pdf`
  - `2609.14858v1.pdf`, `2609.17653v1.pdf`, `2609.17708v1.pdf`, `2609.19671v1.pdf`
- **Deviations from brief:** None.
- **Open questions:** None; plan is fully scoped and ready for operator review.
