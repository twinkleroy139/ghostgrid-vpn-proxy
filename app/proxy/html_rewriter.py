"""
app/proxy/html_rewriter.py

GhostGrid Backend HTML Rewriter (Option 1: bulletproof static rewriting).

Rewrites every static HTTP(S)-navigation / subresource reference in upstream
HTML to route through GhostGrid's /proxy/fetch endpoint. Idempotent — a URL
already wrapped in /proxy/fetch is left untouched. Fragments are preserved
by appending them after the proxy URL.
"""

import logging
from typing import Optional
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.proxy.url_encoder import encode_url

logger = logging.getLogger("ghostgrid.rewriter")

PROXY_ENDPOINT = "/proxy/fetch"

# Schemes that must never go through the HTTP proxy.
SKIPPED_SCHEMES = {
    "javascript",
    "data",
    "blob",
    "mailto",
    "tel",
    "sms",
    "file",
    "about",
    "chrome",
    "chrome-extension",
    "moz-extension",
    "ws",   # WebSocket URLs must not be wrapped; ws_proxy has its own route
    "wss",
}

# <link> rel values we WILL rewrite. Everything else (canonical, alternate,
# preconnect, dns-prefetch, etc.) is left pointing at upstream.
LINK_REWRITE_RELS = {"stylesheet", "icon", "manifest", "preload", "modulepreload"}

# (tag, attribute) pairs that represent fetchable HTTP(S) resources.
ATTRIBUTE_MAP = [
    ("a", "href"),
    ("area", "href"),
    ("form", "action"),
    ("img", "src"),
    ("img", "srcset"),
    ("source", "src"),
    ("source", "srcset"),
    ("script", "src"),
    ("link", "href"),          # filtered by rel below
    ("iframe", "src"),
    ("video", "src"),
    ("video", "poster"),
    ("audio", "src"),
    ("track", "src"),
    ("object", "data"),
    ("embed", "src"),
    ("input", "formaction"),
    ("button", "formaction"),
]


# ---------------------------------------------------------------- URL helpers

def _is_already_proxied(value: str) -> bool:
    return value.startswith(PROXY_ENDPOINT) or value.startswith(f"http://{_host()}{PROXY_ENDPOINT}") \
        or value.startswith(f"https://{_host()}{PROXY_ENDPOINT}")


def _host() -> str:
    return "ghostgrid.local"


def _split_fragment(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    return clean, fragment


def _build_proxy_url(target_url: str, node: str) -> str:
    clean, fragment = _split_fragment(target_url)
    query = urlencode({
        "url": encode_url(clean),
        "node": node or "direct",
    })
    return f"{PROXY_ENDPOINT}?{query}{fragment}"


def _should_rewrite_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return False
    if v.startswith("#"):
        return False
    if _is_already_proxied(v):
        return False
    lowered = v.lower()
    if any(lowered.startswith(f"{s}:") for s in SKIPPED_SCHEMES):
        return False
    return True


def _resolve_and_proxy(original: str, base_url: str, node: str) -> Optional[str]:
    """Return the proxy URL for `original`, or None if it should be left alone."""
    if not _should_rewrite_url(original):
        return None
    try:
        absolute = urljoin(base_url, original.strip())
        parsed = urlsplit(absolute)
        if parsed.scheme.lower() not in ("http", "https"):
            return None
        if not parsed.netloc:
            return None
        return _build_proxy_url(absolute, node)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- element rewriters

def _rewrite_simple_attr(element, attribute: str, base_url: str, node: str) -> bool:
    original = element.get(attribute)
    proxied = _resolve_and_proxy(original, base_url, node) if original is not None else None
    if proxied is None:
        return False
    element[attribute] = proxied
    return True


def _rewrite_link_element(element, base_url: str, node: str) -> bool:
    rel_attr = element.get("rel") or []
    rels = {r.lower() for r in (rel_attr if isinstance(rel_attr, list) else [rel_attr])}
    if not (rels & LINK_REWRITE_RELS):
        return False
    return _rewrite_simple_attr(element, "href", base_url, node)


def _rewrite_srcset(element, base_url: str, node: str) -> bool:
    srcset = element.get("srcset")
    if not isinstance(srcset, str) or not srcset.strip():
        return False
    rewritten_entries = []
    changed = False
    for entry in srcset.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(None, 1)
        url_part = parts[0]
        descriptor = f" {parts[1]}" if len(parts) > 1 else ""
        proxied = _resolve_and_proxy(url_part, base_url, node)
        if proxied is not None:
            rewritten_entries.append(f"{proxied}{descriptor}")
            changed = True
        else:
            rewritten_entries.append(f"{url_part}{descriptor}")
    if changed:
        element["srcset"] = ", ".join(rewritten_entries)
    return changed


# ---------------------------------------------------------------- public API

def rewrite_html_links(
    html_text: str,
    base_url: str,
    node: str = "direct",
) -> str:
    """
    Rewrite every static navigation / subresource reference in upstream HTML
    to route through GhostGrid. Idempotent — already-proxied URLs are left alone.
    """
    if not html_text or not base_url:
        return html_text

    try:
        base_parts = urlsplit(base_url)
        if base_parts.scheme.lower() not in ("http", "https"):
            return html_text
        if not base_parts.netloc:
            return html_text
    except (ValueError, TypeError):
        return html_text

    try:
        soup = BeautifulSoup(html_text, "html.parser")

        for tag_name, attribute in ATTRIBUTE_MAP:
            for element in soup.find_all(tag_name):
                if tag_name == "link" and attribute == "href":
                    _rewrite_link_element(element, base_url, node)
                elif attribute == "srcset":
                    _rewrite_srcset(element, base_url, node)
                else:
                    _rewrite_simple_attr(element, attribute, base_url, node)

        return str(soup)

    except Exception as exc:
        # Fail open — preserve original HTML — but log so we can see it in Render.
        logger.warning(
            "rewriter fail-open url=%s cls=%s msg=%s",
            base_url, exc.__class__.__name__, exc,
        )
        return html_text