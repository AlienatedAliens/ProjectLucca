# Work Order 18 — Architectural Remediation & Process Hardening (Execution Manual)

**Status:** Planned (pending owner ratification)
**Date:** 2026-09-25
**Audience:** an implementing agent with no prior context. Every step lists exact files, exact actions, verification commands, and rollback. If a step says **STOP**, halt and ask the owner — do not improvise.
**Inputs:** [`docs/audit/findings/ARCHITECTURAL_DEBT_AUDIT_2026-09.md`](../docs/audit/findings/ARCHITECTURAL_DEBT_AUDIT_2026-09.md) (F-ARCH-101…107)
**Golden rules:**
1. **One phase = one commit.** Never mix phases in a commit.
2. After **every** step, run: `uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"`. If anything fails that passed before your change, revert your change (`git checkout -- .`) and re-read the step. Do not "fix forward."
3. **Never edit anything under `docs/archive/`.** Ever.
4. Do not refactor beyond the step's manifest. If you notice something else wrong, write it down; don't fix it.

---

## Phase 1 — WO-18a: Sync Memory-Layer Cascade (F-ARCH-101)

**Goal:** delete the async/sync duality. Root cause: `EmbeddingPort.embed` is `async` but does CPU-bound local inference. Making it sync lets the whole memory layer go sync and every shim die.

### 1.1 Exact change manifest

| File | Action |
|---|---|
| `src/lucca/ports.py` | `EmbeddingPort.embed`: remove `async` (line ~77). `MemoryStorePort` methods `commit/search/supersede/forget/graph_neighbors`: remove `async` (lines ~84-88). **DO NOT touch `SpeechLLMPort.stream` or the `AsyncIterator` import — those stay async.** |
| `src/lucca/senses/embed.py` | `LocalEmbeddingPort.embed` (and any `EmbedWorker` async method it wraps): remove `async`, remove internal `await`s. |
| `src/lucca/memory/store.py` | `commit` (:72), `search` (:310), `supersede` (:314), `forget` (:378), `graph_neighbors` (:440): remove `async`; remove `await` at :99 (`vecs = await self.embedding_port.embed(...)`) and :312 (`return await self.retriever.search(q)`). |
| `src/lucca/memory/retrieval.py` | `HybridRetriever.search` → sync; remove `await` at :114. |
| `src/lucca/memory/reflection.py` | Remove `async`/`await` on methods calling `self.store.*` (:213-214, :301-302, :392, :429-430 and any others — grep the file for `await` after editing; result must be zero). |
| `src/lucca/core/orchestrator.py` | Delete `_run_async_commit` (:1201-1209) and the `_commit_executor` ThreadPoolExecutor created in `__init__` (:508). Delete every `if asyncio.iscoroutine(res): ...` guard (there are 7+: search the file for `iscoroutine`). Delete the loop-vs-threadpool branching in `_check_contradictions` (:1816-1824) and `maybe_run_nightly_rollup` (:1861-1870) — replace with direct synchronous calls. |
| `tests/fakes/` + `tests/conftest.py` + any test calling store methods with `asyncio.run` / `await` | Remove `asyncio.run(...)` wrappers around `store.commit/search/supersede/forget` calls; make fake store classes' methods synchronous. **Expect 10–40 test edits. This is normal.** |

### 1.2 Traps

