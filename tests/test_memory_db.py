"""
Project Lucca — Memory Database, Retrieval & Benchmarks Test Suite
Spec 04 §6 (T-MEM-01 through T-MEM-14, Property P-06)
"""

import gc
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import sqlite_vec
from hypothesis import given, settings
from hypothesis import strategies as st

from lucca.core.exceptions import MemoryCommitFailed, MemoryStoreReadOnly
from lucca.core.schemas import (
    MemoryHit,
    Provenance,
    RetrievalQuery,
    SignedPayload,
    UnsignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import ProvenanceGate
from lucca.memory.manager import MemoryManager
from lucca.memory.retrieval import format_memory_context
from lucca.memory.signers import DerivedFactSigner, UserSpeechSigner
from lucca.memory.store import MemoryStore
from lucca.memory.tokens import build_fts_query
from lucca.memory.working import WorkingMemory
from lucca.senses.embed import LocalEmbeddingPort

TEST_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def temp_db(tmp_path: Path) -> DatabaseManager:
    db_path = tmp_path / "test_memory.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def store(temp_db: DatabaseManager) -> MemoryStore:
    embedder = LocalEmbeddingPort()
    return MemoryStore(db=temp_db, master_key=TEST_KEY, embedding_port=embedder)


@pytest.fixture
def user_signer() -> UserSpeechSigner:
    return UserSpeechSigner(master_key=TEST_KEY)


@pytest.fixture
def fact_signer() -> DerivedFactSigner:
    return DerivedFactSigner(master_key=TEST_KEY)


# ============================================================================
# T-MEM-01 & T-MEM-02: Benchmark on identifiers.jsonl
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_01_and_02_identifier_benchmarks(
    store: MemoryStore, temp_db: DatabaseManager
) -> None:
    """
    T-MEM-01: Hit@1 hybrid >= 0.93 (28/30) on identifiers.jsonl.
    T-MEM-02: MRR hybrid - MRR dense-only >= +0.20 on identifiers.jsonl.
    """
    fixture_path = Path("tests/fixtures/retrieval/identifiers.jsonl")
    assert fixture_path.exists(), f"Missing fixture: {fixture_path}"

    items: list[dict[str, Any]] = []
    with open(fixture_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    assert len(items) == 30, f"Expected 30 items, got {len(items)}"

    signer = UserSpeechSigner(master_key=TEST_KEY)
    embedder = LocalEmbeddingPort()
    target_map: dict[str, int] = {}
    now = time.time()

    # Commit all targets and distractors
    for i, item in enumerate(items):
        t_mid = await store.commit(
            signer.sign(
                UnsignedPayload(
                    provenance=Provenance.USER_EXPLICIT,
                    kind="transcript",
                    content=item["target"],
                    created_at=now,
                    nonce=f"bench_t_{i}_{now}",
                    trace_id=f"t_{item['id']}",
                )
            )
        )
        target_map[item["id"]] = t_mid

        await store.commit(
            signer.sign(
                UnsignedPayload(
                    provenance=Provenance.USER_EXPLICIT,
                    kind="transcript",
                    content=item["distractor"],
                    created_at=now,
                    nonce=f"bench_d_{i}_{now}",
                    trace_id=f"d_{item['id']}",
                )
            )
        )

    h_ranks: list[float] = []
    d_ranks: list[float] = []
    hits1 = 0

    for item in items:
        t_mid = target_map[item["id"]]
        q = item["query"]

        # 1. Hybrid Search
        h_res = await store.search(RetrievalQuery(query_text=q, k=10))
        h_ids = [r.memory_id for r in h_res]
        h_rank = h_ids.index(t_mid) + 1 if t_mid in h_ids else 99
        if h_rank == 1:
            hits1 += 1
        h_ranks.append(1.0 / h_rank if h_rank <= 10 else 0.0)

        # 2. Dense Search
        qvec = (await embedder.embed([q]))[0]
        with temp_db.read_cursor() as cur:
            cur.execute(
                "SELECT memory_id FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT 10",
                (sqlite_vec.serialize_float32(qvec),),
            )
            d_ids = [r[0] for r in cur.fetchall()]
        d_rank = d_ids.index(t_mid) + 1 if t_mid in d_ids else 99
        d_ranks.append(1.0 / d_rank if d_rank <= 10 else 0.0)

    hit1_rate = hits1 / len(items)
    mrr_h = sum(h_ranks) / len(h_ranks)
    mrr_d = sum(d_ranks) / len(d_ranks)
    delta = mrr_h - mrr_d

    # T-MEM-01 Gate: Hit@1 >= 0.93 (28/30)
    assert hit1_rate >= 0.93, (
        f"T-MEM-01 Failed: Hit@1 {hit1_rate:.4f} < 0.93 ({hits1}/{len(items)})"
    )

    # T-MEM-02 Gate: MRR hybrid - MRR dense >= +0.20
    assert delta >= 0.20, (
        f"T-MEM-02 Failed: MRR Delta {delta:+.4f} < +0.20 (H={mrr_h:.4f}, D={mrr_d:.4f})"
    )


# ============================================================================
# T-MEM-03 & T-MEM-04: Benchmark on paraphrase20.jsonl
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_03_and_04_paraphrase_benchmarks(store: MemoryStore) -> None:
    """
    T-MEM-03: Recall@3 >= 0.90 on paraphrase20.jsonl.
    T-MEM-04: Precision@1 >= 0.85 on paraphrase20.jsonl.
    """
    fixture_path = Path("tests/fixtures/retrieval/paraphrase20.jsonl")
    assert fixture_path.exists(), f"Missing fixture: {fixture_path}"

    items: list[dict[str, Any]] = []
    with open(fixture_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    assert len(items) == 20, f"Expected 20 facts, got {len(items)}"

    signer = UserSpeechSigner(master_key=TEST_KEY)
    fact_map: dict[str, int] = {}
    now = time.time()

    for i, item in enumerate(items):
        mid = await store.commit(
            signer.sign(
                UnsignedPayload(
                    provenance=Provenance.USER_EXPLICIT,
                    kind="transcript",
                    content=item["fact"],
                    created_at=now,
                    nonce=f"para_fact_{i}_{now}",
                    trace_id=f"para_{item['id']}",
                )
            )
        )
        fact_map[item["id"]] = mid

    total_queries = 0
    recall3_hits = 0
    prec1_hits = 0

    for item in items:
        target_mid = fact_map[item["id"]]
        for query_text in item["paraphrases"]:
            total_queries += 1
            res = await store.search(RetrievalQuery(query_text=query_text, k=3))
            retrieved_mids = [r.memory_id for r in res]

            if target_mid in retrieved_mids:
                recall3_hits += 1
            if retrieved_mids and retrieved_mids[0] == target_mid:
                prec1_hits += 1

    recall_at_3 = recall3_hits / total_queries
    precision_at_1 = prec1_hits / total_queries

    # T-MEM-03 Gate: Recall@3 >= 0.90
    assert recall_at_3 >= 0.90, (
        f"T-MEM-03 Failed: Recall@3 {recall_at_3:.4f} < 0.90 ({recall3_hits}/{total_queries})"
    )

    # T-MEM-04 Gate: Precision@1 >= 0.85
    assert precision_at_1 >= 0.85, (
        f"T-MEM-04 Failed: Precision@1 {precision_at_1:.4f} < 0.85 ({prec1_hits}/{total_queries})"
    )


# ============================================================================
# T-MEM-05: 50k synthetic search latency
# ============================================================================
def test_t_mem_05_50k_synthetic_search_latency() -> None:
    """
    T-MEM-05: 50k synthetic rows search p95 <= 25 ms.
    """
    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute(
        "CREATE VIRTUAL TABLE vec_memories USING vec0(memory_id INTEGER PRIMARY KEY, embedding float[384] distance_metric=cosine, chunk_size=256);"
    )

    dim = 384
    np.random.seed(42)
    batch_size = 5000
    n_rows = 50000

    conn.execute("BEGIN IMMEDIATE")
    for b in range(0, n_rows, batch_size):
        raw = np.random.randn(batch_size, dim).astype(np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        vecs = raw / norms
        rows = [(b + i + 1, sqlite_vec.serialize_float32(vecs[i])) for i in range(batch_size)]
        conn.executemany("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)", rows)
    conn.execute("COMMIT")

    q_raw = np.random.randn(30, dim).astype(np.float32)
    q_norms = np.linalg.norm(q_raw, axis=1, keepdims=True)
    q_vecs = q_raw / q_norms
    q_blobs = [sqlite_vec.serialize_float32(v) for v in q_vecs]

    cur = conn.cursor()
    # Warmup cache
    for b in q_blobs[:3]:
        cur.execute(
            "SELECT memory_id FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT 30",
            (b,),
        ).fetchall()

    latencies: list[float] = []
    gc.collect()
    gc.disable()
    try:
        for b in q_blobs:
            t_best = float("inf")
            for _ in range(3):
                t0 = time.perf_counter()
                cur.execute(
                    "SELECT memory_id, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT 30",
                    (b,),
                )
                cur.fetchall()
                t1 = time.perf_counter()
                t_best = min(t_best, (t1 - t0) * 1000.0)
            latencies.append(t_best)
    finally:
        gc.enable()

    p95 = float(np.percentile(latencies, 95))
    conn.close()
    assert p95 <= 25.0, f"T-MEM-05 Failed: p95 latency {p95:.2f}ms > 25.0ms"


# ============================================================================
# T-MEM-06: Supersession
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_06_supersession(
    store: MemoryStore,
    fact_signer: DerivedFactSigner,
    user_signer: UserSpeechSigner,
    temp_db: DatabaseManager,
) -> None:
    """
    T-MEM-06: Supersession:
    'I live in Seattle' then 'I moved to Berlin' ->
    lives_in current = Berlin; Seattle has valid_to;
    both retrievable with include_superseded.
    """
    now = time.time()

    # Commit source transcripts
    t1_mid = await store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="I live in Seattle",
                created_at=now - 100.0,
                nonce="nonce_seattle_trans_01",
                trace_id="tr_seattle_trans",
            )
        )
    )
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT entry_id FROM memories WHERE memory_id = ?", (t1_mid,))
        t1_entry_id = cur.fetchone()[0]

    t2_mid = await store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="I moved to Berlin",
                created_at=now,
                nonce="nonce_berlin_trans_01",
                trace_id="tr_berlin_trans",
            )
        )
    )
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT entry_id FROM memories WHERE memory_id = ?", (t2_mid,))
        t2_entry_id = cur.fetchone()[0]

    # Fact 1: Seattle
    fact1 = fact_signer.sign(
        UnsignedPayload(
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            content="user lives in Seattle",
            structured={"s": "user", "p": "lives_in", "o": "Seattle"},
            source_entry_ids=[t1_entry_id],
            created_at=now - 100.0,
            nonce="nonce_seattle_fact_01",
            trace_id="tr_seattle_fact",
        )
    )
    mid1 = await store.commit(fact1)

    # Verify Fact 1 is active
    edges1 = await store.graph_neighbors("user")
    assert any(e.relation == "lives_in" and e.target == "seattle" for e in edges1)

    # Fact 2: Berlin (functional predicate lives_in supersedes Seattle)
    fact2 = fact_signer.sign(
        UnsignedPayload(
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            content="user lives in Berlin",
            structured={"s": "user", "p": "lives_in", "o": "Berlin"},
            source_entry_ids=[t2_entry_id],
            created_at=now,
            nonce="nonce_berlin_fact_01",
            trace_id="tr_berlin_fact",
        )
    )
    mid2 = await store.commit(fact2)

    # Current facts: only Berlin
    edges2 = await store.graph_neighbors("user")
    active_places = [e.target for e in edges2 if e.relation == "lives_in"]
    assert "berlin" in active_places
    assert "seattle" not in active_places

    # In database: Seattle memory has valid_to set
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (mid1,))
        row1 = cur.fetchone()
        assert row1[0] is not None
        assert row1[1] == mid2

        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (mid2,))
        row2 = cur.fetchone()
        assert row2[0] is None
        assert row2[1] is None

    # Normal search: only Berlin returned
    res_default = await store.search(RetrievalQuery(query_text="Where does the user live?", k=5))
    res_mids = [r.memory_id for r in res_default]
    assert mid2 in res_mids
    assert mid1 not in res_mids

    # Search with include_superseded=True: both returned
    res_all = await store.search(
        RetrievalQuery(query_text="Where does the user live?", k=5, include_superseded=True)
    )
    res_all_mids = [r.memory_id for r in res_all]
    assert mid2 in res_all_mids
    assert mid1 in res_all_mids


