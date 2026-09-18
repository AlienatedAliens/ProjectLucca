"""
Project Lucca — Common Domain Models & Schemas
Spec 02, Spec 03, Spec 06 (Zero-Any Rule Compliant)
"""

from enum import StrEnum
from pathlib import Path
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
    structured: dict[str, JsonValue] | None = None  # TOOL_VERIFIED facts
    content: str | None = None  # TOOL_CONTENT_UNTRUSTED body
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

MemoryId = int | str


class Provenance(StrEnum):
    USER_EXPLICIT = "USER_EXPLICIT"
    USER_EXPLICIT_LOWCONF = "USER_EXPLICIT_LOWCONF"
    USER_DERIVED = "USER_DERIVED"
    TOOL_VERIFIED = "TOOL_VERIFIED"
    TOOL_CONTENT_UNTRUSTED = "TOOL_CONTENT_UNTRUSTED"
    LISP_ASSERTION = "LISP_ASSERTION"
    LLM_NARRATION = "LLM_NARRATION"


MemoryProvenance = Provenance

MEMORY_ELIGIBLE: frozenset[Provenance] = frozenset(
    {
        Provenance.USER_EXPLICIT,
        Provenance.USER_DERIVED,
        Provenance.TOOL_VERIFIED,
        Provenance.LISP_ASSERTION,
    }
)


class ASRMeta(BaseModel, frozen=True):
    model: str
    avg_logprob: float
    audio_sha256: str


class ToolMeta(BaseModel, frozen=True):
    tool: str
    call_id: str
    exit_code: int
    content_sha256: str


class UnsignedPayload(BaseModel, frozen=True):
    schema_version: Literal[2] = 2
    provenance: Provenance
    kind: Literal["transcript", "fact", "tool_fact", "rule_assertion"]
    content: str  # verbatim text or canonical fact rendering
    structured: dict[str, JsonValue] | None = None  # e.g. {"s":..., "p":..., "o":...}
    source_entry_ids: list[str] = Field(default_factory=list)
    trace_id: str = ""
    session_id: str = ""
    created_at: float  # unix seconds (ClockPort)
    nonce: str  # 16 random bytes, base64url (RandomPort)
    asr: ASRMeta | None = None
    tool: ToolMeta | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SignedPayload(UnsignedPayload, frozen=True):
    signer_id: str  # e.g. "asr@lucca-core"
    signature: str  # base64 HMAC-SHA256
    content_sha256: str
    entry_id: str  # sha256(canonical(payload_without_sig))[:32]


class LLMNarration(BaseModel, frozen=True):
    text: str
    trace_id: str = ""
    created_at: float = 0.0


class Admitted(BaseModel, frozen=True):
    payload: SignedPayload


class RetrievalQuery(BaseModel):
    query_text: str
    query_vector: list[float] | None = None
    k: int = 8
    exact_identifiers: list[str] = Field(default_factory=list)
    include_superseded: bool = False
    kinds: list[str] | None = None
    since: float | None = None


class MemoryHit(BaseModel):
    memory_id: MemoryId
    content: str
    provenance: MemoryProvenance
    score: float
    source_turn_id: str | None = None
    kind: str = "fact"
    created_at: float = 0.0
    valid_from: float = 0.0
    valid_to: float | None = None


class Edge(BaseModel):
    source: str
    target: str
    relation: str


# ============================================================================
# Rule Engine & Router Models (Spec 02, Spec 05, Spec 06)
# ============================================================================

RuleId = str


class Say(BaseModel):
    text: str


class Plan(BaseModel):
    actions: list[ToolCall | Say]
    rationale: str = ""


RuleAction = ToolCall | Say


class RuleState(BaseModel, frozen=True):
    schema_version: Literal[1] = 1
    transcript: str = ""  # Whisper text, normalised
    transcript_lower: str = ""
    intent: str = "unknown"  # launch_app|file_read|file_write|web_fetch|...
    intent_conf: float = 0.0
    entities: dict[str, list[str]] = Field(default_factory=dict)  # {"app":["calculator"], ...}
    hour_local: int = 0
    weekday: int = 0  # 0=Mon
    apps_running: frozenset[str] = Field(default_factory=frozenset)
    last_tool: str | None = None
    last_tool_ok: bool | None = None
    session_turns: int = 0
    mode: Literal["audio", "transcript"] = "transcript"


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
    # RuleState snapshot fields (Spec 05 §5)
    transcript: str = ""
    transcript_lower: str = ""
    intent: str = "unknown"
    intent_conf: float = 0.0
    entities: dict[str, list[str]] = Field(default_factory=dict)
    hour_local: int = 0
    weekday: int = 0
    apps_running: list[str] = Field(default_factory=list)
    last_tool: str | None = None
    last_tool_ok: bool | None = None
    session_turns: int = 0
    mode: Literal["audio", "transcript"] = "transcript"
    # Router specific additions (Spec 06 §1)
    vad_speech_ms: int = 1000
    asr_avg_logprob: float = 0.0
    any_active_rule_fired: bool = False
    any_quarantine_rule_fired: bool = False
    has_registered_rule: bool = False


