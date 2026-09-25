"""
Project Lucca — Hexagonal Architecture Ports
Spec 02 (`lucca.ports`)
All external boundaries are accessed strictly through these Protocols.
"""

from collections.abc import Iterator, Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, JsonValue

from lucca.core.ipc_schemas import ASRResultPayload, TTSDonePayload
from lucca.core.schemas import (
    Edge,
    LLMEvent,
    MemoryHit,
    MemoryId,
    RetrievalQuery,
    Risk,
    SignedPayload,
    ToolResult,
    TracePoint,
    TurnTrace,
)


class SpeechLLMPort(Protocol):
    """Interacts with llama-server on Windows (ADR-001, D-PORT-01)."""

    def stream_turn(
        self,
        current_audio_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        trace_id: str | None = None,
        **kwargs: object,
    ) -> Iterator[LLMEvent]: ...

    def abort(self, trace_id: str | None = None) -> None: ...


class STTPort(Protocol):
    """Speech-to-text running on Intel NPU via OpenVINO GenAI or CPU."""

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    def transcribe(self, pcm_int16: npt.NDArray[np.int16]) -> ASRResultPayload: ...


class TTSPort(Protocol):
    """Text-to-speech synthesis with device ladder."""

    def __init__(self, play_ring: object = ...) -> None: ...

    def synthesize(
        self,
        chunk_id: int,
        text: str,
        voice: str | None = None,
        speed: float | None = None,
        is_first: bool = False,
    ) -> TTSDonePayload: ...
    def set_voice(self, voice: str) -> None: ...
    def set_speed(self, speed: float) -> None: ...
    def set_dsp_config(self, pitch_semitones: float = 0.0, enabled: bool = True) -> None: ...


class EmbeddingPort(Protocol):
    """Text embedding generation for hybrid memory."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
    def dim(self) -> int: ...


class MemoryStorePort(Protocol):
    """SQLite WAL + FTS5 + sqlite-vec storage engine (ADR-002)."""

    def commit(self, payload: SignedPayload, now: float | None = None) -> MemoryId: ...
    def search(self, q: RetrievalQuery) -> list[MemoryHit]: ...
    def supersede(self, old: MemoryId, new: MemoryId, reason: str) -> None: ...
    def forget(self, ids: list[MemoryId], *, user_confirmed: bool) -> None: ...
    def graph_neighbors(self, entity: str, hops: int = 1) -> list[Edge]: ...


class SandboxPort(Protocol):
    """Tool execution inside containerized WSL2 sandboxes or local fallback (D-PORT-01)."""

    def execute_tool(
        self,
        call_id: str,
        tool_name: str,
        args: dict[str, JsonValue] | BaseModel,
        confirmed: bool = False,
        human_confirmed: bool = False,
    ) -> ToolResult: ...

    def check_confirmation_needed(self, tool_name: str) -> bool: ...
    def get_tool_risk(self, tool_name: str) -> Risk: ...


class ClockPort(Protocol):
    """Injected clock interface for test determinism and session replay."""

    def now_utc(self) -> float: ...
    def monotonic_ns(self) -> int: ...
    def now_ns(self) -> int: ...


class TracePort(Protocol):
    """Latency trace collector and metrics recorder (Spec 10)."""

    def mark(self, trace_id: str, point: TracePoint, t_ns: int | None = None) -> None: ...
    def finish(self, trace_id: str) -> TurnTrace: ...