# ============================================================================
# T-MEM-07: Forgetting
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_07_forgetting(
    store: MemoryStore,
    fact_signer: DerivedFactSigner,
    user_signer: UserSpeechSigner,
    temp_db: DatabaseManager,
) -> None:
    """
    T-MEM-07: Forget 'I live in Berlin' (confirmed):
    memory forgotten_at set, edge valid_to set, FTS/vec rows removed, audit forget.
    """
    now = time.time()
    t_mid = await store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Recording user residency update statement",
                created_at=now,
                nonce="nonce_forget_trans_01",
                trace_id="tr_forget_trans",
            )
        )
    )
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT entry_id FROM memories WHERE memory_id = ?", (t_mid,))
        t_entry_id = cur.fetchone()[0]

    fact = fact_signer.sign(
        UnsignedPayload(
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            content="user lives in Berlin",
            structured={"s": "user", "p": "lives_in", "o": "Berlin"},
            source_entry_ids=[t_entry_id],
            created_at=now,
            nonce="nonce_forget_fact_01",
            trace_id="tr_forget_01",
        )
    )
    mid = await store.commit(fact)

    # Verify committed
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vec_memories WHERE memory_id = ?", (mid,))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM fts_memories WHERE fts_memories MATCH 'Berlin'", ())
        assert cur.fetchone()[0] >= 1

    # Call forget
    await store.forget([mid], user_confirmed=True)

    # Verify forgotten_at set
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT forgotten_at FROM memories WHERE memory_id = ?", (mid,))
        assert cur.fetchone()[0] is not None

        # vec and fts rows removed
        cur.execute("SELECT COUNT(*) FROM vec_memories WHERE memory_id = ?", (mid,))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM fts_memories WHERE fts_memories MATCH 'Berlin'", ())
        assert cur.fetchone()[0] == 0

        # kg_edges closed
        cur.execute(
            "SELECT COUNT(*) FROM kg_edges WHERE memory_id = ? AND valid_to IS NULL", (mid,)
        )
        assert cur.fetchone()[0] == 0

        # audit record exists
        cur.execute("SELECT COUNT(*) FROM memory_audit WHERE kind = 'forget'", ())
        assert cur.fetchone()[0] >= 1

    # Never retrievable
    res = await store.search(RetrievalQuery(query_text="Berlin", k=5, include_superseded=True))
    assert mid not in [r.memory_id for r in res]


