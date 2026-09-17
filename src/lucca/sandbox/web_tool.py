"""
Project Lucca — Hardened Web Fetch & SSRF Guard
Spec 09 §5, ADR-003, ADR-004, TM-03b
"""

import importlib
import ipaddress
import re
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from lucca.core.exceptions import SandboxPathError

logger = structlog.get_logger(__name__)

MAX_URL_LEN: int = 512
MAX_QUERY_LEN: int = 128
MAX_BODY_BYTES: int = 2 * 1024 * 1024  # 2 MiB
MAX_REDIRECTS: int = 8
DEFAULT_MAX_CHARS: int = 20000

CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")


def _get_trafilatura_extract() -> Callable[..., Any] | None:
    try:
        mod = importlib.import_module("trafilatura")
        fn = getattr(mod, "extract", None)
        return fn if callable(fn) else None
    except ImportError:
        return None


def validate_url_ssrf(url: str) -> tuple[str, str]:
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
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as err:
        raise SandboxPathError("dns_failed", f"Failed to resolve host '{hostname}': {err}") from err

    resolved_ip = ""
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as err:
            raise SandboxPathError(
                "invalid_ip", f"Resolved invalid IP '{ip_str}': {err}"
            ) from err

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
) -> tuple[dict[str, Any], str]:
    """
    Executes a hardened, SSRF-guarded HTTP GET request.
    Validates every redirect hop against the SSRF resolver.
    """
    valid_url, _ = validate_url_ssrf(url)

    headers = {
        "User-Agent": "Lucca/1.0 (+https://github.com/seatr/ProjectLucca)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip",
    }

    current_url = valid_url
    redirects_followed = 0

    with httpx.Client(timeout=httpx.Timeout(15.0, connect=10.0), follow_redirects=False) as client:
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
            break

    content_type = resp.headers.get("content-type", "").lower()
    allowed_types = ("text/", "application/json", "application/xml", "application/xhtml+xml")
    if not any(t in content_type for t in allowed_types):
        return {
            "url": str(resp.url),
            "status_code": resp.status_code,
            "blocked_content_type": content_type,
            "content_truncated": False,
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

    structured = {
        "url": str(resp.url),
        "status_code": resp.status_code,
        "content_type": content_type,
        "content_truncated": truncated,
        "redirects": redirects_followed,
    }

    return structured, text
