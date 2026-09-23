# WO-16 — v1.0 Deep Clean: Execution Plan

> **Date:** 2026-09-24
> **Executor:** Gemini (delegated)
> **Reviewer:** User (manual review at each STOP gate)
> **Scope:** No new features. Archive stale docs/logs, re-run ALL tests as functional checks, audit every active document line-by-line against code, compile all open findings, fix all confirmed bugs.
> **Working Directory:** `C:\Projects\ProjectLucca`
> **Branch:** `master`
> **Starting Commit:** `b6fc285` (current `v1.0.0` tag)

---

## How To Use This Plan

1. Execute phases **in order**. Each phase has numbered milestones.
2. At every **🛑 STOP & REVIEW** gate, stop execution entirely, present evidence to the user, and wait for explicit approval before proceeding.
3. Every milestone has a **FUNCTIONAL CHECK** — a specific assertion about the meaning/content of results, not just "did the command exit 0."
4. If any functional check fails, stop immediately and report the failure with full context. Do NOT proceed.
5. Never guess values. Every number, path, and name must be verified against actual source code.

---

## Phase 1 — Archive Sweep

**Goal:** Move all stale documentation, historical audit artifacts, and pre-v1.0 test logs to named archive directories. Nothing is deleted. No code changes.

---

### Milestone 1.1 — Create Archive Directories

Run these commands:

```powershell
mkdir docs/archive/2026-09_audit_framework -ErrorAction SilentlyContinue
mkdir docs/archive/2026-09_eval_reports -ErrorAction SilentlyContinue
mkdir docs/archive/2026-09_evidence -ErrorAction SilentlyContinue
mkdir docs/archive/2026-09_raw_findings -ErrorAction SilentlyContinue
mkdir docs/archive/2026-09_closing_audits -ErrorAction SilentlyContinue
mkdir docs/archive/2026-09_milestone_specs -ErrorAction SilentlyContinue
mkdir docs/archive/2026-09_tickets -ErrorAction SilentlyContinue
mkdir logs/archive/pre_v1.0 -ErrorAction SilentlyContinue
```

**FUNCTIONAL CHECK:** All 8 directories exist on disk. Verify with:
```powershell
Get-ChildItem docs/archive/ -Directory | Select-Object Name
Get-ChildItem logs/archive/ -Directory | Select-Object Name
```
Expected: 8 archive directories (including the pre-existing `2026-09_handovers`).

---

### Milestone 1.2 — Archive Audit Framework Documents

These are the WO-8 audit charter, template, evidence index, baseline, and gap analysis docs. They describe the audit *process*, not v1.0 *truth*.

```powershell
git mv docs/audit/00_AUDIT_CHARTER.md docs/archive/2026-09_audit_framework/
git mv docs/audit/01_FINDING_TEMPLATE.md docs/archive/2026-09_audit_framework/
git mv docs/audit/02_EVIDENCE_INDEX.md docs/archive/2026-09_audit_framework/
git mv docs/audit/03_BASELINE.md docs/archive/2026-09_audit_framework/
git mv docs/audit/03b_BASELINE_DELTA.md docs/archive/2026-09_audit_framework/
git mv docs/audit/04_OWNER_DECISIONS.md docs/archive/2026-09_audit_framework/
git mv docs/audit/05_TEST_STRATEGY_GAP_ANALYSIS.md docs/archive/2026-09_audit_framework/
git mv docs/audit/COGNITIVE_LOOP_MAP.md docs/archive/2026-09_audit_framework/
```

**FUNCTIONAL CHECK:** 8 files moved. Verify:
```powershell
(Get-ChildItem docs/archive/2026-09_audit_framework/ -File).Count  # Must be exactly 8
Test-Path docs/audit/00_AUDIT_CHARTER.md  # Must be False
```

---

### Milestone 1.3 — Archive Historical Eval Reports

```powershell
git mv docs/audit/COMPREHENSIVE_100_EVAL_REPORT.md docs/archive/2026-09_eval_reports/
git mv docs/audit/DIAGNOSTIC_EVAL_V2_REPORT.md docs/archive/2026-09_eval_reports/
git mv docs/eval/COMPREHENSIVE_100_EVAL_REPORT.md docs/archive/2026-09_eval_reports/COMPREHENSIVE_100_EVAL_REPORT_eval.md
git mv docs/eval/DIAGNOSTIC_EVAL_V2_REPORT.md docs/archive/2026-09_eval_reports/DIAGNOSTIC_EVAL_V2_eval.md
git mv docs/eval/LIVE_AI_VERIFICATION_REPORT.md docs/archive/2026-09_eval_reports/
```

