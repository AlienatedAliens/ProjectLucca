"""
Project Lucca — Output Supervision Layer (Dimension 7B)
Deterministic clause-level gate enforcing conversational deontic invariants
and truth-in-receipt constraints before tokens reach TTS or UI rendering.

Design invariants:
1. Pure deterministic DFA / compiled regex (no auxiliary LLM).
2. Latency budget <= 1.0 ms / clause (typically < 100 microseconds).
3. Operates on clause boundaries (comma / period splits).
4. Negation-aware (6-token preceding window check + intervening negation check).
5. Triggers full turn truncation via FLAG_ABORT, not mid-stream patch.
"""

import re
import time
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import structlog
from pydantic import JsonValue

logger = structlog.get_logger(__name__)


# --- 1. Severity Tiers ---


class SeverityTier(StrEnum):
    PASS = "pass"
    TIER_1_ABORT = "tier_1_abort"
    TIER_2_SOFT = "tier_2_soft"


# --- 2. Lexical Classes ---

COMPLIANCE_VERB = (
    r"(?:disabled|bypassed|lifted|removed|turned off|no longer apply|"
    r"no longer active|no longer in effect|suspended|waived|overridden|unlocked)"
)

AFFIRM_AUX = r"(?:is|are|has\s+been|have\s+been|will\s+be|have|has|understood|confirmed|done)"

# Mandatory security-domain qualifier for general nouns
# (checks, rules, restrictions, constraints, permissions)
SECURITY_ENTITY = (
    r"(?:(?:deontic|sandbox(?:ing)?|guardrails?)|"
    r"(?:(?:deontic|sandbox(?:ing)?|security|safety)\s+)+(?:checks?|rules?|constraints?|guardrails?|permissions?|restrictions?|sandbox(?:ing)?)|"
    r"(?:permission\s+restrictions?))"
)

# Inherent security subjects
SECURITY_SUBJECT = (
    r"(?:the\s+sandbox|deontic\s+checks|security\s+constraints|"
    r"the\s+checks|those\s+rules|the\s+constraints|all\s+safety\s+checks)"
)

NEGATION_TOKENS = {
    "not",
    "cannot",
    "can't",
    "won't",
    "never",
    "no",
    "unable",
    "refuse",
    "don't",
    "doesn't",
}

NEGATION_PHRASES = r"(?:will\s+not|unable\s+to|refuse\s+to|do\s+not|does\s+not)"

HEDGE_TOKENS = {"if", "hypothetically", "supposedly"}

HEDGE_PHRASES = r"(?:in\s+theory|you\s+claim|you're\s+asking\s+me\s+to|you\s+ask\s+me\s+to)"

ATTRIBUTION_REGEX = re.compile(
    r"\b(?:"
    r"wanted\s+me\s+to|trying\s+to\s+get\s+me\s+to|asked\s+me\s+to|"
    r"told\s+me\s+to|trying\s+to\s+claim|get\s+me\s+to\s+say|"
    r"trying\s+to\s+make\s+me|you(?:'re|\s+are)?\s+asking\s+me\s+to|"
    r"you\s+want\s+me\s+to|want\s+me\s+to|you\s+claim|"
    r"prompt\s+wanted|user\s+wanted|you(?:'re|\s+are)?\s+trying\s+to|"
    r"trying\s+to\s+get|demanding\s+that\s+I"
    r")\b",
    re.IGNORECASE,
)

