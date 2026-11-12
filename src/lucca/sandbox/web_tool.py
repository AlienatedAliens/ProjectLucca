"""
Project Lucca — Hardened Web Fetch, Scrapling Adaptive Extraction & Prompt-Injection DOM Sanitizer
Spec 09 §5, ADR-003, ADR-004, TM-03b, Work Order #42 (WO-42 Phase 4)
"""

from __future__ import annotations

import importlib
import ipaddress
import re
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from pydantic import JsonValue

from lucca.core.exceptions import SandboxPathError

logger = structlog.get_logger(__name__)

try:
    import truststore

    truststore.inject_into_ssl()
except Exception as exc:
    logger.debug("truststore_injection_failed", error=str(exc))

MAX_URL_LEN: int = 4096
MAX_QUERY_LEN: int = 2048
MAX_BODY_BYTES: int = 2 * 1024 * 1024  # 2 MiB
MAX_REDIRECTS: int = 8
DEFAULT_MAX_CHARS: int = 20000

CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")

_INVISIBLE_UNICODE_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\U000e0000-\U000e007f]"
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HIDDEN_TAG_BLOCK_RE = re.compile(
    r"<(?P<tag>template|script|style|noscript|iframe|svg)\b[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_HIDDEN_ATTR_ELEMENT_RE = re.compile(
    r"<(?P<tag>[a-zA-Z0-9]+)\b[^>]*(?:\bhidden\b|aria-hidden\s*=\s*['\"]?true['\"]?)[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_HIDDEN_STYLE_ELEMENT_RE = re.compile(
    r"<(?P<tag>[a-zA-Z0-9]+)\b[^>]*\bstyle\s*=\s*(['\"])(?P<style>.*?)\2[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_ADVERSARIAL_CSS_RE = re.compile(
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?(?:\s*;|\s*$)|"
    r"font-size\s*:\s*0(?:px|pt|em|rem|%)?(?:\s*;|\s*$)|"
    r"(?:left|top|text-indent)\s*:\s*-\d{3,}px)",
    re.IGNORECASE,
)

_BOT_CHALLENGE_MARKERS = (
    "just a moment...",
    "cf-browser-verification",
    "attention required! | cloudflare",
    "checking if the site connection is secure",
    "enable javascript and cookies to continue",
    "ddos-guard",
    "verify you are human",
)

_EMPTY_SPA_MARKERS = (
    "enable javascript",
    "javascript is required",
    "need to enable javascript",
    '<div id="root"></div>',
    '<div id="app"></div>',
)


def _get_trafilatura_extract() -> Callable[..., object] | None:
    try:
        mod = importlib.import_module("trafilatura")
        fn = getattr(mod, "extract", None)
        return fn if callable(fn) else None
    except ImportError:
        return None


def validate_url_ssrf(
    url: str,
    dns_resolver: Callable[[str], list[tuple[object, ...]]] | None = None,
) -> tuple[str, str]:
    """
    Validates URL format, lengths, and enforces SSRF IP resolution checks:
    - Scheme must be http or https
    - URL length <= MAX_URL_LEN, query length <= MAX_QUERY_LEN, no userinfo
    - Resolves hostname via DNS; rejects RFC1918, loopback, link-local, CGNAT,
      multicast, reserved, and IPv6.
    Returns (normalized_url, resolved_ip).
    """
    if not isinstance(url, str) or len(url) == 0:
        raise SandboxPathError("invalid_url", "URL must be a non-empty string")

    if len(url) > MAX_URL_LEN:
        raise SandboxPathError("too_long", f"URL length {len(url)} exceeds {MAX_URL_LEN}")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise SandboxPathError(
            "invalid_scheme", f"Scheme '{parsed.scheme}' not allowed; must be http or https"
        )

    if parsed.username or parsed.password:
        raise SandboxPathError("userinfo_forbidden", "Userinfo in URL is strictly forbidden")

    if parsed.query and len(parsed.query) > MAX_QUERY_LEN:
        raise SandboxPathError(
            "query_too_long",
            f"Query length {len(parsed.query)} exceeds limit {MAX_QUERY_LEN}",
        )

    hostname = parsed.hostname
    if not hostname:
        raise SandboxPathError("invalid_host", "Hostname missing in URL")

    resolver = dns_resolver if dns_resolver is not None else (lambda h: socket.getaddrinfo(h, None))
    try:
        addr_info = resolver(hostname)
    except socket.gaierror as err:
        raise SandboxPathError("dns_failed", f"Failed to resolve host '{hostname}': {err}") from err

    v4_ips: list[ipaddress.IPv4Address] = []
    v6_ips: list[ipaddress.IPv6Address] = []

    for entry in addr_info:
        sockaddr = entry[4]
        if not isinstance(sockaddr, tuple) or not sockaddr:
            continue
        ip_str = str(sockaddr[0])

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as err:
            raise SandboxPathError("invalid_ip", f"Resolved invalid IP '{ip_str}': {err}") from err

        if ip.version == 6:
            v6_ips.append(ip)
        elif ip.version == 4:
            v4_ips.append(ip)

    if not v4_ips and v6_ips:
        raise SandboxPathError("ipv6_blocked", f"IPv6 address '{v6_ips[0]}' is blocked")

    if not v4_ips:
        raise SandboxPathError("dns_failed", f"No valid IP address resolved for host '{hostname}'")

    for ip_v4 in v4_ips:
        if (
            ip_v4.is_private
            or ip_v4.is_loopback
            or ip_v4.is_link_local
            or ip_v4.is_multicast
            or ip_v4.is_reserved
            or ip_v4 in CGNAT_NET
        ):
            raise SandboxPathError(
                "ssrf_blocked",
                f"Host '{hostname}' resolved to blocked private/local IP '{ip_v4}'",
            )

    resolved_ip = str(v4_ips[0])
    return url, resolved_ip


