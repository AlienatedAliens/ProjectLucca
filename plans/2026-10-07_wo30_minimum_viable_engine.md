# Work Order 30: Minimum Viable Engine (Macro Mining & Rule Induction Loop)

```yaml
doc_status: canonical
as_of: 2026-10-07
supersedes: []
superseded_by: []
verification: code-cited
```

**Target Release:** Project Lucca v1.4.0 Baseline  
**Prerequisites Satisfied:** Pre-WO-30 shoring and harmonization complete (Commits `7f71fce`, `9ea19f5`, `dd14034`, `54640f9`; audit register: 30 remediated, 1 not reproduced, 0 open; RESULTS.md ledger: 32 rows, 0 mismatches; static gates: 24/24 passing).  
**Hardware Budget Constraint:** $\Delta\text{VRAM} = 0\,\text{MB}$ (RTX 5080 reserved exclusively for primary LLM / `llama-server`), Host CPU threads only (Intel Core Ultra 9 275HX), $\Delta\text{RAM} \le 512\,\text{MB}$.

---

## 1. Architectural Purpose & Scope

Per the ratified roadmap re-sequencing ([`plans/2026-10-05_pre_wo30_shoring_and_ladder_resequencing.md`](2026-10-05_pre_wo30_shoring_and_ladder_resequencing.md) §3.1), **Work Order 30** delivers a thin, end-to-end neuro-symbolic macro-mining loop on top of existing foundations (`src/lucca/reasoning/egraph.py`, `src/lucca/reasoning/lifecycle.py`, and `src/lucca/reasoning/smt_verifier.py`).

Rather than building horizontal hygiene layers prior to core cognition, WO-30 builds the end-to-end engine loop where Lucca acquires, evaluates, and bounds her own learned macro-rules:

```
Candidate Execution Traces (MicroScheme ASTs)
          │
          ▼
   [Module 4: GBNF S-Expression Grammar]  ──► Enforces syntactically closed Scheme proposals
          │
          ▼
   [Module 14: DreamCoder Macro Miner]    ──► Anti-unification over e-graphs (D-REAS-08)
          │
          ▼
   [Module 7: Idiomaticity Cost Engine]   ──► Minimum Description Length compression metric
          │
          ▼
   [Module 5: Scratchpad Falsification]   ──► Dynamic execution in isolated Docker sandbox (D-AUD-13)
          │
          ▼
   [Z3 SMT Verification (D-REAS-07)]      ──► Proves non-tautology, satisfiability & safety
          │
          ▼
   [RuleLifecycleManager (D-REAS-06)]     ──► Enters QUARANTINE; bounded by D-REAS-05; 0 to ACTIVE
```

---

## 2. Included Modules & Implementation Cut-Lines

### Module 14: DreamCoder Macro Miner (`src/lucca/reasoning/compression.py`)
- **Foundation:** Extends first-order syntactic anti-unification in [`src/lucca/reasoning/egraph.py`](../src/lucca/reasoning/egraph.py).
- **Function:** Mines common sub-AST patterns across successful execution traces, extracts parameter-abstracted MacroDefinitions, and computes compression gain against Module 7's cost metric.
- **Cut-Line:** "Good enough" when recurring 2-to-4 node subtrees are extracted into parameter-abstracted S-expression forms and passed to Z3 SMT verification. Exhaustive higher-order lambda abstraction is not required for v1.4.0.

### Module 7: Idiomaticity Cost Extractor (`src/lucca/reasoning/cost.py`)
- **Foundation:** Plugs into MicroScheme AST node parsing and e-graph extraction.
- **Function:** Evaluates structural complexity / description length: $\text{Cost}(T) = \sum_{n \in T} w(\text{op}_n) + \alpha \cdot \text{depth}(T)$. Serves as the objective function for candidate compression ranking.
- **Cut-Line:** "Good enough" when AST node counting with basic operator weights ($w(\text{primitive})=1$, $w(\text{branch})=2$, depth penalty $\alpha=0.5$) consistently ranks collapsed macros lower than redundant expansions.

### Module 4: GBNF S-Expression Grammar (`config/grammars/scheme_sketch.gbnf`)
- **Foundation:** Native GBNF logit constraint in `llama-server.exe` (`--grammar`).
- **Function:** Enforces that LLM-generated Scheme sketches and candidate proposals strictly parse into valid, balanced MicroScheme S-expressions at decode time.
- **Cut-Line:** "Good enough" when all generated tokens conform to MicroScheme primitives, identifiers, and balanced parentheses with 0 parse errors.
- **Synergy:** Shares decode-time grammar infrastructure with **SPIKE-A** (grammar-constrained ACTION-CLAIM channel).

