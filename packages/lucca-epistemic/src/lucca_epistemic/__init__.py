"""Standalone cross-platform epistemic verification library extracted from Project Lucca."""

from lucca_epistemic.corroboration import (
    POLICY_TABLE_2D,
    deduplicate_syndicated_sources,
    evaluate_web_evidence_burden,
    meets_standard,
    required_standard,
    shingle_jaccard_similarity,
)
from lucca_epistemic.exceptions import (
    EpistemicError,
    ProvenanceError,
    SignatureTamperError,
)
from lucca_epistemic.hazard import (
    HazardVerdict,
    OpenVINOHazardClassifier,
    split_into_clauses,
)
from lucca_epistemic.provenance import (
    DomainSigner,
    OperatorApprovalToken,
    ProvenanceGate,
    SignerFactory,
    derive_public_key_registry,
    generate_operator_keypair,
    sign_rule_approval,
    verify_rule_approval_token,
)
from lucca_epistemic.schemas import (
    ELIGIBLE_PROVENANCE,
    PROOF_STANDARDS,
    BelnapValue,
    ClauseSupervisionVerdict,
    Hazard,
    ProofStandard,
    Provenance,
    SignedPayload,
    ToolReceipt,
    UnsignedPayload,
    WebEvidentiaryBurden,
    standard_for_confidence,
)
from lucca_epistemic.supervision import ReceiptSupervisor

__all__ = [
    "ELIGIBLE_PROVENANCE",
    "POLICY_TABLE_2D",
    "PROOF_STANDARDS",
    "BelnapValue",
    "ClauseSupervisionVerdict",
    "DomainSigner",
    "EpistemicError",
    "Hazard",
    "HazardVerdict",
    "OpenVINOHazardClassifier",
    "OperatorApprovalToken",
    "ProofStandard",
    "Provenance",
    "ProvenanceError",
    "ProvenanceGate",
    "ReceiptSupervisor",
    "SignatureTamperError",
    "SignedPayload",
    "SignerFactory",
    "ToolReceipt",
    "UnsignedPayload",
    "WebEvidentiaryBurden",
    "deduplicate_syndicated_sources",
    "derive_public_key_registry",
    "evaluate_web_evidence_burden",
    "generate_operator_keypair",
    "meets_standard",
    "required_standard",
    "shingle_jaccard_similarity",
    "sign_rule_approval",
    "split_into_clauses",
    "standard_for_confidence",
    "verify_rule_approval_token",
]
