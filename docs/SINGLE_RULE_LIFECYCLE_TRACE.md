# End-to-End Single-Rule Lifecycle Trace (`induced-read-file-notes-roadmap-md-v1`)

**Model:** `Gemma 4 26B-A4B MoE` (`gemma-4-26B-A4B-it-heretic.Q6_K.gguf` on `llama-server`, `temperature=0.0`, `cache_prompt=False`)  
**Total Live LLM Calls in Trace:** `66` (`50` waking + `10` shadow + `5` held-out head-to-head + `1` live user correction)  
**Reproducible Harness:** [`scripts/trace_single_rule_lifecycle.py`](../scripts/trace_single_rule_lifecycle.py)  
**Raw Telemetry Artifact:** [`logs/test_reports/single_rule_lifecycle_trace_wo39.json`](../logs/test_reports/single_rule_lifecycle_trace_wo39.json)  
**Saved Task States:** [`logs/test_reports/saved_task_states_wo39.json`](../logs/test_reports/saved_task_states_wo39.json)  
**Lifecycle State Machine:** [`src/lucca/reasoning/lifecycle.py`](../src/lucca/reasoning/lifecycle.py)

---

## 1. Local Outcome Signals Evaluated

This trace evaluates procedural rule learning end-to-end using five local outcome signals measurable entirely inside Project Lucca (`SQLite` + local filesystem + `RuleLifecycleManager`) without external business-system dependencies:

1. **Tool Execution Completion:** Did the tool execution complete cleanly (`signal="tool_exit_zero"`)?
2. **Task-Specific Verifier Pass:** Did strict `ToolSchema` validation, workspace path confinement, and exact `SHA-256` file-content verification pass?
3. **Cost & Latency:** How many retries, tool calls, LLM tokens (`prompt` + `completion`), and milliseconds were required?
4. **User Correction / Undo / Reject:** Did the user correct, undo, or reject the action shortly afterward (`signal="operator_correct"`), and does a 1-strike circuit breaker immediately demote the rule?
5. **Regression Check:** Did the rule introduce any regression or conflict on previously successful cases (`verify_regression_suite()` + 50-turn historical replay + near-miss negative controls)?

---

## 2. Complete Lifecycle Path of `induced-read-file-notes-roadmap-md-v1`

| Stage | State Transition | What Ran Live on `Gemma 4 26B-A4B` + Local Verifiers | Measured Result |
| :--- | :--- | :--- | :--- |
| **Stage 1: Waking Workload** | `Waking Episodes (N=50)` | `50` live natural-language turns (`4` target `notes/roadmap.md` reads, `4` `calculator` launches, `4` near-miss `notes/todo.md` reads, `38` distractors). Real filesystem execution + `SHA-256` & path-confinement verifier. | `2,220.44 ms` mean LLM latency, `464.4` mean tokens/turn, `0` retries. `4/4` target reads verified (`SHA-256: 08f62653...`); `2/2` path-traversal attempts (`../secret_keys.txt`, `../../../etc/passwd`) blocked (`tool_ok=0`). |
| **Stage 2: Rule Induction & Z3 Gate** | `PROPOSED -> QUARANTINE` | `DreamRetrospective` + `RuleInducer` anti-unification over verified `decisions` rows + E-Graph macro compression (`ConsolidationEngine`) + Z3 SMT conflict check (`is_rule_conflict`). | Induced `induced-read-file-notes-roadmap-md-v1` + generalized macro `(defmacro when-file-read-path ...)`. Z3 verified conflict-free in `29.21 ms`. Admitted to `QUARANTINE` (`learned_skills_active = 0`). |
| **Stage 3: Offline Historical Replay** | `QUARANTINE (replay_passed=True)` | `ReplayEngine.replay_candidate(limit=50)` evaluates the candidate MicroScheme AST across all `50` live-recorded SQLite task states before allowing live shadow budget. | `1.69 ms` total replay time: `4/4` target fires, `0/50` runtime/gas errors, `0/46` distractor misfires (including `notes/todo.md`). |
| **Stage 4: Contrastive Shadow** | `QUARANTINE (5/5 clusters)` | `5` unseen requests for `notes/roadmap.md` across `5` distinct 15-minute session clusters (`compute_cluster_id`). Runs `lifecycle.evaluate(mode="shadow")` alongside live `Gemma 4 26B-A4B` inference (`log_contrastive_shadow_pair`). | Shadow eval: `0.5762 ms` mean latency vs. live `26B-A4B` core: `2,490.91 ms` (`476.2` tokens/turn). Plan agreement (`check_plan_and_core_agreement`): **`5/5 (100.0%)`**. |
| **Stage 5 & 6: Regression Check & Promotion** | `PENDING_APPROVAL -> ACTIVE` | `verify_regression_suite()` checks all saved `(RuleState, expected_plan)` snapshots for prior active rules (`induced-launch-app-calculator-v1`, `10` snapshots pre-promotion, `20` post-promotion). | `0/10` pre-promotion regressions; `0/20` post-promotion regressions. Promoted to `ACTIVE`. |
| **Stage 7: Active vs. Normal Path** | `ACTIVE (Execution)` | Head-to-head execution on `5` saved task states (`3` unseen positive `notes/roadmap.md` states + `2` negative/prior-rule controls in [`saved_task_states_wo39.json`](../logs/test_reports/saved_task_states_wo39.json)). | Same verified `SHA-256` result (`3/3`), `0.1109 ms` vs `2,471.06 ms` planning latency, `0` vs `475.7` LLM tokens from saved state, `0` regressions/misfires. |
| **Stage 8: User Correction & Rollback** | `ACTIVE -> QUARANTINE -> RETIRED` | Live follow-up turn sent to `26B-A4B`: *"Wait no, stop—I meant notes/todo.md, not notes/roadmap.md! Undo that and read notes/todo.md instead."* | `26B-A4B` parses `user_correction: true` (`2,773.36 ms`), emits `ExecutionTriple(verdict="overridden", signal="operator_correct")`, triggers **1-strike demotion** (`ACTIVE -> QUARANTINE`, `demotion_count=1`), followed by explicit `user_retire() -> RETIRED`. |

