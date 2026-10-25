"""
Project Lucca — Deterministic Tool Shortlister
WO-24 Phase 2

Reduces the LLM's active tool list from the full 24-tool factory registry down to
a focused subset (≤ 12 tools) per turn based on deterministic intent and entity mapping.
Zero LLM calls, zero VRAM cost, microsecond latency.

When intent is ambiguous or unclassified, falls back to the full 24-tool registry
(safe fallback, zero tool starvation).
"""

from __future__ import annotations

from typing import Final

import structlog

from lucca.core.capabilities import get_default_native_tools

logger = structlog.get_logger(__name__)

# Complete 24-tool category taxonomy (WO-24 Phase 2)
# Every tool in get_default_native_tools() belongs to EXACTLY ONE category.
NATIVE_TOOL_CATEGORIES: Final[dict[str, list[str]]] = {
    "cognitive_core": [
        "calc_math",
        "invoke_skill",
        "memory_commit",
        "memory_search",
        "note_read",
        "note_write",
    ],
    "workspace": [
        "artifact_verify",
        "list_dir",
        "read_file",
        "search_text",
        "write_file",
    ],
    "external_recon": [
        "clipboard_read",
        "fetch_url",
        "search_web",
    ],
    "platform_actuation": [
        "inbox_handoff",
        "launch_app",
        "run_python",
        "run_python_async",
    ],
    "self_introspection": [
        "query_capabilities",
        "self_history_search",
        "self_metrics",
    ],
    "system_schedule": [
        "schedule_event",
        "screenshot_capture",
        "sys_info",
    ],
}

# Intent mapping table: normalized intent token -> category name
_INTENT_CATEGORY_MAP: Final[dict[str, str]] = {
    # external_recon
    "search": "external_recon",
    "research": "external_recon",
    "browse": "external_recon",
    "web": "external_recon",
    "external_recon": "external_recon",
    # workspace
    "code": "workspace",
    "workspace": "workspace",
    "file": "workspace",
    "edit": "workspace",
    "document": "workspace",
    # platform_actuation
    "execute": "platform_actuation",
    "launch": "platform_actuation",
    "run": "platform_actuation",
    "actuation": "platform_actuation",
    "platform_actuation": "platform_actuation",
    # self_introspection
    "self": "self_introspection",
    "status": "self_introspection",
    "introspection": "self_introspection",
    "capability": "self_introspection",
    "capabilities": "self_introspection",
    "metrics": "self_introspection",
    "self_introspection": "self_introspection",
    # system_schedule
    "time": "system_schedule",
    "reminder": "system_schedule",
    "schedule": "system_schedule",
    "screenshot": "system_schedule",
    "vision": "system_schedule",
    "system": "system_schedule",
    "system_schedule": "system_schedule",
}

# Entity keyword mapping table -> category name
_ENTITY_CATEGORY_MAP: Final[dict[str, str]] = {
    "url": "external_recon",
    "web": "external_recon",
    "website": "external_recon",
    "clipboard": "external_recon",
    "file": "workspace",
    "path": "workspace",
    "filepath": "workspace",
    "directory": "workspace",
    "dir": "workspace",
    "artifact": "workspace",
    "app": "platform_actuation",
    "application": "platform_actuation",
    "python": "platform_actuation",
    "script": "platform_actuation",
    "inbox": "platform_actuation",
    "capability": "self_introspection",
    "history": "self_introspection",
    "metrics": "self_introspection",
    "latency": "self_introspection",
    "schedule": "system_schedule",
    "event": "system_schedule",
    "reminder": "system_schedule",
    "screenshot": "system_schedule",
    "screen": "system_schedule",
    "display": "system_schedule",
}


def validate_category_map() -> None:
    """Static validation: asserts every tool in get_default_native_tools()
    appears in exactly one category, and no unknown tools appear.
    """
    native_tools = get_default_native_tools()
    all_mapped: list[str] = []
    seen: set[str] = set()

    for cat, tools in NATIVE_TOOL_CATEGORIES.items():
        for t in tools:
            if t in seen:
                raise ValueError(
                    f"Tool '{t}' appears in multiple categories (seen again in '{cat}')"
                )
            if t not in native_tools:
                raise ValueError(
                    f"Tool '{t}' in category '{cat}' is not in get_default_native_tools()"
                )
            seen.add(t)
            all_mapped.append(t)

    missing = set(native_tools.keys()) - seen
    if missing:
        raise ValueError(f"Tools missing from NATIVE_TOOL_CATEGORIES: {sorted(missing)}")


# Validate at import time so drift cannot occur silently
validate_category_map()


