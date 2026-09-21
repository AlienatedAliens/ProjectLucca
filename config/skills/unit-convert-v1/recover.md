# Recovery Protocol for unit-convert-v1

- Entity extractor limitation: The heuristic router currently populates `app`, `file`, `url`, and `quoted` entities. Unit conversion math `expr` is not extracted in live turns.
- Fallback behavior: Under the entity-absent invariant, when `(entity-str "expr")` is empty, the plan branches to `(yield-to-core "convert: no expression" :need "expr")`, yielding control to the orchestrator rather than running a placeholder calculation. When `expr` is present (e.g. via `invoke_skill`), the plan executes `run_python`.
- Sandbox failure recovery: If Docker CE is unavailable, `run_python` returns a structured `policy_violation` ToolResult. The orchestrator catches this and triggers grounded fallback narration.
