"""
Project Lucca — Common Domain Models & Schemas
Spec 02, Spec 03, Spec 06 (Zero-Any Rule Compliant)
"""

import re
import time
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal

import ulid
from pydantic import BaseModel, Field, JsonValue, field_validator

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
    target: Literal["self", "host_readonly", "shared"]


ALLOWED_SKILL_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "cognitive_core",
        "information",
        "host_perception",
        "companion",
        "self",
        "host_readonly",
        "shared",
    }
)

SKILL_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*-v[0-9]+$")


class SkillMeta(BaseModel):
    id: str
    intent: str
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    status: Literal["ACTIVE", "QUARANTINE", "RETIRED"] = "QUARANTINE"
    version: str = "1.0.0"
    categories: list[str] = Field(default_factory=list)
    expose_as_tool: bool = False

    @field_validator("id")
    @classmethod
    def validate_skill_id(cls, v: str) -> str:
        if not SKILL_ID_PATTERN.match(v):
            raise ValueError(
                f"Invalid skill id '{v}': must be kebab-case and version-suffixed "
                "(e.g. 'calc-eval-v1')"
            )
        return v

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, v: list[str]) -> list[str]:
        if len(v) > 2:
            raise ValueError(f"Skill cannot declare more than 2 categories, got {len(v)}")
        for cat in v:
            if cat not in ALLOWED_SKILL_CATEGORIES:
                raise ValueError(
                    f"Unknown category '{cat}': must be one of {sorted(ALLOWED_SKILL_CATEGORIES)}"
                )
        return v


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
    raw_text: str = ""
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
    INFERRED = "INFERRED"
    LLM_NARRATION = "LLM_NARRATION"
    ASSISTANT_UTTERANCE = "ASSISTANT_UTTERANCE"
    ASSISTANT_ACTION = "ASSISTANT_ACTION"
    ASSISTANT_BELIEF = "ASSISTANT_BELIEF"
    COHERENCE_BREACH = "COHERENCE_BREACH"


MemoryProvenance = Provenance

MEMORY_ELIGIBLE: frozenset[Provenance] = frozenset(
    {
        Provenance.USER_EXPLICIT,
        Provenance.USER_DERIVED,
        Provenance.INFERRED,
        Provenance.TOOL_VERIFIED,
        Provenance.LISP_ASSERTION,
        Provenance.ASSISTANT_UTTERANCE,
        Provenance.ASSISTANT_ACTION,
        Provenance.ASSISTANT_BELIEF,
        Provenance.COHERENCE_BREACH,
    }
)

GROUNDING_ELIGIBLE: frozenset[Provenance] = frozenset(
    {
        Provenance.USER_EXPLICIT,
        Provenance.USER_DERIVED,
        Provenance.INFERRED,
        Provenance.TOOL_VERIFIED,
        Provenance.LISP_ASSERTION,
        Provenance.ASSISTANT_ACTION,
        Provenance.COHERENCE_BREACH,
    }
)


# WO-17 Phase 2 (ADR-010 supersession): open-predicate vocabulary.
# Standard common predicates retained for schema guidance and manifest menus.
FACT_PREDICATES: Final[frozenset[str]] = frozenset(
    {
        "is_named",
        "has_sibling",
        "has_parent",
        "has_child",
        "has_partner",
        "has_friend",
        "lives_in",
        "works_at",
        "works_as",
        "born_on",
        "likes",
        "dislikes",
        "owns",
        "uses_app",
        "prefers",
        "allergic_to",
        "speaks_language",
        "has_pet",
        "studies",
        "birthday_is",
        "timezone_is",
        "project_is",
        "note",
        "nationality_is",
        "origin_is",
    }
)

PREDICATE_SLUG_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def is_valid_predicate(p: str) -> bool:
    """Validates predicate format (lowercase snake_case identifier, 2–41 chars)."""
    clean = p.strip().lower()
    if clean.startswith("unauthorized_"):
        return False
    return bool(PREDICATE_SLUG_REGEX.match(clean))


PREDICATE_SYNONYMS: Final[dict[str, str]] = {
    "nationality": "nationality_is",
    "citizenship": "nationality_is",
    "origin": "origin_is",
    "resides_in": "lives_in",
    "located_in": "lives_in",
    "living_in": "lives_in",
    "employed_by": "works_at",
    "works_for": "works_at",
    "occupation_is": "works_as",
    "job_is": "works_as",
    "preferred_language": "speaks_language",
    "language_spoken": "speaks_language",
    "hobbies": "likes",
    "hobby": "likes",
    "dislike": "dislikes",
    "pet_is": "has_pet",
    "partner_is": "has_partner",
    "child_is": "has_child",
    "sibling_is": "has_sibling",
    "parent_is": "has_parent",
    "friend_is": "has_friend",
}


def canonicalize_predicate(p: str) -> str:
    """Maps predicate synonyms to their canonical slug form."""
    clean = p.strip().lower()
    return PREDICATE_SYNONYMS.get(clean, clean)


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
    kind: Literal[
        "transcript",
        "fact",
        "tool_fact",
        "rule_assertion",
        "assistant_utterance",
        "action_receipt",
        "belief",
        "coherence_breach",
        "session_summary",
        "user_model",
    ]
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
    grounding_eligible: bool = True
    confidence: float = 1.0


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


