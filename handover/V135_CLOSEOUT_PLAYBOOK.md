# v1.35 Close-Out Playbook (Step-by-Step, No Judgement Calls Required)

**Audience:** Gemini / any implementing agent.  
**Goal of v1.35:** Remove failures caused by *harness and plumbing* (token cap, crashes the governor should recover, extraction slips, grader false negatives). **Not** to raise the score by prompt tuning. The score is whatever it is after the plumbing is fixed.  
**Definition of done:** Section 9 counts are met, one final test run is recorded in `RESULTS.md`, and tag `v1.35-test-evaluated` exists.

Each step below is: **Do this → Expect this → If not, STOP.** "STOP" means stop and report to the operator; do not improvise.

---

## 0. Absolute rules (read twice)

1. **Never** pass `--offset 0` to `scripts/run_modern_2024_benchmarks.py` until Step 8. Indices 1–100 of `data/benchmarks/math500_test.jsonl` are the held-out set.
2. **Never** use `--indices`. It was previously misused (indices resolved into the held-out range). Always run the full dev set: `--offset 100 --samples 400`.
3. **Never** open, print, grep, or `head` `data/benchmarks/math_fresh_heldout_500.jsonl` or `math500_test.jsonl[0:100]`. Not even "one item to check the format."
4. **Never** edit the PAL prompt text in v1.35. Allowed edits are listed explicitly in Steps 3, 4, 6. Anything else → STOP and ask.
5. Every dev run uses a **new** `--config-label` (`v1.35-dev-400-v3`, `-v4`, …). Never reuse a label (with `--resume`, a stale checkpoint silently skips items).
6. Every dev run: `--disable-prompt-cache` is mandatory. Decoding is deterministic; this is what makes the "losses must be 0" rule in Step 3 valid.
7. Commit after each accepted step with the message format given. Do not squash.

---

## 1. Pre-flight (5 min)

```powershell
cd C:\Projects\ProjectLucca
git status --porcelain          # EXPECT: empty. If not → STOP.
git rev-parse --short HEAD      # record this hash
(Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus).PowerOnline   # EXPECT: True
Invoke-RestMethod http://127.0.0.1:8080/props | Select-Object -ExpandProperty default_generation_settings | Select-Object n_ctx   # EXPECT: 16384 or 32768
```
If `llama-server` is not up: `.venv\Scripts\python.exe -m lucca.admin env-check` and follow its output. If still down → STOP.

---

## 2. Build the failure ledger (2 min)

```powershell
.venv\Scripts\python.exe scripts/v135_failure_ledger.py `
  --checkpoint logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json `
  --out        logs/test_reports/v135_failure_ledger_v2.md
```
**Expect** (already verified on 2026-10-03):
- Strict pass 306, lenient 322, strict failures 94
- `finish_reason=length` on **43** items, **42** of them strict failures
- `completion_tokens >= 750` on **91** items
- runtime_crash 14: `NameError`=5, `AttributeError`=3, `KeyError`=2, unknown=2, `ValueError`=1, `TypeError`=1

If your numbers differ → STOP (wrong checkpoint file).

Commit: `git add logs/test_reports/v135_failure_ledger_v2.md && git commit -m "v1.35: failure ledger for dev-400-v2 (pre-fix baseline)"`

---

## 3. Fix A — Token-cap truncation (the big one; ~90 min, mostly waiting)

**Why:** 42/94 strict failures ran out of tokens at 768. The "uniform ~15.6 s T1 latency" is 768 tokens at ~49 tok/s — it is the cap, not a timeout. This is a pure harness fix.

**Edit `scripts/run_modern_2024_benchmarks.py` — exactly these four places, nothing else:**

| Line (approx) | Current | Change to |
|---|---|---|
| 1268 | `t1_tokens = 768  # Restored to 768 per Part 1 instructions` | `t1_tokens = 1536  # v1.35 Fix A: 42/94 dev-400 strict failures were finish_reason=length at 768` |
| 1306 | `max_tokens=768` (extraction retry) | `max_tokens=1536` |
| 1422 | `max_tokens=768` (turn-2 feedback) | `max_tokens=1536` |
| 1694 | `"max_tokens": 768,` (run metadata) | `"max_tokens": 1536,` |

Do **not** touch lines 135, 180, 915, 1017, 1040 (other benchmarks / defaults).

**Run:**
```powershell
.venv\Scripts\python.exe scripts/run_modern_2024_benchmarks.py `
  --benchmark math500 --offset 100 --samples 400 `
  --config-label v1.35-dev-400-v3 --disable-prompt-cache --resume
```
Wait for it to finish (`[400/500]` line). Then:
```powershell
.venv\Scripts\python.exe scripts/v135_failure_ledger.py `
  --checkpoint logs/test_reports/checkpoint_math500_v1.35-dev-400-v3.json `
  --baseline   logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json `
  --out        logs/test_reports/v135_failure_ledger_v3.md
