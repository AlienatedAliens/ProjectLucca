"""Pydantic v2 schemas for `epistemic-guard` (zero LLM, UI, or daemon dependencies)."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final
from uuid import uuid4

from pydantic import BaseModel, Field

from epistemic_guard.exceptions import SignatureTamperError


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


def _coerce_receipt_arg(val: object) -> str | int | float | bool:
    if isinstance(val, (str, int, float, bool)):
        return val
    try:
        return json.dumps(val, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return str(val)


def _decode_aer1_canonical_bytes(raw: object) -> bytes | None:
    if isinstance(raw, bytes):
        return raw
    if not isinstance(raw, str) or not raw:
        return None
    stripped = raw.strip()
    if stripped.startswith("{"):
        return raw.encode("utf-8")
    try:
        return base64.b64decode(stripped, validate=True)
    except Exception:
        return raw.encode("utf-8")


class ToolReceipt(BaseModel):
    """Execution or pre-execution rejection receipt emitted for a tool call attempt."""

    tool: str
    ok: bool = True
    executed: bool = True
    error_code: str = ""
    call_id: str = Field(default_factory=lambda: f"rcpt-{uuid4().hex[:10]}")
    args: dict[str, str | int | float | bool] = Field(default_factory=dict)
    output: str = ""
    output_sha256: str = ""
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    signature: str = ""

    @classmethod
    def from_aer1(
        cls,
        payload: Mapping[str, Any],
        *,
        verify_commitment: bool = True,
    ) -> ToolReceipt:
        """Parse an AER-1 (`draft-zambo-aer1`) receipt or verify envelope into a `ToolReceipt`."""
        rec_raw = payload.get("receipt")
        rec: Mapping[str, Any] = rec_raw if isinstance(rec_raw, Mapping) else payload

        canon_bytes = _decode_aer1_canonical_bytes(rec.get("canonical_bytes"))
        expected_hash = str(rec.get("output_hash", "")).strip()
        computed_hex = ""
        if canon_bytes is not None:
            computed_hex = hashlib.sha256(canon_bytes).hexdigest()
            if verify_commitment and expected_hash:
                exp_hex = expected_hash.removeprefix("sha256:").lower()
                if computed_hex != exp_hex:
                    raise SignatureTamperError(
                        f"AER-1 canonical_bytes SHA-256 ({computed_hex}) != "
                        f"output_hash ({exp_hex})."
                    )

        canon_obj: Mapping[str, Any] = {}
        if canon_bytes is not None:
            try:
                parsed = json.loads(canon_bytes.decode("utf-8"))
                if isinstance(parsed, Mapping):
                    canon_obj = parsed
            except Exception:
                canon_obj = {}

        tool_block = rec.get("tool") or canon_obj.get("tool")
        if isinstance(tool_block, Mapping):
            tool_name = str(tool_block.get("name", "unknown_tool"))
        elif isinstance(tool_block, str) and tool_block:
            tool_name = tool_block
        else:
            tools_list = rec.get("tools")
            tool_name = (
                str(tools_list[0])
                if isinstance(tools_list, list) and tools_list
                else "unknown_tool"
            )

        steps = rec.get("steps")
        step0 = (
            steps[0]
            if isinstance(steps, list) and steps and isinstance(steps[0], Mapping)
            else {}
        )
        step_status = str(step0.get("status", "")).lower()

        out_obj = canon_obj.get("output")
        executed = True
        ok = True
        error_code = ""
        output_text = str(rec.get("result_preview") or "")
        args_map: dict[str, str | int | float | bool] = {}

        prov_obj = rec.get("provenance")
        if isinstance(prov_obj, Mapping) and isinstance(prov_obj.get("request"), Mapping):
            args_map = {
                str(k): _coerce_receipt_arg(v) for k, v in prov_obj["request"].items()
            }

        if isinstance(out_obj, Mapping):
            is_pre_rej = (
                out_obj.get("executed") is False
                or out_obj.get("receipt_type") == "pre_execution_rejection"
            )
            if is_pre_rej:
                executed = False
                ok = False
            if isinstance(out_obj.get("arguments_received"), Mapping):
                args_map = {
                    str(k): _coerce_receipt_arg(v)
                    for k, v in out_obj["arguments_received"].items()
                }
            err_obj = out_obj.get("error")
            if isinstance(err_obj, Mapping):
                error_code = str(err_obj.get("code", ""))
                output_text = str(err_obj.get("message", output_text))
                ok = False
            elif "text" in out_obj:
                output_text = str(out_obj["text"])

        if step_status in {"rejected_before_execution", "rejected"}:
            executed = False
            ok = False
        elif step_status in {"failed", "error"}:
            ok = False

        ver_status = str(rec.get("verification_status", "")).lower()
        if ver_status in {"failed", "invalid", "tampered"}:
            ok = False

        out_sha = computed_hex or expected_hash.removeprefix("sha256:").lower()
        return cls(
            tool=tool_name,
            ok=ok,
            executed=executed,
            error_code=error_code,
            call_id=str(rec.get("id") or f"rcpt-{uuid4().hex[:10]}"),
            args=args_map,
            output=output_text,
            output_sha256=out_sha,
            timestamp_utc=str(rec.get("created_at") or datetime.now(UTC).isoformat()),
        )

    def to_aer1(
        self,
        *,
        receipt_schema_version: str = "0.4",
        provenance_class: str | None = None,
    ) -> dict[str, Any]:
        """Export this `ToolReceipt` as a portable AER-1-compatible JSON dictionary."""
        prov_cls = provenance_class or (
            "EXECUTED BY EPISTEMIC-GUARD" if self.executed else "OBSERVED VIA GATEWAY"
        )
        if not self.executed:
            out_block: dict[str, Any] = {
                "arguments_received": dict(self.args),
                "error": {
                    "code": self.error_code or "invalid_tool_arguments",
                    "message": self.output,
                },
                "executed": False,
                "outcome": "rejected_before_execution",
                "receipt_type": "pre_execution_rejection",
                "requested_tool": self.tool,
            }
            step_status = "rejected_before_execution"
        elif not self.ok:
            out_block = {
                "arguments_received": dict(self.args),
                "error": {
                    "code": self.error_code or "execution_error",
                    "message": self.output,
                },
                "executed": True,
                "outcome": "execution_failed",
            }
            step_status = "failed"
        else:
            out_block = {"text": self.output}
            step_status = "success"

        canon_payload = {
            "issuer_claims": {"provenance_class": prov_cls},
            "output": out_block,
            "receipt_schema_version": receipt_schema_version,
            "tool": {"name": self.tool, "scope": "local", "version": "0.3.1"},
        }
        canon_raw = json.dumps(canon_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        canon_sha = hashlib.sha256(canon_raw).hexdigest()
        return {
            "id": self.call_id,
            "created_at": self.timestamp_utc,
            "receipt_schema_version": receipt_schema_version,
            "tool": {"name": self.tool, "scope": "local", "version": "0.3.1"},
            "provenance_class": prov_cls,
            "canonical_bytes": base64.b64encode(canon_raw).decode("ascii"),
            "output_hash": f"sha256:{canon_sha}",
            "verification_status": "verified",
            "steps": [
                {
                    "tool": self.tool,
                    "status": step_status,
                    "completed_at": self.timestamp_utc,
                }
            ],
        }


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

    def to_retry_prompt(self, executed_receipts: Sequence[ToolReceipt] | None = None) -> str:
        """Build a concise system/developer correction prompt for automatic LLM retry loops."""
        if self.is_valid:
            return ""
        all_rcpts = list(executed_receipts or ())
        ok_tools = [
            f"{r.tool}({', '.join(f'{k}={v!r}' for k, v in r.args.items())})"
            for r in all_rcpts
            if r.ok and r.executed
        ]
        failed_attempts: list[str] = []
        for r in all_rcpts:
            if r.ok and r.executed:
                continue
            args_fmt = ", ".join(f"{k}={v!r}" for k, v in r.args.items())
            stage_lbl = "REJECTED BEFORE EXECUTION" if not r.executed else "FAILED"
            detail = (
                f"{r.error_code}: {r.output}"
                if r.error_code and r.error_code not in r.output
                else (r.output or r.error_code or "error")
            )
            failed_attempts.append(f"{r.tool}({args_fmt}) -> {stage_lbl} ({detail})")

        tools_summary = ", ".join(ok_tools) if ok_tools else "NONE"
        failed_clause = (
            f" Rejected/failed tool attempts in this turn: [{'; '.join(failed_attempts)}]."
            if failed_attempts
            else ""
        )
        flagged = "; ".join(f'"{c}"' for c in (self.unsupported_claims + self.unfulfilled_promises))
        return (
            "VERIFICATION FAILED: Your draft reply claimed actions or pending executions without "
            f"matching tool receipts ({flagged}). Verified tool calls in this turn: "
            f"[{tools_summary}].{failed_clause} Rewrite your reply so it only states actions "
            "backed by verified tool calls, accurately reports any rejected/failed tool attempts, "
            "or asks before running the tool."
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
