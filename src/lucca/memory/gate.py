"""
Project Lucca — Provenance Verification Gate
Spec 03 §4, Spec 04 §3, ADR-006
"""

import base64
import hashlib
import hmac
import json
import re
import time
from collections.abc import Sequence
from typing import Final

import structlog

from lucca.core.config import get_config
from lucca.core.exceptions import ProvenanceRejected
from lucca.core.schemas import (
    FACT_PREDICATES,
    GROUNDING_ELIGIBLE,
    MEMORY_ELIGIBLE,
    Admitted,
    LLMNarration,
    Provenance,
    SignedPayload,
    VerifierLabel,
    canonicalize_predicate,
    is_valid_predicate,
)
from lucca.memory.signers import canonicalize_unsigned_payload, derive_provenance_key

logger = structlog.get_logger(__name__)

_NEGATION_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "not",
        "no",
        "never",
        "none",
        "false",
        "neither",
        "nor",
        "cannot",
        "cant",
        "isnt",
        "arent",
        "wasnt",
        "werent",
        "doesnt",
        "dont",
        "didnt",
        "wont",
        "wouldnt",
        "shouldnt",
        "couldnt",
        "without",
        "untrue",
        "disputes",
        "refutes",
        "contradicts",
    }
)

_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "by",
        "that",
        "this",
        "it",
        "as",
    }
)

_ALLOWED_SIGNER_TYPES: Final[frozenset[str]] = frozenset(
    {
        "USER_EXPLICIT",
        "TOOL_VERIFIED",
        "LISP_ASSERTION",
        "ASSISTANT_ACTION",
        "USER_DERIVED",
        "SYSTEM_OBSERVED",
        "TOOL_OUTPUT",
        "INFERRED",
        "tool_output",
        "system_observed",
        "inferred",
        "user_derived",
        "user_explicit",
        "assistant_action",
    }
)


def _normalize_proposition(text: str) -> str:
    """Normalizes a proposition for structural comparison."""
    cleaned = text.strip().lower().replace("_", " ")
    cleaned = re.sub(r"[^\w\s.]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_tokens(text: str) -> list[str]:
    norm = _normalize_proposition(text)
    return [t for t in norm.split() if t]


def _has_negation(text: str) -> bool:
    tokens = set(_extract_tokens(text))
    if tokens & _NEGATION_TOKENS:
        return True
    lower = text.strip().lower()
    return bool(re.search(r"\b(?:not_|does_not_|non_|unverified)\w*", lower))


def _has_negation_conflict(text_a: str, text_b: str) -> bool:
    return _has_negation(text_a) != _has_negation(text_b)


def _extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"(?<![a-zA-Z_])-?\d+(?:\.\d+)?(?![a-zA-Z_])", text))


def _extract_spo_triple(
    text: str, structured: dict[str, object] | None = None
) -> tuple[str, str, str] | None:
    """Extracts a normalized (subject, predicate, object) triple if present."""
    if isinstance(structured, dict):
        s = str(structured.get("s") or structured.get("subject") or "").strip().lower()
        p = str(structured.get("p") or structured.get("predicate") or "").strip().lower()
        o = str(structured.get("o") or structured.get("object") or "").strip().lower()
        if s and p and o:
            return (s.replace("_", " "), canonicalize_predicate(p), o.replace("_", " "))

    raw = text.strip()
    if not raw:
        return None
    parts = raw.split()
    if len(parts) == 3:
        s, p, o = parts[0].lower(), parts[1].lower(), parts[2].lower()
        return (s.replace("_", " "), canonicalize_predicate(p), o.replace("_", " "))

    m = re.match(
        r"^([a-zA-Z0-9_.-]+)\s+(is|are|has|have|uses|equals|located_in|works_at|lives_in|[a-z0-9_]+_[a-z0-9_]+)\s+(.+?)\.?$",
        raw,
        re.IGNORECASE,
    )
    if m:
        s = m.group(1).strip().lower().replace("_", " ")
        p = canonicalize_predicate(m.group(2).strip().lower())
        o = _normalize_proposition(m.group(3))
        if s and p and o:
            return (s, p, o)
    return None


