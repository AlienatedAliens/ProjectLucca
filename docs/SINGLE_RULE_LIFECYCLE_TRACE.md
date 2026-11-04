# End-to-End Single-Rule Lifecycle Trace (`induced-read-file-notes-roadmap-md-v1`)

**Model:** `Gemma 4 26B-A4B MoE` (`gemma-4-26B-A4B-it-heretic.Q6_K.gguf` on `llama-server`, `temperature=0.0`, `cache_prompt=False`)  
**Total Live LLM Calls in Trace:** `66` (`50` waking + `10` shadow + `5` held-out head-to-head + `1` live user correction)  
**Run Timestamp (UTC):** `2026-11-04T02:27:07Z`  
**Reproducible Harness:** [`scripts/trace_single_rule_lifecycle.py`](../scripts/trace_single_rule_lifecycle.py)  
**Raw Telemetry Artifact (Untouched Script Output):** [`logs/test_reports/single_rule_lifecycle_trace_wo39.json`](../logs/test_reports/single_rule_lifecycle_trace_wo39.json)  
**Saved Task States:** [`logs/test_reports/saved_task_states_wo39.json`](../logs/test_reports/saved_task_states_wo39.json)  
**Lifecycle State Machine:** [`src/lucca/reasoning/lifecycle.py`](../src/lucca/reasoning/lifecycle.py)

---

## 1. Scope & Honest Limitations

This trace is a controlled, locally reproducible case study designed to make every stage of Project Lucca's procedural rule lifecycle (`PROPOSED -> QUARANTINE -> REPLAY_PASSED -> SHADOW_VERIFIED -> PENDING_APPROVAL -> ACTIVE -> QUARANTINE -> RETIRED`) inspectable end to end on one rule.

**What this trace does and does not claim:**
1. **Deliberately simple rule & small held-out sample:** The traced rule (`induced-read-file-notes-roadmap-md-v1`) is a fixed-argument single-tool rule (`read_file(path="notes/roadmap.md")`), evaluated head-to-head on `3` positive held-out saved states and `2` negative/cross-rule saved states (following `50` waking episodes and `5` shadow clusters). It verifies that the lifecycle mechanics work end to end; it does **not** yet prove that induced rules improve performance on messy, multi-step real-world tasks.
2. **Programmatic approval step:** `RuleLifecycleManager.promote_if_eligible()` transitions a shadow-verified rule to `PENDING_APPROVAL` (`require_human_approval=True`). In this unattended script, the human approval step (`approve_rule(target_rule_id, approver="sean_operator")`) is called programmatically by the harness so the full state machine executes in a single automated run.
3. **Saved `RuleState` evaluation vs. full utterance-to-action NLU:** In Stage 7, the active rule (`0.0976 ms`, `0` LLM tokens) is evaluated on the saved `RuleState` (`intent="file_read"`, `entities={"file": ["notes/roadmap.md"]}`) stored in [`saved_task_states_wo39.json`](../logs/test_reports/saved_task_states_wo39.json), compared against the full `Gemma 4 26B-A4B` planning path (`2,379.86 ms`, `475.7` tokens). In a live turn starting from raw user text, extracting `intent` and `entities` into a `RuleState` still incurs NLU extraction cost unless handled by a fast local classifier/grammar rather than the 26B LLM.
4. **How Stage 8 (User Correction -> Demotion) is wired:** In Stage 8, the natural-language user correction (*"Wait no, stop—I meant notes/todo.md, not notes/roadmap.md! Undo that and read notes/todo.md instead."*) is parsed live by `Gemma 4 26B-A4B` (`2,661.49 ms`) into `{"intent": "user_correction", "user_correction": true, "tool": "read_file", "args": {"path": "notes/todo.md"}}`. The harness then passes that parsed correction into `lifecycle.emit_execution_triple(..., signal="operator_correct")` and `lifecycle.record_shadow(target_rule_id, matched=False)`, which triggers `RuleLifecycleManager`'s 1-strike circuit breaker (`ACTIVE -> QUARANTINE`, `demotion_count = 1`), followed by an explicit `lifecycle.user_retire()` call (`QUARANTINE -> RETIRED`).
5. **Single model scale (`Gemma 4 26B-A4B`):** All LLM latencies and token counts in this report come from `Gemma 4 26B-A4B MoE` (`~2.38 s` mean planning latency). Do not mix these figures with the separate `Gemma 4 12B Dense` baseline (`~462 ms` mean planning latency) reported in [`in_d_live_baseline_wo39.json`](../logs/test_reports/in_d_live_baseline_wo39.json).

---

## 2. Five Local Outcome Signals Evaluated

