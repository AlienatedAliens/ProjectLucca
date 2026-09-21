# Recovery Protocol for resource-report-v1

- Execution semantics: `self_metrics` executes natively on Windows to poll CPU, RAM, and GPU sensors without mutating state.
- Fallback behavior: If any telemetry sensor is unavailable, partial metrics are returned with error indications.
- LLM narration: The orchestrator passes structured telemetry to the core LLM for conversational summarization.
