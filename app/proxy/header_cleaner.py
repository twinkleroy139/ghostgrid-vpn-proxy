"""
app/proxy/header_cleaner.py

Header hygiene for proxied requests and responses.

Design intent (per GhostGrid architecture):
  - curl_cffi(impersonate="chrome124") already generates a complete, internally
    consistent set of Chrome headers. We must NOT override them — otherwise the
    TLS fingerprint and the header fingerprint disagree, and WAFs reject.
  - We only add headers the client's browser sent that curl_cffi cannot know:
    Host (target), Referer (only if client sent a real one), Origin (only for
    state-changing methods when the client sent one).
  - On the response side, we strip hop-by-hop + problem headers but preserve
    upstream CORS headers. We only synthesize ACAO on JSON responses.
"""

from typing import Dict, Set

HOP_BY_HOP_HEADERS: Set[str] = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

# Headers we ALWAYS strip from the client request before forwarding upstream.
# NOTE: we do NOT strip user-agent, accept-language, accept-encoding, or
# sec-fetch-* anymore — curl_cffi sets those and impersonation requires them.
BLOCKED_REQUEST_HEADERS: Set[str] = {
    "host",
    "content-length",          # curl_cffi recomputes for the actual body
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "x-forwarded-port",
    "x-real-ip",
    "cf-connecting-ip",
    "cf-ray",
    "cf-visitor",
    "connection",
    "keep-alive",
    "proxy-authorization",
}

# Response headers we strip because they break in-iframe rendering or
# conflict with GhostGrid's own policy.
BLOCKED_RESPONSE_HEADERS: Set[str] = {
    "content-security-policy",
    "content-security-policy-report-only",
    "x-frame-options",         # critical — needed to embed in iframe
    "strict-transport-security",
    "clear-site-data",
    "content-encoding",        # we already decode on the backend
    "content-length",          # FastAPI recomputes
}

# Methods that legitimately carry an Origin header.
METHODS_WITH_ORIGIN: Set[str] = {"POST", "PUT", "PATCH", "DELETE"}


def _is_http_url(value: str) -> bool:
    v = value.strip().lower()
    return v.startswith("http://") or v.startswith("https://")


def sanitize_request_headers(
    headers: Dict[str, str], target_host: str, method: str = "GET"
) -> Dict[str, str]:
    """
    Build the outgoing upstream request headers.

    - Blocks hop-by-hop and known-bad headers.
    - Sets Host to the target.
    - Preserves client Referer only if it looks real.
    - Preserves client Origin only for state-changing methods.
    - Does NOT touch User-Agent, Accept-*, Sec-Fetch-* — curl_cffi owns those.
    """
    sanitized: Dict[str, str] = {}
    method_upper = method.upper()
    original_referer: str = ""
    original_origin: str = ""

    for key, value in headers.items():
        k_lower = key.lower()
        if k_lower in HOP_BY_HOP_HEADERS or k_lower in BLOCKED_REQUEST_HEADERS:
            continue
        # Capture the client-provided values we might re-emit later.
        if k_lower == "referer":
            original_referer = value
            continue  # decided below
        if k_lower == "origin":
            original_origin = value
            continue  # decided below
        sanitized[key] = value

    # Host is required and must be the upstream target.
    sanitized["Host"] = target_host

    # Referer: only forward if the client actually sent one. Fabricating a
    # Referer on cold navigations is a strong bot signal.
    if original_referer and _is_http_url(original_referer):
        sanitized["Referer"] = original_referer

    # Origin: only for state-changing methods. Prefer the client's Origin
    # (which correctly identifies the initiating page). Fall back to the
    # target origin only for same-origin POSTs where the browser omitted it.
    if method_upper in METHODS_WITH_ORIGIN:
        if original_origin and _is_http_url(original_origin):
            sanitized["Origin"] = original_origin
        else:
            sanitized["Origin"] = f"https://{target_host}"

    return sanitized


def sanitize_response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Clean upstream response headers before sending to the browser.

    Preserves upstream CORS headers when present. Synthesizes
    `Access-Control-Allow-Origin: *` ONLY for JSON responses (the common case
    where a proxied SPA needs to read the API response cross-origin).
    """
    sanitized: Dict[str, str] = {}

    for key, value in headers.items():
        k_lower = key.lower()
        if k_lower in HOP_BY_HOP_HEADERS or k_lower in BLOCKED_RESPONSE_HEADERS:
            continue
        sanitized[key] = value

    # Only synthesize CORS headers where they're actually needed by a proxied
    # frontend: JSON/JS API responses. Do NOT add them to images/CSS/HTML —
    # doing so is a cache-poisoning and browser-security hazard.
    content_type = sanitized.get("content-type", "").lower()
    needs_cors = "application/json" in content_type or "javascript" in content_type
    has_upstream_cors = "access-control-allow-origin" in {k.lower() for k in sanitized.keys()}

    if needs_cors and not has_upstream_cors:
        sanitized["Access-Control-Allow-Origin"] = "*"
        sanitized["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        sanitized["Access-Control-Allow-Headers"] = "*"

    sanitized["X-Proxy-Engine"] = "GhostGrid-Cyberpunk-Core"
    return sanitized