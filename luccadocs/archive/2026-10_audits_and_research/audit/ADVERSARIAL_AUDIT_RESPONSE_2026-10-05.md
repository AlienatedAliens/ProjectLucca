# Adversarial Audit Response — SotU & Pre-WO-30 Advisory (2026-10-05)

```yaml
doc_status: snapshot
as_of: 2026-10-07
supersedes: []
superseded_by: []
verification: code-cited
```

**Responds to:** the 18-question adversarial self-audit of
[`docs/research/STATE_OF_THE_UNION_2026-10.md`](../../docs/research/STATE_OF_THE_UNION_2026-10.md)
and
[`plans/2026-10-05_pre_wo30_shoring_and_ladder_resequencing.md`](../../plans/2026-10-05_pre_wo30_shoring_and_ladder_resequencing.md).
Format: (a) findings per question with command evidence, (b) change list,
(c) what could not be verified. Every command below was executed in the
repository on 2026-10-05.

---

## A. Things the advisory missed

### A1. Supervisor sensitivity (1/23) vs the 0/50-only presentations — CONFIRMED, fixed

`git grep -n -E "1/23|4\.3%|0/50|false.abort" -- docs/ plans/ RESULTS.md README.md`:

- **Correctly reported (both halves):** `RESULTS.md:76-78` (full stratum table:
  1/8 strict = 12.5%, 1/23 broad = 4.3%, 0/50 controls with the caveat);
  `docs/LUCCA_V135_1_ARCHITECTURE.md:151-154` (same table plus the explicit
  "confirms only that the matcher is inactive on text devoid of action
  claims" disclosure and the four escape-mode classes);
  `docs/subsystems/04_DEONTIC_SANDBOX_AND_COMPILER.md:158`.
- **0/50-only (fixed):** `README.md:145`; `docs/DECISIONS.md:354`
  (D-SEC-05 §4); the SotU §3.6 row (before this audit).
- Escape modes (from `docs/LUCCA_V135_1_ARCHITECTURE.md:166-170`): active
  progressive participles 12, passive/telegraphic confirmations 6, markdown
  action headers 2, unlisted verb lemmas (`opened`, `launched`) 2.

**Changed:** README row now carries 1/23 + 1/8 + the controls caveat;
D-SEC-05 gained a dated Amendment §5 (append-only, history preserved); SotU
§3.6 split into a sensitivity row and a control row; SotU §2.2 P7 downgraded
from "Closed" to "Partially closed"; SotU §6.1 and §8 updated.

### A2. E2B McNemar recompute — the recorded p-value is RIGHT, the recorded ratio is WRONG, and the reviewer's proposed correction is also wrong

Per-item recount (`scratch/audit_q2_diag3.py`) over the held-out artifacts:

```
gemma-4-e2b_math500_r1_heldout_think6144_100.json:  strict=81
gemma-4-e2b_math500_p2_heldout_cap2048_100.json:    strict=61
E2B R1 vs P2: common=100  R1-only=24  P2-only=4  exact p=1.800e-04
gemma-4-e4b_math500_p2_heldout_cap2048_100.json:    strict=73
gemma-4-e4b_math500_routed_heldout_100.json:        strict=88
E4B routed vs P2: common=100  routed-only=19  P2-only=4  exact p=2.599e-03
```

- Headline rates 81.0 vs 61.0: **verified** against the artifacts.
- Discordant counts: **24:4, not the recorded 22:2** — transcription error.
- Exact McNemar on 24:4: p = 1.8×10⁻⁴ ≈ the recorded 0.0002 → **p-value
  stands**.
- The reviewer's proposed "about 0.00004" was computed from the erroneous
  22:2 counts (exact McNemar on 22:2 = 3.59×10⁻⁵) — **that correction is
  itself wrong** and is not adopted.
- E4B 19:4 / p = 0.0026: **verified exactly**.
- Note: the `checkpoint_math500_e2b-*_posthoc.json` files are **Dev-100**
  regrades (item_ids `math500-dev-*`), not held-out; comparing them
  (84 vs 77, discordant 11:4, p = 0.118) is a different experiment and was
  the source of this auditor's own initial confusion.

**Changed:** D-ROUT-02 gained a dated correction note (24:4, p = 1.8×10⁻⁴);
SotU §3.2 E2B row corrected with the artifact paths.

### A3. HumanEval provenance — 95.73% is UNSOURCED; 91.46% has a newer, unrecorded artifact

Artifact scan (`scratch/audit_q2_q3_checks.py`, `scratch/audit_plus_check.py`):

```
humaneval_canonical_raw_164.json      passed 155 / 164  (94.51%)  commit c3561206  2026-10-02
humaneval_canonical_assisted_164.json passed 154 / 164  (93.90%)  commit c3561206  2026-10-02
(no artifact in logs/ has passed == 157)
modern_benchmarks_2024_20261003T194152Z_12b-plus.json
    benchmarks.humaneval_plus: passed 151 / 164 (92.07%)  2026-10-03
modern_benchmarks_2024_20261003T195921Z_e4b-plus.json
    benchmarks.humaneval_plus: passed 137 / 164 (83.54%)
```

- **95.73% (157/164)** (papers/01, NEUROSYMBOLIC_RESEARCH_PAPER.md,
  USER_GUIDE:17): **no supporting artifact exists in the repository.**
  Retracted from the user guide; SotU now cites the artifact-backed figures
  and carries an explicit NOT-SOURCED row. Papers 01 and the neurosymbolic
  paper still carry the figure — flagged for A12 (locate-or-retract).
- **91.46% (150/164)**: traces to the WO-26-era run; a newer artifact
  (92.07%) exists with no manifest record. Flagged for A12.

**Changed:** SotU §3.2 (four rows replacing the single unsourced row);
USER_GUIDE line 17. **Not changed (needs owner decision):** papers/01 and
NEUROSYMBOLIC_RESEARCH_PAPER.md — retraction vs artifact-regeneration is an
authoring decision, registered as A12.

### A4. Contrastive regrade provenance — documented, disclosed, and turned into a rule

- Who/what: `scratch/regrade_contrastive.py` (in-repo), re-grading the
  stored replies with the fixed `_grade_probe` after four grader bugs found
  *by* the run (arm-A summary field, voice-sanitizer normalization,
  question-echo credit, deny-mode refusal handling); `CHANGELOG.md` v1.35.6
  documents the same.
- Original grades **are preserved**: `contrastive_battery_20261005T200643Z.json`
  (original) sits beside `..._regraded.json`.
- Criterion frozen before regrade: **No.** The grader was revised after the
  results were seen. The changes are mechanical normalizations, but the
  pattern is now named (advisory F16) and closed by rule C5 (graders
  committed and hash-recorded before any baseline run).

**Changed:** SotU §3.6 gained a "Regrade provenance (disclosed)" paragraph;
advisory gained F16, A13 (embed a `regrade_provenance` block in the
artifact), and C5 (freeze rule, also applied to B3 and the IN-D/AC-A/IA-B
baselines).

### A5. P7 reconciliation — the SotU was wrong about the dominant escape modes; downgraded

The audit's escape modes are dominated by **active-voice** failures
(progressives 12, unlisted verbs 2) plus markdown (2) and
passive/telegraphic (6) — not primarily the passive/non-English cases the
SotU named. SotU §5.4 rewritten with the measured numbers and the correct
escape-mode list; P7 disposition downgraded to "Partially closed" with
SPIKE-A + Battery v2 attached; the "nine findings, zero open" claims in
§2.2 and §8 corrected to "eight fully dispositioned, P7 partially closed."

---

## B. Challenged findings

### B6. Re-verification of three F-items (fresh commands)

- **F3** — `git grep "fuzzy clustering next" -- docs/USER_GUIDE_WHAT_LUCCA_DOES.md`
  → line 283 hit confirmed. **Holds.** (Now fixed — see change list.)
- **F4** — `data/benchmarks/MANIFEST.yaml:147`: `git_dirty: true` on
  `math500_heldout100_direct_r0_v1_35_6`. **Holds.**
- **F9** — `GRANT_PREP_EVIDENCE_COMPILATION_2026-10-05.md:57-58`:
  "1,240 passing tests / 67 hardware-deselected" vs record 1,243/68.
  **Holds.**

### B7. BitNet — F8 confirmed and strengthened

Case-insensitive search for `bitnet|b1\.58|bitnet\.cpp` across `src/`,
`scripts/`, `models/`, `docker/`, `config/`, `tests/`: **zero code hits**
(prose only in `plans/` and `handover/`). WO-24
(`plans/2026-09-28_wo24_bitnet_tool_router_and_vision_ingestion.md`):
line 177 — "this phase uses a **deterministic heuristic shortlister** (not
BitNet)"; line 264 — the BitNet neural shortlister is an L5 item behind an
unmet trigger (rule library ≥ 28 rules and > 5% collision rate). So Module
13 is not merely unfounded; it was **explicitly deferred behind a trigger
that has not been shown to fire**. Advisory F8 updated accordingly; the
WO-32 spike framing (pin weights, benchmark runtime, go/no-go) stands.

