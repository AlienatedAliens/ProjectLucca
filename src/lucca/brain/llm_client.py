"""
Project Lucca — LLM Client & Streaming Demuxer
Spec 02 (SpeechLLMPort), Spec 08, ADR-001
"""

import json
import os
import re
import threading
import uuid
from collections.abc import Generator
from dataclasses import dataclass

import httpx
import structlog
from pydantic import JsonValue

from lucca.brain.prompt_builder import TOOL_DEFINITIONS, build_messages
from lucca.brain.toolcall_demux import ToolCallDemux
from lucca.core.config import LLMSettings, get_config
from lucca.core.exceptions import LLMUnavailable
from lucca.core.schemas import (
    ChatMessage,
    Done,
    LLMEvent,
    LLMUsage,
    MemoryHit,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
    ToolDefinition,
)
from lucca.core.trace import now_ns

logger = structlog.get_logger(__name__)


@dataclass
class _StreamState:
    client: httpx.Client
    aborted: bool
    trace_id: str


def build_chat_template_kwargs(
    llm_cfg: LLMSettings,
    enable_thinking: bool | None = None,
) -> dict[str, JsonValue]:
    """
    Builds the llama-server chat_template_kwargs from config only or per-turn override.
    enable_thinking is forwarded when set (reasoning-model templates honour
    chat_template_kwargs.enable_thinking; other templates ignore it).
    None means "omit, let the template decide".
    """
    kwargs: dict[str, JsonValue] = {"tools_in_user_message": False}
    eff_thinking = enable_thinking if enable_thinking is not None else llm_cfg.enable_thinking
    if eff_thinking is not None:
        kwargs["enable_thinking"] = eff_thinking
    return kwargs


def _parse_and_repair_tool_args(raw: str, tool_name: str = "") -> dict[str, JsonValue]:
    """
    Parses tool arguments JSON with multi-stage recovery:
    1. Standard json.loads
    2. Non-strict json.loads(..., strict=False) to allow unescaped newlines/tabs
    3. Structural repair for truncated strings, unclosed brackets/braces
    4. Regex extraction for tools like run_python / calc_math
    """
    if not raw or not raw.strip():
        return {}
    s = raw.strip()

    # 1. Standard json.loads
    try:
        res = json.loads(s)
        if isinstance(res, dict):
            return res
    except json.JSONDecodeError:
        pass

    # 2. Non-strict (allows unescaped control chars like \n, \t)
    try:
        res = json.loads(s, strict=False)
        if isinstance(res, dict):
            return res
    except json.JSONDecodeError:
        pass

    # 3. Structural repair: close unclosed strings, square brackets, curly braces
    repaired = s
    quotes = len(re.findall(r'(?<!\\)"', repaired))
    if quotes % 2 != 0:
        repaired += '"'
    open_square = repaired.count("[") - repaired.count("]")
    if open_square > 0:
        repaired += "]" * open_square
    open_curly = repaired.count("{") - repaired.count("}")
    if open_curly > 0:
        repaired += "}" * open_curly

    try:
        res = json.loads(repaired, strict=False)
        if isinstance(res, dict):
            return res
    except json.JSONDecodeError:
        pass

    # 4. Fallback extraction for run_python / code argument
    if tool_name in ("run_python", "run_python_async") or '"code"' in s:
        code_match = re.search(r'"code"\s*:\s*"', s)
        if code_match:
            code_part = s[code_match.end() :]
            code_part = re.sub(r'"\s*}\s*$', "", code_part)
            try:
                code_unescaped = code_part.encode("utf-8").decode("unicode_escape")
            except (UnicodeDecodeError, ValueError) as exc:
                logger.debug("code_unicode_unescape_fallback", error=str(exc))
                code_unescaped = (
                    code_part.replace("\\n", "\n")
                    .replace('\\"', '"')
                    .replace("\\\\", "\\")
                    .replace("\\t", "\t")
                )
            return {"code": code_unescaped}

    # 5. Fallback extraction for calc_math / expr argument
    if tool_name == "calc_math" or '"expr"' in s:
        expr_match = re.search(r'"expr"\s*:\s*"([^"]*)', s)
        if expr_match:
            return {"expr": expr_match.group(1)}

    logger.warning("invalid_tool_call_json", args=raw, tool=tool_name)
    return {}



