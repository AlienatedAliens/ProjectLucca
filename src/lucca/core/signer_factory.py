"""
Project Lucca — Signer Factory (F-ARCH-103, WO-18b)
Spec 03 §1, §2, §3, ADR-006

Provides a centralized, fail-closed factory for capability provenance signers.
Constructed once at runtime initialization with the system master key.
Enforces fail-closed semantics: refuses startup with missing or short master keys
unless explicitly running in development mode (LUCCA_ENV=dev).
"""

from __future__ import annotations

import os
from typing import Final

from lucca.memory.signers import (
    AssistantUtteranceSigner,
    CoherenceBreachSigner,
    LispAssertionSigner,
    ToolResultSigner,
    UserSpeechSigner,
    create_assistant_utterance_signer,
    create_lisp_assertion_signer,
    create_tool_result_signer,
    create_user_speech_signer,
)

DEV_MASTER_KEY: Final[bytes] = b"01234567890123456789012345678901"


class SignerFactory:
    """Centralized factory constructing capability provenance signers."""

    def __init__(self, master_key: bytes | None = None) -> None:
        key = master_key
        if key is None or len(key) < 32:
            env = os.environ.get("LUCCA_ENV") or os.environ.get("LUCCA_ENV__MODE", "dev")
            if env != "dev":
                raise ValueError(
                    f"Master key must be at least 32 bytes (got {len(key) if key is not None else 0}); "
                    f"dev fallback prohibited when LUCCA_ENV={env!r} (must be 'dev')."
                )
            key = DEV_MASTER_KEY
        self._master_key: bytes = bytes(key)

    @property
    def master_key(self) -> bytes:
        """Returns the active 32-byte master key."""
        return self._master_key

    def user_speech(self, signer_id: str = "asr@lucca-core") -> UserSpeechSigner:
        """Creates an authorized UserSpeechSigner."""
        return create_user_speech_signer(master_key=self._master_key, signer_id=signer_id)

    def tool_result(self, signer_id: str = "sandbox@lucca-core") -> ToolResultSigner:
        """Creates an authorized ToolResultSigner."""
        return create_tool_result_signer(master_key=self._master_key, signer_id=signer_id)

    def assistant_utterance(
        self, signer_id: str = "orchestrator@lucca-core"
    ) -> AssistantUtteranceSigner:
        """Creates an authorized AssistantUtteranceSigner."""
        return create_assistant_utterance_signer(master_key=self._master_key, signer_id=signer_id)

    def coherence_breach(self, signer_id: str = "supervisor@lucca-core") -> CoherenceBreachSigner:
        """Creates an authorized CoherenceBreachSigner."""
        return CoherenceBreachSigner(master_key=self._master_key, signer_id=signer_id)

    def lisp_assertion(self, signer_id: str = "rules@lucca-core") -> LispAssertionSigner:
        """Creates an authorized LispAssertionSigner (WO-20 Phase 1)."""
        return create_lisp_assertion_signer(master_key=self._master_key, signer_id=signer_id)

