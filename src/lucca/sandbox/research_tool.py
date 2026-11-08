"""
Project Lucca — Compound Autonomous Research Tool (Scrapling-Powered Concurrent Multi-Source
Dossier)
Spec 09 §5, Spec 10 §4, Work Order #42 (WO-42 Phase 4 Milestone 4.2)
Orchestrates multi-query web search, source ranking, followable URL resolution,
and concurrent deep content extraction (with prompt-injection DOM sanitization and
tiered TLS/headless rendering fallback) to provide grounded factual dossiers.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
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
MAX_CONCURRENT_SOURCE_FETCHES: int = 4


def _generate_sub_queries(query: str) -> list[str]:
    """Generates 1-2 complementary sub-queries for multi-angle research if query is complex."""
    clean = query.strip()
    words = clean.split()
    if len(words) <= 6:
        return [clean]

    sub_queries: list[str] = [clean]

    vs_match = re.search(
        r"(\bvs\.?\b|\bversus\b|\bdifference between\b|\bcompared to\b)",
        clean,
        re.IGNORECASE,
    )
    if vs_match:
        parts = re.split(r"\bvs\.?\b|\bversus\b|\band\b", clean, flags=re.IGNORECASE)
        for p in parts:
            p_clean = p.strip("?,.:;\"' ")
            if len(p_clean.split()) >= 2:
                sub_queries.append(p_clean)

    if any(
        k in clean.lower()
        for k in ("mechanism", "reaction", "synthesis", "proof", "theorem", "structure")
    ):
        sub_queries.append(f"{clean} summary explanation")

    return list(dict.fromkeys(sub_queries))[:3]


def _fetch_single_candidate_source(
    idx: int,
    source: dict[str, JsonValue],
) -> tuple[int, dict[str, JsonValue], list[str]]:
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
            if (
                fetched_text
                and not fetched_text.startswith("[Blocked")
                and not fetched_text.startswith("[PDF Parse Error")
            ):
                extracted_content = fetched_text
        except Exception as exc:  # noqa: BLE001
            logger.debug("research_source_fetch_failed", url=url, error=str(exc))

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

    section_lines: list[str] = [f"### {idx}. [{title}]({url})"]
    if snippet and snippet != final_text:
        section_lines.append(f"**Abstract:** {snippet}\n")
    section_lines.append(f"**Extracted Findings:**\n{final_text}\n")

    return idx, fetched_record, section_lines


def research_topic(
    query: str,
    max_sources: int = DEFAULT_MAX_SOURCES,
    target_entity: str | None = None,
) -> tuple[dict[str, JsonValue], str]:
    """
    Executes an autonomous research workflow:
    1. Multi-query search via SearXNG aggregator.
    2. URL triage and followability ranking.
    3. Concurrent deep text extraction on top authoritative sources (with Scrapling
       adaptive DOM parsing, prompt-injection sanitization, and Trafilatura/Playwright fallback).
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

    candidate_sources: list[dict[str, JsonValue]] = []
    for r in all_results:
        url = str(r.get("url", ""))
        cat, followable, rec = classify_link_followability(url)
        if followable and url.startswith(("http://", "https://")):
            r["category"] = cat
            r["recommendation"] = rec
            candidate_sources.append(r)

    if not candidate_sources:
        candidate_sources = all_results[:max_sources]

    selected_sources = candidate_sources[:max_sources]
    fetched_sources: list[JsonValue] = []
    dossier_sections: list[str] = [
        f"# Research Dossier: {clean_query}\n",
        f"**Search Angles Explored:** {', '.join(f'`{sq}`' for sq in sub_queries)}\n",
        "## Authoritative Sources Examined\n",
    ]

    workers = max(1, min(MAX_CONCURRENT_SOURCE_FETCHES, len(selected_sources)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_fetch_single_candidate_source, idx, src)
            for idx, src in enumerate(selected_sources, 1)
        ]
        ordered_results = sorted(
            (fut.result() for fut in futures),
            key=lambda item: item[0],
        )

    for _, fetched_record, section_lines in ordered_results:
        fetched_sources.append(fetched_record)
        dossier_sections.extend(section_lines)

    summary_text = "\n".join(dossier_sections).strip()
    sub_queries_json: list[JsonValue] = [str(sq) for sq in sub_queries]

    structured_out: dict[str, JsonValue] = {
        "query": clean_query,
        "ok": True,
        "sub_queries": sub_queries_json,
        "sources_count": len(fetched_sources),
        "sources": fetched_sources,
        "results": fetched_sources,
    }

    return structured_out, summary_text
