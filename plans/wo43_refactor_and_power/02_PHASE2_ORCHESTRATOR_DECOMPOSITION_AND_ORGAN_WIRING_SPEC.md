# WO-43 Phase 2 Specification — `Orchestrator` Decomposition (`5,243` $\to$ `<= 2,200` LOC) & Live Organ Activation

**Phase:** `Phase 2 of 6`
**Prerequisite:** Phase 1 completed and signed off by the Independent Auditor Subagent.
**Target God-Object:** [`src/lucca/core/orchestrator.py`](../../src/lucca/core/orchestrator.py) (`5,243` lines total / `4,813` non-blank lines $\to$ **`<= 2,200` total lines**).
**Commits in Phase 2:** `6` atomic commits (`Sub-steps 2.1` through `2.6`), strictly separating structural extractions from behavioral organ-wiring commits.

---

## 1. Shared-State Ownership Matrix for `Orchestrator` Extractions

To prevent broken state references during extraction, all extracted services receive `orch: Orchestrator` (or a typed `OrchestratorStateProtocol`) and read/mutate state strictly on the single `Orchestrator` instance—**never** caching duplicate copies of per-turn lists:

| State Attribute on `Orchestrator` | Mutated / Read By | Ownership Rule |
| :--- | :--- | :--- |
| `self.history: list[dict[str, str]]` | `SpeechStreamPipeline`, `CodePreflightService`, `TurnPipeline` | Owned by `Orchestrator`; mutated in place via `self._orch.history`. |
| `self.current_turn_receipts: list[object]` | `ToolDispatcher`, `SpeechStreamPipeline`, `DeductionAndPlanningRunner` | Owned by `Orchestrator`; cleared in `reset_turn_state()`, appended by `ToolDispatcher`. |
| `self.pending_spoken_updates: list[str]` | `BeliefService`, `SpeechStreamPipeline` | Owned by `Orchestrator`. |
| `self.current_turn_assistant_reply: str` | `SpeechStreamPipeline`, `CodePreflightService` | Owned by `Orchestrator`. |
| `self._last_transcript_signed: object` | `TurnPipeline`, `MemoryCommitService` | Owned by `Orchestrator`. |
| `self.current_reasoning_context: ReasoningContext | None` | `DeductionAndPlanningRunner` | Owned by `Orchestrator`. |

---

## 2. Sub-Step 2.1 — Prune Dead Delegation Stubs & Leftover Wrappers in `orchestrator.py`

### 2.1 Exact AST Targets (`orchestrator.py`)
Our AST call-graph audit identified `11` methods in `orchestrator.py` that are leftover stubs from `WO-11` (`TurnPipeline`) and `WO-18b` (`SpeechOutputManager`) with **zero callers in `src/lucca/`**:
- `_execute_reflex` (`L3613–3629`, `17` lines)
- `_execute_act_then_narrate` (`L3631–3647`, `17` lines)
- `_build_epistemic_context` (`L3649–3667`, `19` lines)
- `_detect_follow_up_and_gate_tools` (`L3669–3681`, `13` lines)
- `_synthesize_chunk` (`L3788–3789`, `2` lines), `_tts_worker` (`L3791–3793`, `3` lines), `_emit_tts_overflow` (`L819–821`, `3` lines), `_is_cross_reference_command` (`L4408–4409`, `2` lines)

*Check before deleting:* Grep `tests/` for each of these 8 private method names. Any method called directly by an old unit test in `tests/` is either repointed in the test to `orch.turn_pipeline.<method>` / `orch.speech_output.<method>` or kept as a 1-line lambda/alias if required by a legacy test.

---

## 3. Sub-Step 2.2 (Structural) — Extract `SpeechStreamPipeline` (`orchestrator.py:2527-3307`, `781` Lines)