**FUNCTIONAL CHECK:** 5 files moved. The `docs/eval/` directory should be empty (only `__pycache__` or empty). Verify:
```powershell
(Get-ChildItem docs/archive/2026-09_eval_reports/ -File).Count  # Must be 5
Get-ChildItem docs/eval/ -File -Filter "*.md"  # Must return nothing
```

> [!WARNING]
> If git mv fails because a file already exists at the target (e.g., duplicate names), rename with a suffix like `_audit_copy.md` and note it. Do NOT silently skip.

---

### Milestone 1.4 — Archive Historical Evidence

```powershell
git mv docs/audit/evidence/BRAIN_BAKEOFF_2026-09-21.md docs/archive/2026-09_evidence/
git mv docs/audit/evidence/S1_SUMMARY.md docs/archive/2026-09_evidence/
```

**FUNCTIONAL CHECK:** 2 files moved.
```powershell
Get-ChildItem docs/audit/evidence/ -File -Filter "*.md" | Select-Object Name  # Should be empty
```

---

### Milestone 1.5 — Archive Raw WO-8 Module Finding Dumps

These are the massive (40–216 KB) raw audit findings from WO-8. They contain resolved findings but also **open items that must be extracted first** (Phase 2). **Do NOT archive them yet.** Instead, mark them for Phase 2 extraction. For now, archive only the files whose findings are ALL resolved.

Files where ALL findings are resolved (safe to archive now):
```powershell
# WO-8 work product findings (all resolved per AUDIT_REMEDIATION_LOG.md)
git mv docs/audit/findings/WO8_WP4_findings_2026-09-21.md docs/archive/2026-09_closing_audits/
git mv docs/audit/findings/WO8_WP5_findings_2026-09-22.md docs/archive/2026-09_closing_audits/
git mv docs/audit/findings/WO8_WP5-5_findings_2026-09-22.md docs/archive/2026-09_closing_audits/

# WO-11, WO-12, WO-13 closing audits (all resolved)
git mv docs/audit/findings/WO11_CLOSING_AUDIT.md docs/archive/2026-09_closing_audits/
git mv docs/audit/findings/WO12_CLOSING_AUDIT.md docs/archive/2026-09_closing_audits/
git mv docs/audit/findings/WO13_CLOSING_AUDIT.md docs/archive/2026-09_closing_audits/

# WO-12 research sub-reports (all resolved)
git mv docs/audit/findings/WO12_0_SPEC_CONFORMANCE_AUDIT.md docs/archive/2026-09_closing_audits/
git mv docs/audit/findings/WO12_3_G3_DIGIT_NARRATION_RESEARCH.md docs/archive/2026-09_closing_audits/
git mv docs/audit/findings/WO12_4_FAULT_MODE_C_RESEARCH.md docs/archive/2026-09_closing_audits/
git mv docs/audit/findings/WO12_5_SPOKEN_REVISION_VERIFICATION.md docs/archive/2026-09_closing_audits/
git mv docs/audit/findings/WO13_4_PERSONA_UNDER_PRESSURE.md docs/archive/2026-09_closing_audits/

# Fully-resolved fuzzing report
git mv docs/audit/findings/extended_fuzzing_audit_report.md docs/archive/2026-09_closing_audits/
```

**FUNCTIONAL CHECK:**
```powershell
(Get-ChildItem docs/archive/2026-09_closing_audits/ -File).Count  # Must be exactly 12
```

---

### Milestone 1.6 — Archive Stale Specs, Reports & Miscellaneous

```powershell
git mv docs/specs/MILESTONE_1_MEASUREMENT_PLAN.md docs/archive/2026-09_milestone_specs/
git mv docs/specs/MILESTONE_4_IMPLEMENTATION_PLAN.md docs/archive/2026-09_milestone_specs/
git mv docs/specs/NEUROSYMBOLIC_REMEDIATION_STRATEGY.md docs/archive/2026-09_milestone_specs/
git mv docs/RECON_REPORT.md docs/archive/2026-09_milestone_specs/
git mv docs/AUDIT_REMEDIATION_LOG.md docs/archive/2026-09_milestone_specs/
git mv docs/NEUROSYMBOLIC_RESEARCH_PAPER.md docs/archive/2026-09_milestone_specs/

# Resolved ticket
git mv docs/tickets/TICKET-REAS-001_counterfactual_shadow_audit.md docs/archive/2026-09_tickets/
```

**FUNCTIONAL CHECK:**
```powershell
(Get-ChildItem docs/archive/2026-09_milestone_specs/ -File).Count  # Must be 6
(Get-ChildItem docs/archive/2026-09_tickets/ -File).Count  # Must be 1
```

---

### Milestone 1.7 — Archive Pre-v1.0 Test Report Logs

