"""
Project Lucca — Corroboration Engine Tests (WO-21 Phase 2 / Spec D-REAS-09)

Functional acceptance tests for:
- Argumentation scheme dispatch & Walton AUTHORITY critical questions (Q1, Q2, Q3)
- Single seam arithmetic:
  * Corroborated claim boosted by +0.10, strictly capped at 0.95 (Trap 2)
  * Disputed claim docked by -0.30 (floor at 0.0) + defeater condition added
  * Unknown stays flat
  * Asymmetric priority (dispute overrides corroboration)
- Trap 1: Deduplication of corroborating sources (same domain/fetch does not corroborate)
- Ratified requirement: Structured Q-results with question, answer, count, and evidence_entry_ids
  persisted to ReasoningContext entry and proof trace
- End-to-end deduction step with corroboration boost and dispute docking
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.coherence import ToolReceipt
from lucca.core.config import get_config
from lucca.core.corroboration import (
    CQAnswer,
    CriticalQuestionResult,
    Scheme,
    adjust_confidence,
    critical_questions,
    extract_etld_plus_one,
    is_same_source,
    normalize_source_identity,
)
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    ExecutionTier,
    InferenceStep,
    LLMUsage,
    Provenance,
    TokenDelta,
    UnsignedPayload,
)
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import DerivedFactSigner
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM

TEST_MASTER_KEY = b"01234567890123456789012345678901"


def _trace(trace_id: str = "tr-test-corrob") -> TurnTrace:
    return TurnTrace(
        trace_id=trace_id,
        session_id="s-corrob",
        origin="text",
        mode="transcript",
    )


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "test_corroboration.sqlite")
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
# Unit Tests: Scheme Dispatch & Single Seam Arithmetic
# ============================================================================


def test_scheme_dispatch_unsupported_schemes_raise() -> None:
    """Non-AUTHORITY schemes raise NotImplementedError with typed reason."""
    step = InferenceStep(
        premises=["source asserts claim"],
        s="source",
        p="asserts",
        o="claim",
        confidence=0.8,
    )
    for scheme in (Scheme.SIGN, Scheme.ANALOGY, Scheme.CONSEQUENCE, Scheme.PRECEDENT):
        with pytest.raises(NotImplementedError) as exc_info:
            critical_questions(scheme, step)
        assert f"Scheme '{scheme}' not implemented in v1" in str(exc_info.value)


def test_adjust_confidence_single_seam_arithmetic_and_cap() -> None:
    """Validates single seam arithmetic:
    - Corroborated: min(0.95, conf + 0.10) (Trap 2: cap at 0.95)
    - Disputed: max(0.00, conf - 0.30) + condition added
    - Unknown: unadjusted
    - Asymmetric priority: dispute overrides corroboration
    """
    q_corrob = CriticalQuestionResult(
        question="Is the claim corroborated by an independent grounding-eligible fact?",
        answer=CQAnswer.SATISFIED,
        count=1,
        evidence_entry_ids=["env-1"],
        sources=["the-verge"],
    )
    q_dispute = CriticalQuestionResult(
        question="Is the claim disputed by any grounding-eligible fact?",
        answer=CQAnswer.SATISFIED,
        count=1,
        evidence_entry_ids=["env-2"],
        sources=["ms-bulletin"],
        detail="ms-bulletin disputes driver-582.11 fixes wsl-crash",
    )
    q_unknown_corrob = CriticalQuestionResult(
        question="Is the claim corroborated by an independent grounding-eligible fact?",
        answer=CQAnswer.UNKNOWN,
        count=0,
    )
    q_unknown_dispute = CriticalQuestionResult(
        question="Is the claim disputed by any grounding-eligible fact?",
        answer=CQAnswer.UNKNOWN,
        count=0,
    )

    # 1. Corroboration boost (+0.10)
    conf, conds = adjust_confidence(0.80, [q_corrob, q_unknown_dispute])
    assert conf == 0.90
    assert conds == []

    # 2. Trap 2: Corroboration strictly capped at 0.95 (never 1.0)
    conf, conds = adjust_confidence(0.90, [q_corrob, q_unknown_dispute])
    assert conf == 0.95
    conf, conds = adjust_confidence(0.95, [q_corrob, q_unknown_dispute])
    assert conf == 0.95

    # 3. Dispute dock (-0.30) and condition added
    conf, conds = adjust_confidence(0.85, [q_unknown_corrob, q_dispute])
    assert conf == 0.55
    assert len(conds) == 1
    assert "ms-bulletin disputes driver-582.11 fixes wsl-crash" in conds[0]

    # 4. Dispute dock floor at 0.0
    conf, conds = adjust_confidence(0.20, [q_unknown_corrob, q_dispute])
    assert conf == 0.0

    # 5. Unknown: unadjusted
    conf, conds = adjust_confidence(0.85, [q_unknown_corrob, q_unknown_dispute])
    assert conf == 0.85
    assert conds == []

    # 6. Asymmetric priority: if both dispute and corroboration are satisfied, dispute overrides
    conf, conds = adjust_confidence(0.85, [q_corrob, q_dispute])
    assert conf == 0.55
    assert len(conds) == 1


def test_q_results_record_counts_and_envelope_ids() -> None:
    """Ratified STOP gate requirement:
    Q-results must record count and evidence envelope IDs.
    """
    res = CriticalQuestionResult(
        question="Is the claim corroborated by an independent grounding-eligible fact?",
        answer=CQAnswer.SATISFIED,
        count=2,
        evidence_entry_ids=["env-10", "env-11"],
        sources=["source-a", "source-b"],
        detail="Corroborated by 2 independent sources",
    )
    d = res.to_dict()
    assert d["question"] == "Is the claim corroborated by an independent grounding-eligible fact?"
    assert d["answer"] == "satisfied"
    assert d["count"] == 2
    assert d["evidence_entry_ids"] == ["env-10", "env-11"]
    assert d["sources"] == ["source-a", "source-b"]


# ============================================================================
# Functional Acceptance Tests: Corroboration Engine & Deduction Integration
# ============================================================================


def test_corroboration_dedupes_same_domain_source(memory_store: MemoryStore) -> None:
    """WO-21 Phase 2 Trap 1:
    Corroboration counts independent sources — two receipts from the same fetch/domain
    do NOT corroborate (deduped by source).
    """
    step = InferenceStep(
        premises=["ars-technica asserts driver-582.11 fixes wsl-crash"],
        s="driver-582.11",
        p="fixes_issue",
        o="wsl-crash",
        confidence=0.85,
    )
    # Two receipts from the same domain 'ars-technica'
    receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-1",
            source="ars-technica",
            output="Report from ars-technica: confirmed that driver-582.11 fixes wsl-crash.",
        ),
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-2",
            source="ars-technica",
            output="Update from ars-technica: driver-582.11 fixes wsl-crash on Windows 11.",
        ),
    ]

    q_results = critical_questions(Scheme.AUTHORITY, step, store=memory_store, receipts=receipts)
    assert len(q_results) == 3

    # Q1: Signed receipt proved the source asserted the claim -> SATISFIED (count = 2 receipts)
    assert q_results[0].question == "Does a signed receipt prove the source asserted the claim?"
    assert q_results[0].answer == CQAnswer.SATISFIED
    assert q_results[0].count == 2

    # Q2: Independent corroboration -> UNKNOWN (same domain does NOT count as independent)
    assert (
        q_results[1].question
        == "Is the claim corroborated by an independent grounding-eligible fact?"
    )
    assert q_results[1].answer == CQAnswer.UNKNOWN
    assert q_results[1].count == 0


def test_corroboration_boosts_confidence_with_independent_store_fact(
    orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """WO-21 Phase 2 Functional Acceptance 1:
    Seed the store with an independent source asserting the same claim ->
    the step's effective confidence is boosted (+0.10).
    """
    trace = _trace("tr-corrob-boost")

    # 1. Seed store with prior independent fact from user/hardware
    user_signer = signer_factory.user_speech()
    t_signed = user_signer.sign(
        UnsignedPayload(
            content="driver-582.11 fixes wsl-crash",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce="user-corrob-nonce-001",
            created_at=time.time() - 100,
            trace_id=trace.trace_id,
        )
    )
    orch.memory_store.commit(t_signed)

    # 2. Web receipt arrives from 'ars-technica'
    orch.current_turn_receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-ars",
            source="ars-technica",
            output="ars-technica asserts driver-582.11 fixes wsl-crash on WSL2.",
        )
    ]

    # 3. LLM proposes inference step with attributed premise (proposed confidence 0.80)
    step_json = json.dumps(
        [
            {
                "premises": ["ars-technica asserts driver-582.11 fixes wsl-crash"],
                "s": "driver-582.11",
                "p": "fixes_issue",
                "o": "wsl-crash",
                "confidence": 0.80,
            }
        ]
    )
    fake_llm = FakeLLM(
        script=[
            TokenDelta(delta=step_json),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20)),
        ]
    )

    accepted, spoken = orch.run_deduction_step(
        goal="Can driver 582.11 fix my WSL crash?",
        trace=trace,
        llm=fake_llm,
    )

    # Must accept step with boosted confidence: 0.80 + 0.10 = 0.90!
    assert len(accepted) == 1
    assert accepted[0].confidence == 0.90

    # Intermediate in context has boosted confidence and structured Q-results
    ctx = orch.current_reasoning_context
    assert ctx is not None
    entry = ctx.resolve_premise("driver-582.11 fixes_issue wsl-crash")
    assert entry is not None
    assert entry.confidence == 0.90
    assert len(entry.critical_questions) == 3
    q2 = next(q for q in entry.critical_questions if "corroborated" in q["question"])
    assert q2["answer"] == "satisfied"
    assert q2["count"] >= 1
    assert t_signed.entry_id in q2["evidence_entry_ids"]

    # Final INFERRED fact committed with proof trace containing critical_questions
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
    assert row[0] == "driver-582.11 fixes_issue wsl-crash"
    assert row[2] == 0.90

    payload = json.loads(row[3])
    pt = payload["structured"]["proof_trace"]
    assert len(pt) == 1
    assert "critical_questions" in pt[0]
    assert len(pt[0]["critical_questions"]) == 3


def test_corroboration_docks_confidence_and_adds_condition_when_disputed(
    orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """WO-21 Phase 2 Functional Acceptance 2:
    Seed a disputing fact in store ->
    confidence is docked (-0.30), dispute named in conditions, and the final INFERRED
    commit (surviving >= 0.75 or refused if < 0.75) carries the dispute condition.
    """
    trace = _trace("tr-corrob-dispute")

    # 1. Seed store with a disputing fact from another source
    derived_signer = DerivedFactSigner(master_key=signer_factory.master_key)
    user_signer = signer_factory.user_speech()
    t_signed = user_signer.sign(
        UnsignedPayload(
            content="driver does not fix wsl-crash",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce="user-dispute-nonce-001",
            created_at=time.time() - 100,
            trace_id=trace.trace_id,
        )
    )
    orch.memory_store.commit(t_signed)

    dispute_fact = derived_signer.sign(
        UnsignedPayload(
            content="driver-582.11 does_not_fixes_issue wsl-crash",
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            confidence=0.95,
            source_entry_ids=[t_signed.entry_id],
            nonce="dispute-fact-nonce-001",
            created_at=time.time() - 50,
            trace_id=trace.trace_id,
            structured={"s": "driver-582.11", "p": "does_not_fixes_issue", "o": "wsl-crash"},
        )
    )
    orch.memory_store.commit(dispute_fact)

    # 2. Tool receipt arrives asserting the claim
    orch.current_turn_receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-forum",
            source="nvidia-forum",
            output="nvidia-forum asserts driver-582.11 fixes wsl-crash on Windows.",
        )
    ]

    # 3. LLM proposes step with proposed confidence 0.90 (docked by -0.30 -> 0.60)
    step_json = json.dumps(
        [
            {
                "premises": ["nvidia-forum asserts driver-582.11 fixes wsl-crash"],
                "s": "driver-582.11",
                "p": "fixes_issue",
                "o": "wsl-crash",
                "confidence": 0.90,
            }
        ]
    )
    fake_llm = FakeLLM(
        script=[
            TokenDelta(delta=step_json),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20)),
        ]
    )

    accepted, spoken = orch.run_deduction_step(
        goal="Does driver 582.11 fix the crash?",
        trace=trace,
        llm=fake_llm,
    )

    # Step is accepted, but confidence is docked: 0.90 - 0.30 = 0.60
    assert len(accepted) == 1
    assert accepted[0].confidence == 0.60

    # Dispute condition is added to conditions
    assert any(
        "contradicts" in c or "dispute" in c or "does_not" in c for c in accepted[0].conditions
    )

    # Because confidence 0.60 < 0.75 (CLEAR_AND_CONVINCING), finalize_chain refuses commit!
    assert spoken is not None
    assert "I think" in spoken
    assert "not sure enough to keep it" in spoken

    with orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED'
            """
        )
        assert cur.fetchall() == []


