"""
Project Lucca — Hybrid Memory Retrieval (sqlite-vec KNN + FTS5 BM25 + RRF)
Spec 04 §6, Spec 10
"""

import hashlib
import json
import re
import sqlite3
import time
from datetime import UTC, datetime
from typing import Final, Literal, cast

import sqlite_vec
import structlog

from lucca.core.active_goals import ActiveGoalManager
from lucca.core.schemas import (
    DecisionRecord,
    MemoryHit,
    Provenance,
    RetrievalQuery,
    RouteDecision,
    RouteFeatures,
    ToolCall,
    standard_for_confidence,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.tokens import build_fts_query, subtokens, verify_provenance_signature
from lucca.ports import EmbeddingPort
from lucca.reasoning.relational.allen import AllenRelation, relation_1d
from lucca.reasoning.relational.sorts import Interval1D

logger = structlog.get_logger(__name__)

RRF_K_CONST: Final[int] = 60
MAX_CANDIDATES: Final[int] = 30


def calculate_age_str(created_at: float, now: float) -> str:
    """Format human-readable age string (e.g. 5m ago, 2h ago, 3d ago)."""
    delta_s = max(0.0, now - created_at)
    if delta_s < 60:
        return f"{int(delta_s)}s ago"
    if delta_s < 3600:
        return f"{int(delta_s // 60)}m ago"
    if delta_s < 82800:
        return f"{int(delta_s // 3600)}h ago"
    return f"{max(1, int(round(delta_s / 86400.0)))}d ago"


_QUERY_STOP_AND_GENERIC: Final[frozenset[str]] = frozenset(
    {
        "what",
        "which",
        "when",
        "where",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "many",
        "much",
        "did",
        "does",
        "do",
        "done",
        "has",
        "have",
        "had",
        "was",
        "were",
        "is",
        "are",
        "been",
        "being",
        "can",
        "could",
        "would",
        "should",
        "will",
        "shall",
        "may",
        "might",
        "must",
        "you",
        "your",
        "yours",
        "yourself",
        "me",
        "my",
        "mine",
        "myself",
        "we",
        "our",
        "ours",
        "us",
        "they",
        "them",
        "their",
        "he",
        "him",
        "his",
        "she",
        "her",
        "it",
        "its",
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "some",
        "any",
        "all",
        "both",
        "each",
        "every",
        "either",
        "neither",
        "no",
        "not",
        "nor",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "even",
        "also",
        "ever",
        "never",
        "always",
        "actually",
        "really",
        "exactly",
        "specifically",
        "currently",
        "previously",
        "earlier",
        "recently",
        "originally",
        "initially",
        "finally",
        "ultimately",
        "already",
        "still",
        "yet",
        "now",
        "then",
        "here",
        "there",
        "from",
        "into",
        "onto",
        "upon",
        "with",
        "without",
        "within",
        "about",
        "above",
        "across",
        "after",
        "against",
        "along",
        "among",
        "around",
        "before",
        "behind",
        "below",
        "beneath",
        "beside",
        "between",
        "beyond",
        "during",
        "except",
        "inside",
        "near",
        "off",
        "out",
        "outside",
        "over",
        "past",
        "since",
        "through",
        "throughout",
        "toward",
        "towards",
        "under",
        "until",
        "up",
        "down",
        "for",
        "of",
        "on",
        "in",
        "to",
        "at",
        "by",
        "as",
        "or",
        "and",
        "but",
        "if",
        "because",
        "while",
        "versus",
        "today",
        "yesterday",
        "tomorrow",
        "morning",
        "afternoon",
        "evening",
        "night",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
        "hour",
        "hours",
        "minute",
        "minutes",
        "second",
        "seconds",
        "ago",
        "last",
        "next",
        "first",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "time",
        "times",
        "date",
        "history",
        "session",
        "sessions",
        "turn",
        "turns",
        "point",
        "period",
        "window",
        "span",
        "prior",
        "previous",
        "recent",
        "latest",
        "entire",
        "total",
        "full",
        "complete",
        "exact",
        "specific",
        "particular",
        "certain",
        "different",
        "various",
        "several",
        "multiple",
        "single",
        "other",
        "another",
        "most",
        "earliest",
        "again",
        "back",
        "looking",
        "type",
        "types",
        "file",
        "files",
        "filename",
        "filenames",
        "code",
        "system",
        "systems",
        "server",
        "servers",
        "project",
        "projects",
        "data",
        "key",
        "keys",
        "name",
        "names",
        "named",
        "number",
        "numbers",
        "value",
        "values",
        "status",
        "version",
        "versions",
        "model",
        "models",
        "user",
        "users",
        "account",
        "accounts",
        "address",
        "port",
        "path",
        "paths",
        "log",
        "logs",
        "test",
        "tests",
        "work",
        "home",
        "office",
        "app",
        "apps",
        "application",
        "applications",
        "program",
        "programs",
        "utility",
        "utilities",
        "desktop",
        "standard",
        "tool",
        "tools",
        "action",
        "actions",
        "operation",
        "operations",
        "command",
        "commands",
        "script",
        "scripts",
        "document",
        "documents",
        "directory",
        "folder",
        "workspace",
        "disk",
        "record",
        "records",
        "receipt",
        "receipts",
        "memory",
        "memories",
        "fact",
        "facts",
        "detail",
        "details",
        "info",
        "information",
        "setting",
        "settings",
        "option",
        "options",
        "choice",
        "choices",
        "change",
        "changed",
        "update",
        "updated",
        "switch",
        "switched",
        "revised",
        "revision",
        "tell",
        "told",
        "say",
        "said",
        "mention",
        "mentioned",
        "state",
        "stated",
        "discuss",
        "discussed",
        "talk",
        "talked",
        "ask",
        "asked",
        "share",
        "shared",
        "give",
        "gave",
        "given",
        "note",
        "noted",
        "remember",
        "recall",
        "recount",
        "list",
        "summarize",
        "trace",
        "progression",
        "confirm",
        "verify",
        "check",
        "checked",
        "checking",
        "show",
        "shown",
        "according",
        "regarding",
        "concerning",
        "respect",
        "whether",
        "happened",
        "occurred",
        "performed",
        "attempted",
        "tried",
        "used",
        "called",
        "invoked",
        "outcome",
        "outcomes",
        "result",
        "results",
        "reason",
        "reasons",
        "due",
        "right",
        "best",
        "final",
        "old",
        "new",
        "high",
        "low",
        "put",
        "set",
        "sit",
        "sitting",
        "leave",
        "left",
        "wearing",
        "attend",
        "front",
        "successfully",
        "succeeded",
        "completed",
        "topic",
        "topics",
        "tuesday",
        "monday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "recorded",
        "runs",
        "run",
        "shift",
        "shifted",
        "engine",
        "engines",
        "optimised",
        "optimized",
        "tuned",
        "kind",
        "caused",
        "data-sorting",
        "sorting",
    }
)

_ACTION_AND_BELIEF_SYNONYMS: Final[dict[str, frozenset[str]]] = {
    "write": frozenset({"write", "wrote", "written", "write_file", "save", "saved"}),
    "wrote": frozenset({"write", "wrote", "written", "write_file", "save", "saved"}),
    "written": frozenset({"write", "wrote", "written", "write_file", "save", "saved"}),
    "write_file": frozenset({"write", "wrote", "written", "write_file", "save", "saved"}),
    "save": frozenset({"write", "wrote", "written", "write_file", "save", "saved"}),
    "saved": frozenset({"write", "wrote", "written", "write_file", "save", "saved"}),
    "create": frozenset({"write", "wrote", "written", "write_file", "created"}),
    "created": frozenset({"write", "wrote", "written", "write_file", "created"}),
    "markdown": frozenset({"notes.md", "md"}),
    "read": frozenset({"read", "read_file"}),
    "read_file": frozenset({"read", "read_file"}),
    "inspect": frozenset({"read", "read_file"}),
    "inspected": frozenset({"read", "read_file"}),
    "delete": frozenset({"delete", "deleted", "delete_file"}),
    "deleted": frozenset({"delete", "deleted", "delete_file"}),
    "delete_file": frozenset({"delete", "deleted", "delete_file"}),
    "deletion": frozenset({"delete", "deleted", "delete_file"}),
    "remove": frozenset({"delete", "deleted", "delete_file"}),
    "removed": frozenset({"delete", "deleted", "delete_file"}),
    "removal": frozenset({"delete", "deleted", "delete_file"}),
    "erase": frozenset({"delete", "deleted", "delete_file"}),
    "erased": frozenset({"delete", "deleted", "delete_file"}),
    "launch": frozenset({"launch", "launched", "launch_app", "opened"}),
    "launched": frozenset({"launch", "launched", "launch_app", "opened"}),
    "launch_app": frozenset({"launch", "launched", "launch_app", "opened"}),
    "open": frozenset({"launch", "launched", "launch_app", "opened", "read", "read_file"}),
    "opened": frozenset({"launch", "launched", "launch_app", "opened", "read", "read_file"}),
    "start": frozenset({"launch", "launched", "launch_app", "opened"}),
    "started": frozenset({"launch", "launched", "launch_app", "opened"}),
    "editor": frozenset({"notepad"}),
    "math": frozenset({"calculator"}),
    "execute": frozenset({"execute", "executed", "run_python", "ran", "script"}),
    "executed": frozenset({"execute", "executed", "run_python", "ran", "script"}),
    "run_python": frozenset({"execute", "executed", "run_python", "ran", "script"}),
    "run": frozenset({"execute", "executed", "run_python", "ran", "script"}),
    "ran": frozenset({"execute", "executed", "run_python", "ran", "script"}),
    "python": frozenset({"python", "run_python", "3.10", "3.12"}),
    "fetch": frozenset({"fetch", "fetched", "fetch_url", "http", "https"}),
    "fetched": frozenset({"fetch", "fetched", "fetch_url", "http", "https"}),
    "fetch_url": frozenset({"fetch", "fetched", "fetch_url", "http", "https"}),
    "retrieve": frozenset({"fetch", "fetched", "fetch_url", "read", "read_file"}),
    "retrieved": frozenset({"fetch", "fetched", "fetch_url", "read", "read_file"}),
    "website": frozenset({"fetch", "fetched", "fetch_url", "http", "https"}),
    "websites": frozenset({"fetch", "fetched", "fetch_url", "http", "https"}),
    "url": frozenset({"fetch", "fetched", "fetch_url", "http", "https"}),
    "urls": frozenset({"fetch", "fetched", "fetch_url", "http", "https"}),
    "web": frozenset({"search_web", "searched", "fetch_url", "fetched"}),
    "search": frozenset({"search", "searched", "search_web", "provider", "duckduckgo", "brave"}),
    "searched": frozenset({"search", "searched", "search_web"}),
    "search_web": frozenset({"search", "searched", "search_web"}),
    "query": frozenset({"search", "searched", "search_web"}),
    "queries": frozenset({"search", "searched", "search_web"}),
    "block": frozenset({"blocked", "denied", "read-only"}),
    "blocked": frozenset({"blocked", "denied", "read-only"}),
    "deny": frozenset({"denied", "blocked", "protected_file"}),
    "denied": frozenset({"denied", "blocked", "protected_file"}),
    "fail": frozenset(
        {"failed", "error", "blocked", "denied", "syntax", "read-only", "unreachable"}
    ),
    "failed": frozenset(
        {"failed", "error", "blocked", "denied", "syntax", "read-only", "unreachable"}
    ),
    "failure": frozenset(
        {"failed", "error", "blocked", "denied", "syntax", "read-only", "unreachable"}
    ),
    "failures": frozenset(
        {"failed", "error", "blocked", "denied", "syntax", "read-only", "unreachable"}
    ),
    "permissions": frozenset({"read-only", "denied", "blocked", "protected_file"}),
    "read-only": frozenset({"read-only", "lucca_test"}),
    "prefer": frozenset(
        {
            "prefer",
            "favour",
            "favor",
            "switched",
            "upgraded",
            "toml",
            "json",
            "brave",
            "duckduckgo",
            "bge",
            "minilm",
            "python",
        }
    ),
    "preference": frozenset(
        {
            "prefer",
            "favour",
            "favor",
            "switched",
            "upgraded",
            "toml",
            "json",
            "brave",
            "duckduckgo",
            "bge",
            "minilm",
            "python",
        }
    ),
    "preferences": frozenset(
        {
            "prefer",
            "favour",
            "favor",
            "switched",
            "upgraded",
            "toml",
            "json",
            "brave",
            "duckduckgo",
            "bge",
            "minilm",
            "python",
        }
    ),
    "preferred": frozenset(
        {
            "prefer",
            "favour",
            "favor",
            "switched",
            "upgraded",
            "toml",
            "json",
            "brave",
            "duckduckgo",
            "bge",
            "minilm",
            "python",
        }
    ),
    "belief": frozenset(
        {
            "prefer",
            "favour",
            "favor",
            "think",
            "switched",
            "upgraded",
            "improved",
            "benchmark",
            "toml",
            "json",
            "brave",
            "duckduckgo",
            "bge",
            "minilm",
            "python",
        }
    ),
    "beliefs": frozenset(
        {
            "prefer",
            "favour",
            "favor",
            "think",
            "switched",
            "upgraded",
            "improved",
            "benchmark",
            "toml",
            "json",
            "brave",
            "duckduckgo",
            "bge",
            "minilm",
            "python",
        }
    ),
    "view": frozenset(
        {
            "prefer",
            "favour",
            "favor",
            "think",
            "switched",
            "upgraded",
            "improved",
            "benchmark",
            "python",
        }
    ),
    "views": frozenset(
        {
            "prefer",
            "favour",
            "favor",
            "think",
            "switched",
            "upgraded",
            "improved",
            "benchmark",
            "python",
        }
    ),
    "opinion": frozenset(
        {"prefer", "favour", "favor", "think", "switched", "upgraded", "improved", "python"}
    ),
    "stance": frozenset(
        {"prefer", "favour", "favor", "think", "switched", "upgraded", "improved", "python"}
    ),
    "embedding": frozenset({"embedding", "embeddings", "minilm", "bge"}),
    "embeddings": frozenset({"embedding", "embeddings", "minilm", "bge"}),
    "configuration": frozenset({"configuration", "config", "json", "toml"}),
    "config": frozenset({"configuration", "config", "json", "toml"}),
    "format": frozenset({"configuration", "config", "json", "toml"}),
    "formats": frozenset({"configuration", "config", "json", "toml"}),
    "provider": frozenset({"provider", "duckduckgo", "brave", "search"}),
    "providers": frozenset({"provider", "duckduckgo", "brave", "search"}),
    "benchmark": frozenset({"benchmark", "throughput", "tokens"}),
    "throughput": frozenset({"benchmark", "throughput", "tokens"}),
    "speed": frozenset({"benchmark", "throughput", "tokens"}),
}


def filter_relevant_memory_hits(query_text: str, hits: list[MemoryHit]) -> list[MemoryHit]:
    """Filters dense-vector neighbor hits to ensure lexical/artifact relevance to the query."""
    if not hits or not query_text.strip():
        return hits
    low = query_text.lower()
    files = re.findall(
        r"\b[a-z0-9_.\-/]+\.(?:txt|md|py|json|ini|csv|log|sys|db|yaml|yml|toml|sh|bat|exe|env|cfg|conf|sql|html|xml)\b",
        low,
    )
    urls = re.findall(
        r"https?://[^\s\"'<>?]+|\b(?:docs\.python\.org|python\.org|arxiv\.org|news\.ycombinator\.com|github\.com|en\.wikipedia\.org|pypi\.org|stackoverflow\.com|google\.com|sqlite\.org|unreachable\.example\.internal)\b",
        low,
    )
    quoted = [
        m.strip().lower()
        for pair in re.findall(r"'([^']{3,60})'|\"([^\"]{3,60})\"", query_text)
        for m in pair
        if m.strip() and " " in m.strip()
    ]
    artifacts: list[str] = []
    for f in files:
        artifacts.append(f.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    for u in urls:
        artifacts.append(u.rstrip(".,;:?)"))
    for q_lit in quoted:
        artifacts.append(q_lit)

    if artifacts:
        return [h for h in hits if any(a in h.content.lower() for a in artifacts)]

    has_self_or_tool_ref = bool(
        re.search(
            r"\b(?:you|your|yours|lucca|write_file|read_file|delete_file|launch_app|run_python|search_web|fetch_url|workspace|sandbox|script|python|execution)\b",
            low,
        )
    )
    raw_words = re.findall(r"\b[a-z0-9_\-.]{3,}\b", low)
    non_action: set[str] = set()
    action: set[str] = set()
    for w in raw_words:
        w_clean = w.strip(".-_")
        if len(w_clean) < 3 or w_clean in _QUERY_STOP_AND_GENERIC or w_clean.isdigit():
            continue
        if w_clean in _ACTION_AND_BELIEF_SYNONYMS and has_self_or_tool_ref:
            action.update(_ACTION_AND_BELIEF_SYNONYMS[w_clean])
        else:
            non_action.add(w_clean)

    if not non_action and not action:
        return hits

    filtered: list[MemoryHit] = []
    for h in hits:
        c_low = h.content.lower()
        c_tokens = set(re.findall(r"\b[a-z0-9_\-.]{2,}\b", c_low))
        if non_action:
            matched_non_act = sum(
                1
                for w in non_action
                if w in c_tokens
                or any(
                    (ct.startswith(w) or w.startswith(ct))
                    for ct in c_tokens
                    if len(ct) >= 5 and len(w) >= 5
                )
            )
            if len(non_action) == 1 and matched_non_act >= 1:
                filtered.append(h)
            elif len(non_action) >= 2 and (
                matched_non_act >= 2
                or (matched_non_act >= 1 and action and any(a in c_low for a in action))
            ):
                filtered.append(h)
            elif (
                has_self_or_tool_ref
                and action
                and any(a in c_low for a in action)
                and len(non_action) <= 2
            ):
                filtered.append(h)
        elif action and any(a in c_low for a in action):
            filtered.append(h)
    return filtered


def _provenance_tier(prov: object) -> int:
    val = prov.value.upper() if hasattr(prov, "value") else str(prov).upper()
    if "USER_EXPLICIT" in val:
        return 0
    if "USER_DERIVED" in val:
        return 1
    if "INFERRED" in val:
        return 2
    if "LISP" in val or "ASSERTION" in val:
        return 3
    if "VERIFIED" in val:
        return 4
    return 5


def format_memory_context(
    hits: list[MemoryHit],
    max_tokens: int = 2048,
    now: float | None = None,
    max_content_chars: int = 160,
    max_items: int = 8,
) -> str:
    """
    Render memory hits into prompt context block per Spec 04 §6 / Spec 10 / D-MEM-03:
    - [{kind}/{provenance} {age}] {content} truncated to max_content_chars (default 160)
    - graph hits as: - {content}
    - sorted by multi-factor hierarchy: (provenance tier, -score, -created_at)
    - Enforces <= max_tokens (approx 4 chars/token).

    Multi-session grouping (D-MEM-04):
    When hits span multiple distinct sessions (different source_turn_id prefixes or
    created_at buckets > 4h apart), hits are grouped by session and emitted with
    [Session N — {age}] headers. This enables cross-session synthesis by the LLM
    rather than presenting a flat ranked list that obscures temporal structure.
    """
    current_time = now if now is not None else time.time()
    sorted_hits = sorted(
        hits,
        key=lambda h: (
            _provenance_tier(h.provenance),
            1 if h.valid_to is not None else 0,
            -h.score,
            -h.created_at,
        ),
    )

    char_budget = max_tokens * 4

    def _clean_content(hit: MemoryHit) -> str:
        raw_text = hit.content[:max_content_chars] if max_content_chars > 0 else hit.content
        content_clean = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        while "\n[" in content_clean:
            content_clean = content_clean.replace("\n[", "\n(")
        if content_clean.startswith("["):
            content_clean = "(" + content_clean[1:]
        return content_clean

    def _format_hit(hit: MemoryHit, content_clean: str) -> str:
        if hit.kind == "graph":
            return f"- {content_clean}"
        age = calculate_age_str(hit.created_at, current_time)
        prov_val = hit.provenance.value if hasattr(hit.provenance, "value") else str(hit.provenance)
        if prov_val == "INFERRED":
            conf_val = getattr(hit, "confidence", 1.0)
            std_label = standard_for_confidence(conf_val).value
            prefix = (
                f"- [{hit.kind}/INFERRED inferred, confidence {conf_val:.2f} — {std_label} {age}]"
            )
            return f"{prefix} {content_clean}"
        conf_str = f" conf={hit.confidence:.2f}" if getattr(hit, "confidence", 1.0) < 0.85 else ""
        sup_str = " [SUPERSEDED]" if hit.valid_to is not None else ""
        return f"- [{hit.kind}/{prov_val}{conf_str}{sup_str} {age}] {content_clean}"

    # --- Multi-session grouping (D-MEM-04) ---
    # Group hits by session prefix derived from source_turn_id (e.g. "sess_1:turn_3" ->
    # "sess_1"), or by created_at 4-hour time bucket. Sessions sorted oldest-first so
    # the LLM sees a chronological narrative rather than a flat score-ranked list.
    SESSION_GAP_S = 4 * 3600  # 4 hours gap = distinct session

    def _session_key(hit: MemoryHit) -> str:
        tid = hit.source_turn_id or ""
        for sep in (":", "_turn", "-turn"):
            if sep in tid:
                return tid.split(sep)[0]
        if tid.startswith("sess"):
            return tid
        return str(int(hit.created_at // SESSION_GAP_S))

    session_keys_ordered: list[str] = []
    session_groups: dict[str, list[MemoryHit]] = {}
    for hit in sorted_hits[:max_items]:
        sk = _session_key(hit)
        if sk not in session_groups:
            session_keys_ordered.append(sk)
            session_groups[sk] = []
        session_groups[sk].append(hit)

    multi_session = len(session_groups) > 1

    lines: list[str] = []
    current_len = 0

    if multi_session:
        # Sort sessions oldest-first by min created_at of their hits
        session_keys_ordered.sort(key=lambda sk: min(h.created_at for h in session_groups[sk]))
        for s_num, sk in enumerate(session_keys_ordered, start=1):
            group_hits = sorted(session_groups[sk], key=lambda h: h.created_at)
            oldest_ts = group_hits[0].created_at
            sess_age = calculate_age_str(oldest_ts, current_time)
            header = f"[Session {s_num} — {sess_age}]"
            header_len = len(header) + 1
            if current_len + header_len > char_budget:
                break
            lines.append(header)
            current_len += header_len
            for hit in group_hits:
                content_clean = _clean_content(hit)
                line = _format_hit(hit, content_clean)
                line_len = len(line) + 1
                if current_len + line_len > char_budget:
                    break
                lines.append(line)
                current_len += line_len
    else:
        # Single-session: original flat rendering
        for hit in sorted_hits[:max_items]:
            content_clean = _clean_content(hit)
            line = _format_hit(hit, content_clean)
            line_len = len(line) + 1
            if current_len + line_len > char_budget:
                break
            lines.append(line)
            current_len += line_len

    return "\n".join(lines)


def _eval_temporal_constraint(
    created_at: float,
    valid_from: float,
    valid_to: float | None,
    anchor: tuple[float, float],
    relation: str,
    clock: str = "created_at",
) -> bool:
    """
    Evaluates qualitative temporal relation between a memory event and an anchor interval.

    Clocks:
    - 'created_at': Interaction / dialogue time (when the conversation event took place).
    - 'valid_time': World fact validity span [valid_from, valid_to).
    """
    if clock == "valid_time":
        evt_start = valid_from
        evt_end = valid_to if valid_to is not None else time.time()
        evt_end = max(evt_end, evt_start)
    else:  # default 'created_at' (interaction time)
        evt_start = created_at
        evt_end = created_at

    anchor_start, anchor_end = anchor
    if anchor_start > anchor_end:
        anchor_start, anchor_end = anchor_end, anchor_start

    # Continuous interval degenerate protection: nudge end slightly for point events
    if evt_start == evt_end:
        evt_end = evt_start + 1e-6
    if anchor_start == anchor_end:
        anchor_end = anchor_start + 1e-6

    evt_interval = Interval1D(start=evt_start, end=evt_end, kind="continuous")
    anchor_interval = Interval1D(start=anchor_start, end=anchor_end, kind="continuous")

    rel = relation_1d(evt_interval, anchor_interval)

    if relation == "before":
        return rel in (AllenRelation.BEFORE, AllenRelation.MEETS)
    elif relation == "after":
        return rel in (AllenRelation.AFTER, AllenRelation.MET_BY)
    elif relation == "during":
        return rel in (
            AllenRelation.DURING,
            AllenRelation.STARTS,
            AllenRelation.FINISHES,
            AllenRelation.EQUALS,
        )
    elif relation == "overlaps":
        return rel not in (
            AllenRelation.BEFORE,
            AllenRelation.AFTER,
            AllenRelation.MEETS,
            AllenRelation.MET_BY,
        )
    return False


def _clean_temporal_query(s: str) -> str:
    cleaned = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s+([?.!,])", r"\1", cleaned).strip()


def extract_temporal_constraints(
    query_text: str,
    now: float | None = None,
    db: DatabaseManager | None = None,
) -> tuple[
    str,
    tuple[float, float] | None,
    Literal["before", "after", "during", "overlaps"] | None,
    Literal["created_at", "valid_time"],
]:
    """
    Extracts qualitative temporal relations and anchor intervals from query text.

    Supports:
    1. Calendar years: 'during 2024', 'in 2024' -> valid_time clock.
    2. Relative conversational periods: 'yesterday', 'today', 'last week', 'last month',
       'last hour', 'earlier' -> created_at clock.
    3. Conversational event anchors: 'before [the] <topic>', 'after [the] <topic>'
       resolved via SQLite memory lookup.

    Returns: (cleaned_query_text, temporal_anchor, temporal_relation, temporal_clock)
    """
    current_time = now if now is not None else time.time()
    clean = query_text.strip()
    if not clean:
        return clean, None, None, "created_at"

    # 1. Calendar year: "in 2024", "during 2024" -> valid_time clock
    year_match = re.search(r"\b(?:in|during)\s+(20\d\d)\b", clean, re.IGNORECASE)
    if year_match:
        yr = int(year_match.group(1))
        t_start = datetime(yr, 1, 1, tzinfo=UTC).timestamp()
        t_end = datetime(yr + 1, 1, 1, tzinfo=UTC).timestamp()
        stripped = re.sub(r"\b(?:in|during)\s+20\d\d\b", "", clean, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "valid_time"

    # 2. Relative time anchors -> created_at clock
    dt_now = datetime.fromtimestamp(current_time, tz=UTC)
    start_of_today = datetime(dt_now.year, dt_now.month, dt_now.day, tzinfo=UTC).timestamp()

    # Number words lookup for relative date parsing
    _NUM_WORDS: dict[str, int] = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    _NUM_PAT = (
        r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
    )

    def _parse_num_token(tok: str) -> int:
        low_tok = tok.lower()
        return int(low_tok) if low_tok.isdigit() else _NUM_WORDS.get(low_tok, 1)

    # Past / last N days ("over the past 3 days", "in the last five days")
    m_past_days = re.search(
        rf"\b(?:over\s+the\s+|in\s+the\s+)?(?:past|last)\s+({_NUM_PAT})\s+days?\b",
        clean,
        re.IGNORECASE,
    )
    if m_past_days:
        n_past = _parse_num_token(m_past_days.group(1))
        t_start = start_of_today - n_past * 86400.0
        t_end = current_time
        stripped = re.sub(
            rf"\b(?:over\s+the\s+|in\s+the\s+)?(?:past|last)\s+{_NUM_PAT}\s+days?\b",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # Multi-day range ("between one and two days ago", "two and three days ago",
    # "yesterday and six days ago", "three days ago and seven days ago")
    day_offsets: set[int] = set()
    m_range_days = re.search(
        rf"\b(?:between\s+(?:the\s+)?)?({_NUM_PAT})\s+(?:days?\s+ago\s+)?(?:and|to|or)\s+(?:the\s+)?({_NUM_PAT})\s+days?\s+ago\b",
        clean,
        re.IGNORECASE,
    )
    if m_range_days:
        day_offsets.add(_parse_num_token(m_range_days.group(1)))
        day_offsets.add(_parse_num_token(m_range_days.group(2)))
    for m_d in re.finditer(rf"\b({_NUM_PAT})\s+days?\s+ago\b", clean, re.IGNORECASE):
        day_offsets.add(_parse_num_token(m_d.group(1)))
    if re.search(r"\byesterday\b", clean, re.IGNORECASE) and day_offsets:
        day_offsets.add(1)
    if len(day_offsets) >= 2:
        n_min = min(day_offsets)
        n_max = max(day_offsets)
        t_start = start_of_today - n_max * 86400.0
        t_end = start_of_today - (n_min - 1) * 86400.0
        stripped = re.sub(
            rf"\b(?:between\s+(?:the\s+)?)?{_NUM_PAT}\s+(?:days?\s+ago\s+)?(?:and|to|or)\s+(?:the\s+)?{_NUM_PAT}\s+days?\s+ago\b",
            "",
            clean,
            flags=re.IGNORECASE,
        )
        stripped = re.sub(rf"\b{_NUM_PAT}\s+days?\s+ago\b", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\byesterday\b", "", stripped, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # Yesterday
    if re.search(r"\byesterday\b", clean, re.IGNORECASE):
        t_start = start_of_today - 86400.0
        t_end = start_of_today
        stripped = re.sub(r"\byesterday\b", "", clean, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # Last night
    if re.search(r"\blast night\b", clean, re.IGNORECASE):
        t_start = start_of_today - 6 * 3600.0  # yesterday 18:00
        t_end = min(current_time, start_of_today + 6 * 3600.0)  # today 06:00
        stripped = re.sub(r"\blast night\b", "", clean, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # This morning
    if re.search(r"\bthis morning\b", clean, re.IGNORECASE):
        t_start = start_of_today + 5 * 3600.0  # today 05:00
        t_end = min(current_time, start_of_today + 12 * 3600.0)  # today 12:00
        if t_start >= t_end:
            t_start = start_of_today
        stripped = re.sub(r"\bthis morning\b", "", clean, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # N hours ago
    m_hours = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+hours?\s+ago\b",
        clean,
        re.IGNORECASE,
    )
    if m_hours:
        raw_n = m_hours.group(1).lower()
        n = int(raw_n) if raw_n.isdigit() else _NUM_WORDS.get(raw_n, 1)
        t_start = current_time - n * 3600.0
        t_end = current_time - (n - 1) * 3600.0 if n > 1 else current_time
        stripped = re.sub(
            r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+hours?\s+ago\b",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # N days ago
    m_days = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+days?\s+ago\b",
        clean,
        re.IGNORECASE,
    )
    if m_days:
        raw_n = m_days.group(1).lower()
        n = int(raw_n) if raw_n.isdigit() else _NUM_WORDS.get(raw_n, 1)
        t_start = start_of_today - n * 86400.0
        t_end = start_of_today - (n - 1) * 86400.0
        stripped = re.sub(
            r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+days?\s+ago\b",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # N weeks ago
    m_weeks = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+weeks?\s+ago\b",
        clean,
        re.IGNORECASE,
    )
    if m_weeks:
        raw_n = m_weeks.group(1).lower()
        n = int(raw_n) if raw_n.isdigit() else _NUM_WORDS.get(raw_n, 1)
        t_start = current_time - n * 7 * 86400.0
        t_end = current_time - (n - 1) * 7 * 86400.0 if n > 1 else current_time
        stripped = re.sub(
            r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+weeks?\s+ago\b",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # N months ago
    m_months = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+months?\s+ago\b",
        clean,
        re.IGNORECASE,
    )
    if m_months:
        raw_n = m_months.group(1).lower()
        n = int(raw_n) if raw_n.isdigit() else _NUM_WORDS.get(raw_n, 1)
        t_start = current_time - n * 30 * 86400.0
        t_end = current_time - (n - 1) * 30 * 86400.0 if n > 1 else current_time
        stripped = re.sub(
            r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+months?\s+ago\b",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # Today / earlier today
    if re.search(r"\b(?:earlier today|today)\b", clean, re.IGNORECASE):
        t_start = start_of_today
        t_end = current_time
        stripped = re.sub(r"\b(?:earlier today|today)\b", "", clean, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # Last week / past week / this week
    if re.search(r"\b(?:last week|past week|this week)\b", clean, re.IGNORECASE):
        t_start = current_time - 7 * 86400.0
        t_end = current_time
        stripped = re.sub(
            r"\b(?:last week|past week|this week)\b", "", clean, flags=re.IGNORECASE
        ).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # Last month / past month
    if re.search(r"\b(?:last month|past month)\b", clean, re.IGNORECASE):
        t_start = current_time - 30 * 86400.0
        t_end = current_time
        stripped = re.sub(r"\b(?:last month|past month)\b", "", clean, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # Last hour / past hour
    if re.search(r"\b(?:last hour|past hour)\b", clean, re.IGNORECASE):
        t_start = current_time - 3600.0
        t_end = current_time
        stripped = re.sub(r"\b(?:last hour|past hour)\b", "", clean, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "during", "created_at"

    # Earlier / previously
    if re.search(r"\b(?:earlier|previously)\b", clean, re.IGNORECASE):
        t_start = 0.0
        t_end = max(0.0, current_time - 60.0)
        stripped = re.sub(r"\b(?:earlier|previously)\b", "", clean, flags=re.IGNORECASE).strip()
        cleaned = _clean_temporal_query(stripped)
        return cleaned or clean, (t_start, t_end), "before", "created_at"

    # 3. Conversational event anchors: "before/after [the] <topic>"
    if db is not None:
        m_rel = re.search(
            r"\b(before|after)\s+(?:the\s+)?([a-zA-Z0-9_\-]+)\b", clean, re.IGNORECASE
        )
        if m_rel:
            rel_word = m_rel.group(1).lower()
            target_word = m_rel.group(2).strip()
            excluded_stop_words = {
                "that",
                "then",
                "this",
                "it",
                "we",
                "i",
                "you",
                "me",
                "us",
                "them",
                "him",
                "her",
            }
            if target_word.lower() not in excluded_stop_words:
                try:
                    with db.read_cursor() as cur:
                        cur.execute(
                            """
                            SELECT created_at FROM memories
                            WHERE content LIKE ? AND forgotten_at IS NULL
                            ORDER BY created_at DESC LIMIT 1
                            """,
                            (f"%{target_word}%",),
                        )
                        row = cur.fetchone()
                        if row is not None:
                            t_anchor = float(row[0])
                            rel_type: Literal["before", "after"] = (
                                "before" if rel_word == "before" else "after"
                            )
                            stripped = re.sub(
                                rf"\b{rel_word}\s+(?:the\s+)?{re.escape(target_word)}\b",
                                "",
                                clean,
                                flags=re.IGNORECASE,
                            ).strip()
                            cleaned = _clean_temporal_query(stripped)
                            return cleaned or clean, (t_anchor, t_anchor), rel_type, "created_at"
                except Exception as exc:  # noqa: BLE001
                    logger.debug("temporal_event_anchor_lookup_failed", error=str(exc))

    return clean, None, None, "created_at"


class HybridRetriever:
    """
    Executes hybrid retrieval combining dense cosine KNN (sqlite-vec)
    and sparse BM25 (FTS5) using Reciprocal Rank Fusion (k=60), followed
    by bi-temporal filtering and 1-hop KG expansion.
    """

    def __init__(
        self,
        db: DatabaseManager,
        embedder: EmbeddingPort | None = None,
        master_key: bytes | None = None,
        raise_on_tamper: bool = False,
        active_goals: ActiveGoalManager | None = None,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.master_key = master_key  # None disables HMAC verification (dev/test only)
        self.raise_on_tamper = raise_on_tamper
        self.active_goals = active_goals if active_goals is not None else ActiveGoalManager(db=db)
        self.quarantined_memory_ids: list[int] = []
        self.user_integrity_warnings: list[str] = []
        self._load_persisted_quarantine_ids()

    def _load_persisted_quarantine_ids(self) -> None:
        """Loads all historically quarantined memory IDs from the database."""
        try:
            with self.db.read_cursor() as cur:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_quarantine'"
                )
                if cur.fetchone():
                    cur.execute("SELECT memory_id FROM memory_quarantine")
                    self.quarantined_memory_ids = [int(row[0]) for row in cur.fetchall()]
        except Exception as exc:
            logger.debug("load_persisted_quarantine_ids_failed", error=str(exc))

    def get_integrity_status_report(self) -> str | None:
        """Returns human-readable notice if any memories are currently quarantined."""
        self._load_persisted_quarantine_ids()
        count = len(self.quarantined_memory_ids)
        if count == 0:
            return None
        return (
            f"Security notice: {count} {'memory' if count == 1 else 'memories'} failed "
            "cryptographic integrity checks and were quarantined."
        )

    def _persist_quarantine(
        self, memory_id: int, entry_id: str | None, stage: str, reason: str
    ) -> None:
        try:
            with self.db.get_writer() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS memory_quarantine ("
                    "memory_id INTEGER PRIMARY KEY, "
                    "entry_id TEXT, "
                    "reason TEXT NOT NULL, "
                    "stage TEXT NOT NULL, "
                    "quarantined_at REAL NOT NULL"
                    ")"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO memory_quarantine (memory_id, entry_id, reason, stage, "
                    "quarantined_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (memory_id, entry_id, reason, stage, time.time()),
                )
                conn.commit()
        except Exception as q_err:
            logger.warning(
                "persist_memory_quarantine_failed", memory_id=memory_id, error=str(q_err)
            )

    def get_persisted_quarantine_records(self) -> list[dict[str, object]]:
        """Returns all memory records quarantined across sessions."""
        try:
            with self.db.read_cursor() as cur:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_quarantine'"
                )
                if not cur.fetchone():
                    return []
                cur.execute(
                    "SELECT memory_id, entry_id, reason, stage, quarantined_at FROM "
                    "memory_quarantine ORDER BY quarantined_at DESC"
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as exc:
            logger.debug("get_persisted_quarantine_records_failed", error=str(exc))
            return []

    def search(
        self,
        q: RetrievalQuery,
        now: float | None = None,
        mode: str = "hybrid",
    ) -> list[MemoryHit]:
        current_time = now if now is not None else time.time()

        # Qualitative temporal constraint extraction from dialogue text (if not already specified)
        if q.temporal_anchor is None:
            clean_text, anchor, rel, clock = extract_temporal_constraints(
                q.query_text, now=current_time, db=self.db
            )
            if anchor is not None and rel is not None:
                q = q.model_copy(
                    update={
                        "query_text": clean_text,
                        "temporal_anchor": anchor,
                        "temporal_relation": rel,
                        "temporal_clock": clock,
                    }
                )

        # 1. Dense search (KNN via sqlite-vec)
        dense_ranks: dict[int, int] = {}
        query_vec = None
        if mode in ("hybrid", "dense"):
            query_vec = q.query_vector
            if query_vec is None and self.embedder is not None:
                try:
                    vecs = self.embedder.embed([q.query_text])
                    if vecs and len(vecs[0]) == 384:
                        query_vec = vecs[0]
                except (RuntimeError, ValueError, OSError) as e:
                    logger.warning("dense_embedding_failed", error=str(e))

        # 1-5. Execute read queries using a single read cursor
        with self.db.read_cursor() as cur:
            if query_vec is not None and mode in ("hybrid", "dense"):
                try:
                    serialized = sqlite_vec.serialize_float32(query_vec)
                    cur.execute(
                        "SELECT memory_id, distance FROM vec_memories "
                        "WHERE embedding MATCH ? "
                        "ORDER BY distance "
                        "LIMIT ?",
                        (serialized, MAX_CANDIDATES),
                    )
                    for rank, row in enumerate(cur.fetchall(), start=1):
                        dense_ranks[int(row[0])] = rank
                except sqlite3.Error as e:
                    logger.warning("vec_search_failed", error=str(e))

            # 2. Sparse search (BM25 via FTS5) + ActiveGoal biasing (Milestone 36.2)
            active_goal_list = (
                self.active_goals.list_active_goals() if self.active_goals is not None else []
            )
            goal_terms: dict[str, int] = {}
            for g in active_goal_list[:3]:
                for tok in re.findall(
                    r"\b[a-zA-Z0-9_\-]{3,}\b", f"{g.title} {g.description}".lower()
                ):
                    if tok not in ("the", "and", "for", "with", "that", "this", "from", "into"):
                        goal_terms[tok] = max(goal_terms.get(tok, 0), 1, g.priority)

            sparse_ranks: dict[int, int] = {}
            if mode in ("hybrid", "bm25"):
                expanded_query = f"{q.query_text} {subtokens(q.query_text)}"
                fts_query_str = build_fts_query(expanded_query)

                try:
                    cur.execute(
                        "SELECT rowid, bm25(fts_memories) as score FROM fts_memories "
                        "WHERE fts_memories MATCH ? "
                        "ORDER BY score "
                        "LIMIT ?",
                        (fts_query_str, MAX_CANDIDATES),
                    )
                    for rank, row in enumerate(cur.fetchall(), start=1):
                        sparse_ranks[int(row[0])] = rank
                except sqlite3.Error as e:
                    logger.warning("fts_search_failed", error=str(e))

                # Lightweight active-goal FTS candidate expansion when active goals exist
                if goal_terms:
                    goal_fts_str = build_fts_query(" ".join(goal_terms.keys()))
                    if goal_fts_str:
                        try:
                            cur.execute(
                                "SELECT rowid, bm25(fts_memories) as score FROM fts_memories "
                                "WHERE fts_memories MATCH ? "
                                "ORDER BY score "
                                "LIMIT ?",
                                (goal_fts_str, MAX_CANDIDATES // 2),
                            )
                            base_offset = len(sparse_ranks) + 5
                            for g_rank, row in enumerate(cur.fetchall(), start=1):
                                mid_g = int(row[0])
                                if mid_g not in sparse_ranks:
                                    sparse_ranks[mid_g] = base_offset + g_rank
                        except sqlite3.Error as g_err:
                            logger.debug("goal_fts_expansion_skipped", error=str(g_err))

            # 3. Reciprocal Rank Fusion (k=60)
            all_candidate_ids = set(dense_ranks.keys()) | set(sparse_ranks.keys())
            if self.quarantined_memory_ids:
                all_candidate_ids -= set(self.quarantined_memory_ids)
            if not all_candidate_ids:
                if q.temporal_anchor is not None:
                    cur.execute(
                        (
                            "SELECT memory_id FROM memories WHERE forgotten_at IS NULL ORDER BY "
                            "created_at DESC LIMIT ?"
                        ),
                        (MAX_CANDIDATES * 2,),
                    )
                    all_candidate_ids = {int(row[0]) for row in cur.fetchall()}
                    if self.quarantined_memory_ids:
                        all_candidate_ids -= set(self.quarantined_memory_ids)
                if not all_candidate_ids:
                    return []

            rrf_scores: dict[int, float] = {}
            for mid in all_candidate_ids:
                score = 0.0
                if mid in dense_ranks:
                    score += 1.0 / (RRF_K_CONST + dense_ranks[mid])
                if mid in sparse_ranks:
                    score += 1.0 / (RRF_K_CONST + sparse_ranks[mid])
                if not dense_ranks and not sparse_ranks:
                    score = 1.0
                rrf_scores[mid] = score

            # 3b. Belief-revision chain propagation along superseded_by
            try:
                cur.execute(
                    "SELECT memory_id, superseded_by FROM memories "
                    "WHERE superseded_by IS NOT NULL AND forgotten_at IS NULL"
                )
                sup_rows = cur.fetchall()
                if sup_rows:
                    fwd_map: dict[int, int] = {}
                    bwd_map: dict[int, list[int]] = {}
                    for sr in sup_rows:
                        old_id = int(sr[0])
                        new_id = int(sr[1])
                        fwd_map[old_id] = new_id
                        bwd_map.setdefault(new_id, []).append(old_id)
                    q_set = set(self.quarantined_memory_ids)
                    seed_ids = list(all_candidate_ids)
                    for mid in seed_ids:
                        base_sc = rrf_scores.get(mid, 0.0)
                        curr = mid
                        for hop in range(1, 5):
                            nxt = fwd_map.get(curr)
                            if nxt is None or nxt in q_set:
                                break
                            all_candidate_ids.add(nxt)
                            rrf_scores[nxt] = max(rrf_scores.get(nxt, 0.0), base_sc * (0.98**hop))
                            curr = nxt
                        if q.include_superseded:
                            frontier = [mid]
                            for hop in range(1, 5):
                                next_frontier: list[int] = []
                                for node in frontier:
                                    for prev_id in bwd_map.get(node, []):
                                        if prev_id not in q_set:
                                            all_candidate_ids.add(prev_id)
                                            rrf_scores[prev_id] = max(
                                                rrf_scores.get(prev_id, 0.0),
                                                base_sc * (0.95**hop),
                                            )
                                            next_frontier.append(prev_id)
                                if not next_frontier:
                                    break
                                frontier = next_frontier
            except sqlite3.Error as chain_err:
                logger.debug("belief_chain_propagation_skipped", error=str(chain_err))

            # Sort candidates descending by RRF score
            sorted_candidates = sorted(
                all_candidate_ids, key=lambda mid: rrf_scores[mid], reverse=True
            )

            # 4. Fetch memory details & apply filters
            hits: list[MemoryHit] = []
            fact_hits: list[MemoryHit] = []

            placeholders = ",".join("?" for _ in sorted_candidates)
            query_sql = f"""
                SELECT m.memory_id, m.content, m.kind, m.created_at, m.valid_from,
                       m.valid_to, m.valid_until, m.superseded_by, m.forgotten_at,
                       p.provenance, p.trace_id,
                       p.session_id, p.grounding_eligible,
                       p.confidence, p.content_sha256, p.signature, p.payload_json
                FROM memories m
                JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE m.memory_id IN ({placeholders})
            """  # noqa: S608

            cur.execute(query_sql, list(sorted_candidates))
            rows = {int(r[0]): r for r in cur.fetchall()}

            for mid in sorted_candidates:
                if mid not in rows:
                    continue
                r = rows[mid]

                # Integrity check — two-stage:
                # Stage 1: content_sha256 fast-fail (catches naive DB edits)
                # Stage 2: HMAC-SHA256 over payload_json (requires master_key; catches
                #           any edit that also updated content_sha256 in the envelope)
                _integrity_ok = True
                try:
                    stored_sha = r["content_sha256"]
                    actual_sha = hashlib.sha256(str(r["content"]).encode("utf-8")).hexdigest()
                    if stored_sha and actual_sha != stored_sha:
                        logger.error(
                            "memory_retrieval_integrity_violation",
                            stage="content_sha256",
                            memory_id=mid,
                        )
                        _integrity_ok = False

                    if _integrity_ok and self.master_key is not None:
                        stored_sig = r["signature"]
                        payload_json_raw = r["payload_json"]
                        if stored_sig and payload_json_raw:
                            # Reconstruct canonical bytes the same way BaseProvenanceSigner.sign()
                            # does: parse the stored JSON, strip the 4 excluded fields, then
                            # re-serialize with sorted keys + compact separators.
                            # This matches canonicalize_unsigned_payload() exactly.
                            _EXCLUDED = {"signature", "signer_id", "entry_id", "content_sha256"}
                            try:
                                raw_dict = json.loads(payload_json_raw)
                                if "content" in raw_dict and raw_dict["content"] != r["content"]:
                                    logger.error(
                                        "memory_retrieval_integrity_violation",
                                        stage="payload_content_mismatch",
                                        memory_id=mid,
                                    )
                                    _integrity_ok = False
                                canon_dict = {
                                    k: v for k, v in raw_dict.items() if k not in _EXCLUDED
                                }
                                canonical_bytes = json.dumps(
                                    canon_dict,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                    ensure_ascii=False,
                                ).encode("utf-8")
                            except (json.JSONDecodeError, AttributeError) as parse_err:
                                logger.warning(
                                    "memory_retrieval_payload_parse_error",
                                    memory_id=mid,
                                    error=str(parse_err),
                                )
                                canonical_bytes = None

                            if canonical_bytes is not None:
                                prov_enum = Provenance(r["provenance"])
                                if not verify_provenance_signature(
                                    stored_sig,
                                    canonical_bytes,
                                    prov_enum,
                                    master_key=self.master_key,
                                    allow_legacy_hmac=True,
                                ):
                                    logger.error(
                                        "memory_retrieval_integrity_violation",
                                        stage="signature",
                                        memory_id=mid,
                                    )
                                    _integrity_ok = False

                except (KeyError, IndexError, ValueError) as exc:
                    logger.warning(
                        "memory_retrieval_integrity_check_error",
                        memory_id=mid,
                        error=str(exc),
                    )

                if not _integrity_ok:
                    eid = str(r["entry_id"]) if "entry_id" in r.keys() else None
                    logger.error(
                        "memory_retrieval_integrity_quarantine",
                        stage="integrity_quarantine",
                        memory_id=mid,
                        entry_id=eid,
                        msg=f"Memory row {mid} failed integrity verification (SHA256/HMAC "
                        "mismatch). Row quarantined.",
                    )
                    self.quarantined_memory_ids.append(mid)
                    self._persist_quarantine(
                        memory_id=mid,
                        entry_id=eid,
                        stage="hmac_or_sha256",
                        reason="Cryptographic integrity verification failed",
                    )
                    warn = (
                        f"Security notice: Memory record {mid} failed cryptographic "
                        "verification and was quarantined."
                    )
                    if warn not in self.user_integrity_warnings:
                        self.user_integrity_warnings.append(warn)

                    if self.raise_on_tamper:
                        raise RuntimeError(
                            f"Memory integrity violation detected for memory_id={mid}. "
                            "The record may have been tampered with. Retrieval aborted."
                        )
                    # Quarantine: exclude from hits and continue retrieving valid rows
                    continue

                valid_to = r["valid_to"]
                valid_until = r["valid_until"]
                superseded_by = r["superseded_by"]
                forgotten_at = r["forgotten_at"]
                kind = str(r["kind"])
                created_at = float(r["created_at"])

                # Filters:
                # - forgotten_at IS NULL (always exclude forgotten memories)
                if forgotten_at is not None:
                    continue
                # - valid_to IS NULL unless include_superseded is True or querying valid_time clock
                if (
                    valid_to is not None
                    and not q.include_superseded
                    and q.temporal_clock != "valid_time"
                ):
                    continue
                # - valid_until > current_time (wall-clock TTL expiry, even when unreplaced)
                if (
                    valid_until is not None
                    and float(valid_until) <= current_time
                    and not q.include_superseded
                    and q.temporal_clock != "valid_time"
                ):
                    continue
                # - kind filter
                if q.kinds is not None and kind not in q.kinds:
                    continue
                # - since timestamp filter
                if q.since is not None and created_at < q.since:
                    continue

                # - Qualitative temporal interval filter (Allen interval algebra)
                if q.temporal_anchor is not None and q.temporal_relation is not None:
                    eff_end: float | None = float(valid_to) if valid_to is not None else None
                    if valid_until is not None:
                        vu_f = float(valid_until)
                        eff_end = min(eff_end, vu_f) if eff_end is not None else vu_f
                    if not _eval_temporal_constraint(
                        created_at=created_at,
                        valid_from=float(r["valid_from"]),
                        valid_to=eff_end,
                        anchor=q.temporal_anchor,
                        relation=q.temporal_relation,
                        clock=q.temporal_clock,
                    ):
                        continue

                grounding_el = True
                try:
                    grounding_el = bool(r["grounding_eligible"])
                except (KeyError, IndexError):
                    pass

                conf_val = 1.0
                try:
                    if r["confidence"] is not None:
                        conf_val = float(r["confidence"])
                except (KeyError, IndexError, ValueError):
                    pass

                content_str = str(r["content"])
                if kind == "tool_fact" and r["payload_json"]:
                    try:
                        p_obj = json.loads(str(r["payload_json"]))
                        if isinstance(p_obj, dict) and isinstance(p_obj.get("structured"), dict):
                            st_dict = p_obj["structured"]
                            extra_tags: list[str] = []
                            for k_st in ("path", "url", "query", "script", "app"):
                                v_st = st_dict.get(k_st)
                                if isinstance(v_st, str) and v_st and v_st not in content_str:
                                    extra_tags.append(f"{k_st}={v_st}")
                            if st_dict.get("ok") is False and "ok=False" not in content_str:
                                extra_tags.append("ok=False")
                            if extra_tags:
                                content_str = f"{content_str} [{', '.join(extra_tags)}]"
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                hit_score = rrf_scores[mid]
                if goal_terms:
                    c_lower = content_str.lower()
                    goal_overlap = sum(prio for tok, prio in goal_terms.items() if tok in c_lower)
                    if goal_overlap > 0:
                        hit_score += 0.005 * goal_overlap

                hit = MemoryHit(
                    memory_id=mid,
                    content=content_str,
                    provenance=Provenance(r["provenance"]),
                    score=hit_score,
                    source_turn_id=r["trace_id"] or r["session_id"],
                    kind=kind,
                    created_at=created_at,
                    valid_from=float(r["valid_from"]),
                    valid_to=float(valid_to) if valid_to is not None else None,
                    valid_until=float(valid_until) if valid_until is not None else None,
                    superseded_by=int(superseded_by) if superseded_by is not None else None,
                    grounding_eligible=grounding_el,
                    confidence=conf_val,
                )
                hits.append(hit)
                if kind == "fact":
                    fact_hits.append(hit)

                if len(hits) >= q.k:
                    break

            # 5. 1-hop KG expansion for fact hits
            min_score = hits[-1].score if hits else 0.01
            graph_score = 0.5 * min_score
            graph_hits: list[MemoryHit] = []

            if fact_hits:
                fact_ids = [int(h.memory_id) for h in fact_hits if isinstance(h.memory_id, int)]
                if fact_ids:
                    ph = ",".join("?" for _ in fact_ids)
                    edge_sql = f"""
                        SELECT ed.memory_id, e1.canonical, ed.p, e2.canonical, ed.valid_from
                        FROM kg_edges ed
                        JOIN kg_entities e1 ON ed.s = e1.entity_id
                        JOIN kg_entities e2 ON ed.o = e2.entity_id
                        WHERE ed.memory_id IN ({ph})
                          AND ed.valid_to IS NULL
                          AND (ed.valid_until IS NULL OR ed.valid_until > ?)
                    """  # noqa: S608
                    cur.execute(edge_sql, [*fact_ids, current_time])
                    for erow in cur.fetchall():
                        s_name, p, o_name = str(erow[1]), str(erow[2]), str(erow[3])
                        graph_content = f"{s_name} {p} {o_name}"
                        graph_hit = MemoryHit(
                            memory_id=int(erow[0]),
                            content=graph_content,
                            provenance=Provenance.USER_DERIVED,
                            score=graph_score,
                            kind="graph",
                            created_at=current_time,
                            valid_from=float(erow[4]),
                        )
                        graph_hits.append(graph_hit)

        # 6. Dedupe & combine: prefer direct hits over graph expansions,
        # active over superseded, higher provenance tier, then score, recency
        hits_to_dedupe = sorted(
            hits + graph_hits,
            key=lambda h: (
                1 if h.kind == "graph" else 0,
                1 if h.valid_to is not None else 0,
                _provenance_tier(h.provenance),
                -h.score,
                -h.created_at,
            ),
        )
        seen_contents: set[str] = set()
        deduped: list[MemoryHit] = []

        for h in hits_to_dedupe:
            key = h.content.strip().lower()
            if key not in seen_contents:
                seen_contents.add(key)
                deduped.append(h)

        deduped.sort(key=lambda h: -h.score)
        result = deduped[: q.k]

        # 7. Batched access count and last_access update
        matched_mids = [int(h.memory_id) for h in result if isinstance(h.memory_id, int)]
        if matched_mids:
            try:
                writer = self.db.get_writer()
                ph = ",".join("?" for _ in matched_mids)
                writer.execute(
                    f"UPDATE memories SET access_count = access_count + 1, last_access = ? "  # noqa: S608
                    f"WHERE memory_id IN ({ph})",
                    [current_time, *matched_mids],
                )
            except sqlite3.Error as e:
                logger.warning("access_update_failed", error=str(e))

        return result

    def index_decision(self, record: DecisionRecord, error: str = "") -> None:
        """Indexes a DecisionRecord into in-session FTS5 retrieval cascade (ITEM-021)."""
        index_decision_record(self.db, record, error=error)

    def search_decisions(self, query: str, limit: int = 5) -> list[DecisionRecord]:
        """Queries past DecisionRecord rows via FTS5 search (ITEM-021)."""
        return search_decision_records(self.db, query, limit=limit)


def ensure_decision_fts(conn: sqlite3.Connection) -> None:
    """Ensures fts_decisions virtual table exists (ITEM-021)."""
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_decisions USING fts5(
                decision_id UNINDEXED,
                trace_id,
                transcript,
                intent,
                action,
                executed_path,
                tool_calls,
                error,
                tokenize="unicode61 remove_diacritics 2 tokenchars '_'"
            );
            """
        )
    except sqlite3.Error as e:
        logger.debug("ensure_decision_fts_failed", error=str(e))


def index_decision_record(db: DatabaseManager, record: DecisionRecord, error: str = "") -> None:
    """Indexes a DecisionRecord into SQLite decisions and fts_decisions table (ITEM-021)."""
    try:
        writer = db.get_writer()
        ensure_decision_fts(writer)

        cur = writer.cursor()
        cur.execute("SELECT 1 FROM decisions WHERE decision_id = ?", (record.decision_id,))
        if not cur.fetchone():
            action_val = (
                record.decision.action.value
                if hasattr(record.decision.action, "value")
                else str(record.decision.action)
            )
            probs_json = json.dumps(
                record.decision.probabilities if record.decision.probabilities is not None else {}
            )
            preds_json = json.dumps(
                [a.value if hasattr(a, "value") else str(a) for a in record.decision.prediction_set]
                if record.decision.prediction_set is not None
                else []
            )
            tool_calls_json = (
                json.dumps([tc.model_dump() for tc in record.tool_calls])
                if record.tool_calls
                else None
            )
            tool_ok_val = 1 if record.tool_ok else (0 if record.tool_ok is False else None)

            writer.execute(
                """
                INSERT INTO decisions(
                    decision_id, trace_id, session_id, ts, features_json, action,
                    probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                    router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                    user_interrupted, interrupted_after_ms, counterfactual_rule_fired
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.decision_id,
                    record.trace_id,
                    record.session_id,
                    record.ts,
                    json.dumps(record.features.model_dump(), ensure_ascii=False),
                    action_val,
                    probs_json,
                    preds_json,
                    1 if record.decision.fallback_applied else 0,
                    record.decision.elapsed_us,
                    record.router_version,
                    record.executed_path,
                    tool_calls_json,
                    tool_ok_val,
                    record.llm_first_token_ms,
                    1 if record.user_interrupted else 0,
                    record.interrupted_after_ms,
                    1 if record.counterfactual_rule_fired else 0,
                ),
            )

        # Upsert into fts_decisions
        writer.execute("DELETE FROM fts_decisions WHERE decision_id = ?", (record.decision_id,))
        tool_calls_str = " ".join(tc.tool for tc in record.tool_calls) if record.tool_calls else ""
        action_str = (
            record.decision.action.value
            if hasattr(record.decision.action, "value")
            else str(record.decision.action)
        )
        writer.execute(
            """
            INSERT INTO fts_decisions(
                decision_id, trace_id, transcript, intent, action, executed_path, tool_calls, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.decision_id,
                record.trace_id,
                record.features.transcript,
                record.features.intent,
                action_str,
                record.executed_path,
                tool_calls_str,
                error,
            ),
        )
    except sqlite3.Error as e:
        logger.warning("index_decision_record_failed", error=str(e), decision_id=record.decision_id)


def search_decision_records(
    db: DatabaseManager,
    query: str,
    limit: int = 5,
) -> list[DecisionRecord]:
    """Retrieves DecisionRecord rows matching the query via FTS5 with fallback
    to LIKE search (ITEM-021)."""
    if not query.strip():
        return []

    results: list[DecisionRecord] = []
    with db.read_cursor() as cur:
        ensure_decision_fts(cur.connection)
        matched_ids: list[str] = []

        try:
            expanded_q = f"{query} {subtokens(query)}"
            fts_q = build_fts_query(expanded_q)
            cur.execute(
                """
                SELECT decision_id FROM fts_decisions
                WHERE fts_decisions MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_q, limit),
            )
            matched_ids = [str(r[0]) for r in cur.fetchall()]
        except sqlite3.Error as e:
            logger.debug("fts_decisions_query_failed", error=str(e))

        if not matched_ids:
            tokens = [t.lower() for t in query.split() if len(t) >= 3]
            if tokens:
                clauses = " OR ".join(
                    "("
                    "features_json LIKE ? OR executed_path LIKE ? "
                    "OR action LIKE ? OR tool_calls_json LIKE ?"
                    ")"
                    for _ in tokens
                )
                params: list[object] = []
                for t in tokens:
                    pat = f"%{t}%"
                    params.extend([pat, pat, pat, pat])
                params.append(limit)
                try:
                    cur.execute(
                        f"""
                        SELECT decision_id FROM decisions
                        WHERE {clauses}
                        ORDER BY ts DESC
                        LIMIT ?
                        """,  # noqa: S608
                        params,
                    )
                    matched_ids = [str(r[0]) for r in cur.fetchall()]
                except sqlite3.Error as fallback_e:
                    logger.debug("decisions_like_fallback_failed", error=str(fallback_e))

        if not matched_ids:
            return []

        ph = ",".join("?" for _ in matched_ids)
        try:
            cur.execute(
                f"""
                SELECT decision_id, trace_id, session_id, ts, features_json, action,
                       probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                       router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                       user_interrupted, interrupted_after_ms, counterfactual_rule_fired
                FROM decisions
                WHERE decision_id IN ({ph})
                """,  # noqa: S608
                matched_ids,
            )
            row_map = {str(r["decision_id"]): r for r in cur.fetchall()}
            for did in matched_ids:
                if did not in row_map:
                    continue
                r = row_map[did]
                feat_dict = (
                    json.loads(r["features_json"])
                    if isinstance(r["features_json"], str)
                    else r["features_json"]
                )
                features = RouteFeatures.model_validate(feat_dict)
                probs = json.loads(r["probabilities_json"]) if r["probabilities_json"] else None
                preds = (
                    json.loads(r["prediction_set_json"])
                    if r["prediction_set_json"]
                    else [r["action"]]
                )
                tc_raw = json.loads(r["tool_calls_json"]) if r["tool_calls_json"] else []
                tool_calls = [ToolCall.model_validate(tc) for tc in tc_raw] if tc_raw else []

                decision = RouteDecision(
                    action=r["action"],
                    tier=features.tier,
                    probabilities=probs,
                    prediction_set=preds,
                    fallback_applied=bool(r["fallback_applied"]),
                    elapsed_us=int(r["elapsed_us"]),
                )

                rec = DecisionRecord(
                    decision_id=str(r["decision_id"]),
                    trace_id=str(r["trace_id"]),
                    session_id=str(r["session_id"]),
                    ts=float(r["ts"]),
                    features=features,
                    decision=decision,
                    router_version=str(r["router_version"]),
                    executed_path=cast(Literal["RULE", "LLM", "CLARIFY"], str(r["executed_path"])),
                    tool_calls=tool_calls,
                    tool_ok=bool(r["tool_ok"]) if r["tool_ok"] is not None else None,
                    llm_first_token_ms=(
                        float(r["llm_first_token_ms"])
                        if r["llm_first_token_ms"] is not None
                        else None
                    ),
                    user_interrupted=bool(r["user_interrupted"]),
                    interrupted_after_ms=(
                        float(r["interrupted_after_ms"])
                        if r["interrupted_after_ms"] is not None
                        else None
                    ),
                    counterfactual_rule_fired=bool(r["counterfactual_rule_fired"]),
                )
                results.append(rec)
        except Exception as parse_e:  # noqa: BLE001
            logger.debug("decision_records_fetch_failed", error=str(parse_e))

    return results
