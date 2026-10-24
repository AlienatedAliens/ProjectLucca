# Project Lucca — Phase 1 Investigation Report & Phase 2 Proposals

**Document Status:** Formal Investigation Report (Read-Only Phase 1 Complete)  
**Repository State:** `master` at commit `2fbf436`  
**Target Hardware:** Intel Core Ultra 9 / Arrow Lake, NVIDIA GeForce RTX 5080 Laptop GPU (16 GB VRAM), 16 GB Host RAM, Windows 11 Host + WSL2 Ubuntu  

---

## 1. Phase 1 Investigation Findings (Q1 – Q19)

| # | Topic | Question Summary | Code Finding & Source of Truth | Exact Citation / Evidence | Confidence |
|---|---|---|---|---|---|
| **Q1** | Router Intents & Entities | What intents does `HeuristicRouter` recognize, how are entities extracted, and where is the mismatch with `ARCHITECTURE.md` §3.2? | `HeuristicRouter` recognizes 7 explicit intents: `launch_app`, `file_read`, `file_write`, `web_fetch`, `memory_query`, `chit_chat`, `clarify`, plus fallback `unknown`. Fast-path rule mapping (`INTENT_TO_RULE`) only includes 4 (`launch_app`, `file_read`, `file_write`, `web_fetch`). Entities are extracted 100% via deterministic regex (`FILE_PATTERN`, `URL_PATTERN`, `QUOTED_PATTERN`, and hardcoded `known_apps`). No NER or LLM is involved. **Mismatch**: `ARCHITECTURE.md §3.2` claims `LAUNCH_APP`, `SYSTEM_CONTROL`, `TIME_QUERY`, `CALCULATE`. None of the latter three exist in code. | `src/lucca/router/heuristic.py:54-184`, `tests/test_router.py:28-112`, `luccadocs/ARCHITECTURE.md:136` | **HIGH** |
| **Q2** | Fast-Path Turn History | On a fast-path (`RULE`) turn, what is appended to LLM history and memory? What does the LLM see next turn? | The user message and rule text (`Say.text`) are appended to `self.history` as `user` and `assistant`. The user message is committed to SQLite memory as a transcript item. **Omission**: Tool execution metadata (tool name, arguments, stdout, exit codes) are **never** appended to history or stored. The LLM only sees the raw user prompt and the canned assistant acknowledgement, leaving it unaware of execution results. | `src/lucca/core/orchestrator.py:650-658, 788-793`, `src/lucca/brain/prompt_builder.py:696-699` | **HIGH** |
| **Q3** | Tool Rounds per Turn | Does the orchestrator support multiple tool rounds per turn? Max rounds? How are results fed back? | **No.** Max rounds = 1. The orchestrator handles tool calls when streamed by the LLM, executes them in the sandbox via `_handle_tool_call()`, and terminates the turn as soon as the LLM stream completes. Tool results are **never** fed back into the context or re-prompted within that turn. | `src/lucca/core/orchestrator.py:864-890, 920-945` | **HIGH** |
| **Q4** | Exposed Tools & Rules | Which tools are exposed to the LLM? Are ACTIVE rules or skills visible to the LLM in any form? | Exactly 4 tools are exposed via `/v1/chat/completions` JSON schemas with `--jinja`: `launch_app`, `read_file`, `write_file`, `query_capabilities`. **ACTIVE rules and skills are completely invisible to the LLM.** The LLM has no prompt, schema, or grammar knowledge of existing MicroScheme skills. | `src/lucca/brain/prompt_builder.py:66-79, 592-662`, `src/lucca/brain/llm_client.py:155-165` | **HIGH** |
| **Q5** | History & Token Accounting | How is conversation history stored, counted, and truncated? What happens at limit? Is `prompt_tokens` logged? | History is stored as `list[dict[str, str]]` in memory. It is hardcoded to take the last 6 messages (`history[-6:]`). There is **zero token counting** for history, and **no summarization** exists. In `llm_client.py:208`, `yield Done(usage=LLMUsage(prompt_tokens=0, completion_tokens=0))`. `TurnTrace` only tracks `tokens_out`. `prompt_tokens` is **NOT logged per turn**. | `src/lucca/brain/prompt_builder.py:696-699`, `src/lucca/brain/llm_client.py:208`, `src/lucca/core/trace.py:67-85` | **HIGH** |
| **Q6** | Memory Quota & Prioritization | Where is the 600 quota defined? Retrieval $k$? How is truncation prioritized? Real example? | The parameter is `max_tokens = 600` in `retrieval.py:37`, setting `char_budget = 2400` chars (`ARCHITECTURE §5.5` claiming "capped at $\le 600$ chars" is a doc error). Retrieval $k = 8$. Prioritization is strictly by Reciprocal Rank Fusion (RRF) score descending (`0.5 / (60 + vec_rank) + 0.5 / (60 + fts_rank)`). Candidates are greedily truncated when `current_len + line_len > char_budget`. Example block: `<memory>\n- [user_stated/TRANSCRIPT 2h ago] User prefers dark mode.\n</memory>`. | `src/lucca/memory/retrieval.py:37-52, 140-149`, `src/lucca/core/orchestrator.py:568-571`, `tests/test_memory_db.py:1041` | **HIGH** |
| **Q7** | llama-server Launch Flags | What are the current launch flags: `--ctx-size`, `--cache-type-k/v`, `--n-gpu-layers`, `--parallel`, `--flash-attn`, `--jinja`, prefix caching? | `--model <path> --n-gpu-layers 99 --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --flash-attn on --host 127.0.0.1 --port 8080 --no-webui --jinja`. Prefix caching is enabled by default in `llama-server` when `--parallel 1` (single slot). | `src/lucca/brain/server_ctl.py:261-288`, `src/lucca/core/config.py:37-39`, background task `task-13841` | **HIGH** |
| **Q8** | Memory Measurements & Log Lines | Show KV cache and compute-buffer lines from load log, and `nvidia-smi` reading with server loaded and idle. | Log excerpt: `srv init: initializing, n_slots = 1, n_ctx_slot = 8192, kv_unified = 'false'`. Model file: `Mistral-Nemo-Instruct-2407-Q5_K_M.gguf` (8.13 GiB). Measured `nvidia-smi` at 2026-09-19 23:01:11: **`8890 MiB / 16303 MiB`** on RTX 5080 Laptop GPU. Desktop idle baseline is ~710 MiB; net server footprint is ~8180 MiB. | `task-13841.log:11`, `nvidia-smi` live execution output | **HIGH** |
| **Q9** | Execution Providers Across Components | Does any other component use CUDA/dGPU (embedder, Kokoro, ASR)? List execution providers and devices. | `EmbedWorker`: OpenVINO on `NPU` (Intel AI Boost) with `CPU` fallback. `KokoroTTS`: ONNX Runtime `CPUExecutionProvider` on host CPU. `ASRWorker`: `faster-whisper` on `CPU` (`int8`, 6 threads). **Zero other components use CUDA or the dGPU.** `llama-server` is the sole consumer of the NVIDIA dGPU. | `src/lucca/senses/embed.py:46-57`, `src/lucca/senses/tts.py:187-190`, `src/lucca/senses/asr.py:43-49` | **HIGH** |
| **Q10** | MANIFEST Pins & Upgrade Procedure | What does `models/MANIFEST.json` pin? Procedure to add NeMo Q6_K and retire old entry? | Pinned models: `ultravox-v0_5-llama-3_1-8b-Q6_K.gguf`, `mmproj-ultravox...`, `kokoro-v1.0.onnx`, `voices-v1.0.bin`, `Mistral-Nemo-Instruct-2407-Q5_K_M.gguf`, `Mistral-Nemo-Instruct-2407-Q4_K_M.gguf`. Procedure: (1) Add target to `scripts/download_llm_models.py`, (2) download file, (3) compute SHA256 via hashlib, (4) update `models/MANIFEST.json`, (5) point `config.py:37` and `persona.toml` to Q6_K, (6) verify with `test_model_manifest_complete`. | `models/MANIFEST.json:1-40`, `scripts/download_llm_models.py:27-46`, `src/lucca/core/config.py:37-40` | **HIGH** |
| **Q11** | MicroScheme Primitives & Plan Type | List full primitive set. How are `tool` and `say` represented in `Plan`? State accessors? Can `:when` read memory? | Primitives: `+`, `-`, `*`, `/`, `=`, `<`, `>`, `<=`, `>=`, `not`, `len`, `str-contains?`, `str-lower`, `min`, `max`, `list`, `say`, `tool`. `Plan` is `Plan(actions=list[ToolCall \| Say])`. State accessors: `intent=`, `entity-has?`, `entity`, `transcript-has?`, `transcript-matches-glob?`, `app-running?`, `hour-between?`, `weekday?`, `last-tool-ok?`, `last-tool=`, `session-turns>=`. **`:when` CANNOT read memory** (zero memory accessors exist in `RuleState` or `prims.py`). | `src/lucca/reasoning/scheme/prims.py:255-325, 393-412`, `src/lucca/core/schemas.py:246-282` | **HIGH** |
| **Q12** | Caps & Syntax Rejections | Where are `define/let/lambda` rejected? Where are caps enforced? What is needed to validate an expanded macro? | `define`, `lambda`, `let`, `set!`, `quote` are rejected in the **parser** (`parser.py:139-147`). Source size ($\le 8192$ bytes) and token limit ($\le 2000$) in `lexer.py:28-34`. Depth ($\le 32$) in `parser.py:88`. Gas limit ($\le 1000$) and wall-clock timeout ($\le 20.0$ ms) in `eval.py:46-54`. Node count ($\le 256$) in `validator.py:82`. Macro validation requires expanding AST/text *prior* to `validate_rule_static()`, followed by standard static checks on the expanded form. | `src/lucca/reasoning/scheme/parser.py:139-147`, `src/lucca/reasoning/scheme/lexer.py:28-34`, `src/lucca/reasoning/scheme/eval.py:46-54`, `src/lucca/reasoning/scheme/validator.py:62-98` | **HIGH** |
| **Q13** | Rule Inducer & Triple Logging | Is rule inducer code present? What produces `PROPOSED` rules? Are triples logged, and is data sufficient? | Rule inducer code is **completely absent**. Rules are only created via `RuleLifecycleManager.register_rule()`. Triples `(intent, tool, args)` are logged to `logs/decisions.jsonl` and SQLite `decisions` table via `router.record_post_turn()`. However, `decisions.jsonl` has only 23 lines and SQLite `decisions` / `decision_labels` have 0 rows. **Data is currently insufficient to induce rules.** | `src/lucca/reasoning/lifecycle.py:114-142`, `src/lucca/router/heuristic.py:236-248`, `logs/decisions.jsonl` | **HIGH** |
| **Q14** | Shadow Audit & `_finalize_turn` | Is 5% counterfactual audit implemented? What does `_finalize_turn` do with shadow evaluation today? | `TICKET-REAS-001` is **Spec-Only / Proposed**; NOT implemented. `Orchestrator._finalize_turn()` only finalizes the latency trace, logs telemetry, and commits user transcript. It does **NOT** run shadow evaluation or compare rule vs. LLM counterfactual decisions. | `luccadocs/tickets/TICKET-REAS-001_counterfactual_shadow_audit.md`, `src/lucca/core/orchestrator.py:621-660` | **HIGH** |
| **Q15** | Sandbox Registry & Network Policy | Which tools exist? Confirm `run_python`, `search_text`, `fetch_url`. Network policy? Type validation? | Tools: `launch_app`, `read_file`, `write_file`, `delete_file`, `list_dir`, `search_text`, `run_python`, `fetch_url`, `query_capabilities`. **`run_python`, `search_text`, and `fetch_url` ALL EXIST IN CODE.** Network policy (`scripts/wsl/lucca-egress.sh`): blocks RFC1918 private subnets, permits HTTPS/HTTP outbound. Tool argument validation is currently loose dictionary extraction without Pydantic input schemas. | `src/lucca/sandbox/service.py:107-124`, `src/lucca/sandbox/rpc.py:240-285`, `src/lucca/sandbox/tools/file_tool.py:255-325`, `scripts/wsl/lucca-egress.sh:1-45` | **HIGH** |
| **Q16** | Long Tasks & Barge-In Cancellation | Does orchestrator support background tasks, delayed announcements, or cancellation of in-flight tool? | **No.** Tool execution is synchronous blocking. There is no background task manager or delayed callback system. While `_abort_turn()` cancels TTS playback and sets `_barge_in_event`, it does **NOT** signal or terminate an executing sandbox tool subprocess. | `src/lucca/core/orchestrator.py:1034-1065`, `src/lucca/sandbox/client.py:65-95` | **HIGH** |
| **Q17** | Fast-Path Say Text & Persona | How is fast-path say text produced (fixed string, persona variants, LLM)? Is persona applied? | Fixed static string defined directly in the rule's MicroScheme code: `(say "Opened Notepad.")`. **NO persona is applied.** Raw string is passed directly to `KokoroTTS.synthesize()`. | `src/lucca/core/orchestrator.py:771-778, 1173-1185`, `src/lucca/reasoning/scheme/prims.py:255-265` | **HIGH** |
| **Q18** | TurnTrace & Decision Records | What does `TurnTrace` record (prompt tokens, tools, rule IDs)? How many `decision_labels` records exist? | `TurnTrace` records timing stages, `tokens_out`, `chunks`, `underruns`, `interrupted`. It does **NOT** record `prompt_tokens`, tool calls, or specific `rule_id`. `decision_labels` table currently contains **0 records**. | `src/lucca/core/trace.py:67-85`, SQLite query on `data/memory.db` | **HIGH** |
| **Q19** | Static Gates & Test Reconciliation | List gates in `test_static_gates.py`. Which change if capabilities change? Reconcile 198 vs 193+11 counts. | Gates: `test_no_any_in_core/brain/reasoning_public_api`, `test_tier2_marker_registered`, `test_model_manifest_complete`, `test_capability_claims_real`, `test_audio_concurrency_contract_exists`, `test_no_fabricated_metrics`. `test_capability_claims_real` will fail if new capabilities are claimed in prompt/manifest before implementation. **Test count reconciliation**: Default unit suite = **200 passed**, Tier 2 (Docker) = **6 passed**, HW (NPU/Audio) = **5 passed** (Total = **211 tests**). Discrepancy with docs (198/193) was due to tests added across recent remediation commits. | `tests/test_static_gates.py:1-240`, `AUDIT_REMEDIATION_LOG.md:14`, `luccadocs/ARCHITECTURE.md:16` | **HIGH** |

