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
from lucca.speech.cosyvoice_client import CosyVoice3Client, format_cosyvoice_instruct
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

__all__ = [
    "ENGINE_CATALOG",
    "KITTEN_VOICES",
    "KOKOCLONE_PRESETS",
    "POCKET_VOICES",
    "SUPERTONIC_VOICES",
    "VOICE_ALIASES",
    "VOICE_RECIPES",
    "BaseVoiceEngine",
    "CosyVoice3Client",
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
    "format_cosyvoice_instruct",
    "get_available_voices",
    "get_kokoclone_metadata",
    "get_voice_engine",
    "normalize_text",
    "parse_engine_from_spec",
    "parse_voice_blend",
]
