# WO-22 — The Practical Reasoning Rung: Means-Ends Planning & Diagnostic Self-Reasoning

**Date:** 2026-09-27
**Audience:** an implementing agent with no prior context. Every phase lists exact files, exact actions, **functional** acceptance criteria (behavioral, not just "suite green"), traps, and STOP gates. **STOP** means halt and report to the owner — do not improvise.
**Golden rules:** one phase = one commit; run `uv run python -m pytest -q -m "not tier2 and not hw and not soak"` after every step (baseline: **874 passed, 0 failed**); never edit `docs/archive/`; never edit an existing migration file — new schema changes are **new migration files only**; never "fix forward" from a red suite — revert and re-read.
**Research grounding:** [`docs/research/REASONING_BREADTH_RESEARCH_PASS_2026-09.md`](../docs/research/REASONING_BREADTH_RESEARCH_PASS_2026-09.md) (practical reasoning/BDI, diagnostic reasoning, bounded rationality). Backlog: [`docs/V2_BACKLOG.md`](../docs/V2_BACKLOG.md) §1.13.

---

## Phase 0 — WO-22a: Tracked Cleanups

**Goal:** clear the three queued items before new work.

**Manifest:**
| File | Action |
|---|---|
| `tests/test_rule_induction.py` | `test_live_induction_production_log_clusters_gt_zero` reads the production DB — add a skip-guard: `pytest.skip` (with reason) when `C:\ProjectLucca\data\memory.sqlite` is absent, so the suite is portable to fresh machines/CI. |
| `src/lucca/core/corroboration.py` | Source-normalization edge: `example.com` vs `example.org` currently over-merge. Replace the strip-TLD heuristic with eTLD+1 extraction (host suffix match against a small embedded public-suffix list: com/org/net/io/dev/ai/github.io/etc.). Two different registrable domains must NEVER dedupe; alias forms of the same domain (`ars-technica.com` vs `arstechnica.com`) should still dedupe — implement as: normalize case, strip leading `www.`, strip hyphens, then compare eTLD+1 labels. Add tests for both directions. |
| (owner action, verify only) | `python -m lucca.admin memory forget 107` — remove the `user origin_is though` pollution from the live-test. Verify the envelope is soft-deleted and audited, then confirm `memory_search` no longer returns it. |

**Functional acceptance:** suite portable (skips, never fails, without the production DB); alias dedupe preserved; distinct-domain over-merge fixed; memory 107 gone from retrieval.

**Traps:** the eTLD+1 list is a lookup, not a network call. Deterministic.

**STOP gate:** none. Proceed.

---

## Phase 1 — WO-22b: Means-Ends Planner

**Goal:** planning becomes a first-class reasoning *output*: given a goal, she produces a bounded, validated, receipt-backed plan — not an improvised tool loop.

