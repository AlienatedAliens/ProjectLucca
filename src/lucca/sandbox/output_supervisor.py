"""
Project Lucca — Output Supervision Layer (Dimension 7B)
Deterministic clause-level gate enforcing conversational deontic invariants
and truth-in-receipt constraints before tokens reach TTS or UI rendering.

Design invariants:
1. Pure deterministic DFA / compiled regex (no auxiliary LLM).
2. Latency budget <= 1.0 ms / clause (typically < 100 microseconds).
3. Operates on clause boundaries (comma / period splits).
4. Negation-aware (6-token preceding window check + intervening negation check).
5. Triggers full turn truncation via FLAG_ABORT, not mid-stream patch.
"""

import re
import time
from dataclasses import dataclass
from typing import Any, Sequence


# --- 1. Lexical Classes ---

SUBJECT_1P = (
    r"(?:I|the sandbox|the system|deontic checks|security constraints|"
    r"the checks|those rules|this session|the constraints)"
)

COMPLIANCE_VERB = (
    r"(?:disabled|bypassed|lifted|removed|turned off|no longer apply|"
    r"no longer active|no longer in effect|suspended|waived|overridden|unlocked)"
)

AFFIRM_AUX = (
    r"(?:is|are|has been|have been|will be|understood|confirmed|done)"
)

SECURITY_ENTITY = (
    r"(?:(?:deontic|sandbox|security|safety)\s+)*(?:sandbox|deontic|checks?|rules?|constraints?|"
    r"guardrails?|permissions?|restrictions?)"
)

NEGATION_TOKENS = {
    "not", "cannot", "can't", "won't", "never", "no",
    "unable", "refuse", "don't", "doesn't"
}

# Multi-word negation phrases
NEGATION_PHRASES = (
    r"(?:will\s+not|unable\s+to|refuse\s+to|do\s+not|does\s+not)"
)

HEDGE_TOKENS = {
    "if", "hypothetically", "supposedly"
}

HEDGE_PHRASES = (
    r"(?:in\s+theory|you\s+claim|you're\s+asking\s+me\s+to|you\s+ask\s+me\s+to)"
)


@dataclass(frozen=True)
class GateResult:
    is_breach: bool
    breach_type: str | None  # "deontic_capitulation" | "ungrounded_action" | None
    matched_text: str | None
    reason: str
    elapsed_us: float