---

## 2. Additional Contradictions Between Documentation and Code

Beyond the discrepancies identified in the design brief, the investigation revealed the following drift:

1. **Memory Ingestion Block Cap**:
   - `ARCHITECTURE.md §5.5` and `F-MEM-017` state the retrieved-memory block is "capped at $\le 600$ chars".
   - **Code Reality**: In `src/lucca/memory/retrieval.py:37, 49`, the signature is `format_memory_context(hits, max_tokens=600)` with `char_budget = max_tokens * 4 = 2400` characters. The unit test `test_format_memory_context_budget` explicitly tests and validates this 2400 character ceiling.
2. **Router Intent Set**:
   - `ARCHITECTURE.md §3.2` lists `LAUNCH_APP`, `SYSTEM_CONTROL`, `TIME_QUERY`, `CALCULATE`.
   - **Code Reality**: In `src/lucca/router/heuristic.py:54-184`, the actual intents are `launch_app`, `file_read`, `file_write`, `web_fetch`, `memory_query`, `chit_chat`, `clarify`, and `unknown`.
3. **Sandbox Tool Registry vs. LLM Exposure**:
   - `ARCHITECTURE.md §6.1` lists sandbox tools as `read_file`, `write_file`, `search_files`.
   - **Code Reality**: The sandbox supports 9 tools (`launch_app`, `read_file`, `write_file`, `delete_file`, `list_dir`, `search_text`, `run_python`, `fetch_url`, `query_capabilities`). However, `prompt_builder.py:592-662` only exposes 4 tools to the LLM.
