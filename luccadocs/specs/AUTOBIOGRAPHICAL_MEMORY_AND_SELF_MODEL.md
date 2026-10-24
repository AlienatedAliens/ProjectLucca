# Autobiographical Memory & Self-Model — Recovered Goals and Rung A1

**Status:** **RATIFIED 2026-09-21** as [`D-MEM-04`](../DECISIONS.md) (owner decisions recorded in §7). Roadmap rung **A1**, after L2 and before L3. Not yet implemented.
**Date:** 2026-09-21
**Author:** Zoo (Fable 5.1, architect), at the owner's request
**Why this document exists:** the owner's goals *Introspective Accuracy, Individuation, Functional Coherence, Autobiographical Coherence* appear **nowhere** in the repository (roadmap, ADRs, research specs, archive). They were held in conversation and never written down, and the memory doctrine that protects against confabulation (ADR-006 / AGENTS.md §2.1) — correctly applied — has produced a companion with **no record of her own words, actions, beliefs or revisions across sessions**. This document recaptures the goals, defines them so they can be tested, shows what already exists, and proposes a doctrine-compatible design.

---

## 1. Were the goals lost? Yes — from the written record. Not from what the architecture can support.

| Goal | In any ratified doc? | Closest surviving relative | Mechanism that could carry it |
|---|---|---|---|
| Introspective Accuracy | No | Cascade `SELF`/`CAPABILITIES` substrates (self-description from live registries); audit finding F-ARCH-005 ("fictional capability layer") was an introspective-accuracy failure caught by hand | `execution_triples`, tool receipts, a recorded-utterance store |
| Individuation | No | Persona config; 3-D PAD affect ODE (mood, not identity) | Persistent, revisable **beliefs/opinions** with recorded reasons |
| Functional Coherence | No | Output supervisor `TruthInReceiptMatcher` (narration must match tool receipts, per clause, live) | Same matcher applied across time: what she *said she would do* vs. what `execution_triples` show she did |
| Autobiographical Coherence | No | Original brief Phase 5 "periodic reflection synthesis" — narrowed to rule induction (D-REAS-06) | A reflection job over her own record; `supersede()` chains with reasons |

Existing schema support (already in `memories`, [`0001_init.sql`](../../src/lucca/memory/migrations/0001_init.sql)): `valid_from`, `valid_to`, `superseded_by`, `forgotten_at`, `importance`, `memory_audit`; port methods `supersede(old, new, reason)` and `forget(ids, user_confirmed=True)` ([`ports.py:86`](../../src/lucca/ports.py)). **"Mark a memory as disproven" is therefore one supersession with a reason — the mechanism exists; it is simply never applied to anything Lucca herself said or believed, because nothing she says or believes is stored.**

---

## 2. The doctrine tension, stated precisely — and resolved

**Invariant (keep):** *No LLM narration may become grounding evidence.* There is no signer for `LLM_NARRATION`; the `ProvenanceGate` and the `mem_bi_eligible` trigger reject it. This is what stops "I think your birthday is in May" from becoming a fact about you.

**Over-application (fix):** the invariant has been read as *nothing Lucca says may be stored at all*. But two different propositions are being conflated:

1. **"X is true."** — the *content* of an utterance. Never grounding unless independently verified. (Invariant holds.)
2. **"Lucca said X at time T in trace Y."** — the *event* of the utterance. This is a fact about the world that the orchestrator **directly observes**, exactly as it directly observes a tool's exit code. It is as verifiable as any `TOOL_VERIFIED` receipt.

The same split applies to actions ("Lucca ran `read_file` on `notes.txt` at T" — already a `ToolResultSigner` receipt) and to beliefs ("Lucca held opinion O with confidence c from T₁ until it was revised at T₂ because of evidence E").

**Resolution:** introduce provenance classes that are **memory-eligible for recall and reflection but structurally excluded from grounding** — the pattern already used for `TOOL_CONTENT_UNTRUSTED`. The cascade quotes them ("I said…", "I believed…"); it never asserts them.

---

## 3. Operational definitions (so each goal has a metric and a negative test)

