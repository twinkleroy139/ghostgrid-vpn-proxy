import re
from urllib.parse import urlparse
from app.security.blocklist import is_domain_blocked
from app.security.ssrf_guard import validate_url_against_ssrf

# Strict URL scheme validator
ALLOWED_SCHEMES = {"http", "https"}


def sanitize_and_validate_target_url(raw_url: str) -> str:
    """
    Complete security gatekeeper for any inbound proxy target URL.
    1. Trims and cleans whitespace and control characters.
    2. Validates scheme (only http/https permitted).
    3. Verifies domain against the blocklist.
    4. Triggers DNS SSRF inspection to ensure no private/cloud metadata IPs are hit.
    Returns cleaned canonical URL string, or raises ValueError.
    """
    if not raw_url:
        raise ValueError("URL cannot be empty.")

    cleaned = raw_url.strip()

    # Prepend https:// if protocol was omitted
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", cleaned):
        cleaned = "https://" + cleaned

    parsed = urlparse(cleaned)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(f"Prohibited scheme: '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    if not parsed.netloc:
        raise ValueError("Malformed URL: missing host or network location.")

    # Blocklist Check
    if is_domain_blocked(cleaned):
        raise ValueError(f"Access to domain '{parsed.hostname}' is prohibited by safety policy.")

    # SSRF Resolution & Verification Check
    validate_url_against_ssrf(cleaned)

    return cleaned