"""
GhostGrid Backend HTML Rewriter

Rewrites upstream HTML anchor and form destinations
to route through GhostGrid's /proxy/fetch endpoint.
"""

from typing import Optional
from urllib.parse import urljoin, urlencode, urlsplit

from bs4 import BeautifulSoup

from app.proxy.url_encoder import encode_url


PROXY_ENDPOINT = "/proxy/fetch"

# Schemes that must never be sent through the HTTP proxy.
SKIPPED_SCHEMES = {
    "javascript",
    "data",
    "blob",
    "mailto",
    "tel",
    "sms",
    "file",
}


def _build_proxy_url(target_url: str, node: str) -> str:
    """Build a GhostGrid proxy URL for an absolute HTTP(S) target."""

    query = urlencode({
        "url": encode_url(target_url),
        "node": node or "direct",
    })

    return f"{PROXY_ENDPOINT}?{query}"


def _rewrite_attribute(
    element,
    attribute: str,
    base_url: str,
    node: str,
) -> bool:
    """Rewrite one HTML navigation attribute when it targets HTTP(S)."""

    original_url = element.get(attribute)

    if not isinstance(original_url, str):
        return False

    original_url = original_url.strip()

    if not original_url:
        return False

    # Keep fragment-only links inside the current document.
    if original_url.startswith("#"):
        return False

    # Preserve non-HTTP browser actions.
    if original_url.lower().startswith(
        tuple(f"{scheme}:" for scheme in SKIPPED_SCHEMES)
    ):
        return False

    try:
        absolute_url = urljoin(base_url, original_url)
        parsed = urlsplit(absolute_url)

        if parsed.scheme.lower() not in ("http", "https"):
            return False

        if not parsed.netloc:
            return False

        element[attribute] = _build_proxy_url(absolute_url, node)
        return True

    except (ValueError, TypeError):
        return False


def rewrite_html_links(
    html_text: str,
    base_url: str,
    node: str = "direct",
) -> str:
    """
    Rewrite upstream HTML navigation destinations.

    Supported:
        <a href="...">
        <form action="...">

    Relative and absolute HTTP(S) URLs are resolved against base_url.

    JavaScript, data, blob, mailto, tel, SMS, file and fragment-only
    destinations remain unchanged.
    """

    if not html_text or not base_url:
        return html_text

    try:
        base_parts = urlsplit(base_url)

        if base_parts.scheme.lower() not in ("http", "https"):
            return html_text

        if not base_parts.netloc:
            return html_text

        soup = BeautifulSoup(html_text, "html.parser")

        # Rewrite hyperlinks.
        for anchor in soup.find_all("a", href=True):
            _rewrite_attribute(
                anchor,
                "href",
                base_url,
                node,
            )

        # Rewrite form submission destinations.
        for form in soup.find_all("form", action=True):
            _rewrite_attribute(
                form,
                "action",
                base_url,
                node,
            )

        return str(soup)

    except Exception:
        # Fail open: preserve the original HTML if parsing fails.
        return html_text