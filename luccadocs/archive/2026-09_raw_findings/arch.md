# Findings — ARCH (programme-level architectural findings, consolidated from all area recursive logs)

**Subtask:** S2k (final) · **Method:** consolidation of the F-ARCH candidates nominated in the recursive logs of `core.md` §11, `brain.md` §12, `mem.md` §7, `rout.md` §7, `reas.md` §7, `sbx.md` §7, `sens.md` §7, `ui.md` §7, `test.md` §7, `drift.md` §7, per Charter §3.5 step 5 · **Baseline:** HEAD `ed14f6b` + working tree · **Written:** 2026-09-18 (UTC)

**Severity totals: S0 = 0 · S1 = 0 · S2 = 6 · S3 = 2 · S4 = 0 · total = 8.**

Grading note: ARCH findings are structural diagnoses whose local symptoms are already graded in the area files. They are graded by programme consequence and **each carries a consolidated remediation** executable by the post-audit programme — fixing an ARCH finding is not a code edit but a sequencing decision plus the referenced area remediations.

---

## 1. The consolidated findings

### F-ARCH-001 — The Phase 2–4 architecture is specified and component-complete but not instantiated: the product is a voice loop with a dormant everything-else

| Field | Value |
|---|---|
| **ID** | F-ARCH-001 |
| **Title** | The Phase 2–4 architecture is specified and component-complete but not instantiated: the product is a voice loop with a dormant everything-else |
| **Severity** | S2 — Medium |
| **Category** | ARCH |
| **Location** | Consolidates: F-CORE-003 (router/memory/reasoning absent from the turn loop), F-ROUT-001 (decision tables empty), F-REAS-002/003 (no persistence/executor), F-MEM-007/008 (dead tables/backfill), F-SBX-002 (containers never created), F-BRAIN-035 (dead `restart_server`), F-UI-011 (unreachable `degraded` theme) |
| **Status** | OPEN |

**What is wrong**

The nominating recursive logs converged on one structural diagnosis: every Phase 2–4 subsystem exists as a tested (or testable) component and as a correct schema/protocol, and **no production entry point connects them**. The turn loop is ASR→LLM→TTS with tool execution; router decisions, rule evaluation, memory retrieval/commit, provenance signing, and sandbox containment are all reachable only from tests. The consequence chain is mechanical: no decisions logged → data-volume gate permanently blocked → Phase-6 human gates (≥ 600 labelled decisions, ≥ 1 promoted rule) unreachable by operation alone → the phased-build promise broken at the integration seam rather than at any component.

**Why it matters at programme level**

Every area's local remediations are necessary but jointly insufficient: wiring them in the wrong order (e.g. memory retrieval before the gate fix F-MEM-001, or rule execution before F-REAS-004's outcome semantics) would activate defects at scale. The architecture needs a single wiring programme with ordering constraints, not ten independent patches.

**Consolidated remediation**

