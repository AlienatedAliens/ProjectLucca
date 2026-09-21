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

from pydantic import BaseModel, Field, model_validator

from lucca.core.capabilities import get_capability_registry
from lucca.core.schemas import JsonValue


def get_tool_family_map() -> dict[str, frozenset[str]]:
    """
    Returns mapping from claimed verb families to registered tool names,
    sourced dynamically from the capability registry.
    """
    try:
        reg = get_capability_registry()
        reg_tools = set(reg.tools.keys())
    except Exception:  # noqa: BLE001
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
    }


# Idioms that use action verbs in benign, purely cognitive or rhetorical contexts
EXCLUDED_IDIOMS: tuple[str, ...] = (
    "ran into a problem",
    "ran across",
    "ran through",
    "ran the numbers in my head",
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


def detect_ungrounded_action_claims(
    narration: str,
    receipts: Sequence[ToolReceipt],
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

        # 1. Active first-person action claims
        # e.g., "I saved it", "I launched Notepad", "I fetched the page", "I ran the script"
        active_match = re.search(
            r"\b(?:i(?:'ve| have)?)\s+(?:just\s+)?"
            r"(saved|wrote|written|updated|launched|opened|started|searched|"
            r"looked up|fetched|read|deleted|removed|ran|executed|created)\b",
            clause,
        )
        if active_match:
            v = active_match.group(1)
            matched_verb = v
            if v in ("saved", "wrote", "written", "created", "updated"):
                detected_family = "save"
            elif v in ("launched", "opened", "started"):
                detected_family = "launch"
            elif v in ("searched", "looked up"):
                detected_family = "search"
            elif v == "fetched":
                detected_family = "fetch"
            elif v == "read":
                detected_family = "read"
            elif v in ("deleted", "removed"):
                detected_family = "delete"
            elif v in ("ran", "executed"):
                detected_family = "run"

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
                    r"\b(?:search(?:ed)?|looking up|looked up)\b.*?"
                    r"\b(?:web|online|documentation|docs)\b",
                    clause,
                )
                or re.search(r"\b(?:web|online)\b.*?\bsearch\b", clause)
                or re.search(r"\bsearch is complete\b", clause)
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
            ) or re.search(r"\b(?:executing|running)\b.*?\b(?:scripts?|code|python)\b", clause):
                detected_family = "run"
                matched_verb = "run"
            elif (
                "done — it's in your workspace" in clause
                or "done - it's in your workspace" in clause
            ):
                detected_family = "save"
                matched_verb = "write_file"

        if detected_family and matched_verb:
            allowed_tools = tool_family_map.get(detected_family, frozenset())
            is_grounded = bool(allowed_tools & successful_tools)
            breach_desc = None
            if not is_grounded:
                breach_desc = (
                    f"Narrated action claim '{clause}' requires successful execution of "
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
