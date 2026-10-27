"""
WO-38 Phase 2 — Operator-gated corroboration requirement for USER_EXPLICIT Belnap grounding.

Covers the flag-gated grounding-eligibility decision shared by every write path
(``MemoryStore.commit`` and ``MemoryManager.add_memory`` / ``update_memory``):

- Flag OFF (default): frozen v1 behavior — USER_EXPLICIT is grounding-eligible on
  admission, preserving the Paper 1 Cohort C reproduction (Cohort C = 100.0%
  absorption measured with the flag off).
- Flag ON + uncorroborated USER_EXPLICIT: admitted (cryptographic gate untouched)
  but ``grounding_eligible = 0`` (Belnap-deferred), never dropped.
- Flag ON + corroborated USER_EXPLICIT: grounding-eligible = 1; corroboration must
  come from a non-USER_EXPLICIT grounding source, so a repeated user assertion
  never self-launders (Paper 1 self-poisoning semantics).
- TRAP 6: USER_DERIVED is unaffected by the flag.
- TRAP 7: corroboration lookup failures fail open (admission keeps v1 eligibility).
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from lucca.core.config import get_config
from lucca.core.schemas import Provenance, UnsignedPayload
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import resolve_grounding_eligible
from lucca.memory.manager import MemoryManager
from lucca.memory.signers import DerivedFactSigner, ToolResultSigner, UserSpeechSigner
from lucca.memory.store import MemoryStore

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "wo38_corroboration.sqlite"
    db = DatabaseManager(db_path=db_file)
    db.migrate()
    return db


@pytest.fixture
def mem_store(test_db: DatabaseManager) -> MemoryStore:
    return MemoryStore(db=test_db, master_key=TEST_MASTER_KEY, embedding_port=None)


def _set_flag(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    cfg = get_config()
    monkeypatch.setattr(cfg.memory, "user_explicit_requires_corroboration", value)


def _commit(
    store: MemoryStore,
    signer: UserSpeechSigner | ToolResultSigner | DerivedFactSigner,
    provenance: Provenance,
    content: str,
    source_entry_ids: list[str] | None = None,
) -> str:
    unsigned = UnsignedPayload(
        provenance=provenance,
        kind="fact",
        content=content,
        trace_id=f"wo38-{uuid.uuid4().hex[:8]}",
        session_id="wo38-session",
        created_at=time.time(),
        nonce=uuid.uuid4().hex,
        confidence=1.0,
        source_entry_ids=source_entry_ids or [],
    )
    signed = signer.sign(unsigned)
    store.commit(signed)
    return signed.entry_id


def _grounding_of(db: DatabaseManager, entry_id: str) -> int:
    with db.read_cursor() as cur:
        cur.execute(
            "SELECT grounding_eligible FROM provenance_envelopes WHERE entry_id = ?",
            (entry_id,),
        )
        row = cur.fetchone()
    assert row is not None, f"envelope missing for entry {entry_id}"
    return int(row[0])


def _memory_exists(db: DatabaseManager, entry_id: str) -> bool:
    with db.read_cursor() as cur:
        cur.execute(
            "SELECT valid_to FROM memories WHERE entry_id = ?",
            (entry_id,),
        )
        row = cur.fetchone()
    return row is not None and row[0] is None


def test_flag_off_preserves_frozen_grounding_eligibility(
    test_db: DatabaseManager, mem_store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag OFF: USER_EXPLICIT commits grounding-eligible exactly as in frozen v1."""
    _set_flag(monkeypatch, False)
    entry_id = _commit(
        mem_store, UserSpeechSigner(master_key=TEST_MASTER_KEY), Provenance.USER_EXPLICIT, "The user likes coffee"
    )
    assert _grounding_of(test_db, entry_id) == 1
    assert _memory_exists(test_db, entry_id)


def test_flag_on_uncorroborated_user_explicit_is_admitted_but_belnap_deferred(
    test_db: DatabaseManager, mem_store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag ON, no independent source: admitted (never dropped), grounding_eligible = 0."""
    _set_flag(monkeypatch, True)
    entry_id = _commit(
        mem_store,
        UserSpeechSigner(master_key=TEST_MASTER_KEY),
        Provenance.USER_EXPLICIT,
        "The capital of France is Berlin",
    )
    assert _grounding_of(test_db, entry_id) == 0
    assert _memory_exists(test_db, entry_id), "uncorroborated memory must be retained, not dropped"


def test_flag_on_corroborated_user_explicit_is_grounding_eligible(
    test_db: DatabaseManager, mem_store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag ON with a prior non-USER_EXPLICIT grounding fact of the same content: eligible = 1."""
    _set_flag(monkeypatch, True)
    claim = "The user's wedding anniversary is June 14"
    _commit(mem_store, ToolResultSigner(master_key=TEST_MASTER_KEY), Provenance.ASSISTANT_ACTION, claim)
    entry_id = _commit(
        mem_store, UserSpeechSigner(master_key=TEST_MASTER_KEY), Provenance.USER_EXPLICIT, claim
    )
    assert _grounding_of(test_db, entry_id) == 1


def test_flag_on_user_explicit_repeat_never_self_laundered(
    test_db: DatabaseManager, mem_store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prior USER_EXPLICIT row of the same content is NOT independent corroboration."""
    _set_flag(monkeypatch, True)
    claim = "The user's wedding anniversary is June 14"
    first = _commit(
        mem_store, UserSpeechSigner(master_key=TEST_MASTER_KEY), Provenance.USER_EXPLICIT, claim
    )
    assert _grounding_of(test_db, first) == 0
    second = _commit(
        mem_store, UserSpeechSigner(master_key=TEST_MASTER_KEY), Provenance.USER_EXPLICIT, claim
    )
    assert _grounding_of(test_db, second) == 0, "repeated user assertion must not self-corroborate"


def test_flag_on_does_not_affect_user_derived(
    test_db: DatabaseManager, mem_store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TRAP 6: the flag gates USER_EXPLICIT only; USER_DERIVED keeps frozen class eligibility."""
    _set_flag(monkeypatch, True)
    source = _commit(
        mem_store, UserSpeechSigner(master_key=TEST_MASTER_KEY), Provenance.USER_EXPLICIT, "Meeting moved to Friday"
    )
    derived = _commit(
        mem_store,
        DerivedFactSigner(master_key=TEST_MASTER_KEY),
        Provenance.USER_DERIVED,
        "The meeting was rescheduled to Friday",
        source_entry_ids=[source],
    )
    assert _grounding_of(test_db, derived) == 1


def test_flag_on_corroboration_lookup_failure_fails_open(
    test_db: DatabaseManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TRAP 7: with no usable DB handle the lookup passes and v1 eligibility is kept."""
    _set_flag(monkeypatch, True)
    assert resolve_grounding_eligible(Provenance.USER_EXPLICIT, "any claim", None) == 1


def test_manager_add_memory_respects_flag(
    test_db: DatabaseManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The administrative write path shares the same flag-gated decision."""
    _set_flag(monkeypatch, True)
    mgr = MemoryManager(db=test_db, master_key=TEST_MASTER_KEY)
    memory_id = mgr.add_memory("The user's dog is named Rex", kind="fact")
    with test_db.read_cursor() as cur:
        cur.execute(
            "SELECT e.grounding_eligible FROM memories m "
            "JOIN provenance_envelopes e ON m.entry_id = e.entry_id "
            "WHERE m.memory_id = ?",
            (memory_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert int(row[0]) == 0
