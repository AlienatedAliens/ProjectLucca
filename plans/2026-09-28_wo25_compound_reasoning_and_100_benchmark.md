# WO-25 — Compound Reasoning Integration, Database Hard Purge & 100-Problem Benchmark

**Date:** 2026-09-28  
**Audience:** An implementing agent with no prior context. Every phase lists exact files, exact actions, **functional** acceptance criteria (behavioral, not just "suite green"), traps, and STOP gates. **STOP** means halt and report to the owner — do not improvise.  
**Golden rules:** One phase = one commit; run `uv run python -m pytest -q -m "not tier2 and not hw and not soak"` after every step (baseline: **997 passed, 8 failed** — verified 2026-09-28; re-run before your first commit); never edit `luccadocs/archive/`; never edit an existing migration file; never "fix forward" from a red suite — revert and re-read.  
**Provenance:** Follows the live 10-problem diagnostic test failure (3.5/10), the ghost memory leak analysis, and the 100-problem specification defined in `luccadocs/specs/COMPOUND_REASONING_100_SPEC.md`.

---

## Current State & Problem Analysis

1. **Ghost Memory Bleed**: The UI memory "Factory Reset" performed only a soft-delete on the `memories` table (`forgotten_at IS NOT NULL`). It never touched `kg_entities`, `kg_edges`, `decisions`, or `rule_states`. Stale records (e.g. "Beverly Quintos in the Philippines") bled silently through Case-Based Reasoning (`episode_recall`) and the Knowledge Graph into live turns, causing Lucca to hallucinate location deductions.
2. **Tool Execution Chokepoints**:
   - `max_tokens` was capped at 512, truncating multi-line code generation mid-sentence.
   - Truncated or unescaped JSON caused standard `json.loads` to crash (`invalid_tool_call_json`), passing `{}` to Pydantic and failing closed.
   - The orchestrator's Honesty Directive commanded the model to never guess numbers or report failed tool output, barring chain-of-thought fallback and forcing the agent to go completely mute.
3. **Over-Aggressive Cascade Gating**:
   - Naive substring matching in `classify_epistemic_intent` caused the word *"lasted"* to match `"ast"` (Abstract Syntax Tree), misclassifying closed-world math word problems as queries about missing workspace files.
   - When ripgrep found no matching local file, the Belnap evidential bilattice forced a hard refusal: *"I checked my workspace files, but have no verified record of that."*
4. **Latency Budget Violation**:
   - Synchronous external HTTP calls inside `sys_info` took >532ms, violating the Class B tool latency SLA (<500ms). Host telemetry must remain purely local (<5ms).

---

## Phase 0 — Baseline Audit & Recon

**Goal:** Establish verified baseline state across test suite, database ghost rows, and token settings before modifying production code.

**Manifest:**
- Record baseline test count: `uv run python -m pytest -q -m "not tier2 and not hw and not soak"` (Recorded: **997 passed, 8 failed**).
- Audit `C:\ProjectLucca\data\memory.sqlite`: document exact row counts in `memories`, `kg_entities`, `kg_edges`, `decisions`, `rule_states`.
- Verify live tool failure reproduction with truncated JSON payload.

**Functional Acceptance:**
- Baseline test pass count recorded (997 passed).
- Database ghost record count documented (38 Beverly rows in `memories`, 1 in `kg_entities`, 3 in `kg_edges`, 16 in `decisions`, 1 in `rule_states`).

**STOP Gate 0:** Present Phase 0 baseline findings to the owner before modifying database or production code. **[COMPLETED & RATIFIED]**

---

## Phase 1 — Database Hard Purge & Zero-Leak Memory Barrier

