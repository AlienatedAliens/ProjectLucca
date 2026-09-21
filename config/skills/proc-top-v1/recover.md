# Recovery Protocol for proc-top-v1

- Security caveat: Output from `sys_info` carries the `TOOL_CONTENT_UNTRUSTED` provenance stamp. Malicious process names cannot be committed to long-term memory.
- Execution semantics: `sys_info` executes read-only process listing via psutil.
- LLM narration: The orchestrator passes structured process information to the LLM core for concise spoken or written summary.