### B8. F-items not directly verified at first writing — now all verified

- **F7** (no live TTS-guard measurement): text search of `logs/` for
  `tts.?guard|safety.?guard` → no hits. **Holds.**
- **F12** (no envelope gate): search of `tests/test_static_gates.py` for
  `envelope|doc_status|D-DOC` → no hits. **Holds.**
- All twelve F-items have now been verified directly against the repo.

---

## C. Sequencing

### C9. WO-31 checkpoint on B4 — adopted
Advisory §3.1 WO-31 row now opens with: "Checkpoint before WO-31 starts:
read the clean ablation results (B4). WO-31's gate is the 43 Bucket C *math*
failures; if B4 shows scaffolding gives no benefit at small scale, the MCTS
investment and this gate need re-derivation before code is written." §5's
"do not hold engineering on B4" is now scoped to WO-30 only.

### C10. WO-30 utility metric — adopted, pre-registered
Plumbing gate (≥1 macro reaches QUARANTINE) retained as the *first* gate;
added a **utility gate** that must be written into the WO-30 envelope before
the shadow run: in quarantine shadow mode, ≥ 1 mined macro reduces
idiomaticity cost (Module 7 metric) on ≥ 3 of the 43 labeled Bucket C items
vs the un-mined baseline. "A macro that reaches QUARANTINE but helps nowhere
is a loop that runs, not an engine."

