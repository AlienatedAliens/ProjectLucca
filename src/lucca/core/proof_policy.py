"""
Project Lucca — Standards-of-Proof Policy Table
WO-21 Phase 1 (The Defeasible Rung) / Spec D-REAS-09

Maps belief consumers to their required standard of proof using legal-analogous burdens:
- SPECULATION (0.0): May be voiced, but only with an explicit "I'm guessing" hedge —
  never stated as belief, never committed to long-term memory.
- BALANCE_OF_PROBABILITIES (0.50): More likely than not; acceptable for casual conversational mention.
- CLEAR_AND_CONVINCING (0.75): High probability with solid grounding; required to commit an INFERRED fact.
- BEYOND_REASONABLE_DOUBT (0.95): Virtual epistemic certainty; required for unhedged assertions and irreversible actions.
Fail-closed default: unknown consumers require BEYOND_REASONABLE_DOUBT (0.95).
"""

from typing import Final

import structlog

from lucca.core.schemas import PROOF_STANDARDS, ProofStandard, standard_for_confidence

logger = structlog.get_logger(__name__)

# Consumer -> Required ProofStandard policy table
POLICY_TABLE: Final[dict[str, ProofStandard]] = {
    "casual_mention": ProofStandard.BALANCE_OF_PROBABILITIES,
    "memory_commit_inferred": ProofStandard.CLEAR_AND_CONVINCING,
    "unhedged_assertion": ProofStandard.BEYOND_REASONABLE_DOUBT,
    "irreversible_action": ProofStandard.BEYOND_REASONABLE_DOUBT,
}


def required_standard(consumer: str) -> ProofStandard:
    """Returns the required ProofStandard for a consumer context.

    Fail-closed: returns BEYOND_REASONABLE_DOUBT for any unregistered consumer.
    """
    return POLICY_TABLE.get(consumer, ProofStandard.BEYOND_REASONABLE_DOUBT)


def required_threshold(consumer: str) -> float:
    """Returns the minimum confidence threshold required for a consumer context."""
    return PROOF_STANDARDS[required_standard(consumer)]


def meets_standard(confidence: float, consumer: str) -> bool:
    """Checks whether an evidential confidence score satisfies the consumer's required standard."""
    return confidence >= required_threshold(consumer)


def format_inferred_label(confidence: float) -> str:
    """Formats the human-readable standard label for prompt context display.

    Example: 'inferred, confidence 0.82 — clear and convincing'
    """
    std = standard_for_confidence(confidence)
    return f"inferred, confidence {confidence:.2f} \u2014 {std.value}"
