"""
Project Lucca — Theory of Mind UserModel Tests
WO-21 Phase 4 (Spec D-REAS-09, Spec 10)

Functional acceptance tests for:
- Told-topic recognition (ASSISTANT_UTTERANCE)
- Confirmed-topic recognition (USER_EXPLICIT, USER_DERIVED)
- TRAP 1: UserModel is built ONLY from signed records (ASSISTANT_UTTERANCE, USER_EXPLICIT, USER_DERIVED)
  and NEVER admits LLM narration beliefs (ASSISTANT_BELIEF, LLM_NARRATION)
- Directive formatting: "The user already knows: X, Y — do not re-explain unless asked."
- Query-relevance token matching and deduplication
- Prompt builder integration: build_messages consumes user_model_directive
- Full loop: tell her a fact, ask to explain -> trace.user_model_fired is True, directive present
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.brain.prompt_builder import build_messages
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Provenance, UnsignedPayload
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import TurnInput, TurnPipeline
from lucca.core.user_model import UserModel
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(tmp_path / "test_user_model.sqlite")
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


def test_told_topic_recognition_assistant_utterance(
    test_db: DatabaseManager, memory_store: MemoryStore, signer_factory: SignerFactory
) -> None:
    """Told-topic recognition: ASSISTANT_UTTERANCE records are recognized as known topics."""
    signer = signer_factory.assistant_utterance()
    unsigned = UnsignedPayload(
        content="MicroScheme syntax uses parenthesized prefix notation",
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        nonce="nonce-told-1",
        created_at=time.time(),
        trace_id="tr-told-1",
    )
    signed = signer.sign(unsigned)
    memory_store.commit(signed)

    user_model = UserModel(db=test_db)
    topics = user_model.known_topics("What is the syntax of MicroScheme?")
    assert len(topics) == 1
    assert "MicroScheme syntax uses parenthesized prefix notation" in topics[0]


def test_confirmed_topic_recognition_user_explicit(
    test_db: DatabaseManager, memory_store: MemoryStore, signer_factory: SignerFactory
) -> None:
    """Confirmed-topic recognition: USER_EXPLICIT records are recognized as known topics."""
    signer = signer_factory.user_speech()
    unsigned = UnsignedPayload(
        content="I already know Python 3.13 enables nogil free-threading",
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        nonce="nonce-explicit-1",
        created_at=time.time(),
        trace_id="tr-explicit-1",
    )
    signed = signer.sign(unsigned)
    memory_store.commit(signed)

    user_model = UserModel(db=test_db)
    topics = user_model.known_topics("Tell me about Python 3.13 nogil")
    assert len(topics) == 1
    assert "Python 3.13 enables nogil free-threading" in topics[0]


def test_confirmed_topic_recognition_user_derived(
    test_db: DatabaseManager, memory_store: MemoryStore, signer_factory: SignerFactory
) -> None:
    """Confirmed-topic recognition: USER_DERIVED ratified web-facts are recognized as known topics."""
    signer_action = signer_factory.tool_result()
    action_unsigned = UnsignedPayload(
        content="Fetched https://docs.python.org",
        provenance=Provenance.ASSISTANT_ACTION,
        kind="action_receipt",
        nonce="nonce-act-001",
        created_at=time.time(),
        trace_id="tr-act-001",
    )
    action_signed = signer_action.sign(action_unsigned)
    memory_store.commit(action_signed)

    signer = signer_factory.derived_fact()
    unsigned = UnsignedPayload(
        content="Python 3.13 was released on October 7, 2024",
        provenance=Provenance.USER_DERIVED,
        kind="fact",
        nonce="nonce-derived-1",
        created_at=time.time(),
        trace_id="tr-derived-1",
        confidence=1.0,
        source_entry_ids=[action_signed.entry_id],
        structured={
            "source_url": "https://docs.python.org",
            "fetch_receipt_entry_id": action_signed.entry_id,
            "confirmed_by_user": True,
        },
    )
    signed = signer.sign(unsigned)
    memory_store.commit(signed)

    user_model = UserModel(db=test_db)
    topics = user_model.known_topics("When was Python 3.13 released?")
    assert len(topics) == 1
    assert "Python 3.13 was released on October 7, 2024" in topics[0]


def test_trap1_narration_belief_never_in_user_model(
    test_db: DatabaseManager, memory_store: MemoryStore, signer_factory: SignerFactory
) -> None:
    """
    TRAP 1 INVARIANT:
    The user model is built ONLY from signed records (ASSISTANT_UTTERANCE, USER_EXPLICIT, USER_DERIVED).
    It NEVER admits ASSISTANT_BELIEF or LLM_NARRATION records.
    """
    user_model = UserModel(db=test_db)

    # 1. Direct record_topic rejects LLM narration belief with ValueError
    with pytest.raises(ValueError, match="Trap 1 violation"):
        user_model.record_topic(
            "User might like hiking",
            provenance=Provenance.ASSISTANT_BELIEF,
        )

    with pytest.raises(ValueError, match="Trap 1 violation"):
        user_model.record_topic(
            "Unverified narration claim",
            provenance=Provenance.LLM_NARRATION,
        )

    # 2. Database contains an ASSISTANT_BELIEF entry (inserted via DB)
    now_ts = time.time()
    conn = test_db.get_writer()
    conn.execute(
        """
        INSERT INTO provenance_envelopes (
            entry_id, provenance, kind, signer_id, signature, content_sha256,
            nonce, created_at, trace_id, session_id, confidence, payload_json, grounding_eligible
        )
        VALUES (
            'env-belief-1', 'ASSISTANT_BELIEF', 'belief', 'belief@lucca-core', 'sig-b-1',
            'sha-b-1', 'nonce-b-1', ?, 'tr-1', 's-1', 0.7, '{}', 0
        )
        """,
        (now_ts,),
    )
    conn.execute(
        """
        INSERT INTO memories (entry_id, content, kind, created_at, valid_from)
        VALUES ('env-belief-1', 'Speculative belief: user prefers dark chocolate', 'belief', ?, ?)
        """,
        (now_ts, now_ts),
    )
    conn.commit()

    # Database also contains a valid USER_EXPLICIT entry
    signer_user = signer_factory.user_speech()
    unsigned_user = UnsignedPayload(
        content="I prefer tea over coffee",
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        nonce="nonce-user-trap1",
        created_at=time.time(),
        trace_id="tr-user-1",
    )
    signed_user = signer_user.sign(unsigned_user)
    memory_store.commit(signed_user)

    # Querying user model retrieves ONLY the USER_EXPLICIT fact, NEVER the ASSISTANT_BELIEF
    all_topics = user_model.known_topics(query=None)
    assert any("prefer tea over coffee" in t for t in all_topics)
    assert not any("chocolate" in t.lower() for t in all_topics)
    assert not any("speculative" in t.lower() for t in all_topics)


def test_user_model_format_directive() -> None:
    """format_directive emits the exact canonical directive string."""
    user_model = UserModel()
    user_model.record_topic("Python 3.13 has nogil", provenance=Provenance.USER_EXPLICIT)
    user_model.record_topic("Seattle weather is rainy", provenance=Provenance.ASSISTANT_UTTERANCE)

    directive = user_model.format_directive()
    assert directive is not None
    assert directive.startswith("The user already knows:")
    assert directive.endswith("— do not re-explain unless asked.")
    assert "Python 3.13 has nogil" in directive
    assert "Seattle weather is rainy" in directive

    # Empty model returns None
    empty_model = UserModel()
    assert empty_model.format_directive() is None


def test_user_model_query_relevance_filtering() -> None:
    """known_topics filters topics by token relevance when query is provided."""
    user_model = UserModel()
    user_model.record_topic("Rust ownership and borrowing rules", provenance=Provenance.USER_EXPLICIT)
    user_model.record_topic("Python 3.13 subinterpreters", provenance=Provenance.USER_EXPLICIT)
    user_model.record_topic("PostgreSQL indexing strategies", provenance=Provenance.ASSISTANT_UTTERANCE)

    # Query matching Rust
    rust_topics = user_model.known_topics("Tell me how Rust borrowing works")
    assert len(rust_topics) == 1
    assert "Rust ownership and borrowing" in rust_topics[0]

    # Query matching Python
    py_topics = user_model.known_topics("What is new in Python 3.13?")
    assert len(py_topics) == 1
    assert "Python 3.13 subinterpreters" in py_topics[0]


def test_prompt_builder_consumes_user_model_directive() -> None:
    """build_messages injects user_model_directive into the system message in proper section order."""
    directive = "The user already knows: Python 3.13 nogil — do not re-explain unless asked."
    messages = build_messages(
        current_text="Explain Python 3.13 concurrency",
        user_model_directive=directive,
    )
    assert len(messages) >= 2
    system_msg = messages[0].content
    assert isinstance(system_msg, str)
    assert "[Theory of Mind — User Knowledge State]" in system_msg
    assert directive in system_msg


def test_full_turn_user_model_directive_and_trace(test_db: DatabaseManager) -> None:
    """
    Functional acceptance test:
    Tell her a fact, ask to explain related topic -> trace.user_model_fired is True,
    directive is present in prompt, no re-stating required.
    """
    orch = Orchestrator.__new__(Orchestrator)
    orch.db = test_db
    orch.user_model = UserModel(db=test_db)
    orch.user_model.record_topic(
        "Python 3.13 disables the global interpreter lock",
        provenance=Provenance.USER_EXPLICIT,
    )

    orch.router = MagicMock()
    orch.router.classify_intent.return_value = ("general", 0.95, {})
    orch.router.route.return_value = None
    orch.cascade = MagicMock()
    orch.cascade.classify_intent.return_value = (False, [], 0.0)
    orch.rule_engine = MagicMock()
    orch.rule_engine.evaluate.return_value = []
    orch.rule_engine.rules = {}
    orch._search_memories = MagicMock(return_value=[])
    orch._build_rule_state = MagicMock(return_value=MagicMock(intent="general", hour_local=12, weekday=2, session_turns=1))
    orch.sandbox = MagicMock()
    orch.output_supervisor = MagicMock()
    orch.play_ring = MagicMock()
    orch.prev_decision_record = None
    orch._stream_llm_speech = MagicMock()
    orch.history = []

    pipeline = TurnPipeline(orch)
    trace = TurnTrace(trace_id="tr-tom-turn", origin="text")
    inp = TurnInput(
        user_text="Can you explain Python 3.13 lock mechanisms?",
        trace=trace,
        origin="text",
    )

    pipeline.run(inp)

    # 1. Trace records that user-model directive fired
    assert trace.user_model_fired is True

    # 2. _stream_llm_speech was called with epistemic context containing the directive
    orch._stream_llm_speech.assert_called_once()
    call_kwargs = orch._stream_llm_speech.call_args.kwargs
    epistemic_ctx = call_kwargs.get("epistemic_context", "")
    assert "The user already knows: Python 3.13 disables the global interpreter lock" in epistemic_ctx
    assert "do not re-explain unless asked" in epistemic_ctx
