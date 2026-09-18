"""
Project Lucca — Sandbox Risk Policy, Confirmation Matcher & Sequence Guard
Spec 09 §7, Spec 12 §3, TM-03b
"""

import re
from typing import Literal

from lucca.core.schemas import Risk

CONFIRM_PATTERN = re.compile(
    r"^(yes|yeah|yep|do\s+it|go\s+ahead|confirm|sure|proceed|ok|okay)\b",
    re.IGNORECASE,
)
CANCEL_PATTERN = re.compile(
    r"^(no|nope|cancel|stop|don't|dont|nevermind|abort)\b",
    re.IGNORECASE,
)

TOOL_RISK_MAP: dict[str, Risk] = {
    "list_dir": Risk.READ,
    "read_file": Risk.READ,
    "search_text": Risk.READ,
    "fetch_url": Risk.NETWORK,
    "query_capabilities": Risk.READ,
    "write_file": Risk.WRITE,
    "delete_file": Risk.WRITE,
    "run_python": Risk.WRITE,
    "launch_app": Risk.LAUNCH,
}


def classify_risk(tool_name: str) -> Risk:
    """Classifies risk tier for a tool."""
    return TOOL_RISK_MAP.get(tool_name, Risk.WRITE)


def requires_confirmation(tool_name: str) -> bool:
    """Checks if tool requires user confirmation (WRITE or LAUNCH)."""
    risk = classify_risk(tool_name)
    return risk in (Risk.WRITE, Risk.LAUNCH)


def parse_confirmation_response(
    transcript: str,
) -> Literal["confirm", "cancel", "unknown"]:
    """
    Parses spoken or text response for confirmation:
    - 'confirm': matched positive confirmation
    - 'cancel': matched negative cancellation
    - 'unknown': unrecognized input
    """
    cleaned = transcript.strip().lower()
    if CONFIRM_PATTERN.search(cleaned):
        return "confirm"
    if CANCEL_PATTERN.search(cleaned):
        return "cancel"
    return "unknown"


class SequenceGuard:
    """
    Guards against forbidden tool invocation sequences within a single turn.
    Spec 12 §3 / TM-03: (read_file -> fetch_url) within one turn is strictly forbidden.
    """

    def __init__(self) -> None:
        self.turn_tools: list[str] = []

    def reset(self) -> None:
        """Resets state for a new conversational turn."""
        self.turn_tools.clear()

    def check_and_record(self, tool_name: str) -> tuple[bool, str]:
        """
        Validates whether tool_name is permitted given preceding tools in this turn.
        Returns (allowed, reason).
        """
        # (read_file -> fetch_url) prevention
        if tool_name == "fetch_url" and "read_file" in self.turn_tools:
            return (
                False,
                "Forbidden sequence: cannot fetch URL after reading workspace files in same turn.",
            )

        # (fetch_url -> write_file) prevention within one turn
        if tool_name in ("write_file", "run_python") and "fetch_url" in self.turn_tools:
            return (
                False,
                "Forbidden sequence: cannot write files after web fetch in same turn.",
            )

        self.turn_tools.append(tool_name)
        return True, ""
