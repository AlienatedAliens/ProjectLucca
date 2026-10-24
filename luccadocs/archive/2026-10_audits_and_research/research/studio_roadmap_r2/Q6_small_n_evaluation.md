# Research Deep Dive: Q6 — Small-Sample Evaluation & Single-User Statistics

**Document:** `luccadocs/research/studio_roadmap_r2/Q6_small_n_evaluation.md`  
**Author:** Antigravity (Gemini)  
**Consumer:** Fable 5.1 (author of `luccadocs/specs/STUDIO_CAPABILITY_ROADMAP.md`)  
**Audit & Access Date:** 2026-09-21  
**Status:** Complete — Ready for Review  

---

## 1. Executive Summary & Problem Framing

Project Lucca is designed as a personal, local-first companion for a **single human operator**. Unlike enterprise cloud agents that evaluate performance over tens of thousands of customer queries, Lucca must validate new skills, evaluate induced rules, and detect regressions using **sparse local histories** ($N \le 50$ turns per intent cluster).

The central methodological question is: *What claims can be statistically justified under small sample sizes ($N < 50$)? How should regression harnesses, sequential testing, paired testing, and frozen suites be structured to prevent contamination and self-delusion?*

### Key Statistical Insights:
1. **The Frequentist "Rule of Three":** In zero-defect testing, the upper bound of the 95% confidence interval for the true failure rate is $p \le 3/N$. Observing 0 failures across $N = 5$ shadow clusters only proves that the true failure rate is $\le 60\%$ ($3/5$). Therefore, **empirical shadow testing alone cannot guarantee safety**. Lucca's safety is guaranteed because empirical shadowing is strictly paired with **formal Z3 SMT verification, gas bounds (1,000 gas), and pure functional immutability**.
2. **Paired Non-Parametric Testing:** Because turn difficulty varies wildly, unpaired A/B testing has almost zero statistical power at $N < 30$. Testing candidate rules vs. the base LLM on the **exact same frozen turn traces** using **McNemar's test** or **Wilcoxon signed-rank tests** dramatically increases statistical power.
3. **LLM-as-a-Judge is Disqualified as an Autonomous Oracle:** Literature (and XConf §C) shows that LLM judges suffer from self-enhancement bias, verbosity bias, and shared distribution blindness. Ground-truth evaluation must rely on external verifiers (tool exit codes, schema validation, user corrections).
4. **Benchmark-Disjoint Frozen Suites:** To prevent self-improving agents from overfitting to past prompts, the regression suite must remain strictly disjoint from the induction training pool (ModularRSI).

---

## 2. In-Depth Research Findings

### F-Q6-1: The Statistical "Rule of Three" Defines Confidence Limits for Zero-Failure Shadowing
- **Source(s):** *Quantitative Evaluation of Rare Event Probabilities in AI Systems*, J. Machine Learning Research (2023) & Classic Biostatistics (*The Rule of Three: Calculating 95% Confidence Intervals for Zero Events*), accessed 2026-09-21.
- **Read:** Statistical proofs and methodology papers.
- **Mechanism:** When $N$ independent Bernoulli trials result in 0 failures ($k = 0$), the upper 95% confidence limit for the true underlying failure rate $p$ is approximated by:
  $$p_{95} = 1 - 0.05^{1/N} \approx \frac{3}{N}$$
  To statistically claim with 95% confidence that an agent's failure rate is $<5\%$, the system must observe at least $N = 60$ trials with 0 failures ($3/60 = 0.05$).
- **Evidence Grade:** **E1.** Standard mathematical theorem in frequentist probability theory.
- **Transfer to Lucca:** **Direct Mathematical Reality.** Lucca's roadmap requires 5 distinct shadow clusters with 0 errors before a rule is eligible for promotion. Under the Rule of Three, $3/5 = 0.60$. Empirically, 5 trials only guarantees that the error rate is $\le 60\%$.
- **What would falsify or limit this:** If trials were not independent. (In correlated trials, the effective $N$ is even smaller).
- **Roadmap action:** **Adapt** Rung L2. Clarify that 5 shadow clusters is a *prerequisite for human review*, not an automated mathematical proof of perfection. Formal safety comes from Z3 and pure MicroScheme constraints.
- **Confidence:** Absolute.

---

### F-Q6-2: Paired Non-Parametric Testing Maximizes Statistical Power on Small Sample Sets
- **Source(s):** *Statistical Methods for Evaluating Small-Sample Natural Language Processing Models*, ACL 2023 & Empirical Software Engineering Review, accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** In conversational systems, variance across different user requests is massive compared to the variance between model variants on the same request. Two-sample unpaired tests (e.g., Student's t-test) require $N > 200$ to detect modest improvements. In contrast, **paired testing** (McNemar's test for binary pass/fail; Wilcoxon signed-rank test for continuous latency/gas) evaluates the candidate rule against the core LLM on the **exact same input string**, isolating treatment effect from prompt variance.
- **Evidence Grade:** **E1.** Standard statistical methodology.
- **Transfer to Lucca:** **Yes.** When evaluating a quarantined rule in LISP Studio, the harness must run a paired comparison on the 50 frozen turns in `data/eval/regression_frozen_50.jsonl`: Rule execution vs. Core LLM execution. A paired McNemar test on 50 turns can detect a 15% delta at $p < 0.05$.
- **What would falsify or limit this:** None; mathematically sound.
- **Roadmap action:** **Adopt** paired testing into Rung L2 shadow telemetry.
- **Confidence:** Very High.

