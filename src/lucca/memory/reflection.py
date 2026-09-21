"""
Project Lucca — Autobiographical Reflection, Belief Revision & Review Queue
Spec D-MEM-04, Rung A1, ModularRSI §4.3
"""

import datetime
import time
import uuid

import structlog

from lucca.core.exceptions import ProvenanceRejected
from lucca.core.schemas import (
    Provenance,
    UnsignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import AssistantUtteranceSigner
from lucca.memory.store import MemoryStore

logger = structlog.get_logger(__name__)

THIRTY_DAYS_SECONDS = 30.0 * 86400.0


class ReflectionEngine:
    """
    Manages autobiographical belief revision, evidence-gated supersession,
    review queue gating (5 flags), and nightly importance-weighted roll-up.
    """

    def __init__(
        self,
        db: DatabaseManager,
        store: MemoryStore,
        master_key: bytes,
    ) -> None:
        self.db = db
        self.store = store
        self.master_key = master_key
        self.signer = AssistantUtteranceSigner(master_key=master_key)

    def is_topic_review_required(self, topic: str) -> bool:
        """Checks if a normalized topic has been marked review-required by operator."""
        clean_topic = topic.strip().lower()
        with self.db.read_cursor() as cur:
            cur.execute(
                "SELECT 1 FROM review_required_topics WHERE lower(topic) = ? LIMIT 1",
                (clean_topic,),
            )
            return cur.fetchone() is not None

    def mark_topic_review_required(self, topic: str, now: float | None = None) -> None:
        """Marks a topic as requiring explicit operator review before belief updates."""
        clean_topic = topic.strip().lower()
        current_time = now if now is not None else time.time()
        conn = self.db.get_writer()
        conn.execute(
            "INSERT OR IGNORE INTO review_required_topics(topic, created_at) VALUES (?, ?)",
            (clean_topic, current_time),
        )

    def unmark_topic_review_required(self, topic: str) -> None:
        """Removes a topic from the review-required list."""
        clean_topic = topic.strip().lower()
        conn = self.db.get_writer()
        conn.execute(
            "DELETE FROM review_required_topics WHERE lower(topic) = ?",
            (clean_topic,),
        )

    def list_review_required_topics(self) -> list[str]:
        """Lists all topics marked as review-required."""
        with self.db.read_cursor() as cur:
            cur.execute("SELECT topic FROM review_required_topics ORDER BY topic ASC")
            return [str(row[0]) for row in cur.fetchall()]

    async def detect_and_handle_contradiction(
        self,
        old_belief_id: int,
        new_content: str,
        reason_entry_id: str,
        proposed_confidence: float = 1.0,
        is_conflict_top: bool = False,
        topic: str | None = None,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """
        Evaluates belief contradiction against evidence reason.
        Autonomous revision if no review flags apply; otherwise queues into review_queue.

        Returns:
            (is_queued, identifier_or_spoken_update)
        """
        current_time = now if now is not None else time.time()

        # Evidence reason MUST be grounding-eligible (Invariant ADR-006 / D-MEM-04)
        with self.db.read_cursor() as cur:
            cur.execute(
                "SELECT grounding_eligible FROM provenance_envelopes WHERE entry_id = ?",
                (reason_entry_id,),
            )
            env_row = cur.fetchone()
            if not env_row or env_row[0] != 1:
                raise ProvenanceRejected(
                    f"Contradiction reason '{reason_entry_id}' is not a grounding-eligible entry_id"
                )

            # Fetch active old belief record
            cur.execute(
                "SELECT memory_id, content, kind, importance, created_at, valid_from, valid_to "
                "FROM memories WHERE memory_id = ?",
                (old_belief_id,),
            )
            belief_row = cur.fetchone()
            if not belief_row:
                raise KeyError(f"Belief #{old_belief_id} not found")
            if belief_row[6] is not None:
                raise ValueError(f"Belief #{old_belief_id} has already been superseded")

        old_content = str(belief_row[1])
        kind = str(belief_row[2])
        importance = float(belief_row[3])
        created_at = float(belief_row[4])
        valid_from = float(belief_row[5])

        # Evaluate the 5 review flags (Spec §7 Decision 4):
        # 1. Belief is about the user (kind="user_model")
        flag_user_model = kind == "user_model"

        # 2. importance >= 0.7
        flag_high_importance = importance >= 0.7

        # 3. Contradiction resolves to Belnap B (conflict / TOP) rather than F
        flag_conflict_top = is_conflict_top

        # 4. Oscillation guard: belief already revised within last 30 days
        age_since_revision = current_time - valid_from
        flag_oscillation = age_since_revision < THIRTY_DAYS_SECONDS and valid_from > created_at

        # 5. Topic marked review-required
        effective_topic = topic or kind
        flag_topic_required = self.is_topic_review_required(effective_topic)

        reasons: list[str] = []
        if flag_user_model:
            reasons.append("kind_user_model")
        if flag_high_importance:
            reasons.append(f"high_importance_{importance:.2f}")
        if flag_conflict_top:
            reasons.append("belnap_conflict_top")
        if flag_oscillation:
            reasons.append(f"oscillation_guard_{age_since_revision:.0f}s")
        if flag_topic_required:
            reasons.append(f"topic_review_required_{effective_topic}")

        if reasons:
            # Enqueue in review_queue
            review_id = f"rev-{uuid.uuid4().hex[:12]}"
            trigger_reason = "; ".join(reasons)
            conn = self.db.get_writer()
            conn.execute(
                """
                INSERT INTO review_queue (
                    review_id, belief_id, proposed_content, proposed_confidence,
                    reason_entry_id, trigger_reason, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    review_id,
                    old_belief_id,
                    new_content,
                    proposed_confidence,
                    reason_entry_id,
                    trigger_reason,
                    current_time,
                ),
            )
            logger.info(
                "belief_revision_flagged_for_review",
                review_id=review_id,
                belief_id=old_belief_id,
                reasons=reasons,
            )
            return True, review_id

        # Autonomous revision: commit new belief and supersede old belief
        # Base importance boosted +0.4 for revised belief per Spec §7
        revised_importance = min(1.0, max(importance, 0.5) + 0.4)
        unsigned = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content=new_content,
            structured={"importance": revised_importance, "valid_from": current_time},
            trace_id=f"autonomous-refl-{uuid.uuid4().hex[:8]}",
            created_at=current_time,
            nonce=uuid.uuid4().hex,
            confidence=proposed_confidence,
        )
        signed = self.signer.sign(unsigned)
        new_memory_id = await self.store.commit(signed)
        await self.store.supersede(
            old_belief_id, new_memory_id, reason=reason_entry_id, now=current_time
        )

        # Summarise new_content to a readable cap so spoken update stays concise.
        new_summary = new_content[:80].rstrip() + ("…" if len(new_content) > 80 else "")
        spoken_update = (
            f"I've revised a belief I had — previously: {old_content[:60].rstrip()}. "
            f"New understanding: {new_summary}."
        )
        logger.info(
            "autonomous_belief_revision_applied",
            old_belief_id=old_belief_id,
            new_memory_id=new_memory_id,
            reason_entry_id=reason_entry_id,
        )
        return False, spoken_update

    def list_pending_reviews(self) -> list[dict[str, object]]:
        """Returns all pending items in review_queue."""
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT r.review_id, r.belief_id, m.content as old_content,
                       r.proposed_content, r.proposed_confidence, r.reason_entry_id,
                       r.trigger_reason, r.created_at, r.status
                FROM review_queue r
                LEFT JOIN memories m ON r.belief_id = m.memory_id
                WHERE r.status = 'PENDING'
                ORDER BY r.created_at ASC
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "review_id": str(r[0]),
                    "belief_id": int(r[1]) if r[1] is not None else None,
                    "old_content": str(r[2]) if r[2] is not None else "",
                    "proposed_content": str(r[3]),
                    "proposed_confidence": float(r[4]),
                    "reason_entry_id": str(r[5]),
                    "trigger_reason": str(r[6]),
                    "created_at": float(r[7]),
                    "status": str(r[8]),
                }
                for r in rows
            ]

    async def approve_review(
        self,
        review_id: str,
        decided_by: str = "operator",
        now: float | None = None,
    ) -> int:
        """Approves a flagged belief revision, superseding old belief with proposed content."""
        current_time = now if now is not None else time.time()
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT belief_id, proposed_content, proposed_confidence, reason_entry_id, status
                FROM review_queue WHERE review_id = ?
                """,
                (review_id,),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Review item '{review_id}' not found")
            if str(row[4]) != "PENDING":
                raise ValueError(f"Review item '{review_id}' is not PENDING (status={row[4]})")

        old_belief_id = int(row[0])
        proposed_content = str(row[1])
        proposed_confidence = float(row[2])
        reason_entry_id = str(row[3])

        # Commit proposed belief
        unsigned = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content=proposed_content,
            structured={"importance": 0.8, "valid_from": current_time},
            trace_id=f"review-approve-{review_id}",
            created_at=current_time,
            nonce=uuid.uuid4().hex,
            confidence=proposed_confidence,
        )
        signed = self.signer.sign(unsigned)
        new_mid = await self.store.commit(signed)
        await self.store.supersede(old_belief_id, new_mid, reason=reason_entry_id, now=current_time)

        conn = self.db.get_writer()
        conn.execute(
            "UPDATE review_queue SET status = 'APPROVED', decided_at = ?, decided_by = ? "
            "WHERE review_id = ?",
            (current_time, decided_by, review_id),
        )
        logger.info("review_approved", review_id=review_id, old=old_belief_id, new=new_mid)
        return new_mid

    def reject_review(
        self,
        review_id: str,
        decided_by: str = "operator",
        now: float | None = None,
    ) -> None:
        """Rejects a flagged belief revision, preserving old belief intact."""
        current_time = now if now is not None else time.time()
        with self.db.read_cursor() as cur:
            cur.execute("SELECT status FROM review_queue WHERE review_id = ?", (review_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Review item '{review_id}' not found")
            if str(row[0]) != "PENDING":
                raise ValueError(f"Review item '{review_id}' is not PENDING (status={row[0]})")

        conn = self.db.get_writer()
        conn.execute(
            "UPDATE review_queue SET status = 'REJECTED', decided_at = ?, decided_by = ? "
            "WHERE review_id = ?",
            (current_time, decided_by, review_id),
        )
        logger.info("review_rejected", review_id=review_id, decided_by=decided_by)

    async def rollup_nightly(self, now: float | None = None) -> int:
        """
        Rolls up low-importance autobiographical rows (< 0.2 and > 30 days) into
        session summaries (kind="session_summary"), marking originals forgotten_at.
        Rows with importance >= 0.2 are retained indefinitely.
        """
        current_time = now if now is not None else time.time()
        cutoff_time = current_time - THIRTY_DAYS_SECONDS

        # Query eligible low-importance autobiographical memories
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT m.memory_id, m.content, p.session_id, m.created_at
                FROM memories m
                JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE p.provenance IN ('ASSISTANT_UTTERANCE', 'ASSISTANT_BELIEF')
                  AND m.importance < 0.2
                  AND m.created_at < ?
                  AND m.forgotten_at IS NULL
                ORDER BY p.session_id, m.created_at ASC
                """,
                (cutoff_time,),
            )
            rows = cur.fetchall()

        if not rows:
            return 0

        # Group by session
        by_session: dict[str, list[tuple[int, str]]] = {}
        for r in rows:
            mid = int(r[0])
            content = str(r[1])
            sess = str(r[2]) or "default-session"
            by_session.setdefault(sess, []).append((mid, content))

        total_compressed = 0
        for sess_id, items in by_session.items():
            mids = [m[0] for m in items]
            summary_content = (
                f"Session {sess_id} historical autobiographical summary: "
                f"{len(items)} items compressed (including '{items[0][1][:40]}...')."
            )
            unsigned = UnsignedPayload(
                provenance=Provenance.ASSISTANT_UTTERANCE,
                kind="session_summary",
                content=summary_content,
                session_id=sess_id,
                trace_id=f"rollup-{uuid.uuid4().hex[:8]}",
                created_at=current_time,
                nonce=uuid.uuid4().hex,
                confidence=1.0,
            )
            signed = self.signer.sign(unsigned)
            await self.store.commit(signed)

            # Mark original items forgotten_at
            ph = ",".join("?" for _ in mids)
            conn = self.db.get_writer()
            conn.execute(
                f"UPDATE memories SET forgotten_at = ? WHERE memory_id IN ({ph})",  # noqa: S608
                [current_time, *mids],
            )
            total_compressed += len(mids)

        logger.info("autobiographical_nightly_rollup_completed", compressed_count=total_compressed)
        return total_compressed

    async def nightly_rollup(self, now: float | None = None) -> int:
        """Alias for rollup_nightly per Work Order #8."""
        return await self.rollup_nightly(now=now)

    def get_last_rollup_at(self) -> float | None:
        """Retrieves persistent timestamp of the last executed roll-up."""
        conn = self.db.get_writer()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS system_metadata ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        with self.db.read_cursor() as cur:
            cur.execute("SELECT value FROM system_metadata WHERE key = 'last_rollup_at'")
            row = cur.fetchone()
            return float(row[0]) if row else None

    def record_last_rollup_at(self, ts: float) -> None:
        """Persists timestamp of completed roll-up to prevent duplicate runs across restarts."""
        conn = self.db.get_writer()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS system_metadata ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO system_metadata(key, value, updated_at) VALUES ('last_rollup_at', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (str(ts), ts),
        )


def is_rollup_due(
    last_rollup_at: float | None,
    current_time: float,
    rollup_hour_local: int = 3,
) -> bool:
    """
    Evaluates whether a nightly autobiographical roll-up is due.
    Triggers once per 24h at first idle after rollup_hour_local (default 03:00).
    """
    dt_now = datetime.datetime.fromtimestamp(current_time)
    target_today = dt_now.replace(hour=rollup_hour_local, minute=0, second=0, microsecond=0)
    target_today_ts = target_today.timestamp()

    if current_time < target_today_ts:
        return False

    if last_rollup_at is None:
        return True

    return last_rollup_at < target_today_ts
