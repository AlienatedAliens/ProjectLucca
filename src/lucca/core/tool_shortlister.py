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
) -> list[str]:
    """Deterministically shortlists active tools for a turn.

    Args:
        intent: The turn intent class string (e.g. 'SEARCH', 'WORKSPACE', 'EXECUTE').
        entities: Optional list of detected entity type or keyword strings.
        force_full: If True, bypass shortlisting and return all 24 tools.

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
    logger.debug(
        "shortlist_computed",
        intent=intent,
        task_category=task_cat,
        tool_count=len(result),
    )
    return result
