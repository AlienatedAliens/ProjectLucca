# v1.0 Action Log — Open Findings & Bug Tracker

**Generated:** 2026-09-24 (WO-16 Phase 2)  
**Source:** Exhaustive scan of all WO-8 through WO-15 audit findings across 14 audit modules  
**Review Baseline:** Commit `b6fc285` (`v1.0.0`)

---

## 1. Summary

| Classification | Count | Description |
|---|:---:|---|
| **BUG_V1** | **8** | Confirmed defects in existing v1.0 feature code to be fixed in Phase 5 |
| **DOC_DRIFT** | **6** | Factual documentation drift to be corrected in Phase 4 |
| **DESIGN_DEBT** | **12** | Architectural and design limitations deferred to `docs/V2_BACKLOG.md` |
| **TEST_GAP** | **2** | Test fixtures / assertions requiring calibration to be updated in Phase 5 |
| **Total Open Items** | **28** | Exhaustively tracked and classified |

---

## 2. Items Catalog

### [ITEM-001] Router Known Apps Whitelist Leak
- **Source:** `docs/audit/findings/rout.md`, Finding `F-ROUT-003`
- **Classification:** BUG_V1
- **Severity:** Medium
- **Feature Area:** router
- **Description:** `DEFAULT_KNOWN_APPS` in `src/lucca/router/heuristic.py:37-52` includes shell and terminal applications (`cmd`, `powershell`, `code`, `vscode`). In `tool_whitelist.toml`, shell executables are strictly barred for safety. The router should never identify banned shell executables as valid known application intents.
- **Code Location:** `src/lucca/router/heuristic.py:47-50`
- **User-Visible Impact:** Yes — user speech asking to "launch cmd" or "open powershell" is classified as a valid `launch_app` intent at high confidence rather than being rejected or passed to the LLM for safety deflection.
- **Resolution Path:** Fix in WO-16 Phase 5: remove `cmd`, `powershell`, `code`, `vscode` from `DEFAULT_KNOWN_APPS`.
- **Status:** OPEN

### [ITEM-002] Greedy 1-2 Word Candidate App Matcher
- **Source:** `docs/audit/findings/rout.md`, Finding `F-ROUT-004`
- **Classification:** BUG_V1
- **Severity:** Medium
- **Feature Area:** router
- **Description:** In `src/lucca/router/heuristic.py:224-226`, after checking known apps, if no file entity was found and candidate text is $\le 2$ words, the router blindly classifies the phrase as `launch_app` intent at $0.85$ confidence (e.g. "start flight simulator" -> `launch_app` at $0.85$).
- **Code Location:** `src/lucca/router/heuristic.py:224-226`
- **User-Visible Impact:** Yes — arbitrary 1-2 word utterances following launch verbs bypass intent calibration and produce erroneous `launch_app` tool calls for non-existent apps.
- **Resolution Path:** Fix in WO-16 Phase 5: restrict fallback to confirmed installed apps or require confidence $< 0.50$ to trigger LLM fallback.
- **Status:** OPEN

### [ITEM-003] Labeler Negation Priority Inversion
- **Source:** `docs/audit/findings/rout.md`, Finding `F-ROUT-006`
- **Classification:** BUG_V1
- **Severity:** Low
- **Feature Area:** router
- **Description:** In `src/lucca/router/labeler.py:68-73`, the check for Priority 4 (`confirm_declined` -> `INDETERMINATE`) is evaluated before Priority 2 (`next_transcript` explicit negation -> `NEG`).
- **Code Location:** `src/lucca/router/labeler.py:67-74`
- **User-Visible Impact:** Low — in turns where explicit correction and decline coincide, telemetry labels the turn as indeterminate rather than negative.
- **Resolution Path:** Fix in WO-16 Phase 5: reorder checks to match declared priority (Priority 2 explicit negation before Priority 4 user declined).
- **Status:** OPEN

