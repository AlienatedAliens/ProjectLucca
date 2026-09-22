"""
Project Lucca — Streaming Tool-Call Demultiplexer
Spec 08 §1, §2
"""

import json
import re
import uuid

from pydantic import JsonValue

from lucca.core.schemas import (
    LLMEvent,
    TokenDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
)

INLINE_TOOL_PREFIX_REGEX = re.compile(r"^\s*(?:<\|python_tag\|>|\[TOOL_CALLS\]|\[|\{|<function=)")

# Qwen/Harmony-style XML tool calls (e.g. Ternary-Bonsai 2):
#   <function=run_python>
#   <parameter=code>print("hi")</parameter>
#   </function>
FUNCTION_TAG_REGEX = re.compile(r"<function=(\w+)>\s*(.*?)\s*</function>", re.DOTALL)
PARAMETER_TAG_REGEX = re.compile(r"<parameter=(\w+)>\s*(.*?)\s*</parameter>", re.DOTALL)

# Gemma malformed-args sentinel (WO-9 A6 / F-WO8-26): the model sometimes
# emits query:<|"|>Sean<|"|> instead of JSON. The sentinel is stripped before
# lenient key:value / key=value parsing.
GEMMA_ARG_SENTINEL_REGEX = re.compile(r'<\|"\|>')

# Any unresolved tool markup that must never be spoken as text.
TOOL_MARKUP_REGEX = re.compile(
    r"<\|tool_call|<tool_call\|>|<function=|<\|python_tag\|>|\[TOOL_CALLS\]"
)


