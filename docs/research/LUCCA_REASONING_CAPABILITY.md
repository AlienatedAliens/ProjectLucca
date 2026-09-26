# Lucca's Reasoning Capability — What We're Building and Why It's Different

**Date:** 2026-09-26
**Status:** WO-20 in flight (Phase 0 complete; Phases 1–5 ratified)

---

## The one-paragraph version

Most AI reasons in one of two ways: a big language model that thinks fluently but can't prove anything, or a rigid rule engine that's verifiable but can't really think. Lucca is being built to do both *at once* — a small local language model that **proposes** reasoning steps, and a symbolic LISP engine that **validates and signs** every step, so that every conclusion she reaches comes with a **cryptographic proof of how she got there**. Not "trust me" — "here's the derivation, check it."

## How it functions (the concert loop)

```mermaid
flowchart LR
    A[Your question] --> B[LISP gathers signed facts<br/>from provenance-gated memory]
    B --> C[LLM proposes an<br/>inference step]
    C --> D{LISP validates:<br/>premises real? rule Z3-verified?}
    D -- valid --> E[Step signed as<br/>LISP_ASSERTION intermediate]
    E --> C
    D -- invalid --> F[Rejected with reason;<br/>model revises or abstains]
    E --> G[Conclusion commits as INFERRED<br/>with full proof trace]
    G --> H[Direct evidence can<br/>supersede it later]
```

1. **Evidence first.** Every chain starts from *signed* facts — your words, tool receipts, verified extractions. Never from the model's imagination.
2. **The LLM proposes.** It generates an inference step (premises → conclusion, with confidence) — the creative, abductive part.
3. **LISP disposes.** The symbolic layer checks the premises against the signed store and the rule against Z3. Valid → signed. Invalid → rejected with a machine-readable reason.
4. **Chain to a conclusion.** Steps accumulate as signed intermediates until the chain completes (bounded: depth 8, gas-limited).
5. **The conclusion carries its proof.** It commits to memory as `INFERRED` — marked as a deduction, with confidence, with the full trace — and *direct evidence can overrule it later*.

## How it compares

| Capability | Frontier LLMs (Claude/GPT) | Agent frameworks (LangGraph) | Companions (Replika/VTubers) | **Lucca (WO-20)** |
|---|---|---|---|---|
| Multi-step reasoning | Yes, unverified | Yes, unverified | No | **Yes, every step signed** |
| Can prove its reasoning | No | No | No | **Yes — proof traces** |
| Memory that separates fact from opinion | No | No | No | **Yes — provenance-gated** |
| Learns from you over time | No (resets) | Partial | Persona only | **Yes — quarantined, human-approved** |
| Runs locally, no cloud | No | Partial | Some | **Yes — fully local** |
| Abstains instead of guessing | Sometimes | No | No | **Yes — by construction** |
| Raw per-turn intelligence | **Highest** | Medium | Low | 12B (swappable) |

**The honest trade-off:** a frontier model out-reasons her per-turn on open-ended problems — permanently, at 12B. Her wins are depth-over-time, verifiability, and accountability: she *remembers*, *proves*, and *improves with you*, locally. The field optimizes for capability; Lucca optimizes for being *checkable*.

## The types of reasoning — what she can and can't do

| Form | What it is | She can now | After WO-20 |
|---|---|---|---|
| **Deduction** | General → specific; *certain* (A→B, A ⊢ B) | Single-step only (one rule firing) | **Multi-step chains, every step Z3-verified and signed** |
| **Abduction** | Best explanation from evidence (judge + UTC+8 → Philippines) | Yes, but *uncommittable* — evaporates at turn end | **Committable as `INFERRED` with proof trace; direct evidence can supersede** |
| **Induction** | Specific → general; pattern learning (5 similar searches → a habit) | Pipeline exists; 0 production clusters so far | Same — needs your recurring habits to fire |
| **Epistemic** | Reasoning about what's known/unknown (Belnap T/F/B/⊥) | **Yes — genuinely strong** (the cascade) | Unchanged — already her best suit |
| **Counterfactual** | "What would have happened if…" | Partially — shadow replay of rules | Unchanged |
| **Common-sense** | Tacit world knowledge (drop bears are folklore) | Yes — LLM parametric, unverified | Unverified steps get *marked* as deduced, not asserted as fact |
| **Analogical** | Mapping structure across domains | LLM can attempt it; no verification path | Still no verification path — parked |
| **Means-ends / planning** | Reasoning about action sequences to goals | Not yet | WO-22 (planned) |
| **Causal** | X *causes* Y (vs correlation) | **No *verified* causal reasoning over external facts** — an active research field, not a solved one | Narrow exception: her *own* receipts are interventional records, so she can reason causally about *her own actions* |

**The key distinction the concert layer draws:** deduction and abduction are both *enabled*, but they're treated differently by the honesty layer. Deductive conclusions (provable from verified rules) commit as facts. Abductive conclusions (best-guess explanations) commit as `INFERRED` — *marked* as deductions with confidence, never laundered into certainty, and always overruled by direct evidence later. She doesn't just reason; she *labels the kind of reasoning* every conclusion came from.

## The reasoning ladder (where this sits)

| Rung | What it is | Status |
|---|---|---|
| Verified memory | Signed, tiered facts; fact separated from opinion | **Live** |
| Epistemic cascade | Belnap four-valued evidence fusion; honest abstention | **Live** |
| Single-step rules | Verified condition→action reflexes | **Live** |
| **Concert layer** | Multi-step deduction + committable abduction, proof-traced | **WO-20 (building)** |
| Curiosity loop | Notices knowledge gaps, investigates, learns | WO-21 (planned) |
| Means-ends planning | Reasoning about action sequences to goals | WO-22 (planned) |

## The one-sentence version

Every other AI asks you to trust its reasoning; Lucca is being built to *show* it — every step signed, every premise checked, every conclusion replayable, and every deduction marked as a deduction until direct evidence confirms it.
