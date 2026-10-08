"""
Project Lucca — Speech Subsystem
Spec 07 §5, Spec 16 §4, ADR-008, WO-27
"""

try:
    from lucca.senses.tts import TTSWorker
    __all__ = ["TTSWorker"]
except (ImportError, ModuleNotFoundError):
    __all__ = []
