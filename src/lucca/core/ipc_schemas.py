"""
Project Lucca — Inter-Process Communication (IPC) Schemas
Spec 01 §2, §4 (ZeroMQ Message Catalogue)
"""

import struct
from typing import Literal

from pydantic import BaseModel, JsonValue

from lucca.core.exceptions import IPCError
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
    is_final: bool = False
    source: Literal["assistant", "user", "status"] = "assistant"


class UIUserTextPayload(BaseModel):
    text: str


class UIConfigUpdatePayload(BaseModel):
    voice: str | None = None
    speed: float | None = None
    ptt_key: str | None = None
    persona_archetype: str | None = None
    formality: str | None = None
    custom_system_prompt: str | None = None
    llm_model: str | None = None


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


# ============================================================================
# Wire Framing Codec (Spec 01 §2)
# ============================================================================

MAX_FRAME_SIZE = 1024 * 1024  # 1 MiB


def encode_envelope(envelope: Envelope) -> bytes:
    """
    Serializes Envelope to wire format: uint32 big-endian length + UTF-8 JSON.
    Raises IPCError if serialized size exceeds MAX_FRAME_SIZE (1 MiB).
    """
    payload_bytes = envelope.model_dump_json().encode("utf-8")
    length = len(payload_bytes)
    if length > MAX_FRAME_SIZE:
        raise IPCError(f"Envelope size ({length} bytes) exceeds 1 MiB limit")

    return struct.pack(">I", length) + payload_bytes


def decode_envelope(data: bytes) -> Envelope:
    """
    Deserializes wire format into Envelope.
    Accepts either raw length-prefixed bytes (>I) or bare JSON bytes.
    Raises IPCError if corrupted or exceeds MAX_FRAME_SIZE.
    """
    if len(data) < 4:
        raise IPCError(f"Frame truncated (length {len(data)} < 4 bytes)")

    # Check if first 4 bytes indicate length prefix
    declared_len = struct.unpack(">I", data[:4])[0]
    if declared_len + 4 == len(data):
        if declared_len > MAX_FRAME_SIZE:
            raise IPCError(f"Declared frame size ({declared_len} bytes) exceeds 1 MiB limit")
        json_bytes = data[4:]
    else:
        # Fallback to bare data if no length prefix matches exactly
        if len(data) > MAX_FRAME_SIZE:
            raise IPCError(f"Frame size ({len(data)} bytes) exceeds 1 MiB limit")
        json_bytes = data

    try:
        return Envelope.model_validate_json(json_bytes.decode("utf-8"))
    except Exception as e:
        raise IPCError(f"Envelope decoding failed: {e}") from e