class AssertFact(BaseModel):
    s: str
    p: str
    o: str

    @field_validator("p")
    @classmethod
    def validate_predicate(cls, v: str) -> str:
        if not is_valid_predicate(v):
            raise ValueError(f"Invalid predicate format: '{v}'")
        return v


class InferenceStep(BaseModel):
    """Structured abductive inference step proposed by LLM (Spec D-REAS-09, WO-20 Phase 3).

    Ratified 2026-09-26: conclusion is a structured triple (s, p, o) with valid predicate.
    Conditions carry Toulmin defeaters / attributed premises without blocking deduction.
    """

    premises: list[str] = Field(
        ...,
        description="List of premise statements resolving to signed facts or '<source> asserts <claim>'.",
    )
    s: str = Field(..., description="Subject identifier or slug.")
    p: str = Field(..., description="Predicate slug conforming to is_valid_predicate.")
    o: str = Field(..., description="Object value.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Step confidence in [0.0, 1.0].")
    rationale: str = Field(default="", max_length=500, description="Optional brief rationale (<= 500 chars).")
    conditions: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Carried conditions / Toulmin defeaters (<= 8).",
    )

    @field_validator("p")
    @classmethod
    def validate_predicate(cls, v: str) -> str:
        if not is_valid_predicate(v):
            raise ValueError(f"Invalid predicate format: '{v}'")
        return v

    @property
    def conclusion(self) -> str:
        return f"{self.s} {self.p} {self.o}"


class Plan(BaseModel):
    actions: list[ToolCall | Say | AssertFact]
    rationale: str = ""


RuleAction = ToolCall | Say | AssertFact


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
    interrupted: bool = False
    asserted_facts: frozenset[tuple[str, str, str]] = frozenset()


class RuleOutcome(BaseModel):
    rule_id: RuleId
    fired: bool
    errored: bool = False
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


# ============================================================================
# S1 Typed Execution Triple Models (Spec §5, Handover #4 S1.1)
# ============================================================================

PlanStep = ToolCall | Say


class Proposal(BaseModel):
    """Proposal emitted by S1 (rule engine). Spec §5."""

    proposal_id: str = Field(default_factory=lambda: str(ulid.ULID()))
    rule_id: str
    plan: list[ToolCall | Say]
    confidence: float = 1.0
    gas_estimate: int = 0
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("plan", mode="before")
    @classmethod
    def _coerce_plan(cls, v: object) -> object:
        if isinstance(v, Plan):
            return v.actions
        return v


class Decision(BaseModel):
    """Decision emitted by arbiter / S2. Spec §5."""

    decision_id: str = Field(default_factory=lambda: str(ulid.ULID()))
    proposal_id: str
    verdict: Literal["accepted", "overridden", "escalated"]
    reason_code: str


class Outcome(BaseModel):
    """Grounded outcome, never self-judged. Spec §5."""

    outcome_id: str = Field(default_factory=lambda: str(ulid.ULID()))
    decision_id: str
    signal: Literal[
        "tool_exit_zero",
        "pydantic_valid",
        "operator_confirm",
        "operator_correct",
        "abstained",
    ]
    detail: str = ""


class ExecutionTriple(BaseModel):
    """(Proposal, Decision, Outcome) triple persisted to SQLite WAL. Spec §5."""

    triple_id: str = Field(default_factory=lambda: str(ulid.ULID()))
    proposal: Proposal
    decision: Decision
    outcome: Outcome
    created_at: float = Field(default_factory=time.time)


class ExecutionTier(StrEnum):
    REFLEX = "REFLEX"
    ACT_THEN_NARRATE = "ACT_THEN_NARRATE"
    FULL_LOOP = "FULL_LOOP"


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
    tier: ExecutionTier = ExecutionTier.FULL_LOOP


class RouteDecision(BaseModel):
    action: RouteAction
    tier: ExecutionTier = ExecutionTier.REFLEX
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

    @property
    def fallback_applied(self) -> bool:
        return self.decision.fallback_applied


class RecallEpisode(BaseModel):
    source: Literal["decisions", "execution_triples"]
    record_id: str
    ts: float
    match_score: int  # tokens matched
    tokens_total: int  # tokens in query after stop-word removal
    # one-line human-readable summary, e.g.:
    # "Historical turn 'open calculator': routed RULE via ACT_THEN_NARRATE (succeeded)"
    summary: str
    payload: dict[str, JsonValue]


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
    content: str | list[dict[str, JsonValue]] = ""
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[dict[str, JsonValue]] | None = None

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
    speed: float = 1.05
    ptt_key: str = "alt_gr"
    archetype: str = "inventor"
    formality: str = "casual"
    custom_prompt: str = ""
    uses_your_name: bool = True
    admits_uncertainty: bool = True
    dsp_pitch_semitones: float = 0.0
    dsp_enabled: bool = False
    narration_prefer_digits: bool = True
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
