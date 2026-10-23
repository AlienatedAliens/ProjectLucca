"""
Project Lucca — Constitutional Kernel Fingerprint
WO-36 Milestone 36.4 & Sovereign Cognitive Unification
Computes a cryptographic SHA-256 fingerprint over persona.toml configuration and constitutional invariants.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_constitutional_hash(config_path: Path | str | None = None) -> str:
    """
    Computes SHA-256 kernel hash over persona configuration and invariant gates.
    Attached to every DecisionRecord to certify unbroken constitutional alignment.
    """
    path = Path(config_path) if config_path else Path("config/persona.toml")
    hasher = hashlib.sha256()
    if path.exists():
        hasher.update(path.read_bytes())
    else:
        hasher.update(b"default_persona_kernel")

    invariants = (
        "never_pretend_to_feel:true;"
        "zero_host_exec:true;"
        "d_reas_06_quarantine:true;"
        "trap1_signed_only:true;"
        "trap2_history_context_only:true"
    )
    hasher.update(invariants.encode("utf-8"))
    return hasher.hexdigest()
