"""
Project Lucca — Inter-Process Communication (IPC) Schemas
Spec 01 §2, §4 (ZeroMQ Message Catalogue)
"""

from typing import Literal

from pydantic import BaseModel, JsonValue

from lucca.core.schemas import Segment

# ============================================================================
# Universal Wire Envelope
# ============================================================================


class Envelope(BaseModel):
    v: Literal[1] = 1
    type: str  # Dotted type, e.g. "ptt.released"
    trace_id: str  # ULID identifying user turn
    ts_ns: int  # Monotonic timestamp of sender
    src: Literal["core", "audio", "npu", "ui"]
    payload: JsonValue  # Parsed by recipient per type


# ============================================================================
# Audio -> Core (`ingest`)
# ============================================================================


class PTTPressedPayload(BaseModel):
    t_ns: int


class PTTReleasedPayload(BaseModel):
    t_ns: int
    capture_seq_start: int
    capture_seq_end: int
    duration_ms: float
    vad_speech_ms: float


class AudioUnderrunPayload(BaseModel):
    count: int


class AudioFirstSamplePlayedPayload(BaseModel):
    trace_id: str
    t_ns: int


class AudioRMSPayload(BaseModel):
    t_ns: int
    dbfs: float


# ============================================================================
# Core -> NPU (`ctl`) & NPU -> Core
# ============================================================================


class ASRTranscribePayload(BaseModel):
    trace_id: str
    capture_seq_start: int
    capture_seq_end: int


class ASRResultPayload(BaseModel):
    text: str
    segments: list[Segment]
    avg_logprob: float
    model: str
    audio_sha256: str
    elapsed_ms: float


class TTSSynthesizePayload(BaseModel):
    trace_id: str
    chunk_id: int
    text: str
    voice: str = "af_heart"
    is_first: bool = False


class TTSDonePayload(BaseModel):
    chunk_id: int
    samples: int
    elapsed_ms: float
    device: Literal["NPU", "GPU", "CPU"]


class TTSAbortPayload(BaseModel):
    trace_id: str


class TTSAbortedPayload(BaseModel):
    trace_id: str


class EmbedTextPayload(BaseModel):
    texts: list[str]


class EmbedResultPayload(BaseModel):
    vectors: list[list[float]]
    dim: int
    elapsed_ms: float


class IntentEncodePayload(BaseModel):
    text: str


class IntentResultPayload(BaseModel):
    vector: list[float]
    elapsed_ms: float


class SysSelfTestPayload(BaseModel):
    pass


class SysSelfTestResultPayload(BaseModel):
    asr_device: str
    tts_device: str
    embed_device: str
    compile_cache_hit: bool


# ============================================================================
# Core -> Audio (`ctl`)
# ============================================================================


class PlayBeginPayload(BaseModel):
    trace_id: str


class PlayAbortPayload(BaseModel):
    trace_id: str


class CaptureMarkPayload(BaseModel):
    trace_id: str


# ============================================================================
# Core -> UI (`bus`) & UI -> Core (`ingest`)
# ============================================================================


class UIStatePayload(BaseModel):
    state: Literal["idle", "listening", "thinking", "speaking", "confirm", "offline", "degraded"]
    detail: str = ""


class UIConfirmPayload(BaseModel):
    prompt_text: str
    action_summary: str
    timeout_s: float = 15.0


class UICaptionPayload(BaseModel):
    text: str


class UIConfirmResultPayload(BaseModel):
    accepted: bool
    via: Literal["voice", "click", "timeout"]


# ============================================================================
# System Heartbeat (`ctl`)
# ============================================================================


class SysPingPayload(BaseModel):
    pass


class SysPongPayload(BaseModel):
    rss_mb: float
    queue_depth: int
