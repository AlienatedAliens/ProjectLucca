"""
Project Lucca — Truth-in-Receipt and Citation Provenance Matchers (WO-43 Phase 3.2)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §2
"""

from __future__ import annotations

import re
import time
import urllib.parse
from collections.abc import Sequence

import structlog
from pydantic import JsonValue

from lucca.sandbox.action_claim_grammar import ActionClaimGrammarSupervisor
from lucca.sandbox.supervisor_lexicon import (
    _INITIATING_ACTION_REGEX,
    EXPANDED_STEM_MAP,
    HEDGE_PATTERN,
    IDIOMATIC_NON_ACTION_PATTERN,
    PAST_CONTEXT_PATTERN,
    STRUCTURED_ACTION_TAG_REGEX,
    GateResult,
    SeverityTier,
)

logger = structlog.get_logger(__name__)


class TruthInReceiptMatcher:
    """
    Validates that claims of stateful side effects correspond to verified ToolReceipts.
    Handles contractions, filler idioms, quantifiers, and compound targets.
    Supports decode-time structured action channel and legacy 1P matching.
    """

    ACTION_VERBS = (
        r"(?:deleted|created|modified|executed|ran|installed|removed|sent|uploaded|fetched|"
        r"saved|wrote|posted|rebooted|booked|placed|processed|started|closed|copied|moved|updated)"
    )

    PRESENT_ACTION_VERBS = (
        r"(?:sending|closing|rebooting|restarting|deleting|creating|modifying|installing|terminating|"
        r"placing|booking|processing|running|executing|uploading|downloading|clearing|purging|updating)"
    )

    STEM_MAP = EXPANDED_STEM_MAP
    PAST_CONTEXT_PATTERN = PAST_CONTEXT_PATTERN
    IDIOMATIC_NON_ACTION_PATTERN = IDIOMATIC_NON_ACTION_PATTERN
    HEDGE_PATTERN = HEDGE_PATTERN

    # Receipt statuses that count as verified grounding. Receipts carrying any
    # other status (failed, error, timeout, ...) do NOT ground action claims.
    SUCCESS_STATUSES: frozenset[str] = frozenset(
        {"success", "succeeded", "ok", "completed", "done"}
    )

    def __init__(self, enable_grammar_channel: bool = False) -> None:
        self.enable_grammar_channel = enable_grammar_channel
        self._grammar_supervisor = ActionClaimGrammarSupervisor()
        self._action_pattern = re.compile(
            r"\b(?:(?:I|it)(?:\s+have|\'ve|\s+did|\s+was)?\s+|^)"
            r"(?:gone\s+ahead\s+and\s+|went\s+ahead\s+and\s+|just\s+|already\s+|successfully\s+)?"
            rf"({self.ACTION_VERBS})\s+(.+)",
            re.IGNORECASE,
        )
        self._present_action_pattern = re.compile(
            r"(?:^|\b(?:I\s+am|\'m|I\'m|am)\s+)"
            rf"({self.PRESENT_ACTION_VERBS})\s+(.+)",
            re.IGNORECASE,
        )
        self._future_pattern = re.compile(
            r"\b(?:about\s+to|going\s+to|will|plan(?:ning)?\s+to)\b",
            re.IGNORECASE,
        )

    def evaluate_clause(
        self,
        clause: str,
        verified_receipts: Sequence[dict[str, JsonValue]],
        stale_before: float | None = None,
        user_context: str | Sequence[dict[str, str]] | None = None,
        full_narration: str | None = None,
    ) -> GateResult:
        """Evaluate a completed-action claim against current-turn receipts.

        P6 battery broadening (workshop 2026-10-04):
        - Markdown emphasis (``*``, backtick, ``~``) is stripped before matching
          so "I **deleted** file.txt" is still detected. Underscores are
          preserved so snake_case filenames match their receipts.
        - Receipts with a non-success ``status`` never ground a claim.
        - When ``stale_before`` (epoch seconds) is provided, receipts stamped
          (``timestamp`` / ``ts``) earlier than it are ignored — a previous
          turn's receipt must not ground this turn's claim. Receipts without
          a timestamp are given the benefit of the doubt (staleness is the
          caller's contract when timestamps are absent).
        """
        # If grammar channel is active or structured tags are present, delegate to ActionClaimGrammarSupervisor
        if (
            self.enable_grammar_channel
            or STRUCTURED_ACTION_TAG_REGEX.search(clause)
            or _INITIATING_ACTION_REGEX.search(re.sub(r"[*`~]", "", clause).strip())
        ):
            return self._grammar_supervisor.evaluate_clause(
                clause,
                verified_receipts,
                stale_before=stale_before,
                user_context=user_context,
                full_narration=full_narration,
            )

        t0 = time.perf_counter()

        # Strip markdown emphasis before matching (underscores preserved for
        # snake_case targets).
        clause = re.sub(r"[*`~]", "", clause)

        # 1. Reject future / intentional framing (not a completed past-tense action)
        if self._future_pattern.search(clause):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Future/intentional framing (not a completed action)",
                elapsed_us,
            )

        # 2. Reject figurative or idiomatic expressions
        if self.IDIOMATIC_NON_ACTION_PATTERN.search(clause):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Idiomatic/figurative non-action phrasing",
                elapsed_us,
            )

        # 3. Reject hedged / epistemic claims (speaker uncertain → not asserting)
        if self.HEDGE_PATTERN.search(clause):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Hedged/epistemic claim — speaker is not asserting a completed action",
                elapsed_us,
            )

        is_present_match = False
        m = self._action_pattern.search(clause)
        if not m:
            m = self._present_action_pattern.search(clause)
            if m:
                is_present_match = True
        if not m:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "No completed action claim matched",
                elapsed_us,
            )

        # Disambiguate explanatory gerund subjects from active physical claims
        if is_present_match:
            prefix = clause[: m.start()].lower()
            if re.search(r"\b(?:by|for|while|worth|when|if|after|before|without|to|such\s+as|than)\s*$", prefix):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return GateResult(
                    False,
                    None,
                    SeverityTier.PASS,
                    None,
                    "Prepositional gerund phrase (not an active physical claim)",
                    elapsed_us,
                )
            remainder = m.group(2)
            if not re.search(r"\b(?:I\s+am|\'m|I\'m)\b", clause, re.IGNORECASE):
                if re.search(
                    r"\b(?:is|are|was|were|can|could|will|would|makes|means|requires|helps|allows|provides|causes|involves|installs|works|operates)\b",
                    remainder,
                    re.IGNORECASE,
                ):
                    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                    return GateResult(
                        False,
                        None,
                        SeverityTier.PASS,
                        None,
                        "Explanatory gerund subject (not an active physical claim)",
                        elapsed_us,
                    )

        # Past-session recollection exemption: claims framed as recollections of
        # PRIOR sessions are grounded by long-term memory, not current-turn
        # receipts. Only current-turn action claims require receipt verification.
        if self.PAST_CONTEXT_PATTERN.search(clause):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                m.group(0) if m else None,
                "Past-session recollection (out of scope for current-turn receipts)",
                elapsed_us,
            )

        # Check if the action claim is within the scope of a preceding negation or abstention phrase
        prefix = clause[: m.start()].lower()
        if re.search(
            r"\b(?:no|not|never|don't|do\s+not|didn't|did\s+not|haven't|have\s+not|without|denied)\b",
            prefix,
        ):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Action claim is negated in lookback window",
                elapsed_us,
            )

        action_verb = m.group(1).lower()
        stem = self.STEM_MAP.get(action_verb, action_verb)
        remainder = m.group(2).strip()

        # Clean trailing adverbial / prepositional phrases
        remainder = re.sub(
            r"\s+(?:for\s+you|as\s+requested|now|for\s+your\s+records|from\s+the\s+workspace)[\.!]?$",
            "",
            remainder,
            flags=re.IGNORECASE,
        )
        remainder = re.sub(r"^\s*both\s+", "", remainder, flags=re.IGNORECASE)

        # Split multiple conjuncts (e.g. "both config file and backup archive")
        raw_targets = [t.strip() for t in re.split(r"\s+and\s+|\s*,\s*", remainder) if t.strip()]
        clean_targets = []
        for t in raw_targets:
            clean = re.sub(
                r"^(?:the|a|an|your|my|our|this|that|these|those)\s+",
                "",
                t,
                flags=re.IGNORECASE,
            ).strip(".,!?;: ")
            if clean:
                clean_targets.append(clean)

        # Filter receipts that cannot ground a claim: failed status or stale
        # timestamp (P6 battery broadening). Receipts without a status are
        # treated as successful; receipts without a timestamp are never
        # stale (staleness is the caller's contract when unstamped).
        eligible_receipts: list[dict[str, JsonValue]] = []
        for r in verified_receipts:
            status = str(r.get("status", "success")).lower()
            if status not in self.SUCCESS_STATUSES:
                continue
            if stale_before is not None:
                raw_ts = r.get("timestamp", r.get("ts"))
                if raw_ts is not None:
                    try:
                        if float(str(raw_ts)) < stale_before:
                            continue
                    except ValueError:
                        logger.debug(
                            "receipt_timestamp_unparseable", raw_ts=str(raw_ts)
                        )
            eligible_receipts.append(r)

        # Verify all claimed objects have corresponding ToolReceipts
        tool_map_legacy: dict[str, tuple[str, ...]] = {
            "save": ("note_write", "write_file", "memory_commit", "inbox_handoff", "schedule_event"),
            "write": ("note_write", "write_file", "memory_commit"),
            "create": ("note_write", "write_file", "memory_commit", "schedule_event"),
            "run": ("run_python", "calc_math"),
            "execute": ("run_python", "calc_math"),
            "search": ("memory_search", "search_web", "search_text", "self_history_search"),
            "read": ("read_file", "clipboard_read", "memory_search", "artifact_verify"),
            "delete": ("delete_file",),
            "remove": ("delete_file",),
            "launch": ("launch_app",),
            "open": ("launch_app",),
        }
        mapped_legacy = tool_map_legacy.get(stem, ())
        ungrounded: list[str] = []
        for target_obj in clean_targets:
            target_lower = target_obj.lower().replace("'", "").replace('"', "")
            matched = False
            for r in eligible_receipts:
                r_action = str(r.get("action", "")).lower()
                r_target = str(r.get("target", r.get("path", ""))).lower().replace("'", "").replace('"', "")
                action_ok = (
                    (stem in r_action)
                    or (action_verb in r_action)
                    or (r_action in action_verb)
                    or (r_action in mapped_legacy)
                )
                target_ok = bool(
                    r_target
                    and (
                        (target_lower in r_target)
                        or (r_target in target_lower)
                        or target_lower in ("it", "that", "this", "them", "those")
                    )
                )
                if action_ok and target_ok:
                    matched = True
                    break
            if not matched:
                ungrounded.append(target_obj)

        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        if ungrounded:
            return GateResult(
                is_breach=True,
                breach_type="ungrounded_action",
                severity=SeverityTier.TIER_1_ABORT,
                matched_text=m.group(0),
                reason=(
                    f"Claimed action '{action_verb}' on ungrounded object(s) {ungrounded} "
                    "without matching ToolReceipt"
                ),
                elapsed_us=elapsed_us,
            )

        return GateResult(
            False,
            None,
            SeverityTier.PASS,
            m.group(0),
            "Action claim verified by ToolReceipt",
            elapsed_us,
        )