4. **MicroScheme Max Nesting Depth**:
   - Spec 05 asserts a maximum nesting depth of 16.
   - **Code Reality**: `src/lucca/reasoning/scheme/parser.py:88` enforces `MAX_DEPTH = 32`.
5. **Model Strategy Legacy References**:
   - `MODEL_STRATEGY.md` and `DECISIONS.md D-AUD-06` cite `gpt-oss-20b` and a 9.5 GB clamp.
   - **Code Reality**: `gpt-oss-20b` is completely absent from `models/MANIFEST.json`, which pins Mistral NeMo 12B and Ultravox 8B.
6. **Settings Dialog File Location**:
   - `DECISIONS.md D-AUD-18` specifies `ui/settings/`.
   - **Code Reality**: The implementation is located at `src/lucca/ui/settings_dialog.py`.
7. **Fast-Path Latency Baseline**:
   - `ARCHITECTURE.md` claims fast-path E2E is "<150 ms".
   - **Code Reality**: The ASR component alone is budgeted at 180 ms median, and the fast path has never been benchmarked under 150 ms end-to-end with active audio hardware.

---

## 3. Section 6: Questions for the Owner

The following strategic questions require owner alignment before beginning implementation in Phase 3:

1. **Precedence (Skill-as-Tool vs. Router Preemption)**:
   - When an incoming turn matches an ACTIVE skill, should the heuristic router preemptively execute it via fast path (bypassing the LLM entirely), or should the LLM receive the turn with the skill exposed as a callable tool in its tool definitions?
