"""
Project Lucca — Live Web, PDF, Browser & Citation Provenance Verification Script
Zero Mocks: Executes real network queries, real PDF downloads, real Playwright Chromium,
and live Output Supervisor provenance validation.
"""

import sys
import structlog
from lucca.sandbox.search_tool import search_web, classify_link_followability
from lucca.sandbox.web_tool import fetch_url
from lucca.sandbox.browser_tool import HeadlessBrowserTool
from lucca.sandbox.output_supervisor import OutputSupervisorSession, SeverityTier
from lucca.core.exceptions import SandboxPathError

logger = structlog.get_logger("live_verification")


def main():
    print("=" * 70)
    print("PROJECT LUCCA: LIVE ZERO-MOCK COMPREHENSIVE VERIFICATION")
    print("=" * 70)

    passed = 0
    total = 5

    # ------------------------------------------------------------------------
    # Test 1: Live Web Search with Link Triage & Re-Ranking
    # ------------------------------------------------------------------------
    print("\n[TEST 1/5] Live DuckDuckGo Search with Followability Triage...")
    query = "Beverly Ann F. Quintos, Philippines, Judge"
    struct, text = search_web(query, max_results=5)
    print(f"-> Query: {query}")
    print(f"-> Results returned: {struct.get('results_count', 0)}")
    assert struct["ok"] is True, f"Search failed: {struct.get('error')}"
    assert struct["results_count"] > 0, "No results returned"

    results = struct["results"]
    first_res = results[0]
    print(f"-> Top Ranked Result: {first_res['title']}")
    print(f"   URL: {first_res.get('url')}")
    print(f"   Status: {first_res.get('recommendation')}")

    # Check that followable HTML/PDF is prioritized over social media
    for r in results:
        if "facebook.com" in r.get("url", "") or "linkedin.com" in r.get("url", ""):
            assert r["followable"] is False
            print(f"   [Verified] Social link demoted & tagged snippet only: {r['url'][:50]}...")

    passed += 1
    print(">>> TEST 1 PASSED: Live search and triage functional.")

    # ------------------------------------------------------------------------
    # Test 2: Live Government PDF Extraction
    # ------------------------------------------------------------------------
    print("\n[TEST 2/5] Live Real-World PDF Download & Text Extraction...")
    pdf_url = "https://jbc.judiciary.gov.ph/wp-content/uploads/PdfFiles/Schedules/Interviews/2022/Interview_RegIII_11-21to11-22-22.pdf"
    print(f"-> Target URL: {pdf_url}")
    p_struct, p_text = fetch_url(pdf_url)

    print(f"-> HTTP Status: {p_struct.get('status_code')}")
    print(f"-> Content-Type: {p_struct.get('content_type')}")
    print(f"-> Extracted Pages: {p_struct.get('pdf_pages')}")
    assert p_struct["status_code"] == 200, f"HTTP status failed: {p_struct}"
    assert p_struct["content_type"] == "application/pdf"
    assert "Quintos" in p_text or "QUINTOS" in p_text, "Failed to find Quintos in extracted text"

    # Print matching line
    for line in p_text.splitlines():
        if "quintos" in line.lower():
            print(f"   [Verified Ground Truth in PDF]: '{line.strip()}'")

    passed += 1
    print(">>> TEST 2 PASSED: Real government PDF extracted successfully.")

    # ------------------------------------------------------------------------
    # Test 3: Live Real Web Page Extraction (Path 1)
    # ------------------------------------------------------------------------
    print("\n[TEST 3/5] Live HTML Webpage Scraping (Path 1)...")
    html_url = "https://example.com"
    h_struct, h_text = fetch_url(html_url)
    print(f"-> Target URL: {html_url}")
    print(f"-> HTTP Status: {h_struct.get('status_code')}")
    assert h_struct["status_code"] == 200
    assert "Example Domain" in h_text
    passed += 1
    print(">>> TEST 3 PASSED: Live HTML fetch functional.")

    # ------------------------------------------------------------------------
    # Test 4: Live Headless Chromium Rendering & SSRF Protection (Path 2)
    # ------------------------------------------------------------------------
    print("\n[TEST 4/5] Live Playwright Headless Browser Rendering (Path 2)...")
    browser_tool = HeadlessBrowserTool()
    b_struct, b_text = browser_tool.render_url("https://example.com")
    print(f"-> Rendered URL: {b_struct['url']}")
    print(f"-> Page Title: '{b_struct['title']}'")
    assert b_struct["rendered"] is True
    assert "Example Domain" in b_text

    # SSRF Protection test
    print("-> Verifying SSRF Protection blocks 127.0.0.1...")
    ssrf_blocked = False
    try:
        browser_tool.render_url("http://127.0.0.1:8080")
    except SandboxPathError as exc:
        if exc.code == "ssrf_blocked":
            ssrf_blocked = True
            print(f"   [Verified] SSRF blocked: {exc.message}")
    assert ssrf_blocked is True, "SSRF did not block 127.0.0.1!"

    passed += 1
    print(">>> TEST 4 PASSED: Live headless browser and SSRF shield functional.")

    # ------------------------------------------------------------------------
    # Test 5: Live Citation Provenance Guard (Output Supervisor)
    # ------------------------------------------------------------------------
    print("\n[TEST 5/5] Live Citation Provenance Guard (Tier 1 Abort)...")
    supervisor = OutputSupervisorSession()
    # Register the real URL we just fetched
    supervisor.register_allowed_urls([pdf_url, html_url])

    # Case A: Model cites verified URL
    valid_clause = f"She was interviewed per the JBC schedule ({pdf_url})."
    emitted, should_abort = supervisor.feed_chunk(None, valid_clause)
    assert should_abort is False
    assert len(emitted) == 1
    assert emitted[0][1].severity == SeverityTier.PASS
    print(f"-> Valid citation allowed: PASS")

    # Case B: Model cites fabricated URL
    fake_clause = "Her biography is on https://sc.judiciary.gov.ph/fake-database/quintos."
    emitted, should_abort = supervisor.feed_chunk(None, fake_clause)
    assert supervisor.pending_tier1_chunk is not None
    assert supervisor.pending_tier1_chunk[1].breach_type == "ungrounded_citation"

    # End of stream flush commits abort
    _, final_abort = supervisor.flush()
    assert final_abort is True
    print(f"-> Fabricated citation detected: TIER 1 ABORT COMMITTED")

    passed += 1
    print(">>> TEST 5 PASSED: Citation Provenance Guard blocks fake URLs and allows real URLs.")

    # ------------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"ALL LIVE TESTS PASSED: {passed}/{total} (100% Zero-Mock Verification)")
    print("=" * 70)


if __name__ == "__main__":
    main()
