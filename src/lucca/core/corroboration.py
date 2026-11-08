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

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Final

import structlog
from pydantic import BaseModel, Field

from lucca.core.schemas import InferenceStep, VerifierLabel
from lucca.memory.latent_probe import (
    BelnapLatentInvestigator,
    BelnapValue,
    has_structural_proposition_conflict,
)
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
    "github.io", "gitlab.io", "co.uk", "org.uk", "gov.uk", "ac.uk", "me.uk", "ltd.uk", "plc.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au", "co.nz", "org.nz", "net.nz", "co.jp",
    "ne.jp", "ac.jp", "go.jp", "com.br", "org.br", "co.in", "org.in", "net.in",
    # Single-level generic and country-code TLDs
    "com", "org", "net", "edu", "gov", "mil", "int", "io", "dev", "ai", "app", "tech", "info",
    "biz", "me", "tv", "co", "uk", "us", "ca", "de", "fr", "jp", "au", "eu", "nl", "ch", "se",
    "no", "es", "it", "ru", "cn", "br", "in", "nz", "cc", "to",
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
    # 1. Direct source / source_id attribute
    if hasattr(r, "source_id") and getattr(r, "source_id", None):
        return str(r.source_id).strip()
    if hasattr(r, "source") and getattr(r, "source", None):
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


def extract_receipt_signer_type(r: object) -> str:
    """Extracts signer_type or provenance class from a receipt or envelope if present."""
    for attr in ("signer_type", "provenance", "signer_id"):
        val = getattr(r, attr, None)
        if val:
            return str(val).strip()
    structured = getattr(r, "structured", None)
    if isinstance(structured, dict):
        for key in ("signer_type", "provenance", "signer_id"):
            val = structured.get(key)
            if val:
                return str(val).strip()
    return ""


def verify_source_independence(
    source_a: str,
    source_b: str,
    signer_type_a: str = "",
    signer_type_b: str = "",
) -> bool:
    """Checks whether two sources are genuinely independent in provenance."""
    sa = source_a.strip()
    sb = source_b.strip()
    if not sa or not sb:
        return False
    if is_same_source(sa, sb):
        return False
    ta = signer_type_a.strip().upper()
    tb = signer_type_b.strip().upper()
    if ta and tb and ta == tb and ta in ("USER_EXPLICIT", "UNVERIFIED", "SELF"):
        return False
    return True


_CORROB_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "to", "of", "in", "on", "at", "for", "with", "by", "that", "this",
        "it", "as", "and", "or", "from", "asserts",
    }
)

_RE_NEGATION_POLARITY: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"not|no|never|none|neither|nor|cannot|without|false|untrue|"
    r"not_[a-z0-9_]+|does_not_[a-z0-9_]+|"
    r"disput\w*|refut\w*|contradict\w*|debunk\w*|revers\w*|invalid\w*|vacat\w*|abrogat\w*|"
    r"overturn\w*|supersed\w*|unratified|non[\-\s]?binding|"
    r"inapplicable|incongruent|implausible|unreliable|unrelated|coincidental|spurious|"
    r"dissimilar|unlike"
    r")\b",
    re.IGNORECASE,
)

_RE_ADVERSATIVE_DEFEATER: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"alternativ\w+|countervail\w+|competing|conflicting|contrary|"
    r"disparit\w+|distinguish\w+|outweigh\w+|prevent\w+|throttl\w+|"
    r"side\s+effect\w*|adverse|drawback\w*|fallback|split"
    r")\b"
    r"|\b(?:differs?|difference\w*|distinct\w*)\b",
    re.IGNORECASE,
)


def _tokenize_proposition(text: str) -> list[str]:
    norm = re.sub(r"[^\w\s.]", " ", text.lower().replace("_", " ").replace("-", " "))
    return [t for t in norm.split() if len(t) > 1 and t not in _CORROB_STOPWORDS]