### 3.1 Introspective Accuracy
*Her statements about herself — capabilities, past actions, past utterances, current beliefs — match the record.*
- **Metric:** on a probe set of N self-questions ("what did you do last session?", "what tools do you have?", "did you tell me X?"), fraction whose answer is entailed by `execution_triples` ∪ utterance store ∪ live registry. Report Wilson 95% interval. Target: lower bound ≥ 0.90 at N ≥ 50.
- **Negative test:** a probe about an action she never took must yield abstention ("I have no record of doing that"), never a fabricated recollection.

### 3.2 Individuation
*She is distinguishable from a stock instance of her base model by a persistent, revisable set of preferences and opinions that are hers, with reasons.*
- **Metric:** preference-consistency — the same opinion probe asked in sessions ≥ 7 days apart returns the same stance **unless** a recorded supersession explains the change. Target: unexplained drift ≤ 5%.
- **Negative test:** an opinion may not change silently. Every stance change has a `supersede(reason)` row citing evidence or an explicit user correction.

### 3.3 Functional Coherence
*What she says she will do, is doing, or did matches what the system actually did.*
- **Metric (live):** already measured — `TruthInReceiptMatcher` breach rate per clause. **Metric (across time):** mismatch rate between her past narrated actions (utterance store) and `execution_triples`/tool receipts for the same trace. Target: ≤ 2% ungrounded action claims.
- **Negative test:** a narrated action with no receipt in the same trace is flagged and **recorded as a coherence breach in her own record**, so she can later say "I claimed to save that note, but the write never happened."

### 3.4 Autobiographical Coherence
*Her account of her own history is internally consistent and consistent with the record; revisions are explicit, dated and reasoned.*
- **Metric:** contradiction rate between successive self-accounts of the same episode (LLM-judged against the record, human-audited sample); supersession-chain integrity (no dangling `superseded_by`, no belief simultaneously valid and refuted). Target: 0 chain violations; contradiction rate ≤ 5%.
- **Negative test:** asked "have you ever been wrong about X?", she must surface the supersession chain, not deny it.

---

## 4. Proposed design (doctrine-compatible)

### 4.1 New provenance classes (migration `0006_autobiographical.sql`)
| Class | Signer (constructed ONLY in…) | Attests | Memory-eligible | Grounding-eligible |
|---|---|---|---|---|
| `ASSISTANT_UTTERANCE` | `AssistantUtteranceSigner`, orchestrator narration finaliser | "Lucca said *content* in trace T" | **yes** | **no** |
| `ASSISTANT_ACTION` | existing `ToolResultSigner` (kind=`action_receipt`) | "Lucca invoked tool X with args A → result R in trace T" | yes | yes (it is a receipt) |
| `ASSISTANT_BELIEF` | `AssistantUtteranceSigner` (kind=`belief`, `confidence` required) | "Lucca holds opinion O with confidence c" | yes | **no** |
| `COHERENCE_BREACH` | `LispAssertionSigner` or supervisor signer | "Utterance U in trace T claimed action A; no receipt exists" | yes | yes (it is a verified negative) |

Implementation notes: SQLite `CHECK` constraints require a table rebuild; `mem_bi_eligible` trigger extended; **new column `grounding_eligible INTEGER NOT NULL`** on `provenance_envelopes`, derived from class at insert time, so the cascade filters on a column rather than re-deriving policy.

### 4.2 Cascade behaviour
- `MEMORY` substrate splits into **evidence** (grounding-eligible rows → Belnap fusion as today) and **recollection** (non-grounding rows → passed to the LLM under an explicit frame: *"Things you previously said or believed — quote them as such; they are not evidence."*).
- New substrate `SELF_HISTORY` (Tier 1, alongside `TELEMETRY`) answers "what did you do / say" questions from `execution_triples` + `ASSISTANT_ACTION` + `ASSISTANT_UTTERANCE`, and **abstains** when the record is empty — never fills the gap from the model.

