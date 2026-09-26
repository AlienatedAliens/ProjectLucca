"""
Project Lucca — Standards-of-Proof Policy Table
WO-21 Phase 1 & Phase 3 (The Defeasible Rung) / Spec D-REAS-09

Maps belief consumers and hazard levels to their required standard of proof
using legal-analogous burdens and decision-theoretic risk scaling:
- SPECULATION (0.0): May be voiced, but only with an explicit "I'm guessing" hedge —
  never stated as belief, never committed to long-term memory.
- BALANCE_OF_PROBABILITIES (0.50): More likely than not; acceptable for casual mention
  under low hazard.
- CLEAR_AND_CONVINCING (0.75): High probability with solid grounding; required to commit
  an INFERRED fact.
- BEYOND_REASONABLE_DOUBT (0.95): Virtual epistemic certainty; required for unhedged assertions,
  high-hazard claims, and irreversible actions.

Amendment A (Phase 3): 2-D policy required_standard = f(consumer, hazard).
Irreversible actions always require BEYOND_REASONABLE_DOUBT (0.95).
Fail-closed default: unknown consumers or unknown hazard require BEYOND_REASONABLE_DOUBT (0.95).
"""

import re
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Final

import structlog

from lucca.core.config import get_resource_path
from lucca.core.schemas import PROOF_STANDARDS, ProofStandard, standard_for_confidence

logger = structlog.get_logger(__name__)


class Hazard(StrEnum):
    """Hazard dimension for decision-theoretic proof standards (WO-21 Phase 3 Amendment A)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# 1D Consumer -> Required ProofStandard policy table (Phase 1 backward compatibility)
POLICY_TABLE: Final[dict[str, ProofStandard]] = {
    "casual_mention": ProofStandard.BALANCE_OF_PROBABILITIES,
    "memory_commit_inferred": ProofStandard.CLEAR_AND_CONVINCING,
    "unhedged_assertion": ProofStandard.BEYOND_REASONABLE_DOUBT,
    "irreversible_action": ProofStandard.BEYOND_REASONABLE_DOUBT,
}

# 2D (Consumer, Hazard) -> Required ProofStandard policy table (Phase 3 Amendment A)
POLICY_TABLE_2D: Final[dict[tuple[str, Hazard], ProofStandard]] = {
    # casual_mention: low hazard = 0.50 (balance of probabilities);
    # medium hazard = 0.75 (clear and convincing);
    # high hazard = 0.95 (beyond reasonable doubt).
    ("casual_mention", Hazard.LOW): ProofStandard.BALANCE_OF_PROBABILITIES,
    ("casual_mention", Hazard.MEDIUM): ProofStandard.CLEAR_AND_CONVINCING,
    ("casual_mention", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,

    # memory_commit_inferred: never commits below clear and convincing (Phase 1 invariant);
    # high hazard scales to beyond reasonable doubt.
    ("memory_commit_inferred", Hazard.LOW): ProofStandard.CLEAR_AND_CONVINCING,
    ("memory_commit_inferred", Hazard.MEDIUM): ProofStandard.CLEAR_AND_CONVINCING,
    ("memory_commit_inferred", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,

    # unhedged_assertion: low hazard allows clear and convincing;
    # medium and high require beyond reasonable doubt.
    ("unhedged_assertion", Hazard.LOW): ProofStandard.CLEAR_AND_CONVINCING,
    ("unhedged_assertion", Hazard.MEDIUM): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("unhedged_assertion", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,

    # irreversible_action: ALWAYS beyond reasonable doubt (0.95) regardless of hazard level.
    ("irreversible_action", Hazard.LOW): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("irreversible_action", Hazard.MEDIUM): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("irreversible_action", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,
}

# Hazard classification keyword sets (Phase 3 Amendment A)
_HIGH_HAZARD_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "health",
        "medical",
        "medicine",
        "doctor",
        "hospital",
        "dosage",
        "drug",
        "prescription",
        "symptom",
        "disease",
        "treatment",
        "cure",
        "pain",
        "finance",
        "financial",
        "bank",
        "banking",
        "money",
        "account",
        "credit",
        "debit",
        "wire",
        "transfer",
        "tax",
        "taxes",
        "stock",
        "invest",
        "investment",
        "crypto",
        "bitcoin",
        "wallet",
        "legal",
        "law",
        "lawsuit",
        "court",
        "attorney",
        "contract",
        "delete",
        "destroy",
        "wipe",
        "rm",
        "rmdir",
        "format",
        "drop",
        "truncate",
        "password",
        "secret",
        "token",
        "credential",
        "credentials",
        "key",
        "auth",
        "kill",
        "shut down",
    }
)

_MEDIUM_HAZARD_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "config",
        "configuration",
        "setting",
        "settings",
        "python",
        "version",
        "api",
        "code",
        "install",
        "directory",
        "path",
        "network",
        "port",
        "compiler",
        "runtime",
        "dependency",
        "package",
        "env",
        "environment",
        "git",
        "branch",
        "repo",
        "repository",
        "query",
        "database",
        "table",
        "schema",
        "function",
        "module",
        "class",
        "method",
        "syntax",
        "endpoint",
        "url",
        "server",
        "ip",
        "dns",
        "protocol",
        "docker",
        "container",
    }
)

_LOW_HAZARD_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "trivia",
        "game",
        "games",
        "movie",
        "movies",
        "film",
        "music",
        "song",
        "band",
        "album",
        "food",
        "color",
        "hobby",
        "sport",
        "sports",
        "actor",
        "actress",
        "release",
        "released",
        "birthday",
        "birth",
        "preference",
        "favorite",
        "metal gear",
        "mgs",
        "author",
        "book",
        "novel",
        "character",
        "weather",
        "capital",
        "population",
        "mascot",
        "genre",
        "holiday",
        "quote",
    }
)


_HIGH_HAZARD_PHRASES: Final[tuple[str, ...]] = (
    "wire transfer",
    "credit card",
    "bank account",
    "shut down",
    "rm -rf",
    "drop table",
)

_LOW_HAZARD_PHRASES: Final[tuple[str, ...]] = (
    "metal gear",
    "pop culture",
    "video game",
    "video games",
    "release date",
    "release year",
)


def classify_hazard(claim_or_topic: str) -> Hazard:
    """Classifies the hazard level of a claim or topic (WO-21 Phase 3 Amendment A).

    Classification v1:
    - HIGH: health, medical, safety, financial, legal, credentials, destructive actions.
    - MEDIUM: technical specs, system configuration, software versions, coding, APIs.
    - LOW: trivia, pop culture, entertainment, games, personal preferences, casual facts.
    - Fail-closed: returns Hazard.HIGH for unknown or unclassified claims.
    """
    text = (claim_or_topic or "").strip().lower()
    if not text:
        return Hazard.HIGH

    # Tokenize words
    words = set(re.findall(r"\b[a-z0-9_-]+\b", text))

    # Multi-word phrase checks
    if any(re.search(rf"\b{re.escape(p)}\b", text) for p in _HIGH_HAZARD_PHRASES):
        return Hazard.HIGH

    # Priority 1: High hazard words
    if words & _HIGH_HAZARD_KEYWORDS:
        return Hazard.HIGH

    # Priority 2: Medium hazard words
    if words & _MEDIUM_HAZARD_KEYWORDS:
        return Hazard.MEDIUM

    # Multi-word low hazard phrases
    if any(re.search(rf"\b{re.escape(p)}\b", text) for p in _LOW_HAZARD_PHRASES):
        return Hazard.LOW

    # Priority 3: Low hazard words
    if words & _LOW_HAZARD_KEYWORDS:
        return Hazard.LOW

    # Fail-closed default for unknown claims
    return Hazard.HIGH


def required_standard(
    consumer: str, hazard: Hazard | str | None = None
) -> ProofStandard:
    """Returns the required ProofStandard for a consumer context and optional hazard level.

    Fail-closed: returns BEYOND_REASONABLE_DOUBT for any unregistered consumer or hazard.
    """
    if hazard is not None:
        try:
            h = Hazard(hazard.lower()) if isinstance(hazard, str) else hazard
        except ValueError:
            h = Hazard.HIGH
        return POLICY_TABLE_2D.get((consumer, h), ProofStandard.BEYOND_REASONABLE_DOUBT)
    return POLICY_TABLE.get(consumer, ProofStandard.BEYOND_REASONABLE_DOUBT)


def required_threshold(
    consumer: str, hazard: Hazard | str | None = None
) -> float:
    """Returns the minimum confidence threshold required for a consumer context and hazard."""
    return PROOF_STANDARDS[required_standard(consumer, hazard=hazard)]


def meets_standard(
    confidence: float, consumer: str, hazard: Hazard | str | None = None
) -> bool:
    """Checks whether an evidential confidence score satisfies the consumer's required standard."""
    return confidence >= required_threshold(consumer, hazard=hazard)


