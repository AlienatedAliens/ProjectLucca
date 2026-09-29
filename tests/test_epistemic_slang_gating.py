"""
Project Lucca — Epistemic Slang Gating, Grounded Telemetry & Entity Filtering Tests
WO-26 Phase 3 Acceptance Suite
Tests:
1. Conformal uncertainty gating on unfamiliar cultural/culinary slang vs reflex confabulation.
2. Sibling tests on Australian, British, and American regional dialect terms.
3. Strict conversational negative controls (small talk, companion identity, capabilities).
4. Deterministic zoneinfo timezone resolution (Perth/AWST, Melbourne/AEST, Manila/PST, Singapore).
5. Sub-5ms Class B SLA verification for offline zoneinfo telemetry.
6. Target entity word-boundary snippet filtering (including substring Beverly vs ever).
7. Cascade web search fallback integration.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from lucca.core.cascade import (
    BelnapValue,
    EpistemicSearchCascade,
    EpistemicSubstrate,
    EvidenceItem,
    TrustTier,
    _extract_target_entity,
    classify_epistemic_intent,
    matches_slang_or_world_definition,
)
from lucca.core.schemas import ToolResult
from lucca.sandbox.schemas import SearchWebArgs, SysInfoArgs
from lucca.sandbox.search_tool import search_web
from lucca.sandbox.service import SandboxService, resolve_target_timezone


# ============================================================================
# 1. Conformal Slang & Regional Dialect Gating
# ============================================================================


def test_australian_slang_forces_web_substrate() -> None:
    """Verifies Australian slang terms ('flake', 'witchetty grub') route to WEB substrate."""
    cases = [
        "What is flake in Australia?",
        "What is a witchetty grub?",
        "What does bludger mean in Australia?",
        "Tell me what a chiko roll is in Australia",
        "Australian slang for food",
    ]
    for q in cases:
        is_ep, subs, topic = classify_epistemic_intent(q)
        assert is_ep is True, f"Expected epistemic query for '{q}'"
        assert EpistemicSubstrate.WEB in subs, f"Expected WEB substrate in {subs} for '{q}'"


def test_regional_dialect_siblings_force_web_substrate() -> None:
    """
    Sibling tests: British ('pasty barm'), American ('chopped cheese'),
    and Scottish/regional terms force WEB search rather than reflex confabulation.
    """
    cases = [
        "What is a pasty barm?",
        "What is chopped cheese in New York?",
        "British slang for drunk",
        "What is bubble and squeak?",
        "What does scran mean in the UK?",
    ]
    for q in cases:
        is_ep, subs, topic = classify_epistemic_intent(q)
        assert is_ep is True, f"Expected epistemic query for '{q}'"
        assert EpistemicSubstrate.WEB in subs, f"Expected WEB substrate in {subs} for '{q}'"


def test_conversational_negative_controls_do_not_trigger_web_search() -> None:
    """
    TRAP 2: Everyday conversational chat and non-slang queries MUST NOT
    falsely trigger WEB search.
    """
    pure_conversational = [
        "How are you doing today?",
        "how are you?",
        "Hello",
        "good morning",
        "thank you",
        "Tell me a joke",
        "Write a poem about autumn",
        "What is 15 * 24?",
    ]
    for utt in pure_conversational:
        is_ep, subs, _ = classify_epistemic_intent(utt)
        assert EpistemicSubstrate.WEB not in subs, f"Utterance '{utt}' falsely routed to WEB"

    # Self and capability inquiries must route to SELF or CAPABILITIES, never WEB
    companion_queries = [
        ("What is your name?", EpistemicSubstrate.SELF),
        ("Who built you?", EpistemicSubstrate.SELF),
        ("What tools do you have?", EpistemicSubstrate.CAPABILITIES),
        ("What can you do?", EpistemicSubstrate.CAPABILITIES),
    ]
    for q, expected_sub in companion_queries:
        is_ep, subs, _ = classify_epistemic_intent(q)
        assert is_ep is True
        assert expected_sub in subs
        assert EpistemicSubstrate.WEB not in subs, f"Query '{q}' falsely routed to WEB"


def test_extract_target_entity_utility() -> None:
    """Verifies target entity extraction from definitional queries."""
    assert _extract_target_entity("What is flake in Australia?") == "flake"
    assert _extract_target_entity("What is a witchetty grub?") == "witchetty grub"
    assert _extract_target_entity("What is a pasty barm?") == "pasty barm"
    assert _extract_target_entity("slang for police") == "police"
    assert _extract_target_entity("How are you doing today?") is None


# ============================================================================
# 2. Grounded Telemetry & zoneinfo Timezone Resolution
# ============================================================================


def test_timezone_queries_route_to_telemetry_substrate() -> None:
    """Verifies timezone inquiries route to TELEMETRY substrate."""
    tz_queries = [
        "What time is it in Perth?",
        "What is the timezone of Melbourne?",
        "Is Manila currently in daylight saving time?",
        "What is the UTC offset for Singapore?",
        "What timezone is AWST?",
        "What is the current time in London?",
    ]
    for q in tz_queries:
        is_ep, subs, _ = classify_epistemic_intent(q)
        assert is_ep is True, f"Expected epistemic for '{q}'"
        assert EpistemicSubstrate.TELEMETRY in subs, f"Expected TELEMETRY in {subs} for '{q}'"
        assert EpistemicSubstrate.WEB not in subs, f"Timezone query '{q}' should not route to WEB"


def test_resolve_target_timezone_offline_mapping() -> None:
    """
    Verifies resolve_target_timezone resolves IANA names and regional aliases
    (Perth, Melbourne, Manila, Singapore, Tokyo, New York) accurately.
    """
    assert resolve_target_timezone("Australia/Perth") is not None
    assert resolve_target_timezone("Perth").key == "Australia/Perth"
    assert resolve_target_timezone("AWST").key == "Australia/Perth"
    assert resolve_target_timezone("Melbourne").key == "Australia/Melbourne"
    assert resolve_target_timezone("AEST").key == "Australia/Melbourne"
    assert resolve_target_timezone("Manila").key == "Asia/Manila"
    assert resolve_target_timezone("Singapore").key in ("Singapore", "Asia/Singapore")
    assert resolve_target_timezone("New York").key == "America/New_York"
    assert resolve_target_timezone("nonexistent_fake_city") is None


def test_sys_info_zoneinfo_fields() -> None:
    """
    Verifies sys_info outputs iana_name, abbreviation, utc_offset, is_dst, and local_time.
    """
    sandbox_service = SandboxService()
    # 1. Query Perth timezone
    res_perth = sandbox_service.execute_tool("c-perth", "sys_info", {"timezone": "Perth"})
    assert res_perth.ok is True
    assert res_perth.structured.get("iana_name") == "Australia/Perth"
    assert res_perth.structured.get("abbreviation") == "AWST"
    assert res_perth.structured.get("utc_offset") == "+0800"
    assert res_perth.structured.get("is_dst") is False
    assert "local_time" in res_perth.structured

    # 2. Query Manila timezone
    res_manila = sandbox_service.execute_tool("c-manila", "sys_info", {"timezone": "Manila"})
    assert res_manila.ok is True
    assert res_manila.structured.get("iana_name") == "Asia/Manila"
    assert res_manila.structured.get("utc_offset") == "+0800"
    assert res_manila.structured.get("is_dst") is False

    # 3. Query Melbourne timezone (observes Australian DST in summer)
    res_melb = sandbox_service.execute_tool("c-melb", "sys_info", {"timezone": "Melbourne"})
    assert res_melb.ok is True
    assert res_melb.structured.get("iana_name") == "Australia/Melbourne"
    assert res_melb.structured.get("abbreviation") in ("AEST", "AEDT")
    assert res_melb.structured.get("utc_offset") in ("+1000", "+1100")


def test_zoneinfo_lookup_latency_sla() -> None:
    """
    TRAP 1: zoneinfo resolution must be an offline lookup (<5ms latency SLA).
    """
    # Warm run
    _ = resolve_target_timezone("Australia/Perth")

    t0 = time.perf_counter()
    tz = resolve_target_timezone("Australia/Perth")
    assert tz is not None
    from datetime import datetime

    now_tz = datetime.now(tz)
    _ = (
        tz.key,
        now_tz.strftime("%Z"),
        now_tz.strftime("%z"),
        bool(now_tz.dst()),
        now_tz.strftime("%Y-%m-%d %H:%M:%S"),
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 5.0, f"zoneinfo lookup took {elapsed_ms:.2f}ms, exceeding 5ms Class B SLA"


def test_cascade_query_resolves_grounded_timezone_evidence() -> None:
    """
    Verifies that EpistemicSearchCascade.query on timezone questions
    returns grounded EvidenceItem with zoneinfo source.
    """
    cascade = EpistemicSearchCascade()
    res = cascade.query("What time is it in Perth?")
    assert res.belnap_status == BelnapValue.TRUE

    tz_evidence = [e for e in res.evidence if e.source == "system_tools:zoneinfo"]
    assert len(tz_evidence) >= 1
    ev = tz_evidence[0]
    assert ev.trust_tier == TrustTier.TIER_1_HARDWARE
    assert "Australia/Perth" in ev.content
    assert "AWST" in ev.content
    assert ev.metadata.get("utc_offset") == "+0800"
    assert ev.metadata.get("is_dst") is False


# ============================================================================
# 3. Target Entity Snippet Filtering & Word Boundaries
# ============================================================================


def test_search_web_target_entity_present_and_absent() -> None:
    """
    Verifies search_web target_entity flag:
    - Target entity found in snippet/title -> entity_absent_in_results = False
    - Target entity absent in snippet/title -> entity_absent_in_results = True + warning
    """
    from unittest.mock import patch

    mock_results = [
        {
            "title": "Australian Fish Guide: Flake and Gummy Shark",
            "snippet": "In Australia, flake is a term used for the meat of any of several species of shark.",
            "url": "https://example.com/flake",
        }
    ]

    with patch("lucca.sandbox.search_tool.DDGS") as mock_ddgs:
        # 1. Target entity present
        mock_instance = MagicMock()
        mock_instance.text.return_value = [
            {"title": r["title"], "body": r["snippet"], "href": r["url"]} for r in mock_results
        ]
        mock_ddgs.return_value.__enter__.return_value = mock_instance

        res_present, content_present = search_web("flake in Australia", target_entity="flake")
        assert res_present.get("entity_absent_in_results") is False
        assert "WARNING: Target entity" not in content_present

        # 2. Target entity absent
        res_absent, content_absent = search_web("flake in Australia", target_entity="witchetty grub")
        assert res_absent.get("entity_absent_in_results") is True
        assert "[WARNING: Target entity 'witchetty grub' was NOT found" in content_absent


def test_search_web_target_entity_word_boundary_prevents_substring_false_positive() -> None:
    """
    Verifies word-boundary enforcement: target entity 'ever' MUST NOT
    match 'Beverly' in search results.
    """
    from unittest.mock import patch

    mock_results = [
        {
            "title": "Beverly Hills Hotel and Resorts",
            "snippet": "Located on Sunset Boulevard in Beverly Hills.",
            "url": "https://example.com/beverly",
        }
    ]

    with patch("lucca.sandbox.search_tool.DDGS") as mock_ddgs:
        mock_instance = MagicMock()
        mock_instance.text.return_value = [
            {"title": r["title"], "body": r["snippet"], "href": r["url"]} for r in mock_results
        ]
        mock_ddgs.return_value.__enter__.return_value = mock_instance

        res, content = search_web("Beverly Hills", target_entity="ever")
        # 'ever' is a substring of 'Beverly' but NOT a whole word.
        # Word boundary matching must flag entity_absent_in_results = True!
        assert res.get("entity_absent_in_results") is True
        assert "[WARNING: Target entity 'ever' was NOT found" in content


# ============================================================================
# 4. Cascade Web Search Fallback Integration
# ============================================================================


def test_cascade_query_substrate_3_web_fallback_to_search_web() -> None:
    """
    Verifies that when query_substrate_3_web receives a query without an HTTP URL,
    it falls back to executing search_web via the sandbox.
    """
    fake_sandbox = MagicMock()
    fake_sandbox.execute.return_value = ToolResult(
        call_id="call-test",
        ok=True,
        exit_code=0,
        content="Flake is gummy shark served in Australian fish and chip shops.",
        structured={"ok": True, "results_count": 1},
        elapsed_ms=12.0,
    )

    cascade = EpistemicSearchCascade(sandbox=fake_sandbox)
    items = cascade.query_substrate_3_web("What is flake in Australia?")

    assert len(items) == 1
    ev = items[0]
    assert ev.substrate == EpistemicSubstrate.WEB
    assert ev.trust_tier == TrustTier.TIER_4_WEB
    assert "Flake is gummy shark" in ev.content
    assert fake_sandbox.execute.called
    call_args = fake_sandbox.execute.call_args[1]
    assert call_args["tool_name"] == "search_web"
    assert "flake in Australia" in call_args["args"]["query"]
    assert call_args["args"].get("target_entity") == "flake"
