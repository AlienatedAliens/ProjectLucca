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

from lucca.core.schemas import InferenceStep, VerifierLabel
from lucca.ports import SemanticVerifierPort

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


# Walton Scheme Critical Questions (WO-21 Phase 2, WO-23 Phase 1)
# AUTHORITY
Q_AUTH_SIGNED_RECEIPT: Final[str] = "Does a signed receipt prove the source asserted the claim?"
Q_AUTH_INDEPENDENT_CORROB: Final[str] = (
    "Is the claim corroborated by an independent grounding-eligible fact?"
)
Q_AUTH_DISPUTE: Final[str] = "Is the claim disputed by any grounding-eligible fact?"

# SIGN
Q_SIGN_CORRELATION: Final[str] = (
    "Does the observed sign reliably correlate with the claimed condition?"
)
Q_SIGN_INDEPENDENT_CORROB: Final[str] = (
    "Is the observed sign corroborated by an independent grounding-eligible source?"
)
Q_SIGN_DISPUTE: Final[str] = (
    "Is there an alternative explanation or contradicting fact that disputes the sign?"
)

# ANALOGY
Q_ANALOGY_SIMILARITY: Final[str] = (
    "Are the two cases relevantly similar in the respects that matter for the claim?"
)
Q_ANALOGY_DIFFERENCES: Final[str] = (
    "Are there critical differences between the cases that defeat the analogy?"
)
Q_ANALOGY_INDEPENDENT_CORROB: Final[str] = (
    "Are the facts of the source case independently corroborated?"
)

# CONSEQUENCE
Q_CONSEQ_PLAUSIBLE: Final[str] = "Does the claimed consequence plausibly follow from the action?"
Q_CONSEQ_COUNTERVAILING: Final[str] = (
    "Are there countervailing consequences that outweigh the claimed outcome?"
)
Q_CONSEQ_INDEPENDENT_CORROB: Final[str] = (
    "Is there independent empirical evidence or precedent confirming the consequence?"
)

# PRECEDENT
Q_PREC_FACT_CONGRUENCE: Final[str] = (
    "Were the facts in the cited precedent congruent with the current case?"
)
Q_PREC_RATIFIED: Final[str] = (
    "Was the prior decision ratified and grounding-eligible, not overturned or superseded?"
)
Q_PREC_COMPETING: Final[str] = "Is there a competing or conflicting precedent on record?"


class CriticalQuestionResult(BaseModel):
    """Structured critical question result (WO-21 Phase 2, extended WO-23 Phase 1)."""

    question: str
    answer: CQAnswer
    count: int = 0
    evidence_entry_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    detail: str = ""
    scheme: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "answer": self.answer.value,
            "count": self.count,
            "evidence_entry_ids": list(self.evidence_entry_ids),
            "sources": list(self.sources),
            "detail": self.detail,
            "scheme": self.scheme,
        }