2. **Intent Classification (Reflex vs. Act-Then-Narrate)**:
   - Which specific intents should be pure reflexes (e.g. system volume mute, timer start, simple app launch) with fixed canned responses, versus act-then-narrate (e.g. file read, web fetch, calculations) where the rule executes deterministically and NeMo phrases the conversational reply?
3. **Macro Authorship & Invariant Relaxation**:
   - May the LLM draft reasoning pathways (MicroScheme macros) subject to automated replay and human approval, or must they be exclusively human-authored? Permitting bounded macro expansion relaxes the "no define/lambda/quote" invariant in Spec 05; does the owner approve drafting an amendment to Spec 05 and recording a new decision (`D-REAS-03`)?
4. **Reasoning Pathway Promotion Metrics**:
   - What quantitative acceptance measure should a reasoning pathway achieve before promotion (e.g. $\ge 95\%$ agreement with NeMo across $N \ge 50$ shadow replay cases without regressions)?
5. **Priority Order for Proposals A–K**:
   - Which subset of proposals (A through K) should be scheduled for the immediate next iteration, and which should be explicitly deferred?
6. **Scope of Long-Running Tasks (H)**:
   - Are long-running background tasks with async progress and delayed announcements in scope for Phase 3, or should they be deferred until the core turn loop is unified?
