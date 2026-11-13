"""Exceptions and warnings for `epistemic-guard`."""

from __future__ import annotations


class EpistemicGuardError(Exception):
    """Base error for epistemic-guard verification failures."""


# Backwards-compatible alias
EpistemicError = EpistemicGuardError


class ProvenanceError(EpistemicGuardError):
    """Raised when an ineligible or mismatched provenance domain attempts a memory write."""


class SignatureTamperError(ProvenanceError):
    """Raised when an Ed25519/HMAC signature or immutable SQLite row fails verification."""


class MerkleTamperError(EpistemicGuardError):
    """Raised when a receipt hash chain or Merkle inclusion proof fails verification."""


class ModelIntegrityError(EpistemicGuardError):
    """Raised when OpenVINO model files are missing (strict mode) or fail SHA-256 verification."""


class EpistemicModelUnavailableWarning(RuntimeWarning):
    """Emitted when OpenVINO INT8 weights are not installed and deterministic fallback is active."""
