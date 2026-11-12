"""
Project Lucca — Capability Provenance Signers
Spec 03 §1, §2, §3, ADR-006
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Final, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from lucca.core.exceptions import ProvenanceRejected
from lucca.core.schemas import Provenance, SignedPayload, UnsignedPayload
from lucca.memory.tokens import derive_ed25519_private_key, sign_ed25519_canonical

KNOWN_DEV_KEYS: Final[frozenset[str]] = frozenset(
    {
        "insecure_dev_key",
        "changeme",
        "test_secret_key_lucca_12345",
        "default_master_key",
    }
)


def canonicalize_payload_dict(d: Mapping[str, object]) -> bytes:
    """Canonical JSON encoding: sorted keys, compact separators, UTF-8."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonicalize_unsigned_payload(payload: UnsignedPayload | SignedPayload) -> bytes:
    dump = payload.model_dump(
        mode="json",
        exclude={"signature", "signer_id", "entry_id", "content_sha256"},
    )
    return canonicalize_payload_dict(dump)


class ProvenanceSigner(Protocol):
    signer_id: str
    allowed_provenances: frozenset[Provenance]

    def sign(self, payload: UnsignedPayload) -> SignedPayload: ...


class BaseProvenanceSigner:
    signer_id: str
    allowed_provenances: frozenset[Provenance]

    def __init__(self, master_key: bytes, signer_id: str) -> None:
        if len(master_key) < 32:
            raise ProvenanceRejected(f"Master key must be at least 32 bytes, got {len(master_key)}")
        self.signer_id = signer_id
        # Derive ONLY the capability-scoped Ed25519 private keys for allowed_provenances;
        # master_key is never retained on the signer instance (least-privilege isolation).
        self._signing_keys: dict[Provenance, Ed25519PrivateKey] = {
            p: derive_ed25519_private_key(master_key, p) for p in self.allowed_provenances
        }
        self._public_keys: dict[Provenance, Ed25519PublicKey] = {
            p: priv.public_key() for p, priv in self._signing_keys.items()
        }

    def public_keys(self) -> dict[Provenance, Ed25519PublicKey]:
        """Returns the public verification keys for this signer's allowed provenances."""
        return dict(self._public_keys)

    def public_key_bytes(self, provenance: Provenance) -> bytes:
        """Returns the raw 32-byte RFC 8032 Ed25519 public key for an allowed provenance."""
        if provenance not in self._public_keys:
            raise ProvenanceRejected(
                f"Signer '{self.signer_id}' has no public key for provenance '{provenance}'"
            )
        return self._public_keys[provenance].public_bytes(Encoding.Raw, PublicFormat.Raw)

    def sign(self, payload: UnsignedPayload) -> SignedPayload:
        if payload.provenance not in self.allowed_provenances:
            allowed = [p.value for p in self.allowed_provenances]
            raise ProvenanceRejected(
                f"Signer '{self.signer_id}' is not authorized to sign provenance "
                f"'{payload.provenance}'. Allowed: {allowed}"
            )

        canonical_bytes = canonicalize_unsigned_payload(payload)
        priv_key = self._signing_keys[payload.provenance]
        signature = sign_ed25519_canonical(priv_key, canonical_bytes)
        content_sha256 = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
        entry_id = hashlib.sha256(canonical_bytes).hexdigest()[:32]

        return SignedPayload(
            **payload.model_dump(),
            signer_id=self.signer_id,
            signature=signature,
            content_sha256=content_sha256,
            entry_id=entry_id,
        )


class UserSpeechSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.senses.asr_proxy."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.USER_EXPLICIT,
            Provenance.USER_EXPLICIT_LOWCONF,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "asr@lucca-core") -> None:
        super().__init__(master_key, signer_id)


def create_user_speech_signer(
    master_key: bytes, signer_id: str = "asr@lucca-core"
) -> UserSpeechSigner:
    """Authorized factory for constructing UserSpeechSigner in the memory domain."""
    return UserSpeechSigner(master_key=master_key, signer_id=signer_id)


class DerivedFactSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.memory.extraction."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.USER_DERIVED,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "extraction@lucca-core") -> None:
        super().__init__(master_key, signer_id)