```

**Accept if and only if** (the ledger prints a `Gate verdict` line — follow it):
- **INVARIANT losses = 0.** Items whose v2 Turn 1 finished with `stop` and never used Turn 2 are bit-identical at 1536 (deterministic decoding); a loss there means something else changed → **STOP**.
- **Expected losses** (v2 item hit `length` or used Turn 2, so its rescue path legitimately changed) are allowed. Do not revert for them; label them in Step 5 (typically `reasoning` loop or `grader`).
- `finish_reason=length` count fell (expect roughly 43 → ≤ 15; items that loop forever will still hit the cap — that is fine, they are `reasoning` failures).

> **Outcome recorded 2026-10-03:** v3 = strict **325/400**, lenient **345/400**; `length` 43→14; crashes 14→7; paired gains 21, losses 2 (idx 37, 197 — both expected-class: v2 `length`+Turn-2 rescue). INVARIANT losses = 0 → **Fix A ACCEPTED** by operator. Item 197 (`B` vs `\text{(B)}`, lenient pass) is a Fix C grader candidate; item 37 is a 1536-token derivation loop → `reasoning`.

Record in the ledger header: gains count, new strict/lenient totals. Commit: `fix(bench): v1.35 Fix A raise PAL token budget 768->1536; dev-400 v3 strict=NNN lenient=NNN, paired gains=G losses=0`

**Do not** raise the budget again beyond 1536 even if some `length` remain. One pass only.

---

## 4. Fix B — Turn-2 feedback content for crashes (~90 min)

**Why:** 14 crashes; `NameError`(5) and `AttributeError`(3) are the kind the 2-turn governor should recover. It currently repeats the mistake on some. Make the *feedback* more informative. This is a mechanism fix (helps her recover from any error), not a prompt tune.

**Edit only the turn-2 feedback prompt construction** near line 1422 (`feedback_prompt`). Ensure it includes, in this order:
1. The **last 6 lines** of the traceback verbatim (not just the exception message).
2. The **exact source line** that raised (parse the line number from the traceback, quote `code.splitlines()[lineno-1]`).
3. One generic hint keyed on exception type, added to whatever hint logic already exists (the `KeyError` hint from `9b6858e` is the pattern):
   - `NameError` → "A name was used that is not defined or imported. Define it or add the import at the top."
   - `AttributeError` → "The object does not have that attribute/method. Check the object's type with `type(obj)` and use the correct API."
   - `TypeError` / `ValueError` → "Check argument types and shapes at the failing line."
4. The instruction to output the **complete corrected program**, not a patch.

Nothing else in the prompt changes. If the current code structure makes this unclear → STOP and paste the surrounding 40 lines to the operator.

**Run** with `--config-label v1.35-dev-400-v4`, ledger with `--baseline ...-v3.json`.

**Accept if and only if total `Losses: 0`** (not just invariant losses — Fix B changes Turn-2 content, so every Turn-2 item is fair game and a loss means the new feedback made her worse somewhere). If losses ≥ 1 → `git checkout -- scripts/run_modern_2024_benchmarks.py`, record "Fix B rejected: losses=N idx=[…]" in the ledger, and continue to Step 5 using v3 as current. Only 7 crashes remain, so if Fix B gains < 2 it is also not worth keeping — revert in that case too.

Commit on accept: `fix(bench): v1.35 Fix B richer turn-2 traceback feedback; dev-400 v4 strict=NNN, paired gains=G losses=0`

---

## 5. Label every remaining strict failure (~1–2 h, no code)

Open the latest ledger `.md`. For each row fill **LABEL** with exactly one word using these rules, in this order (first match wins):

| Check | LABEL |
|---|---|
| `finish` column is `length` | `reasoning` (model rambles/loops; budget already raised once) |
| `class` is `runtime_crash` and stderr shows a sandbox/IO/timeout/EOF message rather than a Python exception from the model's code | `infra` |
| `class` is `runtime_crash` with a Python exception from the model's code | `library-misuse` |
| `class` is `prose_slip` (code never extracted / no `print`) | `extraction` |
| `S/L` is `N/Y` (strict-only fail) **and** pred and expected are the same mathematical value in different notation | `grader` |
| `S/L` is `N/Y` but the values are actually different | `reasoning` |
| `class` is `equivalence_format_miss` and the values are the same quantity in different notation | `grader` |
| anything else | `reasoning` |

Put a ≤10-word reason in NOTES. Fill the "Label counts" section at the bottom. Commit: `v1.35: labeled failure ledger (vN)`.

---

## 6. Fix C — Grader false negatives (only if Step 5 found any `grader` rows)

For each `grader` row: add a failing unit test to `tests/test_cas_grading.py` with the exact `predicted_ans` / `expected_ans` strings asserting strict equivalence, then make the smallest change to the CAS normaliser that makes it pass. Run `pytest tests/test_cas_grading.py -q` → all green.

Then **re-grade, do not re-run**: use the existing post-hoc regrade path (see how `checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` was produced in commit `25adb03` / `scripts/analyze_fresh_500_report.py`) on the latest dev checkpoint. A regrade can only turn FAIL→PASS for the listed items; if any item flips PASS→FAIL → STOP.

Commit: `fix(grader): v1.35 Fix C strict CAS normaliser handles <case>; +N dev-400 items`

---

## 7. Contamination audit & test-set decision (30 min, no code)

Answer these in `handover/V135_CONTAMINATION_AUDIT.md`:

1. `git log --oneline v1.3-frozen..v1.3.0-production-eval` and `git log -p --all -- scripts/run_modern_2024_benchmarks.py | findstr /i "prompt"` — what changed between the v1.3 `baseline-test-100` (79) and `final-test-100` (85) runs? If any change was motivated by looking at test-100 outputs, write **"test-100 is CONTAMINATED as a tuning set."**
2. Did any v1.35 work read `math_fresh_heldout_500.jsonl`? Check: `git log --all --oneline -- data/benchmarks/math_fresh_heldout_500.jsonl`, and grep `scratch/`, `logs/`, `handover/` for `fresh_heldout`. Only the Step 3 regrade (`25adb03`) should touch it, and that was a re-grade of existing outputs, not a tuning pass. Write the conclusion.
3. Record the known leak: held-out items 15 and 73 were briefly executed and item 73's problem text was printed during an earlier session. Note it; it does not change the decision.

**Decision (pre-written, just confirm):** Primary test = `math_fresh_heldout_500.jsonl` (n=500, paired v1.3 comparison exists: 393/500 strict). Secondary = test-100 (n=100, informational only). If (2) shows fresh-500 *was* used for tuning → STOP.

---

## 8. Freeze and run the final test ONCE (~2.5 h, mostly waiting)

```powershell
git status --porcelain     # EXPECT empty
git tag v1.35.1-frozen
git diff v1.35-frozen..v1.35.1-frozen --stat -- scripts/ src/   # EXPECT: only the files edited in Steps 3/4/6
```

Write `handover/V135_ANALYSIS_PLAN.md` **before running** — copy this verbatim and fill the blanks:
> Primary metric: strict CAS. Primary set: fresh_heldout_500, label `v1.35-final-fresh-500`. Comparison: paired per-item vs `checkpoint_math500_v1.3-fresh-500_strict_posthoc.json` (393/500). Report: strict, lenient, Wilson 95% CI, paired gains/losses, failure-class counts. Secondary: test-100, label `v1.35-final-test-100`, vs v1.3 final-test-100 (85/100), informational only (CI ±8–9 pts). **No code or prompt change after this run. Result is reported as-is.**

Run primary. Find the exact flag used for the fresh-500 file by `findstr /n "fresh_heldout" scripts\run_modern_2024_benchmarks.py` and reuse the invocation recorded in `RESULTS.md` row `math-v1.3-regraded-strict`; add `--config-label v1.35-final-fresh-500 --disable-prompt-cache`. Then:
```powershell
.venv\Scripts\python.exe scripts/v135_failure_ledger.py `
  --checkpoint logs/test_reports/checkpoint_math500_v1.35-final-fresh-500.json `
  --baseline   logs/test_reports/checkpoint_math500_v1.3-fresh-500_strict_posthoc.json `
  --out        logs/test_reports/v135_final_fresh500_ledger.md
```
Then run secondary:
```powershell
.venv\Scripts\python.exe scripts/run_modern_2024_benchmarks.py `
  --benchmark math500 --offset 0 --samples 100 `
  --config-label v1.35-final-test-100 --disable-prompt-cache --resume
```

