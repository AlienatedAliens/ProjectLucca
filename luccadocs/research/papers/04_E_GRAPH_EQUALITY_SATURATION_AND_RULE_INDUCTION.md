# Technical Report TR-04: A Gated Lifecycle for Agent-Authored Rules
## Z3-Checked Admission, Quarantine-Only Induction, Shadow Evaluation, Human Promotion, and Single-Strike Demotion (`ADR-007`, `D-REAS-05`, `D-REAS-06`)

```yaml
doc_status: canonical
as_of: 2026-10-19
release_baseline: v1.45.0 (WO-36)
submission_status: technical_report (design note; no induction-quality evaluation exists yet)
related_adrs: [ADR-007, D-REAS-05, D-REAS-06, D-SEC-04, D-COG-01]
verification: artifact-sourced (V1_RELEASE_AUDIT.md, tests/test_l3_lifecycle_proof.py & in_d_latest.json)
```

**Authors:** Project Lucca Program Synthesis, Formal Verification & Cognitive Architecture Group
**Date:** October 19, 2026 (`v1.45.0` / `WO-36` Baseline)
**Hardware Platform:** Intel Core Ultra 9 275HX (24 cores, Host CPU LISP + Microsoft Z3 `libz3.dll`) + Intel AI Boost NPU (`OpenVINO`) + SQLite WAL (`execution_triples` & `learning_events`)

**Contribution type and retitling note.** This report describes the *safety lifecycle* through which an agent-proposed rule must pass before it can act, and the mechanical proof that the lifecycle works end-to-end on one synthetic rule. It was previously titled as an equality-saturation / rule-induction paper. That title overstated the evidence: the e-graph anti-unification component exists and is unit-tested, but **no evaluation of induction quality** (compression ratio, generalization, false-trigger rate on a recurring workload) has been run, and the count of organically induced production rules is zero (`IN-D = 0`). The retitled report claims only what the lifecycle tests demonstrate.

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

---

## 4. Contributions

1. **A lifecycle in which agent-proposed rules cannot act without passing an SMT admission check, a replay gate, shadow evaluation, and human approval (`D-REAS-06`).**
   The full path — induce → Z3 check → `QUARANTINE` → 50-turn replay → 5 shadow clusters → `PENDING_APPROVAL` → operator approval → `ACTIVE` — is exercised end-to-end on one synthetic rule in [`tests/test_l3_lifecycle_proof.py`](../../../tests/test_l3_lifecycle_proof.py:1).
2. **Fail-closed admission.** The Z3 check rejects candidates with unsatisfiable or tautological preconditions and any path argument outside the workspace root, and it rejects (rather than admits) any predicate it cannot model.
3. **Single-strike demotion (`Option A`, `Rung T4`).** Any runtime failure of an `ACTIVE` rule returns it to `QUARANTINE`; verified in [`tests/test_lifecycle.py`](../../../tests/test_lifecycle.py:1).
4. **A hook from solver outcomes into procedural memory (`WO-36`).** [`CognitiveOutcomeSink`](../../../src/lucca/core/cognitive_sink.py:1) records multi-turn CEGIS repairs to `EpisodeRecall` and `execution_triples`, where they become candidates for induction. Whether this produces useful rules has not been evaluated.

---

## 5. Scope of Legitimate Claims & What Is NOT Claimed (`D-DOC-01`)

1. **No induction-quality evaluation exists.** The e-graph anti-unification and library-compression components ([`egraph.py`](../../../src/lucca/reasoning/egraph.py:1), [`compression.py`](../../../src/lucca/reasoning/compression.py:1)) are implemented and unit-tested, but we have not measured how well they induce rules: no compression ratio, no generalization rate, no false-trigger rate on held-out turns, and no comparison against a trivial template-matching baseline. The required experiment is a synthetic recurring-workload benchmark with planted rules and distractors; it has not been run. This report therefore makes **no claim about induction quality**.
2. **Mechanical lifecycle proof vs. live production accumulation (`IN-D = 0`).**
   The lifecycle is exercised end-to-end on one synthetic rule in [`tests/test_l3_lifecycle_proof.py`](../../../tests/test_l3_lifecycle_proof.py:1), and 15 hand-authored skill packages are active in `config/skills/` ([`tests/test_l1b_all_skills.py`](../../../tests/test_l1b_all_skills.py:1)). The count of organically induced and human-promoted production rules in the live telemetry snapshot [`in_d_latest.json`](../../../logs/test_reports/personhood/in_d_latest.json:5) is **zero**. The 15 shipped skills were written by hand.
3. **Plan-step latency is not end-to-end latency.** The `0.14 ms` figure is the MicroScheme evaluator alone. In `ACT_THEN_NARRATE` the LLM still narrates afterward (~450–600 ms end-to-end); only `REFLEX` emergency commands skip the LLM (~85–120 ms). The earlier "3,300×" framing compared the plan step only and has been removed from the headline.
4. **What the Z3 check does and does not cover.**
   [`SMTVerifier`](../../../src/lucca/reasoning/smt_verifier.py:1) checks rule *preconditions* and *path arguments* over linear integer/real arithmetic and string prefix/containment. It does not prove anything about arbitrary plan bodies; those execute inside the `--network none` container described in TR-05. "Fail-closed" means an unmodeled predicate causes rejection, not that the check is complete.
5. **Z3 admission has no adversarial evaluation.** The admission check has been exercised on authored rules and on the stress tests in [`tests/test_smt_stress.py`](../../../tests/test_smt_stress.py:1). It has not been red-teamed with rules crafted to pass the check while escaping the workspace.
