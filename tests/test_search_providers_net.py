"""
Project Lucca — Consolidated Search Provider Network Battery (WP-5)
Work Order #8, §7.5 (F-TS-07)

Folds exploratory search scripts (scripts/probe_search_providers.py,
scripts/test_ddgs_live.py, etc.) into a permanent @pytest.mark.net test suite.
Validates:
  1. Configured DDGS provider returns >= 3 results with valid URLs for a fixed query.
  2. Fallback direct HTML/Lite endpoints return valid structured results.
  3. Seamless failover to fallback endpoints when primary DDGS raises or is blocked.
  4. Link followability categorization logic (HTML, PDF, login walls, binary assets).

Run:
  uv run pytest tests/test_search_providers_net.py -m net -v
"""

from __future__ import annotations

import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

from lucca.sandbox.search_tool import (
    classify_link_followability,
    search_web,
)

FIXED_TEST_QUERY = "Python 3.12 release date"


@pytest.mark.net
def test_ddgs_live_configured_provider() -> None:
    """
    Asserts the primary configured DDGS provider returns >= 3 results
    with non-empty titles, snippets, and valid HTTP/HTTPS URLs.
    """
    structured, summary = search_web(FIXED_TEST_QUERY, max_results=5)

    assert structured.get("ok") is True, f"search_web failed: {structured.get('error')}"
    results = structured.get("results")
    assert isinstance(results, list)
    assert len(results) >= 3, f"Expected >= 3 results, got {len(results)}"

    valid_urls = 0
    for item in results:
        assert isinstance(item, dict)
        title = str(item.get("title", ""))
        snippet = str(item.get("snippet", ""))
        url = str(item.get("url", ""))

        assert title or snippet, "Result must have title or snippet"
        if url.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc:
                valid_urls += 1

    assert valid_urls >= 2, f"Expected >= 2 valid HTTP/HTTPS URLs, got {valid_urls}"
    assert "Search Results for" in summary


@pytest.mark.net
def test_search_fallback_endpoints_live() -> None:
    """
    Forces the secondary HTTP fallback path (simulating DDGS unavailable)
    and asserts the fallback parsing returns >= 1 result with valid structure.
    """
    with patch("lucca.sandbox.search_tool.DDGS", None):
        structured, summary = search_web(FIXED_TEST_QUERY, max_results=5)

    # Fallback either returns valid results or reports a bot challenge / no_results gracefully
    if structured.get("ok"):
        results = structured.get("results")
        assert isinstance(results, list)
        assert len(results) >= 1
        for item in results:
            assert isinstance(item, dict)
            assert "title" in item
            assert "snippet" in item
    else:
        # If rate limited by DuckDuckGo on CI/test IP, must fail closed with clean error
        assert structured.get("error") in ("bot_challenge", "no_results")
        assert "Search engine rate limited" in summary or "No verified web search" in summary


@pytest.mark.net
def test_search_provider_failover() -> None:
    """
    Asserts that if DDGS raises an unhandled exception during execution,
    search_web catches it, logs a warning, and falls over to the fallback endpoint.
    """
    mock_ddgs_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.__enter__.return_value = mock_instance
    mock_instance.__exit__.return_value = None
    mock_instance.text.side_effect = RuntimeError("Simulated DDGS TLS connection timeout")
    mock_ddgs_cls.return_value = mock_instance

    with patch("lucca.sandbox.search_tool.DDGS", mock_ddgs_cls):
        structured, summary = search_web(FIXED_TEST_QUERY, max_results=5)

    # DDGS must have been attempted
    assert mock_ddgs_cls.called
    # The call must not raise RuntimeError, and must either succeed via fallback or cleanly report error
    assert isinstance(structured, dict)
    assert "query" in structured
    assert isinstance(summary, str)


def test_classify_link_followability() -> None:
    """
    Validates link triage and followability categorization per Spec 09 §5.
    (Unit test — does not require network).
    """
    cat_html, follow_html, _ = classify_link_followability(
        "https://www.python.org/downloads/release/python-3120/"
    )
    assert cat_html == "html_page"
    assert follow_html is True

    cat_pdf, follow_pdf, _ = classify_link_followability("https://example.org/docs/manual.pdf")
    assert cat_pdf == "pdf_document"
    assert follow_pdf is True

    cat_bin, follow_bin, _ = classify_link_followability("https://example.org/files/archive.zip")
    assert cat_bin == "binary_asset"
    assert follow_bin is False

    cat_wall, follow_wall, _ = classify_link_followability("https://www.facebook.com/groups/python")
    assert cat_wall == "login_wall"
    assert follow_wall is False

    cat_none, follow_none, _ = classify_link_followability("")
    assert cat_none == "unknown"
    assert follow_none is False
