"""
Project Lucca v1.35.7 — Acceptance Gates and Functional Tests for Phase 1 Core Pipeline Hygiene
Spec: plans/2026-10-08_v1_35_7_epistemic_integrity_and_semantic_verification.md

Gates and Functional Verification covered:
1. G-V1357-HYGIENE:
   - Static: 0 instances of hardcoded is_conflict_top=False, topic=None,
     content=new_content, or told_false=False at the 4 cascade.py sites.
2. Defect 1 Functional Verification:
   - True Belnap TOP contradiction (e.g. conflicting configuration/numeric values)
     dynamically routes to review_queue with 'belnap_conflict_top' reason.
   - Candidate topic is dynamically extracted from candidate payload_json structured topic
     and triggers operator review when the topic is marked review-required.
   - Explicit user retraction/negation evaluates as Belnap F (not TOP), allowing
     autonomous supersession and spoken update generation.
3. Defect 2 Functional Verification:
   - Conversational filler / raw transcripts are stripped and canonicalized via
     _canonicalize_proposition before ASSISTANT_BELIEF commit. Raw conversational text
     is strictly banned from stored belief propositions.
4. Defect 3 Functional Verification:
   - Dynamic polarity propagation across all four cascade evidence sites:
     * Site 1: Breach retrospection in _query_history
     * Site 2: Autobiographical memory in _query_history / query_substrate_self_history
     * Site 3: Sandboxed fetch_url in query_substrate_3_web
     * Site 4: Sandboxed search_web in query_substrate_3_web
     * Belnap bilattice synthesis correctly derives FALSE on refutations and TRUE on assertions.
5. Defect 4 Functional Verification (G-V1357-RULE):
   - Opposing rule candidate pairs ("always use single quotes", "never use single quotes")
     are rejected from single-cluster merging.
   - Negative fixture: near-paraphrase pair is NOT flagged as a conflict.
   - RuleInducer mine_patterns preserves separate clusters for opposing tool arguments.
"""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

from lucca.core.belief_service import BeliefService
from lucca.core.cascade import (
    BelnapValue,
    EpistemicSearchCascade,
    EvidenceItem,
)
from lucca.core.schemas import Provenance, ToolResult, UnsignedPayload
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    UserSpeechSigner,
)
from lucca.memory.store import MemoryStore
from lucca.reasoning.induction import (
    RuleInducer,
    cluster_phrasings,
    is_rule_conflict,
)
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.senses.embed import LocalEmbeddingPort

TEST_KEY = b"01234567890123456789012345678901"


# ============================================================================
# Gate G-V1357-HYGIENE (Static AST & Source Gate)
# ============================================================================


def test_g_v1357_hygiene() -> None:
    """G-V1357-HYGIENE static gate.

    Asserts 0 instances of:
    - hardcoded is_conflict_top=False in belief_service.py check_contradictions
    - hardcoded topic=None in belief_service.py check_contradictions
    - content=new_content in reflection.py detect_and_handle_contradiction
    - told_false=False at the four cascade.py evidence sites
    """
    repo_root = Path(__file__).parent.parent

    # 1. Check belief_service.py
    bs_path = repo_root / "src" / "lucca" / "core" / "belief_service.py"
    bs_text = bs_path.read_text(encoding="utf-8")
    assert "is_conflict_top=False" not in bs_text, (
        "Found hardcoded is_conflict_top=False in belief_service.py"
    )
    assert "topic=None" not in bs_text, "Found hardcoded topic=None in belief_service.py"

    # 2. Check reflection.py
    refl_path = repo_root / "src" / "lucca" / "memory" / "reflection.py"
    refl_text = refl_path.read_text(encoding="utf-8")
    assert "content=new_content" not in refl_text, (
        "Found raw transcript ingestion content=new_content in reflection.py"
    )

    # 3. Check cascade.py
    casc_path = repo_root / "src" / "lucca" / "core" / "cascade.py"
    casc_text = casc_path.read_text(encoding="utf-8")
    casc_tree = ast.parse(casc_text, filename=str(casc_path))

    # Verify no EvidenceItem call passes a literal False to told_false
    told_false_literal_false: list[int] = []
    for node in ast.walk(casc_tree):
        if isinstance(node, ast.Call):
            func_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if func_name == "EvidenceItem":
                for kw in node.keywords:
                    if (
                        kw.arg == "told_false"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is False
                    ):
                        told_false_literal_false.append(kw.lineno)

    assert not told_false_literal_false, (
        f"Found hardcoded told_false=False in cascade.py EvidenceItem calls at lines: {told_false_literal_false}"
    )