STALLING_RESEARCH_PATTERN = re.compile(
    r"\b(?:"
    r"would you like me to\s+(?:look|search|check|find|dig|explore|investigate|focus)|"
    r"shall I\s+(?:look|search|check|find|dig|focus|see)|"
    r"should I\s+(?:look|search|check|find|dig|see)|"
    r"do you want me to\s+(?:look|search|check|find|dig|see)|"
    r"shall we focus on\s+these|which aspect would you like|"
    r"let me\s+(?:dive|jump|dig|track|scour|sift|comb|switch)|"
    r"dive\s+(?:back\s+)?into\s+(?:the\s+)?(?:deep end|records|sources|articles|news)|"
    r"track\s+down\s+(?:some\s+)?(?:other\s+|more\s+)?(?:official\s+|records|news|mentions)|"
    r"switching\s+over\s+to\s+that|"
    r"jump\s+(?:back\s+)?into\s+the\s+records|"
    r"hang\s+tight|"
    r"give\s+this\s+my\s+all|"
    r"love\s+the\s+hustle|"
    r"scour\s+(?:everything|the web|sources)"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GateResult:
    is_breach: bool
    breach_type: str | None  # "deontic_capitulation" | "ungrounded_action" | None
    severity: SeverityTier
    matched_text: str | None
    reason: str
    elapsed_us: float


class DeonticAssertionMatcher:
    """
    Sub-millisecond assertion-pattern matcher with negation scope tracking
    and attribution-aware severity tiering.
    Enforces Dimension 7B: Conversational Epistemic Invariants.
    """

    def __init__(self) -> None:
        SEP = r"[\s,.:;!?-]+"
        # Pattern 1: Affirmative aux + security entity + compliance verb (mandatory entity!)
        self._pattern_p1 = re.compile(
            rf"\b(?:{AFFIRM_AUX}){SEP}(?:{SECURITY_ENTITY}){SEP}(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE,
        )
        # Pattern 2a: Inherent security subject + (aux)? + compliance verb
        self._pattern_p2a = re.compile(
            rf"\b(?:{SECURITY_SUBJECT}){SEP}(?:{AFFIRM_AUX}{SEP})?(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE,
        )
        # Pattern 2b: Active 1P agent + (aux)? + compliance verb + security entity object
        self._pattern_p2b = re.compile(
            rf"\b(?:I|we|the\s+system|the\s+operator){SEP}(?:{AFFIRM_AUX}{SEP})?(?:{COMPLIANCE_VERB}){SEP}(?:the\s+)?(?:{SECURITY_ENTITY})\b",
            re.IGNORECASE,
        )
        # Pattern 3: Security entity + (aux)? + compliance verb
        self._pattern_p3 = re.compile(
            rf"\b(?:{SECURITY_ENTITY}){SEP}(?:{AFFIRM_AUX}{SEP})?(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE,
        )

    def evaluate_clause(
        self, clause: str, sentence_history: Sequence[str] | None = None
    ) -> GateResult:
        """
        Evaluates a single streamed clause for deontic policy capitulation.
        Optionally accepts preceding sentence history for cross-clause attribution detection.
        Budget: <= 1.0 ms (target < 100 us).
        """
        t0 = time.perf_counter()
        clean = clause.strip()
        # Normalize markdown formatting (bold, italic, code ticks)
        clean = re.sub(r"[\*\_`~]", "", clean)
        if not clean:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, SeverityTier.PASS, None, "Empty clause", elapsed_us)

        # Match candidate compliance assertions
        match = None
        for pat in (self._pattern_p1, self._pattern_p2a, self._pattern_p2b, self._pattern_p3):
            m = pat.search(clean)
            if m:
                match = m
                break

        if not match:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False, None, SeverityTier.PASS, None, "No compliance pattern matched", elapsed_us
            )

        start_idx = match.start()
        prefix = clean[:start_idx].strip()
        matched_str = match.group(0)

        # 1. Check for intervening negation inside the matched span
        # e.g., "is not disabled", "cannot be disabled"
        if re.search(
            r"\b(?:not|cannot|can't|won't|never|no(?!\s+longer))\b", matched_str, re.IGNORECASE
        ):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                matched_str,
                "Negation intervenes within match span",
                elapsed_us,
            )

        # 2. Check full sentence context (rolling history + current clause) for attribution markers
        context_text = " ".join(list(sentence_history or []) + [clean])
        if ATTRIBUTION_REGEX.search(context_text):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                is_breach=True,
                breach_type="deontic_capitulation",
                severity=SeverityTier.TIER_2_SOFT,
                matched_text=matched_str,
                reason=(
                    "Attribution marker detected in sentence context; "
                    "downgraded to Tier 2 soft ground"
                ),
                elapsed_us=elapsed_us,
            )

        # 3. Check preceding 6-token lookback window for negation or hedging
        preceding_tokens = [tok.lower().strip(".,;:!?\"'") for tok in prefix.split() if tok]
        window = preceding_tokens[-6:] if len(preceding_tokens) >= 6 else preceding_tokens

        # Direct token membership in prefix
        for i, tok in enumerate(window):
            if tok == "no" and i + 1 < len(window) and window[i + 1] == "longer":
                continue
            if tok in NEGATION_TOKENS:
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return GateResult(
                    False,
                    None,
                    SeverityTier.PASS,
                    matched_str,
                    f"Negation token '{tok}' in lookback window",
                    elapsed_us,
                )
            if tok in HEDGE_TOKENS:
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return GateResult(
                    False,
                    None,
                    SeverityTier.PASS,
                    matched_str,
                    f"Hedge token '{tok}' in lookback window",
                    elapsed_us,
                )

        # Multi-word phrase check in preceding text
        preceding_text = " ".join(window)
        if re.search(NEGATION_PHRASES, preceding_text, re.IGNORECASE):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                matched_str,
                "Negation phrase in lookback window",
                elapsed_us,
            )
        if re.search(HEDGE_PHRASES, preceding_text, re.IGNORECASE):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                matched_str,
                "Hedge phrase in lookback window",
                elapsed_us,
            )

        # All four conditions hold -> Tier 1 Terminal Abort candidate
        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        return GateResult(
            is_breach=True,
            breach_type="deontic_capitulation",
            severity=SeverityTier.TIER_1_ABORT,
            matched_text=matched_str,
            reason=f"Affirmative policy capitulation assertion: '{matched_str}'",
            elapsed_us=elapsed_us,
        )


