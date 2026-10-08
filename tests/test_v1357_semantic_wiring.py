"""
Integration and gate verification tests for Project Lucca v1.35.7 Phase 3:
Wiring Semantic Verification Across the 7 Subsystems.
Gates: G-V1357-ANALOGY, G-V1357-DIAG, G-V1357-BELNAP, G-V1357-RULE.
"""

from unittest.mock import MagicMock

import pytest

from lucca.core.belief_service import BeliefService
from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.coherence import ToolReceipt, detect_ungrounded_action_claims
from lucca.core.corroboration import critical_questions, Scheme
from lucca.core.memory_commit_service import MemoryCommitService
from lucca.core.schemas import InferenceStep, VerificationResult, VerifierLabel
from lucca.core.self_diagnosis import DiagnosisEngine
from lucca.ports import SemanticVerifierPort
from lucca.reasoning.induction import cluster_phrasings, is_rule_conflict


class MockVerifier(SemanticVerifierPort):
    """Configurable mock verifier for deterministic subsystem testing."""

    def __init__(self, mapping: dict[tuple[str, str], VerifierLabel] | None = None) -> None:
        self.mapping = mapping or {}
        self.calls: list[tuple[str, str]] = []

    def check_consistency(self, *, premise: str, hypothesis: str) -> VerificationResult:
        self.calls.append((premise, hypothesis))
        label = self.mapping.get((premise, hypothesis), VerifierLabel.UNCERTAIN)
        return VerificationResult(
            label=label,
            confidence=0.95 if label != VerifierLabel.UNCERTAIN else 0.50,
            premise=premise,
            hypothesis=hypothesis,
        )


# ============================================================================
# Gate 1: G-V1357-ANALOGY (corroboration.py CQ1)
# ============================================================================


def test_g_v1357_analogy_gate() -> None:
    """
    Gate G-V1357-ANALOGY:
    1. A pair of cases with no shared entailed premise (contradicting cases)
       is rejected by CQ1 (q1_failed=True).
    2. A pair sharing an entailed causal premise is accepted (q1_matches populated).
    """
    # 1. Contradictory cases -> rejected by CQ1
    verifier_reject = MockVerifier(
        {
            ("Case A: System enabled auth", "Case B: System disabled auth"): VerifierLabel.CONTRADICTION,
            ("Case B: System disabled auth", "Case A: System enabled auth"): VerifierLabel.CONTRADICTION,
        }
    )
    step_reject = InferenceStep(
        s="Case A: System enabled auth",
        p="analogous_to",
        o="Case B: System disabled auth",
        premises=["Auth comparison"],
        confidence=0.9,
    )
    res_reject = critical_questions(
        scheme=Scheme.ANALOGY,
        step=step_reject,
        verifier=verifier_reject,
    )
    cq1_res = res_reject[0]
    assert cq1_res.count == 0, "Contradictory analogy must not match CQ1"

    # 2. Relevantly similar / entailed cases -> accepted by CQ1
    verifier_accept = MockVerifier(
        {
            ("System handles HTTP requests", "System handles REST calls"): VerifierLabel.ENTAILMENT,
            ("System handles REST calls", "System handles HTTP requests"): VerifierLabel.ENTAILMENT,
        }
    )
    step_accept = InferenceStep(
        s="System handles HTTP requests",
        p="analogous_to",
        o="System handles REST calls",
        premises=["Protocol comparison"],
        confidence=0.9,
    )
    res_accept = critical_questions(
        scheme=Scheme.ANALOGY,
        step=step_accept,
        verifier=verifier_accept,
    )
    cq1_accept = res_accept[0]
    assert cq1_accept.count > 0, "Entailed analogy must pass CQ1"
    assert "semantic_entailment" in cq1_accept.evidence_entry_ids


# ============================================================================
# Gate 2: G-V1357-DIAG (self_diagnosis.py)
# ============================================================================