def _parse_lenient_args(raw: str) -> dict[str, JsonValue] | None:
    """Lenient parser for malformed Gemma tool-call args (WO-9 A6).

    Handles e.g. ``query:<|"|>Sean<|"|>`` — strips <|"|> sentinels, then
    accepts strict JSON or key:value / key=value pairs separated by commas
    or newlines. Returns None when nothing parseable remains.
    """
    cleaned = GEMMA_ARG_SENTINEL_REGEX.sub("", raw).strip()
    # Strip enclosing brace characters left over from the malformed call body
    cleaned = cleaned.strip("{}").strip()
    if not cleaned:
        return None
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    args: dict[str, JsonValue] = {}
    for pair in re.split(r"[,\n]+", cleaned):
        if ":" in pair:
            key, _, value = pair.partition(":")
        elif "=" in pair:
            key, _, value = pair.partition("=")
        else:
            continue
        key = key.strip().strip("'\"")
        value = value.strip().strip("'\"")
        if key:
            args[key] = value
    return args or None


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
        self._function_tag_buffering = False

    def _parse_function_tag(self, text: str) -> ToolCall | None:
        """Parses a closed <function=...>...</function> block into a ToolCall."""
        m = FUNCTION_TAG_REGEX.search(text)
        if not m:
            return None
        tool_name = m.group(1)
        args: dict[str, JsonValue] = {}
        for pm in PARAMETER_TAG_REGEX.finditer(m.group(2)):
            key = pm.group(1)
            raw_val = pm.group(2)
            try:
                args[key] = json.loads(raw_val)
            except json.JSONDecodeError:
                args[key] = raw_val
        return ToolCall(tool=tool_name, args=args, call_id=f"inline-{uuid.uuid4().hex[:8]}")

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
                or sample.startswith("<|tool_call")
            ):
                self._suspected_tool_call = True

        self._total_chars_seen += len(delta)

        # Qwen/Harmony-style <function=...> blocks can appear mid-stream after
        # narration text (Bonsai 2 template). Buffer until the closing tag.
        if self._function_tag_buffering or "<function=" in delta:
            self._function_tag_buffering = True
            self._buffer.append(delta)
            self._buffered_len += len(delta)
            buffered_text = "".join(self._buffer)
            if "</function>" in buffered_text:
                call = self._parse_function_tag(buffered_text)
                self._buffer.clear()
                self._buffered_len = 0
                self._function_tag_buffering = False
                if call is not None:
                    self._resolved_tool_call = True
                    return [ToolCallEnd(call=call)]
                # Malformed block: flush as text
                for chunk in self._buffer:
                    out_events.extend(self._process_text_delta(chunk))
                self._buffer.clear()
                self._buffered_len = 0
                self._function_tag_buffering = False
                return out_events
            if self._buffered_len > 4096:
                self._function_tag_buffering = False
                for chunk in self._buffer:
                    out_events.extend(self._process_text_delta(chunk))
                self._buffer.clear()
                self._buffered_len = 0
            return out_events

        if self._suspected_tool_call:
            self._buffer.append(delta)
            self._buffered_len += len(delta)
            buffered_text = "".join(self._buffer)

            # Try parsing Gemma native <|tool_call>call:tool_name{args}<tool_call|>
            if "<|tool_call" in buffered_text:
                m = re.search(
                    r"<\|tool_call\|?>call:(\w+)\s*(\{.*?\})(?:<tool_call\|>|<\|tool_call\|?>)?",
                    buffered_text,
                    re.DOTALL,
                )
                if m:
                    tool_name = m.group(1)
                    raw_args_str = m.group(2)
                    try:
                        raw_args = json.loads(raw_args_str)
                        parsed: dict[str, JsonValue] | None = (
                            raw_args if isinstance(raw_args, dict) else None
                        )
                    except json.JSONDecodeError:
                        # WO-9 A6: lenient fallback for malformed args such as
                        # query:<|"|>Sean<|"|> (sentinel-wrapped key:value).
                        parsed = _parse_lenient_args(raw_args_str)
                    if parsed is not None:
                        call = ToolCall(
                            tool=tool_name,
                            args=parsed,
                            call_id=f"inline-{uuid.uuid4().hex[:8]}",
                        )
                        self._suspected_tool_call = False
                        self._resolved_tool_call = True
                        self._buffer.clear()
                        self._buffered_len = 0
                        return [ToolCallEnd(call=call)]

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
                # Give up: exceeded 4KB buffer without valid JSON. Never speak
                # unresolved tool markup (WO-9 A6): drop it instead.
                self._suspected_tool_call = False
                if not TOOL_MARKUP_REGEX.search("".join(self._buffer)):
                    for chunk in self._buffer:
                        evs = self._process_text_delta(chunk)
                        out_events.extend(evs)
                self._buffer.clear()
                self._buffered_len = 0
            return out_events

        # WO-9 A6: mid-stream tool-call detection. Gemma sometimes narrates
        # first and emits <|tool_call>... afterwards; the old first-24-chars
        # window leaked the markup as speech. Speak any text before the
        # marker, then buffer the call.
        if (
            not self._suspected_tool_call
            and not self._function_tag_buffering
            and "<|tool_call" in delta
        ):
            idx = delta.index("<|tool_call")
            pre_text = delta[:idx]
            if pre_text:
                out_events.extend(self._process_text_delta(pre_text))
            self._suspected_tool_call = True
            self._buffer.append(delta[idx:])
            self._buffered_len += len(delta) - idx
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

            # WO-9 A6: mid-stream Gemma calls often terminate at flush; try the
            # native <|tool_call> parse (with lenient args fallback) first.
            gemma_m = re.search(
                r"<\|tool_call\|?>call:(\w+)\s*(\{.*?\})(?:<tool_call\|>|<\|tool_call\|?>)?",
                buffered_text,
                re.DOTALL,
            )
            if gemma_m:
                try:
                    raw_args = json.loads(gemma_m.group(2))
                    gemma_parsed: dict[str, JsonValue] | None = (
                        raw_args if isinstance(raw_args, dict) else None
                    )
                except json.JSONDecodeError:
                    gemma_parsed = _parse_lenient_args(gemma_m.group(2))
                if gemma_parsed is not None:
                    call = ToolCall(
                        tool=gemma_m.group(1),
                        args=gemma_parsed,
                        call_id=f"inline-{uuid.uuid4().hex[:8]}",
                    )
                    self._buffer.clear()
                    self._buffered_len = 0
                    self._suspected_tool_call = False
                    return [ToolCallEnd(call=call)]

            # WO-9 A6: never speak unresolved tool markup on flush — drop it.
            if TOOL_MARKUP_REGEX.search(buffered_text):
                self._buffer.clear()
                self._buffered_len = 0
                self._suspected_tool_call = False
                return out

            for chunk in self._buffer:
                out.extend(self._process_text_delta(chunk))
            self._buffer.clear()
        return out
