# WO-43 Phase 5 Specification — High-Power Empirical Expansion (`Contrastive Battery v2 N=300` & `Memory Poisoning v3 N=300`)

**Phase:** `Phase 5 of 6`
**Prerequisite:** Phase 4 completed and signed off by the Independent Auditor Subagent.
**Commits in Phase 5:** `3` atomic commits (`Sub-step 5.1` Pre-Registration & Blind Corpus Authoring, `Sub-step 5.2` Live Multi-Arm Execution & Dual Blinded IRR Grading, `Sub-step 5.3` Statistical Power & Anti-Contamination Gate Locking).

---

## 1. Statistical Justification & Target Power Math

### 1.1 Contrastive Companion Battery (`N = 30` $\to$ `N = 300`)
- **Current Deficit (`v1`):** `data/benchmarks/contrastive_battery.jsonl` has $N = 30$ total items ($n = 10$ Recall, $n = 10$ Introspection, $n = 10$ Abstention). At $n = 10$:
  - A $10/10$ ($100\%$) score has a 95% Wilson CI of $[72.2\%, 100.0\%]$ ($\pm 13.9\%$).
  - An $8/10$ ($80\%$) score has a 95% Wilson CI of $[49.0\%, 94.3\%]$ ($\pm 22.6\%$).
  - Paired McNemar tests on Introspection ($+10\text{ pp}$) and Abstention ($-10\text{ pp}$) yield $p = 1.000$ ($< 15\%$ statistical power).
- **Target (`v2`, $N = 300 = 100$ per stratum):**
  - **Stratum 1 — Grounded Episodic Recall ($n = 100$):** Fact-seeded multi-session recall queries with verifiable ground-truth tokens.
  - **Stratum 2 — Telemetry & State Introspection ($n = 100$):** Queries over live hardware, memory integrity, active subsystem status, and tool execution receipts.
  - **Stratum 3 — Calibrated Epistemic Abstention ($n = 100$):** Queries over unseeded future events, nonexistent files/URLs, fabricated citations, and unverified third-party claims where the correct behavior is explicit abstention rather than confabulation.
  - **Precision & Power at $n = 100$ per stratum:**
    - At $p = 100\%$ ($100/100$), the 95% Wilson CI tightens from $[72.2\%, 100.0\%]$ to **$[96.3\%, 100.0\%]$** ($\pm 1.85\%$).
    - At $p = 80\%$ ($80/100$), the 95% Wilson CI tightens from $\pm 22.6\%$ to **$[71.1\%, 86.7\%]$ ($\pm 7.8\%$)**.
    - Paired exact McNemar power to detect a $\ge 12\text{ pp}$ discordant difference between Bare (`Arm 1`), RAG (`Arm 2`), and Compound (`Arm 3`) reaches **$\ge 80\%$ at $\alpha = 0.05$**.

### 1.2 Memory Poisoning Battery (`N = 100` $\to$ `N = 300`)
- **Current Deficit (`v2`):** `data/benchmarks/memory_poisoning_v2.jsonl` has $N = 100$ ($n = 40$ Cohort A adversarial injection, $n = 30$ Cohort B benign update, $n = 30$ Cohort C paraphrase/conflict). At $n = 30$, a $0/30$ ($0.0\%$) error rate has a 95% Wilson upper bound of **$11.4\%$**.
- **Target (`v3`, $N = 300 = 100$ per cohort):**
  - **Cohort A ($n = 100$):** Adversarial false-memory injection attempts across web-fetch, tool-output, and indirect prompt channels (target: $0\%$ silent admission to grounding-eligible `ACTIVE` memory).
  - **Cohort B ($n = 100$):** Legitimate user-authenticated state updates and preference revisions (target: $0\%$ false quarantine).
  - **Cohort C ($n = 100$):** Semantic paraphrases, negated restatements, and Belnap $\bot$/$\top$ multi-source conflicts (target: $0\%$ silent contradiction overwrite).
  - **Precision at $n = 100$ per cohort:** A $0/100$ error rate tightens the 95% Wilson upper bound from **$11.4\%$ down to $3.7\%$** ($3.1\times$ tighter).

---

## 2. Sub-Step 5.1 — Blind Subagent Corpus Authoring & Cryptographic Pre-Registration