**Goal:** Upgrade the UI "Factory Reset" and memory forget operations from soft-delete into true cascading hard-purges that eradicate ghost records across all backing stores.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/memory/store.py` | Implement `hard_purge_all(user_confirmed: bool = True) -> dict[str, int]`: executes an atomic SQLite transaction deleting all rows from `memories`, `fts_memories`, `vec_memories`, `kg_entities`, `kg_edges`, `decisions`, `fts_decisions`, `rule_states`, `memory_audit`, `provenance_envelopes`. Order of deletion: `kg_edges` before `kg_entities` (foreign key integrity); clears FTS and vector virtual tables. Returns dict of deleted row counts per table. |
| `src/lucca/core/studio_facade.py` | Update `factory_reset_memories(user_confirmed: bool = True) -> int` to invoke `store.hard_purge_all(user_confirmed=True)` and return total purged row count. |
| `src/lucca/ui/settings_tabs/memory_tab.py` | Update UI button text and tooltips: "💥 Factory Reset / Hard Purge (Clears All Stores)". Connect to updated facade method with confirmation dialog. |
| `tests/test_memory_purge.py` (new) | Positive & negative controls: seed facts into memories, KG, decisions -> execute hard purge -> assert exact count 0 across all 6 tables. Assert subsequent query triggers honest abstention with zero ghost recall. |
| `C:\ProjectLucca\data\memory.sqlite` | Execute hard purge to clean the live workstation database. |

**Functional Acceptance:**
- A seeded fact (e.g. "The secret key is CRIMSON") leaves zero traces in `memories`, `kg_entities`, or `decisions` after reset.
- A query asking for the secret returns honest calibrated abstention ("I have no verified record of that").
- Full test suite green against baseline (997 passed).

**Traps:**
- **TRAP 1:** Foreign keys are ON in SQLite (`PRAGMA foreign_keys = ON`). Deleting `kg_entities` before `kg_edges` will throw `sqlite3.IntegrityError: FOREIGN KEY constraint failed`. Always delete `kg_edges` first.
- **TRAP 2:** Virtual tables (`fts_memories`, `vec_memories`) have shadow backing tables. Delete using `DELETE FROM fts_memories` and `DELETE FROM vec_memories` rather than manual shadow-table drops.
- **TRAP 3:** Must require `user_confirmed=True` to prevent accidental programmatic wipes.

**STOP Gate 1:** Inspect database tables, confirm zero ghost rows, run test suite, commit Phase 1 (`git commit -m "WO-25 Phase 1: true cascading hard purge across all memory and KG tables"`), and report to owner.

---

## Phase 2 — Pipeline Joints & Tool Unchoking

**Goal:** Eliminate token truncation, JSON formatting crashes, naive substring collisions, latency violations, and over-aggressive honesty silences.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/sandbox/service.py` | Revert synchronous HTTP `ipinfo.io` call in `sys_info`. Host telemetry must only inspect local clock, timezone, OS, and hardware metrics (<5ms latency), satisfying the Class B <500ms SLA in `test_sys_info_execution_latency_and_untrusted_stamp`. |
| `src/lucca/core/config.py` & `schemas.py` | Increase default `max_tokens` from 512 to 2048. |
| `src/lucca/brain/llm_client.py` | Wire `_parse_and_repair_tool_args()`: multi-stage parser with `strict=False`, quote/bracket repair, and regex fallback for `code` and `expr`. Fix untyped broad `except Exception:` to satisfy `test_no_silent_broad_excepts`. |
| `src/lucca/ui/settings_tabs/dsp_tab.py` | Remove unused `refresh_from_dialog` function to satisfy `test_dead_code_register_no_unreferenced_symbols`. |
| `src/lucca/core/cascade.py` | Enforce word-boundary regex (`\b`) for all substrate keywords (`ast` cannot match `lasted`, `ram` cannot match `program`, `clock` cannot match `clockwise`). Add closed-world puzzle exemption (CAT03, CAT04, CAT06). Add missing `datetime`/`platform` imports. |
| `src/lucca/brain/prompt_builder.py` | Revert frontier-message temporal suffix injection to restore bit-identical prefix KV cache required by ADR-009 (`test_invariant3...` and `test_category_manifest...`). Instead, inject host clock and timezone via Substrate 0 epistemic context when temporal/situational intent is detected. Add prompt directives prioritizing `calc_math` over `run_python` for arithmetic/formulas, and enforce anti-lecture negative constraints. |
| `src/lucca/core/orchestrator.py` | Soften tool-failure honesty directive: allow step-by-step chain-of-thought calculation fallback labeled as analytical derivation rather than forcing absolute silence. |
| `src/lucca/core/turn_pipeline.py` | Suppress trivial no-op yield messages like `[Cognitive Bus Yield: define: no term]`. |

**Functional Acceptance:**
- `sys_info` latency is <50ms (passes `test_sys_info_execution_latency_and_untrusted_stamp`).
- `test_static_gates.py` passes 100% (zero broad excepts, zero dead code).
- `test_affect_quarantine.py` passes 100% (prefix KV-cache byte-identity preserved).
- Truncated multiline Python strings repair into valid execution dicts with extracted code.
- "Events occurred on a single afternoon..." returns `is_epistemic = False` (no ripgrep file search, no Belnap refusal).
- "Do you know what time it is?" returns `is_epistemic = True` querying Substrate 0.
- Suite returns **green with 0 failures** (remediating all 8 baseline failures).

