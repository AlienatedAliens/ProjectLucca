"""
Project Lucca — Speech Subsystem
Spec 07 §5, Spec 16 §4, ADR-008, WO-27
"""

try:
    from lucca.senses.tts import CosyVoice2Worker, TTSWorker
    __all__ = ["CosyVoice2Worker", "TTSWorker"]
except (ImportError, ModuleNotFoundError):
    __all__ = []
