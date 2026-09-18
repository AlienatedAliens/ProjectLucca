"""
Project Lucca — LLM Client & Streaming Demuxer
Spec 02 (SpeechLLMPort), Spec 08, ADR-001
"""

import json
import uuid
from collections.abc import Generator
from typing import Any

import httpx
import structlog

from lucca.brain.prompt_builder import TOOL_DEFINITIONS, build_messages
from lucca.brain.toolcall_demux import ToolCallDemux
from lucca.core.config import get_config
from lucca.core.exceptions import LLMUnavailable
from lucca.core.schemas import (
    Done,
    LLMEvent,
    LLMUsage,
    MemoryHit,
    TokenDelta,
    ToolCall,
    ToolCallEnd,
)

logger = structlog.get_logger(__name__)


class LLMClient:
    """
    Streaming LLM client connecting to native llama-server on Windows.
    Integrates ToolCallDemux and StreamingChunker for sub-400ms voice pipeline.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.config = get_config()
        self.base_url = base_url or f"http://{self.config.llm.host}:{self.config.llm.port}"
        self.active_client: httpx.Client | None = None
        self.aborted: bool = False

    def stream_turn(
        self,
        current_audio_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Generator[LLMEvent, None, None]:
        eff_temp = (
            temperature
            if temperature is not None
            else getattr(self.config.llm, "temperature", 0.6)
        )
        eff_tokens = (
            max_tokens
            if max_tokens is not None
            else getattr(self.config.llm, "max_tokens", 512)
        )
        messages = build_messages(
            memories=memories,
            history=history,
            current_audio_b64=current_audio_b64,
            current_text=current_text,
        )

        payload: dict[str, Any] = {
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "chat_template_kwargs": {"tools_in_user_message": False},
            "max_tokens": eff_tokens,
            "temperature": eff_temp,
            "stream": True,
        }

        demux = ToolCallDemux()
        client = httpx.Client(timeout=30.0)
        self.aborted = False
        self.active_client = client
        current_tool_calls: dict[int, dict[str, Any]] = {}

        try:
            with client.stream(
                "POST", f"{self.base_url}/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code != 200:
                    err_body = resp.read().decode("utf-8")
                    raise LLMUnavailable(f"llama-server error {resp.status_code}: {err_body}")

                for line in resp.iter_lines():
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
                            args: dict[str, Any] = {}
                            if tc_data["arguments"]:
                                try:
                                    args = json.loads(tc_data["arguments"])
                                except json.JSONDecodeError:
                                    logger.warning(
                                        "invalid_tool_call_json", args=tc_data["arguments"]
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
                args = {}
                if tc_data["arguments"]:
                    try:
                        args = json.loads(tc_data["arguments"])
                    except json.JSONDecodeError:
                        logger.warning("invalid_tool_call_json", args=tc_data["arguments"])
                if tc_data["name"]:
                    yield ToolCallEnd(
                        call=ToolCall(tool=tc_data["name"], args=args, call_id=tc_data["id"])
                    )

            # Flush any pending buffer in demux
            for event in demux.flush():
                yield event

            yield Done(usage=LLMUsage(prompt_tokens=0, completion_tokens=0))

        except (httpx.HTTPError, OSError) as exc:
            if self.aborted or self.active_client is None:
                return
            raise LLMUnavailable(f"llama-server connection error: {exc}") from exc
        finally:
            client.close()
            self.active_client = None

    def abort(self) -> None:
        """Immediately aborts in-flight generation (Spec 10 barge-in gate <= 50ms)."""
        self.aborted = True
        if self.active_client:
            try:
                self.active_client.close()
            except (httpx.HTTPError, OSError) as exc:
                logger.debug("llm_abort_client_close_error", error=str(exc))
            self.active_client = None

        # Release active slot in llama-server
        try:
            with httpx.Client(timeout=0.2) as c:
                c.post(f"{self.base_url}/slots/0?action=release")
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("llm_abort_slot_release_error", error=str(exc))
