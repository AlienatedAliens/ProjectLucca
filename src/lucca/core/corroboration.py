"""
Project Lucca — Corroboration Engine (Walton Critical Questions)
WO-21 Phase 2 (The Defeasible Rung) / Spec D-REAS-09

Implements evidence-derived confidence adjustment via Walton argumentation schemes:
- Dispatches scheme critical questions against signed store and current-turn receipts.
- AUTHORITY scheme questions:
  1. Signed receipt: Does a signed receipt prove the source asserted the claim?
  2. Independent corroboration: Is the claim corroborated by an independent grounding-eligible fact?
  3. Dispute check: Is the claim disputed by any grounding-eligible fact?
- Single seam: adjust_confidence(confidence, q_results) applies owner-ratified arithmetic:
  * Corroborated: min(0.95, conf + 0.10) (capped at 0.95, no certainty laundering)
  * Disputed: max(0.00, conf - 0.30), with dispute appended to conditions
  * Unknown: unadjusted
- All Q-results record count + envelope IDs for empirical calibration and future opinion fusion.
"""

from collections.abc import Sequence
from enum import StrEnum
import json
import re
from typing import Final

from pydantic import BaseModel, Field
import structlog

from lucca.core.schemas import InferenceStep, MemoryHit, RetrievalQuery

logger = structlog.get_logger(__name__)

# Argumentation Scheme Enums
class Scheme(StrEnum):
    """Walton argumentation schemes."""

    AUTHORITY = "authority"
    SIGN = "sign"
    ANALOGY = "analogy"
    CONSEQUENCE = "consequence"
    PRECEDENT = "precedent"


class CQAnswer(StrEnum):
    """Critical question answer."""

    SATISFIED = "satisfied"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CriticalQuestionResult(BaseModel):
    """Structured critical question result (WO-21 Phase 2)."""

    question: str
    answer: CQAnswer
    count: int = 0
    evidence_entry_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "answer": self.answer.value,
            "count": self.count,
            "evidence_entry_ids": list(self.evidence_entry_ids),
            "sources": list(self.sources),
            "detail": self.detail,
        }


def adjust_confidence(
    confidence: float,
    q_results: Sequence[CriticalQuestionResult],
) -> tuple[float, list[str]]:
    """Calculates evidence-derived effective confidence and defeater conditions (WO-21 Phase 2).

    Single seam for Walton critical-question confidence arithmetic:
    - Disputed: max(0.00, conf - 0.30), dispute string returned in conditions.
    - Corroborated: min(0.95, conf + 0.10) (Trap 2: capped at 0.95).
    - Unknown: unadjusted.
    """
    conditions_to_add: list[str] = []
    effective = float(confidence)

    # Disputes have priority (asymmetric dock)
    disputes = [
        q
        for q in q_results
        if q.question == "Is the claim disputed by any grounding-eligible fact?"
        and q.answer == CQAnswer.SATISFIED
    ]
    if disputes:
        effective = max(0.0, effective - 0.30)
        for d in disputes:
            cond = (
                d.detail
                if d.detail
                else f"disputed by {', '.join(d.sources) if d.sources else 'prior grounding evidence'}"
            )
            conditions_to_add.append(cond)
    else:
        corroborations = [
            q
            for q in q_results
            if q.question
            == "Is the claim corroborated by an independent grounding-eligible fact?"
            and q.answer == CQAnswer.SATISFIED
        ]
        if corroborations:
            effective = min(0.95, effective + 0.10)

    return (round(effective, 4), conditions_to_add)


