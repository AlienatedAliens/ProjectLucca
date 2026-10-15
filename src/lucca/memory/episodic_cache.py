"""
Project Lucca — Episodic Solution Cache
v1.44.0 Deterministic Lifelong Reasoning Memory (Pillar 3)

Provides zero-token instant recall for previously verified neurosymbolic programs.
When a synthesized program passes 100% of training assertions, it is cataloged
in the episodic solution cache keyed by both exact task hash and structural invariants.

On subsequent encounters:
1. Re-verifies cached candidate against the current demonstrations in < 1 ms.
2. If 100% verified, returns immediately with 0 LLM queries.
3. Completely eliminates stochastic run-to-run sampling variance for regression tests.

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Final

import structlog

from lucca.reasoning.cegis_unshackled import execute_unshackled_python

logger = structlog.get_logger(__name__)

DEFAULT_CACHE_PATH: Final[Path] = Path("data/episodic_solutions.json")


@dataclass(frozen=True)
class CachedSolution:
    """Record of a verified program stored in the episodic cache."""

    task_id: str
    task_hash: str
    invariant_signature: str
    code: str
    method: str
    turns_taken: int
    verified_at: str
    train_demonstrations_count: int


def compute_task_hash(train_pairs: list[dict[str, list[list[int]]]]) -> str:
    """Computes a deterministic SHA-256 hash of training input/output matrices."""
    serialized = json.dumps(train_pairs, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def compute_invariant_signature(train_pairs: list[dict[str, list[list[int]]]]) -> str:
    """
    Computes a structural invariant signature based on shape ratios,
    palette changes, and symmetry patterns.
    """
    if not train_pairs:
        return "empty"

    shape_deltas: list[str] = []
    palette_invariants: list[str] = []

    for pair in train_pairs:
        g_in = pair.get("input", [])
        g_out = pair.get("output", [])
        h_in = len(g_in)
        w_in = len(g_in[0]) if h_in > 0 else 0
        h_out = len(g_out)
        w_out = len(g_out[0]) if h_out > 0 else 0

        # Shape relation
        if (h_in, w_in) == (h_out, w_out):
            shape_deltas.append("preserve")
        elif h_out == 1 and w_out > 1:
            shape_deltas.append(f"tally_1x{w_out}")
        elif h_out > 1 and w_out == 1:
            shape_deltas.append(f"tally_{h_out}x1")
        else:
            shape_deltas.append(f"{h_in}x{w_in}->{h_out}x{w_out}")

        # Colors
        colors_in = {c for row in g_in for c in row}
        colors_out = {c for row in g_out for c in row}
        if colors_out.issubset(colors_in):
            palette_invariants.append("subset")
        else:
            palette_invariants.append(f"+{len(colors_out - colors_in)}")

    sig = f"shapes:{','.join(shape_deltas[:3])}|pal:{','.join(palette_invariants[:3])}"
    return sig


class EpisodicSolutionCache:
    """
    Persistent episodic memory store for verified neurosymbolic code solutions.
    """

    def __init__(self, cache_file: Path = DEFAULT_CACHE_PATH) -> None:
        self.cache_file = cache_file
        self._exact_hash_index: dict[str, CachedSolution] = {}
        self._signature_index: dict[str, list[CachedSolution]] = {}
        self._load()

    def _load(self) -> None:
        """Loads cached solutions from disk into memory indexes."""
        if not self.cache_file.exists():
            return

        try:
            raw_text = self.cache_file.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            if isinstance(data, list):
                for item in data:
                    sol = CachedSolution(
                        task_id=str(item.get("task_id", "")),
                        task_hash=str(item.get("task_hash", "")),
                        invariant_signature=str(item.get("invariant_signature", "")),
                        code=str(item.get("code", "")),
                        method=str(item.get("method", "CEGIS")),
                        turns_taken=int(item.get("turns_taken", 1)),
                        verified_at=str(item.get("verified_at", "")),
                        train_demonstrations_count=int(item.get("train_demonstrations_count", 0)),
                    )
                    if sol.task_hash:
                        self._exact_hash_index[sol.task_hash] = sol
                    if sol.invariant_signature:
                        self._signature_index.setdefault(sol.invariant_signature, []).append(sol)
            logger.info("episodic_cache_loaded", entries=len(self._exact_hash_index))
        except Exception as exc:
            logger.warning("episodic_cache_load_error", error=str(exc))

    def _persist(self) -> None:
        """Saves current cache entries to disk atomically."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            entries = [asdict(sol) for sol in self._exact_hash_index.values()]
            temp_file = self.cache_file.with_suffix(".tmp")
            temp_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")
            temp_file.replace(self.cache_file)
            logger.info("episodic_cache_persisted", total_entries=len(entries))
        except Exception as exc:
            logger.warning("episodic_cache_persist_error", error=str(exc))

    def lookup(
        self,
        task_data: dict[str, list[dict[str, list[list[int]]]]],
    ) -> CachedSolution | None:
        """
        Looks up a cached solution by exact task hash or structural invariant signature.
        Re-verifies any matching candidate against current training pairs to guarantee 100% validity.
        """
        train_pairs = task_data.get("train", [])
        if not train_pairs:
            return None

        task_hash = compute_task_hash(train_pairs)

        # 1. Exact hash check
        if task_hash in self._exact_hash_index:
            candidate = self._exact_hash_index[task_hash]
            if self._verify_code_on_train(candidate.code, train_pairs):
                logger.info("episodic_cache_exact_hit", task_hash=task_hash, task_id=candidate.task_id)
                return candidate

        # 2. Structural invariant transfer check
        sig = compute_invariant_signature(train_pairs)
        if sig in self._signature_index:
            for candidate in self._signature_index[sig]:
                if self._verify_code_on_train(candidate.code, train_pairs):
                    logger.info("episodic_cache_invariant_transfer_hit", sig=sig, from_task=candidate.task_id)
                    return candidate

        return None

    @staticmethod
    def _verify_code_on_train(
        code: str, train_pairs: list[dict[str, list[list[int]]]]
    ) -> bool:
        """Safely verifies if code satisfies 100% of train pairs."""
        for pair in train_pairs:
            outcome = execute_unshackled_python(code, pair["input"], timeout_s=2.0)
            if not outcome.success or outcome.output_grid != pair["output"]:
                return False
        return True

    def store(
        self,
        task_id: str,
        task_data: dict[str, list[dict[str, list[list[int]]]]],
        code: str,
        method: str = "CEGIS_UNSHACKLED",
        turns_taken: int = 1,
    ) -> CachedSolution:
        """Stores a newly verified solution in the episodic cache."""
        train_pairs = task_data.get("train", [])
        task_hash = compute_task_hash(train_pairs)
        sig = compute_invariant_signature(train_pairs)

        from datetime import UTC, datetime

        sol = CachedSolution(
            task_id=task_id,
            task_hash=task_hash,
            invariant_signature=sig,
            code=code,
            method=method,
            turns_taken=turns_taken,
            verified_at=datetime.now(UTC).isoformat(),
            train_demonstrations_count=len(train_pairs),
        )

        self._exact_hash_index[task_hash] = sol
        self._signature_index.setdefault(sig, []).append(sol)
        self._persist()
        return sol

    def stats(self) -> dict[str, int]:
        """Returns summary statistics for the episodic cache."""
        return {
            "total_solutions": len(self._exact_hash_index),
            "unique_signatures": len(self._signature_index),
        }

    def clear(self) -> None:
        """Clears all in-memory entries and removes the cache file."""
        self._exact_hash_index.clear()
        self._signature_index.clear()
        if self.cache_file.exists():
            self.cache_file.unlink()