**Traps:**
- **TRAP 1:** Never alter the system prompt prefix or frontier user message in ways that change static token lengths across turns. KV cache stability (ADR-009) is paramount. Temporal facts belong in the per-turn epistemic context.
- **TRAP 2:** In regex word boundary matching, paths like `config/` or `src/` end with non-alphanumeric characters. Bounding them with `\b` at both ends will fail to match. Use `(r"\b" if t[0].isalnum() else "") + re.escape(t) + (r"\b" if t[-1].isalnum() else "")`.
- **TRAP 3:** When softening the honesty directive, never allow the model to fabricate execution metrics or claim an unverified tool succeeded. Only permit mental chain-of-thought derivation for logic and math puzzles.

**STOP Gate 2:** Run targeted verification tests on JSON repair and cascade classification, run full test suite, verify 0 failures, commit Phase 2 (`git commit -m "WO-25 Phase 2: pipeline joints, tool unchoking, and KV-cache restoration"`), and report to owner.

---

## Phase 3 — The 100-Problem Compound Benchmark Harness

**Goal:** Build the automated test harness implementing the full 100-problem specification from `COMPOUND_REASONING_100_SPEC.md` and execute the live baseline run.

**Manifest:**
| File | Action |
|---|---|
| `tests/test_compound_reasoning_benchmark.py` (new) | Complete test suite containing all 100 problems across CAT01 to CAT10 with deterministic grading rules. |
| `scripts/run_compound_benchmark.py` (new) | CLI runner script that executes the 100 turns through `orch.turn_pipeline.run_turn()`, records timings, tool calls, and outputs a structured JSON report to `logs/test_reports/`. |

**Functional Acceptance:**
- All 100 problems run sequentially through the live pipeline without crashing or hanging.
- Structured report outputs category pass rates, median latency, tool execution counts, and failure logs.

**Traps:**
- **TRAP 1:** Do not mock the turn pipeline. Turns must pass through `orch.turn_pipeline.run_turn(TurnInput(text=prompt, mode="transcript"))` so that routing, cascade, prompt building, LLM inference, tool execution, and supervisory filtering are all live.
- **TRAP 2:** Reset turn session context between independent categories so that conversational history from CAT02 does not pollute CAT03.

**STOP Gate 3:** Harvest the baseline 100-problem report, present category breakdown table to the owner, and do not proceed to Phase 4 without review.

---

## Phase 4 — Review, Analysis & Iterative Remediation

**Goal:** Analyze baseline failure modes across the 10 categories, apply targeted architectural bridges (e.g. Z3 compiler prompt templates for CAT03), and verify score improvement.

**Manifest:**
| File | Action |
|---|---|
| `luccadocs/specs/COMPOUND_REASONING_100_BENCHMARK_RESULTS.md` (new) | Full audit report comparing initial score (35%) vs. Phase 3 baseline vs. remediated score. |
| Targeted components | Apply specific prompt/router tunings for lagging categories. |
| `scripts/deploy_to_workstation.py` | Sync verified code to production workstation target `C:\ProjectLucca`. |

**Functional Acceptance:**
- Benchmark pass rate significantly improved from the 35% initial baseline.
- All 10 categories pass at acceptable levels.
- Workstation target synchronized and verified.

**STOP Gate 4:** Final audit package presented to owner for sign-off.

---

## Execution Order & Sign-off Table

```
Phase 0 (Recon & Audit) [DONE] 
  → Phase 1 (Hard Purge & DB Clean) 
  → Phase 2 (Pipeline Joints & Suite Green) 
  → Phase 3 (100-Benchmark Harness & Baseline Run) 
  → Phase 4 (Analysis & Remediation)
```

| Phase | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|
| **Phase 0** | `b85675c` (baseline) | Antigravity | Owner | **PASS** | 2026-09-28 |
| **Phase 1** | Pending | Antigravity | Owner | In Review | 2026-09-28 |
| **Phase 2** | Pending | Antigravity | Owner | Pending | 2026-09-28 |
| **Phase 3** | Pending | Antigravity | Owner | Pending | 2026-09-28 |
| **Phase 4** | Pending | Antigravity | Owner | Pending | 2026-09-28 |
