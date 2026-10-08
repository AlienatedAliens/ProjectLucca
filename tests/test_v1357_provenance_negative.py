"""
Negative test fixture for v1.35.7 Phase 4: Distillation Provenance Invariants.
Spec 03 §5, ADR-006, Gates: G-V1357-DISTILL, D-MEM-05 quarantine retention.
"""

import os
import sqlite3
from unittest.mock import MagicMock

import pytest

from lucca.core.schemas import (
    LLMNarration,
    Provenance,
    UnsignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import ProvenanceGate, ProvenanceRejected
from lucca.memory.signers import DerivedFactSigner
from lucca.reasoning.distill import (
    DistilledProposition,
    distill_contradiction_to_proposition,
    quarantine_rejected_distillate,
    sign_distilled_proposition,
)


@pytest.fixture
def master_key() -> bytes:
    return b"test_master_key_must_be_32_bytes_long_now!!"


@pytest.fixture
def gate(master_key: bytes) -> ProvenanceGate:
    return ProvenanceGate(master_key=master_key)


@pytest.fixture
def test_db(tmp_path: object) -> DatabaseManager:
    db_file = str(tmp_path) + "/test_quarantine.sqlite"
    return DatabaseManager(db_path=db_file)


def test_unsigned_distillate_rejected_by_provenance_gate(
    gate: ProvenanceGate,
) -> None:
    """
    Negative fixture: Asserts that an unsigned distillate or raw LLMNarration
    is unconditionally rejected by ProvenanceGate (ADR-006 / Spec 03).
    """
    # 1. Distill an utterance with conversational filler
    distilled = distill_contradiction_to_proposition(
        old_content="User prefers tabs",
        new_content="Actually, you know, I always use spaces for indentation.",
        topic="code_style",
    )
    assert "Actually" not in distilled.canonical_proposition
    assert "you know" not in distilled.canonical_proposition
    assert distilled.canonical_proposition.startswith("The user always uses spaces")

    # 2. Raw LLMNarration must be rejected unconditionally
    raw_narration = LLMNarration(
        text=distilled.canonical_proposition,
        trace_id="test-narration",
    )
    with pytest.raises(ProvenanceRejected, match="LLM_NARRATION is forbidden from entering memory"):
        gate.admit(raw_narration)

    # 3. An unsigned payload object must be rejected
    unsigned = UnsignedPayload(
        provenance=Provenance.USER_DERIVED,
        kind="belief",
        content=distilled.canonical_proposition,
        created_at=1000.0,
        nonce="testnonce12345678",
    )
    with pytest.raises(ProvenanceRejected, match="Expected SignedPayload"):
        gate.admit(unsigned)  # type: ignore[arg-type]


def test_signed_distillate_admitted_by_provenance_gate(
    gate: ProvenanceGate,
    master_key: bytes,
) -> None:
    """
    Positive control: Once signed by DerivedFactSigner, the proposition
    is cryptographically verified and admitted by ProvenanceGate.
    """
    distilled = DistilledProposition(
        topic="api_support",
        canonical_proposition="The API does not support endpoint v1.",
        polarity="TRUE",
        confidence=0.95,
    )
    signer = DerivedFactSigner(master_key=master_key)
    signed = sign_distilled_proposition(
        distilled=distilled,
        signer=signer,
        source_entry_ids=["entry-123", "entry-456"],
    )

    admitted = gate.admit(signed)
    assert admitted.payload.entry_id == signed.entry_id
    assert admitted.payload.provenance == Provenance.USER_DERIVED


def test_rejected_distillate_persisted_to_quarantine_table(
    test_db: DatabaseManager,
) -> None:
    """
    D-MEM-05 Retention Invariant:
    Rejected distillates are never silently dropped; they must be written
    to the memory_quarantine table with their failure reason for lucca-admin audit.
    """
    quarantine_rejected_distillate(
        db=test_db,
        entry_id="distill-entry-rejected-001",
        reason="ProvenanceRejected: unsigned LLM proposition",
        stage="post_turn_distillation",
    )

    with test_db.read_cursor() as cur:
        cur.execute("SELECT entry_id, reason, stage FROM memory_quarantine WHERE entry_id = ?", ("distill-entry-rejected-001",))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "distill-entry-rejected-001"
        assert "ProvenanceRejected" in row[1]
        assert row[2] == "post_turn_distillation"
