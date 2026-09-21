# Recovery Protocol for calc-eval-v1

- Entity extractor limitation: The heuristic router currently populates `app`, `file`, `url`, and `quoted` entities. Dedicated mathematical entity `expr` is not extracted in live turns.
- Fallback behavior: Under the entity-absent invariant, when `(entity-str "expr")` is empty, the plan branches to `(yield-to-core "calc: no expression" :need "expr")`, yielding control to the orchestrator to avoid confabulating answers. When `expr` is present (e.g. via `invoke_skill`), the plan executes `run_python`.
- Sandbox failure recovery: If Docker CE container isolation is offline, `run_python` returns a structured `policy_violation` ToolResult rather than crashing. The orchestrator catches this and prompts System 2 narration.