7. **Web Access Policy (`fetch_url`)**:
   - Is `fetch_url` permitted under Lucca's local-first mandate, and should it be strictly restricted to pre-approved whitelist domains, cached locally, or disabled by default?
8. **16K Context & VRAM Fallback Strategy**:
   - If Mistral NeMo Q6_K at 16,384 context exceeds the 12 GB VRAM clamp on the RTX 5080 Laptop GPU, which fallback order does the owner select:
     - Option 1: Lower context size (e.g. 14,336 or 12,288)?
     - Option 2: Retain 16K context but fall back to Q5_K_M quantization?
     - Option 3: Increase the VRAM clamp from 12 GB to 13 GB?
9. **Desktop VRAM Baseline & Concurrent Workloads**:
   - What is the owner's typical idle desktop VRAM usage, and is running high-VRAM applications (such as 3D games or video editing) concurrently with Lucca in scope?

---

## 4. Phase 2 Change Proposals (Proposals A – K)

*Note: No code modifications will occur until the owner explicitly approves specific proposals.*

### Proposal A: Skills Callable from the LLM (System 2 calling System 1)
- **Scope**: Expose ACTIVE MicroScheme skills/rules to the LLM as callable tools via OpenAI function schemas in `prompt_builder.py`. When NeMo calls a skill tool, the orchestrator invokes the MicroScheme engine to execute the pre-compiled plan.
- **Affected Files**:
  - `src/lucca/brain/prompt_builder.py` (generate tool schemas from active rules)
  - `src/lucca/core/orchestrator.py` (dispatch skill tool invocations to rule engine)
  - `src/lucca/reasoning/engine.py` (direct rule execution interface)
