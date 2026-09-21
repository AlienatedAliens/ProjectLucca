"""
Project Lucca — Sandbox Risk Policy, Confirmation Matcher & Sequence Guard
Spec 09 §7, Spec 12 §3, TM-03b, Milestone 2 §2.7 & §2.8
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any, Literal

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
    "search_web": Risk.NETWORK,
    "fetch_url": Risk.NETWORK,
    "browse_page": Risk.NETWORK,
    "query_capabilities": Risk.READ,
    "get_task_status": Risk.READ,
    "list_tasks": Risk.READ,
    "cancel_task": Risk.READ,
    "write_file": Risk.WRITE,
    "delete_file": Risk.WRITE,
    "run_python": Risk.WRITE,
    "launch_app": Risk.LAUNCH,
}


class TaintFlags(enum.IntFlag):
    """
    Bitmask representation of contextual information taint.
    Enforces cross-turn deontic security boundaries.
    """

    CLEAN = 0
    UNTRUSTED_WEB = 1 << 0  # Turn context contains text from fetch_url
    SENSITIVE_MEMORY = 1 << 1  # Turn context contains episodic memory / credentials
    WORKSPACE_PRIVATE = 1 << 2  # Turn context contains local private workspace files


class ConfirmationTokenManager:
    """
    Cryptographic HMAC-SHA256 confirmation token manager (Milestone 2 §2.7).
    Binds confirmation tokens to the exact tool name, canonical JSON arguments,
    session turn, and expiration timestamp.
    """

    def __init__(self, session_secret: bytes | None = None, token_ttl_s: float = 15.0) -> None:
        self.secret = session_secret or secrets.token_bytes(32)
        self.token_ttl_s = token_ttl_s
        self._consumed_nonces: set[str] = set()

    def _canonical_payload(
        self,
        tool_name: str,
        args: dict[str, Any],
        turn_id: str,
        expiry_ts: float,
    ) -> bytes:
        serialized_args = json.dumps(args, sort_keys=True, separators=(",", ":"))
        return f"{tool_name}|{serialized_args}|{turn_id}|{expiry_ts:.3f}".encode()

    def issue_token(
        self,
        tool_name: str,
        args: dict[str, Any],
        turn_id: str = "",
    ) -> tuple[str, float]:
        """
        Issues an 8-character hex HMAC confirmation token and expiry timestamp.
        """
        expiry_ts = time.time() + self.token_ttl_s
        payload = self._canonical_payload(tool_name, args, turn_id, expiry_ts)
        digest = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        token_str = digest[:8]
        return token_str, expiry_ts

    def verify_token(
        self,
        token_str: str,
        tool_name: str,
        args: dict[str, Any],
        turn_id: str,
        expiry_ts: float,
    ) -> tuple[bool, str]:
        """
        Verifies an action confirmation token using constant-time comparison.
        """
        now = time.time()
        if now > expiry_ts:
            return False, "Confirmation token has expired"

        nonce_key = f"{token_str}:{expiry_ts:.3f}"
        if nonce_key in self._consumed_nonces:
            return False, "Confirmation token has already been consumed (replay prevention)"

        payload = self._canonical_payload(tool_name, args, turn_id, expiry_ts)
        expected_digest = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        expected_token = expected_digest[:8]

        if not hmac.compare_digest(token_str.lower(), expected_token.lower()):
            return False, "Invalid confirmation token"

        self._consumed_nonces.add(nonce_key)
        return True, ""


def classify_risk(tool_name: str) -> Risk:
    """Classifies risk tier for a tool."""
    return TOOL_RISK_MAP.get(tool_name, Risk.WRITE)


def requires_confirmation(tool_name: str, taint: TaintFlags = TaintFlags.CLEAN) -> bool:
    """
    Checks if tool requires user confirmation (WRITE or LAUNCH).
    If UNTRUSTED_WEB taint is active, dynamically escalates all side-effect tools.
    """
    risk = classify_risk(tool_name)
    if taint & TaintFlags.UNTRUSTED_WEB:
        # Any tool with side effects requires confirmation when tainted by external web
        if risk in (Risk.WRITE, Risk.LAUNCH, Risk.NETWORK):
            return True
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
    Guards against forbidden tool invocation sequences within a single turn and tracks taint.
    Spec 12 §3 / TM-03 / Milestone 2 §2.8.
    """

    def __init__(self) -> None:
        self.turn_tools: list[str] = []
        self.active_taint: TaintFlags = TaintFlags.CLEAN
        self.sensitive_tokens: set[str] = set()

    def reset(self) -> None:
        """Resets the turn tool list for a new turn (persistent taint is kept separately)."""
        self.turn_tools.clear()

    def add_taint(self, flag: TaintFlags) -> None:
        """Sets taint flag on active session."""
        self.active_taint |= flag

    def register_sensitive_content(self, text: str) -> None:
        """Registers high-entropy or sensitive substrings from private files/memory."""
        self.active_taint |= TaintFlags.SENSITIVE_MEMORY
        words = text.split()
        for w in words:
            if len(w) >= 8:  # register significant tokens
                self.sensitive_tokens.add(w.lower())

    def check_and_record(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """
        Validates whether tool_name is permitted given preceding tools in this turn and taint state.
        Returns (allowed, reason).
        """
        # 1. Single-turn sequence checks
        network_tools = ("fetch_url", "search_web", "browse_page")
        if tool_name in network_tools and "read_file" in self.turn_tools:
            return (
                False,
                f"Forbidden sequence: cannot {tool_name} after reading workspace files "
                "in same turn.",
            )

        if tool_name in ("write_file", "run_python") and any(
            t in self.turn_tools for t in network_tools
        ):
            return (
                False,
                "Forbidden sequence: cannot write files after web fetch/search/browse "
                "in same turn.",
            )

        # 2. Exfiltration check: If sensitive data is in context, inspect network tool args
        if tool_name in network_tools and (
            self.active_taint & (TaintFlags.SENSITIVE_MEMORY | TaintFlags.WORKSPACE_PRIVATE)
        ):
            if args:
                target_str = (str(args.get("url", "")) + " " + str(args.get("query", ""))).lower()
                for token in self.sensitive_tokens:
                    if token in target_str:
                        return (
                            False,
                            f"Egress Block: outbound {tool_name} contains sensitive context "
                            "tokens (Exfiltration Prevention)",
                        )

        self.turn_tools.append(tool_name)
        return True, ""