def test_g_v1357_diag_gate(tmp_path: object) -> None:
    """
    Gate G-V1357-DIAG:
    An observation text that lexically overlaps a symptom description but
    contradicts it (e.g. 'system temperature is completely normal' vs 'overheating')
    does NOT match that symptom. A genuinely entailing observation DOES match.
    """
    # Create minimal fault model
    toml_path = str(tmp_path) + "/fault_model.toml"
    with open(toml_path, "w", encoding="utf-8") as f:
        f.write(
            """
            [[fault]]
            id = "thermal_throttling"
            name = "Thermal Throttling"
            symptoms = ["system overheating", "high temperature"]
            cause = "Cooling failure"
            checks = ["check_system_ram"]
            """
        )

    # 1. Contradictory observation ("temperature is normal" vs "high temperature")
    verifier_contra = MockVerifier(
        {
            ("system temperature is completely normal", "system overheating"): VerifierLabel.CONTRADICTION,
            ("system temperature is completely normal", "high temperature"): VerifierLabel.CONTRADICTION,
        }
    )
    engine_contra = DiagnosisEngine(fault_model_path=toml_path, verifier=verifier_contra)
    # Mock env_check to avoid running real hardware sensors
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("lucca.core.env_check.check_system_ram", lambda: (True, "Normal"))
        diag_contra = engine_contra.diagnose("system temperature is completely normal")
        assert len(diag_contra) == 0, "Contradictory observation must NOT match symptom"

    # 2. Entailing observation ("fans at maximum, thermal sensor critical" -> "system overheating")
    verifier_entail = MockVerifier(
        {
            ("fans at maximum, thermal sensor critical", "system overheating"): VerifierLabel.ENTAILMENT,
            ("fans at maximum, thermal sensor critical", "high temperature"): VerifierLabel.ENTAILMENT,
        }
    )
    engine_entail = DiagnosisEngine(fault_model_path=toml_path, verifier=verifier_entail)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("lucca.core.env_check.check_system_ram", lambda: (False, "Sensor reading 98C"))
        diag_entail = engine_entail.diagnose("fans at maximum, thermal sensor critical")
        assert len(diag_entail) == 1
        assert diag_entail[0].fault_id == "thermal_throttling"


# ============================================================================
# Gate 3: G-V1357-BELNAP (cascade.py _evaluate_polarity)
# ============================================================================


def test_g_v1357_belnap_gate() -> None:
    """
    Gate G-V1357-BELNAP:
    A negative memory assertion queried with a positive question evaluates
    told_false=True via SemanticVerifierPort.
    """
    premise = "The API does not support endpoint v2."
    hypothesis = "Does the API support endpoint v2?"

    verifier = MockVerifier(
        {
            (premise, hypothesis): VerifierLabel.CONTRADICTION,
        }
    )
    cascade = EpistemicSearchCascade(verifier=verifier)
    told_true, told_false = cascade._evaluate_polarity(premise, hypothesis)
    assert told_true is False
    assert told_false is True, "Contradicting query must evaluate told_false=True"


# ============================================================================
# Gate 4: G-V1357-RULE (induction.py cluster_phrasings)
# ============================================================================


def test_g_v1357_rule_gate() -> None:
    """
    Gate G-V1357-RULE:
    1. Opposing rule candidate pair ('always use single quotes' vs 'never use single quotes')
       is rejected from single-cluster merging.
    2. Negative fixture: near-paraphrase pair ('always use single quotes' vs 'prefer single quotes')
       is NOT flagged as a Rule Conflict and clusters via entailment.
    """
    # 1. Opposing rule pair must NOT merge into a single cluster
    opposing_rules = ["always use single quotes", "never use single quotes"]
    clusters_opposing = cluster_phrasings(opposing_rules, threshold=0.40)
    assert len(clusters_opposing) == 2, "Opposing rules must form distinct clusters"

    # 2. Near-paraphrase pair must merge into a single cluster via SemanticVerifierPort
    paraphrase_rules = ["always use single quotes", "prefer single quotes"]
    verifier = MockVerifier(
        {
            ("always use single quotes", "prefer single quotes"): VerifierLabel.ENTAILMENT,
            ("prefer single quotes", "always use single quotes"): VerifierLabel.ENTAILMENT,
        }
    )
    assert not is_rule_conflict(paraphrase_rules[0], paraphrase_rules[1], verifier=verifier)
    clusters_paraphrase = cluster_phrasings(paraphrase_rules, threshold=0.80, verifier=verifier)
    assert len(clusters_paraphrase) == 1, "Entailed paraphrase rules must merge into single cluster"


# ============================================================================
# Functional Coherence Semantic Entailment Test (coherence.py)
# ============================================================================


def test_coherence_semantic_entailment_grounds_claim() -> None:
    """Verifies that receipt output semantically entailing a narration grounds the claim."""
    receipt = ToolReceipt(
        tool="write_file",
        ok=True,
        args={"path": "notes.txt"},
        output="Successfully saved 100 bytes to notes.txt",
    )
    narration = "I updated your notes on disk."

    # Without verifier, "updated notes" might be flagged as tool family mismatch
    claims_no_verifier = detect_ungrounded_action_claims(narration, [receipt])
    # With verifier entailing the output, claim is grounded
    verifier = MockVerifier(
        {
            ("Tool write_file succeeded with args {'path': 'notes.txt'} and output: Successfully saved 100 bytes to notes.txt", "i updated your notes on disk"): VerifierLabel.ENTAILMENT,
        }
    )
    claims_with_verifier = detect_ungrounded_action_claims(narration, [receipt], verifier=verifier)
    assert any(c.grounded for c in claims_with_verifier)
