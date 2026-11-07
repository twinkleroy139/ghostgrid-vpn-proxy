"""
app/proxy/html_rewriter.py

GhostGrid Backend HTML Rewriter.

Rewrites static HTML navigation / subresource URLs to route through GhostGrid's
/proxy/fetch endpoint. Emits ABSOLUTE proxy URLs (scheme://host/proxy/fetch?...)
so they survive the injected <base href="<upstream>"> tag — a relative URL would
otherwise resolve against the upstream origin and double-wrap through the SW.
"""

import logging
from typing import Optional
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.proxy.url_encoder import encode_url

logger = logging.getLogger("ghostgrid.rewriter")

PROXY_ENDPOINT = "/proxy/fetch"

SKIPPED_SCHEMES = {
    "javascript", "data", "blob", "mailto", "tel", "sms", "file",
    "about", "chrome", "chrome-extension", "moz-extension", "ws", "wss",
}

LINK_REWRITE_RELS = {"stylesheet", "icon", "manifest", "preload", "modulepreload"}

ATTRIBUTE_MAP = [
    ("a", "href"),
    ("area", "href"),
    ("form", "action"),
    ("img", "src"),
    ("img", "srcset"),
    ("source", "src"),
    ("source", "srcset"),
    ("script", "src"),
    ("link", "href"),          # filtered by rel
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


# ---------------------------------------------------------------- helpers

def _split_fragment(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    return clean, fragment


def _build_proxy_url(target_url: str, node: str, proxy_origin: str) -> str:
    clean, fragment = _split_fragment(target_url)
    query = urlencode({"url": encode_url(clean), "node": node or "direct"})
    return f"{proxy_origin.rstrip('/')}{PROXY_ENDPOINT}?{query}{fragment}"


def _is_already_proxied(value: str) -> bool:
    try:
        p = urlsplit(value)
        return p.path == PROXY_ENDPOINT
    except (ValueError, TypeError):
        return False


def _should_rewrite(value: str) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or v.startswith("#") or _is_already_proxied(v):
        return False
    lowered = v.lower()
    if any(lowered.startswith(f"{s}:") for s in SKIPPED_SCHEMES):
        return False
    return True


def _resolve_and_proxy(
    original: str, base_url: str, node: str, proxy_origin: str
) -> Optional[str]:
    if not _should_rewrite(original):
        return None
    try:
        absolute = urljoin(base_url, original.strip())
        parsed = urlsplit(absolute)
        if parsed.scheme.lower() not in ("http", "https"):
            return None
        if not parsed.netloc:
            return None
        return _build_proxy_url(absolute, node, proxy_origin)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- element rewriters

def _rewrite_simple_attr(element, attribute: str, base_url: str, node: str, proxy_origin: str) -> bool:
    original = element.get(attribute)
    proxied = _resolve_and_proxy(original, base_url, node, proxy_origin) if original is not None else None
    if proxied is None:
        return False
    element[attribute] = proxied
    return True


def _rewrite_link_element(element, base_url: str, node: str, proxy_origin: str) -> bool:
    rel_attr = element.get("rel") or []
    rels = {r.lower() for r in (rel_attr if isinstance(rel_attr, list) else [rel_attr])}
    if not (rels & LINK_REWRITE_RELS):
        return False
    return _rewrite_simple_attr(element, "href", base_url, node, proxy_origin)


def _rewrite_srcset(element, base_url: str, node: str, proxy_origin: str) -> bool:
    srcset = element.get("srcset")
    if not isinstance(srcset, str) or not srcset.strip():
        return False
    entries, changed = [], False
    for entry in srcset.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(None, 1)
        url_part = parts[0]
        descriptor = f" {parts[1]}" if len(parts) > 1 else ""
        proxied = _resolve_and_proxy(url_part, base_url, node, proxy_origin)
        if proxied is not None:
            entries.append(f"{proxied}{descriptor}")
            changed = True
        else:
            entries.append(f"{url_part}{descriptor}")
    if changed:
        element["srcset"] = ", ".join(entries)
    return changed


# ---------------------------------------------------------------- public API

def rewrite_html_links(
    html_text: str,
    base_url: str,
    node: str = "direct",
    proxy_origin: str = "",
) -> str:
    """
    Rewrite navigation and subresource URLs to route through GhostGrid.
    `proxy_origin` MUST be the absolute scheme://host of the GhostGrid app
    (e.g. https://ghostgrid.example) so emitted URLs survive the <base> tag.
    """
    if not html_text or not base_url or not proxy_origin:
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
                    _rewrite_link_element(element, base_url, node, proxy_origin)
                elif attribute == "srcset":
                    _rewrite_srcset(element, base_url, node, proxy_origin)
                else:
                    _rewrite_simple_attr(element, attribute, base_url, node, proxy_origin)

        return str(soup)

    except Exception as exc:
        logger.warning("rewriter fail-open url=%s cls=%s msg=%s",
                       base_url, exc.__class__.__name__, exc)
        return html_text