1. **Tool Execution Completion:** Did the tool execution complete cleanly (`signal="tool_exit_zero"`)?
2. **Task-Specific Verifier Pass:** Did strict `ToolSchema` validation, workspace path confinement, and exact `SHA-256` file-content verification pass?
3. **Cost & Latency:** How many retries, tool calls, LLM tokens (`prompt` + `completion`), and milliseconds were required?
4. **User Correction / Undo / Reject:** Did the user correct, undo, or reject the action shortly afterward (`signal="operator_correct"`), and does a 1-strike circuit breaker immediately demote the rule?
5. **Regression Check:** Did the rule introduce any regression or conflict on previously successful cases (`verify_regression_suite()` + 50-turn historical replay + near-miss negative controls)?

---

## 3. Complete Lifecycle Path of `induced-read-file-notes-roadmap-md-v1`

| Stage | State Transition | What Ran Live on `Gemma 4 26B-A4B` + Local Verifiers | Measured Result |
| :--- | :--- | :--- | :--- |
| **Stage 1: Waking Workload** | `Waking Episodes (N=50)` | `50` live natural-language turns (`4` target `notes/roadmap.md` reads, `4` `calculator` launches, `4` near-miss `notes/todo.md` reads, `38` distractors). Real filesystem execution + `SHA-256` & path-confinement verifier. | `2,338.39 ms` mean LLM latency, `464.4` mean tokens/turn, `0` retries. `4/4` target reads verified (`SHA-256: 08f62653...`); `2/2` path-traversal attempts (`../secret_keys.txt`, `../../../etc/passwd`) blocked (`tool_ok=0`). |
| **Stage 2: Rule Induction & Z3 Gate** | `PROPOSED -> QUARANTINE` | `DreamRetrospective` + `RuleInducer` anti-unification over verified `decisions` rows + E-Graph macro compression (`induce_macros`) + Z3 SMT conflict check (`is_rule_conflict`). | Induced `induced-read-file-notes-roadmap-md-v1` + generalized macro `(defmacro when-file-read-path ...)`. Z3 verified conflict-free in `27.07 ms`. Admitted to `QUARANTINE` (`learned_skills_active = 0`). |
| **Stage 3: Offline Historical Replay** | `QUARANTINE (replay_passed=True)` | `ReplayEngine.replay_candidate(limit=50)` evaluates the candidate MicroScheme AST across all `50` live-recorded SQLite task states before allowing live shadow budget. | `1.72 ms` total replay time: `4/4` target fires, `0/50` runtime/gas errors, `0/46` distractor misfires (including `notes/todo.md`). |
| **Stage 4: Contrastive Shadow** | `QUARANTINE (5/5 clusters)` | `5` unseen requests for `notes/roadmap.md` across `5` distinct 15-minute session clusters (`compute_cluster_id`). Runs `lifecycle.evaluate(mode="shadow")` alongside live `Gemma 4 26B-A4B` inference (`log_contrastive_shadow_pair`). | Shadow eval: `0.4912 ms` mean latency vs. live `26B-A4B` core: `2,416.78 ms` (`476.2` tokens/turn). Plan agreement (`check_plan_and_core_agreement`): **`5/5 (100.0%)`**. |
| **Stage 5 & 6: Regression Check & Promotion** | `PENDING_APPROVAL -> ACTIVE` | `verify_regression_suite()` checks all saved `(RuleState, expected_plan)` snapshots for prior active rules (`induced-launch-app-calculator-v1`, `10` snapshots pre-promotion, `20` post-promotion). Harness triggers `approve_rule(...)`. | `0/10` pre-promotion regressions; `0/20` post-promotion regressions. Promoted to `ACTIVE`. |
| **Stage 7: Active vs. Normal Path** | `ACTIVE (Execution)` | Head-to-head execution on `5` saved task states (`3` unseen positive `notes/roadmap.md` states + `2` negative/prior-rule controls in [`saved_task_states_wo39.json`](../logs/test_reports/saved_task_states_wo39.json)). | Same verified `SHA-256` result (`3/3`), `0.0976 ms` vs `2,379.86 ms` planning latency, `0` vs `475.7` LLM tokens from saved state, `0` regressions/misfires. |
| **Stage 8: User Correction & Rollback** | `ACTIVE -> QUARANTINE -> RETIRED` | Live follow-up turn sent to `26B-A4B`: *"Wait no, stop—I meant notes/todo.md, not notes/roadmap.md! Undo that and read notes/todo.md instead."* | `26B-A4B` parses `user_correction: true` (`2,661.49 ms`), harness emits `ExecutionTriple(verdict="overridden", signal="operator_correct")` (`01M6J63BX6H03P4GNBFMTS7BZ8`) & triggers **1-strike demotion** (`ACTIVE -> QUARANTINE`, `demotion_count=1`), followed by explicit `user_retire() -> RETIRED`. |

