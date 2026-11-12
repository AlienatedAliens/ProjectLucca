"""Standalone Pydantic schemas for `lucca-epistemic` (zero UI, audio, or Docker dependencies)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Final
from uuid import uuid4

from pydantic import BaseModel, Field


class Provenance(StrEnum):
    """Cryptographic domain provenance labels (ADR-006)."""

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
    """Decision-theoretic hazard tiers for 2D evidentiary burden scaling."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProofStandard(StrEnum):
    """Evidentiary standards of proof ordered by confidence threshold."""

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
    """Map an effective confidence in [0.0, 1.0] to its highest satisfied ProofStandard."""
    if confidence >= PROOF_STANDARDS[ProofStandard.BEYOND_REASONABLE_DOUBT]:
        return ProofStandard.BEYOND_REASONABLE_DOUBT
    if confidence >= PROOF_STANDARDS[ProofStandard.CLEAR_AND_CONVINCING]:
        return ProofStandard.CLEAR_AND_CONVINCING
    if confidence >= PROOF_STANDARDS[ProofStandard.BALANCE_OF_PROBABILITIES]:
        return ProofStandard.BALANCE_OF_PROBABILITIES
    return ProofStandard.SPECULATION


class BelnapValue(StrEnum):
    """Four-valued paraconsistent Belnap bilattice truth state."""

    NEITHER = "neither"
    TRUE = "true"
    FALSE = "false"
    BOTH = "both"


class UnsignedPayload(BaseModel):
    """Payload awaiting domain-separated cryptographic signing."""

    payload_id: str = Field(default_factory=lambda: uuid4().hex)
    content: str
    provenance: Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    trace_id: str = ""
    created_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class SignedPayload(UnsignedPayload):
    """Cryptographically signed memory envelope."""

    signature: str
    signer_domain: str


class ToolReceipt(BaseModel):
    """Deterministic tool execution receipt used for output supervision and corroboration."""

    tool: str
    ok: bool = True
    call_id: str = Field(default_factory=lambda: f"rcpt-{uuid4().hex[:10]}")
    args: dict[str, str | int | float | bool] = Field(default_factory=dict)
    output: str = ""


class WebEvidentiaryBurden(BaseModel):
    """Result of 2D Hazard + Walton multi-source web corroboration with near-duplicate dedup."""

    query: str
    hazard: Hazard
    hazard_device: str = "CPU"
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
    independent_sources_count: int = 0
    independent_domains: list[str] = Field(default_factory=list)
    disputed: bool = False
    dispute_sources: list[str] = Field(default_factory=list)
    summary_tag: str = ""
    guidance: str = ""


class ClauseSupervisionVerdict(BaseModel):
    """Clause-level action-claim supervision verdict against deterministic ToolReceipts."""

    is_valid: bool
    device: str = "CPU"
    latency_ms: float = 0.0
    clauses_checked: int = 0
    unsupported_claims: list[str] = Field(default_factory=list)
