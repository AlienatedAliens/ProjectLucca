# Recovery Protocol for sys-specs-v1

- Security caveat: Output from `sys_info` carries the `TOOL_CONTENT_UNTRUSTED` provenance stamp and cannot be directly written into memory without explicit user approval.
- Execution semantics: `sys_info` executes read-only inspection of host OS platform and processes.
- LLM narration: The orchestrator passes structured specs to the LLM core for factual narration.