def _check_nli_entailment(verifier: object, premise: str, hypothesis: str) -> bool:
    """
    Checks if a SemanticVerifierPort / VerifierWorker entails hypothesis from premise (>= 0.75).
    """
    if verifier is None or not premise.strip() or not hypothesis.strip():
        return False
    try:
        if hasattr(verifier, "check_consistency"):
            res = verifier.check_consistency(premise=premise, hypothesis=hypothesis)
            if getattr(res, "degraded", False):
                return False
            label = getattr(res, "label", None)
            score = float(getattr(res, "score", getattr(res, "confidence", 0.0)))
            if (
                label == VerifierLabel.ENTAILMENT
                or str(label).lower().endswith("entailment")
            ) and score >= 0.75:
                return True
        elif hasattr(verifier, "verify"):
            res = verifier.verify(premise, hypothesis)
            if isinstance(res, (int, float)):
                return float(res) >= 0.75
            if isinstance(res, dict):
                lbl = str(res.get("label", "")).lower()
                sc = float(res.get("score", res.get("entailment", 0.0)))
                return ("entail" in lbl or not lbl) and sc >= 0.75
    except Exception as exc:  # noqa: BLE001
        logger.debug("gate_verifier_entailment_check_failed", error=str(exc))
    return False


def _propositions_match_or_entail(
    claim: str,
    candidate_content: str,
    claim_structured: dict[str, object] | None = None,
    candidate_structured: dict[str, object] | None = None,
    verifier: object = None,
) -> bool:
    """
    Genuine proposition verification:
    1. Rejects negation conflicts and conflicting numeric literals.
    2. Exact normalized proposition match.
    3. Structured (subject, predicate, object) triple match.
    4. High token overlap (Jaccard >= 0.80 or content-token containment >= 0.80 with >= 2 content
    tokens).
    5. VerifierWorker NLI entailment >= 0.75.
    """
    if not claim.strip() or not candidate_content.strip():
        return False

    if _has_negation_conflict(claim, candidate_content):
        return False

    nums_claim = _extract_numbers(claim)
    nums_cand = _extract_numbers(candidate_content)
    if nums_claim and nums_cand and not (nums_claim & nums_cand):
        return False

    norm_claim = _normalize_proposition(claim)
    norm_cand = _normalize_proposition(candidate_content)
    if not norm_claim or not norm_cand:
        return False

    # 1. Exact normalized match
    if norm_claim == norm_cand:
        return True

    # 2. Structured (subject, predicate, object) triple match
    spo_claim = _extract_spo_triple(claim, claim_structured)
    spo_cand = _extract_spo_triple(candidate_content, candidate_structured)
    if spo_claim is not None and spo_cand is not None:
        if spo_claim[0] == spo_cand[0] and spo_claim[1] == spo_cand[1]:
            if spo_claim[2] == spo_cand[2]:
                return True
            return False
    if spo_cand is not None and norm_claim == spo_cand[2] and len(norm_claim.split()) >= 2:
        return True

    # 3. Token overlap (>= 0.8 Jaccard or symmetric content token overlap)
    tokens_claim = [t for t in norm_claim.split() if t not in _STOPWORDS]
    tokens_cand = [t for t in norm_cand.split() if t not in _STOPWORDS]
    if not tokens_claim:
        tokens_claim = norm_claim.split()
    if not tokens_cand:
        tokens_cand = norm_cand.split()

    set_claim = set(tokens_claim)
    set_cand = set(tokens_cand)
    if set_claim and set_cand:
        intersection = len(set_claim & set_cand)
        union = len(set_claim | set_cand)
        jaccard = intersection / union if union > 0 else 0.0
        if jaccard >= 0.80:
            return True
        if len(
            set_claim) >= 2 and (
                intersection / len(set_claim)) >= 0.80 and (intersection / len(set_cand)) >= 0.80:
            return True

    # 4. NLI Entailment via VerifierWorker (>= 0.75)
    if verifier is not None and _check_nli_entailment(verifier, candidate_content, claim):
        return True

    return False


