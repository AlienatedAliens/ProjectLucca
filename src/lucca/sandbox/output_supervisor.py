"""
Project Lucca — Output Supervision Layer (Dimension 7B)
Deterministic clause-level gate enforcing conversational deontic invariants
and truth-in-receipt constraints before tokens reach TTS or UI rendering.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence

import structlog
from pydantic import JsonValue

from lucca.sandbox.action_claim_grammar import ActionClaimGrammarSupervisor
from lucca.sandbox.receipt_truth_matcher import (
    URL_EXTRACTION_REGEX,
    WHITELISTED_DOC_DOMAINS,
    CitationProvenanceMatcher,
    TruthInReceiptMatcher,
    canonicalize_citation_url,
)
from lucca.sandbox.supervisor_lexicon import (
    _CANONICAL_ACTION_REGEX,
    _CAPABILITY_DISCLAIMER_REGEX,
    _COMPANION_ACTION_CLAIM_REGEX,
    _CONVERSATIONAL_META_TARGETS_REGEX,
    _DISCOURSE_ARTIFACT_FRAME_REGEX,
    _FUTURE_INTENT_PATTERN,
    _HOST_FILE_TARGET_PATTERN,
    _ILLUSTRATIVE_FRAME_PREFIX_REGEX,
    _INITIATING_ACTION_REGEX,
    _INTRANSITIVE_RUNTIME_ENV_REGEX,
    _LIVE_INSPECTION_ANNOUNCEMENT_REGEX,
    _META_CREATIVE_USER_PROMPT_REGEX,
    _NEGATION_PREFIX_PATTERN,
    _NON_CLAIM_SUBJECT_PREFIX,
    _PARTICIPLE_VERBS_PATTERN,
    _PASSIVE_ACTION_REGEX,
    _PAST_VERBS_PATTERN,
    _PROGRESSIVE_ACTION_REGEX,
    _STAGE_DIRECTION_OR_FAKE_SCAN_REGEX,
    _SYNCHRONOUS_EXECUTION_FUTURE_REGEX,
    _TELEGRAPHIC_ACTION_REGEX,
    AFFIRM_AUX,
    ALL_ACTION_VERBS,
    ATTRIBUTION_REGEX,
    COMPANION_BOUND_STEM_MAP,
    COMPLIANCE_VERB,
    CORE_ACTION_VERBS,
    EXPANDED_STEM_MAP,
    EXTENDED_ACTION_VERBS,
    HEDGE_PHRASES,
    HEDGE_TOKENS,
    NEGATION_PHRASES,
    NEGATION_TOKENS,
    SECURITY_ENTITY,
    SECURITY_SUBJECT,
    STALLING_RESEARCH_PATTERN,
    STRUCTURED_ACTION_TAG_REGEX,
    GateResult,
    SeverityTier,
    extract_user_context_text,
    is_elliptical_action_confirmation,
    is_meta_or_creative_context,
    is_simulated_inspection_readout,
)

logger = structlog.get_logger(__name__)


class DeonticAssertionMatcher:
    """
    Sub-millisecond assertion-pattern matcher with negation scope tracking
    and attribution-aware severity tiering.
    Enforces Dimension 7B: Conversational Epistemic Invariants.
    """

    def __init__(self) -> None:
        SEP = r"[\s,.:;!?-]+"
        # Pattern 1: Affirmative aux + security entity + compliance verb (mandatory entity!)
        self._pattern_p1 = re.compile(
            rf"\b(?:{AFFIRM_AUX}){SEP}(?:{SECURITY_ENTITY}){SEP}(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE,
        )
        # Pattern 2a: Inherent security subject + (aux)? + compliance verb
        self._pattern_p2a = re.compile(
            rf"\b(?:{SECURITY_SUBJECT}){SEP}(?:{AFFIRM_AUX}{SEP})?(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE,
        )
        # Pattern 2b: Active 1P agent + (aux)? + compliance verb + security entity object
        self._pattern_p2b = re.compile(
            rf"\b(?:I|we|the\s+system|the\s+operator){SEP}(?:{AFFIRM_AUX}{SEP})?(?:{COMPLIANCE_VERB}){SEP}(?:the\s+)?(?:{SECURITY_ENTITY})\b",
            re.IGNORECASE,
        )
        # Pattern 3: Security entity + (aux)? + compliance verb
        self._pattern_p3 = re.compile(
            rf"\b(?:{SECURITY_ENTITY}){SEP}(?:{AFFIRM_AUX}{SEP})?(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE,
        )

    def evaluate_clause(
        self, clause: str, sentence_history: Sequence[str] | None = None
    ) -> GateResult:
        """
        Evaluates a single streamed clause for deontic policy capitulation.
        Optionally accepts preceding sentence history for cross-clause attribution detection.
        Budget: <= 1.0 ms (target < 100 us).
        """
        t0 = time.perf_counter()
        clean = clause.strip()
        # Normalize markdown formatting (bold, italic, code ticks)
        clean = re.sub(r"[\*\_`~]", "", clean)
        if not clean:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, SeverityTier.PASS, None, "Empty clause", elapsed_us)

        # Match candidate compliance assertions
        match = None
        for pat in (self._pattern_p1, self._pattern_p2a, self._pattern_p2b, self._pattern_p3):
            m = pat.search(clean)
            if m:
                match = m
                break

        if not match:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False, None, SeverityTier.PASS, None, "No compliance pattern matched", elapsed_us
            )

        start_idx = match.start()
        prefix = clean[:start_idx].strip()
        matched_str = match.group(0)

        # 1. Check for intervening negation inside the matched span
        # e.g., "is not disabled", "cannot be disabled"
        if re.search(
            r"\b(?:not|cannot|can't|won't|never|no(?!\s+longer))\b", matched_str, re.IGNORECASE
        ):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                matched_str,
                "Negation intervenes within match span",
                elapsed_us,
            )

        # 2. Check full sentence context (rolling history + current clause) for attribution markers
        context_text = " ".join(list(sentence_history or []) + [clean])
        if ATTRIBUTION_REGEX.search(context_text):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                is_breach=True,
                breach_type="deontic_capitulation",
                severity=SeverityTier.TIER_2_SOFT,
                matched_text=matched_str,
                reason=(
                    "Attribution marker detected in sentence context; "
                    "downgraded to Tier 2 soft ground"
                ),
                elapsed_us=elapsed_us,
            )

        # 3. Check preceding 6-token lookback window for negation or hedging
        preceding_tokens = [tok.lower().strip(".,;:!?\"'") for tok in prefix.split() if tok]
        window = preceding_tokens[-6:] if len(preceding_tokens) >= 6 else preceding_tokens

        # Direct token membership in prefix
        for i, tok in enumerate(window):
            if tok == "no" and i + 1 < len(window) and window[i + 1] == "longer":
                continue
            if tok in NEGATION_TOKENS:
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return GateResult(
                    False,
                    None,
                    SeverityTier.PASS,
                    matched_str,
                    f"Negation token '{tok}' in lookback window",
                    elapsed_us,
                )
            if tok in HEDGE_TOKENS:
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return GateResult(
                    False,
                    None,
                    SeverityTier.PASS,
                    matched_str,
                    f"Hedge token '{tok}' in lookback window",
                    elapsed_us,
                )

        # Multi-word phrase check in preceding text
        preceding_text = " ".join(window)
        if re.search(NEGATION_PHRASES, preceding_text, re.IGNORECASE):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                matched_str,
                "Negation phrase in lookback window",
                elapsed_us,
            )
        if re.search(HEDGE_PHRASES, preceding_text, re.IGNORECASE):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                matched_str,
                "Hedge phrase in lookback window",
                elapsed_us,
            )

        # All four conditions hold -> Tier 1 Terminal Abort candidate
        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        return GateResult(
            is_breach=True,
            breach_type="deontic_capitulation",
            severity=SeverityTier.TIER_1_ABORT,
            matched_text=matched_str,
            reason=f"Affirmative policy capitulation assertion: '{matched_str}'",
            elapsed_us=elapsed_us,
        )


class OutputSupervisorSession[ChunkT]:
    """
    Manages stateful streaming output supervision across clauses in an interactive turn.
    Implements:
    1. Rolling sentence history buffer (for cross-clause attribution detection).
    2. One-clause lookahead buffer (delayed commit for Tier 1 candidates).
    3. Session-level hysteresis (escalates repeated Tier 2 security hits).
    4. Sequential chunk emission on downgrade (preserving Kokoro prosody).
    5. Session-scoped allowed URLs for citation provenance verification.
    """

    def __init__(
        self,
        deontic_matcher: DeonticAssertionMatcher | None = None,
        truth_matcher: TruthInReceiptMatcher | None = None,
        citation_matcher: CitationProvenanceMatcher | None = None,
        grammar_supervisor: ActionClaimGrammarSupervisor | None = None,
    ) -> None:
        self.deontic_matcher = deontic_matcher or DeonticAssertionMatcher()
        self.grammar_supervisor = grammar_supervisor or ActionClaimGrammarSupervisor()
        self.truth_matcher = truth_matcher or TruthInReceiptMatcher(enable_grammar_channel=True)
        self.citation_matcher = citation_matcher or CitationProvenanceMatcher()
        self.sentence_history: list[str] = []
        self.pending_tier1_chunk: tuple[ChunkT, GateResult] | None = None
        self.session_tier2_security_hits: int = 0
        self.allowed_urls: set[str] = set()
        self.turn_has_stalled: bool = False
        # Epoch seconds when the current turn began (set by reset_turn).
        # Forwarded to the truth-in-receipt matcher as `stale_before` so a
        # previous turn's receipt can never ground this turn's action claim.
        self.turn_started_at: float | None = None
        self.turn_user_context: str | Sequence[dict[str, str]] | None = None
        self._refutation_regex = re.compile(
            r"\b(?:not|cannot|can't|won't|never|refuse|in\s+your\s+dreams|not\s+going\s+to)\b",
            re.IGNORECASE,
        )

    def set_turn_context(self, user_context: str | Sequence[dict[str, str]] | None) -> None:
        """
        Sets the user / conversation context for the current turn (v3.0 context-aware supervision).
        """
        self.turn_user_context = user_context

    def register_allowed_urls(self, urls: Sequence[str]) -> None:
        """Registers verified URLs into session-scoped allowed citations."""
        for u in urls:
            if u and isinstance(u, str):
                self.allowed_urls.add(u.strip())

    def feed_chunk(
        self,
        chunk_item: ChunkT,
        clause_text: str,
        verified_receipts: Sequence[dict[str, JsonValue]] | None = None,
        user_context: str | Sequence[dict[str, str]] | None = None,
    ) -> tuple[list[tuple[ChunkT, GateResult]], bool]:
        """
        Feeds a streamed clause chunk into the session supervisor.
        Returns:
            (emitted_chunks, should_abort)
            where emitted_chunks is a list of (chunk_item, gate_result) to dispatch to TTS.
        """
        emitted: list[tuple[ChunkT, GateResult]] = []

        # Check stalling rhetorical question evasion (bureaucracy filter)
        if STALLING_RESEARCH_PATTERN.search(clause_text):
            self.turn_has_stalled = True
            return ([], False)

        # 1. Check pending Tier-1 lookahead buffer against incoming clause
        if self.pending_tier1_chunk is not None:
            pending_item, pending_res = self.pending_tier1_chunk
            # Does incoming clause refute the pending claim?
            has_refutation = bool(
                self._refutation_regex.search(clause_text) or ATTRIBUTION_REGEX.search(clause_text)
            )

            if has_refutation:
                # Downgrade pending chunk to Tier 2 and release sequentially
                downgraded_res = GateResult(
                    is_breach=True,
                    breach_type=pending_res.breach_type,
                    severity=SeverityTier.TIER_2_SOFT,
                    matched_text=pending_res.matched_text,
                    reason=(
                        f"{pending_res.reason} (downgraded to Tier 2 via next-clause "
                        f"refutation: '{clause_text.strip()}')"
                    ),
                    elapsed_us=pending_res.elapsed_us,
                )
                emitted.append((pending_item, downgraded_res))
                self.pending_tier1_chunk = None
                self._record_tier2_hit()
            else:
                # Confirmed Tier 1 capitulation: abort immediately!
                self.pending_tier1_chunk = None
                return ([], True)

        # 2. Evaluate incoming clause with rolling sentence history
        gate_res = self.deontic_matcher.evaluate_clause(
            clause_text, sentence_history=self.sentence_history
        )

        # Check truth-in-receipt if receipts provided and deontic check did not flag
        if verified_receipts is not None and not gate_res.is_breach:
            receipt_res = self.grammar_supervisor.evaluate_clause(
                clause_text,
                verified_receipts,
                stale_before=self.turn_started_at,
                user_context=user_context if user_context is not None else self.turn_user_context,
            )
            if receipt_res.is_breach:
                # Tier-1 abort is reserved for turns where a STATEFUL tool ran
                # (write/launch/delete/run): only then can a first-person action
                # claim be a current-turn hallucination verifiable in-stream.
                # On read-only turns (memory_search, query_capabilities, ...) or
                # no-tool turns, an action claim is a long-term-memory
                # recollection (A1) or a hallucination deferred to the post-turn
                # functional-coherence checker (F-WO8-19/F-WO8-23).
                stateful_actions = {
                    "write_file",
                    "edit_file",
                    "note_write",
                    "launch_app",
                    "delete_file",
                    "run_python",
                }
                has_stateful = any(
                    str(r.get("action", "")) in stateful_actions for r in verified_receipts
                )
                if not has_stateful:
                    receipt_res = GateResult(
                        is_breach=True,
                        # Distinct breach type: a recollection of a PAST action
                        # (grounded in long-term memory) is not a security
                        # violation and must NOT feed the session security
                        # hysteresis. Found live via the contrastive battery:
                        # 3+ benign recollections escalated the hysteresis and
                        # hard-aborted later truthful recollections.
                        breach_type="ungrounded_action_recollection",
                        severity=SeverityTier.TIER_2_SOFT,
                        matched_text=receipt_res.matched_text,
                        reason=(
                            f"{receipt_res.reason} (downgraded to Tier 2: no stateful "
                            "current-turn receipts; recollection/hallucination deferred "
                            "to post-turn coherence check)"
                        ),
                        elapsed_us=receipt_res.elapsed_us,
                    )
                gate_res = receipt_res

        # Check citation provenance against session allowed URLs
        if not gate_res.is_breach:
            cite_res = self.citation_matcher.evaluate_clause(
                clause_text, allowed_urls=list(self.allowed_urls)
            )
            if cite_res.is_breach:
                gate_res = cite_res

        # 3. Handle incoming clause classification
        if gate_res.severity == SeverityTier.TIER_2_SOFT:
            # Check session hysteresis: 3rd hit in session escalates to Tier 1 candidate
            if self.session_tier2_security_hits >= 2:
                gate_res = GateResult(
                    is_breach=True,
                    breach_type=gate_res.breach_type,
                    severity=SeverityTier.TIER_1_ABORT,
                    matched_text=gate_res.matched_text,
                    reason=(
                        f"{gate_res.reason} (escalated to Tier 1 via session hysteresis: "
                        "3rd security hit)"
                    ),
                    elapsed_us=gate_res.elapsed_us,
                )

        if gate_res.severity == SeverityTier.TIER_1_ABORT:
            # Hold candidate in lookahead buffer
            self.pending_tier1_chunk = (chunk_item, gate_res)
        elif gate_res.severity == SeverityTier.TIER_2_SOFT:
            if gate_res.breach_type != "ungrounded_action_recollection":
                # Only SECURITY hits feed the hysteresis; recollection
                # downgrades are emitted without counting toward escalation.
                self._record_tier2_hit()
            emitted.append((chunk_item, gate_res))
        else:
            # SeverityTier.PASS
            emitted.append((chunk_item, gate_res))

        # 4. Update sentence rolling history
        clean_t = clause_text.strip()
        self.sentence_history.append(clean_t)
        # Reset on terminal sentence punctuation
        if clean_t and clean_t[-1] in (".", "!", "?"):
            self.sentence_history.clear()
        elif clean_t.endswith("..."):
            self.sentence_history.clear()

        return (emitted, False)

    def flush(self) -> tuple[list[tuple[ChunkT, GateResult]], bool]:
        """
        Called at end of stream.
        If a Tier-1 candidate was held with no subsequent refutation, commit abort.
        """
        if self.pending_tier1_chunk is not None:
            self.pending_tier1_chunk = None
            return ([], True)
        return ([], False)

    def reset_turn(
        self, user_context: str | Sequence[dict[str, str]] | None = None
    ) -> None:
        """Resets turn-level buffers; preserves session-level hysteresis and allowed_urls."""
        self.sentence_history.clear()
        self.pending_tier1_chunk = None
        self.turn_has_stalled = False
        self.turn_started_at = time.time()
        self.turn_user_context = user_context

    def _record_tier2_hit(self) -> None:
        self.session_tier2_security_hits += 1


__all__ = [
    "AFFIRM_AUX", "ALL_ACTION_VERBS", "ATTRIBUTION_REGEX", "ActionClaimGrammarSupervisor",
    "COMPANION_BOUND_STEM_MAP", "COMPLIANCE_VERB", "CORE_ACTION_VERBS",
    "CitationProvenanceMatcher", "DeonticAssertionMatcher", "EXPANDED_STEM_MAP",
    "EXTENDED_ACTION_VERBS", "GateResult", "HEDGE_PHRASES", "HEDGE_TOKENS",
    "NEGATION_PHRASES", "NEGATION_TOKENS", "OutputSupervisorSession", "SECURITY_ENTITY",
    "SECURITY_SUBJECT", "STALLING_RESEARCH_PATTERN", "STRUCTURED_ACTION_TAG_REGEX",
    "SeverityTier", "TruthInReceiptMatcher", "URL_EXTRACTION_REGEX",
    "WHITELISTED_DOC_DOMAINS", "_CANONICAL_ACTION_REGEX", "_CAPABILITY_DISCLAIMER_REGEX",
    "_COMPANION_ACTION_CLAIM_REGEX", "_CONVERSATIONAL_META_TARGETS_REGEX",
    "_DISCOURSE_ARTIFACT_FRAME_REGEX", "_FUTURE_INTENT_PATTERN", "_HOST_FILE_TARGET_PATTERN",
    "_ILLUSTRATIVE_FRAME_PREFIX_REGEX", "_INITIATING_ACTION_REGEX",
    "_INTRANSITIVE_RUNTIME_ENV_REGEX", "_LIVE_INSPECTION_ANNOUNCEMENT_REGEX",
    "_META_CREATIVE_USER_PROMPT_REGEX", "_NEGATION_PREFIX_PATTERN",
    "_NON_CLAIM_SUBJECT_PREFIX", "_PARTICIPLE_VERBS_PATTERN", "_PASSIVE_ACTION_REGEX",
    "_PAST_VERBS_PATTERN", "_PROGRESSIVE_ACTION_REGEX", "_STAGE_DIRECTION_OR_FAKE_SCAN_REGEX",
    "_SYNCHRONOUS_EXECUTION_FUTURE_REGEX", "_TELEGRAPHIC_ACTION_REGEX",
    "canonicalize_citation_url", "extract_user_context_text",
    "is_elliptical_action_confirmation", "is_meta_or_creative_context",
    "is_simulated_inspection_readout",
]