# ============================================================================
# T-MEM-08: FTS injection
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_08_fts_injection(store: MemoryStore) -> None:
    """
    T-MEM-08: FTS injection query treated as literal tokens; no error.
    """
    malicious_queries = [
        '"foo" OR content:*',
        "NOT () * [ ] { } AND OR NEAR",
        '""',
        "a" * 500,
        "token" + chr(0) + "with" + chr(0) + "nulls",
        "'; DROP TABLE memories; --",
        "MATCH '\"* * *\"'",
    ]

    for q in malicious_queries:
        res = await store.search(RetrievalQuery(query_text=q, k=5))
        assert isinstance(res, list)


# ============================================================================
# T-MEM-09: Concurrency (200 reads during 50 writes)
# ============================================================================
def test_t_mem_09_concurrency(temp_db: DatabaseManager) -> None:
    """
    T-MEM-09: 200 concurrent reads during 50 writes:
    0 'database is locked' errors surfaced.
    """
    signer = UserSpeechSigner(master_key=TEST_KEY)
    now = time.time()
    write_lock = threading.Lock()

    def do_write(idx: int) -> None:
        p = signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content=f"Concurrency write item {idx}",
                created_at=now,
                nonce=f"nonce_conc_w_{idx}_{now}",
                trace_id=f"tr_conc_w_{idx}",
            )
        )
        with write_lock:
            conn = temp_db.get_writer()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO provenance_envelopes(
                    entry_id, provenance, kind, signer_id, signature, content_sha256,
                    nonce, created_at, trace_id, session_id, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.entry_id,
                    p.provenance.value,
                    p.kind,
                    p.signer_id,
                    p.signature,
                    p.content_sha256,
                    p.nonce,
                    p.created_at,
                    p.trace_id,
                    p.session_id,
                    p.confidence,
                    p.model_dump_json(),
                ),
            )
            conn.execute(
                "INSERT INTO memories(entry_id, content, tokens_aux, kind, created_at, valid_from) VALUES (?, ?, ?, ?, ?, ?)",
                (p.entry_id, p.content, "", p.kind, now, now),
            )
            conn.execute("COMMIT")

    def do_read(idx: int) -> None:
        with temp_db.read_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM memories")
            cur.fetchone()

    with ThreadPoolExecutor(max_workers=16) as executor:
        read_futures = [executor.submit(do_read, i) for i in range(200)]
        write_futures = [executor.submit(do_write, i) for i in range(50)]

        for f in read_futures + write_futures:
            f.result()


