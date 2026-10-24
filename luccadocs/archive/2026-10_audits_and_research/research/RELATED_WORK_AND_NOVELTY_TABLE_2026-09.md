# Project Lucca — Related Work & Novelty Table

**Prepared:** 2026-09-25 (by Claude, from `T0_citation_audit.md`, `12_prior_art_survey.md`, and web searches run in one conversation)
**Purpose:** Replace "nobody has done this" with a checkable map of neighbors and differences.
**Read this first:** Most rows below rest on abstracts or search snippets, not full-text reads. A failed search is weak evidence of absence. Nothing here shows Lucca works in real use; the induction loop has zero production rows.

> **Companion document:** [`LUCCA_POSITION_AND_TRAJECTORY_2026-09.md`](./LUCCA_POSITION_AND_TRAJECTORY_2026-09.md) — position assessment and research trajectory. This table supplies the per-claim neighbor map that document's §2.3 scorecard summarizes.

## Basis legend

| Tag | Meaning |
|---|---|
| **T0** | Checked by the T0 audit against source text or live lookup. The auditor is an AI (Gemini); human review was still pending. |
| **Survey-A** | Marked verified in the 2026-09-17 survey. Not re-checked. |
| **Survey-R** | Recalled from training data in the survey. Unverified. |
| **Snippet** | Abstract or search snippet read on 2026-09-25. Full text not read. |
| **ID?** | Identifier not retained. Look up before citing. |

## 1. Claim-by-claim comparison

### 1.1 Provenance-typed memory; agent's own speech as non-evidence

| | |
|---|---|
| **Lucca (per docs)** | Signer-per-tier provenance, DB-level trigger, `ASSISTANT_UTTERANCE` (`memory_eligible=1`, `grounding_eligible=0`), `ASSISTANT_ACTION` receipts, `COHERENCE_BREACH` (D-AUD-09, D-MEM-04). |
| **Neighbors** | **MEMIR** (arXiv 2605.25869): typed memory representation that makes source monitoring structural. **MemLineage** (ID?, May 2026): cryptographic provenance and derivation lineage per entry. **Memward** (ID?): gates untrusted memories out of decisions. **SuperLocalMemory** (arXiv 2608.08253): local-first, provenance on every fact. Security guidance against re-ingesting model output as trusted memory (source not retained). |
| **Possible difference** | Strictest stance found: no path for the model's own speech to count as evidence, enforced at the database; claimed-action-without-receipt detection. |
| **Open questions** | Does MEMIR or MemLineage define a non-grounding class for the agent's own utterances? Does any neighbor detect claims with no receipt? |
| **Basis** | Snippet |

### 1.2 Verified skill acquisition with a human gate

| | |
|---|---|
| **Lucca (per docs)** | Induction from history (N≥3), Z3 checks (satisfiable, non-tautology, deontic path/tool invariants), QUARANTINE, ≥5 shadow clusters, human promotion (D-REAS-06/07). |
| **Neighbors** | **VASO** (arXiv 2606.05395): model-checked LLM skill contracts, counterexamples feed skill updates; robotics. **ANNEAL** (arXiv 2605.16309): governed symbolic patches with guardrails, canary, provenance, rollback; fast/deliberate/verify-before-act arbitration. **Pel** (2505.13453), **LLM+AL** (2501.00830), **DecoVer** (ID?) — all in T0. **AGEL-Comp** (ID?): online rule learning with planner/verifier split. |
| **Possible difference** | Personal local companion; human approval step; Z3 over rule preconditions and path invariants (narrower than temporal-spec model checking). |
| **Open questions** | Does ANNEAL's promotion gate include human approval? Does any neighbor pair induction over one user's own history with SMT checks? |
| **Basis** | T0 (Pel, LLM+AL, DecoVer); Snippet (rest) |

### 1.3 Constrained Lisp as the boundary between LLM and actions

| | |
|---|---|
| **Lucca (per docs)** | MicroScheme: pure State→Plan, 1,000 gas, depth 16, 256 nodes, typed accessors, bounded macros. Rules are exposed back to the LLM as tools. |
| **Neighbors** | **PtcRunner** (Hex package, Elixir): "Safe Lisp DSL," no side effects, bounded iteration; the LLM writes programs per turn. **Pel** (T0). **APEX Spec** (Rust crate): deterministic DSL for agent planning and validation. **amla-sandbox**: capability-enforced WASM sandbox (adjacent). |
| **Possible difference** | Rules are authored or induced, verified once, then called by the LLM; the data flow is the reverse of PtcRunner's. |
| **Open questions** | None on precedent: the pattern is established. Lucca's claim is the surrounding lifecycle, not the language. |
| **Basis** | T0 (Pel); Snippet (rest) |

### 1.4 E-graph library learning

| | |
|---|---|
| **Lucca (per docs)** | First-order syntactic anti-unification (LGG) over an e-graph representation, Stitch-style compression metric (D-REAS-08). 0 production rows. |
| **Neighbors** | **Babble** (arXiv 2212.04596, POPL 2023), **Stitch** (Bowers et al., POPL 2023), **E-Stitch** (EGRAPHS 2026, tentative), **LILO** (Grand et al., 2023), **DreamCoder** (Ellis et al.). |
| **Possible difference** | Applied to a live agent's own tool-call history. Per the docs, no equational theory is supplied, so this is closer to LGG plus compression than to full Babble. |
| **Open questions** | Any prior use of e-graph anti-unification on agent traces? Not found; search was shallow. |
| **Basis** | Snippet; Survey-R (DreamCoder) |

### 1.5 Belnap FOUR evidence fusion for grounding and abstention