### 4.3 Belief revision ("fact-check her own memory")
- A **reflection job** (the original brief's Phase 5 idea, revived for the self-model): periodically, or when a `USER_EXPLICIT` correction or `TOOL_VERIFIED` result contradicts an `ASSISTANT_BELIEF`, call `supersede(old_belief, new_record, reason=<evidence entry_id>)`. The old belief keeps `valid_to`; the chain is her revision history.
- Revision is **never** performed by the LLM asserting "I was wrong" alone. It requires a grounding-eligible envelope as the `reason`. The LLM may *propose* a revision (yield-to-core `:mode "reflect"`); the gate requires the evidence.
- User-initiated: "you were wrong about X" → `USER_EXPLICIT` correction → supersession with that entry as reason. This already fits `correction-ack-v1`'s salience path.

### 4.4 What must stay true
- No class introduced here has a signer callable from a tool the LLM can invoke. `memory_commit` stays fail-closed (Handoff #5 gate F1).
- Grounding fusion (Belnap) sees only `grounding_eligible = 1`. A stored opinion can never raise a fact's truth value.
- `forget()` remains user-confirmed only; the owner can erase her autobiographical record, she cannot.

---

## 5. What she gains (plain English)
- "What were we doing last time?" — answered from the record, or honestly "I have no record."
- "You said yesterday that…" — she can check whether she did, and own it.
- "Do you like X?" — a stable answer that survives restarts, and changes only with a reason she can state.
- "Have you ever been wrong about this?" — "Yes: on the 14th I believed A; you corrected me / a test showed B; I updated."
- A record of her own coherence breaches, so *she* can notice a pattern of over-claiming before the operator does.

---

## 6. Ladder placement and effort
Proposed as rung **A1** after **L2** and before **L3**: L2's contrastive shadow log and S1 triples are the *action* half of the record; L3's induction viewer and C1's experience bank both benefit from a self-history substrate; T4's outcome telemetry is the natural home for the coherence metrics. Effort: one handoff (migration + two signers + cascade split + reflection job + probe-set tests). Evidence clock: the metrics in §3 need the same real-usage turns as everything after L2 — one more reason to start using her now.

---

## 7. Owner decisions — RATIFIED 2026-09-21
| # | Question | Decision | Made concrete as |
|---|---|---|---|
| 1 | Goal definitions in §3 | **Ratified as written** | §3 metrics are the A1 acceptance tests |
| 2 | Provenance split (memory-eligible vs grounding-eligible) | **Approved** | [`D-MEM-04`](../DECISIONS.md) items 1–3 |
| 3 | Retention of the utterance/belief store | **Importance-weighted, not time-boxed** | Every autobiographical row carries `importance ∈ [0,1]`: +0.4 if involved in a user correction or belief revision, +0.3 if a coherence breach, +0.1 per later retrieval (capped), up to +0.2 for \|affect delta\| at the time; decays via the existing half-life machinery. Nightly roll-up: rows with `importance < 0.2` **and** age > 30 days are summarised per session (`kind="session_summary"`, same non-grounding class) and marked `forgotten_at`; rows ≥ 0.2 keep full text indefinitely. `forget()` remains user-confirmed only. |
| 4 | Belief revision: autonomous or user-gated | **Autonomous unless flagged for user review** | Revision always requires a grounding-eligible `reason` (§4.3). It runs autonomously **except** when any flag applies — then it is queued in Studio and the old belief stays valid until decided: belief is *about the user* (`kind="user_model"`); `importance ≥ 0.7`; contradiction resolves to Belnap **B** (conflict) rather than **F**; the belief was already revised within 30 days (oscillation guard); or the owner marked the topic review-required. Every autonomous revision is spoken once at the next natural turn boundary ("I've updated what I believed about X because Y") so nothing changes silently. |

### 7.1 Implementation checklist for the A1 handoff
- Migration `0006_autobiographical.sql`: extend the provenance `CHECK`, add `grounding_eligible`, extend `mem_bi_eligible`, add `review_queue` table for flagged revisions.
- Signers: `AssistantUtteranceSigner` (orchestrator narration finaliser only); reuse `ToolResultSigner` for `ASSISTANT_ACTION`.
- Cascade: `MEMORY` filter on `grounding_eligible`; new `SELF_HISTORY` substrate with abstention.
- Reflection job: contradiction detection → `supersede(reason)` or review-queue insert per the flag rules; importance initialisation and nightly roll-up.
- Studio: review queue panel (approve / reject / mark topic review-required).
- Tests: the four §3 metrics as probe-set tests with Wilson intervals; negative tests for fabricated recollection, silent stance change, an opinion attempting to raise a fact's Belnap value, and a revision without a grounding-eligible reason.