### 3.1 Exact Change Manifest (100% Behavior-Preserving Extraction)
| File | Action |
| :--- | :--- |
| `src/lucca/core/speech_stream_pipeline.py` (new) | Create `SpeechStreamPipeline(orch: Orchestrator)` and move the canonical implementation of `stream_llm_speech` (`L2527–3307`, `781` lines) plus its helper methods `_extract_clause_chunks`, `_run_round2_supervision_repair`, and `_register_receipt_citation_urls` out of `Orchestrator`. |
| `src/lucca/core/orchestrator.py` | Instantiate `self.speech_stream = SpeechStreamPipeline(self)` in `__init__`. Replace `_stream_llm_speech` (`L2527–3307`) with a 3-line delegation wrapper `def _stream_llm_speech(self, *args, **kwargs): return self.speech_stream.stream_llm_speech(*args, **kwargs)` (`# delegate — kept for test/back-compat`). |
| `tests/test_static_gates.py` | Add `test_speech_stream_pipeline_decomposition()` following the exact AST parity pattern of `test_memory_commit_service_decomposition()` (`test_static_gates.py:542-596`): `def stream_llm_speech(` must appear `1` time in `speech_stream_pipeline.py` and `0` times in `orchestrator.py`. |

### 3.2 Verification (Sub-Step 2.2)
```powershell
uv run pytest tests/test_static_gates.py -q
uv run lint-imports
uv run pytest tests/ -q -m "not tier2 and not hw and not soak"
```

---

## 4. Sub-Step 2.3 (Behavioral Organ Activation) — Wire `TracebackDivergenceGuard` (`convergence.py`) into `SpeechStreamPipeline`

### 4.1 Exact Problem
[`src/lucca/core/convergence.py`](../../src/lucca/core/convergence.py) (`286` lines) implements `TracebackDivergenceGuard` (SHA-256 state-cycle detection for periods $1..5$, Jaccard token stagnation $\ge 0.95$, and Shannon error-entropy explosion), but has **zero callers in `src/lucca/`** (only imported inside `mcts.py`, which was also unwired). Meanwhile, `SpeechStreamPipeline.stream_llm_speech` runs up to `M = 4` tool convergence rounds without cycle or stagnation detection.

### 4.2 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `src/lucca/core/speech_stream_pipeline.py` | Instantiate `divergence_guard = TracebackDivergenceGuard(max_recurrence=2, max_steps=12)` at the start of `stream_llm_speech`. On each tool call execution round, feed `(tool_name, canonical_args_json, error_or_status)` into `divergence_guard.record_step(...)`. If `report.diverged` is True (`STATE_CYCLE`, `REPETITIVE_DRIFT`, or `ERROR_ENTROPY_EXPLOSION`), log `"subturn_loop_diverged"`, append a directive to `scratchpad_buffer` instructing immediate final synthesis without further tool retries, and break out of the tool convergence loop. |
| `tests/unit/test_convergence_wiring.py` (new) | Add unit tests verifying that: (a) repeating the same failing tool call twice in `stream_llm_speech` triggers `TracebackDivergenceGuard` and aborts Round 3/4 retries; (b) distinct progressive multi-tool calls (`search_web` $\to$ `fetch_url` $\to$ `note_write`) do **not** trigger false divergence. |

### 4.3 Expected Runtime Differences When Online
- **Immediate Termination of Oscillating/Stuck Tool Loops:** When a local model (`E2B` / `E4B` / `12B`) gets stuck calling the same failing tool with identical arguments (or alternating `read_file(a)` $\leftrightarrow$ `read_file(b)`), Lucca halts the loop after the second repetition instead of burning 4 full LLM rounds (`~6–12 seconds` saved on pathological tool turns).

---

## 5. Sub-Step 2.4 (Structural + Deduplication) — Extract & Table-Drive `ToolDispatcher` (`orchestrator.py:4659-5194` + `4110-4274`, `701` Lines)

