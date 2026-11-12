"""
Project Lucca — Compound Autonomous Research Tool (Scrapling-Powered Concurrent Multi-Source
Dossier)
Spec 09 §5, Spec 10 §4, Work Order #42 (WO-42 Phase 4 Milestone 4.2) & WO-46
Orchestrates multi-query web search, source ranking, registrable-domain eTLD+1 diversity,
and concurrent deep content extraction (with query-focused passage windowing, prompt-injection
DOM sanitization, and tiered TLS/headless rendering fallback) to provide grounded dossiers.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import structlog
from pydantic import JsonValue

from lucca.core.corroboration import normalize_source_identity
from lucca.sandbox.search_tool import (
    _simplify_search_query,
    classify_link_followability,
    search_web,
)
from lucca.sandbox.web_tool import fetch_url

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

DEFAULT_MAX_SOURCES: int = 4
DEFAULT_SOURCE_MAX_CHARS: int = 4000
MAX_CONCURRENT_SOURCE_FETCHES: int = 4

_QUERY_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "do",
        "does",
        "did",
        "can",
        "should",
        "must",
        "what",
        "which",
        "who",
        "when",
        "where",
        "why",
        "how",
        "many",
        "much",
        "under",
        "between",
        "difference",
        "compared",
        "according",
        "official",
        "officially",
        "standard",
    }
)


def _query_keywords(query: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", query.lower().replace("_", " ").replace("-", " "))
        if len(t) >= 2 and t not in _QUERY_STOPWORDS
    }


def _generate_sub_queries(query: str) -> list[str]:
    """Generate complementary compact sub-query without splitting comparison pairs (`X and Y`)."""
    clean = query.strip()
    words = clean.split()
    if len(words) <= 7:
        return [clean]

    sub_queries: list[str] = [clean]
    compact = _simplify_search_query(clean)
    if compact and compact.lower() != clean.lower():
        sub_queries.append(compact)

    if any(
        k in clean.lower()
        for k in ("mechanism", "reaction", "synthesis", "proof", "theorem", "structure")
    ):
        sub_queries.append(f"{compact or clean} summary explanation")

    return list(dict.fromkeys(sub_queries))[:2]


def _build_focused_preview(snippet: str, final_text: str, query: str, max_len: int = 1600) -> str:
    """Combine search snippet, lead intro, and best query-aligned mid-article sentences."""
    if not final_text:
        return snippet[:max_len]

    lead = final_text[:950].strip()
    prefix = f"{snippet} {lead}".strip() if (snippet and snippet not in lead[:500]) else lead
    if len(final_text) <= 950 or len(prefix) >= max_len:
        return prefix[:max_len]

    q_kw = _query_keywords(query)
    if not q_kw:
        return prefix[:max_len]

    tail_sents = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", final_text[950:])
        if 25 <= len(s.strip()) <= 380 and not s.strip().startswith("#")
    ]
    scored: list[tuple[int, int, str]] = []
    for idx, sent in enumerate(tail_sents):
        s_toks = set(re.findall(r"[a-z0-9]+", sent.lower()))
        hits = sum(1 for k in q_kw if k in s_toks)
        has_num = 1 if re.search(r"\b\d+\b", sent) else 0
        if hits >= 2 or (hits >= 1 and has_num):
            scored.append((hits * 2 + has_num, -idx, sent))

    if not scored:
        return prefix[:max_len]

    scored.sort(reverse=True)
    extra_parts: list[str] = []
    cur_len = len(prefix)
    for _sc, _neg_i, sent in scored[:3]:
        if sent in prefix:
            continue
        if cur_len + len(sent) + 2 > max_len:
            break
        extra_parts.append(sent)
        cur_len += len(sent) + 2

    return f"{prefix} {' '.join(extra_parts)}".strip()[:max_len]


def _fetch_single_candidate_source(
    idx: int,
    source: dict[str, JsonValue],
    include_raw_html: bool = False,
    query: str = "",
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
                include_raw_html=include_raw_html,
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
        "content_preview": _build_focused_preview(snippet, final_text, query),
        "fetch_status": fetch_meta.get("status_code", 200 if final_text else 0),
        "rendered": bool(fetch_meta.get("rendered", False)),
    }
    if include_raw_html and "raw_html" in fetch_meta:
        fetched_record["raw_html"] = fetch_meta["raw_html"]
        fetched_record["fetch_tier"] = fetch_meta.get("fetch_tier", "")
        fetched_record["final_url"] = fetch_meta.get("url", url)

    section_lines: list[str] = [f"### {idx}. [{title}]({url})"]
    if snippet and snippet != final_text:
        section_lines.append(f"**Abstract:** {snippet}\n")
    section_lines.append(f"**Extracted Findings:**\n{final_text}\n")

    return idx, fetched_record, section_lines


def research_topic(
    query: str,
    max_sources: int = DEFAULT_MAX_SOURCES,
    target_entity: str | None = None,
    include_raw_html: bool = False,
) -> tuple[dict[str, JsonValue], str]:
    """
    Executes an autonomous research workflow:
    1. Multi-query search via SearXNG / DDGS aggregator.
    2. URL triage, query-keyword relevance ranking, and registrable-domain (eTLD+1) diversity.
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
            max_results=max(8, max_sources * 2),
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

    # Stable relevance sort: prefer candidates whose title+snippet match more query keywords
    q_kw = _query_keywords(clean_query)
    if q_kw:

        def _cand_rel_key(item: tuple[int, dict[str, JsonValue]]) -> tuple[int, int]:
            orig_i, cand = item
            blob = f"{cand.get('title', '')} {cand.get('snippet', '')}".lower()
            blob_toks = set(re.findall(r"[a-z0-9]+", blob.replace("_", " ").replace("-", " ")))
            hits = sum(1 for k in q_kw if k in blob_toks)
            return (-hits, orig_i)

        candidate_sources = [c for _, c in sorted(enumerate(candidate_sources), key=_cand_rel_key)]

    # Prefer distinct registrable eTLD+1 domains first so corroboration slots are not wasted
    # on multiple subdomains/paths of a single publisher (e.g. en.wikipedia.org + fr.wikipedia.org).
    distinct_host_sources: list[dict[str, JsonValue]] = []
    overflow_sources: list[dict[str, JsonValue]] = []
    seen_hosts: set[str] = set()
    for cand in candidate_sources:
        cand_url = str(cand.get("url", ""))
        reg_dom = normalize_source_identity(cand_url) if "//" in cand_url else ""
        if reg_dom and reg_dom not in seen_hosts:
            seen_hosts.add(reg_dom)
            distinct_host_sources.append(cand)
        else:
            overflow_sources.append(cand)

    selected_sources = (distinct_host_sources + overflow_sources)[:max_sources]
    fetched_sources: list[JsonValue] = []
    dossier_sections: list[str] = [
        f"# Research Dossier: {clean_query}\n",
        f"**Search Angles Explored:** {', '.join(f'`{sq}`' for sq in sub_queries)}\n",
        "## Authoritative Sources Examined\n",
    ]

    workers = max(1, min(MAX_CONCURRENT_SOURCE_FETCHES, len(selected_sources)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_fetch_single_candidate_source, idx, src, include_raw_html, clean_query)
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