---

## 3. Induced Rule & E-Graph Macro

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

## 4. Stage 7 Head-to-Head Comparison on Saved Task States

### 4.1 Positive Target Saved Task States (`n = 3` Held-Out Phrasings for `notes/roadmap.md`)

| Outcome Signal | Normal LLM Path (`Gemma 4 26B-A4B`) | Active Rule Path (`MicroScheme` AST on Saved `RuleState`) |
| :--- | :--- | :--- |
| **1. Tool Execution Completed (`tool_exit_zero`)** | **`3 / 3` (`100%`)** | **`3 / 3` (`100%`)** |
| **2. Task-Specific Verifier (`ToolSchema` + Path Confinement + `SHA-256`)** | **`3 / 3` (`100%`)** (`08f62653d40f3e25...`) | **`3 / 3` (`100%`)** (`08f62653d40f3e25...`) |
| **3a. Mean Planning Latency** | **`2,471.06 ms`** (`2,589.99`, `2,407.36`, `2,415.83 ms`) | **`0.1109 ms`** (`0.0979`, `0.1304`, `0.1043 ms`; `10/150` gas ticks) |
| **3b. Mean Total Turn Latency (Planning + Disk I/O)** | **`2,471.76 ms`** | **`0.4956 ms`** |
| **3c. Mean LLM Tokens Required (`prompt` + `completion`)** | **`475.7 tokens`** (`422.7` prompt + `53.0` completion) | **`0 tokens`** (deterministic AST evaluation on saved `RuleState`) |
| **3d. Tool Calls & Retries per Turn** | `1` tool call, `0` retries | `1` tool call, `0` retries |
| **4. User Corrections / Undos (`operator_correct`)** | `0 / 3` (`0%`) | `0 / 3` (`0%`) (1-strike circuit breaker verified in Stage 8) |
| **5. Regressions on Previously Successful Cases** | `0 / 20` (`0%`) | **`0 / 20` active regression cases, `0 / 50` replay episodes, `0 / 2` negative controls** |

### 4.2 Negative & Cross-Rule Saved Task States (`n = 2`)

| Case ID | Utterance | Normal LLM Path (`Gemma 4 26B-A4B`) | Active Rule Path (`RuleLifecycleManager`) |
| :--- | :--- | :--- | :--- |
| `SAVED_NEG_01_NEAR_MISS_FILE` | *"Please read notes/todo.md and show me what's in it."* | Calls `read_file(path="notes/todo.md")`, `SHA-256: 1b29044e...` (`2,562.89 ms`, `481` tokens) | `induced-read-file-notes-roadmap-md-v1` **does not misfire** (`target_rule_fired = false`, `0.0723 ms`); yields cleanly to core. |
| `SAVED_NEG_02_PRIOR_ACTIVE_RULE` | *"Hey, could you start calculator for me?"* | Calls `launch_app(app="calculator")` (`2,300.69 ms`, `470` tokens) | `induced-read-file-notes-roadmap-md-v1` **does not misfire**; prior active rule `induced-launch-app-calculator-v1` **fires cleanly** (`0.0921 ms`, `0` regression). |

---

## 5. Reproducing Locally

```powershell
uv run python scripts/trace_single_rule_lifecycle.py
```
This script starts `llama-server` with `Gemma 4 26B-A4B` (`Tier 0`), executes all 66 live turns against a fresh SQLite database and workspace directory, and writes [`logs/test_reports/single_rule_lifecycle_trace_wo39.json`](../logs/test_reports/single_rule_lifecycle_trace_wo39.json) and [`logs/test_reports/saved_task_states_wo39.json`](../logs/test_reports/saved_task_states_wo39.json).
