# Reasoning Research Pass — Papers Informing the Concert Layer

**Date:** 2026-09-26
**Method:** Nia quick searches (2 passes: neuro-symbolic verification; abduction/discovery). Abstracts/snippets read, not full texts — treat mappings as leads to verify, not confirmed transfers.
**Companion:** [`LUCCA_REASONING_CAPABILITY.md`](./LUCCA_REASONING_CAPABILITY.md), [`../adr/0010_d_reas_09_concert_layer.md`](../adr/0010_d_reas_09_concert_layer.md)

---

## The headline

The concert layer's core pattern — **LLM proposes, symbolic layer validates each step, everything leaves an auditable trace** — is *strongly convergent* with 2026 research. Three independent groups have landed on near-identical architectures this year. That's validation of the direction, and it means the window to be *first to ship it with cryptographic provenance* is short.

## Papers, mapped to our mechanisms

| Paper | What it does | What it offers WO-20 |
|---|---|---|
| **SymStep** (arXiv:2607.23055) | Symbolic verification of *each step* in logical reasoning, not just the conclusion | **Direct validation of the Phase 3 pattern** (LISP validates every LLM step). Take: step-level (not conclusion-level) verification granularity. |
| **NSF-CoT** (ACL 2026 Findings) | Neuro-symbolic formal verification of chain-of-thought | How to formalize CoT steps for SMT checking — informs how `InferenceStep` premises map to Z3-checkable form. |
| **LogicTrack** (arXiv:2609.21492) | Audits LLM reasoning *trajectories* with formal logic solvers | **Direct validation of the proof-trace idea** — the trajectory as an auditable object. Take: trace schema design for replay/audit. |
| **Semi-structured Reasoners Can Be Rigorously Audited** (arXiv:2505.24217) | Shows semi-structured LLM output is auditable | Informs the `InferenceStep` JSON schema — what structure makes LLM output machine-checkable without killing fluency. |
| **Forethought** (arXiv:2607.04096) | Verifiable reasoning from neurosymbolic *primitive programming* | Closest to "LISP as the primitive layer the LLM reasons against." Take: primitive design — small, verifiable, composable. |
| **HypoAgent** (arXiv:2605.31370) | Abductive hypothesis generation *over knowledge graphs* | **Direct validation of abduction-over-KG** — our `kg_entities`/`kg_edges` as the reasoning substrate. Take: interactive hypothesis generation loop. |
| **Unified Taxonomy of Abductive Reasoning** (arXiv:2604.08016) | Survey of abduction in LLMs | Framing for the abduction half — where our "best explanation, marked as deduced" sits in the taxonomy. |
| **CEDAR-GRPO** (arXiv:2608.14791) | Process-aware RL for abductive reasoning | Future: if we ever fine-tune the abductive engine (slot-2 brain), process rewards over step validity. Low priority now. |
| **Hybrid Causal KGs + Neural-Symbolic Policy** (SemEval 2026) | Abductive event reasoning over causal KGs | The KG-plus-policy angle for the curiosity loop (WO-21). |
| **Advancing Abductive Reasoning in KGs** (ACL 2024) | Complex logical hypothesis generation in KGs | Foundational KG-abduction method; older but directly on our substrate. |

## What this changes (and doesn't)

**Validated by convergence:** the LISP-validates-LLM-steps pattern (SymStep, NSF-CoT), the proof-trace-as-auditable-object (LogicTrack), abduction-over-KG (HypoAgent), and the structured-step protocol (Semi-structured Reasoners). The design isn't speculative — three independent 2026 groups are building adjacent versions.

