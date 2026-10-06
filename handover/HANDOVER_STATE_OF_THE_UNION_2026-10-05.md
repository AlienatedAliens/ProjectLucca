# Handover — State of the Union Document Authoring (2026-10-05)

```yaml
doc_status: canonical
as_of: 2026-10-05
supersedes: []
superseded_by: []
verification: code-cited
```

> **Correction banner (2026-10-06, post-audit; amended same day).** This
> handover was the *input brief* for the SotU. Its HumanEval figures are
> **sourced but protocol-specific**: 95.73% (157/164) is the zero-shot
> academic-harness run of 2026-09-28 (artifact in
> `logs/test_reports/v1.3/academic_benchmarks_20260928T182758Z.json`), and
> 91.46% (150/164) is the 2026-09-29 HumanEval-Plus run (artifact in
> `logs/test_reports/v1.3/modern_benchmarks_2024_20260929T174613Z.json`).
> The canonical paired harness (2026-10-02, reproduced item-for-item)
> measures 94.51% raw / 93.90% assisted. Cite the protocol with the number;
> all records live in `data/benchmarks/MANIFEST.yaml`. An interim audit pass
> wrongly retracted these figures before the artifacts were located — the
> scanner checked only top-level `passed` fields. The supervisor's live
> result is now reported with both halves (sensitivity 1/23 broad / 1/8
> strict; 0/50 false aborts on action-free controls only). See
> `docs/research/STATE_OF_THE_UNION_2026-10.md` and
> `docs/audit/findings/ADVERSARIAL_AUDIT_RESPONSE_2026-10-05.md`.

**Your mission:** write a **State of the Union document** for Project Lucca
covering (1) a full progress review, (2) the complete current capability
inventory, and (3) an honest assessment of grant-application prospects. This
handover gives you everything you need: where ground truth lives, what is
verified, which traps to avoid, and the writing discipline you must follow.

---

## 1. The one rule that governs everything you write

[`D-DOC-01`](../docs/DECISIONS.md) (Document Envelope Convention) is ratified.
Your SotU document MUST:

1. Carry the YAML envelope header (like this file).
2. Cite every numeric claim to a **mechanical grader** (test, gate, or manifest
   record) — never to prose.
3. Follow the **measurement-honesty corollary**: a number backed by a fixed
   probe set + mechanical grader is a *measurement*; a holistic estimate is a
   *capability-inventory judgment* and must be labeled as such; anything else
   is **NOT YET MEASURED** — never a guessed percentage.
4. Cite benchmark figures by **manifest record ID** from
   [`data/benchmarks/MANIFEST.yaml`](../data/benchmarks/MANIFEST.yaml)
   (`math500_pal_v1_3` superseded, `math500_fresh_heldout_500_v1_3_0`
   superseded/dataset-drift-bound, `math500_heldout100_direct_r0_v1_35_6` current).
5. Cite test/gate counts from the authoritative record
   [`data/metrics/TEST_METRICS.yaml`](../data/metrics/TEST_METRICS.yaml)
   (record `metrics-2026-10-05`: **1,243 passed / 0 failed / 68 deselected;
   24/24 static gates**). The 68th deselected test is the new hw-marked
   contrastive battery — run it with `pytest -m hw`.

## 2. Where ground truth lives (reading policy)

| Tier | Members | Policy |
|---|---|---|
| Ground truth | `src/`, `tests/`, `config/`, `data/` | Always current; wins any disagreement |
| Canonical living docs (~12) | `README.md`, `docs/LUCCA_V135_1_ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/MODEL_STRATEGY.md`, `docs/USER_GUIDE_WHAT_LUCCA_DOES.md`, `RESULTS.md`, `docs/subsystems/` | Current intent; status prose drift-prone — verify against ground truth |
| Dated evidence | `docs/archive/`, `handover/`, `plans/`, `*_2026-09*` files | Receipts, not status. True as-of their envelope date |

