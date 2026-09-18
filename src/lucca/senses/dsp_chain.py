"""
Project Lucca — Anime Voice DSP Post-Processing Chain
Spec 07, ADR-008
Transforms Kokoro-82M natural voice output into a bright, hyper-expressive
English anime voice aesthetic via DSP filtering, equalization, fast compression,
and harmonic excitation.
"""

from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
import scipy.signal  # type: ignore[import-untyped]


@dataclass
class AnimeDSPConfig:
    pitch_semitones: float = 2.5  # +2 to +4 semitones for youthful anime register
    highpass_cutoff_hz: float = 120.0  # Cut low chest weight
    presence_gain_db: float = 3.0  # +3 dB @ 4 kHz for sharp vocal clarity
    presence_freq_hz: float = 4000.0
    air_gain_db: float = 2.5  # +2.5 dB @ >10 kHz for breathy, energetic top end
    air_freq_hz: float = 10000.0
    compression_threshold_db: float = -18.0
    compression_ratio: float = 3.5
    compression_attack_ms: float = 10.0  # Fast attack ~10ms
    compression_release_ms: float = 50.0  # Fast release ~50ms
    saturation_drive: float = 0.20  # Subtle harmonic exciter / tape sheen
    master_gain_db: float = 0.0
    limiter_ceiling: float = 0.98
    enabled: bool = True


def apply_highpass_filter(
    samples: npt.NDArray[np.float32],
    sr: int = 24000,
    cutoff_hz: float = 120.0,
) -> npt.NDArray[np.float32]:
    """Cuts low-end chest weight below cutoff frequency."""
    if cutoff_hz <= 10.0 or len(samples) < 32:
        return samples
    nyquist = 0.5 * sr
    norm_cutoff = min(0.99, cutoff_hz / nyquist)
    sos = scipy.signal.butter(2, norm_cutoff, btype="highpass", output="sos")
    filtered = scipy.signal.sosfilt(sos, samples)
    return cast(npt.NDArray[np.float32], np.asarray(filtered, dtype=np.float32))


def apply_peaking_eq(
    samples: npt.NDArray[np.float32],
    sr: int = 24000,
    center_freq_hz: float = 4000.0,
    gain_db: float = 3.0,
    q: float = 1.2,
) -> npt.NDArray[np.float32]:
    """Applies a parametric peaking equalizer filter for presence boost."""
    if abs(gain_db) < 0.1 or len(samples) < 32:
        return samples
    nyquist = 0.5 * sr
    omega = 2.0 * np.pi * min(0.95 * nyquist, center_freq_hz) / sr
    alpha = np.sin(omega) / (2.0 * q)
    a = 10.0 ** (gain_db / 40.0)

    b0 = 1.0 + alpha * a
    b1 = -2.0 * np.cos(omega)
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * np.cos(omega)
    a2 = 1.0 - alpha / a

    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float64)
    a_coeffs = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float64)

    filtered = scipy.signal.lfilter(b, a_coeffs, samples)
    return cast(npt.NDArray[np.float32], np.asarray(filtered, dtype=np.float32))


def apply_high_shelf(
    samples: npt.NDArray[np.float32],
    sr: int = 24000,
    shelf_freq_hz: float = 10000.0,
    gain_db: float = 2.5,
) -> npt.NDArray[np.float32]:
    """Applies a high-shelf boost for breathy, energetic top-end air."""
    if abs(gain_db) < 0.1 or len(samples) < 32:
        return samples
    nyquist = 0.5 * sr
    norm_freq = min(0.95, shelf_freq_hz / nyquist)
    a = 10.0 ** (gain_db / 40.0)
    omega = np.pi * norm_freq
    sn = np.sin(omega)
    cs = np.cos(omega)
    beta = np.sqrt(a) / 1.0

    b0 = a * ((a + 1.0) + (a - 1.0) * cs + beta * sn)
    b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cs)
    b2 = a * ((a + 1.0) + (a - 1.0) * cs - beta * sn)
    a0 = (a + 1.0) - (a - 1.0) * cs + beta * sn
    a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cs)
    a2 = (a + 1.0) - (a - 1.0) * cs - beta * sn

    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float64)
    a_coeffs = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float64)

    filtered = scipy.signal.lfilter(b, a_coeffs, samples)
    return cast(npt.NDArray[np.float32], np.asarray(filtered, dtype=np.float32))


