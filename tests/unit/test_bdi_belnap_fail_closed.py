"""Unit tests for WO-43 Phase 1.2: Belnap 4-Valued Epistemic Probe Unification
and NLI UNCERTAIN / Degraded Fail-Closed Consumer Remediation.
"""

from __future__ import annotations

from pathlib import Path

from lucca.core.belief_service import BeliefService
from lucca.core.cascade import (
    BelnapValue as CascadeBelnapValue,
)
from lucca.core.cascade import (
    EpistemicSearchCascade,
    EpistemicSubstrate,
    EvidenceItem,
    TrustTier,
    belnap_join_k,
    belnap_join_t,
    belnap_meet_k,
    belnap_meet_t,
    pool_evidence,
)
from lucca.core.coherence import ToolReceipt, detect_ungrounded_action_claims
from lucca.core.corroboration import compute_proposition_alignment
from lucca.core.memory_commit_service import MemoryCommitService
from lucca.core.schemas import (
    Provenance,
    UnsignedPayload,
    VerificationResult,
    VerifierLabel,
)
from lucca.core.self_diagnosis import DiagnosisEngine
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.core.user_model import UserModel
from lucca.memory.db import DatabaseManager
from lucca.memory.latent_probe import (
    BelnapLatentInvestigator,
    BelnapValue,
    information_join,
    information_meet,
    truth_join,
    truth_meet,
)
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.store import MemoryStore
from lucca.ports import SemanticVerifierPort
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"


class UncertainOrDegradedVerifier(SemanticVerifierPort):
    """Deterministic verifier returning UNCERTAIN or degraded=True for fail-closed tests."""

    def __init__(self, *, degraded: bool = False, label: VerifierLabel = VerifierLabel.UNCERTAIN) -> None:
        self.degraded = degraded
        self.label = label
        self.calls: list[tuple[str, str]] = []

    def check_consistency(self, *, premise: str, hypothesis: str) -> VerificationResult:
        self.calls.append((premise, hypothesis))
        return VerificationResult(
            label=self.label,
            confidence=0.42,
            degraded=self.degraded,
            premise=premise,
            hypothesis=hypothesis,
        )


def test_belnap_lattice_unification_between_latent_probe_and_cascade() -> None:
    """Proves cascade.py and latent_probe.py share the exact unified BelnapValue & operators."""
    assert CascadeBelnapValue is BelnapValue
    assert BelnapValue.TRUE == "T"
    assert BelnapValue.FALSE == "F"
    assert BelnapValue.NEITHER == BelnapValue.UNKNOWN == "BOT"
    assert BelnapValue.BOTH == BelnapValue.CONFLICT == "TOP"

    assert belnap_meet_k is information_meet
    assert belnap_join_k is information_join
    assert belnap_meet_t is truth_meet
    assert belnap_join_t is truth_join
    assert pool_evidence([BelnapValue.TRUE, BelnapValue.FALSE]) == BelnapValue.BOTH


def test_evaluate_nli_verdict_fail_closed_semantics() -> None:
    """Proves BelnapLatentInvestigator.evaluate_nli_verdict maps UNCERTAIN/degraded fail-closed."""
    uncertain_res = VerificationResult(
        label=VerifierLabel.UNCERTAIN,
        confidence=0.45,
        degraded=False,
        premise="p",
        hypothesis="h",
    )
    degraded_res = VerificationResult(
        label=VerifierLabel.NEUTRAL,
        confidence=0.0,
        degraded=True,
        premise="p",
        hypothesis="h",
    )

    assert (
        BelnapLatentInvestigator.evaluate_nli_verdict(uncertain_res, has_lexical_conflict=False)
        == BelnapValue.NEITHER
    )
    assert (
        BelnapLatentInvestigator.evaluate_nli_verdict(uncertain_res, has_lexical_conflict=True)
        == BelnapValue.BOTH
    )
    assert (
        BelnapLatentInvestigator.evaluate_nli_verdict(degraded_res, has_lexical_conflict=True)
        == BelnapValue.BOTH
    )


