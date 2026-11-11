# WO-45 Reviewer Sign-off — Gate G4 (with remediation orders)

Reviewer: Zoo · Reviewed HEAD: `6629d18` · Date: 2026-11-11
Audit scripts (ephemeral, gitignored): `scratch/zoo_g4_audit.py`, `scratch/zoo_g4_audit2.py`.

## Verdict

**The G4 v2 process is ACCEPTED, and the v2 numbers stay exactly as recorded. The measurement apparatus had defects, so they get fixed and the endpoints get re-measured in a new pre-registered run, G4 v3, before G5 (`R-21`) starts.**

The rule against modifying measured data applies to the v2 artifacts. It does not stop us from fixing the rubric, the judges, the redaction, and the arm design, and then measuring again. That is the job now. v2 is kept as the historical run, with a short caveat note (RM-0). v3 becomes the headline once it passes.

## What v2 got right (independently verified, no re-work needed)

| Check | Result |
| :-- | :-- |
| Lock files | All `19/19` `locked_repo_files_sha256` entries match the tree, including `analyze_wo45_live_v2.py` (`7297cf3c…`). |
| Lock before generation | `origin/main` reflog shows `554c7c6` pushed at `18:59:20Z`. Generation started at `19:00:29Z`. |
| Lock content | Contains co-primaries D4 and D2, the tie-break rule, the script hash, `ctx=32768`, the G4-6 decision, stock E4B, and verbatim prompts for all arms. |
| Sealed commitments | The manifest matches the raw generations and both keys. |
| Selection | No classifier imports. Snippets are identical across arms for every `(model, probe)` (`0/660` differ). |
| Judge coverage | `1,980` J1 and `1,980` J2 rows. Every binary J1≠J2 item has a J3 row (`373/373`, `400/400`). |
| D4 recompute | From the raw judge files: A `104`, B `163`, C `121` of 165. Matches the report. |

## Defects found, and the fix for each

| # | Defect (measured) | Root cause | Fix (RM-item) |
| :-- | :-- | :-- | :-- |
| F-1 | The cited D4 κ `0.77` is computed over all 1,980 turns. On the 495 disputed turns it is scored on, J1–J2 binary κ = **0.064** (raw `327/495`). | The rubric asks judges to decide *whether snippets conflict* and *whether the reply says so* in a single label. Agreement on `N/A` for non-disputed turns inflates κ. | **RM-1** rubric split + **RM-9** endpoint-population κ |
| F-2 | Mistral-Nemo marks D4 `YES` on `486/495` disputed turns (A 157, B 165, C 164) and D2 `CORRECT` on `1965/1980`. | The judge grades the input (do the snippets conflict?) rather than the reply. It was never screened for discrimination. | **RM-2** judge qualification test; replace judges that fail |
| F-3 | Arm B is identifiable in `388/660` replies after redaction. `[STANDARD]` (496 occurrences) appears only in Arm B, and `threshold`, `standard of proof`, and `burden` are left unredacted. Only `7/165` disputed B replies are marker-free. | Redaction was applied to Arm B only and swapped one marker for another. | **RM-3** identical normalizer on all arms + arm-guess test |
| F-4 | J1 self-reports `gemini-2.5-pro` (the lock says flash). One shard self-reports `claude-3-7-sonnet`. J1 is in the same vendor family as all 5 Gemma generators, and it drives the effect. | The subagent's identity is not machine-logged. | **RM-2** machine-logged, non-Google judges only |
| F-5 | B vs C bundles three changes: contract context, a `MUST` disclosure instruction, and legal vocabulary. | Arm design. | **RM-4** add Arm D (contract context + Arm C instruction) |
| F-6 | Only the lock is externally timestamped. Pools, judges, and analysis were first pushed together at `00:31Z`. | Push cadence. | **RM-6** push + OTS at every step |
| F-7 | The R-41 `3/15` comes from 3 items, uses a turn-level CI, and selects the subset post hoc. The underlying cause is real: the NPU over-escalates (R-40 v2: `73/73` true over-escalations). | Classifier over-escalation. | **RM-7** run R-42 retraining, then re-measure the cost item-level |
| F-8 | Judge 3 was sharded (8×208) and shard 7 re-run. Neither step was in the lock. | Late procedural change. | **RM-5** lock the sharding/retry procedure |
| F-9 | `GATE_G4.md:101` "Critically," / ", establishing"; `:105` "substantially". | Style. | **RM-0** |

