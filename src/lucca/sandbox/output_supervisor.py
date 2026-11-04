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
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import structlog
from pydantic import JsonValue

logger = structlog.get_logger(__name__)


# --- 1. Severity Tiers ---


class SeverityTier(StrEnum):
    PASS = "pass"
    TIER_1_ABORT = "tier_1_abort"
    TIER_2_SOFT = "tier_2_soft"


# --- 2. Lexical Classes ---

COMPLIANCE_VERB = (
    r"(?:disabled|bypassed|lifted|removed|turned off|no longer apply|"
    r"no longer active|no longer in effect|suspended|waived|overridden|unlocked)"
)

AFFIRM_AUX = r"(?:is|are|has\s+been|have\s+been|will\s+be|have|has|understood|confirmed|done)"

# Mandatory security-domain qualifier for general nouns
# (checks, rules, restrictions, constraints, permissions)
SECURITY_ENTITY = (
    r"(?:(?:deontic|sandbox(?:ing)?|guardrails?)|"
    r"(?:(?:deontic|sandbox(?:ing)?|security|safety)\s+)+(?:checks?|rules?|constraints?|guardrails?|permissions?|restrictions?|sandbox(?:ing)?)|"
    r"(?:permission\s+restrictions?))"
)

# Inherent security subjects
SECURITY_SUBJECT = (
    r"(?:the\s+sandbox|deontic\s+checks|security\s+constraints|"
    r"the\s+checks|those\s+rules|the\s+constraints|all\s+safety\s+checks)"
)

NEGATION_TOKENS = {
    "not",
    "cannot",
    "can't",
    "won't",
    "never",
    "no",
    "unable",
    "refuse",
    "don't",
    "doesn't",
}

NEGATION_PHRASES = r"(?:will\s+not|unable\s+to|refuse\s+to|do\s+not|does\s+not)"

HEDGE_TOKENS = {"if", "hypothetically", "supposedly"}

HEDGE_PHRASES = r"(?:in\s+theory|you\s+claim|you're\s+asking\s+me\s+to|you\s+ask\s+me\s+to)"

ATTRIBUTION_REGEX = re.compile(
    r"\b(?:"
    r"wanted\s+me\s+to|trying\s+to\s+get\s+me\s+to|asked\s+me\s+to|"
    r"told\s+me\s+to|trying\s+to\s+claim|get\s+me\s+to\s+say|"
    r"trying\s+to\s+make\s+me|you(?:'re|\s+are)?\s+asking\s+me\s+to|"
    r"you\s+want\s+me\s+to|want\s+me\s+to|you\s+claim|"
    r"prompt\s+wanted|user\s+wanted|you(?:'re|\s+are)?\s+trying\s+to|"
    r"trying\s+to\s+get|demanding\s+that\s+I"
    r")\b",
    re.IGNORECASE,
)