def extract_receipt_source(r: object) -> str:
    """Extracts publisher/domain/source identity from a receipt (WO-21 Phase 2 Trap 1)."""
    # 1. Direct source attribute
    if hasattr(r, "source") and getattr(r, "source"):
        return str(getattr(r, "source")).strip()
    # 2. URL argument in args
    args = getattr(r, "args", {}) or {}
    if isinstance(args, dict):
        url = str(args.get("url", "") or args.get("domain", "") or "")
        if url:
            m = re.search(r"https?://(?:www\.)?([^/]+)", url)
            if m:
                return m.group(1).lower()
            return url.strip().lower()
    # 3. Text patterns: "Report from <domain>:" or "<domain> asserts"
    text = (
        str(getattr(r, "output", "") or "")
        + " "
        + str(getattr(r, "content", "") or "")
        + " "
        + str(getattr(r, "structured", "") or "")
    )
    m = re.search(r"\b(?:report from|from|source:)\s+([a-zA-Z0-9_\-\.]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m = re.match(r"^([a-zA-Z0-9_\-\.]+)\s+asserts\b", text.strip(), re.IGNORECASE)
    if m:
        return m.group(1).lower()
    tool_name = str(getattr(r, "tool", "") or getattr(r, "name", "") or "").strip().lower()
    return tool_name


def critical_questions(
    scheme: Scheme | str,
    step: InferenceStep,
    store: object = None,
    receipts: Sequence[object] = (),
) -> list[CriticalQuestionResult]:
    """Evaluates the critical questions for an argumentation scheme (WO-21 Phase 2).

    v1 fully implements Scheme.AUTHORITY.
    Other schemes raise NotImplementedError with a typed reason.
    """
    norm_scheme = str(scheme).strip().lower()
    if norm_scheme != Scheme.AUTHORITY.value:
        raise NotImplementedError(
            f"Scheme '{scheme}' not implemented in v1 (authority-only supported)"
        )

    results: list[CriticalQuestionResult] = []

    # Parse attributed premise(s)
    attributed_pairs: list[tuple[str, str]] = []
    for prem in step.premises:
        attr_match = re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE)
        if attr_match:
            attributed_pairs.append((attr_match.group(1).strip(), attr_match.group(2).strip()))

    if not attributed_pairs:
        # Fallback to evaluating the step conclusion directly
        asserting_source = "unspecified"
        claim = f"{step.s} {step.p} {step.o}".strip()
    else:
        asserting_source, claim = attributed_pairs[0]

    claim_lower = claim.lower()
    source_lower = asserting_source.lower()

    # -------------------------------------------------------------------------
    # Q1: Does a signed receipt prove the source asserted the claim?
    # -------------------------------------------------------------------------
    q1_matches: list[str] = []
    for r in receipts:
        ok = getattr(r, "ok", True)
        if not ok:
            continue
        text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        r_source = extract_receipt_source(r).lower()

        # Check if text contains the claim and matches the asserting source
        if claim_lower in text:
            if source_lower in text or source_lower in r_source or asserting_source == "unspecified":
                cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
                q1_matches.append(cid)

    if q1_matches:
        results.append(
            CriticalQuestionResult(
                question="Does a signed receipt prove the source asserted the claim?",
                answer=CQAnswer.SATISFIED,
                count=len(q1_matches),
                evidence_entry_ids=q1_matches,
                sources=[asserting_source],
                detail=f"Signed receipt proved {asserting_source} asserted '{claim}'",
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question="Does a signed receipt prove the source asserted the claim?",
                answer=CQAnswer.FAILED,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail=f"No signed receipt found proving {asserting_source} asserted '{claim}'",
            )
        )

    # -------------------------------------------------------------------------
    # Q2: Is the claim corroborated by an independent grounding-eligible fact?
    # -------------------------------------------------------------------------
    corrob_entry_ids: list[str] = []
    independent_sources: list[str] = []
    seen_sources: set[str] = {source_lower} if source_lower != "unspecified" else set()
    if source_lower and source_lower != "unspecified":
        seen_sources.add(source_lower.replace(".com", "").replace(".org", "").replace(".net", ""))

    # Check store for independent grounding-eligible memories
    if store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id, m.content, e.signer_id, e.payload_json
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1
                          AND m.valid_to IS NULL
                          AND (m.content = ? OR m.content = ? OR m.content LIKE ?)
                        """,
                        (claim, claim_lower, f"%{claim_lower}%"),
                    )
                    for row in cur.fetchall():
                        eid, content, signer, payload_json_str = row
                        # Determine source
                        src = signer or "store"
                        if payload_json_str:
                            try:
                                pj = json.loads(payload_json_str)
                                src = pj.get("structured", {}).get("source") or pj.get("signer_id") or src
                            except Exception as exc:
                                logger.debug("payload_json_parse_error", error=str(exc))
                        src_str = str(src).strip()
                        if src_str.lower() not in seen_sources:
                            seen_sources.add(src_str.lower())
                            independent_sources.append(src_str)
                            corrob_entry_ids.append(str(eid))
            except Exception as exc:  # noqa: BLE001
                logger.debug("corroboration_db_lookup_failed", error=str(exc))

    # Check other receipts with independent sources
    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        r_source = extract_receipt_source(r).lower()
        if r_source in seen_sources or r_source in ("fetch_url", "web_search", "search_web", "tool", ""):
            continue
        if claim_lower in r_text:
            seen_sources.add(r_source)
            independent_sources.append(r_source)
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            corrob_entry_ids.append(cid)

    if independent_sources:
        results.append(
            CriticalQuestionResult(
                question="Is the claim corroborated by an independent grounding-eligible fact?",
                answer=CQAnswer.SATISFIED,
                count=len(independent_sources),
                evidence_entry_ids=corrob_entry_ids,
                sources=independent_sources,
                detail=f"Corroborated by {len(independent_sources)} independent sources: {', '.join(independent_sources)}",
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question="Is the claim corroborated by an independent grounding-eligible fact?",
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No independent corroboration found",
            )
        )

    # -------------------------------------------------------------------------
    # Q3: Is the claim disputed by any grounding-eligible fact?
    # -------------------------------------------------------------------------
    dispute_entry_ids: list[str] = []
    dispute_sources: list[str] = []
    dispute_details: list[str] = []

    # Check store for active conflicting facts
    if store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    # Look for explicit dispute or contrary predicate/object
                    # 1. Opposite triple / conflicting assertion: same subject and predicate with different object
                    if step.s and step.p:
                        cur.execute(
                            """
                            SELECT m.entry_id, m.content, e.signer_id
                            FROM memories m
                            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                            WHERE e.grounding_eligible = 1
                              AND m.valid_to IS NULL
                              AND m.content LIKE ?
                            """,
                            (f"{step.s} {step.p} %",),
                        )
                        for row in cur.fetchall():
                            eid, content, signer = row
                            parts = content.strip().split()
                            if len(parts) >= 3:
                                obj = parts[2]
                                if obj.lower() != step.o.lower():
                                    dispute_entry_ids.append(str(eid))
                                    dispute_sources.append(str(signer or "memory"))
                                    dispute_details.append(f"{content} contradicts {claim}")

                    # 2. Explicit negation or dispute phrasing
                    cur.execute(
                        """
                        SELECT m.entry_id, m.content, e.signer_id
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1
                          AND m.valid_to IS NULL
                          AND (m.content LIKE ? OR m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%disputes {claim_lower}%", f"%not_{step.p}%", f"%does_not_{step.p}%"),
                    )
                    for row in cur.fetchall():
                        eid, content, signer = row
                        if str(eid) not in dispute_entry_ids:
                            dispute_entry_ids.append(str(eid))
                            dispute_sources.append(str(signer or "memory"))
                            dispute_details.append(f"{content}")
            except Exception as exc:  # noqa: BLE001
                logger.debug("dispute_db_lookup_failed", error=str(exc))

    # Check receipts for explicit disputes
    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        if (
            f"disputes {claim_lower}" in r_text
            or f"refutes {claim_lower}" in r_text
            or f"not {claim_lower}" in r_text
            or f"does_not_{step.p}" in r_text
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            src = str(getattr(r, "source", "") or getattr(r, "tool", "") or "receipt")
            dispute_entry_ids.append(cid)
            dispute_sources.append(src)
            dispute_details.append(f"{src} reports dispute for {claim}")

    if dispute_entry_ids:
        results.append(
            CriticalQuestionResult(
                question="Is the claim disputed by any grounding-eligible fact?",
                answer=CQAnswer.SATISFIED,
                count=len(dispute_entry_ids),
                evidence_entry_ids=dispute_entry_ids,
                sources=dispute_sources,
                detail=dispute_details[0] if dispute_details else f"Dispute found for '{claim}'",
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question="Is the claim disputed by any grounding-eligible fact?",
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No disputes found",
            )
        )

    return results