def test_memory_commit_service_quarantines_conflicting_fact_on_nli_uncertain(
    tmp_path: Path,
) -> None:
    """Proves MemoryCommitService routes conflicting (s, p, o) facts to review_queue when NLI is UNCERTAIN."""
    db = DatabaseManager(tmp_path / "mem_belnap.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    signer_factory = SignerFactory(master_key=TEST_MASTER_KEY)

    # 1. Commit initial fact ("I live in London") with no verifier contention
    svc_clean = MemoryCommitService(memory_store=store, signer_factory=signer_factory)
    t1 = TurnTrace(trace_id="tr-belnap-1", session_id="s1", origin="text", mode="transcript")
    svc_clean.commit_transcript("I live in London.", t1)
    svc_clean.maybe_extract_facts(t1)

    with db.read_cursor() as cur:
        cur.execute(
            "SELECT content FROM memories WHERE valid_to IS NULL AND superseded_by IS NULL AND content LIKE 'user lives_in %'"
        )
        active_rows = [r[0] for r in cur.fetchall()]
    assert active_rows == ["user lives_in London"]

    # 2. Now NLI verifier returns UNCERTAIN on a conflicting location ("I live in Paris.")
    uncertain_verifier = UncertainOrDegradedVerifier(degraded=False, label=VerifierLabel.UNCERTAIN)
    svc_uncertain = MemoryCommitService(
        memory_store=store,
        signer_factory=signer_factory,
        verifier=uncertain_verifier,
    )
    t2 = TurnTrace(trace_id="tr-belnap-2", session_id="s1", origin="text", mode="transcript")
    svc_uncertain.commit_transcript("I live in Paris.", t2)
    svc_uncertain.maybe_extract_facts(t2)

    # Active memory must NOT be overwritten; conflicting fact must be quarantined in review_queue
    with db.read_cursor() as cur:
        cur.execute(
            "SELECT content FROM memories WHERE valid_to IS NULL AND superseded_by IS NULL AND content LIKE 'user lives_in %'"
        )
        still_active = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT trigger_reason, proposed_content, status FROM review_queue")
        queued = cur.fetchall()

    assert still_active == ["user lives_in London"]
    assert len(queued) == 1
    assert "user.lives_in" in queued[0][0]
    assert queued[0][1] == "user lives_in Paris"
    assert queued[0][2] == "PENDING"


def test_belief_service_flags_review_and_clarification_on_nli_uncertain(
    tmp_path: Path,
) -> None:
    """Proves BeliefService fails closed to review_queue + Belnap clarification on UNCERTAIN NLI."""
    db = DatabaseManager(tmp_path / "belief_belnap.sqlite")
    db.migrate()
    store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=LocalEmbeddingPort())
    signer_factory = SignerFactory(master_key=TEST_MASTER_KEY)
    refl = ReflectionEngine(db=db, store=store, master_key=TEST_MASTER_KEY)

    belief_signer = signer_factory.assistant_utterance()
    old_belief = belief_signer.sign(
        UnsignedPayload(
            content="The primary database server runs on port 5432 in production.",
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            nonce="0123456789abcdef0123456789abcdef",
            created_at=1000.0,
            trace_id="tr-b0",
            structured={"topic": "database server"},
        )
    )
    store.commit(old_belief, now=1000.0)

    user_signer = signer_factory.user_speech()
    reason_payload = user_signer.sign(
        UnsignedPayload(
            content="The primary database server runs on port 6432 in production.",
            provenance=Provenance.USER_EXPLICIT,
            kind="fact",
            nonce="fedcba9876543210fedcba9876543210",
            created_at=1005.0,
            trace_id="tr-b1",
        )
    )
    store.commit(reason_payload, now=1005.0)

    uncertain_verifier = UncertainOrDegradedVerifier(degraded=True, label=VerifierLabel.UNCERTAIN)
    bs = BeliefService(db=db, reflection_engine=refl, verifier=uncertain_verifier)
    trace = TurnTrace(trace_id="tr-b1", session_id="s1", origin="text", mode="transcript")
    bs.check_contradictions(
        new_entry_id=reason_payload.entry_id,
        new_content="The primary database server runs on port 6432 in production.",
        trace=trace,
    )

    with db.read_cursor() as cur:
        cur.execute("SELECT proposed_content, status FROM review_queue")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "PENDING"
    assert any("contradiction" in msg.lower() for msg in bs.pending_spoken_updates)


