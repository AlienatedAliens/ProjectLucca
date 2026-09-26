"""
Project Lucca — Standards of Proof & Proof Policy Tests (WO-21 Phase 1 / Spec D-REAS-09)

Functional acceptance tests for:
- Table completeness & fail-closed fallback for unknown consumers
- Boundary values for legal-analogous proof standards (0.0 / 0.5 / 0.75 / 0.95)
- finalize_chain refusal below CLEAR_AND_CONVINCING (0.75), retaining working memory context
- finalize_chain commit at >= 0.75 as INFERRED with proof standard metadata
- run_deduction_step spoken speculation framing:
  * confidence < 0.50 -> voiced with explicit "I'm guessing" hedge, uncommitted
  * 0.50 <= confidence < 0.75 -> voiced as "I think ... but I'm not sure enough to keep it", uncommitted
  * confidence >= 0.75 -> committed as INFERRED
- Memory context renderer and cascade labeling with proof standard
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import ulid

from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.proof_policy import (
    format_inferred_label,
    meets_standard,
    required_standard,
    required_threshold,
)
from lucca.core.reasoning_context import ReasoningContext
from lucca.core.schemas import (
    AssertFact,
    Done,
    ExecutionTier,
    LLMUsage,
    ProofStandard,
    PROOF_STANDARDS,
    Provenance,
    RetrievalQuery,
    TokenDelta,
    standard_for_confidence,
)
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.retrieval import format_memory_context
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM

TEST_MASTER_KEY = b"01234567890123456789012345678901"


def _trace(trace_id: str = "tr-test-proof-policy") -> TurnTrace:
    return TurnTrace(
        trace_id=trace_id,
        session_id="s-proof-policy",
        origin="text",
        mode="transcript",
    )


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "test_proof_policy.sqlite")
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def memory_store(test_db: DatabaseManager) -> MemoryStore:
    return MemoryStore(db=test_db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())


@pytest.fixture
def signer_factory() -> SignerFactory:
    return SignerFactory(master_key=TEST_MASTER_KEY)


@pytest.fixture
def orch(test_db: DatabaseManager, memory_store: MemoryStore, signer_factory: SignerFactory) -> Orchestrator:
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.config = get_config()
    orchestrator.execute_tools = True
    orchestrator.state = "idle"
    orchestrator.running = True
    orchestrator.db = test_db
    orchestrator.memory_store = memory_store
    orchestrator.signer_factory = signer_factory
    orchestrator.rule_engine = RuleLifecycleManager(db=test_db)
    orchestrator.current_turn_receipts = []
    orchestrator.current_turn_tool_calls = []
    orchestrator.current_turn_tier = ExecutionTier.FULL_LOOP
    orchestrator.history = []
    orchestrator.executed_tools = []
    orchestrator.current_turn_transcript = None
    orchestrator.router = MagicMock()
    orchestrator._speak_text = MagicMock()
    return orchestrator


# ============================================================================
# Unit Tests: Policy Table & Boundary Mathematics
# ============================================================================


def test_proof_standards_threshold_constants() -> None:
    """Owner-ratified constants must be exact: 0.0, 0.50, 0.75, 0.95."""
    assert PROOF_STANDARDS[ProofStandard.SPECULATION] == 0.0
    assert PROOF_STANDARDS[ProofStandard.BALANCE_OF_PROBABILITIES] == 0.50
    assert PROOF_STANDARDS[ProofStandard.CLEAR_AND_CONVINCING] == 0.75
    assert PROOF_STANDARDS[ProofStandard.BEYOND_REASONABLE_DOUBT] == 0.95


def test_policy_table_completeness_and_exact_mappings() -> None:
    """Validates every consumer specified in WO-21 Phase 1 manifest."""
    assert required_standard("casual_mention") == ProofStandard.BALANCE_OF_PROBABILITIES
    assert required_standard("memory_commit_inferred") == ProofStandard.CLEAR_AND_CONVINCING
    assert required_standard("unhedged_assertion") == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert required_standard("irreversible_action") == ProofStandard.BEYOND_REASONABLE_DOUBT

    assert required_threshold("casual_mention") == 0.50
    assert required_threshold("memory_commit_inferred") == 0.75
    assert required_threshold("unhedged_assertion") == 0.95
    assert required_threshold("irreversible_action") == 0.95


def test_policy_table_fail_closed_unknown_consumer() -> None:
    """Unknown consumers must fail-closed to BEYOND_REASONABLE_DOUBT (0.95)."""
    assert required_standard("arbitrary_unknown_consumer") == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert required_standard("") == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert required_standard("dangerous_tool") == ProofStandard.BEYOND_REASONABLE_DOUBT

    assert required_threshold("arbitrary_unknown_consumer") == 0.95
    assert not meets_standard(0.949, "arbitrary_unknown_consumer")
    assert meets_standard(0.95, "arbitrary_unknown_consumer")


def test_standard_for_confidence_boundaries() -> None:
    """Boundary test across all four legal-analogous proof standard rungs."""
    # SPECULATION (< 0.50)
    assert standard_for_confidence(0.0) == ProofStandard.SPECULATION
    assert standard_for_confidence(0.35) == ProofStandard.SPECULATION
    assert standard_for_confidence(0.4999) == ProofStandard.SPECULATION

    # BALANCE_OF_PROBABILITIES ([0.50, 0.75))
    assert standard_for_confidence(0.50) == ProofStandard.BALANCE_OF_PROBABILITIES
    assert standard_for_confidence(0.60) == ProofStandard.BALANCE_OF_PROBABILITIES
    assert standard_for_confidence(0.7499) == ProofStandard.BALANCE_OF_PROBABILITIES

    # CLEAR_AND_CONVINCING ([0.75, 0.95))
    assert standard_for_confidence(0.75) == ProofStandard.CLEAR_AND_CONVINCING
    assert standard_for_confidence(0.82) == ProofStandard.CLEAR_AND_CONVINCING
    assert standard_for_confidence(0.9499) == ProofStandard.CLEAR_AND_CONVINCING

    # BEYOND_REASONABLE_DOUBT (>= 0.95)
    assert standard_for_confidence(0.95) == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert standard_for_confidence(0.99) == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert standard_for_confidence(1.0) == ProofStandard.BEYOND_REASONABLE_DOUBT


def test_format_inferred_label() -> None:
    assert format_inferred_label(0.82) == "inferred, confidence 0.82 \u2014 clear and convincing"
    assert format_inferred_label(0.60) == "inferred, confidence 0.60 \u2014 balance of probabilities"
    assert format_inferred_label(0.96) == "inferred, confidence 0.96 \u2014 beyond reasonable doubt"
    assert format_inferred_label(0.40) == "inferred, confidence 0.40 \u2014 speculation"


# ============================================================================
# Functional Acceptance Tests: finalize_chain Standard Enforcement (WO-21b)
# ============================================================================


def test_finalize_chain_refuses_below_clear_and_convincing_and_preserves_context(orch: Orchestrator) -> None:
    """WO-21 Phase 1 Functional Acceptance 1 & Trap 2:
    finalize_chain refuses to commit an INFERRED conclusion whose confidence < CLEAR_AND_CONVINCING (0.75).
    The intermediate stays in ReasoningContext and proof trace remains available.
    """
    trace = _trace("tr-refuse-060")
    signed_prem = orch._commit_lisp_assertion(AssertFact(s="user", p="likes", o="coffee"), trace)
    assert signed_prem is not None

    ctx = ReasoningContext()
    ctx.add_intermediate(
        envelope_id=signed_prem.entry_id,
        s="user",
        p="likes",
        o="coffee",
        confidence=1.0,
        step_kind="lisp_rule",
    )
    signed_step = orch._commit_lisp_assertion(AssertFact(s="user", p="lives_in", o="Seattle"), trace)
    assert signed_step is not None
    ctx.add_intermediate(
        envelope_id=signed_step.entry_id,
        s="user",
        p="lives_in",
        o="Seattle",
        confidence=0.60,  # Below CLEAR_AND_CONVINCING (0.75)
        step_kind="llm_abductive",
        premises=["user likes coffee"],
    )

    result = orch.finalize_chain(ctx, trace)

    # 1. Must refuse commit
    assert result is None

    # 2. Store must NOT have committed the conclusion as INFERRED
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        assert cur.fetchall() == []

    # 3. TRAP 2: context and proof trace remain intact
    assert len(ctx) == 2
    pt = ctx.proof_trace()
    assert len(pt) == 2
    assert pt[-1].conclusion == "user lives_in Seattle"
    assert pt[-1].confidence == 0.60


def test_finalize_chain_commits_at_and_above_clear_and_convincing(orch: Orchestrator) -> None:
    """WO-21 Phase 1 Functional Acceptance 2:
    A chain concluding at >= 0.75 commits as INFERRED with proof standard metadata.
    """
    trace = _trace("tr-commit-080")
    signed_prem = orch._commit_lisp_assertion(AssertFact(s="user", p="job", o="engineer"), trace)
    assert signed_prem is not None

    ctx = ReasoningContext()
    ctx.add_intermediate(
        envelope_id=signed_prem.entry_id,
        s="user",
        p="job",
        o="engineer",
        confidence=1.0,
        step_kind="lisp_rule",
    )
    signed_step = orch._commit_lisp_assertion(AssertFact(s="user", p="seniority", o="lead"), trace)
    assert signed_step is not None
    ctx.add_intermediate(
        envelope_id=signed_step.entry_id,
        s="user",
        p="seniority",
        o="lead",
        confidence=0.80,  # Above CLEAR_AND_CONVINCING (0.75)
        step_kind="llm_abductive",
        premises=["user job engineer"],
    )

    result = orch.finalize_chain(ctx, trace)

    # 1. Must commit successfully
    assert result is not None
    assert result.provenance == Provenance.INFERRED
    assert result.confidence == 0.80

    # 2. Store must contain the committed fact with proof standard
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content, e.provenance, e.confidence, e.payload_json
            FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "user seniority lead"
    assert row[1] == "INFERRED"
    assert row[2] == 0.80

    payload = json.loads(row[3])
    assert payload["structured"]["proof_standard"] == "clear and convincing"


# ============================================================================
# Functional Acceptance Tests: Spoken Speculation & Guessing Framing
# ============================================================================


def test_run_deduction_step_speaks_speculation_at_confidence_060(orch: Orchestrator) -> None:
    """WO-21 Phase 1 Functional Acceptance:
    A chain concluding with confidence 0.60 does NOT commit;
    the spoken output frames it as speculation ("I think... but I'm not sure enough to keep it").
    """
    trace = _trace("tr-deduction-060")
    orch._commit_lisp_assertion(AssertFact(s="user", p="likes", o="coffee"), trace)

    step_json = json.dumps([
        {
            "premises": ["user likes coffee"],
            "s": "user",
            "p": "lives_in",
            "o": "Melbourne",
            "confidence": 0.60,
        }
    ])
    fake_llm = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20)),
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="Where does user live?",
        trace=trace,
        llm=fake_llm,
    )

    # Step was accepted as intermediate
    assert len(accepted) == 1

    # Spoken output must frame as speculation per functional acceptance
    assert spoken is not None
    assert "I think" in spoken
    assert "not sure enough to keep it" in spoken
    assert "user lives_in Melbourne" in spoken

    # Store must NOT have committed the conclusion as INFERRED
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        assert cur.fetchall() == []


def test_run_deduction_step_speaks_guessing_hedge_below_050(orch: Orchestrator) -> None:
    """WO-21 Phase 1 Ratified Amendment:
    SPECULATION band (< 0.50) is voiced with an explicit "I'm guessing" hedge,
    never stated as belief, never committed.
    """
    trace = _trace("tr-deduction-040")
    orch._commit_lisp_assertion(AssertFact(s="user", p="likes", o="coffee"), trace)

    step_json = json.dumps([
        {
            "premises": ["user likes coffee"],
            "s": "user",
            "p": "fav_color",
            "o": "brown",
            "confidence": 0.40,
        }
    ])
    fake_llm = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20)),
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="What is favorite color?",
        trace=trace,
        llm=fake_llm,
    )

    assert len(accepted) == 1
    assert spoken is not None
    assert "I'm guessing" in spoken
    assert "speculation" in spoken
    assert "user fav_color brown" in spoken

    # Store must NOT have committed the conclusion as INFERRED
    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        assert cur.fetchall() == []


def test_run_deduction_step_commits_at_080_without_speculation_hedge(orch: Orchestrator) -> None:
    """WO-21 Phase 1 Functional Acceptance:
    A chain concluding at 0.80 commits as INFERRED; spoken is None (normal turn flow).
    """
    trace = _trace("tr-deduction-080")
    orch._commit_lisp_assertion(AssertFact(s="user", p="job", o="engineer"), trace)

    step_json = json.dumps([
        {
            "premises": ["user job engineer"],
            "s": "user",
            "p": "interest_is",
            "o": "systems",
            "confidence": 0.80,
        }
    ])
    fake_llm = FakeLLM(script=[
        TokenDelta(delta=step_json),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20)),
    ])

    accepted, spoken = orch.run_deduction_step(
        goal="What is user interest?",
        trace=trace,
        llm=fake_llm,
    )

    assert len(accepted) == 1
    assert spoken is None  # Committed without hesitation/speculation fallback

    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content, e.provenance
            FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "user interest_is systems"
        assert rows[0][1] == "INFERRED"


# ============================================================================
# Functional Acceptance Tests: Context Renderer & Cascade Proof Standard Label
# ============================================================================


def test_renderer_and_cascade_show_proof_standard_labels(orch: Orchestrator) -> None:
    """WO-21 Phase 1 Functional Acceptance 3:
    The prompt context shows the standard label:
    [inferred, confidence 0.82 — clear and convincing]
    """
    trace = _trace("tr-renderer-standard")
    signed_prem = orch._commit_lisp_assertion(AssertFact(s="user", p="job", o="architect"), trace)
    assert signed_prem is not None

    ctx = ReasoningContext()
    ctx.add_intermediate(
        envelope_id=signed_prem.entry_id,
        s="user",
        p="job",
        o="architect",
        confidence=1.0,
        step_kind="lisp_rule",
    )
    signed_step = orch._commit_lisp_assertion(AssertFact(s="user", p="field", o="software"), trace)
    assert signed_step is not None
    ctx.add_intermediate(
        envelope_id=signed_step.entry_id,
        s="user",
        p="field",
        o="software",
        confidence=0.82,
        step_kind="llm_abductive",
        premises=["user job architect"],
    )

    inferred_signed = orch.finalize_chain(ctx, trace)
    assert inferred_signed is not None

    # 1. Test format_memory_context (renderer)
    q = RetrievalQuery(query_text="software", k=5)
    hits = orch.memory_store.search(q)
    inferred_hits = [h for h in hits if h.provenance == Provenance.INFERRED or str(h.provenance) == "INFERRED"]
    assert len(inferred_hits) >= 1
    rendered = format_memory_context(inferred_hits)
    assert "inferred, confidence 0.82 \u2014 clear and convincing" in rendered

    # 2. Test cascade synthesize output
    cascade = EpistemicSearchCascade(memory_store=orch.memory_store)
    evidence = cascade.query_substrate_2_memory("software")
    _, cascade_text, _ = cascade.synthesize("software", evidence)
    assert "[inferred, confidence 0.82 \u2014 clear and convincing]" in cascade_text
