# Technical Report TR-04: A Gated Lifecycle for Agent-Authored Rules
## Z3-Checked Admission, Quarantine-Only Induction, Shadow Evaluation, Human Promotion, and Single-Strike Demotion (`ADR-007`, `D-REAS-05`, `D-REAS-06`)

```yaml
doc_status: canonical
as_of: 2026-11-03
release_baseline: v1.47.0 (WO-39)
submission_status: technical_report (design note; no induction-quality evaluation exists yet)
related_adrs: [ADR-007, D-REAS-05, D-REAS-06, D-SEC-04, D-COG-01]
verification: artifact-sourced (V1_RELEASE_AUDIT.md, tests/test_l3_lifecycle_proof.py & in_d_latest.json)
```

**Authors:** Project Lucca Program Synthesis, Formal Verification & Cognitive Architecture Group
**Date:** November 3, 2026 (`v1.47.0` / `WO-39` Baseline)
**Hardware Platform:** Intel Core Ultra 9 275HX (24 cores, Host CPU LISP + Microsoft Z3 `libz3.dll`) + Intel AI Boost NPU (`OpenVINO`) + SQLite WAL (`execution_triples` & `learning_events`)

**Contribution type and retitling note.** This report describes the *safety lifecycle* through which an agent-proposed rule must pass before it can act, the mechanical proof that the lifecycle works end-to-end, and the **Post-WO-39 Live 52-Turn Organic Rule-Induction Baseline (`IN-D`)** (`logs/test_reports/in_d_live_baseline_wo39.json`, `logs/test_reports/personhood/in_d_latest.json`). On structured tool-call workflows, `RuleInducer` + `Z3` + `Dream-RSI` achieves **4/4 (100%) Z3-verified quarantine induction**, **4/4 50-turn replay pass**, **8/8 (100%) held-out positive recall**, and **0/8 (0%) false-trigger rate** (`IN-D = 4 quarantined, 0 active`). Conversely, on unconstrained S-expression math synthesis, pure-Python first-order anti-unification (`egraph.py` + `compression.py`) achieves only a **1.169× raw AST compression ratio (`83 -> 71` nodes)** and **0/2 quarantined S-expression macros** due to outer-shape distractor collisions and syntactic variance (`(* 0.5 8)` vs `6`) + Python falsification timeouts (`1,233 ms > 500 ms`). This establishes the exact empirical baseline for `ProjectElle` (`egglog` + `stitch-core`).

---

## 1. Abstract & Motivation

In persistent companion AI systems, recurring multi-step workflows (such as unit conversions, system diagnostics, workspace note briefings, or repaired mathematical sub-routines) should not repeatedly invoke multi-billion-parameter neural deliberation from scratch (`~462 ms` LLM generation latency). Conversely, allowing an autonomous agent to synthesize and execute its own operational rules without formal boundaries introduces severe safety hazards: self-induced scripts can introduce path traversal vulnerabilities, infinite recursion, or silent semantic misfires (`over-triggering` on benign user turns).