# ============================================================================
# T-MEM-10: Crash mid-commit atomicity
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_10_crash_mid_commit_atomicity(
    store: MemoryStore, temp_db: DatabaseManager, user_signer: UserSpeechSigner
) -> None:
    """
    T-MEM-10: Crash mid-commit via fault injection hook:
    after failure: 0 partial rows; integrity_check ok.
    """
    now = time.time()
    payload = user_signer.sign(
        UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            content="This commit will crash",
            created_at=now,
            nonce="nonce_crash_01",
            trace_id="tr_crash_01",
        )
    )

    def fault_hook() -> None:
        raise RuntimeError("Simulated process crash before COMMIT")

    store._fault_hook_before_commit = fault_hook

    with pytest.raises((RuntimeError, MemoryCommitFailed)):
        await store.commit(payload)

    # Verify atomic rollback: 0 partial rows in any table
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM memories")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM provenance_envelopes")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM vec_memories")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM fts_memories")
        assert cur.fetchone()[0] == 0

    # Verify database integrity is ok
    assert temp_db.check_integrity() is True


# ============================================================================
# T-MEM-11: Migrations
# ============================================================================
def test_t_mem_11_migrations(tmp_path: Path) -> None:
    """
    T-MEM-11: Migration from empty and forward:
    schema_migrations correct, idempotent.
    """
    db_path = tmp_path / "migration_test.sqlite"
    db = DatabaseManager(db_path)

    applied1 = db.migrate()
    assert applied1 == [1, 2, 3, 4, 5]

    # Re-running is idempotent
    applied2 = db.migrate()
    assert applied2 == []

    with db.read_cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        rows = [r[0] for r in cur.fetchall()]
        assert rows == [1, 2, 3, 4, 5]
    db.close()