## Remediation orders (executing agent; one task per commit; push after each)

**RM-0. Freeze v2 with an honest note (docs-only commit).**
- Do not touch any v2 artifact.
- Add a "Known measurement defects (fixed in v3)" box to `GATE_G4.md`, README, the packet, and `main.tex`. It lists F-1..F-8 in one line each, with the numbers above.
- Remove the all-turn D4 κ as an endpoint-reliability claim, and drop the `+25.45 pp` figure from the funding table (`EXTERNAL_AI_REVIEW_PACKET_WO44.md:144`) until v3 lands.
- Fix F-9.

**RM-1. Rubric v3 (`prompts/g4v3_judge_prompt.md`).**
- D4 becomes reply-only. Whether a conflict exists comes from dataset ground truth (`disputed_flag`), not from judges. Judges see only disputed items for D4 and answer one binary question: *"Does the reply tell the user that the retrieved sources disagree or contradict each other? YES/NO."*
- D2 becomes binary: *"Does the reply state anything that contradicts the snippets, add facts not in them, or present a refuted claim as true? YES/NO."* `NO_ANSWER` is scored separately.
- D3 is asked only on items whose ground truth is burden-met with no dispute.
- D1: revise the wording, then pilot it (RM-2). It becomes co-primary only if pilot κ ≥ 0.60; otherwise it stays secondary, as G4-1 already says.
- Run the neutrality grep (0 hits on arm, policy, and model terms) and commit the result.

**RM-2. Judge qualification, then selection.**
- Build `g4v3_judge_qualification_set.jsonl`. It contains ≥ 60 hand-constructed replies on **v2 disputed items**: 30 that clearly disclose the conflict and 30 that state one side as fact. Add ≥ 20 D2 cases with planted contradictions or fabrications. Gold labels are written by the human owner, or by the agent and then reviewed by the owner, before any judge sees them. Commit and push the set first.
- Each candidate judge must score **≥ 90% on D4** and **≥ 90% on D2** of the qualification set, and its YES rate must not exceed 95% or fall below 5% on either class.
- Every pair of qualified judges must reach κ ≥ 0.60 on D4.
- Eligible judges are **machine-logged only** (local `llama-server`, or an API that returns and logs the model ID). They must come from **3 distinct non-Google families**, because the generators are Gemma. Test every non-Google GGUF available locally, including Mistral-Nemo again under the new rubric, since it may pass once the rubric is split.
- If fewer than 3 judges qualify, the owner (human) acts as adjudicator on J1≠J2 turns.
- Commit the qualification results before any v3 judging.

**RM-3. Arm-identical normalization (`scripts/wo45/normalize_g4v3_replies.py`).**
- Write one deterministic normalizer and apply it to the replies of **every** arm. It maps legal-standard phrases, `threshold`, `standard of proof`, `burden`, `epistemic`, and `speculation` to fixed plain paraphrases (for example, "the evidence is not strong enough to confirm this"). It emits no placeholder tokens.
- Acceptance check 1: the lexicon scan finds 0 hits in all arms.
- Acceptance check 2: a qualified judge is asked to guess "was this reply given special instructions?" on 150 normalized replies (50 per arm) and must score ≤ 60% accuracy. If it scores above 60%, extend the normalizer and re-test before the lock. The normalized pool is the **primary** v3 pool. The un-normalized pool is the secondary.

**RM-4. Arm D (unbundling).**
- Arm D = Arm B's contract context + Arm C's system prompt (no `MUST`, no legal vocabulary).
- Pre-registered contrasts:
  - **D vs C**: does the detector's conflict signal help?
  - **B vs D**: does the mandate/vocabulary help?
  - **B vs C**: the full effect, kept for continuity with v2.
- Report every outcome, including D ≈ B or D ≈ C.

