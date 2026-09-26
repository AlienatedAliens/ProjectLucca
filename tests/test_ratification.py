"""
Project Lucca — Web-Fact Ratification Flow & Hazard Policy Tests
WO-21 Phase 3 (The Defeasible Rung) / Spec D-REAS-09

Functional acceptance tests for:
- Ratification domain whitelist (config/domain_whitelist.toml)
- Proactive ratification offer on whitelisted domains
  ("I found on {domain} that {claim} — want me to remember that?")
- Non-whitelisted domains: never prompt
- User "yes" commits USER_DERIVED fact with structured metadata
  {source_url, fetch_receipt_entry_id, confirmed_by_user: true}
- Provenance signer is DerivedFactSigner (your ratification is trust root)
- Grounding eligibility: Ratified fact is eligible for subsequent deduction premises
- Gate defense: Fabricated receipt IDs rejected (ProvenanceRejected)
- Trap 1: One offer per turn maximum, no nagging loops
- Trap 2: Provenance signer is DerivedFactSigner, never any web signer
- Amendment A: 2-D proof policy f(consumer, hazard), Hazard enum, classify_hazard,
  casual_mention scaling (0.50 low -> 0.95 high), irreversible actions always 0.95,
  fail-closed default to HIGH
- Amendment B: User-invocable cross-reference ("cross-reference that", "find more sources"),
  fresh web searches (<= 3), Walton corroboration engine, confidence adjustment, standard label
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.clock import SystemClock
from lucca.core.coherence import ToolReceipt
from lucca.core.config import get_config
from lucca.core.exceptions import ProvenanceRejected
from lucca.core.orchestrator import Orchestrator
from lucca.core.proof_policy import (
    Hazard,
    classify_hazard,
    load_ratification_domains,
    meets_standard,
    required_standard,
    required_threshold,
)
from lucca.core.schemas import (
    ExecutionTier,
    InferenceStep,
    PendingRatification,
    ProofStandard,
    Provenance,
    UnsignedPayload,
)
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import TurnInput, TurnPipeline
from lucca.memory.db import DatabaseManager
from lucca.memory.gate import ProvenanceGate
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


def _trace(trace_id: str = "tr-test-ratify") -> TurnTrace:
    return TurnTrace(
        trace_id=trace_id,
        session_id="s-ratify",
        origin="text",
        mode="transcript",
    )


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "test_ratification.sqlite")
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def memory_store(test_db: DatabaseManager) -> MemoryStore:
    return MemoryStore(
        db=test_db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort()
    )


@pytest.fixture
def signer_factory() -> SignerFactory:
    return SignerFactory(master_key=TEST_MASTER_KEY)


@pytest.fixture
def orch(
    test_db: DatabaseManager, memory_store: MemoryStore, signer_factory: SignerFactory
) -> Orchestrator:
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.config = get_config()
    orchestrator.execute_tools = True
    orchestrator.state = "idle"
    orchestrator.running = True
    orchestrator.db = test_db
    orchestrator.memory_store = memory_store
    orchestrator.signer_factory = signer_factory
    orchestrator.current_turn_receipts = []
    orchestrator.current_turn_tool_calls = []
    orchestrator.current_turn_tier = ExecutionTier.FULL_LOOP
    orchestrator.current_turn_tool_spoken = []
    orchestrator.current_turn_tool_ok = True
    orchestrator._last_unspoken_tool_msg = None
    orchestrator.history = []
    orchestrator.executed_tools = []
    orchestrator.router = MagicMock()
    orchestrator.router.classify_intent.return_value = ("chit_chat", 0.9, {})
    orchestrator.sandbox = MagicMock()
    orchestrator.speech_output = MagicMock()
    orchestrator.play_ring = MagicMock()
    orchestrator._speak_text = MagicMock()
    orchestrator._publish_caption = MagicMock()
    orchestrator._finalize_turn = MagicMock()

    # Ratification & cross-reference state
    orchestrator.ratification_domains = {
        "docs.python.org",
        "en.wikipedia.org",
        "github.com",
        "ars-technica.com",
        "arstechnica.com",
    }
    orchestrator._pending_ratification = None
    orchestrator._ratification_offered_this_turn = False
    orchestrator._last_ratified_claim = None
    orchestrator.cross_reference_search_fn = None
    orchestrator.output_supervisor = MagicMock()
    orchestrator.clock = SystemClock()
    orchestrator.prev_decision_record = None
    orchestrator.prev_turn_ts = None
    orchestrator.active_detected_words = []
    orchestrator._neutralize_context_attractors = MagicMock(return_value=[])
    orchestrator.session_id = "s-ratify"
    orchestrator.cascade = MagicMock()
    orchestrator.cascade.classify_intent.return_value = (False, [], None)
    orchestrator._search_memories = MagicMock(return_value=[])
    orchestrator.rule_engine = RuleLifecycleManager(db=test_db)

    orchestrator.turn_pipeline = TurnPipeline(orchestrator)
    return orchestrator


# ============================================================================
# Amendment A: Hazard Classification & 2-D Proof Policy
# ============================================================================


def test_classify_hazard_categories() -> None:
    """Classifies claims into LOW, MEDIUM, and HIGH hazard levels."""
    # Low hazard: trivia, pop culture, entertainment, preferences
    assert classify_hazard("MGS was released in 1998") == Hazard.LOW
    assert classify_hazard("favorite food is pizza") == Hazard.LOW
    assert classify_hazard("Metallica released Master of Puppets") == Hazard.LOW
    assert classify_hazard("trivia about video games") == Hazard.LOW

    # Medium hazard: technical specs, configuration, programming, tools
    assert classify_hazard("python version 3.13 syntax") == Hazard.MEDIUM
    assert classify_hazard("database port 5432 configuration") == Hazard.MEDIUM
    assert classify_hazard("git branch main in repository") == Hazard.MEDIUM
    assert classify_hazard("api endpoint url settings") == Hazard.MEDIUM

    # High hazard: health, medical, financial, security, destructive
    assert classify_hazard("aspirin dosage for headache") == Hazard.HIGH
    assert classify_hazard("wire transfer bank funds") == Hazard.HIGH
    assert classify_hazard("delete all database files") == Hazard.HIGH
    assert classify_hazard("user password credential secret") == Hazard.HIGH


def test_classify_hazard_fail_closed() -> None:
    """Fail-closed invariant: unknown, empty, or unclassifiable claims return Hazard.HIGH."""
    assert classify_hazard("") == Hazard.HIGH
    assert classify_hazard("   ") == Hazard.HIGH
    assert classify_hazard("completely obscure unrecognized assertible token") == Hazard.HIGH


def test_2d_policy_table_scaling() -> None:
    """Amendment A: Required standard scales with (consumer, hazard)."""
    # Casual mention scales from 0.50 (low) to 0.75 (medium) to 0.95 (high)
    assert required_standard("casual_mention", Hazard.LOW) == ProofStandard.BALANCE_OF_PROBABILITIES
    assert required_standard("casual_mention", Hazard.MEDIUM) == ProofStandard.CLEAR_AND_CONVINCING
    assert required_standard("casual_mention", Hazard.HIGH) == ProofStandard.BEYOND_REASONABLE_DOUBT

    assert required_threshold("casual_mention", Hazard.LOW) == 0.50
    assert required_threshold("casual_mention", Hazard.MEDIUM) == 0.75
    assert required_threshold("casual_mention", Hazard.HIGH) == 0.95

    # Memory commit inferred requires at least clear and convincing; high hazard requires beyond reasonable doubt
    assert required_standard("memory_commit_inferred", Hazard.LOW) == ProofStandard.CLEAR_AND_CONVINCING
    assert required_standard("memory_commit_inferred", Hazard.MEDIUM) == ProofStandard.CLEAR_AND_CONVINCING
    assert required_standard("memory_commit_inferred", Hazard.HIGH) == ProofStandard.BEYOND_REASONABLE_DOUBT

    # Irreversible actions ALWAYS require BEYOND_REASONABLE_DOUBT (0.95)
    assert required_standard("irreversible_action", Hazard.LOW) == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert required_standard("irreversible_action", Hazard.MEDIUM) == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert required_standard("irreversible_action", Hazard.HIGH) == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert required_threshold("irreversible_action", Hazard.LOW) == 0.95


def test_2d_policy_fail_closed_and_backward_compat() -> None:
    """Unregistered consumer or unknown hazard fails closed to BEYOND_REASONABLE_DOUBT."""
    assert required_standard("unknown_consumer", Hazard.LOW) == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert required_standard("casual_mention", "invalid_hazard_str") == ProofStandard.BEYOND_REASONABLE_DOUBT

    # Backward compatibility: hazard=None uses Phase 1 1-D values
    assert required_standard("casual_mention") == ProofStandard.BALANCE_OF_PROBABILITIES
    assert required_standard("memory_commit_inferred") == ProofStandard.CLEAR_AND_CONVINCING
    assert required_standard("irreversible_action") == ProofStandard.BEYOND_REASONABLE_DOUBT


def test_meets_standard_with_hazard() -> None:
    """meets_standard respects hazard-scaled thresholds."""
    # 0.60 confidence satisfies casual mention for LOW hazard (0.50 threshold),
    # but fails for MEDIUM (0.75) and HIGH (0.95) hazard.
    assert meets_standard(0.60, "casual_mention", Hazard.LOW) is True
    assert meets_standard(0.60, "casual_mention", Hazard.MEDIUM) is False
    assert meets_standard(0.60, "casual_mention", Hazard.HIGH) is False

    # 0.80 satisfies MEDIUM (0.75) but fails HIGH (0.95)
    assert meets_standard(0.80, "casual_mention", Hazard.MEDIUM) is True
    assert meets_standard(0.80, "casual_mention", Hazard.HIGH) is False


# ============================================================================
# Base Spec: Domain Whitelist & Ratification Offer Flow
# ============================================================================


def test_domain_whitelist_loader() -> None:
    """Domain whitelist loads from config/domain_whitelist.toml with fallback."""
    domains = load_ratification_domains()
    assert "docs.python.org" in domains
    assert "en.wikipedia.org" in domains
    assert "github.com" in domains
    assert "ars-technica.com" in domains or "arstechnica.com" in domains


def test_ratification_offer_whitelisted_domain(orch: Orchestrator) -> None:
    """Receipt from whitelisted domain with durable claim triggers ratification offer."""
    trace = _trace()
    rcpt = ToolReceipt(
        tool="fetch_url",
        tool_name="fetch_url",
        ok=True,
        call_id="call-whitelisted-1",
        args={"url": "https://docs.python.org/3/whatsnew/3.13.html"},
        output="Python 3.13 was released on October 7, 2024. It adds experimental free-threading.",
        timestamp=time.time(),
    )
    orch.current_turn_receipts = [rcpt]

    offer = orch._check_and_offer_ratification(trace)
    assert offer is not None
    assert "docs.python.org" in offer
    assert "Python 3.13 was released on October 7, 2024" in offer
    assert offer.endswith("— want me to remember that?")

    # Offer was spoken to user
    orch._speak_text.assert_called_with(trace, offer)

    # Pending ratification recorded
    assert orch._pending_ratification is not None
    assert orch._pending_ratification.domain == "docs.python.org"
    assert orch._pending_ratification.claim == "Python 3.13 was released on October 7, 2024"
    assert orch._pending_ratification.source_url == "https://docs.python.org/3/whatsnew/3.13.html"


def test_ratification_offer_non_whitelisted_domain_never_prompts(orch: Orchestrator) -> None:
    """Non-whitelisted domain NEVER prompts for ratification."""
    trace = _trace()
    rcpt = ToolReceipt(
        tool="fetch_url",
        tool_name="fetch_url",
        ok=True,
        call_id="call-untrusted-1",
        args={"url": "https://untrusted-blog.xyz/facts"},
        output="Python 3.13 was released on October 7, 2024.",
        timestamp=time.time(),
    )
    orch.current_turn_receipts = [rcpt]

    offer = orch._check_and_offer_ratification(trace)
    assert offer is None
    assert orch._pending_ratification is None
    orch._speak_text.assert_not_called()


def test_ratification_trap1_one_offer_per_turn_max(orch: Orchestrator) -> None:
    """Trap 1: Maximum one offer per turn even with multiple whitelisted receipts."""
    trace = _trace()
    rcpt1 = ToolReceipt(
        tool="fetch_url",
        tool_name="fetch_url",
        ok=True,
        call_id="call-wl-1",
        args={"url": "https://docs.python.org/3.13"},
        output="Python 3.13 was released on October 7, 2024.",
        timestamp=time.time(),
    )
    rcpt2 = ToolReceipt(
        tool="fetch_url",
        tool_name="fetch_url",
        ok=True,
        call_id="call-wl-2",
        args={"url": "https://en.wikipedia.org/wiki/Python"},
        output="Python was created by Guido van Rossum.",
        timestamp=time.time(),
    )
    orch.current_turn_receipts = [rcpt1, rcpt2]

    offer1 = orch._check_and_offer_ratification(trace)
    assert offer1 is not None

    # Second check in same turn returns None (no nagging)
    offer2 = orch._check_and_offer_ratification(trace)
    assert offer2 is None


# ============================================================================
# Full Loop Acceptance: Offer -> User "Yes" -> USER_DERIVED Committed
# ============================================================================


def test_full_loop_user_yes_commits_user_derived(
    orch: Orchestrator, test_db: DatabaseManager, signer_factory: SignerFactory
) -> None:
    """Full loop: fetch -> offer -> user 'yes' -> USER_DERIVED committed with source metadata.

    Trap 2: Provenance signer is DerivedFactSigner (your ratification is trust root).
    """
    trace1 = _trace("tr-turn-1")

    # 1. Turn 1: fetch from whitelisted domain
    rcpt = ToolReceipt(
        tool="fetch_url",
        tool_name="fetch_url",
        ok=True,
        call_id="call-rcpt-1",
        args={"url": "https://docs.python.org/3.13"},
        output="Python 3.13 was released on October 7, 2024.",
        timestamp=time.time(),
    )
    orch.current_turn_receipts = [rcpt]

    # Pre-commit the fetch receipt envelope into provenance_envelopes (as commit_action_receipts does)
    action_signer = signer_factory.tool_result()
    action_unsigned = UnsignedPayload(
        content="fetch_url(url='https://docs.python.org/3.13') -> ok",
        provenance=Provenance.ASSISTANT_ACTION,
        kind="action_receipt",
        nonce="rcpt-nonce-001",
        created_at=time.time(),
        trace_id=trace1.trace_id,
        confidence=1.0,
        structured={"call_id": rcpt.call_id},
    )
    action_signed = action_signer.sign(action_unsigned)
    orch.memory_store.commit(action_signed)

    # Offer ratification
    offer = orch._check_and_offer_ratification(trace1)
    assert offer is not None
    assert orch._pending_ratification is not None
    # Link the committed envelope id
    orch._pending_ratification.fetch_receipt_entry_id = action_signed.entry_id

    # 2. Turn 2: User says "yes"
    trace2 = _trace("tr-turn-2")
    inp = TurnInput(
        user_text="Yes, remember that please.",
        trace=trace2,
        origin="text",
        mode="transcript",
    )
    orch.turn_pipeline.run(inp)

    # User confirmation processed and cleared
    assert orch._pending_ratification is None
    assert orch._last_ratified_claim == "Python 3.13 was released on October 7, 2024"

    # Verify committed fact in database
    with test_db.read_cursor() as cur:
        cur.execute(
            """
            SELECT e.entry_id, e.provenance, e.signer_id, e.grounding_eligible, e.payload_json, m.content
            FROM provenance_envelopes e
            JOIN memories m ON e.entry_id = m.entry_id
            WHERE e.provenance = 'USER_DERIVED'
            """
        )
        row = cur.fetchone()
        assert row is not None, "USER_DERIVED fact must be persisted in store"
        entry_id, prov, signer_id, grounding_el, payload_json_str, content = row

        assert prov == "USER_DERIVED"
        assert "ratification" in signer_id  # DerivedFactSigner
        assert grounding_el == 1
        assert "Python 3.13 was released on October 7, 2024" in content
        assert action_signed.entry_id in payload_json_str
        assert "confirmed_by_user" in payload_json_str


def test_user_no_commits_nothing(orch: Orchestrator, test_db: DatabaseManager) -> None:
    """User 'no' cancels ratification and commits nothing."""
    orch._pending_ratification = PendingRatification(
        call_id="call-cancel-1",
        domain="docs.python.org",
        claim="Python 3.13 was released on October 7, 2024",
        source_url="https://docs.python.org",
        fetch_receipt_entry_id="receipt-001",
    )

    trace2 = _trace("tr-turn-2")
    inp = TurnInput(
        user_text="No, don't remember that.",
        trace=trace2,
        origin="text",
        mode="transcript",
    )
    orch.turn_pipeline.run(inp)

    # Cleared
    assert orch._pending_ratification is None

    # Nothing committed
    with test_db.read_cursor() as cur:
        cur.execute("SELECT count(*) FROM provenance_envelopes WHERE provenance = 'USER_DERIVED'")
        count = cur.fetchone()[0]
        assert count == 0


def test_user_unrelated_utterance_clears_offer_without_nagging(
    orch: Orchestrator, test_db: DatabaseManager
) -> None:
    """Trap 1: If user ignores the offer and speaks an unrelated turn, offer clears without nagging."""
    orch._pending_ratification = PendingRatification(
        call_id="call-ignore-1",
        domain="docs.python.org",
        claim="Python 3.13 was released on October 7, 2024",
        source_url="https://docs.python.org",
        fetch_receipt_entry_id="receipt-001",
    )

    trace2 = _trace("tr-turn-2")
    inp = TurnInput(
        user_text="What is the weather today?",
        trace=trace2,
        origin="text",
        mode="transcript",
    )
    # Router mock returns harmless fallback
    orch.router.route.return_value = None
    orch._stream_llm_speech = MagicMock()
    orch.turn_pipeline.run(inp)

    # Cleared — no nagging loop
    assert orch._pending_ratification is None


# ============================================================================
# Gate Replay & Fabricated-Receipt Rejection
# ============================================================================


def test_gate_rejects_fabricated_receipt_id(
    test_db: DatabaseManager, signer_factory: SignerFactory
) -> None:
    """ProvenanceGate rejects USER_DERIVED commits citing a fabricated fetch receipt."""
    gate = ProvenanceGate(master_key=TEST_MASTER_KEY, db=test_db)
    signer = signer_factory.derived_fact()

    # Create signed payload referencing a non-existent receipt envelope
    unsigned = UnsignedPayload(
        content="Fabricated Python 3.14 claim",
        provenance=Provenance.USER_DERIVED,
        kind="fact",
        nonce="nonce-fab-001",
        created_at=time.time(),
        trace_id="tr-fab-1",
        confidence=1.0,
        source_entry_ids=["fabricated-receipt-envelope-999"],
        structured={
            "source_url": "https://fabricated.site",
            "fetch_receipt_entry_id": "fabricated-receipt-envelope-999",
            "confirmed_by_user": True,
        },
    )
    signed = signer.sign(unsigned)

    with pytest.raises(ProvenanceRejected, match="does not exist in store"):
        gate.admit(signed, db=test_db)


def test_ratified_fact_usable_as_deduction_premise(
    orch: Orchestrator, test_db: DatabaseManager, memory_store: MemoryStore, signer_factory: SignerFactory
) -> None:
    """Ratified fact is grounding-eligible and can resolve as a premise in an INFERRED deduction."""
    # Seed a real receipt envelope
    action_signer = signer_factory.tool_result()
    rcpt_unsigned = UnsignedPayload(
        content="fetch_url(url='https://docs.python.org') -> ok",
        provenance=Provenance.ASSISTANT_ACTION,
        kind="action_receipt",
        nonce="rcpt-nonce-deduct",
        created_at=time.time(),
        trace_id="tr-rcpt-deduct",
        confidence=1.0,
        structured={"call_id": "call-deduct-1"},
    )
    rcpt_signed = action_signer.sign(rcpt_unsigned)
    memory_store.commit(rcpt_signed)

    # Commit ratified fact
    derived_signer = signer_factory.derived_fact()
    ratified_unsigned = UnsignedPayload(
        content="Python supports free-threading",
        provenance=Provenance.USER_DERIVED,
        kind="fact",
        nonce="ratified-nonce-deduct",
        created_at=time.time(),
        trace_id="tr-ratified-deduct",
        confidence=1.0,
        source_entry_ids=[rcpt_signed.entry_id],
        structured={
            "source_url": "https://docs.python.org",
            "fetch_receipt_entry_id": rcpt_signed.entry_id,
            "confirmed_by_user": True,
        },
    )
    ratified_signed = derived_signer.sign(ratified_unsigned)
    memory_store.commit(ratified_signed)

    # Now verify that an INFERRED deduction citing this ratified fact is admitted by the gate
    inferred_signer = signer_factory.inferred_fact()
    step = InferenceStep(
        premises=[ratified_signed.entry_id],
        s="Python",
        p="enables",
        o="multithreaded concurrency",
        conclusion="Python enables multithreaded concurrency",
        confidence=0.85,
        rule_id="concurrency_rule",
        envelope_id=ratified_signed.entry_id,
    )
    inferred_unsigned = UnsignedPayload(
        content="Python enables multithreaded concurrency",
        provenance=Provenance.INFERRED,
        kind="fact",
        nonce="inferred-nonce-deduct",
        created_at=time.time(),
        trace_id="tr-inferred-deduct",
        confidence=0.85,
        source_entry_ids=[ratified_signed.entry_id],
        structured={"proof_trace": [step.model_dump()]},
    )
    inferred_signed = inferred_signer.sign(inferred_unsigned)

    # Gate admission succeeds because the ratified fact is in provenance_envelopes and grounding_eligible=1
    gate = ProvenanceGate(master_key=TEST_MASTER_KEY, db=test_db)
    admitted = gate.admit(inferred_signed, db=test_db)
    assert admitted.payload.entry_id == inferred_signed.entry_id


# ============================================================================
# Amendment B: User-Invocable Cross-Reference
# ============================================================================


def test_is_cross_reference_command(orch: Orchestrator) -> None:
    """Detects spoken cross-reference commands."""
    assert orch._is_cross_reference_command("cross-reference that") is True
    assert orch._is_cross_reference_command("cross reference that") is True
    assert orch._is_cross_reference_command("find more sources") is True
    assert orch._is_cross_reference_command("check more sources on that") is True
    assert orch._is_cross_reference_command("verify that") is True
    assert orch._is_cross_reference_command("what is the weather") is False


def test_cross_reference_flow_corroborated(orch: Orchestrator) -> None:
    """Spoken cross-reference executes fresh searches (<=3), runs Walton corroboration, and reports standard."""
    trace = _trace("tr-crossref-1")
    target_claim = "Python 3.13 was released on October 7, 2024"

    # Set pending claim
    orch._pending_ratification = PendingRatification(
        call_id="call-cr-1",
        domain="docs.python.org",
        claim=target_claim,
        source_url="https://docs.python.org",
    )

    # Mock search hook returning 2 independent sources
    def mock_searches(claim: str, max_searches: int) -> list[ToolReceipt]:
        assert max_searches <= 3
        return [
            ToolReceipt(
                tool="search_web",
                tool_name="search_web",
                ok=True,
                call_id="cr-rcpt-1",
                args={"url": "https://arstechnica.com/python-release"},
                output=f"Report from arstechnica.com: {target_claim}.",
                timestamp=time.time(),
            ),
            ToolReceipt(
                tool="search_web",
                tool_name="search_web",
                ok=True,
                call_id="cr-rcpt-2",
                args={"url": "https://en.wikipedia.org/wiki/Python"},
                output=f"Wikipedia asserts {target_claim}.",
                timestamp=time.time(),
            ),
        ]

    orch.cross_reference_search_fn = mock_searches

    # Run turn with "cross-reference that"
    inp = TurnInput(
        user_text="cross-reference that",
        trace=trace,
        origin="text",
        mode="transcript",
    )
    orch.turn_pipeline.run(inp)

    # Spoken output reports corroboration and standard label
    orch._speak_text.assert_called()
    spoken_text = orch._speak_text.call_args[0][1]
    assert "Cross-referenced across 2 independent sources" in spoken_text
    assert "clear and convincing" in spoken_text


def test_cross_reference_flow_disputed(orch: Orchestrator) -> None:
    """Spoken cross-reference docks confidence when disputing evidence is found."""
    trace = _trace("tr-crossref-2")
    target_claim = "Python 3.13 was released on October 7, 2024"
    orch._last_ratified_claim = target_claim

    def mock_searches(claim: str, max_searches: int) -> list[ToolReceipt]:
        return [
            ToolReceipt(
                tool="search_web",
                tool_name="search_web",
                ok=True,
                call_id="cr-rcpt-dispute",
                args={"url": "https://disputing-news.org/errata"},
                output=f"disputed by disputing-news.org: false claim that {target_claim}",
                timestamp=time.time(),
            )
        ]

    orch.cross_reference_search_fn = mock_searches

    inp = TurnInput(
        user_text="find more sources",
        trace=trace,
        origin="text",
        mode="transcript",
    )
    orch.turn_pipeline.run(inp)

    spoken_text = orch._speak_text.call_args[0][1]
    assert "disputing evidence" in spoken_text
    assert "docked" in spoken_text