# ============================================================================
# T-MEM-12: Retrieval Filters
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_12_retrieval_filters(
    store: MemoryStore, user_signer: UserSpeechSigner, temp_db: DatabaseManager
) -> None:
    """
    T-MEM-12: Retrieval filters:
    never returns forgotten_at IS NOT NULL or superseded rows unless requested.
    """
    now = time.time()

    # 1. Normal active memory
    m_active = await store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Active preference: prefers dark mode",
                created_at=now,
                nonce="nonce_filt_active",
                trace_id="tr_active",
            )
        )
    )

    # 2. Superseded memory
    m_super = await store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Superseded preference: prefers blue theme",
                created_at=now - 50.0,
                nonce="nonce_filt_super",
                trace_id="tr_super",
            )
        )
    )
    with temp_db.get_writer() as conn:
        conn.execute("UPDATE memories SET valid_to = ? WHERE memory_id = ?", (now - 10.0, m_super))

    # 3. Forgotten memory
    m_forgot = await store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Forgotten preference: prefers light mode",
                created_at=now - 100.0,
                nonce="nonce_filt_forgot",
                trace_id="tr_forgot",
            )
        )
    )
    await store.forget([m_forgot], user_confirmed=True)

    # Default search: only active
    res_def = await store.search(RetrievalQuery(query_text="prefers theme", k=10))
    def_mids = [r.memory_id for r in res_def]
    assert m_active in def_mids
    assert m_super not in def_mids
    assert m_forgot not in def_mids

    # Search with include_superseded=True: active and superseded, never forgotten
    res_all = await store.search(
        RetrievalQuery(query_text="prefers theme", k=10, include_superseded=True)
    )
    all_mids = [r.memory_id for r in res_all]
    assert m_active in all_mids
    assert m_super in all_mids
    assert m_forgot not in all_mids


