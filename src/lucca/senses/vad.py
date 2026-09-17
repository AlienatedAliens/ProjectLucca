"""
Project Lucca — Voice Activity Detection (VAD)
Spec 07 §3
"""

import numpy as np
import numpy.typing as npt


class EnergyVAD:
    """
    Fast, lightweight frame-based energy VAD for 16 kHz audio.
    Computes speech segments and trims leading/trailing silence.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        threshold_db: float = -42.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = (sample_rate * frame_ms) // 1000
        self.threshold_linear = 10.0 ** (threshold_db / 20.0)

    def process(self, samples: npt.NDArray[np.generic]) -> tuple[float, int, int]:
        """
        Analyzes audio samples and returns:
        (vad_speech_ms, start_sample_idx, end_sample_idx)
        """
        if len(samples) == 0:
            return 0.0, 0, 0

        # Convert to float [-1.0, 1.0] if int16
        if samples.dtype == np.int16:
            audio_f = samples.astype(np.float32) / 32768.0
        else:
            audio_f = samples.astype(np.float32)

        n_frames = len(audio_f) // self.frame_samples
        if n_frames == 0:
            return 0.0, 0, len(samples)

        # Reshape to 2D frames
        usable_samples = n_frames * self.frame_samples
        frames = audio_f[:usable_samples].reshape(n_frames, self.frame_samples)

        # Compute RMS per frame
        frame_rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
        is_speech = frame_rms > self.threshold_linear

        speech_indices = np.where(is_speech)[0]
        if len(speech_indices) == 0:
            return 0.0, 0, 0

        first_speech_frame = int(speech_indices[0])
        last_speech_frame = int(speech_indices[-1])

        speech_frames_count = int(np.sum(is_speech))
        speech_ms = (speech_frames_count * self.frame_samples * 1000.0) / self.sample_rate

        start_sample = max(0, first_speech_frame * self.frame_samples)
        end_sample = min(len(samples), (last_speech_frame + 1) * self.frame_samples)

        return float(speech_ms), start_sample, end_sample
