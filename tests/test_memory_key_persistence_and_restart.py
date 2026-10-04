"""
Tests key persistence across restarts and behavior when restarting with a mismatched key.
Verifies that:
1. resolve_or_create_master_key persists the generated key to disk.
2. On second boot, reading the disk key matches the original key.
3. If an adversary or key-rotation changes the key, old memories fail HMAC check,
   are safely quarantined into SQLite `memory_quarantine` table, user warning is issued,
   and retrieval succeeds for uncorrupted memories rather than crashing.
"""

import hashlib
import time
from pathlib import Path

import pytest

from lucca.core.config import LuccaConfig, resolve_or_create_master_key
from lucca.core.schemas import Provenance, RetrievalQuery, UnsignedPayload
from lucca.memory.db import DatabaseManager
from lucca.memory.retrieval import HybridRetriever
from lucca.memory.signers import create_user_speech_signer
from lucca.memory.store import MemoryStore


def test_key_persistence_on_disk(tmp_path: Path):
    """Key is persisted to data/keys/master.key and reloaded identically across restarts."""
    key_dir = tmp_path / "data" / "keys"
    
    # 1. First resolution: file doesn't exist -> generates and saves
    key1 = resolve_or_create_master_key(key_dir=key_dir)
    assert len(key1) == 32
    key_file = key_dir / "master.key"
    assert key_file.exists()
    assert key_file.read_bytes() == key1

    # 2. Second resolution (simulating restart): reads persisted key from disk
    key2 = resolve_or_create_master_key(key_dir=key_dir)
    assert key2 == key1


def test_restart_with_mismatched_key_quarantines_and_warns(tmp_path: Path):
    """When a database is opened with a rotated/different key:
    - Tampered/mismatched rows are quarantined to the SQLite memory_quarantine table.
    - Quarantined memories are excluded from search results.
    - User warning is accumulated.
    - Retrieval does not crash with RuntimeError.
    """
    db_path = tmp_path / "memory.sqlite"
    db = DatabaseManager(str(db_path))
    db.migrate()

    # Session 1: Seed memory signed with Key A
    key_a = b"KEY_AAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # 32 bytes
    store_a = MemoryStore(db=db, master_key=key_a)
    signer_a = create_user_speech_signer(master_key=key_a)

    now = time.time()
    payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="fact",
        content="The user's favorite editor is Neovim.",
        nonce="nonce-key-test-01",
        created_at=now,
        trace_id="trace-key-test-01",
    )
    env = signer_a.sign(payload)
    mid = store_a.commit(env, now=now)

    # Verify Session 1 retrieval works with Key A
    retriever_a = HybridRetriever(db=db, master_key=key_a)
    hits = retriever_a.search(RetrievalQuery(query_text="editor", top_k=5))
    assert len(hits) == 1
    assert hits[0].memory_id == mid

    # Session 2: "Restart" with Key B (mismatched key)
    key_b = b"KEY_BBBBBBBBBBBBBBBBBBBBBBBBBBBB"  # 32 bytes
    retriever_b = HybridRetriever(db=db, master_key=key_b, raise_on_tamper=False)

    # Retrieval must NOT crash
    hits_b = retriever_b.search(RetrievalQuery(query_text="editor", top_k=5))
    assert len(hits_b) == 0  # Row quarantined

    # Verify DB quarantine table persistence
    quarantined = retriever_b.get_persisted_quarantine_records()
    assert len(quarantined) == 1
    assert quarantined[0]["memory_id"] == mid
    assert quarantined[0]["stage"] == "hmac_or_sha256"

    # Verify user-facing warning
    assert len(retriever_b.user_integrity_warnings) >= 1
    assert f"Memory record {mid} failed cryptographic verification" in retriever_b.user_integrity_warnings[0]

    # Session 3: Reboot / instantiate fresh retriever
    # Verifies requirement 2: Persist quarantine list in DB instead of memory only
    retriever_c = HybridRetriever(db=db, master_key=key_b, raise_on_tamper=False)
    assert mid in retriever_c.quarantined_memory_ids
    assert retriever_c.get_integrity_status_report() == "Security notice: 1 memory failed cryptographic integrity checks and were quarantined."

    # Commit a new valid memory under key_b
    store_b = MemoryStore(db=db, master_key=key_b)
    signer_b = create_user_speech_signer(master_key=key_b)
    payload_b = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="fact",
        content="The user's favorite editor is Emacs.",
        nonce="nonce-key-test-02",
        created_at=now + 10,
        trace_id="trace-key-test-02",
    )
    env_b = signer_b.sign(payload_b)
    mid_b = store_b.commit(env_b, now=now + 10)

    # Retrieval in Session 3: only valid new memory returned, old quarantined stays excluded
    hits_c = retriever_c.search(RetrievalQuery(query_text="editor", top_k=5))
    assert len(hits_c) == 1
    assert hits_c[0].memory_id == mid_b
    assert hits_c[0].content == "The user's favorite editor is Emacs."

