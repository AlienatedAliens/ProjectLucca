"""Clean-venv test suite for standalone `lucca-epistemic` wheel (`WO-45 R-51`)."""

from __future__ import annotations

import os

import pytest
from lucca_epistemic import (
    Hazard,
    OpenVINOHazardClassifier,
    ProofStandard,
    Provenance,
    ProvenanceError,
    ProvenanceGate,
    ReceiptSupervisor,
    SignatureTamperError,
    SignerFactory,
    ToolReceipt,
    UnsignedPayload,
    deduplicate_syndicated_sources,
    evaluate_web_evidence_burden,
    generate_operator_keypair,
    sign_rule_approval,
    split_into_clauses,
    verify_rule_approval_token,
)


def test_ed25519_provenance_gate_public_key_only_and_tamper_rejection() -> None:
    master_key = os.urandom(32)
    factory = SignerFactory.from_master_key(master_key)
    gate = ProvenanceGate(factory.public_keys())

    # Gate holds zero private or master keys
    assert not hasattr(gate, "_master_key")
    assert gate._legacy_hmac_keys == {}

    env = factory.user_explicit().sign("User prefers dark mode.", trace_id="tr-01")
    assert env.signature.startswith("ed25519:")
    assert gate.verify(env, expected_provenance=Provenance.USER_EXPLICIT) is True

    # Tampered content must raise SignatureTamperError
    tampered = env.model_copy(update={"content": "User prefers light mode."})
    with pytest.raises(SignatureTamperError):
        gate.verify(tampered)

    # LLM_NARRATION is rejected by construction
    ineligible = UnsignedPayload(content="Hallucinated memory", provenance=Provenance.LLM_NARRATION)
    with pytest.raises(ProvenanceError):
        factory.for_domain(Provenance.LLM_NARRATION)
    fake_signed = env.model_copy(
        update={
            "provenance": Provenance.LLM_NARRATION,
            "signer_domain": Provenance.LLM_NARRATION.value,
        }
    )
    with pytest.raises(ProvenanceError):
        gate.verify(fake_signed)


def test_operator_approval_token_ed25519_authentication() -> None:
    priv, pub = generate_operator_keypair()
    ast_src = '(rule open-calc (when (= intent "calc")) (call "calc.exe"))'
    tok = sign_rule_approval(
        private_key_bytes=priv,
        rule_id="rule-001",
        rule_ast=ast_src,
        approved_by="operator",
    )
    assert (
        verify_rule_approval_token(
            token=tok,
            public_key_bytes=pub,
            expected_rule_id="rule-001",
            expected_rule_ast=ast_src,
        )
        is True
    )

    with pytest.raises(SignatureTamperError):
        verify_rule_approval_token(
            token=tok,
            public_key_bytes=pub,
            expected_rule_id="rule-001",
            expected_rule_ast='(rule mutated (call "rm -rf"))',
        )


def test_openvino_cpu_fallback_and_multiclause_hazard_pooling() -> None:
    clauses = split_into_clauses(
        "What year was Python released, and what is the adult warfarin dosage in mg?"
    )
    assert len(clauses) >= 1

    clf = OpenVINOHazardClassifier(device="CPU")
    verdict = clf.evaluate(
        "What year was Python 3.12 released; also what is the maximum adult warfarin dosage in mg?"
    )
    assert verdict.hazard == Hazard.HIGH
    assert verdict.device in ("CPU", "HEURISTIC_CPU")
    assert verdict.latency_ms >= 0.0


def test_syndicated_near_duplicate_deduplication_and_web_burden() -> None:
    wire_copy = (
        "The central reserve announced on Thursday that overnight lending rates will remain "
        "unchanged at 4.25 percent through the third fiscal quarter."
    )
    deduped, collapsed = deduplicate_syndicated_sources(
        [
            ("reuters.com", wire_copy),
            ("yahoo.com", wire_copy),
            ("msn.com", wire_copy + " Markets reacted calmly."),
        ]
    )
    assert len(deduped) == 1
    assert collapsed == 2

    burden = evaluate_web_evidence_burden(
        "What is the maximum adult warfarin dosage in mg?",
        [
            {"url": "https://mirror1.example.com/a", "snippet": wire_copy},
            {"url": "https://mirror2.example.org/b", "snippet": wire_copy},
            {"url": "https://mirror3.example.net/c", "snippet": wire_copy},
        ],
        device="CPU",
    )
    assert burden.hazard == Hazard.HIGH
    assert burden.required_casual_standard == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert burden.deduplicated_duplicates_collapsed == 2
    assert burden.independent_sources_count == 1
    assert burden.meets_casual_burden is False


def test_clause_level_receipt_supervisor_cpu() -> None:
    sup = ReceiptSupervisor(device="CPU")
    receipts = [
        ToolReceipt(tool="write_file", ok=True, args={"path": "notes.txt"}, output="ok"),
    ]
    bad = sup.verify_narration(
        "I saved your summary to notes.txt; I also deleted backup.sql.",
        receipts=receipts,
    )
    assert bad.is_valid is False
    assert len(bad.unsupported_claims) == 1

    good = sup.verify_narration(
        "I saved your summary to notes.txt. Let me know if you want me to delete backup.sql.",
        receipts=receipts,
    )
    assert good.is_valid is True
