# WO-45 Executor Prompt — paste this verbatim to the executing AI

You are executing **WO-45**, the remediation of WO-44 in Project Lucca. The full task list, with acceptance criteria (AC) and Return blocks, is in `plans/2026-11-09_wo45_wo44_review_remediation.md`. Read all of it before you start. This prompt adds binding rules about **how** you work and **how** you report.

## Why these rules exist

In WO-44 you reported fixes that were never made:
- "harness uses `build_launch_command()`": the script has no reference to it;
- "Arm A batched separately from Arm B": the loop still alternates per item;
- "`classify_hazard()` uses ClauseSplitter": it still classifies the whole string.

You also committed `web_evidentiary_burden_60_report.json` as a byte-identical copy of the 360 report, and you overwrote the pre-fix artifacts. A reviewer will verify every claim in your hand-back against the diff and the files. If a claim can't be verified, the task is marked FAILED, whatever the reason.

## Non-negotiable working rules

1. **No claim without evidence.** Every "done" statement in your hand-back must carry at least one of these:
   - the commit SHA plus the exact file:line of the change;
   - the verbatim terminal output of the AC check command, copied rather than summarised;
   - the artifact path plus its SHA-256.

   A statement with none of these counts as false.
2. **Intent is not completion.** Never write "aligned", "fixed", "batched", "wired" or "resolved" unless the AC command for that task has been run *after* the change and its output is pasted. If you planned something but didn't do it, write `NOT DONE`.
3. **Status vocabulary is fixed.** Use only `DONE` (every AC met, with evidence), `PARTIAL` (state exactly which AC failed), `BLOCKED` (state the blocker and what you tried), or `NOT STARTED`. Never round PARTIAL up to DONE.
4. **One task, one commit.** The commit message is `wo45(R-xx): <what changed>` plus the line `AI-assisted: <model name>`. Never squash. Never amend a pushed commit. Never force-push.
5. **Never modify, overwrite or delete existing measured artifacts.** R-00 records their hashes first, and the hand-back re-hashes them at the end. New results go in new files: `_v2` suffix, or under `logs/test_reports/wo45/`.
6. **Lock before you generate.** For R-14, R-21, R-32 and R-33 there must be three separate commits, in this order:
   1. the lock (hashes of all code and model files involved, *including* `src/lucca/core/neural_hazard_classifier.py`, plus an external timestamp);
   2. the corpus;
   3. the results.

   At run time, re-verify the lock hashes and save that output. If any locked file has to change after the lock, the lock is void: write a new lock and run again.
7. **A holdout is used once.** Once you have seen results on a holdout, you must not change code and re-run on that holdout. If you do, declare it `BURNED` and build a new one.
8. **Blinding.** Corpus authors, raters and judges are subagents. Their prompts must not contain:
   - arm names or model names;
   - the legal-standard vocabulary (balance of probabilities, clear and convincing, beyond reasonable doubt, speculation);
   - `_HEDGE_OR_CONFLICT_RE`;
   - anything from `src/lucca/`, prior results, or this WO.

   Save every subagent prompt verbatim under `logs/test_reports/wo45/prompts/`.
9. **No regex or script grading of meaning.** Scripts may only do structural checks: counts, hashes, schemas. Semantic labels come from at least 2 blinded judges using the §4 rubric, with Cohen's κ reported; below 0.70, a third judge adjudicates.
10. **The cache-reuse switch is banned.** `LUCCA_BENCH_REUSE_MODELS` must not be set for any reported run. Every model row in a report must carry `provenance: "fresh"`, the exact launch command, start and end UTC timestamps, and the llama-server build string.
11. **Negative results are reported, not fixed away.** If a hypothesis fails, report it with `(k/N, %)`, a CI and an error breakdown, then move on. Do not tune to make it pass.
12. **No publishing.** No GitHub release, no Reddit, LinkedIn or Zenodo, until the reviewer signs off on Phases 1–3. You may push commits to `main`.
13. **Writing standard.** No superlatives or exclamation marks, and nothing from the AGENTS.md §2.9 blacklist. Every number is written as `(k/N, XX.X%)` with an artifact path.
14. **If you're unsure, stop and ask.** Don't guess at a fact, a number or a file path. Put it under "Open issues" and ask.

