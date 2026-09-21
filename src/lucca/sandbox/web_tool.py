"""
Project Lucca — Hardened Web Fetch & SSRF Guard
Spec 09 §5, ADR-003, ADR-004, TM-03b
"""

import importlib
import ipaddress
import re
import socket
from collections.abc import Callable
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import JsonValue

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

from lucca.core.exceptions import SandboxPathError

logger = structlog.get_logger(__name__)

MAX_URL_LEN: int = 512
MAX_QUERY_LEN: int = 128
MAX_BODY_BYTES: int = 2 * 1024 * 1024  # 2 MiB
MAX_REDIRECTS: int = 8
DEFAULT_MAX_CHARS: int = 20000

CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")


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
    - URL length <= 512 chars, query length <= 128 chars, no userinfo
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

    # Resolve IP addresses
    resolver = dns_resolver if dns_resolver is not None else (lambda h: socket.getaddrinfo(h, None))
    try:
        addr_info = resolver(hostname)
    except socket.gaierror as err:
        raise SandboxPathError("dns_failed", f"Failed to resolve host '{hostname}': {err}") from err

    resolved_ip = ""
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as err:
            raise SandboxPathError("invalid_ip", f"Resolved invalid IP '{ip_str}': {err}") from err

        # Reject IPv6 per Spec 09 & ADR-003
        if ip.version == 6:
            raise SandboxPathError("ipv6_blocked", f"IPv6 address '{ip_str}' is blocked")

        # Reject RFC1918, Loopback, Link-local, CGNAT, Multicast, Reserved
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip in CGNAT_NET
        ):
            raise SandboxPathError(
                "ssrf_blocked",
                f"Host '{hostname}' resolved to blocked private/local IP '{ip_str}'",
            )

        if not resolved_ip:
            resolved_ip = str(ip)

    return url, resolved_ip


def extract_readable_text(html: str) -> str:
    """Extracts clean article/page text using trafilatura or fallback HTML strip."""
    extract_fn = _get_trafilatura_extract()
    if extract_fn is not None:
        try:
            extracted = extract_fn(html, include_links=False, include_comments=False)
            if extracted and len(str(extracted).strip()) > 50:
                return str(extracted).strip()
        except Exception as exc:  # noqa: BLE001
            logger.debug("trafilatura_extract_error", error=str(exc))

    # Fallback extraction: extract title and strip tags
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    # Remove script and style tags
    clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", " ", clean)
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()

    if title:
        return f"{title}\n\n{clean}"
    return clean


def fetch_url(
    url: str,
    render: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
    allow_render: bool = False,
) -> tuple[dict[str, JsonValue], str]:
    if render:
        if not allow_render:
            raise SandboxPathError(
                "render_disabled",
                "Headless browser rendering (render=True) is disabled on host pending "
                "Milestone 2 container isolation",
            )
        # Lazy import: browser_tool pulls Playwright only when rendering is requested.
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
                    next_url = str(resp.headers.get("Location", ""))
                    current_url, _ = validate_url_ssrf(next_url)
                    continue
                return resp

    resp = _execute_get_with_redirects(verify_ssl=True)

    content_type = resp.headers.get("content-type", "").lower()
    is_pdf = (
        ("application/pdf" in content_type)
        or (resp.content[:4] == b"%PDF")
        or current_url.lower().endswith(".pdf")
    )
    if is_pdf:
        try:
            # Lazy imports: PDF extraction is the rare path; keep httpx fetches cheap.
            import io  # noqa: PLC0415

            from pypdf import PdfReader  # noqa: PLC0415

            reader = PdfReader(io.BytesIO(resp.content[:MAX_BODY_BYTES]))
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

            # Extract embedded links from text layer
            embedded_raw = re.findall(r"https?://[^\s<>\"'()]+", text)
            embedded_links = [u.rstrip(".,;:!?'\")>]") for u in set(embedded_raw) if len(u) < 512][
                :100
            ]

            return {
                "url": str(resp.url),
                "status_code": resp.status_code,
                "content_type": "application/pdf",
                "content_truncated": truncated,
                "redirects": redirects_followed,
                "pdf_pages": len(reader.pages),
                "embedded_links": embedded_links,
            }, text
        except Exception as pdf_err:
            logger.warning("pdf_extraction_failed", url=current_url, error=str(pdf_err))
            return {
                "url": str(resp.url),
                "status_code": resp.status_code,
                "content_type": "application/pdf",
                "error": f"pdf_parse_error: {pdf_err}",
                "content_truncated": False,
                "embedded_links": [],
            }, f"[PDF Parse Error: {pdf_err}]"

    allowed_types = ("text/", "application/json", "application/xml", "application/xhtml+xml")
    if not any(t in content_type for t in allowed_types):
        return {
            "url": str(resp.url),
            "status_code": resp.status_code,
            "blocked_content_type": content_type,
            "content_truncated": False,
            "embedded_links": [],
        }, f"[Blocked Content-Type: {content_type}]"

    raw_body = resp.content[:MAX_BODY_BYTES]
    try:
        html_str = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        html_str = raw_body.decode("latin1", errors="replace")

    text = extract_readable_text(html_str)
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    embedded_raw = re.findall(r"https?://[^\s<>\"'()]+", html_str)
    embedded_links = [u.rstrip(".,;:!?'\")>]") for u in set(embedded_raw) if len(u) < 512][:100]

    structured = {
        "url": str(resp.url),
        "status_code": resp.status_code,
        "content_type": content_type,
        "content_truncated": truncated,
        "redirects": redirects_followed,
        "embedded_links": embedded_links,
    }

    return structured, text
