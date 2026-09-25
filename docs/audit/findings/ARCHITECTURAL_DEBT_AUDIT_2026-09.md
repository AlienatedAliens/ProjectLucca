# Project Lucca — Architectural Debt Audit & Rectification Plan

**Status:** Complete audit, findings ratified-pending-owner
**Date:** 2026-09-25
**Scope:** Full `src/lucca/` tree (100 modules, 32,756 lines), import graph, port contracts, exception handling, god objects, test-hook leakage
**Method:** AST-based automated analysis (`scratch/audit_import_graph.py`, `scratch/audit_exceptions.py`, `scratch/audit_except_shapes.py`) + import-linter run + manual verification of all load-bearing claims
**Prior art:** Builds on `docs/archive/2026-09_raw_findings/arch.md` (F-ARCH series); does not repeat resolved findings

---

## 0. Executive Summary

The codebase is **not** shim-accumulation architecture. Layering is mostly correct, all six import-linter contracts pass, the signer allow-list is clean, and there are zero TODO/FIXME/HACK markers in the tree. The debt is **concentrated in four structural defects**, each with a bounded rectification:

| # | Finding | Severity | Effort |
|---|---|---|---|
| F-ARCH-101 | Async/sync port-contract duality (one `async` keyword cascaded through the memory layer) | **S1** | 1–2 days |
| F-ARCH-102 | Hexagonal architecture half-realized: 5 of 9 ports are dead definitions; `ClockPort` exists but test hooks bypass it | S2 | 1 day |
| F-ARCH-103 | Orchestrator god-object: 3,213 lines, 62 methods, 10 duplicated signer blocks | S2 | 3–5 days |
| F-ARCH-104 | `settings_dialog` god-object + UI constructs domain objects directly | S2 | deferred behind 103 |
| F-ARCH-105 | 120 silent broad `except Exception` handlers (24 fail-closed-but-silent) | S3 | 1 day |
| F-ARCH-106 | ADR-006 import-linter contract missing from `.importlinter` | S3 | 1 hour |
| F-ARCH-107 | `_current_simulated_time` test hook at 8 production sites | S3 | folded into 102 |

**Positive findings (verified):** 6/6 import-linter contracts KEPT; signer imports restricted to `core/orchestrator.py` + memory-internal modules (ADR-006 allow-list holds); `core/cascade.py` well-factored (6 classes, 26 methods); no dependency cycles; 14 static gates green including the two new drift gates.

---

## F-ARCH-101 — Async/Sync Port-Contract Duality (S1)

**Root cause (single point):** [`EmbeddingPort.embed`](src/lucca/ports.py:77) is declared `async` — but the only implementation is local CPU-bound ONNX/MiniLM inference with no I/O to await. That one keyword forced `MemoryStore` ([`store.py:72-441`](src/lucca/memory/store.py:72): all five methods `async def`), which forced `ReflectionEngine` async ([`reflection.py:213-302`](src/lucca/memory/reflection.py:213)), which forced the thread-based orchestrator to bridge at every call site.

**The shim layer this created:**
- [`_run_async_commit`](src/lucca/core/orchestrator.py:1201): `executor.submit(asyncio.run, coro).result()` — a **new event loop per call** on a single-thread executor, at 7+ call sites (`_commit_transcript`, `_commit_action_receipts`, `_maybe_extract_facts`, `_commit_assistant_utterance`, `_commit_coherence_breach`, `_maybe_form_belief`, `_search_memories`).
- `asyncio.iscoroutine` guards at every one of those sites.
- The two un-awaited-coroutine `RuntimeWarning`s in `tests/test_turn_loop.py` are this defect's exhaust.

**Why S1:** per-call `asyncio.run` is fragile (any future loop-bound object — an aiohttp session, an async sqlite driver — breaks silently), wastes a thread-block per memory operation on the latency-critical turn path, and the guard pattern means a *new* call site that forgets the guard fails silently.

**Rectification (WO-18a):**
1. `EmbeddingPort.embed` → sync `def embed(...)`. (`LocalEmbeddingPort`/`EmbedWorker` are CPU-bound; no behavioral change.)
2. `MemoryStore` five methods → sync. `HybridRetriever.search` → sync.
3. `ReflectionEngine` → sync (its `await self.store.*` calls become plain calls).
4. Delete `_run_async_commit` and every `iscoroutine` guard.
5. Delete the now-dead `AsyncIterator` import if unused; update `MemoryStorePort` to sync signatures.
6. **Acceptance:** full non-HW suite green; zero `RuntimeWarning` in `tests/test_turn_loop.py`; `grep -rn "iscoroutine" src/` returns nothing; `grep -rn "asyncio.run" src/lucca/core` returns nothing.