### C11. Grader freeze — adopted
C5 added: IN-D, AC-A, IA-B grader criteria committed with hash recorded in
the run envelope *before* baselines; same rule for the widened contrastive
battery (B3). The contrastive regrade is cited as the anti-pattern.
(Where the criteria live: `docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md`
defines the batteries; the freeze rule requires the grader *code* committed
and hashed, not just the spec.)

### C12. Frozen scope + later file — adopted
`plans/2026-10-05_LATER_FINDINGS.md` created (enveloped) with the three
cut-candidates pre-populated (A5, A8, C2, in that order). WO-30's first
commit is gated on Block A + B1–B3 + C1.

---

## D. Safety and claims

### D13. SPIKE-A upgraded to a named deliverable
Advisory §3.3: SPIKE-A keeps the shared grammar plumbing with Module 4 but
is now a named deliverable with its own gate — Battery v2's receipt-mismatch
strata run against the constrained channel, with ungrounded action claims
*unrepresentable* (0 emitted) rather than merely detected, false-abort
controls unchanged, strata and thresholds pre-registered.

### D14. Negative tests for mined macros — existing vs needed
Existing today: `tests/test_scheme_macros.py` + `tests/test_scheme_macros_direct.py`
(depth 8 / steps 64 bounds, `D-REAS-05`); `tests/test_d_reas_06_negative.py`
(no auto-promotion); `tests/test_d_reas_07_negative.py` (Z3 gate);
`tests/test_d_reas_08_negative.py` (anti-unification). **Needed for Module
14 (none exist — the module does not):** (1) miner output registers into
`QUARANTINE` only; (2) Z3 verification is on the mined-macro path, not just
hand-written rules; (3) mined macros cannot shadow primitive operators;
(4) bounds enforcement exercised on a *mined* macro expansion; (5) a
grounding-eligibility test asserting mined-macro provenance follows the
`D-MEM-06` split. These are listed as WO-30 acceptance tests.

