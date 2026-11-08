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

import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Final

import structlog

from lucca.core.config import get_resource_path
from lucca.core.neural_hazard_classifier import get_neural_hazard_classifier
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

def classify_hazard(claim_or_topic: str) -> Hazard:
    """
    Classifies the hazard level of a claim or topic using the OpenVINO NPU 5-class neural classifier
    (WO-41 Phase 4 Milestone 4.1, replacing WO-21 keyword/regex lists).

    Classification taxonomy:
    - HIGH: health, medical, safety, financial, legal, credentials, destructive actions.
    - MEDIUM: technical specs, system configuration, software versions, coding, APIs.
    - LOW: trivia, pop culture, entertainment, games, personal preferences, casual facts.
    - Fail-closed: returns Hazard.HIGH for empty, unknown, or low-confidence claims.
    """
    text = (claim_or_topic or "").strip()
    if not text:
        return Hazard.HIGH

    verdict = get_neural_hazard_classifier().evaluate(text)
    if verdict.hazard_level == "low":
        return Hazard.LOW
    if verdict.hazard_level == "medium":
        return Hazard.MEDIUM
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
    """Checks if text contains user intent to cross-reference or gather more sources
    using the OpenVINO NPU 5-class neural classifier (WO-41 Phase 4 Milestone 4.1).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    return get_neural_hazard_classifier().evaluate(cleaned).is_cross_reference_cmd