```powershell
Get-ChildItem logs/test_reports/ -File | Where-Object { $_.LastWriteTime -lt "2026-09-23" } | ForEach-Object { git mv $_.FullName logs/archive/pre_v1.0/ }
```

**FUNCTIONAL CHECK:**
```powershell
$pre = (Get-ChildItem logs/archive/pre_v1.0/ -File).Count
$post = (Get-ChildItem logs/test_reports/ -File).Count
Write-Host "Archived: $pre, Remaining: $post"
# Archived should be approximately 71
# Remaining should be approximately 41
```

---

### Milestone 1.8 — Add README Markers to Research & Archive

Create `docs/research/README.md`:
```markdown
# Research Reference (Read-Only)

This directory contains academic research papers, literature reviews, and design
explorations created during Project Lucca's development. These documents are
**read-only reference material** and are NOT part of the active documentation
corpus. They are not maintained or updated.

For current project truth, see the 10 active documents enforced by the staleness
linter in `tests/test_static_gates.py`.
```

**FUNCTIONAL CHECK:** File exists and contains "read-only reference".

---

### Milestone 1.9 — Commit Archive Sweep

```powershell
git add -A
git status  # Review: ONLY moves/renames and the new README.md
git commit -m "WO-16 Phase 1: Archive sweep — stale docs, eval reports, evidence, closing audits, specs, pre-v1.0 test logs"
```

**FUNCTIONAL CHECK:**
```powershell
git diff --stat HEAD~1..HEAD  # Should show ONLY rename operations and 1 new file
```

### 🛑 STOP & REVIEW — Phase 1

Present to the user:
1. Count of files archived per directory
2. `git status` output (must be clean)
3. `git diff --stat HEAD~1..HEAD` output
4. List of files remaining in `docs/audit/findings/` (should be: `V1_RELEASE_AUDIT.md`, `WO15_EVIDENCE.md`, `README.md`, `adjacent_defects_diagnostic_summary.md`, plus the 11 raw module dumps that still need Phase 2 extraction)

**Wait for user approval before Phase 2.**

---

## Phase 2 — Open Item Extraction

**Goal:** Read every remaining un-archived audit finding document. Extract ALL findings that are still open/unresolved. Produce a single consolidated `docs/V2_ACTION_LOG.md`.

---

### Milestone 2.1 — Extract Open Findings from Raw Module Dumps

The following files contain a mix of resolved and open findings. For each file, read the ENTIRE document and classify every finding.

**Files to process (these remain in `docs/audit/findings/`):**

| File | Size | Known Open Count (from Agent 1 research) |
|---|---|---|
| `arch.md` | 24 KB | 0 (all 8 resolved in AUDIT_REMEDIATION_LOG) |
| `rout.md` | 41 KB | 8 open (F-ROUT-003, 004, 006–011) |
| `drift.md` | 39 KB | 5 open (F-DRIFT-002, 004, 007, 009, 010) |
| `brain.md` | 205 KB | Scan needed |
| `core.md` | 216 KB | Scan needed |
| `mem.md` | 69 KB | Scan needed |
| `sbx.md` | 53 KB | Scan needed |
| `sens.md` | 51 KB | Scan needed |
| `test.md` | 43 KB | Scan needed |
| `ui.md` | 43 KB | Scan needed |
| `reas.md` | 48 KB | Scan needed |
| `COGNITIVE_AUDIT_2026-09.md` | 20 KB | 7 open (F11–F13, F15, F19–F21) |
| `CAPABILITY_FACT_FINDING_2026-09.md` | 14 KB | 1 open (G3) |
| `adjacent_defects_diagnostic_summary.md` | 7 KB | 17 open |

**For each file, the executor must:**

1. Open the file and read it completely (use multiple view_file calls for large files)
2. Find every section labeled as a "Finding", "Issue", "Defect", or similar
3. For each finding, determine if it is RESOLVED or OPEN by checking:
   - Does the finding text say "RESOLVED", "FIXED", "CLOSED"?
   - Does the finding cite a commit hash?
   - Cross-reference against `docs/archive/2026-09_milestone_specs/AUDIT_REMEDIATION_LOG.md` for resolution status
4. Record all OPEN findings

**FUNCTIONAL CHECK per file:** Report the counts: `"File X: N total findings, M resolved, K open. Open IDs: [list]"`

---

### Milestone 2.2 — Classify Open Findings

For each open finding extracted in 2.1, classify it as one of:

- **BUG_V1** — A bug in existing v1.0 feature code that causes incorrect behavior (fix in Phase 5)
- **DOC_DRIFT** — A documentation claim that doesn't match code (fix in Phase 4)
- **DESIGN_DEBT** — A design limitation known at v1.0 ship, acceptable for now (defer to V2_BACKLOG)
- **TEST_GAP** — A missing test for existing behavior (fix in Phase 5)