def is_content_corroborated(
    db: object,
    content: str,
    verifier: object = None,
    structured: dict[str, object] | None = None,
) -> bool:
    """
    WO-38 Phase 2 / WO-39 Milestone 2.1: Independent-corroboration lookup backing
    ``memory.user_explicit_requires_corroboration``.

    Fails CLOSED (returns False) when ``db is None`` or when any SQLite exception
    occurs. Requires corroborating rows to have ``grounding_eligible = 1`` (or valid
    signer_type in ('USER_EXPLICIT', 'TOOL_VERIFIED', 'LISP_ASSERTION')) from an
    independent provenance source, matching via normalized proposition match,
    structured (s, p, o) triple match, or VerifierWorker NLI entailment (>= 0.75).
    """
    if db is None:
        return False
    claim = (content or "").strip()
    if not claim:
        return False

    effective_verifier = verifier if verifier is not None else getattr(db, "verifier", None)

    def _inspect_rows(cur: object) -> bool:
        rows: list[tuple[object, ...]] = []
        try:
            cur.execute(  # type: ignore[attr-defined]
                """
                SELECT m.content, e.payload_json, e.grounding_eligible, e.provenance
                FROM memories m
                JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                WHERE e.grounding_eligible = 1
                  AND e.provenance <> ?
                  AND m.valid_to IS NULL
                """,
                (Provenance.USER_EXPLICIT.value,),
            )
            rows = list(cur.fetchall())  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.debug("corroboration_envelopes_join_fallback", error=str(exc))
            # Fallback for simplified schemas used in unit tests (e.g. signer_type column)
            cur.execute(  # type: ignore[attr-defined]
                """
                SELECT content, NULL, grounding_eligible, signer_type
                FROM memories
                WHERE grounding_eligible = 1
                  AND signer_type IN ('USER_EXPLICIT', 'TOOL_VERIFIED', 'LISP_ASSERTION')
                """
            )
            rows = list(cur.fetchall())  # type: ignore[attr-defined]

        for row in rows:
            row_content = str(row[0] or "").strip()
            payload_json_raw = row[1] if len(row) > 1 else None
            grounding_flag = int(row[2]) if len(row) > 2 and row[2] is not None else 0
            prov_or_signer = str(row[3] or "").strip() if len(row) > 3 else ""
            if grounding_flag != 1:
                continue
            if prov_or_signer and prov_or_signer not in _ALLOWED_SIGNER_TYPES:
                continue

            cand_struct: dict[str, object] | None = None
            if isinstance(payload_json_raw, str) and payload_json_raw.strip():
                try:
                    pj = json.loads(payload_json_raw)
                    if isinstance(pj, dict) and isinstance(pj.get("structured"), dict):
                        cand_struct = pj["structured"]
                except Exception as exc:  # noqa: BLE001
                    logger.debug("corroboration_payload_json_error", error=str(exc))
                    cand_struct = None

            if _propositions_match_or_entail(
                claim=claim,
                candidate_content=row_content,
                claim_structured=structured,
                candidate_structured=cand_struct,
                verifier=effective_verifier,
            ):
                return True
        return False

    try:
        if hasattr(db, "read_cursor"):
            with db.read_cursor() as cur:  # type: ignore[attr-defined]
                return _inspect_rows(cur)
        elif hasattr(db, "cursor"):
            cur = db.cursor()  # type: ignore[attr-defined]
            try:
                return _inspect_rows(cur)
            finally:
                if hasattr(cur, "close"):
                    cur.close()
        return False
    except Exception as exc:  # noqa: BLE001
        logger.debug("user_explicit_corroboration_lookup_failed", error=str(exc))
        return False


def user_explicit_requires_corroboration() -> bool:
    """Operator flag, read at commit time so config precedence (env/toml) applies."""
    try:
        return bool(get_config().memory.user_explicit_requires_corroboration)
    except Exception as exc:  # noqa: BLE001
        logger.debug("memory_corroboration_flag_config_error", error=str(exc))
        return False


def resolve_grounding_eligible(provenance: Provenance, content: str, db: object) -> int:
    """
    Grounding-eligibility decision shared by every write path (store.commit,
    MemoryManager.add_memory, MemoryManager.update_memory).

    Class membership in GROUNDING_ELIGIBLE is the frozen v1 invariant (TRAP 5);
    the corroboration requirement is a flag-gated runtime downgrade applied only
    to USER_EXPLICIT, never to USER_DERIVED or other classes (TRAP 6).
    """
    if provenance not in GROUNDING_ELIGIBLE:
        return 0
    if (
        provenance is Provenance.USER_EXPLICIT
        and user_explicit_requires_corroboration()
        and not is_content_corroborated(db, content)
    ):
        logger.warning("user_explicit_uncorroborated_belnap_deferred", content_sha=content[:40])
        return 0
    return 1

