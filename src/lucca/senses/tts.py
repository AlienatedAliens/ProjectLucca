"""
Project Lucca — TTS Subsystem (Kokoro-82M)
Spec 07 §5, ADR-008
"""

import re
import time
from pathlib import Path
from typing import Final, Literal

import kokoro_onnx
import numpy as np
import numpy.typing as npt

from lucca.core.config import get_config
from lucca.core.ipc_schemas import TTSDonePayload
from lucca.senses.ring_buffer import FLAG_ABORT, SharedAudioRing

# Canonical Anime English Voice Blend Recipes
VOICE_RECIPES: Final[dict[str, str]] = {
    "genki_heroine": "blend:0.70*af_sky+0.30*jf_alpha",
    "anime_heroine_expressive": "blend:0.70*af_bella+0.30*af_sarah",
    "energetic_dub": "blend:0.60*af_bella+0.40*jf_gongitsune",
    "soft_kuudere": "blend:0.80*af_sarah+0.20*jf_tebukuro",
    "young_shonen": "blend:0.60*am_adam+0.40*af_sky",
}

VOICE_ALIASES: Final[dict[str, str]] = {
    "jf_teokure": "jf_tebukuro",
}


def enhance_anime_expressive_punctuation(text: str) -> str:
    """
    Applies expressive punctuation heuristics (cadence commas, ellipses, emphatic hyphens,
    and expressive punctuation) to shape Kokoro's G2P engine into dynamic anime pitch contours.
    Preserves URLs and code blocks intact.
    """
    if not text or not text.strip():
        return text

    if "```" in text or "http://" in text or "https://" in text:
        return text

    result = text
    interjections = [
        ("Oh wow.", "Oh wow!"),
        ("No way.", "No way!"),
        ("Aha.", "Aha!"),
        ("Look.", "Look!"),
        ("Yes.", "Yes!"),
        ("All right.", "All right!"),
    ]
    for orig, repl in interjections:
        result = result.replace(orig, repl)

    result = re.sub(r"\b(wait|well|listen),\s*", r"\1... ", result, flags=re.IGNORECASE)
    return result