**FUNCTIONAL CHECK:** Every open finding has exactly one classification. No finding is left unclassified.

---

### Milestone 2.3 — Write V2_ACTION_LOG.md

Create `docs/V2_ACTION_LOG.md` with the following structure:

```markdown
# v1.0 Action Log — Open Findings & Bug Tracker

**Generated:** 2026-09-24 (WO-16 Phase 2)
**Source:** Exhaustive scan of all WO-8 through WO-15 audit findings

## Summary

| Classification | Count |
|---|---|
| BUG_V1 (fix now) | N |
| DOC_DRIFT (fix in Phase 4) | N |
| DESIGN_DEBT (defer to V2) | N |
| TEST_GAP (fix in Phase 5) | N |
| **Total open** | N |

## Items

### [ITEM-001] <title>
- **Source:** `docs/audit/findings/<file>.md`, Finding <ID>
- **Classification:** BUG_V1 | DOC_DRIFT | DESIGN_DEBT | TEST_GAP
- **Severity:** Critical | High | Medium | Low
- **Feature Area:** core | router | sandbox | memory | audio | ui | reasoning
- **Description:** <what is wrong>
- **Code Location:** <file:line if applicable>
- **User-Visible Impact:** Yes/No — <description if yes>
- **Resolution Path:** Fix in WO-16 Phase 5 | Fix in WO-16 Phase 4 | Defer to V2_BACKLOG
- **Status:** OPEN
```

**FUNCTIONAL CHECK:** Every open finding from Milestone 2.1 appears exactly once. Count the items — must match the sum from 2.1.

---

### Milestone 2.4 — Archive the Raw Dumps

Now that open items have been extracted, archive all remaining raw module dumps:

```powershell
git mv docs/audit/findings/arch.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/brain.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/core.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/drift.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/mem.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/reas.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/rout.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/sbx.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/sens.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/test.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/ui.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/COGNITIVE_AUDIT_2026-09.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/CAPABILITY_FACT_FINDING_2026-09.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/adjacent_defects_diagnostic_summary.md docs/archive/2026-09_raw_findings/
git mv docs/audit/findings/adjacent_defects_diagnostic_results.json docs/archive/2026-09_raw_findings/
```

**FUNCTIONAL CHECK:**
```powershell
# After archiving, docs/audit/findings/ should contain ONLY these files:
Get-ChildItem docs/audit/findings/ -File | Select-Object Name
# Expected: V1_RELEASE_AUDIT.md, WO15_EVIDENCE.md, README.md
```

---

### Milestone 2.5 — Commit Phase 2

```powershell
git add -A
git commit -m "WO-16 Phase 2: Open item extraction — V2_ACTION_LOG.md created, raw findings archived"
```

### 🛑 STOP & REVIEW — Phase 2

Present to the user:
1. Full contents of `docs/V2_ACTION_LOG.md`
2. Classification summary table (BUG_V1 / DOC_DRIFT / DESIGN_DEBT / TEST_GAP counts)
3. The list of BUG_V1 items specifically — these will be fixed in Phase 5
4. `docs/audit/findings/` directory listing (should have only 3 files)

**Wait for user approval before Phase 3.**

---

## Phase 3 — Full Test Suite Re-Run & Canonical Baseline

**Goal:** Produce one definitive test baseline for the v1.0 source tree. Every test must be run. Every failure must be investigated (not just counted).

---

### Milestone 3.1 — Run Full Non-HW Test Suite

```powershell
uv run python -m pytest tests/ `
  --ignore=tests/test_capability_assessment_live_hw.py `
  --ignore=tests/test_a1_live_hw.py `
  --ignore=tests/test_phase1_live_hw.py `
  --ignore=tests/test_phase2_live_hw.py `
  --ignore=tests/test_rag_live_hw.py `
  --ignore=tests/test_research_live_hw.py `
  --ignore=tests/test_soak_live_hw.py `
  -v --tb=long 2>&1 | Tee-Object logs/test_reports/baseline_v1.0.0_non_hw.txt
```

**FUNCTIONAL CHECKS (not just pass/fail):**

1. **Total test count:** Must be ≥ 649. Record exact number.
2. **Failure count:** Must be 0. If any test fails:
   - Read the full traceback
   - Determine: is it a real bug, a flaky test, or an environment issue?
   - Add to `V2_ACTION_LOG.md` as BUG_V1 or TEST_GAP
   - Do NOT proceed to Phase 4 until all failures are understood and documented
3. **Deselected count:** Record exact number and reason (should be `hw` markers only)
4. **Warning check:** Scan the output for `DeprecationWarning`, `FutureWarning`, or `PytestUnraisableExceptionWarning`. If any found, note them in `V2_ACTION_LOG.md`.

