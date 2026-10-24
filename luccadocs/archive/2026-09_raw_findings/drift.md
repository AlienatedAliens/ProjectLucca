# Findings — DRIFT (cross-area implementation-vs-archived-spec divergences)

**Subtask:** S2j · **Method:** synthesis over the nine completed area files (`core.md`, `brain.md`, `mem.md`, `rout.md`, `reas.md`, `sbx.md`, `sens.md`, `ui.md`, `test.md`) + the archived specs/ADRs read during those subtasks · **Baseline:** HEAD `ed14f6b` + working tree, delta in [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; every finding cites the owning area findings by ID (no restatement) plus the archived-spec section it diverges from. One finding, one divergence.

**Severity totals: S0 = 0 · S1 = 0 · S2 = 8 · S3 = 2 · S4 = 0 · total = 10.**

Grading note: DRIFT findings record *documented intent vs shipped behaviour* gaps whose local symptoms are already graded in the area files; severities here reflect the divergence's programme consequence, capped at S2 unless a hard invariant is directly contradicted (those were graded S0 in their owning areas).

---

## 1. Divergence matrix (archived claim → as-built)

| # | Archived source | Claimed | As-built | Owning findings |
|---|---|---|---|---|
| 1 | ADR-008 / Spec 01 §1, §4 | Four processes; `lucca-npu` owns Whisper/Kokoro/embeddings; core ≤ 900 MB; ZMQ ping/pong health | Four processes exist, but core runs ASR+TTS in-process (870 MB at cap); npu double-loads the same models; heartbeat is a sleep no-op; pong RSS is fabricated | F-CORE-002, F-SENS-012, F-SENS-005, F-CORE-005 |
| 2 | ADR-001 / Spec 07 §4 | Whisper-large-v3-turbo via OpenVINO, NPU→GPU→CPU ladder; every turn transcribed; confidence-gated provenance | `distil-small.en` CPU int8 English-only hard-coded; ladder dead; `lowconf_logprob` unconsumed | F-SENS-001, F-SENS-014 |
| 3 | ADR-004 / Spec 09 §2 | File-sandbox (`--network none`) + ephemeral web-sandbox containers, host-validated RPC | Arg renderers exist; **no container is ever created**; file tools and `run_python` default to unconfined host execution; web fetch host-side | F-SBX-001, F-SBX-002, F-SBX-003 |
| 4 | ADR-006 / Spec 03 §3–4 | Provenance tiers with per-tier signers; `USER_EXPLICIT` from verified transcripts; LOWCONF read-back flow | Gate+signers are correct components but unwired; the only live write path (UI admin) bypasses the gate with `signature="manual"`; LOWCONF has no consumer; ASR confidence gate absent | F-MEM-001, F-MEM-004, F-SENS-014, F-CORE-003 |
| 5 | Spec 04 / ADR-002 | SQLite+FTS5+sqlite-vec memory: commit path, backfill, quota, audits | Schema correct and trigger-gated; store/retrieval/manager unwired except the gate-bypassing admin CRUD; backfill queue dead; `tool_contents`/`pending_confirmations` tables dead | F-MEM-007, F-MEM-008, F-CORE-003 |
| 6 | Spec 05 §8–9 / ADR-007 | Rule DSL lifecycle: quarantine ≥ 5 clusters / 0 failures / regression suite; persistence | State machine correct in-memory and untested against real signals; no persistence; no executor; validator's constant-true check unimplemented | F-REAS-002, F-REAS-003, F-REAS-005 |
| 7 | Spec 06 §1, §3, §7 / ADR-007 | Heuristic router with deterministic intent→RULE; decision telemetry; conformal classifier after the data gate | Router unwired; intent never influences action; probabilities fabricated; classifier path absent end-to-end | F-ROUT-001, F-ROUT-002, F-ROUT-005, F-ROUT-010 |
| 8 | Spec 08 §1–6 / ADR-001 | Chunker/demux: newline boundaries, idle flush 350 ms, 30-stream demux gate, constant-true protection | Boundaries/flush/gates partially or wholly unimplemented; per-delta normalisation; quote-depth race; T-CHK-06/11/13/14 untested | F-BRAIN-018, F-BRAIN-019, F-BRAIN-005, F-BRAIN-021, F-BRAIN-022 |
| 9 | Spec 09 §3–7 | Workspace quota, search budgets, sequence cap 4/turn | Quota checkable but unenforced; search unbounded on the fallback; `MAX_TOOL_CALLS_PER_TURN` unimplemented | F-SBX-008, F-SBX-014, F-SBX-007 |
| 10 | Spec 10 §1–4 / Spec 11 | 16 trace points populated; per-stage budgets; latency regression detection; config sources lucca.toml/.env | 7 trace points never populated; clocks unusable for sub-50 ms budgets; no regression detection; config is env-only despite documented five sources | F-CORE-008, F-CORE-009, F-CORE-020, F-CORE-056 |
| 11 | Spec 11 §1 / Spec 12 §3, §8 | Fail-closed prod master key; known-dev-key list; risk policy single source `core/risk_policy.py`; `models verify` | No fail-closed; `KNOWN_DEV_KEYS` dead; policy lives in `sandbox/policy.py`; no sha256 manifest or verification | F-CORE-013, F-MEM-005, F-BRAIN-003, F-CORE-022 |
| 12 | Spec 12 TM-01…TM-18 | Threat-model control matrix | Controls verified implemented: TM-06 (weaker), TM-08, TM-14, TM-15-partial; controls absent on the shipped path: TM-01 (bypass), TM-03/04 (host-side fetch), TM-05/07 (no containers), TM-10 (validator gap), TM-13 | F-SBX-001…005, F-MEM-001, F-REAS-005, F-BRAIN-003 |

---

## 2. Findings

Ordered by severity, then by ID. Every finding re-reviewed per Charter §3.5 (log in §7); `Status: OPEN`.

### F-DRIFT-001 — Phase 1–4 subsystems are specified, partially built, and not instantiated: the architecture exists as components, not as a system

| Field | Value |
|---|---|
| **ID** | F-DRIFT-001 |
| **Title** | Phase 1–4 subsystems are specified, partially built, and not instantiated: the architecture exists as components, not as a system |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/core/orchestrator.py` (no router/memory/reasoning imports); `src/lucca/reasoning/lifecycle.py:85-94`; `src/lucca/router/heuristic.py:55`; `src/lucca/memory/store.py:43`; `luccadocs/archive/2026-09-17_pre_phase4_audit/11_phase_plan_v2.md` §Phases 3–4 |
| **Status** | OPEN |

**Evidence**

Consolidated from the nine area files' wiring verdicts: `RuleLifecycleManager`, `HybridRetriever`/`MemoryStore` (except the bypassing manager), `HeuristicRouter`, `ConformalGuard`, `derive_label`, `check_data_volume_gate`, `EgressVerifier`, `get_*_sandbox_run_args`, `format_memory_context`, `spoken_prefix`, `restart_server`, `LocalEmbeddingPort` — every one tested or testable, **none constructed by any production entry point**. The turn loop (F-CORE-003) runs ASR→LLM→TTS with tool execution and nothing else.

**What is wrong / assumed / missing**

Phases 3 (memory) and 4 (router/rules/decisions) delivered components whose integration into the turn loop does not exist: no rule fires before the LLM, no memory is retrieved or committed, no decision is logged, no label is derived. The phase-plan gates that depend on accumulated real data (≥ 600 labelled decisions, ≥ 1 promoted rule) are therefore unreachable by operation alone. Which side is right: the phase plan's *intent* — the components were the right build; the missing half is the wiring, and the plan never recorded the split.

**Why it matters**

The audit's single largest structural finding: every subsystem-specific remediation is local; this one is the programme. It also explains the honest-telemetry family — components report fabricated values because nothing consumes the real ones yet.

**Questions this raises**

1. None — the wiring order is the remediation.

**Proposed remediation**

1. Wire in this order (each step a separate PR with its area's tests): (a) router→turn loop with honest telemetry (F-ROUT-001/002/005); (b) rule engine shadow evaluation feeding `record_shadow` (F-REAS-003); (c) rule persistence (F-REAS-002); (d) memory retrieval→prompt via `format_memory_context` (F-BRAIN-011/F-MEM-017) and commit via the gate (F-MEM-001's fix first); (e) rule promotion on real clusters.
2. Gate each step on its area's verification tests plus a new T2 `test_phase_wiring_N` per step.
3. Update the phase plan to mark Phases 3–4 "components complete, integration pending" until (e) lands.

**Verification test**

- **Tier:** T2 (per step)
- **Input:** wired orchestrator + fakes
- **Expected output:** decisions logged, rules evaluated, memory committed through the gate
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest -m tier2 -q` (after F-TEST-001 registers the tier)

**Cross-references:** F-CORE-003, F-ROUT-001, F-REAS-002/003, F-MEM-001/007/008, F-BRAIN-011, F-TEST-001

---

### F-DRIFT-002 — The threat model's control matrix is aspirational: 8 of 18 controls are absent or non-binding on the shipped path

| Field | Value |
|---|---|
| **ID** | F-DRIFT-002 |
| **Title** | The threat model's control matrix is aspirational: 8 of 18 controls are absent or non-binding on the shipped path |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `luccadocs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/12_threat_model.md:19-38`; owning findings per row of the divergence matrix |
| **Status** | OPEN |

**Evidence**

Row-by-row verification during S2b–S2i (divergence matrix row 12): implemented — TM-06 (weaker: no `O_NOFOLLOW`), TM-08 (sha256 audit, dual-path), TM-14 (launcher), TM-15-partial (loopback bind; session-token absent), TM-16 (redirect re-validation, modulo F-SBX-003); absent or non-binding — TM-01 (admin bypass + no gate wiring), TM-03/TM-04 (fetch host-side; egress N/A), TM-05/TM-07 (no containers; POSIX-only rlimits), TM-10 (constant-true check missing), TM-13 (dev-key list dead).

**What is wrong / assumed / missing**

The threat model documents controls as the system's design; the shipped path enforces fewer than half of them, and the sandbox fallback (F-SBX-001) is the default rather than the exception. The document itself is accurate about *intent* — it is the implementation, not the model, that drifted.

**Why it matters**

A threat model whose control column is not traceable to code is a security document describing a different product; every future security review would re-derive this audit's sandbox findings from scratch.

**Questions this raises**

1. None.

**Proposed remediation**

1. In the post-audit docs set: re-issue Spec 12 with a per-control traceability column — control → code location → verification test ID — marking absent controls as "planned Phase N" instead of present.
2. Adopt the traceability rule: no TM row ships without a test ID (mechanical check in F-TEST-002's import-linter config or a T0 grep test).
3. Verification: the re-issued matrix has a test ID on every implemented row and a phase tag on every absent row.

**Verification test**

- **Tier:** T0
- **Input:** the traceability grep
- **Expected output:** every control row accounted for
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_static_gates.py::test_threat_model_traceability -q` (new)

**Cross-references:** F-SBX-001…005, F-MEM-001, F-REAS-005, F-BRAIN-003, F-CORE-013

---

### F-DRIFT-003 — The canonical latency budget cannot be measured by the shipped instrumentation, and the boot path reports fabricated measurements

| Field | Value |
|---|---|
| **ID** | F-DRIFT-003 |
| **Title** | The canonical latency budget cannot be measured by the shipped instrumentation, and the boot path reports fabricated measurements |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/core/trace.py:14-60`; `src/lucca/core/orchestrator.py:333,469`; `scripts/run_spike02_suite.py:117-124`; `src/lucca/ui/speech_bubble.py:99`; `luccadocs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/10_latency_trace_and_budgets.md` §1–2 |
| **Status** | OPEN |

**Evidence**

Consolidated: 7 of 16 trace points never populated; `time.monotonic_ns()` at ≈ 15.6 ms Windows granularity stored as absolute values (F-CORE-008); `t_llm_sent` stamped before ASR (F-CORE-009); the spike suite hard-codes cold start 42.5 s (F-BRAIN-007); the UI shows a constant "382 ms" (F-UI-001); `sys.pong` RSS constants (F-SENS-005). No component measures the Spec 10 S1→S5 chain the 475 ms canonical gate is defined on.

**What is wrong / assumed / missing**

The project's central numeric promise — push-to-talk to first audio in ≈ 475 ms — has no instrument that could verify or refute it: the trace schema exists, half the points are dead, the clock is too coarse for the stage budgets, the one script that claims to measure fabricates, and the one badge the user sees is a constant.

**Why it matters**

Every latency claim in every document is currently unfalsifiable; the Phase-1 sign-off (which required both audio and transcript latency reports) never produced them (`S1_SUMMARY` §3: both MISSING).

**Questions this raises**

1. None.

**Proposed remediation**

1. Fix the substrate first: F-CORE-008's clock remediation (relative ms, `perf_counter_ns`), F-CORE-009's trace points, F-CORE-056's persistence.
2. Then wire one measurement per stage boundary (the stage list is already in Spec 10 §2) and a `lucca-admin latency --last N` implementation (currently `Unknown command`, F-CORE-026/027).
3. Delete or re-measure the three fabrications (F-BRAIN-007, F-UI-001, F-SENS-005/013).
4. Add a T3 gate: 20-turn median per stage within the Spec 10 §2 budgets, written to `logs\latency_report_<ts>.md` (F-TEST-010's helper).

**Verification test**

- **Tier:** T3
- **Input:** 20 real turns
- **Expected output:** per-stage medians within budget; report file written
- **Threshold:** total ≤ 600 ms median / 800 ms p95 (audio mode)
- **Command:** `uv run pytest -m hw tests/test_latency_e2e.py -q` (spec'd harness, to be authored)

**Cross-references:** F-CORE-008/009/056, F-BRAIN-007, F-UI-001, F-SENS-005/013, F-TEST-010

---

### F-DRIFT-004 — The provenance chain is correct at both ends and open in the middle: the invariant holds vacuously and fails at the one live path

| Field | Value |
|---|---|
| **ID** | F-DRIFT-004 |
| **Title** | The provenance chain is correct at both ends and open in the middle: the invariant holds vacuously and fails at the one live path |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/memory/gate.py:54-135`; `src/lucca/memory/signers.py`; `src/lucca/memory/manager.py:84-150`; `src/lucca/senses/asr.py:54-118`; `luccadocs/archive/2026-09-17_pre_phase4_audit/08_adr/ADR-006_provenance_tiers_and_signers.md` |
| **Status** | OPEN |

**Evidence**

End 1 (signing): four disjoint signers, tested authorisation matrix (T-PROV-02) — but constructed by nothing (F-REAS wiring verdict), and the ASR confidence gate that would choose `USER_EXPLICIT` vs `USER_EXPLICIT_LOWCONF` is unimplemented (F-SENS-014). Middle (transport): no turn path carries a transcript to a signer at all (F-CORE-003). End 2 (admission): the gate is mechanically correct and trigger-backed (`mem_bi_eligible`) — but the one live write path, `MemoryManager.add_memory`, writes `signature="manual"` envelopes with an unchecked provenance string (F-MEM-001), and its edit/delete siblings corrupt the audit chain (F-MEM-002/003).

**What is wrong / assumed / missing**

ADR-006's design is "provenance is enforced at every boundary"; as-built it is enforced at a boundary no traffic crosses, and unenforced at the boundary all traffic would use. The invariant (Charter §5.1) is therefore satisfied vacuously in the running product and violated by construction the moment the admin path (or any unwired consumer) is exercised.

**Why it matters**

This is the audit's core-invariant finding family; the remediation order matters — fixing the middle (wiring) before the ends (admin path, ASR gate) would activate the bypass at scale.

**Questions this raises**

1. None — order recorded in F-MEM-001/F-DRIFT-001 remediations.

**Proposed remediation**

1. Sequence per F-DRIFT-001 step (d), with the admin path fix (F-MEM-001) and the ASR provenance hint (F-SENS-014) as preconditions of the memory wiring PR.
2. Add the T-PROV end-to-end test the spec implies: real transcript → signer → gate → store → retrieval hit with provenance intact (T2, fakes at the model seams).
3. Verification: the end-to-end test green + F-MEM-001's signature-verifiability test green.

**Verification test**

- **Tier:** T2
- **Input:** the end-to-end test above
- **Expected output:** provenance preserved through the full chain
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest -m tier2 tests/test_provenance_e2e.py -q`

**Cross-references:** F-MEM-001/002/003/004, F-SENS-014, F-CORE-003, F-REAS-003

---

### F-DRIFT-005 — The ADR-001 model-supply chain delivers a renamed substitute with no verification, contradicting the ADR's own identity claim

| Field | Value |
|---|---|
| **ID** | F-DRIFT-005 |
| **Title** | The ADR-001 model-supply chain delivers a renamed substitute with no verification, contradicting the ADR's own identity claim |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `scripts/download_llm_models.py:11-47`; `luccadocs/archive/2026-09-17_pre_phase4_audit/08_adr/ADR-001_inference_engine.md:22-23,65`; `luccadocs/audit/evidence/S1_07c_models_manifest.txt` |
| **Status** | OPEN |

**Evidence**

ADR-001 pins `C:\ProjectLucca\models\llm\ultravox-v0_5-llama-3_1-8b-Q6_K.gguf` and `mmproj-…-Q8_0.gguf` as Ultravox release artefacts (Q8_0 mmproj ≈ 0.74 GB); the downloader fetches the **f16** mmproj and the **bartowski Llama-3.1-8B-Instruct** backbone, renaming both to the Ultravox names (F-BRAIN-002/026); on-disk mmproj is 1.28 GiB (f16-size, `S1_07c`); no MANIFEST, no hash check anywhere (F-BRAIN-003); ADR-001's own conditional ("Verify in spike S10: if v0.5 LoRA-tuned the backbone…") was never executed as specified.

**What is wrong / assumed / missing**

The ADR's decision ("matches the brief's model and quantization literally") is not what the disk holds; the substitution may be functionally acceptable (ADR-001 :65 sanctions it *after* S10), but the identity claim — on which the audit's settled facts, the VRAM budget, and the threat model's weight-verification residual risk all rest — is false as deployed.

**Why it matters**

The owner has ratified Option A (true ggml-org backbone + manifest, D-AUD-05) — this finding records the divergence itself so the re-download closes a *documented* gap rather than an undocumented substitution.

**Questions this raises**

1. None — execution queued as remediation task #1 per D-AUD-05.

**Proposed remediation**

1. Execute D-AUD-05: download the true ggml-org backbone + Q8_0 mmproj, pin sha256 in `MANIFEST.json`, wire verification into the downloader and `start_server`, re-run the audio fixture suite and ADR-001 S10; fall back to Option B (true-name retention) only on worse measured tool-call validity.
2. Amend ADR-001 (post-audit docs) with the substitution history and the executed S10 numbers.
3. Verification: F-BRAIN-002/003's tests green; VRAM within the Q8_0 budget (≤ 7 500 MiB).

**Verification test**

- **Tier:** T3
- **Input:** fresh download + spike re-run
- **Expected output:** identity verified by hash; S10 ≥ 18/20; VRAM ≤ 7 500 MiB
- **Threshold:** per D-AUD-05
- **Command:** `uv run python scripts/download_llm_models.py && uv run python scripts/run_spike02_suite.py`

**Cross-references:** F-BRAIN-002/003/026, D-AUD-05

---

### F-DRIFT-006 — The system prompt, capability manifest, UI surfaces, and sample assets jointly advertise a system that does not exist

| Field | Value |
|---|---|
| **ID** | F-DRIFT-006 |
| **Title** | The system prompt, capability manifest, UI surfaces, and sample assets jointly advertise a system that does not exist |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/brain/prompt_builder.py:47-91`; `src/lucca/sandbox/service.py:144-215`; `src/lucca/ui/app.py:125-130`; `src/lucca/ui/settings_dialog.py:272-273,2258,2331`; `luccadocs/audit/findings/brain.md` F-BRAIN-004 |
| **Status** | OPEN |

**Evidence**

Four coordinated surfaces claim: MicroScheme pathways executing "in sub-10ms before neural inference" (six named pathways absent from `src/`); ZMQ ports 5557-5559 (actual 47001-47003); "Codebase Inspection" read-only access (unregistered `read_codebase_file`); `query_capabilities` returning a fictional manifest (fictional reasoning pathways, workspace/codebase claims); a shipped sample rule referencing non-existent primitives; help text describing rule execution where only parsing runs. The T3 hardware failure (`query_capabilities` instead of `launch_app`) is the measured consequence.

**What is wrong / assumed / missing**

The fictional capability surface is not one defect but a designed marketing layer inside the product: the model is *told* it has capabilities, the *tool* confirms them, and the *UI* advertises them — so the hallucination is self-consistent and self-reinforcing, which is why it survived every green test run. Which side is right: the implementation prompt's mission statement ("every claim must be verifiably real") and the owner's D-AUD-03 (strip fictional persona content).

**Why it matters**

This is the mechanism behind the measured wrong-tool failure and the root cause any surface-level fix (editing one file) would leave intact.

**Questions this raises**

1. None — D-AUD-03 already ratified the strip.

**Proposed remediation**

1. Execute F-BRAIN-004's remediation (prompt + manifest truth pass) and F-UI-004/005's (UI claims), as one coordinated change gated by a new T1 `test_capability_claims_real`: grep system prompt + `query_capabilities` output + commorose descriptions + help text for the forbidden tokens (5557, the six pathway names, Codebase Inspection) — all absent.
2. Verification: the claims test green; T3 tool-call turn returns `launch_app`.

**Verification test**

- **Tier:** T1 + T3
- **Input:** the claims test + the hw tool-call turn
- **Expected output:** no fictional claims; correct tool selected
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_prompt_builder.py::test_self_awareness_claims_are_real tests/test_ui_widgets.py::test_codebase_claims_honest -q && uv run pytest -m hw tests/test_phase1_live_hw.py::test_live_phase1_tool_call_turn -q`

**Cross-references:** F-BRAIN-004, F-SBX-012, F-UI-004/005, D-AUD-03

---

### F-DRIFT-007 — The documented configuration contract (five sources, canonical defaults, env names) is not the implemented contract

| Field | Value |
|---|---|
| **ID** | F-DRIFT-007 |
| **Title** | The documented configuration contract (five sources, canonical defaults, env names) is not the implemented contract |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/core/config.py:132-177`; `luccadocs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/11_observability_config_and_lifecycle.md` §1; `luccadocs/audit/findings/core.md` §5 |
| **Status** | OPEN |

**Evidence**

Spec 11 §1 documents: CLI flags → env vars → `lucca.toml` → `.env` → defaults; canonical defaults `ptt.key="right ctrl"`, `tts.voice="af_heart"`; exit code 2 on validation errors; observability via structured per-process logs. As-built: two sources (env vars with `__` nesting + defaults — F-CORE-020); `ptt.key="alt-gr"`, `tts.voice="genki_heroine"` (F-CORE-049); validation errors are tracebacks (F-CORE-028); no structured log files exist (F-CORE-032); `.env.example` teaches the retired contract (F-TEST-006); and the hard-coded-path family (F-CORE-030 + 5 area instances) bypasses the whole system anyway.

**What is wrong / assumed / missing**

The configuration system that ships is env-vars-plus-defaults with drift in the two most user-visible defaults and a documentation example that configures nothing. Which side is right: partially the shipped code (env+defaults is a defensible v1 simplification) — but the defaults drift and the dead example are unambiguous defects, and the five-source claim should be re-issued as two sources until toml/CLI land.

**Why it matters**

Configuration is the operator's only lever on a local-first product; a documented contract that differs from the implemented one makes every operational runbook wrong.

**Questions this raises**

1. None.

**Proposed remediation**

1. In the post-audit docs set: re-issue the configuration contract as env-vars + defaults (two sources), align the defaults to the shipped values (per Q-11/D-AUD-03), and fix `.env.example` per F-TEST-006.
2. Add the T0 env-contract test from F-TEST-006 and the exit-code test from F-CORE-028's remediation.
3. Verification: docs + tests agree with `core/config.py` field-by-field.

**Verification test**

- **Tier:** T0
- **Input:** the env-contract test
- **Expected output:** zero dead keys; defaults match shipped config
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_env_example.py -q`

**Cross-references:** F-CORE-020/028/030/049/050, F-TEST-006, D-AUD-03/04

---

### F-DRIFT-008 — The shutdown and supervision contract (Spec 01 §7) is unimplemented at every layer: UI, supervisor, and process teardown

| Field | Value |
|---|---|
| **ID** | F-DRIFT-008 |
| **Title** | The shutdown and supervision contract (Spec 01 §7) is unimplemented at every layer: UI, supervisor, and process teardown |
| **Severity** | S2 — Medium |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/main.py:129-162`; `src/lucca/ui/app.py:471-478`; `src/lucca/senses/npu_proc.py` (no stop); `luccadocs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/01_process_topology_and_ipc.md` §7; `luccadocs/audit/evidence/S1_37_shutdown.txt` |
| **Status** | OPEN |

**Evidence**

Spec 01 §7 orders shutdown as `ui.state offline` → `play.abort` → stop turns → flush SQLite ≤ 5 s → `VACUUM INTO` backup → SIGTERM children 3 s → llama-server stop. As-built: UI quit publishes nothing (F-UI-002); the supervisor only reacts to `KeyboardInterrupt` and never restarts or degrades (F-CORE-005/006); `NPUProcess` has no stop and dies by `TerminateProcess` (F-SENS-012); graceful `taskkill` left the supervisor and two children alive after 10 s (`S1_37`); no SQLite flush exists (nothing writes); llama-server is stopped only if we spawned it.

**What is wrong / assumed / missing**

Every layer of the documented shutdown sequence is missing; the observed shutdown is "force-kill everything and hope no data was mid-write" — which is safe today only because nothing persists yet (memory unwired), i.e. the contract will matter exactly when the memory wiring lands.

**Why it matters**

Data-loss risk scales with the remediation programme: F-DRIFT-001 wires persistence into a system with no flush/ordering discipline.

**Questions this raises**

1. None.

**Proposed remediation**

1. Sequence the shutdown fix with F-DRIFT-001's wiring: (a) UI publishes offline (F-UI-002 step 1); (b) supervisor reacts to child exits (F-CORE-005/006) and runs the spec order; (c) `NPUProcess.stop()` + clean ZMQ teardown (F-SENS-012 step 2); (d) memory flush + `VACUUM INTO` before child termination once F-MEM-001's commit path is live.
2. Add `tests/test_shutdown.py::test_shutdown_order_spec01` (T2): scripted quit → assert offline → abort → flush → backup → terminate ordering via recorded calls.

**Verification test**

- **Tier:** T2
- **Input:** the test above
- **Expected output:** spec order observed
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_shutdown.py -q`

**Cross-references:** F-CORE-005/006/029, F-UI-002, F-SENS-012, F-MEM-001

---

### F-DRIFT-009 — The docs set is structurally unreachable from the code it documents: paths, component names, and ports in AGENTS/SKILL reference a layout that never existed

| Field | Value |
|---|---|
| **ID** | F-DRIFT-009 |
| **Title** | The docs set is structurally unreachable from the code it documents: paths, component names, and ports in AGENTS/SKILL reference a layout that never existed |
| **Severity** | S3 — Low |
| **Category** | DOCS |
| **Location** | `AGENTS.md`; `.agents/skills/lucca-pipeline/SKILL.md` §4; `luccadocs/archive/2026-09-17_pre_phase4_audit/` (whole set); `luccadocs/audit/00_AUDIT_CHARTER.md` §10 |
| **Status** | OPEN |

**Evidence**

SKILL.md documents `app\bin\llama-server.exe` (actual: `app\llama-server\`), `/opt/lucca/lucca-egress.sh` (absent; code uses the repo path as root — F-SBX-012), `lucca-admin sandbox verify` (unimplemented), `uv run lint` (unimplemented — F-TEST-008); the charter itself was amended to note these stale references (§10). The system prompt's fictional architecture (F-BRAIN-004) is the in-product face of the same documentation drift.

**What is wrong / assumed / missing**

The charter's own §10 defers stale-path handling to a later subtask; this finding is that subtask's pin: the operational documentation (SKILL.md, AGENTS.md) is the operator's entry point and currently misdirects every first action (start server at the wrong path, apply egress at the wrong path, run an unimplemented admin command, run an unimplemented lint gate).

**Why it matters**

Operator trust and onboarding: the first four commands an operator runs per the docs fail or differ from reality.

**Questions this raises**

1. None.

**Proposed remediation**

1. In the post-audit docs programme: regenerate SKILL.md §4/§2 from code truth (exe path from `build_launch_command`, egress from `egress.apply_rules`, admin commands from `admin.py`, lint from F-TEST-008's new script); keep AGENTS.md's invariants, replace its paths.
2. Add a T0 `test_docs_paths_exist`: extract paths from SKILL.md and assert each exists or is explicitly marked as post-audit.
3. Verification: the gate green; operator commands from the docs succeed.

**Verification test**

- **Tier:** T0
- **Input:** the docs-path gate
- **Expected output:** zero dangling operational paths
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_static_gates.py::test_docs_paths_exist -q`

**Cross-references:** F-CORE-026/027/036, F-TEST-002/008, F-SBX-012, Charter §10

---

### F-DRIFT-010 — The ADR corpus itself is incomplete and inconsistent with the shipped decisions (ADR-009 cited but missing; ADR-001 command drift; ADR-010 forward-looking-only trap)

| Field | Value |
|---|---|
| **ID** | F-DRIFT-010 |
| **Title** | The ADR corpus itself is incomplete and inconsistent with the shipped decisions (ADR-009 cited but missing; ADR-001 command drift; ADR-010 forward-looking-only trap) |
| **Severity** | S3 — Low |
| **Category** | DOCS |
| **Location** | `luccadocs/audit/03_BASELINE.md:103` (commit `b75ce27` cites ADR-009); `luccadocs/archive/2026-09-17_pre_phase4_audit/08_adr/` (ADR-001…008, 010 — no 009); `ADR-001_inference_engine.md:40` (`--log-format json`, F-BRAIN-023); `ADR-010` (64 GB upgrade — forward-looking, Charter §3.3) |
| **Status** | OPEN |

**Evidence**

`03_BASELINE.md` §3: commit `b75ce27` "cites an **ADR-009** that does not exist in the archived docs set (archived ADRs: 001–008 and 010)" — the affect/decision commit references a decision record that was never written. ADR-001's canonical command includes the flag the binary rejects (F-BRAIN-023). ADR-010 (64 GB RAM upgrade) is forward-looking but sits in the same numbered series as accepted decisions, inviting accidental reliance (the charter had to fence it explicitly, §3.3).

**What is wrong / assumed / missing**

The decision record — the system's source of truth for *why* — is missing one ADR, stale on one command, and ambiguous on one forward-looking decision. Post-audit, every remediation that touches these areas must re-derive intent from code because the record is unreliable.

**Why it matters**

Informational for behaviour, structural for the docs programme: ADR-009's absence means the affect/decision design (the affected commit's subject) has no recorded rationale at all.

**Questions this raises**

1. None.

**Proposed remediation**

1. In the post-audit docs programme: write the missing ADR-009 (affect/decision layer — content recoverable from commit `b75ce27` + `core/affect.py`), amend ADR-001 per F-BRAIN-023, and mark ADR-010's status line "FUTURE — not ratified; do not rely" at the top of the document.
2. Add a T0 ADR-integrity test: every `ADR-\d+` reference in commits/docs resolves to a file; every ADR has a Status line.
3. Verification: gate green on the post-audit docs set.

**Verification test**

- **Tier:** T0
- **Input:** the ADR-integrity gate
- **Expected output:** all references resolve; statuses present
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_static_gates.py::test_adr_integrity -q`

**Cross-references:** F-BRAIN-023, F-CORE-049, Charter §3.3/§10

---

## 4. Assumptions register

| # | Assumption | Why unverified | Risk if false |
|---|---|---|---|
| A-D-01 | The archived specs describe intent worth preserving (not noise to discard wholesale) | The docs programme decides per-document; this audit graded divergence, not intent quality | Discarding good intent with the drift |
| A-D-02 | Phase order (router → rules → memory) is the right wiring sequence | Recorded as F-DRIFT-001's decision; alternatives (memory first) plausible | Re-work if dependencies differ |
| A-D-03 | Threat-model controls marked "absent" are genuinely absent (not implemented elsewhere) | Row-by-row repo searches during S2b–S2i | Missed controls change the matrix |
| A-D-04 | The fictional-capability surface is unintentional (not a deliberate demo layer) | No record found; D-AUD-03 ratified stripping | If intentional, F-DRIFT-006's remediation conflicts with owner intent |
| A-D-05 | `distil-small.en` under-performs large-v3-turbo on the product's transcript quality needs | No product-path accuracy benchmark exists | F-SENS-001's remediation priority |

## 5. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-D-01 | Should the archived specs be re-issued as-is-minus-drift, or rewritten from code truth (the charter's stated plan)? | Determines whether F-DRIFT findings are fixed in docs or in code first | owner |
| Q-D-02 | Which wiring step of F-DRIFT-001 lands first given the model-supply work (D-AUD-05/06) in parallel? | Programme sequencing | architect |
| Q-D-03 | Is the fictional-capability layer (F-DRIFT-006) to be deleted entirely or replaced with a true capability manifest? | Prompt/UI redesign scope | owner |

## 6. Coverage gaps

### 6.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| Spec-to-code traceability (per-control test IDs) | Spec 12 | none (F-DRIFT-002) |
| Canonical latency chain measurement | Spec 10 §1–2 | none end-to-end (F-DRIFT-003) |
| Provenance end-to-end (sign→gate→store→retrieve) | ADR-006 / Spec 03 | component tests only (F-DRIFT-004) |
| Model identity verification | ADR-001 | none pre-D-AUD-05 (F-DRIFT-005) |
| Capability-claim honesty across surfaces | impl. prompt mission | none (F-DRIFT-006) |
| Config contract conformance | Spec 11 §1 | none (F-DRIFT-007) |
| Shutdown order | Spec 01 §7 | none (F-DRIFT-008) |
| Docs-path integrity | — | none (F-DRIFT-009) |
| ADR corpus integrity | — | none (F-DRIFT-010) |

### 6.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| Phase 3/4 commit-gated test suites | Memory/router/reasoning phases complete | Components tested in isolation; integration absent (F-DRIFT-001) |
| Sign-off bundles §4 (partial) | Phase gates verified | Latency reports missing; spike suite fabricating; hw reports absent (F-DRIFT-003, F-BRAIN-007, F-TEST-010) |

## 7. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** The divergence matrix (12 rows) was drafted first and each row audited for whether it warranted its own finding or was fully covered by owning area findings: rows 1–12 produced 10 findings; rows fully covered elsewhere (e.g. the affect-layer unwiring, F-CORE-031; the exit-code drift, F-CORE-028) were left as matrix rows only. Reviewing F-DRIFT-001 (unwiring) surfaced the sequencing dependency with D-AUD-05/06 (model supply first) and the memory-wiring precondition chain (F-MEM-001 before wiring) — recorded as ordering constraints, not separate findings.
2. **Unasked questions.** 3 registered (§5); decisions recorded where derivable (F-DRIFT-001 wiring order; F-DRIFT-006 coordinated claims test).
3. **Unwarranted assumptions.** The first draft of F-DRIFT-002 said "10 of 18 controls absent" — row-by-row recount set it to "8 absent or non-binding" with the implemented set named. The first draft of F-DRIFT-003 asserted "no latency measurement exists anywhere" — corrected: the spike suite and TTFT probes measure components; what is missing is the *chain* measurement the budget is defined on. A-D-04 (fictional surface intentionality) was made explicit after realising D-AUD-03 presupposes it.
4. **Incomplete planning.** F-DRIFT-001's remediation is a programme-level sequence, not a single patch — each step names its owning area findings and verification tier; the owner-owned calls (docs re-issue strategy, capability-layer fate) are parked as Q-D-01/Q-D-03.
5. **Architectural flaws.** This entire area *is* the F-ARCH roll-up input: F-DRIFT-001 (not instantiated), F-DRIFT-002 (governance not instantiated, with F-TEST-002/008), F-DRIFT-006 (honesty), F-DRIFT-008 (shutdown contract) are the four programme-level candidates the recursive logs of BRAIN/MEM/ROUT/REAS/SBX/SENS/UI/TEST nominated; the ARCH roll-up subtask should consolidate them with core.md §11's nominations.

Severity re-grades during the pass: all DRIFT findings capped at S2 per the area-file precedence rule (local symptoms already graded; the two hard-invariant contradictions — provenance bypass, zero-`Any` — remain S0/S1 in their owning areas, cross-referenced from F-DRIFT-004/001); F-DRIFT-009/010 set S3 (documentation integrity, no runtime impact).
