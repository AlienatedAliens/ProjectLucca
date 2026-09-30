"""
Project Lucca — RVC Voice Conversion Module
Provides SynthesizerTrn generator and HuBERT feature projection for character voice synthesis.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SynthesizerTrnMs256NSFsid, SynthesizerTrnMs768NSFsid

try:
    from .models import SynthesizerTrnMs256NSFsid, SynthesizerTrnMs768NSFsid

    __all__ = ["SynthesizerTrnMs768NSFsid", "SynthesizerTrnMs256NSFsid"]
except ImportError:
    __all__ = []