class RouteDecision(BaseModel):
    action: RouteAction
    probabilities: dict[str, float] | None = None
    prediction_set: list[RouteAction]
    fallback_applied: bool = False
    calibrated: bool = False
    elapsed_us: int


class DecisionLabel(StrEnum):
    POS = "POS"
    NEG = "NEG"
    INDETERMINATE = "INDETERMINATE"


class DecisionLabelReason(StrEnum):
    EARLY_BARGEIN = "early_bargein"
    EXPLICIT_NEGATION = "explicit_negation"
    TOOL_FAILED = "tool_failed"
    USER_DECLINED = "user_declined"
    RULE_WOULD_MATCH = "rule_would_match"
    RULE_WRONG = "rule_wrong"
    CLARIFY_USEFUL = "clarify_useful"
    IMPLICIT_OK = "implicit_ok"


class DecisionRecord(BaseModel):
    decision_id: str
    trace_id: str
    session_id: str
    ts: float
    features: RouteFeatures
    decision: RouteDecision
    router_version: str = "heuristic-1.0"
    executed_path: Literal["RULE", "LLM", "CLARIFY"]
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_ok: bool | None = None
    llm_first_token_ms: float | None = None
    user_interrupted: bool = False
    interrupted_after_ms: float | None = None
    label: DecisionLabel | None = None
    label_reason: DecisionLabelReason | str | None = None
    counterfactual_rule_fired: bool = False


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


# ============================================================================
# Brain & Persona Domain Models (F-BRAIN-001)
# ============================================================================


class ToolFunctionSchema(BaseModel):
    name: str
    description: str
    parameters: dict[str, JsonValue]


class ToolDefinition(BaseModel):
    type: str = "function"
    function: ToolFunctionSchema

    def __getitem__(self, item: str) -> object:
        if item == "type":
            return self.type
        if item == "function":
            return self.function.model_dump()
        return getattr(self, item)


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, JsonValue]]

    def __getitem__(self, item: str) -> object:
        return getattr(self, item)

    def get(self, item: str, default: object = None) -> object:
        return getattr(self, item, default)


class PersonaTraitsConfig(BaseModel):
    technical_depth: float = 0.5
    warmth: float = 0.5
    directness: float = 0.5

    def __getitem__(self, item: str) -> object:
        return getattr(self, item)

    def get(self, item: str, default: object = None) -> object:
        return getattr(self, item, default)


class PersonaBoundariesConfig(BaseModel):
    never_pretend_to_feel: bool = True
    refuse_topics: list[str] = Field(default_factory=list)

    def __getitem__(self, item: str) -> object:
        return getattr(self, item)

    def get(self, item: str, default: object = None) -> object:
        return getattr(self, item, default)


class PersonaAffectConfig(BaseModel):
    enabled: bool = True
    decay_tau_seconds: float = 600.0
    max_speed_delta: float = 0.10

    def __getitem__(self, item: str) -> object:
        return getattr(self, item)

    def get(self, item: str, default: object = None) -> object:
        return getattr(self, item, default)


class PersonaConfig(BaseModel):
    name: str = "Lucca"
    voice: str = "genki_heroine"
    archetype: str = "inventor"
    formality: str = "casual"
    custom_prompt: str = ""
    uses_your_name: bool = True
    admits_uncertainty: bool = True
    traits: PersonaTraitsConfig = Field(default_factory=PersonaTraitsConfig)
    boundaries: PersonaBoundariesConfig = Field(default_factory=PersonaBoundariesConfig)
    affect: PersonaAffectConfig = Field(default_factory=PersonaAffectConfig)
    user_archetypes: dict[str, str] = Field(default_factory=dict)

    def __getitem__(self, item: str) -> object:
        return getattr(self, item)

    def get(self, item: str, default: object = None) -> object:
        return getattr(self, item, default)


class ModelRegistryEntry(BaseModel):
    path: Path
    filename: str
    rel_path: str
    name: str
    architecture: str
    quantization: str
    size_gb: float
    tensor_count: int
    badge: str
    badge_type: str
    is_active: bool
    paired_mmproj: Path | None = None

    def __getitem__(self, item: str) -> object:
        return getattr(self, item)

    def get(self, item: str, default: object = None) -> object:
        return getattr(self, item, default)
