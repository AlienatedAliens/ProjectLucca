"""
Project Lucca — Affect & Persona Tests (ADR-009, Spec 16 §3, §4)
"""

from lucca.core.affect import (
    AffectSignal,
    AffectState,
    AffectTracker,
    apply_affect_signal,
    decay_affect,
    format_prompt_hint,
    get_tts_speed_multiplier,
    handle_affect_query,
)


def test_affect_signal_and_decay():
    """Verify signal updates valence/arousal and decays over tau."""
    t0 = 1000.0
    state = AffectState(valence=0.0, arousal=0.0, updated_at=t0)

    # 1. Apply double interrupt -> arousal up, valence down
    state = apply_affect_signal(state, AffectSignal.DOUBLE_INTERRUPT, now=t0)
    assert state.arousal > 0.3
    assert state.valence < -0.15
    assert "interrupted twice in a row" in state.causes

    # 2. Check TTS speed multiplier increases with arousal
    speed = get_tts_speed_multiplier(state)
    assert 1.0 < speed <= 1.10

    # 3. Decay over 600s (one tau) -> decayed by ~1/e (~0.368)
    t1 = t0 + 600.0
    decayed = decay_affect(state, now=t1, tau=600.0)
    assert abs(decayed.arousal - (state.arousal * 0.3678)) < 0.05
    assert abs(decayed.valence - (state.valence * 0.3678)) < 0.05

    # 4. Long time decay (2000s) snaps to 0.0
    t2 = t0 + 2000.0
    deep_decay = decay_affect(state, now=t2, tau=600.0)
    assert deep_decay.arousal == 0.0
    assert deep_decay.valence == 0.0
    assert deep_decay.causes == []


def test_affect_honest_query_response():
    """Verify answers to 'how are you feeling' are truthful and non-theatrical."""
    t0 = 1000.0
    state = AffectState(valence=0.0, arousal=0.0, updated_at=t0)
    neutral_resp = handle_affect_query(state)
    assert "neutral" in neutral_resp.lower()

    # Tool failure -> subdued
    state = apply_affect_signal(
        state, AffectSignal.TOOL_FAILURE, custom_cause="database write timeout", now=t0
    )
    subdued_resp = handle_affect_query(state)
    assert "subdued" in subdued_resp.lower() or "flat" in subdued_resp.lower()
    assert "database write timeout" in subdued_resp
    # Must NOT claim fake emotional theatre
    assert "i am sad" not in subdued_resp.lower()

    # Prompt hint
    hint = format_prompt_hint(state)
    assert hint is not None
    assert "subdued" in hint
    assert "database write timeout" in hint


def test_affect_tracker_lifecycle():
    """Verify tracker manages state, config, and signals."""
    tracker = AffectTracker()
    tracker.state = AffectState(valence=0.0, arousal=0.0, updated_at=100.0)

    tracker.record_signal(AffectSignal.USER_PRAISE, now=100.0)
    st = tracker.get_current_state(now=100.0)
    assert st.valence > 0.2

    hint = tracker.get_prompt_hint(now=100.0)
    assert hint is not None
    assert "upbeat" in hint

    status = tracker.answer_status_query(now=100.0)
    assert "positive" in status.lower() or "well" in status.lower()