## Execution order (gated)

| Gate | Tasks | Must be true before the next gate |
| :-- | :-- | :-- |
| G0 | R-00 | Baseline hashes committed |
| G1 | R-01, R-02, R-03, R-04, R-07, R-08, R-09, R-20, R-23 (disclosure part), R-30 (wording) | Every false or unsourced claim in the packet, Paper 4, README, `CAPABILITY_REGISTER.md` and `luccadocs/funding/` is corrected or retracted. A short **correction notice** is added to `README.md` and the packet listing what WO-44 overstated. **Push this gate immediately**, because WO-44 is already public. |
| G2 | R-05, R-06, R-22, R-31, R-40 | Harness rebuilt (real `build_launch_command()`, arm batching, provenance). Latency measured. Ablations and baselines run on the *existing* 360 (allowed: these are disclosed post-hoc analyses, not new holdout claims). |
| G3 | R-10 | Blinded re-grade of the **existing** 288 replies (already stored in `turn_records`; no regeneration). |
| G4 | R-14, then R-11, R-12, R-13, R-15, R-16, R-17 | v2 lock committed, *then* the v2 live run with Arms A/B/C (+D optional), unconditioned item selection, ≥96 items, a stock Gemma-4 model, and a mixed-effects or cluster-bootstrap analysis. |
| G5 | R-21 | Fresh multi-clause hazard holdout (lock → corpus → results). |
| G6 | R-32, R-33, R-41, R-42 | Real-web corpus, sybil/syndication set, utility cost, retraining only if pre-registered. |
| G7 | R-50, R-51, R-52, R-53 | Related-work table with verified DOIs, `lucca-epistemic` wheel tested in a clean venv, grant text citing WO-45 artifacts only. |
| G8 | Final | `uv run ruff check`, `uv run mypy`, `uv run pytest tests/test_static_gates.py`, **full** `uv run pytest` (report the total pass/fail/skip counts, not a subset), import-linter. Then write the hand-back. |

After each gate, write a short gate report to `logs/test_reports/wo45/GATE_Gx.md`, with the same structure as the §5 hand-back for that gate's tasks, and commit it. **Stop after G1 and G3** and wait for reviewer sign-off before you continue.

## Mandatory AC commands (run after the change, paste the output)

```
:: R-08
findstr /n "build_launch_command" scripts\run_web_evidentiary_burden_benchmark.py
findstr /n "LUCCA_BENCH_REUSE_MODELS" scripts\run_web_evidentiary_burden_benchmark.py
findstr /n "ClauseSplitter split_clauses" src\lucca\core\proof_policy.py
:: R-09
certutil -hashfile logs\test_reports\web_evidentiary_burden_360_report.json SHA256
certutil -hashfile logs\test_reports\web_evidentiary_burden_60_report.json SHA256
:: R-01
findstr /s /i /n "ed25519" papers\*.tex luccadocs\*.md README.md logs\test_reports\EXTERNAL_AI_REVIEW_PACKET_WO44.md
:: R-02
findstr /s /i /n "deontic_ov" papers\*.tex luccadocs\*.md README.md logs\test_reports\*.md
:: lock ordering (R-14, R-21, R-32, R-33)
git log --format="%h %ad %s" --date=iso -- logs/test_reports/wo45/
```

Expected results:
- R-08: the first command returns a hit, the second returns nothing (or only a line that raises an error if the variable is set), and the third returns a hit or is accompanied by retraction text.
- R-09: the two hashes differ, or the 60 file has been deleted and every claim citing it removed.
- R-01: nothing, or only lines that state Ed25519 is not used.
- R-02: nothing, or only corrected references.

## Hand-back

Write `logs/test_reports/wo45/WO45_HANDBACK.md` using exactly the template in §5 of the WO. Section B must have one row per R-ID, all 33 of them (R-00 to R-53). Section C sets every WO-44 headline number beside its WO-45 replacement, or beside `RETRACTED` / `UNSOURCED`. Section D lists every negative result. Then stop and tell the reviewer the hand-back commit SHA.