1. Execute the F-DRIFT-001 sequence with its recorded preconditions: (a) router + honest telemetry; (b) rule shadow evaluation + outcome-semantics fix (F-REAS-004) + persistence (F-REAS-002); (c) admin-path gate fix (F-MEM-001) **before** memory wiring; (d) retrieval→prompt via the compliant renderer (F-BRAIN-011/F-MEM-017); (e) promotion on real clusters.
2. Gate each step on a T2 wiring test (F-TEST-001's new tier) and re-run the full T1 suite per step.
3. Update the phase plan: Phases 3–4 marked "components complete, integration pending" until step (e).

**Verification test**

- **Tier:** T2 per step; final `uv run pytest -m tier2 -q` green with wiring tests included.

**Cross-references:** F-DRIFT-001, F-DRIFT-004; every consolidating finding above.

---

### F-ARCH-002 — The quality-governance layer is declaratively complete and functionally absent

| Field | Value |
|---|---|
| **ID** | F-ARCH-002 |
| **Title** | The quality-governance layer is declaratively complete and functionally absent |
| **Severity** | S2 — Medium |
| **Category** | ARCH |
| **Location** | Consolidates: F-TEST-001 (tier2 unregistered/empty), F-TEST-002 (import-linter unconfigured), F-TEST-003 (static gates disabled), F-TEST-008 (`uv run lint` missing, no CI/pre-commit), F-CORE-034/036/054, F-TEST-010 (hw reports), F-TEST-015 (blocker home) |
| **Status** | OPEN |

**What is wrong**

The governance apparatus — four test tiers, an import-boundary contract, strict typing, a composite lint gate, machine-readable hw reports, and a blockers register — is cited in AGENTS.md, SKILL.md, the threat model, and the testing matrix, and is implemented as: two registered markers, no linter config, non-strict mypy, a missing command, no CI, and no report substrate. The audit's three S0s and the majority of S1/S2s are classes the installed tooling catches by default once configured.

**Why it matters at programme level**

The remediation programme will be executed by weaker models (GLM 5.3 Flash per the finding templates) against 223 findings; without the governance layer, the programme cannot distinguish fixed from regressed. The governance findings are therefore prerequisites for executing the rest of the audit's remediations safely.

**Consolidated remediation**

1. Land, in order: F-TEST-008 (lint script), F-TEST-002 (import-linter contracts), F-TEST-003 (strict gates, together with the three zero-`Any` retypings), F-TEST-001 (tier2 registration + seeds), F-TEST-007 (LUCCA_HOME isolation), F-TEST-010 (hw reports).
2. Then declare T0 mandatory per commit (CI or pre-commit per Q-T-02).
3. Verification: full gate suite green on the post-remediation tree; a seeded violation fails the gate.

**Verification test**

- **Tier:** T0
- **Input:** `uv run lint && uv run pytest -m "not hw and not soak" -q`
- **Expected output:** all green; seeded violations caught
- **Threshold:** n/a — boolean
- **Command:** `uv run lint`

**Cross-references:** All F-TEST findings; F-CORE-035/036/054; Charter §5.5

---

### F-ARCH-003 — Recorded metrics are systematically dishonest: six components fabricate or suppress measurements the user and the logs present as real

| Field | Value |
|---|---|
| **ID** | F-ARCH-003 |
| **Title** | Recorded metrics are systematically dishonest: six components fabricate or suppress measurements the user and the logs present as real |
| **Severity** | S2 — Medium |
| **Category** | ARCH |
| **Location** | Consolidates: F-CORE-008/009 (trace clock/points), F-CORE-046 (quadratic caption traffic), F-BRAIN-007 (spike suite fabrications), F-BRAIN-017 (zero usage), F-ROUT-005 (constant probabilities), F-SBX-011 (fabricated hardware telemetry), F-SENS-005/013 (fake pong/selftest), F-UI-001 (constant latency badge), F-DRIFT-003 |
| **Status** | OPEN |

**What is wrong**

Eight independent components emit fabricated or structurally meaningless numbers: a constant latency badge on the primary widget, hard-coded cold-start in the sign-off generator, zero token usage, constant decision probabilities, fake RSS in the health protocol, fictional hardware statuses, dead trace points on a clock too coarse for the budgets they gate. No single defect explains it — the pattern is that **nothing consumes these metrics**, so nothing notices they are wrong (the F-DRIFT-001 corollary).

**Why it matters at programme level**

The audit could not verify the product's central numeric promise (475 ms voice-to-audio) because no instrument measures it; after remediation, the same gap would hide regressions. The fix is a rule, not eight patches: *no metric is recorded that nothing measures; no metric is displayed that nothing records.*

**Consolidated remediation**

1. Adopt the honesty rule as a T0 gate (new `test_static_gates.py::test_no_fabricated_metrics`): grep for the known constants ("382 ms", 42.5, `rss_mb=50.0`, `rss_mb=250.0`, `compile_cache_hit=True`) — zero matches.
2. Wire the real substrates per F-DRIFT-003 (trace clock/points → `lucca-admin latency`), then reconnect the consumers (badge, pong, selftest) to measured values.
3. Re-run the spike suite with the F-BRAIN-007 fixes so the Phase-0 bundle is real.

**Verification test**

- **Tier:** T0 + T3
- **Input:** the gate + an instrumented 20-turn run
- **Expected output:** zero fabricated constants; per-stage medians within budget
- **Threshold:** Spec 10 §2 budgets
- **Command:** `uv run pytest tests/test_static_gates.py::test_no_fabricated_metrics -q`

**Cross-references:** All listed findings; F-DRIFT-003

---

### F-ARCH-004 — The model-supply chain has no identity verification: the product cannot state what weights it runs

| Field | Value |
|---|---|
| **ID** | F-ARCH-004 |
| **Title** | The model-supply chain has no identity verification: the product cannot state what weights it runs |
| **Severity** | S2 — Medium |
| **Category** | ARCH |
| **Location** | Consolidates: F-BRAIN-002 (renamed backbone), F-BRAIN-003 (no sha256/MANIFEST), F-BRAIN-026 (f16 mmproj named Q8_0), F-CORE-022/025 (env-check omissions), F-DRIFT-005, D-AUD-05 |
| **Status** | OPEN |

**What is wrong**

The chain is: Hub download (no hash) → rename to the Ultravox identity → boot (existence-only check) → env-check green → every turn runs weights no artefact can vouch for. Spec 12 scopes supply-chain compromise as mitigated *only* by the sha256 manifest — which does not exist. The ADR-001 identity claim ("matches the brief's model literally") is false as deployed, and the audit's measured symptoms (hallucinated tool calls on tones, T3 wrong-tool) are consistent with a projector/backbone mismatch.

**Why it matters at programme level**

Every quality measurement in the audit (TTFT, tool-call validity, transcript quality) was taken against unverified weights; D-AUD-05's re-download resets that baseline, making this the first remediation task — before any performance or accuracy regression claim is trusted.

**Consolidated remediation**

1. Execute D-AUD-05 (true ggml-org backbone + true Q8_0 mmproj + `MANIFEST.json` + verification in downloader and `start_server` + env-check predicate).
2. Then execute the spike re-run (S6/S10) and re-baseline all measured budgets.
3. Add the T0 supply-chain gate: `test_model_identity` — `parse_gguf_file(general.name)` contains `ultravox`, hash matches manifest.

**Verification test**

- **Tier:** T1 + T3
- **Input:** fresh download + spike
- **Expected output:** hash-verified identity; S10 ≥ 18/20
- **Threshold:** per D-AUD-05
- **Command:** `uv run python scripts/download_llm_models.py && uv run pytest tests/test_server_ctl.py::test_start_server_rejects_hash_mismatch -q`

**Cross-references:** F-BRAIN-002/003/026, F-CORE-022/025, F-DRIFT-005, D-AUD-05

---

### F-ARCH-005 — A self-consistent fictional capability layer spans the system prompt, tool manifest, UI, and help text

| Field | Value |
|---|---|
| **ID** | F-ARCH-005 |
| **Title** | A self-consistent fictional capability layer spans the system prompt, tool manifest, UI, and help text |
| **Severity** | S2 — Medium |
| **Category** | ARCH |
| **Location** | Consolidates: F-BRAIN-004 (prompt fiction + T3 consequence), F-DRIFT-006 (four surfaces), F-UI-004/005 (commorose/help/sample rule), F-SBX-012 (`read_codebase_file`), `query_capabilities` fictional manifest (`service.py:144-215`) |
| **Status** | OPEN |

**What is wrong**

The companion is *told* it has six LISP pathways, a codebase-inspection capability, and specific architecture internals (ports 5557-5559); the *tool* it can call returns the same fiction as ground truth; the *UI* advertises it in three places; and the shipped sample rule uses primitives that fail the shipped validator. Each surface is individually minor; jointly they form a self-reinforcing hallucination that produced the measured T3 wrong-tool failure and the fabricated `query_capabilities` answers users receive.

**Why it matters at programme level**

D-AUD-03 already ratified stripping the fictional persona; this finding extends the strip to the capability fiction across all four surfaces with one coordinated change and one honesty gate, so the surfaces cannot drift apart again.

**Consolidated remediation**

1. Execute F-BRAIN-004's prompt/manifest truth pass, F-UI-004/005's UI relabelling, and F-SBX-012's `read_codebase_file` deletion as one change set.
2. Add the T0 claims gate: `test_capability_claims_real` (grep all four surfaces for the forbidden tokens).
3. Re-run the T3 tool-call turn; verify `launch_app` is selected.
4. Per Q-U-01/Q-S-02: if the codebase-inspection capability is wanted later, it arrives as a registered tool + honest prompt claim + UI claim in one PR.

**Verification test**

- **Tier:** T1 + T3
- **Input:** the claims gate + the hw tool-call turn
- **Expected output:** zero fictional claims; correct tool selected
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_static_gates.py::test_capability_claims_real -q`

**Cross-references:** F-BRAIN-004, F-DRIFT-006, F-UI-004/005, F-SBX-012, D-AUD-03

---

### F-ARCH-006 — The concurrency model across the audio path is undefined: shared memory without synchronisation, blocking inference on the turn thread, and a GIL-era design in a multi-process topology

| Field | Value |
|---|---|
| **ID** | F-ARCH-006 |
| **Title** | The concurrency model across the audio path is undefined: shared memory without synchronisation, blocking inference on the turn thread, and a GIL-era design in a multi-process topology |
| **Severity** | S2 — Medium |
| **Category** | ARCH |
| **Location** | Consolidates: F-SENS-002 (ring header RMW race), F-SENS-003 (stale slice), F-CORE-011 (barge-in does not join the turn thread), F-CORE-014 (state clobber in `finally`), F-CORE-015 (sync ASR in ingest lock), F-CORE-017 (TTS blocks streaming), F-BRAIN-006 (LLMClient shared abort state) |
| **Status** | OPEN |

**What is wrong**

The audio path spans three processes and at least five threads (sounddevice in/out callbacks, PTT poller, TTS synthesis, ZMQ ctl/bus, turn worker), sharing two lock-free rings whose headers are plain read-modify-write. Barge-in sets flags that writers may overwrite; the turn thread blocks the ingest lock on confirmation ASR; TTS blocks the token stream; the LLM client's abort state is instance-global. Each is a local finding; jointly they mean **the product has no stated concurrency model** — no document says which thread owns which resource, so every fix is local and every interaction is emergent.

**Why it matters at programme level**

Barge-in is the product's signature interaction and its latency gate (≤ 30 ms) is measured only client-side; the race family produces intermittent, unreproducible failures in the 0 %-coverage audio process that no amount of feature work will stabilise.

**Consolidated remediation**

1. Write the concurrency contract first (one page: per-resource owner, permitted blocking, barge-in path) as a new ADR.
2. Land the local fixes in contract order: F-SENS-002 (mutex/atomics on ring headers), F-BRAIN-006 (per-stream abort state), F-CORE-014/011 (thread join + state discipline), F-CORE-017 (synthesis queue), F-CORE-015 (confirmation ASR off the ingest lock).
3. Add the race regression tests from the findings plus a T3 barge-in measurement to slot-idle (F-BRAIN-014 step 2).
4. Verification: race tests green under repeat; barge-in ≤ 30 ms measured.

**Verification test**

- **Tier:** T1 + T3
- **Input:** the race and barge-in tests above
- **Expected output:** no lost updates; barge-in within budget
- **Threshold:** ≤ 30 ms key-down → silence; ≤ 100 ms slot idle
- **Command:** `uv run pytest tests/test_ring_buffer.py tests/test_llm_client_race.py -q && uv run pytest -m hw tests/test_phase1_live_hw.py::test_live_barge_in_abort -q`

**Cross-references:** All listed findings; F-SENS-002/003, F-CORE-011/014/015/017, F-BRAIN-006/014

---

### F-ARCH-007 — The shutdown contract is unimplemented at every layer, and persistence remediation will inherit the gap

| Field | Value |
|---|---|
| **ID** | F-ARCH-007 |
| **Title** | The shutdown contract is unimplemented at every layer, and persistence remediation will inherit the gap |
| **Severity** | S3 — Low |
| **Category** | ARCH |
| **Location** | Consolidates: F-CORE-005/006/029/038/039, F-UI-002, F-SENS-012 (no NPU stop), F-DRIFT-008, F-MEM-001 (persistence incoming) |
| **Status** | OPEN |

**What is wrong**

Spec 01 §7's ordered shutdown (offline → abort → stop turns → flush → backup → terminate) exists at no layer: the UI exits silently, the supervisor only reacts to KeyboardInterrupt and never degrades, children are `TerminateProcess`ed, the NPU loop has no stop, and the data-loss risk scales directly with the memory-wiring remediation.

**Why it matters at programme level**

The wiring programme (F-ARCH-001) introduces persisted state into a system whose teardown is force-kill; the shutdown contract must land between "rules persisted" and "memory wired" in the sequencing.

**Consolidated remediation**

1. Sequence inside F-DRIFT-001's programme: after F-REAS-002 (rule persistence), before F-MEM-001 (memory commit wiring) — implement F-UI-002's offline publication, F-CORE-005/006's supervisor reaction, F-CORE-029's order, F-SENS-012's `stop()`.
2. Verification: `tests/test_shutdown.py::test_shutdown_order_spec01` (T2) green.

**Verification test**

- **Tier:** T2
- **Input:** scripted quit
- **Expected output:** spec order observed
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_shutdown.py -q`

**Cross-references:** F-CORE-005/006/029/038/039, F-UI-002, F-SENS-012, F-DRIFT-008

---

### F-ARCH-008 — The audit-freeze process failed silently: the tree mutated mid-audit with no commit, attribution, or re-baseline trigger

| Field | Value |
|---|---|
| **ID** | F-ARCH-008 |
| **Title** | The audit-freeze process failed silently: the tree mutated mid-audit with no commit, attribution, or re-baseline trigger |
| **Severity** | S3 — Low |
| **Category** | ARCH |
| **Location** | Consolidates: F-BRAIN-008 (three files changed post-S0/post-S1), F-TEST-009 (TEST-side instance), `luccadocs/audit/03b_BASELINE_DELTA.md`, Charter §3.1/§3.4 |
| **Status** | OPEN |

**What is wrong**

The findings-only freeze (Charter §3.1) has no enforcement mechanism and no declared procedure for legitimate mid-audit fixes: the mutation was discovered by line-count drift, initially mis-scoped (all five brain modules) due to a metric mismatch, corrected by re-inventory (F-BRAIN-008's third pass), and handled by owner decision — the process worked only because a human was in the loop.

**Why it matters at programme level**

The remaining audit subtasks and the whole remediation programme depend on stable baselines; the same silent mutation during remediation would corrupt the fix-verification chain (finding → fix → verification test → closed).

**Consolidated remediation**

1. Adopt the F-BRAIN-008 step-3 rule: no edits to frozen trees except through a declared fix-forward event that triggers re-baseline (`03b`-style delta record + evidence rows).
2. For the remediation programme: one commit per finding ID (`fix(F-BRAIN-009): …`), so the finding→commit→verification chain is mechanical.
3. Verification: `03b_BASELINE_DELTA.md` exists (done); the remediation programme's log shows per-finding commits.

**Verification test**

- **Tier:** T0
- **Input:** the delta record + future commit log
- **Expected output:** every mutation attributable
- **Threshold:** n/a — boolean
- **Command:** `git log --oneline` (post-audit)

**Cross-references:** F-BRAIN-008, F-TEST-009, Charter §3.1/§3.4

---

## 2. Programme sequencing (consolidated)

| Order | Work | Findings consumed | Gate |
|---|---|---|---|
| 0 | Governance layer (lint script, import-linter, strict gates, tier2, isolation) | F-ARCH-002, F-TEST-001/002/003/007/008 | T0 green |
| 1 | Model supply (D-AUD-05) + supply-chain verification | F-ARCH-004, F-BRAIN-002/003/026 | T3 spike + hash gate |
| 2 | Capability-honesty pass (D-AUD-03 + prompt/manifest/UI strip) | F-ARCH-005, F-BRAIN-004, F-DRIFT-006, F-UI-004/005 | T1 claims gate |
| 3 | Shutdown contract | F-ARCH-007, F-CORE-005/006/029, F-UI-002, F-SENS-012 | T2 order test |
| 4 | Wiring programme step a–b (router, rules shadow) | F-ARCH-001, F-ROUT-001/002/005, F-REAS-003/004 | T2 wiring tests |
| 5 | Wiring step c (admin gate fix + rule persistence) | F-MEM-001/002/003, F-REAS-002 | T1 provenance tests |
| 6 | Wiring step d–e (memory retrieval/commit, promotion) | F-BRAIN-011, F-MEM-017, F-DRIFT-001 step d–e | T2 end-to-end provenance |
| 7 | Concurrency contract + local fixes | F-ARCH-006, F-SENS-002/003, F-BRAIN-006, F-CORE-011/014/015/017 | T1 race tests |
| 8 | Instrumentation honesty + latency measurement | F-ARCH-003, F-DRIFT-003, F-CORE-008/009/056 | T3 latency report |
| — | Continuous | F-ARCH-008 process rule | per-commit attribution |

---

## 3. Assumptions register

| # | Assumption | Why unverified | Risk if false |
|---|---|---|---|
| A-A-01 | The wiring order in §2 respects all real dependencies | Derived from the findings' preconditions; no implementation spike yet | Re-sequencing during the programme |
| A-A-02 | The weaker-model execution model (GLM 5.3 Flash) can execute the atomic remediations as written | Template design assumption; not tested at scale | Programme velocity/quality |
| A-A-03 | D-AUD-05's true-backbone swap improves (or at least does not degrade) measured behaviour | F-BRAIN-002's fallback clause exists for the contrary case | Re-baseline to Option B |
| A-A-04 | The honesty rule (F-ARCH-003) is enforceable by grep for the known constants | The enumerated set is finite today; new fabrications would need new detection | Gate misses future fabrications |
| A-A-05 | No further mid-audit mutations occur | One observed; process rule unenforced until adopted | Repeat of F-BRAIN-008 |

## 4. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-A-01 | Does the remediation programme target the current 10-tab UI + CT styling, or the post-D-AUD-03 redesigned UI? | Changes the scope of F-UI-003/008 and the persona strip | owner |
| Q-A-02 | Is `run_python` retained (container-mandatory) or dropped until the container path is the only path? | F-SBX-001/Q-S-01; largest security lever | owner |
| Q-A-03 | Which model is the Phase-6 classifier target (Ultravox backbone vs gpt-oss-20B per D-AUD-06)? | Affects wiring step 4's telemetry schema | owner / architect |

## 5. Recursive review log

Second pass applied Charter §3.5's five questions:

1. **Oversights:** The first draft consolidated six candidates; re-reading every recursive log surfaced shutdown (F-ARCH-007) and the process breach (F-ARCH-008) as nominated-but-unconsolidated, and split the original "wiring + governance" mega-candidate into F-ARCH-001/002 (different remediation shapes: sequencing vs configuration).
2. **Unasked questions:** 3 registered; the sequencing table (§2) resolves the "what order" question the area findings each raised locally.
3. **Unwarranted assumptions:** The first draft graded F-ARCH-001 S1 — downgraded to S2 per the drift-area precedence rule (programme consequence, local symptoms already graded); the "voice loop works today" claim was verified against S1's evidence (T3 failures notwithstanding, the loop completes).
4. **Incomplete planning:** Each ARCH finding carries a consolidated remediation naming its member findings and the verification gates; the sequencing table is the executable programme skeleton.
5. **Architectural flaws:** None further — this file is the roll-up.

Severity re-grades: none (all set at consolidation).