def test_cascade_discounts_confidence_on_nli_uncertain() -> None:
    """Proves EpistemicSearchCascade discounts confidence (* 0.65) and marks belnap_state=NEITHER on UNCERTAIN."""
    uncertain_verifier = UncertainOrDegradedVerifier(degraded=False, label=VerifierLabel.UNCERTAIN)
    cascade = EpistemicSearchCascade(verifier=uncertain_verifier)

    ev_a = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="mem:1",
        content="Deployment target region is us-east primary cluster",
        confidence=0.90,
    )
    ev_b = EvidenceItem(
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="mem:2",
        content="Deployment target region is eu-west backup cluster",
        confidence=0.90,
    )
    cascade._annotate_active_memory_conflicts([ev_a, ev_b])

    assert ev_a.confidence == round(0.90 * 0.65, 4)
    assert ev_b.confidence == round(0.90 * 0.65, 4)
    assert ev_a.metadata.get("belnap_state") == "NEITHER"
    assert ev_a.metadata.get("nli_uncertain") is True


def test_corroboration_coherence_and_user_model_fail_closed_on_nli_uncertain(
    tmp_path: Path,
) -> None:
    """Proves corroboration, coherence, user_model, and self_diagnosis do not fail open on UNCERTAIN."""
    uncertain_verifier = UncertainOrDegradedVerifier(degraded=False, label=VerifierLabel.UNCERTAIN)

    # 1. Corroboration: non-verbatim partial overlap with UNCERTAIN verifier does not align
    is_aligned, score, _ = compute_proposition_alignment(
        claim="libxml2 patches heap overflow vulnerability",
        candidate_text="libxml2 release notes mention heap overflow",
        verifier=uncertain_verifier,
    )
    assert is_aligned is False
    assert score < 0.65

    # 2. Coherence: UNCERTAIN verifier never clears a contradicted receipt
    class _ContraThenUncertainVerifier(SemanticVerifierPort):
        def __init__(self) -> None:
            self.idx = 0

        def check_consistency(self, *, premise: str, hypothesis: str) -> VerificationResult:
            self.idx += 1
            if "Receipt 1" in premise:
                return VerificationResult(
                    label=VerifierLabel.CONTRADICTION,
                    confidence=0.92,
                    premise=premise,
                    hypothesis=hypothesis,
                )
            return VerificationResult(
                label=VerifierLabel.UNCERTAIN,
                confidence=0.40,
                premise=premise,
                hypothesis=hypothesis,
            )

    r_contra = ToolReceipt(
        tool="write_file",
        ok=True,
        args={"path": "config.toml"},
        output="Receipt 1: read-only mode",
    )
    r_uncertain = ToolReceipt(
        tool="write_file",
        ok=True,
        args={"path": "config.toml"},
        output="Receipt 2: status check",
    )
    claims = detect_ungrounded_action_claims(
        "I wrote the updated settings to config.toml.",
        [r_contra, r_uncertain],
        verifier=_ContraThenUncertainVerifier(),
        use_neural_verifier=True,
    )
    assert any(not c.grounded for c in claims)

    # 3. UserModel: UNCERTAIN verifier discounts score by 0.65
    um_clean = UserModel()
    um_clean.record_topic("Python async event loop internals", provenance=Provenance.USER_EXPLICIT)
    um_uncertain = UserModel(verifier=uncertain_verifier)
    um_uncertain.record_topic(
        "Python async event loop internals", provenance=Provenance.USER_EXPLICIT
    )
    assert um_uncertain.known_topics(query="Python async") == ["Python async event loop internals"]

    # 4. Self-diagnosis: UNCERTAIN verifier with negated symptom ("not overheating") fails closed
    toml_path = tmp_path / "faults.toml"
    toml_path.write_text(
        '[[fault]]\nid = "f1"\nname = "Thermal"\nsymptoms = ["system overheating"]\ncause = "Fan"\nchecks = []\n',
        encoding="utf-8",
    )
    diag_engine = DiagnosisEngine(fault_model_path=str(toml_path), verifier=uncertain_verifier)
    assert diag_engine.diagnose("The system is not overheating right now") == []