def create_derived_fact_signer(
    master_key: bytes, signer_id: str = "ratification@lucca-core"
) -> DerivedFactSigner:
    """Authorized factory for constructing DerivedFactSigner (WO-21 Phase 3)."""
    return DerivedFactSigner(master_key=master_key, signer_id=signer_id)


class ToolResultSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.sandbox.client (host side)."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.TOOL_VERIFIED,
            Provenance.TOOL_CONTENT_UNTRUSTED,
            Provenance.ASSISTANT_ACTION,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "sandbox@lucca-core") -> None:
        super().__init__(master_key, signer_id)


def create_tool_result_signer(
    master_key: bytes, signer_id: str = "sandbox@lucca-core"
) -> ToolResultSigner:
    """Authorized factory for constructing ToolResultSigner outside the sandbox
    domain (WO-9 A9: the orchestrator signs ASSISTANT_ACTION receipts)."""
    return ToolResultSigner(master_key=master_key, signer_id=signer_id)


class LispAssertionSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.reasoning.executor.

    Signs deterministic rule-engine output (LISP_ASSERTION). LLM-proposed deduction
    steps are NOT signed here — they carry LLM_INFERRED_ASSERTION via
    InferredAssertionSigner, which is never grounding-eligible (P0 split).
    """

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.LISP_ASSERTION,
            Provenance.COHERENCE_BREACH,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "rules@lucca-core") -> None:
        super().__init__(master_key, signer_id)


def create_lisp_assertion_signer(
    master_key: bytes, signer_id: str = "rules@lucca-core"
) -> LispAssertionSigner:
    """Authorized factory for constructing LispAssertionSigner (WO-20 Phase 1)."""
    return LispAssertionSigner(master_key=master_key, signer_id=signer_id)


class InferredAssertionSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.core.orchestrator for LLM-proposed deduction steps.

    P0 provenance split: LLM-authored InferenceSteps are signed LLM_INFERRED_ASSERTION,
    which is memory-eligible (review queue) but never grounding-eligible. A step is
    promoted to the deterministic LISP_ASSERTION badge only when re-derived by a
    deterministic rule or Z3-verified.
    """

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.LLM_INFERRED_ASSERTION,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "orchestrator@lucca-core") -> None:
        super().__init__(master_key, signer_id)


def create_inferred_assertion_signer(
    master_key: bytes, signer_id: str = "orchestrator@lucca-core"
) -> InferredAssertionSigner:
    """Authorized factory for constructing InferredAssertionSigner (P0 provenance split)."""
    return InferredAssertionSigner(master_key=master_key, signer_id=signer_id)


class InferredFactSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.core.orchestrator to attest deduced facts (WO-20 Phase 4)."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.INFERRED,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "orchestrator@lucca-core") -> None:
        super().__init__(master_key, signer_id)


def create_inferred_fact_signer(
    master_key: bytes, signer_id: str = "orchestrator@lucca-core"
) -> InferredFactSigner:
    """Authorized factory for constructing InferredFactSigner (WO-20 Phase 4)."""
    return InferredFactSigner(master_key=master_key, signer_id=signer_id)


class AssistantUtteranceSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.core.orchestrator (narration finaliser) or test factory."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.ASSISTANT_UTTERANCE,
            Provenance.ASSISTANT_BELIEF,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "orchestrator@lucca-core") -> None:
        super().__init__(master_key, signer_id)

    def sign(self, payload: UnsignedPayload) -> SignedPayload:
        if payload.provenance == Provenance.ASSISTANT_BELIEF:
            if payload.confidence is None or not (0.0 <= payload.confidence <= 1.0):
                raise ProvenanceRejected(
                    f"ASSISTANT_BELIEF requires confidence in [0.0, 1.0], got {payload.confidence}"
                )
        return super().sign(payload)


def create_assistant_utterance_signer(
    master_key: bytes, signer_id: str = "orchestrator@lucca-core"
) -> AssistantUtteranceSigner:
    """Authorized factory for constructing AssistantUtteranceSigner in the memory domain."""
    return AssistantUtteranceSigner(master_key=master_key, signer_id=signer_id)


class CoherenceBreachSigner(BaseProvenanceSigner):
    """Constructed in supervisor or reasoning domain to attest coherence breaches."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.COHERENCE_BREACH,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "supervisor@lucca-core") -> None:
        super().__init__(master_key, signer_id)
