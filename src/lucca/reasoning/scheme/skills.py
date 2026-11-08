"""Scheme skill constants and lazy re-exports from lucca.reasoning.skills."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from lucca.reasoning.skills import (
        Skill,
        SkillError,
        SkillLibrary,
        SkillLimitExceededError,
        SkillManager,
        SkillNotFoundError,
        SkillPackage,
        SkillValidationError,
        resolve_skills_dir,
    )

ACTIVE_SKILL_LIMIT: Final[int] = 30

__all__ = [
    "ACTIVE_SKILL_LIMIT",
    "Skill",
    "SkillError",
    "SkillLibrary",
    "SkillLimitExceededError",
    "SkillManager",
    "SkillNotFoundError",
    "SkillPackage",
    "SkillValidationError",
    "resolve_skills_dir",
]


def __getattr__(name: str) -> object:
    if name in __all__:
        mod = importlib.import_module("lucca.reasoning.skills")
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
