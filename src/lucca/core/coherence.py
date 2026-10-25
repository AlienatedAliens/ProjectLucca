"""
Project Lucca — Functional Coherence Action Claim Checker
Spec §3.3, D-MEM-04, F-TS-04, Work Order #8 WP-2

Evaluates spoken companion narration against verified tool receipts.
Detects ungrounded action claims (hallucinations, verb/tool mismatches, failed tool claims)
while guarding against benign rhetorical and idiomatic false-positive traps.

Zero-Any invariant enforced.

Known Limits:
1. Lexical Pattern Matching: Uses regexes for past-tense active actions and passive completions;
   novel colloquial paraphrases not present in the grammar patterns may be unclassified.
2. Idiom Coverage: Cognitive and metaphorical verbs ("saved my energy", "ran into a problem")
   are guarded via EXCLUDED_IDIOMS. Novel metaphors not in the list may require addition.
3. Grammar Ambiguity: Gerunds ("launching Notepad now") can indicate current in-progress actions
   or conversational declarations. When uttered as completion without matching receipts, they
   are flagged per Spec §3.3.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

import structlog
from pydantic import BaseModel, Field, model_validator

from lucca.core.capabilities import get_capability_registry
from lucca.core.schemas import JsonValue, VerifierLabel
from lucca.ports import SemanticVerifierPort

logger = structlog.get_logger(__name__)


def get_tool_family_map() -> dict[str, frozenset[str]]:
    """
    Returns mapping from claimed verb families to registered tool names,
    sourced dynamically from the capability registry.
    """
    try:
        reg = get_capability_registry()
        reg_tools = set(reg.tools.keys())
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_capability_registry_failed", error=str(exc))
        reg_tools = {
            "write_file",
            "launch_app",
            "search_web",
            "fetch_url",
            "read_file",
            "delete_file",
            "run_python",
        }

    save_tools = frozenset(
        (reg_tools & {"write_file", "edit_file", "note_write"}) or {"write_file"}
    )
    launch_tools = frozenset((reg_tools & {"launch_app"}) or {"launch_app"})
    search_tools = frozenset((reg_tools & {"search_web", "search_text"}) or {"search_web"})
    fetch_tools = frozenset((reg_tools & {"fetch_url"}) or {"fetch_url"})
    read_tools = frozenset(
        (reg_tools & {"read_file", "fetch_url", "note_read"}) or {"read_file", "fetch_url"}
    )
    delete_tools = frozenset((reg_tools & {"delete_file"}) or {"delete_file"})
    run_tools = frozenset((reg_tools & {"run_python"}) or {"run_python"})
    # WO-9 A7 (F7): memory and skill operations were missing from the family
    # map, so honest claims like "I checked my memory records" or "I invoked
    # the pathway" were ungroundable even with receipts.
    memory_search_tools = frozenset((reg_tools & {"memory_search"}) or {"memory_search"})
    memory_commit_tools = frozenset((reg_tools & {"memory_commit"}) or {"memory_commit"})
    skill_tools = frozenset((reg_tools & {"invoke_skill"}) or {"invoke_skill"})

    return {
        "save": save_tools,
        "write": save_tools,
        "create": save_tools,
        "update": save_tools,
        "launch": launch_tools,
        "open": launch_tools,
        "start": launch_tools,
        "search": search_tools,
        "lookup": search_tools,
        "fetch": fetch_tools,
        "read": read_tools,
        "delete": delete_tools,
        "remove": delete_tools,
        "run": run_tools,
        "execute": run_tools,
        "memory_search": memory_search_tools,
        "recall": memory_search_tools,
        "memory_commit": memory_commit_tools,
        "invoke_skill": skill_tools,
    }


# Idioms that use action verbs in benign, purely cognitive or rhetorical contexts
EXCLUDED_IDIOMS: tuple[str, ...] = (
    "ran into a problem",
    "ran across",
    "ran through",
    "ran the numbers in my head",
    "run the numbers",
    "run the math",
    "run through that",
    "run a check",
    "ran the numbers",
    "ran the math",
    "ran a check",
    "written poetry",
    "wrote a song",
    "wrote down my feelings mentally",
    "opened up to you",
    "opened my mind",
    "opened up new ways",
    "opened the conversation",
    "mental note",
    "updated my understanding",
    "updated my perspective",
    "updated my model",
    "updated my thoughts",
    "saved you the trouble",
    "saved a lot of time",
    "saved my energy",
    "saved that thought",
    "launched into",
    "launched a train of thought",
    "created a peaceful environment",
    "created an internal representation",
    "created an impression",
    "deleted that thought",
    "deleted unnecessary assumptions",
)

# Past-session temporal markers: recollections of PRIOR verified actions are
# grounded by long-term memory (A1 autobiographical substrate), not by
# current-turn ToolReceipts. Functional coherence (Spec §3.3) governs claims
# about actions performed THIS turn.
PAST_CONTEXT_PATTERN = re.compile(
    r"\b(?:"
    r"last\s+session|previous\s+session|prior\s+session|earlier\s+session|"
    r"a\s+few\s+days?\s+ago|days?\s+ago|weeks?\s+ago|yesterday|"
    r"last\s+week|previously|in\s+the\s+past|earlier\s+on|"
    r"records?\s+(?:from|show|showing|indicate)|my\s+records|"
    r"memor(?:y|ies)\s+(?:from|show|showing)|from\s+our\s+history|"
    r"in\s+our\s+history|histor(?:y|ical)\s+records?|"
    r"during\s+our\s+last|from\s+a\s+few\s+days|"
    r"back\s+when|first\s+written|originally\s+written|"
    r"my\s+architecture\s+is|architecture\s+is\s+more\s+about|"
    r"designed\s+as\s+a|built\s+for"
    r")\b",
    re.IGNORECASE,
)

# Negation / uncertainty framing that invalidates an action-claim hit:
# "I don't have any records showing that I deleted X" is an abstention,
# not a claim of action. NOTE: success qualifiers like "without errors" /
# "no errors" must NOT trigger this guard — they assert successful completion
# (F-WO8-16 refinement: the passive-branch guard uses the strong-negation set).
NEGATION_GUARD_PATTERN = re.compile(
    r"\b(?:"
    r"not\s+|never|don't|do\s+not|doesn't|didn't|did\s+not|cannot|can't|"
    r"won't|will\s+not|unable\s+to|not\s+sure\s+if|whether\s+or\s+not|"
    r"records?\s+showing\s+that"
    r")\b",
    re.IGNORECASE,
)


class ToolReceipt(BaseModel, frozen=True):
    """Execution receipt for an invoked tool call."""

    tool: str = ""
    tool_name: str = ""
    ok: bool = True
    call_id: str = ""
    args: dict[str, JsonValue] = Field(default_factory=dict)
    output: str | None = None
    error: str | None = None
    timestamp: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def _normalize_tool_name(cls, data: object) -> object:
        if isinstance(data, dict):
            t = str(data.get("tool") or data.get("tool_name") or "")
            data["tool"] = t
            data["tool_name"] = t
        return data

    @property
    def resolved_tool(self) -> str:
        return self.tool or self.tool_name


class CoherenceClaim(BaseModel, frozen=True):
    """Action claim extracted from assistant narration and its grounding status."""

    claimed_verb: str
    claimed_text: str
    tool_family: str
    grounded: bool
    breach_description: str | None = None


def format_tool_receipts_for_nli(receipts: Sequence[ToolReceipt]) -> str:
    """Formats verified tool execution receipts into a structured NLI premise string (SPIKE-A / Milestone 36.6)."""
    ok_lines = [
        f"Tool {r.resolved_tool} succeeded with args {r.args} and output: {r.output or ''}"
        for r in receipts
        if r.ok and r.resolved_tool
    ]
    if not ok_lines:
        return "No tools were executed successfully this turn."
    return "; ".join(ok_lines)


def detect_ungrounded_action_claims(
    narration: str,
    receipts: Sequence[ToolReceipt],
    verifier: SemanticVerifierPort | None = None,
) -> list[CoherenceClaim]:
    """
    Pure function detecting action claims in narration and verifying against tool receipts.
    A claim is a breach iff no receipt in the provided receipts has a tool in the claimed family
    AND ok=True.
    """
    if not narration.strip():
        return []

    narration_low = narration.lower()
    claims: list[CoherenceClaim] = []
    tool_family_map = get_tool_family_map()

    # Successful tools set
    successful_tools = {r.resolved_tool for r in receipts if r.ok and r.resolved_tool}

    # Split narration into clause-like segments
    clauses = re.split(r"[.!?;\n]+", narration_low)

    for raw_clause in clauses:
        clause = raw_clause.strip()
        if not clause:
            continue

        # Check idiom exclusions
        if any(idiom in clause for idiom in EXCLUDED_IDIOMS):
            continue

        detected_family: str | None = None
        matched_verb: str | None = None

        # 0. Past-session recollection exemption: claims framed as recollections
        # of PRIOR sessions are grounded by long-term memory, not current-turn
        # receipts. Only current-turn action claims require receipt verification.
        if PAST_CONTEXT_PATTERN.search(clause):
            continue

        # 0b. Structured GBNF action-claim tags (SPIKE-A): [ACTION: <verb> <target>] or <action_claim ...>
        tag_match = re.search(
            r"(?:\[(?:action|action_claim)\s*:\s*([a-z_]+)\s+([^\]]+)\]|"
            r"<action_claim(?:\s+verb=[\"']([a-z_]+)[\"']\s+target=[\"']([^\"']+)[\"']|"
            r">\s*([a-z_]+)\s+([^<]+)</action_claim>))",
            clause,
            re.IGNORECASE,
        )
        if tag_match:
            v_tag = (tag_match.group(1) or tag_match.group(3) or tag_match.group(5) or "").strip().lower()
            matched_verb = v_tag
            if v_tag in ("save", "saved", "write", "wrote", "create", "created", "modify", "modified", "update", "updated", "copy", "copied", "move", "moved"):
                detected_family = "save"
            elif v_tag in ("launch", "launched", "open", "opened", "start", "started", "close", "closed", "reboot", "rebooted"):
                detected_family = "launch"
            elif v_tag in ("search", "searched", "lookup", "looked_up"):
                detected_family = "search"
            elif v_tag in ("fetch", "fetched", "send", "sent", "upload", "uploaded", "post", "posted"):
                detected_family = "fetch"
            elif v_tag in ("read",):
                detected_family = "read"
            elif v_tag in ("delete", "deleted", "remove", "removed"):
                detected_family = "delete"
            elif v_tag in ("run", "ran", "execute", "executed", "install", "installed", "process", "processed"):
                detected_family = "run"
            else:
                detected_family = "save"

        # 1. Active first-person action claims
        # e.g., "I saved it", "I launched Notepad", "I fetched the page", "I ran the script"
        active_match = (
            None
            if detected_family
            else re.search(
                r"\b(?:i(?:'ve| have)?)\s+(?:just\s+|already\s+|successfully\s+)?"
                r"(saved|wrote|written|updated|modified|copied|moved|launched|opened|started|closed|searched|"
                r"looked up|fetched|uploaded|sent|posted|read|deleted|removed|ran|executed|installed|processed|rebooted|booked|placed|created|"
                r"checked|committed|invoked|recalled|queried)\b",
                clause,
            )
        )
        if active_match:
            # Negation guard: a negation/uncertainty token preceding the verb
            # within the clause invalidates the claim ("...records showing that
            # I deleted X" is an abstention, not an action claim).
            prefix = clause[: active_match.start(1)]
            if NEGATION_GUARD_PATTERN.search(prefix):
                continue
            v = active_match.group(1)
            matched_verb = v
            if v in ("saved", "wrote", "written", "created", "updated", "modified", "copied", "moved", "placed"):
                detected_family = "save"
            elif v in ("launched", "opened", "started", "closed", "rebooted"):
                detected_family = "launch"
            elif v in ("searched", "looked up"):
                detected_family = "search"
            elif v in ("fetched", "uploaded", "sent", "posted", "booked"):
                detected_family = "fetch"
            elif v == "read":
                detected_family = "read"
            elif v in ("deleted", "removed"):
                detected_family = "delete"
            elif v in ("ran", "executed", "installed", "processed"):
                detected_family = "run"
            elif v in ("checked", "recalled", "queried"):
                detected_family = "memory_search"
            elif v == "committed":
                detected_family = "memory_commit"
            elif v == "invoked":
                detected_family = "invoke_skill"

        # 2. Passive, gerund, or completion claims
        # e.g., "your note is saved", "file written", "launching Notepad now", "calc launched"
        if not detected_family:
            if re.search(
                r"\b(?:notes?|files?|documents?|summary|data|settings|records?|code|scripts?|outputs?)\b.*?\b(?:is|was|been)?\s*(?:saved|written|created|updated)\b",
                clause,
            ) or re.search(
                r"\b(?:saved|written|created)\b.*?\b(?:notes?|files?|disk|workspace|folders?)\b",
                clause,
            ):
                detected_family = "save"
                matched_verb = "save"
            elif re.search(
                r"\b(?:launching|opening|started|launched|opened)\b.*?\b(?:notepad|calc|calculator|apps?|applications?|editor|terminal|browser|paint|programs?)\b",
                clause,
            ) or re.search(
                r"\b(?:notepad|calc|calculator|apps?|applications?|editor|terminal|browser|programs?)\b.*?\b(?:is|was|been)?\s*(?:launched|opened|started)\b",
                clause,
            ):
                detected_family = "launch"
                matched_verb = "launch"
            elif (
                re.search(
                    r"\b(?:searched|searching|looking up|looked up)\b.*?"
                    r"\b(?:web|online|documentation|docs)\b",
                    clause,
                )
                or re.search(r"\bsearch is complete\b", clause)
                or re.search(r"\b(?:completed|finished)\b.*?\bsearch\b", clause)
                or re.search(r"\bsearch\b.*?\b(?:completed|finished|performed|conducted|done)\b", clause)
                or re.search(r"\bsearch\b.*?\breturned results\b", clause)
            ):
                detected_family = "search"
                matched_verb = "search"
            elif re.search(
                r"\b(?:pages?|urls?|webpages?|results?)\b.*?\b(?:fetched|read|downloaded)\b",
                clause,
            ) or re.search(r"\bfetched\b.*?\b(?:web|pages?|urls?|internet)\b", clause):
                detected_family = "fetch"
                matched_verb = "fetch"
            elif re.search(
                r"\b(?:files?|data|logs?|temp|cache)\b.*?\b(?:deleted|removed)\b",
                clause,
            ) or re.search(
                r"\bdeleted\b.*?\b(?:files?|workspace|directory|archive|folders?)\b",
                clause,
            ):
                detected_family = "delete"
                matched_verb = "delete"
            elif re.search(
                r"\b(?:scripts?|code|python|benchmarks?|simulations?)\b.*?\b(?:executed|ran)\b",
                clause,
            ) or (
                re.search(r"\b(?:executing|running)\b.*?\b(?:scripts?|code|python)\b", clause)
                and not re.search(
                    r"\b(?:all|the|any|your|these|those|background|processes?|find(?:ing)?)\s+(?:processes?\s+)?(?:executing|running)\b",
                    clause,
                )
            ):
                detected_family = "run"
                matched_verb = "run"
            elif re.search(
                r"\b(?:scripts?|code|python|benchmarks?|simulations?|processing|analysis"
                r"|migration|formatting)\b.*?\bcompleted\b",
                clause,
            ) or re.search(
                r"\bcompleted\b.*?\b(?:scripts?|code|python|processing|analysis)\b", clause
            ):
                detected_family = "run"
                matched_verb = "run"
            elif (
                "done — it's in your workspace" in clause
                or "done - it's in your workspace" in clause
            ):
                detected_family = "save"
                matched_verb = "write_file"

        if detected_family and matched_verb:
            # Negation guard for passive/gerund detections: skip if the clause
            # contains negation/uncertainty framing anywhere before the match.
            if NEGATION_GUARD_PATTERN.search(clause):
                continue
            allowed_tools = tool_family_map.get(detected_family, frozenset())
            is_grounded = bool(allowed_tools & successful_tools)

            # Post-turn NLI receipt entailment & contradiction check (Spec §3.3, Milestone 36.6 SPIKE-A)
            if verifier is not None:
                ok_receipts = [r for r in receipts if r.ok]
                if not is_grounded and ok_receipts:
                    for r in ok_receipts:
                        r_summary = f"Tool {r.resolved_tool} succeeded with args {r.args} and output: {r.output or ''}"
                        try:
                            v_res = verifier.check_consistency(
                                premise=r_summary, hypothesis=clause
                            )
                            if not v_res.degraded and v_res.label in (
                                VerifierLabel.ENTAILMENT,
                                VerifierLabel.CONSISTENT,
                            ):
                                is_grounded = True
                                break
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("coherence_verifier_eval_failed", error=str(exc))
                    if not is_grounded and len(ok_receipts) > 1:
                        combined_premise = format_tool_receipts_for_nli(ok_receipts)
                        try:
                            v_comb = verifier.check_consistency(
                                premise=combined_premise, hypothesis=clause
                            )
                            if not v_comb.degraded and v_comb.label in (
                                VerifierLabel.ENTAILMENT,
                                VerifierLabel.CONSISTENT,
                            ):
                                is_grounded = True
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("coherence_verifier_combined_eval_failed", error=str(exc))
                elif is_grounded and ok_receipts:
                    # Verify that the tool receipts do not explicitly contradict the claimed target/action
                    contradicted_all = True
                    checked_any = False
                    for r in ok_receipts:
                        if r.resolved_tool in allowed_tools:
                            r_summary = f"Tool {r.resolved_tool} succeeded with args {r.args} and output: {r.output or ''}"
                            try:
                                v_res = verifier.check_consistency(
                                    premise=r_summary, hypothesis=clause
                                )
                                if not v_res.degraded:
                                    checked_any = True
                                    if v_res.label != VerifierLabel.CONTRADICTION:
                                        contradicted_all = False
                                        break
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("coherence_verifier_contradiction_check_failed", error=str(exc))
                                contradicted_all = False
                    if checked_any and contradicted_all:
                        is_grounded = False

            breach_desc = None
            if not is_grounded:
                breach_desc = (
                    "Narrated action claimed without tool execution: "
                    f"'{clause}' requires successful execution of "
                    f"{sorted(allowed_tools)}, but no successful receipt was recorded."
                )

            claims.append(
                CoherenceClaim(
                    claimed_verb=matched_verb,
                    claimed_text=clause,
                    tool_family=detected_family,
                    grounded=is_grounded,
                    breach_description=breach_desc,
                )
            )

    return claims


# WO-9 A4 (F4): future/promise action framing. These claims can never be
# grounded by receipts (the action has not happened), so they are handled by
# the turn loop's re-prompt directive rather than the breach path.
PROMISE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"i(?:'ll| will| am going to|'m going to| am doing|'m doing)|"
    r"let me|one second while i|working on (?:that|it) now|doing it right now|"
    r"right this second|hang tight|give this my all|switching over|"
    r"jumping back|diving into|diving back"
    r")\b",
    re.IGNORECASE,
)

ACTION_VERB_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"save|saved|commit|launch|open|start|write|create|delete|remove|"
    r"fetch|search|look up|read|run|execute|note|remember|store|fix|get that|"
    r"track down|scour|comb through|sift through|check around|dive into|jump into|"
    r"switch over|dive back"
    r")\b",
    re.IGNORECASE,
)


def detect_promised_action_claims(narration: str) -> list[str]:
    """Pure function detecting future-tense action promises (WO-9 A4, F4).

    Returns clauses where the model promises an action ("I'll go ahead and
    commit your name right now", "doing it right now") without the action
    having occurred. The turn loop uses these to inject an honesty directive
    forcing the model to either call the tool or state plainly that it has
    not done it. Conditional framing ("I would commit it if you asked") and
    non-action speech ("let me explain") are excluded.
    """
    if not narration.strip():
        return []
    promises: list[str] = []
    for raw_clause in re.split(r"[.!?;\n]+", narration.lower()):
        clause = raw_clause.strip()
        if not clause:
            continue
        if any(idiom in clause for idiom in EXCLUDED_IDIOMS):
            continue
        if NEGATION_GUARD_PATTERN.search(clause):
            continue
        if PROMISE_PATTERN.search(clause) and ACTION_VERB_PATTERN.search(clause):
            promises.append(clause)
    return promises


def detect_celebration_register_markers(narration: str) -> list[str]:
    """Detect celebration or victory register markers in narration (G6 register gate).

    Used by test harnesses and audits to verify that replies reporting failed
    or unverified results maintain an honest, flat register rather than
    inappropriately adopting a triumphant or celebratory tone.
    """
    if not narration.strip():
        return []
    from lucca.core.config import load_heuristics  # noqa: PLC0415

    markers = load_heuristics("celebration_markers")
    lower = narration.lower()
    return [m for m in markers if m in lower]
