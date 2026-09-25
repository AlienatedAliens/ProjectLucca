# User Guide Truth Audit — Claim-by-Claim Verification

**Status:** Complete; fixes applied to `docs/USER_GUIDE_WHAT_LUCCA_DOES.md` and `docs/DECISIONS.md`
**Date:** 2026-09-25
**Subject:** [`docs/USER_GUIDE_WHAT_LUCCA_DOES.md`](../../USER_GUIDE_WHAT_LUCCA_DOES.md) — whose own rule (line 5) is: *"Every claim below is either observable by you in a live session or points at the file that implements it."*
**Method:** mechanical verification script (`scratch/audit_userguide_claims.py`) + manual constant/symbol chase for every citation the script could not resolve + Nia improvement research pass.
**Verdict legend:** **VERIFIED** (claim matches code) · **STALE** (was true once; code moved on) · **WRONG** (claim contradicts code, or cites a symbol that never existed)

---

## 1. WRONG claims (contradict the code or cite nonexistent symbols)

| # | Guide location | Claim | Code truth |
|---|---|---|---|
| W1 | §2.3 table, row 4 | "`memory_commit` — Disabled, fail-closed. Advertised but refuses every call (see §2.4)." | **Grounded path is live** (WO-9 A2/ADR-010): [`_handle_memory_commit`](../../../src/lucca/core/orchestrator.py:2813) commits facts quote-grounded in the current turn's signed `USER_EXPLICIT` transcript; 21 tests in `tests/test_grounded_memory_commit.py`. It refuses *model-authored* content — that is the gate working, not the tool being disabled. |
| W2 | §2.4 bullet 4 | "The `memory_commit` tool visible to the model remains fail-closed." | Same staleness as W1. |
| W3 | §2.4 bullet 6 | "`python -m lucca.admin memory forget <entry_id>`" | **Command does not exist.** `admin memory` subcommands: `list`, `review-queue`, `review-approve`, `review-reject`, `mark-review`, `unmark-review`, `list-topics`, `rollup` ([`admin.py:819-853`](../../../src/lucca/admin.py:819)). `MemoryStore.forget` exists; no CLI exposes it. → **F-FEAT-07** (documented operator capability missing). |
| W4 | §2.5 table | "`config/skills/good-morning-v1/plan.scm`" | Actual skill id/path: `config/skills/time-greeting-v1/plan.scm`. |
| W5 | §2.3 under-the-hood | "`tests/test_sandbox_rpc.py`" | Actual: `tests/test_persistent_rpc.py`. |
| W6 | §2.4 under-the-hood | "`src/lucca/memory/embeddings.py`" | Actual: `src/lucca/senses/embed.py`. |
| W7 | §0 under-the-hood | "16K ctx per `launch_server.ps1`" | File does not exist anywhere in the tree. Server launch is [`src/lucca/brain/server_ctl.py`](../../../src/lucca/brain/server_ctl.py). |
| W8 | §2.2 item 2 | "`src/lucca/router/heuristic.py:DEFAULT_CONFIDENCE_THRESHOLD`" | No such module constant. Actual: constructor param `confidence_threshold: float = 0.60` ([`heuristic.py:166`](../../../src/lucca/router/heuristic.py:166)). Value correct; symbol wrong. |
| W9 | §2.2 item 3 | "`src/lucca/router/calibration.py:MIN_CALIBRATION_SAMPLES`" | No such constant. Actual: param `min_samples: int = 30` ([`calibration.py:107`](../../../src/lucca/router/calibration.py:107)). Value correct; symbol wrong. |
| W10 | §3 Claim A | "`src/lucca/reasoning/induction.py:MIN_PATTERN_SUPPORT`" | Actual: `MIN_FREQUENCY_THRESHOLD: Final[int] = 3` ([`induction.py:31`](../../../src/lucca/reasoning/induction.py:31)). Value correct; symbol wrong. |
| W11 | §3 Claim A | "`src/lucca/reasoning/lifecycle.py:SHADOW_PROMOTION_THRESHOLD`" | No such constant. Actual: hardcoded `len(rule.success_clusters) < 5` checks ([`lifecycle.py:665,759`](../../../src/lucca/reasoning/lifecycle.py:665)). Value correct; symbol wrong. |
| W12 | §2.4 under-the-hood | "`src/lucca/memory/store.py:RETRIEVAL_TOKEN_BUDGET`" | No such constant in `store.py`. Actual: `format_memory_context(hits, max_tokens: int = 2048)` ([`retrieval.py:46`](../../../src/lucca/memory/retrieval.py:46)). Value correct; symbol and file wrong. |
| W13 | §2.5 under-the-hood | "up to 4 tool rounds per D-BRAIN-05 v2, `src/lucca/core/orchestrator.py:MAX_REASONING_ROUNDS`" | No such constant. Actual: `_stream_llm_speech(max_rounds: int = 8)` ([`orchestrator.py:1907`](../../../src/lucca/core/orchestrator.py:1907)); all callers use the default → **actual behavior is up to 8 rounds**. The "M=4 active rounds" tier in D-BRAIN-05 v2's text is not implemented as a separate cap. → also a DECISIONS.md reconciliation item. |
| W14 | §2.5 under-the-hood | "up to 8 research rounds per `src/lucca/core/cascade.py:MAX_RESEARCH_ROUNDS`" | No such constant in `cascade.py`. Citation fabricated. |
| W15 | §0.1, §2.5, §3 | "capped at 30 in `src/lucca/reasoning/lifecycle.py`" | Actual: `ACTIVE_SKILL_LIMIT: Final[int] = 30` in [`reasoning/skills.py:32`](../../../src/lucca/reasoning/skills.py:32). Value correct; file wrong. |
| W16 | §3 Claim A table | "there is almost no real usage yet (2 recorded decisions)" | Production DB now has **20 decisions** — the D-REAS-08 tripwire fired 2026-09-25. The induction floor (N≥3) is crossed. |