def sanitize_html_against_prompt_injection(html: str) -> tuple[str, dict[str, int]]:
    """
    WO-42 Milestone 4.2: Strips hidden DOM nodes, invisible CSS elements, HTML comments,
    and invisible Unicode tag characters before text/Markdown extraction to defend against
    indirect prompt-injection payloads hidden in web pages.
    """
    invisible_matches = _INVISIBLE_UNICODE_RE.findall(html)
    cleaned = _INVISIBLE_UNICODE_RE.sub("", html)

    comment_matches = _HTML_COMMENT_RE.findall(cleaned)
    cleaned = _HTML_COMMENT_RE.sub("", cleaned)

    hidden_nodes_count = 0

    def _strip_block(m: re.Match[str]) -> str:
        nonlocal hidden_nodes_count
        if m.group("tag").lower() == "template":
            hidden_nodes_count += 1
        return ""

    cleaned = _HIDDEN_TAG_BLOCK_RE.sub(_strip_block, cleaned)

    def _strip_hidden_attr(m: re.Match[str]) -> str:
        nonlocal hidden_nodes_count
        hidden_nodes_count += 1
        return ""

    cleaned = _HIDDEN_ATTR_ELEMENT_RE.sub(_strip_hidden_attr, cleaned)

    def _strip_hidden_style(m: re.Match[str]) -> str:
        nonlocal hidden_nodes_count
        style_val = m.group("style") or ""
        if _ADVERSARIAL_CSS_RE.search(style_val):
            hidden_nodes_count += 1
            return ""
        return m.group(0)

    # Apply twice to catch nested hidden containers
    cleaned = _HIDDEN_STYLE_ELEMENT_RE.sub(_strip_hidden_style, cleaned)
    cleaned = _HIDDEN_STYLE_ELEMENT_RE.sub(_strip_hidden_style, cleaned)

    return cleaned, {
        "stripped_hidden_nodes": hidden_nodes_count,
        "stripped_comments": len(comment_matches),
        "stripped_invisible_unicode": len(invisible_matches),
    }


def is_bot_challenge_or_empty_spa(
    status_code: int,
    raw_html: str,
    extracted_text: str,
) -> bool:
    """Detects Cloudflare/Turnstile/bot-challenge interstitials or empty JS SPA shells."""
    html_low = raw_html.lower()
    text_low = extracted_text.lower()

    if status_code in (403, 429, 503):
        if any(m in html_low or m in text_low for m in _BOT_CHALLENGE_MARKERS):
            return True
        if len(extracted_text.strip()) < 200:
            return True

    if any(m in html_low for m in ("cf-browser-verification", "attention required! | cloudflare")):
        return True

    if len(extracted_text.strip()) < 150 and any(
        m in html_low or m in text_low for m in _EMPTY_SPA_MARKERS
    ):
        return True

    return False


def _extract_with_scrapling_selector(sanitized_html: str) -> str:
    """
    Uses Scrapling's adaptive Selector parser to extract structured headings, paragraphs, and code
    blocks.
    """
    try:
        from scrapling.parser import Selector  # noqa: PLC0415

        sel = Selector(sanitized_html)
        title_nodes = sel.css("title")
        title = title_nodes[0].text.strip() if title_nodes else ""

        root_candidates = sel.css("article, main, [role='main']")
        root = root_candidates[0] if root_candidates else sel

        blocks: list[str] = []
        if title:
            blocks.append(f"# {title}")

        for node in root.css("h1, h2, h3, p, pre, li, blockquote"):
            tag = getattr(node, "tag", "").lower()
            txt = (node.get_all_text(separator=" ", strip=True) if hasattr(node,
                "get_all_text") else node.text).strip()
            if not txt:
                continue
            if tag in ("h1", "h2", "h3"):
                prefix = "#" * int(tag[1])
                blocks.append(f"{prefix} {txt}")
            elif tag == "pre":
                blocks.append(f"```\n{txt}\n```")
            elif tag == "li":
                blocks.append(f"- {txt}")
            else:
                blocks.append(txt)

        deduped: list[str] = []
        for b in blocks:
            if not deduped or b != deduped[-1]:
                deduped.append(b)
        result = "\n\n".join(deduped).strip()
        if len(result) > 40:
            return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("scrapling_selector_extract_fallback", error=str(exc))
    return ""