### [ITEM-004] RouterPort Protocol Signature Mismatch
- **Source:** `docs/audit/findings/rout.md`, Finding `F-ROUT-007`
- **Classification:** BUG_V1
- **Severity:** Low
- **Feature Area:** router
- **Description:** `RouterPort` in `src/lucca/ports.py:106-109` defines `route(feats: RouteFeatures) -> RouteDecision`, whereas `HeuristicRouter.route()` in `src/lucca/router/heuristic.py:276` takes unpacked keyword arguments (`transcript: str, any_active_rule_fired: bool, ...`).
- **Code Location:** `src/lucca/router/heuristic.py:276` and `src/lucca/ports.py:106-109`
- **User-Visible Impact:** No — runtime uses `HeuristicRouter` directly, but breaks hexagonal port polymorphism.
- **Resolution Path:** Fix in WO-16 Phase 5: add support for `route(feats)` or an adapter method on `HeuristicRouter` to satisfy `RouterPort`.
- **Status:** OPEN

### [ITEM-005] Decision SQLite Write Errors Swallowed Without Telemetry Counter
- **Source:** `docs/audit/findings/rout.md`, Finding `F-ROUT-009`
- **Classification:** BUG_V1
- **Severity:** Low
- **Feature Area:** router
- **Description:** In `src/lucca/router/heuristic.py:482-483`, exceptions during `_log_decision_sqlite` are caught and logged via `logger.warning`, but no failure counter is incremented.
- **Code Location:** `src/lucca/router/heuristic.py:482-484`
- **User-Visible Impact:** No — telemetry degradation is unmetered.
- **Resolution Path:** Fix in WO-16 Phase 5: add `db_write_failures` counter attribute to router.
- **Status:** OPEN

### [ITEM-006] Dead Conjunct in Heuristic Clarify Probability Branch
- **Source:** `docs/audit/findings/rout.md`, Finding `F-ROUT-011`
- **Classification:** BUG_V1
- **Severity:** Low
- **Feature Area:** router
- **Description:** In `src/lucca/router/heuristic.py:319`, the condition `(intent in INTENT_TO_RULE and conf < 0.35 and not any_active_rule_fired)` contains a redundant or misleading conjunct `not any_active_rule_fired` when `rule_eligible` is already false.
- **Code Location:** `src/lucca/router/heuristic.py:319`
- **User-Visible Impact:** No — clean up dead logic.
- **Resolution Path:** Fix in WO-16 Phase 5: simplify clarify branch condition.
- **Status:** OPEN

### [ITEM-007] Silent Fallback on Whitelist Parse Error
- **Source:** `docs/audit/findings/sbx.md`, Finding `F-SBX-013`
- **Classification:** BUG_V1
- **Severity:** Low
- **Feature Area:** sandbox
- **Description:** In `src/lucca/sandbox/policy.py`, loading an invalid `tool_whitelist.toml` falls back silently to default apps without logging an explicit error or raising an audit event.
- **Code Location:** `src/lucca/sandbox/policy.py`
- **User-Visible Impact:** Low — user configuration mistakes silently revert to defaults.
- **Resolution Path:** Fix in WO-16 Phase 5: log structured warning on parse error with fallback notice.
- **Status:** OPEN

### [ITEM-008] Long URL Validation in Web Sandbox
- **Source:** `docs/audit/findings/adjacent_defects_diagnostic_summary.md`, Defect `M5-11`
- **Classification:** BUG_V1
- **Severity:** Medium
- **Feature Area:** sandbox
- **Description:** Realistic complex search queries generating long URLs (> 128 chars) should be validated properly rather than rejected by arbitrary length limits.
- **Code Location:** `src/lucca/sandbox/service.py`
- **User-Visible Impact:** Yes — search URLs with detailed parameters can fail validation.
- **Resolution Path:** Fix in WO-16 Phase 5: ensure URL length ceiling matches RFC limits (2048 chars).
- **Status:** OPEN

### [ITEM-009] Test Fixture q09 Action Receipt Framing Gap
- **Source:** `docs/audit/findings/COGNITIVE_AUDIT_2026-09.md`, Finding `F21`
- **Classification:** TEST_GAP
- **Severity:** Low
- **Feature Area:** test
- **Description:** In `tests/test_a1_live_hw.py`, probe `q09` checks introspective accuracy for a cancelled web search. When action receipts are enabled, the model accurately recalls "the search request was cancelled", which was flagged as a miss by keyword-only check expecting search keywords.
- **Code Location:** `tests/test_a1_live_hw.py` probe `q09`
- **User-Visible Impact:** No — test fixture under-crediting.
- **Resolution Path:** Fix in WO-16 Phase 5: update `q09` assertion to accept cancellation receipt framing.
- **Status:** OPEN

