"""Exceptions for standalone `lucca-epistemic` provenance and supervision gates."""

from __future__ import annotations


class EpistemicError(Exception):
    """Base error for epistemic verification failures."""


class ProvenanceError(EpistemicError):
    """Raised when an envelope lacks eligible provenance or required credentials."""


class SignatureTamperError(ProvenanceError):
    """Raised when an RFC 8032 Ed25519 or HMAC provenance signature fails verification."""