# ============================================================================
# Defect 1 Functional Tests: Belief Service Belnap TOP & Topic Lock
# ============================================================================


def test_defect1_belnap_top_conflict_enqueues_review(tmp_path: Path) -> None:
    """Tests that Belnap TOP conflicts (e.g. conflicting settings) dynamically

    set is_conflict_top=True and route to review_queue with 'belnap_conflict_top'.
    """
    db_file = tmp_path / "test_defect1_top.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    embedder = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_KEY, embedding_port=embedder)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_KEY)
    bs = BeliefService(db=db, reflection_engine=refl)
    asst_signer = AssistantUtteranceSigner(master_key=TEST_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_KEY)

    now = time.time()
    # Seed an active belief: "The system theme is light mode."
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="The system theme is light mode.",
        structured={"importance": 0.5, "topic": "system_ui", "valid_from": now},
        trace_id="tr-seed-top",
        created_at=now,
        nonce="nonce-seed-top-1",
        confidence=0.9,
    )
    old_mid = store.commit(asst_signer.sign(payload))

    # Commit grounded user turn
    new_user_text = "The system theme is dark mode."
    user_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content=new_user_text,
        trace_id="tr-top-eval",
        created_at=now + 1.0,
        nonce="nonce-user-dark",
        confidence=1.0,
    )
    signed_user = user_signer.sign(user_payload)
    store.commit(signed_user)

    # Trigger contradiction check with the grounded entry_id
    trace = TurnTrace(trace_id="tr-top-eval", session_id="s1")
    bs.check_contradictions(
        new_entry_id=signed_user.entry_id,
        new_content=new_user_text,
        trace=trace,
    )

    # 1. Old belief must NOT be superseded
    with db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is None, "Old belief was unexpectedly superseded despite Belnap TOP conflict"
        assert row[1] is None

    # 2. review_queue must have a pending review with trigger_reason 'belnap_conflict_top'
    reviews = refl.list_pending_reviews()
    assert len(reviews) == 1, f"Expected 1 pending review, got {len(reviews)}"
    assert reviews[0]["belief_id"] == old_mid
    assert "belnap_conflict_top" in str(reviews[0]["trigger_reason"])
    assert reviews[0]["proposed_content"] == "The system theme is dark mode."

    db.close()


def test_defect1_candidate_topic_extracted_and_enforces_lock(tmp_path: Path) -> None:
    """Tests that topic is extracted from candidate payload_json and triggers

    operator topic lock (remediating the hardcoded topic=None defect).
    """
    db_file = tmp_path / "test_defect1_topic.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    embedder = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_KEY, embedding_port=embedder)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_KEY)
    bs = BeliefService(db=db, reflection_engine=refl)
    asst_signer = AssistantUtteranceSigner(master_key=TEST_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_KEY)

    # Operator locks topic 'network_policy'
    refl.mark_topic_review_required("network_policy")

    now = time.time()
    # Seed an active belief under topic 'network_policy' with importance < 0.7
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="Default proxy port is set to 8080.",
        structured={"importance": 0.4, "topic": "network_policy", "valid_from": now},
        trace_id="tr-seed-topic",
        created_at=now,
        nonce="nonce-seed-topic-1",
        confidence=0.9,
    )
    old_mid = store.commit(asst_signer.sign(payload))

    # Commit grounded user turn with candidate update
    new_user_text = "Default proxy port is set to 8080 with strict TLS."
    user_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content=new_user_text,
        trace_id="tr-topic-eval",
        created_at=now + 1.0,
        nonce="nonce-user-topic",
        confidence=1.0,
    )
    signed_user = user_signer.sign(user_payload)
    store.commit(signed_user)

    # Candidate belief updates proxy configuration
    trace = TurnTrace(trace_id="tr-topic-eval", session_id="s1")
    bs.check_contradictions(
        new_entry_id=signed_user.entry_id,
        new_content=new_user_text,
        trace=trace,
    )

    # review_queue must have a pending review because topic 'network_policy' is locked!
    reviews = refl.list_pending_reviews()
    assert len(reviews) == 1, "Expected review item to be queued due to topic lock"
    assert "topic_review_required_network_policy" in str(reviews[0]["trigger_reason"])

    db.close()


