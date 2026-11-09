"""
app/proxy/waf_detector.py

Detects WAF bot-protection challenge pages returned by upstream sites.

Host categories:
  HARD_WAF_HOSTS  — every endpoint is gated. Preemptively block top-level nav.
  SOFT_WAF_HOSTS  — only some endpoints (search APIs) are gated. Fetch first,
                    then detect on response so partial success is preserved.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("ghostgrid.waf")

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

CHALLENGE_STATUSES = {403, 429, 503}
MIN_CHALLENGE_SIZE = 200
MAX_CHALLENGE_SIZE = 600 * 1024

# Hard list — preemptive block. Every endpoint is WAF-gated.
HARD_WAF_HOSTS = {
    "instagram.com": "Cloudflare",
    "facebook.com": "Cloudflare",
    "twitter.com": "Cloudflare",
    "x.com": "Cloudflare",
    "tiktok.com": "DataDome",
    "linkedin.com": "Akamai",
    "reddit.com": "Cloudflare",
}

# Soft list — post-response detection only. Homepage and static pages may work.
SOFT_WAF_HOSTS = {
    "truepeoplesearch.com": "PerimeterX",
    "usphonebook.com": "Akamai",
    "whitepages.com": "Akamai",
    "fastpeoplesearch.com": "PerimeterX",
    "spokeo.com": "PerimeterX",
    "beenverified.com": "PerimeterX",
    "intelius.com": "PerimeterX",
    "peoplefinders.com": "PerimeterX",
    "radaris.com": "Akamai",
    "ticketmaster.com": "Akamai",
    "amazon.com": "Akamai",
    "walmart.com": "Akamai",
    "bestbuy.com": "Akamai",
    "target.com": "Akamai",
    "chase.com": "Akamai",
    "bankofamerica.com": "Akamai",
    "nytimes.com": "Cloudflare",
    "wsj.com": "Cloudflare",
}


def _as_lower_bytes(data: bytes) -> bytes:
    try:
        return data.lower()
    except Exception:
        return data


def _body_contains_any(body_lower: bytes, signatures: list) -> bool:
    for sig in signatures:
        try:
            if sig.lower() in body_lower:
                return True
        except Exception:
            continue
    return False


def _lookup_host(hostname: str, table: dict) -> Optional[str]:
    if not hostname:
        return None
    h = hostname.lower().strip()
    candidates = [h]
    if h.startswith("www."):
        candidates.append(h[4:])
    for cand in candidates:
        if cand in table:
            return table[cand]
    for base, vendor in table.items():
        if h.endswith("." + base):
            return vendor
    return None


def is_known_waf_host(hostname: str) -> Optional[str]:
    """HARD list only — for preemptive blocking."""
    return _lookup_host(hostname, HARD_WAF_HOSTS)


def is_soft_waf_host(hostname: str) -> Optional[str]:
    """SOFT list — for logging and post-response detection hints."""
    return _lookup_host(hostname, SOFT_WAF_HOSTS)


def detect_waf_challenge(
    response_body: bytes,
    status_code: int,
    content_type: str,
    url: str = "",
) -> Optional[str]:
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
    for vendor, signatures in WAF_SIGNATURES.items():
        if _body_contains_any(body_lower, signatures):
            logger.info(
                "WAF challenge detected: vendor=%s url=%s status=%d bytes=%d",
                vendor, url, status_code, body_len,
            )
            return vendor
    return None


def classify_target_for_ui(url: str) -> Optional[dict]:
    """Pre-request check: only HARD list. Returns None for SOFT hosts."""
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