def test_etld_plus_one_extraction_and_alias_dedupe() -> None:
    """WO-22 Phase 0 Unit Tests:
    - Extracts eTLD+1 using embedded public suffix list.
    - Strips leading www., extracts host from URL, strips hyphens from registrable label.
    - Multi-part public suffixes (e.g. github.io, co.uk) properly respected.
    """
    assert extract_etld_plus_one("example.com") == ("example", "com")
    assert extract_etld_plus_one("example.org") == ("example", "org")
    assert extract_etld_plus_one("ars-technica.com") == ("arstechnica", "com")
    assert extract_etld_plus_one("arstechnica.com") == ("arstechnica", "com")
    assert extract_etld_plus_one("www.ars-technica.com") == ("arstechnica", "com")
    assert extract_etld_plus_one("https://sub.ars-technica.com/articles/123") == (
        "arstechnica",
        "com",
    )
    assert extract_etld_plus_one("alice.github.io") == ("alice", "github.io")
    assert extract_etld_plus_one("bob.github.io") == ("bob", "github.io")
    assert extract_etld_plus_one("news.bbc.co.uk") == ("bbc", "co.uk")
    assert extract_etld_plus_one("the-verge") == ("theverge", None)

    assert normalize_source_identity("example.com") == "example.com"
    assert normalize_source_identity("example.org") == "example.org"
    assert normalize_source_identity("ars-technica.com") == "arstechnica.com"
    assert normalize_source_identity("arstechnica.com") == "arstechnica.com"


