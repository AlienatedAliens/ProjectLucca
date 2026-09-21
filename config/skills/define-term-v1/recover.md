# Recovery Protocol for define-term-v1

- Entity extractor limitation: The heuristic router extracts `app`, `file`, `url`, and `quoted` entities, but does not extract a dedicated `term` entity.
- Fallback behavior: Under the entity-absent invariant, when `(entity-str "term")` is empty, the plan branches to `(yield-to-core "define: no term" :need "term")`, yielding control to the orchestrator rather than searching for generic placeholder keywords. When `term` is provided (e.g. via `invoke_skill`), the plan executes `search_web`.
- Search failure recovery: If web search fails or network is disconnected, `search_web` returns a graceful error result, which the orchestrator narrates without crashing.
