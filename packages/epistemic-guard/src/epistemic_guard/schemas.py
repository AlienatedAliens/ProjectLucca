"""Pydantic v2 schemas for `epistemic-guard` (zero LLM, UI, or daemon dependencies)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Final
from uuid import uuid4

from pydantic import BaseModel, Field


class Provenance(StrEnum):
    """Origin domain tags for memory envelopes."""

    USER_EXPLICIT = "user_explicit"
    USER_CONFIRMED = "user_confirmed"
    TOOL_VERIFIED = "tool_verified"
    LISP_ASSERTION = "lisp_assertion"
    INFERRED = "inferred"
    LLM_NARRATION = "llm_narration"
    TOOL_CONTENT_UNTRUSTED = "tool_content_untrusted"


ELIGIBLE_PROVENANCE: Final[frozenset[Provenance]] = frozenset(
    {
        Provenance.USER_EXPLICIT,
        Provenance.USER_CONFIRMED,
        Provenance.TOOL_VERIFIED,
        Provenance.LISP_ASSERTION,
        Provenance.INFERRED,
    }
)


class Hazard(StrEnum):
    """Query/claim risk tier used to scale required source corroboration."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProofStandard(StrEnum):
    """Confidence thresholds mapped to human-readable proof tiers."""

    SPECULATION = "speculation"
    BALANCE_OF_PROBABILITIES = "balance of probabilities"
    CLEAR_AND_CONVINCING = "clear and convincing"
    BEYOND_REASONABLE_DOUBT = "beyond reasonable doubt"


PROOF_STANDARDS: Final[dict[ProofStandard, float]] = {
    ProofStandard.SPECULATION: 0.0,
    ProofStandard.BALANCE_OF_PROBABILITIES: 0.50,
    ProofStandard.CLEAR_AND_CONVINCING: 0.75,
    ProofStandard.BEYOND_REASONABLE_DOUBT: 0.95,
}


def standard_for_confidence(confidence: float) -> ProofStandard:
    """Map a confidence score in `[0.0, 1.0]` to its highest satisfied `ProofStandard`."""
    if confidence >= PROOF_STANDARDS[ProofStandard.BEYOND_REASONABLE_DOUBT]:
        return ProofStandard.BEYOND_REASONABLE_DOUBT
    if confidence >= PROOF_STANDARDS[ProofStandard.CLEAR_AND_CONVINCING]:
        return ProofStandard.CLEAR_AND_CONVINCING
    if confidence >= PROOF_STANDARDS[ProofStandard.BALANCE_OF_PROBABILITIES]:
        return ProofStandard.BALANCE_OF_PROBABILITIES
    return ProofStandard.SPECULATION


class BelnapValue(StrEnum):
    """Four-valued truth state (`neither`, `true`, `false`, `both` for contradictions)."""

    NEITHER = "neither"
    TRUE = "true"
    FALSE = "false"
    BOTH = "both"


class UnsignedPayload(BaseModel):
    """Memory record awaiting domain-separated Ed25519 signing."""

    payload_id: str = Field(default_factory=lambda: uuid4().hex)
    content: str
    provenance: Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    trace_id: str = ""
    created_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class SignedPayload(UnsignedPayload):
    """Ed25519-signed memory envelope verified by `ProvenanceGate`."""

    signature: str
    signer_domain: str


class ToolReceipt(BaseModel):
    """Execution receipt emitted when a tool actually runs."""

    tool: str
    ok: bool = True
    call_id: str = Field(default_factory=lambda: f"rcpt-{uuid4().hex[:10]}")
    args: dict[str, str | int | float | bool] = Field(default_factory=dict)
    output: str = ""
    output_sha256: str = ""
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    signature: str = ""


class StructuredActionTag(BaseModel):
    """Parsed `[ACTION: <verb> <target>]` or `<action_claim>` tag from assistant output."""

    verb: str
    target: str
    raw_tag: str
    start_char: int
    end_char: int
    grounded: bool


class UnsupportedClaimSpan(BaseModel):
    """Character-offset span of an assistant clause claiming an unexecuted action."""

    text: str
    start_char: int
    end_char: int
    claimed_family: str
    reason: str


class SupervisionVerdict(BaseModel):
    """Clause-level action-receipt verification result."""

    is_valid: bool
    device: str = "CPU"
    latency_ms: float = 0.0
    clauses_checked: int = 0
    unsupported_claims: list[str] = Field(default_factory=list)
    unsupported_spans: list[UnsupportedClaimSpan] = Field(default_factory=list)
    unfulfilled_promises: list[str] = Field(default_factory=list)
    structured_actions: list[StructuredActionTag] = Field(default_factory=list)

    def to_retry_prompt(self, executed_receipts: list[ToolReceipt] | None = None) -> str:
        """Build a concise system/developer correction prompt for automatic LLM retry loops."""
        if self.is_valid:
            return ""
        ok_tools = [
            f"{r.tool}({', '.join(f'{k}={v!r}' for k, v in r.args.items())})"
            for r in (executed_receipts or [])
            if r.ok
        ]
        tools_summary = ", ".join(ok_tools) if ok_tools else "NONE"
        flagged = "; ".join(f'"{c}"' for c in (self.unsupported_claims + self.unfulfilled_promises))
        return (
            "VERIFICATION FAILED: Your draft reply claimed actions or pending executions without "
            f"matching tool receipts ({flagged}). Verified tool calls in this turn: "
            f"[{tools_summary}]. Rewrite your reply so it only states actions backed by verified "
            "tool calls, or ask before running the tool."
        )


# Backwards-compatible alias
ClauseSupervisionVerdict = SupervisionVerdict


class NLIVerdict(BaseModel):
    """3-class natural language inference result for `(premise, hypothesis)`."""

    label: str
    contradiction: float
    entailment: float
    neutral: float
    device: str = "CPU"
    latency_ms: float = 0.0

    @property
    def belnap(self) -> BelnapValue:
        """Fail-closed 4-valued Belnap projection (`neutral` -> `NEITHER`)."""
        if self.label == "entailment":
            return BelnapValue.TRUE
        if self.label == "contradiction":
            return BelnapValue.FALSE
        return BelnapValue.NEITHER


class PassageAssessment(BaseModel):
    """Per-source relevance and stance classification."""

    domain: str
    stance: str
    confidence: float
    used_neural: bool = False


class WebEvidentiaryBurden(BaseModel):
    """Multi-source RAG corroboration result after domain & wire-copy deduplication."""

    query: str
    hazard: Hazard
    hazard_device: str = "CPU"
    evidence_device: str = "DETERMINISTIC_CPU"
    nli_device: str = "DETERMINISTIC_CPU"
    hazard_latency_ms: float = 0.0
    corroboration_latency_ms: float = 0.0
    confidence: float
    achieved_standard: ProofStandard
    required_casual_standard: ProofStandard
    required_commit_standard: ProofStandard
    required_unhedged_standard: ProofStandard
    meets_casual_burden: bool
    meets_commit_burden: bool
    meets_unhedged_burden: bool
    raw_sources_count: int = 0
    deduplicated_duplicates_collapsed: int = 0
    irrelevant_sources_filtered: int = 0
    independent_sources_count: int = 0
    independent_domains: list[str] = Field(default_factory=list)
    disputed: bool = False
    dispute_sources: list[str] = Field(default_factory=list)
    passage_assessments: list[PassageAssessment] = Field(default_factory=list)
    summary_tag: str = ""
    guidance: str = ""