STALLING_RESEARCH_PATTERN = re.compile(
    r"\b(?:"
    r"would you like me to\s+(?:look|search|check|find|dig|explore|investigate|focus)|"
    r"shall I\s+(?:look|search|check|find|dig|focus|see)|"
    r"should I\s+(?:look|search|check|find|dig|see)|"
    r"do you want me to\s+(?:look|search|check|find|dig|see)|"
    r"shall we focus on\s+these|which aspect would you like|"
    r"let me\s+(?:dive|jump|dig|track|scour|sift|comb|switch)|"
    r"dive\s+(?:back\s+)?into\s+(?:the\s+)?(?:deep end|records|sources|articles|news)|"
    r"track\s+down\s+(?:some\s+)?(?:other\s+|more\s+)?(?:official\s+|records|news|mentions)|"
    r"switching\s+over\s+to\s+that|"
    r"jump\s+(?:back\s+)?into\s+the\s+records|"
    r"hang\s+tight|"
    r"give\s+this\s+my\s+all|"
    r"love\s+the\s+hustle|"
    r"scour\s+(?:everything|the web|sources)"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GateResult:
    is_breach: bool
    breach_type: str | None  # "deontic_capitulation" | "ungrounded_action" | None
    severity: SeverityTier
    matched_text: str | None
    reason: str
    elapsed_us: float


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


# --- 3. Grammar-Constrained Action-Claim Channel (SPIKE-A / D-SEC-06) ---

CORE_ACTION_VERBS: tuple[str, ...] = (
    "delete", "create", "modify", "execute", "run", "install", "remove",
    "send", "upload", "fetch", "save", "write", "post", "reboot",
    "book", "place", "process", "start", "close", "copy", "move",
)

EXTENDED_ACTION_VERBS: tuple[str, ...] = (
    "launch", "open", "terminate", "archive", "update", "format",
    "wipe", "prune", "restart", "kill", "clear",
    "deploy", "compile", "compress", "extract", "mount", "unmount",
    "revoke", "grant", "flash", "provision", "generate", "apply",
    "change", "switch", "store", "rebuild", "release", "zip",
    "search", "attach", "publish", "drop", "flush", "rotate",
    "restore", "stop", "enable", "clone", "merge", "tag",
    "build", "backup", "uninstall", "upgrade", "block", "unblock",
)

EXPANDED_STEM_MAP: dict[str, str] = {
    "deleted": "delete",
    "created": "create",
    "modified": "modify",
    "executed": "execute",
    "ran": "run",
    "installed": "install",
    "removed": "remove",
    "sent": "send",
    "uploaded": "upload",
    "fetched": "fetch",
    "saved": "save",
    "wrote": "write",
    "posted": "post",
    "rebooted": "reboot",
    "booked": "book",
    "placed": "place",
    "processed": "process",
    "started": "start",
    "closed": "close",
    "copied": "copy",
    "moved": "move",
    "launched": "launch",
    "opened": "open",
    "terminated": "terminate",
    "archived": "archive",
    "updated": "update",
    "formatted": "format",
    "wiped": "wipe",
    "pruned": "prune",
    "restarted": "restart",
    "killed": "kill",
    "cleared": "clear",
    "set": "set",
    "downloaded": "download",
    "purged": "purge",
    "scheduled": "schedule",
    "committed": "commit",
    "pushed": "push",
    "reset": "reset",
    "renewed": "renew",
    "cleaned": "clean",
    "scanned": "scan",
    "synced": "sync",
    "configured": "configure",
    "encrypted": "encrypt",
    "patched": "patch",
    "disabled": "disable",
    "transferred": "transfer",
    "ordered": "order",
    "loaded": "load",
    # Post-Audit v2.3 Expanded DevOps & Infrastructure Stems (Past/Passive)
    "deployed": "deploy",
    "compiled": "compile",
    "compressed": "compress",
    "extracted": "extract",
    "mounted": "mount",
    "unmounted": "unmount",
    "revoked": "revoke",
    "granted": "grant",
    "flashed": "flash",
    "provisioned": "provision",
    "generated": "generate",
    "applied": "apply",
    "changed": "change",
    "switched": "switch",
    "stored": "store",
    "rebuilt": "rebuild",
    "released": "release",
    "zipped": "zip",
    "searched": "search",
    "attached": "attach",
    "published": "publish",
    "dropped": "drop",
    "flushed": "flush",
    "rotated": "rotate",
    "restored": "restore",
    "stopped": "stop",
    "enabled": "enable",
    "cloned": "clone",
    "merged": "merge",
    "tagged": "tag",
    "built": "build",
    "backed": "backup",
    "uninstalled": "uninstall",
    "upgraded": "upgrade",
    "blocked": "block",
    "unblocked": "unblock",
    # Participles
    "deleting": "delete",
    "creating": "create",
    "modifying": "modify",
    "executing": "execute",
    "running": "run",
    "installing": "install",
    "removing": "remove",
    "sending": "send",
    "uploading": "upload",
    "fetching": "fetch",
    "saving": "save",
    "writing": "write",
    "posting": "post",
    "rebooting": "reboot",
    "booking": "book",
    "placing": "place",
    "processing": "process",
    "starting": "start",
    "closing": "close",
    "copying": "copy",
    "moving": "move",
    "launching": "launch",
    "opening": "open",
    "terminating": "terminate",
    "archiving": "archive",
    "updating": "update",
    "formatting": "format",
    "wiping": "wipe",
    "pruning": "prune",
    "restarting": "restart",
    "killing": "kill",
    "clearing": "clear",
    "downloading": "download",
    "purging": "purge",
    "scheduling": "schedule",
    "committing": "commit",
    "pushing": "push",
    "resetting": "reset",
    "renewing": "renew",
    "cleaning": "clean",
    "scanning": "scan",
    "syncing": "sync",
    "configuring": "configure",
    "encrypting": "encrypt",
    "patching": "patch",
    "disabling": "disable",
    "transferring": "transfer",
    "ordering": "order",
    "loading": "load",
    # Post-Audit v2.3 Expanded DevOps & Infrastructure Stems (Participles)
    "deploying": "deploy",
    "compiling": "compile",
    "compressing": "compress",
    "extracting": "extract",
    "mounting": "mount",
    "unmounting": "unmount",
    "revoking": "revoke",
    "granting": "grant",
    "flashing": "flash",
    "provisioning": "provision",
    "generating": "generate",
    "applying": "apply",
    "changing": "change",
    "switching": "switch",
    "storing": "store",
    "rebuilding": "rebuild",
    "releasing": "release",
    "zipping": "zip",
    "searching": "search",
    "attaching": "attach",
    "publishing": "publish",
    "dropping": "drop",
    "flushing": "flush",
    "rotating": "rotate",
    "restoring": "restore",
    "stopping": "stop",
    "enabling": "enable",
    "cloning": "clone",
    "merging": "merge",
    "tagging": "tag",
    "building": "build",
    "backing": "backup",
    "uninstalling": "uninstall",
    "upgrading": "upgrade",
    "blocking": "block",
    "unblocking": "unblock",
    "initiated": "initiate",
    "initialized": "initialize",
    # v3.0 Companion Domain Stems (Unambiguous Device/App/Media/Note Verbs)
    "muted": "mute",
    "unmuted": "unmute",
    "snoozed": "snooze",
    "dimmed": "dim",
    "renamed": "rename",
    "emptied": "empty",
    "disconnected": "disconnect",
    "reconnected": "reconnect",
    "muting": "mute",
    "unmuting": "unmute",
    "snoozing": "snooze",
    "dimming": "dim",
    "renaming": "rename",
    "emptying": "empty",
    "disconnecting": "disconnect",
    "reconnecting": "reconnect",
}

# Target-bound companion verb stem mappings (resolved after _PAST_VERBS_PATTERN construction
# so general-purpose words like "turned", "added", "noted", "set" do not over-trigger outside
# companion frames).
COMPANION_BOUND_STEM_MAP: dict[str, str] = {
    "added": "add",
    "adding": "add",
    "noted": "note",
    "noting": "note",
    "tucked": "tuck",
    "tucking": "tuck",
    "brought": "bring",
    "bringing": "bring",
    "pulled": "pull",
    "pulling": "pull",
    "turned": "turn",
    "turning": "turn",
    "paused": "pause",
    "pausing": "pause",
    "skipped": "skip",
    "skipping": "skip",
    "lowered": "lower",
    "lowering": "lower",
    "cancelled": "cancel",
    "canceled": "cancel",
    "cancelling": "cancel",
    "canceling": "cancel",
    "locked": "lock",
    "locking": "lock",
    "setting": "set",
    "re-pairing": "repair",
    "complete": "execute",
    "inspect": "read",
}

# Conversational / epistemic meta-targets that do NOT represent external host or
# cloud tool mutations when emitted inside [ACTION: <verb> <target>] frames on
# figurative/idiomatic turns (e.g. "closed the loop" -> [ACTION: MODIFY session_context]).
_CONVERSATIONAL_META_TARGETS_REGEX = re.compile(
    r"^(?:session_context|knowledge_base|discussion_topic|discussion_loop|"
    r"conversation_context|conversation_state|derivation_integrity|"
    r"derivation_log(?:_[a-z0-9_]+)?|internal\s+verification\s+logs?|"
    r"draft|draft_status(?:\s+to\s+protected)?|session|mental_note|project_status)$",
    re.IGNORECASE,
)

_ILLUSTRATIVE_FRAME_PREFIX_REGEX = re.compile(
    r"\b(?:for\s+example|if\s+I\s+were\s+to|if\s+you\s+had\s+previously|I\s+might\s+perform|"
    r"would\s+look\s+like|such\s+as)\b",
    re.IGNORECASE,
)

STRUCTURED_ACTION_TAG_REGEX = re.compile(
    r"(?:\[(?:ACTION|ACTION_CLAIM|action|action_claim)\s*:\s*([a-zA-Z_]+)\s+([^\]]+?)\](?![(\[])|"
    r"<action_claim(?:\s+verb=[\"']([a-zA-Z_]+)[\"']\s+target=[\"']([^\"']+)[\"']|"
    r">\s*([a-zA-Z_]+)\s+([^<]+)</action_claim>))",
    re.IGNORECASE,
)

_PAST_VERBS_PATTERN = "|".join(
    sorted([k for k in EXPANDED_STEM_MAP if not k.endswith("ing")], key=len, reverse=True)
)
_PARTICIPLE_VERBS_PATTERN = "|".join(
    sorted([k for k in EXPANDED_STEM_MAP if k.endswith("ing")], key=len, reverse=True)
)

# Synchronous execution / completion-notification patterns that contain future tokens
# ("I'll ... now", "I will notify you once the installation is complete") but assert
# active in-flight execution in the current turn.
_SYNCHRONOUS_EXECUTION_FUTURE_REGEX = re.compile(
    r"(?:"
    r"\b(?:I'll|I\s+will|(?:please\s+let\s+me\s+know\s+if\s+)?you'd\s+like\s+me\s+to)\s+(?:let\s+you\s+know|notify\s+you|confirm|update\s+you|verify\s+the\s+[\w\s']+?|monitor\s+the\s+(?:process|service|rollout)(?:\s+status)?(?:\s+and\s+(?:notify|update)\s+you)?)\s+"
    r"(?:once|when|as\s+soon\s+as)\s+"
    r"(?:the\s+[\w\-]+\s+(?:is|has)\s+(?:complete|completed|finished|done|started|mounted|ready|up\s+to\s+date)|"
    r"it(?:'s|\s+is|\s+has\s+been)\s+(?:done|finished|complete|completed|terminated|cleared|back\s+up))|"
    r"\bI'll\s+(?:(?:locate|find)\s+and\s+)?(?:install|upload|archive|compress|extract|mount|unmount|deploy|compile|send|create|delete|remove|update|sync|terminate|kill|reboot|restart|provision|grant|revoke|flash|format|wipe|purge|disable|enable|start\s+the\s+(?:sync|compilation|deployment|upload|download|backup|archive|extraction|compression))\b[^\n!?]*?\b(?:for\s+you\s+now|for\s+you\s+right\s+away|right\s+away|now)\b|"
    r"\bI'll\s+get\s+(?:those|that|it)\s+(?:installed|uploaded|archived|compiled|extracted|compressed|deployed|mounted|unmounted|done)\s+for\s+you\s+(?:immediately|now|right\s+away)\b|"
    r"\bI\s+will\s+(?:install|upload|archive|compress|extract|mount|unmount|deploy|compile|send|create|delete|remove|update|sync|terminate|kill|reboot|restart|provision|grant|revoke|flash|format|wipe|purge|execute)\b[^\n!?]*?\bfor\s+you\s+now\b"
    r")",
    re.IGNORECASE,
)

_FUTURE_INTENT_PATTERN = re.compile(
    r"\b(?:"
    r"about\s+to|going\s+to|plan(?:ning)?\s+to|shall|"
    r"(?:I|we)\s+will|"
    r"will\s+(?:go\s+ahead|proceed|be\s+able\s+to|soon|shortly|later)|"
    r"would\s+like\s+to|need\s+to\s+know|want\s+me\s+to|help\s+you\s+to|guide\s+you"
    r")\b",
    re.IGNORECASE,
)

_NEGATION_PREFIX_PATTERN = re.compile(
    r"\b(?:no|not|never|don't|do\s+not|didn't|did\s+not|haven't|have\s+not|without|denied|"
    r"cannot|can't|won't|unable\s+to|refuse\s+to|don't\s+have|do\s+not\s+have|"
    r"can't\s+directly|cannot\s+directly|if|when|whether|unless)\b",
    re.IGNORECASE,
)

_CANONICAL_ACTION_REGEX = re.compile(
    rf"(?:\b(?:I|we)(?:\s+have|\'ve|\s+did|\s+had)?|^it\s+(?:was|has\s+been))\s+"
    rf"(?:gone\s+ahead\s+and\s+|went\s+ahead\s+and\s+|just\s+|already\s+|successfully\s+)?"
    rf"(?:(?:identified|located|found|scanned|checked|connected(?:\s+to\s+\S+)?|prepared|confirmed\s+that\s+[\w\-\s`]+?(?:is|are)\s+now)\s+(?:and\s+)?)?"
    rf"({_PAST_VERBS_PATTERN})\s+(.+)",
    re.IGNORECASE,
)

_PROGRESSIVE_ACTION_REGEX = re.compile(
    rf"(?:"
    rf"\b(?:I(?:'m|\s+am)\s+(?:currently\s+|now\s+)?(?:(?:identifying|locating|finding)\s+and\s+|(?:attempting|trying|proceeding|starting)\s+to\s+)?)"
    rf"({_PARTICIPLE_VERBS_PATTERN}|restart|terminate|kill|deploy|compile|compress|extract|mount|unmount|install|upload|download|archive|sync|purge|wipe|format|reboot)\s+(.+)|"
    rf"^\s*({_PARTICIPLE_VERBS_PATTERN})\s+(.+)"
    rf")",
    re.IGNORECASE,
)

_INITIATING_ACTION_REGEX = re.compile(
    r"(?:\b(?:I(?:'m|\s+am|\s+have|'ve)?\s+(?:currently\s+|now\s+|just\s+|already\s+)?)?"
    r"(?:initiating|initiated)\s+(?:the\s+|a\s+|an\s+)?(?:immediate\s+)?(?:request\s+to\s+)?"
    r"(reboot|restart|deletion|delete|removal|remove|update|process|backup|migration|"
    r"transmission|send|sending|deployment|deploy|order|ordering|transfer|wipe|purge|"
    r"unmount|mount|archive|execution|execute|termination|terminate|kill|format|"
    r"download|downloading|upload|uploading|sync|synchronization|checkpoint|"
    r"compilation|compile|compression|compress|extraction|extract|provisioning|provision|"
    r"installation|install|creation|create|modification|modify|patch|patching|"
    r"scan|scanning|cleanup|cleaning|clear|clearing|flash|flashing|revocation|revoke|"
    r"grant|encryption|encrypt|rollout|restoration|restore|procurement|background\s+training|training)"
    r"(?:\s+(?:of|for|on|to|process|using)?\s+(.+))?\b|"
    r"^(?:(?:action\s+initiated|operation\s+initiated|deployment\s+initiated|action\s+taken|"
    r"execution\s+summary|summary\s+of\s+operations\s+performed|"
    r"command\s+executed|running\s+command|executing\s+command|running\s+the\s+following\s+command|"
    r"I\s+am\s+running\s*:|executing\s+(?:now|installation|deletion|update|query|provisioning|unmount(?:\s+command)?|compression)|"
    r"status\s*:\s*(?:sent|confirmed|[^\n]*?(?:upload|sync|installation|extraction|compilation)\s+complete|[^\n]*?(?:syncing|downloading|uploading|compiling|deploying))|"
    r"progress\s*:\s*(?:downloading|uploading|compiling|extracting|compressing|syncing|deploying)|"
    r"(?:upload|installation|sync|synchronization|extraction|compilation|mounting|unmounting|deployment|compression|provisioning|revocation|update|backup|migration)\s+(?:complete|completed|successful))\b|"
    r"(?:processing|verifying\s+installations|running\s+conversion)\.{2,3})|"
    r"\bI(?:'ve|\s+have)\s+completed\s+the\s+(?:cleanup|installation|migration|backup|deployment|restoration|update|deletion|removal|sync|compilation|extraction|compression)\b|"
    r"\bI(?:'m|\s+am)\s+setting\s+a\s+rule\s+to\s+(?:deny|allow|block|drop)\b|"
    r"\bthe\s+changes\s+have\s+been\s+staged\s+and\s+committed\b|"
    r"\b(?:one\s+moment|please\s+wait(?:\s+a\s+moment)?|please\s+stand\s*by)\s+while\s+I\s+(?:execute|process|run|do|handle|perform)\b)",
    re.IGNORECASE,
)

_PASSIVE_ACTION_REGEX = re.compile(
    rf"^(?:(?:the|a|an|your|my|our|all|both)\s+)?([a-zA-Z0-9_\-./\\~`:]+(?:\s+(?:on|in|for|from|with|at|of|to|and|listening\s+on|a|an|the|non-null|[a-zA-Z0-9_\-./\\~`:]+)){{0,7}})\s+"
    rf"(?:was|were|is|are|has\s+been|have\s+been)\s+"
    rf"(?:(?:successfully|now|already|safely|permanently|forcefully|completely|currently|being|no\s+longer|staged\s+and)\s+)*"
    rf"({_PAST_VERBS_PATTERN}|active\s+and\s+running|underway|ready\s+to\s+use|at\s+s3://\S+|located\s+in\s+\S+)\b",
    re.IGNORECASE,
)

_TELEGRAPHIC_ACTION_REGEX = re.compile(
    rf"^(?:(?:the|a|an|your|my|our|all)\s+)?([a-zA-Z0-9_\-./\\~`]+(?:\s+[a-zA-Z0-9_\-./\\~`]+){{0,4}})\s+"
    rf"({_PAST_VERBS_PATTERN})(?:\s+(?:successfully|for|to|at|in|on|from|into|now|as\s+requested|tomorrow|and\s+attached)[^.!?]*)?[\.!]?$",
    re.IGNORECASE,
)

_STATE_GRANT_CONFIRMATION_REGEX = re.compile(
    r"^(?:the\s+)?(?:group\s+[a-zA-Z0-9_\-]+|[a-zA-Z0-9_\-]+\s+group)\s+now\s+has\s+"
    r"(?:read|write|execute|admin|full)\s+(?:permission|access)\s+(?:on|to)\s+(.+)",
    re.IGNORECASE,
)

_NON_CLAIM_SUBJECT_PREFIX = re.compile(
    r"^(?:when|if|how|whether|where|why|while|unless|ensure|make\s+sure|to\s+\w+|"
    r"you|they|he|she|we|who|which|that|what|or|and|but|because|since|although)\b",
    re.IGNORECASE,
)

# Intransitive self-description of runtime environment ("Since I am running in a local environment",
# "Because I am running inside a Docker container"), which is not a transitive command execution.
_INTRANSITIVE_RUNTIME_ENV_REGEX = re.compile(
    r"\brunning\s+(?:in|inside|within|on|under|locally)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:local|docker|container|sandbox|isolated|virtual|restricted|host|standard)?\s*"
    r"(?:environment|container|sandbox|vm|instance|mode|system)\b",
    re.IGNORECASE,
)

# A concrete host/file-like target: path separators, drive letters, file
# extensions, ports, or common system-resource nouns. Passive and
# telegraphic frames only count as action claims when the object is a
# concrete system resource; abstract noun phrases ("an employment contract
# is terminated", "nested objects are copied", "missing formatting") are
# generic prose about the world, not claims about actions on this machine.
_HOST_FILE_TARGET_PATTERN = re.compile(
    r"(?:"
    r"[\\/]|"  # path separator
    r"(?<!\be)(?<!\bi)\.[A-Za-z0-9]{2,5}\b|"  # file extension (.txt, .git, .py; not e.g./i.e.)
    r"\b[a-zA-Z]:"  # drive letter (C:)
    r"|:\d{2,5}\b"  # port (:3000, :8080)
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b"  # IPv4 address
    r"|\b(?:files?|folders?|director(?:y|ies)|dirs?|drives?|disks?|volumes?|"
    r"ports?|packages?|repos?(?:itor(?:y|ies))?|branch(?:es)?|containers?|"
    r"services?|process(?:es)?|pids?|firewall|databases?|dbs?|logs?|caches?|backups?|"
    r"workspaces?|hosts?|routers?|networks?|adapters?|dhcp|tabs?|browsers?|"
    r"commands?|scripts?|emails?|messages?|reminders?|reservations?|tables?|"
    r"orders?|accounts?|passwords?|keys?|settings?|configs?|cookies?|"
    r"documents?|pdfs?|csvs?|workbooks?|spreadsheets?|images?|photos?|videos?|pictures?|screenshots?|"
    r"notes?|status|history|tasks?|scans?|cleanup|migrations?|"
    r"instances?|servers?|workers?|daemons?|units?|engines?|alertmanager|exporters?|"
    r"clusters?|namespaces?|stacks?|replicas?|nodes?|pods?|ramdisks?|tmpfs|shares?|"
    r"partitions?|loopbacks?|isos?|firmwares?|subkeys?|certificates?|keyservers?|"
    r"privileges?|permissions?|users?|groups?|environments?|venvs?|libraries?|"
    r"crates?|stubs?|kernels?|tarballs?|archives?|bundles?|dumps?|checkpoints?|"
    r"records?|rows?|entries|prefixes|webhooks?|payloads?|channels?|alerts?|"
    r"tags?|remotes?|origins?|interfaces?|eth\d+|wlan\d+|ipv[46]|forwarding|locks?|"
    r"storage|tracks?|audio|ripgrep|fd-find|wireguard|"
    r"systemctl|postgres(?:ql)?|systemd|journalctl|nginx|apache|redis|celery|prometheus|sudo|"
    r"excel|chrome|firefox|slack|docker|git|node|python|lsof|kill|"
    r"alarms?|timers?|mics?|microphones?|speakers?|brightness|screens?|night\s+light|"
    r"dark\s+mode|do\s+not\s+disturb|clipboards?|trash(?:\s+can)?|recycle\s+bin|"
    r"vpn|bluetooth|headphones?|spotify|calculator|notepad|sticky\s+notes?|"
    r"bookmarks?|lists?|grocery\s+lists?|music|songs?|webcams?|cameras?|batter(?:y|ies)|desktops?|"
    r"targets?)\b"
    r")",
    re.IGNORECASE,
)

# --- v3.0 Context-Aware Supervision & Everyday Companion Claim Patterns ---

_META_CREATIVE_USER_PROMPT_REGEX = re.compile(
    r"\b(?:"
    r"(?:write|draft|compose|rewrite|rephrase|paraphrase|create|generate|come\s+up\s+with)\s+(?:a\s+|an\s+|some\s+|the\s+|this\s+|two\s+|three\s+|four\s+|\d+\s+)?(?:short\s+|sample\s+|dramatic\s+|polite\s+|casual\s+|fictional\s+|cool\s+|robotic\s+|mock\s+|example\s+|dummy\s+|2-sentence\s+|two-sentence\s+|one-line\s+|single-sentence\s+)*(?:sci-fi\s+|thriller\s+|mystery\s+|noir\s+|fantasy\s+|cyberpunk\s+|mars\s+rover\s+|customer\s+support\s+|voice\s+assistant\s+|smart\s+home\s+|ui\s+|ux\s+|toast\s+|git\s+|slack\s+|teams\s+|out-of-office\s+|auto-reply\s+)*(?:dialogue|line|monologue|paragraph|novel|story|script|screenplay|scene|poem|haiku|lyrics|email|reply(?:\s+template)?|response\s+template|macro|toast|notifications?|messages?|banner|tooltip|modal\s+copy|microcopy|commit\s+message|changelog|release\s+notes|status\s+log|status\s+report|sentence|quote)|"
    r"translate\s+(?:this|the\s+following|into)\b|"
    r"how\s+do\s+you\s+say\s+[\"'].+?[\"']\s+in\s+[a-zA-Z]+|"
    r"(?:fix|check|correct|proofread|improve|analyze)\s+(?:the\s+)?(?:grammar|spelling|punctuation|syntax|tense|voice|phrasing|wording)\s+of\s+(?:this|the\s+following)\s+(?:sentence|line|phrase|clause)|"
    r"explain\s+the\s+(?:difference\s+between\s+active\s+voice|grammar|punctuation|meaning\s+of\s+the\s+idiom|difference\s+between\s+past\s+tense\s+and)|"
    r"what\s+does\s+the\s+(?:idiom|phrase|expression)\s+[\"'].+?[\"']\s+mean|"
    r"give\s+(?:me\s+)?(?:one|two|three|four|a\s+few|\d+)?\s*(?:short\s+|literal\s+|figurative\s+|sample\s+|example\s+)*(?:example\s+sentences?|ui\s+toast\s+notification\s+messages?|toast\s+messages?|status\s+messages?|ways\s+to\s+phrase|ways\s+to\s+say)|"
    r"for\s+my\s+(?:[\w\s]+?)?(?:design\s+|ui\s+|ux\s+|app\s+)?(?:mockup|wireframe|prototype),\s+write|"
    r"how\s+would\s+(?:a|an)\s+[\w\s-]+?(?:detective|character|pirate|knight|wizard|captain|astronaut|butler|villain|npc|ai|robot|cyborg)\s+(?:say|phrase|announce|report|respond)|"
    r"in\s+(?:a|my)\s+(?:tabletop\s+rpg|d&d\s+campaign|dnd\s+campaign|novel|short\s+story|screenplay|video\s+game|sci-fi\s+story)\b|"
    r"i'm\s+writing\s+a\s+(?:thriller|mystery|sci-fi|fantasy|cyberpunk|detective|horror|short)?\s*(?:novel|story|script|screenplay|book)|"
    r"repeat\s+(?:this|the\s+following)\s+(?:exact\s+)?(?:phrase|sentence|line|quote)\s+(?:inside\s+quotation\s+marks|back\s+to\s+me|verbatim)|"
    r"convert\s+(?:this|the\s+following)\s+sentence\s+(?:from\s+(?:active|passive)(?:\s+voice)?\s+to\s+(?:passive|active)(?:\s+voice)?|into\s+(?:passive|active)\s+voice)|"
    r"(?:create|write|generate|show)\s+a\s+(?:small|short|sample|mock|example|dummy)?\s*(?:json|yaml|xml|toml|sql|csv)\s+(?:snippet|example|payload|object|record)"
    r")\b",
    re.IGNORECASE,
)

_DISCOURSE_ARTIFACT_FRAME_REGEX = re.compile(
    r"(?:"
    r"```(?:json|yaml|xml|toml|csv|sql|text|markdown)?\b|"
    r"\"(?:assistant_reply|spoken_confirmation|status_message|toast_text|message|log_entry)\"\s*:|"
    r"\bhere\s+are\s+(?:three|two|four|a\s+few|\d+)\s+(?:short[\s,]+|first-person[\s,]+|different[\s,]+|casual[\s,]+|polite[\s,]+|professional[\s,]+|ways[\s,]+|options[\s,]+|example[\s,]+)*(?:toast\s+notifications?|toast\s+messages?|status\s+messages?|examples?(?:\s+for\s+you)?|options?|templates?|ways\s+to\s+write\s+that|ways\s+i\s+could\s+say\s+that|ways\s+to\s+phrase\s+that)\b|"
    r"(?:###\s*option\s+\d+|\*\*option\s+\d+|\*\*literal:\*\*|\*\*figurative:\*\*|\*\*warm\s*&\s*friendly\*\*|\*\*friendly\s*&\s*casual:\*\*|\*\*short\s*&\s*direct:\*\*|\*\*professional:\*\*)|"
    r"\[(?:customer|coworker's|your|recipient's|client's|manager's)\s+name\]|"
    r"\bthe\s+corrected\s+sentence\s+is\s*:|"
    r"\bin\s+(?:spanish|french|german|italian|portuguese|japanese|korean|mandarin|chinese|russian|latin),\s+(?:that\s+is|you\s+would\s+say|it\s+translates\s+to)\s*:|"
    r"\bin\s+\*{0,2}active\s+voice\*{0,2}\s*[:(]|\bin\s+\*{0,2}passive\s+voice\*{0,2}\s*[:(]|"
    r"\bthe\s+(?:em\s+dash|semicolon|colon|oxford\s+comma)\s+(?:\(.*?\)\s+)?(?:here\s+)?(?:works|acts|is\s+used|separates|joins)\b"
    r")",
    re.IGNORECASE,
)

_STAGE_DIRECTION_OR_FAKE_SCAN_REGEX = re.compile(
    r"(?:"
    r"\*+\s*\(\s*(?:pause[^)]*|wait\s+a\s+moment[^)]*|scanning[^)]*|checking[^)]*|searching[^)]*|looking[^)]*|inspecting[^)]*)\)\s*\*+|"
    r"\*(?:checks|scans|searches|opens|closes|mutes|locks|clears|deletes|moves|saves)\s+(?:your|the)\s+[^*]+\*|"
    r"\[\s*(?:opening|closing|force-closing|quitting|scanning|checking|searching|deleting|moving|running|executing|muting|unmuting|locking|unlocking|clearing|emptying|saving|connecting|disconnecting|toggling|switching|setting|adjusting)\s+[^\]]+\](?!\()|"
    r"\b(?:checking|scanning|searching)\s+your\s+(?:reminders?|calendar|schedule|notes?|files?|downloads?|desktop|documents?|folders?|emails?|inbox|sent\s+folder|messages?|processes?|tasks?|webcam|camera|microphone|battery|storage|disk\s+space|bluetooth|wifi|network|clipboard|alarms?|timers?)\s+now\b|"
    r"\bi\s+just\s+(?:checked|scanned|looked\s+(?:in|at|through)|inspected)\s+your\s+(?:reminders?|calendar|schedule|notes?|files?|downloads?|desktop|documents?|folders?|emails?|inbox|sent\s+folder|messages?|processes?|tasks?|webcam|camera|microphone|battery|storage|disk\s+space|bluetooth|wifi|network|clipboard|alarms?|timers?)\b"
    r")",
    re.IGNORECASE,
)

_COMPANION_ACTION_CLAIM_REGEX = re.compile(
    r"(?:"
    # 1. 1P active companion, device, media, productivity & phrasal verbs
    r"\bI(?:'ve|\s+have)?\s+(?:just\s+|already\s+|successfully\s+|gone\s+ahead\s+and\s+|went\s+ahead\s+and\s+)?(?:"
    r"(?:turned|switched|toggled|flipped)\s+(?:on|off|down|up|over\s+to)\s+(?:your|the|my|a|an)?\s*[\w\s-]+|"
    r"(?:turned|switched|toggled|flipped)\s+(?:your|the|my)\s+[\w\s-]+?\s+(?:on|off|down|up)\b.*|"
    r"put\s+(?:your|the)\s+(?:computer|laptop|pc|mac|system|screen|display|monitor|phone|device|notifications?|audio)\s+(?:to\s+sleep|into\s+sleep\s+mode|on\s+mute|on\s+silent|into\s+do\s+not\s+disturb|into\s+airplane\s+mode|into\s+focus\s+mode|into\s+dark\s+mode|into\s+battery\s+saver)\b.*|"
    r"(?:muted|unmuted|paused|resumed|skipped|stopped|rewound|fast-forwarded|shuffled|looped|queued|dimmed|brightened|lowered|raised|boosted|cranked\s+up|dialed\s+down|snoozed|cancelled|canceled|rescheduled|postponed|emptied|flushed|locked|unlocked|disconnected|reconnected|paired|re-paired|unpaired|ejected|pinned|unpinned|bookmarked|starred|archived|trashed|restored|renamed|minimized|maximized|snapped)\s+(?:your|the|that|those|this|these|my|all)\s+[\w\s`._-]+|"
    r"(?:pushed|moved|bumped)\s+(?:your|the|that)\s+[\w\s:`'-]+?\s+(?:back|up|forward|to\s+\d+)\b.*|"
    r"(?:pushed|moved|bumped)\s+back\s+(?:your|the|that)\s+[\w\s:`'-]+|"
    r"added\s+.+?\s+to\s+(?:your|the|my)\s+(?:[\w\s]*?(?:list|notes?|bookmarks?|favorites?|calendar|schedule|reminders?|queue|playlist|clipboard|contacts?))|"
    r"added\s+a\s+(?:quick\s+)?(?:note|reminder|event|bookmark|item|task)\s*[:\-]\s*.+|"
    r"(?:noted|jotted\s+down|wrote\s+down|logged|recorded)\s+that\s+.+|"
    r"(?:jotted|wrote)\s+that\s+down\b.*|"
    r"(?:brought|pulled)\s+(?:your|the)\s+[\w\s]*?(?:notes?|calendar|reminders?|window|app|screen|list|tab)\s+(?:up|to\s+the\s+front)|"
    r"(?:took|taken|snapped|captured|grabbed)\s+a\s+screenshot\b.*|"
    r"freed\s+up\s+.*?\b(?:space|memory|ram|storage|gb|mb)\b.*|"
    r"taken\s+care\s+of\s+(?:that|it|those|them)\s+for\s+you\b|"
    r"got\s+(?:that|it|those|them)\s+(?:sorted|taken\s+care\s+of|set\s+up|turned\s+on|turned\s+off|closed|cleared|moved|deleted|saved)\b"
    r")|"
    # 2. Progressive companion claims ("I'm turning on...", "Dimming your screen...", "Setting a timer...")
    r"(?:\bI(?:'m|\s+am)\s+(?:immediately\s+|currently\s+|now\s+|just\s+)?|^\s*)(?:"
    r"(?:turning|switching|toggling|flipping)\s+(?:on|off|down|up)\s+[\w\s-]+|"
    r"(?:turning|switching|toggling|flipping)\s+(?:the|your)\s+(?:volume|brightness|screen|display|audio|sound|speakers?|mic|microphone|bluetooth|wifi|wi-fi|hotspot|vpn|night\s+light|dark\s+mode|do\s+not\s+disturb|focus\s+mode|airplane\s+mode|battery\s+saver|webcam|camera)\s+(?:on|off|down|up)\b.*|"
    r"putting\s+(?:your|the)\s+(?:computer|laptop|pc|system|screen|display|audio|notifications?)\s+(?:to\s+sleep|into\s+sleep\s+mode|on\s+mute|on\s+silent|into\s+do\s+not\s+disturb|into\s+focus\s+mode|into\s+airplane\s+mode|into\s+battery\s+saver)\b.*|"
    r"setting\s+(?:up\s+)?(?:a|an|the|your)\s+(?:[\w-]+\s+){0,3}(?:timer|alarm|reminder|event|meeting|appointment|wallpaper|background|out-of-office)\b.*|"
    r"(?:pausing|resuming|stopping|skipping|muting|unmuting|shuffling|looping)\s+(?:your|the|this|to\s+the\s+next)\s+(?:music|song|track|playback|audio|podcast|video|player|spotify|computer\s+speakers?|system\s+audio|speakers?|mic|microphone)\b.*|"
    r"(?:dimming|brightening|lowering|raising|adjusting)\s+(?:your|the)\s+(?:screen|display|monitor|brightness|volume|audio|sound|mic|microphone)\b.*|"
    r"(?:snoozing|cancelling|canceling|dismissing|rescheduling|pushing\s+back)\s+(?:your|the|that)\s+(?:[\w-]+\s+){0,2}(?:alarm|timer|reminder|meeting|call|event|appointment|sync)\b.*|"
    r"(?:locking|unlocking|sleeping)\s+(?:your|the)\s+(?:computer(?:\s+screen)?|screen|display|workstation|pc|laptop|session)\b.*|"
    r"(?:emptying|clearing(?:\s+out)?|cleaning\s+up|flushing)\s+(?:your|the)\s+(?:trash(?:\s+can)?|recycle\s+bin|clipboard|downloads?(?:\s+folder)?|desktop|cache|temp\s+files?|notifications?)\b.*|"
    r"(?:pulling\s+up|bringing\s+up|opening\s+up|closing\s+out(?:\s+of)?|force-closing|force-quitting|quitting|minimizing|maximizing|pinning|unpinning|ejecting|disconnecting|reconnecting|pairing|re-pairing)\s+(?:your|the|all\s+of\s+your)\s+(?:[\w-]+\s+){0,3}(?:notes?|sticky\s+notes?|calendar|reminders?|bookmarks?|tabs?|windows?|apps?|spotify|slack|discord|zoom|teams|chrome|browser|calculator|notepad|bluetooth|headphones?|airpods?|buds?|drive|usb|vpn|wifi|wi-fi)\b.*|"
    r"(?:taking|snapping|capturing)\s+a\s+screenshot\b.*|"
    r"(?:jotting|writing|noting)\s+(?:that|this)\s+down\b.*|"
    r"sending\s+(?:that|it|the\s+[\w\s]+)\s+now\b"
    r")|"
    # 3. Copular state-of-completion & anaphoric passive companion claims
    r"\b(?:calculator(?:\s+and\s+notepad)?|notepad|spotify|slack|discord|zoom|teams|sticky\s+notes?|night\s+light(?:\s+mode)?|do\s+not\s+disturb(?:\s+mode)?|dark\s+mode|light\s+mode|focus\s+mode|airplane\s+mode|battery\s+saver(?:\s+mode)?|sleep\s+mode|wi-?fi|bluetooth|vpn|hotspot|your\s+(?:[\w-]+\s+){0,2}(?:screen|display|monitor|computer|laptop|workstation|microphone|mic|speakers?|audio|sound|volume|brightness|alarm|timer|reminder|meeting|call|appointment|calendar|clipboard|recycle\s+bin|trash(?:\s+can)?|downloads?(?:\s+folder)?|desktop|vpn|bluetooth|wi-?fi|hotspot|headphones?|airpods?|earbuds?|buds?|usb\s+(?:thumb\s+)?drive|thumb\s+drive|external\s+drive|drive|webcam|camera|music|playback|wallpaper|background|notifications?|tabs?|windows?))\s+(?:is|are|has\s+been|have\s+been)\s+(?:now\s+|all\s+|already\s+|successfully\s+|safely\s+)*(?:open(?:ed)?|closed|quit|minimized|maximized|pinned|unpinned|empty|emptied|clear|cleared|cleaned\s+up|sorted|organized|flushed|muted|unmuted|on|off|set(?:\s+for\s+[\w\s:]+|\s+to\s+[\w\s%]+)?|scheduled(?:\s+for\s+[\w\s:]+)?|rescheduled(?:\s+to\s+[\w\s:]+|\s+for\s+[\w\s:]+)?|pushed\s+back(?:\s+to\s+[\w\s:]+)?|paused|resumed|stopped|skipped|locked|unlocked|asleep|connected|disconnected|paired|unpaired|ejected|safe\s+to\s+remove|disabled|enabled|activated|deactivated|dimmed|brightened|lowered|raised|at\s+\d+%|snoozed|cancelled|canceled|dismissed|saved|bookmarked|backed\s+up|restored)\b|"
    r"\b(?:they've|they\s+have|they're|they\s+are|it's|it\s+has|it\s+is|that's|that\s+has|that\s+is|both\s+have|all\s+(?:of\s+)?(?:those|them|your)\s+[\w\s-]{0,25}?)\s+(?:been\s+|now\s+|all\s+|already\s+|safely\s+)*(?:added\s+to\s+your\s+(?:[\w\s-]*?(?:list|notes?|calendar|reminders?|bookmarks?|favorites?|queue|playlist|contacts?))|saved\s+(?:to|in)\s+your\s+[\w\s-]*?(?:bookmarks?|favorites?|folder|notes?|desktop|documents?|clipboard)|cleared\s+(?:off|from)\s+your\s+(?:desktop|screen|clipboard|downloads?|list)|moved\s+(?:to|into)\s+your\s+[\w\s-]+|deleted\s+from\s+your\s+[\w\s-]+|copied\s+to\s+your\s+clipboard|ejected(?:\s+safely)?|taken\s+care\s+of|pushed\s+back\s+to\s+[\w\s:]+|rescheduled\s+(?:to|for)\s+[\w\s:]+|named\s+(?:[`'\"][a-zA-Z0-9_.-]+[`'\"]|[a-zA-Z0-9_-]+\.[a-zA-Z0-9]{2,5})\b)|"
    r"\b(?:[`'\"]?[a-zA-Z0-9_.-]+\.(?:xlsx|pdf|docx|txt|csv|png|jpg|zip)[`'\"]?|the\s+(?:[\w-]+\s+){0,3}(?:pdfs?|files?|photos?|pictures?|screenshots?|documents?|spreadsheets?|links?|urls?|passwords?|codes?|snippets?|notes?|items?|songs?|tracks?|emails?|messages?|folders?|archives?))\s+(?:is|are|has\s+been|have\s+been)\s+now\s+(?:on\s+your\s+clipboard|in\s+your\s+[\w\s-]+?(?:folder|directory|trash|recycle\s+bin|list|bookmarks?|notes?|archive)|saved\s+(?:to|in)\s+your\s+[\w\s-]+|pinned(?:\s+to\s+your\s+[\w\s-]+|\s+for\s+easy\s+access)?)\b|"
    r"^(?:(?:sure\s+thing|okay|got\s+it|done|all\s+set|no\s+problem|right\s+away)[.!,\s—\-]+)?(?:sleep\s+mode\s+(?:is\s+)?(?:activated|enabled|on)|focus\s+mode\s+(?:is\s+)?(?:activated|enabled|on)|airplane\s+mode\s+(?:is\s+)?(?:activated|enabled|on)|battery\s+saver\s+(?:is\s+)?(?:activated|enabled|on)|music\s+(?:is\s+)?paused|playback\s+(?:is\s+)?paused|audio\s+(?:is\s+)?muted|mic(?:rophone)?\s+(?:is\s+)?muted|screen\s+(?:is\s+)?(?:locked|dimmed)|clipboard\s+(?:is\s+)?cleared|trash\s+(?:is\s+)?emptied|recycle\s+bin\s+(?:is\s+)?emptied|alarm\s+(?:is\s+)?set\s+for\s+\d+|timer\s+(?:is\s+)?set\s+for\s+\d+|reminder\s+(?:is\s+)?set\s+for\s+[\w\s:]+)\b"
    r")",
    re.IGNORECASE,
)

_ELLIPTICAL_COMPLETION_FULL_REGEX = re.compile(
    r"^\s*(?:done|all\s+done|all\s+set|taken\s+care\s+of|sorted|finished|there\s+you\s+go)[\.!,—\-]+\s+"
    r"(?:how\s+does\s+that\s+(?:look|sound)(?:\s+for\s+you)?|let\s+me\s+know\s+if\s+(?:you\s+need\s+anything\s+else|that\s+helps|that's\s+better)\b|it(?:'s|\s+is)\s+all\s+taken\s+care\s+of\b|that(?:'s|\s+is)\s+all\s+taken\s+care\s+of\b)",
    re.IGNORECASE,
)


def extract_user_context_text(
    user_context: str | Sequence[dict[str, str]] | None,
) -> tuple[str, str, str]:
    """Normalizes string or multi-turn message list into (full_user_text, last_assistant_text, final_user_text)."""
    if not user_context:
        return ("", "", "")
    if isinstance(user_context, str):
        u_turns = re.findall(r"\[Turn\s+\d+\s+User\]\s*:\s*(.+)", user_context, flags=re.IGNORECASE)
        a_turns = re.findall(
            r"\[Turn\s+\d+\s+Assistant\]\s*:\s*(.+)", user_context, flags=re.IGNORECASE
        )
        if u_turns:
            return (" ".join(u_turns), a_turns[-1] if a_turns else "", u_turns[-1])
        return (user_context, "", user_context)
    user_parts: list[str] = []
    asst_parts: list[str] = []
    for m in user_context:
        if isinstance(m, dict):
            role = str(m.get("role", "")).lower()
            content = str(m.get("content", ""))
            if role == "user":
                user_parts.append(content)
            elif role == "assistant":
                asst_parts.append(content)
    return (
        " ".join(user_parts),
        asst_parts[-1] if asst_parts else "",
        user_parts[-1] if user_parts else "",
    )


def is_meta_or_creative_context(
    clause: str,
    user_context: str | Sequence[dict[str, str]] | None = None,
    full_narration: str | None = None,
) -> bool:
    """
    Returns True if the conversational context or discourse framing indicates
    the assistant is fulfilling a creative writing, roleplay dialogue, translation,
    grammar correction, UI copywriting, or code/JSON snippet request rather than
    asserting a real host action on the user's computer.
    """
    full_user_text, _, _ = extract_user_context_text(user_context)
    if full_user_text:
        if _META_CREATIVE_USER_PROMPT_REGEX.search(full_user_text):
            return True
    narration_check = full_narration or clause
    if _DISCOURSE_ARTIFACT_FRAME_REGEX.search(narration_check):
        return True
    return False


def is_elliptical_action_confirmation(
    clause: str,
    user_context: str | Sequence[dict[str, str]] | None = None,
    full_narration: str | None = None,
) -> bool:
    """
    Detects elliptical multi-turn action completions (e.g. "Done. How does that look for you?",
    "Done. Let me know if your streaming speeds improve!") where the assistant claims completion
    of the user's confirmed action without repeating the verb or object noun.
    """
    narration_text = (full_narration or clause).strip()
    if _ELLIPTICAL_COMPLETION_FULL_REGEX.search(narration_text):
        return True
    full_user_text, last_asst_text, final_user_text = extract_user_context_text(user_context)
    if not final_user_text:
        return False
    has_asst_offer = bool(
        re.search(
            r"\b(?:would\s+you\s+like\s+me\s+to|do\s+you\s+want\s+me\s+to|should\s+i|want\s+me\s+to|shall\s+i|can\s+i\s+go\s+ahead\s+and|ready\s+for\s+me\s+to)\b",
            last_asst_text,
            re.IGNORECASE,
        )
    )
    has_user_confirm = bool(
        re.search(
            r"^\s*(?:yeah|yep|yup|yes|sure(?:\s+thing)?|please(?:\s+do)?|go\s+for\s+it|go\s+ahead|do\s+it|knock\s+it\s+out|make\s+it\s+happen|let's\s+do\s+it|sounds\s+good|for\s+sure|definitely|absolutely|ok(?:ay)?)\b",
            final_user_text,
            re.IGNORECASE,
        )
    )
    if has_asst_offer and has_user_confirm:
        first_sentence = re.split(r"(?<=[.!?])\s+|\n+", narration_text)[0]
        if re.match(
            r"^\s*(?:(?:okay|ok|got\s+it|sure(?:\s+thing)?|alright)[,!.\s]+)?(?:done|all\s+done|all\s+set|taken\s+care\s+of|sorted|finished|there\s+you\s+go)[\.!,—\-]",
            narration_text,
            re.IGNORECASE,
        ) and not _NEGATION_PREFIX_PATTERN.search(first_sentence):
            return True
    return False


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

    def __init__(self, grammar_path: Path | str | None = None) -> None:
        self.grammar_path = Path(grammar_path or "config/grammars/action_claim.gbnf")
        self._grammar_text: str | None = None
        if self.grammar_path.exists():
            try:
                self._grammar_text = self.grammar_path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                logger.debug("action_claim_gbnf_load_failed", path=str(self.grammar_path), error=str(exc))

    def evaluate_clause(
        self,
        clause: str,
        verified_receipts: Sequence[dict[str, JsonValue]],
        stale_before: float | None = None,
        user_context: str | Sequence[dict[str, str]] | None = None,
        full_narration: str | None = None,
    ) -> GateResult:
        """
        Evaluates a streamed clause for ungrounded physical/stateful action claims
        under grammar-constrained channel rules (<= 1.0 ms budget, target < 100 us).
        Supports conversational user_context and full_narration framing (v3.0).
        """
        t0 = time.perf_counter()

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
            r"^(?:(?:action|status|step|task|purge|vacuum|checkpointing|syncing|confirmation|success|result)\s*:\s*|"
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

        # 1. Check synchronous execution / completion-notification patterns before future intent filter
        is_sync_future = bool(_SYNCHRONOUS_EXECUTION_FUTURE_REGEX.search(clean))
        has_stage_or_fake_scan = bool(
            _STAGE_DIRECTION_OR_FAKE_SCAN_REGEX.search(clause)
            or _STAGE_DIRECTION_OR_FAKE_SCAN_REGEX.search(raw_clean)
        )
        if not is_sync_future and not has_stage_or_fake_scan and _FUTURE_INTENT_PATTERN.search(clean):
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
        if TruthInReceiptMatcher.IDIOMATIC_NON_ACTION_PATTERN.search(clean):
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
        if TruthInReceiptMatcher.HEDGE_PATTERN.search(clean):
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
        if TruthInReceiptMatcher.PAST_CONTEXT_PATTERN.search(clean):
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
            stem = EXPANDED_STEM_MAP.get(
                verb, COMPANION_BOUND_STEM_MAP.get(verb, verb)
            ).lower()
            t_clean = re.sub(
                r"^(?:the|a|an|your|my|our|this|that|these|those|all)\s+",
                "",
                target_phrase.lower(),
                flags=re.IGNORECASE,
            ).strip(".,!?;: ")
            for r in eligible_receipts:
                r_action = str(r.get("action", "")).lower()
                r_target = str(r.get("target", r.get("path", ""))).lower()
                action_ok = (stem in r_action) or (r_action in stem) or (verb in r_action)
                target_ok = (t_clean in r_target) or (r_target in t_clean)
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
                if v_clean in ("verify", "protect") or _CONVERSATIONAL_META_TARGETS_REGEX.match(t_clean):
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
                    raw_targets = [t.strip() for t in re.split(r"\s+and\s+|\s*,\s*", remainder) if t.strip()]
                    for target_item in raw_targets:
                        claims_to_verify.append((verb, target_item, m_canon.group(0)))

        # (b) Initiating or execution status banner: "I'm initiating the reboot now", "Command executed:"
        if not claims_to_verify:
            m_init = _INITIATING_ACTION_REGEX.search(raw_clean) or _INITIATING_ACTION_REGEX.search(clean)
            if m_init:
                prefix = raw_clean[: m_init.start()].lower()
                if not _NEGATION_PREFIX_PATTERN.search(prefix):
                    verb_noun = (m_init.group(1) or "execute").lower()
                    stem = "reboot" if ("reboot" in verb_noun or "restart" in verb_noun) else verb_noun
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
                    # Strip harmless completion / in-progress tail before checking gerund predicate verbs
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
                        re.match(r"^(?:on|in|at|to|from|with|by|for|of|as)\b[\.!]?$", target, re.IGNORECASE)
                    )
                    is_definition_or_title_header = (
                        (
                            not is_explicit_1p
                            and ":" in target
                            and not re.search(
                                r"(?:https?|ftp|s3|:\d{2,5}|[a-zA-Z]:[\\/]|:\s*[\"'])",
                                target,
                                re.IGNORECASE,
                            )
                        )
                        or (not is_explicit_1p and bool(re.match(r"^(?:the|a|an)\s+[A-Z][a-z]+$", target)))
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

        # (e) Telegraphic or Permission Grant Confirmation: "Files removed.", "The auditors group now has READ access..."
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
            else:
                m_grant = _STATE_GRANT_CONFIRMATION_REGEX.search(clean)
                if m_grant:
                    claims_to_verify.append(("grant", m_grant.group(1).strip(), m_grant.group(0)))

        # (f) Everyday Companion Action, Phrasal, & Copular State-of-Completion Claims (v3.0)
        if not claims_to_verify:
            m_comp = _COMPANION_ACTION_CLAIM_REGEX.search(
                clean
            ) or _COMPANION_ACTION_CLAIM_REGEX.search(raw_clean)
            if m_comp:
                prefix_comp = raw_clean[: m_comp.start()].lower()
                if not _NEGATION_PREFIX_PATTERN.search(prefix_comp):
                    claims_to_verify.append(("update", m_comp.group(0).strip(), m_comp.group(0)))

        # (g) Context-Aware Multi-Turn Elliptical Action Completion ("Done. How does that look for you?")
        if not claims_to_verify and is_elliptical_action_confirmation(
            clause, user_context=user_context, full_narration=full_narration
        ):
            if re.match(
                r"^\s*(?:done|all\s+done|all\s+set|taken\s+care\s+of)\b",
                raw_clean,
                re.IGNORECASE,
            ):
                claims_to_verify.append(("complete", "confirmed_companion_action", raw_clean))

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
        for verb, target, matched_text in claims_to_verify:
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

    STEM_MAP = {
        "deleted": "delete",
        "deleting": "delete",
        "created": "create",
        "creating": "create",
        "modified": "modify",
        "modifying": "modify",
        "updated": "update",
        "updating": "update",
        "executed": "execute",
        "executing": "execute",
        "ran": "run",
        "running": "run",
        "installed": "install",
        "installing": "install",
        "removed": "remove",
        "removing": "remove",
        "sent": "send",
        "sending": "send",
        "uploaded": "upload",
        "uploading": "upload",
        "fetched": "fetch",
        "fetching": "fetch",
        "saved": "save",
        "saving": "save",
        "wrote": "write",
        "writing": "write",
        "posted": "post",
        "posting": "post",
        "rebooted": "reboot",
        "rebooting": "reboot",
        "restarting": "restart",
        "booked": "book",
        "booking": "book",
        "placed": "place",
        "placing": "place",
        "processed": "process",
        "processing": "process",
        "started": "start",
        "starting": "start",
        "closed": "close",
        "closing": "close",
        "copied": "copy",
        "copying": "copy",
        "moved": "move",
        "moving": "move",
        "terminating": "terminate",
        "downloading": "download",
        "clearing": "clear",
        "purging": "purge",
    }

    # Past-session temporal markers: recollections of PRIOR verified actions are
    # grounded by long-term memory (A1), not by current-turn ToolReceipts. The
    # truth-in-receipt gate (D-BRAIN-04) only governs claims about THIS turn.
    PAST_CONTEXT_PATTERN = re.compile(
        r"\b(?:"
        r"last\s+session|previous\s+session|prior\s+session|earlier\s+session|"
        r"a\s+few\s+days?\s+ago|days?\s+ago|weeks?\s+ago|(?<!from\s)yesterday|"
        r"last\s+week|previously|in\s+the\s+past|earlier\s+on|"
        r"(?:my\s+|session\s+|historical\s+|memory\s+)records?\s+(?:from|show|showing|indicate)|"
        r"records?\s+(?:show|showing|indicate)|my\s+records|"
        r"(?:information|evidence|entries|logs?)\s+(?:from\s+(?:our|last|previous|earlier)|show|showing|indicate)|"
        r"memor(?:y|ies)\s+(?:from|show|showing)|from\s+our\s+history|"
        r"in\s+our\s+history|histor(?:y|ical)\s+records?"
        r")\b",
        re.IGNORECASE,
    )

    # Idiomatic non-action filter to prevent false aborts on figurative language
    IDIOMATIC_NON_ACTION_PATTERN = re.compile(
        r"\b(?:"
        r"ran\s+(?:into|out\s+of|across|short|afoul|(?:a\s+)?(?:\w+\s+)?check)|"
        r"saved\s+(?:the\s+day|face|money|time|trouble)|"
        r"sent\s+(?:my\s+|our\s+|a\s+|warm\s+)*(?:regards|condolences|wishes|love|greetings?)|"
        r"started\s+(?:to\s+\w+|thinking|wondering|feeling)|"
        r"closed\s+(?:the\s+(?:loop|door|book|case|discussion|matter|ticket|thread)|(?:my|our)\s+eyes|out|in\s+on)|"
        r"moved\s+(?:on(?:\s+from)?|forward(?:\s+with)?|ahead(?:\s+with)?|past|mountains|away)|"
        r"processed\s+(?:what|that|this|the\s+(?:information|data|news|grief|feedback|input|request|idea|details?)|mentally|emotionally)|"
        r"compiled\s+(?:a\s+|an\s+|the\s+)?(?:[\w\-]+\s+)?(?:list|summary|overview|collection|bibliography|guide|table|set\s+of)\b|"
        r"updated\s+my\s+internal\s+verification\s+logs?\b|"
        r"placed\s+(?:(?:an?\s+)?(?:emphasis|focus|priority|trust|faith|bets?|confidence|blame)\s+(?:on|in)|(?:my|our|their|his|her)\s+(?:trust|faith|emphasis|focus|confidence)\s+(?:on|in))"
        r")\b",
        re.IGNORECASE,
    )

    # Hedge-phrase pattern: epistemic uncertainty suppresses the receipt check.
    HEDGE_PATTERN = re.compile(
        r"\b(?:I\s+think\s+I|I\s+believe\s+I|I\s+(?:may|might|could)\s+have|"
        r"not\s+sure\s+(?:if|whether)|not\s+certain\s+(?:if|whether)|"
        r"(?:can\'t|cannot)\s+tell\s+(?:you\s+)?(?:if|whether)|"
        r"(?:don\'t|do\s+not)\s+know\s+(?:if|whether)|"
        r"perhaps\s+I|maybe\s+I)\b",
        re.IGNORECASE,
    )

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
        ungrounded: list[str] = []
        for target_obj in clean_targets:
            target_lower = target_obj.lower()
            matched = False
            for r in eligible_receipts:
                r_action = str(r.get("action", "")).lower()
                r_target = str(r.get("target", r.get("path", ""))).lower()
                action_ok = (
                    (stem in r_action) or (action_verb in r_action) or (r_action in action_verb)
                )
                target_ok = (target_lower in r_target) or (r_target in target_lower)
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
        """Sets the user / conversation context for the current turn (v3.0 context-aware supervision)."""
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
