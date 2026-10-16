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
    "accept-encoding",
    "content-length",
}

BLOCKED_RESPONSE_HEADERS: Set[str] = {
    "content-security-policy",
    "content-security-policy-report-only",
    "x-frame-options",
    "strict-transport-security",
    "clear-site-data",
    "content-encoding",
    "content-length",
}


def sanitize_request_headers(
    headers: Dict[str, str], target_host: str
) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}

    for key, value in headers.items():
        k_lower = key.lower()
        if k_lower in HOP_BY_HOP_HEADERS or k_lower in BLOCKED_REQUEST_HEADERS:
            continue
        sanitized[key] = value

    sanitized["Host"] = target_host

    # Authentic Desktop Browser Fingerprint
    sanitized["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    sanitized["Accept-Language"] = "en-US,en;q=0.9"

    # Forward or set appropriate client hints
    if "sec-ch-ua" not in sanitized:
        sanitized["sec-ch-ua"] = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'
        sanitized["sec-ch-ua-mobile"] = "?0"
        sanitized["sec-ch-ua-platform"] = '"Windows"'

    return sanitized


def sanitize_response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}

    for key, value in headers.items():
        k_lower = key.lower()
        if k_lower in HOP_BY_HOP_HEADERS or k_lower in BLOCKED_RESPONSE_HEADERS:
            continue
        sanitized[key] = value

    sanitized["X-Proxy-Engine"] = "GhostGrid-Cyberpunk-Core"
    return sanitized