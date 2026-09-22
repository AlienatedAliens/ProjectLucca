"""
Project Lucca — Provenance Verification Gate
Spec 03 §4, Spec 04 §3, ADR-006
"""

import base64
import hashlib
import hmac
import time
from typing import Final

from lucca.core.exceptions import ProvenanceRejected
from lucca.core.schemas import (
    FACT_PREDICATES,
    MEMORY_ELIGIBLE,
    Admitted,
    LLMNarration,
    Provenance,
    SignedPayload,
)
from lucca.memory.signers import canonicalize_unsigned_payload, derive_provenance_key

# Closed predicate list from Spec 04 §3 — canonical definition lives in
# core.schemas (FACT_PREDICATES) so the gate and the tool manifest share one
# source of truth (WO-9 A2).
PREDICATES: Final[frozenset[str]] = FACT_PREDICATES

NONCE_RETENTION_SECONDS = 86400.0  # 24 hours


class ProvenanceGate:
    """
    Gatekeeper that admits only cryptographically verified, fresh, replay-free,
    and structurally valid payloads into persistent memory.
    """

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) < 32:
            raise ProvenanceRejected(f"Master key must be at least 32 bytes, got {len(master_key)}")
        self.master_key = master_key
        # Verification keys derived via HKDF
        self._keys: dict[Provenance, bytes] = {
            p: derive_provenance_key(master_key, p) for p in Provenance
        }
        # Nonce replay tracking: (nonce, content_sha256) -> seen_timestamp
        self._seen_nonces: dict[tuple[str, str], float] = {}

    def _prune_nonces(self, now: float) -> None:
        cutoff = now - NONCE_RETENTION_SECONDS
        to_delete = [k for k, ts in self._seen_nonces.items() if ts < cutoff]
        for k in to_delete:
            del self._seen_nonces[k]

    def admit(self, payload: SignedPayload | LLMNarration, now: float | None = None) -> Admitted:
        current_time = now if now is not None else time.time()

        # 1. Type check: LLMNarration is unconditionally forbidden
        if isinstance(payload, LLMNarration):
            raise ProvenanceRejected("LLM_NARRATION is forbidden from entering memory")

        if not isinstance(payload, SignedPayload):
            raise ProvenanceRejected(f"Expected SignedPayload, got {type(payload).__name__}")

        # 2. Eligibility check
        if payload.provenance not in MEMORY_ELIGIBLE:
            raise ProvenanceRejected(f"Provenance '{payload.provenance}' is not memory eligible")

        # 3. Structural re-computation checks
        canonical_bytes = canonicalize_unsigned_payload(payload)
        expected_entry_id = hashlib.sha256(canonical_bytes).hexdigest()[:32]
        if payload.entry_id != expected_entry_id:
            raise ProvenanceRejected(
                f"Tampered entry_id: expected {expected_entry_id}, got {payload.entry_id}"
            )

        expected_content_sha = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
        if payload.content_sha256 != expected_content_sha:
            raise ProvenanceRejected(
                f"Tampered content_sha256: expected {expected_content_sha}, "
                f"got {payload.content_sha256}"
            )

        # 4. Cryptographic HMAC verification
        key = self._keys[payload.provenance]
        expected_raw_sig = hmac.new(key, canonical_bytes, hashlib.sha256).digest()
        expected_sig = base64.b64encode(expected_raw_sig).decode("ascii")

        if not hmac.compare_digest(payload.signature, expected_sig):
            raise ProvenanceRejected("Invalid cryptographic signature on payload")

        # 5. Freshness check: |now - created_at| <= 300s
        age = abs(current_time - payload.created_at)
        if age > 300.0:
            raise ProvenanceRejected(f"Payload timestamp expired ({age:.1f}s > 300.0s)")

        # 6. Replay protection
        self._prune_nonces(current_time)
        replay_key = (payload.nonce, payload.content_sha256)
        if replay_key in self._seen_nonces:
            raise ProvenanceRejected("Replay detected: duplicate nonce and content within 24h")
        self._seen_nonces[replay_key] = current_time

        # 7. Semantic / Structural checks
        if payload.provenance == Provenance.USER_DERIVED:
            if not payload.source_entry_ids:
                raise ProvenanceRejected("USER_DERIVED payload requires non-empty source_entry_ids")
            if payload.structured is not None and "p" in payload.structured:
                pred = payload.structured["p"]
                if isinstance(pred, str) and pred not in PREDICATES:
                    raise ProvenanceRejected(f"Predicate '{pred}' is not in closed PREDICATES list")

        if payload.provenance == Provenance.ASSISTANT_BELIEF:
            if payload.confidence is None or not (0.60 <= payload.confidence <= 1.0):
                raise ProvenanceRejected(
                    f"ASSISTANT_BELIEF requires confidence in [0.60, 1.0], got {payload.confidence}"
                )

        return Admitted(payload=payload)
