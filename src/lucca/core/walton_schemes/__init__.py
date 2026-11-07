"""
Project Lucca — Walton Argumentation Scheme Evaluators Package (WO-43 Phase 3.1)
"""

from lucca.core.walton_schemes.evaluators import (
    _evaluate_analogy_questions,
    _evaluate_authority_questions,
    _evaluate_consequence_questions,
    _evaluate_precedent_questions,
    _evaluate_sign_questions,
    collect_dispute_evidence,
    collect_independent_corroboration,
    extract_normalized_receipt_text,
)

__all__ = [
    "_evaluate_analogy_questions",
    "_evaluate_authority_questions",
    "_evaluate_consequence_questions",
    "_evaluate_precedent_questions",
    "_evaluate_sign_questions",
    "collect_dispute_evidence",
    "collect_independent_corroboration",
    "extract_normalized_receipt_text",
]
