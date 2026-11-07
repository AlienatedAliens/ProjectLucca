"""
Project Lucca — Output Supervisor Lexicon, Stem Maps and Compiled Regex Constants (WO-43 Phase 3.2)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §2
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

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
    'deleted': 'delete', 'created': 'create', 'modified': 'modify', 'executed': 'execute',
    'ran': 'run', 'installed': 'install', 'removed': 'remove', 'sent': 'send',
    'uploaded': 'upload', 'fetched': 'fetch', 'saved': 'save', 'wrote': 'write',
    'posted': 'post', 'rebooted': 'reboot', 'booked': 'book', 'placed': 'place',
    'processed': 'process', 'started': 'start', 'closed': 'close', 'copied': 'copy',
    'moved': 'move', 'launched': 'launch', 'opened': 'open', 'terminated': 'terminate',
    'archived': 'archive', 'updated': 'update', 'formatted': 'format', 'wiped': 'wipe',
    'pruned': 'prune', 'restarted': 'restart', 'killed': 'kill', 'cleared': 'clear',
    'set': 'set', 'downloaded': 'download', 'purged': 'purge', 'scheduled': 'schedule',
    'committed': 'commit', 'pushed': 'push', 'reset': 'reset', 'renewed': 'renew',
    'cleaned': 'clean', 'scanned': 'scan', 'synced': 'sync', 'configured': 'configure',
    'encrypted': 'encrypt', 'patched': 'patch', 'disabled': 'disable',
    'transferred': 'transfer', 'ordered': 'order', 'loaded': 'load', 'deployed': 'deploy',
    'compiled': 'compile', 'compressed': 'compress', 'extracted': 'extract',
    'mounted': 'mount', 'unmounted': 'unmount', 'revoked': 'revoke', 'granted': 'grant',
    'flashed': 'flash', 'provisioned': 'provision', 'generated': 'generate',
    'applied': 'apply', 'changed': 'change', 'switched': 'switch', 'stored': 'store',
    'rebuilt': 'rebuild', 'released': 'release', 'zipped': 'zip', 'searched': 'search',
    'attached': 'attach', 'published': 'publish', 'dropped': 'drop', 'flushed': 'flush',
    'rotated': 'rotate', 'restored': 'restore', 'stopped': 'stop', 'enabled': 'enable',
    'cloned': 'clone', 'merged': 'merge', 'tagged': 'tag', 'built': 'build',
    'backed': 'backup', 'uninstalled': 'uninstall', 'upgraded': 'upgrade', 'blocked': 'block',
    'unblocked': 'unblock', 'deleting': 'delete', 'creating': 'create', 'modifying': 'modify',
    'executing': 'execute', 'running': 'run', 'installing': 'install', 'removing': 'remove',
    'sending': 'send', 'uploading': 'upload', 'fetching': 'fetch', 'saving': 'save',
    'writing': 'write', 'posting': 'post', 'rebooting': 'reboot', 'booking': 'book',
    'placing': 'place', 'processing': 'process', 'starting': 'start', 'closing': 'close',
    'copying': 'copy', 'moving': 'move', 'launching': 'launch', 'opening': 'open',
    'terminating': 'terminate', 'archiving': 'archive', 'updating': 'update',
    'formatting': 'format', 'wiping': 'wipe', 'pruning': 'prune', 'restarting': 'restart',
    'killing': 'kill', 'clearing': 'clear', 'downloading': 'download', 'purging': 'purge',
    'scheduling': 'schedule', 'committing': 'commit', 'pushing': 'push', 'resetting': 'reset',
    'renewing': 'renew', 'cleaning': 'clean', 'scanning': 'scan', 'syncing': 'sync',
    'configuring': 'configure', 'encrypting': 'encrypt', 'patching': 'patch',
    'disabling': 'disable', 'transferring': 'transfer', 'ordering': 'order', 'loading': 'load',
    'deploying': 'deploy', 'compiling': 'compile', 'compressing': 'compress',
    'extracting': 'extract', 'mounting': 'mount', 'unmounting': 'unmount',
    'revoking': 'revoke', 'granting': 'grant', 'flashing': 'flash',
    'provisioning': 'provision', 'generating': 'generate', 'applying': 'apply',
    'changing': 'change', 'switching': 'switch', 'storing': 'store', 'rebuilding': 'rebuild',
    'releasing': 'release', 'zipping': 'zip', 'searching': 'search', 'attaching': 'attach',
    'publishing': 'publish', 'dropping': 'drop', 'flushing': 'flush', 'rotating': 'rotate',
    'restoring': 'restore', 'stopping': 'stop', 'enabling': 'enable', 'cloning': 'clone',
    'merging': 'merge', 'tagging': 'tag', 'building': 'build', 'backing': 'backup',
    'uninstalling': 'uninstall', 'upgrading': 'upgrade', 'blocking': 'block',
    'unblocking': 'unblock', 'initiated': 'initiate', 'initialized': 'initialize',
    'muted': 'mute', 'unmuted': 'unmute', 'snoozed': 'snooze', 'dimmed': 'dim',
    'renamed': 'rename', 'emptied': 'empty', 'disconnected': 'disconnect',
    'reconnected': 'reconnect', 'muting': 'mute', 'unmuting': 'unmute', 'snoozing': 'snooze',
    'dimming': 'dim', 'renaming': 'rename', 'emptying': 'empty', 'disconnecting': 'disconnect',
    'reconnecting': 'reconnect',
}

COMPANION_BOUND_STEM_MAP: dict[str, str] = {
    'added': 'add', 'adding': 'add', 'noted': 'note', 'noting': 'note', 'brought': 'bring',
    'bringing': 'bring', 'pulled': 'pull', 'pulling': 'pull', 'turned': 'turn',
    'turning': 'turn', 'paused': 'pause', 'pausing': 'pause', 'skipped': 'skip',
    'skipping': 'skip', 'lowered': 'lower', 'lowering': 'lower', 'cancelled': 'cancel',
    'canceled': 'cancel', 'cancelling': 'cancel', 'canceling': 'cancel', 'locked': 'lock',
    'locking': 'lock', 'setting': 'set', 'complete': 'execute', 'inspect': 'read',
}

ALL_ACTION_VERBS: frozenset[str] = frozenset(
    CORE_ACTION_VERBS + EXTENDED_ACTION_VERBS + tuple(EXPANDED_STEM_MAP.values())
)

# Conversational / epistemic meta-targets that do NOT represent external host or
# cloud tool mutations when emitted inside [ACTION: <verb> <target>] frames on
# figurative/idiomatic turns (e.g. "closed the loop" -> [ACTION: MODIFY session_context]).
_CONVERSATIONAL_META_TARGETS_REGEX = re.compile(
    r"^(?:session_context|knowledge_base|discussion_topic|discussion_loop|"
    r"conversation_context|conversation_state|session|mental_note)$",
    re.IGNORECASE,
)

_ILLUSTRATIVE_FRAME_PREFIX_REGEX = re.compile(
    r"\b(?:for\s+example|such\s+as|e\.g\.|i\.e\.|hypothetical(?:ly)?|"
    r"if\s+(?:I|you|we|one)\s+(?:were|had|wanted|needed)|"
    r"(?:would|could|might)\s+(?:emit|output|write|say|use|perform|look\s+like))\b",
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
    r"\b(?:once|when|as\s+soon\s+as)\s+(?:the\s+[\w\-]+|it)\s+(?:is|has(?:\s+been)?|'s)\s+(?:complete|completed|finished|done|started|mounted|ready|terminated|cleared|back\s+up|up\s+to\s+date)\b|"
    r"\bI(?:'ll|\s+will)\s+(?:(?:locate|find)\s+and\s+)?(?:install|upload|archive|compress|extract|mount|unmount|deploy|compile|send|create|delete|remove|update|sync|terminate|kill|reboot|restart|provision|grant|revoke|flash|format|wipe|purge|disable|enable|execute|start\s+the\s+[\w\-]+)\b[^\n!?]*?\b(?:for\s+you\s+now|for\s+you\s+right\s+away|right\s+away|now)\b|"
    r"\bI(?:'ll|\s+will)\s+get\s+(?:those|that|it)\s+(?:"
    + _PAST_VERBS_PATTERN
    + r"|done)\s+for\s+you\s+(?:immediately|now|right\s+away)\b"
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
    rf"(?:(?:identified|located|found|scanned|checked|connected(?:\s+to\s+\S+)?|prepared)\s+(?:and\s+)?)?"
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
    rf"(?:\b(?:I(?:'m|\s+am|\s+have|'ve)?\s+(?:currently\s+|now\s+|just\s+|already\s+)?)?"
    r"(?:initiating|initiated)\s+(?:the\s+|a\s+|an\s+)?(?:immediate\s+)?(?:request\s+to\s+)?"
    r"(reboot|restart|deletion|delete|removal|remove|update|process|backup|migration|"
    r"transmission|send|sending|deployment|deploy|order|ordering|transfer|wipe|purge|"
    r"unmount|mount|archive|execution|execute|termination|terminate|kill|format|"
    r"download|downloading|upload|uploading|sync|synchronization|checkpoint|"
    r"compilation|compile|compression|compress|extraction|extract|provisioning|provision|"
    r"installation|install|creation|create|modification|modify|patch|patching|"
    r"scan|scanning|cleanup|cleaning|clear|clearing|flash|flashing|revocation|revoke|"
    r"grant|encryption|encrypt|rollout|restoration|restore)"
    r"(?:\s+(?:of|for|on|to|process|using)?\s+(.+))?\b|"
    r"^(?:(?:action\s+initiated|operation\s+initiated|deployment\s+initiated|action\s+taken|"
    r"execution\s+summary|summary\s+of\s+operations\s+performed|"
    r"command\s+executed|running\s+command|executing\s+command|running\s+the\s+following\s+command|"
    r"I\s+am\s+running\s*:|executing\s+(?:now|installation|deletion|update|query|provisioning|unmount|compression)|"
    r"status\s*:\s*(?:sent|confirmed|[^\n]*?(?:upload|sync|installation|extraction|compilation)\s+complete|[^\n]*?(?:syncing|downloading|uploading|compiling|deploying))|"
    r"progress\s*:\s*(?:downloading|uploading|compiling|extracting|compressing|syncing|deploying)|"
    r"(?:upload|installation|sync|synchronization|extraction|compilation|mounting|unmounting|deployment|compression|provisioning|revocation|update|backup|migration)\s+(?:complete|completed|successful))\b|"
    rf"(?:{_PARTICIPLE_VERBS_PATTERN}|processing)(?:\s+[a-zA-Z0-9_\-]+){{0,2}}\.{{2,3}})|"
    r"\bI(?:'ve|\s+have)\s+completed\s+the\s+(?:cleanup|installation|migration|backup|deployment|restoration|update|deletion|removal|sync|compilation|extraction|compression)\b|"
    r"\b(?:one\s+moment|please\s+wait(?:\s+a\s+moment)?|please\s+stand\s*by)\s+while\s+I\s+(?:execute|process|run|do|handle|perform)\b)",
    re.IGNORECASE,
)

_PASSIVE_ACTION_REGEX = re.compile(
    rf"^(?:I(?:'ve|\s+have)?\s+(?:confirmed|verified|checked|ensured)\s+that\s+)?(?:(?:the|a|an|your|my|our|all|both)\s+)?([a-zA-Z0-9_\-./\\~`:]+(?:\s+[a-zA-Z0-9_\-./\\~`:]+){{0,7}})\s+"
    rf"(?:was|were|is|are|has\s+been|have\s+been)\s+"
    rf"(?:(?:successfully|now|already|safely|permanently|forcefully|completely|currently|being|no\s+longer)\s+)*"
    rf"(?:[a-z]+ed\s+and\s+)?({_PAST_VERBS_PATTERN}|active\s+and\s+running|underway|ready\s+to\s+use)\b",
    re.IGNORECASE,
)

_TELEGRAPHIC_ACTION_REGEX = re.compile(
    rf"^(?:(?:the|a|an|your|my|our|all)\s+)?([a-zA-Z0-9_\-./\\~`]+(?:\s+[a-zA-Z0-9_\-./\\~`]+){{0,4}})\s+"
    rf"({_PAST_VERBS_PATTERN})(?:\s+(?:successfully|for|to|at|in|on|from|into|now|as\s+requested|tomorrow)[^.!?]*)?[\.!]?$",
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
    r"instances?|servers?|workers?|daemons?|units?|engines?|"
    r"clusters?|namespaces?|stacks?|replicas?|nodes?|pods?|ramdisks?|tmpfs|shares?|"
    r"partitions?|loopbacks?|isos?|firmwares?|certificates?|"
    r"privileges?|permissions?|users?|groups?|environments?|venvs?|libraries?|"
    r"crates?|kernels?|tarballs?|archives?|bundles?|dumps?|checkpoints?|"
    r"records?|rows?|entries|webhooks?|payloads?|channels?|alerts?|"
    r"tags?|remotes?|origins?|interfaces?|eth\d+|wlan\d+|ipv[46]|forwarding|locks?|"
    r"storage|tracks?|audio|changes|commits?|rules?|"
    r"systemctl|postgres(?:ql)?|systemd|journalctl|nginx|apache|redis|sudo|"
    r"excel|chrome|firefox|slack|docker|git|node|python|lsof|kill|"
    r"alarms?|timers?|mics?|microphones?|speakers?|brightness|screens?|night\s+light|"
    r"dark\s+mode|do\s+not\s+disturb|clipboards?|trash(?:\s+can)?|recycle\s+bin|"
    r"vpn|bluetooth|headphones?|calculator|notepad|sticky\s+notes?|"
    r"bookmarks?|lists?|music|songs?|webcams?|cameras?|batter(?:y|ies)|desktops?|"
    r"targets?)\b"
    r")",
    re.IGNORECASE,
)

# --- v3.0 Context-Aware Supervision & Everyday Companion Claim Patterns ---

_META_CREATIVE_USER_PROMPT_REGEX = re.compile(
    r"\b(?:"
    r"(?:write|draft|compose|rewrite|rephrase|paraphrase|create|generate|come\s+up\s+with)\s+(?:a\s+|an\s+|some\s+|the\s+|this\s+|two\s+|three\s+|four\s+|\d+\s+)?(?:[\w-]+\s+){0,4}(?:dialogue|line|monologue|paragraph|novel|story|script|screenplay|scene|poem|haiku|lyrics|email|reply(?:\s+template)?|response\s+template|macro|toast|notifications?|messages?|banner|tooltip|modal\s+copy|microcopy|mockup|wireframe|prototype|commit\s+message|changelog|release\s+notes|status\s+log|status\s+report|sentence|quote)|"
    r"translate\s+(?:this|the\s+following|into)\b|"
    r"how\s+do\s+you\s+say\s+[\"'].+?[\"']\s+in\s+[a-zA-Z]+|"
    r"(?:fix|check|correct|proofread|improve|analyze|explain)\s+(?:the\s+)?(?:grammar|spelling|punctuation|syntax|tense|voice|phrasing|wording|meaning|difference\s+between)\b|"
    r"what\s+does\s+the\s+(?:idiom|phrase|expression)\s+[\"'].+?[\"']\s+mean|"
    r"give\s+(?:me\s+)?(?:one|two|three|four|a\s+few|\d+)?\s*(?:[\w-]+\s+){0,3}(?:example\s+sentences?|notifications?|status\s+messages?|ways\s+to\s+phrase|ways\s+to\s+say)|"
    r"how\s+would\s+(?:a|an)\s+[\w\s-]+?\s+(?:say|phrase|announce|report|respond)\b|"
    r"in\s+(?:a|my)\s+(?:roleplay|rpg|campaign|novel|short\s+story|screenplay|video\s+game|story)\b|"
    r"i'm\s+writing\s+a\s+(?:[\w-]+\s+){0,2}(?:novel|story|script|screenplay|book)|"
    r"repeat\s+(?:this|the\s+following)\s+(?:exact\s+)?(?:phrase|sentence|line|quote|text)\b|"
    r"convert\s+(?:this|the\s+following)\s+sentence\s+(?:from\s+(?:active|passive)(?:\s+voice)?\s+to\s+(?:passive|active)(?:\s+voice)?|into\s+(?:passive|active)\s+voice)|"
    r"(?:create|write|generate|show)\s+a\s+(?:[\w-]+\s+){0,2}(?:json|yaml|xml|toml|sql|csv)\s+(?:snippet|example|payload|object|record)"
    r")\b",
    re.IGNORECASE,
)

_DISCOURSE_ARTIFACT_FRAME_REGEX = re.compile(
    r"(?:"
    r"(?:^|\n)\s*```(?:json|yaml|xml|toml|csv|sql|text|markdown)?\b|"
    r"\bhere\s+are\s+(?:three|two|four|a\s+few|\d+)\s+(?:[\w,-]+\s+){0,4}(?:notifications?|messages?|examples?(?:\s+for\s+you)?|options?|templates?|ways\s+to\s+write\s+that|ways\s+i\s+could\s+say\s+that|ways\s+to\s+phrase\s+that)\b|"
    r"(?:^|\n)\s*(?:#+\s*option\s+\d+|\*\*option\s+\d+)|"
    r"\bthe\s+corrected\s+sentence\s+is\s*:|"
    r"\b(?:that\s+is|you\s+would\s+say|it\s+translates\s+to)\s*:\s*[\"'\*]|"
    r"\bin\s+\*{0,2}active\s+voice\*{0,2}\s*[:(]|\bin\s+\*{0,2}passive\s+voice\*{0,2}\s*[:(]|"
    r"\bthe\s+(?:punctuation|clause|verb|tense|subject|object)\s+(?:here\s+)?(?:works|acts|is\s+used|separates|joins|indicates)\b"
    r")",
    re.IGNORECASE,
)

_LIVE_INSPECTION_ANNOUNCEMENT_REGEX = re.compile(
    r"\b(?:let\s+me|allow\s+me\s+to|i'll|i\s+will)\s+(?:just\s+|quickly\s+|go\s+ahead\s+and\s+)?"
    r"(?:check|look\s+(?:at|in|into|through)|take\s+a\s+(?:quick\s+)?look\s+(?:at|in|into)|"
    r"pull\s+up|scan|inspect|see\s+what(?:'s|\s+is)\s+(?:on|in))\s+"
    r"(?:your|the)\s+(?:[\w-]+\s+){0,2}"
    r"(?:calendar|schedule|meetings?|appointments?|alarms?|timers?|reminders?|"
    r"emails?|inbox|sent\s+(?:folder|items|mail)|messages?|files?|folders?|documents?|"
    r"storage|disk(?:\s+space)?|drive|space|battery|vpn|network|wi-?fi|bluetooth|"
    r"processes?|system|settings?|clipboard|notes?)\b",
    re.IGNORECASE,
)

_CAPABILITY_DISCLAIMER_REGEX = re.compile(
    r"\b(?:cannot|can't|unable\s+to|don't\s+have\s+(?:access|a\s+tool|the\s+ability|permission|any\s+way)|"
    r"do\s+not\s+have\s+(?:access|a\s+tool|the\s+ability|permission|any\s+way)|"
    r"no\s+way\s+to|not\s+able\s+to|cannot\s+directly|can't\s+directly)\b",
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
    r"(?:jotted\s+down|wrote\s+down|logged|recorded)\s+that\s+.+|"
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
    r"setting\s+(?:up\s+)?(?:a|an|the|your)\s+(?:[\w-]+\s+){0,3}(?:timer|alarm|reminder|event|meeting|appointment|wallpaper|background|out-of-office|rule)\b.*|"
    r"(?:pausing|resuming|stopping|skipping|muting|unmuting|shuffling|looping)\s+(?:your|the|this|to\s+the\s+next)\s+(?:music|song|track|playback|audio|podcast|video|player|app|computer\s+speakers?|system\s+audio|speakers?|mic|microphone)\b.*|"
    r"(?:dimming|brightening|lowering|raising|adjusting)\s+(?:your|the)\s+(?:screen|display|monitor|brightness|volume|audio|sound|mic|microphone)\b.*|"
    r"(?:snoozing|cancelling|canceling|dismissing|rescheduling|pushing\s+back)\s+(?:your|the|that)\s+(?:[\w-]+\s+){0,2}(?:alarm|timer|reminder|meeting|call|event|appointment|sync)\b.*|"
    r"(?:locking|unlocking|sleeping)\s+(?:your|the)\s+(?:computer(?:\s+screen)?|screen|display|workstation|pc|laptop|session)\b.*|"
    r"(?:emptying|clearing(?:\s+out)?|cleaning\s+up|flushing)\s+(?:your|the)\s+(?:trash(?:\s+can)?|recycle\s+bin|clipboard|downloads?(?:\s+folder)?|desktop|cache|temp\s+files?|notifications?)\b.*|"
    r"(?:pulling\s+up|bringing\s+up|opening\s+up|closing\s+out(?:\s+of)?|force-closing|force-quitting|quitting|minimizing|maximizing|pinning|unpinning|ejecting|disconnecting|reconnecting|pairing|re-pairing)\s+(?:your|the|all\s+of\s+your)\s+(?:[\w-]+\s+){0,3}(?:notes?|sticky\s+notes?|calendar|reminders?|bookmarks?|tabs?|windows?|apps?|applications?|programs?|clients?|players?|chats?|browser|calculator|notepad|bluetooth|headphones?|headsets?|devices?|drive|usb|vpn|wifi|wi-fi)\b.*|"
    r"(?:taking|snapping|capturing)\s+a\s+screenshot\b.*|"
    r"(?:jotting|writing|noting)\s+(?:that|this)\s+down\b.*|"
    r"sending\s+(?:that|it|the\s+[\w\s]+)\s+now\b"
    r")|"
    # 3. Copular state-of-completion & anaphoric passive companion claims
    r"\b(?:(?:calculator|notepad|browser|terminal|player|sticky\s+notes?)(?:\s+and\s+(?:calculator|notepad|browser|terminal|player|sticky\s+notes?))?|night\s+light(?:\s+mode)?|do\s+not\s+disturb(?:\s+mode)?|dark\s+mode|light\s+mode|focus\s+mode|airplane\s+mode|battery\s+saver(?:\s+mode)?|sleep\s+mode|wi-?fi|bluetooth|vpn|hotspot|your\s+(?:[\w-]+\s+){0,2}(?:screen|display|monitor|computer|laptop|workstation|microphone|mic|speakers?|audio|sound|volume|brightness|alarm|timer|reminder|meeting|call|appointment|calendar|clipboard|recycle\s+bin|trash(?:\s+can)?|downloads?(?:\s+folder)?|desktop|vpn|bluetooth|wi-?fi|hotspot|headphones?|headset|devices?|usb\s+(?:[\w-]+\s+)?drive|external\s+drive|drive|webcam|camera|music|playback|wallpaper|background|notifications?|tabs?|windows?|apps?|applications?|programs?|players?|clients?))\s+(?:is|are|has\s+been|have\s+been)\s+(?:now\s+|all\s+|already\s+|successfully\s+|safely\s+)*(?:open(?:ed)?|closed|quit|minimized|maximized|pinned|unpinned|empty|emptied|clear|cleared|cleaned\s+up|sorted|organized|flushed|muted|unmuted|on|off|set(?:\s+for\s+[\w\s:]+|\s+to\s+[\w\s%]+)?|scheduled(?:\s+for\s+[\w\s:]+)?|rescheduled(?:\s+to\s+[\w\s:]+|\s+for\s+[\w\s:]+)?|pushed\s+back(?:\s+to\s+[\w\s:]+)?|paused|resumed|stopped|skipped|locked|unlocked|asleep|connected|disconnected|paired|unpaired|ejected|safe\s+to\s+remove|disabled|enabled|activated|deactivated|dimmed|brightened|lowered|raised|at\s+\d+%|snoozed|cancelled|canceled|dismissed|saved|bookmarked|backed\s+up|restored)\b|"
    r"\b(?:they've|they\s+have|they're|they\s+are|it's|it\s+has|it\s+is|that's|that\s+has|that\s+is|both\s+have|all\s+(?:of\s+)?(?:those|them|your)\s+[\w\s-]{0,25}?)\s+(?:been\s+|now\s+|all\s+|already\s+|safely\s+)+(?:added\s+to\s+your\s+(?:[\w\s-]*?(?:list|notes?|calendar|reminders?|bookmarks?|favorites?|queue|playlist|contacts?))|saved\s+(?:to|in)\s+your\s+[\w\s-]*?(?:bookmarks?|favorites?|folder|notes?|desktop|documents?|clipboard)|cleared\s+(?:off|from)\s+your\s+(?:desktop|screen|clipboard|downloads?|list)|moved\s+(?:to|into)\s+your\s+[\w\s-]+|deleted\s+from\s+your\s+[\w\s-]+|copied\s+to\s+your\s+clipboard|ejected(?:\s+safely)?|taken\s+care\s+of|pushed\s+back\s+to\s+[\w\s:]+|rescheduled\s+(?:to|for)\s+[\w\s:]+|named\s+(?:[`'\"][a-zA-Z0-9_.-]+[`'\"]|[a-zA-Z0-9_-]+\.[a-zA-Z0-9]{2,5})\b)|"
    r"\b(?:[`'\"]?[a-zA-Z0-9_.-]+\.(?:xlsx|pdf|docx|txt|csv|png|jpg|zip)[`'\"]?|the\s+(?:[\w-]+\s+){0,3}(?:pdfs?|files?|photos?|pictures?|screenshots?|documents?|spreadsheets?|links?|urls?|passwords?|codes?|snippets?|notes?|items?|songs?|tracks?|emails?|messages?|folders?|archives?))\s+(?:is|are|has\s+been|have\s+been)\s+now\s+(?:on\s+your\s+clipboard|in\s+your\s+[\w\s-]+?(?:folder|directory|trash|recycle\s+bin|list|bookmarks?|notes?|archive)|saved\s+(?:to|in)\s+your\s+[\w\s-]+|pinned(?:\s+to\s+your\s+[\w\s-]+)?)\b|"
    r"^(?:(?:sure\s+thing|okay|got\s+it|done|all\s+set|no\s+problem|right\s+away)[.!,\s—\-]+)?(?:sleep\s+mode\s+(?:is\s+)?(?:activated|enabled|on)|focus\s+mode\s+(?:is\s+)?(?:activated|enabled|on)|airplane\s+mode\s+(?:is\s+)?(?:activated|enabled|on)|battery\s+saver\s+(?:is\s+)?(?:activated|enabled|on)|music\s+(?:is\s+)?paused|playback\s+(?:is\s+)?paused|audio\s+(?:is\s+)?muted|mic(?:rophone)?\s+(?:is\s+)?muted|screen\s+(?:is\s+)?(?:locked|dimmed)|clipboard\s+(?:is\s+)?cleared|trash\s+(?:is\s+)?emptied|recycle\s+bin\s+(?:is\s+)?emptied|alarm\s+(?:is\s+)?set\s+for\s+\d+|timer\s+(?:is\s+)?set\s+for\s+\d+|reminder\s+(?:is\s+)?set\s+for\s+[\w\s:]+)\b"
    r")",
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
        has_real_exec_suffix = bool(
            re.search(
                r"\band\s+(?:send|execute|run|delete|remove|install|deploy|save)\s+(?:it|them|that)\b",
                full_user_text,
                re.IGNORECASE,
            )
        )
        if not has_real_exec_suffix and _META_CREATIVE_USER_PROMPT_REGEX.search(full_user_text):
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


def is_simulated_inspection_readout(
    clause: str,
    full_narration: str | None = None,
) -> bool:
    """
    Detects single-turn simulated live inspection followed immediately by a fabricated
    readout in the same response (e.g. "Let me check your schedule. Yep, you have a meeting...",
    "Let me check your storage. Okay, it looks like you have...") without a capability disclaimer.
    """
    if not full_narration:
        return False
    narration_text = full_narration.strip()
    m_ann = _LIVE_INSPECTION_ANNOUNCEMENT_REGEX.search(narration_text)
    if not m_ann:
        return False
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", narration_text) if s.strip()]
    if len(sentences) < 2:
        return False
    ann_idx = -1
    for idx, s in enumerate(sentences):
        if _LIVE_INSPECTION_ANNOUNCEMENT_REGEX.search(s):
            ann_idx = idx
            break
    if ann_idx == -1 or ann_idx >= len(sentences) - 1:
        return False
    readout_sentences = [
        s
        for s in sentences[ann_idx + 1 :]
        if not s.endswith("?")
        and not re.match(
            r"^(?:\.+|(?:(?:give\s+me\s+)?(?:just\s+)?(?:a|one)\s+(?:moment|second|sec|minute)|hold\s+on|hang\s+on|checking(?:\s+now)?)[.!]*)$",
            s.strip(),
            re.IGNORECASE,
        )
    ]
    if not readout_sentences:
        return False
    subsequent_text = " ".join(readout_sentences)
    if _CAPABILITY_DISCLAIMER_REGEX.search(subsequent_text):
        return False
    return bool(_LIVE_INSPECTION_ANNOUNCEMENT_REGEX.search(clause))


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
    r"placed\s+(?:(?:an?\s+)?(?:emphasis|focus|priority|trust|faith|bets?|confidence|blame)\s+(?:on|in)|(?:my|our|their|his|her)\s+(?:trust|faith|emphasis|focus|confidence)\s+(?:on|in))"
    r")\b",
    re.IGNORECASE,
)

HEDGE_PATTERN = re.compile(
    r"\b(?:I\s+think\s+I|I\s+believe\s+I|I\s+(?:may|might|could)\s+have|"
    r"not\s+sure\s+(?:if|whether)|not\s+certain\s+(?:if|whether)|"
    r"(?:can\'t|cannot)\s+tell\s+(?:you\s+)?(?:if|whether)|"
    r"(?:don\'t|do\s+not)\s+know\s+(?:if|whether)|"
    r"perhaps\s+I|maybe\s+I)\b",
    re.IGNORECASE,
)
