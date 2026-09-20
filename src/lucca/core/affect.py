"""
Project Lucca — Honest State-Based Affect Machine
ADR-009, Spec 16 §4, D-BRAIN-04, D-BRAIN-05
"""

from __future__ import annotations

import math
import time
import tomllib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from lucca.core.affective_ode import (
    AffectiveODEMachine,
    AffectSignal3D,
    AffectState3D,
    DiscreteStance,
)


class AffectConfig(BaseModel):
    enabled: bool = True
    decay_tau_seconds: float = 600.0
    max_speed_delta: float = 0.10


class AffectSignal(StrEnum):
    DOUBLE_INTERRUPT = "double_interrupt"
    TOOL_FAILURE = "tool_failure"
    USER_PRAISE = "user_praise"
    LATE_NIGHT = "late_night"
    LONG_GAP = "long_gap"
    TASK_SUCCESS = "task_success"
    USER_CORRECTION = "user_correction"
    DEONTIC_REJECTION = "deontic_rejection"


SIGNAL_DELTAS: dict[AffectSignal, tuple[float, float, str]] = {
    # signal: (delta_valence, delta_arousal, default_cause)
    AffectSignal.DOUBLE_INTERRUPT: (-0.2, 0.35, "interrupted twice in a row"),
    AffectSignal.TOOL_FAILURE: (-0.3, 0.1, "tool execution failed"),
    AffectSignal.USER_PRAISE: (0.3, 0.1, "positive user feedback"),
    AffectSignal.LATE_NIGHT: (0.0, -0.4, "late night quiet hours"),
    AffectSignal.LONG_GAP: (0.1, -0.2, "welcoming return after absence"),
    AffectSignal.TASK_SUCCESS: (0.2, 0.05, "task completed successfully"),
    AffectSignal.USER_CORRECTION: (-0.2, 0.1, "user correction"),
    AffectSignal.DEONTIC_REJECTION: (-0.15, 0.3, "deontic safety alert"),
}

SIGNAL_DELTAS_3D_EXT: dict[AffectSignal, tuple[float, float, float, str]] = {
    AffectSignal.DOUBLE_INTERRUPT: (-0.20, 0.35, -0.25, "interrupted twice in a row"),
    AffectSignal.TOOL_FAILURE: (-0.30, 0.10, -0.30, "tool execution failed"),
    AffectSignal.USER_PRAISE: (0.30, 0.10, 0.15, "positive user feedback"),
    AffectSignal.LATE_NIGHT: (0.00, -0.40, 0.00, "late night quiet hours"),
    AffectSignal.LONG_GAP: (0.10, -0.20, 0.05, "welcoming return after absence"),
    AffectSignal.TASK_SUCCESS: (0.20, 0.05, 0.20, "task completed successfully"),
    AffectSignal.USER_CORRECTION: (-0.20, 0.10, -0.15, "user correction"),
    AffectSignal.DEONTIC_REJECTION: (-0.15, 0.30, 0.40, "deontic safety alert"),
}


class AffectState(BaseModel):
    valence: float = 0.0  # [-1.0, 1.0] from negative to positive (Pleasure)
    arousal: float = 0.0  # [-1.0, 1.0] from calm/quiet to energized/flustered (Arousal)
    dominance: float = 0.0  # [-1.0, 1.0] agency / control / mastery (Dominance)
    updated_at: float = Field(default_factory=time.time)
    causes: list[str] = Field(default_factory=list)
    active_stance: str = DiscreteStance.NEUTRAL_STEADY.value

    @property
    def pleasure(self) -> float:
        """Alias for valence."""
        return self.valence


def clamp(val: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, val))


