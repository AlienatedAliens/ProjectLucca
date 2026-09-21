# Recovery Protocol for session-recap-v1

- Entity extractor limitation: Natural language requests for session recaps do not automatically extract query entities unless structured or quoted.
- Fallback behavior: Under the entity-absent invariant, when `(entity-str "query")` is empty, the plan branches to `(yield-to-core "session-recap: no query" :need "query")`, yielding to the LLM core to narrate the ongoing conversation. When `query` is present, `memory_search` queries the memory store.
- Substrate failure recovery: If memory store retrieval returns empty, the LLM core digests the current session turn history directly.
