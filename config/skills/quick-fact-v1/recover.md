# Recovery Protocol for quick-fact-v1

- Entity extractor limitation: The heuristic router extracts `app`, `file`, `url`, and `quoted` entities, but does not extract a dedicated `topic` entity.
- Fallback behavior: Under the entity-absent invariant, when `(entity-str "topic")` is empty, the plan branches to `(yield-to-core "fact: no topic" :need "topic")`, yielding control to the orchestrator rather than searching for generic placeholder keywords. When `topic` is provided (e.g. via `invoke_skill`), the plan invokes `search_web`.
- Search failure recovery: If web search fails or network is disconnected, `search_web` returns a graceful error result, which the orchestrator narrates without crashing.