This paper presents the design and verification of **Project Lucca's Symbolic Skill Studio & Two-Cadence Inner Life (`v1.45.0` / `WO-36`)**, which bridges neural deliberation and deterministic symbolic execution across five architectural layers:
1. **Pure Gas-Metered MicroScheme DSL (`ADR-007` & `D-REAS-05`, [`src/lucca/reasoning/scheme/`](../../../src/lucca/reasoning/scheme/__init__.py:1)):** Rules are pure functional `State -> Plan` transformations evaluated under a strict **1,000-unit gas limit** with zero global state mutation, typed entity accessors (`entity-str`, `entity-int`, `entity-num` per `D-SEC-04`), and compile-time bounded macro expansion (`MAX_MACRO_DEPTH = 8`, `MAX_MACRO_STEPS = 64`).
2. **E-Graph Equality Saturation, Syntactic Anti-Unification & Babble/Stitch Compression ([`src/lucca/reasoning/egraph.py`](../../../src/lucca/reasoning/egraph.py:1), [`src/lucca/reasoning/compression.py`](../../../src/lucca/reasoning/compression.py:1)):** Ingests recurring `execution_triples` ($N \ge 3$) and multi-turn CEGIS repairs (`Turn 1 Fail -> Turn K Fix` captured by [`CognitiveOutcomeSink`](../../../src/lucca/core/cognitive_sink.py:1)) into equivalence graphs, computing least general generalizations ($\text{lgg}$) to synthesize candidate MicroScheme skills and reusable library macros (`data/learned_macros.json`).
3. **Microsoft Z3 SMT Admission Check & Edge GBNF Constraint Compiler ([`src/lucca/reasoning/smt_verifier.py`](../../../src/lucca/reasoning/smt_verifier.py:1)):** Checks with Z3 that a candidate rule's precondition is satisfiable (`SAT`) and non-tautological (contingency), and that its path arguments stay inside the workspace root, before the rule is admitted into `QUARANTINE`; rejects (`UNMODELED_PREDICATE`) any form it cannot encode. The check covers preconditions and path arguments only, not arbitrary plan semantics (§5 item 4). Also provides a deterministic GBNF-to-Z3 compiler (`config/grammars/zebra_constraints.gbnf`) for 2B–4.5B edge tiers.
4. **The Two-Cadence Inner Life (`IdlePulse` + `DreamRetrospective`, [`src/lucca/memory/reflection.py`](../../../src/lucca/memory/reflection.py:1)):** Governed by homeostatic **`CoherenceDrive`** (unresolved Belnap $\top$ conflicts) and **`CompetenceDrive`** (multi-turn CEGIS repairs and recurring action triples), `DreamRetrospective` executes offline **Dream-RSI Replay** ([`src/lucca/reasoning/replay.py`](../../../src/lucca/reasoning/replay.py:1)) across $\ge 50$ historical turns and logs skill progression in the auditable `learning_events` ledger (`0009_active_goals_and_learning_events.sql`).
5. **Graduated Quarantine Lifecycle & Option A Single-Strike Circuit Breaker (`D-REAS-06`, [`src/lucca/reasoning/lifecycle.py`](../../../src/lucca/reasoning/lifecycle.py:1)):** Induced rules enter **`QUARANTINE`** only. Promotion to **`ACTIVE`** (capped at `MAX_ACTIVE_RULES = 30`) requires $\ge 50$ clean historical replay turns (0 errors, 0 misfires), **5 distinct error-free shadow evaluation clusters**, and **explicit human operator CLI approval (`lucca-admin`)**. Under **Option A (`Rung T4`)**, any single runtime failure on the active path immediately demotes the rule back to `QUARANTINE`.

---

## 2. Architecture: From `CognitiveOutcomeSink` to Verified Symbolic Reflex

```mermaid
flowchart TD
    subgraph WakingTurn ["Waking Turn Execution & CognitiveOutcomeSink (src/lucca/core/cognitive_sink.py)"]
        CEGIS["Multi-Turn CEGIS Repair / Tool Execution"] --> SINK["Emit Signed ASSISTANT_ACTION Receipt<br/>+ Store RecallEpisode & ExecutionTriple (SQLite WAL)"]
        SINK --> DRIVE["Increment CompetenceDrive Priority Queue"]
    end

    subgraph Synthesis ["DreamRetrospective: E-Graph Anti-Unification & Babble/Stitch (src/lucca/reasoning/)"]
        DRIVE --> MINER["RuleInducer (induction.py): Mine Recurrences (N >= 3)"]
        MINER --> EGR["E-Graph Equality Saturation (egraph.py) & LGG Anti-Unification"]
        EGR --> COMP["Library Compression (compression.py) -> Candidate MicroScheme AST"]
    end

    subgraph FormalProver ["Microsoft Z3 SMT Deontic Gate (src/lucca/reasoning/smt_verifier.py)"]
        COMP --> Z3["SMTVerifier (libz3.dll) — Fail-Closed on UNMODELED_PREDICATE"]
        Z3 --> P1["1. Satisfiability Check: ∃S Precondition(S) = True"]
        Z3 --> P2["2. Contingency Check: ∃S Precondition(S) = False"]
        Z3 --> P3["3. Path Argument Check: ∀p ∈ Paths(R), p ⊆ WorkspaceRoot ∧ ¬Contains(p, '..')"]
    end

    subgraph Lifecycle ["Graduated Lifecycle & Circuit Breaker (src/lucca/reasoning/lifecycle.py)"]
        P1 & P2 & P3 -->|All Checks Pass| QUAR["QUARANTINE State (D-REAS-06)"]
        QUAR --> REPLAY["Dream-RSI Replay (replay.py): >= 50 Historical Turns (0 Errors, 0 Misfires)"]
        REPLAY --> SHADOW["SHADOW Evaluation: 5 Distinct Clusters, 0 Runtime Errors"]
        SHADOW --> PEND["PENDING_APPROVAL (Logged in learning_events)"]
        PEND -->|Explicit Operator CLI Sign-Off (lucca-admin)| ACT["ACTIVE Pool (Cap <= 30; 140us Plan Evaluation)"]
        ACT -->|Option A Circuit Breaker: Any Single Runtime Failure| QUAR
    end
```

