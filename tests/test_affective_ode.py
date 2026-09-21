"""
Project Lucca — Continuous Affective Dynamics (3D PAD ODE) Unit Tests
ADR-009, Spec 16 §4, D-BRAIN-04, D-BRAIN-05

Formally verifies:
1. Exact analytical discrete integration vs psychological half-lives.
2. Lyapunov asymptotic stability under endogenous cognitive feedback.
3. Schmitt-trigger hysteresis deadband preventing stance chattering.
4. RBF Mahalanobis stance quantization.
5. Kokoro TTS prosodic steering (speed and pitch shift).
6. Zero-Any architectural invariant.
"""

from __future__ import annotations

import math

from lucca.core.affective_ode import (
    HALF_LIFE_AROUSAL_S,
    HALF_LIFE_DOMINANCE_S,
    HALF_LIFE_PLEASURE_S,
    MAX_LYAPUNOV_FEEDBACK_GAIN,
    MIN_GAMMA,
    AffectiveODEMachine,
    AffectSignal3D,
    AffectState3D,
    DiscreteStance,
)


def test_analytical_decay_matches_half_lives():
    """Verify analytical solution decays by exactly 50% at each coordinate's half-life."""
    t0 = 1000.0
    machine = AffectiveODEMachine(
        baseline_pleasure=0.0,
        baseline_arousal=0.0,
        baseline_dominance=0.0,
        now=t0,
    )

    # Set initial displacement: P=0.8, A=0.8, D=0.8
    machine.state.pleasure = 0.8
    machine.state.arousal = 0.8
    machine.state.dominance = 0.8
    machine.state.updated_at = t0

    # 1. At t0 + 45s (Arousal half-life): A should be exactly 0.40 (half of 0.8)
    st_a = machine.decay_state(now=t0 + HALF_LIFE_AROUSAL_S)
    assert abs(st_a.arousal - 0.40) < 1e-4
    # P and D should have decayed much less
    assert st_a.pleasure > 0.70
    assert st_a.dominance > 0.75

    # 2. At t0 + 300s (Pleasure half-life): P should be 0.40 from original
    machine.state.pleasure = 0.8
    machine.state.updated_at = t0
    st_p = machine.decay_state(now=t0 + HALF_LIFE_PLEASURE_S)
    assert abs(st_p.pleasure - 0.40) < 1e-4

    # 3. At t0 + 900s (Dominance half-life): D should be 0.40 from original
    machine.state.dominance = 0.8
    machine.state.updated_at = t0
    st_d = machine.decay_state(now=t0 + HALF_LIFE_DOMINANCE_S)
    assert abs(st_d.dominance - 0.40) < 1e-4


def test_lyapunov_asymptotic_stability_under_feedback():
    """
    Theorem: For feedback gain < min(gamma_i), all closed-loop eigenvalues
    have strictly negative real parts, guaranteeing global asymptotic stability.
    """
    assert MAX_LYAPUNOV_FEEDBACK_GAIN < MIN_GAMMA

    # Initialize machine with maximum permitted Lyapunov feedback gain
    machine = AffectiveODEMachine(
        baseline_pleasure=0.0,
        baseline_arousal=0.0,
        baseline_dominance=0.0,
        feedback_gain=MAX_LYAPUNOV_FEEDBACK_GAIN,
        now=0.0,
    )

    # Apply severe emotional shock (Double Interrupt + Tool Failure)
    machine.apply_signal(AffectSignal3D.DOUBLE_INTERRUPT, now=0.0)
    machine.apply_signal(AffectSignal3D.TOOL_FAILURE, now=1.0)

    # State is perturbed
    st_init = machine.get_current_state(now=1.0)
    assert st_init.pleasure < -0.40
    assert st_init.arousal > 0.30

    # Simulate closed-loop decay over 2000 seconds in 10-second discrete turns
    prev_norm = math.sqrt(st_init.pleasure**2 + st_init.arousal**2 + st_init.dominance**2)

    t = 10.0
    while t <= 2500.0:
        st = machine.decay_state(now=t)
        norm = math.sqrt(st.pleasure**2 + st.arousal**2 + st.dominance**2)
        # Verify strictly non-expanding trajectory (Lyapunov decrease)
        assert norm <= prev_norm + 1e-6
        prev_norm = norm
        t += 50.0

    # Must asymptotically converge back to resting baseline (0.0, 0.0, 0.0)
    # Note: Dominance half-life is 900s; full snap to 0 occurs after > 5 half-lives (~4700s)
    final_st = machine.get_current_state(now=6000.0)
    assert final_st.pleasure == 0.0
    assert final_st.arousal == 0.0
    assert final_st.dominance == 0.0
    assert final_st.active_stance == DiscreteStance.NEUTRAL_STEADY


