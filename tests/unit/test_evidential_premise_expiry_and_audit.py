"""End-to-end unit tests for wall-clock premise expiration (valid_until),
pre-tool SpeculativeBDIValidator freshness enforcement, Belnap BOT vs. TOP
distinction, and Ed25519 public-key-verifiable reviewer audit receipts.

Models the industrial hot-work permit + expired gas reading scenario:
- Permit stands (valid_until = t0 + 8h), gas reading expires (valid_until = t0 + 30m)
  with no newer reading arriving to contradict or supersede it (superseded_by IS NULL).
- Evaluates to Belnap BOT / NEITHER (epistemic gap), NOT Belnap TOP / BOTH (contradiction).
- Hard-blocks candidate tool dispatch in SpeculativeBDIValidator before sandbox execution.
- Commits an Ed25519-signed negative action_receipt (ok=False) foreign-keyed via
  memory_sources to both the standing permit envelope and the expired gas-reading envelope.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import JsonValue

from lucca.core.affect import AffectTracker
from lucca.core.bdi_validator import DeonticNorm, SpeculativeBDIValidator
from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.coherence import ToolReceipt
from lucca.core.memory_commit_service import MemoryCommitService
from lucca.core.schemas import (
    Provenance,
    RetrievalQuery,
    SignedPayload,
    ToolCall,
    ToolResult,
    UnsignedPayload,
)
from lucca.core.signer_factory import SignerFactory
from lucca.core.tool_dispatcher import ToolDispatcher
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.latent_probe import BelnapValue
from lucca.memory.retrieval import HybridRetriever
from lucca.memory.signers import canonicalize_unsigned_payload
from lucca.memory.store import MemoryStore
from lucca.memory.tokens import derive_ed25519_public_key, verify_provenance_signature
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"0123456789abcdef0123456789abcdef"


class _MutableClock:
    def __init__(self, initial: float) -> None:
        self.t = initial

    def now_utc(self) -> float:
        return self.t


class _CountingSandbox:
    def __init__(self) -> None:
        self.taint_flags = 0
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []

    def check_confirmation_needed(self, tool_name: str) -> bool:  # noqa: ARG002
        return False

    def execute_tool(
        self,
        *,
        call_id: str,
        tool_name: str,
        args: dict[str, JsonValue],
        confirmed: bool = True,  # noqa: ARG002
        human_confirmed: bool = False,  # noqa: ARG002
    ) -> ToolResult:
        self.calls.append((tool_name, dict(args)))
        return ToolResult(
            call_id=call_id,
            ok=True,
            exit_code=0,
            content=f"executed {tool_name}",
            elapsed_ms=1.0,
        )


class _MinimalOrchestratorHarness:
    """Minimal strictly typed orchestrator harness wiring real ToolDispatcher,
    SpeculativeBDIValidator, MemoryStore, and MemoryCommitService.
    """

    def __init__(
        self,
        *,
        db: DatabaseManager,
        store: MemoryStore,
        signer_factory: SignerFactory,
        clock: _MutableClock,
        workspace_root: Path,
    ) -> None:
        self.db = db
        self.memory_store = store
        self.signer_factory = signer_factory
        self.clock = clock
        self.rule_engine = RuleLifecycleManager(db=db)
        self.sandbox = _CountingSandbox()
        self.bdi_validator = SpeculativeBDIValidator(
            workspace_root=workspace_root,
            db=db,
            clock_fn=clock.now_utc,
        )
        self.affect_tracker = AffectTracker()
        self.action_signer = signer_factory.tool_result()
        self.execute_tools = True
        self.executed_tools: list[tuple[str, dict[str, JsonValue]]] = []
        self.current_turn_tool_calls: list[ToolCall] = []
        self.current_turn_receipts: list[ToolReceipt] = []
        self.current_turn_tool_spoken: list[str] = []
        self.current_turn_tool_ok = True
        self.current_turn_transcript: str | None = None
        self.history: list[dict[str, str]] = []
        self.commits = MemoryCommitService(
            memory_store=store,
            signer_factory=signer_factory,
            clock=clock,  # type: ignore[arg-type]
            orchestrator=self,  # type: ignore[arg-type]
        )
        self.dispatcher = ToolDispatcher(self)  # type: ignore[arg-type]

    def _speak_text(self, trace: TurnTrace, text: str) -> None:  # noqa: ARG002
        return None

    def _record_tool_receipt(
        self,
        name: str,
        call_id: str,
        args: dict[str, JsonValue],
        ok: bool,
        output: str | None = None,
        error: str | None = None,
        source_entry_ids: list[str] | None = None,
        precondition_audit: list[dict[str, JsonValue]] | None = None,
    ) -> None:
        self.current_turn_receipts.append(
            ToolReceipt(
                tool=name,
                tool_name=name,
                ok=ok,
                call_id=call_id,
                args=dict(args),
                output=output,
                error=error,
                timestamp=self.clock.now_utc(),
                source_entry_ids=list(source_entry_ids) if source_entry_ids else [],
                precondition_audit=list(precondition_audit) if precondition_audit else [],
            )
        )


def _commit_tool_verified_state_fact(
    *,
    store: MemoryStore,
    signer_factory: SignerFactory,
    subject: str,
    predicate: str,
    obj_val: str,
    created_at: float,
    valid_until: float | None,
    trace_id: str,
) -> SignedPayload:
    tool_signer = signer_factory.tool_result()
    structured: dict[str, JsonValue] = {
        "s": subject,
        "p": predicate,
        "o": obj_val,
        "valid_from": created_at,
    }
    if valid_until is not None:
        structured["valid_until"] = valid_until
    unsigned = UnsignedPayload(
        provenance=Provenance.TOOL_VERIFIED,
        kind="tool_fact",
        content=f"{subject} {predicate} {obj_val}",
        structured=structured,
        created_at=created_at,
        nonce=os.urandom(16).hex(),
        trace_id=trace_id,
        confidence=1.0,
    )
    signed = tool_signer.sign(unsigned)
    store.commit(signed, now=created_at)
    return signed


def test_hot_work_permit_stands_but_gas_reading_expires_blocks_tool_and_binds_audit_receipt(
    tmp_path: Path,
) -> None:
    """Proves end-to-end handling when a standing permit remains valid (8h TTL)
    while a gas reading expires (30m TTL) with zero newer readings to contradict it.
    """
    t0 = 1_700_000_000.0
    clock = _MutableClock(t0)
    db = DatabaseManager(tmp_path / "hot_work_audit.sqlite")
    db.migrate()
    embedder = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=embedder)
    retriever = HybridRetriever(db=db, embedder=embedder, master_key=TEST_MASTER_KEY)
    signer_factory = SignerFactory(master_key=TEST_MASTER_KEY)
    orch = _MinimalOrchestratorHarness(
        db=db,
        store=store,
        signer_factory=signer_factory,
        clock=clock,
        workspace_root=tmp_path / "workspace",
    )

    # 1. At t0: Commit 8-hour standing hot-work permit and 30-minute gas reading
    permit_signed = _commit_tool_verified_state_fact(
        store=store,
        signer_factory=signer_factory,
        subject="bay_4",
        predicate="hot_work_permit",
        obj_val="PERMIT-2026-884",
        created_at=t0,
        valid_until=t0 + 28_800.0,  # 8 hours
        trace_id="tr-init-permit",
    )
    gas_signed = _commit_tool_verified_state_fact(
        store=store,
        signer_factory=signer_factory,
        subject="bay_4",
        predicate="gas_reading",
        obj_val="0.0_pct_LEL",
        created_at=t0,
        valid_until=t0 + 1_800.0,  # 30 minutes
        trace_id="tr-init-gas",
    )

    # Register MicroScheme deontic precondition requiring both facts to be fresh
    precond_sexpr = (
        '(and (fresh-fact? "bay_4" "hot_work_permit") '
        '(fresh-fact? "bay_4" "gas_reading"))'
    )

    # 2. At t0 + 10 min (600s): Both permit and gas reading are fresh -> PERMITTED
    clock.t = t0 + 600.0
    trace_ok = TurnTrace(trace_id="tr-10min-ok", session_id="s1", origin="text", mode="transcript")
    res_ok = orch.dispatcher.handle_tool_call(
        trace_ok,
        "write_file",
        {
            "path": "weld_log.txt",
            "content": "pass 1",
            "_preconditions": precond_sexpr,
        },
        speak=False,
    )
    assert res_ok is not None
    assert res_ok.ok is True
    assert len(orch.sandbox.calls) == 1
    assert "_preconditions" not in orch.sandbox.calls[0][1]
    orch.commits.commit_action_receipts(trace_ok)

    # 3. Advance clock to t0 + 57 min (3,420s):
    #    - Permit stands (valid_until = t0 + 28,800 > t_stale)
    #    - Gas reading expired (valid_until = t0 + 1,800 <= t_stale)
    #    - NO newer gas reading arrived (superseded_by IS NULL, valid_to IS NULL)
    t_stale = t0 + 3_420.0
    clock.t = t_stale

    # 3a. Active retrieval excludes expired gas reading while retaining standing permit
    gas_hits = retriever.search(RetrievalQuery(query_text="bay_4 gas_reading"), now=t_stale)
    assert [h for h in gas_hits if "gas_reading" in h.content] == []
    permit_hits = retriever.search(
        RetrievalQuery(query_text="bay_4 hot_work_permit"), now=t_stale
    )
    assert any(h.content.startswith("bay_4 hot_work_permit") for h in permit_hits)

    # 3b. EpistemicSearchCascade resolves zero active gas readings to Belnap BOT (not TOP!)
    cascade = EpistemicSearchCascade(memory_store=store)
    belnap_val, _, refusal = cascade.synthesize(
        query_text="bay_4 gas_reading",
        evidence=[],
        topic="bay_4 gas_reading",
    )
    assert belnap_val == BelnapValue.NEITHER == "BOT"
    assert refusal is not None

    # 3c. Attempt candidate tool call -> hard pre-tool block BEFORE sandbox execution
    trace_blk = TurnTrace(trace_id="tr-57min-blocked", session_id="s1", origin="text", mode="transcript")
    res_blk = orch.dispatcher.handle_tool_call(
        trace_blk,
        "write_file",
        {
            "path": "weld_log.txt",
            "content": "pass 2 after expiry",
            "_preconditions": precond_sexpr,
        },
        speak=False,
    )
    assert res_blk is not None
    assert res_blk.ok is False
    assert res_blk.exit_code == -4
    # Sandbox execution count MUST remain 1 (never invoked on the blocked turn)
    assert len(orch.sandbox.calls) == 1
    assert "EXPIRED [Belnap BOT]" in (res_blk.stderr or "")
    assert gas_signed.entry_id in (res_blk.stderr or "")

    orch.commits.commit_action_receipts(trace_blk)

    # 4. External Reviewer Verification (Public Key + SQLite Audit Lineage Only)
    action_pub_key = derive_ed25519_public_key(TEST_MASTER_KEY, Provenance.ASSISTANT_ACTION)
    tool_fact_pub_key = derive_ed25519_public_key(TEST_MASTER_KEY, Provenance.TOOL_VERIFIED)

    with db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.memory_id, p.entry_id, p.signature, p.payload_json
            FROM memories m
            JOIN provenance_envelopes p ON m.entry_id = p.entry_id
            WHERE p.trace_id = ? AND p.kind = 'action_receipt'
            """,
            ("tr-57min-blocked",),
        )
        receipt_row = cur.fetchone()
        assert receipt_row is not None
        receipt_mem_id = int(receipt_row["memory_id"])
        receipt_sig = str(receipt_row["signature"])
        receipt_payload = SignedPayload.model_validate_json(str(receipt_row["payload_json"]))

        # 4a. Reviewer verifies Ed25519 signature using ONLY the public key
        assert verify_provenance_signature(
            receipt_sig,
            canonicalize_unsigned_payload(receipt_payload),
            Provenance.ASSISTANT_ACTION,
            public_key=action_pub_key,
            allow_legacy_hmac=False,
        )

        # 4b. Reviewer checks memory_sources foreign-key links to exact inspected envelopes
        cur.execute(
            "SELECT source_entry_id FROM memory_sources WHERE memory_id = ? ORDER BY rowid",
            (receipt_mem_id,),
        )
        fk_sources = {str(r[0]) for r in cur.fetchall()}
        assert fk_sources == {permit_signed.entry_id, gas_signed.entry_id}

        # 4c. Reviewer inspects structured precondition_audit inside signed envelope
        assert receipt_payload.structured is not None
        assert receipt_payload.structured["ok"] is False
        audit_list = receipt_payload.structured["precondition_audit"]
        assert isinstance(audit_list, list) and len(audit_list) == 2
        by_pred = {
            str(item["predicate"]): item for item in audit_list if isinstance(item, dict)
        }

        permit_audit = by_pred["hot_work_permit"]
        assert permit_audit["status"] == "VALID"
        assert permit_audit["belnap_state"] == "T"
        assert permit_audit["entry_id"] == permit_signed.entry_id
        assert permit_audit["valid_until"] == t0 + 28_800.0
        assert permit_audit["checked_at"] == t_stale

        gas_audit = by_pred["gas_reading"]
        assert gas_audit["status"] == "EXPIRED"
        assert gas_audit["belnap_state"] == "BOT"
        assert gas_audit["entry_id"] == gas_signed.entry_id
        assert gas_audit["valid_until"] == t0 + 1_800.0
        assert gas_audit["checked_at"] == t_stale
        assert gas_audit["superseded_by"] is None

        # 4d. Reviewer independently verifies Ed25519 signature of the cited gas_reading envelope
        cur.execute(
            "SELECT signature, payload_json FROM provenance_envelopes WHERE entry_id = ?",
            (gas_signed.entry_id,),
        )
        gas_env_row = cur.fetchone()
        assert gas_env_row is not None
        gas_env_payload = SignedPayload.model_validate_json(str(gas_env_row["payload_json"]))
        assert verify_provenance_signature(
            str(gas_env_row["signature"]),
            canonicalize_unsigned_payload(gas_env_payload),
            Provenance.TOOL_VERIFIED,
            public_key=tool_fact_pub_key,
            allow_legacy_hmac=False,
        )
        assert json.loads(str(gas_env_row["payload_json"]))["structured"]["o"] == "0.0_pct_LEL"