### 2.1 First-Order Syntactic Anti-Unification & Bounded Macro Expansion
Given recurring execution ASTs $T_1, T_2, \dots, T_k$ ($k \ge 3$) mined by [`RuleInducer`](../../../src/lucca/reasoning/induction.py:1), [`egraph.py`](../../../src/lucca/reasoning/egraph.py:1) constructs an equivalence graph and extracts the least general generalization $\text{lgg}(T_1, T_2)$ such that substitutions $\sigma_1, \sigma_2$ satisfy $\sigma_1(\text{lgg}) = T_1$ and $\sigma_2(\text{lgg}) = T_2$:
$$\text{lgg}\big(\texttt{(convert-unit 15 "km" "mi")}, \texttt{(convert-unit 100 "km" "mi")}\big) = \texttt{(convert-unit ?val "km" "mi")}$$

To prevent unbounded recursion or operator shadowing in synthesized macros ([`src/lucca/reasoning/scheme/macros.py`](../../../src/lucca/reasoning/scheme/macros.py:1)):
- **Primitive Non-Shadowing Invariant (`D-REAS-05`):** `defmacro` cannot bind names in `PRIMITIVE_OPERATORS` (`and`, `or`, `not`, `if`, `let`, `entity-str`, `entity-int`, `entity-num`, `plan`, `step`).
- **Compile-Time Expansion Bounds:** Macro expansion enforces `MAX_MACRO_DEPTH = 8` and `MAX_MACRO_STEPS = 64`.
- **Runtime Gas Metering:** [`eval.py`](../../../src/lucca/reasoning/scheme/eval.py:1) enforces a strict `1,000` gas ceiling per rule evaluation with zero I/O or global mutation (`tests/test_d_reas_08_negative.py`).

### 2.2 Microsoft Z3 SMT Deontic Invariant Encoding (`src/lucca/reasoning/smt_verifier.py`)
Every candidate MicroScheme rule $R = \langle \text{Pre}_R(S), \text{Plan}_R(S) \rangle$ is compiled into a first-order SMT formula evaluated by Z3 (`tests/test_equality_saturation.py`, `scripts/audit_z3_live.py`):
1. **Satisfiability (`SAT` Gate):** $\exists S : \text{Pre}_R(S) = \text{True}$ (rejects dead/contradictory preconditions).
2. **Contingency (`Non-Tautology` Gate):** $\exists S : \text{Pre}_R(S) = \text{False}$ (rejects overly broad rules that hijack every turn).
3. **Deontic Path & Argument Bound Gate:** $\forall p \in \text{Paths}(\text{Plan}_R(S)) : \text{Pre}_R(S) \implies \big(\text{StartsWith}(p, \text{WorkspaceRoot}) \land \neg\text{Contains}(p, \texttt{".."}) \land \neg\text{IsSymlink}(p)\big)$.
4. **Fail-Closed Unknown Predicate Policy:** If `Pre_R` or `Plan_R` references any unmodeled operator, `SMTVerifier` returns `UNMODELED_PREDICATE` and blocks registration.

### 2.3 Edge Z3 GBNF Constraint Compiler for 2B–4.5B Models (`WO-36` Milestone 36.5.2)
Beyond rule verification, [`src/lucca/reasoning/smt_verifier.py`](../../../src/lucca/reasoning/smt_verifier.py:1) includes a deterministic constraint compiler paired with `config/grammars/zebra_constraints.gbnf`. When solving $5 \times 5$ Einstein/Zebra logic grids on small edge models (`Gemma 4 E2B` and `E4B`), grammar-constrained decoding forces the LLM to emit valid relational JSON (`left_of`, `adjacent`, `at_pos`, `same_house`), which `smt_verifier.py` compiles directly into Z3 `Distinct` and arithmetic constraints, eliminating Python Z3 syntax errors on small parameter scales.