### [ITEM-010] Windows Shutdown Handler Contention in Test Tier
- **Source:** `docs/audit/findings/WO8_WP4_findings_2026-09-21.md`, Finding `F-WO8-07`
- **Classification:** TEST_GAP
- **Severity:** Low
- **Feature Area:** test
- **Description:** `tests/test_shutdown.py` times out intermittently on Windows due to Fortran / OpenBLAS `CTRL_BREAK_EVENT` signal routing differences.
- **Code Location:** `tests/test_shutdown.py`
- **User-Visible Impact:** No — CI test timeout.
- **Resolution Path:** Fix in WO-16 Phase 5: adjust test timeout and signal emulation for Windows.
- **Status:** OPEN

### [ITEM-011] Native Tool Count and Registry Cap Inconsistency
- **Source:** Known Error Checklist #1 & #2, `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17`
- **Classification:** DOC_DRIFT
- **Severity:** Medium
- **Feature Area:** docs
- **Description:** Documentation states "15 sandboxed tools... capped at 16". The actual implementation in `src/lucca/core/capabilities.py` defines 18 tools and sets `MAX_REGISTRY_TOOLS = 18`.
- **Code Location:** `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17`, `docs/specs/STUDIO_CAPABILITY_ROADMAP.md`
- **User-Visible Impact:** Confusing capability reporting in user guide and specifications.
- **Resolution Path:** Correct in WO-16 Phase 4 to 18 native tools and cap 18.
- **Status:** OPEN

### [ITEM-012] Epistemic Substrate Count Documentation Drift
- **Source:** Known Error Checklist #3 & #6, `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17`, `README.md`
- **Classification:** DOC_DRIFT
- **Severity:** Medium
- **Feature Area:** docs
- **Description:** Documentation states "7 cascade substrates" (or "5-Substrate" in README). The actual code enum `EpistemicSubstrate` in `src/lucca/core/cascade.py:49-56` defines 8 substrates (`TELEMETRY=0` through `SELF_HISTORY=7`).
- **Code Location:** `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17`, `README.md:35`
- **User-Visible Impact:** Inaccurate architectural description.
- **Resolution Path:** Correct in WO-16 Phase 4 to 8 cascade substrates across all active documents.
- **Status:** OPEN

### [ITEM-013] Non-Existent Code Constants Cited in Documentation
- **Source:** Known Error Checklist #4 & #5, `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17`
- **Classification:** DOC_DRIFT
- **Severity:** Medium
- **Feature Area:** docs
- **Description:** `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17` cites `src/lucca/core/cascade.py:SUBSTRATE_ORDER` and `src/lucca/reasoning/lifecycle.py:MAX_ACTIVE_RULES`. Neither constant exists by that name in the source code.
- **Code Location:** `docs/USER_GUIDE_WHAT_LUCCA_DOES.md:17`
- **User-Visible Impact:** Broken code citations in documentation.
- **Resolution Path:** Correct in WO-16 Phase 4 to cite actual code constructs (`EpistemicSubstrate` enum and rule lifecycle manager).
- **Status:** OPEN

### [ITEM-014] Configuration Sources Documentation Mismatch
- **Source:** `docs/audit/findings/drift.md`, Finding `F-DRIFT-007`
- **Classification:** DOC_DRIFT
- **Severity:** Low
- **Feature Area:** docs
- **Description:** Documentation in `ARCHITECTURE.md` advertises 5 layered configuration sources (CLI, env, TOML, .env, defaults) whereas code only loads environment variables and Pydantic defaults.
- **Code Location:** `docs/ARCHITECTURE.md`
- **User-Visible Impact:** User expectation of TOML configuration loading.
- **Resolution Path:** Correct in WO-16 Phase 4 to match actual configuration hierarchy.
- **Status:** OPEN

