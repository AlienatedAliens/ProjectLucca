"""
Project Lucca — Speech TTS Subsystem
Spec 07 §5, Spec 16 §4, ADR-008, WO-27
Re-exports TTSWorker, CosyVoice2Worker, and affective vocal synthesis helpers.
"""

from lucca.senses.tts import (
    VOICE_ALIASES,
    VOICE_RECIPES,
    CosyVoice2Worker,
    TTSWorker,
    enhance_anime_expressive_punctuation,
    get_available_voices,
    parse_voice_blend,
)

__all__ = [
    "VOICE_ALIASES",
    "VOICE_RECIPES",
    "CosyVoice2Worker",
    "TTSWorker",
    "enhance_anime_expressive_punctuation",
    "get_available_voices",
    "parse_voice_blend",
]