### 2.4 `WO-39` (2026-11-03) Implementation & Decontamination Sync: Organs 3 & 4
In `WO-39` (Total Decontamination & Bicameral Mind Restoration), the symbolic rule induction, skill library, and neurosymbolic synthesis layers were upgraded:
1. **`DreamRetrospective` Real Trace & Impasse Extraction (`src/lucca/memory/reflection.py`):** Replaced placeholder `:code "print(1)"` stub rules in `DreamRetrospective` with real execution trace mining from `execution_triples` and waking impasse resolution from `Orchestrator.impasse_backlog`.
2. **`RuleInductionEngine` Wired to `DreamCoderMiner` + `EGraph` (`src/lucca/reasoning/induction.py`):** `RuleInductionEngine` invokes `DreamCoderMiner` (`compression.py`) and `EGraph.extract_best` (`egraph.py`) using the structural description length objective `cost_fn` (`cost.py`). `DreamCoderMiner` expands synthesized `(defmacro ...)` forms prior to Z3 verification (`SMTVerifier`), and `SMTVerifier` verifies arithmetic/division safety (`divisor != 0`).
3. **`SkillLibrary` Shadow Sandbox, AST Symbol Grounding, NARS & ACT-R (`src/lucca/reasoning/skills.py`):** Candidate skills must pass `_check_ast_symbol_grounding` (rejecting ungrounded identifiers) and `verify_in_shadow_sandbox` (isolated execution over test cases). Active/quarantined skills track OpenNARS $(w^+, w^-)$ evidence counts and are retrieved via ACT-R base-level + contextual spreading activation ($B_i = \ln \sum t_j^{-d} + \sum W_k S_{ki}$).
4. **MCTS + Koza GP Crossover & Thread-Safe Z3 Abduction (`mcts.py` & `abduction.py`):** `ASTHoleMCTSEngine` was decontaminated to `UNIVERSAL_NUMERIC_CONSTANTS = [0, 1, 2, 3, -1]` and augmented with Koza GP subtree crossover and mutation over `test_cases`, while `BackwardAbductionSolver.solve_holes_z3` solves symbolic holes across all `test_cases` simultaneously using thread-isolated Z3 contexts.

---

## 3. Empirical Evaluation & Lifecycle Verification Scorecard

### 3.1 Plan-Step Latency: Rule Evaluation vs. LLM Tool-Call Generation
Measured across 50 recurrent procedural invocations, comparing the time for the LLM (`Gemma 4 12B`) to emit a tool call against the time for the MicroScheme evaluator ([`src/lucca/reasoning/scheme/eval.py`](../../../src/lucca/reasoning/scheme/eval.py:1)) to produce the same plan:

| Dimension | LLM Tool-Call Generation (`12B`) | MicroScheme Rule Evaluation | Note |
| :--- | :---: | :---: | :--- |
| **Plan-step latency (P50)** | $462.15\,\text{ms}$ | $0.14\,\text{ms}$ | Compares *only the plan step*. In `ACT_THEN_NARRATE` the LLM is still invoked afterwards to narrate the result (~450–600 ms end-to-end), so the user-visible saving is the ~460 ms plan step, not an end-to-end multiplier. |
| **GPU VRAM during plan step** | $9,972\,\text{MiB}$ resident + CUDA kernels | $0\,\text{MiB}$ (host CPU) | — |
| **Tokens for plan step** | ~240 | 0 | Narration tokens are still spent afterwards. |
| **Precondition & path check** | Sampled | Z3-checked at admission (§2.2) | Z3 checks the rule's precondition and path arguments against the stated constraints; it does not prove properties of arbitrary plan bodies. |

### 3.2 End-to-End L1–L4 & T4 Verification Battery (`luccadocs/audit/findings/V1_RELEASE_AUDIT.md`)