### [ITEM-015] Stale File Paths and Commands in AGENTS.md / SKILL.md
- **Source:** `docs/audit/findings/drift.md`, Finding `F-DRIFT-009`
- **Classification:** DOC_DRIFT
- **Severity:** Low
- **Feature Area:** docs
- **Description:** Historical file paths and obsolete CLI invocations remain in agent instructions.
- **Code Location:** `AGENTS.md`, `GEMINI.md`
- **User-Visible Impact:** Agent navigation confusion.
- **Resolution Path:** Audit and clean in WO-16 Phase 4.
- **Status:** OPEN

### [ITEM-016] Missing Architecture Decision Record ADR-009
- **Source:** `docs/audit/findings/drift.md`, Finding `F-DRIFT-010`
- **Classification:** DOC_DRIFT
- **Severity:** Low
- **Feature Area:** docs
- **Description:** ADR-0009 is cited in commit messages and docs but was saved as `docs/adr/0009_audio_concurrency_contract.md`.
- **Code Location:** `docs/DECISIONS.md`, `docs/adr/`
- **User-Visible Impact:** Broken link reference.
- **Resolution Path:** Reconcile in WO-16 Phase 4.
- **Status:** OPEN

### [ITEM-017] ACT_THEN_NARRATE Multi-Action Output Aggregation
- **Source:** `docs/audit/findings/COGNITIVE_AUDIT_2026-09.md`, Finding `F11`
- **Classification:** DESIGN_DEBT
- **Severity:** Medium
- **Feature Area:** core
- **Description:** When an induced or procedural MicroScheme rule produces a multi-action plan (e.g. 2 tool calls), the narration generator currently only verbalizes the final tool result.
- **Code Location:** `src/lucca/core/turn_pipeline.py`
- **User-Visible Impact:** Intermediate tool actions in a compound rule are not verbally described to the user.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (multi-action verbalization).
- **Status:** OPEN

### [ITEM-018] Transcript Normalization Divergence (Router vs Rule Engine)
- **Source:** `docs/audit/findings/COGNITIVE_AUDIT_2026-09.md`, Finding `F12`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** core
- **Description:** The HeuristicRouter evaluates the raw ASR transcript string, while the MicroScheme rule evaluator receives a normalized transcript token sequence.
- **Code Location:** `src/lucca/core/orchestrator.py`
- **User-Visible Impact:** Subtle boundary cases where punctuation or casing affects routing but not rule matching.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (unified transcript tokenizer).
- **Status:** OPEN

### [ITEM-019] Dedicated CLARIFY Action Handler
- **Source:** `docs/audit/findings/COGNITIVE_AUDIT_2026-09.md`, Finding `F13`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** core
- **Description:** `RouteAction.CLARIFY` routes to `FULL_LOOP` with a hint rather than having a distinct sub-50ms conversational reflex handler.
- **Code Location:** `src/lucca/core/orchestrator.py`
- **User-Visible Impact:** Clarification queries invoke the 12B model instead of a fast conversational reflex.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (dedicated clarify reflex).
- **Status:** OPEN

### [ITEM-020] Dynamic Model-Callable Async Task Initiation
- **Source:** `docs/audit/findings/COGNITIVE_AUDIT_2026-09.md`, Finding `F15`
- **Classification:** DESIGN_DEBT
- **Severity:** Medium
- **Feature Area:** brain
- **Description:** The asynchronous task subsystem exists and executes in background workers, but the primary LLM does not have a direct tool to initiate long-running autonomous background tasks.
- **Code Location:** `src/lucca/brain/`
- **User-Visible Impact:** Background tasks must be triggered via code or rule procedures.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (autonomous async task invocation).
- **Status:** OPEN

### [ITEM-021] In-Session Live Retrieval of DecisionRecord / TurnTrace
- **Source:** `docs/audit/findings/COGNITIVE_AUDIT_2026-09.md`, Finding `F19`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** memory
- **Description:** Decision records and turn traces are written to SQLite and JSONL, but are not indexed into the in-session vector or FTS5 memory search cascade for live meta-cognitive querying.
- **Code Location:** `src/lucca/memory/retrieval.py`
- **User-Visible Impact:** Lucca cannot inspect her own low-level decision routing records during live conversation.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (decision trace memory indexing).
- **Status:** OPEN

