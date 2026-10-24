# Project Lucca — General Reasoning Improvement Plan, Live Benchmark Review & Technical Audit
**Generated:** 2026-10-13 | **Status:** Implemented, Audited & Live-Validated on RTX 5080 | **Version:** `v1.38.0-dev`

---

## 1. Executive Summary: Complete Live Benchmark Matrix (`v1.37.0` $\rightarrow$ `v1.38.0-dev`)

All architectural upgrades (**P0–P6**) and the five post-audit runtime/security patches were implemented, verified against **all 55 unit, security, and static-gate tests (`55 passed in 9.86s`)**, and evaluated back-to-back across **10 live benchmark suites ($N=248$ total problems)** on the physical workstation (**NVIDIA GeForce RTX 5080 Laptop GPU, 16 GB GDDR7**, running `gemma-4-12b-heretic-Q6_K.gguf` via `llama-server` and `lucca-file-sandbox` in WSL2 Ubuntu):

| # | Benchmark Suite | $N$ | Bare / Direct (12B) | Extended Thinking (12B) | v1.37.0 Compound (12B) | **v1.38.0-dev Compound (12B)** | Net Lift (v1.38 vs. Bare / v1.37) | Live Report Artifact on Disk |
|---|---|---|---|---|---|---|---|---|
| **1** | **MuSR Object Placements Diagnostic** (`ContainerWorld`) | 10 | 30.0% (3/10) | 40.0% (4/10) | 60.0% (6/10) | **90.0% (9/10)** | **+60.0 pp** vs. Direct / **+30.0 pp** vs. v1.37 | [`musr_op_diagnostic_12B_V138_1791827372.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/musr_op_diagnostic_12B_V138_1791827372.json) |
| **2** | **MuSR Full 3-Domain Compound Suite** | 30 | 53.3% (16/30) | 60.0% (18/30) | 56.7% (17/30) | **83.3% (25/30)** | **+30.0 pp** vs. Direct / **+26.6 pp** vs. v1.37 | [`musr_compound_benchmark_12B_V138_1791834503.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/musr_compound_benchmark_12B_V138_1791834503.json) |
| 2a | — *MuSR: Murder Mystery* (`Structured_MMO_Thinking`) | 10 | 70.0% (7/10) | 80.0% (8/10) | 70.0% (7/10) | **80.0% (8/10)** | **+10.0 pp** vs. Direct & v1.37 | [`musr_compound_benchmark_12B_V138_1791834503.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/musr_compound_benchmark_12B_V138_1791834503.json) |
| 2b | — *MuSR: Team Allocation* (`Schema_Python_Optimizer`) | 10 | 50.0% (5/10) | 60.0% (6/10) | 40.0% (4/10) | **90.0% (9/10)** | **+40.0 pp** vs. Direct / **+50.0 pp** vs. v1.37 | [`musr_compound_benchmark_12B_V138_1791834503.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/musr_compound_benchmark_12B_V138_1791834503.json) |
| 2c | — *MuSR: Object Placements* (`ContainerWorld_v138`) | 10 | 40.0% (4/10) | 40.0% (4/10) | 60.0% (6/10) | **80.0% (8/10)** | **+40.0 pp** vs. Direct / **+20.0 pp** vs. v1.37 | [`musr_compound_benchmark_12B_V138_1791834503.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/musr_compound_benchmark_12B_V138_1791834503.json) |
| **3** | **LongMemEval Full Pipeline (`top_k=12`, Session-Grouped)** | 30 | 33.3% (10/30) | — | 70.0% (21/30) | **83.3% (25/30)** | **+50.0 pp** vs. Bare ($p=0.0001$) / **+13.3 pp** vs. v1.37 | [`longmemeval_pipeline_12B_V138_1791827862.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/longmemeval_pipeline_12B_V138_1791827862.json) |
| 3a | — *LongMemEval: Knowledge-Update* | 10 | 60.0% (6/10) | — | 90.0% (9/10) | **100.0% (10/10)** | **+40.0 pp** vs. Bare / **+10.0 pp** vs. v1.37 | [`longmemeval_pipeline_12B_V138_1791827862.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/longmemeval_pipeline_12B_V138_1791827862.json) |
| 3b | — *LongMemEval: Multi-Session* | 10 | 20.0% (2/10) | — | 70.0% (7/10) | **80.0% (8/10)** | **+60.0 pp** vs. Bare / **+10.0 pp** vs. v1.37 | [`longmemeval_pipeline_12B_V138_1791827862.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/longmemeval_pipeline_12B_V138_1791827862.json) |
| 3c | — *LongMemEval: Temporal-Reasoning* | 10 | 20.0% (2/10) | — | 50.0% (5/10) | **70.0% (7/10)** | **+50.0 pp** vs. Bare / **+20.0 pp** vs. v1.37 | [`longmemeval_pipeline_12B_V138_1791827862.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/longmemeval_pipeline_12B_V138_1791827862.json) |
| **4** | **AIME 2024 Expanded SymPy Diagnostic** | 10 | — | 10.0% (1/10) | 40.0% (2/5) | **80.0% (8/10)** | **+70.0 pp** vs. Extended Thinking / **+40.0 pp** vs. v1.37 | [`aime_sympy_diagnostic_12B_V138_1791838851.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/aime_sympy_diagnostic_12B_V138_1791838851.json) |
| **5** | **Checked Formalization & Hybrid Suite** (`SYMBOLIC`+`BRUTE_FORCE`) | 10 | 40.0% (4/10) | — | N/A (New) | **100.0% (10/10)** | **+60.0 pp** vs. Bare (`8/10` Dual-Agreed, `2/10` Repaired) | [`checked_formalization_12B_V138_1791836638.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/checked_formalization_12B_V138_1791836638.json) |
| **6** | **Multi-Lobe Shared Python Workspace** (`D-REAS-10`) | 15 | 73.3% (11/15) | — | N/A (New) | **93.3% (14/15)** | **+20.0 pp** overall (**+60.0 pp** on `ContainerWorld+SymPy`) | [`multi_lobe_composition_12B_V138_1791836880.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/multi_lobe_composition_12B_V138_1791836880.json) |
| **7** | **ZebraLogic Difficulty Sweep ($2\times 2$ to $5\times 5$)** | 8 | 75.0% (6/8) | 87.5% (7/8) | 75.0% (6/8) | **87.5% (7/8)** (`5x5`: **100%**) | **+100.0 pp** on Tier $5\times 5$ ($0/2 \rightarrow 2/2$ vs. v1.37) | [`zebra_logic_sweep_1791831114.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/zebra_logic_sweep_1791831114.json) |
| **8** | **BFCL v3 Function Calling & Irrelevance** | 50 | — | — | 78.0% (39/50) | **92.0% (46/50)** | **+14.0 pp** (`exec_simple`: **100%**, `irrelevance`: **84%**) | [`bfcl_v3_benchmark_12B_V138_1791828599.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/bfcl_v3_benchmark_12B_V138_1791828599.json) |
| **9** | **CRUXEval-Input Counterfactual Code Execution** | 50 | 76.0% (38/50) | — | 90.0% (45/50) | **90.0% (45/50)** | **+14.0 pp** vs. Direct ($0:7$ discordant, $p=0.0156$) | [`cruxeval_input_dev_1791828687429.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/cruxeval_input_dev_1791828687429.json) |
| **10** | **OOD & Live BIPIA/InjecAgent Security Benchmark** | 30 | — | — | 100% (14/14 in-dist) | **100.0% (25/25 blocked, 0/5 FPR)** | **15/15** OOD Evasions + **10/10** Live 12B Injections blocked | [`ood_adversarial_security_12B_V138_1791836391.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/ood_adversarial_security_12B_V138_1791836391.json) |
| **11** | **GPQA Diamond Stratified Parametric Baseline** | 30 | 10.0% (3/30) | **30.0% (9/30)** | 30.0% (3/10) | **30.0% (9/30)** | **+20.0 pp** Thinking over Direct (`Physics`: 38.5%, `Chem`: 28.6%) | [`gpqa_diamond_1791835888.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/gpqa_diamond_1791835888.json) |

---

## 2. Root-Cause Diagnoses & Implemented Architectural Fixes (`v1.38.0-dev`)

### ✅ P0 — Multi-Session Chronological Memory Grouping (`D-MEM-04`)
- **Files:** [`src/lucca/memory/retrieval.py`](file:///C:/Projects/ProjectLucca/src/lucca/memory/retrieval.py), [`scripts/run_longmemeval_pipeline_benchmark.py`](file:///C:/Projects/ProjectLucca/scripts/run_longmemeval_pipeline_benchmark.py)
- **Root Cause Found:**
  1. [`format_memory_context()`](file:///C:/Projects/ProjectLucca/src/lucca/memory/retrieval.py#L446-L520) previously rendered retrieved hits as a flat RRF score-ranked list with `max_items=8`, stripping session boundaries and chronological ordering.
  2. `RetrievalQuery(query_text=q_text, limit=top_k)` in the benchmark passed `limit=` instead of `k=`, which Pydantic v2 silently ignored, forcing `k=8`.
  3. `evaluate_memory_answer()` crashed with `AttributeError` when `ground_truth` was an integer (`4` on item `d23cf73b`) and marked valid abstentions (`"I do not have enough information"`) as false on `_abs` items.
- **Fix & Live Result:** Added session-grouped chronological rendering (`[Session N — {age}]` headers sorted oldest-first by session timestamp, grouping by `session_id`, `source_turn_id` prefix, or 4-hour `created_at` buckets) and set `k=12`. Accuracy rose from **70.0% $\rightarrow$ 83.3%** overall (**100.0% Knowledge-Update, 80.0% Multi-Session, 70.0% Temporal-Reasoning**, **96.7% Recall@12** at **10.9 ms** retrieval latency).

### ✅ P1 — `ContainerWorld` Initial-Belief Retention, Flexible Signatures & 3-Domain MuSR Upgrade
- **Files:** [`src/lucca/sandbox/container_world.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/container_world.py), [`src/lucca/sandbox/rpc.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/rpc.py), [`scripts/run_musr_object_placements_diagnostic.py`](file:///C:/Projects/ProjectLucca/scripts/run_musr_object_placements_diagnostic.py), [`scripts/run_musr_compound_benchmark.py`](file:///C:/Projects/ProjectLucca/scripts/run_musr_compound_benchmark.py)
- **Root Cause Found:**
  1. `OP_02`, `OP_06`, and `OP_08` failed on every tier in v1.37 because all three are **initial-belief retention** stories where the queried agent knows Paragraph 1's starting location (`Steve's desk`, `storage box`, `studio`) and never observes subsequent moves. Because `tracker.beliefs[agent]` was empty, `ContainerWorld.query()` fell back to `self.world[item]` (the **final** physical location—the exact opposite of Theory-of-Mind false belief).
  2. In MuSR Team Allocation, v1.37 used an unconstrained free-form Python prompt where the 12B model hallucinated arbitrary scoring rules and underperformed Direct LLM (`40.0%` vs. `50.0%`).
- **Fix & Live Result:**
  - Added `self.initial_world` tracking and flexible `.place()`, `.move()`, `.reset()`, and `.simulate()` signatures to [`ContainerWorld`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/container_world.py) and `_CONTAINER_WORLD_PRELUDE` in [`src/lucca/sandbox/rpc.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/rpc.py).
  - Replaced free-form Team Allocation synthesis with a **2-Stage Schema-Constrained `itertools.permutations` Optimizer** (`Schema_Python_Optimizer`) and upgraded Murder Mystery to **Structured Means-Motive-Opportunity (MMO) Elimination**.
  - On the dedicated Object Placements diagnostic ($N=10$), accuracy jumped from **60.0% $\rightarrow$ 90.0%**. On the full 3-domain MuSR benchmark ($N=30$), Compound accuracy jumped from **56.7% $\rightarrow$ 83.3%** (`Murder Mystery`: **80.0%**, `Team Allocation`: **90.0%**, `Object Placements`: **80.0%**).

### ✅ P2 & P5 — CEGIS Checked Formalization, Last-Match Extraction & Empty-Stdout Guard
- **Files:** [`src/lucca/reasoning/cegis_python.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/cegis_python.py), [`src/lucca/sandbox/ast_sanitizer.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/ast_sanitizer.py)
- **Root Cause Found (During Live Audit):**
  1. `re.search(output_pattern, stdout_val)` matched the **first** integer in stdout (so `"The remainder for 7^2026 is 49"` extracted `"7"` instead of `"49"`).
  2. `synthesize_and_repair()` accepted `ok_exec=True` even when `stdout_val` was completely empty (`""`) or printed `<built-in function print>` (due to `max_tokens=512` truncating long scripts right at `print`), prematurely halting at Turn 1 instead of triggering a repair turn!
  3. `ast_sanitizer.py` auto-imported `math`, `sympy`, `z3`, and `itertools`, but did not auto-import `from fractions import Fraction` (which caused `NameError` on AIME 2024 Problem 4).
- **Fix & Live Result:**
  - Added [`_extract_output_pattern()`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/cegis_python.py#L45-L60) (last regex match on the final non-empty line).
  - Increased default `max_tokens` from `512` to `1024` across all CEGIS synthesis loops, added `EmptyOutputError` / `OutputFormatError` validation when `test_harness is None`, and added `from fractions import Fraction` auto-injection in [`ast_sanitizer.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/ast_sanitizer.py#L77-L80).
  - **Impact on AIME 2024 ($N=10$):** Compound SymPy accuracy surged from **0/10–1/10 (10.0%) Bare Extended Thinking** $\rightarrow$ **5/10 (50.0%) pre-audit** $\rightarrow$ **8/10 (80.0%) post-audit** (solving Problems 1, 2, 3, 4, 6, 7, 8, and 10!).
  - **Impact on Checked Formalization ($N=10$):** Achieved **10/10 (100.0%)** vs. **4/10 (40.0%)** Bare Mental LLM, with `8/10` immediately verified by `SYMBOLIC` + `BRUTE_FORCE` dual agreement.

### ✅ P3, P4 & P6 — Shared Python Workspace (`D-REAS-10`) & Compact Z3 Dictionary Encoding
- **Files:** [`src/lucca/router/heuristic.py`](file:///C:/Projects/ProjectLucca/src/lucca/router/heuristic.py), [`src/lucca/sandbox/rpc.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/rpc.py), [`scripts/run_zebra_logic_sweep.py`](file:///C:/Projects/ProjectLucca/scripts/run_zebra_logic_sweep.py), [`scripts/run_multi_lobe_composition_benchmark.py`](file:///C:/Projects/ProjectLucca/scripts/run_multi_lobe_composition_benchmark.py)
- **What Changed & Live Result:**
  - Fixed `get_config().llm.model.lower()` in [`HeuristicRouter`](file:///C:/Projects/ProjectLucca/src/lucca/router/heuristic.py) and expanded `CONTAINER_WORLD_PATTERN` so multi-lobe prompts expose all required libraries (`["container_world", "sympy", "z3"]`) in a single shared Docker execution workspace.
  - On the **Multi-Lobe Shared Workspace Benchmark ($N=15$)**, accuracy rose from **73.3% (11/15) Bare** $\rightarrow$ **80.0% (12/15) pre-audit** $\rightarrow$ **93.3% (14/15) post-audit** (`ContainerWorld+Z3`: **100%**, `Z3+SymPy`: **100%**, `ContainerWorld+SymPy`: **80%**).
  - On **ZebraLogic ($N=8$)**, replacing verbose per-variable Z3 declarations with a compact dictionary comprehension (`h = {v: z3.Int(v) ...}`) and `max_tokens=2048` lifted Tier $5\times 5$ ($207,360,000$ states) from **0.0% (0/2) in v1.37 $\rightarrow$ 100.0% (2/2) in v1.38**.

### ✅ OOD & Canonical Adversarial Security Hardening (`N=30`)
- **Files:** [`src/lucca/sandbox/file_tool.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/file_tool.py), [`src/lucca/sandbox/policy.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/policy.py), [`scripts/run_ood_adversarial_security_benchmark.py`](file:///C:/Projects/ProjectLucca/scripts/run_ood_adversarial_security_benchmark.py)
- **What Changed & Live Result:**
  - [`validate_rel_path()`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/file_tool.py) now rejects Unicode NFKC homoglyphs (`\uff0e\uff0e`), double percent-encoding (`%252e%252e`), NTFS Alternate Data Streams (`::$DATA`), UNC SMB paths, and CRLF control characters.
  - [`SequenceGuard`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/policy.py) now registers lowercase, Base64, and Hex encodings of sensitive tokens, strips zero-width characters (`\u200b`–`\u200d`, `\ufeff`), URL-unquotes outbound arguments, and blocks `private_read_tools -> network_tools` and `network_tools -> side_effect_tools`.
  - Achieved **25/25 (100.0%) attack block rate** (`15/15` deterministic OOD evasion vectors + `10/10` live 12B BIPIA/Greshake/InjecAgent/TensorTrust/HackAPrompt indirect injections) with **0/5 (0.0%) false positives** on hard-negative benign workflows.

---

## 3. Technical Audit of Remaining Bottlenecks & `v1.39` Improvement Roadmap

An item-by-item audit of every remaining failure across all 248 evaluated tasks reveals **five specific, high-leverage bottlenecks** that define the next engineering horizon (`v1.39`):

### 1. AIME 2024 Geometry/Combinatorics Token Budget & Multi-Line String Truncation (AIME Problems 5 & 9; `ML_CW_SYMPY_03`)
- **Observed Failure Mode:**
  - In [`aime_sympy_diagnostic_12B_V138_1791838851.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/aime_sympy_diagnostic_12B_V138_1791838851.json), only **2 out of 10** problems failed: Problem 5 (convex equilateral hexagon with parallel opposite sides, target `80`) and Problem 9 ($5\times 5$ grid with 25 white and 25 black chips, target `902`). In both cases, the 12B model wrote a long exploratory docstring/comment block inside the Python code fence and hit the 1,024-token ceiling before emitting `print(ans)` (`tokenize_normalization_fallback error="('EOF in multi-line string', ...)"` / `EmptyOutputError`).
  - On `ML_CW_SYMPY_03` (`container_world+sympy`), the model printed `0` because it called `poly.coeff(x, 5)` on an unexpanded `(2*x + 3)**14` expression instead of `sympy.expand((2*x + 3)**14).coeff(x, 5)`.
- **Recommended `v1.39` Fix:**
  1. Enforce a **"No-Docstring / Code-Only"** system constraint in `PythonCEGISEngine` (`"Do NOT write multi-line docstrings or narrative comments inside the Python block; write executable statements only"`) and raise `max_tokens` to `1536` on AIME-class geometry/combinatorics repairs.
  2. Add a lightweight AST lint rule in `ast_sanitizer.py` that warns or auto-expands `.coeff(` calls on unexpanded `Pow` nodes in SymPy scripts.

### 2. LongMemEval Temporal Anchor & Duration Arithmetic (`Temporal-Reasoning`: 70.0% vs. `Knowledge-Update`: 100.0%)
- **Observed Failure Mode:**
  - While `Knowledge-Update` reached **100.0% (10/10)** and `Multi-Session` reached **80.0% (8/10)**, `Temporal-Reasoning` is at **70.0% (7/10)**. The 3 missed items require computing exact day/week/month deltas between a relative reference (`"two weeks before the conference"`, `"last Tuesday"`) inside an older session and the query's current anchor date.
- **Recommended `v1.39` Fix:**
  - Add **Ingestion-Time Relative Date Grounding (`datetime` Anchor Resolution)** in `src/lucca/memory/` and expose `datetime` / `dateutil` to a lightweight temporal calculator when `TEMPORAL_REASONING` intent is detected.

### 3. BFCL v3 Irrelevance False-Triggering on Near-Miss Parameter Schemas (`irrelevance`: 84.0% vs. `exec_simple`: 100.0%)
- **Observed Failure Mode:**
  - `exec_simple` achieved **100.0% (25/25)** after the v1.38 prompt calibration, while `irrelevance` achieved **84.0% (21/25)** (up from 68.0% in v1.37). The 4 remaining false positives occur when the user asks for a closely related quantity (e.g., asking for a derivative or unit conversion when the tool only computes a definite integral or raw lookup) and the 12B model coerces the arguments to fit the available tool.
- **Recommended `v1.39` Fix:**
  - Add a **Post-Generation Tool-Relevance Verification Check** (or a `<tool_fit_check>` rubric field) that verifies every required semantic post-condition of the user's question is explicitly provided by the tool's docstring before emitting a tool call.

### 4. MuSR Murder Mystery & Object Placements Residual Single-Item Misses (80.0%–90.0%)
- **Observed Failure Mode:**
  - In `musr_op_diagnostic` (90.0%, 9/10) and `musr_compound_benchmark` (83.3%, 25/30), the single missed Object Placements story involves **implicit collective presence** (`"everyone else was in the room"` / `"they walked back together"`), where the LLM event extractor forgets to list all unmentioned co-present agents in `present=[...]`.
- **Recommended `v1.39` Fix:**
  - Add `world.set_room_occupants(room, agents)` to [`ContainerWorld`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/container_world.py) so co-presence is tracked automatically by room location rather than requiring the LLM to manually enumerate the `present` list on every `.move()` call.

### 5. GPQA Diamond Parametric Knowledge Boundary (30.0% Extended Thinking vs. 10.0% Direct)
- **Observed Failure Mode:**
  - On `GPQA Diamond` ($N=30$), Extended Thinking triples the Direct score (**10.0% $\rightarrow$ 30.0%**, with **38.5% in Physics** and **28.6% in Chemistry**), but graduate-level **Biology (0/2)** and specialized organic/quantum recall remain bounded by the 12B Q6_K model's parametric weights when no external reference corpus is attached.
- **Recommended `v1.39` Fix:**
  - Connect the local `HybridRetriever` (`sqlite-vec` + FTS5) to an offline **STEM Reference Pack** (constants, standard reaction mechanisms, and physical formulas) + SymPy dimensional-analysis verification for Physics/Chemistry questions.