| Capability Rung | Verification Target | Measured Result | Verification Test / Artifact |
| :--- | :--- | :---: | :--- |
| **Rung L1b: Shipped Skill Corpus** | 15 active MicroScheme skill packages (`config/skills/`), each with `plan.scm`, `meta_info.json`, `golden_traces.jsonl`, `backup.md`, `recover.md` | **15 / 15 Active Skills Verified** (`MAX_ACTIVE_RULES = 30`) | `tests/test_l1b_all_skills.py` |
| **Rung L2: Dream-RSI Replay & Contrastive Gate** | Offline historical replay ($\ge 50$ turns, 0 errors, 0 misfires) + contrastive negative-twin shadow evaluation | **100% Pass on Positive & Negative Twins** | `tests/test_l2_replay_and_contrastive.py` |
| **Rung L3: Full Graduated Lifecycle Proof** | Complete end-to-end induction: `induce -> Z3 SMT -> QUARANTINE -> 50-turn replay -> 5 shadow clusters -> PENDING_APPROVAL -> operator approve -> ACTIVE` | **Verified (`induced-launch-app-calculator-v1` reached `ACTIVE` and executed plan)** | `tests/test_l3_lifecycle_proof.py`, `V1_RELEASE_AUDIT.md` §3 |
| **Rung T4: Option A Single-Strike Circuit Breaker** | Any single runtime failure on an `ACTIVE` rule immediately demotes it back to `QUARANTINE` | **100% Immediate Demotion Verified** | `tests/test_lifecycle.py`, `luccadocs/specs/STUDIO_CAPABILITY_ROADMAP.md` §6.4 |
| **Two-Cadence Inner Life (`WO-36`)** | `IdlePulse` (60s NLI + distillation) + `DreamRetrospective` (`CoherenceDrive` & `CompetenceDrive` + `learning_events`) | **Verified (`0009_active_goals_and_learning_events.sql`)** | `tests/test_inner_life.py`, `tests/test_cognitive_sink.py` |

### 3.3 Post-WO-39 Live 52-Turn Multi-Turn Organic `IN-D` Baseline (`logs/test_reports/in_d_live_baseline_wo39.json`)

Executed via [`scripts/run_in_d_live_baseline.py`](../../../scripts/run_in_d_live_baseline.py:1) against live `Gemma 4 12B` (`gemma-4-12b-heretic-Q6_K.gguf`, $T=0.0$, seed 42, `cache_prompt: false`, parser mode) across **52 live natural-language waking turns** (24 recurring turns across 6 planted task families—4 structured tool families and 2 MicroScheme S-expression math families—interleaved with 28 distractor and adversarial turns), followed by `DreamRetrospective`, 50-turn `Dream-RSI` replay, and **16 unseen held-out natural-language turns** (8 positive recurring + 8 negative/adversarial distractors):

| Evaluation Metric | Measured Result (`WO-39` Baseline) | Architectural Failure / Success Diagnosis |
| :--- | :---: | :--- |
| **Live Waking Workload** | **52 turns** (`24` recurring + `28` distractors) | Zero synthetic AST injection; all intents, arguments, and S-expressions emitted live by `Gemma 4 12B`. |
| **Structured Tool Clusters Mined (`RuleInducer`)** | **4 / 4 (100.0%)** | Discovered `calculator` ($n=4$), `notepad` ($n=4$), `notes/roadmap.md` ($n=4$), and `notes/todo.md` ($n=4$). |
| **Z3-Verified Quarantined Tool Rules (`IN-D`)** | **4 / 4 (`QUARANTINE`), 0 (`ACTIVE`)** | All 4 rules passed Z3 SAT, Non-Tautology, and Deontic Path checks; `D-REAS-06` (`0` active without human sign-off) preserved. |
| **E-Graph Rule-Precondition Macros (`induce_macros`)** | **2 / 2 (100.0%)** | Synthesized `(defmacro when-launch-app-app (arg_1_0) ...)` and `(defmacro when-file-read-path (arg_1_0) ...)`. |
| **Dream-RSI $\ge 50$-Turn Historical Replay Pass** | **4 / 4 (100.0%)** | Evaluated across `n_real = 50` live episodes with `0` runtime errors and `0` misfires (`3–4` valid fires per rule). |
| **Held-Out Unseen Positive Recall ($N=8$)** | **8 / 8 (100.0%)** | Induced rules matched all 8 unseen natural-language phrasings across the 4 recurring tool families. |
| **Held-Out Distractor / Adversarial Misfire Rate ($N=8$)** | **0 / 8 (0.0%)** | Zero false triggers on unseen apps (`discord`, `task manager`), unseen files, chitchat mentioning `"calculator"`, or `../../../etc/passwd`. |
| **Free-Form S-Expression Macros Mined (`DreamCoderMacroMiner`)** | **2 mined / 0 quarantined (`0.0%` admission)** | Raw AST compressed `1.169x` (`83 -> 71` nodes), but **0/2** S-expression macros cleared admission into `QUARANTINE`. |
| **Why Pure-Python `egraph.py` + `compression.py` Failed on Free-Form S-Expressions** | **2 Structural Bottlenecks Exposed** | 1. **Outer-Shape Bucket Collision:** `ConsolidationEngine` buckets by `(op:arity)` (`+:3`), merging `FAM_05` `(+ 100 (* 2 100))` with distractor `(+ 2 2)` and collapsing the anti-unified `lgg` to trivial `(+ ?x ?y)`.<br/>2. **Algebraic Variance & Python Falsifier Latency:** On `FAM_06` (`+:4`), the LLM emitted `(/ (* 0.5 8) 2)` on Turn 1 vs `(/ 6 2)` on Turns 2–4, and Python `ScratchpadFalsifier` timed out (`1,233.22 ms > 500.0 ms`). |

