"""
Project Lucca — Grammar-Constrained Action-Claim Supervisor (WO-43 Phase 3.2)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §2
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from pathlib import Path

import structlog
from pydantic import JsonValue

from lucca.sandbox.supervisor_lexicon import (
    _CANONICAL_ACTION_REGEX,
    _COMPANION_ACTION_CLAIM_REGEX,
    _CONVERSATIONAL_META_TARGETS_REGEX,
    _FUTURE_INTENT_PATTERN,
    _HOST_FILE_TARGET_PATTERN,
    _ILLUSTRATIVE_FRAME_PREFIX_REGEX,
    _INITIATING_ACTION_REGEX,
    _INTRANSITIVE_RUNTIME_ENV_REGEX,
    _NEGATION_PREFIX_PATTERN,
    _NON_CLAIM_SUBJECT_PREFIX,
    _PASSIVE_ACTION_REGEX,
    _PROGRESSIVE_ACTION_REGEX,
    _STAGE_DIRECTION_OR_FAKE_SCAN_REGEX,
    _SYNCHRONOUS_EXECUTION_FUTURE_REGEX,
    _TELEGRAPHIC_ACTION_REGEX,
    ALL_ACTION_VERBS,
    COMPANION_BOUND_STEM_MAP,
    EXPANDED_STEM_MAP,
    HEDGE_PATTERN,
    IDIOMATIC_NON_ACTION_PATTERN,
    PAST_CONTEXT_PATTERN,
    STRUCTURED_ACTION_TAG_REGEX,
    GateResult,
    SeverityTier,
    is_elliptical_action_confirmation,
    is_meta_or_creative_context,
    is_simulated_inspection_readout,
)

logger = structlog.get_logger(__name__)


class ActionClaimGrammarSupervisor:
    """
    Grammar-Constrained Action-Claim Channel Supervisor (SPIKE-A / D-SEC-06).
    Enforces that action assertions emitted on the speech/narration channel
    strictly conform to verified grammatical frames and ToolReceipt provenance.

    Structurally eliminates the 4 live-audit escape modes (Finding P7):
    1. Active progressive participles ("Moving all PDFs...", "Rebooting host...")
    2. Passive and telegraphic confirmations ("Files removed", "Reminder set", "Target cleared")
    3. Unlisted verb lemmas ("launch", "open", "terminate", "archive", "update", "format")
    4. Markdown action headers and bullet points ("### Deleting logs", "* Moving files")

    Supports explicit structured channels:
    - [ACTION: <verb> <target>]
    - [ACTION_CLAIM: <verb> <target>]
    - <action_claim verb="..." target="..." />
    - <action_claim><verb> <target></action_claim>
    """

    SUCCESS_STATUSES: frozenset[str] = frozenset(
        {"success", "succeeded", "ok", "completed", "done"}
    )

    def __init__(
        self,
        grammar_path: Path | str | None = None,
        use_neural_verifier: bool = True,
    ) -> None:
        self.grammar_path = Path(grammar_path or "config/grammars/action_claim.gbnf")
        self.use_neural_verifier = use_neural_verifier
        self._grammar_text: str | None = None
        if self.grammar_path.exists():
            try:
                self._grammar_text = self.grammar_path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                logger.debug("action_claim_gbnf_load_failed", path=str(self.grammar_path),
                    error=str(exc))

    def evaluate_clause(
        self,
        clause: str,
        verified_receipts: Sequence[dict[str, JsonValue]],
        stale_before: float | None = None,
        user_context: str | Sequence[dict[str, str]] | None = None,
        full_narration: str | None = None,
        use_neural_verifier: bool | None = None,
    ) -> GateResult:
        """
        Evaluates a streamed clause for ungrounded physical/stateful action claims
        under grammar-constrained channel rules (<= 1.0 ms budget, target < 100 us).
        Supports conversational user_context and full_narration framing (v3.0 / WO-41).
        """
        t0 = time.perf_counter()

        run_neural = (
            self.use_neural_verifier if use_neural_verifier is None else use_neural_verifier
        )
        if run_neural and user_context is not None:
            try:
                from lucca.sandbox.neural_claim_verifier import (  # noqa: PLC0415
                    get_neural_claim_verifier,
                )

                nv = get_neural_claim_verifier()
                if nv.available:
                    ok_tool_strs: list[str] = []
                    for r in verified_receipts:
                        st = str(r.get("status", "ok")).lower()
                        if st not in self.SUCCESS_STATUSES:
                            continue
                        if stale_before is not None:
                            ts_val = r.get("timestamp") or r.get("ts")
                            if isinstance(ts_val, (int, float)) and float(ts_val) < stale_before:
                                continue
                        act = str(r.get("action") or r.get("tool") or r.get("tool_name") or "")
                        tgt = str(r.get("target") or "")
                        if act:
                            ok_tool_strs.append(f"{act}({tgt!r})" if tgt else act)
                    verdict = nv.evaluate(
                        completion=full_narration if full_narration else clause,
                        user_context=user_context,
                        verified_tools=ok_tool_strs,
                    )
                    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                    if verdict.is_ungrounded_claim:
                        return GateResult(
                            True,
                            "ungrounded_action",
                            SeverityTier.TIER_1_ABORT,
                            clause.strip(),
                            (
                                f"OpenVINO 4-Class Neural Verifier ({verdict.device}) "
                                f"detected ungrounded action/state claim "
                                f"(class={verdict.predicted_class}, "
                                f"p={verdict.prob_ungrounded_claim:.3f})."
                            ),
                            elapsed_us,
                        )
                    return GateResult(
                        False,
                        None,
                        SeverityTier.PASS,
                        None,
                        f"OpenVINO 4-Class Neural Verifier PASS (class={verdict.predicted_class})",
                        elapsed_us,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("grammar_supervisor_neural_hook_failed", error=str(exc))

        # 0a. Context Gate A (v3.0): Meta-linguistic, creative writing, roleplay dialogue,
        # translation, grammar correction, UI copywriting, or code/JSON template request.
        if is_meta_or_creative_context(
            clause, user_context=user_context, full_narration=full_narration
        ):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Meta-linguistic, creative, or quoted example context (not a host action claim)",
                elapsed_us,
            )

        # 0. Markdown normalization: strip header hashes, bullet points, checkboxes,
        # formatting, and leading status labels left after emphasis stripping.
        raw_clean = re.sub(r"[*`~]", "", clause.strip()).strip()
        raw_clean = re.sub(r"^\s*#+\s*", "", raw_clean)
        raw_clean = re.sub(r"^\s*[\*\-\+]\s+", "", raw_clean)
        raw_clean = re.sub(r"^\s*\[(?:done|x|\s)\]\s*", "", raw_clean, flags=re.IGNORECASE)
        raw_clean = re.sub(r"^\s*\d+\.\s*", "", raw_clean).strip()

        clean = re.sub(
            r"^(?:(?:action|status|step|task|confirmation|success|result)\s*:\s*|"
            r"(?:done|understood|acknowledged|okay|got\s+it|sure\s+thing|no\s+problem|on\s+it|i'm\s+on\s+it)\s*[.!,—\-]+\s*)+",
            "",
            raw_clean,
            flags=re.IGNORECASE,
        ).strip()

        if not clean and not raw_clean:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(False, None, SeverityTier.PASS, None, "Empty clause", elapsed_us)
        if not clean:
            clean = raw_clean

        # 1. Check synchronous execution / completion-notification patterns before future intent
        # filter
        is_sync_future = bool(_SYNCHRONOUS_EXECUTION_FUTURE_REGEX.search(clean))
        has_stage_or_fake_scan = bool(
            _STAGE_DIRECTION_OR_FAKE_SCAN_REGEX.search(clause)
            or _STAGE_DIRECTION_OR_FAKE_SCAN_REGEX.search(raw_clean)
        )
        is_sim_inspect = is_simulated_inspection_readout(clause, full_narration=full_narration)
        if (
            not is_sync_future
            and not has_stage_or_fake_scan
            and not is_sim_inspect
            and _FUTURE_INTENT_PATTERN.search(clean)
        ):
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
        if IDIOMATIC_NON_ACTION_PATTERN.search(clean):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Idiomatic/figurative non-action phrasing",
                elapsed_us,
            )

        # 3. Reject hedged / epistemic claims
        if HEDGE_PATTERN.search(clean):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Hedged/epistemic claim (speaker uncertain)",
                elapsed_us,
            )

        # 4. Past-session recollection exemption
        if PAST_CONTEXT_PATTERN.search(clean):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Past-session recollection (grounded in autobiographical memory)",
                elapsed_us,
            )

        # 4b. Intransitive runtime environment self-description exemption (W192, W547)
        if _INTRANSITIVE_RUNTIME_ENV_REGEX.search(clean):
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "Intransitive runtime environment description (not a tool execution claim)",
                elapsed_us,
            )

        # Filter receipts that are eligible to ground claims
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
                        logger.debug("receipt_timestamp_unparseable", raw_ts=str(raw_ts))
            eligible_receipts.append(r)

        def _is_grounded(verb: str, target_phrase: str) -> bool:
            v_norm = verb[4:] if verb.startswith("got_") else verb
            stem = EXPANDED_STEM_MAP.get(
                v_norm, COMPANION_BOUND_STEM_MAP.get(v_norm, v_norm)
            ).lower()
            t_clean = re.sub(
                r"^(?:the|a|an|your|my|our|this|that|these|those|all)\s+",
                "",
                target_phrase.lower(),
                flags=re.IGNORECASE,
            ).strip(".,!?;:\"' ")
            t_unquoted = t_clean.replace("'", "").replace('"', "")
            tool_map: dict[str, tuple[str, ...]] = {
                "save": ("note_write", "write_file", "memory_commit", "inbox_handoff",
                    "schedule_event"),
                "write": ("note_write", "write_file", "memory_commit"),
                "create": ("note_write", "write_file", "memory_commit", "schedule_event"),
                "note": ("note_write", "memory_commit"),
                "add": ("note_write", "write_file", "memory_commit", "schedule_event"),
                "store": ("note_write", "write_file", "memory_commit"),
                "schedule": ("schedule_event", "note_write"),
                "run": ("run_python", "calc_math"),
                "execute": ("run_python", "calc_math"),
                "search": ("memory_search", "search_web", "search_text", "self_history_search"),
                "read": ("read_file", "clipboard_read", "memory_search", "artifact_verify"),
                "delete": ("delete_file",),
                "remove": ("delete_file",),
                "launch": ("launch_app",),
                "open": ("launch_app",),
            }
            mapped_tools = tool_map.get(stem, ())
            for r in eligible_receipts:
                r_action = str(r.get("action", "")).lower()
                r_target = str(r.get("target", r.get("path", ""))).lower().strip(".,!?;:\"' ")
                r_unquoted = r_target.replace("'", "").replace('"', "")
                action_ok = (
                    (stem in r_action)
                    or (r_action in stem)
                    or (v_norm in r_action)
                    or (r_action in mapped_tools)
                )
                target_ok = bool(
                    r_unquoted
                    and (
                        (t_unquoted in r_unquoted)
                        or (r_unquoted in t_unquoted)
                        or t_unquoted in ("it", "that", "this", "them", "those")
                    )
                )
                if action_ok and target_ok:
                    return True
            return False

        # 5. Extract structured action claims [ACTION: ...] or <action_claim ...>
        structured_matches: list[tuple[str, str, str]] = []
        for sm in STRUCTURED_ACTION_TAG_REGEX.finditer(clause):
            prefix_before_tag = clause[: sm.start()]
            if _ILLUSTRATIVE_FRAME_PREFIX_REGEX.search(prefix_before_tag):
                continue
            v = sm.group(1) or sm.group(3) or sm.group(5)
            t = sm.group(2) or sm.group(4) or sm.group(6)
            if v and t:
                v_clean = v.strip().lower()
                t_clean = t.strip()
                v_stem = EXPANDED_STEM_MAP.get(v_clean, v_clean)
                if v_stem not in ALL_ACTION_VERBS or _CONVERSATIONAL_META_TARGETS_REGEX.match(
                    t_clean):
                    continue
                structured_matches.append((v_clean, t_clean, sm.group(0)))

        if structured_matches:
            for v, t, raw in structured_matches:
                if not _is_grounded(v, t):
                    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                    return GateResult(
                        is_breach=True,
                        breach_type="ungrounded_action",
                        severity=SeverityTier.TIER_1_ABORT,
                        matched_text=raw,
                        reason=f"Claimed structured action '{raw}' without matching ToolReceipt",
                        elapsed_us=elapsed_us,
                    )
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                clean,
                "Structured action claims verified by ToolReceipt",
                elapsed_us,
            )

        # 6. Natural Language Claim Identification
        claims_to_verify: list[tuple[str, str, str]] = []

        # (a0) Synchronous execution future / completion-notification claim
        if is_sync_future:
            m_sync = _SYNCHRONOUS_EXECUTION_FUTURE_REGEX.search(clean)
            if m_sync and not _NEGATION_PREFIX_PATTERN.search(clean[: m_sync.start()].lower()):
                claims_to_verify.append(("execute", clean, m_sync.group(0)))

        # (a0b) Roleplayed stage directions or simulated live inspection scans
        if not claims_to_verify and has_stage_or_fake_scan:
            m_stage = _STAGE_DIRECTION_OR_FAKE_SCAN_REGEX.search(
                clause
            ) or _STAGE_DIRECTION_OR_FAKE_SCAN_REGEX.search(raw_clean)
            if m_stage:
                claims_to_verify.append(("scan", m_stage.group(0).strip(), m_stage.group(0)))

        # (a) Canonical 1P past tense: "I deleted file.txt"
        if not claims_to_verify:
            m_canon = _CANONICAL_ACTION_REGEX.search(clean)
            if m_canon:
                prefix = clean[: m_canon.start()].lower()
                if not _NEGATION_PREFIX_PATTERN.search(prefix):
                    verb = m_canon.group(1).lower()
                    remainder = m_canon.group(2).strip()
                    remainder = re.sub(
                        r"\s+(?:for\s+you|as\s+requested|now|for\s+your\s+records|from\s+the\s+workspace)[\.!]?$",
                        "",
                        remainder,
                        flags=re.IGNORECASE,
                    )
                    remainder = re.sub(r"^\s*both\s+", "", remainder, flags=re.IGNORECASE)
                    raw_targets = [t.strip() for t in re.split(r"\s+and\s+|\s*,\s*",
                        remainder) if t.strip()]
                    for target_item in raw_targets:
                        claims_to_verify.append((verb, target_item, m_canon.group(0)))

        # (b) Initiating or execution status banner: "I'm initiating the reboot now", "Command
        # executed:"
        if not claims_to_verify:
            m_init = _INITIATING_ACTION_REGEX.search(
                raw_clean) or _INITIATING_ACTION_REGEX.search(clean)
            if m_init:
                prefix = raw_clean[: m_init.start()].lower()
                if not _NEGATION_PREFIX_PATTERN.search(prefix):
                    verb_noun = (m_init.group(1) or "execute").lower()
                    stem = "reboot" if (
                        "reboot" in verb_noun or "restart" in verb_noun) else verb_noun
                    target = m_init.group(2) or verb_noun
                    claims_to_verify.append((stem, target, m_init.group(0)))

        # (c) Active progressive: "Rebooting the host system...", "Moving all PDFs..."
        if not claims_to_verify:
            m_prog = _PROGRESSIVE_ACTION_REGEX.search(clean)
            if m_prog:
                prefix = clean[: m_prog.start()].lower()
                if not _NEGATION_PREFIX_PATTERN.search(prefix) and not re.search(
                    r"\b(?:by|for|while|worth|when|if|after|before|without|to|such\s+as|than|from|in|on|of|about|into|involves|since|because|as)\s*$",
                    prefix,
                    re.IGNORECASE,
                ):
                    is_explicit_1p = m_prog.group(1) is not None
                    verb = (m_prog.group(1) or m_prog.group(3)).lower()
                    target = (m_prog.group(2) or m_prog.group(4)).strip()
                    # Strip harmless completion / in-progress tail before checking gerund predicate
                    # verbs
                    target_for_check = re.sub(
                        r"\s+(?:will\s+take\s+a\s+(?:moment|second|minute|few\s+\w+)|is\s+(?:in\s+progress|currently\s+running|underway|complete|done))[\.!]?$",
                        "",
                        target,
                        flags=re.IGNORECASE,
                    )
                    is_gerund_subject = bool(
                        re.search(
                            r"\b(?:is|are|was|were|can|could|will|would|should|may|might|must|"
                            r"makes|means|requires|helps|allows|provides|causes|involves|"
                            r"installs|works|operates|affects|distributes|prevents|ensures|takes|shows|"
                            r"risks|breaks|corrupts|locks|exposes|leads|results|triggers|avoids|overwrites)\b",
                            target_for_check,
                            re.IGNORECASE,
                        )
                    )
                    is_bare_preposition = bool(
                        re.match(r"^(?:on|in|at|to|from|with|by|for|of|a"
                            r"s)\b[\.!]?$", target, re.IGNORECASE)
                    )
                    is_definition_or_title_header = (
                        not is_explicit_1p
                        and ":" in target
                        and not re.search(
                            r"(?:https?|ftp|s3|:\d{2,5}|[a-zA-Z]:[\\/]|:\s*[\"'])",
                            target,
                            re.IGNORECASE,
                        )
                    )
                    is_parenthetical_fragment = (
                        (")" in target and "(" not in target)
                        or (not is_explicit_1p and bool(raw_clean) and raw_clean[0].islower())
                        or (not is_explicit_1p and clean.endswith(":"))
                    )
                    has_concrete_target = (
                        is_explicit_1p
                        or bool(_HOST_FILE_TARGET_PATTERN.search(target))
                        or bool(re.search(r"\bnow[\.!]*$|\.{3}$", target, re.IGNORECASE))
                    )
                    if (
                        not is_gerund_subject
                        and not is_bare_preposition
                        and not is_definition_or_title_header
                        and not is_parenthetical_fragment
                        and has_concrete_target
                    ):
                        target = re.sub(
                            r"\s+(?:now|from\s+Downloads|to\s+Documents.*|please\s+give\s+me\s+a\s+moment|will\s+take\s+a\s+moment)[\.!]?$",
                            "",
                            target,
                            flags=re.IGNORECASE,
                        )
                        claims_to_verify.append((verb, target, m_prog.group(0)))

        # (d) Passive: "The file was deleted from the workspace"
        # Scope restriction: the target must be a concrete host/file-like
        # resource (path, extension, port, or system noun). Generic prose
        # ("an employment contract is terminated") is not an action claim.
        if not claims_to_verify:
            m_pass = _PASSIVE_ACTION_REGEX.search(clean)
            if m_pass:
                prefix = clean[: m_pass.start()].lower()
                target = m_pass.group(1).strip()
                suffix_after_pass = clean[m_pass.end() :].lower()
                if (
                    not _NEGATION_PREFIX_PATTERN.search(prefix)
                    and not _NON_CLAIM_SUBJECT_PREFIX.search(target)
                    and not re.search(
                        r"\b(?:if|whether|when|how|why|where|is|are|was|were|that|which|who)\b|:\s",
                        target,
                        re.IGNORECASE,
                    )
                    and not re.match(
                        r"^\s*(?:instantly\s+|immediately\s+|automatically\s+)?by\s+(?:the\s+)?(?:kernel|os|operating\s+system|cpu|hardware|browser|scheduler)\b",
                        suffix_after_pass,
                    )
                    and _HOST_FILE_TARGET_PATTERN.search(target)
                ):
                    verb = m_pass.group(2).lower()
                    claims_to_verify.append((verb, target, m_pass.group(0)))

        # (e) Telegraphic: "Files removed.", "Reminder set for tomorrow."
        if not claims_to_verify:
            m_tele = _TELEGRAPHIC_ACTION_REGEX.search(clean)
            if m_tele:
                prefix = clean[: m_tele.start()].lower()
                target = m_tele.group(1).strip()
                if (
                    not _NEGATION_PREFIX_PATTERN.search(prefix)
                    and not _NON_CLAIM_SUBJECT_PREFIX.search(target)
                    and not re.search(
                        r"\b(?:if|whether|when|how|why|where|is|are|was|were|has|have|that|which|who)\b|:\s",
                        target,
                        re.IGNORECASE,
                    )
                    and _HOST_FILE_TARGET_PATTERN.search(target)
                ):
                    verb = m_tele.group(2).lower()
                    claims_to_verify.append((verb, target, m_tele.group(0)))

        # (f) Everyday Companion Action, Phrasal, & Copular State-of-Completion Claims (v3.0)
        if not claims_to_verify:
            m_comp = _COMPANION_ACTION_CLAIM_REGEX.search(
                clean
            ) or _COMPANION_ACTION_CLAIM_REGEX.search(raw_clean)
            if m_comp:
                prefix_comp = raw_clean[: m_comp.start()].lower()
                if not _NEGATION_PREFIX_PATTERN.search(prefix_comp):
                    claims_to_verify.append(("update", m_comp.group(0).strip(), m_comp.group(0)))

        # (g) Context-Aware Multi-Turn Elliptical Action Completion ("Done. How does that look for
        # you?")
        if not claims_to_verify and is_elliptical_action_confirmation(
            clause, user_context=user_context, full_narration=full_narration
        ):
            if re.match(
                r"^\s*(?:done|all\s+done|all\s+set|taken\s+care\s+of)\b",
                raw_clean,
                re.IGNORECASE,
            ):
                claims_to_verify.append(("complete", "confirmed_companion_action", raw_clean))

        # (h) Single-Turn Simulated Inspection + Readout ("Let me check your schedule. Yep, you
        # have...")
        if not claims_to_verify and is_sim_inspect:
            claims_to_verify.append(("inspect", "simulated_live_inspection", raw_clean))

        if not claims_to_verify:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return GateResult(
                False,
                None,
                SeverityTier.PASS,
                None,
                "No completed action claim matched",
                elapsed_us,
            )

        # 7. Grounding verification
        ungrounded: list[str] = []
        for verb, target, _matched_text in claims_to_verify:
            if not _is_grounded(verb, target):
                ungrounded.append(f"{verb} {target}")

        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        if ungrounded:
            first_match_text = claims_to_verify[0][2]
            return GateResult(
                is_breach=True,
                breach_type="ungrounded_action",
                severity=SeverityTier.TIER_1_ABORT,
                matched_text=first_match_text,
                reason=(
                    f"Claimed action on ungrounded object(s) {ungrounded} "
                    "without matching ToolReceipt"
                ),
                elapsed_us=elapsed_us,
            )

        return GateResult(
            False,
            None,
            SeverityTier.PASS,
            claims_to_verify[0][2],
            "Action claim verified by ToolReceipt",
            elapsed_us,
        )
