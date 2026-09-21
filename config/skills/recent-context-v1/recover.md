# Recovery Protocol for recent-context-v1

- Entity extractor limitation: The heuristic router does not extract dedicated topic entities from arbitrary natural language without explicit quoted or pattern support.
- Fallback behavior: Under the entity-absent invariant, when `(entity-str "topic")` is empty, the plan branches to `(yield-to-core "recent-context: no topic" :need "topic")`, yielding to the LLM core to prompt the user. When `topic` is present, `memory_search` queries the memory store.
- Substrate failure recovery: If the SQLite memory store is locked or empty, `memory_search` returns gracefully, allowing the companion to state that no relevant recent context was found.
