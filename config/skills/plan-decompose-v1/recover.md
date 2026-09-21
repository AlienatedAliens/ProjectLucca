# Recovery Protocol for plan-decompose-v1

- Yield control signal: Raises `SchemeYieldSignal` carrying `{reason: "multi-step task", context: {mode: "plan"}}`.
- Arbitration: Orchestrator captures the signal, logs event, and routes prompt into System 2 deliberative synthesis.
- Error recovery: If System 2 is unavailable, fallback reflex handler provides canned acknowledgment.