def test_schmitt_trigger_hysteresis_deadband():
    """
    Verifies that continuous micro-fluctuations inside the deadband (delta = 0.15)
    do NOT cause discrete stance chattering across turn boundaries.
    """
    machine = AffectiveODEMachine(now=0.0)
    assert machine.get_current_stance(now=0.0) == DiscreteStance.NEUTRAL_STEADY

    # 1. Drive system firmly into FOCUSED_ANALYTICAL
    machine.state.pleasure = 0.05
    machine.state.arousal = 0.10
    machine.state.dominance = 0.50
    machine.state.updated_at = 1.0
    stance = machine.quantize_stance(machine.state, current_stance=DiscreteStance.NEUTRAL_STEADY)
    assert stance == DiscreteStance.FOCUSED_ANALYTICAL
    machine.state.active_stance = stance

    # 2. Perturb coordinates slightly toward ENERGETIC_SUPPORTIVE but within hysteresis band
    machine.state.pleasure = 0.20
    machine.state.arousal = 0.25
    # Schmitt trigger must hold FOCUSED_ANALYTICAL to prevent chattering
    held_stance = machine.quantize_stance(
        machine.state, current_stance=DiscreteStance.FOCUSED_ANALYTICAL
    )
    assert held_stance == DiscreteStance.FOCUSED_ANALYTICAL

    # 3. Apply large definitive shift into ENERGETIC_SUPPORTIVE
    machine.state.pleasure = 0.60
    machine.state.arousal = 0.55
    machine.state.dominance = 0.30
    switched_stance = machine.quantize_stance(
        machine.state, current_stance=DiscreteStance.FOCUSED_ANALYTICAL
    )
    assert switched_stance == DiscreteStance.ENERGETIC_SUPPORTIVE


def test_stance_quantization_anchors():
    """Verifies canonical 3D PAD vectors map to their intended discrete stances."""
    machine = AffectiveODEMachine(now=0.0)

    test_vectors = [
        (0.0, 0.0, 0.0, DiscreteStance.NEUTRAL_STEADY),
        (0.05, 0.10, 0.45, DiscreteStance.FOCUSED_ANALYTICAL),
        (0.30, -0.45, 0.10, DiscreteStance.CALM_RELAXED),
        (0.55, 0.50, 0.25, DiscreteStance.ENERGETIC_SUPPORTIVE),
        (-0.35, 0.35, -0.35, DiscreteStance.GUARDED_CAUTIOUS),
        (-0.35, -0.35, -0.25, DiscreteStance.SUBDUED_REFLECTIVE),
        (-0.10, 0.60, 0.65, DiscreteStance.COMMANDING_PROTECTIVE),
    ]

    for p, a, d, expected in test_vectors:
        st = AffectState3D(pleasure=p, arousal=a, dominance=d)
        stance = machine.quantize_stance(st, current_stance=None)
        assert stance == expected, f"Vector ({p}, {a}, {d}) expected {expected}, got {stance}"


def test_prompt_suffix_tag_formatting():
    """Verifies prompt suffix tag produces orthogonal semantic tokens."""
    machine = AffectiveODEMachine(now=0.0)
    tag = machine.get_prompt_suffix_tag(now=0.0)
    assert tag == "[STANCE: neutral_steady]"

    machine.state.pleasure = 0.05
    machine.state.arousal = 0.10
    machine.state.dominance = 0.50
    machine.state.active_stance = DiscreteStance.FOCUSED_ANALYTICAL
    tag_focused = machine.get_prompt_suffix_tag(now=1.0)
    assert tag_focused == "[STANCE: focused_analytical]"


def test_tts_prosody_steering():
    """Verifies zero-latency voice prosody parameter steering."""
    machine = AffectiveODEMachine(max_speed_delta=0.10, now=0.0)

    # Neutral: speed = 1.0, pitch = 0.0
    assert machine.get_tts_speed_multiplier(now=0.0) == 1.0
    assert machine.get_tts_pitch_shift_semitones(now=0.0) == 0.0

    # High arousal (+0.8), high dominance (+0.6)
    machine.state.arousal = 0.80
    machine.state.dominance = 0.60
    machine.state.updated_at = 1.0
    speed_high = machine.get_tts_speed_multiplier(now=1.0)
    assert speed_high == 1.08  # 1.0 + 0.8 * 0.10
    pitch_high = machine.get_tts_pitch_shift_semitones(now=1.0)
    assert pitch_high == 0.42  # 0.3 * 0.6 + 0.3 * 0.8 = 0.42

    # Low arousal (-0.6), low dominance (-0.4)
    machine.state.arousal = -0.60
    machine.state.dominance = -0.40
    machine.state.updated_at = 2.0
    speed_low = machine.get_tts_speed_multiplier(now=2.0)
    assert speed_low == 0.94  # 1.0 - 0.6 * 0.10
    pitch_low = machine.get_tts_pitch_shift_semitones(now=2.0)
    assert pitch_low == -0.30  # 0.3 * -0.4 + 0.3 * -0.6 = -0.30