**Alternative considered and rejected:** making the orchestrator fully async. It is thread-based by design (ZMQ ingest loop, audio rings, bounded-join barge-in); an async migration is a multi-week risk with no payoff.

---

## F-ARCH-102 — Hexagonal Architecture Half-Realized (S2)

**Evidence:** [`ports.py`](src/lucca/ports.py) defines 9 Protocols. Only 4 are consumed anywhere (`MemoryStorePort`, `STTPort`, `TTSPort`, `EmbeddingPort` — verified by AST import scan). `SandboxPort`, `SpeechLLMPort`, `RuleEnginePort`, `RouterPort`, `ClockPort`, `RandomPort` are **dead definitions**; consumers inject concrete classes (`SandboxService`, `LLMClient`, `ASRWorker`, `TTSWorker`, `HeuristicRouter`).

**The sharpest instance:** `ClockPort` ([`ports.py:121`](src/lucca/ports.py:121)) exists *specifically* for "test determinism and session replay" — and production instead uses `getattr(self, "_current_simulated_time", None) or time.time()` at **8 sites** in the orchestrator (F-ARCH-107). The designed mechanism exists; the workaround was built anyway.

**Rectification (WO-18d):**
1. Ratify or prune each dead port by ADR: `SandboxPort` and `SpeechLLMPort` are worth ratifying (real external boundaries); `RuleEnginePort`/`RouterPort` likely prune (single implementation, no second consumer foreseeable); `RandomPort` prune unless replay lands.
2. Implement `ClockPort` in the orchestrator; delete all 8 `_current_simulated_time` sites; tests inject a `FixedClock`.
3. **Acceptance:** every port in `ports.py` has ≥1 consumer or is deleted; `grep -rn "_current_simulated_time" src/` returns nothing.

---

## F-ARCH-103 — Orchestrator God-Object (S2)

**Evidence:** 3,213 lines, 1 class, 62 methods, 77 `hasattr`/`getattr` sites (next-highest file: 18). It mixes at least six distinct responsibilities:

| Responsibility | Methods (approx.) | Extraction target |
|---|---|---|
| Turn lifecycle & IPC | `_run_turn`, `_on_ptt_*`, `_ingest_loop`, `_handle_ingest_message` | stays (it *is* the orchestrator) |
| Memory commits (6 provenance classes) | `_commit_transcript`, `_commit_action_receipts`, `_commit_assistant_utterance`, `_commit_coherence_breach`, `_maybe_extract_facts`, `_maybe_form_belief` | **`MemoryCommitService`** |
| Belief/contradiction engine glue | `_check_contradictions`, `_maybe_speak_pending_updates` | **`BeliefService`** |
| Confirmation state machine | `confirm_action`, `_request_confirmation`, `_abort_confirmation_prompt_playback` | **`ConfirmationManager`** |
| TTS queue & captions | `_enqueue_tts_chunk`, `_tts_worker`, `_publish_caption` | **`SpeechOutputManager`** |
| Signer construction | duplicated **10×** with **10 hardcoded dev-key literals** | **`SignerFactory`** (single construction site, fail-closed) |

**The duplicated signer block** (get master key → else hardcoded dev key → construct signer → cache on `self`) appears in 5 commit methods with the dev-key literal `01234567890123456789012345678901` repeated 10 times. Beyond duplication, a *fail-open* pattern: the dev-key fallback means a misconfigured production boot signs provenance with a publicly-known key — the exact threat TM-08/TM-13 name. The boot-time `assert_prod_master_key` gate (F-MEM-005 remediation) covers startup, but the per-method fallbacks remain a latent bypass.

**Rectification (WO-18b):**
1. `SignerFactory` constructed once at `__init__` (fail-closed: no key → raise, no dev fallback outside `LUCCA_ENV=dev`).
2. Extract `MemoryCommitService` (all 6 commit paths + `SignerFactory` consumer).
3. Extract `BeliefService` and `ConfirmationManager`.
4. **Acceptance:** orchestrator ≤ 1,500 lines; `grep -c "01234567890123456789012345678901" src/lucca/core/orchestrator.py` == 0; all 680+ tests green with zero behavioral change (parity is the acceptance bar — this is a pure refactor).

---

## F-ARCH-104 — `settings_dialog` God-Object + UI→Domain Construction (S2)

