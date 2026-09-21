# Backup & Alternative Triggers for self-health-v1

- Alternative trigger conditions: When transcript mentions "self health" or queries hardware/substrate health.
- Keywords: "health", "telemetry", "hardware", "cpu", "gpu", "vram", "metrics".
- Fallback path: If self_metrics fails, queries static capability manifest or asks System 2 to report operational state.
