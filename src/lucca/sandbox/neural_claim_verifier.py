"""
OpenVINO 10-Class Clause-Level Neurosymbolic Action-Claim & Speech-Act Verifier (WO-42 Milestone 1.1).

Replaces the whole-paragraph 4-class verifier from WO-41 with a factored neurosymbolic architecture:
  1. Neural Speech-Act & Tool-Family Classifier (`cross-encoder/nli-MiniLM2-L6-H768`, 82.1M params):
     Evaluates `(user_request, assistant_clause)` on Intel NPU / iGPU / CPU (static shape `[1, 192]`)
     WITHOUT injecting `verified_tools` strings into the neural prompt.
  2. Deterministic Symbolic Tool-Receipt Set Verifier:
     Checks each clause's predicted `CLAIM_*` tool family against the normalized set of executed
     tool receipts (`REQUIRED_TOOLS[family] & executed_tools`), enforcing multi-clause and
     multi-target receipt cardinality invariants.

10-Class Speech-Act Output Taxonomy (`logits[:, 0:10]`):
  - 0: BENIGN               (Safe answer, translation, rewrite, quote, roleplay/fiction, UI copy,
                             technical explanation, figurative idiom, past-session recollection, refusal)
  - 1: UNFULFILLED_PROMISE  (Pure hanging promise to check/act with 0 tools and no completed result)
  - 2: CLAIM_FILE_WRITE     (Completed/active/implicit claim of saving, writing, updating, or creating a file/note)
  - 3: CLAIM_DELETE         (Completed/active/implicit claim of deleting, removing, wiping, purging, or emptying)
  - 4: CLAIM_LAUNCH_EXEC    (Completed/active/implicit claim of launching/opening an app or running code/processes)
  - 5: CLAIM_SEARCH_READ    (Completed/active/implicit claim of reading a file, searching, or live telemetry inspection)
  - 6: CLAIM_MEMORY         (Completed/active/implicit claim of committing/storing a fact to long-term memory)
  - 7: CLAIM_COMM_EXTERNAL  (Completed/active/implicit claim of sending an email/message or scheduling an event)
  - 8: CLAIM_SYSTEM_STATE   (Completed/active/implicit OS/device/audio/display/network/power state-change claim)
  - 9: DEONTIC_CAPITULATION (Policy/guardrail capitulation assertion: safety/sandbox checks disabled/bypassed)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import threading
import time
from typing import Final

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

MAX_LEN: Final[int] = 192

SPEECH_ACT_CLASSES: Final[tuple[str, ...]] = (
    "BENIGN",
    "UNFULFILLED_PROMISE",
    "CLAIM_FILE_WRITE",
    "CLAIM_DELETE",
    "CLAIM_LAUNCH_EXEC",
    "CLAIM_SEARCH_READ",
    "CLAIM_MEMORY",
    "CLAIM_COMM_EXTERNAL",
    "CLAIM_SYSTEM_STATE",
    "DEONTIC_CAPITULATION",
)

CLAIM_FAMILY_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "CLAIM_FILE_WRITE",
        "CLAIM_DELETE",
        "CLAIM_LAUNCH_EXEC",
        "CLAIM_SEARCH_READ",
        "CLAIM_MEMORY",
        "CLAIM_COMM_EXTERNAL",
        "CLAIM_SYSTEM_STATE",
        "DEONTIC_CAPITULATION",
    }
)

# Legacy 4-class names preserved for backward-compatible verdict reporting
CLASS_NAMES: Final[tuple[str, ...]] = (
    "BENIGN",
    "GROUNDED_ACTION",
    "UNGROUNDED_CLAIM",
    "UNFULFILLED_PROMISE",
)

# Symbolic Tool-Family -> Allowed Canonical Tool Names
FAMILY_TOOL_SETS: Final[dict[str, frozenset[str]]] = {
    "CLAIM_FILE_WRITE": frozenset(
        {
            "write_file",
            "edit_file",
            "note_write",
            "memory_commit",
            "save",
            "write",
            "create",
            "update",
            "modify",
            "add",
            "store",
            "note",
            "settings_update",
        }
    ),
    "CLAIM_DELETE": frozenset(
        {
            "delete_file",
            "note_delete",
            "delete",
            "remove",
            "system_empty_trash",
            "calendar_delete",
            "reminder_delete",
            "github_delete_ssh_key",
            "printer_clear_queue",
            "redis_flushall",
            "network_flush_dns",
            "wipe",
            "purge",
            "clear",
            "empty",
        }
    ),
    "CLAIM_LAUNCH_EXEC": frozenset(
        {
            "launch_app",
            "run_python",
            "calc_math",
            "process_kill",
            "docker_stop_all",
            "launch",
            "open",
            "start",
            "run",
            "execute",
            "invoke_skill",
            "apply_patch",
        }
    ),
    "CLAIM_SEARCH_READ": frozenset(
        {
            "read_file",
            "fetch_url",
            "note_read",
            "search_web",
            "search_text",
            "memory_search",
            "self_history_search",
            "clipboard_read",
            "artifact_verify",
            "disk_usage",
            "calendar_list_events",
            "alarm_list",
            "email_search",
            "vpn_status",
            "contacts_search",
            "system_memory_status",
            "research_topic",
            "read",
            "search",
            "fetch",
            "scan",
            "check",
            "inspect",
        }
    ),
    "CLAIM_MEMORY": frozenset(
        {
            "memory_commit",
            "note_write",
            "commit",
            "save",
            "store",
        }
    ),
    "CLAIM_COMM_EXTERNAL": frozenset(
        {
            "email_send",
            "send",
            "schedule_event",
            "inbox_handoff",
            "calendar_delete",
            "reminder_delete",
            "post",
            "upload",
            "order",
            "book",
            "transfer",
        }
    ),
    "CLAIM_SYSTEM_STATE": frozenset(
        {
            "settings_update",
            "audio_set_mode",
            "audio_set_mute",
            "vpn_connect",
            "vpn_status",
            "camera_set_state",
            "smart_home_cover",
            "power_profile_set",
            "network_flush_dns",
            "hotspot_set_state",
            "slack_set_dnd",
            "windows_update_pause_restarts",
            "system_empty_trash",
            "printer_clear_queue",
            "redis_flushall",
            "process_kill",
            "docker_stop_all",
            "launch_app",
            "calendar_delete",
            "reminder_delete",
            "github_delete_ssh_key",
        }
    ),
    # Deontic capitulation is NEVER grounded by any tool receipt
    "DEONTIC_CAPITULATION": frozenset(),
}

# Substring stems for matching custom/unlisted tool names to speech-act families
FAMILY_TOOL_STEMS: Final[dict[str, tuple[str, ...]]] = {
    "CLAIM_FILE_WRITE": ("write", "save", "edit", "create", "update", "append", "patch"),
    "CLAIM_DELETE": (
        "delete",
        "remove",
        "trash",
        "purge",
        "wipe",
        "flush",
        "clear",
        "revoke",
        "drop",
        "empty",
        "cancel",
    ),
    "CLAIM_LAUNCH_EXEC": (
        "launch",
        "open",
        "run",
        "exec",
        "start",
        "kill",
        "stop",
        "terminate",
        "compile",
        "build",
        "deploy",
        "install",
        "calc",
    ),
    "CLAIM_SEARCH_READ": (
        "read",
        "search",
        "fetch",
        "list",
        "status",
        "usage",
        "inspect",
        "scan",
        "check",
        "query",
        "find",
        "lookup",
        "verify",
    ),
    "CLAIM_MEMORY": ("memory_commit", "commit", "remember", "note_write"),
    "CLAIM_COMM_EXTERNAL": (
        "send",
        "email",
        "post",
        "upload",
        "schedule",
        "book",
        "order",
        "transfer",
        "handoff",
        "notify",
    ),
    "CLAIM_SYSTEM_STATE": (
        "set",
        "update",
        "toggle",
        "switch",
        "mute",
        "unmute",
        "connect",
        "disconnect",
        "enable",
        "disable",
        "pause",
        "resume",
        "sleep",
        "lock",
        "unlock",
        "dim",
        "brighten",
        "flush",
        "clear",
        "kill",
        "stop",
        "reboot",
        "restart",
        "cover",
        "dnd",
        "mode",
        "state",
        "profile",
        "launch",
        "trash",
        "revoke",
    ),
    "DEONTIC_CAPITULATION": (),
}

_SENTENCE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+|\n+")

_COORDINATED_ACTION_SPLIT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:;\s+|(?:\s*,\s*|\s+)and\s+(?=(?:also\s+|then\s+)?(?:I\s+|I've\s+|I\s+have\s+|we\s+|we've\s+)?"
    r"(?:permanently\s+|successfully\s+|completely\s+|already\s+|just\s+|gone\s+ahead\s+and\s+|went\s+ahead\s+and\s+)?"
    r"(?:deleted|removed|wiped|purged|cleared|emptied|scrubbed|saved|wrote|updated|created|modified|edited|"
    r"sent|emailed|dispatched|uploaded|posted|launched|opened|started|executed|ran|terminated|killed|"
    r"stopped|restarted|rebooted|committed|stored|searched|checked|read|fetched|installed|deployed|"
    r"formatted|muted|unmuted|locked|unlocked|enabled|disabled|paused|resumed|cancelled|canceled|"
    r"scheduled|revoked|flushed|dropped)\b))",
    re.IGNORECASE,
)

_BARE_PAST_ACTION_START_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:also|then|permanently|successfully|completely|already|just|gone\s+ahead\s+and|went\s+ahead\s+and)\s+)*"
    r"(?:deleted|removed|wiped|purged|cleared|emptied|scrubbed|saved|wrote|updated|created|modified|edited|"
    r"sent|emailed|dispatched|uploaded|posted|launched|opened|started|executed|ran|terminated|killed|"
    r"stopped|restarted|rebooted|committed|stored|searched|checked|read|fetched|installed|deployed|"
    r"formatted|muted|unmuted|locked|unlocked|enabled|disabled|paused|resumed|cancelled|canceled|"
    r"scheduled|revoked|flushed|dropped)\b",
    re.IGNORECASE,
)

_CLAUSE_ACTION_VERB_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:deleted|removed|wiped|purged|cleared|emptied|scrubbed|saved|wrote|written|updated|created|"
    r"modified|edited|appended|sent|emailed|dispatched|uploaded|posted|launched|opened|started|"
    r"executed|ran|terminated|killed|stopped|restarted|rebooted|committed|stored|searched|"
    r"checked|read|fetched|installed|deployed|formatted|muted|unmuted|locked|unlocked|enabled|"
    r"disabled|paused|resumed|cancelled|canceled|scheduled|revoked|flushed|dropped|overwritten|"
    r"archived|backed\s+up|renamed|moved|copied|"
    r"looking\s+at\s+your\s+live|according\s+to\s+your\s+live|scanning\s+your\s+live|"
    r"checking\s+your\s+local|inspecting\s+your\s+local|actively\s+connected\s+to)\b",
    re.IGNORECASE,
)

_FIRST_PERSON_EXPLICIT_CLAIM_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:I|I've|I\s+have)\s+(?:just\s+|now\s+|then\s+|also\s+|went\s+ahead\s+and\s+)*"
    r"(?:deleted|removed|erased|wiped|purged|emptied|cleared|flushed|dropped|saved|wrote|written|"
    r"overwritten|updated|created|modified|edited|appended|sent|emailed|dispatched|launched|"
    r"opened|started|executed|ran|terminated|killed|stopped|committed|stored|searched|queried|"
    r"checked|read|inspected|reviewed|fetched|enabled|disabled|muted|switched|disconnected)\b",
    re.IGNORECASE,
)

_PASSIVE_OR_COPULAR_STATE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:deontic|sandbox(?:ing)?|guardrails?|security\s+constraints|safety\s+checks|safety\s+rules|safety\s+filters|"
    r"microphone|brightness|night\s+light|do\s+not\s+disturb|bluetooth|vpn|dns\s+cache|docker|container|"
    r"cpu\s+temperature|battery\s+is\s+at|unread\s+emails?|unread\s+messages?|"
    r"has\s+been\s+(?:deleted|removed|saved|written|updated|sent|launched|closed|flushed|muted|enabled|disabled)|"
    r"is\s+now\s+(?:deleted|removed|saved|updated|sent|launched|closed|flushed|muted|enabled|disabled|activated|active|off|on))\b",
    re.IGNORECASE,
)


def resolve_clause_claim_family(clause_text: str, neural_claim_cls: str) -> str:
    """
    Deterministic neurosymbolic resolver that maps an action-claim clause with an
    unambiguous verb/target to its exact `CLAIM_*` tool family, falling back to
    `neural_claim_cls` for implicit/zero-verb or open-vocabulary state claims.
    """
    c_low = clause_text.lower()
    if re.search(
        r"\b(?:deontic|sandbox(?:ing)?|guardrails?|security\s+constraints|safety\s+checks|safety\s+rules|safety\s+filters)\b.*"
        r"\b(?:disabled|bypassed|lifted|suspended|overridden|unlocked|turned\s+off|no\s+longer\s+active)\b",
        c_low,
    ):
        return "DEONTIC_CAPITULATION"
    if re.search(
        r"\b(?:committed|saved|stored|added|recorded|logged)\b.*\bmemory\b|\bmemory\b.*\b(?:committed|saved|stored)\b",
        c_low,
    ):
        return "CLAIM_MEMORY"
    if re.search(
        r"\b(?:deleted|removed|erased|wiped|purged|emptied|revoked|scrubbed|cleared|flushed|dropped)\b",
        c_low,
    ):
        return "CLAIM_DELETE"
    if re.search(
        r"\b(?:sent|emailed|dispatched)\b.*\b(?:email|message|notification|confirmation|report|proposal|invoice|thread)\b|"
        r"\b(?:email|message)\s+(?:has\s+been\s+|is\s+)?(?:sent|dispatched)\b",
        c_low,
    ):
        return "CLAIM_COMM_EXTERNAL"
    if re.search(
        r"\b(?:wrote|written|overwritten|created|saved|appended)\b.*\b(?:file|note|reminder|config|configuration|schedule|report|markdown|directory|workspace|entry|keys?|\.[a-z0-9]{2,8})\b|"
        r"\b(?:file|note)\s+is\s+(?:now\s+)?saved\b|"
        r"\bupdated\s+[a-z0-9_.-]+\.(?:json|yaml|yml|toml|md|txt|conf|ini|env|gitignore|nvmrc)\b",
        c_low,
    ):
        return "CLAIM_FILE_WRITE"
    if re.search(
        r"\b(?:executed|ran|launched|opened|started|killed|terminated)\b",
        c_low,
    ):
        return "CLAIM_LAUNCH_EXEC"
    if re.search(
        r"\b(?:updated|changed|switched|enabled|disabled|muted|lowered|dimmed|disconnected|flushed)\b.*\b(?:setting|settings|theme|mode|volume|brightness|audio|microphone|night\s+light|vpn|dns)\b",
        c_low,
    ):
        return "CLAIM_SYSTEM_STATE"
    if re.search(
        r"\b(?:read|searched|queried|checked|inspected|reviewed|scanned|fetched|found|retrieved|located|pulled\s+up|verified)\b",
        c_low,
    ):
        return "CLAIM_SEARCH_READ"
    return neural_claim_cls

_ADDITIVE_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:also|additionally|furthermore|moreover|plus|next|afterwards|as\s+well)\b",
    re.IGNORECASE,
)

_BOTH_CONJUNCTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\bboth\s+(.+?)\s+and\s+(.+?)(?:[\.!?,;]|$)",
    re.IGNORECASE,
)

_CAPABILITY_DISCLAIMER_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:cannot|can't|unable\s+to|don't\s+have\s+(?:access|a\s+tool|the\s+ability|permission|any\s+way)|"
    r"do\s+not\s+have\s+(?:access|a\s+tool|the\s+ability|permission|any\s+way)|"
    r"no\s+way\s+to|not\s+able\s+to|cannot\s+directly|can't\s+directly|"
    r"haven't\s+(?:executed|called|run)\s+the\s+tool|"
    r"failed\s+with\s+an?\s+error|execution\s+failed|tool\s+call\s+failed)\b",
    re.IGNORECASE,
)

_PSYCHOLOGICAL_OR_CONVERSATIONAL_METAPHOR_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"ran\s+into\s+a\s+problem|"
    r"have\s+written\s+poetry\s+before|"
    r"opened\s+(?:up\s+to\s+you|the\s+(?:conversation|discussion|floor|topic|dialogue))|"
    r"saved\s+(?:you\s+the\s+trouble|that\s+thought(?:\s+for\s+our\s+next\s+chat)?|the\s+day|face|money|time)|"
    r"created\s+(?:a\s+peaceful\s+environment|an\s+internal\s+representation|a\s+mental\s+note)|"
    r"deleted\s+(?:that\s+thought(?:\s+from\s+memory)?|unnecessary\s+assumptions)|"
    r"ran\s+through\s+the\s+(?:logical\s+)?(?:possibilities|options|scenarios|steps)|"
    r"updated\s+my\s+(?:understanding|mental\s+model|perspective|thinking)|"
    r"can\s+see\s+the\s+icon\s+clearly\s+on\s+screen"
    r")\b",
    re.IGNORECASE,
)


def parse_tool_spec(raw_spec: str) -> tuple[str, str]:
    """Parses `tool_name(k='v')` or `tool_name` into `(normalized_tool_name, args_string)`."""
    s = (raw_spec or "").strip()
    if not s:
        return ("", "")
    if "(" in s and s.endswith(")"):
        idx = s.index("(")
        return (s[:idx].strip().lower(), s[idx + 1 : -1].strip().lower())
    return (s.lower(), "")


def tool_matches_family(tool_name: str, family: str) -> bool:
    """Checks if a normalized tool name satisfies a required `CLAIM_*` speech-act family."""
    t = tool_name.strip().lower()
    if not t or family not in CLAIM_FAMILY_CLASSES:
        return False
    allowed_set = FAMILY_TOOL_SETS.get(family, frozenset())
    if t in allowed_set:
        return True
    stems = FAMILY_TOOL_STEMS.get(family, ())
    return any(stem in t for stem in stems)


def split_into_clauses(completion: str) -> list[tuple[str, bool]]:
    """
    Splits a completion into `(clause_text, is_coordinated_or_additive)` pairs.
    Preserves whole single-clause sentences while splitting multi-sentence replies and
    coordinated multi-action clauses (`"I searched X and deleted Y"`).
    """
    text = (completion or "").strip()
    if not text:
        return []

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    clauses: list[tuple[str, bool]] = []

    for s_idx, sent in enumerate(sentences):
        # Do not split inside quoted strings or markdown code blocks
        if sent.startswith(("```", '"', "'", ">")):
            clauses.append((sent, False))
            continue

        sub_parts = [p.strip() for p in _COORDINATED_ACTION_SPLIT_RE.split(sent) if p.strip()]
        if len(sub_parts) <= 1:
            is_add = s_idx > 0 and bool(_ADDITIVE_MARKER_RE.search(sent))
            clauses.append((sent, is_add))
        else:
            for p_idx, part in enumerate(sub_parts):
                if p_idx > 0 and _BARE_PAST_ACTION_START_RE.match(part):
                    norm_part = f"I {part}"
                    clauses.append((norm_part, True))
                else:
                    is_add = (p_idx > 0) or (s_idx > 0 and bool(_ADDITIVE_MARKER_RE.search(part)))
                    clauses.append((part, is_add))

    return clauses


def verify_clause_claims_against_receipts(
    clause_claims: Sequence[tuple[str, str, bool]],
    verified_tools: Sequence[str],
) -> tuple[bool, list[str]]:
    """
    Deterministic Symbolic Tool-Receipt Set Verifier (WO-42 Milestone 1.1).

    Args:
        clause_claims: Sequence of `(clause_text, predicted_claim_family, is_coordinated_or_additive)`
                       for every clause that predicted a `CLAIM_*` family.
        verified_tools: Sequence of executed tool receipt strings (bare names or `name(args)`).

    Returns:
        `(all_grounded, ungrounded_clauses)`
    """
    if not clause_claims:
        return (True, [])

    parsed_tools = [parse_tool_spec(t) for t in verified_tools if str(t).strip()]
    if not parsed_tools:
        return (False, [c[0] for c in clause_claims])

    ungrounded: list[str] = []
    # Track how many distinct coordinated/additive actions of each destructive/write family were claimed
    family_action_counts: dict[str, int] = {}

    for idx, (clause_text, family, is_coord_or_add) in enumerate(clause_claims):
        matching_receipts = [
            (t_name, t_args)
            for t_name, t_args in parsed_tools
            if tool_matches_family(t_name, family)
        ]
        c_low = clause_text.lower()
        if family == "CLAIM_LAUNCH_EXEC" and matching_receipts:
            if re.search(
                r"\b(?:launched|opened)\s+(?:the\s+)?(?!python\b)[a-z0-9_]+\s+(?:desktop\s+)?(?:app|application)\b",
                c_low,
            ):
                matching_receipts = [
                    (tn, ta)
                    for tn, ta in matching_receipts
                    if any(k in tn for k in ("launch", "open", "start"))
                ]
            elif re.search(
                r"\b(?:executed|ran)\s+(?:a\s+|the\s+)?(?:python|[\w\s]*\b(?:script|code|simulation|benchmark|command|test\s+suite))\b",
                c_low,
            ):
                matching_receipts = [
                    (tn, ta)
                    for tn, ta in matching_receipts
                    if any(k in tn for k in ("python", "run", "exec", "calc"))
                ]
        elif family == "CLAIM_SEARCH_READ" and matching_receipts:
            if re.search(
                r"\b(?:i|i've|i\s+have)\s+searched\s+(?:for\s+error\s+codes|the\s+web|online)\b",
                c_low,
            ):
                matching_receipts = [
                    (tn, ta)
                    for tn, ta in matching_receipts
                    if any(k in tn for k in ("search", "query", "find", "lookup", "research"))
                ]

        if not matching_receipts:
            ungrounded.append(clause_text)
            continue

        # Check `both X and Y` multi-target conjunction against single-target receipt
        m_both = _BOTH_CONJUNCTION_RE.search(clause_text)
        if m_both and len(matching_receipts) < 2:
            only_args = matching_receipts[0][1]
            if only_args:
                t1 = re.sub(r"^(?:the|a|an|your|my|our)\s+", "", m_both.group(1).strip().lower())
                t2 = re.sub(r"^(?:the|a|an|your|my|our)\s+", "", m_both.group(2).strip().lower())
                t1_clean = t1.strip(".,!?;:\"'` ")
                t2_clean = t2.strip(".,!?;:\"'` ")
                if (t1_clean in only_args) != (t2_clean in only_args):
                    ungrounded.append(clause_text)
                    continue

        if idx == 0 or family not in family_action_counts:
            family_action_counts[family] = 1
        elif is_coord_or_add and family in {"CLAIM_DELETE", "CLAIM_FILE_WRITE", "CLAIM_COMM_EXTERNAL"}:
            family_action_counts[family] += 1
            if family_action_counts[family] > len(matching_receipts):
                ungrounded.append(clause_text)
                continue

    return (len(ungrounded) == 0, ungrounded)


@dataclass(frozen=True)
class NeuralClaimVerdict:
    predicted_class: str
    prob_benign: float
    prob_grounded: float
    prob_ungrounded_claim: float
    prob_unfulfilled_promise: float
    is_ungrounded_claim: bool
    is_unfulfilled_promise: bool
    latency_ms: float
    device: str
    claimed_families: tuple[str, ...] = ()
    ungrounded_clauses: tuple[str, ...] = ()


class NeuralActionClaimVerifier:
    """
    Thread-safe OpenVINO runtime wrapper for the 10-class clause-level neurosymbolic
    action-claim verifier.
    """

    def __init__(
        self,
        model_dir: Path | str | None = None,
        preferred_devices: tuple[str, ...] = ("NPU", "GPU.0", "CPU"),
        claim_threshold: float = 0.50,
    ) -> None:
        if model_dir is None:
            repo_root = Path(__file__).resolve().parents[3]
            candidate = repo_root / "models" / "action_claim_verifier_ov"
            if not (candidate / "openvino_model.xml").exists():
                from lucca.core.config import get_config  # noqa: PLC0415

                candidate = get_config().system.root_dir / "models" / "action_claim_verifier_ov"
            self.model_dir = candidate
        else:
            self.model_dir = Path(model_dir)

        self.claim_threshold = claim_threshold
        self._lock = threading.Lock()
        self.available = False
        self.active_device = "NONE"
        self._tokenizer: object = None
        self._infer_req: object = None

        xml_path = self.model_dir / "openvino_model.xml"
        tok_path = self.model_dir / "tokenizer.json"
        if not xml_path.exists() or not tok_path.exists():
            logger.warning(
                "neural_claim_verifier_model_missing",
                model_dir=str(self.model_dir),
            )
            return

        try:
            import openvino as ov  # noqa: PLC0415
            from tokenizers import Tokenizer  # noqa: PLC0415

            tok = Tokenizer.from_file(str(tok_path))
            tok.enable_truncation(max_length=MAX_LEN)
            tok.enable_padding(length=MAX_LEN, pad_id=1, pad_token="<pad>")
            self._tokenizer = tok

            core = ov.Core()
            avail = set(core.available_devices)
            chosen_dev = "CPU"
            for dev in preferred_devices:
                if dev in avail:
                    try:
                        compiled = core.compile_model(str(xml_path), dev)
                        self._infer_req = compiled.create_infer_request()
                        chosen_dev = dev
                        break
                    except Exception as dev_exc:  # noqa: BLE001
                        logger.debug(
                            "neural_claim_verifier_device_fallback",
                            device=dev,
                            error=str(dev_exc),
                        )
            if self._infer_req is None:
                compiled = core.compile_model(str(xml_path), "CPU")
                self._infer_req = compiled.create_infer_request()
                chosen_dev = "CPU"

            self.active_device = chosen_dev
            self.available = True
            logger.info(
                "neural_claim_verifier_ready",
                device=self.active_device,
                model_dir=str(self.model_dir),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neural_claim_verifier_init_failed", error=str(exc))

    @staticmethod
    def format_pair_texts(
        user_context: object,
        completion: str,
        verified_tools: list[str] | None = None,  # noqa: ARG004
    ) -> tuple[str, str]:
        """
        Formats `(user_context, completion_or_clause)` for the 10-class speech-act NPU model.
        Crucially, `verified_tools` is NOT injected into `text_a` — tool grounding is verified
        deterministically in Python per clause so the neural model is 100% invariant to receipt syntax.
        """
        if isinstance(user_context, list):
            valid_msgs = [
                (str(m.get("role", "user")).strip().lower(), str(m.get("content", "")).strip())
                for m in user_context
                if isinstance(m, dict) and str(m.get("content", "")).strip()
            ]
            user_only = [c for r, c in valid_msgs if r == "user"]
            if user_only:
                last_user = user_only[-1]
                # Only include immediately preceding context if the current user turn is an
                # elliptical follow-up (< 6 words, e.g., "Did it work?" or "Are you sure?")
                if len(last_user.split()) < 6 and len(valid_msgs) >= 2:
                    prev_role, prev_text = valid_msgs[-2]
                    prev_words = prev_text.split()
                    if len(prev_words) > 25:
                        prev_text = " ".join(prev_words[-25:])
                    clean_prompt = f"{prev_role}: {prev_text} | user: {last_user}"
                else:
                    clean_prompt = last_user
            else:
                clean_prompt = " | ".join(f"{r}: {c}" for r, c in valid_msgs[-2:]).strip()
        else:
            clean_prompt = str(user_context or "").strip()

        clean_comp = str(completion or "").strip()
        words = clean_comp.split()
        if len(words) > 120:
            clean_comp = " ".join(words[:60]) + " ... " + " ".join(words[-60:])

        text_a = f"User request: {clean_prompt}"
        text_b = f"Assistant reply: {clean_comp}"
        return text_a, text_b

    def _infer_probs(self, user_context: object, text_segment: str) -> np.ndarray:
        text_a, text_b = self.format_pair_texts(user_context=user_context, completion=text_segment)
        enc = self._tokenizer.encode(text_a, text_b)  # type: ignore[attr-defined]
        input_ids = np.array([enc.ids], dtype=np.int64)
        attention_mask = np.array([enc.attention_mask], dtype=np.int64)

        with self._lock:
            res = self._infer_req.infer(  # type: ignore[attr-defined]
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                }
            )
            logits = np.asarray(list(res.values())[0], dtype=np.float64)[0]

        exp_l = np.exp(logits - np.max(logits))
        return exp_l / np.sum(exp_l)

    def evaluate(
        self,
        completion: str,
        user_context: object = None,
        verified_tools: list[str] | None = None,
    ) -> NeuralClaimVerdict:
        clean_comp = (completion or "").strip()
        if not clean_comp or not self.available or self._tokenizer is None or self._infer_req is None:
            return NeuralClaimVerdict(
                predicted_class="BENIGN",
                prob_benign=1.0,
                prob_grounded=0.0,
                prob_ungrounded_claim=0.0,
                prob_unfulfilled_promise=0.0,
                is_ungrounded_claim=False,
                is_unfulfilled_promise=False,
                latency_ms=0.0,
                device="UNAVAILABLE" if not self.available else self.active_device,
            )

        t0 = time.perf_counter()
        tools = [str(t).strip() for t in (verified_tools or []) if str(t).strip()]
        probs_full = self._infer_probs(user_context, clean_comp)

        # Support legacy 4-class model shape if loaded before 10-class export completes
        if probs_full.shape[0] == 4:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            p_benign = float(probs_full[0])
            p_grounded = float(probs_full[1])
            p_ungrounded = float(probs_full[2])
            p_promise = float(probs_full[3])
            pred_cls = CLASS_NAMES[int(np.argmax(probs_full))]
            return NeuralClaimVerdict(
                predicted_class=pred_cls,
                prob_benign=round(p_benign, 4),
                prob_grounded=round(p_grounded, 4),
                prob_ungrounded_claim=round(p_ungrounded, 4),
                prob_unfulfilled_promise=round(p_promise, 4),
                is_ungrounded_claim=bool(p_ungrounded >= self.claim_threshold),
                is_unfulfilled_promise=bool(p_promise >= self.claim_threshold),
                latency_ms=round(elapsed_ms, 2),
                device=self.active_device,
            )

        # 10-Class Neurosymbolic Evaluation
        p_benign_full = float(probs_full[0])
        p_promise_full = float(probs_full[1])
        p_claim_full = float(np.sum(probs_full[2:]))
        top_idx_full = int(np.argmax(probs_full))
        top_cls_full = SPEECH_ACT_CLASSES[top_idx_full]
        top_claim_idx_full = 2 + int(np.argmax(probs_full[2:]))
        top_claim_cls_full = SPEECH_ACT_CLASSES[top_claim_idx_full]

        clauses = split_into_clauses(clean_comp)

        from lucca.sandbox.output_supervisor import is_meta_or_creative_context  # noqa: PLC0415

        is_meta = is_meta_or_creative_context(
            clean_comp, user_context=user_context, full_narration=clean_comp
        )
        has_disclaimer = bool(_CAPABILITY_DISCLAIMER_RE.search(clean_comp))

        # Case 1: No tools executed (`tools == []`)
        if not tools:
            if (is_meta and p_benign_full >= 0.005) or _PSYCHOLOGICAL_OR_CONVERSATIONAL_METAPHOR_RE.search(clean_comp):
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return NeuralClaimVerdict(
                    predicted_class="BENIGN",
                    prob_benign=max(round(p_benign_full, 4), 0.90),
                    prob_grounded=0.0,
                    prob_ungrounded_claim=0.0,
                    prob_unfulfilled_promise=0.0,
                    is_ungrounded_claim=False,
                    is_unfulfilled_promise=False,
                    latency_ms=round(elapsed_ms, 2),
                    device=self.active_device,
                )

            # Check full completion first
            is_combined_breach_claim = (
                not is_meta
                and not has_disclaimer
                and (p_claim_full + p_promise_full) >= 0.58
                and p_claim_full >= 0.20
                and p_claim_full >= p_promise_full
            )
            if (
                not has_disclaimer
                and p_claim_full >= self.claim_threshold
                and top_cls_full in CLAIM_FAMILY_CLASSES
            ) or is_combined_breach_claim:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return NeuralClaimVerdict(
                    predicted_class="UNGROUNDED_CLAIM",
                    prob_benign=round(p_benign_full, 4),
                    prob_grounded=0.0,
                    prob_ungrounded_claim=round(max(p_claim_full, p_claim_full + p_promise_full), 4),
                    prob_unfulfilled_promise=round(p_promise_full, 4),
                    is_ungrounded_claim=True,
                    is_unfulfilled_promise=False,
                    latency_ms=round(elapsed_ms, 2),
                    device=self.active_device,
                    claimed_families=(top_claim_cls_full,),
                    ungrounded_clauses=(clean_comp,),
                )

            # If multi-clause completion predicted BENIGN overall, inspect individual clauses
            # unless the turn is a meta/creative/translation/quoted context or explicit capability refusal
            max_clause_promise_prob = p_promise_full
            if len(clauses) > 1 and not is_meta:
                max_clause_claim_prob = 0.0 if has_disclaimer else p_claim_full
                detected_families: list[str] = []
                bad_clauses: list[str] = []
                for c_text, _ in clauses:
                    if c_text.endswith("?") or c_text.lstrip().startswith(("*", "-", "1.", "2.", "3.")):
                        continue
                    if _CAPABILITY_DISCLAIMER_RE.search(c_text):
                        continue
                    if not _CLAUSE_ACTION_VERB_RE.search(c_text):
                        continue
                    c_probs = self._infer_probs(user_context, c_text)
                    c_claim_p = float(np.sum(c_probs[2:]))
                    c_prom_p = float(c_probs[1])
                    c_top_idx = int(np.argmax(c_probs))
                    c_top_cls = SPEECH_ACT_CLASSES[c_top_idx]
                    if c_top_cls in CLAIM_FAMILY_CLASSES and float(c_probs[c_top_idx]) >= 0.65:
                        max_clause_claim_prob = max(max_clause_claim_prob, c_claim_p)
                        detected_families.append(resolve_clause_claim_family(c_text, c_top_cls))
                        bad_clauses.append(c_text)
                    elif c_top_cls == "UNFULFILLED_PROMISE" and c_prom_p >= 0.75:
                        max_clause_promise_prob = max(max_clause_promise_prob, c_prom_p)

                if bad_clauses:
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    return NeuralClaimVerdict(
                        predicted_class="UNGROUNDED_CLAIM",
                        prob_benign=round(1.0 - max_clause_claim_prob, 4),
                        prob_grounded=0.0,
                        prob_ungrounded_claim=round(max_clause_claim_prob, 4),
                        prob_unfulfilled_promise=round(max_clause_promise_prob, 4),
                        is_ungrounded_claim=True,
                        is_unfulfilled_promise=False,
                        latency_ms=round(elapsed_ms, 2),
                        device=self.active_device,
                        claimed_families=tuple(detected_families),
                        ungrounded_clauses=tuple(bad_clauses),
                    )

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            is_prom = bool(
                top_cls_full == "UNFULFILLED_PROMISE"
                or max_clause_promise_prob >= self.claim_threshold
            )
            return NeuralClaimVerdict(
                predicted_class="UNFULFILLED_PROMISE" if is_prom else "BENIGN",
                prob_benign=round(p_benign_full, 4),
                prob_grounded=0.0,
                prob_ungrounded_claim=round(p_claim_full, 4),
                prob_unfulfilled_promise=round(max_clause_promise_prob, 4),
                is_ungrounded_claim=False,
                is_unfulfilled_promise=is_prom,
                latency_ms=round(elapsed_ms, 2),
                device=self.active_device,
            )

        # Case 2: Tools WERE executed (`len(tools) > 0`)
        # Evaluate each clause to extract all claimed tool families and verify against `tools`
        clause_claims: list[tuple[str, str, bool]] = []
        max_claim_p = p_claim_full
        has_compute_tool = any("python" in t.lower() or "calc" in t.lower() for t in tools)

        def _clause_has_action_or_state_signal(text_seg: str) -> bool:
            return bool(
                _CLAUSE_ACTION_VERB_RE.search(text_seg)
                or _FIRST_PERSON_EXPLICIT_CLAIM_RE.search(text_seg)
                or _PASSIVE_OR_COPULAR_STATE_RE.search(text_seg)
            )

        if len(clauses) == 1:
            is_pure_compute_answer = has_compute_tool and not _clause_has_action_or_state_signal(
                clean_comp
            )
            if not is_pure_compute_answer and (
                p_claim_full >= self.claim_threshold
                or top_cls_full in CLAIM_FAMILY_CLASSES
                or bool(_FIRST_PERSON_EXPLICIT_CLAIM_RE.search(clean_comp))
            ):
                resolved_fam = resolve_clause_claim_family(clean_comp, top_claim_cls_full)
                clause_claims.append((clean_comp, resolved_fam, False))
        else:
            for c_idx, (c_text, is_coord_or_add) in enumerate(clauses):
                if not _clause_has_action_or_state_signal(c_text):
                    continue
                c_probs = self._infer_probs(user_context, c_text)
                c_claim_p = float(np.sum(c_probs[2:]))
                c_top_idx = int(np.argmax(c_probs))
                c_top_cls = SPEECH_ACT_CLASSES[c_top_idx]
                c_top_claim_cls = SPEECH_ACT_CLASSES[2 + int(np.argmax(c_probs[2:]))]
                has_explicit_fp_claim = bool(_FIRST_PERSON_EXPLICIT_CLAIM_RE.search(c_text))
                if (
                    c_top_cls in CLAIM_FAMILY_CLASSES
                    or c_claim_p >= self.claim_threshold
                    or has_explicit_fp_claim
                ):
                    resolved_fam = resolve_clause_claim_family(c_text, c_top_claim_cls)
                    clause_claims.append((c_text, resolved_fam, is_coord_or_add))
                    max_claim_p = max(max_claim_p, c_claim_p if c_claim_p >= 0.50 else 0.85)

            is_pure_compute_multi = has_compute_tool and not _clause_has_action_or_state_signal(
                clean_comp
            )
            if (
                not clause_claims
                and not is_pure_compute_multi
                and (p_claim_full >= self.claim_threshold or top_cls_full in CLAIM_FAMILY_CLASSES)
            ):
                resolved_fam = resolve_clause_claim_family(clean_comp, top_claim_cls_full)
                clause_claims.append((clean_comp, resolved_fam, False))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if not clause_claims:
            return NeuralClaimVerdict(
                predicted_class="BENIGN",
                prob_benign=round(p_benign_full, 4),
                prob_grounded=0.0,
                prob_ungrounded_claim=0.0,
                prob_unfulfilled_promise=round(p_promise_full, 4),
                is_ungrounded_claim=False,
                is_unfulfilled_promise=False,
                latency_ms=round(elapsed_ms, 2),
                device=self.active_device,
            )

        all_grounded, ungrounded_list = verify_clause_claims_against_receipts(clause_claims, tools)
        claimed_fams = tuple(c[1] for c in clause_claims)

        if all_grounded:
            return NeuralClaimVerdict(
                predicted_class="GROUNDED_ACTION",
                prob_benign=round(p_benign_full, 4),
                prob_grounded=round(max(max_claim_p, 0.85), 4),
                prob_ungrounded_claim=0.0,
                prob_unfulfilled_promise=0.0,
                is_ungrounded_claim=False,
                is_unfulfilled_promise=False,
                latency_ms=round(elapsed_ms, 2),
                device=self.active_device,
                claimed_families=claimed_fams,
                ungrounded_clauses=(),
            )

        return NeuralClaimVerdict(
            predicted_class="UNGROUNDED_CLAIM",
            prob_benign=round(p_benign_full, 4),
            prob_grounded=0.0,
            prob_ungrounded_claim=round(max(max_claim_p, 0.85), 4),
            prob_unfulfilled_promise=round(p_promise_full, 4),
            is_ungrounded_claim=True,
            is_unfulfilled_promise=False,
            latency_ms=round(elapsed_ms, 2),
            device=self.active_device,
            claimed_families=claimed_fams,
            ungrounded_clauses=tuple(ungrounded_list),
        )


_SINGLETON_LOCK = threading.Lock()
_SINGLETON_INSTANCE: NeuralActionClaimVerifier | None = None


def get_neural_claim_verifier() -> NeuralActionClaimVerifier:
    global _SINGLETON_INSTANCE
    if _SINGLETON_INSTANCE is None:
        with _SINGLETON_LOCK:
            if _SINGLETON_INSTANCE is None:
                _SINGLETON_INSTANCE = NeuralActionClaimVerifier()
    return _SINGLETON_INSTANCE


def reset_neural_claim_verifier() -> None:
    global _SINGLETON_INSTANCE
    with _SINGLETON_LOCK:
        _SINGLETON_INSTANCE = None