def get_available_voices() -> list[str]:
    """Returns all verified Kokoro-82M voices (all 54 installed vectors) and recipe blends."""
    voices_path = Path(r"C:\ProjectLucca\models\tts\voices-v1.0.bin")
    if voices_path.exists():
        try:
            data = np.load(str(voices_path))
            return sorted(list(data.files) + list(VOICE_RECIPES.keys()))
        except Exception:  # noqa: BLE001
            pass
    # Full canonical list of 54 Kokoro-82M voices
    all_kokoro = [
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore",
        "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
        "am_onyx", "am_puck", "am_santa",
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
        "ef_dora", "em_alex", "em_santa",
        "ff_siwis", "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
        "if_sara", "im_nicola",
        "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
        "pf_dora", "pm_alex", "pm_santa",
        "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
        "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    ]
    return sorted(all_kokoro + list(VOICE_RECIPES.keys()))


def parse_voice_blend(
    engine: kokoro_onnx.Kokoro,
    voice_spec: str,
) -> str | npt.NDArray[np.float32]:
    """
    Parses a single voice ID or a linear blend formula (e.g. 'blend:0.70*af_sky+0.30*jf_alpha')
    and computes the normalized weighted vector sum over Kokoro 512-dim embedding matrices.
    """
    spec = VOICE_RECIPES.get(voice_spec, voice_spec).strip()
    if not spec.startswith("blend:") and "+" not in spec:
        return spec

    raw_formula = spec.removeprefix("blend:").strip()
    tokens = [t.strip() for t in raw_formula.split("+") if t.strip()]

    total_style: npt.NDArray[np.float32] | None = None
    total_weight = 0.0

    for token in tokens:
        if "*" in token:
            w_str, name = token.split("*", 1)
            weight = float(w_str.strip())
            name = name.strip()
        else:
            weight = 1.0
            name = token.strip()

        style = engine.get_voice_style(name)
        if total_style is None:
            total_style = (weight * style).astype(np.float32)
        else:
            total_style = (total_style + (weight * style)).astype(np.float32)
        total_weight += weight

    if total_style is not None and total_weight > 0.0:
        return (total_style / total_weight).astype(np.float32)

    return spec


class TTSWorker:
    def __init__(self, play_ring: SharedAudioRing) -> None:
        self.config = get_config()
        self.play_ring = play_ring
        self.device: Literal["NPU", "GPU", "CPU"] = "CPU"

        model_path = Path(r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx")
        voices_path = Path(r"C:\ProjectLucca\models\tts\voices-v1.0.bin")

        self.active_voice = self.config.tts.voice
        self.active_speed = getattr(self.config.tts, "speed", 1.05)
        self._blend_cache: dict[str, npt.NDArray[np.float32]] = {}

        if not model_path.exists() or not voices_path.exists():
            # Fallback to dev/mock if models missing
            self.engine: kokoro_onnx.Kokoro | None = None
        else:
            self.engine = kokoro_onnx.Kokoro(str(model_path), str(voices_path))

    def set_voice(self, voice: str) -> None:
        self.active_voice = voice

    def set_speed(self, speed: float) -> None:
        self.active_speed = speed

    def resolve_voice_style(self, voice_spec: str) -> str | npt.NDArray[np.float32]:
        """Resolves a voice string to either a native voice ID or cached blended array."""
        if self.engine is None:
            return voice_spec

        canonical_key = VOICE_RECIPES.get(voice_spec, voice_spec)
        if canonical_key in self._blend_cache:
            return self._blend_cache[canonical_key]

        style_or_str = parse_voice_blend(self.engine, canonical_key)
        if isinstance(style_or_str, np.ndarray):
            self._blend_cache[canonical_key] = style_or_str
        return style_or_str

    def synthesize(
        self,
        chunk_id: int,
        text: str,
        voice: str | None = None,
        speed: float | None = None,
        is_first: bool = False,  # noqa: ARG002
    ) -> TTSDonePayload:
        t0 = time.perf_counter()

        if self.play_ring.has_flag(FLAG_ABORT):
            return TTSDonePayload(chunk_id=chunk_id, samples=0, elapsed_ms=0.0, device=self.device)

        clean_text = text.strip()
        if not clean_text or self.engine is None:
            return TTSDonePayload(chunk_id=chunk_id, samples=0, elapsed_ms=0.0, device=self.device)

        raw_spec = voice or self.active_voice
        v_spec = VOICE_ALIASES.get(raw_spec, raw_spec)
        s = speed if speed is not None else self.active_speed
        resolved_voice = self.resolve_voice_style(v_spec)

        # Kokoro produces 24000 Hz float32 audio
        try:
            samples_f32, sr = self.engine.create(clean_text, voice=resolved_voice, speed=s)
        except Exception:  # noqa: BLE001
            # Fallback to default voice if custom/blended voice encounters issues
            fallback_voice = self.resolve_voice_style("af_sarah")
            samples_f32, sr = self.engine.create(clean_text, voice=fallback_voice, speed=s)
        dur_ms = (time.perf_counter() - t0) * 1000.0

        # Check abort again
        if self.play_ring.has_flag(FLAG_ABORT):
            return TTSDonePayload(
                chunk_id=chunk_id, samples=0, elapsed_ms=dur_ms, device=self.device
            )

        # Convert to int16 PCM [-32768, 32767]
        samples_int16 = (np.clip(samples_f32, -1.0, 1.0) * 32767).astype(np.int16)

        # Write directly into 24 kHz playback ring
        written = self.play_ring.write(samples_int16)

        return TTSDonePayload(
            chunk_id=chunk_id,
            samples=written,
            elapsed_ms=dur_ms,
            device=self.device,
        )
