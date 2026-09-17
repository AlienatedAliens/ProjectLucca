"""
Project Lucca — Common Domain Models & Schemas
Spec 02, Spec 03, Spec 06 (Zero-Any Rule Compliant)
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, JsonValue

# ============================================================================
# Audio & ASR Common Models (Spec 02)
# ============================================================================

class AudioRef(BaseModel):
    """Reference to shared-memory audio ring buffer; never carries raw PCM over IPC."""
    ring: Literal["cap"] = "cap"
    seq_start: int
    seq_end: int
    rate: Literal[16000] = 16000

class Segment(BaseModel):
    t0: float
    t1: float
    text: str
    avg_logprob: float

class Transcript(BaseModel):
    text: str
    segments: list[Segment]
    avg_logprob: float
    model: str
    audio_sha256: str
    elapsed_ms: float

# ============================================================================
# Tool & Sandbox Contracts (Spec 02, Spec 09)
# ============================================================================

class Risk(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    LAUNCH = "LAUNCH"
    NETWORK = "NETWORK"

class ToolCall(BaseModel):
    tool: str
    args: dict[str, JsonValue]
    call_id: str

class ToolResult(BaseModel):
    call_id: str
    ok: bool
    exit_code: int | None = None
    structured: dict[str, JsonValue] | None = None   # TOOL_VERIFIED facts
    content: str | None = None                       # TOOL_CONTENT_UNTRUSTED body
    content_truncated: bool = False
    elapsed_ms: float
    stderr: str = ""

class ToolParameter(BaseModel):
    type: str
    description: str
    required: bool = True

class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict[str, ToolParameter]
    risk: Risk

# ============================================================================
# LLM Port Models (Spec 02 §SpeechLLMPort)
# ============================================================================

class Msg(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None

class LLMRequest(BaseModel):
    system: str
    memory_block: str
    history: list[Msg]
    user_audio: AudioRef | None = None
    user_text: str | None = None
    tools: list[ToolSchema] = Field(default_factory=list)
    grammar: str | None = None
    max_tokens: int = 512

class TokenDelta(BaseModel):
    delta: str

class ToolCallStart(BaseModel):
    tool: str
    call_id: str

class ToolCallDelta(BaseModel):
    call_id: str
    json_fragment: str

class ToolCallEnd(BaseModel):
    call: ToolCall

class LLMUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int

class Done(BaseModel):
    usage: LLMUsage

LLMEvent = TokenDelta | ToolCallStart | ToolCallDelta | ToolCallEnd | Done

class LLMHealth(BaseModel):
    ok: bool
    model: str
    mode: Literal["audio", "transcript"]
    slots_idle: int

# ============================================================================
# TTS Models (Spec 02 §TTSPort)
# ============================================================================

class TTSChunk(BaseModel):
    trace_id: str
    chunk_id: int
    text: str
    voice: str = "af_heart"
    is_first: bool = False

class TTSChunkDone(BaseModel):
    chunk_id: int
    samples: int
    elapsed_ms: float
    device: Literal["NPU", "GPU", "CPU"]

# ============================================================================
# Memory & Provenance Models (Spec 02, Spec 03, ADR-006)
# ============================================================================

MemoryId = str

class MemoryProvenance(StrEnum):
    USER_EXPLICIT = "USER_EXPLICIT"         # Verbatim transcribed user turn
    USER_DERIVED = "USER_DERIVED"           # Quote-grounded fact extraction
    TOOL_VERIFIED = "TOOL_VERIFIED"         # Structured tool output facts
    LISP_ASSERTION = "LISP_ASSERTION"       # Derived from pure rule
    TOOL_CONTENT_UNTRUSTED = "TOOL_CONTENT_UNTRUSTED"  # Never directly memory-eligible
    LLM_NARRATION = "LLM_NARRATION"         # FORBIDDEN; no signer exists

class SignedPayload(BaseModel):
    entry_id: MemoryId
    content: str
    provenance: MemoryProvenance
    quote: str | None = None             # Required for USER_DERIVED
    source_turn_id: str | None = None
    signature: str                          # Capability signature from authorized signer
    timestamp_utc: float
    entities: list[str] = Field(default_factory=list)

class RetrievalQuery(BaseModel):
    query_text: str
    query_vector: list[float] | None = None
    k: int = 8
    exact_identifiers: list[str] = Field(default_factory=list)

class MemoryHit(BaseModel):
    memory_id: MemoryId
    content: str
    provenance: MemoryProvenance
    score: float
    source_turn_id: str | None = None

class Edge(BaseModel):
    source: str
    target: str
    relation: str

# ============================================================================
# Rule Engine & Router Models (Spec 02, Spec 05, Spec 06)
# ============================================================================

RuleId = str

class RuleAction(BaseModel):
    tool: str
    args: dict[str, JsonValue]

class Plan(BaseModel):
    actions: list[RuleAction]
    rationale: str = ""

class RuleState(BaseModel):
    intent: str
    args: dict[str, JsonValue] = Field(default_factory=dict)
    workspace_files: list[str] = Field(default_factory=list)
    recent_tools: list[str] = Field(default_factory=list)

class RuleOutcome(BaseModel):
    rule_id: RuleId
    fired: bool
    plan: Plan | None = None
    gas_used: int
    elapsed_us: int
    error: str | None = None

class CandidateRule(BaseModel):
    rule_id: RuleId
    s_expression: str
    intended_intent: str

class PromotionResult(BaseModel):
    promoted: bool
    rule_id: RuleId
    reason: str

class RegressionReport(BaseModel):
    passed: bool
    cases_evaluated: int
    failures: list[str] = Field(default_factory=list)

class RouteAction(StrEnum):
    RULE = "RULE"
    LLM = "LLM"
    CLARIFY = "CLARIFY"

class RouteFeatures(BaseModel):
    text: str
    embedding: list[float]
    word_count: int
    char_length: int
    has_question_mark: bool

class RouteDecision(BaseModel):
    action: RouteAction
    probabilities: dict[str, float]
    prediction_set: list[RouteAction]
    calibrated: bool
    elapsed_us: int

# ============================================================================
# Tracing Models (Spec 02 §TracePort, Spec 10)
# ============================================================================

class TracePoint(StrEnum):
    PTT_PRESS = "ptt_press"
    PTT_RELEASE = "ptt_release"
    VAD_SPEECH_START = "vad_speech_start"
    VAD_SPEECH_END = "vad_speech_end"
    ASR_START = "asr_start"
    ASR_DONE = "asr_done"
    LLM_START = "llm_start"
    LLM_FIRST_TOKEN = "llm_first_token"
    LLM_FIRST_CHUNK = "llm_first_chunk"
    TTS_FIRST_CHUNK_DONE = "tts_first_chunk_done"
    AUDIO_FIRST_SAMPLE = "audio_first_sample"
    TURN_DONE = "turn_done"

class TurnTrace(BaseModel):
    trace_id: str
    points_ns: dict[str, int]
    e2e_latency_ms: float
    mode: Literal["audio", "transcript"]