def _check_verifier_nli(
    verifier: SemanticVerifierPort | None,
    premise: str,
    hypothesis: str,
) -> tuple[VerifierLabel | None, float]:
    """Queries SemanticVerifierPort / VerifierWorker for NLI entailment or contradiction."""
    if verifier is None or not premise.strip() or not hypothesis.strip():
        return (None, 0.0)
    try:
        if hasattr(verifier, "check_consistency"):
            res = verifier.check_consistency(premise=premise, hypothesis=hypothesis)
            if getattr(res, "degraded", False) or res.label == VerifierLabel.UNCERTAIN:
                lex_conflict = has_structural_proposition_conflict(premise, hypothesis)
                verdict = BelnapLatentInvestigator.evaluate_nli_verdict(
                    res, has_lexical_conflict=lex_conflict
                )
                if verdict == BelnapValue.BOTH:
                    return (VerifierLabel.CONTRADICTION, 1.0)
                return (VerifierLabel.UNCERTAIN, 0.0)
            score = float(getattr(res, "score", getattr(res, "confidence", 0.85)))
            return (res.label, score)
        elif hasattr(verifier, "verify"):
            raw = verifier.verify(premise, hypothesis)
            if isinstance(raw, (int, float)):
                sc = float(raw)
                if sc >= 0.75:
                    return (VerifierLabel.ENTAILMENT, sc)
                if sc <= 0.25:
                    return (VerifierLabel.CONTRADICTION, 1.0 - sc)
                return (VerifierLabel.UNCERTAIN, 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("corroboration_nli_check_error", error=str(exc))
    return (None, 0.0)


def compute_proposition_alignment(
    claim: str,
    candidate_text: str,
    step: InferenceStep | None = None,
    verifier: SemanticVerifierPort | None = None,
) -> tuple[bool, float, bool]:
    """Computes structural entity/predicate alignment, NLI entailment, and polarity conflict."""
    cand_clean = candidate_text.strip()
    claim_clean = claim.strip()
    if not cand_clean or not claim_clean:
        return (False, 0.0, False)

    cand_lower = cand_clean.lower()
    claim_lower = claim_clean.lower()

    nli_label, nli_score = _check_verifier_nli(verifier, cand_clean, claim_clean)
    if nli_label == VerifierLabel.CONTRADICTION and nli_score >= 0.60:
        return (False, nli_score, True)

    claim_neg = bool(_RE_NEGATION_POLARITY.search(claim_lower))
    cand_neg = bool(_RE_NEGATION_POLARITY.search(cand_lower))
    has_conflict = (claim_neg != cand_neg) or bool(_RE_ADVERSATIVE_DEFEATER.search(cand_lower))

    claim_tokens = set(_tokenize_proposition(claim_lower))
    cand_tokens = set(_tokenize_proposition(cand_lower))
    if step is not None:
        s_toks = set(_tokenize_proposition(step.s))
        o_toks = set(_tokenize_proposition(step.o))
        p_toks = set(_tokenize_proposition(step.p))
        entity_tokens = s_toks | o_toks
    else:
        entity_tokens = claim_tokens
        p_toks = set()

    overlap = len(claim_tokens & cand_tokens) / max(1, len(claim_tokens))
    entity_overlap = (
        len(entity_tokens & cand_tokens) / max(1, len(entity_tokens))
        if entity_tokens
        else overlap
    )
    pred_overlap = len(p_toks & cand_tokens) / max(1, len(p_toks)) if p_toks else overlap

    combined_score = max(overlap, 0.7 * entity_overlap + 0.3 * pred_overlap)
    if claim_lower in cand_lower:
        combined_score = max(combined_score, 0.95)
    if nli_label == VerifierLabel.ENTAILMENT:
        combined_score = max(combined_score, nli_score)
    elif nli_label == VerifierLabel.UNCERTAIN and claim_lower not in cand_lower:
        combined_score = round(combined_score * 0.65, 4)

    uncertain_unverified = (nli_label == VerifierLabel.UNCERTAIN) and (
        claim_lower not in cand_lower
    )
    is_aligned = (combined_score >= 0.50) and not has_conflict and not uncertain_unverified
    return (is_aligned, combined_score, has_conflict)


from lucca.core.walton_schemes.evaluators import (  # noqa: E402, F401
    _RE_CONGRUENCE_POSITIVE,
    _RE_RATIFICATION_POSITIVE,
    _evaluate_analogy_questions,
    _evaluate_authority_questions,
    _evaluate_consequence_questions,
    _evaluate_precedent_questions,
    _evaluate_sign_questions,
)


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
        return _evaluate_authority_questions(
            step, store=store, receipts=receipts, verifier=verifier
        )
    if norm_scheme == Scheme.SIGN.value:
        return _evaluate_sign_questions(step, store=store, receipts=receipts, verifier=verifier)
    if norm_scheme == Scheme.ANALOGY.value:
        return _evaluate_analogy_questions(step, store=store, receipts=receipts, verifier=verifier)
    if norm_scheme == Scheme.CONSEQUENCE.value:
        return _evaluate_consequence_questions(
            step, store=store, receipts=receipts, verifier=verifier
        )
    if norm_scheme == Scheme.PRECEDENT.value:
        return _evaluate_precedent_questions(
            step, store=store, receipts=receipts, verifier=verifier
        )

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