**Evidence:** 2,799 lines, 3 classes, 84 methods, ~25 of the 49 manual-review silent excepts. It directly constructs `MemoryStore`, `RuleLifecycleManager`, `SkillManager`, and calls `evaluate_rule`/`parse_rule` ([`settings_dialog.py:78-85`](src/lucca/ui/settings_dialog.py:78)) — the UI process holding domain objects is the F-MEM-001 legacy surface (the UI admin memory path that bypassed the ProvenanceGate).

**Rectification (WO-18e, deferred behind WO-18b):** introduce a `StudioFacade` in `lucca.core` exposing the operations the dialog needs (list rules, validate skill, read memories, telemetry); the dialog consumes the facade (in-process) or IPC (cross-process). **Acceptance:** `settings_dialog.py` imports nothing from `lucca.memory`, `lucca.reasoning`, or `lucca.sandbox` directly; ≤ 1,200 lines.

---

## F-ARCH-105 — 120 Silent Broad Excepts (S3)

**Classification (AST-verified):** of 199 broad `except Exception` handlers: 60 logged-and-continue (fine), 19 re-raise (fine), **120 silent**:

| Shape | Count | Verdict |
|---|---|---|
| bare `pass` | 46 | Mostly best-effort cleanup (ring buffers, stdio reconfigure) — acceptable, but should `logger.debug` |
| fail-closed return (`ToolResult(error)`, `(False, ...)`, `SMTVerificationResult`) | 24 | **Deliberate fail-closed design, but silent** — violates the project's own doctrine ("every refusal is logged with a reason code", user guide §troubleshooting) |
| `other` / multi-statement | 49 | Need manual review; concentrated: `settings_dialog.py` (~25), `admin.py` (7), `sandbox/` (8) |

**Rectification (WO-18c):** add `logger.debug` minimum to all 120; convert the 49 reviewed sites to typed exceptions where a specific failure mode exists. **Acceptance:** zero silent broad excepts (new static-gate test asserting every broad handler contains a log call or raise — the AST classifier already exists as `scratch/audit_except_shapes.py` and can be promoted into `tests/test_static_gates.py`).

---

## F-ARCH-106 — ADR-006 Import-Linter Contract Missing (S3)

**Evidence:** `.importlinter` has 6 contracts, all KEPT — but the ADR-006 contract (`lucca.brain` must not import `lucca.memory.signers`) specified in the archived ADR is **absent**. The boundary currently holds (verified: only `core/orchestrator.py` + memory-internal modules import signers), but it is enforced by nothing.

**Rectification (WO-18d, 1 hour):** add the contract; consider also `lucca.router` → `lucca.senses` (currently imports concrete `EmbedWorker` at [`heuristic.py:27`](src/lucca/router/heuristic.py:27) — should consume `EmbeddingPort`) and ratify the `brain` → `memory.retrieval` edge created by the F-MEM-017 remediation ([`prompt_builder.py:26`](src/lucca/brain/prompt_builder.py:26)) — either bless it by ADR or move `format_memory_context` to a shared rendering module.

---

## Rectification Sequencing

| Order | WO | Content | Blocks |
|---|---|---|---|
| 1 | **WO-18a** | Sync `EmbeddingPort` cascade; delete all async shims | nothing — do first, it simplifies everything downstream |
| 2 | **WO-18d** | Port ratification + ClockPort + ADR-006 linter contract | cheap, independent |
| 3 | **WO-18c** | Exception hygiene + static gate | independent |
| 4 | **WO-18b** | Orchestrator decomposition (SignerFactory → MemoryCommitService → BeliefService → ConfirmationManager) | do after 18a (shims gone = smaller diff) |
| 5 | **WO-18e** | StudioFacade + settings_dialog slimming | after 18b |

Each WO ships with the acceptance criteria listed in its finding and runs the full non-HW suite as the parity gate. **No feature work (P1 head-to-head, BFCL, provenance-library extraction) should land before WO-18a/18d/18c** — they are small and they de-risk everything after; WO-18b/18e can run in parallel with P1 if capacity allows.

---

## Appendix — Verification Commands

```powershell
uv run lint-imports                                    # 6/6 KEPT
uv run python scratch/audit_import_graph.py            # import graph + signer allow-list
uv run python scratch/audit_exceptions.py              # except classification + god-object metrics
uv run python scratch/audit_except_shapes.py           # silent-handler shapes
uv run python -m pytest tests/test_static_gates.py -q  # 14 gates incl. drift gates
```
