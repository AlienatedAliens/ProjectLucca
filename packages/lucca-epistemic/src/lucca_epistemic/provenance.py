"""RFC 8032 Ed25519 domain-separated provenance envelopes, public-key-only `ProvenanceGate`,
and cryptographically authenticated `OperatorApprovalToken` for procedural rule promotion.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from lucca_epistemic.exceptions import ProvenanceError, SignatureTamperError
from lucca_epistemic.schemas import (
    ELIGIBLE_PROVENANCE,
    Provenance,
    SignedPayload,
    UnsignedPayload,
)

ED25519_PREFIX: Final[str] = "ed25519:"
HMAC_PREFIX: Final[str] = "hmac-sha256:"
_HKDF_SALT: Final[bytes] = b"lucca-epistemic-rfc8032-v1"


def canonical_envelope_bytes(payload: UnsignedPayload) -> bytes:
    """Serialize an UnsignedPayload deterministically for signing/verification."""
    canonical = {
        "payload_id": payload.payload_id,
        "content": payload.content,
        "provenance": payload.provenance.value,
        "confidence": round(float(payload.confidence), 6),
        "trace_id": payload.trace_id,
        "created_at_utc": payload.created_at_utc,
        "metadata": payload.metadata,
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _derive_domain_seed(master_key: bytes, provenance: Provenance, purpose: bytes) -> bytes:
    if len(master_key) < 32:
        raise ValueError("master_key must be at least 32 bytes")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=purpose + b":" + provenance.value.encode("utf-8"),
    )
    return hkdf.derive(master_key)


def derive_domain_ed25519_private_key(
    master_key: bytes, provenance: Provenance
) -> Ed25519PrivateKey:
    seed = _derive_domain_seed(master_key, provenance, b"ed25519-domain-signer")
    return Ed25519PrivateKey.from_private_bytes(seed)


def derive_public_key_registry(master_key: bytes) -> dict[Provenance, bytes]:
    """Derive 32-byte raw Ed25519 public keys for every eligible Provenance domain."""
    return {
        prov: derive_domain_ed25519_private_key(master_key, prov).public_key().public_bytes_raw()
        for prov in ELIGIBLE_PROVENANCE
    }


class DomainSigner:
    """Domain-isolated RFC 8032 Ed25519 signer (retains no master key bytes)."""

    def __init__(self, provenance: Provenance, private_key: Ed25519PrivateKey) -> None:
        if provenance not in ELIGIBLE_PROVENANCE:
            raise ProvenanceError(f"Provenance '{provenance}' is not eligible for memory signing.")
        self.provenance = provenance
        self._private_key = private_key

    @property
    def public_key_bytes(self) -> bytes:
        return self._private_key.public_key().public_bytes_raw()

    def sign_payload(self, payload: UnsignedPayload) -> SignedPayload:
        if payload.provenance != self.provenance:
            raise ProvenanceError(
                f"Signer for '{self.provenance}' cannot sign '{payload.provenance}' payload."
            )
        msg = canonical_envelope_bytes(payload)
        sig_b64 = base64.b64encode(self._private_key.sign(msg)).decode("ascii")
        return SignedPayload(
            **payload.model_dump(),
            signature=f"{ED25519_PREFIX}{sig_b64}",
            signer_domain=self.provenance.value,
        )

    def sign(
        self,
        content: str,
        *,
        confidence: float = 1.0,
        trace_id: str = "",
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> SignedPayload:
        unsigned = UnsignedPayload(
            content=content,
            provenance=self.provenance,
            confidence=confidence,
            trace_id=trace_id,
            metadata=metadata or {},
        )
        return self.sign_payload(unsigned)


class SignerFactory:
    """Constructs domain-isolated Ed25519 signers without retaining the master key."""

    def __init__(self, signers: dict[Provenance, DomainSigner]) -> None:
        self._signers = dict(signers)

    @classmethod
    def from_master_key(cls, master_key: bytes) -> SignerFactory:
        signers = {
            prov: DomainSigner(prov, derive_domain_ed25519_private_key(master_key, prov))
            for prov in ELIGIBLE_PROVENANCE
        }
        return cls(signers)

    def public_keys(self) -> dict[Provenance, bytes]:
        return {prov: s.public_key_bytes for prov, s in self._signers.items()}

    def for_domain(self, provenance: Provenance) -> DomainSigner:
        if provenance not in self._signers:
            raise ProvenanceError(f"No signer registered for provenance '{provenance}'.")
        return self._signers[provenance]

    def user_explicit(self) -> DomainSigner:
        return self.for_domain(Provenance.USER_EXPLICIT)

    def tool_verified(self) -> DomainSigner:
        return self.for_domain(Provenance.TOOL_VERIFIED)


class ProvenanceGate:
    """Public-key-only memory barrier verifying RFC 8032 Ed25519 provenance envelopes.

    Optionally accepts `legacy_hmac_master_key` strictly for read-compatible migration
    of pre-Ed25519 symmetric records.
    """

    def __init__(
        self,
        public_keys: dict[Provenance, bytes],
        *,
        legacy_hmac_master_key: bytes | None = None,
    ) -> None:
        self._pubkeys: dict[Provenance, Ed25519PublicKey] = {
            prov: Ed25519PublicKey.from_public_bytes(raw) for prov, raw in public_keys.items()
        }
        self._legacy_hmac_keys: dict[Provenance, bytes] = {}
        if legacy_hmac_master_key is not None:
            self._legacy_hmac_keys = {
                prov: _derive_domain_seed(legacy_hmac_master_key, prov, b"hmac-legacy-signer")
                for prov in ELIGIBLE_PROVENANCE
            }

    @classmethod
    def from_master_key(
        cls, master_key: bytes, *, allow_legacy_hmac: bool = False
    ) -> ProvenanceGate:
        return cls(
            derive_public_key_registry(master_key),
            legacy_hmac_master_key=master_key if allow_legacy_hmac else None,
        )

    def verify(
        self,
        envelope: SignedPayload,
        *,
        expected_provenance: Provenance | None = None,
    ) -> bool:
        if envelope.provenance not in ELIGIBLE_PROVENANCE:
            raise ProvenanceError(
                f"Ineligible provenance '{envelope.provenance}' rejected at memory gate."
            )
        if expected_provenance is not None and envelope.provenance != expected_provenance:
            raise ProvenanceError(
                f"Expected provenance '{expected_provenance}', got '{envelope.provenance}'."
            )
        if envelope.signer_domain != envelope.provenance.value:
            raise SignatureTamperError(
                f"Signer domain mismatch: '{envelope.signer_domain}' != '{envelope.provenance}'."
            )

        msg = canonical_envelope_bytes(envelope)
        if envelope.signature.startswith(ED25519_PREFIX):
            pubkey = self._pubkeys.get(envelope.provenance)
            if pubkey is None:
                raise ProvenanceError(f"Missing public key for domain '{envelope.provenance}'.")
            try:
                raw_sig = base64.b64decode(envelope.signature[len(ED25519_PREFIX) :], validate=True)
                pubkey.verify(raw_sig, msg)
                return True
            except (ValueError, InvalidSignature) as exc:
                raise SignatureTamperError("Invalid Ed25519 provenance signature.") from exc

        if envelope.signature.startswith(HMAC_PREFIX) and self._legacy_hmac_keys:
            hkey = self._legacy_hmac_keys.get(envelope.provenance)
            if hkey is None:
                raise SignatureTamperError("Legacy HMAC key unavailable for domain.")
            expected = hmac.new(hkey, msg, hashlib.sha256).hexdigest()
            provided = envelope.signature[len(HMAC_PREFIX) :]
            if hmac.compare_digest(expected, provided):
                return True
            raise SignatureTamperError("Invalid legacy HMAC signature.")

        raise SignatureTamperError("Unsupported or unauthenticated signature scheme.")


@dataclass(frozen=True)
class OperatorApprovalToken:
    """Ed25519-authenticated operator approval token for `PENDING_APPROVAL -> ACTIVE` promotion."""

    rule_id: str
    rule_ast_sha256: str
    approved_by: str
    issued_at_utc: str
    signature_b64: str

    def canonical_bytes(self) -> bytes:
        body = {
            "rule_id": self.rule_id,
            "rule_ast_sha256": self.rule_ast_sha256,
            "approved_by": self.approved_by,
            "issued_at_utc": self.issued_at_utc,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def generate_operator_keypair() -> tuple[bytes, bytes]:
    """Return `(private_key_32b, public_key_32b)` for offline operator rule signing."""
    priv = Ed25519PrivateKey.generate()
    return (priv.private_bytes_raw(), priv.public_key().public_bytes_raw())


def sign_rule_approval(
    *,
    private_key_bytes: bytes,
    rule_id: str,
    rule_ast: str,
    approved_by: str = "local_operator",
) -> OperatorApprovalToken:
    priv = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    ast_sha = hashlib.sha256(rule_ast.encode("utf-8")).hexdigest()
    issued = datetime.now(UTC).isoformat()
    unsigned = OperatorApprovalToken(
        rule_id=rule_id,
        rule_ast_sha256=ast_sha,
        approved_by=approved_by,
        issued_at_utc=issued,
        signature_b64="",
    )
    sig_b64 = base64.b64encode(priv.sign(unsigned.canonical_bytes())).decode("ascii")
    return OperatorApprovalToken(
        rule_id=rule_id,
        rule_ast_sha256=ast_sha,
        approved_by=approved_by,
        issued_at_utc=issued,
        signature_b64=sig_b64,
    )


def verify_rule_approval_token(
    *,
    token: OperatorApprovalToken,
    public_key_bytes: bytes,
    expected_rule_id: str,
    expected_rule_ast: str,
) -> bool:
    if token.rule_id != expected_rule_id:
        raise SignatureTamperError("OperatorApprovalToken rule_id mismatch.")
    expected_sha = hashlib.sha256(expected_rule_ast.encode("utf-8")).hexdigest()
    if token.rule_ast_sha256 != expected_sha:
        raise SignatureTamperError("OperatorApprovalToken AST SHA-256 mismatch.")
    pub = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    try:
        raw_sig = base64.b64decode(token.signature_b64, validate=True)
        pub.verify(raw_sig, token.canonical_bytes())
        return True
    except (ValueError, InvalidSignature) as exc:
        raise SignatureTamperError("Invalid Ed25519 signature on OperatorApprovalToken.") from exc
