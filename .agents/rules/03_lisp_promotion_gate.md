# Rule 03: Symbolic Rule Promotion & Regression Suite

1. **Quarantine Isolation:**
   - LLM-synthesized candidate rules must be placed in `quarantine_rules.json`.
   - Quarantined rules are evaluated in shadow mode only and cannot execute live mutations.

2. **The 5-Strike Qualification Rule:**
   - A candidate rule must succeed across $N \ge 5$ distinct interaction clusters with 0 failures before being eligible for promotion.
   - Distinctness requires: $\Delta t \ge 15\text{ min}$, or cosine query distance $\ge 0.25$, or distinct environment state hashes.

3. **Zero Regression Invariant:**
   - Prior to promoting any candidate rule to `active_rules.lisp`, the entire accumulated historical regression suite must execute.
   - Any regression immediately aborts the promotion.

4. **Instant Demotion:**
   - If an active rule encounters a single contradiction or runtime failure in production, it must be instantly demoted back to quarantine.
