"""
Project Lucca — Belief Service
Spec §7, D-MEM-04, WP-2, WO-18b (F-ARCH-103)

Extracted from Orchestrator: handles belief contradiction evaluation,
reflection engine dispatch, and queued spoken update delivery.
"""

from __future__ import annotations

import json
import re
import time
from collections import deque
from typing import TYPE_CHECKING, Final

import structlog

from lucca.core.clock import SystemClock
from lucca.core.trace import TurnTrace
from lucca.ports import ClockPort

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator
    from lucca.memory.db import DatabaseManager
    from lucca.memory.reflection import ReflectionEngine

logger = structlog.get_logger(__name__)

# Interrogative openers: questions are requests for information, not belief
# candidates. Committing a question as an ASSISTANT_BELIEF produced nonsense
# spoken updates ("New understanding: Can you open Notepad?") — F-WO8-17.
_INTERROGATIVE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:who|what|when|where|why|how|which|whose|whom|can|could|should|"
    r"would|will|do|does|did|is|are|was|were|have|has|had|may|might|must|"
    r"tell\s+me|give\s+me|show\s+me|list|name)\b.*\?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# Stop-words excluded from contradiction FTS matching (fix: belief attractor bug).
# Without this filter, common words like "you/what/where/that" matched every
# utterance against high-importance beliefs that contained them, flooding the
# review_queue. Topical keywords must be at least 4 chars and not in this set.
# Bug discovered 2026-10-07: Belief #17 (user utterance committed as
# ASSISTANT_BELIEF, importance=0.9) generated 166 bogus review_queue items
# because FTS matched every conversation turn on stop-words alone.
_BELIEF_STOP_WORDS: Final[frozenset[str]] = frozenset({
    "that", "this", "they", "them", "then", "than", "there", "their", "these",
    "what", "when", "where", "with", "will", "would", "were", "which", "well",
    "your", "yeah", "just", "some", "have", "from", "here", "also", "into",
    "been", "more", "said", "says", "like", "know", "knows", "knew", "known",
    "time", "back", "mean", "means", "meant", "think", "thinks", "thought",
    "could", "about", "other", "over", "only", "very", "still", "after",
    "because", "should", "through", "being", "going", "doing", "does", "done",
    "asking", "asked", "asks", "saying", "looking", "looked", "looks",
    "working", "worked", "work", "works", "talking", "talked", "talks",
    "trying", "tried", "tries", "telling", "tells", "told", "getting",
    "want", "wants", "wanted", "need", "needs", "needed", "help", "helps",
    "make", "makes", "made", "take", "takes", "took", "taken",
    "give", "gives", "gave", "given", "show", "shows", "showed", "shown",
    "look", "come", "comes", "came", "okay", "right", "maybe", "really",
    "actually", "basically", "probably", "down", "much", "many", "good",
    "something", "anything", "everything", "nothing", "someone", "anyone",
    "sort", "kind", "type", "based", "using", "around", "under", "before",
})

# Minimum number of unique topical (non-stop) tokens required to trigger FTS
# belief contradiction search. Prevents single-word matches from flooding the
# review_queue when an utterance contains only common conversational words.
_MIN_TOPICAL_TOKENS: Final[int] = 2