def test_is_same_source_invariants() -> None:
    """WO-22 Phase 0 Invariants:
    1. Two different registrable domains must NEVER dedupe.
    2. Alias forms of the same domain ALWAYS dedupe.
    """
    # 1. Distinct registrable domains NEVER dedupe
    assert not is_same_source("example.com", "example.org")
    assert not is_same_source("sub.example.com", "sub.example.org")
    assert not is_same_source("alice.github.io", "bob.github.io")
    assert not is_same_source("reuters.com", "bloomberg.com")
    assert not is_same_source("theverge.com", "wired.com")

    # 2. Alias forms of the same domain ALWAYS dedupe
    assert is_same_source("ars-technica.com", "arstechnica.com")
    assert is_same_source("www.ars-technica.com", "arstechnica.com")
    assert is_same_source("https://arstechnica.com/gadgets", "ars-technica.com")
    assert is_same_source("news.arstechnica.com", "ars-technica.com")
    assert is_same_source("ars-technica", "arstechnica.com")
    assert is_same_source("the-verge", "theverge")
    assert is_same_source("example.com", "sub.example.com")


def test_corroboration_distinct_domains_never_dedupe_boosts(memory_store: MemoryStore) -> None:
    """WO-22 Phase 0 Functional Acceptance:
    Two distinct registrable domains (example.com vs example.org) do NOT dedupe;
    example.org provides independent corroboration to example.com claim -> Q2 SATISFIED.
    """
    step = InferenceStep(
        premises=["example.com asserts driver-582.11 fixes wsl-crash"],
        s="driver-582.11",
        p="fixes_issue",
        o="wsl-crash",
        confidence=0.80,
    )
    receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-ex-org",
            source="example.org",
            output="Report from example.org: confirmed that driver-582.11 fixes wsl-crash.",
        ),
    ]

    q_results = critical_questions(Scheme.AUTHORITY, step, store=memory_store, receipts=receipts)
    assert len(q_results) == 3

    # Q2: Independent corroboration MUST be SATISFIED (example.org != example.com)
    assert (
        q_results[1].question
        == "Is the claim corroborated by an independent grounding-eligible fact?"
    )
    assert q_results[1].answer == CQAnswer.SATISFIED
    assert q_results[1].count == 1
    assert "example.org" in q_results[1].sources

    # Confidence must be boosted (+0.10)
    eff_conf, conds = adjust_confidence(step.confidence, q_results)
    assert eff_conf == 0.90