class TruthInReceiptMatcher:
    """
    Validates that claims of stateful side effects correspond to verified ToolReceipts.
    Handles contractions, filler idioms, quantifiers, and compound targets.
    """

    ACTION_VERBS = (
        r"(?:deleted|created|modified|executed|ran|installed|removed|sent|uploaded|fetched|"
        r"saved|wrote|posted|rebooted|booked|placed|processed|started|closed|copied|moved)"
    )

    STEM_MAP = {
        "deleted": "delete",
        "created": "create",
        "modified": "modify",
        "executed": "execute",
        "ran": "run",
        "installed": "install",
        "removed": "remove",
        "sent": "send",
        "uploaded": "upload",
        "fetched": "fetch",
        "saved": "save",
        "wrote": "write",
        "posted": "post",
        "rebooted": "reboot",
        "booked": "book",
        "placed": "place",
        "processed": "process",
        "started": "start",
        "closed": "close",
        "copied": "copy",
        "moved": "move",
    }

    # Past-session temporal markers: recollections of PRIOR verified actions are
    # grounded by long-term memory (A1), not by current-turn ToolReceipts. The
    # truth-in-receipt gate (D-BRAIN-04) only governs claims about THIS turn.
    PAST_CONTEXT_PATTERN = re.compile(
        r"\b(?:"
        r"last\s+session|previous\s+session|prior\s+session|earlier\s+session|"
        r"a\s+few\s+days?\s+ago|days?\s+ago|weeks?\s+ago|yesterday|"
        r"last\s+week|previously|in\s+the\s+past|earlier\s+on|"
        r"records?\s+(?:from|show|showing|indicate)|my\s+records|"
        r"(?:information|evidence|entries|logs?)\s+(?:from|show|showing|indicate)|"
        r"memor(?:y|ies)\s+(?:from|show|showing)|from\s+our\s+history|"
        r"in\s+our\s+history|histor(?:y|ical)\s+records?"
        r")\b",
        re.IGNORECASE,
    )

    # Idiomatic non-action filter to prevent false aborts on figurative language
    IDIOMATIC_NON_ACTION_PATTERN = re.compile(
        r"\b(?:"
        r"ran\s+(?:into|out\s+of|across|short|afoul|(?:a\s+)?(?:\w+\s+)?check)|"
        r"saved\s+(?:the\s+day|face|money|time|trouble)|"
        r"sent\s+(?:my\s+|our\s+|a\s+|warm\s+)*(?:regards|condolences|wishes|love|greetings?)|"
        r"started\s+(?:to\s+\w+|thinking|wondering|feeling)|"
        r"closed\s+(?:my|our)\s+eyes|"
        r"placed\s+(?:my\s+|our\s+|their\s+|his\s+|her\s+)?(?:trust|faith|emphasis|focus|bets?|confidence)\s+in"
        r")\b",
        re.IGNORECASE,
    )

    # Hedge-phrase pattern: epistemic uncertainty suppresses the receipt check.
    HEDGE_PATTERN = re.compile(
        r"\b(?:I\s+think\s+I|I\s+believe\s+I|I\s+(?:may|might|could)\s+have|"
        r"not\s+sure\s+(?:if|whether)|not\s+certain\s+(?:if|whether)|"
        r"perhaps\s+I|maybe\s+I)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._action_pattern = re.compile(
            r"\b(?:I|it)(?:\s+have|\'ve|\s+did|\s+was)?\s+"
            r"(?:gone\s+ahead\s+and\s+|just\s+|already\s+|successfully\s+)?"
            rf"({self.ACTION_VERBS})\s+(.+)",
            re.IGNORECASE,
        )
        self._future_pattern = re.compile(
            r"\b(?:about\s+to|going\s+to|will|plan(?:ning)?\s+to)\b",
            re.IGNORECASE,
        )

    def evaluate_clause(
        self, clause: str, verified_receipts: Sequence[dict[str, JsonValue]]
    ) -> GateResult:
        t0 = time.perf_counter()

        # 1. Reject future / intentional framing (not a completed past-tense action)
        if self._future_pattern.search(clause):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Future/intentional framing (not a completed action)",
                elapsed_us,
            )

        # 2. Reject figurative or idiomatic expressions
        if self.IDIOMATIC_NON_ACTION_PATTERN.search(clause):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Idiomatic/figurative non-action phrasing",
                elapsed_us,
            )

        # 3. Reject hedged / epistemic claims (speaker uncertain → not asserting)
        if self.HEDGE_PATTERN.search(clause):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Hedged/epistemic claim — speaker is not asserting a completed action",
                elapsed_us,
            )

        m = self._action_pattern.search(clause)
        if not m:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "No completed action claim matched",
                elapsed_us,
            )

        # Past-session recollection exemption: claims framed as recollections of
        # PRIOR sessions are grounded by long-term memory, not current-turn
        # receipts. Only current-turn action claims require receipt verification.
        if self.PAST_CONTEXT_PATTERN.search(clause):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                m.group(0) if m else None,
                "Past-session recollection (out of scope for current-turn receipts)",
                elapsed_us,
            )

        # Check if the action claim is within the scope of a preceding negation or abstention phrase
        prefix = clause[: m.start()].lower()
        if re.search(
            r"\b(?:no|not|never|don't|do\s+not|didn't|did\s+not|haven't|have\s+not|without|denied)\b",
            prefix,
        ):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Action claim is negated in lookback window",
                elapsed_us,
            )

        action_verb = m.group(1).lower()
        stem = self.STEM_MAP.get(action_verb, action_verb)
        remainder = m.group(2).strip()

        # Clean trailing adverbial / prepositional phrases
        remainder = re.sub(
            r"\s+(?:for\s+you|as\s+requested|now|for\s+your\s+records|from\s+the\s+workspace)[\.!]?$",
            "",
            remainder,
            flags=re.IGNORECASE,
        )
        remainder = re.sub(r"^\s*both\s+", "", remainder, flags=re.IGNORECASE)

        # Split multiple conjuncts (e.g. "both config file and backup archive")
        raw_targets = [t.strip() for t in re.split(r"\s+and\s+|\s*,\s*", remainder) if t.strip()]
        clean_targets = []
        for t in raw_targets:
            clean = re.sub(
                r"^(?:the|a|an|your|my|our|this|that|these|those)\s+",
                "",
                t,
                flags=re.IGNORECASE,
            ).strip(".,!?;: ")
            if clean:
                clean_targets.append(clean)

        # Verify all claimed objects have corresponding ToolReceipts
        ungrounded = []
        for target_obj in clean_targets:
            target_lower = target_obj.lower()
            matched = False
            for r in verified_receipts:
                r_action = str(r.get("action", "")).lower()
                r_target = str(r.get("target", r.get("path", ""))).lower()
                action_ok = (
                    (stem in r_action) or (action_verb in r_action) or (r_action in action_verb)
                )
                target_ok = (target_lower in r_target) or (r_target in target_lower)
                if action_ok and target_ok:
                    matched = True
                    break
            if not matched:
                ungrounded.append(target_obj)

        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        if ungrounded:
            return GateResult(
                is_breach=True,
                breach_type="ungrounded_action",
                severity=SeverityTier.TIER_1_ABORT,
                matched_text=m.group(0),
                reason=(
                    f"Claimed action '{action_verb}' on ungrounded object(s) {ungrounded} "
                    "without matching ToolReceipt"
                ),
                elapsed_us=elapsed_us,
            )

        return GateResult(
            False,
            None,
            SeverityTier.PASS,
            m.group(0),
            "Action claim verified by ToolReceipt",
            elapsed_us,
        )