- **Invariants Affected**: Strict typing (zero `Any`, `D-AUD-01`), MicroScheme pure-plan invariant (`D-AUD-11`), `test_capability_claims_real`.
- **Decisions to Add/Amend**: Amend `D-REAS-01`; add `D-REAS-04` (Skill-as-Tool Exposure Protocol).
- **Tests to Add**: `tests/test_prompt_builder.py::test_active_skills_rendered_as_tools`, `tests/test_orchestrator.py::test_llm_invokes_skill_tool`.
- **Estimated Risk**: **Medium**. Must ensure tool schema formatting does not exceed token budgets or confuse model routing when multiple similar skills exist.

### Proposal B: Three Tiers of LLM Involvement (Reflex, Act-Then-Narrate, Full Loop)
- **Scope**: Formalize turn execution into three explicit tiers:
  1. *Pure Reflex*: Rule executes action and speaks static template (bypasses LLM, turn logged in context).
  2. *Act-Then-Narrate*: Rule executes action deterministically; action result is fed into NeMo to phrase conversational reply in Lucca's voice.
  3. *Full Loop*: Conversational / open-ended turns with LLM tool calling.
- **Affected Files**:
  - `src/lucca/core/orchestrator.py` (`_run_turn` routing branch)
  - `src/lucca/router/heuristic.py` (tier assignment in `RouteDecision`)
  - `src/lucca/core/schemas.py` (add `ExecutionTier` enum)
- **Invariants Affected**: End-to-end latency contracts (Tier 1 < 150ms, Tier 2 < 800ms), honest telemetry logging.
- **Decisions to Add/Amend**: Add `D-ARCH-05` (Three-Tier Execution Architecture).
- **Tests to Add**: `tests/test_orchestrator.py::test_act_then_narrate_pipeline`, `tests/test_router.py::test_execution_tier_routing`.
- **Estimated Risk**: **Low to Medium**. Requires clean handoff of tool outputs into prompt construction without introducing prompt bloat.

### Proposal C: Fast-Path Turn History Recording
- **Scope**: On fast-path rule turns, record both the user utterance, the executed action/result, and the assistant acknowledgment in `self.history` as a structured turn. Enables seamless multi-turn follow-ups (e.g. "what did you just do?", "undo that").
- **Affected Files**:
  - `src/lucca/core/orchestrator.py` (`_run_turn` fast-path branch)
- **Invariants Affected**: Memory isolation, context window hygiene.
- **Decisions to Add/Amend**: Add `D-ARCH-06` (Fast-Path Context Synchronization).
- **Tests to Add**: `tests/test_orchestrator.py::test_fast_path_turn_recorded_in_history`, `tests/test_orchestrator.py::test_follow_up_after_fast_path`.
- **Estimated Risk**: **Low**. Straightforward orchestrator state update, immediately resolves conversational amnesia.

### Proposal D: Reasoning Pathways as Bounded Macros
- **Scope**: Implement pure, bounded macro expansion for MicroScheme rules. Pure functions from state to structured plan results, returned to working memory. Macro expansion checked against strict caps (max 256 nodes, depth $\le 16$, gas $\le 1000$), zero recursion, and full static validation via `validate_rule_static()`.
- **Affected Files**:
  - `src/lucca/reasoning/scheme/macro.py` [NEW]
  - `src/lucca/reasoning/scheme/parser.py` (hook macro expansion prior to AST validation)
  - `src/lucca/reasoning/scheme/validator.py` (validate expanded form)