def test_corroboration_alias_domains_dedupe_unknown(memory_store: MemoryStore) -> None:
    """WO-22 Phase 0 Functional Acceptance:
    Alias forms of the same domain (ars-technica.com vs arstechnica.com) DO dedupe;
    arstechnica.com receipt does NOT count as independent corroboration -> Q2 UNKNOWN.
    """
    step = InferenceStep(
        premises=["ars-technica.com asserts driver-582.11 fixes wsl-crash"],
        s="driver-582.11",
        p="fixes_issue",
        o="wsl-crash",
        confidence=0.80,
    )
    receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-ars-alias",
            source="arstechnica.com",
            output="Report from arstechnica.com: driver-582.11 fixes wsl-crash.",
        ),
    ]

    q_results = critical_questions(Scheme.AUTHORITY, step, store=memory_store, receipts=receipts)
    assert len(q_results) == 3

    # Q1: Matched via alias
    assert q_results[0].question == "Does a signed receipt prove the source asserted the claim?"
    assert q_results[0].answer == CQAnswer.SATISFIED

    # Q2: Deduped as same domain -> UNKNOWN
    assert (
        q_results[1].question
        == "Is the claim corroborated by an independent grounding-eligible fact?"
    )
    assert q_results[1].answer == CQAnswer.UNKNOWN
    assert q_results[1].count == 0

    # Confidence remains unadjusted
    eff_conf, conds = adjust_confidence(step.confidence, q_results)
    assert eff_conf == 0.80


def test_corroboration_subdomain_same_domain_dedupes_unknown(memory_store: MemoryStore) -> None:
    """WO-22 Phase 0 Functional Acceptance:
    Subdomains of the same registrable domain (sub.example.com vs example.com) DO dedupe;
    sub.example.com receipt does NOT count as independent corroboration -> Q2 UNKNOWN.
    """
    step = InferenceStep(
        premises=["example.com asserts driver-582.11 fixes wsl-crash"],
        s="driver-582.11",
        p="fixes_issue",
        o="wsl-crash",
        confidence=0.80,
    )
    receipts = [
        ToolReceipt(
            tool="fetch_url",
            call_id="call-fetch-sub",
            source="sub.example.com",
            output="Report from sub.example.com: driver-582.11 fixes wsl-crash.",
        ),
    ]

    q_results = critical_questions(Scheme.AUTHORITY, step, store=memory_store, receipts=receipts)
    assert len(q_results) == 3

    # Q2: Deduped -> UNKNOWN
    assert (
        q_results[1].question
        == "Is the claim corroborated by an independent grounding-eligible fact?"
    )
    assert q_results[1].answer == CQAnswer.UNKNOWN
    assert q_results[1].count == 0
