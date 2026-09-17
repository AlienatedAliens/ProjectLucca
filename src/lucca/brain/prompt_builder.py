"""
Project Lucca — Prompt Builder
Spec 10 §4 (Prompt Section Order & KV-Cache Friendly Layout)
"""

from typing import Any

from lucca.core.schemas import MemoryHit

SYSTEM_PROMPT: str = (
    "You are Lucca, a local-first desktop companion. You are thoughtful, concise, and helpful. "
    "You communicate via natural voice speech. Keep responses conversational and direct "
    "(under 2-3 sentences unless explicitly asked for detail). Never read out long code "
    "blocks or URLs. You have sandboxed tools to interact with the desktop. "
    "Reply conversationally unless explicitly asked to perform a desktop action "
    "or launch an application."
)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch an approved application on the desktop",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "enum": ["calculator", "notepad", "terminal", "browser", "task_manager"],
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the user workspace",
            "parameters": {
                "type": "object",
                "properties": {
                    "rel_path": {"type": "string", "description": "Relative path under workspace"}
                },
                "required": ["rel_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file in the workspace",
            "parameters": {
                "type": "object",
                "properties": {
                    "rel_path": {"type": "string", "description": "Relative path under workspace"},
                    "content": {"type": "string", "description": "File text content"},
                },
                "required": ["rel_path", "content"],
            },
        },
    },
]


def build_messages(
    memories: list[MemoryHit] | None = None,
    history: list[dict[str, str]] | None = None,
    current_audio_b64: str | None = None,
    current_text: str | None = None,
) -> list[dict[str, Any]]:
    """
    Builds the messages array in strict Section Order (Spec 10 §4):
    1. System Prompt (static prefix cacheable)
    2. Persistent Memory Context
    3. Conversation History (last N turns)
    4. Current Turn (Audio or Text)
    """
    messages: list[dict[str, Any]] = []

    # 1. System Prompt
    system_content = SYSTEM_PROMPT

    # 2. Memories Block (appended to system content to keep prefix unified)
    if memories:
        mem_lines = ["\n\n[Persistent Memory Context]"]
        for m in memories:
            mem_lines.append(f"- {m.content}")
        system_content += "\n".join(mem_lines)

    messages.append({"role": "system", "content": system_content})

    # 3. Conversation History (last 6 exchanges)
    if history:
        for turn in history[-6:]:
            messages.append(turn)

    # 4. Current User Turn
    if current_audio_b64:
        content: list[dict[str, Any]] = [
            {
                "type": "input_audio",
                "input_audio": {"data": current_audio_b64, "format": "wav"},
            }
        ]
        if current_text:
            content.append({"type": "text", "text": current_text})
        messages.append({"role": "user", "content": content})
    elif current_text:
        messages.append({"role": "user", "content": current_text})

    return messages