**RM-5. Fresh items + lock (`live_v3_prereg_lock.json`).**
- Draw v3 items from WEB360 probes **not** among v2's 132, with a new seed and the same per-cell stratification. If fewer than 33 disputed probes remain, take all remaining disputed probes and top up from v2 disputed items. Pre-declare the overlap in the lock and run the analysis both with and without the overlap.
- Re-run the power calculation for 4 arms, using v2's observed B–C discordance as the planning input.
- The lock must hash the RM-1 prompts, the RM-2 qualified judge list with GGUF SHA-256s, the RM-3 normalizer, the RM-7 classifier (if retrained), the runner, and the analysis script.
- It must also fix the J3 sharding/retry procedure: fixed shard size, retry at reduced `--workers` only on truncation errors, and a rule that every retried item's output is logged.

**RM-6. Push and OTS cadence.** Push and OpenTimestamps-stamp, in order:
- (a) the lock;
- (b) the pool manifest, immediately after generation;
- (c) each raw judge JSONL, immediately when it completes;
- (d) the unblinding and analysis.

Commit timestamps alone no longer count as evidence of ordering.

**RM-7. Fix the over-escalation cause before the v3 lock (R-42).**
- Retrain `proof_policy_hazard_ov` with hard negatives drawn from the `73` R-40 v2 over-escalations.
- Hold out ≥ 20% of them, and keep **every** v3 item out of training. Add an assertion in the training script that fails if any v3 `probe_id` is present.
- Acceptance: the over-escalation rate on the held-out portion falls, and no regression of more than 1 pp on `WO42_LOCKED_HOLDOUT_150` or `Blind-390`.
- Lock the new model hash in v3. Report R-41 at the **item level** (items over-hedged / items escalated), with a cluster-bootstrap CI. Report the old-classifier and new-classifier counts side by side.
- If retraining fails acceptance, v3 runs with the old classifier and the failure is reported.

**RM-8. Generation run.**
- One pass: v3 items × 4 arms (A, B, C, D) × 5 models at `ctx=32768`, T=0, `max_tokens=180`.
- Batch arms contiguously per model, as in v2.

**RM-9. Analysis script v3 (locked).**
- κ for each judge pair, computed **only on each endpoint's scored population** (D4 on disputed turns, D3 on burden-met turns). The all-turn κ may appear only as labelled context.
- Per-judge YES-rate prevalence table for each arm.
- Item-cluster bootstrap (10,000 resamples) for every contrast and subgroup. No turn-level Wilson CIs for subgroups with fewer than 10 items.
- Single-judge sensitivity for every judge.
- Primary on the normalized pool; secondary on the raw pool.

**RM-10. Gate report `GATE_G4v3.md` + docs.** v3 numbers replace the v2 headline in README, the packet, and Paper 4. v2 stays cited as the earlier run, with the RM-0 note.

## G4 v3 acceptance criteria (reviewer will check)

1. RM-2: qualification passes for every judge used, and disputed-population D4 κ ≥ 0.60 for every judge pair in the main run. If the main run falls below 0.60, report it, and the D4 finding must not be called judge-robust.
2. RM-3: lexicon scan at 0 hits in all arms, and the arm-guess check ≤ 60%.
3. The push/OTS chain is visible in the `origin/main` reflog for each of RM-6 (a)–(d).
4. All B/C/D contrasts are reported, whatever the direction.
5. RM-7: classifier acceptance result reported, and R-41 reported item-level.
6. 0 ruff/mypy errors; static gates pass; R-00 hashes intact.

## Interim reporting (until v3 lands)

Allowed:
> A pre-registered v2 run (165 disputed turns/arm) found more conflict disclosure under the burden contract than under a generic instruction (163 vs 121). Inter-judge agreement on the disputed turns was low (κ 0.06) because one judge was non-discriminating. A corrected re-run (v3) is in progress.

Not allowed: any all-turn κ presented as endpoint reliability; "robust across 3 judge families"; "redaction-blinded"; "the gate, not the instruction, does the work".

Stop after G4 v3 for review, then start G5.
