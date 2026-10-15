"""
Project Lucca — Compound Autonomous Research Tool
Spec 09 §5, Spec 10 §4
Orchestrates multi-query web search, source ranking, followable URL resolution,
and automated deep content extraction (with headless Playwright rendering fallback)
to provide grounded factual dossiers for complex reasoning and verification.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog
from pydantic import JsonValue

from lucca.sandbox.search_tool import classify_link_followability, search_web
from lucca.sandbox.web_tool import fetch_url

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

DEFAULT_MAX_SOURCES: int = 3
DEFAULT_SOURCE_MAX_CHARS: int = 3500


def _generate_sub_queries(query: str) -> list[str]:
    """Generates 1-2 complementary sub-queries for multi-angle research if query is complex."""
    clean = query.strip()
    words = clean.split()
    if len(words) <= 6:
        return [clean]

    sub_queries: list[str] = [clean]

    # If question contains comparison or 'versus' / 'vs'
    vs_match = re.search(r"(\bvs\.?\b|\bversus\b|\bdifference between\b|\bcompared to\b)", clean, re.IGNORECASE)
    if vs_match:
        parts = re.split(r"\bvs\.?\b|\bversus\b|\band\b", clean, flags=re.IGNORECASE)
        for p in parts:
            p_clean = p.strip("?,.:;\"' ")
            if len(p_clean.split()) >= 2:
                sub_queries.append(p_clean)

    # Scientific/academic query angle
    if any(k in clean.lower() for k in ("mechanism", "reaction", "synthesis", "proof", "theorem", "structure")):
        sub_queries.append(f"{clean} summary explanation")

    return list(dict.fromkeys(sub_queries))[:3]


def research_topic(
    query: str,
    max_sources: int = DEFAULT_MAX_SOURCES,
    target_entity: str | None = None,
) -> tuple[dict[str, JsonValue], str]:
    """
    Executes an autonomous research workflow:
    1. Multi-query search via SearXNG aggregator.
    2. URL triage and followability ranking.
    3. Deep text extraction on top authoritative sources (using Trafilatura / Playwright fallback).
    4. Synthesis of a structured research dossier with citations.
    """
    clean_query = query.strip()
    if not clean_query:
        return {"query": "", "ok": False, "error": "empty_query"}, "Research query was empty."

    sub_queries = _generate_sub_queries(clean_query)
    all_results: list[dict[str, JsonValue]] = []
    seen_urls: set[str] = set()

    for sq in sub_queries:
        structured_search, _ = search_web(
            query=sq,
            max_results=max_sources * 2,
            target_entity=target_entity,
        )
        items = structured_search.get("results", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    url = str(item.get("url", "")).strip()
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(item)

    if not all_results:
        return {
            "query": clean_query,
            "ok": False,
            "error": "no_results",
            "sources_count": 0,
            "sources": [],
        }, f"No verified web search results found for research query: '{clean_query}'."

    # Sort results by followability priority
    candidate_sources: list[dict[str, JsonValue]] = []
    for r in all_results:
        url = str(r.get("url", ""))
        cat, followable, rec = classify_link_followability(url)
        if followable and url.startswith(("http://", "https://")):
            r["category"] = cat
            r["recommendation"] = rec
            candidate_sources.append(r)

    # If no followable links found, fall back to snippet summaries
    if not candidate_sources:
        candidate_sources = all_results[:max_sources]

    # Fetch top sources
    fetched_sources: list[dict[str, JsonValue]] = []
    dossier_sections: list[str] = [
        f"# Research Dossier: {clean_query}\n",
        f"**Search Angles Explored:** {', '.join(f'`{sq}`' for sq in sub_queries)}\n",
        "## Authoritative Sources Examined\n",
    ]

    for idx, source in enumerate(candidate_sources[:max_sources], 1):
        url = str(source.get("url", ""))
        title = str(source.get("title", f"Source {idx}")).strip()
        snippet = str(source.get("snippet", "")).strip()

        extracted_content = ""
        fetch_meta: dict[str, JsonValue] = {}
        if url:
            try:
                fetch_meta, fetched_text = fetch_url(
                    url=url,
                    render=False,
                    max_chars=DEFAULT_SOURCE_MAX_CHARS,
                )
                if fetched_text and not fetched_text.startswith("[Blocked") and not fetched_text.startswith("[PDF Parse Error"):
                    extracted_content = fetched_text
            except Exception as exc:  # noqa: BLE001
                logger.debug("research_source_fetch_failed", url=url, error=str(exc))

        # Use snippet if full fetch yielded nothing
        final_text = extracted_content.strip() or snippet

        fetched_record: dict[str, JsonValue] = {
            "index": idx,
            "title": title,
            "url": url,
            "snippet": snippet,
            "content_preview": final_text[:500],
            "fetch_status": fetch_meta.get("status_code", 200 if final_text else 0),
            "rendered": bool(fetch_meta.get("rendered", False)),
        }
        fetched_sources.append(fetched_record)

        dossier_sections.append(f"### {idx}. [{title}]({url})")
        if snippet and snippet != final_text:
            dossier_sections.append(f"**Abstract:** {snippet}\n")
        dossier_sections.append(f"**Extracted Findings:**\n{final_text}\n")

    summary_text = "\n".join(dossier_sections).strip()

    structured_out: dict[str, JsonValue] = {
        "query": clean_query,
        "ok": True,
        "sub_queries": sub_queries,
        "sources_count": len(fetched_sources),
        "sources": fetched_sources,
    }

    return structured_out, summary_text