WHITELISTED_DOC_DOMAINS: frozenset[str] = frozenset(
    {
        "github.com",
        "docs.python.org",
        "python.org",
        "pypi.org",
        "wikipedia.org",
        "en.wikipedia.org",
        "w3.org",
        "www.w3.org",
        "example.com",
    }
)

URL_EXTRACTION_REGEX = re.compile(
    r"(?:https?://[^\s<>\"'()]+|\b[a-zA-Z0-9.-]+\.(?:com|org|net|gov|edu|mil|int|io|ai|co|ph|uk|de|ca|judiciary)(?:/[^\s<>\"'()]+)?\b)",
    re.IGNORECASE,
)


def canonicalize_citation_url(raw_url: str) -> str:
    cleaned = raw_url.rstrip(".,;:!?'\")>]")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    try:
        parsed = urllib.parse.urlsplit(cleaned)
        netloc = parsed.netloc.lower().split(":")[0]
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme.lower()}://{netloc}{path}"
    except Exception as exc:
        logger.debug("canonicalize_citation_url_failed", error=str(exc))
        return cleaned.lower().rstrip("/")


class CitationProvenanceMatcher:
    """
    Validates that URLs and official citations cited in generated assistant text
    have verified provenance in ToolReceipts, EpistemicContext, or verified tool output.
    Prevents hallucination of fake authoritative URLs (Dimension 7B Provenance Invariant).
    """

    def __init__(self, doc_whitelist: frozenset[str] | None = None) -> None:
        self.doc_whitelist = doc_whitelist or WHITELISTED_DOC_DOMAINS

    def evaluate_clause(self, clause: str, allowed_urls: Sequence[str] | None = None) -> GateResult:
        t0 = time.perf_counter()
        clean = clause.strip()
        if not clean:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, SeverityTier.PASS, None, "Empty clause", elapsed_us)

        # Normalize allowed URLs into canonical set
        canon_allowed: set[str] = set()
        allowed_domains: set[str] = set()
        if allowed_urls:
            for u in allowed_urls:
                if not u:
                    continue
                c = canonicalize_citation_url(str(u))
                canon_allowed.add(c)
                try:
                    p = urllib.parse.urlsplit(c)
                    if p.netloc:
                        allowed_domains.add(p.netloc.lower())
                except Exception as exc:
                    logger.debug("extract_domain_failed", error=str(exc))

        # Find candidate citations in clause
        matches = URL_EXTRACTION_REGEX.findall(clean)
        for raw_match in matches:
            # Reject email addresses (preceded by @)
            match_idx = clean.find(raw_match)
            if match_idx > 0 and clean[match_idx - 1] == "@":
                continue

            cleaned_url = raw_match.rstrip(".,;:!?'\")>]")
            canon = canonicalize_citation_url(cleaned_url)

            try:
                parsed = urllib.parse.urlsplit(canon)
                netloc = parsed.netloc.lower()
            except Exception as exc:
                logger.debug("parse_canon_url_failed", error=str(exc))
                netloc = ""

            # Check whitelist exemptions (docs, standard educational/dev domains)
            if any(netloc == wl or netloc.endswith("." + wl) for wl in self.doc_whitelist):
                continue

            # Check local development ports / services (devops context)
            if netloc in ("localhost", "127.0.0.1") or netloc.startswith(
                ("localhost:", "127.0.0.1:")
            ):
                if (
                    canon in canon_allowed
                    or (
                        ":" in cleaned_url
                        and not cleaned_url.startswith(
                            ("http://localhost:80/", "https://localhost:443/")
                        )
                    )
                    or any("localhost" in a or "127.0.0.1" in a for a in canon_allowed)
                ):
                    continue

            # Check exact match against verified receipts
            if canon in canon_allowed:
                continue

            # Check if citing a parent section or root of an allowed deep URL
            if any(a.startswith(canon) for a in canon_allowed):
                continue

            # Check if an allowed URL was registered as an explicit directory path (ending in '/')
            if any(a.endswith("/") and canon.startswith(a) for a in canon_allowed):
                continue

            # Ungrounded citation detected!
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                is_breach=True,
                breach_type="ungrounded_citation",
                severity=SeverityTier.TIER_1_ABORT,
                matched_text=cleaned_url,
                reason=(
                    f"Emitted ungrounded citation URL '{cleaned_url}' without verified "
                    "provenance in tool receipts or epistemic context"
                ),
                elapsed_us=elapsed_us,
            )

        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        return GateResult(
            False,
            None,
            SeverityTier.PASS,
            None,
            "All citations verified or none present",
            elapsed_us,
        )


