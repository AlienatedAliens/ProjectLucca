"""
Project Lucca — Speech TTS Subsystem
Spec 07 §5, Spec 16 §4, ADR-008, WO-27
Re-exports TTSWorker, CosyVoice2Worker, and affective vocal synthesis helpers.
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

__all__ = [
    "VOICE_ALIASES",
    "VOICE_RECIPES",
    "CosyVoice3Client",
    "TTSWorker",
    "enhance_anime_expressive_punctuation",
    "format_cosyvoice_instruct",
    "get_available_voices",
    "parse_voice_blend",
]