WHITELISTED_DOC_DOMAINS: frozenset[str] = frozenset(
    {
        "github.com",
        "docs.python.org",
        "python.org",
        "pypi.org",
        "wikipedia.org",
        "en.wikipedia.org",
        "w3.org",
        "www.w3.org",
        "example.com",
    }
)

URL_EXTRACTION_REGEX = re.compile(
    r"(?:https?://[^\s<>\"'()]+|\b[a-zA-Z0-9.-]+\.(?:com|org|net|gov|edu|mil|int|io|ai|co|ph|uk|de|ca|judiciary)(?:/[^\s<>\"'()]+)?\b)",
    re.IGNORECASE,
)


def canonicalize_citation_url(raw_url: str) -> str:
    cleaned = raw_url.rstrip(".,;:!?'\")>]")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    try:
        parsed = urllib.parse.urlsplit(cleaned)
        netloc = parsed.netloc.lower().split(":")[0]
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme.lower()}://{netloc}{path}"
    except Exception as exc:
        logger.debug("canonicalize_citation_url_failed", error=str(exc))
        return cleaned.lower().rstrip("/")


class CitationProvenanceMatcher:
    """
    Validates that URLs and official citations cited in generated assistant text
    have verified provenance in ToolReceipts, EpistemicContext, or verified tool output.
    Prevents hallucination of fake authoritative URLs (Dimension 7B Provenance Invariant).
    """

    def __init__(self, doc_whitelist: frozenset[str] | None = None) -> None:
        self.doc_whitelist = doc_whitelist or WHITELISTED_DOC_DOMAINS

    def evaluate_clause(self, clause: str, allowed_urls: Sequence[str] | None = None) -> GateResult:
        t0 = time.perf_counter()
        clean = clause.strip()
        if not clean:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, SeverityTier.PASS, None, "Empty clause", elapsed_us)

        # Normalize allowed URLs into canonical set
        canon_allowed: set[str] = set()
        allowed_domains: set[str] = set()
        if allowed_urls:
            for u in allowed_urls:
                if not u:
                    continue
                c = canonicalize_citation_url(str(u))
                canon_allowed.add(c)
                try:
                    p = urllib.parse.urlsplit(c)
                    if p.netloc:
                        allowed_domains.add(p.netloc.lower())
                except Exception as exc:
                    logger.debug("extract_domain_failed", error=str(exc))

        # Find candidate citations in clause
        matches = URL_EXTRACTION_REGEX.findall(clean)
        for raw_match in matches:
            # Reject email addresses (preceded by @)
            match_idx = clean.find(raw_match)
            if match_idx > 0 and clean[match_idx - 1] == "@":
                continue

            cleaned_url = raw_match.rstrip(".,;:!?'\")>]")
            canon = canonicalize_citation_url(cleaned_url)

            try:
                parsed = urllib.parse.urlsplit(canon)
                netloc = parsed.netloc.lower()
            except Exception as exc:
                logger.debug("parse_canon_url_failed", error=str(exc))
                netloc = ""

            # Check whitelist exemptions (docs, standard educational/dev domains)
            if any(netloc == wl or netloc.endswith("." + wl) for wl in self.doc_whitelist):
                continue

            # Check local development ports / services (devops context)
            if netloc in ("localhost", "127.0.0.1") or netloc.startswith(
                ("localhost:", "127.0.0.1:")
            ):
                if (
                    canon in canon_allowed
                    or (
                        ":" in cleaned_url
                        and not cleaned_url.startswith(
                            ("http://localhost:80/", "https://localhost:443/")
                        )
                    )
                    or any("localhost" in a or "127.0.0.1" in a for a in canon_allowed)
                ):
                    continue

            # Check exact match against verified receipts
            if canon in canon_allowed:
                continue

            # Check if citing a parent section or root of an allowed deep URL
            if any(a.startswith(canon) for a in canon_allowed):
                continue

            # Check if an allowed URL was registered as an explicit directory path (ending in '/')
            if any(a.endswith("/") and canon.startswith(a) for a in canon_allowed):
                continue

            # Ungrounded citation detected!
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                is_breach=True,
                breach_type="ungrounded_citation",
                severity=SeverityTier.TIER_1_ABORT,
                matched_text=cleaned_url,
                reason=(
                    f"Emitted ungrounded citation URL '{cleaned_url}' without verified "
                    "provenance in tool receipts or epistemic context"
                ),
                elapsed_us=elapsed_us,
            )

        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        return GateResult(
            False,
            None,
            SeverityTier.PASS,
            None,
            "All citations verified or none present",
            elapsed_us,
        )
