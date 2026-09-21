# Recovery Protocol for self-health-v1

- Execution semantics: `self_metrics` retrieves hardware telemetry across GPU, CPU, and RAM without modifying state.
- Fallback behavior: If `nvidia-smi` or psutil query experiences temporary latency or error, `self_metrics` returns fallback metrics or error dictionary.
- LLM narration: The orchestrator passes structured telemetry to the LLM core for natural grounded narration.