---

## 4. Induced Rule & E-Graph Macro

### Canonical MicroScheme Rule (`SHA-256: a4a23ec215bc8239...`)
```scheme
(rule "induced-read-file-notes-roadmap-md-v1"
  :when (and (intent= "file_read") (entity-has? "file" "notes/roadmap.md"))
  :plan (list (tool "read_file" :path "notes/roadmap.md"))
  :priority 5)
```

### Generalized E-Graph Macro (`RuleInducer.induce_macros`)
Across `induced-read-file-notes-roadmap-md-v1` and `induced-read-file-notes-todo-md-v1`, anti-unification extracts the reusable file-read guard macro:
```scheme
(defmacro when-file-read-path (arg_1_0)
  (and (intent= "file_read") (entity-has? "file" arg_1_0)))
```

---

## 5. Stage 7 Head-to-Head Comparison on Saved Task States

### 5.1 Positive Target Saved Task States (`n = 3` Held-Out Phrasings for `notes/roadmap.md`)

| Outcome Signal | Normal LLM Path (`Gemma 4 26B-A4B`) | Active Rule Path (`MicroScheme` AST on Saved `RuleState`) |
| :--- | :--- | :--- |
| **1. Tool Execution Completed (`tool_exit_zero`)** | **`3 / 3` (`100%`)** | **`3 / 3` (`100%`)** |
| **2. Task-Specific Verifier (`ToolSchema` + Path Confinement + `SHA-256`)** | **`3 / 3` (`100%`)** (`08f62653d40f3e25...`) | **`3 / 3` (`100%`)** (`08f62653d40f3e25...`) |
| **3a. Mean Planning Latency** | **`2,379.86 ms`** (`2,399.03`, `2,342.58`, `2,397.96 ms`) | **`0.0976 ms`** (`0.0926`, `0.0934`, `0.1067 ms`; `10/150` gas ticks) |
| **3b. Mean Total Turn Latency (Planning + Disk I/O)** | **`2,380.50 ms`** | **`0.5035 ms`** |
| **3c. Mean LLM Tokens Required (`prompt` + `completion`)** | **`475.7 tokens`** (`422.7` prompt + `53.0` completion) | **`0 tokens`** (deterministic AST evaluation on saved `RuleState`) |
| **3d. Tool Calls & Retries per Turn** | `1` tool call, `0` retries | `1` tool call, `0` retries |
| **4. User Corrections / Undos (`operator_correct`)** | `0 / 3` (`0%`) | `0 / 3` (`0%`) (1-strike circuit breaker verified in Stage 8) |
| **5. Regressions on Previously Successful Cases** | `0 / 20` (`0%`) | **`0 / 20` active regression cases, `0 / 50` replay episodes, `0 / 2` negative controls** |

### 5.2 Negative & Cross-Rule Saved Task States (`n = 2`)

| Case ID | Utterance | Normal LLM Path (`Gemma 4 26B-A4B`) | Active Rule Path (`RuleLifecycleManager`) |
| :--- | :--- | :--- | :--- |
| `SAVED_NEG_01_NEAR_MISS_FILE` | *"Please read notes/todo.md and show me what's in it."* | Calls `read_file(path="notes/todo.md")`, `SHA-256: 1b29044e...` (`2,474.70 ms`, `481` tokens) | `induced-read-file-notes-roadmap-md-v1` **does not misfire** (`target_rule_fired = false`, `0.0560 ms`); yields cleanly to core. |
| `SAVED_NEG_02_PRIOR_ACTIVE_RULE` | *"Hey, could you start calculator for me?"* | Calls `launch_app(app="calculator")` (`2,351.01 ms`, `470` tokens) | `induced-read-file-notes-roadmap-md-v1` **does not misfire**; prior active rule `induced-launch-app-calculator-v1` **fires cleanly** (`0.1090 ms`, `0` regression). |

---

## 6. Reproducing Locally

```powershell
uv run python scripts/trace_single_rule_lifecycle.py
```
This script starts `llama-server` with `Gemma 4 26B-A4B` (`Tier 0`), executes all 66 live turns against a fresh SQLite database and workspace directory, and writes [`logs/test_reports/single_rule_lifecycle_trace_wo39.json`](../logs/test_reports/single_rule_lifecycle_trace_wo39.json) and [`logs/test_reports/saved_task_states_wo39.json`](../logs/test_reports/saved_task_states_wo39.json).