def shortlist_tools(
    intent: str,
    entities: list[str] | None = None,
    force_full: bool = False,
    user_query: str | None = None,
    verifier: object | None = None,
) -> list[str]:
    """Deterministically shortlists active tools for a turn.

    Args:
        intent: The turn intent class string (e.g. 'SEARCH', 'WORKSPACE', 'EXECUTE').
        entities: Optional list of detected entity type or keyword strings.
        force_full: If True, bypass shortlisting and return all 24 tools.
        user_query: Optional user query string to filter by semantic tool fit (WO-36 §36.5).
        verifier: Optional VerifierWorker instance for NLI verification.

    Returns:
        Alphabetically sorted list of tool names.

    Guarantees:
        1. Always includes 'cognitive_core' (memory, notes, calc, invoke_skill) when shortlisting.
        2. Returns ≤ 12 tools for any classified intent (cognitive_core: 6 + task category: 3-5).
        3. If intent is unclassified / ambiguous and no entities match, safely falls back
           to the full 24-tool registry (zero tool starvation).
    """
    all_tools = sorted(get_default_native_tools().keys())
    if force_full:
        return all_tools

    norm_intent = intent.strip().lower() if intent else ""
    target_categories: set[str] = set()

    # 1. Map intent
    if norm_intent in _INTENT_CATEGORY_MAP:
        target_categories.add(_INTENT_CATEGORY_MAP[norm_intent])

    # 2. Map entities if available
    if entities:
        for ent in entities:
            norm_ent = ent.strip().lower()
            if norm_ent in _ENTITY_CATEGORY_MAP:
                target_categories.add(_ENTITY_CATEGORY_MAP[norm_ent])

    # 3. Fallback: if no category could be determined, return full registry
    if not target_categories:
        logger.debug("shortlist_fallback_full_registry", intent=intent)
        return all_tools

    # 4. If more than 1 task category was activated, prioritize the intent category
    # to maintain the hard ≤ 12 tools budget guarantee:
    # cognitive_core (6) + max 1 task category (5) = 11 <= 12 tools.
    task_cat: str
    intent_cat = _INTENT_CATEGORY_MAP.get(norm_intent)
    if intent_cat and intent_cat in target_categories:
        task_cat = intent_cat
    else:
        # Pick the first activated category
        task_cat = sorted(target_categories)[0]

    selected_tools: set[str] = set(NATIVE_TOOL_CATEGORIES["cognitive_core"])
    selected_tools.update(NATIVE_TOOL_CATEGORIES.get(task_cat, []))

    result = sorted(selected_tools)

    # 5. Semantic Tool-Fit Filter (WO-36 §36.5)
    if user_query and user_query.strip():
        fit_tools = [
            t for t in result if check_tool_fit(t, user_query, verifier=verifier)
        ]
        if fit_tools:
            result = fit_tools

    logger.debug(
        "shortlist_computed",
        intent=intent,
        task_category=task_cat,
        tool_count=len(result),
    )
    return result


_TOOL_RELEVANCE_CUES: Final[dict[str, tuple[str, ...]]] = {
    "calc_math": (
        "math", "calculate", "calc", "compute", "sum", "multiply", "divide", "add", "subtract",
        "formula", "equation", "integral", "derivative", "+", "-", "*", "/", "^", "%", "=",
        "arithmetic", "percentage", "ratio",
    ),
    "run_python": (
        "python", "code", "script", "program", "simulate", "algorithm", "plot", "def ",
        "import ", "print(", "dataframe", "numpy", "pandas", "scipy", "itertools", "z3",
        "solve", "sympy", "matrix", "combinatorics", "permutation",
    ),
    "run_python_async": (
        "async", "python", "script", "background", "daemon", "long-running", "simulation",
    ),
    "search_web": (
        "search", "web", "google", "find online", "look up", "online", "internet", "website",
        "news", "weather", "browse", "live info",
    ),
    "fetch_url": (
        "url", "http", "https", "link", "webpage", "download", "fetch", "scrape",
    ),
    "clipboard_read": (
        "clipboard", "paste", "copied", "what is on my clipboard",
    ),
    "read_file": (
        "file", "read", "open", "cat", "view", "lines", "inspect", "contents",
        ".txt", ".py", ".json", ".md", ".csv", ".toml", ".yaml",
    ),
    "write_file": (
        "file", "write", "save", "create", "edit", "update", "modify", "append", "overwrite",
    ),
    "list_dir": (
        "dir", "directory", "list", "ls", "folder", "files", "tree", "subfolder",
    ),
    "search_text": (
        "grep", "search file", "search text", "find in file", "find in files", "search codebase",
    ),
    "artifact_verify": (
        "artifact", "verify", "diff", "patch", "validation",
    ),
    "launch_app": (
        "launch", "app", "open app", "start app", "application", "browser", "notepad", "terminal",
    ),
    "inbox_handoff": (
        "inbox", "handoff", "dispatch", "forward",
    ),
    "query_capabilities": (
        "capability", "capabilities", "what can you do", "skills", "tools",
    ),
    "self_history_search": (
        "history", "past conversation", "prior turn", "earlier turn",
    ),
    "self_metrics": (
        "metrics", "latency", "tokens", "vram", "ram", "cpu", "performance", "stats",
    ),
    "schedule_event": (
        "schedule", "reminder", "alarm", "event", "timer", "calendar",
    ),
    "screenshot_capture": (
        "screenshot", "screen", "display", "capture", "look at my screen", "see what",
    ),
    "sys_info": (
        "sysinfo", "system info", "os", "hardware", "cpu info", "specs", "disk space",
    ),
    "memory_search": (
        "remember", "memory", "recall", "did i say", "did we discuss", "earlier", "past",
        "yesterday", "last week", "told you", "mentioned",
    ),
    "memory_commit": (
        "remember this", "save this to memory", "commit", "don't forget", "note down",
    ),
    "note_read": (
        "note", "notes", "read note",
    ),
    "note_write": (
        "note", "notes", "write note", "take note",
    ),
    "invoke_skill": (
        "skill", "invoke",
    ),
}