---

### Milestone 3.2 — Run Static Analysis Suite

```powershell
# Ruff lint
uv run ruff check src/ tests/ 2>&1 | Tee-Object logs/test_reports/baseline_v1.0.0_ruff.txt

# Ruff format
uv run ruff format --check src/ tests/ 2>&1 | Tee-Object logs/test_reports/baseline_v1.0.0_format.txt

# Import linter (if configured)
uv run lint-imports 2>&1 | Tee-Object logs/test_reports/baseline_v1.0.0_imports.txt

# Staleness lint
uv run python -m pytest tests/test_static_gates.py -v 2>&1 | Tee-Object logs/test_reports/baseline_v1.0.0_static_gates.txt
```

**FUNCTIONAL CHECKS:**

1. **Ruff lint:** 0 errors. If any errors, categorise (real issue vs. false positive) and log.
2. **Ruff format:** All files clean. Record file count inspected.
3. **Import linter:** All contracts kept. Record N/N.
4. **Static gates:** All tests pass. Record exact count (should be ≥ 12).

---

### Milestone 3.3 — Run Live Hardware Acceptance (C1 + A1)

```powershell
# C1 Conformal Abstention
uv run python -m pytest tests/test_c1_abstention_acceptance.py -v --tb=long 2>&1 | Tee-Object logs/test_reports/baseline_v1.0.0_c1.txt

# A1 Capability Assessment
uv run python -m pytest tests/test_capability_assessment_live_hw.py -m hw -v --tb=long 2>&1 | Tee-Object logs/test_reports/baseline_v1.0.0_a1_caps.txt

# A1 Live Hardware
uv run python -m pytest tests/test_a1_live_hw.py -m hw -v --tb=long 2>&1 | Tee-Object logs/test_reports/baseline_v1.0.0_a1_live.txt
```

**FUNCTIONAL CHECKS:**

1. **C1 offline twin:** Passes. Wilson LB ≥ 0.80. Record exact value.
2. **C1 live HW turns:** All pass. Record exact turn count.
3. **A1 gates:** All 6 gates pass. List each gate name and result.
4. **TTFT observation:** If any test reports TTFT, record the value. Must be < 1500 ms.

---

### Milestone 3.4 — Commit Baseline Artifacts

```powershell
git add logs/test_reports/baseline_v1.0.0_*.txt
git commit -m "WO-16 Phase 3: Canonical v1.0 test baseline — all suites re-run"
```

### 🛑 STOP & REVIEW — Phase 3

Present to the user:
1. Test count summary: `N passed, M failed, K deselected, J warnings`
2. Static analysis summary: `ruff: 0 errors, format: N files clean, imports: N/N`
3. Live HW summary: `C1 Wilson LB = X.XXXX, A1 6/6 gates`
4. Any new items added to `V2_ACTION_LOG.md`

**Wait for user approval before Phase 4.**

---

## Phase 4 — Line-by-Line Active Document Audit

**Goal:** Every factual claim in the 10 active documents verified against source code. Every error corrected.

> [!CAUTION]
> **KNOWN ERRORS THAT MUST BE FOUND AND FIXED.** If the executor does NOT find and fix ALL of the following, the audit has failed and must be re-done:
>
> 1. `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17` says "**15** sandboxed tools" — actual count in `capabilities.py` is **18** (count the `name=` assignments in `get_default_native_tools()`)
> 2. `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17` says "capped at **16**" — actual cap is `MAX_REGISTRY_TOOLS = 18` at `capabilities.py:34`
> 3. `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17` says "**7** cascade substrates" — actual count in `cascade.py` `EpistemicSubstrate` enum is **8** (TELEMETRY=0 through SELF_HISTORY=7)
> 4. `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17` references `cascade.py:SUBSTRATE_ORDER` — this constant **does not exist** in the source
> 5. `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17` references `lifecycle.py:MAX_ACTIVE_RULES` — this constant **does not exist** in the source
> 6. `README.md` line 35 says "5-Substrate Epistemic Search Cascade" — actual is **8** substrates
> 7. `docs/specs/STUDIO_CAPABILITY_ROADMAP.md` multiple lines reference "≤16 native tools" — actual cap is **18**

---

### Milestone 4.1 — Verify Constants Against Code

Before touching any document, independently establish the ground truth by reading code:

