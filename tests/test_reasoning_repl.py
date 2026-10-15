"""
Unit tests for Reasoning REPL, Task Registry, and Episodic Solution Cache
v1.44.0 General Reasoning Core
"""

from pathlib import Path
import tempfile
import pytest

from lucca.memory.episodic_cache import EpisodicSolutionCache
from lucca.reasoning.repl_loop import ReasoningREPL, TaskRegistry


def test_task_registry_resolution() -> None:
    registry = TaskRegistry()

    # Minimal task resolution
    min_task = registry.resolve_task_path("CenterMinimal")
    assert min_task is not None
    assert min_task.exists()
    assert min_task.name == "CenterMinimal.json"

    # ConceptARC corpus resolution
    corpus_task = registry.resolve_task_path("AboveBelow1")
    assert corpus_task is not None
    assert corpus_task.exists()
    assert corpus_task.name == "AboveBelow1.json"


def test_episodic_solution_cache(tmp_path: Path) -> None:
    cache_file = tmp_path / "episodic_solutions.json"
    cache = EpisodicSolutionCache(cache_file=cache_file)

    task_data = {
        "train": [
            {"input": [[1, 0], [0, 1]], "output": [[2, 0], [0, 2]]},
            {"input": [[3, 0], [0, 3]], "output": [[4, 0], [0, 4]]},
        ],
        "test": [{"input": [[5, 0], [0, 5]], "output": [[6, 0], [0, 6]]}],
    }

    # Cache should be initially empty
    hit = cache.lookup(task_data)
    assert hit is None

    # Store verified code
    code = """
import numpy as np

def transform(grid):
    arr = np.array(grid)
    return np.where(arr > 0, arr + 1, 0).tolist()
"""
    cache.store(task_id="TestTask", task_data=task_data, code=code)

    # Reload cache and lookup
    cache2 = EpisodicSolutionCache(cache_file=cache_file)
    hit2 = cache2.lookup(task_data)
    assert hit2 is not None
    assert hit2.task_id == "TestTask"
    assert "transform" in hit2.code

    stats = cache2.stats()
    assert stats["total_solutions"] == 1


def test_reasoning_repl_task_loading() -> None:
    repl = ReasoningREPL(use_color=False)
    loaded = repl.load_task("CenterMinimal")
    assert loaded is True
    assert repl.active_task_id == "CenterMinimal"
    assert repl.active_task_data is not None
    assert len(repl.active_task_data["train"]) > 0


def test_reasoning_repl_eval_python() -> None:
    repl = ReasoningREPL(use_color=False)
    repl.load_task("CenterMinimal")

    # Evaluate simple transform on loaded task
    code = """
def transform(grid):
    return grid
"""
    repl.eval_python(code, train_idx=0)
    assert repl.active_task_id == "CenterMinimal"