### 5.1 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `src/lucca/core/tool_dispatcher.py` (new) | Create `ToolDispatcher(orch: Orchestrator)` and move `_handle_tool_call` (`L4659–5194`, `536` lines), `_handle_memory_commit` (`L4110–4274`, `165` lines), and tool receipt signing helpers out of `orchestrator.py`. Refactor the repetitive `if/elif` receipt-signing and trace-recording boilerplate into a single `_sign_and_record_tool_receipt()` helper (`~180` lines net reduction). |
| `src/lucca/core/orchestrator.py` | Instantiate `self.tool_dispatcher = ToolDispatcher(self)` in `__init__`. Keep 2-line delegates `_handle_tool_call` and `_handle_memory_commit` on `Orchestrator`. |
| `tests/test_static_gates.py` | Add `test_tool_dispatcher_decomposition()` AST parity gate. |

---

## 6. Sub-Step 2.5 (Structural) — Extract `DeductionAndPlanningRunner` (`orchestrator.py:1234-2175`, `942` Lines) & `CodePreflightService` (`orchestrator.py:3366-3608`, `243` Lines)

### 6.1 Exact Change Manifest (100% Behavior-Preserving Extraction)
| File | Action |
| :--- | :--- |
| `src/lucca/core/deduction_runner.py` (new) | Create `DeductionAndPlanningRunner(orch: Orchestrator)` and move all 10 deduction/planning methods (`evaluate_rules_chain`, `finalize_chain`, `_validate_premise`, `_search_memory_for_premise`, `_parse_inference_steps`, `_evaluate_step_corroboration`, `run_deduction_step`, `_format_conditioned_speech`, `_parse_and_validate_plan`, `run_planning_step` = `942` lines) from `orchestrator.py`. Keep thin 2-line delegation methods on `Orchestrator` so all `tests/test_wo20_*.py`, `tests/test_wo21_*.py`, and `tests/test_wo22_*.py` tests pass unchanged. |
| `src/lucca/core/code_preflight_service.py` (new) | Create `CodePreflightService(orch: Orchestrator)` and move `synthesize_code_with_preflight` and `stream_code_synthesis` (`L3366–3608`, `243` lines) out of `orchestrator.py`, keeping thin delegates on `Orchestrator`. |
| `tests/test_static_gates.py` | Add `test_deduction_runner_decomposition()`, `test_code_preflight_service_decomposition()`, and hard LOC ceiling gate `assert len(orch_lines) <= 2200`. |

---

## 7. Sub-Step 2.6 (Behavioral Organ Activation) — Wire `DeductionAndPlanningRunner`, `ConsolidationEngine` (`consolidation.py` + `compression.py` + `scratchpad.py` + `mcts.py` + `abduction.py` + `topology.py`), `WorkingMemory` (`working.py`), and `PipelineTracer` (`pipeline_tracer.py`) Into the Live Runtime

### 7.1 Exact Problem
1. `DeductionAndPlanningRunner` (`942` lines), `WorkingMemory` (`61` lines), and `PipelineTracer` (`261` lines) are never called by `TurnPipeline.run()`.
2. `ConsolidationEngine` (`consolidation.py` `209` lines + `compression.py` `630` lines + `scratchpad.py` `378` lines) and `ASTHoleMCTSEngine` (`mcts.py` `925` lines + `abduction.py` `587` lines + `topology.py` `660` lines) are never called by `Orchestrator.maybe_run_nightly_rollup()`.