```powershell
# 1. Tool count: Count lines matching 'name="' in get_default_native_tools
Select-String -Path src/lucca/core/capabilities.py -Pattern 'name="' | Measure-Object

# 2. Tool cap constant
Select-String -Path src/lucca/core/capabilities.py -Pattern 'MAX_REGISTRY'

# 3. Substrate count: Count enum members in EpistemicSubstrate
Select-String -Path src/lucca/core/cascade.py -Pattern '^\s+[A-Z_]+ = \d+$'

# 4. Rule cap: Search for any constant capping active rules
Select-String -Path src/lucca/reasoning/lifecycle.py -Pattern 'MAX|cap|limit' -CaseSensitive:$false

# 5. Convergence loop limits
Select-String -Path src/lucca/core/orchestrator.py -Pattern 'MAX_ROUNDS|max_round|M=4|M=8|hard_cap|active_limit'

# 6. Model filename
Select-String -Path models/MANIFEST.json -Pattern 'filename|model'

# 7. Context length
Select-String -Path launch_server.ps1 -Pattern 'ctx|context|16384|16K'
```

**FUNCTIONAL CHECK:** Record every ground-truth value in a table:

| Constant | Expected Location | Actual Value | What Docs Currently Say |
|---|---|---|---|
| Native tool count | `capabilities.py` `get_default_native_tools()` | ? | 15 |
| Tool cap | `capabilities.py:34` `MAX_REGISTRY_TOOLS` | ? | 16 |
| Substrate count | `cascade.py` `EpistemicSubstrate` enum | ? | 7 |
| Rule cap | `lifecycle.py` | ? | 30 |
| Convergence active limit | `orchestrator.py` | ? | M=4 |
| Convergence hard cap | `orchestrator.py` | ? | M=8 |
| Model filename | `models/MANIFEST.json` | ? | gemma-4-12b-heretic-Q6_K.gguf |
| Context length | `launch_server.ps1` | ? | 16K |

This table is the **single source of truth** for all document corrections. If any value differs from what the docs say, the docs are wrong and must be fixed.

---

### Milestone 4.2 — Audit & Fix Each Active Document

For **each** of the 10 active documents, perform:

1. **Read the entire file** (use multiple view_file calls as needed)
2. **For every claim** that references a number, path, class name, constant name, or test file:
   - Verify it against the code
   - If WRONG: fix it
   - If the referenced path/constant doesn't exist: fix the reference
3. **For every module path mentioned** (e.g., `src/lucca/foo/bar.py`): verify it exists on disk
4. **For every test file mentioned** (e.g., `tests/test_foo.py`): verify it exists on disk
5. **Record what was changed** with before/after for each fix

**Documents to audit (in order):**

1. **`docs/USER_GUIDE_WHAT_LUCCA_DOES.md`** — Highest priority. Contains the known errors above.
2. **`README.md`** — Root project README; references substrate count, architecture diagram, model name
3. **`docs/ARCHITECTURE.md`** — Process names, module paths, convergence limits, tool caps
4. **`docs/MODEL_STRATEGY.md`** — Model filename, quantization, VRAM budget, TTFT
5. **`docs/DECISIONS.md`** — ADR references, cited code paths
6. **`docs/V2_BACKLOG.md`** — Deferred items must NOT be implemented in current code
7. **`docs/specs/STUDIO_CAPABILITY_ROADMAP.md`** — Status column, tool cap references
8. **`docs/audit/findings/V1_RELEASE_AUDIT.md`** — Gate verdicts, evidence file paths
9. **`AGENTS.md`** — File paths, class names
10. **`GEMINI.md`** — Instructions, file paths

**Per-document FUNCTIONAL CHECK:**

For each document, produce a mini-report:
```
Document: <filename>
Lines read: <N>
Claims verified: <N>
Errors found: <N>
Errors fixed: <list of line:old→new>
Module paths verified: <N> exist, <N> missing
Test files verified: <N> exist, <N> missing
```

---

### Milestone 4.3 — Update Staleness Lint Patterns

After fixing documents, the staleness linter in `tests/test_static_gates.py` may need updated patterns. Check:

1. If the tool cap changed from 16 → 18, any assertion checking `<= 16` must change to `<= 18`
2. If substrate count changed from 7 → 8, any assertion must update
3. If `SUBSTRATE_ORDER` was a lint target, it must be removed or replaced with the actual constant name

```powershell
Select-String -Path tests/test_static_gates.py -Pattern "16|SUBSTRATE_ORDER|MAX_ACTIVE_RULES|15 sandboxed|7 cascade"
```

**FUNCTIONAL CHECK:** Run the staleness lint:
```powershell
uv run python -m pytest tests/test_static_gates.py -v
```
Must pass. If it fails, the document fix introduced a new staleness lint failure — fix the pattern or the document.

---

### Milestone 4.4 — Commit Phase 4

```powershell
git add -A
git commit -m "WO-16 Phase 4: Line-by-line document audit — all 10 active docs verified against code"
```

### 🛑 STOP & REVIEW — Phase 4

