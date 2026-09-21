"""
Project Lucca — Streaming Tool-Call Demultiplexer
Spec 08 §1, §2
"""

import json
import re
import uuid

from lucca.core.schemas import (
    LLMEvent,
    TokenDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
)

INLINE_TOOL_PREFIX_REGEX = re.compile(r"^\s*(?:<\|python_tag\|>|\[TOOL_CALLS\]|\[|\{)")


class ToolCallDemux:
    """
    Demultiplexes LLMEvent streams into pure spoken text deltas and structured ToolCallEnd events.
    Catches inline JSON tool calls emitted in content deltas when models bypass structured output.
    """

    def __init__(self, speak_code: bool = False) -> None:
        self.speak_code = speak_code
        self._buffer: list[str] = []
        self._buffered_len = 0
        self._suspected_tool_call = False
        self._resolved_tool_call = False
        self._in_code_fence = False
        self._code_omitted_spoken = False
        self._total_chars_seen = 0

    def feed(self, event: LLMEvent) -> list[LLMEvent]:
        # Pass structured tool call events straight through
        if isinstance(event, (ToolCallStart, ToolCallDelta, ToolCallEnd)):
            return [event]

        if not isinstance(event, TokenDelta):
            return [event]

        delta = event.delta
        out_events: list[LLMEvent] = []

        # Check for suspected inline tool call at stream start (within first 24 chars of the reply)
        if (
            self._total_chars_seen <= 24
            and not self._suspected_tool_call
            and not self._resolved_tool_call
        ):
            sample = ("".join(self._buffer) + delta).lstrip()
            if sample and (
                sample[0] in ("{", "[")
                or sample.startswith("<|python_tag|>")
                or sample.startswith("[TOOL_CALLS]")
            ):
                self._suspected_tool_call = True

        self._total_chars_seen += len(delta)

        if self._suspected_tool_call:
            self._buffer.append(delta)
            self._buffered_len += len(delta)
            buffered_text = "".join(self._buffer)

            # Try parsing JSON if we see matching braces/brackets or length threshold
            cleaned = (
                buffered_text.replace("<|python_tag|>", "")
                .replace("[TOOL_CALLS]", "")
                .replace("[/TOOL_CALLS]", "")
                .strip()
            )
            if cleaned.startswith("{") and cleaned.endswith("}"):
                try:
                    obj = json.loads(cleaned)
                    if (
                        isinstance(obj, dict)
                        and "name" in obj
                        and ("parameters" in obj or "arguments" in obj)
                    ):
                        tool_name = str(obj["name"])
                        args = obj.get("parameters") or obj.get("arguments") or {}
                        if not isinstance(args, dict):
                            args = {}
                        call = ToolCall(
                            tool=tool_name,
                            args=args,
                            call_id=f"inline-{uuid.uuid4().hex[:8]}",
                        )
                        self._suspected_tool_call = False
                        self._resolved_tool_call = True
                        self._buffer.clear()
                        self._buffered_len = 0
                        return [ToolCallEnd(call=call)]
                except json.JSONDecodeError:
                    pass
            elif cleaned.startswith("[") and cleaned.endswith("]"):
                try:
                    obj_list = json.loads(cleaned)
                    if isinstance(obj_list, list) and len(obj_list) > 0:
                        calls: list[ToolCallEnd] = []
                        for item in obj_list:
                            if isinstance(item, dict) and "name" in item:
                                tool_name = str(item["name"])
                                args = item.get("parameters") or item.get("arguments") or {}
                                if not isinstance(args, dict):
                                    args = {}
                                call = ToolCall(
                                    tool=tool_name,
                                    args=args,
                                    call_id=f"inline-{uuid.uuid4().hex[:8]}",
                                )
                                calls.append(ToolCallEnd(call=call))
                        if calls:
                            self._suspected_tool_call = False
                            self._resolved_tool_call = True
                            self._buffer.clear()
                            self._buffered_len = 0
                            return calls
                except json.JSONDecodeError:
                    pass

            if self._buffered_len > 4096:
                # Give up: exceeded 4KB buffer without valid JSON, flush buffer as text
                self._suspected_tool_call = False
                for chunk in self._buffer:
                    evs = self._process_text_delta(chunk)
                    out_events.extend(evs)
                self._buffer.clear()
                self._buffered_len = 0
            return out_events

        return self._process_text_delta(delta)

    def _process_text_delta(self, text: str) -> list[LLMEvent]:
        # Handle code fences ```
        if "```" in text:
            parts = text.split("```")
            out: list[LLMEvent] = []
            for idx, part in enumerate(parts):
                if idx > 0:
                    self._in_code_fence = not self._in_code_fence
                    if self._in_code_fence:
                        if not self.speak_code and not self._code_omitted_spoken:
                            out.append(TokenDelta(delta=" code block omitted. "))
                            self._code_omitted_spoken = True
                    else:
                        self._code_omitted_spoken = False
                if not self._in_code_fence and part:
                    out.append(TokenDelta(delta=part))
            return out

        if self._in_code_fence and not self.speak_code:
            return []

        return [TokenDelta(delta=text)]

    def flush(self) -> list[LLMEvent]:
        out: list[LLMEvent] = []
        if self._buffer:
            buffered_text = "".join(self._buffer)
            cleaned = (
                buffered_text.replace("<|python_tag|>", "")
                .replace("[TOOL_CALLS]", "")
                .replace("[/TOOL_CALLS]", "")
                .strip()
            )
            if cleaned.startswith("{") and cleaned.endswith("}"):
                try:
                    obj = json.loads(cleaned)
                    if isinstance(obj, dict) and "name" in obj:
                        call = ToolCall(
                            tool=str(obj["name"]),
                            args=obj.get("parameters") or obj.get("arguments") or {},
                            call_id=f"inline-{uuid.uuid4().hex[:8]}",
                        )
                        self._buffer.clear()
                        return [ToolCallEnd(call=call)]
                except json.JSONDecodeError:
                    pass
            elif cleaned.startswith("[") and cleaned.endswith("]"):
                try:
                    obj_list = json.loads(cleaned)
                    if (
                        isinstance(obj_list, list)
                        and len(obj_list) > 0
                        and isinstance(obj_list[0], dict)
                    ):
                        first_call = obj_list[0]
                        if "name" in first_call:
                            call_args = (
                                first_call.get("parameters") or first_call.get("arguments") or {}
                            )
                            call = ToolCall(
                                tool=str(first_call["name"]),
                                args=call_args,
                                call_id=f"inline-{uuid.uuid4().hex[:8]}",
                            )
                            self._buffer.clear()
                            return [ToolCallEnd(call=call)]
                except json.JSONDecodeError:
                    pass

            for chunk in self._buffer:
                out.extend(self._process_text_delta(chunk))
            self._buffer.clear()
        return out