### [ITEM-022] Configuration-Driven Behavioral Heuristics
- **Source:** `docs/audit/findings/COGNITIVE_AUDIT_2026-09.md`, Finding `F20`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** core
- **Description:** Keyword patterns for follow-up detection, entity extraction, and celebration filtering are partly defined in Python code constants rather than loaded from `heuristics.toml`.
- **Code Location:** `src/lucca/core/orchestrator.py`, `src/lucca/core/cascade.py`
- **User-Visible Impact:** Modifying heuristic thresholds requires code edits rather than configuration changes.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (externalize all heuristics to TOML).
- **Status:** OPEN

### [ITEM-023] Decision Records JSONL Rotation & Pruning
- **Source:** `docs/audit/findings/rout.md`, Finding `F-ROUT-008`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** router
- **Description:** Decision records JSONL log appends indefinitely without file rotation or disk size bounding.
- **Code Location:** `src/lucca/router/heuristic.py`
- **User-Visible Impact:** Disk usage grows continuously over months of heavy local usage.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (JSONL log rotation).
- **Status:** OPEN

### [ITEM-024] Process Topology Refactor (In-Process vs Independent NPU)
- **Source:** `docs/audit/findings/core.md`, Finding `F-CORE-002`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** core
- **Description:** ASR and TTS execute in the core process with multi-threading, while `lucca-npu` serves as a parallel process. A full separation where all neural audio models run exclusively in `lucca-npu` was specified in early ADR-008.
- **Code Location:** `src/lucca/main.py`, `src/lucca/core/orchestrator.py`
- **User-Visible Impact:** No — voice pipeline functions with sub-second latency as built.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (process topology clean-up).
- **Status:** OPEN

### [ITEM-025] SSRF DNS-Rebinding TOCTOU Hardening
- **Source:** `docs/audit/findings/sbx.md`, Finding `F-SBX-003`
- **Classification:** DESIGN_DEBT
- **Severity:** Medium
- **Feature Area:** sandbox
- **Description:** SSRF validation checks the resolved IP before HTTP request dispatch. A malicious DNS server changing IPs between resolution and fetch could permit DNS rebinding.
- **Code Location:** `src/lucca/sandbox/service.py`
- **User-Visible Impact:** Low in offline desktop setting; security hardening for web tool.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (pinned IP socket fetch).
- **Status:** OPEN

### [ITEM-026] EnergyVAD Hysteresis for Continuous Voice Streaming
- **Source:** `docs/audit/findings/sens.md`, Finding `F-SENS-016`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** senses
- **Description:** EnergyVAD has fixed thresholds without hysteresis or hangover frames, which is sufficient for PTT but causes utterance splitting in continuous open-mic environments.
- **Code Location:** `src/lucca/senses/ring_buffer.py`
- **User-Visible Impact:** None in v1.0 (PTT is the primary mode); relevant for v2 open-mic.
- **Resolution Path:** Tracked in `docs/V2_BACKLOG.md` (Open-mic VAD replacing PTT).
- **Status:** OPEN

### [ITEM-027] Threat Model Matrix Mechanical CI Test ID Tagging
- **Source:** `docs/audit/findings/drift.md`, Finding `F-DRIFT-002`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** test
- **Description:** The threat model matrix describes 24 security controls; individual test cases do not yet embed machine-readable `@threat_control_id` decorators in test reports.
- **Code Location:** `tests/`
- **User-Visible Impact:** Documentation/traceability only.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (security control test traceability).
- **Status:** OPEN

### [ITEM-028] Voice Narration Markdown Sanitization Enhancement
- **Source:** `docs/audit/findings/adjacent_defects_diagnostic_summary.md`, Defect `M6-01..20`
- **Classification:** DESIGN_DEBT
- **Severity:** Low
- **Feature Area:** brain
- **Description:** Occasional markdown formatting (bullet points, asterisks) can slip into raw text before TTS synthesis when the model outputs lists.
- **Code Location:** `src/lucca/brain/chunker.py`
- **User-Visible Impact:** TTS reads punctuation or bullet characters literally.
- **Resolution Path:** Defer to `docs/V2_BACKLOG.md` (streaming voice text regex sanitization filter).
- **Status:** OPEN