### Module 5: Scratchpad Falsification Loop (`src/lucca/core/scratchpad.py`)
- **Foundation:** Integrates into `SubTurnScratchpadBuffer` and persistent Docker Scheme RPC (`src/lucca/sandbox/rpc.py`).
- **Function:** Tests candidate macros against $\ge 3$ concrete I/O test cases in the WSL2 Docker sandbox before admitting them to quarantine. Fails fast on runtime errors, timeouts, or assertion failures.
- **Cut-Line:** "Good enough" when counterexample generation terminates within 500ms and filters out syntactically valid but semantically broken candidates before SMT/quarantine ingestion.

---

## 3. Explicit Invariants & Boundary Contracts

1. **`D-REAS-05` (Bounded Complexity):** Mined macros must strictly satisfy depth $\le 8$ and execution step limit $\le 64$. Any candidate exceeding these bounds must be rejected with a recorded violation.
2. **`D-REAS-06` (Quarantine-Only Induction):** Mined macros are emitted strictly into `QUARANTINE` via `RuleLifecycleManager`. Auto-promotion to `ACTIVE` is prohibited; promotion requires human/operator sign-off.
3. **`D-REAS-07` (Z3 Formal Verification):** All mined macro candidates must pass Z3 SMT pre-verification (SAT, non-tautology, and path-traversal safety invariants) prior to entering `QUARANTINE`.
4. **`D-AUD-13` / `ADR-013` (Container Sandboxing):** Dynamic execution during scratchpad falsification occurs strictly inside WSL2 Docker containers (`--network none`); no direct host execution.
5. **`ADR-006` / `D-MEM-06` (Cryptographic Provenance):** Mined rules and execution receipts must be cryptographically signed by authorized signers (`InferredAssertionSigner` or `DeterministicRuleSigner`). Unsigned LLM text is barred from memory.

---

## 4. Pre-Registered Verification Gates

### Plumbing Gate (G-WO30-PLUMB)
1. **Quarantine Admission:** $\ge 1$ mined macro successfully generated from execution traces reaches `QUARANTINE` in `RuleLifecycleManager`.
2. **Promotion Guard:** Exactly $0$ mined macros reach `ACTIVE` state without explicit operator review/approval.
3. **Negative Bound Test:** A synthetic over-depth candidate (depth $> 8$ or steps $> 64$) is rejected by `D-REAS-05` validation.
4. **IN-D Grader Progress:** The personhood IN-D learned-skill metric advances from "NOT YET MEASURED" to an active measurement showing quarantined skills tracked.

### Utility Gate (G-WO30-UTIL, Pre-Registered for Shadow Execution)
1. In quarantine shadow mode, $\ge 1$ mined macro reduces the idiomaticity cost (Module 7 metric) on $\ge 3$ of the 43 labeled Bucket C reasoning failure items (`handover/WORKORDER_29.md` §6) relative to the un-mined baseline.
2. Complete reporting: All mined proposals, passes, rejections (Z3 unsat, counterexample, bound exceeded), and cost deltas recorded in a versioned run artifact.

---

## 5. What Is Explicitly Not Claimed

- **No Autonomous Deployment:** Mined macros in `QUARANTINE` are evaluated in shadow mode only; they do not alter live production agent responses without human ratification.
- **No Autonomous Tree Search (MCTS):** S-expression hole tree search is reserved for **WO-31**.
- **No Neural Policy Prior:** BitNet b1.58 2B policy prior is deferred to **WO-32** as an empirical spike.
- **No General Multi-Language Synthesis:** Program synthesis is strictly scoped to the MicroScheme domain-specific AST.

---

## 6. Execution Disposition & Verification Receipts (2026-10-09)

- **Status:** **Shipped & Verified.**
- **Ratification:** `D-REAS-10` ratified in `docs/DECISIONS.md`.
- **Shipped Modules:**
  1. Module 4: `config/grammars/scheme_sketch.gbnf`
  2. Module 7: `src/lucca/reasoning/cost.py`
  3. Module 5: `src/lucca/core/scratchpad.py`
  4. Module 14: `src/lucca/reasoning/compression.py`
  5. Personhood IN-D Grader: `src/lucca/evaluation/in_d_grader.py`, `scripts/grade_in_d.py`
- **Verification Gates:**
  1. `G-WO30-PLUMB`: Passed (quarantined $\ge 1$, active $= 0$, synthetic over-depth rejected, IN-D advanced to `MEASURED` in `logs/test_reports/personhood/in_d_latest.json`).
  2. `G-WO30-UTIL`: Passed (cost reduced on 3 of the 43 labeled Bucket C failure items, artifact committed at `logs/test_reports/wo30_utility_gate_report.json`).
  3. Static Gates: 24/24 passing (`test_static_gates.py`).
  4. Regression Suites: 62/62 passing (`tests/test_wo30_minimum_viable_engine.py`, `tests/test_v1357_*.py`).