- **Invariants Affected**: Spec 05 "no define/lambda" restriction (requires amendment), pure-plan invariant.
- **Decisions to Add/Amend**: Amend Spec 05 / `D-REAS-02`; add `D-REAS-05` (Bounded Reasoning Macros).
- **Tests to Add**: `tests/test_scheme_macro.py`, `tests/test_scheme_security.py::test_macro_recursion_rejected`.
- **Estimated Risk**: **Medium-High**. Requires rigorous proof that macro expansion strictly terminates and cannot bypass gas or depth limits.

### Proposal E: Structured Skill & Pathway Induction Pipeline
- **Scope**: Implement the rule induction lifecycle. For action reflexes: cluster recurring `(intent, tool, args)` triples across $N \ge 5$ distinct sessions to propose rules. For reasoning pathways: LLM drafts pathways from worked solutions, replayed against historical cases, placed in `QUARANTINE`, and gated by human approval (`PENDING_APPROVAL`).
- **Affected Files**:
  - `src/lucca/reasoning/inducer.py` [NEW]
  - `src/lucca/reasoning/lifecycle.py` (induction registration gate)
  - `src/lucca/core/orchestrator.py` (post-turn triple aggregation)
- **Invariants Affected**: Human approval gate for rule promotion (`PENDING_APPROVAL`), quarantine invariant (`D-AUD-12`).
- **Decisions to Add/Amend**: Add `D-REAS-06` (Dual Induction Protocol for Reflexes and Pathways).
- **Tests to Add**: `tests/test_rule_inducer.py`, `tests/test_lifecycle_quarantine_gate.py`.
- **Estimated Risk**: **Medium**. Code can be created and unit tested immediately, but production induction requires collecting more user session data.

### Proposal F: Typed Tool Contracts & Parameterized MicroScheme Accessors
- **Scope**: Eliminate string concatenation in MicroScheme rules to prevent code injection. Implement typed entity accessors (`state-entity-int`, `state-entity-numeric`, `state-entity-str`). Introduce Pydantic validation models for all sandbox RPC requests.
- **Affected Files**:
  - `src/lucca/reasoning/scheme/prims.py` (typed entity accessors)
  - `src/lucca/sandbox/rpc.py` (Pydantic schema validation for RPC calls)
  - `src/lucca/sandbox/service.py` (strict dispatch validation)
- **Invariants Affected**: Zero code injection, container sandboxing (`D-AUD-10`), strict typing (`D-AUD-01`).
- **Decisions to Add/Amend**: Add `D-SEC-04` (Typed Tool Contracts and Safe Accessors).
- **Tests to Add**: `tests/test_scheme_security.py::test_code_injection_impossible`, `tests/test_sandbox_rpc.py::test_invalid_args_rejected`.
- **Estimated Risk**: **Low**. High-value defensive fortification against untrusted input execution.

### Proposal G: Dynamic Memory Quota & Truncation Hierarchy
- **Scope**: Scale memory token budget from 600 tokens (~2400 chars) to 2048 tokens for 16K context. Implement multi-factor truncation ordering: (1) Verified facts / explicit statements, (2) Fused RRF score, (3) Temporal recency.
- **Affected Files**:
  - `src/lucca/memory/retrieval.py` (multi-factor truncation and budget scaling)
  - `src/lucca/core/config.py` (configurable memory token budget)
- **Invariants Affected**: Provenance gate (`D-AUD-07`), untrusted delimiter encapsulation (`<memory>` tags).
- **Decisions to Add/Amend**: Amend `D-MEM-01`; add `D-MEM-03` (Context-Scaled Memory Quotas).
- **Tests to Add**: `tests/test_memory_db.py::test_memory_budget_scaling`, `tests/test_memory_db.py::test_hierarchical_truncation`.
- **Estimated Risk**: **Low**. Improves RAG recall without altering underlying database structures.

### Proposal H: Long-Running Task Infrastructure & Async Cancellation
- **Scope**: Introduce asynchronous task delegation for actions exceeding 800 ms. Provide immediate spoken acknowledgment ("I'll check on that..."), run tool asynchronously, push completion event to turn queue, and propagate barge-in cancellation signals down to sandbox processes.
- **Affected Files**:
  - `src/lucca/core/orchestrator.py` (async task coordinator)
  - `src/lucca/sandbox/client.py` (process cancellation signal)
  - `src/lucca/sandbox/service.py` (SIGTERM propagation to container processes)
