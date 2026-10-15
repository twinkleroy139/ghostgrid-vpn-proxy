from typing import Dict, Set

# Headers that must NEVER be forwarded to upstream target servers (prevents leaks)
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

# Request headers to strip to prevent tracking, leaks, and compression mismatches
BLOCKED_REQUEST_HEADERS: Set[str] = {
    "host",
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "x-forwarded-port",
    "x-real-ip",
    "cf-connecting-ip",
    "cf-ray",
    "cf-visitor",
    "accept-encoding",  # Strip so httpx automatically negotiates and decompresses content
    "content-length",
}

# Response headers to strip so proxied sites can be framed, styled, and loaded safely
BLOCKED_RESPONSE_HEADERS: Set[str] = {
    "content-security-policy",
    "content-security-policy-report-only",
    "x-frame-options",
    "strict-transport-security",
    "clear-site-data",
    "content-encoding",  # Stripped because httpx yields decompressed text/data
    "content-length",    # Stripped because DOM and CSS rewriting changes payload length
}


def sanitize_request_headers(
    headers: Dict[str, str], target_host: str
) -> Dict[str, str]:
    """
    Cleans incoming client headers before sending request upstream.
    Sets genuine host header and realistic User-Agent.
    Does NOT manually inject Accept-Encoding so httpx can decompress natively.
    """
    sanitized: Dict[str, str] = {}

    for key, value in headers.items():
        k_lower = key.lower()
        if k_lower in HOP_BY_HOP_HEADERS or k_lower in BLOCKED_REQUEST_HEADERS:
            continue
        sanitized[key] = value

    # Set appropriate Host header for upstream destination
    sanitized["Host"] = target_host

    # Standardize User-Agent
    sanitized["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 GhostGrid/1.0"
    )

    return sanitized


def sanitize_response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Cleans upstream response headers before sending back to client browser.
    Removes frame-busting, CSP barriers, and stale encoding lengths.
    """
    sanitized: Dict[str, str] = {}

    for key, value in headers.items():
        k_lower = key.lower()
        if k_lower in HOP_BY_HOP_HEADERS or k_lower in BLOCKED_RESPONSE_HEADERS:
            continue
        sanitized[key] = value

    # Add custom GhostGrid debugging identifier
    sanitized["X-Proxy-Engine"] = "GhostGrid-Cyberpunk-Core"
    return sanitized