def test_defect1_retraction_autonomously_supersedes(tmp_path: Path) -> None:
    """Tests that explicit user retraction resolves to Belnap F (is_conflict_top=False),

    enabling autonomous supersession and queueing a spoken update.
    """
    db_file = tmp_path / "test_defect1_retract.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    embedder = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_KEY, embedding_port=embedder)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_KEY)
    bs = BeliefService(db=db, reflection_engine=refl)
    asst_signer = AssistantUtteranceSigner(master_key=TEST_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_KEY)

    now = time.time()
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="I think you live in the United States.",
        structured={"importance": 0.4, "topic": "residence", "valid_from": now},
        trace_id="tr-seed-retract",
        created_at=now,
        nonce="nonce-seed-retract-1",
        confidence=0.9,
    )
    old_mid = store.commit(asst_signer.sign(payload))

    # Commit grounded user retraction
    retract_text = "I don't live in the US, I live in Japan."
    user_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content=retract_text,
        trace_id="tr-retract-eval",
        created_at=now + 1.0,
        nonce="nonce-user-retract",
        confidence=1.0,
    )
    signed_user = user_signer.sign(user_payload)
    store.commit(signed_user)

    trace = TurnTrace(trace_id="tr-retract-eval", session_id="s1")
    bs.check_contradictions(
        new_entry_id=signed_user.entry_id,
        new_content=retract_text,
        trace=trace,
    )

    # 1. Old belief must be superseded
    with db.read_cursor() as cur:
        cur.execute("SELECT valid_to, superseded_by FROM memories WHERE memory_id = ?", (old_mid,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] is not None, "Old belief was not superseded on retraction"
        assert row[1] is not None

    # 2. Spoken update was generated
    assert len(bs.pending_spoken_updates) == 1
    spoken = bs.pending_spoken_updates[0]
    assert "revised a belief" in spoken.lower()

    # 3. No items stuck in review_queue
    assert len(refl.list_pending_reviews()) == 0

    db.close()


# ============================================================================
# Defect 2 Functional Tests: Verbatim Ingestion Ban & Canonicalization
# ============================================================================


def test_defect2_canonicalize_proposition_and_ban_verbatim(tmp_path: Path) -> None:
    """Tests that raw conversational transcripts are stripped of conversational

    filler and canonicalized into declarative statements before commit.
    """
    db_file = tmp_path / "test_defect2_canon.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    embedder = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_KEY, embedding_port=embedder)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_KEY)
    asst_signer = AssistantUtteranceSigner(master_key=TEST_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_KEY)

    # Test pure canonicalizer unit behavior
    assert (
        ReflectionEngine._canonicalize_proposition("actually, well, look, I prefer Neovim")
        == "I prefer Neovim."
    )
    assert (
        ReflectionEngine._canonicalize_proposition("hey, basically we migrated to AWS")
        == "We migrated to AWS."
    )
    assert (
        ReflectionEngine._canonicalize_proposition("um, no, the server is on port 9000.")
        == "No, the server is on port 9000."
    )

    # Test end-to-end autonomous revision commit in database
    now = time.time()
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="User preferred text editor is Vim.",
        structured={"importance": 0.4, "topic": "editor", "valid_from": now},
        trace_id="tr-seed-editor",
        created_at=now,
        nonce="nonce-seed-editor-1",
        confidence=0.9,
    )
    old_mid = store.commit(asst_signer.sign(payload))

    # Commit grounded user turn with conversational boilerplate
    raw_utterance = "actually, well, look, I prefer Neovim now"
    user_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content=raw_utterance,
        trace_id="tr-refl-canon",
        created_at=now + 1.0,
        nonce="nonce-user-canon",
        confidence=1.0,
    )
    signed_user = user_signer.sign(user_payload)
    store.commit(signed_user)

    is_queued, _ = refl.detect_and_handle_contradiction(
        old_belief_id=old_mid,
        new_content=raw_utterance,
        reason_entry_id=signed_user.entry_id,
        proposed_confidence=1.0,
        is_conflict_top=False,
        now=now + 10.0,
    )
    assert is_queued is False

    # Check the newly committed belief row in memories:
    with db.read_cursor() as cur:
        cur.execute("SELECT superseded_by FROM memories WHERE memory_id = ?", (old_mid,))
        sup_mid = cur.fetchone()[0]
        assert sup_mid is not None

        cur.execute(
            "SELECT m.content, p.provenance FROM memories m JOIN provenance_envelopes p "
            "ON m.entry_id = p.entry_id WHERE m.memory_id = ?",
            (sup_mid,),
        )
        row = cur.fetchone()
        assert row is not None
        committed_content = str(row[0])
        committed_prov = str(row[1])

        # Assert: committed content MUST be canonicalized, never verbatim raw utterance
        assert committed_content == "I prefer Neovim now."
        assert committed_content != raw_utterance
        assert committed_prov == "ASSISTANT_BELIEF"

    db.close()


