# Reasoning Breadth Research Pass — 2026-09-26

**Purpose:** owner asked whether the WO-20 concert layer covers the full breadth of reasoning *types*, *methods*, and *outcomes* — or whether there are forms we haven't thought of. Four Nia research passes (taxonomy surveys, uncertainty calculi, computational argumentation, metacognition, legal/causal reasoning) plus prior-art grounding. This document maps the complete landscape against what Lucca has, and identifies what was missing from our taxonomy.

**Status:** research synthesis. Feeds the WO-21 spec (defeasible/source-conditioned reasoning + corroboration + standards of proof).

---

## 1. The Complete Reasoning Map

Legend: ✅ shipped · 🔨 in flight (WO-20) · 🕳️ gap we had identified · 🆕 **gap we had NOT identified**

### A. Truth-preserving (monotonic)

| Type | Lucca status |
|---|---|
| Deduction | 🔨 WO-20 Phases 1–2 (LISP forward-chaining, signed intermediates) |
| Calculation / exact inference | ✅ `calc_math` → TOOL_VERIFIED, grounding-eligible |
| Constraint solving (SAT/SMT) | ✅ Z3 verification of authored rules (D-REAS-07) |

### B. Non-monotonic / defeasible (conclusions retractable on new evidence)

| Method | What it is | Lucca status |
|---|---|---|
| Default logic (Reiter), circumscription (McCarthy), autoepistemic logic (Moore) | The classic 1980s trio: "conclude X unless evidence against" | 🕳️ partial — supersession + `conditions` give retraction, no formal semantics |
| Defeasible logic (Nute) | Directly implementable rule priorities + defeaters | 🕳️ closest formal match to the concert layer |
| **ASPIC+ structured argumentation** | Arguments built from premises/rules attack each other; acceptability computed | 🆕 **LLM-ASPIC+ (IOS Press, 2025/26) proves the neuro-symbolic version works with LLMs** — convergent with D-REAS-09 |
| Dung abstract argumentation | Arguments as nodes, attacks as edges, accepted-set semantics | 🆕 not modeled; our Belnap "both" is a 2-argument special case |
| Answer Set Programming | Non-monotonic logic programs; **LLMs-as-ASP-programmers (ACL 2026 Findings)** shows LLM→ASP with self-correction | 🆕 alternative substrate to MicroScheme for the defeasible layer |

### C. Uncertainty calculi (how to represent *degrees*)

| Calculus | What it adds over a raw float | Lucca status |
|---|---|---|
| Probability / Bayesian | — | 🔨 confidence float (un-banded, LLM-self-reported) |
| **Dempster–Shafer belief functions** | Belief/plausibility *interval*; explicit ignorance mass; Dempster's rule combines independent evidence | 🆕 Belnap "neither" ≈ DST ignorance; corroboration ≈ rule of combination (with known conflict caveats) |
| **Subjective logic (Jøsang)** | Opinion = (belief, disbelief, uncertainty, base rate); **trust-discount operator for source chains; fusion operators for corroboration** | 🆕 **best-fit calculus for source-conditioned claims** — "X asserts Y" is literally a trust-discounted opinion |
| Possibility theory / fuzzy | Vague predicates ("tall", "soon") | 🆕 not needed yet |
| Imprecise probabilities | Probability sets instead of points | 🆕 research-stage |

### D. Explanation-seeking

