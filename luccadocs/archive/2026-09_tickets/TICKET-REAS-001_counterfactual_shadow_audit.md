# TICKET-REAS-001: 5% Stochastic Counterfactual LLM Shadow-Sampling for Active Rules

> [!NOTE]
> **RESOLUTION & ARCHIVE (September 20, 2026)**  
> Resolved and superseded by the implementation of `RuleLifecycleManager` shadow evaluation (`evaluate(mode="shadow")`), Single-Strike Demotion (`D-AUD-12`), Autonomous Rule Induction quarantine isolation (`D-REAS-06`), and E-Graph Macro Synthesis (`D-REAS-08`). Promoted rules operate under a strict zero-failure policy; any execution error immediately demotes the rule back to quarantine.

**Status:** **Resolved & Archived**  
**Priority:** High (Safety & Drift Prevention)  
**Component:** `src/lucca/core/orchestrator.py`, `src/lucca/reasoning/lifecycle.py`, `src/lucca/router/labeler.py`  
**Related Findings:** F-REAS-003, F-DRIFT-001  

---

## 1. Problem Statement

When an `ACTIVE` MicroScheme rule matches a user request, `Orchestrator._on_user_text` executes the rule's plan immediately and issues an early `return` (`src/lucca/core/orchestrator.py:755-773`). This bypasses LLM inference entirely, delivering $<1\text{ms}$ execution latency.

However, if an active rule becomes **confidently wrong without crashing** (e.g. user intent shifts, subtle phrasing differences cause unintended matching, or context changes):
- The rule executes cleanly (`matched=True`, `errored=False`).
- Zero failure counters are incremented.
- The rule never fails regression cases (since regression cases only evaluate historical snapshots).
- The system remains silently divergent until the user notices and explicitly says "cancel" or "stop doing that".

---

## 2. Proposed Architecture & Solution

Implement a background **5% Stochastic Counterfactual Audit**:

```mermaid
flowchart TD
    Turn["User Turn Input"] --> RuleCheck{"Active Rule Matched?"}
    RuleCheck -->|No| LLM["Standard LLM Dispatch"]
    RuleCheck -->|Yes| ExecFast["Execute Rule Plan Fast-Path (<1ms)"]
    ExecFast --> SampleCheck{"Sample p < 0.05?"}
    SampleCheck -->|No (95%)| Finish["Done (Sub-ms Turn)"]
    SampleCheck -->|Yes (5%)| BgThread["Async Background Worker"]
    BgThread --> ShadowLLM["Invoke LLM Stream in Shadow Mode"]
    ShadowLLM --> DivergeCheck{"LLM Plan matches Rule Plan?"}
    DivergeCheck -->|Yes| AuditPass["Log Decision: RULE_AGREED"]
    DivergeCheck -->|No| DivergeAlert["Record DIVERGENCE_DETECTED in decision_labels"]
    DivergeAlert --> DemoteCheck{"Divergence Count >= 3?"}
    DemoteCheck -->|Yes| Demote["Auto-demote Rule to PENDING_APPROVAL for Human Review"]
```

### Key Technical Details
1. **Zero Latency Impact on User**: The primary turn response is dispatched to the user immediately upon rule evaluation. The counterfactual LLM call runs completely asynchronously in a detached background daemon worker.
2. **Telemetry & Audit Records**:
   - Background execution records `decisions.executed_path = "RULE_SHADOW_AUDIT"`.
   - Divergence events are logged to SQLite table `decision_labels` with `label = "DIVERGENT"` and `reason = "counterfactual_plan_mismatch"`.
3. **Automatic Safeguard**:
   - If a rule accumulates $\ge 3$ divergent shadow evaluations within a 7-day rolling window, the rule engine transitions the rule from `ACTIVE` $\to$ `PENDING_APPROVAL`.
   - Telemetry notifies the human operator via `lucca-admin rules list` that re-approval is required.

---

## 3. Acceptance Criteria

- [ ] Fast-path rule execution maintains $\le 1\text{ms}$ latency; background worker does not block the active turn thread.
- [ ] Random seed / probability sampling honors configured rate (`0.05` default in `config/system.toml`).
- [ ] Divergent plans are recorded in SQLite `decision_labels`.
- [ ] Cumulative divergence triggers automatic transition to `PENDING_APPROVAL`.
- [ ] Tier 2 test verifies that divergent shadow execution does not alter active speech playback.