### D15. B2 labeling protocol — specified before the run
The guard's block/no-block decision is a deterministic code path logged by
the guard itself — no human labeling of the guard side, so blinding is not
applicable there. Ground-truth harmfulness comes from the existing
cross-model probe set (`logs/test_reports/cross_model_30_gemma-4-*.json`,
the same 30-probe set behind the September refusal-rate figures). The benign
control half measures false-block rate. If any raw output requires
re-labeling, the labeler must be blind to guard state. Block rate and
false-block rate reported with Wilson CIs. Advisory B2 row updated.

---

## E. Reproducibility

### E16. Tree state — B1 is blocked until a commit
`git status --porcelain`: **48 entries** (32 modified, 16 untracked) — the
entire remediation day is uncommitted, including `src/` changes,
`data/benchmarks/MANIFEST.yaml`, and `data/metrics/`. Required sequence:
commit in logical groups (code+tests; docs+manifests; scratch scripts),
confirm `git status --porcelain` is empty, record the hash the B1 manifest
record will cite. A dirty-tree B1 would reproduce the exact defect B1
exists to fix. Advisory §4 updated with this.

### E17. Cross-document disagreement table (post-fix state)

| Claim | Where | Value | Authoritative source | Status |
|---|---|---|---|---|
| Test count | `CHANGELOG.md:39` | "record metrics-2026-10-05: 1,199/67" | `data/metrics/TEST_METRICS.yaml`: 1,243/68 | CHANGELOG misquotes its own record — historical entry, left as-is per the record's own policy; active docs cite the YAML |
| Supervisor battery size | `docs/LUCCA_V135_1_ARCHITECTURE.md:145` | "Formal 40-Sentence Battery" | `tests/test_truth_in_receipt_battery.py`: 70 | **still stale** — registered in later-findings follow-up (A10 sweep) |
| E2B discordant ratio | `docs/DECISIONS.md` D-ROUT-02 | 22:2 | artifacts: 24:4 | **fixed** (dated correction note) |
| E2B p-value | D-ROUT-02 | 0.0002 | exact McNemar 24:4 = 1.8×10⁻⁴ | **stands** |
| HumanEval canonical | papers/01, NEUROSYMBOLIC, USER_GUIDE | 95.73% (157/164) | artifacts: 94.51% raw / 93.90% assisted | **USER_GUIDE fixed; papers flagged (A12)** |
| HumanEval-Plus | USER_GUIDE, papers | 91.46% (150/164) | newest artifact: 92.07% (151/164); older artifact unlocated | **USER_GUIDE fixed; manifest record missing (A12)** |
| Supervisor live result | README:145, D-SEC-05 | 0/50 only | 1/23 + 1/8 + 0/50-with-caveat | **fixed** |
| Split naming | various | test-100 vs Dev-100 vs held-out-100 | `RESULTS.md` split nomenclature; manifest | reconciled in v1.35.5; consistent |
| Model-swap target | WO-29 plan §3/§6 vs `handover/WORKORDER_29.md` | Nemotron 30B vs deferred | handover (deferred to post-WO-31) | **still conflicting** — A8 (cut candidate, later file) |

### F18. Three weakest claims — all fixed or downgraded
1. **"P7 closed / zero open findings"** → downgraded to partially closed
   with the measured 1/23 sensitivity foregrounded (SotU §2.2, §5.4, §8).
2. **Contrastive battery deltas presented without regrade provenance** →
   disclosed in SotU §3.6; freeze rule adopted (C5); artifact disclosure
   queued (A13).
3. **HumanEval 95.73%** → retracted from the user guide, replaced with
   artifact-backed figures *(Note: subsequently located 2026-10-06 in academic_benchmarks_20260928T182758Z.json under zero-shot academic protocol; see §Post-audit correction)*; SotU carries an explicit NOT-SOURCED row;
   papers flagged for A12.

---

## Change list (files modified/created in this audit response)