# ============================================================================
# Defect 3 Functional Tests: Dynamic Polarity Across All 4 Cascade Sites
# ============================================================================


def test_defect3_cascade_polarity_at_all_four_sites(tmp_path: Path) -> None:
    """Tests dynamic polarity evaluation across all four cascade evidence sites:

    1. History breach retrospection in _query_history
    2. Autobiographical memory in query_substrate_self_history (refutation vs assertion)
    3. Sandboxed fetch_url in query_substrate_3_web
    4. Sandboxed search_web in query_substrate_3_web
    """
    db_file = tmp_path / "test_defect3_cascade.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    embedder = LocalEmbeddingPort()
    store = MemoryStore(db=db, master_key=TEST_KEY, embedding_port=embedder)
    cascade = EpistemicSearchCascade(memory_store=store)

    # ------------------------------------------------------------------------
    # Site 1: History breach retrospection in _query_history
    # ------------------------------------------------------------------------
    breach_signer = CoherenceBreachSigner(master_key=TEST_KEY)
    now = time.time()
    breach_payload = UnsignedPayload(
        provenance=Provenance.COHERENCE_BREACH,
        kind="coherence_breach",
        content="Execution failed: database cluster is disabled and unavailable.",
        structured={"topic": "database", "valid_from": now},
        trace_id="tr-breach-01",
        created_at=now,
        nonce="nonce-breach-01",
        confidence=1.0,
    )
    breach_mid = store.commit(breach_signer.sign(breach_payload))

    # Commit a resolution memory to serve as the foreign key target for superseded_by
    asst_signer = AssistantUtteranceSigner(master_key=TEST_KEY)
    fix_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_UTTERANCE,
        kind="assistant_utterance",
        content="Database cluster restored and available.",
        structured={"topic": "database", "valid_from": now - 1.0},
        trace_id="tr-breach-fix",
        created_at=now - 1.0,
        nonce="nonce-breach-fix",
        confidence=1.0,
    )
    fix_mid = store.commit(asst_signer.sign(fix_payload))

    # Mark superseded to simulate historical error retrospection
    with db.get_writer() as conn:
        conn.execute("UPDATE memories SET superseded_by = ? WHERE memory_id = ?", (fix_mid, breach_mid))

    breach_evidence = cascade.query_substrate_self_history(query_text="What was the wrong error with database?")
    assert len(breach_evidence) > 0
    breach_item = breach_evidence[0]
    assert breach_item.told_false is True, (
        f"Site 1 breach evidence expected told_false=True, got {breach_item.told_false}"
    )

    # ------------------------------------------------------------------------
    # Site 2: Autobiographical memory in query_substrate_self_history
    # ------------------------------------------------------------------------
    asst_signer = AssistantUtteranceSigner(master_key=TEST_KEY)
    # A. Negative assertion -> told_false=True
    neg_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="WebSocket protocol is unsupported.",
        structured={"topic": "websocket", "valid_from": now},
        trace_id="tr-asst-neg",
        created_at=now + 1.0,
        nonce="nonce-asst-neg",
        confidence=0.9,
    )
    store.commit(asst_signer.sign(neg_payload))

    neg_ev = cascade.query_substrate_self_history("Is WebSocket protocol functional?")
    assert len(neg_ev) > 0
    assert neg_ev[0].told_false is True
    assert neg_ev[0].told_true is False

    # B. Positive assertion -> told_true=True, told_false=False
    pos_payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="Multiplexing pipeline is verified.",
        structured={"topic": "pipeline", "valid_from": now},
        trace_id="tr-asst-pos",
        created_at=now + 2.0,
        nonce="nonce-asst-pos",
        confidence=0.9,
    )
    store.commit(asst_signer.sign(pos_payload))

    pos_ev = cascade.query_substrate_self_history("Is multiplexing pipeline active?")
    assert len(pos_ev) > 0
    assert pos_ev[0].told_true is True
    assert pos_ev[0].told_false is False

    # ------------------------------------------------------------------------
    # Sites 3 & 4: Sandboxed fetch_url & search_web in query_substrate_3_web
    # ------------------------------------------------------------------------
    mock_sandbox = MagicMock()
    cascade.sandbox = mock_sandbox

    # Site 3: fetch_url returning negative refutation
    mock_sandbox.execute.return_value = ToolResult(
        call_id="call-url-1",
        ok=True,
        elapsed_ms=12.5,
        content="Official Docs: XML-RPC endpoint is deprecated and unsupported.",
        structured={"status": 200},
    )
    url_items = cascade.query_substrate_3_web(
        "https://api.example.com/spec Is XML-RPC endpoint supported?"
    )
    assert len(url_items) == 1
    assert url_items[0].told_false is True, (
        f"Site 3 fetch_url expected told_false=True, got {url_items[0].told_false}"
    )
    assert url_items[0].told_true is False

    # Site 4: search_web returning negative refutation
    mock_sandbox.execute.return_value = ToolResult(
        call_id="call-web-1",
        ok=True,
        elapsed_ms=25.0,
        content="Search Results: Vendor does not support Python 2 anymore.",
        structured={"query": "python 2 support"},
    )
    web_items = cascade.query_substrate_3_web("Does vendor support Python 2?")
    assert len(web_items) == 1
    assert web_items[0].told_false is True, (
        f"Site 4 search_web expected told_false=True, got {web_items[0].told_false}"
    )
    assert web_items[0].told_true is False

    # ------------------------------------------------------------------------
    # Belnap bilattice synthesis test
    # ------------------------------------------------------------------------
    belnap_val, _, _ = cascade.synthesize("Is WebSocket protocol functional?", neg_ev)
    assert belnap_val == BelnapValue.FALSE

    belnap_val_pos, _, _ = cascade.synthesize("Is multiplexing pipeline active?", pos_ev)
    assert belnap_val_pos == BelnapValue.TRUE

    db.close()


