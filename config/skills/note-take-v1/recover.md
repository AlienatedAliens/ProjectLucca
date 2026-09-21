# Recovery Protocol for note-take-v1

- Entity extractor limitation: The heuristic router extracts file names, but note content is typically unquoted or informal and not extracted into `content` in live turns.
- Fallback behavior: Under the entity-absent invariant, when `(entity-str "content")` is empty, the plan branches to `(yield-to-core "note-take: no content" :need "content")`, allowing the LLM orchestrator to ask what should be noted or parse the utterance directly. When `content` is present, `note_write` saves it to `scratchpad.txt`.
- Substrate failure recovery: If the notes directory is unwritable or path traversal is detected, `note_write` returns a structured error without crashing.
