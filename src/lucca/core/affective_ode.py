"""
Project Lucca — Continuous Affective Dynamics (3D PAD ODE)
ADR-009, Spec 16 §4, D-BRAIN-04, D-BRAIN-05

Implements Mehrabian's 3D Pleasure-Arousal-Dominance (PAD) manifold with:
1. Exact analytical discrete integration over arbitrary time deltas.
2. Damping matrix with cognitive half-lives (tau_A=45s, tau_P=300s, tau_D=900s).
3. Lyapunov asymptotic stability bounding (feedback gain <= 0.0005 < min(gamma_i)).
4. RBF Schmitt-trigger hysteresis discrete stance quantization.
5. Zero-Any architectural invariant.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field


def clamp(val: float, low: float = -1.0, high: float = 1.0) -> float:
    """Clamps a floating-point scalar into [low, high]."""
    return max(low, min(high, val))


# Psychological half-lives in seconds
HALF_LIFE_AROUSAL_S: Final[float] = 45.0      # Fast sensorimotor decay
HALF_LIFE_PLEASURE_S: Final[float] = 300.0    # 5-minute valence decay
HALF_LIFE_DOMINANCE_S: Final[float] = 900.0   # 15-minute agency/mastery decay

# Analytical damping rates: gamma = ln(2) / t_half
GAMMA_A: Final[float] = math.log(2.0) / HALF_LIFE_AROUSAL_S     # ~0.015403 s^-1
GAMMA_P: Final[float] = math.log(2.0) / HALF_LIFE_PLEASURE_S    # ~0.002310 s^-1
GAMMA_D: Final[float] = math.log(2.0) / HALF_LIFE_DOMINANCE_S   # ~0.000770 s^-1

# Lyapunov stability bound: max cognitive feedback gain < min(gamma_i)
MIN_GAMMA: Final[float] = min(GAMMA_P, GAMMA_A, GAMMA_D)
MAX_LYAPUNOV_FEEDBACK_GAIN: Final[float] = 0.0005

# Schmitt-trigger hysteresis deadband
DEFAULT_HYSTERESIS_DELTA: Final[float] = 0.15


class DiscreteStance(StrEnum):
    """
    Quantized discrete stances for prompt frontier suffix injection.
    Orthogonal semantic tokens preventing KV-cache fragmentation.
    """
    NEUTRAL_STEADY = "neutral_steady"
    FOCUSED_ANALYTICAL = "focused_analytical"
    CALM_RELAXED = "calm_relaxed"
    ENERGETIC_SUPPORTIVE = "energetic_supportive"
    GUARDED_CAUTIOUS = "guarded_cautious"
    SUBDUED_REFLECTIVE = "subdued_reflective"
    COMMANDING_PROTECTIVE = "commanding_protective"


@dataclass(frozen=True)
class StanceAnchor:
    """Radial Basis Function cluster center and bandwidth in 3D PAD space."""
    stance: DiscreteStance
    mu_p: float
    mu_a: float
    mu_d: float
    sigma_p: float = 0.35
    sigma_a: float = 0.35
    sigma_d: float = 0.35


# Canonical stance anchors in Mehrabian PAD space [-1.0, 1.0]^3
STANCE_ANCHORS: Final[list[StanceAnchor]] = [
    StanceAnchor(DiscreteStance.NEUTRAL_STEADY, 0.0, 0.0, 0.0, 0.25, 0.25, 0.25),
    StanceAnchor(DiscreteStance.FOCUSED_ANALYTICAL, 0.05, 0.10, 0.40, 0.35, 0.35, 0.35),
    StanceAnchor(DiscreteStance.CALM_RELAXED, 0.25, -0.40, 0.10, 0.35, 0.35, 0.35),
    StanceAnchor(DiscreteStance.ENERGETIC_SUPPORTIVE, 0.50, 0.45, 0.25, 0.35, 0.35, 0.35),
    StanceAnchor(DiscreteStance.GUARDED_CAUTIOUS, -0.30, 0.30, -0.30, 0.35, 0.35, 0.35),
    StanceAnchor(DiscreteStance.SUBDUED_REFLECTIVE, -0.30, -0.30, -0.20, 0.35, 0.35, 0.35),
    StanceAnchor(DiscreteStance.COMMANDING_PROTECTIVE, -0.10, 0.55, 0.60, 0.35, 0.35, 0.35),
]


class AffectSignal3D(StrEnum):
    """Discrete runtime appraisal signals updating the 3D PAD manifold."""
    DOUBLE_INTERRUPT = "double_interrupt"
    TOOL_FAILURE = "tool_failure"
    TASK_SUCCESS = "task_success"
    USER_PRAISE = "user_praise"
    USER_CORRECTION = "user_correction"
    LATE_NIGHT = "late_night"
    LONG_GAP = "long_gap"
    DEONTIC_REJECTION = "deontic_rejection"


# Impulse delta vector [dP, dA, dD] and default causal description
SIGNAL_DELTAS_3D: Final[dict[AffectSignal3D, tuple[float, float, float, str]]] = {
    # signal: (dP, dA, dD, default_cause)
    AffectSignal3D.DOUBLE_INTERRUPT: (-0.20, 0.35, -0.25, "interrupted twice in a row"),
    AffectSignal3D.TOOL_FAILURE: (-0.30, 0.10, -0.30, "tool execution failed"),
    AffectSignal3D.TASK_SUCCESS: (0.20, 0.05, 0.20, "task completed successfully"),
    AffectSignal3D.USER_PRAISE: (0.30, 0.10, 0.15, "positive user feedback"),
    AffectSignal3D.USER_CORRECTION: (-0.20, 0.10, -0.15, "user correction"),
    AffectSignal3D.LATE_NIGHT: (0.00, -0.40, 0.00, "late night quiet hours"),
    AffectSignal3D.LONG_GAP: (0.10, -0.20, 0.05, "welcoming return after absence"),
    AffectSignal3D.DEONTIC_REJECTION: (-0.15, 0.30, 0.40, "deontic safety alert"),
}


class AffectState3D(BaseModel):
    """
    Continuous state representation in Mehrabian's 3D PAD space.
    Valence is an alias for pleasure.
    """
    pleasure: float = 0.0    # [-1.0, 1.0] Pleasure / Valence
    arousal: float = 0.0     # [-1.0, 1.0] Arousal / Engagement
    dominance: float = 0.0   # [-1.0, 1.0] Dominance / Agency / Mastery
    updated_at: float = Field(default_factory=time.time)
    causes: list[str] = Field(default_factory=list)
    active_stance: DiscreteStance = DiscreteStance.NEUTRAL_STEADY

    @property
    def valence(self) -> float:
        """Backward-compatible alias for pleasure."""
        return self.pleasure


class AffectiveODEMachine:
    """
    Continuous 3D PAD differential state machine with exact discrete analytical
    solutions, Lyapunov stability guarantees, and Schmitt-trigger hysteresis.
    """

    def __init__(
        self,
        baseline_pleasure: float = 0.0,
        baseline_arousal: float = 0.0,
        baseline_dominance: float = 0.0,
        gamma_p: float = GAMMA_P,
        gamma_a: float = GAMMA_A,
        gamma_d: float = GAMMA_D,
        hysteresis_delta: float = DEFAULT_HYSTERESIS_DELTA,
        feedback_gain: float = 0.0,
        max_speed_delta: float = 0.10,
        now: float | None = None,
    ) -> None:
        self.p0 = clamp(baseline_pleasure)
        self.a0 = clamp(baseline_arousal)
        self.d0 = clamp(baseline_dominance)

        self.gamma_p = gamma_p
        self.gamma_a = gamma_a
        self.gamma_d = gamma_d

        self.hysteresis_delta = hysteresis_delta
        # Bound feedback gain strictly below min damping rate (Lyapunov theorem)
        self.feedback_gain = min(MAX_LYAPUNOV_FEEDBACK_GAIN, max(0.0, feedback_gain))
        self.max_speed_delta = max_speed_delta

        t0 = now if now is not None else time.time()
        self.state = AffectState3D(
            pleasure=self.p0,
            arousal=self.a0,
            dominance=self.d0,
            updated_at=t0,
            active_stance=DiscreteStance.NEUTRAL_STEADY,
        )

    def decay_state(self, now: float) -> AffectState3D:
        """
        Computes exact closed-form analytical continuous decay over dt = now - updated_at:
        x_i(t + dt) = x_0,i + e^(-gamma_i * dt) * (x_i(t) - x_0,i)
        Snap tiny deviations (< 0.015) to resting baseline.
        """
        dt = max(0.0, now - self.state.updated_at)
        if dt <= 0.0:
            return self.state

        # Exact exponential decay factors
        exp_p = math.exp(-self.gamma_p * dt)
        exp_a = math.exp(-self.gamma_a * dt)
        exp_d = math.exp(-self.gamma_d * dt)

        # Analytical solution
        new_p = self.p0 + exp_p * (self.state.pleasure - self.p0)
        new_a = self.a0 + exp_a * (self.state.arousal - self.a0)
        new_d = self.d0 + exp_d * (self.state.dominance - self.d0)

        # Snap to baseline when within deadband threshold
        if abs(new_p - self.p0) < 0.015:
            new_p = self.p0
        if abs(new_a - self.a0) < 0.015:
            new_a = self.a0
        if abs(new_d - self.d0) < 0.015:
            new_d = self.d0

        # Causes decay out after 2x slowest half-life (1800s)
        causes = self.state.causes if dt < (2.0 * HALF_LIFE_DOMINANCE_S) else []

        new_state = AffectState3D(
            pleasure=clamp(new_p),
            arousal=clamp(new_a),
            dominance=clamp(new_d),
            updated_at=now,
            causes=causes,
            active_stance=self.state.active_stance,
        )

        # Requantize stance using Schmitt-trigger hysteresis
        new_state.active_stance = self.quantize_stance(new_state, self.state.active_stance)
        self.state = new_state
        return self.state

    def apply_signal(
        self,
        signal: AffectSignal3D,
        custom_cause: str | None = None,
        now: float | None = None,
    ) -> AffectState3D:
        """
        Applies an instantaneous appraisal impulse signal after continuous decay.
        x_i <- clamp(x_i + dp_i, -1.0, 1.0)
        """
        t = now if now is not None else time.time()
        decayed = self.decay_state(t)

        dp, da, dd, default_cause = SIGNAL_DELTAS_3D[signal]
        cause_desc = custom_cause if custom_cause is not None else default_cause

        # Apply endogenous cognitive feedback if configured (bounded by Lyapunov theorem)
        if self.feedback_gain > 0.0:
            dp += self.feedback_gain * (decayed.pleasure - self.p0)
            da += self.feedback_gain * (decayed.arousal - self.a0)
            dd += self.feedback_gain * (decayed.dominance - self.d0)

        new_p = clamp(decayed.pleasure + dp)
        new_a = clamp(decayed.arousal + da)
        new_d = clamp(decayed.dominance + dd)

        new_causes = [c for c in decayed.causes if c != cause_desc]
        new_causes.append(cause_desc)
        if len(new_causes) > 4:
            new_causes = new_causes[-4:]

        interim_state = AffectState3D(
            pleasure=new_p,
            arousal=new_a,
            dominance=new_d,
            updated_at=t,
            causes=new_causes,
            active_stance=decayed.active_stance,
        )
        interim_state.active_stance = self.quantize_stance(interim_state, decayed.active_stance)
        self.state = interim_state
        return self.state

    def quantize_stance(
        self,
        state: AffectState3D,
        current_stance: DiscreteStance | None = None,
    ) -> DiscreteStance:
        """
        Evaluates RBF Mahalanobis distance across STANCE_ANCHORS and applies
        Schmitt-trigger hysteresis to prevent chattering across turn boundaries.
        pi(s* | x) - pi(s_current | x) > delta_hyst (0.15).
        """
        probs: dict[DiscreteStance, float] = {}
        total_phi = 0.0

        for anchor in STANCE_ANCHORS:
            # Squared Mahalanobis distance
            dp = (state.pleasure - anchor.mu_p) / anchor.sigma_p
            da = (state.arousal - anchor.mu_a) / anchor.sigma_a
            dd = (state.dominance - anchor.mu_d) / anchor.sigma_d
            d2 = dp * dp + da * da + dd * dd
            phi = math.exp(-0.5 * d2)
            probs[anchor.stance] = phi
            total_phi += phi

        if total_phi <= 1e-12:
            return DiscreteStance.NEUTRAL_STEADY

        # Normalize to probability distribution
        for st in probs:
            probs[st] /= total_phi

        best_stance = max(probs, key=lambda s: probs[s])
        if current_stance is None:
            return best_stance

        current_prob = probs.get(current_stance, 0.0)
        best_prob = probs[best_stance]

        # Schmitt-trigger threshold test
        if best_prob - current_prob > self.hysteresis_delta:
            return best_stance
        return current_stance

    def get_current_state(self, now: float | None = None) -> AffectState3D:
        """Returns the decayed, current 3D affect state."""
        t = now if now is not None else time.time()
        return self.decay_state(t)

    def get_current_stance(self, now: float | None = None) -> DiscreteStance:
        """Returns the active discrete stance token for prompt frontier suffix injection."""
        st = self.get_current_state(now)
        return st.active_stance

    def get_prompt_suffix_tag(self, now: float | None = None) -> str:
        """
        Formats discrete stance tag for prompt frontier suffix.
        Returns e.g. '[STANCE: focused_analytical]'.
        """
        stance = self.get_current_stance(now)
        return f"[STANCE: {stance.value}]"

    def get_tts_speed_multiplier(self, now: float | None = None) -> float:
        """
        Modulates Kokoro TTS speaking rate based on Arousal:
        speed = clamp(1.0 + A * max_speed_delta, 1.0 - delta, 1.0 + delta)
        """
        st = self.get_current_state(now)
        mult = 1.0 + (st.arousal * self.max_speed_delta)
        low = 1.0 - self.max_speed_delta
        high = 1.0 + self.max_speed_delta
        return round(clamp(mult, low, high), 3)

    def get_tts_pitch_shift_semitones(self, now: float | None = None) -> float:
        """
        Modulates voice pitch shift semitones based on Dominance and Arousal:
        delta_pitch = 0.3 * D + 0.3 * A clamped to [-2.0, 2.0].
        Executes via SIMD DSP without re-initializing ONNX TTS.
        """
        st = self.get_current_state(now)
        pitch = 0.30 * st.dominance + 0.30 * st.arousal
        return round(clamp(pitch, -2.0, 2.0), 2)

    def format_prompt_hint(self, now: float | None = None) -> str | None:
        """
        Honest non-theatrical operational register description per Spec 16 §4.
        Never claims biological emotion.
        """
        st = self.get_current_state(now)
        if abs(st.pleasure) < 0.15 and abs(st.arousal) < 0.15 and abs(st.dominance) < 0.15:
            return None

        causes_str = "; ".join(st.causes) if st.causes else "recent system events"

        if st.arousal > 0.25 and st.pleasure < -0.15:
            return f"System note: Operating in a slightly flustered state due to: {causes_str}."
        if st.pleasure < -0.2:
            return f"System note: Operating in a subdued state due to: {causes_str}."
        if st.pleasure > 0.2:
            return f"System note: Operating in an upbeat, positive state due to: {causes_str}."
        if st.arousal < -0.25:
            return f"System note: Operating in a calm, low-energy mode due to: {causes_str}."
        if st.dominance > 0.3:
            return f"System note: Operating with elevated agency and focus due to: {causes_str}."

        return f"System note: Operating with state influenced by: {causes_str}."

    def answer_status_query(self, now: float | None = None) -> str:
        """Answers 'How are you feeling?' objectively using measured telemetry and causes."""
        st = self.get_current_state(now)
        if abs(st.pleasure) < 0.15 and abs(st.arousal) < 0.15 and abs(st.dominance) < 0.15:
            return "Operating normally with a steady, neutral system state."

        causes_str = " and ".join(st.causes) if st.causes else "recent interactions"

        if st.arousal > 0.25 and st.pleasure < -0.15:
            return f"A bit flustered right now — {causes_str}."
        if st.pleasure < -0.2:
            return f"A bit flat or subdued — {causes_str}."
        if st.pleasure > 0.2:
            return f"Running well and feeling sharp — {causes_str}."
        if st.arousal < -0.25:
            return f"Quiet and relaxed — {causes_str}."
        if st.dominance > 0.3:
            return f"Focused and in control — {causes_str}."

        return f"Steady, currently influenced by: {causes_str}."