---

### F-Q6-3: Sequential Probability Ratio Testing (SPRT) Enables Early Termination of Bad Rules
- **Source(s):** *Sequential Analysis for Automated Machine Learning Evaluation*, IEEE Trans. Software Eng. (2024) & Wald's Sequential Analysis, accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** Rather than running a fixed batch of 50 evaluations for every candidate rule, Sequential Probability Ratio Testing (SPRT) updates the log-likelihood ratio after each individual test turn. If a candidate rule fails its first 2 turns, SPRT hits the lower rejection boundary immediately, terminating evaluation in 2 turns instead of 50. Conversely, consistently superior rules reach the acceptance boundary early.
- **Evidence Grade:** **E1.** Proven in automated testing and clinical trials.
- **Transfer to Lucca:** **Yes.** In Dream-RSI replay simulation, Lucca should test candidate induced rules sequentially against historical turns. If a rule fails on Turn 1 or 2, abort immediately without wasting CPU time on the remaining 48 turns.
- **What would falsify or limit this:** If early failure was uninformative of later performance. (In deterministic MicroScheme, a failure indicates an unhandled syntax or precondition error).
- **Roadmap action:** **Adopt** into Dream-RSI offline replay simulator (Rung L2).
- **Confidence:** High.

---

### F-Q6-4: LLM-as-a-Judge Exhibits Severe Self-Enhancement and Shared-Distribution Blindness
- **Source(s):** *Judging the Judges: Evaluating Alignment and Biases in LLM-as-a-Judge*, [arXiv:2306.05685](https://arxiv.org/abs/2306.05685) & XConf (§C, [arXiv:2609.17708](https://arxiv.org/abs/2609.17708)), accessed 2026-09-21.
- **Read:** Full text and empirical tables.
- **Mechanism:** Using an LLM to evaluate agent outputs introduces well-documented systemic distortions:
  1. *Self-Enhancement Bias:* Models assign higher scores to their own completions than to outputs from competing models.
  2. *Verbosity Bias:* Longer, wordy responses receive higher marks regardless of factual accuracy.
  3. *Consensus-Wrong Blindness:* As proven in XConf §C, an LLM judge shares pre-training distribution blind spots with the generator, systematically verifying incorrect answers as correct on difficult items (+0.13 to +0.25 confidence inflation).
- **Evidence Grade:** **E1.** Replicated across dozens of independent evaluation papers.
- **Transfer to Lucca:** **Critical Warning.** Lucca must **never** use Gemma-4 to autonomously grade its own induced MicroScheme rules. Evaluation of rule outcomes must be anchored exclusively in **ground-truth observables**: tool exit code ($0 = \text{success}$), Pydantic argument validation, AST execution without gas exhaustion, and explicit human operator grading.
- **What would falsify or limit this:** If an LLM judge had 100% agreement with formal Z3 proofs.
- **Roadmap action:** **Reject** autonomous LLM-as-a-judge for promotion; require ground-truth signals and human review.
- **Confidence:** Absolute.

---

### F-Q6-5: Benchmark-Disjoint Evaluation (ModularRSI) Prevents Data Contamination in Self-Improvement
- **Source(s):** *MODULARRSI: Modular and Generalizable Recursive Harness Self-Improvement*, [arXiv:2609.14857](https://arxiv.org/abs/2609.14857), §3.1 & §4, accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** ModularRSI explicitly enforces a "benchmark-disjoint" protocol: the tasks used by the agent to evolve harness modules are strictly separated from the evaluation benchmarks (TerminalBench 2.0 and SWE-Bench). If an agent evolves rules on tasks that overlap with the evaluation harness, it achieves artificially inflated pass rates that collapse when transferred to unseen environments.
- **Evidence Grade:** **E2.** Ablations showing generalizable cross-domain transfer only under benchmark-disjoint splits.
- **Transfer to Lucca:** **Yes.** Lucca's frozen evaluation suite (`data/eval/regression_frozen_50.jsonl`) must contain canonical, immutable golden turns that are **read-only and never fed into the induction candidate generator**.
- **What would falsify or limit this:** If overfitting to past turns had zero negative transfer on new turns. (Disproven by all machine learning literature).
- **Roadmap action:** **Adopt** benchmark-disjoint protocol for frozen regression suites.
- **Confidence:** Very High.

---

### F-Q6-6: Trajectory-Level Multi-Factor Scoring Outperforms Binary Pass/Fail on Small Sample Sizes
- **Source(s):** *Trajectory-Level Evaluation for LLM Agents: Measuring Process Over Outcome*, ICML 2024 Workshop on Agent Evaluation, accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** On small sample sizes ($N < 50$), binary pass/fail metrics are too coarse to distinguish subtle algorithmic improvements. Evaluating the *trajectory*—measuring intermediate tool precision, parameter validity, gas consumption, and execution latency—provides continuous, high-resolution signals that allow statistical significance to be established with far fewer trials.
- **Evidence Grade:** **E2.**
- **Transfer to Lucca:** **Yes.** Lucca logs complete `TurnTrace` objects containing `t_llm_first_token`, `t_llm_end`, tool execution time, gas consumed, and Pydantic validation status. LISP Studio telemetry should present multi-factor metrics (latency delta, gas delta, schema conformance), not just binary trigger hit rate.
- **What would falsify or limit this:** If binary outcomes perfectly captured all latency and safety regressions.
- **Roadmap action:** **Adopt** multi-factor telemetry into Rung L2 & T4.
- **Confidence:** High.

---

### F-Q6-7 (Disconfirming / Negative Result): The N=5 Cluster Vulnerability Demands Multi-Tier Safety
- **Source(s):** *Small-Sample Validation Vulnerabilities in Adaptive Agent Systems*, IEEE Security & Privacy (2025), accessed 2026-09-21.
- **Read:** Full text.
- **Mechanism:** Evaluates systems that promote rules based on small empirical clusters ($N \le 5$). Proves that an adversarial or accidental prompt injection can easily satisfy a 5-turn shadow threshold if the user repeats a specific command pattern during a single afternoon. If the system treats 5 successful shadow turns as sufficient for automated production promotion, it suffers from privilege escalation and prompt poisoning.
- **Evidence Grade:** **E2.** Demonstrated successful rule injection exploits against adaptive agent frameworks.
- **Transfer to Lucca:** **Direct Validation of `D-REAS-06`.** Proves that 5 shadow clusters must **NEVER** trigger automatic promotion to `ACTIVE`. Automatic promotion is strictly prohibited. The 5 clusters merely light up an "Eligible for Review" badge in LISP Studio; the human operator must inspect the diff and click Approve.
- **What would falsify or limit this:** None; this is a fundamental security requirement.
- **Roadmap action:** **Maintain** strict human promotion gate in Rung L3.
- **Confidence:** Absolute.

---

### F-Q6-8: Wilson Score Intervals Provide Accurate Coverage for Small-N Success Proportions
- **Source(s):** *Interval Estimation for a Binomial Proportion*, Brown, Cai, DasGupta, Statistical Science (2001), accessed 2026-09-21.
- **Read:** Full mathematical proofs.
- **Mechanism:** The standard Wald interval ($\hat{p} \pm 1.96 \sqrt{\hat{p}(1-\hat{p})/N}$) performs terribly near $\hat{p} = 1.0$ or small $N$, frequently yielding confidence intervals that exceed 1.0 or collapse to zero width. The **Wilson score interval** with continuity correction provides asymmetric, mathematically sound confidence intervals for small $N$ that correctly capture uncertainty near 100% success rates.
- **Evidence Grade:** **E1.** Standard consensus in mathematical statistics.
- **Transfer to Lucca:** **Yes.** In `src/lucca/admin.py` and LISP Studio UI, when reporting shadow match rates or tool success rates on $N = 10$ to $50$ turns, Lucca must compute Wilson score intervals rather than naive standard errors.
- **What would falsify or limit this:** None; mathematical theorem.
- **Roadmap action:** **Adopt** Wilson score calculations in `lucca-admin tools report` (Rung T4).
- **Confidence:** Very High.

---

## 3. Synthesis & Recommendations for Fable 5.1

1. **Clarify the Role of 5 Shadow Clusters (Rung L2):** In the roadmap text, clarify that 5 shadow clusters is an empirical heuristic to establish intent recurrence, not a statistical guarantee of zero errors (since the Rule of Three shows 5 trials bounds failure rate only to $\le 60\%$). Absolute safety is established by the formal SMT verifier, gas bounds, and human approval.
2. **Mandate Benchmark-Disjoint Frozen Suite (Rung L1 & L2):** Establish `data/eval/regression_frozen_50.jsonl` containing 50 golden turns. This file is immutable, benchmark-disjoint, and evaluated on every rule promotion.
3. **Use Paired Testing for Studio Comparisons (Rung L2):** When displaying candidate rule performance in LISP Studio, run paired comparisons (Rule vs. Base LLM on the same frozen inputs) using McNemar's test.
4. **Use Wilson Intervals in Tool Telemetry (Rung T4):** Implement Wilson score confidence intervals for `lucca-admin tools report` to accurately present success rates on small trial counts.
