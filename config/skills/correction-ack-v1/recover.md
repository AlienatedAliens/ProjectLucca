# Recovery Protocol for correction-ack-v1

- Yield control signal: Raises `SchemeYieldSignal` with `{reason: "operator correction", context: {salience: "high"}}`.
- Arbitration: Orchestrator captures the signal and initiates epistemic context update in neural System 2.
- Error recovery: Pure cognitive event signal; cannot fail external RPC or sandbox calls.