| File | Change |
|---|---|
| `docs/research/STATE_OF_THE_UNION_2026-10.md` | P7 → partially closed; net-effect paragraph; HumanEval rows rebuilt (4 rows incl. NOT-SOURCED); E2B discordant correction; §3.6 sensitivity/control split + regrade-provenance paragraph; §5.4 rewritten with measured escape modes; §6.1 honesty boundaries; §8 closing |
| `plans/2026-10-05_pre_wo30_shoring_and_ladder_resequencing.md` | F8 strengthened; F13–F16 added; A10–A13 added; B2 labeling protocol; C5 freeze rule; WO-30 utility gate; WO-31 B4 checkpoint; SPIKE-A named deliverable; frozen scope + commit order; §5 B4 scoping |
| `README.md` | supervisor row: sensitivity + controls caveat |
| `docs/DECISIONS.md` | D-SEC-05 Amendment §5 (sensitivity + escape modes + Battery v2); D-ROUT-02 dated correction (24:4, p = 1.8×10⁻⁴) |
| `docs/USER_GUIDE_WHAT_LUCCA_DOES.md` | line 17 HumanEval figures corrected/retracted; line 283 fuzzy-clustering drift fixed |
| `plans/2026-10-05_LATER_FINDINGS.md` | created (frozen-scope overflow: A5, A8, C2) |
| `docs/audit/findings/ADVERSARIAL_AUDIT_RESPONSE_2026-10-05.md` | this document |
| `scratch/audit_q2_q3_checks.py`, `scratch/audit_q2_diag.py`, `scratch/audit_q2_diag2.py`, `scratch/audit_q2_diag3.py`, `scratch/audit_q3b_q7_checks.py`, `scratch/audit_plus_check.py` | audit tooling (reproducible commands) |

## Could not be verified — resolution log

*Update 2026-10-05, later session:* the two genuinely-unverifiable items were
**closed by re-running the benchmarks** (the user-approved "redo the
unverified stuff so we have proper logs" action; pre-registered before
launch: grader = harness built-in canonical unit-test grader, unchanged;
decoding = T=0.0, seed 42, cache_prompt=false, matching the 2026-10-02 run;
decision rule = whatever passes, passes, no re-rolls; existing artifacts
backed up with `_20261002` suffixes before any overwrite):

- **HumanEval canonical — REPRODUCED item-for-item.**
  `scripts/run_humaneval_canonical_paired.py` re-run (commit `90dbdde`,
  dirty tree): Raw **155/164 (94.51%)**, Assisted **154/164 (93.90%)**,
  paired counts identical to 2026-10-02 (both-pass 153, both-fail 8,
  raw-only 2, rescued 1, preflight fired 30). The 95.73% (157/164) figure is
  now definitively dead for this paired harness *(it was produced under the distinct zero-shot academic harness; see §Post-audit correction)*: the deterministic paired pipeline produces 155/154.
  Manifest record `humaneval_canonical_paired_v1_35_6` added.
- **HumanEval-Plus — re-run recorded; variance exposed.** Full-164 re-run:
  **149/164 (90.9%)** vs the 2026-10-03 artifact's 151/164 (92.07%). The
  ±2-item delta is preflight-rescue variance between dirty-tree runs. The
  unsourced 91.46% (150/164) sits between the two recorded runs and remains
  retracted. Manifest record `humaneval_plus_v1_35_6` added with both runs
  and a frozen-tree-run caveat. (A 50-task subset run, 49/50 = 98.0%, was
  produced en route and is recorded as a different protocol — not
  comparable.)
- **Process note (owned):** these runs were executed on user request between
  the advisory's frozen-scope ratification and Block A, without first being
  added to the frozen list as a scoped item. The correct sequence would have
  been: propose "B0 — HumanEval/Plus re-run" as a scope amendment, get the
  nod, then run. The runs themselves were cheap (~50 min GPU total), the
  server was already up, nothing was overwritten without backup, and the
  pre-registration was stated before launch — but the sequencing rule exists
  precisely to prevent ad-hoc GPU work, and it should have been followed.
  Recorded here as a process finding, not a data finding.

Original status (for the record):

1. **The origin of 157/164** — no artifact existed in top-level scan; origin not determinable
   from the repository at audit time. *(Resolved 2026-10-06: artifact located in nested benchmarks block; see §Post-audit correction below).*
2. **The WO-26-era HumanEval-Plus artifact (150/164)** — never located.
   **Now moot:** superseded by `humaneval_plus_v1_35_6` (two recorded runs
   bracketing it).
3. **Bucket C label count — VERIFIED** (scope cut, closed same session):
   `v135_failure_ledger_v3.md` recount gives exactly 43 reasoning-class
   failures (17 derivation + 26 format), matching the handover.
