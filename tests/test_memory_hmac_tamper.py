"""
HMAC Tamper Test — verifies real HMAC verification at read-time in HybridRetriever.

Tests:
  1. Clean row → passes through
  2. Naive tamper (content changed only) → caught by Stage 1 (content_sha256)
  3. Sophisticated tamper (content+sha256 both updated, sig not forged) → caught by Stage 2 (HMAC)
  4. Stage 2 tamper without master_key → NOT caught (documented dev-mode limitation)

Run with:
    uv run pytest tests/test_memory_hmac_tamper.py -v --tb=short
"""

import base64
import hashlib
import hmac
import json
import tempfile
import time
from pathlib import Path

import pytest

from lucca.core.schemas import Provenance, RetrievalQuery, UnsignedPayload
from lucca.memory.db import DatabaseManager
from lucca.memory.retrieval import HybridRetriever
from lucca.memory.signers import create_user_speech_signer, derive_provenance_key
from lucca.memory.store import MemoryStore

MASTER_KEY = b"test_hmac_tamper_key_32bytes_xxx!"  # exactly 32 bytes


@pytest.fixture()
def seeded_store(tmp_path: Path):
    """Create a MemoryStore with one properly-signed memory row, using the real signer."""
    db_path = tmp_path / "test.db"
    db = DatabaseManager(str(db_path))
    db.migrate()

    store = MemoryStore(db=db, master_key=MASTER_KEY)
    signer = create_user_speech_signer(master_key=MASTER_KEY)

    now = time.time()
    payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="fact",
        content="The secret project name is Meridian.",
        nonce="nonce-hmac-test-001",
        created_at=now,
        trace_id="trace-hmac-001",
    )
    envelope = signer.sign(payload)
    store.commit(envelope, now=now)

    # Return (store, db) so tests can tamper via db.get_writer()
    return store, db


def _retriever(db) -> HybridRetriever:
    return HybridRetriever(db=db, master_key=MASTER_KEY)


def _retriever_no_key(db) -> HybridRetriever:
    return HybridRetriever(db=db, master_key=None)



# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — clean row passes through
# ──────────────────────────────────────────────────────────────────────────────

def test_clean_row_retrieves_successfully(seeded_store):
    """A correctly signed row must not trigger an integrity error."""
    store, db = seeded_store
    retriever = _retriever(db)
    q = RetrievalQuery(query_text="secret project name", top_k=5)
    try:
        retriever.search(q)
    except RuntimeError as e:
        pytest.fail(f"Clean row raised integrity error unexpectedly: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — Stage 1: naive tamper (content changed, envelope untouched)
# ──────────────────────────────────────────────────────────────────────────────

def test_naive_tamper_caught_by_stage1(seeded_store):
    """Stage 1 (content_sha256) catches a tamper that changes content but not the hash."""
    store, db = seeded_store

    with db.get_writer() as conn:
        conn.execute(
            "UPDATE memories SET content='OVERWRITTEN' WHERE content LIKE '%Meridian%'"
        )
        conn.commit()

    retriever = _retriever(db)
    # Use a word that's in the FTS index (indexed before the tamper) so the row IS found
    q = RetrievalQuery(query_text="Meridian", top_k=5)
    with pytest.raises(RuntimeError, match="integrity violation"):
        retriever.search(q)


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — Stage 2: sophisticated tamper (content + sha256 both updated, sig not forged)
# ──────────────────────────────────────────────────────────────────────────────

def test_sophisticated_tamper_caught_by_hmac(seeded_store):
    """Stage 2 (HMAC) catches a tamper that updates both content and content_sha256
    but cannot forge the signature (attacker lacks master_key)."""
    store, db = seeded_store

    tampered = "The secret project name is FORGED."
    new_sha = hashlib.sha256(tampered.encode("utf-8")).hexdigest()

    with db.get_writer() as conn:
        conn.execute(
            "UPDATE memories SET content=? WHERE content LIKE '%Meridian%'",
            (tampered,),
        )
        conn.execute(
            "UPDATE provenance_envelopes SET content_sha256=? "
            "WHERE entry_id=(SELECT entry_id FROM memories WHERE content=?)",
            (new_sha, tampered),
        )
        conn.commit()

    retriever = _retriever(db)
    q = RetrievalQuery(query_text="secret project name", top_k=5)
    with pytest.raises(RuntimeError, match="integrity violation"):
        retriever.search(q)


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — no master_key: Stage 2 tamper passes (documented dev-mode limitation)
# ──────────────────────────────────────────────────────────────────────────────

def test_tamper_not_caught_without_master_key(seeded_store):
    """Without a master_key only Stage 1 runs. A Stage 2 tamper (content+sha256 both
    updated) will NOT be caught. Documents the expected dev-mode limitation."""
    store, db = seeded_store

    tampered = "Stage 2 bypass because no master_key."
    new_sha = hashlib.sha256(tampered.encode("utf-8")).hexdigest()

    with db.get_writer() as conn:
        conn.execute(
            "UPDATE memories SET content=? WHERE content LIKE '%Meridian%'",
            (tampered,),
        )
        conn.execute(
            "UPDATE provenance_envelopes SET content_sha256=? "
            "WHERE entry_id=(SELECT entry_id FROM memories WHERE content=?)",
            (new_sha, tampered),
        )
        conn.commit()

    retriever = _retriever_no_key(db)
    q = RetrievalQuery(query_text="secret project name", top_k=5)
    try:
        retriever.search(q)
    except RuntimeError as e:
        pytest.fail(f"Without master_key Stage 2 tamper should not raise but got: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Test 5 — Stage 2: attacker updates content, sha256, AND payload_json
# ──────────────────────────────────────────────────────────────────────────────

def test_forged_payload_json_caught_by_hmac(seeded_store):
    """If attacker updates memories.content, envelope.content_sha256, AND
    envelope.payload_json to match the forged text, HMAC recomputation
    over the tampered payload_json fails to match the original signature."""
    store, db = seeded_store

    tampered = "The secret project name is FORGED_IN_PAYLOAD."
    new_sha = hashlib.sha256(tampered.encode("utf-8")).hexdigest()

    # Read existing payload_json, update its content field
    with db.get_writer() as conn:
        row = conn.execute(
            "SELECT payload_json FROM provenance_envelopes WHERE entry_id="
            "(SELECT entry_id FROM memories WHERE content LIKE '%Meridian%')"
        ).fetchone()
        payload_data = json.loads(row[0])
        payload_data["content"] = tampered
        tampered_payload_json = json.dumps(payload_data)

        conn.execute(
            "UPDATE memories SET content=? WHERE content LIKE '%Meridian%'",
            (tampered,),
        )
        conn.execute(
            "UPDATE provenance_envelopes SET content_sha256=?, payload_json=? "
            "WHERE entry_id=(SELECT entry_id FROM memories WHERE content=?)",
            (new_sha, tampered_payload_json, tampered),
        )
        conn.commit()

    retriever = _retriever(db)
    q = RetrievalQuery(query_text="secret project name", top_k=5)
    with pytest.raises(RuntimeError, match="integrity violation"):
        retriever.search(q)