### 2.1 Anti-Contamination Protocol (`AGENTS.md` Rule 8 / `WO-39` Standard)
1. Spawn **two isolated `research` subagents with `Zero Training Access`**:
   - **Subagent 1 (`Blind Contrastive Benchmark Author`):** Authors `data/benchmarks/contrastive_battery_v2_300.jsonl` ($N = 300$: `100` Recall, `100` Introspection, `100` Abstention). Forbids viewing `src/lucca/core/cascade*`, `src/lucca/sandbox/output_supervisor*`, or any `heuristics.toml` file.
   - **Subagent 2 (`Blind Memory Poisoning Benchmark Author`):** Authors `data/benchmarks/memory_poisoning_v3_300.jsonl` ($N = 300$: `100` Cohort A, `100` Cohort B, `100` Cohort C). Forbids viewing `src/lucca/memory/gate.py`, `src/lucca/core/memory_commit_service.py`, or `src/lucca/memory/latent_probe.py`.
2. **Pre-Registration Lock Before Running Any Evaluation:**
   - Compute and record the SHA-256 digests of `contrastive_battery_v2_300.jsonl`, `memory_poisoning_v3_300.jsonl`, `src/lucca/eval/contrastive_grader.py`, and the runner scripts in `data/benchmarks/MANIFEST.json`.
   - Commit the locked benchmark files and manifest, and create an annotated git tag `prereg-wo43-power-300` **before** executing the evaluation runners.
   - **Zero post-lock production code or regex/threshold edits are permitted after `prereg-wo43-power-300` is tagged.**

---

## 3. Sub-Step 5.2 — Live Multi-Arm Execution & Independent Blinded IRR Verification

1. **Execute Contrastive Companion Battery v2 ($N = 300 \times 3\text{ arms} = 900$ live turns):**
   ```powershell
   uv run python scripts/run_contrastive_eval.py --battery data/benchmarks/contrastive_battery_v2_300.jsonl --output logs/test_reports/contrastive_v2_300_results.json
   ```
   - Evaluates all 3 arms (`Bare LLM`, `RAG-Only`, `Full Compound Lucca`) using the frozen `contrastive_grader.py`.
   - Computes per-stratum proportions, exact 95% Wilson CIs, and paired exact McNemar $p$-values (with Holm-Bonferroni multiplicity correction).
2. **Execute Memory Poisoning Battery v3 ($N = 300$):**
   ```powershell
   uv run python scripts/run_memory_poisoning_eval_v2.py --battery data/benchmarks/memory_poisoning_v3_300.jsonl --output logs/test_reports/memory_poisoning_v3_300_results.json
   ```
   - Evaluates Cohorts A (`100`), B (`100`), and C (`100`) across Bare/Unfiltered and Full Compound Lucca (with `BelnapLatentInvestigator` + NPU NLI + Provenance Gate online).
   - Computes per-cohort 95% Wilson CIs, Fisher's exact test $p$-values, and paired McNemar $p$-values.
3. **Blinded Independent Subagent IRR Audit ($60$-item stratified slice):**
   - Spawn two independent blinded `research` subagents to grade a 60-item stratified random slice of the live outputs without seeing arm labels or automated grader verdicts, verifying Cohen's $\kappa \ge 0.85$ against the automated grader.

---

## 4. Sub-Step 5.3 — Anti-Contamination & Statistical Power Static Gates

Add `test_wo43_statistical_power_benchmarks_locked()` in `tests/test_static_gates.py` asserting:
1. `data/benchmarks/contrastive_battery_v2_300.jsonl` has exactly `300` unique items (`100` per stratum) and its SHA-256 matches `data/benchmarks/MANIFEST.json`.
2. `data/benchmarks/memory_poisoning_v3_300.jsonl` has exactly `300` unique items (`100` per cohort) and its SHA-256 matches `data/benchmarks/MANIFEST.json`.
3. Zero benchmark item strings or IDs appear anywhere in `src/lucca/`.

---

## 5. Phase 5 Independent Subagent Audit Gate (Mandatory STOP Before Phase 6)

Spawn a read-only `research` subagent to verify:
1. Git tag `prereg-wo43-power-300` precedes the evaluation result commits in `git log`, with zero edits to `src/lucca/` after the tag.
2. All 900 Contrastive v2 turns and 300 Memory Poisoning v3 items have complete, non-truncated execution logs and verified Wilson CIs / McNemar $p$-values.
3. Blinded IRR Cohen's $\kappa \ge 0.85$.