class LLMClient:
    """
    Streaming LLM client connecting to native llama-server on Windows.
    Integrates ToolCallDemux and StreamingChunker for sub-400ms voice pipeline.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.config = get_config()
        env_endpoint = os.environ.get("LUCCA_LLM_MODEL")
        if base_url:
            self.base_url = base_url
        elif env_endpoint:
            self.base_url = (
                env_endpoint
                if env_endpoint.startswith(("http://", "https://"))
                else f"http://{env_endpoint}"
            )
        else:
            self.base_url = f"http://{self.config.llm.host}:{self.config.llm.port}"
        self._streams_lock = threading.Lock()
        self._streams: dict[str, _StreamState] = {}
        self._stream_order: list[str] = []

    @property
    def aborted(self) -> bool:
        with self._streams_lock:
            if self._stream_order:
                latest = self._streams.get(self._stream_order[-1])
                return latest.aborted if latest else False
            return False

    def stream_turn(
        self,
        current_audio_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        trace_id: str | None = None,
        tools: list[ToolDefinition] | None = None,
        messages: list[ChatMessage] | None = None,
        tool_messages: list[ChatMessage] | None = None,
        epistemic_context: str | None = None,
        stance_tag: str | None = None,
        enable_thinking: bool | None = None,
        user_model_directive: str | None = None,
        episode_hints: list[str] | str | None = None,
    ) -> Generator[LLMEvent, None, None]:
        eff_trace_id = trace_id or f"anon-{now_ns()}"
        eff_temp = (
            temperature if temperature is not None else getattr(self.config.llm, "temperature", 0.6)
        )
        eff_tokens = (
            max_tokens if max_tokens is not None else getattr(self.config.llm, "max_tokens", 2048)
        )
        if messages is not None:
            eff_messages = list(messages)
            if tool_messages:
                eff_messages.extend(tool_messages)
        else:
            eff_messages = build_messages(
                memories=memories,
                history=history,
                current_audio_b64=current_audio_b64,
                current_text=current_text,
                tool_messages=tool_messages,
                epistemic_context=epistemic_context,
                stance_tag=stance_tag,
                user_model_directive=user_model_directive,
                episode_hints=episode_hints,
            )

        # WO-24 Phase 1 — Multimodal image injection (TRAP 2: variable suffix position only).
        # If any message in eff_messages carries image_b64, inject it into the last user message
        # content array in OpenAI multimodal format.  The image is consumed here and cleared from
        # the message object so it cannot leak into a subsequent LLM call.
        #
        # Injection rules:
        #   1. Only the last user message in eff_messages receives the image.
        #   2. If that message already has a list content (e.g. audio turn), append the image block.
        #   3. If that message has a plain string content, promote it to a list, append the image.
        #   4. image_b64 is cleared (set to None) unconditionally — including error paths — because
        #      clearing happens before the HTTP stream is opened.
        # Text-only path is completely unchanged when no message carries image_b64.
        _image_b64_to_inject: str | None = None
        for _msg in eff_messages:
            if getattr(_msg, "image_b64", None):
                _image_b64_to_inject = _msg.image_b64
                _msg.image_b64 = None  # consume; cleared before any stream open
        if _image_b64_to_inject is not None:
            # Find the last user message
            for _idx in range(len(eff_messages) - 1, -1, -1):
                if eff_messages[_idx].role == "user":
                    _frontier = eff_messages[_idx]
                    _img_block: dict[str, JsonValue] = {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{_image_b64_to_inject}"},
                    }
                    if isinstance(_frontier.content, list):
                        _frontier.content = list(_frontier.content) + [_img_block]
                    else:
                        _text = str(_frontier.content) if _frontier.content else ""
                        _frontier.content = (
                            [{"type": "text", "text": _text}, _img_block]
                            if _text
                            else [_img_block]
                        )
                    logger.debug(
                        "multimodal_image_injected",
                        trace_id=eff_trace_id,
                        image_bytes=len(_image_b64_to_inject) * 3 // 4,
                    )
                    break

        eff_tools = tools if tools is not None else TOOL_DEFINITIONS
        prepared_messages: list[dict[str, JsonValue]] = []
        for i, m in enumerate(eff_messages):
            dumped = m.model_dump(exclude_none=True)
            if i == len(eff_messages) - 1 and dumped.get("role") == "assistant":
                content_str = str(dumped.get("content", ""))
                if "Directive:" in content_str or "[System Executed" in content_str:
                    if prepared_messages and prepared_messages[-1].get("role") == "user":
                        prev_c = prepared_messages[-1].get("content")
                        if isinstance(prev_c, list):
                            prepared_messages[-1]["content"] = list(prev_c) + [
                                {"type": "text", "text": f"\n\n{content_str}"}
                            ]
                        else:
                            prepared_messages[-1]["content"] = f"{prev_c}\n\n{content_str}".strip()
                        continue
                    dumped["role"] = "user"
            prepared_messages.append(dumped)

        payload: dict[str, object] = {
            "messages": prepared_messages,
            "tools": [t.model_dump() for t in eff_tools],
            "tool_choice": "auto",
            "chat_template_kwargs": build_chat_template_kwargs(
                self.config.llm, enable_thinking=enable_thinking
            ),
            "max_tokens": eff_tokens,
            "temperature": eff_temp,
            "repeat_penalty": 1.1,
            "repeat_last_n": 64,
            "stop": ["</s>", "[INST]", "[/INST]", "<|im_end|>", "\nUser:"],
            "stream": True,
        }


        demux = ToolCallDemux()
        client = httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0))
        stream_state = _StreamState(client=client, aborted=False, trace_id=eff_trace_id)
        with self._streams_lock:
            self._streams[eff_trace_id] = stream_state
            self._stream_order.append(eff_trace_id)

        current_tool_calls: dict[int, dict[str, str]] = {}

        try:
            with client.stream(
                "POST", f"{self.base_url}/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code != 200:
                    err_body = resp.read().decode("utf-8")
                    raise LLMUnavailable(f"llama-server error {resp.status_code}: {err_body}")

                for line in resp.iter_lines():
                    with self._streams_lock:
                        if stream_state.aborted:
                            return
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    # Handle native structured tool_calls if emitted by Jinja template
                    if "tool_calls" in delta and delta["tool_calls"]:
                        for tc in delta["tool_calls"]:
                            idx = int(tc.get("index", 0))
                            if idx not in current_tool_calls:
                                current_tool_calls[idx] = {
                                    "id": str(tc.get("id") or f"call-{uuid.uuid4().hex[:8]}"),
                                    "name": "",
                                    "arguments": "",
                                }
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                current_tool_calls[idx]["name"] = str(fn["name"])
                            if fn.get("arguments"):
                                current_tool_calls[idx]["arguments"] += str(fn["arguments"])

                    finish_reason = choices[0].get("finish_reason")
                    if finish_reason == "tool_calls":
                        for idx in sorted(current_tool_calls.keys()):
                            tc_data = current_tool_calls[idx]
                            args = _parse_and_repair_tool_args(
                                tc_data["arguments"], tc_data.get("name", "")
                            )
                            if tc_data["name"]:
                                yield ToolCallEnd(
                                    call=ToolCall(
                                        tool=tc_data["name"],
                                        args=args,
                                        call_id=tc_data["id"],
                                    )
                                )
                        current_tool_calls.clear()

                    # Handle streaming content
                    content = delta.get("content", "")
                    if content:
                        for event in demux.feed(TokenDelta(delta=content)):
                            yield event

            # Flush any remaining tool calls
            for idx in sorted(current_tool_calls.keys()):
                tc_data = current_tool_calls[idx]
                flush_args = _parse_and_repair_tool_args(
                    tc_data["arguments"], tc_data.get("name", "")
                )
                if tc_data["name"]:
                    yield ToolCallEnd(
                        call=ToolCall(tool=tc_data["name"], args=flush_args, call_id=tc_data["id"])
                    )

            # Flush any pending buffer in demux
            for event in demux.flush():
                yield event

            yield Done(usage=LLMUsage(prompt_tokens=0, completion_tokens=0))

        except (httpx.HTTPError, OSError) as exc:
            with self._streams_lock:
                was_aborted = stream_state.aborted
            if was_aborted:
                return
            raise LLMUnavailable(f"llama-server connection error: {exc}") from exc
        finally:
            with self._streams_lock:
                self._streams.pop(eff_trace_id, None)
                if eff_trace_id in self._stream_order:
                    self._stream_order.remove(eff_trace_id)
            client.close()

    def abort(self, trace_id: str | None = None) -> None:
        """Immediately aborts targeted in-flight generation (Spec 10 barge-in gate <= 50ms)."""
        target_state: _StreamState | None = None
        with self._streams_lock:
            if trace_id is not None:
                target_state = self._streams.get(trace_id)
            elif self._stream_order:
                latest_id = self._stream_order[-1]
                target_state = self._streams.get(latest_id)

            if target_state is not None:
                target_state.aborted = True

        if target_state is not None:
            try:
                target_state.client.close()
            except (httpx.HTTPError, OSError) as exc:
                logger.debug("llm_abort_client_close_error", error=str(exc))

        # Release active slot in llama-server
        try:
            with httpx.Client(timeout=0.2) as c:
                c.post(f"{self.base_url}/slots/0?action=release")
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("llm_abort_slot_release_error", error=str(exc))