def format_inferred_label(confidence: float) -> str:
    """Formats the human-readable standard label for prompt context display.

    Example: 'inferred, confidence 0.82 — clear and convincing'
    """
    std = standard_for_confidence(confidence)
    return f"inferred, confidence {confidence:.2f} \u2014 {std.value}"


DEFAULT_RATIFICATION_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "docs.python.org",
        "en.wikipedia.org",
        "github.com",
        "ars-technica.com",
        "arstechnica.com",
    }
)


def load_ratification_domains(path: Path | str | None = None) -> set[str]:
    """Loads approved domain whitelist for proactive ratification (WO-21 Phase 3)."""
    p = Path(path) if path is not None else get_resource_path("config/domain_whitelist.toml")
    if not p.exists():
        fallback_p = Path("config/domain_whitelist.toml")
        if fallback_p.exists():
            p = fallback_p
        else:
            return set(DEFAULT_RATIFICATION_DOMAINS)

    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
            domains = data.get("ratification_domains", [])
            if isinstance(domains, list):
                return {str(d).strip().lower() for d in domains if str(d).strip()}
    except Exception as exc:  # noqa: BLE001
        logger.debug("load_ratification_domains_failed", path=str(p), error=str(exc))

    return set(DEFAULT_RATIFICATION_DOMAINS)


def is_cross_reference_command(text: str) -> bool:
    """Checks if text contains user intent to cross-reference or gather more sources."""
    cleaned = text.strip().lower()
    cleaned_no_punct = re.sub(r"[^\w\s-]", "", cleaned)
    patterns = (
        r"\bcross[\s-]?reference\b",
        r"\bfind\s+more\s+sources\b",
        r"\bcheck\s+more\s+sources\b",
        r"\bverify\s+(?:that|this|it)\b",
        r"\bfind\s+other\s+sources\b",
    )
    return any(re.search(pat, cleaned_no_punct) for pat in patterns)
