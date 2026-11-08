"""
Project Lucca — Episodic Solution & Code Cache (Case-Based Reasoning 4 Rs)
v1.44.0 Deterministic Lifelong Reasoning Memory (Pillar 3) & WO-39 CBR Engine

Implements Aamodt & Plaza's (1994) 4 Rs of Case-Based Reasoning:
1. Retrieve (`retrieve_precedent`, `find_similar`, `lookup`)
2. Reuse (`adapt_and_reuse`)
3. Revise (`revise_solution`, `record_reuse_outcome`)
4. Retain (`retain_episode`, `store_episode`, `store`)

Tracks NARS-style (w+, w-) evidential weights (`positive_evidence`, `negative_evidence`)
for each cached episode.
Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import structlog

from lucca.reasoning.cegis_unshackled import execute_unshackled_python

logger = structlog.get_logger(__name__)

DEFAULT_CACHE_PATH: Final[Path] = Path("data/episodic_solutions.json")

_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on",
        "at", "for", "with", "by", "from", "that", "this", "it", "be", "as",
        "or", "and", "please", "can", "you", "compute", "calculate", "find",
        "what", "how", "write", "python", "code", "script",
    }
)


def _tokenize_goal(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower()))
    return tokens - _STOP_WORDS


@dataclass(frozen=True)
class CachedSolution:
    """Record of a verified program stored in the episodic cache with (w+, w-) evidence."""

    task_id: str
    task_hash: str
    invariant_signature: str
    code: str
    method: str = "CEGIS"
    turns_taken: int = 1
    verified_at: str = ""
    train_demonstrations_count: int = 0
    query: str = ""
    output: str = ""
    positive_evidence: int = 1
    negative_evidence: int = 0
    reuse_count: int = 0

    @property
    def nars_frequency(self) -> float:
        """NARS frequency f = w+ / (w+ + w-)."""
        total = self.positive_evidence + self.negative_evidence
        if total <= 0:
            return 0.5
        return float(self.positive_evidence) / float(total)

    @property
    def nars_confidence(self) -> float:
        """NARS confidence c = (w+ + w-) / (w+ + w- + k) with k = 1.0."""
        total = self.positive_evidence + self.negative_evidence
        if total <= 0:
            return 0.0
        return float(total) / float(total + 1.0)

    @property
    def nars_expectation(self) -> float:
        """NARS expected truth value E = c * (f - 0.5) + 0.5."""
        return self.nars_confidence * (self.nars_frequency - 0.5) + 0.5


CodeEpisode = CachedSolution


def compute_task_hash(train_pairs: list[dict[str, list[list[int]]]]) -> str:
    """Computes a deterministic SHA-256 hash of training input/output matrices."""
    serialized = json.dumps(train_pairs, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def compute_goal_hash(goal: str) -> str:
    """Computes a deterministic SHA-256 hash of a normalized text goal."""
    norm = " ".join(goal.strip().lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


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

        if (h_in, w_in) == (h_out, w_out):
            shape_deltas.append("preserve")
        elif h_out == 1 and w_out > 1:
            shape_deltas.append(f"tally_1x{w_out}")
        elif h_out > 1 and w_out == 1:
            shape_deltas.append(f"tally_{h_out}x1")
        else:
            shape_deltas.append(f"{h_in}x{w_in}->{h_out}x{w_out}")

        colors_in = {c for row in g_in for c in row}
        colors_out = {c for row in g_out for c in row}
        if colors_out.issubset(colors_in):
            palette_invariants.append("subset")
        else:
            palette_invariants.append(f"+{len(colors_out - colors_in)}")

    sig = f"shapes:{','.join(shape_deltas[:3])}|pal:{','.join(palette_invariants[:3])}"
    return sig


def compute_goal_signature(goal: str) -> str:
    """Computes a structural signature for a natural-language or symbolic goal."""
    tokens = sorted(_tokenize_goal(goal))
    has_nums = bool(re.search(r"\b\d+\b", goal))
    return f"goal_tokens:{','.join(tokens[:8])}|nums:{int(has_nums)}"


class EpisodicSolutionCache:
    """
    Persistent episodic memory store and Case-Based Reasoning (4 Rs) engine
    for verified neurosymbolic code solutions.
    """

    def __init__(
        self,
        cache_file: Path = DEFAULT_CACHE_PATH,
        db: object | None = None,
    ) -> None:
        self.cache_file = cache_file
        self.db = db
        self._exact_hash_index: dict[str, CachedSolution] = {}
        self._signature_index: dict[str, list[CachedSolution]] = {}
        self._ensure_db_table()
        self._load()

    def _ensure_db_table(self) -> None:
        if self.db is None or not hasattr(self.db, "write_transaction"):
            return
        try:
            with self.db.write_transaction() as cur:  # type: ignore[attr-defined]
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS episodic_code_cache (
                        task_hash TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        invariant_signature TEXT NOT NULL,
                        query TEXT NOT NULL DEFAULT '',
                        code TEXT NOT NULL,
                        output TEXT NOT NULL DEFAULT '',
                        method TEXT NOT NULL DEFAULT 'CBR',
                        turns_taken INTEGER NOT NULL DEFAULT 1,
                        verified_at TEXT NOT NULL,
                        train_demonstrations_count INTEGER NOT NULL DEFAULT 0,
                        positive_evidence INTEGER NOT NULL DEFAULT 1,
                        negative_evidence INTEGER NOT NULL DEFAULT 0,
                        reuse_count INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("episodic_code_cache_table_init_error", error=str(exc))

    def _index_solution(self, sol: CachedSolution) -> None:
        if sol.task_hash:
            self._exact_hash_index[sol.task_hash] = sol
        if sol.invariant_signature:
            bucket = self._signature_index.setdefault(sol.invariant_signature, [])
            bucket[:] = [existing for existing in bucket if existing.task_hash != sol.task_hash]
            bucket.append(sol)

    def _load(self) -> None:
        """Loads cached solutions from disk and optional SQLite table into memory indexes."""
        if self.cache_file.exists():
            try:
                raw_text = self.cache_file.read_text(encoding="utf-8")
                data = json.loads(raw_text)
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        sol = CachedSolution(
                            task_id=str(item.get("task_id", "")),
                            task_hash=str(item.get("task_hash", "")),
                            invariant_signature=str(item.get("invariant_signature", "")),
                            code=str(item.get("code", "")),
                            method=str(item.get("method", "CEGIS")),
                            turns_taken=int(item.get("turns_taken", 1)),
                            verified_at=str(item.get("verified_at", "")),
                            train_demonstrations_count=int(
                                item.get("train_demonstrations_count", 0)
                            ),
                            query=str(item.get("query", "")),
                            output=str(item.get("output", "")),
                            positive_evidence=int(item.get("positive_evidence", 1)),
                            negative_evidence=int(item.get("negative_evidence", 0)),
                            reuse_count=int(item.get("reuse_count", 0)),
                        )
                        self._index_solution(sol)
                logger.info("episodic_cache_loaded", entries=len(self._exact_hash_index))
            except Exception as exc:  # noqa: BLE001
                logger.warning("episodic_cache_load_error", error=str(exc))

        if self.db is not None and hasattr(self.db, "read_cursor"):
            try:
                with self.db.read_cursor() as cur:  # type: ignore[attr-defined]
                    cur.execute(
                        """
                        SELECT task_hash, task_id, invariant_signature, query, code, output,
                               method, turns_taken, verified_at, train_demonstrations_count,
                               positive_evidence, negative_evidence, reuse_count
                        FROM episodic_code_cache
                        """
                    )
                    for row in cur.fetchall():
                        sol = CachedSolution(
                            task_hash=str(row[0]),
                            task_id=str(row[1]),
                            invariant_signature=str(row[2]),
                            query=str(row[3]),
                            code=str(row[4]),
                            output=str(row[5]),
                            method=str(row[6]),
                            turns_taken=int(row[7]),
                            verified_at=str(row[8]),
                            train_demonstrations_count=int(row[9]),
                            positive_evidence=int(row[10]),
                            negative_evidence=int(row[11]),
                            reuse_count=int(row[12]),
                        )
                        self._index_solution(sol)
            except Exception as exc:  # noqa: BLE001
                logger.debug("episodic_cache_db_load_error", error=str(exc))

    def _persist(self, changed: CachedSolution | None = None) -> None:
        """Saves current cache entries to disk atomically and syncs to SQLite if attached."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            entries = [asdict(sol) for sol in self._exact_hash_index.values()]
            temp_file = self.cache_file.with_suffix(".tmp")
            temp_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")
            temp_file.replace(self.cache_file)
            logger.info("episodic_cache_persisted", total_entries=len(entries))
        except Exception as exc:  # noqa: BLE001
            logger.warning("episodic_cache_persist_error", error=str(exc))

        if changed is not None and self.db is not None and hasattr(self.db, "write_transaction"):
            try:
                with self.db.write_transaction() as cur:  # type: ignore[attr-defined]
                    cur.execute(
                        """
                        INSERT INTO episodic_code_cache (
                            task_hash, task_id, invariant_signature, query, code, output,
                            method, turns_taken, verified_at, train_demonstrations_count,
                            positive_evidence, negative_evidence, reuse_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(task_hash) DO UPDATE SET
                            code = excluded.code,
                            output = excluded.output,
                            verified_at = excluded.verified_at,
                            positive_evidence = excluded.positive_evidence,
                            negative_evidence = excluded.negative_evidence,
                            reuse_count = excluded.reuse_count
                        """,
                        (
                            changed.task_hash,
                            changed.task_id,
                            changed.invariant_signature,
                            changed.query,
                            changed.code,
                            changed.output,
                            changed.method,
                            changed.turns_taken,
                            changed.verified_at,
                            changed.train_demonstrations_count,
                            changed.positive_evidence,
                            changed.negative_evidence,
                            changed.reuse_count,
                        ),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("episodic_cache_db_persist_error", error=str(exc))

    # =========================================================================
    # CBR Step 1: RETRIEVE
    # =========================================================================

    def lookup(
        self,
        task_data: dict[str, list[dict[str, list[list[int]]]]],
    ) -> CachedSolution | None:
        """
        Looks up a cached solution by exact task hash or structural invariant signature.
        Re-verifies any matching candidate against current training pairs to guarantee 100%
        validity.
        """
        train_pairs = task_data.get("train", [])
        if not train_pairs:
            return None

        task_hash = compute_task_hash(train_pairs)

        # 1. Exact hash check
        if task_hash in self._exact_hash_index:
            candidate = self._exact_hash_index[task_hash]
            if candidate.nars_frequency >= 0.3 and self._verify_code_on_train(
                candidate.code, train_pairs
            ):
                self.record_reuse_outcome(candidate.task_hash, success=True)
                logger.info(
                    "episodic_cache_exact_hit", task_hash=task_hash, task_id=candidate.task_id
                )
                return self._exact_hash_index[task_hash]

        # 2. Structural invariant transfer check
        sig = compute_invariant_signature(train_pairs)
        if sig in self._signature_index:
            ranked = sorted(
                self._signature_index[sig],
                key=lambda s: s.nars_expectation,
                reverse=True,
            )
            for candidate in ranked:
                if candidate.nars_frequency < 0.25:
                    continue
                if self._verify_code_on_train(candidate.code, train_pairs):
                    self.record_reuse_outcome(candidate.task_hash, success=True)
                    logger.info(
                        "episodic_cache_invariant_transfer_hit",
                        sig=sig,
                        from_task=candidate.task_id,
                    )
                    return self._exact_hash_index.get(candidate.task_hash, candidate)

        return None

    def find_similar(
        self,
        query: str,
        top_k: int = 3,
        min_similarity: float = 0.25,
    ) -> list[CachedSolution]:
        """
        Retrieves top-k structurally/lexically similar code precedents weighted by NARS expectation.
        """
        if not query.strip():
            return []

        g_hash = compute_goal_hash(query)
        if g_hash in self._exact_hash_index:
            exact = self._exact_hash_index[g_hash]
            if exact.nars_frequency >= 0.3:
                return [exact]

        q_tokens = _tokenize_goal(query)
        if not q_tokens:
            return []

        scored: list[tuple[float, CachedSolution]] = []
        for sol in self._exact_hash_index.values():
            if sol.nars_frequency < 0.25:
                continue
            cand_text = sol.query if sol.query.strip() else sol.task_id
            c_tokens = _tokenize_goal(cand_text)
            if not c_tokens:
                continue
            inter = len(q_tokens & c_tokens)
            union = len(q_tokens | c_tokens)
            jaccard = float(inter) / float(union) if union > 0 else 0.0
            if jaccard >= min_similarity:
                combined_score = jaccard * sol.nars_expectation
                scored.append((combined_score, sol))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [sol for _, sol in scored[:top_k]]

    def retrieve_precedent(
        self,
        query: str = "",
        task_data: dict[str, list[dict[str, list[list[int]]]]] | None = None,
        min_similarity: float = 0.35,
    ) -> CachedSolution | None:
        """CBR Retrieve step: finds the highest-expectation matching precedent."""
        if task_data is not None:
            hit = self.lookup(task_data)
            if hit is not None:
                return hit
        if query.strip():
            similar = self.find_similar(query, top_k=1, min_similarity=min_similarity)
            if similar:
                return similar[0]
        return None

    # =========================================================================
    # CBR Step 2: REUSE (Adaptation)
    # =========================================================================

    def adapt_and_reuse(
        self,
        precedent: CachedSolution,
        current_goal: str,
        parameters: dict[str, str | int | float] | None = None,
    ) -> str:
        """
        CBR Reuse step: adapts a retrieved precedent's code to the current goal
        by substituting parameter bindings or numeric literals while preserving AST validity.
        """
        adapted = precedent.code
        if not adapted.strip():
            return adapted

        # 1. Explicit parameter substitution if provided
        if parameters:
            for k, v in parameters.items():
                pattern = re.compile(rf"\b{re.escape(k)}\s*=\s*[^#\n]+")
                replacement = f"{k} = {repr(v)}"
                candidate = pattern.sub(replacement, adapted, count=1)
                if self._is_valid_syntax(candidate):
                    adapted = candidate

        # 2. Structural numeric literal alignment between precedent.query and current_goal
        if precedent.query and current_goal and precedent.query.strip() != current_goal.strip():
            old_nums = re.findall(r"(?<![a-zA-Z0-9_])-?\d+(?:\.\d+)?(?![a-"
                r"zA-Z0-9_])", precedent.query)
            new_nums = re.findall(r"(?<![a-zA-Z0-9_])-?\d+(?:\.\d+)?(?![a-zA-Z0-9_])", current_goal)
            if old_nums and len(old_nums) == len(new_nums) and old_nums != new_nums:
                candidate = adapted
                for o_val, n_val in zip(old_nums, new_nums, strict=False):
                    if o_val != n_val:
                        candidate = re.sub(
                            rf"(?<![a-zA-Z0-9_.]){re.escape(o_val)}(?![a-zA-Z0-9_.])",
                            n_val,
                            candidate,
                            count=1,
                        )
                if self._is_valid_syntax(candidate):
                    adapted = candidate

        return adapted

    @staticmethod
    def _is_valid_syntax(code: str) -> bool:
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    # =========================================================================
    # CBR Step 3: REVISE (Verification & Evidential Feedback)
    # =========================================================================

    def revise_solution(
        self,
        adapted_code: str,
        precedent: CachedSolution | None = None,
        verifier_fn: Callable[[str], tuple[bool, str]] | None = None,
        train_pairs: list[dict[str, list[list[int]]]] | None = None,
    ) -> tuple[bool, str]:
        """
        CBR Revise step: verifies the adapted candidate solution via AST check,
        training pairs, or sandbox verifier callback, and updates (w+, w-) evidence.
        """
        if not self._is_valid_syntax(adapted_code):
            if precedent is not None:
                self.record_reuse_outcome(precedent.task_hash or precedent.task_id, success=False)
            return False, "SyntaxError in adapted candidate"

        if train_pairs is not None:
            ok = self._verify_code_on_train(adapted_code, train_pairs)
            if precedent is not None:
                self.record_reuse_outcome(precedent.task_hash or precedent.task_id, success=ok)
            return ok, "Verified on train pairs" if ok else "Failed train pair verification"

        if verifier_fn is not None:
            ok, detail = verifier_fn(adapted_code)
            if precedent is not None:
                self.record_reuse_outcome(precedent.task_hash or precedent.task_id, success=ok)
            return ok, detail

        if precedent is not None:
            self.record_reuse_outcome(precedent.task_hash or precedent.task_id, success=True)
        return True, "Syntax valid"

    def record_reuse_outcome(self, key: str, success: bool) -> CachedSolution | None:
        """Updates positive_evidence (w+) or negative_evidence (w-) for a cached episode."""
        target = self._exact_hash_index.get(key)
        if target is None:
            for sol in self._exact_hash_index.values():
                if sol.task_id == key or (sol.query and sol.query == key):
                    target = sol
                    break
        if target is None:
            return None

        updated = replace(
            target,
            positive_evidence=target.positive_evidence + (1 if success else 0),
            negative_evidence=target.negative_evidence + (0 if success else 1),
            reuse_count=target.reuse_count + 1,
        )
        self._index_solution(updated)
        self._persist(changed=updated)
        return updated

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

    # =========================================================================
    # CBR Step 4: RETAIN
    # =========================================================================

    def retain_episode(
        self,
        query: str,
        code: str,
        output: str = "",
        task_id: str = "",
        method: str = "CBR_RETAIN",
        turns_taken: int = 1,
        train_pairs: list[dict[str, list[list[int]]]] | None = None,
    ) -> CachedSolution:
        """CBR Retain step: stores a verified episode in the episodic code cache."""
        if train_pairs:
            t_hash = compute_task_hash(train_pairs)
            sig = compute_invariant_signature(train_pairs)
            demos = len(train_pairs)
        else:
            t_hash = compute_goal_hash(query or code)
            sig = compute_goal_signature(query or code)
            demos = 1

        existing = self._exact_hash_index.get(t_hash)
        pos_ev = (existing.positive_evidence + 1) if existing is not None else 1
        neg_ev = existing.negative_evidence if existing is not None else 0
        reuses = existing.reuse_count if existing is not None else 0

        sol = CachedSolution(
            task_id=task_id or f"ep-{t_hash[:8]}",
            task_hash=t_hash,
            invariant_signature=sig,
            code=code,
            method=method,
            turns_taken=turns_taken,
            verified_at=datetime.now(UTC).isoformat(),
            train_demonstrations_count=demos,
            query=query,
            output=output,
            positive_evidence=pos_ev,
            negative_evidence=neg_ev,
            reuse_count=reuses,
        )
        self._index_solution(sol)
        self._persist(changed=sol)
        return sol

    store_episode = retain_episode

    def store(
        self,
        task_id: str,
        task_data: dict[str, list[dict[str, list[list[int]]]]],
        code: str,
        method: str = "CEGIS_UNSHACKLED",
        turns_taken: int = 1,
        query: str = "",
        output: str = "",
    ) -> CachedSolution:
        """Stores a newly verified solution in the episodic cache."""
        train_pairs = task_data.get("train", [])
        return self.retain_episode(
            query=query or task_id,
            code=code,
            output=output,
            task_id=task_id,
            method=method,
            turns_taken=turns_taken,
            train_pairs=train_pairs,
        )

    def get_all_episodes(self) -> list[CachedSolution]:
        """Returns all cached episodes."""
        return list(self._exact_hash_index.values())

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


EpisodicCodeCache = EpisodicSolutionCache
