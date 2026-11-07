"""
app/proxy/css_rewriter.py

Rewrites url(...) references inside upstream CSS text so relative subresources
(fonts, background images, @import targets) resolve against the upstream host
— not against GhostGrid's own origin, where they'd 404.

Why regex, not a CSS parser:
  - Adding tinycss2/html5lib to requirements is out of scope for this fix.
  - CSS url() and @import syntax is simple enough to handle reliably.
  - Malformed CSS is preserved verbatim (fail-open).
"""

import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.proxy.url_encoder import encode_url

logger = logging.getLogger("ghostgrid.css_rewriter")

PROXY_ENDPOINT = "/proxy/fetch"
SKIPPED_SCHEMES = ("data:", "blob:", "chrome-extension:", "moz-extension:")

# Matches url(...) with optional quotes. Captures the raw interior.
_URL_RE = re.compile(
    r"""url\(\s*(['"]?)(?P<url>(?:\\.|[^\\'")])*)\1\s*\)""",
    re.IGNORECASE,
)

# Matches @import "..." or @import '...' or @import url(...)
_IMPORT_QUOTED_RE = re.compile(
    r"""@import\s+(['"])(?P<url>[^'"]+)\1""",
    re.IGNORECASE,
)


def _split_fragment(url: str) -> tuple[str, str]:
    p = urlsplit(url)
    fragment = f"#{p.fragment}" if p.fragment else ""
    clean = urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))
    return clean, fragment


def _is_already_proxied(value: str) -> bool:
    try:
        return urlsplit(value).path == PROXY_ENDPOINT
    except (ValueError, TypeError):
        return False


def _should_rewrite(value: str) -> bool:
    if not value:
        return False
    v = value.strip()
    if not v or v.startswith("#"):
        return False
    if _is_already_proxied(v):
        return False
    lowered = v.lower()
    if any(lowered.startswith(s) for s in SKIPPED_SCHEMES):
        return False
    return True


def _build_proxy_url(target_url: str, node: str, proxy_origin: str) -> str:
    clean, fragment = _split_fragment(target_url)
    return f"{proxy_origin.rstrip('/')}{PROXY_ENDPOINT}?url={encode_url(clean)}&node={node or 'direct'}{fragment}"


def _resolve_and_proxy(
    original: str, css_base_url: str, node: str, proxy_origin: str
) -> Optional[str]:
    if not _should_rewrite(original):
        return None
    try:
        absolute = urljoin(css_base_url, original.strip())
        p = urlsplit(absolute)
        if p.scheme.lower() not in ("http", "https"):
            return None
        if not p.netloc:
            return None
        return _build_proxy_url(absolute, node, proxy_origin)
    except (ValueError, TypeError):
        return None


def _rewrite_url_token(
    quote: str, inner: str, css_base_url: str, node: str, proxy_origin: str
) -> str:
    proxied = _resolve_and_proxy(inner, css_base_url, node, proxy_origin)
    if proxied is None:
        return f"url({quote}{inner}{quote})"
    return f"url({quote}{proxied}{quote})"


def rewrite_css(
    css_text: str,
    css_base_url: str,
    node: str = "direct",
    proxy_origin: str = "",
) -> str:
    """
    Rewrite every url(...) and @import "..." inside CSS so relative references
    resolve against the upstream host via GhostGrid's proxy.
    """
    if not css_text or not css_base_url or not proxy_origin:
        return css_text

    try:
        base_parts = urlsplit(css_base_url)
        if base_parts.scheme.lower() not in ("http", "https"):
            return css_text
        if not base_parts.netloc:
            return css_text
    except (ValueError, TypeError):
        return css_text

    def url_replacer(m: re.Match) -> str:
        quote = m.group(1) or ""
        inner = m.group("url")
        return _rewrite_url_token(quote, inner, css_base_url, node, proxy_origin)

    def import_replacer(m: re.Match) -> str:
        quote = m.group(1) or '"'
        inner = m.group("url")
        proxied = _resolve_and_proxy(inner, css_base_url, node, proxy_origin)
        if proxied is None:
            return m.group(0)
        return f"@import {quote}{proxied}{quote}"

    try:
        # Rewrite @import "..." first (before generic url() would catch its content).
        out = _IMPORT_QUOTED_RE.sub(import_replacer, css_text)
        # Then every url(...) anywhere else.
        out = _URL_RE.sub(url_replacer, out)
        return out
    except Exception as exc:
        logger.warning(
            "css_rewriter fail-open url=%s cls=%s msg=%s",
            css_base_url, exc.__class__.__name__, exc,
        )
        return css_text