---

## 4. Contributions

1. **A lifecycle in which agent-proposed rules cannot act without passing an SMT admission check, a replay gate, shadow evaluation, and human approval (`D-REAS-06`).**
   The full path — induce → Z3 check → `QUARANTINE` → 50-turn replay → 5 shadow clusters → `PENDING_APPROVAL` → operator approval → `ACTIVE` — is exercised end-to-end on one synthetic rule in [`tests/test_l3_lifecycle_proof.py`](../../../tests/test_l3_lifecycle_proof.py:1) and evaluated on a live 52-turn LLM workload in [`scripts/run_in_d_live_baseline.py`](../../../scripts/run_in_d_live_baseline.py:1).
2. **Fail-closed admission.** The Z3 check rejects candidates with unsatisfiable or tautological preconditions and any path argument outside the workspace root, and it rejects (rather than admits) any predicate it cannot model.
3. **Single-strike demotion (`Option A`, `Rung T4`).** Any runtime failure of an `ACTIVE` rule returns it to `QUARANTINE`; verified in [`tests/test_lifecycle.py`](../../../tests/test_lifecycle.py:1).
4. **A hook from solver outcomes into procedural memory (`WO-36`).** [`CognitiveOutcomeSink`](../../../src/lucca/core/cognitive_sink.py:1) records multi-turn CEGIS repairs to `EpisodeRecall` and `execution_triples`, where they become candidates for induction.

---

## 5. Scope of Legitimate Claims & What Is NOT Claimed (`D-DOC-01`)

1. **Sharp dichotomy between structured tool-rule induction (`100%`) and free-form S-expression macro compression (`0%` admission).** On the 52-turn live LLM baseline ([`in_d_live_baseline_wo39.json`](../../../logs/test_reports/in_d_live_baseline_wo39.json:1)), structured `intent + entity` tool-rule induction (`RuleInducer`) induced **4/4** planted rules into `QUARANTINE`, passed 50-turn replay (**4/4**), and achieved **100% (8/8)** held-out recall with **0% (0/8)** false-trigger rate. However, pure-Python syntactic anti-unification (`egraph.py` + `compression.py`) achieved only **1.169×** raw AST compression (`83 -> 71` nodes) and **0/2** admitted S-expression macros because first-order syntactic `lgg` cannot unify algebraically equivalent forms (`(* 0.5 8)` vs `(/ 8 2)`) and outer-arity bucketing (`+:3`) is vulnerable to distractor collisions (`(+ 2 2)`). Overcoming these two limits requires true equality saturation (`egglog`) and corpus-wide MDL subtree mining (`stitch-core`).
2. **Quarantine accumulation vs. human-promoted active rules (`IN-D = 4 quarantined, 0 active`).**
   In [`in_d_latest.json`](../../../logs/test_reports/personhood/in_d_latest.json:5), `learned_skills_quarantined = 4` and `learned_skills_active = 0` (`guard_active_zero_passed = true` per `D-REAS-06`). The 15 shipped active skills in `config/skills/` were written by hand.
3. **Plan-step latency is not end-to-end latency.** The `0.14 ms` figure is the MicroScheme evaluator alone. In `ACT_THEN_NARRATE` the LLM still narrates afterward (~450–600 ms end-to-end); only `REFLEX` emergency commands skip the LLM (~85–120 ms). The earlier "3,300×" framing compared the plan step only and has been removed from the headline.
4. **What the Z3 check does and does not cover.**
   [`SMTVerifier`](../../../src/lucca/reasoning/smt_verifier.py:1) checks rule *preconditions* and *path arguments* over linear integer/real arithmetic and string prefix/containment. It does not prove anything about arbitrary plan bodies; those execute inside the `--network none` container described in TR-05. "Fail-closed" means an unmodeled predicate causes rejection, not that the check is complete.
5. **Z3 admission has no adversarial evaluation.** The admission check has been exercised on authored rules and on the stress tests in [`tests/test_smt_stress.py`](../../../tests/test_smt_stress.py:1). It has not been red-teamed with rules crafted to pass the check while escaping the workspace.