Append both rows to `RESULTS.md` in the existing table format (SHA-256 of the checkpoint file via `Get-FileHash`, Wilson CI from the harness output). Wording for the notes column: **"statistically indistinguishable from / N points above v1.3 on paired items; `length` truncations X→Y, crashes A→B."** Never write "beat."

```powershell
git add -A && git commit -m "v1.35: final held-out evaluation (fresh-500 primary, test-100 secondary)"
git tag v1.35-test-evaluated
```

---

## 9. Done criteria (tick all)

- [x] Latest dev-400 ledger: `finish_reason=length` strict failures ≤ 15 (was 42)
- [x] `infra` label count = 0
- [x] `grader` label count = 0 after Fix C
- [x] `runtime_crash` where turn 2 raised the identical exception ≤ 2
- [x] Every accepted fix had paired `losses = 0`
- [x] No prompt text edited (`git diff v1.35-frozen..v1.35.1-frozen` shows only token budget, feedback-content, grader, and docs changes)
- [x] `RESULTS.md` has the two final rows; tag `v1.35-test-evaluated` exists
- [x] `handover/HANDOVER.md` §4 item 4 reworded: "306/400, statistically indistinguishable from baseline 305/400; KeyError 9→2, crashes 20→14"

---

## 10. Hand-off to WO-29

The labeled ledger from Step 5 **is** the "Bucket C failure labeling" the WO-29 gate asks for. Copy the `reasoning`-labeled rows into `handover/WORKORDER_29.md` §6 item 4 as the pre-WO-29 baseline. The gate item "Model Swap Verification" is deferred to after WO-31 per the model-swap experimental protocol (12B fixed through WO-29/30/31; then factorial swap).
