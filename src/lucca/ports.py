"""
Project Lucca — Hexagonal Architecture Ports
Spec 02 (`lucca.ports`)
All external boundaries are accessed strictly through these Protocols.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

from lucca.core.ipc_schemas import ASRResultPayload, TTSDonePayload
from lucca.core.schemas import (
    CandidateRule,
    Edge,
    LLMEvent,
    LLMHealth,
    LLMRequest,
    MemoryHit,
    MemoryId,
    PromotionResult,
    RegressionReport,
    RetrievalQuery,
    Risk,
    RouteDecision,
    RouteFeatures,
    RuleId,
    RuleOutcome,
    RuleState,
    SignedPayload,
    ToolCall,
    ToolResult,
    ToolSchema,
    TracePoint,
    TurnTrace,
)


class SpeechLLMPort(Protocol):
    """Interacts with llama-server on Windows (ADR-001)."""

    async def stream(self, req: LLMRequest) -> AsyncIterator[LLMEvent]: ...
    async def abort(self, trace_id: str) -> None: ...
    async def health(self) -> LLMHealth: ...


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


class EmbeddingPort(Protocol):
    """Text embedding generation for hybrid memory."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
    def dim(self) -> int: ...


class MemoryStorePort(Protocol):
    """SQLite WAL + FTS5 + sqlite-vec storage engine (ADR-002)."""

    async def commit(self, payload: SignedPayload) -> MemoryId: ...
    async def search(self, q: RetrievalQuery) -> list[MemoryHit]: ...
    async def supersede(self, old: MemoryId, new: MemoryId, reason: str) -> None: ...
    async def forget(self, ids: list[MemoryId], *, user_confirmed: bool) -> None: ...
    async def graph_neighbors(self, entity: str, hops: int = 1) -> list[Edge]: ...


class RuleEnginePort(Protocol):
    """Pure symbolic MicroScheme rule evaluation and promotion."""

    def evaluate(
        self, state: RuleState, *, mode: Literal["shadow", "active"]
    ) -> list[RuleOutcome]: ...
    def register_candidate(self, cand: CandidateRule) -> RuleId: ...
    def record_shadow(
        self, rule_id: RuleId, *, matched: bool, cluster_id: str, indeterminate: bool
    ) -> None: ...
    def promote_if_eligible(self, rule_id: RuleId) -> PromotionResult: ...
    def approve_rule(self, rule_id: RuleId, approver: str = "human") -> PromotionResult: ...
    def verify_regression_suite(self) -> RegressionReport: ...


class RouterPort(Protocol):
    """Executive decision router (heuristic Phase 4, learned Phase 6)."""

    def route(self, feats: RouteFeatures) -> RouteDecision: ...


class SandboxPort(Protocol):
    """Tool execution inside containerized WSL2 sandboxes."""

    async def run(self, call: ToolCall, *, trace_id: str) -> ToolResult: ...
    async def reset_workspace(self) -> None: ...
    def tool_schemas(self) -> list[ToolSchema]: ...
    def risk_of(self, tool: str) -> Risk: ...


class ClockPort(Protocol):
    """Injected clock interface for test determinism and session replay."""

    def now_utc(self) -> float: ...
    def monotonic_ns(self) -> int: ...
    def now_ns(self) -> int: ...


class RandomPort(Protocol):
    """Injected randomness interface for deterministic session replay."""

    def random(self) -> float: ...


class TracePort(Protocol):
    """Latency trace collector and metrics recorder (Spec 10)."""

    def mark(self, trace_id: str, point: TracePoint, t_ns: int | None = None) -> None: ...
    def finish(self, trace_id: str) -> TurnTrace: ...
