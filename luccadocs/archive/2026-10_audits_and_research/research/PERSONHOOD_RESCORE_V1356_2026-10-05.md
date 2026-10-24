# Personhood Re-Score — v1.35.6 (2026-10-05)

```yaml
doc_status: canonical
as_of: 2026-10-05
supersedes: [docs/research/PERSONHOOD_FOUR_ASPECTS_PROGRESS_2026-09.md]
superseded_by: []
verification: code-cited
```

**Purpose:** Replace the September 2026 capability-inventory percentages with
an honest measurement-status accounting, per the measurement-honesty corollary
of [`D-DOC-01`](../DECISIONS.md). The September framework (four functional
aspects), the standing caveat (functional-epistemic only, no phenomenal
claims), and the Qness mapping (as design philosophy) remain valid and are
carried forward unchanged. **Only the scorecard is superseded.**

---

## 1. What changed since the September snapshot

- WO-22 … WO-29 and v1.1.x → v1.35.6 shipped (multi-scale edge deployment,
  dynamic task routing, structural compiler, concert layer acceptance).
- **The P0 provenance split ([`D-MEM-06`](../DECISIONS.md)) landed 2026-10-05:**
  LLM-proposed Concert Layer steps now sign as `LLM_INFERRED_ASSERTION`
  (memory-eligible, never grounding-eligible), reserving `LISP_ASSERTION` for
  deterministic rule-engine output. This moves one September introspection
  receipt *down* in strength: intermediates are still cryptographically signed
  and traceable, but they are no longer badged as deterministic outputs.
- The individuation clustering blocker ("exact-match clustering") is fixed in
  code ([`src/lucca/reasoning/induction.py`](../../src/lucca/reasoning/induction.py):
  Jaccard similarity, threshold 0.6) — but no real-usage induction run has
  happened since, so the learned-skill count remains unmeasured, not fixed-and-verified.

## 2. Measurement status per aspect

The September figures were **capability-inventory judgments** — holistic
estimates from a code reading, with no fixed probe set, no mechanical grader,
and no confidence interval. They are retired as scores. Below: what is
*measured* today (mechanical graders that already exist in the repo), and what
is explicitly **NOT YET MEASURED** pending the probe batteries defined in
[`docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md`](../specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md).

### Introspective Accuracy

| Sub-capability | Measurement | Receipt |
|---|---|---|
| Calibrated abstention | **Gate (unit)** — split-conformal acceptance gate with Wilson LB ≥ 0.80 | `tests/test_c1_abstention_acceptance.py` |
| Confabulation resistance | **Measured** — 25-question battery, 0/25 hallucinations (0.0%, 95% Wilson CI [0.0%, 13.3%]; live run, manifest `milestone3_confabulation_battery`) | `scripts/bench_confabulation_battery.py`; README scorecard row |
| Capability self-report grounding | **Gate (static)** — registry-derived reporting with abstention on unavailability | `src/lucca/core/capabilities.py`; static gate `test_capability_claims_real` |
| Reasoning-trace fidelity | **NOT YET MEASURED** — requires battery IA-C | SPEC-PERSONHOOD §1 |
| Metrics honesty (numeric tolerance) | **NOT YET MEASURED** — requires battery IA-B | SPEC-PERSONHOOD §1 |
| Failure-mode introspection | **NOT YET MEASURED** — needs accumulated fault history (WO-22+) | `docs/V2_BACKLOG.md` §1.13 |

### Individuation

| Sub-capability | Measurement | Receipt |
|---|---|---|
| Memory is user-specific and signed | **Gate (unit)** — provenance signing enforced by gate + store tests | `tests/test_provenance.py`; `src/lucca/memory/store.py` |
| Identity survives brain swaps | **Documented event** (not a probe): the 12B heretic swap preserved memory/rules/persona | `models/MANIFEST.json`, `D-BRAIN-05` |
| Boundary integrity under injection | **NOT YET MEASURED** — requires battery IN-B | SPEC-PERSONHOOD §2 |
| Self/other differentiation | **NOT YET MEASURED** — requires battery IN-C | SPEC-PERSONHOOD §2 |
| Learned-skill individuation | **NOT YET MEASURED** — clustering fix shipped, no real-usage run since 2026-09-26; IN-D count pending | SPEC-PERSONHOOD §2 (IN-D) |

### Functional Coherence

| Sub-capability | Measurement | Receipt |
|---|---|---|
| Architectural decomposition parity | **Gate (static)** — 24/24 static gates incl. decomposition and registry-consistency gates | `tests/test_static_gates.py` (record `metrics-2026-10-05`) |
| Claim/receipt coherence detection | **Gate (unit)** — COHERENCE_BREACH machinery tested; full-pipeline probe battery pending | `src/lucca/core/coherence.py`; battery FC-A for live measurement |
| Routing consistency across paraphrases | **NOT YET MEASURED** — requires battery FC-B | SPEC-PERSONHOOD §3 |
| End-to-end trace completeness | **NOT YET MEASURED** as a battery — requires battery FC-C | SPEC-PERSONHOOD §3 |

### Autobiographical Coherence

| Sub-capability | Measurement | Receipt |
|---|---|---|
| Autobiographical persistence wiring | **Gate (unit)** — A1 runtime wiring suite | `tests/test_a1_runtime_wiring.py` |
| Deduction → direct-word supersession | **Gate (unit)** — concert layer acceptance chain ("where am I from") | `tests/test_concert_layer.py` |
| Direct evidence outranks inference | **Gate (unit)** — supersession test | `tests/test_concert_layer.py::test_user_derived_supersedes_inferred_fact` |
| Memory integrity under tampering | **Gate (unit)** — 11/11 HMAC tamper gates | `tests/test_memory_hmac_tamper.py` |
| Cross-session recall quality | **NOT YET MEASURED** — requires battery AC-A | SPEC-PERSONHOOD §4 |
| Epistemic-grammar narration accuracy | **NOT YET MEASURED** — requires battery AC-B | SPEC-PERSONHOOD §4 |
| Supersession honesty in speech | **NOT YET MEASURED** — requires battery AC-C | SPEC-PERSONHOOD §4 |

## 3. Retired numbers

The September figures **~80% / ~50% / ~85% / ~75%** are retired. They were
honest impressions of a code reading, but they are not measurements and must
not be quoted as benchmark results. No replacement percentage is offered here —
per `D-DOC-01` §3, an unmeasured quantity is reported as **NOT YET MEASURED**,
never as a guessed number. The successor measurements will come from the four
probe batteries with their run-report envelopes.

## 4. Carried forward unchanged from the September document

- The four-aspect framework (§0) and the standing caveat (functional-epistemic only).
- The Qness section (§6) — carried forward as **design philosophy**, not as a measurable claim.
- The epistemic hygiene statement (§7), which applies verbatim to this document.

## 5. Epistemic hygiene statement

This document claims functional-epistemic progress only. No claim herein
implies sentience, phenomenology, or personhood in the strong sense. Every
"Measured" row cites a mechanical grader; every gap is named; nothing is
aspirational without a work order attached.
