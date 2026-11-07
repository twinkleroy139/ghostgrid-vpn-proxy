"""
app/proxy/waf_detector.py

Detects WAF bot-protection challenge pages returned by upstream sites.

PerimeterX, Cloudflare, DataDome, Akamai, Imperva, and similar vendors serve
these pages in place of real content when they suspect the request is from a bot
or a non-browser client. GhostGrid's proxy (curl_cffi + SOCKS5 VPN) cannot
execute the JS challenges these pages require, so we surface an honest
error instead of relaying a broken challenge body to the browser iframe.

Signature-based only — no new dependencies.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("ghostgrid.waf")

# Body/header signatures, ranked by specificity.
# We require at least one match to declare a challenge.
WAF_SIGNATURES = {
    "PerimeterX": [
        b"PerimeterX", b"_pxAppId", b"px-captcha", b"captcha.px-cdn.net",
        b"px-cloud.net", b"pxchk.px-cloud.net",
    ],
    "Cloudflare": [
        b"__cf_chl_", b"cf-chl-", b"cloudflare", b"Just a moment...",
        b"Attention Required! | Cloudflare", b"cf-mitigated",
        b"cf_error", b"Ray ID:",
    ],
    "DataDome": [
        b"datadome", b"dd_captcha", b"geo.captcha-delivery.com",
    ],
    "Akamai": [
        b"Access Denied", b"Reference&#32;&#35;", b"akamai",
        b"_abck", b"sec_cpt",
    ],
    "Imperva": [
        b"incapsula", b"_Incapsula_Resource", b"Incapsula incident",
        b"Request unsuccessful. Incapsula",
    ],
    "Distil": [
        b"distil", b"distilnetworks", b"distil_r_captcha",
    ],
    "AWS WAF": [
        b"AWS WAF", b"aws-waf-token", b"awswaf",
    ],
    "Sucuri": [
        b"Sucuri WebSite Firewall", b"sucuri.net", b"Access Denied - Sucuri",
    ],
}

# Status codes most associated with challenges.
CHALLENGE_STATUSES = {403, 429, 503}

# Body size bounds for a plausible challenge page.
MIN_CHALLENGE_SIZE = 200
MAX_CHALLENGE_SIZE = 600 * 1024  # 600 KB

# Static list of hosts that are known to always return challenges to proxies.
# Add to this as you discover sites that block GhostGrid.
KNOWN_WAF_HOSTS = {
    # People-search / data brokers (PerimeterX, Akamai)
    "truepeoplesearch.com": "PerimeterX",
    "usphonebook.com": "Akamai",
    "whitepages.com": "Akamai",
    "fastpeoplesearch.com": "PerimeterX",
    "spokeo.com": "PerimeterX",
    "beenverified.com": "PerimeterX",
    "intelius.com": "PerimeterX",
    "peoplefinders.com": "PerimeterX",
    "radaris.com": "Akamai",
    # Social / big-tech (Cloudflare, DataDome)
    "instagram.com": "Cloudflare",
    "facebook.com": "Cloudflare",
    "tiktok.com": "DataDome",
    "twitter.com": "Cloudflare",
    "x.com": "Cloudflare",
    "linkedin.com": "Akamai",
    "reddit.com": "Cloudflare",
    # E-commerce / ticketing (Akamai, DataDome)
    "ticketmaster.com": "Akamai",
    "amazon.com": "Akamai",
    "walmart.com": "Akamai",
    "bestbuy.com": "Akamai",
    "target.com": "Akamai",
    # Banking / finance (Akamai, Imperva)
    "chase.com": "Akamai",
    "bankofamerica.com": "Akamai",
    # News sites that gate by bot detection
    "nytimes.com": "Cloudflare",
    "wsj.com": "Cloudflare",
}


def _as_lower_bytes(data: bytes) -> bytes:
    """Return lowercase bytes for case-insensitive matching."""
    try:
        return data.lower()
    except Exception:
        return data


def _body_contains_any(body_lower: bytes, signatures: list) -> bool:
    """True if any signature (bytes) appears in the lowercased body."""
    for sig in signatures:
        try:
            if sig.lower() in body_lower:
                return True
        except Exception:
            continue
    return False


def is_known_waf_host(hostname: str) -> Optional[str]:
    """
    Look up a hostname against KNOWN_WAF_HOSTS.
    Matches exact hostname OR any subdomain of a known host.
    Returns vendor name or None.
    """
    if not hostname:
        return None
    h = hostname.lower().strip()

    # Strip leading "www." for matching against base domain
    candidates = [h]
    if h.startswith("www."):
        candidates.append(h[4:])

    for cand in candidates:
        if cand in KNOWN_WAF_HOSTS:
            return KNOWN_WAF_HOSTS[cand]

    # Also check subdomain match (e.g., api.truepeoplesearch.com)
    for base, vendor in KNOWN_WAF_HOSTS.items():
        if h.endswith("." + base):
            return vendor

    return None


def detect_waf_challenge(
    response_body: bytes,
    status_code: int,
    content_type: str,
    url: str = "",
) -> Optional[str]:
    """
    Inspect an upstream response and return the WAF vendor name if it's a
    bot-protection challenge page, or None if it looks like real content.

    Heuristics:
      - Body size must be plausible (200 B – 600 KB)
      - Status must be 200, 403, 429, or 503
      - Content-Type must be text/html or text/plain (challenges are HTML/plain)
      - Body must contain a signature string for exactly one vendor
    """
    if not response_body or not content_type:
        return None

    body_len = len(response_body)
    if body_len < MIN_CHALLENGE_SIZE or body_len > MAX_CHALLENGE_SIZE:
        return None

    ct_lower = content_type.lower()
    if "html" not in ct_lower and "text/plain" not in ct_lower:
        return None

    if status_code not in CHALLENGE_STATUSES and status_code != 200:
        return None

    body_lower = _as_lower_bytes(response_body)

    # Check each vendor's signatures
    for vendor, signatures in WAF_SIGNATURES.items():
        if _body_contains_any(body_lower, signatures):
            logger.info(
                "WAF challenge detected: vendor=%s url=%s status=%d bytes=%d",
                vendor, url, status_code, body_len,
            )
            return vendor

    return None


def classify_target_for_ui(url: str) -> Optional[dict]:
    """
    Pre-request check: if the target host is in KNOWN_WAF_HOSTS, return
    {"vendor": "...", "host": "..."} so the UI can warn the user up front.
    Returns None for hosts not on the list.
    """
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return None

    host = (parsed.hostname or "").lower()
    if not host:
        return None

    vendor = is_known_waf_host(host)
    if vendor:
        return {"vendor": vendor, "host": host}
    return None