# WO-12 — Belief Model Completion Audit & turn_pipeline Extraction

**Date:** 2026-09-23 · **Status:** DRAFT FOR APPROVAL
**Provenance:** WO-11 closing audit (`luccadocs/audit/findings/WO11_CLOSING_AUDIT.md`) issued **GO for WO-12**. Spec: [`luccadocs/specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md`](../luccadocs/specs/AUTOBIOGRAPHICAL_MEMORY_AND_SELF_MODEL.md) (D-MEM-04).

---

## 0. Why this WO is a completion audit, not a greenfield build

Scoping review (2026-09-23) found most of D-MEM-04 already landed during WO-8/WO-9/A1 implementation, before this WO was formally opened:

| Spec item | Status | Evidence |
|---|---|---|
| §1 grounding_eligible flag on envelopes | ✅ Landed | [`schemas.py`](../src/lucca/core/schemas.py:376) `grounding_eligible: bool = True` |
| §2 provenance classes (UTTERANCE / BELIEF / ACTION / BREACH) + signers | ✅ Landed | [`signers.py`](../src/lucca/memory/signers.py) |
| §3 cascade split: evidence vs recollection under "quote — do not assert" frame | ✅ Landed | [`cascade.py:927-929`](../src/lucca/core/cascade.py:927) D-MEM-04 invariant comment |
| §4 belief revision + 5-flag review queue | ✅ Landed | [`reflection.py:28`](../src/lucca/memory/reflection.py), flags at :143-167 |
| §5 nightly importance-weighted rollup | ✅ Landed | [`reflection.py:338`](../src/lucca/memory/reflection.py) |
| Studio review-queue panel | ✅ Landed | [`settings_dialog.py:2619-2706`](../src/lucca/ui/settings_dialog.py) `list_review_queue` wiring |

**Remaining genuine gaps (this WO's actual scope):**
1. **§3 formal metric probes** — the spec defines four metrics (Introspective Accuracy, Individuation, Functional Coherence, Autobiographical Coherence) with Wilson-interval acceptance thresholds. The A1 battery exists, but the *formal* §3 probe-set acceptance tests (Wilson LB ≥ 0.90 @ N ≥ 50; drift ≤ 5%; ungrounded claims ≤ 2%; zero chain violations) are not wired as named acceptance gates.
2. **`turn_pipeline.py` full extraction** — deferred from WO-11 to land with D-MEM-04's commit-point restructure (spoiler: D-MEM-04 landed early, but the split was deliberately deferred; execute now while commit points are stable).
3. **G3 word-form digit narration research** (carried from WO-11 closing audit).
4. **Fault-mode-C sanity-check research** (carried from WO-11 closing audit).
5. **Spoken-one-time autonomous revision announcement** (spec §7 decision 4) — verify it fires (`_maybe_speak_pending_updates` exists in orchestrator but the "I've updated what I believed about X because Y" contract needs a live verification probe).

---

## PHASE 0 — WO-12.0: spec-conformance audit (0.5 day)

**Scope:** mechanically verify each "landed" row above against the spec's §7.1 checklist; produce a gap table rather than assuming completeness.

**Gate:** each checklist item mapped to (a) code path, (b) test path, (c) live evidence. Missing any leg → real finding, moved into a phase below.

**Milestone M0 — *Verified, not assumed.***

**Review R0:** gap table sign-off before proceeding.

---

## PHASE 1 — WO-12.1: formal §3 metric acceptance tests (1 day)

**Scope:** wrap the four spec metrics as named acceptance gates in the hw suite:
- Introspective Accuracy: Wilson LB ≥ 0.90 @ N ≥ 50 self-probes
- Individuation: unexplained stance drift ≤ 5%
- Functional Coherence: ungrounded action claims ≤ 2%
- Autobiographical Coherence: 0 supersession-chain violations; contradiction rate ≤ 5%

**Gate:** `tests/test_a1_acceptance_hw.py` runs the four named gates against the live brain; each prints its threshold verdict.

**Milestone M1 — *The spec's own definition of done, executable.***

**Review R1:** thresholds match spec text verbatim; negative tests included (fabricated recollection, silent drift, opinion-raising-fact, revision-without-grounding-reason).

---

## PHASE 2 — WO-12.2: `turn_pipeline.py` full extraction (2–3 days)

**Scope:** the full phase-based split deferred from WO-11.5's shared-method extraction — orchestrator becomes input adapters (`_run_turn`, `_run_text_turn` → unified `TurnInput`) over a single [`turn_pipeline.py`] with phases: normalization → rules/route → tier dispatch → epistemic context → LLM streaming+guards → finalize.

**Gate:** 606+ tests green; parity gate (WO-11.1) re-pointed at pipeline structure; ruff zero.

**Milestone M2 — *One turn path, file-level.***

**Review R2:** two-person-style diff review; parity gate negative test re-demonstrated post-split.

---

## PHASE 3 — WO-12.3: G3 word-form digit narration probe (0.5 day)

**Scope:** research probe — measure whether biasing computed-number narration to digits (vs words) reduces the digit-carry slips found in WO-10 (`math_06`, `multi_05`). Config-gated narration formatter flag.

**Gate:** before/after probe run on 10 arithmetic probes; digit-form variant adopted only if slip rate measurably drops.

**Milestone M3 — *Evidence-based narration format choice.***

**Review R3:** probe data attached to findings register G3 → closed or carried.

---

## PHASE 4 — WO-12.4: fault-mode-C sanity-check research (1 day)

**Scope:** deliberate investigation of `plausible_wrong` tool output handling — can the model cross-check tool results against parametric knowledge before asserting? Feeds future sanity-check guard design.

**Gate:** research note in `luccadocs/audit/findings/` with measured accept/flag rates across 10 plausible-wrong probes; design sketch for a sanity-check nudge if accepted-rate is high.

**Milestone M4 — *The hardest honesty boundary, measured.***

**Review R4:** research note + design proposal sign-off.

---

## PHASE 5 — WO-12.5: spoken-revision-announcement live verification (0.5 day)

**Scope:** live probe that autonomous revision announcements ("I've updated what I believed about X because Y") actually speak at the next turn boundary — spec §7 decision 4 requires no silent changes.

**Gate:** live hw probe passes; announcement text review.

**Milestone M5 — *No silent self-model changes, ever.***

**Review R5:** transcript evidence attached.

---

## PHASE 6 — WO-12.6: closing audit (1 day)

Same shape as WO-11.7: evidence bundle (all reviews, suite, battery, fault logs), findings register updated (G3/fault-C closed or carried), Go/No-Go for **WO-13 — Proactive Calibrated Meta-Cognition** (confidence tracking live), with full pipeline now extracted, is the next rung.

---

## Deferred Register

| Item | Deferred to | Reason |
|---|---|---|
| Proactive meta-cognition (proactive low-confidence flagging) | WO-13 | Needs the belief model confidence primitive measured and stabilized by this WO first |
| Persona-under-pressure probes | WO-13 | Same dependency |
| Long-session drift test | Monthly cadence | Not a release gate |

## Risk Register

| Risk | Mitigation |
|---|---|
| "Landed" items found hollow in Phase 0 audit | Each hollow item becomes its own real phase before Phase 2 |
| Pipeline split regresses turn behavior | 606-test suite + parity gate + A1 battery re-run in Phase 2 |
| §3 thresholds too strict for 12B (Wilson LB 0.90) | Thresholds are spec-text; if missed, the miss is a documented capability finding, not a gate tweak |

---