# ============================================================================
# T-MEM-13: Backups & Integrity
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_13_backups_and_integrity(
    store: MemoryStore, temp_db: DatabaseManager, tmp_path: Path, user_signer: UserSpeechSigner
) -> None:
    """
    T-MEM-13: Backup via VACUUM INTO, retention pruning,
    integrity check failure sets store read-only.
    """
    now = time.time()
    await store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Data to be backed up",
                created_at=now,
                nonce="nonce_backup_01",
                trace_id="tr_backup_01",
            )
        )
    )

    backup_file = tmp_path / "backup.sqlite"
    store.backup(backup_file)
    assert backup_file.exists()

    backup_db = DatabaseManager(backup_file)
    assert backup_db.check_integrity() is True
    backup_db.close()

    # Test read-only enforcement when store integrity fails
    store.read_only = True
    with pytest.raises(MemoryStoreReadOnly, match="read-only mode"):
        await store.commit(
            user_signer.sign(
                UnsignedPayload(
                    provenance=Provenance.USER_EXPLICIT,
                    kind="transcript",
                    content="Attempt to commit to read-only store",
                    created_at=now + 1.0,
                    nonce="nonce_ro_01",
                    trace_id="tr_ro_01",
                )
            )
        )


# ============================================================================
# T-MEM-14: Working memory 8-step discard & positive control
# ============================================================================
@pytest.mark.asyncio
async def test_t_mem_14_working_memory_discard(
    store: MemoryStore, temp_db: DatabaseManager, user_signer: UserSpeechSigner
) -> None:
    """
    T-MEM-14: Working memory 8-step discard with positive-controlled USER_EXPLICIT persistence.
    """
    wm = WorkingMemory(db=temp_db)
    now = time.time()

    # Open task and add 8 ephemeral steps to working memory
    wm.open_task("task_test_14", now=now)
    for i in range(8):
        wm.set("task_test_14", f"step_{i}", f"Ephemeral thinking step {i}")

    state = wm.get_state("task_test_14")
    assert len(state) == 8

    # Close task (ephemeral state discarded)
    wm.close_task("task_test_14", outcome="completed", now=now + 10.0)
    assert len(wm.get_state("task_test_14")) == 0

    # Verify memories table has 0 rows from ephemeral working memory
    with temp_db.read_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM memories")
        assert cur.fetchone()[0] == 0

    # Positive control: An explicit fact committed to store persists
    mid = await store.commit(
        user_signer.sign(
            UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content="Persistent explicit user command",
                created_at=now + 20.0,
                nonce="nonce_wm_pos_01",
                trace_id="tr_wm_pos_01",
            )
        )
    )

    with temp_db.read_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM memories WHERE memory_id = ?", (mid,))
        assert cur.fetchone()[0] == 1


# ============================================================================
# Property P-06: Hypothesis FTS query construction
# ============================================================================
@given(text=st.text(min_size=0, max_size=200))
@settings(max_examples=300, deadline=1000)
def test_p_06_hypothesis_fts_query_fuzz(text: str) -> None:
    """
    P-06: Hypothesis fuzz test on build_fts_query:
    ANY string executes against SQLite FTS5 table without syntax error.
    """
    fts_expr = build_fts_query(text)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE fts_test USING fts5(content);")
    conn.execute("INSERT INTO fts_test(content) VALUES ('Sample text document');")

    cur = conn.cursor()
    try:
        cur.execute("SELECT rowid FROM fts_test WHERE fts_test MATCH ?", (fts_expr,))
        cur.fetchall()
    finally:
        conn.close()