**Manifest:**
| File | Action |
|---|---|
| `src/lucca/core/schemas.py` | `PlanStep(BaseModel)`: `tool: str`, `args: dict[str, JsonValue]`, `purpose: str (max 200)`, `order: int (ge=1)`. `GoalPlan(BaseModel)`: `goal: str`, `steps: list[PlanStep] (max 8)`, `rationale: str (max 500)`, `plan_id: str`. |
| `src/lucca/brain/prompt_builder.py` | Planning-mode contract section (mirror the deduction contract's shape): emit a JSON `GoalPlan`, not prose; each step names its tool, args, and *why*; max 8 steps. |
| `src/lucca/core/orchestrator.py` | `run_planning_step(goal, trace, llm) -> GoalPlan | None`: parse the plan; validate every step's tool exists in the registry and args pass the central `TOOL_ARG_SCHEMAS` schema (WO-19a); deontic pre-check each step via `SpeculativeBDIValidator`; invalid plan → one revision with machine-readable error → then honest refusal ("I can't plan that safely because…"). Valid plan → stored on the turn, executed step-by-step through the **existing** dispatch path (confirmations, sequence guard, taint all apply per-step), each step's receipt appended to the plan record. |
| `src/lucca/core/reasoning_context.py` | Plans may reference the current `ReasoningContext` — a plan step's `purpose` may cite intermediates. |
| `tests/test_planning.py` (new) | Valid 3-step plan executes in order with per-step receipts; invalid tool → revision → refusal; step args failing schema → revision; >8 steps → schema failure; plan step requiring confirmation still asks (per-step gates honored); plan referencing a deduction intermediate works. |

**Functional acceptance:**
- "Research X and save a summary to notes" → she emits a plan (search_web → fetch_url → note_write), executes it step-by-step with confirmations where required, and each step's receipt is recorded — the plan is inspectable, not improvised.
- A plan with a deontically-unsafe step is refused with the named step and reason.

**Traps:**
- **TRAP 1:** plans execute through the EXISTING dispatch path — no bypass of confirmations, sequence guard, or taint. The planner proposes; the sandbox still disposes.
- **TRAP 2:** bounded at 8 steps; no plan-within-plan recursion.
- **TRAP 3:** a failed step does NOT silently abort the plan — the failure is spoken, remaining steps are cancelled, and the partial plan + receipts are recorded (partial-failure honesty, D-HON-01 register).

**STOP gate:** the `GoalPlan` JSON shape and the max-8-steps bound are owner-visible — present before implementing.

---

## Phase 2 — WO-22c: Diagnostic Self-Reasoning (Fault Model v1)

**Goal:** symptom→cause reasoning about her own stack, seeded from the *real* incidents already on record.

**Manifest:**
| File | Action |
|---|---|
| `config/fault_model.toml` (new) | Owner-curated fault model v1, authored from the documented incidents: (1) boot MemoryError / OpenVINO alloc failure → cause: system RAM below 3.5 GB budget → check `check_system_ram`; (2) `run_python` returns `policy_violation` → cause: Docker CE not running in WSL2 → check `check_docker_wsl`; (3) ASR latency spike with normal NPU load → cause: audio ring contention → check ring-buffer underruns; (4) `llama-server` unhealthy → cause: VRAM over-budget or model file missing → check `check_mshybrid_vram` + manifest hashes; (5) frozen-binary `--check` timeout → cause: WSL unresponsive → check `wsl --status`. Each entry: `symptoms` (observable signals), `cause`, `checks` (env_check function names), `severity`. |
| `src/lucca/core/self_diagnosis.py` (new) | `DiagnosisEngine`: `diagnose(observations: dict) -> list[Diagnosis]` — matches observed symptoms against the fault model, runs the listed checks (env_check functions), returns ranked diagnoses `{cause, confidence, evidence, suggested_remedy}`. Diagnoses are **hypotheses** (`INFERRED`-style, hedged speech), never asserted as fact. |
| `src/lucca/core/orchestrator.py` | Wire into the self-diagnostics path: when `self_metrics` reveals anomaly signals (or the user asks "why are you slow / what's wrong with you"), run the engine and speak the top diagnosis with hedge: *"My ASR is slow and the NPU looks fine — my best guess is audio ring contention; I'd check the ring buffer."* |
| `tests/test_self_diagnosis.py` (new) | Each fault-model entry matches its seeded symptoms; no-match → honest "no known fault pattern matches"; checks actually invoked; hedged (never unhedged) speech. |

**Functional acceptance:**
- Seed Docker-down symptoms → she names the cause and the check, hedged.
- Unknown symptom combination → honest no-match abstention (named-gap style).
- The fault model is data (TOML), not code — adding an entry requires no deploy.

**Traps:**
- **TRAP 1:** diagnoses are hypotheses with confidence — never committed as facts, never spoken unhedged (standards-of-proof applies: diagnosis speech is SPECULATION-band unless a check *confirms*).
- **TRAP 2:** the engine reads only her own telemetry/registers — no host introspection beyond existing env_check functions.

**STOP gate:** the fault-model v1 contents (the 5 entries) are owner-visible — present before implementing.

---

## Phase 3 — WO-22d: Live Acceptance — Plan + Diagnosis

**Goal:** both rungs proven end-to-end.

**Functional acceptance (the only test that matters for this phase):**
- **Planning:** "Look up when Metal Gear Solid came out and note it" → plan (search_web → note_write) → executed with per-step receipts → note written → spoken summary cites both steps.
- **Diagnosis:** with the Docker sandbox fault-injected (`tests/fakes/fault_injecting_sandbox.py`), "what's wrong with your tools?" → she names the cause (Docker not running), the check that confirmed it, hedged — and the diagnosis is recorded as a hedged intermediate, not a committed fact.
- Both scenarios run cold, unled, in one turn each; R.1 includes verbatim spoken output.

**Traps:** fault injection must not leak into other tests (fixture-scoped).

**STOP gate:** none — but verbatim spoken output goes to the owner with the R.1.

---

## Execution order

```
Phase 0 (cleanups) → Phase 1 (planner) → Phase 2 (diagnosis) → Phase 3 (live acceptance)
```

Phase 2 is independent of Phase 1 and may run in parallel after Phase 0.

## Review protocol (unchanged)

R.1 package per phase: one commit hash, verbatim full-suite output, verbatim phase-verify output, self-check table, out-of-scope observations. Reviewer independently re-runs scope audit, diff read, verify, trap audit, gate quality (positive controls on new gates), suite state vs **874-passed baseline**. PASS logged; BOUNCE gets the failing row + exact fix; two bounces → STOP, escalate to owner.

## R.4 Phase sign-off log

| Phase | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|
| 0 (cleanups) | | | | | |
| 1 (means-ends planner) | | | | | |
| 2 (diagnostic self-reasoning) | | | | | |
| 3 (live acceptance) | | | | | |

## Deferred (WO-23 candidates)

- **Curiosity loop** (proactive background exploration) — backlog §1.1 trigger governs.
- **Counterfactual reasoning** — research watch item.
- **Full argumentation semantics (Dung/ASPIC+)** — trigger: recurring multi-source conflict clusters.