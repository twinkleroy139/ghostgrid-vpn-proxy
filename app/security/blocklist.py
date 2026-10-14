from typing import Set
from urllib.parse import urlparse

# Default domain blocklist (prohibited domains, internal services, and known abusive targets)
DEFAULT_BLOCKED_DOMAINS: Set[str] = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "metadata.google.internal",
    "169.254.169.254",
    "render.com",           # Prevent infinite recursion through self-hosting infrastructure
    "api.render.com",
    "dashboard.render.com",
}

# Blocked top-level domains and extensions
BLOCKED_TLDS: Set[str] = {
    ".onion",
    ".i2p",
    ".internal",
    ".local",
}


def is_domain_blocked(url: str, custom_blocklist: Set[str] = None) -> bool:
    """
    Checks if a target URL's domain or subdomains are present in the blacklist.
    Also blocks darkweb (.onion) and local network (.local) top-level domains.
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        return True

    active_blocklist = DEFAULT_BLOCKED_DOMAINS if custom_blocklist is None else custom_blocklist

    # 1. Direct domain check
    if hostname in active_blocklist:
        return True

    # 2. Check parent domain parts (e.g. sub.render.com matches render.com)
    for blocked in active_blocklist:
        if hostname.endswith("." + blocked):
            return True

    # 3. Check blocked TLDs
    for tld in BLOCKED_TLDS:
        if hostname.endswith(tld):
            return True

    return False