Present to the user:
1. The complete per-document audit report (10 mini-reports from 4.2)
2. The ground-truth constants table (from 4.1)
3. `git diff HEAD~1..HEAD` showing every document change
4. Staleness lint output (must be green)
5. **Explicit confirmation:** "The following 7 known errors were found and fixed: [list]" — if any of the 7 known errors from the caution box were NOT found, explain why

**Wait for user approval before Phase 5.**

---

## Phase 5 — Bug Fix Pass

**Goal:** Fix all items in `V2_ACTION_LOG.md` classified as `BUG_V1` or `TEST_GAP`. Each fix gets its own commit with a regression test.

---

### Milestone 5.1 — Triage BUG_V1 Items

Read `docs/V2_ACTION_LOG.md`. List every item where `Classification: BUG_V1` or `Classification: TEST_GAP`.

For each item:
1. Read the referenced code location
2. Verify the bug still exists on the current HEAD
3. If the bug was already fixed in a prior WO (and the finding doc was just stale), mark it `RESOLVED (already fixed)` and cite the commit
4. If the bug is real and still present, write the fix

**FUNCTIONAL CHECK:** For each item, report:
```
ITEM-NNN: <title>
  Still present: Yes/No
  If Yes: Fix description + new test name
  If No: Already resolved in commit <hash>
```

---

### Milestone 5.2 — Implement Fixes

For each confirmed bug:

1. Write the code fix
2. Write a regression test that:
   - **Fails before the fix** (verify by temporarily reverting if needed, or by testing the specific bad path)
   - **Passes after the fix**
   - Tests the **functional behavior**, not just that the function doesn't crash
3. Commit with message: `fix(<area>): <description> [V2_ACTION_LOG ITEM-NNN]`
4. Update `V2_ACTION_LOG.md`: change `Status: OPEN` to `Status: RESOLVED` and add `Commit: <hash>`

**FUNCTIONAL CHECK per fix:**
```powershell
# The specific new test passes
uv run python -m pytest tests/test_<relevant>.py::<new_test_name> -v

# The full suite still passes (no regressions)
uv run python -m pytest tests/ --ignore=tests/test_*live_hw.py -q --tb=short
```

---

### Milestone 5.3 — Mark Deferred Items in V2_BACKLOG.md

For every item in `V2_ACTION_LOG.md` classified as `DESIGN_DEBT`:
1. Verify it already has a corresponding entry in `docs/V2_BACKLOG.md`
2. If not, add it with a trigger condition
3. Cross-reference: `V2_ACTION_LOG.md` gets `Resolution Path: Tracked in V2_BACKLOG.md`

**FUNCTIONAL CHECK:**
```powershell
# Count DESIGN_DEBT items in ACTION_LOG
Select-String -Path docs/V2_ACTION_LOG.md -Pattern "DESIGN_DEBT" | Measure-Object
# Count entries in V2_BACKLOG
Select-String -Path docs/V2_BACKLOG.md -Pattern "^###|^- " | Measure-Object
# V2_BACKLOG must have at least as many entries as DESIGN_DEBT items
```

---

### Milestone 5.4 — Regression Verification

```powershell
# Full non-HW suite
uv run python -m pytest tests/ --ignore=tests/test_*live_hw.py -v --tb=short 2>&1 | Tee-Object logs/test_reports/post_fixes_v1.0.0.txt

# Ruff
uv run ruff check src/ tests/

# Staleness lint
uv run python -m pytest tests/test_static_gates.py -v
```

**FUNCTIONAL CHECKS:**
1. Test count must be ≥ the Phase 3 baseline count (fixes should add tests, not remove them)
2. 0 failures
3. Ruff clean
4. Staleness lint green

### 🛑 STOP & REVIEW — Phase 5

Present to the user:
1. List of all BUG_V1 items: which were fixed, which were already resolved
2. Each fix: commit hash, regression test name, brief description
3. Post-fix test results: `N passed, 0 failed`
4. Updated `V2_ACTION_LOG.md` summary table

**Wait for user approval before Phase 6.**

---

## Phase 6 — Final Audit Update & Re-Tag

**Goal:** Update the release audit, commit, and re-tag v1.0.0.

---

### Milestone 6.1 — Update V1_RELEASE_AUDIT.md

Add a new section to `docs/audit/findings/V1_RELEASE_AUDIT.md`:

