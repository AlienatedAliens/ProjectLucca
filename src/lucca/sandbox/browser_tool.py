"""
Project Lucca — Headless Browser Tool (Path 2: Interactive Web Rendering)
Spec 09 §5, ADR-004, D-SAND-02
Provides headless Chromium browser execution with strict SSRF route interception
for client-side JavaScript rendering, SPAs, and dynamic DOM extraction.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog
from pydantic import JsonValue

from lucca.core.exceptions import SandboxPathError
from lucca.sandbox.web_tool import DEFAULT_MAX_CHARS, validate_url_ssrf

if TYPE_CHECKING:
    from playwright.sync_api import Route

logger = structlog.get_logger(__name__)

# Private / link-local ranges are mapped to 0.0.0.0 at Chromium's resolver so no
# subresource can reach them even before the route interceptor sees the request.
_BLOCKED_RESOLVER_RULES = (
    "MAP 127.* 0.0.0.0",
    "MAP 10.* 0.0.0.0",
    "MAP 172.16.* 0.0.0.0",
    "MAP 192.168.* 0.0.0.0",
    "MAP 169.254.* 0.0.0.0",
    "MAP ::1 0.0.0.0",
)

# Chromium launch arguments for hardened headless execution
HARDENED_BROWSER_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-translate",
    "--disable-default-apps",
    "--mute-audio",
    "--host-resolver-rules=" + ", ".join(_BLOCKED_RESOLVER_RULES),
]


class HeadlessBrowserTool:
    """
    Executes headless Chromium browsing with subresource SSRF route interception,
    dynamic DOM rendering, and readable text extraction.
    """

    def __init__(self, headless: bool = True, timeout_ms: int = 15000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms

    def render_url(
        self,
        url: str,
        max_chars: int = DEFAULT_MAX_CHARS,
        wait_until: str = "domcontentloaded",
    ) -> tuple[dict[str, JsonValue], str]:
        """
        Navigates to URL in headless Chromium, enforces subresource SSRF blocking,
        and extracts rendered DOM text.
        """
        # 1. Pre-navigation SSRF verification
        valid_url, _ = validate_url_ssrf(url)

        try:
            # Lazy import: Playwright is an optional, heavy dependency (Chromium runtime).
            from playwright.sync_api import sync_playwright  # noqa: PLC0415
        except ImportError as err:
            logger.error("playwright_not_installed", error=str(err))
            raise SandboxPathError(
                "browser_unavailable",
                "Playwright browser engine is not installed in the active environment.",
            ) from err

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=HARDENED_BROWSER_ARGS,
            )
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=False,
                )
                try:
                    page = context.new_page()

                    # 2. Subresource SSRF route interception (Mitigates Vector 1)
                    blocked_subresources: list[str] = []

                    def _ssrf_route_interceptor(route: Route) -> None:
                        req_url = route.request.url
                        try:
                            is_valid, _ = validate_url_ssrf(req_url)
                            if not is_valid:
                                blocked_subresources.append(req_url)
                                route.abort("blockedbyclient")
                                return
                        except Exception as exc:  # noqa: BLE001 — fail closed: any validator error blocks
                            logger.debug("browser_ssrf_validation_error", error=str(exc))
                            blocked_subresources.append(req_url)
                            route.abort("blockedbyclient")
                            return
                        route.continue_()

                    page.route("**/*", _ssrf_route_interceptor)

                    response = page.goto(valid_url, timeout=self.timeout_ms, wait_until=wait_until)
                    status_code = response.status if response else 200
                    page_title = page.title() or ""

                    # Extract readable text and embedded links
                    dom_data = page.evaluate(
                        """() => {
                        const root = document.body ? document.body : document.documentElement;
                        const clone = root.cloneNode(true);
                        const toRemove = clone.querySelectorAll(
                            'script, style, noscript, iframe, svg, nav, footer'
                        );
                        toRemove.forEach(el => el.remove());
                        const text = clone.innerText || clone.textContent || '';
                        const links = Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href)
                            .filter(h => h.startsWith('http://') || h.startsWith('https://'));
                        return { text, links };
                    }"""
                    )

                    extracted_text = dom_data.get("text", "")
                    raw_links = dom_data.get("links", [])
                    clean_links = [
                        u.rstrip(".,;:!?'\")>]") for u in set(raw_links) if len(u) < 512
                    ][:100]

                    clean_text = re.sub(r"\n{3,}", "\n\n", extracted_text).strip()
                    clean_text = re.sub(r"[ \t]+", " ", clean_text)

                    truncated = len(clean_text) > max_chars
                    if truncated:
                        clean_text = clean_text[:max_chars]

                    formatted_content = (
                        f"# {page_title}\n\n{clean_text}" if page_title else clean_text
                    )

                    structured: dict[str, JsonValue] = {
                        "url": page.url,
                        "title": page_title,
                        "status_code": status_code,
                        "rendered": True,
                        "engine": "chromium_headless",
                        "content_truncated": truncated,
                        "blocked_subresources_count": len(blocked_subresources),
                        "embedded_links": clean_links,
                    }
                    return structured, formatted_content

                finally:
                    context.close()
            except Exception as exc:
                err_msg = str(exc)
                logger.warning("browser_navigation_failed", url=valid_url, error=err_msg)
                raise SandboxPathError(
                    "browser_navigation_error", f"Browser navigation failed: {err_msg}"
                ) from exc
            finally:
                browser.close()


def render_page(url: str, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[dict[str, JsonValue], str]:
    """Helper dispatch function for browser rendering."""
    tool = HeadlessBrowserTool()
    return tool.render_url(url=url, max_chars=max_chars)