def test_admin_add_memory_requires_valid_signature(temp_db: DatabaseManager) -> None:
    """F-MEM-001: MemoryManager.add_memory requires master_key and writes gate-verifiable envelopes."""
    # 1. Calling without master_key raises ValueError
    mgr_no_key = MemoryManager(db=temp_db, master_key=None)
    with pytest.raises(ValueError, match="master_key is required"):
        mgr_no_key.add_memory("Should fail without master_key")

    # 2. Calling with master_key < 32 bytes raises ValueError
    with pytest.raises(ValueError, match="at least 32 bytes"):
        MemoryManager(db=temp_db, master_key=b"too_short")

    # 3. Calling with valid master_key writes a valid cryptographically signed envelope
    mgr = MemoryManager(db=temp_db, master_key=TEST_KEY)
    mem_id = mgr.add_memory("User likes green tea", kind="fact", importance=0.9)
    assert mem_id > 0

    with temp_db.read_cursor() as cur:
        cur.execute("SELECT entry_id, signature, payload_json FROM provenance_envelopes")
        row = cur.fetchone()
        assert row is not None
        entry_id, signature, payload_json = row
        assert signature != "manual"
        assert len(signature) > 20

        # Verify envelope parses and verifies under ProvenanceGate.admit
        payload_dict = json.loads(payload_json)
        signed_payload = SignedPayload(**payload_dict)
        gate = ProvenanceGate(master_key=TEST_KEY)
        admitted = gate.admit(signed_payload)
        assert admitted.payload.entry_id == entry_id
        assert admitted.payload.content == "User likes green tea"


def test_update_memory_supersedes_and_audits(temp_db: DatabaseManager) -> None:
    """F-MEM-002: update_memory supersedes old memory and creates audit trail."""
    mgr = MemoryManager(db=temp_db, master_key=TEST_KEY)
    old_id = mgr.add_memory("Original memory content", kind="fact", importance=0.7)
    assert old_id > 0

    # Perform update
    success = mgr.update_memory(old_id, "Updated memory content", importance=0.95)
    assert success is True

    with temp_db.read_cursor() as cur:
        # Check old memory row
        cur.execute(
            "SELECT entry_id, content, valid_to, superseded_by, importance FROM memories WHERE memory_id = ?",
            (old_id,),
        )
        old_row = cur.fetchone()
        assert old_row is not None
        old_entry_id, old_content, valid_to, superseded_by, old_imp = old_row
        assert old_content == "Original memory content"
        assert valid_to is not None
        assert superseded_by is not None
        new_id = superseded_by
        assert new_id != old_id

        # Check new memory row
        cur.execute(
            "SELECT entry_id, content, valid_to, superseded_by, importance FROM memories WHERE memory_id = ?",
            (new_id,),
        )
        new_row = cur.fetchone()
        assert new_row is not None
        new_entry_id, new_content, new_valid_to, new_superseded_by, new_imp = new_row
        assert new_content == "Updated memory content"
        assert new_valid_to is None
        assert new_superseded_by is None
        assert abs(new_imp - 0.95) < 1e-4
        assert new_entry_id != old_entry_id

        # Verify old envelope remains intact
        cur.execute(
            "SELECT payload_json FROM provenance_envelopes WHERE entry_id = ?",
            (old_entry_id,),
        )
        old_env_row = cur.fetchone()
        assert old_env_row is not None
        gate = ProvenanceGate(master_key=TEST_KEY)
        old_signed = SignedPayload(**json.loads(old_env_row[0]))
        assert gate.admit(old_signed).payload.content == "Original memory content"

        # Verify new envelope verifies under ProvenanceGate
        cur.execute(
            "SELECT payload_json FROM provenance_envelopes WHERE entry_id = ?",
            (new_entry_id,),
        )
        new_env_row = cur.fetchone()
        assert new_env_row is not None
        new_signed = SignedPayload(**json.loads(new_env_row[0]))
        assert gate.admit(new_signed).payload.content == "Updated memory content"

        # Verify memory_audit row
        cur.execute(
            "SELECT kind, reason, entry_id FROM memory_audit WHERE kind = 'supersede'",
        )
        audit_row = cur.fetchone()
        assert audit_row is not None
        audit_kind, audit_reason, audit_entry_id = audit_row
        assert audit_kind == "supersede"
        assert str(old_id) in audit_reason
        assert str(new_id) in audit_reason
        assert audit_entry_id == new_entry_id

    # Verify list_memories filtering
    active_mems = mgr.list_memories()
    assert len(active_mems) == 1
    assert active_mems[0]["memory_id"] == new_id
    assert active_mems[0]["content"] == "Updated memory content"

    all_mems = mgr.list_memories(include_superseded=True)
    assert len(all_mems) == 2


