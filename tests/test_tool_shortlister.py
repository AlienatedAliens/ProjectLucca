"""
Project Lucca — Test Suite for Deterministic Tool Shortlister
WO-24 Phase 2

Validates:
1. Category map completeness (24 tools, exactly 1 category each, no missing/unknown tools)
2. Shortlist size guarantee (≤ 12 tools for all classified intents)
3. Safe fallback to full registry (all 24 tools) on ambiguous intent
4. force_full=True returns all 24 tools
5. prompt_builder.get_all_tool_definitions filtering and non-regression
6. 50-trace synthetic benchmark proving ≥ 95% recall on gold tool sets
7. Wilson score lower bound on recall ≥ 0.90 (95% CI)
"""

from __future__ import annotations

import math
from typing import Final

import pytest

from lucca.brain.prompt_builder import get_all_tool_definitions
from lucca.core.capabilities import MAX_REGISTRY_TOOLS, get_default_native_tools
from lucca.core.tool_shortlister import (
    NATIVE_TOOL_CATEGORIES,
    shortlist_tools,
    validate_category_map,
)


# ---------------------------------------------------------------------------
# 1. Category taxonomy completeness and disjointness
# ---------------------------------------------------------------------------
def test_category_map_exact_partition_of_native_tools() -> None:
    """Every tool in get_default_native_tools() must be in exactly one category."""
    validate_category_map()  # Must not raise

    native_tools = get_default_native_tools()
    assert len(native_tools) == 24
    assert len(native_tools) == MAX_REGISTRY_TOOLS

    all_categorized: list[str] = []
    for cat_name, tools in NATIVE_TOOL_CATEGORIES.items():
        assert len(tools) > 0, f"Category '{cat_name}' is empty"
        all_categorized.extend(tools)

    # Must be 24 total
    assert len(all_categorized) == 24
    # Must have no duplicates
    assert len(set(all_categorized)) == 24
    # Must match the registry tools exactly
    assert set(all_categorized) == set(native_tools.keys())


def test_category_map_expected_memberships() -> None:
    """Verify specific key tools are placed in their normative categories."""
    assert "calc_math" in NATIVE_TOOL_CATEGORIES["cognitive_core"]
    assert "invoke_skill" in NATIVE_TOOL_CATEGORIES["cognitive_core"]
    assert "read_file" in NATIVE_TOOL_CATEGORIES["workspace"]
    assert "artifact_verify" in NATIVE_TOOL_CATEGORIES["workspace"]
    assert "search_web" in NATIVE_TOOL_CATEGORIES["external_recon"]
    assert "clipboard_read" in NATIVE_TOOL_CATEGORIES["external_recon"]
    assert "run_python" in NATIVE_TOOL_CATEGORIES["platform_actuation"]
    assert "inbox_handoff" in NATIVE_TOOL_CATEGORIES["platform_actuation"]
    assert "self_metrics" in NATIVE_TOOL_CATEGORIES["self_introspection"]
    assert "self_history_search" in NATIVE_TOOL_CATEGORIES["self_introspection"]
    assert "schedule_event" in NATIVE_TOOL_CATEGORIES["system_schedule"]
    assert "screenshot_capture" in NATIVE_TOOL_CATEGORIES["system_schedule"]


# ---------------------------------------------------------------------------
# 2. Shortlist size guarantee: ≤ 12 tools for all classified intents
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "intent",
    [
        "SEARCH",
        "RESEARCH",
        "BROWSE",
        "CODE",
        "WORKSPACE",
        "EXECUTE",
        "LAUNCH",
        "SELF",
        "STATUS",
        "TIME",
        "REMINDER",
        "SCREENSHOT",
    ],
)
def test_shortlist_size_bound_classified_intents(intent: str) -> None:
    """For any classified intent, shortlist length must be ≤ 12."""
    tools = shortlist_tools(intent)
    assert len(tools) <= 12, f"Intent '{intent}' produced {len(tools)} tools (> 12)"
    # Must always include all 6 cognitive_core tools
    for core_tool in NATIVE_TOOL_CATEGORIES["cognitive_core"]:
        assert core_tool in tools, f"Missing core tool '{core_tool}' for intent '{intent}'"


# ---------------------------------------------------------------------------
# 3. Fallback to full registry (all 24 tools) on ambiguous / unclassified intent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ambiguous_intent", ["", "UNKNOWN", "gibberish_intent_xyz", "NONE"])
def test_shortlist_fallback_on_unclassified_intent(ambiguous_intent: str) -> None:
    """Ambiguous or unclassified intents safely fall back to the full 24-tool registry."""
    tools = shortlist_tools(ambiguous_intent)
    assert len(tools) == 24
    assert tools == sorted(get_default_native_tools().keys())


def test_shortlist_force_full_override() -> None:
    """force_full=True returns all 24 tools regardless of intent."""
    tools = shortlist_tools("SEARCH", force_full=True)
    assert len(tools) == 24
    assert tools == sorted(get_default_native_tools().keys())


# ---------------------------------------------------------------------------
# 4. Entity-driven category activation
# ---------------------------------------------------------------------------
def test_shortlist_entity_activation() -> None:
    """Entity keywords activate the corresponding task category."""
    # Ambiguous intent, but entity 'filepath' activates workspace
    tools = shortlist_tools("UNKNOWN", entities=["filepath"])
    assert len(tools) <= 12
    assert "read_file" in tools
    assert "write_file" in tools
    assert "calc_math" in tools  # core always present


