"""
Project Lucca — Qualitative Temporal Retrieval Unit Tests
Spec 04, D-MEM-10: Allen interval algebra bridge to SQLite episodic memory.
Verifies 'before', 'during', 'after', 'overlaps' constraints across
both 'created_at' (interaction time) and 'valid_time' (fact time) clocks.
Strict zero-Any typing per D-AUD-01.
"""

from collections.abc import Generator, Sequence
from pathlib import Path
import pytest

from lucca.core.schemas import (
    Provenance,
    RetrievalQuery,
    UnsignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import UserSpeechSigner
from lucca.memory.store import MemoryStore

TEST_KEY = b"01234567890123456789012345678901"


class DeterministicEmbeddingPort:
    """Lightweight deterministic embedding mock for unit tests."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vec = [0.0] * 384
        vec[0] = 1.0
        return [list(vec) for _ in texts]

    def dim(self) -> int:
        return 384


@pytest.fixture
def temp_db(tmp_path: Path) -> Generator[DatabaseManager, None, None]:
    db_path = tmp_path / "test_temporal_memory.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def store(temp_db: DatabaseManager) -> MemoryStore:
    embedder = DeterministicEmbeddingPort()
    return MemoryStore(db=temp_db, master_key=TEST_KEY, embedding_port=embedder)


@pytest.fixture
def user_signer() -> UserSpeechSigner:
    return UserSpeechSigner(master_key=TEST_KEY)


def test_temporal_retrieval_created_at_before_during_after(
    store: MemoryStore, user_signer: UserSpeechSigner
) -> None:
    """Verifies qualitative queries on the interaction clock (created_at)."""
    t_a = 1000.0
    t_b = 1075.0
    t_c = 1150.0

    # Memory A: Past interaction (t = 1000.0)
    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Interaction Alpha: User asked about breakfast recipes.",
                created_at=t_a,
                nonce="nonce_temp_a",
                trace_id="tr_temp_a",
            )
        ),
        now=t_a,
    )

    # Memory B: Target interval interaction (t = 1075.0)
    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Interaction Beta: User discussed quantum computing.",
                created_at=t_b,
                nonce="nonce_temp_b",
                trace_id="tr_temp_b",
            )
        ),
        now=t_b,
    )

    # Memory C: Future interaction (t = 1150.0)
    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Interaction Gamma: User planned a vacation to Japan.",
                created_at=t_c,
                nonce="nonce_temp_c",
                trace_id="tr_temp_c",
            )
        ),
        now=t_c,
    )

    anchor = (1050.0, 1100.0)

    # 1. Query: BEFORE anchor [150, 200]
    q_before = RetrievalQuery(
        query_text="User",
        temporal_anchor=anchor,
        temporal_relation="before",
        temporal_clock="created_at",
    )
    hits_before = store.search(q_before)
    assert len(hits_before) == 1
    assert "Interaction Alpha" in hits_before[0].content

    # 2. Query: DURING anchor [150, 200]
    q_during = RetrievalQuery(
        query_text="User",
        temporal_anchor=anchor,
        temporal_relation="during",
        temporal_clock="created_at",
    )
    hits_during = store.search(q_during)
    assert len(hits_during) == 1
    assert "Interaction Beta" in hits_during[0].content

    # 3. Query: AFTER anchor [150, 200]
    q_after = RetrievalQuery(
        query_text="User",
        temporal_anchor=anchor,
        temporal_relation="after",
        temporal_clock="created_at",
    )
    hits_after = store.search(q_after)
    assert len(hits_after) == 1
    assert "Interaction Gamma" in hits_after[0].content


def test_temporal_retrieval_valid_time_clock(
    store: MemoryStore, user_signer: UserSpeechSigner, temp_db: DatabaseManager
) -> None:
    """Verifies qualitative queries on the world fact clock ([valid_from, valid_to))."""
    # Fact 1: Overlaps anchor [150.0, 200.0] (valid 120.0 to 170.0)
    m1 = store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="fact",
                content="Fact 1: User resided in Melbourne.",
                structured={"valid_from": 120.0},
                created_at=100.0,
                nonce="nonce_fact_1",
                trace_id="tr_fact_1",
            )
        ),
        now=100.0,
    )
    with temp_db.get_writer() as conn:
        conn.execute("UPDATE memories SET valid_to = ? WHERE memory_id = ?", (170.0, m1))

    # Fact 2: Strictly DURING anchor [150.0, 200.0] (valid 160.0 to 180.0)
    m2 = store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="fact",
                content="Fact 2: User worked on Project Lucca v1.",
                structured={"valid_from": 160.0},
                created_at=100.0,
                nonce="nonce_fact_2",
                trace_id="tr_fact_2",
            )
        ),
        now=100.0,
    )
    with temp_db.get_writer() as conn:
        conn.execute("UPDATE memories SET valid_to = ? WHERE memory_id = ?", (180.0, m2))

    # Fact 3: Disjoint BEFORE anchor [150.0, 200.0] (valid 50.0 to 100.0)
    m3 = store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="fact",
                content="Fact 3: User attended university.",
                structured={"valid_from": 50.0},
                created_at=100.0,
                nonce="nonce_fact_3",
                trace_id="tr_fact_3",
            )
        ),
        now=100.0,
    )
    with temp_db.get_writer() as conn:
        conn.execute("UPDATE memories SET valid_to = ? WHERE memory_id = ?", (100.0, m3))

    anchor = (150.0, 200.0)

    # 1. OVERLAPS test: Fact 1 (120-170) and Fact 2 (160-180) overlap anchor; Fact 3 does not.
    q_overlap = RetrievalQuery(
        query_text="User",
        temporal_anchor=anchor,
        temporal_relation="overlaps",
        temporal_clock="valid_time",
    )
    hits_overlap = store.search(q_overlap)
    hit_contents = {h.content for h in hits_overlap}
    assert "Fact 1: User resided in Melbourne." in hit_contents
    assert "Fact 2: User worked on Project Lucca v1." in hit_contents
    assert "Fact 3: User attended university." not in hit_contents

    # 2. DURING test: Only Fact 2 (160-180) is strictly contained in [150, 200].
    q_during = RetrievalQuery(
        query_text="User",
        temporal_anchor=anchor,
        temporal_relation="during",
        temporal_clock="valid_time",
    )
    hits_during = store.search(q_during)
    during_contents = {h.content for h in hits_during}
    assert "Fact 2: User worked on Project Lucca v1." in during_contents
    assert "Fact 1: User resided in Melbourne." not in during_contents
    assert "Fact 3: User attended university." not in during_contents


def test_pure_temporal_query_empty_text(
    store: MemoryStore, user_signer: UserSpeechSigner
) -> None:
    """Verifies that queries with empty query_text still retrieve candidates via temporal anchor."""
    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Solo memory item at specific timestamp.",
                created_at=500.0,
                nonce="nonce_solo",
                trace_id="tr_solo",
            )
        ),
        now=500.0,
    )

    q_pure = RetrievalQuery(
        query_text="",
        temporal_anchor=(450.0, 550.0),
        temporal_relation="during",
        temporal_clock="created_at",
    )
    hits = store.search(q_pure)
    assert len(hits) == 1
    assert "Solo memory item" in hits[0].content


def test_extract_temporal_constraints_units() -> None:
    """Verifies regex and calendar extraction rules in extract_temporal_constraints."""
    from datetime import UTC, datetime
    from lucca.memory.retrieval import extract_temporal_constraints

    now = 1735689600.0  # 2025-01-01 00:00:00 UTC

    # 1. Year match
    q1, anchor1, rel1, clock1 = extract_temporal_constraints("What was my role in 2024?", now=now)
    assert q1 == "What was my role?"
    assert rel1 == "during"
    assert clock1 == "valid_time"
    assert anchor1 is not None
    assert anchor1[0] == datetime(2024, 1, 1, tzinfo=UTC).timestamp()
    assert anchor1[1] == datetime(2025, 1, 1, tzinfo=UTC).timestamp()

    # 2. Yesterday match
    q2, anchor2, rel2, clock2 = extract_temporal_constraints("What did we say yesterday?", now=now)
    assert q2 == "What did we say?"
    assert rel2 == "during"
    assert clock2 == "created_at"
    assert anchor2 is not None

    # 3. Earlier match
    q3, anchor3, rel3, clock3 = extract_temporal_constraints("What did I say earlier?", now=now)
    assert q3 == "What did I say?"
    assert rel3 == "before"
    assert clock3 == "created_at"
    assert anchor3 is not None


def test_dialogue_automatic_temporal_filtering_e2e(
    store: MemoryStore, user_signer: UserSpeechSigner
) -> None:
    """
    Verifies that natural dialogue queries automatically resolve event anchors
    and filter episodic memory before/after the referenced event.
    """
    t_past = 500.0
    t_benchmark = 1000.0
    t_future = 1500.0

    # Past memory
    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Discussion: User shared pizza recipe ideas.",
                created_at=t_past,
                nonce="nonce_recipe",
                trace_id="tr_recipe",
            )
        ),
        now=t_past,
    )

    # Anchor memory (the benchmark event)
    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Discussion: Started the benchmark run on Tier 0 silicon.",
                created_at=t_benchmark,
                nonce="nonce_bench",
                trace_id="tr_bench",
            )
        ),
        now=t_benchmark,
    )

    # Future memory
    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Discussion: Reviewed benchmark log outputs and charts.",
                created_at=t_future,
                nonce="nonce_after",
                trace_id="tr_after",
            )
        ),
        now=t_future,
    )

    # Natural dialogue query asking what happened BEFORE the benchmark:
    q = RetrievalQuery(query_text="What recipe ideas did we discuss before the benchmark?")
    hits = store.search(q, now=t_future)
    assert len(hits) >= 1
    hit_contents = [h.content for h in hits]
    assert any("pizza recipe ideas" in c for c in hit_contents)
    # The benchmark and post-benchmark logs must be filtered out by the 'before' constraint!
    assert not any("Reviewed benchmark log" in c for c in hit_contents)


def test_cascade_temporal_dialogue_e2e(
    store: MemoryStore, user_signer: UserSpeechSigner
) -> None:
    """Verifies that EpistemicSearchCascade end-to-end resolves temporal queries via Substrate 2."""
    from lucca.core.cascade import EpistemicSearchCascade, EpistemicSubstrate

    cascade = EpistemicSearchCascade(memory_store=store)

    t_1 = 100.0
    t_2 = 500.0

    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Favorite animal discussion: User stated they love sea otters.",
                created_at=t_1,
                nonce="nonce_otter",
                trace_id="tr_otter",
            )
        ),
        now=t_1,
    )

    store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="System update event occurred on local workstation.",
                created_at=t_2,
                nonce="nonce_update",
                trace_id="tr_update",
            )
        ),
        now=t_2,
    )

    res = cascade.query("What animal did I mention before the update?", substrates=[EpistemicSubstrate.MEMORY])
    assert any("sea otters" in e.content for e in res.evidence)
    assert not any("System update" in e.content for e in res.evidence)