```markdown
## 5. WO-16 Deep Clean Certificate (2026-09-24)

### 5.1 Archive Summary
| Archive Directory | Files Moved |
|---|---|
| ... | ... |

### 5.2 Open Item Extraction
- Total findings scanned across WO-8–WO-15 audits: N
- Resolved: N
- Open: N (tracked in V2_ACTION_LOG.md)
  - BUG_V1 (fixed): N
  - DOC_DRIFT (fixed): N
  - DESIGN_DEBT (deferred to V2_BACKLOG.md): N
  - TEST_GAP (fixed): N

### 5.3 Test Baseline
- Non-HW suite: N passed, 0 failed
- Static analysis: ruff clean, N/N import contracts
- Live HW: C1 Wilson LB = X.XXXX, A1 N/N gates

### 5.4 Document Audit
- 10 active documents audited line-by-line against source code
- Errors found and corrected: N
- Known error checklist: 7/7 found and fixed

### 5.5 Bugs Fixed
| ITEM | Description | Commit |
|---|---|---|
| ... | ... | ... |
```

---

### Milestone 6.2 — Final Commit & Re-Tag

```powershell
git add -A
git commit -m "WO-16: v1.0 deep clean — archive sweep, open item extraction, test re-baseline, doc audit, bug fixes"

# Delete old tag and re-create
git tag -d v1.0.0
git tag -a v1.0.0 -m "Project Lucca v1.0.0 — WO-16 deep clean applied"
```

**FUNCTIONAL CHECKS:**
```powershell
git tag -n v1.0.0      # Must show the new tag message
git log -1 --oneline   # Must show WO-16 commit
git status              # Must be clean
```

---

### Milestone 6.3 — Final Verification Pass

```powershell
# Everything still passes after the tag
uv run python -m pytest tests/ --ignore=tests/test_*live_hw.py -q --tb=short
uv run ruff check src/ tests/
uv run python -m pytest tests/test_static_gates.py -v
```

### 🛑 STOP & REVIEW — Phase 6 (Final)

Present to the user:
1. `git log -5 --oneline`
2. `git tag -n v1.0.0`
3. Final test results
4. Contents of the WO-16 Deep Clean Certificate (§5 of V1_RELEASE_AUDIT.md)
5. Summary counts:
   - Files archived: N
   - Open findings extracted: N
   - Bugs fixed: N
   - Document errors corrected: N
   - Tests in final baseline: N

**This is the final deliverable. WO-16 is complete.**

---

## Appendix A — Files That Must Remain in `docs/audit/findings/` After WO-16

Only these files should remain (not archived):

1. `V1_RELEASE_AUDIT.md` — The live release audit (updated)
2. `WO15_EVIDENCE.md` — Phase-by-phase remediation evidence
3. `README.md` — Index/description of findings directory

Everything else has been archived.

## Appendix B — Files That Must Remain as Active Documents

The staleness linter enforces these 10 files. If any file is renamed or removed, the linter must be updated first.

1. `AGENTS.md`
2. `GEMINI.md`
3. `README.md`
4. `docs/ARCHITECTURE.md`
5. `docs/DECISIONS.md`
6. `docs/MODEL_STRATEGY.md`
7. `docs/USER_GUIDE_WHAT_LUCCA_DOES.md`
8. `docs/V2_BACKLOG.md`
9. `docs/specs/STUDIO_CAPABILITY_ROADMAP.md`
10. `docs/audit/findings/V1_RELEASE_AUDIT.md`

## Appendix C — Known Errors the Executor MUST Find

These are factual errors confirmed by code inspection. The executor's audit in Phase 4 MUST catch all of them. If any are missed, the audit is incomplete.

| # | Document | Line | Error | Correct Value | How to Verify |
|---|---|---|---|---|---|
| 1 | `USER_GUIDE_WHAT_LUCCA_DOES.md` | 17 | Says "15 sandboxed tools" | 18 tools | Count `name="` lines in `capabilities.py:get_default_native_tools()` |
| 2 | `USER_GUIDE_WHAT_LUCCA_DOES.md` | 17 | Says "capped at 16" | `MAX_REGISTRY_TOOLS = 18` | Read `capabilities.py:34` |
| 3 | `USER_GUIDE_WHAT_LUCCA_DOES.md` | 17 | Says "7 cascade substrates" | 8 substrates | Count `EpistemicSubstrate` enum members in `cascade.py:37-56` |
| 4 | `USER_GUIDE_WHAT_LUCCA_DOES.md` | 17 | References `cascade.py:SUBSTRATE_ORDER` | Constant doesn't exist | `Select-String cascade.py -Pattern SUBSTRATE_ORDER` returns nothing |
| 5 | `USER_GUIDE_WHAT_LUCCA_DOES.md` | 17 | References `lifecycle.py:MAX_ACTIVE_RULES` | Constant doesn't exist | `Select-String lifecycle.py -Pattern MAX_ACTIVE_RULES` returns nothing |
| 6 | `README.md` | ~35 | Says "5-Substrate" | 8 substrates | Same as #3 |
| 7 | `STUDIO_CAPABILITY_ROADMAP.md` | Multiple | Says "≤16 native tools" | ≤18 | Same as #2 |
