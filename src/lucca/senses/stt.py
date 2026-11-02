"""
Project Lucca — Speech-to-Text (STT) & Wake-Word Normalization Module
Re-exports ASRWorker, STTWorker, and normalize_lucca_wake_word from lucca.senses.asr.
"""

from __future__ import annotations

from lucca.senses.asr import ASRWorker, normalize_lucca_wake_word

STTWorker = ASRWorker

__all__ = [
    "ASRWorker",
    "STTWorker",
    "normalize_lucca_wake_word",
]
