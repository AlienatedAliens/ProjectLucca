"""
Project Lucca — Hard Purge & Zero-Leak Memory Barrier Tests
WO-25 Phase 1 / SPEC-BENCH-100 CAT08-07
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from lucca.core.cascade import BelnapValue, EpistemicSearchCascade, EpistemicSubstrate
from lucca.core.schemas import RetrievalQuery
from lucca.core.studio_facade import StudioFacade
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore


@pytest.fixture
def master_key() -> bytes:
    return b"01234567890123456789012345678901"


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_purge_memory.sqlite"
    db = DatabaseManager(db_path=db_file)
    db.migrate()
    return db


@pytest.fixture
def test_store(test_db: DatabaseManager, master_key: bytes) -> MemoryStore:
    return MemoryStore(db=test_db, master_key=master_key)


@pytest.fixture
def facade(test_db: DatabaseManager, test_store: MemoryStore, master_key: bytes) -> StudioFacade:
    return StudioFacade(
        db=test_db,
        store=test_store,
        master_key=master_key,
    )


def test_hard_purge_requires_user_confirmation(test_store: MemoryStore, facade: StudioFacade) -> None:
    """Negative control: hard purge without explicit confirmation must fail closed."""
    with pytest.raises(ValueError, match="explicit user confirmation"):
        test_store.hard_purge_all(user_confirmed=False)

    with pytest.raises(ValueError, match="user confirmation"):
        facade.factory_reset_memories(user_confirmed=False)


def test_hard_purge_zero_ghost_leak(test_db: DatabaseManager, test_store: MemoryStore, facade: StudioFacade) -> None:
    """
    Positive control: Seed data across memories, KG, decisions, and rules.
    Execute hard purge -> Assert exact 0 rows across all stores.
    Assert subsequent queries return honest calibrated abstention with zero ghost recall.
    """
    # 1. Seed Memory facts
    secret_fact = "The deployment secret code is CRIMSON-OCTOBER-99."
    m_id = facade.add_memory_fact(secret_fact, importance=0.95)
    assert m_id > 0

    # 2. Seed Knowledge Graph entity and edge
    conn = test_db.get_writer()
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO kg_entities(canonical, type, created_at) VALUES ('crimson_code', 'secret', ?) ON CONFLICT(canonical) DO NOTHING",
            (now,),
        )
        conn.execute(
            "INSERT INTO kg_entities(canonical, type, created_at) VALUES ('october_operation', 'operation', ?) ON CONFLICT(canonical) DO NOTHING",
            (now,),
        )
        s_id = conn.execute("SELECT entity_id FROM kg_entities WHERE canonical='crimson_code'").fetchone()[0]
        o_id = conn.execute("SELECT entity_id FROM kg_entities WHERE canonical='october_operation'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO kg_edges(s, p, o, memory_id, valid_from, recorded_at, confidence)
            VALUES (?, 'associated_with', ?, ?, ?, ?, 1.0)
            """,
            (s_id, o_id, m_id, now, now),
        )
        # 3. Seed Decision record
        conn.execute(
            """
            INSERT INTO decisions(
                decision_id, trace_id, session_id, ts, features_json, action,
                probabilities_json, prediction_set_json, elapsed_us, router_version, executed_path
            ) VALUES ('dec-test-01', 'tr-01', 'sess-01', ?, '{"transcript": "CRIMSON-OCTOBER"}', 'recall',
                      '{}', '[]', 100, 'v1', 'recall')
            """,
            (now,),
        )
        # 4. Seed Rule State
        conn.execute(
            """
            INSERT INTO rule_states(
                rule_id, status, source_canonical, source_hash, created_at
            ) VALUES ('rule-crimson-v1', 'active', '(rule crimson)', 'hash123', ?)
            """,
            (now,),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    # Verify seed state exists in all target stores
    with test_db.read_cursor() as cur:
        assert cur.execute("SELECT count(*) FROM memories").fetchone()[0] >= 1
        assert cur.execute("SELECT count(*) FROM kg_entities").fetchone()[0] >= 2
        assert cur.execute("SELECT count(*) FROM kg_edges").fetchone()[0] >= 1
        assert cur.execute("SELECT count(*) FROM decisions").fetchone()[0] >= 1
        assert cur.execute("SELECT count(*) FROM rule_states").fetchone()[0] >= 1

    # Verify search recall prior to purge
    hits = test_store.search(RetrievalQuery(query_text="CRIMSON", top_k=5))
    assert len(hits) >= 1
    assert "CRIMSON-OCTOBER-99" in hits[0].content

    # 5. EXECUTE THE HARD PURGE BARRIER
    purged_counts = test_store.hard_purge_all(user_confirmed=True)
    assert sum(purged_counts.values()) >= 5

    # 6. Assert exact ZERO rows across ALL stores
    with test_db.read_cursor() as cur:
        tables_to_verify = [
            "memories",
            "kg_entities",
            "kg_edges",
            "decisions",
            "rule_states",
            "provenance_envelopes",
            "vec_memories",
            "fts_memories",
            "vec_decisions",
            "fts_decisions",
            "memory_audit",
            "review_queue",
            "memory_sources",
        ]
        for tbl in tables_to_verify:
            cnt = cur.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
            assert cnt == 0, f"Table '{tbl}' still contains {cnt} ghost records after hard purge"

    # 7. Assert honest calibrated abstention & zero ghost recall
    post_hits = test_store.search(RetrievalQuery(query_text="CRIMSON", top_k=5))
    assert len(post_hits) == 0

    # Epistemic cascade query for the secret
    cascade = EpistemicSearchCascade(memory_store=test_store)
    res = cascade.query("What is the deployment secret code?", substrates=[EpistemicSubstrate.MEMORY])
    assert res.belnap_status == BelnapValue.UNKNOWN
    assert res.calibrated_refusal is not None
    assert "memory records" in res.calibrated_refusal
    assert "CRIMSON" not in (res.synthesized_context or "")