| | |
|---|---|
| **Lucca (per docs)** | 8-substrate cascade, Belnap bilattice, honest abstention (D-CASC-01). |
| **Neighbors** | None found applying it as evidence fusion in front of an LLM (shallow search). Belnap (1977) is classic. Z3-based output checkers (NSVIF, arXiv 2601.17789; VeriCoT, 2511.04662) are adjacent. |
| **Open questions** | Paraconsistent or four-valued logic in RAG or hallucination-control literature not searched. |
| **Basis** | Not verified |

### 1.6 PAD affect for tone and cadence; KV-cache-safe design

| | |
|---|---|
| **Lucca (per docs)** | Closed-form PAD update, gain clamped below the slowest damping rate, Schmitt-trigger quantization to stance tokens at the prompt suffix, arousal→Kokoro rate, affect has zero evidential weight (D-AFF-01). 8.58× prefill speedup reported. |
| **Neighbors** | **Rabiee, Kim, Lee**, Interspeech 2019: PAD-conditioned TTS. **PAD+ AI** (PyPI): PAD-based emotion layer for any LLM, with memory. **PsychoAgent** (2608.07438, T0). **ZifaMem** (2607.17564). **DAM-LLM** (2510.27418). **Aura**: emotion state machine. |
| **Possible difference** | Cache-safe quantization, stability clamp, and the epistemic quarantine rule. No neighbor found that addresses prefix-cache invalidation. |
| **Open questions** | WASABI / Becker-Asano is cited in Lucca advocacy but appears in neither T0 nor the survey. Verify before citing. |
| **Basis** | T0 (PsychoAgent); Snippet (rest) |

### 1.7 Sandboxed, schema-gated tool execution

| | |
|---|---|
| **Lucca (per docs)** | Docker/WSL2, no host fallback, Pydantic argument schemas, risk classes, taint gating, egress filtering, shell ban. |
| **Neighbors** | **OpenHands**, **E2B** (Survey-A); **amla-sandbox** (Snippet); Vellum's separate credential process (Snippet). |
| **Open questions** | Comparative strictness of governance inside each sandbox not checked. |
| **Basis** | Survey-A / Snippet |

### 1.8 Not searched

Streaming speech-output supervision (D-SUP-01), pre-narration sanity checks (D-META-01), and counterfactual shadow sampling of live rule hits (TICKET-REAS-001). No claim made either way.

## 2. Design lineage (T0-audited)

Eight core preprints (September 2026) were checked against local PDFs. Others were checked by lookup.

| Source | ID | Used for |
|---|---|---|
| EvoSkill-GUI | 2609.17653 | Metadata retrieval (12/12 vs 1/12), isolated critic |
| ModularRSI | 2609.14857 | Contrastive shadow analysis |
| Dream-RSI | 2609.14858 | Replay-before-live |
| XConf | 2609.17708 | Non-parametric Recall; self-labeled banks fail; verbalized Reflect fails below ~27B |
| When2Think | 2609.19671 | Difficulty-aware thinking (analogy) |
| AREX-Skill | 2609.02749 | Skill package format |
| The Last AI Built by Humans | 2609.11873 | RSI ladder |
| Library Drift | 2605.19576 | Skill retirement / 30-rule cap |
| Rethinking Skill Evolution | 2608.02636 | Conservative promotion |
| Selective Conformal Risk Control | 2512.12844 | Abstention |
| Q-Evolve, PANDO | 2603.04419, 2605.24785 | Analogy |
| DAMM, Vera | no paper ID | Inspiration only |

T0 flagged and corrected six wrong identifiers and one ghost citation (2609.13770).

## 3. Deployed local companions and assistants

| Project | What it ships (per its own README/listing) | Basis |
|---|---|---|
| Open-LLM-VTuber, AIRI, Neuro, Amica | Local voice + avatar companions (survey: memory has no provenance) | Survey-A |
| Local AI Companion (LiiLk) | VAD → Whisper → LLM → Kokoro → RVC, Live2D, bounded conversation memory | Snippet |
| Dunoon Daemon | Windows, llama.cpp, personas, memory, multi-character Arena | Snippet |
| Aura (Android) | Long-term memory, emotion state machine, relationship model, MCP | Snippet |
| Operit (Android) | Tool calling, workflows, embedded Ubuntu 24, memory, voice | Snippet |
| Vellum, Goose, Open Interpreter | General local assistants; Vellum separates credentials from the model | Snippet |

None advertised provenance-typed memory, formal rule verification, or a non-grounding class for their own speech. Capability and reliability were **not** tested against any of them.

## 4. Verification to-do before public use

1. Look up IDs for MemLineage, Memward, AGEL-Comp, DecoVer; read MEMIR, MemLineage, and ANNEAL in full.
2. Fill `docs/12a_prior_art_verification.md` for every `Survey-R` row you rely on (Soar, ACT-R, Voyager, Reflexion, DreamCoder).
3. Verify WASABI / Becker-Asano or drop it.
4. Search the areas in §1.5 and §1.8.
5. Get a human review of T0.

## 5. Wording that survives a counterexample

1. **Safe:** "I have not found another local voice companion that combines provenance-gated memory, a non-grounding class for the agent's own speech, verified skill induction with human promotion, and Belnap-fused abstention. Pairs of these ideas appear in recent research (MEMIR, MemLineage, VASO, ANNEAL)."
2. **Safe, with evidence:** "The design is grounded in an audited research base (19 sources, six identifier errors corrected)."
3. **Say up front:** "The induction loop has zero production rows; the evidence so far is internal test batteries."
4. **Avoid:** "unprecedented," "the only system," "no one has combined."