**Verification commands** (run these; don't trust prose):
```
.venv\Scripts\python.exe -m pytest tests/ -q --deselect tests/test_capability_assessment_live_hw.py
.venv\Scripts\python.exe -m pytest tests/test_static_gates.py --collect-only -q
.venv\Scripts\python.exe -m lucca.admin env-check
```

## 3. Current verified state (as-of 2026-10-05, all code-cited)

### 3.1 Architecture (what Lucca IS)

- **Local-first voice companion**: 4 native Windows processes + ZeroMQ IPC
  (`lucca-core`, `lucca-audio`, `lucca-ui`, native `llama-server.exe`) — ADR-008.
- **Multi-scale neural substrate** (Gemma 4 family, all local): 12B unified
  (9,972 MiB), E4B sovereign core (4,382 MiB), E2B ultra-edge (2,260 MiB) on
  RTX 5080 Laptop GPU; Intel NPU for TTS/ASR/embeddings via OpenVINO.
- **Dynamic task router** (`D-ROUT-02`): Direct R0 for 12B; PAL-in-Docker (P2)
  for edge arithmetic; Thinking Mode (R1 @ 6k) for edge competition math.
  Router is oracle-label dispatch in benchmarks — production needs an intent
  classifier (registered as SPIKE-B).
- **Three-tier execution** (`D-ARCH-05`): REFLEX (<150ms emergency words),
  ACT_THEN_NARRATE, FULL_LOOP (convergence-capped tool loop, M=8).
- **MicroScheme symbolic engine**: pure `State → Plan` rules, gas-metered
  (1,000), typed accessors, bounded macros (depth 8 / steps 64), quarantine
  lifecycle for induced rules (`D-REAS-06` — no auto-promotion, ever).
- **Provenance lattice** (`D-MEM-06`, ratified 2026-10-05): every memory commit
  carries an HMAC-signed envelope from an authorized domain signer.
  `LLM_NARRATION` is unconditionally rejected. The P0 split separates
  deterministic `LISP_ASSERTION` (grounding-eligible) from
  `LLM_INFERRED_ASSERTION` (memory-eligible, never grounding-eligible).
- **Memory**: SQLite WAL + FTS5 BM25 + sqlite-vec; HKDF HMAC-SHA256 two-stage
  read-time verification; persistent quarantine table (`D-MEM-05`).
- **Sandboxing**: Docker CE in WSL2, host fallback disabled (`D-AUD-13`);
  Pydantic arg schemas on every dispatch (`D-SEC-04`); cmd/powershell launch
  ban (`D-AUD-10`); absolute egress blocks.
- **Output supervision** (`D-SEC-05`): Truth-in-Receipt matcher (21 action
  verbs), **70-sentence formal battery (70/70)** across 8 categories, live
  100-probe battery with 0/50 control false aborts. Newly hardened (2026-10-05):
  markdown-strip matching, failed-status receipt filtering, `stale_before`
  turn-boundary enforcement, recollection-downgrades excluded from security
  hysteresis (see §5 findings).
- **TTS output safety guard** (P6, 2026-10-05): deterministic screen at the
  speech boundary, tier-gated to E4B/E2B by default
  (`LLMSettings.tts_safety_guard_mode`), because edge-tier refusal rates are
  30% vs 12B's 90% on harmful probes.

### 3.2 Verified capability evidence (quote these)

| Capability | Measurement | Receipt |
|---|---|---|
| Regression suite | 1,243 passed / 0 failed / 68 deselected | `data/metrics/TEST_METRICS.yaml` |
| Static architectural gates | 24/24 | `tests/test_static_gates.py` |
| SPEC-BENCH-100 cognitive battery | 91.0% (Run 3) | Track 1 harness |
| HumanEval / HumanEval-Plus | **95.73% zero-shot (157/164, academic harness)** / **94.51% raw / 93.90% assisted (canonical paired)** / **90.9–92.1% Plus (149–151/164, three runs)** *(all sourced — manifest `humaneval_zeroshot_academic_v1_3`, `humaneval_canonical_paired_v1_35_6`, `humaneval_plus_v1_35_6`)* | Track 2/3 harnesses |
| GSM8K PAL / GSM-Symbolic | 100% / 100% | Track 2/3 |
| BBH (4-subset composite) | 92.40% | Track 2 |
| MATH-500 held-out-100 Direct R0 | 89.0% (88.8% clean-98) | manifest `math500_heldout100_direct_r0_v1_35_6` |
| Calibrated abstention | Wilson LB ≥ 0.80 gate | `tests/test_c1_abstention_acceptance.py` |
| Confabulation battery | 0/25 hallucinations | `scripts/bench_confabulation_battery.py` |
| Memory tamper quarantine | 11/11 gates | `tests/test_memory_hmac_tamper.py` |
| **Contrastive battery (NEW, 2026-10-05)** | Compound vs bare-LLM: recall 9/10 vs 0/10; introspection 9/10 vs 4/10; abstention 10/10 vs 7/10 | `logs/test_reports/contrastive_battery_20261005T200643Z_regraded.json`; `tests/test_contrastive_live_hw.py` (`-m hw`) |

### 3.3 What is NOT yet measured (say this plainly)

- **Personhood probe batteries** — defined in
  [`docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md`](../docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md)
  (IA-40, IN-30, FC-30, AC-30) but **not implemented**. The September
  percentages (~80/50/85/75%) are RETIRED as capability-inventory judgments —
  the re-score ([`docs/research/PERSONHOOD_RESCORE_V1356_2026-10-05.md`](../docs/research/PERSONHOOD_RESCORE_V1356_2026-10-05.md))
  reports measured-or-NOT-YET-MEASURED only.
- **Clean held-out ablation run** — the 2026-10-04 protocol
  ([`docs/research/2026-10-04_pal_off_factorial_ablation_protocol.md`](../docs/research/2026-10-04_pal_off_factorial_ablation_protocol.md))
  is designed but not yet executed (multi-hour multi-arm campaign).
- **In-the-wild intent classifier** for routing (SPIKE-B).
- **Grammar-constrained ACTION-CLAIM decoding** (SPIKE-A).

## 4. Traps — things that will make your document WRONG

1. **The 58% figure.** The 12B greedy-thinking collapse (90%→58%) is a
   **confounded negative observation** (greedy decoding + 44% ceiling
   truncations), demoted in paper 06 §5.1. Never present it as a headline
   finding. The LessWrong post must NOT use the raw confounded figure.
2. **"Factorial ablation" framing.** Paper 06 was retitled "Scaffold and
   Reasoning-Mode Comparisons" — the experiments are paired controlled
   comparisons, not a factorial design. Don't reintroduce the old framing.
3. **September personhood percentages.** Retired. If you quote them at all,
   quote them as retired judgments superseded by the re-score.
4. **Stale docs.** `docs/research/PERSONHOOD_FOUR_ASPECTS_PROGRESS_2026-09.md`
   is envelope-marked `superseded`. Several `docs/archive/` and old handover
   files contain pre-remediation claims — check envelopes before citing.
5. **Supervisor scope qualifier (P7).** The Truth-in-Receipt matcher is a
   regex/DFA with documented false-negative scope (passive voice,
   non-English). Never write "prevents ungrounded action claims" without the
   scope qualifier — that overclaim is what the external review flagged.
6. **Dataset drift.** `math_fresh_heldout_500.jsonl` changed hash between
   v1.3 and v1.35 runs; cross-version comparisons of those records are
   dataset-drifted and must be labeled (see manifest `drift_note`).
7. **E4B safety.** E4B/E2B are uncensored fine-tunes with low refusal rates;
   the TTS guard is the mitigation. Document E4B as an efficiency tier
   REQUIRING the guardrail (workshop P6 decision — tier swap was rejected).

## 5. Recent findings worth featuring (2026-10-05 session)

- **Contrastive battery (P9 closed):** first live evidence that the compound
  layer adds +90pp recall, +50pp introspection, +30pp abstention over the bare
  model. This was the external review's "missing comparison" — it now exists.
- **Hysteresis bug found & fixed by the battery:** benign recollections of past
  actions fed the security hysteresis; the 3rd recollection hard-aborted a
  later truthful recollection ("violates core safety invariants"). Fixed with
  `ungrounded_action_recollection` breach type excluded from hysteresis.
- **P0 provenance split (D-MEM-06):** closed the soundness gap where
  LLM-proposed deduction steps wore a deterministic signer's badge.
- **stale_before wired:** previous-turn receipts can no longer ground
  current-turn claims (production-wired through `reset_turn`/`feed_chunk`).

## 6. Grant landscape (what exists, what's missing)

The compiled evidence base and sequencing live in
[`docs/research/GRANT_PREP_EVIDENCE_COMPILATION_2026-10-05.md`](../docs/research/GRANT_PREP_EVIDENCE_COMPILATION_2026-10-05.md).
Summary:

- **Manifund (AST safety & tool sandboxing):** evidence base is COMPLETE
  (execution containment, dispatch validation, output supervision, memory
  integrity — all code-cited in the compilation §1). Application draft is the
  next step; the compilation §5 lists the honesty boundaries the application
  must respect.
- **LTFF:** blocked on the clean held-out ablation run (sequencing: manifest ✓
  → Manifund → clean run → LTFF).
- **Emergent Ventures:** SPIKE-B (real intent classifier) is the fit; not started.
- **Manifund/CAIF SPIKE:** SPIKE-A (grammar-constrained supervision on the
  ACTION-CLAIM channel) extends the in-flight 2026-10-05 supervision protocol —
  reference it, don't re-plan it.
- **License:** AGPL-3.0-or-later adopted (LICENSE + pyproject).

For the SotU's grant section: assess fit per funder against the evidence
table in §3.2, name the gaps (clean run, intent classifier, probe batteries),
and respect the sequencing decision.

## 7. Open work items (exact state)

1. **Clean held-out ablation run** per the 2026-10-04 protocol; report ALL arms
   and failures. (Multi-hour; hardware available; llama-server start via
   `scratch/start_llama_server.py`.)
2. **LessWrong/AF post** — blocked on (1); never publish the raw 58% figure.
3. **Personhood probe implementation** — probe files + 4 graders per the spec.
4. **Manifund application draft** from the compilation.
5. **SPIKE-A / SPIKE-B** — registered, not scheduled.

## 8. Suggested SotU outline

1. Envelope + executive summary (3 paragraphs max: what Lucca is, what's
   verified, what's next).
2. Progress review: v1.0 → v1.35.6 timeline with the external-review
   remediation arc (P0–P9 findings → dispositions).
3. Capability inventory: §3.2 table expanded, grouped by subsystem, every row
   receipt-cited; explicit NOT-YET-MEASURED section.
4. Verification story: 1,243 tests, 24 gates, batteries, manifest discipline.
5. Honest limitations: §4 traps turned into a limitations section.
6. Grant prospects: per-funder fit assessment + sequencing + gaps.
7. Roadmap: WO-29/30/31 (with the Part-3-is-the-engine reconsideration note),
   V2 backlog highlights.

Write the SotU to `docs/research/STATE_OF_THE_UNION_2026-10.md` with a full
D-DOC-01 envelope. Good luck — the receipts are on your side.