def adjust_confidence(
    confidence: float,
    q_results: Sequence[CriticalQuestionResult],
    scheme: Scheme | str | None = None,
) -> tuple[float, list[str]]:
    """Calculates evidence-derived effective confidence and defeater conditions (WO-23 Phase 1).

    Single seam for Walton critical-question confidence arithmetic:
    - Bounded arithmetic: strictly min(0.95, ...) ceiling and max(0.00, ...) floor.
    - AUTHORITY: Corroborated +0.10, Disputed -0.30.
    - SIGN: CQ1 SAT + CQ2 SAT +0.15 (CQ1 SAT + CQ2 UNK +0.05);
      Dispute (CQ3 SAT) or CQ1 FAILED -0.25.
    - ANALOGY: CQ1 SAT + CQ3 SAT +0.12 (CQ1 SAT + CQ3 UNK +0.05);
      Defeating difference (CQ2 SAT) or CQ1 FAILED -0.30.
    - CONSEQUENCE: CQ1 SAT + CQ3 SAT +0.15 (CQ1 SAT + CQ3 UNK +0.05);
      Countervailing (CQ2 SAT) or CQ1 FAILED -0.30.
    - PRECEDENT: CQ1 SAT + CQ2 SAT +0.15; Superseded/unratified (CQ2 FAILED) -0.25;
      Competing precedent (CQ3 SAT) -0.20; CQ1 FAILED -0.20.
    """
    conditions_to_add: list[str] = []
    effective = float(confidence)

    active_scheme = Scheme.AUTHORITY.value
    if scheme is not None:
        active_scheme = str(scheme).strip().lower()
    elif q_results:
        for q in q_results:
            if getattr(q, "scheme", ""):
                active_scheme = str(q.scheme).strip().lower()
                break
        else:
            for q in q_results:
                ql = q.question.lower()
                if "sign" in ql:
                    active_scheme = Scheme.SIGN.value
                    break
                if "analogy" in ql or "relevantly similar" in ql:
                    active_scheme = Scheme.ANALOGY.value
                    break
                if "consequence" in ql:
                    active_scheme = Scheme.CONSEQUENCE.value
                    break
                if "precedent" in ql:
                    active_scheme = Scheme.PRECEDENT.value
                    break

    if active_scheme == Scheme.SIGN.value:
        q1 = next(
            (q for q in q_results if "reliably correlate" in q.question.lower()),
            q_results[0] if len(q_results) > 0 else None,
        )
        q2 = next(
            (q for q in q_results if "corroborated" in q.question.lower()),
            q_results[1] if len(q_results) > 1 else None,
        )
        q3 = next(
            (
                q
                for q in q_results
                if "dispute" in q.question.lower() or "alternative" in q.question.lower()
            ),
            q_results[2] if len(q_results) > 2 else None,
        )

        disputed = q3 is not None and q3.answer == CQAnswer.SATISFIED
        q1_failed = q1 is not None and q1.answer == CQAnswer.FAILED

        if disputed or q1_failed:
            effective = max(0.0, effective - 0.25)
            if disputed and q3:
                cond = (
                    q3.detail if q3.detail else "alternative explanation or dispute found for sign"
                )
                conditions_to_add.append(cond)
            if q1_failed and q1:
                cond = q1.detail if q1.detail else "observed sign does not reliably correlate"
                conditions_to_add.append(cond)
        elif q1 is not None and q1.answer == CQAnswer.SATISFIED:
            if q2 is not None and q2.answer == CQAnswer.SATISFIED:
                effective = min(0.95, effective + 0.15)
            elif q2 is not None and q2.answer == CQAnswer.UNKNOWN:
                effective = min(0.95, effective + 0.05)

    elif active_scheme == Scheme.ANALOGY.value:
        q1 = next(
            (q for q in q_results if "relevantly similar" in q.question.lower()),
            q_results[0] if len(q_results) > 0 else None,
        )
        q2 = next(
            (
                q
                for q in q_results
                if "critical differences" in q.question.lower() or "defeat" in q.question.lower()
            ),
            q_results[1] if len(q_results) > 1 else None,
        )
        q3 = next(
            (
                q
                for q in q_results
                if "independently corroborated" in q.question.lower()
                or "source case" in q.question.lower()
            ),
            q_results[2] if len(q_results) > 2 else None,
        )

        defeated = q2 is not None and q2.answer == CQAnswer.SATISFIED
        q1_failed = q1 is not None and q1.answer == CQAnswer.FAILED

        if defeated or q1_failed:
            effective = max(0.0, effective - 0.30)
            if defeated and q2:
                cond = q2.detail if q2.detail else "critical difference defeats analogy"
                conditions_to_add.append(cond)
            if q1_failed and q1:
                cond = q1.detail if q1.detail else "cases lack relevant similarity for analogy"
                conditions_to_add.append(cond)
        elif q1 is not None and q1.answer == CQAnswer.SATISFIED:
            if q3 is not None and q3.answer == CQAnswer.SATISFIED:
                effective = min(0.95, effective + 0.12)
            elif q3 is not None and q3.answer == CQAnswer.UNKNOWN:
                effective = min(0.95, effective + 0.05)

    elif active_scheme == Scheme.CONSEQUENCE.value:
        q1 = next(
            (q for q in q_results if "plausibly follow" in q.question.lower()),
            q_results[0] if len(q_results) > 0 else None,
        )
        q2 = next(
            (q for q in q_results if "countervailing" in q.question.lower()),
            q_results[1] if len(q_results) > 1 else None,
        )
        q3 = next(
            (
                q
                for q in q_results
                if "independent empirical" in q.question.lower()
                or "precedent confirming" in q.question.lower()
                or "corroborat" in q.question.lower()
            ),
            q_results[2] if len(q_results) > 2 else None,
        )

        countervailing = q2 is not None and q2.answer == CQAnswer.SATISFIED
        q1_failed = q1 is not None and q1.answer == CQAnswer.FAILED

        if countervailing or q1_failed:
            effective = max(0.0, effective - 0.30)
            if countervailing and q2:
                cond = q2.detail if q2.detail else "countervailing consequence identified"
                conditions_to_add.append(cond)
            if q1_failed and q1:
                cond = q1.detail if q1.detail else "claimed consequence does not plausibly follow"
                conditions_to_add.append(cond)
        elif q1 is not None and q1.answer == CQAnswer.SATISFIED:
            if q3 is not None and q3.answer == CQAnswer.SATISFIED:
                effective = min(0.95, effective + 0.15)
            elif q3 is not None and q3.answer == CQAnswer.UNKNOWN:
                effective = min(0.95, effective + 0.05)

    elif active_scheme == Scheme.PRECEDENT.value:
        q1 = next(
            (q for q in q_results if "congruent" in q.question.lower()),
            q_results[0] if len(q_results) > 0 else None,
        )
        q2 = next(
            (
                q
                for q in q_results
                if "ratified" in q.question.lower() or "overturned" in q.question.lower()
            ),
            q_results[1] if len(q_results) > 1 else None,
        )
        q3 = next(
            (
                q
                for q in q_results
                if "competing" in q.question.lower()
                or "conflicting precedent" in q.question.lower()
            ),
            q_results[2] if len(q_results) > 2 else None,
        )

        superseded = q2 is not None and q2.answer == CQAnswer.FAILED
        competing = q3 is not None and q3.answer == CQAnswer.SATISFIED
        q1_failed = q1 is not None and q1.answer == CQAnswer.FAILED

        if superseded or competing or q1_failed:
            dock = 0.20
            if superseded:
                dock = 0.25
            effective = max(0.0, effective - dock)
            if superseded and q2:
                cond = q2.detail if q2.detail else "precedent overturned or unratified"
                conditions_to_add.append(cond)
            if competing and q3:
                cond = q3.detail if q3.detail else "competing precedent on record"
                conditions_to_add.append(cond)
            if q1_failed and q1:
                cond = q1.detail if q1.detail else "precedent facts incongruent with current case"
                conditions_to_add.append(cond)
        elif (
            q1 is not None
            and q1.answer == CQAnswer.SATISFIED
            and q2 is not None
            and q2.answer == CQAnswer.SATISFIED
        ):
            effective = min(0.95, effective + 0.15)

    else:
        disputes = [
            q
            for q in q_results
            if ("dispute" in q.question.lower() or "disputed" in q.question.lower())
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
                if "corroborated" in q.question.lower() and q.answer == CQAnswer.SATISFIED
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


def _evaluate_authority_questions(
    step: InferenceStep,
    store: object = None,
    receipts: Sequence[object] = (),
) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Position to Know / Authority critical questions.
    (WO-21 Phase 2).
    """
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
                question=Q_AUTH_SIGNED_RECEIPT,
                answer=CQAnswer.SATISFIED,
                count=len(q1_matches),
                evidence_entry_ids=q1_matches,
                sources=[asserting_source],
                detail=f"Signed receipt proved {asserting_source} asserted '{claim}'",
                scheme=Scheme.AUTHORITY.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_AUTH_SIGNED_RECEIPT,
                answer=CQAnswer.FAILED,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail=f"No signed receipt found proving {asserting_source} asserted '{claim}'",
                scheme=Scheme.AUTHORITY.value,
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
                question=Q_AUTH_INDEPENDENT_CORROB,
                answer=CQAnswer.SATISFIED,
                count=len(independent_sources),
                evidence_entry_ids=corrob_entry_ids,
                sources=independent_sources,
                detail=detail_msg,
                scheme=Scheme.AUTHORITY.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_AUTH_INDEPENDENT_CORROB,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No independent corroboration found",
                scheme=Scheme.AUTHORITY.value,
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
                question=Q_AUTH_DISPUTE,
                answer=CQAnswer.SATISFIED,
                count=len(dispute_entry_ids),
                evidence_entry_ids=dispute_entry_ids,
                sources=dispute_sources,
                detail=dispute_details[0] if dispute_details else f"Dispute found for '{claim}'",
                scheme=Scheme.AUTHORITY.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_AUTH_DISPUTE,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No disputes found",
                scheme=Scheme.AUTHORITY.value,
            )
        )

    return results


def _evaluate_sign_questions(
    step: InferenceStep,
    store: object = None,
    receipts: Sequence[object] = (),
) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Sign critical questions (WO-23 Phase 1).

    CQ1: Does the observed sign reliably correlate with the claimed condition?
    CQ2: Is the observed sign corroborated by an independent grounding-eligible source?
    CQ3: Is there an alternative explanation or contradicting fact that disputes the sign?
    """
    results: list[CriticalQuestionResult] = []
    sign = step.s.strip()
    condition = step.o.strip()
    claim = f"{step.s} {step.p} {step.o}".strip()
    sign_lower = sign.lower()
    cond_lower = condition.lower()

    # CQ1: Observation & correlation check
    q1_matches: list[str] = []
    q1_failed = False
    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        ok = getattr(r, "ok", True)
        if not ok:
            q1_failed = True
            break
        if any(
            bad in r_text
            for bad in (
                "spurious correlation",
                "does not correlate",
                "unreliable indicator",
                "no correlation",
                "coincidental",
                "unrelated",
            )
        ):
            q1_failed = True
            break
        if (
            sign_lower in r_text
            or cond_lower in r_text
            or any(p.lower() in r_text for p in step.premises)
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            q1_matches.append(cid)

    if not q1_matches and not q1_failed and store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%{sign_lower}%", f"%{cond_lower}%"),
                    )
                    for row in cur.fetchall():
                        q1_matches.append(str(row[0]))
            except Exception as exc:  # noqa: BLE001
                logger.debug("sign_q1_db_error", error=str(exc))

    if q1_matches and not q1_failed:
        results.append(
            CriticalQuestionResult(
                question=Q_SIGN_CORRELATION,
                answer=CQAnswer.SATISFIED,
                count=len(q1_matches),
                evidence_entry_ids=q1_matches,
                sources=[extract_receipt_source(receipts[0])] if receipts else ["store"],
                detail=f"Observed sign '{sign}' reliably correlates with '{condition}'",
                scheme=Scheme.SIGN.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_SIGN_CORRELATION,
                answer=CQAnswer.FAILED,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail=(
                    f"Sign correlation for '{claim}' is unreliable or unobserved"
                    if q1_failed
                    else f"No observation confirming sign '{sign}' correlates with '{condition}'"
                ),
                scheme=Scheme.SIGN.value,
            )
        )

    # CQ2: Independent grounding-eligible corroboration
    independent_sources: list[str] = []
    seen_sources: list[str] = []
    corrob_entry_ids: list[str] = []
    if receipts:
        seen_sources.append(extract_receipt_source(receipts[0]))

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
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%{sign_lower}%", f"%{cond_lower}%"),
                    )
                    for row in cur.fetchall():
                        eid, content, signer, payload_json_str = row
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
                                logger.debug("sign_payload_parse_error", error=str(exc))
                        src_str = str(src).strip()
                        if src_str and not any(is_same_source(src_str, s) for s in seen_sources):
                            seen_sources.append(src_str)
                            independent_sources.append(src_str)
                            corrob_entry_ids.append(str(eid))
            except Exception as exc:  # noqa: BLE001
                logger.debug("sign_q2_db_error", error=str(exc))

    for r in receipts[1:] if len(receipts) > 1 else ():
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
        if sign_lower in r_text or cond_lower in r_text:
            seen_sources.append(r_source)
            independent_sources.append(r_source)
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            corrob_entry_ids.append(cid)

    if independent_sources:
        results.append(
            CriticalQuestionResult(
                question=Q_SIGN_INDEPENDENT_CORROB,
                answer=CQAnswer.SATISFIED,
                count=len(independent_sources),
                evidence_entry_ids=corrob_entry_ids,
                sources=independent_sources,
                detail=(
                    f"Sign corroborated by {len(independent_sources)} independent sources: "
                    f"{', '.join(independent_sources)}"
                ),
                scheme=Scheme.SIGN.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_SIGN_INDEPENDENT_CORROB,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No independent corroboration found for the sign",
                scheme=Scheme.SIGN.value,
            )
        )

    # CQ3: Alternative explanation or contradicting fact
    dispute_entry_ids: list[str] = []
    dispute_sources: list[str] = []
    dispute_details: list[str] = []

    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        if any(
            w in r_text
            for w in (
                "alternative explanation",
                "alternative cause",
                "dispute",
                "refute",
                "contradict",
                "not caused by",
                "actually caused by",
                "false sign",
                "debunk",
            )
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            src = extract_receipt_source(r)
            dispute_entry_ids.append(cid)
            dispute_sources.append(src)
            dispute_details.append(
                f"{src} reports alternative explanation or dispute for sign '{sign}'"
            )

    if store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id, m.content, e.signer_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (m.content LIKE ? OR m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (
                            f"%alternative%{sign_lower}%",
                            f"%disputes%{sign_lower}%",
                            f"%not_{cond_lower}%",
                        ),
                    )
                    for row in cur.fetchall():
                        eid, content, signer = row
                        if str(eid) not in dispute_entry_ids:
                            dispute_entry_ids.append(str(eid))
                            dispute_sources.append(str(signer or "memory"))
                            dispute_details.append(f"{content}")
            except Exception as exc:  # noqa: BLE001
                logger.debug("sign_q3_db_error", error=str(exc))

    if dispute_entry_ids:
        results.append(
            CriticalQuestionResult(
                question=Q_SIGN_DISPUTE,
                answer=CQAnswer.SATISFIED,
                count=len(dispute_entry_ids),
                evidence_entry_ids=dispute_entry_ids,
                sources=dispute_sources,
                detail=dispute_details[0]
                if dispute_details
                else f"Dispute found for sign '{sign}'",
                scheme=Scheme.SIGN.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_SIGN_DISPUTE,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No alternative explanation or dispute found",
                scheme=Scheme.SIGN.value,
            )
        )

    return results


def _evaluate_analogy_questions(
    step: InferenceStep,
    store: object = None,
    receipts: Sequence[object] = (),
    verifier: SemanticVerifierPort | None = None,
) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Analogy critical questions (WO-23 Phase 1).

    CQ1: Are the two cases relevantly similar in the respects that matter for the claim?
    CQ2: Are there critical differences between the cases that defeat the analogy?
    CQ3: Are the facts of the source case independently corroborated?
    """
    results: list[CriticalQuestionResult] = []
    case_a = step.s.strip()
    case_b = step.o.strip()
    case_a_lower = case_a.lower()
    case_b_lower = case_b.lower()
    asserting_source = ""
    for prem in step.premises:
        m = re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE)
        if m:
            asserting_source = m.group(1).strip()
            break

    # CQ1: Relevant similarity check (bidirectional entailment via SemanticVerifierPort)
    q1_matches: list[str] = []
    q1_failed = False
    if verifier is not None and case_a and case_b:
        try:
            r_ab = verifier.check_consistency(premise=case_a, hypothesis=case_b)
            r_ba = verifier.check_consistency(premise=case_b, hypothesis=case_a)
            if not r_ab.degraded and not r_ba.degraded:
                if (
                    r_ab.label == VerifierLabel.CONTRADICTION
                    or r_ba.label == VerifierLabel.CONTRADICTION
                ):
                    q1_failed = True
                elif (
                    r_ab.label == VerifierLabel.ENTAILMENT
                    or r_ba.label == VerifierLabel.ENTAILMENT
                ):
                    q1_matches.append("semantic_entailment")
        except Exception as exc:  # noqa: BLE001
            logger.debug("analogy_verifier_eval_failed", error=str(exc))
    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        ok = getattr(r, "ok", True)
        if not ok:
            q1_failed = True
            break
        if any(
            bad in r_text
            for bad in (
                "not similar",
                "dissimilar",
                "irrelevant comparison",
                "false equivalence",
                "no similarity",
                "unlike",
            )
        ):
            q1_failed = True
            break
        if (
            any(
                sim in r_text
                for sim in ("similar", "relevantly similar", "analogous", "parallel", "comparable")
            )
            or (case_a_lower in r_text and case_b_lower in r_text)
            or any(p.lower() in r_text for p in step.premises)
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            q1_matches.append(cid)

    if not q1_matches and not q1_failed and store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%{case_a_lower}%", f"%{case_b_lower}%"),
                    )
                    for row in cur.fetchall():
                        q1_matches.append(str(row[0]))
            except Exception as exc:  # noqa: BLE001
                logger.debug("analogy_q1_db_error", error=str(exc))

    if q1_matches and not q1_failed:
        results.append(
            CriticalQuestionResult(
                question=Q_ANALOGY_SIMILARITY,
                answer=CQAnswer.SATISFIED,
                count=len(q1_matches),
                evidence_entry_ids=q1_matches,
                sources=[extract_receipt_source(receipts[0])] if receipts else ["store"],
                detail=f"Relevant similarity established between '{case_a}' and '{case_b}'",
                scheme=Scheme.ANALOGY.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_ANALOGY_SIMILARITY,
                answer=CQAnswer.FAILED,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail=(
                    f"Analogy defeated: cases '{case_a}' and '{case_b}' lack relevant similarity"
                    if q1_failed
                    else (
                        f"No evidence establishing relevant similarity between "
                        f"'{case_a}' and '{case_b}'"
                    )
                ),
                scheme=Scheme.ANALOGY.value,
            )
        )

    # CQ2: Critical differences defeating analogy
    diff_entry_ids: list[str] = []
    diff_sources: list[str] = []
    diff_details: list[str] = []

    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        if any(
            d in r_text
            for d in (
                "critical difference",
                "defeating difference",
                "material difference",
                "crucial distinction",
                "different architecture",
                "differs significantly",
                "fundamental difference",
                "distinct mechanism",
            )
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            src = extract_receipt_source(r)
            diff_entry_ids.append(cid)
            diff_sources.append(src)
            diff_details.append(
                f"{src} reports critical difference defeating analogy "
                f"between '{case_a}' and '{case_b}'"
            )

    if store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id, m.content, e.signer_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (m.content LIKE '%difference%' OR m.content LIKE '%differs%')
                          AND (m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%{case_a_lower}%", f"%{case_b_lower}%"),
                    )
                    for row in cur.fetchall():
                        eid, content, signer = row
                        if str(eid) not in diff_entry_ids:
                            diff_entry_ids.append(str(eid))
                            diff_sources.append(str(signer or "memory"))
                            diff_details.append(f"{content}")
            except Exception as exc:  # noqa: BLE001
                logger.debug("analogy_q2_db_error", error=str(exc))

    if diff_entry_ids:
        results.append(
            CriticalQuestionResult(
                question=Q_ANALOGY_DIFFERENCES,
                answer=CQAnswer.SATISFIED,
                count=len(diff_entry_ids),
                evidence_entry_ids=diff_entry_ids,
                sources=diff_sources,
                detail=diff_details[0]
                if diff_details
                else f"Critical difference defeats analogy between '{case_a}' and '{case_b}'",
                scheme=Scheme.ANALOGY.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_ANALOGY_DIFFERENCES,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No defeating differences found",
                scheme=Scheme.ANALOGY.value,
            )
        )

    # CQ3: Source case facts independently corroborated
    independent_sources: list[str] = []
    seen_sources: list[str] = (
        [asserting_source] if (asserting_source and asserting_source != "unspecified") else []
    )
    corrob_entry_ids: list[str] = []

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
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND m.content LIKE ?
                        """,
                        (f"%{case_b_lower}%",),
                    )
                    for row in cur.fetchall():
                        eid, content, signer, payload_json_str = row
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
                                logger.debug("analogy_payload_parse_error", error=str(exc))
                        src_str = str(src).strip()
                        if src_str and not any(is_same_source(src_str, s) for s in seen_sources):
                            seen_sources.append(src_str)
                            independent_sources.append(src_str)
                            corrob_entry_ids.append(str(eid))
            except Exception as exc:  # noqa: BLE001
                logger.debug("analogy_q3_db_error", error=str(exc))

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
        case_b_clean = case_b_lower.replace("_", " ")
        if (
            case_b_lower in r_text
            or case_b_clean in r_text
            or any(w in r_text for w in re.split(r"[_\s]+", case_b_lower) if len(w) > 2)
        ):
            seen_sources.append(r_source)
            independent_sources.append(r_source)
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            corrob_entry_ids.append(cid)

    if independent_sources:
        results.append(
            CriticalQuestionResult(
                question=Q_ANALOGY_INDEPENDENT_CORROB,
                answer=CQAnswer.SATISFIED,
                count=len(independent_sources),
                evidence_entry_ids=corrob_entry_ids,
                sources=independent_sources,
                detail=(
                    f"Source case facts corroborated by {len(independent_sources)} "
                    f"independent sources: {', '.join(independent_sources)}"
                ),
                scheme=Scheme.ANALOGY.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_ANALOGY_INDEPENDENT_CORROB,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No independent corroboration of source case facts",
                scheme=Scheme.ANALOGY.value,
            )
        )

    return results


