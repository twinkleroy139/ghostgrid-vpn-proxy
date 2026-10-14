from typing import Set
from urllib.parse import urlparse

# Common tracking, analytics, and telemetry domains to block
TRACKER_DOMAINS: Set[str] = {
    "google-analytics.com",
    "googletagmanager.com",
    "analytics.google.com",
    "doubleclick.net",
    "pagead2.googlesyndication.com",
    "adnxs.com",
    "scorecardresearch.com",
    "facebook.net",
    "connect.facebook.net",
    "hotjar.com",
    "clarity.ms",
    "mixpanel.com",
}


def is_ad_or_tracker(url: str) -> bool:
    """
    Checks if an upstream URL belongs to a known advertisement or tracking service.
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        return False

    if hostname in TRACKER_DOMAINS:
        return True

    for tracker in TRACKER_DOMAINS:
        if hostname.endswith("." + tracker):
            return True

    return False