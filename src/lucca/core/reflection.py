"""
Project Lucca — Core Reflection & Offline Consolidation Alias Module
Re-exports ReflectionEngine, IdlePulse, DreamRetrospective, CoherenceDrive,
CompetenceDrive, and related models from lucca.memory.reflection.
"""

from __future__ import annotations

from lucca.memory.reflection import (
    CoherenceDrive,
    CompetenceDrive,
    DreamRetrospective,
    DreamRetrospectiveResult,
    IdlePulse,
    IdlePulseResult,
    ReflectionEngine,
    is_rule_conflict,
    log_learning_event,
    quarantine_rejected_distillate,
)

__all__ = [
    "CoherenceDrive",
    "CompetenceDrive",
    "DreamRetrospective",
    "DreamRetrospectiveResult",
    "IdlePulse",
    "IdlePulseResult",
    "ReflectionEngine",
    "is_rule_conflict",
    "log_learning_event",
    "quarantine_rejected_distillate",
]
