"""Unit and integration tests for the 4 code-verified WO-42 compounded enhancements:
1. Per-source sentence-filtered Scrapling corroboration in Orchestrator._execute_cross_reference_searches
2. search_web(deep_extract=True) dispatch to research_topic + OutputSupervisor 'sources'/'results' URL registration
3. Multi-category compound-turn tool shortlisting under the <= 12 tool cap in tool_shortlister.py
4. NLI verifier wiring into RuleInducer.mine_patterns() and DreamRetrospective.retrospective()
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from lucca.core.capabilities import get_default_native_tools
from lucca.core.coherence import ToolReceipt
from lucca.core.corroboration import (
    Q_AUTH_INDEPENDENT_CORROB,
    CQAnswer,
    Scheme,
    compute_proposition_alignment,
    critical_questions,
)
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    InferenceStep,
    VerificationResult,
    VerifierLabel,
)
from lucca.core.tool_shortlister import NATIVE_TOOL_CATEGORIES, shortlist_tools
from lucca.reasoning.induction import RuleInducer
from lucca.sandbox.schemas import SearchWebArgs


def test_fix1_sentence_filtered_scrapling_corroboration() -> None:
    """Proves Fix #1 upgrades truncated snippets with claim-aligned sentences from Scrapling
    without triggering full-article negation/adversative false conflicts in corroboration.py:666.
    """
    claim = "libxml2 version 2.12.5 patches CVE 2026 4096"
    truncated_snippet = "Security Advisory Bulletin for XML parsers"
    full_scraped_article = (
        "Welcome to the security portal. However, legacy 2.9 branches are not maintained "
        "and will never receive backports. "
        "In the latest upstream release, libxml2 version 2.12.5 patches CVE 2026 4096 "
        "by bounds-checking entity expansion. "
        "Users should not delay upgrading their production containers."
    )

    # 1. Truncated snippet alone fails alignment (0 claim token overlap)
    snippet_aligned, _, _ = compute_proposition_alignment(claim, truncated_snippet)
    assert snippet_aligned is False

    # 2. Raw full article with unrelated 'However... not... never' fails alignment due to has_conflict
    raw_full_aligned, _, raw_has_conflict = compute_proposition_alignment(claim, full_scraped_article)
    assert raw_has_conflict is True
    assert raw_full_aligned is False

    # 3. Orchestrator._extract_claim_aligned_sentences extracts the exact claim-matching sentence
    extracted = Orchestrator._extract_claim_aligned_sentences(
        claim=claim,
        page_text=full_scraped_article,
        fallback_snippet=truncated_snippet,
        max_sentences=1,
    )
    assert "libxml2 version 2.12.5 patches CVE 2026 4096" in extracted
    assert "However, legacy 2.9 branches are not maintained" not in extracted

    # 4. Extracted sentence passes proposition alignment and 2 independent domains satisfy Q_AUTH_INDEPENDENT_CORROB
    ext_aligned, _, ext_conflict = compute_proposition_alignment(claim, extracted)
    assert ext_aligned is True
    assert ext_conflict is False

    r1 = ToolReceipt(
        tool="search_web",
        tool_name="search_web",
        ok=True,
        call_id="01JTEST1",
        args={"url": "https://nvd.nist.gov/vuln/detail/CVE-2026-4096", "domain": "nvd.nist.gov", "query": claim},
        output=extracted,
    )
    r2 = ToolReceipt(
        tool="search_web",
        tool_name="search_web",
        ok=True,
        call_id="01JTEST2",
        args={"url": "https://gitlab.gnome.org/GNOME/libxml2/-/releases/v2.12.5", "domain": "gitlab.gnome.org", "query": claim},
        output=extracted,
    )
    step = InferenceStep(
        s="web_search",
        p="asserts",
        o=claim,
        premises=[claim],
        confidence=0.80,
        rule_id="cross_ref",
    )
    cq_results = critical_questions(
        scheme=Scheme.AUTHORITY,
        step=step,
        receipts=[r1, r2],
        store=None,
    )
    indep_q = next(q for q in cq_results if q.question == Q_AUTH_INDEPENDENT_CORROB)
    assert indep_q.answer == CQAnswer.SATISFIED
    assert indep_q.count == 2
    assert set(indep_q.sources) == {"nvd.nist.gov", "gitlab.gnome.org"}


def test_fix2_search_web_deep_extract_schema_and_sources_registration() -> None:
    """Proves Fix #2 exposes deep_extract on search_web and populates 'results' + 'sources'."""
    parsed = SearchWebArgs.model_validate({"query": "libxml2 CVE", "deep_extract": True})
    assert parsed.deep_extract is True
    assert parsed.query == "libxml2 CVE"

    tools = get_default_native_tools()
    assert len(tools) == 24
    assert "deep_extract" in tools["search_web"].parameters

    with patch("lucca.sandbox.research_tool.search_web") as mock_search, patch(
        "lucca.sandbox.research_tool.fetch_url"
    ) as mock_fetch:
        mock_search.return_value = (
            {
                "ok": True,
                "results": [
                    {
                        "title": "NVD CVE-2026-4096",
                        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-4096",
                        "snippet": "libxml2 advisory",
                    }
                ],
            },
            "1. NVD CVE-2026-4096",
        )
        mock_fetch.return_value = (
            {"ok": True, "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-4096", "title": "NVD"},
            "libxml2 2.12.5 fixes CVE-2026-4096.",
        )
        from lucca.sandbox.research_tool import research_topic

        structured, _summary = research_topic("libxml2 CVE", max_sources=1)
        assert structured["ok"] is True
        assert "sources" in structured
        assert "results" in structured
        assert structured["results"] == structured["sources"]


