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

from lucca.core.schemas import Provenance

if TYPE_CHECKING:
    from lucca.memory.db import DatabaseManager

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
        "explain",
        "for",
        "from",
        "how",
        "please",
        "tell",
        "that",
        "the",
        "this",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }
)


def _tokenize_query(text: str) -> list[str]:
    """Tokenizes text into lowercase tokens >= 3 chars, filtering common stop words."""
    if not text.strip():
        return []
    return [
        t.lower()
        for t in re.findall(r"\b[a-zA-Z0-9_\-.]+\b", text)
        if len(t) >= 3 and t.lower() not in USER_MODEL_STOP_WORDS
    ]


class UserModel:
    """
    Epistemic model of user knowledge state (Spec D-REAS-09, WO-21 Phase 4).

    Prevents repetitive re-explanation by tracking confirmed and told topics.
    Enforces Trap 1: Only admits signed ASSISTANT_UTTERANCE and USER_EXPLICIT/USER_DERIVED.
    """

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self.db = db
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

        If query is provided, ranks topics by token relevance to the query.
        Guarantees Trap 1: Only returns facts with allowed provenance.
        """
        candidates: list[tuple[str, int, float]] = []  # (content, match_score, ts)
        seen_contents: set[str] = set()

        query_tokens = _tokenize_query(query) if query else []

        # 1. Inspect in-memory records
        for rec in reversed(self._in_memory_records):
            content = str(rec.get("content", "")).strip()
            prov = str(rec.get("provenance", ""))
            ts = float(rec.get("created_at", 0.0) or 0.0)
            if not content or prov not in ALLOWED_USER_MODEL_PROVENANCES:
                continue

            normalized_key = content.lower()
            if normalized_key in seen_contents:
                continue

            match_score = (
                sum(1 for tok in query_tokens if tok in normalized_key)
                if query_tokens
                else 1
            )
            if not query_tokens or match_score > 0:
                seen_contents.add(normalized_key)
                candidates.append((content, match_score, ts))

        # 2. Query persistent store if DB available
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

                        match_score = (
                            sum(1 for tok in query_tokens if tok in normalized_key)
                            if query_tokens
                            else 1
                        )
                        if not query_tokens or match_score > 0:
                            seen_contents.add(normalized_key)
                            candidates.append((content, match_score, ts))
            except Exception as exc:  # noqa: BLE001
                logger.debug("user_model_db_lookup_error", error=str(exc))

        # Rank candidates: highest token match first, then most recent
        candidates.sort(key=lambda c: (c[1], c[2]), reverse=True)
        return [c[0] for c in candidates[:limit]]

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