- **TRAP 1:** `SpeechLLMPort.stream` is legitimately async (`AsyncIterator[LLMEvent]`). If you blanket-delete `async` from `ports.py` you will break the LLM client. Only `EmbeddingPort` and `MemoryStorePort` go sync in this phase.
- **TRAP 2:** `orchestrator.py` imports `asyncio` for other reasons (`asyncio.get_running_loop` in contradiction/rollup paths you're replacing). After your edits, `grep -n "asyncio" src/lucca/core/orchestrator.py` — if the only remaining uses are your deletions' leftovers, remove the import; if `asyncio` is still used elsewhere (it is — check first), keep it.
- **TRAP 3:** `ReflectionEngine.detect_and_handle_contradiction` and `nightly_rollup` return values are unpacked as tuples (`is_queued, res_str = ...`). Keep the return shapes identical when de-asyncing.
- **TRAP 4:** `tests/test_turn_loop.py` currently emits two `RuntimeWarning: coroutine ... never awaited` warnings. After this phase they must be **gone**. If they're still there, you missed a call site — find it with `grep -rn "\.search(\|\.commit(" src/lucca/core/turn_pipeline.py`.

### 1.3 Verify

```powershell
uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"
grep -rn "iscoroutine" src/           # expect: no output
grep -rn "asyncio.run" src/lucca/core # expect: no output
grep -rn "await " src/lucca/memory    # expect: no output
```

### 1.4 Rollback

`git checkout -- src tests` — the phase is one commit; nothing else should be in it.

---

## Phase 2 — WO-18d: Ports, ClockPort, Linter Contracts (F-ARCH-102/106/107)

### 2.1 Exact change manifest

| Step | Action | Gate |
|---|---|---|
| 2.1 | Add to `.importlinter`: contract `brain must not import memory.signers` (copy the shape of contract 2, swap modules). Run `uv run lint-imports` → 7/7 KEPT. | no stop |
| 2.2 | `src/lucca/router/heuristic.py:27`: replace `from lucca.senses.embed import EmbedWorker` usage with the `EmbeddingPort` protocol for type annotations (the concrete worker is still injected at construction in `orchestrator.py:632-636`; only the *annotation* changes). | no stop |
| 2.3 | **STOP — owner decision required.** Dead ports `SandboxPort`, `SpeechLLMPort`, `RuleEnginePort`, `RouterPort`, `RandomPort` (`src/lucca/ports.py`): ratify (keep + wire consumers) or prune (delete). Present the owner the audit's recommendation (ratify SandboxPort + SpeechLLMPort, prune the rest). Do not choose yourself. | **STOP** |
| 2.4 | Implement `ClockPort` in `orchestrator.py`: add `clock: ClockPort | None = None` constructor param defaulting to a `SystemClock`; replace all 8 `getattr(self, "_current_simulated_time", None) or time.time()` sites with `self.clock.now_utc()`. Update tests that set `_current_simulated_time` to inject a `FixedClock` instead (grep `tests/` for `_current_simulated_time`). | no stop |
| 2.5 | **STOP — owner decision.** The `brain → memory.retrieval` edge (`prompt_builder.py:26` imports `format_memory_context`): bless by ADR or move the function to a shared module. Recommend: bless (it was the F-MEM-017 remediation). | **STOP** |

### 2.2 Verify

```powershell
uv run lint-imports                                    # 7/7 KEPT
uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"
grep -rn "_current_simulated_time" src/                # expect: no output
```

---

## Phase 3 — WO-18c: Exception Hygiene + Verifier Positive Controls (F-ARCH-105)

### 3.1 Procedure

1. Run `uv run python scratch/audit_except_shapes.py` — it prints the current silent-handler list. Work file by file, **sandbox/ first** (30 silent), then `ui/` (34), then the rest.
2. For each silent handler: add `logger.debug("<what_failed>", error=str(exc))` (or the module's existing logger name — match the file's convention). **Do not change behavior.** If a handler returns a fail-closed value (`ToolResult`, `(False, ...)`), keep the return exactly as-is; only add the log line.
3. The 49 `other`/multi-statement sites (list in the audit doc): read each one. If the handler catches something specific (e.g., `json.JSONDecodeError` territory), narrow the type. If unsure, leave broad + logged. **Do not narrow `except Exception` in `orchestrator.py` turn-path code without a STOP.**
4. Promote `scratch/audit_except_shapes.py` into `tests/test_static_gates.py` as `test_no_silent_broad_excepts`. **Positive control requirement:** the gate must first assert it detects a synthetic silent handler and a synthetic logged handler correctly (write two tiny fixture strings inline), then assert the tree is clean.
5. Boot-path files (`main.py`, `admin.py`, `core/env_check.py`) are WO-19d — same treatment, same phase.

### 3.2 Verify

```powershell
uv run python -m pytest tests/test_static_gates.py -q   # new gate green
uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"
```

---

## Phase 4 — WO-18b: Orchestrator Decomposition (F-ARCH-103)

**This is the risky phase. The parity pattern to copy already exists: `tests/test_orchestrator_parity.py` (the TurnPipeline extraction gate). One extraction per commit, in this exact order:**

### 4.1 `SignerFactory` (do first — smallest, kills the worst duplication)
1. New file `src/lucca/core/signer_factory.py`: one class constructed once with the master key; methods `user_speech()`, `tool_result()`, `assistant_utterance()`, `coherence_breach()`. **Fail-closed:** key missing/short → raise at construction unless `LUCCA_ENV=dev`.
2. In `orchestrator.py`: replace the 10 inline signer-construction blocks (grep for `create_user_speech_signer|create_tool_result_signer|create_assistant_utterance_signer|CoherenceBreachSigner(`) and all 10 occurrences of the dev-key literal `01234567890123456789012345678901` with factory calls.
3. Verify: `grep -c "01234567890123456789012345678901" src/lucca/core/orchestrator.py` → `0`. Full suite green.

### 4.2 `MemoryCommitService`
1. New file `src/lucca/core/memory_commit_service.py`. Move these methods out of `Orchestrator`, unchanged in behavior: `_commit_transcript`, `_commit_action_receipts`, `_maybe_extract_facts`, `_commit_assistant_utterance`, `_commit_coherence_breach`, `_maybe_form_belief`. The service takes the store + signer factory at construction; the orchestrator delegates (`self.commits = MemoryCommitService(...)` and each old method becomes a one-line delegate or is re-pointed at call sites).
2. Add a marker-count static test modeled on the existing parity gate: the moved method names must appear exactly once in the new file and zero times in `orchestrator.py`.
3. Full suite green before proceeding.

### 4.3 `BeliefService`, then 4.4 `ConfirmationManager`
Same playbook: move `_check_contradictions`, `_maybe_speak_pending_updates` (Belief); `confirm_action`, `_request_confirmation`, `_abort_confirmation_prompt_playback`, the `_confirm_*` fields (Confirmation). One commit each. Suite green each time.

### 4.5 Traps
- **TRAP 1:** these methods read/write orchestrator state (`current_turn_receipts`, `pending_spoken_updates`, `_last_transcript_signed`, `history`). Pass state explicitly or keep the fields on the orchestrator and have services reference it — do **not** duplicate state.
- **TRAP 2:** tests reach into `orch._handle_memory_commit`, `orch._commit_transcript` etc. directly (e.g., `tests/test_grounded_memory_commit.py`). Keep thin delegate methods on `Orchestrator` with the same names so tests don't break; mark them `# delegate — kept for test/back-compat`.
- **TRAP 3:** do not "improve" logic while moving it. Byte-for-byte behavior parity is the acceptance bar.

### 4.6 Verify / done
Orchestrator ≤ 1,500 lines (`(Get-Content src/lucca/core/orchestrator.py | Measure-Object -Line).Lines`); suite green; per-service marker tests green.

---

## Phase 5 — WO-18e: StudioFacade (may run parallel to P1)

**STOP — do not start until Phase 4 is merged.** The facade's shape depends on the post-decomposition services.

## Phase 6 — Process hardening (continuous)

Land with each phase: promote `scratch/audit_*.py` → `scripts/` with positive controls; add ratchet gates (orchestrator line ceiling, silent-except ceiling = 0 after Phase 3, dead-port count = 0 after Phase 2); create `docs/audit/baseline.json` after Phase 4; file findings into `docs/V2_ACTION_LOG.md`.

---

## Research-ratified decisions (do not re-litigate)

- **D-WO18-01:** sync-ify, never bridge per-call. If a network-bound embedder ever appears: one long-lived background loop + `asyncio.run_coroutine_threadsafe` (AnyIO `from_thread` acceptable). Per-call `asyncio.run` is banned.
- **D-WO18-02:** ratchet gates = architectural fitness functions. Stay with import-linter + AST gates; do not adopt pytest-archon/archfit (our gates cross-check docs against code constants; theirs can't).
- **D-WO18-03:** decomposition follows the in-repo TurnPipeline parity playbook; no external pattern imports.

---

## Review Protocol — every phase comes back for review before the next begins

**No phase is "done" when the implementer says it is.** Each phase ends with a review gate executed by a different agent (or the owner) than the one that implemented it.

### R.1 What the implementer must hand back (the review package)

1. **The commit hash** (one commit per phase — if there are two, the phase fails review automatically).
2. **Full test output** of `uv run python -m pytest tests/ -q -m "not tier2 and not hw and not soak"` pasted verbatim, plus `tests/test_static_gates.py` output.
3. **Verbatim output of every command in the phase's own Verify section** (grep results included — empty results must be shown as empty, not omitted).
4. **The completed self-check table** (R.2) with every row marked.
5. **A list of everything they noticed but did not fix** (the golden rule says don't fix out of scope — this list is where those observations go).

### R.2 Reviewer checklist (the reviewer re-verifies independently — never trusts the package)

| # | Check | How |
|---|---|---|
| 1 | **Scope audit** | `git show --stat <hash>` — every changed file must appear in the phase's change manifest. Any file outside the manifest → **bounce**. |
| 2 | **Diff read** | Read the full diff. Look for: behavior changes disguised as refactors, deleted tests, weakened assertions, new `type: ignore`/`noqa` without justification, any edit under `docs/archive/` → **bounce**. |
| 3 | **Independent verify** | Re-run the phase's Verify commands yourself. Outputs must match the package. |
| 4 | **Trap audit** | Re-read the phase's Traps section and check each one against the diff specifically (e.g., Phase 1: `AsyncIterator` still in `ports.py`; `SpeechLLMPort` still async; zero `iscoroutine` in `src/`). |
| 5 | **Gate quality** | For any new static gate: does it have its positive control (does the test prove the test can fail)? Comment it out mentally — would anything catch the regression it guards? |
| 6 | **Suite state** | 680+ green, and the two known pre-existing failures (D-REAS-08 tripwire, frozen binary) are the *only* failures and are unchanged in character. |

### R.3 Verdicts

- **PASS** — recorded in the phase's section below with reviewer, date, commit hash. Next phase may begin.
- **BOUNCE** — reviewer writes a bounce note: what's wrong, which R.2 row failed, what to do. The implementer fixes *only* what the bounce note says, then resubmits the entire package. Two bounces on the same phase → **STOP**, escalate to owner.

### R.4 Phase sign-off log

| Phase | Commit | Implementer | Reviewer | Verdict | Date |
|---|---|---|---|---|---|
| 1 (WO-18a sync cascade) | `b7625b7` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-25 |
| 2 (WO-18d ports/clock) | `dfd6e06` | implementing agent | reviewer (Zoo) | **PASS** | 2026-09-25 |
| 3 (WO-18c exceptions) | | | | | |
| 4 (WO-18b decomposition) | | | | | |
| 5 (WO-18e facade) | | | | | |