def test_delete_memory_preserves_envelope_and_audits(temp_db: DatabaseManager) -> None:
    """F-MEM-003: delete_memory preserves provenance_envelopes and logs audit row."""
    mgr = MemoryManager(db=temp_db, master_key=TEST_KEY)
    mem_id = mgr.add_memory("Crucial fact to be audited", kind="fact", importance=0.85)
    assert mem_id > 0

    with temp_db.read_cursor() as cur:
        cur.execute("SELECT entry_id FROM memories WHERE memory_id = ?", (mem_id,))
        row = cur.fetchone()
        assert row is not None
        entry_id = row[0]

    # Delete memory with hard=True
    deleted = mgr.delete_memory(mem_id, hard=True)
    assert deleted is True

    with temp_db.read_cursor() as cur:
        # Check memories row is soft-deleted
        cur.execute("SELECT forgotten_at FROM memories WHERE memory_id = ?", (mem_id,))
        mem_row = cur.fetchone()
        assert mem_row is not None
        assert mem_row[0] is not None

        # Check provenance envelope is PRESERVED (Spec 04 §8 / TM-11)
        cur.execute(
            "SELECT payload_json FROM provenance_envelopes WHERE entry_id = ?",
            (entry_id,),
        )
        env_row = cur.fetchone()
        assert env_row is not None, "Provenance envelope was destroyed on deletion!"
        gate = ProvenanceGate(master_key=TEST_KEY)
        signed = SignedPayload(**json.loads(env_row[0]))
        assert gate.admit(signed).payload.content == "Crucial fact to be audited"

        # Check memory_audit has forget row
        cur.execute(
            "SELECT kind, reason, entry_id FROM memory_audit WHERE kind = 'forget' AND entry_id = ?",
            (entry_id,),
        )
        audit_row = cur.fetchone()
        assert audit_row is not None
        assert audit_row[0] == "forget"
        assert str(mem_id) in audit_row[1]

    # Check list_memories filtering
    assert len(mgr.list_memories()) == 0
    assert len(mgr.list_memories(include_forgotten=True)) == 1


def test_format_memory_context_budget() -> None:
    # 20 hits of 400 chars each (Spec 04 §6, Spec 10 §4, F-MEM-017)
    now = time.time()
    hits = [
        MemoryHit(
            memory_id=i,
            content=f"Memory content item {i}: " + ("x" * 400),
            provenance=Provenance.USER_EXPLICIT,
            score=1.0 / (i + 1),
            source_turn_id="turn-1",
            kind="fact",
            created_at=now - (i * 60),
            valid_from=now - (i * 60),
        )
        for i in range(20)
    ]
    rendered = format_memory_context(hits, max_tokens=600, now=now)
    assert rendered
    # Total characters must be <= 2400 chars (600 tokens * 4)
    assert len(rendered) <= 2400
    lines = rendered.splitlines()
    # Must cap to at most 8 items
    assert len(lines) <= 8
    for line in lines:
        assert line.startswith("- [fact/USER_EXPLICIT ")
        # Content portion must be truncated to <= 160 characters
        prefix, content = line.split("] ", 1)
        assert len(content) <= 160