def decay_affect(state: AffectState, now: float, tau: float = 600.0) -> AffectState:
    """
    Decays valence and arousal toward neutral (0.0) exponentially
    over time constant tau (default 600s / 10m).
    Dominance decays over tau * 1.5.
    """
    delta_t = max(0.0, now - state.updated_at)
    if delta_t <= 0.0:
        return state

    decay_factor = math.exp(-delta_t / tau)
    new_v = state.valence * decay_factor
    new_a = state.arousal * decay_factor
    new_d = state.dominance * math.exp(-delta_t / (tau * 1.5))

    # Snap tiny values to 0
    if abs(new_v) < 0.02:
        new_v = 0.0
    if abs(new_a) < 0.02:
        new_a = 0.0
    if abs(new_d) < 0.02:
        new_d = 0.0

    # Prune old causes if decayed past 2x tau
    causes = state.causes if delta_t < (2.0 * tau) else []

    return AffectState(
        valence=new_v,
        arousal=new_a,
        dominance=new_d,
        updated_at=now,
        causes=causes,
        active_stance=state.active_stance,
    )


def apply_affect_signal(
    state: AffectState,
    signal: AffectSignal,
    custom_cause: str | None = None,
    now: float | None = None,
    tau: float = 600.0,
) -> AffectState:
    """
    Applies an external signal to update affect state after decaying from previous update.
    """
    current_time = now if now is not None else time.time()
    decayed = decay_affect(state, current_time, tau=tau)

    dv, da, dd, default_cause = SIGNAL_DELTAS_3D_EXT[signal]
    cause_desc = custom_cause if custom_cause is not None else default_cause

    new_v = clamp(decayed.valence + dv)
    new_a = clamp(decayed.arousal + da)
    new_d = clamp(decayed.dominance + dd)

    new_causes = [c for c in decayed.causes if c != cause_desc]
    new_causes.append(cause_desc)
    # Keep up to 4 most recent causes
    if len(new_causes) > 4:
        new_causes = new_causes[-4:]

    return AffectState(
        valence=new_v,
        arousal=new_a,
        dominance=new_d,
        updated_at=current_time,
        causes=new_causes,
        active_stance=decayed.active_stance,
    )


def get_tts_speed_multiplier(state: AffectState, max_delta: float = 0.10) -> float:
    """
    Modulates Kokoro TTS speaking rate based on arousal level:
    - Calm / late night (arousal < 0): slower, down to 1.0 - max_delta (e.g. 0.90)
    - Energized / urgent (arousal > 0): faster, up to 1.0 + max_delta (e.g. 1.10)
    """
    mult = 1.0 + (state.arousal * max_delta)
    return round(clamp(mult, 1.0 - max_delta, 1.0 + max_delta), 3)


def format_prompt_hint(state: AffectState) -> str | None:
    """
    Renders an honest, non-theatrical prompt hint for the LLM when affect is non-neutral.
    Per Spec 16 §4: Affect is described as system state, not claimed emotional feelings.
    """
    if abs(state.valence) < 0.15 and abs(state.arousal) < 0.15:
        return None

    causes_str = "; ".join(state.causes) if state.causes else "recent system events"

    if state.arousal > 0.25 and state.valence < -0.15:
        return f"System note: You are operating in a slightly flustered state due to: {causes_str}."
    if state.valence < -0.2:
        return f"System note: You are operating in a subdued state due to: {causes_str}."
    if state.valence > 0.2:
        return f"System note: You are operating in an upbeat, positive state due to: {causes_str}."
    if state.arousal < -0.25:
        return f"System note: You are operating in a calm, low-energy mode due to: {causes_str}."

    return None


def handle_affect_query(state: AffectState) -> str:
    """
    Answers user questions like 'How are you feeling?' objectively with measured state and causes.
    Per Spec 16 §4: Never 'I am sad' as a bare emotional claim.
    """
    if abs(state.valence) < 0.15 and abs(state.arousal) < 0.15:
        return "Operating normally with a steady, neutral system state."

    causes_str = " and ".join(state.causes) if state.causes else "recent interactions"

    if state.arousal > 0.25 and state.valence < -0.15:
        return f"A bit flustered right now — {causes_str}."
    if state.valence < -0.2:
        return f"A bit flat or subdued — {causes_str}."
    if state.valence > 0.2:
        return f"Running well and feeling sharp — {causes_str}."
    if state.arousal < -0.25:
        return f"Quiet and relaxed — {causes_str}."

    return f"Steady, currently influenced by: {causes_str}."


