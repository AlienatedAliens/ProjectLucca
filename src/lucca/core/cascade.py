"""
Project Lucca — 5-Substrate Epistemic Search Cascade & Belnap Bilattice Orchestration
Spec 10 §4, Milestone 3 Architecture, WO-43 Phase 3.3
"""

from __future__ import annotations

import enum
import re
import time
from collections.abc import Sequence

import structlog
from pydantic import BaseModel, Field, JsonValue, model_validator

from lucca.core.cascade_intent import (
    CULINARY_WORDS,
    RECENT_CONTEXT_PATTERN,
    REGIONAL_OR_CULTURE_WORDS,
    SLANG_OR_DIALECT_WORDS,
    _any_term_matches,
    _extract_target_entity,
    _term_matches,
    classify_epistemic_intent,
    extract_clean_topic,
    matches_slang_or_world_definition,
    select_floor_cue,
)
from lucca.core.cascade_substrates import CascadeSubstrateAdapters
from lucca.core.schemas import VerifierLabel, standard_for_confidence
from lucca.core.trace import now_ns
from lucca.memory.extraction import FUNCTIONAL_PREDICATES
from lucca.memory.latent_probe import (
    BelnapLatentInvestigator,
    BelnapValue,
    belnap_join_k,
    belnap_join_t,
    belnap_meet_k,
    belnap_meet_t,
    belnap_negation,
    information_join,
    information_meet,
    pool_evidence,
    truth_join,
    truth_meet,
)
from lucca.ports import MemoryStorePort, SemanticVerifierPort
from lucca.reasoning.recall import recall_past_episodes, tokenize_query

logger = structlog.get_logger(__name__)


def _as_float(v: object, default: float = 0.0) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return default
    return default


class EpistemicSubstrate(enum.IntEnum):
    """
    Epistemic substrates in Project Lucca's cognitive architecture:
    0: Live System / Hardware Telemetry (< 1ms, Tier 1)
    1: Workspace Filesystem / AST (5–20ms, Tier 2)
    2: Cryptographic Episodic & Semantic Memory (15–40ms, Tier 3)
    3: SSRF-Hardened Sandboxed Web (300–1500ms, Tier 4)
    4: Calibrated Honest Abstention (0ms, \\bot Ground Truth Gap)
    5: Axiomatic Core Persona & Self-Model (0ms, Tier 0)
    6: Authoritative Dynamic Capability & Tool Registry (0ms, Tier 0)
    """

    TELEMETRY = 0
    WORKSPACE = 1
    MEMORY = 2
    WEB = 3
    ABSTENTION = 4
    SELF = 5
    CAPABILITIES = 6
    SELF_HISTORY = 7


class TrustTier(enum.IntEnum):
    """
    Epistemic Trust Hierarchy: Lower integer denotes higher physical authority.
    Tier 0 strictly supersedes Tier 1, Tier 1 strictly supersedes Tier 2, etc.
    """

    TIER_0_AXIOMATIC = 0  # Axiomatic self-knowledge, persona, and registered capabilities
    TIER_1_HARDWARE = 1  # Direct OS/sensor telemetry (hardware truth)
    TIER_2_WORKSPACE = 2  # Bounded container filesystem / source AST
    TIER_3_MEMORY = 3  # HMAC-signed episodic memory & user preferences
    TIER_4_WEB = 4  # External untrusted network content (tainted)


# ============================================================================
# 3. Evidence Models & Dynamic Calibrated Abstention
# ============================================================================