# ============================================================================
# Defect 4 Functional Tests: Rule Induction Conflict Guard (G-V1357-RULE)
# ============================================================================


def test_defect4_induction_cluster_phrasings_no_false_merges() -> None:
    """G-V1357-RULE gate & functional test.

    1. Opposing rule candidate pairs are rejected from single-cluster merging.
    2. Negative fixture: near-paraphrase pairs are NOT flagged as conflicts.
    3. Multiple polarity oppositions (enable/disable, allow/block) are verified.
    """
    # 1. Opposing pair: always vs never
    opposing_1 = ["always use single quotes", "never use single quotes"]
    clusters_1 = cluster_phrasings(opposing_1, threshold=0.60)
    assert len(clusters_1) == 2, f"Opposing pair wrongly merged: {clusters_1}"

    # 2. Opposing pair: enable vs disable
    opposing_2 = ["enable telemetry logging", "disable telemetry logging"]
    clusters_2 = cluster_phrasings(opposing_2, threshold=0.60)
    assert len(clusters_2) == 2, f"Opposing pair wrongly merged: {clusters_2}"

    # 3. Opposing pair: allow vs block
    opposing_3 = ["port 8080 is allowed", "port 8080 is blocked"]
    clusters_3 = cluster_phrasings(opposing_3, threshold=0.60)
    assert len(clusters_3) == 2, f"Opposing pair wrongly merged: {clusters_3}"

    # 4. Negative fixture: compatible near-paraphrase must NOT be flagged as conflict
    assert is_rule_conflict("always use single quotes", "prefer single quotes") is False
    assert is_rule_conflict("enable telemetry logging", "telemetry logging enabled") is False

    # 5. Near-paraphrases merge properly into single cluster
    compatible = ["always use single quotes", "single quotes must always be used"]
    comp_clusters = cluster_phrasings(compatible, threshold=0.40)
    assert len(comp_clusters) == 1, f"Compatible pair failed to merge: {comp_clusters}"


