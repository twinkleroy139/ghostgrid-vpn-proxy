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
    headers: Dict[str, str], target_host: str, method: str = "GET"
) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}

    for key, value in headers.items():
        k_lower = key.lower()
        if k_lower in HOP_BY_HOP_HEADERS or k_lower in BLOCKED_REQUEST_HEADERS:
            continue
        sanitized[key] = value

    sanitized["Host"] = target_host

    # Only attach Origin/Referer on state-modifying requests, never on static GETs
    target_origin = f"https://{target_host}"
    if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
        sanitized["Origin"] = target_origin
        sanitized["Referer"] = f"{target_origin}/"

    sanitized["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    sanitized["Accept-Language"] = "en-US,en;q=0.9"

    return sanitized


def sanitize_response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}

    for key, value in headers.items():
        k_lower = key.lower()
        if k_lower in HOP_BY_HOP_HEADERS or k_lower in BLOCKED_RESPONSE_HEADERS:
            continue
        sanitized[key] = value

    sanitized["Access-Control-Allow-Origin"] = "*"
    sanitized["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    sanitized["Access-Control-Allow-Headers"] = "*"
    sanitized["X-Proxy-Engine"] = "GhostGrid-Cyberpunk-Core"
    return sanitized