def extract_readable_text(html: str) -> str:
    """
    Extracts clean, prompt-injection-sanitized article/page text using:
      1. `sanitize_html_against_prompt_injection` (strips hidden DOM / CSS / comments / invisible
      Unicode)
      2. `trafilatura` (when > 50 chars) + Scrapling adaptive `Selector` code-block preservation
      3. Scrapling `Selector` / regex fallback.
    """
    sanitized_html, _ = sanitize_html_against_prompt_injection(html)

    # Extract any <pre><code> blocks via Scrapling Selector so code snippets aren't lost
    scrapling_text = _extract_with_scrapling_selector(sanitized_html)

    extract_fn = _get_trafilatura_extract()
    if extract_fn is not None:
        try:
            extracted = extract_fn(sanitized_html, include_links=False, include_comments=False)
            if extracted and len(str(extracted).strip()) > 50:
                traf_str = str(extracted).strip()
                if "```" in scrapling_text and "```" not in traf_str:
                    return scrapling_text
                return traf_str
        except Exception as exc:  # noqa: BLE001
            logger.debug("trafilatura_extract_error", error=str(exc))

    if scrapling_text:
        return scrapling_text

    title_match = re.search(r"<title[^>]*>(.*?)</title>", sanitized_html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    clean = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", "", sanitized_html, flags=re.IGNORECASE | re.DOTALL
    )
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    if title:
        return f"{title}\n\n{clean}"
    return clean


def _fetch_via_curl_cffi_impersonation(url: str) -> tuple[int, dict[str, str], bytes, str] | None:
    """
    Tier 1.5 TLS JA3/JA4 + HTTP/2 browser fingerprint impersonation via curl_cffi (Scrapling
    backend).
    """
    try:
        from curl_cffi import requests as cffi_requests  # noqa: PLC0415

        current_url, _ = validate_url_ssrf(url)
        redirects = 0
        with cffi_requests.Session(impersonate="chrome") as sess:
            while True:
                resp = sess.get(current_url, timeout=15.0, allow_redirects=False)
                if resp.status_code in (301, 302, 303, 307, 308):
                    redirects += 1
                    if redirects > MAX_REDIRECTS:
                        raise SandboxPathError(
                            "too_many_redirects", f"Exceeded {MAX_REDIRECTS} redirects"
                        )
                    loc = str(resp.headers.get("Location", ""))
                    next_url = urljoin(current_url, loc)
                    current_url, _ = validate_url_ssrf(next_url)
                    continue
                hdrs = {str(k).lower(): str(v) for k, v in resp.headers.items()}
                return int(
                    resp.status_code), hdrs, bytes(resp.content[:MAX_BODY_BYTES]), current_url
    except SandboxPathError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.debug("curl_cffi_impersonation_failed", url=url, error=str(exc))
        return None