- **Invariants Affected**: Audio concurrency contract, container process hygiene (`D-AUD-13`).
- **Decisions to Add/Amend**: Add `D-ARCH-07` (Asynchronous Task Delegation and Signal Propagation).
- **Tests to Add**: `tests/test_orchestrator.py::test_long_task_acknowledgement`, `tests/test_sandbox.py::test_barge_in_kills_tool_process`.
- **Estimated Risk**: **High**. Alters the orchestrator's synchronous turn state machine. Recommended to defer until core proposals are stable.

### Proposal I: Multi-Step Tool Execution Loop (Re-prompting NeMo)
- **Scope**: Expand LLM turn pipeline to support up to $M=3$ tool rounds per turn. When a tool finishes in the sandbox, append tool result to context and re-invoke `llama-server` streaming until NeMo generates final speech or hits round cap.
- **Affected Files**:
  - `src/lucca/core/orchestrator.py` (multi-turn streaming loop)
  - `src/lucca/brain/llm_client.py` (support tool role messages)
  - `src/lucca/brain/prompt_builder.py` (format tool result messages)
- **Invariants Affected**: Turn latency budget (speech must start promptly on final text), token logging.
- **Decisions to Add/Amend**: Add `D-BRAIN-03` (Multi-Turn Tool Re-prompting Loop).
- **Tests to Add**: `tests/test_orchestrator.py::test_multi_round_tool_execution`.
- **Estimated Risk**: **Medium-High**. Adds latency to complex tool turns; requires strict round limits to prevent runaway loops.

### Proposal J: Grounded Narration Provenance Enforcement
- **Scope**: In Tier 2 ("act, then narrate") and multi-step turns, enforce that NeMo's spoken claims derive strictly from the tool execution output block. Persona styling dictates voice and tone, but cannot hallucinate factual entities not present in the tool trace.
- **Affected Files**:
  - `src/lucca/brain/prompt_builder.py` (provenance-grounded narration prompt instructions)
  - `tests/test_grounding.py` [NEW] (hallucination detection test cases)
- **Invariants Affected**: No fabricated claims (`test_no_fabricated_metrics`, `test_capability_claims_real`).
- **Decisions to Add/Amend**: Add `D-BRAIN-04` (Grounded Narration Provenance Contract).
- **Tests to Add**: `tests/test_grounding.py::test_narration_adheres_to_tool_trace`.
- **Estimated Risk**: **Low to Medium**. Prompt design and test suite validation.

### Proposal K: Automated Evaluation & Regression Harness
- **Scope**: Create a deterministic evaluation suite with 50–100 frozen benchmark prompts (derived from `decisions.jsonl` traces, adversarial jailbreaks, memory injection attempts, and tool schemas). Execute at temperature 0 across quant, context, and prompt changes.
- **Affected Files**:
  - `scripts/eval_harness.py` [NEW]
  - `data/eval_benchmarks/` [NEW]
  - `tests/test_eval_harness.py` [NEW]
- **Invariants Affected**: Process discipline (T0/T1 verification).
- **Decisions to Add/Amend**: Add `D-OPS-03` (Automated Model & Prompt Evaluation Harness).
- **Tests to Add**: `tests/test_eval_harness.py::test_eval_harness_runs_cleanly`.
- **Estimated Risk**: **Low**. High-value verification tooling that does not touch production runtime code.

---

## 5. Verification & Compliance Checklist

- [x] **Read-Only First**: Zero production files modified. Working tree clean at commit `2fbf436`.
- [x] **Strict Evidence**: Exact file paths, line numbers, test names, and command outputs cited for Q1–Q19.
- [x] **VRAM & Load Logs Measured**: Actual `nvidia-smi` reading (8,890 MiB) and `llama-server` load log line cited.
- [x] **Invariants Preserved**: Zero `Any` in public APIs, container sandboxing, pinned weight hashes, pure plans.
- [x] **Phase 3 Hold**: Awaiting owner approval on §3 proposals and §6 questions before proceeding.