def test_defect4_rule_inducer_mine_patterns_separates_opposing_rules(tmp_path: Path) -> None:
    """Tests that RuleInducer.mine_patterns preserves separate clusters when

    tool calls contain opposing argument values across decisions.
    """
    db_file = tmp_path / "test_inducer.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    # Seed decisions with opposing argument values
    with db.get_writer() as conn:
        for i in range(3):
            conn.execute(
                """
                INSERT INTO decisions (
                    decision_id, trace_id, session_id, ts, features_json, action,
                    probabilities_json, prediction_set_json, elapsed_us, router_version,
                    executed_path, tool_calls_json, tool_ok
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    f"dec-pos-{i}",
                    f"tr-pos-{i}",
                    "s1",
                    100.0 + i,
                    json.dumps({"intent": "format_code"}),
                    "tool_use",
                    "{}",
                    "[]",
                    100,
                    "v1",
                    "exec",
                    json.dumps([{"tool": "formatter", "args": {"quotes": "always use single quotes"}}]),
                ),
            )
        for i in range(3):
            conn.execute(
                """
                INSERT INTO decisions (
                    decision_id, trace_id, session_id, ts, features_json, action,
                    probabilities_json, prediction_set_json, elapsed_us, router_version,
                    executed_path, tool_calls_json, tool_ok
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    f"dec-neg-{i}",
                    f"tr-neg-{i}",
                    "s1",
                    200.0 + i,
                    json.dumps({"intent": "format_code"}),
                    "tool_use",
                    "{}",
                    "[]",
                    100,
                    "v1",
                    "exec",
                    json.dumps([{"tool": "formatter", "args": {"quotes": "never use single quotes"}}]),
                ),
            )

    lifecycle = RuleLifecycleManager(db)
    inducer = RuleInducer(
        db=db,
        rule_engine=lifecycle,
        min_frequency=2,
        similarity_threshold=0.60,
    )

    clusters = inducer.mine_patterns()
    # Must produce 2 separate clusters for the two opposing rules
    assert len(clusters) == 2, (
        f"Expected 2 separate clusters for opposing rules, got {len(clusters)}: {clusters}"
    )
    arg_vals = {c.arg_val for c in clusters}
    assert "always use single quotes" in arg_vals
    assert "never use single quotes" in arg_vals

    db.close()