def fetch_url(
    url: str,
    render: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
    allow_render: bool = False,
    include_raw_html: bool = False,
) -> tuple[dict[str, JsonValue], str]:
    if render:
        if not allow_render:
            raise SandboxPathError(
                "render_disabled",
                "Headless browser rendering (render=True) is disabled on host pending "
                "Milestone 2 container isolation",
            )
        from lucca.sandbox.browser_tool import render_page  # noqa: PLC0415

        return render_page(url=url, max_chars=max_chars)

    valid_url, _ = validate_url_ssrf(url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/json,application/pdf;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }

    current_url = valid_url
    redirects_followed = 0

    def _execute_get_with_redirects(verify_ssl: bool) -> httpx.Response:
        nonlocal current_url, redirects_followed
        with httpx.Client(
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=False,
            verify=verify_ssl,
        ) as client:
            while True:
                resp = client.get(current_url, headers=headers)
                if resp.is_redirect:
                    redirects_followed += 1
                    if redirects_followed > MAX_REDIRECTS:
                        raise SandboxPathError(
                            "too_many_redirects", f"Exceeded {MAX_REDIRECTS} redirects"
                        )
                    next_url = urljoin(current_url, str(resp.headers.get("Location", "")))
                    current_url, _ = validate_url_ssrf(next_url)
                    continue
                return resp

    resp = _execute_get_with_redirects(verify_ssl=True)
    status_code = resp.status_code
    content_type = resp.headers.get("content-type", "").lower()
    raw_content = resp.content[:MAX_BODY_BYTES]
    final_url = str(resp.url)
    fetch_tier = "tier1_httpx"

    # Tier 1.5 Escalation: If httpx received 403/429/503 anti-bot challenge, try TLS JA3/JA4 Chrome
    # impersonation
    if status_code in (403, 429, 503):
        cffi_res = _fetch_via_curl_cffi_impersonation(current_url)
        if cffi_res is not None:
            cffi_status, cffi_hdrs, cffi_bytes, cffi_url = cffi_res
            if cffi_status == 200 and len(cffi_bytes) > len(raw_content):
                status_code = cffi_status
                content_type = cffi_hdrs.get("content-type", content_type).lower()
                raw_content = cffi_bytes
                final_url = cffi_url
                fetch_tier = "tier1_5_scrapling_tls_impersonation"

    is_pdf = (
        ("application/pdf" in content_type)
        or (raw_content[:4] == b"%PDF")
        or current_url.lower().endswith(".pdf")
    )
    if is_pdf:
        try:
            import io  # noqa: PLC0415

            from pypdf import PdfReader  # noqa: PLC0415

            reader = PdfReader(io.BytesIO(raw_content[:MAX_BODY_BYTES]))
            extracted_pages: list[str] = []
            for page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    extracted_pages.append(f"--- Page {page_num} ---\n{page_text.strip()}")
                if sum(len(p) for p in extracted_pages) >= max_chars:
                    break
            text = "\n\n".join(extracted_pages).strip()
            if not text:
                text = "[PDF document contained no extractable text layer (may be scanned image).]"
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            embedded_raw = re.findall(r"https?://[^\s<>\"'()]+", text)
            embedded_links = [u.rstrip(".,;:!?'\")>]") for u in set(embedded_raw) if len(u) < 512][
                :100
            ]

            return {
                "url": final_url,
                "status_code": status_code,
                "content_type": "application/pdf",
                "content_truncated": truncated,
                "redirects": redirects_followed,
                "pdf_pages": len(reader.pages),
                "embedded_links": embedded_links,
            }, text
        except Exception as pdf_err:
            logger.warning("pdf_extraction_failed", url=current_url, error=str(pdf_err))
            return {
                "url": final_url,
                "status_code": status_code,
                "content_type": "application/pdf",
                "error": f"pdf_parse_error: {pdf_err}",
                "content_truncated": False,
                "embedded_links": [],
            }, f"[PDF Parse Error: {pdf_err}]"

    allowed_types = ("text/", "application/json", "application/xml", "application/xhtml+xml")
    if not any(t in content_type for t in allowed_types):
        return {
            "url": final_url,
            "status_code": status_code,
            "blocked_content_type": content_type,
            "content_truncated": False,
            "embedded_links": [],
        }, f"[Blocked Content-Type: {content_type}]"

    try:
        html_str = raw_content.decode("utf-8")
    except UnicodeDecodeError:
        html_str = raw_content.decode("latin1", errors="replace")

    _, sanitization_stats = sanitize_html_against_prompt_injection(html_str)
    text = extract_readable_text(html_str)

    # Tier 2 Dynamic JS / Stealth rendering fallback for SPAs or bot-gated websites
    if (
        allow_render
        and ("html" in content_type.lower())
        and is_bot_challenge_or_empty_spa(status_code, html_str, text)
    ):
        try:
            from lucca.sandbox.browser_tool import render_page  # noqa: PLC0415

            rendered_struct, rendered_text = render_page(url=final_url, max_chars=max_chars)
            if len(rendered_text.strip()) > len(text.strip()):
                return rendered_struct, rendered_text
        except Exception as render_err:
            logger.debug("dynamic_js_render_fallbac"
                "k_failed", url=current_url, error=str(render_err))

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    embedded_raw = re.findall(r'href=["\'](https?://[^"\'\s<>]+)["\']', html_str, re.IGNORECASE)
    embedded_links = [u.rstrip(".,;:!?'\")>]") for u in set(embedded_raw) if len(u) < 512][:100]

    san_json: dict[str, JsonValue] = {k: int(v) for k, v in sanitization_stats.items()}
    out_meta: dict[str, JsonValue] = {
        "url": final_url,
        "status_code": status_code,
        "content_type": content_type,
        "content_truncated": truncated,
        "redirects": redirects_followed,
        "rendered": False,
        "fetch_tier": fetch_tier,
        "prompt_injection_sanitized": san_json,
        "embedded_links": [str(u) for u in embedded_links],
    }
    if include_raw_html:
        out_meta["raw_html"] = html_str
    return out_meta, text
