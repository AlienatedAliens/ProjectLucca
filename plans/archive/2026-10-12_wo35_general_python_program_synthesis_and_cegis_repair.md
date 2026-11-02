# Work Order 35: General Python Program Synthesis with CEGIS Autonomous Self-Repair & Universal Symbolic Reasoning

```yaml
doc_status: canonical
as_of: 2026-10-12
target_release: v1.5.0 / WO-35
supersedes: []
superseded_by: []
verification: code-cited
```

**Target Release:** Project Lucca v1.5.0 General Reasoning Core  
**Prerequisites Satisfied:**
- WO-33 Controlled Library Extension & Multi-Domain Harmonization complete.
- OOD Generality Audit complete (Option 1 Noise Floor $\pm 1.6\text{ pp}$ verified, Option 2 Extended-Thinking Baseline verified across 60 problems; sealed reports `ood_generality_audit_1791738304.json` and `ood_thinking_baseline_1791744715.json`).
- Weight & Projector provenance pinned in [`models/MANIFEST.json`](file:///C:/Projects/ProjectLucca/models/MANIFEST.json).
- Docker persistent sandbox (`lucca-file-sandbox`) verified with non-root UID, read-only FS, and network isolation.

**Hardware & Server Environment:**
- Single-slot resident `llama-server` (`--parallel 1`, 32k context, Q8_0 KV, Flash Attention) on NVIDIA GeForce RTX 5080 Laptop GPU (16,303 MiB, 175W).
- Target Models: `gemma-4-12b-heretic-Q6_K.gguf` (Primary), `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` (Edge), `Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf` (Ultra-Edge).

---

## 1. Executive Summary & Problem Formulation

In Options 1 and 2 of the Benchmark Review audit, we established the definitive ground truth of the system:
1. **The Extended-Thinking Finding:** Gemma 4 12B natively solves 92.5% of constraint and navigation problems via mental chain-of-thought (CoT). However, it expends 8,000–11,000 characters of CoT taking 40–74 seconds per query, and frequently falls into repetitive token-budget loops.
2. **The Code Synthesis Structural Advantage:** General Python program synthesis (PAL) achieves **100.0% (60/60)** accuracy in $<1.5\text{ seconds}$ execution time, completely outperforming mental simulation on Code Execution Tracing (CruxEval: 100% vs 50%, $p = 2.44 \times 10^{-4}$).
3. **The Current Bottleneck:** General Python synthesis is currently **one-shot**. When code fails (or on harder multi-step problems), the system immediately falls back to direct output (`INTERNAL_FALLBACK`). Furthermore, MicroScheme's formal Z3 SMT verifier and e-graphs are locked to 2D integer matrices and cannot process general lists, vectors, or symbolic constraints.

**Work Order 35 elevates Lucca from a "one-shot code executor" to an "autonomous self-repairing neurosymbolic reasoning system."**

---

## 2. Architecture & Work Packages

```
               [Input Problem (Text, Math, Constraint, or Code)]
                                      │
                                      ▼
                      ┌───────────────────────────────┐
                      │    NEUROSYMBOLIC DISPATCH     │
                      │  • Grid/Visual -> MicroScheme │
                      │  • General -> General Python  │
                      └───────────────┬───────────────┘
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
┌──────────────────────────────┐              ┌──────────────────────────────┐
│   UNIVERSAL MICROSCHEME      │              │      AUTONOMOUS CEGIS        │
│   (Milestone 35.3)           │              │      PYTHON ENGINE (M35.1)   │
│ • Lists, Vectors, Sets, Maps │              │ • GBNF Code Generation       │
│ • Z3 Invariant Pre-Filter    │              │ • Docker Sandbox Execution   │
│ • SMT Formal Proof Receipts  │              │ • Traceback & State Diffs    │
└──────────────────────────────┘              │ • Multi-Turn Self-Repair     │
                                              └──────────────────────────────┘
```

### 2.1 Milestone 35.1: Multi-Turn Python CEGIS Engine ([`src/lucca/reasoning/cegis_python.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/cegis_python.py))
- **Objective:** Implement an autonomous Counter-Example Guided Inductive Synthesis loop for general Python tasks.
- **Specification:**
  - `synthesize_and_repair(prompt, test_cases, max_turns=3)`:
    - **Turn 1:** Synthesizes initial Python solution using system prompt guidelines (pure functions, assert statements, minimal imports).
    - **Execution:** Executes inside Docker container `lucca-file-sandbox` via `DockerRPCTransport`.
    - **Failure Interception:** Catches `AssertionError`, `IndexError`, `TypeError`, `ValueError`, `TimeoutError`.
    - **Repair Abduction:** Constructs structured feedback:
      ```
      [Execution Failure on Turn {k}]
      Error: {error_type}: {error_message}
      Failed Line: {line_number}: {line_content}
      Local Variables: {locals_dict}
      Please repair the function to satisfy the constraints. Output ONLY the corrected ```python block.
      ```
    - **Repair Turns:** Up to 3 iterations until clean execution or budget exhaustion.
    - **Invariant:** $Arm\ B \ge Arm\ A$ strictly preserved via verifiable test harness.

### 2.2 Milestone 35.2: GBNF Grammar Constraints for Code Blocks ([`config/grammars/python_program.gbnf`](file:///C:/Projects/ProjectLucca/config/grammars/python_program.gbnf))
- **Objective:** Guarantee that synthesized code is syntactically valid Python enclosed in markdown blocks, completely eliminating token waste, conversational preamble, and regex parse failures.
- **Grammar Spec:**
  - Token stream forced to: `root ::= "```python\n" python-code "\n```"`
  - Enforces Python indentation, identifier rules, and balanced parentheses.

### 2.3 Milestone 35.3: Universal Symbolic Primitives for MicroScheme ([`src/lucca/reasoning/scheme/universal_primitives.py`](file:///C:/Projects/ProjectLucca/src/lucca/reasoning/scheme/universal_primitives.py))
- **Objective:** Extend MicroScheme to handle non-grid data structures (vectors, lists, sets, graphs) without throwing `ValueError: invalid literal for int`.
- **Primitives:**
  - **Sequence Operations:** `map`, `filter`, `fold`, `zip`, `take`, `drop`, `reverse`, `length`.
  - **Relational & Sets:** `member?`, `subset?`, `union`, `intersection`, `difference`, `unique?`.
  - **Vector Geometry:** `vec2d`, `vec-add`, `vec-sub`, `heading-turn`, `manhattan-dist`, `euclidean-dist`.
  - **Logical Invariants:** `all?`, `any?`, `none?`, `count-if`.

### 2.4 Milestone 35.4: Empirical Benchmark & Non-Regression Audit
- Run the full 60-problem OOD suite and ConceptARC suite.
- Verify:
  1. CEGIS self-repair handles edge case errors gracefully.
  2. Universal MicroScheme executes vector navigation without grid conversion crashes.
  3. Static gates and pytest suites pass with 0 regressions.

---

## 3. Success Criteria & Non-Negotiable Gates
1. **Safety Boundary:** All synthesized Python executes exclusively inside `lucca-file-sandbox` with `--network none`, `--read-only`, non-root user, and host fallback disabled.
2. **Zero Regression:** $Arm\ B \ge Arm\ A$ must be empirically verified across all evaluated benchmarks.
3. **Strict Typing:** All new modules must pass `uv run mypy --strict` with zero errors.
4. **Pytest Gate:** All unit tests must pass in $<15\text{s}$.