def check_tool_fit(
    tool_name: str,
    user_query: str,
    verifier: object | None = None,
) -> bool:
    """Evaluates whether a tool is semantically relevant and fits the user query (WO-36 §36.5).

    Acts as a BFCL <tool_fit_check> guard to eliminate false-triggering on near-miss parameter
    schemas and irrelevant natural language dialogue.

    Args:
        tool_name: Name of native tool to check.
        user_query: The natural language user query.
        verifier: Optional VerifierWorker instance for ModernBERT NLI consistency verification.

    Returns:
        True if the tool is appropriate to expose/call for this query, False if irrelevant.
    """
    native_tools = get_default_native_tools()
    if tool_name not in native_tools:
        return False

    q_clean = user_query.strip()
    if not q_clean:
        return True  # Fail-open for empty or system prompts

    q_lower = q_clean.lower()

    # 1. Semantic NLI Verification via VerifierWorker if present
    if verifier is not None and hasattr(verifier, "check_consistency"):
        tool_def = native_tools.get(tool_name)
        tool_desc = tool_def.description if tool_def is not None else tool_name
        premise = f"Tool '{tool_name}' performs: {tool_desc}"
        hypothesis = f"The user request requires invoking tool '{tool_name}': {q_clean}"
        try:
            res = verifier.check_consistency(premise=premise, hypothesis=hypothesis)
            lbl = getattr(res.label, "value", str(res.label)).lower()
            conf = getattr(res, "confidence", 0.0)
            if "contradiction" in lbl and conf > 0.60:
                logger.info(
                    "tool_fit_rejected_by_verifier",
                    tool=tool_name,
                    confidence=conf,
                    query=q_clean[:80],
                )
                return False
            if ("consistent" in lbl or "entailment" in lbl) and conf >= 0.50:
                return True
        except Exception as v_err:  # noqa: BLE001
            logger.debug("tool_fit_verifier_error", error=str(v_err))

    # 2. Exact tool name mention in query
    if tool_name.lower() in q_lower or tool_name.replace("_", " ") in q_lower:
        return True

    # 3. Domain cue relevance matching
    cues = _TOOL_RELEVANCE_CUES.get(tool_name, ())
    for cue in cues:
        if cue in q_lower:
            return True

    # 4. Entity & category mapping check
    for ent_keyword, cat_name in _ENTITY_CATEGORY_MAP.items():
        if ent_keyword in q_lower:
            if tool_name in NATIVE_TOOL_CATEGORIES.get(cat_name, []):
                return True

    for intent_keyword, cat_name in _INTENT_CATEGORY_MAP.items():
        if intent_keyword in q_lower:
            if tool_name in NATIVE_TOOL_CATEGORIES.get(cat_name, []):
                return True

    # 5. Strict domain filters for specialized tools (BFCL false-trigger guard)
    if tool_name == "calc_math":
        has_digit = any(ch.isdigit() for ch in q_clean)
        has_math_op = any(op in q_clean for op in ("+", "-", "*", "/", "=", "^", "%"))
        has_calc_cue = any(w in q_lower for w in ("calculate", "compute", "evaluate", "math", "sum", "multiply", "divide"))
        return (has_digit and has_math_op) or (has_digit and has_calc_cue)

    if tool_name in ("run_python", "run_python_async"):
        code_cues = ("python", "code", "script", "program", "simulate", "algorithm", "plot", "def ", "import ", "print(", "solve", "sympy", "z3")
        if any(c in q_lower for c in code_cues):
            return True
        qa_cues = ("who wrote", "capital of", "tell me a joke", "how are you", "what is the capital", "meaning of life")
        if any(c in q_lower for c in qa_cues):
            return False

    # 6. Fail-open for active native tools (zero tool starvation per D-ARCH-05 / WO-24)
    return True