### 7.2 Exact Change Manifest
| File | Action |
| :--- | :--- |
| `src/lucca/core/turn_pipeline.py` | 1. Integrate `PipelineTracer.get_instance()`: record `start_flow` at Phase 1 (`tank_1_ingestion`), `transition_stage` at Phase 3 (`tank_2_intent_valve`), Phase 4 (`tank_3_symbolic_centrifuge` / `tank_5_deliberation`), and `finish_flow` at Phase 6 (`tank_9_wal_basin`).<br>2. Integrate `WorkingMemory`: open a task journal entry (`working_memory.open_task(trace.trace_id)`) on multi-step `ACT_THEN_NARRATE` and `FULL_LOOP` turns, recording intermediate step status, and close it (`working_memory.close_task(trace.trace_id, outcome=...)`) in `_finalize_turn`.<br>3. Integrate `DeductionAndPlanningRunner`: when `DifficultyEstimator.should_enable_thinking(user_text, intent)` is True on an analytical/deductive query, invoke `orch.deduction_runner.evaluate_step_corroboration` on extracted inference steps to attach Walton critical-question corroboration metadata to the epistemic context. |
| `src/lucca/reasoning/consolidation.py` & `src/lucca/core/orchestrator.py` | 1. In `ConsolidationEngine`: wire `ASTHoleMCTSEngine` (`mcts.py`, which already imports `BackwardAbductionSolver` from `abduction.py` and `BoundaryTopologyParser` from `topology.py`) as the fallback hole-repair solver when a mined macro candidate has an unresolved parameter hole.<br>2. In `Orchestrator.maybe_run_nightly_rollup()`: after `ReflectionEngine.nightly_rollup()` completes, invoke `self.consolidation_engine.run_consolidation_cycle()` on buffered MicroScheme traces so verified macros are mined, falsified in `ScratchpadFalsifier`, verified in `SMTVerifier`, and admitted to `QUARANTINE` (`0` to `ACTIVE` per `D-REAS-06`). |
| `tests/unit/test_organ_activation_phase2.py` (new) | Add end-to-end tests proving: (a) a live turn through `TurnPipeline.run()` writes a task lifecycle entry in `task_journal` (`WorkingMemory`) and updates `logs/telemetry/live_pipeline_state.json` (`PipelineTracer`); (b) `maybe_run_nightly_rollup()` triggers `ConsolidationEngine.run_consolidation_cycle()` and invokes `ASTHoleMCTSEngine` on partial macro sketches while strictly enforcing `0` auto-promotions to `ACTIVE`. |

### 7.3 Expected Runtime Differences When Online
- **Live Telemetry & Task Journaling:** Every turn now populates `logs/telemetry/live_pipeline_state.json` (Tank 1 through Tank 9 latencies and payloads) and records multi-step task completion/failure in the SQLite `task_journal` table without polluting long-term autobiographical memory.
- **Walton Critical-Question Corroboration on Deep-Thinking Turns:** When the user requests step-by-step deliberation (`should_enable_thinking=True`), Lucca evaluates authority/sign/analogy/consequence/precedent critical questions against signed memories and receipts rather than leaving `DeductionAndPlanningRunner` dormant.
- **Sleep-Phase Skill Mining (`ConsolidationEngine` + `DreamCoderMacroMiner` + `ASTHoleMCTSEngine`):** During `maybe_run_nightly_rollup()`, Lucca mines recurring symbolic rule traces, repairs open AST holes with CPU MCTS + backward abduction, tests them on $\ge 3$ concrete counterexample inputs (`ScratchpadFalsifier`), verifies them with Z3 (`SMTVerifier`), and places passing rules in `QUARANTINE` for operator review.

---

## 8. Phase 2 Independent Subagent Audit Gate (Mandatory STOP Before Phase 3)

Spawn a read-only `research` subagent to verify:
1. `src/lucca/core/orchestrator.py` is **`<= 2,200` total lines**.
2. All 4 extracted services (`speech_stream_pipeline.py`, `tool_dispatcher.py`, `deduction_runner.py`, `code_preflight_service.py`) have AST parity gates in `tests/test_static_gates.py`.
3. `TracebackDivergenceGuard`, `DeductionAndPlanningRunner`, `ConsolidationEngine` (+ `mcts.py`, `abduction.py`, `topology.py`, `compression.py`, `scratchpad.py`), `WorkingMemory`, and `PipelineTracer` are wired into live runtime paths and tested.
4. Full `pytest` suite and `uv run lint-imports` (`7/7` contracts) are green.
