"""
Project Lucca — Belnap Latent Investigator (Module 10 / WO-33 & WO-43 Phase 1)
Spec: plans/2026-10-03_wo29_neurosymbolic_program_synthesis_and_15_module_cognitive_ladder.md §2
      plans/wo43_refactor_and_power/01_PHASE1_HYGIENE_BELNAP_NLI_AND_SANDBOX_WIRING_SPEC.md §2

Implements Belnap-Dunn four-valued lattice logic (4 = {T, F, ⊥, ⊤}) and non-destructive
epistemic probing across memory, filesystem, and conversational hypotheses.
Prevents destructive state overwrites and provides grounded epistemic clarification.

Invariants:
- Zero-Any typing discipline strictly enforced (D-AUD-01).
- Hardware budget: ΔVRAM = 0 MB, ΔRAM <= 20 MB.
- Sub-millisecond lattice and non-destructive probe latency.
- Generates structured, non-destructive user clarification prompts on ⊤ (contradiction).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, StrEnum
import os
from pathlib import Path
import re
import time

from pydantic import BaseModel, Field
import structlog

from lucca.core.schemas import VerifierLabel
from lucca.ports import SemanticVerifierPort

logger = structlog.get_logger(__name__)

_NEGATION_TOKENS: frozenset[str] = frozenset(
    {"not", "never", "no", "false", "disabled", "cannot", "none", "unsupported"}
)
_STOP_TOKENS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "by",
        "from",
        "that",
        "this",
        "it",
        "be",
        "as",
        "or",
        "and",
    }
)


class BelnapValue(StrEnum):
    """
    The four truth values of the Belnap-Dunn bilattice FOUR:
    - TRUE (T): Evidence for truth, no evidence for falsity.
    - FALSE (F): Evidence for falsity, no evidence for truth.
    - NEITHER / UNKNOWN (BOT, ⊥): Unobserved / unknown; no evidence either way.
    - BOTH / CONFLICT (TOP, ⊤): Contradiction / conflicting evidence for both truth and falsity.
    """

    TRUE = "T"
    FALSE = "F"
    UNKNOWN = "BOT"
    CONFLICT = "TOP"
    NEITHER = "BOT"  # ⊥ (bottom / unobserved)
    BOTH = "TOP"     # ⊤ (top / contradiction)


def belnap_negation(val: BelnapValue) -> BelnapValue:
    """Truth negation (~): inverts TRUE <-> FALSE, preserves NEITHER (BOT) and BOTH (TOP)."""
    if val == BelnapValue.TRUE:
        return BelnapValue.FALSE
    if val == BelnapValue.FALSE:
        return BelnapValue.TRUE
    return val


def information_meet(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """
    Information meet (∧_k): greatest lower bound in knowledge ordering (BOT <= {T, F} <= TOP).
    Represents the shared information between two evidence sources.
    """
    if a == b:
        return a
    if a == BelnapValue.NEITHER or b == BelnapValue.NEITHER:
        return BelnapValue.NEITHER
    if a == BelnapValue.BOTH:
        return b
    if b == BelnapValue.BOTH:
        return a
    return BelnapValue.NEITHER


def information_join(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """
    Information join (∨_k): least upper bound in knowledge ordering (BOT <= {T, F} <= TOP).
    Combines evidence from two independent sources.
    Combining TRUE and FALSE produces BOTH (⊤, contradiction).
    """
    if a == b:
        return a
    if a == BelnapValue.NEITHER:
        return b
    if b == BelnapValue.NEITHER:
        return a
    if a == BelnapValue.BOTH or b == BelnapValue.BOTH:
        return BelnapValue.BOTH
    return BelnapValue.BOTH


def truth_meet(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """
    Truth meet (∧_t): logical AND in the Belnap truth ordering (F <= {BOT, TOP} <= T).
    """
    if a == BelnapValue.FALSE or b == BelnapValue.FALSE:
        return BelnapValue.FALSE
    if a == BelnapValue.TRUE:
        return b
    if b == BelnapValue.TRUE:
        return a
    if a == b:
        return a
    return BelnapValue.FALSE


def truth_join(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """
    Truth join (∨_t): logical OR in the Belnap truth ordering (F <= {BOT, TOP} <= T).
    """
    if a == BelnapValue.TRUE or b == BelnapValue.TRUE:
        return BelnapValue.TRUE
    if a == BelnapValue.FALSE:
        return b
    if b == BelnapValue.FALSE:
        return a
    if a == b:
        return a
    return BelnapValue.TRUE


# Canonical algebraic aliases shared with EpistemicSearchCascade (WO-43 Phase 1 deduplication)
belnap_meet_k = information_meet
belnap_join_k = information_join
belnap_meet_t = truth_meet
belnap_join_t = truth_join


def pool_evidence(values: Sequence[BelnapValue]) -> BelnapValue:
    """Pools multiple evidence items using Belnap information join (sum of knowledge)."""
    res = BelnapValue.UNKNOWN
    for v in values:
        res = information_join(res, v)
    return res


def has_structural_proposition_conflict(premise: str, hypothesis: str) -> bool:
    """Detects lexical/polarity/value divergence on a shared subject+predicate frame."""
    p_norm = premise.strip().lower()
    h_norm = hypothesis.strip().lower()
    if not p_norm or not h_norm or p_norm == h_norm:
        return False

    neg_phrases = ("no longer", "not ", "never ")
    p_words = re.findall(r"[a-z0-9_.-]+", p_norm)
    h_words = re.findall(r"[a-z0-9_.-]+", h_norm)
    p_has_neg = any(w in _NEGATION_TOKENS for w in p_words) or any(
        phrase in p_norm for phrase in neg_phrases
    )
    h_has_neg = any(w in _NEGATION_TOKENS for w in h_words) or any(
        phrase in h_norm for phrase in neg_phrases
    )
    if p_has_neg != h_has_neg:
        return True

    content_p = set(p_words) - _STOP_TOKENS - _NEGATION_TOKENS
    content_h = set(h_words) - _STOP_TOKENS - _NEGATION_TOKENS
    shared = content_p & content_h
    if len(shared) >= 2:
        nums_p = set(re.findall(r"\b\d+(?:\.\d+)?\b", p_norm))
        nums_h = set(re.findall(r"\b\d+(?:\.\d+)?\b", h_norm))
        if nums_p and nums_h and nums_p != nums_h:
            return True
        if len(p_words) == len(h_words) and len(p_words) >= 3:
            diffs = [
                (wa, wb) for wa, wb in zip(p_words, h_words, strict=False) if wa != wb
            ]
            if len(diffs) == 1:
                return True
        if len(p_words) >= 3 and len(h_words) >= 3 and p_words[:2] == h_words[:2]:
            if p_words[2:] != h_words[2:]:
                return True
    return False


class ProbeTargetType(str, Enum):
    """Domain category for the non-destructive latent probe."""

    FILESYSTEM_PATH = "FILESYSTEM_PATH"
    ENVIRONMENT_VARIABLE = "ENVIRONMENT_VARIABLE"
    CONVERSATIONAL_PREMISE = "CONVERSATIONAL_PREMISE"
    CONFIG_KEY = "CONFIG_KEY"
    MEMORY_ASSERTION = "MEMORY_ASSERTION"


class ProbeActionRecommendation(str, Enum):
    """Actionable directive yielded by the Belnap probe evaluation."""

    ACCEPT_AS_TRUE = "ACCEPT_AS_TRUE"
    ACCEPT_AS_FALSE = "ACCEPT_AS_FALSE"
    SOLICIT_USER_CLARIFICATION = "SOLICIT_USER_CLARIFICATION"
    INSPECT_EXTERNAL_STATE = "INSPECT_EXTERNAL_STATE"
    NO_OP_INSUFFICIENT_EVIDENCE = "NO_OP_INSUFFICIENT_EVIDENCE"


class LatentProbeRequest(BaseModel):
    """Specification of a non-destructive query to test state consistency."""

    probe_id: str
    target_type: ProbeTargetType
    target_identifier: str
    claim_assertion: str
    context: dict[str, str] = Field(default_factory=dict)
    expected_truth_polarity: bool = True


class LatentProbeResponse(BaseModel):
    """Mechanical result of an executed non-destructive latent probe."""

    probe_id: str
    belnap_value: BelnapValue
    confidence: float
    evidence_receipt: str
    recommendation: ProbeActionRecommendation
    clarification_prompt: str | None = None
    probe_latency_ms: float = 0.0


class BelnapLatentInvestigator:
    """
    Investigates latent environment state drift and conversational contradictions
    without destructive side effects.
    """

    def __init__(self, verifier: SemanticVerifierPort | None = None) -> None:
        self.verifier = verifier

    @staticmethod
    def evaluate_nli_verdict(
        verdict_or_result: object,
        has_lexical_conflict: bool = False,
    ) -> BelnapValue:
        """
        Maps a VerificationResult or VerifierLabel to a Belnap-Dunn 4-valued truth state.

        Fail-closed epistemic semantics (WO-43 Phase 1.2):
        - CONTRADICTION -> BelnapValue.BOTH (⊤) if prior/lexical evidence exists, else FALSE.
        - ENTAILMENT / CONSISTENT -> BelnapValue.TRUE.
        - UNCERTAIN or degraded=True -> BelnapValue.BOTH (⊤) if has_lexical_conflict is True,
          else BelnapValue.NEITHER (⊥, epistemic ignorance).
        """
        degraded = bool(getattr(verdict_or_result, "degraded", False))
        raw_label = getattr(verdict_or_result, "label", verdict_or_result)
        label_str = str(getattr(raw_label, "value", raw_label)).upper()

        if degraded or "UNCERTAIN" in label_str:
            return BelnapValue.BOTH if has_lexical_conflict else BelnapValue.NEITHER
        if "CONTRADICTION" in label_str:
            return BelnapValue.BOTH if has_lexical_conflict else BelnapValue.FALSE
        if "ENTAILMENT" in label_str or "CONSISTENT" in label_str:
            return BelnapValue.TRUE
        return BelnapValue.BOTH if has_lexical_conflict else BelnapValue.NEITHER

    def investigate_filesystem(
        self,
        path: Path | str,
        claim_exists: bool = True,
        probe_id: str = "fs_probe",
    ) -> LatentProbeResponse:
        """
        Non-destructively probes the host filesystem for path existence
        and maps evidence to a Belnap truth valuation.
        """
        t0 = time.perf_counter()
        p = Path(path)
        actual_exists = p.exists()

        if claim_exists:
            if actual_exists:
                val = BelnapValue.TRUE
                rec = ProbeActionRecommendation.ACCEPT_AS_TRUE
                receipt = f"Path '{p}' verified present on filesystem."
            else:
                val = BelnapValue.FALSE
                rec = ProbeActionRecommendation.ACCEPT_AS_FALSE
                receipt = f"Path '{p}' verified absent on filesystem."
        else:
            if not actual_exists:
                val = BelnapValue.TRUE
                rec = ProbeActionRecommendation.ACCEPT_AS_TRUE
                receipt = f"Path '{p}' verified absent as expected."
            else:
                val = BelnapValue.FALSE
                rec = ProbeActionRecommendation.ACCEPT_AS_FALSE
                receipt = f"Path '{p}' contradicts negative claim; path exists."

        elapsed = (time.perf_counter() - t0) * 1000.0
        return LatentProbeResponse(
            probe_id=probe_id,
            belnap_value=val,
            confidence=1.0,
            evidence_receipt=receipt,
            recommendation=rec,
            probe_latency_ms=elapsed,
        )

    def investigate_env_var(
        self,
        var_name: str,
        expected_val: str | None = None,
        probe_id: str = "env_probe",
    ) -> LatentProbeResponse:
        """
        Non-destructively probes environment variables.
        """
        t0 = time.perf_counter()
        val_in_env = os.environ.get(var_name)

        if val_in_env is None:
            val = BelnapValue.NEITHER
            rec = ProbeActionRecommendation.NO_OP_INSUFFICIENT_EVIDENCE
            receipt = f"Environment variable '{var_name}' is unset."
        elif expected_val is not None:
            if val_in_env == expected_val:
                val = BelnapValue.TRUE
                rec = ProbeActionRecommendation.ACCEPT_AS_TRUE
                receipt = f"Environment variable '{var_name}' matches expected value."
            else:
                val = BelnapValue.BOTH  # Contradiction: exists but differs
                rec = ProbeActionRecommendation.SOLICIT_USER_CLARIFICATION
                receipt = (
                    f"Environment variable '{var_name}' has value '{val_in_env}', "
                    f"expected '{expected_val}'."
                )
        else:
            val = BelnapValue.TRUE
            rec = ProbeActionRecommendation.ACCEPT_AS_TRUE
            receipt = f"Environment variable '{var_name}' is set."

        elapsed = (time.perf_counter() - t0) * 1000.0
        return LatentProbeResponse(
            probe_id=probe_id,
            belnap_value=val,
            confidence=1.0,
            evidence_receipt=receipt,
            recommendation=rec,
            probe_latency_ms=elapsed,
        )

    def investigate_memory_conflict(
        self,
        existing_premise: str,
        candidate_hypothesis: str,
        probe_id: str = "mem_probe",
    ) -> LatentProbeResponse:
        """
        Evaluates conversational or memory conflict between an existing premise
        and a new candidate hypothesis.
        """
        t0 = time.perf_counter()
        lexical_conflict = has_structural_proposition_conflict(
            existing_premise, candidate_hypothesis
        )

        if self.verifier is not None:
            try:
                v_res = self.verifier.check_consistency(
                    premise=existing_premise,
                    hypothesis=candidate_hypothesis,
                )
                if not v_res.degraded:
                    if v_res.label == VerifierLabel.CONTRADICTION:
                        clarification = self.generate_clarification_prompt(
                            existing_premise, candidate_hypothesis
                        )
                        elapsed = (time.perf_counter() - t0) * 1000.0
                        return LatentProbeResponse(
                            probe_id=probe_id,
                            belnap_value=BelnapValue.BOTH,
                            confidence=0.95,
                            evidence_receipt=(
                                f"Semantic verifier flagged direct contradiction ({v_res.label})."
                            ),
                            recommendation=ProbeActionRecommendation.SOLICIT_USER_CLARIFICATION,
                            clarification_prompt=clarification,
                            probe_latency_ms=elapsed,
                        )
                    if v_res.label in (VerifierLabel.ENTAILMENT, VerifierLabel.CONSISTENT):
                        elapsed = (time.perf_counter() - t0) * 1000.0
                        return LatentProbeResponse(
                            probe_id=probe_id,
                            belnap_value=BelnapValue.TRUE,
                            confidence=0.95,
                            evidence_receipt="Candidate hypothesis is entailed by existing memory.",
                            recommendation=ProbeActionRecommendation.ACCEPT_AS_TRUE,
                            probe_latency_ms=elapsed,
                        )
                # When degraded or UNCERTAIN, map via fail-closed Belnap evaluation
                mapped = self.evaluate_nli_verdict(v_res, has_lexical_conflict=lexical_conflict)
                if mapped == BelnapValue.BOTH:
                    clarification = self.generate_clarification_prompt(
                        existing_premise, candidate_hypothesis
                    )
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    return LatentProbeResponse(
                        probe_id=probe_id,
                        belnap_value=BelnapValue.BOTH,
                        confidence=0.75,
                        evidence_receipt=(
                            "NLI uncertain/degraded on lexically conflicting memory slot; "
                            "failing closed to Belnap TOP conflict."
                        ),
                        recommendation=ProbeActionRecommendation.SOLICIT_USER_CLARIFICATION,
                        clarification_prompt=clarification,
                        probe_latency_ms=elapsed,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("latent_verifier_error", error=str(exc))

        p_norm = existing_premise.strip().lower()
        h_norm = candidate_hypothesis.strip().lower()

        if p_norm == h_norm:
            val = BelnapValue.TRUE
            rec = ProbeActionRecommendation.ACCEPT_AS_TRUE
            receipt = "Identical assertion already exists in memory."
            clarification = None
        elif lexical_conflict:
            val = BelnapValue.BOTH
            rec = ProbeActionRecommendation.SOLICIT_USER_CLARIFICATION
            receipt = "Polarity or value mismatch detected between existing memory and candidate claim."
            clarification = self.generate_clarification_prompt(
                existing_premise, candidate_hypothesis
            )
        else:
            val = BelnapValue.NEITHER
            rec = ProbeActionRecommendation.NO_OP_INSUFFICIENT_EVIDENCE
            receipt = "Novel assertion with neutral overlap."
            clarification = None

        elapsed = (time.perf_counter() - t0) * 1000.0
        return LatentProbeResponse(
            probe_id=probe_id,
            belnap_value=val,
            confidence=0.80,
            evidence_receipt=receipt,
            recommendation=rec,
            clarification_prompt=clarification,
            probe_latency_ms=elapsed,
        )

    def combine_evidence(
        self,
        probes: list[LatentProbeResponse],
        combined_probe_id: str = "combined_probe",
    ) -> LatentProbeResponse:
        """
        Combines multiple probe responses using the Belnap knowledge ordering join (∨_k).
        """
        if not probes:
            return LatentProbeResponse(
                probe_id=combined_probe_id,
                belnap_value=BelnapValue.NEITHER,
                confidence=0.0,
                evidence_receipt="No probe evidence provided.",
                recommendation=ProbeActionRecommendation.NO_OP_INSUFFICIENT_EVIDENCE,
                probe_latency_ms=0.0,
            )

        accumulated_val = probes[0].belnap_value
        total_latency = probes[0].probe_latency_ms
        receipts: list[str] = [probes[0].evidence_receipt]
        clarifications: list[str] = []
        if probes[0].clarification_prompt:
            clarifications.append(probes[0].clarification_prompt)

        for p in probes[1:]:
            accumulated_val = information_join(accumulated_val, p.belnap_value)
            total_latency += p.probe_latency_ms
            receipts.append(p.evidence_receipt)
            if p.clarification_prompt:
                clarifications.append(p.clarification_prompt)

        if accumulated_val == BelnapValue.BOTH:
            rec = ProbeActionRecommendation.SOLICIT_USER_CLARIFICATION
        elif accumulated_val == BelnapValue.TRUE:
            rec = ProbeActionRecommendation.ACCEPT_AS_TRUE
        elif accumulated_val == BelnapValue.FALSE:
            rec = ProbeActionRecommendation.ACCEPT_AS_FALSE
        else:
            rec = ProbeActionRecommendation.NO_OP_INSUFFICIENT_EVIDENCE

        return LatentProbeResponse(
            probe_id=combined_probe_id,
            belnap_value=accumulated_val,
            confidence=min(p.confidence for p in probes),
            evidence_receipt=" | ".join(receipts),
            recommendation=rec,
            clarification_prompt="; ".join(clarifications) if clarifications else None,
            probe_latency_ms=total_latency,
        )

    def generate_clarification_prompt(self, premise: str, hypothesis: str) -> str:
        """
        Constructs a polite, non-destructive spoken clarification prompt when ⊤ occurs.
        """
        return (
            f"I noticed a potential contradiction with what we established earlier: "
            f"'{premise}' vs '{hypothesis}'. Which one should I treat as current?"
        )
