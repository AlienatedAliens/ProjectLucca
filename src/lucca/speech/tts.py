"""
Project Lucca — Speech TTS Subsystem
Spec 07 §5, Spec 16 §4, ADR-008, WO-30
Re-exports TTSWorker, Kokoro, KittenTTS, Pocket TTS, Supertonic 3, and KokoClone.
"""

from lucca.senses.tts import (
    VOICE_ALIASES,
    VOICE_RECIPES,
    TTSWorker,
    enhance_anime_expressive_punctuation,
    get_available_voices,
    parse_voice_blend,
)
from lucca.speech.engines import (
    ENGINE_CATALOG,
    KITTEN_VOICES,
    KOKOCLONE_PRESETS,
    POCKET_VOICES,
    SUPERTONIC_VOICES,
    BaseVoiceEngine,
    KittenTTSEngine,
    KokoCloneEngine,
    KokoroEngine,
    PocketTTSEngine,
    Supertonic3Engine,
    VoiceEngineDescriptor,
    get_voice_engine,
    parse_engine_from_spec,
)
from lucca.speech.kokoclone import compute_cloned_style_vector, get_kokoclone_metadata
from lucca.speech.text_normalizer import KittenTextNormalizer, normalize_text

def modulate_epistemic_prosody(
    base_speed: float = 1.05,
    base_pitch_semitones: float = 0.0,
    epistemic_status: str = "NEUTRAL",
) -> tuple[float, float]:
    """
    Modulates Kokoro TTS prosody based on verified epistemic status (Milestone 36.4).
    - CHECKED_FORMALIZATION_AGREED: crisp, assertive, slightly faster pace (+5%), steady pitch.
    - SPECULATION: tentative, slower pace (-8%), inquisitive pitch (+0.5 semitones).
    - Otherwise: returns base speed and base pitch.
    """
    if epistemic_status == "CHECKED_FORMALIZATION_AGREED":
        speed = round(base_speed * 1.05, 3)
        pitch = round(base_pitch_semitones, 2)
        return speed, pitch
    elif epistemic_status == "SPECULATION":
        speed = round(base_speed * 0.92, 3)
        pitch = round(base_pitch_semitones + 0.50, 2)
        return speed, pitch
    return base_speed, base_pitch_semitones


__all__ = [
    "ENGINE_CATALOG",
    "KITTEN_VOICES",
    "KOKOCLONE_PRESETS",
    "POCKET_VOICES",
    "SUPERTONIC_VOICES",
    "VOICE_ALIASES",
    "VOICE_RECIPES",
    "BaseVoiceEngine",
    "KittenTTSEngine",
    "KittenTextNormalizer",
    "KokoCloneEngine",
    "KokoroEngine",
    "PocketTTSEngine",
    "Supertonic3Engine",
    "TTSWorker",
    "VoiceEngineDescriptor",
    "compute_cloned_style_vector",
    "enhance_anime_expressive_punctuation",
    "get_available_voices",
    "get_kokoclone_metadata",
    "get_voice_engine",
    "modulate_epistemic_prosody",
    "normalize_text",
    "parse_engine_from_spec",
    "parse_voice_blend",
]
