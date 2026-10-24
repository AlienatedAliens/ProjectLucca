# Work Order 29: Neuro-Symbolic Program Synthesis & The 15-Module Cognitive Ladder

**Date:** 2026-10-03  
**Target Release:** Project Lucca v1.4.0 Baseline (Part 1) $\to$ v1.5.0 Autonomous Cognitive Engine (Part 3)  
**Status:** Ratified Roadmap & Architecture Plan (Gated on Verification Protocol)  
**Audience:** Incoming AI Agents, Core Systems Engineers, and Evaluation Harness Operators  

---

## 1. Architectural Foundation & Overview

**Project Lucca** is uniquely primed for this 15-module neuro-symbolic program synthesis expansion. Rather than starting from scratch, these modules directly extend and mature architectural foundations already operating within the codebase:

- **MicroScheme Symbolic Core:** AST parser, lexer, validator, and primitives in [`src/lucca/reasoning/scheme/`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/scheme/).
- **Congruence-Closure E-Graphs:** Equivalence graph rewrite engine in [`src/lucca/reasoning/egraph.py`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/egraph.py).
- **Persistent Docker RPC Transport:** Line-buffered sub-millisecond container execution in [`src/lucca/sandbox/rpc.py`](file:///c:/Projects/ProjectLucca/src/lucca/sandbox/rpc.py).
- **Conformal Intent Valve & Epistemic Belnap Bilattice:** Split-conformal calibration and abstention router in [`src/lucca/router/heuristic.py`](file:///c:/Projects/ProjectLucca/src/lucca/router/heuristic.py) and [`src/lucca/router/conformal.py`](file:///c:/Projects/ProjectLucca/src/lucca/router/conformal.py).
- **Tolerant AST Sanitizer:** Multi-stage extraction and syntax repair pipeline in [`src/lucca/sandbox/ast_sanitizer.py`](file:///c:/Projects/ProjectLucca/src/lucca/sandbox/ast_sanitizer.py).

---

## 2. The 15 Modules: Architectural Mapping to Lucca

| Tier | # | Module Name | Target File | Existing Foundation in Lucca |
| :--- | :---: | :--- | :--- | :--- |
| **Part 1: Core Synthesis**<br>*(v1.4.0 Baseline / WO-29)* | **1** | **Functional Scheme Spatial DSL** | `src/lucca/reasoning/spatial_primitives.scm` | Plugs directly into MicroScheme AST parser & primitives in [`src/lucca/reasoning/scheme/`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/scheme/) |
| | **2** | **Equality Saturation Rewrite Rules** | `src/lucca/reasoning/egraph.py` | Extends the existing Congruence-Closure E-Graph in [`egraph.py`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/egraph.py#L37-L60) |
| | **3** | **Persistent Docker Scheme RPC** | `src/lucca/sandbox/rpc.py` | Extends line-buffered `DockerRPCTransport` in [`rpc.py`](file:///c:/Projects/ProjectLucca/src/lucca/sandbox/rpc.py) |
| | **4** | **GBNF S-Expression Grammar** | `config/grammars/scheme_sketch.gbnf` | Native GBNF logit constraint in `llama-server.exe` |
| | **5** | **Scratchpad Falsification Loop** | `src/lucca/core/scratchpad.py` | Integrates into `SubTurnScratchpadBuffer` & Docker preflight |
| | **6** | **Non-Destructive Epistemic Prober** | `src/lucca/router/heuristic.py` | Extends the Conformal Intent Valve to halt on ambiguity ($\bot$) |
| **Part 2: Robustness & Hygiene**<br>*(WO-30)* | **7** | **Idiomaticity Cost Extractor** | `src/lucca/reasoning/cost.py` | Plugs into AST extraction in [`egraph.py`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/egraph.py) |
| | **8** | **Transactional Git Staging DAG** | `src/lucca/sandbox/staging.py` | Context-manager worktree isolation inside WSL2 |
| | **9** | **Traceback Divergence Guard** | `src/lucca/core/convergence.py` | Extends turn convergence checks to abort hallucination loops |
| | **10** | **Belnap Latent Investigator** | `src/lucca/memory/latent_probe.py` | Uses Belnap 4-valued logic ($\top, \bot, T, F$) to isolate env state drift |
| | **11** | **Boundary Topology Parser** | `src/lucca/reasoning/topology.py` | Builds on AST extraction in [`ast_sanitizer.py`](file:///c:/Projects/ProjectLucca/src/lucca/sandbox/ast_sanitizer.py) to protect API contracts |
| **Part 3: Autonomous Search**<br>*(v1.5.0 Cognitive Engine / WO-31)* | **12** | **AST-Hole MCTS Engine** | `src/lucca/reasoning/mcts.py` | Multi-threaded CPU tree search over S-expression holes |
| | **13** | **BitNet b1.58 2B Policy Prior** | `src/lucca/reasoning/bitnet_policy.py` | Host CPU integer SIMD execution (~1.2 GB RAM, 0 MB VRAM) |
| | **14** | **DreamCoder Macro Miner** | `src/lucca/reasoning/compression.py` | Extends anti-unification in [`egraph.py`](file:///c:/Projects/ProjectLucca/src/lucca/reasoning/egraph.py) for sleep-phase library learning |
| | **15** | **Backward Abduction Solver** | `src/lucca/reasoning/abduction.py` | Works backwards from target invariant assertions using e-graph unification |

---

## 3. Architectural & Hardware Integrity

This design strictly respects Lucca's non-negotiable workstation hardware budget:
- **0 MB VRAM Delta:** Every single one of these 15 modules executes exclusively in **host CPU threads (Intel Core Ultra 9 275HX, 24T), host DDR5 RAM, or the WSL2 Docker sandbox**.
- **Uncompromised Neural & Voice Engines:** The **RTX 5080 Laptop GPU (16 GB GDDR7)** remains 100% dedicated to serving the primary LLM (`gemma-4-12b-heretic-Q6_K.gguf` / `nemotron-30b`), while the **Intel NPU** runs Kokoro TTS and Silero VAD without contention.
- **Strict Invariant Adherence:**
  - **ADR-006**: No raw ungrounded narration into memory; commits must be cryptographically signed by authorized domain signers.
  - **ADR-013**: Direct host fallback disabled; untrusted code runs inside isolated Docker containers in WSL2.

---

## 4. Phased Execution Roadmap

To prevent conflation and maintain clean empirical verification, implementation proceeds across sequential work orders:

```mermaid
flowchart TD
    subgraph Gate ["Immediate Verification Gate"]
        H1["3-Way Re-Prompt Brief on ~110 Items"] --> H2["Harness Frozen"]
        H2 --> H3["Model Swap (Nemotron on Frozen Harness)"]
        H3 --> H4["Label 20 Bucket C Failures"]
    end

    subgraph WO29 ["WO-29: Part 1 Baseline (v1.4.0)"]
        M1["1. Spatial DSL"]
        M2["2. E-Graph Rewrites"]
        M3["3. Docker Scheme RPC"]
        M4["4. GBNF Grammar"]
        M5["5. Scratchpad Falsification"]
        M6["6. Epistemic Prober"]
    end

    subgraph WO30 ["WO-30: Part 2 Robustness & Hygiene"]
        M7["7. Idiomaticity Cost"]
        M8["8. Transactional Git DAG"]
        M9["9. Loop Divergence Guard"]
        M10["10. Belnap Latent Probe"]
        M11["11. Boundary AST Parser"]
    end

    subgraph WO31 ["WO-31: Part 3 Scaling (v1.5.0)"]
        M12["12. AST-Hole MCTS"]
        M13["13. BitNet b1.58 2B Prior"]
        M14["14. DreamCoder Macro Miner"]
        M15["15. Backward Abduction"]
    end

    Gate --> WO29
    WO29 --> WO30
    WO30 --> WO31

    subgraph Orthogonal ["Parallel & Gated Work"]
        Voice["Voice Scaffolding: Acoustic Lock & Slot-Locking (Parallel)"]
        WO32["WO-32: Reflection Loop (Gated on 200-500 Organic Dogfood Turns)"]
    end
```

---

## 5. Sequential Execution Work Orders

### WO-29: Part 1 Core Synthesis Baseline (Target: v1.4.0)
Focuses on establishing the closed-loop neural-symbolic synthesis channel:
1. `src/lucca/reasoning/spatial_primitives.scm`: Define domain-specific spatial and algebraic primitives in MicroScheme.
2. `src/lucca/reasoning/egraph.py`: Implement equality saturation rewrite rules for canonical simplification.
3. `src/lucca/sandbox/rpc.py`: Persistent line-buffered MicroScheme RPC inside the Docker sandbox.
4. `config/grammars/scheme_sketch.gbnf`: GBNF logit constraint enforcing valid S-expression sketches from `llama-server`.
5. `src/lucca/core/scratchpad.py`: Sub-turn scratchpad falsification loop validating intermediate sketches against preflight assertions.
6. `src/lucca/router/heuristic.py`: Non-destructive epistemic prober extending conformal intent gating to halt and seek clarification on ambiguous ($\bot$) queries.

### WO-30: Part 2 Robustness & Hygiene
Focuses on invariant safety, rollback stability, and semantic state protection:
7. `src/lucca/reasoning/cost.py`: AST extraction cost function prioritizing idiomatic, minimal-depth expressions.
8. `src/lucca/sandbox/staging.py`: Transactional Git staging DAG with context-manager worktree isolation inside WSL2.
9. `src/lucca/core/convergence.py`: Traceback divergence guard tracking error entropy to abort degenerate hallucination loops.
10. `src/lucca/memory/latent_probe.py`: Belnap 4-valued logic investigator detecting environment and state drift.
11. `src/lucca/reasoning/topology.py`: Boundary topology parser protecting external API contracts and typed accessors.

### WO-31: Part 3 Scaling to Autonomous Search (Target: v1.5.0)
Focuses on test-time compute scaling and autonomous library learning:
12. `src/lucca/reasoning/mcts.py`: Multi-threaded CPU MCTS engine over typed S-expression holes.
13. `src/lucca/reasoning/bitnet_policy.py`: 1-bit / 1.58-bit BitNet 2B policy prior running via CPU AVX-512/AMX integer SIMD (~1.2 GB host RAM, 0 MB VRAM).
14. `src/lucca/reasoning/compression.py`: DreamCoder-style macro miner discovering reusable symbolic abstractions during background consolidation.
15. `src/lucca/reasoning/abduction.py`: Backward abduction solver deriving preconditions from target assertions via e-graph unification.

### Orthogonal Tracks
- **Voice Scaffolding (Parallel)**: Acoustic Lock & Slot-Locking ensuring seamless barge-in and audio turn discipline.
- **WO-32 Reflection Loop (Gated)**: Unprompted proactive reflection loop, strictly gated on accumulating 200–500 organic dogfood companion conversation turns.

---

## 6. Immediate Verification Gate: Protocol & Action Plan

Pre-flight gate status following v1.35 closeout (1.35-test-evaluated):

1. **Three-Way Re-Prompt Comparison Brief**:
   - **Resolved**: Baseline prompt locked. Fix B (traceback enrichment) evaluated on dev-400 (1.35-dev-400-v4) and rejected under the zero-loss gate rule (losses=3).
2. **Lock Harness Configuration**:
   - **Locked**: Frozen under 1.35.1-frozen (cache_prompt: false, 1536 max tokens, deterministic decoding seed=42, 2-turn feedback).
3. **Model Swap Verification**:
   - **Deferred**: Postponed to after WO-31 per the model-swap experimental protocol (12B fixed through WO-29/30/31; then factorial swap).
4. **Bucket C Failure Labeling (Pre-WO-29 Baseline)**:
   - **Complete**: Labeled 43 genuine `reasoning` failures from the dev-400 ledger (`logs/test_reports/v135_failure_ledger_v3.md`) to serve as the benchmark target for neural-symbolic synthesis:

| idx | failure_class | S/L | finish | tokens | pred | expected | NOTES |
|---|---|---|---|---|---|---|---|
| 4 | genuine_derivation_miss | N/N | stop | 2320 | 3 < \lambda \le 4 | (3,4] | Derivation error |
| 11 | genuine_derivation_miss | N/N | length | 3072 | 4 | 504 | Token budget exhausted; loop/rambling |
| 20 | genuine_derivation_miss | N/N | length | 3072 | 1 | -9 | Token budget exhausted; loop/rambling |
| 30 | (strict-only) | N/Y | stop | 303 | 13.2871972318339 | \frac{3840}{289} | Float approximation instead of exact symbolic |
| 37 | prose_slip | N/N | length | 3072 |  | 64 | Cauchy-Schwarz loop at 1536 tokens |
| 39 | equivalence_format_miss | N/N | stop | 400 | 1/6 | \frac{1}{3} | Mathematical derivation error |
| 55 | equivalence_format_miss | N/N | length | 3072 | 11 | 2\sqrt{113} | Token budget exhausted; loop/rambling |
| 65 | (strict-only) | N/Y | length | 1536 | -tan(4*pi/9) + 4*cos(pi… | -\sqrt{3} | Token budget exhausted; loop/rambling |
| 67 | equivalence_format_miss | N/N | length | 3072 | 45 | \frac{270}7\text{ degre… | Token budget exhausted; loop/rambling |
| 69 | genuine_derivation_miss | N/N | stop | 2796 | 9 | 19 | Derivation error |
| 74 | genuine_derivation_miss | N/N | stop | 294 | 16 | 4 | Derivation error |
| 80 | genuine_derivation_miss | N/N | stop | 1874 | 5x + -7y + 11z + 4 = 0 | 5x - 7y + 11z + 4 = 0 | Derivation error |
| 82 | (strict-only) | N/Y | stop | 161 | 0.577350269189626 | \frac{\sqrt{3}}{3} | Float approximation instead of exact symbolic |
| 84 | genuine_derivation_miss | N/N | stop | 311 | 13 | 23 | Derivation error |
| 85 | equivalence_format_miss | N/N | length | 1536 | 2 < infinity | (2,\infty) | Token budget exhausted; loop/rambling |
| 103 | (strict-only) | N/Y | stop | 290 | 0.666666666666667 | \frac{2}{3} | Float approximation instead of exact symbolic |
| 105 | genuine_derivation_miss | N/N | length | 3072 | 1 | 0 | Token budget exhausted; loop/rambling |
| 117 | genuine_derivation_miss | N/N | stop | 173 | 21/2 | 6 | Derivation error |
| 123 | genuine_derivation_miss | N/N | length | 3072 | -4 | 54 | Token budget exhausted; loop/rambling |
| 141 | genuine_derivation_miss | N/N | stop | 1438 | 154.0 | 116 | Derivation error |
| 158 | equivalence_format_miss | N/N | stop | 440 | 72*12**(1/3) | 864 \mbox{ inches}^2 | Mathematical derivation error |
| 165 | equivalence_format_miss | N/N | length | 3072 | 0 | 1\frac{4}{5} | Token budget exhausted; loop/rambling |
| 168 | equivalence_format_miss | N/N | stop | 1160 | 150 | 180^\circ | Mathematical derivation error |
| 185 | equivalence_format_miss | N/N | stop | 2079 | 2*sqrt(2) + 3, 3 - 2*sq… | 3 \pm 2 \sqrt{2} | Superfluous roots derived |
| 187 | equivalence_format_miss | N/N | length | 3072 | 3 | \frac{17}{21} | Token budget exhausted; loop/rambling |
| 191 | genuine_derivation_miss | N/N | stop | 353 | 7/2 | 4 | Derivation error |
| 194 | equivalence_format_miss | N/N | stop | 541 | Interval(3/5, 8/3) | \left(\frac{3}{5},\frac… | Incorrect boundary inclusion/exclusion |
| 206 | equivalence_format_miss | N/N | stop | 242 | 0.473684210526316 | \frac9{19} | Mathematical derivation error |
| 209 | equivalence_format_miss | N/N | stop | 1048 | 1.0 + 3*sqrt(3) | 1+2\sqrt{3} | Mathematical derivation error |
| 220 | genuine_derivation_miss | N/N | stop | 150 | 1 | -128 | Derivation error |
| 225 | genuine_derivation_miss | N/N | stop | 1913 | 150 | 120 | Derivation error |
| 227 | equivalence_format_miss | N/N | stop | 1019 | -9/100 | \frac{9}{100} | Sign error in derivation |
| 229 | genuine_derivation_miss | N/N | stop | 1691 | 0 | 3 | Derivation error |
| 262 | equivalence_format_miss | N/N | stop | 821 | -16*sqrt(3) | 16 \sqrt{3} | Sign error in derivation |
| 280 | genuine_derivation_miss | N/N | stop | 261 | 12th | 12 | Derivation error |
| 281 | equivalence_format_miss | N/N | stop | 1021 | Interval(0, 36) | (0,9) \cup (9,36) | Missed singularity/domain hole |
| 284 | equivalence_format_miss | N/N | stop | 239 | Interval(-2, 7) | x \in [-2,7] | Incorrect boundary inclusion/exclusion |
| 290 | (strict-only) | N/Y | stop | 293 | 0.916515138991168 | \frac{\sqrt{21}}{5} | Float approximation instead of exact symbolic |
| 301 | equivalence_format_miss | N/N | stop | 2013 | -56*sqrt(sqrt(2) + 2) -… | \frac{14}{3} | Mathematical derivation error |
| 332 | equivalence_format_miss | N/N | stop | 1191 | Interval(pi**2/8, 5*pi*… | \left[ \frac{\pi^2}{8},… | Incorrect boundary inclusion/exclusion |
| 346 | genuine_derivation_miss | N/N | stop | 1480 | 0.0 | 15 | Derivation error |
| 361 | equivalence_format_miss | N/N | length | 3072 | 0 | 75^\circ | Token budget exhausted; loop/rambling |
| 396 | equivalence_format_miss | N/N | stop | 1418 | Interval(2, 102) | (2,12) \cup (12,102) | Missed singularity/domain hole |

5. **Clear Gate for WO-29**:
   - **Cleared**: Baseline verified, test evaluated on held-out battery, and pre-WO-29 reasoning catalog locked. Ready for Phase 1 baseline implementation of Modules 1–6.
