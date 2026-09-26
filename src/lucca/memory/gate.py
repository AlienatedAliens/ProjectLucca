"""
Project Lucca — Provenance Verification Gate
Spec 03 §4, Spec 04 §3, ADR-006
"""

import base64
import hashlib
import hmac
import re
import time
from typing import Final

import structlog

from lucca.core.exceptions import ProvenanceRejected
from lucca.core.schemas import (
    FACT_PREDICATES,
    MEMORY_ELIGIBLE,
    Admitted,
    LLMNarration,
    Provenance,
    SignedPayload,
    canonicalize_predicate,
    is_valid_predicate,
)
from lucca.memory.signers import canonicalize_unsigned_payload, derive_provenance_key

logger = structlog.get_logger(__name__)

# Baseline predicate set; open predicates validated via is_valid_predicate (WO-17 Phase 2).
PREDICATES: Final[frozenset[str]] = FACT_PREDICATES

NONCE_RETENTION_SECONDS = 86400.0  # 24 hours


class ProvenanceGate:
    """
    Gatekeeper that admits only cryptographically verified, fresh, replay-free,
    and structurally valid payloads into persistent memory.
    """

    def __init__(self, master_key: bytes, db: object = None) -> None:
        if len(master_key) < 32:
            raise ProvenanceRejected(f"Master key must be at least 32 bytes, got {len(master_key)}")
        self.master_key = master_key
        self.db = db
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

    def admit(
        self,
        payload: SignedPayload | LLMNarration,
        now: float | None = None,
        db: object = None,
    ) -> Admitted:
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
                if isinstance(pred, str):
                    canon_pred = canonicalize_predicate(pred)
                    if not is_valid_predicate(canon_pred):
                        raise ProvenanceRejected(
                            f"Predicate '{pred}' is not a valid predicate slug"
                        )
            # WO-21 Phase 3: Ratified web-fact receipt validation
            if payload.structured is not None and payload.structured.get("confirmed_by_user"):
                receipt_id = payload.structured.get("fetch_receipt_entry_id")
                if not receipt_id or not str(receipt_id).strip():
                    raise ProvenanceRejected(
                        "Ratified USER_DERIVED payload requires valid fetch_receipt_entry_id"
                    )
                effective_db = db if db is not None else getattr(self, "db", None)
                found = False
                if effective_db is not None and hasattr(effective_db, "read_cursor"):
                    try:
                        with effective_db.read_cursor() as cur:
                            cur.execute(
                                "SELECT entry_id FROM provenance_envelopes WHERE entry_id = ?",
                                (str(receipt_id),),
                            )
                            if cur.fetchone():
                                found = True
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("gate_ratification_receipt_lookup_error", error=str(exc))
                if not found:
                    raise ProvenanceRejected(
                        f"Ratified fetch receipt envelope '{receipt_id}' does not exist in store"
                    )

        if payload.provenance == Provenance.ASSISTANT_BELIEF:
            if payload.confidence is None or not (0.60 <= payload.confidence <= 1.0):
                raise ProvenanceRejected(
                    f"ASSISTANT_BELIEF requires confidence in [0.60, 1.0], got {payload.confidence}"
                )

        if payload.provenance == Provenance.INFERRED:
            if not payload.structured or "proof_trace" not in payload.structured:
                raise ProvenanceRejected("INFERRED payload requires non-empty structured['proof_trace']")
            proof_trace = payload.structured["proof_trace"]
            if not isinstance(proof_trace, list) or len(proof_trace) == 0:
                raise ProvenanceRejected("INFERRED payload requires non-empty structured['proof_trace']")

            effective_db = db if db is not None else getattr(self, "db", None)

            produced_envelopes: set[str] = set()
            produced_conclusions: set[str] = set()

            for step in proof_trace:
                if isinstance(step, dict):
                    premises = step.get("premises", [])
                    step_env_id = step.get("envelope_id")
                    conclusion = step.get("conclusion")
                elif hasattr(step, "premises") and hasattr(step, "envelope_id") and hasattr(step, "conclusion"):
                    premises = step.premises
                    step_env_id = step.envelope_id
                    conclusion = step.conclusion
                elif isinstance(step, (list, tuple)) and len(step) >= 5:
                    premises = step[2]
                    conclusion = step[3]
                    step_env_id = step[4]
                else:
                    raise ProvenanceRejected(f"Invalid proof trace step format: {step}")

                for prem in premises:
                    prem_str = str(prem).strip()
                    if not prem_str:
                        continue
                    # Check 0: Attributed premise ("<source> asserts <claim>") carried as condition
                    if re.match(r"^(.+?)\s+asserts\s+(.+)$", prem_str, re.IGNORECASE):
                        continue

                    # Check 1: Resolved by earlier step in this proof trace
                    if prem_str in produced_envelopes or prem_str.lower() in produced_conclusions:
                        continue
                    parts = prem_str.split()
                    if len(parts) >= 2 and any(
                        parts[0].lower() in c and parts[-1].lower() in c for c in produced_conclusions
                    ):
                        continue

                    # Check 2: Resolved in persistent store
                    resolved = False
                    if effective_db is not None and hasattr(effective_db, "read_cursor"):
                        try:
                            with effective_db.read_cursor() as cur:
                                cur.execute(
                                    """
                                    SELECT e.entry_id
                                    FROM provenance_envelopes e
                                    LEFT JOIN memories m ON e.entry_id = m.entry_id
                                    WHERE e.grounding_eligible = 1
                                      AND (e.entry_id = ? OR m.content = ? OR m.content = ? OR m.content LIKE ?)
                                    """,
                                    (prem_str, prem_str, prem_str.lower(), f"%{prem_str}%"),
                                )
                                if cur.fetchone():
                                    resolved = True
                                else:
                                    if len(parts) >= 2:
                                        s_target = parts[0]
                                        o_target = parts[-1]
                                        cur.execute(
                                            """
                                            SELECT e.entry_id
                                            FROM provenance_envelopes e
                                            JOIN memories m ON e.entry_id = m.entry_id
                                            WHERE e.grounding_eligible = 1
                                              AND m.content LIKE ? AND m.content LIKE ?
                                            """,
                                            (f"%{s_target}%", f"%{o_target}%"),
                                        )
                                        if cur.fetchone():
                                            resolved = True
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("gate_proof_trace_verification_db_error", error=str(exc))

                    if not resolved:
                        raise ProvenanceRejected(
                            f"Proof trace premise '{prem_str}' does not resolve to an existing envelope"
                        )

                if step_env_id and effective_db is not None and hasattr(effective_db, "read_cursor"):
                    try:
                        with effective_db.read_cursor() as cur:
                            cur.execute(
                                "SELECT entry_id FROM provenance_envelopes WHERE entry_id = ?",
                                (str(step_env_id),),
                            )
                            if not cur.fetchone():
                                raise ProvenanceRejected(
                                    f"Proof trace step envelope '{step_env_id}' does not exist in store"
                                )
                    except ProvenanceRejected:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("gate_step_envelope_lookup_error", error=str(exc))

                if step_env_id:
                    produced_envelopes.add(str(step_env_id))
                if conclusion:
                    produced_conclusions.add(str(conclusion).strip().lower())

        return Admitted(payload=payload)