# Baseline predicate set; open predicates validated via is_valid_predicate (WO-17 Phase 2).
PREDICATES: Final[frozenset[str]] = FACT_PREDICATES

NONCE_RETENTION_SECONDS = 86400.0  # 24 hours


class ProvenanceGate:
    """
    Gatekeeper that admits only cryptographically verified, fresh, replay-free,
    and structurally valid payloads into persistent memory.
    """

    def __init__(
        self,
        master_key: bytes = b"0" * 32,
        db: object = None,
        verifier: object = None,
    ) -> None:
        if len(master_key) < 32:
            raise ProvenanceRejected(f"Master key must be at least 32 bytes, got {len(master_key)}")
        self.master_key = master_key
        self.db = db
        self.verifier = verifier
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

    def _verify_single_premise(
        self,
        prem_str: str,
        effective_db: object = None,
        produced_envelopes: set[str] | None = None,
        produced_conclusions: set[str] | None = None,
        effective_verifier: object = None,
    ) -> bool:
        """Verifies a single rule premise against earlier proof steps or persistent store."""
        clean_prem = prem_str.strip()
        if not clean_prem:
            return True

        envs = produced_envelopes or set()
        concls = produced_conclusions or set()

        # Check 1: Resolved by earlier step in this proof trace
        if clean_prem in envs or clean_prem.lower() in concls:
            return True
        for prev_c in concls:
            if _propositions_match_or_entail(
                claim=clean_prem,
                candidate_content=prev_c,
                verifier=effective_verifier,
            ):
                return True

        # Check 2: Resolved in persistent store
        if effective_db is None:
            return False

        def _check_cursor(cur: object) -> bool:
            # 2a. Direct envelope ID match
            try:
                cur.execute(  # type: ignore[attr-defined]
                    """
                    SELECT entry_id
                    FROM provenance_envelopes
                    WHERE grounding_eligible = 1 AND entry_id = ?
                    LIMIT 1
                    """,
                    (clean_prem,),
                )
                if cur.fetchone():  # type: ignore[attr-defined]
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.debug("premise_envelope_id_lookup_error", error=str(exc))

            # 2b. Grounding-eligible memory / envelope proposition & triple & NLI verification
            rows: list[tuple[object, ...]] = []
            try:
                cur.execute(  # type: ignore[attr-defined]
                    """
                    SELECT m.content, e.payload_json, e.grounding_eligible
                    FROM provenance_envelopes e
                    LEFT JOIN memories m ON e.entry_id = m.entry_id
                    WHERE e.grounding_eligible = 1
                      AND (m.valid_to IS NULL)
                    """
                )
                rows = list(cur.fetchall())  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                logger.debug("premise_envelopes_join_fallback", error=str(exc))
                try:
                    cur.execute(  # type: ignore[attr-defined]
                        """
                        SELECT content, NULL, grounding_eligible
                        FROM memories
                        WHERE grounding_eligible = 1
                        """
                    )
                    rows = list(cur.fetchall())  # type: ignore[attr-defined]
                except Exception as inner_exc:  # noqa: BLE001
                    logger.debug("premise_memories_fallback_error", error=str(inner_exc))
                    return False

            for row in rows:
                row_content = str(row[0] or "").strip()
                payload_json_raw = row[1] if len(row) > 1 else None
                cand_struct: dict[str, object] | None = None
                if isinstance(payload_json_raw, str) and payload_json_raw.strip():
                    try:
                        pj = json.loads(payload_json_raw)
                        if isinstance(pj, dict):
                            if not row_content and isinstance(pj.get("content"), str):
                                row_content = pj["content"]
                            if isinstance(pj.get("structured"), dict):
                                cand_struct = pj["structured"]
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("premise_payload_json_error", error=str(exc))
                        cand_struct = None

                if not row_content:
                    continue

                if _propositions_match_or_entail(
                    claim=clean_prem,
                    candidate_content=row_content,
                    candidate_structured=cand_struct,
                    verifier=effective_verifier,
                ):
                    return True

            return False

        try:
            if hasattr(effective_db, "read_cursor"):
                with effective_db.read_cursor() as cur:  # type: ignore[attr-defined]
                    return _check_cursor(cur)
            elif hasattr(effective_db, "cursor"):
                cur = effective_db.cursor()  # type: ignore[attr-defined]
                try:
                    return _check_cursor(cur)
                finally:
                    if hasattr(cur, "close"):
                        cur.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("gate_proof_trace_verification_db_error", error=str(exc))
            return False

        return False

    def verify_rule_premises(
        self,
        premises: Sequence[object],
        db: object = None,
        produced_envelopes: set[str] | None = None,
        produced_conclusions: set[str] | None = None,
        verifier: object = None,
    ) -> bool:
        """
        WO-39 Milestone 2.1: Verifies that all rule premises resolve to grounding-eligible
        envelopes or earlier verified conclusions via exact normalized match, high token
        overlap (>= 0.8 Jaccard with negation check), structured (s, p, o) triple lookup,
        or VerifierWorker NLI entailment (>= 0.75).
        """
        if not premises:
            return False
        effective_db = db if db is not None else getattr(self, "db", None)
        effective_verifier = (
            verifier
            if verifier is not None
            else (getattr(self, "verifier", None) or getattr(effective_db, "verifier", None))
        )
        for prem in premises:
            prem_str = str(prem).strip()
            if not prem_str:
                continue
            if not self._verify_single_premise(
                prem_str=prem_str,
                effective_db=effective_db,
                produced_envelopes=produced_envelopes,
                produced_conclusions=produced_conclusions,
                effective_verifier=effective_verifier,
            ):
                return False
        return True

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
                raise ProvenanceRejected("INFERRED payload requires non-empty "
                    "structured['proof_trace']")
            proof_trace = payload.structured["proof_trace"]
            if not isinstance(proof_trace, list) or len(proof_trace) == 0:
                raise ProvenanceRejected("INFERRED payload requires non-empty "
                    "structured['proof_trace']")

            effective_db = db if db is not None else getattr(self, "db", None)
            effective_verifier = getattr(self, "verifier", None) or getattr(
                effective_db, "verifier", None
            )

            produced_envelopes: set[str] = set()
            produced_conclusions: set[str] = set()
            payload_conds_raw = payload.structured.get("conditions",
                []) if isinstance(payload.structured, dict) else []
            payload_conditions = {
                str(c).strip().lower()
                for c in (payload_conds_raw if isinstance(payload_conds_raw, list) else [])
                if str(c).strip()
            }

            for step in proof_trace:
                step_conditions: set[str] = set()
                if isinstance(step, dict):
                    premises = step.get("premises", [])
                    step_env_id = step.get("envelope_id")
                    conclusion = step.get("conclusion")
                    raw_sc = step.get("conditions", [])
                    if isinstance(raw_sc, list):
                        step_conditions = {str(c).strip().lower() for c in raw_sc if str(c).strip()}
                elif hasattr(step, "premises") and hasattr(step, "envelope_id") and hasattr(step,
                    "conclusion"):
                    premises = step.premises
                    step_env_id = step.envelope_id
                    conclusion = step.conclusion
                    raw_sc = getattr(step, "conditions", [])
                    if isinstance(raw_sc, list):
                        step_conditions = {str(c).strip().lower() for c in raw_sc if str(c).strip()}
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
                    if (
                        prem_str.lower() in step_conditions and prem_str.lower()
                        in payload_conditions
                    ):
                        continue
                    if not self._verify_single_premise(
                        prem_str=prem_str,
                        effective_db=effective_db,
                        produced_envelopes=produced_envelopes,
                        produced_conclusions=produced_conclusions,
                        effective_verifier=effective_verifier,
                    ):
                        raise ProvenanceRejected(
                            f"Proof trace premise '{
                                prem_str}' does not resolve to an existing envelope"
                        )

                if step_env_id and effective_db is not None and hasattr(effective_db,
                    "read_cursor"):
                    try:
                        with effective_db.read_cursor() as cur:
                            cur.execute(
                                "SELECT entry_id FROM provenance_envelopes WHERE entry_id = ?",
                                (str(step_env_id),),
                            )
                            if not cur.fetchone():
                                raise ProvenanceRejected(
                                    f"Proof trace step envelope '{
                                        step_env_id}' does not exist in store"
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