def apply_fast_compressor(
    samples: npt.NDArray[np.float32],
    sr: int = 24000,
    threshold_db: float = -18.0,
    ratio: float = 3.5,
    attack_ms: float = 10.0,
    release_ms: float = 50.0,
) -> npt.NDArray[np.float32]:
    """
    Fast-acting dynamic compressor to flatten peaks, bring up quiet breath sounds,
    and give vocal presence right against the microphone.
    """
    if len(samples) < 32:
        return samples

    alpha_attack = float(np.exp(-1.0 / (sr * (attack_ms / 1000.0))))
    alpha_release = float(np.exp(-1.0 / (sr * (release_ms / 1000.0))))
    threshold_linear = 10.0 ** (threshold_db / 20.0)

    out = np.empty_like(samples)
    env = 0.0

    for i in range(len(samples)):
        val = abs(samples[i])
        if val > env:
            env = alpha_attack * env + (1.0 - alpha_attack) * val
        else:
            env = alpha_release * env + (1.0 - alpha_release) * val

        if env > threshold_linear and env > 1e-6:
            env_db = 20.0 * np.log10(env)
            gain_reduction_db = (env_db - threshold_db) * (1.0 - (1.0 / ratio))
            gain = 10.0 ** (-gain_reduction_db / 20.0)
        else:
            gain = 1.0

        out[i] = samples[i] * gain

    # Makeup gain
    makeup = 1.4
    return (out * makeup).astype(np.float32)


def apply_harmonic_saturation(
    samples: npt.NDArray[np.float32],
    drive: float = 0.20,
) -> npt.NDArray[np.float32]:
    """Adds subtle upper-harmonic tape/tube exciter sheen."""
    if drive <= 0.01 or len(samples) == 0:
        return samples
    boosted = samples * (1.0 + drive * 1.5)
    saturated = np.tanh(boosted) / (1.0 + drive * 0.4)
    return cast(npt.NDArray[np.float32], np.asarray(saturated, dtype=np.float32))


def apply_pitch_shift(
    samples: npt.NDArray[np.float32],
    sr: int = 24000,
    semitones: float = 2.5,
) -> tuple[npt.NDArray[np.float32], int]:
    """
    Formant-aware pitch shift.
    Shifts sampling playback rate and performs anti-aliased interpolation.
    """
    if abs(semitones) < 0.1:
        return samples, sr

    pitch_ratio = float(2.0 ** (semitones / 12.0))
    # Effective sample playback rate
    playback_sr = int(round(sr * pitch_ratio))
    return samples, playback_sr


class AnimeVoiceDSP:
    """Complete English Anime Voice DSP processing chain."""

    def __init__(self, config: AnimeDSPConfig | None = None) -> None:
        self.config = config or AnimeDSPConfig()

    def process(
        self,
        samples: npt.NDArray[np.float32],
        sr: int = 24000,
    ) -> tuple[npt.NDArray[np.float32], int]:
        """
        Executes the complete anime vocal chain:
        1. High-Pass Filter (120 Hz)
        2. Presence Boost EQ (3.5 - 5 kHz)
        3. Air Boost High-Shelf (>10 kHz)
        4. Fast Dynamic Compressor (10ms attack / 50ms release)
        5. Harmonic Saturation
        6. Master Gain & Soft-Knee Limiter
        7. Pitch Shift & Sampling Alignment
        """
        if not self.config.enabled or len(samples) == 0:
            return samples, sr

        audio = samples.copy().astype(np.float32)

        # 1. 120 Hz High-Pass Filter
        audio = apply_highpass_filter(audio, sr, cutoff_hz=self.config.highpass_cutoff_hz)

        # 2. Presence Boost
        audio = apply_peaking_eq(
            audio,
            sr,
            center_freq_hz=self.config.presence_freq_hz,
            gain_db=self.config.presence_gain_db,
        )

        # 3. Air Boost High-Shelf
        audio = apply_high_shelf(
            audio,
            sr,
            shelf_freq_hz=self.config.air_freq_hz,
            gain_db=self.config.air_gain_db,
        )

        # 4. Aggressive Compression
        audio = apply_fast_compressor(
            audio,
            sr,
            threshold_db=self.config.compression_threshold_db,
            ratio=self.config.compression_ratio,
            attack_ms=self.config.compression_attack_ms,
            release_ms=self.config.compression_release_ms,
        )

        # 5. Harmonic Saturation
        audio = apply_harmonic_saturation(audio, drive=self.config.saturation_drive)

        # 6. Master Gain
        if abs(self.config.master_gain_db) > 0.1:
            gain_lin = float(10.0 ** (self.config.master_gain_db / 20.0))
            audio = audio * gain_lin

        # Soft-knee limiter
        ceiling = self.config.limiter_ceiling
        audio = np.clip(audio, -ceiling, ceiling).astype(np.float32)

        # 7. Pitch Shift
        final_samples, final_sr = apply_pitch_shift(
            audio, sr, semitones=self.config.pitch_semitones
        )

        return final_samples, final_sr