class DeonticAssertionMatcher:
    """
    Sub-millisecond assertion-pattern matcher with negation scope tracking.
    Enforces Dimension 7B: Conversational Epistemic Invariants.
    """

    def __init__(self) -> None:
        SEP = r"[\s,.:;!?-]+"
        OPT_SEP = r"[\s,.:;!?-]*"
        # Pattern 1: Affirmative aux + security entity + compliance verb (e.g. "Understood. Deontic sandbox checks disabled")
        self._pattern_p1 = re.compile(
            rf"\b(?:{AFFIRM_AUX}){SEP}(?:{SECURITY_ENTITY}{SEP})?(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE
        )
        # Pattern 2: Subject + compliance verb (e.g. "Those rules no longer apply")
        self._pattern_p2 = re.compile(
            rf"\b(?:{SUBJECT_1P}){SEP}(?:{AFFIRM_AUX}{SEP})?(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE
        )
        # Pattern 3: Security entity + aux + compliance verb (e.g. "Sandbox is disabled")
        self._pattern_p3 = re.compile(
            rf"\b(?:{SECURITY_ENTITY}){SEP}(?:{AFFIRM_AUX}{SEP})?(?:{COMPLIANCE_VERB})\b",
            re.IGNORECASE
        )

    def evaluate_clause(self, clause: str) -> GateResult:
        """
        Evaluates a single streamed clause for deontic policy capitulation.
        Budget: <= 1.0 ms (target < 100 us).
        """
        t0 = time.perf_counter()
        clean = clause.strip()
        if not clean:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, None, "Empty clause", elapsed_us)

        # Match candidate compliance assertions
        match = None
        for pat in (self._pattern_p1, self._pattern_p2, self._pattern_p3):
            m = pat.search(clean)
            if m:
                match = m
                break

        if not match:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, None, "No compliance pattern matched", elapsed_us)

        start_idx = match.start()
        prefix = clean[:start_idx].strip()
        matched_str = match.group(0)

        # 1. Check for intervening negation inside the matched span
        # e.g., "is not disabled", "cannot be disabled"
        # Note: "no longer" is a temporal cessation marker in COMPLIANCE_VERB, not logical negation.
        if re.search(rf"\b(?:not|cannot|can't|won't|never|no(?!\s+longer))\b", matched_str, re.IGNORECASE):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, matched_str, "Negation intervenes within match span", elapsed_us)

        # 2. Check preceding 6-token lookback window for negation or hedging
        preceding_tokens = [tok.lower().strip(".,;:!?\"'") for tok in prefix.split() if tok]
        window = preceding_tokens[-6:] if len(preceding_tokens) >= 6 else preceding_tokens

        # Direct token membership
        for i, tok in enumerate(window):
            if tok == "no" and i + 1 < len(window) and window[i + 1] == "longer":
                continue
            if tok in NEGATION_TOKENS:
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return GateResult(False, None, matched_str, f"Negation token '{tok}' in lookback window", elapsed_us)
            if tok in HEDGE_TOKENS:
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return GateResult(False, None, matched_str, f"Hedge token '{tok}' in lookback window", elapsed_us)

        # Multi-word phrase check in preceding text
        preceding_text = " ".join(window)
        if re.search(NEGATION_PHRASES, preceding_text, re.IGNORECASE):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, matched_str, "Negation phrase in lookback window", elapsed_us)
        if re.search(HEDGE_PHRASES, preceding_text, re.IGNORECASE):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, matched_str, "Hedge phrase in lookback window", elapsed_us)

        # Assertion confirmed without negation or hedge
        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        return GateResult(
            is_breach=True,
            breach_type="deontic_capitulation",
            matched_text=matched_str,
            reason=f"Affirmative policy capitulation assertion: '{matched_str}'",
            elapsed_us=elapsed_us
        )


class TruthInReceiptMatcher:
    """
    Validates that claims of stateful side effects correspond to verified ToolReceipts.
    """

    ACTION_VERBS = (
        r"(?:deleted|created|modified|executed|ran|installed|removed|sent|uploaded|fetched)"
    )

    def __init__(self) -> None:
        self._pattern = re.compile(
            rf"\b(?:I|it)\s+(?:have\s+|did\s+|was\s+)?({self.ACTION_VERBS})\s+([a-zA-Z0-9_\-\./\\]+)",
            re.IGNORECASE
        )

    def evaluate_clause(self, clause: str, verified_receipts: Sequence[dict[str, Any]]) -> GateResult:
        t0 = time.perf_counter()
        m = self._pattern.search(clause)
        if not m:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, None, "No action claim matched", elapsed_us)

        action_verb = m.group(1).lower()
        target_obj = m.group(2).lower()

        # Check against receipts
        found = False
        for r in verified_receipts:
            r_action = str(r.get("action", "")).lower()
            r_target = str(r.get("target", r.get("path", ""))).lower()
            if (action_verb in r_action or r_action in action_verb) and (target_obj in r_target or r_target in target_obj):
                found = True
                break

        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        if not found:
            return GateResult(
                is_breach=True,
                breach_type="ungrounded_action",
                matched_text=m.group(0),
                reason=f"Claimed action '{action_verb}' on '{target_obj}' without matching ToolReceipt",
                elapsed_us=elapsed_us
            )

        return GateResult(False, None, m.group(0), "Action claim verified by ToolReceipt", elapsed_us)
