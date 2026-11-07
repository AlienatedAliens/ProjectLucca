"""
Project Lucca — Theory of Mind User Model
WO-21 Phase 4 (Spec D-REAS-09 / Spec 10)

Tracks what the user already knows from:
1. What the user has been told (from ASSISTANT_UTTERANCE)
2. What the user has explicitly stated or confirmed (USER_EXPLICIT, USER_DERIVED)

Exposed to prompt builder as a directive:
"The user already knows: X, Y — do not re-explain unless asked."

TRAP 1 INVARIANT:
The user model is built ONLY from signed records (ASSISTANT_UTTERANCE, USER_EXPLICIT,
USER_DERIVED) — NEVER from LLM narration beliefs (ASSISTANT_BELIEF, LLM_NARRATION).
Zero-Any invariant enforced.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Final

import structlog

from lucca.core.schemas import Provenance, VerifierLabel

if TYPE_CHECKING:
    from lucca.memory.db import DatabaseManager
    from lucca.ports import EmbeddingPort
    from lucca.senses.verifier import VerifierWorker

logger = structlog.get_logger(__name__)

ALLOWED_USER_MODEL_PROVENANCES: Final[frozenset[str]] = frozenset(
    {
        str(Provenance.ASSISTANT_UTTERANCE),
        str(Provenance.USER_EXPLICIT),
        str(Provenance.USER_DERIVED),
    }
)

DISALLOWED_USER_MODEL_PROVENANCES: Final[frozenset[str]] = frozenset(
    {
        str(Provenance.ASSISTANT_BELIEF),
        str(Provenance.LLM_NARRATION),
    }
)

USER_MODEL_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "about",
        "also",
        "and",
        "are",
        "can",
        "could",
        "did",
        "does",
        "doing",
        "explain",
        "fast",
        "fine",
        "for",
        "from",
        "good",
        "great",
        "had",
        "has",
        "have",
        "hello",
        "hey",
        "how",
        "just",
        "luka",
        "lukas",
        "lucca",
        "please",
        "responses",
        "some",
        "speech",
        "tell",
        "testing",
        "thank",
        "thanks",
        "that",
        "the",
        "there",
        "this",
        "today",
        "very",
        "was",
        "well",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "yeah",
        "yes",
        "you",
        "your",
    }
)

MAX_USER_MODEL_NLI_CANDIDATES: Final[int] = 8


def _tokenize_query(text: str) -> list[str]:
    """Tokenizes text into lowercase tokens >= 3 chars, filtering common stop words."""
    if not text.strip():
        return []
    return [
        t.lower()
        for t in re.findall(r"\b[a-zA-Z0-9_\-.]+\b", text)
        if len(t) >= 3 and t.lower() not in USER_MODEL_STOP_WORDS
    ]


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if len(vec_a) != len(vec_b) or not vec_a:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a <= 1e-9 or norm_b <= 1e-9:
        return 0.0
    return float(dot / (norm_a * norm_b))


class UserModel:
    """
    Epistemic model of user knowledge state (Spec D-REAS-09, WO-21 Phase 4, WO-36 Milestone 36.2).

    Prevents repetitive re-explanation by tracking confirmed and told topics.
    Enforces Trap 1: Only admits signed ASSISTANT_UTTERANCE and USER_EXPLICIT/USER_DERIVED.
    Uses OpenVINO NLI entailment boosting, contradiction rejection, and 384-D cosine fallback.
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        embedder: EmbeddingPort | None = None,
        verifier: VerifierWorker | None = None,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.verifier = verifier
        self._in_memory_records: list[dict[str, object]] = []

    def record_topic(
        self,
        content: str,
        provenance: Provenance | str,
        created_at: float | None = None,
    ) -> None:
        """
        Records a topic known to the user.

        Raises ValueError on Trap 1 violation (attempting to record LLM narration beliefs).
        """
        prov_str = str(provenance).strip()
        if prov_str in DISALLOWED_USER_MODEL_PROVENANCES:
            raise ValueError(
                f"Trap 1 violation: UserModel cannot record LLM narration belief '{prov_str}'"
            )
        if prov_str not in ALLOWED_USER_MODEL_PROVENANCES:
            raise ValueError(
                f"UserModel only admits signed records {sorted(ALLOWED_USER_MODEL_PROVENANCES)}, "
                f"got '{prov_str}'"
            )

        clean_topic = content.strip()
        if not clean_topic:
            return

        ts = created_at if created_at is not None else time.time()
        self._in_memory_records.append(
            {
                "content": clean_topic,
                "provenance": prov_str,
                "created_at": ts,
            }
        )

    def known_topics(self, query: str | None = None, limit: int = 5) -> list[str]:
        """
        Returns relevant topics the user already knows.

        Ranks topics using:
        1. OpenVINO NLI entailment boosting (threshold > 0.60) & contradiction rejection.
        2. 384-D dense embedding cosine similarity (if embedder available).
        3. Token overlap fallback (if embedder/verifier unavailable).
        Guarantees Trap 1: Only returns facts with allowed provenance.
        """
        seen_contents: set[str] = set()
        raw_candidates: list[tuple[str, float]] = []

        # 1. Collect in-memory records
        for rec in reversed(self._in_memory_records):
            content = str(rec.get("content", "")).strip()
            prov = str(rec.get("provenance", ""))
            ts = float(rec.get("created_at", 0.0) or 0.0)
            if not content or prov not in ALLOWED_USER_MODEL_PROVENANCES:
                continue

            normalized_key = content.lower()
            if normalized_key in seen_contents:
                continue

            seen_contents.add(normalized_key)
            raw_candidates.append((content, ts))

        # 2. Collect persistent store records if DB available
        if self.db is not None and hasattr(self.db, "read_cursor"):
            try:
                with self.db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.content, e.provenance, e.created_at
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.provenance IN (
                            'ASSISTANT_UTTERANCE', 'USER_EXPLICIT', 'USER_DERIVED'
                        )
                        ORDER BY e.created_at DESC
                        LIMIT 100
                        """
                    )
                    for content_raw, prov_raw, ts_raw in cur.fetchall():
                        content = str(content_raw or "").strip()
                        prov = str(prov_raw or "").strip()
                        ts = float(ts_raw or 0.0)

                        if not content or prov not in ALLOWED_USER_MODEL_PROVENANCES:
                            continue

                        normalized_key = content.lower()
                        if normalized_key in seen_contents:
                            continue

                        seen_contents.add(normalized_key)
                        raw_candidates.append((content, ts))
            except Exception as exc:  # noqa: BLE001
                logger.debug("user_model_db_lookup_error", error=str(exc))

        if not raw_candidates:
            return []

        if not query or not query.strip():
            raw_candidates.sort(key=lambda c: c[1], reverse=True)
            return [c[0] for c in raw_candidates[:limit]]

        query_clean = query.strip()
        query_tokens = _tokenize_query(query_clean)

        if not query_tokens and self.embedder is None:
            return []

        # Baseline scoring via dense embeddings if available
        dense_scores: dict[str, float] = {}
        if self.embedder is not None:
            try:
                cand_texts = [c[0] for c in raw_candidates]
                all_vecs = self.embedder.embed([query_clean, *cand_texts])
                if all_vecs and len(all_vecs) == len(raw_candidates) + 1:
                    q_vec = all_vecs[0]
                    for (c_text, _), vec in zip(raw_candidates, all_vecs[1:]):
                        sim = _cosine_similarity(q_vec, vec)
                        dense_scores[c_text.lower()] = sim
            except Exception as exc:  # noqa: BLE001
                logger.debug("user_model_dense_embed_error", error=str(exc))

        pre_scored: list[tuple[str, float, float]] = []
        for content, ts in raw_candidates:
            normalized_key = content.lower()
            if normalized_key in dense_scores:
                base_score = dense_scores[normalized_key]
            else:
                overlap = (
                    sum(1 for tok in query_tokens if tok in normalized_key)
                    if query_tokens
                    else 0
                )
                base_score = (
                    float(overlap) / max(1.0, float(len(query_tokens)))
                    if query_tokens
                    else 0.0
                )
            if base_score > 0.0 or len(raw_candidates) <= 5:
                pre_scored.append((content, base_score, ts))

        pre_scored.sort(key=lambda c: (c[1], c[2]), reverse=True)

        scored_candidates: list[tuple[str, float, float]] = []  # (content, score, ts)
        nli_calls = 0
        for content, base_score, ts in pre_scored:
            final_score = base_score

            # OpenVINO NLI Entailment / Contradiction verification (bounded to top candidates)
            if self.verifier is not None and nli_calls < MAX_USER_MODEL_NLI_CANDIDATES:
                nli_calls += 1
                try:
                    res = self.verifier.check_consistency(
                        premise=content,
                        hypothesis=query_clean,
                    )
                    is_contradiction = (
                        res.label == VerifierLabel.CONTRADICTION
                        or getattr(res, "contradiction_prob", 0.0) > 0.60
                    )
                    if is_contradiction:
                        logger.debug(
                            "user_model_nli_contradiction_rejected",
                            candidate=content,
                            query=query_clean,
                        )
                        continue  # Reject candidate

                    is_entailment = (
                        not getattr(res, "degraded", False)
                        and (
                            res.label == VerifierLabel.ENTAILMENT
                            or getattr(res, "entailment_prob", 0.0) > 0.60
                        )
                    )
                    if is_entailment:
                        boost = 2.0 + float(getattr(res, "entailment_prob", 0.8))
                        final_score += boost
                    elif getattr(res, "degraded", False) or res.label == VerifierLabel.UNCERTAIN:
                        final_score *= 0.65
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "user_model_verifier_eval_error",
                        candidate=content,
                        error=str(exc),
                    )

            if final_score > 0.0:
                scored_candidates.append((content, final_score, ts))

        scored_candidates.sort(key=lambda c: (c[1], c[2]), reverse=True)
        return [c[0] for c in scored_candidates[:limit]]

    def format_directive(self, query: str | None = None, limit: int = 5) -> str | None:
        """
        Formats the user model directive for prompt context injection.

        Example:
        'The user already knows: Python 3.13 has nogil, Seattle weather is rainy —
        do not re-explain unless asked.'
        """
        topics = self.known_topics(query, limit=limit)
        if not topics:
            return None

        # Clean topics: remove leading/trailing punctuation and quotes
        cleaned_topics: list[str] = []
        for t in topics:
            c = t.strip().rstrip(".!?")
            if c:
                cleaned_topics.append(c)

        if not cleaned_topics:
            return None

        topics_str = ", ".join(cleaned_topics)
        return f"The user already knows: {topics_str} — do not re-explain unless asked."
