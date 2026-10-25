"""
Project Lucca — Studio Facade (Core Boundary)
Spec §1, §16, ADR-005, WO-18e (F-ARCH-104)

Unifies domain operations required by SettingsDialog, TelemetryHUD, and UI components
behind a clean, in-process core interface.
Direct domain imports (lucca.memory, lucca.reasoning, lucca.sandbox) from lucca.ui
are eliminated in favor of this facade.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import JsonValue

from lucca.core.config import get_config
from lucca.core.schemas import Provenance, RuleState, UnsignedPayload
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import create_user_speech_signer
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.eval import evaluate_rule as _evaluate_rule
from lucca.reasoning.scheme.parser import parse_rule as _parse_rule
from lucca.reasoning.skills import SkillManager
from lucca.reasoning.stats import rule_of_three_ucl as _rule_of_three_ucl
from lucca.sandbox.system_tools import get_system_metrics as _get_system_metrics

if TYPE_CHECKING:
    from lucca.reasoning.lifecycle import ContrastiveSummary, ReplayReport
    from lucca.reasoning.scheme.eval import RuleEvalOutcome
    from lucca.reasoning.scheme.parser import Rule

logger = logging.getLogger(__name__)


class StudioFacade:
    """Consolidated in-process facade mediating UI access to Lucca domain services (WO-18e)."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        store: MemoryStore | None = None,
        rule_lifecycle: RuleLifecycleManager | None = None,
        skill_manager: SkillManager | None = None,
        reflection_engine: ReflectionEngine | None = None,
        master_key: bytes | None = None,
    ) -> None:
        cfg = get_config()
        from lucca.core.config import resolve_or_create_master_key
        self.master_key = (
            master_key
            if master_key is not None
            else resolve_or_create_master_key(cfg)
        )

        if db is not None:
            self.db = db
        else:
            db_path = cfg.home_dir / "data" / "memory.sqlite"
            self.db = DatabaseManager(db_path=db_path)

        if store is not None:
            self.store = store
        elif self.master_key:
            try:
                self.store = MemoryStore(db=self.db, master_key=self.master_key)
            except Exception as exc:
                logger.debug("init_memory_store_failed: %s", exc)
                self.store = None
        else:
            self.store = None

        if rule_lifecycle is not None:
            self.rule_lifecycle = rule_lifecycle
        else:
            try:
                self.rule_lifecycle = RuleLifecycleManager(db=self.db)
            except Exception as exc:
                logger.debug("init_rule_lifecycle_failed: %s", exc)
                self.rule_lifecycle = None

        if skill_manager is not None:
            self.skill_manager = skill_manager
        else:
            try:
                self.skill_manager = SkillManager()
            except Exception as exc:
                logger.debug("init_skill_manager_failed: %s", exc)
                self.skill_manager = None

        if reflection_engine is not None:
            self.reflection_engine = reflection_engine
        elif self.store is not None and self.master_key:
            try:
                self.reflection_engine = ReflectionEngine(
                    db=self.db, store=self.store, master_key=self.master_key
                )
            except Exception as exc:
                logger.debug("init_reflection_engine_failed: %s", exc)
                self.reflection_engine = None
        else:
            self.reflection_engine = None

    # =========================================================================
    # Memory Operations (Gate-Verified, Store-Backed)
    # =========================================================================

    def get_memory_stats(self) -> dict[str, JsonValue]:
        """Returns statistics on memory database."""
        conn = self.db.get_connection()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM memories WHERE forgotten_at IS NULL")
            active_count = cur.fetchone()[0]

            cur = conn.execute("SELECT COUNT(*) FROM memories WHERE forgotten_at IS NOT NULL")
            forgotten_count = cur.fetchone()[0]

            db_size_bytes = 0
            if Path(self.db.db_path).exists():
                db_size_bytes = Path(self.db.db_path).stat().st_size

            return {
                "active_memories": active_count,
                "forgotten_memories": forgotten_count,
                "total_memories": active_count + forgotten_count,
                "db_size_kb": round(db_size_bytes / 1024, 1),
                "db_path": str(self.db.db_path),
            }
        finally:
            conn.close()

    def list_memories(
        self,
        search: str = "",
        kind_filter: str | None = None,
        include_forgotten: bool = False,
        include_superseded: bool = False,
    ) -> list[dict[str, JsonValue]]:
        """Lists memories matching optional text and kind filters."""
        conn = self.db.get_connection()
        try:
            query = """
                SELECT
                    m.memory_id,
                    m.entry_id,
                    m.content,
                    m.kind,
                    m.created_at,
                    m.valid_from,
                    m.valid_to,
                    m.superseded_by,
                    m.importance,
                    m.forgotten_at,
                    p.provenance,
                    p.confidence
                FROM memories m
                LEFT JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE (m.forgotten_at IS NULL OR ? = 1)
                  AND (m.valid_to IS NULL OR ? = 1)
            """
            params: list[object] = [1 if include_forgotten else 0, 1 if include_superseded else 0]

            if search.strip():
                query += " AND (m.content LIKE ? OR m.kind LIKE ? OR p.provenance LIKE ?)"
                term = f"%{search.strip()}%"
                params.extend([term, term, term])

            if kind_filter:
                query += " AND m.kind = ?"
                params.append(kind_filter)

            query += " ORDER BY m.created_at DESC"
            cur = conn.execute(query, params)
            rows = cur.fetchall()

            result = []
            for r in rows:
                result.append(
                    {
                        "memory_id": r["memory_id"],
                        "entry_id": r["entry_id"],
                        "content": r["content"],
                        "kind": r["kind"],
                        "created_at": r["created_at"],
                        "valid_from": r["valid_from"],
                        "valid_to": r["valid_to"],
                        "superseded_by": r["superseded_by"],
                        "importance": float(r["importance"]),
                        "forgotten_at": r["forgotten_at"],
                        "provenance": r["provenance"] or "USER_EXPLICIT",
                        "confidence": float(r["confidence"]) if r["confidence"] is not None else 1.0,
                    }
                )
            return result
        finally:
            conn.close()

    def forget_memory(self, memory_id: int, user_confirmed: bool = True) -> None:
        """Soft-deletes a memory through MemoryStore.forget with user confirmation (WO-19f / Trap 2)."""
        if self.store is None:
            raise RuntimeError("MemoryStore is not initialized")
        self.store.forget([memory_id], user_confirmed=user_confirmed)

    def forget_memories(self, memory_ids: list[int], user_confirmed: bool = True) -> int:
        """Soft-deletes multiple memories through MemoryStore.forget with user confirmation."""
        if self.store is None:
            raise RuntimeError("MemoryStore is not initialized")
        if not user_confirmed:
            raise ValueError("Forgetting memories requires explicit user confirmation")
        if not memory_ids:
            return 0
        self.store.forget(memory_ids, user_confirmed=True)
        return len(memory_ids)

    def factory_reset_memories(self, user_confirmed: bool = True) -> int:
        """Permanently eradicates all memories, KG, decisions, rules, and provenance via hard purge. Returns total count pruned."""
        if not user_confirmed:
            raise ValueError("Factory reset requires user confirmation")
        if self.store is None:
            from lucca.core.config import get_config, resolve_or_create_master_key
            key = self.master_key or resolve_or_create_master_key(get_config())
            self.store = MemoryStore(db=self.db, master_key=key)
        deleted_counts = self.store.hard_purge_all(user_confirmed=True)
        return sum(deleted_counts.values())

    def add_memory_fact(
        self,
        content: str,
        importance: float = 0.85,
        kind: Literal["transcript", "fact", "tool_fact", "rule_assertion"] = "fact",
    ) -> int:
        """Adds an operator-seeded memory fact through HMAC signing and ProvenanceGate admission."""
        if self.store is None or self.master_key is None:
            raise RuntimeError("MemoryStore and master_key are required to admit memories")

        signer = create_user_speech_signer(master_key=self.master_key, signer_id="ui-admin")
        now = time.time()
        unsigned = UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind=kind,
            content=content,
            structured={"source": "operator_seed", "importance": importance},
            trace_id="operator-seed-trace",
            session_id="operator-seed-session",
            created_at=now,
            nonce=uuid.uuid4().hex,
            confidence=1.0,
        )
        signed = signer.sign(unsigned)
        admitted = self.store.gate.admit(signed, now=now)
        return int(self.store.commit(admitted, now=now))

    def update_memory(
        self,
        memory_id: int,
        new_content: str,
        importance: float = 0.8,
    ) -> int:
        """Updates an existing memory via gate-verified commit and bi-temporal supersession."""
        if self.store is None or self.master_key is None:
            raise RuntimeError("MemoryStore and master_key are required to update memories")

        # 1. Fetch kind of existing memory
        with self.db.read_cursor() as cur:
            cur.execute("SELECT kind FROM memories WHERE memory_id = ?", (memory_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Memory #{memory_id} not found")
            existing_kind = row[0]

        # 2. Commit new memory
        new_mid = self.add_memory_fact(
            content=new_content,
            importance=importance,
            kind=existing_kind,
        )

        # 3. Fetch entry_id of new memory
        with self.db.read_cursor() as cur:
            cur.execute("SELECT entry_id FROM memories WHERE memory_id = ?", (new_mid,))
            row = cur.fetchone()
            new_entry_id = row[0] if row else ""

        # 4. Mark old memory superseded by new memory
        self.store.supersede(memory_id, new_mid, reason=new_entry_id)
        return new_mid

    def vacuum_database(self) -> None:
        """Optimizes SQLite database and vector indices.

        Surfaces an informative RuntimeError when core engine holds a WAL write lock.
        """
        conn = self.db.get_writer()
        try:
            conn.execute("VACUUM")
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise RuntimeError(
                    "Database is locked by the active Lucca engine. "
                    "Please shut down Lucca core before vacuuming."
                ) from exc
            raise

    # =========================================================================
    # Review Queue & Autonomic Reflection
    # =========================================================================

    def list_review_queue(self, status: str = "ALL") -> list[dict[str, object]]:
        """Lists items from the reflection review_queue."""
        conn = self.db.get_connection()
        try:
            cur = conn.execute(
                """
                SELECT r.review_id, r.belief_id, m.content as old_content,
                       r.proposed_content, r.proposed_confidence, r.reason_entry_id,
                       r.trigger_reason, r.created_at, r.status
                FROM review_queue r
                LEFT JOIN memories m ON r.belief_id = m.memory_id
                WHERE (? = 'ALL' OR r.status = ?)
                ORDER BY r.created_at ASC
                """,
                (status, status),
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
        finally:
            conn.close()

    def approve_review(self, review_id: str, decided_by: str = "ui-operator") -> int | None:
        """Approves a queued belief update and commits the new belief."""
        if self.reflection_engine is None:
            raise RuntimeError("ReflectionEngine is not initialized")
        return self.reflection_engine.approve_review(review_id, decided_by=decided_by)

    def reject_review(self, review_id: str, decided_by: str = "ui-operator") -> None:
        """Rejects a queued belief update and preserves the existing belief."""
        if self.reflection_engine is None:
            raise RuntimeError("ReflectionEngine is not initialized")
        self.reflection_engine.reject_review(review_id, decided_by=decided_by)

    def list_review_required_topics(self) -> list[str]:
        """Lists all topics requiring operator review before updates."""
        if self.reflection_engine is not None:
            return self.reflection_engine.list_review_required_topics()
        with self.db.read_cursor() as cur:
            cur.execute("SELECT topic FROM review_required_topics ORDER BY topic ASC")
            return [str(row[0]) for row in cur.fetchall()]

    def mark_topic_review_required(self, topic: str) -> None:
        """Marks a topic as requiring explicit review."""
        if self.reflection_engine is not None:
            self.reflection_engine.mark_topic_review_required(topic)
        else:
            conn = self.db.get_writer()
            conn.execute(
                "INSERT OR IGNORE INTO review_required_topics (topic, created_at) VALUES (?, ?)",
                (topic.strip().lower(), time.time()),
            )

    def unmark_topic_review_required(self, topic: str) -> None:
        """Removes a topic from the review-required list."""
        if self.reflection_engine is not None:
            self.reflection_engine.unmark_topic_review_required(topic)
        else:
            conn = self.db.get_writer()
            conn.execute(
                "DELETE FROM review_required_topics WHERE lower(topic) = ?",
                (topic.strip().lower(),),
            )

    def trigger_nightly_rollup(self) -> tuple[bool, str]:
        """Triggers nightly reflection and consolidation rollup."""
        if self.reflection_engine is None:
            return False, "ReflectionEngine is not available"
        return self.reflection_engine.nightly_rollup()

    # =========================================================================
    # Rule Lifecycle & LISP Studio (Read-Only Snapshots)
    # =========================================================================

    def get_rules(self) -> dict[str, Rule]:
        """Returns registered rules dictionary.

        Returned objects are snapshots for display; mutate only through facade methods.
        """
        if self.rule_lifecycle is None:
            return {}
        return self.rule_lifecycle.rules

    def approve_rule(self, rule_id: str) -> None:
        """Approves a rule candidate for activation."""
        if self.rule_lifecycle is None:
            raise RuntimeError("RuleLifecycleManager is not initialized")
        self.rule_lifecycle.approve_rule(rule_id)

    def retire_rule(self, rule_id: str) -> None:
        """Retires an active rule."""
        if self.rule_lifecycle is None:
            raise RuntimeError("RuleLifecycleManager is not initialized")
        self.rule_lifecycle.retire_rule(rule_id)

    def replay_rule_candidate(self, rule_id: str) -> ReplayReport:
        """Replays a rule candidate against recorded turn logs.

        Returned objects are snapshots for display; mutate only through facade methods.
        """
        if self.rule_lifecycle is None:
            raise RuntimeError("RuleLifecycleManager is not initialized")
        return self.rule_lifecycle.replay_candidate(rule_id)

    def get_rule_contrastive_summary(self, rule_id: str) -> ContrastiveSummary:
        """Returns contrastive performance metrics for a rule candidate.

        Returned objects are snapshots for display; mutate only through facade methods.
        """
        if self.rule_lifecycle is None:
            raise RuntimeError("RuleLifecycleManager is not initialized")
        return self.rule_lifecycle.get_contrastive_summary(rule_id)

    @staticmethod
    def parse_rule(code: str) -> Rule:
        """Parses Scheme LISP code into a validated Rule object.

        Returned objects are snapshots for display; mutate only through facade methods.
        """
        return _parse_rule(code)

    @staticmethod
    def evaluate_rule(rule_obj: Rule, state: RuleState) -> RuleEvalOutcome:
        """Evaluates a parsed Rule against the provided environmental RuleState."""
        return _evaluate_rule(rule_obj, state)

    @staticmethod
    def rule_of_three_ucl(n_clusters: int) -> float:
        """Calculates upper confidence limit via rule of three."""
        return _rule_of_three_ucl(n_clusters)

    # =========================================================================
    # Skill Packages
    # =========================================================================

    def get_skills_dir(self) -> Path:
        """Returns active skills directory."""
        if self.skill_manager is None:
            return Path()
        return self.skill_manager.skills_dir

    def get_retired_dir(self) -> Path:
        """Returns retired skills quarantine directory."""
        if self.skill_manager is None:
            return Path()
        return self.skill_manager.retired_dir

    def retire_skill(self, rule_id: str) -> None:
        """Retires a skill package to the quarantine directory."""
        if self.skill_manager is None:
            raise RuntimeError("SkillManager is not initialized")
        self.skill_manager.retire_skill(rule_id)

    def save_skill_plan(self, rule_id: str, code: str) -> Path:
        """Saves Scheme plan code into the corresponding skill package on disk."""
        if self.skill_manager is None:
            raise RuntimeError("SkillManager is not initialized")
        plan_path = self.skill_manager.skills_dir / rule_id / "plan.scm"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(code, encoding="utf-8")
        return plan_path

    # =========================================================================
    # System Telemetry & Diagnostics
    # =========================================================================

    @staticmethod
    def get_system_metrics() -> dict[str, JsonValue]:
        """Collects live workstation system telemetry (RAM, VRAM, CPU, latency)."""
        return _get_system_metrics()

    @staticmethod
    def capture_screenshot(
        max_width: int = 1280,
        quality: int = 75,
    ) -> tuple[str, int, int]:
        """Captures primary display/active screen via sandbox screenshot tool."""
        from lucca.sandbox.screenshot_tool import capture_screenshot as _capture_screenshot

        return _capture_screenshot(max_width=max_width, quality=quality)
