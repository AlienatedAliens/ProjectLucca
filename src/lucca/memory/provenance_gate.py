"""
Project Lucca — Provenance-Gated Memory Subsystem
Prevents ungrounded LLM narrative hallucinations from polluting long-term memory.
"""

import hmac
import hashlib
import time
from typing import List, Dict, Any
from lucca.core.schemas import MemoryProvenance, MemoryCommitPayload
from lucca.core.exceptions import ProvenanceViolationException, SecurityException

class MemoryProvenanceGate:
    def __init__(self, secret_key: str):
        self._secret_key = secret_key.encode("utf-8")
        self._committed_entries: Dict[str, MemoryCommitPayload] = {}

    def generate_signature(self, content: str, provenance: MemoryProvenance, timestamp: float) -> str:
        """Generates an internal HMAC-SHA256 signature for verified inputs."""
        payload = f"{content}:{provenance.value}:{timestamp}".encode("utf-8")
        return hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()

    def verify_and_commit(self, payload: MemoryCommitPayload) -> bool:
        """
        Hard gate evaluating memory commit requests.
        Enforces:
        1. Hard rejection of LLM_NARRATION.
        2. Cryptographic signature validity.
        """
        # Hard Invariant 1: Reject unverified LLM narration
        if payload.provenance == MemoryProvenance.LLM_NARRATION:
            raise ProvenanceViolationException(
                f"SECURITY REJECTION: LLM Narration is strictly forbidden from long-term memory write. "
                f"Attempted content: '{payload.content}'"
            )

        # Hard Invariant 2: Verify provenance signature
        expected_signature = self.generate_signature(
            payload.content, payload.provenance, payload.created_at_utc
        )
        if not hmac.compare_digest(payload.signature_token, expected_signature):
            raise SecurityException(
                "SECURITY REJECTION: Invalid or forged provenance signature token."
            )

        # Commit to internal registry
        self._committed_entries[payload.entry_id] = payload
        return True

    def create_verified_payload(self, content: str, provenance: MemoryProvenance) -> MemoryCommitPayload:
        """Factory for orchestrator to create valid, signed payloads for ground-truth observations."""
        if provenance == MemoryProvenance.LLM_NARRATION:
            raise ValueError("Cannot sign an LLM_NARRATION payload.")
        
        now = time.time()
        signature = self.generate_signature(content, provenance, now)
        entry_id = hashlib.sha256(f"{content}:{now}".encode("utf-8")).hexdigest()[:16]
        
        return MemoryCommitPayload(
            entry_id=entry_id,
            content=content,
            provenance=provenance,
            signature_token=signature,
            created_at_utc=now,
        )

    def get_all_committed(self) -> List[MemoryCommitPayload]:
        return list(self._committed_entries.values())
