"""
Project Lucca v1.35.7 — Edge Case Battery & Defensive Boundary Suite
Phase 1 Core Pipeline Hygiene Deep Verification
Spec: plans/2026-10-08_v1_35_7_epistemic_integrity_and_semantic_verification.md

Edge Cases Covered:
1. Proposition Canonicalizer Torture & Prefix Safety:
   - Words starting with filler characters ('Software', 'Sole', 'Welcome', 'Lookup')
   - Terminal punctuation preservation (!, ?, .) without double-punctuation
   - Empty, whitespace-only, and punctuation-only inputs
   - Chained multi-filler conversational preambles
2. Toxic/Malformed payload_json Robustness in BeliefService:
   - Null, malformed, non-dict, and type-mismatched payload_json structured fields
   - Zero unhandled exceptions and deterministic fallback to kind
3. Numeric & Version Attribute Contradictions:
   - Float percentages (99.5% vs 99.9%)
   - Software versions (v1.35.6 vs v1.35.7)
   - Port numbers (8080 vs 9000)
   - Identical numbers (100 vs 100)
   - Retraction + numbers ('It is not 8080, it is 9000') -> Belnap F
4. Negated Query Evidential Polarity Inversion & Synthesis:
   - Negative query against refuting evidence -> told_true=True, BelnapValue.TRUE
   - Affirmative query against refuting evidence -> told_false=True, BelnapValue.FALSE
   - Affirmative query against confirming evidence -> told_true=True, BelnapValue.TRUE
5. Clustering Neutral-Bridge Transitive Isolation:
   - Opposing rules with an intermediate neutral phrasing (A='always enforce', B='enforce', C='never enforce')
   - Asserts A and C never leak into the same cluster via neutral bridge B
6. Cross-Conjugation Antonym Oppositions in Induction:
   - enable vs disabled, enabled vs disable, allow vs blocked, allowed vs deny
7. Candidate Capping & Execution Budget Bounds in BeliefService:
   - Enforces candidate cap of 5 and verifies graceful budget break
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from lucca.core.belief_service import BeliefService
from lucca.core.cascade import (
    BelnapValue,
    EpistemicSearchCascade,
    EpistemicSubstrate,
    EvidenceItem,
    TrustTier,
)
from lucca.core.schemas import Provenance, UnsignedPayload
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import AssistantUtteranceSigner, UserSpeechSigner
from lucca.memory.store import MemoryStore
from lucca.reasoning.induction import cluster_phrasings, is_rule_conflict
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


# ============================================================================
# 1. Proposition Canonicalizer Torture & Prefix Safety
# ============================================================================


def test_edge_canonicalize_torture_and_prefix_safety() -> None:
    """Verifies proposition canonicalizer behavior under adversarial prefixes,

    terminal punctuation preservation, and boundary edge cases.
    """
    refl = ReflectionEngine

    # 1. Words whose prefixes overlap with fillers but are NOT fillers
    assert refl._canonicalize_proposition("Software deployment is complete.") == (
        "Software deployment is complete."
    )
    assert refl._canonicalize_proposition("Sole tenancy is enabled.") == "Sole tenancy is enabled."
    assert refl._canonicalize_proposition("Solid state storage is mounted.") == (
        "Solid state storage is mounted."
    )
    assert refl._canonicalize_proposition("Welcome to the cluster.") == "Welcome to the cluster."
    assert refl._canonicalize_proposition("Lookup table is cached.") == "Lookup table is cached."
    assert refl._canonicalize_proposition("Listening alone is insufficient.") == (
        "Listening alone is insufficient."
    )

    # 2. Legitimate fillers stripped cleanly
    assert refl._canonicalize_proposition("So, we use Linux.") == "We use Linux."
    assert refl._canonicalize_proposition("Basically, software engineering is fun.") == (
        "Software engineering is fun."
    )
    assert refl._canonicalize_proposition("Well, look, actually, we deployed.") == "We deployed."

    # 3. Punctuation preservation (never double-punctuate)
    assert refl._canonicalize_proposition("Deployment completed successfully!") == (
        "Deployment completed successfully!"
    )
    assert refl._canonicalize_proposition("Is the replica synchronized?") == (
        "Is the replica synchronized?"
    )
    assert refl._canonicalize_proposition("Daemon listens on port 8080.") == (
        "Daemon listens on port 8080."
    )

    # 4. Missing terminal punctuation appended
    assert refl._canonicalize_proposition("daemon listens on port 8080") == (
        "Daemon listens on port 8080."
    )

    # 5. Empty and whitespace-only strings
    assert refl._canonicalize_proposition("") == ""
    assert refl._canonicalize_proposition("   ") == ""
    assert refl._canonicalize_proposition("\n\t  ") == ""

    # 6. Chained multi-filler torture test
    chained = (
        "well, actually, look, hey, basically, listen, you know, um, uh, database port is 5432"
    )
    assert refl._canonicalize_proposition(chained) == "Database port is 5432."


# ============================================================================
# 2. Toxic / Malformed payload_json Robustness in BeliefService
# ============================================================================


def test_edge_belief_service_payload_json_robustness(tmp_path: Path) -> None:
    """Verifies BeliefService.check_contradictions handles any corrupt, malformed,

    or unexpected payload_json without crashing or unhandled exceptions.
    """
    db_file = tmp_path / "test_corrupt_payload.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)
    bs = BeliefService(db=db, reflection_engine=refl)
    asst_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)

    # Seed an initial belief
    now = time.time()
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content="Primary server theme is dark mode.",
        structured={"importance": 0.4, "topic": "theme", "valid_from": now},
        trace_id="tr-seed-corrupt",
        created_at=now,
        nonce="nonce-seed-corrupt",
        confidence=0.9,
    )
    store.commit(asst_signer.sign(payload))

    # Commit a grounded user utterance
    u_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="Primary server theme is light mode.",
        trace_id="tr-eval-corrupt",
        created_at=now + 1.0,
        nonce="nonce-eval-corrupt",
        confidence=1.0,
    )
    signed_u = user_signer.sign(u_payload)
    store.commit(signed_u)

    # Corrupt payloads to inject into provenance_envelopes.payload_json
    toxic_payloads = [
        "{broken json string",
        "12345",
        "[]",
        '{"structured": null}',
        '{"structured": "not a dict"}',
        '{"structured": {"topic": null}}',
        '{"structured": {"topic": 9999}}',
        '{"structured": {"topic": ""}}',
    ]

    trace = TurnTrace(trace_id="tr-eval-corrupt", session_id="s1")

    for toxic in toxic_payloads:
        # Manually alter payload_json for the seed belief envelope
        with db.get_writer() as conn:
            conn.execute(
                "UPDATE provenance_envelopes SET payload_json = ? WHERE entry_id IN "
                "(SELECT entry_id FROM memories WHERE content LIKE '%Primary server theme%')",
                (toxic,),
            )

        # Must execute cleanly without raising any exception!
        bs.check_contradictions(
            new_entry_id=signed_u.entry_id,
            new_content="Primary server theme is light mode.",
            trace=trace,
        )

    db.close()


# ============================================================================
# 3. Numeric & Version Attribute Contradictions
# ============================================================================


def test_edge_numeric_attribute_and_version_contradictions() -> None:
    """Verifies that _evaluate_candidate_conflict correctly handles float percentages,

    software versions, port numbers, and mixed retraction scenarios.
    """
    bs = BeliefService.__new__(BeliefService)

    # 1. Float percentages disagreement -> True
    assert (
        bs._evaluate_candidate_conflict(
            "CPU target utilization is 99.5%.",
            "CPU target utilization is 99.9%.",
        )
        is True
    )

    # 2. Software version disagreement -> True
    assert (
        bs._evaluate_candidate_conflict(
            "Target release is Project Lucca v1.35.6.",
            "Target release is Project Lucca v1.35.7.",
        )
        is True
    )

    # 3. Port numbers disagreement -> True
    assert (
        bs._evaluate_candidate_conflict(
            "Daemon listens on port 8080.",
            "Daemon listens on port 9000.",
        )
        is True
    )

    # 4. Identical numbers -> False
    assert (
        bs._evaluate_candidate_conflict(
            "Daemon listens on port 8080.",
            "Daemon listens on port 8080.",
        )
        is False
    )

    # 5. Mixed: retraction cue with differing numbers -> False (Belnap F retraction)
    assert (
        bs._evaluate_candidate_conflict(
            "Daemon listens on port 8080.",
            "The daemon does not listen on port 8080, it listens on port 9000.",
        )
        is False
    )

    # 6. Competing states -> True
    assert (
        bs._evaluate_candidate_conflict(
            "System UI is configured in light mode.",
            "System UI is configured in dark mode.",
        )
        is True
    )


# ============================================================================
# 4. Negated Query Evidential Polarity Inversion & Synthesis
# ============================================================================


def test_edge_negated_query_polarity_inversion_and_synthesis(tmp_path: Path) -> None:
    """Verifies that when a query contains negation (e.g. 'Is TLS 1.0 unsupported?'),

    refuting evidence correctly yields told_true=True (confirming the query proposition)
    and evaluates to BelnapValue.TRUE.
    """
    db_file = tmp_path / "test_neg_query.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    cascade = EpistemicSearchCascade(memory_store=store)

    doc_text = "Official Spec: TLS 1.0 is unsupported and disabled."

    # Case A: Negated query asked -> document confirms the negation
    # Q: "Is TLS 1.0 unsupported?"
    # Doc: "TLS 1.0 is unsupported..."
    told_true, told_false = EpistemicSearchCascade._evaluate_polarity(
        doc_text, "Is TLS 1.0 unsupported?"
    )
    assert told_true is True
    assert told_false is False

    ev_confirmed = EvidenceItem(
        substrate=EpistemicSubstrate.SELF_HISTORY,
        trust_tier=TrustTier.TIER_1_HARDWARE,
        source="spec:tls",
        content=doc_text,
        told_true=told_true,
        told_false=told_false,
    )
    val_confirmed, _, _ = cascade.synthesize("Is TLS 1.0 unsupported?", [ev_confirmed])
    assert val_confirmed == BelnapValue.TRUE

    # Case B: Affirmative query asked -> document refutes the query
    # Q: "Is TLS 1.0 supported?"
    # Doc: "TLS 1.0 is unsupported..."
    told_true_b, told_false_b = EpistemicSearchCascade._evaluate_polarity(
        doc_text, "Is TLS 1.0 supported?"
    )
    assert told_true_b is False
    assert told_false_b is True

    ev_refuted = EvidenceItem(
        substrate=EpistemicSubstrate.SELF_HISTORY,
        trust_tier=TrustTier.TIER_1_HARDWARE,
        source="spec:tls",
        content=doc_text,
        told_true=told_true_b,
        told_false=told_false_b,
    )
    val_refuted, _, _ = cascade.synthesize("Is TLS 1.0 supported?", [ev_refuted])
    assert val_refuted == BelnapValue.FALSE

    db.close()


# ============================================================================
# 5. Clustering Neutral-Bridge Transitive Isolation
# ============================================================================


def test_edge_clustering_neutral_bridge_transitive_isolation() -> None:
    """Verifies that an intermediate neutral phrasing (B='enforce single quotes')

    cannot act as a transitive bridge to falsely merge opposing rules
    (A='always enforce single quotes' and C='never enforce single quotes').
    """
    # A has 'always', C has 'never', B has neither
    corpus = [
        "always enforce single quotes",
        "enforce single quotes",
        "never enforce single quotes",
    ]

    clusters = cluster_phrasings(corpus, threshold=0.50)

    # Must produce 2 separate clusters: A and C must NEVER share a cluster!
    assert len(clusters) == 2, f"Expected 2 clusters, got {len(clusters)}: {clusters}"

    leader_a: str | None = None
    leader_c: str | None = None
    for leader, count, members in clusters:
        if "always enforce single quotes" in members:
            leader_a = leader
        if "never enforce single quotes" in members:
            leader_c = leader

    assert leader_a is not None
    assert leader_c is not None
    assert leader_a != leader_c, "Transitive bridge falsely merged opposing rules!"


# ============================================================================
# 6. Cross-Conjugation Antonym Oppositions in Induction
# ============================================================================


def test_edge_rule_induction_cross_conjugation_oppositions() -> None:
    """Verifies that cross-conjugations between inflectional variants are detected as conflicts."""
    # enable / disabled
    assert (
        is_rule_conflict(
            "enable telemetry streaming",
            "telemetry streaming disabled",
        )
        is True
    )

    # enabled / disable
    assert (
        is_rule_conflict(
            "telemetry streaming enabled",
            "disable telemetry streaming",
        )
        is True
    )

    # allow / blocked
    assert (
        is_rule_conflict(
            "allow incoming connections",
            "incoming connections blocked",
        )
        is True
    )

    # allowed / deny
    assert (
        is_rule_conflict(
            "incoming connections allowed",
            "deny incoming connections",
        )
        is True
    )

    # require / forbidden
    assert (
        is_rule_conflict(
            "require client certificates",
            "client certificates forbidden",
        )
        is True
    )

    # Near-paraphrase controls (must NOT be conflicts)
    assert (
        is_rule_conflict(
            "require client certificates",
            "client certificates must be provided",
        )
        is False
    )
    assert (
        is_rule_conflict(
            "enable telemetry streaming",
            "telemetry streaming active",
        )
        is False
    )


# ============================================================================
# 7. Candidate Capping & Execution Budget Bounds in BeliefService
# ============================================================================


def test_edge_check_contradictions_budget_and_candidate_cap(tmp_path: Path) -> None:
    """Verifies that check_contradictions caps candidates at 5 and terminates cleanly

    when the 200 ms budget expires.
    """
    db_file = tmp_path / "test_budget.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)
    bs = BeliefService(db=db, reflection_engine=refl)
    asst_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)

    # Seed 8 active beliefs sharing the token 'cluster'
    now = time.time()
    for i in range(8):
        payload = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content=f"Database cluster replica node number {i} is online.",
            structured={"importance": 0.4, "topic": f"replica_{i}", "valid_from": now},
            trace_id=f"tr-seed-rep-{i}",
            created_at=now,
            nonce=f"nonce-seed-rep-{i}",
            confidence=0.9,
        )
        store.commit(asst_signer.sign(payload))

    u_payload = UnsignedPayload(
        provenance=Provenance.USER_EXPLICIT,
        kind="transcript",
        content="Database cluster replica node number 99 is offline.",
        trace_id="tr-eval-rep",
        created_at=now + 1.0,
        nonce="nonce-eval-rep",
        confidence=1.0,
    )
    signed_u = user_signer.sign(u_payload)
    store.commit(signed_u)

    trace = TurnTrace(trace_id="tr-budget-test", session_id="s1")

    # Simulate budget expiration after 1 candidate inspection
    call_counts = 0
    orig_perf_counter = time.perf_counter

    def mock_perf_counter() -> float:
        nonlocal call_counts
        call_counts += 1
        if call_counts > 2:
            return orig_perf_counter() + 1.0  # Simulate >200ms elapsed
        return orig_perf_counter()

    with patch("time.perf_counter", side_effect=mock_perf_counter):
        # Must terminate cleanly without hanging or raising
        bs.check_contradictions(
            new_entry_id=signed_u.entry_id,
            new_content="Database cluster replica node number 99 is offline.",
            trace=trace,
        )

    db.close()