## 2. Cross-document finding

| # | Document | Claim | Code truth |
|---|---|---|---|
| X1 | `docs/DECISIONS.md` D-CASC-01 | Substrates `TELEMETRY=0, WORKSPACE=1, MEMORY=2, REASONING=3, SENSES=4, SYSTEM=5, WEB_FLOOR=6, SELF_HISTORY=7` | Code ([`cascade.py:50-57`](../../../src/lucca/core/cascade.py:50)) and the user guide agree: `WEB=3, ABSTENTION=4, SELF=5, CAPABILITIES=6`. **DECISIONS.md is the stale document** — the guide was right. |

## 3. VERIFIED claims (sample of the pass)

19 tools / `MAX_REGISTRY_TOOLS=19`; 15 skill directories; `EMERGENCY_REFLEX_PATTERN`; `calc_math` registered; `models/MANIFEST.json` pins `gemma-4-12b-heretic`; substrate names match code exactly; `all-MiniLM-L6-v2` in `senses/embed.py`; `admin env-check` exists; `config/rules/calc-open-with-expr-v1.scm` present; `_retired/barge-in-sorry-v1` present; 30-day rollup (`THIRTY_DAYS_SECONDS`, reflection.py:23); `format_memory_context(max_tokens=2048)`; `max_rounds=8` default; sequence-guard taint rules (§2.3) match `sandbox/policy.py`.

**Score: 16 wrong/stale claims, ~25 verified claims.** The guide's *behavioral* descriptions are accurate; its *citations* rotted — exactly the drift class the new static gates (WO-17 drift gates, this session) were built to catch, and a strong argument for extending them to symbol-existence checks (see §5).

## 4. New finding: F-FEAT-07 — `admin memory forget` CLI missing (S2)

The guide promises operator deletion via CLI; the CLI has no such command. `MemoryStore.forget` (soft-delete + audit) and `MemoryManager.delete_memory` (UI-wired) both exist. **Rectification (WO-19f):** add `admin memory forget <entry_id>` calling `MemoryStore.forget(user_confirmed=True)` — never `MemoryManager.delete_memory` (the F-MEM-001/003 bypass path). Until then the guide points at the Settings memory tab.

## 5. Nia improvement mission — the slot-filling opportunity

The guide's own "honest reading" (§2.5) admits most tool-call skills are *typed hints to the model* because the router extracts only `file, url, quoted, app` entities — never `expr`, `term`, `topic`, `query`, `content`. The Nia pass found the mature on-device solution class: **Snips NLU** (intent+slot filling, Rust/Python, designed for offline voice assistants), **Intently NLU** (same data model), and on-device voice-to-tool-call pipelines. A small slot-filling model — an encoder on the Intel NPU per the existing hardware doctrine (encoders on NPU, tree models on CPU) — would let the router supply those slots, **converting 8 yield-heavy skills from hints into autonomous actions**. This is the single largest functional upgrade available to the documented featureset without new hardware or a bigger brain. Proposed as v2 candidate **Rung R5 — NPU slot-filling router** (trigger: WO-19c scheme tests restored + ≥600 labeled decisions, the existing Phase-6 data gate).

## 6. Process lesson (feeds WO-18 Phase 6)

Citation rot outpaced behavioral rot 16:0. The two WO-17 drift gates added this session check *numeric* claims (tool count, version). The next gate class is **symbol-existence**: for every `` `path.py:SYMBOL` `` citation in active docs, assert the file exists and the symbol resolves (AST). `scratch/audit_userguide_claims.py` is the prototype; promote with positive controls.
