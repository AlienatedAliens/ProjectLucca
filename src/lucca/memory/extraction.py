"""
Project Lucca — Memory Fact Extraction & Quote Grounding
Spec 03 §5.2, Spec 04 §3
"""

import json
import unicodedata
from typing import Any, Final

import rapidfuzz
import structlog
from pydantic import BaseModel

from lucca.core.schemas import (
    Provenance,
    SignedPayload,
    UnsignedPayload,
    canonicalize_predicate,
    is_valid_predicate,
)
from lucca.memory.entities import FIRST_PERSON_TERMS
from lucca.memory.signers import DerivedFactSigner

logger = structlog.get_logger(__name__)

FUNCTIONAL_PREDICATES: Final[frozenset[str]] = frozenset(
    {
        "is_named",
        "lives_in",
        "works_at",
        "works_as",
        "born_on",
        "timezone_is",
        "birthday_is",
        "nationality_is",
        "origin_is",
    }
)


class ExtractedFact(BaseModel):
    s: str
    p: str
    o: str
    quote: str


def check_fact_grounding(
    transcript: str,
    fact: ExtractedFact,
) -> tuple[bool, str | None]:
    """
    Verify grounding rules per Spec 03 §5.2:
    1. quote is a substring of transcript (exact, after NFC + whitespace collapse).
    2. s and o each: substring of quote OR rapidfuzz.fuzz.partial_ratio >= 90 OR 'user'.
    3. p is a valid predicate slug (canonicalized).
    """
    norm_transcript = " ".join(unicodedata.normalize("NFC", transcript).split())
    norm_quote = " ".join(unicodedata.normalize("NFC", fact.quote).split())

    # 1. Quote check
    if not norm_quote or norm_quote not in norm_transcript:
        return False, "quote_not_in_transcript"

    # 2. Predicate check
    canon_p = canonicalize_predicate(fact.p)
    if not is_valid_predicate(canon_p):
        return False, f"invalid_predicate:{fact.p}"

    norm_quote_lower = norm_quote.lower()

    # 3. Subject (s) grounding
    s_clean = fact.s.strip()
    s_lower = s_clean.lower()
    if s_lower == "user" or s_lower in FIRST_PERSON_TERMS:
        s_ok = True
    elif s_clean in fact.quote or s_lower in norm_quote_lower:
        s_ok = True
    elif rapidfuzz.fuzz.partial_ratio(s_lower, norm_quote_lower) >= 90:
        s_ok = True
    else:
        s_ok = False

    if not s_ok:
        return False, f"s_not_grounded:{fact.s}"

    # 4. Object (o) grounding
    o_clean = fact.o.strip()
    o_lower = o_clean.lower()
    if o_lower == "user" or o_lower in FIRST_PERSON_TERMS:
        o_ok = True
    elif o_clean in fact.quote or o_lower in norm_quote_lower:
        o_ok = True
    elif rapidfuzz.fuzz.partial_ratio(o_lower, norm_quote_lower) >= 90:
        o_ok = True
    else:
        o_ok = False

    if not o_ok:
        return False, f"o_not_grounded:{fact.o}"

    return True, None


class FactExtractor:
    """
    Validates extracted facts against transcript grounding and signs valid facts
    with DerivedFactSigner.
    """

    def __init__(self, master_key: bytes) -> None:
        self.signer = DerivedFactSigner(master_key=master_key)

    def extract_and_sign(
        self,
        transcript_payload: SignedPayload,
        raw_facts: list[dict[str, Any]] | str,
        now: float | None = None,
    ) -> list[SignedPayload]:
        """
        Takes candidate facts (from LLM JSON output or dicts), performs grounding checks,
        enforces max 5 facts per turn, and signs passing facts as USER_DERIVED.
        """
        current_time = now if now is not None else transcript_payload.created_at

        facts_list: list[dict[str, Any]] = []
        if isinstance(raw_facts, str):
            try:
                data = json.loads(raw_facts)
                if isinstance(data, dict) and "facts" in data:
                    facts_list = data["facts"]
                elif isinstance(data, list):
                    facts_list = data
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.warning("fact_json_parse_error", error=str(e))
                return []
        else:
            facts_list = raw_facts

        # 4. Fact count <= 5 per turn (excess dropped, logged)
        if len(facts_list) > 5:
            logger.warning("excess_facts_dropped", total=len(facts_list), keeping=5)
            facts_list = facts_list[:5]

        signed_facts: list[SignedPayload] = []

        for i, item in enumerate(facts_list):
            try:
                raw_p = str(item.get("p", ""))
                fact = ExtractedFact(
                    s=str(item.get("s", "")),
                    p=canonicalize_predicate(raw_p),
                    o=str(item.get("o", "")),
                    quote=str(item.get("quote", "")),
                )
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning("fact_validation_error", index=i, error=str(exc))
                continue

            ok, reason = check_fact_grounding(transcript_payload.content, fact)
            if not ok:
                logger.info(
                    "grounding_fail",
                    reason=reason,
                    fact=fact.model_dump(),
                    transcript=transcript_payload.content,
                )
                continue

            content = f"{fact.s} {fact.p} {fact.o}"
            confidence = min(0.8, max(0.1, transcript_payload.confidence * 0.9))

            unsigned = UnsignedPayload(
                provenance=Provenance.USER_DERIVED,
                kind="fact",
                content=content,
                structured={
                    "s": fact.s,
                    "p": fact.p,
                    "o": fact.o,
                    "quote": fact.quote,
                },
                source_entry_ids=[transcript_payload.entry_id],
                trace_id=transcript_payload.trace_id,
                session_id=transcript_payload.session_id,
                created_at=current_time,
                nonce=f"fact_{transcript_payload.nonce}_{i}",
                confidence=confidence,
            )

            signed = self.signer.sign(unsigned)
            signed_facts.append(signed)

        return signed_facts