class BeliefService:
    """Encapsulates belief contradiction detection and pending update speech (F-ARCH-103, WO-18b)."""

    def __init__(
        self,
        db: DatabaseManager | None,
        reflection_engine: ReflectionEngine | None,
        clock: ClockPort | None = None,
        orchestrator: Orchestrator | None = None,
    ) -> None:
        self.db = db
        self.reflection_engine = reflection_engine
        self.clock: ClockPort = clock or SystemClock()
        self._orchestrator = orchestrator
        self._local_pending_spoken_updates: deque[str] = deque()

    @property
    def pending_spoken_updates(self) -> deque[str]:
        if self._orchestrator is not None:
            if not hasattr(self._orchestrator, "pending_spoken_updates"):
                self._orchestrator.pending_spoken_updates = deque()
            return self._orchestrator.pending_spoken_updates
        return self._local_pending_spoken_updates

    @pending_spoken_updates.setter
    def pending_spoken_updates(self, val: deque[str]) -> None:
        if self._orchestrator is not None:
            self._orchestrator.pending_spoken_updates = val
        else:
            self._local_pending_spoken_updates = val

    def check_contradictions(self, new_entry_id: str, new_content: str, trace: TurnTrace) -> None:
        """
        Evaluates contradiction detection against active beliefs (Spec §7, D-MEM-04, WP-2).
        FTS matches candidate beliefs on topic tokens, capped at 5 beliefs with a 200 ms budget.
        """
        refl_engine = (
            getattr(self._orchestrator, "reflection_engine", None)
            if self._orchestrator is not None
            else self.reflection_engine
        )
        db = (
            getattr(self._orchestrator, "db", None)
            if self._orchestrator is not None
            else self.db
        )
        if refl_engine is None or db is None:
            return

        # Questions are not belief candidates: skip contradiction resolution so
        # no belief is committed from an interrogative utterance (F-WO8-17).
        if _INTERROGATIVE_PATTERN.match(new_content.strip()):
            return

        # Extract topical tokens: ≥4 chars, not stop-words, deduplicated.
        # The stop-word filter prevents common conversational words (you/what/where/that)
        # from triggering FTS matches against every active belief — the root cause of the
        # Belief #17 attractor bug (2026-10-07) that flooded review_queue with 166 items.
        all_tokens = re.findall(r"\b[a-zA-Z0-9_\-]{4,}\b", new_content.lower())
        tokens = list(dict.fromkeys(
            w for w in all_tokens if w not in _BELIEF_STOP_WORDS
        ))
        if len(tokens) < _MIN_TOPICAL_TOKENS:
            return

        candidate_beliefs: list[tuple[int, str, str, str | None]] = []
        try:
            with db.read_cursor() as cur:
                fts_query = " OR ".join(f'"{t}"' for t in tokens[:10])
                try:
                    cur.execute(
                        """
                        SELECT m.memory_id, m.content, m.kind, p.payload_json
                        FROM memories m
                        JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                        WHERE m.valid_to IS NULL
                          AND p.provenance = 'ASSISTANT_BELIEF'
                          AND m.memory_id IN (
                              SELECT rowid FROM fts_memories WHERE fts_memories MATCH ?
                          )
                        LIMIT 5
                        """,
                        (fts_query,),
                    )
                    candidate_beliefs = [
                        (int(r[0]), str(r[1]), str(r[2]), str(r[3]) if r[3] is not None else None)
                        for r in cur.fetchall()
                    ]
                except Exception as exc:  # noqa: BLE001
                    logger.debug("fts_match_failed_fallback_plain", error=str(exc))
                    cur.execute(
                        """
                        SELECT m.memory_id, m.content, m.kind, p.payload_json
                        FROM memories m
                        JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                        WHERE m.valid_to IS NULL AND p.provenance = 'ASSISTANT_BELIEF'
                        LIMIT 50
                        """
                    )
                    for r in cur.fetchall():
                        c_low = str(r[1]).lower()
                        if any(t in c_low for t in tokens):
                            candidate_beliefs.append(
                                (
                                    int(r[0]),
                                    str(r[1]),
                                    str(r[2]),
                                    str(r[3]) if r[3] is not None else None,
                                )
                            )
                            if len(candidate_beliefs) >= 5:
                                break
        except Exception as exc:  # noqa: BLE001
            logger.debug("contradiction_search_error", error=str(exc))
            return

        if not candidate_beliefs:
            return

        t_start = time.perf_counter()
        for belief_id, old_content, kind, payload_json in candidate_beliefs:
            if (time.perf_counter() - t_start) > 0.200:
                logger.warning("reflection_contradiction_budget_exceeded", trace_id=trace.trace_id)
                break

            candidate_topic: str = kind
            if payload_json:
                try:
                    pj = json.loads(payload_json)
                    struct = pj.get("structured")
                    if isinstance(struct, dict) and struct.get("topic"):
                        candidate_topic = str(struct["topic"])
                except Exception as exc:  # noqa: BLE001
                    logger.debug("candidate_topic_parse_failed", error=str(exc))

            is_conflict_top = self._evaluate_candidate_conflict(old_content, new_content)

            try:
                is_queued, res_str = refl_engine.detect_and_handle_contradiction(
                    old_belief_id=belief_id,
                    new_content=new_content,
                    reason_entry_id=new_entry_id,
                    proposed_confidence=1.0,
                    is_conflict_top=is_conflict_top,
                    topic=candidate_topic,
                    now=self.clock.now_utc(),
                )

                if is_queued:
                    logger.info(
                        "belief_revision_flagged_for_review",
                        review_id=res_str,
                        belief_id=belief_id,
                    )
                else:
                    self.pending_spoken_updates.append(res_str)
                    logger.info(
                        "belief_revision_enqueued_spoken_update",
                        spoken_update=res_str,
                        belief_id=belief_id,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("contradiction_handling_failed", error=str(exc), belief_id=belief_id)

    def _evaluate_candidate_conflict(self, old_content: str, new_content: str) -> bool:
        """Evaluates candidate belief contradiction signal (Belnap TOP conflict).

        In Belnap bilattice semantics:
        - Explicit user correction / negation of prior belief resolves as Belnap F, which
          enables clean autonomous supersession (Spec §7, D-MEM-04).
        - Mutually competing affirmative values without retraction (e.g. 100% vs 150%,
          port 8080 vs port 9000) represent true Belnap TOP conflict requiring review.
        """
        old_lower = old_content.lower()
        new_lower = new_content.lower()

        # Explicit user negation / retraction resolves to Belnap F (not TOP conflict)
        retraction_cues = [
            r"\b(?:don't|dont|do\s+not|not|never|no\s+longer|wrong|actually\s+live\s+in)\b",
        ]
        if any(re.search(cue, new_lower) for cue in retraction_cues):
            return False

        # Numeric attribute disagreement represents genuine Belnap TOP conflict
        old_nums = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", old_lower))
        new_nums = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", new_lower))
        if old_nums and new_nums and old_nums != new_nums:
            return True

        # Mutually exclusive affirmative values / states
        competing_pairs = [
            ("enabled", "disabled"),
            ("light mode", "dark mode"),
            ("dark mode", "light mode"),
        ]
        for v1, v2 in competing_pairs:
            if v1 in old_lower and v2 in new_lower:
                return True

        return False

    _check_contradictions = check_contradictions

    def maybe_speak_pending_updates(self, trace: TurnTrace) -> None:
        """Processes queued unflagged belief revision sentences without speaking them aloud (WO-26 Phase 1).

        Maintains the interiority barrier: logs the revision to structured audit telemetry
        and publishes a system caption, but strictly quarantines it from conversational TTS and history.
        """
        while self.pending_spoken_updates:
            spoken_update = self.pending_spoken_updates.popleft()
            if spoken_update.strip():
                logger.info(
                    "belief_revision_applied",
                    spoken_update=spoken_update,
                    trace_id=trace.trace_id if trace else None,
                )
                print(f"[Lucca Revision] 💡 {spoken_update}", flush=True)
                if self._orchestrator is not None and hasattr(self._orchestrator, "_publish_caption"):
                    self._orchestrator._publish_caption(spoken_update, source="system", is_final=True)

    _maybe_speak_pending_updates = maybe_speak_pending_updates
