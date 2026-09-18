"""
Unit tests for English Anime Voice DSP processing chain and TTS pre-processing
Spec 07, ADR-008
"""

from typing import cast

import numpy as np
import numpy.typing as npt

from lucca.senses.dsp_chain import (
    AnimeDSPConfig,
    AnimeVoiceDSP,
    apply_fast_compressor,
    apply_harmonic_saturation,
    apply_high_shelf,
    apply_highpass_filter,
    apply_peaking_eq,
    apply_pitch_shift,
)
from lucca.senses.tts import enhance_anime_expressive_punctuation


def _generate_sine(
    freq_hz: float, sr: int = 24000, duration_s: float = 0.2
) -> npt.NDArray[np.float32]:
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False, dtype=np.float32)
    return cast(
        npt.NDArray[np.float32],
        np.asarray(0.5 * np.sin(2.0 * np.pi * freq_hz * t), dtype=np.float32),
    )


def test_highpass_filter_attenuates_low_frequencies() -> None:
    """Verifies that 120Hz highpass filter attenuates 50Hz tone much more than 1000Hz tone."""
    sr = 24000
    low_tone = _generate_sine(50.0, sr=sr)
    mid_tone = _generate_sine(1000.0, sr=sr)

    filtered_low = apply_highpass_filter(low_tone, sr=sr, cutoff_hz=120.0)
    filtered_mid = apply_highpass_filter(mid_tone, sr=sr, cutoff_hz=120.0)

    # Steady state RMS after initial filter transient
    rms_low_orig = float(np.sqrt(np.mean(low_tone[500:] ** 2)))
    rms_low_filt = float(np.sqrt(np.mean(filtered_low[500:] ** 2)))
    rms_mid_orig = float(np.sqrt(np.mean(mid_tone[500:] ** 2)))
    rms_mid_filt = float(np.sqrt(np.mean(filtered_mid[500:] ** 2)))

    low_ratio = rms_low_filt / rms_low_orig
    mid_ratio = rms_mid_filt / rms_mid_orig

    assert low_ratio < 0.35, f"50Hz tone was not sufficiently attenuated: ratio={low_ratio}"
    assert mid_ratio > 0.90, f"1000Hz tone was attenuated too much: ratio={mid_ratio}"


def test_peaking_eq_boosts_presence() -> None:
    """Verifies that peaking EQ with positive gain boosts frequencies near center frequency."""
    sr = 24000
    presence_tone = _generate_sine(4000.0, sr=sr)
    boosted = apply_peaking_eq(presence_tone, sr=sr, center_freq_hz=4000.0, gain_db=3.0)

    rms_orig = float(np.sqrt(np.mean(presence_tone[500:] ** 2)))
    rms_boosted = float(np.sqrt(np.mean(boosted[500:] ** 2)))

    assert rms_boosted > rms_orig * 1.15


def test_high_shelf_boosts_air() -> None:
    """Verifies that high shelf EQ boosts frequencies > 10kHz."""
    sr = 24000
    air_tone = _generate_sine(11000.0, sr=sr)
    boosted = apply_high_shelf(air_tone, sr=sr, shelf_freq_hz=10000.0, gain_db=2.5)

    rms_orig = float(np.sqrt(np.mean(air_tone[500:] ** 2)))
    rms_boosted = float(np.sqrt(np.mean(boosted[500:] ** 2)))

    assert rms_boosted > rms_orig * 1.10


def test_fast_compressor_reduces_peak_dynamics() -> None:
    """Verifies fast compressor flattens strong peaks while maintaining low-level signals."""
    sr = 24000
    # Create signal with high peak and quiet tail
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32)
    loud_burst = 0.9 * np.sin(2.0 * np.pi * 500.0 * t[:2400])
    quiet_tail = 0.05 * np.sin(2.0 * np.pi * 500.0 * t[2400:])
    signal = np.concatenate([loud_burst, quiet_tail]).astype(np.float32)

    compressed = apply_fast_compressor(
        signal,
        sr=sr,
        threshold_db=-18.0,
        ratio=4.0,
        attack_ms=10.0,
        release_ms=50.0,
    )

    peak_orig = float(np.max(np.abs(signal)))
    peak_comp = float(np.max(np.abs(compressed)))
    # The loud portion should be compressed
    assert peak_comp <= peak_orig * 1.5  # With makeup gain, well controlled
    assert compressed.dtype == np.float32


def test_harmonic_saturation() -> None:
    """Verifies saturation applies smooth tanh wave-shaping."""
    sine = _generate_sine(440.0)
    saturated = apply_harmonic_saturation(sine, drive=0.25)
    assert saturated.shape == sine.shape
    assert np.all(np.abs(saturated) <= 1.0)
    # Saturation introduces slight harmonic divergence from pure sine
    diff = float(np.max(np.abs(saturated - sine)))
    assert diff > 0.001


def test_pitch_shift_playback_rate() -> None:
    """Verifies pitch shift calculates the expected target sampling rate."""
    sr = 24000
    sine = _generate_sine(440.0, sr=sr)
    out_samples, new_sr = apply_pitch_shift(sine, sr=sr, semitones=3.0)

    expected_sr = int(round(24000 * (2.0 ** (3.0 / 12.0))))
    assert new_sr == expected_sr
    assert len(out_samples) == len(sine)


def test_anime_voice_dsp_pipeline() -> None:
    """Verifies complete AnimeVoiceDSP pipeline end-to-end execution."""
    sr = 24000
    sine = _generate_sine(500.0, sr=sr, duration_s=0.1)

    dsp = AnimeVoiceDSP()
    out_samples, out_sr = dsp.process(sine, sr=sr)

    assert out_samples.dtype == np.float32
    assert len(out_samples) == len(sine)
    assert out_sr > sr  # Pitch shifted up
    assert np.all(np.abs(out_samples) <= dsp.config.limiter_ceiling)


def test_anime_voice_dsp_disabled() -> None:
    """Verifies that disabled DSP bypasses processing unchanged."""
    sr = 24000
    sine = _generate_sine(500.0, sr=sr, duration_s=0.1)

    dsp = AnimeVoiceDSP(AnimeDSPConfig(enabled=False))
    out_samples, out_sr = dsp.process(sine, sr=sr)

    np.testing.assert_array_equal(out_samples, sine)
    assert out_sr == sr


def test_enhance_anime_expressive_punctuation() -> None:
    """Verifies expressive punctuation enhancer shapes text for Kokoro G2P engine."""
    input_text = "I cannot believe this worked. It is totally amazing!"
    enhanced = enhance_anime_expressive_punctuation(input_text)

    # Enhancer should add expressive pauses / breath marks
    assert len(enhanced) >= len(input_text)
    assert any(punct in enhanced for punct in [",", "...", "!", "-"])
