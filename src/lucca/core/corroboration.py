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

import json
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Final

import structlog
from pydantic import BaseModel, Field

from lucca.core.schemas import InferenceStep

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
            dispute_str = ", ".join(d.sources) if d.sources else "prior grounding evidence"
            cond = d.detail if d.detail else f"disputed by {dispute_str}"
            conditions_to_add.append(cond)
    else:
        corroborations = [
            q
            for q in q_results
            if q.question == "Is the claim corroborated by an independent grounding-eligible fact?"
            and q.answer == CQAnswer.SATISFIED
        ]
        if corroborations:
            effective = min(0.95, effective + 0.10)

    return (round(effective, 4), conditions_to_add)


# Small embedded public-suffix list (WO-22 Phase 0)
# Lookup table, zero network calls, deterministic.
PUBLIC_SUFFIXES: Final[tuple[str, ...]] = (
    # Multi-level public suffixes first (e.g. github.io, co.uk)
    "github.io",
    "gitlab.io",
    "co.uk",
    "org.uk",
    "gov.uk",
    "ac.uk",
    "me.uk",
    "ltd.uk",
    "plc.uk",
    "com.au",
    "net.au",
    "org.au",
    "edu.au",
    "gov.au",
    "co.nz",
    "org.nz",
    "net.nz",
    "co.jp",
    "ne.jp",
    "ac.jp",
    "go.jp",
    "com.br",
    "org.br",
    "co.in",
    "org.in",
    "net.in",
    # Single-level generic and country-code TLDs
    "com",
    "org",
    "net",
    "edu",
    "gov",
    "mil",
    "int",
    "io",
    "dev",
    "ai",
    "app",
    "tech",
    "info",
    "biz",
    "me",
    "tv",
    "co",
    "uk",
    "us",
    "ca",
    "de",
    "fr",
    "jp",
    "au",
    "eu",
    "nl",
    "ch",
    "se",
    "no",
    "es",
    "it",
    "ru",
    "cn",
    "br",
    "in",
    "nz",
    "cc",
    "to",
)

_SORTED_SUFFIXES: Final[tuple[str, ...]] = tuple(
    sorted(PUBLIC_SUFFIXES, key=lambda s: (s.count("."), len(s)), reverse=True)
)


def extract_etld_plus_one(source: str) -> tuple[str, str | None]:
    """Extracts (normalized_label, public_suffix) from a source or domain string (WO-22 Phase 0).

    Normalizes case, strips leading 'www.', strips hyphens from the registrable label,
    and matches against the embedded public suffix list.

    Returns:
        (clean_label, public_suffix) if a domain/suffix is recognized,
        (clean_source, None) if no domain suffix is present (bare source).
    """
    raw = source.strip().lower()
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].split(":", 1)[0].strip()
    raw = raw.rstrip(".")

    while raw.startswith("www."):
        raw = raw[4:]

    if not raw:
        return ("", None)

    for suffix in _SORTED_SUFFIXES:
        if raw == suffix:
            return (raw.replace("-", ""), suffix)
        if raw.endswith("." + suffix):
            prefix = raw[: -len(suffix) - 1]
            label = prefix.split(".")[-1]
            return (label.replace("-", ""), suffix)

    if "." in raw:
        parts = raw.split(".")
        suffix = parts[-1]
        label = parts[-2]
        return (label.replace("-", ""), suffix)

    return (raw.replace("-", ""), None)


def normalize_source_identity(source: str) -> str:
    """Returns canonical source identity for deduplication (WO-22 Phase 0).

    - For domain sources, returns '{clean_label}.{suffix}'.
    - For bare sources, returns '{clean_source}'.
    """
    label, suffix = extract_etld_plus_one(source)
    if suffix is not None:
        return f"{label}.{suffix}"
    return label


def is_same_source(source_a: str, source_b: str) -> bool:
    """Checks if two source representations refer to the same publisher/domain.

    Invariants (WO-22 Phase 0 / Trap 1):
    1. Two different registrable domains (e.g. 'example.com' vs 'example.org') NEVER match.
    2. Alias forms of the same domain ('ars-technica.com' vs 'arstechnica.com',
       'www.ars-technica.com' vs 'arstechnica.com') ALWAYS match.
    3. If at least one source has no domain suffix (bare source like 'ars-technica'),
       they match if their normalized labels match.
    """
    sa = source_a.strip().lower()
    sb = source_b.strip().lower()
    if not sa or not sb:
        return False
    if sa == sb:
        return True

    label_a, suffix_a = extract_etld_plus_one(sa)
    label_b, suffix_b = extract_etld_plus_one(sb)

    if suffix_a is not None and suffix_b is not None:
        # Both have domain suffixes -> must match both label and suffix
        return label_a == label_b and suffix_a == suffix_b

    # At least one is bare -> match on label
    return label_a == label_b


def extract_receipt_source(r: object) -> str:
    """Extracts publisher/domain/source identity from a receipt (WO-21 Phase 2 Trap 1)."""
    # 1. Direct source attribute
    if hasattr(r, "source") and r.source:
        return str(r.source).strip()
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
            if (
                source_lower in text
                or source_lower in r_source
                or is_same_source(asserting_source, r_source)
                or asserting_source == "unspecified"
            ):
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
    seen_sources: list[str] = (
        [asserting_source] if (asserting_source and asserting_source != "unspecified") else []
    )

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
                                src = (
                                    pj.get("structured", {}).get("source")
                                    or pj.get("signer_id")
                                    or src
                                )
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("payload_json_parse_error", error=str(exc))
                        src_str = str(src).strip()
                        if src_str and not any(is_same_source(src_str, s) for s in seen_sources):
                            seen_sources.append(src_str)
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
        r_source = extract_receipt_source(r).strip()
        if (
            not r_source
            or r_source.lower() in ("fetch_url", "web_search", "search_web", "tool")
            or any(is_same_source(r_source, s) for s in seen_sources)
        ):
            continue
        is_dispute = any(
            m in r_text
            for m in (
                "dispute",
                "disputed by",
                "refute",
                "refuted by",
                "contradict",
                "false claim",
                "debunk",
            )
        )
        if claim_lower in r_text and not is_dispute:
            seen_sources.append(r_source)
            independent_sources.append(r_source)
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            corrob_entry_ids.append(cid)

    if independent_sources:
        sources_str = ", ".join(independent_sources)
        detail_msg = (
            f"Corroborated by {len(independent_sources)} independent sources: {sources_str}"
        )
        results.append(
            CriticalQuestionResult(
                question="Is the claim corroborated by an independent grounding-eligible fact?",
                answer=CQAnswer.SATISFIED,
                count=len(independent_sources),
                evidence_entry_ids=corrob_entry_ids,
                sources=independent_sources,
                detail=detail_msg,
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
                    # 1. Opposite triple / conflicting assertion: same subject/predicate,
                    # different object
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
            or any(
                m in r_text
                for m in (
                    "dispute",
                    "disputed by",
                    "refute",
                    "refuted by",
                    "false claim",
                    "debunked",
                    "contradicts",
                )
            )
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
