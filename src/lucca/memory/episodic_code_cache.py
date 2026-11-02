"""
Project Lucca — Episodic Code Cache (CBR 4 Rs Alias Module)
Re-exports EpisodicCodeCache, EpisodicSolutionCache, CachedSolution, and CodeEpisode
from lucca.memory.episodic_cache so imports from either module path work seamlessly.
"""

from __future__ import annotations

from lucca.memory.episodic_cache import (
    DEFAULT_CACHE_PATH,
    CachedSolution,
    CodeEpisode,
    EpisodicCodeCache,
    EpisodicSolutionCache,
    compute_goal_hash,
    compute_goal_signature,
    compute_invariant_signature,
    compute_task_hash,
)

__all__ = [
    "DEFAULT_CACHE_PATH",
    "CachedSolution",
    "CodeEpisode",
    "EpisodicCodeCache",
    "EpisodicSolutionCache",
    "compute_goal_hash",
    "compute_goal_signature",
    "compute_invariant_signature",
    "compute_task_hash",
]
