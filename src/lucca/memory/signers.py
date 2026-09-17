"""
Project Lucca — Capability Provenance Signers
Spec 03 §1, §2, §3, ADR-006
"""

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Final, Protocol

from lucca.core.exceptions import ProvenanceRejected
from lucca.core.schemas import Provenance, SignedPayload, UnsignedPayload

KNOWN_DEV_KEYS: Final[frozenset[str]] = frozenset(
    {
        "insecure_dev_key",
        "changeme",
        "test_secret_key_lucca_12345",
        "default_master_key",
    }
)


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if not salt:
        salt = b"\x00" * 32
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int = 32) -> bytes:
    t = b""
    okm = b""
    i = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


def derive_provenance_key(master_key: bytes, provenance: Provenance) -> bytes:
    """HKDF(SHA256, ikm=master, salt=b'lucca-v2', info=b'prov/' + provenance.value, L=32)."""
    prk = hkdf_extract(salt=b"lucca-v2", ikm=master_key)
    info = b"prov/" + provenance.value.encode("utf-8")
    return hkdf_expand(prk, info=info, length=32)


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
        self.master_key = master_key
        self.signer_id = signer_id
        # Precompute keys for allowed provenances
        self._keys: dict[Provenance, bytes] = {
            p: derive_provenance_key(master_key, p) for p in self.allowed_provenances
        }

    def sign(self, payload: UnsignedPayload) -> SignedPayload:
        if payload.provenance not in self.allowed_provenances:
            allowed = [p.value for p in self.allowed_provenances]
            raise ProvenanceRejected(
                f"Signer '{self.signer_id}' is not authorized to sign provenance "
                f"'{payload.provenance}'. Allowed: {allowed}"
            )

        canonical_bytes = canonicalize_unsigned_payload(payload)
        key = self._keys[payload.provenance]
        raw_sig = hmac.new(key, canonical_bytes, hashlib.sha256).digest()
        signature = base64.b64encode(raw_sig).decode("ascii")
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


class DerivedFactSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.memory.extraction."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.USER_DERIVED,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "extraction@lucca-core") -> None:
        super().__init__(master_key, signer_id)


class ToolResultSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.sandbox.client (host side)."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.TOOL_VERIFIED,
            Provenance.TOOL_CONTENT_UNTRUSTED,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "sandbox@lucca-core") -> None:
        super().__init__(master_key, signer_id)


class LispAssertionSigner(BaseProvenanceSigner):
    """Constructed ONLY in lucca.reasoning.executor."""

    allowed_provenances: frozenset[Provenance] = frozenset(
        {
            Provenance.LISP_ASSERTION,
        }
    )

    def __init__(self, master_key: bytes, signer_id: str = "rules@lucca-core") -> None:
        super().__init__(master_key, signer_id)