# ---------------------------------------------------------------------------
# 5. prompt_builder.get_all_tool_definitions integration
# ---------------------------------------------------------------------------
def test_prompt_builder_shortlisting_filter() -> None:
    """get_all_tool_definitions filters when shortlisted_tools is passed."""
    # Test shortlisting filter
    shortlist = ["read_file", "write_file", "calc_math"]
    filtered_defs = get_all_tool_definitions(shortlisted_tools=shortlist)
    assert len(filtered_defs) == 3
    filtered_names = {d.function.name for d in filtered_defs}
    assert filtered_names == set(shortlist)

    # Non-regression test: shortlisted_tools=None returns full 24 definitions
    all_defs = get_all_tool_definitions(shortlisted_tools=None)
    assert len(all_defs) == 24


# ---------------------------------------------------------------------------
# 6. 50-Trace Synthetic Benchmark & Wilson Confidence Lower Bound
# ---------------------------------------------------------------------------
# Synthetic test trace definition: (intent, entities, gold_tool_required)
_SYNTHETIC_50_TRACES: Final[list[tuple[str, list[str], str]]] = [
    # 1-10: Search & Web Recon traces
    ("SEARCH", ["query"], "search_web"),
    ("RESEARCH", ["author"], "search_web"),
    ("BROWSE", ["url"], "fetch_url"),
    ("search", ["website"], "fetch_url"),
    ("RESEARCH", ["clipboard"], "clipboard_read"),
    ("SEARCH", ["text"], "search_web"),
    ("browse", ["article"], "fetch_url"),
    ("search", ["fact"], "search_web"),
    ("EXTERNAL_RECON", ["url"], "fetch_url"),
    ("research", ["reference"], "search_web"),
    # 11-20: Workspace & Code traces
    ("CODE", ["file"], "read_file"),
    ("WORKSPACE", ["path"], "write_file"),
    ("workspace", ["directory"], "list_dir"),
    ("code", ["text"], "search_text"),
    ("WORKSPACE", ["artifact"], "artifact_verify"),
    ("code", ["py"], "read_file"),
    ("workspace", ["src"], "list_dir"),
    ("EDIT", ["file"], "write_file"),
    ("DOCUMENT", ["doc"], "read_file"),
    ("workspace", ["checksum"], "artifact_verify"),
    # 21-30: Execution & Platform Actuation traces
    ("EXECUTE", ["python"], "run_python"),
    ("LAUNCH", ["app"], "launch_app"),
    ("RUN", ["script"], "run_python"),
    ("EXECUTE", ["async"], "run_python_async"),
    ("launch", ["notepad"], "launch_app"),
    ("run", ["code"], "run_python"),
    ("ACTUATION", ["inbox"], "inbox_handoff"),
    ("execute", ["test"], "run_python"),
    ("PLATFORM_ACTUATION", ["application"], "launch_app"),
    ("run", ["batch"], "run_python_async"),
    # 31-40: Self-Introspection & Telemetry traces
    ("SELF", ["capability"], "query_capabilities"),
    ("STATUS", ["metrics"], "self_metrics"),
    ("INTROSPECTION", ["history"], "self_history_search"),
    ("self", ["capabilities"], "query_capabilities"),
    ("status", ["latency"], "self_metrics"),
    ("introspection", ["past"], "self_history_search"),
    ("CAPABILITIES", ["tool"], "query_capabilities"),
    ("METRICS", ["perf"], "self_metrics"),
    ("self", ["action"], "self_history_search"),
    ("SELF_INTROSPECTION", ["status"], "self_metrics"),
    # 41-50: System & Schedule traces
    ("TIME", ["datetime"], "schedule_event"),
    ("REMINDER", ["event"], "schedule_event"),
    ("SCREENSHOT", ["screen"], "screenshot_capture"),
    ("VISION", ["display"], "screenshot_capture"),
    ("SYSTEM", ["hardware"], "sys_info"),
    ("schedule", ["meeting"], "schedule_event"),
    ("screenshot", ["window"], "screenshot_capture"),
    ("system", ["cpu"], "sys_info"),
    ("SYSTEM_SCHEDULE", ["reminder"], "schedule_event"),
    ("time", ["clock"], "sys_info"),
]


def _wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    """Calculates Wilson score lower bound for a binomial confidence interval."""
    if total == 0:
        return 0.0
    p = successes / total
    denom = 1.0 + (z**2) / total
    centre = p + (z**2) / (2 * total)
    spread = z * math.sqrt((p * (1.0 - p) / total) + ((z**2) / (4 * (total**2))))
    return (centre - spread) / denom


def test_50_trace_synthetic_benchmark_recall_and_wilson_gate() -> None:
    """50-trace synthetic benchmark proving ≥ 95% recall and Wilson score LB ≥ 0.90."""
    total_traces = len(_SYNTHETIC_50_TRACES)
    assert total_traces == 50, f"Expected exactly 50 benchmark traces, got {total_traces}"

    successes = 0
    failures: list[str] = []

    for idx, (intent, entities, gold_tool) in enumerate(_SYNTHETIC_50_TRACES):
        shortlist = shortlist_tools(intent=intent, entities=entities)
        # Size invariant: must be <= 12 tools
        assert (
            len(shortlist) <= 12
        ), f"Trace {idx+1} ({intent}) produced {len(shortlist)} tools (> 12)"

        if gold_tool in shortlist:
            successes += 1
        else:
            failures.append(
                f"Trace {idx+1}: intent='{intent}', entities={entities}, gold='{gold_tool}' not in shortlist={shortlist}"
            )

    recall = successes / total_traces
    wilson_lb = _wilson_lower_bound(successes, total_traces, z=1.96)

    assert (
        recall >= 0.95
    ), f"Tool shortlister recall {recall:.2%} < 95% threshold. Failures: {failures}"
    assert (
        wilson_lb >= 0.90
    ), f"Wilson score lower bound {wilson_lb:.4f} < 0.90 threshold (successes={successes}/{total_traces})"
