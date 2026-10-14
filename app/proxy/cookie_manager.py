from http.cookies import SimpleCookie
from typing import Dict, List, Optional
from urllib.parse import urlparse


class CookieManager:
    """
    Manages and isolates HTTP cookies per target domain and per user session.
    Prevents cross-site cookie leaks and maintains logged-in state across requests.
    """

    def __init__(self):
        # Nested dictionary structure: { user_id: { domain: { cookie_name: cookie_value } } }
        self._jars: Dict[str, Dict[str, Dict[str, str]]] = {}

    def _extract_domain(self, url: str) -> str:
        """Extracts the hostname domain from a full URL."""
        parsed = urlparse(url)
        return parsed.hostname.lower() if parsed.hostname else ""

    def save_response_cookies(self, user_id: str, target_url: str, raw_headers: Dict[str, str]) -> None:
        """
        Extracts Set-Cookie headers from an upstream response and stores them
        in the isolated jar for the specified user and target domain.
        """
        domain = self._extract_domain(target_url)
        if not domain:
            return

        if user_id not in self._jars:
            self._jars[user_id] = {}
        if domain not in self._jars[user_id]:
            self._jars[user_id][domain] = {}

        # Look for set-cookie headers in case-insensitive keys
        for key, val in raw_headers.items():
            if key.lower() == "set-cookie":
                cookie_parser = SimpleCookie()
                try:
                    cookie_parser.load(val)
                    for name, morsel in cookie_parser.items():
                        # Morsels can store empty values to delete cookies
                        if morsel.value:
                            self._jars[user_id][domain][name] = morsel.value
                        else:
                            self._jars[user_id][domain].pop(name, None)
                except Exception:
                    continue

    def get_cookie_header(self, user_id: str, target_url: str) -> Optional[str]:
        """
        Retrieves matching cookies for the target domain and formats them
        as a standard 'Cookie: name=value; name2=value2' header string.
        """
        domain = self._extract_domain(target_url)
        if not domain or user_id not in self._jars or domain not in self._jars[user_id]:
            return None

        cookies = self._jars[user_id][domain]
        if not cookies:
            return None

        cookie_pairs = [f"{k}={v}" for k, v in cookies.items()]
        return "; ".join(cookie_pairs)

    def clear_user_cookies(self, user_id: str) -> None:
        """Flushes all cookies stored for a specific user session."""
        if user_id in self._jars:
            self._jars[user_id].clear()


# Global in-memory cookie manager instance
cookie_jar = CookieManager()