**Still Lucca-specific (the differentiators nobody else has):**
1. **Cryptographically signed intermediates** — the papers verify steps; none *sign* them into a provenance-gated store. Our `LISP_ASSERTION` envelopes make every intermediate a tamper-evident, replayable record.
2. **The `INFERRED` commit path with supersession-by-direct-evidence** — conclusions marked as deductions, overruled by later direct facts. Nobody else has the fact/opinion/deduction tiering.
3. **Local, companion deployment** — the papers are cloud-scale reasoning systems; none run as a local companion with a 12B brain and a 12.5 GB VRAM clamp.
4. **The honesty layer as a first-class constraint** — abstention, taint, and the output supervisor are absent from the research systems.

## Types of reasoning — the second pass

Two more searches (taxonomy/types; specific forms). The map, by reasoning type:

| Type | Closest work | What it offers us |
|---|---|---|
| **Deduction / abduction / induction (mixed)** | **LOGIDYNAMICS** (EMNLP 2025) — how LLMs actually *mix* the three inference types in one reasoning trace | Informs the routing question: which steps belong to LISP (formal) vs the LLM (abductive) vs induction (pattern). Read before Phase 3. |
| **Typed thinking** | **TypedThinker** (ICLR 2025) — diversifying LLM reasoning with *typed* thinking | **Convergence warning:** someone else is explicitly *typing* reasoning steps — our "label the kind of reasoning every conclusion came from" idea. Validates it and shortens the window. |
| **Abduction** | **Wiring the 'Why'** (arXiv:2604.08016) — unified taxonomy of abductive reasoning in LLMs | The framing for the abduction half; where "best explanation, marked as deduced" sits. |
| **Analogical** | **LLMs as models for analogical reasoning** (ScienceDirect 2025) | The row we parked — LLMs do analogy parametrically; this is the current state of the art on whether it's reliable. Read before deciding whether analogical gets a verification path. |
| **Causal + planning** | **Psychologically grounded causal reasoning for planning under uncertainty** (PMC) | The causal row — augmenting LLMs with causal *models* (not just causal text). Informs whether WO-22 (means-ends) can carry a causal layer. |
| **KG reasoning + refinement** | **CoG: Controllable Graph Reasoning** (ACL 2026) — relational blueprints + failure-aware refinement over KGs | The KG as reasoning substrate with *failure-aware* refinement — maps to the curiosity loop's investigate-and-revise cycle (WO-21). |
| **Dual-process planning** | **Brain-inspired agentic architecture for planning** (Nature Comms 2025) | The System 1/System 2 integration for planning — directly relevant to the concert model and WO-22. |
| **Planning + memory** | **PRIME: Planning and Retrieval-Integrated Memory** (AAAI) | RAG + planning — the means-ends rung's memory integration pattern. |

**The convergence that matters most here:** TypedThinker is doing *typed thinking* — explicitly labeling reasoning by type — which is the same idea as our "she labels the kind of reasoning every conclusion came from." That's the second independent convergence (after SymStep/NSF-CoT/LogicTrack on step verification). The field is converging on *typed, verified, traced* reasoning from multiple directions at once. Our durable edge remains what it was: signed intermediates, the INFERRED tier with supersession, and local companion deployment — the *accountability* layer, not the reasoning pattern itself.

## Action items

1. **Read SymStep and LogicTrack in full** before Phase 3 (the LLM protocol) — they're the two closest to the step-validation and trace-schema designs, and may save a design iteration. Add **LOGIDYNAMICS** for the LISP-vs-LLM routing question and **TypedThinker** for the typed-thinking convergence.
2. **Read HypoAgent** before WO-21 (curiosity loop) — its KG-hypothesis loop is the closest existing thing to the gap→hypothesize→verify cycle.
3. **Cite the convergence in the capability doc** — "three independent 2026 groups (SymStep, NSF-CoT, LogicTrack) are building adjacent verified-reasoning systems; Lucca's differentiators are signed intermediates, the INFERRED tier, and local deployment." Strengthens the related-work position.
4. **Watch the window** — the convergence means the "verified reasoning" claim has a shelf life. The signed-provenance and local-companion differentiators are the durable ones; the step-validation pattern will be commodity within a year.
