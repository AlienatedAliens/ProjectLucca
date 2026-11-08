"""
Unit tests for Sovereign Cognitive Outcome Sink (Milestone 36.1, G-WO36-OUTCOME-SINK).
Pre-registered acceptance gate verification:
1. Signs ASSISTANT_ACTION receipt via ToolResultSigner.
2. Non-empty proof_trace() steps in ReasoningContext.
3. Retrievable RecallEpisode in EpisodeRecall for turns >= 2 and success == True.
4. Positive Dominance shift in AffectiveODEMachine (EUREKA_DISCOVERY).
5. Evidential truth weight strictly 0.0.
"""

from __future__ import annotations

from lucca.core.affective_ode import AffectiveODEMachine, AffectSignal3D
from lucca.core.cognitive_sink import CognitiveOutcomeSink
from lucca.core.episode_recall import EpisodeRecall
from lucca.core.reasoning_context import ReasoningContext
from lucca.core.schemas import Provenance
from lucca.memory.signers import ToolResultSigner

MASTER_KEY = b"test-master-key-32-bytes-long!!!"


def test_cognitive_outcome_sink_2turn_repair_success() -> None:
    """Verifies G-WO36-OUTCOME-SINK 2-turn CEGIS repair cognitive unification."""
    action_signer = ToolResultSigner(master_key=MASTER_KEY, signer_id="test@cegis")
    reasoning_context = ReasoningContext()
    episode_recall = EpisodeRecall()
    affect_machine = AffectiveODEMachine()

    initial_d = affect_machine.state.dominance

    sink = CognitiveOutcomeSink(
        action_signer=action_signer,
        reasoning_context=reasoning_context,
        episode_recall=episode_recall,
        affect_machine=affect_machine,
    )

    outcome = sink.record_cegis_outcome(
        task_id="arc_sample_01",
        problem_summary="InsideOutside container enclosure puzzle",
        engine_name="UnshackledCEGISEngine",
        success=True,
        turns_taken=2,
        final_code="def transform(grid): return [[1]]",
        turn_1_error="IndexError: grid index out of range",
        verified_strategy="Flipped enclosure polarity using in_cavity()",
        status_label="VERIFIED_REPAIRED_PROGRAM",
    )

    # (a) Signed ASSISTANT_ACTION receipt
    receipt = outcome["signed_receipt"]
    assert receipt is not None
    assert receipt.provenance == Provenance.ASSISTANT_ACTION
    assert receipt.signature is not None
    assert "arc_sample_01" in receipt.content

    # (b) Non-empty proof_trace() steps
    proof_steps = reasoning_context.proof_trace()
    assert len(proof_steps) >= 2
    assert proof_steps[0].step_kind == "cegis_repair"
    assert "arc_sample_01" in proof_steps[0].conclusion or "arc_sample_01" in proof_steps[0].envelope_id

    # (c) Retrievable RecallEpisode in EpisodeRecall
    episodes = episode_recall.retrieve_episodes("container enclosure puzzle")
    assert len(episodes) >= 1
    recalled = episodes[0]
    assert "InsideOutside" in recalled.summary
    assert recalled.payload.get("turns_taken") == 2
    assert recalled.payload.get("turn_1_error") == "IndexError: grid index out of range"
    assert "in_cavity" in str(recalled.payload.get("verified_repair_strategy"))

    # (d) Positive Dominance shift in AffectiveODEMachine (EUREKA_DISCOVERY) & evidential weight 0.0
    assert outcome["affect_signal"] == AffectSignal3D.EUREKA_DISCOVERY.value
    assert affect_machine.state.dominance > initial_d
    assert outcome["dominance_delta"] > 0.0
    assert outcome["evidential_weight"] == 0.0


def test_cognitive_outcome_sink_failure_fallback() -> None:
    """Verifies failure appraisal emits TOOL_FAILURE and skips episode recording."""
    action_signer = ToolResultSigner(master_key=MASTER_KEY, signer_id="test@cegis")
    reasoning_context = ReasoningContext()
    episode_recall = EpisodeRecall()
    affect_machine = AffectiveODEMachine()

    initial_d = affect_machine.state.dominance

    sink = CognitiveOutcomeSink(
        action_signer=action_signer,
        reasoning_context=reasoning_context,
        episode_recall=episode_recall,
        affect_machine=affect_machine,
    )

    outcome = sink.record_cegis_outcome(
        task_id="failed_task_99",
        problem_summary="Impossible parity problem",
        engine_name="PythonCEGISEngine",
        success=False,
        turns_taken=4,
        final_code=None,
        turn_1_error="SyntaxError: invalid syntax",
        status_label="INTERNAL_FALLBACK",
    )

    assert outcome["affect_signal"] == AffectSignal3D.TOOL_FAILURE.value
    assert affect_machine.state.dominance < initial_d
    assert outcome["dominance_delta"] < 0.0
    # No episode recorded on failure
    assert len(episode_recall.retrieve_episodes("Impossible parity problem")) == 0
    # Still signs receipt and records proof trace for auditability
    assert outcome["signed_receipt"] is not None
    assert len(reasoning_context.proof_trace()) >= 4


def test_cognitive_outcome_sink_single_turn_success() -> None:
    """Verifies 1-turn success appraises TASK_SUCCESS without polluting repair fast path."""
    affect_machine = AffectiveODEMachine()
    episode_recall = EpisodeRecall()

    sink = CognitiveOutcomeSink(
        affect_machine=affect_machine,
        episode_recall=episode_recall,
    )

    outcome = sink.record_cegis_outcome(
        task_id="trivial_task_01",
        problem_summary="Identity grid copy",
        engine_name="UnshackledCEGISEngine",
        success=True,
        turns_taken=1,
        final_code="def transform(g): return g",
        status_label="CHECKED_FORMALIZATION_AGREED",
    )

    assert outcome["affect_signal"] == AffectSignal3D.TASK_SUCCESS.value
    assert len(episode_recall.retrieve_episodes("Identity grid copy")) == 0