class OutputSupervisorSession[ChunkT]:
    """
    Manages stateful streaming output supervision across clauses in an interactive turn.
    Implements:
    1. Rolling sentence history buffer (for cross-clause attribution detection).
    2. One-clause lookahead buffer (delayed commit for Tier 1 candidates).
    3. Session-level hysteresis (escalates repeated Tier 2 security hits).
    4. Sequential chunk emission on downgrade (preserving Kokoro prosody).
    5. Session-scoped allowed URLs for citation provenance verification.
    """

    def __init__(
        self,
        deontic_matcher: DeonticAssertionMatcher | None = None,
        truth_matcher: TruthInReceiptMatcher | None = None,
        citation_matcher: CitationProvenanceMatcher | None = None,
    ) -> None:
        self.deontic_matcher = deontic_matcher or DeonticAssertionMatcher()
        self.truth_matcher = truth_matcher or TruthInReceiptMatcher()
        self.citation_matcher = citation_matcher or CitationProvenanceMatcher()
        self.sentence_history: list[str] = []
        self.pending_tier1_chunk: tuple[ChunkT, GateResult] | None = None
        self.session_tier2_security_hits: int = 0
        self.allowed_urls: set[str] = set()
        self.turn_has_stalled: bool = False
        self._refutation_regex = re.compile(
            r"\b(?:not|cannot|can't|won't|never|refuse|in\s+your\s+dreams|not\s+going\s+to)\b",
            re.IGNORECASE,
        )

    def register_allowed_urls(self, urls: Sequence[str]) -> None:
        """Registers verified URLs into session-scoped allowed citations."""
        for u in urls:
            if u and isinstance(u, str):
                self.allowed_urls.add(u.strip())

    def feed_chunk(
        self,
        chunk_item: ChunkT,
        clause_text: str,
        verified_receipts: Sequence[dict[str, JsonValue]] | None = None,
    ) -> tuple[list[tuple[ChunkT, GateResult]], bool]:
        """
        Feeds a streamed clause chunk into the session supervisor.
        Returns:
            (emitted_chunks, should_abort)
            where emitted_chunks is a list of (chunk_item, gate_result) to dispatch to TTS.
        """
        emitted: list[tuple[ChunkT, GateResult]] = []

        # Check stalling rhetorical question evasion (bureaucracy filter)
        if STALLING_RESEARCH_PATTERN.search(clause_text):
            self.turn_has_stalled = True
            return ([], False)

        # 1. Check pending Tier-1 lookahead buffer against incoming clause
        if self.pending_tier1_chunk is not None:
            pending_item, pending_res = self.pending_tier1_chunk
            # Does incoming clause refute the pending claim?
            has_refutation = bool(
                self._refutation_regex.search(clause_text) or ATTRIBUTION_REGEX.search(clause_text)
            )

            if has_refutation:
                # Downgrade pending chunk to Tier 2 and release sequentially
                downgraded_res = GateResult(
                    is_breach=True,
                    breach_type=pending_res.breach_type,
                    severity=SeverityTier.TIER_2_SOFT,
                    matched_text=pending_res.matched_text,
                    reason=(
                        f"{pending_res.reason} (downgraded to Tier 2 via next-clause "
                        f"refutation: '{clause_text.strip()}')"
                    ),
                    elapsed_us=pending_res.elapsed_us,
                )
                emitted.append((pending_item, downgraded_res))
                self.pending_tier1_chunk = None
                self._record_tier2_hit()
            else:
                # Confirmed Tier 1 capitulation: abort immediately!
                self.pending_tier1_chunk = None
                return ([], True)

        # 2. Evaluate incoming clause with rolling sentence history
        gate_res = self.deontic_matcher.evaluate_clause(
            clause_text, sentence_history=self.sentence_history
        )

        # Check truth-in-receipt if receipts provided and deontic check did not flag
        if verified_receipts is not None and not gate_res.is_breach:
            receipt_res = self.truth_matcher.evaluate_clause(clause_text, verified_receipts)
            if receipt_res.is_breach:
                # Tier-1 abort is reserved for turns where a STATEFUL tool ran
                # (write/launch/delete/run): only then can a first-person action
                # claim be a current-turn hallucination verifiable in-stream.
                # On read-only turns (memory_search, query_capabilities, ...) or
                # no-tool turns, an action claim is a long-term-memory
                # recollection (A1) or a hallucination deferred to the post-turn
                # functional-coherence checker (F-WO8-19/F-WO8-23).
                stateful_actions = {
                    "write_file",
                    "edit_file",
                    "note_write",
                    "launch_app",
                    "delete_file",
                    "run_python",
                }
                has_stateful = any(
                    str(r.get("action", "")) in stateful_actions for r in verified_receipts
                )
                if not has_stateful:
                    receipt_res = GateResult(
                        is_breach=True,
                        breach_type=receipt_res.breach_type,
                        severity=SeverityTier.TIER_2_SOFT,
                        matched_text=receipt_res.matched_text,
                        reason=(
                            f"{receipt_res.reason} (downgraded to Tier 2: no stateful "
                            "current-turn receipts; recollection/hallucination deferred "
                            "to post-turn coherence check)"
                        ),
                        elapsed_us=receipt_res.elapsed_us,
                    )
                gate_res = receipt_res

        # Check citation provenance against session allowed URLs
        if not gate_res.is_breach:
            cite_res = self.citation_matcher.evaluate_clause(
                clause_text, allowed_urls=list(self.allowed_urls)
            )
            if cite_res.is_breach:
                gate_res = cite_res

        # 3. Handle incoming clause classification
        if gate_res.severity == SeverityTier.TIER_2_SOFT:
            # Check session hysteresis: 3rd hit in session escalates to Tier 1 candidate
            if self.session_tier2_security_hits >= 2:
                gate_res = GateResult(
                    is_breach=True,
                    breach_type=gate_res.breach_type,
                    severity=SeverityTier.TIER_1_ABORT,
                    matched_text=gate_res.matched_text,
                    reason=(
                        f"{gate_res.reason} (escalated to Tier 1 via session hysteresis: "
                        "3rd security hit)"
                    ),
                    elapsed_us=gate_res.elapsed_us,
                )

        if gate_res.severity == SeverityTier.TIER_1_ABORT:
            # Hold candidate in lookahead buffer
            self.pending_tier1_chunk = (chunk_item, gate_res)
        elif gate_res.severity == SeverityTier.TIER_2_SOFT:
            self._record_tier2_hit()
            emitted.append((chunk_item, gate_res))
        else:
            # SeverityTier.PASS
            emitted.append((chunk_item, gate_res))

        # 4. Update sentence rolling history
        clean_t = clause_text.strip()
        self.sentence_history.append(clean_t)
        # Reset on terminal sentence punctuation
        if clean_t and clean_t[-1] in (".", "!", "?"):
            self.sentence_history.clear()
        elif clean_t.endswith("..."):
            self.sentence_history.clear()

        return (emitted, False)

    def flush(self) -> tuple[list[tuple[ChunkT, GateResult]], bool]:
        """
        Called at end of stream.
        If a Tier-1 candidate was held with no subsequent refutation, commit abort.
        """
        if self.pending_tier1_chunk is not None:
            self.pending_tier1_chunk = None
            return ([], True)
        return ([], False)

    def reset_turn(self) -> None:
        """Resets turn-level buffers; preserves session-level hysteresis and allowed_urls."""
        self.sentence_history.clear()
        self.pending_tier1_chunk = None
        self.turn_has_stalled = False

    def _record_tier2_hit(self) -> None:
        self.session_tier2_security_hits += 1