class AffectTracker:
    """
    Thread-safe or in-memory tracker for lucca-core runtime affect.
    Backed by both AffectState and the continuous AffectiveODEMachine.
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        self.state = AffectState()
        self.enabled = True
        self.decay_tau = 600.0
        self.max_speed_delta = 0.10
        self.ode_machine = AffectiveODEMachine(max_speed_delta=self.max_speed_delta)
        self._load_config(config_path)

    def _load_config(self, config_path: Path | str | None) -> None:
        path = (
            Path(config_path)
            if config_path is not None
            else Path(r"C:\ProjectLucca\config\persona.toml")
        )
        if not path.exists():
            return
        try:
            with open(path, "rb") as f:
                cfg: dict[str, object] = tomllib.load(f)
            raw_affect = cfg.get("affect", {})
            affect_dict = raw_affect if isinstance(raw_affect, dict) else {}
            affect_cfg = AffectConfig.model_validate(affect_dict)
            self.enabled = affect_cfg.enabled
            self.decay_tau = affect_cfg.decay_tau_seconds
            self.max_speed_delta = affect_cfg.max_speed_delta
            self.ode_machine.max_speed_delta = self.max_speed_delta
        except (OSError, tomllib.TOMLDecodeError, ValueError, KeyError):
            return

    def record_signal(
        self,
        signal: AffectSignal | AffectSignal3D | str,
        custom_cause: str | None = None,
        now: float | None = None,
    ) -> None:
        if not self.enabled:
            return
        # Normalize signal enum
        sig_str = signal.value if hasattr(signal, "value") else str(signal)
        aff_sig = AffectSignal(sig_str)
        aff_sig_3d = AffectSignal3D(sig_str)

        self.state = apply_affect_signal(
            self.state, aff_sig, custom_cause=custom_cause, now=now, tau=self.decay_tau
        )
        self.ode_machine.apply_signal(aff_sig_3d, custom_cause=custom_cause, now=now)
        self.state.active_stance = self.ode_machine.get_current_stance(now).value
        self.state.dominance = self.ode_machine.state.dominance

    def get_current_state(self, now: float | None = None) -> AffectState:
        if not self.enabled:
            return AffectState()
        current_time = now if now is not None else time.time()
        self.state = decay_affect(self.state, current_time, tau=self.decay_tau)
        ode_st = self.ode_machine.get_current_state(current_time)
        self.state.active_stance = ode_st.active_stance.value
        self.state.dominance = ode_st.dominance
        return self.state

    def get_current_stance(self, now: float | None = None) -> DiscreteStance:
        """Returns active discrete stance for prompt frontier suffix injection."""
        if not self.enabled:
            return DiscreteStance.NEUTRAL_STEADY
        return self.ode_machine.get_current_stance(now)

    def get_prompt_suffix_tag(self, now: float | None = None) -> str:
        """Returns e.g. '[STANCE: focused_analytical]'."""
        if not self.enabled:
            return f"[STANCE: {DiscreteStance.NEUTRAL_STEADY.value}]"
        return self.ode_machine.get_prompt_suffix_tag(now)

    def get_tts_speed_multiplier(self, now: float | None = None) -> float:
        if not self.enabled:
            return 1.0
        current_state = self.get_current_state(now)
        return get_tts_speed_multiplier(current_state, self.max_speed_delta)

    def get_tts_pitch_shift_semitones(self, now: float | None = None) -> float:
        if not self.enabled:
            return 0.0
        return self.ode_machine.get_tts_pitch_shift_semitones(now)

    def get_prompt_hint(self, now: float | None = None) -> str | None:
        if not self.enabled:
            return None
        current_state = self.get_current_state(now)
        return format_prompt_hint(current_state)

    def answer_status_query(self, now: float | None = None) -> str:
        current_state = self.get_current_state(now)
        return handle_affect_query(current_state)