def _evaluate_consequence_questions(
    step: InferenceStep,
    store: object = None,
    receipts: Sequence[object] = (),
) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Consequences critical questions (WO-23 Phase 1).

    CQ1: Does the claimed consequence plausibly follow from the action?
    CQ2: Are there countervailing consequences that outweigh the claimed outcome?
    CQ3: Is there independent empirical evidence or precedent confirming the consequence?
    """
    results: list[CriticalQuestionResult] = []
    action = step.s.strip()
    consequence = step.o.strip()
    action_lower = action.lower()
    conseq_lower = consequence.lower()
    asserting_source = ""
    for prem in step.premises:
        m = re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE)
        if m:
            asserting_source = m.group(1).strip()
            break

    # CQ1: Plausible consequence check
    q1_matches: list[str] = []
    q1_failed = False
    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        ok = getattr(r, "ok", True)
        if not ok:
            q1_failed = True
            break
        if any(
            bad in r_text
            for bad in (
                "does not follow",
                "implausible",
                "unrelated consequence",
                "no causal link",
                "broken chain",
                "will not cause",
                "cannot produce",
            )
        ):
            q1_failed = True
            break
        if (
            any(
                c in r_text
                for c in (
                    "leads to",
                    "causes",
                    "results in",
                    "produces",
                    "will cause",
                    "consequence",
                    "triggers",
                )
            )
            or (action_lower in r_text and conseq_lower in r_text)
            or any(p.lower() in r_text for p in step.premises)
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            q1_matches.append(cid)

    if not q1_matches and not q1_failed and store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%{action_lower}%", f"%{conseq_lower}%"),
                    )
                    for row in cur.fetchall():
                        q1_matches.append(str(row[0]))
            except Exception as exc:  # noqa: BLE001
                logger.debug("consequence_q1_db_error", error=str(exc))

    if q1_matches and not q1_failed:
        results.append(
            CriticalQuestionResult(
                question=Q_CONSEQ_PLAUSIBLE,
                answer=CQAnswer.SATISFIED,
                count=len(q1_matches),
                evidence_entry_ids=q1_matches,
                sources=[extract_receipt_source(receipts[0])] if receipts else ["store"],
                detail=f"Plausible consequence established: '{action}' leads to '{consequence}'",
                scheme=Scheme.CONSEQUENCE.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_CONSEQ_PLAUSIBLE,
                answer=CQAnswer.FAILED,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail=(
                    f"Causal link implausible: '{action}' does not lead to '{consequence}'"
                    if q1_failed
                    else f"No evidence establishing that '{action}' leads to '{consequence}'"
                ),
                scheme=Scheme.CONSEQUENCE.value,
            )
        )

    # CQ2: Countervailing consequences
    counter_entry_ids: list[str] = []
    counter_sources: list[str] = []
    counter_details: list[str] = []

    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        if any(
            c in r_text
            for c in (
                "countervailing consequence",
                "countervailing",
                "unintended consequence",
                "side effect",
                "adverse outcome",
                "outweighed by",
                "drawback",
                "severe negative impact",
                "harm outweighs",
            )
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            src = extract_receipt_source(r)
            counter_entry_ids.append(cid)
            counter_sources.append(src)
            counter_details.append(f"{src} reports countervailing consequence for '{action}'")

    if store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id, m.content, e.signer_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (
                              m.content LIKE '%countervailing%'
                              OR m.content LIKE '%side effect%'
                              OR m.content LIKE '%adverse%'
                          )
                          AND m.content LIKE ?
                        """,
                        (f"%{action_lower}%",),
                    )
                    for row in cur.fetchall():
                        eid, content, signer = row
                        if str(eid) not in counter_entry_ids:
                            counter_entry_ids.append(str(eid))
                            counter_sources.append(str(signer or "memory"))
                            counter_details.append(f"{content}")
            except Exception as exc:  # noqa: BLE001
                logger.debug("consequence_q2_db_error", error=str(exc))

    if counter_entry_ids:
        results.append(
            CriticalQuestionResult(
                question=Q_CONSEQ_COUNTERVAILING,
                answer=CQAnswer.SATISFIED,
                count=len(counter_entry_ids),
                evidence_entry_ids=counter_entry_ids,
                sources=counter_sources,
                detail=counter_details[0]
                if counter_details
                else f"Countervailing consequence identified for '{action}'",
                scheme=Scheme.CONSEQUENCE.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_CONSEQ_COUNTERVAILING,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No countervailing consequences found",
                scheme=Scheme.CONSEQUENCE.value,
            )
        )

    # CQ3: Independent empirical evidence or precedent confirming consequence
    independent_sources: list[str] = []
    seen_sources: list[str] = (
        [asserting_source] if (asserting_source and asserting_source != "unspecified") else []
    )
    corrob_entry_ids: list[str] = []

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
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND m.content LIKE ?
                        """,
                        (f"%{conseq_lower}%",),
                    )
                    for row in cur.fetchall():
                        eid, content, signer, payload_json_str = row
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
                                logger.debug("consequence_payload_parse_error", error=str(exc))
                        src_str = str(src).strip()
                        if src_str and not any(is_same_source(src_str, s) for s in seen_sources):
                            seen_sources.append(src_str)
                            independent_sources.append(src_str)
                            corrob_entry_ids.append(str(eid))
            except Exception as exc:  # noqa: BLE001
                logger.debug("consequence_q3_db_error", error=str(exc))

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
        conseq_clean = conseq_lower.replace("_", " ")
        if (
            conseq_lower in r_text
            or conseq_clean in r_text
            or any(w in r_text for w in re.split(r"[_\s]+", conseq_lower) if len(w) > 2)
        ):
            seen_sources.append(r_source)
            independent_sources.append(r_source)
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            corrob_entry_ids.append(cid)

    if independent_sources:
        results.append(
            CriticalQuestionResult(
                question=Q_CONSEQ_INDEPENDENT_CORROB,
                answer=CQAnswer.SATISFIED,
                count=len(independent_sources),
                evidence_entry_ids=corrob_entry_ids,
                sources=independent_sources,
                detail=(
                    f"Consequence confirmed by {len(independent_sources)} "
                    f"independent sources: {', '.join(independent_sources)}"
                ),
                scheme=Scheme.CONSEQUENCE.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_CONSEQ_INDEPENDENT_CORROB,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No independent empirical confirmation of consequence",
                scheme=Scheme.CONSEQUENCE.value,
            )
        )

    return results


def _evaluate_precedent_questions(
    step: InferenceStep,
    store: object = None,
    receipts: Sequence[object] = (),
) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Precedent critical questions (WO-23 Phase 1).

    CQ1: Were the facts in the cited precedent congruent with the current case?
    CQ2: Was the prior decision ratified and grounding-eligible, not overturned or superseded?
    CQ3: Is there a competing or conflicting precedent on record?
    """
    results: list[CriticalQuestionResult] = []
    current_case = step.s.strip()
    ruling = step.o.strip()
    case_lower = current_case.lower()
    ruling_lower = ruling.lower()

    # CQ1: Factual congruence check
    q1_matches: list[str] = []
    q1_failed = False
    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        ok = getattr(r, "ok", True)
        if not ok:
            q1_failed = True
            break
        if any(
            bad in r_text
            for bad in (
                "incongruent facts",
                "distinguishable on the facts",
                "distinguishable facts",
                "different facts",
                "facts differ",
                "distinguishable",
                "inapplicable precedent",
            )
        ):
            q1_failed = True
            break
        if (
            any(
                cg in r_text
                for cg in (
                    "congruent facts",
                    "matching facts",
                    "facts are congruent",
                    "parallel facts",
                    "same factual basis",
                    "identical facts",
                    "factually congruent",
                    "on all fours",
                )
            )
            or (case_lower in r_text and ruling_lower in r_text)
            or any(p.lower() in r_text for p in step.premises)
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            q1_matches.append(cid)

    if not q1_matches and not q1_failed and store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%{case_lower}%", f"%{ruling_lower}%"),
                    )
                    for row in cur.fetchall():
                        q1_matches.append(str(row[0]))
            except Exception as exc:  # noqa: BLE001
                logger.debug("precedent_q1_db_error", error=str(exc))

    if q1_matches and not q1_failed:
        results.append(
            CriticalQuestionResult(
                question=Q_PREC_FACT_CONGRUENCE,
                answer=CQAnswer.SATISFIED,
                count=len(q1_matches),
                evidence_entry_ids=q1_matches,
                sources=[extract_receipt_source(receipts[0])] if receipts else ["store"],
                detail=f"Precedent facts congruent with current case '{current_case}'",
                scheme=Scheme.PRECEDENT.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_PREC_FACT_CONGRUENCE,
                answer=CQAnswer.FAILED,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail=(
                    f"Precedent facts incongruent or distinguishable for '{ruling}'"
                    if q1_failed
                    else f"No evidence establishing factual congruence for precedent '{ruling}'"
                ),
                scheme=Scheme.PRECEDENT.value,
            )
        )

    # CQ2: Prior decision ratified and grounding-eligible, not overturned or superseded
    is_superseded = False
    is_ratified = False
    q2_eids: list[str] = []
    q2_sources: list[str] = []
    q2_detail = ""

    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        src = extract_receipt_source(r)
        cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
        if any(
            bad in r_text
            for bad in (
                "overturned",
                "superseded",
                "vacated",
                "unratified",
                "non-binding",
                "abrogated",
                "invalidated",
                "reversed",
            )
        ):
            is_superseded = True
            q2_eids.append(cid)
            q2_sources.append(src)
            q2_detail = f"{src} reports precedent for '{ruling}' was overturned or superseded"
            break
        if any(
            good in r_text
            for good in (
                "ratified",
                "binding",
                "grounding-eligible",
                "upheld",
                "affirmed",
                "established ruling",
            )
        ):
            is_ratified = True
            q2_eids.append(cid)
            q2_sources.append(src)
            q2_detail = f"Prior decision '{ruling}' was ratified and remains binding"

    if not is_superseded and store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id, m.content, e.signer_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%{case_lower}%", f"%{ruling_lower}%"),
                    )
                    rows = cur.fetchall()
                    if rows:
                        for row in rows:
                            row_content = str(row[1] or "").lower()
                            if any(
                                bad in row_content
                                for bad in (
                                    "overturned",
                                    "superseded",
                                    "vacated",
                                    "unratified",
                                    "non-binding",
                                    "abrogated",
                                    "invalidated",
                                    "reversed",
                                )
                            ):
                                is_superseded = True
                                q2_eids.append(str(row[0]))
                                q2_sources.append(str(row[2] or "store"))
                                q2_detail = (
                                    f"Prior decision '{ruling}' was overturned or "
                                    f"superseded: {row[1]}"
                                )
                                break
                            else:
                                is_ratified = True
                                q2_eids.append(str(row[0]))
                                q2_sources.append(str(row[2] or "store"))
                        if is_ratified and not is_superseded:
                            q2_detail = (
                                f"Prior decision '{ruling}' found ratified in grounding store"
                            )
            except Exception as exc:  # noqa: BLE001
                logger.debug("precedent_q2_db_error", error=str(exc))

    if is_superseded:
        results.append(
            CriticalQuestionResult(
                question=Q_PREC_RATIFIED,
                answer=CQAnswer.FAILED,
                count=len(q2_eids),
                evidence_entry_ids=q2_eids,
                sources=q2_sources,
                detail=q2_detail or f"Precedent for '{ruling}' was overturned or superseded",
                scheme=Scheme.PRECEDENT.value,
            )
        )
    elif is_ratified:
        results.append(
            CriticalQuestionResult(
                question=Q_PREC_RATIFIED,
                answer=CQAnswer.SATISFIED,
                count=len(q2_eids),
                evidence_entry_ids=q2_eids,
                sources=q2_sources,
                detail=q2_detail or f"Prior decision '{ruling}' was ratified and remains binding",
                scheme=Scheme.PRECEDENT.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_PREC_RATIFIED,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="Precedent ratification status unconfirmed",
                scheme=Scheme.PRECEDENT.value,
            )
        )

    # CQ3: Competing or conflicting precedent on record
    competing_eids: list[str] = []
    competing_sources: list[str] = []
    competing_details: list[str] = []

    for r in receipts:
        r_text = (
            str(getattr(r, "output", "") or "")
            + " "
            + str(getattr(r, "content", "") or "")
            + " "
            + str(getattr(r, "structured", "") or "")
        ).lower()
        if any(
            c in r_text
            for c in (
                "competing precedent",
                "conflicting precedent",
                "contrary precedent",
                "split of authority",
                "conflicting ruling",
                "split decision",
            )
        ):
            cid = str(getattr(r, "call_id", "") or getattr(r, "entry_id", "") or "rcpt")
            src = extract_receipt_source(r)
            competing_eids.append(cid)
            competing_sources.append(src)
            competing_details.append(f"{src} reports competing precedent for '{ruling}'")

    if store is not None:
        db = getattr(store, "db", None)
        if db is not None and hasattr(db, "read_cursor"):
            try:
                with db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.entry_id, m.content, e.signer_id FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL
                          AND (
                              m.content LIKE '%competing precedent%'
                              OR m.content LIKE '%conflicting precedent%'
                          )
                          AND (m.content LIKE ? OR m.content LIKE ?)
                        """,
                        (f"%{case_lower}%", f"%{ruling_lower}%"),
                    )
                    for row in cur.fetchall():
                        eid, content, signer = row
                        if str(eid) not in competing_eids:
                            competing_eids.append(str(eid))
                            competing_sources.append(str(signer or "memory"))
                            competing_details.append(f"{content}")
            except Exception as exc:  # noqa: BLE001
                logger.debug("precedent_q3_db_error", error=str(exc))

    if competing_eids:
        results.append(
            CriticalQuestionResult(
                question=Q_PREC_COMPETING,
                answer=CQAnswer.SATISFIED,
                count=len(competing_eids),
                evidence_entry_ids=competing_eids,
                sources=competing_sources,
                detail=competing_details[0]
                if competing_details
                else f"Competing precedent on record for '{ruling}'",
                scheme=Scheme.PRECEDENT.value,
            )
        )
    else:
        results.append(
            CriticalQuestionResult(
                question=Q_PREC_COMPETING,
                answer=CQAnswer.UNKNOWN,
                count=0,
                evidence_entry_ids=[],
                sources=[],
                detail="No competing precedents found",
                scheme=Scheme.PRECEDENT.value,
            )
        )

    return results


def critical_questions(
    scheme: Scheme | str,
    step: InferenceStep,
    store: object = None,
    receipts: Sequence[object] = (),
    verifier: SemanticVerifierPort | None = None,
) -> list[CriticalQuestionResult]:
    """Evaluates the critical questions for an argumentation scheme (WO-21 Phase 2, WO-23 Phase 1).

    Dispatches to scheme-specific evaluators:
    - Scheme.AUTHORITY: expert citation / signed receipt
    - Scheme.SIGN: observable indicator / symptom -> cause
    - Scheme.ANALOGY: case comparison / relevant similarity
    - Scheme.CONSEQUENCE: causal claim / action -> outcome
    - Scheme.PRECEDENT: prior ruling / congruence & ratification
    """
    norm_scheme = str(scheme).strip().lower()
    if norm_scheme == Scheme.AUTHORITY.value:
        return _evaluate_authority_questions(step, store=store, receipts=receipts)
    if norm_scheme == Scheme.SIGN.value:
        return _evaluate_sign_questions(step, store=store, receipts=receipts)
    if norm_scheme == Scheme.ANALOGY.value:
        return _evaluate_analogy_questions(step, store=store, receipts=receipts, verifier=verifier)
    if norm_scheme == Scheme.CONSEQUENCE.value:
        return _evaluate_consequence_questions(step, store=store, receipts=receipts)
    if norm_scheme == Scheme.PRECEDENT.value:
        return _evaluate_precedent_questions(step, store=store, receipts=receipts)

    raise NotImplementedError(f"Scheme '{scheme}' not implemented in corroboration engine")


# Premise-shape cue regexes (WO-23 Phase 1)
_RE_SIGN = re.compile(
    r"\b("
    r"indicat(es?|ed|ing|ion|or|ors)?|"
    r"symptom(s|atic)?|"
    r"signs?\s+of|"
    r"observ(ed|able|es?|ation(s)?)|"
    r"evidence\s+of|"
    r"telemetry|"
    r"signal(s)?|"
    r"metrics?|"
    r"sensor"
    r")\b|"
    r"\b(npu|cpu|gpu|ram|memory)\s+(load|usage|utilization|status)\b|"
    r"\bload\s+is\s+(zero|high|low|normal)\b|"
    r"\b(slow|lag|latency|timeout|bottleneck)\b",
    re.IGNORECASE,
)

_RE_ANALOGY = re.compile(
    r"\b("
    r"analog(y|ous)?|"
    r"similar(ly|ity|ities)?|"
    r"parallel(s)?|"
    r"compar(es?|ed|ing|ison|able)?|"
    r"resembl(es?|ance)|"
    r"case\s+comparison|"
    r"like\s+in\s+case|"
    r"parallel\s+case|"
    r"similar\s+case|"
    r"as\s+in\s+case"
    r")\b",
    re.IGNORECASE,
)

_RE_CONSEQUENCE = re.compile(
    r"\b("
    r"consequen(ce|ces|t|tial)?|"
    r"caus(es?|ed|ing|al)|"
    r"leads?\s+to|"
    r"leading\s+to|"
    r"results?\s+in|"
    r"resulting\s+in|"
    r"countervail(ing)?|"
    r"will\s+cause|"
    r"will\s+lead\s+to|"
    r"will\s+result\s+in|"
    r"outcomes?\s+of"
    r")\b",
    re.IGNORECASE,
)

_RE_PRECEDENT = re.compile(
    r"\b("
    r"precedent(s|ial)?|"
    r"prior\s+(ruling|decision|case)|"
    r"previous\s+(ruling|decision|case)|"
    r"(ratified|binding|established|superseded|overturned)\s+(ruling|precedent)|"
    r"stare\s+decisis|"
    r"ruled\s+in|"
    r"held\s+in"
    r")\b",
    re.IGNORECASE,
)

_RE_EXPERT_AUTHORITY = re.compile(
    r"\b("
    r"expert(s)?|"
    r"specialist(s)?|"
    r"authorit(y|ies)|"
    r"testif(ies|y|ied|ication)|"
    r"cites?|"
    r"cited\s+by|"
    r"according\s+to|"
    r"statement\s+by|"
    r"quoted\s+by"
    r")\b",
    re.IGNORECASE,
)


def detect_premise_scheme(step: InferenceStep) -> tuple[Scheme, str | None]:
    """Classifies the premise shape of an InferenceStep into a Walton scheme (WO-23 Phase 1).

    Classification mappings:
    - observable indicator / symptom -> Scheme.SIGN
    - case comparison / similarity -> Scheme.ANALOGY
    - causal claim / action -> outcome -> Scheme.CONSEQUENCE
    - prior ruling / precedent -> Scheme.PRECEDENT
    - expert citation / authority -> Scheme.AUTHORITY

    Ambiguous premise shapes (multiple conflicting cues or zero distinct cues)
    fall back to Scheme.AUTHORITY with a recorded explanation condition note.
    """
    has_attr = any(
        re.match(r"^(.+?)\s+asserts\s+(.+)$", p.strip(), re.IGNORECASE) for p in step.premises
    )

    texts_to_inspect: list[str] = []
    for prem in step.premises:
        attr_m = re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE)
        if attr_m:
            texts_to_inspect.append(attr_m.group(2).strip())
        else:
            texts_to_inspect.append(prem.strip())

    texts_to_inspect.append(step.conclusion.strip())

    combined_text = " ".join(texts_to_inspect)
    search_text = f"{combined_text} {combined_text.replace('_', ' ')}"

    candidates: list[Scheme] = []
    if _RE_SIGN.search(search_text):
        candidates.append(Scheme.SIGN)
    if _RE_ANALOGY.search(search_text):
        candidates.append(Scheme.ANALOGY)
    if _RE_CONSEQUENCE.search(search_text):
        candidates.append(Scheme.CONSEQUENCE)
    if _RE_PRECEDENT.search(search_text):
        candidates.append(Scheme.PRECEDENT)

    if len(candidates) == 1:
        return (candidates[0], None)

    if len(candidates) > 1:
        matched_names = ", ".join(sorted(s.value for s in candidates))
        note = f"ambiguous premise shape (multiple cues: {matched_names}); defaulting to authority"
        return (Scheme.AUTHORITY, note)

    # If no other scheme cues, check if it's cleanly an expert authority or attributed claim
    if has_attr or _RE_EXPERT_AUTHORITY.search(search_text):
        return (Scheme.AUTHORITY, None)

    # Zero cues and not attributed: ambiguous fallback
    note = "ambiguous premise shape (no distinct scheme cues); defaulting to authority"
    return (Scheme.AUTHORITY, note)