class EvidenceItem(BaseModel):
    """
    Atomic unit of evidence retrieved from an epistemic substrate.
    Strictly implements Belnap's (1977) four-valued data model via independent
    'told_true' and 'told_false' epistemic bits and NARS (w+, w-) evidence counts:
    - (told_true=True, told_false=False) -> T (Asserts p, w+ > 0, w- == 0)
    - (told_true=False, told_false=True) -> F (Refutes p, w+ == 0, w- > 0)
    - (told_true=True, told_false=True)   -> TOP (Contradiction / Conflict, w+ > 0, w- > 0)
    - (told_true=False, told_false=False) -> BOT (Epistemic Gap / Unknown, w+ == 0, w- == 0)
    """

    substrate: EpistemicSubstrate
    trust_tier: TrustTier
    source: str
    content: str
    proposition: str = ""
    told_true: bool = True
    told_false: bool = False
    positive_evidence: int = 1
    negative_evidence: int = 0
    confidence: float = 1.0
    timestamp_ns: int = Field(default_factory=now_ns)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _sync_belnap_and_evidence_counts(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        pol = d.pop("polarity", None) or d.pop("belnap_val", None)
        has_explicit_bits = "told_true" in d or "told_false" in d
        has_explicit_counts = "positive_evidence" in d or "negative_evidence" in d

        if pol is not None and not has_explicit_bits and not has_explicit_counts:
            pol_str = pol.value if hasattr(pol, "value") else str(pol).upper()
            if pol_str in ("TOP", "CONFLICT"):
                d.update(told_true=True, told_false=True, positive_evidence=1, negative_evidence=1)
            elif pol_str in ("F", "FALSE"):
                d.update(told_true=False, told_false=True, positive_evidence=0, negative_evidence=1)
            elif pol_str in ("BOT", "UNKNOWN"):
                d.update(
                    told_true=False, told_false=False, positive_evidence=0, negative_evidence=0
                )
            else:
                d.update(told_true=True, told_false=False, positive_evidence=1, negative_evidence=0)
        elif has_explicit_counts and not has_explicit_bits:
            w_pos = int(d.get("positive_evidence", 0) or 0)
            w_neg = int(d.get("negative_evidence", 0) or 0)
            d["told_true"] = w_pos > 0
            d["told_false"] = w_neg > 0
        else:
            tt = bool(d.get("told_true", True))
            tf = bool(d.get("told_false", False))
            d.setdefault("positive_evidence", 1 if tt else 0)
            d.setdefault("negative_evidence", 1 if tf else 0)
        return d

    @property
    def polarity(self) -> BelnapValue:
        """Derives the atomic Belnap value from the two independent epistemic bits."""
        if self.told_true and self.told_false:
            return BelnapValue.CONFLICT
        if self.told_true:
            return BelnapValue.TRUE
        if self.told_false:
            return BelnapValue.FALSE
        return BelnapValue.UNKNOWN

    @property
    def nars_frequency(self) -> float:
        """NARS frequency f = w+ / (w+ + w-)."""
        total = self.positive_evidence + self.negative_evidence
        if total <= 0:
            return 0.5
        return float(self.positive_evidence) / float(total)

    @property
    def nars_confidence(self) -> float:
        """NARS confidence c = (w+ + w-) / (w+ + w- + k) with horizon k = 1.0."""
        total = self.positive_evidence + self.negative_evidence
        if total <= 0:
            return 0.0
        return float(total) / float(total + 1.0)


def build_calibrated_refusal(
    queried_substrates: Sequence[EpistemicSubstrate],
    topic: str | None = None,
) -> str:
    """
    Dynamically constructs a calibrated honest refusal listing ONLY the substrates
    actually queried for this turn, preventing false action assertions.
    """
    names_map: dict[EpistemicSubstrate, str] = {
        EpistemicSubstrate.SELF: "core persona & self-knowledge",
        EpistemicSubstrate.CAPABILITIES: "registered capabilities",
        EpistemicSubstrate.TELEMETRY: "system telemetry",
        EpistemicSubstrate.WORKSPACE: "workspace files",
        EpistemicSubstrate.MEMORY: "memory records",
        EpistemicSubstrate.WEB: "external web sources",
        EpistemicSubstrate.SELF_HISTORY: "execution and utterance history",
    }
    checked = [names_map[s] for s in queried_substrates if s in names_map]
    if not checked:
        checked_str = "available verified sources"
    elif len(checked) == 1:
        checked_str = checked[0]
    elif len(checked) == 2:
        checked_str = f"{checked[0]} and {checked[1]}"
    else:
        checked_str = f"{', '.join(checked[:-1])}, and {checked[-1]}"

    display_topic = topic.strip() if topic and len(topic.strip()) < 80 else "that"
    return (
        f"I checked my {checked_str}, but have no verified record of {display_topic}. "
        f"I don't know the answer and won't guess."
    )


class SearchCascadeResult(BaseModel):
    """Unified outcome of the 5-substrate search cascade."""

    belnap_status: BelnapValue
    evidence: list[EvidenceItem]
    resolved_substrate: EpistemicSubstrate
    elapsed_ms: float
    floor_cue_spoken: str | None = None
    calibrated_refusal: str | None = None
    synthesized_context: str = ""
    queried_substrates: list[EpistemicSubstrate] = Field(default_factory=list)
    recollections: list[str] = Field(default_factory=list)


class EpistemicSearchCascade(CascadeSubstrateAdapters):
    """Executes multi-tier epistemic search across Substrates 0 to 7 and Belnap FOUR synthesis."""

    def __init__(
        self,
        sandbox: object | None = None,
        memory_store: MemoryStorePort | None = None,
        enable_floor_cues: bool = True,
        verifier: SemanticVerifierPort | None = None,
    ) -> None:
        self.sandbox = sandbox
        self.memory_store = memory_store
        self.enable_floor_cues = enable_floor_cues
        self.verifier = verifier

    def classify_intent(self, query_text: str) -> tuple[bool, list[EpistemicSubstrate], str | None]:
        return classify_epistemic_intent(query_text)

    def select_floor_cue(
        self, query_text: str, target_substrate: EpistemicSubstrate | None = None
    ) -> str:
        return select_floor_cue(query_text, target_substrate)

    def _annotate_active_memory_conflicts(self, items: list[EvidenceItem]) -> None:
        """Detects contradictions between active (non-superseded) memory items in Substrate 2.
        When two active items contradict each other without D-HON-01 temporal supersession,
        both positive and negative evidence bits/counts are set (BelnapValue.CONFLICT / TOP)."""
        active = [it for it in items if not bool(it.metadata.get("is_superseded"))]
        if len(active) < 2:
            return

        def _is_dhon01_pair(a: EvidenceItem, b: EvidenceItem) -> bool:
            """Returns True if (a, b) is a canonical FUNCTIONAL_PREDICATES pair with distinct
            precedence/valid_from timestamps handled by _detect_memory_supersession."""
            for pred in FUNCTIONAL_PREDICATES:
                if f" {pred} " in f" {a.content.strip()} " and (
                    f" {pred} " in f" {b.content.strip()} "
                ):
                    vf_a = _as_float(a.metadata.get("valid_from", 0.0))
                    vf_b = _as_float(b.metadata.get("valid_from", 0.0))
                    prov_a = str(a.metadata.get("provenance", "")).upper()
                    prov_b = str(b.metadata.get("provenance", "")).upper()
                    if vf_a != vf_b or prov_a != prov_b:
                        return True
            return False

        neg_tokens = {"not", "never", "no", "false", "disabled", "cannot", "none", "unsupported"}
        stop_tokens = {
            "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on", "at",
            "for", "with", "by", "from", "that", "this", "it", "be", "as", "or", "and",
        }

        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                it_a = active[i]
                it_b = active[j]
                if it_a.content.strip().lower() == it_b.content.strip().lower():
                    continue
                if _is_dhon01_pair(it_a, it_b):
                    continue

                is_conflict = False
                is_uncertain_nli = False
                if self.verifier is not None:
                    try:
                        v_res = self.verifier.check_consistency(
                            premise=it_a.content, hypothesis=it_b.content
                        )
                        mapped_val = BelnapLatentInvestigator.evaluate_nli_verdict(
                            v_res, has_lexical_conflict=False
                        )
                        if not v_res.degraded and v_res.label == VerifierLabel.CONTRADICTION:
                            is_conflict = True
                        elif mapped_val == BelnapValue.NEITHER and (
                            v_res.degraded or v_res.label == VerifierLabel.UNCERTAIN
                        ):
                            is_uncertain_nli = True
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("cascade_verifier_consistency_error", error=str(exc))
                        is_uncertain_nli = True

                words_a = re.findall(r"[a-z0-9_.-]+", it_a.content.lower())
                words_b = re.findall(r"[a-z0-9_.-]+", it_b.content.lower())
                content_a = set(words_a) - stop_tokens - neg_tokens
                content_b = set(words_b) - stop_tokens - neg_tokens
                shared = content_a & content_b

                if not is_conflict and len(shared) >= 2:
                    neg_a = bool(set(words_a) & neg_tokens)
                    neg_b = bool(set(words_b) & neg_tokens)
                    if neg_a != neg_b:
                        is_conflict = True
                    else:
                        nums_a = set(re.findall(r"\b\d+(?:\.\d+)?\b", it_a.content))
                        nums_b = set(re.findall(r"\b\d+(?:\.\d+)?\b", it_b.content))
                        if nums_a and nums_b and nums_a != nums_b:
                            is_conflict = True
                        elif len(words_a) == len(words_b) and len(words_a) >= 3:
                            diffs = [
                                (wa, wb)
                                for wa, wb in zip(words_a, words_b, strict=False)
                                if wa != wb
                            ]
                            if len(diffs) == 1:
                                is_conflict = True

                if is_conflict:
                    for it in (it_a, it_b):
                        it.told_true = True
                        it.told_false = True
                        it.positive_evidence = max(1, it.positive_evidence)
                        it.negative_evidence = max(1, it.negative_evidence)
                        it.metadata["belnap_state"] = "BOTH"
                elif is_uncertain_nli and len(shared) >= 2:
                    for it in (it_a, it_b):
                        if not it.metadata.get("nli_uncertain"):
                            it.confidence = round(it.confidence * 0.65, 4)
                            it.metadata["belnap_state"] = "NEITHER"
                            it.metadata["nli_uncertain"] = True

    def _evaluate_polarity(
        self,
        content: str,
        query_text: str = "",
    ) -> tuple[bool, bool]:
        """Evaluates evidential polarity (told_true, told_false) for an evidence item.

        Remediates hardcoded told_false=False defects (v1.35.7 Phase 1 hygiene).
        In Phase 3, integrates SemanticVerifierPort with automatic fail-open lexical degradation.
        Supports both instance calls `self._evaluate_polarity(content, query)` and
        unbound class calls `EpistemicSearchCascade._evaluate_polarity(content, query)`.
        """
        if isinstance(self, str):
            actual_content: str = self
            actual_query: str = content if isinstance(content, str) else query_text
            verifier = None
        else:
            actual_content = content
            actual_query = query_text
            verifier = getattr(self, "verifier", None)

        if verifier is not None and actual_query.strip():
            try:
                v_res = verifier.check_consistency(premise=actual_content, hypothesis=actual_query)
                if not v_res.degraded:
                    if v_res.label == VerifierLabel.ENTAILMENT:
                        return True, False
                    if v_res.label == VerifierLabel.CONTRADICTION:
                        return False, True
            except Exception as exc:  # noqa: BLE001
                logger.debug("cascade_verifier_eval_failed", error=str(exc))

        content_lower = actual_content.lower()
        query_lower = actual_query.lower() if actual_query else ""

        # Strong negation / refutation patterns
        refutation_patterns = [
            r"\b(?:not\s+supported|does\s+not\s+support|do\s+not\s+support|cannot|unsupported)\b",
            r"\b(?:no\s+longer\s+supported|deprecated|removed|disabled|incompatible)\b",
            r"\b(?:not\s+available|never\s+supported|impossible|fails\s+to)\b",
            r"\b(?:is\s+false|false\b)",
        ]

        is_refuting = any(re.search(pat, content_lower) for pat in refutation_patterns)

        if is_refuting:
            query_is_negative = bool(
                re.search(r"\b(?:not|unsupported|never|cannot)\b", query_lower)
            )
            if query_is_negative:
                return True, False
            return False, True

        return True, False

    def _detect_memory_supersession(
        self,
        evidence: list[EvidenceItem],
    ) -> tuple[list[str], list[str]]:
        """
        Detects intra-tier memory supersession per D-HON-01 and Spec 04 §3.
        Identifies newer valid_from facts on functional predicates or explicitly
        superseded rows.
        Returns:
            (resolutions, narration_contracts)
        Marks superseded EvidenceItems with metadata['is_superseded'] = True.
        """
        resolutions: list[str] = []
        narration_contracts: list[str] = []

        mem_items = [e for e in evidence if e.trust_tier == TrustTier.TIER_3_MEMORY]
        if not mem_items:
            return resolutions, narration_contracts

        # 1. Group by functional predicate (s, p)
        pred_groups: dict[tuple[str, str], list[tuple[EvidenceItem, float, str]]] = {}
        for item in mem_items:
            vf = _as_float(item.metadata.get("valid_from"), default=item.timestamp_ns / 1e9)
            if vf == 0.0:
                vf = item.timestamp_ns / 1e9
            content = item.content.strip()
            parts = content.split(maxsplit=2)
            if len(parts) >= 3 and parts[1] in FUNCTIONAL_PREDICATES:
                s, p, o = parts[0], parts[1], parts[2]
                pred_groups.setdefault((s, p), []).append((item, vf, o))
            else:
                for pred in FUNCTIONAL_PREDICATES:
                    if f" {pred} " in f" {content} ":
                        idx = content.find(pred)
                        s = content[:idx].strip() or "user"
                        o = content[idx + len(pred) :].strip()
                        pred_groups.setdefault((s, p), []).append((item, vf, o))
                        break

        def _entry_precedence(e: tuple[EvidenceItem, float, str]) -> tuple[int, float]:
            item, vf, _ = e
            prov = str(item.metadata.get("provenance", "")).upper()
            if "USER_EXPLICIT" in prov:
                p_rank = 4
            elif "USER_DERIVED" in prov:
                p_rank = 3
            elif "INFERRED" in prov:
                p_rank = 2
            elif "LISP" in prov or "ASSERTION" in prov:
                p_rank = 1
            else:
                p_rank = 0
            return (p_rank, vf)

        for (_s, _p), entries in pred_groups.items():
            if len(entries) < 2:
                continue
            entries.sort(key=_entry_precedence, reverse=True)
            best_item, best_vf, best_val = entries[0]
            for stale_item, _stale_vf, stale_val in entries[1:]:
                if stale_val.lower() != best_val.lower():
                    stale_item.metadata["is_superseded"] = True
                    resolutions.append(
                        f"D-HON-01 Verified Store Priority — Current value per store: "
                        f"'{best_item.content}' (valid_from: {best_vf}) supersedes "
                        f"historical record: '{stale_item.content}'"
                    )
                    narration_contracts.append(
                        "Narration Contract: Cite the verified store's current value over "
                        "transcript echo for entity-attribute queries per D-HON-01."
                    )

        # 2. Check for explicit valid_to on any memory items
        for item in mem_items:
            if item.metadata.get("valid_to") is not None or item.metadata.get("is_superseded"):
                item.metadata["is_superseded"] = True
                if not any(item.content in r for r in resolutions):
                    active_candidates = [
                        e
                        for e in mem_items
                        if not bool(e.metadata.get("is_superseded"))
                        and e.metadata.get("valid_to") is None
                    ]
                    if active_candidates:
                        active_candidates.sort(
                            key=lambda e: _as_float(e.metadata.get("valid_from", 0.0)),
                            reverse=True,
                        )
                        best = active_candidates[0]
                        resolutions.append(
                            f"D-HON-01 Verified Store Priority — Current value per store: "
                            f"'{best.content}' supersedes historical record: '{item.content}'"
                        )
                        narration_contracts.append(
                            "Narration Contract: Cite the verified store's current value over "
                            "transcript echo for entity-attribute queries per D-HON-01."
                        )

        return resolutions, narration_contracts

    def synthesize(
        self,
        query_text: str,
        evidence: list[EvidenceItem],
        topic: str | None = None,
        queried_substrates: Sequence[EpistemicSubstrate] | None = None,
        recollections: Sequence[str] | None = None,
    ) -> tuple[BelnapValue, str, str | None]:
        """
        Computes the Belnap evidential valuation and renders formatted context.
        Applies hierarchical trust tier tie-breaking:
        - Same-tier contradiction (told_true AND told_false) -> genuine conflict (TOP).
        - Cross-tier contradiction -> higher trust tier strictly supersedes lower tier.
          Stale historical lower-tier records do not block or force an unnecessary hedge.
        - Zero evidence -> BelnapValue.UNKNOWN (BOT) with dynamic honest refusal.
        Returns: (BelnapValue, synthesized_context, calibrated_refusal)
        """
        # Case 1: Substrate 4 Honest Abstention (Epistemic Gap BOT)
        if not evidence:
            refusal = build_calibrated_refusal(queried_substrates or [], topic)
            queried_names = [s.name for s in (queried_substrates or [])]
            synth_ctx = (
                f"[Belnap Epistemic State: BOT (Epistemic Gap / Unknown)]\n"
                f"Queried Substrates: {queried_names}\n"
                f"Empirical Status: No verified records or facts found for topic "
                f"'{topic or 'unspecified'}'.\n"
                "Mandatory Grounding Directive: You do not possess verified knowledge on this "
                "topic. You MUST explicitly admit uncertainty and decline to confabulate or guess. "
                f'Calibrated Statement: "{refusal}"'
            )
            return BelnapValue.UNKNOWN, synth_ctx, refusal

        # Group evidence by Trust Tier
        tier_map: dict[TrustTier, list[EvidenceItem]] = {}
        for ev in evidence:
            tier_map.setdefault(ev.trust_tier, []).append(ev)

        highest_tier = min(tier_map.keys())
        highest_tier_evidence = tier_map[highest_tier]

        # Supersession checks: intra-tier (D-HON-01) and cross-tier
        superseded_annotations: list[str] = []
        narration_contracts: list[str] = []

        intra_res, intra_contracts = self._detect_memory_supersession(evidence)
        superseded_annotations.extend(intra_res)
        narration_contracts.extend(intra_contracts)

        # Check Belnap value within highest active trust tier (excluding superseded records)
        active_highest = [
            e for e in highest_tier_evidence if not bool(e.metadata.get("is_superseded"))
        ]
        eval_tier_evidence = active_highest if active_highest else highest_tier_evidence
        highest_told_true = any(e.told_true for e in eval_tier_evidence)
        highest_told_false = any(e.told_false for e in eval_tier_evidence)

        if highest_told_true and highest_told_false:
            # Genuine same-tier contradiction
            belnap_status = BelnapValue.CONFLICT
        elif highest_told_true:
            belnap_status = BelnapValue.TRUE
        elif highest_told_false:
            belnap_status = BelnapValue.FALSE
        else:
            belnap_status = BelnapValue.UNKNOWN

        # Cross-tier staleness / supersession check
        for tier, items in tier_map.items():
            if tier > highest_tier:
                tier_told_true = any(e.told_true for e in items)
                tier_told_false = any(e.told_false for e in items)
                # If lower tier contradicts the higher tier:
                if (highest_told_true and tier_told_false) or (
                    highest_told_false and tier_told_true
                ):
                    superseded_annotations.append(
                        f"Trust Tier {highest_tier.value} ({highest_tier.name}) strictly "
                        f"supersedes historical/lower-trust Tier {tier.value} ({tier.name}) record."
                    )

        # Build formatted grounded context
        lines: list[str] = ["[Epistemic Search Cascade — Verified Ground Truth]"]
        if belnap_status == BelnapValue.CONFLICT:
            lines.append(
                "[Status: CONFLICT (TOP) — Genuine internal contradiction detected within "
                "authoritative tier; tension noted]"
            )
        else:
            lines.append(
                f"[Status: CONSISTENT ({belnap_status.value}) — Grounded Evidence Verified]"
            )

        if superseded_annotations:
            for note in superseded_annotations:
                lines.append(f"[Resolution: {note}]")
        if narration_contracts:
            for contract in sorted(set(narration_contracts)):
                lines.append(f"[{contract}]")

        # Sort evidence by Trust Tier, active before superseded, then confidence, valid_from
        def _evidence_sort_key(e: EvidenceItem) -> tuple[int, int, float, float]:
            is_sup = 1 if bool(e.metadata.get("is_superseded")) else 0
            vf = _as_float(e.metadata.get("valid_from", 0.0))
            return (e.trust_tier.value, is_sup, -e.confidence, -vf)

        sorted_evidence = sorted(evidence, key=_evidence_sort_key)

        current_tier: TrustTier | None = None
        for item in sorted_evidence:
            if item.trust_tier != current_tier:
                current_tier = item.trust_tier
                lines.append(f"\n[Trust Tier {current_tier.value}: {current_tier.name}]")
            if bool(item.metadata.get("is_superseded")):
                polarity_tag = "[superseded]"
            elif item.metadata.get("provenance") == "INFERRED":
                meta_conf = item.metadata.get("confidence")
                conf_val = (
                    _as_float(meta_conf, default=float(item.confidence))
                    if meta_conf is not None
                    else float(item.confidence)
                )
                std_label = standard_for_confidence(conf_val).value
                polarity_tag = f"[inferred, confidence {conf_val:.2f} — {std_label}]"
            else:
                polarity_tag = (
                    "[asserts]"
                    if (item.told_true and not item.told_false)
                    else "[refutes]"
                    if (item.told_false and not item.told_true)
                    else "[both]"
                    if (item.told_true and item.told_false)
                    else "[neither]"
                )
            lines.append(f"- ({item.source}) {polarity_tag} {item.content}")

        # Append non-grounding recollections under explicit quoting frame (D-MEM-04)
        if recollections:
            lines.append(
                "\n[Recollections (Non-Grounding)]\n"
                "Things you previously said or believed — quote them as such; "
                "they are not evidence:"
            )
            for rec in recollections:
                lines.append(f"- {rec}")

        context_str = "\n".join(lines)
        return belnap_status, context_str, None

    # Master Cascade Query Loop
    def query(
        self,
        query_text: str,
        substrates: list[EpistemicSubstrate] | None = None,
        emit_floor_cue: bool = True,
    ) -> SearchCascadeResult:
        """
        Executes cascade fall-through across designated substrates,
        measuring elapsed time and returning consolidated evidence.
        """
        t0 = time.perf_counter()

        is_epistemic, detected_subs, topic = self.classify_intent(query_text)

        if substrates is not None:
            active_substrates = list(substrates)
        else:
            active_substrates = detected_subs or [
                EpistemicSubstrate.TELEMETRY,
                EpistemicSubstrate.WORKSPACE,
                EpistemicSubstrate.MEMORY,
            ]

        cue = self.select_floor_cue(query_text, active_substrates[0] if active_substrates else None)
        floor_cue = cue if (self.enable_floor_cues and emit_floor_cue) else None

        collected_evidence: list[EvidenceItem] = []
        resolved_substrate = EpistemicSubstrate.ABSTENTION

        for sub in active_substrates:
            if sub == EpistemicSubstrate.SELF:
                items = self.query_substrate_self(query_text)
                if items:
                    collected_evidence.extend(items)
                    resolved_substrate = EpistemicSubstrate.SELF
            elif sub == EpistemicSubstrate.CAPABILITIES:
                items = self.query_substrate_capabilities(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate in (
                        EpistemicSubstrate.ABSTENTION,
                        EpistemicSubstrate.SELF,
                    ):
                        resolved_substrate = EpistemicSubstrate.CAPABILITIES
            elif sub == EpistemicSubstrate.TELEMETRY:
                items = self.query_substrate_0_telemetry(query_text)
                if items:
                    collected_evidence.extend(items)
                    resolved_substrate = EpistemicSubstrate.TELEMETRY
            elif sub == EpistemicSubstrate.WORKSPACE:
                items = self.query_substrate_1_workspace(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.WORKSPACE
            elif sub == EpistemicSubstrate.MEMORY:
                items = self.query_substrate_2_memory(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.MEMORY
            elif sub == EpistemicSubstrate.WEB:
                items = self.query_substrate_3_web(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.WEB
            elif sub == EpistemicSubstrate.SELF_HISTORY:
                items = self.query_substrate_self_history(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate in (
                        EpistemicSubstrate.ABSTENTION,
                        EpistemicSubstrate.SELF,
                    ):
                        resolved_substrate = EpistemicSubstrate.SELF_HISTORY

        # Retrieve any non-grounding recollections recorded during memory query
        recollections = list(getattr(self, "_last_recollections", []))

        # Perform Belnap evidential synthesis
        belnap_val, synthesized_ctx, calibrated_refusal = self.synthesize(
            query_text=query_text,
            evidence=collected_evidence,
            topic=topic,
            queried_substrates=active_substrates,
            recollections=recollections,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return SearchCascadeResult(
            belnap_status=belnap_val,
            evidence=collected_evidence,
            resolved_substrate=resolved_substrate,
            elapsed_ms=round(elapsed_ms, 3),
            floor_cue_spoken=floor_cue,
            calibrated_refusal=calibrated_refusal,
            synthesized_context=synthesized_ctx,
            queried_substrates=active_substrates,
            recollections=recollections,
        )


__all__ = [
    "BelnapLatentInvestigator", "BelnapValue", "CULINARY_WORDS", "CascadeSubstrateAdapters",
    "EpistemicSearchCascade", "EpistemicSubstrate", "EvidenceItem", "RECENT_CONTEXT_PATTERN",
    "REGIONAL_OR_CULTURE_WORDS", "SLANG_OR_DIALECT_WORDS", "SearchCascadeResult", "TrustTier",
    "_any_term_matches", "_extract_target_entity", "_term_matches", "belnap_join_k",
    "belnap_join_t", "belnap_meet_k", "belnap_meet_t", "belnap_negation",
    "build_calibrated_refusal", "classify_epistemic_intent", "extract_clean_topic",
    "information_join", "information_meet", "matches_slang_or_world_definition", "pool_evidence",
    "recall_past_episodes", "select_floor_cue", "tokenize_query", "truth_join", "truth_meet",
]