| Type | Lucca status |
|---|---|
| Abduction / inference to best explanation | 🔨 WO-20 Phase 3 (ratified: LLM proposes, LISP validates, gather ladder) |
| Diagnostic reasoning (abduction + fault models) | 🆕 natural fit for self-diagnostics — she already has `self_metrics`; reasoning *from symptoms to causes* about her own stack is unbuilt |
| Causal reasoning (Pearl's ladder: association → intervention → counterfactual) | 🕳️ known-hard rung; legal-BN literature (below) shows scenario-based approximations |

### E. Analogical & case-based

| Method | Lucca status |
|---|---|
| Structure mapping (Gentner) — relational analogy | 🆕 not built |
| **Case-based reasoning (retrieve → reuse → revise → retain)** | 🆕 **SELF_HISTORY + memory is a CBR substrate missing only the cycle** — "last time X happened I did Y and it worked" is companion gold |
| Precedent reasoning (legal CBR) | 🆕 same machinery, legal flavor |

### F. Practical reasoning (about action)

| Method | Lucca status |
|---|---|
| BDI (belief-desire-intention) | ✅ partial — `test_bdi_validator.py` exists |
| Means-ends planning | 🕳️ WO-22 candidate |
| **Satisficing / bounded rationality (Simon)** | ✅ **embodied without being named** — the three-tier architecture (REFLEX / ACT_THEN_NARRATE / FULL_LOOP) *is* bounded rationality: cheapest sufficient cognition first |
| Deontic reasoning (obligation/permission) | ✅ on the action side — deontic sandbox + deontic capitulation matcher |
| Moral reasoning | 🆕 persona boundaries only; no explicit moral machinery (arguably correct for a companion) |

### G. Meta-reasoning (reasoning about reasoning)

| Method | Lucca status |
|---|---|
| Metacognition: monitoring / control / evaluation of own reasoning | ✅ partial — D-META-01, confidence calibration, honest abstention |
| Reflective AI (2026 surveys: *Reflective Artificial Intelligence*; *Metacognition in LLMs*; Stanford's *Wise Machines*) | 🕳️ dogfooding/reflection backlog item |
| Meta-reasoning for LLMs survey (2026) | 🆕 formal monitor/control split we could adopt for the router |

### H. Social & dialectical

| Method | Lucca status |
|---|---|
| **Theory of mind** — modeling what the *user* knows/believes | 🆕 **companion-critical gap**: she should not explain what you know nor assume what you don't; user-modeling is unbuilt |
| Argumentation dialogue (Walton: inquiry, persuasion, deliberation dialogues) | 🔨 primitive — the named-gap question is an *inquiry dialogue* move; no dialogue model yet |
| Dialectical reasoning (thesis → antithesis → synthesis) | 🆕 could be a prompt-level pattern over the concert layer |

### I. Reasoning-adjacent methods

| Method | Why it matters to Lucca |
|---|---|
| **Walton's argumentation schemes + critical questions** | 🆕 **the single most actionable find.** ~25 schemes (argument from authority, from sign, from analogy, from consequences, from precedent…), each shipped with *critical questions* that are literally its defeaters. "Source X says Y" = argument from authority; its critical questions — *Is X credible? Is Y in X's domain? Do other authorities agree?* — are exactly the owner's corroboration idea, formalized decades ago. The concert layer can type abductive steps by scheme and auto-generate the checks. |
| Sensemaking (Pirolli–Card loop, Klein) | 🆕 corroboration is a sensemaking operation; frames the intelligence-analysis view of the gather ladder |
| Fast-and-frugal heuristics (Gigerenzer) | ✅ embodied — REFLEX tier is a fast-and-frugal tree |
| Inductive logic programming | ✅ D-REAS-06/08 induction pipeline is ILP-flavored |
| Markov logic / statistical relational learning | 🆕 weighted rules; possible future induction upgrade |
| Commonsense reasoning formalizations (JAIR survey) | 🆕 benchmark source for evaluation |

---

## 2. What We Hadn't Thought Of (the honest delta)

1. **Theory of mind / user modeling** — the biggest companion-relevant gap. She reasons about the world but not about *your* knowledge state.
2. **Case-based reasoning** — SELF_HISTORY is a case base; the retrieve-reuse-revise-retain cycle is unbuilt.
3. **Argumentation schemes with critical questions (Walton)** — gives the abductive layer *typed* steps with built-in defeaters instead of freeform InferenceSteps.
4. **Subjective logic** — a better calculus than raw confidence for source-conditioned claims; handles "X asserts Y" natively via trust discounting, and corroboration via fusion.
5. **Formal argumentation semantics (Dung/ASPIC+)** — our Belnap "both" handles pairwise contradiction; multi-argument attack graphs are the general case. LLM-ASPIC+ proves LLM-compatibility.
6. **Diagnostic reasoning** — she has the telemetry (`self_metrics`, traces) but no symptom→cause reasoning about herself.
7. **Dialectical/dialogue models** — the named-gap question is one move in what could be a full inquiry-dialogue protocol.
8. **ASP as an alternative defeasible substrate** — LLMs-as-ASP-programmers (ACL 2026) shows the pattern; MicroScheme remains our substrate, but ASP is the benchmark to compare against.

---

## 3. Deep Dives (the three most actionable)

### 3.1 Walton schemes → typed InferenceSteps
Instead of freeform abductive steps, Phase 3+ could type each step: `scheme: "authority" | "sign" | "analogy" | "consequence" | "precedent"`. Each scheme carries its critical questions, which the orchestrator turns into *checks*: authority → (source credible? in-domain? corroborated?); sign → (is the sign reliable? alternative explanations?); analogy → (relevant similarities? relevant differences?). This converts the corroboration pass from bespoke logic into a scheme-dispatch table — and every critical question a chain fails becomes a `condition` on the conclusion. Toulmin gave us the slots; Walton gives us the *content* of the rebuttal slot.

### 3.2 Subjective logic → source-conditioned confidence
Jøsang's opinion triangle (belief, disbelief, uncertainty, base rate) with two operators that are exactly our use cases:
- **Trust discounting**: "X asserts Y" where X has trust t → opinion about Y is X's opinion discounted by t. This is the formal version of "true only if the source is right."
- **Cumulative/belief fusion**: independent sources asserting Y combine; corroboration raises belief and shrinks uncertainty; dispute raises disbelief — *without* the false precision of multiplying probabilities.
Maps cleanly onto Belnap: high uncertainty ≈ "neither", belief ∧ disbelief both high ≈ "both". Candidate replacement for the raw `confidence` float in WO-21, or a derived view over it.

### 3.3 LLM-ASPIC+ → convergence evidence
LLM-ASPIC+ (IOS Press FAIA 2025/26) is a neuro-symbolic defeasible-reasoning framework where the LLM extracts arguments and ASPIC+ semantics compute acceptability — the same division of labor as D-REAS-09 (LLM proposes, symbolic layer validates). Independent convergence from the formal-argumentation community; their evaluation methodology (attack-graph benchmarks) is reusable for our Phase 5 acceptance tests.

---

## 4. What This Changes for WO-21

The WO-21 scope grows from "web ratification + corroboration" into the **defeasible reasoning rung**:

1. `conditions` on InferenceStep (already ratified as schema hook)
2. Corroboration engine — implement as **scheme-dispatched critical questions** (Walton), not bespoke counters
3. Confidence → **subjective-logic opinions** (or a banded view over confidence as v1, opinions as v2)
4. Standards-of-proof policy table (balance / clear-and-convincing / beyond-reasonable-doubt) as the consumer-side gate
5. Web fact ratification flow (user as trust root; whitelist as friction reducer)
6. **New:** theory-of-mind stub (track what the user has been told / has confirmed, to stop re-explaining) — cheap because SELF_HISTORY already records it
7. **New:** CBR stub (retrieve similar past episodes from SELF_HISTORY when a situation recurs)

Deferred deliberately: full Dung/ASPIC+ semantics (overkill until multi-argument conflicts are common), ASP substrate comparison (benchmark only), diagnostic self-reasoning (WO-22+), causal ladder (research rung).

---

## 5. Sources

**Taxonomy:** *The Periodic Table of LLM Reasoning* (arXiv 2606.11470, 2026); *Logical Formalizations of Commonsense Reasoning: A Survey* (JAIR); *Natural Language Reasoning: A Survey* (arXiv 2303.14725); *Evaluating Reasoning Systems* (NIST IR 7310); *Synergies Between Machine Learning and Reasoning* (Amel group).

**Uncertainty:** *Respecting evidence: belief functions not imprecise probabilities* (Synthese 2022); Shafer, *Perspectives on the Theory and Practice of Belief Functions*; Deneux, *Introduction to Belief Functions* (2023); *Representations of Uncertainty in AI: Beyond Probability and Possibility* (Springer); SEP, *Representations of Uncertain Inference*.

**Argumentation:** *LLM-ASPIC+: A Neuro-Symbolic Framework for Defeasible Reasoning* (IOS Press FAIA, doi:10.3233/faia250981); *LLMs as ASP Programmers: Self-Correction Enables Task-Agnostic Nonmonotonic Reasoning* (ACL 2026 Findings); `formal-argumentation` (PyPI v0.3.0); `patricker/argumentation` (GitHub); `argumentation` (crates.io); arXiv 2508.10976.

**Metacognition:** *A Systematic Review of Meta-Cognitive Approaches to AGI* (Springer 2026); *Reflective Artificial Intelligence* (Minds & Machines 2024); *Meta-Reasoning for Large Language Models: A Survey*; *Metacognition in LLMs* (arXiv 2607.11881); *Imagining and Building Wise Machines* (Stanford 2026).

**Legal/causal:** *Scenario-based Bayesian Networks for Legal Evidence* (AI & Law 2026); *Reasonable Doubt and Appellate Review Through Probabilistic Causal DAGs*; *A Causal Model Checker for Legal Cases* (Bologna); *Causal AI in Legal Language Processing* (MDPI Entropy); *Causal Models versus Reason Models in Bayesian Networks for Legal Evidence* (Synthese 2022).