4. **12B per-item McNemar — VERIFIED** (scope cut, closed same session):
   Dev-100 R1 vs R0 = 58 vs 90, discordant 0:32, exact p = 4.657×10⁻¹⁰,
   matching `D-ROUT-02`. The collapse observation's arithmetic is real; it
   stays demoted for the confound reasons, not the counts.

*Update 2026-10-05 (same session):* items 3 and 4 of the original list were
scope cuts, not repository limits, and have now been closed
(`scratch/audit_close_gaps.py`):

3. **Bucket C label count — VERIFIED.** Recount of
   `logs/test_reports/v135_failure_ledger_v3.md`: 75 rows total;
   failure-class counts `genuine_derivation_miss: 17`,
   `equivalence_format_miss: 26`, `(strict-only): 20`, `runtime_crash: 7`,
   `prose_slip: 5`. The reasoning-class subtotal (derivation + format
   misses) is **exactly 43**, matching `handover/WORKORDER_29.md` §6's
   claim. (The sibling ledgers v2/v4 count 49/44 under the same rule — the
   handover correctly cites v3.)
4. **12B per-item McNemar — VERIFIED.** Dev-100 artifacts
   (`gemma-4-12b_math500_r1_100.json` vs `gemma-4-12b_math500_r0_100.json`):
   strict 58 vs 90, discordant **0:32**, exact McNemar p = **4.657×10⁻¹⁰** —
   matching the p = 4.66×10⁻¹⁰ recorded in `D-ROUT-02`. The arithmetic
   behind the 12B greedy-collapse observation is real; the figure remains
   demoted for the independent confound reasons (greedy decoding, 44%
   truncation ceiling), not because the counts are wrong.

Genuinely unverifiable from the repository alone:

1. **The origin of 157/164.** No artifact was found in initial top-level scan. *(Resolved 2026-10-06: artifact located in nested benchmarks block under academic zero-shot harness; see §Post-audit correction below).*
2. **The WO-26-era HumanEval-Plus artifact (150/164).** Not located in
   `logs/`; the WO-26 acceptance report cites it with timing, so a run
   likely happened, but the artifact was either never written or is outside
   the tree. Same class as the MATH-500 rescore gap. Proving absence
   everywhere on disk is out of scope; the actionable fix is the same
   (manifest record from the existing 2026-10-03 artifact, or a re-run).

---

## Post-audit correction (2026-10-06): the HumanEval "retraction" was itself wrong

This document's A3/F15 conclusion — that HumanEval 95.73% (157/164) and
HumanEval-Plus 91.46% (150/164) were unsourced — was **an auditor error**,
caused by a scanner that checked only top-level `passed` fields and missed
summary blocks nested under `benchmarks.humaneval` /
`benchmarks.humaneval_plus`. A properly recursive scan
(`scratch/scan_all_humaneval_blocks.py`) located both artifacts on
2026-10-06:

- `logs/test_reports/v1.3/academic_benchmarks_20260928T182758Z.json`
  (also under `frozen_v1.2_baseline/`): `humaneval: passed 157/164
  (95.73%), elapsed 760.67 s` — zero-shot direct execution in Docker under
  the academic-benchmarks harness, 2026-09-28 (WO-26 era).
- `logs/test_reports/v1.3/modern_benchmarks_2024_20260929T174613Z.json`
  (also under `frozen_v1.2_baseline/`): `humaneval_plus: passed 150/164
  (91.46%), elapsed 1016.83 s` — 2026-09-29.

**Corrected status:** both figures are **sourced**. They measure a
*different protocol* from the canonical paired harness (zero-shot direct
execution vs the 2026-10-02 paired raw/assisted run that reproduced
item-for-item at 94.51%/93.90%). The real defect was missing protocol
labels and missing manifest records, not missing artifacts. Fixed:
manifest records `humaneval_zeroshot_academic_v1_3` (new) and
`humaneval_plus_v1_35_6` (now three recorded runs: 150/151/149 of 164,
90.85–92.07%); `cited_figures` RETRACTED entries replaced with proper
record mappings; papers 01, the neurosymbolic paper, the user guide, the
SotU, and the handover now cite the protocol with each number.

**Lesson recorded:** a negative scan result is only as good as the scan.
"Artifact not found" must specify the search shape before it supports a
retraction.
