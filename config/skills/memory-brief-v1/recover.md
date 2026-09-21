# Recovery Protocol for memory-brief-v1

- Entity extractor limitation: The heuristic router extracts common entities, but specific memory queries may lack extracted `query` entities in live turns.
- Fallback behavior: Under the entity-absent invariant, when `(entity-str "query")` is empty, the plan branches to `(yield-to-core "memory-brief: no query" :need "query")`, yielding control to System 2 to request clarification or query parameters. When `query` is present, `memory_search` executes directly.
- Substrate failure recovery: If the SQLite memory store is locked or unavailable, `memory_search` returns a structured error or empty list, allowing the orchestrator to explain gracefully.