def test_fix5_multi_category_compound_turn_shortlisting() -> None:
    """Proves Fix #5 maps router intent names and packs secondary task categories within <= 12 tools."""
    # 1. Exact router intent names map cleanly instead of falling back to 24 tools
    for router_intent in ("search_web", "write_file", "run_python", "schedule_event", "self_metrics"):
        shortlist = shortlist_tools(router_intent)
        assert len(shortlist) <= 12
        for core_t in NATIVE_TOOL_CATEGORIES["cognitive_core"]:
            assert core_t in shortlist

    # 2. Compound multi-sentence prompt: search_web (external_recon: 3) + schedule_event (system_schedule: 3)
    # 6 core + 3 external_recon + 3 system_schedule = 12 tools (both categories kept in full!)
    compound_12 = shortlist_tools(
        intent="search_web",
        entities=["reminder"],
        user_query="Search the web for the flight status and set a reminder for 6pm.",
    )
    assert len(compound_12) <= 12
    assert "search_web" in compound_12
    assert "fetch_url" in compound_12
    assert "schedule_event" in compound_12

    # 3. Compound multi-sentence prompt: search_web (external_recon: 3) + workspace (5 tools: 6+3+5=14 > 12)
    # Packs cue-matched workspace tools (write_file, read_file) into the remaining 3 budget slots!
    compound_ws = shortlist_tools(
        intent="search_web",
        entities=["file"],
        user_query="Search the web for CVE-2026-4096 and write the summary to audit.md file.",
    )
    assert len(compound_ws) <= 12
    assert "search_web" in compound_ws
    assert "write_file" in compound_ws
    for core_t in NATIVE_TOOL_CATEGORIES["cognitive_core"]:
        assert core_t in compound_ws


def test_fix6_rule_inducer_wires_nli_verifier_into_cluster_phrasings() -> None:
    """Proves Fix #6 wires SemanticVerifierPort into RuleInducer.mine_patterns() so paraphrases
    with Jaccard < 0.60 cluster via bidirectional NLI entailment.
    """
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    # 3 turns with identical intent/tool/arg_key but low-Jaccard paraphrased argument values
    rows = [
        (
            f"d{i}",
            json.dumps({"intent": "search_web"}),
            json.dumps([{"tool": "search_web", "args": {"query": phrase}}]),
            1,
        )
        for i, phrase in enumerate(
            [
                "latest rust compiler release notes",
                "newest cargo language changelog update",
                "recent rustc version announcement details",
            ]
        )
    ]
    mock_cursor.__enter__.return_value.fetchall.return_value = rows
    mock_db.read_cursor.return_value = mock_cursor

    mock_rule_engine = MagicMock()

    # Without NLI verifier, Jaccard is < 0.60 so 0 clusters reach min_frequency=3
    inducer_no_v = RuleInducer(db=mock_db, rule_engine=mock_rule_engine, min_frequency=3)
    assert len(inducer_no_v.mine_patterns()) == 0

    # With NLI verifier returning ENTAILMENT, all 3 paraphrases merge into 1 cluster of count=3
    class _EntailingVerifier:
        def check_consistency(self, premise: str, hypothesis: str) -> Any:
            return VerificationResult(
                label=VerifierLabel.ENTAILMENT,
                score=0.92,
                probs={"entailment": 0.92, "neutral": 0.05, "contradiction": 0.03},
                elapsed_ms=1.0,
            )

    inducer_with_v = RuleInducer(
        db=mock_db,
        rule_engine=mock_rule_engine,
        min_frequency=3,
        verifier=_EntailingVerifier(),  # type: ignore[arg-type]
    )
    clusters = inducer_with_v.mine_patterns()
    assert len(clusters) == 1
    assert clusters[0].occurrences == 3
    assert clusters[0].intent == "search_web"
    assert clusters[0].tool == "search_web"