def test_belnap_top_conflict_vs_bot_expired_and_renewal_recovery(tmp_path: Path) -> None:
    """Proves SpeculativeBDIValidator distinguishes:
    1. Conflicting live readings -> status='CONFLICT', belnap_state=BelnapValue.BOTH ('TOP')
    2. Expired unreplaced reading -> status='EXPIRED', belnap_state=BelnapValue.NEITHER ('BOT')
    3. Fresh replacement reading -> status='VALID', belnap_state=BelnapValue.TRUE ('T')
    """
    t0 = 1_700_100_000.0
    clock = _MutableClock(t0)
    db = DatabaseManager(tmp_path / "belnap_distinction.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    signer_factory = SignerFactory(master_key=TEST_MASTER_KEY)
    validator = SpeculativeBDIValidator(
        workspace_root=tmp_path,
        db=db,
        clock_fn=clock.now_utc,
    )
    validator.register_tool_premises("run_python", [("vessel_2", "gas_reading")])

    # 1. Two opposing live TOOL_VERIFIED sensor readings (neither superseded) -> Belnap TOP
    _commit_tool_verified_state_fact(
        store=store,
        signer_factory=signer_factory,
        subject="vessel_2",
        predicate="gas_reading",
        obj_val="0.0_pct_LEL",
        created_at=t0,
        valid_until=t0 + 600.0,
        trace_id="tr-sensor-a",
    )
    _commit_tool_verified_state_fact(
        store=store,
        signer_factory=signer_factory,
        subject="vessel_2",
        predicate="gas_reading",
        obj_val="12.4_pct_LEL_ALARM",
        created_at=t0 + 5.0,
        valid_until=t0 + 600.0,
        trace_id="tr-sensor-b",
    )
    clock.t = t0 + 60.0
    res_conflict = validator.validate_tool_call("run_python", {"code": "print(1)"})
    assert res_conflict.is_valid is False
    assert res_conflict.norm == DeonticNorm.PROHIBITED
    assert len(res_conflict.inspected_premises) == 1
    assert res_conflict.inspected_premises[0].status == "CONFLICT"
    assert res_conflict.inspected_premises[0].belnap_state == BelnapValue.BOTH == "TOP"

    # 2. Once both 10-minute readings expire with no newer reading -> Belnap BOT (EXPIRED)
    clock.t = t0 + 900.0
    res_expired = validator.validate_tool_call("run_python", {"code": "print(1)"})
    assert res_expired.is_valid is False
    assert res_expired.inspected_premises[0].status == "EXPIRED"
    assert res_expired.inspected_premises[0].belnap_state == BelnapValue.NEITHER == "BOT"

    # 3. Fresh clear reading arrives at t0 + 910s -> restores VALID (Belnap TRUE)
    fresh = _commit_tool_verified_state_fact(
        store=store,
        signer_factory=signer_factory,
        subject="vessel_2",
        predicate="gas_reading",
        obj_val="0.0_pct_LEL",
        created_at=t0 + 910.0,
        valid_until=t0 + 2_710.0,
        trace_id="tr-sensor-renew",
    )
    clock.t = t0 + 920.0
    res_renewed = validator.validate_tool_call("run_python", {"code": "print(1)"})
    assert res_renewed.is_valid is True
    assert res_renewed.norm == DeonticNorm.PERMITTED
    assert res_renewed.inspected_premises[0].status == "VALID"
    assert res_renewed.inspected_premises[0].belnap_state == BelnapValue.TRUE == "T"
    assert res_renewed.inspected_premises[0].entry_id == fresh.entry_id
